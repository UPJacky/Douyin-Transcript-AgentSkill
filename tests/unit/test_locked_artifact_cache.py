from __future__ import annotations

import hashlib
from pathlib import Path
from runpy import run_path

import pytest

ROOT = Path(__file__).resolve().parents[2]
verifier = run_path(str(ROOT / "scripts" / "verify_locked_artifact_cache.py"))
verify_cache = verifier["verify_cache"]
CacheVerificationError = verifier["CacheVerificationError"]


def _fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, bytes]]:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    contents = {
        b"locked wheel bytes": b"locked wheel bytes",
        b"locked sdist bytes": b"locked sdist bytes",
    }
    digests = {
        content: hashlib.sha256(content).hexdigest() for content in contents.values()
    }
    for content, digest in digests.items():
        (cache_dir / digest).write_bytes(content)
    wheel = b"locked wheel bytes"
    sdist = b"locked sdist bytes"
    lock_text = (
        'version = 1\n\n[[package]]\nname = "one"\nversion = "1"\n'
        f'sdist = {{ url = "https://files.pythonhosted.org/one.tar.gz", '
        f'hash = "sha256:{digests[sdist]}", size = {len(sdist)} }}\n'
        f'wheels = [{{ url = "https://files.pythonhosted.org/one.whl", '
        f'hash = "sha256:{digests[wheel]}", size = {len(wheel)} }}]\n\n'
        '[[package]]\nname = "two"\nversion = "1"\n'
        f'wheels = [{{ url = "https://files.pythonhosted.org/two.whl", '
        f'hash = "sha256:{digests[wheel]}", size = {len(wheel)} }}]\n'
    )
    lock_path = tmp_path / "uv.lock"
    lock_path.write_text(lock_text, encoding="utf-8")
    return (
        lock_path,
        cache_dir,
        {digest: content for content, digest in digests.items()},
    )


def test_verifies_every_unique_locked_artifact(tmp_path: Path) -> None:
    lock_path, cache_dir, contents = _fixture(tmp_path)

    summary = verify_cache(lock_path, cache_dir)

    assert summary.packages == 2
    assert summary.artifacts == 2
    assert summary.references == 3
    assert summary.total_bytes == sum(map(len, contents.values()))


def test_rejects_missing_or_tampered_artifact(tmp_path: Path) -> None:
    lock_path, cache_dir, contents = _fixture(tmp_path)
    first_digest = next(iter(contents))
    (cache_dir / first_digest).write_bytes(b"tampered")

    with pytest.raises(CacheVerificationError, match="size differs|bytes differ"):
        verify_cache(lock_path, cache_dir)


def test_rejects_non_https_lock_artifact_url(tmp_path: Path) -> None:
    lock_path, cache_dir, _contents = _fixture(tmp_path)
    lock_text = lock_path.read_text(encoding="utf-8").replace(
        "https://files.pythonhosted.org", "http://files.pythonhosted.org", 1
    )
    lock_path.write_text(lock_text, encoding="utf-8")

    with pytest.raises(CacheVerificationError, match="URL is missing or not HTTPS"):
        verify_cache(lock_path, cache_dir)


def test_cli_reports_lock_cache_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lock_path, cache_dir, _contents = _fixture(tmp_path)

    exit_code = verifier["main"](
        ["--lockfile", str(lock_path), "--cache-dir", str(cache_dir)]
    )

    assert exit_code == 0
    assert (
        "2 packages, 2 unique artifacts, 3 lock references" in capsys.readouterr().out
    )
