"""Optional Playwright capture for Douyin page metadata and media candidates."""

from __future__ import annotations

import logging
import mimetypes
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .browser_proxy import PinnedHttpsConnectProxy
from .storage_security import PrivateStorageError, ensure_private_directory
from .text_safety import strip_bidi_controls
from .urls import (
    DOUYIN_SHORT_HOSTS,
    DOUYIN_WEB_HOSTS,
    MEDIA_HOST_SUFFIXES,
    ResolvedInput,
    UnsupportedUrlError,
    resolve_public_addresses,
    validate_https_url,
)

_LOGGER = logging.getLogger(__name__)
_NAVIGATION_HOSTS = (
    DOUYIN_WEB_HOSTS
    | DOUYIN_SHORT_HOSTS
    | {
        "passport.douyin.com",
        "www.iesdouyin.com",
    }
)
_PUBLIC_HOST_DNS_TIMEOUT_SECONDS = 5.0
_AUDIO_MIMES = frozenset(
    {
        "audio/aac",
        "audio/mp4",
        "audio/mpeg",
        "audio/ogg",
        "audio/wav",
        "audio/webm",
        "audio/x-m4a",
        "audio/x-wav",
    }
)
_VIDEO_MIMES = frozenset(
    {
        "video/mp4",
        "video/webm",
        "video/quicktime",
        "video/x-matroska",
        "application/vnd.apple.mpegurl",
    }
)


class CaptureError(RuntimeError):
    """A user-safe browser capture error with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class MediaCandidate:
    url: str = field(repr=False)
    kind: str
    mime_type: str
    headers: dict[str, str] = field(default_factory=dict, repr=False)
    observed_at: str = ""
    source: str = "browser_response"


@dataclass(frozen=True, slots=True)
class VideoMetadata:
    video_id: str
    title: str | None
    author: str | None
    publish_date: str | None
    source_url: str
    duration_seconds: float | None
    media_candidates: list[MediaCandidate]


class BrowserCapture:
    """A persistent Playwright Chromium context reusable across URL batches.

    Playwright is imported only when ``start`` is called. The profile directory
    is the user's long-lived browser state and should live under the configured
    application data directory.
    """

    def __init__(
        self,
        profile_dir: str | Path,
        *,
        headless: bool = False,
        navigation_timeout_ms: int = 30_000,
        launch_options: dict[str, Any] | None = None,
    ) -> None:
        self.profile_dir = Path(profile_dir).expanduser()
        self.headless = headless
        self.navigation_timeout_ms = navigation_timeout_ms
        self.launch_options = dict(launch_options or {})
        self._playwright: Any = None
        self._context: Any = None
        self._proxy: PinnedHttpsConnectProxy | None = None

    def start(self) -> BrowserCapture:
        if self._context is not None:
            return self
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise CaptureError("PLAYWRIGHT_MISSING", "浏览器抓取需要安装 Playwright") from None

        try:
            if "proxy" in self.launch_options:
                raise ValueError("browser proxy is managed by the capture security policy")
            args = self.launch_options.get("args", ())
            if any(
                str(value).lower().startswith("--proxy-")
                or str(value).lower() == "--no-proxy-server"
                for value in args
            ):
                raise ValueError("browser proxy command-line overrides are not supported")
            if self.launch_options.get("ignore_default_args"):
                raise ValueError("ignore_default_args could bypass the capture proxy")
            self.profile_dir = ensure_private_directory(self.profile_dir)
            self._proxy = PinnedHttpsConnectProxy().start()
            self._playwright = sync_playwright().start()
            launch_options = dict(self.launch_options)
            launch_options.update(
                headless=self.headless,
                proxy=self._proxy.playwright_options,
                # Persistent profiles may already contain a service worker.
                # Block workers because Playwright page/context routes do not
                # intercept requests handled by them.
                service_workers="block",
            )
            self._context = self._playwright.chromium.launch_persistent_context(
                str(self.profile_dir),
                **launch_options,
            )
            # Context routes also cover the first navigation of popup pages.
            # Install these before capture() creates or navigates any page.
            self._context.route("**/*", _guard_browser_request)
            self._context.route_web_socket("**/*", _guard_browser_websocket)
        except PrivateStorageError as exc:
            self.close()
            raise CaptureError("PRIVATE_STORAGE_UNSAFE", str(exc)) from None
        except Exception as exc:
            self.close()
            # Exception strings from Playwright can contain URLs or filesystem
            # details. Expose only a stable code and exception type.
            raise CaptureError(
                "BROWSER_START_FAILED", f"Chromium 启动失败（{type(exc).__name__}）"
            ) from None
        return self

    def close(self) -> None:
        context, playwright = self._context, self._playwright
        proxy = self._proxy
        self._context = None
        self._playwright = None
        self._proxy = None
        if context is not None:
            try:
                context.close()
            except Exception:
                _LOGGER.debug("浏览器上下文关闭失败")
        if proxy is not None:
            try:
                proxy.close()
            except Exception:
                _LOGGER.debug("受限网络代理关闭失败")
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                _LOGGER.debug("Playwright 关闭失败")

    def __enter__(self) -> BrowserCapture:
        return self.start()

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def capture(self, item: ResolvedInput) -> VideoMetadata:
        context = self._require_context()
        try:
            page = context.new_page()
        except Exception as exc:
            raise CaptureError("CAPTURE_FAILED", f"页面捕获失败（{type(exc).__name__}）") from None
        candidates_by_url: dict[str, MediaCandidate] = {}

        def on_response(response: Any) -> None:
            try:
                candidate = _candidate_from_response(response)
            except Exception:
                # Event handlers must not leak signed URLs in tracebacks/logs.
                return
            if candidate is not None:
                candidates_by_url.setdefault(candidate.url, candidate)

        try:
            # The response listener is installed before navigation, so initial
            # document and media responses are observable.
            page.on("response", on_response)
            page.set_default_navigation_timeout(self.navigation_timeout_ms)
            response = page.goto(item.canonical_url, wait_until="domcontentloaded")
            if response is not None and response.status in (401, 403):
                raise CaptureError("LOGIN_REQUIRED", "页面要求登录或当前账号无权访问")
            page.wait_for_timeout(500)
            if _login_required(page):
                raise CaptureError("LOGIN_REQUIRED", "页面要求登录，请在打开的浏览器中手动登录")
            title, author, publish_date, duration = _read_metadata(page)
            candidates = sorted(
                candidates_by_url.values(),
                key=lambda value: (value.kind != "audio", value.observed_at),
            )
            if not candidates:
                raise CaptureError("CAPTURE_NO_MEDIA", "页面已打开，但没有发现可下载的音视频流")
            return VideoMetadata(
                video_id=item.video_id,
                title=title,
                author=author,
                publish_date=publish_date,
                source_url=item.canonical_url,
                duration_seconds=duration,
                media_candidates=candidates,
            )
        except CaptureError:
            raise
        except Exception as exc:
            # Never include raw browser exception messages: they often contain
            # request URLs with temporary signatures.
            raise CaptureError("CAPTURE_FAILED", f"页面捕获失败（{type(exc).__name__}）") from None
        finally:
            try:
                page.close()
            except Exception:
                pass

    def capture_many(self, items: Iterable[ResolvedInput]) -> list[VideoMetadata | CaptureError]:
        """Capture a batch with one persistent browser context and isolated pages."""
        self._require_context()
        results: list[VideoMetadata | CaptureError] = []
        for item in items:
            try:
                results.append(self.capture(item))
            except CaptureError as exc:
                results.append(exc)
        return results

    def _require_context(self) -> Any:
        if self._context is None:
            self.start()
        return self._context


def _candidate_from_response(response: Any) -> MediaCandidate | None:
    status = int(response.status)
    if status not in (200, 206):
        return None
    raw_url = str(response.url)
    if raw_url.startswith("blob:"):
        return None
    try:
        validate_https_url(
            raw_url,
            allowed_hosts=DOUYIN_WEB_HOSTS | DOUYIN_SHORT_HOSTS,
            allowed_suffixes=MEDIA_HOST_SUFFIXES,
            resolve_dns=False,
        )
    except UnsupportedUrlError:
        return None
    headers = response.headers
    expires = headers.get("expires")
    if expires:
        try:
            expires_at = parsedate_to_datetime(str(expires))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= datetime.now(UTC):
                return None
        except (TypeError, ValueError, OverflowError):
            return None
    mime = str(headers.get("content-type", "")).split(";", 1)[0].strip().lower()
    if mime in _AUDIO_MIMES:
        kind = "audio"
    elif mime in _VIDEO_MIMES:
        kind = "video"
    else:
        guessed, _ = mimetypes.guess_type(urlsplit(raw_url).path)
        if guessed in _AUDIO_MIMES:
            kind, mime = "audio", guessed
        elif guessed in _VIDEO_MIMES:
            kind, mime = "video", guessed
        else:
            return None
    safe_headers: dict[str, str] = {}
    try:
        request_headers = response.request.all_headers()
    except Exception:
        request_headers = {}
    for name in ("user-agent", "accept"):
        value = request_headers.get(name)
        if value and len(value) <= 1024:
            safe_headers[name.title()] = value
    referer = request_headers.get("referer")
    if referer:
        try:
            referer_parts = urlsplit(referer)
            if referer_parts.scheme == "https" and referer_parts.hostname:
                safe_headers["Referer"] = urlunsplit(
                    (referer_parts.scheme, referer_parts.netloc, referer_parts.path, "", "")
                )
        except ValueError:
            pass
    return MediaCandidate(
        url=raw_url,
        kind=kind,
        mime_type=mime,
        headers=safe_headers,
        observed_at=datetime.now(UTC).isoformat(),
    )


def _read_metadata(page: Any) -> tuple[str | None, str | None, str | None, float | None]:
    title = _first_text(
        page,
        [
            '[data-e2e="video-desc"]',
            'meta[property="og:title"]',
            "title",
        ],
    )
    title = _clean_title(title)
    author = _first_text(page, ['[data-e2e="video-author-name"]', 'meta[name="author"]'])
    publish_date = _first_attribute(
        page,
        ['meta[property="article:published_time"]', "time[datetime]"],
        "content",
    ) or _first_attribute(page, ["time[datetime]"], "datetime")
    try:
        raw_duration = page.locator("video").first.evaluate("element => element.duration")
        duration = float(raw_duration) if raw_duration is not None else None
        if duration is not None and (duration <= 0 or duration != duration):
            duration = None
    except Exception:
        duration = None
    return title, _clean_plain_text(author), _clean_plain_text(publish_date), duration


def _first_text(page: Any, selectors: list[str]) -> str | None:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            value = (
                locator.get_attribute("content")
                if selector.startswith("meta[")
                else locator.inner_text()
            )
            if value and value.strip():
                return value.strip()
        except Exception:
            continue
    return None


def _first_attribute(page: Any, selectors: list[str], attribute: str) -> str | None:
    for selector in selectors:
        try:
            value = page.locator(selector).first.get_attribute(attribute)
            if value and value.strip():
                return value.strip()
        except Exception:
            continue
    return None


def _clean_title(value: str | None) -> str | None:
    value = _clean_plain_text(value)
    if value is None:
        return None
    value = re.sub(r"\s*[-|｜]\s*抖音.*$", "", value).strip()
    if not value or len(value) > 160 or "#" in value or "\n" in value:
        return None
    return value


def _clean_plain_text(value: str | None) -> str | None:
    if value is None:
        return None
    # Page metadata is untrusted. Remove terminal and bidirectional controls
    # before it reaches console output, filenames, or a Markdown heading.
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", value)
    value = strip_bidi_controls(value)
    cleaned = " ".join(value.split()).strip()
    return cleaned or None


def _login_required(page: Any) -> bool:
    try:
        host = (urlsplit(page.url).hostname or "").lower()
        if host.startswith("passport."):
            return True
        if page.locator('[data-e2e="login-tab"]:visible, [data-e2e="login-modal"]:visible').count():
            return True
        body = page.locator("body").inner_text(timeout=1000)
        return "登录后观看" in body or "请登录后" in body
    except Exception:
        return False


def _require_public_host(host: str) -> None:
    try:
        resolve_public_addresses(
            host,
            deadline=time.monotonic() + _PUBLIC_HOST_DNS_TIMEOUT_SECONDS,
        )
    except Exception:
        raise CaptureError("UNSAFE_PAGE_REQUEST", "页面请求被安全策略拦截") from None


def _guard_browser_request(route: Any) -> None:
    """Route only HTTPS requests to approved public Douyin destinations."""
    try:
        parsed = urlsplit(route.request.url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or not host:
            route.abort()
            return
        if route.request.is_navigation_request and host not in _NAVIGATION_HOSTS:
            route.abort()
            return
        if not route.request.is_navigation_request and not _resource_host_allowed(host):
            route.abort()
            return
        _require_public_host(host)
        route.continue_()
    except Exception:
        route.abort()


def _guard_browser_websocket(route: Any) -> None:
    """Allow only public WSS endpoints already permitted for browser resources."""
    try:
        parsed = urlsplit(route.url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "wss" or not host or not _resource_host_allowed(host):
            route.close(code=1008, reason="Blocked by network policy")
            return
        _require_public_host(host)
        route.connect_to_server()
    except Exception:
        # If policy parsing, DNS validation, or routing fails, do not establish
        # the WebSocket as a fallback.
        try:
            route.close(code=1008, reason="Blocked by network policy")
        except Exception:
            pass


def _resource_host_allowed(host: str) -> bool:
    host = host.lower().rstrip(".")
    trusted_suffixes = MEDIA_HOST_SUFFIXES | {".douyin.com", ".iesdouyin.com"}
    return host in _NAVIGATION_HOSTS or any(
        host == suffix[1:] or host.endswith(suffix) for suffix in trusted_suffixes
    )
