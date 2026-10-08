"""Command line entry point for douyin-transcript."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from . import __version__
from .doctor import collect_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="douyin-transcript",
        description="本地优先的抖音口播转写工具。当前阶段提供环境检查；转写功能尚未实现。",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")

    doctor = commands.add_parser(
        "doctor",
        help="检查 Python、模型、浏览器和数据目录；不会安装或下载",
    )
    doctor.add_argument("--json", action="store_true", help="以 JSON 输出检查结果")
    doctor.add_argument("--data-dir", help="覆盖用户数据目录，仅用于本次检查")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "doctor":
        report = collect_report(data_dir_override=args.data_dir)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"douyin-transcript doctor — {report['overall']}")
            for name, item in report["checks"].items():
                print(f"- {name}: {item['status']} — {item['detail']}")
            print(f"- data_dir: {report['data_dir']}")
        return 0 if report["overall"] == "ready" else 1

    parser.print_help()
    return 0
