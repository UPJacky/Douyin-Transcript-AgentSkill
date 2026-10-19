"""Client orchestration for an authenticated capture-service transport.

This module is transport-neutral and does not claim process isolation. A Windows
named-pipe adapter is available separately, but is not selected by default
because this repository has no installed service/worker package. Every injected
transport must authenticate the peer, bind the result frame and media stream to
the same request, and interrupt reads when the deadline or cancellation fires.
"""

from __future__ import annotations

import math
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

from .capture_artifacts import CaptureArtifactError, receive_capture_artifact
from .capture_ipc import (
    DEFAULT_LIMITS,
    CaptureFailureCode,
    CaptureIpcProtocolError,
    CaptureLimits,
    CaptureRequest,
    CaptureResolveFailure,
    CaptureResolveRequest,
    CaptureResolveSuccess,
    CaptureResultFailure,
    CaptureResultSuccess,
    CaptureVideoMetadata,
    decode_capture_resolve_result,
    decode_capture_result,
    encode_capture_request,
    encode_capture_resolve_request,
)

DEFAULT_CAPTURE_TIMEOUT_SECONDS = 180.0
MAX_CAPTURE_TIMEOUT_SECONDS = 15 * 60


class CaptureClientError(RuntimeError):
    """A safe, detail-free failure from capture-service client orchestration."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(message)


class CaptureExchange(Protocol):
    """One authenticated request/result/artifact exchange owned by a transport."""

    result_frame: bytes
    media_stream: BinaryIO | None

    def close(self) -> None:
        """Close all handles associated with this exchange."""


class CaptureTransport(Protocol):
    """Transport contract; implementations must be supplied by a trusted host.

    A production implementation must authenticate the caller and service,
    enforce exclusive access to its endpoint, bind both outputs to the exact
    request, and interrupt blocked I/O on deadline/cancellation. A plain local
    socket, caller-controlled endpoint, or unauthenticated named pipe is not a
    valid implementation.
    """

    def exchange(
        self,
        request_frame: bytes,
        *,
        deadline_monotonic: float,
        is_cancelled: Callable[[], bool] | None,
    ) -> CaptureExchange:
        """Submit one bounded request and return its bound result/artifact pair."""


@dataclass(frozen=True, slots=True)
class CapturedMedia:
    """Validated protocol metadata and the locally received private media file."""

    video: CaptureVideoMetadata
    path: Path
    size_bytes: int
    sha256: str
    media_type: str
    duration_seconds: float


class CaptureServiceClient:
    """Submit an original URL and receive only safe metadata plus media bytes."""

    def __init__(
        self,
        transport: CaptureTransport,
        cache_dir: str | os.PathLike[str],
        *,
        timeout_seconds: float = DEFAULT_CAPTURE_TIMEOUT_SECONDS,
    ) -> None:
        if not callable(getattr(transport, "exchange", None)):
            raise TypeError("transport must provide exchange()")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or (isinstance(timeout_seconds, float) and not math.isfinite(timeout_seconds))
            or not 0 < timeout_seconds <= MAX_CAPTURE_TIMEOUT_SECONDS
        ):
            raise ValueError(f"timeout_seconds must be between 0 and {MAX_CAPTURE_TIMEOUT_SECONDS}")
        self._transport = transport
        self._cache_dir = Path(cache_dir)
        self._timeout_seconds = float(timeout_seconds)

    def resolve_source(
        self,
        original_url: str,
        *,
        max_short_link_redirects: int = 5,
        deadline_monotonic: float | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> str:
        """Resolve a source URL to a stable video ID without returning redirects.

        This separate cheap operation lets the task store deduplicate and check
        its cache before the worker performs a full media capture.
        """
        request = CaptureResolveRequest.create(
            original_url, max_short_link_redirects=max_short_link_redirects
        )
        try:
            request_frame = encode_capture_resolve_request(request)
        except CaptureIpcProtocolError as exc:
            raise CaptureClientError("INVALID_URL", "抖音链接不符合隔离采集请求格式") from exc
        deadline = self._request_deadline(deadline_monotonic)
        self._raise_if_cancelled(is_cancelled)
        exchange: CaptureExchange | None = None
        try:
            exchange = self._transport.exchange(
                request_frame,
                deadline_monotonic=deadline,
                is_cancelled=is_cancelled,
            )
            result = decode_capture_resolve_result(exchange.result_frame, request)
            if exchange.media_stream is not None:
                raise CaptureClientError("INVALID_RESULT", "隔离服务在解析请求中返回了额外数据")
            if isinstance(result, CaptureResolveFailure):
                raise CaptureClientError(
                    result.code.value,
                    _failure_message(result.code),
                    retryable=result.retryable,
                )
            if not isinstance(result, CaptureResolveSuccess):
                raise CaptureClientError("INVALID_RESULT", "隔离服务返回了无效结果")
            return result.video_id
        except CaptureClientError:
            raise
        except CaptureIpcProtocolError as exc:
            raise CaptureClientError("INVALID_RESULT", "隔离服务返回了无效结果") from exc
        except InterruptedError:
            raise CaptureClientError("CANCELLED", "隔离采集已取消") from None
        except TimeoutError:
            raise CaptureClientError(
                "CAPTURE_TIMEOUT", "隔离采集超过时限", retryable=True
            ) from None
        except Exception as exc:
            raise CaptureClientError(
                "CAPTURE_TRANSPORT_FAILED",
                f"隔离采集服务不可用（{type(exc).__name__}）",
                retryable=True,
            ) from None
        finally:
            if exchange is not None:
                try:
                    exchange.close()
                except Exception:
                    raise CaptureClientError(
                        "CAPTURE_TRANSPORT_CLOSE_FAILED", "隔离采集通道无法安全关闭"
                    ) from None

    def capture(
        self,
        original_url: str,
        *,
        limits: CaptureLimits = DEFAULT_LIMITS,
        deadline_monotonic: float | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> CapturedMedia:
        """Run a full worker-owned capture and securely receive its artifact.

        ``original_url`` is placed only in the bounded request frame. It is not
        copied to the returned object or any local file name. No URL candidate,
        browser identity, service path, or proxy endpoint is returned.
        """
        request = CaptureRequest.create(original_url, limits)
        try:
            request_frame = encode_capture_request(request)
        except CaptureIpcProtocolError as exc:
            raise CaptureClientError("INVALID_URL", "抖音链接不符合隔离采集请求格式") from exc

        deadline = self._request_deadline(deadline_monotonic)
        self._raise_if_cancelled(is_cancelled)

        exchange: CaptureExchange | None = None
        media_path: Path | None = None
        try:
            exchange = self._transport.exchange(
                request_frame,
                deadline_monotonic=float(deadline),
                is_cancelled=is_cancelled,
            )
            result = decode_capture_result(exchange.result_frame, request)
            if isinstance(result, CaptureResultFailure):
                message = _failure_message(result.code)
                raise CaptureClientError(result.code.value, message, retryable=result.retryable)
            if not isinstance(result, CaptureResultSuccess):
                raise CaptureClientError("INVALID_RESULT", "隔离服务返回了无效结果")
            if exchange.media_stream is None:
                raise CaptureClientError("ARTIFACT_MISSING", "隔离服务未交付媒体文件")
            media_path = receive_capture_artifact(
                result,
                request,
                exchange.media_stream,
                self._cache_dir,
                deadline_monotonic=float(deadline),
                is_cancelled=is_cancelled,
            )
            artifact = result.media_artifact
            captured = CapturedMedia(
                video=result.video,
                path=media_path,
                size_bytes=artifact.size_bytes,
                sha256=artifact.sha256,
                media_type=artifact.media_type,
                duration_seconds=artifact.duration_seconds,
            )
        except CaptureClientError:
            raise
        except CaptureArtifactError as exc:
            raise CaptureClientError(
                exc.code,
                str(exc),
                retryable=exc.code in {"TIMEOUT", "STREAM_READ_FAILED"},
            ) from None
        except CaptureIpcProtocolError as exc:
            raise CaptureClientError("INVALID_RESULT", "隔离服务返回了无效结果") from exc
        except InterruptedError:
            raise CaptureClientError("CANCELLED", "隔离采集已取消") from None
        except TimeoutError:
            raise CaptureClientError(
                "CAPTURE_TIMEOUT", "隔离采集超过时限", retryable=True
            ) from None
        except Exception as exc:
            # Do not echo implementation exception text; transports can contain
            # endpoint, path, URL, or OS detail that is not safe for the CLI.
            raise CaptureClientError(
                "CAPTURE_TRANSPORT_FAILED",
                f"隔离采集服务不可用（{type(exc).__name__}）",
                retryable=True,
            ) from None
        finally:
            if exchange is not None:
                try:
                    exchange.close()
                except Exception:
                    if media_path is not None:
                        try:
                            media_path.unlink(missing_ok=True)
                        except OSError:
                            pass
                    raise CaptureClientError(
                        "CAPTURE_TRANSPORT_CLOSE_FAILED", "隔离采集通道无法安全关闭"
                    ) from None

        return captured

    def _request_deadline(self, deadline_monotonic: float | None) -> float:
        now = time.monotonic()
        client_deadline = now + self._timeout_seconds
        deadline = client_deadline if deadline_monotonic is None else deadline_monotonic
        if (
            isinstance(deadline, bool)
            or not isinstance(deadline, (int, float))
            or (isinstance(deadline, float) and not math.isfinite(deadline))
            or deadline <= now
        ):
            raise CaptureClientError("CAPTURE_TIMEOUT", "隔离采集请求已超过时限", retryable=True)
        return float(min(deadline, client_deadline))

    @staticmethod
    def _raise_if_cancelled(is_cancelled: Callable[[], bool] | None) -> None:
        if is_cancelled is None:
            return
        try:
            cancelled = bool(is_cancelled())
        except Exception:
            cancelled = True
        if cancelled:
            raise CaptureClientError("CANCELLED", "隔离采集已取消")


def _failure_message(code: CaptureFailureCode) -> str:
    messages = {
        CaptureFailureCode.INVALID_URL: "抖音链接格式无效",
        CaptureFailureCode.UNSUPPORTED_URL: "当前隔离服务不支持此抖音链接",
        CaptureFailureCode.NETWORK_ERROR: "隔离采集网络请求失败",
        CaptureFailureCode.BROWSER_ISOLATION_UNAVAILABLE: "系统浏览器隔离服务不可用",
        CaptureFailureCode.BROWSER_ISOLATION_LOST: "浏览器隔离租约已失效",
        CaptureFailureCode.LOGIN_REQUIRED: "抖音要求登录后才能采集",
        CaptureFailureCode.CAPTURE_NO_MEDIA: "页面中没有可用媒体",
        CaptureFailureCode.CAPTURE_TIMEOUT: "隔离采集超过时限",
        CaptureFailureCode.DOWNLOAD_FAILED: "隔离服务下载媒体失败",
        CaptureFailureCode.MEDIA_INVALID: "隔离服务返回的媒体无效",
        CaptureFailureCode.RESOURCE_LIMIT: "媒体超过采集资源限制",
        CaptureFailureCode.SERVICE_BUSY: "隔离采集服务正忙",
        CaptureFailureCode.CANCELLED: "隔离采集已取消",
        CaptureFailureCode.INTERNAL_ERROR: "隔离采集服务发生内部错误",
    }
    return messages[code]
