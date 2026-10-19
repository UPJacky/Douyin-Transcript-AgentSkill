from __future__ import annotations

import os

import pytest
from douyin_transcript.config import ConfigurationError, resolve_paths
from douyin_transcript.storage_security import PrivateStorageError


def _write_private_config(path, text):
    path.write_text(text, encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)


def test_cli_paths_override_environment_and_config(monkeypatch, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    _write_private_config(
        data / "config.toml", '[paths]\noutput_dir = "configured-output"\n'
    )
    monkeypatch.setenv("DOUYIN_TRANSCRIPT_HOME", str(tmp_path / "env-data"))
    monkeypatch.setenv("DOUYIN_TRANSCRIPT_OUTPUT", str(tmp_path / "env-output"))

    paths = resolve_paths(
        data_dir=data,
        output_dir=tmp_path / "cli-output",
        cwd=tmp_path,
    )

    assert paths.data_dir == data.resolve()
    assert paths.output_dir == (tmp_path / "cli-output").resolve()
    assert paths.config_path == (data / "config.toml").resolve()


@pytest.mark.parametrize(
    ("argument", "option"),
    [("data_dir", "--data-dir"), ("output_dir", "--output-dir")],
)
def test_explicit_empty_path_is_rejected(tmp_path, argument, option):
    with pytest.raises(ConfigurationError, match=option):
        resolve_paths(**{argument: ""}, cwd=tmp_path)


def test_environment_paths_override_config(monkeypatch, tmp_path):
    data = tmp_path / "env-data"
    data.mkdir()
    _write_private_config(
        data / "config.toml", '[paths]\noutput_dir = "configured-output"\n'
    )
    output = tmp_path / "env-output"
    monkeypatch.setenv("DOUYIN_TRANSCRIPT_HOME", str(data))
    monkeypatch.setenv("DOUYIN_TRANSCRIPT_OUTPUT", str(output))

    paths = resolve_paths(cwd=tmp_path)

    assert paths.data_dir == data.resolve()
    assert paths.output_dir == output.resolve()
    assert not paths.output_dir_is_default


def test_implicit_output_defaults_to_selected_data_directory(monkeypatch, tmp_path):
    data = tmp_path / "private-data"
    monkeypatch.setenv("DOUYIN_TRANSCRIPT_HOME", str(data))
    monkeypatch.delenv("DOUYIN_TRANSCRIPT_OUTPUT", raising=False)

    paths = resolve_paths(cwd=tmp_path / "shared-working-directory")

    assert paths.data_dir == data.resolve()
    assert paths.output_dir == (data / "output").resolve()
    assert paths.output_dir_is_default


def test_invalid_config_fails_with_user_safe_error(monkeypatch, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    _write_private_config(data / "config.toml", "[paths\n")
    monkeypatch.setenv("DOUYIN_TRANSCRIPT_HOME", str(data))

    try:
        resolve_paths(cwd=tmp_path)
    except ConfigurationError as exc:
        assert "配置文件" in str(exc)
    else:
        raise AssertionError("invalid TOML should be rejected")


def test_untrusted_config_cannot_redirect_transcript_output(monkeypatch, tmp_path):
    data = tmp_path / "unsafe-data"
    data.mkdir()
    _write_private_config(
        data / "config.toml", '[paths]\noutput_dir = "attacker-readable-output"\n'
    )
    monkeypatch.setattr(
        "douyin_transcript.config.open_private_regular_file",
        lambda _path: (_ for _ in ()).throw(PrivateStorageError("shared ancestor")),
    )

    with pytest.raises(ConfigurationError, match="权限不安全"):
        resolve_paths(data_dir=data, cwd=tmp_path)


def test_resource_limits_load_from_config_and_cli_values_override(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    _write_private_config(
        data / "config.toml",
        "[limits]\n"
        "max_media_duration_seconds = 900\n"
        "max_output_segments = 1234\n"
        "max_output_characters = 45678\n",
    )

    configured = resolve_paths(data_dir=data, cwd=tmp_path)
    overridden = resolve_paths(
        data_dir=data,
        max_media_duration_seconds=120,
        max_output_segments=12,
        max_output_characters=345,
        cwd=tmp_path,
    )

    assert configured.max_media_duration_seconds == 900
    assert configured.max_output_segments == 1234
    assert configured.max_output_characters == 45678
    assert overridden.max_media_duration_seconds == 120
    assert overridden.max_output_segments == 12
    assert overridden.max_output_characters == 345


def test_resource_limits_reject_unbounded_config_values(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    _write_private_config(
        data / "config.toml", "[limits]\nmax_media_duration_seconds = 999999999\n"
    )

    try:
        resolve_paths(data_dir=data, cwd=tmp_path)
    except ConfigurationError as exc:
        assert "limits" in str(exc)
    else:
        raise AssertionError("unbounded resource limits should be rejected")


def test_unknown_resource_limit_names_have_display_controls_removed(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    _write_private_config(
        data / "config.toml",
        '[limits]\n"bad\\u001b[31m" = true\n',
    )

    with pytest.raises(ConfigurationError) as exc_info:
        resolve_paths(data_dir=data, cwd=tmp_path)

    assert "\x1b" not in str(exc_info.value)
    assert "bad[31m" in str(exc_info.value)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink traversal regression")
def test_config_rejects_symlink_dotdot_path_before_reading_redirected_file(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    _write_private_config(data / "config.toml", '[paths]\noutput_dir = "safe"\n')

    redirected = tmp_path / "redirected"
    (redirected / "child").mkdir(parents=True)
    (redirected / "config.toml").write_text(
        '[paths]\noutput_dir = "attacker-controlled"\n', encoding="utf-8"
    )
    (redirected / "config.toml").chmod(0o644)
    alias = data / "alias"
    alias.symlink_to(redirected / "child", target_is_directory=True)

    with pytest.raises(ConfigurationError, match="权限不安全"):
        resolve_paths(data_dir=data / "alias" / "..", cwd=tmp_path)
