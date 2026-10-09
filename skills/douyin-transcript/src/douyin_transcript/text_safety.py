"""Utilities for handling invisible controls in untrusted display text."""

from __future__ import annotations

_BIDI_CONTROL_CODEPOINTS = frozenset(
    [0x061C, 0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x2070)]
)
BIDI_CONTROLS = frozenset(chr(codepoint) for codepoint in _BIDI_CONTROL_CODEPOINTS)


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
            and ord(character) != 127
        )
    )


def show_bidi_controls(text: str) -> str:
    """Render invisible direction controls as visible code point labels."""
    return "".join(
        f"<U+{ord(character):04X}>" if character in BIDI_CONTROLS else character
        for character in text
    )
