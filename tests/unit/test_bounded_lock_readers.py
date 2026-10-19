from __future__ import annotations

import sys
from pathlib import Path
from runpy import run_path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = str(ROOT / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import inventory_locked_pe_imports as pe_inventory  # noqa: E402
import inventory_numpy_native_members as numpy_inventory  # noqa: E402
import verify_spdx_evidence as evidence_verifier  # noqa: E402

artifact_inventory = run_path(
    str(ROOT / "scripts" / "inventory_locked_artifact_members.py")
)

LOCK_READERS = [
    pytest.param(
        artifact_inventory["_lock_identities"],
        artifact_inventory["InventoryError"],
        id="artifact-members",
    ),
    pytest.param(
        numpy_inventory._locked_numpy_wheels,
        numpy_inventory.InventoryError,
        id="numpy-native-members",
    ),
    pytest.param(
        pe_inventory._locked_windows_wheels,
        pe_inventory.InventoryError,
        id="locked-pe-imports",
    ),
]


def _valid_lock_bytes() -> bytes:
    digest = "a" * 64
    return (
        "version = 1\n"
        "revision = 3\n\n"
        "[[package]]\n"
        'name = "numpy"\n'
        'version = "1.0"\n'
        "wheels = [{ url = "
        '"https://files.example/numpy-1.0-cp313-cp313-win_amd64.whl", '
        f'hash = "sha256:{digest}", size = 1 }}]\n'
    ).encode("utf-8")


@pytest.mark.parametrize(("reader", "_error_type"), LOCK_READERS)
def test_lock_readers_accept_files_exactly_at_shared_size_limit(
    reader, _error_type, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _valid_lock_bytes()
    path = tmp_path / "uv.lock"
    path.write_bytes(payload)
    monkeypatch.setattr(evidence_verifier, "_MAX_LOCK_FILE_BYTES", len(payload))

    result = reader(path)

    assert result


@pytest.mark.parametrize(("reader", "error_type"), LOCK_READERS)
def test_lock_readers_reject_oversized_files_before_toml_parsing(
    reader, error_type, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    limit = 4096
    path = tmp_path / "uv.lock"
    with path.open("wb") as sparse_file:
        sparse_file.truncate(limit + 1)
    monkeypatch.setattr(evidence_verifier, "_MAX_LOCK_FILE_BYTES", limit)

    original_open = evidence_verifier._open_regular_file

    class NoReadStream:
        def __init__(self, stream):
            self._stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self._stream.close()

        def fileno(self):
            return self._stream.fileno()

        def read(self, _size=-1):
            pytest.fail("oversized uv.lock must be rejected before reading bytes")

    monkeypatch.setattr(
        evidence_verifier,
        "_open_regular_file",
        lambda candidate, label: NoReadStream(original_open(candidate, label)),
    )

    def fail_if_parsed(*_args, **_kwargs):
        pytest.fail("oversized uv.lock must be rejected before TOML parsing")

    monkeypatch.setattr(reader.__globals__["tomllib"], "loads", fail_if_parsed)

    with pytest.raises(error_type, match="exceeds .* byte size limit"):
        reader(path)


@pytest.mark.parametrize(("reader", "error_type"), LOCK_READERS)
def test_lock_readers_recheck_limit_if_file_grows_after_stat(
    reader, error_type, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _valid_lock_bytes()
    path = tmp_path / "uv.lock"
    path.write_bytes(payload)
    monkeypatch.setattr(evidence_verifier, "_MAX_LOCK_FILE_BYTES", len(payload))
    original_open = evidence_verifier._open_regular_file

    class GrowingStream:
        def __init__(self, stream):
            self._stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self._stream.close()

        def fileno(self):
            return self._stream.fileno()

        def read(self, size=-1):
            assert size == len(payload) + 1
            return payload + b"#"

    monkeypatch.setattr(
        evidence_verifier,
        "_open_regular_file",
        lambda candidate, label: GrowingStream(original_open(candidate, label)),
    )

    def fail_if_parsed(*_args, **_kwargs):
        pytest.fail("grown uv.lock must be rejected before TOML parsing")

    monkeypatch.setattr(reader.__globals__["tomllib"], "loads", fail_if_parsed)

    with pytest.raises(error_type, match="exceeds .* byte size limit"):
        reader(path)
