from __future__ import annotations

import gzip
import hashlib
import io
import sys
import tarfile
import time
import zipfile
from pathlib import Path
from runpy import run_path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = str(ROOT / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
metadata_audit = run_path(
    str(ROOT / "scripts" / "verify_locked_wheel_metadata_audit.py")
)
sdist_metadata_evidence = metadata_audit["_sdist_metadata_evidence"]
EvidenceVerificationError = metadata_audit["EvidenceVerificationError"]

_PKG_INFO = (
    b"Metadata-Version: 2.4\nName: demo\nVersion: 1.0\nLicense-Expression: MIT\n\n"
)


def _sdist_bytes(*, pax_comment: str | None = None) -> bytes:
    archive_bytes = io.BytesIO()
    with gzip.GzipFile(fileobj=archive_bytes, mode="wb") as compressed:
        with tarfile.open(
            fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT
        ) as archive:
            info = tarfile.TarInfo("demo-1.0/PKG-INFO")
            info.size = len(_PKG_INFO)
            if pax_comment is not None:
                info.pax_headers = {"comment": pax_comment}
            archive.addfile(info, io.BytesIO(_PKG_INFO))
    return archive_bytes.getvalue()


def _read_metadata(sdist: bytes, *, deadline: float | None = None) -> dict[str, object]:
    return sdist_metadata_evidence(
        package_name="demo",
        package_version="1.0",
        artifact_url="https://files.example/demo-1.0.tar.gz",
        artifact_sha256=hashlib.sha256(sdist).hexdigest(),
        artifact_size=len(sdist),
        stream=io.BytesIO(sdist),
        deadline=time.monotonic() + 10 if deadline is None else deadline,
    )


def test_sdist_metadata_is_read_from_bounded_gzip_tar() -> None:
    evidence = _read_metadata(_sdist_bytes())

    assert evidence["metadata_path"] == "demo-1.0/PKG-INFO"
    assert evidence["metadata_name"] == "demo"
    assert evidence["metadata_version"] == "1.0"
    assert evidence["license_fields"] == {
        "License": [],
        "License-Expression": ["MIT"],
    }


def test_sdist_pax_header_is_bounded_before_tar_member_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader_globals = metadata_audit["_BoundedDecompressedReader"].read.__globals__
    budget_globals = metadata_audit["_ArchiveReadBudget"].charge_bytes.__globals__
    monkeypatch.setitem(reader_globals, "_MAX_ARCHIVE_UNCOMPRESSED_BYTES", 256)
    monkeypatch.setitem(budget_globals, "_MAX_ARCHIVE_UNCOMPRESSED_BYTES", 256)
    archive_bytes = _sdist_bytes(pax_comment="x" * 4096)

    with pytest.raises(EvidenceVerificationError, match="decompressed size limit"):
        _read_metadata(archive_bytes)


def test_sdist_decompression_checks_deadline_before_reading() -> None:
    with pytest.raises(
        EvidenceVerificationError,
        match="Source archive metadata scan exceeded its time limit",
    ):
        _read_metadata(
            _sdist_bytes(pax_comment="x" * 4096), deadline=time.monotonic() - 1
        )


def test_wheel_member_limit_is_checked_before_zipfile_materialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("one", b"1")
        archive.writestr("two", b"2")

    directory_globals = metadata_audit["_zip_directory_info"].__globals__
    monkeypatch.setitem(directory_globals, "_MAX_ARCHIVE_MEMBERS", 1)

    def fail_if_materialized(*_args, **_kwargs):
        pytest.fail("wheel ZIP must be preflighted before ZipFile")

    monkeypatch.setattr(metadata_audit["zipfile"], "ZipFile", fail_if_materialized)

    with pytest.raises(EvidenceVerificationError, match="member limit"):
        metadata_audit["_metadata_evidence"](
            package_name="demo",
            package_version="1.0",
            artifact_url="https://files.example/demo-1.0-py3-none-any.whl",
            artifact_sha256="0" * 64,
            artifact_size=len(stream.getvalue()),
            stream=stream,
            deadline=time.monotonic() + 10,
        )


def test_oversized_wheel_record_is_rejected_before_member_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = b"Name: demo\nVersion: 1.0\n\n"
    record = b"x" * 128
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("demo-1.0.dist-info/METADATA", metadata)
        archive.writestr("demo-1.0.dist-info/RECORD", record)

    metadata_globals = metadata_audit["_member_bytes"].__globals__
    monkeypatch.setitem(metadata_globals, "_MAX_MEMBER_BYTES", len(metadata) + 1)
    opened_members: list[str] = []
    original_zipfile = zipfile.ZipFile

    class TrackingArchive:
        def __init__(self, file: io.BytesIO) -> None:
            self._archive = original_zipfile(file)

        def __enter__(self) -> TrackingArchive:
            self._archive.__enter__()
            return self

        def __exit__(self, *args: object) -> object:
            return self._archive.__exit__(*args)

        def infolist(self) -> list[zipfile.ZipInfo]:
            return self._archive.infolist()

        def open(self, info: zipfile.ZipInfo, mode: str = "r"):
            opened_members.append(info.filename)
            return self._archive.open(info, mode)

    monkeypatch.setattr(metadata_audit["zipfile"], "ZipFile", TrackingArchive)

    with pytest.raises(EvidenceVerificationError, match="Archive member exceeds"):
        metadata_audit["_metadata_evidence"](
            package_name="demo",
            package_version="1.0",
            artifact_url="https://files.example/demo-1.0-py3-none-any.whl",
            artifact_sha256="0" * 64,
            artifact_size=len(stream.getvalue()),
            stream=stream,
            deadline=time.monotonic() + 10,
        )

    assert opened_members == ["demo-1.0.dist-info/METADATA"]


def test_metadata_audit_cli_escapes_terminal_controls(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    message = "unsafe\x1b[31m\u202e"
    main_globals = metadata_audit["main"].__globals__
    monkeypatch.setitem(main_globals, "_read_bounded", lambda *_args: b"lock")

    def fail_collection(*_args, **_kwargs):
        raise EvidenceVerificationError(message)

    monkeypatch.setitem(main_globals, "collect_evidence", fail_collection)

    assert metadata_audit["main"](["--cache-dir", str(tmp_path)]) == 1
    stderr = capsys.readouterr().err
    assert "unsafe\\u001b[31m\\u202e" in stderr
    assert "\x1b" not in stderr
    assert "\u202e" not in stderr
