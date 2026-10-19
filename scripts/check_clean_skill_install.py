"""Smoke-test the Skill as an isolated, repository-external installation."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    expected_returncode: int = 0,
) -> str:
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
    if result.returncode != expected_returncode:
        if result.stdout:
            print(result.stdout, end="", file=sys.stderr)
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        raise SystemExit(result.returncode or 1)
    return result.stdout.strip()


def parse_json_object(stdout: str, *, label: str) -> dict[str, object]:
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{label} did not return valid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{label} JSON must be an object")
    return value


def validate_dry_run_report(stdout: str) -> None:
    report = parse_json_object(stdout, label="dry-run")
    items = report.get("items")
    paths = report.get("paths")
    url_capture = report.get("url_capture")
    if report.get("status") != "needs_attention":
        raise SystemExit(
            "the copied Skill dry-run did not report unavailable URL capture"
        )
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise SystemExit("the copied Skill dry-run returned no valid input item")
    if (
        items[0].get("input_status") != "valid"
        or items[0].get("status") != "capture_unavailable"
        or items[0].get("error_code") != "BROWSER_ISOLATION_UNAVAILABLE"
    ):
        raise SystemExit(
            "the copied Skill dry-run did not fail closed for the sample URL"
        )
    if (
        not isinstance(url_capture, dict)
        or url_capture.get("status") != "unavailable"
        or url_capture.get("error_code") != "BROWSER_ISOLATION_UNAVAILABLE"
    ):
        raise SystemExit(
            "the copied Skill dry-run returned an unexpected capture capability"
        )
    if not isinstance(paths, dict) or any(
        not isinstance(paths.get(name), dict) or paths[name].get("status") != "writable"
        for name in ("data_dir", "output_dir")
    ):
        raise SystemExit("the copied Skill dry-run returned invalid path checks")


def validate_doctor_report(stdout: str) -> None:
    report = parse_json_object(stdout, label="doctor --json")
    if report.get("project") != "douyin-transcript":
        raise SystemExit("the copied Skill doctor returned an unexpected project")
    if report.get("overall") != "setup_required":
        raise SystemExit(
            "the dependency-free copied Skill doctor must report setup_required"
        )
    if not isinstance(report.get("checks"), dict):
        raise SystemExit("the copied Skill doctor returned no checks object")
    capabilities = report.get("capabilities")
    if (
        not isinstance(capabilities, dict)
        or capabilities.get("local_transcription") != "setup_required"
    ):
        raise SystemExit("the copied Skill doctor returned invalid capability status")


def _smoke_environment(root: Path, copied_skill: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["DOUYIN_TRANSCRIPT_HOME"] = str(root / "app-data")
    env["UV_PROJECT_ENVIRONMENT"] = str(copied_skill / ".venv")
    return env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test the Skill as an isolated, repository-external installation."
    )
    parser.parse_args(argv)

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
            ignore=shutil.ignore_patterns(
                ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"
            ),
        )

        env = _smoke_environment(root, copied_skill)

        run(
            [uv, "sync", "--project", str(copied_skill), "--locked", "--no-dev"],
            cwd=root,
            env=env,
        )

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
            raise SystemExit(
                f"CLI imported outside the copied Skill: {resolved_import}"
            )

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

        dry_run_output = run(
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
            expected_returncode=2,
        )
        validate_dry_run_report(dry_run_output)

        doctor_output = run(
            [
                uv,
                "run",
                "--project",
                str(copied_skill),
                "--locked",
                "--no-sync",
                "douyin-transcript",
                "doctor",
                "--json",
                "--data-dir",
                str(root / "app-data"),
                "--output-dir",
                str(root / "output"),
            ],
            cwd=root,
            env=env,
            expected_returncode=1,
        )
        validate_doctor_report(doctor_output)

        if (root / "app-data").exists() or (root / "output").exists():
            raise SystemExit(
                "the dry-run smoke check created an application data or output directory"
            )

        print(f"Clean Skill installation passed: {version}; import={resolved_import}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
