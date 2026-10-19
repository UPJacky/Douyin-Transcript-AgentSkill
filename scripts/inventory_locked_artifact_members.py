#!/usr/bin/env python3
"""Create a read-only member inventory for cached uv.lock artifacts.

The script never downloads, installs, or extracts artifacts. It verifies each
SHA-keyed cache object against uv.lock, then records archive member paths and
declared uncompressed sizes. Candidate labels are filename/path heuristics only.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import os
import re
import stat
import sys
import tarfile
import time
import tomllib
import unicodedata
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from urllib.parse import urlsplit

from verify_spdx_evidence import (
    EvidenceVerificationError,
    _ArchiveReadBudget,
    _read_bounded_lock_bytes,
    _verified_artifact_snapshot,
    _zip_directory_info,
)
from spdx_terminal_safety import (
    escape_terminal_controls,
    escape_terminal_controls_unambiguously,
)
from safe_output import write_atomic_text

_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
_CHUNK_SIZE = 1024 * 1024
_MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
_MAX_TOTAL_ARTIFACT_BYTES = 2 * 1024 * 1024 * 1024
_MAX_ARCHIVE_MEMBERS = 50_000
_MAX_MEMBER_BYTES = 512 * 1024 * 1024
_MAX_ARCHIVE_SECONDS = 120.0
_MAX_TOTAL_SECONDS = 1_800.0
_REPARSE_POINT = 0x400

_LICENSE_NAME_RE = re.compile(
    r"license|licence|notice|copying|third[-_. ]?party|thirdparty", re.IGNORECASE
)
_NATIVE_EXTENSIONS = {
    ".a",
    ".bin",
    ".dylib",
    ".dll",
    ".exe",
    ".framework",
    ".lib",
    ".node",
    ".pyd",
    ".so",
    ".wasm",
}
_NATIVE_NAME_RE = re.compile(
    r"ffmpeg|libav|avcodec|avformat|avutil|swresample|swscale|x264|x265|"
    r"openblas|libgomp|libquadmath|cudnn|iomp|openmp|onnxruntime|"
    r"ctranslate2|tokenizers|libtorch|mkl",
    re.IGNORECASE,
)
_DEPENDENCY_METADATA_NAMES = {
    "build-details.json",
    "cargo.lock",
    "cargo.toml",
    "cmakelists.txt",
    "direct_url.json",
    "entry_points.txt",
    "manifest.in",
    "metadata",
    "npm-shrinkwrap.json",
    "package-lock.json",
    "package.json",
    "pkg-info",
    "pyproject.toml",
    "record",
    "sbom.json",
    "setup.cfg",
    "setup.py",
    "sources.txt",
    "wheel",
}
_DEPENDENCY_METADATA_SUFFIXES = {".cmake", ".pc"}


class InventoryError(Exception):
    """Raised when lock identities, cache objects, or archive bounds fail."""


@dataclass(frozen=True)
class LockIdentity:
    package: str
    version: str
    artifact_type: str
    url: str
    sha256: str
    size: int

    @property
    def filename(self) -> str:
        return PurePosixPath(urlsplit(self.url).path).name


class BoundedReader:
    """Cap bytes expanded while walking a gzip tar stream."""

    def __init__(self, source: BinaryIO, limit: int, deadline: float) -> None:
        self._source = source
        self._limit = limit
        self._deadline = deadline
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        if time.monotonic() >= self._deadline:
            raise InventoryError("archive member listing exceeded its time limit")
        remaining = self._limit - self.bytes_read
        if size < 0:
            size = _CHUNK_SIZE
        if size == 0:
            return b""
        data = self._source.read(min(size, _CHUNK_SIZE, remaining + 1))
        self.bytes_read += len(data)
        if self.bytes_read > self._limit:
            raise InventoryError("archive exceeds expanded-byte limit")
        return data


def _checked_regular_file(path: Path) -> tuple[BinaryIO, os.stat_result]:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise InventoryError(f"cache object is not a regular file: {path.name}")
    if getattr(before, "st_file_attributes", 0) & _REPARSE_POINT:
        raise InventoryError(f"cache object is a Windows reparse point: {path.name}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    stream = os.fdopen(descriptor, "rb")
    opened = os.fstat(stream.fileno())
    if (
        not stat.S_ISREG(opened.st_mode)
        or opened.st_dev != before.st_dev
        or opened.st_ino != before.st_ino
        or opened.st_size != before.st_size
        or opened.st_mtime_ns != before.st_mtime_ns
    ):
        stream.close()
        raise InventoryError(
            f"cache object identity changed while opening: {path.name}"
        )
    return stream, opened


def _lock_identities(lock_path: Path) -> tuple[list[LockIdentity], str, int]:
    try:
        lock_bytes = _read_bounded_lock_bytes(lock_path)
    except (EvidenceVerificationError, OSError) as exc:
        raise InventoryError(f"cannot read uv.lock: {exc}") from exc
    lock_digest = hashlib.sha256(lock_bytes).hexdigest()
    try:
        lock = tomllib.loads(lock_bytes.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise InventoryError(f"cannot parse uv.lock: {exc}") from exc

    records: list[LockIdentity] = []
    packages = lock.get("package")
    if not isinstance(packages, list):
        raise InventoryError("uv.lock has no package array")
    for package in packages:
        if not isinstance(package, dict):
            raise InventoryError("uv.lock contains a malformed package record")
        name = package.get("name")
        version = package.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            continue
        artifacts: list[tuple[str, object]] = []
        if isinstance(package.get("sdist"), dict):
            artifacts.append(("sdist", package["sdist"]))
        wheels = package.get("wheels", [])
        if isinstance(wheels, list):
            artifacts.extend(("wheel", wheel) for wheel in wheels)
        for artifact_type, artifact in artifacts:
            if not isinstance(artifact, dict):
                raise InventoryError(f"malformed artifact record for {name} {version}")
            url = artifact.get("url")
            raw_hash = artifact.get("hash")
            size = artifact.get("size")
            if not isinstance(url, str) or not isinstance(raw_hash, str):
                raise InventoryError(f"artifact lacks URL/hash for {name} {version}")
            if any(unicodedata.category(char) == "Cc" for char in url):
                raise InventoryError(
                    f"artifact URL contains a control character for {name} {version}"
                )
            if not raw_hash.startswith("sha256:"):
                raise InventoryError(f"non-SHA256 lock hash for {name} {version}")
            digest = raw_hash.removeprefix("sha256:")
            if not _DIGEST_RE.fullmatch(digest):
                raise InventoryError(f"invalid lock SHA-256 for {name} {version}")
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                raise InventoryError(f"invalid locked size for {name} {version}")
            records.append(
                LockIdentity(name, version, artifact_type, url, digest, size)
            )
    return records, lock_digest, len(packages)


def _candidate_flags(path: str) -> list[str]:
    folded = path.casefold()
    basename = PurePosixPath(path).name.casefold()
    suffixes = {suffix.casefold() for suffix in PurePosixPath(path).suffixes}
    flags: list[str] = []
    if _LICENSE_NAME_RE.search(path):
        flags.append("license-notice-name")
    if suffixes & _NATIVE_EXTENSIONS:
        flags.append("native-binary-extension")
    if _NATIVE_NAME_RE.search(basename):
        flags.append("native-dependency-name")
    if (
        basename in _DEPENDENCY_METADATA_NAMES
        or suffixes & _DEPENDENCY_METADATA_SUFFIXES
    ):
        flags.append("dependency-metadata-name")
    if ".dist-info/" in folded and basename in {"metadata", "record", "wheel"}:
        if "dependency-metadata-name" not in flags:
            flags.append("dependency-metadata-name")
    return sorted(flags)


def _zip_members(
    stream: BinaryIO, deadline: float, expanded_limit: int
) -> Iterator[dict[str, object]]:
    # The cache file is capped at 512 MiB; member count is separately bounded.
    _zip_directory_info(stream, _ArchiveReadBudget(deadline=deadline))
    with zipfile.ZipFile(stream) as archive:
        infos = archive.infolist()
        if len(infos) > _MAX_ARCHIVE_MEMBERS:
            raise InventoryError("ZIP archive exceeds the member-count limit")
        for info in infos:
            if time.monotonic() >= deadline:
                raise InventoryError("ZIP member listing exceeded its time limit")
            if info.file_size > _MAX_MEMBER_BYTES:
                raise InventoryError(f"ZIP member exceeds size limit: {info.filename}")
            if info.file_size > expanded_limit:
                raise InventoryError("ZIP archive exceeds declared expanded-byte limit")
            expanded_limit -= info.file_size
            mode = info.external_attr >> 16
            member_type = _zip_member_type(mode, info.is_dir())
            path = info.filename
            yield {
                "path": path,
                "size": info.file_size,
                "type": member_type,
                "candidate_flags": _candidate_flags(path),
            }


def _zip_member_type(mode: int, is_directory: bool) -> str:
    """Classify ZIP entries with omitted Unix type bits as regular files."""
    if is_directory:
        return "directory"
    file_type = stat.S_IFMT(mode)
    if file_type == stat.S_IFLNK:
        return "symlink"
    if file_type in {0, stat.S_IFREG}:
        return "file"
    return "other"


def _tar_members(
    stream: BinaryIO, deadline: float, remaining_total_expanded: int
) -> tuple[list[dict[str, object]], int]:
    expanded_limit = min(_MAX_MEMBER_BYTES, remaining_total_expanded)
    with gzip.GzipFile(fileobj=stream, mode="rb") as decompressor:
        bounded = BoundedReader(decompressor, expanded_limit, deadline)
        with tarfile.open(fileobj=bounded, mode="r|") as archive:
            members: list[dict[str, object]] = []
            declared_total = 0
            for info in archive:
                if time.monotonic() >= deadline:
                    raise InventoryError("tar member listing exceeded its time limit")
                if len(members) >= _MAX_ARCHIVE_MEMBERS:
                    raise InventoryError("tar archive exceeds the member-count limit")
                if info.size < 0 or info.size > _MAX_MEMBER_BYTES:
                    raise InventoryError(
                        f"tar member has invalid/oversized size: {info.name}"
                    )
                declared_total += info.size
                if declared_total > expanded_limit:
                    raise InventoryError(
                        "tar archive exceeds declared expanded-byte limit"
                    )
                if info.isdir():
                    member_type = "directory"
                elif info.issym():
                    member_type = "symlink"
                elif info.islnk():
                    member_type = "hardlink"
                elif info.isfile():
                    member_type = "file"
                else:
                    member_type = "other"
                path = info.name
                members.append(
                    {
                        "path": path,
                        "size": info.size,
                        "type": member_type,
                        "candidate_flags": _candidate_flags(path),
                    }
                )
            expanded = bounded.bytes_read
    return members, expanded


def _archive_members(
    cache_path: Path,
    identities: list[LockIdentity],
    deadline: float,
    remaining_total_expanded: int,
) -> tuple[str, list[dict[str, object]], int]:
    try:
        expected_sizes = {identity.size for identity in identities}
        if len(expected_sizes) != 1:
            raise InventoryError(f"lock records disagree on size for {cache_path.name}")
        expected_size = expected_sizes.pop()
        if expected_size < 0 or expected_size > _MAX_ARTIFACT_BYTES:
            raise InventoryError(
                f"locked artifact exceeds per-artifact limit: {cache_path.name}"
            )
        with _verified_artifact_snapshot(
            cache_path,
            cache_path.name,
            expected_size,
            max_bytes=_MAX_ARTIFACT_BYTES,
            deadline=deadline,
        ) as stream:
            sample = stream.read(4)
            stream.seek(0)
            if sample.startswith(b"PK\x03\x04"):
                members = list(
                    _zip_members(
                        stream,
                        deadline,
                        min(_MAX_MEMBER_BYTES, remaining_total_expanded),
                    )
                )
                return "zip", members, sum(int(item["size"]) for item in members)
            urls = {urlsplit(identity.url).path.casefold() for identity in identities}
            if not any(url.endswith((".tar.gz", ".tgz")) for url in urls):
                raise InventoryError(
                    f"unsupported archive format for lock identity: {cache_path.name}"
                )
            stream.seek(0)
            members, expanded = _tar_members(stream, deadline, remaining_total_expanded)
            return "tar.gz", members, expanded
    except EvidenceVerificationError as exc:
        raise InventoryError(
            f"cache artifact verification failed: {cache_path.name}"
        ) from exc
    except (
        OSError,
        EOFError,
        tarfile.TarError,
        zipfile.BadZipFile,
        gzip.BadGzipFile,
    ) as exc:
        raise InventoryError(f"cannot list archive {cache_path.name}: {exc}") from exc


def _escape_cell(value: str) -> str:
    escaped = html.escape(value, quote=True).replace("|", "&#124;")
    escaped = "".join(
        f"&#{ord(char)};" if unicodedata.category(char) == "Cc" else char
        for char in escaped
    )
    return escape_terminal_controls_unambiguously(escaped)


def _atomic_write(path: Path, content: str) -> None:
    write_atomic_text(path, content)


def build_inventory(
    lockfile: Path,
    cache_dir: Path,
    *,
    max_total_expanded_bytes: int = _MAX_TOTAL_ARTIFACT_BYTES,
) -> tuple[str, str]:
    if (
        not isinstance(max_total_expanded_bytes, int)
        or isinstance(max_total_expanded_bytes, bool)
        or max_total_expanded_bytes <= 0
        or max_total_expanded_bytes > 64 * 1024**3
    ):
        raise InventoryError("expanded-byte limit must be between 1 byte and 64 GiB")
    start = time.monotonic()
    deadline = start + _MAX_TOTAL_SECONDS
    records, lock_digest, package_record_count = _lock_identities(lockfile)
    lock_by_digest: dict[str, list[LockIdentity]] = {}
    for identity in records:
        lock_by_digest.setdefault(identity.sha256, []).append(identity)
    unique_lock_artifacts = len(lock_by_digest)
    if not cache_dir.is_dir():
        raise InventoryError(f"cache directory does not exist: {cache_dir}")
    cache_children = list(cache_dir.iterdir())
    if any(path.is_dir() for path in cache_children):
        raise InventoryError("cache must be flat; subdirectories are not inventoried")
    cache_files = sorted(cache_children, key=lambda path: path.name)
    if not cache_files:
        raise InventoryError("cache directory contains no artifact files")
    total_compressed = 0
    for path in cache_files:
        if not _DIGEST_RE.fullmatch(path.name):
            raise InventoryError(f"unexpected cache entry name: {path.name}")
        if path.name not in lock_by_digest:
            raise InventoryError(
                f"cache object has no exact uv.lock identity: {path.name}"
            )
        stream, info = _checked_regular_file(path)
        stream.close()
        total_compressed += info.st_size
        if total_compressed > _MAX_TOTAL_ARTIFACT_BYTES:
            raise InventoryError("cache exceeds aggregate compressed-byte limit")
        expected_sizes = {identity.size for identity in lock_by_digest[path.name]}
        if len(expected_sizes) != 1:
            raise InventoryError(f"lock records disagree on size for {path.name}")

    jsonl_rows: list[str] = []
    artifacts: list[dict[str, object]] = []
    total_expanded = 0
    candidate_counts: dict[str, int] = {}
    total_members = 0
    for cache_path in cache_files:
        if time.monotonic() >= deadline:
            raise InventoryError("complete inventory exceeded its time limit")
        identities = sorted(
            lock_by_digest[cache_path.name],
            key=lambda item: (
                item.package.casefold(),
                item.version,
                item.artifact_type,
                item.url,
            ),
        )
        expected_size = identities[0].size
        remaining = (
            min(_MAX_TOTAL_ARTIFACT_BYTES, max_total_expanded_bytes) - total_expanded
        )
        if remaining <= 0:
            raise InventoryError("inventory exceeds configured expanded-byte limit")
        archive_format, members, expanded = _archive_members(
            cache_path,
            identities,
            min(deadline, time.monotonic() + _MAX_ARCHIVE_SECONDS),
            remaining,
        )
        total_expanded += expanded
        artifact_record = {
            "sha256": cache_path.name,
            "cached_size": expected_size,
            "archive_format": archive_format,
            "lock_identities": [
                {
                    "package": identity.package,
                    "version": identity.version,
                    "artifact_type": identity.artifact_type,
                    "url": identity.url,
                    "filename": identity.filename,
                    "sha256": identity.sha256,
                    "size": identity.size,
                }
                for identity in identities
            ],
            "member_count": len(members),
            "candidate_member_count": sum(
                bool(member["candidate_flags"]) for member in members
            ),
            "expanded_bytes_walked": expanded,
        }
        artifacts.append(artifact_record)
        for member in members:
            flags = member["candidate_flags"]
            total_members += 1
            for flag in flags:
                candidate_counts[flag] = candidate_counts.get(flag, 0) + 1
            jsonl_rows.append(
                json.dumps(
                    {
                        "artifact_sha256": cache_path.name,
                        "member_path": escape_terminal_controls_unambiguously(
                            str(member["path"])
                        ),
                        "member_size": member["size"],
                        "member_type": member["type"],
                        "candidate_flags": flags,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
    if len(cache_files) != len({item["sha256"] for item in artifacts}):
        raise InventoryError("cache contains duplicate artifact identities")
    if total_expanded > max_total_expanded_bytes:
        raise InventoryError("expanded archive walk exceeds configured aggregate limit")

    summary = {
        "lockfile": lockfile.as_posix(),
        "lockfile_sha256": lock_digest,
        "lock_package_records": package_record_count,
        "lock_unique_artifact_identities": unique_lock_artifacts,
        "cache_artifact_count": len(artifacts),
        "cache_compressed_bytes": total_compressed,
        "archive_member_records": total_members,
        "expanded_bytes_walked": total_expanded,
        "candidate_member_counts_by_flag": dict(sorted(candidate_counts.items())),
        "artifacts": artifacts,
    }
    jsonl_content = "\n".join(jsonl_rows) + "\n"
    markdown = _render_markdown(summary)
    return markdown, jsonl_content


def _render_markdown(summary: dict[str, object]) -> str:
    # Candidate detail is rendered from the complete JSONL by the caller-facing
    # report link; this document keeps one row per artifact and counts by label.
    lock_identities = summary["artifacts"]
    lines = [
        "# Locked artifact member inventory",
        "",
        (
            "Generated from the local SHA-256-keyed cache using "
            "`scripts/inventory_locked_artifact_members.py`."
        ),
        "",
        "## Scope and method",
        "",
        f"- `uv.lock` SHA-256: `{summary['lockfile_sha256']}`.",
        (
            f"- Lock coverage: {summary['cache_artifact_count']} cached artifacts with exact "
            f"lock identities out of {summary['lock_unique_artifact_identities']} unique "
            "artifact identities in the lock; this is a cached evidence subset, not a complete "
            "inventory of all lock artifacts."
        ),
        (
            f"- Cached artifact bytes whose SHA-256 values were checked: "
            f"{summary['cache_compressed_bytes']:,}; expanded archive bytes traversed for tar "
            f"indexing: {summary['expanded_bytes_walked']:,}."
        ),
        (
            f"- Archive member rows: {summary['archive_member_records']:,}; one JSONL row per "
            "member is in [`artifact-member-inventory.jsonl`](artifact-member-inventory.jsonl). "
            "Each row carries the artifact SHA-256, member path, declared uncompressed size, "
            "archive-entry type, and heuristic candidate labels; the table below maps each "
            "artifact SHA-256 to its lock URL, package, version, type, and filename."
        ),
        (
            "- Every cached object matched a SHA-256, size, URL, package/version and artifact "
            "type recorded in `uv.lock`. ZIP/tar headers were read in place; no member was "
            "extracted to disk. The script did not download or install anything."
        ),
        (
            "- Candidate labels are filename/path/extension signals only. They do not establish "
            "licensing, applicability, provenance, linkage or publication permission."
        ),
        "",
        "## Cached artifacts",
        "",
        (
            "| Package/version | Type | Filename | Lock URL | SHA-256 | Bytes | Members | "
            "Candidate members |"
        ),
        "|---|---|---|---|---|---:|---:|---:|",
    ]
    for artifact in lock_identities:
        identities = artifact["lock_identities"]
        package_labels = ", ".join(
            f"{identity['package']} {identity['version']}" for identity in identities
        )
        artifact_types = ", ".join(
            sorted({identity["artifact_type"] for identity in identities})
        )
        filenames = ", ".join(sorted({identity["filename"] for identity in identities}))
        urls = "<br>".join(sorted({identity["url"] for identity in identities}))
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_cell(package_labels),
                    _escape_cell(artifact_types),
                    _escape_cell(filenames),
                    _escape_cell(urls),
                    f"`{artifact['sha256']}`",
                    f"{artifact['cached_size']:,}",
                    f"{artifact['member_count']:,}",
                    f"{artifact['candidate_member_count']:,}",
                ]
            )
            + " |"
        )
    counts = summary["candidate_member_counts_by_flag"]
    lines.extend(
        [
            "",
            "## Candidate flag counts",
            "",
            "These counts are per member row; a member can carry more than one flag.",
            "",
            "| Candidate label | Member rows |",
            "|---|---:|",
        ]
    )
    for label, count in counts.items():
        lines.append(f"| `{label}` | {count:,} |")
    lines.extend(
        [
            "",
            "## Candidate flag meanings",
            "",
            (
                "- `license-notice-name`: member path contains `LICENSE`, `LICENCE`, `NOTICE`, "
                "`COPYING`, or a `THIRD-PARTY` spelling."
            ),
            (
                "- `native-binary-extension`: member suffix is a common native/binary extension "
                "(`.dll`, `.pyd`, `.so`, `.dylib`, `.a`, `.lib`, `.exe`, `.node`, `.wasm`, or "
                "related entries in the scanner)."
            ),
            (
                "- `native-dependency-name`: the member filename contains a known native-library "
                "name such as FFmpeg/libav, x264/x265, OpenBLAS, cuDNN, OpenMP, ONNX Runtime, "
                "CTranslate2, Tokenizers, or MKL."
            ),
            (
                "- `dependency-metadata-name`: the member filename is a package/build/dependency "
                "metadata name such as `METADATA`, `PKG-INFO`, `RECORD`, `Cargo.lock`, "
                "`package.json`, `pyproject.toml`, or a `.cmake`/`.pc` file."
            ),
            "",
            "## Limits",
            "",
            (
                "This scan lists cached lock-pinned archive members and labels names/paths that "
                "merit later review. It does not inspect file contents, enumerate binaries' linked "
                "dependencies, prove build inputs, decide which dependencies are shipped, or draw "
                "any `licenseConcluded` value. The separate project distribution-scope and "
                "license-owner decisions remain open."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lockfile",
        type=Path,
        default=root / "skills" / "douyin-transcript" / "uv.lock",
    )
    parser.add_argument(
        "--cache-dir",
        required=True,
        type=Path,
        help="existing flat SHA-256 cache; no network access is used",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=root / "docs" / "ARTIFACT_MEMBER_INVENTORY.md",
    )
    parser.add_argument(
        "--output-jsonl",
        type=Path,
        default=root / "docs" / "artifact-member-inventory.jsonl",
    )
    args = parser.parse_args(argv)
    try:
        markdown, jsonl_content = build_inventory(args.lockfile, args.cache_dir)
        _atomic_write(args.output_jsonl, jsonl_content)
        _atomic_write(args.output_md, markdown)
    except (InventoryError, OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        message = escape_terminal_controls(str(exc))
        print(f"Artifact member inventory failed: {message}", file=sys.stderr)
        return 1
    member_rows = sum(1 for line in jsonl_content.splitlines() if line)
    print(
        "Artifact member inventory written: "
        f"{member_rows} members; markdown={args.output_md}; jsonl={args.output_jsonl}"
    )
    print("Candidate labels are path/name heuristics, not licensing conclusions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
