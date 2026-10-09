from __future__ import annotations

import json
import os
from pathlib import Path

import douyin_transcript.asr as asr_module
import pytest
from douyin_transcript.asr import LocalASR
from douyin_transcript.downloader import MediaFile, MediaIdentity, MediaInvalidError
from douyin_transcript.models import model_spec, write_model_provenance


def make_model(path):
    path.mkdir(parents=True)
    (path / "model.bin").write_bytes(b"weights")
    (path / "config.json").write_text(
        json.dumps({"model_type": "whisper"}), encoding="utf-8"
    )
    (path / "tokenizer.json").write_text('{"version":"1.0"}', encoding="utf-8")
    profile = "fast" if path.name == "small" else "balanced"
    write_model_provenance(path, model_spec(profile))
    return path


def valid_media(path: Path, duration: float = 2.5) -> MediaFile:
    return MediaFile(path, "wav", path.stat().st_size, duration)


class FakeWhisper:
    def __init__(self):
        self.calls = []
        self.exhausted = 0

    def transcribe(self, source, **kwargs):
        self.calls.append((source, kwargs))

        def generated():
            yield {"start": 0, "end": 1.2, "text": "嗯，大家好"}
            yield {"start": 1.2, "end": 2.0, "text": "我是小明。"}
            self.exhausted += 1

        return generated(), {"duration": 2.5, "language": "zh"}


def test_asr_lazily_uses_local_model_and_exhausts_generator_once_per_call(tmp_path):
    model_path = make_model(tmp_path / "data" / "models" / "medium")
    media_a = tmp_path / "a.wav"
    media_b = tmp_path / "b.wav"
    media_a.write_bytes(b"mock audio")
    media_b.write_bytes(b"mock audio")
    fake_model = FakeWhisper()
    factory_calls = []

    def factory(path, **kwargs):
        factory_calls.append((path, kwargs))
        return fake_model

    asr = LocalASR(
        tmp_path / "data", model_factory=factory, media_validator=valid_media
    )
    assert asr._model is None

    result_a = asr.transcribe(media_a)
    asr.transcribe(media_b, language="auto")

    assert len(factory_calls) == 1
    assert factory_calls[0] == (
        str(model_path.resolve()),
        {"device": "cpu", "compute_type": "int8"},
    )
    assert fake_model.exhausted == 2
    assert len(result_a.segments) == 2
    assert result_a.text == "嗯，大家好我是小明。"
    assert result_a.duration_seconds == 2.5
    assert result_a.language == "zh"
    assert result_a.model == "faster-whisper-medium-int8"
    assert fake_model.calls[0][1]["beam_size"] == 1
    assert fake_model.calls[0][1]["language"] == "zh"
    assert fake_model.calls[0][1]["vad_filter"] is True
    assert "initial_prompt" not in fake_model.calls[0][1]
    assert fake_model.calls[1][1]["language"] is None


def test_asr_accepts_an_explicit_domain_prompt(tmp_path):
    model_path = make_model(tmp_path / "data" / "models" / "medium")
    media = tmp_path / "sample.wav"
    media.write_bytes(b"mock audio")
    fake_model = FakeWhisper()
    asr = LocalASR(
        tmp_path / "data",
        model_factory=lambda *_args, **_kwargs: fake_model,
        media_validator=valid_media,
    )

    asr.transcribe(media, initial_prompt="品牌词和行业术语")

    assert fake_model.calls[0][1]["initial_prompt"] == "品牌词和行业术语"
    assert model_path.exists()


def test_prevalidated_media_is_passed_to_asr_as_the_same_checked_file_handle(tmp_path):
    make_model(tmp_path / "data" / "models" / "medium")
    media = tmp_path / "sample.wav"
    contents = b"validated media bytes"
    media.write_bytes(contents)
    seen = {}

    class RecordingWhisper:
        def transcribe(self, source, **_kwargs):
            seen["is_file_object"] = hasattr(source, "read") and hasattr(source, "seek")
            seen["contents"] = source.read()
            seen["closed_during_call"] = source.closed
            return iter([{"start": 0, "end": 1, "text": "hello"}]), {
                "duration": 1.0,
                "language": "zh",
            }

    with media.open("rb") as handle:
        validated_identity = MediaIdentity.from_stat(os.fstat(handle.fileno()))
    validated = MediaFile(
        media,
        "wav",
        len(contents),
        1.0,
        validated_identity,
    )
    asr = LocalASR(
        tmp_path / "data",
        model_factory=lambda *_args, **_kwargs: RecordingWhisper(),
        media_validator=lambda _path: pytest.fail("validated media must be reused"),
    )

    result = asr.transcribe(media, validated_media=validated)

    assert result.text == "hello"
    assert seen == {
        "is_file_object": True,
        "contents": contents,
        "closed_during_call": False,
    }


def test_prevalidated_media_rejects_path_replacement_before_loading_model(tmp_path):
    media = tmp_path / "sample.wav"
    media.write_bytes(b"validated version")
    validated = MediaFile(
        media,
        "wav",
        media.stat().st_size,
        1.0,
        MediaIdentity.from_stat(media.stat()),
    )
    replacement = tmp_path / "replacement.wav"
    replacement.write_bytes(b"replacement version")
    replacement.replace(media)
    factory_calls = []
    asr = LocalASR(
        tmp_path / "data",
        model_factory=lambda *_args, **_kwargs: factory_calls.append(True),
        media_validator=lambda _path: pytest.fail("validation capability was supplied"),
    )

    with pytest.raises(MediaInvalidError) as error:
        asr.transcribe(media, validated_media=validated)

    assert error.value.code == "MEDIA_CHANGED"
    assert factory_calls == []


def test_fast_profile_uses_small_and_language_argument_is_validated(tmp_path):
    model_path = make_model(tmp_path / "data" / "models" / "small")
    media = tmp_path / "sample.mp3"
    media.write_bytes(b"mock audio")
    fake_model = FakeWhisper()
    calls = []
    asr = LocalASR(
        tmp_path / "data",
        profile="fast",
        model_factory=lambda path, **kwargs: calls.append((path, kwargs)) or fake_model,
        media_validator=valid_media,
    )

    try:
        asr.transcribe(media, language="en")
    except ValueError as exc:
        assert "zh" in str(exc)
    else:
        raise AssertionError("unsupported language should fail before model loading")
    assert calls == []

    result = asr.transcribe(media, initial_prompt=None)
    assert result.profile == "fast"
    assert result.model == "faster-whisper-small-int8"
    assert calls[0][0] == str(model_path.resolve())
    assert "initial_prompt" not in fake_model.calls[-1][1]


def test_explicit_symlink_model_is_validated_and_loaded_by_canonical_path(
    monkeypatch, tmp_path
):
    model_path = make_model(tmp_path / "models" / "medium")
    replacement_path = make_model(tmp_path / "models" / "replacement")
    alias = tmp_path / "model-alias"
    alias_target = {"path": model_path.resolve()}
    original_resolve = Path.resolve

    def resolve_alias(path, *, strict=False):
        if path == alias:
            return alias_target["path"]
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve_alias)

    original_compatibility_check = asr_module.is_compatible_model_path

    def validate_then_replace_alias(path, spec):
        valid = original_compatibility_check(path, spec)
        alias_target["path"] = replacement_path.resolve()
        return valid

    monkeypatch.setattr(
        asr_module, "is_compatible_model_path", validate_then_replace_alias
    )
    factory_paths = []
    asr = LocalASR(
        tmp_path / "data",
        model_path=alias,
        model_factory=lambda path, **_kwargs: factory_paths.append(path) or object(),
    )

    asr._load_model()

    assert factory_paths == [str(model_path.resolve())]
    assert asr.model_path == model_path.resolve()


def test_overlong_media_is_rejected_before_model_factory(tmp_path):
    media = tmp_path / "long.wav"
    media.write_bytes(b"audio")
    factory_calls = []
    asr = LocalASR(
        tmp_path / "data",
        model_factory=lambda *_args, **_kwargs: factory_calls.append(True),
        media_validator=lambda path: valid_media(path, duration=61 * 60),
        max_media_duration_seconds=60 * 60,
    )

    try:
        asr.transcribe(media)
    except RuntimeError as exc:
        assert getattr(exc, "code", None) == "MEDIA_TOO_LONG"
    else:
        raise AssertionError("over-limit media should be rejected")
    assert factory_calls == []


def test_asr_uses_decoded_duration_cap_before_loading_model(monkeypatch, tmp_path):
    import sys
    from types import ModuleType

    class Stream:
        type = "audio"
        duration = 1
        time_base = 1

    class Frame:
        def __init__(self, second):
            self.samples = 1
            self.sample_rate = 1
            self.pts = second
            self.time_base = 1

    class Container:
        streams = [Stream()]
        duration = 1_000_000
        format = type("Format", (), {"name": "wav"})()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def decode(self, _stream):
            return iter(Frame(second) for second in range(5))

    av = ModuleType("av")
    av.open = lambda *_args, **_kwargs: Container()
    monkeypatch.setitem(sys.modules, "av", av)

    media = tmp_path / "understated.wav"
    media.write_bytes(b"non-empty")
    factory_calls = []
    asr = LocalASR(
        tmp_path / "data",
        model_factory=lambda *_args, **_kwargs: factory_calls.append(True),
        max_media_duration_seconds=2,
    )

    try:
        asr.transcribe(media)
    except RuntimeError as exc:
        assert getattr(exc, "code", None) == "MEDIA_TOO_LONG"
    else:
        raise AssertionError("decoded audio over the cap should be rejected")

    assert factory_calls == []


def test_asr_output_caps_close_generator_without_materializing_remainder(tmp_path):
    make_model(tmp_path / "data" / "models" / "medium")
    media = tmp_path / "audio.wav"
    media.write_bytes(b"audio")
    state = {"yielded": 0, "closed": False}

    class BoundedFakeWhisper:
        def transcribe(self, _source, **_kwargs):
            def generated():
                try:
                    for text in ("one", "two", "three"):
                        state["yielded"] += 1
                        yield {"start": 0, "end": 1, "text": text}
                finally:
                    state["closed"] = True

            return generated(), {"duration": 2.5, "language": "en"}

    asr = LocalASR(
        tmp_path / "data",
        model_factory=lambda *_args, **_kwargs: BoundedFakeWhisper(),
        media_validator=valid_media,
        max_output_segments=2,
    )
    try:
        asr.transcribe(media)
    except RuntimeError as exc:
        assert getattr(exc, "code", None) == "ASR_OUTPUT_LIMIT"
    else:
        raise AssertionError("output over the segment cap should be rejected")
    assert state == {"yielded": 3, "closed": True}


def test_asr_character_cap_is_enforced_incrementally(tmp_path):
    make_model(tmp_path / "data" / "models" / "medium")
    media = tmp_path / "audio.wav"
    media.write_bytes(b"audio")
    yielded = []

    class CharacterFakeWhisper:
        def transcribe(self, _source, **_kwargs):
            def generated():
                for text in ("abc", "def"):
                    yielded.append(text)
                    yield {"start": 0, "end": 1, "text": text}

            return generated(), {"duration": 2.5, "language": "en"}

    asr = LocalASR(
        tmp_path / "data",
        model_factory=lambda *_args, **_kwargs: CharacterFakeWhisper(),
        media_validator=valid_media,
        max_output_characters=5,
    )
    try:
        asr.transcribe(media)
    except RuntimeError as exc:
        assert getattr(exc, "code", None) == "ASR_OUTPUT_LIMIT"
    else:
        raise AssertionError("output over the character cap should be rejected")
    assert yielded == ["abc", "def"]
