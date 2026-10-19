from __future__ import annotations

import http.client
import socket
import sys
import threading
import time
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import douyin_transcript.downloader as downloader_module
import pytest
from douyin_transcript.capture import MediaCandidate
from douyin_transcript.downloader import (
    DecoderUnavailableError,
    DownloadCancellation,
    DownloadError,
    MediaFile,
    MediaIdentity,
    MediaInvalidError,
    download_media,
    validate_media_file,
)
from douyin_transcript.limits import ResourceLimitError


class FakeSocket:
    def settimeout(self, _timeout):
        pass


class FakeConnection:
    def __init__(self):
        self.sock = FakeSocket()
        self.closed = False

    def close(self):
        self.closed = True


class FakeResponse:
    def __init__(
        self,
        body=b"valid-media",
        *,
        status=200,
        content_type="audio/mp4",
        location=None,
    ):
        self.status = status
        self._body = body
        self._offset = 0
        self._headers = {"Content-Type": content_type}
        if body:
            self._headers["Content-Length"] = str(len(body))
        if location:
            self._headers["Location"] = location
        self.closed = False

    def getheader(self, name, default=None):
        return self._headers.get(name, default)

    def read(self, size):
        chunk = self._body[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def close(self):
        self.closed = True


def candidate(kind="audio", url="https://v3-web.douyinvod.com/media.m4a"):
    return MediaCandidate(url, kind, "audio/mp4" if kind == "audio" else "video/mp4")


def test_download_streams_to_hashed_atomic_file_and_reuses_verified_cache(tmp_path):
    calls = []

    def requester(url, **kwargs):
        calls.append(url)
        return FakeConnection(), FakeResponse(b"audio bytes")

    decoder_calls = []

    def decoder(path: Path):
        decoder_calls.append(path)
        assert path.read_bytes() == b"audio bytes"
        return "mov,mp4,m4a,3gp,3g2,mj2", 4.5

    first = download_media(
        "123456",
        [candidate()],
        tmp_path,
        decoder=decoder,
        requester=requester,
        sleeper=lambda _: None,
    )
    second = download_media(
        "123456",
        [candidate()],
        tmp_path,
        decoder=decoder,
        requester=requester,
        sleeper=lambda _: None,
    )

    assert first == second
    assert first.path.name.startswith("123456-audio-")
    assert first.path.suffix == ".m4a"
    assert first.size_bytes == len(b"audio bytes")
    assert first.duration_seconds == 4.5
    assert calls == [candidate().url]
    assert not list(tmp_path.glob("*.part"))
    assert not list(tmp_path.glob(".*.part"))


def test_download_accepts_mediafile_decoder_and_reuses_verified_cache(tmp_path):
    requests = []
    decoder_paths = []

    def requester(url, **_kwargs):
        requests.append(url)
        return FakeConnection(), FakeResponse(b"validated media")

    def decoder(path: Path):
        decoder_paths.append(path)
        info = path.stat()
        return MediaFile(
            path,
            "mp4",
            info.st_size,
            4.5,
            MediaIdentity.from_stat(info),
        )

    first = download_media(
        "123456",
        [candidate()],
        tmp_path,
        decoder=decoder,
        requester=requester,
        sleeper=lambda _: None,
    )
    second = download_media(
        "123456",
        [candidate()],
        tmp_path,
        decoder=decoder,
        requester=requester,
        sleeper=lambda _: None,
    )

    assert first.path == second.path
    assert first.path.is_file()
    assert decoder_paths[0].name.endswith(".part")
    assert decoder_paths[1] == first.path
    assert first.identity == second.identity
    assert first.identity == MediaIdentity.from_stat(first.path.stat())
    assert requests == [candidate().url]


def test_audio_candidate_is_attempted_before_video(tmp_path):
    calls = []

    def requester(url, **kwargs):
        calls.append(url)
        return FakeConnection(), FakeResponse(b"valid audio")

    result = download_media(
        "10",
        [candidate("video", "https://v3-web.douyinvod.com/video.mp4"), candidate()],
        tmp_path,
        decoder=lambda _: ("mp4", 2.0),
        requester=requester,
        sleeper=lambda _: None,
    )
    assert result.path.name.startswith("10-audio-")
    assert calls == [candidate().url]


def test_materially_short_audio_falls_back_to_video(tmp_path):
    audio = candidate()
    video = candidate("video", "https://v3-web.douyinvod.com/video.mp4")
    calls = []

    def requester(url, **_kwargs):
        calls.append(url)
        return FakeConnection(), FakeResponse(url.encode("ascii"))

    def decoder(path: Path):
        return "mp4", 30.0 if "-audio-" in path.name else 59.5

    result = download_media(
        "123",
        [audio, video],
        tmp_path,
        expected_duration_seconds=60.0,
        decoder=decoder,
        requester=requester,
        retries=0,
        sleeper=lambda _: None,
    )

    assert result.path.name.startswith("123-video-")
    assert calls == [audio.url, video.url]


def test_all_materially_short_candidates_fail_without_caching(tmp_path):
    audio = candidate()
    video = candidate("video", "https://v3-web.douyinvod.com/video.mp4")
    calls = []

    def requester(url, **_kwargs):
        calls.append(url)
        return FakeConnection(), FakeResponse(url.encode("ascii"))

    with pytest.raises(DownloadError) as error:
        download_media(
            "123",
            [audio, video],
            tmp_path,
            expected_duration_seconds=60.0,
            decoder=lambda _path: ("mp4", 20.0),
            requester=requester,
            retries=0,
            sleeper=lambda _: None,
        )

    assert error.value.code == "ALL_MEDIA_CANDIDATES_FAILED"
    assert "audio=MEDIA_INCOMPLETE" in str(error.value)
    assert "video=MEDIA_INCOMPLETE" in str(error.value)
    assert calls == [audio.url, video.url]
    assert not list(tmp_path.glob("123-*-*"))


@pytest.mark.parametrize(
    ("expected", "actual", "accepted"),
    [
        (60.0, 59.4, True),
        (60.0, 59.39, False),
        (1000.0, 995.0, True),
        (1000.0, 994.99, False),
        (10.0, 9.75, True),
        (10.0, 9.74, False),
        (2.0, 1.75, True),
        (2.0, 1.74, False),
    ],
)
def test_expected_duration_tolerance_edges(expected, actual, accepted):
    if accepted:
        result = downloader_module.require_expected_media_duration(actual, expected)
        assert result is None
    else:
        with pytest.raises(DownloadError) as error:
            downloader_module.require_expected_media_duration(actual, expected)
        assert error.value.code == "MEDIA_INCOMPLETE"


def test_unknown_expected_duration_does_not_reject_valid_media():
    assert downloader_module.require_expected_media_duration(1.0, None) is None


@pytest.mark.parametrize("value", [10**400, float("nan"), float("inf"), True])
def test_expected_duration_rejects_invalid_numeric_values(value):
    with pytest.raises(DownloadError) as error:
        downloader_module.require_expected_media_duration(1.0, value)

    assert error.value.code == "MEDIA_INCOMPLETE"


def test_short_cached_media_is_revalidated_and_video_fallback_is_used(tmp_path):
    cached = tmp_path / f"123-audio-{'a' * 16}.m4a"
    cached.write_bytes(b"short cached audio")
    audio = candidate()
    video = candidate("video", "https://v3-web.douyinvod.com/video.mp4")
    calls = []

    def requester(url, **_kwargs):
        calls.append(url)
        return FakeConnection(), FakeResponse(b"candidate media")

    def decoder(path: Path):
        return "mp4", 20.0 if "-audio-" in path.name else 59.5

    result = download_media(
        "123",
        [audio, video],
        tmp_path,
        expected_duration_seconds=60.0,
        decoder=decoder,
        requester=requester,
        retries=0,
        sleeper=lambda _: None,
    )

    assert result.path.name.startswith("123-video-")
    assert calls == [audio.url, video.url]


def test_oversized_cache_entry_is_skipped_before_decoder(tmp_path):
    oversized = tmp_path / f"123-audio-{'b' * 16}.m4a"
    oversized.write_bytes(b"x" * 30)
    decoder_paths = []

    def decoder(path: Path):
        decoder_paths.append(path)
        return "mp4", 1.0

    result = download_media(
        "123",
        [candidate()],
        tmp_path,
        max_bytes=20,
        decoder=decoder,
        requester=lambda *_args, **_kwargs: (FakeConnection(), FakeResponse(b"small")),
        retries=0,
        sleeper=lambda _: None,
    )

    assert result.path != oversized
    assert result.size_bytes == len(b"small")
    assert oversized not in decoder_paths


def test_cache_validation_obeys_shared_total_deadline(tmp_path):
    cached = tmp_path / f"123-audio-{'c' * 16}.m4a"
    cached.write_bytes(b"cached audio")
    requester_calls = []

    def slow_decoder(_path: Path):
        time.sleep(0.04)
        return "mp4", 1.0

    with pytest.raises(DownloadError) as error:
        download_media(
            "123",
            [candidate()],
            tmp_path,
            total_timeout=0.01,
            decoder=slow_decoder,
            requester=lambda *args, **kwargs: requester_calls.append(args),
            retries=0,
            sleeper=lambda _: None,
        )

    assert error.value.code == "TIMEOUT"
    assert requester_calls == []


def test_expired_cache_deadline_prevents_decoder_call(monkeypatch, tmp_path):
    cached = tmp_path / f"123-audio-{'d' * 16}.m4a"
    cached.write_bytes(b"cached audio")
    decoder_calls = []
    monkeypatch.setattr(downloader_module.time, "monotonic", lambda: 11.0)

    with pytest.raises(DownloadError) as error:
        downloader_module._find_valid_cache(
            "123",
            "audio",
            tmp_path,
            lambda path: decoder_calls.append(path) or ("mp4", 1.0),
            max_bytes=1024,
            deadline=10.0,
            expected_duration_seconds=None,
        )

    assert error.value.code == "TIMEOUT"
    assert decoder_calls == []


def test_cache_scan_checks_deadline_without_sorting_directory_entries(
    monkeypatch, tmp_path
):
    clock = [10.0]
    monkeypatch.setattr(
        downloader_module,
        "time",
        SimpleNamespace(monotonic=lambda: clock[0]),
    )

    class SlowEntries:
        def __iter__(self):
            return self

        def __next__(self):
            if getattr(self, "yielded", False):
                raise StopIteration
            self.yielded = True
            clock[0] = 11.0
            return tmp_path / f"123-audio-{'x' * 16}.m4a"

    monkeypatch.setattr(Path, "iterdir", lambda _self: SlowEntries())
    monkeypatch.setattr(
        Path,
        "glob",
        lambda *_args, **_kwargs: pytest.fail("cache discovery must stream entries"),
    )
    decoder_calls = []

    with pytest.raises(DownloadError) as error:
        downloader_module._find_valid_cache(
            "123",
            "audio",
            tmp_path,
            lambda path: decoder_calls.append(path) or ("mp4", 1.0),
            max_bytes=1024,
            deadline=10.5,
            expected_duration_seconds=None,
        )

    assert error.value.code == "TIMEOUT"
    assert decoder_calls == []


def test_expired_cache_deadline_stops_before_download_attempt(monkeypatch, tmp_path):
    cached = tmp_path / f"123-audio-{'g' * 16}.m4a"
    cached.write_bytes(b"cached audio")
    requester_calls = []
    monotonic_values = iter((10.0, 10.5, 10.75, 11.01))
    monkeypatch.setattr(
        downloader_module,
        "time",
        SimpleNamespace(monotonic=lambda: next(monotonic_values)),
    )

    with pytest.raises(DownloadError) as error:
        download_media(
            "123",
            [candidate()],
            tmp_path,
            total_timeout=1.0,
            decoder=lambda _path: pytest.fail(
                "deadline should stop before cache decoding"
            ),
            requester=lambda *args, **_kwargs: requester_calls.append(args),
            retries=0,
        )

    assert error.value.code == "TIMEOUT"
    assert requester_calls == []


def test_cache_directory_with_media_name_is_skipped(tmp_path):
    cache_directory = tmp_path / f"123-audio-{'e' * 16}.m4a"
    cache_directory.mkdir()
    decoder_paths = []

    result = download_media(
        "123",
        [candidate()],
        tmp_path,
        decoder=lambda path: decoder_paths.append(path) or ("mp4", 1.0),
        requester=lambda *_args, **_kwargs: (
            FakeConnection(),
            FakeResponse(b"download"),
        ),
        retries=0,
        sleeper=lambda _: None,
    )

    assert result.path != cache_directory
    assert cache_directory not in decoder_paths


def test_cache_symlink_is_skipped_when_supported(tmp_path):
    outside = tmp_path.parent / f"outside-{tmp_path.name}.m4a"
    outside.write_bytes(b"outside media")
    linked = tmp_path / f"123-audio-{'f' * 16}.m4a"
    try:
        linked.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(
            f"filesystem does not permit symlink creation: {type(exc).__name__}"
        )
    decoder_paths = []

    result = download_media(
        "123",
        [candidate()],
        tmp_path,
        decoder=lambda path: decoder_paths.append(path) or ("mp4", 1.0),
        requester=lambda *_args, **_kwargs: (
            FakeConnection(),
            FakeResponse(b"download"),
        ),
        retries=0,
        sleeper=lambda _: None,
    )

    assert result.path != linked
    assert linked not in decoder_paths


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(b"", content_type="audio/mp4"),
        FakeResponse(b"<!doctype html><html>login</html>", content_type="audio/mp4"),
        FakeResponse(b"page", content_type="text/html"),
    ],
)
def test_empty_and_html_responses_are_rejected_and_part_removed(tmp_path, response):
    with pytest.raises(DownloadError) as error:
        download_media(
            "123",
            [candidate()],
            tmp_path,
            retries=0,
            decoder=lambda _: ("mp4", 3.0),
            requester=lambda *_args, **_kwargs: (FakeConnection(), response),
            sleeper=lambda _: None,
        )
    assert error.value.code == "ALL_MEDIA_CANDIDATES_FAILED"
    assert not list(tmp_path.glob(".*.part"))
    assert not list(tmp_path.glob("123-audio-*"))


def test_candidate_failure_summary_keeps_safe_codes_without_signed_urls(tmp_path):
    audio = candidate("audio", "https://v3-web.douyinvod.com/audio.m4a?token=private")
    video = candidate("video", "https://v3-web.douyinvod.com/video.mp4?sig=private")

    def requester(url, **_kwargs):
        if "/audio." in url:
            return FakeConnection(), FakeResponse(b"", status=403)
        return FakeConnection(), FakeResponse(
            b"<!doctype html>", content_type="video/mp4"
        )

    with pytest.raises(DownloadError) as error:
        download_media(
            "123",
            [audio, video],
            tmp_path,
            decoder=lambda _: ("mp4", 5.0),
            requester=requester,
            retries=0,
            sleeper=lambda _: None,
        )

    assert error.value.code == "ALL_MEDIA_CANDIDATES_FAILED"
    assert "audio=HTTP_STATUS" in str(error.value)
    assert "video=NOT_MEDIA" in str(error.value)
    assert "private" not in str(error.value)


def test_size_limit_is_enforced_before_and_during_download(tmp_path):
    body = b"a" * 30
    with pytest.raises(DownloadError):
        download_media(
            "123",
            [candidate()],
            tmp_path,
            max_bytes=20,
            retries=0,
            decoder=lambda _: ("mp4", 1.0),
            requester=lambda *_args, **_kwargs: (FakeConnection(), FakeResponse(body)),
            sleeper=lambda _: None,
        )
    assert not list(tmp_path.glob(".*.part"))


def test_overlong_download_is_rejected_and_never_cached(tmp_path):
    with pytest.raises(ResourceLimitError) as error:
        download_media(
            "123",
            [candidate()],
            tmp_path,
            max_duration_seconds=60,
            retries=0,
            decoder=lambda _: ("mp4", 61),
            requester=lambda *_args, **_kwargs: (FakeConnection(), FakeResponse()),
            sleeper=lambda _: None,
        )

    assert error.value.code == "MEDIA_TOO_LONG"
    assert not list(tmp_path.glob(".*.part"))
    assert not list(tmp_path.glob("123-audio-*"))


def test_retries_429_and_503_with_bounded_backoff(tmp_path):
    statuses = [503, 429, 200]
    delays = []

    def requester(_url, **kwargs):
        status = statuses.pop(0)
        body = b"ok" if status == 200 else b""
        return FakeConnection(), FakeResponse(body, status=status)

    result = download_media(
        "987",
        [candidate()],
        tmp_path,
        retries=2,
        backoff_base=0.25,
        decoder=lambda _: ("mp4", 1.0),
        requester=requester,
        sleeper=delays.append,
    )
    assert result.size_bytes == 2
    assert delays == [0.25, 0.5]


def test_redirect_to_unapproved_host_is_rejected_before_request(tmp_path):
    urls = []

    def requester(url, **kwargs):
        urls.append(url)
        if len(urls) == 1:
            return FakeConnection(), FakeResponse(
                b"", status=302, location="https://evil.test/file"
            )
        return FakeConnection(), FakeResponse(b"should-not-be-requested")

    with pytest.raises(DownloadError) as error:
        download_media(
            "123",
            [candidate()],
            tmp_path,
            retries=0,
            decoder=lambda _: ("mp4", 1.0),
            requester=requester,
            sleeper=lambda _: None,
        )
    assert error.value.code == "ALL_MEDIA_CANDIDATES_FAILED"
    assert urls == [candidate().url]


def test_total_timeout_interrupts_a_slow_drip_body(tmp_path):
    client, server = socket.socketpair()
    server_errors = []

    class SocketConnection:
        sock = client

        def close(self):
            client.close()

    def send_slow_body():
        try:
            server.sendall(
                b"HTTP/1.1 200 OK\r\nContent-Type: audio/mp4\r\nContent-Length: 6\r\n\r\n"
            )
            for byte in b"abcdef":
                time.sleep(0.07)
                server.sendall(bytes([byte]))
        except OSError as exc:
            server_errors.append(exc)
        finally:
            server.close()

    sender = threading.Thread(target=send_slow_body, daemon=True)
    sender.start()

    def requester(_url, **_kwargs):
        response = http.client.HTTPResponse(client)
        response.begin()
        return SocketConnection(), response

    started = time.monotonic()
    with pytest.raises(DownloadError) as error:
        download_media(
            "123",
            [candidate()],
            tmp_path,
            retries=0,
            connect_timeout=1,
            read_timeout=1,
            total_timeout=0.18,
            decoder=lambda _: pytest.fail("deadline should expire before decoding"),
            requester=requester,
            sleeper=lambda _: None,
        )

    elapsed = time.monotonic() - started
    assert error.value.code == "TIMEOUT"
    assert elapsed < 0.45
    assert not list(tmp_path.glob(".*.part"))
    assert not list(tmp_path.glob("123-audio-*"))
    client.close()
    sender.join(timeout=0.2)


def test_cancellation_interrupts_retry_backoff_without_another_request(tmp_path):
    backoff_started = threading.Event()
    requests = []
    failures = []

    class ObservedCancellation(DownloadCancellation):
        def wait(self, timeout=None):
            backoff_started.set()
            return super().wait(timeout)

    cancellation = ObservedCancellation()

    class RetryResponse(FakeResponse):
        def __init__(self):
            super().__init__(b"", status=503)

    def requester(_url, **_kwargs):
        requests.append("request")
        return FakeConnection(), RetryResponse()

    def download():
        try:
            download_media(
                "123",
                [candidate()],
                tmp_path,
                retries=2,
                total_timeout=10,
                requester=requester,
                cancellation=cancellation,
            )
        except DownloadError as exc:
            failures.append(exc)

    worker = threading.Thread(target=download, daemon=True)
    worker.start()
    assert backoff_started.wait(timeout=2)
    cancellation.cancel()
    worker.join(timeout=1)

    assert not worker.is_alive()
    assert len(requests) == 1
    assert len(failures) == 1
    assert failures[0].code == "CANCELLED"
    assert not list(tmp_path.glob(".*.part"))


def test_linked_child_cancellation_is_scoped_and_parent_cancellation_propagates():
    parent = DownloadCancellation()
    first = parent.linked_child()
    second = parent.linked_child()

    first.cancel()

    assert first.is_set()
    assert not parent.is_set()
    assert not second.is_set()

    parent.cancel()

    assert second.is_set()


def test_total_timeout_is_checked_after_media_validation(tmp_path):
    def slow_decoder(_path: Path):
        time.sleep(0.08)
        return "mp4", 1.0

    with pytest.raises(DownloadError) as error:
        download_media(
            "123",
            [candidate()],
            tmp_path,
            retries=0,
            total_timeout=0.04,
            decoder=slow_decoder,
            requester=lambda *_args, **_kwargs: (FakeConnection(), FakeResponse()),
            sleeper=lambda _: None,
        )

    assert error.value.code == "TIMEOUT"
    assert not list(tmp_path.glob("*.m4a"))
    assert not list(tmp_path.glob(".*.part"))


def test_absolute_deadline_caps_downloader_total_timeout(monkeypatch, tmp_path):
    clock = [100.0]
    deadline = 100.05
    monkeypatch.setattr(
        downloader_module,
        "time",
        SimpleNamespace(monotonic=lambda: clock[0]),
    )
    request_options = []

    def requester(_url, **kwargs):
        request_options.append(kwargs)
        clock[0] = deadline + 0.01
        return FakeConnection(), FakeResponse(b"audio")

    with pytest.raises(DownloadError) as error:
        download_media(
            "123",
            [candidate()],
            tmp_path,
            retries=0,
            total_timeout=10,
            absolute_deadline=deadline,
            decoder=lambda _: pytest.fail("deadline should expire before decoding"),
            requester=requester,
            sleeper=lambda _: None,
        )

    assert error.value.code == "TIMEOUT"
    assert request_options
    assert request_options[0]["timeout"] == pytest.approx(0.05)
    assert not list(tmp_path.glob(".*.part"))
    assert not list(tmp_path.glob("123-audio-*"))


def test_total_timeout_interrupts_slow_response_headers(monkeypatch):
    from douyin_transcript import urls

    base_connection = urls._PinnedHTTPSConnection

    class SocketConnection(base_connection):
        def __init__(self, host, ip_address, *, timeout, deadline=None):
            super().__init__(host, ip_address, timeout=timeout, deadline=deadline)
            self.sock, self._peer = socket.socketpair()
            # This fake skips connect(), which normally bounds socket reads by the deadline.
            remaining = (
                timeout
                if deadline is None
                else min(timeout, deadline - time.monotonic())
            )
            self.sock.settimeout(max(remaining, 0.001))
            self._sender = None

        def request(self, _method, _path, headers=None):
            def send_slow_headers():
                try:
                    self._peer.sendall(b"HTTP/1.1 200 OK\r\nX-Slow: ")
                    for byte in b"header-value\r\nContent-Length: 0\r\n\r\n":
                        time.sleep(0.04)
                        self._peer.sendall(bytes([byte]))
                except OSError:
                    pass
                finally:
                    self._peer.close()

            self._sender = threading.Thread(target=send_slow_headers, daemon=True)
            self._sender.start()

        def getresponse(self):
            response = http.client.HTTPResponse(self.sock)
            response.begin()
            return response

        def close(self):
            super().close()
            try:
                self._peer.close()
            except OSError:
                pass

    monkeypatch.setattr(
        urls,
        "validate_https_url",
        lambda url, **_kwargs: (urlsplit(url), "127.0.0.1"),
    )
    monkeypatch.setattr(urls, "_PinnedHTTPSConnection", SocketConnection)

    started = time.monotonic()
    with pytest.raises((OSError, TimeoutError)):
        urls.open_pinned_https(
            candidate().url,
            allowed_suffixes=frozenset({".douyinvod.com"}),
            timeout=1,
            deadline=started + 0.16,
        )
    assert time.monotonic() - started < 0.45


def test_total_timeout_bounds_dns_resolution(monkeypatch, tmp_path):
    from douyin_transcript import urls

    marker = tmp_path / "resolver-started"
    worker_script = (
        "import pathlib,sys,time; "
        "pathlib.Path(sys.argv[2]).write_text('started', encoding='ascii'); "
        "time.sleep(30)"
    )
    monkeypatch.setattr(
        urls,
        "_dns_worker_command",
        lambda host: [sys.executable, "-I", "-c", worker_script, host, str(marker)],
    )
    stopped: list[int | None] = []
    original_stop = urls._stop_dns_worker

    def track_reaped_worker(process):
        original_stop(process)
        stopped.append(process.returncode)

    monkeypatch.setattr(urls, "_stop_dns_worker", track_reaped_worker)
    started = time.monotonic()
    with pytest.raises(urls.UnsupportedUrlError) as error:
        urls.validate_https_url(
            candidate().url,
            allowed_suffixes=frozenset({".douyinvod.com"}),
            deadline=started + 0.5,
        )

    assert error.value.code == "TIMEOUT"
    assert marker.is_file()
    assert time.monotonic() - started < 1.5
    assert stopped and all(returncode is not None for returncode in stopped)


def test_redirect_hops_share_one_absolute_deadline(monkeypatch, tmp_path):
    from douyin_transcript import downloader

    deadlines = []
    timeouts = []

    def requester(url, *, timeout, deadline, **_kwargs):
        deadlines.append(deadline)
        timeouts.append(timeout)
        if url == candidate().url:
            time.sleep(0.04)
            return FakeConnection(), FakeResponse(
                b"", status=302, location="https://v4-web.douyinvod.com/media.m4a"
            )
        return FakeConnection(), FakeResponse(b"audio")

    monkeypatch.setattr(downloader, "open_pinned_https", requester)
    result = download_media(
        "123",
        [candidate()],
        tmp_path,
        retries=0,
        total_timeout=0.5,
        decoder=lambda _: ("mp4", 1.0),
        sleeper=lambda _: None,
    )

    assert result.size_bytes == 5
    assert len(deadlines) == 2
    assert deadlines[0] == deadlines[1]
    assert timeouts[1] < timeouts[0]


def test_candidate_fallbacks_share_one_absolute_deadline(monkeypatch, tmp_path):
    from douyin_transcript import downloader

    deadlines = []
    calls = []

    def requester(url, *, deadline, **_kwargs):
        deadlines.append(deadline)
        calls.append(url)
        if url == candidate().url:
            return FakeConnection(), FakeResponse(b"", status=404)
        return FakeConnection(), FakeResponse(b"video bytes")

    monkeypatch.setattr(downloader, "open_pinned_https", requester)
    result = download_media(
        "123",
        [candidate(), candidate("video", "https://v4-web.douyinvod.com/video.mp4")],
        tmp_path,
        retries=0,
        total_timeout=0.5,
        decoder=lambda _: ("mp4", 1.0),
        sleeper=lambda _: None,
    )

    assert result.path.name.startswith("123-video-")
    assert len(deadlines) == 2
    assert deadlines[0] == deadlines[1]
    assert calls == [
        candidate().url,
        "https://v4-web.douyinvod.com/video.mp4",
    ]


def test_decoder_is_required_and_its_error_is_not_hidden(tmp_path):
    def unavailable(_path):
        raise DecoderUnavailableError()

    with pytest.raises(DecoderUnavailableError):
        download_media(
            "123",
            [candidate()],
            tmp_path,
            retries=0,
            decoder=unavailable,
            requester=lambda *_args, **_kwargs: (FakeConnection(), FakeResponse()),
            sleeper=lambda _: None,
        )
    assert not list(tmp_path.glob(".*.part"))


def test_public_local_media_validator_checks_file_and_decodable_audio(
    monkeypatch, tmp_path
):
    import os
    import sys
    from types import ModuleType

    class Stream:
        type = "audio"
        duration = 5
        time_base = 1

    class Frame:
        samples = 5
        sample_rate = 1
        pts = 0
        time_base = 1

    class Container:
        streams = [Stream()]
        duration = 5_000_000
        format = type("Format", (), {"name": "wav"})()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def decode(self, _stream):
            return iter([Frame()])

    path = tmp_path / "valid.wav"
    path.write_bytes(b"non-empty")
    opened = []
    checked_identities = []
    av = ModuleType("av")

    def open_media(source, **_kwargs):
        opened.append(source)
        checked_identities.append(MediaIdentity.from_stat(os.fstat(source.fileno())))
        return Container()

    av.open = open_media
    monkeypatch.setitem(sys.modules, "av", av)

    result = validate_media_file(path)

    assert result.path == path
    assert result.format == "wav"
    assert result.size_bytes == len(b"non-empty")
    assert result.duration_seconds == 5.0
    # Compare against the identity captured from the same open handle passed to
    # PyAV. A later path stat can observe different timestamp granularity on
    # Windows even though validation never changed the file.
    assert result.identity == checked_identities[0]
    assert len(opened) == 1
    assert hasattr(opened[0], "read") and hasattr(opened[0], "seek")


def test_media_validator_rejects_mutation_during_decode(monkeypatch, tmp_path):
    import sys
    from types import ModuleType

    path = tmp_path / "changing.wav"
    path.write_bytes(b"original media")

    class Stream:
        type = "audio"
        duration = 1
        time_base = 1

    class Frame:
        samples = 1
        sample_rate = 1
        pts = 0
        time_base = 1

    class Container:
        streams = [Stream()]
        duration = 1_000_000
        format = type("Format", (), {"name": "wav"})()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def decode(self, _stream):
            path.write_bytes(b"changed media content")
            return iter([Frame()])

    av = ModuleType("av")
    av.open = lambda *_args, **_kwargs: Container()
    monkeypatch.setitem(sys.modules, "av", av)

    with pytest.raises(MediaInvalidError) as error:
        validate_media_file(path)

    assert error.value.code == "MEDIA_CHANGED"


def test_media_duration_uses_decoded_samples_when_container_metadata_understates(
    monkeypatch, tmp_path
):
    import sys
    from types import ModuleType

    frames_yielded = []

    class Stream:
        type = "audio"
        duration = 1
        time_base = 1

    class Frame:
        def __init__(self, second):
            self.samples = 1
            self.sample_rate = 1
            self.pts = second
            self.time_base = 1

    class Container:
        streams = [Stream()]
        duration = 1_000_000
        format = type("Format", (), {"name": "wav"})()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def decode(self, _stream):
            for second in range(3):
                frames_yielded.append(second)
                yield Frame(second)

    av = ModuleType("av")
    av.open = lambda *_args, **_kwargs: Container()
    monkeypatch.setitem(sys.modules, "av", av)
    path = tmp_path / "understated.wav"
    path.write_bytes(b"non-empty")

    result = validate_media_file(path, max_duration_seconds=4)

    assert result.duration_seconds == 3.0
    assert frames_yielded == [0, 1, 2]


@pytest.mark.parametrize(
    ("frame_count", "max_duration_seconds", "expected_error"),
    [(2, 3, None), (2, 1.5, "MEDIA_TOO_LONG")],
)
def test_media_duration_uses_decoded_samples_without_duration_metadata(
    monkeypatch, tmp_path, frame_count, max_duration_seconds, expected_error
):
    import sys
    from types import ModuleType

    class Stream:
        type = "audio"
        duration = None
        time_base = None

    class Frame:
        samples = 48_000
        sample_rate = 48_000
        pts = None
        time_base = None

    class Container:
        streams = [Stream()]
        duration = None
        format = type("Format", (), {"name": "wav"})()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def decode(self, _stream):
            return iter(Frame() for _ in range(frame_count))

    av = ModuleType("av")
    av.open = lambda *_args, **_kwargs: Container()
    monkeypatch.setitem(sys.modules, "av", av)
    path = tmp_path / "unknown-duration.wav"
    path.write_bytes(b"non-empty")

    if expected_error is None:
        result = validate_media_file(path, max_duration_seconds=max_duration_seconds)
        assert result.duration_seconds == 2.0
    else:
        with pytest.raises(ResourceLimitError) as error:
            validate_media_file(path, max_duration_seconds=max_duration_seconds)
        assert error.value.code == expected_error


def test_real_vbr_mp3_is_fully_decoded_and_duration_is_measured(tmp_path):
    av = pytest.importorskip("av")
    np = pytest.importorskip("numpy")
    if "libmp3lame" not in av.codecs_available:
        pytest.skip("the installed FFmpeg build has no libmp3lame encoder")

    sample_rate = 44_100
    requested_duration = 8
    path = tmp_path / "variable-bitrate.mp3"
    with av.open(str(path), mode="w", format="mp3") as output:
        stream = output.add_stream("libmp3lame", rate=sample_rate)
        stream.layout = "stereo"
        stream.codec_context.flags |= av.codec.context.Flags.qscale
        stream.codec_context.options = {"qscale": "5"}

        for start in range(0, sample_rate * requested_duration, 1_152):
            count = min(1_152, sample_rate * requested_duration - start)
            seconds = (np.arange(count, dtype=np.float64) + start) / sample_rate
            if start < sample_rate * 2:
                signal = np.zeros(count)
            elif start < sample_rate * 4:
                signal = 0.15 * np.sin(2 * np.pi * 440 * seconds)
            elif start < sample_rate * 6:
                signal = np.random.default_rng(start).normal(0, 0.3, count)
            else:
                signal = 0.8 * np.sin(2 * np.pi * (220 + 500 * (seconds - 6)) * seconds)

            samples = np.clip(signal * 32_767, -32_768, 32_767).astype(np.int16)
            frame = av.AudioFrame.from_ndarray(
                np.stack([samples, samples]), format="s16p", layout="stereo"
            )
            frame.sample_rate = sample_rate
            frame.pts = start
            frame.time_base = Fraction(1, sample_rate)
            for packet in stream.encode(frame):
                output.mux(packet)

        for packet in stream.encode(None):
            output.mux(packet)

    with av.open(str(path)) as encoded:
        packet_sizes = [
            packet.size for packet in encoded.demux(audio=0) if packet.size > 0
        ]

    assert len(set(packet_sizes)) >= 3
    assert max(packet_sizes) >= min(packet_sizes) * 2

    validated = validate_media_file(path)
    assert requested_duration <= validated.duration_seconds <= requested_duration + 0.2


def test_mp4_video_container_with_aac_audio_is_decoded_and_duration_is_measured(
    tmp_path,
):
    av = pytest.importorskip("av")
    np = pytest.importorskip("numpy")
    missing_codecs = {"aac", "mpeg4"} - av.codecs_available
    if missing_codecs:
        pytest.skip("the installed FFmpeg build lacks an MP4 test encoder")

    sample_rate = 48_000
    audio_frame_size = 1_024
    audio_frame_count = 192
    requested_duration = audio_frame_size * audio_frame_count / sample_rate
    video_rate = 10
    video_frame_count = int(requested_duration * video_rate) + 1
    path = tmp_path / "video-with-aac-audio.mp4"

    with av.open(str(path), mode="w", format="mp4") as output:
        video = output.add_stream("mpeg4", rate=video_rate)
        video.width = 64
        video.height = 64
        video.pix_fmt = "yuv420p"
        video.codec_context.max_b_frames = 0

        audio = output.add_stream("aac", rate=sample_rate)
        audio.layout = "stereo"

        next_video_frame = 0
        for audio_index in range(audio_frame_count):
            audio_start = audio_index * audio_frame_size
            audio_time = Fraction(audio_start, sample_rate)
            while (
                next_video_frame < video_frame_count
                and Fraction(next_video_frame, video_rate) <= audio_time
            ):
                pixels = np.full(
                    (64, 64, 3),
                    48 + (next_video_frame % 160),
                    dtype=np.uint8,
                )
                video_frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
                video_frame.pts = next_video_frame
                video_frame.time_base = Fraction(1, video_rate)
                for packet in video.encode(video_frame):
                    output.mux(packet)
                next_video_frame += 1

            seconds = (
                np.arange(audio_frame_size, dtype=np.float64) + audio_start
            ) / sample_rate
            signal = (0.1 * np.sin(2 * np.pi * 440 * seconds)).astype(np.float32)
            audio_frame = av.AudioFrame.from_ndarray(
                np.stack((signal, signal)), format="fltp", layout="stereo"
            )
            audio_frame.sample_rate = sample_rate
            audio_frame.pts = audio_start
            audio_frame.time_base = Fraction(1, sample_rate)
            for packet in audio.encode(audio_frame):
                output.mux(packet)

        for packet in audio.encode(None):
            output.mux(packet)
        for packet in video.encode(None):
            output.mux(packet)

    with av.open(str(path)) as encoded:
        assert any(stream.type == "video" for stream in encoded.streams)
        assert any(stream.type == "audio" for stream in encoded.streams)

    validated = validate_media_file(path)
    assert requested_duration <= validated.duration_seconds <= requested_duration + 0.2


def test_media_validation_rejects_invalid_data_that_ends_the_decode_iterator(
    monkeypatch, tmp_path
):
    import sys
    from types import ModuleType, SimpleNamespace

    class InvalidDataError(Exception):
        pass

    class Stream:
        type = "audio"
        duration = 1
        time_base = 1

    class Frame:
        samples = 1
        sample_rate = 1
        pts = 0
        time_base = 1

    class Container:
        streams = [Stream()]
        duration = 1_000_000
        format = type("Format", (), {"name": "wav"})()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def decode(self, _stream):
            yield Frame()
            raise InvalidDataError("corrupt packet ends the decoder iterator")
            yield Frame()  # pragma: no cover - a closed generator cannot resume

    av = ModuleType("av")
    av.error = SimpleNamespace(InvalidDataError=InvalidDataError)
    av.open = lambda *_args, **_kwargs: Container()
    monkeypatch.setitem(sys.modules, "av", av)
    path = tmp_path / "recoverable-corruption.wav"
    path.write_bytes(b"non-empty")

    with pytest.raises(MediaInvalidError) as error:
        validate_media_file(path, max_duration_seconds=2)

    assert error.value.code == "MEDIA_DECODE_FAILED"


def test_declared_over_limit_media_is_rejected_before_decoding(monkeypatch, tmp_path):
    import sys
    from types import ModuleType

    class Stream:
        type = "audio"
        duration = 3
        time_base = 1

    class Container:
        streams = [Stream()]
        duration = 3_000_000
        format = type("Format", (), {"name": "wav"})()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def decode(self, _stream):
            pytest.fail("declared over-limit duration should stop before decoding")

    av = ModuleType("av")
    av.open = lambda *_args, **_kwargs: Container()
    monkeypatch.setitem(sys.modules, "av", av)
    path = tmp_path / "declared-over-limit.wav"
    path.write_bytes(b"non-empty")

    with pytest.raises(ResourceLimitError) as error:
        validate_media_file(path, max_duration_seconds=2)

    assert error.value.code == "MEDIA_TOO_LONG"


def test_standalone_media_validator_uses_default_one_hour_limit(monkeypatch, tmp_path):
    import sys
    from types import ModuleType

    class Stream:
        type = "audio"
        duration = 3601
        time_base = 1

    class Container:
        streams = [Stream()]
        duration = 3_601_000_000
        format = type("Format", (), {"name": "wav"})()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def decode(self, _stream):
            pytest.fail("default one-hour limit should stop before decoding")

    av = ModuleType("av")
    av.open = lambda *_args, **_kwargs: Container()
    monkeypatch.setitem(sys.modules, "av", av)
    path = tmp_path / "over-default-limit.wav"
    path.write_bytes(b"non-empty")

    with pytest.raises(ResourceLimitError) as error:
        validate_media_file(path)

    assert error.value.code == "MEDIA_TOO_LONG"


def test_media_duration_limit_stops_decode_at_first_over_limit_frame(
    monkeypatch, tmp_path
):
    import sys
    from types import ModuleType

    frames_yielded = []

    class Stream:
        type = "audio"
        duration = 1
        time_base = 1

    class Frame:
        def __init__(self, second):
            self.samples = 1
            self.sample_rate = 1
            self.pts = second
            self.time_base = 1

    class Container:
        streams = [Stream()]
        duration = 1_000_000
        format = type("Format", (), {"name": "wav"})()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def decode(self, _stream):
            for second in range(5):
                frames_yielded.append(second)
                yield Frame(second)

    av = ModuleType("av")
    av.open = lambda *_args, **_kwargs: Container()
    monkeypatch.setitem(sys.modules, "av", av)
    path = tmp_path / "overlong.wav"
    path.write_bytes(b"non-empty")

    with pytest.raises(ResourceLimitError) as error:
        validate_media_file(path, max_duration_seconds=2)

    assert error.value.code == "MEDIA_TOO_LONG"
    assert frames_yielded == [0, 1, 2]


def test_media_validation_denies_nested_decoder_resource_opens(monkeypatch, tmp_path):
    from types import ModuleType

    class Stream:
        type = "audio"
        duration = 1
        time_base = 1

    class Frame:
        samples = 1
        sample_rate = 1
        pts = 0
        time_base = 1

    class Container:
        streams = [Stream()]
        duration = 1_000_000
        format = type("Format", (), {"name": "wav"})()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def decode(self, _stream):
            return iter([Frame()])

    av = ModuleType("av")

    def open_media(_source, *, mode, io_open):
        assert mode == "r"
        assert io_open is downloader_module._deny_nested_media_io
        with pytest.raises(OSError, match="additional media resources"):
            io_open("http://127.0.0.1/private", 0, {})
        return Container()

    av.open = open_media
    monkeypatch.setitem(sys.modules, "av", av)
    path = tmp_path / "valid.wav"
    path.write_bytes(b"non-empty")

    result = validate_media_file(path)

    assert result.duration_seconds == 1


def test_default_download_decoder_enforces_decoded_duration_cap(monkeypatch, tmp_path):
    import sys
    from types import ModuleType

    class Stream:
        type = "audio"
        duration = 1
        time_base = 1

    class Frame:
        def __init__(self, second):
            self.samples = 1
            self.sample_rate = 1
            self.pts = second
            self.time_base = 1

    class Container:
        streams = [Stream()]
        duration = 1_000_000
        format = type("Format", (), {"name": "wav"})()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def decode(self, _stream):
            return iter(Frame(second) for second in range(5))

    av = ModuleType("av")
    av.open = lambda *_args, **_kwargs: Container()
    monkeypatch.setitem(sys.modules, "av", av)

    with pytest.raises(ResourceLimitError) as error:
        download_media(
            "123",
            [candidate()],
            tmp_path,
            max_duration_seconds=2,
            retries=0,
            requester=lambda *_args, **_kwargs: (
                FakeConnection(),
                FakeResponse(b"audio bytes"),
            ),
            sleeper=lambda _delay: None,
        )

    assert error.value.code == "MEDIA_TOO_LONG"
    assert not list(tmp_path.glob(".*.part"))
    assert not list(tmp_path.glob("123-audio-*"))


def test_public_local_media_validator_rejects_missing_and_empty_files(tmp_path):
    with pytest.raises(MediaInvalidError) as missing:
        validate_media_file(tmp_path / "missing.mp4")
    assert missing.value.code == "MEDIA_NOT_FOUND"

    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    with pytest.raises(MediaInvalidError) as error:
        validate_media_file(empty)
    assert error.value.code == "EMPTY_MEDIA"
