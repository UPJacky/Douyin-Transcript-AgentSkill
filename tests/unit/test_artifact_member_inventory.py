from __future__ import annotations

import hashlib
import io
import json
import stat
import sys
import tarfile
import textwrap
import time
import zipfile
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
scanner = run_path(str(ROOT / "scripts" / "inventory_locked_artifact_members.py"))
zip_members = scanner["_zip_members"]
atomic_write = scanner["_atomic_write"]
escape_cell = scanner["_escape_cell"]
lock_identities = scanner["_lock_identities"]
render_markdown = scanner["_render_markdown"]
build_inventory = scanner["build_inventory"]
InventoryError = scanner["InventoryError"]


def test_checked_regular_file_tolerates_path_descriptor_ctime_difference(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "locked-wheel.whl"
    path.write_bytes(b"wheel contents")
    original_lstat = Path.lstat

    def lstat_with_different_ctime(candidate: Path):
        info = original_lstat(candidate)
        if candidate != path:
            return info
        return SimpleNamespace(
            st_mode=info.st_mode,
            st_dev=info.st_dev,
            st_ino=info.st_ino,
            st_size=info.st_size,
            st_mtime_ns=info.st_mtime_ns,
            st_ctime_ns=info.st_ctime_ns + 1_000_000,
            st_file_attributes=getattr(info, "st_file_attributes", 0),
        )

    monkeypatch.setattr(Path, "lstat", lstat_with_different_ctime)
    stream, opened = scanner["_checked_regular_file"](path)

    with stream:
        assert opened.st_ino == original_lstat(path).st_ino
        assert stream.read() == b"wheel contents"


def _entry(name: str, mode: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = mode << 16
    return info


def test_zip_member_type_defaults_unspecified_unix_type_to_regular_file() -> None:
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr(_entry("LICENSE", 0o644), b"license")
        archive.writestr(
            _entry("regular/LICENSE", stat.S_IFREG | 0o644),
            b"regular",
        )
        archive.writestr(_entry("link/LICENSE", stat.S_IFLNK | 0o777), b"target")
        archive.writestr(_entry("fifo/LICENSE", stat.S_IFIFO | 0o644), b"other")
        directory = _entry("directory/", stat.S_IFDIR | 0o755)
        archive.writestr(directory, b"")

    members = list(
        zip_members(
            archive_bytes,
            deadline=time.monotonic() + 10,
            expanded_limit=1024,
        )
    )
    types = {member["path"]: member["type"] for member in members}

    assert types == {
        "LICENSE": "file",
        "regular/LICENSE": "file",
        "link/LICENSE": "symlink",
        "fifo/LICENSE": "other",
        "directory/": "directory",
    }


def test_atomic_write_does_not_overwrite_legacy_predictable_temp_file(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "inventory.jsonl"
    legacy_temp = tmp_path / "inventory.jsonl.tmp"
    legacy_temp.write_text("preserve this file", encoding="utf-8")

    atomic_write(destination, "new inventory\n")

    assert destination.read_text(encoding="utf-8") == "new inventory\n"
    assert legacy_temp.read_text(encoding="utf-8") == "preserve this file"


def test_atomic_write_does_not_follow_legacy_predictable_temp_symlink(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "inventory.jsonl"
    sentinel = tmp_path / "outside-sentinel.txt"
    legacy_temp = tmp_path / "inventory.jsonl.tmp"
    sentinel.write_text("preserve this file", encoding="utf-8")
    try:
        legacy_temp.symlink_to(sentinel)
    except OSError as exc:
        pytest.skip(f"filesystem does not permit symlink creation: {exc}")

    atomic_write(destination, "new inventory\n")

    assert destination.read_text(encoding="utf-8") == "new inventory\n"
    assert legacy_temp.is_symlink()
    assert sentinel.read_text(encoding="utf-8") == "preserve this file"


def test_atomic_write_replaces_regular_output_and_rejects_linked_parent(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "inventory.jsonl"
    atomic_write(destination, "first inventory\n")
    atomic_write(destination, "replacement inventory\n")
    assert destination.read_text(encoding="utf-8") == "replacement inventory\n"

    outside = tmp_path / "outside"
    outside.mkdir()
    linked_parent = tmp_path / "linked"
    try:
        linked_parent.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink creation is unavailable: {exc}")

    with pytest.raises(OSError, match="symbolic link or reparse point"):
        atomic_write(linked_parent / "inventory.jsonl", "redirected\n")
    assert not (outside / "inventory.jsonl").exists()


@pytest.mark.parametrize("control", ["\r", "\n", "\t", "\x1b", "\x85", "\x9f"])
def test_markdown_cell_encodes_unicode_control_characters(control: str) -> None:
    encoded = escape_cell(f"before{control}after")

    assert control not in encoded
    assert encoded == f"before&#{ord(control)};after"


def test_markdown_report_control_characters_cannot_create_rows_or_cells() -> None:
    summary = {
        "lockfile_sha256": "a" * 64,
        "cache_artifact_count": 1,
        "lock_unique_artifact_identities": 1,
        "cache_compressed_bytes": 10,
        "expanded_bytes_walked": 10,
        "archive_member_records": 1,
        "candidate_member_counts_by_flag": {},
        "artifacts": [
            {
                "lock_identities": [
                    {
                        "package": "demo",
                        "version": "1.0",
                        "artifact_type": "wheel",
                        "url": "https://example.test/demo.whl\r# forged heading\n| forged cell\tend",
                        "filename": "demo.whl",
                    }
                ],
                "sha256": "b" * 64,
                "cached_size": 10,
                "member_count": 1,
                "candidate_member_count": 0,
            }
        ],
    }

    report = render_markdown(summary)
    row = next(
        line for line in report.splitlines() if "https://example.test/demo.whl" in line
    )

    assert row.count("|") == 9
    assert "&#13;# forged heading&#10;&#124; forged cell&#9;end" in row
    assert "forged heading" not in report.splitlines()


def test_inventory_outputs_visibly_escape_bidi_controls_in_labels_and_member_names(
    tmp_path: Path,
) -> None:
    batch_scanner = run_path(
        str(ROOT / "scripts" / "inventory_locked_artifact_members_batched.py")
    )
    bidi_controls = (
        "\u202a",
        "\u202b",
        "\u202c",
        "\u202d",
        "\u202e",
        "\u2066",
        "\u2067",
        "\u2068",
        "\u2069",
    )
    package_name = "demo" + "".join(bidi_controls)
    member_path = "members/" + "".join(bidi_controls) + "NOTICE.txt"
    literal_escape_path = (
        "members/"
        + "".join(f"\\u{ord(control):04x}" for control in bidi_controls)
        + "NOTICE.txt"
    )
    archive_buffer = io.BytesIO()
    with tarfile.open(fileobj=archive_buffer, mode="w:gz") as archive:
        for path, body in (
            (member_path, b"member data"),
            (literal_escape_path, b"literal escape text"),
        ):
            member = tarfile.TarInfo(name=path)
            member.size = len(body)
            archive.addfile(member, io.BytesIO(body))
    artifact_bytes = archive_buffer.getvalue()
    artifact_digest = hashlib.sha256(artifact_bytes).hexdigest()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / artifact_digest).write_bytes(artifact_bytes)
    artifact_url = "https://files.example/demo-1.0.tar.gz"
    lockfile = tmp_path / "uv.lock"
    lockfile.write_text(
        "[[package]]\n"
        f'name = "{package_name}"\nversion = "1.0"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
        f'sdist = {{ url = "{artifact_url}", hash = "sha256:{artifact_digest}", size = {len(artifact_bytes)} }}\n',
        encoding="utf-8",
    )

    markdown, jsonl = build_inventory(lockfile, cache_dir)
    rows = [json.loads(line) for line in jsonl.splitlines()]
    assert len(rows) == 2
    assert all(row["artifact_sha256"] == artifact_digest for row in rows)
    assert (
        hashlib.sha256((cache_dir / artifact_digest).read_bytes()).hexdigest()
        == artifact_digest
    )
    assert all(control not in markdown for control in bidi_controls)
    displayed_paths = {row["member_path"] for row in rows}
    assert len(displayed_paths) == 2
    assert all(
        control not in row["member_path"] for row in rows for control in bidi_controls
    )
    assert all(f"\\u{ord(control):04x}" in markdown for control in bidi_controls)
    assert displayed_paths == {
        "members/"
        + "".join(f"\\u{ord(control):04x}" for control in bidi_controls)
        + "NOTICE.txt",
        "members/"
        + "".join(f"\\\\u{ord(control):04x}" for control in bidi_controls)
        + "NOTICE.txt",
    }
    assert all(
        all(f"\\u{ord(control):04x}" in path for control in bidi_controls)
        for path in displayed_paths
    )

    output_dir = tmp_path / "batch-output"
    output_dir.mkdir()
    spool = io.BytesIO(jsonl.encode("utf-8"))
    parts = batch_scanner["_write_jsonl_parts"](spool, output_dir, "bidi")
    batch_rows = [
        json.loads(line)
        for part in parts
        for line in (output_dir / part["path"]).read_text(encoding="utf-8").splitlines()
    ]
    batch_report = batch_scanner["_render_report"](
        lock_digest="a" * 64,
        expected_artifacts=1,
        results=[
            {
                "sha256": artifact_digest,
                "status": "scanned",
                "compressed_bytes": len(artifact_bytes),
                "member_rows": 1,
                "candidate_member_rows": 0,
                "candidate_counts": {},
                "expanded_bytes_walked": len(artifact_bytes),
                "lock_identities": [
                    {
                        "package": package_name,
                        "version": "1.0",
                        "artifact_type": "wheel",
                        "filename": "demo-1.0-py3-none-any.whl",
                        "url": artifact_url,
                    }
                ],
            }
        ],
        expanded_budget=1024,
        expanded_total=len(artifact_bytes),
        elapsed_seconds=0.1,
        parts=parts,
    )
    assert all(control not in batch_report for control in bidi_controls)
    assert {row["member_path"] for row in batch_rows} == displayed_paths
    assert all(f"\\u{ord(control):04x}" in batch_report for control in bidi_controls)
    assert all(
        control not in row["member_path"]
        for row in batch_rows
        for control in bidi_controls
    )


@pytest.mark.parametrize("escaped_control", [r"\r", r"\n", r"\t", r"\u0085"])
def test_lock_urls_with_control_characters_are_rejected(
    tmp_path: Path, escaped_control: str
) -> None:
    lockfile = tmp_path / "uv.lock"
    lockfile.write_text(
        textwrap.dedent(
            f"""\
            version = 1

            [[package]]
            name = "demo"
            version = "1.0"
            wheels = [{{ url = "https://example.test/demo.whl{escaped_control}", hash = "sha256:{"a" * 64}", size = 10 }}]
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(InventoryError, match="URL contains a control character"):
        lock_identities(lockfile)
