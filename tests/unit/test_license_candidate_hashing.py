from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = str(ROOT / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import hash_locked_license_candidates as candidate_hash  # noqa: E402


def test_nonregular_candidate_diagnostic_escapes_controls_and_keeps_unicode(
    tmp_path: Path,
) -> None:
    digest = "a" * 64
    member_path = "licenses/许可\x1b[2J"
    row = {
        "artifact_sha256": digest,
        "member_path": member_path,
        "member_size": 1,
        "member_type": "directory",
        "candidate_flags": ["license-notice-name"],
    }
    part_bytes = (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
    part_name = "members.jsonl"
    (tmp_path / part_name).write_bytes(part_bytes)
    manifest = {
        "expected_artifact_count": 1,
        "scanned_artifact_count": 1,
        "failed_artifact_count": 0,
        "not_scanned_artifact_count": 0,
        "member_rows": 1,
        "artifacts": [{"sha256": digest}],
        "jsonl_parts": [
            {
                "path": part_name,
                "sha256": hashlib.sha256(part_bytes).hexdigest(),
                "bytes": len(part_bytes),
                "member_rows": 1,
            }
        ],
    }

    with pytest.raises(candidate_hash.CandidateHashError) as caught:
        candidate_hash._load_unbound_candidates(
            tmp_path,
            manifest,
            {digest: []},
            set(),
        )

    message = str(caught.value)
    assert "\\u001b[2J" in message
    assert "许可" in message
    assert "\x1b" not in message
