"""Conservative transcript formatting that keeps ASR words and ordering."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .limits import HARD_MAX_MEDIA_DURATION_SECONDS

_SENTENCE_END = tuple("。！？!?；;.")
_WHITESPACE = re.compile(r"\s+")
_ASCII_WORD_SUFFIX = re.compile(r"[A-Za-z0-9][A-Za-z0-9_'-]*[,.!?;:'\")\]]*\Z")


@dataclass(frozen=True)
class NormalizedTranscript:
    paragraphs: tuple[str, ...]
    timeline_lines: tuple[str, ...]

    @property
    def text(self) -> str:
        return "\n\n".join(self.paragraphs)

    @property
    def timeline_text(self) -> str:
        return "\n".join(self.timeline_lines)


def _value(segment: Any, name: str, default: Any = None) -> Any:
    if isinstance(segment, dict):
        return segment.get(name, default)
    return getattr(segment, name, default)


def _time(segment: Any, name: str) -> float | None:
    try:
        value = float(_value(segment, name))
    except (OverflowError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) and 0 <= value <= HARD_MAX_MEDIA_DURATION_SECONDS else None


def _clean_text(value: Any) -> str:
    # Collapse whitespace only.  Do not remove fillers, alter words, or rewrite
    # punctuation; those changes could alter the spoken content.
    return _WHITESPACE.sub(" ", str(value or "")).strip()


def format_timestamp(seconds: float) -> str:
    """Format bounded seconds as a stable ``[mm:ss]`` timestamp."""
    try:
        value = float(seconds)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError("timestamp must be a finite number") from exc
    if not math.isfinite(value) or value < 0 or value > HARD_MAX_MEDIA_DURATION_SECONDS:
        raise ValueError("timestamp is outside the supported media duration")
    whole_seconds = int(value)
    minutes, remainder = divmod(whole_seconds, 60)
    return f"[{minutes:02d}:{remainder:02d}]"


def normalize_segments(
    segments: Iterable[Any],
    *,
    max_paragraph_chars: int = 400,
    pause_seconds: float = 1.2,
) -> NormalizedTranscript:
    """Group source segments without splitting or paraphrasing their text.

    Boundaries come only from original ASR segment boundaries, long pauses, and
    sentence punctuation.  An overlong ASR segment stays intact to avoid
    splitting a term in the middle.
    """
    if max_paragraph_chars < 1:
        raise ValueError("max_paragraph_chars must be positive")
    if pause_seconds < 0:
        raise ValueError("pause_seconds must be nonnegative")

    paragraphs: list[str] = []
    timeline: list[tuple[float, int, str]] = []
    current = ""
    previous_end: float | None = None
    previous_trailing_space = False

    for segment in segments:
        raw_text = str(_value(segment, "text", "") or "")
        source_boundary_space = bool(raw_text[:1].isspace())
        source_trailing_space = bool(raw_text[-1:].isspace())
        text = _clean_text(raw_text)
        start = _time(segment, "start")
        end = _time(segment, "end")
        if not text:
            if end is not None:
                previous_end = end
            continue

        display_text = (
            text
            if not current
            else _join_segments(
                current,
                text,
                source_boundary_space=source_boundary_space,
                previous_boundary_space=previous_trailing_space,
            )
        )
        pause = start - previous_end if start is not None and previous_end is not None else 0
        if current and pause >= pause_seconds:
            paragraphs.append(current)
            current = text
        elif current and len(display_text) > max_paragraph_chars:
            paragraphs.append(current)
            current = text
        else:
            current = display_text

        if start is not None:
            timeline.append((start, len(timeline), f"{format_timestamp(start)} {text}"))
        if end is not None:
            previous_end = end
        previous_trailing_space = source_trailing_space
        if current and current[-1] in _SENTENCE_END:
            paragraphs.append(current)
            current = ""

    if current:
        paragraphs.append(current)
    timeline.sort(key=lambda item: (item[0], item[1]))
    return NormalizedTranscript(tuple(paragraphs), tuple(line for _start, _index, line in timeline))


def _join_segments(
    left: str,
    right: str,
    *,
    source_boundary_space: bool = False,
    previous_boundary_space: bool = False,
) -> str:
    """Preserve source spaces while avoiding invented spaces between Han text."""
    if source_boundary_space:
        return f"{left.rstrip()} {right.lstrip()}"
    if (
        previous_boundary_space
        and right[:1].isascii()
        and right[:1].isalnum()
        and _ASCII_WORD_SUFFIX.search(left.rstrip())
    ):
        return f"{left} {right}"
    # Whisper commonly emits English words as separate segments without a
    # leading space; insert one only between ASCII word characters.
    if left[-1:].isascii() and right[:1].isascii():
        if left[-1:].isalnum() and right[:1].isalnum():
            return f"{left} {right}"
    return left + right
