from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL_PROJECT = ROOT / "tools" / "spdx-schema-check"
CHECKER = ROOT / "scripts" / "check_spdx_schema.py"
DOCUMENT = ROOT / "docs" / "third-party-sbom.spdx.json"
SCHEMA = ROOT / "scripts" / "schemas" / "spdx-2.3.schema.json"


def _run_checker(*arguments: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    schema_test_env = env.get("DOUYIN_SPDX_SCHEMA_TEST_ENV")
    if schema_test_env:
        env["UV_PROJECT_ENVIRONMENT"] = schema_test_env
    else:
        # Do not let the main project's environment override the locked checker project.
        env.pop("UV_PROJECT_ENVIRONMENT", None)
    return subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(TOOL_PROJECT),
            "--locked",
            "--no-sync",
            "python",
            str(CHECKER),
            *arguments,
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )


def test_checked_in_sbom_matches_pinned_official_schema() -> None:
    result = _run_checker()

    assert result.returncode == 0, result.stderr
    assert "SPDX 2.3 schema validation passed" in result.stdout
    assert (
        "4126dc29f15e92feec92e9622f4939131ad58b125d6f578aa93e980a6e6f3212"
        in result.stdout
    )


def test_checker_rejects_modified_schema(tmp_path: Path) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    schema["title"] = "modified schema"
    modified_schema = tmp_path / "schema.json"
    modified_schema.write_text(json.dumps(schema), encoding="utf-8")

    result = _run_checker("--schema", str(modified_schema))

    assert result.returncode == 1
    assert (
        "schema SHA-256 differs from the pinned official support/2.3 schema"
        in result.stderr
    )


def test_checker_rejects_document_that_violates_schema(tmp_path: Path) -> None:
    document = json.loads(DOCUMENT.read_text(encoding="utf-8"))
    document["packages"] = "not an array"
    invalid_document = tmp_path / "invalid.spdx.json"
    invalid_document.write_text(json.dumps(document), encoding="utf-8")

    result = _run_checker("--document", str(invalid_document))

    assert result.returncode == 1
    assert "does not match the pinned 2.3 schema" in result.stderr
    assert "packages" in result.stderr


def test_checker_bounds_schema_error_materialization(tmp_path: Path) -> None:
    document = json.loads(DOCUMENT.read_text(encoding="utf-8"))
    document["packages"] = [None] * 120
    invalid_document = tmp_path / "many-invalid-packages.spdx.json"
    invalid_document.write_text(json.dumps(document), encoding="utf-8")

    result = _run_checker("--document", str(invalid_document))

    assert result.returncode == 1
    assert "at least 101 schema violations" in result.stderr
    assert "additional violations omitted" in result.stderr


def test_checker_rejects_malformed_document_json(tmp_path: Path) -> None:
    invalid_document = tmp_path / "malformed.spdx.json"
    invalid_document.write_text("{invalid", encoding="utf-8")

    result = _run_checker("--document", str(invalid_document))

    assert result.returncode == 1
    assert "SPDX document is not valid UTF-8 JSON" in result.stderr
