"""Durable SQLite task state for transcript jobs.

The store deliberately keeps only canonical source URLs. Query strings and
fragments are discarded because they may contain expiring signatures or
tracking tokens. Request headers are not part of this module's API.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import stat
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

from .markdown import MAX_FRONTMATTER_CHARACTERS
from .storage_security import (
    PrivateStorageError,
    create_private_file,
    ensure_private_directory,
    inspect_private_path,
)
from .text_safety import strip_display_controls

TaskState = str
MediaValidator = Callable[[Path], bool]

_SCHEMA_VERSION = 8
DEFAULT_STALE_AFTER_SECONDS = 300.0
_VALID_STATES = {
    "pending",
    "resolving",
    "downloading",
    "downloaded",
    "transcribing",
    "writing",
    "completed",
    "failed",
}
_TRANSITIONS = {
    "pending": {"resolving"},
    "resolving": {"downloading", "downloaded"},
    "downloading": {"downloaded"},
    "downloaded": {"transcribing"},
    "transcribing": {"writing"},
    "writing": set(),
    "completed": set(),
    "failed": set(),
}
_SENSITIVE_HEADER = re.compile(
    r"(?i)\b(authorization|proxy-authorization|cookie|set-cookie|"
    r"x-[a-z0-9_-]*(?:token|key|secret))\s*[:=]\s*[^\r\n]+"
)
_URL_IN_TEXT = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_SENSITIVE_QUERY_VALUE = re.compile(
    r"(?i)([?&](?:signature|sig|token|access_token|auth|key|secret|expires?|"
    r"x-amz-[a-z0-9-]+)=)[^&\s]+"
)
_ERROR_CODE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_UNSET = object()
_PROCESSING_OPTION_KEYS = {
    "schema_version",
    "language",
    "timestamps",
    "max_processing_seconds",
    "max_media_duration_seconds",
    "max_output_segments",
    "max_output_characters",
    "max_downloads",
    "retries",
    "correction_rules_enabled",
    "correction_rules",
    "output_dir",
}
@dataclass(frozen=True)
class Task:
    task_id: str
    source_url: str
    video_id: str | None
    title: str | None
    state: TaskState
    profile: str
    media_path: str | None
    output_path: str | None
    output_sha256: str | None
    timeline_path: str | None
    timeline_sha256: str | None
    timeline_required: bool
    error_code: str | None
    error_message: str | None
    attempt_count: int
    created_at: str
    updated_at: str
    completed_at: str | None
    claimed_by: str | None
    claimed_at: str | None
    claim_generation: int
    local_path: str | None
    content_hash: str | None
    processing_options_json: str
    source_duration_seconds: float | None


@dataclass(frozen=True)
class RecoveryResult:
    task_id: str
    from_state: str
    to_state: str
    reason: str


def canonicalize_source_url(source_url: str) -> str:
    """Return a credential-free URL without query parameters or fragments."""
    if not isinstance(source_url, str) or not source_url.strip():
        raise ValueError("source_url must be a non-empty HTTP(S) URL")
    try:
        parsed = urlsplit(source_url.strip())
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("source_url is malformed") from exc
    if scheme not in {"http", "https"} or not hostname:
        raise ValueError("source_url must be an absolute HTTP(S) URL")

    host = hostname.lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    default_port = 80 if scheme == "http" else 443
    authority = host if port is None or port == default_port else f"{host}:{port}"
    path = parsed.path or "/"
    # Credentials, query strings, and fragments are intentionally never stored.
    return urlunsplit((scheme, authority, path, "", ""))


def _local_source_marker(path: Path) -> str:
    """Stable frontmatter value for associating a local transcript with input."""
    return "local:" + quote(path.as_posix(), safe="/:._-~")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _serialize_processing_options(options: dict[str, object] | None) -> str:
    """Serialize a bounded, caller-supplied options snapshot (never task output)."""
    if options is None:
        return "{}"
    if not isinstance(options, dict):
        raise TypeError("processing_options must be a dict")
    if set(options) - _PROCESSING_OPTION_KEYS:
        raise ValueError("processing_options contains unsupported fields")
    rules = options.get("correction_rules", [])
    if not isinstance(rules, list) or any(
        not isinstance(rule, dict)
        or set(rule) - {"rule_id", "source", "replacement", "note"}
        for rule in rules
    ):
        raise ValueError("processing_options contains invalid correction rules")
    try:
        serialized = json.dumps(
            options, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("processing_options must contain JSON-compatible values") from exc
    if len(serialized.encode("utf-8")) > 512 * 1024:
        raise ValueError("processing_options exceeds 512 KiB")
    return serialized


def _path_is_complete_file(path: Path) -> bool:
    try:
        return path.is_file() and path.suffix.lower() != ".part" and path.stat().st_size > 0
    except OSError:
        return False


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sanitize_error_message(message: str | None) -> str | None:
    if message is None:
        return None
    sanitized = _SENSITIVE_HEADER.sub(lambda match: f"{match.group(1)}: [REDACTED]", str(message))

    def redact_url(match: re.Match[str]) -> str:
        raw_url = match.group(0)
        punctuation = ".,;:!)]}"
        suffix = raw_url[len(raw_url.rstrip(punctuation)) :]
        try:
            return canonicalize_source_url(raw_url.rstrip(punctuation)) + suffix
        except ValueError:
            return "[REDACTED_URL]" + suffix

    sanitized = _URL_IN_TEXT.sub(redact_url, sanitized)
    sanitized = _SENSITIVE_QUERY_VALUE.sub(r"\1[REDACTED]", sanitized)
    return sanitized[:1000]


def _require_claim_owner(
    task: Task,
    worker_id: str | None,
    claim_generation: int | None,
) -> None:
    """Reject worker writes after a claim is released or superseded."""
    if worker_id is None:
        if task.claimed_by is not None:
            raise RuntimeError("task is claimed by another worker")
    elif task.claimed_by != worker_id:
        raise RuntimeError("worker no longer owns the task claim")
    elif claim_generation is None:
        raise ValueError("claim_generation is required for worker writes")
    if claim_generation is not None:
        if (
            isinstance(claim_generation, bool)
            or not isinstance(claim_generation, int)
            or claim_generation < 0
        ):
            raise ValueError("claim_generation must be a non-negative integer")
        if task.claim_generation != claim_generation:
            raise RuntimeError("task claim generation has changed")
    elif worker_id is not None and task.claimed_by is None:
        # Preserve the optional generation parameter for administrative callers,
        # while never allowing an identified worker to write an unclaimed row.
        raise RuntimeError("worker no longer owns the task claim")


def _frontmatter(path: Path) -> dict[str, str] | None:
    """Read simple scalar frontmatter fields without importing a YAML parser."""
    try:
        with path.open("r", encoding="utf-8") as transcript:
            first_line = transcript.readline(MAX_FRONTMATTER_CHARACTERS + 1)
            if len(first_line) > MAX_FRONTMATTER_CHARACTERS or not first_line.startswith(
                "---\n"
            ):
                return None
            fields: dict[str, str] = {}
            characters_read = len(first_line)
            while characters_read < MAX_FRONTMATTER_CHARACTERS:
                line = transcript.readline(
                    MAX_FRONTMATTER_CHARACTERS - characters_read + 1
                )
                if not line:
                    return None
                characters_read += len(line)
                if characters_read > MAX_FRONTMATTER_CHARACTERS:
                    return None
                if line.strip() == "---":
                    return fields
                match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*?)\s*$", line)
                if not match:
                    continue
                value = match.group(2)
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                    value = value[1:-1]
                fields[match.group(1)] = value
    except (OSError, UnicodeError):
        return None
    return None


def _output_associated_with_task(path: Path, task: Task) -> bool:
    if not _path_is_complete_file(path):
        return False
    fields = _frontmatter(path)
    if fields is None:
        return False
    if task.video_id is not None:
        return fields.get("video_id") == task.video_id
    expected_source = task.source_url
    # A local transcript can use the persisted local source marker, or include
    # the task ID as a stronger association key.
    return fields.get("source_url") == expected_source or fields.get("task_id") == task.task_id


def _output_matches_task(path: Path, task: Task) -> bool:
    """Verify association and the private digest recorded for the output."""
    if not task.output_sha256 or not task.output_path:
        return False
    try:
        expected_path = os.path.normcase(
            str(Path(task.output_path).expanduser().resolve(strict=False))
        )
        actual_path = os.path.normcase(str(path.expanduser().resolve(strict=False)))
        return (
            actual_path == expected_path
            and _output_associated_with_task(path, task)
            and _sha256_file(path) == task.output_sha256
        )
    except OSError:
        return False


def _timeline_matches_task(path: Path, task: Task) -> bool:
    """Verify the optional timeline sidecar against its private attempt binding."""
    if not task.timeline_required:
        return task.timeline_path is None and task.timeline_sha256 is None
    if not task.output_path or not task.timeline_path or not task.timeline_sha256:
        return False
    if not re.fullmatch(r"[0-9a-f]{64}", task.timeline_sha256):
        return False
    try:
        output_path = Path(task.output_path).expanduser().resolve(strict=False)
        expected_path = _lexical_absolute_path(Path(task.timeline_path))
        actual_path = _lexical_absolute_path(path)
        expected_base = f"{output_path.stem}_timeline"
        same_parent = os.path.normcase(str(actual_path.parent)) == os.path.normcase(
            str(output_path.parent)
        )
        if actual_path != expected_path or not same_parent:
            return False
        if not re.fullmatch(
            re.escape(expected_base) + r"(?:__(?:[2-9]|[1-9][0-9]{1,3}))?\.md",
            actual_path.name,
        ):
            return False
        metadata = actual_path.lstat()
        return (
            stat.S_ISREG(metadata.st_mode)
            and metadata.st_size > 0
            and actual_path.suffix.lower() != ".part"
            and _sha256_file(actual_path) == task.timeline_sha256
        )
    except OSError:
        return False


def _lexical_absolute_path(path: Path) -> Path:
    """Normalize an absolute path without resolving its final symlink/reparse point."""
    return Path(os.path.abspath(path.expanduser()))


def _storage_path_identity(value: str | os.PathLike[str]) -> str:
    """Return a stable comparison key for paths persisted in task rows."""
    path = Path(value).expanduser()
    try:
        normalized = path.resolve(strict=False)
    except (OSError, RuntimeError):
        normalized = Path(os.path.abspath(path))
    return os.path.normcase(str(normalized))


def _task_outputs_match(task: Task) -> bool:
    if not task.output_path or not _output_matches_task(Path(task.output_path), task):
        return False
    if not task.timeline_required:
        return _timeline_matches_task(Path(""), task)
    return bool(task.timeline_path and _timeline_matches_task(Path(task.timeline_path), task))


class TaskStore:
    """SQLite-backed task state with atomic claims and crash recovery.

    Use a separate instance for each process. ``BEGIN IMMEDIATE`` serializes
    claims across those connections; a claim remains held until completion,
    failure, or stale-claim recovery.
    """

    def __init__(self, db_path: str | os.PathLike[str], *, busy_timeout_ms: int = 5000):
        in_memory = str(db_path) == ":memory:"
        self.db_path = Path(db_path).expanduser()
        if not in_memory:
            # Keep the caller's lexical path until the storage policy has a
            # chance to reject symlink/reparse aliases and `..` components.
            protected_parent = ensure_private_directory(self.db_path.parent)
            self.db_path = protected_parent / self.db_path.name
            database_existed = self.db_path.exists()
            if database_existed:
                if not self.db_path.is_file():
                    raise PrivateStorageError(f"任务数据库路径不是普通文件：{self.db_path}")
                report = inspect_private_path(self.db_path)
                if report.status != "private":
                    raise PrivateStorageError(
                        f"已有任务数据库权限不私有：{self.db_path}（{report.detail}）。"
                        "程序不会更改已有权限；请先备份后由你自行调整权限，或改用新的数据目录。"
                    )
            elif not create_private_file(self.db_path):
                report = inspect_private_path(self.db_path)
                if report.status != "private":
                    raise PrivateStorageError(
                        f"并发创建的任务数据库权限不私有：{self.db_path} "
                        f"（{report.detail}）。程序不会更改已有权限。"
                    )
            # SQLite creates and removes WAL/SHM files while other connections
            # may open this database. The parent directory is private and new
            # entries inherit its platform protections; checking a sidecar by
            # pathname here races normal checkpoint/removal operations.
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            ":memory:" if in_memory else str(self.db_path),
            timeout=max(0, busy_timeout_ms) / 1000,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(f"PRAGMA busy_timeout = {max(0, int(busy_timeout_ms))}")
        self._connection.execute("PRAGMA foreign_keys = ON")
        try:
            if not in_memory:
                self._enable_wal(busy_timeout_ms)
                self._connection.execute("PRAGMA synchronous = FULL")
            self._migrate()
        except BaseException:
            self._connection.close()
            raise

    def __enter__(self) -> TaskStore:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _enable_wal(self, busy_timeout_ms: int) -> None:
        """Set persistent WAL mode, retrying concurrent first-open races."""
        deadline = time.monotonic() + max(0, busy_timeout_ms) / 1000
        while True:
            try:
                self._connection.execute("PRAGMA journal_mode = WAL")
                return
            except sqlite3.OperationalError as exc:
                message = str(exc).casefold()
                error_code = getattr(exc, "sqlite_errorcode", None)
                primary_code = error_code & 0xFF if isinstance(error_code, int) else None
                transient = primary_code in {
                    sqlite3.SQLITE_BUSY,
                    sqlite3.SQLITE_LOCKED,
                    sqlite3.SQLITE_PROTOCOL,
                } or any(token in message for token in ("locked", "busy", "locking protocol"))
                if not transient or time.monotonic() >= deadline:
                    raise
                time.sleep(0.01)

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    @contextmanager
    def cache_entry_cleanup_guard(
        self, cache_path: str | os.PathLike[str], video_id: str
    ) -> Iterator[bool]:
        """Coordinate one cache-file deletion with claims and task updates.

        The caller must keep the context to one identity-checked unlink. It
        yields whether the cache path is currently referenced by an unfinished
        task, a live download, or any local-input task.
        """
        clean_video_id = str(video_id).strip()
        if re.fullmatch(r"[0-9]{1,32}", clean_video_id) is None:
            raise ValueError("video_id must contain 1 to 32 decimal digits")
        resolved_path = Path(cache_path).expanduser().resolve(strict=False)
        normalized_path = os.path.normcase(str(resolved_path))
        with self._lock, self._transaction():
            protected = False
            rows = self._connection.execute(
                """SELECT state, claimed_by, media_path FROM tasks
                   WHERE video_id = ?""",
                (clean_video_id,),
            ).fetchall()
            for row in rows:
                media_path = row["media_path"]
                if (
                    row["state"] != "completed"
                    and media_path
                    and _storage_path_identity(media_path) == normalized_path
                ) or (row["state"] == "downloading" and row["claimed_by"]):
                    protected = True
                    break

            if not protected:
                local_path_text = str(resolved_path)
                protected = self._connection.execute(
                    "SELECT 1 FROM tasks WHERE local_path = ? LIMIT 1",
                    (local_path_text,),
                ).fetchone() is not None
                if not protected and os.name == "nt":
                    # Path.resolve() usually gives the same spelling as the
                    # stored path. Compare normalized values as a fallback for
                    # Windows case aliases without making every cleanup scan
                    # all local tasks on the common exact-match path.
                    local_rows = self._connection.execute(
                        "SELECT local_path FROM tasks WHERE local_path IS NOT NULL"
                    ).fetchall()
                    protected = any(
                        _storage_path_identity(row["local_path"]) == normalized_path
                        for row in local_rows
                    )
            yield protected

    def _migrate(self) -> None:
        with self._lock, self._transaction():
            version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
            if version > _SCHEMA_VERSION:
                raise RuntimeError(
                    f"task database schema {version} is newer than supported {_SCHEMA_VERSION}"
                )
            if version < 1:
                self._connection.execute(
                    """CREATE TABLE IF NOT EXISTS tasks (
                        task_id TEXT PRIMARY KEY,
                        source_url TEXT NOT NULL,
                        video_id TEXT,
                        title TEXT,
                        state TEXT NOT NULL,
                        profile TEXT NOT NULL,
                        media_path TEXT,
                        output_path TEXT,
                        output_sha256 TEXT,
                        error_code TEXT,
                        error_message TEXT,
                        attempt_count INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        completed_at TEXT
                    )"""
                )
                version = 1
            if version < 2:
                columns = {
                    row[1]
                    for row in self._connection.execute("PRAGMA table_info(tasks)").fetchall()
                }
                for name, declaration in (
                    ("claimed_by", "TEXT"),
                    ("claimed_at", "TEXT"),
                    ("local_path", "TEXT"),
                    ("content_hash", "TEXT"),
                ):
                    if name not in columns:
                        self._connection.execute(
                            f"ALTER TABLE tasks ADD COLUMN {name} {declaration}"
                        )
                self._connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tasks_state_created ON tasks(state, created_at)"
                )
                version = 2
            if version < 3:
                columns = {
                    row[1]
                    for row in self._connection.execute("PRAGMA table_info(tasks)").fetchall()
                }
                if "processing_options_json" not in columns:
                    self._connection.execute(
                        "ALTER TABLE tasks ADD COLUMN processing_options_json "
                        "TEXT NOT NULL DEFAULT '{}'"
                    )
                version = 3
            if version < 4:
                columns = {
                    row[1]
                    for row in self._connection.execute("PRAGMA table_info(tasks)").fetchall()
                }
                if "source_duration_seconds" not in columns:
                    self._connection.execute(
                        "ALTER TABLE tasks ADD COLUMN source_duration_seconds REAL"
                    )
                version = 4
            if version < 5:
                columns = {
                    row[1]
                    for row in self._connection.execute("PRAGMA table_info(tasks)").fetchall()
                }
                if "output_sha256" not in columns:
                    self._connection.execute(
                        "ALTER TABLE tasks ADD COLUMN output_sha256 TEXT"
                    )
                version = 5
            if version < 6:
                columns = {
                    row[1]
                    for row in self._connection.execute("PRAGMA table_info(tasks)").fetchall()
                }
                for name, declaration in (
                    ("timeline_path", "TEXT"),
                    ("timeline_sha256", "TEXT"),
                    ("timeline_required", "INTEGER NOT NULL DEFAULT 0"),
                ):
                    if name not in columns:
                        self._connection.execute(
                            f"ALTER TABLE tasks ADD COLUMN {name} {declaration}"
                        )
                # Old attempts requested timestamps but have no private sidecar
                # binding. Do not keep treating those completed records as valid.
                rows = self._connection.execute(
                    "SELECT task_id, state, processing_options_json FROM tasks"
                ).fetchall()
                for row in rows:
                    try:
                        options = json.loads(row["processing_options_json"])
                    except (json.JSONDecodeError, TypeError):
                        options = None
                    timestamps = (
                        options.get("timestamps")
                        if isinstance(options, dict)
                        else None
                    )
                    # Preserve the explicit no-sidecar case. For completed or
                    # interrupted writing rows with missing/invalid legacy
                    # options, fail closed because an unbound sidecar may exist.
                    requires_timeline = timestamps is True or (
                        timestamps is not False and row["state"] in {"completed", "writing"}
                    )
                    if requires_timeline:
                        self._connection.execute(
                            "UPDATE tasks SET timeline_required = 1 WHERE task_id = ?",
                            (row["task_id"],),
                        )
                version = 6
            if version < 7:
                columns = {
                    row[1]
                    for row in self._connection.execute("PRAGMA table_info(tasks)").fetchall()
                }
                if "claim_generation" not in columns:
                    self._connection.execute(
                        "ALTER TABLE tasks ADD COLUMN claim_generation "
                        "INTEGER NOT NULL DEFAULT 0"
                    )
                version = 7
            if version < 8:
                self._connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tasks_local_path ON tasks(local_path)"
                )
                self._connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tasks_video_id ON tasks(video_id)"
                )
                version = 8
            self._connection.execute(f"PRAGMA user_version = {version}")

    @staticmethod
    def _to_task(row: sqlite3.Row | None) -> Task | None:
        if row is None:
            return None
        values = {key: row[key] for key in Task.__dataclass_fields__}
        values["timeline_required"] = bool(values["timeline_required"])
        if values["title"] is not None:
            values["title"] = strip_display_controls(values["title"])
        return Task(**values)

    def get_task(self, task_id: str) -> Task | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        return self._to_task(row)

    def list_tasks(self, *, states: tuple[str, ...] | None = None) -> list[Task]:
        with self._lock:
            if states is None:
                rows = self._connection.execute(
                    "SELECT * FROM tasks ORDER BY created_at, task_id"
                ).fetchall()
            else:
                unknown = set(states) - _VALID_STATES
                if unknown:
                    raise ValueError(f"unknown task state: {sorted(unknown)[0]}")
                if not states:
                    return []
                placeholders = ",".join("?" for _ in states)
                rows = self._connection.execute(
                    f"SELECT * FROM tasks WHERE state IN ({placeholders}) "
                    "ORDER BY created_at, task_id",
                    states,
                ).fetchall()
        return [self._to_task(row) for row in rows if row is not None]

    def create_remote_task(
        self,
        source_url: str,
        video_id: str,
        *,
        profile: str = "balanced",
        title: str | None = None,
        processing_options: dict[str, object] | None = None,
    ) -> Task:
        """Create or return the task keyed by the canonical remote video ID."""
        clean_video_id = str(video_id).strip()
        if not clean_video_id:
            raise ValueError("video_id must be non-empty")
        if title is not None:
            title = strip_display_controls(title)
        canonical_url = canonicalize_source_url(source_url)
        options_json = _serialize_processing_options(processing_options)
        now = _now()
        with self._lock, self._transaction():
            self._connection.execute(
                """INSERT OR IGNORE INTO tasks
                   (task_id, source_url, video_id, title, state, profile,
                    created_at, updated_at, processing_options_json)
                   VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
                (
                    clean_video_id, canonical_url, clean_video_id, title, profile,
                    now, now, options_json,
                ),
            )
            row = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (clean_video_id,)
            ).fetchone()
        task = self._to_task(row)
        assert task is not None
        return task

    def create_local_task(
        self,
        media_path: str | os.PathLike[str],
        *,
        profile: str = "balanced",
        title: str | None = None,
        processing_options: dict[str, object] | None = None,
    ) -> Task:
        """Create or return a task keyed by normalized path and file content."""
        path = Path(media_path).expanduser().resolve(strict=True)
        if not _path_is_complete_file(path):
            raise ValueError("local input must be a non-empty complete file, not a .part file")
        content_hash = _sha256_file(path)
        normalized_path = os.path.normcase(str(path))
        stable_key = hashlib.sha256(
            normalized_path.encode("utf-8") + b"\0" + content_hash.encode("ascii")
        ).hexdigest()
        task_id = f"local:{stable_key}"
        if title is not None:
            title = strip_display_controls(title)
        options_json = _serialize_processing_options(processing_options)
        marker = _local_source_marker(path)
        now = _now()
        with self._lock, self._transaction():
            self._connection.execute(
                """INSERT OR IGNORE INTO tasks
                   (task_id, source_url, video_id, title, state, profile, media_path,
                    created_at, updated_at, local_path, content_hash,
                    processing_options_json)
                   VALUES (?, ?, NULL, ?, 'downloaded', ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    marker,
                    title,
                    profile,
                    str(path),
                    now,
                    now,
                    str(path),
                    content_hash,
                    options_json,
                ),
            )
            row = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        task = self._to_task(row)
        assert task is not None
        return task

    def claim_task(self, task_id: str, worker_id: str) -> Task | None:
        """Atomically claim one runnable task; return None if another worker owns it."""
        if not worker_id.strip():
            raise ValueError("worker_id must be non-empty")
        worker_id = worker_id.strip()
        now = _now()
        with self._lock, self._transaction():
            row = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            task = self._to_task(row)
            if task is None or task.state not in {"pending", "downloaded"} or task.claimed_by:
                return None
            new_state = "resolving" if task.state == "pending" else "downloaded"
            self._connection.execute(
                """UPDATE tasks SET state = ?, claimed_by = ?, claimed_at = ?,
                   claim_generation = claim_generation + 1,
                   attempt_count = attempt_count + 1, updated_at = ? WHERE task_id = ?""",
                (new_state, worker_id, now, now, task_id),
            )
            claimed = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        return self._to_task(claimed)

    def claim_next(self, worker_id: str) -> Task | None:
        """Atomically claim the oldest unclaimed pending or cached task."""
        if not worker_id.strip():
            raise ValueError("worker_id must be non-empty")
        worker_id = worker_id.strip()
        now = _now()
        with self._lock, self._transaction():
            row = self._connection.execute(
                """SELECT * FROM tasks
                   WHERE state IN ('pending', 'downloaded') AND claimed_by IS NULL
                   ORDER BY created_at, task_id LIMIT 1"""
            ).fetchone()
            task = self._to_task(row)
            if task is None:
                return None
            new_state = "resolving" if task.state == "pending" else "downloaded"
            self._connection.execute(
                """UPDATE tasks SET state = ?, claimed_by = ?, claimed_at = ?,
                   claim_generation = claim_generation + 1,
                   attempt_count = attempt_count + 1, updated_at = ?
                   WHERE task_id = ? AND claimed_by IS NULL""",
                (new_state, worker_id, now, now, task.task_id),
            )
            claimed = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task.task_id,)
            ).fetchone()
        return self._to_task(claimed)

    def heartbeat_claim(
        self,
        task_id: str,
        worker_id: str,
        *,
        claim_generation: int | None = None,
    ) -> bool:
        """Refresh a claim lease; return False if the caller does not own it."""
        worker_id = worker_id.strip()
        if claim_generation is None:
            raise ValueError("claim_generation is required for worker heartbeats")
        if (
            isinstance(claim_generation, bool)
            or not isinstance(claim_generation, int)
            or claim_generation < 0
        ):
            raise ValueError("claim_generation must be a non-negative integer")
        now = _now()
        with self._lock, self._transaction():
            cursor = self._connection.execute(
                """UPDATE tasks SET claimed_at = ?, updated_at = ?
                   WHERE task_id = ? AND claimed_by = ? AND claim_generation = ?""",
                (now, now, task_id, worker_id, claim_generation),
            )
            return cursor.rowcount == 1

    def transition(
        self,
        task_id: str,
        new_state: str,
        *,
        worker_id: str | None = None,
        claim_generation: int | None = None,
        media_path: str | os.PathLike[str] | None | object = _UNSET,
        output_path: str | os.PathLike[str] | None | object = _UNSET,
        title: str | None | object = _UNSET,
        source_duration_seconds: float | None | object = _UNSET,
        timeline_required: bool | object = _UNSET,
    ) -> Task:
        """Advance through one legal stage and commit that stage immediately."""
        if new_state not in _VALID_STATES - {"failed", "completed"}:
            raise ValueError(f"use fail_task/complete_task for state {new_state!r}")
        if worker_id is not None:
            worker_id = worker_id.strip()
        changes: dict[str, object] = {}
        for column, value in (
            ("media_path", media_path),
            ("output_path", output_path),
            ("title", title),
        ):
            if value is not _UNSET:
                if value is None:
                    changes[column] = None
                elif column in {"media_path", "output_path"}:
                    changes[column] = str(Path(value).expanduser().resolve())
                elif column == "title":
                    changes[column] = strip_display_controls(str(value))
                else:
                    changes[column] = str(value)
        if source_duration_seconds is not _UNSET:
            if source_duration_seconds is None:
                changes["source_duration_seconds"] = None
            else:
                if isinstance(source_duration_seconds, bool) or not isinstance(
                    source_duration_seconds, (int, float)
                ):
                    raise ValueError(
                        "source_duration_seconds must be a positive finite number"
                    )
                try:
                    duration = float(source_duration_seconds)
                except OverflowError:
                    duration = float("inf")
                if not math.isfinite(duration) or duration <= 0:
                    raise ValueError(
                        "source_duration_seconds must be a positive finite number"
                    )
                changes["source_duration_seconds"] = duration
        if timeline_required is not _UNSET:
            if not isinstance(timeline_required, bool):
                raise ValueError("timeline_required must be a boolean")
            changes["timeline_required"] = int(timeline_required)
        if new_state == "writing":
            # Every writing attempt starts with a fresh sidecar binding.
            if timeline_required is _UNSET:
                changes["timeline_required"] = 0
            changes["timeline_path"] = None
            changes["timeline_sha256"] = None
            changes["output_sha256"] = None
        now = _now()
        with self._lock, self._transaction():
            row = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            task = self._to_task(row)
            if task is None:
                raise KeyError(task_id)
            _require_claim_owner(task, worker_id, claim_generation)
            if new_state not in _TRANSITIONS[task.state]:
                raise ValueError(f"illegal task transition: {task.state} -> {new_state}")
            if new_state == "downloaded":
                candidate = changes.get("media_path", task.media_path)
                if candidate is None or not _path_is_complete_file(Path(str(candidate))):
                    raise ValueError("downloaded state requires a non-empty file other than .part")
            assignments = ["state = ?", "updated_at = ?"]
            values: list[object] = [new_state, now]
            for column, value in changes.items():
                assignments.append(f"{column} = ?")
                values.append(value)
            values.append(task_id)
            self._connection.execute(
                f"UPDATE tasks SET {', '.join(assignments)} WHERE task_id = ?", values
            )
            updated = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        result = self._to_task(updated)
        assert result is not None
        return result

    def fail_task(
        self,
        task_id: str,
        error_code: str,
        error_message: str | None = None,
        *,
        worker_id: str | None = None,
        claim_generation: int | None = None,
    ) -> Task:
        """Persist failure immediately and release the claim."""
        error_code = error_code.strip()
        if not _ERROR_CODE.fullmatch(error_code):
            raise ValueError(
                "error_code must contain only letters, digits, dot, underscore, or hyphen"
            )
        if worker_id is not None:
            worker_id = worker_id.strip()
        now = _now()
        safe_message = _sanitize_error_message(error_message)
        with self._lock, self._transaction():
            row = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            task = self._to_task(row)
            if task is None:
                raise KeyError(task_id)
            if task.state == "completed":
                raise ValueError("completed tasks cannot transition to failed")
            if task.state == "failed":
                raise ValueError("failed task must be explicitly retried before another attempt")
            _require_claim_owner(task, worker_id, claim_generation)
            self._connection.execute(
                """UPDATE tasks SET state = 'failed', error_code = ?, error_message = ?,
                   claimed_by = NULL, claimed_at = NULL, claim_generation = claim_generation + 1,
                   completed_at = NULL, updated_at = ?
                   WHERE task_id = ?""",
                (error_code, safe_message, now, task_id),
            )
            updated = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        result = self._to_task(updated)
        assert result is not None
        return result

    def update_failed_retry_error(
        self, task_id: str, error_code: str, error_message: str | None = None
    ) -> Task:
        """Keep an unstarted retry failed while recording its new input error."""
        error_code = error_code.strip()
        if not _ERROR_CODE.fullmatch(error_code):
            raise ValueError(
                "error_code must contain only letters, digits, dot, underscore, or hyphen"
            )
        now = _now()
        safe_message = _sanitize_error_message(error_message)
        with self._lock, self._transaction():
            row = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            task = self._to_task(row)
            if task is None:
                raise KeyError(task_id)
            if task.state != "failed":
                raise ValueError("only a failed task can record a retry input error")
            self._connection.execute(
                "UPDATE tasks SET error_code = ?, error_message = ?, updated_at = ? "
                "WHERE task_id = ?",
                (error_code, safe_message, now, task_id),
            )
            updated = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        result = self._to_task(updated)
        assert result is not None
        return result

    def retry_failed(
        self,
        *,
        error_code: str | None = None,
        task_id: str | None = None,
        limit: int | None = None,
        include_login_required: bool = False,
        processing_options: dict[str, object] | None = None,
    ) -> list[Task]:
        """Queue eligible failures; local tasks stay failed until input validation."""
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")
        if limit == 0:
            return []
        options_json = (
            _serialize_processing_options(processing_options)
            if processing_options is not None
            else None
        )
        conditions = ["state = 'failed'"]
        params: list[object] = []
        if error_code is not None:
            conditions.append("error_code = ?")
            params.append(error_code)
        if task_id is not None:
            conditions.append("task_id = ?")
            params.append(task_id)
        if not include_login_required:
            conditions.append("COALESCE(error_code, '') != 'LOGIN_REQUIRED'")
        limit_sql = ""
        if limit is not None:
            limit_sql = " LIMIT ?"
            params.append(limit)
        now = _now()
        with self._lock, self._transaction():
            rows = self._connection.execute(
                "SELECT * FROM tasks WHERE "
                + " AND ".join(conditions)
                + " ORDER BY created_at, task_id"
                + limit_sql,
                params,
            ).fetchall()
            ids = [row["task_id"] for row in rows]
            for row in rows:
                # A local retry must remain failed until the CLI has validated
                # that the original path and content are still available.
                if row["local_path"] is not None:
                    if options_json is not None:
                        self._connection.execute(
                            "UPDATE tasks SET processing_options_json = ?, updated_at = ? "
                            "WHERE task_id = ?",
                            (options_json, now, row["task_id"]),
                        )
                    continue
                if options_json is None:
                    self._connection.execute(
                        """UPDATE tasks SET state = 'pending', error_code = NULL,
                           error_message = NULL, claimed_by = NULL, claimed_at = NULL,
                           claim_generation = claim_generation + 1,
                           completed_at = NULL, output_path = NULL, output_sha256 = NULL,
                           timeline_path = NULL, timeline_sha256 = NULL, timeline_required = 0,
                           updated_at = ? WHERE task_id = ?""",
                        (now, row["task_id"]),
                    )
                else:
                    self._connection.execute(
                        """UPDATE tasks SET state = 'pending', error_code = NULL,
                           error_message = NULL, claimed_by = NULL, claimed_at = NULL,
                           claim_generation = claim_generation + 1,
                           completed_at = NULL, output_path = NULL, output_sha256 = NULL,
                           timeline_path = NULL, timeline_sha256 = NULL, timeline_required = 0,
                           processing_options_json = ?, updated_at = ? WHERE task_id = ?""",
                        (options_json, now, row["task_id"]),
                    )
            retried = [
                self._connection.execute(
                    "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
                ).fetchone()
                for task_id in ids
            ]
        return [task for row in retried if (task := self._to_task(row)) is not None]

    def fail_unclaimed_retry(
        self,
        task_id: str,
        *,
        expected_claim_generation: int,
        error_code: str,
        error_message: str | None = None,
    ) -> bool:
        """Restore a retry to failed if URL resolution failed before claiming it."""
        error_code = error_code.strip()
        if not _ERROR_CODE.fullmatch(error_code):
            raise ValueError(
                "error_code must contain only letters, digits, dot, underscore, or hyphen"
            )
        if (
            isinstance(expected_claim_generation, bool)
            or not isinstance(expected_claim_generation, int)
            or expected_claim_generation < 0
        ):
            raise ValueError("expected_claim_generation must be a non-negative integer")
        now = _now()
        safe_message = _sanitize_error_message(error_message)
        with self._lock, self._transaction():
            cursor = self._connection.execute(
                """UPDATE tasks SET state = 'failed', error_code = ?, error_message = ?,
                   claim_generation = claim_generation + 1, completed_at = NULL,
                   updated_at = ?
                   WHERE task_id = ? AND state = 'pending' AND claimed_by IS NULL
                   AND claim_generation = ?""",
                (
                    error_code,
                    safe_message,
                    now,
                    task_id,
                    expected_claim_generation,
                ),
            )
            return cursor.rowcount == 1

    def prepare_local_retry(
        self,
        task_id: str,
        media_path: str | os.PathLike[str],
        *,
        worker_id: str | None = None,
    ) -> Task:
        """Queue a failed local task only after its original path/content validate."""
        if worker_id is not None:
            worker_id = worker_id.strip()
            if not worker_id:
                raise ValueError("worker_id must be non-empty")
        path = Path(media_path).expanduser().resolve(strict=True)
        if not _path_is_complete_file(path):
            raise ValueError("local input must be a non-empty complete file, not a .part file")
        content_hash = _sha256_file(path)
        normalized_path = os.path.normcase(str(path))
        now = _now()
        with self._lock, self._transaction():
            row = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            task = self._to_task(row)
            if task is None:
                raise KeyError(task_id)
            if task.state != "failed" or not task.local_path:
                raise ValueError("local retry task is no longer failed")
            stored_path = os.path.normcase(
                str(Path(task.local_path).expanduser().resolve(strict=False))
            )
            if stored_path != normalized_path or task.content_hash != content_hash:
                raise ValueError("local retry input path or content changed")
            if worker_id is None:
                self._connection.execute(
                    """UPDATE tasks SET state = 'downloaded', error_code = NULL,
                       error_message = NULL, output_path = NULL, output_sha256 = NULL,
                       timeline_path = NULL, timeline_sha256 = NULL, timeline_required = 0,
                       claimed_by = NULL, claimed_at = NULL,
                       claim_generation = claim_generation + 1, completed_at = NULL,
                       updated_at = ? WHERE task_id = ? AND state = 'failed'""",
                    (now, task_id),
                )
            else:
                self._connection.execute(
                    """UPDATE tasks SET state = 'downloaded', error_code = NULL,
                       error_message = NULL, output_path = NULL, output_sha256 = NULL,
                       timeline_path = NULL, timeline_sha256 = NULL, timeline_required = 0,
                       claimed_by = ?, claimed_at = ?,
                       claim_generation = claim_generation + 1,
                       attempt_count = attempt_count + 1, completed_at = NULL,
                       updated_at = ? WHERE task_id = ? AND state = 'failed'""",
                    (worker_id, now, now, task_id),
                )
            updated = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        result = self._to_task(updated)
        assert result is not None
        return result

    def set_writing_output_path(
        self,
        task_id: str,
        output_path: str | os.PathLike[str],
        *,
        worker_id: str | None = None,
        claim_generation: int | None = None,
    ) -> Task:
        """Persist the actual no-overwrite writer destination for crash recovery."""
        resolved = Path(output_path).expanduser().resolve(strict=False)
        now = _now()
        with self._lock, self._transaction():
            row = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            task = self._to_task(row)
            if task is None:
                raise KeyError(task_id)
            if task.state != "writing":
                raise ValueError("task must be in writing state before setting output path")
            _require_claim_owner(task, worker_id, claim_generation)
            self._connection.execute(
                """UPDATE tasks SET output_path = ?, output_sha256 = NULL,
                   timeline_path = NULL, timeline_sha256 = NULL,
                   updated_at = ? WHERE task_id = ?""",
                (str(resolved), now, task_id),
            )
            updated = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        result = self._to_task(updated)
        assert result is not None
        return result

    def record_output_integrity(
        self,
        task_id: str,
        output_path: str | os.PathLike[str],
        expected_sha256: str,
        *,
        worker_id: str | None = None,
        claim_generation: int | None = None,
    ) -> Task:
        """Bind the published Markdown bytes to this attempt in the private DB."""
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            raise ValueError("expected_sha256 must be a lowercase SHA-256 digest")
        resolved = Path(output_path).expanduser().resolve(strict=False)
        now = _now()
        with self._lock, self._transaction():
            row = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            task = self._to_task(row)
            if task is None:
                raise KeyError(task_id)
            if task.state != "writing":
                raise ValueError("task must be in writing state before recording output")
            _require_claim_owner(task, worker_id, claim_generation)
            if not task.output_path or os.path.normcase(task.output_path) != os.path.normcase(
                str(resolved)
            ):
                raise ValueError("output path does not match the writing task")
            if (
                not _output_associated_with_task(resolved, task)
                or _sha256_file(resolved) != expected_sha256
            ):
                raise ValueError("published output does not match this attempt")
            self._connection.execute(
                "UPDATE tasks SET output_sha256 = ?, updated_at = ? WHERE task_id = ?",
                (expected_sha256, now, task_id),
            )
            updated = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        result = self._to_task(updated)
        assert result is not None
        return result

    def prepare_timeline_integrity(
        self,
        task_id: str,
        timeline_path: str | os.PathLike[str],
        expected_sha256: str,
        *,
        worker_id: str | None = None,
        claim_generation: int | None = None,
    ) -> Task:
        """Persist the expected sidecar path and digest before publishing it."""
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            raise ValueError("expected_sha256 must be a lowercase SHA-256 digest")
        resolved = _lexical_absolute_path(Path(timeline_path))
        now = _now()
        with self._lock, self._transaction():
            row = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            task = self._to_task(row)
            if task is None:
                raise KeyError(task_id)
            if task.state != "writing":
                raise ValueError("task must be in writing state before binding a timeline")
            _require_claim_owner(task, worker_id, claim_generation)
            if not task.timeline_required:
                raise ValueError("timeline output was not requested for this attempt")
            if not task.output_path:
                raise ValueError("main output path must be bound before the timeline")
            output_path = Path(task.output_path).expanduser().resolve(strict=False)
            expected_base = f"{output_path.stem}_timeline"
            if os.path.normcase(str(resolved.parent)) != os.path.normcase(
                str(output_path.parent)
            ) or not re.fullmatch(
                re.escape(expected_base) + r"(?:__(?:[2-9]|[1-9][0-9]{1,3}))?\.md",
                resolved.name,
            ):
                raise ValueError("timeline path is not a valid sidecar of this output")
            self._connection.execute(
                """UPDATE tasks SET timeline_path = ?, timeline_sha256 = ?, updated_at = ?
                   WHERE task_id = ?""",
                (str(resolved), expected_sha256, now, task_id),
            )
            updated = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        result = self._to_task(updated)
        assert result is not None
        return result

    def complete_task(
        self,
        task_id: str,
        output_path: str | os.PathLike[str],
        *,
        worker_id: str | None = None,
        claim_generation: int | None = None,
    ) -> Task:
        """Mark completed only when the output matches its private attempt digest."""
        resolved_output = Path(output_path).expanduser().resolve()
        now = _now()
        with self._lock, self._transaction():
            row = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            task = self._to_task(row)
            if task is None:
                raise KeyError(task_id)
            if task.state != "writing":
                raise ValueError("task must be in writing state before completion")
            _require_claim_owner(task, worker_id, claim_generation)
            if (
                not _output_matches_task(resolved_output, task)
                or not _timeline_matches_task(
                    Path(task.timeline_path) if task.timeline_path else Path(""), task
                )
            ):
                raise ValueError(
                    "output file or timeline file is missing, changed, malformed, "
                    "or not bound to this task"
                )
            self._connection.execute(
                """UPDATE tasks SET state = 'completed', output_path = ?, error_code = NULL,
                   error_message = NULL, completed_at = ?, updated_at = ?,
                   claimed_by = NULL, claimed_at = NULL,
                   claim_generation = claim_generation + 1 WHERE task_id = ?""",
                (str(resolved_output), now, now, task_id),
            )
            updated = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        result = self._to_task(updated)
        assert result is not None
        return result

    def is_completed_valid(self, task_id: str) -> bool:
        """Re-check the output digest and embedded task association."""
        task = self.get_task(task_id)
        return bool(
            task is not None
            and task.state == "completed"
            and task.output_path
            and _task_outputs_match(task)
        )

    def get_valid_completed_task(self, task_id: str) -> Task | None:
        """Return a completed task only if its recorded output still validates."""
        task = self.get_task(task_id)
        return task if task is not None and self.is_completed_valid(task_id) else None

    def reopen_completed(
        self,
        task_id: str,
        *,
        initial_state: str = "pending",
        profile: str | None = None,
        title: str | None | object = _UNSET,
        processing_options: dict[str, object] | None = None,
    ) -> Task:
        """Explicitly queue a completed task for a non-destructive forced rerun.

        The old output path remains on disk; the caller must write a new
        collision-safe output. Local inputs can start at ``downloaded`` because
        their source media is already available. Remote inputs start at
        ``pending`` and are recaptured.
        """
        if initial_state not in {"pending", "downloaded"}:
            raise ValueError("initial_state must be pending or downloaded")
        now = _now()
        with self._lock, self._transaction():
            row = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            task = self._to_task(row)
            if task is None:
                raise KeyError(task_id)
            if task.state != "completed":
                raise ValueError("only completed tasks can be reopened")
            if initial_state == "downloaded" and (
                task.media_path is None or not _path_is_complete_file(Path(task.media_path))
            ):
                raise ValueError("downloaded state requires a complete cached media file")
            updates = [
                "state = ?",
                "error_code = NULL",
                "error_message = NULL",
                "completed_at = NULL",
                "output_path = NULL",
                "output_sha256 = NULL",
                "timeline_path = NULL",
                "timeline_sha256 = NULL",
                "timeline_required = 0",
                "claimed_by = NULL",
                "claimed_at = NULL",
                "claim_generation = claim_generation + 1",
                "updated_at = ?",
            ]
            values: list[object] = [initial_state, now]
            if profile is not None:
                updates.append("profile = ?")
                values.append(profile)
            if title is not _UNSET:
                updates.append("title = ?")
                values.append(
                    strip_display_controls(title) if isinstance(title, str) else title
                )
            if processing_options is not None:
                updates.append("processing_options_json = ?")
                values.append(_serialize_processing_options(processing_options))
            if initial_state == "pending":
                updates.append("source_duration_seconds = NULL")
            values.append(task_id)
            self._connection.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE task_id = ?",
                values,
            )
            updated = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        result = self._to_task(updated)
        assert result is not None
        return result

    def recover_interrupted(
        self,
        *,
        stale_after_seconds: float = 300,
        media_validator: MediaValidator | None = None,
    ) -> list[RecoveryResult]:
        """Recover stale stages after validating media and any just-written output.

        ``resolving`` resumes at ``pending`` unless a validated media cache exists.
        ``downloading`` becomes ``downloaded`` only for a complete non-.part file.
        ``transcribing`` and ``writing`` rerun from downloaded media; a valid output
        already present during ``writing`` becomes completed. Active claims newer
        than the staleness threshold are left alone.
        """
        if stale_after_seconds < 0:
            raise ValueError("stale_after_seconds must be non-negative")
        validate_media = media_validator or _path_is_complete_file
        cutoff = (datetime.now(UTC) - timedelta(seconds=stale_after_seconds)).isoformat(
            timespec="milliseconds"
        )
        results: list[RecoveryResult] = []
        with self._lock:
            rows = self._connection.execute(
                """SELECT * FROM tasks
                   WHERE (state IN ('resolving', 'downloading', 'transcribing', 'writing')
                          OR (state = 'downloaded' AND claimed_by IS NOT NULL))
                   AND (claimed_by IS NULL OR claimed_at IS NULL OR claimed_at <= ?)
                   ORDER BY created_at, task_id""",
                (cutoff,),
            ).fetchall()
        candidates = [task for row in rows if (task := self._to_task(row)) is not None]

        # Media decoding and output hashing can take substantial time. Perform
        # both checks without a SQLite write transaction so another process can
        # continue claiming or updating tasks while recovery examines the files.
        decisions: list[tuple[Task, bool, bool, str, str]] = []
        for task in candidates:
            media_ok = False
            if task.media_path:
                try:
                    media_ok = bool(validate_media(Path(task.media_path)))
                except Exception:
                    media_ok = False
            output_ok = bool(
                task.state == "writing"
                and task.output_path
                and _task_outputs_match(task)
            )
            if output_ok:
                target, reason = "completed", "valid associated output already exists"
            elif media_ok:
                target, reason = "downloaded", "validated media cache can be reused"
            else:
                target, reason = "pending", "no valid media cache; restart from source"
            decisions.append((task, media_ok, output_ok, target, reason))

        now = _now()
        with self._lock, self._transaction():
            for task, media_ok, output_ok, target, reason in decisions:
                current_row = self._connection.execute(
                    "SELECT * FROM tasks WHERE task_id = ?", (task.task_id,)
                ).fetchone()
                current_task = self._to_task(current_row)
                # A heartbeat, worker transition, or concurrent recovery may
                # have changed this task while its files were being checked.
                # Never apply the earlier decision to a newer row snapshot.
                if current_task != task:
                    continue
                completed_at = now if target == "completed" else None
                media_path = task.media_path if media_ok else None
                output_path = task.output_path if output_ok else None
                self._connection.execute(
                    """UPDATE tasks SET state = ?, media_path = ?, output_path = ?,
                       output_sha256 = ?,
                       timeline_path = ?, timeline_sha256 = ?,
                       timeline_required = ?,
                       error_code = NULL, error_message = NULL, completed_at = ?,
                       claimed_by = NULL, claimed_at = NULL,
                       claim_generation = claim_generation + 1, updated_at = ?
                       WHERE task_id = ?""",
                    (
                        target,
                        media_path,
                        output_path,
                        task.output_sha256 if output_ok else None,
                        task.timeline_path if output_ok else None,
                        task.timeline_sha256 if output_ok else None,
                        int(task.timeline_required) if output_ok else 0,
                        completed_at,
                        now,
                        task.task_id,
                    ),
                )
                results.append(RecoveryResult(task.task_id, task.state, target, reason))
        return results
