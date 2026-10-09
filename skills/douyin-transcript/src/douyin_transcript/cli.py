"""Command line entry point for douyin-transcript."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import __version__
from .cache import cleanup_media_cache, inspect_media_cache
from .config import ConfigurationError, RuntimePaths, resolve_paths
from .corrections import (
    MAX_TERMINOLOGY_DICTIONARY_BYTES,
    MAX_TERMINOLOGY_RULES,
    CorrectionRule,
)
from .doctor import collect_report, output_directory_permission_status
from .limits import (
    DEFAULT_MAX_MEDIA_DURATION_SECONDS,
    DEFAULT_MAX_OUTPUT_CHARACTERS,
    DEFAULT_MAX_OUTPUT_SEGMENTS,
    validate_resource_limits,
)
from .markdown import strip_control_characters
from .models import model_spec
from .output import ItemResult, exit_code_for_summary, make_summary
from .pipeline import (
    DEFAULT_MAX_PROCESSING_SECONDS,
    HARD_MAX_PROCESSING_SECONDS,
    MAX_URL_BATCH_ITEMS,
    MAX_URL_LENGTH,
    TranscriptionPipeline,
    validate_url_batch,
)
from .storage_security import PrivateStorageError, ensure_private_directory
from .tasks import Task, TaskStore
from .urls import UnsupportedUrlError, resolve_input

MODEL_SETUP_MIN_FREE_BYTES = 2 * 1024**3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="douyin-transcript",
        description="本地优先的抖音口播转写工具；逐字稿只写入本地 Markdown 文件。",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")

    doctor = commands.add_parser("doctor", help="检查运行环境；不会安装或下载")
    doctor.add_argument("--json", action="store_true", help="以 JSON 输出检查结果")
    doctor.add_argument("--data-dir", help="覆盖用户数据目录，仅用于本次检查")
    doctor.add_argument("--output-dir", help="覆盖本次权限检查的 Markdown 输出目录")
    doctor.add_argument("--profile", choices=("balanced", "fast"), default="balanced")

    setup = commands.add_parser("setup", help="在确认后安装运行依赖、模型或 Chromium")
    setup.add_argument("--model", choices=("balanced", "fast"), help="下载 medium 或 small 模型")
    setup.add_argument("--browser", action="store_true", help="安装 Playwright Chromium")
    setup.add_argument("--data-dir", help="模型、任务数据库和浏览器 profile 的根目录")
    setup.add_argument("--yes", action="store_true", help="确认本次显示的安装和下载操作")

    transcribe = commands.add_parser("transcribe", help="转写抖音链接、URL 清单或本地媒体")
    transcribe.add_argument("urls", nargs="*", help="一个或多个 HTTPS 抖音链接")
    transcribe.add_argument("--file", help="每行一个链接的文本文件；支持空行和 # 注释")
    transcribe.add_argument("--input-file", help="本地音频或含音轨的视频文件")
    transcribe.add_argument("--title", help="本地文件的显示标题，或覆盖远端标题")
    transcribe.add_argument("--output-dir", help="Markdown 输出目录")
    transcribe.add_argument("--data-dir", help="用户数据目录；不存放在 Skill 安装目录")
    transcribe.add_argument("--profile", choices=("balanced", "fast"), default="balanced")
    transcribe.add_argument("--language", choices=("zh", "auto"), default="zh")
    transcribe.add_argument(
        "--max-duration-minutes",
        type=_positive_float,
        help=f"本次媒体时长上限（默认 {DEFAULT_MAX_MEDIA_DURATION_SECONDS // 60} 分钟）",
    )
    transcribe.add_argument(
        "--max-output-segments",
        type=_positive_int,
        help=f"本次最多保留的识别分段数（默认 {DEFAULT_MAX_OUTPUT_SEGMENTS}）",
    )
    transcribe.add_argument(
        "--max-output-characters",
        type=_positive_int,
        help=f"本次最多保留的识别字符数（默认 {DEFAULT_MAX_OUTPUT_CHARACTERS}）",
    )
    transcribe.add_argument("--timestamps", action="store_true", help="另存时间轴 Markdown")
    existing_behavior = transcribe.add_mutually_exclusive_group()
    existing_behavior.add_argument(
        "--skip-existing",
        dest="skip_existing",
        action="store_true",
        default=True,
        help="跳过已有有效结果（默认）",
    )
    existing_behavior.add_argument(
        "--force",
        dest="skip_existing",
        action="store_false",
        help="重新转写并另存，不覆盖旧稿",
    )
    transcribe.add_argument(
        "--dry-run", action="store_true", help="解析输入并检查路径，不下载或转写"
    )
    transcribe.add_argument(
        "--max-downloads", type=int, choices=(1, 2), default=2,
        help="媒体下载并发数（1–2，默认 2；ASR 仍串行）",
    )
    transcribe.add_argument(
        "--retry", type=int, choices=(0, 1, 2), default=2,
        help="下载或页面临时失败的重试次数（0–2，默认 2）",
    )
    transcribe.add_argument(
        "--processing-timeout-seconds",
        type=_processing_timeout_seconds,
        default=DEFAULT_MAX_PROCESSING_SECONDS,
        help=(
            "单条媒体从下载/解码校验到 ASR 的总墙钟时限 "
            f"（默认 {DEFAULT_MAX_PROCESSING_SECONDS} 秒，最多 {HARD_MAX_PROCESSING_SECONDS} 秒）"
        ),
    )
    transcribe.add_argument(
        "--terminology-dictionary", help="显式启用 JSON 白名单术语词典",
    )
    transcribe.add_argument("--json", action="store_true", help="只输出不含正文的 JSON 摘要")
    transcribe.add_argument(
        "--quiet", action="store_true", help="简化结果输出；输出目录隐私警告仍会显示"
    )

    status = commands.add_parser("status", help="查看持久化任务状态；不读取逐字稿正文")
    status.add_argument("--json", action="store_true", help="以 JSON 输出任务状态")
    status.add_argument("--data-dir", help="覆盖用户数据目录")

    retry = commands.add_parser("retry-failed", help="将失败任务重新排队并执行")
    retry.add_argument("--limit", type=_nonnegative_int, help="最多重试的任务数")
    retry.add_argument("--data-dir", help="覆盖用户数据目录")
    retry.add_argument("--output-dir", help="Markdown 输出目录")
    retry.add_argument(
        "--processing-timeout-seconds",
        type=_processing_timeout_seconds,
        default=None,
        help=(
            "仅本次重试覆盖任务快照中的总墙钟时限；未指定时恢复原值 "
            f"（旧任务默认 {DEFAULT_MAX_PROCESSING_SECONDS} 秒，"
            f"最多 {HARD_MAX_PROCESSING_SECONDS} 秒）"
        ),
    )
    retry.add_argument(
        "--use-current-defaults",
        action="store_true",
        help="仅对缺少或无效配置快照的旧任务，明确使用当前默认配置重试",
    )
    retry.add_argument("--json", action="store_true", help="只输出不含正文的 JSON 摘要")

    cache = commands.add_parser("cache", help="查看或清理应用自己的媒体缓存")
    cache_commands = cache.add_subparsers(dest="cache_command", required=True)
    cache_inspect = cache_commands.add_parser("inspect", help="列出可识别缓存文件和容量")
    cache_inspect.add_argument("--data-dir", help="覆盖用户数据目录")
    cache_inspect.add_argument("--json", action="store_true", help="以 JSON 输出缓存信息")
    cache_clean = cache_commands.add_parser("clean", help="按容量或保留时间预览/清理缓存")
    cache_clean.add_argument("--data-dir", help="覆盖用户数据目录")
    cache_clean.add_argument("--max-bytes", type=_nonnegative_int, help="目标媒体缓存总字节数")
    cache_clean.add_argument(
        "--max-age-hours",
        type=_nonnegative_int,
        help="删除超过指定小时数的缓存和临时文件",
    )
    cache_clean.add_argument("--apply", action="store_true", help="执行删除；默认只预览")
    cache_clean.add_argument("--json", action="store_true", help="以 JSON 输出清理计划")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _configure_output_encoding()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            return _run_doctor(args)
        if args.command == "setup":
            return _run_setup(args, parser)
        if args.command == "transcribe":
            return _run_transcribe(args)
        if args.command == "status":
            return _run_status(args)
        if args.command == "retry-failed":
            return _run_retry(args)
        if args.command == "cache":
            return _run_cache(args)
        parser.print_help()
        return 0
    except ConfigurationError as exc:
        print(f"CONFIG_INVALID: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(f"INVALID_INPUT: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("CANCELLED: 操作已取消。", file=sys.stderr)
        return 130


def _run_doctor(args: argparse.Namespace) -> int:
    report = collect_report(
        data_dir_override=args.data_dir,
        profile=args.profile,
        output_dir_override=getattr(args, "output_dir", None),
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=True, separators=(",", ":")))
    else:
        print(f"douyin-transcript doctor — {report['overall']}")
        for name, item in report["checks"].items():
            print(f"- {name}: {item['status']} — {item['detail']}")
        print(f"- data_dir: {report['data_dir']}")
    return 0 if report["overall"] == "ready" else 1


def _run_transcribe(args: argparse.Namespace) -> int:
    selected = int(bool(args.urls)) + int(bool(args.file)) + int(bool(args.input_file))
    if selected != 1:
        raise ValueError("请且仅提供一种输入：抖音 URL、--file URL 清单或 --input-file 本地媒体")
    url_values = (
        _read_url_file(Path(args.file))
        if args.file
        else validate_url_batch(args.urls)
        if args.urls
        else None
    )
    paths = resolve_paths(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        max_media_duration_seconds=(
            args.max_duration_minutes * 60 if args.max_duration_minutes is not None else None
        ),
        max_output_segments=args.max_output_segments,
        max_output_characters=args.max_output_characters,
    )
    correction_rules = _read_correction_dictionary(args.terminology_dictionary)
    if args.dry_run:
        return _run_dry_run(args, paths, url_values=url_values)
    output_permissions = _output_permissions_summary([paths.output_dir])
    _warn_output_permissions(output_permissions, as_json=args.json)
    pipeline = TranscriptionPipeline(
        paths,
        profile=args.profile,
        language=args.language,
        timestamps=args.timestamps,
        force=not args.skip_existing,
        max_downloads=args.max_downloads,
        retries=args.retry,
        max_processing_seconds=args.processing_timeout_seconds,
        correction_rules=correction_rules,
        corrections_enabled=bool(args.terminology_dictionary),
    )
    try:
        if args.input_file:
            items = [pipeline.run_local(args.input_file, title=args.title)]
        else:
            items = pipeline.run_urls(url_values or (), title=args.title)
    finally:
        pipeline.close()
    summary = make_summary(items, paths.output_dir)
    _print_summary(
        summary,
        as_json=args.json,
        quiet=args.quiet,
        output_dir_permissions=output_permissions,
        warn_output_permissions=False,
    )
    return exit_code_for_summary(summary)


def _run_dry_run(args: argparse.Namespace, paths, *, url_values: list[str] | None = None) -> int:
    """Resolve and validate inputs without creating dirs or opening media."""
    if args.input_file:
        media_path = Path(args.input_file).expanduser().resolve(strict=False)
        input_status = "ready" if media_path.is_file() else "missing"
        rows = [{"input": str(media_path), "status": input_status}]
    else:
        values = url_values or []
        rows = []
        seen: set[str] = set()
        for value in values:
            try:
                resolved = resolve_input(value)
                duplicate = resolved.video_id in seen
                seen.add(resolved.video_id)
                rows.append({
                    "video_id": resolved.video_id,
                    "url": resolved.canonical_url,
                    "status": "duplicate" if duplicate else "ready",
                })
            except UnsupportedUrlError as exc:
                rows.append({"status": "invalid", "error_code": exc.code, "hint": str(exc)})
    path_checks = {
        "data_dir": _path_writable_without_create(paths.data_dir),
        "output_dir": _path_writable_without_create(paths.output_dir),
    }
    output_permissions = _output_permissions_summary([paths.output_dir])
    result = {
        "status": "ready" if all(row["status"] != "invalid" for row in rows)
        and all(value["status"] == "writable" for value in path_checks.values())
        and all(row["status"] != "missing" for row in rows) else "needs_attention",
        "items": rows,
        "paths": path_checks,
        "output_dir_permissions": output_permissions,
        "note": "dry-run 不会创建目录、下载媒体或启动 ASR；短链接解析可能访问抖音 HTTPS 跳转页。",
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    else:
        for row in rows:
            identity = row.get("video_id") or row.get("input") or row.get("error_code")
            print(f"{row['status']}: {identity}")
        for name, check in path_checks.items():
            print(f"{name}: {check['status']} — {check['path']}")
        _warn_output_permissions(output_permissions, as_json=False)
        print(result["status"])
    return 0 if result["status"] == "ready" else 2


def _path_writable_without_create(path: Path) -> dict[str, str]:
    target = Path(path).expanduser().resolve(strict=False)
    if target.exists():
        if not target.is_dir():
            return {"status": "not_directory", "path": str(target)}
        status = "writable" if os.access(target, os.W_OK) else "read_only"
        return {"status": status, "path": str(target)}
    parent = target.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    if not parent.is_dir():
        return {"status": "invalid_parent", "path": str(target)}
    status = "writable" if os.access(parent, os.W_OK) else "read_only_parent"
    return {"status": status, "path": str(target)}


def _output_directory_permission_entry(path: Path | str) -> dict[str, str]:
    target = Path(path).expanduser().resolve(strict=False)
    return {
        "path": str(target),
        **output_directory_permission_status(target),
    }


def _output_permissions_summary(paths: Sequence[Path | str]) -> dict[str, Any]:
    directories: dict[str, dict[str, str]] = {}
    for path in paths:
        entry = _output_directory_permission_entry(path)
        key = os.path.normcase(entry["path"])
        directories.setdefault(key, entry)
    return _aggregate_output_permissions(list(directories.values()))


def _aggregate_output_permissions(
    entries: list[dict[str, str]],
) -> dict[str, Any]:
    if not entries:
        status = "not_applicable"
    elif any(entry["status"] == "unsafe" for entry in entries):
        status = "unsafe"
    elif any(entry["status"] == "unknown" for entry in entries):
        status = "unknown"
    else:
        status = "ok"
    return {"status": status, "directories": entries}


def _warn_output_permissions(
    report: dict[str, Any], *, as_json: bool
) -> None:
    if as_json:
        return
    for directory in report["directories"]:
        if directory["status"] != "ok":
            print(
                "OUTPUT_DIR_PERMISSIONS: "
                f"{directory['status']} — {directory['path']} — {directory['detail']}",
                file=sys.stderr,
            )


def _read_correction_dictionary(path: str | None) -> tuple[CorrectionRule, ...]:
    if path is None:
        return ()
    dictionary_path = Path(path).expanduser()
    try:
        raw = _read_bounded_regular_file(
            dictionary_path, MAX_TERMINOLOGY_DICTIONARY_BYTES
        )
    except (OSError, ValueError) as exc:
        raise ValueError(f"无法读取 JSON 术语词典：{dictionary_path}") from exc
    if len(raw) > MAX_TERMINOLOGY_DICTIONARY_BYTES:
        raise ValueError("术语词典不得超过 256 KiB")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 JSON 术语词典：{dictionary_path}") from exc
    if not isinstance(payload, list) or len(payload) > MAX_TERMINOLOGY_RULES:
        raise ValueError(
            f"术语词典必须是最多 {MAX_TERMINOLOGY_RULES} 条规则的 JSON 数组"
        )
    rules: list[CorrectionRule] = []
    allowed = {"id", "source", "replacement", "note"}
    for index, item in enumerate(payload, start=1):
        required = {"id", "source", "replacement"}
        if not isinstance(item, dict) or set(item) - allowed or not required <= set(item):
            raise ValueError(f"术语词典第 {index} 条规则字段无效")
        rules.append(
            CorrectionRule(
                item["id"], item["source"], item["replacement"], item.get("note", "")
            )
        )
    return tuple(rules)


def _cache_task_protection(tasks):
    protected = [
        task.media_path
        for task in tasks
        if task.media_path and task.state != "completed"
    ]
    protected.extend(task.local_path for task in tasks if task.local_path)
    protected_video_ids = {
        task.video_id
        for task in tasks
        if task.state == "downloading" and task.video_id and task.claimed_by
    }
    return protected, protected_video_ids


def _run_cache(args: argparse.Namespace) -> int:
    paths = resolve_paths(data_dir=args.data_dir)
    cache_dir = paths.data_dir / "media-cache"
    if not cache_dir.exists():
        result = {"cache_dir": str(cache_dir), "media_bytes": 0, "entries": []}
        if args.json:
            print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        else:
            print(f"媒体缓存目录尚不存在：{cache_dir}")
        return 0
    database = paths.data_dir / "tasks.sqlite3"
    if args.cache_command == "inspect":
        protected: list[str] = []
        protected_video_ids: set[str] = set()
        if database.is_file():
            with TaskStore(database) as store:
                protected, protected_video_ids = _cache_task_protection(store.list_tasks())
        snapshot = inspect_media_cache(
            cache_dir,
            protected_paths=protected,
            protected_video_ids=protected_video_ids,
        )
        result = {
            "cache_dir": str(snapshot.cache_dir),
            "media_bytes": snapshot.media_bytes,
            "protected_media_bytes": snapshot.protected_media_bytes,
            "entries": [
                {"path": str(entry.path), "kind": entry.kind, "size_bytes": entry.size_bytes,
                 "age_seconds": int(entry.age_seconds), "protected": entry.protected}
                for entry in snapshot.entries
            ],
        }
        if args.json:
            print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        else:
            print(f"media_bytes={snapshot.media_bytes} protected={snapshot.protected_media_bytes}")
            for entry in snapshot.entries:
                protected_label = "protected" if entry.protected else ""
                print(
                    f"{entry.kind}: {entry.size_bytes} bytes "
                    f"{protected_label} {entry.path.name}"
                )
        return 0
    cleanup_options = {
        "max_bytes": args.max_bytes,
        "max_age_seconds": (
            args.max_age_hours * 3600 if args.max_age_hours is not None else None
        ),
        "dry_run": not args.apply,
    }
    if args.apply:
        # Plan and scan outside SQLite write transactions. Each identity-checked
        # unlink then coordinates briefly with the matching task row, so a
        # concurrent claim cannot start using the same cache entry mid-delete.
        with TaskStore(database) as store:
            protected, protected_video_ids = _cache_task_protection(store.list_tasks())

            def coordinated_delete(entry, unlink):
                with store.cache_entry_cleanup_guard(entry.path, entry.video_id) as in_use:
                    if in_use:
                        return False
                    return unlink()

            cleanup = cleanup_media_cache(
                cache_dir,
                protected_paths=protected,
                protected_video_ids=protected_video_ids,
                allow_partial_cleanup=True,
                deletion_coordinator=coordinated_delete,
                **cleanup_options,
            )
    else:
        protected: list[str] = []
        protected_video_ids: set[str] = set()
        if database.is_file():
            with TaskStore(database) as store:
                protected, protected_video_ids = _cache_task_protection(store.list_tasks())
        cleanup = cleanup_media_cache(
            cache_dir,
            protected_paths=protected,
            protected_video_ids=protected_video_ids,
            allow_partial_cleanup=True,
            **cleanup_options,
        )
    result = {
        "dry_run": cleanup.dry_run,
        "selected_bytes": cleanup.selected_bytes,
        "remaining_media_bytes": cleanup.remaining_media_bytes,
        "selected_paths": [str(path) for path in cleanup.selected_paths],
        "removed_paths": [str(path) for path in cleanup.removed_paths],
        "skipped_paths": [str(path) for path in cleanup.skipped_paths],
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    else:
        action = "将删除" if cleanup.dry_run else "已删除"
        print(f"{action} {len(cleanup.selected_paths)} 个文件，共 {cleanup.selected_bytes} 字节。")
        if cleanup.dry_run:
            print("确认清理后添加 --apply 执行。")
    return 0


def _run_status(args: argparse.Namespace) -> int:
    paths = resolve_paths(data_dir=args.data_dir)
    database = paths.data_dir / "tasks.sqlite3"
    if not database.is_file():
        tasks = []
    else:
        with TaskStore(database) as store:
            tasks = store.list_tasks()
    rows = [
        {
            "task_id": task.task_id,
            "video_id": task.video_id,
            "title": (
                strip_control_characters(task.title) if task.title is not None else None
            ),
            "state": task.state,
            "profile": task.profile,
            "output_path": task.output_path,
            "error_code": task.error_code,
            "error_message": task.error_message,
        }
        for task in tasks
    ]
    result = {"total": len(rows), "tasks": rows}
    if args.json:
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    else:
        if not rows:
            print("没有已记录的转写任务。")
        for row in rows:
            identity = row["video_id"] or row["task_id"][:20]
            safe_title = strip_control_characters(row["title"] or "(无标题)")
            print(f"{row['state']}: {identity} — {safe_title}")
    return 0


def _run_retry(args: argparse.Namespace) -> int:
    paths = resolve_paths(data_dir=args.data_dir, output_dir=args.output_dir)
    retried: list[Task] = []
    legacy_skipped: list[Task] = []
    legacy_opted_in = 0
    with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
        candidates = store.list_tasks(states=("failed",))
        queued_count = 0
        if args.limit != 0:
            for candidate in candidates:
                if candidate.error_code == "LOGIN_REQUIRED":
                    continue
                options = _retry_processing_options(candidate.processing_options_json)
                if options is None and not args.use_current_defaults:
                    legacy_skipped.append(candidate)
                    continue
                snapshot = None
                if options is None:
                    snapshot = _current_retry_snapshot(
                        paths,
                        max_processing_seconds=(
                            args.processing_timeout_seconds
                            if args.processing_timeout_seconds is not None
                            else DEFAULT_MAX_PROCESSING_SECONDS
                        ),
                    )
                    legacy_opted_in += 1
                elif (
                    args.processing_timeout_seconds is not None
                    or args.output_dir is not None
                ):
                    snapshot = {"schema_version": 2, **options}
                    if args.processing_timeout_seconds is not None:
                        snapshot["max_processing_seconds"] = (
                            args.processing_timeout_seconds
                        )
                    if args.output_dir is not None:
                        snapshot["output_dir"] = str(
                            paths.output_dir.expanduser().resolve(strict=False)
                        )
                queued = store.retry_failed(
                    task_id=candidate.task_id,
                    limit=1,
                    processing_options=snapshot,
                )
                if queued:
                    retried.extend(queued)
                    queued_count += 1
                    if args.limit is not None and queued_count >= args.limit:
                        break
    all_results: list[ItemResult] = [
        ItemResult(
            "skipped",
            title=task.title,
            video_id=task.video_id,
            hint=(
                "LEGACY_CONFIG: 任务没有有效配置快照；添加 "
                "--use-current-defaults 可明确按当前默认值重试。"
            ),
        )
        for task in legacy_skipped
    ]
    if legacy_skipped:
        print(
            f"LEGACY_CONFIG_SKIPPED: {len(legacy_skipped)} 个旧任务未重试；"
            "如接受当前默认配置，请显式传入 --use-current-defaults。",
            file=sys.stderr,
        )
    if legacy_opted_in:
        print(
            "LEGACY_CONFIG: 已按显式 --use-current-defaults 选择当前默认值，"
            f"并将配置快照写回 {legacy_opted_in} 个任务。",
            file=sys.stderr,
        )
    pipelines: dict[str, tuple[TranscriptionPipeline, Any]] = {}
    permission_entries: dict[str, dict[str, str]] = {}
    result_output_dir = paths.output_dir
    for task in retried:
        options = _retry_processing_options(task.processing_options_json)
        if options is None:
            print(
                "LEGACY_CONFIG: 配置快照仍无效；"
                "因显式 --use-current-defaults 使用当前默认配置。",
                file=sys.stderr,
            )
            options = _current_retry_options(
                paths,
                max_processing_seconds=(
                    args.processing_timeout_seconds
                    if args.processing_timeout_seconds is not None
                    else DEFAULT_MAX_PROCESSING_SECONDS
                ),
            )
        output_dir = (
            paths.output_dir
            if args.output_dir is not None
            else Path(options["output_dir"]).expanduser().resolve(strict=False)
        )
        permission_entry = _output_directory_permission_entry(output_dir)
        permission_key = os.path.normcase(permission_entry["path"])
        if permission_key not in permission_entries:
            permission_entries[permission_key] = permission_entry
            _warn_output_permissions(
                {"directories": [permission_entry]}, as_json=args.json
            )
        task_paths = replace(
            paths,
            output_dir=output_dir,
            max_media_duration_seconds=options["max_media_duration_seconds"],
            max_output_segments=options["max_output_segments"],
            max_output_characters=options["max_output_characters"],
        )
        result_output_dir = output_dir
        key = json.dumps(
            {"profile": task.profile, **options},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if key not in pipelines:
            rules = tuple(CorrectionRule(**rule) for rule in options["correction_rules"])
            pipeline = TranscriptionPipeline(
                task_paths,
                profile=task.profile,
                language=options["language"],
                timestamps=options["timestamps"],
                max_media_duration_seconds=options["max_media_duration_seconds"],
                max_output_segments=options["max_output_segments"],
                max_output_characters=options["max_output_characters"],
                max_downloads=options["max_downloads"],
                retries=options["retries"],
                max_processing_seconds=options["max_processing_seconds"],
                correction_rules=rules,
                corrections_enabled=options["correction_rules_enabled"],
            )
            pipelines[key] = (pipeline, task_paths.output_dir)
        pipeline = pipelines[key][0]
        if task.local_path:
            all_results.append(
                pipeline.run_local(
                    task.local_path,
                    title=task.title,
                    retry_task_id=task.task_id,
                )
            )
        else:
            retry_results = pipeline.run_urls([task.source_url], title=task.title)
            if (
                len(retry_results) == 1
                and retry_results[0].status == "failed"
                and retry_results[0].video_id is None
            ):
                # URL resolution runs before the pipeline can claim the queued
                # retry. Restore the durable failed state only if no other
                # process has claimed or advanced this retry generation.
                with TaskStore(paths.data_dir / "tasks.sqlite3") as store:
                    store.fail_unclaimed_retry(
                        task.task_id,
                        expected_claim_generation=task.claim_generation,
                        error_code=retry_results[0].error_code or "URL_RESOLVE_FAILED",
                        error_message=retry_results[0].hint,
                    )
            all_results.extend(retry_results)
    for pipeline, _output_dir in pipelines.values():
        close = getattr(pipeline, "close", None)
        if callable(close):
            close()
    summary = make_summary(all_results, result_output_dir)
    _print_summary(
        summary,
        as_json=args.json,
        quiet=False,
        output_dir_permissions=_aggregate_output_permissions(
            list(permission_entries.values())
        ),
        warn_output_permissions=False,
    )
    return exit_code_for_summary(summary)


def _current_retry_options(
    paths: RuntimePaths,
    *,
    max_processing_seconds: int = DEFAULT_MAX_PROCESSING_SECONDS,
) -> dict[str, Any]:
    return {
        "language": "zh",
        "timestamps": False,
        "max_processing_seconds": max_processing_seconds,
        "max_media_duration_seconds": paths.max_media_duration_seconds,
        "max_output_segments": paths.max_output_segments,
        "max_output_characters": paths.max_output_characters,
        "max_downloads": 2,
        "retries": 2,
        "correction_rules_enabled": False,
        "correction_rules": [],
        "output_dir": str(paths.output_dir.expanduser().resolve(strict=False)),
    }


def _current_retry_snapshot(
    paths: RuntimePaths,
    *,
    max_processing_seconds: int = DEFAULT_MAX_PROCESSING_SECONDS,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        **_current_retry_options(
            paths, max_processing_seconds=max_processing_seconds
        ),
    }


def _retry_processing_options(raw: str) -> dict[str, Any] | None:
    """Validate a stored non-transcript snapshot; None denotes legacy/invalid data."""
    try:
        options = json.loads(raw)
        version_one_fields = {
            "schema_version",
            "language",
            "timestamps",
            "max_media_duration_seconds",
            "max_output_segments",
            "max_output_characters",
            "max_downloads",
            "retries",
            "correction_rules_enabled",
            "correction_rules",
            "output_dir",
        }
        version_two_fields = version_one_fields | {"max_processing_seconds"}
        if not isinstance(options, dict):
            return None
        version = options.get("schema_version")
        if type(version) is not int or version not in {1, 2}:
            return None
        expected = version_one_fields if version == 1 else version_two_fields
        if set(options) != expected:
            return None
        if options["language"] not in {"zh", "auto"}:
            return None
        if not isinstance(options["timestamps"], bool):
            return None
        if not isinstance(options["correction_rules_enabled"], bool):
            return None
        if (
            isinstance(options["max_downloads"], bool)
            or options["max_downloads"] not in {1, 2}
            or isinstance(options["retries"], bool)
            or options["retries"] not in {0, 1, 2}
        ):
            return None
        duration, segments, characters = validate_resource_limits(
            options["max_media_duration_seconds"],
            options["max_output_segments"],
            options["max_output_characters"],
        )
        max_processing_seconds = (
            DEFAULT_MAX_PROCESSING_SECONDS
            if version == 1
            else options["max_processing_seconds"]
        )
        if (
            isinstance(max_processing_seconds, bool)
            or not isinstance(max_processing_seconds, int)
            or not 1 <= max_processing_seconds <= HARD_MAX_PROCESSING_SECONDS
        ):
            return None
        rules = options["correction_rules"]
        if not isinstance(rules, list) or len(rules) > 1000:
            return None
        normalized_rules = []
        for rule in rules:
            if not isinstance(rule, dict) or set(rule) != {
                "rule_id", "source", "replacement", "note"
            }:
                return None
            CorrectionRule(**rule)
            normalized_rules.append(rule)
        output_dir = options["output_dir"]
        if not isinstance(output_dir, str) or not output_dir.strip():
            return None
        return {
            "language": options["language"],
            "timestamps": options["timestamps"],
            "max_processing_seconds": max_processing_seconds,
            "max_media_duration_seconds": duration,
            "max_output_segments": segments,
            "max_output_characters": characters,
            "max_downloads": options["max_downloads"],
            "retries": options["retries"],
            "correction_rules_enabled": options["correction_rules_enabled"],
            "correction_rules": normalized_rules,
            "output_dir": str(Path(output_dir).expanduser().resolve(strict=False)),
        }
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
        return None


def _run_setup(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if not args.model and not args.browser:
        parser.error("setup 至少需要指定 --model balanced|fast 或 --browser")
    paths = resolve_paths(data_dir=args.data_dir)
    project_dir = Path(__file__).resolve().parents[2]
    uv = shutil.which("uv")
    requested_extras: list[str] = []
    actions: list[str] = []
    spec = model_spec(args.model) if args.model else None
    if args.model:
        requested_extras.append("asr")
        actions.append(
            "安装 faster-whisper/PyAV 并下载 "
            f"{spec.size} 模型到 {paths.data_dir / 'models' / spec.size}"
        )
    if args.browser:
        requested_extras.append("browser")
        actions.append("安装 Playwright 依赖及 Chromium 浏览器")
    print("本次 setup 将执行：")
    for action in actions:
        print(f"- {action}")
    if requested_extras:
        print(f"uv executable：{uv or '未找到'}")
        print(f"Python 依赖安装器：uv（锁文件：{project_dir / 'uv.lock'}）")
        print(f"Python 环境目标：{_uv_environment_target(project_dir)}")
        print(f"uv 缓存位置：{_uv_cache_path()}")
        for source in _locked_registry_sources(project_dir):
            print(f"uv.lock 软件包源：{source}")
        for variable in ("UV_DEFAULT_INDEX", "UV_INDEX_URL", "UV_INDEX"):
            value = os.environ.get(variable)
            if value:
                print(f"uv 自定义源 {variable}：{_safe_endpoint(value)}")
    if spec:
        print(
            "模型来源：Hugging Face Hub "
            f"{spec.repository}@{spec.revision} "
            f"(https://huggingface.co/{spec.repository}/tree/{spec.revision})"
        )
        hf_endpoint = os.environ.get("HF_ENDPOINT")
        print(
            "Hugging Face 下载端点："
            + (_safe_endpoint(hf_endpoint) if hf_endpoint else "https://huggingface.co")
            + ("（HF_ENDPOINT 覆盖）" if hf_endpoint else "（默认；可由 HF_ENDPOINT 覆盖）")
        )
        print(f"模型保存位置：{paths.data_dir / 'models' / spec.size}")
    if args.browser:
        print("Chromium 来源：Playwright 下载服务（可由 PLAYWRIGHT_DOWNLOAD_HOST 等环境变量覆盖）")
        for variable in ("PLAYWRIGHT_DOWNLOAD_HOST", "PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST"):
            value = os.environ.get(variable)
            if value:
                print(f"Playwright 自定义下载源 {variable}：{_safe_endpoint(value)}")
        print(f"Chromium 保存位置：{_playwright_browser_target()}")
    disk_targets: list[tuple[str, Path, int | None]] = []
    if requested_extras:
        disk_targets.extend(
            (
                ("Python 环境", _uv_environment_path(project_dir), None),
                ("uv 缓存", _uv_cache_path(), None),
            )
        )
    if spec:
        disk_targets.append(
            (
                "模型目录",
                paths.data_dir / "models" / spec.size,
                MODEL_SETUP_MIN_FREE_BYTES,
            )
        )
    if args.browser:
        browser_path = _playwright_browser_path()
        if browser_path is not None:
            disk_targets.append(("Chromium 目录", browser_path, None))
    if not _preflight_setup_disk_space(disk_targets):
        return 2
    if uv is None:
        print("找不到 uv；请先安装 uv，再重新运行 setup。", file=sys.stderr)
        return 2
    if args.model and args.browser:
        print(
            "磁盘估算：模型权重可能占数百 MB 至约 1.5 GB；"
            "Chromium 及运行依赖的大小随平台/版本变化。"
        )
    elif args.model:
        print("磁盘估算：模型权重可能占数百 MB 至约 1.5 GB，另有 Python 运行依赖。")
    else:
        print("磁盘估算：Chromium 和 Playwright 运行依赖的大小随平台/版本变化。")
    print("磁盘预检只是当前可用空间快照；安装过程仍可能因空间变化而失败。")
    print("网络和磁盘使用仅在确认后开始。")
    if not args.yes and not _confirm("继续？输入 yes 确认："):
        print("已取消；未安装依赖或下载模型。")
        return 1

    if args.model:
        try:
            ensure_private_directory(paths.data_dir)
            ensure_private_directory(paths.data_dir / "models" / spec.size)
        except PrivateStorageError as exc:
            print(f"PRIVATE_STORAGE_UNSAFE: {exc}", file=sys.stderr)
            return 2

    # A user may run setup in separate steps (model, then browser).  Keep the
    # other already-installed optional extra in this project-local environment.
    sync_command = [uv, "sync", "--inexact", "--project", str(project_dir), "--locked"]
    for extra in requested_extras:
        sync_command.extend(("--extra", extra))
    completed = subprocess.run(sync_command, check=False)
    if completed.returncode:
        print(f"依赖安装失败（退出码 {completed.returncode}）。", file=sys.stderr)
        return completed.returncode

    if args.browser:
        completed = subprocess.run(
            [sys.executable, "-P", "-m", "playwright", "install", "chromium"],
            check=False,
        )
        if completed.returncode:
            print(f"Chromium 安装失败（退出码 {completed.returncode}）。", file=sys.stderr)
            return completed.returncode

    if args.model:
        destination = paths.data_dir / "models" / spec.size
        if not _preflight_setup_disk_space(
            [("模型目录（依赖安装后）", destination, MODEL_SETUP_MIN_FREE_BYTES)],
            failure_message=(
                "模型下载前可用空间不足或无法验证；依赖已安装，模型未下载。"
            ),
        ):
            return 2
        try:
            from huggingface_hub import snapshot_download

            spec = model_spec(args.model)
            snapshot_download(
                repo_id=spec.repository,
                revision=spec.revision,
                local_dir=str(destination),
            )
            from .models import is_complete_model, write_model_provenance

            if not is_complete_model(destination):
                print("模型下载结束，但必需文件缺失或无效。", file=sys.stderr)
                return 3
            write_model_provenance(destination, spec)
        except Exception as exc:
            print(f"模型准备失败（{type(exc).__name__}）。", file=sys.stderr)
            return 3
    print("setup 完成。运行 `douyin-transcript doctor` 检查状态。")
    return 0


def _safe_endpoint(value: str) -> str:
    """Show a configured download/index host without leaking URL credentials."""
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        if parsed.scheme and hostname:
            if ":" in hostname:
                hostname = f"[{hostname}]"
            port = f":{parsed.port}" if parsed.port else ""
            return f"{parsed.scheme}://{hostname}{port}"
    except ValueError:
        pass
    return "已配置自定义地址（为保护凭据不回显）"


def _locked_registry_sources(project_dir: Path) -> list[str]:
    try:
        lock_text = (project_dir / "uv.lock").read_text(encoding="utf-8")
    except OSError:
        return ["无法读取 uv.lock 中的 registry；安装仍会由 uv 按配置处理"]
    sources = sorted(
        {
            _safe_endpoint(value)
            for value in re.findall(r'registry = "([^\"]+)"', lock_text)
        }
    )
    return sources or ["uv.lock 未声明 registry；安装仍会由 uv 按配置处理"]


def _uv_environment_target(project_dir: Path) -> str:
    target = _uv_environment_path(project_dir)
    if os.environ.get("UV_PROJECT_ENVIRONMENT"):
        return str(target)
    note = "（uv 项目默认环境；若当前激活环境被 uv 采用，以 uv 实际选择为准）"
    return str(target) + note


def _uv_environment_path(project_dir: Path) -> Path:
    configured = os.environ.get("UV_PROJECT_ENVIRONMENT")
    if configured:
        target = Path(configured).expanduser()
        if not target.is_absolute():
            target = project_dir / target
        return target.resolve(strict=False)
    return project_dir / ".venv"


def _uv_cache_path() -> Path:
    configured = os.environ.get("UV_CACHE_DIR")
    if configured:
        return Path(configured).expanduser().resolve(strict=False)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "uv" / "cache"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "uv"
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "uv"


def _playwright_browser_path() -> Path | None:
    configured = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if configured == "0":
        return None
    if configured:
        return Path(configured).expanduser().resolve(strict=False)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "ms-playwright"


def _playwright_browser_target() -> str:
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH") == "0":
        return "Playwright hermetic cache（PLAYWRIGHT_BROWSERS_PATH=0，位于 Python 环境内）"
    target = _playwright_browser_path()
    assert target is not None
    return str(target)


def _preflight_setup_disk_space(
    targets: Sequence[tuple[str, Path, int | None]],
    *,
    failure_message: str = "磁盘空间不足或无法验证；没有安装依赖、创建数据目录或下载文件。",
) -> bool:
    failed = False
    for label, target, minimum_free in targets:
        probe = target.expanduser()
        while not probe.exists() and probe.parent != probe:
            probe = probe.parent
        try:
            free_bytes = shutil.disk_usage(probe).free
        except OSError as exc:
            print(
                f"磁盘预检失败：{label} {target} 无法检查 "
                f"（{type(exc).__name__}），setup 已停止。",
                file=sys.stderr,
            )
            failed = True
            continue
        free_gib = free_bytes / (1024**3)
        line = f"磁盘预检：{label} {target}，可用 {free_gib:.1f} GiB"
        if minimum_free is not None:
            required_gib = minimum_free / (1024**3)
            line += f"（建议至少 {required_gib:.0f} GiB）"
            if free_bytes < minimum_free:
                line += "；空间不足"
                failed = True
        print(line)
    if failed:
        print(failure_message, file=sys.stderr)
    return not failed


def _read_url_file(path: Path) -> list[str]:
    max_bytes = 1024 * 1024
    try:
        payload = _read_bounded_regular_file(path, max_bytes)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"无法读取 URL 清单：{path}") from exc
    if len(payload) > max_bytes:
        raise ValueError(f"URL 清单不得超过 {max_bytes} 字节")
    try:
        lines = payload.decode("utf-8-sig").splitlines()
    except UnicodeError as exc:
        raise ValueError(f"无法读取 URL 清单：{path}") from exc
    values: list[str] = []
    for line_number, line in enumerate(lines, start=1):
        if len(line) > MAX_URL_LENGTH:
            raise ValueError(
                f"URL 清单第 {line_number} 行超过 {MAX_URL_LENGTH} 个字符"
            )
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            values.append(stripped)
            if len(values) > MAX_URL_BATCH_ITEMS:
                raise ValueError(f"URL 批次最多支持 {MAX_URL_BATCH_ITEMS} 条（包含重复链接）")
    return validate_url_batch(values)


def _read_bounded_regular_file(path: Path, max_bytes: int) -> bytes:
    """Read a bounded regular file without blocking on a POSIX FIFO."""
    if os.name == "nt" and not path.is_file():
        raise ValueError("input path is not a regular file")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if os.name == "posix":
        flags |= getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("input path is not a regular file")
        if os.name == "posix" and hasattr(os, "O_NONBLOCK"):
            import fcntl

            descriptor_flags = fcntl.fcntl(descriptor, fcntl.F_GETFL)
            fcntl.fcntl(descriptor, fcntl.F_SETFL, descriptor_flags & ~os.O_NONBLOCK)
        chunks = bytearray()
        while len(chunks) < max_bytes + 1:
            chunk = os.read(descriptor, min(64 * 1024, max_bytes + 1 - len(chunks)))
            if not chunk:
                break
            chunks.extend(chunk)
        return bytes(chunks)
    finally:
        os.close(descriptor)


def _print_summary(
    summary: Any,
    *,
    as_json: bool,
    quiet: bool,
    output_dir_permissions: dict[str, Any] | None = None,
    warn_output_permissions: bool = True,
) -> None:
    if as_json:
        result = summary.to_dict()
        if output_dir_permissions is not None:
            result["output_dir_permissions"] = output_dir_permissions
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        return
    if output_dir_permissions is not None and warn_output_permissions:
        _warn_output_permissions(output_dir_permissions, as_json=False)
    for item in summary.items:
        if quiet:
            if item.status == "success" and item.output_path:
                print(item.output_path)
            elif item.status == "failed":
                print(f"{item.error_code or 'FAILED'}: {item.hint or '处理失败'}", file=sys.stderr)
            continue
        if item.status == "success":
            identity = strip_control_characters(item.title or item.video_id or "本地媒体")
            print(f"SUCCESS: {identity} -> {item.output_path}")
        elif item.status == "skipped":
            identity = strip_control_characters(item.title or item.video_id or "任务")
            print(f"SKIPPED: {identity} -> {item.output_path}")
        else:
            print(f"FAILED: {item.error_code or 'FAILED'}: {item.hint or '处理失败'}")
    if quiet:
        counts = summary.to_dict()
        print(
            f"{summary.status}: total={counts['total']} success={counts['success']} "
            f"skipped={counts['skipped']} failed={counts['failed']} "
            f"output_dir={summary.output_dir}"
        )
    else:
        print(f"{summary.status}: total={len(summary.items)} output_dir={summary.output_dir}")


def _confirm(prompt: str) -> bool:
    try:
        response = input(prompt)
    except (EOFError, OSError):
        return False
    return response.strip().casefold() in {"yes", "y"}


def _nonnegative_int(value: str) -> int:
    try:
        result = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("必须是非负整数") from None
    if result < 0:
        raise argparse.ArgumentTypeError("必须是非负整数")
    return result


def _positive_int(value: str) -> int:
    result = _nonnegative_int(value)
    if result == 0:
        raise argparse.ArgumentTypeError("必须是正整数")
    return result


def _processing_timeout_seconds(value: str) -> int:
    result = _positive_int(value)
    if result > HARD_MAX_PROCESSING_SECONDS:
        raise argparse.ArgumentTypeError(
            f"不得超过 {HARD_MAX_PROCESSING_SECONDS} 秒"
        )
    return result


def _positive_float(value: str) -> float:
    try:
        result = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("必须是正数") from None
    if not 0 < result <= 240:
        raise argparse.ArgumentTypeError("必须在 0 到 240 分钟之间")
    return result


def _configure_output_encoding() -> None:
    """Make subprocess output predictable for Agent and JSON consumers on Windows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (OSError, ValueError):
                continue
