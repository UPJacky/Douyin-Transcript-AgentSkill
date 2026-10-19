# Douyin Transcript

Douyin Transcript is a command-line tool and Agent Skill for turning authorized local audio/video or Douyin URLs into Markdown transcripts for personal Windows use. URL capture uses the existing ordinary account and a dedicated Chromium profile, with one task at a time. Three distinct authorized URLs passed capture, download, local ASR, current-default-model text proofreading and registration of separate reviewed files. The raw files are preserved; acoustic review remains unverified. The two new videos use video-ID filenames because no distinct short title was available. See [current delivery status](docs/CURRENT_DELIVERY_STATUS.md). Speech recognition runs locally with faster-whisper after you explicitly install an optional ASR model. Once the user requests or approves model proofreading, the Agent Skill uses the calling Agent's configured/default model to fix clear ASR errors and add Chinese punctuation, saving a separate `.reviewed.md` file. The Agent task is complete only after that reviewed file has been saved and checked. The review places the transcript body in the Agent model context and may send it to the model provider; disclose this data flow before the first review. Users can request local-only processing to skip review, in which case the output remains an unreviewed raw transcript.

The CLI writes transcript text to local Markdown files. Its JSON and quiet summaries report status and file paths without including transcript bodies. An optional, user-supplied terminology dictionary applies literal, case-sensitive replacements; it is disabled unless explicitly selected. Markdown metadata stores a ruleset hash and aggregate counts only, without rule IDs, source/replacement text, notes, or per-rule counts. The hash may still be matched against a known dictionary. Full rules remain in the protected local task database for retries.

## Scope

- The official support target is Windows 11 x64 with Python 3.11 or 3.12. macOS and Linux are not supported.
- Local audio/video transcription runs with faster-whisper. Initial setup may download locked dependencies or a selected model from the configured sources.
- Personal URL capture uses visible Chromium and does not provide OS network isolation. Doctor's URL ready status checks dependencies and paths; it does not prove that a URL can be captured.
- After the user requests or approves proofreading, the Agent Skill can use the calling Agent's default model and save a separate reviewed Markdown file. The transcript body enters that model context; disclose the data flow before the first review. Users can choose local-only processing.

## Requirements

- Python 3.11 or 3.12
- [uv](https://docs.astral.sh/uv/)

CI currently pins uv 0.12.7; older versions have not been verified.

Start with the [installation guide](skills/douyin-transcript/references/INSTALL.md) for supported Windows installation. It also contains compatibility notes for unsupported macOS and Linux environments. From the repository checkout root, basic installation prepares the lightweight CLI. `uv sync --locked` creates or updates `.venv` under the Skill and may download locked dependencies from the configured package index; an Agent must explain these network and filesystem effects and ask before running it:

~~~powershell
uv sync --project .\skills\douyin-transcript --locked
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript doctor --json
~~~

For compatibility checks only, macOS or Linux commands use ./skills/douyin-transcript as the project path. These platforms are unsupported. The doctor command is read-only; a setup_required result means optional components are not ready.

### First setup

To install the ASR dependency and download a model, choose one profile:

~~~powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript setup --model balanced
~~~

Balanced uses medium; fast uses small. Setup first displays the requested dependencies, model and destination, then asks for confirmation. Model weights may take hundreds of megabytes or more; actual size and download time vary. For personal URL capture, use `doctor --json` to identify missing browser dependencies and run the authorized `setup --browser` flow when needed. No administrator WFP service is required.

If authentication is required, run `douyin-transcript login` with the same command prefix and data directory, sign in manually, and close the browser window to save profile state. Then use `transcribe <original-URL> --force --max-downloads 1 --json` with that prefix to rerun only the intended failed target. The tool does not automate sign-in or bypass access controls. Do not use setup's --yes option unless you have reviewed and explicitly accepted its displayed installation and download actions.

## Example commands

Run these from the repository checkout root. Use only media you are authorized to process.

~~~powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript doctor --json
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript transcribe --input-file "$env:USERPROFILE\Videos\sample.mp4" --output-dir "$env:USERPROFILE\Transcripts" --json
~~~

The first command is read-only. Local-media transcription requires the ASR extra and the selected model. Personal mode reports `capture_mode=personal` and `checks.browser_isolation.status=not_used`; `capabilities.douyin_urls=ready` indicates local environment readiness only. Process authorized URLs with `transcribe <URL> --max-downloads 1 --json`, using the same command prefix. Authentication remains manual.

Each item's media validation, download, and ASR share an absolute 7,200-second deadline by default. Adjust it with `--processing-timeout-seconds N` (hard maximum 86,400 seconds). If the deadline expires, the processing child is terminated and an already-created task is marked failed. The loaded ASR model is reused by that child for the current batch.

An illustrative JSON summary has this shape; it contains no transcript text:

~~~json
{"status":"success","result_scope":"raw_asr_only","llm_review_status":"not_performed_by_cli","total":1,"success":1,"skipped":0,"failed":0,"output_dir":"<output-dir>","output_dir_permissions":{"status":"ok","directories":[{"path":"<output-dir>","status":"ok","detail":"private output directory"}]},"items":[{"status":"success","title":"Example title","video_id":null,"output_path":"<output-file>","error_code":null,"hint":null,"duration_seconds":12.3}]}
~~~

For transcription and retry commands, `status=success` and exit code 0 mean the CLI finished only the raw ASR/output stage. `result_scope=raw_asr_only` and `llm_review_status=not_performed_by_cli` make that scope explicit. The CLI does not call an LLM; complete an authorized Agent Skill review and verify the `.reviewed.md` output before reporting the end-to-end task complete.

## Data, output, and safety

On Windows, application data uses %LOCALAPPDATA%\douyin-transcript when its ancestor ACL is safe. If that path is unsafe and does not already exist, it falls back to %USERPROFILE%\.local\share\douyin-transcript. An existing unsafe directory stays selected and writes are refused so previous task data is not silently hidden or migrated. Use `doctor --json` to see the effective `data_dir`. macOS uses ~/Library/Application Support/douyin-transcript. Linux uses $XDG_DATA_HOME/douyin-transcript, or ~/.local/share/douyin-transcript when XDG_DATA_HOME is unset. Set `DOUYIN_TRANSCRIPT_HOME` to choose another configuration anchor and, unless overridden by `[paths].data_dir`, the effective data location. `--data-dir` takes precedence when selecting the anchor. The config file is read from `<anchor>/config.toml`; `[paths].data_dir` changes where task state and caches live, but does not move that config file. The selected directory must have a trusted permission chain.

The default model profile uses medium; the fast profile uses small. Model weights can take substantial disk space and require network access during setup. Resource limits default to one hour of media, 20,000 output segments, and 2,000,000 output characters, with hard caps enforced by the program. See the CLI reference for configurable limits.

`doctor` checks the configured output directory; pass `--output-dir PATH` to inspect a specific target. Set `DOUYIN_TRANSCRIPT_OUTPUT` to choose a persistent output directory through the environment. Selection precedence is `--output-dir`, `DOUYIN_TRANSCRIPT_OUTPUT`, `[paths].output_dir` in the selected config anchor `config.toml`, then `<data_dir>/output`. The implicit default inherits the application's private data-directory permissions and processing stops if those permissions are unsafe or unknown. Explicit output paths may intentionally be shared; the command reports their permissions without rewriting an existing ACL. Dry runs, transcription, and retries report permissions for the actual output directory. JSON summaries include the checked paths and statuses in `output_dir_permissions`; text commands print warnings to stderr.

There are no verified speed claims: transcription time depends on the machine, media, and selected model, and a representative runtime benchmark has not been completed. Completed tasks are normally skipped on repeat. Use `--force` to process again and save a separate file without overwriting the prior transcript. Use `status` to inspect task states and `retry-failed` to requeue failed tasks. New tasks preserve language, timestamps, terminology rules, resource limits, retry count, download concurrency, and output directory for retries. Legacy tasks without a valid options snapshot are skipped by default; pass `--use-current-defaults` to explicitly accept current settings and save them as the retry snapshot. Pass `--output-dir` to intentionally override a saved output path. Valid schema 1/2 snapshots whose saved output permissions are unsafe or unknown are skipped unless `--output-dir` explicitly selects a new destination; see the [CLI reference](skills/douyin-transcript/references/CLI_REFERENCE.md).

Cache inspection is available with cache inspect. Cache cleanup is manual and previews a plan by default; review the paths, then use --apply to delete eligible files. The cleanup skips media referenced by non-completed tasks.

The tool does not bypass login, CAPTCHA, DRM, or access controls. Browser state can retain login cookies. Keep the application data directory private, and do not put transcripts, browser profiles, cookies, signed media URLs, or private media into public repositories or support reports.

The project license has not been approved; do not treat this repository as granting a reuse license for its original material. Third-party components retain their own license and notice terms. The planned initial distribution is source only; it does not bundle wheels, models, browsers, or prebuilt binaries. See [SECURITY.md](SECURITY.md) for vulnerability reporting guidance.

## FAQ

**Doctor says setup_required.** Run the separate model or browser setup only after reviewing its prompt and accepting the downloads. Doctor itself does not install or download anything.

**A video produces no transcript.** The media needs a decodable audio stream. Check the error and use an authorized local audio/video file if URL capture is unavailable.

**Where is application data stored?** Windows prefers %LOCALAPPDATA%\douyin-transcript and falls back to %USERPROFILE%\.local\share\douyin-transcript only when the first path is unsafe and does not already exist. An existing unsafe directory remains selected and is not modified. `doctor --json` reports the effective path. Set DOUYIN_TRANSCRIPT_HOME to use another location. The installation guide documents macOS and Linux paths for compatibility checks; those platforms are unsupported.

**Can I use this to bypass a login or verification page?** No. Authentication is manual, and the tool does not bypass CAPTCHA, DRM, or access controls.

## Contributing and issues

See [CONTRIBUTING.md](CONTRIBUTING.md) for offline development checks and data-handling guidance. For ordinary bugs and questions, use the issue tracker configured by the repository host. Do not put vulnerability details or private media in a public issue; see [SECURITY.md](SECURITY.md).

## Project files

- [Agent Skill](skills/douyin-transcript/SKILL.md)
- [CLI reference](skills/douyin-transcript/references/CLI_REFERENCE.md)
- [Troubleshooting](skills/douyin-transcript/references/TROUBLESHOOTING.md)
- [Installation guide](skills/douyin-transcript/references/INSTALL.md)
