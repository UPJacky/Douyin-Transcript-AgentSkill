from __future__ import annotations

import os
import sys
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = str(ROOT / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import safe_output  # noqa: E402
from safe_output import (  # noqa: E402
    SafeOutputError,
    open_new_text,
    validate_output_directory,
    write_atomic_text,
    write_new_text,
)


def test_atomic_text_writer_creates_and_replaces_regular_outputs(
    tmp_path: Path,
) -> None:
    output = tmp_path / "nested" / "evidence.json"

    result = write_atomic_text(output, "first\n")
    assert output.read_text(encoding="utf-8") == "first\n"
    assert result == output.resolve()

    write_atomic_text(output, "second\n")
    assert output.read_text(encoding="utf-8") == "second\n"


def test_create_only_text_writer_creates_and_refuses_existing_output(
    tmp_path: Path,
) -> None:
    output = tmp_path / "nested" / "evidence.json"

    result = write_new_text(output, "first\n")
    assert output.read_text(encoding="utf-8") == "first\n"
    assert result == output.resolve()

    with pytest.raises(FileExistsError):
        write_new_text(output, "replacement\n")
    assert output.read_text(encoding="utf-8") == "first\n"
    assert list(output.parent.glob(".codex-output-*.tmp")) == []


def test_exclusive_text_stream_refuses_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "evidence.json"
    output.write_text("preserve\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        with open_new_text(output) as stream:
            stream.write("replacement\n")

    assert output.read_text(encoding="utf-8") == "preserve\n"


def test_atomic_text_writer_rejects_symlink_destination(tmp_path: Path) -> None:
    target = tmp_path / "outside.json"
    target.write_text("preserve\n", encoding="utf-8")
    output = tmp_path / "evidence.json"
    try:
        output.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    with pytest.raises(SafeOutputError, match="symbolic link or reparse point"):
        write_atomic_text(output, "attacker-controlled\n")

    assert target.read_text(encoding="utf-8") == "preserve\n"
    assert output.is_symlink()


def test_atomic_text_writer_rejects_symlinked_parent(tmp_path: Path) -> None:
    target_dir = tmp_path / "outside"
    target_dir.mkdir()
    linked_dir = tmp_path / "linked"
    try:
        linked_dir.symlink_to(target_dir, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink creation is unavailable: {exc}")

    with pytest.raises(SafeOutputError, match="symbolic link or reparse point"):
        write_atomic_text(linked_dir / "evidence.json", "attacker-controlled\n")

    assert not (target_dir / "evidence.json").exists()


def test_create_only_writers_reject_symlinked_parent(tmp_path: Path) -> None:
    target_dir = tmp_path / "outside"
    target_dir.mkdir()
    linked_dir = tmp_path / "linked"
    try:
        linked_dir.symlink_to(target_dir, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink creation is unavailable: {exc}")

    with pytest.raises(SafeOutputError, match="symbolic link or reparse point"):
        write_new_text(linked_dir / "evidence.json", "new\n")
    with pytest.raises(SafeOutputError, match="symbolic link or reparse point"):
        with open_new_text(linked_dir / "stream.json") as stream:
            stream.write("new\n")

    assert not (target_dir / "evidence.json").exists()
    assert not (target_dir / "stream.json").exists()


def test_output_directory_validation_rejects_symlink(tmp_path: Path) -> None:
    target_dir = tmp_path / "outside"
    target_dir.mkdir()
    linked_dir = tmp_path / "linked"
    try:
        linked_dir.symlink_to(target_dir, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink creation is unavailable: {exc}")

    with pytest.raises(SafeOutputError, match="symbolic link or reparse point"):
        validate_output_directory(linked_dir)


def test_atomic_text_writer_rejects_reparse_point_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reparse_dir = tmp_path / "reparse"
    reparse_dir.mkdir()
    original_lstat = Path.lstat

    def fake_lstat(path: Path):
        if path == reparse_dir:
            return SimpleNamespace(
                st_mode=stat.S_IFDIR | 0o700,
                st_file_attributes=0x400,
            )
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    with pytest.raises(SafeOutputError, match="symbolic link or reparse point"):
        write_atomic_text(reparse_dir / "evidence.json", "attacker-controlled\n")

    assert not (reparse_dir / "evidence.json").exists()


def test_create_only_text_writer_rejects_reparse_point_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reparse_dir = tmp_path / "reparse"
    reparse_dir.mkdir()
    original_lstat = Path.lstat

    def fake_lstat(path: Path):
        if path == reparse_dir:
            return SimpleNamespace(
                st_mode=stat.S_IFDIR | 0o700,
                st_file_attributes=0x400,
            )
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    with pytest.raises(SafeOutputError, match="symbolic link or reparse point"):
        write_new_text(reparse_dir / "evidence.json", "attacker-controlled\n")

    assert not (reparse_dir / "evidence.json").exists()


@pytest.mark.skipif(
    sys.platform == "win32" or not hasattr(os, "supports_dir_fd"),
    reason="directory-relative replacement test requires POSIX dir_fd support",
)
def test_atomic_replace_stays_in_pinned_directory_during_parent_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "parent"
    moved_parent = tmp_path / "moved-parent"
    outside = tmp_path / "outside"
    parent.mkdir()
    outside.mkdir()
    actual_rename = os.rename

    def swap_parent_then_rename(src, dst, **kwargs):
        parent.rename(moved_parent)
        parent.symlink_to(outside, target_is_directory=True)
        return actual_rename(src, dst, **kwargs)

    monkeypatch.setattr(safe_output.os, "rename", swap_parent_then_rename)
    write_atomic_text(parent / "evidence.txt", "pinned\n")

    assert (moved_parent / "evidence.txt").read_text(encoding="utf-8") == "pinned\n"
    assert not (outside / "evidence.txt").exists()
