#!/usr/bin/env python3
"""Map direct PE imports in cached, locked Windows wheels.

The command is offline, never extracts archive members, verifies each wheel
against uv.lock from a same-handle temporary snapshot, and checks PE members
against wheel RECORD entries. Unhashed RECORD rows are reported explicitly.
The output is an observed import map, not a complete native BOM,
build-provenance record, linkage map, or license opinion.
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
import struct
import sys
import tempfile
import time
import tomllib
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterator
from urllib.parse import urlsplit

from verify_spdx_evidence import (
    EvidenceVerificationError,
    _ArchiveReadBudget,
    _read_bounded_lock_bytes,
    _zip_directory_info,
)
from spdx_terminal_safety import escape_terminal_controls
from safe_output import write_atomic_text

_CHUNK_SIZE = 1024 * 1024
_MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
_MAX_MEMBER_BYTES = 256 * 1024 * 1024
_MAX_TOTAL_NATIVE_BYTES = 1024 * 1024 * 1024
_MAX_MEMBERS = 50_000
_MAX_RECORD_BYTES = 16 * 1024 * 1024
_MAX_RECORD_ROWS = 50_000
_MAX_TARGET_WHEELS = 64
_MAX_TOTAL_ARTIFACT_BYTES = 2 * 1024 * 1024 * 1024
_MAX_PE_MEMBERS_PER_WHEEL = 4096
_MAX_TOTAL_PE_MEMBERS = 10_000
_MAX_PE_SECTIONS = 96
_MAX_IMPORT_DESCRIPTORS = 4096
_MAX_DLL_NAME_BYTES = 512
_MAX_TOTAL_SECONDS = 300.0
_MAX_ARCHIVE_SECONDS = 60.0
_REPARSE_POINT = 0x400
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_PE_SUFFIXES = {".dll", ".exe", ".pyd"}
_WINDOWS_MACHINES = {
    "win32": {0x014C},
    "win_amd64": {0x8664},
    "win_arm64": {0xAA64, 0xA641},
}


class InventoryError(Exception):
    """Raised when a lock identity, cached artifact, archive, or PE is invalid."""


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


def _locked_windows_wheels(lock_path: Path) -> tuple[list[Wheel], str]:
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
        if not isinstance(package, dict):
            raise InventoryError("uv.lock contains a malformed package record")
        name = package.get("name")
        version = package.get("version")
        artifacts = package.get("wheels", [])
        if not isinstance(version, str) or not isinstance(artifacts, list):
            raise InventoryError(f"malformed wheel list for {name}")
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                raise InventoryError(f"malformed wheel record for {name} {version}")
            url = artifact.get("url")
            raw_digest = artifact.get("hash")
            size = artifact.get("size")
            if (
                not isinstance(url, str)
                or not isinstance(raw_digest, str)
                or not raw_digest.startswith("sha256:")
                or not isinstance(size, int)
                or isinstance(size, bool)
                or size < 0
            ):
                raise InventoryError(f"invalid wheel identity for {name} {version}")
            digest = raw_digest.removeprefix("sha256:")
            if not _SHA256_RE.fullmatch(digest):
                raise InventoryError(f"invalid wheel SHA-256 for {name} {version}")
            filename = PurePosixPath(urlsplit(url).path).name
            platform_tag = (
                filename[:-4].rsplit("-", 1)[-1] if filename.endswith(".whl") else ""
            )
            if platform_tag.startswith("win"):
                if platform_tag not in _WINDOWS_MACHINES:
                    raise InventoryError(
                        f"unsupported Windows wheel platform tag: {platform_tag}"
                    )
                wheels.append(Wheel(name, version, url, digest, size))
    if not wheels:
        raise InventoryError("uv.lock contains no target Windows wheels")
    if len({wheel.sha256 for wheel in wheels}) != len(wheels):
        raise InventoryError("uv.lock contains duplicate target wheel hashes")
    if len(wheels) > _MAX_TARGET_WHEELS:
        raise InventoryError("uv.lock contains too many target Windows wheels")
    if sum(wheel.size for wheel in wheels) > _MAX_TOTAL_ARTIFACT_BYTES:
        raise InventoryError(
            "locked Windows wheels exceed aggregate compressed-byte limit"
        )
    return sorted(wheels, key=lambda item: (item.package, item.filename)), lock_sha256


@contextmanager
def _verified_snapshot(path: Path, wheel: Wheel, deadline: float) -> Iterator[BinaryIO]:
    """Copy a lock-sized regular cache file into one hashed temporary snapshot."""
    try:
        before = path.lstat()
    except OSError as exc:
        raise InventoryError(f"cannot stat cache object {path.name}: {exc}") from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or getattr(before, "st_file_attributes", 0) & _REPARSE_POINT
    ):
        raise InventoryError(
            f"cache object is not a regular non-reparse file: {path.name}"
        )
    if before.st_size != wheel.size or before.st_size > _MAX_ARTIFACT_BYTES:
        raise InventoryError(
            f"locked size mismatch or artifact exceeds limit: {wheel.filename}"
        )

    digest = hashlib.sha256()
    copied = 0
    snapshot: BinaryIO | None = None
    try:
        snapshot = tempfile.TemporaryFile(mode="w+b")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as source:
            opened = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or getattr(opened, "st_file_attributes", 0) & _REPARSE_POINT
                or opened.st_size != before.st_size
                or opened.st_ino != before.st_ino
                or opened.st_dev != before.st_dev
            ):
                raise InventoryError(f"cache object changed while opening: {path.name}")
            for chunk in iter(lambda: source.read(_CHUNK_SIZE), b""):
                if time.monotonic() >= deadline:
                    raise InventoryError("cache snapshot exceeded its time limit")
                copied += len(chunk)
                if copied > wheel.size or copied > _MAX_ARTIFACT_BYTES:
                    raise InventoryError(
                        f"cache object grew while reading: {path.name}"
                    )
                digest.update(chunk)
                snapshot.write(chunk)
        if copied != wheel.size or digest.hexdigest() != wheel.sha256:
            raise InventoryError(f"cache bytes differ from uv.lock: {wheel.filename}")
        snapshot.seek(0)
        yield snapshot
    except OSError as exc:
        raise InventoryError(
            f"cannot snapshot cache object {path.name}: {exc}"
        ) from exc
    finally:
        if snapshot is not None:
            snapshot.close()


def _record_rows(archive: zipfile.ZipFile) -> dict[str, tuple[str, int, str]]:
    names = [name for name in archive.namelist() if name.endswith(".dist-info/RECORD")]
    if len(names) != 1:
        raise InventoryError("wheel must contain exactly one .dist-info/RECORD")
    info = archive.getinfo(names[0])
    if info.file_size > _MAX_RECORD_BYTES:
        raise InventoryError("wheel RECORD exceeds its size limit")
    result: dict[str, tuple[str, int, str]] = {}
    try:
        with archive.open(info) as raw:
            content = raw.read(_MAX_RECORD_BYTES + 1)
        if len(content) != info.file_size or len(content) > _MAX_RECORD_BYTES:
            raise InventoryError("wheel RECORD size differs from ZIP directory")
        text = content.decode("utf-8")
        _check_record_csv_bounds(text)
        for row in csv.reader(io.StringIO(text, newline="")):
            if len(result) >= _MAX_RECORD_ROWS:
                raise InventoryError("wheel RECORD exceeds row limit")
            if len(row) != 3:
                raise InventoryError("malformed wheel RECORD row")
            member_path, digest, raw_size = row
            normalized_path = member_path.replace("\\", "/")
            if normalized_path in result:
                raise InventoryError("duplicate path in wheel RECORD")
            if not raw_size:
                size = -1
            else:
                try:
                    size = int(raw_size)
                except ValueError as exc:
                    raise InventoryError("invalid wheel RECORD size") from exc
                if size < 0:
                    raise InventoryError("negative size in wheel RECORD")
            result[normalized_path] = (digest, size, member_path)
    except (OSError, UnicodeDecodeError, csv.Error, zipfile.BadZipFile) as exc:
        raise InventoryError(f"cannot read wheel RECORD: {exc}") from exc
    return result


def _check_record_csv_bounds(text: str) -> None:
    """Bound CSV columns and logical rows before csv.reader allocates row lists."""
    fields = 1
    rows = 0
    field_start = True
    record_open = False
    quoted = False
    index = 0
    while index < len(text):
        char = text[index]
        record_open = True
        if quoted:
            if char == '"':
                if index + 1 < len(text) and text[index + 1] == '"':
                    index += 2
                    continue
                quoted = False
            index += 1
            continue

        if char == '"' and field_start:
            quoted = True
            field_start = False
        elif char == ",":
            fields += 1
            if fields > 3:
                raise InventoryError("malformed wheel RECORD row")
            field_start = True
        elif char in "\r\n":
            rows += 1
            if rows > _MAX_RECORD_ROWS:
                raise InventoryError("wheel RECORD exceeds row limit")
            if char == "\r" and index + 1 < len(text) and text[index + 1] == "\n":
                index += 1
            fields = 1
            field_start = True
            record_open = False
        else:
            field_start = False
        index += 1

    if record_open:
        rows += 1
        if rows > _MAX_RECORD_ROWS:
            raise InventoryError("wheel RECORD exceeds row limit")


def _record_digest(member_sha256: str) -> str:
    digest = base64.urlsafe_b64encode(bytes.fromhex(member_sha256)).decode("ascii")
    return f"sha256={digest.rstrip('=')}"


def _read_exact(stream: BinaryIO, offset: int, size: int, file_size: int) -> bytes:
    if offset < 0 or size < 0 or offset + size > file_size:
        raise InventoryError("PE structure points outside its member")
    stream.seek(offset)
    data = stream.read(size)
    if len(data) != size:
        raise InventoryError("truncated PE structure")
    return data


def _u16(stream: BinaryIO, offset: int, file_size: int) -> int:
    return struct.unpack("<H", _read_exact(stream, offset, 2, file_size))[0]


def _u32(stream: BinaryIO, offset: int, file_size: int) -> int:
    return struct.unpack("<I", _read_exact(stream, offset, 4, file_size))[0]


@dataclass(frozen=True)
class _Section:
    virtual_address: int
    raw_size: int
    raw_offset: int


class _PEImage:
    def __init__(self, stream: BinaryIO, file_size: int) -> None:
        self.stream = stream
        self.file_size = file_size
        if file_size < 0x40 or _read_exact(stream, 0, 2, file_size) != b"MZ":
            raise InventoryError("PE candidate lacks a valid DOS signature")
        pe_offset = _u32(stream, 0x3C, file_size)
        if _read_exact(stream, pe_offset, 4, file_size) != b"PE\0\0":
            raise InventoryError("PE candidate lacks a valid NT signature")
        coff = pe_offset + 4
        machine, section_count = struct.unpack(
            "<HH", _read_exact(stream, coff, 4, file_size)
        )
        optional_size = _u16(stream, coff + 16, file_size)
        if not 1 <= section_count <= _MAX_PE_SECTIONS:
            raise InventoryError("PE section count is outside supported bounds")
        optional = coff + 20
        magic = _u16(stream, optional, file_size)
        if magic == 0x10B:
            self.pe_format = "PE32"
            directory_count_offset = 92
            directory_offset = 96
            image_base_offset = 28
            image_base_format = "<I"
        elif magic == 0x20B:
            self.pe_format = "PE32+"
            directory_count_offset = 108
            directory_offset = 112
            image_base_offset = 24
            image_base_format = "<Q"
        else:
            raise InventoryError(f"unsupported PE optional-header magic: 0x{magic:04x}")
        minimum_optional_size = directory_offset
        if optional_size < minimum_optional_size:
            raise InventoryError("PE optional header is truncated")
        _read_exact(stream, optional, optional_size, file_size)
        self.machine = machine
        self.image_base = struct.unpack(
            image_base_format,
            _read_exact(
                stream,
                optional + image_base_offset,
                struct.calcsize(image_base_format),
                file_size,
            ),
        )[0]
        self.size_of_headers = _u32(stream, optional + 60, file_size)
        directory_count = _u32(stream, optional + directory_count_offset, file_size)
        available_directories = (optional_size - directory_offset) // 8
        if directory_count > available_directories:
            raise InventoryError(
                "PE data-directory count exceeds optional-header bounds"
            )
        self.directories: list[tuple[int, int]] = []
        for index in range(directory_count):
            entry = _read_exact(
                stream, optional + directory_offset + index * 8, 8, file_size
            )
            self.directories.append(struct.unpack("<II", entry))

        section_table = optional + optional_size
        section_data = _read_exact(stream, section_table, section_count * 40, file_size)
        self.sections: list[_Section] = []
        for index in range(section_count):
            entry = section_data[index * 40 : (index + 1) * 40]
            _, virtual_address, size_of_raw_data, pointer_to_raw_data = (
                struct.unpack_from("<IIII", entry, 8)
            )
            if pointer_to_raw_data + size_of_raw_data > file_size:
                raise InventoryError("PE section raw range extends beyond its member")
            self.sections.append(
                _Section(virtual_address, size_of_raw_data, pointer_to_raw_data)
            )

    def rva_to_offset(self, rva: int, size: int) -> int:
        if rva < 0 or size < 0 or rva + size > 0x1_0000_0000:
            raise InventoryError("PE RVA range overflows its address space")
        offset, available = self._rva_file_span(rva)
        if size > available:
            raise InventoryError("PE RVA range extends beyond file-backed data")
        return offset

    def _rva_file_span(self, rva: int) -> tuple[int, int]:
        if rva < 0 or rva >= 0x1_0000_0000:
            raise InventoryError("PE RVA is outside its address space")
        if rva < self.size_of_headers:
            if rva >= self.file_size:
                raise InventoryError("PE header RVA points outside its member")
            return rva, min(self.size_of_headers - rva, self.file_size - rva)
        matches = [
            section
            for section in self.sections
            if section.virtual_address <= rva
            and rva - section.virtual_address < section.raw_size
        ]
        if len(matches) != 1:
            raise InventoryError(
                "PE RVA does not map uniquely to file-backed section data"
            )
        section = matches[0]
        delta = rva - section.virtual_address
        offset = section.raw_offset + delta
        available = min(section.raw_size - delta, self.file_size - offset)
        if available <= 0:
            raise InventoryError("PE RVA maps beyond its member")
        return offset, available

    def _directory(
        self, index: int, kind: str, descriptor_size: int, name_offset: int
    ) -> list[str]:
        if index >= len(self.directories):
            return []
        rva, size = self.directories[index]
        if rva == 0 and size == 0:
            return []
        if rva == 0 or size < descriptor_size or size > self.file_size:
            raise InventoryError(f"PE {kind} import directory has an invalid range")
        self.rva_to_offset(rva, size)
        names: list[str] = []
        descriptor_count = min(size // descriptor_size, _MAX_IMPORT_DESCRIPTORS)
        terminated = False
        for item in range(descriptor_count):
            offset = self.rva_to_offset(rva + item * descriptor_size, descriptor_size)
            descriptor = _read_exact(
                self.stream, offset, descriptor_size, self.file_size
            )
            if not any(descriptor):
                terminated = True
                break
            if kind == "delay":
                attributes, name_value = struct.unpack_from("<II", descriptor)
                if attributes & ~1:
                    raise InventoryError(
                        "PE delay-import descriptor has unsupported attributes"
                    )
                if not attributes:
                    if name_value < self.image_base:
                        raise InventoryError("PE delay-import VA precedes image base")
                    name_rva = name_value - self.image_base
                else:
                    name_rva = name_value
            else:
                name_rva = struct.unpack_from("<I", descriptor, name_offset)[0]
            if name_rva == 0:
                raise InventoryError(
                    f"PE {kind} import descriptor has an empty DLL name RVA"
                )
            names.append(self._read_dll_name(name_rva))
        if not terminated:
            raise InventoryError(
                f"PE {kind} import descriptors lack a bounded terminator"
            )
        return names

    def _read_dll_name(self, rva: int) -> str:
        offset, available = self._rva_file_span(rva)
        length = min(_MAX_DLL_NAME_BYTES + 1, available)
        data = _read_exact(self.stream, offset, length, self.file_size)
        terminator = data.find(b"\0")
        if terminator < 0:
            raise InventoryError(
                "PE imported DLL name exceeds its size or section limit"
            )
        raw = data[:terminator]
        if not raw:
            raise InventoryError("PE import contains an empty DLL name")
        if any(byte < 0x20 or byte > 0x7E for byte in raw):
            raise InventoryError("PE imported DLL name contains non-printable bytes")
        try:
            return raw.decode("ascii")
        except UnicodeDecodeError as exc:
            raise InventoryError("PE imported DLL name is not ASCII") from exc

    def imports(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for name in self._directory(1, "normal", 20, 12):
            rows.append({"kind": "normal", "dll": name})
        for name in self._directory(13, "delay", 32, 4):
            rows.append({"kind": "delay", "dll": name})
        return rows


def _safe_member_path(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        bool(name)
        and not name.startswith("/")
        and "\\" not in name
        and ".." not in path.parts
        and "\x00" not in name
        and all(ord(character) >= 0x20 for character in name)
    )


def _is_pe_candidate(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in _PE_SUFFIXES


def _platform_tag(filename: str) -> str:
    if not filename.endswith(".whl"):
        raise InventoryError("locked Windows wheel filename is malformed")
    platform_tag = filename[:-4].rsplit("-", 1)[-1]
    if platform_tag not in _WINDOWS_MACHINES:
        raise InventoryError(f"unsupported Windows wheel platform tag: {platform_tag}")
    return platform_tag


def _expected_machines(filename: str) -> set[int]:
    return _WINDOWS_MACHINES[_platform_tag(filename)]


def _pe_rows(
    wheel: Wheel,
    lock_sha256: str,
    cache_path: Path,
    deadline: float,
    native_budget: list[int] | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    expanded_native = native_budget if native_budget is not None else [0]
    platform_tag = _platform_tag(wheel.filename)
    expected_machines = _expected_machines(wheel.filename)
    try:
        with _verified_snapshot(cache_path, wheel, deadline) as snapshot:
            archive_deadline = min(deadline, time.monotonic() + _MAX_ARCHIVE_SECONDS)
            try:
                _zip_directory_info(
                    snapshot,
                    _ArchiveReadBudget(
                        deadline=archive_deadline,
                        deadline_message="wheel ZIP directory inspection exceeded its time limit",
                    ),
                )
            except EvidenceVerificationError as exc:
                raise InventoryError(f"wheel ZIP directory is invalid: {exc}") from exc
            with zipfile.ZipFile(snapshot) as archive:
                infos = archive.infolist()
                if len(infos) > _MAX_MEMBERS:
                    raise InventoryError(
                        f"wheel exceeds the member-count limit: {wheel.filename}"
                    )
                paths: set[str] = set()
                candidates: list[zipfile.ZipInfo] = []
                for info in infos:
                    if info.filename in paths:
                        raise InventoryError(
                            f"duplicate ZIP member path: {wheel.filename}:{info.filename}"
                        )
                    paths.add(info.filename)
                    if not _safe_member_path(info.filename):
                        raise InventoryError(
                            f"unsafe ZIP member path: {wheel.filename}:{info.filename}"
                        )
                    if info.file_size < 0 or info.file_size > _MAX_MEMBER_BYTES:
                        raise InventoryError(
                            f"oversized wheel member: {wheel.filename}:{info.filename}"
                        )
                    if info.is_dir() or not _is_pe_candidate(info.filename):
                        continue
                    mode = info.external_attr >> 16
                    if stat.S_ISLNK(mode) or (mode and not stat.S_ISREG(mode)):
                        raise InventoryError(
                            f"PE candidate is not a regular file: {wheel.filename}:{info.filename}"
                        )
                    if info.flag_bits & 1:
                        raise InventoryError(
                            f"encrypted PE candidate: {wheel.filename}:{info.filename}"
                        )
                    expanded_native[0] += info.file_size
                    if expanded_native[0] > _MAX_TOTAL_NATIVE_BYTES:
                        raise InventoryError(
                            "PE members exceed aggregate expanded-byte limit"
                        )
                    candidates.append(info)
                    if len(candidates) > _MAX_PE_MEMBERS_PER_WHEEL:
                        raise InventoryError("wheel contains too many PE members")

                record = _record_rows(archive)
                for info in candidates:
                    if time.monotonic() >= archive_deadline:
                        raise InventoryError(
                            f"PE member parsing exceeded time limit: {wheel.filename}"
                        )
                    digest = hashlib.sha256()
                    total = 0
                    try:
                        with archive.open(info) as member:
                            for chunk in iter(lambda: member.read(_CHUNK_SIZE), b""):
                                total += len(chunk)
                                if total > info.file_size:
                                    raise InventoryError(
                                        f"member exceeds declared size: {info.filename}"
                                    )
                                digest.update(chunk)
                            if total != info.file_size:
                                raise InventoryError(
                                    f"member size differs from ZIP directory: {info.filename}"
                                )
                            member_sha256 = digest.hexdigest()
                            record_row = record.get(info.filename)
                            record_digest = ""
                            record_verified = False
                            record_path: str | None = None
                            if record_row is None:
                                record_status = "missing_from_record"
                            else:
                                record_digest, record_size, record_path = record_row
                                record_verified = (
                                    record_digest == _record_digest(member_sha256)
                                    and record_size == info.file_size
                                )
                                if not record_verified and not (
                                    record_digest == "" and record_size == -1
                                ):
                                    raise InventoryError(
                                        f"PE member differs from wheel RECORD: "
                                        f"{wheel.filename}:{info.filename}"
                                    )
                                record_status = (
                                    "verified"
                                    if record_verified
                                    else "unhashed_in_record"
                                )
                            member.seek(0)
                            image = _PEImage(member, info.file_size)
                            machine_matches_platform = (
                                image.machine in expected_machines
                            )
                            try:
                                imports = image.imports()
                            except InventoryError as exc:
                                raise InventoryError(
                                    f"invalid PE imports in {wheel.filename}:{info.filename}: {exc}"
                                ) from exc
                    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                        raise InventoryError(
                            f"cannot read PE member {wheel.filename}:{info.filename}: {exc}"
                        ) from exc
                    rows.append(
                        {
                            "artifact_sha256": wheel.sha256,
                            "artifact_size": wheel.size,
                            "lock_sha256": lock_sha256,
                            "member_path": info.filename,
                            "member_sha256": member_sha256,
                            "member_size": info.file_size,
                            "package": wheel.package,
                            "pe_format": image.pe_format,
                            "pe_machine": f"0x{image.machine:04x}",
                            "wheel_platform": platform_tag,
                            "machine_matches_wheel_platform": machine_matches_platform,
                            "imports": imports,
                            "record_sha256": (
                                record_digest.removeprefix("sha256=")
                                if record_verified
                                else None
                            ),
                            "record_path": record_path,
                            "record_status": record_status,
                            "record_verified": record_verified,
                            "version": wheel.version,
                            "wheel_filename": wheel.filename,
                        }
                    )
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise InventoryError(f"cannot inspect wheel {wheel.filename}: {exc}") from exc
    if not rows:
        raise InventoryError(
            f"locked Windows wheel contains no PE members: {wheel.filename}"
        )
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
        raise InventoryError(f"cannot write PE import evidence {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True, help="path to uv.lock")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        required=True,
        help="flat SHA-256-keyed artifact cache",
    )
    parser.add_argument("--output", type=Path, required=True, help="JSONL destination")
    args = parser.parse_args(argv)

    try:
        wheels, lock_sha256 = _locked_windows_wheels(args.lock)
        start = time.monotonic()
        deadline = start + _MAX_TOTAL_SECONDS
        rows: list[dict[str, object]] = []
        missing: list[str] = []
        present: list[str] = []
        native_budget = [0]
        for wheel in wheels:
            cache_path = args.cache_dir / wheel.sha256
            if not cache_path.exists():
                missing.append(wheel.filename)
                continue
            present.append(wheel.filename)
            rows.extend(
                _pe_rows(
                    wheel,
                    lock_sha256,
                    cache_path,
                    deadline,
                    native_budget=native_budget,
                )
            )
            if len(rows) > _MAX_TOTAL_PE_MEMBERS:
                raise InventoryError("locked wheels contain too many PE members")
        if not present:
            raise InventoryError("none of the locked Windows target wheels are cached")
        if missing:
            raise InventoryError(
                f"cache is missing {len(missing)} locked Windows wheels: "
                + ", ".join(missing)
            )
        rows.sort(
            key=lambda row: (
                str(row["package"]),
                str(row["wheel_filename"]),
                str(row["member_path"]),
            )
        )
        _write_jsonl(args.output, rows)
    except (InventoryError, OSError) as exc:
        message = escape_terminal_controls(str(exc))
        print(f"locked PE import inventory: {message}", file=sys.stderr)
        return 2

    print(
        f"Verified {len(present)}/{len(wheels)} cached locked Windows wheels and "
        f"{len(rows)} PE members; lock SHA-256 {lock_sha256}; output {args.output}"
    )
    if missing:
        print("Missing locked wheels: " + ", ".join(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
