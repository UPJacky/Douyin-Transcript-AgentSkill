from __future__ import annotations

import hashlib
import gzip
import io
import json
import os
import struct
import tarfile
import zipfile
import sys
import time
from pathlib import Path
from runpy import run_path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = str(ROOT / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
verifier = run_path(str(ROOT / "scripts" / "verify_spdx_evidence.py"))
verify_evidence = verifier["verify_evidence"]
verified_artifact_snapshot = verifier["_verified_artifact_snapshot"]
verifier_globals = verify_evidence.__globals__
EvidenceVerificationError = verifier["EvidenceVerificationError"]


def _fixture(tmp_path: Path, archive_kind: str = "sdist") -> tuple[Path, Path, Path]:
    if archive_kind == "wheel":
        metadata_path = "demo-1.0.dist-info/METADATA"
        license_path = "demo-1.0.dist-info/licenses/LICENSE"
        notice_path = "demo/NOTICE"
        artifact_url = "https://files.example/demo-1.0-py3-none-any.whl"
    else:
        metadata_path = "demo-1.0/PKG-INFO"
        license_path = "demo-1.0/LICENSE"
        notice_path = "demo-1.0/NOTICE"
        artifact_url = "https://files.example/demo-1.0.tar.gz"

    metadata = (
        b"Metadata-Version: 2.4\nName: demo\nVersion: 1.0\nLicense-Expression: MIT\n\n"
    )
    license_text = b"MIT License fixture\n"
    notice_text = b"Third-party notice fixture\n"
    members = {
        metadata_path: metadata,
        license_path: license_text,
        notice_path: notice_text,
    }
    artifact_path = tmp_path / "fixture.archive"
    if archive_kind == "wheel":
        with zipfile.ZipFile(
            artifact_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for name, content in members.items():
                archive.writestr(name, content)
        artifact_type = "wheel"
    else:
        with tarfile.open(artifact_path, "w:gz") as archive:
            for name, content in members.items():
                info = tarfile.TarInfo(name)
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        artifact_type = "sdist"

    archive_bytes = artifact_path.read_bytes()
    artifact_digest = hashlib.sha256(archive_bytes).hexdigest()
    artifact_size = len(archive_bytes)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / artifact_digest).write_bytes(archive_bytes)

    lock_path = tmp_path / "uv.lock"
    lock_path.write_text(
        "version = 1\n\n[[package]]\n"
        'name = "demo"\nversion = "1.0"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
        + (
            f'wheels = [{{ url = "{artifact_url}", hash = "sha256:{artifact_digest}", size = {artifact_size} }}]\n'
            if artifact_type == "wheel"
            else f'sdist = {{ url = "{artifact_url}", hash = "sha256:{artifact_digest}", size = {artifact_size} }}\n'
        ),
        encoding="utf-8",
    )
    evidence = {
        "schema_version": 1,
        "packages": [
            {
                "name": "demo",
                "version": "1.0",
                "artifact_type": artifact_type,
                "artifact_url": artifact_url,
                "artifact_sha256": artifact_digest,
                "artifact_size": artifact_size,
                "metadata_path": metadata_path,
                "metadata_sha256": hashlib.sha256(metadata).hexdigest(),
                "metadata_field": "License-Expression",
                "metadata_field_value": "MIT",
                "declared_expression": None,
                "mapped_expression": None,
                "status": "file_verified_declaration",
                "license_file": {
                    "artifact_type": artifact_type,
                    "artifact_url": artifact_url,
                    "artifact_sha256": artifact_digest,
                    "artifact_size": artifact_size,
                    "path": license_path,
                    "sha256": hashlib.sha256(license_text).hexdigest(),
                    "expression": "MIT",
                },
                "license_notices": [
                    {
                        "artifact_type": artifact_type,
                        "artifact_url": artifact_url,
                        "artifact_sha256": artifact_digest,
                        "artifact_size": artifact_size,
                        "path": notice_path,
                        "sha256": hashlib.sha256(notice_text).hexdigest(),
                        "size": len(notice_text),
                    }
                ],
            }
        ],
    }
    evidence_path = tmp_path / "license-evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    return lock_path, evidence_path, cache_dir


def test_verified_artifact_snapshot_is_unchanged_when_cache_path_changes(
    tmp_path: Path,
) -> None:
    locked_bytes = b"bytes bound to the expected artifact SHA-256"
    digest = hashlib.sha256(locked_bytes).hexdigest()
    cache_path = tmp_path / digest
    cache_path.write_bytes(locked_bytes)

    with verified_artifact_snapshot(
        cache_path,
        digest,
        len(locked_bytes),
        deadline=time.monotonic() + 10,
    ) as snapshot:
        cache_path.write_bytes(b"replacement bytes with matching length? no")
        snapshot.seek(0)
        assert snapshot.read() == locked_bytes


@pytest.mark.parametrize("archive_kind", ["sdist", "wheel"])
def test_verifies_artifact_metadata_license_and_notice_without_extraction(
    tmp_path: Path, archive_kind: str
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path, archive_kind)

    summary = verify_evidence(lock_path, evidence_path, cache_dir)

    assert summary.packages == 1
    assert summary.artifacts == 1
    assert summary.metadata_members == 1
    assert summary.license_members == 1
    assert summary.notice_members == 1
    assert len(list(cache_dir.iterdir())) == 1


def test_sdist_member_limit_applies_to_each_bounded_archive_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path, "sdist")
    monkeypatch.setitem(verifier_globals, "_MAX_ARCHIVE_MEMBERS", 3)

    summary = verify_evidence(lock_path, evidence_path, cache_dir)

    assert summary.metadata_members == 1
    assert summary.license_members == 1
    assert summary.notice_members == 1


def test_verifies_supplemental_members_for_metadata_declared_package(
    tmp_path: Path,
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path, "wheel")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    row = evidence["packages"][0]
    row["status"] = "valid_spdx_declaration"
    row["declared_expression"] = "MIT"
    row.pop("license_file")
    row.pop("license_notices")
    row["artifact_members"] = [
        {
            "artifact_type": "wheel",
            "artifact_url": row["artifact_url"],
            "artifact_sha256": row["artifact_sha256"],
            "artifact_size": row["artifact_size"],
            "path": "demo/NOTICE",
            "sha256": hashlib.sha256(b"Third-party notice fixture\n").hexdigest(),
            "size": len(b"Third-party notice fixture\n"),
        }
    ]
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    summary = verify_evidence(lock_path, evidence_path, cache_dir)

    assert summary.license_members == 0
    assert summary.notice_members == 0
    assert summary.supplemental_members == 1


def test_rejects_tampered_supplemental_member_digest(tmp_path: Path) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path, "wheel")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    row = evidence["packages"][0]
    row["status"] = "valid_spdx_declaration"
    row["declared_expression"] = "MIT"
    row.pop("license_file")
    row.pop("license_notices")
    row["artifact_members"] = [
        {
            "artifact_type": "wheel",
            "artifact_url": row["artifact_url"],
            "artifact_sha256": row["artifact_sha256"],
            "artifact_size": row["artifact_size"],
            "path": "demo/NOTICE",
            "sha256": "0" * 64,
            "size": len(b"Third-party notice fixture\n"),
        }
    ]
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(EvidenceVerificationError, match="supplemental SHA-256 differs"):
        verify_evidence(lock_path, evidence_path, cache_dir)


def test_cli_reports_summary_for_local_cache(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path, "wheel")

    exit_code = verifier["main"](
        [
            "--lockfile",
            str(lock_path),
            "--evidence",
            str(evidence_path),
            "--cache-dir",
            str(cache_dir),
        ]
    )

    assert exit_code == 0
    assert (
        "1 packages, 1 artifacts, 1 metadata, 1 license, 1 notice, 0 supplemental members"
        in capsys.readouterr().out
    )


@pytest.mark.parametrize(
    ("section", "expected_message"),
    [
        ("metadata", "metadata SHA-256 differs from evidence"),
        ("license", "license SHA-256 differs from evidence"),
        ("notice", "notice SHA-256 differs from evidence"),
    ],
)
def test_rejects_tampered_member_digest(
    tmp_path: Path, section: str, expected_message: str
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    row = evidence["packages"][0]
    if section == "metadata":
        row["metadata_sha256"] = "0" * 64
    elif section == "license":
        row["license_file"]["sha256"] = "0" * 64
    else:
        row["license_notices"][0]["sha256"] = "0" * 64
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(EvidenceVerificationError, match=expected_message):
        verify_evidence(lock_path, evidence_path, cache_dir)


def test_rejects_missing_evidence_member(tmp_path: Path) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["packages"][0]["license_file"]["path"] = "demo-1.0/NOT-PRESENT"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(EvidenceVerificationError, match="Archive member is missing"):
        verify_evidence(lock_path, evidence_path, cache_dir)


@pytest.mark.parametrize("control", ["\x1b", "\r", "\n", "\x85", "\u202e"])
def test_rejects_terminal_controls_in_archive_paths(control: str) -> None:
    with pytest.raises(EvidenceVerificationError, match="relative POSIX archive path"):
        verifier["_safe_member_path"](f"demo-1.0/{control}LICENSE", "license path")


def test_accepts_unicode_archive_paths() -> None:
    assert verifier["_safe_member_path"]("demo-1.0/许可证.txt", "license path") == (
        "demo-1.0/许可证.txt"
    )


def test_cli_escapes_control_characters_in_evidence_diagnostics(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["packages"][0]["name"] = "demo\x1b[31m\r\n"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    exit_code = verifier["main"](
        [
            "--lockfile",
            str(lock_path),
            "--evidence",
            str(evidence_path),
            "--cache-dir",
            str(cache_dir),
        ]
    )

    diagnostic = capsys.readouterr().err
    assert exit_code == 1
    assert "\\u001b[31m\\u000d\\u000a" in diagnostic
    assert "\x1b" not in diagnostic and "\r" not in diagnostic
    assert "\n" not in diagnostic.removesuffix("\n")


def test_rejects_cached_artifact_with_wrong_sha256(tmp_path: Path) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    digest = evidence["packages"][0]["artifact_sha256"]
    cache_path = cache_dir / digest
    wrong_bytes = bytearray(cache_path.read_bytes())
    wrong_bytes[-1] ^= 1
    cache_path.write_bytes(wrong_bytes)

    with pytest.raises(
        EvidenceVerificationError, match="Artifact SHA-256 differs from uv.lock"
    ):
        verify_evidence(lock_path, evidence_path, cache_dir)


def test_rejects_artifact_hash_in_manifest_that_is_not_locked(tmp_path: Path) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["packages"][0]["artifact_sha256"] = "0" * 64
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(EvidenceVerificationError, match="not pinned by uv.lock"):
        verify_evidence(lock_path, evidence_path, cache_dir)


@pytest.mark.parametrize(
    ("limit_name", "limit", "expected_message"),
    [
        (
            "_MAX_ARCHIVE_UNCOMPRESSED_BYTES",
            1024,
            "decompressed size limit",
        ),
        ("_MAX_ARCHIVE_MEMBERS", 1, "member limit"),
        ("_MAX_ARCHIVE_PARSE_SECONDS", 0.0, "second limit"),
    ],
)
def test_rejects_tar_archive_when_global_resource_budget_is_exceeded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    limit_name: str,
    limit: int | float,
    expected_message: str,
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path)
    monkeypatch.setitem(verifier_globals, limit_name, limit)

    with pytest.raises(EvidenceVerificationError, match=expected_message):
        verify_evidence(lock_path, evidence_path, cache_dir)


def test_tar_evidence_members_share_one_bounded_decompression_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    digest = evidence["packages"][0]["artifact_sha256"]
    artifact = (cache_dir / digest).read_bytes()
    # One complete parse fits. Metadata, license, and notice evidence should
    # share that pass instead of expanding the tar once per path.
    limit = len(gzip.decompress(artifact))
    monkeypatch.setitem(verifier_globals, "_MAX_ARCHIVE_UNCOMPRESSED_BYTES", limit)

    summary = verify_evidence(lock_path, evidence_path, cache_dir)

    assert summary.metadata_members == 1
    assert summary.license_members == 1
    assert summary.notice_members == 1


def test_rejects_artifact_above_hard_size_limit_before_hashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path, "wheel")
    monkeypatch.setitem(verifier_globals, "_MAX_ARTIFACT_SIZE_BYTES", 1)

    def fail_if_temp_snapshot_created(*_args, **_kwargs):
        pytest.fail("oversized artifact must be rejected before snapshot creation")

    monkeypatch.setattr(
        verifier["tempfile"], "TemporaryFile", fail_if_temp_snapshot_created
    )

    with pytest.raises(
        EvidenceVerificationError, match="Artifact exceeds .* size limit"
    ):
        verify_evidence(lock_path, evidence_path, cache_dir)


def test_rejects_cache_size_mismatch_before_hashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path, "wheel")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    digest = evidence["packages"][0]["artifact_sha256"]
    with (cache_dir / digest).open("ab") as stream:
        stream.write(b"extra")

    def fail_if_temp_snapshot_created(*_args, **_kwargs):
        pytest.fail("cache size mismatch must be rejected before snapshot creation")

    monkeypatch.setattr(
        verifier["tempfile"], "TemporaryFile", fail_if_temp_snapshot_created
    )

    with pytest.raises(
        EvidenceVerificationError, match="Artifact size differs from uv.lock"
    ):
        verify_evidence(lock_path, evidence_path, cache_dir)


@pytest.mark.parametrize(
    ("limit_name", "limit", "expected_message"),
    [
        ("_MAX_ARCHIVE_MEMBERS", 2, "member limit"),
        ("_MAX_ZIP_CENTRAL_DIRECTORY_BYTES", 1, "central directory exceeds"),
    ],
)
def test_wheel_directory_limits_are_checked_before_zipfile_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    limit_name: str,
    limit: int,
    expected_message: str,
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path, "wheel")
    monkeypatch.setitem(verifier_globals, limit_name, limit)

    def fail_if_materialized(*_args, **_kwargs):
        pytest.fail("ZIP central directory must be preflighted before ZipFile")

    monkeypatch.setattr(verifier["zipfile"], "ZipFile", fail_if_materialized)

    with pytest.raises(EvidenceVerificationError, match=expected_message):
        verify_evidence(lock_path, evidence_path, cache_dir)


def test_rejects_conflicting_package_metadata_for_shared_archive_member(
    tmp_path: Path,
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path, "wheel")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    original = evidence["packages"][0]
    alias = dict(original)
    alias["name"] = "demo-alias"
    evidence["packages"].append(alias)
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    lock_path.write_text(
        lock_path.read_text(encoding="utf-8")
        + "\n[[package]]\n"
        + 'name = "demo-alias"\nversion = "1.0"\n'
        + 'source = { registry = "https://pypi.org/simple" }\n'
        + f'wheels = [{{ url = "{original["artifact_url"]}", '
        + f'hash = "sha256:{original["artifact_sha256"]}", '
        + f"size = {original['artifact_size']} }}]\n",
        encoding="utf-8",
    )

    with pytest.raises(
        EvidenceVerificationError, match="Conflicting evidence for archive member"
    ):
        verify_evidence(lock_path, evidence_path, cache_dir)


def test_wheel_preflight_counts_actual_central_directory_records() -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("one", b"1")
        archive.writestr("two", b"2")
        archive.writestr("three", b"3")
    data = bytearray(stream.getvalue())
    eocd_index = data.rfind(b"PK\x05\x06")
    struct.pack_into("<HH", data, eocd_index + 8, 1, 1)

    with pytest.raises(
        EvidenceVerificationError,
        match="entry count differs from its end record",
    ):
        verifier["_zip_directory_info"](
            io.BytesIO(data), verifier["_ArchiveReadBudget"]()
        )


def test_verifier_rejects_non_license_header_as_spdx_declaration(
    tmp_path: Path,
) -> None:
    lock_path, evidence_path, _cache_dir = _fixture(tmp_path, "wheel")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    row = evidence["packages"][0]
    row["status"] = "valid_spdx_declaration"
    row["metadata_field"] = "X-Claim"
    row["declared_expression"] = "MIT"
    lock = verifier["tomllib"].loads(lock_path.read_text(encoding="utf-8"))

    with pytest.raises(
        EvidenceVerificationError, match="Invalid SPDX declaration evidence"
    ):
        verifier["_collect_artifacts"](lock, evidence)


@pytest.mark.parametrize(
    ("limit_name", "label"),
    [
        ("_MAX_LOCK_FILE_BYTES", "uv.lock exceeds"),
        ("_MAX_EVIDENCE_FILE_BYTES", "License evidence document exceeds"),
    ],
)
def test_lock_and_evidence_files_are_size_limited_before_parsing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    limit_name: str,
    label: str,
) -> None:
    lock_path, evidence_path, cache_dir = _fixture(tmp_path, "wheel")
    monkeypatch.setitem(verifier_globals, limit_name, 1)

    with pytest.raises(EvidenceVerificationError, match=label):
        verify_evidence(lock_path, evidence_path, cache_dir)


@pytest.mark.skipif(sys.platform == "win32", reason="FIFO replacement requires POSIX")
def test_open_regular_file_rejects_fifo_swapped_after_lstat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "cache-entry"
    path.write_bytes(b"regular cache entry")
    original_open = os.open

    def swap_then_open(candidate, flags, *args, **kwargs):
        if Path(candidate) == path:
            path.unlink()
            os.mkfifo(path)
        return original_open(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(verifier["os"], "open", swap_then_open)
    with pytest.raises(EvidenceVerificationError, match="must be a regular file"):
        verifier["_open_regular_file"](path, "Cache entry")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX FIFO behavior")
def test_bounded_text_reader_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    path = tmp_path / "fifo-input"
    os.mkfifo(path)

    with pytest.raises(EvidenceVerificationError, match="regular, non-symlink file"):
        verifier["_read_bounded_text"](path, 1024, "Test input", time.monotonic() + 5)
