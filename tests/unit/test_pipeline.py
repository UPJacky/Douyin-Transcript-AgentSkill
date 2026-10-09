from __future__ import annotations

import _thread
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import douyin_transcript.pipeline as pipeline_module
import pytest
from douyin_transcript.asr import TranscriptionResult, TranscriptSegment
from douyin_transcript.capture import MediaCandidate, VideoMetadata
from douyin_transcript.config import RuntimePaths
from douyin_transcript.corrections import CorrectionRule, CorrectionWorkBudget
from douyin_transcript.downloader import DownloadError, MediaFile, MediaIdentity
from douyin_transcript.naming import candidate_output_paths
from douyin_transcript.output import json_summary, make_summary
from douyin_transcript.pipeline import (
    MAX_URL_BATCH_ITEMS,
    TranscriptionPipeline,
    validate_url_batch,
)
from douyin_transcript.tasks import TaskStore
from douyin_transcript.urls import ResolvedInput


def _paths(tmp_path: Path) -> RuntimePaths:
    return RuntimePaths(
        data_dir=tmp_path / "data",
        output_dir=tmp_path / "output",
        config_path=tmp_path / "data" / "config.toml",
    )


def _validator(path: Path) -> MediaFile:
    return MediaFile(Path(path), "wav", 10, 5.0)


class _ASR:
    def transcribe(self, _path: Path, *, language: str) -> TranscriptionResult:
        return TranscriptionResult(
            (TranscriptSegment(0.0, 2.0, " 你好。"),),
            5.0,
            "zh" if language == "zh" else "en",
            "test-model",
            "balanced",
        )


def _asr_factory(_data_dir: Path, _profile: str, **_kwargs) -> _ASR:
    return _ASR()


def test_local_pipeline_writes_markdown_and_summary_excludes_body(tmp_path):
    media = tmp_path / "sensitive-user" / "private-media" / "sample.wav"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"fake fixture accepted by validator")
    pipeline = TranscriptionPipeline(
        _paths(tmp_path), media_validator=_validator, asr_factory=_asr_factory
    )

    result = pipeline.run_local(media, title="测试标题")

    assert result.status == "success"
    output = Path(result.output_path or "")
    content = output.read_text(encoding="utf-8")
    assert "你好。" in content
    assert 'task_id: "local:' in content
    assert 'source: "local_file"' in content
    assert "source_url:" not in content
    assert "sensitive-user" not in content
    assert "private-media" not in content
    assert "你好。" not in json_summary(make_summary([result], output.parent))
    with TaskStore(_paths(tmp_path).data_dir / "tasks.sqlite3") as store:
        tasks = store.list_tasks()
        assert len(tasks) == 1
        task = tasks[0]
        assert task.local_path == str(media.resolve())
        assert task.source_url.endswith("sensitive-user/private-media/sample.wav")


def test_local_pipeline_reuses_its_preflight_media_validation(tmp_path, monkeypatch):
    media = tmp_path / "sample.wav"
    media.write_bytes(b"fake fixture accepted by validator")
    calls = []
    validated = MediaFile(media, "wav", media.stat().st_size, 5.0)

    def validator(path):
        calls.append(Path(path))
        return validated

    class ValidationAwareASR:
        def __init__(self, *_args, **_kwargs):
            self.received_validation = None

        def transcribe(self, _path, *, language, validated_media=None):
            self.received_validation = validated_media
            return TranscriptionResult(
                (TranscriptSegment(0.0, 2.0, "已验证媒体。"),),
                5.0,
                language,
                "test-model",
                "balanced",
            )

    monkeypatch.setattr(pipeline_module, "LocalASR", ValidationAwareASR)
    pipeline = TranscriptionPipeline(
        _paths(tmp_path),
        media_validator=validator,
        asr_factory=ValidationAwareASR,
    )

    result = pipeline.run_local(media)

    assert result.status == "success"
    assert calls == [media]
    assert pipeline._asr.received_validation is validated


def test_concurrent_local_retries_reserve_once_and_report_the_race_as_skipped(tmp_path):
    media = tmp_path / "retry-race.wav"
    media.write_bytes(b"original retry input")
    paths = _paths(tmp_path)
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        task = store.create_local_task(media)
        claimed = store.claim_task(task.task_id, "original-run")
        assert claimed is not None
        store.fail_task(
            task.task_id,
            "ASR_FAILED",
            worker_id="original-run",
            claim_generation=claimed.claim_generation,
        )
        store.retry_failed()

    validation_barrier = threading.Barrier(2)
    asr_calls = []

    def validator(path):
        validation_barrier.wait(timeout=3)
        return _validator(path)

    def asr_factory(*_args, **_kwargs):
        asr_calls.append(True)
        return _ASR()

    first = TranscriptionPipeline(paths, media_validator=validator, asr_factory=asr_factory)
    second = TranscriptionPipeline(paths, media_validator=validator, asr_factory=asr_factory)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    pipeline.run_local, media, retry_task_id=task.task_id
                )
                for pipeline in (first, second)
            ]
            results = [future.result(timeout=5) for future in futures]
    finally:
        first.close()
        second.close()

    assert sorted(result.status for result in results) == ["skipped", "success"]
    assert len(asr_calls) == 1
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        completed = store.get_task(task.task_id)
        assert completed is not None and store.is_completed_valid(task.task_id)


def test_output_permission_error_does_not_mark_local_task_completed(tmp_path):
    media = tmp_path / "sample.wav"
    media.write_bytes(b"fake fixture accepted by validator")

    def reject_output(*_args, **_kwargs):
        raise PermissionError("output directory is read-only")

    pipeline = TranscriptionPipeline(
        _paths(tmp_path),
        media_validator=_validator,
        asr_factory=_asr_factory,
        markdown_writer=reject_output,
    )

    result = pipeline.run_local(media)

    assert result.status == "failed"
    assert result.error_code == "OUTPUT_NOT_WRITABLE"
    with TaskStore(_paths(tmp_path).data_dir / "tasks.sqlite3") as store:
        task = store.list_tasks()[0]
        assert task.state == "failed"
        assert task.completed_at is None


def test_timeline_escapes_untrusted_title_and_asr_text(tmp_path):
    media = tmp_path / "sample.wav"
    media.write_bytes(b"fake fixture accepted by validator")
    hostile = "![x](https://example.invalid/pixel) <script>alert(1)</script>"

    class HostileASR:
        def transcribe(self, _path: Path, *, language: str) -> TranscriptionResult:
            return TranscriptionResult(
                (TranscriptSegment(0.0, 2.0, hostile),),
                5.0,
                language,
                "test-model",
                "balanced",
            )

    pipeline = TranscriptionPipeline(
        _paths(tmp_path),
        timestamps=True,
        media_validator=_validator,
        asr_factory=lambda *_args, **_kwargs: HostileASR(),
    )
    result = pipeline.run_local(media, title=hostile)
    main_path = Path(result.output_path or "")
    timeline_path = main_path.with_name(f"{main_path.stem}_timeline.md")

    assert result.status == "success"
    timeline = timeline_path.read_text(encoding="utf-8")
    assert r"\!\[x\]\(https\:\/\/example\.invalid\/pixel\)" in timeline
    assert r"\<script\>alert\(1\)\<\/script\>" in timeline
    assert "![x](https://example.invalid/pixel)" not in timeline
    assert "<script>" not in timeline
    with TaskStore(_paths(tmp_path).data_dir / "tasks.sqlite3") as store:
        task = store.list_tasks()[0]
        assert task.timeline_required
        assert task.timeline_path == str(timeline_path.resolve())
        assert task.timeline_sha256 is not None
        assert store.is_completed_valid(task.task_id)

    assert pipeline.run_local(media, title=hostile).status == "skipped"
    timeline_path.write_text("edited sidecar", encoding="utf-8")
    invalid = pipeline.run_local(media, title=hostile)
    assert invalid.status == "failed"
    assert invalid.error_code == "OUTPUT_INVALID"


def test_timeline_collision_preserves_existing_regular_file_and_uses_suffix(tmp_path):
    media = tmp_path / "sample.wav"
    media.write_bytes(b"fake fixture accepted by validator")
    paths = _paths(tmp_path)
    paths.output_dir.mkdir(parents=True)
    title = "timeline collision"
    expected_main = next(candidate_output_paths(paths.output_dir, title, None))
    first_sidecar = expected_main.with_name(f"{expected_main.stem}_timeline.md")
    first_sidecar.write_text("existing user file", encoding="utf-8")

    pipeline = TranscriptionPipeline(
        paths,
        timestamps=True,
        media_validator=_validator,
        asr_factory=_asr_factory,
    )
    result = pipeline.run_local(media, title=title)

    second_sidecar = expected_main.with_name(f"{expected_main.stem}_timeline__2.md")
    assert result.status == "success"
    assert first_sidecar.read_text(encoding="utf-8") == "existing user file"
    assert second_sidecar.is_file()
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        task = store.list_tasks()[0]
        assert task.timeline_path == str(second_sidecar.resolve())
        assert store.is_completed_valid(task.task_id)


def test_timeline_symlink_collision_is_not_resolved_or_overwritten(tmp_path):
    media = tmp_path / "sample.wav"
    media.write_bytes(b"fake fixture accepted by validator")
    paths = _paths(tmp_path)
    paths.output_dir.mkdir(parents=True)
    title = "timeline symlink collision"
    expected_main = next(candidate_output_paths(paths.output_dir, title, None))
    first_sidecar = expected_main.with_name(f"{expected_main.stem}_timeline.md")
    external_target = tmp_path / "external.md"
    external_target.write_text("outside target", encoding="utf-8")
    try:
        first_sidecar.symlink_to(external_target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"filesystem does not permit symlink creation: {type(exc).__name__}")

    pipeline = TranscriptionPipeline(
        paths,
        timestamps=True,
        media_validator=_validator,
        asr_factory=_asr_factory,
    )
    result = pipeline.run_local(media, title=title)

    second_sidecar = expected_main.with_name(f"{expected_main.stem}_timeline__2.md")
    assert result.status == "success"
    assert first_sidecar.is_symlink()
    assert external_target.read_text(encoding="utf-8") == "outside target"
    assert second_sidecar.is_file()
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        task = store.list_tasks()[0]
        assert task.timeline_path == str(second_sidecar.resolve())
        assert store.is_completed_valid(task.task_id)


def test_timeline_publish_is_atomic_and_cleans_staging_file_on_failure(
    tmp_path, monkeypatch
):
    import douyin_transcript.markdown as markdown_module

    def fail_publish(_source, _destination):
        raise OSError("simulated timeline publication failure")

    monkeypatch.setattr(markdown_module, "_publish_no_replace", fail_publish)
    pipeline = TranscriptionPipeline(
        _paths(tmp_path), media_validator=_validator, asr_factory=_asr_factory
    )
    output_path = tmp_path / "output" / "transcript.md"
    output_path.parent.mkdir()

    with pytest.raises(OSError, match="simulated timeline publication failure"):
        pipeline._write_timeline(output_path, "title", "[00:00] transcript")

    assert not list(output_path.parent.glob("*_timeline*.md"))
    assert not list(output_path.parent.glob(".*.tmp"))


def test_local_pipeline_skips_completed_and_force_writes_new_file(tmp_path):
    media = tmp_path / "sample.wav"
    media.write_bytes(b"fake fixture accepted by validator")
    paths = _paths(tmp_path)
    options = {"media_validator": _validator, "asr_factory": _asr_factory}

    first = TranscriptionPipeline(paths, **options).run_local(media, title="Same title")
    second = TranscriptionPipeline(paths, **options).run_local(
        media, title="Same title"
    )
    forced = TranscriptionPipeline(paths, force=True, **options).run_local(
        media, title="Same title"
    )

    assert first.status == "success"
    assert second.status == "skipped"
    assert forced.status == "success"
    assert first.output_path != forced.output_path
    assert Path(first.output_path or "").is_file()
    assert Path(forced.output_path or "").is_file()


class _Capture:
    def __init__(self, _profile_dir: Path) -> None:
        self.closed = False

    def start(self) -> _Capture:
        return self

    def capture(self, item: ResolvedInput) -> VideoMetadata:
        return VideoMetadata(
            item.video_id,
            "远端标题",
            "作者",
            None,
            item.canonical_url,
            5.0,
            [
                MediaCandidate(
                    "https://media.douyinvod.com/audio.m4a?sig=secret",
                    "audio",
                    "audio/mp4",
                )
            ],
        )

    def close(self) -> None:
        self.closed = True


def _remote_resolver(_value: str) -> ResolvedInput:
    return ResolvedInput(
        "https://www.douyin.com/video/123",
        "https://www.douyin.com/video/123",
        "123",
        "direct",
    )


def test_remote_pipeline_uses_capture_download_and_persists_task(tmp_path):
    paths = _paths(tmp_path)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    forged_output = paths.output_dir / "untrusted-existing.md"
    forged_output.write_text(
        '---\nvideo_id: "123"\n---\n\n未验证的旧内容\n', encoding="utf-8"
    )
    capture_instances: list[_Capture] = []
    expected_durations: list[float | None] = []

    def capture_factory(profile_dir: Path) -> _Capture:
        capture = _Capture(profile_dir)
        capture_instances.append(capture)
        return capture

    def downloader(_video_id: str, _candidates, cache_dir: Path, **_kwargs) -> MediaFile:
        expected_durations.append(_kwargs.get("expected_duration_seconds"))
        cache_dir.mkdir(parents=True)
        media = cache_dir / "123-audio-hash.m4a"
        media.write_bytes(b"fake media")
        return MediaFile(media, "mp4", media.stat().st_size, 5.0)

    pipeline = TranscriptionPipeline(
        paths,
        capture_factory=capture_factory,
        downloader=downloader,
        media_validator=_validator,
        asr_factory=_asr_factory,
        url_resolver=_remote_resolver,
    )
    result = pipeline.run_urls(["https://www.douyin.com/video/123"])[0]

    assert result.status == "success"
    assert result.video_id == "123"
    assert Path(result.output_path or "") != forged_output
    assert "未验证的旧内容" in forged_output.read_text(encoding="utf-8")
    assert capture_instances[0].closed
    assert "你好。" not in str(result.to_dict())
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        task = store.get_task("123")
        assert task is not None and task.state == "completed"
        assert task.output_sha256 is not None
        assert task.source_duration_seconds == 5.0
        assert store.is_completed_valid("123")
    assert expected_durations == [5.0]


def test_default_remote_pipeline_accepts_validated_mediafile_decoder(
    monkeypatch, tmp_path
):
    import douyin_transcript.downloader as downloader_module

    body = b"validated remote audio"
    requests = []

    class FakeSocket:
        def settimeout(self, _timeout):
            pass

    class FakeConnection:
        def __init__(self):
            self.sock = FakeSocket()

        def close(self):
            pass

    class FakeResponse:
        status = 200

        def __init__(self):
            self.offset = 0

        def getheader(self, name, default=None):
            return {
                "Content-Type": "audio/mp4",
                "Content-Length": str(len(body)),
            }.get(name, default)

        def read(self, size):
            chunk = body[self.offset : self.offset + size]
            self.offset += len(chunk)
            return chunk

        def close(self):
            pass

    def requester(url, **_kwargs):
        requests.append(url)
        return FakeConnection(), FakeResponse()

    def validated_media(path):
        info = Path(path).stat()
        return MediaFile(
            Path(path), "mp4", info.st_size, 5.0, MediaIdentity.from_stat(info)
        )

    class ValidationAwareASR:
        def __init__(self):
            self.validated_media = None

        def transcribe(self, _path, *, language, validated_media=None):
            self.validated_media = validated_media
            return TranscriptionResult(
                (TranscriptSegment(0.0, 2.0, "远端已通过验证。"),),
                5.0,
                language,
                "test-model",
                "balanced",
            )

    asr = ValidationAwareASR()
    forwarded_deadlines = []
    monkeypatch.setattr(pipeline_module, "LocalASR", ValidationAwareASR)
    actual_download_media = downloader_module.download_media

    def default_downloader(video_id, candidates, cache_dir, **kwargs):
        forwarded_deadlines.append(kwargs.get("absolute_deadline"))
        return actual_download_media(
            video_id,
            candidates,
            cache_dir,
            requester=requester,
            sleeper=lambda _seconds: None,
            **kwargs,
        )

    monkeypatch.setattr(pipeline_module, "download_media", default_downloader)
    pipeline = TranscriptionPipeline(
        _paths(tmp_path),
        capture_factory=_Capture,
        downloader=default_downloader,
        media_validator=validated_media,
        asr_factory=lambda *_args, **_kwargs: asr,
        url_resolver=_remote_resolver,
    )

    result = pipeline.run_urls(["https://www.douyin.com/video/123"])[0]

    assert result.status == "success"
    assert len(requests) == 1
    assert len(forwarded_deadlines) == 1
    assert isinstance(forwarded_deadlines[0], float)
    assert asr.validated_media is not None
    assert asr.validated_media.path.is_file()
    assert asr.validated_media.identity == MediaIdentity.from_stat(
        asr.validated_media.path.stat()
    )


def test_remote_processing_deadline_reports_processing_timeout(
    monkeypatch, tmp_path
):
    import douyin_transcript.downloader as downloader_module

    class FakeConnection:
        def close(self):
            pass

    class FakeResponse:
        def close(self):
            pass

    def slow_requester(_url, **_kwargs):
        time.sleep(1.05)
        return FakeConnection(), FakeResponse()

    monkeypatch.setattr(downloader_module, "open_pinned_https", slow_requester)
    paths = _paths(tmp_path)
    pipeline = TranscriptionPipeline(
        paths,
        capture_factory=_Capture,
        url_resolver=_remote_resolver,
        max_processing_seconds=1,
    )

    result = pipeline.run_urls(["https://www.douyin.com/video/123"])[0]

    assert result.status == "failed"
    assert result.error_code == "PROCESSING_TIMEOUT"
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        task = store.get_task("123")
        assert task is not None
        assert task.state == "failed"
        assert task.error_code == "PROCESSING_TIMEOUT"


def test_keyboard_interrupt_cancels_slow_download_and_releases_claim(
    monkeypatch, tmp_path
):
    import douyin_transcript.downloader as downloader_module

    read_started = threading.Event()
    connection_closed = threading.Event()
    interrupt_sent: list[bool] = []
    captures: list[_Capture] = []

    class FakeSocket:
        def settimeout(self, _timeout):
            pass

    class SlowConnection:
        def __init__(self):
            self.sock = FakeSocket()

        def close(self):
            connection_closed.set()

    class SlowResponse:
        status = 200

        def __init__(self):
            self._connection = None

        def getheader(self, name, default=None):
            return {"Content-Type": "audio/mp4", "Content-Length": "100"}.get(
                name, default
            )

        def read1(self, _size):
            read_started.set()
            if connection_closed.wait(timeout=10):
                raise OSError("connection closed by cancellation")
            return b"x" * 100

        read = read1

        def close(self):
            pass

    connection = SlowConnection()

    def slow_requester(_url, **_kwargs):
        return connection, SlowResponse()

    def capture_factory(profile_dir: Path):
        capture = _Capture(profile_dir)
        captures.append(capture)
        return capture

    monkeypatch.setattr(downloader_module, "open_pinned_https", slow_requester)
    paths = _paths(tmp_path)
    pipeline = TranscriptionPipeline(
        paths,
        capture_factory=capture_factory,
        url_resolver=_remote_resolver,
    )

    def interrupt_when_reading():
        interrupt_sent.append(read_started.wait(timeout=3))
        _thread.interrupt_main()

    interrupter = threading.Thread(target=interrupt_when_reading, daemon=True)
    interrupter.start()
    started = time.monotonic()
    with pytest.raises(KeyboardInterrupt):
        pipeline.run_urls(["https://www.douyin.com/video/123"])
    elapsed = time.monotonic() - started
    interrupter.join(timeout=1)

    assert interrupt_sent == [True]
    assert elapsed < 1.5
    assert connection_closed.is_set()
    assert captures and captures[0].closed
    assert not interrupter.is_alive()
    assert not list((paths.data_dir / "media-cache").glob(".*.part"))
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        task = store.get_task("123")
        assert task is not None
        assert task.state == "failed"
        assert task.claimed_by is None
        assert task.error_code == "CANCELLED"


def test_keyboard_interrupt_during_capture_start_closes_created_capture(
    tmp_path,
):
    start_entered = threading.Event()
    interrupt_sent: list[bool] = []

    class BlockingCapture(_Capture):
        def start(self):
            start_entered.set()
            while True:
                time.sleep(0.01)

    captures: list[BlockingCapture] = []

    def capture_factory(profile_dir: Path):
        capture = BlockingCapture(profile_dir)
        captures.append(capture)
        return capture

    paths = _paths(tmp_path)
    pipeline = TranscriptionPipeline(
        paths,
        capture_factory=capture_factory,
        url_resolver=_remote_resolver,
    )

    def interrupt_during_start():
        interrupt_sent.append(start_entered.wait(timeout=3))
        _thread.interrupt_main()

    interrupter = threading.Thread(target=interrupt_during_start, daemon=True)
    interrupter.start()
    started = time.monotonic()
    with pytest.raises(KeyboardInterrupt):
        pipeline.run_urls(["https://www.douyin.com/video/123"])
    elapsed = time.monotonic() - started
    interrupter.join(timeout=1)

    assert interrupt_sent == [True]
    assert elapsed < 1.5
    assert captures and captures[0].closed
    assert not interrupter.is_alive()
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        task = store.get_task("123")
        assert task is not None
        assert task.state == "failed"
        assert task.claimed_by is None
        assert task.error_code == "CANCELLED"


def test_pipeline_cancels_processing_when_task_claim_is_recovered(tmp_path):
    paths = _paths(tmp_path)
    database = paths.data_dir / "tasks.sqlite3"
    pipeline = TranscriptionPipeline(paths, heartbeat_interval_seconds=0.01)

    with TaskStore(database) as store:
        created = store.create_remote_task(
            "https://www.douyin.com/video/claim-lost", "claim-lost"
        )
        claimed = store.claim_task(created.task_id, pipeline._worker_id)
        assert claimed is not None

        with pipeline._keep_claim_alive(
            store,
            claimed.task_id,
            claim_generation=claimed.claim_generation,
        ) as cancellation:
            with TaskStore(database) as recovery_store:
                recovered = recovery_store.recover_interrupted(stale_after_seconds=0)
            assert [(item.from_state, item.to_state) for item in recovered] == [
                ("resolving", "pending")
            ]
            assert cancellation.wait(timeout=1)
            current = store.get_task(claimed.task_id)
            assert current is not None
            assert current.state == "pending"
            assert current.claimed_by is None
            with pytest.raises(RuntimeError, match="no longer owns"):
                store.fail_task(
                    claimed.task_id,
                    "LATE_FAILURE",
                    worker_id=pipeline._worker_id,
                    claim_generation=claimed.claim_generation,
                )

    pipeline.close()


def test_keyboard_interrupt_cancels_supervised_download_validation(
    monkeypatch, tmp_path
):
    import douyin_transcript.downloader as downloader_module

    validation_started = threading.Event()
    validation_cancelled = threading.Event()
    worker_closed = threading.Event()
    interrupt_sent: list[bool] = []

    class FakeSocket:
        def settimeout(self, _timeout):
            pass

    class FastConnection:
        def __init__(self):
            self.sock = FakeSocket()

        def close(self):
            pass

    class FastResponse:
        status = 200

        def __init__(self):
            self._body = b"synthetic media bytes"
            self._read = False

        def getheader(self, name, default=None):
            return {
                "Content-Type": "audio/mp4",
                "Content-Length": str(len(self._body)),
            }.get(name, default)

        def read1(self, _size):
            if self._read:
                return b""
            self._read = True
            return self._body

        read = read1

        def close(self):
            pass

    class BlockingProcessingWorker:
        def __init__(self):
            self.cancel_token = None

        def validate_media(
            self, _path, *, max_duration_seconds, deadline=None, cancellation=None
        ):
            self.cancel_token = cancellation
            validation_started.set()
            assert cancellation is not None
            while not cancellation.wait(0.01):
                pass
            validation_cancelled.set()
            raise DownloadError("CANCELLED", "decoder request cancelled")

        def close(self):
            worker_closed.set()

    workers: list[BlockingProcessingWorker] = []

    def worker_factory():
        worker = BlockingProcessingWorker()
        workers.append(worker)
        return worker

    monkeypatch.setattr(downloader_module, "open_pinned_https", lambda *_a, **_k: (
        FastConnection(), FastResponse()
    ))
    monkeypatch.setattr(pipeline_module, "SupervisedProcessingWorker", worker_factory)
    paths = _paths(tmp_path)
    pipeline = TranscriptionPipeline(
        paths,
        capture_factory=_Capture,
        url_resolver=_remote_resolver,
    )

    def interrupt_during_validation():
        interrupt_sent.append(validation_started.wait(timeout=3))
        _thread.interrupt_main()

    interrupter = threading.Thread(target=interrupt_during_validation, daemon=True)
    interrupter.start()
    started = time.monotonic()
    with pytest.raises(KeyboardInterrupt):
        pipeline.run_urls(["https://www.douyin.com/video/123"])
    elapsed = time.monotonic() - started
    interrupter.join(timeout=1)

    assert interrupt_sent == [True]
    assert elapsed < 1.5
    assert validation_cancelled.is_set()
    assert worker_closed.is_set()
    assert not interrupter.is_alive()
    assert not list((paths.data_dir / "media-cache").glob(".*.part"))
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        task = store.get_task("123")
        assert task is not None
        assert task.state == "failed"
        assert task.claimed_by is None
        assert task.error_code == "CANCELLED"


def test_remote_pipeline_rejects_media_shorter_than_page_metadata(tmp_path):
    paths = _paths(tmp_path)

    def downloader(_video_id: str, _candidates, cache_dir: Path, **_kwargs) -> MediaFile:
        cache_dir.mkdir(parents=True, exist_ok=True)
        media = cache_dir / "123-audio-short.m4a"
        media.write_bytes(b"short media")
        return MediaFile(media, "mp4", media.stat().st_size, 1.0)

    def short_validator(path: Path) -> MediaFile:
        return MediaFile(Path(path), "mp4", Path(path).stat().st_size, 1.0)

    pipeline = TranscriptionPipeline(
        paths,
        capture_factory=_Capture,
        downloader=downloader,
        media_validator=short_validator,
        asr_factory=_asr_factory,
        url_resolver=_remote_resolver,
    )

    result = pipeline.run_urls(["https://www.douyin.com/video/123"])[0]

    assert result.status == "failed"
    assert result.error_code == "MEDIA_INCOMPLETE"
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        task = store.get_task("123")
        assert task is not None and task.state == "failed"
        assert task.source_duration_seconds == 5.0


def test_remote_download_failure_is_durable_and_retryable(tmp_path):
    paths = _paths(tmp_path)

    def downloader(*_args, **_kwargs):
        raise DownloadError("NETWORK_FAILED", "network unavailable")

    pipeline = TranscriptionPipeline(
        paths,
        capture_factory=_Capture,
        downloader=downloader,
        media_validator=_validator,
        asr_factory=_asr_factory,
        url_resolver=_remote_resolver,
    )
    result = pipeline.run_urls(["https://www.douyin.com/video/123"])[0]

    assert result.status == "failed"
    assert result.error_code == "NETWORK_FAILED"
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        failed = store.get_task("123")
        assert failed is not None and failed.state == "failed"
        queued = store.retry_failed()
        assert [task.task_id for task in queued] == ["123"]
        assert queued[0].state == "pending"


def test_remote_retry_reuses_valid_cached_media_without_browser_or_download(tmp_path):
    paths = _paths(tmp_path)
    cached_media = paths.data_dir / "media-cache" / "123-audio-0123456789abcdef.m4a"
    cached_media.parent.mkdir(parents=True)
    cached_media.write_bytes(b"cached validated media")
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        created = store.create_remote_task(
            "https://www.douyin.com/video/123", "123", title="已保存标题"
        )
        claimed = store.claim_task(created.task_id, "failed-run")
        assert claimed is not None
        downloading = store.transition(
            created.task_id,
            "downloading",
            worker_id="failed-run",
            claim_generation=claimed.claim_generation,
        )
        downloaded = store.transition(
            created.task_id,
            "downloaded",
            worker_id="failed-run",
            claim_generation=downloading.claim_generation,
            media_path=cached_media,
            title="已保存标题",
        )
        transcribing = store.transition(
            created.task_id,
            "transcribing",
            worker_id="failed-run",
            claim_generation=downloaded.claim_generation,
        )
        store.fail_task(
            created.task_id,
            "ASR_FAILED",
            worker_id="failed-run",
            claim_generation=transcribing.claim_generation,
        )
        assert store.retry_failed(task_id=created.task_id)[0].state == "pending"

    pipeline = TranscriptionPipeline(
        paths,
        capture_factory=lambda *_args: pytest.fail("cached retry must not start capture"),
        downloader=lambda *_args, **_kwargs: pytest.fail(
            "cached retry must not download media again"
        ),
        media_validator=_validator,
        asr_factory=_asr_factory,
        url_resolver=_remote_resolver,
    )
    result = pipeline.run_urls(["https://www.douyin.com/video/123"])[0]
    pipeline.close()

    assert result.status == "success"
    assert result.output_path is not None
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        completed = store.get_task(created.task_id)
        assert completed is not None
        assert completed.state == "completed"
        assert completed.media_path == str(cached_media.resolve())


def test_remote_pipeline_recovers_a_stale_interrupted_download(tmp_path):
    paths = _paths(tmp_path)
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        store.create_remote_task("https://www.douyin.com/video/123", "123")
        claimed = store.claim_task("123", "crashed-worker")
        assert claimed is not None
        store.transition(
            "123", "downloading", worker_id="crashed-worker",
            claim_generation=claimed.claim_generation,
        )

    def downloader(_video_id: str, _candidates, cache_dir: Path, **_kwargs) -> MediaFile:
        cache_dir.mkdir(parents=True)
        media = cache_dir / "123-audio-hash.m4a"
        media.write_bytes(b"fake media")
        return MediaFile(media, "mp4", media.stat().st_size, 5.0)

    pipeline = TranscriptionPipeline(
        paths,
        capture_factory=_Capture,
        downloader=downloader,
        media_validator=_validator,
        asr_factory=_asr_factory,
        url_resolver=_remote_resolver,
        stale_after_seconds=0,
    )

    result = pipeline.run_urls(["https://www.douyin.com/video/123"])[0]

    assert result.status == "success"
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        recovered = store.get_task("123")
        assert recovered is not None and recovered.state == "completed"


def test_local_pipeline_rejects_overlong_media_before_asr_factory(tmp_path):
    media = tmp_path / "long.wav"
    media.write_bytes(b"fake fixture accepted by validator")
    factory_calls = []

    def long_validator(path: Path) -> MediaFile:
        return MediaFile(path, "wav", path.stat().st_size, 61 * 60)

    pipeline = TranscriptionPipeline(
        _paths(tmp_path),
        media_validator=long_validator,
        asr_factory=lambda *_args, **_kwargs: factory_calls.append(True),
    )

    result = pipeline.run_local(media)

    assert result.status == "failed"
    assert result.error_code == "MEDIA_TOO_LONG"
    assert factory_calls == []


def test_remote_pipeline_bounds_downloads_and_keeps_asr_serial(tmp_path):
    paths = _paths(tmp_path)
    download_barrier = threading.Barrier(2)
    state_lock = threading.Lock()
    active_downloads = 0
    maximum_downloads = 0
    active_asr = 0
    maximum_asr = 0
    retry_values: list[int] = []

    def resolver(value: str) -> ResolvedInput:
        video_id = value.rsplit("/", 1)[-1]
        return ResolvedInput(value, value, video_id, "direct")

    def downloader(video_id: str, _candidates, cache_dir: Path, **kwargs) -> MediaFile:
        nonlocal active_downloads, maximum_downloads
        retry_values.append(kwargs["retries"])
        with state_lock:
            active_downloads += 1
            maximum_downloads = max(maximum_downloads, active_downloads)
        try:
            download_barrier.wait(timeout=3)
            time.sleep(0.02)
            cache_dir.mkdir(parents=True, exist_ok=True)
            media = cache_dir / f"{video_id}-audio-{'a' * 16}.m4a"
            media.write_bytes(b"fake media")
            return MediaFile(media, "mp4", media.stat().st_size, 5.0)
        finally:
            with state_lock:
                active_downloads -= 1

    class SerialASR:
        def transcribe(self, _path: Path, *, language: str) -> TranscriptionResult:
            nonlocal active_asr, maximum_asr
            with state_lock:
                active_asr += 1
                maximum_asr = max(maximum_asr, active_asr)
            try:
                time.sleep(0.02)
                return TranscriptionResult(
                    (TranscriptSegment(0, 1, "你好。"),), 5.0, language, "test", "balanced"
                )
            finally:
                with state_lock:
                    active_asr -= 1

    pipeline = TranscriptionPipeline(
        paths,
        max_downloads=2,
        retries=1,
        capture_factory=_Capture,
        downloader=downloader,
        media_validator=_validator,
        asr_factory=lambda *_args, **_kwargs: SerialASR(),
        url_resolver=resolver,
    )

    results = pipeline.run_urls(
        ["https://www.douyin.com/video/123", "https://www.douyin.com/video/456"]
    )

    assert [item.status for item in results] == ["success", "success"]
    assert maximum_downloads == 2
    assert maximum_asr == 1
    assert retry_values == [1, 1]


def test_terminology_dictionary_requires_opt_in_and_is_archived(tmp_path):
    media = tmp_path / "sample.wav"
    media.write_bytes(b"fake fixture accepted by validator")
    paths = _paths(tmp_path)
    options = {
        "media_validator": _validator,
        "asr_factory": _asr_factory,
        "correction_rules": (
            CorrectionRule("approved", "\u4f60\u597d", "\u60a8\u597d"),
        ),
    }

    unchanged = TranscriptionPipeline(paths, **options).run_local(
        media, title="\u5173\u95ed"
    )
    corrected = TranscriptionPipeline(
        paths, corrections_enabled=True, force=True, **options
    ).run_local(media, title="\u5f00\u542f")

    unchanged_text = Path(unchanged.output_path or "").read_text(encoding="utf-8")
    corrected_text = Path(corrected.output_path or "").read_text(encoding="utf-8")
    assert "\u4f60\u597d\u3002" in unchanged_text
    assert "\u60a8\u597d\u3002" in corrected_text
    assert 'enabled\\\":false' in unchanged_text
    assert 'enabled\\\":true' in corrected_text
    assert '\\"occurrences\\":1' in corrected_text
    assert "\u4f60\u597d\u3002" not in corrected_text.split(
        "## \u53e3\u64ad\u9010\u5b57\u7a3f", 1
    )[-1]



def test_ten_item_batch_isolates_failures_reuses_cache_and_deduplicates(tmp_path):
    paths = _paths(tmp_path)

    def resolver(value: str) -> ResolvedInput:
        video_id = value.rsplit("/", 1)[-1]
        canonical = f"https://www.douyin.com/video/{video_id}"
        return ResolvedInput(canonical, canonical, video_id, "direct")

    def downloader(video_id: str, _candidates, cache_dir: Path, **_kwargs) -> MediaFile:
        if video_id in {"4", "5"}:
            raise DownloadError("NETWORK_FAILED", "simulated network failure")
        cache_dir.mkdir(parents=True, exist_ok=True)
        media = cache_dir / f"{video_id}-audio-{'a' * 16}.m4a"
        media.write_bytes(b"fake media")
        return MediaFile(media, "mp4", media.stat().st_size, 5.0)

    def make_pipeline() -> TranscriptionPipeline:
        return TranscriptionPipeline(
            paths,
            max_downloads=2,
            capture_factory=_Capture,
            downloader=downloader,
            media_validator=_validator,
            asr_factory=_asr_factory,
            url_resolver=resolver,
        )

    initial = make_pipeline().run_urls(
        [f"https://www.douyin.com/video/{video_id}" for video_id in ("1", "2", "3")]
    )
    previous_paths = {item.output_path for item in initial}
    inputs = ["1", "2", "3", "4", "5", "6", "7", "8", "4", "7"]

    results = make_pipeline().run_urls(
        [f"https://www.douyin.com/video/{video_id}" for video_id in inputs]
    )

    assert [item.status for item in results] == [
        "skipped", "skipped", "skipped", "failed", "failed",
        "success", "success", "success", "failed", "skipped",
    ]
    assert all(Path(path or "").is_file() for path in previous_paths)
    assert len(list(paths.output_dir.glob("*.md"))) == 6
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        completed_ids = ("1", "2", "3", "6", "7", "8")
        assert all(store.is_completed_valid(video_id) for video_id in completed_ids)
        assert store.get_task("4").error_code == "NETWORK_FAILED"
        assert store.get_task("5").error_code == "NETWORK_FAILED"


def test_timeline_terminology_expansion_uses_a_finite_character_budget(tmp_path):
    media = tmp_path / "sample.wav"
    media.write_bytes(b"fake fixture accepted by validator")
    pipeline = TranscriptionPipeline(
        _paths(tmp_path),
        media_validator=_validator,
        asr_factory=_asr_factory,
        correction_rules=(CorrectionRule("timestamp", "[00:00]", "T" * 100),),
        corrections_enabled=True,
        max_output_characters=10,
        max_output_segments=1,
    )

    result = pipeline.run_local(media, title="timeline budget")

    assert result.status == "failed"
    assert result.error_code == "TERMINOLOGY_OUTPUT_LIMIT"


def test_pipeline_shares_terminology_work_budget_between_body_and_timeline(
    monkeypatch, tmp_path
):
    media = tmp_path / "sample.wav"
    media.write_bytes(b"fake fixture accepted by validator")
    monkeypatch.setattr(
        pipeline_module,
        "CorrectionWorkBudget",
        lambda: CorrectionWorkBudget(max_steps=12),
    )
    pipeline = TranscriptionPipeline(
        _paths(tmp_path),
        media_validator=_validator,
        asr_factory=_asr_factory,
        correction_rules=(CorrectionRule("unmatched", "zz", "ZZ"),),
        corrections_enabled=True,
    )

    result = pipeline.run_local(media, title="shared work budget")

    assert result.status == "failed"
    assert result.error_code == "TERMINOLOGY_WORK_LIMIT"


def test_url_batch_accepts_50_and_rejects_over_limit_before_consuming_unbounded_input():
    normal_batch = [f"https://www.douyin.com/video/{index}" for index in range(50)]
    assert len(validate_url_batch(normal_batch)) == 50

    consumed = 0

    def values():
        nonlocal consumed
        while True:
            consumed += 1
            yield f"https://www.douyin.com/video/{consumed}"

    try:
        validate_url_batch(values())
    except ValueError as exc:
        assert "最多支持" in str(exc)
    else:
        raise AssertionError("unbounded URL input should be rejected")

    assert consumed == MAX_URL_BATCH_ITEMS + 1


def test_run_urls_rejects_oversized_batch_before_opening_task_store(tmp_path):
    paths = _paths(tmp_path)
    pipeline = TranscriptionPipeline(paths)
    urls = [f"https://www.douyin.com/video/{index}" for index in range(MAX_URL_BATCH_ITEMS + 1)]

    try:
        pipeline.run_urls(urls)
    except ValueError as exc:
        assert "最多支持" in str(exc)
    else:
        raise AssertionError("oversized run_urls batch should be rejected")

    assert not paths.data_dir.exists()


def test_url_batch_rejects_non_string_and_excessive_url_length():
    for values, expected in (([None], "字符串"), (["x" * 8193], "不得超过")):
        try:
            validate_url_batch(values)  # type: ignore[arg-type]
        except ValueError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError("invalid URL batch should be rejected")
