from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace

import douyin_transcript.cache as cache
import douyin_transcript.cli as cli
import pytest
from douyin_transcript.asr import TranscriptionResult, TranscriptSegment
from douyin_transcript.cli import _read_url_file, _run_setup, build_parser
from douyin_transcript.corrections import (
    MAX_TERMINOLOGY_DICTIONARY_BYTES,
    CorrectionRule,
)
from douyin_transcript.downloader import MediaFile
from douyin_transcript.models import model_spec
from douyin_transcript.output import ItemResult, make_summary
from douyin_transcript.pipeline import MAX_URL_BATCH_ITEMS, MAX_URL_LENGTH
from douyin_transcript.pipeline import TranscriptionPipeline as RealPipeline
from douyin_transcript.tasks import DEFAULT_STALE_AFTER_SECONDS, TaskStore
from douyin_transcript.urls import ResolvedInput, UnsupportedUrlError


def test_transcribe_accepts_exactly_one_input_form():
    parser = build_parser()
    args = parser.parse_args(["transcribe", "https://www.douyin.com/video/12"])
    assert args.urls == ["https://www.douyin.com/video/12"]


    assert args.file is None and args.input_file is None

    file_args = parser.parse_args(["transcribe", "--file", "urls.txt"])
    assert file_args.file == "urls.txt"
    assert file_args.urls == []

    media_args = parser.parse_args(["transcribe", "--input-file", "voice.wav"])
    assert media_args.input_file == "voice.wav"

    bounded_args = parser.parse_args(
        [
            "transcribe",
            "--input-file",
            "voice.wav",
            "--max-duration-minutes",
            "45",
            "--max-output-segments",
            "5000",
            "--max-output-characters",
            "250000",
        ]
    )
    assert bounded_args.max_duration_minutes == 45
    assert bounded_args.max_output_segments == 5000
    assert bounded_args.max_output_characters == 250000


def test_transcribe_cli_reports_keyboard_interrupt_and_closes_pipeline(
    monkeypatch, tmp_path, capsys
):
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "output"
    instances = []

    class InterruptPipeline:
        def __init__(self, *_args, **_kwargs):
            self.closed = False
            instances.append(self)

        def run_urls(self, _urls, *, title=None):
            raise KeyboardInterrupt

        def close(self):
            self.closed = True

    monkeypatch.setattr(
        cli,
        "resolve_paths",
        lambda **_kwargs: SimpleNamespace(data_dir=data_dir, output_dir=output_dir),
    )
    monkeypatch.setattr(cli, "TranscriptionPipeline", InterruptPipeline)
    monkeypatch.setattr(
        cli,
        "output_directory_permission_status",
        lambda _path: {"status": "ok", "detail": "private"},
    )

    code = cli.main(
        [
            "transcribe",
            "https://www.douyin.com/video/123",
            "--data-dir",
            str(data_dir),
            "--output-dir",
            str(output_dir),
        ]
    )
    captured = capsys.readouterr()

    assert code == 130
    assert captured.err.strip() == "CANCELLED: 操作已取消。"
    assert instances and instances[0].closed


def test_skip_existing_is_explicit_default_and_force_is_mutually_exclusive():
    parser = build_parser()

    default = parser.parse_args(["transcribe", "https://www.douyin.com/video/1"])
    explicit = parser.parse_args(
        ["transcribe", "https://www.douyin.com/video/1", "--skip-existing"]
    )
    force = parser.parse_args(
        ["transcribe", "https://www.douyin.com/video/1", "--force"]
    )

    assert default.skip_existing is True
    assert explicit.skip_existing is True
    assert force.skip_existing is False
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "transcribe",
                "https://www.douyin.com/video/1",
                "--skip-existing",
                "--force",
            ]
        )


def test_url_list_ignores_blank_and_comment_lines(tmp_path):
    source = tmp_path / "urls.txt"
    source.write_text(
        "# note\nhttps://www.douyin.com/video/1\n  \n  # ignored\nhttps://www.douyin.com/video/2\n",
        encoding="utf-8",
    )

    assert _read_url_file(source) == [
        "https://www.douyin.com/video/1",
        "https://www.douyin.com/video/2",
    ]


def test_url_manifest_accepts_50_and_rejects_over_batch_limit(tmp_path):
    accepted = tmp_path / "accepted.txt"
    accepted.write_text(
        "\n".join(f"https://www.douyin.com/video/{index}" for index in range(50)),
        encoding="utf-8",
    )
    assert len(_read_url_file(accepted)) == 50

    oversized = tmp_path / "oversized.txt"
    oversized.write_text(
        "\n".join(
            f"https://www.douyin.com/video/{index}"
            for index in range(MAX_URL_BATCH_ITEMS + 1)
        ),
        encoding="utf-8",
    )
    try:
        _read_url_file(oversized)
    except ValueError as exc:
        assert "最多支持" in str(exc)
    else:
        raise AssertionError("oversized URL manifest should be rejected")


def test_url_manifest_rejects_oversized_file_and_line(tmp_path):
    too_large = tmp_path / "too-large.txt"
    too_large.write_bytes(b"x" * (1024 * 1024 + 1))
    try:
        _read_url_file(too_large)
    except ValueError as exc:
        assert "不得超过" in str(exc)
    else:
        raise AssertionError("oversized URL manifest should be rejected")

    long_line = tmp_path / "long-line.txt"
    long_line.write_text("x" * (MAX_URL_LENGTH + 1), encoding="utf-8")
    try:
        _read_url_file(long_line)
    except ValueError as exc:
        assert "超过" in str(exc)
    else:
        raise AssertionError("oversized URL line should be rejected")


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "mkfifo"), reason="POSIX FIFO")
@pytest.mark.parametrize("input_kind", ["urls", "dictionary"])
def test_cli_file_inputs_reject_fifo_without_blocking(tmp_path, input_kind):
    fifo = tmp_path / "input.fifo"
    os.mkfifo(fifo)
    script = """
import sys
from pathlib import Path
import douyin_transcript.cli as cli
try:
    if sys.argv[1] == 'urls':
        cli._read_url_file(Path(sys.argv[2]))
    else:
        cli._read_correction_dictionary(sys.argv[2])
except ValueError:
    raise SystemExit(0)
raise SystemExit('FIFO was not rejected')
"""

    result = subprocess.run(
        [sys.executable, "-P", "-c", script, input_kind, str(fifo)],
        capture_output=True,
        text=True,
        timeout=2,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_transcribe_rejects_oversized_positional_batch_before_creating_data_dir(
    tmp_path, capsys
):
    data_dir = tmp_path / "not-created-data"
    urls = [f"https://www.douyin.com/video/{index}" for index in range(MAX_URL_BATCH_ITEMS + 1)]

    exit_code = cli.main(["transcribe", *urls, "--data-dir", str(data_dir)])

    assert exit_code == 2
    assert "最多支持" in capsys.readouterr().err
    assert not data_dir.exists()


def test_summary_terminal_output_strips_title_controls(capsys):
    summary = make_summary(
        [ItemResult("success", title="safe\x1b[2J\x07\x7ftext", output_path="out.md")],
        ".",
    )

    cli._print_summary(summary, as_json=False, quiet=False)

    output = capsys.readouterr().out
    assert "\x1b" not in output and "\x07" not in output and "\x7f" not in output
    assert "safe[2Jtext" in output


def test_summary_json_strips_bidi_title_controls(capsys):
    summary = make_summary(
        [ItemResult("success", title="safe\u202eTitle", output_path="out.md")],
        ".",
    )

    cli._print_summary(summary, as_json=True, quiet=False)

    result = json.loads(capsys.readouterr().out)
    assert result["items"][0]["title"] == "safeTitle"
    assert "\u202e" not in result["items"][0]["title"]


def test_status_json_sanitizes_new_and_legacy_task_titles(tmp_path, capsys):
    database = tmp_path / "data" / "tasks.sqlite3"
    with TaskStore(database) as store:
        created = store.create_remote_task(
            "https://www.douyin.com/video/123", "123", title="safe\u202eTitle"
        )
        assert created.title == "safeTitle"
        stored = store._connection.execute(
            "SELECT title FROM tasks WHERE task_id = ?", (created.task_id,)
        ).fetchone()
        assert stored["title"] == "safeTitle"
        store._connection.execute(
            "UPDATE tasks SET title = ? WHERE task_id = ?",
            ("legacy\u202eTitle", created.task_id),
        )

    code = cli.main(["status", "--data-dir", str(database.parent), "--json"])
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert result["tasks"][0]["title"] == "legacyTitle"
    assert "\u202e" not in result["tasks"][0]["title"]


def test_setup_decline_discloses_sources_and_targets_without_side_effects(
    monkeypatch, tmp_path, capsys
):
    data_dir = tmp_path / "data"
    browser_dir = tmp_path / "browser cache"
    monkeypatch.setenv(
        "UV_INDEX_URL", "https://user:secret@packages.example/simple?token=hidden"
    )
    monkeypatch.setenv(
        "PLAYWRIGHT_DOWNLOAD_HOST", "https://user:secret@browser.example/download"
    )
    monkeypatch.setenv(
        "HF_ENDPOINT", "https://model-user:model-secret@hf-mirror.example/api?token=hf-hidden"
    )
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(browser_dir))
    monkeypatch.setattr("builtins.input", lambda _prompt: "no")
    args = argparse.Namespace(
        model="balanced", browser=True, data_dir=str(data_dir), yes=False
    )

    exit_code = _run_setup(args, build_parser())

    assert exit_code == 1
    output = capsys.readouterr().out
    spec = model_spec("balanced")
    assert "已取消" in output
    assert f"{spec.repository}@{spec.revision}" in output
    assert "uv.lock 软件包源：https://pypi.org" in output
    assert "Python 环境目标：" in output and "uv.lock" in output
    assert "uv 自定义源 UV_INDEX_URL：https://packages.example" in output
    assert "Hugging Face 下载端点：https://hf-mirror.example（HF_ENDPOINT 覆盖）" in output
    assert "Chromium 来源：Playwright 下载服务" in output
    assert "Playwright 自定义下载源 PLAYWRIGHT_DOWNLOAD_HOST：https://browser.example" in output
    assert str(browser_dir) in output
    assert "secret" not in output and "hidden" not in output
    assert "model-secret" not in output and "hf-hidden" not in output
    assert not data_dir.exists()


def test_setup_refuses_model_install_when_target_volume_is_low_on_space(
    monkeypatch, tmp_path, capsys
):
    data_dir = tmp_path / "data"
    monkeypatch.setattr(cli.shutil, "which", lambda _name: "uv")
    monkeypatch.setattr(
        cli.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=1024**3, total=2 * 1024**3, used=1024**3),
    )
    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt: pytest.fail("setup must stop before requesting consent"),
    )
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("setup must not invoke uv or Playwright"),
    )
    args = argparse.Namespace(
        model="balanced", browser=False, data_dir=str(data_dir), yes=False
    )

    exit_code = _run_setup(args, build_parser())

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "模型目录" in captured.out and "空间不足" in captured.out
    assert "没有安装依赖" in captured.err
    assert not data_dir.exists()


def test_setup_rechecks_model_volume_after_dependency_install(
    monkeypatch, tmp_path, capsys
):
    disk_checks = 0
    subprocess_calls = []
    download_calls = []

    def disk_usage(_path):
        nonlocal disk_checks
        disk_checks += 1
        free = 4 * 1024**3 if disk_checks <= 4 else 1024**3
        return SimpleNamespace(free=free, total=8 * 1024**3, used=8 * 1024**3 - free)

    def fake_snapshot_download(**kwargs):
        download_calls.append(kwargs)

    fake_hub = ModuleType("huggingface_hub")
    fake_hub.snapshot_download = fake_snapshot_download
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hub)
    monkeypatch.setattr(cli, "ensure_private_directory", lambda _path: None)
    monkeypatch.setattr(cli, "_playwright_browser_path", lambda: tmp_path / "browser")
    monkeypatch.setattr(cli.shutil, "which", lambda _name: "uv")
    monkeypatch.setattr(cli.shutil, "disk_usage", disk_usage)
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda command, **_kwargs: (
            subprocess_calls.append(list(command)) or SimpleNamespace(returncode=0)
        ),
    )
    args = argparse.Namespace(
        model="balanced", browser=True, data_dir=str(tmp_path / "data"), yes=True
    )

    exit_code = _run_setup(args, build_parser())

    captured = capsys.readouterr()
    assert exit_code == 2
    assert len(subprocess_calls) == 2
    assert subprocess_calls[0][:2] == ["uv", "sync"]
    assert subprocess_calls[1][-3:] == ["playwright", "install", "chromium"]
    assert download_calls == []
    assert "模型目录（依赖安装后）" in captured.out
    assert "依赖已安装，模型未下载" in captured.err
    assert disk_checks == 5


@pytest.mark.parametrize("profile", ["balanced", "fast"])
def test_setup_download_uses_profile_pinned_hugging_face_revision(
    monkeypatch, tmp_path, profile
):
    spec = model_spec(profile)
    download_calls = []

    def fake_snapshot_download(*, repo_id, revision, local_dir):
        download_calls.append((repo_id, revision, local_dir))
        destination = tmp_path / "data" / "models" / spec.size
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "model.bin").write_bytes(b"test weights")
        (destination / "config.json").write_text('{"model_type":"whisper"}', encoding="utf-8")
        (destination / "tokenizer.json").write_text('{"version":"1.0"}', encoding="utf-8")

    fake_hub = ModuleType("huggingface_hub")
    fake_hub.snapshot_download = fake_snapshot_download
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hub)
    monkeypatch.setattr(cli, "ensure_private_directory", lambda _path: None)
    monkeypatch.setattr(cli.shutil, "which", lambda _name: "uv")
    monkeypatch.setattr(
        cli.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(
            free=4 * 1024**3, total=8 * 1024**3, used=4 * 1024**3
        ),
    )
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
    )

    args = argparse.Namespace(
        model=profile, browser=False, data_dir=str(tmp_path / "data"), yes=True
    )
    exit_code = _run_setup(args, build_parser())

    assert exit_code == 0
    assert download_calls == [
        (spec.repository, spec.revision, str(tmp_path / "data" / "models" / spec.size))
    ]
    provenance_path = (
        tmp_path / "data" / "models" / spec.size / ".douyin-transcript-model.json"
    )
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    assert provenance["repository"] == spec.repository
    assert provenance["revision"] == spec.revision
    assert set(provenance["files"]) == {
        "model.bin",
        "config.json",
        "tokenizer.json",
    }


def test_setup_preserves_previously_installed_optional_extras(
    monkeypatch, tmp_path
):
    commands = []
    monkeypatch.setattr(cli.shutil, "which", lambda _name: "uv")
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda command, **_kwargs: (
            commands.append(list(command)) or SimpleNamespace(returncode=0)
        ),
    )
    args = argparse.Namespace(
        model=None, browser=True, data_dir=str(tmp_path / "data"), yes=True
    )

    exit_code = _run_setup(args, build_parser())

    assert exit_code == 0
    assert "--inexact" in commands[0]
    assert "--extra" in commands[0] and "browser" in commands[0]
    assert commands[1] == [sys.executable, "-P", "-m", "playwright", "install", "chromium"]


def test_quiet_summary_keeps_counts_and_failure_codes(capsys, tmp_path):
    summary = cli.make_summary(
        [
            cli.ItemResult("success", output_path=str(tmp_path / "one.md")),
            cli.ItemResult("skipped", output_path=str(tmp_path / "two.md")),
            cli.ItemResult("failed", error_code="DOWNLOAD_FAILED", hint="retry later"),
        ],
        tmp_path,
    )

    cli._print_summary(summary, as_json=False, quiet=True)

    captured = capsys.readouterr()
    assert str(tmp_path / "one.md") in captured.out
    assert "total=3 success=1 skipped=1 failed=1" in captured.out
    assert "DOWNLOAD_FAILED" in captured.err
    assert str(tmp_path / "two.md") not in captured.out


def test_transcribe_cli_has_bounded_dry_run_download_and_retry_options():
    args = build_parser().parse_args(
        ["transcribe", "https://www.douyin.com/video/12", "--dry-run",
         "--max-downloads", "1", "--retry", "0",
         "--processing-timeout-seconds", "900"]
    )
    assert args.dry_run is True
    assert args.max_downloads == 1
    assert args.retry == 0
    assert args.processing_timeout_seconds == 900
    retry_args = build_parser().parse_args(["retry-failed"])
    assert retry_args.processing_timeout_seconds is None


def test_terminology_dictionary_cli_loads_explicit_json_whitelist(tmp_path):
    dictionary = tmp_path / "terms.json"
    dictionary.write_text(
        json.dumps(
            [{"id": "acos", "source": "ACoS", "replacement": "ACoS 指标"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rules = cli._read_correction_dictionary(str(dictionary))

    assert len(rules) == 1
    assert rules[0].rule_id == "acos"
    assert rules[0].source == "ACoS"
    assert rules[0].replacement == "ACoS 指标"


def test_terminology_dictionary_cli_reads_only_the_configured_byte_limit(tmp_path):
    dictionary = tmp_path / "oversized-terms.json"
    dictionary.write_bytes(b" " * (MAX_TERMINOLOGY_DICTIONARY_BYTES + 1))

    with pytest.raises(ValueError, match="256 KiB"):
        cli._read_correction_dictionary(str(dictionary))


def test_dry_run_parses_input_and_checks_paths_without_creating_them(
    monkeypatch, tmp_path, capsys
):
    data_dir = tmp_path / "not-created-data"
    output_dir = tmp_path / "not-created-output"
    monkeypatch.setattr(
        cli,
        "resolve_input",
        lambda _value: ResolvedInput(
            "https://www.douyin.com/video/12",
            "https://www.douyin.com/video/12",
            "12",
            "direct",
        ),
    )
    monkeypatch.setattr(
        cli,
        "TranscriptionPipeline",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("pipeline started")),
    )
    monkeypatch.setattr(
        cli,
        "output_directory_permission_status",
        lambda _path: {"status": "unsafe", "detail": "shared ACL"},
    )

    exit_code = cli.main(
        [
            "transcribe",
            "https://www.douyin.com/video/12",
            "--dry-run",
            "--json",
            "--data-dir",
            str(data_dir),
            "--output-dir",
            str(output_dir),
        ]
    )

    result = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert result["status"] == "ready"
    assert result["items"][0]["video_id"] == "12"
    assert result["paths"]["data_dir"]["status"] == "writable"
    assert result["output_dir_permissions"] == {
        "status": "unsafe",
        "directories": [
            {
                "path": str(output_dir.resolve()),
                "status": "unsafe",
                "detail": "shared ACL",
            }
        ],
    }
    assert not data_dir.exists()
    assert not output_dir.exists()


def test_doctor_accepts_output_dir_override(monkeypatch, capsys, tmp_path):
    selected = tmp_path / "selected-output"
    calls = []

    def collect_report(**kwargs):
        calls.append(kwargs)
        return {
            "overall": "setup_required",
            "checks": {},
            "data_dir": "data",
            "output_dir": str(selected),
        }

    monkeypatch.setattr(cli, "collect_report", collect_report)

    code = cli.main(["doctor", "--output-dir", str(selected), "--json"])

    assert code == 1
    assert calls == [
        {
            "data_dir_override": None,
            "profile": "balanced",
            "output_dir_override": str(selected),
        }
    ]
    assert json.loads(capsys.readouterr().out)["output_dir"] == str(selected)


def test_transcribe_json_reports_actual_output_directory_permissions_before_run(
    monkeypatch, tmp_path, capsys
):
    media = tmp_path / "spoken.wav"
    media.write_bytes(b"fixture")
    output_dir = tmp_path / "shared-output"
    checks = []

    def permission_status(path):
        checks.append(Path(path))
        return {"status": "unsafe", "detail": "shared ACL"}

    class StubPipeline:
        def __init__(self, paths, **_kwargs):
            assert checks == [output_dir.resolve()]
            assert paths.output_dir == output_dir.resolve()

        def run_local(self, _path, *, title=None):
            return ItemResult("success", title=title, output_path=str(output_dir / "spoken.md"))

        def close(self):
            pass

    monkeypatch.setattr(cli, "output_directory_permission_status", permission_status)
    monkeypatch.setattr(cli, "TranscriptionPipeline", StubPipeline)

    code = cli.main(
        [
            "transcribe",
            "--input-file",
            str(media),
            "--data-dir",
            str(tmp_path / "data"),
            "--output-dir",
            str(output_dir),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert code == 0
    assert result["output_dir_permissions"] == {
        "status": "unsafe",
        "directories": [
            {
                "path": str(output_dir.resolve()),
                "status": "unsafe",
                "detail": "shared ACL",
            }
        ],
    }
    assert captured.err == ""


def test_transcribe_text_reports_shared_output_directory(monkeypatch, tmp_path, capsys):
    media = tmp_path / "spoken.wav"
    media.write_bytes(b"fixture")
    output_dir = tmp_path / "shared-output"

    class StubPipeline:
        def __init__(self, *_args, **_kwargs):
            pass

        def run_local(self, _path, *, title=None):
            return ItemResult("success", title=title, output_path=str(output_dir / "spoken.md"))

        def close(self):
            pass

    monkeypatch.setattr(
        cli,
        "output_directory_permission_status",
        lambda _path: {"status": "unsafe", "detail": "shared ACL"},
    )
    monkeypatch.setattr(cli, "TranscriptionPipeline", StubPipeline)

    code = cli.main(
        [
            "transcribe",
            "--input-file",
            str(media),
            "--data-dir",
            str(tmp_path / "data"),
            "--output-dir",
            str(output_dir),
        ]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "OUTPUT_DIR_PERMISSIONS: unsafe" in captured.err
    assert str(output_dir.resolve()) in captured.err


def test_cache_cleanup_defaults_to_preview_and_protects_referenced_media(
    tmp_path, capsys
):
    data_dir = tmp_path / "data"
    cache_dir = data_dir / "media-cache"
    cache_dir.mkdir(parents=True)
    protected = cache_dir / f"1-audio-{'a' * 16}.m4a"
    removable = cache_dir / f"2-audio-{'b' * 16}.m4a"
    protected.write_bytes(b"active")
    removable.write_bytes(b"old")
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        store.create_remote_task("https://www.douyin.com/video/1", "1")
        claimed = store.claim_task("1", "worker")
        store.transition(
            "1", "downloading", worker_id="worker",
            claim_generation=claimed.claim_generation,
        )
        store.transition(
            "1", "downloaded", worker_id="worker",
            claim_generation=claimed.claim_generation, media_path=protected
        )

    preview_code = cli.main(
        ["cache", "clean", "--data-dir", str(data_dir), "--max-bytes", "0", "--json"]
    )
    preview = json.loads(capsys.readouterr().out)

    assert preview_code == 0
    assert preview["dry_run"] is True
    assert preview["selected_paths"] == [str(removable)]
    assert protected.is_file() and removable.is_file()

    apply_code = cli.main(
        [
            "cache", "clean", "--data-dir", str(data_dir), "--max-bytes", "0",
            "--apply", "--json",
        ]
    )
    applied = json.loads(capsys.readouterr().out)
    assert apply_code == 0
    assert applied["removed_paths"] == [str(removable)]
    assert protected.is_file() and not removable.exists()


def test_cache_cleanup_preview_does_not_create_task_database(tmp_path, capsys):
    data_dir = tmp_path / "data"
    cache_dir = data_dir / "media-cache"
    cache_dir.mkdir(parents=True)
    old_media = cache_dir / f"1-audio-{'a' * 16}.m4a"
    old_media.write_bytes(b"old")

    code = cli.main(
        ["cache", "clean", "--data-dir", str(data_dir), "--max-bytes", "0", "--json"]
    )
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert result["dry_run"] is True
    assert result["selected_paths"] == [str(old_media)]
    assert not (data_dir / "tasks.sqlite3").exists()


def test_cache_age_cleanup_protects_live_download_partial_file(tmp_path, capsys):
    data_dir = tmp_path / "data"
    cache_dir = data_dir / "media-cache"
    cache_dir.mkdir(parents=True)
    active_part = cache_dir / f".123-audio-{'c' * 32}.part"
    stale_part = cache_dir / f".456-audio-{'d' * 32}.part"
    active_part.write_bytes(b"active partial")
    stale_part.write_bytes(b"stale partial")
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        store.create_remote_task("https://www.douyin.com/video/123", "123")
        claimed = store.claim_task("123", "worker")
        store.transition(
            "123", "downloading", worker_id="worker",
            claim_generation=claimed.claim_generation,
        )

    code = cli.main(
        [
            "cache", "clean", "--data-dir", str(data_dir), "--max-age-hours", "0",
            "--apply", "--json",
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert active_part.is_file()
    assert not stale_part.exists()
    assert result["removed_paths"] == [str(stale_part)]


def test_cache_clean_rechecks_task_claim_before_removing_partial(
    tmp_path, capsys, monkeypatch
):
    data_dir = tmp_path / "data"
    cache_dir = data_dir / "media-cache"
    cache_dir.mkdir(parents=True)
    database = data_dir / "tasks.sqlite3"
    partial = cache_dir / f".123-audio-{'f' * 32}.part"
    task_ready_to_claim = threading.Event()
    with TaskStore(database) as store:
        store.create_remote_task("https://www.douyin.com/video/123", "123")

    def claim_and_start_download():
        task_ready_to_claim.set()
        with TaskStore(database) as store:
            claimed = store.claim_task("123", "late-worker")
            assert claimed is not None
            store.transition(
                "123", "downloading", worker_id="late-worker",
                claim_generation=claimed.claim_generation,
            )
        partial.write_bytes(b"download starts after cleanup")
        # Keep the cache entry unambiguously eligible for max-age=0 cleanup;
        # the claim guard, not timestamp resolution, must protect it.
        os.utime(partial, (1, 1))

    real_cleanup = cli.cleanup_media_cache
    with ThreadPoolExecutor(max_workers=1) as executor:
        claim_future = None

        def cleanup_with_racing_claim(*args, **kwargs):
            nonlocal claim_future
            claim_future = executor.submit(claim_and_start_download)
            assert task_ready_to_claim.wait(timeout=2)
            claim_future.result(timeout=5)
            return real_cleanup(*args, **kwargs)

        monkeypatch.setattr(cli, "cleanup_media_cache", cleanup_with_racing_claim)
        code = cli.main(
            [
                "cache", "clean", "--data-dir", str(data_dir), "--max-age-hours", "0",
                "--apply", "--json",
            ]
        )
        assert claim_future is not None
        claim_future.result(timeout=5)

    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert partial.is_file()
    assert result["removed_paths"] == []
    assert result["skipped_paths"] == [str(partial)]


def test_cache_clean_releases_task_write_lock_between_file_deletions(
    tmp_path, capsys, monkeypatch
):
    data_dir = tmp_path / "data"
    cache_dir = data_dir / "media-cache"
    cache_dir.mkdir(parents=True)
    database = data_dir / "tasks.sqlite3"
    first = cache_dir / f"123-audio-{'a' * 16}.m4a"
    second = cache_dir / f"456-audio-{'b' * 16}.m4a"
    first.write_bytes(b"old first")
    second.write_bytes(b"old second")
    os.utime(first, (1, 1))
    os.utime(second, (2, 2))
    with TaskStore(database):
        pass

    real_cleanup = cli.cleanup_media_cache
    writer_completed = threading.Event()
    writer_future = None
    with ThreadPoolExecutor(max_workers=1) as executor:
        def create_task_between_deletes():
            with TaskStore(database) as store:
                store.create_remote_task(
                    "https://www.douyin.com/video/789", "789"
                )
            writer_completed.set()

        def cleanup_with_writer_between_entries(*args, **kwargs):
            coordinator = kwargs["deletion_coordinator"]
            deletions = 0

            def release_and_write(entry, unlink):
                nonlocal deletions, writer_future
                removed = coordinator(entry, unlink)
                deletions += 1
                if deletions == 1:
                    writer_future = executor.submit(create_task_between_deletes)
                    assert writer_completed.wait(timeout=2)
                return removed

            kwargs["deletion_coordinator"] = release_and_write
            return real_cleanup(*args, **kwargs)

        monkeypatch.setattr(cli, "cleanup_media_cache", cleanup_with_writer_between_entries)
        code = cli.main(
            [
                "cache", "clean", "--data-dir", str(data_dir), "--max-age-hours", "0",
                "--apply", "--json",
            ]
        )
        assert writer_future is not None
        writer_future.result(timeout=5)

    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert not first.exists() and not second.exists()
    assert result["removed_paths"] == [str(first), str(second)]


def test_cache_clean_winning_single_file_race_finishes_before_new_claim(
    tmp_path, capsys, monkeypatch
):
    data_dir = tmp_path / "data"
    cache_dir = data_dir / "media-cache"
    cache_dir.mkdir(parents=True)
    database = data_dir / "tasks.sqlite3"
    partial = cache_dir / f".123-audio-{'d' * 32}.part"
    partial.write_bytes(b"stale partial")
    os.utime(partial, (1, 1))
    with TaskStore(database) as store:
        store.create_remote_task("https://www.douyin.com/video/123", "123")

    unlink_entered = threading.Event()
    allow_unlink = threading.Event()
    claim_started = threading.Event()
    claim_finished = threading.Event()
    real_unlink = cache._unlink_if_unchanged

    def blocked_unlink(root, entry):
        unlink_entered.set()
        assert allow_unlink.wait(timeout=5)
        return real_unlink(root, entry)

    monkeypatch.setattr(cache, "_unlink_if_unchanged", blocked_unlink)

    def claim_and_start_new_download():
        claim_started.set()
        with TaskStore(database) as store:
            claimed = store.claim_task("123", "next-worker")
            assert claimed is not None
            store.transition(
                "123", "downloading", worker_id="next-worker",
                claim_generation=claimed.claim_generation,
            )
        partial.write_bytes(b"new download partial")
        claim_finished.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        cleanup_future = executor.submit(
            cli.main,
            [
                "cache", "clean", "--data-dir", str(data_dir), "--max-age-hours", "0",
                "--apply", "--json",
            ],
        )
        assert unlink_entered.wait(timeout=2)
        claim_future = executor.submit(claim_and_start_new_download)
        assert claim_started.wait(timeout=2)
        assert not claim_finished.wait(timeout=0.1)
        allow_unlink.set()
        code = cleanup_future.result(timeout=5)
        claim_future.result(timeout=5)

    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert claim_finished.is_set()
    assert partial.read_bytes() == b"new download partial"
    assert result["removed_paths"] == [str(partial)]


def test_cache_clean_preserves_completed_local_source_matching_cache_name(
    tmp_path, capsys
):
    data_dir = tmp_path / "data"
    cache_dir = data_dir / "media-cache"
    cache_dir.mkdir(parents=True)
    source = cache_dir / f"123-audio-{'c' * 16}.m4a"
    source.write_bytes(b"the user's original media")
    os.utime(source, (1, 1))
    database = data_dir / "tasks.sqlite3"
    with TaskStore(database) as store:
        task = store.create_local_task(source)
        store._connection.execute(
            "UPDATE tasks SET state = 'completed', completed_at = ? WHERE task_id = ?",
            (datetime.now(UTC).isoformat(), task.task_id),
        )

    code = cli.main(
        [
            "cache", "clean", "--data-dir", str(data_dir), "--max-age-hours", "0",
            "--apply", "--json",
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert source.is_file()
    assert result["selected_paths"] == []
    assert result["removed_paths"] == []


def test_cache_age_cleanup_removes_partial_after_stale_claim_recovery(
    tmp_path, capsys
):
    data_dir = tmp_path / "data"
    cache_dir = data_dir / "media-cache"
    cache_dir.mkdir(parents=True)
    partial = cache_dir / f".123-audio-{'e' * 32}.part"
    partial.write_bytes(b"abandoned partial")
    stale_claim = datetime.now(UTC) - timedelta(seconds=DEFAULT_STALE_AFTER_SECONDS + 1)
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        store.create_remote_task("https://www.douyin.com/video/123", "123")
        claimed = store.claim_task("123", "worker")
        store.transition(
            "123", "downloading", worker_id="worker",
            claim_generation=claimed.claim_generation,
        )
        store._connection.execute(
            "UPDATE tasks SET claimed_at = ? WHERE task_id = ?",
            (stale_claim.isoformat(timespec="milliseconds"), "123"),
        )
        store.recover_interrupted(stale_after_seconds=DEFAULT_STALE_AFTER_SECONDS)

    code = cli.main(
        [
            "cache", "clean", "--data-dir", str(data_dir), "--max-age-hours", "0",
            "--apply", "--json",
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert not partial.exists()
    assert result["removed_paths"] == [str(partial)]


def test_retry_failed_restores_original_processing_options_and_hides_transcript(
    tmp_path, capsys, monkeypatch
):
    media = tmp_path / "spoken.wav"
    media.write_bytes(b"fixture media")
    data_dir = tmp_path / "private-data"
    original_output = tmp_path / "original-output"
    dictionary = tmp_path / "terms.json"
    dictionary.write_text(
        json.dumps(
            [{"id": "brand", "source": "ASR词", "replacement": "标准词"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    factory_calls = 0
    factory_options = []
    transcribe_languages = []
    pipeline_options = []

    class StubASR:
        def transcribe(self, _path: Path, *, language: str) -> TranscriptionResult:
            transcribe_languages.append(language)
            return TranscriptionResult(
                (TranscriptSegment(0.0, 2.0, "ASR词 秘密逐字稿正文"),),
                12.0,
                "zh",
                "test-model",
                "balanced",
            )

    def asr_factory(_data_dir, _profile, **kwargs):
        nonlocal factory_calls
        factory_calls += 1
        factory_options.append(kwargs)
        if factory_calls == 1:
            raise RuntimeError("temporary model startup failure")
        return StubASR()

    def pipeline_factory(paths, **kwargs):
        pipeline_options.append(kwargs)
        return RealPipeline(
            paths,
            media_validator=lambda path: MediaFile(Path(path), "wav", 13, 12.0),
            asr_factory=asr_factory,
            **kwargs,
        )

    permission_checks = []

    def output_permission_status(path):
        permission_checks.append(Path(path))
        return {"status": "unsafe", "detail": "shared snapshot ACL"}

    monkeypatch.setattr(cli, "output_directory_permission_status", output_permission_status)
    monkeypatch.setattr(cli, "TranscriptionPipeline", pipeline_factory)
    first_code = cli.main(
        [
            "transcribe",
            "--input-file",
            str(media),
            "--data-dir",
            str(data_dir),
            "--output-dir",
            str(original_output),
            "--language",
            "auto",
            "--timestamps",
            "--max-duration-minutes",
            "3.5",
            "--max-output-segments",
            "45",
            "--max-output-characters",
            "123",
            "--max-downloads",
            "1",
            "--retry",
            "0",
            "--processing-timeout-seconds",
            "900",
            "--terminology-dictionary",
            str(dictionary),
            "--json",
        ]
    )
    first_output = capsys.readouterr()
    assert first_code == 5
    assert "秘密逐字稿正文" not in first_output.out + first_output.err

    with TaskStore(data_dir / "tasks.sqlite3") as store:
        failed = store.list_tasks(states=("failed",))[0]
        snapshot = json.loads(failed.processing_options_json)
        assert snapshot == {
            "schema_version": 2,
            "language": "auto",
            "timestamps": True,
            "max_processing_seconds": 900,
            "max_media_duration_seconds": 210.0,
            "max_output_segments": 45,
            "max_output_characters": 123,
            "max_downloads": 1,
            "retries": 0,
            "correction_rules_enabled": True,
            "correction_rules": [
                {"rule_id": "brand", "source": "ASR词", "replacement": "标准词", "note": ""}
            ],
            "output_dir": str(original_output.resolve()),
        }

    retry_code = cli.main(
        ["retry-failed", "--data-dir", str(data_dir), "--json"]
    )
    retry_output = capsys.readouterr()
    result = json.loads(retry_output.out)
    assert retry_code == 0
    assert result["output_dir"] == str(original_output.resolve())
    assert result["output_dir_permissions"] == {
        "status": "unsafe",
        "directories": [
            {
                "path": str(original_output.resolve()),
                "status": "unsafe",
                "detail": "shared snapshot ACL",
            }
        ],
    }
    assert original_output.resolve() in permission_checks
    assert transcribe_languages == ["auto"]
    assert pipeline_options[1] == {
        "profile": "balanced",
        "language": "auto",
        "timestamps": True,
        "max_media_duration_seconds": 210.0,
        "max_output_segments": 45,
        "max_output_characters": 123,
        "max_downloads": 1,
        "retries": 0,
        "max_processing_seconds": 900,
        "correction_rules": (CorrectionRule("brand", "ASR词", "标准词"),),
        "corrections_enabled": True,
    }
    assert factory_options[1] == {
        "max_media_duration_seconds": 210.0,
        "max_output_segments": 45,
        "max_output_characters": 123,
    }
    assert Path(result["items"][0]["output_path"]).parent == original_output.resolve()
    output_path = Path(result["items"][0]["output_path"])
    assert "标准词 秘密逐字稿正文" in output_path.read_text(encoding="utf-8")
    timeline_path = output_path.with_name(f"{output_path.stem}_timeline.md")
    assert timeline_path.is_file()
    assert "秘密逐字稿正文" not in retry_output.out + retry_output.err
    assert "LEGACY_CONFIG" not in retry_output.err
    assert "秘密逐字稿正文".encode() not in (data_dir / "tasks.sqlite3").read_bytes()


def test_force_failure_retry_uses_latest_attempt_snapshot(tmp_path, capsys, monkeypatch):
    media = tmp_path / "spoken.wav"
    media.write_bytes(b"fixture media")
    data_dir = tmp_path / "private-data"
    first_output = tmp_path / "first-output"
    forced_output = tmp_path / "forced-output"
    asr_calls = 0
    asr_profiles = []
    pipeline_options = []

    class StubASR:
        def transcribe(self, _path: Path, *, language: str) -> TranscriptionResult:
            return TranscriptionResult(
                (TranscriptSegment(0.0, 2.0, f"成功-{language}"),),
                12.0,
                "zh",
                "test-model",
                "fast",
            )

    def asr_factory(_data_dir, profile, **_kwargs):
        nonlocal asr_calls
        asr_calls += 1
        asr_profiles.append(profile)
        if asr_calls == 2:
            raise RuntimeError("forced attempt startup failure")
        return StubASR()

    def pipeline_factory(paths, **kwargs):
        pipeline_options.append(kwargs)
        return RealPipeline(
            paths,
            media_validator=lambda path: MediaFile(Path(path), "wav", 13, 12.0),
            asr_factory=asr_factory,
            **kwargs,
        )

    monkeypatch.setattr(cli, "TranscriptionPipeline", pipeline_factory)
    first_code = cli.main(
        [
            "transcribe", "--input-file", str(media), "--data-dir", str(data_dir),
            "--output-dir", str(first_output), "--json",
        ]
    )
    capsys.readouterr()
    assert first_code == 0

    forced_code = cli.main(
        [
            "transcribe", "--input-file", str(media), "--data-dir", str(data_dir),
            "--output-dir", str(forced_output), "--profile", "fast",
            "--language", "auto", "--timestamps", "--force", "--json",
        ]
    )
    capsys.readouterr()
    assert forced_code == 5
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        failed = store.list_tasks(states=("failed",))[0]
        assert failed.profile == "fast"
        assert json.loads(failed.processing_options_json)["language"] == "auto"
        assert json.loads(failed.processing_options_json)["timestamps"] is True
        assert json.loads(failed.processing_options_json)["output_dir"] == str(
            forced_output.resolve()
        )

    retry_code = cli.main(["retry-failed", "--data-dir", str(data_dir), "--json"])
    retry_output = json.loads(capsys.readouterr().out)

    assert retry_code == 0
    assert asr_profiles == ["balanced", "fast", "fast"]
    assert pipeline_options[-1]["language"] == "auto"
    assert pipeline_options[-1]["timestamps"] is True
    assert Path(retry_output["items"][0]["output_path"]).parent == forced_output.resolve()
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        completed = store.list_tasks(states=("completed",))[0]
        assert completed.profile == "fast"
        assert json.loads(completed.processing_options_json)["language"] == "auto"


def test_retry_failed_missing_local_input_remains_failed(tmp_path, capsys):
    data_dir = tmp_path / "private-data"
    media = tmp_path / "removed.wav"
    media.write_bytes(b"original input")
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        task = store.create_local_task(
            media,
            processing_options={
                "schema_version": 1,
                "language": "zh",
                "timestamps": False,
                "max_media_duration_seconds": 3600.0,
                "max_output_segments": 20_000,
                "max_output_characters": 2_000_000,
                "max_downloads": 2,
                "retries": 2,
                "correction_rules_enabled": False,
                "correction_rules": [],
                "output_dir": str((tmp_path / "output").resolve()),
            },
        )
        store.fail_task(task.task_id, "ASR_FAILED", "prior attempt failed")
    media.unlink()

    exit_code = cli.main(
        ["retry-failed", "--data-dir", str(data_dir), "--json"]
    )
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 5
    assert result["failed"] == 1
    assert result["items"][0]["status"] == "failed"
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        retried = store.get_task(task.task_id)
        assert retried is not None
        assert retried.state == "failed"
        assert retried.error_code is not None


@pytest.mark.parametrize(
    ("schema_version", "valid"),
    [(1, True), (2, True), (True, False), (1.0, False), ("1", False)],
)
def test_retry_snapshot_schema_version_requires_exact_integer_type(
    tmp_path, schema_version, valid
):
    snapshot = {
        "schema_version": schema_version,
        "language": "zh",
        "timestamps": False,
        "max_media_duration_seconds": 3600,
        "max_output_segments": 20_000,
        "max_output_characters": 2_000_000,
        "max_downloads": 1,
        "retries": 0,
        "correction_rules_enabled": False,
        "correction_rules": [],
        "output_dir": str(tmp_path),
    }
    if type(schema_version) is int and schema_version == 2:
        snapshot["max_processing_seconds"] = 900

    parsed = cli._retry_processing_options(json.dumps(snapshot))

    assert (parsed is not None) is valid
    if valid:
        assert parsed["max_processing_seconds"] == (900 if schema_version == 2 else 7200)


@pytest.mark.parametrize("timeout", [True, 0, -1, 86_401, 900.0, "900"])
def test_retry_snapshot_rejects_invalid_processing_timeout(tmp_path, timeout):
    snapshot = {
        "schema_version": 2,
        "language": "zh",
        "timestamps": False,
        "max_processing_seconds": timeout,
        "max_media_duration_seconds": 3600,
        "max_output_segments": 20_000,
        "max_output_characters": 2_000_000,
        "max_downloads": 1,
        "retries": 0,
        "correction_rules_enabled": False,
        "correction_rules": [],
        "output_dir": str(tmp_path),
    }

    assert cli._retry_processing_options(json.dumps(snapshot)) is None


def test_retry_timeout_override_updates_snapshot_and_pipeline_option(
    tmp_path, capsys, monkeypatch
):
    media = tmp_path / "spoken.wav"
    media.write_bytes(b"fixture media")
    data_dir = tmp_path / "private-data"
    options = {
        "schema_version": 2,
        "language": "zh",
        "timestamps": False,
        "max_processing_seconds": 60,
        "max_media_duration_seconds": 3600,
        "max_output_segments": 20_000,
        "max_output_characters": 2_000_000,
        "max_downloads": 1,
        "retries": 0,
        "correction_rules_enabled": False,
        "correction_rules": [],
        "output_dir": str((tmp_path / "output").resolve()),
    }
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        task = store.create_local_task(media, processing_options=options)
        store.fail_task(task.task_id, "PROCESSING_TIMEOUT", "prior timeout")

    pipeline_options = []

    class StubPipeline:
        def __init__(self, _paths, **kwargs):
            pipeline_options.append(kwargs)

        def run_local(self, _path, **_kwargs):
            return ItemResult("success", output_path=str(tmp_path / "done.md"))

    monkeypatch.setattr(cli, "TranscriptionPipeline", StubPipeline)
    exit_code = cli.main(
        [
            "retry-failed",
            "--data-dir",
            str(data_dir),
            "--processing-timeout-seconds",
            "321",
            "--json",
        ]
    )
    capsys.readouterr()

    assert exit_code == 0
    assert pipeline_options[0]["max_processing_seconds"] == 321
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        retried = store.get_task(task.task_id)
        assert retried is not None
        stored_options = json.loads(retried.processing_options_json)
        assert stored_options["schema_version"] == 2
        assert stored_options["max_processing_seconds"] == 321


def test_retry_output_dir_override_is_saved_in_the_processing_snapshot(
    tmp_path, capsys, monkeypatch
):
    data_dir = tmp_path / "private-data"
    original_output = tmp_path / "original-output"
    retry_output = tmp_path / "retry-output"
    options = {
        "schema_version": 1,
        "language": "zh",
        "timestamps": False,
        "max_media_duration_seconds": 3600,
        "max_output_segments": 20_000,
        "max_output_characters": 2_000_000,
        "max_downloads": 1,
        "retries": 0,
        "correction_rules_enabled": False,
        "correction_rules": [],
        "output_dir": str(original_output.resolve()),
    }
    source_url = "https://www.douyin.com/video/retry-output"
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        task = store.create_remote_task(
            source_url,
            "retry-output",
            processing_options=options,
        )
        store.fail_task(task.task_id, "NETWORK_FAILED", "prior failure")

    pipeline_paths = []

    class StubPipeline:
        def __init__(self, paths, **_kwargs):
            pipeline_paths.append(paths.output_dir)

        def run_urls(self, urls, *, title=None):
            assert urls == [source_url]
            return [ItemResult("success", title=title, output_path=str(retry_output / "result.md"))]

        def close(self):
            pass

    monkeypatch.setattr(
        cli,
        "output_directory_permission_status",
        lambda _path: {"status": "ok", "detail": "private"},
    )
    monkeypatch.setattr(cli, "TranscriptionPipeline", StubPipeline)

    code = cli.main(
        [
            "retry-failed",
            "--data-dir",
            str(data_dir),
            "--output-dir",
            str(retry_output),
            "--json",
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert pipeline_paths == [retry_output.resolve()]
    assert result["output_dir"] == str(retry_output.resolve())
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        retried = store.get_task(task.task_id)
        assert retried is not None
        saved_options = json.loads(retried.processing_options_json)
        assert saved_options["schema_version"] == 2
        assert saved_options["output_dir"] == str(retry_output.resolve())
        assert saved_options["max_processing_seconds"] == 7200


def test_legacy_retry_requires_explicit_current_defaults_opt_in(
    tmp_path, capsys, monkeypatch
):
    data_dir = tmp_path / "private-data"
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        task = store.create_remote_task(
            "https://www.douyin.com/video/legacy", "legacy"
        )
        store.fail_task(task.task_id, "NETWORK_FAILED", "temporary failure")

    pipeline_calls = []

    class StubPipeline:
        def __init__(self, _paths, **kwargs):
            pipeline_calls.append(kwargs)

        def run_urls(self, urls, *, title=None):
            assert urls == ["https://www.douyin.com/video/legacy"]
            return [ItemResult("success", title=title, video_id="legacy")]

    monkeypatch.setattr(cli, "TranscriptionPipeline", StubPipeline)
    skipped_code = cli.main(
        ["retry-failed", "--data-dir", str(data_dir), "--json"]
    )
    skipped = json.loads(capsys.readouterr().out)

    assert skipped_code == 0
    assert skipped["skipped"] == 1
    assert "LEGACY_CONFIG" in skipped["items"][0]["hint"]
    assert pipeline_calls == []
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        assert store.get_task("legacy").state == "failed"

    opted_code = cli.main(
        [
            "retry-failed", "--data-dir", str(data_dir),
            "--use-current-defaults", "--json",
        ]
    )
    opted = json.loads(capsys.readouterr().out)

    assert opted_code == 0
    assert opted["success"] == 1
    assert pipeline_calls[0]["language"] == "zh"
    assert pipeline_calls[0]["timestamps"] is False
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        retried = store.get_task("legacy")
        assert retried.state == "pending"
        assert json.loads(retried.processing_options_json)["language"] == "zh"


def test_retry_resolution_failure_restores_failed_state(tmp_path, capsys, monkeypatch):
    data_dir = tmp_path / "private-data"
    processing_options = {
        "schema_version": 2,
        "language": "zh",
        "timestamps": False,
        "max_processing_seconds": 7200,
        "max_media_duration_seconds": 3600.0,
        "max_output_segments": 20_000,
        "max_output_characters": 2_000_000,
        "max_downloads": 2,
        "retries": 2,
        "correction_rules_enabled": False,
        "correction_rules": [],
        "output_dir": str((tmp_path / "output").resolve()),
    }
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        task = store.create_remote_task(
            "https://www.douyin.com/video/retry-resolution",
            "retry-resolution",
            processing_options=processing_options,
        )
        claimed = store.claim_task(task.task_id, "first-run")
        assert claimed is not None
        store.fail_task(
            task.task_id,
            "NETWORK_FAILED",
            worker_id="first-run",
            claim_generation=claimed.claim_generation,
        )

    def fail_resolve(_url):
        raise UnsupportedUrlError("temporary resolver failure", "RESOLVE_TIMEOUT")

    original_pipeline = cli.TranscriptionPipeline

    def failing_resolver_pipeline(*args, **kwargs):
        kwargs["url_resolver"] = fail_resolve
        return original_pipeline(*args, **kwargs)

    monkeypatch.setattr(cli, "TranscriptionPipeline", failing_resolver_pipeline)
    code = cli.main(["retry-failed", "--data-dir", str(data_dir), "--json"])
    result = json.loads(capsys.readouterr().out)

    assert code == 5
    assert result["failed"] == 1
    assert result["items"][0]["error_code"] == "RESOLVE_TIMEOUT"
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        failed = store.get_task(task.task_id)
        assert failed is not None
        assert failed.state == "failed"
        assert failed.error_code == "RESOLVE_TIMEOUT"
