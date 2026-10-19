#!/usr/bin/env python3
"""Classify direct PE import names against locked Windows wheel PE members.

This offline report classifies API-set and a small explicit Windows system-DLL
name catalog, then matches case-insensitive basenames against RECORD-verified
PE members with compatible machine types. A filename match is a candidate only;
it does not prove Windows loader selection, runtime loading, static linkage, or
a full native dependency graph. Unmatched names are deliberately not called
missing dependencies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tomllib
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import urlsplit

from spdx_terminal_safety import escape_terminal_controls
from safe_output import write_new_text

_MAX_INPUT_BYTES = 16 * 1024 * 1024
_MAX_LOCK_BYTES = 4 * 1024 * 1024
_MAX_ROWS = 10_000
_MAX_IMPORTS = 100_000
_MAX_OUTPUT_BYTES = 64 * 1024 * 1024
_MAX_CANDIDATE_COMPARISONS = 2_000_000
_MAX_TARGET_CANDIDATES = 50_000
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_MACHINE_RE = re.compile(r"0x[0-9a-f]{4}\Z")
_PLATFORMS = {"win32", "win_amd64", "win_arm64"}
_RECORD_STATUSES = {
    "verified",
    "missing_from_record",
    "unhashed_in_record",
}
_REPARSE_POINT = 0x400
_API_SET_PREFIXES = ("api-ms-win-", "api-ms-onecore-", "ext-ms-win-")

# Intentionally small exact-name catalog. These are recognizable Windows
# system DLL names observed in the locked PE imports; this is not a complete
# Windows DLL catalog and does not establish which file the loader selects.
_WINDOWS_SYSTEM_DLL_NAMES = frozenset(
    {
        "advapi32.dll",
        "avicap32.dll",
        "bcrypt.dll",
        "bcryptprimitives.dll",
        "combase.dll",
        "crypt32.dll",
        "dxgi.dll",
        "gdi32.dll",
        "imagehlp.dll",
        "iphlpapi.dll",
        "kernel32.dll",
        "msvcrt.dll",
        "netapi32.dll",
        "ntdll.dll",
        "ole32.dll",
        "oleaut32.dll",
        "pdh.dll",
        "powrprof.dll",
        "psapi.dll",
        "secur32.dll",
        "setupapi.dll",
        "shell32.dll",
        "shlwapi.dll",
        "user32.dll",
        "userenv.dll",
        "winmm.dll",
        "wintrust.dll",
        "ws2_32.dll",
        "wsock32.dll",
    }
)


class EdgeMapError(Exception):
    """Raised when import-map evidence is malformed or outside bounds."""


def _regular_bytes(path: Path, limit: int, description: str) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise EdgeMapError(f"cannot stat {description}: {exc}") from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or path.is_symlink()
        or getattr(before, "st_file_attributes", 0) & _REPARSE_POINT
        or before.st_size > limit
    ):
        raise EdgeMapError(f"{description} is not a bounded regular file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or getattr(opened, "st_file_attributes", 0) & _REPARSE_POINT
                or opened.st_size != before.st_size
                or opened.st_ino != before.st_ino
                or opened.st_dev != before.st_dev
            ):
                raise EdgeMapError(f"{description} changed while opening")
            data = stream.read(limit + 1)
    except OSError as exc:
        raise EdgeMapError(f"cannot read {description}: {exc}") from exc
    if len(data) > limit or len(data) != before.st_size:
        raise EdgeMapError(f"{description} changed size or exceeds its limit")
    return data


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EdgeMapError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise EdgeMapError(f"non-finite JSON value is not allowed: {value}")


def _locked_windows_wheels(lock_bytes: bytes) -> set[tuple[str, str, str, str, str]]:
    try:
        lock = tomllib.loads(lock_bytes.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise EdgeMapError(f"cannot parse lock file: {exc}") from exc
    packages = lock.get("package")
    if not isinstance(packages, list):
        raise EdgeMapError("lock file has no package list")

    wheels: set[tuple[str, str, str, str, str]] = set()
    for package in packages:
        if not isinstance(package, dict):
            raise EdgeMapError("lock file contains a malformed package")
        package_name = package.get("name")
        version = package.get("version")
        artifacts = package.get("wheels", [])
        if (
            not isinstance(package_name, str)
            or not isinstance(version, str)
            or not isinstance(artifacts, list)
        ):
            raise EdgeMapError("lock file contains a malformed package wheel list")
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                raise EdgeMapError(
                    f"lock file contains a malformed wheel for {package_name}"
                )
            url = artifact.get("url")
            digest = artifact.get("hash")
            if not isinstance(url, str) or not isinstance(digest, str):
                raise EdgeMapError(
                    f"lock file contains an invalid wheel for {package_name}"
                )
            filename = PurePosixPath(urlsplit(url).path).name
            if not filename.endswith(".whl"):
                continue
            platform = filename[:-4].rsplit("-", 1)[-1]
            if platform not in _PLATFORMS:
                continue
            if not digest.startswith("sha256:"):
                raise EdgeMapError(
                    f"lock file contains an invalid wheel hash for {package_name}"
                )
            artifact_sha256 = digest.removeprefix("sha256:")
            if not _SHA256_RE.fullmatch(artifact_sha256):
                raise EdgeMapError(
                    f"lock file contains an invalid wheel hash for {package_name}"
                )
            wheels.add((artifact_sha256, package_name, version, filename, platform))
    if not wheels:
        raise EdgeMapError("lock file contains no supported Windows wheels")
    return wheels


def _safe_member_path(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        bool(value)
        and not value.startswith("/")
        and "\\" not in value
        and ".." not in path.parts
        and "\0" not in value
        and all(ord(character) >= 0x20 for character in value)
    )


def _require_string(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise EdgeMapError(f"PE import inventory has invalid {key}")
    return value


def _load_inventory(
    inventory_path: Path, lock_path: Path
) -> tuple[list[dict[str, Any]], str, str]:
    lock_bytes = _regular_bytes(lock_path, _MAX_LOCK_BYTES, "lock file")
    lock_sha256 = hashlib.sha256(lock_bytes).hexdigest()
    locked_wheels = _locked_windows_wheels(lock_bytes)
    raw = _regular_bytes(inventory_path, _MAX_INPUT_BYTES, "PE import inventory")
    if raw and not raw.endswith(b"\n"):
        raise EdgeMapError("PE import inventory must end with a newline")

    rows: list[dict[str, Any]] = []
    node_keys: set[tuple[str, str]] = set()
    total_imports = 0
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line:
            raise EdgeMapError(
                f"PE import inventory contains a blank line at {line_number}"
            )
        try:
            value = json.loads(
                line.decode("utf-8", errors="strict"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EdgeMapError(
                f"invalid JSON on PE import inventory line {line_number}"
            ) from exc
        if not isinstance(value, dict):
            raise EdgeMapError(
                f"PE import inventory line {line_number} is not an object"
            )

        artifact_sha = _require_string(value, "artifact_sha256")
        member_sha = _require_string(value, "member_sha256")
        source_path = _require_string(value, "member_path")
        if not _SHA256_RE.fullmatch(artifact_sha) or not _SHA256_RE.fullmatch(
            member_sha
        ):
            raise EdgeMapError(
                f"invalid SHA-256 identity on inventory line {line_number}"
            )
        if not _safe_member_path(source_path):
            raise EdgeMapError(f"unsafe member path on inventory line {line_number}")
        if _require_string(value, "lock_sha256") != lock_sha256:
            raise EdgeMapError(
                "PE import inventory was generated from a different lock file"
            )
        platform = _require_string(value, "wheel_platform")
        machine = _require_string(value, "pe_machine")
        if platform not in _PLATFORMS or not _MACHINE_RE.fullmatch(machine):
            raise EdgeMapError(
                f"invalid platform/machine identity on inventory line {line_number}"
            )
        for key in ("package", "version", "wheel_filename"):
            _require_string(value, key)
        if (
            artifact_sha,
            value["package"],
            value["version"],
            value["wheel_filename"],
            platform,
        ) not in locked_wheels:
            raise EdgeMapError(
                f"PE member is not bound to a locked Windows wheel on line {line_number}"
            )
        record_status = _require_string(value, "record_status")
        if record_status not in _RECORD_STATUSES:
            raise EdgeMapError(f"invalid RECORD status on inventory line {line_number}")
        if not isinstance(value.get("record_verified"), bool) or not isinstance(
            value.get("machine_matches_wheel_platform"), bool
        ):
            raise EdgeMapError(
                f"invalid verification flags on inventory line {line_number}"
            )
        if value["record_verified"] != (record_status == "verified"):
            raise EdgeMapError(
                f"inconsistent RECORD status on inventory line {line_number}"
            )
        key = (artifact_sha, source_path)
        if key in node_keys:
            raise EdgeMapError(
                f"duplicate PE member identity on inventory line {line_number}"
            )
        node_keys.add(key)

        imports = value.get("imports")
        if not isinstance(imports, list):
            raise EdgeMapError(f"invalid import list on inventory line {line_number}")
        total_imports += len(imports)
        if total_imports > _MAX_IMPORTS:
            raise EdgeMapError("PE import inventory exceeds the edge-count limit")
        for import_record in imports:
            if (
                not isinstance(import_record, dict)
                or set(import_record) != {"dll", "kind"}
                or not isinstance(import_record["dll"], str)
                or not isinstance(import_record["kind"], str)
                or not import_record["dll"]
                or len(import_record["dll"]) > 4096
                or any(ord(character) < 0x20 for character in import_record["dll"])
                or import_record["kind"] not in {"normal", "delay"}
            ):
                raise EdgeMapError(
                    f"invalid import record on inventory line {line_number}"
                )
            if not PureWindowsPath(import_record["dll"]).name:
                raise EdgeMapError(
                    f"invalid DLL import name on inventory line {line_number}"
                )
        rows.append(value)
        if len(rows) > _MAX_ROWS:
            raise EdgeMapError("PE import inventory exceeds the member-count limit")

    if not rows:
        raise EdgeMapError("PE import inventory is empty")
    return rows, lock_sha256, hashlib.sha256(raw).hexdigest()


def _candidate_identity(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_sha256": row["artifact_sha256"],
        "machine_matches_wheel_platform": row["machine_matches_wheel_platform"],
        "member_path": row["member_path"],
        "member_sha256": row["member_sha256"],
        "pe_machine": row["pe_machine"],
        "package": row["package"],
        "record_status": row["record_status"],
        "record_verified": row["record_verified"],
        "version": row["version"],
        "wheel_filename": row["wheel_filename"],
        "wheel_platform": row["wheel_platform"],
    }


def _candidate_record(
    candidate: dict[str, Any], source: dict[str, Any], scope: str
) -> dict[str, Any]:
    same_package = candidate["package"].casefold() == source["package"].casefold()
    if not same_package:
        package_relation = "different_package"
    elif candidate["version"] == source["version"]:
        package_relation = "same_package_version"
    else:
        package_relation = "same_package_different_version"
    return {
        **_candidate_identity(candidate),
        "candidate_scope": scope,
        "lock_package_relation": package_relation,
    }


def _name_classification(import_basename: str) -> tuple[str, str]:
    folded = import_basename.casefold()
    if folded.startswith(_API_SET_PREFIXES):
        return "windows_api_set_import", "api_set_name_prefix"
    if folded in _WINDOWS_SYSTEM_DLL_NAMES:
        return "windows_system_dll_name", "explicit_system_dll_name_catalog"
    return "non_catalogued_name", "no_system_name_rule_matched"


def _map_edges(
    rows: list[dict[str, Any]],
    lock_sha256: str,
    inventory_sha256: str,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    by_artifact: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_basename: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        basename = PureWindowsPath(row["member_path"]).name.casefold()
        by_artifact[(row["artifact_sha256"], basename)].append(row)
        by_basename[basename].append(row)

    edges: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    candidate_comparisons = 0
    target_candidate_count = 0
    for row in rows:
        source = _candidate_identity(row)
        for import_index, imported in enumerate(row["imports"]):
            import_name = PureWindowsPath(imported["dll"]).name
            folded_name = import_name.casefold()
            named_candidates = by_basename.get(folded_name, [])

            source_eligible = bool(
                row["record_verified"] and row["machine_matches_wheel_platform"]
            )

            def compatible(candidate: dict[str, Any]) -> bool:
                return bool(
                    source_eligible
                    and candidate["record_verified"]
                    and candidate["machine_matches_wheel_platform"]
                    and candidate["pe_machine"].casefold()
                    == row["pe_machine"].casefold()
                )

            same_artifact: list[dict[str, Any]] = []
            cross_artifact: list[dict[str, Any]] = []
            for candidate in named_candidates:
                candidate_comparisons += 1
                if candidate_comparisons > _MAX_CANDIDATE_COMPARISONS:
                    raise EdgeMapError("candidate matching work exceeds its limit")
                if not compatible(candidate):
                    continue
                target_candidate_count += 1
                if target_candidate_count > _MAX_TARGET_CANDIDATES:
                    raise EdgeMapError("mapped target candidates exceed their limit")
                if candidate["artifact_sha256"] == row["artifact_sha256"]:
                    same_artifact.append(candidate)
                else:
                    cross_artifact.append(candidate)
            target_candidates = [
                _candidate_record(candidate, row, "same_artifact")
                for candidate in same_artifact
            ] + [
                _candidate_record(candidate, row, "cross_artifact")
                for candidate in cross_artifact
            ]
            target_candidates.sort(
                key=lambda item: (
                    item["candidate_scope"],
                    item["package"].casefold(),
                    item["version"],
                    item["wheel_filename"],
                    item["member_path"].casefold(),
                    item["artifact_sha256"],
                )
            )

            name_classification, name_basis = _name_classification(import_name)
            candidate_count = len(target_candidates)
            if candidate_count > 1:
                resolution = "ambiguous_inventory_filename_candidates"
                resolution_reason = "multiple_record_verified_same_machine_members"
            elif len(same_artifact) == 1:
                resolution = "same_artifact_filename_candidate"
                resolution_reason = "exact_basename_same_artifact_and_machine"
            elif len(cross_artifact) == 1:
                resolution = "cross_artifact_filename_candidate"
                resolution_reason = "exact_basename_other_artifact_same_machine"
            elif name_classification != "non_catalogued_name":
                resolution = name_classification
                resolution_reason = name_basis
            else:
                resolution = "unresolved_in_inventory"
                if not source_eligible:
                    resolution_reason = (
                        "source_record_or_wheel_architecture_not_verified"
                    )
                elif named_candidates:
                    resolution_reason = (
                        "matching_basename_candidates_failed_record_or_machine_gate"
                    )
                else:
                    resolution_reason = "no_matching_pe_member_in_inventory"

            counts[resolution] += 1
            if same_artifact:
                counts["edges_with_same_artifact_candidates"] += 1
            if cross_artifact:
                counts["edges_with_cross_artifact_candidates"] += 1
            edges.append(
                {
                    "candidate_counts": {
                        "cross_artifact": len(cross_artifact),
                        "same_artifact": len(same_artifact),
                    },
                    "candidate_resolution": (
                        "ambiguous_inventory_candidates"
                        if candidate_count > 1
                        else "same_artifact"
                        if len(same_artifact) == 1
                        else "cross_artifact"
                        if len(cross_artifact) == 1
                        else "none"
                    ),
                    "format_version": 1,
                    "import_index": import_index,
                    "import_kind": imported["kind"],
                    "import_name": imported["dll"],
                    "import_basename": import_name,
                    "inventory_sha256": inventory_sha256,
                    "lock_sha256": lock_sha256,
                    "name_classification": name_classification,
                    "name_classification_basis": name_basis,
                    "resolution": resolution,
                    "resolution_reason": resolution_reason,
                    "source": {
                        **source,
                    },
                    "target_candidates": target_candidates,
                }
            )
    return edges, counts


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    parts: list[bytes] = []
    total_bytes = 0
    for row in rows:
        payload = (
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        total_bytes += len(payload)
        if total_bytes > _MAX_OUTPUT_BYTES:
            raise EdgeMapError("edge-map output exceeds its byte limit")
        parts.append(payload)
    try:
        # Publish a completed sibling file with a no-clobber hard link.
        write_new_text(path, (part.decode("utf-8") for part in parts), mode=0o666)
    except FileExistsError as exc:
        raise EdgeMapError(
            "output path already exists; refusing to replace evidence"
        ) from exc
    except OSError as exc:
        raise EdgeMapError(f"cannot write edge map {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True, help="path to uv.lock")
    parser.add_argument("--inventory", type=Path, required=True, help="PE import JSONL")
    parser.add_argument("--output", type=Path, required=True, help="edge-map JSONL")
    args = parser.parse_args(argv)

    try:
        rows, lock_sha256, inventory_sha256 = _load_inventory(args.inventory, args.lock)
        edges, counts = _map_edges(rows, lock_sha256, inventory_sha256)
        _write_jsonl(args.output, edges)
    except (EdgeMapError, OSError) as exc:
        message = escape_terminal_controls(str(exc))
        print(f"locked PE import edge map: {message}", file=sys.stderr)
        return 2

    print(
        f"Mapped {len(rows)} PE members and {len(edges)} import occurrences; "
        f"Windows API-set names={counts['windows_api_set_import']}, "
        f"Windows system-DLL names={counts['windows_system_dll_name']}, "
        f"edges with same-artifact candidates={counts['edges_with_same_artifact_candidates']}, "
        f"edges with cross-artifact candidates={counts['edges_with_cross_artifact_candidates']}, "
        f"single-candidate resolutions: same={counts['same_artifact_filename_candidate']}, "
        f"cross={counts['cross_artifact_filename_candidate']}, "
        "ambiguous inventory filename sets="
        f"{counts['ambiguous_inventory_filename_candidates']}, "
        f"unresolved-in-inventory={counts['unresolved_in_inventory']}; "
        f"lock SHA-256 {lock_sha256}; inventory SHA-256 {inventory_sha256}; "
        f"output {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
