from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SANDBOX = ROOT / "native" / "windows" / "wfp-policy-plan" / "sandbox"


def _source(name: str) -> str:
    return (SANDBOX / name).read_text(encoding="utf-8")


def _assert_powershell_entrypoint_is_side_effect_free_stub(
    name: str, expected_message: str
) -> None:
    lines = [line.strip() for line in _source(name).splitlines() if line.strip()]

    assert lines == [
        "$ErrorActionPreference = 'Stop'",
        "Set-StrictMode -Version Latest",
        f"throw '{expected_message}'",
    ]


def _assert_parameterized_powershell_entrypoint_is_side_effect_free_stub(
    name: str, expected_message: str
) -> None:
    lines = [line.strip() for line in _source(name).splitlines() if line.strip()]
    throw_line = f"throw '{expected_message}'"
    throw_index = lines.index(throw_line)

    assert lines[0] == "param("
    assert lines[throw_index - 1] == ")"
    assert lines[throw_index:] == [throw_line]


def test_chromium_headless_cleanup_requires_successful_directory_creation() -> None:
    source = _source("ChromiumInteractiveHeadlessSmoke.ps1")

    assert "$workRootCreated = $false" in source
    assert "$workRootCreated = $true" in source
    assert (
        "if ($workRootCreated -and (Test-Path -LiteralPath $workRoot -PathType Container))"
        in source
    )


def test_user_token_smoke_fails_closed_before_host_side_effects() -> None:
    _assert_parameterized_powershell_entrypoint_is_side_effect_free_stub(
        "ChromiumAsUserTokenSmoke.ps1",
        "CreateProcessAsUser Chromium smoke is disabled until a trusted Sandbox guest attestation is implemented.",
    )


def test_desktop_acl_grant_fails_closed_before_acl_changes() -> None:
    _assert_parameterized_powershell_entrypoint_is_side_effect_free_stub(
        "GrantInteractiveDesktopAccess.ps1",
        "Interactive desktop ACL grant is disabled until a trusted Sandbox guest attestation is implemented.",
    )


def test_appcontainer_chromium_cleanup_is_gated_by_created_directories() -> None:
    source = _source("AppContainerIdentitySmoke.ps1")

    assert "$chromiumProfilePathCreated = $false" in source
    assert "$chromiumProfilePathCreated = $true" in source
    assert "$chromiumPackagePathCreated = $false" in source
    assert "$chromiumPackagePathCreated = $true" in source
    assert "$chromiumProfilePathCreated -and $null -ne $chromiumProfilePath" in source
    assert "$chromiumPackagePathCreated -and $null -ne $chromiumPackagePath" in source


def test_user_sid_wfp_smoke_fails_closed_before_account_or_wfp_operations() -> None:
    _assert_powershell_entrypoint_is_side_effect_free_stub(
        "UserSidChromiumSmoke.ps1",
        "User-SID WFP mutation smoke is disabled until the Sandbox guest boundary can be independently authenticated.",
    )


def test_bfe_sandbox_wrapper_and_guest_runner_fail_closed_before_side_effects() -> None:
    _assert_powershell_entrypoint_is_side_effect_free_stub(
        "RunMaterializerBfeSandboxSmoke.ps1",
        "Sandbox BFE mutation probe is disabled until a trusted guest attestation is implemented.",
    )
    _assert_powershell_entrypoint_is_side_effect_free_stub(
        "RunMaterializerBfeProbe.ps1",
        "Sandbox BFE guest runner is disabled; it will not create accounts, start a controller, or open BFE.",
    )


def test_bfe_cmd_entrypoint_is_disabled() -> None:
    lines = [
        line.strip()
        for line in _source("RunMaterializerBfeProbe.cmd").splitlines()
        if line.strip()
    ]

    assert lines == [
        "@echo off",
        "echo Sandbox BFE guest runner is disabled.",
        "exit /b 2",
    ]


def test_process_singleton_lockfile_is_created_exclusively() -> None:
    source = _source("ProcessSingletonApiProbe.ps1")
    lockfile_probe = source.split(
        "public static ProcessSingletonProbeApiResult ProbeLockFile", 1
    )[1]
    lockfile_probe = lockfile_probe.split(
        "public static ProcessSingletonProbeApiResult ProbeMessageWindow", 1
    )[0]

    assert "FileShareRead" in lockfile_probe
    assert "CreateNew" in lockfile_probe
    assert "FileFlagDeleteOnClose" in lockfile_probe
    assert "CreateAlways" not in lockfile_probe
