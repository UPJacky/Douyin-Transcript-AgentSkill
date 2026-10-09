# Douyin Transcript

Douyin Transcript is a local-first command-line tool and Agent Skill for turning media you are authorized to process into Markdown transcripts. It accepts Douyin URLs and local audio or video files. Speech recognition runs locally with faster-whisper after you explicitly install an optional ASR model.

The CLI writes transcript text to local Markdown files. Its JSON and quiet summaries report status and file paths without including transcript bodies. An optional, user-supplied terminology dictionary applies literal, case-sensitive replacements; it is disabled unless explicitly selected.

## Validation status

The following reflects the local worktree as checked on 2026-10-09. Mocked or offline results do not establish that a real media or platform workflow works.

| Area | Status |
| --- | --- |
| Windows offline regression | Latest worktree suite on Python 3.11.15: 382 passed, 20 skipped; whole-tree Ruff and sensitive-file scanning passed (2026-10-09). Python 3.12.13 last passed 376 tests with 20 skipped before this round's changes and has not been rerun. Skips include POSIX-only checks and tests requiring symlink creation unavailable on this host. |
| macOS and Linux | Not verified on these operating systems. They are included in the CI configuration, but no remote CI run has been recorded. |
| Real local ASR | Not verified with an authorized sample or downloaded model. Recognition quality and runtime are unknown. |
| Douyin browser capture and download | Not verified with real links, login, or media. No account was used for this validation. |
| Clean installation | After the latest hardening changes, an offline clean copy outside the repository passed locked no-dev installation, `--version`, and direct-URL `--dry-run --json` on Python 3.12. Remote repository installation has not been tested. |
| Agent invocation | The Skill files pass the format validator; an actual conversation-based Agent invocation has not been accepted. |

This is an implementation snapshot, not a release announcement. The project is not yet release-ready. See [the release report](docs/RELEASE_REPORT.md) and [the project audit](docs/PROJECT_AUDIT_REPORT.md) for outstanding verification and remediation items.

## Requirements

- Python 3.11 or 3.12
- [uv](https://docs.astral.sh/uv/)

CI currently pins uv 0.12.7; older versions have not been verified.

Start with the [installation guide](skills/douyin-transcript/references/INSTALL.md) for Windows PowerShell, Command Prompt, macOS, and Linux. From the repository checkout root, basic installation prepares the lightweight CLI. `uv sync --locked` creates or updates `.venv` under the Skill and may download locked dependencies from the configured package index; an Agent must explain these network and filesystem effects and ask before running it:

~~~powershell
uv sync --project .\skills\douyin-transcript --locked
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript doctor --json
~~~

On macOS or Linux, use ./skills/douyin-transcript as the project path. The doctor command is read-only; a setup_required result means optional components are not ready.

### First setup

To install the ASR dependency and download a model, choose one profile:

~~~powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript setup --model balanced
~~~

Balanced uses medium; fast uses small. Setup first displays the requested dependencies, model and destination, then asks for confirmation. Model weights may take hundreds of megabytes or more; actual size and download time vary. To enable URL capture, setup also needs Playwright and Chromium:

~~~powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript setup --browser
~~~

If the page asks for authentication, sign in manually in the opened browser. The tool does not automate sign-in or bypass access controls. Do not use setup's --yes option unless you have reviewed and explicitly accepted its displayed installation and download actions.

## Example commands

Run these from the repository checkout root. Replace paths and URLs with ones you are authorized to use.

~~~powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript doctor --json
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript transcribe --input-file 'D:\Videos\sample.mp4' --output-dir "$env:USERPROFILE\Transcripts" --json
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript transcribe --file .\urls.txt --json
~~~

The first command is read-only. The media commands require the ASR extra and the selected model to be set up. URL capture also requires Playwright and Chromium; authentication, if requested by the page, is manual.

Each item's media validation, download, and ASR share an absolute 7,200-second deadline by default. Adjust it with `--processing-timeout-seconds N` (hard maximum 86,400 seconds). If the deadline expires, the processing child is terminated and an already-created task is marked failed. The loaded ASR model is reused by that child for the current batch.

An illustrative JSON summary has this shape; it contains no transcript text:

~~~json
{"status":"success","total":1,"success":1,"skipped":0,"failed":0,"output_dir":"C:\\Users\\Example\\Transcripts","output_dir_permissions":{"status":"ok","directories":[{"path":"C:\\Users\\Example\\Transcripts","status":"ok","detail":"private output directory"}]},"items":[{"status":"success","title":"Example title","video_id":null,"output_path":"C:\\Users\\Example\\Transcripts\\Example-title.md","error_code":null,"hint":null,"duration_seconds":12.3}]}
~~~

## Data, output, and safety

On Windows, application data uses %LOCALAPPDATA%\douyin-transcript when its ancestor ACL is safe. If that path is unsafe and does not already exist, it falls back to %USERPROFILE%\.local\share\douyin-transcript. An existing unsafe directory stays selected and writes are refused so previous task data is not silently hidden or migrated. Use `doctor --json` to see the effective `data_dir`. macOS uses ~/Library/Application Support/douyin-transcript. Linux uses $XDG_DATA_HOME/douyin-transcript, or ~/.local/share/douyin-transcript when XDG_DATA_HOME is unset. Set DOUYIN_TRANSCRIPT_HOME to choose another data location; the selected directory must have a trusted permission chain.

The default model profile uses medium; the fast profile uses small. Model weights can take substantial disk space and require network access during setup. Resource limits default to one hour of media, 20,000 output segments, and 2,000,000 output characters, with hard caps enforced by the program. See the CLI reference for configurable limits.

`doctor` checks the configured output directory; pass `--output-dir PATH` to inspect a specific target. Set `DOUYIN_TRANSCRIPT_OUTPUT` to choose a persistent output directory through the environment. Selection precedence is `--output-dir`, `DOUYIN_TRANSCRIPT_OUTPUT`, `[paths].output_dir` in `config.toml`, then the default under the current working directory. Dry runs, transcription, and retries also report permissions for the actual output directory. An `unsafe` or `unknown` result is advisory: the command allows intentionally shared folders and never rewrites an existing ACL. JSON summaries include the checked paths and statuses in `output_dir_permissions`; text commands print warnings to stderr.

There are no verified speed claims: transcription time depends on the machine, media, and selected model, and a representative runtime benchmark has not been completed. Completed tasks are normally skipped on repeat. Use `--force` to process again and save a separate file without overwriting the prior transcript. Use `status` to inspect task states and `retry-failed` to requeue failed tasks. New tasks preserve language, timestamps, terminology rules, resource limits, retry count, download concurrency, and output directory for retries. Legacy tasks without a valid options snapshot are skipped by default; pass `--use-current-defaults` to explicitly accept current settings and save them as the retry snapshot. Pass `--output-dir` to intentionally override a saved output path.

Cache inspection is available with cache inspect. Cache cleanup is manual and previews a plan by default; review the paths, then use --apply to delete eligible files. The cleanup skips media referenced by non-completed tasks.

The tool does not bypass login, CAPTCHA, DRM, or access controls. Browser state can retain login cookies. Keep the application data directory private, and do not put transcripts, browser profiles, cookies, signed media URLs, or private media into public repositories or support reports.

The repository does not include a license selection. The repository owner must decide licensing before distribution. See [SECURITY.md](SECURITY.md) for vulnerability reporting guidance.

## FAQ

**Doctor says setup_required.** Run the separate model or browser setup only after reviewing its prompt and accepting the downloads. Doctor itself does not install or download anything.

**A video produces no transcript.** The media needs a decodable audio stream. Check the error and use an authorized local audio/video file if URL capture is unavailable.

**Where is application data stored?** Windows prefers %LOCALAPPDATA%\douyin-transcript and falls back to %USERPROFILE%\.local\share\douyin-transcript only when the first path is unsafe and does not already exist. An existing unsafe directory remains selected and is not modified. `doctor --json` reports the effective path. Set DOUYIN_TRANSCRIPT_HOME to use another location. See the installation guide for macOS and Linux defaults.

**Can I use this to bypass a login or verification page?** No. Authentication is manual, and the tool does not bypass CAPTCHA, DRM, or access controls.

## Contributing and issues

See [CONTRIBUTING.md](CONTRIBUTING.md) for offline development checks and data-handling guidance. For ordinary bugs and questions, use the issue tracker configured by the repository host. Do not put vulnerability details or private media in a public issue; see [SECURITY.md](SECURITY.md).

## Project files

- [Agent Skill](skills/douyin-transcript/SKILL.md)
- [CLI reference](skills/douyin-transcript/references/CLI_REFERENCE.md)
- [Troubleshooting](skills/douyin-transcript/references/TROUBLESHOOTING.md)
- [Installation guide](skills/douyin-transcript/references/INSTALL.md)
- [Changelog](CHANGELOG.md)
