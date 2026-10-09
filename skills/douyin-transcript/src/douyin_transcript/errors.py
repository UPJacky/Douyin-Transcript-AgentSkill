"""Stable CLI error codes for local, capture, download, and ASR operations."""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    INVALID_URL = "INVALID_URL"
    NETWORK_ERROR = "NETWORK_ERROR"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    CAPTURE_NO_MEDIA = "CAPTURE_NO_MEDIA"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    MEDIA_INVALID = "MEDIA_INVALID"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    MODEL_INCOMPATIBLE = "MODEL_INCOMPATIBLE"
    ASR_FAILED = "ASR_FAILED"
    OUTPUT_NOT_WRITABLE = "OUTPUT_NOT_WRITABLE"
    OUTPUT_COLLISION = "OUTPUT_COLLISION"
    TASK_LOCKED = "TASK_LOCKED"
    CONFIG_INVALID = "CONFIG_INVALID"


class TranscriptError(Exception):
    """An expected operation failure with a stable code and user-safe hint."""

    def __init__(self, code: ErrorCode | str, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.code = str(code)
        self.message = message
        self.hint = hint
