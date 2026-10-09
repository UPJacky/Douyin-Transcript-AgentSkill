"""Safe, bounded, atomic media downloads with optional decoder validation."""

from __future__ import annotations

import hashlib
import math
import os
import re
import stat
import threading
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from .capture import MediaCandidate
from .limits import (
    DEFAULT_MAX_MEDIA_DURATION_SECONDS,
    DEFAULT_MAX_OUTPUT_CHARACTERS,
    DEFAULT_MAX_OUTPUT_SEGMENTS,
    HARD_MAX_MEDIA_DURATION_SECONDS,
    ResourceLimitError,
    require_media_duration,
    validate_resource_limits,
)
from .storage_security import PrivateStorageError, ensure_private_directory
from .urls import (
    DOUYIN_SHORT_HOSTS,
    DOUYIN_WEB_HOSTS,
    MEDIA_HOST_SUFFIXES,
    UnsupportedUrlError,
    open_pinned_https,
    validate_https_url,
)

DEFAULT_MAX_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_REDIRECTS = 3
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
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_RETRY_STATUSES = frozenset({429, 503})
_SAFE_ERROR_CODE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_MAX_FAILURE_DETAILS = 8


class DownloadError(RuntimeError):
    """A user-safe downloader failure with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DownloadCancellation:
    """Cancel a download promptly, including its retry wait and active socket."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._closers: dict[int, Callable[[], None]] = {}

    def is_set(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._event.wait(timeout)

    def register(self, closer: Callable[[], None]) -> Callable[[], None]:
        key = id(closer)
        with self._lock:
            if not self._event.is_set():
                self._closers[key] = closer
                registered = True
            else:
                registered = False
        if not registered:
            _close_quietly(closer)

        def unregister() -> None:
            with self._lock:
                self._closers.pop(key, None)

        return unregister

    def linked_child(self) -> DownloadCancellation:
        """Create a task-scoped cancellation linked to this parent signal."""
        child = DownloadCancellation()
        unregister_parent = self.register(child.cancel)
        child.register(unregister_parent)
        return child

    def cancel(self) -> None:
        self._event.set()
        with self._lock:
            closers = list(self._closers.values())
            self._closers.clear()
        for closer in closers:
            _close_quietly(closer)


def _close_quietly(closer: Callable[[], None]) -> None:
    try:
        closer()
    except Exception:
        pass


def _raise_if_cancelled(cancellation: DownloadCancellation | None) -> None:
    if cancellation is not None and cancellation.is_set():
        raise DownloadError("CANCELLED", "媒体下载已取消")


class DecoderUnavailableError(DownloadError):
    def __init__(self) -> None:
        super().__init__("DECODER_UNAVAILABLE", "需要安装 PyAV 或 FFprobe 才能验证媒体文件")


class MediaInvalidError(DownloadError):
    """Raised when a local or downloaded file is not usable speech media."""


@dataclass(frozen=True, slots=True)
class MediaFile:
    path: Path
    format: str
    size_bytes: int
    duration_seconds: float
    identity: MediaIdentity | None = None


@dataclass(frozen=True, slots=True)
class MediaIdentity:
    """Identity of the file descriptor whose contents passed media validation."""

    device: int
    inode: int
    size_bytes: int
    mtime_ns: int
    ctime_ns: int

    @classmethod
    def from_stat(cls, info: os.stat_result) -> MediaIdentity:
        return cls(
            info.st_dev,
            info.st_ino,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )


def validate_media_file(
    path: str | Path,
    *,
    max_duration_seconds: float = DEFAULT_MAX_MEDIA_DURATION_SECONDS,
) -> MediaFile:
    """Validate an existing media file before the pipeline loads its ASR model.

    The decoder is imported lazily. A valid file must be a non-empty regular
    file with a decodable audio frame and positive duration.
    """
    max_duration_seconds, _, _ = validate_resource_limits(
        max_duration_seconds,
        DEFAULT_MAX_OUTPUT_SEGMENTS,
        DEFAULT_MAX_OUTPUT_CHARACTERS,
    )
    media_path = Path(path).expanduser()
    try:
        if not media_path.is_file():
            raise MediaInvalidError("MEDIA_NOT_FOUND", "媒体文件不存在或不是普通文件")
        size = media_path.stat().st_size
    except OSError:
        raise MediaInvalidError("MEDIA_UNREADABLE", "媒体文件无法读取") from None
    if size <= 0:
        raise MediaInvalidError("EMPTY_MEDIA", "媒体文件为空")
    try:
        validation = _coerce_validation(
            _validate_with_pyav(
                media_path, max_duration_seconds=max_duration_seconds
            )
        )
    except DecoderUnavailableError:
        raise
    except MediaInvalidError:
        raise
    except DownloadError as exc:
        raise MediaInvalidError(exc.code, str(exc)) from None
    except OSError:
        raise MediaInvalidError("MEDIA_UNREADABLE", "媒体文件无法读取") from None
    if validation.identity is not None:
        size = validation.identity.size_bytes
    return MediaFile(
        media_path,
        validation.format,
        size,
        validation.duration_seconds,
        validation.identity,
    )


@dataclass(frozen=True, slots=True)
class _Validation:
    format: str
    duration_seconds: float
    identity: MediaIdentity | None = None


def download_media(
    video_id: str,
    candidates: Iterable[MediaCandidate],
    cache_dir: str | Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_duration_seconds: float = DEFAULT_MAX_MEDIA_DURATION_SECONDS,
    connect_timeout: float = 10.0,
    read_timeout: float = 30.0,
    total_timeout: float = 300.0,
    absolute_deadline: float | None = None,
    expected_duration_seconds: float | None = None,
    retries: int = 2,
    backoff_base: float = 0.5,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    decoder: Callable[[Path], _Validation | MediaFile | tuple[str, float]] | None = None,
    requester: Callable[..., tuple[Any, Any]] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    cancellation: DownloadCancellation | None = None,
) -> MediaFile:
    """Download the first valid candidate, with audio prioritized over video.

    Media bytes are streamed to a unique ``.part`` file. The final cache name
    uses the video ID, media kind, and content hash; signed source URLs and
    request headers are never written to disk or included in errors. When an
    absolute processing deadline is supplied, it caps the downloader's own
    total timeout.
    """
    if not re.fullmatch(r"[0-9]{1,32}", video_id):
        raise DownloadError("INVALID_VIDEO_ID", "视频 ID 格式无效")
    if max_bytes <= 0 or retries < 0 or max_redirects < 0 or max_redirects > 5:
        raise ValueError("invalid download limits")
    max_duration_seconds, _, _ = validate_resource_limits(
        max_duration_seconds,
        DEFAULT_MAX_OUTPUT_SEGMENTS,
        DEFAULT_MAX_OUTPUT_CHARACTERS,
    )
    if expected_duration_seconds is not None:
        require_media_duration(expected_duration_seconds, max_duration_seconds)
    if min(connect_timeout, read_timeout, total_timeout) <= 0:
        raise ValueError("timeouts must be positive")
    items = sorted(list(candidates), key=lambda candidate: candidate.kind != "audio")
    if not items:
        raise DownloadError("NO_MEDIA_CANDIDATE", "没有可下载的媒体地址")
    cache = Path(cache_dir).expanduser()
    try:
        cache = ensure_private_directory(cache)
    except PrivateStorageError as exc:
        raise DownloadError("PRIVATE_STORAGE_UNSAFE", str(exc)) from None
    validate = decoder or (
        lambda path: _validate_with_pyav(
            path, max_duration_seconds=max_duration_seconds
        )
    )
    deadline = time.monotonic() + total_timeout
    if absolute_deadline is not None:
        deadline = min(deadline, absolute_deadline)
    failure_details: list[tuple[str, str]] = []

    for candidate in items:
        _raise_if_cancelled(cancellation)
        if candidate.kind not in {"audio", "video"}:
            continue
        _require_time_remaining(deadline)
        cached = _find_valid_cache(
            video_id,
            candidate.kind,
            cache,
            validate,
            max_bytes=max_bytes,
            deadline=deadline,
            expected_duration_seconds=expected_duration_seconds,
            cancellation=cancellation,
        )
        if cached is not None:
            require_media_duration(cached.duration_seconds, max_duration_seconds)
            return cached
        try:
            return _download_candidate(
                video_id,
                candidate,
                cache,
                max_bytes=max_bytes,
                max_duration_seconds=max_duration_seconds,
                expected_duration_seconds=expected_duration_seconds,
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
                deadline=deadline,
                retries=retries,
                backoff_base=backoff_base,
                max_redirects=max_redirects,
                decoder=validate,
                requester=requester or open_pinned_https,
                sleeper=sleeper,
                cancellation=cancellation,
            )
        except DecoderUnavailableError:
            raise
        except ResourceLimitError:
            raise
        except DownloadError as exc:
            if exc.code in {"TIMEOUT", "PROCESSING_TIMEOUT", "CANCELLED"}:
                raise
            detail = (
                candidate.kind,
                exc.code if _SAFE_ERROR_CODE.fullmatch(exc.code) else "OTHER",
            )
            if detail not in failure_details and len(failure_details) < _MAX_FAILURE_DETAILS:
                failure_details.append(detail)
            continue
    detail_text = "；候选错误：" + ", ".join(
        f"{kind}={code}" for kind, code in failure_details
    ) if failure_details else ""
    raise DownloadError(
        "ALL_MEDIA_CANDIDATES_FAILED",
        "所有音视频候选均下载或校验失败"
        + detail_text
        + "；可改用本地媒体文件",
    )


def _download_candidate(
    video_id: str,
    candidate: MediaCandidate,
    cache: Path,
    *,
    max_bytes: int,
    max_duration_seconds: float,
    expected_duration_seconds: float | None,
    connect_timeout: float,
    read_timeout: float,
    deadline: float,
    retries: int,
    backoff_base: float,
    max_redirects: int,
    decoder: Callable[[Path], _Validation | MediaFile | tuple[str, float]],
    requester: Callable[..., tuple[Any, Any]],
    sleeper: Callable[[float], None],
    cancellation: DownloadCancellation | None,
) -> MediaFile:
    part = cache / f".{video_id}-{candidate.kind}-{uuid.uuid4().hex}.part"
    try:
        for attempt in range(retries + 1):
            _raise_if_cancelled(cancellation)
            try:
                remaining = _require_time_remaining(deadline)
                response, connection = _get_candidate_response(
                    candidate,
                    requester=requester,
                    timeout=min(connect_timeout, remaining),
                    read_timeout=read_timeout,
                    max_redirects=max_redirects,
                    deadline=deadline,
                    cancellation=cancellation,
                )
                unregister = (
                    cancellation.register(
                        partial(_close_response_and_connection, response, connection)
                    )
                    if cancellation is not None
                    else lambda: None
                )
                try:
                    _raise_if_cancelled(cancellation)
                    if response.status in _RETRY_STATUSES and attempt < retries:
                        delay = _retry_after(response, backoff_base, attempt)
                        _wait_before_retry(
                            sleeper,
                            min(delay, _require_time_remaining(deadline)),
                            deadline=deadline,
                            cancellation=cancellation,
                        )
                        _require_time_remaining(deadline)
                        continue
                    if response.status != 200:
                        raise DownloadError("HTTP_STATUS", "媒体服务器返回了不可用状态")
                    mime = (
                        str(response.getheader("Content-Type", "")).split(";", 1)[0].strip().lower()
                    )
                    if mime in {
                        "text/html",
                        "application/xhtml+xml",
                        "application/json",
                        "text/plain",
                    }:
                        raise DownloadError("NOT_MEDIA", "服务器返回的内容不是媒体文件")
                    length = response.getheader("Content-Length")
                    if length:
                        try:
                            if int(length) > max_bytes:
                                raise DownloadError("TOO_LARGE", "媒体文件超过大小上限")
                        except ValueError:
                            pass
                    digest = hashlib.sha256()
                    total = 0
                    first = bytearray()
                    with part.open("wb") as stream:
                        while True:
                            remaining = _require_time_remaining(deadline)
                            deadline_limited_read = remaining <= read_timeout
                            try:
                                if connection.sock is not None:
                                    connection.sock.settimeout(min(read_timeout, remaining))
                            except (AttributeError, OSError):
                                pass
                            try:
                                _raise_if_cancelled(cancellation)
                                # read1 performs at most one underlying socket
                                # read so the next loop can enforce the deadline.
                                read_once = getattr(response, "read1", response.read)
                                chunk = read_once(64 * 1024)
                            except Exception as exc:
                                if time.monotonic() >= deadline or (
                                    deadline_limited_read and isinstance(exc, TimeoutError)
                                ):
                                    raise DownloadError(
                                        "TIMEOUT", "媒体下载超过总时限"
                                    ) from None
                                raise DownloadError(
                                    "READ_FAILED", f"读取媒体失败（{type(exc).__name__}）"
                                ) from None
                            _require_time_remaining(deadline)
                            if not chunk:
                                break
                            if len(first) < 512:
                                first.extend(chunk[: 512 - len(first)])
                            total += len(chunk)
                            if total > max_bytes:
                                raise DownloadError("TOO_LARGE", "媒体文件超过大小上限")
                            stream.write(chunk)
                            digest.update(chunk)
                        stream.flush()
                        os.fsync(stream.fileno())
                    if total == 0:
                        raise DownloadError("EMPTY_MEDIA", "服务器返回了空文件")
                    if _looks_like_html(bytes(first)):
                        raise DownloadError("NOT_MEDIA", "服务器返回的内容不是媒体文件")
                    try:
                        validation = decoder(part)
                    except DecoderUnavailableError:
                        raise
                    except ResourceLimitError:
                        raise
                    except DownloadError:
                        raise
                    except Exception as exc:
                        raise DownloadError(
                            "MEDIA_DECODE_FAILED", f"媒体解码校验失败（{type(exc).__name__}）"
                        ) from None
                    checked = _coerce_validation(validation)
                    _raise_if_cancelled(cancellation)
                    require_media_duration(checked.duration_seconds, max_duration_seconds)
                    require_expected_media_duration(
                        checked.duration_seconds, expected_duration_seconds
                    )
                    _require_time_remaining(deadline)
                    suffix = _MEDIA_EXTENSIONS.get(mime, ".media")
                    final = cache / f"{video_id}-{candidate.kind}-{digest.hexdigest()[:16]}{suffix}"
                    part.replace(final)
                    try:
                        _require_time_remaining(deadline)
                    except DownloadError:
                        final.unlink(missing_ok=True)
                        raise
                    return MediaFile(
                        final,
                        checked.format,
                        total,
                        checked.duration_seconds,
                        checked.identity,
                    )
                finally:
                    _close_response_and_connection(response, connection)
                    unregister()
            except (DownloadError, ResourceLimitError):
                part.unlink(missing_ok=True)
                _raise_if_cancelled(cancellation)
                raise
            except Exception as exc:
                part.unlink(missing_ok=True)
                _raise_if_cancelled(cancellation)
                if attempt < retries:
                    delay = max(backoff_base, 0.0) * (2**attempt)
                    _wait_before_retry(
                        sleeper,
                        min(delay, _require_time_remaining(deadline)),
                        deadline=deadline,
                        cancellation=cancellation,
                    )
                    _require_time_remaining(deadline)
                    continue
                raise DownloadError(
                    "NETWORK_FAILED", f"媒体网络请求失败（{type(exc).__name__}）"
                ) from None
        raise DownloadError("NETWORK_FAILED", "媒体下载重试次数已用完")
    finally:
        part.unlink(missing_ok=True)


def _get_candidate_response(
    candidate: MediaCandidate,
    *,
    requester: Callable[..., tuple[Any, Any]],
    timeout: float,
    read_timeout: float,
    max_redirects: int,
    deadline: float | None = None,
    cancellation: DownloadCancellation | None = None,
) -> tuple[Any, Any]:
    current = candidate.url
    seen = {current}
    allowed = DOUYIN_WEB_HOSTS | DOUYIN_SHORT_HOSTS
    headers = _safe_request_headers(candidate.headers)
    for hop in range(max_redirects + 1):
        connection = None
        response = None
        try:
            _raise_if_cancelled(cancellation)
            remaining = _require_time_remaining(deadline)
            validate_https_url(
                current,
                allowed_hosts=allowed,
                allowed_suffixes=MEDIA_HOST_SUFFIXES,
                resolve_dns=False,
            )
            request_options = {
                "allowed_hosts": allowed,
                "allowed_suffixes": MEDIA_HOST_SUFFIXES,
                "method": "GET",
                "headers": headers,
                "timeout": min(timeout, remaining),
            }
            if requester is open_pinned_https and deadline is not None:
                request_options["deadline"] = deadline
            if requester is open_pinned_https and cancellation is not None:
                request_options["cancellation"] = cancellation
            connection, response = requester(current, **request_options)
            _raise_if_cancelled(cancellation)
            if deadline is not None and time.monotonic() >= deadline:
                response.close()
                connection.close()
                raise DownloadError("TIMEOUT", "媒体下载超过总时限")
        except UnsupportedUrlError as exc:
            raise DownloadError(exc.code, str(exc)) from None
        except DownloadError:
            _close_response_and_connection(response, connection)
            raise
        except Exception as exc:
            if cancellation is not None and cancellation.is_set():
                _close_response_and_connection(response, connection)
                _raise_if_cancelled(cancellation)
            if deadline is not None and time.monotonic() >= deadline:
                raise DownloadError("TIMEOUT", "媒体下载超过总时限") from None
            raise DownloadError(
                "NETWORK_FAILED", f"媒体网络请求失败（{type(exc).__name__}）"
            ) from None
        if response.status not in _REDIRECT_STATUSES:
            # Per-read timeout is set on the live connection before body access.
            try:
                connection.sock.settimeout(read_timeout)
            except (AttributeError, OSError):
                pass
            return response, connection
        location = response.getheader("Location")
        response.close()
        connection.close()
        if not location:
            raise DownloadError("BAD_REDIRECT", "媒体服务器返回了无效跳转")
        target = urljoin(current, location)
        if target in seen:
            raise DownloadError("REDIRECT_LOOP", "媒体地址发生跳转环")
        seen.add(target)
        if hop == max_redirects:
            raise DownloadError("TOO_MANY_REDIRECTS", "媒体地址跳转次数超过限制")
        current = target
        _require_time_remaining(deadline)
    raise DownloadError("TOO_MANY_REDIRECTS", "媒体地址跳转次数超过限制")


def _require_time_remaining(deadline: float | None) -> float:
    if deadline is None:
        return float("inf")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise DownloadError("TIMEOUT", "媒体下载超过总时限")
    return remaining


def _wait_before_retry(
    sleeper: Callable[[float], None],
    delay: float,
    *,
    deadline: float,
    cancellation: DownloadCancellation | None,
) -> None:
    _raise_if_cancelled(cancellation)
    if cancellation is None:
        sleeper(delay)
    else:
        cancellation.wait(delay)
    _raise_if_cancelled(cancellation)
    _require_time_remaining(deadline)


def _close_response_and_connection(response: Any, connection: Any) -> None:
    for resource in (response, connection):
        if resource is None:
            continue
        try:
            resource.close()
        except Exception:
            pass


def require_expected_media_duration(
    actual_duration_seconds: float | None,
    expected_duration_seconds: float | None,
) -> None:
    """Reject a decoded candidate that is materially shorter than page metadata."""
    if expected_duration_seconds is None:
        return
    actual_valid = isinstance(actual_duration_seconds, (int, float)) and not isinstance(
        actual_duration_seconds, bool
    )
    expected_valid = isinstance(expected_duration_seconds, (int, float)) and not isinstance(
        expected_duration_seconds, bool
    )
    if not actual_valid or not expected_valid:
        raise DownloadError("MEDIA_INCOMPLETE", "无法核对候选媒体与页面声明时长")
    try:
        actual_duration = float(actual_duration_seconds)
        expected_duration = float(expected_duration_seconds)
    except OverflowError:
        raise DownloadError("MEDIA_INCOMPLETE", "无法核对候选媒体与页面声明时长") from None
    if (
        not math.isfinite(actual_duration)
        or not math.isfinite(expected_duration)
        or actual_duration <= 0
        or expected_duration <= 0
    ):
        raise DownloadError("MEDIA_INCOMPLETE", "无法核对候选媒体与页面声明时长")
    tolerance = max(0.25, min(5.0, expected_duration * 0.01))
    if actual_duration + tolerance < expected_duration:
        raise DownloadError("MEDIA_INCOMPLETE", "候选媒体时长明显短于页面声明时长")


def _safe_request_headers(headers: dict[str, str]) -> dict[str, str]:
    safe: dict[str, str] = {"User-Agent": "douyin-transcript/0.1"}
    allowed = {"user-agent": "User-Agent", "accept": "Accept", "referer": "Referer"}
    for name, value in headers.items():
        target = allowed.get(name.lower())
        if (
            target
            and isinstance(value, str)
            and len(value) <= 1024
            and "\r" not in value
            and "\n" not in value
        ):
            safe[target] = value
    return safe


def _retry_after(response: Any, base: float, attempt: int) -> float:
    # Ignore arbitrary server-provided delays; a bounded exponential backoff is
    # deterministic and cannot cause the client to wait indefinitely.
    return min(max(base, 0.0) * (2**attempt), 8.0)


def _looks_like_html(data: bytes) -> bool:
    prefix = data.lstrip().lower()[:128]
    return prefix.startswith((b"<!doctype html", b"<html", b"<head", b"<body"))


def _coerce_validation(value: _Validation | MediaFile | tuple[str, float]) -> _Validation:
    if isinstance(value, _Validation):
        result = value
    elif isinstance(value, MediaFile):
        result = _Validation(value.format, value.duration_seconds, value.identity)
    else:
        result = _Validation(str(value[0]), float(value[1]))
    if (
        not result.format
        or isinstance(result.duration_seconds, bool)
        or not isinstance(result.duration_seconds, (int, float))
        or not math.isfinite(result.duration_seconds)
        or result.duration_seconds <= 0
    ):
        raise DownloadError("INVALID_MEDIA", "媒体格式或时长无效")
    return result


def _validate_with_pyav(
    path: Path,
    *,
    max_duration_seconds: float = HARD_MAX_MEDIA_DURATION_SECONDS,
) -> _Validation:
    try:
        import av
    except ImportError:
        raise DecoderUnavailableError() from None
    try:
        with path.open("rb") as source:
            before = MediaIdentity.from_stat(os.fstat(source.fileno()))
            source_info = os.fstat(source.fileno())
            if not stat.S_ISREG(source_info.st_mode):
                raise MediaInvalidError("MEDIA_NOT_FOUND", "媒体文件不存在或不是普通文件")
            if before.size_bytes <= 0:
                raise MediaInvalidError("EMPTY_MEDIA", "媒体文件为空")
            with av.open(
                _NonClosingFile(source),
                mode="r",
                io_open=_deny_nested_media_io,
            ) as container:
                result = _validate_open_container(
                    av,
                    container,
                    max_duration_seconds=max_duration_seconds,
                )
            after = MediaIdentity.from_stat(os.fstat(source.fileno()))
            if after != before:
                raise MediaInvalidError("MEDIA_CHANGED", "媒体在解码校验期间发生了变化")
            return _Validation(result.format, result.duration_seconds, before)
    except ResourceLimitError:
        raise
    except DownloadError:
        raise
    except Exception as exc:
        raise MediaInvalidError(
            "MEDIA_DECODE_FAILED", f"媒体解码校验失败（{type(exc).__name__}）"
        ) from None


class _NonClosingFile:
    """Let PyAV use an open descriptor without closing its owner's handle."""

    def __init__(self, stream: Any) -> None:
        self._stream = stream

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)

    def close(self) -> None:
        return None


def _deny_nested_media_io(_url: str, _flags: int, _options: dict[str, str]) -> Any:
    """Prevent demuxers from opening playlist segments or other secondary URLs."""
    raise OSError("opening additional media resources is disabled")


def _validate_open_container(
    av: Any,
    container: Any,
    *,
    max_duration_seconds: float,
) -> _Validation:
    audio_streams = [stream for stream in container.streams if stream.type == "audio"]
    if not audio_streams:
        raise MediaInvalidError("NO_AUDIO_TRACK", "媒体文件中没有音轨")
    stream = audio_streams[0]
    declared_durations: list[float] = []
    if container.duration is not None:
        declared_durations.append(float(container.duration) / 1_000_000)
    if stream.duration is not None and stream.time_base is not None:
        declared_durations.append(float(stream.duration * stream.time_base))
    for declared_duration in declared_durations:
        if math.isfinite(declared_duration) and declared_duration > 0:
            require_media_duration(declared_duration, max_duration_seconds)

    observed_samples_seconds = 0.0
    first_frame_time: float | None = None
    last_frame_end: float | None = None
    frame_count = 0
    decoded_frames = iter(container.decode(stream))
    while True:
        try:
            frame = next(decoded_frames)
        except StopIteration:
            break
        except av.error.InvalidDataError:
            # Match faster-whisper's decoder: recoverable corrupt packets do
            # not make later valid audio unreachable.
            continue
        frame_count += 1
        samples = getattr(frame, "samples", None)
        sample_rate = getattr(frame, "sample_rate", None)
        if (
            isinstance(samples, bool)
            or not isinstance(samples, int)
            or samples <= 0
            or isinstance(sample_rate, bool)
            or not isinstance(sample_rate, int)
            or sample_rate <= 0
        ):
            require_media_duration(None, max_duration_seconds)
        frame_duration = samples / sample_rate
        observed_samples_seconds += frame_duration

        frame_pts = getattr(frame, "pts", None)
        frame_time_base = getattr(frame, "time_base", None) or stream.time_base
        if frame_pts is not None and frame_time_base is not None:
            try:
                frame_start = float(frame_pts * frame_time_base)
            except (OverflowError, TypeError, ValueError):
                frame_start = math.nan
            if not math.isfinite(frame_start):
                require_media_duration(None, max_duration_seconds)
            first_frame_time = (
                frame_start
                if first_frame_time is None
                else min(first_frame_time, frame_start)
            )
            frame_end = frame_start + frame_duration
            last_frame_end = (
                frame_end
                if last_frame_end is None
                else max(last_frame_end, frame_end)
            )

        observed_duration = observed_samples_seconds
        if first_frame_time is not None and last_frame_end is not None:
            observed_duration = max(observed_duration, last_frame_end - first_frame_time)
        require_media_duration(observed_duration, max_duration_seconds)

    if frame_count == 0:
        raise MediaInvalidError("NO_DECODABLE_AUDIO", "媒体音轨无法解码")
    duration = observed_samples_seconds
    if first_frame_time is not None and last_frame_end is not None:
        duration = max(duration, last_frame_end - first_frame_time)
    duration = max(
        [duration]
        + [value for value in declared_durations if math.isfinite(value) and value > 0]
    )
    require_media_duration(duration, max_duration_seconds)
    return _Validation(container.format.name, duration)


def _find_valid_cache(
    video_id: str,
    kind: str,
    cache: Path,
    decoder: Callable[[Path], _Validation | MediaFile | tuple[str, float]],
    *,
    max_bytes: int,
    deadline: float,
    expected_duration_seconds: float | None,
    cancellation: DownloadCancellation | None = None,
) -> MediaFile | None:
    for path in sorted(cache.glob(f"{video_id}-{kind}-*")):
        _raise_if_cancelled(cancellation)
        _require_time_remaining(deadline)
        if path.suffix == ".part":
            continue
        try:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                continue
            size = info.st_size
            if size <= 0 or size > max_bytes:
                continue
            validation = _coerce_validation(decoder(path))
            _raise_if_cancelled(cancellation)
            _require_time_remaining(deadline)
            require_expected_media_duration(
                validation.duration_seconds, expected_duration_seconds
            )
            return MediaFile(
                path,
                validation.format,
                size,
                validation.duration_seconds,
                validation.identity,
            )
        except DecoderUnavailableError:
            raise
        except ResourceLimitError:
            raise
        except DownloadError as exc:
            if exc.code in {"TIMEOUT", "PROCESSING_TIMEOUT", "CANCELLED"}:
                raise
            continue
        except Exception:
            continue
    return None
