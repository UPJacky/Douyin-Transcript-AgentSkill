"""Fail CI if Git-visible files contain sensitive artifacts or obvious secrets."""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

from spdx_terminal_safety import escape_terminal_controls

_FORBIDDEN_DIRECTORIES = {
    "browser-profile",
    "browser_profile",
    "cache",
    "media-cache",
    "media_cache",
    "models",
    "output",
    "douyin-transcripts",
}
_FORBIDDEN_SUFFIXES = {
    ".aac",
    ".aiff",
    ".amr",
    ".avi",
    ".db",
    ".key",
    ".flac",
    ".m4a",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".mpg",
    ".mpeg",
    ".ogg",
    ".opus",
    ".part",
    ".pem",
    ".sqlite",
    ".sqlite3",
    ".wav",
    ".webm",
}
_MODEL_WEIGHT_SUFFIXES = {
    ".bin",
    ".engine",
    ".gguf",
    ".onnx",
    ".pth",
    ".pt",
    ".safetensors",
    ".tflite",
}
_SECRET_FILENAMES = {"cookies.txt", "cookies.json", "cookie.txt", "cookie.json"}
_MAX_TEXT_FILE_BYTES = 16 * 1024 * 1024
_FILE_ATTRIBUTE_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class _UnsafeGitPathError(OSError):
    """Raised when a Git-visible path cannot be read without following aliases."""


_SECRET_PATTERNS = (
    (
        "private-key material",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "GitHub access token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{30,})\b"),
    ),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    (
        "credential assignment",
        re.compile(
            r"(?i)\b(?:access_token|refresh_token|client_secret|sessionid|csrf_token)"
            r"\s*[:=]\s*[\"']?[A-Za-z0-9._=\-]{16,}"
        ),
    ),
)
_PERSONAL_WINDOWS_PROFILE_PATH = re.compile(
    r"(?i)(?<![A-Z0-9_])[A-Z]:(?:\\{1,2}|/)Users(?:\\{1,2}|/)"
    r"(?!Example(?:\\{1,2}|/|$)|USERNAME(?:\\{1,2}|/|$)|<[^>]+>(?:\\{1,2}|/|$))"
    r"[^\\/\s\"'<>]+"
)


def path_violations(paths: list[str]) -> list[tuple[str, str]]:
    """Return forbidden path diagnostics without reading file contents."""
    violations: list[tuple[str, str]] = []
    for name in paths:
        parts = _git_visible_path_parts(name)
        if parts is None:
            violations.append((name, "unsafe repository-relative path"))
            continue
        path = PurePosixPath(*parts)
        directory_parts = {part.casefold() for part in path.parts[:-1]}
        suffix = path.suffix.casefold()
        basename = path.name.casefold()
        reason = None
        if directory_parts & _FORBIDDEN_DIRECTORIES:
            reason = "sensitive data directory"
        elif suffix in _MODEL_WEIGHT_SUFFIXES:
            reason = "model weight or inference artifact"
        elif suffix in _FORBIDDEN_SUFFIXES:
            reason = "sensitive media, database, key, or partial file"
        elif basename in _SECRET_FILENAMES:
            reason = "browser cookie file"
        elif basename == ".env" or (
            basename.startswith(".env.") and basename != ".env.example"
        ):
            reason = "environment file"
        elif basename.endswith(".md.tmp"):
            reason = "temporary transcript file"
        if reason:
            violations.append((name, reason))
    return violations


def _git_visible_path_parts(name: str) -> tuple[str, ...] | None:
    """Accept only canonical Git paths that cannot escape on any supported OS."""
    if not name or "\\" in name or "\0" in name:
        return None
    posix_path = PurePosixPath(name)
    windows_path = PureWindowsPath(name)
    if (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or posix_path.as_posix() != name
        or any(part in {"", ".", ".."} for part in posix_path.parts)
        or any(0xD800 <= ord(char) <= 0xDFFF for char in name)
        or any(_unsafe_windows_component(part) for part in posix_path.parts)
    ):
        return None
    return posix_path.parts


def _unsafe_windows_component(part: str) -> bool:
    """Reject path components that Windows may reinterpret as another path."""
    windows_path = PureWindowsPath(part)
    device_name = part.split(".", 1)[0].rstrip(" .").casefold()
    return (
        windows_path.is_absolute()
        or bool(windows_path.drive)
        or ":" in part
        or part.endswith((" ", "."))
        or any(ord(char) < 32 for char in part)
        or device_name in {"con", "prn", "aux", "nul"}
        or re.fullmatch(r"(?:com|lpt)[1-9¹²³]", device_name) is not None
    )


def _open_posix_git_file(root: Path, parts: tuple[str, ...]):
    """Open a repository file by walking pinned directory descriptors."""
    required = ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")
    if (
        any(not hasattr(os, name) for name in required)
        or os.open not in os.supports_dir_fd
    ):
        raise _UnsafeGitPathError("safe descriptor-relative file access is unavailable")

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory_flags |= getattr(os, "O_CLOEXEC", 0)
    current_fd = os.open(root.anchor, directory_flags)
    file_fd: int | None = None
    try:
        components = (*root.parts[1:], *parts[:-1])
        for component in components:
            next_fd = os.open(component, directory_flags, dir_fd=current_fd)
            if not stat.S_ISDIR(os.fstat(next_fd).st_mode):
                os.close(next_fd)
                raise _UnsafeGitPathError(
                    "repository path component is not a directory"
                )
            os.close(current_fd)
            current_fd = next_fd

        file_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        file_flags |= getattr(os, "O_CLOEXEC", 0)
        file_fd = os.open(parts[-1], file_flags, dir_fd=current_fd)
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            raise _UnsafeGitPathError("Git-visible path is not a regular file")
        stream = os.fdopen(file_fd, "rb")
        file_fd = None
        return stream
    finally:
        os.close(current_fd)
        if file_fd is not None:
            os.close(file_fd)


def _open_windows_git_file(root: Path, parts: tuple[str, ...]):
    """Open through pinned Windows directory handles without following reparses."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    invalid_handle = ctypes.c_void_p(-1).value
    file_read_data = 0x0001
    file_list_directory = 0x0001
    file_read_attributes = 0x0080
    synchronize = 0x00100000
    file_share_read = 0x00000001
    file_share_write = 0x00000002
    file_share_delete = 0x00000004
    open_existing = 3
    file_flag_backup_semantics = 0x02000000
    file_flag_open_reparse_point = 0x00200000
    file_attribute_directory = 0x00000010
    file_attribute_device = 0x00000040
    file_open = 1
    file_non_directory_file = 0x00000040
    file_open_reparse_point = 0x00200000
    file_directory_file = 0x00000001
    file_synchronous_io_nonalert = 0x00000020
    obj_case_insensitive = 0x00000040
    file_type_disk = 1

    class FileTime(ctypes.Structure):
        _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

    class ByHandleFileInformation(ctypes.Structure):
        _fields_ = [
            ("attributes", wintypes.DWORD),
            ("creation_time", FileTime),
            ("last_access_time", FileTime),
            ("last_write_time", FileTime),
            ("volume_serial", wintypes.DWORD),
            ("file_size_high", wintypes.DWORD),
            ("file_size_low", wintypes.DWORD),
            ("number_of_links", wintypes.DWORD),
            ("file_index_high", wintypes.DWORD),
            ("file_index_low", wintypes.DWORD),
        ]

    class UnicodeString(ctypes.Structure):
        _fields_ = [
            ("length", wintypes.USHORT),
            ("maximum_length", wintypes.USHORT),
            ("buffer", wintypes.LPWSTR),
        ]

    class ObjectAttributes(ctypes.Structure):
        _fields_ = [
            ("length", wintypes.ULONG),
            ("root_directory", wintypes.HANDLE),
            ("object_name", ctypes.POINTER(UnicodeString)),
            ("attributes", wintypes.ULONG),
            ("security_descriptor", ctypes.c_void_p),
            ("security_quality_of_service", ctypes.c_void_p),
        ]

    class IoStatusBlock(ctypes.Structure):
        _fields_ = [("status", ctypes.c_void_p), ("information", ctypes.c_size_t)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ByHandleFileInformation),
    ]
    kernel.GetFileInformationByHandle.restype = wintypes.BOOL
    kernel.GetFileType.argtypes = [wintypes.HANDLE]
    kernel.GetFileType.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL

    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtCreateFile.argtypes = [
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.DWORD,
        ctypes.POINTER(ObjectAttributes),
        ctypes.POINTER(IoStatusBlock),
        ctypes.c_void_p,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
        ctypes.c_void_p,
        wintypes.ULONG,
    ]
    ntdll.NtCreateFile.restype = ctypes.c_long

    def close(handle: int | None) -> None:
        if handle is not None and handle != invalid_handle:
            kernel.CloseHandle(handle)

    def check_handle(handle: int, *, directory: bool) -> None:
        info = ByHandleFileInformation()
        if not kernel.GetFileInformationByHandle(handle, ctypes.byref(info)):
            raise OSError(
                ctypes.get_last_error(), "cannot inspect Git-visible file handle"
            )
        attributes = int(info.attributes)
        if attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
            raise _UnsafeGitPathError(
                "symbolic link or reparse point in Git-visible path"
            )
        if directory:
            if not attributes & file_attribute_directory:
                raise _UnsafeGitPathError(
                    "Git-visible path component is not a directory"
                )
        elif (
            attributes & (file_attribute_directory | file_attribute_device)
            or kernel.GetFileType(handle) != file_type_disk
        ):
            raise _UnsafeGitPathError("Git-visible path is not a regular file")

    def open_relative(parent_handle: int, component: str, *, directory: bool) -> int:
        encoded_name = component.encode("utf-16-le", errors="strict")
        name_length = len(encoded_name)
        if name_length > 0xFFFD:
            raise _UnsafeGitPathError("Git-visible path component is too long")
        name_buffer = ctypes.create_unicode_buffer(component)
        name = UnicodeString(
            name_length,
            name_length + ctypes.sizeof(ctypes.c_wchar),
            ctypes.cast(name_buffer, wintypes.LPWSTR),
        )
        attributes = ObjectAttributes(
            ctypes.sizeof(ObjectAttributes),
            parent_handle,
            ctypes.pointer(name),
            obj_case_insensitive,
            None,
            None,
        )
        io_status = IoStatusBlock()
        handle = wintypes.HANDLE()
        desired_access = file_read_attributes | synchronize
        share_access = file_share_read | file_share_write
        create_options = file_open_reparse_point | file_synchronous_io_nonalert
        if directory:
            desired_access |= file_list_directory
            create_options |= file_directory_file
            # Prevent a concurrent rename/replacement while this directory is
            # the root for the next relative open.
        else:
            desired_access |= file_read_data
            share_access |= file_share_delete
            create_options |= file_non_directory_file
        status = ntdll.NtCreateFile(
            ctypes.byref(handle),
            desired_access,
            ctypes.byref(attributes),
            ctypes.byref(io_status),
            None,
            0,
            share_access,
            file_open,
            create_options,
            None,
            0,
        )
        if status < 0 or handle.value in (None, invalid_handle):
            raise OSError(
                f"NtCreateFile failed with NTSTATUS 0x{status & 0xFFFFFFFF:08X}"
            )
        result = handle.value
        try:
            check_handle(result, directory=directory)
            return result
        except BaseException:
            close(result)
            raise

    root_anchor = Path(root.anchor)
    if not root_anchor.anchor or not PureWindowsPath(root.anchor).drive:
        raise _UnsafeGitPathError(
            "repository root must have an absolute Windows anchor"
        )
    root_handle = kernel.CreateFileW(
        str(root_anchor),
        file_read_attributes | file_list_directory,
        file_share_read | file_share_write,
        None,
        open_existing,
        file_flag_backup_semantics | file_flag_open_reparse_point,
        None,
    )
    if root_handle in (None, invalid_handle):
        raise OSError(ctypes.get_last_error(), "cannot open repository volume root")
    directory_handles = [int(root_handle)]
    leaf_handle: int | None = None
    descriptor: int | None = None
    try:
        check_handle(directory_handles[0], directory=True)
        for component in (*root.parts[1:], *parts[:-1]):
            next_handle = open_relative(
                directory_handles[-1], component, directory=True
            )
            # Keep every ancestor open without FILE_SHARE_DELETE until the
            # leaf is opened, so no parent can be moved outside the root while
            # a deeper component is being resolved.
            directory_handles.append(next_handle)

        leaf_handle = open_relative(directory_handles[-1], parts[-1], directory=False)
        descriptor = msvcrt.open_osfhandle(
            leaf_handle, os.O_RDONLY | getattr(os, "O_BINARY", 0)
        )
        leaf_handle = None
        stream = os.fdopen(descriptor, "rb")
        descriptor = None
        return stream
    finally:
        if descriptor is not None:
            os.close(descriptor)
        close(leaf_handle)
        for handle in reversed(directory_handles):
            close(handle)


def _open_git_visible_file(root: Path, parts: tuple[str, ...]):
    if os.name == "posix":
        return _open_posix_git_file(root, parts)
    if os.name == "nt":
        return _open_windows_git_file(root, parts)
    raise _UnsafeGitPathError(
        "safe Git-visible file access is unsupported on this platform"
    )


def content_violations(name: str, content: str) -> list[tuple[str, str]]:
    """Return sensitive-content indicators without echoing matched values."""
    found = [reason for reason, pattern in _SECRET_PATTERNS if pattern.search(content)]
    if _PERSONAL_WINDOWS_PROFILE_PATH.search(content):
        found.append("personal Windows user-profile path")
    return [(name, reason) for reason in found]


def _scan_text_file(name: str, stream) -> list[tuple[str, str]]:
    """Scan a whole bounded UTF-8 file so patterns cannot fall across a lost boundary."""
    content = stream.read(_MAX_TEXT_FILE_BYTES + 1)
    if len(content) > _MAX_TEXT_FILE_BYTES:
        return [(name, "exceeds content scan size limit")]
    if b"\0" in content:
        return [(name, "binary file requires explicit review")]
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return [(name, "non-UTF-8 file requires explicit review")]
    return content_violations(name, text)


def git_visible_paths(root: Path) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(
            "git ls-files failed; cannot verify sensitive repository files"
        )
    return [
        item.decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    ]


def scan_repository(root: Path) -> list[tuple[str, str]]:
    """Inspect Git-visible names and UTF-8 text files under ``root``."""
    root = Path(root).resolve(strict=True)
    paths = git_visible_paths(root)
    violations = path_violations(paths)
    for name in paths:
        parts = _git_visible_path_parts(name)
        if parts is None:
            continue
        try:
            with _open_git_visible_file(root, parts) as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):
                    violations.append((name, "Git-visible path is not a regular file"))
                    continue
                if info.st_size > _MAX_TEXT_FILE_BYTES:
                    violations.append((name, "exceeds content scan size limit"))
                    continue
                violations.extend(_scan_text_file(name, stream))
        except _UnsafeGitPathError:
            violations.append(
                (name, "symbolic link or reparse point cannot be content-scanned")
            )
        except OSError:
            violations.append((name, "unable to inspect Git-visible file"))
    return violations


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    try:
        violations = scan_repository(root)
    except (OSError, RuntimeError) as exc:
        print(f"Sensitive-file check failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    if violations:
        for name, reason in violations:
            safe_name = escape_terminal_controls(name)
            print(
                f"Sensitive-file check failed: {safe_name}: {reason}", file=sys.stderr
            )
        print("Matched credential values are never displayed.", file=sys.stderr)
        return 1
    print("Sensitive-file check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
