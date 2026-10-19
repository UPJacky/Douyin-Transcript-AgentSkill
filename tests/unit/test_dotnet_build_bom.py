from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SDK_PIN_FILES = (
    ROOT / "native/windows/capture-pipe/global.json",
    ROOT / "native/windows/wfp-policy-core/global.json",
    ROOT / "native/windows/wfp-policy-native-readback/global.json",
    ROOT / "native/windows/wfp-policy-plan/global.json",
    ROOT
    / "native/windows/wfp-policy-plan/sandbox/b2-launcher/host-runner/lease-job-helper/global.json",
    ROOT / "native/windows/wfp-policy-runtime/global.json",
    ROOT / "scripts/nuget_content_hash/global.json",
)
SCRIPTS_DIR = str(ROOT / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
SPEC = importlib.util.spec_from_file_location(
    "generate_dotnet_build_bom", ROOT / "scripts" / "generate_dotnet_build_bom.py"
)
assert SPEC is not None and SPEC.loader is not None
bom = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bom
SPEC.loader.exec_module(bom)
_real_nuget_content_hash = bom._nuget_content_hash


@pytest.fixture(autouse=True)
def _use_archive_hash_as_test_content_hash(monkeypatch) -> None:
    monkeypatch.setattr(
        bom,
        "_nuget_content_hash",
        lambda package_path, *_args: base64.b64encode(
            hashlib.sha512(package_path.read_bytes()).digest()
        ).decode("ascii"),
    )


def _write(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_sdk_pins_match_ci_without_rolling_forward() -> None:
    for path in SDK_PIN_FILES:
        config = json.loads(path.read_text(encoding="utf-8"))
        assert config["sdk"] == {
            "version": "10.0.401",
            "rollForward": "disable",
            "allowPrerelease": False,
        }

    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert workflow.count('dotnet-version: "10.0.401"') == 2


def test_package_record_binds_lock_metadata_archive_signature_and_verify(
    tmp_path: Path, monkeypatch
) -> None:
    package_id = "Example.Package"
    version = "1.2.3"
    package_root = tmp_path / "packages"
    package_dir = package_root / package_id.casefold() / version
    package_bytes = b"locked package archive"
    signature_bytes = b"detached signature"
    archive_hash = base64.b64encode(hashlib.sha512(package_bytes).digest()).decode(
        "ascii"
    )
    lock_content_hash = archive_hash

    package_path = _write(package_dir / f"{package_id}.{version}.nupkg", package_bytes)
    _write(
        package_dir / ".nupkg.metadata",
        json.dumps({"contentHash": lock_content_hash}).encode("utf-8"),
    )
    _write(
        package_dir / f"{package_id}.{version}.nupkg.sha512",
        archive_hash.encode("ascii"),
    )
    signature_path = _write(package_dir / ".signature.p7s", signature_bytes)
    calls: list[list[str]] = []

    def fake_run(command: list[str], *, cwd: Path, env=None) -> str:
        calls.append(command)
        assert cwd == tmp_path
        return "verified"

    monkeypatch.setattr(bom, "_run", fake_run)
    result = bom._package_record(
        package_root,
        package_id,
        version,
        {
            "type": "Direct",
            "contentHash": lock_content_hash,
            "dependencies": {"Example.Dependency": "4.5.6"},
        },
        "dotnet.exe",
        tmp_path,
    )

    assert result["dependencyType"] == "Direct"
    assert (
        result["nupkg"]["path"] == "example.package/1.2.3/Example.Package.1.2.3.nupkg"
    )
    assert result["nupkg"]["sha256"] == hashlib.sha256(package_bytes).hexdigest()
    assert result["nupkg"]["sha512Base64"] == archive_hash
    assert (
        result["nupkg"]["signatureFile"]["sha256"]
        == hashlib.sha256(signature_bytes).hexdigest()
    )
    assert result["nupkg"]["nugetVerifyAll"]["status"] == "passed"
    assert calls == [["dotnet.exe", "nuget", "verify", "--all", str(package_path)]]
    assert signature_path.is_file()


def test_package_record_rejects_archive_hash_mismatch_before_signature_verification(
    tmp_path: Path, monkeypatch
) -> None:
    package_id = "Example.Package"
    version = "1.2.3"
    package_root = tmp_path / "packages"
    package_dir = package_root / package_id.casefold() / version
    package_bytes = b"locked package archive"
    _write(package_dir / f"{package_id}.{version}.nupkg", package_bytes)
    _write(
        package_dir / ".nupkg.metadata",
        json.dumps({"contentHash": "lock-hash"}).encode("utf-8"),
    )
    _write(package_dir / f"{package_id}.{version}.nupkg.sha512", b"wrong hash")
    _write(package_dir / ".signature.p7s", b"signature")

    def unexpected_run(*_args, **_kwargs):
        raise AssertionError("signature verifier must not run after hash mismatch")

    monkeypatch.setattr(bom, "_run", unexpected_run)
    try:
        bom._package_record(
            package_root,
            package_id,
            version,
            {"type": "Direct", "contentHash": "lock-hash"},
            "dotnet.exe",
            tmp_path,
        )
    except bom.BomError as exc:
        assert "SHA-512 sidecar mismatch" in str(exc)
    else:
        raise AssertionError("expected hash mismatch to fail closed")


def test_package_record_rejects_coordinated_cache_metadata_when_archive_hash_differs(
    tmp_path: Path, monkeypatch
) -> None:
    package_id = "Example.Package"
    version = "1.2.3"
    package_root = tmp_path / "packages"
    package_dir = package_root / package_id.casefold() / version
    package_bytes = b"cached package archive"
    archive_hash = base64.b64encode(hashlib.sha512(package_bytes).digest()).decode(
        "ascii"
    )
    lock_hash = base64.b64encode(
        hashlib.sha512(b"different lockfile package archive").digest()
    ).decode("ascii")
    _write(package_dir / f"{package_id}.{version}.nupkg", package_bytes)
    _write(
        package_dir / ".nupkg.metadata",
        json.dumps({"contentHash": lock_hash}).encode("utf-8"),
    )
    _write(
        package_dir / f"{package_id}.{version}.nupkg.sha512",
        archive_hash.encode("ascii"),
    )
    _write(package_dir / ".signature.p7s", b"signature")

    def unexpected_run(*_args, **_kwargs):
        raise AssertionError("signature verifier must not run after lock hash mismatch")

    monkeypatch.setattr(bom, "_run", unexpected_run)
    with pytest.raises(bom.BomError, match="does not match lock contentHash"):
        bom._package_record(
            package_root,
            package_id,
            version,
            {"contentHash": lock_hash},
            "dotnet.exe",
            tmp_path,
        )


def test_package_record_accepts_when_nuget_content_hash_matches_lock_even_if_archive_hash_differs(
    tmp_path: Path, monkeypatch
) -> None:
    package_id = "Example.Package"
    version = "1.2.3"
    package_root = tmp_path / "packages"
    package_dir = package_root / package_id.casefold() / version
    package_bytes = b"archive bytes whose raw digest differs from NuGet contentHash"
    archive_hash = base64.b64encode(hashlib.sha512(package_bytes).digest()).decode(
        "ascii"
    )
    lock_hash = base64.b64encode(
        hashlib.sha512(b"NuGet canonical package content hash").digest()
    ).decode("ascii")
    assert archive_hash != lock_hash
    package_path = _write(package_dir / f"{package_id}.{version}.nupkg", package_bytes)
    _write(
        package_dir / ".nupkg.metadata",
        json.dumps({"contentHash": lock_hash}).encode("utf-8"),
    )
    _write(
        package_dir / f"{package_id}.{version}.nupkg.sha512",
        archive_hash.encode("ascii"),
    )
    _write(package_dir / ".signature.p7s", b"signature")
    monkeypatch.setattr(bom, "_nuget_content_hash", lambda *_args: lock_hash)
    monkeypatch.setattr(bom, "_run", lambda *_args, **_kwargs: "verified")

    result = bom._package_record(
        package_root,
        package_id,
        version,
        {"type": "Direct", "contentHash": lock_hash},
        "dotnet.exe",
        tmp_path,
    )

    assert result["nupkg"]["sha512Base64"] == archive_hash
    assert result["nupkg"]["lockContentHashMatchesNuGetComputedContentHash"] is True
    assert package_path.is_file()


@pytest.mark.parametrize(
    "helper_output",
    ["not-a-hash", base64.b64encode(b"short").decode("ascii")],
)
def test_nuget_content_hash_rejects_malformed_helper_output(
    tmp_path: Path, monkeypatch, helper_output: str
) -> None:
    monkeypatch.setattr(bom, "_run", lambda *_args, **_kwargs: helper_output)
    with pytest.raises(bom.BomError, match="helper returned"):
        _real_nuget_content_hash(
            tmp_path / "package.nupkg",
            "dotnet.exe",
            tmp_path,
            tmp_path / "hash-helper.dll",
        )


def test_package_record_rejects_malformed_nuget_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    package_id = "Example.Package"
    version = "1.2.3"
    package_root = tmp_path / "packages"
    package_dir = package_root / package_id.casefold() / version
    package_bytes = b"locked package archive"
    archive_hash = base64.b64encode(hashlib.sha512(package_bytes).digest()).decode(
        "ascii"
    )
    _write(package_dir / f"{package_id}.{version}.nupkg", package_bytes)
    _write(package_dir / ".nupkg.metadata", b"[]")
    _write(
        package_dir / f"{package_id}.{version}.nupkg.sha512",
        archive_hash.encode("ascii"),
    )

    monkeypatch.setattr(
        bom, "_run", lambda *_args, **_kwargs: pytest.fail("verify must not run")
    )
    with pytest.raises(bom.BomError, match="metadata is malformed"):
        bom._package_record(
            package_root,
            package_id,
            version,
            {"contentHash": "lock-hash"},
            "dotnet.exe",
            tmp_path,
        )


def test_package_record_rejects_oversized_nuget_metadata_before_reading(
    tmp_path: Path, monkeypatch
) -> None:
    package_id = "Example.Package"
    version = "1.2.3"
    package_root = tmp_path / "packages"
    package_dir = package_root / package_id.casefold() / version
    package_bytes = b"locked package archive"
    archive_hash = base64.b64encode(hashlib.sha512(package_bytes).digest()).decode(
        "ascii"
    )
    _write(package_dir / f"{package_id}.{version}.nupkg", package_bytes)
    _write(
        package_dir / ".nupkg.metadata",
        b" " * (64 * 1024 + 1),
    )
    _write(
        package_dir / f"{package_id}.{version}.nupkg.sha512",
        archive_hash.encode("ascii"),
    )

    monkeypatch.setattr(
        bom, "_run", lambda *_args, **_kwargs: pytest.fail("verify must not run")
    )
    with pytest.raises(bom.BomError, match="exceeds the size limit"):
        bom._package_record(
            package_root,
            package_id,
            version,
            {"contentHash": "lock-hash"},
            "dotnet.exe",
            tmp_path,
        )


def test_lock_inventory_excludes_project_references_from_nuget_packages() -> None:
    lock = {
        "dependencies": {
            "net10.0": {
                "Example.Package": {
                    "type": "Direct",
                    "resolved": "1.2.3",
                    "contentHash": "locked-hash",
                },
                "WfpPolicy.Core": {"type": "Project"},
            }
        }
    }

    result = bom._lock_packages(lock)

    assert [package_id for package_id, _version, _record in result] == [
        "Example.Package"
    ]


def test_lock_inventory_rejects_malformed_project_reference_records() -> None:
    lock = {
        "dependencies": {
            "net10.0": {"WfpPolicy.Core": {"type": "Project", "resolved": "1.0"}}
        }
    }

    with pytest.raises(bom.BomError, match="project dependency record"):
        bom._lock_packages(lock)


def test_source_inventory_uses_repository_relative_paths_without_user_paths() -> None:
    paths = bom._source_inputs(bom.PROJECT_ROOT, bom.REPO_ROOT)
    relative = [bom._relative(path, bom.REPO_ROOT) for path in paths]

    assert "native/windows/wfp-policy-plan/global.json" in relative
    assert "native/windows/wfp-policy-plan/packages.lock.json" in relative
    assert "native/windows/shared/PublicUnicastAddressPolicy.cs" in relative
    assert "native/windows/wfp-policy-core/global.json" in relative
    assert "native/windows/wfp-policy-core/WfpPolicy.Core.csproj" in relative
    assert "native/windows/wfp-policy-core/packages.lock.json" in relative
    assert "native/windows/wfp-policy-core/AssemblyInfo.cs" in relative
    assert "native/windows/wfp-policy-core/LeasePolicyCompiler.cs" in relative
    assert all("Users/" not in path and "Users\\" not in path for path in relative)


def test_runtime_source_inventory_includes_all_locked_projects_without_user_paths() -> (
    None
):
    paths = bom._runtime_source_inputs(bom.REPO_ROOT)
    relative = [bom._relative(path, bom.REPO_ROOT) for path in paths]

    assert "native/windows/wfp-policy-runtime/global.json" in relative
    assert "native/windows/wfp-policy-runtime/packages.lock.json" in relative
    assert "native/windows/wfp-policy-runtime/BaselineCoordinator.cs" in relative
    assert "native/windows/wfp-policy-runtime/WfpNativeObjectProjection.cs" in relative
    assert "native/windows/wfp-policy-runtime/WfpNativeReadbackAdapter.cs" in relative
    assert "native/windows/wfp-policy-runtime/tests/packages.lock.json" in relative
    assert "native/windows/wfp-policy-runtime/tests/Program.cs" in relative
    assert (
        "native/windows/wfp-policy-native-readback/WfpNativeReadbackReader.cs"
        in relative
    )
    assert "native/windows/wfp-policy-native-readback/NativeMethods.txt" in relative
    assert "native/windows/wfp-policy-core/packages.lock.json" in relative
    assert all("Users/" not in path and "Users\\" not in path for path in relative)


def test_project_only_runtime_lock_rejects_an_uninventoried_nuget_package(
    tmp_path: Path,
) -> None:
    lock_path = _write(
        tmp_path / "packages.lock.json",
        json.dumps(
            {
                "version": 1,
                "dependencies": {
                    "net10.0": {
                        "WfpPolicy.Core": {"type": "Project"},
                        "Unexpected.Package": {
                            "type": "Transitive",
                            "resolved": "1.2.3",
                            "contentHash": "hash",
                        },
                    }
                },
            }
        ).encode("utf-8"),
    )

    with pytest.raises(bom.BomError, match="acquired a NuGet package"):
        bom._validate_project_only_lock(lock_path)


def test_json_writer_preserves_regular_output_replacement_semantics(
    tmp_path: Path,
) -> None:
    output = tmp_path / "bom.json"

    bom._write_json(output, {"version": 1})
    bom._write_json(output, {"version": 2})

    assert json.loads(output.read_text(encoding="utf-8")) == {"version": 2}


def test_json_writer_rejects_symlink_destination(tmp_path: Path) -> None:
    target = tmp_path / "outside.json"
    target.write_text("preserve\n", encoding="utf-8")
    output = tmp_path / "bom.json"
    try:
        output.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    with pytest.raises(OSError, match="symbolic link or reparse point"):
        bom._write_json(output, {"version": 1})

    assert target.read_text(encoding="utf-8") == "preserve\n"
