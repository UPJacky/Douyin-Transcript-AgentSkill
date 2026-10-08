"""Convenience wrapper; use the installed CLI for normal operation."""

from douyin_transcript.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["doctor", *__import__("sys").argv[1:]]))
