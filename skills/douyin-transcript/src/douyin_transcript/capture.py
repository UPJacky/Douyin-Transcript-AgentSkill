"""Optional Playwright capture for Douyin page metadata and media candidates."""

from __future__ import annotations

import hashlib
import importlib.metadata
import logging
import mimetypes
import re
import stat
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .isolation_broker import (
    BrowserIdentity,
    IsolationBrokerUnavailable,
    IsolationLease,
    ProxyEndpoint,
    open_system_broker,
)
from .storage_security import PrivateStorageError, ensure_private_directory
from .text_safety import strip_bidi_controls
from .urls import (
    DOUYIN_SHORT_HOSTS,
    DOUYIN_WEB_HOSTS,
    MEDIA_HOST_SUFFIXES,
    ResolvedInput,
    UnsupportedUrlError,
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
# Script/style assets observed on the authorized Douyin page. These are
# browser resources only; downloadable media keeps its separate allowlist.
_PERSONAL_RESOURCE_SUFFIXES = frozenset(
    {".douyinstatic.com", ".bytegoofy.com", ".bytetos.com", ".bytescm.com"}
)
_DEFAULT_CAPTURE_TIMEOUT_MS = 45_000
_DEFAULT_LOCATOR_TIMEOUT_MS = 1_000
_MAX_MEDIA_DISCOVERY_GRACE_MS = 2_000
_MEDIA_DISCOVERY_POLL_INTERVAL_MS = 200
_MAX_CAPTURE_MEDIA_URL_CHARS = 8_192
_MAX_CAPTURE_MEDIA_CANDIDATES_PER_KIND = 16
_MAX_CAPTURE_CONTENT_TYPE_CHARS = 1_024
_MAX_CAPTURE_EXPIRES_CHARS = 256
_MAX_CAPTURE_REFERER_CHARS = 2_048
_MAX_CAPTURE_TITLE_CHARS = 160
_MAX_CAPTURE_AUTHOR_CHARS = 256
_MAX_CAPTURE_PUBLISH_DATE_CHARS = 128
_MAX_DOM_TEXT_NODES = 4_096
_MAX_LOGIN_BODY_SCAN_CHARS = 16_384
_WEBRTC_POLICY_FLAG = "--force-webrtc-ip-handling-policy"
_WEBRTC_POLICY_ARGUMENT = f"{_WEBRTC_POLICY_FLAG}=disable_non_proxied_udp"
_FORBIDDEN_LAUNCH_OPTIONS = frozenset(
    {"args", "channel", "env", "executable_path", "ignore_default_args", "proxy"}
)
_BOUNDED_DOM_TEXT_SCRIPT = """
(element, limits) => {
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
  let text = "";
  let visitedNodes = 0;
  while (text.length <= limits.maxChars && visitedNodes < limits.maxNodes && walker.nextNode()) {
    visitedNodes += 1;
    const node = walker.currentNode;
    const parent = node.parentElement;
    if (!parent || parent.closest("script,style,noscript,[hidden]")) continue;
    const style = window.getComputedStyle(parent);
    if (
      style.display === "none" ||
      style.visibility === "hidden" ||
      style.visibility === "collapse"
    ) continue;
    const remaining = limits.maxChars + 1 - text.length;
    text += (node.nodeValue || "").slice(0, remaining);
  }
  return text;
}
""".strip()
_BOUNDED_ATTRIBUTE_SCRIPT = """
(element, limits) => {
  const value = element.getAttribute(limits.attribute);
  return value === null ? null : value.slice(0, limits.maxChars + 1);
}
""".strip()
_LOGIN_BODY_SCAN_SCRIPT = """
(element, limits) => {
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
  let scannedChars = 0;
  let visitedNodes = 0;
  while (scannedChars < limits.maxChars && visitedNodes < limits.maxNodes && walker.nextNode()) {
    visitedNodes += 1;
    const node = walker.currentNode;
    const parent = node.parentElement;
    if (!parent || parent.closest("script,style,noscript,[hidden]")) continue;
    const style = window.getComputedStyle(parent);
    if (
      style.display === "none" ||
      style.visibility === "hidden" ||
      style.visibility === "collapse"
    ) continue;
    const remaining = limits.maxChars - scannedChars;
    const text = (node.nodeValue || "").slice(0, remaining);
    if (text.includes("登录后观看") || text.includes("请登录后")) return true;
    scannedChars += text.length;
  }
  return false;
}
""".strip()
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
    ``personal=True`` uses the current user's bundled Chromium with its sandbox
    enabled, without requesting the optional system isolation service.
    """

    def __init__(
        self,
        profile_dir: str | Path,
        *,
        headless: bool = False,
        navigation_timeout_ms: int = 30_000,
        capture_timeout_ms: int = _DEFAULT_CAPTURE_TIMEOUT_MS,
        locator_timeout_ms: int = _DEFAULT_LOCATOR_TIMEOUT_MS,
        launch_options: dict[str, Any] | None = None,
        personal: bool = False,
    ) -> None:
        if min(navigation_timeout_ms, capture_timeout_ms, locator_timeout_ms) <= 0:
            raise ValueError("browser capture timeouts must be positive")
        if not isinstance(personal, bool):
            raise ValueError("personal must be a boolean")
        self.profile_dir = Path(profile_dir).expanduser()
        self.headless = headless
        self.navigation_timeout_ms = navigation_timeout_ms
        self.capture_timeout_ms = capture_timeout_ms
        self.locator_timeout_ms = locator_timeout_ms
        self.launch_options = dict(launch_options or {})
        self.personal = personal
        self._playwright: Any = None
        self._context: Any = None
        self._lease: IsolationLease | None = None
        self._lease_lost = False
        self._capture_deadline: float | None = None

    def start(self) -> BrowserCapture:
        if self._context is not None:
            self._ensure_lease_active()
            return self

        forbidden = sorted(_FORBIDDEN_LAUNCH_OPTIONS.intersection(self.launch_options))
        if forbidden:
            raise CaptureError(
                "BROWSER_SECURITY_OVERRIDE",
                "浏览器可执行文件和网络参数由隔离策略管理",
            )
        self._lease_lost = False
        broker = None
        if not self.personal:
            try:
                broker = open_system_broker()
            except Exception:
                raise CaptureError(
                    "BROWSER_ISOLATION_UNAVAILABLE",
                    "管理员预配置的浏览器网络隔离服务不可用",
                ) from None

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise CaptureError("PLAYWRIGHT_MISSING", "浏览器抓取需要安装 Playwright") from None

        try:
            self.profile_dir = ensure_private_directory(self.profile_dir)
            launch_options = dict(self.launch_options)
            launch_options["args"] = [_WEBRTC_POLICY_ARGUMENT]
            launch_options.update(
                headless=self.headless,
                # Persistent profiles may already contain a service worker.
                # Block workers because Playwright page/context routes do not
                # intercept requests handled by them.
                service_workers="block",
            )
            if self.personal:
                # Use Playwright's bundled Chromium as the current user. This
                # mode provides no system-wide network isolation contract.
                launch_options["chromium_sandbox"] = True
            else:
                try:
                    self._lease = broker.acquire()
                    browser_identity = _verify_browser_identity(self._lease.browser)
                    proxy_endpoint = _validate_proxy_endpoint(self._lease.proxy_endpoint)
                except Exception:
                    raise IsolationBrokerUnavailable from None
                self._ensure_lease_active()
                launch_options.update(
                    executable_path=str(browser_identity.executable_path),
                    proxy={
                        "server": f"http://{proxy_endpoint.host}:{proxy_endpoint.port}",
                        "bypass": "<-loopback>",
                    },
                )
            self._playwright = sync_playwright().start()
            self._context = self._playwright.chromium.launch_persistent_context(
                str(self.profile_dir),
                **launch_options,
            )
            # Context routes also cover the first navigation of popup pages.
            # Install these before capture() creates or navigates any page.
            self._context.route("**/*", self._guard_request)
            self._context.route_web_socket("**/*", self._guard_websocket)
        except PrivateStorageError as exc:
            self.close()
            raise CaptureError("PRIVATE_STORAGE_UNSAFE", str(exc)) from None
        except CaptureError:
            self.close()
            raise
        except IsolationBrokerUnavailable:
            self.close()
            raise CaptureError(
                "BROWSER_ISOLATION_UNAVAILABLE",
                "无法核验浏览器网络隔离服务或 Chromium 身份",
            ) from None
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
        lease = self._lease
        self._context = None
        self._playwright = None
        self._lease = None
        self._lease_lost = False
        self._capture_deadline = None
        if context is not None:
            try:
                context.close()
            except Exception:
                _LOGGER.debug("浏览器上下文关闭失败")
        if lease is not None:
            try:
                lease.close()
            except Exception:
                _LOGGER.debug("浏览器隔离租约关闭失败")
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
        self._ensure_lease_active()
        context = self._require_context()
        deadline = time.monotonic() + self.capture_timeout_ms / 1000
        self._capture_deadline = deadline
        try:
            page = context.new_page()
        except Exception as exc:
            self._capture_deadline = None
            if time.monotonic() >= deadline:
                raise CaptureError("CAPTURE_TIMEOUT", "页面捕获超时") from None
            raise CaptureError("CAPTURE_FAILED", f"页面捕获失败（{type(exc).__name__}）") from None
        candidates_by_url: dict[str, MediaCandidate] = {}
        candidate_counts = {"audio": 0, "video": 0}

        def on_response(response: Any) -> None:
            if len(candidates_by_url) >= 2 * _MAX_CAPTURE_MEDIA_CANDIDATES_PER_KIND:
                return
            try:
                candidate = _candidate_from_response(response)
            except Exception:
                # Event handlers must not leak signed URLs in tracebacks/logs.
                return
            if candidate is not None:
                if candidate.url in candidates_by_url:
                    return
                if candidate_counts[candidate.kind] >= _MAX_CAPTURE_MEDIA_CANDIDATES_PER_KIND:
                    return
                candidates_by_url[candidate.url] = candidate
                candidate_counts[candidate.kind] += 1

        try:
            # The response listener is installed before navigation, so initial
            # document and media responses are observable.
            page.on("response", on_response)
            page.set_default_timeout(self.locator_timeout_ms)
            navigation_timeout = min(
                self.navigation_timeout_ms,
                _remaining_capture_timeout_ms(deadline, self.capture_timeout_ms),
            )
            page.set_default_navigation_timeout(navigation_timeout)
            response = page.goto(
                item.canonical_url,
                wait_until="domcontentloaded",
                timeout=navigation_timeout,
            )
            self._ensure_lease_active()
            _remaining_capture_timeout_ms(deadline, self.capture_timeout_ms)
            if response is not None and response.status in (401, 403):
                raise CaptureError("LOGIN_REQUIRED", "页面要求登录或当前账号无权访问")
            page.wait_for_timeout(
                min(500, _remaining_capture_timeout_ms(deadline, self.capture_timeout_ms))
            )
            if _login_required(page, deadline, self.locator_timeout_ms):
                raise CaptureError("LOGIN_REQUIRED", "页面要求登录，请在打开的浏览器中手动登录")
            title, author, publish_date, duration = _read_metadata(
                page, deadline, self.locator_timeout_ms
            )
            _wait_for_media_candidates(
                page,
                candidates_by_url,
                deadline,
                max_wait_ms=_MAX_MEDIA_DISCOVERY_GRACE_MS,
            )
            self._ensure_lease_active()
            _remaining_capture_timeout_ms(deadline, self.capture_timeout_ms)
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
            if self._lease_lost:
                self._ensure_lease_active()
            raise
        except Exception as exc:
            if self._lease_lost:
                self._ensure_lease_active()
            # Never include raw browser exception messages: they often contain
            # request URLs with temporary signatures.
            if deadline is not None and time.monotonic() >= deadline:
                raise CaptureError("CAPTURE_TIMEOUT", "页面捕获超时") from None
            raise CaptureError("CAPTURE_FAILED", f"页面捕获失败（{type(exc).__name__}）") from None
        finally:
            try:
                page.close()
            except Exception:
                pass
            self._capture_deadline = None

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

    def _guard_request(self, route: Any) -> None:
        if not self._route_lease_active():
            try:
                route.abort()
            except Exception:
                pass
            return
        _guard_browser_request(
            route, deadline=self._capture_deadline, personal=self.personal
        )

    def _guard_websocket(self, route: Any) -> None:
        if not self._route_lease_active():
            try:
                route.close(code=1008, reason="Browser isolation lease lost")
            except Exception:
                pass
            return
        _guard_browser_websocket(route, deadline=self._capture_deadline)

    def _route_lease_active(self) -> bool:
        if self._lease is None:
            return not self._lease_lost
        if self._lease_lost:
            return False
        try:
            self._lease.ensure_active()
        except Exception:
            self._lease_lost = True
            return False
        return True

    def _ensure_lease_active(self) -> None:
        if self._lease is None:
            return
        if self._lease_lost:
            self.close()
            raise CaptureError(
                "BROWSER_ISOLATION_LOST",
                "浏览器网络隔离租约中断，已关闭捕获浏览器",
            ) from None
        try:
            self._lease.ensure_active()
        except Exception:
            self.close()
            raise CaptureError(
                "BROWSER_ISOLATION_LOST",
                "浏览器网络隔离租约中断，已关闭捕获浏览器",
            ) from None


def _verify_browser_identity(identity: BrowserIdentity) -> BrowserIdentity:
    """Verify a broker-selected, administrator-protected Chromium identity."""

    if (
        not isinstance(identity, BrowserIdentity)
        or not isinstance(identity.executable_path, Path)
        or not isinstance(identity.executable_sha256, str)
        or not isinstance(identity.playwright_version, str)
        or not isinstance(identity.chromium_revision, str)
        or not re.fullmatch(r"[a-fA-F0-9]{64}", identity.executable_sha256)
        or not re.fullmatch(r"\d+", identity.chromium_revision)
    ):
        raise IsolationBrokerUnavailable
    try:
        executable = identity.executable_path.resolve(strict=True)
        before = executable.stat()
        if not stat.S_ISREG(before.st_mode):
            raise OSError("Chromium executable is not a regular file")
        digest = hashlib.sha256()
        with executable.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        after = executable.stat()
        identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if identity_before != identity_after:
            raise OSError("Chromium executable changed during identity check")
        if digest.hexdigest().lower() != identity.executable_sha256.lower():
            raise OSError("Chromium executable hash does not match broker identity")
        revision = next(
            (
                match.group(1)
                for part in executable.parts
                if (match := re.fullmatch(r"chromium-(\d+)", part, flags=re.IGNORECASE))
            ),
            None,
        )
        if revision is None or revision != identity.chromium_revision:
            raise OSError("Chromium revision is not identifiable")
        version = importlib.metadata.version("playwright")
        if version != identity.playwright_version:
            raise OSError("Playwright version does not match broker identity")
    except (OSError, importlib.metadata.PackageNotFoundError, ValueError):
        raise IsolationBrokerUnavailable from None
    return BrowserIdentity(executable, identity.executable_sha256.lower(), version, revision)


def _validate_proxy_endpoint(endpoint: ProxyEndpoint) -> ProxyEndpoint:
    if (
        not isinstance(endpoint, ProxyEndpoint)
        or endpoint.host != "127.0.0.1"
        or type(endpoint.port) is not int
        or not 1 <= endpoint.port <= 65535
    ):
        raise IsolationBrokerUnavailable
    return endpoint


def _candidate_from_response(response: Any) -> MediaCandidate | None:
    status = int(response.status)
    if status not in (200, 206):
        return None
    raw_url = str(response.url)
    if len(raw_url) > _MAX_CAPTURE_MEDIA_URL_CHARS:
        return None
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
            expires_value = str(expires)
            if len(expires_value) > _MAX_CAPTURE_EXPIRES_CHARS:
                return None
            expires_at = parsedate_to_datetime(expires_value)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= datetime.now(UTC):
                return None
        except (TypeError, ValueError, OverflowError):
            return None
    content_type = str(headers.get("content-type", ""))
    if len(content_type) > _MAX_CAPTURE_CONTENT_TYPE_CHARS:
        return None
    mime = content_type.split(";", 1)[0].strip().lower()
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
    if referer and len(referer) <= _MAX_CAPTURE_REFERER_CHARS:
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


def _read_metadata(
    page: Any,
    deadline: float,
    locator_timeout_ms: int,
) -> tuple[str | None, str | None, str | None, float | None]:
    title = _first_text(
        page,
        [
            '[data-e2e="video-desc"]',
            'meta[property="og:title"]',
            "title",
        ],
        deadline,
        locator_timeout_ms,
        max_chars=_MAX_CAPTURE_TITLE_CHARS,
    )
    title = _clean_title(title)
    author = _first_text(
        page,
        ['[data-e2e="video-author-name"]', 'meta[name="author"]'],
        deadline,
        locator_timeout_ms,
        max_chars=_MAX_CAPTURE_AUTHOR_CHARS,
    )
    publish_date = _first_attribute(
        page,
        ['meta[property="article:published_time"]', "time[datetime]"],
        "content",
        deadline,
        locator_timeout_ms,
        max_chars=_MAX_CAPTURE_PUBLISH_DATE_CHARS,
    ) or _first_attribute(
        page,
        ["time[datetime]"],
        "datetime",
        deadline,
        locator_timeout_ms,
        max_chars=_MAX_CAPTURE_PUBLISH_DATE_CHARS,
    )
    try:
        raw_duration = page.locator("video").first.evaluate(
            "element => element.duration",
            timeout=_remaining_capture_timeout_ms(deadline, locator_timeout_ms),
        )
        duration = float(raw_duration) if raw_duration is not None else None
        if duration is not None and (duration <= 0 or duration != duration):
            duration = None
    except CaptureError:
        raise
    except Exception:
        duration = None
    return (
        title,
        _clean_bounded_plain_text(author, _MAX_CAPTURE_AUTHOR_CHARS),
        _clean_bounded_plain_text(publish_date, _MAX_CAPTURE_PUBLISH_DATE_CHARS),
        duration,
    )


def _first_text(
    page: Any,
    selectors: list[str],
    deadline: float,
    locator_timeout_ms: int,
    *,
    max_chars: int,
) -> str | None:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if selector.startswith("meta["):
                value = _read_bounded_attribute(
                    locator,
                    "content",
                    max_chars=max_chars,
                    deadline=deadline,
                    timeout_ms=locator_timeout_ms,
                )
            elif selector == "title":
                # <title> is hidden by CSS, so the visible-text reader skips it.
                value = locator.evaluate(
                    "(element, limits) => "
                    "(element.textContent || '').slice(0, limits.maxChars + 1)",
                    {"maxChars": max_chars},
                    timeout=_remaining_capture_timeout_ms(deadline, locator_timeout_ms),
                )
            else:
                value = _read_bounded_dom_text(
                    locator,
                    max_chars=max_chars,
                    deadline=deadline,
                    timeout_ms=locator_timeout_ms,
                )
            if value is not None and len(value) > max_chars:
                continue
            if value and value.strip():
                return value.strip()
        except CaptureError:
            raise
        except Exception:
            continue
    return None


def _first_attribute(
    page: Any,
    selectors: list[str],
    attribute: str,
    deadline: float,
    locator_timeout_ms: int,
    *,
    max_chars: int,
) -> str | None:
    for selector in selectors:
        try:
            value = _read_bounded_attribute(
                page.locator(selector).first,
                attribute,
                max_chars=max_chars,
                deadline=deadline,
                timeout_ms=locator_timeout_ms,
            )
            if value is not None and len(value) > max_chars:
                continue
            if value and value.strip():
                return value.strip()
        except CaptureError:
            raise
        except Exception:
            continue
    return None


def _remaining_capture_timeout_ms(deadline: float, max_timeout_ms: int) -> int:
    remaining_seconds = deadline - time.monotonic()
    if remaining_seconds <= 0:
        raise CaptureError("CAPTURE_TIMEOUT", "页面捕获超时")
    return min(max_timeout_ms, max(1, int(remaining_seconds * 1000)))


def _read_bounded_dom_text(
    locator: Any,
    *,
    max_chars: int,
    deadline: float,
    timeout_ms: int,
) -> str:
    value = locator.evaluate(
        _BOUNDED_DOM_TEXT_SCRIPT,
        {"maxChars": max_chars, "maxNodes": _MAX_DOM_TEXT_NODES},
        timeout=_remaining_capture_timeout_ms(deadline, timeout_ms),
    )
    return value[: max_chars + 1] if isinstance(value, str) else ""


def _read_bounded_attribute(
    locator: Any,
    attribute: str,
    *,
    max_chars: int,
    deadline: float,
    timeout_ms: int,
) -> str | None:
    value = locator.evaluate(
        _BOUNDED_ATTRIBUTE_SCRIPT,
        {"attribute": attribute, "maxChars": max_chars},
        timeout=_remaining_capture_timeout_ms(deadline, timeout_ms),
    )
    return value[: max_chars + 1] if isinstance(value, str) else None


def _wait_for_media_candidates(
    page: Any,
    candidates_by_url: dict[str, MediaCandidate],
    deadline: float,
    *,
    max_wait_ms: int,
) -> None:
    """Give delayed media responses a short bounded window to arrive."""
    grace_deadline = min(deadline, time.monotonic() + max_wait_ms / 1000)
    while not candidates_by_url:
        remaining_seconds = grace_deadline - time.monotonic()
        if remaining_seconds <= 0:
            return
        page.wait_for_timeout(
            min(
                _MEDIA_DISCOVERY_POLL_INTERVAL_MS,
                max(1, int(remaining_seconds * 1000)),
            )
        )
        _remaining_capture_timeout_ms(deadline, _MEDIA_DISCOVERY_POLL_INTERVAL_MS)


def _clean_title(value: str | None) -> str | None:
    value = _clean_plain_text(value)
    if value is None:
        return None
    value = re.sub(r"\s*[-|｜]\s*抖音.*$", "", value).strip()
    value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
    if not value or len(value) > _MAX_CAPTURE_TITLE_CHARS or "#" in value or "\n" in value:
        return None
    return value


def _clean_bounded_plain_text(value: str | None, max_chars: int) -> str | None:
    if value is None or len(value) > max_chars:
        return None
    return _clean_plain_text(value)


def _clean_plain_text(value: str | None) -> str | None:
    if value is None:
        return None
    # Page metadata is untrusted. Remove terminal and bidirectional controls
    # before it reaches console output, filenames, or a Markdown heading.
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", value)
    value = strip_bidi_controls(value)
    cleaned = " ".join(value.split()).strip()
    return cleaned or None


def _login_required(page: Any, deadline: float, locator_timeout_ms: int) -> bool:
    try:
        host = (urlsplit(page.url).hostname or "").lower()
        if host.startswith("passport."):
            return True
        if page.locator('[data-e2e="login-tab"]:visible, [data-e2e="login-modal"]:visible').count():
            return True
        has_login_prompt = page.locator("body").evaluate(
            _LOGIN_BODY_SCAN_SCRIPT,
            {
                "maxChars": _MAX_LOGIN_BODY_SCAN_CHARS,
                "maxNodes": _MAX_DOM_TEXT_NODES,
            },
            timeout=_remaining_capture_timeout_ms(deadline, locator_timeout_ms),
        )
        return bool(has_login_prompt)
    except CaptureError:
        raise
    except Exception:
        return False


def _guard_browser_request(
    route: Any, *, deadline: float | None = None, personal: bool = False
) -> None:
    """Route HTTPS requests by URL and hostname policy without doing DNS."""
    try:
        if deadline is not None and time.monotonic() >= deadline:
            route.abort()
            return
        host = _validated_route_host(route.request.url, expected_scheme="https")
        if host is None:
            route.abort()
            return
        is_navigation = route.request.is_navigation_request()
        if is_navigation and host not in _NAVIGATION_HOSTS:
            route.abort()
            return
        if not is_navigation and not _resource_host_allowed(host, personal=personal):
            route.abort()
            return
        route.continue_()
    except Exception:
        route.abort()


def _guard_browser_websocket(route: Any, *, deadline: float | None = None) -> None:
    """Allow WSS URLs by hostname policy without doing DNS in the app process."""
    try:
        if deadline is not None and time.monotonic() >= deadline:
            route.close(code=1008, reason="Blocked by network policy")
            return
        host = _validated_route_host(route.url, expected_scheme="wss")
        if host is None or not _resource_host_allowed(host):
            route.close(code=1008, reason="Blocked by network policy")
            return
        route.connect_to_server()
    except Exception:
        # If URL policy parsing or routing fails, do not establish the
        # WebSocket as a fallback.
        try:
            route.close(code=1008, reason="Blocked by network policy")
        except Exception:
            pass


def _validated_route_host(url: str, *, expected_scheme: str) -> str | None:
    """Validate route URL syntax and return its normalized host without DNS."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme.lower() != expected_scheme:
            return None
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host:
            return None
        https_url = (
            url
            if expected_scheme == "https"
            else urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, parsed.fragment))
        )
        validate_https_url(
            https_url,
            allowed_hosts={host},
            resolve_dns=False,
        )
    except (TypeError, ValueError, UnsupportedUrlError):
        return None
    return host


def _resource_host_allowed(host: str, *, personal: bool = False) -> bool:
    host = host.lower().rstrip(".")
    trusted_suffixes = MEDIA_HOST_SUFFIXES | {".douyin.com", ".iesdouyin.com"}
    if personal:
        trusted_suffixes |= _PERSONAL_RESOURCE_SUFFIXES
    return host in _NAVIGATION_HOSTS or any(
        host == suffix[1:] or host.endswith(suffix) for suffix in trusted_suffixes
    )
