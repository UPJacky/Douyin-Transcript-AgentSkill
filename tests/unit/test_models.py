from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import douyin_transcript.models as models_module
import pytest
from douyin_transcript.models import (
    is_complete_model,
    model_spec,
    resolve_model_path,
    write_model_provenance,
)


def make_model(path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "model.bin").write_bytes(b"weights")
    (path / "config.json").write_text(
        json.dumps({"model_type": "whisper"}), encoding="utf-8"
    )
    (path / "tokenizer.json").write_text('{"version":"1.0"}', encoding="utf-8")
    return path


def clear_hf_env(monkeypatch):
    for name in ("HF_HUB_CACHE", "HF_HOME", "XDG_CACHE_HOME"):
        monkeypatch.delenv(name, raising=False)


def allow_cache_path_in_windows_unit_test(monkeypatch):
    """Separate resolver behavior from this host's inherited Windows ACLs."""
    if os.name == "nt":
        monkeypatch.setattr(
            models_module, "_cache_path_is_trusted", lambda *_a, **_k: True
        )


def mark_local_model(path, profile):
    return write_model_provenance(path, model_spec(profile))


def make_hub_snapshot(cache_root, profile="balanced"):
    spec = model_spec(profile)
    repo_cache = cache_root / ("models--" + spec.repository.replace("/", "--"))
    snapshot = repo_cache / "snapshots" / spec.revision
    blobs = repo_cache / "blobs"
    snapshot.mkdir(parents=True)
    blobs.mkdir()
    contents = {
        "model.bin": b"weights",
        "config.json": b'{"model_type":"whisper"}',
        "tokenizer.json": b'{"version":"1.0"}',
    }
    blob_paths = {}
    for name, content in contents.items():
        if name == "model.bin":
            digest = hashlib.sha256(content).hexdigest()
        else:
            digest = hashlib.sha1(
                f"blob {len(content)}\0".encode() + content
            ).hexdigest()
        blob = blobs / digest
        blob.write_bytes(content)
        (snapshot / name).write_bytes(content)
        blob_paths[name] = blob
    return snapshot, blob_paths


def test_profiles_pin_medium_and_small_cpu_int8():
    balanced = model_spec("balanced")
    fast = model_spec("fast")

    assert (
        balanced.size,
        balanced.device,
        balanced.compute_type,
        balanced.beam_size,
    ) == ("medium", "cpu", "int8", 1)
    assert (fast.size, fast.device, fast.compute_type, fast.beam_size) == (
        "small",
        "cpu",
        "int8",
        1,
    )
    assert model_spec("medium") == balanced
    assert model_spec("small") == fast
    assert balanced.repository == "Systran/faster-whisper-medium"
    assert balanced.revision == "08e178d48790749d25932bbc082711ddcfdfbc4f"
    assert fast.repository == "Systran/faster-whisper-small"
    assert fast.revision == "536b0662742c02347bc0e980a01041f333bce120"


def test_resolver_checks_complete_local_model_and_keeps_profiles_separate(
    monkeypatch, tmp_path
):
    clear_hf_env(monkeypatch)
    medium = tmp_path / "data" / "models" / "medium"
    small = tmp_path / "data" / "models" / "small"
    medium.mkdir(parents=True)
    (medium / "model.bin").write_bytes(b"weights")

    assert resolve_model_path(tmp_path / "data", "balanced") is None
    assert resolve_model_path(tmp_path / "data", "fast") is None

    make_model(medium)
    make_model(small)
    assert resolve_model_path(tmp_path / "data", "balanced") is None
    assert resolve_model_path(tmp_path / "data", "fast") is None
    mark_local_model(medium, "balanced")
    mark_local_model(small, "fast")
    assert resolve_model_path(tmp_path / "data", "balanced") == medium.resolve()
    assert resolve_model_path(tmp_path / "data", "fast") == small.resolve()


def test_model_validation_rejects_empty_weight_invalid_config_and_missing_tokenizer(
    tmp_path,
):
    model = make_model(tmp_path / "model")
    assert is_complete_model(model)

    (model / "model.bin").write_bytes(b"")
    assert not is_complete_model(model)
    (model / "model.bin").write_bytes(b"weights")
    (model / "config.json").write_text("not json", encoding="utf-8")
    assert not is_complete_model(model)
    (model / "config.json").write_text("{}", encoding="utf-8")
    (model / "tokenizer.json").unlink()
    assert not is_complete_model(model)


def test_resolver_honors_hf_hub_cache_and_returns_complete_snapshot(
    monkeypatch, tmp_path
):
    allow_cache_path_in_windows_unit_test(monkeypatch)
    clear_hf_env(monkeypatch)
    cache = tmp_path / "custom-hub"
    monkeypatch.setenv("HF_HUB_CACHE", str(cache))
    broken = cache / "models--Systran--faster-whisper-medium" / "snapshots" / "broken"
    broken.mkdir(parents=True)
    (broken / "model.bin").write_bytes(b"partial")
    spec = model_spec("balanced")
    mismatch = (
        cache
        / "models--Systran--faster-whisper-medium"
        / "snapshots"
        / "newer-unpinned"
    )
    make_model(mismatch)
    good = (
        cache / "models--Systran--faster-whisper-medium" / "snapshots" / spec.revision
    )
    make_model(good)

    resolved = resolve_model_path(tmp_path / "data", "balanced")

    assert resolved == good.resolve()
    assert (resolved / "model.bin").is_file()


def test_resolver_rejects_hub_blob_content_substitution(monkeypatch, tmp_path):
    clear_hf_env(monkeypatch)
    cache = tmp_path / "custom-hub"
    monkeypatch.setenv("HF_HUB_CACHE", str(cache))
    snapshot, blobs = make_hub_snapshot(cache)
    data_dir = tmp_path / "data"
    snapshot_entries = {name: snapshot / name for name in blobs}
    original_lstat = Path.lstat
    original_resolve = Path.resolve

    def snapshot_entry_lstat(path):
        if path in snapshot_entries.values():
            return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_file_attributes=0)
        return original_lstat(path)

    def snapshot_entry_resolve(path, *, strict=False):
        for name, entry in snapshot_entries.items():
            if path == entry:
                return blobs[name]
        return original_resolve(path, strict=strict)

    # Model Hub snapshot links are represented deterministically so this test
    # covers their hash validation even on Windows hosts without symlink rights.
    monkeypatch.setattr(Path, "lstat", snapshot_entry_lstat)
    monkeypatch.setattr(Path, "resolve", snapshot_entry_resolve)

    assert resolve_model_path(data_dir, "balanced") == snapshot.resolve()

    blobs["model.bin"].write_bytes(b"replaced weights")

    assert resolve_model_path(data_dir, "balanced") is None


def test_resolver_rejects_writable_shared_hub_cache(monkeypatch, tmp_path):
    clear_hf_env(monkeypatch)
    cache = tmp_path / "shared-hub"
    monkeypatch.setenv("HF_HUB_CACHE", str(cache))
    snapshot = make_model(
        cache
        / "models--Systran--faster-whisper-medium"
        / "snapshots"
        / model_spec("balanced").revision
    )
    data_dir = tmp_path / "data"
    original_trust_check = models_module._cache_path_is_trusted
    if os.name == "nt":

        def trust_except_shared_cache(path, *, is_directory=True):
            try:
                Path(path).relative_to(cache)
            except ValueError:
                return original_trust_check(path, is_directory=is_directory)
            return False

        monkeypatch.setattr(
            models_module, "_cache_path_is_trusted", trust_except_shared_cache
        )
    else:
        cache.chmod(stat.S_IMODE(cache.stat().st_mode) | 0o022)

    assert snapshot.is_dir()
    assert resolve_model_path(data_dir, "balanced") is None


def test_posix_cache_component_rejects_untrusted_owner(tmp_path):
    if os.name == "nt":
        pytest.skip("POSIX ownership is not available on Windows")
    info = tmp_path.stat()
    foreign = SimpleNamespace(st_uid=os.geteuid() + 12345, st_mode=info.st_mode)

    assert not models_module._cache_component_is_trusted(foreign, is_directory=True)


def test_hub_blob_digest_supports_sha256_and_git_blob_sha1(tmp_path):
    raw = b"content-addressed weights"
    sha256_blob = tmp_path / hashlib.sha256(raw).hexdigest()
    sha256_blob.write_bytes(raw)
    git_hash = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
    git_blob = tmp_path / git_hash
    git_blob.write_bytes(raw)

    assert models_module._hub_blob_name_matches_content(sha256_blob)
    assert models_module._hub_blob_name_matches_content(git_blob)

    sha256_blob.write_bytes(b"changed")
    assert not models_module._hub_blob_name_matches_content(sha256_blob)


def test_resolver_finds_faster_whisper_download_root_under_data_models(
    monkeypatch, tmp_path
):
    clear_hf_env(monkeypatch)
    allow_cache_path_in_windows_unit_test(monkeypatch)
    data_dir = tmp_path / "data"
    downloaded = (
        data_dir
        / "models"
        / "models--Systran--faster-whisper-medium"
        / "snapshots"
        / model_spec("balanced").revision
    )
    model = make_model(downloaded)

    assert resolve_model_path(data_dir, "balanced") == model.resolve()


def test_resolver_rejects_complete_hf_snapshot_with_mismatched_revision(
    monkeypatch, tmp_path
):
    clear_hf_env(monkeypatch)
    cache = tmp_path / "custom-hub"
    monkeypatch.setenv("HF_HUB_CACHE", str(cache))
    mismatched = (
        cache
        / "models--Systran--faster-whisper-medium"
        / "snapshots"
        / "another-commit"
    )
    make_model(mismatched)

    assert resolve_model_path(tmp_path / "data", "balanced") is None


def test_local_model_requires_matching_manifest_and_unchanged_file_digests(
    monkeypatch, tmp_path
):
    clear_hf_env(monkeypatch)
    local = make_model(tmp_path / "data" / "models" / "medium")

    assert resolve_model_path(tmp_path / "data", "balanced") is None
    mark_local_model(local, "balanced")
    assert resolve_model_path(tmp_path / "data", "balanced") == local.resolve()

    manifest_path = local / ".douyin-transcript-model.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["revision"] = "another-commit"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    assert resolve_model_path(tmp_path / "data", "balanced") is None

    mark_local_model(local, "balanced")
    (local / "model.bin").write_bytes(b"replaced weights")
    assert resolve_model_path(tmp_path / "data", "balanced") is None


def test_resolver_honors_hf_home_and_default_cache(monkeypatch, tmp_path):
    clear_hf_env(monkeypatch)
    allow_cache_path_in_windows_unit_test(monkeypatch)
    hf_home_model = (
        tmp_path
        / "hf-home"
        / "hub"
        / "models--Systran--faster-whisper-small"
        / "snapshots"
        / model_spec("small").revision
    )
    model = make_model(hf_home_model)
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf-home"))
    assert resolve_model_path(tmp_path / "data", "small") == model.resolve()

    clear_hf_env(monkeypatch)
    default_model = (
        tmp_path
        / "xdg"
        / "huggingface"
        / "hub"
        / "models--Systran--faster-whisper-small"
        / "snapshots"
        / model_spec("small").revision
    )
    model = make_model(default_model)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert resolve_model_path(tmp_path / "data", "fast") == model.resolve()

    clear_hf_env(monkeypatch)
    profile_root = tmp_path / "profile"
    monkeypatch.setattr(Path, "home", lambda: profile_root)
    default_model = (
        profile_root
        / ".cache"
        / "huggingface"
        / "hub"
        / "models--Systran--faster-whisper-small"
        / "snapshots"
        / model_spec("small").revision
    )
    model = make_model(default_model)
    assert resolve_model_path(tmp_path / "data", "small") == model.resolve()


def test_unknown_profile_is_rejected(tmp_path):
    try:
        resolve_model_path(tmp_path, "turbo")
    except ValueError as exc:
        assert "unsupported model profile" in str(exc)
    else:
        raise AssertionError("turbo is not enabled in the P1 model resolver")
