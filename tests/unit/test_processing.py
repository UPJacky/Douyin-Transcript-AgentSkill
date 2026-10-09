from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest
from douyin_transcript.downloader import (
    DownloadCancellation,
    DownloadError,
    MediaFile,
    MediaInvalidError,
)
from douyin_transcript.processing import (
    ProcessingTimeoutError,
    SupervisedProcessingWorker,
)


def test_worker_uses_json_frames_and_reuses_its_child(tmp_path):
    worker = SupervisedProcessingWorker()
    missing = tmp_path / "missing.wav"

    with pytest.raises(MediaInvalidError) as first:
        worker.validate_media(missing, max_duration_seconds=3600)
    first_process = worker._process
    assert first_process is not None and first_process.poll() is None

    with pytest.raises(MediaInvalidError) as second:
        worker.validate_media(missing, max_duration_seconds=3600)

    assert first.value.code == second.value.code == "MEDIA_NOT_FOUND"
    assert worker._process is first_process
    worker.close()
    assert worker._process is None
    assert first_process.poll() is not None


def test_default_worker_ignores_shadow_package_in_current_directory(tmp_path, monkeypatch):
    marker = tmp_path / "shadow-imported"
    shadow_package = tmp_path / "douyin_transcript"
    shadow_package.mkdir()
    (shadow_package / "__init__.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('loaded')\n",
        encoding="utf-8",
    )
    (shadow_package / "processing_worker.py").write_text(
        "raise RuntimeError('shadow worker executed')\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    worker = SupervisedProcessingWorker()
    try:
        with pytest.raises(MediaInvalidError) as error:
            worker.validate_media(
                tmp_path / "missing.wav", max_duration_seconds=3600
            )

        process = worker._process
        assert process is not None and process.poll() is None
        assert "-P" in process.args
        assert error.value.code == "MEDIA_NOT_FOUND"
        assert not marker.exists()
    finally:
        worker.close()


def test_worker_timeout_terminates_the_child_process(tmp_path):
    worker = SupervisedProcessingWorker(
        command=(
            sys.executable,
            "-c",
            "import sys,time; sys.stdin.buffer.readline(); time.sleep(30)",
        )
    )
    deadline = time.monotonic() + 0.2

    with pytest.raises(ProcessingTimeoutError):
        worker.validate_media(
            tmp_path / "slow.wav",
            max_duration_seconds=3600,
            deadline=deadline,
        )

    assert worker._process is None


def test_worker_default_timeout_uses_one_absolute_deadline(tmp_path, monkeypatch):
    import douyin_transcript.processing as processing_module

    monkeypatch.setattr(processing_module, "DEFAULT_MAX_PROCESSING_SECONDS", 0.2)
    worker = SupervisedProcessingWorker(
        command=(
            sys.executable,
            "-c",
            "import sys,time; sys.stdin.buffer.readline(); time.sleep(30)",
        )
    )

    with pytest.raises(ProcessingTimeoutError):
        worker.validate_media(
            tmp_path / "slow.wav",
            max_duration_seconds=3600,
        )

    assert worker._process is None


def test_worker_cancellation_terminates_child_during_validation(tmp_path, monkeypatch):
    marker = tmp_path / "validation-started"
    script = (
        "import pathlib,sys,time; sys.stdin.buffer.readline(); "
        f"pathlib.Path({str(marker)!r}).write_text('started'); time.sleep(30)"
    )
    worker = SupervisedProcessingWorker(command=(sys.executable, "-c", script))
    cancellation = DownloadCancellation()
    failures = []
    started = threading.Event()
    ensure_started = worker._ensure_started

    def observe_started():
        process = ensure_started()
        started.set()
        return process

    monkeypatch.setattr(worker, "_ensure_started", observe_started)

    def validate():
        try:
            worker.validate_media(
                tmp_path / "slow.wav",
                max_duration_seconds=3600,
                deadline=time.monotonic() + 60,
                cancellation=cancellation,
            )
        except DownloadError as exc:
            failures.append(exc)

    request_thread = threading.Thread(target=validate, daemon=True)
    request_thread.start()
    assert started.wait(timeout=2)
    deadline = time.monotonic() + 2
    while not marker.is_file() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert marker.is_file()
    process = worker._process
    assert process is not None and process.poll() is None

    cancellation.cancel()
    request_thread.join(timeout=3)

    assert not request_thread.is_alive()
    assert worker._process is None
    assert process.poll() is not None
    assert len(failures) == 1
    assert failures[0].code == "CANCELLED"


def test_pipeline_records_processing_timeout_as_failed_task(tmp_path, monkeypatch):
    import douyin_transcript.pipeline as pipeline_module
    from douyin_transcript.config import RuntimePaths
    from douyin_transcript.tasks import TaskStore

    media_path = tmp_path / "sample.wav"
    media_path.write_bytes(b"test media")
    paths = RuntimePaths(
        data_dir=tmp_path / "data",
        output_dir=tmp_path / "output",
        config_path=tmp_path / "data" / "config.toml",
    )

    class TimedOutWorker:
        def validate_media(self, path, **_kwargs):
            return MediaFile(Path(path), "wav", 10, 5.0)

        def transcribe(self, *_args, **_kwargs):
            raise ProcessingTimeoutError()

        def close(self):
            return None

    monkeypatch.setattr(pipeline_module, "SupervisedProcessingWorker", TimedOutWorker)
    pipeline = pipeline_module.TranscriptionPipeline(paths)

    result = pipeline.run_local(media_path)

    assert result.status == "failed"
    assert result.error_code == "PROCESSING_TIMEOUT"
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        task = store.list_tasks()[0]
        assert task.state == "failed"
        assert task.error_code == "PROCESSING_TIMEOUT"
