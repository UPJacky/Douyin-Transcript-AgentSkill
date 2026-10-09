from __future__ import annotations

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event

import douyin_transcript.tasks as task_module
import pytest
from douyin_transcript.corrections import CorrectionRule, apply_terminology_dictionary
from douyin_transcript.markdown import render_transcript_markdown
from douyin_transcript.tasks import TaskStore


def _markdown(
    path: Path, *, video_id: str | None = None, source_url: str | None = None
) -> Path:
    metadata = []
    if video_id is not None:
        metadata.append(f'video_id: "{video_id}"')
    if source_url is not None:
        metadata.append(f'source_url: "{source_url}"')
    path.write_text(
        "---\n" + "\n".join(metadata) + "\n---\n\n逐字稿正文\n", encoding="utf-8"
    )
    return path


def _to_writing(
    store: TaskStore,
    task_id: str,
    media_path: Path,
    worker: str | None = None,
    *,
    timeline_required: bool = False,
):
    current = store.get_task(task_id)
    assert current is not None
    def worker_options() -> dict[str, object]:
        if worker is None:
            return {}
        return {"worker_id": worker, "claim_generation": current.claim_generation}

    if current.state == "pending":
        current = store.transition(task_id, "resolving", **worker_options())
    if current.state == "resolving":
        current = store.transition(task_id, "downloading", **worker_options())
    if current.state == "downloading":
        current = store.transition(
            task_id, "downloaded", media_path=media_path, **worker_options()
        )
    if current.state == "downloaded":
        current = store.transition(task_id, "transcribing", **worker_options())
    if current.state == "transcribing":
        current = store.transition(
            task_id,
            "writing",
            timeline_required=timeline_required,
            **worker_options(),
        )
    return current


def test_task_store_rejects_symlink_database_alias(tmp_path):
    target = tmp_path / "tasks.sqlite3"
    with TaskStore(target):
        pass

    alias = tmp_path / "database-alias.sqlite3"
    try:
        alias.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"filesystem does not permit symlink creation: {type(exc).__name__}")

    with pytest.raises(PermissionError, match="重解析点|符号链接|普通文件"):
        TaskStore(alias)


def test_task_store_checks_database_before_resolving_path(monkeypatch, tmp_path):
    database = tmp_path / "database.sqlite3"
    database.write_bytes(b"existing")
    seen_paths = []
    original_resolve = Path.resolve

    def guarded_resolve(path, *args, **kwargs):
        if path == database:
            pytest.fail("TaskStore must preserve the lexical database path")
        return original_resolve(path, *args, **kwargs)

    def reject_leaf(path):
        seen_paths.append(Path(path))
        return type("Report", (), {"status": "unknown", "detail": "simulated link"})()

    monkeypatch.setattr(Path, "resolve", guarded_resolve)
    monkeypatch.setattr(task_module, "inspect_private_path", reject_leaf)

    with pytest.raises(PermissionError):
        TaskStore(database)

    assert seen_paths == [database]


def test_wal_initialization_retries_transient_locking_protocol(monkeypatch):
    class FlakyConnection:
        attempts = 0

        def execute(self, _statement):
            self.attempts += 1
            if self.attempts == 1:
                raise sqlite3.OperationalError("locking protocol")
            return None

    store = TaskStore.__new__(TaskStore)
    connection = FlakyConnection()
    store._connection = connection
    monkeypatch.setattr(task_module.time, "sleep", lambda _seconds: None)

    store._enable_wal(busy_timeout_ms=100)

    assert connection.attempts == 2


def test_schema_migration_adds_claim_and_local_identity_columns(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute(
        """CREATE TABLE tasks (
            task_id TEXT PRIMARY KEY, source_url TEXT NOT NULL, video_id TEXT, title TEXT,
            state TEXT NOT NULL, profile TEXT NOT NULL, media_path TEXT, output_path TEXT,
            error_code TEXT, error_message TEXT, attempt_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT
        )"""
    )
    connection.execute("PRAGMA user_version = 1")
    connection.commit()
    connection.close()

    with TaskStore(database) as store:
        columns = {
            row[1] for row in store._connection.execute("PRAGMA table_info(tasks)")
        }
        version = store._connection.execute("PRAGMA user_version").fetchone()[0]
        indexes = {
            row[1] for row in store._connection.execute("PRAGMA index_list(tasks)")
        }

    assert version == 8
    assert {"idx_tasks_local_path", "idx_tasks_video_id"} <= indexes
    assert {
        "claimed_by",
        "claimed_at",
        "local_path",
        "content_hash",
        "processing_options_json",
        "source_duration_seconds",
        "output_sha256",
        "timeline_path",
        "timeline_sha256",
        "timeline_required",
        "claim_generation",
    } <= columns


def test_schema_v2_migration_adds_empty_processing_options_snapshot(tmp_path):
    database = tmp_path / "v2.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute(
        """CREATE TABLE tasks (
            task_id TEXT PRIMARY KEY, source_url TEXT NOT NULL, video_id TEXT,
            title TEXT, state TEXT NOT NULL, profile TEXT NOT NULL, media_path TEXT,
            output_path TEXT, error_code TEXT, error_message TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, completed_at TEXT, claimed_by TEXT,
            claimed_at TEXT, local_path TEXT, content_hash TEXT
        )"""
    )
    connection.execute(
        """
        INSERT INTO tasks (task_id, source_url, state, profile, created_at, updated_at)
        VALUES ('legacy', 'https://www.douyin.com/video/legacy', 'failed', 'balanced', 'now', 'now')
        """
    )
    connection.execute("PRAGMA user_version = 2")
    connection.commit()
    connection.close()

    with TaskStore(database) as store:
        legacy = store.get_task("legacy")
        version = store._connection.execute("PRAGMA user_version").fetchone()[0]

    assert version == 8
    assert legacy is not None
    assert legacy.processing_options_json == "{}"
    assert legacy.source_duration_seconds is None


def test_schema_v3_migration_preserves_task_and_adds_unknown_source_duration(tmp_path):
    database = tmp_path / "v3.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute(
        """CREATE TABLE tasks (
            task_id TEXT PRIMARY KEY, source_url TEXT NOT NULL, video_id TEXT,
            title TEXT, state TEXT NOT NULL, profile TEXT NOT NULL, media_path TEXT,
            output_path TEXT, error_code TEXT, error_message TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, completed_at TEXT, claimed_by TEXT,
            claimed_at TEXT, local_path TEXT, content_hash TEXT,
            processing_options_json TEXT NOT NULL DEFAULT '{}'
        )"""
    )
    connection.execute(
        """INSERT INTO tasks (
               task_id, source_url, video_id, title, state, profile,
               created_at, updated_at, processing_options_json
           ) VALUES ('legacy-v3', 'https://www.douyin.com/video/legacy-v3',
                     'legacy-v3', 'saved title', 'failed', 'balanced',
                     'created', 'updated', '{"language":"auto"}')"""
    )
    connection.execute("PRAGMA user_version = 3")
    connection.commit()
    connection.close()

    with TaskStore(database) as store:
        legacy = store.get_task("legacy-v3")
        version = store._connection.execute("PRAGMA user_version").fetchone()[0]

    assert version == 8
    assert legacy is not None
    assert legacy.title == "saved title"
    assert legacy.processing_options_json == '{"language":"auto"}'
    assert legacy.source_duration_seconds is None


def test_v5_migration_fails_closed_for_completed_tasks_without_timeline_manifest(tmp_path):
    database = tmp_path / "v5.sqlite3"
    with TaskStore(database) as store:
        pass
    output = tmp_path / "legacy-timestamps.md"
    no_timestamps_output = tmp_path / "legacy-no-timestamps.md"
    unknown_timestamps_output = tmp_path / "legacy-unknown-timestamps.md"
    malformed_options_output = tmp_path / "legacy-malformed-options.md"
    _markdown(output, video_id="legacy-timestamps")
    _markdown(no_timestamps_output, video_id="legacy-no-timestamps")
    _markdown(unknown_timestamps_output, video_id="legacy-unknown-timestamps")
    _markdown(malformed_options_output, video_id="legacy-malformed-options")

    connection = sqlite3.connect(database)
    connection.execute(
        """CREATE TABLE tasks_v5 (
            task_id TEXT PRIMARY KEY, source_url TEXT NOT NULL, video_id TEXT,
            title TEXT, state TEXT NOT NULL, profile TEXT NOT NULL, media_path TEXT,
            output_path TEXT, output_sha256 TEXT, error_code TEXT, error_message TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, completed_at TEXT, claimed_by TEXT,
            claimed_at TEXT, local_path TEXT, content_hash TEXT,
            processing_options_json TEXT NOT NULL DEFAULT '{}',
            source_duration_seconds REAL
        )"""
    )
    connection.execute(
        """INSERT INTO tasks_v5 VALUES (
            'legacy-timestamps', 'https://www.douyin.com/video/legacy-timestamps',
            'legacy-timestamps', 'legacy', 'completed', 'balanced', NULL, ?, ?, NULL,
            NULL, 1, 'now', 'now', 'now', NULL, NULL, NULL, NULL, ?, NULL
        )""",
        (
            str(output),
            hashlib.sha256(output.read_bytes()).hexdigest(),
            '{"timestamps":true}',
        ),
    )
    connection.execute(
        """INSERT INTO tasks_v5 VALUES (
            'legacy-no-timestamps', 'https://www.douyin.com/video/legacy-no-timestamps',
            'legacy-no-timestamps', 'legacy', 'completed', 'balanced', NULL, ?, ?, NULL,
            NULL, 1, 'now', 'now', 'now', NULL, NULL, NULL, NULL, ?, NULL
        )""",
        (
            str(no_timestamps_output),
            hashlib.sha256(no_timestamps_output.read_bytes()).hexdigest(),
            '{"timestamps":false}',
        ),
    )
    for task_id, path, options_json in (
        ("legacy-unknown-timestamps", unknown_timestamps_output, "{}"),
        ("legacy-malformed-options", malformed_options_output, "not-json"),
    ):
        connection.execute(
            """INSERT INTO tasks_v5 VALUES (
                ?, ?, ?, 'legacy', 'completed', 'balanced', NULL, ?, ?, NULL, NULL,
                1, 'now', 'now', 'now', NULL, NULL, NULL, NULL, ?, NULL
            )""",
            (
                task_id,
                f"https://www.douyin.com/video/{task_id}",
                task_id,
                str(path),
                hashlib.sha256(path.read_bytes()).hexdigest(),
                options_json,
            ),
        )
    connection.execute("DROP TABLE tasks")
    connection.execute("ALTER TABLE tasks_v5 RENAME TO tasks")
    connection.execute("PRAGMA user_version = 5")
    connection.commit()
    connection.close()

    with TaskStore(database) as store:
        requires_sidecar = store.get_task("legacy-timestamps")
        no_sidecar = store.get_task("legacy-no-timestamps")
        unknown_snapshot = store.get_task("legacy-unknown-timestamps")
        malformed_snapshot = store.get_task("legacy-malformed-options")
        assert requires_sidecar is not None and requires_sidecar.timeline_required
        assert no_sidecar is not None and not no_sidecar.timeline_required
        assert unknown_snapshot is not None and unknown_snapshot.timeline_required
        assert malformed_snapshot is not None and malformed_snapshot.timeline_required
        assert not store.is_completed_valid("legacy-timestamps")
        assert store.is_completed_valid("legacy-no-timestamps")
        assert not store.is_completed_valid("legacy-unknown-timestamps")
        assert not store.is_completed_valid("legacy-malformed-options")


def test_remote_creation_is_immediately_durable_and_strips_url_secrets(tmp_path):
    database = tmp_path / "tasks.sqlite3"
    store = TaskStore(database)
    first = store.create_remote_task(
        "https://User:Password@www.douyin.com/video/123?X-Bogus=secret&token=private#fragment",
        "123",
    )
    assert first.source_url == "https://www.douyin.com/video/123"
    store.close()

    with TaskStore(database) as reopened:
        persisted = reopened.get_task("123")

    assert persisted is not None
    assert persisted.state == "pending"
    raw_database = database.read_bytes()
    assert b"Password" not in raw_database
    assert b"secret" not in raw_database
    assert b"private" not in raw_database
    assert b"fragment" not in raw_database


def test_processing_options_are_optional_bounded_json_and_never_default_to_body(tmp_path):
    database = tmp_path / "tasks-options.sqlite3"
    with TaskStore(database) as store:
        legacy = store.create_remote_task("https://www.douyin.com/video/1", "1")
        configured = store.create_remote_task(
            "https://www.douyin.com/video/2",
            "2",
            processing_options={"language": "auto", "timestamps": True},
        )

    assert legacy.processing_options_json == "{}"
    assert configured.processing_options_json == '{"language":"auto","timestamps":true}'
    assert b"transcript" not in database.read_bytes()
    with TaskStore(tmp_path / "reject-options.sqlite3") as store:
        with pytest.raises(ValueError, match="unsupported fields"):
            store.create_remote_task(
                "https://www.douyin.com/video/3",
                "3",
                processing_options={"transcript": "private text"},
            )


def test_remote_dedup_uses_video_id_and_keeps_first_canonical_source(tmp_path):
    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        first = store.create_remote_task(
            "https://www.douyin.com/video/123?token=one", "123"
        )
        duplicate = store.create_remote_task(
            "https://v.douyin.com/other?signature=two", "123"
        )

    assert duplicate.task_id == first.task_id == "123"
    assert duplicate.source_url == "https://www.douyin.com/video/123"
    assert duplicate.created_at == first.created_at


def test_local_dedup_uses_absolute_path_and_content_hash(tmp_path):
    one = tmp_path / "one.wav"
    two = tmp_path / "two.wav"
    one.write_bytes(b"audio-content")
    two.write_bytes(b"audio-content")

    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        first = store.create_local_task(one)
        same = store.create_local_task(one)
        different_path = store.create_local_task(two)
        one.write_bytes(b"changed-audio")
        changed_content = store.create_local_task(one)

    assert first.task_id == same.task_id
    assert first.state == "downloaded"
    assert first.media_path == str(one.resolve())
    assert first.content_hash != changed_content.content_hash
    assert len({first.task_id, different_path.task_id, changed_content.task_id}) == 3


def test_transition_graph_persists_each_stage_and_rejects_skips(tmp_path):
    media = tmp_path / "media.bin"
    media.write_bytes(b"media")
    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        task = store.create_remote_task("https://www.douyin.com/video/456", "456")
        with pytest.raises(ValueError, match="illegal task transition"):
            store.transition(task.task_id, "downloaded", media_path=media)
        task = store.transition(task.task_id, "resolving")
        task = store.transition(
            task.task_id, "downloading", source_duration_seconds=58.5
        )
        task = store.transition(task.task_id, "downloaded", media_path=media)
        assert task.source_duration_seconds == 58.5
        assert store.get_task(task.task_id).state == "downloaded"
        task = store.transition(task.task_id, "transcribing")
        task = store.transition(task.task_id, "writing")

    assert task.state == "writing"


@pytest.mark.parametrize(
    "duration", [True, 0, -1, float("nan"), float("inf"), 10**400, "5"]
)
def test_transition_rejects_invalid_source_duration(tmp_path, duration):
    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        task = store.create_remote_task("https://www.douyin.com/video/invalid", "invalid")
        store.transition(task.task_id, "resolving")

        with pytest.raises(ValueError, match="positive finite number"):
            store.transition(
                task.task_id, "downloading", source_duration_seconds=duration
            )

        assert store.get_task(task.task_id).state == "resolving"


def test_downloaded_state_rejects_empty_and_part_files(tmp_path):
    part = tmp_path / "media.mp3.part"
    part.write_bytes(b"partial")
    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        task = store.create_remote_task("https://www.douyin.com/video/part", "part")
        store.transition(task.task_id, "resolving")
        store.transition(task.task_id, "downloading")
        with pytest.raises(ValueError, match=r"other than \.part"):
            store.transition(task.task_id, "downloaded", media_path=part)
        assert store.get_task(task.task_id).state == "downloading"


def test_completion_requires_nonempty_output_associated_by_video_id(tmp_path):
    media = tmp_path / "media.bin"
    media.write_bytes(b"media")
    output = tmp_path / "transcript.md"
    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        task = store.create_remote_task("https://www.douyin.com/video/789", "789")
        task = _to_writing(store, task.task_id, media)
        _markdown(output, video_id="wrong")
        with pytest.raises(ValueError, match="output file"):
            store.complete_task(task.task_id, output)
        assert store.get_task(task.task_id).state == "writing"

        output.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="output file"):
            store.complete_task(task.task_id, output)

        _markdown(output, video_id="789")
        with pytest.raises(ValueError, match="bound to this task"):
            store.complete_task(task.task_id, output)
        store.set_writing_output_path(task.task_id, output)
        store.record_output_integrity(
            task.task_id,
            output,
            hashlib.sha256(output.read_bytes()).hexdigest(),
        )
        completed = store.complete_task(task.task_id, output)
        assert completed.state == "completed"
        assert completed.completed_at is not None
        assert store.is_completed_valid(task.task_id)
        assert store.get_valid_completed_task(task.task_id) == completed

        _markdown(output, video_id="somebody-else")
        assert not store.is_completed_valid(task.task_id)
        assert store.get_valid_completed_task(task.task_id) is None


def test_output_integrity_accepts_frontmatter_larger_than_legacy_read_limit(tmp_path):
    media = tmp_path / "media.bin"
    media.write_bytes(b"media")
    output = tmp_path / "large-metadata.md"
    correction = apply_terminology_dictionary(
        "term",
        [CorrectionRule("rule-1", "term", "fixed", note="\x01" * 20_000)],
        enabled=True,
    )
    archive = json.dumps(
        correction.archive_record(), ensure_ascii=False, separators=(",", ":")
    )
    content = render_transcript_markdown(
        "title",
        "transcript",
        {
            "video_id": "123",
            "terminology_corrections": archive,
        },
    )
    assert len(content.split("\n---\n", maxsplit=1)[0]) > 128 * 1024
    output.write_text(content, encoding="utf-8")
    expected_sha256 = hashlib.sha256(output.read_bytes()).hexdigest()

    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        task = store.create_remote_task("https://www.douyin.com/video/123", "123")
        task = _to_writing(store, task.task_id, media)
        store.set_writing_output_path(task.task_id, output)
        recorded = store.record_output_integrity(
            task.task_id,
            output,
            expected_sha256,
        )

        assert recorded.output_sha256 == expected_sha256


def test_completion_requires_bound_timeline_and_detects_sidecar_mutation(tmp_path):
    media = tmp_path / "media.bin"
    media.write_bytes(b"media")
    output = tmp_path / "transcript.md"
    timeline = tmp_path / "transcript_timeline__10.md"
    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        task = store.create_remote_task(
            "https://www.douyin.com/video/timeline-integrity",
            "timeline-integrity",
            processing_options={"timestamps": True},
        )
        task = _to_writing(
            store, task.task_id, media, timeline_required=True
        )
        _markdown(output, video_id="timeline-integrity")
        store.set_writing_output_path(task.task_id, output)
        store.record_output_integrity(
            task.task_id,
            output,
            hashlib.sha256(output.read_bytes()).hexdigest(),
        )
        with pytest.raises(ValueError, match="timeline file"):
            store.complete_task(task.task_id, output)

        expected_timeline = b"# transcript -- timeline\n"
        store.prepare_timeline_integrity(
            task.task_id,
            timeline,
            hashlib.sha256(expected_timeline).hexdigest(),
        )
        with pytest.raises(ValueError, match="timeline file"):
            store.complete_task(task.task_id, output)

        timeline.write_bytes(expected_timeline)
        completed = store.complete_task(task.task_id, output)
        assert completed.timeline_path == str(timeline.resolve())
        assert completed.timeline_sha256 == hashlib.sha256(expected_timeline).hexdigest()
        assert store.is_completed_valid(task.task_id)

        timeline.write_bytes(b"changed timeline")
        assert not store.is_completed_valid(task.task_id)
        assert store.get_valid_completed_task(task.task_id) is None


def test_local_completion_requires_local_source_association(tmp_path):
    media = tmp_path / "local.wav"
    media.write_bytes(b"media")
    output = tmp_path / "local.md"
    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        task = store.create_local_task(media)
        store.transition(task.task_id, "transcribing")
        store.transition(task.task_id, "writing")
        _markdown(output, source_url="local:/wrong/path")
        with pytest.raises(ValueError, match="output file"):
            store.complete_task(task.task_id, output)
        _markdown(output, source_url=task.source_url)
        with pytest.raises(ValueError, match="bound to this task"):
            store.complete_task(task.task_id, output)
        store.set_writing_output_path(task.task_id, output)
        store.record_output_integrity(
            task.task_id,
            output,
            hashlib.sha256(output.read_bytes()).hexdigest(),
        )
        assert store.complete_task(task.task_id, output).state == "completed"


def test_local_retry_stays_failed_until_original_file_is_validated(tmp_path):
    media = tmp_path / "retry.wav"
    media.write_bytes(b"original media")
    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        task = store.create_local_task(media)
        store.fail_task(task.task_id, "ASR_FAILED", "temporary failure")

        media.unlink()
        retried = store.retry_failed()
        assert len(retried) == 1
        assert retried[0].state == "failed"
        with pytest.raises(FileNotFoundError):
            store.prepare_local_retry(task.task_id, media)
        assert store.get_task(task.task_id).state == "failed"

        media.write_bytes(b"changed media")
        with pytest.raises(ValueError, match="content changed"):
            store.prepare_local_retry(task.task_id, media)
        assert store.get_task(task.task_id).state == "failed"

        media.write_bytes(b"original media")
        prepared = store.prepare_local_retry(task.task_id, media)
        assert prepared.state == "downloaded"
        assert prepared.error_code is None


def test_local_retry_can_atomically_reserve_the_validated_attempt(tmp_path):
    media = tmp_path / "retry-reserved.wav"
    media.write_bytes(b"original media")
    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        task = store.create_local_task(media)
        claimed = store.claim_task(task.task_id, "first-run")
        assert claimed is not None
        store.fail_task(
            task.task_id,
            "ASR_FAILED",
            worker_id="first-run",
            claim_generation=claimed.claim_generation,
        )
        store.retry_failed()

        prepared = store.prepare_local_retry(
            task.task_id, media, worker_id="retry-worker"
        )

        assert prepared.state == "downloaded"
        assert prepared.claimed_by == "retry-worker"
        assert prepared.claim_generation > claimed.claim_generation
        assert prepared.attempt_count == task.attempt_count + 2
        with pytest.raises(ValueError, match="no longer failed"):
            store.prepare_local_retry(
                task.task_id, media, worker_id="racing-retry-worker"
            )


def test_pending_retry_failure_uses_generation_checked_compare_and_set(tmp_path):
    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        task = store.create_remote_task(
            "https://www.douyin.com/video/retry-resolve", "retry-resolve"
        )
        claimed = store.claim_task(task.task_id, "first-run")
        assert claimed is not None
        store.fail_task(
            task.task_id,
            "NETWORK_FAILED",
            worker_id="first-run",
            claim_generation=claimed.claim_generation,
        )
        retried = store.retry_failed(task_id=task.task_id)[0]

        assert not store.fail_unclaimed_retry(
            task.task_id,
            expected_claim_generation=retried.claim_generation - 1,
            error_code="URL_RESOLVE_FAILED",
        )
        assert store.fail_unclaimed_retry(
            task.task_id,
            expected_claim_generation=retried.claim_generation,
            error_code="URL_RESOLVE_FAILED",
            error_message="resolver unavailable",
        )
        failed = store.get_task(task.task_id)
        assert failed is not None
        assert failed.state == "failed"
        assert failed.error_code == "URL_RESOLVE_FAILED"
        assert failed.error_message == "resolver unavailable"


def test_recovery_requires_a_private_output_digest(tmp_path):
    media = tmp_path / "media.bin"
    media.write_bytes(b"media")
    forged = tmp_path / "forged.md"
    authenticated = tmp_path / "authenticated.md"
    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        forged_task = store.create_remote_task(
            "https://www.douyin.com/video/forged", "forged"
        )
        forged_task = _to_writing(store, forged_task.task_id, media)
        store.set_writing_output_path(forged_task.task_id, forged)
        _markdown(forged, video_id="forged")

        trusted_task = store.create_remote_task(
            "https://www.douyin.com/video/trusted", "trusted"
        )
        trusted_task = _to_writing(store, trusted_task.task_id, media)
        store.set_writing_output_path(trusted_task.task_id, authenticated)
        _markdown(authenticated, video_id="trusted")
        store.record_output_integrity(
            trusted_task.task_id,
            authenticated,
            hashlib.sha256(authenticated.read_bytes()).hexdigest(),
        )

        recovered = store.recover_interrupted(
            stale_after_seconds=0, media_validator=lambda _path: True
        )

        assert {result.task_id: result.to_state for result in recovered} == {
            "forged": "downloaded",
            "trusted": "completed",
        }
        assert store.get_task("forged").output_sha256 is None
        assert store.is_completed_valid("trusted")


def test_failures_are_durable_redacted_and_login_required_is_not_retried(tmp_path):
    database = tmp_path / "tasks.sqlite3"
    with TaskStore(database) as store:
        login = store.create_remote_task("https://www.douyin.com/video/login", "login")
        store.fail_task(login.task_id, "LOGIN_REQUIRED", "login required")
        failed = store.create_remote_task("https://www.douyin.com/video/error", "error")
        failed = store.fail_task(
            failed.task_id,
            "NETWORK_ERROR",
            "GET https://media.test/file?X-Amz-Signature=private failed\nCookie: session-secret",
        )
        assert "private" not in failed.error_message
        assert "session-secret" not in failed.error_message

    with TaskStore(database) as reopened:
        assert reopened.get_task("error").state == "failed"
        retried = reopened.retry_failed()
        assert [task.task_id for task in retried] == ["error"]
        assert reopened.get_task("error").state == "pending"
        assert reopened.get_task("error").error_code is None
        assert reopened.get_task("login").state == "failed"
        assert reopened.retry_failed(error_code="LOGIN_REQUIRED") == []
        assert (
            reopened.retry_failed(
                error_code="LOGIN_REQUIRED", include_login_required=True
            )[0].task_id
            == "login"
        )


def test_recovery_reuses_valid_media_and_never_promotes_part_files(tmp_path):
    media = tmp_path / "valid.media"
    media.write_bytes(b"media bytes")
    part = tmp_path / "partial.media.part"
    part.write_bytes(b"partial")
    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        cached = store.create_remote_task("https://www.douyin.com/video/cache", "cache")
        claimed = store.claim_task(cached.task_id, "worker-a")
        assert claimed.state == "resolving"
        store.transition(
            cached.task_id, "downloading", worker_id="worker-a",
            claim_generation=claimed.claim_generation,
        )
        store.transition(
            cached.task_id, "downloaded", worker_id="worker-a",
            claim_generation=claimed.claim_generation, media_path=media
        )
        store.transition(
            cached.task_id, "transcribing", worker_id="worker-a",
            claim_generation=claimed.claim_generation,
        )

        partial = store.create_remote_task(
            "https://www.douyin.com/video/partial", "partial"
        )
        store.transition(partial.task_id, "resolving")
        store.transition(partial.task_id, "downloading", media_path=part)

        results = store.recover_interrupted(stale_after_seconds=0)

        assert {result.task_id: result.to_state for result in results} == {
            "cache": "downloaded",
            "partial": "pending",
        }
        assert store.get_task("cache").media_path == str(media)
        assert store.get_task("cache").claimed_by is None
        assert store.get_task("partial").media_path is None


def test_recovery_validates_media_without_holding_the_write_lock(tmp_path):
    database = tmp_path / "tasks.sqlite3"
    media = tmp_path / "cached.wav"
    media.write_bytes(b"media")
    with TaskStore(database) as setup:
        task = setup.create_remote_task("https://www.douyin.com/video/recovery-lock", "lock")
        setup.transition(task.task_id, "resolving")
        setup.transition(task.task_id, "downloading")
        setup.transition(task.task_id, "downloaded", media_path=media)
        setup.transition(task.task_id, "transcribing")

    entered = Event()
    release = Event()

    def slow_validator(_path: Path) -> bool:
        entered.set()
        if not release.wait(timeout=5):
            raise TimeoutError("test validator was not released")
        return True

    with (
        TaskStore(database, busy_timeout_ms=250) as recovery_store,
        TaskStore(database, busy_timeout_ms=250) as writer,
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        recovery = executor.submit(
            recovery_store.recover_interrupted,
            stale_after_seconds=0,
            media_validator=slow_validator,
        )
        try:
            assert entered.wait(timeout=2)
            created = writer.create_remote_task(
                "https://www.douyin.com/video/during-recovery", "concurrent"
            )
            assert created.state == "pending"
        finally:
            release.set()

        results = recovery.result(timeout=5)

    assert [(item.task_id, item.to_state) for item in results] == [
        ("lock", "downloaded")
    ]


def test_recovery_does_not_clear_a_claim_refreshed_during_media_validation(tmp_path):
    database = tmp_path / "tasks.sqlite3"
    media = tmp_path / "claimed.wav"
    media.write_bytes(b"media")
    with TaskStore(database) as setup:
        task = setup.create_remote_task(
            "https://www.douyin.com/video/recovery-lease", "lease"
        )
        setup.transition(task.task_id, "resolving")
        setup.transition(task.task_id, "downloading")
        setup.transition(task.task_id, "downloaded", media_path=media)
        claimed = setup.claim_task(task.task_id, "worker-a")
        assert claimed is not None
        setup._connection.execute(
            "UPDATE tasks SET claimed_at = ?, updated_at = ? WHERE task_id = ?",
            ("2000-01-01T00:00:00.000+00:00", "2000-01-01T00:00:00.000+00:00", task.task_id),
        )

    entered = Event()
    release = Event()

    def slow_validator(_path: Path) -> bool:
        entered.set()
        if not release.wait(timeout=5):
            raise TimeoutError("test validator was not released")
        return True

    with (
        TaskStore(database, busy_timeout_ms=250) as recovery_store,
        TaskStore(database, busy_timeout_ms=250) as worker_store,
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        recovery = executor.submit(
            recovery_store.recover_interrupted,
            stale_after_seconds=300,
            media_validator=slow_validator,
        )
        try:
            assert entered.wait(timeout=2)
            assert worker_store.heartbeat_claim(
                task.task_id,
                "worker-a",
                claim_generation=claimed.claim_generation,
            )
        finally:
            release.set()

        assert recovery.result(timeout=5) == []
        current = worker_store.get_task(task.task_id)

    assert current is not None
    assert current.state == "downloaded"
    assert current.claimed_by == "worker-a"
    assert current.claimed_at != "2000-01-01T00:00:00.000+00:00"


def test_recovery_fences_old_worker_mutations_even_when_worker_id_is_reused(tmp_path):
    database = tmp_path / "tasks.sqlite3"
    media = tmp_path / "cached.wav"
    media.write_bytes(b"media")
    with TaskStore(database) as store:
        created = store.create_remote_task(
            "https://www.douyin.com/video/recovery-fence", "recovery-fence"
        )
        claimed = store.claim_task(created.task_id, "worker-a")
        assert claimed is not None
        old_generation = claimed.claim_generation
        store.transition(
            created.task_id, "downloading", worker_id="worker-a",
            claim_generation=claimed.claim_generation,
        )
        store.transition(
            created.task_id,
            "downloaded",
            worker_id="worker-a",
            claim_generation=claimed.claim_generation,
            media_path=media,
        )
        store.transition(
            created.task_id, "transcribing", worker_id="worker-a",
            claim_generation=claimed.claim_generation,
        )
        stale_claim = (datetime.now(UTC) - timedelta(seconds=600)).isoformat(
            timespec="milliseconds"
        )
        store._connection.execute(
            "UPDATE tasks SET claimed_at = ? WHERE task_id = ?",
            (stale_claim, created.task_id),
        )

        recovery = store.recover_interrupted(stale_after_seconds=300)
        recovered = store.get_task(created.task_id)

        assert [(item.from_state, item.to_state) for item in recovery] == [
            ("transcribing", "downloaded")
        ]
        assert recovered is not None
        assert recovered.claimed_by is None
        assert recovered.claim_generation > old_generation
        with pytest.raises(RuntimeError, match="no longer owns"):
            store.fail_task(
                created.task_id,
                "LATE_FAILURE",
                worker_id="worker-a",
                claim_generation=old_generation,
            )

        reclaimed = store.claim_task(created.task_id, "worker-a")
        assert reclaimed is not None
        assert reclaimed.claim_generation > recovered.claim_generation
        with pytest.raises(RuntimeError, match="generation has changed"):
            store.fail_task(
                created.task_id,
                "LATE_FAILURE",
                worker_id="worker-a",
                claim_generation=old_generation,
            )

        current = store.get_task(created.task_id)
        assert current is not None
        assert current.state == "downloaded"
        assert current.claimed_by == "worker-a"
        assert not store.heartbeat_claim(
            created.task_id,
            "worker-a",
            claim_generation=old_generation,
        )


def test_worker_writes_and_heartbeats_require_claim_generation(tmp_path):
    database = tmp_path / "tasks.sqlite3"
    with TaskStore(database) as store:
        created = store.create_remote_task(
            "https://www.douyin.com/video/generation-required", "generation-required"
        )
        first_claim = store.claim_task(created.task_id, "reused-worker")
        assert first_claim is not None
        stale_claim = (datetime.now(UTC) - timedelta(seconds=600)).isoformat(
            timespec="milliseconds"
        )
        store._connection.execute(
            "UPDATE tasks SET claimed_at = ? WHERE task_id = ?",
            (stale_claim, created.task_id),
        )
        store.recover_interrupted(stale_after_seconds=300)
        current_claim = store.claim_task(created.task_id, "reused-worker")
        assert current_claim is not None
        assert current_claim.claim_generation > first_claim.claim_generation

        with pytest.raises(ValueError, match="claim_generation is required"):
            store.transition(
                created.task_id, "downloading", worker_id="reused-worker"
            )
        with pytest.raises(ValueError, match="claim_generation is required"):
            store.heartbeat_claim(created.task_id, "reused-worker")

        unchanged = store.get_task(created.task_id)
        assert unchanged is not None
        assert unchanged.state == "resolving"
        assert unchanged.claim_generation == current_claim.claim_generation


def test_recovery_completes_writing_task_when_associated_output_exists(tmp_path):
    media = tmp_path / "media.wav"
    media.write_bytes(b"media")
    output = tmp_path / "transcript.md"
    _markdown(output, video_id="recover")
    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        task = store.create_remote_task(
            "https://www.douyin.com/video/recover", "recover"
        )
        store.transition(task.task_id, "resolving")
        store.transition(task.task_id, "downloading")
        store.transition(task.task_id, "downloaded", media_path=media)
        store.transition(task.task_id, "transcribing")
        store.transition(task.task_id, "writing", output_path=output)
        store.record_output_integrity(
            task.task_id,
            output,
            hashlib.sha256(output.read_bytes()).hexdigest(),
        )

        results = store.recover_interrupted(stale_after_seconds=0)
        recovered = store.get_task("recover")
        assert recovered is not None
        assert store.is_completed_valid("recover")

    assert results[0].to_state == "completed"
    assert results[0].reason == "valid associated output already exists"
    assert recovered.state == "completed"


def test_recovery_requires_the_expected_timeline_sidecar(tmp_path):
    media = tmp_path / "media.wav"
    media.write_bytes(b"media")
    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        def writing_task(task_id: str):
            task = store.create_remote_task(
                f"https://www.douyin.com/video/{task_id}",
                task_id,
                processing_options={"timestamps": True},
            )
            task = _to_writing(store, task.task_id, media, timeline_required=True)
            output = tmp_path / f"{task_id}.md"
            _markdown(output, video_id=task_id)
            store.set_writing_output_path(task.task_id, output)
            store.record_output_integrity(
                task.task_id,
                output,
                hashlib.sha256(output.read_bytes()).hexdigest(),
            )
            return task, output

        valid, valid_output = writing_task("recover-timeline")
        valid_timeline = valid_output.with_name(f"{valid_output.stem}_timeline.md")
        expected_timeline = b"timeline"
        expected_timeline_sha256 = hashlib.sha256(expected_timeline).hexdigest()
        # Match production ordering: persist the expected sidecar binding before
        # the atomic publication, so recovery can validate a crash after publish.
        store.prepare_timeline_integrity(
            valid.task_id, valid_timeline, expected_timeline_sha256
        )
        valid_timeline.write_bytes(expected_timeline)

        no_manifest, _no_manifest_output = writing_task("recover-no-manifest")

        missing, missing_output = writing_task("recover-missing-sidecar")
        missing_timeline = missing_output.with_name(
            f"{missing_output.stem}_timeline.md"
        )
        store.prepare_timeline_integrity(
            missing.task_id, missing_timeline, expected_timeline_sha256
        )

        mismatched, mismatched_output = writing_task("recover-mismatched-sidecar")
        mismatched_timeline = mismatched_output.with_name(
            f"{mismatched_output.stem}_timeline.md"
        )
        store.prepare_timeline_integrity(
            mismatched.task_id, mismatched_timeline, expected_timeline_sha256
        )
        mismatched_timeline.write_bytes(b"tampered timeline")

        recovered = store.recover_interrupted(
            stale_after_seconds=0, media_validator=lambda _path: True
        )
        by_id = {item.task_id: item for item in recovered}
        assert by_id["recover-timeline"].to_state == "completed"
        assert by_id["recover-no-manifest"].to_state == "downloaded"
        assert by_id["recover-missing-sidecar"].to_state == "downloaded"
        assert by_id["recover-mismatched-sidecar"].to_state == "downloaded"
        assert store.is_completed_valid("recover-timeline")
        for task_id in (
            "recover-no-manifest",
            "recover-missing-sidecar",
            "recover-mismatched-sidecar",
        ):
            task = store.get_task(task_id)
            assert task is not None
            assert task.state == "downloaded"
            assert task.output_path is None
            assert task.output_sha256 is None
            assert task.timeline_path is None
            assert task.timeline_sha256 is None
            assert not task.timeline_required


def test_two_connections_cannot_claim_the_same_task(tmp_path):
    database = tmp_path / "tasks.sqlite3"
    setup = TaskStore(database)
    setup.create_remote_task("https://www.douyin.com/video/race", "race")
    setup.close()
    store_a = TaskStore(database)
    store_b = TaskStore(database)
    gate = Barrier(2)

    def claim(store: TaskStore, worker: str):
        gate.wait(timeout=5)
        return store.claim_task("race", worker)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda pair: claim(*pair), [(store_a, "a"), (store_b, "b")]
                )
            )
        winners = [task for task in results if task is not None]
        assert len(winners) == 1
        assert winners[0].attempt_count == 1
        assert store_a.get_task("race").claimed_by in {"a", "b"}
    finally:
        store_a.close()
        store_b.close()
