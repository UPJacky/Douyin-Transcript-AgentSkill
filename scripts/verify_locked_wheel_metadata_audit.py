#!/usr/bin/env python3
"""Verify locked wheel and sdist metadata evidence from a local cache.

This offline audit records packaging metadata only. It does not conclude license
applicability, component coverage, or redistribution permission.
"""

from __future__ import annotations

import argparse
import base64
import csv
import gzip
import hashlib
import io
import json
import os
import re
import stat
import sys
import tarfile
import time
import tomllib
import zipfile
import zlib
from email import policy
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Sequence
from urllib.parse import urlsplit

from verify_spdx_evidence import (
    _ArchiveReadBudget,
    _BoundedDecompressedReader,
    EvidenceVerificationError,
    _canonical_name,
    _open_regular_file,
    _safe_member_path,
    _verified_artifact_snapshot,
    _zip_directory_info,
)
from spdx_terminal_safety import escape_terminal_controls
from safe_output import write_atomic_text

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_RECORD_HASH_RE = re.compile(r"sha256=([A-Za-z0-9_-]+)\Z")
_MAX_LOCK_BYTES = 16 * 1024 * 1024
_MAX_EVIDENCE_BYTES = 16 * 1024 * 1024
_MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
_MAX_TOTAL_ARTIFACT_BYTES = 2 * 1024 * 1024 * 1024
_MAX_MEMBER_BYTES = 64 * 1024 * 1024
_MAX_ARCHIVE_MEMBERS = 50_000
_MAX_ARCHIVE_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
_MAX_ARCHIVE_SECONDS = 30.0
_MAX_SECONDS = 300.0


def _read_bounded(path: Path, limit: int, label: str) -> bytes:
    with _open_regular_file(path, label) as stream:
        if os.fstat(stream.fileno()).st_size > limit:
            raise EvidenceVerificationError(f"{label} exceeds {limit} bytes")
        result = stream.read(limit + 1)
    if len(result) > limit:
        raise EvidenceVerificationError(f"{label} exceeds {limit} bytes")
    return result


def _member_bytes(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    if info.file_size < 0 or info.file_size > _MAX_MEMBER_BYTES:
        raise EvidenceVerificationError(
            f"Archive member exceeds {_MAX_MEMBER_BYTES} bytes: {info.filename}"
        )
    mode = info.external_attr >> 16
    kind = stat.S_IFMT(mode)
    if info.is_dir() or stat.S_ISLNK(mode) or kind not in {0, stat.S_IFREG}:
        raise EvidenceVerificationError(
            f"Archive evidence member is not a regular file: {info.filename}"
        )
    with archive.open(info, "r") as member:
        data = member.read(_MAX_MEMBER_BYTES + 1)
    if len(data) != info.file_size or len(data) > _MAX_MEMBER_BYTES:
        raise EvidenceVerificationError(
            f"Archive member size is inconsistent: {info.filename}"
        )
    return data


def _parse_package_metadata(
    content: bytes,
    *,
    package_name: str,
    package_version: str,
    source: str,
) -> Any:
    try:
        message = BytesParser(policy=policy.compat32).parsebytes(content)
    except (ValueError, UnicodeError) as exc:
        raise EvidenceVerificationError(f"Could not parse {source} metadata") from exc
    if _canonical_name(str(message.get("Name", ""))) != _canonical_name(package_name):
        raise EvidenceVerificationError(
            f"{source} metadata Name does not match lock: {package_name}"
        )
    if str(message.get("Version", "")) != package_version:
        raise EvidenceVerificationError(
            f"{source} metadata Version does not match lock: {package_name}"
        )
    return message


def _metadata_evidence(
    *,
    package_name: str,
    package_version: str,
    artifact_url: str,
    artifact_sha256: str,
    artifact_size: int,
    stream: BinaryIO,
    deadline: float,
) -> dict[str, Any]:
    stream.seek(0)
    _zip_directory_info(
        stream,
        _ArchiveReadBudget(
            deadline=deadline,
            deadline_message="Wheel metadata audit exceeded time limit",
        ),
    )
    stream.seek(0)
    with zipfile.ZipFile(stream) as archive:
        infos = archive.infolist()
        if len(infos) > _MAX_ARCHIVE_MEMBERS:
            raise EvidenceVerificationError(
                f"Wheel exceeds {_MAX_ARCHIVE_MEMBERS} member limit"
            )
        expanded_size = 0
        for info in infos:
            expanded_size += info.file_size
            if expanded_size > _MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise EvidenceVerificationError(
                    "Wheel exceeds declared uncompressed-byte limit"
                )
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise EvidenceVerificationError("Wheel contains duplicate member paths")
        metadata_infos = [
            info for info in infos if info.filename.endswith(".dist-info/METADATA")
        ]
        record_infos = [
            info for info in infos if info.filename.endswith(".dist-info/RECORD")
        ]
        if len(metadata_infos) != 1 or len(record_infos) != 1:
            raise EvidenceVerificationError(
                f"Expected exactly one METADATA and RECORD in {Path(urlsplit(artifact_url).path).name}"
            )
        metadata_info = metadata_infos[0]
        record_info = record_infos[0]
        _safe_member_path(metadata_info.filename, "wheel METADATA path")
        _safe_member_path(record_info.filename, "wheel RECORD path")
        metadata_bytes = _member_bytes(archive, metadata_info)
        record_bytes = _member_bytes(archive, record_info)

    try:
        message = _parse_package_metadata(
            metadata_bytes,
            package_name=package_name,
            package_version=package_version,
            source="Wheel METADATA",
        )
        record_text = record_bytes.decode("utf-8")
        record_rows: list[list[str]] = []
        for row in csv.reader(io.StringIO(record_text, newline="")):
            if len(record_rows) >= _MAX_ARCHIVE_MEMBERS:
                raise EvidenceVerificationError(
                    f"Wheel RECORD exceeds {_MAX_ARCHIVE_MEMBERS} row limit"
                )
            record_rows.append(row)
    except EvidenceVerificationError:
        raise
    except (ValueError, UnicodeError, csv.Error) as exc:
        raise EvidenceVerificationError(
            "Could not parse wheel metadata or RECORD"
        ) from exc
    if time.monotonic() >= deadline:
        raise EvidenceVerificationError("Wheel metadata audit exceeded time limit")
    windows_wheel = (
        Path(urlsplit(artifact_url).path).name[:-4].rsplit("-", 1)[-1].startswith("win")
    )
    matching_rows = [
        row
        for row in record_rows
        if row
        and (
            row[0].replace("\\", "/") == metadata_info.filename
            if windows_wheel
            else row[0] == metadata_info.filename
        )
    ]
    if len(matching_rows) != 1 or len(matching_rows[0]) != 3:
        raise EvidenceVerificationError(
            f"Wheel RECORD must have one complete row for {metadata_info.filename}"
        )
    record_hash_match = _RECORD_HASH_RE.fullmatch(matching_rows[0][1])
    if record_hash_match is None:
        raise EvidenceVerificationError(
            "Wheel RECORD metadata hash is missing or invalid"
        )
    encoded_hash = record_hash_match.group(1)
    expected_metadata_hash = base64.urlsafe_b64decode(
        encoded_hash + "=" * ((4 - len(encoded_hash) % 4) % 4)
    ).hex()
    metadata_sha256 = hashlib.sha256(metadata_bytes).hexdigest()
    if expected_metadata_hash != metadata_sha256 or matching_rows[0][2] != str(
        len(metadata_bytes)
    ):
        raise EvidenceVerificationError(
            f"Wheel RECORD does not match {metadata_info.filename}"
        )
    if not _SHA256_RE.fullmatch(artifact_sha256) or artifact_size <= 0:
        raise EvidenceVerificationError("Invalid locked wheel identity")

    return {
        "package": package_name,
        "version": package_version,
        "artifact_type": "wheel",
        "artifact_filename": Path(urlsplit(artifact_url).path).name,
        "artifact_url": artifact_url,
        "artifact_sha256": artifact_sha256,
        "artifact_size": artifact_size,
        "metadata_path": metadata_info.filename,
        "metadata_sha256": metadata_sha256,
        "metadata_size": len(metadata_bytes),
        "metadata_name": str(message.get("Name", "")),
        "metadata_version": str(message.get("Version", "")),
        "license_fields": {
            "License": message.get_all("License", []),
            "License-Expression": message.get_all("License-Expression", []),
        },
        "record_path": record_info.filename,
        "record_sha256": hashlib.sha256(record_bytes).hexdigest(),
        "record_size": len(record_bytes),
        "record_metadata_path": matching_rows[0][0],
        "record_metadata_row_verified": True,
    }


def _sdist_metadata_evidence(
    *,
    package_name: str,
    package_version: str,
    artifact_url: str,
    artifact_sha256: str,
    artifact_size: int,
    stream: BinaryIO,
    deadline: float,
) -> dict[str, Any]:
    stream.seek(0)
    archive_deadline = min(deadline, time.monotonic() + _MAX_ARCHIVE_SECONDS)
    metadata_path: str | None = None
    metadata_bytes: bytes | None = None
    member_count = 0
    expanded_size = 0
    try:
        budget = _ArchiveReadBudget(
            deadline=archive_deadline,
            deadline_message="Source archive metadata scan exceeded its time limit",
        )
        with gzip.GzipFile(fileobj=stream, mode="rb") as decompressed:
            bounded_stream = _BoundedDecompressedReader(decompressed, budget)
            with tarfile.open(fileobj=bounded_stream, mode="r|") as archive:
                for info in archive:
                    budget.check_deadline()
                    member_count += 1
                    if member_count > _MAX_ARCHIVE_MEMBERS:
                        raise EvidenceVerificationError(
                            f"Source archive exceeds {_MAX_ARCHIVE_MEMBERS} member limit"
                        )
                    if info.size < 0:
                        raise EvidenceVerificationError(
                            f"Source archive has a negative member size: {info.name}"
                        )
                    expanded_size += info.size
                    if expanded_size > _MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                        raise EvidenceVerificationError(
                            "Source archive exceeds the expanded-size limit"
                        )
                    path = PurePosixPath(info.name)
                    if (
                        not info.isfile()
                        or path.name != "PKG-INFO"
                        or len(path.parts) != 2
                    ):
                        continue
                    _safe_member_path(info.name, "source PKG-INFO path")
                    if metadata_path is not None:
                        raise EvidenceVerificationError(
                            "Source archive has multiple root PKG-INFO members"
                        )
                    if info.size > _MAX_MEMBER_BYTES:
                        raise EvidenceVerificationError(
                            f"PKG-INFO exceeds {_MAX_MEMBER_BYTES} bytes"
                        )
                    member = archive.extractfile(info)
                    if member is None:
                        raise EvidenceVerificationError(
                            "Could not read source PKG-INFO"
                        )
                    with member:
                        metadata_bytes = member.read(_MAX_MEMBER_BYTES + 1)
                    if len(metadata_bytes) != info.size:
                        raise EvidenceVerificationError(
                            f"Source PKG-INFO size is inconsistent: {info.name}"
                        )
                    metadata_path = info.name
                budget.check_deadline()
    except EvidenceVerificationError:
        raise
    except (OSError, tarfile.TarError, EOFError, gzip.BadGzipFile, zlib.error) as exc:
        raise EvidenceVerificationError(
            "Could not read source archive metadata"
        ) from exc
    if metadata_path is None or metadata_bytes is None:
        raise EvidenceVerificationError("Source archive has no root PKG-INFO")
    if time.monotonic() >= deadline:
        raise EvidenceVerificationError("Wheel metadata audit exceeded time limit")
    message = _parse_package_metadata(
        metadata_bytes,
        package_name=package_name,
        package_version=package_version,
        source="Source PKG-INFO",
    )
    if not _SHA256_RE.fullmatch(artifact_sha256) or artifact_size <= 0:
        raise EvidenceVerificationError("Invalid locked source archive identity")
    return {
        "package": package_name,
        "version": package_version,
        "artifact_type": "sdist",
        "artifact_filename": Path(urlsplit(artifact_url).path).name,
        "artifact_url": artifact_url,
        "artifact_sha256": artifact_sha256,
        "artifact_size": artifact_size,
        "metadata_path": metadata_path,
        "metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
        "metadata_size": len(metadata_bytes),
        "metadata_name": str(message.get("Name", "")),
        "metadata_version": str(message.get("Version", "")),
        "license_fields": {
            "License": message.get_all("License", []),
            "License-Expression": message.get_all("License-Expression", []),
        },
        "record_path": None,
        "record_sha256": None,
        "record_size": None,
        "record_metadata_path": None,
        "record_metadata_row_verified": None,
    }


def collect_evidence(lock_bytes: bytes, cache_dir: Path) -> dict[str, Any]:
    if len(lock_bytes) > _MAX_LOCK_BYTES:
        raise EvidenceVerificationError(f"uv.lock exceeds {_MAX_LOCK_BYTES} bytes")
    try:
        lock = tomllib.loads(lock_bytes.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise EvidenceVerificationError("Could not parse uv.lock") from exc
    if cache_dir.is_symlink() or not cache_dir.is_dir():
        raise EvidenceVerificationError(
            "Artifact cache must be a non-symlink directory"
        )

    lock_packages: dict[tuple[str, str], dict[str, Any]] = {}
    for package in lock.get("package", []):
        if package.get("source", {}).get("editable"):
            continue
        key = (_canonical_name(package.get("name", "")), package.get("version", ""))
        if key in lock_packages:
            raise EvidenceVerificationError(f"Duplicate package in lock: {key}")
        lock_packages[key] = package

    deadline = time.monotonic() + _MAX_SECONDS
    entries: list[dict[str, Any]] = []
    total_artifact_bytes = 0
    packages_with_artifacts = [
        package
        for package in lock_packages.values()
        if package.get("wheels") or package.get("sdist")
    ]
    artifact_counts = {"wheel": 0, "sdist": 0}
    for package in sorted(
        packages_with_artifacts,
        key=lambda item: (
            _canonical_name(str(item.get("name", ""))),
            str(item.get("version", "")),
        ),
    ):
        name = package.get("name")
        version = package.get("version")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(version, str)
            or not version
        ):
            raise EvidenceVerificationError("Malformed package identity in uv.lock")
        wheels = package.get("wheels", [])
        if not isinstance(wheels, list):
            raise EvidenceVerificationError(f"Malformed wheel list for {name}")
        artifact_specs: list[tuple[str, dict[str, Any]]] = []
        source_artifact = package.get("sdist")
        if source_artifact is not None:
            if not isinstance(source_artifact, dict):
                raise EvidenceVerificationError(f"Malformed sdist record for {name}")
            artifact_specs.append(("sdist", source_artifact))
        if any(not isinstance(item, dict) for item in wheels):
            raise EvidenceVerificationError(f"Malformed wheel record for {name}")
        artifact_specs.extend(("wheel", artifact) for artifact in wheels)
        artifact_specs.sort(key=lambda item: (item[0], str(item[1].get("url", ""))))
        for artifact_type, artifact in artifact_specs:
            url = artifact.get("url")
            hash_value = artifact.get("hash")
            size = artifact.get("size")
            if (
                not isinstance(url, str)
                or not isinstance(hash_value, str)
                or not hash_value.startswith("sha256:")
                or not isinstance(size, int)
                or isinstance(size, bool)
            ):
                raise EvidenceVerificationError(f"Malformed locked wheel for {name}")
            digest = hash_value.removeprefix("sha256:")
            if (
                not _SHA256_RE.fullmatch(digest)
                or size <= 0
                or size > _MAX_ARTIFACT_BYTES
            ):
                raise EvidenceVerificationError(
                    f"Invalid locked {artifact_type} bounds for {name}"
                )
            suffix = ".whl" if artifact_type == "wheel" else ".tar.gz"
            if not urlsplit(url).path.lower().endswith(suffix):
                raise EvidenceVerificationError(
                    f"Locked artifact is not a {artifact_type}: {url}"
                )
            total_artifact_bytes += size
            if total_artifact_bytes > _MAX_TOTAL_ARTIFACT_BYTES:
                raise EvidenceVerificationError(
                    f"Audit exceeds {_MAX_TOTAL_ARTIFACT_BYTES} total artifact bytes"
                )
            if time.monotonic() >= deadline:
                raise EvidenceVerificationError(
                    "Wheel metadata audit exceeded time limit"
                )

            cache_path = cache_dir / digest
            with _verified_artifact_snapshot(
                cache_path,
                digest,
                size,
                max_bytes=_MAX_ARTIFACT_BYTES,
                deadline=deadline,
            ) as stream:
                evidence_arguments = {
                    "package_name": name,
                    "package_version": version,
                    "artifact_url": url,
                    "artifact_sha256": digest,
                    "artifact_size": size,
                    "stream": stream,
                    "deadline": deadline,
                }
                if artifact_type == "wheel":
                    row = _metadata_evidence(**evidence_arguments)
                else:
                    row = _sdist_metadata_evidence(**evidence_arguments)
            entries.append(row)
            artifact_counts[artifact_type] += 1

    return {
        "schema_version": 1,
        "uv_lock_sha256": hashlib.sha256(lock_bytes).hexdigest(),
        "scope": "Every non-editable wheel and source-distribution artifact in uv.lock.",
        "package_count": len(packages_with_artifacts),
        "artifact_count": len(entries),
        "wheel_count": artifact_counts["wheel"],
        "sdist_count": artifact_counts["sdist"],
        "artifacts": entries,
        "limitations": [
            "Records locked wheel/sdist identity, package metadata bytes and License fields; RECORD is checked for wheels only.",
            "Does not determine license applicability, bundled/native component licenses, source/build provenance, or redistribution permission.",
            "An absent License or License-Expression field is recorded as absent and is not interpreted as a license conclusion.",
        ],
    }


def _write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    serialized = json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    if len(serialized.encode("utf-8")) > _MAX_EVIDENCE_BYTES:
        raise EvidenceVerificationError(f"Evidence exceeds {_MAX_EVIDENCE_BYTES} bytes")
    write_atomic_text(path, serialized, create_parents=False)


def main(argv: Sequence[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument(
        "--evidence",
        type=Path,
        default=root / "docs" / "locked-wheel-metadata-audit.json",
    )
    parser.add_argument(
        "--write", action="store_true", help="write freshly verified evidence"
    )
    args = parser.parse_args(argv)
    try:
        lock_path = root / "skills" / "douyin-transcript" / "uv.lock"
        lock_bytes = _read_bounded(lock_path, _MAX_LOCK_BYTES, "uv.lock")
        evidence = collect_evidence(lock_bytes, args.cache_dir)
        if args.write:
            _write_evidence(args.evidence, evidence)
            print(
                "Wrote verified metadata evidence for "
                f"{evidence['artifact_count']} locked distribution artifacts"
            )
            return 0
        manifest_bytes = _read_bounded(
            args.evidence, _MAX_EVIDENCE_BYTES, "metadata evidence"
        )
        try:
            observed = json.loads(manifest_bytes.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise EvidenceVerificationError(
                "Metadata evidence is not valid UTF-8 JSON"
            ) from exc
        if observed != evidence:
            raise EvidenceVerificationError(
                "Metadata evidence differs from the locked wheels and cache"
            )
        print(
            "Verified "
            f"{evidence['artifact_count']} locked distribution artifacts "
            f"({evidence['wheel_count']} wheels, {evidence['sdist_count']} sdists); "
            "metadata hashes and wheel RECORD rows match."
        )
        return 0
    except (EvidenceVerificationError, OSError, zipfile.BadZipFile) as exc:
        message = escape_terminal_controls(str(exc))
        print(f"metadata audit failed: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
