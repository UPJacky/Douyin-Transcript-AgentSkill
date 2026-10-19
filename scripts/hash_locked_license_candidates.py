#!/usr/bin/env python3
"""Hash unbound license/notice-name members from the complete locked cache.

The tool reads archive members in place, binds each digest to its locked artifact,
and can add the records as SPDX supplemental evidence without changing any license
expression or conclusion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from inventory_locked_artifact_members import (
    InventoryError,
    _lock_identities,
)
from verify_locked_artifact_cache import verify_cache
from verify_spdx_evidence import (
    EvidenceVerificationError,
    _ArchiveReadBudget,
    _canonical_name,
    _read_archive_member,
    _safe_member_path,
    _verified_artifact_snapshot,
    verify_evidence,
)
from spdx_terminal_safety import escape_terminal_controls
from safe_output import open_new_binary, write_atomic_text

_MAX_MANIFEST_BYTES = 16 * 1024 * 1024
_MAX_PART_BYTES = 8 * 1024 * 1024
_MAX_CANDIDATES = 5_000
_MAX_TOTAL_READ_BYTES = 32 * 1024**3
_MAX_RUNTIME_SECONDS = 3 * 60 * 60
_MAX_MEMBER_SECONDS = 120.0
_OUTPUT_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


class CandidateHashError(ValueError):
    """Raised when inventory, cache, or evidence identities are inconsistent."""


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CandidateHashError("JSON input contains a duplicate object key")
        result[key] = value
    return result


def _read_regular(path: Path, limit: int, label: str) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise CandidateHashError(f"cannot stat {label}: {type(exc).__name__}") from None
    if (
        not stat.S_ISREG(before.st_mode)
        or getattr(before, "st_file_attributes", 0) & 0x400
        or before.st_size > limit
    ):
        raise CandidateHashError(f"{label} is not a bounded regular file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or getattr(opened, "st_file_attributes", 0) & 0x400
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            or opened.st_size != before.st_size
        ):
            raise CandidateHashError(f"{label} changed while opening")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            content = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
        if len(content) != before.st_size or len(content) > limit:
            raise CandidateHashError(f"{label} changed size while reading")
        before_signature = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        after_signature = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if before_signature != after_signature:
            raise CandidateHashError(f"{label} changed while reading")
        return content
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _load_json(path: Path, limit: int, label: str) -> tuple[dict[str, Any], bytes]:
    raw = _read_regular(path, limit, label)
    try:
        parsed = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CandidateHashError(
            f"{label} is invalid UTF-8 JSON: {type(exc).__name__}"
        ) from None
    if not isinstance(parsed, dict):
        raise CandidateHashError(f"{label} must contain a JSON object")
    return parsed, raw


def _evidence_members(
    evidence: dict[str, Any],
) -> tuple[set[tuple[str, str, str, str]], dict[tuple[str, str], set[tuple[str, str]]]]:
    bound: set[tuple[str, str, str, str]] = set()
    known_hashes: dict[tuple[str, str], set[tuple[str, str]]] = {}

    def add(
        package: str, version: str, artifact_sha256: Any, path: Any, member_sha256: Any
    ) -> None:
        if not all(isinstance(item, str) and item for item in (artifact_sha256, path)):
            return
        key = (_canonical_name(package), version)
        bound.add((key[0], version, artifact_sha256, path))
        if isinstance(member_sha256, str) and re.fullmatch(
            r"[0-9a-f]{64}", member_sha256
        ):
            known_hashes.setdefault(key, set()).add((path, member_sha256))

    packages = evidence.get("packages")
    if not isinstance(packages, list):
        raise CandidateHashError("SPDX evidence has no package array")
    for package in packages:
        if not isinstance(package, dict):
            raise CandidateHashError("SPDX evidence has a malformed package row")
        name = package.get("name")
        version = package.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            raise CandidateHashError("SPDX evidence package identity is malformed")
        add(
            name,
            version,
            package.get("artifact_sha256"),
            package.get("metadata_path"),
            package.get("metadata_sha256"),
        )
        for field in ("license_file",):
            item = package.get(field)
            if isinstance(item, dict):
                add(
                    name,
                    version,
                    item.get("artifact_sha256"),
                    item.get("path"),
                    item.get("sha256"),
                )
        for field in ("license_notices", "artifact_members"):
            items = package.get(field, [])
            if not isinstance(items, list):
                raise CandidateHashError(f"SPDX evidence {field} list is malformed")
            for item in items:
                if isinstance(item, dict):
                    add(
                        name,
                        version,
                        item.get("artifact_sha256"),
                        item.get("path"),
                        item.get("sha256"),
                    )
    return bound, known_hashes


def _load_unbound_candidates(
    inventory_dir: Path,
    manifest: dict[str, Any],
    identities_by_digest: dict[str, list[Any]],
    bound: set[tuple[str, str, str, str]],
) -> dict[str, dict[str, dict[str, Any]]]:
    expected_count = manifest.get("expected_artifact_count")
    artifacts = manifest.get("artifacts")
    parts = manifest.get("jsonl_parts")
    if (
        not isinstance(expected_count, int)
        or not isinstance(artifacts, list)
        or not isinstance(parts, list)
        or manifest.get("scanned_artifact_count") != expected_count
        or manifest.get("failed_artifact_count") != 0
        or manifest.get("not_scanned_artifact_count") != 0
    ):
        raise CandidateHashError(
            "member manifest does not describe complete successful coverage"
        )
    manifest_artifacts: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise CandidateHashError("member manifest has a malformed artifact row")
        digest = artifact.get("sha256")
        if not isinstance(digest, str) or digest in manifest_artifacts:
            raise CandidateHashError(
                "member manifest has a duplicate/malformed artifact hash"
            )
        manifest_artifacts[digest] = artifact
    if set(manifest_artifacts) != set(identities_by_digest):
        raise CandidateHashError("member manifest artifact set differs from uv.lock")
    by_digest: dict[str, dict[str, dict[str, Any]]] = {}
    total_rows = 0
    for part in parts:
        if not isinstance(part, dict):
            raise CandidateHashError("member manifest has a malformed JSONL part row")
        part_name = part.get("path")
        expected_hash = part.get("sha256")
        expected_size = part.get("bytes")
        expected_rows = part.get("member_rows")
        if (
            not isinstance(part_name, str)
            or not _OUTPUT_NAME_RE.fullmatch(part_name)
            or not isinstance(expected_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
            or not isinstance(expected_size, int)
            or expected_size < 0
            or expected_size > _MAX_PART_BYTES
            or not isinstance(expected_rows, int)
            or expected_rows < 0
        ):
            raise CandidateHashError("member manifest has invalid JSONL part metadata")
        raw = _read_regular(
            inventory_dir / part_name, _MAX_PART_BYTES, "member JSONL part"
        )
        if (
            len(raw) != expected_size
            or hashlib.sha256(raw).hexdigest() != expected_hash
        ):
            raise CandidateHashError(
                f"member JSONL part identity mismatch: {part_name}"
            )
        lines = raw.splitlines()
        if len(lines) != expected_rows:
            raise CandidateHashError(
                f"member JSONL part row count mismatch: {part_name}"
            )
        for line in lines:
            try:
                row = json.loads(
                    line.decode("utf-8"),
                    object_pairs_hook=_reject_duplicate_json_keys,
                )
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CandidateHashError(
                    "member JSONL contains an invalid row"
                ) from exc
            if not isinstance(row, dict):
                raise CandidateHashError("member JSONL row is not an object")
            digest = row.get("artifact_sha256")
            path = row.get("member_path")
            size = row.get("member_size")
            flags = row.get("candidate_flags")
            if (
                digest not in manifest_artifacts
                or not isinstance(path, str)
                or not isinstance(size, int)
                or isinstance(size, bool)
                or size < 0
                or not isinstance(flags, list)
                or any(not isinstance(flag, str) for flag in flags)
            ):
                raise CandidateHashError("member JSONL row identity is malformed")
            total_rows += 1
            if "license-notice-name" not in flags or size == 0:
                continue
            member_type = row.get("member_type")
            if member_type != "file":
                raise CandidateHashError(
                    "non-regular license-name candidate needs separate review: "
                    f"{escape_terminal_controls(digest)}:"
                    f"{escape_terminal_controls(path)}"
                )
            path = _safe_member_path(path, "license/notice candidate path")
            for identity in identities_by_digest[digest]:
                package_key = (
                    _canonical_name(identity.package),
                    identity.version,
                    digest,
                    path,
                )
                if package_key in bound:
                    continue
                item = {
                    "package": identity.package,
                    "version": identity.version,
                    "artifact_type": identity.artifact_type,
                    "artifact_url": identity.url,
                    "artifact_sha256": digest,
                    "artifact_size": identity.size,
                    "member_path": path,
                    "member_size": size,
                    "evidence_bound_before": False,
                }
                candidates = by_digest.setdefault(digest, {})
                previous = candidates.get(path)
                if previous is not None and previous["member_size"] != size:
                    raise CandidateHashError(
                        "duplicate candidate paths disagree on size"
                    )
                candidates[path] = item
                if sum(len(paths) for paths in by_digest.values()) > _MAX_CANDIDATES:
                    raise CandidateHashError(
                        "too many unbound license/notice candidates"
                    )
    if total_rows != manifest.get("member_rows"):
        raise CandidateHashError("member manifest total row count is inconsistent")
    return by_digest


def hash_candidate_member(
    stream: Any,
    artifact_type: str,
    path: str,
    expected_size: int,
    deadline: float,
) -> tuple[str, int, int]:
    """Hash one safe regular archive member without extracting it to disk."""
    member_deadline = min(deadline, time.monotonic() + _MAX_MEMBER_SECONDS)
    budget = _ArchiveReadBudget(
        member_deadline,
        "license/notice member hash exceeded its time limit",
    )
    digest, size, _content = _read_archive_member(
        stream,
        artifact_type,
        _safe_member_path(path, "license/notice member path"),
        budget,
    )
    if size != expected_size:
        raise CandidateHashError("candidate member size differs from inventory")
    return digest, size, budget.bytes_read


def _write_candidate_report(path: Path, encoded: bytes) -> None:
    try:
        with open_new_binary(path, create_parents=False) as output:
            output.write(encoded)
    except FileExistsError as exc:
        raise CandidateHashError("hash evidence output already exists") from exc


def run_candidate_hashes(
    lockfile: Path,
    cache_dir: Path,
    inventory_dir: Path,
    manifest_path: Path,
    evidence_path: Path,
    output_path: Path,
    *,
    update_evidence: bool = False,
    runtime_seconds: int = _MAX_RUNTIME_SECONDS,
) -> dict[str, Any]:
    if not 0 < runtime_seconds <= _MAX_RUNTIME_SECONDS:
        raise CandidateHashError("runtime limit must be between 1 second and 3 hours")
    if output_path.exists():
        raise CandidateHashError("hash evidence output already exists")
    evidence, evidence_bytes = _load_json(
        evidence_path, _MAX_MANIFEST_BYTES, "SPDX evidence"
    )
    bound, known_hashes = _evidence_members(evidence)
    manifest, _manifest_bytes = _load_json(
        manifest_path, _MAX_MANIFEST_BYTES, "member inventory manifest"
    )
    identities, lock_digest, _package_count = _lock_identities(lockfile)
    summary = verify_cache(lockfile, cache_dir)
    if manifest.get("lock_sha256") != lock_digest or summary.lock_sha256 != lock_digest:
        raise CandidateHashError(
            "lockfile identity differs between evidence, cache and inventory"
        )
    identities_by_digest: dict[str, list[Any]] = {}
    for identity in identities:
        identities_by_digest.setdefault(identity.sha256, []).append(identity)
    if summary.artifacts != len(identities_by_digest):
        raise CandidateHashError("offline cache and uv.lock artifact counts differ")
    candidate_paths = _load_unbound_candidates(
        inventory_dir, manifest, identities_by_digest, bound
    )
    started = time.monotonic()
    deadline = started + runtime_seconds
    total_read_bytes = 0
    records: list[dict[str, Any]] = []

    for digest in sorted(candidate_paths):
        artifact_candidates = candidate_paths[digest]
        if time.monotonic() >= deadline:
            raise CandidateHashError(
                "overall candidate hash run exceeded its time limit"
            )
        identities_for_digest = identities_by_digest[digest]
        expected_size = identities_for_digest[0].size
        if any(item.size != expected_size for item in identities_for_digest):
            raise CandidateHashError("lock identities disagree on artifact size")
        artifact_types = {item.artifact_type for item in identities_for_digest}
        if len(artifact_types) != 1:
            raise CandidateHashError(
                "identical artifact hash has conflicting archive types"
            )
        artifact_type = next(iter(artifact_types))
        cache_path = cache_dir / digest
        try:
            with _verified_artifact_snapshot(
                cache_path,
                digest,
                expected_size,
                deadline=deadline,
            ) as stream:
                total_read_bytes += expected_size
                if total_read_bytes > _MAX_TOTAL_READ_BYTES:
                    raise CandidateHashError(
                        "candidate hash run exceeded total archive read budget"
                    )
                for path, candidate in sorted(artifact_candidates.items()):
                    if time.monotonic() >= deadline:
                        raise CandidateHashError(
                            "overall candidate hash run exceeded its time limit"
                        )
                    member_hash, member_size, member_read = hash_candidate_member(
                        stream,
                        artifact_type,
                        path,
                        int(candidate["member_size"]),
                        deadline,
                    )
                    total_read_bytes += member_read
                    if total_read_bytes > _MAX_TOTAL_READ_BYTES:
                        raise CandidateHashError(
                            "candidate hash run exceeded total archive read budget"
                        )
                    package_key = (
                        _canonical_name(str(candidate["package"])),
                        str(candidate["version"]),
                    )
                    evidence_hashes = sorted(
                        existing_path
                        for existing_path, existing_hash in known_hashes.get(
                            package_key, set()
                        )
                        if existing_hash == member_hash
                    )
                    records.append(
                        {
                            **candidate,
                            "member_sha256": member_hash,
                            "member_size": member_size,
                            "matches_existing_member_paths": evidence_hashes,
                            "evidence_bound_after": bool(update_evidence),
                        }
                    )
        except (EvidenceVerificationError, InventoryError, OSError) as exc:
            raise CandidateHashError(
                f"could not hash locked artifact {digest}: {type(exc).__name__}"
            ) from None

    package_map = {
        (_canonical_name(item["name"]), item["version"]): item
        for item in evidence["packages"]
        if isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and isinstance(item.get("version"), str)
    }
    if len(package_map) != len(evidence["packages"]):
        raise CandidateHashError("SPDX evidence package identities are not unique")

    added_count = 0
    if update_evidence:
        for record in records:
            package = package_map.get(
                (_canonical_name(record["package"]), record["version"])
            )
            if package is None:
                raise CandidateHashError(
                    "candidate package is missing from SPDX evidence"
                )
            existing = package.setdefault("artifact_members", [])
            if not isinstance(existing, list):
                raise CandidateHashError("package supplemental evidence is malformed")
            entry = {
                "artifact_type": record["artifact_type"],
                "artifact_url": record["artifact_url"],
                "artifact_sha256": record["artifact_sha256"],
                "artifact_size": record["artifact_size"],
                "path": record["member_path"],
                "sha256": record["member_sha256"],
                "size": record["member_size"],
            }
            existing.append(entry)
            added_count += 1
        evidence_text = json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
        evidence_bytes_now = _read_regular(
            evidence_path, _MAX_MANIFEST_BYTES, "SPDX evidence"
        )
        if (
            hashlib.sha256(evidence_bytes_now).hexdigest()
            != hashlib.sha256(evidence_bytes).hexdigest()
        ):
            raise CandidateHashError("SPDX evidence changed during candidate hashing")
        with tempfile.TemporaryDirectory(
            prefix="license-evidence-validation-"
        ) as temporary_directory:
            temporary_path = Path(temporary_directory) / "evidence.json"
            write_atomic_text(temporary_path, evidence_text)
            verify_evidence(lockfile, temporary_path, cache_dir)
            write_atomic_text(evidence_path, evidence_text, create_parents=False)

    report = {
        "schema_version": 1,
        "lock_sha256": lock_digest,
        "inventory_manifest_sha256": hashlib.sha256(_manifest_bytes).hexdigest(),
        "candidate_count": len(records),
        "evidence_added_count": added_count,
        "evidence_updated": update_evidence,
        "total_read_bytes": total_read_bytes,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "records": records,
    }
    encoded = (
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    if len(encoded) > _MAX_MANIFEST_BYTES:
        raise CandidateHashError("candidate hash report exceeds 16 MiB")
    _write_candidate_report(output_path, encoded)
    return {
        "candidate_count": len(records),
        "evidence_added_count": added_count,
        "evidence_updated": update_evidence,
        "output_sha256": hashlib.sha256(encoded).hexdigest(),
        "elapsed_seconds": report["elapsed_seconds"],
        "total_read_bytes": total_read_bytes,
    }


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lockfile", type=Path, default=root / "skills/douyin-transcript/uv.lock"
    )
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--inventory-dir", type=Path, default=root / "docs")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=root / "docs/artifact-member-inventory-complete-manifest.json",
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=root / "docs/third-party-license-evidence.json",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--update-spdx-evidence", action="store_true")
    parser.add_argument("--runtime-seconds", type=int, default=_MAX_RUNTIME_SECONDS)
    args = parser.parse_args(argv)
    try:
        result = run_candidate_hashes(
            args.lockfile,
            args.cache_dir,
            args.inventory_dir,
            args.manifest,
            args.evidence,
            args.output,
            update_evidence=args.update_spdx_evidence,
            runtime_seconds=args.runtime_seconds,
        )
    except (
        CandidateHashError,
        EvidenceVerificationError,
        InventoryError,
        OSError,
    ) as exc:
        print(
            f"License candidate hashing failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    print(
        f"Hashed {result['candidate_count']} unbound members; "
        f"added {result['evidence_added_count']} supplemental evidence rows; "
        f"output SHA-256 {result['output_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
