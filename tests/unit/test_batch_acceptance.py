from __future__ import annotations

import hashlib
import threading
import time
from collections import Counter
from pathlib import Path

from douyin_transcript.asr import TranscriptionResult, TranscriptSegment
from douyin_transcript.capture_client import CaptureClientError, CapturedMedia
from douyin_transcript.capture_ipc import CaptureVideoMetadata
from douyin_transcript.config import RuntimePaths
from douyin_transcript.downloader import MediaFile
from douyin_transcript.pipeline import TranscriptionPipeline
from douyin_transcript.tasks import TaskStore


def test_fifty_item_mixed_batch_has_bounded_work_and_no_missing_results(tmp_path):
    paths = RuntimePaths(
        data_dir=tmp_path / "data",
        output_dir=tmp_path / "output",
        config_path=tmp_path / "data" / "config.toml",
    )
    state_lock = threading.Lock()
    active_captures = 0
    maximum_captures = 0
    active_asr = 0
    maximum_asr = 0

    class CaptureService:
        def capture(self, original_url: str, **_kwargs) -> CapturedMedia:
            nonlocal active_captures, maximum_captures
            video_id = original_url.rsplit("/", 1)[-1]
            with state_lock:
                active_captures += 1
                maximum_captures = max(maximum_captures, active_captures)
            try:
                time.sleep(0.002)
                if video_id in {"10", "11", "12", "13"}:
                    raise CaptureClientError(
                        "DOWNLOAD_FAILED", "simulated capture failure"
                    )
                media_bytes = b"x" * 65536
                digest = hashlib.sha256(media_bytes).hexdigest()
                cache_dir = paths.data_dir / "media-cache"
                cache_dir.mkdir(parents=True, exist_ok=True)
                media = cache_dir / f"{video_id}-audio-{digest[:16]}.m4a"
                media.write_bytes(media_bytes)
                return CapturedMedia(
                    CaptureVideoMetadata(
                        video_id,
                        f"标题 {video_id}",
                        "模拟作者",
                        None,
                        5.0,
                    ),
                    media,
                    len(media_bytes),
                    digest,
                    "audio/mp4",
                    5.0,
                )
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
                time.sleep(0.001)
                return TranscriptionResult(
                    (TranscriptSegment(0.0, 1.0, "模拟逐字稿。"),),
                    5.0,
                    language,
                    "fake-model",
                    "balanced",
                )
            finally:
                with state_lock:
                    active_asr -= 1

    def validate_media(path: Path) -> MediaFile:
        return MediaFile(path, "mp4", path.stat().st_size, 5.0)

    def make_pipeline() -> TranscriptionPipeline:
        return TranscriptionPipeline(
            paths,
            max_downloads=2,
            retries=0,
            capture_service_client=CaptureService(),
            media_validator=validate_media,
            asr_factory=lambda *_args, **_kwargs: SerialASR(),
        )

    first = make_pipeline().run_urls(
        [f"https://www.douyin.com/video/{video_id}" for video_id in range(1, 9)]
    )
    assert len(first) == 8
    assert all(result.status == "success" for result in first)

    batch = [f"https://www.douyin.com/video/{video_id}" for video_id in range(1, 48)]
    batch.extend(
        [
            "https://www.douyin.com/video/1",
            "https://www.douyin.com/video/9",
            "https://www.douyin.com/video/10",
        ]
    )
    results = make_pipeline().run_urls(batch)

    assert len(results) == 50
    assert Counter(result.status for result in results) == {
        "success": 35,
        "skipped": 10,
        "failed": 5,
    }
    assert maximum_captures <= 2
    assert maximum_asr == 1
    assert len(list(paths.output_dir.glob("*.md"))) == 43
    cache_files = list((paths.data_dir / "media-cache").glob("*-audio-*.m4a"))
    assert len(cache_files) == 43
    assert sum(path.stat().st_size for path in cache_files) == 43 * 65536

    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        tasks = store.list_tasks()
        assert len(tasks) == 47
        assert sum(task.state == "completed" for task in tasks) == 43
        assert sum(task.state == "failed" for task in tasks) == 4
        assert all(
            store.is_completed_valid(str(video_id))
            for video_id in range(1, 10)
            if video_id != 0
        )
        assert all(
            store.get_task(str(video_id)).error_code == "DOWNLOAD_FAILED"
            for video_id in range(10, 14)
        )
