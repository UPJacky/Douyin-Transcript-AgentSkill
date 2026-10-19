from __future__ import annotations

import pytest

from douyin_transcript.limits import HARD_MAX_MEDIA_DURATION_SECONDS
from douyin_transcript.normalize import format_timestamp, normalize_segments


def test_normalizer_preserves_fillers_words_order_and_chinese_spacing():
    result = normalize_segments(
        [
            {"start": 0, "end": 1, "text": " 嗯，大家好  "},
            {"start": 1, "end": 2, "text": "然后我们聊 ACoS。"},
        ]
    )

    assert result.text == "嗯，大家好然后我们聊 ACoS。"
    assert result.timeline_lines == ("[00:00] 嗯，大家好", "[00:01] 然后我们聊 ACoS。")


def test_normalizer_preserves_trailing_boundary_space_between_english_segments():
    result = normalize_segments(
        [
            {"start": 0, "end": 1, "text": "Hello, "},
            {"start": 1, "end": 2, "text": "world."},
        ]
    )

    assert result.text == "Hello, world."


def test_normalizer_breaks_on_pause_punctuation_and_length_without_splitting_segment():
    result = normalize_segments(
        [
            {"start": 0, "end": 1, "text": "第一句。"},
            {"start": 1.2, "end": 2, "text": "第二句"},
            {"start": 4, "end": 5, "text": "停顿后继续"},
            {"start": 5, "end": 7, "text": "这是一个超过阈值的完整ASR分段"},
        ],
        max_paragraph_chars=8,
        pause_seconds=1.2,
    )

    assert result.paragraphs == (
        "第一句。",
        "第二句",
        "停顿后继续",
        "这是一个超过阈值的完整ASR分段",
    )
    assert "这是一个超过阈值的完整ASR分段" in result.text


def test_timestamp_handles_long_recordings_and_invalid_segment_times():
    result = normalize_segments(
        [
            {"start": 3605.8, "end": 3606, "text": "一小时后"},
            {"start": None, "end": None, "text": "保留无时间文本"},
        ]
    )

    assert format_timestamp(3605.8) == "[60:05]"
    assert result.timeline_lines == ("[60:05] 一小时后",)
    assert result.text == "一小时后保留无时间文本"


def test_timestamp_rejects_values_beyond_the_hard_media_duration():
    result = normalize_segments(
        [{"start": 1e308, "end": 1e308, "text": "保留正文但不写异常时间"}]
    )

    assert result.text == "保留正文但不写异常时间"
    assert result.timeline_lines == ()
    assert format_timestamp(HARD_MAX_MEDIA_DURATION_SECONDS) == "[240:00]"
    with pytest.raises(ValueError, match="supported media duration"):
        format_timestamp(HARD_MAX_MEDIA_DURATION_SECONDS + 1)


def test_timeline_is_chronological_without_reordering_transcript_text():
    result = normalize_segments(
        [
            {"start": 3, "end": 4, "text": "后来"},
            {"start": 1, "end": 2, "text": "先前"},
        ]
    )

    assert result.text == "后来先前"
    assert result.timeline_lines == ("[00:01] 先前", "[00:03] 后来")
