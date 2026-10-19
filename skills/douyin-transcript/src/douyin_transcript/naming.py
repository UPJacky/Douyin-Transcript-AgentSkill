"""Windows-safe transcript names and collision-resistant output paths."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from pathlib import Path

from .text_safety import strip_bidi_controls

_INVALID_WINDOWS = re.compile(r'[\\/:*?"<>|]')
_SAFE_EXTENSION = re.compile(r"\.[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*\Z")
_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
    *(f"COM{number}" for number in "¹²³"),
    *(f"LPT{number}" for number in "¹²³"),
}


def sanitize_filename(
    title: str | None,
    *,
    fallback: str = "transcript",
    output_dir: Path | None = None,
    extension: str = ".md",
    max_title_chars: int = 80,
    max_path_chars: int = 240,
    reserved_suffix: str = "",
) -> str:
    """Return a legal basename, shortened for both title and full path limits."""
    if max_title_chars < 1 or max_path_chars < 16:
        raise ValueError("filename limits are too small")
    if not isinstance(extension, str) or _SAFE_EXTENSION.fullmatch(extension) is None:
        raise ValueError("extension must be a simple file suffix such as '.md'")

    def clean_component(value: str) -> str:
        value = strip_bidi_controls(value)
        cleaned = _INVALID_WINDOWS.sub("_", value)
        cleaned = "".join(
            "_" if unicodedata.category(char) in {"Cc", "Cs"} else char for char in cleaned
        )
        cleaned = cleaned.strip().strip(" .")
        if cleaned and cleaned.split(".", 1)[0].upper() in _RESERVED:
            cleaned = f"_{cleaned}"
        return cleaned

    safe_fallback = clean_component(str(fallback)) or "transcript"
    cleaned = clean_component(str(title if title is not None else ""))
    if not cleaned:
        cleaned = safe_fallback

    # Windows path limits apply to the full path; reduce the basename enough
    # for the caller's destination and the extension.
    available = max_title_chars
    if output_dir is not None:
        prefix_len = len(str(Path(output_dir).expanduser().absolute())) + 1
        available = min(
            available,
            max_path_chars - prefix_len - len(extension) - len(reserved_suffix),
        )
    if available < 1:
        raise ValueError("output directory leaves no room for a safe filename")
    cleaned = clean_component(cleaned[:available])
    if not cleaned:
        cleaned = clean_component(safe_fallback[:available]) or "t"
    return cleaned


def candidate_output_paths(
    output_dir: Path,
    title: str | None,
    video_id: str | None = None,
    *,
    extension: str = ".md",
    max_path_chars: int = 240,
) -> Iterator[Path]:
    """Yield deterministic names, ending in numeric safe suffixes if occupied."""
    root = Path(output_dir).expanduser()
    fallback = video_id or "transcript"
    base = sanitize_filename(
        title,
        fallback=fallback,
        output_dir=root,
        extension=extension,
        max_path_chars=max_path_chars,
    )
    yield root / f"{base}{extension}"
    if video_id:
        short_id = re.sub(r"[^A-Za-z0-9_-]", "", video_id)[-8:] or "video"
        suffix = f"__{short_id}"
        id_base = sanitize_filename(
            title,
            fallback=fallback,
            output_dir=root,
            extension=extension,
            max_path_chars=max_path_chars,
            reserved_suffix=suffix,
        )
        yield root / f"{id_base}{suffix}{extension}"
    index = 2
    while True:
        suffix = f"__{index}"
        numbered_base = sanitize_filename(
            title,
            fallback=fallback,
            output_dir=root,
            extension=extension,
            max_path_chars=max_path_chars,
            reserved_suffix=suffix,
        )
        yield root / f"{numbered_base}{suffix}{extension}"
        index += 1


def choose_output_path(
    output_dir: Path,
    title: str | None,
    video_id: str | None = None,
    *,
    extension: str = ".md",
    max_path_chars: int = 240,
) -> Path:
    """Choose the first unoccupied deterministic path; never overwrite files."""
    for candidate in candidate_output_paths(
        output_dir,
        title,
        video_id,
        extension=extension,
        max_path_chars=max_path_chars,
    ):
        if not candidate.exists():
            return candidate
    raise FileExistsError("unable to find an unused transcript filename")
