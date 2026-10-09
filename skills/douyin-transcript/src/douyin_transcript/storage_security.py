"""Private permissions for newly created application storage.

Existing user paths are never chmod'ed or have their ACL rewritten. If an
existing sensitive path is not private, callers fail closed and explain how
to select a private data directory.
"""

from __future__ import annotations

import ctypes
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import BinaryIO, Literal

StorageStatus = Literal["private", "shared", "unknown", "missing"]


class PrivateStorageError(PermissionError):
    """A sensitive application path is not known to be private."""


@dataclass(frozen=True, slots=True)
class PermissionReport:
    status: StorageStatus
    detail: str


def _display_path(path: Path) -> str:
    return str(path)


def _unsafe_message(path: Path, report: PermissionReport) -> str:
    return (
        f"敏感数据路径无法确认仅当前用户可访问：{_display_path(path)} "
        f"（{report.detail}）。程序不会更改已有权限；请改用权限私有的新数据目录。"
    )


def _creation_residue_error(error: BaseException, object_type: str) -> PrivateStorageError:
    return PrivateStorageError(
        f"{error}；若本次操作已新建私有{object_type}，失败后对象可能仍保留；"
        "若路径祖先被移动，残留位置也可能变化。请核对对象身份后再清理。"
    )


def _canonical_storage_path(path: str | os.PathLike[str]) -> Path:
    """Make an absolute path and reject traversal components before normalization."""
    target = Path(path).expanduser()
    if ".." in target.parts:
        raise ValueError("敏感存储路径不得包含 .. 组件")
    if not target.is_absolute():
        target = Path.cwd() / target
    if os.name == "nt":
        windows_path = PureWindowsPath(str(target))
        anchor = windows_path.anchor
        if anchor.startswith(("\\\\", "//")):
            raise ValueError("UNC/device namespace 路径不支持作为敏感存储目录")
        if len(anchor) == 3 and anchor[1:] == ":\\":
            drive_type = _windows_drive_type(anchor)
            if drive_type == 4:  # DRIVE_REMOTE
                raise ValueError("映射网络驱动器不支持作为敏感存储目录")
            if drive_type in {0, 1}:  # DRIVE_UNKNOWN / DRIVE_NO_ROOT_DIR
                raise ValueError("无法确认敏感存储驱动器是否为本地磁盘")
    # Path.resolve() follows symlinks/junctions and would erase components
    # inspect_private_path must reject. `.` normalization is lexical and safe.
    return Path(os.path.abspath(target))


def _windows_drive_type(root: str) -> int:
    """Return the Win32 drive type for an absolute drive root such as ``Z:\\``."""
    _advapi, kernel = _windows_api()
    get_drive_type = kernel.GetDriveTypeW
    get_drive_type.argtypes = [ctypes.c_wchar_p]
    get_drive_type.restype = ctypes.c_uint32
    return int(get_drive_type(root))


def _path_components(path: Path) -> tuple[Path, ...]:
    """Return every absolute component from the filesystem root to ``path``."""
    if not path.is_absolute() or not path.anchor:
        raise ValueError("storage path must be absolute")
    current = Path(path.anchor)
    components = [current]
    for name in path.parts[1:]:
        current = current / name
        components.append(current)
    return tuple(components)


def _is_reparse_point(info: os.stat_result) -> bool:
    attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(info, "st_file_attributes", 0) & attribute)


def _inspect_posix_ancestor(path: Path, info: os.stat_result) -> PermissionReport:
    if not stat.S_ISDIR(info.st_mode):
        return PermissionReport("unknown", f"存储路径祖先不是目录：{path}")
    effective_uid = os.geteuid()
    mode = stat.S_IMODE(info.st_mode)
    sticky = bool(mode & stat.S_ISVTX)
    if info.st_uid not in {effective_uid, 0}:
        return PermissionReport(
            "shared",
            f"祖先目录所有者 UID 为 {info.st_uid}，不是当前用户或 root：{path}",
        )
    if mode & 0o022 and not sticky:
        return PermissionReport(
            "shared",
            f"祖先目录 mode 为 {mode:04o}，其他主体可修改目录项：{path}",
        )
    return PermissionReport("private", f"祖先目录不可由不可信主体替换：{path}")


def _same_posix_object(first: os.stat_result, second: os.stat_result) -> bool:
    return first.st_dev == second.st_dev and first.st_ino == second.st_ino


def _verify_posix_directory_chain(path: Path, descriptors: list[int]) -> None:
    """Verify each pinned directory is still named by its pinned parent."""
    if len(descriptors) != len(path.parts):
        raise PrivateStorageError("无法核对敏感目录的固定句柄链")
    for index, name in enumerate(path.parts[1:], start=1):
        try:
            entry_info = os.stat(
                name, dir_fd=descriptors[index - 1], follow_symlinks=False
            )
            descriptor_info = os.fstat(descriptors[index])
        except OSError as exc:
            raise PrivateStorageError(
                f"无法核对敏感目录对象身份：{path}（{type(exc).__name__}）"
            ) from None
        if (
            not stat.S_ISDIR(entry_info.st_mode)
            or not _same_posix_object(entry_info, descriptor_info)
        ):
            raise PrivateStorageError(f"敏感目录在检查期间被替换：{path}")


def _open_posix_directory_chain(
    path: Path, *, create_missing: bool
) -> list[int]:
    """Pin and validate a directory chain, optionally creating private parts."""
    required_dir_fd = (os.open, os.mkdir, os.stat)
    required_flags = ("O_DIRECTORY", "O_NOFOLLOW")
    if (
        any(function not in os.supports_dir_fd for function in required_dir_fd)
        or os.stat not in os.supports_follow_symlinks
        or any(not hasattr(os, name) for name in required_flags)
    ):
        raise PrivateStorageError("当前 POSIX 平台不支持安全的目录句柄相对操作")

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    flags |= getattr(os, "O_CLOEXEC", 0)
    descriptors: list[int] = []
    try:
        descriptor = os.open(path.anchor, flags)
        descriptors.append(descriptor)
        current = Path(path.anchor)
        report = _inspect_posix_ancestor(current, os.fstat(descriptor))
        if report.status != "private":
            raise PrivateStorageError(_unsafe_message(current, report))

        for name in path.parts[1:]:
            child_path = current / name
            parent_descriptor = descriptors[-1]
            created = False
            try:
                child_descriptor = os.open(name, flags, dir_fd=parent_descriptor)
            except FileNotFoundError:
                if not create_missing:
                    raise
                try:
                    os.mkdir(name, mode=0o700, dir_fd=parent_descriptor)
                    created = True
                except FileExistsError:
                    pass
                child_descriptor = os.open(name, flags, dir_fd=parent_descriptor)

            descriptors.append(child_descriptor)
            child_info = os.fstat(child_descriptor)
            report = _inspect_posix_ancestor(child_path, child_info)
            if report.status != "private":
                raise PrivateStorageError(_unsafe_message(child_path, report))
            try:
                entry_info = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
            except OSError as exc:
                raise PrivateStorageError(
                    f"无法核对敏感目录对象身份：{child_path}（{type(exc).__name__}）"
                ) from None
            if (
                not stat.S_ISDIR(entry_info.st_mode)
                or not _same_posix_object(entry_info, child_info)
            ):
                raise PrivateStorageError(f"敏感目录在检查期间被替换：{child_path}")
            if created:
                report = _inspect_posix_file(child_path, child_info)
                if report.status != "private":
                    raise PrivateStorageError(_unsafe_message(child_path, report))
            current = child_path

        leaf_info = os.fstat(descriptors[-1])
        report = _inspect_posix_file(path, leaf_info)
        if report.status != "private":
            raise PrivateStorageError(_unsafe_message(path, report))
        _verify_posix_directory_chain(path, descriptors)
        return descriptors
    except BaseException:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise


def ensure_private_directory(path: str | os.PathLike[str]) -> Path:
    """Create a private directory tree, without changing existing components."""
    try:
        directory = _canonical_storage_path(path)
    except ValueError as exc:
        report = PermissionReport("unknown", str(exc))
        raise PrivateStorageError(_unsafe_message(Path(path), report)) from None
    except (OSError, RuntimeError) as exc:
        report = PermissionReport("unknown", f"无法规范化存储路径（{type(exc).__name__}）")
        raise PrivateStorageError(_unsafe_message(Path(path), report)) from None

    if os.name != "nt":
        try:
            descriptors = _open_posix_directory_chain(directory, create_missing=True)
        except PrivateStorageError as exc:
            raise _creation_residue_error(exc, "目录") from None
        except OSError as exc:
            error = PrivateStorageError(
                f"无法为敏感数据目录设置私有权限：{directory}（{type(exc).__name__}）"
            )
            raise _creation_residue_error(error, "目录") from None
        else:
            for descriptor in reversed(descriptors):
                os.close(descriptor)
            return directory

    try:
        return _ensure_windows_private_directory(directory)
    except PrivateStorageError as exc:
        raise _creation_residue_error(exc, "目录") from None
    except OSError as exc:
        error = PrivateStorageError(
            f"无法为敏感数据目录设置私有权限：{directory}（{type(exc).__name__}）"
        )
        raise _creation_residue_error(error, "目录") from None


def create_private_file(path: str | os.PathLike[str]) -> bool:
    """Exclusively create and protect a file; return False if it already exists."""
    try:
        target = _canonical_storage_path(path)
    except ValueError as exc:
        report = PermissionReport("unknown", str(exc))
        raise PrivateStorageError(_unsafe_message(Path(path), report)) from None
    except (OSError, RuntimeError) as exc:
        raise PrivateStorageError(
            f"无法规范化敏感文件路径（{type(exc).__name__}）"
        ) from None
    if os.name != "nt":
        try:
            directory_descriptors = _open_posix_directory_chain(
                target.parent, create_missing=False
            )
        except PrivateStorageError:
            raise
        except OSError as exc:
            report = PermissionReport("unknown", f"父目录不可安全打开（{type(exc).__name__}）")
            raise PrivateStorageError(_unsafe_message(target.parent, report)) from None

        file_descriptor: int | None = None
        try:
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW
            flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0)
            try:
                file_descriptor = os.open(
                    target.name, flags, 0o600, dir_fd=directory_descriptors[-1]
                )
            except FileExistsError:
                return False
            info = os.fstat(file_descriptor)
            report = _inspect_posix_file(target, info)
            if report.status != "private":
                raise PrivateStorageError(_unsafe_message(target, report))
            entry_info = os.stat(
                target.name,
                dir_fd=directory_descriptors[-1],
                follow_symlinks=False,
            )
            if not _same_posix_object(entry_info, info):
                raise PrivateStorageError(f"敏感文件在检查期间被替换：{target}")
            _verify_posix_directory_chain(target.parent, directory_descriptors)
            return True
        except PrivateStorageError as exc:
            if file_descriptor is not None:
                raise _creation_residue_error(exc, "文件") from None
            raise
        except OSError as exc:
            error = PrivateStorageError(
                f"无法以排他方式创建敏感文件：{target}（{type(exc).__name__}）"
            )
            if file_descriptor is not None:
                raise _creation_residue_error(error, "文件") from None
            raise error from None
        finally:
            if file_descriptor is not None:
                os.close(file_descriptor)
            for descriptor in reversed(directory_descriptors):
                os.close(descriptor)

    try:
        return _create_windows_private_file(target)
    except PrivateStorageError:
        raise
    except OSError as exc:
        raise PrivateStorageError(
            f"无法以排他方式创建敏感文件：{target}（{type(exc).__name__}）"
        ) from None


def inspect_private_path(path: str | os.PathLike[str]) -> PermissionReport:
    """Read-only check of the path's effective standard permissions/ACL."""
    try:
        target = _canonical_storage_path(path)
        components = _path_components(target)
    except ValueError as exc:
        return PermissionReport("unknown", str(exc))
    except (OSError, RuntimeError) as exc:
        return PermissionReport("unknown", f"无法规范化存储路径（{type(exc).__name__}）")

    for component in components[:-1]:
        try:
            info = component.lstat()
        except FileNotFoundError:
            return PermissionReport(
                "missing", "目标不存在；现有祖先已通过替换权限检查，创建时将设置私有权限"
            )
        except OSError as exc:
            return PermissionReport("unknown", f"祖先路径状态不可读取（{type(exc).__name__}）")
        if stat.S_ISLNK(info.st_mode) or _is_reparse_point(info):
            return PermissionReport("unknown", f"拒绝经过符号链接或重解析点：{component}")
        if os.name == "nt":
            ancestor_report = _inspect_windows_ancestor_path(component)
        else:
            ancestor_report = _inspect_posix_ancestor(component, info)
        if ancestor_report.status != "private":
            return ancestor_report

    try:
        info = target.lstat()
    except FileNotFoundError:
        return PermissionReport(
            "missing", "目标不存在；现有祖先已通过替换权限检查，创建时将设置私有权限"
        )
    except OSError as exc:
        return PermissionReport("unknown", f"权限状态不可读取（{type(exc).__name__}）")

    if stat.S_ISLNK(info.st_mode) or _is_reparse_point(info):
        return PermissionReport("unknown", "符号链接/重解析点不由本程序作为敏感路径使用")
    if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
        return PermissionReport("unknown", "路径不是普通文件或目录")

    if os.name == "nt":
        return _inspect_windows_path(target)
    return _inspect_posix_file(target, info)


def open_private_regular_file(path: str | os.PathLike[str]) -> BinaryIO:
    """Open a private regular file and return a reader for the checked object.

    Ancestors are checked before opening. The leaf is then opened without
    following links and its type and permissions are checked through the same
    descriptor/handle that the caller will read.
    """
    try:
        target = _canonical_storage_path(path)
    except (OSError, RuntimeError, ValueError) as exc:
        report = PermissionReport("unknown", f"无法规范化敏感文件路径（{type(exc).__name__}）")
        raise PrivateStorageError(_unsafe_message(Path(path), report)) from None

    parent_report = inspect_private_path(target.parent)
    if parent_report.status == "missing":
        raise FileNotFoundError(target)
    if parent_report.status != "private":
        raise PrivateStorageError(_unsafe_message(target.parent, parent_report))

    try:
        descriptor = (
            _open_windows_private_file(target)
            if os.name == "nt"
            else _open_posix_private_file(target)
        )
        try:
            return os.fdopen(descriptor, "rb")
        except BaseException:
            os.close(descriptor)
            raise
    except FileNotFoundError:
        raise
    except PrivateStorageError:
        raise
    except OSError as exc:
        report = PermissionReport("unknown", f"无法安全打开配置文件（{type(exc).__name__}）")
        raise PrivateStorageError(_unsafe_message(target, report)) from None


def _inspect_posix_file(path: Path, info: os.stat_result) -> PermissionReport:
    if stat.S_ISLNK(info.st_mode) or _is_reparse_point(info):
        return PermissionReport("unknown", "符号链接/重解析点不由本程序作为敏感路径使用")
    if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
        return PermissionReport("unknown", "路径不是普通文件或目录")

    effective_uid = os.geteuid()
    if info.st_uid != effective_uid:
        return PermissionReport(
            "shared",
            f"POSIX 所有者 UID 为 {info.st_uid}，当前有效 UID 为 {effective_uid}；已有权限未修改",
        )
    mode = stat.S_IMODE(info.st_mode)
    if mode & 0o077:
        return PermissionReport(
            "shared",
            f"POSIX mode 为 {mode:04o}，组用户或其他用户具有权限；已有权限未修改",
        )
    return PermissionReport(
        "private",
        f"POSIX mode 为 {mode:04o}，组用户和其他用户无权限（不检查非标准 ACL 扩展）",
    )


def _open_posix_private_file(path: Path) -> int:
    required_flags = ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK")
    if any(not hasattr(os, name) for name in required_flags) or os.open not in os.supports_dir_fd:
        raise PrivateStorageError("当前 POSIX 平台不支持安全的目录句柄文件打开")

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory_flags |= getattr(os, "O_CLOEXEC", 0)
    directory_fd = os.open(path.anchor, directory_flags)
    file_fd: int | None = None
    try:
        current = Path(path.anchor)
        root_report = _inspect_posix_ancestor(current, os.fstat(directory_fd))
        if root_report.status != "private":
            raise PrivateStorageError(_unsafe_message(current, root_report))

        for component in path.parts[1:-1]:
            next_path = current / component
            next_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            report = _inspect_posix_ancestor(next_path, os.fstat(next_fd))
            if report.status != "private":
                os.close(next_fd)
                raise PrivateStorageError(_unsafe_message(next_path, report))
            os.close(directory_fd)
            directory_fd = next_fd
            current = next_path

        file_flags = (
            os.O_RDONLY
            | os.O_NOFOLLOW
            | os.O_NONBLOCK
            | getattr(os, "O_CLOEXEC", 0)
        )
        file_fd = os.open(path.name, file_flags, dir_fd=directory_fd)
        file_info = os.fstat(file_fd)
        if not stat.S_ISREG(file_info.st_mode):
            report = PermissionReport("unknown", "配置目标不是普通文件")
            raise PrivateStorageError(_unsafe_message(path, report))
        report = _inspect_posix_file(path, file_info)
        if report.status != "private":
            raise PrivateStorageError(_unsafe_message(path, report))
        # O_NONBLOCK is needed to avoid waiting forever when the leaf is a
        # FIFO. Clear it after confirming a regular file so subsequent reads
        # use ordinary blocking-file semantics.
        import fcntl

        descriptor_flags = fcntl.fcntl(file_fd, fcntl.F_GETFL)
        if descriptor_flags & os.O_NONBLOCK:
            fcntl.fcntl(file_fd, fcntl.F_SETFL, descriptor_flags & ~os.O_NONBLOCK)
        result = file_fd
        file_fd = None
        return result
    finally:
        os.close(directory_fd)
        if file_fd is not None:
            os.close(file_fd)


def _open_windows_private_file(path: Path) -> int:
    import msvcrt

    advapi, kernel = _windows_api()

    # OPEN_REPARSE_POINT pins the leaf itself instead of following a link.
    handle = kernel.CreateFileW(
        str(path),
        0x80000000 | 0x00020000,  # GENERIC_READ | READ_CONTROL
        0x1 | 0x2 | 0x4,  # share read/write/delete; the opened object stays pinned
        None,
        3,  # OPEN_EXISTING
        0x00200000 | 0x00000080,  # FILE_FLAG_OPEN_REPARSE_POINT | FILE_ATTRIBUTE_NORMAL
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if not handle or handle == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        information = _WindowsByHandleFileInformation()
        if not kernel.GetFileInformationByHandle(handle, ctypes.byref(information)):
            raise ctypes.WinError(ctypes.get_last_error())
        if information.attributes & (0x00000400 | 0x00000010):  # reparse point or directory
            report = PermissionReport("unknown", "拒绝链接或非普通文件")
            raise PrivateStorageError(_unsafe_message(path, report))
        if kernel.GetFileType(handle) != 1:  # FILE_TYPE_DISK
            report = PermissionReport("unknown", "目标不是普通磁盘文件")
            raise PrivateStorageError(_unsafe_message(path, report))
        report = _inspect_windows_handle(handle)
        if report.status != "private":
            raise PrivateStorageError(_unsafe_message(path, report))

        descriptor = msvcrt.open_osfhandle(
            handle, os.O_RDONLY | getattr(os, "O_BINARY", 0)
        )
        handle = None
        return descriptor
    finally:
        if handle is not None:
            kernel.CloseHandle(handle)


def protection_capability() -> PermissionReport:
    """Check whether this runtime can apply its platform-specific protection."""
    if os.name != "nt":
        return PermissionReport("private", "POSIX 目录 mode 0700/文件 mode 0600 可用")
    try:
        _current_user_sid()
    except OSError as exc:
        return PermissionReport(
            "unknown", f"无法从进程令牌读取当前用户 SID（{type(exc).__name__}）"
        )
    return PermissionReport("private", "可从进程令牌读取 SID 并设置受保护的 Windows DACL")


class _WindowsFileTime(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]


class _WindowsByHandleFileInformation(ctypes.Structure):
    _fields_ = [
        ("attributes", ctypes.c_uint32),
        ("creation_time", _WindowsFileTime),
        ("last_access_time", _WindowsFileTime),
        ("last_write_time", _WindowsFileTime),
        ("volume_serial_number", ctypes.c_uint32),
        ("file_size_high", ctypes.c_uint32),
        ("file_size_low", ctypes.c_uint32),
        ("number_of_links", ctypes.c_uint32),
        ("file_index_high", ctypes.c_uint32),
        ("file_index_low", ctypes.c_uint32),
    ]


def _windows_api():
    if os.name != "nt":
        raise OSError("Windows security APIs are unavailable")
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi.OpenProcessToken.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi.OpenProcessToken.restype = ctypes.c_int
    advapi.GetTokenInformation.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    advapi.GetTokenInformation.restype = ctypes.c_int
    advapi.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    advapi.ConvertSidToStringSidW.restype = ctypes.c_int
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = ctypes.c_int
    advapi.GetNamedSecurityInfoW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi.GetNamedSecurityInfoW.restype = ctypes.c_uint32
    advapi.GetSecurityInfo.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi.GetSecurityInfo.restype = ctypes.c_uint32
    advapi.GetAce.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
    advapi.GetAce.restype = ctypes.c_int
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.GetFileInformationByHandle.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_WindowsByHandleFileInformation),
    ]
    kernel.GetFileInformationByHandle.restype = ctypes.c_int
    kernel.GetFileType.argtypes = [ctypes.c_void_p]
    kernel.GetFileType.restype = ctypes.c_uint32
    kernel.CreateDirectoryW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p]
    kernel.CreateDirectoryW.restype = ctypes.c_int
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int
    return advapi, kernel


def _current_user_sid() -> str:
    """Resolve the caller SID from its access token, never from a username."""
    advapi, kernel = _windows_api()
    handle = ctypes.c_void_p()
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    if not advapi.OpenProcessToken(
        kernel.GetCurrentProcess(), 0x0008, ctypes.byref(handle)  # TOKEN_QUERY
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        needed = ctypes.c_uint32()
        advapi.GetTokenInformation(handle, 1, None, 0, ctypes.byref(needed))  # TokenUser
        if not needed.value:
            raise ctypes.WinError(ctypes.get_last_error())
        buffer = ctypes.create_string_buffer(needed.value)
        if not advapi.GetTokenInformation(
            handle, 1, buffer, needed.value, ctypes.byref(needed)
        ):
            raise ctypes.WinError(ctypes.get_last_error())

        class SidAndAttributes(ctypes.Structure):
            _fields_ = [("sid", ctypes.c_void_p), ("attributes", ctypes.c_uint32)]

        class TokenUser(ctypes.Structure):
            _fields_ = [("user", SidAndAttributes)]

        sid_pointer = ctypes.cast(buffer, ctypes.POINTER(TokenUser)).contents.user.sid
        string_sid = ctypes.c_wchar_p()
        if not advapi.ConvertSidToStringSidW(sid_pointer, ctypes.byref(string_sid)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return string_sid.value
        finally:
            kernel.LocalFree(ctypes.cast(string_sid, ctypes.c_void_p))
    finally:
        kernel.CloseHandle(handle)


def _new_windows_private_security_descriptor(*, is_directory: bool):
    """Build a protected DACL descriptor for a newly created private object."""
    advapi, kernel = _windows_api()
    sid = _current_user_sid()
    ace_flags = "OICI" if is_directory else ""
    sddl = f"D:P(A;{ace_flags};FA;;;{sid})"
    descriptor = ctypes.c_void_p()
    descriptor_size = ctypes.c_uint32()
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, 1, ctypes.byref(descriptor), ctypes.byref(descriptor_size)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return advapi, kernel, descriptor


def _create_windows_private_directory(path: Path) -> None:
    """Create a directory with a protected private DACL from its first instant."""
    _advapi, kernel, descriptor = _new_windows_private_security_descriptor(
        is_directory=True
    )

    class SecurityAttributes(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_uint32),
            ("security_descriptor", ctypes.c_void_p),
            ("inherit_handle", ctypes.c_int),
        ]

    attributes = SecurityAttributes(
        ctypes.sizeof(SecurityAttributes), descriptor, 0
    )
    try:
        if not kernel.CreateDirectoryW(str(path), ctypes.byref(attributes)):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.LocalFree(descriptor)


def _create_windows_private_file(path: Path) -> bool:
    """Create a private file atomically and verify its path/object identity."""
    _advapi, kernel, descriptor = _new_windows_private_security_descriptor(
        is_directory=False
    )

    class SecurityAttributes(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_uint32),
            ("security_descriptor", ctypes.c_void_p),
            ("inherit_handle", ctypes.c_int),
        ]

    attributes = SecurityAttributes(ctypes.sizeof(SecurityAttributes), descriptor, 0)
    chain: list[tuple[Path, int, tuple[int, int, int]]] = []
    handle: int | None = None
    try:
        chain = _open_windows_directory_chain(path.parent, create_missing=False)
        try:
            handle = kernel.CreateFileW(
                str(path),
                0x40000000 | 0x00020000,  # GENERIC_WRITE | READ_CONTROL
                0x1 | 0x2 | 0x4,  # share read/write/delete
                ctypes.byref(attributes),
                1,  # CREATE_NEW
                0x00000080,  # FILE_ATTRIBUTE_NORMAL
                None,
            )
            invalid_handle = ctypes.c_void_p(-1).value
            if not handle or handle == invalid_handle:
                error = ctypes.WinError(ctypes.get_last_error())
                handle = None
                if getattr(error, "winerror", None) in {80, 183}:
                    return False
                raise error

            information = _windows_file_information(handle)
            if information.attributes & (0x00000400 | 0x00000010):
                raise PrivateStorageError(f"拒绝新建的链接或非普通敏感文件：{path}")
            if kernel.GetFileType(handle) != 1:
                raise PrivateStorageError(f"新建目标不是普通磁盘文件：{path}")
            report = _inspect_windows_handle(handle)
            if report.status != "private":
                raise PrivateStorageError(_unsafe_message(path, report))

            _verify_windows_directory_chain(chain)
            path_handle = _open_windows_object_handle(path)
            try:
                if _windows_handle_identity(handle) != _windows_handle_identity(
                    path_handle
                ):
                    raise PrivateStorageError(f"敏感文件在检查期间被替换：{path}")
            finally:
                kernel.CloseHandle(path_handle)
            return True
        except PrivateStorageError as exc:
            if handle is not None:
                raise _creation_residue_error(exc, "文件") from None
            raise
        except OSError as exc:
            error = PrivateStorageError(
                f"无法以排他方式创建敏感文件：{path}（{type(exc).__name__}）"
            )
            if handle is not None:
                raise _creation_residue_error(error, "文件") from None
            raise error from None
    finally:
        if handle is not None:
            kernel.CloseHandle(handle)
        for _directory_path, directory_handle, _identity in reversed(chain):
            kernel.CloseHandle(directory_handle)
        kernel.LocalFree(descriptor)


def _windows_file_information(handle: int) -> _WindowsByHandleFileInformation:
    _advapi, kernel = _windows_api()
    information = _WindowsByHandleFileInformation()
    if not kernel.GetFileInformationByHandle(handle, ctypes.byref(information)):
        raise ctypes.WinError(ctypes.get_last_error())
    return information


def _windows_handle_identity(handle: int) -> tuple[int, int, int]:
    information = _windows_file_information(handle)
    identity = (
        information.volume_serial_number,
        information.file_index_high,
        information.file_index_low,
    )
    if identity[1] == 0 and identity[2] == 0:
        raise PrivateStorageError("Windows 文件系统未提供可核对的对象 ID")
    return identity


def _open_windows_object_handle(path: Path) -> int:
    """Open the named object itself, without following a leaf reparse point."""
    _advapi, kernel = _windows_api()
    handle = kernel.CreateFileW(
        str(path),
        0x00000080 | 0x00020000,  # FILE_READ_ATTRIBUTES | READ_CONTROL
        0x1 | 0x2 | 0x4,
        None,
        3,  # OPEN_EXISTING
        0x00200000 | 0x02000000,  # OPEN_REPARSE_POINT | BACKUP_SEMANTICS
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if not handle or handle == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def _open_windows_directory_handle(path: Path) -> tuple[int, tuple[int, int, int]]:
    handle = _open_windows_object_handle(path)
    try:
        information = _windows_file_information(handle)
        if information.attributes & 0x00000400:
            raise PrivateStorageError(f"拒绝经过 Windows 重解析点：{path}")
        if not information.attributes & 0x00000010:
            raise PrivateStorageError(f"存储路径祖先不是目录：{path}")
        return handle, _windows_handle_identity(handle)
    except BaseException:
        _advapi, kernel = _windows_api()
        kernel.CloseHandle(handle)
        raise


def _verify_windows_directory_chain(
    chain: list[tuple[Path, int, tuple[int, int, int]]]
) -> None:
    """Check that each path component still names its pinned directory object."""
    _advapi, kernel = _windows_api()
    for path, _handle, identity in chain:
        try:
            current_handle = _open_windows_object_handle(path)
        except OSError as exc:
            raise PrivateStorageError(
                f"敏感目录路径在检查期间发生变化：{path}（{type(exc).__name__}）"
            ) from None
        try:
            information = _windows_file_information(current_handle)
            if information.attributes & 0x00000400 or not information.attributes & 0x10:
                raise PrivateStorageError(f"敏感目录路径在检查期间发生变化：{path}")
            if _windows_handle_identity(current_handle) != identity:
                raise PrivateStorageError(f"敏感目录在检查期间被替换：{path}")
        finally:
            kernel.CloseHandle(current_handle)


def _open_windows_directory_chain(
    path: Path, *, create_missing: bool
) -> list[tuple[Path, int, tuple[int, int, int]]]:
    """Open, validate and pin a path's directory components with Win32 handles.

    Win32 directory creation is pathname-based. The held handles and identity
    checks detect ordinary replacements around each operation, but cannot rule
    out an ABA swap between checks; new components still get a private DACL
    atomically in CreateDirectoryW.
    """
    _advapi, kernel = _windows_api()
    chain: list[tuple[Path, int, tuple[int, int, int]]] = []
    try:
        current = Path(path.anchor)
        handle, identity = _open_windows_directory_handle(current)
        chain.append((current, handle, identity))
        report = _inspect_windows_ancestor_handle(handle, current)
        if report.status != "private":
            raise PrivateStorageError(_unsafe_message(current, report))

        for name in path.parts[1:]:
            current = current / name
            try:
                child_handle, child_identity = _open_windows_directory_handle(current)
            except OSError as exc:
                if getattr(exc, "winerror", None) not in {2, 3} or not create_missing:
                    raise
                try:
                    _create_windows_private_directory(current)
                except OSError as create_error:
                    if getattr(create_error, "winerror", None) not in {80, 183}:
                        raise
                _verify_windows_directory_chain(chain)
                child_handle, child_identity = _open_windows_directory_handle(current)

            chain.append((current, child_handle, child_identity))
            report = _inspect_windows_ancestor_handle(child_handle, current)
            if report.status != "private":
                raise PrivateStorageError(_unsafe_message(current, report))

        final_handle = chain[-1][1]
        report = _inspect_windows_handle(final_handle)
        if report.status != "private":
            raise PrivateStorageError(_unsafe_message(path, report))
        _verify_windows_directory_chain(chain)
        return chain
    except BaseException:
        for _directory_path, handle, _identity in reversed(chain):
            kernel.CloseHandle(handle)
        raise


def _ensure_windows_private_directory(path: Path) -> Path:
    try:
        chain = _open_windows_directory_chain(path, create_missing=True)
    except PrivateStorageError:
        raise
    except OSError as exc:
        report = PermissionReport("unknown", f"路径无法安全打开（{type(exc).__name__}）")
        raise PrivateStorageError(_unsafe_message(path, report)) from None
    else:
        _advapi, kernel = _windows_api()
        for _directory_path, handle, _identity in reversed(chain):
            kernel.CloseHandle(handle)
        return path


def _inspect_windows_path(path: Path) -> PermissionReport:
    """Reject paths owned by untrusted principals or granted to foreign users."""
    try:
        advapi, kernel = _windows_api()
        current_sid = _current_user_sid()
    except OSError as exc:
        return PermissionReport(
            "unknown", f"无法读取 Windows 安全 API 状态（{type(exc).__name__}）"
        )

    owner = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    result = advapi.GetNamedSecurityInfoW(
        str(path),
        1,  # SE_FILE_OBJECT
        0x00000001 | 0x00000004,  # OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION
        ctypes.byref(owner),
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    )
    if result != 0:
        return PermissionReport("unknown", f"GetNamedSecurityInfoW 失败（{result}）")
    try:
        return _inspect_windows_acl(advapi, kernel, current_sid, owner, dacl)
    finally:
        if descriptor.value:
            kernel.LocalFree(descriptor)


def _inspect_windows_handle(handle: int) -> PermissionReport:
    """Check owner and ACL through the already-open file handle."""
    try:
        advapi, kernel = _windows_api()
        current_sid = _current_user_sid()
    except OSError as exc:
        return PermissionReport(
            "unknown", f"无法读取 Windows 安全 API 状态（{type(exc).__name__}）"
        )

    owner = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    result = advapi.GetSecurityInfo(
        handle,
        1,  # SE_FILE_OBJECT
        0x00000001 | 0x00000004,  # OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION
        ctypes.byref(owner),
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    )
    if result != 0:
        return PermissionReport("unknown", f"GetSecurityInfo 失败（{result}）")
    try:
        return _inspect_windows_acl(advapi, kernel, current_sid, owner, dacl)
    finally:
        if descriptor.value:
            kernel.LocalFree(descriptor)


def _inspect_windows_acl(advapi, kernel, current_sid: str, owner, dacl) -> PermissionReport:
    if not dacl.value:
        return PermissionReport("shared", "DACL 为空或未限制访问")

    class Acl(ctypes.Structure):
        _fields_ = [
            ("revision", ctypes.c_ubyte),
            ("sbz1", ctypes.c_ubyte),
            ("size", ctypes.c_uint16),
            ("ace_count", ctypes.c_uint16),
            ("sbz2", ctypes.c_uint16),
        ]

    class AceHeader(ctypes.Structure):
        _fields_ = [
            ("ace_type", ctypes.c_ubyte),
            ("ace_flags", ctypes.c_ubyte),
            ("ace_size", ctypes.c_uint16),
        ]

    try:
        owner_sid = _sid_to_string(advapi, kernel, owner)
    except OSError:
        return PermissionReport("unknown", "无法确认 Windows 安全描述符的所有者 SID")
    owner_report = _check_windows_owner(owner_sid, current_sid)
    if owner_report is not None:
        return owner_report
    allowed_sids = _trusted_windows_sids(current_sid)
    acl = ctypes.cast(dacl, ctypes.POINTER(Acl)).contents
    for index in range(acl.ace_count):
        ace_pointer = ctypes.c_void_p()
        if not advapi.GetAce(dacl, index, ctypes.byref(ace_pointer)):
            return PermissionReport("unknown", "无法解析 Windows DACL ACE")
        ace_address = ace_pointer.value
        header = ctypes.cast(ace_pointer, ctypes.POINTER(AceHeader)).contents
        if header.ace_type in {1, 2, 3, 6, 7, 8, 10, 12, *range(13, 22)}:
            continue
        if header.ace_type not in {0, 5, 9, 11}:  # allow, object/callback variants
            return PermissionReport(
                "unknown", f"无法可靠判定 Windows DACL ACE 类型（{header.ace_type}）"
            )
        sid_offset = 8
        if header.ace_type in {5, 11}:
            flags = ctypes.c_uint32.from_address(ace_address + 8).value
            sid_offset = 12 + (16 if flags & 1 else 0) + (16 if flags & 2 else 0)
        if sid_offset >= header.ace_size:
            return PermissionReport("unknown", "无法解析 Windows DACL SID")
        sid_pointer = ctypes.c_void_p(ace_address + sid_offset)
        try:
            ace_sid = _sid_to_string(advapi, kernel, sid_pointer)
        except OSError:
            return PermissionReport("unknown", "无法解码 Windows DACL SID")
        if ace_sid == "S-1-3-4" and owner_sid in allowed_sids:
            # OWNER RIGHTS applies only to the security descriptor's owner.
            continue
        if ace_sid not in allowed_sids and _foreign_windows_ace_grants_sensitive_access(
            ctypes.c_uint32.from_address(ace_address + 4).value
        ):
            return PermissionReport(
                "shared",
                f"DACL 含有向其他主体授权的 ACE（{ace_sid}）；已有 ACL 未修改",
            )
    return PermissionReport(
        "private",
        "DACL 未向其他主体授予读取或修改内容的权限（遍历/同步权限不读取文件内容）",
    )


def _foreign_windows_ace_grants_sensitive_access(access_mask: int) -> bool:
    """Whether an untrusted allow ACE can read, change, or replace private data.

    FILE_EXECUTE (0x20) on a directory is traverse-only, and SYNCHRONIZE
    (0x00100000) does not expose or modify directory entries or file contents.
    Windows profile roots commonly grant only these rights to an AppContainer
    capability SID; treating that ACE as content-readable blocks safe output
    locations without improving transcript privacy.
    """
    traversal_and_sync = 0x00000020 | 0x00100000
    return bool(access_mask & ~traversal_and_sync)


def _inspect_windows_ancestor_path(path: Path) -> PermissionReport:
    """Require trusted ownership and deny foreign directory-entry replacement."""
    try:
        handle, _identity = _open_windows_directory_handle(path)
    except OSError as exc:
        return PermissionReport(
            "unknown", f"无法读取 Windows 祖先目录安全 API 状态（{type(exc).__name__}）"
        )
    except PrivateStorageError as exc:
        return PermissionReport("unknown", str(exc))
    try:
        return _inspect_windows_ancestor_handle(handle, path)
    finally:
        _advapi, kernel = _windows_api()
        kernel.CloseHandle(handle)


def _inspect_windows_ancestor_handle(handle: int, path: Path) -> PermissionReport:
    """Check owner/replacement rights from the same pinned directory handle."""
    try:
        advapi, kernel = _windows_api()
        current_sid = _current_user_sid()
    except OSError as exc:
        return PermissionReport(
            "unknown", f"无法读取 Windows 祖先目录安全 API 状态（{type(exc).__name__}）"
        )

    owner = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    result = advapi.GetSecurityInfo(
        handle,
        1,
        0x00000001 | 0x00000004,
        ctypes.byref(owner),
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    )
    if result != 0:
        return PermissionReport("unknown", f"GetSecurityInfo 失败（{result}）")
    try:
        if not dacl.value:
            return PermissionReport("shared", f"祖先目录 DACL 为空或未限制访问：{path}")
        try:
            owner_sid = _sid_to_string(advapi, kernel, owner)
        except OSError:
            return PermissionReport("unknown", "无法确认 Windows 祖先目录所有者 SID")
        trusted_owners = _trusted_windows_ancestor_sids(current_sid)
        if owner_sid not in trusted_owners:
            return PermissionReport(
                "shared", f"祖先目录由不可信主体所有（{owner_sid}）：{path}"
            )

        class Acl(ctypes.Structure):
            _fields_ = [
                ("revision", ctypes.c_ubyte),
                ("sbz1", ctypes.c_ubyte),
                ("size", ctypes.c_uint16),
                ("ace_count", ctypes.c_uint16),
                ("sbz2", ctypes.c_uint16),
            ]

        class AceHeader(ctypes.Structure):
            _fields_ = [
                ("ace_type", ctypes.c_ubyte),
                ("ace_flags", ctypes.c_ubyte),
                ("ace_size", ctypes.c_uint16),
            ]

        # DELETE on the directory or FILE_DELETE_CHILD on its parent permits
        # an untrusted principal to replace an existing child path. WRITE_DAC,
        # WRITE_OWNER and generic-all can grant the same authority later.
        replacement_rights = 0x00010000 | 0x00000040 | 0x00040000 | 0x00080000 | 0x10000000
        trusted_sids = _trusted_windows_sids(current_sid)
        acl = ctypes.cast(dacl, ctypes.POINTER(Acl)).contents
        for index in range(acl.ace_count):
            ace_pointer = ctypes.c_void_p()
            if not advapi.GetAce(dacl, index, ctypes.byref(ace_pointer)):
                return PermissionReport("unknown", "无法解析 Windows 祖先目录 ACE")
            ace_address = ace_pointer.value
            header = ctypes.cast(ace_pointer, ctypes.POINTER(AceHeader)).contents
            if header.ace_type in {1, 2, 3, 6, 7, 8, 10, 12, *range(13, 22)}:
                continue
            if header.ace_type not in {0, 5, 9, 11}:
                return PermissionReport(
                    "unknown", f"无法判定 Windows 祖先目录 ACE 类型（{header.ace_type}）"
                )
            # INHERIT_ONLY ACEs do not grant access to this directory. Each
            # child component is checked separately, and new private children
            # receive protected DACLs.
            if header.ace_flags & 0x08:
                continue
            sid_offset = 8
            if header.ace_type in {5, 11}:
                flags = ctypes.c_uint32.from_address(ace_address + 8).value
                sid_offset = 12 + (16 if flags & 1 else 0) + (16 if flags & 2 else 0)
            if sid_offset >= header.ace_size:
                return PermissionReport("unknown", "无法解析 Windows 祖先目录 ACE SID")
            access_mask = ctypes.c_uint32.from_address(ace_address + 4).value
            sid_pointer = ctypes.c_void_p(ace_address + sid_offset)
            try:
                ace_sid = _sid_to_string(advapi, kernel, sid_pointer)
            except OSError:
                return PermissionReport("unknown", "无法解码 Windows 祖先目录 ACE SID")
            if ace_sid == "S-1-3-4" and owner_sid in trusted_sids:
                continue
            if ace_sid not in trusted_sids and access_mask & replacement_rights:
                return PermissionReport(
                    "shared",
                    f"祖先目录向其他主体授予目录替换权限（{ace_sid}）：{path}",
                )
        return PermissionReport("private", "祖先目录的 owner 和替换权限可信")
    finally:
        if descriptor.value:
            kernel.LocalFree(descriptor)


def _trusted_windows_sids(current_sid: str) -> frozenset[str]:
    """Return principals allowed to own sensitive application storage."""
    return frozenset({current_sid, "S-1-5-18", "S-1-5-32-544"})


def _trusted_windows_ancestor_sids(current_sid: str) -> frozenset[str]:
    """Include Windows servicing ownership used by trusted system ancestors."""
    trusted_installer_sid = "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464"
    return _trusted_windows_sids(current_sid) | {trusted_installer_sid}


def _check_windows_owner(owner_sid: str, current_sid: str) -> PermissionReport | None:
    """Reject existing paths owned by a principal outside the trusted set."""
    if owner_sid in _trusted_windows_sids(current_sid):
        return None
    return PermissionReport(
        "shared",
        f"路径所有者不属于当前用户、SYSTEM 或本机 Administrators（{owner_sid}）；已有 ACL 未修改",
    )


def _sid_to_string(advapi, kernel, sid_pointer: ctypes.c_void_p) -> str:
    string_sid = ctypes.c_wchar_p()
    if not advapi.ConvertSidToStringSidW(sid_pointer, ctypes.byref(string_sid)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return string_sid.value
    finally:
        kernel.LocalFree(ctypes.cast(string_sid, ctypes.c_void_p))
