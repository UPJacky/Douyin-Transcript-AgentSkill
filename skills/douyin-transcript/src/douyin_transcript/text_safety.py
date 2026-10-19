"""Utilities for handling invisible controls in untrusted display text."""

from __future__ import annotations

import re

_BIDI_CONTROL_CODEPOINTS = frozenset(
    [0x061C, 0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x2070)]
)
BIDI_CONTROLS = frozenset(chr(codepoint) for codepoint in _BIDI_CONTROL_CODEPOINTS)
_SENSITIVE_HEADER = re.compile(
    r"(?i)\b(authorization|proxy-authorization|cookie|set-cookie|"
    r"x-[a-z0-9_-]*(?:token|key|secret))\s*[:=]\s*[^\r\n]+"
)
_URL_IN_TEXT = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_SENSITIVE_QUERY_VALUE = re.compile(
    r"(?i)([?&](?:signature|sig|token|access_token|auth|key|secret|expires?|"
    r"x-amz-[a-z0-9-]+)=)[^&\s]+"
)


def strip_bidi_controls(text: str) -> str:
    """Remove Unicode direction controls from untrusted labels and filenames."""
    return "".join(character for character in text if character not in BIDI_CONTROLS)


def strip_display_controls(text: str) -> str:
    """Remove terminal and bidi controls from untrusted display labels."""
    return "".join(
        character
        for character in text
        if (
            character not in BIDI_CONTROLS
            and ord(character) >= 32
            and not 127 <= ord(character) <= 159
        )
    )


def sanitize_error_message(message: str | None) -> str | None:
    """Redact credentials and URLs before an error is stored or displayed."""
    if message is None:
        return None
    sanitized = _SENSITIVE_HEADER.sub(lambda match: f"{match.group(1)}: [REDACTED]", str(message))

    def redact_url(match: re.Match[str]) -> str:
        raw_url = match.group(0)
        punctuation = ".,;:!)]}"
        suffix = raw_url[len(raw_url.rstrip(punctuation)) :]
        return "[REDACTED_URL]" + suffix

    sanitized = _URL_IN_TEXT.sub(redact_url, sanitized)
    sanitized = _SENSITIVE_QUERY_VALUE.sub(r"\1[REDACTED]", sanitized)
    return strip_display_controls(sanitized)[:1000]


def show_bidi_controls(text: str) -> str:
    """Render invisible direction controls as visible code point labels."""
    return "".join(
        f"<U+{ord(character):04X}>" if character in BIDI_CONTROLS else character
        for character in text
    )
