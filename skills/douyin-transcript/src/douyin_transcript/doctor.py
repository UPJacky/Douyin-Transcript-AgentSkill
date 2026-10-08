"""Read-only environment diagnostics. This module never installs or downloads."""

from __future__ import annotations

import importlib.util
import os
import platform
import sys
from pathlib import Path
from typing import Any


def default_data_dir() -> Path:
    """Return a platform-appropriate user data path without creating it."""
    configured = os.environ.get("DOUYIN_TRANSCRIPT_HOME")
    if configured:
        return Path(configured).expanduser()

    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "douyin-transcript"
        return Path.home() / "AppData" / "Local" / "douyin-transcript"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "douyin-transcript"
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".local" / "share"
    return root / "douyin-transcript"


def _module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        return False


def _model_cache_available(data_dir: Path) -> bool:
    candidates = [
        data_dir / "models" / "medium",
        data_dir / "models" / "small",
    ]
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        hub = Path(hf_home).expanduser() / "hub"
        candidates.extend(
            [
                hub / "models--Systran--faster-whisper-medium",
                hub / "models--Systran--faster-whisper-small",
            ]
        )
    return any(path.is_dir() for path in candidates)


def _chromium_available() -> bool:
    configured = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    roots = [Path(configured).expanduser()] if configured else []
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            roots.append(Path(local) / "ms-playwright")
    elif sys.platform == "darwin":
        roots.append(Path.home() / "Library" / "Caches" / "ms-playwright")
    else:
        roots.append(Path.home() / ".cache" / "ms-playwright")
    return any(root.is_dir() and any(root.glob("chromium-*")) for root in roots)


def collect_report(data_dir_override: str | None = None) -> dict[str, Any]:
    """Collect basic setup status without touching the filesystem."""
    data_dir = Path(data_dir_override).expanduser() if data_dir_override else default_data_dir()
    whisper_available = _module_available("faster_whisper")
    playwright_available = _module_available("playwright")
    model_available = whisper_available and _model_cache_available(data_dir)
    chromium_available = playwright_available and _chromium_available()

    checks = {
        "python": {
            "status": (
                "ok"
                if sys.version_info >= (3, 11) and sys.version_info < (3, 13)
                else "missing"
            ),
            "detail": f"{platform.python_version()} ({platform.python_implementation()})",
        },
        "faster_whisper": {
            "status": "ok" if whisper_available else "missing",
            "detail": "已安装" if whisper_available else "未安装；本地转写依赖将在 P1 阶段接入",
        },
        "model": {
            "status": "ok" if model_available else "missing",
            "detail": (
                "发现 medium/small 模型缓存"
                if model_available
                else "未发现模型缓存；doctor 不会下载模型"
            ),
        },
        "playwright": {
            "status": "ok" if playwright_available else "missing",
            "detail": (
                "已安装"
                if playwright_available
                else "未安装；浏览器抓取依赖将在 P2 阶段接入"
            ),
        },
        "chromium": {
            "status": "ok" if chromium_available else "missing",
            "detail": (
                "发现 Playwright Chromium"
                if chromium_available
                else "未发现 Playwright Chromium 浏览器"
            ),
        },
    }
    ready = all(item["status"] == "ok" for item in checks.values())
    return {
        "project": "douyin-transcript",
        "version": "0.1.0",
        "overall": "ready" if ready else "setup_required",
        "data_dir": str(data_dir),
        "checks": checks,
        "note": "doctor 只读取环境状态，不安装依赖、不下载模型，也不创建数据目录。",
    }
