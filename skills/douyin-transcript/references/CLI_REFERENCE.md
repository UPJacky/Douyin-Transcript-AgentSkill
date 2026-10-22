# CLI reference

Every command runs from the Skill's self-contained project directory:

```text
uv run --project <skill-directory> --locked --no-sync douyin-transcript <command>
```

## `doctor`

`doctor [--json] [--data-dir PATH] [--output-dir PATH] [--profile balanced|fast]` reports Python, ASR, decoder, model, browser, browser isolation, configured paths, permissions, and free space. It does not install dependencies, download models, or create directories. `--output-dir` checks the exact directory selected for a planned run. Permission checks appear as `data_dir_permissions`, `task_database_permissions`, `browser_profile_permissions`, and `media_cache_permissions`; `unsafe` or `unknown` storage blocks the corresponding capability. The implicit `<data_dir>/output` default is rejected at pipeline startup when its permission status is `unsafe` or `unknown`. Explicit output paths remain advisory so users can intentionally select a shared folder; existing permissions are never rewritten. `capabilities.local_transcription` and `capabilities.douyin_urls` are reported separately. Personal URL capture reports top-level `capture_mode=personal` and `checks.browser_isolation.status=not_used`. `capabilities.douyin_urls=ready` requires local ASR dependencies, Playwright/Chromium and usable private storage; it means environment readiness, not that a page is accessible or capture has succeeded. No administrator WFP service is used, and the browser has the current account's network access.

The config anchor is selected by `--data-dir`, then `DOUYIN_TRANSCRIPT_HOME`, then the platform default. The program reads `<config-anchor>/config.toml` before applying its `[paths]` values. `[paths].data_dir` selects task state and cache storage; it does not move the config file. Output directory selection follows this precedence: explicit `--output-dir`, `DOUYIN_TRANSCRIPT_OUTPUT`, `[paths].output_dir` in the selected config anchor `config.toml`, then `<data_dir>/output`. A valid retry snapshot preserves its saved output directory unless `retry-failed --output-dir PATH` is passed; schema 1/2 snapshots with unsafe or unknown saved output permissions are skipped before requeue unless that explicit override is supplied.

## `setup`

- `setup --model balanced|fast` installs the ASR extra and downloads the selected model.
- Model repository revisions and their upstream provenance are recorded in [`MODEL_PROVENANCE.md`](MODEL_PROVENANCE.md); setup passes the pinned commit as the Hugging Face download revision.
- `setup --browser` installs the Playwright extra and Chromium.
- `--data-dir PATH` selects the application data root.
- `--yes` accepts the exact installation/download actions printed by the command.

Model setup can consume substantial disk and network resources. Do not run it without the user's confirmation.

## `login`

`login [--data-dir PATH]` opens Douyin in the dedicated visible Chromium profile under the current ordinary account. The user completes login manually and closes the window to save profile state; then use `transcribe <original-URL> --force --max-downloads 1 --json` to rerun only the intended failed target. Login has a bounded wait and does not automate credentials, CAPTCHA, DRM, or access controls. Login and URL capture take the same nonblocking OS lock for the normalized data directory, across threads, client instances, and processes. If another login or capture is using that directory, the command returns `CAPTURE_BUSY` promptly; wait for it to finish and retry. Different data directories have independent locks. `--dry-run` does not create or acquire a lock.

## `transcribe`

URL tasks use the current Windows ordinary account and the application's dedicated persistent Chromium profile. Normal tasks and `retry-failed` use the same personal capture path. Its data-directory lock stays held through browser use and media download; a persistent lock file alone does not mean that it is occupied.

Choose exactly one input form:

- `transcribe URL [URL ...]`
- `transcribe --file URLS.txt`
- `transcribe --input-file MEDIA`

Options include `--title`, `--output-dir`, `--data-dir`, `--profile balanced|fast`, `--language zh|auto`, `--timestamps`, `--skip-existing` (default), `--force`, `--json`, and `--quiet`. `--skip-existing` and `--force` are mutually exclusive; `--force` reruns the requested task and writes a collision-safe new output file. It can explicitly requeue that failed remote target, including `LOGIN_REQUIRED`; other failed tasks remain unchanged.

- `--dry-run` checks the supplied input form, data/output path writability, and reports output-directory privacy (`ok`, `unsafe`, or `unknown`) without creating directories, making network requests, downloading media, or starting ASR. The privacy status is advisory and does not change the dry-run exit status. A local media file can be ready when it exists and paths are writable. A direct URL can be syntactically `valid`; a short link is `resolution_required` and is resolved only during the actual task. URL dry-run reports `url_capture.status=not_checked` and never proves page access or capture readiness.
- Personal URL mode uses `--max-downloads 1`; capture, download and ASR are serial. Do not overlap commands using the same browser profile. `--retry 0|1|2` controls download and temporary page capture retries.
- `--processing-timeout-seconds N` sets one absolute deadline per item across media validation, remote download, and ASR. Default: 7,200 seconds; maximum: 86,400 seconds. The decoder and model run in a reusable child process; timeout terminates that child and reports `PROCESSING_TIMEOUT`.
- Resource limits default to 3,600 media seconds, 20,000 output segments, and 2,000,000 output characters. Override one run with `--max-duration-minutes`, `--max-output-segments`, or `--max-output-characters`; hard maxima are 240 minutes, 100,000 segments, and 10,000,000 characters. Persistent values use `[limits]` keys `max_media_duration_seconds`, `max_output_segments`, and `max_output_characters` in the selected config anchor `config.toml`.
- Decoder validation disables PyAV secondary resource opens. HLS playlists that require separate segments are unsupported; provide a self-contained media file.
- `--terminology-dictionary PATH` explicitly enables a UTF-8 JSON whitelist. The file must be a JSON array of objects with `id`, `source`, and `replacement`, plus optional `note`. Matches are literal and case-sensitive. Markdown metadata stores the ruleset hash and aggregate counts of matched rules and replacements; it omits rule IDs, source/replacement strings, notes, and per-rule counts. A hash can still be compared with a known dictionary. Full rules are stored in the protected local task database for retry. The dictionary is off when this option is absent. Use `--force` to rerun an already completed task after changing the dictionary.

Example dictionary:

```json
[
  {"id": "approved-01", "source": "插屏", "replacement": "插屏广告", "note": "人工确认的术语"}
]
```

JSON contains only summary metadata and never contains transcript body text. For `transcribe` and `retry-failed`, `status=success` and exit code 0 mean the CLI completed the raw ASR/output stage; the summary also declares `result_scope=raw_asr_only` and `llm_review_status=not_performed_by_cli`. The CLI does not call the Agent model. When the request includes model proofreading, the Agent Skill must save and verify a separate reviewed file before reporting the end-to-end request complete. Transcription and retry summaries include a top-level `output_dir_permissions` object with an aggregate status and the checked directories. A retry batch that restores tasks from multiple saved output directories reports `output_dir: null`; each item's `output_path` and `output_dir_permissions.directories` identify its actual destination. Text summaries label this case `output_dir=多个目录`. Text mode prints `OUTPUT_DIR_PERMISSIONS` warnings to stderr for `unsafe` or `unknown` paths, including when `--quiet` is set. Exit codes are 0 for raw ASR success, 4 for a partial batch, 5 for a failed batch, and 2 for invalid command/config input.

## `review-sidecar`

`review-sidecar --raw-file RAW.md [--data-dir PATH]` saves an Agent-reviewed plain-text body from one UTF-8 JSON object read on stdin. Input is bounded to 12 MB plus small JSON framing allowance, decoded strictly as UTF-8, and duplicate keys are rejected:

```json
{"reviewed_body":"校对后的简体中文正文使用自然标点，便于阅读。\n\n另起一段继续说明。"}
```

The command does not call a model and treats `reviewed_body` as opaque text: it does not convert or validate Simplified/Traditional Chinese or add, remove, or validate punctuation. Follow the canonical Skill's Chinese script and punctuation policy, supply a readable body with natural punctuation and blank-line paragraph breaks, and inspect the saved transcript section before reporting completion. The command requires the raw file and its parent directory to pass the private-storage check, and rejects symlink/reparse or non-regular inputs without changing permissions. It preserves the raw file and frontmatter, replaces the ASR notice with the explicit model-review/no-listening notice, and requires at least one blank-line paragraph break for bodies of at least 300 characters. It escapes Markdown syntax, atomically creates the first available `.reviewed.md` sibling, never replaces an existing file, and returns `status=sidecar_saved`, `output_path`, and `task_binding`. If a matching private task database exists, it binds path and SHA-256 metadata to the exact completed raw attempt; transcript text is never stored. These structural checks do not prove the Agent reviewed the transcript or that corrections are acoustically accurate.

`bind-review-sidecar --raw-file RAW.md --reviewed-file REVIEWED.md [--data-dir PATH]` registers an existing reviewed sibling. It rejects a path/hash mismatch, non-private artifact, mismatched task frontmatter, or missing model-only review notice. `task_binding=registered` means only that the raw and review artifacts are durably associated; it is not evidence of acoustic review or user acceptance. Modification time is never used to choose among candidates.

## `status` and `retry-failed`

- `status [--json] [--data-dir PATH]` keeps the existing `state` and `output_path` meanings and adds:
  - `review_status`: `not_reviewed`, `valid`, `missing`, `changed`, or `unverifiable`. The latest registry entry by `(created_at, review_id)` is checked; an invalid latest entry is reported as-is, with no fallback to an older review.
  - `reviewed_output_path`: the reviewed file path only when the current raw file and that review are both private, within size bounds, and match their registered hashes; otherwise `null`.
  - `review_scope`: the registered review scope, such as `model_text_review_unheard`. Registration proves file association, not listening or acoustic accuracy.

  JSON remains a metadata summary and never includes transcript content. Text output separates `原稿完成` from `校对稿已关联（文本校对，未听审）` and labels missing, changed, or uncheckable files explicitly. `completed` continues to mean only that the raw transcript task completed.
- `retry-failed [--limit N] [--data-dir PATH] [--output-dir PATH] [--processing-timeout-seconds N] [--use-current-defaults] [--json]` requeues failed tasks, except `LOGIN_REQUIRED` failures, which require user action first. A valid saved options snapshot restores the original settings, including the processing timeout. If a valid schema 1/2 snapshot's saved output permissions are `unsafe` or `unknown`, it remains failed and returns `OUTPUT_PATH_UNSAFE` before requeue; explicitly pass `--output-dir` to select and save a new destination. Passing `--processing-timeout-seconds` explicitly overrides and saves that value. Snapshot schema v1 remains compatible with its 7,200-second timeout; tasks without a valid snapshot are skipped by default. `--use-current-defaults` explicitly selects and persists current settings for those legacy tasks.

## `cache`

- `cache inspect [--data-dir PATH] [--json]` lists recognized application media-cache files and protected task references.
- `cache clean [--data-dir PATH] [--max-bytes N] [--max-age-hours N] [--apply] [--json]` previews the cleanup plan by default. Specify at least one retention limit; add `--apply` only after reviewing the listed paths. Cleanup skips media referenced by non-completed tasks and only handles recognized files directly under the application's `media-cache` directory.
- Remote media is retained in the application cache for retry/reuse. V1 does not automatically delete it after transcription; use `cache inspect` and the preview-first `cache clean` command to manage disk usage.
