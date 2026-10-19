from __future__ import annotations

import hashlib
import io
import math
import uuid

import pytest

from douyin_transcript.capture_client import CaptureClientError, CaptureServiceClient
from douyin_transcript.capture_ipc import (
    CaptureFailureCode,
    CaptureLimits,
    CaptureMediaArtifact,
    CaptureRequest,
    CaptureResolveFailure,
    CaptureResolveSuccess,
    CaptureResultFailure,
    CaptureResultSuccess,
    CaptureVideoMetadata,
    decode_capture_request,
    decode_capture_resolve_request,
    encode_capture_resolve_result,
    encode_capture_result,
)
from douyin_transcript.storage_security import inspect_private_path


class FakeExchange:
    def __init__(self, result_frame: bytes, media_stream=None, *, close_error=None):
        self.result_frame = result_frame
        self.media_stream = media_stream
        self.close_error = close_error
        self.closed = False

    def close(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


class FakeTransport:
    def __init__(self, exchange=None, *, error=None):
        self.exchange_value = exchange
        self.error = error
        self.request_frame = None
        self.deadline = None
        self.is_cancelled = None

    def exchange(self, request_frame, *, deadline_monotonic, is_cancelled):
        self.request_frame = request_frame
        self.deadline = deadline_monotonic
        self.is_cancelled = is_cancelled
        if self.error is not None:
            raise self.error
        return self.exchange_value


class FactoryTransport(FakeTransport):
    def __init__(self, exchange_factory):
        super().__init__()
        self.exchange_factory = exchange_factory

    def exchange(self, request_frame, *, deadline_monotonic, is_cancelled):
        self.request_frame = request_frame
        self.deadline = deadline_monotonic
        self.is_cancelled = is_cancelled
        self.exchange_value = self.exchange_factory(
            decode_capture_request(request_frame)
        )
        return self.exchange_value


class ResolveFactoryTransport(FakeTransport):
    def __init__(self, exchange_factory):
        super().__init__()
        self.exchange_factory = exchange_factory

    def exchange(self, request_frame, *, deadline_monotonic, is_cancelled):
        self.request_frame = request_frame
        self.deadline = deadline_monotonic
        self.is_cancelled = is_cancelled
        request = decode_capture_resolve_request(request_frame)
        self.exchange_value = self.exchange_factory(request)
        return self.exchange_value


def make_success(request: CaptureRequest, media: bytes) -> CaptureResultSuccess:
    return CaptureResultSuccess(
        request_id=request.request_id,
        video=CaptureVideoMetadata("123456", "演示标题", "作者", None, 2.0),
        media_artifact=CaptureMediaArtifact(
            uuid.uuid4(),
            hashlib.sha256(media).hexdigest(),
            len(media),
            "audio/mpeg",
            2.0,
        ),
    )


def test_capture_client_sends_original_url_and_receives_bound_private_artifact(
    tmp_path,
):
    url = "https://v.douyin.com/example/"
    media = b"opaque media bytes"
    transport = FactoryTransport(
        lambda request: FakeExchange(
            encode_capture_result(make_success(request, media)), io.BytesIO(media)
        )
    )
    client = CaptureServiceClient(transport, tmp_path / "media-cache")

    captured = client.capture(url, limits=CaptureLimits(max_media_bytes=128))

    sent_request = decode_capture_request(transport.request_frame)
    assert sent_request.original_url == url
    assert sent_request.request_id != uuid.UUID(int=0)
    assert captured.video.video_id == "123456"
    assert captured.path.read_bytes() == media
    assert captured.size_bytes == len(media)
    assert captured.sha256 == hashlib.sha256(media).hexdigest()
    assert captured.media_type == "audio/mpeg"
    assert inspect_private_path(captured.path).status == "private"
    assert transport.exchange_value.closed


def test_capture_client_resolves_short_link_before_capture_without_media(tmp_path):
    url = "https://v.douyin.com/example/?share_token=secret"
    transport = ResolveFactoryTransport(
        lambda request: FakeExchange(
            encode_capture_resolve_result(
                CaptureResolveSuccess(request.request_id, "123456")
            )
        )
    )

    video_id = CaptureServiceClient(transport, tmp_path / "cache").resolve_source(url)

    request = decode_capture_resolve_request(transport.request_frame)
    assert request.original_url == url
    assert request.request_id != uuid.UUID(int=0)
    assert video_id == "123456"
    assert transport.exchange_value.media_stream is None
    assert transport.exchange_value.closed
    assert not (tmp_path / "cache").exists()


def test_capture_client_preserves_resolve_failure_code_and_retryability(tmp_path):
    transport = ResolveFactoryTransport(
        lambda request: FakeExchange(
            encode_capture_resolve_result(
                CaptureResolveFailure(
                    request.request_id, CaptureFailureCode.NETWORK_ERROR
                )
            )
        )
    )

    with pytest.raises(CaptureClientError) as error:
        CaptureServiceClient(transport, tmp_path / "cache").resolve_source(
            "https://v.douyin.com/example/"
        )

    assert error.value.code == "NETWORK_ERROR"
    assert error.value.retryable is True
    assert transport.exchange_value.closed


def test_capture_client_maps_worker_failure_without_exposing_request_details(tmp_path):
    url = "https://www.douyin.com/video/123456?secret=not-for-output"
    transport = FactoryTransport(
        lambda request: FakeExchange(
            encode_capture_result(
                CaptureResultFailure(
                    request.request_id, CaptureFailureCode.CAPTURE_NO_MEDIA
                )
            )
        )
    )
    client = CaptureServiceClient(transport, tmp_path / "cache")

    with pytest.raises(CaptureClientError) as error:
        client.capture(url)

    assert error.value.code == "CAPTURE_NO_MEDIA"
    assert "secret" not in str(error.value)
    assert transport.exchange_value.closed
    assert not (tmp_path / "cache").exists()


def test_capture_client_rejects_wrong_request_and_closes_exchange(tmp_path):
    url = "https://www.douyin.com/video/123456"
    transport = FactoryTransport(
        lambda _request: FakeExchange(
            encode_capture_result(
                CaptureResultFailure(uuid.uuid4(), CaptureFailureCode.CAPTURE_TIMEOUT)
            )
        )
    )

    with pytest.raises(CaptureClientError) as error:
        CaptureServiceClient(transport, tmp_path / "cache").capture(url)

    assert error.value.code == "INVALID_RESULT"
    assert transport.exchange_value.closed


def test_capture_client_cleans_artifact_if_exchange_close_fails(tmp_path):
    url = "https://www.douyin.com/video/123456"
    media = b"opaque media bytes"
    transport = FactoryTransport(
        lambda request: FakeExchange(
            encode_capture_result(make_success(request, media)),
            io.BytesIO(media),
            close_error=OSError("secret endpoint"),
        )
    )

    with pytest.raises(CaptureClientError) as error:
        CaptureServiceClient(transport, tmp_path / "cache").capture(url)

    assert error.value.code == "CAPTURE_TRANSPORT_CLOSE_FAILED"
    assert "secret endpoint" not in str(error.value)
    assert transport.exchange_value.closed
    assert not list((tmp_path / "cache").glob("*.mp3"))
    assert not list((tmp_path / "cache").glob("*.part"))


def test_capture_client_sanitizes_transport_errors(tmp_path):
    client = CaptureServiceClient(
        FakeTransport(error=OSError("pipe name leaked")), tmp_path / "cache"
    )

    with pytest.raises(CaptureClientError) as error:
        client.capture("https://www.douyin.com/video/123456")

    assert error.value.code == "CAPTURE_TRANSPORT_FAILED"
    assert "pipe name leaked" not in str(error.value)


def test_capture_client_validates_limits_timeout_and_url(tmp_path):
    with pytest.raises(ValueError):
        CaptureServiceClient(FakeTransport(), tmp_path / "cache", timeout_seconds=0)
    with pytest.raises(ValueError):
        CaptureServiceClient(
            FakeTransport(), tmp_path / "cache", timeout_seconds=math.nan
        )

    client = CaptureServiceClient(FakeTransport(), tmp_path / "cache")
    with pytest.raises(CaptureClientError) as error:
        client.capture("http://www.douyin.com/video/123456")
    assert error.value.code == "INVALID_URL"

    with pytest.raises(CaptureClientError) as error:
        client.capture("https://www.douyin.com/video/123456", deadline_monotonic=0)
    assert error.value.code == "CAPTURE_TIMEOUT"

    transport = FakeTransport()
    with pytest.raises(CaptureClientError) as error:
        CaptureServiceClient(transport, tmp_path / "cache").capture(
            "https://www.douyin.com/video/123456", deadline_monotonic=math.inf
        )
    assert error.value.code == "CAPTURE_TIMEOUT"
    assert transport.request_frame is None

    transport = FakeTransport()
    with pytest.raises(CaptureClientError) as error:
        CaptureServiceClient(transport, tmp_path / "cache").capture(
            "https://www.douyin.com/video/123456", is_cancelled=lambda: True
        )
    assert error.value.code == "CANCELLED"
    assert transport.request_frame is None


@pytest.mark.parametrize(
    ("operation", "transport_error", "expected_code"),
    [
        ("capture", TimeoutError(), "CAPTURE_TIMEOUT"),
        ("capture", InterruptedError(), "CANCELLED"),
        ("resolve", TimeoutError(), "CAPTURE_TIMEOUT"),
        ("resolve", InterruptedError(), "CANCELLED"),
    ],
)
def test_capture_client_maps_transport_deadline_and_cancellation(
    tmp_path, operation, transport_error, expected_code
):
    client = CaptureServiceClient(
        FakeTransport(error=transport_error), tmp_path / "cache"
    )

    with pytest.raises(CaptureClientError) as caught:
        if operation == "capture":
            client.capture("https://www.douyin.com/video/123456")
        else:
            client.resolve_source("https://www.douyin.com/video/123456")

    assert caught.value.code == expected_code
