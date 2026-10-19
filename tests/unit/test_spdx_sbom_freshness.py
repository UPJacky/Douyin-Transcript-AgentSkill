from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import check_spdx_sbom_freshness as freshness  # noqa: E402


@pytest.fixture
def current_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    lock = tmp_path / "uv.lock"
    evidence = tmp_path / "third-party-license-evidence.json"
    document = tmp_path / "third-party-sbom.spdx.json"
    shutil.copyfile(ROOT / "skills" / "douyin-transcript" / "uv.lock", lock)
    shutil.copyfile(ROOT / "docs" / "third-party-license-evidence.json", evidence)
    shutil.copyfile(ROOT / "docs" / "third-party-sbom.spdx.json", document)
    return lock, evidence, document


def _write_document(path: Path, document: dict) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def test_current_sbom_matches_lock_and_license_evidence(
    current_inputs: tuple[Path, Path, Path],
) -> None:
    lock, evidence, document = current_inputs
    assert freshness.verify_spdx_sbom_freshness(lock, evidence, document) == 121


@pytest.mark.parametrize(
    "mutate",
    [
        lambda doc: doc["packages"][0].__setitem__("versionInfo", "0.0.0"),
        lambda doc: doc["packages"][0].__setitem__("licenseDeclared", "NOASSERTION"),
        lambda doc: doc["relationships"].pop(),
    ],
)
def test_changed_package_license_or_relationship_is_rejected(
    current_inputs: tuple[Path, Path, Path],
    mutate,
) -> None:
    lock, evidence, path = current_inputs
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    _write_document(path, document)
    with pytest.raises(freshness.FreshnessError, match="stale or modified"):
        freshness.verify_spdx_sbom_freshness(lock, evidence, path)


def test_freshness_rejects_a_purl_with_unencoded_identity_delimiters(
    current_inputs: tuple[Path, Path, Path],
) -> None:
    lock, evidence, path = current_inputs
    document = json.loads(path.read_text(encoding="utf-8"))
    package = next(
        row
        for row in document["packages"]
        if any(
            reference.get("referenceLocator", "").startswith("pkg:pypi/")
            for reference in row["externalRefs"]
        )
    )
    purl = next(
        reference
        for reference in package["externalRefs"]
        if reference.get("referenceLocator", "").startswith("pkg:pypi/")
    )
    purl["referenceLocator"] = "pkg:pypi/demo/foo@1.0?x"
    _write_document(path, document)

    with pytest.raises(freshness.FreshnessError, match="stale or modified"):
        freshness.verify_spdx_sbom_freshness(lock, evidence, path)


def test_freshness_rejects_a_valid_but_noncanonical_pypi_version_purl(
    current_inputs: tuple[Path, Path, Path],
) -> None:
    lock, evidence, path = current_inputs
    document = json.loads(path.read_text(encoding="utf-8"))
    package = next(row for row in document["packages"] if row["name"] == "packaging")
    purl = next(
        reference
        for reference in package["externalRefs"]
        if reference.get("referenceLocator", "").startswith("pkg:pypi/")
    )
    purl["referenceLocator"] = f"pkg:pypi/packaging@v{package['versionInfo']}"
    _write_document(path, document)

    with pytest.raises(freshness.FreshnessError, match="stale or modified"):
        freshness.verify_spdx_sbom_freshness(lock, evidence, path)


@pytest.mark.parametrize("input_index", [0, 1])
def test_changed_lock_or_evidence_rejects_old_sbom(
    current_inputs: tuple[Path, Path, Path],
    input_index: int,
) -> None:
    lock, evidence, document = current_inputs
    path = (lock, evidence)[input_index]
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(freshness.FreshnessError, match="stale or modified"):
        freshness.verify_spdx_sbom_freshness(lock, evidence, document)


def test_incomplete_license_evidence_fails_closed(
    current_inputs: tuple[Path, Path, Path],
) -> None:
    lock, evidence, document = current_inputs
    contents = json.loads(evidence.read_text(encoding="utf-8"))
    contents["packages"].pop()
    evidence.write_text(json.dumps(contents), encoding="utf-8")
    with pytest.raises(ValueError, match="evidence missing|package set differs"):
        freshness.verify_spdx_sbom_freshness(lock, evidence, document)


def test_malformed_creation_timestamp_fails_closed(
    current_inputs: tuple[Path, Path, Path],
) -> None:
    lock, evidence, path = current_inputs
    document = json.loads(path.read_text(encoding="utf-8"))
    document["creationInfo"]["created"] = "2026-99-99T00:00:00Z"
    _write_document(path, document)
    with pytest.raises(freshness.FreshnessError, match="timestamp"):
        freshness.verify_spdx_sbom_freshness(lock, evidence, path)


def test_duplicate_spdx_json_keys_are_rejected(
    current_inputs: tuple[Path, Path, Path],
) -> None:
    lock, evidence, path = current_inputs
    path.write_text(
        '{"spdxVersion":"SPDX-2.3","spdxVersion":"SPDX-2.3"}', encoding="utf-8"
    )
    with pytest.raises(freshness.FreshnessError, match="duplicate"):
        freshness.verify_spdx_sbom_freshness(lock, evidence, path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "demo\n::warning:: forged"),
        ("version", "1.0\r::error:: forged"),
        ("name", "demo\u202ehidden"),
        ("version", "1.0\u2066hidden"),
        ("name", "demo/foo"),
        ("version", "1.0?x"),
    ],
)
def test_freshness_cli_rejects_control_or_format_characters_without_echo(
    current_inputs: tuple[Path, Path, Path],
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: str,
) -> None:
    lock, evidence, document = current_inputs
    prefix, package_section = lock.read_text(encoding="utf-8").split("[[package]]", 1)
    old_line = next(
        line for line in package_section.splitlines() if line.startswith(f"{field} = ")
    )
    package_section = package_section.replace(
        old_line,
        f"{field} = {json.dumps(value, ensure_ascii=False)}",
        1,
    )
    lock.write_text(prefix + "[[package]]" + package_section, encoding="utf-8")

    exit_code = freshness.main(
        [
            "--lockfile",
            str(lock),
            "--evidence",
            str(evidence),
            "--document",
            str(document),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "invalid package name or version" in captured.err
    assert "::warning::" not in captured.err and "::error::" not in captured.err
    assert "\u202e" not in captured.err and "\u2066" not in captured.err
    assert len(captured.err.splitlines()) == 1
    assert not any(
        line.startswith(("::warning::", "::error::"))
        for line in captured.err.splitlines()
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "demo/foo"),
        ("version", "1.0?x"),
        ("name", "demo\n::error:: forged"),
    ],
)
def test_freshness_cli_rejects_invalid_evidence_identity_without_echo(
    current_inputs: tuple[Path, Path, Path],
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: str,
) -> None:
    lock, evidence, document = current_inputs
    evidence_document = json.loads(evidence.read_text(encoding="utf-8"))
    evidence_document["packages"][0][field] = value
    _write_document(evidence, evidence_document)

    exit_code = freshness.main(
        [
            "--lockfile",
            str(lock),
            "--evidence",
            str(evidence),
            "--document",
            str(document),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert (
        "License evidence contains an invalid package name or version" in captured.err
    )
    assert value not in captured.err
    assert len(captured.err.splitlines()) == 1
    assert "::error::" not in captured.err


def test_freshness_cli_escapes_multiline_diagnostic(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_with_untrusted_message(*_args, **_kwargs):
        raise ValueError("bad input\n::warning:: forged command")

    monkeypatch.setattr(
        freshness, "verify_spdx_sbom_freshness", fail_with_untrusted_message
    )

    exit_code = freshness.main([])

    diagnostic = capsys.readouterr().err
    assert exit_code == 1
    assert "\\u000a" in diagnostic
    assert "\n::warning::" not in diagnostic
    assert len(diagnostic.splitlines()) == 1
