"""Read-only environment diagnostics. This module never installs or downloads."""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .storage_security import inspect_private_path, protection_capability

_IMPORT_TIMEOUT_SECONDS = 20
_IMPORT_CHECK = "import importlib, sys; importlib.import_module(sys.argv[1])"
_CHROMIUM_PATH_CHECK = (
    "from playwright.sync_api import sync_playwright; "
    "p = sync_playwright().start(); "
    "print(p.chromium.executable_path); p.stop()"
)


def default_data_dir() -> Path:
    """Return a platform-appropriate user data path without creating it."""
    configured = os.environ.get("DOUYIN_TRANSCRIPT_HOME")
    if configured:
        return Path(configured).expanduser()

    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            local_app_data = Path(base) / "douyin-transcript"
            report = inspect_private_path(local_app_data)
            if report.status in {"private", "missing"}:
                return local_app_data
            try:
                local_app_data.lstat()
            except FileNotFoundError:
                pass
            except OSError:
                return local_app_data
            else:
                # Preserve the existing location for diagnosis. Do not silently
                # select an empty fallback and make prior tasks appear missing.
                return local_app_data
        profile_fallback = Path.home() / ".local" / "share" / "douyin-transcript"
        if inspect_private_path(profile_fallback).status in {"private", "missing"}:
            return profile_fallback
        if base:
            return Path(base) / "douyin-transcript"
        return profile_fallback
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "douyin-transcript"
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".local" / "share"
    return root / "douyin-transcript"


def _module_status(module_name: str) -> dict[str, str]:
    """Distinguish a missing module from one that exists but cannot import."""
    try:
        spec = importlib.util.find_spec(module_name)
    except (ImportError, ValueError):
        spec = None
    if spec is None:
        return {"status": "missing", "detail": "未安装"}

    try:
        result = subprocess.run(
            [sys.executable, "-P", "-c", _IMPORT_CHECK, module_name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_IMPORT_TIMEOUT_SECONDS,
            check=False,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        return {"status": "broken", "detail": "导入检查超时"}
    except OSError as exc:
        return {"status": "broken", "detail": f"无法启动导入检查：{type(exc).__name__}"}

    if result.returncode == 0:
        return {"status": "ok", "detail": "导入成功"}
    # Keep output small and avoid echoing environment-specific paths or secrets.
    error_name = "导入失败"
    for line in result.stderr.splitlines():
        candidate = line.strip()
        if candidate.startswith(("ImportError:", "ModuleNotFoundError:", "OSError:")):
            error_name = candidate.split(":", 1)[0]
            break
    return {"status": "broken", "detail": error_name}


def _resolved_model_path(data_dir: Path, profile: str) -> Path | None:
    """Use the model resolver shared with setup and ASR when it is available."""
    try:
        from .models import resolve_model_path
    except ImportError:
        return None
    try:
        return resolve_model_path(data_dir, profile)
    except (OSError, ValueError):
        return None


def _model_status(data_dir: Path, profile: str) -> dict[str, str]:
    path = _resolved_model_path(data_dir, profile)
    if path is None:
        return {"status": "missing", "detail": f"未发现可用的 {profile} 模型缓存；不会自动下载"}
    return {"status": "ok", "detail": f"模型文件可用（{profile}）"}


def _chromium_executable() -> Path | None:
    """Ask the installed Playwright version for its effective Chromium path."""
    try:
        result = subprocess.run(
            [sys.executable, "-P", "-c", _CHROMIUM_PATH_CHECK],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_IMPORT_TIMEOUT_SECONDS,
            check=False,
            env=os.environ.copy(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    raw_path = result.stdout.strip().splitlines()
    if not raw_path:
        return None
    return Path(raw_path[-1])


def _chromium_status(playwright_status: str) -> dict[str, str]:
    if playwright_status != "ok":
        return {"status": "missing", "detail": "Playwright 未能成功导入"}
    executable = _chromium_executable()
    if executable is None:
        return {"status": "broken", "detail": "无法解析当前 Playwright 的 Chromium 路径"}
    try:
        available = executable.is_file() and executable.stat().st_size > 0
    except OSError:
        available = False
    if not available:
        return {"status": "missing", "detail": "当前 Playwright 版本所需的 Chromium 文件未安装"}
    return {"status": "ok", "detail": "当前 Playwright 版本的 Chromium 可执行文件存在"}


def _directory_status(path: Path) -> dict[str, str]:
    """Check an existing directory or its nearest existing parent without writes."""
    candidate = path.expanduser()
    probe = candidate
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if not probe.is_dir():
        return {"status": "missing", "detail": "没有可检查的父目录"}
    if os.access(probe, os.W_OK | os.X_OK):
        detail = "目录可写" if candidate.exists() else "最近的现有父目录可写"
        return {"status": "ok", "detail": detail}
    return {"status": "unwritable", "detail": "目录及其现有父目录不可写"}


def _disk_status(path: Path) -> dict[str, str]:
    probe = path.expanduser()
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        free_bytes = shutil.disk_usage(probe).free
    except OSError as exc:
        return {"status": "unavailable", "detail": f"无法查询磁盘空间（{type(exc).__name__}）"}
    free_gib = free_bytes / (1024**3)
    status = "ok" if free_bytes >= 2 * (1024**3) else "low_space"
    return {"status": status, "detail": f"可用空间 {free_gib:.1f} GiB；模型准备建议至少 2 GiB"}


def _permission_status(path: Path) -> dict[str, str]:
    """Report private-storage state without creating or changing any path."""
    target = Path(path).expanduser()
    report = inspect_private_path(target)
    if report.status == "private":
        return {"status": "ok", "detail": report.detail}
    if report.status == "missing":
        # inspect_private_path returns "missing" only after applying the
        # platform's ancestor/replacement policy to every existing component.
        # Do not re-check the nearest parent as a leaf: an ancestor may grant
        # read-only access while still preventing replacement of a protected
        # child created with a private DACL/mode.
        capability = protection_capability()
        if capability.status != "private":
            return {"status": "unknown", "detail": capability.detail}
        return {"status": "ok", "detail": "尚未创建；写入时将设置仅当前用户可访问的权限"}
    if report.status == "shared":
        return {"status": "unsafe", "detail": report.detail}
    return {"status": "unknown", "detail": report.detail}


def output_directory_permission_status(path: Path) -> dict[str, str]:
    """Report output ACLs without treating user-selected shared folders as fatal."""
    target = Path(path).expanduser()
    probe = target
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if not probe.is_dir():
        return {"status": "unknown", "detail": "输出目录或可检查的父目录不存在"}

    report = inspect_private_path(probe)
    if report.status == "private":
        detail = (
            report.detail
            if probe == target
            else f"输出目录尚未创建；最近现有父目录的权限：{report.detail}"
        )
        return {"status": "ok", "detail": detail}
    if report.status == "shared":
        return {
            "status": "unsafe",
            "detail": f"输出目录可能由其他主体读取；不会更改已有权限。{report.detail}",
        }
    return {"status": "unknown", "detail": report.detail}


def _output_directory_permission_status(path: Path) -> dict[str, str]:
    """Backward-compatible internal alias for the output permission check."""
    return output_directory_permission_status(path)


def collect_report(
    data_dir_override: str | None = None,
    *,
    profile: str = "balanced",
    output_dir_override: str | None = None,
) -> dict[str, Any]:
    """Collect basic environment status without changing user files."""
    from .config import ConfigurationError, resolve_paths

    config_error: str | None = None
    output_dir: Path | None = None
    try:
        paths = resolve_paths(
            data_dir=data_dir_override,
            output_dir=output_dir_override,
        )
        data_dir, output_dir = paths.data_dir, paths.output_dir
    except ConfigurationError as exc:
        config_error = str(exc)
        data_dir = Path(data_dir_override).expanduser() if data_dir_override else default_data_dir()
        output_dir = (
            None
            if output_dir_override == ""
            else Path(output_dir_override).expanduser()
            if output_dir_override is not None
            else Path(os.environ["DOUYIN_TRANSCRIPT_OUTPUT"]).expanduser()
            if os.environ.get("DOUYIN_TRANSCRIPT_OUTPUT")
            else None
        )
    whisper = _module_status("faster_whisper")
    decoder = _module_status("av")
    playwright = _module_status("playwright")
    data_path = _directory_status(data_dir)
    if output_dir is None:
        output_detail = (
            "--output-dir 不能为空；未检查输出路径"
            if output_dir_override == ""
            else "配置无效且没有可确定的输出目录；未检查输出路径"
        )
        output_path = {"status": "unknown", "detail": output_detail}
        output_permissions = {
            "status": "unknown",
            "detail": output_detail.replace("输出路径", "输出路径权限"),
        }
    else:
        output_path = _directory_status(output_dir)
        output_permissions = output_directory_permission_status(output_dir)
    data_permissions = _permission_status(data_dir)
    database_permissions = _permission_status(data_dir / "tasks.sqlite3")
    profile_permissions = _permission_status(data_dir / "browser-profile")
    cache_permissions = _permission_status(data_dir / "media-cache")
    checks: dict[str, dict[str, str]] = {
        "python": {
            "status": ("ok" if (3, 11) <= sys.version_info[:2] < (3, 13) else "missing"),
            "detail": f"{platform.python_version()} ({platform.python_implementation()})",
        },
        "faster_whisper": whisper,
        "decoder": decoder,
        "model": _model_status(data_dir, profile),
        "playwright": playwright,
        "chromium": _chromium_status(playwright["status"]),
        "browser_isolation": {
            "status": "not_used",
            "detail": "个人模式使用当前账号的 Chromium；不使用管理员 WFP 服务",
        },
        "config": {
            "status": "invalid" if config_error else "ok",
            "detail": config_error if config_error else "配置文件可读取",
        },
        "data_dir": data_path,
        "data_dir_permissions": data_permissions,
        "task_database_permissions": database_permissions,
        "browser_profile_permissions": profile_permissions,
        "media_cache_permissions": cache_permissions,
        "output_dir": output_path,
        "output_dir_permissions": output_permissions,
        "disk_space": _disk_status(data_dir),
    }
    local_ready = all(
        checks[name]["status"] == "ok"
        for name in (
            "python",
            "faster_whisper",
            "decoder",
            "model",
            "config",
            "data_dir",
            "data_dir_permissions",
            "task_database_permissions",
            "output_dir",
        )
    )
    url_ready = local_ready and all(
        checks[name]["status"] == "ok"
        for name in (
            "playwright",
            "chromium",
            "browser_profile_permissions",
            "media_cache_permissions",
        )
    )
    return {
        "project": "douyin-transcript",
        "version": "0.1.0",
        "capture_mode": "personal",
        "overall": "ready" if local_ready else "setup_required",
        "data_dir": str(data_dir),
        "output_dir": str(output_dir) if output_dir is not None else "",
        "checks": checks,
        "capabilities": {
            "local_transcription": "ready" if local_ready else "setup_required",
            "douyin_urls": "ready" if url_ready else "setup_required",
        },
        "note": (
            "doctor 只读取环境状态，不安装依赖、不下载模型，也不创建目录；"
            "磁盘检查建议模型预留空间。权限检查不会修复已有目录；POSIX 检查标准 mode，"
            "Windows 检查进程令牌用户 SID、SYSTEM 和 Administrators 的 DACL。"
        ),
    }
