from __future__ import annotations

import hashlib
import json
import os
import sys
import tomllib
import zipfile
from pathlib import Path
from runpy import run_path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = str(ROOT / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
generator = run_path(str(ROOT / "scripts" / "generate_spdx_sbom.py"))
build_document = generator["build_document"]
valid_expression = generator["_valid_spdx_expression"]
license_evidence_by_package = generator["_license_evidence_by_package"]
pypi_purl = generator["_pypi_purl"]
valid_pypi_identity = generator["_valid_pypi_identity"]


def _fixture(tmp_path: Path, *, file_license: bool = False):
    metadata_path = "demo-1.0.dist-info/METADATA"
    license_path = "demo-1.0.dist-info/licenses/LICENSE"
    artifact_url = "https://files.example/demo-1.0-py3-none-any.whl"
    metadata = b"Metadata-Version: 2.4\nName: demo\nVersion: 1.0\n" + (
        b"\n" if file_license else b"License-Expression: MIT\n\n"
    )
    license_text = b"MIT License fixture\n"
    artifact_path = tmp_path / "demo-1.0-py3-none-any.whl"
    with zipfile.ZipFile(
        artifact_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        archive.writestr(metadata_path, metadata)
        if file_license:
            archive.writestr(license_path, license_text)
    artifact_bytes = artifact_path.read_bytes()
    artifact_digest = hashlib.sha256(artifact_bytes).hexdigest()
    artifact_size = len(artifact_bytes)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / artifact_digest).write_bytes(artifact_bytes)

    lock_path = tmp_path / "uv.lock"
    lock_path.write_text(
        "[[package]]\n"
        'name = "demo"\nversion = "1.0"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
        f'wheels = [{{ url = "{artifact_url}", hash = "sha256:{artifact_digest}", size = {artifact_size} }}]\n\n'
        "[[package]]\n"
        'name = "douyin-transcript"\nversion = "0.1.0"\n'
        'source = { editable = "." }\n',
        encoding="utf-8",
    )
    row = {
        "name": "demo",
        "version": "1.0",
        "artifact_type": "wheel",
        "artifact_url": artifact_url,
        "artifact_sha256": artifact_digest,
        "artifact_size": artifact_size,
        "metadata_path": metadata_path,
        "metadata_sha256": hashlib.sha256(metadata).hexdigest(),
        "metadata_field": None if file_license else "License-Expression",
        "metadata_field_value": None if file_license else "MIT",
        "declared_expression": None if file_license else "MIT",
        "mapped_expression": None,
        "status": "file_verified_declaration"
        if file_license
        else "valid_spdx_declaration",
    }
    if file_license:
        row["license_file"] = {
            "artifact_type": "wheel",
            "artifact_url": artifact_url,
            "artifact_sha256": artifact_digest,
            "artifact_size": artifact_size,
            "path": license_path,
            "sha256": hashlib.sha256(license_text).hexdigest(),
            "expression": "MIT",
        }
    evidence_path = tmp_path / "license-evidence.json"
    evidence_path.write_text(
        json.dumps({"schema_version": 1, "packages": [row]}), encoding="utf-8"
    )
    return lock_path, evidence_path, cache_dir


def test_checked_in_inventory_matches_lock_and_evidence_identity() -> None:
    lock_path = ROOT / "skills" / "douyin-transcript" / "uv.lock"
    evidence_path = ROOT / "docs" / "third-party-license-evidence.json"
    sbom_path = ROOT / "docs" / "third-party-sbom.spdx.json"
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    checked_in = json.loads(sbom_path.read_text(encoding="utf-8"))
    created = checked_in["creationInfo"]["created"]

    expected_packages = {(row["name"], row["version"]) for row in lock["package"]}
    evidence_by_package = {
        (row["name"], row["version"]): row for row in evidence["packages"]
    }
    playwright_evidence = evidence_by_package[("playwright", "1.63.0")]
    npm_components = {
        (component["name"], component["version"]): component
        for sidecar in playwright_evidence["artifact_bound_npm_sidecars"]
        for component in sidecar["packages"]
    }
    expected_packages.update(npm_components)
    actual_packages = {
        (row["name"], row["versionInfo"]) for row in checked_in["packages"]
    }
    assert actual_packages == expected_packages

    generator_digest = hashlib.sha256(
        (ROOT / "scripts" / "generate_spdx_sbom.py").read_bytes()
    ).hexdigest()
    namespace_digest = hashlib.sha256(
        "\0".join(
            (
                hashlib.sha256(lock_path.read_bytes()).hexdigest(),
                hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
                generator_digest,
                created,
            )
        ).encode("utf-8")
    ).hexdigest()
    assert checked_in["documentNamespace"].endswith(namespace_digest)

    for package in checked_in["packages"]:
        if package["primaryPackagePurpose"] == "APPLICATION":
            assert package["licenseDeclared"] == "NOASSERTION"
            assert package["licenseConcluded"] == "NOASSERTION"
            continue
        key = (package["name"], package["versionInfo"])
        if key in npm_components:
            expected = npm_components[key]["license_expression"]
        else:
            row = evidence_by_package[key]
            expected = (
                row.get("declared_expression")
                or row.get("mapped_expression")
                or (row.get("license_file") or {}).get("expression")
                or "NOASSERTION"
            )
        assert package["licenseDeclared"] == expected
        assert package["licenseConcluded"] == "NOASSERTION"

    assert len(playwright_evidence["artifact_members"]) == 63
    playwright_package = next(
        row for row in checked_in["packages"] if row["name"] == "playwright"
    )
    assert "63 additional artifact members" in playwright_package["licenseComments"]
    assert (
        "Node.js and musl MIT notices without versions"
        in playwright_package["licenseComments"]
    )
    npm_records = [
        row
        for row in checked_in["packages"]
        if any(
            ref["referenceLocator"].startswith("pkg:npm/")
            for ref in row["externalRefs"]
        )
    ]
    assert len(npm_records) == 79
    assert (
        sum(
            component["license_basis"] == "license_text"
            for component in npm_components.values()
        )
        == 78
    )
    proxy = next(row for row in npm_records if row["name"] == "proxy-agent-negotiate")
    assert proxy["versionInfo"] == "1.1.0"
    assert "contains no license text" in proxy["licenseComments"]
    assert all(row["licenseConcluded"] == "NOASSERTION" for row in npm_records)

    contains = [
        row
        for row in checked_in["relationships"]
        if row["relationshipType"] == "CONTAINS"
    ]
    assert len(contains) == 79
    assert {row["relatedSpdxElement"] for row in contains} == {
        row["SPDXID"] for row in npm_records
    }
    scoped = next(row for row in npm_records if row["name"] == "@hono/node-server")
    assert (
        scoped["externalRefs"][0]["referenceLocator"]
        == "pkg:npm/%40hono/node-server@1.19.14"
    )


def test_pypi_purl_accepts_locked_editable_and_encoded_pep440_identities() -> None:
    lock_path = ROOT / "skills" / "douyin-transcript" / "uv.lock"
    packages = tomllib.loads(lock_path.read_text(encoding="utf-8"))["package"]

    assert all(valid_pypi_identity(row["name"], row["version"]) for row in packages)
    root = next(row for row in packages if row.get("source", {}).get("editable"))
    assert pypi_purl(root["name"], root["version"]) == (
        "pkg:pypi/douyin-transcript@0.1.0"
    )
    assert pypi_purl("Friendly._--Name", "2!1.0rc1+build.7") == (
        "pkg:pypi/friendly-name@2%211.0rc1%2Bbuild.7"
    )


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("v1.0", "1.0"),
        ("1.0.0", "1.0.0"),
        ("1.0-1", "1.0.post1"),
        ("1.0.post1", "1.0.post1"),
        ("1.0+ABC", "1.0%2Babc"),
        ("1.0alpha", "1.0a0"),
    ],
)
def test_pypi_purl_canonicalizes_pep440_aliases(version: str, expected: str) -> None:
    assert pypi_purl("Demo_Pkg", version) == f"pkg:pypi/demo-pkg@{expected}"


def test_generator_rejects_duplicate_normalized_lock_identities_without_echo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path)
    lock_path.write_text(
        lock_path.read_text(encoding="utf-8")
        + '\n[[package]]\nname = "Demo"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )

    exit_code = generator["main"](
        [
            "--lockfile",
            str(lock_path),
            "--evidence",
            str(evidence_path),
            "--cache-dir",
            str(cache_dir),
            "--output",
            str(tmp_path / "output.spdx.json"),
        ]
    )

    diagnostic = capsys.readouterr().err
    assert exit_code == 1
    assert "duplicate normalized package identities" in diagnostic
    assert "Demo" not in diagnostic and "1.0.0" not in diagnostic
    assert len(diagnostic.splitlines()) == 1


def test_generator_rejects_duplicate_normalized_evidence_identities_without_echo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    duplicate = dict(evidence["packages"][0])
    duplicate["name"] = "Demo"
    duplicate["version"] = "1.0.0"
    evidence["packages"].append(duplicate)
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    exit_code = generator["main"](
        [
            "--lockfile",
            str(lock_path),
            "--evidence",
            str(evidence_path),
            "--cache-dir",
            str(cache_dir),
            "--output",
            str(tmp_path / "output.spdx.json"),
        ]
    )

    diagnostic = capsys.readouterr().err
    assert exit_code == 1
    assert "duplicate normalized package identities" in diagnostic
    assert "Demo" not in diagnostic and "1.0.0" not in diagnostic
    assert len(diagnostic.splitlines()) == 1


def test_playwright_sidecar_evidence_is_artifact_bound_and_canonical() -> None:
    lock_path = ROOT / "skills" / "douyin-transcript" / "uv.lock"
    packages = tomllib.loads(lock_path.read_text(encoding="utf-8"))["package"]
    evidence_path = ROOT / "docs" / "third-party-license-evidence.json"
    mapped, _ = license_evidence_by_package(
        packages, evidence_path.read_bytes(), evidence_path
    )
    playwright = mapped[("playwright", "1.63.0")]
    npm_components = playwright["_validated_bundled_npm_packages"]
    assert len(npm_components) == 79
    assert sum(item["license_basis"] == "license_text" for item in npm_components) == 78
    assert playwright["webp_codec_component_note"]["components"] == [
        {
            "name": "libwebp",
            "version": None,
            "license_expression": "BSD-3-Clause",
            "association": "webp_codec.wasm",
        },
        {
            "name": "Emscripten",
            "version": None,
            "license_expression": "MIT OR NCSA",
            "association": "webp_codec.js glue and runtime",
        },
    ]
    assert (
        "not asserted as direct dependencies"
        in playwright["webp_codec_component_note"]["scope_note"]
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("license_expression", "catalog differs from reviewed evidence"),
        ("member_sha256", "catalog differs from reviewed evidence"),
        ("webp_version", "WebP sidecar note differs from reviewed artifact evidence"),
    ],
)
def test_playwright_sidecar_evidence_rejects_tampering(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    lock_path = ROOT / "skills" / "douyin-transcript" / "uv.lock"
    packages = tomllib.loads(lock_path.read_text(encoding="utf-8"))["package"]
    evidence_path = ROOT / "docs" / "third-party-license-evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    playwright = next(
        row for row in evidence["packages"] if row["name"] == "playwright"
    )
    if mutation == "license_expression":
        playwright["artifact_bound_npm_sidecars"][1]["packages"][0][
            "license_expression"
        ] = "Apache-2.0"
    elif mutation == "member_sha256":
        playwright["artifact_bound_npm_sidecars"][0]["member_sha256"] = "0" * 64
    else:
        playwright["webp_codec_component_note"]["components"][0]["version"] = "1.0.0"
    tampered_path = tmp_path / "tampered-playwright-evidence.json"
    tampered_path.write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        license_evidence_by_package(packages, tampered_path.read_bytes(), tampered_path)


def test_generation_requires_artifact_bytes_and_binds_metadata_declaration(
    tmp_path: Path,
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path)

    document = build_document(
        lock_path,
        artifact_cache_dir=cache_dir,
        license_evidence_path=evidence_path,
        created="2026-10-09T00:00:00Z",
    )

    package = next(row for row in document["packages"] if row["name"] == "demo")
    assert package["licenseDeclared"] == "MIT"


def test_rejects_metadata_digest_that_does_not_match_locked_artifact(
    tmp_path: Path,
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["packages"][0]["metadata_sha256"] = "0" * 64
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(ValueError, match="metadata SHA-256 differs from evidence"):
        build_document(
            lock_path, artifact_cache_dir=cache_dir, license_evidence_path=evidence_path
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("artifact_sha256", "0" * 64),
        ("path", "../outside/LICENSE"),
        ("path", "playwright/driver/\x1bLICENSE"),
    ],
)
def test_supplemental_artifact_members_are_locked_and_path_safe(
    tmp_path: Path, field: str, value: str
) -> None:
    lock = tomllib.loads(
        (ROOT / "skills" / "douyin-transcript" / "uv.lock").read_text()
    )
    packages = lock["package"]
    evidence_path = ROOT / "docs" / "third-party-license-evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    row = next(item for item in evidence["packages"] if item["name"] == "playwright")
    row["artifact_members"][0][field] = value
    tampered = tmp_path / "tampered-evidence.json"
    tampered.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(
        ValueError, match="not pinned by uv.lock|Invalid supplemental artifact member"
    ):
        license_evidence_by_package(packages, tampered.read_bytes(), tampered)


def test_rejects_metadata_value_that_does_not_match_locked_artifact(
    tmp_path: Path,
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["packages"][0]["metadata_field_value"] = "BSD-3-Clause"
    evidence["packages"][0]["declared_expression"] = "BSD-3-Clause"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(
        ValueError, match="Metadata license value differs from evidence"
    ):
        build_document(
            lock_path, artifact_cache_dir=cache_dir, license_evidence_path=evidence_path
        )


def test_file_license_declaration_is_verified_against_artifact_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path, file_license=True)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    license_file = evidence["packages"][0]["license_file"]
    assertion = (
        "demo",
        "1.0",
        "wheel",
        license_file["artifact_sha256"],
        license_file["path"],
        license_file["sha256"],
    )
    reviewed = dict(generator["_REVIEWED_LICENSE_FILE_ASSERTIONS"])
    reviewed[assertion] = ("MIT", None)
    monkeypatch.setitem(
        build_document.__globals__, "_REVIEWED_LICENSE_FILE_ASSERTIONS", reviewed
    )

    document = build_document(
        lock_path, artifact_cache_dir=cache_dir, license_evidence_path=evidence_path
    )

    package = next(row for row in document["packages"] if row["name"] == "demo")
    assert package["licenseDeclared"] == "MIT"
    assert "demo-1.0.dist-info/licenses/LICENSE" in package["licenseComments"]

    evidence["packages"][0]["license_file"]["expression"] = "BSD-3-Clause"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(ValueError, match="Unreviewed license-file evidence"):
        build_document(
            lock_path, artifact_cache_dir=cache_dir, license_evidence_path=evidence_path
        )

    evidence["packages"][0]["license_file"]["expression"] = "MIT"
    evidence["packages"][0]["license_file"]["sha256"] = "0" * 64
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(ValueError, match="license SHA-256 differs from evidence"):
        build_document(
            lock_path, artifact_cache_dir=cache_dir, license_evidence_path=evidence_path
        )


@pytest.mark.parametrize(
    ("field", "changed_value"),
    [
        ("expression", "Apache-2.0"),
        ("review_note", "This altered note changes the SPDX comment."),
    ],
)
def test_checked_in_license_expression_is_bound_to_reviewed_artifact_identity(
    tmp_path: Path,
    field: str,
    changed_value: str,
) -> None:
    lock_path = ROOT / "skills" / "douyin-transcript" / "uv.lock"
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    packages = [
        row for row in lock["package"] if not row.get("source", {}).get("editable")
    ]
    evidence_path = ROOT / "docs" / "third-party-license-evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    onnx = next(row for row in evidence["packages"] if row["name"] == "onnxruntime")
    onnx["license_file"][field] = changed_value
    tampered_path = tmp_path / "tampered-evidence.json"
    tampered_path.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(ValueError, match="Unreviewed license-file evidence"):
        license_evidence_by_package(packages, tampered_path.read_bytes(), tampered_path)


def test_python_dateutil_dual_license_uses_locked_source_license_and_is_pinned(
    tmp_path: Path,
) -> None:
    lock_path = ROOT / "skills" / "douyin-transcript" / "uv.lock"
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    packages = [
        row for row in lock["package"] if not row.get("source", {}).get("editable")
    ]
    evidence_path = ROOT / "docs" / "third-party-license-evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    mapped_by_package, _evidence_bytes = license_evidence_by_package(
        packages, evidence_path.read_bytes(), evidence_path
    )
    mapped = mapped_by_package[("python-dateutil", "2.9.0.post0")]
    assert mapped["license_file"]["expression"] == "BSD-3-Clause"
    assert mapped["license_file"]["artifact_sha256"] == (
        "37dd54208da7e1cd875388217d5e00ebd4179249f90fb72437e91a35459a0ad3"
    )
    assert mapped["license_file"]["sha256"] == (
        "ba00f51a0d92823b5a1cde27d8b5b9d2321e67ed8da9bc163eff96d5e17e577e"
    )

    dateutil = next(
        row for row in evidence["packages"] if row["name"] == "python-dateutil"
    )
    dateutil["license_file"]["expression"] = "Apache-2.0"
    tampered_path = tmp_path / "tampered-dateutil-evidence.json"
    tampered_path.write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(ValueError, match="Unreviewed license-file evidence"):
        license_evidence_by_package(packages, tampered_path.read_bytes(), tampered_path)


@pytest.mark.skipif(sys.platform == "win32", reason="FIFO replacement requires POSIX")
def test_bounded_reader_rejects_fifo_swapped_after_lstat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "input.json"
    path.write_bytes(b"regular input")
    original_open = os.open

    def swap_then_open(candidate, flags, *args, **kwargs):
        if Path(candidate) == path:
            path.unlink()
            os.mkfifo(path)
        return original_open(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(generator["os"], "open", swap_then_open)
    with pytest.raises(ValueError, match="must be a regular file"):
        generator["_read_bounded_bytes"](path, 1024, "Test input")


def test_generation_fails_before_writing_output_without_a_valid_cache(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lock_path, evidence_path, _cache_dir = _fixture(tmp_path)
    missing_cache = tmp_path / "missing-cache"
    output_path = tmp_path / "output.spdx.json"

    exit_code = generator["main"](
        [
            "--lockfile",
            str(lock_path),
            "--evidence",
            str(evidence_path),
            "--cache-dir",
            str(missing_cache),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 1
    assert "artifact cache" in capsys.readouterr().err.lower()
    assert not output_path.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "demo\x1b[31m\r\n::warning:: forged"),
        ("version", "1.0\n::error:: forged"),
        ("name", "demo\u202ehidden"),
        ("version", "1.0\u2066hidden"),
        ("name", "demo/foo"),
        ("version", "1.0?x"),
    ],
)
def test_generator_rejects_control_or_format_characters_in_evidence_identity_without_echo(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: str,
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["packages"][0][field] = value
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")

    exit_code = generator["main"](
        [
            "--lockfile",
            str(lock_path),
            "--evidence",
            str(evidence_path),
            "--cache-dir",
            str(cache_dir),
            "--output",
            str(tmp_path / "output.spdx.json"),
        ]
    )

    captured = capsys.readouterr()
    diagnostic = captured.err
    assert exit_code == 1
    assert captured.out == ""
    assert "invalid package name or version" in diagnostic
    assert "::warning::" not in diagnostic and "::error::" not in diagnostic
    assert "demo" not in diagnostic and "1.0" not in diagnostic
    assert not any(
        line.startswith(("::warning::", "::error::"))
        for line in diagnostic.splitlines()
    )
    assert len(diagnostic.splitlines()) == 1
    assert "\x1b" not in diagnostic and "\r" not in diagnostic


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
def test_generator_rejects_invalid_lock_identity_without_echo(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: str,
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path)
    lock_text = lock_path.read_text(encoding="utf-8")
    package_section = lock_text.split("[[package]]", 1)[1]
    old_value = 'name = "demo"' if field == "name" else 'version = "1.0"'
    new_value = f"{field} = {json.dumps(value, ensure_ascii=False)}"
    assert old_value in package_section
    package_section = package_section.replace(old_value, new_value, 1)
    lock_path.write_text(
        lock_text.split("[[package]]", 1)[0] + "[[package]]" + package_section,
        encoding="utf-8",
    )

    exit_code = generator["main"](
        [
            "--lockfile",
            str(lock_path),
            "--evidence",
            str(evidence_path),
            "--cache-dir",
            str(cache_dir),
            "--output",
            str(tmp_path / "output.spdx.json"),
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


def test_generator_escapes_terminal_controls_in_output_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path)
    output_path = tmp_path / "output\x1b[31m.spdx.json"
    monkeypatch.setitem(
        generator["main"].__globals__, "write_atomic_text", lambda path, _text: path
    )

    exit_code = generator["main"](
        [
            "--lockfile",
            str(lock_path),
            "--evidence",
            str(evidence_path),
            "--cache-dir",
            str(cache_dir),
            "--output",
            str(output_path),
        ]
    )

    diagnostic = capsys.readouterr().out
    assert exit_code == 0
    assert "output\\u001b[31m.spdx.json" in diagnostic
    assert "\x1b" not in diagnostic


def test_generator_rejects_symlink_output_without_touching_target(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path)
    target = tmp_path / "outside.spdx.json"
    target.write_text("preserve\n", encoding="utf-8")
    output_path = tmp_path / "output.spdx.json"
    try:
        output_path.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    exit_code = generator["main"](
        [
            "--lockfile",
            str(lock_path),
            "--evidence",
            str(evidence_path),
            "--cache-dir",
            str(cache_dir),
            "--output",
            str(output_path),
        ]
    )

    diagnostic = capsys.readouterr().err
    assert exit_code == 1
    assert "symbolic link or reparse point" in diagnostic
    assert target.read_text(encoding="utf-8") == "preserve\n"


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("MIT", True),
        ("MIT AND Apache-2.0 OR BSD-3-Clause", True),
        ("(MIT OR Apache-2.0) AND BSD-3-Clause", True),
        ("MIT WITH Apache-2.0", False),
        ("(MIT", False),
        ("(" * 65 + "MIT" + ")" * 65, False),
        (" MIT" + " AND MIT" * 4096, False),
        ("A" * 65_537, False),
    ],
    ids=(
        "simple",
        "precedence",
        "grouped",
        "with-rejected",
        "unclosed",
        "deep",
        "many-tokens",
        "long",
    ),
)
def test_spdx_expression_parser_has_input_and_recursion_budgets(
    expression: str, expected: bool
) -> None:
    assert valid_expression(expression) is expected


def test_evidence_document_has_package_row_budget(tmp_path: Path, monkeypatch) -> None:
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        json.dumps(
            {"schema_version": 1, "packages": [{"name": "demo", "version": "1"}]}
        ),
        encoding="utf-8",
    )
    monkeypatch.setitem(
        license_evidence_by_package.__globals__, "_MAX_EVIDENCE_PACKAGES", 0
    )

    with pytest.raises(ValueError, match="package row limit"):
        license_evidence_by_package(
            [{"name": "demo", "version": "1", "source": {}}],
            evidence_path.read_bytes(),
            evidence_path,
        )


def test_build_rejects_oversized_evidence_before_verification(
    tmp_path: Path, monkeypatch
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path)
    monkeypatch.setitem(
        build_document.__globals__,
        "_MAX_EVIDENCE_FILE_BYTES",
        len(evidence_path.read_bytes()) - 1,
    )

    with pytest.raises(ValueError, match="License evidence document exceeds"):
        build_document(
            lock_path, artifact_cache_dir=cache_dir, license_evidence_path=evidence_path
        )
