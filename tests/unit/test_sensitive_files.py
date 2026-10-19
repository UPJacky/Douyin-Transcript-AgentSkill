from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_sensitive_files.py"
_SCRIPT_DIRECTORY = str(_SCRIPT.parent)
sys.path.insert(0, _SCRIPT_DIRECTORY)
_SPEC = importlib.util.spec_from_file_location("check_sensitive_files", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
try:
    _SPEC.loader.exec_module(_MODULE)
finally:
    sys.path.remove(_SCRIPT_DIRECTORY)
content_violations = _MODULE.content_violations
path_violations = _MODULE.path_violations
scan_repository = _MODULE.scan_repository


def test_sensitive_path_rules_reject_media_cookies_and_private_data():
    violations = path_violations(
        [
            "recording.wav",
            "browser-profile/Default/Cookies",
            "db/tasks.sqlite3",
            "secrets/.env.production",
        ]
    )

    assert len(violations) == 4
    assert {reason for _name, reason in violations} == {
        "sensitive media, database, key, or partial file",
        "sensitive data directory",
        "environment file",
    }


def test_sensitive_path_rules_reject_generic_cache_directory():
    assert path_violations(["cache/media/unclassified.payload"]) == [
        ("cache/media/unclassified.payload", "sensitive data directory")
    ]


def test_sensitive_path_rules_allow_examples_and_source_assets():
    assert (
        path_violations(
            [
                ".env.example",
                "skills/douyin-transcript/assets/config.example.toml",
                "skills/douyin-transcript/src/douyin_transcript/models.py",
                "tests/fixtures/example_output.md",
            ]
        )
        == []
    )


def test_sensitive_path_rules_reject_paths_that_are_not_canonical_git_paths():
    unsafe_paths = [
        "../outside.txt",
        "nested/../../outside.txt",
        r"nested\outside.txt",
        "C:/outside.txt",
        "//server/share/outside.txt",
        "nested/C:../outside.txt",
        "nested/transcript.txt:private-stream",
        "nested/trailing-dot.",
        "nested/NUL.txt",
    ]

    assert path_violations(unsafe_paths) == [
        (name, "unsafe repository-relative path") for name in unsafe_paths
    ]


def test_sensitive_path_rules_reject_local_media_and_model_weights():
    violations = path_violations(["sample.flac", "weights.safetensors"])

    assert violations == [
        ("sample.flac", "sensitive media, database, key, or partial file"),
        ("weights.safetensors", "model weight or inference artifact"),
    ]


def test_credential_scan_reports_type_without_echoing_value():
    secret = "sessionid=" + ("a" * 24)

    violations = content_violations("sample.txt", secret)

    assert violations == [("sample.txt", "credential assignment")]
    assert secret not in repr(violations)


def test_credential_scan_detects_private_keys_without_echoing_material():
    content = "-----BEGIN " + "PRIVATE KEY-----\nexample\n-----END PRIVATE KEY-----"

    violations = content_violations("key.txt", content)

    assert violations == [("key.txt", "private-key material")]
    assert content not in repr(violations)


@pytest.mark.parametrize(
    "style",
    ["single separators", "JSON escaped separators", "forward slash separators"],
)
def test_personal_windows_profile_paths_are_detected_without_echoing_values(style):
    separator = "\\" if style == "single separators" else "\\\\"
    if style == "forward slash separators":
        content = "forward slash path C:" + "/Users/PrivateUser/Downloads/media.mp4"
    else:
        content = (
            "SDK path C:"
            + separator
            + "Users"
            + separator
            + "PrivateUser"
            + separator
            + ".dotnet"
        )
    violations = content_violations("report.md", content)

    assert violations == [("report.md", "personal Windows user-profile path")]
    assert "PrivateUser" not in repr(violations)


@pytest.mark.parametrize(
    "content",
    [
        r"C:\Users\Example\Transcripts",
        r"C:\\Users\\Example\\Transcripts",
        r"C:\Users\<account>\Transcripts",
        r"C:\Users\USERNAME\Transcripts",
    ],
)
def test_windows_profile_path_placeholders_are_allowed(content):
    assert content_violations("README.md", content) == []


def test_sensitive_file_diagnostics_escape_untrusted_path_controls(monkeypatch, capsys):
    name = "cache/\x1b[2Jbad\r\n\u202e\u2028.txt"
    monkeypatch.setattr(
        _MODULE,
        "scan_repository",
        lambda _root: [(name, "sensitive data directory")],
    )

    assert _MODULE.main() == 1

    diagnostic = capsys.readouterr().err
    assert name not in diagnostic
    assert r"cache/\u001b[2Jbad\u000d\u000a\u202e\u2028.txt" in diagnostic
    assert "Sensitive-file check failed:" in diagnostic


def test_scan_fails_closed_for_large_or_non_text_files(monkeypatch, tmp_path):
    files = {
        "large.txt": b"large",
        "binary.dat": b"a\0b",
        "encoded.dat": b"\xff",
    }
    for name, content in files.items():
        (tmp_path / name).write_bytes(content)
    monkeypatch.setattr(_MODULE, "git_visible_paths", lambda _root: list(files))
    monkeypatch.setattr(_MODULE, "_MAX_TEXT_FILE_BYTES", 4)

    violations = scan_repository(tmp_path)

    assert violations == [
        ("large.txt", "exceeds content scan size limit"),
        ("binary.dat", "binary file requires explicit review"),
        ("encoded.dat", "non-UTF-8 file requires explicit review"),
    ]


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor walk")
def test_scan_rejects_symlinked_parent_before_reading_external_file(
    monkeypatch, tmp_path
):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "transcript.txt").write_text("sessionid=" + "B" * 24, encoding="utf-8")
    (root / "nested").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(
        _MODULE, "git_visible_paths", lambda _root: ["nested/transcript.txt"]
    )
    scan_called = False

    def record_scan(_name, _stream):
        nonlocal scan_called
        scan_called = True
        return []

    monkeypatch.setattr(_MODULE, "_scan_text_file", record_scan)

    violations = scan_repository(root)

    assert violations == [
        (
            "nested/transcript.txt",
            "symbolic link or reparse point cannot be content-scanned",
        )
    ]
    assert not scan_called


@pytest.mark.skipif(os.name != "nt", reason="Windows directory junction")
def test_scan_rejects_junction_parent_before_reading_external_file(
    monkeypatch, tmp_path
):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "transcript.txt").write_text("sessionid=" + "C" * 24, encoding="utf-8")
    junction = root / "nested"
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        pytest.skip("Windows did not allow creating a temporary directory junction")
    monkeypatch.setattr(
        _MODULE, "git_visible_paths", lambda _root: ["nested/transcript.txt"]
    )
    scan_called = False

    def record_scan(_name, _stream):
        nonlocal scan_called
        scan_called = True
        return []

    monkeypatch.setattr(_MODULE, "_scan_text_file", record_scan)

    violations = scan_repository(root)

    assert violations == [
        (
            "nested/transcript.txt",
            "symbolic link or reparse point cannot be content-scanned",
        )
    ]
    assert not scan_called


@pytest.mark.skipif(os.name != "nt", reason="Windows UTF-16 path components")
def test_scan_opens_exact_supplementary_unicode_component(monkeypatch, tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    intended = root / "nested😀x"
    intended.mkdir()
    (intended / "transcript.txt").write_text("sessionid=" + "D" * 24, encoding="utf-8")
    truncated_sibling = root / "nested😀"
    truncated_sibling.mkdir()
    (truncated_sibling / "transcript.txt").write_text(
        "ordinary synthetic text", encoding="utf-8"
    )
    name = "nested😀x/transcript.txt"
    monkeypatch.setattr(_MODULE, "git_visible_paths", lambda _root: [name])

    violations = scan_repository(root)

    assert violations == [(name, "credential assignment")]


def test_scan_detects_credential_after_long_whitespace_across_chunk_boundary(
    monkeypatch, tmp_path
):
    name = "artifact-inventory.jsonl"
    boundary = 64 * 1024
    content = (
        b"x" * (boundary - 11)
        + b" "
        + b"sessionid="
        + b" " * (boundary + 40)
        + b"a" * 16
        + b"\n"
        + b"x" * (2 * 1024 * 1024)
    )
    (tmp_path / name).write_bytes(content)
    monkeypatch.setattr(_MODULE, "git_visible_paths", lambda _root: [name])

    violations = scan_repository(tmp_path)

    assert violations == [(name, "credential assignment")]
