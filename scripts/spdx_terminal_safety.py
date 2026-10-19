"""Helpers for safely displaying untrusted SPDX input in terminals."""

from __future__ import annotations

import unicodedata


def contains_terminal_controls(value: str) -> bool:
    """Return whether *value* contains control/format or line-separator characters."""
    return any(
        unicodedata.category(character).startswith("C")
        or unicodedata.category(character) in {"Zl", "Zp"}
        for character in value
    )


def escape_terminal_controls(value: str) -> str:
    """Escape invisible control/format characters while preserving ordinary Unicode."""
    escaped: list[str] = []
    for character in value:
        category = unicodedata.category(character)
        if category.startswith("C") or category in {"Zl", "Zp"}:
            codepoint = ord(character)
            escaped.append(
                f"\\u{codepoint:04x}" if codepoint <= 0xFFFF else f"\\U{codepoint:08x}"
            )
        else:
            escaped.append(character)
    return "".join(escaped)


def escape_terminal_controls_unambiguously(value: str) -> str:
    """Escape terminal controls and double literal backslashes before visible escapes."""
    return escape_terminal_controls(value.replace("\\", "\\\\"))
