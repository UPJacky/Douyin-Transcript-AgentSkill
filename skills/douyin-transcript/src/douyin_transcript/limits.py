"""Resource limits for local media decoding and ASR output."""

from __future__ import annotations

import math

DEFAULT_MAX_MEDIA_DURATION_SECONDS = 60 * 60
DEFAULT_MAX_OUTPUT_SEGMENTS = 20_000
DEFAULT_MAX_OUTPUT_CHARACTERS = 2_000_000

# Permit purposeful configuration while keeping accidental values bounded.
HARD_MAX_MEDIA_DURATION_SECONDS = 4 * 60 * 60
HARD_MAX_OUTPUT_SEGMENTS = 100_000
HARD_MAX_OUTPUT_CHARACTERS = 10_000_000


class ResourceLimitError(RuntimeError):
    """A stable, user-facing failure caused by a configured resource cap."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_resource_limits(
    max_media_duration_seconds: float,
    max_output_segments: int,
    max_output_characters: int,
) -> tuple[float, int, int]:
    """Validate and normalize a set of finite, hard-bounded resource limits."""
    valid_duration = isinstance(max_media_duration_seconds, (int, float)) and not isinstance(
        max_media_duration_seconds, bool
    )
    if valid_duration:
        if isinstance(max_media_duration_seconds, float):
            valid_duration = math.isfinite(max_media_duration_seconds)
        valid_duration = valid_duration and 0 < max_media_duration_seconds <= (
            HARD_MAX_MEDIA_DURATION_SECONDS
        )
    if not valid_duration:
        raise ValueError(
            f"max media duration must be between 0 and {HARD_MAX_MEDIA_DURATION_SECONDS} seconds"
        )
    if (
        isinstance(max_output_segments, bool)
        or not isinstance(max_output_segments, int)
        or not 0 < max_output_segments <= HARD_MAX_OUTPUT_SEGMENTS
    ):
        raise ValueError(f"max output segments must be between 1 and {HARD_MAX_OUTPUT_SEGMENTS}")
    if (
        isinstance(max_output_characters, bool)
        or not isinstance(max_output_characters, int)
        or not 0 < max_output_characters <= HARD_MAX_OUTPUT_CHARACTERS
    ):
        raise ValueError(
            f"max output characters must be between 1 and {HARD_MAX_OUTPUT_CHARACTERS}"
        )
    return float(max_media_duration_seconds), max_output_segments, max_output_characters


def require_media_duration(duration_seconds: float | None, limit_seconds: float) -> None:
    """Reject unknown, invalid, or over-limit decoder-reported media duration."""
    valid_duration = isinstance(duration_seconds, (int, float)) and not isinstance(
        duration_seconds, bool
    )
    if valid_duration and isinstance(duration_seconds, float):
        valid_duration = math.isfinite(duration_seconds)
    if not valid_duration or duration_seconds <= 0:
        raise ResourceLimitError(
            "MEDIA_DURATION_UNKNOWN",
            "无法可靠确定媒体时长；请先转换为常见的音频或视频格式。",
        )
    if duration_seconds > limit_seconds:
        minutes = limit_seconds / 60
        raise ResourceLimitError(
            "MEDIA_TOO_LONG",
            f"媒体时长超过限制（{minutes:g} 分钟）；可通过 limits 配置或命令行调整上限。",
        )
