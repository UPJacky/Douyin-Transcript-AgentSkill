"""Killable, JSON-only worker for media decoding and local ASR."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .asr import ASRUnavailableError, TranscriptionResult, TranscriptSegment
from .downloader import (
    DecoderUnavailableError,
    DownloadError,
    MediaFile,
    MediaIdentity,
    MediaInvalidError,
)
from .limits import ResourceLimitError

_MAX_REQUEST_BYTES = 128 * 1024
_MAX_RESPONSE_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_PROCESSING_SECONDS = 2 * 60 * 60
HARD_MAX_PROCESSING_SECONDS = 24 * 60 * 60


class ProcessingTimeoutError(DownloadError):
    """An item's download, decoding, or ASR exceeded its absolute deadline."""

    def __init__(self) -> None:
        super().__init__("PROCESSING_TIMEOUT", "媒体解码或转写超过处理时限")


class ProcessingWorkerError(DownloadError):
    """The supervised worker exited or violated its bounded JSON protocol."""

    def __init__(self) -> None:
        super().__init__("PROCESSING_WORKER_FAILED", "媒体处理子进程异常退出")


def _raise_if_cancelled(cancellation: Any | None, *, stop=None) -> None:
    if cancellation is None or not cancellation.is_set():
        return
    if stop is not None:
        stop(force=True)
    raise DownloadError("CANCELLED", "媒体处理已取消")


class SupervisedProcessingWorker:
    """Own one reusable child process; terminate it when a call misses deadline.

    Requests and responses use bounded UTF-8 JSON frames. No Python objects,
    transcript pickles, or inherited Python connections cross the boundary.
    """

    def __init__(self, *, command: Sequence[str] | None = None) -> None:
        self._lock = threading.Lock()
        if command is not None and (
            not command or any(not isinstance(part, str) or not part for part in command)
        ):
            raise ValueError("worker command must be a non-empty argument sequence")
        self._command = tuple(command) if command is not None else None
        self._process: subprocess.Popen[bytes] | None = None
        self._responses: queue.Queue[bytes | None] | None = None
        self._reader: threading.Thread | None = None

    def validate_media(
        self,
        path: str | Path,
        *,
        max_duration_seconds: float,
        deadline: float | None = None,
        cancellation: Any | None = None,
    ) -> MediaFile:
        response = self._request(
            {
                "command": "validate",
                "path": str(Path(path).expanduser()),
                "max_duration_seconds": max_duration_seconds,
            },
            deadline=deadline,
            cancellation=cancellation,
        )
        return _media_from_json(response)

    def transcribe(
        self,
        media: MediaFile,
        *,
        data_dir: Path,
        profile: str,
        language: str,
        max_media_duration_seconds: float,
        max_output_segments: int,
        max_output_characters: int,
        deadline: float | None = None,
        cancellation: Any | None = None,
    ) -> Any:
        response = self._request(
            {
                "command": "transcribe",
                "path": str(media.path),
                "media": _media_to_json(media),
                "data_dir": str(data_dir),
                "profile": profile,
                "language": language,
                "max_media_duration_seconds": max_media_duration_seconds,
                "max_output_segments": max_output_segments,
                "max_output_characters": max_output_characters,
            },
            deadline=deadline,
            cancellation=cancellation,
        )
        try:
            segments = tuple(
                TranscriptSegment(
                    start=float(item["start"]),
                    end=float(item["end"]),
                    text=str(item["text"]),
                )
                for item in response["segments"]
            )
            return TranscriptionResult(
                segments=segments,
                duration_seconds=(
                    float(response["duration_seconds"])
                    if response["duration_seconds"] is not None
                    else None
                ),
                language=response["language"],
                model=str(response["model"]),
                profile=str(response["profile"]),
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            self._stop(force=True)
            raise ProcessingWorkerError() from None

    def _request(
        self,
        payload: dict[str, Any],
        *,
        deadline: float | None,
        cancellation: Any | None = None,
    ) -> dict[str, Any]:
        if deadline is None:
            deadline = time.monotonic() + DEFAULT_MAX_PROCESSING_SECONDS
        while True:
            _raise_if_cancelled(cancellation)
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                raise ProcessingTimeoutError()
            if self._lock.acquire(timeout=min(timeout, 0.1)):
                break
        try:
            _raise_if_cancelled(cancellation, stop=self._stop)
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                raise ProcessingTimeoutError()
            process = self._ensure_started()
            _raise_if_cancelled(cancellation, stop=self._stop)
            encoded = _encode_frame(payload, _MAX_REQUEST_BYTES)
            try:
                assert process.stdin is not None
                process.stdin.write(encoded)
                process.stdin.flush()
            except (BrokenPipeError, OSError, ValueError):
                self._stop(force=True)
                raise ProcessingWorkerError() from None
            responses = self._responses
            if responses is None:
                self._stop(force=True)
                raise ProcessingWorkerError()
            while True:
                _raise_if_cancelled(cancellation, stop=self._stop)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._stop(force=True)
                    raise ProcessingTimeoutError()
                try:
                    frame = responses.get(timeout=min(remaining, 0.1))
                    break
                except queue.Empty:
                    continue
            if time.monotonic() >= deadline:
                self._stop(force=True)
                raise ProcessingTimeoutError()
            if frame is None or len(frame) > _MAX_RESPONSE_BYTES or not frame.endswith(b"\n"):
                self._stop(force=True)
                raise ProcessingWorkerError()
            try:
                response = json.loads(frame)
            except (UnicodeError, json.JSONDecodeError):
                self._stop(force=True)
                raise ProcessingWorkerError() from None
            if not isinstance(response, dict):
                self._stop(force=True)
                raise ProcessingWorkerError()
            if response.get("ok") is True:
                result = response.get("result")
                if not isinstance(result, dict):
                    self._stop(force=True)
                    raise ProcessingWorkerError()
                return result
            _raise_worker_error(response.get("error"))
        finally:
            self._lock.release()

    def _ensure_started(self) -> subprocess.Popen[bytes]:
        if self._process is not None and self._process.poll() is None:
            return self._process
        self._stop(force=True)
        source_root = str(Path(__file__).resolve().parent.parent)
        environment = os.environ.copy()
        existing_pythonpath = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = source_root + (
            os.pathsep + existing_pythonpath if existing_pythonpath else ""
        )
        options: dict[str, Any] = {}
        if os.name == "nt":
            options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            command = self._command or (
                sys.executable,
                "-P",
                "-m",
                "douyin_transcript.processing_worker",
            )
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=environment,
                **options,
            )
        except OSError:
            raise ProcessingWorkerError() from None
        responses: queue.Queue[bytes | None] = queue.Queue(maxsize=1)
        reader = threading.Thread(
            target=_read_responses,
            args=(process, responses),
            name="transcript-processing-ipc",
            daemon=True,
        )
        self._process = process
        self._responses = responses
        self._reader = reader
        reader.start()
        return process

    def _stop(self, *, force: bool) -> None:
        process = self._process
        self._process = None
        responses = self._responses
        self._responses = None
        reader = self._reader
        self._reader = None
        if process is None:
            return
        if process.poll() is None and not force:
            try:
                if process.stdin is not None:
                    process.stdin.write(b'{"command":"close"}\n')
                    process.stdin.flush()
                process.wait(timeout=1.0)
            except (OSError, subprocess.TimeoutExpired, ValueError):
                force = True
        if process.poll() is None and force:
            try:
                process.terminate()
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                    process.wait(timeout=1.0)
                except OSError:
                    pass
            except OSError:
                pass
        for stream in (process.stdin, process.stdout):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        if reader is not None and reader is not threading.current_thread():
            reader.join(timeout=0.2)
        del responses

    def close(self) -> None:
        """Ask the child to exit cleanly, then force-stop it if necessary."""
        if not self._lock.acquire(timeout=1.0):
            return
        try:
            self._stop(force=False)
        finally:
            self._lock.release()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


def _read_responses(process: subprocess.Popen[bytes], responses: queue.Queue[bytes | None]) -> None:
    try:
        assert process.stdout is not None
        while True:
            frame = process.stdout.readline(_MAX_RESPONSE_BYTES + 1)
            if not frame:
                try:
                    responses.put_nowait(None)
                except queue.Full:
                    pass
                return
            responses.put(frame)
    except (OSError, ValueError):
        try:
            responses.put_nowait(None)
        except queue.Full:
            pass


def _encode_frame(payload: dict[str, Any], limit: int) -> bytes:
    try:
        frame = (
            json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode(
                "utf-8"
            )
            + b"\n"
        )
    except (TypeError, ValueError, UnicodeError):
        raise ValueError("invalid processing worker request") from None
    if len(frame) > limit:
        raise ValueError("processing worker request exceeds protocol limit")
    return frame


def _media_to_json(media: MediaFile) -> dict[str, Any]:
    identity = media.identity
    return {
        "path": str(media.path),
        "format": media.format,
        "size_bytes": media.size_bytes,
        "duration_seconds": media.duration_seconds,
        "identity": (
            {
                "device": identity.device,
                "inode": identity.inode,
                "size_bytes": identity.size_bytes,
                "mtime_ns": identity.mtime_ns,
                "ctime_ns": identity.ctime_ns,
            }
            if identity is not None
            else None
        ),
    }


def _media_from_json(value: dict[str, Any]) -> MediaFile:
    try:
        identity_value = value.get("identity")
        identity = (
            MediaIdentity(
                device=int(identity_value["device"]),
                inode=int(identity_value["inode"]),
                size_bytes=int(identity_value["size_bytes"]),
                mtime_ns=int(identity_value["mtime_ns"]),
                ctime_ns=int(identity_value["ctime_ns"]),
            )
            if isinstance(identity_value, dict)
            else None
        )
        return MediaFile(
            path=Path(value["path"]),
            format=str(value["format"]),
            size_bytes=int(value["size_bytes"]),
            duration_seconds=float(value["duration_seconds"]),
            identity=identity,
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ProcessingWorkerError() from None


def _raise_worker_error(value: Any) -> None:
    if not isinstance(value, dict):
        raise ProcessingWorkerError()
    name = value.get("type")
    code = value.get("code")
    message = value.get("message")
    if not isinstance(message, str) or len(message) > 1000:
        raise ProcessingWorkerError()
    if name == "ResourceLimitError" and isinstance(code, str):
        raise ResourceLimitError(code, message)
    if name == "DecoderUnavailableError":
        raise DecoderUnavailableError()
    if name == "MediaInvalidError" and isinstance(code, str):
        raise MediaInvalidError(code, message)
    if name == "DownloadError" and isinstance(code, str):
        raise DownloadError(code, message)
    if name == "ASRUnavailableError":
        raise ASRUnavailableError(message)
    raise ProcessingWorkerError()
