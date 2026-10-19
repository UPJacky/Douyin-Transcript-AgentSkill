from __future__ import annotations

import argparse
import hashlib
import io
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
import douyin_transcript.config as config
import douyin_transcript.cli as cli
import pytest
from douyin_transcript.asr import TranscriptionResult, TranscriptSegment
from douyin_transcript.capture_client import CaptureClientError
from douyin_transcript.cli import _read_url_file, _run_setup, build_parser
from douyin_transcript.corrections import (
    MAX_TERMINOLOGY_DICTIONARY_BYTES,
    CorrectionRule,
)
from douyin_transcript.downloader import MediaFile
from douyin_transcript.markdown import (
    render_transcript_markdown,
    write_reviewed_transcript_markdown,
)
from douyin_transcript.models import model_spec
from douyin_transcript.output import ItemResult, make_summary
from douyin_transcript.pipeline import MAX_URL_BATCH_ITEMS, MAX_URL_LENGTH
from douyin_transcript.pipeline import TranscriptionPipeline as RealPipeline
from douyin_transcript.tasks import DEFAULT_STALE_AFTER_SECONDS, TaskStore
from douyin_transcript.urls import ResolvedInput


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


def test_url_cli_injects_personal_client_and_runs_serially(
    tmp_path, monkeypatch, capsys
):
    client = object()
    calls = {}
    monkeypatch.setattr(cli, "PersonalCaptureClient", lambda _data_dir: client)

    class Pipeline:
        def __init__(self, _paths, **options):
            calls.update(options)

        def run_urls(self, _values, *, title):
            return [ItemResult("skipped", video_id="12")]

        def close(self):
            calls["closed"] = True

    monkeypatch.setattr(cli, "TranscriptionPipeline", Pipeline)
    code = cli.main(
        [
            "transcribe",
            "https://www.douyin.com/video/12",
            "--json",
            "--data-dir",
            str(tmp_path / "data"),
        ]
    )
    assert code == 0
    assert calls["capture_service_client"] is client
    assert calls["max_downloads"] == 1
    assert calls["closed"] is True
    assert json.loads(capsys.readouterr().out)["skipped"] == 1


def test_login_cli_opens_personal_profile_and_reports_only_window_state(
    tmp_path, monkeypatch, capsys
):
    calls = []

    class Client:
        def __init__(self, data_dir):
            calls.append(data_dir)

        def login(self):
            calls.append("opened")

    monkeypatch.setattr(cli, "PersonalCaptureClient", Client)
    assert cli.main(["login", "--data-dir", str(tmp_path / "data"), "--json"]) == 0
    result = capsys.readouterr()
    assert calls == [(tmp_path / "data").resolve(), "opened"]
    assert json.loads(result.out) == {"status": "browser_closed"}
    assert "5 分钟" in result.err


def test_review_sidecar_reads_body_from_stdin_and_only_reports_path(
    tmp_path, monkeypatch, capsys
):
    raw_path = tmp_path / "raw.md"
    raw_path.write_text(
        '---\ntitle: "raw"\n---\n\n# raw\n\n'
        "> 本文为自动语音识别逐字稿，未经人工逐字校对。\n\n"
        "## 口播逐字稿\n\n原始机密标记。\n",
        encoding="utf-8",
    )
    original_raw = raw_path.read_bytes()
    private_reviewed_text = "闭源组件已经完成校对。"
    monkeypatch.setattr(
        cli.sys,
        "stdin",
        io.StringIO(json.dumps({"reviewed_body": private_reviewed_text})),
    )

    code = cli.main(
        [
            "review-sidecar",
            "--raw-file",
            str(raw_path),
            "--data-dir",
            str(tmp_path / "data"),
        ]
    )
    captured = capsys.readouterr()
    result = json.loads(captured.out)

    assert code == 0
    assert result["status"] == "sidecar_saved"
    assert result["task_binding"] == "no_task_database"
    assert Path(result["output_path"]).is_file()
    assert private_reviewed_text not in captured.out
    assert private_reviewed_text not in captured.err
    assert "原始机密标记" not in captured.out + captured.err
    assert raw_path.read_bytes() == original_raw


def test_review_sidecar_cli_binds_new_output_to_exact_completed_task(
    tmp_path, monkeypatch, capsys
):
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    media = tmp_path / "media.bin"
    media.write_bytes(b"media")
    raw_path = output_dir / "task-output.md"
    reviewed_body = "模型校对后的正文。"
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        task = store.create_remote_task(
            "https://www.douyin.com/video/review-cli-binding", "review-cli-binding"
        )
        store.transition(task.task_id, "resolving")
        store.transition(task.task_id, "downloading")
        store.transition(task.task_id, "downloaded", media_path=media)
        store.transition(task.task_id, "transcribing")
        task = store.transition(task.task_id, "writing", output_path=raw_path)
        raw_path.write_text(
            render_transcript_markdown(
                "task output",
                "原始口播逐字稿。",
                {"video_id": "review-cli-binding"},
            ),
            encoding="utf-8",
        )
        store.record_output_integrity(
            task.task_id,
            raw_path,
            hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        )
        store.complete_task(task.task_id, raw_path)

    monkeypatch.setattr(
        cli.sys,
        "stdin",
        io.StringIO(json.dumps({"reviewed_body": reviewed_body})),
    )
    code = cli.main(
        ["review-sidecar", "--raw-file", str(raw_path), "--data-dir", str(data_dir)]
    )
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert result["task_binding"] == "registered"
    assert reviewed_body not in json.dumps(result, ensure_ascii=False)
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        records = store.list_reviewed_sidecars(task.task_id)
    assert len(records) == 1
    assert (
        records[0].source_output_sha256
        == hashlib.sha256(raw_path.read_bytes()).hexdigest()
    )
    assert records[0].reviewed_path == result["output_path"]


def test_review_sidecar_rejects_interactive_stdin_without_reading(monkeypatch, capsys):
    class InteractiveStdin:
        @staticmethod
        def isatty():
            return True

        @staticmethod
        def read(_size=-1):
            raise AssertionError("interactive input should be rejected before reading")

    monkeypatch.setattr(cli.sys, "stdin", InteractiveStdin())

    code = cli.main(["review-sidecar", "--raw-file", "unused.md"])
    captured = capsys.readouterr()

    assert code == 2
    assert "interactive terminal input is not supported" in captured.err
    assert "reviewed_body" not in captured.out + captured.err


def test_review_sidecar_decodes_utf8_bytes_independent_of_console_encoding(
    tmp_path, monkeypatch, capsys
):
    raw_path = tmp_path / "raw.md"
    raw_path.write_text(
        '---\ntitle: "raw"\n---\n\n# raw\n\n'
        "> 本文为自动语音识别逐字稿，未经人工逐字校对。\n\n"
        "## 口播逐字稿\n\n原始正文。\n",
        encoding="utf-8",
    )
    reviewed_body = "这是 UTF-8 中文闭源校对。"
    payload = json.dumps({"reviewed_body": reviewed_body}, ensure_ascii=False)
    monkeypatch.setattr(
        cli.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(payload.encode("utf-8")))
    )

    code = cli.main(
        [
            "review-sidecar",
            "--raw-file",
            str(raw_path),
            "--data-dir",
            str(tmp_path / "data"),
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    reviewed_output = Path(result["output_path"]).read_text(encoding="utf-8")
    assert "这是 UTF\\-8 中文闭源校对。" in reviewed_output


def test_review_sidecar_accepts_worst_case_escaped_unicode_at_body_limit(
    tmp_path, monkeypatch, capsys
):
    raw_path = tmp_path / "raw.md"
    raw_path.write_text(
        '---\ntitle: "raw"\n---\n\n# raw\n\n'
        "> 本文为自动语音识别逐字稿，未经人工逐字校对。\n\n"
        "## 口播逐字稿\n\n原始正文。\n",
        encoding="utf-8",
    )
    paragraph = ("😀" * 159 + "，") * 3_124 + "😀" * 158 + "。"
    reviewed_body = paragraph + "\n\n" + paragraph
    payload = json.dumps({"reviewed_body": reviewed_body})
    assert len(reviewed_body) == cli.MAX_REVIEWED_TRANSCRIPT_CHARACTERS
    assert len(payload.encode("utf-8")) > 6 * cli.MAX_REVIEWED_TRANSCRIPT_CHARACTERS
    monkeypatch.setattr(
        cli.sys,
        "stdin",
        SimpleNamespace(buffer=io.BytesIO(payload.encode("utf-8"))),
    )

    code = cli.main(
        [
            "review-sidecar",
            "--raw-file",
            str(raw_path),
            "--data-dir",
            str(tmp_path / "data"),
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    reviewed_output = Path(result["output_path"]).read_text(encoding="utf-8")
    assert reviewed_output.endswith(reviewed_body + "\n")


def test_review_sidecar_rejects_invalid_utf8_bytes(tmp_path, monkeypatch, capsys):
    raw_path = tmp_path / "raw.md"
    raw_path.write_text(
        '---\ntitle: "raw"\n---\n\n# raw\n\n'
        "> 本文为自动语音识别逐字稿，未经人工逐字校对。\n\n"
        "## 口播逐字稿\n\n原始正文。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        cli.sys,
        "stdin",
        SimpleNamespace(buffer=io.BytesIO(b'{"reviewed_body":"\xff"}')),
    )

    code = cli.main(["review-sidecar", "--raw-file", str(raw_path)])
    captured = capsys.readouterr()

    assert code == 2
    assert "INVALID_INPUT" in captured.err
    assert not list(tmp_path.glob("*.reviewed.md"))


def test_review_sidecar_rejects_duplicate_json_fields(tmp_path, monkeypatch, capsys):
    raw_path = tmp_path / "raw.md"
    raw_path.write_text(
        '---\ntitle: "raw"\n---\n\n# raw\n\n'
        "> 本文为自动语音识别逐字稿，未经人工逐字校对。\n\n"
        "## 口播逐字稿\n\n原始正文。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        cli.sys,
        "stdin",
        io.StringIO('{"reviewed_body":"第一版正文。","reviewed_body":"替换正文。"}'),
    )

    code = cli.main(["review-sidecar", "--raw-file", str(raw_path)])
    captured = capsys.readouterr()

    assert code == 2
    assert "reviewed_body" not in captured.out + captured.err
    assert not list(tmp_path.glob("*.reviewed.md"))


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


@pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "mkfifo"), reason="POSIX FIFO"
)
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
    urls = [
        f"https://www.douyin.com/video/{index}"
        for index in range(MAX_URL_BATCH_ITEMS + 1)
    ]

    exit_code = cli.main(["transcribe", *urls, "--data-dir", str(data_dir)])

    assert exit_code == 2
    assert "最多支持" in capsys.readouterr().err
    assert not data_dir.exists()


def test_summary_terminal_output_strips_title_controls(capsys):
    summary = make_summary(
        [
            ItemResult(
                "success", title="safe\x1b[2J\x07\x7f\x85\x9btext", output_path="out.md"
            )
        ],
        ".",
    )

    cli._print_summary(summary, as_json=False, quiet=False)

    output = capsys.readouterr().out
    assert not any(0x7F <= ord(character) <= 0x9F for character in output)
    assert "\x1b" not in output and "\x07" not in output
    assert "safe[2Jtext" in output


@pytest.mark.parametrize("quiet", [False, True], ids=("text", "quiet"))
def test_summary_terminal_output_strips_path_controls(capsys, tmp_path, quiet):
    output_path = "safe-output\x1b[2J\x85‮name.md"
    output_dir = tmp_path / "safe-dir\x1b[2J\x85‮name"
    summary = make_summary(
        [ItemResult("success", title="item", output_path=output_path)],
        output_dir,
    )
    permissions = {
        "directories": [
            {
                "status": "unsafe",
                "path": "safe-warning\x1b[2J",
                "detail": "private\x85‮ detail",
            }
        ]
    }

    cli._print_summary(
        summary,
        as_json=False,
        quiet=quiet,
        output_dir_permissions=permissions,
    )

    captured = capsys.readouterr()
    emitted = captured.out + captured.err
    lines = emitted.splitlines()
    assert len(captured.out.splitlines()) == 2
    assert len(captured.err.splitlines()) == 1
    assert not any(
        ord(character) < 32 or 127 <= ord(character) <= 159
        for line in lines
        for character in line
    )
    assert "‮" not in emitted
    assert "safe-output[2Jname.md" in captured.out
    assert "safe-dir[2Jname" in captured.out
    assert "safe-warning[2J" in captured.err
    assert "private detail" in captured.err


def test_summary_json_escapes_path_controls_and_preserves_values(capsys, tmp_path):
    output_path = "safe-output\x1b[2J\x85‮name.md"
    summary = make_summary(
        [ItemResult("success", title="item", output_path=output_path)],
        tmp_path / "safe-dir\x1b[2J",
    )
    permissions = {
        "directories": [
            {
                "status": "unsafe",
                "path": "safe-warning\x1b[2J",
                "detail": "private\x85‮ detail",
            }
        ]
    }

    cli._print_summary(
        summary,
        as_json=True,
        quiet=False,
        output_dir_permissions=permissions,
    )

    output = capsys.readouterr().out
    result = json.loads(output)
    assert "\x1b" not in output and "\x85" not in output
    assert "\\u202e" in output
    assert result["items"][0]["output_path"] == output_path
    assert result["output_dir"] == summary.output_dir
    assert result["output_dir_permissions"] == permissions
    assert result["result_scope"] == "raw_asr_only"
    assert result["llm_review_status"] == "not_performed_by_cli"


def test_text_summary_marks_success_as_raw_asr_only(capsys, tmp_path):
    summary = make_summary(
        [ItemResult("success", title="item", output_path=str(tmp_path / "raw.md"))],
        tmp_path,
    )

    cli._print_summary(summary, as_json=False, quiet=False)

    output = capsys.readouterr().out
    assert "RAW_ASR_READY: item ->" in output
    assert "success: total=1" in output
    assert "result_scope=raw_asr_only" in output
    assert "llm_review_status=not_performed_by_cli" in output


@pytest.mark.parametrize("control", ["\x1b[2J", "\x85", "\r\n", "\u202e"])
def test_cli_invalid_url_file_path_strips_terminal_controls(capsys, tmp_path, control):
    source = tmp_path / f"urls{control}.txt"

    exit_code = cli.main(["transcribe", "--file", str(source)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "INVALID_INPUT: 无法读取 URL 清单：" in captured.err
    lines = captured.err.splitlines()
    assert len(lines) == 1
    assert not any(
        ord(character) < 32 or 127 <= ord(character) <= 159
        for line in lines
        for character in line
    )
    assert "\u202e" not in captured.err
    assert "urls" in captured.err and ".txt" in captured.err


def test_argparse_errors_strip_terminal_controls(capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["transcribe", "--unknown\x1b[2J‮"])

    assert error.value.code == 2
    lines = capsys.readouterr().err.splitlines()
    assert not any(
        ord(character) < 32 or 127 <= ord(character) <= 159 or character == "‮"
        for line in lines
        for character in line
    )
    assert any("--unknown[2J" in line for line in lines)


def test_dry_run_terminal_output_strips_media_and_storage_path_controls(
    monkeypatch, capsys, tmp_path
):
    media_path = str(tmp_path / "media\x1b[2J\x85‮name.wav")
    data_dir = tmp_path / "data\x1b[2J"
    output_dir = tmp_path / "output\x85"
    monkeypatch.setattr(
        cli,
        "_path_writable_without_create",
        lambda path: {"status": "writable", "path": str(path)},
    )
    monkeypatch.setattr(
        cli,
        "_output_permissions_summary",
        lambda _paths: {"status": "ok", "directories": []},
    )
    args = argparse.Namespace(input_file=media_path, json=False)
    paths = SimpleNamespace(data_dir=data_dir, output_dir=output_dir)

    exit_code = cli._run_dry_run(args, paths)

    output = capsys.readouterr().out
    assert exit_code == 2
    lines = output.splitlines()
    assert len(lines) == 4
    assert not any(
        ord(character) < 32 or 127 <= ord(character) <= 159
        for line in lines
        for character in line
    )
    assert "\u202e" not in output
    assert "media[2Jname.wav" in output
    assert "data[2J" in output
    assert "output" in output


def test_summary_json_strips_bidi_title_controls(capsys):
    summary = make_summary(
        [ItemResult("success", title="safe\u202eTitle", output_path="out.md")],
        ".",
    )

    cli._print_summary(summary, as_json=True, quiet=False)

    result = json.loads(capsys.readouterr().out)
    assert result["items"][0]["title"] == "safeTitle"
    assert "\u202e" not in result["items"][0]["title"]


@pytest.mark.parametrize(
    ("as_json", "quiet"),
    [(True, False), (False, False), (False, True)],
)
def test_error_summaries_redact_urls_in_json_stdout_and_quiet_stderr(
    capsys, tmp_path, as_json, quiet
):
    sensitive_url = (
        "https://media.example/private/path-token?X-Amz-Signature=query-secret"
    )
    summary = make_summary(
        [
            ItemResult(
                "failed",
                error_code="DOWNLOAD_FAILED",
                hint=f"request failed: {sensitive_url}",
            )
        ],
        tmp_path,
    )

    cli._print_summary(summary, as_json=as_json, quiet=quiet)
    captured = capsys.readouterr()
    emitted = captured.out + captured.err

    assert "[REDACTED_URL]" in emitted
    assert "path-token" not in emitted
    assert "query-secret" not in emitted


@pytest.mark.parametrize(
    "mode_args",
    [("--json",), (), ("--quiet",)],
    ids=("json", "text", "quiet"),
)
def test_transcribe_cli_keeps_synthetic_transcript_out_of_terminal_and_status(
    monkeypatch, capsys, tmp_path, mode_args
):
    marker = "TRANSCRIPTSENTINEL7c6f3ad2"
    media = tmp_path / "synthetic-input.wav"
    media.write_bytes(b"synthetic fixture; fake validator and ASR only")
    data_dir = tmp_path / "private-data"
    output_dir = tmp_path / "private-output"

    class SyntheticASR:
        def __init__(self, *_args, **_kwargs):
            pass

        def transcribe(self, _path, *, language):
            return TranscriptionResult(
                (TranscriptSegment(0.0, 1.0, marker),),
                1.0,
                language,
                "synthetic-test-model",
                "balanced",
            )

    def synthetic_validator(path):
        source = Path(path)
        return MediaFile(source, "wav", source.stat().st_size, 1.0)

    def pipeline_factory(paths, **kwargs):
        return RealPipeline(
            paths,
            **kwargs,
            asr_factory=SyntheticASR,
            media_validator=synthetic_validator,
        )

    monkeypatch.setattr(cli, "TranscriptionPipeline", pipeline_factory)
    monkeypatch.setattr(
        cli,
        "output_directory_permission_status",
        lambda _path: {"status": "ok", "detail": "test fixture"},
    )

    code = cli.main(
        [
            "transcribe",
            "--input-file",
            str(media),
            "--data-dir",
            str(data_dir),
            "--output-dir",
            str(output_dir),
            *mode_args,
        ]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert marker not in captured.out
    assert marker not in captured.err
    markdown_files = list(output_dir.glob("*.md"))
    assert len(markdown_files) == 1
    assert marker in markdown_files[0].read_text(encoding="utf-8")

    if mode_args == ("--json",):
        summary = json.loads(captured.out)
        assert summary["status"] == "success"
        assert marker not in json.dumps(summary, ensure_ascii=False)

    status_code = cli.main(["status", "--data-dir", str(data_dir), "--json"])
    status_output = capsys.readouterr()
    assert status_code == 0
    assert marker not in status_output.out
    assert marker not in status_output.err
    assert json.loads(status_output.out)["tasks"][0]["state"] == "completed"


def test_status_json_redacts_urls_from_legacy_error_messages(tmp_path, capsys):
    data_dir = tmp_path / "data"
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        task = store.create_remote_task("https://www.douyin.com/video/123", "123")
        store.fail_task(task.task_id, "DOWNLOAD_FAILED", "download failed")
        store._connection.execute(
            "UPDATE tasks SET error_message = ? WHERE task_id = ?",
            (
                "failed https://media.example/private/path-token?token=query-secret",
                task.task_id,
            ),
        )

    code = cli.main(["status", "--data-dir", str(data_dir), "--json"])
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    message = result["tasks"][0]["error_message"]
    assert "[REDACTED_URL]" in message
    assert "path-token" not in message
    assert "query-secret" not in message


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


def _create_completed_status_task(tmp_path, *, video_id="status-review"):
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    media = tmp_path / "media.bin"
    media.write_bytes(b"synthetic-media")
    raw_path = output_dir / f"{video_id}.md"
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        task = store.create_remote_task(
            f"https://www.douyin.com/video/{video_id}", video_id
        )
        store.transition(task.task_id, "resolving")
        store.transition(task.task_id, "downloading")
        store.transition(task.task_id, "downloaded", media_path=media)
        store.transition(task.task_id, "transcribing")
        store.transition(task.task_id, "writing", output_path=raw_path)
        raw_path.write_text(
            render_transcript_markdown(
                "status fixture", "原始口播文本。", {"video_id": video_id}
            ),
            encoding="utf-8",
        )
        store.record_output_integrity(
            task.task_id, raw_path, hashlib.sha256(raw_path.read_bytes()).hexdigest()
        )
        store.complete_task(task.task_id, raw_path)
    return data_dir, raw_path


def _register_status_review(data_dir, raw_path, *, body="校对后的文本。"):
    reviewed_path = write_reviewed_transcript_markdown(raw_path, body)
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        record = store.register_reviewed_sidecar(raw_path, reviewed_path)
        assert record is not None
    return reviewed_path, record


def _read_status_json(data_dir, capsys):
    code = cli.main(["status", "--data-dir", str(data_dir), "--json"])
    output = capsys.readouterr()
    assert code == 0
    assert output.err == ""
    return json.loads(output.out)


def test_status_without_review_keeps_raw_task_fields_unchanged(tmp_path, capsys):
    data_dir, raw_path = _create_completed_status_task(tmp_path)

    result = _read_status_json(data_dir, capsys)
    row = result["tasks"][0]

    assert row["state"] == "completed"
    assert row["output_path"] == str(raw_path.resolve())
    assert row["review_status"] == "not_reviewed"
    assert row["reviewed_output_path"] is None
    assert row["review_scope"] is None


def test_status_reports_valid_review_hash_scope_and_plain_text(tmp_path, capsys):
    data_dir, raw_path = _create_completed_status_task(tmp_path)
    reviewed_path, _record = _register_status_review(data_dir, raw_path)

    result = _read_status_json(data_dir, capsys)
    row = result["tasks"][0]
    assert row["state"] == "completed"
    assert row["output_path"] == str(raw_path.resolve())
    assert row["review_status"] == "valid"
    assert row["reviewed_output_path"] == str(reviewed_path)
    assert row["review_scope"] == "model_text_review_unheard"

    assert cli.main(["status", "--data-dir", str(data_dir)]) == 0
    output = capsys.readouterr()
    assert "原稿完成" in output.out
    assert "校对稿已关联（文本校对，未听审）" in output.out
    assert str(reviewed_path) in output.out


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ("review_missing", "missing"),
        ("raw_missing", "missing"),
        ("review_changed", "changed"),
        ("raw_changed", "changed"),
    ],
)
def test_status_detects_missing_and_changed_review_artifacts(
    tmp_path, capsys, change, expected
):
    data_dir, raw_path = _create_completed_status_task(tmp_path)
    reviewed_path, _record = _register_status_review(data_dir, raw_path)
    if change == "review_missing":
        reviewed_path.unlink()
    elif change == "raw_missing":
        raw_path.unlink()
    elif change == "review_changed":
        with reviewed_path.open("ab") as stream:
            stream.write(b"changed")
    else:
        with raw_path.open("ab") as stream:
            stream.write(b"changed")

    row = _read_status_json(data_dir, capsys)["tasks"][0]
    assert row["review_status"] == expected
    assert row["reviewed_output_path"] is None
    assert row["review_scope"] == "model_text_review_unheard"


def test_status_marks_review_unverifiable_when_private_file_cannot_be_checked(
    tmp_path, monkeypatch, capsys
):
    data_dir, raw_path = _create_completed_status_task(tmp_path)
    reviewed_path, _record = _register_status_review(data_dir, raw_path)
    original = cli.open_private_regular_file

    def refuse_review(path):
        if Path(path) == reviewed_path:
            raise PermissionError("synthetic permission failure")
        return original(path)

    monkeypatch.setattr(cli, "open_private_regular_file", refuse_review)
    row = _read_status_json(data_dir, capsys)["tasks"][0]
    assert row["review_status"] == "unverifiable"
    assert row["reviewed_output_path"] is None


def test_status_uses_latest_review_and_does_not_fall_back_when_it_is_missing(
    tmp_path, capsys
):
    data_dir, raw_path = _create_completed_status_task(tmp_path)
    _first_path, first = _register_status_review(
        data_dir, raw_path, body="第一份校对稿。"
    )
    second_path, second = _register_status_review(
        data_dir, raw_path, body="第二份校对稿。"
    )
    second_path.unlink()

    with TaskStore(data_dir / "tasks.sqlite3") as store:
        records = store.list_reviewed_sidecars(first.task_id)
    assert [record.review_id for record in records][-1] == second.review_id

    row = _read_status_json(data_dir, capsys)["tasks"][0]
    assert row["review_status"] == "missing"
    assert row["reviewed_output_path"] is None
    assert row["review_scope"] == "model_text_review_unheard"


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
        "HF_ENDPOINT",
        "https://model-user:model-secret@hf-mirror.example/api?token=hf-hidden",
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
    assert (
        "Hugging Face 下载端点：https://hf-mirror.example（HF_ENDPOINT 覆盖）" in output
    )
    assert "Chromium 来源：Playwright 下载服务" in output
    assert (
        "Playwright 自定义下载源 PLAYWRIGHT_DOWNLOAD_HOST：https://browser.example"
        in output
    )
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
        (destination / "config.json").write_text(
            '{"model_type":"whisper"}', encoding="utf-8"
        )
        (destination / "tokenizer.json").write_text(
            '{"version":"1.0"}', encoding="utf-8"
        )

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


def test_setup_preserves_previously_installed_optional_extras(monkeypatch, tmp_path):
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
    assert commands[1] == [
        sys.executable,
        "-P",
        "-m",
        "playwright",
        "install",
        "chromium",
    ]


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
        [
            "transcribe",
            "https://www.douyin.com/video/12",
            "--dry-run",
            "--max-downloads",
            "1",
            "--retry",
            "0",
            "--processing-timeout-seconds",
            "900",
        ]
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
        "resolve_direct_input",
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
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("pipeline started")
        ),
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
    assert result["items"][0]["input_status"] == "valid"
    assert result["items"][0]["status"] == "valid"
    assert result["url_capture"]["status"] == "not_checked"
    assert result["url_capture"]["mode"] == "personal"
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


def test_dry_run_keeps_local_media_ready_without_url_capture(tmp_path, capsys):
    media_path = tmp_path / "audio.wav"
    media_path.write_bytes(b"audio")
    paths = cli.resolve_paths(
        data_dir=tmp_path / "not-created-data",
        output_dir=tmp_path / "not-created-output",
    )

    exit_code = cli.main(
        [
            "transcribe",
            "--input-file",
            str(media_path),
            "--dry-run",
            "--json",
            "--data-dir",
            str(paths.data_dir),
            "--output-dir",
            str(paths.output_dir),
        ]
    )

    result = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert result["status"] == "ready"
    assert result["items"][0]["status"] == "ready"
    assert result["url_capture"]["status"] == "not_required"


def test_dry_run_leaves_short_link_resolution_for_capture_without_network(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(
        cli,
        "output_directory_permission_status",
        lambda _path: {"status": "ok"},
    )

    exit_code = cli.main(
        [
            "transcribe",
            "https://v.douyin.com/abc123/",
            "--dry-run",
            "--json",
            "--data-dir",
            str(tmp_path / "data"),
            "--output-dir",
            str(tmp_path / "output"),
        ]
    )

    result = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert result["status"] == "ready"
    assert result["items"][0]["status"] == "resolution_required"
    assert result["url_capture"]["status"] == "not_checked"
    assert result["url_capture"]["mode"] == "personal"


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


def test_doctor_human_output_removes_config_key_terminal_controls(capsys, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    config_path = data_dir / "config.toml"
    config_path.write_text('[limits]\n"bad\\u001b[31m" = true\n', encoding="utf-8")
    if os.name != "nt":
        config_path.chmod(0o600)

    exit_code = cli.main(["doctor", "--data-dir", str(data_dir)])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "\x1b" not in output
    assert "bad[31m" in output


def test_doctor_human_output_removes_controls_from_config_path_and_diagnostics(
    monkeypatch, capsys
):
    unsafe = "config.toml\x1b[31m\u202e"
    monkeypatch.setattr(
        cli,
        "collect_report",
        lambda **_kwargs: {
            "overall": "setup_required",
            "checks": {
                "config": {
                    "status": "invalid",
                    "detail": f"无法读取配置文件：{unsafe}",
                }
            },
            "data_dir": f"C:/private/{unsafe}",
        },
    )

    exit_code = cli.main(["doctor"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "\x1b" not in output
    assert "\u202e" not in output
    assert "config.toml[31m" in output


def test_doctor_json_escapes_controls_from_config_path_and_diagnostics(
    monkeypatch, capsys
):
    unsafe = "config.toml\x1b[31m\u202e"
    monkeypatch.setattr(
        cli,
        "collect_report",
        lambda **_kwargs: {
            "overall": "setup_required",
            "checks": {
                "config": {
                    "status": "invalid",
                    "detail": f"无法读取配置文件：{unsafe}",
                }
            },
            "data_dir": f"C:/private/{unsafe}",
        },
    )

    exit_code = cli.main(["doctor", "--json"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "\x1b" not in output
    assert "\\u001b" in output
    assert "\\u202e" in output


def test_cli_configuration_error_removes_terminal_controls(
    monkeypatch, capsys, tmp_path
):
    media = tmp_path / "input.wav"
    media.write_bytes(b"fixture")

    def fail_config(**_kwargs):
        raise config.ConfigurationError("无法读取 config.toml：\x1b[31msecret\u202e")

    monkeypatch.setattr(cli, "resolve_paths", fail_config)

    exit_code = cli.main(["transcribe", "--input-file", str(media)])

    output = capsys.readouterr().err
    assert exit_code == 2
    assert "\x1b" not in output
    assert "\u202e" not in output
    assert "config.toml" in output


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
            return ItemResult(
                "success", title=title, output_path=str(output_dir / "spoken.md")
            )

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
            return ItemResult(
                "success", title=title, output_path=str(output_dir / "spoken.md")
            )

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
            "1",
            "downloading",
            worker_id="worker",
            claim_generation=claimed.claim_generation,
        )
        store.transition(
            "1",
            "downloaded",
            worker_id="worker",
            claim_generation=claimed.claim_generation,
            media_path=protected,
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
            "cache",
            "clean",
            "--data-dir",
            str(data_dir),
            "--max-bytes",
            "0",
            "--apply",
            "--json",
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
            "123",
            "downloading",
            worker_id="worker",
            claim_generation=claimed.claim_generation,
        )

    code = cli.main(
        [
            "cache",
            "clean",
            "--data-dir",
            str(data_dir),
            "--max-age-hours",
            "0",
            "--apply",
            "--json",
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
                "123",
                "downloading",
                worker_id="late-worker",
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
                "cache",
                "clean",
                "--data-dir",
                str(data_dir),
                "--max-age-hours",
                "0",
                "--apply",
                "--json",
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
                store.create_remote_task("https://www.douyin.com/video/789", "789")
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

        monkeypatch.setattr(
            cli, "cleanup_media_cache", cleanup_with_writer_between_entries
        )
        code = cli.main(
            [
                "cache",
                "clean",
                "--data-dir",
                str(data_dir),
                "--max-age-hours",
                "0",
                "--apply",
                "--json",
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
                "123",
                "downloading",
                worker_id="next-worker",
                claim_generation=claimed.claim_generation,
            )
        partial.write_bytes(b"new download partial")
        claim_finished.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        cleanup_future = executor.submit(
            cli.main,
            [
                "cache",
                "clean",
                "--data-dir",
                str(data_dir),
                "--max-age-hours",
                "0",
                "--apply",
                "--json",
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
            "cache",
            "clean",
            "--data-dir",
            str(data_dir),
            "--max-age-hours",
            "0",
            "--apply",
            "--json",
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert source.is_file()
    assert result["selected_paths"] == []
    assert result["removed_paths"] == []


def test_cache_age_cleanup_removes_partial_after_stale_claim_recovery(tmp_path, capsys):
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
            "123",
            "downloading",
            worker_id="worker",
            claim_generation=claimed.claim_generation,
        )
        store._connection.execute(
            "UPDATE tasks SET claimed_at = ? WHERE task_id = ?",
            (stale_claim.isoformat(timespec="milliseconds"), "123"),
        )
        store.recover_interrupted(stale_after_seconds=DEFAULT_STALE_AFTER_SECONDS)

    code = cli.main(
        [
            "cache",
            "clean",
            "--data-dir",
            str(data_dir),
            "--max-age-hours",
            "0",
            "--apply",
            "--json",
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
        return {"status": "ok", "detail": "private snapshot ACL"}

    monkeypatch.setattr(
        cli, "output_directory_permission_status", output_permission_status
    )
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
                {
                    "rule_id": "brand",
                    "source": "ASR词",
                    "replacement": "标准词",
                    "note": "",
                }
            ],
            "output_dir": str(original_output.resolve()),
        }

    retry_code = cli.main(["retry-failed", "--data-dir", str(data_dir), "--json"])
    retry_output = capsys.readouterr()
    result = json.loads(retry_output.out)
    assert retry_code == 0
    assert result["output_dir"] == str(original_output.resolve())
    assert result["output_dir_permissions"] == {
        "status": "ok",
        "directories": [
            {
                "path": str(original_output.resolve()),
                "status": "ok",
                "detail": "private snapshot ACL",
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


def test_force_failure_retry_uses_latest_attempt_snapshot(
    tmp_path, capsys, monkeypatch
):
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
            "transcribe",
            "--input-file",
            str(media),
            "--data-dir",
            str(data_dir),
            "--output-dir",
            str(first_output),
            "--json",
        ]
    )
    capsys.readouterr()
    assert first_code == 0

    forced_code = cli.main(
        [
            "transcribe",
            "--input-file",
            str(media),
            "--data-dir",
            str(data_dir),
            "--output-dir",
            str(forced_output),
            "--profile",
            "fast",
            "--language",
            "auto",
            "--timestamps",
            "--force",
            "--json",
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
    assert (
        Path(retry_output["items"][0]["output_path"]).parent == forced_output.resolve()
    )
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        completed = store.list_tasks(states=("completed",))[0]
        assert completed.profile == "fast"
        assert json.loads(completed.processing_options_json)["language"] == "auto"


def test_retry_failed_missing_local_input_remains_failed(tmp_path, capsys, monkeypatch):
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

    original_parse = cli._retry_processing_options
    parse_calls = 0

    def count_parse_calls(raw, **kwargs):
        nonlocal parse_calls
        parse_calls += 1
        return original_parse(raw, **kwargs)

    monkeypatch.setattr(cli, "_retry_processing_options", count_parse_calls)

    exit_code = cli.main(["retry-failed", "--data-dir", str(data_dir), "--json"])
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 5
    assert parse_calls == 1
    assert result["failed"] == 1
    assert result["items"][0]["status"] == "failed"
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        retried = store.get_task(task.task_id)
        assert retried is not None
        assert retried.state == "failed"
        assert retried.error_code is not None


def test_retry_snapshot_resolution_runtime_error_is_skipped_before_queue(
    tmp_path, capsys, monkeypatch
):
    media = tmp_path / "spoken.wav"
    media.write_bytes(b"fixture media")
    data_dir = tmp_path / "private-data"
    saved_output = tmp_path / "symlink-loop"
    snapshot = {
        "schema_version": 2,
        "language": "zh",
        "timestamps": False,
        "max_processing_seconds": 900,
        "max_media_duration_seconds": 3600,
        "max_output_segments": 20_000,
        "max_output_characters": 2_000_000,
        "max_downloads": 1,
        "retries": 0,
        "correction_rules_enabled": False,
        "correction_rules": [],
        "output_dir": str(saved_output.resolve()),
    }
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        task = store.create_local_task(media, processing_options=snapshot)
        store.fail_task(task.task_id, "ASR_FAILED", "prior attempt failed")

    original_resolve = Path.resolve

    def resolve_with_loop(path, strict=False):
        if path == saved_output:
            raise RuntimeError("Symlink loop")
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve_with_loop)
    monkeypatch.setattr(
        cli,
        "TranscriptionPipeline",
        lambda *_args, **_kwargs: pytest.fail("invalid snapshot was queued"),
    )

    exit_code = cli.main(["retry-failed", "--data-dir", str(data_dir), "--json"])
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert result["skipped"] == 1
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        current = store.get_task(task.task_id)
        assert current is not None
        assert current.state == "failed"


def test_retry_snapshot_resolution_failure_can_use_explicit_output_override(
    tmp_path, capsys, monkeypatch
):
    media = tmp_path / "spoken.wav"
    media.write_bytes(b"fixture media")
    data_dir = tmp_path / "private-data"
    saved_output = tmp_path / "symlink-loop"
    retry_output = tmp_path / "safe-retry-output"
    snapshot = {
        "schema_version": 2,
        "language": "auto",
        "timestamps": True,
        "max_processing_seconds": 900,
        "max_media_duration_seconds": 210.0,
        "max_output_segments": 45,
        "max_output_characters": 123,
        "max_downloads": 1,
        "retries": 0,
        "correction_rules_enabled": False,
        "correction_rules": [],
        "output_dir": str(saved_output.resolve()),
    }
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        task = store.create_local_task(media, processing_options=snapshot)
        store.fail_task(task.task_id, "ASR_FAILED", "prior attempt failed")

    original_resolve = Path.resolve

    def resolve_with_loop(path, strict=False):
        if path == saved_output:
            raise RuntimeError("Symlink loop")
        return original_resolve(path, strict=strict)

    class StubPipeline:
        def __init__(self, paths, **_kwargs):
            assert paths.output_dir == retry_output.resolve()

        def run_local(self, _path, **_kwargs):
            return ItemResult("success", output_path=str(retry_output / "result.md"))

        def close(self):
            pass

    monkeypatch.setattr(Path, "resolve", resolve_with_loop)
    monkeypatch.setattr(
        cli,
        "output_directory_permission_status",
        lambda _path: {"status": "ok", "detail": "private"},
    )
    monkeypatch.setattr(cli, "TranscriptionPipeline", StubPipeline)

    exit_code = cli.main(
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

    assert exit_code == 0
    assert result["output_dir"] == str(retry_output.resolve())
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        retried = store.get_task(task.task_id)
        assert retried is not None
        saved_options = json.loads(retried.processing_options_json)
        assert saved_options["language"] == "auto"
        assert saved_options["timestamps"] is True
        assert saved_options["output_dir"] == str(retry_output.resolve())


@pytest.mark.parametrize("schema_version", [1, 2])
def test_retry_failed_skips_unsafe_snapshot_directory_before_queue(
    tmp_path, capsys, monkeypatch, schema_version
):
    media = tmp_path / "spoken.wav"
    media.write_bytes(b"fixture media")
    data_dir = tmp_path / "private-data"
    saved_output = tmp_path / "shared-output"
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
        "output_dir": str(saved_output.resolve()),
    }
    if schema_version == 2:
        snapshot["max_processing_seconds"] = 900
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        task = store.create_local_task(media, processing_options=snapshot)
        store.fail_task(task.task_id, "ASR_FAILED", "prior attempt failed")

    monkeypatch.setattr(
        cli,
        "output_directory_permission_status",
        lambda _path: {"status": "unsafe", "detail": "shared snapshot ACL"},
    )
    monkeypatch.setattr(
        cli,
        "TranscriptionPipeline",
        lambda *_args, **_kwargs: pytest.fail("unsafe snapshot was queued"),
    )

    exit_code = cli.main(["retry-failed", "--data-dir", str(data_dir), "--json"])
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 5
    assert result["failed"] == 1
    assert result["items"][0]["error_code"] == "OUTPUT_PATH_UNSAFE"
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        current = store.get_task(task.task_id)
        assert current is not None
        assert current.state == "failed"


def test_retry_snapshot_permission_resolution_runtime_error_is_unknown_and_skipped(
    tmp_path, capsys, monkeypatch
):
    media = tmp_path / "spoken.wav"
    media.write_bytes(b"fixture media")
    data_dir = tmp_path / "private-data"
    saved_output = tmp_path / "output"
    snapshot = {
        "schema_version": 2,
        "language": "zh",
        "timestamps": False,
        "max_processing_seconds": 900,
        "max_media_duration_seconds": 3600,
        "max_output_segments": 20_000,
        "max_output_characters": 2_000_000,
        "max_downloads": 1,
        "retries": 0,
        "correction_rules_enabled": False,
        "correction_rules": [],
        "output_dir": str(saved_output.resolve()),
    }
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        task = store.create_local_task(media, processing_options=snapshot)
        store.fail_task(task.task_id, "ASR_FAILED", "prior attempt failed")

    original_resolve = Path.resolve
    saved_path_resolutions = 0

    def resolve_then_loop(path, strict=False):
        nonlocal saved_path_resolutions
        if path == saved_output:
            saved_path_resolutions += 1
            if saved_path_resolutions == 2:
                raise RuntimeError("Symlink loop appeared during validation")
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve_then_loop)
    monkeypatch.setattr(
        cli,
        "TranscriptionPipeline",
        lambda *_args, **_kwargs: pytest.fail("unverifiable snapshot was queued"),
    )

    exit_code = cli.main(["retry-failed", "--data-dir", str(data_dir), "--json"])
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 5
    assert result["failed"] == 1
    assert result["items"][0]["error_code"] == "OUTPUT_PATH_UNSAFE"
    assert result["output_dir_permissions"]["directories"] == [
        {
            "path": str(saved_output.resolve()),
            "status": "unknown",
            "detail": "保存的输出目录无法解析",
        }
    ]
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        current = store.get_task(task.task_id)
        assert current is not None
        assert current.state == "failed"


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
        assert parsed["max_processing_seconds"] == (
            900 if schema_version == 2 else 7200
        )


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
            return [
                ItemResult(
                    "success", title=title, output_path=str(retry_output / "result.md")
                )
            ]

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


def test_retry_summary_uses_null_output_dir_for_multiple_saved_directories(
    tmp_path, capsys, monkeypatch
):
    data_dir = tmp_path / "private-data"
    output_dirs = [tmp_path / "first-output", tmp_path / "second-output"]
    source_urls = [
        "https://www.douyin.com/video/retry-first-output",
        "https://www.douyin.com/video/retry-second-output",
    ]
    base_options = {
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
    }
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        tasks = [
            store.create_remote_task(
                source_url,
                f"retry-output-{index}",
                processing_options={**base_options, "output_dir": str(output_dir)},
            )
            for index, (source_url, output_dir) in enumerate(
                zip(source_urls, output_dirs, strict=True)
            )
        ]
        for task in tasks:
            store.fail_task(task.task_id, "NETWORK_FAILED", "prior failure")

    pipeline_paths = []

    class StubPipeline:
        def __init__(self, paths, **_kwargs):
            pipeline_paths.append(paths.output_dir)

        def run_urls(self, urls, *, title=None):
            assert len(urls) == 1
            return [
                ItemResult(
                    "success",
                    title=title,
                    output_path=str(pipeline_paths[-1] / "result.md"),
                )
            ]

        def close(self):
            pass

    monkeypatch.setattr(
        cli,
        "output_directory_permission_status",
        lambda _path: {"status": "ok", "detail": "private"},
    )
    monkeypatch.setattr(cli, "TranscriptionPipeline", StubPipeline)

    code = cli.main(["retry-failed", "--data-dir", str(data_dir), "--json"])
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert set(pipeline_paths) == {output.resolve() for output in output_dirs}
    assert result["output_dir"] is None
    assert {Path(item["output_path"]).parent for item in result["items"]} == {
        output.resolve() for output in output_dirs
    }
    assert {
        Path(entry["path"]) for entry in result["output_dir_permissions"]["directories"]
    } == {output.resolve() for output in output_dirs}


def test_legacy_retry_requires_explicit_current_defaults_opt_in(
    tmp_path, capsys, monkeypatch
):
    data_dir = tmp_path / "private-data"
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        task = store.create_remote_task("https://www.douyin.com/video/legacy", "legacy")
        store.fail_task(task.task_id, "NETWORK_FAILED", "temporary failure")

    pipeline_calls = []

    class StubPipeline:
        def __init__(self, _paths, **kwargs):
            pipeline_calls.append(kwargs)

        def run_urls(self, urls, *, title=None):
            assert urls == ["https://www.douyin.com/video/legacy"]
            return [ItemResult("success", title=title, video_id="legacy")]

    monkeypatch.setattr(cli, "TranscriptionPipeline", StubPipeline)
    skipped_code = cli.main(["retry-failed", "--data-dir", str(data_dir), "--json"])
    skipped = json.loads(capsys.readouterr().out)

    assert skipped_code == 0
    assert skipped["skipped"] == 1
    assert "LEGACY_CONFIG" in skipped["items"][0]["hint"]
    assert pipeline_calls == []
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        assert store.get_task("legacy").state == "failed"

    opted_code = cli.main(
        [
            "retry-failed",
            "--data-dir",
            str(data_dir),
            "--use-current-defaults",
            "--json",
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
            "https://v.douyin.com/retry-resolution/",
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

    class FailingResolutionClient:
        def resolve_source(self, _url, **_kwargs):
            raise CaptureClientError(
                "RESOLVE_TIMEOUT", "temporary isolated resolver failure"
            )

    original_pipeline = cli.TranscriptionPipeline

    def failing_service_pipeline(*args, **kwargs):
        kwargs["capture_service_client"] = FailingResolutionClient()
        return original_pipeline(*args, **kwargs)

    monkeypatch.setattr(cli, "TranscriptionPipeline", failing_service_pipeline)
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
