"""Helpers for writing generated evidence without following redirected paths."""

from __future__ import annotations

import os
import secrets
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterable, Iterator, TextIO, cast

_FILE_ATTRIBUTE_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class SafeOutputError(OSError):
    """Raised when an output path contains a symbolic link or reparse point."""


def _is_reparse_point(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT
    )


def _check_directory_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if _is_reparse_point(info):
            raise SafeOutputError(
                "output path contains a symbolic link or reparse point"
            )
        if not stat.S_ISDIR(info.st_mode):
            raise SafeOutputError("output parent path must contain only directories")


def _check_components(path: Path) -> None:
    _check_directory_components(path.parent)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if _is_reparse_point(info):
        raise SafeOutputError("output path contains a symbolic link or reparse point")
    if not stat.S_ISREG(info.st_mode):
        raise SafeOutputError("output destination must be a regular file")


@contextmanager
def _open_parent_directory(
    path: Path, *, create: bool = True
) -> Iterator[int | list[int]]:
    """Pin every parent directory while creating and replacing the output."""
    if os.name == "nt":
        handles = _open_windows_parent(path, create=create)
        try:
            yield handles
        finally:
            _close_windows_parent(handles)
        return

    required = (os.open, os.mkdir, os.replace)
    if not all(function in os.supports_dir_fd for function in required):
        raise SafeOutputError("safe output requires directory-relative file operations")
    if not getattr(os, "O_NOFOLLOW", 0) or not getattr(os, "O_DIRECTORY", 0):
        raise SafeOutputError("safe output requires no-follow directory handles")

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        descriptor = os.open(path.anchor, flags)
        try:
            for component in path.parts[1:]:
                try:
                    child = os.open(component, flags, dir_fd=descriptor)
                except FileNotFoundError:
                    if not create:
                        raise SafeOutputError("output parent directory does not exist")
                    os.mkdir(component, dir_fd=descriptor)
                    child = os.open(component, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            yield descriptor
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise SafeOutputError("cannot safely open output parent directory") from exc


def _open_windows_parent(path: Path, *, create: bool) -> list[int]:
    """Open each Windows directory without delete sharing to prevent path swaps."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    get_info = kernel32.GetFileInformationByHandle
    get_info.argtypes = (wintypes.HANDLE, ctypes.c_void_p)
    get_info.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    class _FileInformation(ctypes.Structure):
        _fields_ = [
            ("attributes", wintypes.DWORD),
            ("creation_low", wintypes.DWORD),
            ("creation_high", wintypes.DWORD),
            ("access_low", wintypes.DWORD),
            ("access_high", wintypes.DWORD),
            ("write_low", wintypes.DWORD),
            ("write_high", wintypes.DWORD),
            ("volume_serial", wintypes.DWORD),
            ("size_high", wintypes.DWORD),
            ("size_low", wintypes.DWORD),
            ("links", wintypes.DWORD),
            ("index_high", wintypes.DWORD),
            ("index_low", wintypes.DWORD),
        ]

    invalid_handle = ctypes.c_void_p(-1).value
    handles: list[int] = []

    def open_directory(directory: Path) -> int:
        handle = create_file(
            os.fspath(directory),
            0x80,  # FILE_READ_ATTRIBUTES
            0x1 | 0x2,  # FILE_SHARE_READ | FILE_SHARE_WRITE; deny FILE_SHARE_DELETE
            None,
            3,  # OPEN_EXISTING
            0x02000000 | 0x00200000,  # BACKUP_SEMANTICS | OPEN_REPARSE_POINT
            None,
        )
        if handle == invalid_handle:
            error = ctypes.get_last_error()
            raise ctypes.WinError(error)
        info = _FileInformation()
        if not get_info(handle, ctypes.byref(info)):
            error = ctypes.get_last_error()
            close_handle(handle)
            raise ctypes.WinError(error)
        if info.attributes & (0x400 | 0x10) != 0x10:
            close_handle(handle)
            raise SafeOutputError(
                "output parent path contains a reparse point or non-directory"
            )
        return int(handle)

    try:
        current = Path(path.anchor)
        handles.append(open_directory(current))
        for component in path.parts[1:]:
            current /= component
            try:
                child = open_directory(current)
            except OSError as exc:
                if getattr(exc, "winerror", None) not in (2, 3):
                    raise
                if not create:
                    raise SafeOutputError(
                        "output parent directory does not exist"
                    ) from exc
                try:
                    os.mkdir(current)
                except FileExistsError:
                    pass
                child = open_directory(current)
            handles.append(child)
        return handles
    except BaseException:
        for handle in reversed(handles):
            close_handle(handle)
        raise


def _close_windows_parent(handles: list[int]) -> None:
    import ctypes

    close_handle = ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle
    close_handle.argtypes = (ctypes.c_void_p,)
    for handle in reversed(handles):
        close_handle(handle)


def _check_destination_leaf(destination: Path) -> None:
    try:
        info = destination.lstat()
    except FileNotFoundError:
        return
    if _is_reparse_point(info):
        raise SafeOutputError("output path contains a symbolic link or reparse point")
    if not stat.S_ISREG(info.st_mode):
        raise SafeOutputError("output destination must be a regular file")


def _absolute_output_path(path: Path) -> Path:
    destination = Path(os.path.abspath(os.fspath(path)))
    if not destination.name:
        raise SafeOutputError("output destination must name a file")
    return destination


@contextmanager
def _open_new_file(
    path: Path, *, binary: bool, create_parents: bool = True, mode: int = 0o600
) -> Iterator[BinaryIO | TextIO]:
    destination = _absolute_output_path(path)
    _check_components(destination)
    with _open_parent_directory(destination.parent, create=create_parents) as parent:
        _check_destination_leaf(destination)
        if os.name == "nt":
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
            descriptor = os.open(destination, flags, mode)
            mode = "wb" if binary else "w"
        else:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
            descriptor = os.open(destination.name, flags, mode, dir_fd=int(parent))
            mode = "wb" if binary else "w"

        try:
            if binary:
                with os.fdopen(descriptor, mode) as stream:
                    yield stream
                    stream.flush()
                    os.fsync(stream.fileno())
            else:
                with os.fdopen(
                    descriptor, mode, encoding="utf-8", newline="\n"
                ) as stream:
                    yield stream
                    stream.flush()
                    os.fsync(stream.fileno())
        except BaseException:
            try:
                if os.name == "nt":
                    destination.unlink(missing_ok=True)
                else:
                    os.unlink(destination.name, dir_fd=int(parent))
            except FileNotFoundError:
                pass
            raise


@contextmanager
def open_new_text(path: Path, *, create_parents: bool = True) -> Iterator[TextIO]:
    """Open a new text output exclusively beneath a pinned, link-free parent."""
    with _open_new_file(path, binary=False, create_parents=create_parents) as stream:
        yield cast(TextIO, stream)


@contextmanager
def open_new_binary(
    path: Path, *, create_parents: bool = True, mode: int = 0o600
) -> Iterator[BinaryIO]:
    """Open a new binary output exclusively beneath a pinned, link-free parent."""
    with _open_new_file(
        path, binary=True, create_parents=create_parents, mode=mode
    ) as stream:
        yield cast(BinaryIO, stream)


def write_new_binary(
    path: Path, content: bytes, *, create_parents: bool = True, mode: int = 0o600
) -> Path:
    """Create a binary output exclusively and remove it if writing fails."""
    with open_new_binary(path, create_parents=create_parents, mode=mode) as stream:
        stream.write(content)
    return _absolute_output_path(path)


def write_new_text(
    path: Path, content: str | Iterable[str], *, mode: int = 0o600
) -> Path:
    """Atomically publish new text with mode filtered by umask on POSIX."""
    destination = _absolute_output_path(path)
    _check_components(destination)
    temporary_path: str | None = None
    temporary_name: str | None = None
    with _open_parent_directory(destination.parent) as parent:
        _check_destination_leaf(destination)
        try:
            if os.name != "nt" and os.link not in os.supports_dir_fd:
                raise SafeOutputError(
                    "safe output requires directory-relative hard links"
                )
            descriptor = int(parent) if os.name != "nt" else None
            for _ in range(10):
                temporary_name = f".codex-output-{secrets.token_hex(16)}.tmp"
                try:
                    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                    if os.name != "nt":
                        flags |= os.O_NOFOLLOW
                    if hasattr(os, "O_BINARY"):
                        flags |= os.O_BINARY
                    if os.name == "nt":
                        temporary_path = os.fspath(destination.parent / temporary_name)
                        fd = os.open(temporary_path, flags, mode)
                    else:
                        fd = os.open(temporary_name, flags, mode, dir_fd=descriptor)
                    break
                except FileExistsError:
                    continue
            else:
                raise SafeOutputError("cannot allocate temporary output file")

            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                chunks = (content,) if isinstance(content, str) else content
                for chunk in chunks:
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())

            if os.name == "nt":
                os.link(temporary_path, destination)
            else:
                os.link(
                    temporary_name,
                    destination.name,
                    src_dir_fd=descriptor,
                    dst_dir_fd=descriptor,
                    follow_symlinks=False,
                )
            return destination
        finally:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass
            elif temporary_name is not None and os.name != "nt":
                try:
                    os.unlink(temporary_name, dir_fd=int(parent))
                except FileNotFoundError:
                    pass


def validate_output_directory(path: Path) -> Path:
    """Reject a missing, linked, or non-directory output directory."""
    directory = Path(os.path.abspath(os.fspath(path)))
    _check_directory_components(directory)
    with _open_parent_directory(directory, create=False):
        pass
    return directory


def unlink_output(path: Path, *, missing_ok: bool = False) -> None:
    """Unlink an output without traversing a symbolic-link/reparse parent."""
    destination = _absolute_output_path(path)
    _check_directory_components(destination.parent)
    with _open_parent_directory(destination.parent, create=False) as parent:
        try:
            if os.name == "nt":
                destination.unlink()
            else:
                os.unlink(destination.name, dir_fd=int(parent))
        except FileNotFoundError:
            if not missing_ok:
                raise


def write_atomic_text(path: Path, content: str, *, create_parents: bool = True) -> Path:
    """Atomically replace a regular output file without following links."""
    destination = _absolute_output_path(path)

    _check_components(destination)
    temporary_path: str | None = None
    temporary_name: str | None = None
    with _open_parent_directory(destination.parent, create=create_parents) as parent:
        _check_destination_leaf(destination)
        try:
            if os.name == "nt":
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    newline="\n",
                    dir=destination.parent,
                    delete=False,
                ) as stream:
                    temporary_path = stream.name
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary_path, destination)
                temporary_path = None
            else:
                descriptor = int(parent)
                for _ in range(10):
                    temporary_name = f".codex-output-{secrets.token_hex(16)}.tmp"
                    try:
                        fd = os.open(
                            temporary_name,
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                            0o600,
                            dir_fd=descriptor,
                        )
                        break
                    except FileExistsError:
                        continue
                else:
                    raise SafeOutputError("cannot allocate temporary output file")
                try:
                    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                        stream.write(content)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(
                        temporary_name,
                        destination.name,
                        src_dir_fd=descriptor,
                        dst_dir_fd=descriptor,
                    )
                    temporary_name = None
                finally:
                    if temporary_name is not None:
                        try:
                            os.unlink(temporary_name, dir_fd=descriptor)
                        except FileNotFoundError:
                            pass
            return destination
        finally:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass
