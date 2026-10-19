#!/usr/bin/env python3
"""Compare recorded .NET build output identities with a generated BOM."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Sequence

MAX_BOM_BYTES = 16 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class BomOutputError(ValueError):
    """Raised when a BOM output inventory is malformed or differs."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BomOutputError("BOM JSON contains a duplicate object key")
        result[key] = value
    return result


def _read_bom(path: Path, label: str) -> dict[str, Any]:
    try:
        info = path.lstat()
        if path.is_symlink() or not path.is_file():
            raise BomOutputError(f"{label} must be a regular non-symlink file")
        if info.st_size > MAX_BOM_BYTES:
            raise BomOutputError(f"{label} exceeds the size limit")
        content = path.read_bytes()
        if len(content) > MAX_BOM_BYTES:
            raise BomOutputError(f"{label} exceeds the size limit")
        value = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise BomOutputError(f"Could not read {label} as bounded JSON") from exc
    if not isinstance(value, dict):
        raise BomOutputError(f"{label} root must be an object")
    return value


def _output_records(build: dict[str, Any], label: str) -> list[tuple[str, int, str]]:
    outputs = build.get("buildOutputs")
    if not isinstance(outputs, list) or not outputs:
        raise BomOutputError(f"{label} has no build outputs")

    records: list[tuple[str, int, str]] = []
    seen: set[str] = set()
    for item in outputs:
        if not isinstance(item, dict) or set(item) != {"path", "sizeBytes", "sha256"}:
            raise BomOutputError(f"{label} has a malformed build output record")
        relative_path = item["path"]
        size = item["sizeBytes"]
        digest = item["sha256"]
        if (
            not isinstance(relative_path, str)
            or not relative_path
            or "\\" in relative_path
            or relative_path.startswith("/")
            or PurePosixPath(relative_path).is_absolute()
            or PureWindowsPath(relative_path).is_absolute()
            or PureWindowsPath(relative_path).drive
            or ".." in PurePosixPath(relative_path).parts
            or "." in PurePosixPath(relative_path).parts
            or relative_path in seen
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or not isinstance(digest, str)
            or not _SHA256.fullmatch(digest)
        ):
            raise BomOutputError(f"{label} has an invalid build output identity")
        seen.add(relative_path)
        records.append((relative_path, size, digest))
    return sorted(records, key=lambda record: record[0])


def _all_builds(
    document: dict[str, Any], label: str
) -> list[tuple[str, dict[str, Any]]]:
    related = document.get("relatedBuilds")
    if not isinstance(related, list) or len(related) != 2:
        raise BomOutputError(f"{label} must contain the two related build records")
    if any(not isinstance(item, dict) for item in related):
        raise BomOutputError(f"{label} has a malformed related build record")
    return [("main", document), ("related[0]", related[0]), ("related[1]", related[1])]


def verify_build_output_identities(
    actual: dict[str, Any], expected: dict[str, Any]
) -> int:
    """Require exact path, size and SHA-256 inventories for all three builds."""
    actual_builds = _all_builds(actual, "generated BOM")
    expected_builds = _all_builds(expected, "checked-in BOM")
    total = 0
    for (actual_label, actual_build), (expected_label, expected_build) in zip(
        actual_builds, expected_builds, strict=True
    ):
        if actual_label != expected_label:
            raise BomOutputError("BOM build record order changed")
        actual_projects = actual_build.get("projects")
        expected_projects = expected_build.get("projects")
        if actual_projects != expected_projects:
            raise BomOutputError(f"{actual_label} project identity differs")
        actual_records = _output_records(actual_build, f"generated {actual_label}")
        expected_records = _output_records(expected_build, f"checked-in {actual_label}")
        if actual_records != expected_records:
            raise BomOutputError(
                f"{actual_label} build output path/size/SHA-256 inventory differs"
            )
        total += len(actual_records)
    return total


def main(argv: Sequence[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actual", type=Path, required=True)
    parser.add_argument(
        "--expected", type=Path, default=root / "docs" / "dotnet-windows-build-bom.json"
    )
    args = parser.parse_args(argv)
    try:
        actual = _read_bom(args.actual, "generated BOM")
        expected = _read_bom(args.expected, "checked-in BOM")
        count = verify_build_output_identities(actual, expected)
    except (BomOutputError, OSError) as exc:
        print(f".NET build BOM output verification failed: {exc}", file=sys.stderr)
        return 1
    print(f".NET build BOM output identities match for three builds ({count} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
