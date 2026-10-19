from __future__ import annotations

import _thread
import hashlib
import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import douyin_transcript.pipeline as pipeline_module
import pytest
from douyin_transcript.asr import TranscriptionResult, TranscriptSegment
from douyin_transcript.capture_client import CaptureClientError, CapturedMedia
from douyin_transcript.capture_ipc import CaptureVideoMetadata
from douyin_transcript.config import ConfigurationError, RuntimePaths
from douyin_transcript.corrections import CorrectionRule, CorrectionWorkBudget
from douyin_transcript.downloader import (
    MediaFile,
    MediaInvalidError,
)
from douyin_transcript.naming import candidate_output_paths
from douyin_transcript.output import json_summary, make_summary
from douyin_transcript.pipeline import (
    MAX_URL_BATCH_ITEMS,
    TranscriptionPipeline,
    validate_url_batch,
)
from douyin_transcript.tasks import TaskStore


def _paths(tmp_path: Path) -> RuntimePaths:
    return RuntimePaths(
        data_dir=tmp_path / "data",
        output_dir=tmp_path / "output",
        config_path=tmp_path / "data" / "config.toml",
    )


def test_pipeline_blocks_unsafe_implicit_output_directory(monkeypatch, tmp_path):
    paths = _paths(tmp_path)
    paths = RuntimePaths(
        data_dir=paths.data_dir,
        output_dir=paths.output_dir,
        config_path=paths.config_path,
        output_dir_is_default=True,
    )
    monkeypatch.setattr(
        pipeline_module,
        "output_directory_permission_status",
        lambda _path: {"status": "unsafe", "detail": "shared"},
    )

    with pytest.raises(ConfigurationError, match="默认输出目录权限不安全"):
        TranscriptionPipeline(paths)


def test_pipeline_keeps_explicit_shared_output_available(monkeypatch, tmp_path):
    monkeypatch.setattr(
        pipeline_module,
        "output_directory_permission_status",
        lambda _path: {"status": "unsafe", "detail": "shared"},
    )

    pipeline = TranscriptionPipeline(_paths(tmp_path))
    pipeline.close()


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


def test_media_invalid_error_has_media_specific_recovery_hint():
    error = MediaInvalidError("MEDIA_DECODE_FAILED", "媒体包含无法恢复的数据")

    code, message, hint = pipeline_module._error_details(error)

    assert code == "MEDIA_DECODE_FAILED"
    assert message == "媒体包含无法恢复的数据"
    assert hint == "确认媒体文件完整且包含可解码音轨。"


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

    first = TranscriptionPipeline(
        paths, media_validator=validator, asr_factory=asr_factory
    )
    second = TranscriptionPipeline(
        paths, media_validator=validator, asr_factory=asr_factory
    )
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(pipeline.run_local, media, retry_task_id=task.task_id)
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
        pytest.skip(
            f"filesystem does not permit symlink creation: {type(exc).__name__}"
        )

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


def test_local_force_retries_failed_task_with_current_processing_profile(tmp_path):
    media = tmp_path / "failed-before-model-ready.wav"
    media.write_bytes(b"fake fixture accepted by validator")
    paths = _paths(tmp_path)

    class FailingASR:
        def transcribe(self, _path, *, language):
            raise RuntimeError("model unavailable")

    failed = TranscriptionPipeline(
        paths,
        profile="fast",
        media_validator=_validator,
        asr_factory=lambda *_args, **_kwargs: FailingASR(),
    ).run_local(media)
    assert failed.status == "failed"

    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        task = store.list_tasks()[0]
        assert task.state == "failed"
        assert task.profile == "fast"

    retried = TranscriptionPipeline(
        paths,
        profile="balanced",
        language="auto",
        force=True,
        media_validator=_validator,
        asr_factory=_asr_factory,
    ).run_local(media)

    assert retried.status == "success"
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        task = store.list_tasks()[0]
        assert task.state == "completed"
        assert task.profile == "balanced"
        assert json.loads(task.processing_options_json or "{}")["language"] == "auto"


def _captured_media(
    paths: RuntimePaths,
    video_id: str,
    *,
    title: str | None = None,
    duration_seconds: float = 5.0,
    body: bytes | None = None,
) -> CapturedMedia:
    """Create a protocol-shaped service result inside the private media cache."""
    payload = body if body is not None else f"synthetic media for {video_id}".encode()
    digest = hashlib.sha256(payload).hexdigest()
    cache = paths.data_dir / "media-cache"
    cache.mkdir(parents=True, exist_ok=True)
    media = cache / f"{video_id}-{digest[:16]}.m4a"
    media.write_bytes(payload)
    return CapturedMedia(
        CaptureVideoMetadata(
            video_id,
            title or f"服务标题 {video_id}",
            "测试作者",
            None,
            duration_seconds,
        ),
        media,
        len(payload),
        digest,
        "audio/mp4",
        duration_seconds,
    )


class _CaptureServiceFake:
    """Complete-job fake: resolution and capture are owned by one client."""

    def __init__(
        self, paths: RuntimePaths, *, resolve_handler=None, capture_handler=None
    ) -> None:
        self.paths = paths
        self.resolve_handler = resolve_handler
        self.capture_handler = capture_handler
        self.resolve_calls: list[str] = []
        self.capture_calls: list[str] = []

    def resolve_source(self, original_url: str, **_kwargs) -> str:
        self.resolve_calls.append(original_url)
        if self.resolve_handler is not None:
            return self.resolve_handler(original_url)
        return original_url.rstrip("/").rsplit("/", 1)[-1].split("?", 1)[0]

    def capture(self, original_url: str, **kwargs) -> CapturedMedia:
        self.capture_calls.append(original_url)
        if self.capture_handler is not None:
            return self.capture_handler(original_url, **kwargs)
        video_id = original_url.rstrip("/").rsplit("/", 1)[-1].split("?", 1)[0]
        return _captured_media(self.paths, video_id)


def test_remote_pipeline_uses_complete_capture_service_and_persists_task(tmp_path):
    paths = _paths(tmp_path)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    forged_output = paths.output_dir / "untrusted-existing.md"
    forged_output.write_text(
        '---\nvideo_id: "123"\n---\n\n未验证的旧内容\n', encoding="utf-8"
    )
    service = _CaptureServiceFake(paths)

    pipeline = TranscriptionPipeline(
        paths,
        capture_service_client=service,
        media_validator=_validator,
        asr_factory=_asr_factory,
    )
    result = pipeline.run_urls(["https://www.douyin.com/video/123"])[0]

    assert result.status == "success"
    assert result.video_id == "123"
    assert Path(result.output_path or "") != forged_output
    assert "未验证的旧内容" in forged_output.read_text(encoding="utf-8")
    assert service.capture_calls == ["https://www.douyin.com/video/123"]
    assert "你好。" not in str(result.to_dict())
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        task = store.get_task("123")
        assert task is not None and task.state == "completed"
        assert task.title == "服务标题 123"
        assert task.output_sha256 is not None
        assert task.source_duration_seconds == 5.0
        assert store.is_completed_valid("123")

    skipped = pipeline.run_urls(["https://www.douyin.com/video/123"])[0]
    assert skipped.status == "skipped"
    assert skipped.title == "服务标题 123"
    assert service.capture_calls == ["https://www.douyin.com/video/123"]


@pytest.mark.parametrize(
    ("crash_at", "expected_asr_calls"),
    [("downloaded", 1), ("transcribing", 1), ("writing", 2)],
)
def test_pipeline_recovers_after_real_subprocess_crash(
    tmp_path, crash_at: str, expected_asr_calls: int
):
    fixture = Path(__file__).parents[1] / "fixtures" / "pipeline_crash_worker.py"
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "output"
    events_path = tmp_path / "events.json"
    arguments = [
        sys.executable,
        str(fixture),
        str(data_dir),
        str(output_dir),
        str(events_path),
    ]

    crashed = subprocess.run(
        [*arguments, "crash", crash_at],
        cwd=Path(__file__).parents[2],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert crashed.returncode == 86, crashed.stderr

    resumed = subprocess.run(
        [*arguments, "resume"],
        cwd=Path(__file__).parents[2],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert resumed.returncode == 0, resumed.stderr

    payload = json.loads((data_dir / "resume-result.json").read_text(encoding="utf-8"))
    assert payload["status"] == "success"
    assert payload["error_code"] is None
    assert payload["events"] == {
        "asr_calls": expected_asr_calls,
        "capture_calls": 1,
        "download_calls": 1,
    }
    output_path = Path(payload["output_path"])
    assert output_path.is_file()
    assert "测试恢复。" in output_path.read_text(encoding="utf-8")
    with TaskStore(data_dir / "tasks.sqlite3") as store:
        recovered = store.get_task("123")
        assert recovered is not None and recovered.state == "completed"
        assert recovered.title == "Crash recovery fixture"
        assert store.is_completed_valid("123")


def test_old_capture_factory_is_rejected_and_url_pipeline_fails_closed_before_side_effects(
    monkeypatch,
    tmp_path,
):
    paths = _paths(tmp_path)
    factory_calls = []
    resolver_calls = []
    store_factory_calls = []

    def old_capture_factory(*_args, **_kwargs):
        factory_calls.append(True)
        raise AssertionError("legacy caller-side capture must never start")

    original_resolver = pipeline_module.resolve_direct_input

    def resolver(value):
        resolver_calls.append(value)
        return original_resolver(value)

    monkeypatch.setattr(pipeline_module, "resolve_direct_input", resolver)

    def store_factory(path):
        store_factory_calls.append(Path(path))
        return TaskStore(path)

    with pytest.raises(TypeError, match="capture_factory"):
        TranscriptionPipeline(
            paths,
            capture_factory=old_capture_factory,
            task_store_factory=store_factory,
        )

    pipeline = TranscriptionPipeline(
        paths,
        task_store_factory=store_factory,
    )
    result = pipeline.run_urls(["https://www.douyin.com/video/123"])[0]

    assert result.status == "failed"
    assert result.error_code == "BROWSER_ISOLATION_UNAVAILABLE"
    assert factory_calls == []
    assert resolver_calls == []
    assert store_factory_calls == []
    assert not paths.data_dir.exists()


def test_default_pipeline_short_link_fails_closed_without_service(tmp_path):
    pipeline = TranscriptionPipeline(_paths(tmp_path))

    result = pipeline.run_urls(["https://v.douyin.com/example/"])[0]

    assert result.status == "failed"
    assert result.error_code == "BROWSER_ISOLATION_UNAVAILABLE"
    assert "隔离服务" in (result.hint or "")


def test_pipeline_uses_service_resolution_and_capture_while_deduplicating_ids(tmp_path):
    paths = _paths(tmp_path)
    paths.output_dir.mkdir(parents=True, exist_ok=True)

    service = _CaptureServiceFake(
        paths,
        resolve_handler=lambda _url: "123",
        capture_handler=lambda _url, **_kwargs: _captured_media(
            paths, "123", title="服务标题"
        ),
    )
    pipeline = TranscriptionPipeline(
        paths,
        capture_service_client=service,
        media_validator=_validator,
        asr_factory=_asr_factory,
    )

    results = pipeline.run_urls(
        [
            "https://v.douyin.com/example/?share_token=private",
            "https://www.douyin.com/video/123",
        ]
    )

    assert [item.status for item in results] == ["success", "skipped"]
    assert service.resolve_calls == [
        "https://v.douyin.com/example/?share_token=private"
    ]
    assert service.capture_calls == [
        "https://v.douyin.com/example/?share_token=private"
    ]
    assert results[0].title == "服务标题"
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        task = store.get_task("123")
        assert task is not None and task.state == "completed"
        assert task.source_url == "https://www.douyin.com/video/123"
        assert "share_token" not in task.source_url


def test_pipeline_rejects_service_video_id_mismatch_before_asr(tmp_path):
    paths = _paths(tmp_path)
    paths.output_dir.mkdir(parents=True, exist_ok=True)

    service = _CaptureServiceFake(
        paths,
        capture_handler=lambda _url, **_kwargs: _captured_media(
            paths, "999", title="错配标题"
        ),
    )

    pipeline = TranscriptionPipeline(
        paths,
        capture_service_client=service,
        media_validator=lambda _path: pytest.fail(
            "mismatched ID must fail before decoding"
        ),
        asr_factory=lambda *_args, **_kwargs: pytest.fail(
            "mismatched ID must fail before ASR"
        ),
    )

    result = pipeline.run_urls(["https://www.douyin.com/video/123"])[0]

    assert result.status == "failed"
    assert result.error_code == "INVALID_RESULT"
    assert not list((paths.data_dir / "media-cache").glob("*.m4a"))
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        task = store.get_task("123")
        assert task is not None and task.state == "failed"
        assert task.media_path is None


def test_service_resolution_retries_only_retryable_failures(tmp_path):
    class RetryableService:
        def __init__(self):
            self.calls = 0

        def resolve_source(self, _url: str, **_kwargs) -> str:
            self.calls += 1
            if self.calls == 1:
                raise CaptureClientError("NETWORK_ERROR", "network", retryable=True)
            return "123"

    service = RetryableService()
    pipeline = TranscriptionPipeline(_paths(tmp_path), retries=1)

    assert (
        pipeline._resolve_service_source_with_retries(
            service,
            "https://v.douyin.com/example/",
            deadline_monotonic=time.monotonic() + 10,
        )
        == "123"
    )
    assert service.calls == 2


def test_service_resolution_does_not_retry_nonretryable_failures(tmp_path):
    class NonRetryableService:
        calls = 0

        def resolve_source(self, _url: str, **_kwargs) -> str:
            self.calls += 1
            raise CaptureClientError("UNSUPPORTED_URL", "unsupported", retryable=False)

    service = NonRetryableService()
    pipeline = TranscriptionPipeline(_paths(tmp_path), retries=2)

    with pytest.raises(CaptureClientError) as error:
        pipeline._resolve_service_source_with_retries(
            service,
            "https://v.douyin.com/example/",
            deadline_monotonic=time.monotonic() + 10,
        )

    assert error.value.code == "UNSUPPORTED_URL"
    assert service.calls == 1


def test_capture_service_media_is_validated_before_it_reaches_asr(tmp_path):
    paths = _paths(tmp_path)
    service = _CaptureServiceFake(paths)

    class ValidationAwareASR:
        def __init__(self):
            self.received_path = None

        def transcribe(self, path, *, language):
            self.received_path = Path(path)
            return TranscriptionResult(
                (TranscriptSegment(0.0, 2.0, "远端已通过验证。"),),
                5.0,
                language,
                "test-model",
                "balanced",
            )

    asr = ValidationAwareASR()
    validated_paths = []

    def validated_media(path):
        path = Path(path)
        validated_paths.append(path)
        return MediaFile(path, "mp4", path.stat().st_size, 5.0)

    pipeline = TranscriptionPipeline(
        paths,
        capture_service_client=service,
        media_validator=validated_media,
        asr_factory=lambda *_args, **_kwargs: asr,
    )

    result = pipeline.run_urls(["https://www.douyin.com/video/123"])[0]

    assert result.status == "success"
    assert service.capture_calls == ["https://www.douyin.com/video/123"]
    assert len(validated_paths) == 1
    assert asr.received_path == validated_paths[0]
    assert asr.received_path.is_file()


def test_remote_processing_deadline_reports_processing_timeout(tmp_path):
    paths = _paths(tmp_path)

    def capture_after_deadline(_url, **_kwargs):
        time.sleep(1.05)
        raise CaptureClientError("CAPTURE_TIMEOUT", "service timed out", retryable=True)

    service = _CaptureServiceFake(paths, capture_handler=capture_after_deadline)
    pipeline = TranscriptionPipeline(
        paths,
        capture_service_client=service,
        retries=0,
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


def test_keyboard_interrupt_cancels_slow_service_capture_and_releases_claim(tmp_path):
    capture_started = threading.Event()
    cancellation_seen = threading.Event()
    interrupt_sent: list[bool] = []
    paths = _paths(tmp_path)

    def slow_service_capture(_url, *, is_cancelled, **_kwargs):
        capture_started.set()
        while not is_cancelled():
            time.sleep(0.01)
        cancellation_seen.set()
        raise CaptureClientError("CANCELLED", "service request cancelled")

    service = _CaptureServiceFake(paths, capture_handler=slow_service_capture)
    pipeline = TranscriptionPipeline(
        paths,
        capture_service_client=service,
    )

    def interrupt_during_capture():
        interrupt_sent.append(capture_started.wait(timeout=3))
        _thread.interrupt_main()

    interrupter = threading.Thread(target=interrupt_during_capture, daemon=True)
    interrupter.start()
    started = time.monotonic()
    with pytest.raises(KeyboardInterrupt):
        pipeline.run_urls(["https://www.douyin.com/video/123"])
    elapsed = time.monotonic() - started
    interrupter.join(timeout=1)

    assert interrupt_sent == [True]
    assert elapsed < 1.5
    assert cancellation_seen.wait(timeout=1)
    assert not interrupter.is_alive()
    assert not list((paths.data_dir / "media-cache").glob("*.m4a"))
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        task = store.get_task("123")
        assert task is not None
        assert task.state == "failed"
        assert task.claimed_by is None
        assert task.error_code == "CANCELLED"


def test_pipeline_cancels_processing_when_task_claim_is_recovered(
    tmp_path, monkeypatch
):
    paths = _paths(tmp_path)
    database = paths.data_dir / "tasks.sqlite3"
    pipeline = TranscriptionPipeline(paths, heartbeat_interval_seconds=0.01)
    heartbeat_started = threading.Event()
    allow_heartbeat = threading.Event()
    original_heartbeat = TaskStore.heartbeat_claim

    def delayed_heartbeat(store, task_id, worker_id, *, claim_generation):
        heartbeat_started.set()
        allow_heartbeat.wait(timeout=2)
        return original_heartbeat(
            store,
            task_id,
            worker_id,
            claim_generation=claim_generation,
        )

    monkeypatch.setattr(TaskStore, "heartbeat_claim", delayed_heartbeat)

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
            try:
                assert heartbeat_started.wait(timeout=1)
                with TaskStore(database) as recovery_store:
                    with recovery_store._transaction():
                        recovery_store._connection.execute(
                            "UPDATE tasks SET claimed_at = ? WHERE task_id = ?",
                            ("2000-01-01T00:00:00.000+00:00", claimed.task_id),
                        )
                    recovered = recovery_store.recover_interrupted(
                        stale_after_seconds=0
                    )
            finally:
                allow_heartbeat.set()
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


def test_keyboard_interrupt_cancels_supervised_capture_media_validation(
    monkeypatch, tmp_path
):
    validation_started = threading.Event()
    validation_cancelled = threading.Event()
    worker_closed = threading.Event()
    interrupt_sent: list[bool] = []

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
            raise CaptureClientError("CANCELLED", "decoder request cancelled")

        def close(self):
            worker_closed.set()

    workers: list[BlockingProcessingWorker] = []

    def worker_factory():
        worker = BlockingProcessingWorker()
        workers.append(worker)
        return worker

    monkeypatch.setattr(pipeline_module, "SupervisedProcessingWorker", worker_factory)
    paths = _paths(tmp_path)
    service = _CaptureServiceFake(paths)
    pipeline = TranscriptionPipeline(
        paths,
        capture_service_client=service,
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
    assert not list((paths.data_dir / "media-cache").glob("*.m4a"))
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        task = store.get_task("123")
        assert task is not None
        assert task.state == "failed"
        assert task.claimed_by is None
        assert task.error_code == "CANCELLED"


def test_remote_pipeline_rejects_media_shorter_than_service_metadata(tmp_path):
    paths = _paths(tmp_path)

    service = _CaptureServiceFake(
        paths,
        capture_handler=lambda _url, **_kwargs: _captured_media(
            paths, "123", duration_seconds=5.0
        ),
    )

    def short_validator(path: Path) -> MediaFile:
        return MediaFile(Path(path), "mp4", Path(path).stat().st_size, 1.0)

    pipeline = TranscriptionPipeline(
        paths,
        capture_service_client=service,
        media_validator=short_validator,
        asr_factory=_asr_factory,
    )

    result = pipeline.run_urls(["https://www.douyin.com/video/123"])[0]

    assert result.status == "failed"
    assert result.error_code == "MEDIA_INCOMPLETE"
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        task = store.get_task("123")
        assert task is not None and task.state == "failed"
        assert task.source_duration_seconds is None


@pytest.mark.parametrize("force", [False, True])
def test_remote_force_retries_only_the_requested_login_failure(tmp_path, force):
    paths = _paths(tmp_path)
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        for video_id in ("123", "456"):
            task = store.create_remote_task(
                f"https://www.douyin.com/video/{video_id}", video_id
            )
            claimed = store.claim_task(task.task_id, "prior")
            assert claimed is not None
            store.fail_task(
                task.task_id,
                "LOGIN_REQUIRED",
                worker_id="prior",
                claim_generation=claimed.claim_generation,
            )
    service = _CaptureServiceFake(paths)
    pipeline = TranscriptionPipeline(
        paths,
        capture_service_client=service,
        force=force,
        media_validator=_validator,
        asr_factory=_asr_factory,
    )
    try:
        result = pipeline.run_urls(["https://www.douyin.com/video/123"])[0]
    finally:
        pipeline.close()
    assert result.status == ("success" if force else "failed")
    assert service.capture_calls == (
        ["https://www.douyin.com/video/123"] if force else []
    )
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        assert store.get_task("456").state == "failed"


def test_remote_capture_failure_is_durable_and_retryable(tmp_path):
    paths = _paths(tmp_path)

    def failed_capture(_url, **_kwargs):
        raise CaptureClientError("CAPTURE_TRANSPORT_FAILED", "service unavailable")

    service = _CaptureServiceFake(paths, capture_handler=failed_capture)

    pipeline = TranscriptionPipeline(
        paths,
        capture_service_client=service,
        retries=0,
        media_validator=_validator,
        asr_factory=_asr_factory,
    )
    result = pipeline.run_urls(["https://www.douyin.com/video/123"])[0]

    assert result.status == "failed"
    assert result.error_code == "CAPTURE_TRANSPORT_FAILED"
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        failed = store.get_task("123")
        assert failed is not None and failed.state == "failed"
        queued = store.retry_failed()
        assert [task.task_id for task in queued] == ["123"]
        assert queued[0].state == "pending"


def test_remote_retry_reuses_valid_cached_media_without_service_capture(tmp_path):
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

    service = _CaptureServiceFake(
        paths,
        capture_handler=lambda *_args, **_kwargs: pytest.fail(
            "cached retry must not request new captured media"
        ),
    )
    pipeline = TranscriptionPipeline(
        paths,
        capture_service_client=service,
        media_validator=_validator,
        asr_factory=_asr_factory,
    )
    result = pipeline.run_urls(["https://www.douyin.com/video/123"])[0]
    pipeline.close()

    assert result.status == "success"
    assert result.output_path is not None
    assert service.capture_calls == []
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        completed = store.get_task(created.task_id)
        assert completed is not None
        assert completed.state == "completed"
        assert completed.media_path == str(cached_media.resolve())


def test_remote_pipeline_recovers_a_stale_interrupted_capture(tmp_path):
    paths = _paths(tmp_path)
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        store.create_remote_task("https://www.douyin.com/video/123", "123")
        claimed = store.claim_task("123", "crashed-worker")
        assert claimed is not None
        store.transition(
            "123",
            "downloading",
            worker_id="crashed-worker",
            claim_generation=claimed.claim_generation,
        )

    service = _CaptureServiceFake(paths)
    pipeline = TranscriptionPipeline(
        paths,
        capture_service_client=service,
        media_validator=_validator,
        asr_factory=_asr_factory,
        stale_after_seconds=0,
    )

    result = pipeline.run_urls(["https://www.douyin.com/video/123"])[0]

    assert result.status == "success"
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        recovered = store.get_task("123")
        assert recovered is not None and recovered.state == "completed"


def test_remote_recovery_defers_media_decode_until_task_processing(tmp_path):
    paths = _paths(tmp_path)
    media = paths.data_dir / "media" / "cached.wav"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"fake media accepted by the test validator")
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        task = store.create_remote_task("https://www.douyin.com/video/123", "123")
        claimed = store.claim_task(task.task_id, "crashed-worker")
        assert claimed is not None
        store.transition(
            task.task_id,
            "downloading",
            worker_id="crashed-worker",
            claim_generation=claimed.claim_generation,
        )
        store.transition(
            task.task_id,
            "downloaded",
            worker_id="crashed-worker",
            claim_generation=claimed.claim_generation,
            media_path=media,
        )
        store.transition(
            task.task_id,
            "transcribing",
            worker_id="crashed-worker",
            claim_generation=claimed.claim_generation,
        )

    validation_calls = []

    def validator(path: Path) -> MediaFile:
        validation_calls.append(Path(path))
        return _validator(Path(path))

    service = _CaptureServiceFake(
        paths,
        capture_handler=lambda *_args, **_kwargs: pytest.fail(
            "recovered cached media should not request a service capture"
        ),
    )
    pipeline = TranscriptionPipeline(
        paths,
        capture_service_client=service,
        media_validator=validator,
        asr_factory=_asr_factory,
        stale_after_seconds=0,
    )

    result = pipeline.run_urls(["https://www.douyin.com/video/123"])[0]

    assert result.status == "success"
    assert validation_calls == [media]
    assert service.capture_calls == []
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        recovered = store.get_task("123")
        assert recovered is not None and recovered.state == "completed"


def test_remote_recovery_recaptures_when_deferred_cache_validation_fails(tmp_path):
    paths = _paths(tmp_path)
    cached_media = paths.data_dir / "media" / "cached.wav"
    cached_media.parent.mkdir(parents=True)
    cached_media.write_bytes(b"corrupt cached media")
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        task = store.create_remote_task("https://www.douyin.com/video/123", "123")
        claimed = store.claim_task(task.task_id, "crashed-worker")
        assert claimed is not None
        store.transition(
            task.task_id,
            "downloading",
            worker_id="crashed-worker",
            claim_generation=claimed.claim_generation,
        )
        store.transition(
            task.task_id,
            "downloaded",
            worker_id="crashed-worker",
            claim_generation=claimed.claim_generation,
            media_path=cached_media,
        )
        store.transition(
            task.task_id,
            "transcribing",
            worker_id="crashed-worker",
            claim_generation=claimed.claim_generation,
        )

    validation_calls = []
    captured_media = []

    def validator(path: Path) -> MediaFile:
        path = Path(path)
        validation_calls.append(path)
        if path == cached_media:
            raise MediaInvalidError("MEDIA_INVALID", "cached file is corrupt")
        return _validator(path)

    def capture(_url: str, **_kwargs) -> CapturedMedia:
        result = _captured_media(paths, "123", body=b"fresh media")
        captured_media.append(result.path)
        return result

    service = _CaptureServiceFake(paths, capture_handler=capture)
    pipeline = TranscriptionPipeline(
        paths,
        capture_service_client=service,
        media_validator=validator,
        asr_factory=_asr_factory,
        stale_after_seconds=0,
    )

    result = pipeline.run_urls(["https://www.douyin.com/video/123"])[0]

    assert result.status == "success", result
    assert validation_calls == [cached_media, captured_media[0]]
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        recovered = store.get_task("123")
        assert recovered is not None and recovered.state == "completed"
        assert recovered.media_path == str(captured_media[0].resolve())


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


def test_remote_pipeline_bounds_service_captures_and_keeps_asr_serial(tmp_path):
    paths = _paths(tmp_path)
    capture_barrier = threading.Barrier(2)
    state_lock = threading.Lock()
    active_captures = 0
    maximum_captures = 0
    active_asr = 0
    maximum_asr = 0

    def capture(url: str, **_kwargs) -> CapturedMedia:
        nonlocal active_captures, maximum_captures
        video_id = url.rstrip("/").rsplit("/", 1)[-1]
        with state_lock:
            active_captures += 1
            maximum_captures = max(maximum_captures, active_captures)
        try:
            capture_barrier.wait(timeout=3)
            time.sleep(0.02)
            return _captured_media(paths, video_id)
        finally:
            with state_lock:
                active_captures -= 1

    class SerialASR:
        def transcribe(self, _path: Path, *, language: str) -> TranscriptionResult:
            nonlocal active_asr, maximum_asr
            with state_lock:
                active_asr += 1
                maximum_asr = max(maximum_asr, active_asr)
            try:
                time.sleep(0.02)
                return TranscriptionResult(
                    (TranscriptSegment(0, 1, "你好。"),),
                    5.0,
                    language,
                    "test",
                    "balanced",
                )
            finally:
                with state_lock:
                    active_asr -= 1

    pipeline = TranscriptionPipeline(
        paths,
        max_downloads=2,
        retries=1,
        capture_service_client=_CaptureServiceFake(paths, capture_handler=capture),
        media_validator=_validator,
        asr_factory=lambda *_args, **_kwargs: SerialASR(),
    )

    results = pipeline.run_urls(
        ["https://www.douyin.com/video/123", "https://www.douyin.com/video/456"]
    )

    assert [item.status for item in results] == ["success", "success"]
    assert maximum_captures == 2
    assert maximum_asr == 1


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
    unchanged_metadata = unchanged_text.split("## \u53e3\u64ad\u9010\u5b57\u7a3f", 1)[0]
    corrected_metadata = corrected_text.split("## \u53e3\u64ad\u9010\u5b57\u7a3f", 1)[0]
    for expected in (
        '\\"schema_version\\":2',
        '\\"applied_rule_count\\":1',
        '\\"replacement_count\\":1',
    ):
        assert expected in corrected_metadata
    for private_value in ("approved", "\u4f60\u597d", "\u60a8\u597d"):
        assert private_value not in corrected_metadata
    assert '\\"applied_rule_count\\":0' in unchanged_metadata
    assert '\\"replacement_count\\":0' in unchanged_metadata
    for private_value in ("approved", "\u4f60\u597d", "\u60a8\u597d"):
        assert private_value not in unchanged_metadata
    assert (
        "\u4f60\u597d\u3002"
        not in corrected_text.split("## \u53e3\u64ad\u9010\u5b57\u7a3f", 1)[-1]
    )


def test_ten_item_batch_isolates_failures_reuses_cache_and_deduplicates(tmp_path):
    paths = _paths(tmp_path)

    def capture(url: str, **_kwargs) -> CapturedMedia:
        video_id = url.rstrip("/").rsplit("/", 1)[-1]
        if video_id in {"4", "5"}:
            raise CaptureClientError(
                "CAPTURE_TRANSPORT_FAILED", "simulated service failure"
            )
        return _captured_media(paths, video_id)

    def make_pipeline() -> TranscriptionPipeline:
        return TranscriptionPipeline(
            paths,
            max_downloads=2,
            capture_service_client=_CaptureServiceFake(paths, capture_handler=capture),
            media_validator=_validator,
            asr_factory=_asr_factory,
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
        "skipped",
        "skipped",
        "skipped",
        "failed",
        "failed",
        "success",
        "success",
        "success",
        "failed",
        "skipped",
    ]
    assert all(Path(path or "").is_file() for path in previous_paths)
    assert len(list(paths.output_dir.glob("*.md"))) == 6
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        completed_ids = ("1", "2", "3", "6", "7", "8")
        assert all(store.is_completed_valid(video_id) for video_id in completed_ids)
        assert store.get_task("4").error_code == "CAPTURE_TRANSPORT_FAILED"
        assert store.get_task("5").error_code == "CAPTURE_TRANSPORT_FAILED"


def test_fifty_item_mixed_batch_bounds_service_captures_and_keeps_asr_serial(tmp_path):
    paths = _paths(tmp_path)
    state_lock = threading.Lock()
    capture_barrier = threading.Barrier(2)
    state = {
        "capture_calls": 0,
        "active_captures": 0,
        "max_captures": 0,
        "active_asr": 0,
        "max_asr": 0,
    }

    def capture(url: str, **_kwargs) -> CapturedMedia:
        video_id = url.rstrip("/").rsplit("/", 1)[-1]
        with state_lock:
            state["capture_calls"] += 1
            call_number = state["capture_calls"]
            state["active_captures"] += 1
            state["max_captures"] = max(state["max_captures"], state["active_captures"])
        try:
            if call_number <= 2:
                capture_barrier.wait(timeout=3)
            else:
                time.sleep(0.001)
            if video_id in {"9", "10", "11"}:
                raise CaptureClientError(
                    "CAPTURE_TRANSPORT_FAILED", "simulated service failure"
                )
            return _captured_media(paths, video_id)
        finally:
            with state_lock:
                state["active_captures"] -= 1

    class SerialASR:
        def transcribe(self, _path: Path, *, language: str) -> TranscriptionResult:
            with state_lock:
                state["active_asr"] += 1
                state["max_asr"] = max(state["max_asr"], state["active_asr"])
            try:
                time.sleep(0.001)
                return TranscriptionResult(
                    (TranscriptSegment(0.0, 1.0, "\u4f60\u597d\u3002"),),
                    5.0,
                    language,
                    "test-model",
                    "balanced",
                )
            finally:
                with state_lock:
                    state["active_asr"] -= 1

    def make_pipeline() -> TranscriptionPipeline:
        return TranscriptionPipeline(
            paths,
            max_downloads=2,
            retries=0,
            capture_service_client=_CaptureServiceFake(paths, capture_handler=capture),
            media_validator=_validator,
            asr_factory=lambda *_args, **_kwargs: SerialASR(),
        )

    cached = make_pipeline().run_urls(
        [f"https://www.douyin.com/video/{video_id}" for video_id in range(1, 9)]
    )
    assert all(item.status == "success" for item in cached)
    for key in state:
        state[key] = 0

    video_ids = [*range(1, 12), *range(12, 49), 9, 12]
    assert len(video_ids) == 50
    results = make_pipeline().run_urls(
        [f"https://www.douyin.com/video/{video_id}" for video_id in video_ids]
    )

    assert len(results) == 50
    assert sum(item.status == "skipped" for item in results) == 9
    assert sum(item.status == "failed" for item in results) == 4
    assert sum(item.status == "success" for item in results) == 37
    assert state["capture_calls"] == 40
    assert state["max_captures"] == 2
    assert state["max_asr"] == 1
    assert len(list(paths.output_dir.glob("*.md"))) == 45
    assert len(list((paths.data_dir / "media-cache").glob("*.m4a"))) == 45

    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        assert len(store.list_tasks()) == 48
        completed_ids = (*range(1, 9), *range(12, 49))
        assert all(
            store.is_completed_valid(str(video_id)) for video_id in completed_ids
        )
        assert store.get_task("9").attempt_count == 1
        assert store.get_task("10").error_code == "CAPTURE_TRANSPORT_FAILED"
        assert store.get_task("11").error_code == "CAPTURE_TRANSPORT_FAILED"


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
    urls = [
        f"https://www.douyin.com/video/{index}"
        for index in range(MAX_URL_BATCH_ITEMS + 1)
    ]

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
