#!/usr/bin/env sh
set -eu
skill_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec uv run --project "$skill_dir" --locked --no-sync douyin-transcript "$@"
