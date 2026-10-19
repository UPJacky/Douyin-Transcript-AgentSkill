from __future__ import annotations

import builtins
import hashlib
import sys
import time
from types import ModuleType, SimpleNamespace

import pytest

import douyin_transcript.capture as capture_module
import douyin_transcript.urls as urls_module
from douyin_transcript.capture import (
    BrowserCapture,
    CaptureError,
    _candidate_from_response,
    _clean_title,
    _guard_browser_request,
    _guard_browser_websocket,
)
from douyin_transcript.isolation_broker import BrowserIdentity, ProxyEndpoint
from douyin_transcript.urls import ResolvedInput


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


def test_untrusted_page_title_drops_c0_c1_and_bidi_controls():
    cleaned = _clean_title("Title\x1b[31m\x07\x7f\x85\x9b\u202e\tcontinued")

    assert cleaned == "Title[31m continued"
    assert not any(
        ord(character) < 32 or 127 <= ord(character) <= 159 for character in cleaned
    )
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


def test_context_routes_do_not_use_the_local_dns_resolver(monkeypatch):
    def resolver_must_not_run(*_args, **_kwargs):
        raise AssertionError("browser route must leave DNS to the lease proxy")

    monkeypatch.setattr(urls_module.socket, "getaddrinfo", resolver_must_not_run)
    monkeypatch.setattr(urls_module.subprocess, "Popen", resolver_must_not_run)

    class FakeRoute:
        def __init__(self, url, *, navigation=False):
            self.request = type(
                "Request",
                (),
                {
                    "url": url,
                    "is_navigation_request": lambda _self: navigation,
                },
            )()
            self.action = None

        def abort(self):
            self.action = "abort"

        def continue_(self):
            self.action = "continue"

    allowed = FakeRoute("https://www.douyin.com/video/123", navigation=True)
    _guard_browser_request(allowed, deadline=time.monotonic() + 10.0)
    assert allowed.action == "continue"

    allowed_resource = FakeRoute("https://v3-web.douyinvod.com/audio.m4a")
    _guard_browser_request(allowed_resource, deadline=time.monotonic() + 10.0)
    assert allowed_resource.action == "continue"

    media_host_navigation = FakeRoute(
        "https://v3-web.douyinvod.com/video/123", navigation=True
    )
    _guard_browser_request(media_host_navigation)
    assert media_host_navigation.action == "abort"

    loopback = FakeRoute("http://127.0.0.1:8000/admin", navigation=True)
    _guard_browser_request(loopback)
    assert loopback.action == "abort"

    unapproved = FakeRoute("https://attacker.example/script.js")
    _guard_browser_request(unapproved)
    assert unapproved.action == "abort"

    malformed = FakeRoute(
        "https://user:password@www.douyin.com:8443/video/123", navigation=True
    )
    _guard_browser_request(malformed)
    assert malformed.action == "abort"

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

    allowed_websocket = FakeWebSocketRoute("wss://v3-web.douyinvod.com/ws")
    _guard_browser_websocket(allowed_websocket, deadline=time.monotonic() + 10.0)
    assert allowed_websocket.connected
    assert not allowed_websocket.closed

    unapproved_websocket = FakeWebSocketRoute("wss://attacker.example/ws")
    _guard_browser_websocket(unapproved_websocket, deadline=time.monotonic() + 10.0)
    assert not unapproved_websocket.connected
    assert unapproved_websocket.closed
    assert unapproved_websocket.close_args[0] == 1008


@pytest.mark.parametrize("personal", [False, True])
def test_browser_context_guards_share_the_active_capture_deadline(
    monkeypatch, personal
):
    calls = []
    monkeypatch.setattr(
        capture_module,
        "_guard_browser_request",
        lambda route, *, deadline=None, personal=False: calls.append(
            ("request", deadline, personal)
        ),
    )
    monkeypatch.setattr(
        capture_module,
        "_guard_browser_websocket",
        lambda route, *, deadline=None: calls.append(("websocket", deadline)),
    )
    capture = BrowserCapture("unused-profile", personal=personal)
    capture._capture_deadline = 42.0

    capture._guard_request(object())
    capture._guard_websocket(object())

    assert calls == [("request", 42.0, personal), ("websocket", 42.0)]


def test_websocket_route_rejects_invalid_schemes_and_hosts():
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

    allowed = FakeWebSocketRoute("wss://www.douyin.com/ws")
    _guard_browser_websocket(allowed, deadline=time.monotonic() + 10.0)
    assert allowed.connected
    assert not allowed.closed

    cleartext = FakeWebSocketRoute("ws://127.0.0.1:3000/devtools")
    _guard_browser_websocket(cleartext)
    assert not cleartext.connected
    assert cleartext.closed
    assert cleartext.close_args[0] == 1008

    malformed = FakeWebSocketRoute("wss://v3-web.douyinvod.com:444/ws")
    _guard_browser_websocket(malformed, deadline=time.monotonic() + 10.0)
    assert not malformed.connected
    assert malformed.closed
    assert malformed.close_args[0] == 1008


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


def test_candidate_filter_bounds_media_url_and_metadata_header_sizes():
    response = FakeResponse()
    response.url = "https://v3-web.douyinvod.com/" + "x" * (
        capture_module._MAX_CAPTURE_MEDIA_URL_CHARS + 1
    )
    assert _candidate_from_response(response) is None

    response.url = FakeResponse.url
    response.headers = {
        "content-type": "audio/mp4"
        + "x" * capture_module._MAX_CAPTURE_CONTENT_TYPE_CHARS,
    }
    assert _candidate_from_response(response) is None

    response.headers = {
        "content-type": "audio/mp4",
        "expires": "x" * (capture_module._MAX_CAPTURE_EXPIRES_CHARS + 1),
    }
    assert _candidate_from_response(response) is None

    class OversizedRefererRequest(FakeRequest):
        def all_headers(self):
            headers = super().all_headers()
            headers["referer"] = "https://www.douyin.com/" + "x" * (
                capture_module._MAX_CAPTURE_REFERER_CHARS + 1
            )
            return headers

    class OversizedRefererResponse(FakeResponse):
        request = OversizedRefererRequest()

    candidate = _candidate_from_response(OversizedRefererResponse())
    assert candidate is not None
    assert "Referer" not in candidate.headers


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
    def __init__(self, selector: str, timeout_calls=None):
        self.selector = selector
        self.first = self
        self.timeout_calls = timeout_calls if timeout_calls is not None else []

    def get_attribute(self, name, *, timeout=None):
        self.timeout_calls.append(timeout)
        if self.selector == 'meta[property="og:title"]' and name == "content":
            return "测试视频标题"
        return None

    def inner_text(self, timeout=None):
        self.timeout_calls.append(timeout)
        if self.selector == "body":
            return "公开视频"
        if self.selector == '[data-e2e="video-desc"]':
            return "测试视频标题"
        raise LookupError

    def count(self):
        return 0

    def evaluate(self, script, arg=None, *, timeout=None):
        self.timeout_calls.append(timeout)
        if script == capture_module._LOGIN_BODY_SCAN_SCRIPT:
            return False
        if arg is not None:
            if self.selector == 'meta[property="og:title"]':
                return "测试视频标题"
            if self.selector == '[data-e2e="video-author-name"]':
                return "测试作者"
            if self.selector == "body":
                return "公开视频"
            return None
        raise LookupError


class FakePage:
    def __init__(self):
        self.handlers = {}
        self.route_installed = False
        self.closed = False
        self.url = "https://www.douyin.com/video/123456"
        self.default_timeout = None
        self.navigation_timeout = None
        self.timeout_calls = []

    def route(self, _pattern, _handler):
        self.route_installed = True

    def on(self, event, callback):
        self.handlers[event] = callback

    def set_default_timeout(self, timeout):
        self.default_timeout = timeout

    def set_default_navigation_timeout(self, timeout):
        self.navigation_timeout = timeout

    def goto(self, _url, *, wait_until, timeout):
        self.goto_timeout = timeout
        assert "response" in self.handlers
        self.handlers["response"](FakeResponse())
        return type("NavigationResponse", (), {"status": 200})()

    def wait_for_timeout(self, _timeout):
        pass

    def locator(self, selector):
        return FakeLocator(selector, self.timeout_calls)

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
    assert context.pages[0].default_timeout == 1000
    assert context.pages[0].navigation_timeout == 30_000
    assert context.pages[0].goto_timeout == 30_000
    assert all(0 < timeout <= 1000 for timeout in context.pages[0].timeout_calls)


def test_document_title_fallback_ignores_css_visibility_and_removes_topic_tags():
    class TitleLocator(FakeLocator):
        def evaluate(self, script, arg=None, *, timeout=None):
            if self.selector == "title" and "textContent" in script:
                return "新手运营进阶2 #广告运营 #投放 - 抖音"
            return None

    page = SimpleNamespace(locator=lambda selector: TitleLocator(selector))
    title, _author, _date, _duration = capture_module._read_metadata(
        page, time.monotonic() + 10, 1000
    )
    assert title == "新手运营进阶2"


def test_metadata_read_rejects_overlong_title_author_and_publish_date():
    calls = []

    class OversizedLocator(FakeLocator):
        def evaluate(self, script, arg=None, *, timeout=None):
            self.timeout_calls.append(timeout)
            calls.append((self.selector, script, arg))
            if script == capture_module._LOGIN_BODY_SCAN_SCRIPT:
                return False
            if arg is not None and script == capture_module._BOUNDED_ATTRIBUTE_SCRIPT:
                return "x" * (arg["maxChars"] + 50_000)
            if arg is not None and script == capture_module._BOUNDED_DOM_TEXT_SCRIPT:
                return "x" * (arg["maxChars"] + 50_000)
            raise LookupError

    class Page:
        def locator(self, selector):
            return OversizedLocator(selector)

    title, author, publish_date, duration = capture_module._read_metadata(
        Page(),
        deadline=time.monotonic() + 30,
        locator_timeout_ms=1000,
    )

    assert title is None
    assert author is None
    assert publish_date is None
    assert duration is None
    assert calls
    for _selector, script, arg in calls:
        if script in {
            capture_module._BOUNDED_ATTRIBUTE_SCRIPT,
            capture_module._BOUNDED_DOM_TEXT_SCRIPT,
        }:
            assert arg["maxChars"] in {
                capture_module._MAX_CAPTURE_TITLE_CHARS,
                capture_module._MAX_CAPTURE_AUTHOR_CHARS,
                capture_module._MAX_CAPTURE_PUBLISH_DATE_CHARS,
            }
            assert len("x" * (arg["maxChars"] + 50_000)) > arg["maxChars"] + 1
            if script == capture_module._BOUNDED_DOM_TEXT_SCRIPT:
                assert arg["maxNodes"] == capture_module._MAX_DOM_TEXT_NODES


def test_python_metadata_wrappers_cap_unexpected_evaluate_results():
    class OversizedLocator:
        def evaluate(self, _script, _arg=None, *, timeout=None):
            assert timeout == 1000
            return "x" * 50_000

    deadline = time.monotonic() + 5
    text_value = capture_module._read_bounded_dom_text(
        OversizedLocator(),
        max_chars=capture_module._MAX_CAPTURE_TITLE_CHARS,
        deadline=deadline,
        timeout_ms=1000,
    )
    attribute_value = capture_module._read_bounded_attribute(
        OversizedLocator(),
        "content",
        max_chars=capture_module._MAX_CAPTURE_PUBLISH_DATE_CHARS,
        deadline=deadline,
        timeout_ms=1000,
    )

    assert len(text_value) == capture_module._MAX_CAPTURE_TITLE_CHARS + 1
    assert len(attribute_value) == capture_module._MAX_CAPTURE_PUBLISH_DATE_CHARS + 1


def test_login_detection_uses_bounded_scan_instead_of_returning_body_text():
    class BodyLocator:
        def __init__(self, result=False):
            self.result = result

        def count(self):
            return 0

        def evaluate(self, script, arg=None, *, timeout=None):
            assert script == capture_module._LOGIN_BODY_SCAN_SCRIPT
            assert arg == {
                "maxChars": capture_module._MAX_LOGIN_BODY_SCAN_CHARS,
                "maxNodes": capture_module._MAX_DOM_TEXT_NODES,
            }
            assert timeout == 1000
            return self.result

        def inner_text(self, **_kwargs):
            raise AssertionError("the full body text must not be transferred")

    class Page:
        url = "https://www.douyin.com/video/123456"

        def __init__(self, result=False):
            self.result = result

        def locator(self, _selector):
            return BodyLocator(self.result)

    assert not capture_module._login_required(
        Page(), deadline=time.monotonic() + 5, locator_timeout_ms=1000
    )
    assert capture_module._login_required(
        Page(True), deadline=time.monotonic() + 5, locator_timeout_ms=1000
    )


def test_capture_bounds_unique_media_candidates_per_kind(tmp_path):
    class CandidatePage(FakePage):
        def goto(self, _url, *, wait_until, timeout):
            self.goto_timeout = timeout
            for kind, count in (("video", 24), ("audio", 20)):
                for index in range(count):
                    response = FakeResponse()
                    response.url = (
                        f"https://v3-web.douyinvod.com/{kind}-{index}."
                        f"{'mp4' if kind == 'video' else 'm4a'}"
                    )
                    response.headers = {
                        "content-type": "video/mp4" if kind == "video" else "audio/mp4"
                    }
                    self.handlers["response"](response)
            return type("NavigationResponse", (), {"status": 200})()

    class Context:
        def __init__(self):
            self.page = CandidatePage()

        def new_page(self):
            return self.page

    context = Context()
    capture = BrowserCapture(tmp_path / "profile")
    capture._context = context
    item = ResolvedInput(
        "https://www.douyin.com/video/123456",
        "https://www.douyin.com/video/123456",
        "123456",
        "direct",
    )

    result = capture.capture(item)

    assert (
        len(result.media_candidates)
        == 2 * capture_module._MAX_CAPTURE_MEDIA_CANDIDATES_PER_KIND
    )
    assert (
        sum(candidate.kind == "audio" for candidate in result.media_candidates)
        == capture_module._MAX_CAPTURE_MEDIA_CANDIDATES_PER_KIND
    )
    assert (
        sum(candidate.kind == "video" for candidate in result.media_candidates)
        == capture_module._MAX_CAPTURE_MEDIA_CANDIDATES_PER_KIND
    )
    assert result.media_candidates[0].kind == "audio"
    assert context.page.closed


def test_capture_waits_briefly_for_delayed_media_response(monkeypatch, tmp_path):
    clock = [20.0]
    monkeypatch.setattr(
        capture_module,
        "time",
        SimpleNamespace(monotonic=lambda: clock[0]),
    )

    class DelayedCandidatePage(FakePage):
        def __init__(self):
            super().__init__()
            self.wait_calls = []
            self.response_sent = False

        def goto(self, _url, *, wait_until, timeout):
            self.goto_timeout = timeout
            return type("NavigationResponse", (), {"status": 200})()

        def wait_for_timeout(self, timeout):
            self.wait_calls.append(timeout)
            clock[0] += timeout / 1000
            if not self.response_sent and clock[0] >= 20.9:
                self.response_sent = True
                self.handlers["response"](FakeResponse())

    class Context:
        def __init__(self):
            self.page = DelayedCandidatePage()

        def new_page(self):
            return self.page

    context = Context()
    capture = BrowserCapture(tmp_path / "profile", capture_timeout_ms=5_000)
    capture._context = context
    item = ResolvedInput(
        "https://www.douyin.com/video/123456",
        "https://www.douyin.com/video/123456",
        "123456",
        "direct",
    )

    result = capture.capture(item)

    assert len(result.media_candidates) == 1
    assert result.media_candidates[0].kind == "audio"
    assert context.page.wait_calls == [500, 200, 200]
    assert context.page.closed


def test_capture_deadline_bounds_navigation_and_returns_stable_timeout(
    monkeypatch, tmp_path
):
    clock = [10.0]
    monkeypatch.setattr(
        capture_module,
        "time",
        SimpleNamespace(monotonic=lambda: clock[0]),
    )

    class SlowNavigationPage(FakePage):
        def goto(self, _url, *, wait_until, timeout):
            self.goto_timeout = timeout
            clock[0] += timeout / 1000
            return type("NavigationResponse", (), {"status": 200})()

    class Context:
        def __init__(self):
            self.page = SlowNavigationPage()

        def new_page(self):
            return self.page

    context = Context()
    capture = BrowserCapture(
        tmp_path / "profile",
        capture_timeout_ms=500,
        navigation_timeout_ms=30_000,
    )
    capture._context = context
    item = ResolvedInput(
        "https://www.douyin.com/video/123456",
        "https://www.douyin.com/video/123456",
        "123456",
        "direct",
    )

    try:
        capture.capture(item)
    except CaptureError as exc:
        assert exc.code == "CAPTURE_TIMEOUT"
    else:
        raise AssertionError("navigation reaching the capture deadline must time out")

    assert context.page.goto_timeout == 500
    assert context.page.closed


def test_capture_deadline_is_shared_with_login_and_metadata_locators(
    monkeypatch, tmp_path
):
    clock = [20.0]
    monkeypatch.setattr(
        capture_module,
        "time",
        SimpleNamespace(monotonic=lambda: clock[0]),
    )

    class SlowLocator(FakeLocator):
        def evaluate(self, script, arg=None, *, timeout=None):
            assert script in {
                capture_module._LOGIN_BODY_SCAN_SCRIPT,
                capture_module._BOUNDED_DOM_TEXT_SCRIPT,
                capture_module._BOUNDED_ATTRIBUTE_SCRIPT,
            }
            self.timeout_calls.append(timeout)
            clock[0] += timeout / 1000
            raise TimeoutError

    class SlowLocatorPage(FakePage):
        def locator(self, selector):
            return SlowLocator(selector, self.timeout_calls)

    class Context:
        def __init__(self):
            self.page = SlowLocatorPage()

        def new_page(self):
            return self.page

    context = Context()
    capture = BrowserCapture(
        tmp_path / "profile",
        capture_timeout_ms=1500,
        locator_timeout_ms=1000,
    )
    capture._context = context
    item = ResolvedInput(
        "https://www.douyin.com/video/123456",
        "https://www.douyin.com/video/123456",
        "123456",
        "direct",
    )

    try:
        capture.capture(item)
    except CaptureError as exc:
        assert exc.code == "CAPTURE_TIMEOUT"
    else:
        raise AssertionError("metadata lookup must share the navigation deadline")

    assert context.page.timeout_calls == [1000, 500]
    assert context.page.closed


def test_start_fails_closed_without_system_broker_before_playwright_or_chromium(
    monkeypatch, tmp_path
):
    calls = []
    sync_api = ModuleType("playwright.sync_api")
    sync_api.sync_playwright = lambda: calls.append("playwright")
    playwright = ModuleType("playwright")
    playwright.__path__ = []
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)

    profile = tmp_path / "browser-profile"
    capture = BrowserCapture(profile, headless=True)
    try:
        capture.start()
    except CaptureError as exc:
        assert exc.code == "BROWSER_ISOLATION_UNAVAILABLE"
    else:
        raise AssertionError("capture must require the authenticated system broker")

    assert calls == []
    assert not profile.exists()
    assert capture._context is None
    assert capture._lease is None


def test_capture_uses_broker_selected_browser_and_service_endpoint_without_request_fields(
    monkeypatch, tmp_path
):
    events = []
    executable = tmp_path / "chromium-1243" / "chrome.exe"
    executable.parent.mkdir()
    executable.write_bytes(b"broker-selected chromium test fixture")
    identity = BrowserIdentity(
        executable_path=executable,
        executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
        playwright_version="1.2.3",
        chromium_revision="1243",
    )

    class FakeContext:
        def route(self, _pattern, _handler):
            pass

        def route_web_socket(self, _pattern, _handler):
            pass

        def close(self):
            events.append("context")

    class FakeChromium:
        def launch_persistent_context(self, _profile, **options):
            events.append(("launch", options))
            return FakeContext()

    class FakePlaywright:
        chromium = FakeChromium()

        def stop(self):
            events.append("playwright")

    endpoint = ProxyEndpoint("127.0.0.1", 43127)

    class FakeLease:
        browser = identity
        proxy_endpoint = endpoint

        def ensure_active(self):
            events.append("lease_active")

        def close(self):
            events.append("lease")

    class FakeBroker:
        def acquire(self, *args):
            events.append(("acquire", args))
            return FakeLease()

    sync_api = ModuleType("playwright.sync_api")
    sync_api.sync_playwright = lambda: SimpleNamespace(start=lambda: FakePlaywright())
    playwright = ModuleType("playwright")
    playwright.__path__ = []
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)
    monkeypatch.setattr(capture_module, "open_system_broker", lambda: FakeBroker())
    monkeypatch.setattr(
        capture_module.importlib.metadata, "version", lambda _name: "1.2.3"
    )

    capture = BrowserCapture(tmp_path / "profile", headless=True)
    capture.start()
    launch = next(
        event[1]
        for event in events
        if isinstance(event, tuple) and event[0] == "launch"
    )
    assert ("acquire", ()) in events
    assert launch["executable_path"] == str(executable.resolve())
    assert launch["proxy"] == {
        "server": f"http://{endpoint.host}:{endpoint.port}",
        "bypass": "<-loopback>",
    }
    capture.close()

    assert events[-3:] == ["context", "lease", "playwright"]


def test_start_rejects_proxy_override_before_launch(monkeypatch, tmp_path):
    launch_calls = []
    fake_chromium = type(
        "Chromium",
        (),
        {
            "launch_persistent_context": lambda self,
            path,
            **kwargs: launch_calls.append((path, kwargs))
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

    capture = BrowserCapture(
        tmp_path / "profile", launch_options={"proxy": {"server": "http://proxy"}}
    )
    try:
        capture.start()
    except CaptureError as exc:
        assert exc.code == "BROWSER_SECURITY_OVERRIDE"
    else:
        raise AssertionError("proxy override should be rejected")

    assert launch_calls == []


def test_start_rejects_webrtc_policy_override_before_launch(monkeypatch, tmp_path):
    launch_calls = []
    fake_chromium = type(
        "Chromium",
        (),
        {
            "launch_persistent_context": lambda self,
            path,
            **kwargs: launch_calls.append((path, kwargs))
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

    capture = BrowserCapture(
        tmp_path / "profile",
        launch_options={"args": ["--force-webrtc-ip-handling-policy=default"]},
    )
    try:
        capture.start()
    except CaptureError as exc:
        assert exc.code == "BROWSER_SECURITY_OVERRIDE"
    else:
        raise AssertionError("WebRTC policy override should be rejected")

    assert launch_calls == []


def test_start_rejects_executable_override_before_broker_or_launch(tmp_path):
    capture = BrowserCapture(
        tmp_path / "profile",
        launch_options={"executable_path": "C:/unlocked/chrome.exe"},
    )

    try:
        capture.start()
    except CaptureError as exc:
        assert exc.code == "BROWSER_SECURITY_OVERRIDE"
    else:
        raise AssertionError("caller executable_path must not replace locked Chromium")


def test_close_releases_context_then_lease_then_playwright():
    events = []

    class Closeable:
        def __init__(self, name):
            self.name = name

        def close(self):
            events.append(self.name)

    class Playwright(Closeable):
        def stop(self):
            events.append(self.name)

    capture = BrowserCapture("unused-profile")
    capture._context = Closeable("context")
    capture._lease = Closeable("lease")
    capture._playwright = Playwright("playwright")

    capture.close()

    assert events == ["context", "lease", "playwright"]
    assert capture._context is None
    assert capture._lease is None
    assert capture._playwright is None


def test_lost_lease_closes_browser_and_all_capture_resources():
    events = []

    class Context:
        def close(self):
            events.append("context")

    class LostLease:
        def ensure_active(self):
            raise RuntimeError("broker heartbeat was interrupted")

        def close(self):
            events.append("lease")

    class Playwright:
        def stop(self):
            events.append("playwright")

    capture = BrowserCapture("unused-profile")
    capture._context = Context()
    capture._lease = LostLease()
    capture._playwright = Playwright()

    try:
        capture._ensure_lease_active()
    except CaptureError as exc:
        assert exc.code == "BROWSER_ISOLATION_LOST"
    else:
        raise AssertionError("a lost isolation lease must close the browser")

    assert events == ["context", "lease", "playwright"]
    assert capture._context is None
    assert capture._lease is None


def test_route_aborts_when_lease_is_lost_then_capture_closes_browser():
    events = []

    class LostLease:
        def ensure_active(self):
            raise RuntimeError("broker heartbeat was interrupted")

        def close(self):
            events.append("lease")

    class Route:
        aborted = False

        def abort(self):
            self.aborted = True

    class Context:
        def close(self):
            events.append("context")

    capture = BrowserCapture("unused-profile")
    capture._context = Context()
    capture._lease = LostLease()
    route = Route()

    capture._guard_request(route)

    assert route.aborted
    assert capture._lease_lost
    try:
        capture._ensure_lease_active()
    except CaptureError as exc:
        assert exc.code == "BROWSER_ISOLATION_LOST"
    else:
        raise AssertionError("route-detected lease loss must close the browser")

    assert events == ["context", "lease"]
    assert capture._context is None
    assert capture._lease is None


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
