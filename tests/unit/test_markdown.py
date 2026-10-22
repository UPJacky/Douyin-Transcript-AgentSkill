from __future__ import annotations

import json
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import pytest
from douyin_transcript import markdown as markdown_module
from douyin_transcript.markdown import (
    MAX_FRONTMATTER_CHARACTERS,
    escape_markdown_text,
    render_transcript_markdown,
    serialize_frontmatter,
    write_reviewed_transcript_markdown,
    write_transcript_markdown,
)


def test_frontmatter_quotes_yaml_sensitive_values_and_keeps_unicode():
    title = '标题: "# 转写\n第二行'
    serialized = serialize_frontmatter(
        {
            "title": title,
            "source_url": "https://example.test/a?x=1#fragment",
            "author": None,
        }
    )

    assert f"title: {json.dumps(title, ensure_ascii=False)}" in serialized
    assert 'source_url: "https://example.test/a?x=1#fragment"' in serialized
    assert "author: null" in serialized
    assert serialized.startswith("---\n") and serialized.endswith("\n---")


def test_frontmatter_rejects_invalid_keys_and_non_finite_numbers():
    for metadata in ({"title: bad": "x"}, {"duration": float("nan")}):
        try:
            serialize_frontmatter(metadata)
        except (TypeError, ValueError):
            pass
        else:
            raise AssertionError("unsafe frontmatter input should be rejected")


def test_writer_rejects_frontmatter_over_shared_limit_before_publishing(tmp_path):
    with pytest.raises(ValueError, match="frontmatter exceeds"):
        write_transcript_markdown(
            tmp_path,
            "title",
            "transcript",
            {"metadata": "x" * MAX_FRONTMATTER_CHARACTERS},
        )

    assert not list(tmp_path.glob("*.md"))


def test_render_contains_verbatim_body_and_standard_sections():
    rendered = render_transcript_markdown(
        "口播标题", "嗯，然后我们继续。", {"video_id": "123", "author": None}
    )

    assert rendered.startswith(
        '---\ntitle: "口播标题"\nvideo_id: "123"\nauthor: null\n---'
    )
    assert "# 口播标题" in rendered
    assert "## 口播逐字稿\n\n嗯，然后我们继续。" in rendered


def test_untrusted_title_and_transcript_markdown_syntax_is_escaped_as_text():
    hostile = (
        "![x](https://example.invalid/pixel) <img src=x onerror=alert(1)> "
        "[link](javascript:alert(1)) `code`\n```html\n<script>alert(1)</script>"
    )
    rendered = render_transcript_markdown(hostile, hostile, {})

    assert r"\!\[x\]\(https\:\/\/example\.invalid\/pixel\)" in rendered
    assert r"\<img src\=x onerror\=alert\(1\)\>" in rendered
    assert r"\[link\]\(javascript\:alert\(1\)\)" in rendered
    assert r"\`\`\`html" in rendered
    assert r"\<script\>alert\(1\)\<\/script\>" in rendered
    document_body = rendered.split("\n---\n\n", 1)[1]
    assert "![x](https://example.invalid/pixel)" not in document_body
    assert "<script>" not in document_body


def test_render_removes_title_control_characters_from_frontmatter_and_heading():
    title = "safe\x1b[2J\x07\x7f\x85\x9b\ncontinued"

    rendered = render_transcript_markdown(title, "spoken\x1b[31m\x85\x9b\nnext", {})

    assert not any(0x7F <= ord(character) <= 0x9F for character in rendered)
    assert "\x1b" not in rendered and "\x07" not in rendered
    assert 'title: "safe[2Jcontinued"' in rendered
    assert "# safe\\[2Jcontinued" in rendered
    assert "spoken\\[31m\nnext" in rendered


def test_render_strips_bidi_controls_from_title_and_shows_them_in_body():
    body = "spoken\u202e words عربي\u200cمتصل emoji\u200d"
    rendered = render_transcript_markdown("safe\u202eTitle", body, {})

    assert "safeTitle" in rendered
    assert "\u202e" not in rendered
    assert r"spoken\<U\+202E\> words" in rendered
    assert "عربي\u200cمتصل" in rendered and "emoji\u200d" in rendered


def test_markdown_text_escaping_prevents_indented_code_blocks():
    assert escape_markdown_text("    <script>") == "&#32;&#32;&#32;&#32;\\<script\\>"


def test_writer_is_utf8_atomic_and_never_reuses_by_public_video_id(tmp_path):
    output_dir = tmp_path / "output"
    desired = output_dir / "同名_视频.md"
    output_dir.mkdir()
    desired.write_text("手工文件", encoding="utf-8")
    metadata = {"source": "douyin", "language": "zh", "author": None}

    first = write_transcript_markdown(
        output_dir, "同名/视频", "嗯，保留全文。", metadata, video_id="1234567890"
    )
    first_content = first.read_bytes()
    second = write_transcript_markdown(
        output_dir, "同名/视频", "新的识别结果", metadata, video_id="1234567890"
    )

    assert first != second
    assert first.name == "同名_视频__34567890.md"
    assert first_content.decode("utf-8").endswith("嗯，保留全文。\n")
    assert "新的识别结果" in second.read_text(encoding="utf-8")
    assert "嗯，保留全文。" in first.read_text(encoding="utf-8")
    assert desired.read_text(encoding="utf-8") == "手工文件"
    assert not list(output_dir.glob("*.tmp"))


def test_writer_different_videos_never_replace_colliding_names(tmp_path):
    first = write_transcript_markdown(
        tmp_path, "同名", "第一篇", {"source": "douyin"}, video_id="11111111"
    )
    second = write_transcript_markdown(
        tmp_path, "同名", "第二篇", {"source": "douyin"}, video_id="22222222"
    )

    assert first.name == "同名.md"
    assert second.name == "同名__22222222.md"
    assert "第一篇" in first.read_text(encoding="utf-8")
    assert "第二篇" in second.read_text(encoding="utf-8")


def test_writer_keeps_untrusted_empty_title_fallback_inside_output_dir(tmp_path):
    output_dir = tmp_path / "output"

    written = write_transcript_markdown(
        output_dir,
        "",
        "transcript",
        {},
        video_id="../escape",
    )

    assert written.resolve().parent == output_dir.resolve()
    assert written.is_file()
    assert not (tmp_path / "escape.md").exists()


def test_writer_rejects_path_like_extension_before_publication(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "title").mkdir()

    with pytest.raises(ValueError, match="extension"):
        write_transcript_markdown(
            output_dir,
            "title",
            "body",
            {},
            extension="/../../escape.md",
        )

    assert not (tmp_path / "escape.md").exists()


def test_writer_fails_if_parent_directory_cannot_be_synced(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    synced: list[Path] = []

    if os.name == "nt":

        def fail_publish(source: Path, destination: Path) -> None:
            raise OSError("write-through rename failed")

        monkeypatch.setattr(markdown_module, "_publish_no_replace", fail_publish)
        expected_error = "write-through rename failed"
    else:
        original_sync = markdown_module._fsync_directory

        def fail_sync(path: Path) -> None:
            synced.append(path)
            if path == output_dir:
                raise OSError("directory sync failed")
            original_sync(path)

        monkeypatch.setattr(markdown_module, "_fsync_directory", fail_sync)
        expected_error = "directory sync failed"

    with pytest.raises(OSError, match=expected_error):
        write_transcript_markdown(output_dir, "title", "body", {})

    if os.name != "nt":
        assert synced[-1] == output_dir
        assert len(list(output_dir.glob("*.md"))) == 1
    else:
        assert not list(output_dir.glob("*.md"))
    assert not list(output_dir.glob("*.tmp"))


def test_writer_creates_nested_output_directory_for_concurrent_tasks(tmp_path):
    output_dir = tmp_path / "new-parent" / "new-output"
    barrier = Barrier(4)

    def write(index: int) -> Path:
        barrier.wait(timeout=5)
        return write_transcript_markdown(
            output_dir, f"title-{index}", f"body-{index}", {}
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        outputs = list(executor.map(write, range(4)))

    assert len(set(outputs)) == 4
    assert all(path.is_file() for path in outputs)
    assert not list(tmp_path.rglob(".douyin-tmp-*"))


@pytest.mark.skipif(os.name != "nt", reason="Windows MoveFileEx error mapping")
def test_windows_generic_move_error_is_not_treated_as_collision(tmp_path, monkeypatch):
    class FakeFunction:
        argtypes = None
        restype = None

        def __call__(self, *_args):
            return 0

    destination = tmp_path / "appeared.md"
    destination.write_text("external file", encoding="utf-8")
    fake_kernel32 = SimpleNamespace(MoveFileExW=FakeFunction())
    monkeypatch.setattr(
        markdown_module.ctypes, "WinDLL", lambda *_args, **_kwargs: fake_kernel32
    )
    monkeypatch.setattr(markdown_module.ctypes, "get_last_error", lambda: 5)

    with pytest.raises(OSError) as error:
        markdown_module._move_path_write_through(tmp_path / "source.tmp", destination)

    assert not isinstance(error.value, FileExistsError)
    assert error.value.winerror == 5


def test_reviewed_sidecar_preserves_raw_frontmatter_and_never_overwrites(tmp_path):
    raw_path = write_transcript_markdown(
        tmp_path,
        "模型校对样例",
        "原始正文不能被覆盖。",
        {"video_id": "synthetic-123", "author": "测试"},
    )
    raw_before = raw_path.read_bytes()
    raw_frontmatter = raw_before.split(b"\n---\n", 1)[0] + b"\n---"
    reviewed_body = "这里是校对后的闭源术语保留原意\n\n下一段继续原来的内容"

    first = write_reviewed_transcript_markdown(raw_path, reviewed_body)
    first_bytes = first.read_bytes()
    second = write_reviewed_transcript_markdown(raw_path, reviewed_body)

    assert first.name == "模型校对样例.reviewed.md"
    assert second.name == "模型校对样例__2.reviewed.md"
    assert first.read_bytes() == first_bytes
    assert raw_path.read_bytes() == raw_before
    assert first_bytes.startswith(raw_frontmatter)
    assert b'video_id: "synthetic-123"' in first_bytes
    assert "未经人工逐字校对".encode() not in first_bytes
    assert "当前 Agent 默认模型进行文本校对和分段整理".encode() in first_bytes
    assert "这里是校对后的闭源术语保留原意".encode() in first_bytes
    assert "原始正文不能被覆盖".encode() not in first_bytes


@pytest.mark.parametrize(
    ("reviewed_body", "message"),
    [
        ("", "reviewed text is empty"),
        ("甲" * 299 + "。", "paragraph breaks"),
    ],
)
def test_reviewed_sidecar_rejects_incomplete_review_format(
    tmp_path, reviewed_body, message
):
    raw_path = write_transcript_markdown(tmp_path, "format-check", "raw text。", {})

    with pytest.raises(ValueError, match=message):
        write_reviewed_transcript_markdown(raw_path, reviewed_body)

    assert not list(tmp_path.glob("*.reviewed.md"))


def test_reviewed_sidecar_accepts_long_punctuation_free_text(tmp_path):
    raw_path = write_transcript_markdown(
        tmp_path, "punctuation-check", "raw text。", {}
    )
    reviewed_body = "转写文字" * 41

    reviewed_path = write_reviewed_transcript_markdown(raw_path, reviewed_body)

    assert reviewed_path.read_text(encoding="utf-8").endswith(reviewed_body + "\n")


def test_reviewed_sidecar_accepts_punctuation_free_paragraphs(tmp_path):
    raw_path = write_transcript_markdown(
        tmp_path, "paragraph-punctuation-check", "raw text。", {}
    )
    reviewed_body = "甲" * 149 + "\n\n" + "乙" * 151

    reviewed_path = write_reviewed_transcript_markdown(raw_path, reviewed_body)

    assert reviewed_path.read_text(encoding="utf-8").endswith(reviewed_body + "\n")


def test_reviewed_sidecar_rejects_symlinked_raw_input(tmp_path):
    raw_path = write_transcript_markdown(tmp_path, "symlink-source", "raw text。", {})
    alias = tmp_path / "alias.md"
    try:
        alias.symlink_to(raw_path)
    except OSError as exc:
        pytest.skip(
            f"filesystem does not permit symlink creation: {type(exc).__name__}"
        )

    with pytest.raises(PermissionError):
        write_reviewed_transcript_markdown(alias, "已校对正文")

    assert not (tmp_path / "alias.reviewed.md").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not Windows ACLs")
def test_reviewed_sidecar_refuses_shared_parent_without_changing_permissions(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    shared.chmod(0o755)
    raw_path = shared / "raw.md"
    raw_path.write_text(
        '---\ntitle: "raw"\n---\n\n# raw\n\n'
        "> 本文为自动语音识别逐字稿，未经人工逐字校对。\n\n"
        "## 口播逐字稿\n\nraw text。\n",
        encoding="utf-8",
    )

    with pytest.raises(PermissionError):
        write_reviewed_transcript_markdown(raw_path, "已校对正文。")

    assert stat.S_IMODE(shared.stat().st_mode) == 0o755
    assert not list(shared.glob("*.reviewed.md"))
