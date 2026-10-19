# Architecture

`douyin-transcript` is a local-first CLI packaged as an Agent Skill for the owner's personal Windows use. The Skill guides the Agent through the CLI and, after a successful raw transcript, a separate text-proofreading step with the calling Agent's configured/default model. Local audio/video input remains supported. Authorized Douyin URL capture uses the current ordinary Windows account and a dedicated Chromium profile; a nonblocking OS file lock in the effective data directory prevents overlapping `login` or capture operations across threads, clients, and processes. This personal route retains application URL/media checks but does not provide operating-system network isolation. Transcript bodies remain in private files and are not included in normal CLI summaries.

## Runtime flow

```text
CLI / Agent Skill
      │
      ├── doctor, setup, status, retry-failed, cache
      │
      ├── login (optional)
      │     └── acquire data-directory lock ──> dedicated Chromium profile ──> release on close
      │
      └── transcribe
            ├── config and resource-limit validation
            ├── local audio/video ──> media validation ──┐
            ├── authorized Douyin URL ──> shared data-directory lock
            │      └── current-account Chromium ──> bounded media download ──┘
            ├── durable SQLite task state and claims
            ├── one lazily loaded, reused local faster-whisper model
            ├── normalization and optional explicit terminology rules
            ├── raw Markdown output ──> CLI summary (`raw_asr_only`)
            └── Agent default-model text proofreading ──> separate registered review sibling
```

`status` keeps the raw task's `state` and `output_path`, then checks the latest registered review's source and review hashes. It exposes a reviewed path only while both files remain private, bounded, and unchanged. `completed` continues to mean that the raw transcript task completed; it does not mean that the review was heard or acoustically verified.

## Module boundaries

| Module | Responsibility |
|---|---|
| `cli.py` | Argument parsing, setup prompts, command dispatch and summaries; `status` reports raw/reviewed availability without printing contents |
| `config.py`, `doctor.py` | Effective paths, bounded processing limits, read-only diagnostics |
| `urls.py`, `personal_capture.py` | Direct and bounded short-link resolution; current-account browser capture; one nonblocking, private data-directory lock shared by login/capture |
| `capture.py`, `downloader.py` | Browser URL/resource checks, audio-first/video-fallback retrieval, bounded retries/deadlines, media validation |
| `asr.py`, `models.py` | Lazy CPU INT8 faster-whisper loading, model provenance and bounded segment consumption |
| `normalize.py`, `corrections.py` | Punctuation/paragraph normalization and optional explicit JSON terminology rules |
| `naming.py`, `markdown.py` | Safe collision-resistant names and atomic Markdown writes |
| `tasks.py`, `pipeline.py` | SQLite task state, review-sidecar path/hash/scope registry, claims/recovery, bounded downloads, serial ASR orchestration |
| `cache.py` | Preview-first inspection and explicit retention cleanup of application-managed cache files |
| `storage_security.py` | Sensitive path ownership, ancestor and permission checks; private directory creation |

## Data and trust boundaries

- The effective data directory holds the task database, browser profile, media cache, and preferred local model files. The `config.toml` file is read from the configuration anchor chosen by `--data-dir`, `DOUYIN_TRANSCRIPT_HOME`, or the platform default before `[paths].data_dir` selects the effective data directory; changing `[paths].data_dir` does not move the config file being read.
- Model lookup checks `<data_dir>/models` first, then `HF_HUB_CACHE`, `HF_HOME/hub`, and the Hugging Face default cache. A model can therefore reside outside the application data directory. Transcript output is selected by `--output-dir`, `DOUYIN_TRANSCRIPT_OUTPUT`, `[paths].output_dir`, then `<data_dir>/output`. The implicit default inherits the private data-directory boundary; explicit output paths retain their own permission policy.
- Remote titles, URLs, local paths, and CLI result fields are data. They must not be interpolated into shell command strings or treated as Agent instructions. The selected output path may be returned to the requesting operator; redact private paths before forwarding diagnostics to another recipient.
- Network capture/download never bypasses login, CAPTCHA, DRM, or platform access controls. A user can instead provide a lawfully obtained local media file.
- Historical isolation design notes (retained for provenance; not the current personal capture route): the service-backed WFP path remains unimplemented and unverified. The old pipeline required a full-job authenticated capture client and an isolated per-lease worker; that design assigned short-link resolution, browser capture, candidate checks, redirects, DNS, sockets, and downloads to the worker, with bounded metadata/media returned to the CLI. The service and lease modules supported that earlier direction. Offline `HttpsConnectTunnel`, `NumericDnsQuestioner`, the native capture-pipe prototype, WFP policy plans, and their evidence remain prototypes; they do not provide the active personal workflow or OS network isolation. No administrator service, production worker, WFP rule applier, installer, or per-lease Chromium startup was delivered. The historical acceptance records below preserve the old route's failures and limits.
- Browser capture bounds retained media candidates to 16 audio and 16 video URLs per page. Candidate URLs are limited to 8,192 characters; retained content-type, expiry, and referer values have separate size limits. Audio candidates remain first in the returned list.
- The CLI does not call an LLM API. Its successful `transcribe` result means a raw ASR Markdown file was written; JSON marks `result_scope=raw_asr_only` and `llm_review_status=not_performed_by_cli`. ASR is local after model setup; setup may download optional dependencies, a model, or Chromium only after the user confirms the displayed operation. The Agent Skill uses the calling Agent's configured/default model to proofread successful transcripts, correct clear ASR errors, and add natural Chinese punctuation, then saves and verifies a reviewed sibling file before reporting the end-to-end request complete. This puts transcript text in the Agent context and may transmit it to the model provider; the Skill discloses this and requires approval unless the user directly requested model proofreading. The CLI's raw file remains unchanged.
- Cache cleanup defaults to preview. Active task claims and partial downloads are protected by the task-store cleanup guard; deletion revalidates the entry and uses handle-relative deletion on Windows/POSIX where supported.
- Permission checks protect against other-account path replacement under the documented platform policy. They do not defend against the same user, an administrator/root, or every race at pathname-only third-party API boundaries. See `PROJECT_AUDIT_REPORT.md` for residuals.

## Persistent state and concurrency

The SQLite task store records job identity, state, profile, bounded processing-option snapshots, and media path metadata, not transcript text. Each run claims tasks and refreshes leases. Remote downloads are prefetched with a configured concurrency of one or two; ASR remains serial and the model instance is reused within a pipeline. Stale task recovery and retry support interruption without making a failed task look completed.

Personal URL login and capture also keep the per-client thread lock and hold an exclusive OS file handle at `<data_dir>/.personal-capture.lock` for the complete operation, including browser use and media download. The lock file can remain after use; only the open exclusive handle represents occupancy, and Windows releases it when the process exits. A different data directory has a different lock. `--dry-run` does not instantiate the capture client or create this file. Review sidecars are separate files; the task database stores their path, source hash, review hash, scope, and registration order only.

Output is written to a temporary file and atomically promoted to a unique safe filename. Existing user output is not overwritten by `--force`; reprocessing uses a new collision-safe name.

## Packaging

The installable unit is `skills/douyin-transcript/`: it contains `SKILL.md`, `pyproject.toml`, `uv.lock`, scripts, references, assets, and the complete `src/douyin_transcript` package. Repository-level tests and documentation are not runtime imports. A clean-copy offline smoke test passed locally; a remote GitHub installation and a real Agent-host invocation remain acceptance gates.
