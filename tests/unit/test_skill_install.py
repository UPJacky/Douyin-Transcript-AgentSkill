from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_clean_skill_install.py"
_SCRIPT_SPEC = importlib.util.spec_from_file_location("check_clean_skill_install", _SCRIPT_PATH)
assert _SCRIPT_SPEC is not None and _SCRIPT_SPEC.loader is not None
_SCRIPT_MODULE = importlib.util.module_from_spec(_SCRIPT_SPEC)
_SCRIPT_SPEC.loader.exec_module(_SCRIPT_MODULE)
_smoke_environment = _SCRIPT_MODULE._smoke_environment
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
