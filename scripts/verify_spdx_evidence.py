#!/usr/bin/env python3
"""Verify SPDX evidence bytes against uv.lock and a local, SHA-256-keyed cache.

This command is deliberately offline and read-only. It never downloads artifacts or
extracts archive members to disk. Cache entries are named by their lowercase SHA-256
digest, without an extension.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import stat
import struct
import sys
import tarfile
import tempfile
import tomllib
import time
import zipfile
import zlib
from contextlib import contextmanager
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Iterator, Sequence
from urllib.parse import urlsplit

from spdx_terminal_safety import contains_terminal_controls, escape_terminal_controls

_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
_CHUNK_SIZE = 1024 * 1024
_MAX_ARTIFACT_SIZE_BYTES = 512 * 1024 * 1024
_MAX_LOCK_FILE_BYTES = 16 * 1024 * 1024
_MAX_EVIDENCE_FILE_BYTES = 16 * 1024 * 1024
_MAX_EVIDENCE_PACKAGES = 5_000
_MAX_EVIDENCE_MEMBERS = 5_000
_MAX_VERIFICATION_ARTIFACTS = 1_000
_MAX_TOTAL_ARTIFACT_SIZE_BYTES = 2 * 1024 * 1024 * 1024
_MAX_TOTAL_VERIFICATION_SECONDS = 300.0
_MAX_EVIDENCE_MEMBER_SIZE = 64 * 1024 * 1024
_MAX_ARCHIVE_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
_MAX_ARCHIVE_MEMBERS = 50_000
_MAX_ARCHIVE_PARSE_SECONDS = 30.0
_MAX_ZIP_CENTRAL_DIRECTORY_BYTES = 64 * 1024 * 1024
_MAX_ZIP64_EOCD_RECORD_BYTES = 1024 * 1024


class EvidenceVerificationError(ValueError):
    """Raised when the lock, evidence manifest, or cached bytes disagree."""


@dataclass
class MemberEvidence:
    path: str
    sha256: str
    role: str
    expected_size: int | None = None
    metadata_field: str | None = None
    metadata_value: str | None = None
    package_name: str | None = None
    package_version: str | None = None
    metadata_status: str | None = None


@dataclass
class ArtifactEvidence:
    sha256: str
    size: int
    artifact_type: str
    urls: set[str] = field(default_factory=set)
    members: dict[str, MemberEvidence] = field(default_factory=dict)


@dataclass(frozen=True)
class VerificationSummary:
    packages: int
    artifacts: int
    metadata_members: int
    license_members: int
    notice_members: int
    supplemental_members: int
    lock_sha256: str
    evidence_sha256: str


def _canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise EvidenceVerificationError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _require_size(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise EvidenceVerificationError(f"{label} must be a non-negative integer")
    return value


def _read_bounded_text(
    path: Path,
    max_bytes: int,
    label: str,
    deadline: float,
) -> str:
    if time.monotonic() >= deadline:
        raise EvidenceVerificationError(
            f"Verification exceeds {_MAX_TOTAL_VERIFICATION_SECONDS:g} second limit"
        )
    stream = _open_regular_file(path, label)
    with stream:
        if os.fstat(stream.fileno()).st_size > max_bytes:
            raise EvidenceVerificationError(
                f"{label} exceeds {max_bytes} byte size limit"
            )
        content = stream.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise EvidenceVerificationError(f"{label} exceeds {max_bytes} byte size limit")
    if time.monotonic() >= deadline:
        raise EvidenceVerificationError(
            f"Verification exceeds {_MAX_TOTAL_VERIFICATION_SECONDS:g} second limit"
        )
    return content.decode("utf-8")


def _read_bounded_bytes(path: Path, max_bytes: int, label: str) -> bytes:
    """Read a regular file with a hard byte cap before downstream parsing."""
    stream = _open_regular_file(path, label)
    with stream:
        if os.fstat(stream.fileno()).st_size > max_bytes:
            raise EvidenceVerificationError(
                f"{label} exceeds {max_bytes} byte size limit"
            )
        content = stream.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise EvidenceVerificationError(f"{label} exceeds {max_bytes} byte size limit")
    return content


def _read_bounded_lock_bytes(path: Path) -> bytes:
    """Read uv.lock using the shared project lockfile size limit."""
    return _read_bounded_bytes(path, _MAX_LOCK_FILE_BYTES, "uv.lock")


def _open_regular_file(path: Path, label: str) -> BinaryIO:
    """Open a regular file without blocking if a checked path becomes a FIFO."""
    try:
        path_info = path.lstat()
    except OSError:
        raise
    if (
        stat.S_ISLNK(path_info.st_mode)
        or not stat.S_ISREG(path_info.st_mode)
        or getattr(path_info, "st_file_attributes", 0) & 0x400
    ):
        raise EvidenceVerificationError(f"{label} must be a regular, non-symlink file")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags)
    try:
        opened_info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_info.st_mode)
            or getattr(opened_info, "st_file_attributes", 0) & 0x400
        ):
            raise EvidenceVerificationError(f"{label} must be a regular file")
        if (opened_info.st_dev, opened_info.st_ino) != (
            path_info.st_dev,
            path_info.st_ino,
        ):
            raise EvidenceVerificationError(
                f"{label} changed between validation and open"
            )
        return os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise


def _safe_member_path(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or contains_terminal_controls(value)
    ):
        raise EvidenceVerificationError(
            f"{label} must be a relative POSIX archive path"
        )
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise EvidenceVerificationError(
            f"{label} must be a normalized relative archive path"
        )
    return value


def _locked_artifact(
    packages_by_key: dict[tuple[str, str], dict[str, Any]],
    package_name: str,
    package_version: str,
    artifact_type: Any,
    artifact_url: Any,
    artifact_sha256: Any,
    artifact_size: Any,
) -> tuple[str, int, str]:
    key = (_canonical_name(package_name), package_version)
    package = packages_by_key.get(key)
    if package is None:
        raise EvidenceVerificationError(
            f"Evidence package is not uniquely present in uv.lock: {package_name} {package_version}"
        )
    if artifact_type == "sdist":
        records = [package["sdist"]] if package.get("sdist") else []
    elif artifact_type == "wheel":
        records = package.get("wheels", [])
    else:
        raise EvidenceVerificationError(
            f"Invalid artifact type for {package_name} {package_version}"
        )

    digest = _require_digest(artifact_sha256, f"{package_name} artifact_sha256")
    size = _require_size(artifact_size, f"{package_name} artifact_size")
    if not isinstance(artifact_url, str) or not artifact_url:
        raise EvidenceVerificationError(
            f"Missing artifact URL for {package_name} {package_version}"
        )
    url_path = urlsplit(artifact_url).path.lower()
    if artifact_type == "wheel" and not url_path.endswith(".whl"):
        raise EvidenceVerificationError(
            "Only locked .whl artifacts are supported for wheels"
        )
    if artifact_type == "sdist" and not url_path.endswith(".tar.gz"):
        raise EvidenceVerificationError(
            "Only locked .tar.gz artifacts are supported for sdists"
        )

    match = any(
        record.get("url") == artifact_url
        and record.get("hash") == f"sha256:{digest}"
        and record.get("size") == size
        for record in records
    )
    if not match:
        raise EvidenceVerificationError(
            f"Artifact reference is not pinned by uv.lock: {package_name} {package_version}"
        )
    return digest, size, artifact_type


def _add_artifact(
    artifacts: dict[str, ArtifactEvidence],
    packages_by_key: dict[tuple[str, str], dict[str, Any]],
    *,
    package_name: str,
    package_version: str,
    artifact_type: Any,
    artifact_url: Any,
    artifact_sha256: Any,
    artifact_size: Any,
) -> ArtifactEvidence:
    digest, size, normalized_type = _locked_artifact(
        packages_by_key,
        package_name,
        package_version,
        artifact_type,
        artifact_url,
        artifact_sha256,
        artifact_size,
    )
    existing = artifacts.get(digest)
    if existing is None:
        existing = ArtifactEvidence(digest, size, normalized_type)
        artifacts[digest] = existing
        if len(artifacts) > _MAX_VERIFICATION_ARTIFACTS:
            raise EvidenceVerificationError(
                f"Verification exceeds {_MAX_VERIFICATION_ARTIFACTS} artifact limit"
            )
        if (
            sum(item.size for item in artifacts.values())
            > _MAX_TOTAL_ARTIFACT_SIZE_BYTES
        ):
            raise EvidenceVerificationError(
                "Verification exceeds "
                f"{_MAX_TOTAL_ARTIFACT_SIZE_BYTES} byte total artifact size limit"
            )
    elif existing.size != size or existing.artifact_type != normalized_type:
        raise EvidenceVerificationError(
            f"Conflicting lock records use artifact digest {digest}"
        )
    existing.urls.add(artifact_url)
    return existing


def _add_member(artifact: ArtifactEvidence, member: MemberEvidence) -> None:
    path = _safe_member_path(member.path, f"{member.role} path")
    member.path = path
    member.sha256 = _require_digest(member.sha256, f"{member.role} SHA-256")
    if member.expected_size is not None:
        member.expected_size = _require_size(
            member.expected_size, f"{member.role} size"
        )
    previous = artifact.members.get(path)
    if previous is not None:
        if previous != member:
            raise EvidenceVerificationError(
                f"Conflicting evidence for archive member {path} in {artifact.sha256}"
            )
        return
    artifact.members[path] = member


def _collect_artifacts(
    lock: dict[str, Any], evidence: dict[str, Any]
) -> dict[str, ArtifactEvidence]:
    if evidence.get("schema_version") != 1 or not isinstance(
        evidence.get("packages"), list
    ):
        raise EvidenceVerificationError("Unsupported license evidence document")
    if len(evidence["packages"]) > _MAX_EVIDENCE_PACKAGES:
        raise EvidenceVerificationError(
            f"Evidence exceeds {_MAX_EVIDENCE_PACKAGES} package row limit"
        )
    lock_packages = lock.get("package", [])
    if (
        not isinstance(lock_packages, list)
        or len(lock_packages) > _MAX_EVIDENCE_PACKAGES
    ):
        raise EvidenceVerificationError(
            f"uv.lock exceeds {_MAX_EVIDENCE_PACKAGES} package row limit"
        )

    packages_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for package in lock_packages:
        if package.get("source", {}).get("editable"):
            continue
        key = (_canonical_name(package["name"]), package["version"])
        if key in packages_by_key:
            raise EvidenceVerificationError(
                f"Duplicate package key in uv.lock: {key[0]} {key[1]}"
            )
        packages_by_key[key] = package

    rows_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    artifacts: dict[str, ArtifactEvidence] = {}
    evidence_member_count = 0

    def add_evidence_member(artifact: ArtifactEvidence, member: MemberEvidence) -> None:
        nonlocal evidence_member_count
        evidence_member_count += 1
        if evidence_member_count > _MAX_EVIDENCE_MEMBERS:
            raise EvidenceVerificationError(
                f"Evidence exceeds {_MAX_EVIDENCE_MEMBERS} archive member limit"
            )
        _add_member(artifact, member)

    for row in evidence["packages"]:
        if not isinstance(row, dict):
            raise EvidenceVerificationError(
                "Every license evidence package row must be an object"
            )
        name = row.get("name")
        version = row.get("version")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(version, str)
            or not version
        ):
            raise EvidenceVerificationError(
                "License evidence row is missing name or version"
            )
        key = (_canonical_name(name), version)
        if key in rows_by_key:
            raise EvidenceVerificationError(
                f"Duplicate license evidence row: {name} {version}"
            )
        rows_by_key[key] = row

        artifact = _add_artifact(
            artifacts,
            packages_by_key,
            package_name=name,
            package_version=version,
            artifact_type=row.get("artifact_type"),
            artifact_url=row.get("artifact_url"),
            artifact_sha256=row.get("artifact_sha256"),
            artifact_size=row.get("artifact_size"),
        )
        metadata_path = _safe_member_path(
            row.get("metadata_path"), f"{name} metadata_path"
        )
        metadata_hash = _require_digest(
            row.get("metadata_sha256"), f"{name} metadata_sha256"
        )
        status = row.get("status")
        if status not in {
            "valid_spdx_declaration",
            "no_license_field",
            "legacy_value_not_spdx_expression",
            "reviewed_legacy_value_mapping",
            "file_verified_declaration",
        }:
            raise EvidenceVerificationError(
                f"Invalid license evidence status for {name} {version}"
            )
        field_name = row.get("metadata_field")
        field_value = row.get("metadata_field_value")
        if field_name is not None and (
            not isinstance(field_name, str) or not field_name
        ):
            raise EvidenceVerificationError(
                f"Invalid metadata field for {name} {version}"
            )
        if field_value is not None and not isinstance(field_value, str):
            raise EvidenceVerificationError(
                f"Invalid metadata field value for {name} {version}"
            )
        if (field_name is None) != (field_value is None):
            raise EvidenceVerificationError(
                f"Incomplete metadata field evidence for {name} {version}"
            )
        declared_expression = row.get("declared_expression")
        mapped_expression = row.get("mapped_expression")
        license_fields = {"License", "License-Expression"}
        if status == "valid_spdx_declaration":
            if (
                field_name not in license_fields
                or not isinstance(field_value, str)
                or declared_expression != field_value
                or mapped_expression is not None
            ):
                raise EvidenceVerificationError(
                    f"Invalid SPDX declaration evidence for {name} {version}"
                )
        elif status == "no_license_field":
            if (
                field_name is not None
                or field_value is not None
                or declared_expression is not None
                or mapped_expression is not None
            ):
                raise EvidenceVerificationError(
                    f"Inconsistent missing-license evidence for {name} {version}"
                )
        elif status == "legacy_value_not_spdx_expression":
            if (
                field_name not in license_fields
                or not isinstance(field_value, str)
                or declared_expression is not None
                or mapped_expression is not None
            ):
                raise EvidenceVerificationError(
                    f"Inconsistent legacy-license evidence for {name} {version}"
                )
        elif status == "reviewed_legacy_value_mapping":
            if (
                field_name not in license_fields
                or not isinstance(field_value, str)
                or declared_expression is not None
                or not isinstance(mapped_expression, str)
            ):
                raise EvidenceVerificationError(
                    f"Invalid legacy-license mapping evidence for {name} {version}"
                )
        elif status == "file_verified_declaration" and (
            field_name not in {None, *license_fields} or mapped_expression is not None
        ):
            raise EvidenceVerificationError(
                f"Invalid metadata field for file-level license evidence for {name} {version}"
            )
        add_evidence_member(
            artifact,
            MemberEvidence(
                path=metadata_path,
                sha256=metadata_hash,
                role="metadata",
                metadata_field=field_name,
                metadata_value=field_value,
                package_name=name,
                package_version=version,
                metadata_status=status,
            ),
        )

        license_file = row.get("license_file")
        if status == "file_verified_declaration":
            if not isinstance(license_file, dict):
                raise EvidenceVerificationError(
                    f"Missing license-file evidence for {name} {version}"
                )
            license_artifact = _add_artifact(
                artifacts,
                packages_by_key,
                package_name=name,
                package_version=version,
                artifact_type=license_file.get("artifact_type"),
                artifact_url=license_file.get("artifact_url"),
                artifact_sha256=license_file.get("artifact_sha256"),
                artifact_size=license_file.get("artifact_size"),
            )
            add_evidence_member(
                license_artifact,
                MemberEvidence(
                    path=license_file.get("path"),
                    sha256=license_file.get("sha256"),
                    role="license",
                ),
            )
        elif license_file is not None:
            raise EvidenceVerificationError(
                f"Unexpected license-file evidence for {name} {version}"
            )

        notices = row.get("license_notices", [])
        if not isinstance(notices, list):
            raise EvidenceVerificationError(
                f"Invalid license notice list for {name} {version}"
            )
        if status != "file_verified_declaration" and notices:
            raise EvidenceVerificationError(
                f"Unexpected license notices for {name} {version}"
            )
        for notice in notices:
            if not isinstance(notice, dict):
                raise EvidenceVerificationError(
                    f"Invalid license notice evidence for {name} {version}"
                )
            notice_artifact = _add_artifact(
                artifacts,
                packages_by_key,
                package_name=name,
                package_version=version,
                artifact_type=notice.get("artifact_type"),
                artifact_url=notice.get("artifact_url"),
                artifact_sha256=notice.get("artifact_sha256"),
                artifact_size=notice.get("artifact_size"),
            )
            add_evidence_member(
                notice_artifact,
                MemberEvidence(
                    path=notice.get("path"),
                    sha256=notice.get("sha256"),
                    expected_size=notice.get("size"),
                    role="notice",
                ),
            )

        supplemental = row.get("artifact_members", [])
        if not isinstance(supplemental, list):
            raise EvidenceVerificationError(
                f"Invalid supplemental member list for {name} {version}"
            )
        for entry in supplemental:
            if not isinstance(entry, dict):
                raise EvidenceVerificationError(
                    f"Invalid supplemental member evidence for {name} {version}"
                )
            supplemental_artifact = _add_artifact(
                artifacts,
                packages_by_key,
                package_name=name,
                package_version=version,
                artifact_type=entry.get("artifact_type"),
                artifact_url=entry.get("artifact_url"),
                artifact_sha256=entry.get("artifact_sha256"),
                artifact_size=entry.get("artifact_size"),
            )
            add_evidence_member(
                supplemental_artifact,
                MemberEvidence(
                    path=entry.get("path"),
                    sha256=entry.get("sha256"),
                    expected_size=entry.get("size"),
                    role="supplemental",
                ),
            )

    if rows_by_key.keys() != packages_by_key.keys():
        missing = sorted(packages_by_key.keys() - rows_by_key.keys())
        extra = sorted(rows_by_key.keys() - packages_by_key.keys())
        raise EvidenceVerificationError(
            f"Evidence package set differs from uv.lock (missing={missing}, extra={extra})"
        )
    return artifacts


class _ArchiveReadBudget:
    """Aggregate resource limits for all evidence lookups in one archive."""

    def __init__(
        self,
        deadline: float | None = None,
        deadline_message: str | None = None,
    ) -> None:
        self.bytes_read = 0
        self.deadline = (
            time.monotonic() + _MAX_ARCHIVE_PARSE_SECONDS
            if deadline is None
            else deadline
        )
        self.deadline_message = deadline_message or (
            f"Archive parsing exceeds {_MAX_ARCHIVE_PARSE_SECONDS:g} second limit"
        )

    def check_deadline(self) -> None:
        if time.monotonic() >= self.deadline:
            raise EvidenceVerificationError(self.deadline_message)

    def charge_bytes(self, count: int) -> None:
        self.bytes_read += count
        if self.bytes_read > _MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise EvidenceVerificationError(
                "Archive exceeds "
                f"{_MAX_ARCHIVE_UNCOMPRESSED_BYTES} byte decompressed size limit"
            )


@contextmanager
def _verified_artifact_snapshot(
    path: Path,
    expected_sha256: str,
    expected_size: int,
    *,
    max_bytes: int = _MAX_ARTIFACT_SIZE_BYTES,
    deadline: float | None = None,
) -> Iterator[BinaryIO]:
    """Yield a bounded snapshot whose bytes match one locked artifact identity."""
    if (
        not _DIGEST_RE.fullmatch(expected_sha256)
        or not isinstance(expected_size, int)
        or isinstance(expected_size, bool)
        or expected_size < 0
        or expected_size > max_bytes
        or max_bytes <= 0
        or max_bytes > _MAX_ARTIFACT_SIZE_BYTES
    ):
        raise EvidenceVerificationError("Invalid locked artifact snapshot bounds")
    budget = _ArchiveReadBudget(deadline=deadline) if deadline is not None else None
    snapshot: BinaryIO | None = None
    try:
        try:
            with _open_regular_file(path, "Cache artifact") as source:
                opened = os.fstat(source.fileno())
                if opened.st_size != expected_size or opened.st_size > max_bytes:
                    raise EvidenceVerificationError(
                        "Artifact size differs from uv.lock for cached artifact"
                    )
                snapshot = tempfile.TemporaryFile(mode="w+b")
                digest = hashlib.sha256()
                copied = 0
                while True:
                    if budget is not None:
                        budget.check_deadline()
                    chunk = source.read(min(_CHUNK_SIZE, expected_size - copied + 1))
                    if budget is not None:
                        budget.check_deadline()
                    if not chunk:
                        break
                    copied += len(chunk)
                    if copied > expected_size or copied > max_bytes:
                        raise EvidenceVerificationError(
                            "Artifact size exceeds uv.lock for cached artifact"
                        )
                    digest.update(chunk)
                    snapshot.write(chunk)
                if copied != expected_size:
                    raise EvidenceVerificationError(
                        "Artifact size differs from uv.lock for cached artifact"
                    )
                if digest.hexdigest() != expected_sha256:
                    raise EvidenceVerificationError(
                        "Artifact SHA-256 differs from uv.lock for cached artifact"
                    )
        except OSError as exc:
            raise EvidenceVerificationError(
                f"Could not snapshot cache artifact: {type(exc).__name__}"
            ) from None
        snapshot.seek(0)
        yield snapshot
    finally:
        if snapshot is not None:
            snapshot.close()


def _zip_directory_info(
    stream: BinaryIO,
    budget: _ArchiveReadBudget,
) -> tuple[int, int, int]:
    """Read bounded ZIP directory metadata before ZipFile materializes entries."""
    stream.seek(0, 2)
    file_size = stream.tell()
    tail_size = min(file_size, 22 + 65_535)
    stream.seek(file_size - tail_size)
    tail = stream.read(tail_size)
    budget.check_deadline()

    eocd_index = tail.rfind(b"PK\x05\x06")
    eocd_fields: tuple[int, ...] | None = None
    while eocd_index >= 0:
        if eocd_index + 22 <= len(tail):
            comment_length = struct.unpack_from("<H", tail, eocd_index + 20)[0]
            if eocd_index + 22 + comment_length == len(tail):
                eocd_fields = struct.unpack_from("<4s4H2LH", tail, eocd_index)
                break
        eocd_index = tail.rfind(b"PK\x05\x06", 0, eocd_index)
    if eocd_fields is None:
        raise EvidenceVerificationError(
            "Wheel ZIP end-of-central-directory record is missing"
        )

    (
        _,
        disk_number,
        directory_disk,
        disk_entries,
        entry_count,
        directory_size,
        directory_offset,
        _,
    ) = eocd_fields
    eocd_offset = file_size - tail_size + eocd_index
    needs_zip64 = (
        disk_entries == 0xFFFF
        or entry_count == 0xFFFF
        or directory_size == 0xFFFFFFFF
        or directory_offset == 0xFFFFFFFF
    )
    locator_offset = eocd_offset - 20
    locator_fields: tuple[int, ...] | None = None
    if locator_offset >= 0:
        stream.seek(locator_offset)
        locator = stream.read(20)
        if len(locator) == 20 and locator[:4] == b"PK\x06\x07":
            locator_fields = struct.unpack("<4sLQL", locator)

    directory_record_offset = eocd_offset
    if needs_zip64 or locator_fields is not None:
        if locator_fields is None:
            raise EvidenceVerificationError("Wheel ZIP64 directory locator is missing")
        _, zip64_disk, _, disk_count = locator_fields
        if zip64_disk != 0 or disk_count != 1:
            raise EvidenceVerificationError(
                "Multi-disk wheel ZIP archives are unsupported"
            )
        record_end = locator_offset
        record_size = min(record_end, _MAX_ZIP64_EOCD_RECORD_BYTES)
        stream.seek(record_end - record_size)
        record = stream.read(record_size)
        budget.check_deadline()
        record_index = record.rfind(b"PK\x06\x06")
        zip64_fields: tuple[int, ...] | None = None
        while record_index >= 0:
            if record_index + 12 <= len(record):
                extension_size = struct.unpack_from("<Q", record, record_index + 4)[0]
                if (
                    extension_size >= 44
                    and record_index + 12 + extension_size == len(record)
                    and record_index + 56 <= len(record)
                ):
                    zip64_fields = struct.unpack_from(
                        "<4sQ2H2I4Q", record, record_index
                    )
                    break
            record_index = record.rfind(b"PK\x06\x06", 0, record_index)
        if zip64_fields is None:
            raise EvidenceVerificationError(
                "Wheel ZIP64 end record is invalid or oversized"
            )
        directory_record_offset = record_end - record_size + record_index
        (
            _,
            _,
            _,
            _,
            zip64_disk,
            zip64_directory_disk,
            disk_entries,
            entry_count,
            directory_size,
            directory_offset,
        ) = zip64_fields
        if zip64_disk != 0 or zip64_directory_disk != 0 or disk_entries != entry_count:
            raise EvidenceVerificationError(
                "Multi-disk wheel ZIP archives are unsupported"
            )
    elif disk_number != 0 or directory_disk != 0 or disk_entries != entry_count:
        raise EvidenceVerificationError("Multi-disk wheel ZIP archives are unsupported")

    if entry_count > _MAX_ARCHIVE_MEMBERS:
        raise EvidenceVerificationError(
            f"Archive exceeds {_MAX_ARCHIVE_MEMBERS} member limit"
        )
    if directory_size > _MAX_ZIP_CENTRAL_DIRECTORY_BYTES:
        raise EvidenceVerificationError(
            "Wheel ZIP central directory exceeds "
            f"{_MAX_ZIP_CENTRAL_DIRECTORY_BYTES} byte size limit"
        )
    if directory_size > file_size or directory_offset > file_size:
        raise EvidenceVerificationError(
            "Wheel ZIP central directory size is inconsistent"
        )
    directory_start = directory_record_offset - directory_size
    if directory_start < 0:
        raise EvidenceVerificationError(
            "Wheel ZIP central directory size is inconsistent"
        )
    stream.seek(directory_start)
    directory = stream.read(directory_size)
    budget.check_deadline()
    if len(directory) != directory_size:
        raise EvidenceVerificationError("Wheel ZIP central directory is truncated")
    actual_entries = 0
    cursor = 0
    while cursor < len(directory):
        budget.check_deadline()
        remaining = len(directory) - cursor
        if directory[cursor : cursor + 4] == b"PK\x05\x05":
            if remaining < 6:
                raise EvidenceVerificationError(
                    "Wheel ZIP central directory is malformed"
                )
            signature_size = struct.unpack_from("<H", directory, cursor + 4)[0]
            if cursor + 6 + signature_size != len(directory):
                raise EvidenceVerificationError(
                    "Wheel ZIP central directory is malformed"
                )
            cursor += 6 + signature_size
            continue
        if remaining < 46 or directory[cursor : cursor + 4] != b"PK\x01\x02":
            raise EvidenceVerificationError("Wheel ZIP central directory is malformed")
        fields = struct.unpack_from("<4s6H3I5H2I", directory, cursor)
        filename_size, extra_size, comment_size, disk_start = fields[10:14]
        record_size = 46 + filename_size + extra_size + comment_size
        if record_size > remaining or disk_start != 0:
            raise EvidenceVerificationError("Wheel ZIP central directory is malformed")
        cursor += record_size
        actual_entries += 1
        if actual_entries > _MAX_ARCHIVE_MEMBERS:
            raise EvidenceVerificationError(
                f"Archive exceeds {_MAX_ARCHIVE_MEMBERS} member limit"
            )
    if actual_entries != entry_count:
        raise EvidenceVerificationError(
            "Wheel ZIP central directory entry count differs from its end record"
        )
    return entry_count, directory_size, directory_start


class _BoundedDecompressedReader:
    """Limit expanded archive bytes while streaming a gzip tar."""

    def __init__(self, stream: BinaryIO, budget: _ArchiveReadBudget) -> None:
        self._stream = stream
        self._budget = budget
        self._position = 0

    def read(self, size: int = -1) -> bytes:
        self._budget.check_deadline()
        remaining = _MAX_ARCHIVE_UNCOMPRESSED_BYTES - self._budget.bytes_read
        if size < 0:
            size = _CHUNK_SIZE
        if size == 0:
            return b""
        # Read at most one byte beyond the budget so an exact-limit archive can
        # still report EOF without allowing an unbounded decompression request.
        chunk = self._stream.read(min(size, _CHUNK_SIZE, remaining + 1))
        self._position += len(chunk)
        self._budget.charge_bytes(len(chunk))
        self._budget.check_deadline()
        return chunk

    def tell(self) -> int:
        return self._position


def _read_archive_member(
    stream: BinaryIO,
    artifact_type: str,
    member_path: str,
    budget: _ArchiveReadBudget | None = None,
) -> tuple[str, int, bytes | None]:
    """Hash one exact regular member without writing it outside memory."""

    def consume(
        member_stream: BinaryIO, declared_size: int
    ) -> tuple[str, int, bytes | None]:
        member_budget = budget if artifact_type == "wheel" else None
        if declared_size < 0 or declared_size > _MAX_EVIDENCE_MEMBER_SIZE:
            raise EvidenceVerificationError(
                f"Evidence member exceeds {_MAX_EVIDENCE_MEMBER_SIZE} byte limit: {member_path}"
            )
        digest = hashlib.sha256()
        size = 0
        is_metadata = member_path.endswith(
            ("/METADATA", "/PKG-INFO")
        ) or member_path in {
            "METADATA",
            "PKG-INFO",
        }
        content = bytearray() if is_metadata else None
        while True:
            if member_budget is not None:
                member_budget.check_deadline()
            chunk = member_stream.read(
                min(_CHUNK_SIZE, _MAX_EVIDENCE_MEMBER_SIZE - size + 1)
            )
            if member_budget is not None:
                member_budget.check_deadline()
            if not chunk:
                break
            size += len(chunk)
            if size > _MAX_EVIDENCE_MEMBER_SIZE:
                raise EvidenceVerificationError(
                    f"Evidence member exceeds {_MAX_EVIDENCE_MEMBER_SIZE} byte limit: {member_path}"
                )
            if member_budget is not None:
                member_budget.charge_bytes(len(chunk))
            digest.update(chunk)
            if content is not None:
                content.extend(chunk)
        if size != declared_size:
            raise EvidenceVerificationError(
                f"Archive member size is inconsistent: {member_path}"
            )
        return digest.hexdigest(), size, bytes(content) if content is not None else None

    stream.seek(0)
    if zipfile.is_zipfile(stream):
        if artifact_type != "wheel":
            raise EvidenceVerificationError(
                "Source distribution artifact is not a .tar.gz archive"
            )
        if budget is None:
            budget = _ArchiveReadBudget()
        _zip_directory_info(stream, budget)
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            matches = []
            for info in archive.infolist():
                budget.check_deadline()
                if info.filename == member_path:
                    matches.append(info)
                    if len(matches) > 1:
                        raise EvidenceVerificationError(
                            f"Archive has duplicate evidence members: {member_path}"
                        )
            if not matches:
                raise EvidenceVerificationError(
                    f"Archive member is missing: {member_path}"
                )
            info = matches[0]
            mode = info.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            if (
                info.is_dir()
                or stat.S_ISLNK(mode)
                or file_type not in {0, stat.S_IFREG}
            ):
                raise EvidenceVerificationError(
                    f"Evidence member is not a regular file: {member_path}"
                )
            with archive.open(info, "r") as member_stream:
                return consume(member_stream, info.file_size)

    if artifact_type != "sdist":
        raise EvidenceVerificationError("Wheel artifact is not a ZIP archive")
    if budget is None:
        budget = _ArchiveReadBudget()
    stream.seek(0)
    try:
        with gzip.GzipFile(fileobj=stream, mode="rb") as decompressed:
            bounded_stream = _BoundedDecompressedReader(decompressed, budget)
            with tarfile.open(fileobj=bounded_stream, mode="r|") as archive:
                result: tuple[str, int, bytes | None] | None = None
                member_count = 0
                for info in archive:
                    budget.check_deadline()
                    member_count += 1
                    if member_count > _MAX_ARCHIVE_MEMBERS:
                        raise EvidenceVerificationError(
                            f"Archive exceeds {_MAX_ARCHIVE_MEMBERS} member limit"
                        )
                    if info.name != member_path:
                        continue
                    if result is not None:
                        raise EvidenceVerificationError(
                            f"Archive has duplicate evidence members: {member_path}"
                        )
                    if not info.isfile():
                        raise EvidenceVerificationError(
                            f"Evidence member is not a regular file: {member_path}"
                        )
                    member_stream = archive.extractfile(info)
                    if member_stream is None:
                        raise EvidenceVerificationError(
                            f"Could not read archive member: {member_path}"
                        )
                    with member_stream:
                        result = consume(member_stream, info.size)
                budget.check_deadline()
    except (tarfile.TarError, OSError, EOFError, zlib.error) as exc:
        raise EvidenceVerificationError(
            "Could not read bounded gzip tar evidence archive"
        ) from exc
    if result is None:
        raise EvidenceVerificationError(f"Archive member is missing: {member_path}")
    return result


def _read_tar_members(
    stream: BinaryIO,
    members: dict[str, MemberEvidence],
    budget: _ArchiveReadBudget,
) -> dict[str, tuple[str, int, bytes | None]]:
    """Read all requested sdist members in one bounded streaming pass."""
    if not members:
        return {}
    stream.seek(0)
    results: dict[str, tuple[str, int, bytes | None]] = {}
    try:
        with gzip.GzipFile(fileobj=stream, mode="rb") as decompressed:
            bounded_stream = _BoundedDecompressedReader(decompressed, budget)
            with tarfile.open(fileobj=bounded_stream, mode="r|") as archive:
                member_count = 0
                for info in archive:
                    budget.check_deadline()
                    member_count += 1
                    if member_count > _MAX_ARCHIVE_MEMBERS:
                        raise EvidenceVerificationError(
                            f"Archive exceeds {_MAX_ARCHIVE_MEMBERS} member limit"
                        )
                    member = members.get(info.name)
                    if member is None:
                        continue
                    if info.name in results:
                        raise EvidenceVerificationError(
                            f"Archive has duplicate evidence members: {info.name}"
                        )
                    if not info.isfile():
                        raise EvidenceVerificationError(
                            f"Evidence member is not a regular file: {info.name}"
                        )
                    if info.size < 0 or info.size > _MAX_EVIDENCE_MEMBER_SIZE:
                        raise EvidenceVerificationError(
                            f"Evidence member exceeds {_MAX_EVIDENCE_MEMBER_SIZE} byte limit: {info.name}"
                        )
                    member_stream = archive.extractfile(info)
                    if member_stream is None:
                        raise EvidenceVerificationError(
                            f"Could not read archive member: {info.name}"
                        )
                    digest = hashlib.sha256()
                    content = bytearray() if member.role == "metadata" else None
                    size = 0
                    with member_stream:
                        while True:
                            budget.check_deadline()
                            chunk = member_stream.read(
                                min(
                                    _CHUNK_SIZE,
                                    _MAX_EVIDENCE_MEMBER_SIZE - size + 1,
                                )
                            )
                            if not chunk:
                                break
                            size += len(chunk)
                            if size > _MAX_EVIDENCE_MEMBER_SIZE:
                                raise EvidenceVerificationError(
                                    f"Evidence member exceeds {_MAX_EVIDENCE_MEMBER_SIZE} byte limit: {info.name}"
                                )
                            digest.update(chunk)
                            if content is not None:
                                content.extend(chunk)
                    if size != info.size:
                        raise EvidenceVerificationError(
                            f"Archive member size is inconsistent: {info.name}"
                        )
                    results[info.name] = (
                        digest.hexdigest(),
                        size,
                        bytes(content) if content is not None else None,
                    )
    except (tarfile.TarError, OSError, EOFError, zlib.error) as exc:
        raise EvidenceVerificationError(
            "Could not read bounded gzip tar evidence archive"
        ) from exc
    missing = set(members) - set(results)
    if missing:
        raise EvidenceVerificationError(
            f"Archive member is missing: {sorted(missing)[0]}"
        )
    return results


def _check_metadata_member(member: MemberEvidence, content: bytes | None) -> None:
    if content is None:
        raise EvidenceVerificationError(
            f"Metadata member was not read as metadata: {member.path}"
        )
    try:
        message = BytesParser(policy=policy.compat32).parsebytes(content)
    except (ValueError, UnicodeError) as exc:
        raise EvidenceVerificationError(
            f"Could not parse package metadata: {member.path}"
        ) from exc
    if _canonical_name(str(message.get("Name", ""))) != _canonical_name(
        member.package_name or ""
    ):
        raise EvidenceVerificationError(
            f"Metadata package name does not match evidence: {member.path}"
        )
    if str(message.get("Version", "")) != member.package_version:
        raise EvidenceVerificationError(
            f"Metadata package version does not match evidence: {member.path}"
        )

    if member.metadata_field is None:
        if member.metadata_status in {"no_license_field", "file_verified_declaration"}:
            if message.get_all("License") or message.get_all("License-Expression"):
                raise EvidenceVerificationError(
                    f"Metadata license field is present but unrecorded: {member.path}"
                )
        return
    values = message.get_all(member.metadata_field, [])
    if values != [member.metadata_value]:
        raise EvidenceVerificationError(
            f"Metadata license value differs from evidence: {member.path}"
        )


def verify_evidence(
    lock_path: Path,
    evidence_path: Path,
    cache_dir: Path,
    *,
    lock_bytes: bytes | None = None,
    evidence_bytes: bytes | None = None,
) -> VerificationSummary:
    """Verify every artifact and evidence member referenced by the manifest.

    Callers that will consume the parsed inputs can pass bounded, already-read
    bytes so verification and later processing use the same immutable snapshot.
    """

    run_deadline = time.monotonic() + _MAX_TOTAL_VERIFICATION_SECONDS
    if (lock_bytes is None) != (evidence_bytes is None):
        raise EvidenceVerificationError(
            "Lock and evidence bytes must be supplied together"
        )
    try:
        if lock_bytes is None or evidence_bytes is None:
            lock_text = _read_bounded_text(
                lock_path, _MAX_LOCK_FILE_BYTES, "uv.lock", run_deadline
            )
            evidence_text = _read_bounded_text(
                evidence_path,
                _MAX_EVIDENCE_FILE_BYTES,
                "License evidence document",
                run_deadline,
            )
            lock_bytes = lock_text.encode("utf-8")
            evidence_bytes = evidence_text.encode("utf-8")
        if len(lock_bytes) > _MAX_LOCK_FILE_BYTES:
            raise EvidenceVerificationError(
                f"uv.lock exceeds {_MAX_LOCK_FILE_BYTES} byte size limit"
            )
        if len(evidence_bytes) > _MAX_EVIDENCE_FILE_BYTES:
            raise EvidenceVerificationError(
                f"License evidence document exceeds {_MAX_EVIDENCE_FILE_BYTES} byte size limit"
            )
        lock = tomllib.loads(lock_bytes.decode("utf-8"))
        evidence = json.loads(evidence_bytes.decode("utf-8"))
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        tomllib.TOMLDecodeError,
        RecursionError,
    ) as exc:
        raise EvidenceVerificationError(
            f"Could not read lock/evidence input: {exc}"
        ) from exc
    if not isinstance(evidence, dict):
        raise EvidenceVerificationError(
            "License evidence document must be a JSON object"
        )

    if cache_dir.is_symlink() or not cache_dir.is_dir():
        raise EvidenceVerificationError(
            "Artifact cache must be an existing, non-symlink directory"
        )
    artifacts = _collect_artifacts(lock, evidence)
    if len(artifacts) > _MAX_VERIFICATION_ARTIFACTS:
        raise EvidenceVerificationError(
            f"Verification exceeds {_MAX_VERIFICATION_ARTIFACTS} artifact limit"
        )
    total_artifact_bytes = sum(artifact.size for artifact in artifacts.values())
    if total_artifact_bytes > _MAX_TOTAL_ARTIFACT_SIZE_BYTES:
        raise EvidenceVerificationError(
            "Verification exceeds "
            f"{_MAX_TOTAL_ARTIFACT_SIZE_BYTES} byte total artifact size limit"
        )
    metadata_count = license_count = notice_count = supplemental_count = 0

    for digest, artifact in sorted(artifacts.items()):
        if time.monotonic() >= run_deadline:
            raise EvidenceVerificationError(
                f"Verification exceeds {_MAX_TOTAL_VERIFICATION_SECONDS:g} second limit"
            )
        if artifact.size > _MAX_ARTIFACT_SIZE_BYTES:
            raise EvidenceVerificationError(
                f"Artifact exceeds {_MAX_ARTIFACT_SIZE_BYTES} byte size limit: {digest}"
            )
        cache_path = cache_dir / digest
        try:
            artifact_deadline = min(
                run_deadline, time.monotonic() + _MAX_ARCHIVE_PARSE_SECONDS
            )
            budget = _ArchiveReadBudget(artifact_deadline)
            with _verified_artifact_snapshot(
                cache_path,
                digest,
                artifact.size,
                deadline=artifact_deadline,
            ) as stream:
                tar_members = (
                    _read_tar_members(stream, artifact.members, budget)
                    if artifact.artifact_type == "sdist"
                    else {}
                )
                for member in artifact.members.values():
                    try:
                        if artifact.artifact_type == "sdist":
                            member_digest, member_size, content = tar_members[
                                member.path
                            ]
                        else:
                            member_digest, member_size, content = _read_archive_member(
                                stream, artifact.artifact_type, member.path, budget
                            )
                    except (
                        OSError,
                        tarfile.TarError,
                        zipfile.BadZipFile,
                        RuntimeError,
                    ) as exc:
                        raise EvidenceVerificationError(
                            f"Could not read {member.role} member {member.path} from {digest}: {exc}"
                        ) from exc
                    if member_digest != member.sha256:
                        raise EvidenceVerificationError(
                            f"{member.role} SHA-256 differs from evidence: {member.path}"
                        )
                    if (
                        member.expected_size is not None
                        and member_size != member.expected_size
                    ):
                        raise EvidenceVerificationError(
                            f"{member.role} size differs from evidence: {member.path}"
                        )
                    if member.role == "metadata":
                        _check_metadata_member(member, content)
                        metadata_count += 1
                    elif member.role == "license":
                        license_count += 1
                    elif member.role == "notice":
                        notice_count += 1
                    elif member.role == "supplemental":
                        supplemental_count += 1
        except OSError as exc:
            raise EvidenceVerificationError(
                f"Could not read cache artifact {digest}: {exc}"
            ) from exc
        except (
            tarfile.TarError,
            zipfile.BadZipFile,
            RuntimeError,
            EOFError,
            zlib.error,
        ) as exc:
            raise EvidenceVerificationError(
                f"Could not parse cache artifact {digest}: {exc}"
            ) from exc

    return VerificationSummary(
        packages=len(evidence["packages"]),
        artifacts=len(artifacts),
        metadata_members=metadata_count,
        license_members=license_count,
        notice_members=notice_count,
        supplemental_members=supplemental_count,
        lock_sha256=hashlib.sha256(lock_bytes).hexdigest(),
        evidence_sha256=hashlib.sha256(evidence_bytes).hexdigest(),
    )


def main(argv: Sequence[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lockfile",
        type=Path,
        default=root / "skills" / "douyin-transcript" / "uv.lock",
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=root / "docs" / "third-party-license-evidence.json",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        required=True,
        help="existing offline cache containing files named by lowercase SHA-256, without extensions",
    )
    args = parser.parse_args(argv)
    try:
        summary = verify_evidence(args.lockfile, args.evidence, args.cache_dir)
    except (EvidenceVerificationError, OSError) as exc:
        print(
            f"SPDX evidence verification failed: {escape_terminal_controls(str(exc))}",
            file=sys.stderr,
        )
        return 1
    print(
        "SPDX evidence bytes verified: "
        f"{summary.packages} packages, {summary.artifacts} artifacts, "
        f"{summary.metadata_members} metadata, {summary.license_members} license, "
        f"{summary.notice_members} notice, "
        f"{summary.supplemental_members} supplemental members"
    )
    print(
        "This verifies recorded bytes and metadata only; it does not conclude licenses or notices."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
