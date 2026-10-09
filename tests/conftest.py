"""Choose a private Windows pytest root when the system temp ACL is shared."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def pytest_configure(config) -> None:
    if os.name != "nt" or config.option.basetemp is not None:
        return

    from douyin_transcript.storage_security import _inspect_windows_ancestor_path

    profile = Path.home()
    if _inspect_windows_ancestor_path(profile).status != "private":
        return
    temporary_root = tempfile.TemporaryDirectory(
        prefix="douyin-transcript-pytest-", dir=profile
    )
    config.option.basetemp = temporary_root.name
    config._douyin_transcript_test_temp = temporary_root


def pytest_unconfigure(config) -> None:
    temporary_root = getattr(config, "_douyin_transcript_test_temp", None)
    if temporary_root is not None:
        temporary_root.cleanup()
