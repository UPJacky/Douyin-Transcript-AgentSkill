from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

import douyin_transcript.capture as capture_module
import douyin_transcript.personal_capture as personal_module
from douyin_transcript.capture import (
    BrowserCapture,
    CaptureError,
    MediaCandidate,
    VideoMetadata,
)
from douyin_transcript.capture_client import CaptureClientError
from douyin_transcript.capture_ipc import CaptureLimits
from douyin_transcript.downloader import DownloadError, MediaFile
from douyin_transcript.personal_capture import PersonalCaptureClient
from douyin_transcript.storage_security import ensure_private_directory

DIRECT_URL = "https://www.douyin.com/video/123456?share_token=private-share"
SECRET = "https://v3-web.douyinvod.com/audio.mp3?sign=private-signature; cookie=secret"


@pytest.mark.parametrize(
    "host,allowed",
    [
        ("lf-douyin-pc-web.douyinstatic.com", True),
        ("lf-security.bytegoofy.com", True),
        ("lf-c-flwb.bytetos.com", True),
        ("lf-cdn-tos.bytescm.com", True),
        ("douyinstatic.com.attacker.example", False),
        ("127.0.0.1", False),
    ],
)
def test_personal_static_assets_do_not_expand_navigation_or_media_hosts(host, allowed):
    events = []
    route = SimpleNamespace(
        request=SimpleNamespace(
            url=f"https://{host}/asset.js", is_navigation_request=lambda: False
        ),
        continue_=lambda: events.append("continue"),
        abort=lambda: events.append("abort"),
    )
    capture_module._guard_browser_request(route, personal=True)
    assert events == ["continue" if allowed else "abort"]
    events.clear()
    route.request.is_navigation_request = lambda: True
    capture_module._guard_browser_request(route, personal=True)
    assert events == ["abort"]
    candidate = SimpleNamespace(status=200, url=f"https://{host}/video.mp4")
    assert capture_module._candidate_from_response(candidate) is None


def install_playwright_fake(monkeypatch, *, launch_error=None):
    events = []

    class Context:
        def route(self, pattern, handler):
            events.append(("route", pattern, handler))

        def route_web_socket(self, pattern, handler):
            events.append(("websocket", pattern, handler))

        def close(self):
            events.append("context-close")

    def launch(profile, **options):
        events.append(("launch", profile, options))
        if launch_error:
            raise launch_error
        return Context()

    instance = SimpleNamespace(
        chromium=SimpleNamespace(launch_persistent_context=launch),
        stop=lambda: events.append("playwright-stop"),
    )
    sync_api = ModuleType("playwright.sync_api")
    sync_api.sync_playwright = lambda: SimpleNamespace(start=lambda: instance)
    package = ModuleType("playwright")
    package.__path__ = []
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)
    return events


def install_capture_fake(monkeypatch, *, capture_hook=None, download_hook=None):
    events = []

    class Browser:
        def __init__(self, profile, **options):
            self.capture_timeout_ms = options["capture_timeout_ms"]
            events.append(("create", threading.get_ident(), Path(profile), options))

        def __enter__(self):
            events.append(("enter", threading.get_ident()))
            return self

        def __exit__(self, *_args):
            events.append(("close", threading.get_ident()))

        def capture(self, item):
            events.append(
                ("capture", threading.get_ident(), item, self.capture_timeout_ms)
            )
            if capture_hook:
                capture_hook()
            return VideoMetadata(
                item.video_id,
                "测试视频",
                "作者",
                None,
                item.canonical_url,
                2.0,
                [MediaCandidate(SECRET, "audio", "audio/mpeg")],
            )

    def download(video_id, candidates, cache_dir, **options):
        events.append(("download", video_id, list(candidates), options))
        if download_hook:
            download_hook(options)
        cache = ensure_private_directory(cache_dir)
        path = cache / "123456-audio-fixture.mp3"
        path.write_bytes(b"opaque-media-fixture")
        return MediaFile(path, "mp3", path.stat().st_size, 2.0)

    monkeypatch.setattr(personal_module, "BrowserCapture", Browser)
    monkeypatch.setattr(personal_module, "download_media", download)
    return events


def test_personal_browser_uses_bundled_chromium_sandbox_and_guards_without_broker(
    monkeypatch, tmp_path
):
    events = install_playwright_fake(monkeypatch)

    def forbidden_broker():
        pytest.fail("personal capture must not contact the system broker")

    monkeypatch.setattr(capture_module, "open_system_broker", forbidden_broker)
    profile = tmp_path / "profile"
    with BrowserCapture(
        profile,
        personal=True,
        headless=True,
        launch_options={"chromium_sandbox": False},
    ) as browser:
        assert browser._lease is None
        launch = next(
            event
            for event in events
            if isinstance(event, tuple) and event[0] == "launch"
        )
        assert Path(launch[1]) == profile
        assert launch[2]["chromium_sandbox"] is True
        assert launch[2]["headless"] is True
        assert launch[2]["service_workers"] == "block"
        assert "executable_path" not in launch[2]
        assert "proxy" not in launch[2]
        assert any(event[0] == "route" for event in events if isinstance(event, tuple))
        assert any(
            event[0] == "websocket" for event in events if isinstance(event, tuple)
        )
    assert events[-2:] == ["context-close", "playwright-stop"]


def test_default_browser_still_fails_closed_before_playwright(monkeypatch, tmp_path):
    events = install_playwright_fake(monkeypatch)

    def unavailable():
        raise RuntimeError(SECRET)

    monkeypatch.setattr(capture_module, "open_system_broker", unavailable)
    with pytest.raises(CaptureError) as failure:
        BrowserCapture(tmp_path / "strict-profile").start()
    assert failure.value.code == "BROWSER_ISOLATION_UNAVAILABLE"
    assert events == []
    assert not (tmp_path / "strict-profile").exists()


def test_personal_browser_start_failure_stops_playwright_and_hides_exception(
    monkeypatch, tmp_path
):
    events = install_playwright_fake(monkeypatch, launch_error=RuntimeError(SECRET))
    with pytest.raises(CaptureError) as failure:
        BrowserCapture(tmp_path / "profile", personal=True).start()
    assert failure.value.code == "BROWSER_START_FAILED"
    assert SECRET not in str(failure.value)
    assert events[-1] == "playwright-stop"


@pytest.mark.parametrize("options", [{"args": ["--no-sandbox"]}, {"channel": "chrome"}])
def test_personal_browser_rejects_launch_overrides_before_start(tmp_path, options):
    with pytest.raises(CaptureError) as failure:
        BrowserCapture(
            tmp_path / "profile", personal=True, launch_options=options
        ).start()
    assert failure.value.code == "BROWSER_SECURITY_OVERRIDE"


def test_personal_capture_returns_private_artifact_and_passes_download_limits(
    monkeypatch, tmp_path
):
    events = install_capture_fake(monkeypatch)
    client = PersonalCaptureClient(tmp_path / "data", headless=True)
    deadline = time.monotonic() + 20
    limits = CaptureLimits(
        max_media_bytes=128, max_media_duration_seconds=3, max_media_redirects=1
    )

    captured = client.capture(DIRECT_URL, limits=limits, deadline_monotonic=deadline)

    create = next(event for event in events if event[0] == "create")
    assert create[1] == threading.get_ident()
    assert create[2] == tmp_path / "data" / "browser-profile"
    assert create[3]["personal"] is True
    assert create[3]["headless"] is True
    assert 0 < create[3]["launch_options"]["timeout"] <= 20_000
    assert (
        next(event for event in events if event[0] == "close")[1]
        == threading.get_ident()
    )
    assert [event[0] for event in events].index("close") < [
        event[0] for event in events
    ].index("download")
    download = next(event for event in events if event[0] == "download")
    assert download[1] == "123456"
    assert download[3]["max_bytes"] == 128
    assert download[3]["max_duration_seconds"] == 3
    assert download[3]["max_redirects"] == 1
    assert download[3]["expected_duration_seconds"] == 2
    assert download[3]["absolute_deadline"] == deadline
    assert not download[3]["cancellation"].is_set()
    assert captured.video.video_id == "123456"
    assert captured.video.title == "测试视频"
    assert captured.path.parent == (tmp_path / "data" / "media-cache").resolve()
    assert captured.sha256 == hashlib.sha256(b"opaque-media-fixture").hexdigest()
    assert captured.size_bytes == len(b"opaque-media-fixture")
    assert captured.media_type == "audio/mpeg"
    assert "private-share" not in repr(captured)
    assert "private-signature" not in repr(captured)


def test_personal_capture_closes_browser_and_sanitizes_failure_then_releases_lock(
    monkeypatch, tmp_path, caplog
):
    def fail():
        raise CaptureError("CAPTURE_FAILED", SECRET)

    events = install_capture_fake(monkeypatch, capture_hook=fail)
    client = PersonalCaptureClient(tmp_path / "data")
    with pytest.raises(CaptureClientError) as failure:
        client.capture(DIRECT_URL)
    assert failure.value.code == "CAPTURE_FAILED"
    assert SECRET not in str(failure.value)
    assert "private-signature" not in caplog.text
    assert events[-1][0] == "close"
    assert not any(event[0] == "download" for event in events)
    assert client.resolve_source(DIRECT_URL) == "123456"


def test_personal_download_exception_does_not_expose_signed_url(monkeypatch, tmp_path):
    def fail(_options):
        raise DownloadError("DOWNLOAD_FAILED", SECRET)

    events = install_capture_fake(monkeypatch, download_hook=fail)
    with pytest.raises(CaptureClientError) as failure:
        PersonalCaptureClient(tmp_path / "data").capture(DIRECT_URL)
    assert failure.value.code == "DOWNLOAD_FAILED"
    assert SECRET not in str(failure.value)
    assert any(event[0] == "close" for event in events)


def test_personal_client_rejects_concurrent_profile_access_without_waiting(
    monkeypatch, tmp_path
):
    entered = threading.Event()
    release = threading.Event()
    results = []

    def pause():
        entered.set()
        assert release.wait(5)

    events = install_capture_fake(monkeypatch, capture_hook=pause)
    client = PersonalCaptureClient(tmp_path / "data")

    def run():
        try:
            results.append(client.capture(DIRECT_URL))
        except BaseException as error:
            results.append(error)

    worker = threading.Thread(target=run)
    worker.start()
    try:
        assert entered.wait(5)
        with pytest.raises(CaptureClientError) as failure:
            client.capture(DIRECT_URL)
        assert failure.value.code == "CAPTURE_BUSY"
        with pytest.raises(CaptureClientError) as failure:
            client.resolve_source(DIRECT_URL)
        assert failure.value.code == "CAPTURE_BUSY"
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
    assert len(results) == 1 and not isinstance(results[0], BaseException)
    browser_threads = {
        event[1] for event in events if event[0] in {"create", "capture", "close"}
    }
    assert browser_threads == {worker.ident}
    assert client.resolve_source(DIRECT_URL) == "123456"


def test_personal_clients_share_data_directory_lock(monkeypatch, tmp_path):
    entered = threading.Event()
    release = threading.Event()
    results = []

    def pause():
        entered.set()
        assert release.wait(5)

    events = install_capture_fake(monkeypatch, capture_hook=pause)
    first = PersonalCaptureClient(tmp_path / "shared-data")
    second = PersonalCaptureClient(tmp_path / "shared-data")

    def run():
        try:
            results.append(first.capture(DIRECT_URL))
        except BaseException as error:
            results.append(error)

    worker = threading.Thread(target=run)
    worker.start()
    try:
        assert entered.wait(5)
        with pytest.raises(CaptureClientError) as failure:
            second.capture(DIRECT_URL)
        assert failure.value.code == "CAPTURE_BUSY"
        assert "数据目录" in str(failure.value)
    finally:
        release.set()
        worker.join(5)

    assert not worker.is_alive()
    assert len(results) == 1 and not isinstance(results[0], BaseException)
    assert len([event for event in events if event[0] == "create"]) == 1
    assert second.resolve_source(DIRECT_URL) == "123456"


def test_personal_login_and_capture_share_data_directory_lock(monkeypatch, tmp_path):
    entered = threading.Event()
    release = threading.Event()
    closed = []
    events = install_capture_fake(monkeypatch)
    original_browser = personal_module.BrowserCapture

    class Page:
        def goto(self, _url, **_options):
            return None

    class Context:
        pages = [Page()]

        def on(self, event, callback):
            assert event == "close"
            self.callback = callback

        def wait_for_event(self, event, *, timeout):
            assert event == "close" and timeout > 0
            entered.set()
            assert release.wait(5)
            self.callback()

    class Browser(original_browser):
        def __init__(self, profile, **options):
            if options.get("headless") is False:
                self.context = Context()
                self.capture_timeout_ms = 10_000
                self.profile = profile
                self.options = options
            else:
                super().__init__(profile, **options)

        def _require_context(self):
            return self.context

        def __exit__(self, *_args):
            closed.append(threading.get_ident())
            return None

    monkeypatch.setattr(personal_module, "BrowserCapture", Browser)
    client = PersonalCaptureClient(tmp_path / "shared-data")
    outcomes = []

    def login():
        try:
            client.login(timeout_seconds=5)
            outcomes.append("login-ok")
        except BaseException as error:
            outcomes.append(error)

    worker = threading.Thread(target=login)
    worker.start()
    try:
        assert entered.wait(5)
        with pytest.raises(CaptureClientError) as failure:
            PersonalCaptureClient(tmp_path / "shared-data").capture(DIRECT_URL)
        assert failure.value.code == "CAPTURE_BUSY"
        assert not any(event[0] == "create" for event in events)
    finally:
        release.set()
        worker.join(5)

    assert not worker.is_alive()
    assert outcomes == ["login-ok"]
    assert len(closed) == 1
    assert (
        PersonalCaptureClient(tmp_path / "shared-data").resolve_source(DIRECT_URL)
        == "123456"
    )


def test_resolution_reuses_bounded_short_link_resolver_and_returns_only_id(
    monkeypatch, tmp_path
):
    observed = []
    deadline = time.monotonic() + 10

    def redirect(url, *, deadline, cancellation, allow_proxy_dns):
        observed.append((url, deadline, cancellation, allow_proxy_dns))
        return DIRECT_URL

    monkeypatch.setattr(personal_module, "_request_short_redirect", redirect)
    result = PersonalCaptureClient(tmp_path).resolve_source(
        "https://v.douyin.com/fixture/?token=private-share",
        max_short_link_redirects=1,
        deadline_monotonic=deadline,
    )
    assert result == "123456"
    assert len(observed) == 1
    assert observed[0][1] <= deadline
    assert observed[0][2].is_set() is False
    assert observed[0][3] is True


@pytest.mark.parametrize("cancelled", [True, "callback_failure"])
def test_precancelled_capture_never_creates_browser(monkeypatch, tmp_path, cancelled):
    events = install_capture_fake(monkeypatch)

    def callback():
        if cancelled == "callback_failure":
            raise RuntimeError(SECRET)
        return cancelled

    with pytest.raises(CaptureClientError) as failure:
        PersonalCaptureClient(tmp_path / "data").capture(
            DIRECT_URL, is_cancelled=callback
        )
    assert failure.value.code == "CANCELLED"
    assert events == []


def test_download_observes_cancellation_callback(monkeypatch, tmp_path):
    cancelled = False

    def cancel(options):
        nonlocal cancelled
        cancelled = True
        assert options["cancellation"].is_set()
        assert options["cancellation"].wait(0)
        raise DownloadError("CANCELLED", SECRET)

    install_capture_fake(monkeypatch, download_hook=cancel)
    client = PersonalCaptureClient(tmp_path / "data")
    with pytest.raises(CaptureClientError) as failure:
        client.capture(DIRECT_URL, is_cancelled=lambda: cancelled)
    assert failure.value.code == "CANCELLED"
    assert client.resolve_source(DIRECT_URL) == "123456"


_CHILD_LOCK_SCRIPT = r"""
import sys, time
from douyin_transcript.personal_capture import PersonalCaptureClient
from douyin_transcript.capture_client import CaptureClientError
client = PersonalCaptureClient(sys.argv[1])
try:
    with client._operation():
        print('ACQUIRED', flush=True)
        time.sleep(float(sys.argv[2]))
except CaptureClientError as exc:
    print(exc.code, flush=True)
    raise SystemExit(0 if exc.code == 'CAPTURE_BUSY' else 3)
"""


def _start_lock_process(data_dir: Path, *, hold_seconds: float):
    source_root = str(Path(personal_module.__file__).parents[1])
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        source_root if not existing else source_root + os.pathsep + existing
    )
    return subprocess.Popen(
        [sys.executable, "-c", _CHILD_LOCK_SCRIPT, str(data_dir), str(hold_seconds)],
        cwd=Path(__file__).parents[2],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_personal_capture_lock_is_exclusive_across_processes_and_released_on_exit(
    tmp_path,
):
    data_dir = tmp_path / "process-shared-data"
    holder = _start_lock_process(data_dir, hold_seconds=30)
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "ACQUIRED"
        contender = subprocess.run(
            [
                sys.executable,
                "-c",
                _CHILD_LOCK_SCRIPT,
                str(data_dir),
                "0",
            ],
            cwd=Path(__file__).parents[2],
            env=holder_env(data_dir),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert contender.returncode == 0
        assert contender.stdout.strip() == "CAPTURE_BUSY"
    finally:
        holder.terminate()
        holder.wait(timeout=10)
        if holder.stdout:
            holder.stdout.close()
        if holder.stderr:
            holder.stderr.close()

    assert (data_dir / ".personal-capture.lock").is_file()
    released = subprocess.run(
        [sys.executable, "-c", _CHILD_LOCK_SCRIPT, str(data_dir), "0"],
        cwd=Path(__file__).parents[2],
        env=holder_env(data_dir),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert released.returncode == 0
    assert released.stdout.strip() == "ACQUIRED"


def holder_env(_data_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    source_root = str(Path(personal_module.__file__).parents[1])
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        source_root if not existing else source_root + os.pathsep + existing
    )
    return env


def test_personal_capture_locks_allow_separate_data_directories(tmp_path):
    first = _start_lock_process(tmp_path / "data-one", hold_seconds=30)
    second = _start_lock_process(tmp_path / "data-two", hold_seconds=30)
    try:
        assert (
            first.stdout is not None and first.stdout.readline().strip() == "ACQUIRED"
        )
        assert (
            second.stdout is not None and second.stdout.readline().strip() == "ACQUIRED"
        )
    finally:
        for process in (first, second):
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()


def test_resolution_keeps_cancelled_classification_across_resolver_boundary(
    monkeypatch, tmp_path
):
    cancelled = False

    def redirect(_url, *, deadline, cancellation, allow_proxy_dns):
        nonlocal cancelled
        cancelled = True
        return DIRECT_URL

    monkeypatch.setattr(personal_module, "_request_short_redirect", redirect)
    with pytest.raises(CaptureClientError) as failure:
        PersonalCaptureClient(tmp_path).resolve_source(
            "https://v.douyin.com/fixture/", is_cancelled=lambda: cancelled
        )
    assert failure.value.code == "CANCELLED"


def test_personal_requester_opts_into_fake_ip_and_forwards_deadline_cancellation(
    monkeypatch, tmp_path
):
    observed = []
    deadline = time.monotonic() + 20

    def pinned(url, **options):
        observed.append((url, options))
        return object(), object()

    def request(options):
        options["requester"](
            "https://v3-web.douyinvod.com/audio.mp3?sign=private-signature",
            allowed_suffixes=frozenset({".douyinvod.com"}),
            timeout=7,
            headers={"Accept": "audio/mpeg"},
        )
        assert observed[-1][1]["cancellation"] is options["cancellation"]

    monkeypatch.setattr(personal_module, "open_pinned_https", pinned)
    install_capture_fake(monkeypatch, download_hook=request)
    PersonalCaptureClient(tmp_path / "data").capture(
        DIRECT_URL, deadline_monotonic=deadline
    )
    assert len(observed) == 1
    options = observed[0][1]
    assert options["allow_proxy_dns"] is True
    assert options["deadline"] == deadline
    assert options["timeout"] == 7
    assert options["allowed_suffixes"] == frozenset({".douyinvod.com"})
    assert options["headers"] == {"Accept": "audio/mpeg"}


def test_aggregate_download_failure_retains_only_fixed_candidate_reason_codes(
    monkeypatch, tmp_path, caplog
):
    def fail(_options):
        raise DownloadError(
            "ALL_MEDIA_CANDIDATES_FAILED",
            "audio=UNSAFE_ADDRESS, video=HTTP_STATUS, audio=COOKIE_SECRET; " + SECRET,
        )

    install_capture_fake(monkeypatch, download_hook=fail)
    with pytest.raises(CaptureClientError) as failure:
        PersonalCaptureClient(tmp_path / "data").capture(DIRECT_URL)
    assert failure.value.code == "DOWNLOAD_FAILED"
    assert str(failure.value) == (
        "所有音视频候选均下载或校验失败（候选原因：audio=UNSAFE_ADDRESS，video=HTTP_STATUS）"
    )
    assert "COOKIE_SECRET" not in str(failure.value)
    assert "private-signature" not in str(failure.value)
    assert SECRET not in caplog.text


def test_expired_deadline_never_creates_browser(monkeypatch, tmp_path):
    events = install_capture_fake(monkeypatch)
    with pytest.raises(CaptureClientError) as failure:
        PersonalCaptureClient(tmp_path).capture(
            DIRECT_URL, deadline_monotonic=time.monotonic() - 1
        )
    assert failure.value.code == "CAPTURE_TIMEOUT"
    assert events == []


@pytest.mark.parametrize(
    "limits",
    [
        CaptureLimits(max_media_bytes=True),
        CaptureLimits(max_media_bytes=0),
        CaptureLimits(max_media_duration_seconds=float("nan")),
        CaptureLimits(max_short_link_redirects=6),
        CaptureLimits(max_media_redirects=-1),
    ],
)
def test_invalid_limits_never_create_browser(monkeypatch, tmp_path, limits):
    events = install_capture_fake(monkeypatch)
    with pytest.raises(CaptureClientError) as failure:
        PersonalCaptureClient(tmp_path).capture(DIRECT_URL, limits=limits)
    assert failure.value.code == "INVALID_LIMITS"
    assert events == []


@pytest.mark.parametrize(
    "url", ["https://127.0.0.1/video/123456", "https://example.com/video/123456"]
)
def test_personal_resolver_rejects_non_douyin_urls_without_network(tmp_path, url):
    with pytest.raises(CaptureClientError) as failure:
        PersonalCaptureClient(tmp_path).resolve_source(url)
    assert failure.value.code == "INVALID_URL"


@pytest.mark.parametrize("timed_out", [False, True])
def test_manual_login_reuses_personal_profile_and_closes_on_user_close_or_timeout(
    monkeypatch, tmp_path, timed_out
):
    events = []
    handlers = {}

    class Page:
        def goto(self, url, **options):
            events.append(("goto", url, options))

    class Context:
        pages = [Page()]

        def on(self, event, handler):
            handlers[event] = handler

        def wait_for_event(self, event, *, timeout):
            events.append(("wait", event, timeout))
            if timed_out:
                raise TimeoutError(SECRET)
            handlers["close"]()

    class Browser:
        def __init__(self, profile, **options):
            events.append(("create", Path(profile), options, threading.get_ident()))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            events.append(("close", threading.get_ident()))

        def _require_context(self):
            return Context()

    monkeypatch.setattr(personal_module, "BrowserCapture", Browser)
    client = PersonalCaptureClient(tmp_path / "data")
    if timed_out:
        with pytest.raises(CaptureClientError) as failure:
            client.login(timeout_seconds=2)
        assert failure.value.code == "LOGIN_TIMEOUT"
        assert SECRET not in str(failure.value)
    else:
        assert client.login(timeout_seconds=2) is None
    assert events[0][1] == tmp_path / "data" / "browser-profile"
    assert events[0][2]["personal"] is True
    assert events[0][2]["headless"] is False
    assert events[0][3] == threading.get_ident()
    assert (
        next(event for event in events if event[0] == "goto")[1]
        == "https://www.douyin.com/"
    )
    assert 0 < next(event for event in events if event[0] == "wait")[2] <= 2_000
    assert events[-1] == ("close", threading.get_ident())
    assert client.resolve_source(DIRECT_URL) == "123456"
