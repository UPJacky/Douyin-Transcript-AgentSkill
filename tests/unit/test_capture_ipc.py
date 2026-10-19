from __future__ import annotations

import json
import hashlib
import io
import uuid

import pytest

from douyin_transcript.capture_artifacts import (
    MAX_CAPTURE_ARTIFACT_CHUNK_BYTES,
    CaptureArtifactError,
    receive_capture_artifact,
)
from douyin_transcript.capture_ipc import (
    CaptureFailureCode,
    CaptureIpcErrorCode,
    CaptureIpcProtocolError,
    CaptureLimits,
    CaptureMediaArtifact,
    CaptureRequest,
    CaptureResolveFailure,
    CaptureResolveRequest,
    CaptureResolveSuccess,
    CaptureResultFailure,
    CaptureResultSuccess,
    CaptureVideoMetadata,
    decode_capture_request,
    decode_capture_resolve_request,
    decode_capture_resolve_result,
    decode_capture_result,
    encode_capture_request,
    encode_capture_resolve_request,
    encode_capture_resolve_result,
    encode_capture_result,
)
from douyin_transcript.storage_security import inspect_private_path


def _request_payload(**updates):
    payload = {
        "protocol_version": 1,
        "message_type": "capture_request",
        "request_id": "12345678-1234-4234-8234-123456789abc",
        "original_url": "https://www.douyin.com/video/123456",
        "limits": {
            "max_media_bytes": 1024,
            "max_media_duration_seconds": 300,
            "max_short_link_redirects": 5,
            "max_media_redirects": 3,
        },
    }
    payload.update(updates)
    return payload


def test_capture_request_round_trip_contains_only_full_job_input():
    request = CaptureRequest.create(
        "https://v.douyin.com/example/",
        CaptureLimits(max_media_bytes=1024, max_media_duration_seconds=300),
    )

    encoded = encode_capture_request(request)
    decoded = decode_capture_request(encoded)
    payload = json.loads(encoded)

    assert decoded == request
    assert set(payload) == {
        "protocol_version",
        "message_type",
        "request_id",
        "original_url",
        "limits",
    }
    assert set(payload["limits"]) == {
        "max_media_bytes",
        "max_media_duration_seconds",
        "max_short_link_redirects",
        "max_media_redirects",
    }


@pytest.mark.parametrize(
    "url",
    [
        "http://www.douyin.com/video/1",
        "https://douyin.com.evil.test/video/1",
        "https://www.douyin.com.evil.test/video/1",
        "https://v.douyin.com:444/abc/",
        "https://user@www.douyin.com/video/1",
        "https://www.douyin.com/video/1#fragment",
        "https://127.0.0.1/video/1",
    ],
)
def test_capture_request_rejects_untrusted_source_urls(url: str):
    request = CaptureRequest(uuid.uuid4(), url)

    with pytest.raises(CaptureIpcProtocolError) as error:
        encode_capture_request(request)

    assert error.value.code is CaptureIpcErrorCode.INVALID_REQUEST


def test_capture_request_decoder_rejects_duplicate_and_unknown_fields():
    payload = json.dumps(_request_payload(), separators=(",", ":")).encode()
    duplicate = payload.replace(
        b'"request_id":"12345678-1234-4234-8234-123456789abc"',
        b'"request_id":"12345678-1234-4234-8234-123456789abc",'
        b'"request_id":"12345678-1234-4234-8234-123456789abc"',
    )
    with pytest.raises(CaptureIpcProtocolError) as duplicate_error:
        decode_capture_request(duplicate)
    assert duplicate_error.value.code is CaptureIpcErrorCode.DUPLICATE_FIELD

    with pytest.raises(CaptureIpcProtocolError) as unknown_error:
        decode_capture_request(
            json.dumps(
                _request_payload(unexpected=True), separators=(",", ":")
            ).encode()
        )
    assert unknown_error.value.code is CaptureIpcErrorCode.INVALID_REQUEST


def test_capture_request_decoder_rejects_oversized_frames():
    with pytest.raises(CaptureIpcProtocolError) as error:
        decode_capture_request(b" " * (32 * 1024 + 1))

    assert error.value.code is CaptureIpcErrorCode.FRAME_TOO_LARGE


def test_capture_resolve_request_round_trip_is_bounded_and_separate_from_capture():
    request = CaptureResolveRequest.create(
        "https://v.douyin.com/example/?share_token=secret",
        max_short_link_redirects=3,
    )

    encoded = encode_capture_resolve_request(request)
    payload = json.loads(encoded)

    assert decode_capture_resolve_request(encoded) == request
    assert payload["message_type"] == "capture_resolve_request"
    assert payload["max_short_link_redirects"] == 3
    assert "limits" not in payload


def test_capture_resolve_request_rejects_unknown_fields_and_invalid_redirect_limit():
    request = CaptureResolveRequest.create("https://v.douyin.com/example/")
    payload = json.loads(encode_capture_resolve_request(request))

    with pytest.raises(CaptureIpcProtocolError) as error:
        decode_capture_resolve_request(
            json.dumps({**payload, "media_path": "C:/private.mp4"}).encode()
        )
    assert error.value.code is CaptureIpcErrorCode.INVALID_REQUEST

    with pytest.raises(CaptureIpcProtocolError) as error:
        encode_capture_resolve_request(
            CaptureResolveRequest(request.request_id, request.original_url, 6)
        )
    assert error.value.code is CaptureIpcErrorCode.INVALID_REQUEST


def test_capture_resolve_result_contains_only_video_id_and_binds_request_id():
    request = CaptureResolveRequest.create("https://v.douyin.com/example/")
    result = CaptureResolveSuccess(request.request_id, "123456")
    encoded = encode_capture_resolve_result(result)
    payload = json.loads(encoded)

    assert decode_capture_resolve_result(encoded, request) == result
    assert set(payload) == {
        "protocol_version",
        "message_type",
        "request_id",
        "status",
        "video_id",
    }
    assert "url" not in encoded.decode()

    mismatch = encode_capture_resolve_result(
        CaptureResolveFailure(uuid.uuid4(), CaptureFailureCode.CAPTURE_TIMEOUT)
    )
    with pytest.raises(CaptureIpcProtocolError) as error:
        decode_capture_resolve_result(mismatch, request)
    assert error.value.code is CaptureIpcErrorCode.INVALID_RESULT


@pytest.mark.parametrize("video_id", ["", "../123", "1" * 33])
def test_capture_resolve_result_rejects_untrusted_video_ids(video_id: str):
    request = CaptureResolveRequest.create("https://v.douyin.com/example/")
    with pytest.raises(CaptureIpcProtocolError) as error:
        encode_capture_resolve_result(
            CaptureResolveSuccess(request.request_id, video_id)
        )
    assert error.value.code is CaptureIpcErrorCode.INVALID_RESULT


def test_capture_success_round_trip_never_returns_path_or_upstream_url():
    request = CaptureRequest.create("https://www.douyin.com/video/123456")
    result = CaptureResultSuccess(
        request_id=request.request_id,
        video=CaptureVideoMetadata("123456", "标题", "作者", None, 12.5),
        media_artifact=CaptureMediaArtifact(
            uuid.uuid4(),
            "a" * 64,
            1024,
            "audio/mp4",
            12.5,
        ),
    )

    encoded = encode_capture_result(result)
    decoded = decode_capture_result(encoded, request)
    payload = json.loads(encoded)

    assert decoded == result
    assert set(payload) == {
        "protocol_version",
        "message_type",
        "request_id",
        "status",
        "video",
        "media_artifact",
    }
    assert set(payload["media_artifact"]) == {
        "artifact_id",
        "sha256",
        "size_bytes",
        "media_type",
        "duration_seconds",
    }
    assert "path" not in encoded.decode()
    assert "url" not in payload["media_artifact"]


def test_capture_failure_retryability_is_derived_and_validated():
    request = CaptureRequest.create("https://www.douyin.com/video/123456")
    encoded = encode_capture_result(
        CaptureResultFailure(request.request_id, CaptureFailureCode.CAPTURE_TIMEOUT)
    )
    assert decode_capture_result(encoded, request) == CaptureResultFailure(
        request.request_id, CaptureFailureCode.CAPTURE_TIMEOUT
    )

    payload = json.loads(encoded)
    payload["error"]["retryable"] = False
    with pytest.raises(CaptureIpcProtocolError) as error:
        decode_capture_result(
            json.dumps(payload, separators=(",", ":")).encode(), request
        )
    assert error.value.code is CaptureIpcErrorCode.INVALID_RESULT


def test_capture_result_rejects_a_different_request_id():
    request = CaptureRequest.create("https://www.douyin.com/video/123456")
    result = CaptureResultFailure(uuid.uuid4(), CaptureFailureCode.CAPTURE_TIMEOUT)

    with pytest.raises(CaptureIpcProtocolError) as error:
        decode_capture_result(encode_capture_result(result), request)

    assert error.value.code is CaptureIpcErrorCode.INVALID_RESULT


@pytest.mark.parametrize(
    ("size_bytes", "duration_seconds"),
    [(101, 10.0), (100, 10.1)],
)
def test_capture_result_rejects_media_over_request_limits(size_bytes, duration_seconds):
    request = CaptureRequest.create(
        "https://www.douyin.com/video/123456",
        CaptureLimits(max_media_bytes=100, max_media_duration_seconds=10),
    )
    result = CaptureResultSuccess(
        request_id=request.request_id,
        video=CaptureVideoMetadata("123456", "标题", None, None, duration_seconds),
        media_artifact=CaptureMediaArtifact(
            uuid.uuid4(), "a" * 64, size_bytes, "audio/mp4", duration_seconds
        ),
    )

    with pytest.raises(CaptureIpcProtocolError) as error:
        decode_capture_result(encode_capture_result(result), request)

    assert error.value.code is CaptureIpcErrorCode.INVALID_RESULT


def _artifact_result(
    request, data: bytes, *, digest: str | None = None, size: int | None = None
):
    return CaptureResultSuccess(
        request_id=request.request_id,
        video=CaptureVideoMetadata("123456", "标题", None, None, 1.0),
        media_artifact=CaptureMediaArtifact(
            uuid.uuid4(),
            digest or hashlib.sha256(data).hexdigest(),
            len(data) if size is None else size,
            "audio/mpeg",
            1.0,
        ),
    )


def test_capture_artifact_receiver_checks_binding_and_publishes_private_media(tmp_path):
    request = CaptureRequest.create(
        "https://www.douyin.com/video/123456",
        CaptureLimits(max_media_bytes=128, max_media_duration_seconds=10),
    )
    data = b"captured media bytes"
    result = _artifact_result(request, data)

    path = receive_capture_artifact(
        result, request, io.BytesIO(data), tmp_path / "cache"
    )

    assert path.read_bytes() == data
    assert path.parent == tmp_path / "cache"
    assert path.suffix == ".mp3"
    assert inspect_private_path(path).status == "private"
    assert not list(path.parent.glob("*.part"))


@pytest.mark.parametrize(
    ("result_factory", "stream_factory", "expected_code"),
    [
        (
            lambda request, data: _artifact_result(request, data, digest="a" * 64),
            lambda data: io.BytesIO(data),
            "MEDIA_DIGEST_MISMATCH",
        ),
        (
            lambda request, data: _artifact_result(request, data, size=len(data) + 1),
            lambda data: io.BytesIO(data),
            "MEDIA_LENGTH_MISMATCH",
        ),
        (
            lambda request, data: _artifact_result(request, data),
            lambda data: io.BytesIO(data + b"extra"),
            "MEDIA_TOO_LARGE",
        ),
        (
            lambda request, data: _artifact_result(request, data),
            lambda data: io.BytesIO(data),
            "INVALID_DESCRIPTOR",
        ),
    ],
)
def test_capture_artifact_receiver_rejects_invalid_stream_and_descriptor(
    tmp_path, result_factory, stream_factory, expected_code
):
    data = b"small media"
    request = CaptureRequest.create(
        "https://www.douyin.com/video/123456",
        CaptureLimits(
            max_media_bytes=4 if expected_code == "INVALID_DESCRIPTOR" else 128
        ),
    )
    result = result_factory(request, data)
    if expected_code == "INVALID_DESCRIPTOR":
        result = _artifact_result(request, data)

    with pytest.raises(CaptureArtifactError) as error:
        receive_capture_artifact(
            result,
            request,
            stream_factory(data),
            tmp_path / "cache",
        )

    assert error.value.code == expected_code
    cache = tmp_path / "cache"
    if cache.exists():
        assert not list(cache.glob("*.part"))
        assert not [path for path in cache.iterdir() if path.suffix == ".mp3"]


def test_capture_artifact_receiver_rejects_mismatched_request_id(tmp_path):
    request = CaptureRequest.create("https://www.douyin.com/video/123456")
    result = _artifact_result(request, b"media")
    result = CaptureResultSuccess(
        request_id=uuid.uuid4(),
        video=result.video,
        media_artifact=result.media_artifact,
    )

    with pytest.raises(CaptureArtifactError) as error:
        receive_capture_artifact(
            result, request, io.BytesIO(b"media"), tmp_path / "cache"
        )

    assert error.value.code == "INVALID_DESCRIPTOR"
    assert not (tmp_path / "cache").exists()


def test_capture_artifact_receiver_checks_cancellation_deadline_and_read_bound(
    tmp_path,
):
    request = CaptureRequest.create("https://www.douyin.com/video/123456")
    data = b"media"
    result = _artifact_result(request, data)

    with pytest.raises(CaptureArtifactError) as cancelled:
        receive_capture_artifact(
            result,
            request,
            io.BytesIO(data),
            tmp_path / "cancelled",
            is_cancelled=lambda: True,
        )
    assert cancelled.value.code == "CANCELLED"

    with pytest.raises(CaptureArtifactError) as timed_out:
        receive_capture_artifact(
            result,
            request,
            io.BytesIO(data),
            tmp_path / "timed-out",
            deadline_monotonic=0,
        )
    assert timed_out.value.code == "TIMEOUT"

    class OversizedRead:
        def read(self, size):
            return b"x" * (min(size, MAX_CAPTURE_ARTIFACT_CHUNK_BYTES) + 1)

    large_request = CaptureRequest.create(
        "https://www.douyin.com/video/123456",
        CaptureLimits(max_media_bytes=MAX_CAPTURE_ARTIFACT_CHUNK_BYTES + 1),
    )
    large_data = b"x" * (MAX_CAPTURE_ARTIFACT_CHUNK_BYTES + 1)
    large_result = _artifact_result(large_request, large_data)
    with pytest.raises(CaptureArtifactError) as oversized:
        receive_capture_artifact(
            large_result,
            large_request,
            OversizedRead(),
            tmp_path / "oversized",
        )
    assert oversized.value.code == "MEDIA_TOO_LARGE"

    for cache_name in ("cancelled", "timed-out", "oversized"):
        cache = tmp_path / cache_name
        assert not list(cache.glob("*.part"))
        assert not [path for path in cache.iterdir() if path.suffix == ".mp3"]


def test_capture_artifact_receiver_never_overwrites_existing_artifact(tmp_path):
    request = CaptureRequest.create("https://www.douyin.com/video/123456")
    data = b"media"
    result = _artifact_result(request, data)
    cache = tmp_path / "cache"
    cache.mkdir()
    final_path = cache / f"{result.media_artifact.artifact_id}.mp3"
    final_path.write_bytes(b"existing")

    with pytest.raises(CaptureArtifactError) as error:
        receive_capture_artifact(result, request, io.BytesIO(data), cache)

    assert error.value.code == "ARTIFACT_COLLISION"
    assert final_path.read_bytes() == b"existing"
    assert not list(cache.glob("*.part"))
