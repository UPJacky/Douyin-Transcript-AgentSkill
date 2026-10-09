"""Bounded, opt-in cleanup for files owned by the application media cache.

The cache is deliberately treated as a flat directory. Only filenames emitted
by :mod:`downloader` are managed; directories, links, and unrelated files are
never traversed or removed. Cleanup defaults to a preview and callers should
pass media paths referenced by active tasks in ``protected_paths``.
"""

from __future__ import annotations

import math
import os
import re
import stat
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

_CACHE_DIRECTORY_NAME = "media-cache"
_MEDIA_NAME = re.compile(
    r"(?P<video_id>[0-9]{1,32})-(?:audio|video)-[0-9a-f]{16}"
    r"\.(?:aac|m4a|mp3|ogg|wav|webm|mp4|mov|mkv|media)\Z"
)
_PART_NAME = re.compile(r"\.(?P<video_id>[0-9]{1,32})-(?:audio|video)-[0-9a-f]{32}\.part\Z")
_REPARSE_POINT = 0x400


class CacheError(ValueError):
    """The supplied cache path or cleanup policy is unsafe or invalid."""


@dataclass(frozen=True, slots=True)
class CacheEntry:
    """One recognized ordinary file directly inside the application cache."""

    path: Path
    kind: str
    size_bytes: int
    modified_at: float
    age_seconds: float
    protected: bool
    device: int
    inode: int
    modified_ns: int
    changed_ns: int
    cache_device: int
    cache_inode: int
    video_id: str


@dataclass(frozen=True, slots=True)
class CacheSnapshot:
    """Read-only view of recognized media and temporary cache files."""

    cache_dir: Path
    entries: tuple[CacheEntry, ...]
    media_bytes: int
    protected_media_bytes: int


@dataclass(frozen=True, slots=True)
class CacheCleanupResult:
    """Preview or result of an explicit cache retention operation."""

    cache_dir: Path
    selected_paths: tuple[Path, ...]
    selected_bytes: int
    removed_paths: tuple[Path, ...]
    skipped_paths: tuple[Path, ...]
    remaining_media_bytes: int
    dry_run: bool
    max_bytes: int | None
    max_age_seconds: float | None


DeletionCoordinator = Callable[[CacheEntry, Callable[[], bool]], bool]


def inspect_media_cache(
    cache_dir: str | os.PathLike[str],
    *,
    protected_paths: Iterable[str | os.PathLike[str]] = (),
    protected_video_ids: Iterable[str] = (),
    now: float | None = None,
) -> CacheSnapshot:
    """List recognized cache files without following links or visiting subdirs.

    ``protected_paths`` normally contains the ``media_path`` values for active
    tasks. ``protected_video_ids`` protects the cache entry for a live download
    before its final media path has been recorded. Both path identity and file
    identity are considered, so an alias to a protected cache file also
    protects it.
    """
    root = _validate_cache_directory(cache_dir)
    current_time = _validate_now(now)
    protected_names, protected_inodes = _protected_identities(protected_paths)
    protected_ids = _normalize_video_ids(protected_video_ids)
    entries: list[CacheEntry] = []

    # Retain the directory identity from the same snapshot as the entries.
    # Windows deletion opens this exact directory and addresses children
    # relative to its handle, so replacing the cache path cannot redirect it.
    try:
        root_info = root.lstat()
    except OSError as exc:
        raise CacheError(f"cannot inspect media cache directory ({type(exc).__name__})") from None
    if not stat.S_ISDIR(root_info.st_mode) or _is_reparse_point(root_info):
        raise CacheError("media cache path changed during inspection")

    for name, info in _scan_directory(root):
        kind = _recognized_kind(name)
        if kind is None or not stat.S_ISREG(info.st_mode) or int(info.st_nlink) != 1:
            continue
        path = root / name
        identity = (int(info.st_dev), int(info.st_ino))
        id_match = _PART_NAME.fullmatch(name) or _MEDIA_NAME.fullmatch(name)
        protected = (
            _path_identity(path) in protected_names
            or identity in protected_inodes
            or (id_match is not None and id_match.group("video_id") in protected_ids)
        )
        entries.append(
            CacheEntry(
                path=path,
                kind=kind,
                size_bytes=max(0, int(info.st_size)),
                modified_at=float(info.st_mtime),
                age_seconds=max(0.0, current_time - float(info.st_mtime)),
                protected=protected,
                device=int(info.st_dev),
                inode=int(info.st_ino),
                modified_ns=int(getattr(info, "st_mtime_ns", info.st_mtime * 1_000_000_000)),
                changed_ns=int(getattr(info, "st_ctime_ns", info.st_ctime * 1_000_000_000)),
                cache_device=int(root_info.st_dev),
                cache_inode=int(root_info.st_ino),
                video_id=id_match.group("video_id"),
            )
        )

    entries.sort(key=lambda item: (item.modified_at, item.path.name))
    frozen_entries = tuple(entries)
    return CacheSnapshot(
        cache_dir=root,
        entries=frozen_entries,
        media_bytes=sum(item.size_bytes for item in frozen_entries if item.kind == "media"),
        protected_media_bytes=sum(
            item.size_bytes for item in frozen_entries if item.kind == "media" and item.protected
        ),
    )


def cleanup_media_cache(
    cache_dir: str | os.PathLike[str],
    *,
    protected_paths: Iterable[str | os.PathLike[str]] = (),
    protected_video_ids: Iterable[str] = (),
    allow_partial_cleanup: bool = False,
    max_bytes: int | None = None,
    max_age_seconds: float | None = None,
    dry_run: bool = True,
    now: float | None = None,
    deletion_coordinator: DeletionCoordinator | None = None,
) -> CacheCleanupResult:
    """Preview or perform age- and/or capacity-based cache cleanup.

    At least one retention limit must be explicit. Age cleanup removes stale
    downloader temporary files only when ``allow_partial_cleanup`` is enabled
    by a caller that has coordinated with active task claims. Capacity cleanup
    applies only to completed media and removes the oldest eligible files until
    the requested budget is met; protected files may cause the remaining cache
    to exceed that budget. The default is ``dry_run=True``. No directory is ever
    removed.
    """
    if max_bytes is None and max_age_seconds is None:
        raise CacheError("specify max_bytes and/or max_age_seconds")
    if max_bytes is not None and (
        isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 0
    ):
        raise CacheError("max_bytes must be a non-negative integer")
    if max_age_seconds is not None:
        if (
            isinstance(max_age_seconds, bool)
            or not isinstance(max_age_seconds, (int, float))
            or not math.isfinite(max_age_seconds)
            or max_age_seconds < 0
        ):
            raise CacheError("max_age_seconds must be a finite non-negative number")
        max_age_seconds = float(max_age_seconds)
    if not isinstance(dry_run, bool):
        raise CacheError("dry_run must be a boolean")
    if not isinstance(allow_partial_cleanup, bool):
        raise CacheError("allow_partial_cleanup must be a boolean")
    if deletion_coordinator is not None and not callable(deletion_coordinator):
        raise CacheError("deletion_coordinator must be callable")

    protected_ids = _normalize_video_ids(protected_video_ids)
    snapshot = inspect_media_cache(
        cache_dir,
        protected_paths=protected_paths,
        protected_video_ids=protected_ids,
        now=now,
    )
    selected: dict[str, CacheEntry] = {}

    if max_age_seconds is not None:
        for entry in snapshot.entries:
            if (
                not entry.protected
                and (entry.kind != "partial" or allow_partial_cleanup)
                and entry.age_seconds > max_age_seconds
            ):
                selected[_path_identity(entry.path)] = entry

    if max_bytes is not None:
        current_media_bytes = sum(
            entry.size_bytes for entry in snapshot.entries if entry.kind == "media"
        )
        already_selected = sum(
            entry.size_bytes for entry in selected.values() if entry.kind == "media"
        )
        projected_media_bytes = current_media_bytes - already_selected
        if projected_media_bytes > max_bytes:
            candidates = sorted(
                (
                    entry
                    for entry in snapshot.entries
                    if entry.kind == "media"
                    and not entry.protected
                    and _path_identity(entry.path) not in selected
                ),
                key=lambda item: (item.modified_at, item.path.name),
            )
            for entry in candidates:
                selected[_path_identity(entry.path)] = entry
                projected_media_bytes -= entry.size_bytes
                if projected_media_bytes <= max_bytes:
                    break

    planned = tuple(sorted(selected.values(), key=lambda item: (item.modified_at, item.path.name)))
    removed: list[Path] = []
    skipped: list[Path] = []
    if not dry_run:
        for entry in planned:
            unlink = partial(_unlink_if_unchanged, snapshot.cache_dir, entry)
            removed_entry = (
                deletion_coordinator(entry, unlink)
                if deletion_coordinator is not None
                else unlink()
            )
            if removed_entry:
                removed.append(entry.path)
            else:
                skipped.append(entry.path)

    if dry_run:
        remaining_media_bytes = snapshot.media_bytes - sum(
            entry.size_bytes for entry in planned if entry.kind == "media"
        )
    else:
        final_snapshot = inspect_media_cache(
            snapshot.cache_dir,
            protected_paths=protected_paths,
            protected_video_ids=protected_ids,
            now=now,
        )
        remaining_media_bytes = final_snapshot.media_bytes
    return CacheCleanupResult(
        cache_dir=snapshot.cache_dir,
        selected_paths=tuple(entry.path for entry in planned),
        selected_bytes=sum(entry.size_bytes for entry in planned),
        removed_paths=tuple(removed),
        skipped_paths=tuple(skipped),
        remaining_media_bytes=remaining_media_bytes,
        dry_run=dry_run,
        max_bytes=max_bytes,
        max_age_seconds=max_age_seconds,
    )


def _validate_cache_directory(cache_dir: str | os.PathLike[str]) -> Path:
    if not isinstance(cache_dir, (str, os.PathLike)):
        raise CacheError("cache_dir must be a path")
    supplied = Path(cache_dir).expanduser()
    if not supplied.is_absolute():
        supplied = Path.cwd() / supplied
    root = Path(os.path.abspath(supplied))
    if root.name != _CACHE_DIRECTORY_NAME:
        raise CacheError(f"cache directory must be named {_CACHE_DIRECTORY_NAME}")

    # Reject symlink/reparse components so the cache path cannot redirect the
    # operation to a user source, output, model, or browser profile directory.
    component = Path(root.anchor)
    for part in root.parts[1:]:
        component /= part
        try:
            info = component.lstat()
        except FileNotFoundError:
            if component == root:
                raise CacheError("media cache directory does not exist") from None
            raise CacheError("media cache path contains a missing component") from None
        except OSError as exc:
            raise CacheError(f"cannot inspect media cache path ({type(exc).__name__})") from None
        if _is_reparse_point(info) or stat.S_ISLNK(info.st_mode):
            raise CacheError("media cache path cannot contain a symbolic link or reparse point")
        if component != root and not stat.S_ISDIR(info.st_mode):
            raise CacheError("media cache parent is not a directory")
    try:
        info = root.lstat()
    except OSError as exc:
        raise CacheError(f"cannot inspect media cache directory ({type(exc).__name__})") from None
    if not stat.S_ISDIR(info.st_mode) or _is_reparse_point(info):
        raise CacheError("media cache path must be a real directory")
    return root


def _is_reparse_point(info: os.stat_result) -> bool:
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & _REPARSE_POINT)


def _scan_directory(root: Path) -> list[tuple[str, os.stat_result]]:
    """Read direct child metadata without following entry symlinks."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_fd: int | None = None
    try:
        if os.name != "nt":
            directory_fd = os.open(root, flags)
            if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
                raise CacheError("media cache path changed during inspection")
            iterator = os.scandir(directory_fd)
        else:
            iterator = os.scandir(root)
        with iterator as children:
            result: list[tuple[str, os.stat_result]] = []
            for child in children:
                try:
                    info = child.stat(follow_symlinks=False)
                    # Windows scandir's WIN32_FIND_DATA conversion may report
                    # zero link count and inode values. lstat obtains the
                    # handle-backed metadata without following reparse points.
                    if os.name == "nt":
                        info = (root / child.name).lstat()
                except OSError:
                    continue
                result.append((child.name, info))
            return result
    except CacheError:
        raise
    except OSError as exc:
        raise CacheError(f"cannot inspect media cache ({type(exc).__name__})") from None
    finally:
        if directory_fd is not None:
            os.close(directory_fd)


def _recognized_kind(name: str) -> str | None:
    if _MEDIA_NAME.fullmatch(name):
        return "media"
    if _PART_NAME.fullmatch(name):
        return "partial"
    return None


def _validate_now(now: float | None) -> float:
    if now is None:
        return time.time()
    if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now):
        raise CacheError("now must be a finite timestamp")
    return float(now)


def _path_identity(path: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _normalize_video_ids(values: Iterable[str]) -> set[str]:
    if isinstance(values, str):
        raise CacheError("protected_video_ids must contain decimal video IDs")
    try:
        identifiers = tuple(values)
    except TypeError as exc:
        raise CacheError("protected_video_ids must be an iterable of video IDs") from exc
    if any(
        not isinstance(value, str) or re.fullmatch(r"[0-9]{1,32}", value) is None
        for value in identifiers
    ):
        raise CacheError("protected_video_ids must contain decimal video IDs")
    return set(identifiers)


def _protected_identities(
    protected_paths: Iterable[str | os.PathLike[str]],
) -> tuple[set[str], set[tuple[int, int]]]:
    try:
        values = tuple(protected_paths)
    except TypeError as exc:
        raise CacheError("protected_paths must be an iterable of paths") from exc
    names: set[str] = set()
    inodes: set[tuple[int, int]] = set()
    for value in values:
        if not isinstance(value, (str, os.PathLike)):
            raise CacheError("protected_paths must contain only paths")
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        names.add(_path_identity(path))
        try:
            info = path.stat()
        except OSError:
            continue
        if stat.S_ISREG(info.st_mode):
            inodes.add((int(info.st_dev), int(info.st_ino)))
    return names, inodes


def _same_file(info: os.stat_result, entry: CacheEntry) -> bool:
    return (
        stat.S_ISREG(info.st_mode)
        and not _is_reparse_point(info)
        and int(info.st_dev) == entry.device
        and int(info.st_ino) == entry.inode
        and int(info.st_size) == entry.size_bytes
        and int(getattr(info, "st_mtime_ns", info.st_mtime * 1_000_000_000)) == entry.modified_ns
        and int(getattr(info, "st_ctime_ns", info.st_ctime * 1_000_000_000)) == entry.changed_ns
        and int(info.st_nlink) == 1
    )


def _unlink_if_unchanged(root: Path, entry: CacheEntry) -> bool:
    """Unlink one unchanged, single-link regular file from the pinned cache dir."""
    if entry.path.parent != root or _recognized_kind(entry.path.name) != entry.kind:
        return False
    if os.name != "nt" and hasattr(os, "O_NOFOLLOW") and os.supports_dir_fd:
        directory_fd: int | None = None
        file_fd: int | None = None
        try:
            directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
            directory_fd = os.open(root, directory_flags)
            file_flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
            file_fd = os.open(entry.path.name, file_flags, dir_fd=directory_fd)
            if not _same_file(os.fstat(file_fd), entry):
                return False
            current = os.stat(entry.path.name, dir_fd=directory_fd, follow_symlinks=False)
            if not _same_file(current, entry):
                return False
            os.unlink(entry.path.name, dir_fd=directory_fd)
            return True
        except OSError:
            return False
        finally:
            if file_fd is not None:
                os.close(file_fd)
            if directory_fd is not None:
                os.close(directory_fd)

    if os.name == "nt":
        return _unlink_windows_by_handle(root, entry)
    # On an unusual platform without the dirfd/O_NOFOLLOW path above, fail
    # closed instead of reintroducing a pathname-based replacement race.
    return False


def _unlink_windows_by_handle(root: Path, entry: CacheEntry) -> bool:
    """Delete a verified Windows file through a handle bound to its parent.

    The cache directory handle denies delete sharing and the child is opened
    relative to that handle using NtCreateFile. File identity and metadata are
    checked on the opened handle, then FILE_DISPOSITION_INFO marks that exact
    object for deletion. Any API or identity uncertainty fails closed.
    """
    import ctypes
    from ctypes import wintypes

    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    FILE_READ_ATTRIBUTES = 0x0080
    FILE_LIST_DIRECTORY = 0x0001
    DELETE = 0x00010000
    SYNCHRONIZE = 0x00100000
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    OPEN_EXISTING = 3
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    FILE_ATTRIBUTE_DIRECTORY = 0x00000010
    FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
    FILE_OPEN = 1
    FILE_NON_DIRECTORY_FILE = 0x00000040
    FILE_OPEN_REPARSE_POINT = 0x00200000
    FILE_SYNCHRONOUS_IO_NONALERT = 0x00000020
    OBJ_CASE_INSENSITIVE = 0x00000040
    FILE_DISPOSITION_INFO_CLASS = 4
    WINDOWS_EPOCH_TICKS = 116444736000000000

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

    class FileDispositionInfo(ctypes.Structure):
        _fields_ = [("delete_file", ctypes.c_ubyte)]

    if sys.version_info >= (3, 12):
        class FileId128(ctypes.Structure):
            _fields_ = [("identifier", ctypes.c_ubyte * 16)]

        class FileIdInfo(ctypes.Structure):
            _fields_ = [
                ("volume_serial", ctypes.c_ulonglong),
                ("file_id", FileId128),
            ]

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
    if sys.version_info >= (3, 12):
        kernel.GetFileInformationByHandleEx.argtypes = [
            wintypes.HANDLE,
            wintypes.INT,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
    kernel.SetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        wintypes.INT,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel.SetFileInformationByHandle.restype = wintypes.BOOL
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
        if handle is not None and handle != INVALID_HANDLE_VALUE:
            kernel.CloseHandle(handle)

    def get_info(handle: int) -> ByHandleFileInformation | None:
        info = ByHandleFileInformation()
        if not kernel.GetFileInformationByHandle(handle, ctypes.byref(info)):
            return None
        return info

    def filetime_ns(value: FileTime) -> int:
        ticks = (int(value.high) << 32) | int(value.low)
        return (ticks - WINDOWS_EPOCH_TICKS) * 100

    def file_identity(handle: int) -> tuple[int, int] | None:
        if sys.version_info >= (3, 12):
            identity = FileIdInfo()
            if not kernel.GetFileInformationByHandleEx(
                handle,
                18,  # FileIdInfo
                ctypes.byref(identity),
                ctypes.sizeof(identity),
            ):
                return None
            return (
                int(identity.volume_serial),
                int.from_bytes(bytes(identity.file_id.identifier), "little"),
            )
        info = get_info(handle)
        if info is None:
            return None
        return (
            int(info.volume_serial),
            int(info.file_index_high) << 32 | int(info.file_index_low),
        )

    root_handle: int | None = None
    file_handle: int | None = None
    try:
        root_handle = kernel.CreateFileW(
            str(root),
            FILE_READ_ATTRIBUTES | FILE_LIST_DIRECTORY,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT,
            None,
        )
        if root_handle in (None, INVALID_HANDLE_VALUE):
            return False
        root_info = get_info(root_handle)
        root_identity = file_identity(root_handle)
        if (
            root_info is None
            or root_info.attributes & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT)
            != FILE_ATTRIBUTE_DIRECTORY
            or root_identity != (entry.cache_device, entry.cache_inode)
        ):
            return False

        # Open the basename relative to the already-opened directory. The
        # handle is non-share-delete so the name cannot be moved/replaced
        # between identity verification and disposition.
        basename = entry.path.name
        name_buffer = ctypes.create_unicode_buffer(basename)
        name = UnicodeString(
            len(basename) * ctypes.sizeof(ctypes.c_wchar),
            (len(basename) + 1) * ctypes.sizeof(ctypes.c_wchar),
            ctypes.cast(name_buffer, wintypes.LPWSTR),
        )
        attributes = ObjectAttributes(
            ctypes.sizeof(ObjectAttributes),
            root_handle,
            ctypes.pointer(name),
            OBJ_CASE_INSENSITIVE,
            None,
            None,
        )
        io_status = IoStatusBlock()
        file_handle = wintypes.HANDLE()
        status = ntdll.NtCreateFile(
            ctypes.byref(file_handle),
            DELETE | FILE_READ_ATTRIBUTES | SYNCHRONIZE,
            ctypes.byref(attributes),
            ctypes.byref(io_status),
            None,
            0,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            FILE_OPEN,
            FILE_NON_DIRECTORY_FILE | FILE_OPEN_REPARSE_POINT | FILE_SYNCHRONOUS_IO_NONALERT,
            None,
            0,
        )
        if status < 0:
            return False
        file_handle_value = file_handle.value
        if file_handle_value in (None, INVALID_HANDLE_VALUE):
            return False
        file_handle = file_handle_value
        info = get_info(file_handle)
        if info is None:
            return False
        attributes_value = int(info.attributes)
        file_identity_value = file_identity(file_handle)
        file_size = int(info.file_size_high) << 32 | int(info.file_size_low)
        if (
            attributes_value & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT)
            or file_identity_value != (entry.device, entry.inode)
            or file_size != entry.size_bytes
            or filetime_ns(info.last_write_time) != entry.modified_ns
            or filetime_ns(info.creation_time) != entry.changed_ns
            or int(info.number_of_links) != 1
        ):
            return False

        disposition = FileDispositionInfo(1)
        return bool(
            kernel.SetFileInformationByHandle(
                file_handle,
                FILE_DISPOSITION_INFO_CLASS,
                ctypes.byref(disposition),
                ctypes.sizeof(disposition),
            )
        )
    except (AttributeError, OSError, TypeError, ValueError):
        return False
    finally:
        close(file_handle)
        close(root_handle)
