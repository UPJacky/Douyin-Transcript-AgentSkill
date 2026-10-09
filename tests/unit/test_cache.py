from __future__ import annotations

import os
from pathlib import Path

import pytest
from douyin_transcript.cache import (
    CacheError,
    cleanup_media_cache,
    inspect_media_cache,
)


def _cache_dir(parent: Path) -> Path:
    path = parent / "media-cache"
    path.mkdir()
    return path


def _media(cache: Path, video_id: int, digest: str, content: bytes) -> Path:
    path = cache / f"{video_id}-audio-{digest}.m4a"
    path.write_bytes(content)
    return path


def _part(cache: Path, video_id: int, content: bytes) -> Path:
    path = cache / f".{video_id}-audio-{'a' * 32}.part"
    path.write_bytes(content)
    return path


def test_scan_recognizes_only_direct_regular_downloader_files(tmp_path):
    cache = _cache_dir(tmp_path)
    media = _media(cache, 123, "a" * 16, b"media")
    part = _part(cache, 124, b"partial")
    (cache / "notes.txt").write_text("leave me", encoding="utf-8")
    (cache / "123-audio-short.m4a").write_bytes(b"not app-named")
    (cache / "subdirectory").mkdir()
    (cache / "subdirectory" / ("125-audio-" + "b" * 16 + ".m4a")).write_bytes(b"nested")

    snapshot = inspect_media_cache(cache, now=100)

    assert {entry.path for entry in snapshot.entries} == {media, part}
    assert snapshot.media_bytes == len(b"media")
    assert {entry.path: entry.kind for entry in snapshot.entries} == {
        media: "media",
        part: "partial",
    }


def test_cleanup_defaults_to_preview_and_evicts_oldest_to_capacity(tmp_path):
    cache = _cache_dir(tmp_path)
    old = _media(cache, 1, "a" * 16, b"old")
    new = _media(cache, 2, "b" * 16, b"newer")
    os.utime(old, (10, 10))
    os.utime(new, (20, 20))

    preview = cleanup_media_cache(cache, max_bytes=5, now=100)

    assert preview.dry_run is True
    assert preview.selected_paths == (old,)
    assert preview.selected_bytes == 3
    assert preview.removed_paths == ()
    assert old.exists() and new.exists()


def test_capacity_cleanup_removes_only_selected_cache_media(tmp_path):
    cache = _cache_dir(tmp_path)
    old = _media(cache, 1, "a" * 16, b"old")
    kept = _media(cache, 2, "b" * 16, b"newer")
    unrelated = cache / "user-notes.txt"
    unrelated.write_text("keep", encoding="utf-8")
    subdirectory = cache / "nested"
    subdirectory.mkdir()
    nested = _media(subdirectory, 3, "c" * 16, b"nested")
    os.utime(old, (10, 10))
    os.utime(kept, (20, 20))

    result = cleanup_media_cache(cache, max_bytes=5, dry_run=False, now=100)

    assert result.removed_paths == (old,)
    assert result.skipped_paths == ()
    assert result.remaining_media_bytes == len(b"newer")
    assert not old.exists()
    assert kept.exists()
    assert unrelated.exists()
    assert nested.exists()
    assert subdirectory.exists()


def test_age_cleanup_removes_only_expired_files_and_never_directories(tmp_path):
    cache = _cache_dir(tmp_path)
    stale_media = _media(cache, 1, "a" * 16, b"stale")
    recent_media = _media(cache, 2, "b" * 16, b"recent")
    stale_part = _part(cache, 3, b"old part")
    recent_part = _part(cache, 4, b"new part")
    directory = cache / f"5-audio-{'c' * 16}.m4a"
    directory.mkdir()
    os.utime(stale_media, (10, 10))
    os.utime(recent_media, (90, 90))
    os.utime(stale_part, (10, 10))
    os.utime(recent_part, (90, 90))

    result = cleanup_media_cache(
        cache,
        max_age_seconds=20,
        allow_partial_cleanup=True,
        dry_run=False,
        now=100,
    )

    assert set(result.removed_paths) == {stale_media, stale_part}
    assert recent_media.exists() and recent_part.exists() and directory.is_dir()


def test_partial_files_are_not_age_cleaned_without_task_coordination(tmp_path):
    cache = _cache_dir(tmp_path)
    stale_part = _part(cache, 3, b"possibly active")
    os.utime(stale_part, (10, 10))

    result = cleanup_media_cache(
        cache,
        max_age_seconds=20,
        dry_run=False,
        now=100,
    )

    assert result.removed_paths == ()
    assert stale_part.exists()


def test_active_task_references_are_protected_from_age_and_capacity_cleanup(tmp_path):
    cache = _cache_dir(tmp_path)
    protected = _media(cache, 1, "a" * 16, b"active media")
    candidate = _media(cache, 2, "b" * 16, b"old")
    os.utime(protected, (1, 1))
    os.utime(candidate, (2, 2))

    result = cleanup_media_cache(
        cache,
        protected_paths=[protected],
        max_bytes=0,
        max_age_seconds=0,
        dry_run=False,
        now=100,
    )

    assert protected.exists()
    assert not candidate.exists()
    assert result.removed_paths == (candidate,)
    assert result.remaining_media_bytes == len(b"active media")


def test_live_download_video_id_protects_partial_and_completed_cache_entries(tmp_path):
    cache = _cache_dir(tmp_path)
    active_part = _part(cache, 123, b"still downloading")
    same_video_media = _media(cache, 123, "a" * 16, b"existing media")
    stale_part = _part(cache, 456, b"stale")
    for path in (active_part, same_video_media, stale_part):
        os.utime(path, (1, 1))

    snapshot = inspect_media_cache(cache, protected_video_ids=["123"], now=100)
    result = cleanup_media_cache(
        cache,
        protected_video_ids=["123"],
        allow_partial_cleanup=True,
        max_age_seconds=0,
        dry_run=False,
        now=100,
    )

    assert {entry.path for entry in snapshot.entries if entry.protected} == {
        active_part,
        same_video_media,
    }
    assert active_part.exists() and same_video_media.exists()
    assert not stale_part.exists()
    assert result.removed_paths == (stale_part,)


@pytest.mark.parametrize("video_ids", [[123], ["../1"], [""], ["1/2"]])
def test_protected_video_ids_must_be_decimal_strings(tmp_path, video_ids):
    cache = _cache_dir(tmp_path)
    with pytest.raises(CacheError, match="decimal video IDs"):
        inspect_media_cache(cache, protected_video_ids=video_ids)


def test_hard_linked_cache_file_is_excluded_even_when_an_alias_is_protected(tmp_path):
    cache = _cache_dir(tmp_path)
    media = _media(cache, 1, "a" * 16, b"active")
    alias = tmp_path / "active-reference.bin"
    try:
        os.link(media, alias)
    except OSError:
        pytest.skip("filesystem does not support hard links in this test location")

    snapshot = inspect_media_cache(cache, protected_paths=[alias], now=100)
    result = cleanup_media_cache(
        cache, protected_paths=[alias], max_bytes=0, dry_run=False, now=100
    )

    assert snapshot.entries == ()
    assert media.exists() and alias.exists()
    assert result.removed_paths == ()
    assert result.remaining_media_bytes == 0


def test_symlinked_cache_entries_are_never_removed(tmp_path):
    cache = _cache_dir(tmp_path)
    outside = tmp_path / "outside.m4a"
    outside.write_bytes(b"outside")
    link = cache / f"1-audio-{'a' * 16}.m4a"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("filesystem does not permit symlink creation")

    snapshot = inspect_media_cache(cache, now=100)
    result = cleanup_media_cache(cache, max_bytes=0, dry_run=False, now=100)

    assert snapshot.entries == ()
    assert result.removed_paths == ()
    assert link.is_symlink()
    assert outside.read_bytes() == b"outside"


def test_hardlinked_cache_files_are_excluded_from_cleanup(tmp_path):
    cache = _cache_dir(tmp_path)
    hard_link_source = tmp_path / "hard-link-source.m4a"
    hard_link_source.write_bytes(b"shared")
    hard_link = cache / f"2-audio-{'b' * 16}.m4a"
    try:
        os.link(hard_link_source, hard_link)
    except OSError:
        pytest.skip("filesystem does not support hard links in this test location")

    snapshot = inspect_media_cache(cache, now=100)
    result = cleanup_media_cache(cache, max_bytes=0, dry_run=False, now=100)

    assert snapshot.entries == ()
    assert result.removed_paths == ()
    assert hard_link.exists() and hard_link_source.read_bytes() == b"shared"


def test_cleanup_refuses_symlinked_cache_root(tmp_path):
    real_cache = _cache_dir(tmp_path)
    alias_parent = tmp_path / "alias"
    alias_parent.mkdir()
    link = alias_parent / "media-cache"
    try:
        link.symlink_to(real_cache, target_is_directory=True)
    except OSError:
        pytest.skip("filesystem does not permit symlink creation")

    with pytest.raises(CacheError):
        inspect_media_cache(link)


def test_cleanup_refuses_non_cache_directory(tmp_path):
    _cache_dir(tmp_path)
    with pytest.raises(CacheError):
        cleanup_media_cache(tmp_path, max_bytes=0)
    assert (tmp_path / "media-cache").is_dir()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({}, "specify max_bytes"),
        ({"max_bytes": -1}, "max_bytes"),
        ({"max_bytes": True}, "max_bytes"),
        ({"max_age_seconds": float("nan")}, "max_age_seconds"),
        ({"max_age_seconds": -1}, "max_age_seconds"),
    ],
)
def test_cleanup_requires_valid_explicit_retention_limits(tmp_path, kwargs, message):
    cache = _cache_dir(tmp_path)
    with pytest.raises(CacheError, match=message):
        cleanup_media_cache(cache, **kwargs)


def test_changed_file_between_preview_selection_and_unlink_is_skipped(
    tmp_path, monkeypatch
):
    import douyin_transcript.cache as cache_module

    cache = _cache_dir(tmp_path)
    media = _media(cache, 1, "a" * 16, b"before")
    outside = tmp_path / "outside.m4a"
    outside.write_bytes(b"outside")
    original_unlink = cache_module._unlink_if_unchanged

    def replace_with_changed_file_then_unlink(root, entry):
        media.unlink()
        media.write_bytes(b"replacement file with changed size")
        return original_unlink(root, entry)

    monkeypatch.setattr(
        cache_module, "_unlink_if_unchanged", replace_with_changed_file_then_unlink
    )
    result = cleanup_media_cache(cache, max_bytes=0, dry_run=False, now=100)

    assert result.removed_paths == ()
    assert result.skipped_paths == (media,)
    assert outside.read_bytes() == b"outside"
    assert media.read_bytes() == b"replacement file with changed size"


@pytest.mark.skipif(os.name != "nt", reason="requires Windows handle semantics")
def test_windows_handle_cleanup_blocks_cache_and_file_replacement(
    tmp_path, monkeypatch
):
    import ctypes

    cache = _cache_dir(tmp_path)
    media = _media(cache, 1, "a" * 16, b"before")
    moved_cache = tmp_path / "moved-cache"
    moved_file = tmp_path / "moved.m4a"
    blocked: set[str] = set()
    original_windll = ctypes.WinDLL

    def instrumented_windll(name, *args, **kwargs):
        library = original_windll(name, *args, **kwargs)
        normalized_name = str(name).lower()
        if normalized_name.endswith("ntdll"):
            native_create = library.NtCreateFile

            def create_relative(*native_args):
                try:
                    cache.rename(moved_cache)
                except OSError:
                    blocked.add("cache")
                return native_create(*native_args)

            library.NtCreateFile = create_relative
        elif normalized_name.endswith("kernel32"):
            set_disposition = library.SetFileInformationByHandle

            def set_disposition_after_race(*native_args):
                try:
                    media.rename(moved_file)
                except OSError:
                    blocked.add("file")
                return set_disposition(*native_args)

            library.SetFileInformationByHandle = set_disposition_after_race
        return library

    monkeypatch.setattr(ctypes, "WinDLL", instrumented_windll)
    result = cleanup_media_cache(cache, max_bytes=0, dry_run=False, now=100)

    assert result.removed_paths == (media,)
    assert blocked == {"cache", "file"}
    assert not media.exists()
    assert cache.is_dir()
    assert not moved_cache.exists()
    assert not moved_file.exists()
