"""Fail CI if Git-visible files contain sensitive artifacts or obvious secrets."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

_FORBIDDEN_DIRECTORIES = {
    "browser-profile",
    "browser_profile",
    "cache",
    "media-cache",
    "media_cache",
    "models",
    "output",
    "douyin-transcripts",
}
_FORBIDDEN_SUFFIXES = {
    ".aac",
    ".aiff",
    ".amr",
    ".avi",
    ".db",
    ".key",
    ".flac",
    ".m4a",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".mpg",
    ".mpeg",
    ".ogg",
    ".opus",
    ".part",
    ".pem",
    ".sqlite",
    ".sqlite3",
    ".wav",
    ".webm",
}
_MODEL_WEIGHT_SUFFIXES = {
    ".bin",
    ".engine",
    ".gguf",
    ".onnx",
    ".pth",
    ".pt",
    ".safetensors",
    ".tflite",
}
_SECRET_FILENAMES = {"cookies.txt", "cookies.json", "cookie.txt", "cookie.json"}
_MAX_TEXT_FILE_BYTES = 2 * 1024 * 1024
_SECRET_PATTERNS = (
    ("private-key material", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "GitHub access token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{30,})\b"),
    ),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    (
        "credential assignment",
        re.compile(
            r"(?i)\b(?:access_token|refresh_token|client_secret|sessionid|csrf_token)"
            r"\s*[:=]\s*[\"']?[A-Za-z0-9._=\-]{16,}"
        ),
    ),
)


def path_violations(paths: list[str]) -> list[tuple[str, str]]:
    """Return forbidden path diagnostics without reading file contents."""
    violations: list[tuple[str, str]] = []
    for name in paths:
        path = PurePosixPath(name.replace("\\", "/"))
        directory_parts = {part.casefold() for part in path.parts[:-1]}
        suffix = path.suffix.casefold()
        basename = path.name.casefold()
        reason = None
        if directory_parts & _FORBIDDEN_DIRECTORIES:
            reason = "sensitive data directory"
        elif suffix in _MODEL_WEIGHT_SUFFIXES:
            reason = "model weight or inference artifact"
        elif suffix in _FORBIDDEN_SUFFIXES:
            reason = "sensitive media, database, key, or partial file"
        elif basename in _SECRET_FILENAMES:
            reason = "browser cookie file"
        elif basename == ".env" or (basename.startswith(".env.") and basename != ".env.example"):
            reason = "environment file"
        elif basename.endswith(".md.tmp"):
            reason = "temporary transcript file"
        if reason:
            violations.append((name, reason))
    return violations


def content_violations(name: str, content: str) -> list[tuple[str, str]]:
    """Return high-confidence credential indicators, never the matched value."""
    found = [reason for reason, pattern in _SECRET_PATTERNS if pattern.search(content)]
    return [(name, reason) for reason in found]


def git_visible_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        check=False,
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError("git ls-files failed; cannot verify sensitive repository files")
    return [
        item.decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    ]


def scan_repository(root: Path) -> list[tuple[str, str]]:
    """Inspect Git-visible names and UTF-8 text files under ``root``."""
    paths = git_visible_paths(root)
    violations = path_violations(paths)
    for name in paths:
        candidate = root / Path(name)
        try:
            if candidate.is_symlink():
                violations.append((name, "symbolic link cannot be content-scanned"))
                continue
            if not candidate.is_file():
                violations.append((name, "not a regular file; content cannot be scanned"))
                continue
            if candidate.stat().st_size > _MAX_TEXT_FILE_BYTES:
                violations.append((name, "exceeds content scan size limit"))
                continue
            raw = candidate.read_bytes()
        except OSError:
            violations.append((name, "unable to inspect Git-visible file"))
            continue
        if b"\0" in raw:
            violations.append((name, "binary file requires explicit review"))
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            violations.append((name, "non-UTF-8 file requires explicit review"))
            continue
        violations.extend(content_violations(name, text))
    return violations


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    try:
        violations = scan_repository(root)
    except (OSError, RuntimeError) as exc:
        print(f"Sensitive-file check failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    if violations:
        for name, reason in violations:
            print(f"Sensitive-file check failed: {name}: {reason}", file=sys.stderr)
        print("Matched credential values are never displayed.", file=sys.stderr)
        return 1
    print("Sensitive-file check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
