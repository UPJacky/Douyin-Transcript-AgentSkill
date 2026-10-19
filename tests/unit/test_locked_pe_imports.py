from __future__ import annotations

import io
import hashlib
import json
import stat
import struct
import sys
import time
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = str(ROOT / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
import inventory_locked_pe_imports as pe_inventory  # noqa: E402
import map_locked_pe_import_edges as pe_edge_map  # noqa: E402


def _pe_fixture(*, pe32: bool = False) -> bytes:
    image = bytearray(0x400)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 0x80)
    image[0x80:0x84] = b"PE\0\0"
    coff = 0x84
    optional_size = 0xE0 if pe32 else 0xF0
    struct.pack_into(
        "<HHIIIHH", image, coff, 0x14C if pe32 else 0x8664, 1, 0, 0, 0, optional_size, 0
    )

    optional = coff + 20
    directory_count_offset = 92 if pe32 else 108
    directory_offset = 96 if pe32 else 112
    image[optional : optional + 2] = struct.pack("<H", 0x10B if pe32 else 0x20B)
    if pe32:
        struct.pack_into("<I", image, optional + 28, 0x400000)
    else:
        struct.pack_into("<Q", image, optional + 24, 0x140000000)
    struct.pack_into("<I", image, optional + 60, 0x200)
    struct.pack_into("<I", image, optional + directory_count_offset, 16)
    struct.pack_into("<II", image, optional + directory_offset + 8, 0x2000, 40)
    struct.pack_into("<II", image, optional + directory_offset + 13 * 8, 0x2040, 64)

    section_table = optional + optional_size
    image[section_table : section_table + 8] = b".rdata\0\0"
    struct.pack_into("<IIII", image, section_table + 8, 0x200, 0x2000, 0x200, 0x200)

    struct.pack_into("<IIIII", image, 0x200, 0x20A0, 0, 0, 0x20A0, 0)
    image[0x2A0 : 0x2A0 + len(b"KERNEL32.dll\0")] = b"KERNEL32.dll\0"
    delay_name = 0x400000 + 0x20C0 if pe32 else 0x20C0
    struct.pack_into("<II", image, 0x240, 0 if pe32 else 1, delay_name)
    image[0x2C0 : 0x2C0 + len(b"SHELL32.dll\0")] = b"SHELL32.dll\0"
    return bytes(image)


@pytest.mark.parametrize("pe32", [False, True])
def test_reads_normal_and_delay_import_names_for_both_pe_formats(pe32: bool) -> None:
    image = pe_inventory._PEImage(io.BytesIO(_pe_fixture(pe32=pe32)), 0x400)

    assert image.pe_format == ("PE32" if pe32 else "PE32+")
    assert image.machine == (0x14C if pe32 else 0x8664)
    assert image.imports() == [
        {"kind": "normal", "dll": "KERNEL32.dll"},
        {"kind": "delay", "dll": "SHELL32.dll"},
    ]


@pytest.mark.parametrize(
    ("offset", "data"),
    [
        (0, b"ZZ"),
        (0x3C, b"\xff\xff\xff\xff"),
    ],
)
def test_rejects_invalid_dos_or_nt_header_bounds(offset: int, data: bytes) -> None:
    malformed = bytearray(_pe_fixture())
    malformed[offset : offset + len(data)] = data

    with pytest.raises(pe_inventory.InventoryError):
        pe_inventory._PEImage(io.BytesIO(malformed), len(malformed))


def test_rejects_import_directory_without_bounded_terminator() -> None:
    malformed = bytearray(_pe_fixture())
    # The declared import directory contains only one non-null descriptor.
    optional = 0x84 + 20
    struct.pack_into("<II", malformed, optional + 112 + 8, 0x2000, 20)
    image = pe_inventory._PEImage(io.BytesIO(malformed), len(malformed))

    with pytest.raises(pe_inventory.InventoryError, match="terminator"):
        image.imports()


def test_accepts_import_directory_with_bounded_trailing_padding() -> None:
    padded = bytearray(_pe_fixture())
    optional = 0x84 + 20
    struct.pack_into("<II", padded, optional + 112 + 8, 0x2000, 41)

    image = pe_inventory._PEImage(io.BytesIO(padded), len(padded))

    assert image.imports() == [
        {"kind": "normal", "dll": "KERNEL32.dll"},
        {"kind": "delay", "dll": "SHELL32.dll"},
    ]


def test_rejects_rva_with_ambiguous_overlapping_sections() -> None:
    malformed = bytearray(_pe_fixture())
    optional = 0x84 + 20
    section_table = optional + 0xF0
    second = section_table + 40
    struct.pack_into("<H", malformed, 0x84 + 2, 2)
    malformed[second : second + 8] = b".extra\0\0"
    struct.pack_into("<IIII", malformed, second + 8, 0x200, 0x2000, 0x100, 0x300)
    image = pe_inventory._PEImage(io.BytesIO(malformed), len(malformed))

    with pytest.raises(pe_inventory.InventoryError, match="uniquely"):
        image.imports()


def test_locked_windows_wheels_include_all_packages_and_ignore_other_platforms(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "uv.lock"
    lock_path.write_text(
        """version = 1

[[package]]
name = "alpha"
version = "1.0"
wheels = [{ url = "https://example.invalid/alpha-1.0-py3-none-win_amd64.whl", hash = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", size = 10 }]

[[package]]
name = "beta"
version = "2.0"
wheels = [{ url = "https://example.invalid/beta-2.0-cp313-cp313-win_arm64.whl", hash = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", size = 20 }]

[[package]]
name = "gamma"
version = "3.0"
wheels = [{ url = "https://example.invalid/gamma-3.0-cp313-cp313-win32.whl", hash = "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd", size = 40 }]

[[package]]
name = "linux-only"
version = "3.0"
wheels = [{ url = "https://example.invalid/linux_only-3.0-py3-none-manylinux_2_17_x86_64.whl", hash = "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc", size = 30 }]
""",
        encoding="utf-8",
    )

    wheels, _ = pe_inventory._locked_windows_wheels(lock_path)

    assert [wheel.package for wheel in wheels] == ["alpha", "beta", "gamma"]
    assert pe_inventory._expected_machines(wheels[0].filename) == {0x8664}
    assert pe_inventory._expected_machines(wheels[1].filename) == {0xAA64, 0xA641}
    assert pe_inventory._expected_machines(wheels[2].filename) == {0x014C}


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("package/native.dll", True),
        ("package/worker.EXE", True),
        ("package/_native.pyd", True),
        ("package/README.txt", False),
    ],
)
def test_pe_candidate_suffixes_include_executable_and_extension_modules(
    path: str, expected: bool
) -> None:
    assert pe_inventory._is_pe_candidate(path) is expected


def test_maps_executable_imports_and_reports_machine_match_to_wheel_tag(
    tmp_path: Path,
) -> None:
    executable = _pe_fixture()
    member_hash = hashlib.sha256(executable).hexdigest()
    record = (
        f"app.exe,{pe_inventory._record_digest(member_hash)},{len(executable)}\n"
        "app-1.0.dist-info/RECORD,,\n"
    )
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
        executable_info = zipfile.ZipInfo("app.exe")
        executable_info.external_attr = (stat.S_IFREG | 0o644) << 16
        archive.writestr(executable_info, executable)
        record_info = zipfile.ZipInfo("app-1.0.dist-info/RECORD")
        record_info.external_attr = (stat.S_IFREG | 0o644) << 16
        archive.writestr(record_info, record)
    wheel_bytes = payload.getvalue()
    wheel_hash = hashlib.sha256(wheel_bytes).hexdigest()
    cache_path = tmp_path / wheel_hash
    cache_path.write_bytes(wheel_bytes)
    wheel = pe_inventory.Wheel(
        "app",
        "1.0",
        "https://example.invalid/app-1.0-py3-none-win_amd64.whl",
        wheel_hash,
        len(wheel_bytes),
    )

    rows = pe_inventory._pe_rows(
        wheel,
        "0" * 64,
        cache_path,
        time.monotonic() + 10,
    )

    assert len(rows) == 1
    assert rows[0]["member_path"] == "app.exe"
    assert rows[0]["record_verified"] is True
    assert rows[0]["machine_matches_wheel_platform"] is True
    assert rows[0]["imports"] == [
        {"kind": "normal", "dll": "KERNEL32.dll"},
        {"kind": "delay", "dll": "SHELL32.dll"},
    ]

    wrong_architecture = wheel.__class__(
        wheel.package,
        wheel.version,
        wheel.url.removesuffix("win_amd64.whl") + "win_arm64.whl",
        wheel.sha256,
        wheel.size,
    )
    mismatched_rows = pe_inventory._pe_rows(
        wrong_architecture,
        "0" * 64,
        cache_path,
        time.monotonic() + 10,
    )
    assert mismatched_rows[0]["machine_matches_wheel_platform"] is False


@pytest.mark.parametrize(
    ("record_entry", "expected_status"),
    [
        ("app.exe,,\n", "unhashed_in_record"),
        ("", "missing_from_record"),
    ],
)
def test_reports_pe_member_without_record_digest(
    tmp_path: Path, record_entry: str, expected_status: str
) -> None:
    executable = _pe_fixture()
    record = f"{record_entry}app-1.0.dist-info/RECORD,,\n"
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
        executable_info = zipfile.ZipInfo("app.exe")
        executable_info.external_attr = (stat.S_IFREG | 0o644) << 16
        archive.writestr(executable_info, executable)
        record_info = zipfile.ZipInfo("app-1.0.dist-info/RECORD")
        record_info.external_attr = (stat.S_IFREG | 0o644) << 16
        archive.writestr(record_info, record)
    wheel_bytes = payload.getvalue()
    wheel_hash = hashlib.sha256(wheel_bytes).hexdigest()
    cache_path = tmp_path / wheel_hash
    cache_path.write_bytes(wheel_bytes)
    wheel = pe_inventory.Wheel(
        "app",
        "1.0",
        "https://example.invalid/app-1.0-py3-none-win_amd64.whl",
        wheel_hash,
        len(wheel_bytes),
    )

    rows = pe_inventory._pe_rows(
        wheel,
        "0" * 64,
        cache_path,
        time.monotonic() + 10,
    )

    assert rows[0]["record_sha256"] is None
    assert rows[0]["record_verified"] is False
    assert rows[0]["record_status"] == expected_status


def test_record_rows_normalize_windows_backslash_member_paths() -> None:
    record = "pkg\\ruff.exe,sha256=abc,42\ndemo-1.0.dist-info\\RECORD,,\n"
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("demo-1.0.dist-info/RECORD", record)

    with zipfile.ZipFile(io.BytesIO(payload.getvalue())) as archive:
        rows = pe_inventory._record_rows(archive)

    assert rows["pkg/ruff.exe"] == ("sha256=abc", 42, "pkg\\ruff.exe")
    assert rows["demo-1.0.dist-info/RECORD"] == (
        "",
        -1,
        "demo-1.0.dist-info\\RECORD",
    )


def test_record_rows_rejects_rows_over_configured_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "demo-1.0.dist-info/RECORD",
            "first.py,,1\nsecond.py,,2\n",
        )

    monkeypatch.setattr(pe_inventory, "_MAX_RECORD_ROWS", 1)
    with zipfile.ZipFile(io.BytesIO(payload.getvalue())) as archive:
        with pytest.raises(
            pe_inventory.InventoryError, match="RECORD exceeds row limit"
        ):
            pe_inventory._record_rows(archive)


def test_record_rows_rejects_excess_columns_before_csv_row_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "demo-1.0.dist-info/RECORD",
            "first.py," + ("," * 1_000_000) + "\n",
        )

    def csv_reader_must_not_run(*args, **kwargs):
        raise AssertionError("csv.reader must not materialize an oversized row")

    monkeypatch.setattr(pe_inventory.csv, "reader", csv_reader_must_not_run)
    with zipfile.ZipFile(io.BytesIO(payload.getvalue())) as archive:
        with pytest.raises(
            pe_inventory.InventoryError, match="malformed wheel RECORD row"
        ):
            pe_inventory._record_rows(archive)


def _edge_row(
    artifact_sha256: str,
    member_path: str,
    imports: list[dict[str, str]],
    *,
    package: str = "example",
    platform: str = "win_amd64",
    machine: str = "0x8664",
    record_verified: bool = True,
) -> dict[str, object]:
    return {
        "artifact_sha256": artifact_sha256,
        "member_path": member_path,
        "member_sha256": hashlib.sha256(member_path.encode()).hexdigest(),
        "package": package,
        "version": "1.0",
        "wheel_filename": f"{package}-1.0-py3-none-{platform}.whl",
        "wheel_platform": platform,
        "pe_machine": machine,
        "machine_matches_wheel_platform": True,
        "record_status": "verified" if record_verified else "missing_from_record",
        "record_verified": record_verified,
        "imports": imports,
    }


def test_classifies_api_set_system_same_artifact_and_unresolved_imports() -> None:
    artifact = "a" * 64
    rows = [
        _edge_row(
            artifact,
            "pkg/consumer.pyd",
            [
                {"dll": "PROVIDER.DLL", "kind": "normal"},
                {"dll": "KERNEL32.dll", "kind": "normal"},
                {"dll": "API-MS-Win-Core-Synch-L1-2-0.DLL", "kind": "delay"},
                {"dll": "python311.dll", "kind": "normal"},
                {"dll": "vcruntime140.dll", "kind": "normal"},
            ],
        ),
        _edge_row(artifact, "pkg/provider.dll", []),
    ]

    edges, counts = pe_edge_map._map_edges(rows, "b" * 64, "c" * 64)

    assert counts["same_artifact_filename_candidate"] == 1
    assert counts["windows_system_dll_name"] == 1
    assert counts["windows_api_set_import"] == 1
    assert counts["unresolved_in_inventory"] == 2
    assert edges[0]["resolution"] == "same_artifact_filename_candidate"
    assert edges[0]["target_candidates"][0]["member_path"] == "pkg/provider.dll"
    assert edges[0]["target_candidates"][0]["candidate_scope"] == "same_artifact"
    assert edges[0]["format_version"] == 1
    assert edges[1]["resolution"] == "windows_system_dll_name"
    assert edges[1]["name_classification_basis"] == "explicit_system_dll_name_catalog"
    assert edges[2]["resolution"] == "windows_api_set_import"
    assert edges[2]["name_classification_basis"] == "api_set_name_prefix"
    assert edges[3]["resolution"] == "unresolved_in_inventory"
    assert edges[3]["resolution_reason"] == "no_matching_pe_member_in_inventory"
    assert edges[3]["target_candidates"] == []
    assert edges[4]["resolution"] == "unresolved_in_inventory"
    assert edges[4]["name_classification"] == "non_catalogued_name"


def test_maps_cross_artifact_candidates_only_for_verified_same_machine_members() -> (
    None
):
    rows = [
        _edge_row(
            "a" * 64,
            "consumer.pyd",
            [{"dll": "support.dll", "kind": "delay"}],
        ),
        _edge_row("b" * 64, "support.dll", [], package="support"),
    ]

    edges, counts = pe_edge_map._map_edges(rows, "e" * 64, "f" * 64)

    assert counts["cross_artifact_filename_candidate"] == 1
    assert edges[0]["candidate_resolution"] == "cross_artifact"
    assert edges[0]["target_candidates"][0]["candidate_scope"] == "cross_artifact"
    assert edges[0]["target_candidates"][0]["package"] == "support"
    assert edges[0]["target_candidates"][0]["lock_package_relation"] == (
        "different_package"
    )


def test_marks_same_and_cross_artifact_candidates_as_inventory_ambiguous() -> None:
    rows = [
        _edge_row(
            "a" * 64,
            "consumer.pyd",
            [{"dll": "shared.dll", "kind": "normal"}],
        ),
        _edge_row("a" * 64, "same/shared.dll", []),
        _edge_row("b" * 64, "cross/shared.dll", [], package="support"),
    ]

    edges, counts = pe_edge_map._map_edges(rows, "e" * 64, "f" * 64)

    assert counts["ambiguous_inventory_filename_candidates"] == 1
    assert counts["edges_with_same_artifact_candidates"] == 1
    assert counts["edges_with_cross_artifact_candidates"] == 1
    assert edges[0]["candidate_resolution"] == "ambiguous_inventory_candidates"
    assert {
        candidate["candidate_scope"] for candidate in edges[0]["target_candidates"]
    } == {
        "same_artifact",
        "cross_artifact",
    }


def test_marks_multiple_cross_artifact_candidates_ambiguous_and_arch_mismatch_unresolved() -> (
    None
):
    rows = [
        _edge_row(
            "a" * 64,
            "consumer.pyd",
            [
                {"dll": "shared.dll", "kind": "normal"},
                {"dll": "arm-only.dll", "kind": "normal"},
            ],
        ),
        _edge_row("b" * 64, "one/shared.dll", [], package="support_one"),
        _edge_row("c" * 64, "two/SHARED.DLL", [], package="support_two"),
        _edge_row(
            "d" * 64,
            "arm-only.dll",
            [],
            package="arm-support",
            platform="win_arm64",
            machine="0xaa64",
        ),
    ]

    edges, counts = pe_edge_map._map_edges(rows, "e" * 64, "f" * 64)

    assert counts["ambiguous_inventory_filename_candidates"] == 1
    assert edges[0]["resolution"] == "ambiguous_inventory_filename_candidates"
    assert edges[0]["candidate_resolution"] == "ambiguous_inventory_candidates"
    assert {item["package"] for item in edges[0]["target_candidates"]} == {
        "support_one",
        "support_two",
    }
    assert counts["unresolved_in_inventory"] == 1
    assert edges[1]["resolution"] == "unresolved_in_inventory"
    assert edges[1]["resolution_reason"] == (
        "matching_basename_candidates_failed_record_or_machine_gate"
    )
    assert edges[1]["target_candidates"] == []


def test_edge_map_stops_at_candidate_comparison_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        _edge_row(
            "a" * 64,
            "consumer.pyd",
            [{"dll": "support.dll", "kind": "normal"}],
        ),
        _edge_row("b" * 64, "one/support.dll", []),
        _edge_row("c" * 64, "two/support.dll", []),
    ]
    monkeypatch.setattr(pe_edge_map, "_MAX_CANDIDATE_COMPARISONS", 1)

    with pytest.raises(pe_edge_map.EdgeMapError, match="matching work exceeds"):
        pe_edge_map._map_edges(rows, "e" * 64, "f" * 64)


def test_edge_map_stops_before_materializing_excess_target_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        _edge_row(
            "a" * 64,
            "consumer.pyd",
            [{"dll": "support.dll", "kind": "normal"}],
        ),
        _edge_row("b" * 64, "support.dll", []),
    ]
    monkeypatch.setattr(pe_edge_map, "_MAX_TARGET_CANDIDATES", 0)

    with pytest.raises(pe_edge_map.EdgeMapError, match="target candidates exceed"):
        pe_edge_map._map_edges(rows, "e" * 64, "f" * 64)


def test_unverified_target_is_not_reported_as_a_candidate() -> None:
    rows = [
        _edge_row(
            "a" * 64,
            "consumer.pyd",
            [{"dll": "support.dll", "kind": "normal"}],
        ),
        _edge_row(
            "b" * 64,
            "support.dll",
            [],
            package="support",
            record_verified=False,
        ),
    ]

    edges, counts = pe_edge_map._map_edges(rows, "e" * 64, "f" * 64)

    assert counts["unresolved_in_inventory"] == 1
    assert edges[0]["resolution"] == "unresolved_in_inventory"
    assert edges[0]["target_candidates"] == []


def test_edge_map_writer_refuses_to_replace_existing_evidence(tmp_path: Path) -> None:
    output = tmp_path / "edges.jsonl"
    output.write_text("previous evidence\n", encoding="utf-8")

    with pytest.raises(pe_edge_map.EdgeMapError, match="already exists"):
        pe_edge_map._write_jsonl(output, [{"new": "evidence"}])

    assert output.read_text(encoding="utf-8") == "previous evidence\n"


def test_pe_inventory_writer_replaces_regular_output_and_rejects_linked_parent(
    tmp_path: Path,
) -> None:
    output = tmp_path / "imports.jsonl"
    pe_inventory._write_jsonl(output, [{"result": "first"}])
    pe_inventory._write_jsonl(output, [{"result": "replacement"}])
    assert json.loads(output.read_text(encoding="utf-8")) == {"result": "replacement"}

    outside = tmp_path / "outside"
    outside.mkdir()
    linked_parent = tmp_path / "linked"
    try:
        linked_parent.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink creation is unavailable: {exc}")

    with pytest.raises(pe_inventory.InventoryError, match="cannot write"):
        pe_inventory._write_jsonl(linked_parent / "imports.jsonl", [{"x": 1}])
    assert not (outside / "imports.jsonl").exists()


def test_edge_map_writer_rejects_linked_parent(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_parent = tmp_path / "linked"
    try:
        linked_parent.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink creation is unavailable: {exc}")

    with pytest.raises(pe_edge_map.EdgeMapError):
        pe_edge_map._write_jsonl(linked_parent / "edges.jsonl", [{"x": 1}])
    assert not (outside / "edges.jsonl").exists()


def test_preserves_repeated_normal_and_delay_import_occurrences() -> None:
    artifact = "a" * 64
    rows = [
        _edge_row(
            artifact,
            "consumer.pyd",
            [
                {"dll": "provider.dll", "kind": "normal"},
                {"dll": "provider.dll", "kind": "delay"},
            ],
        ),
        _edge_row(artifact, "provider.dll", []),
    ]

    edges, counts = pe_edge_map._map_edges(rows, "b" * 64, "c" * 64)

    assert len(edges) == 2
    assert counts["same_artifact_filename_candidate"] == 2
    assert [edge["import_index"] for edge in edges] == [0, 1]
    assert [edge["import_kind"] for edge in edges] == ["normal", "delay"]
    assert [edge["import_name"] for edge in edges] == ["provider.dll", "provider.dll"]
    assert edges[0]["source"]["record_status"] == "verified"
    assert edges[0]["target_candidates"][0]["machine_matches_wheel_platform"] is True
    assert all(edge["candidate_resolution"] == "same_artifact" for edge in edges)


def test_marks_duplicate_same_wheel_basenames_ambiguous() -> None:
    artifact = "a" * 64
    rows = [
        _edge_row(
            artifact,
            "consumer.pyd",
            [{"dll": "provider.dll", "kind": "normal"}],
        ),
        _edge_row(artifact, "one/provider.dll", []),
        _edge_row(artifact, "two/PROVIDER.DLL", []),
    ]

    edges, counts = pe_edge_map._map_edges(rows, "b" * 64, "c" * 64)

    assert counts["ambiguous_inventory_filename_candidates"] == 1
    assert edges[0]["resolution"] == "ambiguous_inventory_filename_candidates"
    assert [target["member_path"] for target in edges[0]["target_candidates"]] == [
        "one/provider.dll",
        "two/PROVIDER.DLL",
    ]


def test_load_inventory_binds_to_lock_and_rejects_duplicate_json_keys(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "uv.lock"
    lock_path.write_text(
        """version = 1

[[package]]
name = "example"
version = "1.0"
wheels = [{ url = "https://example.invalid/example-1.0-py3-none-win_amd64.whl", hash = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", size = 1 }]
""",
        encoding="utf-8",
    )
    lock_sha = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    row = {
        "artifact_sha256": "a" * 64,
        "member_sha256": "b" * 64,
        "member_path": "pkg/consumer.pyd",
        "lock_sha256": lock_sha,
        "wheel_platform": "win_amd64",
        "pe_machine": "0x8664",
        "package": "example",
        "version": "1.0",
        "wheel_filename": "example-1.0-py3-none-win_amd64.whl",
        "machine_matches_wheel_platform": True,
        "record_status": "missing_from_record",
        "record_verified": False,
        "imports": [],
    }
    inventory = tmp_path / "imports.jsonl"
    inventory.write_text(
        json.dumps(row, separators=(",", ":")) + "\n", encoding="utf-8"
    )

    rows, actual_lock_sha, inventory_sha = pe_edge_map._load_inventory(
        inventory, lock_path
    )

    assert rows[0]["member_path"] == "pkg/consumer.pyd"
    assert actual_lock_sha == lock_sha
    assert inventory_sha == hashlib.sha256(inventory.read_bytes()).hexdigest()

    tampered_row = {**row, "artifact_sha256": "d" * 64}
    inventory.write_text(
        json.dumps(tampered_row, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    with pytest.raises(pe_edge_map.EdgeMapError, match="not bound to a locked"):
        pe_edge_map._load_inventory(inventory, lock_path)

    inventory.write_text(
        '{"lock_sha256":"bad","lock_sha256":"bad"}\n', encoding="utf-8"
    )
    with pytest.raises(pe_edge_map.EdgeMapError, match="duplicate JSON"):
        pe_edge_map._load_inventory(inventory, lock_path)


def test_load_inventory_rejects_evidence_for_another_lockfile(tmp_path: Path) -> None:
    lock_path = tmp_path / "uv.lock"
    lock_path.write_text(
        """version = 1

[[package]]
name = "example"
version = "1.0"
wheels = [{ url = "https://example.invalid/example-1.0-py3-none-win_amd64.whl", hash = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", size = 1 }]
""",
        encoding="utf-8",
    )
    row = {
        "artifact_sha256": "a" * 64,
        "member_sha256": "b" * 64,
        "member_path": "pkg/consumer.pyd",
        "lock_sha256": "c" * 64,
        "wheel_platform": "win_amd64",
        "pe_machine": "0x8664",
        "package": "example",
        "version": "1.0",
        "wheel_filename": "example-1.0-py3-none-win_amd64.whl",
        "imports": [],
    }
    inventory = tmp_path / "imports.jsonl"
    inventory.write_text(
        json.dumps(row, separators=(",", ":")) + "\n", encoding="utf-8"
    )

    with pytest.raises(pe_edge_map.EdgeMapError, match="different lock"):
        pe_edge_map._load_inventory(inventory, lock_path)
