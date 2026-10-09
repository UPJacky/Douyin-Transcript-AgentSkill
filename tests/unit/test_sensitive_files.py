from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_sensitive_files.py"
_SPEC = importlib.util.spec_from_file_location("check_sensitive_files", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
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
    assert path_violations(
        [
            ".env.example",
            "skills/douyin-transcript/assets/config.example.toml",
            "skills/douyin-transcript/src/douyin_transcript/models.py",
            "tests/fixtures/example_output.md",
        ]
    ) == []


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
