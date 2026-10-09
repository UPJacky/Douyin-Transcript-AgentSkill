"""Structured run summaries that never include transcript bodies."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .text_safety import strip_display_controls


@dataclass(frozen=True, slots=True)
class ItemResult:
    status: str
    title: str | None = None
    video_id: str | None = None
    output_path: str | None = None
    error_code: str | None = None
    hint: str | None = None
    duration_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        if result["title"] is not None:
            result["title"] = strip_display_controls(result["title"])
        return result


@dataclass(frozen=True, slots=True)
class RunSummary:
    status: str
    items: tuple[ItemResult, ...]
    output_dir: str

    def to_dict(self) -> dict[str, Any]:
        counts = {
            state: sum(item.status == state for item in self.items)
            for state in ("success", "skipped", "failed")
        }
        return {
            "status": self.status,
            "total": len(self.items),
            **counts,
            "output_dir": self.output_dir,
            "items": [item.to_dict() for item in self.items],
        }


def make_summary(items: list[ItemResult], output_dir: Path | str) -> RunSummary:
    failed = sum(item.status == "failed" for item in items)
    succeeded = sum(item.status in {"success", "skipped"} for item in items)
    if failed == 0:
        status = "success"
    elif succeeded:
        status = "partial"
    else:
        status = "failed"
    return RunSummary(
        status, tuple(items), str(Path(output_dir).expanduser().resolve(strict=False))
    )


def exit_code_for_summary(summary: RunSummary) -> int:
    if summary.status == "success":
        return 0
    if summary.status == "partial":
        return 4
    return 5


def json_summary(summary: RunSummary) -> str:
    """Return an ASCII-safe JSON document for predictable subprocess output."""
    return json.dumps(summary.to_dict(), ensure_ascii=True, separators=(",", ":"))
