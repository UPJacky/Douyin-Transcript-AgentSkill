#!/usr/bin/env python3
"""Inventory FFmpeg configure strings in lock-pinned PyAV wheels, offline.

This command reads existing SHA-256-keyed wheel files only. It does not install,
execute, download, or extract archive members to disk. A string observed in a
wheel is binary evidence, not proof of build provenance or license conclusions.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import re
import sys
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterator

from inventory_locked_artifact_members import (
    InventoryError,
    LockIdentity,
    _lock_identities,
    _zip_member_type,
)
from safe_output import write_atomic_text
from verify_spdx_evidence import (
    EvidenceVerificationError,
    _ArchiveReadBudget,
    _verified_artifact_snapshot,
    _zip_directory_info,
)
from spdx_terminal_safety import escape_terminal_controls

_EXPECTED_WHEEL_COUNT = 14
_MAX_WHEEL_BYTES = 128 * 1024 * 1024
_MAX_TOTAL_WHEEL_BYTES = 1024 * 1024 * 1024
_MAX_MEMBER_BYTES = 64 * 1024 * 1024
_MAX_RECORD_BYTES = 16 * 1024 * 1024
_MAX_ARCHIVE_MEMBERS = 10_000
_MAX_TOTAL_NATIVE_BYTES = 2 * 1024 * 1024 * 1024
_MAX_CONFIGURATION_BYTES = 8192
_MAX_SECONDS = 180.0
_NATIVE_SUFFIX_RE = re.compile(r"(?:\.dll|\.pyd|\.dylib|\.so(?:\.\d+)*)\Z", re.I)
_CONFIG_RE = re.compile(rb"--prefix=[^\x00]{1,8193}\x00")


def _read_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    if info.file_size < 0 or info.file_size > _MAX_MEMBER_BYTES:
        raise InventoryError(f"wheel member exceeds the size limit: {info.filename}")
    with archive.open(info, "r") as member:
        content = member.read(info.file_size + 1)
    if len(content) != info.file_size:
        raise InventoryError(
            f"wheel member size differs from its ZIP record: {info.filename}"
        )
    return content


def _configuration_strings(binary: bytes) -> list[str]:
    configurations: list[str] = []
    for match in _CONFIG_RE.finditer(binary):
        raw = match.group(0)[:-1]
        if len(raw) > _MAX_CONFIGURATION_BYTES:
            continue
        if b"--enable-libx264" not in raw and b"--enable-libx265" not in raw:
            continue
        try:
            configurations.append(raw.decode("ascii"))
        except UnicodeDecodeError:
            continue
    return list(dict.fromkeys(configurations))


def _record_hash_matches(row: list[str], member: bytes) -> bool:
    if len(row) != 3 or not row[1].startswith("sha256="):
        return False
    expected_hash = base64.urlsafe_b64encode(hashlib.sha256(member).digest())
    expected_hash = expected_hash.rstrip(b"=").decode("ascii")
    return row[1] == f"sha256={expected_hash}" and row[2] == str(len(member))


def _record_rows(content: bytes) -> dict[str, list[str]]:
    if len(content) > _MAX_RECORD_BYTES:
        raise InventoryError("wheel RECORD exceeds the size limit")
    try:
        text = content.decode("utf-8")
        rows = list(csv.reader(io.StringIO(text, newline="")))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise InventoryError("wheel RECORD is not valid UTF-8 CSV") from exc
    result: dict[str, list[str]] = {}
    for row in rows:
        if len(row) != 3 or not row[0] or row[0] in result:
            raise InventoryError("wheel RECORD has a malformed or duplicate row")
        result[row[0]] = row
    return result


def _safe_member_name(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        bool(name)
        and "\\" not in name
        and "\x00" not in name
        and not path.is_absolute()
        and ".." not in path.parts
    )


@contextmanager
def _verified_wheel_snapshot(
    cache_path: Path,
    identity: LockIdentity,
    deadline: float,
) -> Iterator[BinaryIO]:
    try:
        with _verified_artifact_snapshot(
            cache_path,
            identity.sha256,
            identity.size,
            max_bytes=_MAX_WHEEL_BYTES,
            deadline=deadline,
        ) as stream:
            yield stream
    except EvidenceVerificationError as exc:
        if "FileNotFoundError" in str(exc):
            raise InventoryError(
                f"cannot open locked wheel {identity.filename}: FileNotFoundError"
            ) from None
        raise InventoryError(
            f"locked wheel verification failed: {identity.filename}"
        ) from exc


def _inventory_wheel(
    identity: LockIdentity,
    cache_dir: Path,
    deadline: float,
) -> tuple[dict[str, object], int]:
    cache_path = cache_dir / identity.sha256
    with _verified_wheel_snapshot(cache_path, identity, deadline) as stream:
        stream.seek(0)
        try:
            _zip_directory_info(
                stream,
                _ArchiveReadBudget(
                    deadline=min(deadline, time.monotonic() + 30.0),
                    deadline_message="PyAV wheel central-directory check exceeded its time limit",
                ),
            )
            stream.seek(0)
            archive_context = zipfile.ZipFile(stream, "r")
        except (EvidenceVerificationError, zipfile.BadZipFile, OSError) as exc:
            raise InventoryError(
                f"locked wheel is not a valid bounded ZIP: {identity.filename}"
            ) from exc

        with archive_context as archive:
            infos = archive.infolist()
            if len(infos) > _MAX_ARCHIVE_MEMBERS:
                raise InventoryError(
                    f"wheel exceeds the member-count limit: {identity.filename}"
                )
            by_name: dict[str, zipfile.ZipInfo] = {}
            for info in infos:
                if not _safe_member_name(info.filename) or info.filename in by_name:
                    raise InventoryError(
                        f"wheel has an unsafe or duplicate member name: {identity.filename}"
                    )
                by_name[info.filename] = info

            record_names = [
                name
                for name in by_name
                if name.casefold().endswith(".dist-info/record")
            ]
            if len(record_names) != 1:
                raise InventoryError(
                    f"wheel must contain exactly one RECORD: {identity.filename}"
                )
            record_info = by_name[record_names[0]]
            if (
                _zip_member_type(record_info.external_attr >> 16, record_info.is_dir())
                != "file"
            ):
                raise InventoryError(
                    f"wheel RECORD is not a regular file: {identity.filename}"
                )
            record_bytes = _read_member(archive, record_info)
            record = _record_rows(record_bytes)

            configuration_members: list[dict[str, object]] = []
            native_bytes = 0
            for name, info in by_name.items():
                if info.is_dir() or not _NATIVE_SUFFIX_RE.search(name):
                    continue
                if _zip_member_type(info.external_attr >> 16, info.is_dir()) != "file":
                    raise InventoryError(
                        f"native wheel member is not a regular file: {name}"
                    )
                if time.monotonic() >= deadline:
                    raise InventoryError(
                        "PyAV build-configuration inventory exceeded its time limit"
                    )
                native_bytes += info.file_size
                if native_bytes > _MAX_TOTAL_NATIVE_BYTES:
                    raise InventoryError(
                        "PyAV native-member scan exceeded its aggregate byte limit"
                    )
                member = _read_member(archive, info)
                configurations = _configuration_strings(member)
                if not configurations:
                    continue
                row = record.get(name)
                if row is None or not _record_hash_matches(row, member):
                    raise InventoryError(
                        f"configuration-bearing native member is missing/mismatched in RECORD: {name}"
                    )
                member_digest = hashlib.sha256(member).hexdigest()
                for configuration in configurations:
                    configuration_members.append(
                        {
                            "member_path": name,
                            "member_size": len(member),
                            "member_sha256": member_digest,
                            "record_sha256_and_size_verified": True,
                            "configuration_string": configuration,
                        }
                    )

    return (
        {
            "filename": identity.filename,
            "url": identity.url,
            "sha256": identity.sha256,
            "size": identity.size,
            "native_configuration_member_count": len(configuration_members),
            "configuration_status": (
                "observed"
                if configuration_members
                else "not-observed-in-readable-native-strings"
            ),
            "configuration_members": configuration_members,
        },
        native_bytes,
    )


def build_inventory(lockfile: Path, cache_dir: Path) -> dict[str, object]:
    identities, lock_digest, _package_count = _lock_identities(lockfile)
    wheels = sorted(
        (
            identity
            for identity in identities
            if identity.package.casefold() == "av"
            and identity.version == "15.1.0"
            and identity.artifact_type == "wheel"
        ),
        key=lambda identity: identity.filename,
    )
    if len(wheels) != _EXPECTED_WHEEL_COUNT or len(
        {item.sha256 for item in wheels}
    ) != len(wheels):
        raise InventoryError(
            "uv.lock must contain 14 unique PyAV 15.1.0 wheel identities"
        )
    if not cache_dir.is_dir():
        raise InventoryError(f"SHA-256 cache directory does not exist: {cache_dir}")

    deadline = time.monotonic() + _MAX_SECONDS
    total_wheel_bytes = sum(item.size for item in wheels)
    if total_wheel_bytes > _MAX_TOTAL_WHEEL_BYTES:
        raise InventoryError("locked PyAV wheel set exceeds the aggregate size limit")
    wheel_rows: list[dict[str, object]] = []
    native_bytes = 0
    for identity in wheels:
        row, scanned_bytes = _inventory_wheel(identity, cache_dir, deadline)
        wheel_rows.append(row)
        native_bytes += scanned_bytes
        if native_bytes > _MAX_TOTAL_NATIVE_BYTES:
            raise InventoryError(
                "PyAV native-member scan exceeded its aggregate byte limit"
            )
        if time.monotonic() >= deadline:
            raise InventoryError(
                "PyAV build-configuration inventory exceeded its time limit"
            )
    return {
        "schema_version": 1,
        "package": "av",
        "version": "15.1.0",
        "lockfile": lockfile.name,
        "lockfile_sha256": lock_digest,
        "wheel_count": len(wheel_rows),
        "wheel_bytes": total_wheel_bytes,
        "native_member_bytes_scanned": native_bytes,
        "observed_configuration_member_count": sum(
            int(row["native_configuration_member_count"]) for row in wheel_rows
        ),
        "wheels": wheel_rows,
        "limitations": [
            "A configure string is a readable string embedded in the exact locked wheel; it does not prove build provenance or the full build inputs.",
            "A missing string means only that no matching readable string was found in scanned native members; it does not prove a feature/component is absent.",
            "This inventory does not map every binary component, verify source/notice completeness, determine license applicability, or approve redistribution.",
        ],
    }


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
        help="existing flat or superset SHA-256 cache; no network access is used",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "docs" / "pyav-ffmpeg-build-config-inventory.json",
    )
    args = parser.parse_args(argv)
    try:
        report = build_inventory(args.lockfile, args.cache_dir)
        serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        write_atomic_text(args.output, serialized)
    except (InventoryError, OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"ERROR {escape_terminal_controls(str(exc))}", file=sys.stderr)
        return 1
    print(
        "PASS "
        f"{report['wheel_count']} locked PyAV wheels; "
        f"{report['observed_configuration_member_count']} RECORD-verified native members; "
        f"output={escape_terminal_controls(str(args.output))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
