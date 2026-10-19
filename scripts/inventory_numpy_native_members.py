#!/usr/bin/env python3
"""Hash native-file candidates in every locked NumPy wheel without extraction to disk.

The cache is keyed by the SHA-256 recorded in uv.lock. The output binds each
candidate member's bytes to both that locked wheel and its wheel RECORD row.
Candidate members are streamed and decompressed for hashing. This is an
artifact-content inventory, not a build-provenance or linkage map.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
import re
import stat
import sys
import tempfile
import tomllib
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from urllib.parse import urlsplit

from verify_spdx_evidence import (
    _ArchiveReadBudget,
    EvidenceVerificationError,
    _read_bounded_lock_bytes,
    _zip_directory_info,
)
from spdx_terminal_safety import escape_terminal_controls
from safe_output import write_atomic_text

_CHUNK_SIZE = 1024 * 1024
_MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
_MAX_MEMBER_BYTES = 512 * 1024 * 1024
_MAX_NATIVE_BYTES = 2 * 1024 * 1024 * 1024
_MAX_MEMBERS = 50_000
_MAX_RECORD_BYTES = 16 * 1024 * 1024
_REPARSE_POINT = 0x400
_NATIVE_SUFFIX_RE = re.compile(
    r"\.(?:a|bin|dylib|dll|exe|lib|node|pyd|wasm|so(?:\.\d+)*)\Z",
    re.IGNORECASE,
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class InventoryError(Exception):
    """Raised when lock/cache/archive identity or bounds are invalid."""


@dataclass(frozen=True)
class Wheel:
    package: str
    version: str
    url: str
    sha256: str
    size: int

    @property
    def filename(self) -> str:
        return PurePosixPath(urlsplit(self.url).path).name


def _locked_numpy_wheels(lock_path: Path) -> tuple[list[Wheel], str]:
    try:
        lock_bytes = _read_bounded_lock_bytes(lock_path)
    except (EvidenceVerificationError, OSError) as exc:
        raise InventoryError(f"cannot read uv.lock: {exc}") from exc
    lock_sha256 = hashlib.sha256(lock_bytes).hexdigest()
    try:
        lock = tomllib.loads(lock_bytes.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise InventoryError(f"cannot parse uv.lock: {exc}") from exc

    wheels: list[Wheel] = []
    for package in lock.get("package", []):
        if not isinstance(package, dict) or package.get("name") != "numpy":
            continue
        version = package.get("version")
        artifacts = package.get("wheels", [])
        if not isinstance(version, str) or not isinstance(artifacts, list):
            raise InventoryError("malformed NumPy lock record")
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                raise InventoryError(f"malformed wheel record for NumPy {version}")
            url = artifact.get("url")
            digest = artifact.get("hash")
            size = artifact.get("size")
            if (
                not isinstance(url, str)
                or not isinstance(digest, str)
                or not digest.startswith("sha256:")
                or not isinstance(size, int)
                or isinstance(size, bool)
                or size < 0
            ):
                raise InventoryError(f"invalid wheel identity for NumPy {version}")
            sha256 = digest.removeprefix("sha256:")
            if not _SHA256_RE.fullmatch(sha256):
                raise InventoryError(f"invalid wheel SHA-256 for NumPy {version}")
            wheels.append(Wheel("numpy", version, url, sha256, size))

    if not wheels:
        raise InventoryError("uv.lock contains no NumPy wheels")
    if len({wheel.sha256 for wheel in wheels}) != len(wheels):
        raise InventoryError("uv.lock contains duplicate NumPy wheel hashes")
    return sorted(
        wheels, key=lambda wheel: (wheel.version, wheel.filename)
    ), lock_sha256


@contextmanager
def _verified_artifact_snapshot(path: Path, wheel: Wheel) -> Iterator[BinaryIO]:
    """Yield a temporary snapshot whose bytes match one locked wheel hash.

    Hashing a cache path and reopening it later leaves a replacement race. Copy
    from one identity-checked handle while hashing, then inspect only the
    verified snapshot so ZIP parsing cannot observe different cache bytes.
    """
    try:
        info = path.lstat()
    except OSError as exc:
        raise InventoryError(f"cannot stat cache object {path.name}: {exc}") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT
    ):
        raise InventoryError(f"cache object is not a regular file: {path.name}")
    if info.st_size != wheel.size or info.st_size > _MAX_ARTIFACT_BYTES:
        raise InventoryError(
            f"locked size mismatch or artifact exceeds limit: {path.name}"
        )

    digest = hashlib.sha256()
    copied_bytes = 0
    snapshot: BinaryIO | None = None
    try:
        snapshot = tempfile.TemporaryFile(mode="w+b")
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_size != info.st_size
                or opened.st_ino != info.st_ino
                or opened.st_dev != info.st_dev
            ):
                raise InventoryError(f"cache object changed while opening: {path.name}")
            for chunk in iter(lambda: stream.read(_CHUNK_SIZE), b""):
                copied_bytes += len(chunk)
                if copied_bytes > wheel.size or copied_bytes > _MAX_ARTIFACT_BYTES:
                    raise InventoryError(
                        f"cache object grew while reading: {path.name}"
                    )
                digest.update(chunk)
                snapshot.write(chunk)
        if copied_bytes != wheel.size:
            raise InventoryError(f"locked size mismatch while reading: {path.name}")
        actual_sha256 = digest.hexdigest()
        if actual_sha256 != wheel.sha256:
            raise InventoryError(
                f"cache SHA-256 differs from uv.lock: {wheel.filename}"
            )
        snapshot.seek(0)
        yield snapshot
    except OSError as exc:
        raise InventoryError(f"cannot hash cache object {path.name}: {exc}") from exc
    finally:
        if snapshot is not None:
            snapshot.close()


def _record_rows(
    archive: zipfile.ZipFile, infos: list[zipfile.ZipInfo]
) -> dict[str, tuple[str, int]]:
    record_infos = [
        info for info in infos if info.filename.endswith(".dist-info/RECORD")
    ]
    if len(record_infos) != 1:
        raise InventoryError("wheel must contain exactly one .dist-info/RECORD")
    record_info = record_infos[0]
    if record_info.file_size < 0 or record_info.file_size > _MAX_RECORD_BYTES:
        raise InventoryError("wheel RECORD exceeds byte limit")
    try:
        with archive.open(record_info, "r") as raw:
            content = raw.read(_MAX_RECORD_BYTES + 1)
        if len(content) != record_info.file_size or len(content) > _MAX_RECORD_BYTES:
            raise InventoryError("wheel RECORD size differs from ZIP directory")
        text = content.decode("utf-8")
        result: dict[str, tuple[str, int]] = {}
        for row in csv.reader(io.StringIO(text, newline="")):
            if len(result) >= _MAX_MEMBERS:
                raise InventoryError("wheel RECORD exceeds row limit")
            if len(row) != 3:
                raise InventoryError("malformed wheel RECORD row")
            member_path, digest, raw_size = row
            if member_path in result:
                raise InventoryError("duplicate path in wheel RECORD")
            if not raw_size:
                size = -1
            else:
                try:
                    size = int(raw_size)
                except ValueError as exc:
                    raise InventoryError("invalid wheel RECORD size") from exc
            result[member_path] = (digest, size)
        return result
    except (
        OSError,
        UnicodeDecodeError,
        csv.Error,
        zipfile.BadZipFile,
        RuntimeError,
    ) as exc:
        raise InventoryError(f"cannot read wheel RECORD: {exc}") from exc


def _member_digest(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    digest = hashlib.sha256()
    total = 0
    try:
        with archive.open(info) as stream:
            for chunk in iter(lambda: stream.read(_CHUNK_SIZE), b""):
                total += len(chunk)
                if total > info.file_size:
                    raise InventoryError(
                        f"member expanded beyond declared size: {info.filename}"
                    )
                digest.update(chunk)
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise InventoryError(
            f"cannot read wheel member {info.filename}: {exc}"
        ) from exc
    if total != info.file_size:
        raise InventoryError(f"member size differs from ZIP directory: {info.filename}")
    return digest.hexdigest()


def _record_digest(member_sha256: str) -> str:
    encoded = base64.urlsafe_b64encode(bytes.fromhex(member_sha256)).decode("ascii")
    return f"sha256={encoded.rstrip('=')}"


def _inventory_wheel(
    wheel: Wheel, lock_sha256: str, cache_dir: Path
) -> list[dict[str, object]]:
    artifact_path = cache_dir / wheel.sha256
    rows: list[dict[str, object]] = []
    expanded_native_bytes = 0
    try:
        with _verified_artifact_snapshot(artifact_path, wheel) as stream:
            try:
                _zip_directory_info(stream, _ArchiveReadBudget())
            except EvidenceVerificationError as exc:
                raise InventoryError(f"invalid wheel ZIP directory: {exc}") from exc
            stream.seek(0)
            with zipfile.ZipFile(stream) as archive:
                infos = archive.infolist()
                if len(infos) > _MAX_MEMBERS:
                    raise InventoryError(
                        f"wheel exceeds member-count limit: {wheel.filename}"
                    )
                record = _record_rows(archive, infos)
                seen_paths: set[str] = set()
                for info in infos:
                    path = info.filename
                    if info.is_dir() or not _NATIVE_SUFFIX_RE.search(
                        PurePosixPath(path).name
                    ):
                        continue
                    if path in seen_paths:
                        raise InventoryError(
                            f"duplicate native member path: {wheel.filename}:{path}"
                        )
                    seen_paths.add(path)
                    if (
                        path.startswith("/")
                        or "\\" in path
                        or ".." in PurePosixPath(path).parts
                    ):
                        raise InventoryError(
                            f"unsafe ZIP member path: {wheel.filename}:{path}"
                        )
                    mode = info.external_attr >> 16
                    if stat.S_ISLNK(mode) or (mode and not stat.S_ISREG(mode)):
                        raise InventoryError(
                            f"native member is not a regular file: {wheel.filename}:{path}"
                        )
                    if info.flag_bits & 1:
                        raise InventoryError(
                            f"encrypted wheel member: {wheel.filename}:{path}"
                        )
                    if info.file_size > _MAX_MEMBER_BYTES:
                        raise InventoryError(
                            f"native member exceeds size limit: {wheel.filename}:{path}"
                        )
                    expanded_native_bytes += info.file_size
                    if expanded_native_bytes > _MAX_NATIVE_BYTES:
                        raise InventoryError(
                            "native members exceed aggregate expanded-byte limit"
                        )

                    member_sha256 = _member_digest(archive, info)
                    record_digest, record_size = record.get(path, ("", -2))
                    if (
                        record_digest != _record_digest(member_sha256)
                        or record_size != info.file_size
                    ):
                        raise InventoryError(
                            f"native member differs from wheel RECORD: {wheel.filename}:{path}"
                        )

                    platform = wheel.filename[:-4].rsplit("-", 1)[-1]
                    rows.append(
                        {
                            "artifact_sha256": wheel.sha256,
                            "artifact_size": wheel.size,
                            "lock_sha256": lock_sha256,
                            "member_path": path,
                            "member_sha256": member_sha256,
                            "member_size": info.file_size,
                            "package": wheel.package,
                            "platform_tag": platform,
                            "record_sha256": record_digest.removeprefix("sha256="),
                            "record_verified": True,
                            "version": wheel.version,
                            "wheel_filename": wheel.filename,
                        }
                    )
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise InventoryError(f"cannot inspect wheel {wheel.filename}: {exc}") from exc
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    payload = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
        for row in rows
    )
    try:
        write_atomic_text(path, payload)
    except OSError as exc:
        raise InventoryError(f"cannot write inventory {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True, help="path to uv.lock")
    parser.add_argument(
        "--cache-dir", type=Path, required=True, help="SHA-256-keyed artifact cache"
    )
    parser.add_argument("--output", type=Path, required=True, help="JSONL destination")
    args = parser.parse_args(argv)

    try:
        wheels, lock_sha256 = _locked_numpy_wheels(args.lock)
        rows: list[dict[str, object]] = []
        for wheel in wheels:
            rows.extend(_inventory_wheel(wheel, lock_sha256, args.cache_dir))
        rows.sort(
            key=lambda row: (
                str(row["version"]),
                str(row["wheel_filename"]),
                str(row["member_path"]),
            )
        )
        _write_jsonl(args.output, rows)
    except (InventoryError, OSError) as exc:
        message = escape_terminal_controls(str(exc))
        print(f"numpy native member inventory: {message}", file=sys.stderr)
        return 2

    print(
        f"Verified {len(wheels)} locked NumPy wheels and {len(rows)} native members; "
        f"lock SHA-256 {lock_sha256}; output {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
