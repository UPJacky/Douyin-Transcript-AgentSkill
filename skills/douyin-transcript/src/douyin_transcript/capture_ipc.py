"""Versioned, bounded JSON messages for service-owned capture IPC.

This module defines and validates the JSON wire contract. A separate Windows
adapter opens and authenticates the named pipe; neither codec nor adapter proves
that WFP isolation is active.
Full capture requests carry the original HTTPS URL so the service can own URL
resolution, browser capture, candidate validation, redirects, and media
download. A separate ID-only resolution request supports task deduplication
before media capture. Results carry no source/CDN URLs, request headers, process
identities, proxy endpoints, or filesystem paths.

The media artifact UUID is an identifier, not an authorization capability.
The Windows adapter transfers artifact bytes through a separately bounded
stream protocol; the artifact is never a caller-selected or service-reported
filesystem path.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urlsplit

PROTOCOL_VERSION = 1
REQUEST_TYPE = "capture_request"
RESULT_TYPE = "capture_result"
RESOLVE_REQUEST_TYPE = "capture_resolve_request"
RESOLVE_RESULT_TYPE = "capture_resolve_result"

MAX_REQUEST_FRAME_BYTES = 32 * 1024
MAX_RESULT_FRAME_BYTES = 16 * 1024
MAX_ORIGINAL_URL_UTF8_BYTES = 8 * 1024
MAX_MEDIA_BYTES = 512 * 1024 * 1024
MAX_MEDIA_DURATION_SECONDS = 4 * 60 * 60
MAX_SHORT_LINK_REDIRECTS = 5
MAX_MEDIA_REDIRECTS = 3
MAX_VIDEO_ID_CHARS = 32
MAX_TITLE_CHARS = 160
MAX_AUTHOR_CHARS = 256
MAX_PUBLISH_DATE_CHARS = 128

_UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_VIDEO_ID_PATTERN = re.compile(r"^[0-9]{1,32}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_URL_HOSTS = frozenset({"douyin.com", "www.douyin.com", "v.douyin.com"})
_MEDIA_TYPES = frozenset(
    {
        "audio/aac",
        "audio/mp4",
        "audio/mpeg",
        "audio/ogg",
        "audio/wav",
        "audio/webm",
        "audio/x-m4a",
        "audio/x-wav",
        "video/mp4",
        "video/webm",
        "video/quicktime",
        "video/x-matroska",
    }
)
_BIDI_CONTROLS = frozenset(
    "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
)


class CaptureIpcErrorCode(StrEnum):
    """Stable local errors raised while encoding or decoding a protocol frame."""

    FRAME_TOO_LARGE = "FRAME_TOO_LARGE"
    INVALID_JSON = "INVALID_JSON"
    DUPLICATE_FIELD = "DUPLICATE_FIELD"
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_RESULT = "INVALID_RESULT"


class CaptureFailureCode(StrEnum):
    """Stable, detail-free job failures safe to send over the future IPC."""

    INVALID_URL = "INVALID_URL"
    UNSUPPORTED_URL = "UNSUPPORTED_URL"
    NETWORK_ERROR = "NETWORK_ERROR"
    BROWSER_ISOLATION_UNAVAILABLE = "BROWSER_ISOLATION_UNAVAILABLE"
    BROWSER_ISOLATION_LOST = "BROWSER_ISOLATION_LOST"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    CAPTURE_NO_MEDIA = "CAPTURE_NO_MEDIA"
    CAPTURE_TIMEOUT = "CAPTURE_TIMEOUT"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    MEDIA_INVALID = "MEDIA_INVALID"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    SERVICE_BUSY = "SERVICE_BUSY"
    CANCELLED = "CANCELLED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class CaptureIpcProtocolError(ValueError):
    """A protocol error without echoing any untrusted frame content."""

    def __init__(self, code: CaptureIpcErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class CaptureLimits:
    """Caller-requested limits; a service must still enforce its own policy."""

    max_media_bytes: int = MAX_MEDIA_BYTES
    max_media_duration_seconds: float = 60 * 60
    max_short_link_redirects: int = MAX_SHORT_LINK_REDIRECTS
    max_media_redirects: int = MAX_MEDIA_REDIRECTS


DEFAULT_LIMITS = CaptureLimits()


@dataclass(frozen=True, slots=True)
class CaptureRequest:
    """One opaque full capture/download request; the original URL is sensitive."""

    request_id: uuid.UUID
    original_url: str = field(repr=False)
    limits: CaptureLimits = DEFAULT_LIMITS

    @classmethod
    def create(cls, original_url: str, limits: CaptureLimits = DEFAULT_LIMITS) -> CaptureRequest:
        """Create a request with a fresh correlation ID."""
        return cls(uuid.uuid4(), original_url, limits)


@dataclass(frozen=True, slots=True)
class CaptureResolveRequest:
    """Resolve a supported share URL to an ID without downloading media."""

    request_id: uuid.UUID
    original_url: str = field(repr=False)
    max_short_link_redirects: int = MAX_SHORT_LINK_REDIRECTS

    @classmethod
    def create(
        cls,
        original_url: str,
        *,
        max_short_link_redirects: int = MAX_SHORT_LINK_REDIRECTS,
    ) -> CaptureResolveRequest:
        return cls(uuid.uuid4(), original_url, max_short_link_redirects)


@dataclass(frozen=True, slots=True)
class CaptureVideoMetadata:
    """Bounded page metadata with no source URL or signed media candidate."""

    video_id: str
    title: str | None
    author: str | None
    publish_date: str | None
    duration_seconds: float | None


@dataclass(frozen=True, slots=True)
class CaptureMediaArtifact:
    """A service-owned media artifact descriptor, never a path or bearer token."""

    artifact_id: uuid.UUID
    sha256: str
    size_bytes: int
    media_type: str
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class CaptureResultSuccess:
    request_id: uuid.UUID
    video: CaptureVideoMetadata
    media_artifact: CaptureMediaArtifact


@dataclass(frozen=True, slots=True)
class CaptureResultFailure:
    request_id: uuid.UUID
    code: CaptureFailureCode

    @property
    def retryable(self) -> bool:
        """Retryability is fixed by the protocol code, not caller supplied."""
        return self.code in _RETRYABLE_FAILURES


@dataclass(frozen=True, slots=True)
class CaptureResolveSuccess:
    request_id: uuid.UUID
    video_id: str


@dataclass(frozen=True, slots=True)
class CaptureResolveFailure:
    request_id: uuid.UUID
    code: CaptureFailureCode

    @property
    def retryable(self) -> bool:
        return self.code in _RETRYABLE_FAILURES


CaptureResult = CaptureResultSuccess | CaptureResultFailure
CaptureResolveResult = CaptureResolveSuccess | CaptureResolveFailure

_RETRYABLE_FAILURES = frozenset(
    {
        CaptureFailureCode.NETWORK_ERROR,
        CaptureFailureCode.BROWSER_ISOLATION_LOST,
        CaptureFailureCode.CAPTURE_TIMEOUT,
        CaptureFailureCode.DOWNLOAD_FAILED,
        CaptureFailureCode.SERVICE_BUSY,
    }
)


class _DuplicateJsonField(ValueError):
    pass


class _InvalidJsonConstant(ValueError):
    pass


def encode_capture_request(request: CaptureRequest) -> bytes:
    """Encode a strict v1 request as compact UTF-8 JSON within the frame cap."""
    if not isinstance(request, CaptureRequest):
        raise CaptureIpcProtocolError(CaptureIpcErrorCode.INVALID_REQUEST)
    payload = {
        "protocol_version": PROTOCOL_VERSION,
        "message_type": REQUEST_TYPE,
        "request_id": _uuid_text(request.request_id, CaptureIpcErrorCode.INVALID_REQUEST),
        "original_url": request.original_url,
        "limits": _limits_payload(request.limits),
    }
    _validate_request_payload(payload)
    return _encode_payload(payload, MAX_REQUEST_FRAME_BYTES, CaptureIpcErrorCode.INVALID_REQUEST)


def decode_capture_request(frame: bytes) -> CaptureRequest:
    """Decode a bounded request, rejecting duplicate keys and unknown fields."""
    payload = _decode_payload(frame, MAX_REQUEST_FRAME_BYTES)
    _validate_request_payload(payload)
    try:
        limits = payload["limits"]
        return CaptureRequest(
            request_id=uuid.UUID(payload["request_id"]),
            original_url=payload["original_url"],
            limits=CaptureLimits(
                max_media_bytes=limits["max_media_bytes"],
                max_media_duration_seconds=limits["max_media_duration_seconds"],
                max_short_link_redirects=limits["max_short_link_redirects"],
                max_media_redirects=limits["max_media_redirects"],
            ),
        )
    except (KeyError, TypeError, ValueError):
        raise CaptureIpcProtocolError(CaptureIpcErrorCode.INVALID_REQUEST) from None


def encode_capture_resolve_request(request: CaptureResolveRequest) -> bytes:
    """Encode a bounded URL-to-video-ID resolution request."""
    if not isinstance(request, CaptureResolveRequest):
        raise CaptureIpcProtocolError(CaptureIpcErrorCode.INVALID_REQUEST)
    payload = {
        "protocol_version": PROTOCOL_VERSION,
        "message_type": RESOLVE_REQUEST_TYPE,
        "request_id": _uuid_text(request.request_id, CaptureIpcErrorCode.INVALID_REQUEST),
        "original_url": request.original_url,
        "max_short_link_redirects": request.max_short_link_redirects,
    }
    _validate_capture_resolve_request_payload(payload)
    return _encode_payload(payload, MAX_REQUEST_FRAME_BYTES, CaptureIpcErrorCode.INVALID_REQUEST)


def decode_capture_resolve_request(frame: bytes) -> CaptureResolveRequest:
    """Decode a strict short-link resolution request."""
    payload = _decode_payload(frame, MAX_REQUEST_FRAME_BYTES)
    _validate_capture_resolve_request_payload(payload)
    try:
        return CaptureResolveRequest(
            request_id=uuid.UUID(payload["request_id"]),
            original_url=payload["original_url"],
            max_short_link_redirects=payload["max_short_link_redirects"],
        )
    except (KeyError, TypeError, ValueError):
        raise CaptureIpcProtocolError(CaptureIpcErrorCode.INVALID_REQUEST) from None


def encode_capture_resolve_result(result: CaptureResolveResult) -> bytes:
    """Encode a bounded ID-only resolution result."""
    if isinstance(result, CaptureResolveSuccess):
        payload = {
            "protocol_version": PROTOCOL_VERSION,
            "message_type": RESOLVE_RESULT_TYPE,
            "request_id": _uuid_text(result.request_id, CaptureIpcErrorCode.INVALID_RESULT),
            "status": "resolved",
            "video_id": result.video_id,
        }
    elif isinstance(result, CaptureResolveFailure):
        if type(result.code) is not CaptureFailureCode:
            raise CaptureIpcProtocolError(CaptureIpcErrorCode.INVALID_RESULT)
        payload = {
            "protocol_version": PROTOCOL_VERSION,
            "message_type": RESOLVE_RESULT_TYPE,
            "request_id": _uuid_text(result.request_id, CaptureIpcErrorCode.INVALID_RESULT),
            "status": "failed",
            "error": {"code": result.code.value, "retryable": result.retryable},
        }
    else:
        raise CaptureIpcProtocolError(CaptureIpcErrorCode.INVALID_RESULT)
    _validate_capture_resolve_result_payload(payload)
    return _encode_payload(payload, MAX_RESULT_FRAME_BYTES, CaptureIpcErrorCode.INVALID_RESULT)


def decode_capture_resolve_result(
    frame: bytes, request: CaptureResolveRequest
) -> CaptureResolveResult:
    """Decode an ID-only result and bind it to the exact resolve request."""
    encode_capture_resolve_request(request)
    payload = _decode_payload(frame, MAX_RESULT_FRAME_BYTES)
    _validate_capture_resolve_result_payload(payload)
    try:
        request_id = uuid.UUID(payload["request_id"])
        if payload["status"] == "failed":
            result: CaptureResolveResult = CaptureResolveFailure(
                request_id, CaptureFailureCode(payload["error"]["code"])
            )
        else:
            result = CaptureResolveSuccess(request_id, payload["video_id"])
    except (KeyError, TypeError, ValueError):
        raise CaptureIpcProtocolError(CaptureIpcErrorCode.INVALID_RESULT) from None
    if result.request_id != request.request_id:
        raise CaptureIpcProtocolError(CaptureIpcErrorCode.INVALID_RESULT)
    return result


def encode_capture_result(result: CaptureResult) -> bytes:
    """Encode a success or detail-free failure within the result frame cap."""
    if isinstance(result, CaptureResultSuccess):
        if (
            type(result.video) is not CaptureVideoMetadata
            or type(result.media_artifact) is not CaptureMediaArtifact
        ):
            raise CaptureIpcProtocolError(CaptureIpcErrorCode.INVALID_RESULT)
        payload = {
            "protocol_version": PROTOCOL_VERSION,
            "message_type": RESULT_TYPE,
            "request_id": _uuid_text(result.request_id, CaptureIpcErrorCode.INVALID_RESULT),
            "status": "succeeded",
            "video": {
                "video_id": result.video.video_id,
                "title": result.video.title,
                "author": result.video.author,
                "publish_date": result.video.publish_date,
                "duration_seconds": result.video.duration_seconds,
            },
            "media_artifact": {
                "artifact_id": _uuid_text(
                    result.media_artifact.artifact_id, CaptureIpcErrorCode.INVALID_RESULT
                ),
                "sha256": result.media_artifact.sha256,
                "size_bytes": result.media_artifact.size_bytes,
                "media_type": result.media_artifact.media_type,
                "duration_seconds": result.media_artifact.duration_seconds,
            },
        }
    elif isinstance(result, CaptureResultFailure):
        if type(result.code) is not CaptureFailureCode:
            raise CaptureIpcProtocolError(CaptureIpcErrorCode.INVALID_RESULT)
        payload = {
            "protocol_version": PROTOCOL_VERSION,
            "message_type": RESULT_TYPE,
            "request_id": _uuid_text(result.request_id, CaptureIpcErrorCode.INVALID_RESULT),
            "status": "failed",
            "error": {"code": result.code.value, "retryable": result.retryable},
        }
    else:
        raise CaptureIpcProtocolError(CaptureIpcErrorCode.INVALID_RESULT)
    _validate_result_payload(payload)
    return _encode_payload(payload, MAX_RESULT_FRAME_BYTES, CaptureIpcErrorCode.INVALID_RESULT)


def decode_capture_result(frame: bytes, request: CaptureRequest) -> CaptureResult:
    """Decode a result and bind it to the request and its resource limits."""
    # Reuse the canonical request validation before trusting its limits.
    encode_capture_request(request)
    payload = _decode_payload(frame, MAX_RESULT_FRAME_BYTES)
    _validate_result_payload(payload)
    try:
        request_id = uuid.UUID(payload["request_id"])
        if payload["status"] == "failed":
            result: CaptureResult = CaptureResultFailure(
                request_id, CaptureFailureCode(payload["error"]["code"])
            )
        else:
            video = payload["video"]
            artifact = payload["media_artifact"]
            result = CaptureResultSuccess(
                request_id=request_id,
                video=CaptureVideoMetadata(
                    video_id=video["video_id"],
                    title=video["title"],
                    author=video["author"],
                    publish_date=video["publish_date"],
                    duration_seconds=video["duration_seconds"],
                ),
                media_artifact=CaptureMediaArtifact(
                    artifact_id=uuid.UUID(artifact["artifact_id"]),
                    sha256=artifact["sha256"],
                    size_bytes=artifact["size_bytes"],
                    media_type=artifact["media_type"],
                    duration_seconds=artifact["duration_seconds"],
                ),
            )
    except (KeyError, TypeError, ValueError):
        raise CaptureIpcProtocolError(CaptureIpcErrorCode.INVALID_RESULT) from None
    _validate_result_for_request(result, request)
    return result


def _validate_result_for_request(result: CaptureResult, request: CaptureRequest) -> None:
    if result.request_id != request.request_id:
        raise CaptureIpcProtocolError(CaptureIpcErrorCode.INVALID_RESULT)
    if not isinstance(result, CaptureResultSuccess):
        return
    limits = request.limits
    artifact = result.media_artifact
    if (
        artifact.size_bytes > limits.max_media_bytes
        or artifact.duration_seconds > limits.max_media_duration_seconds
        or (
            result.video.duration_seconds is not None
            and result.video.duration_seconds > limits.max_media_duration_seconds
        )
    ):
        raise CaptureIpcProtocolError(CaptureIpcErrorCode.INVALID_RESULT)


def _decode_payload(frame: bytes, max_bytes: int) -> object:
    if not isinstance(frame, bytes):
        raise CaptureIpcProtocolError(CaptureIpcErrorCode.INVALID_JSON)
    if len(frame) > max_bytes:
        raise CaptureIpcProtocolError(CaptureIpcErrorCode.FRAME_TOO_LARGE)
    try:
        text = frame.decode("utf-8", errors="strict")
        return json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except _DuplicateJsonField:
        raise CaptureIpcProtocolError(CaptureIpcErrorCode.DUPLICATE_FIELD) from None
    except (UnicodeDecodeError, json.JSONDecodeError, _InvalidJsonConstant, RecursionError):
        raise CaptureIpcProtocolError(CaptureIpcErrorCode.INVALID_JSON) from None
    except ValueError:
        # Includes parser failures such as an integer exceeding Python's digit cap.
        raise CaptureIpcProtocolError(CaptureIpcErrorCode.INVALID_JSON) from None


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonField
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise _InvalidJsonConstant(value)


def _encode_payload(
    payload: dict[str, object], max_bytes: int, error_code: CaptureIpcErrorCode
) -> bytes:
    try:
        frame = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError):
        raise CaptureIpcProtocolError(error_code) from None
    if len(frame) > max_bytes:
        raise CaptureIpcProtocolError(CaptureIpcErrorCode.FRAME_TOO_LARGE)
    return frame


def _validate_request_payload(payload: object) -> None:
    if type(payload) is not dict:
        raise CaptureIpcProtocolError(CaptureIpcErrorCode.INVALID_REQUEST)
    _exact_fields(
        payload,
        {"protocol_version", "message_type", "request_id", "original_url", "limits"},
        CaptureIpcErrorCode.INVALID_REQUEST,
    )
    _validate_header(payload, REQUEST_TYPE, CaptureIpcErrorCode.INVALID_REQUEST)
    _validate_uuid(payload["request_id"], CaptureIpcErrorCode.INVALID_REQUEST)
    _validate_original_url(payload["original_url"])
    limits = payload["limits"]
    if type(limits) is not dict:
        raise CaptureIpcProtocolError(CaptureIpcErrorCode.INVALID_REQUEST)
    _exact_fields(
        limits,
        {
            "max_media_bytes",
            "max_media_duration_seconds",
            "max_short_link_redirects",
            "max_media_redirects",
        },
        CaptureIpcErrorCode.INVALID_REQUEST,
    )
    _require_int(limits["max_media_bytes"], 1, MAX_MEDIA_BYTES, CaptureIpcErrorCode.INVALID_REQUEST)
    _require_number(
        limits["max_media_duration_seconds"],
        0,
        MAX_MEDIA_DURATION_SECONDS,
        CaptureIpcErrorCode.INVALID_REQUEST,
    )
    _require_int(
        limits["max_short_link_redirects"],
        0,
        MAX_SHORT_LINK_REDIRECTS,
        CaptureIpcErrorCode.INVALID_REQUEST,
    )
    _require_int(
        limits["max_media_redirects"],
        0,
        MAX_MEDIA_REDIRECTS,
        CaptureIpcErrorCode.INVALID_REQUEST,
    )


def _validate_capture_resolve_request_payload(payload: object) -> None:
    error_code = CaptureIpcErrorCode.INVALID_REQUEST
    if type(payload) is not dict:
        raise CaptureIpcProtocolError(error_code)
    _exact_fields(
        payload,
        {
            "protocol_version",
            "message_type",
            "request_id",
            "original_url",
            "max_short_link_redirects",
        },
        error_code,
    )
    _validate_header(payload, RESOLVE_REQUEST_TYPE, error_code)
    _validate_uuid(payload["request_id"], error_code)
    _validate_original_url(payload["original_url"])
    _require_int(
        payload["max_short_link_redirects"],
        0,
        MAX_SHORT_LINK_REDIRECTS,
        error_code,
    )


def _validate_result_payload(payload: object) -> None:
    error_code = CaptureIpcErrorCode.INVALID_RESULT
    if type(payload) is not dict:
        raise CaptureIpcProtocolError(error_code)
    _validate_header(payload, RESULT_TYPE, error_code)
    _validate_uuid(payload.get("request_id"), error_code)
    status = payload.get("status")
    if status == "failed":
        _exact_fields(
            payload,
            {"protocol_version", "message_type", "request_id", "status", "error"},
            error_code,
        )
        failure = payload["error"]
        if type(failure) is not dict:
            raise CaptureIpcProtocolError(error_code)
        _exact_fields(failure, {"code", "retryable"}, error_code)
        try:
            code = CaptureFailureCode(failure["code"])
        except (TypeError, ValueError):
            raise CaptureIpcProtocolError(error_code) from None
        expected_retryable = code in _RETRYABLE_FAILURES
        if type(failure["retryable"]) is not bool or failure["retryable"] is not expected_retryable:
            raise CaptureIpcProtocolError(error_code)
        return
    if status != "succeeded":
        raise CaptureIpcProtocolError(error_code)
    _exact_fields(
        payload,
        {
            "protocol_version",
            "message_type",
            "request_id",
            "status",
            "video",
            "media_artifact",
        },
        error_code,
    )
    video = payload["video"]
    if type(video) is not dict:
        raise CaptureIpcProtocolError(error_code)
    _exact_fields(
        video,
        {"video_id", "title", "author", "publish_date", "duration_seconds"},
        error_code,
    )
    video_id = video["video_id"]
    if type(video_id) is not str or _VIDEO_ID_PATTERN.fullmatch(video_id) is None:
        raise CaptureIpcProtocolError(error_code)
    _validate_optional_text(video["title"], MAX_TITLE_CHARS, error_code)
    _validate_optional_text(video["author"], MAX_AUTHOR_CHARS, error_code)
    _validate_optional_text(video["publish_date"], MAX_PUBLISH_DATE_CHARS, error_code)
    if video["duration_seconds"] is not None:
        _require_number(
            video["duration_seconds"],
            0,
            MAX_MEDIA_DURATION_SECONDS,
            error_code,
            minimum_exclusive=True,
        )

    artifact = payload["media_artifact"]
    if type(artifact) is not dict:
        raise CaptureIpcProtocolError(error_code)
    _exact_fields(
        artifact,
        {"artifact_id", "sha256", "size_bytes", "media_type", "duration_seconds"},
        error_code,
    )
    _validate_uuid(artifact["artifact_id"], error_code)
    if type(artifact["sha256"]) is not str or _SHA256_PATTERN.fullmatch(artifact["sha256"]) is None:
        raise CaptureIpcProtocolError(error_code)
    _require_int(artifact["size_bytes"], 1, MAX_MEDIA_BYTES, error_code)
    if type(artifact["media_type"]) is not str or artifact["media_type"] not in _MEDIA_TYPES:
        raise CaptureIpcProtocolError(error_code)
    _require_number(
        artifact["duration_seconds"],
        0,
        MAX_MEDIA_DURATION_SECONDS,
        error_code,
        minimum_exclusive=True,
    )


def _validate_capture_resolve_result_payload(payload: object) -> None:
    error_code = CaptureIpcErrorCode.INVALID_RESULT
    if type(payload) is not dict:
        raise CaptureIpcProtocolError(error_code)
    _validate_header(payload, RESOLVE_RESULT_TYPE, error_code)
    _validate_uuid(payload.get("request_id"), error_code)
    status = payload.get("status")
    if status == "failed":
        _exact_fields(
            payload,
            {"protocol_version", "message_type", "request_id", "status", "error"},
            error_code,
        )
        failure = payload["error"]
        if type(failure) is not dict:
            raise CaptureIpcProtocolError(error_code)
        _exact_fields(failure, {"code", "retryable"}, error_code)
        try:
            code = CaptureFailureCode(failure["code"])
        except (TypeError, ValueError):
            raise CaptureIpcProtocolError(error_code) from None
        if type(failure["retryable"]) is not bool or failure["retryable"] is not (
            code in _RETRYABLE_FAILURES
        ):
            raise CaptureIpcProtocolError(error_code)
        return
    if status != "resolved":
        raise CaptureIpcProtocolError(error_code)
    _exact_fields(
        payload,
        {"protocol_version", "message_type", "request_id", "status", "video_id"},
        error_code,
    )
    if (
        type(payload["video_id"]) is not str
        or _VIDEO_ID_PATTERN.fullmatch(payload["video_id"]) is None
    ):
        raise CaptureIpcProtocolError(error_code)


def _validate_header(
    payload: dict[str, object], expected_type: str, error_code: CaptureIpcErrorCode
) -> None:
    version = payload.get("protocol_version")
    if type(version) is int and version != PROTOCOL_VERSION:
        raise CaptureIpcProtocolError(CaptureIpcErrorCode.UNSUPPORTED_VERSION)
    if type(version) is not int or payload.get("message_type") != expected_type:
        raise CaptureIpcProtocolError(error_code)


def _exact_fields(
    payload: dict[str, object], expected: set[str], error_code: CaptureIpcErrorCode
) -> None:
    if set(payload) != expected:
        raise CaptureIpcProtocolError(error_code)


def _validate_original_url(value: object) -> None:
    error_code = CaptureIpcErrorCode.INVALID_REQUEST
    if type(value) is not str or not value:
        raise CaptureIpcProtocolError(error_code)
    if len(value) > MAX_ORIGINAL_URL_UTF8_BYTES:
        raise CaptureIpcProtocolError(error_code)
    try:
        encoded = value.encode("utf-8", errors="strict")
        parsed = urlsplit(value)
        hostname = parsed.hostname
        parsed_port = parsed.port  # Force rejection of malformed or out-of-range ports.
    except (UnicodeEncodeError, ValueError):
        raise CaptureIpcProtocolError(error_code) from None
    if len(encoded) > MAX_ORIGINAL_URL_UTF8_BYTES:
        raise CaptureIpcProtocolError(error_code)
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.netloc
        or not hostname
        or hostname.lower().rstrip(".") not in _SOURCE_URL_HOSTS
        or parsed_port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or "\\" in value
        or any(
            character.isspace()
            or unicodedata.category(character) == "Cc"
            or character in _BIDI_CONTROLS
            for character in value
        )
    ):
        raise CaptureIpcProtocolError(error_code)


def _validate_optional_text(value: object, max_chars: int, error_code: CaptureIpcErrorCode) -> None:
    if value is None:
        return
    if type(value) is not str or len(value) > max_chars:
        raise CaptureIpcProtocolError(error_code)
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise CaptureIpcProtocolError(error_code) from None
    if any(
        unicodedata.category(character) in {"Cc", "Cs"} or character in _BIDI_CONTROLS
        for character in value
    ):
        raise CaptureIpcProtocolError(error_code)


def _validate_uuid(value: object, error_code: CaptureIpcErrorCode) -> None:
    if type(value) is not str or _UUID_PATTERN.fullmatch(value) is None:
        raise CaptureIpcProtocolError(error_code)
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError
    except ValueError:
        raise CaptureIpcProtocolError(error_code) from None


def _uuid_text(value: object, error_code: CaptureIpcErrorCode) -> str:
    if not isinstance(value, uuid.UUID):
        raise CaptureIpcProtocolError(error_code)
    text = str(value)
    _validate_uuid(text, error_code)
    return text


def _limits_payload(value: object) -> dict[str, object]:
    if not isinstance(value, CaptureLimits):
        raise CaptureIpcProtocolError(CaptureIpcErrorCode.INVALID_REQUEST)
    return {
        "max_media_bytes": value.max_media_bytes,
        "max_media_duration_seconds": value.max_media_duration_seconds,
        "max_short_link_redirects": value.max_short_link_redirects,
        "max_media_redirects": value.max_media_redirects,
    }


def _require_int(
    value: object, minimum: int, maximum: int, error_code: CaptureIpcErrorCode
) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise CaptureIpcProtocolError(error_code)


def _require_number(
    value: object,
    minimum: float,
    maximum: float,
    error_code: CaptureIpcErrorCode,
    *,
    minimum_exclusive: bool = False,
) -> None:
    if (
        type(value) not in {int, float}
        or (type(value) is float and not math.isfinite(value))
        or (value <= minimum if minimum_exclusive else value < minimum)
        or value > maximum
    ):
        raise CaptureIpcProtocolError(error_code)
