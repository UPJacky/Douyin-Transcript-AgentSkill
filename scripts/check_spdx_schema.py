#!/usr/bin/env python3
"""Validate the checked-in SPDX document against the vendored official schema."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Sequence

from jsonschema import Draft201909Validator, validators

from spdx_terminal_safety import escape_terminal_controls

_EXPECTED_SCHEMA_SHA256 = (
    "4126dc29f15e92feec92e9622f4939131ad58b125d6f578aa93e980a6e6f3212"
)
_MAX_INPUT_BYTES = 16 * 1024 * 1024
_MAX_VALIDATION_ERRORS = 100
_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DOCUMENT = _ROOT / "docs" / "third-party-sbom.spdx.json"
_DEFAULT_SCHEMA = Path(__file__).resolve().parent / "schemas" / "spdx-2.3.schema.json"


class SpdxSchemaValidationError(ValueError):
    """Raised when the vendored schema or SPDX document is invalid."""


def _read_bounded_bytes(path: Path, label: str) -> bytes:
    try:
        path_info = path.lstat()
    except OSError:
        raise
    if stat.S_ISLNK(path_info.st_mode) or not stat.S_ISREG(path_info.st_mode):
        raise SpdxSchemaValidationError(f"{label} must be a regular, non-symlink file")
    if path_info.st_size > _MAX_INPUT_BYTES:
        raise SpdxSchemaValidationError(
            f"{label} exceeds {_MAX_INPUT_BYTES} byte size limit"
        )

    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags)
    try:
        with os.fdopen(descriptor, "rb") as stream:
            initial = os.fstat(stream.fileno())
            if not stat.S_ISREG(initial.st_mode):
                raise SpdxSchemaValidationError(f"{label} must be a regular file")
            if (initial.st_dev, initial.st_ino) != (path_info.st_dev, path_info.st_ino):
                raise SpdxSchemaValidationError(
                    f"{label} changed between validation and open"
                )
            content = stream.read(_MAX_INPUT_BYTES + 1)
            if len(content) > _MAX_INPUT_BYTES:
                raise SpdxSchemaValidationError(
                    f"{label} exceeds {_MAX_INPUT_BYTES} byte size limit"
                )
            final = os.fstat(stream.fileno())
            if (
                initial.st_dev,
                initial.st_ino,
                initial.st_size,
                initial.st_mtime_ns,
                initial.st_ctime_ns,
            ) != (
                final.st_dev,
                final.st_ino,
                final.st_size,
                final.st_mtime_ns,
                final.st_ctime_ns,
            ):
                raise SpdxSchemaValidationError(f"{label} changed while being read")
    except BaseException:
        # fdopen owns the descriptor once it succeeds; os.close on an already
        # closed descriptor is harmlessly avoided by checking its validity.
        try:
            os.fstat(descriptor)
        except OSError:
            pass
        else:
            os.close(descriptor)
        raise
    return content


def _parse_json(content: bytes, label: str) -> Any:
    try:
        return json.loads(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise SpdxSchemaValidationError(f"{label} is not valid UTF-8 JSON") from exc


def validate_spdx_document(
    document_path: Path, schema_path: Path = _DEFAULT_SCHEMA
) -> None:
    """Validate one SPDX JSON file using only the exact pinned official schema."""
    schema_bytes = _read_bounded_bytes(schema_path, "SPDX schema")
    schema_digest = hashlib.sha256(schema_bytes).hexdigest()
    if schema_digest != _EXPECTED_SCHEMA_SHA256:
        raise SpdxSchemaValidationError(
            "SPDX schema SHA-256 differs from the pinned official support/2.3 schema"
        )
    schema = _parse_json(schema_bytes, "SPDX schema")
    if not isinstance(schema, dict):
        raise SpdxSchemaValidationError("SPDX schema root must be a JSON object")

    try:
        validator_type = validators.validator_for(schema)
        validator_type.check_schema(schema)
    except Exception as exc:
        raise SpdxSchemaValidationError(
            "Pinned SPDX schema is not a valid JSON Schema"
        ) from exc
    if validator_type is not Draft201909Validator:
        raise SpdxSchemaValidationError(
            "Pinned SPDX schema uses an unexpected JSON Schema draft"
        )

    document = _parse_json(
        _read_bounded_bytes(document_path, "SPDX document"), "SPDX document"
    )
    validator = validator_type(schema)
    errors: list[Any] = []
    for error in validator.iter_errors(document):
        errors.append(error)
        if len(errors) > _MAX_VALIDATION_ERRORS:
            break
    errors.sort(
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.message,
        )
    )
    if errors:
        first = errors[0]
        location = "$" + "".join(
            f"[{part}]" if isinstance(part, int) else f".{part}"
            for part in first.absolute_path
        )
        count_note = (
            f" (at least {_MAX_VALIDATION_ERRORS + 1} schema violations; "
            "additional violations omitted)"
            if len(errors) > _MAX_VALIDATION_ERRORS
            else f" ({len(errors)} schema violations total)"
        )
        message = escape_terminal_controls(first.message)[:400]
        raise SpdxSchemaValidationError(
            f"SPDX document does not match the pinned 2.3 schema at {location}: {message}{count_note}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", type=Path, default=_DEFAULT_DOCUMENT)
    parser.add_argument("--schema", type=Path, default=_DEFAULT_SCHEMA)
    args = parser.parse_args(argv)
    try:
        validate_spdx_document(args.document, args.schema)
    except (OSError, SpdxSchemaValidationError) as exc:
        message = escape_terminal_controls(str(exc))[:600]
        print(f"SPDX schema check failed: {message}", file=sys.stderr)
        return 1
    print(
        "SPDX 2.3 schema validation passed: "
        f"{escape_terminal_controls(str(args.document))} "
        f"(schema SHA-256 {_EXPECTED_SCHEMA_SHA256})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
