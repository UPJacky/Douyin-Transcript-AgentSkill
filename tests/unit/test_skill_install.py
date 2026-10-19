from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "check_clean_skill_install.py"
)
_SCRIPT_SPEC = importlib.util.spec_from_file_location(
    "check_clean_skill_install", _SCRIPT_PATH
)
assert _SCRIPT_SPEC is not None and _SCRIPT_SPEC.loader is not None
_SCRIPT_MODULE = importlib.util.module_from_spec(_SCRIPT_SPEC)
_SCRIPT_SPEC.loader.exec_module(_SCRIPT_MODULE)
_smoke_environment = _SCRIPT_MODULE._smoke_environment
_parse_json_object = _SCRIPT_MODULE.parse_json_object
_validate_doctor_report = _SCRIPT_MODULE.validate_doctor_report
_validate_dry_run_report = _SCRIPT_MODULE.validate_dry_run_report
_REPOSITORY = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "relative_path",
    [
        Path("README.md"),
        Path("README_EN.md"),
        Path("skills/douyin-transcript/SKILL.md"),
        Path("skills/douyin-transcript/references/INSTALL.md"),
        Path("skills/douyin-transcript/references/CLI_REFERENCE.md"),
        Path("skills/douyin-transcript/scripts/run.cmd"),
        Path("skills/douyin-transcript/scripts/run.sh"),
    ],
)
def test_cli_invocation_examples_disable_uv_sync(relative_path: Path) -> None:
    contents = (_REPOSITORY / relative_path).read_text(encoding="utf-8")
    invocation_lines = [
        line
        for line in contents.splitlines()
        if "uv run" in line and "--locked" in line
    ]

    assert invocation_lines, f"expected CLI examples in {relative_path}"
    assert all("--no-sync" in line for line in invocation_lines), relative_path


def test_clean_install_uses_venv_inside_copied_skill(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    external_environment = tmp_path / "caller-owned-venv"
    external_environment.mkdir()
    sentinel = external_environment / "keep.txt"
    sentinel.write_text("caller-owned environment", encoding="utf-8")
    root = tmp_path / "clean-root"
    copied_skill = root / "skills" / "douyin-transcript"
    copied_skill.mkdir(parents=True)
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", str(external_environment))

    env = _smoke_environment(root, copied_skill)

    assert Path(env["UV_PROJECT_ENVIRONMENT"]) == copied_skill / ".venv"
    assert Path(env["UV_PROJECT_ENVIRONMENT"]).is_relative_to(copied_skill)
    assert Path(env["DOUYIN_TRANSCRIPT_HOME"]) == root / "app-data"
    assert env["UV_PROJECT_ENVIRONMENT"] != str(external_environment)
    assert os.environ["UV_PROJECT_ENVIRONMENT"] == str(external_environment)
    assert sentinel.read_text(encoding="utf-8") == "caller-owned environment"


def test_clean_install_json_helpers_validate_dry_run_and_setup_required_doctor() -> (
    None
):
    _validate_dry_run_report(
        '{"status":"needs_attention","items":[{"input_status":"valid",'
        '"status":"capture_unavailable",'
        '"error_code":"BROWSER_ISOLATION_UNAVAILABLE"}],'
        '"url_capture":{"status":"unavailable",'
        '"error_code":"BROWSER_ISOLATION_UNAVAILABLE"},"paths":'
        '{"data_dir":{"status":"writable"},"output_dir":{"status":"writable"}}}'
    )
    _validate_doctor_report(
        '{"project":"douyin-transcript","overall":"setup_required",'
        '"checks":{},"capabilities":{"local_transcription":"setup_required"}}'
    )


@pytest.mark.parametrize("stdout", ["", "not-json", "[]"])
def test_clean_install_json_parser_rejects_invalid_objects(stdout: str) -> None:
    with pytest.raises(SystemExit, match="JSON"):
        _parse_json_object(stdout, label="test output")


def test_clean_install_json_helpers_reject_unexpected_statuses() -> None:
    with pytest.raises(SystemExit, match="did not report unavailable URL capture"):
        _validate_dry_run_report('{"status":"ready","items":[],"paths":{}}')
    with pytest.raises(SystemExit, match="must report setup_required"):
        _validate_doctor_report(
            '{"project":"douyin-transcript","overall":"ready",'
            '"checks":{},"capabilities":{"local_transcription":"ready"}}'
        )


@pytest.mark.parametrize(
    ("argv", "expected_exit", "expected_output"),
    [
        (["--help"], 0, "usage:"),
        (["--unknown-option"], 2, "unrecognized arguments: --unknown-option"),
    ],
)
def test_clean_install_arguments_exit_before_install_side_effects(
    argv: list[str],
    expected_exit: int,
    expected_output: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def forbidden(name: str):
        def fail(*args: object, **kwargs: object) -> None:
            calls.append(name)
            raise AssertionError(f"unexpected install side effect: {name}")

        return fail

    monkeypatch.setattr(_SCRIPT_MODULE.shutil, "which", forbidden("find-uv"))
    monkeypatch.setattr(
        _SCRIPT_MODULE.tempfile, "TemporaryDirectory", forbidden("temporary-directory")
    )
    monkeypatch.setattr(_SCRIPT_MODULE.shutil, "copytree", forbidden("copy-skill"))
    monkeypatch.setattr(_SCRIPT_MODULE.subprocess, "run", forbidden("subprocess"))
    monkeypatch.setattr(_SCRIPT_MODULE, "run", forbidden("uv-command"))
    monkeypatch.setattr(
        _SCRIPT_MODULE, "_smoke_environment", forbidden("smoke-environment")
    )

    with pytest.raises(SystemExit) as result:
        _SCRIPT_MODULE.main(argv)

    assert result.value.code == expected_exit
    assert calls == []
    assert list(tmp_path.iterdir()) == []
    captured = capsys.readouterr()
    assert expected_output in (captured.out + captured.err).lower()
