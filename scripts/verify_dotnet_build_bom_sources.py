#!/usr/bin/env python3
"""Verify source and dependency identities in a generated .NET build BOM."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Sequence

from check_dotnet_build_bom_outputs import BomOutputError, _read_bom


TOP_LEVEL_FIELDS = (
    "schemaVersion",
    "scope",
    "toolchain",
    "sourceInputs",
    "nugetLock",
    "packages",
)
RUNTIME_FIELDS = (
    "projects",
    "targetFramework",
    "runtimeIdentifier",
    "purpose",
    "globalJson",
    "sourceInputs",
    "nugetLocks",
    "nugetPackages",
    "buildCommand",
    "limitations",
)
READBACK_FIELDS = (
    "projects",
    "targetFramework",
    "runtimeIdentifier",
    "purpose",
    "globalJson",
    "sourceInputs",
    "nugetLocks",
    "nugetPackages",
    "buildCommand",
    "harnessCommand",
    "limitations",
)


def _first_difference(actual: Any, expected: Any, path: str) -> str | None:
    """Return the first semantic JSON difference, ignoring object key order."""
    if type(actual) is not type(expected):
        return (
            f"{path} (expected {type(expected).__name__}, got {type(actual).__name__})"
        )
    if isinstance(actual, dict):
        actual_keys = set(actual)
        expected_keys = set(expected)
        if actual_keys != expected_keys:
            missing = sorted(expected_keys - actual_keys)
            extra = sorted(actual_keys - expected_keys)
            return f"{path} (missing keys {missing}; extra keys {extra})"
        for key in sorted(actual):
            difference = _first_difference(actual[key], expected[key], f"{path}.{key}")
            if difference is not None:
                return difference
        return None
    if isinstance(actual, list):
        if len(actual) != len(expected):
            return f"{path} (expected {len(expected)} records, got {len(actual)})"
        for index, (actual_item, expected_item) in enumerate(
            zip(actual, expected, strict=True)
        ):
            difference = _first_difference(
                actual_item, expected_item, f"{path}[{index}]"
            )
            if difference is not None:
                return difference
        return None
    if actual != expected:
        return f"{path} (expected {expected!r}, got {actual!r})"
    return None


def verify_source_identities(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    """Require exact semantic equality for pinned source and package records."""
    actual_related = actual.get("relatedBuilds")
    expected_related = expected.get("relatedBuilds")
    if (
        not isinstance(actual_related, list)
        or len(actual_related) != 2
        or not isinstance(expected_related, list)
        or len(expected_related) != 2
    ):
        raise BomOutputError("BOM must contain exactly two related build records")

    groups = (
        ("$", None, TOP_LEVEL_FIELDS),
        ("relatedBuilds[0]", 0, RUNTIME_FIELDS),
        ("relatedBuilds[1]", 1, READBACK_FIELDS),
    )
    for label, related_index, fields in groups:
        actual_record = (
            actual if related_index is None else actual_related[related_index]
        )
        expected_record = (
            expected if related_index is None else expected_related[related_index]
        )
        if not isinstance(actual_record, dict) or not isinstance(expected_record, dict):
            raise BomOutputError(f"{label} is not a JSON object")
        for field in fields:
            if field not in actual_record or field not in expected_record:
                raise BomOutputError(f"{label}.{field} is missing")
            difference = _first_difference(
                actual_record[field], expected_record[field], f"{label}.{field}"
            )
            if difference is not None:
                raise BomOutputError(f"source identity differs at {difference}")


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
        verify_source_identities(actual, expected)
    except (BomOutputError, OSError) as exc:
        print(f".NET build BOM source verification failed: {exc}", file=sys.stderr)
        return 1
    print(".NET build BOM source and dependency identities match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
