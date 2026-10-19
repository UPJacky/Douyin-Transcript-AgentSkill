"""Local-first task orchestration for URLs and local media files."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .asr import ASRUnavailableError, LocalASR
from .capture_client import CaptureClientError
from .capture_ipc import CaptureVideoMetadata
from .config import ConfigurationError, RuntimePaths
from .corrections import (
    CorrectionRule,
    CorrectionWorkBudget,
    apply_terminology_dictionary,
)
from .doctor import output_directory_permission_status
from .downloader import (
    DecoderUnavailableError,
    DownloadCancellation,
    DownloadError,
    MediaFile,
    MediaInvalidError,
    require_expected_media_duration,
    validate_media_file,
)
from .limits import (
    DEFAULT_MAX_MEDIA_DURATION_SECONDS,
    DEFAULT_MAX_OUTPUT_CHARACTERS,
    DEFAULT_MAX_OUTPUT_SEGMENTS,
    HARD_MAX_OUTPUT_CHARACTERS,
    ResourceLimitError,
    require_media_duration,
    validate_resource_limits,
)
from .markdown import (
    _atomic_publish,
    escape_markdown_text,
    render_transcript_markdown,
    write_transcript_markdown,
)
from .models import model_spec
from .naming import candidate_output_paths
from .normalize import normalize_segments
from .output import ItemResult
from .processing import (
    DEFAULT_MAX_PROCESSING_SECONDS,
    HARD_MAX_PROCESSING_SECONDS,
    ProcessingTimeoutError,
    SupervisedProcessingWorker,
)
from .tasks import DEFAULT_STALE_AFTER_SECONDS, Task, TaskStore
from .urls import (
    ResolvedInput,
    UnsupportedUrlError,
    extract_url,
    resolve_direct_input,
    resolved_short_link,
)

MAX_URL_BATCH_ITEMS = 100
MAX_URL_LENGTH = 8192


def validate_url_batch(values: Iterable[str]) -> list[str]:
    """Consume a bounded URL iterable and reject oversized batches clearly."""
    bounded: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError("URL 批次中的每一项都必须是字符串")
        if len(bounded) >= MAX_URL_BATCH_ITEMS:
            raise ValueError(f"URL 批次最多支持 {MAX_URL_BATCH_ITEMS} 条（包含重复链接）")
        if len(value) > MAX_URL_LENGTH:
            raise ValueError(f"单条 URL 不得超过 {MAX_URL_LENGTH} 个字符")
        bounded.append(value)
    return bounded


@dataclass(frozen=True, slots=True)
class _CaptureJob:
    index: int
    task: Task
    resolved: ResolvedInput
    title: str
    future: Future[Any]
    processing_deadline: float


class TranscriptionPipeline:
    """Run durable local/remote jobs while keeping transcript text on disk."""

    def __init__(
        self,
        paths: RuntimePaths,
        *,
        profile: str = "balanced",
        language: str = "zh",
        timestamps: bool = False,
        force: bool = False,
        task_store_factory: Callable[[Path], TaskStore] = TaskStore,
        capture_service_client: Any | None = None,
        asr_factory: Callable[..., Any] = LocalASR,
        media_validator: Callable[[Path], Any] = validate_media_file,
        markdown_writer: Callable[..., Path] = write_transcript_markdown,
        stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
        heartbeat_interval_seconds: float = 30,
        max_media_duration_seconds: float | None = None,
        max_output_segments: int | None = None,
        max_output_characters: int | None = None,
        max_downloads: int = 2,
        retries: int = 2,
        correction_rules: Iterable[CorrectionRule] = (),
        corrections_enabled: bool = False,
        max_processing_seconds: int = DEFAULT_MAX_PROCESSING_SECONDS,
    ) -> None:
        if getattr(paths, "output_dir_is_default", False):
            output_permissions = output_directory_permission_status(paths.output_dir)
            if output_permissions["status"] != "ok":
                raise ConfigurationError(
                    "默认输出目录权限不安全或无法确认；请指定 --output-dir 或修复应用数据目录权限"
                )
        self.paths = paths
        self.profile = model_spec(profile).profile
        if language not in {"zh", "auto"}:
            raise ValueError("language must be 'zh' or 'auto'")
        self.language = language
        self.timestamps = timestamps
        self.force = force
        (
            self.max_media_duration_seconds,
            self.max_output_segments,
            self.max_output_characters,
        ) = validate_resource_limits(
            max_media_duration_seconds
            if max_media_duration_seconds is not None
            else getattr(paths, "max_media_duration_seconds", DEFAULT_MAX_MEDIA_DURATION_SECONDS),
            max_output_segments
            if max_output_segments is not None
            else getattr(paths, "max_output_segments", DEFAULT_MAX_OUTPUT_SEGMENTS),
            max_output_characters
            if max_output_characters is not None
            else getattr(paths, "max_output_characters", DEFAULT_MAX_OUTPUT_CHARACTERS),
        )
        self._store_factory = task_store_factory
        self._capture_service_client = capture_service_client
        self._asr_factory = asr_factory
        self._use_supervised_processing = (
            asr_factory is LocalASR and media_validator is validate_media_file
        )
        self._media_validator = (
            (
                lambda path: validate_media_file(
                    path, max_duration_seconds=self.max_media_duration_seconds
                )
            )
            if media_validator is validate_media_file
            else media_validator
        )
        self._markdown_writer = markdown_writer
        self._stale_after_seconds = stale_after_seconds
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        if max_downloads not in {1, 2}:
            raise ValueError("max_downloads must be 1 or 2")
        if isinstance(retries, bool) or not isinstance(retries, int) or not 0 <= retries <= 2:
            raise ValueError("retries must be between 0 and 2")
        self.max_downloads = max_downloads
        self.retries = retries
        self.correction_rules = tuple(correction_rules)
        self.corrections_enabled = corrections_enabled
        if not isinstance(corrections_enabled, bool):
            raise ValueError("corrections_enabled must be a boolean")
        if stale_after_seconds < 0 or heartbeat_interval_seconds <= 0:
            raise ValueError("task lease timeouts must be positive")
        self._asr: Any | None = None
        self._processing_worker: SupervisedProcessingWorker | None = None
        if (
            isinstance(max_processing_seconds, bool)
            or not isinstance(max_processing_seconds, int)
            or not 1 <= max_processing_seconds <= HARD_MAX_PROCESSING_SECONDS
        ):
            raise ValueError(
                f"max_processing_seconds must be between 1 and {HARD_MAX_PROCESSING_SECONDS}"
            )
        self.max_processing_seconds = max_processing_seconds
        self._worker_id = f"pid-{os.getpid()}-{uuid.uuid4().hex[:8]}"

    def run_local(
        self,
        media_path: str | Path,
        *,
        title: str | None = None,
        retry_task_id: str | None = None,
    ) -> ItemResult:
        """Validate and transcribe one local audio/video file."""
        source = Path(media_path).expanduser()
        processing_deadline = time.monotonic() + self.max_processing_seconds
        try:
            validated = self._validate_media(source, deadline=processing_deadline)
            require_media_duration(validated.duration_seconds, self.max_media_duration_seconds)
            self._recover_stale_tasks()
            with self._store_factory(self.paths.data_dir / "tasks.sqlite3") as store:
                if retry_task_id is None:
                    task = store.create_local_task(
                        source,
                        profile=self.profile,
                        title=title,
                        processing_options=self._processing_options_snapshot(),
                    )
                    if task.state == "failed" and self.force:
                        task = store.prepare_local_retry(
                            task.task_id,
                            source,
                            worker_id=self._worker_id,
                            profile=self.profile,
                            processing_options=self._processing_options_snapshot(),
                        )
                        outcome = None
                    else:
                        task, outcome = self._prepare_task(
                            store,
                            task,
                            initial_state="downloaded",
                            title=title or source.stem,
                        )
                else:
                    task = store.prepare_local_retry(
                        retry_task_id, source, worker_id=self._worker_id
                    )
                    outcome = None
                if outcome is not None:
                    return outcome
                assert task.claimed_by == self._worker_id
                with self._keep_claim_alive(
                    store,
                    task.task_id,
                    claim_generation=task.claim_generation,
                ) as cancellation:
                    return self._transcribe_claimed(
                        store,
                        task,
                        media_path=Path(task.local_path or source),
                        title=title or source.stem,
                        source_url=task.source_url,
                        video_id=None,
                        duration_hint=None,
                        validated_media=validated,
                        processing_deadline=processing_deadline,
                        cancellation=cancellation,
                    )
        except Exception as exc:
            if retry_task_id is not None:
                try:
                    code, message, _hint = _error_details(exc)
                    with self._store_factory(self.paths.data_dir / "tasks.sqlite3") as store:
                        task = store.get_task(retry_task_id)
                        if task is not None and task.state == "completed":
                            if store.is_completed_valid(retry_task_id):
                                return ItemResult(
                                    "skipped",
                                    title=task.title,
                                    video_id=task.video_id,
                                    output_path=task.output_path,
                                    hint="另一个进程已完成此本地重试。",
                                )
                            return ItemResult(
                                "failed",
                                title=task.title,
                                video_id=task.video_id,
                                error_code="OUTPUT_INVALID",
                                hint="并发重试完成的输出未通过完整性检查。",
                            )
                        if task is not None and task.state != "failed":
                            return ItemResult(
                                "skipped",
                                title=task.title,
                                video_id=task.video_id,
                                output_path=task.output_path,
                                hint="另一个进程已开始此本地重试；可运行 status 查看进度。",
                            )
                        if task is not None:
                            store.update_failed_retry_error(retry_task_id, code, message)
                except Exception:
                    pass
            return self._failure(None, exc)

    def close(self) -> None:
        """Stop the reusable supervised decoder/ASR process, if it was started."""
        if self._processing_worker is not None:
            self._processing_worker.close()
            self._processing_worker = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def run_urls(self, values: Iterable[str], *, title: str | None = None) -> list[ItemResult]:
        """Resolve URLs, run bounded isolated captures, and transcribe serially."""
        raw_values = validate_url_batch(values)
        if raw_values and self._capture_service_client is None:
            unavailable = CaptureClientError(
                "BROWSER_ISOLATION_UNAVAILABLE",
                "完整作业隔离采集服务不可用；调用方进程内 URL 捕获已禁用",
            )
            return [self._failure(None, unavailable) for _ in raw_values]
        if not raw_values:
            return []
        capture_client = self._capture_service_client
        cancellation = DownloadCancellation()

        results: list[ItemResult | None] = [None] * len(raw_values)
        resolved_jobs: list[tuple[int, ResolvedInput, str]] = []
        duplicate_of: dict[int, int] = {}
        first_index_by_video_id: dict[str, int] = {}
        for index, value in enumerate(raw_values):
            try:
                # This resolver is deliberately limited to parsing direct URLs;
                # short-link network resolution belongs to the isolated client.
                try:
                    resolved = resolve_direct_input(value)
                except UnsupportedUrlError as exc:
                    if exc.code != "BROWSER_ISOLATION_UNAVAILABLE":
                        raise
                    capture_url = extract_url(value)
                    try:
                        video_id = self._resolve_service_source_with_retries(
                            capture_client,
                            capture_url,
                            deadline_monotonic=time.monotonic() + self.max_processing_seconds,
                            cancellation=cancellation,
                        )
                    except KeyboardInterrupt:
                        cancellation.cancel()
                        try:
                            self.close()
                        except Exception:
                            pass
                        raise
                    resolved = resolved_short_link(value, video_id)
                else:
                    capture_url = (
                        extract_url(value)
                        if resolved.source_type == "short_link"
                        else resolved.canonical_url
                    )
            except Exception as exc:
                results[index] = self._failure(None, exc)
                continue
            # For short links capture_url can carry a temporary share token;
            # only the query-free source URL is written to TaskStore.
            previous = first_index_by_video_id.get(resolved.video_id)
            if previous is not None:
                duplicate_of[index] = previous
                continue
            first_index_by_video_id[resolved.video_id] = index
            resolved_jobs.append((index, resolved, capture_url))

        self._recover_stale_tasks()
        pending: list[_CaptureJob] = []
        active_task_generations: dict[str, int] = {}

        @contextmanager
        def capture_executor() -> Iterator[ThreadPoolExecutor]:
            executor = ThreadPoolExecutor(
                max_workers=self.max_downloads,
                thread_name_prefix="transcript-capture",
            )
            try:
                yield executor
            except KeyboardInterrupt:
                cancellation.cancel()
                for job in pending:
                    job.future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                try:
                    self.close()
                except Exception:
                    pass
                try:
                    with self._store_factory(self.paths.data_dir / "tasks.sqlite3") as store:
                        for task_id, claim_generation in tuple(active_task_generations.items()):
                            try:
                                store.fail_task(
                                    task_id,
                                    "CANCELLED",
                                    "用户中断了任务；可以安全重试。",
                                    worker_id=self._worker_id,
                                    claim_generation=claim_generation,
                                )
                            except Exception:
                                # A worker may already have committed this task
                                # as failed or completed while cancellation ran.
                                pass
                except Exception:
                    pass
                raise
            else:
                executor.shutdown(wait=True)

        def wait_for_capture(future: Future[Any]) -> Any:
            # Poll so console interrupts are observed even on platforms where
            # a long Condition wait is not interrupted immediately by SIGINT.
            while True:
                try:
                    return future.result(timeout=0.1)
                except FutureTimeoutError:
                    if future.done():
                        raise

        def flush_captures() -> None:
            nonlocal pending
            for job in pending:
                try:
                    capture_result = wait_for_capture(job.future)
                    _task, validated_media, captured_metadata = capture_result
                except Exception as exc:
                    results[job.index] = self._failure(job.resolved.video_id, exc)
                    active_task_generations.pop(job.task.task_id, None)
                    continue
                results[job.index] = self._transcribe_remote_downloaded(
                    job.task.task_id,
                    job.resolved,
                    title=(
                        captured_metadata.title or job.title
                        if captured_metadata is not None and job.title == job.resolved.video_id
                        else job.title
                    ),
                    metadata=captured_metadata,
                    validated_media=validated_media,
                    processing_deadline=job.processing_deadline,
                    cancellation=cancellation,
                )
                active_task_generations.pop(job.task.task_id, None)
            pending = []

        with capture_executor() as executor:
            for index, resolved, capture_url in resolved_jobs:
                task: Task | None = None
                try:
                    with self._store_factory(self.paths.data_dir / "tasks.sqlite3") as store:
                        task = store.create_remote_task(
                            resolved.canonical_url,
                            resolved.video_id,
                            profile=self.profile,
                            title=title,
                            processing_options=self._processing_options_snapshot(),
                        )
                        cached_validated_media: MediaFile | None = None
                        cached_processing_deadline: float | None = None
                        task, outcome = self._prepare_task(
                            store, task, initial_state="pending", title=title
                        )
                        if outcome is not None:
                            results[index] = outcome
                            continue
                        active_task_generations[task.task_id] = task.claim_generation
                        if task.state == "downloaded":
                            cached_task_id = task.task_id
                        else:
                            cached_task_id = None
                            display_title = title or task.title or resolved.video_id
                            with self._keep_claim_alive(
                                store,
                                task.task_id,
                                claim_generation=task.claim_generation,
                            ) as task_cancellation:
                                if task.media_path:
                                    cache_deadline = time.monotonic() + self.max_processing_seconds
                                    try:
                                        candidate_media = self._validate_media(
                                            Path(task.media_path),
                                            deadline=cache_deadline,
                                            cancellation=task_cancellation,
                                        )
                                    except MediaInvalidError:
                                        candidate_media = None
                                    if candidate_media is not None:
                                        require_media_duration(
                                            candidate_media.duration_seconds,
                                            self.max_media_duration_seconds,
                                        )
                                        require_expected_media_duration(
                                            candidate_media.duration_seconds,
                                            task.source_duration_seconds,
                                        )
                                        task = store.transition(
                                            task.task_id,
                                            "downloaded",
                                            worker_id=self._worker_id,
                                            claim_generation=task.claim_generation,
                                            media_path=task.media_path,
                                            title=display_title,
                                        )
                                        cached_task_id = task.task_id
                                        cached_validated_media = candidate_media
                                        cached_processing_deadline = cache_deadline

                                if cached_task_id is None:
                                    processing_deadline = (
                                        time.monotonic() + self.max_processing_seconds
                                    )
                                    display_title = title or resolved.video_id
                                    transition_options: dict[str, Any] = {
                                        "worker_id": self._worker_id,
                                        "claim_generation": task.claim_generation,
                                        "title": display_title,
                                        "media_path": None,
                                    }
                                    task = store.transition(
                                        task.task_id,
                                        "downloading",
                                        **transition_options,
                                    )
                            if cached_task_id is None:
                                future = executor.submit(
                                    self._capture_remote_claimed,
                                    task,
                                    resolved,
                                    capture_url,
                                    capture_client,
                                    title,
                                    processing_deadline,
                                    cancellation,
                                )
                                pending.append(
                                    _CaptureJob(
                                        index,
                                        task,
                                        resolved,
                                        display_title,
                                        future,
                                        processing_deadline,
                                    )
                                )
                                if len(pending) >= self.max_downloads:
                                    flush_captures()
                    if cached_task_id is not None and task is not None:
                        results[index] = self._transcribe_remote_downloaded(
                            cached_task_id,
                            resolved,
                            title=title or task.title or resolved.video_id,
                            validated_media=cached_validated_media,
                            processing_deadline=cached_processing_deadline
                            or time.monotonic() + self.max_processing_seconds,
                            cancellation=cancellation,
                        )
                        active_task_generations.pop(task.task_id, None)
                except Exception as exc:
                    if task is not None and task.claimed_by == self._worker_id:
                        code, message, _hint = _error_details(exc)
                        try:
                            with self._store_factory(
                                self.paths.data_dir / "tasks.sqlite3"
                            ) as failed_store:
                                failed_store.fail_task(
                                    task.task_id,
                                    code,
                                    message,
                                    worker_id=self._worker_id,
                                    claim_generation=task.claim_generation,
                                )
                        except Exception:
                            pass
                    results[index] = self._failure(resolved.video_id, exc)
                    if task is not None:
                        active_task_generations.pop(task.task_id, None)
            flush_captures()
        for index, first_index in duplicate_of.items():
            first = results[first_index]
            if first is None:
                results[index] = self._failure(
                    None, RuntimeError("duplicate source did not produce a result")
                )
            elif first.status == "failed":
                results[index] = ItemResult(
                    "failed",
                    title=first.title,
                    video_id=first.video_id,
                    error_code=first.error_code,
                    hint="重复链接复用了本批次首次处理结果：" + (first.hint or "处理失败"),
                )
            else:
                results[index] = ItemResult(
                    "skipped",
                    title=first.title,
                    video_id=first.video_id,
                    output_path=first.output_path,
                    hint="本批次重复链接已合并处理。",
                )
        return [item for item in results if item is not None]

    def _processing_options_snapshot(self) -> dict[str, Any]:
        """Return the non-transcript settings needed to reproduce a failed task."""
        return {
            "schema_version": 2,
            "language": self.language,
            "timestamps": self.timestamps,
            "max_processing_seconds": self.max_processing_seconds,
            "max_media_duration_seconds": self.max_media_duration_seconds,
            "max_output_segments": self.max_output_segments,
            "max_output_characters": self.max_output_characters,
            "max_downloads": self.max_downloads,
            "retries": self.retries,
            "correction_rules_enabled": self.corrections_enabled,
            "correction_rules": [
                {
                    "rule_id": rule.rule_id,
                    "source": rule.source,
                    "replacement": rule.replacement,
                    "note": rule.note,
                }
                for rule in self.correction_rules
            ],
            "output_dir": str(self.paths.output_dir.expanduser().resolve(strict=False)),
        }

    def _resolve_service_source_with_retries(
        self,
        client: Any,
        original_url: str,
        *,
        deadline_monotonic: float,
        cancellation: DownloadCancellation | None = None,
    ) -> str:
        cancellation = cancellation or DownloadCancellation()
        for attempt in range(self.retries + 1):
            if cancellation.is_set():
                raise CaptureClientError("CANCELLED", "隔离采集已取消")
            try:
                return client.resolve_source(
                    original_url,
                    deadline_monotonic=deadline_monotonic,
                    is_cancelled=cancellation.is_set,
                )
            except CaptureClientError as exc:
                remaining = deadline_monotonic - time.monotonic()
                if not exc.retryable or attempt >= self.retries or remaining <= 0:
                    raise
                if cancellation.wait(min(0.25 * (2**attempt), remaining)):
                    raise CaptureClientError("CANCELLED", "隔离采集已取消") from None
        raise RuntimeError("capture source resolution retry loop ended unexpectedly")

    def _capture_service_with_retries(
        self,
        client: Any,
        original_url: str,
        *,
        deadline_monotonic: float,
        cancellation: DownloadCancellation,
    ) -> Any:
        for attempt in range(self.retries + 1):
            if cancellation.is_set():
                raise CaptureClientError("CANCELLED", "隔离采集已取消")
            try:
                return client.capture(
                    original_url,
                    deadline_monotonic=deadline_monotonic,
                    is_cancelled=cancellation.is_set,
                )
            except CaptureClientError as exc:
                remaining = deadline_monotonic - time.monotonic()
                if not exc.retryable or attempt >= self.retries or remaining <= 0:
                    raise
                if cancellation.wait(min(0.25 * (2**attempt), remaining)):
                    raise CaptureClientError("CANCELLED", "隔离采集已取消") from None
        raise RuntimeError("capture retry loop ended unexpectedly")

    def _capture_remote_claimed(
        self,
        task: Task,
        resolved: ResolvedInput,
        original_url: str,
        client: Any,
        requested_title: str | None,
        processing_deadline: float,
        cancellation: DownloadCancellation,
    ) -> tuple[Task, MediaFile, CaptureVideoMetadata]:
        captured: Any | None = None
        media_path: Path | None = None
        transitioned_to_downloaded = False
        with self._store_factory(self.paths.data_dir / "tasks.sqlite3") as store:
            try:
                with self._keep_claim_alive(
                    store,
                    task.task_id,
                    claim_generation=task.claim_generation,
                    parent_cancellation=cancellation,
                ) as task_cancellation:
                    captured = self._capture_service_with_retries(
                        client,
                        original_url,
                        deadline_monotonic=processing_deadline,
                        cancellation=task_cancellation,
                    )
                    media_path = Path(captured.path)
                    if captured.video.video_id != resolved.video_id:
                        raise CaptureClientError(
                            "INVALID_RESULT", "隔离服务返回的内容与原视频 ID 不匹配"
                        )
                    cache_root = (self.paths.data_dir / "media-cache").resolve(strict=True)
                    resolved_media_path = media_path.resolve(strict=True)
                    if (
                        media_path.is_symlink()
                        or not resolved_media_path.is_relative_to(cache_root)
                        or resolved_media_path == cache_root
                        or not resolved_media_path.is_file()
                    ):
                        raise CaptureClientError("MEDIA_INVALID", "隔离服务返回的媒体文件路径无效")
                    validated = self._validate_media(
                        resolved_media_path,
                        deadline=processing_deadline,
                        cancellation=task_cancellation,
                    )
                    require_media_duration(
                        validated.duration_seconds, self.max_media_duration_seconds
                    )
                    require_expected_media_duration(
                        validated.duration_seconds, captured.duration_seconds
                    )
                    require_expected_media_duration(
                        validated.duration_seconds, captured.video.duration_seconds
                    )
                    display_title = requested_title or captured.video.title or resolved.video_id
                    downloaded_task = store.transition(
                        task.task_id,
                        "downloaded",
                        worker_id=self._worker_id,
                        claim_generation=task.claim_generation,
                        media_path=resolved_media_path,
                        title=display_title,
                        source_duration_seconds=validated.duration_seconds,
                    )
                    transitioned_to_downloaded = True
                    return downloaded_task, validated, captured.video
            except Exception as exc:
                if media_path is not None and not transitioned_to_downloaded:
                    try:
                        cache_root = (self.paths.data_dir / "media-cache").resolve(strict=True)
                        resolved_media_path = media_path.resolve(strict=True)
                        if resolved_media_path.is_relative_to(cache_root):
                            resolved_media_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                normalized_exc = exc
                if (
                    isinstance(exc, CaptureClientError)
                    and exc.code == "CAPTURE_TIMEOUT"
                    and time.monotonic() >= processing_deadline
                ):
                    normalized_exc = ProcessingTimeoutError()
                code, message, _hint = _error_details(normalized_exc)
                try:
                    store.fail_task(
                        task.task_id,
                        code,
                        message,
                        worker_id=self._worker_id,
                        claim_generation=task.claim_generation,
                    )
                except Exception:
                    pass
                if normalized_exc is not exc:
                    raise normalized_exc from None
                raise

    def _transcribe_remote_downloaded(
        self,
        task_id: str,
        resolved: ResolvedInput,
        *,
        title: str,
        metadata: CaptureVideoMetadata | None = None,
        validated_media: MediaFile | None = None,
        processing_deadline: float | None = None,
        cancellation: DownloadCancellation | None = None,
    ) -> ItemResult:
        with self._store_factory(self.paths.data_dir / "tasks.sqlite3") as store:
            task = store.get_task(task_id)
            if task is None:
                return self._failure(resolved.video_id, KeyError("task not found"))
            if task.state == "completed" and store.is_completed_valid(task_id):
                return ItemResult(
                    "skipped",
                    title=task.title,
                    video_id=task.video_id,
                    output_path=task.output_path,
                )
            if task.state != "downloaded" or task.claimed_by != self._worker_id:
                return ItemResult(
                    "failed",
                    title=title,
                    video_id=resolved.video_id,
                    error_code="TASK_LOCKED",
                    hint="下载完成后任务已由另一个进程接管，请稍后查看 status。",
                )
            media_path = Path(task.media_path or "")
            with self._keep_claim_alive(
                store,
                task_id,
                claim_generation=task.claim_generation,
                parent_cancellation=cancellation,
            ) as task_cancellation:
                return self._transcribe_claimed(
                    store,
                    task,
                    media_path=media_path,
                    title=title or task.title or resolved.video_id,
                    source_url=task.source_url,
                    video_id=resolved.video_id,
                    duration_hint=task.source_duration_seconds,
                    metadata=(
                        {"author": metadata.author, "publish_date": metadata.publish_date}
                        if metadata is not None
                        else None
                    ),
                    validated_media=validated_media,
                    processing_deadline=processing_deadline,
                    cancellation=task_cancellation,
                )

    def _recover_stale_tasks(self) -> None:
        database = self.paths.data_dir / "tasks.sqlite3"
        if not database.is_file():
            return
        with self._store_factory(database) as store:
            # Recovery only needs to decide whether a cache candidate exists.
            # Full decoding here would block every later task at startup; the
            # claimed processing path performs strict validation under its deadline.
            store.recover_interrupted(
                stale_after_seconds=self._stale_after_seconds,
                defer_media_validation=True,
            )

    def _validate_media(
        self,
        path: str | Path,
        *,
        deadline: float | None = None,
        cancellation: DownloadCancellation | None = None,
    ) -> MediaFile:
        if self._use_supervised_processing:
            if self._processing_worker is None:
                self._processing_worker = SupervisedProcessingWorker()
            return self._processing_worker.validate_media(
                path,
                max_duration_seconds=self.max_media_duration_seconds,
                deadline=deadline,
                cancellation=cancellation,
            )
        return self._media_validator(Path(path))

    @contextmanager
    def _keep_claim_alive(
        self,
        store: TaskStore,
        task_id: str,
        *,
        claim_generation: int,
        parent_cancellation: DownloadCancellation | None = None,
    ) -> Iterator[DownloadCancellation]:
        stop = threading.Event()
        cancellation = (
            parent_cancellation.linked_child()
            if parent_cancellation is not None
            else DownloadCancellation()
        )

        def heartbeat() -> None:
            while not stop.wait(self._heartbeat_interval_seconds):
                try:
                    if not store.heartbeat_claim(
                        task_id,
                        self._worker_id,
                        claim_generation=claim_generation,
                    ):
                        cancellation.cancel()
                        return
                except Exception:
                    # If ownership cannot be confirmed, stop this task before
                    # it can publish output under a released or replaced claim.
                    cancellation.cancel()
                    return

        thread = threading.Thread(target=heartbeat, name="transcript-task-heartbeat", daemon=True)
        thread.start()
        try:
            yield cancellation
        finally:
            stop.set()
            thread.join(timeout=min(self._heartbeat_interval_seconds, 2))
            cancellation.cancel()

    def _prepare_task(
        self,
        store: TaskStore,
        task: Task,
        *,
        initial_state: str,
        title: str | None = None,
    ) -> tuple[Task, ItemResult | None]:
        if task.state == "completed":
            if not self.force:
                if store.is_completed_valid(task.task_id):
                    return task, ItemResult(
                        "skipped",
                        title=task.title,
                        video_id=task.video_id,
                        output_path=task.output_path,
                    )
                return task, ItemResult(
                    "failed",
                    title=task.title,
                    video_id=task.video_id,
                    error_code="OUTPUT_INVALID",
                    hint=(
                        "已完成任务的 Markdown 缺失或关联信息不匹配；检查文件后使用 --force 重跑。"
                    ),
                )
            task = store.reopen_completed(
                task.task_id,
                initial_state=initial_state,
                profile=self.profile,
                title=title,
                processing_options=self._processing_options_snapshot(),
            )
        elif task.state == "failed" and self.force and not task.local_path:
            queued = store.retry_failed(
                task_id=task.task_id,
                include_login_required=True,
                processing_options=self._processing_options_snapshot(),
            )
            if not queued:
                return task, ItemResult(
                    "failed",
                    video_id=task.video_id,
                    error_code="TASK_LOCKED",
                    hint="任务状态已改变，请稍后重试。",
                )
            task = queued[0]
        elif task.state == "failed":
            return task, ItemResult(
                "failed",
                title=task.title,
                video_id=task.video_id,
                error_code=task.error_code or "PREVIOUS_FAILURE",
                hint=(
                    "此本地任务上次失败；检查输入后可使用 --force 重跑，或运行 retry-failed。"
                    if task.local_path
                    else "此任务上次失败；使用 --force 重跑，或运行 retry-failed。"
                ),
            )

        if task.claimed_by and task.claimed_by != self._worker_id:
            return task, ItemResult(
                "failed",
                title=task.title,
                video_id=task.video_id,
                error_code="TASK_LOCKED",
                hint="任务当前由另一个进程处理。",
            )
        claimed = store.claim_task(task.task_id, self._worker_id)
        if claimed is None:
            # Local tasks are created directly in the downloaded state and
            # must be claimed; a failed claim means another worker owns it.
            return task, ItemResult(
                "failed",
                title=task.title,
                video_id=task.video_id,
                error_code="TASK_LOCKED",
                hint="任务当前由另一个进程处理。",
            )
        return claimed, None

    def _transcribe_claimed(
        self,
        store: TaskStore,
        task: Task,
        *,
        media_path: Path,
        title: str,
        source_url: str,
        video_id: str | None,
        duration_hint: float | None,
        metadata: dict[str, Any] | None = None,
        validated_media: MediaFile | None = None,
        processing_deadline: float | None = None,
        cancellation: DownloadCancellation | None = None,
    ) -> ItemResult:
        try:
            if task.state == "downloaded":
                task = store.transition(
                    task.task_id,
                    "transcribing",
                    worker_id=self._worker_id,
                    claim_generation=task.claim_generation,
                )
            media = validated_media or self._validate_media(
                media_path,
                deadline=processing_deadline,
                cancellation=cancellation,
            )
            require_media_duration(media.duration_seconds, self.max_media_duration_seconds)
            require_expected_media_duration(media.duration_seconds, duration_hint)
            if self._use_supervised_processing:
                if self._processing_worker is None:
                    self._processing_worker = SupervisedProcessingWorker()
                result = self._processing_worker.transcribe(
                    media,
                    data_dir=self.paths.data_dir,
                    profile=self.profile,
                    language=self.language,
                    max_media_duration_seconds=self.max_media_duration_seconds,
                    max_output_segments=self.max_output_segments,
                    max_output_characters=self.max_output_characters,
                    deadline=processing_deadline,
                    cancellation=cancellation,
                )
            else:
                if self._asr is None:
                    self._asr = self._asr_factory(
                        self.paths.data_dir,
                        self.profile,
                        max_media_duration_seconds=self.max_media_duration_seconds,
                        max_output_segments=self.max_output_segments,
                        max_output_characters=self.max_output_characters,
                    )
                if isinstance(self._asr, LocalASR):
                    result = self._asr.transcribe(
                        media_path,
                        language=self.language,
                        validated_media=media,
                    )
                else:
                    result = self._asr.transcribe(media_path, language=self.language)
            if (
                len(result.segments) > self.max_output_segments
                or sum(len(segment.text) for segment in result.segments)
                > self.max_output_characters
            ):
                raise ResourceLimitError(
                    "ASR_OUTPUT_LIMIT",
                    "识别结果超过设置的分段数或字符数上限；可通过 limits 配置或命令行调整。",
                )
            normalized = normalize_segments(result.segments)
            correction_budget = CorrectionWorkBudget()
            correction = apply_terminology_dictionary(
                normalized.text,
                self.correction_rules,
                enabled=self.corrections_enabled,
                max_output_characters=self.max_output_characters,
                work_budget=correction_budget,
            )
            timeline_limit = min(
                self.max_output_characters + self.max_output_segments * 16,
                HARD_MAX_OUTPUT_CHARACTERS + 100_000 * 16,
            )
            corrected_timeline = apply_terminology_dictionary(
                normalized.timeline_text,
                self.correction_rules,
                enabled=self.corrections_enabled,
                max_output_characters=timeline_limit,
                work_budget=correction_budget,
            ).text
            if len(correction.text) > self.max_output_characters:
                raise ResourceLimitError(
                    "ASR_OUTPUT_LIMIT",
                    "整理后的识别文本超过设置的字符数上限；可通过 limits 配置或命令行调整。",
                )
            if not correction.text.strip():
                raise _PipelineFailure("ASR_EMPTY", "没有识别到可保存的口播内容。")

            output_metadata: dict[str, Any] = {
                "duration_seconds": result.duration_seconds
                or duration_hint
                or media.duration_seconds,
                "language": result.language or self.language,
                "model": result.model,
                "profile": result.profile,
            }
            if self.correction_rules or self.corrections_enabled:
                output_metadata["terminology_corrections"] = json.dumps(
                    correction.archive_record(),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            if video_id:
                output_metadata["source_url"] = source_url
                output_metadata["video_id"] = video_id
            else:
                output_metadata["source"] = "local_file"
                output_metadata["task_id"] = task.task_id
            if metadata:
                output_metadata.update(
                    {key: value for key, value in metadata.items() if value is not None}
                )

            expected_content = render_transcript_markdown(title, correction.text, output_metadata)
            expected_sha256 = hashlib.sha256(expected_content.encode("utf-8")).hexdigest()
            output_path = next(
                path
                for path in candidate_output_paths(self.paths.output_dir, title, video_id)
                if not path.exists()
            )
            task = store.transition(
                task.task_id,
                "writing",
                worker_id=self._worker_id,
                claim_generation=task.claim_generation,
                output_path=output_path,
                timeline_required=bool(self.timestamps and normalized.timeline_lines),
            )
            output_path = self._markdown_writer(
                self.paths.output_dir,
                title,
                correction.text,
                output_metadata,
                video_id=video_id,
            )
            task = store.set_writing_output_path(
                task.task_id,
                output_path,
                worker_id=self._worker_id,
                claim_generation=task.claim_generation,
            )
            store.record_output_integrity(
                task.task_id,
                output_path,
                expected_sha256,
                worker_id=self._worker_id,
                claim_generation=task.claim_generation,
            )
            if self.timestamps and normalized.timeline_lines:
                self._write_timeline(
                    output_path,
                    title,
                    corrected_timeline,
                    store=store,
                    task_id=task.task_id,
                    worker_id=self._worker_id,
                    claim_generation=task.claim_generation,
                )
            completed = store.complete_task(
                task.task_id,
                output_path,
                worker_id=self._worker_id,
                claim_generation=task.claim_generation,
            )
            return ItemResult(
                "success",
                title=title,
                video_id=video_id,
                output_path=completed.output_path,
                duration_seconds=media.duration_seconds,
            )
        except Exception as exc:
            code, message, hint = _error_details(exc)
            try:
                store.fail_task(
                    task.task_id,
                    code,
                    message,
                    worker_id=self._worker_id,
                    claim_generation=task.claim_generation,
                )
            except Exception:
                pass
            return ItemResult(
                "failed",
                title=title,
                video_id=video_id,
                error_code=code,
                hint=hint or message,
            )

    def _write_timeline(
        self,
        output_path: Path,
        title: str,
        timeline: str,
        *,
        store: TaskStore | None = None,
        task_id: str | None = None,
        worker_id: str | None = None,
        claim_generation: int | None = None,
    ) -> Path:
        content = f"# {escape_markdown_text(title)} — 时间轴\n\n{escape_markdown_text(timeline)}\n"
        expected_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        base = f"{output_path.stem}_timeline"
        for index in range(1, 10000):
            suffix = "" if index == 1 else f"__{index}"
            timeline_path = output_path.with_name(f"{base}{suffix}.md")
            if store is not None:
                if task_id is None:
                    raise ValueError("task_id is required when binding timeline integrity")
                store.prepare_timeline_integrity(
                    task_id,
                    timeline_path,
                    expected_sha256,
                    worker_id=worker_id,
                    claim_generation=claim_generation,
                )
            try:
                _atomic_publish(timeline_path, content)
                return timeline_path
            except FileExistsError:
                continue
        raise FileExistsError("unable to find an unused timeline filename")

    @staticmethod
    def _failure(video_id: str | None, exc: Exception) -> ItemResult:
        code, message, hint = _error_details(exc)
        return ItemResult(
            "failed",
            video_id=video_id,
            error_code=code,
            hint=hint or message,
        )


class _PipelineFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _error_details(exc: Exception) -> tuple[str, str, str | None]:
    if isinstance(exc, _PipelineFailure):
        return exc.code, str(exc), None
    if isinstance(exc, ResourceLimitError):
        if exc.code == "TERMINOLOGY_WORK_LIMIT":
            return exc.code, str(exc), "精简术语词典后重试，或不启用术语纠错。"
        if exc.code == "TERMINOLOGY_DICTIONARY_LIMIT":
            return exc.code, str(exc), "精简术语词典中的规则或备注后重试。"
        return exc.code, str(exc), "调低媒体时长或 ASR 输出，或按需提高配置上限后重试。"
    if isinstance(exc, UnsupportedUrlError):
        if exc.code == "BROWSER_ISOLATION_UNAVAILABLE":
            return (
                exc.code,
                str(exc),
                "短链接解析需要可用的系统隔离服务；当前可改用抖音直链或本地媒体。",
            )
        return exc.code, str(exc), "检查链接格式，或改用有权处理的本地媒体文件。"
    if isinstance(exc, CaptureClientError):
        hint = (
            "请先安装并启动经验证的管理员隔离服务；当前不支持在调用进程中直接采集。"
            if exc.code in {"BROWSER_ISOLATION_UNAVAILABLE", "CAPTURE_TRANSPORT_FAILED"}
            else None
        )
        return exc.code, str(exc), hint
    if isinstance(exc, MediaInvalidError):
        return exc.code, str(exc), "确认媒体文件完整且包含可解码音轨。"
    if isinstance(exc, DownloadError):
        return exc.code, str(exc), None
    if isinstance(exc, ASRUnavailableError):
        message = str(exc)
        code = "MODEL_NOT_FOUND" if "模型" in message else "ASR_DEPENDENCY_MISSING"
        return code, message, "运行 doctor 检查 ASR 依赖和本地模型。"
    if isinstance(exc, DecoderUnavailableError):
        return exc.code, str(exc), "安装项目的媒体解码依赖后重试。"
    if isinstance(exc, PermissionError):
        return "OUTPUT_NOT_WRITABLE", "目标目录或文件不可写。", "检查输出目录权限或更换输出路径。"
    if isinstance(exc, OSError):
        return "OUTPUT_OR_MEDIA_IO", f"文件操作失败（{type(exc).__name__}）", "检查路径和目录权限。"
    return "TRANSCRIPTION_FAILED", f"处理失败（{type(exc).__name__}）", "检查环境后重试。"
