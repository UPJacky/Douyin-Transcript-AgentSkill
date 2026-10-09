"""Lazy, reusable faster-whisper adapter for local transcription."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .downloader import MediaFile, MediaIdentity, MediaInvalidError, validate_media_file
from .limits import (
    DEFAULT_MAX_MEDIA_DURATION_SECONDS,
    DEFAULT_MAX_OUTPUT_CHARACTERS,
    DEFAULT_MAX_OUTPUT_SEGMENTS,
    ResourceLimitError,
    require_media_duration,
    validate_resource_limits,
)
from .models import ModelSpec, is_compatible_model_path, model_spec, resolve_model_path


class ASRUnavailableError(RuntimeError):
    """Raised when local ASR dependencies or model files are unavailable."""


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TranscriptionResult:
    segments: tuple[TranscriptSegment, ...]
    duration_seconds: float | None
    language: str | None
    model: str
    profile: str

    @property
    def text(self) -> str:
        """Return the unedited, ordered ASR segment text."""
        return "".join(segment.text for segment in self.segments).strip()


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _as_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


class LocalASR:
    """Load one local CTranslate2 model and reuse it for subsequent files.

    ``faster_whisper`` is imported only when the first transcription begins, so
    help, doctor, unit tests, and other lightweight commands do not load the
    optional native dependency.
    """

    def __init__(
        self,
        data_dir: Path,
        profile: str = "balanced",
        *,
        model_path: Path | None = None,
        model_factory: Callable[..., Any] | None = None,
        media_validator: Callable[[Path], MediaFile] = validate_media_file,
        max_media_duration_seconds: float = DEFAULT_MAX_MEDIA_DURATION_SECONDS,
        max_output_segments: int = DEFAULT_MAX_OUTPUT_SEGMENTS,
        max_output_characters: int = DEFAULT_MAX_OUTPUT_CHARACTERS,
    ) -> None:
        self.data_dir = Path(data_dir).expanduser()
        self.spec: ModelSpec = model_spec(profile)
        self.profile = self.spec.profile
        self._model_path = Path(model_path).expanduser() if model_path else None
        self._model_factory = model_factory
        self._model: Any | None = None
        (
            self.max_media_duration_seconds,
            self.max_output_segments,
            self.max_output_characters,
        ) = validate_resource_limits(
            max_media_duration_seconds, max_output_segments, max_output_characters
        )
        self._media_validator = (
            (
                lambda path: validate_media_file(
                    path, max_duration_seconds=self.max_media_duration_seconds
                )
            )
            if media_validator is validate_media_file
            else media_validator
        )

    @property
    def model_path(self) -> Path:
        if self._model_path is None:
            found = resolve_model_path(self.data_dir, self.profile)
            if found is None:
                raise ASRUnavailableError(
                    f"未找到完整的本地 {self.spec.size} 模型；请先运行 setup。"
                )
            self._model_path = found
        supplied_path = self._model_path
        try:
            canonical_path = supplied_path.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ASRUnavailableError(
                f"模型目录无法规范化：{supplied_path}（{type(exc).__name__}）。"
                "请使用 setup 下载配置档位对应的模型。"
            ) from None
        if not is_compatible_model_path(canonical_path, self.spec):
            raise ASRUnavailableError(
                f"模型目录不完整，或来源与配置的固定 revision 不匹配：{canonical_path}。"
                "请使用 setup 下载配置档位对应的模型。"
            )
        # Persist the exact canonical target that passed provenance validation.
        # In particular, never pass a caller-supplied symlink alias to the ASR
        # backend after validating its resolved destination.
        self._model_path = canonical_path
        return canonical_path

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        factory = self._model_factory
        if factory is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise ASRUnavailableError(
                    "未安装 faster-whisper；请按项目安装说明安装运行依赖。"
                ) from exc
            factory = WhisperModel
        self._model = factory(
            str(self.model_path),
            device=self.spec.device,
            compute_type=self.spec.compute_type,
        )
        return self._model

    def transcribe(
        self,
        media_path: Path,
        *,
        language: str = "zh",
        vad_filter: bool = True,
        initial_prompt: str | None = None,
        validated_media: MediaFile | None = None,
    ) -> TranscriptionResult:
        """Transcribe media and consume its result iterator within configured caps."""
        source = Path(media_path).expanduser()
        if not source.is_file():
            raise FileNotFoundError(f"媒体文件不存在：{source}")
        if language not in {"zh", "auto"}:
            raise ValueError("language must be 'zh' or 'auto'")

        media = (
            validated_media
            if validated_media is not None and validated_media.identity is not None
            else self._media_validator(source)
        )
        expected_path = os.path.normcase(os.path.abspath(media.path))
        actual_path = os.path.normcase(os.path.abspath(source))
        if expected_path != actual_path:
            raise MediaInvalidError("MEDIA_CHANGED", "校验结果与待转写路径不一致")
        require_media_duration(media.duration_seconds, self.max_media_duration_seconds)

        kwargs: dict[str, Any] = {
            "language": None if language == "auto" else language,
            "task": "transcribe",
            "beam_size": self.spec.beam_size,
            "vad_filter": vad_filter,
        }
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt
        source_handle = None
        generated = None
        try:
            input_source: Any = str(source)
            if media.identity is not None:
                source_handle = source.open("rb")
                actual_identity = MediaIdentity.from_stat(os.fstat(source_handle.fileno()))
                if actual_identity != media.identity:
                    raise MediaInvalidError("MEDIA_CHANGED", "媒体在校验后发生了变化")
                source_handle.seek(0)
                input_source = source_handle

            model = self._load_model()
            generated, info = model.transcribe(input_source, **kwargs)
            duration = _as_float(_field(info, "duration"))
            # Consume incrementally and bound both object count and aggregate text.
            segments: list[TranscriptSegment] = []
            characters = 0
            if duration is not None:
                require_media_duration(duration, self.max_media_duration_seconds)
            for segment in generated:
                if len(segments) >= self.max_output_segments:
                    raise ResourceLimitError(
                        "ASR_OUTPUT_LIMIT",
                        "识别分段超过设置上限；可通过 limits 配置或命令行调整。",
                    )
                text = str(_field(segment, "text", ""))
                characters += len(text)
                if characters > self.max_output_characters:
                    raise ResourceLimitError(
                        "ASR_OUTPUT_LIMIT",
                        "识别文本超过设置的字符数上限；可通过 limits 配置或命令行调整。",
                    )
                segments.append(
                    TranscriptSegment(
                        start=_as_float(_field(segment, "start", 0)) or 0.0,
                        end=_as_float(_field(segment, "end", 0)) or 0.0,
                        text=text,
                    )
                )
            actual_language = _field(info, "language")
            if source_handle is not None:
                final_identity = MediaIdentity.from_stat(os.fstat(source_handle.fileno()))
                if final_identity != media.identity:
                    raise MediaInvalidError("MEDIA_CHANGED", "媒体在转写期间发生了变化")
            return TranscriptionResult(
                segments=tuple(segments),
                duration_seconds=duration,
                language=str(actual_language) if actual_language else None,
                model=self.spec.model_name,
                profile=self.profile,
            )
        finally:
            try:
                close = getattr(generated, "close", None)
                if callable(close):
                    close()
            finally:
                if source_handle is not None:
                    source_handle.close()
