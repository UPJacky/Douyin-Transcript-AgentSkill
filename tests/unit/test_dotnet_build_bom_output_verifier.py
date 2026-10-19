from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "check_dotnet_build_bom_outputs.py"
SPEC = importlib.util.spec_from_file_location("dotnet_bom_output_verifier", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


@pytest.fixture
def bom_pair() -> tuple[dict, dict]:
    document = json.loads((ROOT / "docs" / "dotnet-windows-build-bom.json").read_text())
    return deepcopy(document), deepcopy(document)


def test_checked_in_bom_output_inventory_matches_itself(
    bom_pair: tuple[dict, dict],
) -> None:
    actual, expected = bom_pair
    assert verifier.verify_build_output_identities(actual, expected) > 0


@pytest.mark.parametrize(
    "field,value",
    [("path", "bin/Release/replaced.dll"), ("sizeBytes", 0), ("sha256", "0" * 64)],
)
def test_related_build_output_identity_mismatch_fails(
    bom_pair: tuple[dict, dict], field: str, value: object
) -> None:
    actual, expected = bom_pair
    actual["relatedBuilds"][0]["buildOutputs"][0][field] = value
    with pytest.raises(verifier.BomOutputError, match="inventory differs"):
        verifier.verify_build_output_identities(actual, expected)


def test_missing_or_extra_output_fails(bom_pair: tuple[dict, dict]) -> None:
    actual, expected = bom_pair
    actual["relatedBuilds"][1]["buildOutputs"].pop()
    with pytest.raises(verifier.BomOutputError, match="inventory differs"):
        verifier.verify_build_output_identities(actual, expected)


@pytest.mark.parametrize(
    "record",
    [
        {"path": "../outside.dll", "sizeBytes": 1, "sha256": "0" * 64},
        {"path": "bin/file.dll", "sizeBytes": True, "sha256": "0" * 64},
        {"path": "bin/file.dll", "sizeBytes": 1, "sha256": "A" * 64},
        {"path": "bin/file.dll", "sizeBytes": 1, "sha256": "0" * 64, "extra": "bad"},
    ],
)
def test_malformed_output_identity_fails_closed(record: dict) -> None:
    with pytest.raises(verifier.BomOutputError):
        verifier._output_records({"buildOutputs": [record]}, "test build")


def test_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bom.json"
    path.write_text('{"buildOutputs": [], "buildOutputs": []}', encoding="utf-8")
    with pytest.raises(verifier.BomOutputError, match="duplicate"):
        verifier._read_bom(path, "fixture")
