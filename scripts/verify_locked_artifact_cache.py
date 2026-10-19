#!/usr/bin/env python3
"""Verify every unique distribution artifact pinned by uv.lock against a local cache.

Cache entries are named by their lowercase SHA-256 digest. The verifier is offline,
read-only, and does not extract, import, or execute package contents.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import stat
import sys
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from spdx_terminal_safety import escape_terminal_controls

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_CHUNK_SIZE = 1024 * 1024
_MAX_LOCK_BYTES = 16 * 1024 * 1024
_MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
_MAX_ARTIFACTS = 1_000
_MAX_TOTAL_BYTES = 4 * 1024 * 1024 * 1024
_MAX_SECONDS = 600.0
_REPARSE_POINT = 0x400


class CacheVerificationError(ValueError):
    """Raised when lock records or cached bytes are invalid or incomplete."""


@dataclass(frozen=True)
class LockedArtifact:
    sha256: str
    size: int
    references: int


@dataclass(frozen=True)
class VerificationSummary:
    packages: int
    artifacts: int
    references: int
    total_bytes: int
    lock_sha256: str


def _open_regular_file(path: Path, label: str) -> BinaryIO:
    try:
        before = path.lstat()
    except OSError as exc:
        raise CacheVerificationError(
            f"cannot stat {label}: {type(exc).__name__}"
        ) from None
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or getattr(before, "st_file_attributes", 0) & _REPARSE_POINT
    ):
        raise CacheVerificationError(f"{label} must be a regular non-reparse file")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CacheVerificationError(
            f"cannot open {label}: {type(exc).__name__}"
        ) from None
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or getattr(opened, "st_file_attributes", 0) & _REPARSE_POINT
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise CacheVerificationError(f"{label} changed while opening")
        return os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise


def _load_lock(lock_path: Path) -> tuple[dict[str, LockedArtifact], int, int, str]:
    stream = _open_regular_file(lock_path, "uv.lock")
    with stream:
        if os.fstat(stream.fileno()).st_size > _MAX_LOCK_BYTES:
            raise CacheVerificationError("uv.lock exceeds its size limit")
        lock_bytes = stream.read(_MAX_LOCK_BYTES + 1)
    if len(lock_bytes) > _MAX_LOCK_BYTES:
        raise CacheVerificationError("uv.lock exceeds its size limit")
    lock_sha256 = hashlib.sha256(lock_bytes).hexdigest()
    try:
        lock = tomllib.loads(lock_bytes.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise CacheVerificationError(
            f"cannot parse uv.lock: {type(exc).__name__}"
        ) from None

    packages = lock.get("package")
    if not isinstance(packages, list):
        raise CacheVerificationError("uv.lock package list is malformed")
    artifacts: dict[str, LockedArtifact] = {}
    references = 0
    for package in packages:
        if not isinstance(package, dict):
            raise CacheVerificationError("uv.lock contains a malformed package record")
        records: list[dict[str, object]] = []
        sdist = package.get("sdist")
        if sdist is not None:
            if not isinstance(sdist, dict):
                raise CacheVerificationError(
                    "uv.lock contains a malformed sdist record"
                )
            records.append(sdist)
        wheels = package.get("wheels", [])
        if not isinstance(wheels, list):
            raise CacheVerificationError("uv.lock contains a malformed wheel list")
        for wheel in wheels:
            if not isinstance(wheel, dict):
                raise CacheVerificationError(
                    "uv.lock contains a malformed wheel record"
                )
            records.append(wheel)

        for record in records:
            raw_digest = record.get("hash")
            if not isinstance(raw_digest, str) or not raw_digest.startswith("sha256:"):
                raise CacheVerificationError("locked artifact lacks a SHA-256 digest")
            digest = raw_digest.removeprefix("sha256:")
            size = record.get("size")
            url = record.get("url")
            if not _SHA256_RE.fullmatch(digest):
                raise CacheVerificationError("locked artifact SHA-256 is malformed")
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                raise CacheVerificationError("locked artifact size is malformed")
            if not isinstance(url, str) or not url.startswith("https://"):
                raise CacheVerificationError(
                    "locked artifact URL is missing or not HTTPS"
                )
            if size > _MAX_ARTIFACT_BYTES:
                raise CacheVerificationError(
                    "locked artifact exceeds per-file size limit"
                )

            existing = artifacts.get(digest)
            if existing is not None and existing.size != size:
                raise CacheVerificationError(
                    "conflicting lock sizes use one SHA-256 digest"
                )
            artifacts[digest] = LockedArtifact(
                sha256=digest,
                size=size,
                references=1 if existing is None else existing.references + 1,
            )
            references += 1
            if len(artifacts) > _MAX_ARTIFACTS:
                raise CacheVerificationError(
                    "uv.lock contains too many unique artifacts"
                )
    total_bytes = sum(item.size for item in artifacts.values())
    if total_bytes > _MAX_TOTAL_BYTES:
        raise CacheVerificationError("locked artifacts exceed aggregate size limit")
    if not artifacts:
        raise CacheVerificationError("uv.lock contains no distribution artifacts")
    return artifacts, references, len(packages), lock_sha256


def verify_cache(lock_path: Path, cache_dir: Path) -> VerificationSummary:
    deadline = time.monotonic() + _MAX_SECONDS
    artifacts, references, package_count, lock_sha256 = _load_lock(lock_path)
    try:
        cache_info = cache_dir.lstat()
    except OSError as exc:
        raise CacheVerificationError(
            f"cannot stat cache directory: {type(exc).__name__}"
        ) from None
    if (
        not stat.S_ISDIR(cache_info.st_mode)
        or stat.S_ISLNK(cache_info.st_mode)
        or getattr(cache_info, "st_file_attributes", 0) & _REPARSE_POINT
    ):
        raise CacheVerificationError(
            "cache path must be a regular non-reparse directory"
        )

    verified_bytes = 0
    for artifact in artifacts.values():
        if time.monotonic() >= deadline:
            raise CacheVerificationError("verification exceeded its time limit")
        path = cache_dir / artifact.sha256
        stream = _open_regular_file(path, f"cache entry {artifact.sha256}")
        with stream:
            initial = os.fstat(stream.fileno())
            if initial.st_size != artifact.size:
                raise CacheVerificationError(
                    f"size differs from uv.lock: {artifact.sha256}"
                )
            digest = hashlib.sha256()
            read_bytes = 0
            for chunk in iter(lambda: stream.read(_CHUNK_SIZE), b""):
                if time.monotonic() >= deadline:
                    raise CacheVerificationError("verification exceeded its time limit")
                read_bytes += len(chunk)
                if read_bytes > artifact.size:
                    raise CacheVerificationError(
                        f"cache entry grew while reading: {artifact.sha256}"
                    )
                digest.update(chunk)
            final = os.fstat(stream.fileno())
            if (
                read_bytes != artifact.size
                or digest.hexdigest() != artifact.sha256
                or (initial.st_dev, initial.st_ino, initial.st_size)
                != (final.st_dev, final.st_ino, final.st_size)
                or getattr(initial, "st_mtime_ns", None)
                != getattr(final, "st_mtime_ns", None)
            ):
                raise CacheVerificationError(
                    f"cache bytes differ from uv.lock: {artifact.sha256}"
                )
        verified_bytes += read_bytes

    return VerificationSummary(
        packages=package_count,
        artifacts=len(artifacts),
        references=references,
        total_bytes=verified_bytes,
        lock_sha256=lock_sha256,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lockfile", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary = verify_cache(args.lockfile, args.cache_dir)
    except (CacheVerificationError, OSError) as exc:
        message = escape_terminal_controls(str(exc))
        print(f"ERROR: {message}", file=sys.stderr)
        return 2
    print(
        f"Verified {summary.packages} packages, {summary.artifacts} unique artifacts, "
        f"{summary.references} lock references, {summary.total_bytes} bytes; "
        f"uv.lock SHA-256 {summary.lock_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
