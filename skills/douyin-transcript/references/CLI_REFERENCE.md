# CLI reference

Every command runs from the Skill's self-contained project directory:

```text
uv run --project <skill-directory> --locked --no-sync douyin-transcript <command>
```

## `doctor`

`doctor [--json] [--data-dir PATH] [--output-dir PATH] [--profile balanced|fast]` reports Python, ASR, decoder, model, browser, configured paths, permissions, and free space. It does not install dependencies, download models, or create directories. `--output-dir` checks the exact directory selected for a planned run. Permission checks appear as `data_dir_permissions`, `task_database_permissions`, `browser_profile_permissions`, and `media_cache_permissions`; `unsafe` or `unknown` storage blocks the corresponding capability. `output_dir_permissions` is advisory: it reports whether the selected output directory or its nearest existing parent appears shared, but does not block transcription because users may intentionally choose a shared output folder. Existing permissions are never rewritten. `capabilities.local_transcription` and `capabilities.douyin_urls` are reported separately.

Output directory selection follows this precedence: explicit `--output-dir`, `DOUYIN_TRANSCRIPT_OUTPUT`, `[paths].output_dir` in `<data-dir>/config.toml`, then the default `douyin-transcripts/output` directory under the current working directory. `DOUYIN_TRANSCRIPT_HOME` selects the data directory that contains `config.toml`.

## `setup`

- `setup --model balanced|fast` installs the ASR extra and downloads the selected model.
- Model repository revisions and their upstream provenance are recorded in [`MODEL_PROVENANCE.md`](MODEL_PROVENANCE.md); setup passes the pinned commit as the Hugging Face download revision.
- `setup --browser` installs the Playwright extra and Chromium.
- `--data-dir PATH` selects the application data root.
- `--yes` accepts the exact installation/download actions printed by the command.

Model setup can consume substantial disk and network resources. Do not run it without the user's confirmation.

## `transcribe`

Choose exactly one input form:

- `transcribe URL [URL ...]`
- `transcribe --file URLS.txt`
- `transcribe --input-file MEDIA`

Options include `--title`, `--output-dir`, `--data-dir`, `--profile balanced|fast`, `--language zh|auto`, `--timestamps`, `--skip-existing` (default), `--force`, `--json`, and `--quiet`. `--skip-existing` and `--force` are mutually exclusive; `--force` reruns the task and writes a collision-safe new output file.

- `--dry-run` resolves inputs, checks data/output path writability, and reports output-directory privacy (`ok`, `unsafe`, or `unknown`) without creating directories, downloading media, or starting ASR. The privacy status is advisory and does not change the dry-run exit status. Short-link resolution can make a bounded HTTPS request to Douyin.
- `--max-downloads 1|2` controls the bounded media download queue; ASR stays serial. `--retry 0|1|2` controls download and temporary page capture retries.
- `--processing-timeout-seconds N` sets one absolute deadline per item across media validation, remote download, and ASR. Default: 7,200 seconds; maximum: 86,400 seconds. The decoder and model run in a reusable child process; timeout terminates that child and reports `PROCESSING_TIMEOUT`.
- Resource limits default to 3,600 media seconds, 20,000 output segments, and 2,000,000 output characters. Override one run with `--max-duration-minutes`, `--max-output-segments`, or `--max-output-characters`; hard maxima are 240 minutes, 100,000 segments, and 10,000,000 characters. Persistent values use `[limits]` keys `max_media_duration_seconds`, `max_output_segments`, and `max_output_characters` in `<data-dir>/config.toml`.
- Decoder validation disables PyAV secondary resource opens. HLS playlists that require separate segments are unsupported; provide a self-contained media file.
- `--terminology-dictionary PATH` explicitly enables a UTF-8 JSON whitelist. The file must be a JSON array of objects with `id`, `source`, and `replacement`, plus optional `note`. Matches are literal, case-sensitive, and recorded as a ruleset hash and applied-rule counts in Markdown metadata. The dictionary is off when this option is absent. Use `--force` to rerun an already completed task after changing the dictionary.

Example dictionary:

```json
[
  {"id": "approved-01", "source": "插屏", "replacement": "插屏广告", "note": "人工确认的术语"}
]
```

JSON contains only summary metadata and never contains transcript body text. Transcription and retry summaries include a top-level `output_dir_permissions` object with an aggregate status and the checked directories; text mode prints `OUTPUT_DIR_PERMISSIONS` warnings to stderr for `unsafe` or `unknown` paths, including when `--quiet` is set. Exit codes are 0 for success, 4 for a partial batch, 5 for a failed batch, and 2 for invalid command/config input.

## `status` and `retry-failed`

- `status [--json] [--data-dir PATH]` displays persisted task state without reading transcript contents.
- `retry-failed [--limit N] [--data-dir PATH] [--output-dir PATH] [--processing-timeout-seconds N] [--use-current-defaults] [--json]` requeues failed tasks, except `LOGIN_REQUIRED` failures, which require user action first. A valid saved options snapshot restores the original settings, including the processing timeout. Passing `--output-dir` or `--processing-timeout-seconds` explicitly overrides and saves that value. Snapshot schema v1 remains compatible with its 7,200-second timeout; tasks without a valid snapshot are skipped by default. `--use-current-defaults` explicitly selects and persists current settings for those legacy tasks.

## `cache`

- `cache inspect [--data-dir PATH] [--json]` lists recognized application media-cache files and protected task references.
- `cache clean [--data-dir PATH] [--max-bytes N] [--max-age-hours N] [--apply] [--json]` previews the cleanup plan by default. Specify at least one retention limit; add `--apply` only after reviewing the listed paths. Cleanup skips media referenced by non-completed tasks and only handles recognized files directly under the application's `media-cache` directory.
- Remote media is retained in the application cache for retry/reuse. V1 does not automatically delete it after transcription; use `cache inspect` and the preview-first `cache clean` command to manage disk usage.
