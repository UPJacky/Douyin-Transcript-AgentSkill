from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "verify_dotnet_build_bom_sources.py"
SPEC = importlib.util.spec_from_file_location("dotnet_bom_source_verifier", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


@pytest.fixture
def bom_pair() -> tuple[dict, dict]:
    document = json.loads(
        (ROOT / "docs" / "dotnet-windows-build-bom.json").read_text(encoding="utf-8")
    )
    return deepcopy(document), deepcopy(document)


def test_checked_in_bom_source_identity_matches_itself(
    bom_pair: tuple[dict, dict],
) -> None:
    actual, expected = bom_pair
    verifier.verify_source_identities(actual, expected)


def test_object_property_order_does_not_change_bom_identity(
    bom_pair: tuple[dict, dict],
) -> None:
    actual, expected = bom_pair
    actual["scope"] = dict(reversed(list(actual["scope"].items())))
    verifier.verify_source_identities(actual, expected)


def test_source_file_hash_mismatch_reports_exact_record(
    bom_pair: tuple[dict, dict],
) -> None:
    actual, expected = bom_pair
    actual["sourceInputs"][0]["sha256"] = "0" * 64
    with pytest.raises(
        verifier.BomOutputError,
        match=r"source identity differs at \$\.sourceInputs\[0\]\.sha256",
    ):
        verifier.verify_source_identities(actual, expected)


def test_related_build_source_mismatch_is_checked(
    bom_pair: tuple[dict, dict],
) -> None:
    actual, expected = bom_pair
    actual["relatedBuilds"][0]["sourceInputs"].pop()
    with pytest.raises(
        verifier.BomOutputError,
        match=r"relatedBuilds\[0\]\.sourceInputs \(expected 29 records, got 28\)",
    ):
        verifier.verify_source_identities(actual, expected)


def test_missing_related_build_fails_closed(bom_pair: tuple[dict, dict]) -> None:
    actual, expected = bom_pair
    actual["relatedBuilds"].pop()
    with pytest.raises(verifier.BomOutputError, match="exactly two"):
        verifier.verify_source_identities(actual, expected)
