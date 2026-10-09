"""User path and configuration resolution shared by CLI and pipeline."""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .doctor import default_data_dir
from .limits import (
    DEFAULT_MAX_MEDIA_DURATION_SECONDS,
    DEFAULT_MAX_OUTPUT_CHARACTERS,
    DEFAULT_MAX_OUTPUT_SEGMENTS,
    validate_resource_limits,
)
from .storage_security import PrivateStorageError, open_private_regular_file


class ConfigurationError(ValueError):
    """Raised when the user's local configuration is invalid."""


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    data_dir: Path
    output_dir: Path
    config_path: Path
    max_media_duration_seconds: float = DEFAULT_MAX_MEDIA_DURATION_SECONDS
    max_output_segments: int = DEFAULT_MAX_OUTPUT_SEGMENTS
    max_output_characters: int = DEFAULT_MAX_OUTPUT_CHARACTERS


def _read_config(path: Path) -> dict[str, Any]:
    # config.toml controls output and data paths. Read from the same handle
    # whose file identity, type, owner, and permissions were checked.
    try:
        with open_private_regular_file(path) as stream:
            config = tomllib.load(stream)
    except FileNotFoundError:
        return {}
    except PrivateStorageError as exc:
        raise ConfigurationError(
            "配置文件或其父路径权限不安全；为避免采用不可信路径设置，已拒绝加载"
        ) from exc
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"无法读取配置文件：{path}") from exc
    if not isinstance(config, dict):
        raise ConfigurationError(f"配置文件格式无效：{path}")
    return config


def _configured_paths(config: dict[str, Any]) -> dict[str, str]:
    paths = config.get("paths", {})
    if not isinstance(paths, dict):
        raise ConfigurationError("config.toml 的 [paths] 必须是表")
    result: dict[str, str] = {}
    for key in ("data_dir", "output_dir"):
        value = paths.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(f"配置 paths.{key} 必须是非空路径字符串")
        result[key] = value
    return result


def _configured_limits(config: dict[str, Any]) -> dict[str, Any]:
    limits = config.get("limits", {})
    if not isinstance(limits, dict):
        raise ConfigurationError("config.toml 的 [limits] 必须是表")
    allowed = {
        "max_media_duration_seconds",
        "max_output_segments",
        "max_output_characters",
    }
    unknown = set(limits) - allowed
    if unknown:
        raise ConfigurationError(f"config.toml [limits] 包含未知选项：{', '.join(sorted(unknown))}")
    return limits


def resolve_paths(
    *,
    data_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    max_media_duration_seconds: float | None = None,
    max_output_segments: int | None = None,
    max_output_characters: int | None = None,
    cwd: str | Path | None = None,
) -> RuntimePaths:
    """Resolve explicit CLI, environment, config, then platform defaults."""
    env_data = os.environ.get("DOUYIN_TRANSCRIPT_HOME")
    config_anchor = Path(data_dir).expanduser() if data_dir else (
        Path(env_data).expanduser() if env_data else default_data_dir()
    )
    config_path = config_anchor / "config.toml"
    config = _read_config(config_path)
    configured = _configured_paths(config)
    configured_limits = _configured_limits(config)

    effective_data = (
        Path(data_dir).expanduser()
        if data_dir is not None
        else Path(env_data).expanduser()
        if env_data
        else Path(configured["data_dir"]).expanduser()
        if "data_dir" in configured
        else default_data_dir()
    )

    env_output = os.environ.get("DOUYIN_TRANSCRIPT_OUTPUT")
    effective_output = (
        Path(output_dir).expanduser()
        if output_dir is not None
        else Path(env_output).expanduser()
        if env_output
        else Path(configured["output_dir"]).expanduser()
        if "output_dir" in configured
        else Path(cwd or Path.cwd()) / "douyin-transcripts" / "output"
    )
    try:
        limits = validate_resource_limits(
            max_media_duration_seconds
            if max_media_duration_seconds is not None
            else configured_limits.get(
                "max_media_duration_seconds", DEFAULT_MAX_MEDIA_DURATION_SECONDS
            ),
            max_output_segments
            if max_output_segments is not None
            else configured_limits.get("max_output_segments", DEFAULT_MAX_OUTPUT_SEGMENTS),
            max_output_characters
            if max_output_characters is not None
            else configured_limits.get(
                "max_output_characters", DEFAULT_MAX_OUTPUT_CHARACTERS
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"config.toml 的 [limits] 配置无效：{exc}") from None
    return RuntimePaths(
        data_dir=effective_data.resolve(strict=False),
        output_dir=effective_output.resolve(strict=False),
        config_path=config_path.resolve(strict=False),
        max_media_duration_seconds=limits[0],
        max_output_segments=limits[1],
        max_output_characters=limits[2],
    )


def default_config_text(*, data_dir: Path, output_dir: Path) -> str:
    """Return a secrets-free TOML configuration sample for an explicit setup."""
    return "\n".join(
        [
            "[paths]",
            f"data_dir = {json.dumps(str(data_dir), ensure_ascii=False)}",
            f"output_dir = {json.dumps(str(output_dir), ensure_ascii=False)}",
            "",
            "[limits]",
            f"max_media_duration_seconds = {DEFAULT_MAX_MEDIA_DURATION_SECONDS}",
            f"max_output_segments = {DEFAULT_MAX_OUTPUT_SEGMENTS}",
            f"max_output_characters = {DEFAULT_MAX_OUTPUT_CHARACTERS}",
            "",
        ]
    )
