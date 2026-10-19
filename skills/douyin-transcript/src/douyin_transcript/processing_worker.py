"""Private subprocess entry point for bounded media and ASR work."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from .asr import ASRUnavailableError, LocalASR
from .downloader import (
    DecoderUnavailableError,
    DownloadError,
    MediaFile,
    MediaIdentity,
    MediaInvalidError,
    validate_media_file,
)
from .limits import ResourceLimitError

_MAX_REQUEST_BYTES = 128 * 1024
_MAX_RESPONSE_BYTES = 64 * 1024 * 1024
_MAX_TEXT_ERROR = 1000


def main() -> int:
    # Keep a private descriptor for protocol frames, then redirect fd 1 to
    # stderr. Native decoder/model libraries cannot corrupt the JSON stream.
    protocol_fd = os.dup(1)
    os.dup2(2, 1)
    asr: LocalASR | None = None
    while True:
        raw = sys.stdin.buffer.readline(_MAX_REQUEST_BYTES + 1)
        if not raw:
            break
        if len(raw) > _MAX_REQUEST_BYTES or not raw.endswith(b"\n"):
            _write_frame(protocol_fd, _failure("ProcessingWorkerError", None, "请求超出协议限制"))
            break
        try:
            request = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError):
            _write_frame(protocol_fd, _failure("ProcessingWorkerError", None, "请求格式无效"))
            break
        if not isinstance(request, dict) or not isinstance(request.get("command"), str):
            _write_frame(protocol_fd, _failure("ProcessingWorkerError", None, "请求格式无效"))
            break
        command = request["command"]
        if command == "close":
            _write_frame(protocol_fd, {"ok": True, "result": {}})
            break
        try:
            result, asr = _dispatch(request, asr)
            response = {"ok": True, "result": result}
        except Exception as exc:
            response = _exception_response(exc)
        if not _write_frame(protocol_fd, response):
            break
    try:
        os.close(protocol_fd)
    except OSError:
        pass
    return 0


def _dispatch(
    request: dict[str, Any], asr: LocalASR | None
) -> tuple[dict[str, Any], LocalASR | None]:
    command = request["command"]
    if command == "validate":
        path = _required_string(request, "path", max_length=32768)
        duration = request.get("max_duration_seconds")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            raise ValueError("invalid duration limit")
        media = validate_media_file(path, max_duration_seconds=float(duration))
        return _media_json(media), asr
    if command != "transcribe":
        raise ValueError("unsupported worker command")

    path = Path(_required_string(request, "path", max_length=32768))
    data_dir = Path(_required_string(request, "data_dir", max_length=32768))
    profile = _required_string(request, "profile", max_length=16)
    language = _required_string(request, "language", max_length=16)
    max_duration = _number(request, "max_media_duration_seconds")
    max_segments = _integer(request, "max_output_segments")
    max_characters = _integer(request, "max_output_characters")
    media = _media_from_json(request.get("media"))
    if os.path.normcase(os.path.abspath(path)) != os.path.normcase(os.path.abspath(media.path)):
        raise MediaInvalidError("MEDIA_CHANGED", "校验结果与待转写路径不一致")
    if asr is None:
        asr = LocalASR(
            data_dir,
            profile,
            max_media_duration_seconds=max_duration,
            max_output_segments=max_segments,
            max_output_characters=max_characters,
        )
    result = asr.transcribe(path, language=language, validated_media=media)
    return {
        "segments": [
            {"start": item.start, "end": item.end, "text": item.text} for item in result.segments
        ],
        "duration_seconds": result.duration_seconds,
        "language": result.language,
        "model": result.model,
        "profile": result.profile,
    }, asr


def _media_json(media: MediaFile) -> dict[str, Any]:
    identity = media.identity
    return {
        "path": str(media.path),
        "format": media.format,
        "size_bytes": media.size_bytes,
        "duration_seconds": media.duration_seconds,
        "identity": (
            {
                "device": identity.device,
                "inode": identity.inode,
                "size_bytes": identity.size_bytes,
                "mtime_ns": identity.mtime_ns,
                "ctime_ns": identity.ctime_ns,
            }
            if identity is not None
            else None
        ),
    }


def _media_from_json(value: Any) -> MediaFile:
    if not isinstance(value, dict):
        raise ValueError("invalid media descriptor")
    identity_value = value.get("identity")
    identity = None
    if isinstance(identity_value, dict):
        identity = MediaIdentity(
            device=_integer(identity_value, "device"),
            inode=_integer(identity_value, "inode"),
            size_bytes=_integer(identity_value, "size_bytes"),
            mtime_ns=_integer(identity_value, "mtime_ns"),
            ctime_ns=_integer(identity_value, "ctime_ns"),
        )
    return MediaFile(
        path=Path(_required_string(value, "path", max_length=32768)),
        format=_required_string(value, "format", max_length=64),
        size_bytes=_integer(value, "size_bytes"),
        duration_seconds=_number(value, "duration_seconds"),
        identity=identity,
    )


def _required_string(value: dict[str, Any], key: str, *, max_length: int) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result or len(result) > max_length:
        raise ValueError(f"invalid {key}")
    return result


def _number(value: dict[str, Any], key: str) -> float:
    result = value.get(key)
    if isinstance(result, bool) or not isinstance(result, (int, float)):
        raise ValueError(f"invalid {key}")
    return float(result)


def _integer(value: dict[str, Any], key: str) -> int:
    result = value.get(key)
    if isinstance(result, bool) or not isinstance(result, int):
        raise ValueError(f"invalid {key}")
    return result


def _exception_response(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ResourceLimitError):
        return _failure(type(exc).__name__, exc.code, str(exc))
    if isinstance(exc, (DecoderUnavailableError, MediaInvalidError, DownloadError)):
        return _failure(type(exc).__name__, exc.code, str(exc))
    if isinstance(exc, ASRUnavailableError):
        return _failure(type(exc).__name__, None, str(exc))
    return _failure("ProcessingWorkerError", None, type(exc).__name__)


def _failure(name: str, code: str | None, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {"type": name, "code": code, "message": str(message)[:_MAX_TEXT_ERROR]},
    }


def _write_frame(protocol_fd: int, payload: dict[str, Any]) -> bool:
    try:
        frame = (
            json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode(
                "utf-8"
            )
            + b"\n"
        )
    except (TypeError, ValueError, UnicodeError):
        frame = _failure("ProcessingWorkerError", None, "invalid result")
        frame = json.dumps(frame, separators=(",", ":")).encode("utf-8") + b"\n"
    if len(frame) > _MAX_RESPONSE_BYTES:
        frame = _failure("ProcessingWorkerError", None, "response exceeds protocol limit")
        frame = json.dumps(frame, separators=(",", ":")).encode("utf-8") + b"\n"
    try:
        view = memoryview(frame)
        while view:
            count = os.write(protocol_fd, view)
            view = view[count:]
        return True
    except OSError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
