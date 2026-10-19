"""Subprocess harness for abrupt pipeline termination and recovery tests."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from douyin_transcript.asr import TranscriptionResult, TranscriptSegment
from douyin_transcript.capture_client import CapturedMedia
from douyin_transcript.capture_ipc import CaptureVideoMetadata
from douyin_transcript.config import RuntimePaths
from douyin_transcript.downloader import MediaFile
from douyin_transcript.pipeline import TranscriptionPipeline
from douyin_transcript.tasks import TaskStore

_CRASH_EXIT_CODE = 86
_URL = "https://www.douyin.com/video/123"


def _read_events(path: Path) -> dict[str, int]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _increment(path: Path, key: str) -> None:
    events = _read_events(path)
    events[key] = events.get(key, 0) + 1
    path.write_text(json.dumps(events, sort_keys=True), encoding="utf-8")


class _CaptureService:
    def __init__(self, cache_dir: Path, events_path: Path) -> None:
        self._cache_dir = cache_dir
        self._events_path = events_path

    def capture(self, _original_url: str, **_kwargs) -> CapturedMedia:
        _increment(self._events_path, "capture_calls")
        media_bytes = b"synthetic complete media fixture"
        digest = hashlib.sha256(media_bytes).hexdigest()
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        media_path = self._cache_dir / f"123-audio-{digest[:16]}.m4a"
        media_path.write_bytes(media_bytes)
        _increment(self._events_path, "download_calls")
        return CapturedMedia(
            CaptureVideoMetadata(
                "123", "Crash recovery fixture", "Fixture author", None, 5.0
            ),
            media_path,
            len(media_bytes),
            digest,
            "audio/mp4",
            5.0,
        )


class _ASR:
    def __init__(self, events_path: Path) -> None:
        self._events_path = events_path

    def transcribe(self, _path: Path, *, language: str) -> TranscriptionResult:
        _increment(self._events_path, "asr_calls")
        return TranscriptionResult(
            (TranscriptSegment(0.0, 2.0, "测试恢复。"),),
            5.0,
            "zh" if language == "zh" else "en",
            "test-model",
            "balanced",
        )


def _main() -> int:
    data_dir, output_dir, events_path = map(Path, sys.argv[1:4])
    mode = sys.argv[4]
    crash_at = sys.argv[5] if len(sys.argv) > 5 else ""
    paths = RuntimePaths(
        data_dir=data_dir,
        output_dir=output_dir,
        config_path=data_dir / "config.toml",
    )

    def validate_media(path: Path) -> MediaFile:
        if not path.is_file():
            raise FileNotFoundError(path)
        return MediaFile(path, "mp4", path.stat().st_size, 5.0)

    def asr_factory(_data_dir: Path, _profile: str, **_kwargs) -> _ASR:
        return _ASR(events_path)

    if mode == "crash":
        original_transition = TaskStore.transition

        def transition_then_crash(
            store: TaskStore, task_id: str, new_state: str, **kwargs: Any
        ):
            task = original_transition(store, task_id, new_state, **kwargs)
            if new_state == crash_at:
                # os._exit skips Python cleanup and closes the SQLite handle
                # only when the operating system tears down this process.
                os._exit(_CRASH_EXIT_CODE)
            return task

        TaskStore.transition = transition_then_crash

    pipeline = TranscriptionPipeline(
        paths,
        capture_service_client=_CaptureService(data_dir / "media-cache", events_path),
        media_validator=validate_media,
        asr_factory=asr_factory,
        stale_after_seconds=0,
        heartbeat_interval_seconds=0.05,
    )
    try:
        results = pipeline.run_urls([_URL])
        if mode == "resume":
            payload = {
                "status": results[0].status,
                "error_code": results[0].error_code,
                "output_path": results[0].output_path,
                "events": _read_events(events_path),
            }
            (data_dir / "resume-result.json").write_text(
                json.dumps(payload, ensure_ascii=True, sort_keys=True),
                encoding="utf-8",
            )
        return 0
    finally:
        pipeline.close()


if __name__ == "__main__":
    raise SystemExit(_main())
