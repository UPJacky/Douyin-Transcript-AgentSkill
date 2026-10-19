"""Capture authorized Douyin media with the current user's local browser."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import math
import mimetypes
import os
import re
import stat
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from .capture import BrowserCapture, CaptureError
from .capture_client import (
    DEFAULT_CAPTURE_TIMEOUT_SECONDS,
    MAX_CAPTURE_TIMEOUT_SECONDS,
    CaptureClientError,
    CapturedMedia,
)
from .capture_ipc import (
    DEFAULT_LIMITS,
    MAX_MEDIA_BYTES,
    MAX_MEDIA_REDIRECTS,
    MAX_ORIGINAL_URL_UTF8_BYTES,
    MAX_SHORT_LINK_REDIRECTS,
    CaptureLimits,
    CaptureVideoMetadata,
)
from .downloader import DownloadCancellation, DownloadError, download_media
from .limits import ResourceLimitError, require_media_duration, validate_resource_limits
from .storage_security import (
    PrivateStorageError,
    _inspect_windows_handle,
    _windows_api,
    _windows_file_information,
    create_private_file,
    ensure_private_directory,
    inspect_private_path,
    open_private_regular_file,
)
from .urls import (
    SHORT_LINK_TOTAL_TIMEOUT_SECONDS,
    ResolvedInput,
    UnsupportedUrlError,
    _request_short_redirect,
    open_pinned_https,
    resolve_input,
)

_ERROR_MESSAGES = {
    "CAPTURE_BUSY": "此数据目录已有采集或登录操作占用；请等待当前操作完成后重试",
    "PLAYWRIGHT_MISSING": "浏览器抓取需要安装 Playwright 和 Chromium",
    "BROWSER_START_FAILED": "本地 Chromium 启动失败，请检查浏览器安装及资料目录",
    "LOGIN_REQUIRED": "页面要求登录；请在专用浏览器资料中登录后重试",
    "CAPTURE_NO_MEDIA": "页面没有提供可下载的音视频流",
    "CAPTURE_TIMEOUT": "本地采集超过时限",
    "TIMEOUT": "本地采集超过时限",
    "CANCELLED": "本地采集已取消",
    "TOO_LARGE": "媒体文件超过大小上限",
    "MEDIA_TOO_LONG": "媒体时长超过配置上限",
    "MEDIA_DURATION_UNKNOWN": "无法可靠确定媒体时长",
    "MEDIA_INCOMPLETE": "下载媒体时长与页面不符",
    "DECODER_UNAVAILABLE": "需要安装 PyAV 才能校验媒体",
    "PRIVATE_STORAGE_UNSAFE": "本地数据目录权限不安全或无法确认",
}
_CANDIDATE_ERROR_CODES = frozenset(
    {
        "UNSAFE_ADDRESS",
        "UNSAFE_HOST",
        "UNSAFE_URL",
        "DNS_FAILED",
        "HTTP_STATUS",
        "NETWORK_FAILED",
        "BAD_REDIRECT",
        "REDIRECT_LOOP",
        "TOO_MANY_REDIRECTS",
        "TOO_LARGE",
        "EMPTY_MEDIA",
        "NOT_MEDIA",
        "MEDIA_DECODE_FAILED",
        "INVALID_MEDIA",
        "MEDIA_INCOMPLETE",
        "OTHER",
    }
)


def _download_failure_message(error: DownloadError) -> str:
    # The downloader aggregates code pairs into a message. Extract only known
    # codes; never forward its free text, URL, headers, or unknown code values.
    reasons = []
    for kind, code in re.findall(r"\b(audio|video)=([A-Z][A-Z0-9_]{0,63})\b", str(error)):
        detail = f"{kind}={code}"
        if code in _CANDIDATE_ERROR_CODES and detail not in reasons:
            reasons.append(detail)
        if len(reasons) >= 8:
            break
    suffix = "（候选原因：" + "，".join(reasons) + "）" if reasons else ""
    return "所有音视频候选均下载或校验失败" + suffix


class _CallbackCancellation(DownloadCancellation):
    def __init__(self, callback: Callable[[], bool] | None) -> None:
        super().__init__()
        self._callback = callback

    def is_set(self) -> bool:
        if self._callback is not None:
            try:
                cancelled = bool(self._callback())
            except Exception:
                cancelled = True
            if cancelled:
                self.cancel()
        return super().is_set()

    def wait(self, timeout: float | None = None) -> bool:
        deadline = math.inf if timeout is None else time.monotonic() + max(0, timeout)
        while not self.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            super().wait(min(0.1, remaining))
        return True


class PersonalCaptureClient:
    """One local, serial capture at a time, with a dedicated persistent profile.

    Browser objects are created and closed in the calling capture thread.
    Cancellation is checked between browser operations and by the downloader;
    synchronous browser operations remain bounded by their Playwright timeouts.
    """

    def __init__(
        self,
        data_dir: str | Path,
        *,
        headless: bool = False,
        timeout_seconds: float = DEFAULT_CAPTURE_TIMEOUT_SECONDS,
    ) -> None:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= MAX_CAPTURE_TIMEOUT_SECONDS
        ):
            raise ValueError("timeout_seconds is outside the supported range")
        self._data_dir = Path(data_dir).expanduser()
        self._headless = headless
        self._timeout_seconds = float(timeout_seconds)
        self._lock = threading.Lock()

    def login(self, *, timeout_seconds: float = 300) -> None:
        """Open the dedicated profile for manual login until its window closes."""
        with self._operation():
            if (
                isinstance(timeout_seconds, bool)
                or not isinstance(timeout_seconds, (int, float))
                or not math.isfinite(timeout_seconds)
                or not 0 < timeout_seconds <= MAX_CAPTURE_TIMEOUT_SECONDS
            ):
                raise CaptureClientError("INVALID_LIMITS", "登录等待时限无效")
            deadline = time.monotonic() + timeout_seconds
            with BrowserCapture(
                self._data_dir / "browser-profile",
                personal=True,
                headless=False,
                launch_options={"timeout": min(30_000, timeout_seconds * 1000)},
            ) as browser:
                context = browser._require_context()
                closed = False

                def mark_closed(*_args: object) -> None:
                    nonlocal closed
                    closed = True

                context.on("close", mark_closed)
                try:
                    if time.monotonic() >= deadline:
                        raise TimeoutError
                    page = context.pages[0] if context.pages else context.new_page()
                    page.goto(
                        "https://www.douyin.com/",
                        wait_until="domcontentloaded",
                        timeout=min(30_000, max(1, (deadline - time.monotonic()) * 1000)),
                    )
                    if not closed:
                        if time.monotonic() >= deadline:
                            raise TimeoutError
                        context.wait_for_event(
                            "close", timeout=max(1, (deadline - time.monotonic()) * 1000)
                        )
                except Exception as exc:
                    if closed:
                        return
                    # Playwright's optional TimeoutError is not the builtin
                    # exception; inspect its type only, never its URL-bearing text.
                    if type(exc).__name__ == "TimeoutError" or time.monotonic() >= deadline:
                        raise CaptureClientError(
                            "LOGIN_TIMEOUT", "登录等待超时，已关闭专用浏览器；可重新运行 login"
                        ) from None
                    raise CaptureClientError("LOGIN_FAILED", "无法打开或等待登录浏览器") from None

    def resolve_source(
        self,
        original_url: str,
        *,
        max_short_link_redirects: int = MAX_SHORT_LINK_REDIRECTS,
        deadline_monotonic: float | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> str:
        with self._operation():
            deadline = self._deadline(deadline_monotonic)
            cancellation = _CallbackCancellation(is_cancelled)
            return self._resolve(
                original_url, max_short_link_redirects, deadline, cancellation
            ).video_id

    def capture(
        self,
        original_url: str,
        *,
        limits: CaptureLimits = DEFAULT_LIMITS,
        deadline_monotonic: float | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> CapturedMedia:
        with self._operation():
            self._validate_limits(limits)
            deadline = self._deadline(deadline_monotonic)
            cancellation = _CallbackCancellation(is_cancelled)
            item = self._resolve(
                original_url, limits.max_short_link_redirects, deadline, cancellation
            )
            timeout_ms = self._remaining_ms(deadline, cancellation)
            with BrowserCapture(
                self._data_dir / "browser-profile",
                personal=True,
                headless=self._headless,
                navigation_timeout_ms=min(30_000, timeout_ms),
                capture_timeout_ms=min(45_000, timeout_ms),
                launch_options={"timeout": min(30_000, timeout_ms)},
            ) as browser:
                # Startup consumes the same overall deadline as navigation/download.
                browser.capture_timeout_ms = min(
                    browser.capture_timeout_ms, self._remaining_ms(deadline, cancellation)
                )
                video = browser.capture(item)
                self._check(deadline, cancellation)
            self._check(deadline, cancellation)
            if video.video_id != item.video_id:
                raise CaptureClientError("INVALID_RESULT", "页面与请求的视频 ID 不符")
            cache_dir = self._data_dir / "media-cache"

            def requester(url: str, **options):
                self._check(deadline, cancellation)
                options.update(allow_proxy_dns=True, deadline=deadline, cancellation=cancellation)
                return open_pinned_https(url, **options)

            media = download_media(
                item.video_id,
                video.media_candidates,
                cache_dir,
                max_bytes=limits.max_media_bytes,
                max_duration_seconds=limits.max_media_duration_seconds,
                max_redirects=limits.max_media_redirects,
                expected_duration_seconds=video.duration_seconds,
                absolute_deadline=deadline,
                cancellation=cancellation,
                requester=requester,
            )
            self._check(deadline, cancellation)
            require_media_duration(media.duration_seconds, limits.max_media_duration_seconds)
            media_path = Path(media.path)
            cache_root = cache_dir.resolve(strict=True)
            resolved_path = media_path.resolve(strict=True)
            if media_path.is_symlink() or not resolved_path.is_relative_to(cache_root):
                raise CaptureClientError("INVALID_RESULT", "下载媒体未保存到应用缓存目录")
            digest = hashlib.sha256()
            size = 0
            with open_private_regular_file(media_path) as stream:
                while True:
                    self._check(deadline, cancellation)
                    block = stream.read(1024 * 1024)
                    if not block:
                        break
                    size += len(block)
                    if size > limits.max_media_bytes:
                        raise DownloadError("TOO_LARGE", "media exceeds limit")
                    digest.update(block)
            if size <= 0 or size != media.size_bytes:
                raise CaptureClientError("INVALID_RESULT", "下载媒体大小不符")
            self._check(deadline, cancellation)
            return CapturedMedia(
                video=CaptureVideoMetadata(
                    item.video_id,
                    video.title,
                    video.author,
                    video.publish_date,
                    video.duration_seconds,
                ),
                path=resolved_path,
                size_bytes=size,
                sha256=digest.hexdigest(),
                media_type=mimetypes.guess_type(media_path.name)[0] or "application/octet-stream",
                duration_seconds=media.duration_seconds,
            )

    def _resolve(
        self,
        original_url: str,
        max_redirects: int,
        deadline: float,
        cancellation: DownloadCancellation,
    ) -> ResolvedInput:
        self._check(deadline, cancellation)
        if (
            not isinstance(original_url, str)
            or len(original_url.encode("utf-8")) > MAX_ORIGINAL_URL_UTF8_BYTES
            or isinstance(max_redirects, bool)
            or not isinstance(max_redirects, int)
            or not 0 <= max_redirects <= MAX_SHORT_LINK_REDIRECTS
        ):
            raise CaptureClientError("INVALID_URL", "抖音链接格式或跳转上限无效")

        redirect_deadline = min(deadline, time.monotonic() + SHORT_LINK_TOTAL_TIMEOUT_SECONDS)

        def redirect(url: str) -> str | None:
            self._check(redirect_deadline, cancellation)
            location = _request_short_redirect(
                url,
                deadline=redirect_deadline,
                cancellation=cancellation,
                allow_proxy_dns=True,
            )
            self._check(redirect_deadline, cancellation)
            return location

        try:
            item = resolve_input(
                original_url, max_redirects=max_redirects, redirect_resolver=redirect
            )
        except UnsupportedUrlError:
            # The resolver deliberately sanitizes callback failures. Preserve
            # cancellation/deadline classifications after that boundary.
            self._check(redirect_deadline, cancellation)
            raise
        self._check(deadline, cancellation)
        return item

    def _deadline(self, supplied: float | None) -> float:
        now = time.monotonic()
        deadline = now + self._timeout_seconds if supplied is None else supplied
        if (
            isinstance(deadline, bool)
            or not isinstance(deadline, (int, float))
            or not math.isfinite(deadline)
            or deadline <= now
        ):
            raise CaptureClientError("CAPTURE_TIMEOUT", "本地采集超过时限", retryable=True)
        return min(float(deadline), now + self._timeout_seconds)

    @staticmethod
    def _check(deadline: float, cancellation: DownloadCancellation) -> None:
        if cancellation.is_set():
            raise CaptureClientError("CANCELLED", "本地采集已取消")
        if time.monotonic() >= deadline:
            raise CaptureClientError("CAPTURE_TIMEOUT", "本地采集超过时限", retryable=True)

    @classmethod
    def _remaining_ms(cls, deadline: float, cancellation: DownloadCancellation) -> int:
        cls._check(deadline, cancellation)
        return max(1, int((deadline - time.monotonic()) * 1000))

    @staticmethod
    def _validate_limits(limits: CaptureLimits) -> None:
        if not isinstance(limits, CaptureLimits):
            raise CaptureClientError("INVALID_LIMITS", "媒体限制配置无效")
        for value, minimum, maximum in (
            (limits.max_media_bytes, 1, MAX_MEDIA_BYTES),
            (limits.max_short_link_redirects, 0, MAX_SHORT_LINK_REDIRECTS),
            (limits.max_media_redirects, 0, MAX_MEDIA_REDIRECTS),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not minimum <= value <= maximum
            ):
                raise CaptureClientError("INVALID_LIMITS", "媒体限制配置无效")
        try:
            validate_resource_limits(limits.max_media_duration_seconds, 20_000, 2_000_000)
        except ValueError:
            raise CaptureClientError("INVALID_LIMITS", "媒体限制配置无效") from None

    @contextmanager
    def _operation(self) -> Iterator[None]:
        if not self._lock.acquire(blocking=False):
            raise CaptureClientError("CAPTURE_BUSY", _ERROR_MESSAGES["CAPTURE_BUSY"])
        lock_fd: int | None = None
        try:
            lock_fd = self._acquire_data_directory_lock()
            yield
        except CaptureClientError:
            raise
        except UnsupportedUrlError:
            raise CaptureClientError("INVALID_URL", "抖音链接无效或无法完成短链跳转") from None
        except PrivateStorageError:
            raise CaptureClientError(
                "PRIVATE_STORAGE_UNSAFE", _ERROR_MESSAGES["PRIVATE_STORAGE_UNSAFE"]
            ) from None
        except (CaptureError, DownloadError, ResourceLimitError) as exc:
            if isinstance(exc, DownloadError) and exc.code in {
                "ALL_MEDIA_CANDIDATES_FAILED",
                "DOWNLOAD_FAILED",
            }:
                raise CaptureClientError(
                    "DOWNLOAD_FAILED", _download_failure_message(exc)
                ) from None
            code = exc.code if exc.code in _ERROR_MESSAGES else "CAPTURE_FAILED"
            if code == "TIMEOUT":
                code = "CAPTURE_TIMEOUT"
            raise CaptureClientError(
                code,
                _ERROR_MESSAGES.get(code, "本地采集或媒体下载失败"),
                retryable=code == "CAPTURE_TIMEOUT",
            ) from None
        except TimeoutError:
            raise CaptureClientError(
                "CAPTURE_TIMEOUT", "本地采集超过时限", retryable=True
            ) from None
        except Exception:
            # Browser/network exceptions may contain signed URLs and cookies.
            raise CaptureClientError("CAPTURE_FAILED", "本地采集或媒体下载失败") from None
        finally:
            try:
                if lock_fd is not None:
                    os.close(lock_fd)
            finally:
                self._lock.release()

    def _acquire_data_directory_lock(self) -> int:
        """Hold an OS file lock for this data directory until the operation ends."""
        data_dir = ensure_private_directory(self._data_dir).resolve(strict=True)
        lock_path = data_dir / ".personal-capture.lock"
        create_private_file(lock_path)

        if os.name == "nt":
            _advapi, kernel = _windows_api()
            handle = kernel.CreateFileW(
                str(lock_path),
                0x80000000 | 0x00020000,  # GENERIC_READ | READ_CONTROL
                0,  # no sharing: the open handle is the cross-process lock
                None,
                3,  # OPEN_EXISTING
                0x00200000 | 0x00000080,  # OPEN_REPARSE_POINT | FILE_ATTRIBUTE_NORMAL
                None,
            )
            invalid_handle = ctypes.c_void_p(-1).value
            if not handle or handle == invalid_handle:
                error = ctypes.WinError(ctypes.get_last_error())
                if getattr(error, "winerror", None) in {32, 33}:
                    raise CaptureClientError("CAPTURE_BUSY", _ERROR_MESSAGES["CAPTURE_BUSY"])
                raise error
            try:
                information = _windows_file_information(handle)
                if information.attributes & (0x00000400 | 0x00000010):
                    raise PrivateStorageError("采集锁目标不是普通私有文件")
                if kernel.GetFileType(handle) != 1:
                    raise PrivateStorageError("采集锁目标不是普通磁盘文件")
                report = _inspect_windows_handle(handle)
                if report.status != "private":
                    raise PrivateStorageError("采集锁文件权限不安全或无法确认")
                import msvcrt

                descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | getattr(os, "O_BINARY", 0))
                handle = None
                return descriptor
            finally:
                if handle is not None:
                    kernel.CloseHandle(handle)

        report = inspect_private_path(lock_path)
        if report.status != "private":
            raise PrivateStorageError("采集锁文件权限不安全或无法确认")
        flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(lock_path, flags)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise PrivateStorageError("采集锁目标不是普通文件")
            import fcntl

            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno in {errno.EACCES, errno.EAGAIN}:
                    raise CaptureClientError(
                        "CAPTURE_BUSY", _ERROR_MESSAGES["CAPTURE_BUSY"]
                    ) from None
                raise
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise
