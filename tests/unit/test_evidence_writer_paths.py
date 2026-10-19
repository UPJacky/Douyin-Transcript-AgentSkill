from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from runpy import run_path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = str(ROOT / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import hash_locked_license_candidates as candidate_hash  # noqa: E402
import inventory_locked_artifact_members as artifact_inventory  # noqa: E402
import inventory_locked_pe_imports as pe_inventory  # noqa: E402
import map_locked_pe_import_edges as edge_map  # noqa: E402
from safe_output import SafeOutputError  # noqa: E402

numpy_inventory = run_path(str(ROOT / "scripts" / "inventory_numpy_native_members.py"))
metadata_audit = run_path(
    str(ROOT / "scripts" / "verify_locked_wheel_metadata_audit.py")
)
batched_inventory = run_path(
    str(ROOT / "scripts" / "inventory_locked_artifact_members_batched.py")
)


def _linked_directory(tmp_path: Path) -> tuple[Path, Path]:
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink creation is unavailable: {exc}")
    return linked, outside


def test_numpy_evidence_writer_replaces_files_and_rejects_linked_parents(
    tmp_path: Path,
) -> None:
    writer = numpy_inventory["_write_jsonl"]
    output = tmp_path / "numpy.jsonl"
    writer(output, [{"version": "first"}])
    writer(output, [{"version": "replacement"}])
    assert json.loads(output.read_text(encoding="utf-8")) == {"version": "replacement"}

    linked, outside = _linked_directory(tmp_path)
    with pytest.raises(numpy_inventory["InventoryError"], match="cannot write"):
        writer(linked / "numpy.jsonl", [{"version": "redirected"}])
    assert not (outside / "numpy.jsonl").exists()


def test_metadata_writer_keeps_existing_parent_and_atomic_replace_contract(
    tmp_path: Path,
) -> None:
    writer = metadata_audit["_write_evidence"]
    missing_parent_output = tmp_path / "missing" / "evidence.json"
    with pytest.raises(OSError):
        writer(missing_parent_output, {"version": 1})
    assert not missing_parent_output.parent.exists()

    output = tmp_path / "evidence.json"
    writer(output, {"version": 1})
    writer(output, {"version": 2})
    assert json.loads(output.read_text(encoding="utf-8")) == {"version": 2}

    linked, outside = _linked_directory(tmp_path)
    with pytest.raises(SafeOutputError, match="symbolic link or reparse point"):
        writer(linked / "evidence.json", {"version": 3})
    assert not (outside / "evidence.json").exists()


def test_candidate_hash_report_is_create_only_and_rejects_linked_parents(
    tmp_path: Path,
) -> None:
    writer = candidate_hash._write_candidate_report
    output = tmp_path / "hash-report.json"
    writer(output, b"first\n")
    with pytest.raises(candidate_hash.CandidateHashError, match="already exists"):
        writer(output, b"replacement\n")
    assert output.read_bytes() == b"first\n"

    missing_parent_output = tmp_path / "missing" / "hash-report.json"
    with pytest.raises(OSError):
        writer(missing_parent_output, b"new\n")
    assert not missing_parent_output.parent.exists()

    linked, outside = _linked_directory(tmp_path)
    with pytest.raises(SafeOutputError, match="symbolic link or reparse point"):
        writer(linked / "hash-report.json", b"redirected\n")
    assert not (outside / "hash-report.json").exists()


def test_artifact_inventory_atomic_writer_replaces_and_rejects_linked_parents(
    tmp_path: Path,
) -> None:
    output = tmp_path / "artifact.jsonl"
    artifact_inventory._atomic_write(output, "first\n")
    artifact_inventory._atomic_write(output, "replacement\n")
    assert output.read_text(encoding="utf-8") == "replacement\n"

    linked, outside = _linked_directory(tmp_path)
    with pytest.raises(SafeOutputError, match="symbolic link or reparse point"):
        artifact_inventory._atomic_write(linked / "artifact.jsonl", "redirected\n")
    assert not (outside / "artifact.jsonl").exists()


def test_batch_writers_are_create_only_and_reject_linked_parents(
    tmp_path: Path,
) -> None:
    writer = batched_inventory["_write_new_file"]
    output = tmp_path / "batch.md"
    writer(output, "first\n")
    with pytest.raises(
        batched_inventory["BatchInventoryError"], match="already exists"
    ):
        writer(output, "replacement\n")
    assert output.read_text(encoding="utf-8") == "first\n"

    linked, outside = _linked_directory(tmp_path)
    with pytest.raises(SafeOutputError, match="symbolic link or reparse point"):
        writer(linked / "batch.md", "redirected\n")
    with pytest.raises(SafeOutputError, match="symbolic link or reparse point"):
        batched_inventory["_write_jsonl_parts"](
            io.BytesIO(b'{"row":1}\n'), linked, "batch"
        )
    assert not (outside / "batch.md").exists()
    assert not (outside / "batch-part-001.jsonl").exists()


def test_batch_output_directory_must_not_be_a_symlink(tmp_path: Path) -> None:
    linked, _outside = _linked_directory(tmp_path)
    with pytest.raises(SafeOutputError, match="symbolic link or reparse point"):
        batched_inventory["validate_output_directory"](linked)


def test_pe_and_edge_map_outputs_use_shared_safe_helpers(tmp_path: Path) -> None:
    pe_path = tmp_path / "pe.jsonl"
    pe_inventory._write_jsonl(pe_path, [{"kind": "first"}])
    pe_inventory._write_jsonl(pe_path, [{"kind": "replacement"}])
    assert json.loads(pe_path.read_text(encoding="utf-8")) == {"kind": "replacement"}

    edge_path = tmp_path / "edges.jsonl"
    old_umask = None
    if os.name != "nt":
        old_umask = os.umask(0)
        os.umask(old_umask)
    edge_map._write_jsonl(edge_path, [{"kind": "first"}])
    if old_umask is not None:
        assert edge_path.stat().st_mode & 0o777 == 0o666 & ~old_umask
    with pytest.raises(edge_map.EdgeMapError, match="already exists"):
        edge_map._write_jsonl(edge_path, [{"kind": "replacement"}])
    assert json.loads(edge_path.read_text(encoding="utf-8")) == {"kind": "first"}
