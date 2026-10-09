"""Smoke-test the Skill as an isolated, repository-external installation."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode:
        if result.stdout:
            print(result.stdout, end="", file=sys.stderr)
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        raise SystemExit(result.returncode)
    return result.stdout.strip()


def _smoke_environment(root: Path, copied_skill: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["DOUYIN_TRANSCRIPT_HOME"] = str(root / "app-data")
    env["UV_PROJECT_ENVIRONMENT"] = str(copied_skill / ".venv")
    return env


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    source_skill = repository / "skills" / "douyin-transcript"
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("uv must be installed to run the clean Skill smoke check")

    with tempfile.TemporaryDirectory(
        prefix="douyin-transcript-clean-skill-",
        dir=Path.home(),
    ) as temporary:
        root = Path(temporary)
        copied_skill = root / "skills" / "douyin-transcript"
        copied_skill.parent.mkdir()
        shutil.copytree(
            source_skill,
            copied_skill,
            ignore=shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", ".ruff_cache"),
        )

        env = _smoke_environment(root, copied_skill)

        run([uv, "sync", "--project", str(copied_skill), "--locked", "--no-dev"], cwd=root, env=env)

        imported_path = run(
            [
                uv,
                "run",
                "--project",
                str(copied_skill),
                "--locked",
                "--no-sync",
                "python",
                "-c",
                "import douyin_transcript; print(douyin_transcript.__file__)",
            ],
            cwd=root,
            env=env,
        )
        resolved_import = Path(imported_path).resolve()
        expected_package = (copied_skill / "src" / "douyin_transcript").resolve()
        if not resolved_import.is_relative_to(expected_package):
            raise SystemExit(f"CLI imported outside the copied Skill: {resolved_import}")

        version = run(
            [
                uv,
                "run",
                "--project",
                str(copied_skill),
                "--locked",
                "--no-sync",
                "douyin-transcript",
                "--version",
            ],
            cwd=root,
            env=env,
        )
        if not version:
            raise SystemExit("the copied Skill CLI returned an empty version")

        run(
            [
                uv,
                "run",
                "--project",
                str(copied_skill),
                "--locked",
                "--no-sync",
                "douyin-transcript",
                "transcribe",
                "https://www.douyin.com/video/1234567890123456789",
                "--dry-run",
                "--json",
                "--data-dir",
                str(root / "app-data"),
                "--output-dir",
                str(root / "output"),
            ],
            cwd=root,
            env=env,
        )

        if (root / "app-data").exists() or (root / "output").exists():
            raise SystemExit(
                "the dry-run smoke check created an application data or output directory"
            )

        print(f"Clean Skill installation passed: {version}; import={resolved_import}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
