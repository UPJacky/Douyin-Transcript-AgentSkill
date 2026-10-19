"""Receive service-owned media bytes without accepting a service filesystem path.

This module is the bounded file sink for an authenticated capture transport. It
does not authenticate a peer; callers must bind the result frame and stream to
one verified IPC exchange.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from .capture_ipc import (
    CaptureIpcProtocolError,
    CaptureRequest,
    CaptureResultSuccess,
    decode_capture_result,
    encode_capture_result,
)
from .markdown import _publish_no_replace
from .storage_security import PrivateStorageError, ensure_private_directory

MAX_CAPTURE_ARTIFACT_CHUNK_BYTES = 64 * 1024
_MEDIA_EXTENSIONS = {
    "audio/aac": ".aac",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/webm": ".webm",
    "audio/x-m4a": ".m4a",
    "audio/x-wav": ".wav",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    "video/x-matroska": ".mkv",
}


class CaptureArtifactError(RuntimeError):
    """A stable, detail-free failure while receiving a captured media artifact."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def receive_capture_artifact(
    result: CaptureResultSuccess,
    request: CaptureRequest,
    stream: BinaryIO,
    cache_dir: str | os.PathLike[str],
    *,
    deadline_monotonic: float | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> Path:
    """Copy exactly one request-bound artifact to a private, no-overwrite file.

    The authenticated transport must bind ``stream`` to the same request and
    artifact descriptor as ``result``, close its sending end after the declared
    byte count, and make reads interruptible by its deadline/cancel path. This
    function independently checks the request ID, requested limits, byte count,
    SHA-256, per-read chunk bound, and local storage before publishing.
    """
    if not callable(getattr(stream, "read", None)):
        raise CaptureArtifactError("INVALID_STREAM", "媒体传输流无效")
    try:
        decoded = decode_capture_result(encode_capture_result(result), request)
    except (CaptureIpcProtocolError, TypeError, ValueError):
        raise CaptureArtifactError("INVALID_DESCRIPTOR", "媒体 artifact 描述无效") from None
    if not isinstance(decoded, CaptureResultSuccess):
        raise CaptureArtifactError("INVALID_DESCRIPTOR", "媒体 artifact 描述无效")

    artifact = decoded.media_artifact
    extension = _MEDIA_EXTENSIONS.get(artifact.media_type)
    if extension is None:
        raise CaptureArtifactError("INVALID_DESCRIPTOR", "媒体类型不受支持")
    try:
        cache = ensure_private_directory(cache_dir)
    except (PrivateStorageError, OSError, ValueError):
        raise CaptureArtifactError("PRIVATE_STORAGE_UNSAFE", "媒体缓存目录权限不安全") from None

    final_path = cache / f"{artifact.artifact_id}{extension}"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{artifact.artifact_id}.",
            suffix=".part",
            dir=cache,
            delete=False,
        ) as destination:
            temporary_path = Path(destination.name)
            digest = hashlib.sha256()
            total = 0
            while total < artifact.size_bytes:
                _check_receive_state(deadline_monotonic, is_cancelled)
                requested_size = min(
                    MAX_CAPTURE_ARTIFACT_CHUNK_BYTES,
                    artifact.size_bytes - total,
                )
                try:
                    chunk = stream.read(requested_size)
                except Exception as exc:
                    if _is_cancelled(is_cancelled):
                        raise CaptureArtifactError("CANCELLED", "媒体接收已取消") from None
                    if _deadline_expired(deadline_monotonic):
                        raise CaptureArtifactError("TIMEOUT", "媒体接收超过时限") from None
                    raise CaptureArtifactError(
                        "STREAM_READ_FAILED", f"读取媒体流失败（{type(exc).__name__}）"
                    ) from None
                _check_receive_state(deadline_monotonic, is_cancelled)
                if not isinstance(chunk, bytes):
                    raise CaptureArtifactError("INVALID_STREAM", "媒体传输流无效")
                if not chunk:
                    raise CaptureArtifactError("MEDIA_LENGTH_MISMATCH", "媒体字节数与声明不符")
                if len(chunk) > requested_size or len(chunk) > MAX_CAPTURE_ARTIFACT_CHUNK_BYTES:
                    raise CaptureArtifactError("MEDIA_TOO_LARGE", "媒体文件超过大小上限")
                if destination.write(chunk) != len(chunk):
                    raise CaptureArtifactError("MEDIA_WRITE_FAILED", "写入媒体文件失败")
                digest.update(chunk)
                total += len(chunk)

            _check_receive_state(deadline_monotonic, is_cancelled)
            try:
                trailing = stream.read(1)
            except Exception as exc:
                if _is_cancelled(is_cancelled):
                    raise CaptureArtifactError("CANCELLED", "媒体接收已取消") from None
                if _deadline_expired(deadline_monotonic):
                    raise CaptureArtifactError("TIMEOUT", "媒体接收超过时限") from None
                raise CaptureArtifactError(
                    "STREAM_READ_FAILED", f"读取媒体流失败（{type(exc).__name__}）"
                ) from None
            _check_receive_state(deadline_monotonic, is_cancelled)
            if trailing != b"":
                raise CaptureArtifactError("MEDIA_TOO_LARGE", "媒体文件超过大小上限")
            if total != artifact.size_bytes:
                raise CaptureArtifactError("MEDIA_LENGTH_MISMATCH", "媒体字节数与声明不符")
            if not hmac.compare_digest(digest.hexdigest(), artifact.sha256):
                raise CaptureArtifactError("MEDIA_DIGEST_MISMATCH", "媒体摘要校验失败")
            destination.flush()
            os.fsync(destination.fileno())

        _check_receive_state(deadline_monotonic, is_cancelled)
        try:
            _publish_no_replace(temporary_path, final_path)
        except FileExistsError:
            raise CaptureArtifactError("ARTIFACT_COLLISION", "媒体 artifact 已存在") from None
        return final_path
    except CaptureArtifactError:
        raise
    except OSError as exc:
        raise CaptureArtifactError(
            "MEDIA_WRITE_FAILED", f"写入媒体文件失败（{type(exc).__name__}）"
        ) from None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _check_receive_state(
    deadline_monotonic: float | None,
    is_cancelled: Callable[[], bool] | None,
) -> None:
    if _is_cancelled(is_cancelled):
        raise CaptureArtifactError("CANCELLED", "媒体接收已取消")
    if _deadline_expired(deadline_monotonic):
        raise CaptureArtifactError("TIMEOUT", "媒体接收超过时限")


def _is_cancelled(is_cancelled: Callable[[], bool] | None) -> bool:
    try:
        return bool(is_cancelled()) if is_cancelled is not None else False
    except Exception:
        return True


def _deadline_expired(deadline_monotonic: float | None) -> bool:
    return deadline_monotonic is not None and time.monotonic() >= deadline_monotonic
