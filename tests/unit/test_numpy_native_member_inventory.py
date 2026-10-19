from __future__ import annotations

import hashlib
import io
import sys
import zipfile
from pathlib import Path
from runpy import run_path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = str(ROOT / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
inventory = run_path(str(ROOT / "scripts" / "inventory_numpy_native_members.py"))
InventoryError = inventory["InventoryError"]


def test_wheel_directory_limit_is_checked_before_zipfile_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("numpy/one.dll", b"one")
        archive.writestr("numpy/two.dll", b"two")
    payload = stream.getvalue()
    digest = hashlib.sha256(payload).hexdigest()
    wheel = inventory["Wheel"](
        "numpy",
        "1.0",
        "https://files.example/numpy-1.0-cp311-win_amd64.whl",
        digest,
        len(payload),
    )
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / digest).write_bytes(payload)

    directory_globals = inventory["_zip_directory_info"].__globals__
    monkeypatch.setitem(directory_globals, "_MAX_ARCHIVE_MEMBERS", 1)

    def fail_if_materialized(*_args, **_kwargs):
        pytest.fail("NumPy wheel ZIP must be preflighted before ZipFile")

    monkeypatch.setattr(inventory["zipfile"], "ZipFile", fail_if_materialized)

    with pytest.raises(InventoryError, match="member limit"):
        inventory["_inventory_wheel"](wheel, "0" * 64, cache_dir)


def test_oversized_record_is_rejected_before_member_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_info = type(
        "ZipInfoStub",
        (),
        {"filename": "numpy-1.0.dist-info/RECORD", "file_size": 128},
    )()
    opened = False

    class ArchiveStub:
        def open(self, *_args, **_kwargs):
            nonlocal opened
            opened = True
            pytest.fail("oversized RECORD must not be read")

    record_globals = inventory["_record_rows"].__globals__
    monkeypatch.setitem(record_globals, "_MAX_RECORD_BYTES", 16)

    with pytest.raises(InventoryError, match="RECORD exceeds byte limit"):
        inventory["_record_rows"](ArchiveStub(), [record_info])

    assert not opened


def test_numpy_inventory_cli_escapes_terminal_controls(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    message = "unsafe\x1b[31m\u202e"

    def fail_lock_read(*_args, **_kwargs):
        raise InventoryError(message)

    main_globals = inventory["main"].__globals__
    monkeypatch.setitem(main_globals, "_locked_numpy_wheels", fail_lock_read)

    result = inventory["main"](
        ["--lock", "unused", "--cache-dir", "unused", "--output", "unused"]
    )
    stderr = capsys.readouterr().err

    assert result == 2
    assert "unsafe\\u001b[31m\\u202e" in stderr
    assert "\x1b" not in stderr
    assert "\u202e" not in stderr
