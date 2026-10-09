from __future__ import annotations

import builtins
import sys
import time
from types import ModuleType, SimpleNamespace

import douyin_transcript.capture as capture_module
from douyin_transcript.capture import (
    BrowserCapture,
    CaptureError,
    _candidate_from_response,
    _clean_title,
    _guard_browser_request,
    _guard_browser_websocket,
    _require_public_host,
)
from douyin_transcript.urls import ResolvedInput, UnsupportedUrlError


class FakeRequest:
    resource_type = "media"

    def all_headers(self):
        return {
            "user-agent": "test-agent",
            "accept": "audio/mp4",
            "referer": "https://www.douyin.com/video/123?tracking=secret",
            "cookie": "session=private-cookie",
            "authorization": "Bearer private-token",
        }


class FakeResponse:
    status = 200
    url = "https://v3-web.douyinvod.com/audio.m4a?sign=secret-token"
    headers = {"content-type": "audio/mp4; codecs=mp4a.40.2"}
    request = FakeRequest()


def test_untrusted_page_title_drops_c0_and_del_control_characters():
    cleaned = _clean_title("Title\x1b[31m\x07\x7f\u202e\tcontinued")

    assert cleaned == "Title[31m continued"
    assert not any(ord(character) < 32 or ord(character) == 127 for character in cleaned)
    assert "\u202e" not in cleaned


def test_media_candidate_keeps_only_whitelisted_headers_and_private_url_in_memory():
    candidate = _candidate_from_response(FakeResponse())

    assert candidate is not None
    assert candidate.kind == "audio"
    assert candidate.url.endswith("sign=secret-token")
    assert candidate.headers == {
        "User-Agent": "test-agent",
        "Accept": "audio/mp4",
        "Referer": "https://www.douyin.com/video/123",
    }
    assert "cookie" not in str(candidate.headers).lower()
    assert "authorization" not in str(candidate.headers).lower()
    assert "secret-token" not in repr(candidate)


def test_expired_media_response_is_discarded():
    class ExpiredResponse(FakeResponse):
        headers = {
            "content-type": "audio/mp4",
            "expires": "Thu, 01 Jan 1970 00:00:00 GMT",
        }

    assert _candidate_from_response(ExpiredResponse()) is None


def test_browser_public_host_guard_uses_a_bounded_dns_deadline(monkeypatch):
    calls = []

    def resolve(host, *, deadline):
        calls.append((host, deadline))
        return ("203.0.113.10",)

    monkeypatch.setattr(capture_module, "resolve_public_addresses", resolve)
    before = time.monotonic()

    _require_public_host("www.douyin.com")

    after = time.monotonic()
    assert len(calls) == 1
    host, deadline = calls[0]
    assert host == "www.douyin.com"
    assert before + 5.0 <= deadline <= after + 5.0


def test_browser_public_host_guard_fails_closed_on_dns_timeout(monkeypatch):
    def timeout(_host, *, deadline):
        assert deadline is not None
        raise UnsupportedUrlError("DNS lookup timed out", "TIMEOUT")

    monkeypatch.setattr(capture_module, "resolve_public_addresses", timeout)

    try:
        _require_public_host("www.douyin.com")
    except CaptureError as exc:
        assert exc.code == "UNSAFE_PAGE_REQUEST"
        assert "timeout" not in str(exc).lower()
    else:
        raise AssertionError("browser DNS timeout must fail closed")


def test_context_request_guard_aborts_loopback_and_routes_allowed_https(monkeypatch):
    class FakeRoute:
        def __init__(self, url, *, navigation=False):
            self.request = SimpleNamespace(
                url=url, is_navigation_request=navigation
            )
            self.action = None

        def abort(self):
            self.action = "abort"

        def continue_(self):
            self.action = "continue"

    resolved = []
    monkeypatch.setattr(
        capture_module,
        "_require_public_host",
        lambda host: resolved.append(host),
    )

    allowed = FakeRoute("https://www.douyin.com/video/123", navigation=True)
    _guard_browser_request(allowed)
    assert allowed.action == "continue"
    assert resolved == ["www.douyin.com"]

    loopback = FakeRoute("http://127.0.0.1:8000/admin", navigation=True)
    _guard_browser_request(loopback)
    assert loopback.action == "abort"
    assert resolved == ["www.douyin.com"]

    unapproved = FakeRoute("https://attacker.example/script.js")
    _guard_browser_request(unapproved)
    assert unapproved.action == "abort"
    assert resolved == ["www.douyin.com"]


def test_websocket_guard_allows_public_wss_and_fails_closed_for_other_targets(
    monkeypatch,
):
    class FakeWebSocketRoute:
        def __init__(self, url):
            self.url = url
            self.connected = False
            self.closed = False

        def connect_to_server(self):
            self.connected = True

        def close(self, *, code, reason):
            self.closed = True
            self.close_args = (code, reason)

    resolved = []

    def require_public(host):
        resolved.append(host)
        if host == "v3-web.douyinvod.com":
            raise CaptureError("UNSAFE_PAGE_REQUEST", "blocked")

    monkeypatch.setattr(capture_module, "_require_public_host", require_public)

    allowed = FakeWebSocketRoute("wss://www.douyin.com/ws")
    _guard_browser_websocket(allowed)
    assert allowed.connected
    assert not allowed.closed
    assert resolved == ["www.douyin.com"]

    cleartext = FakeWebSocketRoute("ws://127.0.0.1:3000/devtools")
    _guard_browser_websocket(cleartext)
    assert not cleartext.connected
    assert cleartext.closed
    assert cleartext.close_args[0] == 1008
    assert resolved == ["www.douyin.com"]

    private_dns = FakeWebSocketRoute("wss://v3-web.douyinvod.com/ws")
    _guard_browser_websocket(private_dns)
    assert not private_dns.connected
    assert private_dns.closed
    assert private_dns.close_args[0] == 1008
    assert resolved == ["www.douyin.com", "v3-web.douyinvod.com"]


def test_candidate_filter_rejects_blob_http_unknown_and_unapproved_hosts():
    class Response(FakeResponse):
        pass

    response = Response()
    response.url = "blob:https://www.douyin.com/video/123/uuid"
    assert _candidate_from_response(response) is None
    response.url = "http://v3-web.douyinvod.com/audio.m4a"
    assert _candidate_from_response(response) is None
    response.url = "https://media.evil.test/audio.m4a"
    assert _candidate_from_response(response) is None
    response.url = "https://v3-web.douyinvod.com/page.html"
    response.headers = {"content-type": "text/html"}
    assert _candidate_from_response(response) is None


def test_playwright_import_is_deferred_until_start(monkeypatch, tmp_path):
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "playwright.sync_api":
            raise AssertionError("Playwright was imported during construction")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    capture = BrowserCapture(tmp_path / "profile")

    assert capture.profile_dir == tmp_path / "profile"
    assert not capture.profile_dir.exists()


class FakeLocator:
    def __init__(self, selector: str):
        self.selector = selector
        self.first = self

    def get_attribute(self, name):
        if self.selector == 'meta[property="og:title"]' and name == "content":
            return "测试视频标题"
        return None

    def inner_text(self, timeout=None):
        if self.selector == "body":
            return "公开视频"
        if self.selector == '[data-e2e="video-desc"]':
            return "测试视频标题"
        raise LookupError

    def count(self):
        return 0

    def evaluate(self, _script):
        raise LookupError


class FakePage:
    def __init__(self):
        self.handlers = {}
        self.route_installed = False
        self.closed = False
        self.url = "https://www.douyin.com/video/123456"

    def route(self, _pattern, _handler):
        self.route_installed = True

    def on(self, event, callback):
        self.handlers[event] = callback

    def set_default_navigation_timeout(self, _timeout):
        pass

    def goto(self, _url, wait_until):
        assert "response" in self.handlers
        self.handlers["response"](FakeResponse())
        return type("NavigationResponse", (), {"status": 200})()

    def wait_for_timeout(self, _timeout):
        pass

    def locator(self, selector):
        return FakeLocator(selector)

    def close(self):
        self.closed = True


def test_listener_is_registered_before_navigation_and_capture_returns_audio_first(
    tmp_path,
):
    class FakeContext:
        def __init__(self):
            self.pages = []
            self.route_handler = None
            self.websocket_handler = None

        def route(self, pattern, handler):
            assert pattern == "**/*"
            self.route_handler = handler

        def route_web_socket(self, pattern, handler):
            assert pattern == "**/*"
            self.websocket_handler = handler

        def new_page(self):
            assert self.route_handler is not None
            assert self.websocket_handler is not None
            page = FakePage()
            self.pages.append(page)
            return page

    context = FakeContext()
    context.route("**/*", _guard_browser_request)
    context.route_web_socket("**/*", _guard_browser_websocket)
    capture = BrowserCapture(tmp_path / "profile")
    capture._context = context
    item = ResolvedInput(
        "https://www.douyin.com/video/123456",
        "https://www.douyin.com/video/123456",
        "123456",
        "direct",
    )

    result = capture.capture(item)

    assert result.video_id == "123456"
    assert result.title == "测试视频标题"
    assert result.media_candidates[0].kind == "audio"
    assert context.pages[0].closed


def test_start_uses_launch_persistent_context_and_passes_profile(monkeypatch, tmp_path):
    calls = []
    context = type(
        "Context",
        (),
        {
            "route": lambda self, pattern, handler: calls.append(("route", pattern, handler)),
            "route_web_socket": lambda self, pattern, handler: calls.append(
                ("websocket", pattern, handler)
            ),
        },
    )()
    fake_playwright = type("Playwright", (), {})()
    fake_playwright.chromium = type(
        "Chromium",
        (),
        {
            "launch_persistent_context": lambda self, path, **kwargs: calls.append(
                (path, kwargs)
            )
            or context
        },
    )()
    fake_instance = type(
        "PlaywrightInstance",
        (),
        {"chromium": fake_playwright.chromium, "stop": lambda self: None},
    )()
    sync_api = ModuleType("playwright.sync_api")
    sync_api.sync_playwright = lambda: type(
        "Factory", (), {"start": lambda self: fake_instance}
    )()
    playwright = ModuleType("playwright")
    playwright.__path__ = []
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)

    profile = tmp_path / "browser-profile"
    capture = BrowserCapture(
        profile,
        headless=True,
        launch_options={"service_workers": "allow"},
    )
    capture.start()

    assert len(calls) == 3
    assert calls[0][0] == str(profile)
    assert calls[0][1]["headless"] is True
    proxy_url = calls[0][1]["proxy"]["server"]
    assert proxy_url.startswith("http://127.0.0.1:")
    assert calls[0][1]["proxy"]["bypass"] == "<-loopback>"
    assert calls[0][1]["service_workers"] == "block"
    assert [call[:2] for call in calls[1:]] == [
        ("route", "**/*"),
        ("websocket", "**/*"),
    ]
    assert capture._proxy is not None
    assert profile.is_dir()
    capture.close()
    assert capture._proxy is None


def test_start_rejects_proxy_override_before_launch(monkeypatch, tmp_path):
    launch_calls = []
    fake_chromium = type(
        "Chromium",
        (),
        {
            "launch_persistent_context": lambda self, path, **kwargs: launch_calls.append(
                (path, kwargs)
            )
        },
    )()
    fake_playwright = type(
        "PlaywrightInstance", (), {"chromium": fake_chromium, "stop": lambda self: None}
    )()
    sync_api = ModuleType("playwright.sync_api")
    sync_api.sync_playwright = lambda: type(
        "Factory", (), {"start": lambda self: fake_playwright}
    )()
    playwright = ModuleType("playwright")
    playwright.__path__ = []
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)

    capture = BrowserCapture(tmp_path / "profile", launch_options={"proxy": {"server": "http://proxy"}})
    try:
        capture.start()
    except CaptureError as exc:
        assert exc.code == "BROWSER_START_FAILED"
    else:
        raise AssertionError("proxy override should be rejected")

    assert launch_calls == []


def test_capture_errors_do_not_include_signed_url():
    class BrokenContext:
        def new_page(self):
            raise RuntimeError("https://cdn.test/video?sig=private")

    capture = BrowserCapture("unused-profile")
    capture._context = BrokenContext()
    item = ResolvedInput("source", "canonical", "123", "direct")

    try:
        capture.capture(item)
    except CaptureError as exc:
        assert "private" not in str(exc)
        assert "cdn.test" not in str(exc)
    else:
        raise AssertionError("capture should fail")
