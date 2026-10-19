#!/usr/bin/env python3
"""Inventory locked wheel/sdist members one artifact at a time under bounded limits.

This offline wrapper uses the existing archive reader for each SHA-256 keyed cache
object separately. It never extracts, installs, imports, or executes package data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import BinaryIO

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "skills" / "douyin-transcript" / "src"),
)

from douyin_transcript.storage_security import ensure_private_directory
from spdx_terminal_safety import (
    escape_terminal_controls,
    escape_terminal_controls_unambiguously,
)
from inventory_locked_artifact_members import (
    InventoryError,
    LockIdentity,
    _lock_identities,
    build_inventory,
)
from verify_locked_artifact_cache import verify_cache
from safe_output import unlink_output, validate_output_directory, write_new_binary

_CHUNK_SIZE = 1024 * 1024
_OUTPUT_PART_BYTES = 8 * 1024 * 1024
_DEFAULT_EXPANDED_BUDGET = 16 * 1024 * 1024 * 1024
_DEFAULT_RUNTIME_SECONDS = 3 * 60 * 60
_MAX_RUNTIME_SECONDS = 24 * 60 * 60
_PREFIX_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z")
_EXPANDED_RE = re.compile(
    r"expanded archive bytes traversed for tar indexing: ([0-9,]+)"
)


class BatchInventoryError(ValueError):
    """Raised when the lock, cache, or output destination is invalid."""


def _error_code(error: Exception) -> str:
    message = str(error).casefold()
    if "time limit" in message or "deadline" in message:
        return "ARCHIVE_TIME_LIMIT"
    if "expanded-byte" in message or "expanded byte" in message:
        return "ARCHIVE_EXPANSION_LIMIT"
    if "member-count" in message or "member count" in message:
        return "ARCHIVE_MEMBER_COUNT_LIMIT"
    if "member exceeds" in message or "oversized size" in message:
        return "ARCHIVE_MEMBER_SIZE_LIMIT"
    if "unsupported archive" in message:
        return "UNSUPPORTED_ARCHIVE_FORMAT"
    if "sha-256" in message or "size mismatch" in message:
        return "CACHE_IDENTITY_MISMATCH"
    if "cache directory" in message or "cache object" in message:
        return "CACHE_PATH_ERROR"
    return type(error).__name__.upper()


def inspect_artifact(
    lockfile: Path,
    cache_dir: Path,
    work_dir: Path,
    digest: str,
    identities: list[LockIdentity],
    expanded_remaining: int,
) -> tuple[dict[str, object], str]:
    """Run the existing verifier on one cache object and return its member rows."""
    source = cache_dir / digest
    with tempfile.TemporaryDirectory(
        prefix=f"member-{digest[:10]}-", dir=work_dir
    ) as raw:
        staged_cache = Path(raw)
        staged_file = staged_cache / digest
        try:
            os.link(source, staged_file)
        except OSError as exc:
            raise InventoryError(
                f"cannot stage cache object: {type(exc).__name__}"
            ) from None

        markdown, jsonl_content = build_inventory(
            lockfile,
            staged_cache,
            max_total_expanded_bytes=expanded_remaining,
        )

    expanded_match = _EXPANDED_RE.search(markdown)
    if expanded_match is None:
        raise BatchInventoryError(
            "existing inventory summary omitted expanded-byte count"
        )
    rows = [line for line in jsonl_content.splitlines() if line]
    flag_counts: dict[str, int] = {}
    candidate_members = 0
    for line in rows:
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BatchInventoryError(
                "existing inventory emitted invalid JSONL"
            ) from exc
        if record.get("artifact_sha256") != digest:
            raise BatchInventoryError(
                "existing inventory emitted a row for another artifact"
            )
        flags = record.get("candidate_flags")
        if not isinstance(flags, list) or any(
            not isinstance(flag, str) for flag in flags
        ):
            raise BatchInventoryError(
                "existing inventory emitted malformed candidate flags"
            )
        if flags:
            candidate_members += 1
            for flag in flags:
                flag_counts[flag] = flag_counts.get(flag, 0) + 1

    return (
        {
            "sha256": digest,
            "status": "scanned",
            "archive_format": "zip"
            if identities[0].artifact_type == "wheel"
            else "tar.gz",
            "compressed_bytes": identities[0].size,
            "member_rows": len(rows),
            "candidate_member_rows": candidate_members,
            "expanded_bytes_walked": int(expanded_match.group(1).replace(",", "")),
            "candidate_counts": dict(sorted(flag_counts.items())),
            "lock_identities": [
                {
                    "package": item.package,
                    "version": item.version,
                    "artifact_type": item.artifact_type,
                    "url": item.url,
                    "filename": item.filename,
                    "sha256": item.sha256,
                    "size": item.size,
                }
                for item in identities
            ],
        },
        jsonl_content,
    )


def _artifact_labels(result: dict[str, object]) -> tuple[str, str, str, str]:
    identities = result["lock_identities"]
    assert isinstance(identities, list)
    packages = ", ".join(f"{item['package']} {item['version']}" for item in identities)
    types = ", ".join(sorted({str(item["artifact_type"]) for item in identities}))
    filenames = ", ".join(sorted({str(item["filename"]) for item in identities}))
    urls = "<br>".join(sorted({str(item["url"]) for item in identities}))
    return packages, types, filenames, urls


def _escape_cell(value: str) -> str:
    escaped = (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("|", "&#124;")
        .replace("\r", "&#13;")
        .replace("\n", "&#10;")
    )
    return escape_terminal_controls_unambiguously(escaped)


def _write_new_file(path: Path, content: str) -> tuple[int, str]:
    digest = hashlib.sha256()
    encoded = content.encode("utf-8")
    try:
        write_new_binary(path, encoded, create_parents=False, mode=0o666)
    except FileExistsError as exc:
        raise BatchInventoryError(f"output already exists: {path.name}") from exc
    digest.update(encoded)
    return len(encoded), digest.hexdigest()


def _write_jsonl_parts(
    spool: BinaryIO, output_dir: Path, prefix: str
) -> list[dict[str, object]]:
    parts: list[dict[str, object]] = []
    part_number = 0
    current_path: Path | None = None
    current_content = bytearray()
    current_size = 0
    current_hash = hashlib.sha256()
    current_rows = 0
    created_paths: list[Path] = []

    def close_part() -> None:
        nonlocal current_path, current_content, current_size, current_hash, current_rows
        if current_path is None:
            return
        write_new_binary(
            current_path,
            bytes(current_content),
            create_parents=False,
            mode=0o666,
        )
        created_paths.append(current_path)
        parts.append(
            {
                "path": current_path.name,
                "bytes": current_size,
                "sha256": current_hash.hexdigest(),
                "member_rows": current_rows,
            }
        )
        current_path = None
        current_content = bytearray()
        current_size = 0
        current_hash = hashlib.sha256()
        current_rows = 0

    try:
        spool.seek(0)
        for line in spool:
            if not line.endswith(b"\n"):
                raise BatchInventoryError("temporary JSONL spool has a partial row")
            if len(line) > _OUTPUT_PART_BYTES:
                raise BatchInventoryError(
                    "one member row exceeds the JSONL part-size limit"
                )
            if current_path is None or current_size + len(line) > _OUTPUT_PART_BYTES:
                close_part()
                part_number += 1
                current_path = output_dir / f"{prefix}-part-{part_number:03d}.jsonl"
            current_content.extend(line)
            current_hash.update(line)
            current_size += len(line)
            current_rows += 1
        close_part()
    except BaseException:
        for path in created_paths:
            try:
                unlink_output(path, missing_ok=True)
            except OSError:
                pass
        raise
    return parts


def _render_report(
    *,
    lock_digest: str,
    expected_artifacts: int,
    results: list[dict[str, object]],
    expanded_budget: int,
    expanded_total: int,
    elapsed_seconds: float,
    parts: list[dict[str, object]],
) -> str:
    scanned = [item for item in results if item["status"] == "scanned"]
    failures = [item for item in results if item["status"] == "failed"]
    unscanned = [item for item in results if item["status"] == "not_scanned"]
    compressed_total = sum(int(item["compressed_bytes"]) for item in scanned)
    member_total = sum(int(item["member_rows"]) for item in scanned)
    candidate_total = sum(int(item["candidate_member_rows"]) for item in scanned)
    candidate_counts: dict[str, int] = {}
    for item in scanned:
        counts = item["candidate_counts"]
        assert isinstance(counts, dict)
        for label, count in counts.items():
            candidate_counts[label] = candidate_counts.get(label, 0) + int(count)

    lines = [
        "# Bounded full-lock artifact member inventory",
        "",
        "## Coverage and method",
        "",
        f"- Lock SHA-256: {lock_digest}.",
        (
            f"- Unique lock artifacts expected: {expected_artifacts}; scanned: {len(scanned)}; "
            f"failed at an archive safety bound: {len(failures)}; "
            f"not scanned due to global budget: {len(unscanned)}."
        ),
        (
            f"- Scanned artifacts total {compressed_total:,} compressed bytes and "
            f"{expanded_total:,} archive bytes traversed/declared. The run used a "
            f"{expanded_budget:,}-byte aggregate expanded-byte budget and took "
            f"{elapsed_seconds:.1f} seconds."
        ),
        (
            f"- Member rows: {member_total:,}; candidate member rows: {candidate_total:,}. "
            "Candidate flag counts are per row, and one row may carry multiple flags."
        ),
        (
            "- The existing bounded archive reader checked each selected artifact against the "
            "lock and listed ZIP/tar members in place. No archive member was extracted, "
            "imported, installed, or executed."
        ),
        (
            "- Candidate labels are path/name heuristics. This inventory does not hash member "
            "contents, prove the complete native BOM or build provenance, determine license "
            "applicability, or approve redistribution."
        ),
        "",
        "## Member detail",
        "",
        "The complete JSONL rows are partitioned into these files (each part is capped at 8 MiB):",
        "",
    ]
    for part in parts:
        lines.append(
            f"- [{part['path']}]({part['path']}) — {part['member_rows']:,} rows, "
            f"{part['bytes']:,} bytes, SHA-256 {part['sha256']}."
        )
    lines.extend(
        [
            "",
            "## Artifact results",
            "",
            (
                "| Package/version | Type | Filename | SHA-256 | Bytes | Members | "
                "Candidate members | Expanded bytes walked | Status |"
            ),
            "|---|---|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for result in results:
        packages, artifact_types, filenames, _urls = _artifact_labels(result)
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_cell(packages),
                    _escape_cell(artifact_types),
                    _escape_cell(filenames),
                    str(result["sha256"]),
                    f"{int(result['compressed_bytes']):,}",
                    f"{int(result.get('member_rows', 0)):,}",
                    f"{int(result.get('candidate_member_rows', 0)):,}",
                    f"{int(result.get('expanded_bytes_walked', 0)):,}",
                    _escape_cell(
                        str(result["status"])
                        + (
                            ":" + str(result["error_code"])
                            if result.get("error_code")
                            else ""
                        )
                    ),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Candidate flag counts", "", "| Flag | Rows |", "|---|---:|"])
    for label, count in sorted(candidate_counts.items()):
        lines.append(f"| {_escape_cell(label)} | {count:,} |")
    return "\n".join(lines) + "\n"


def run_inventory(
    lockfile: Path,
    cache_dir: Path,
    work_dir: Path,
    output_dir: Path,
    *,
    prefix: str,
    expanded_budget: int = _DEFAULT_EXPANDED_BUDGET,
    runtime_seconds: int = _DEFAULT_RUNTIME_SECONDS,
) -> dict[str, object]:
    if not _PREFIX_RE.fullmatch(prefix):
        raise BatchInventoryError("output prefix contains unsupported characters")
    if expanded_budget <= 0 or expanded_budget > 64 * 1024**3:
        raise BatchInventoryError("expanded-byte budget must be between 1 and 64 GiB")
    if (
        not isinstance(runtime_seconds, int)
        or isinstance(runtime_seconds, bool)
        or runtime_seconds <= 0
        or runtime_seconds > _MAX_RUNTIME_SECONDS
    ):
        raise BatchInventoryError("runtime limit must be between 1 second and 24 hours")
    if not output_dir.is_dir():
        raise BatchInventoryError("output directory must already exist")
    try:
        output_dir = validate_output_directory(output_dir)
    except OSError as exc:
        raise BatchInventoryError(
            "output directory must be a regular non-symlink directory"
        ) from exc

    summary = verify_cache(lockfile, cache_dir)
    identities, lock_digest, _package_count = _lock_identities(lockfile)
    by_digest: dict[str, list[LockIdentity]] = {}
    for identity in identities:
        by_digest.setdefault(identity.sha256, []).append(identity)
    if summary.lock_sha256 != lock_digest:
        raise BatchInventoryError("uv.lock changed during cache verification")
    if summary.artifacts != len(by_digest):
        raise BatchInventoryError(
            "offline cache verifier and member scanner disagree on lock coverage"
        )

    output_paths = [
        output_dir / f"{prefix}.md",
        output_dir / f"{prefix}-manifest.json",
    ]
    if any(path.exists() or path.is_symlink() for path in output_paths) or any(
        output_dir.glob(f"{prefix}-part-*.jsonl")
    ):
        raise BatchInventoryError("one or more output files already exist")

    try:
        work_dir = ensure_private_directory(work_dir)
    except (OSError, ValueError) as exc:
        raise BatchInventoryError(
            f"work directory is not verified private: {type(exc).__name__}"
        ) from None
    start = time.monotonic()
    deadline = start + runtime_seconds
    expanded_total = 0
    results: list[dict[str, object]] = []
    spool_path: Path | None = None
    created_outputs: list[Path] = []
    try:
        with tempfile.NamedTemporaryFile(
            mode="w+b",
            prefix="member-inventory-",
            suffix=".jsonl",
            dir=work_dir,
            delete=False,
        ) as spool:
            spool_path = Path(spool.name)
            for index, digest in enumerate(sorted(by_digest), start=1):
                artifact_identities = by_digest[digest]
                common = {
                    "sha256": digest,
                    "compressed_bytes": artifact_identities[0].size,
                    "lock_identities": [
                        {
                            "package": item.package,
                            "version": item.version,
                            "artifact_type": item.artifact_type,
                            "url": item.url,
                            "filename": item.filename,
                            "sha256": item.sha256,
                            "size": item.size,
                        }
                        for item in artifact_identities
                    ],
                }
                if time.monotonic() >= deadline:
                    results.append(
                        {
                            **common,
                            "status": "not_scanned",
                            "error_code": "GLOBAL_TIME_LIMIT",
                        }
                    )
                    continue
                remaining_expanded = expanded_budget - expanded_total
                if remaining_expanded <= 0:
                    results.append(
                        {
                            **common,
                            "status": "not_scanned",
                            "error_code": "GLOBAL_EXPANSION_BUDGET",
                        }
                    )
                    continue
                try:
                    result, jsonl_content = inspect_artifact(
                        lockfile,
                        cache_dir,
                        work_dir,
                        digest,
                        artifact_identities,
                        remaining_expanded,
                    )
                except Exception as exc:
                    results.append(
                        {
                            **common,
                            "status": "failed",
                            "error_code": _error_code(exc),
                        }
                    )
                else:
                    expanded_total += int(result["expanded_bytes_walked"])
                    if expanded_total > expanded_budget:
                        raise BatchInventoryError(
                            "archive scanner exceeded aggregate expansion budget"
                        )
                    results.append(result)
                    spool.write(jsonl_content.encode("utf-8"))
                if index % 10 == 0 or index == len(by_digest):
                    print(
                        f"progress {index}/{len(by_digest)} scanned="
                        f"{sum(item['status'] == 'scanned' for item in results)} "
                        f"failed={sum(item['status'] == 'failed' for item in results)} "
                        f"expanded={expanded_total}",
                        flush=True,
                    )
            spool.flush()
            os.fsync(spool.fileno())

        with spool_path.open("rb") as spool:
            parts = _write_jsonl_parts(spool, output_dir, prefix)
        created_outputs.extend(output_dir / str(part["path"]) for part in parts)
        report = _render_report(
            lock_digest=lock_digest,
            expected_artifacts=len(by_digest),
            results=results,
            expanded_budget=expanded_budget,
            expanded_total=expanded_total,
            elapsed_seconds=time.monotonic() - start,
            parts=parts,
        )
        manifest = {
            "schema_version": 1,
            "lockfile": lockfile.as_posix(),
            "lock_sha256": lock_digest,
            "expected_artifact_count": len(by_digest),
            "scanned_artifact_count": sum(
                item["status"] == "scanned" for item in results
            ),
            "failed_artifact_count": sum(
                item["status"] == "failed" for item in results
            ),
            "not_scanned_artifact_count": sum(
                item["status"] == "not_scanned" for item in results
            ),
            "expanded_budget_bytes": expanded_budget,
            "expanded_bytes_walked": expanded_total,
            "elapsed_seconds": round(time.monotonic() - start, 3),
            "member_rows": sum(int(item.get("member_rows", 0)) for item in results),
            "candidate_member_rows": sum(
                int(item.get("candidate_member_rows", 0)) for item in results
            ),
            "jsonl_parts": parts,
            "artifacts": results,
        }
        manifest_text = (
            json.dumps(
                manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            + "\n"
        )
        manifest_path = output_dir / f"{prefix}-manifest.json"
        manifest_size, manifest_digest = _write_new_file(manifest_path, manifest_text)
        created_outputs.append(manifest_path)
        report_path = output_dir / f"{prefix}.md"
        report_size, report_digest = _write_new_file(report_path, report)
        created_outputs.append(report_path)
    except BaseException:
        for path in created_outputs:
            try:
                unlink_output(path, missing_ok=True)
            except OSError:
                pass
        raise
    finally:
        if spool_path is not None:
            spool_path.unlink(missing_ok=True)

    return {
        "scanned": manifest["scanned_artifact_count"],
        "failed": manifest["failed_artifact_count"],
        "not_scanned": manifest["not_scanned_artifact_count"],
        "member_rows": manifest["member_rows"],
        "report_sha256": report_digest,
        "manifest_sha256": manifest_digest,
        "report_bytes": report_size,
        "manifest_bytes": manifest_size,
    }


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lockfile",
        type=Path,
        default=root / "skills" / "douyin-transcript" / "uv.lock",
    )
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-prefix", default="artifact-member-inventory-complete")
    parser.add_argument(
        "--expanded-budget-bytes",
        type=int,
        default=_DEFAULT_EXPANDED_BUDGET,
    )
    parser.add_argument(
        "--runtime-seconds",
        type=int,
        default=_DEFAULT_RUNTIME_SECONDS,
    )
    args = parser.parse_args(argv)
    try:
        result = run_inventory(
            args.lockfile,
            args.cache_dir,
            args.work_dir,
            args.output_dir,
            prefix=args.output_prefix,
            expanded_budget=args.expanded_budget_bytes,
            runtime_seconds=args.runtime_seconds,
        )
    except (BatchInventoryError, InventoryError, OSError) as exc:
        print(
            "Batch member inventory failed: "
            f"{type(exc).__name__}: {escape_terminal_controls(str(exc))}",
            file=sys.stderr,
        )
        return 2
    print(
        "Batch member inventory written: "
        f"{result['scanned']} scanned, {result['failed']} failed, "
        f"{result['not_scanned']} not scanned, {result['member_rows']} member rows; "
        f"report SHA-256 {result['report_sha256']}"
    )
    return 0 if result["failed"] == 0 and result["not_scanned"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
