from __future__ import annotations

import base64
import csv
import hashlib
import io
import stat
import sys
import zipfile
from pathlib import Path
from runpy import run_path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
inventory = run_path(str(ROOT / "scripts" / "inventory_pyav_ffmpeg_build_config.py"))
build_inventory = inventory["build_inventory"]
InventoryError = inventory["InventoryError"]


def _wheel_bytes(
    index: int,
    *,
    corrupt_record: bool = False,
    native_as_symlink: bool = False,
    native_member_name: str | None = None,
) -> bytes:
    member_name = native_member_name or f"av.libs/avcodec-{index}.dll"
    member = (
        b"prefix noise\x00--prefix=/tmp/vendor --disable-programs "
        b"--enable-libx264 --enable-libx265\x00tail"
    )
    digest = base64.urlsafe_b64encode(hashlib.sha256(member).digest())
    record_digest = digest.rstrip(b"=").decode("ascii")
    if corrupt_record:
        record_digest = "0" * 43

    record_name = "av-15.1.0.dist-info/RECORD"
    record_file = io.StringIO(newline="")
    writer = csv.writer(record_file, lineterminator="\n")
    writer.writerow([member_name, f"sha256={record_digest}", str(len(member))])
    writer.writerow([record_name, "", ""])

    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if native_as_symlink:
            link = zipfile.ZipInfo(member_name)
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, member)
        else:
            archive.writestr(member_name, member)
        archive.writestr(record_name, record_file.getvalue().encode("utf-8"))
    return result.getvalue()


def _locked_cache(
    tmp_path: Path,
    *,
    corrupt_record_at: int | None = None,
    symlink_native_at: int | None = None,
    symlink_native_name: str | None = None,
) -> tuple[Path, Path]:
    lock = tmp_path / "uv.lock"
    cache = tmp_path / "cache"
    cache.mkdir()
    artifacts: list[tuple[str, str, int]] = []
    for index in range(14):
        filename = f"av-15.1.0-cp311-none-any-{index}.whl"
        wheel = _wheel_bytes(
            index,
            corrupt_record=index == corrupt_record_at,
            native_as_symlink=index == symlink_native_at,
            native_member_name=(
                symlink_native_name if index == symlink_native_at else None
            ),
        )
        digest = hashlib.sha256(wheel).hexdigest()
        (cache / digest).write_bytes(wheel)
        artifacts.append((filename, digest, len(wheel)))

    lines = [
        "[[package]]",
        'name = "av"',
        'version = "15.1.0"',
        'source = { registry = "https://pypi.org/simple" }',
        "wheels = [",
    ]
    for filename, digest, size in artifacts:
        lines.append(
            "  { "
            f'url = "https://files.pythonhosted.org/packages/{filename}", '
            f'hash = "sha256:{digest}", '
            f"size = {size} "
            "},"
        )
    lines.extend(
        [
            "]",
            "",
        ]
    )
    lock.write_text("\n".join(lines), encoding="utf-8")
    return lock, cache


def test_inventory_binds_native_configuration_to_locked_wheel_and_record(
    tmp_path: Path,
) -> None:
    lock, cache = _locked_cache(tmp_path)

    result = build_inventory(lock, cache)

    assert result["wheel_count"] == 14
    assert result["observed_configuration_member_count"] == 14
    for wheel in result["wheels"]:
        assert wheel["configuration_status"] == "observed"
        assert len(wheel["sha256"]) == 64
        assert wheel["native_configuration_member_count"] == 1
        member = wheel["configuration_members"][0]
        assert member["member_path"].startswith("av.libs/")
        assert member["record_sha256_and_size_verified"] is True
        assert "--enable-libx264" in member["configuration_string"]
        assert "--enable-libx265" in member["configuration_string"]


def test_inventory_rejects_configuration_member_record_mismatch(
    tmp_path: Path,
) -> None:
    lock, cache = _locked_cache(tmp_path, corrupt_record_at=4)

    with pytest.raises(InventoryError, match="RECORD"):
        build_inventory(lock, cache)


def test_inventory_rejects_native_symlink_members(tmp_path: Path) -> None:
    lock, cache = _locked_cache(tmp_path, symlink_native_at=2)

    with pytest.raises(InventoryError, match="not a regular file"):
        build_inventory(lock, cache)


def test_inventory_rejects_missing_locked_wheel_without_network_fallback(
    tmp_path: Path,
) -> None:
    lock, cache = _locked_cache(tmp_path)
    next(cache.iterdir()).unlink()

    with pytest.raises(InventoryError, match="cannot open locked wheel"):
        build_inventory(lock, cache)


def test_configuration_scanner_ignores_unrelated_prefix_and_missing_terminator() -> (
    None
):
    scanner = inventory["_configuration_strings"]

    assert scanner(b"--prefix=/tmp/vendor --enable-pic\x00") == []
    assert scanner(b"--prefix=/tmp/vendor --enable-libx264 --enable-libx265") == []


def test_cli_escapes_terminal_controls_in_archive_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lock, cache = _locked_cache(
        tmp_path,
        symlink_native_at=2,
        symlink_native_name="av.libs/\x1b[31mavcodec.dll",
    )

    assert (
        inventory["main"](
            [
                "--lockfile",
                str(lock),
                "--cache-dir",
                str(cache),
                "--output",
                str(tmp_path / "output.json"),
            ]
        )
        == 1
    )

    error = capsys.readouterr().err
    assert "\x1b" not in error
    assert r"\u001b" in error
