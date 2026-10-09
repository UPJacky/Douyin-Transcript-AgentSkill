from __future__ import annotations

from itertools import islice

import pytest
from douyin_transcript.naming import (
    candidate_output_paths,
    choose_output_path,
    sanitize_filename,
)


def test_sanitizes_windows_illegal_characters_and_trailing_punctuation():
    result = sanitize_filename('标题: A/B? "不错". ')

    assert result == "标题_ A_B_ _不错_"
    assert not any(char in result for char in '\\/:*?"<>|')
    assert not result.endswith((" ", "."))


def test_handles_reserved_names_control_characters_emoji_and_empty_title():
    assert sanitize_filename("CON") == "_CON"
    assert sanitize_filename("LPT1.txt") == "_LPT1.txt"
    assert sanitize_filename("x\n\x00y") == "x__y"
    assert sanitize_filename("😀") == "😀"
    assert sanitize_filename("  ... ", fallback="video-123") == "video-123"


def test_filename_removes_bidirectional_controls():
    assert sanitize_filename("safe\u202etxt.exe") == "safetxt.exe"


@pytest.mark.parametrize(
    "fallback",
    ["../escape", "..\\escape", "C:\\outside", "/rooted", "CON", "..."],
)
def test_fallback_is_sanitized_as_a_single_filename_component(tmp_path, fallback):
    output_dir = tmp_path / "output"
    paths = list(islice(candidate_output_paths(output_dir, "", fallback), 3))

    assert all(path.resolve(strict=False).parent == output_dir.resolve() for path in paths)
    assert all(not any(separator in path.name for separator in ("/", "\\")) for path in paths)


@pytest.mark.parametrize(
    "extension",
    ["/../../escape.md", r"\..\escape.md", "md", "."],
)
def test_candidate_paths_reject_path_like_extensions(tmp_path, extension):
    with pytest.raises(ValueError, match="extension"):
        next(candidate_output_paths(tmp_path, "title", extension=extension))


def test_shortens_for_full_windows_path_and_unicode_title_limit(tmp_path):
    title = "中" * 120
    result = sanitize_filename(
        title,
        output_dir=tmp_path / ("directory" * 10),
        max_title_chars=80,
        max_path_chars=240,
    )

    assert len(result) <= 80
    assert len(str((tmp_path / ("directory" * 10) / f"{result}.md").absolute())) <= 240
    collision = list(
        islice(
            candidate_output_paths(
                tmp_path / ("directory" * 10), title, "1234567890123456"
            ),
            2,
        )
    )
    assert all(len(str(path.absolute())) <= 240 for path in collision)


def test_same_title_conflicts_use_video_id_then_numeric_suffix_without_overwrite(
    tmp_path,
):
    first = choose_output_path(tmp_path, "同名视频", "video-12345678")
    first.write_text("manual content", encoding="utf-8")
    second = choose_output_path(tmp_path, "同名视频", "87654321")
    second.write_text("another file", encoding="utf-8")
    third = choose_output_path(tmp_path, "同名视频", "99999999")

    assert first.name == "同名视频.md"
    assert second.name == "同名视频__87654321.md"
    assert third.name == "同名视频__99999999.md"
    assert first.read_text(encoding="utf-8") == "manual content"
