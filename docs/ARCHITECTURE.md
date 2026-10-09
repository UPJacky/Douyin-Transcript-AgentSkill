# Architecture

`douyin-transcript` is a local-first CLI packaged as a self-contained Agent Skill. The Skill tells an Agent how to invoke the CLI; Python owns URL handling, media capture, download, ASR, task state, and Markdown output. Transcript bodies stay in local files and are not part of normal CLI summaries.

## Runtime flow

```text
CLI / Agent Skill
      │
      ├── doctor, setup, status, retry-failed, cache
      │
      └── transcribe
            ├── config and resource-limit validation
            ├── URL normalization and duplicate grouping, or local-file validation
            ├── durable SQLite task claim and heartbeat
            ├── browser capture for remote URLs
            ├── bounded media download and decode validation
            ├── one lazily loaded, reused local faster-whisper model
            ├── conservative normalization and optional explicit terminology rules
            └── safe-name, atomic Markdown output and short result summary
```

## Module boundaries

| Module | Responsibility |
|---|---|
| `cli.py` | Argument parsing, setup prompts, command dispatch, summaries and exit codes |
| `config.py`, `doctor.py` | Effective paths, bounded processing limits, read-only diagnostics |
| `urls.py`, `capture.py` | Supported Douyin URL parsing, HTTPS host policy, persistent Playwright capture, title/media metadata |
| `downloader.py` | Audio-first/video-fallback retrieval, bounded retries/deadlines, media validation |
| `asr.py`, `models.py` | Lazy CPU INT8 faster-whisper loading, model provenance and bounded segment consumption |
| `normalize.py`, `corrections.py` | Punctuation/paragraph normalization and optional explicit JSON terminology rules |
| `naming.py`, `markdown.py` | Safe collision-resistant names and atomic Markdown writes |
| `tasks.py`, `pipeline.py` | SQLite state, leases/recovery, bounded concurrent downloads, serial ASR orchestration |
| `cache.py` | Preview-first inspection and explicit retention cleanup of application-managed cache files |
| `storage_security.py` | Sensitive path ownership, ancestor and permission checks; private directory creation |

## Data and trust boundaries

- The effective data directory holds the task database, browser profile, and media cache. The `config.toml` file is read from the configuration anchor chosen by `--data-dir`, `DOUYIN_TRANSCRIPT_HOME`, or the platform default before `[paths].data_dir` selects the effective data directory; changing `[paths].data_dir` does not move the config file being read.
- Model lookup checks `<data_dir>/models` first, then `HF_HUB_CACHE`, `HF_HOME/hub`, and the Hugging Face default cache. A model can therefore reside outside the application data directory. Transcript output has its own directory, selected by `--output-dir`, `DOUYIN_TRANSCRIPT_OUTPUT`, `[paths].output_dir`, then the default under the current working directory.
- Remote titles, URLs, local paths, and CLI result fields are data. They must not be interpolated into shell command strings or treated as Agent instructions.
- Network capture/download never bypasses login, CAPTCHA, DRM, or platform access controls. A user can instead provide a lawfully obtained local media file.
- The CLI does not call an LLM API. ASR is local after model setup; setup may download optional dependencies, a model, or Chromium only after the user confirms the displayed operation.
- Cache cleanup defaults to preview. Active task claims and partial downloads are protected by the task-store cleanup guard; deletion revalidates the entry and uses handle-relative deletion on Windows/POSIX where supported.
- Permission checks protect against other-account path replacement under the documented platform policy. They do not defend against the same user, an administrator/root, or every race at pathname-only third-party API boundaries. See `PROJECT_AUDIT_REPORT.md` for residuals.

## Persistent state and concurrency

The SQLite task store records job identity, state, profile, bounded processing-option snapshots, and media path metadata, not transcript text. Each run claims tasks and refreshes leases. Remote downloads are prefetched with a configured concurrency of one or two; ASR remains serial and the model instance is reused within a pipeline. Stale task recovery and retry support interruption without making a failed task look completed.

Output is written to a temporary file and atomically promoted to a unique safe filename. Existing user output is not overwritten by `--force`; reprocessing uses a new collision-safe name.

## Packaging

The installable unit is `skills/douyin-transcript/`: it contains `SKILL.md`, `pyproject.toml`, `uv.lock`, scripts, references, assets, and the complete `src/douyin_transcript` package. Repository-level tests and documentation are not runtime imports. A clean-copy offline smoke test passed locally; a remote GitHub installation and a real Agent-host invocation remain acceptance gates.
