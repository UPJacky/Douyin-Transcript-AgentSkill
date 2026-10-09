"""Safe YAML-frontmatter Markdown rendering with atomic no-overwrite writes."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import math
import os
import re
import secrets
import string
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .naming import candidate_output_paths
from .text_safety import show_bidi_controls, strip_display_controls

_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_LINE_BREAK = re.compile(r"(\r\n|\r|\n)")
_NON_LINEBREAK_CONTROLS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
# Leaves bounded room for a supported 256 KiB terminology ruleset after its
# archive JSON is quoted again as a YAML scalar.
MAX_FRONTMATTER_CHARACTERS = 4 * 1024 * 1024


def strip_control_characters(text: str) -> str:
    """Remove terminal and bidi controls before displaying an untrusted label."""
    return strip_display_controls(text)


def escape_markdown_text(text: str) -> str:
    """Escape untrusted text so CommonMark displays it literally.

    Escaping every ASCII punctuation character prevents inline syntax, links,
    images, and raw HTML. Leading spaces and tabs are emitted as character
    references so they cannot turn a line into an indented code block.
    Character references render as the original whitespace in Markdown views.
    """
    # Keep control bytes from being interpreted by terminals or embedded in
    # generated Markdown, including the title heading and transcript body.
    text = show_bidi_controls(_NON_LINEBREAK_CONTROLS.sub("", text))
    chunks = _LINE_BREAK.split(text)
    escaped: list[str] = []
    for index, chunk in enumerate(chunks):
        if index % 2:
            escaped.append(chunk)
            continue
        leading_length = len(chunk) - len(chunk.lstrip(" \t"))
        escaped.extend("&#32;" if char == " " else "&#9;" for char in chunk[:leading_length])
        escaped.extend(
            "\\" + char if char in string.punctuation else char
            for char in chunk[leading_length:]
        )
    return "".join(escaped)


def _yaml_scalar(value: Any) -> str:
    # JSON's scalar syntax is a safe subset of YAML 1.2.  Strings use explicit
    # quotes, so titles containing colons, hashes, quotes or newlines stay data.
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("frontmatter numbers must be finite")
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise TypeError(f"unsupported frontmatter value type: {type(value).__name__}")


def serialize_frontmatter(metadata: Mapping[str, Any]) -> str:
    """Serialize an ordered mapping as safe YAML scalar fields."""
    lines = ["---"]
    for key, value in metadata.items():
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            raise ValueError(f"invalid frontmatter key: {key!r}")
        lines.append(f"{key}: {_yaml_scalar(value)}")
    lines.append("---")
    serialized = "\n".join(lines)
    # Rendered Markdown adds a newline after the closing delimiter, which is
    # included in the parser's bounded read.
    if len(serialized) + 1 > MAX_FRONTMATTER_CHARACTERS:
        raise ValueError(
            f"frontmatter exceeds {MAX_FRONTMATTER_CHARACTERS} characters"
        )
    return serialized


def render_transcript_markdown(
    title: str,
    transcript: str,
    metadata: Mapping[str, Any],
) -> str:
    """Build the primary transcript Markdown document without altering text."""
    title = strip_control_characters(title)
    fields = {"title": title}
    fields.update((key, value) for key, value in metadata.items() if key != "title")
    body = transcript.strip()
    return (
        f"{serialize_frontmatter(fields)}\n\n"
        f"# {escape_markdown_text(title)}\n\n"
        "> 本文为自动语音识别逐字稿，未经人工逐字校对。\n\n"
        f"## 口播逐字稿\n\n{escape_markdown_text(body)}\n"
    )


def _atomic_publish(path: Path, content: str) -> None:
    """Publish a same-directory temporary file atomically without replacement."""
    temporary: Path | None = None
    published = False
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # A hard link is an atomic create-if-absent operation on the same
        # filesystem.  Unlike os.replace, it cannot clobber a manual file if a
        # competing writer creates the destination after our initial check.
        _publish_no_replace(temporary, path)
        published = True
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    if published and os.name != "nt":
        _fsync_directory(path.parent)


def _publish_no_replace(source: Path, destination: Path) -> None:
    """Publish atomically without replacement, requesting durable rename on Windows."""
    if os.name != "nt":
        os.link(source, destination)
        return

    _move_path_write_through(source, destination)


def _fsync_directory(path: Path) -> None:
    """Persist POSIX directory-entry changes after publishing an output file."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ensure_output_directory(path: Path) -> None:
    """Create an output directory and reconcile its ancestor entries on POSIX."""
    if os.name == "nt":
        _ensure_windows_output_directory(path)
        return

    path.mkdir(parents=True, exist_ok=True)
    current = path.resolve(strict=True).parent
    while True:
        _fsync_directory(current)
        if current.parent == current:
            break
        current = current.parent


def _ensure_windows_output_directory(path: Path) -> None:
    """Serialize and durably create missing Windows output directories."""
    absolute = Path(os.path.abspath(path)).resolve(strict=False)
    mutex_name = (
        "Local\\DouyinTranscriptOutputDir-"
        + hashlib.sha256(
            os.path.normcase(os.fspath(absolute)).casefold().encode("utf-16le")
        ).hexdigest()
    )
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    create_mutex.restype = wintypes.HANDLE
    wait_for_single_object = kernel32.WaitForSingleObject
    wait_for_single_object.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    wait_for_single_object.restype = wintypes.DWORD
    release_mutex = kernel32.ReleaseMutex
    release_mutex.argtypes = (wintypes.HANDLE,)
    release_mutex.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    mutex = create_mutex(None, False, mutex_name)
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    owned = False
    try:
        wait_result = wait_for_single_object(mutex, 30_000)
        if wait_result in {0, 0x00000080}:  # WAIT_OBJECT_0 / WAIT_ABANDONED
            owned = True
        elif wait_result == 0x00000102:  # WAIT_TIMEOUT
            raise TimeoutError("timed out waiting to create the output directory")
        else:
            raise ctypes.WinError(ctypes.get_last_error())
        _ensure_windows_output_directory_locked(absolute)
    finally:
        if owned:
            release_mutex(mutex)
        close_handle(mutex)


def _ensure_windows_output_directory_locked(absolute: Path) -> None:
    """Create each missing path component while holding its named mutex."""
    missing: list[Path] = []
    probe = absolute
    while not probe.exists():
        missing.append(probe)
        parent = probe.parent
        if parent == probe:
            raise FileNotFoundError(os.fspath(probe))
        probe = parent
    if not probe.is_dir():
        raise NotADirectoryError(os.fspath(probe))

    for directory in reversed(missing):
        if directory.exists():
            raise FileExistsError(
                errno.EEXIST,
                os.strerror(errno.EEXIST),
                os.fspath(directory),
            )
        staging_directory = _create_windows_staging_directory(directory.parent)
        try:
            _move_path_write_through(staging_directory, directory)
        except OSError as move_error:
            try:
                staging_directory.rmdir()
            except OSError as cleanup_error:
                raise cleanup_error from move_error
            raise


def _create_windows_staging_directory(parent: Path) -> Path:
    """Create a random same-parent staging directory, including long paths."""
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_directory = kernel32.CreateDirectoryW
    create_directory.argtypes = (wintypes.LPCWSTR, wintypes.LPVOID)
    create_directory.restype = wintypes.BOOL

    for _ in range(32):
        candidate = parent / f".douyin-tmp-{secrets.token_hex(8)}"
        if create_directory(_windows_extended_path(candidate), None):
            return candidate
        winerror = ctypes.get_last_error()
        if winerror not in {80, 183}:  # ERROR_FILE_EXISTS / ERROR_ALREADY_EXISTS
            raise ctypes.WinError(winerror)
    raise FileExistsError(errno.EEXIST, "could not allocate a staging directory", os.fspath(parent))


def _move_path_write_through(source: Path, destination: Path) -> None:
    """Move a same-directory file or directory without replacement on Windows."""
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    move_file = kernel32.MoveFileExW
    move_file.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
    move_file.restype = wintypes.BOOL
    movefile_write_through = 0x00000008

    source_name = _windows_extended_path(source)
    destination_name = _windows_extended_path(destination)
    if move_file(source_name, destination_name, movefile_write_through):
        return

    winerror = ctypes.get_last_error()
    if winerror in {80, 183}:
        # Only documented already-exists errors are filename collisions. A
        # generic failure must remain visible even if a target appeared too.
        raise FileExistsError(
            errno.EEXIST,
            os.strerror(errno.EEXIST),
            os.fspath(destination),
        )
    raise ctypes.WinError(winerror)


def _windows_extended_path(path: Path) -> str:
    """Return an absolute extended-length Windows path for direct Win32 calls."""
    absolute = os.path.abspath(path)
    if absolute.startswith("\\\\?\\"):
        return absolute
    if absolute.startswith("\\\\"):
        return "\\\\?\\UNC\\" + absolute[2:]
    return "\\\\?\\" + absolute


def write_transcript_markdown(
    output_dir: Path,
    title: str,
    transcript: str,
    metadata: Mapping[str, Any],
    *,
    video_id: str | None = None,
    extension: str = ".md",
) -> Path:
    """Atomically save UTF-8 Markdown and keep existing files safe.

    Filename collisions receive stable suffixes, so retries never overwrite
    prior output. Reuse decisions belong to the task store, which can validate
    a private content digest rather than trusting public frontmatter.
    """
    destination_dir = Path(output_dir).expanduser()
    _ensure_output_directory(destination_dir)
    fields = {"title": title}
    fields.update((key, value) for key, value in metadata.items() if key != "title")
    if video_id is not None:
        fields["video_id"] = video_id
    content = render_transcript_markdown(title, transcript, fields)
    for path in candidate_output_paths(destination_dir, title, video_id, extension=extension):
        if path.exists():
            continue
        try:
            _atomic_publish(path, content)
            return path
        except FileExistsError:
            continue
    # Keep API consistent with path selection and provide an explicit failure.
    raise FileExistsError(f"unable to find an unused transcript filename under {destination_dir}")
