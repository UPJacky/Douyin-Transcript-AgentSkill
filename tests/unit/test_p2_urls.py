from __future__ import annotations

import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from douyin_transcript.urls import (
    ResolvedInput,
    UnsupportedUrlError,
    resolve_input,
    resolve_many,
    resolve_public_addresses,
    validate_https_url,
)


def test_direct_video_url_drops_tracking_parameters():
    result = resolve_input(
        "分享视频 https://www.douyin.com/video/123456?from=copy&modal_id=999"
    )

    assert result == ResolvedInput(
        source_url="https://www.douyin.com/video/123456",
        canonical_url="https://www.douyin.com/video/123456",
        video_id="123456",
        source_type="direct",
    )


def test_direct_video_url_accepts_trailing_dot_host():
    result = resolve_input("https://www.douyin.com./video/123456")
    assert result.video_id == "123456"
    assert result.canonical_url == "https://www.douyin.com/video/123456"
    assert result.source_type == "direct"


def test_jingxuan_uses_only_modal_id():
    result = resolve_input("https://www.douyin.com/jingxuan?from=share&modal_id=987654")
    assert result.video_id == "987654"
    assert result.canonical_url.endswith("/video/987654")


@pytest.mark.parametrize(
    "url",
    [
        "",
        "https://www.douyin.com/jingxuan?from=123",
        "https://www.douyin.com/jingxuan?modal_id=123&modal_id=456",
        "https://www.douyin.com/video/abc",
        "http://www.douyin.com/video/123",
        "file:///C:/video.mp4",
        "https://douyin.com.evil.test/video/123",
        "https://user@www.douyin.com/video/123",
        "https://www.douyin.com:8443/video/123",
    ],
)
def test_rejects_unsupported_or_ambiguous_urls(url):
    with pytest.raises(UnsupportedUrlError):
        resolve_input(url)


def test_short_link_follows_bounded_safe_redirects():
    redirects = {
        "https://v.douyin.com/abc/": "https://v.douyin.com/def/",
        "https://v.douyin.com/def/": "https://www.douyin.com/video/123456?from=share",
    }
    result = resolve_input(
        "复制链接 https://v.douyin.com/abc/。",
        redirect_resolver=redirects.__getitem__,
    )
    assert result.source_type == "short_link"
    assert result.video_id == "123456"
    assert result.canonical_url == "https://www.douyin.com/video/123456"


def test_short_link_accepts_trailing_dot_on_redirect_target():
    result = resolve_input(
        "https://v.douyin.com/abc/",
        redirect_resolver=lambda _: "https://www.douyin.com./video/123456",
    )
    assert result.source_type == "short_link"
    assert result.video_id == "123456"


def test_https_url_scheme_is_case_insensitive():
    parsed, address = validate_https_url(
        "HTTPS://V.DOUYIN.COM./abc/",
        allowed_hosts={"v.douyin.com"},
        resolve_dns=False,
    )
    assert parsed.scheme == "https"
    assert address is None


def test_short_link_rejects_external_redirect_and_loop():
    with pytest.raises(UnsupportedUrlError) as unsafe:
        resolve_input(
            "https://v.douyin.com/abc/",
            redirect_resolver=lambda _: "https://127.0.0.1/admin",
        )
    assert unsafe.value.code == "UNSAFE_REDIRECT"

    with pytest.raises(UnsupportedUrlError) as loop:
        resolve_input(
            "https://v.douyin.com/abc/",
            redirect_resolver=lambda value: value,
        )
    assert loop.value.code == "REDIRECT_LOOP"


def test_short_link_redirect_limit_is_enforced():
    count = 0

    def redirect(_):
        nonlocal count
        count += 1
        return f"https://v.douyin.com/{count}/"

    with pytest.raises(UnsupportedUrlError) as error:
        resolve_input(
            "https://v.douyin.com/start/", redirect_resolver=redirect, max_redirects=2
        )
    assert error.value.code == "TOO_MANY_REDIRECTS"
    assert count == 2


def test_short_link_hops_share_one_absolute_deadline(monkeypatch):
    import douyin_transcript.urls as urls

    deadlines = []
    locations = iter(
        [
            "https://v.douyin.com/next/",
            "https://www.douyin.com/video/123456",
        ]
    )

    def request_redirect(_url, *, deadline):
        deadlines.append(deadline)
        return next(locations)

    monkeypatch.setattr(urls, "_request_short_redirect", request_redirect)
    result = resolve_input("https://v.douyin.com/start/")

    assert result.video_id == "123456"
    assert len(deadlines) == 2
    assert deadlines[0] == deadlines[1]


def _use_dns_worker_script(monkeypatch, script: str, *arguments: str) -> None:
    import douyin_transcript.urls as urls

    monkeypatch.setattr(
        urls,
        "_dns_worker_command",
        lambda host: [
            sys.executable,
            "-I",
            "-c",
            script,
            host,
            *(str(argument) for argument in arguments),
        ],
    )


def test_short_link_deadline_bounds_blocked_dns(monkeypatch, tmp_path):
    import douyin_transcript.urls as urls

    started_path = tmp_path / "dns-started"
    script = (
        "import pathlib,sys,time; "
        "pathlib.Path(sys.argv[2]).write_text('started', encoding='ascii'); "
        "time.sleep(30)"
    )
    _use_dns_worker_script(monkeypatch, script, str(started_path))
    monkeypatch.setattr(urls, "SHORT_LINK_TOTAL_TIMEOUT_SECONDS", 1.0)
    stopped: list[int | None] = []
    original_stop = urls._stop_dns_worker

    def track_reaped_worker(process):
        original_stop(process)
        stopped.append(process.returncode)

    monkeypatch.setattr(urls, "_stop_dns_worker", track_reaped_worker)
    started_at = time.monotonic()
    with pytest.raises(UnsupportedUrlError) as error:
        resolve_input("https://v.douyin.com/start/")
    elapsed = time.monotonic() - started_at
    assert error.value.code == "TIMEOUT"
    assert (tmp_path / "dns-started").is_file()
    assert elapsed < 2.5
    assert stopped and all(returncode is not None for returncode in stopped)


def test_two_blocked_dns_workers_are_reaped_and_slots_recover(monkeypatch, tmp_path):
    import douyin_transcript.urls as urls

    started_dir = tmp_path / "started"
    started_dir.mkdir()
    script = """
import json
import pathlib
import sys
import time

host = sys.argv[1]
if host.startswith("hang-"):
    pathlib.Path(sys.argv[2], host + ".started").write_text("yes", encoding="ascii")
    time.sleep(30)
address = "127.0.0.1" if host == "private.example" else "8.8.8.8"
sys.stdout.write(json.dumps({"ok": True, "addresses": [address]}) + "\\n")
"""
    _use_dns_worker_script(monkeypatch, script, str(started_dir))
    reaped: list[int | None] = []
    original_stop = urls._stop_dns_worker

    def track_reaped_worker(process):
        original_stop(process)
        reaped.append(process.returncode)

    monkeypatch.setattr(urls, "_stop_dns_worker", track_reaped_worker)
    cancelled = threading.Event()
    executor = ThreadPoolExecutor(max_workers=2)
    deadline = time.monotonic() + 10.0
    cancel_future = executor.submit(
        resolve_public_addresses,
        "hang-cancel.example",
        deadline=deadline,
        cancellation=cancelled,
    )
    second_cancelled_future = executor.submit(
        resolve_public_addresses,
        "hang-second.example",
        deadline=deadline,
        cancellation=cancelled,
    )
    try:
        marker_deadline = time.monotonic() + 2.0
        while time.monotonic() < marker_deadline:
            if all(
                (started_dir / f"hang-{suffix}.example.started").is_file()
                for suffix in ("cancel", "second")
            ):
                break
            time.sleep(0.01)
        assert (started_dir / "hang-cancel.example.started").is_file()
        assert (started_dir / "hang-second.example.started").is_file()

        cancelled.set()
        with pytest.raises(UnsupportedUrlError) as cancelled_error:
            cancel_future.result(timeout=2)
        with pytest.raises(UnsupportedUrlError) as second_cancelled_error:
            second_cancelled_future.result(timeout=2)
        assert cancelled_error.value.code == "CANCELLED"
        assert second_cancelled_error.value.code == "CANCELLED"

        assert resolve_public_addresses(
            "good.example", deadline=time.monotonic() + 3
        ) == ("8.8.8.8",)
        with pytest.raises(UnsupportedUrlError) as private_error:
            resolve_public_addresses(
                "private.example", deadline=time.monotonic() + 3
            )
        assert private_error.value.code == "UNSAFE_ADDRESS"
        assert len(reaped) >= 4
        assert all(returncode is not None for returncode in reaped)

        assert urls._DNS_LOOKUP_SLOTS.acquire(blocking=False)
        assert urls._DNS_LOOKUP_SLOTS.acquire(blocking=False)
        urls._DNS_LOOKUP_SLOTS.release()
        urls._DNS_LOOKUP_SLOTS.release()
    finally:
        cancelled.set()
        executor.shutdown(wait=True, cancel_futures=True)


def test_resolve_many_deduplicates_video_ids_in_first_seen_order():
    items = resolve_many(
        [
            "https://www.douyin.com/video/10",
            "https://www.douyin.com/jingxuan?modal_id=20&from=share",
            "https://www.douyin.com/video/10?from=other",
        ]
    )
    assert [item.video_id for item in items] == ["10", "20"]


def test_https_validator_rejects_non_public_dns_answer(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
        ],
    )
    with pytest.raises(UnsupportedUrlError) as error:
        validate_https_url(
            "https://v.douyin.com/abc/",
            allowed_hosts={"v.douyin.com"},
        )
    assert error.value.code == "UNSAFE_ADDRESS"


def test_https_validator_returns_validated_public_ip(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))
        ],
    )
    parsed, address = validate_https_url(
        "https://v.douyin.com/abc/",
        allowed_hosts={"v.douyin.com"},
    )
    assert parsed.hostname == "v.douyin.com"
    assert address == "8.8.8.8"
