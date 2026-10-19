# Changelog

This changelog describes the current implementation in the local worktree. It does not indicate that a package or repository release has been published.

## Unreleased — implementation version 0.1.0

- Added a command-line interface for read-only diagnostics, setup, transcription, task status, failed-task retries, and media-cache inspection or cleanup.
- Added local audio/video transcription. Douyin URL capture remains disabled and fails closed until an authenticated administrator-managed isolation broker is integrated and verified; installing a browser or signing in does not enable it.
- Added Markdown transcript output and optional separate timeline output. JSON summaries contain task metadata and paths, not transcript bodies.
- Added an Agent Skill proofreading step: after user authorization, the calling Agent's configured/default model corrects clear ASR errors, checks suspicious terms, adds Chinese punctuation, and saves a separate `.reviewed.md` while preserving the CLI raw transcript. Glossary or token/frequency checks may flag candidates but never trigger blind replacements. The body enters the Agent model context and may be sent to its provider.
- Added opt-in literal terminology replacement through a UTF-8 JSON dictionary.
- Added bounded media duration and transcript output limits, URL batch/input limits, bounded download concurrency, and configurable retries.
- Bounded browser capture's retained audio/video candidate count and URL/header sizes to cap per-page state and downstream media attempts.
- If navigation yields no media candidate immediately, observe response events for up to 2 seconds in 200 ms intervals, stopping as soon as an approved candidate arrives and always respecting the capture deadline.
- Bound page title/author/date extraction in the browser, and inspect login prompts with a bounded text scan that returns only a boolean instead of the full page body.
- Stream cache-directory scans and check cancellation and the shared deadline before handling each entry, avoiding a full pre-deadline sort/materialization of cached paths.
- Recheck the shared processing deadline immediately before full decoding of cached media.
- Added persistent task state, duplicate-task handling, and cache cleanup previews that protect media referenced by non-completed tasks.
- Added explicit `--skip-existing` behavior, mutually exclusive with `--force`, and documented the V1 retained-cache cleanup policy.
- Added persisted page-duration checks for downloaded and cached media, bounded cache-entry size/deadline checks, browser DNS deadlines, and redacted candidate error summaries.
- Changed the general ASR default to omit domain-specific prompting; callers can still provide an explicit prompt through the API.
- Added bounded, non-transcript processing-option snapshots so new failed tasks can retry with their original language, timestamp, terminology, resource-limit, download, timeout, and output settings. Legacy tasks without a valid snapshot are skipped unless the user explicitly selects current settings.
- Hardened retries of valid schema 1/2 snapshots: unsafe or unknown saved output permissions now require an explicit `--output-dir` before the task is requeued, and that destination is saved in the refreshed snapshot.
- Added private-permission checks for application-owned data storage and read-only environment diagnostics.
- Added a uv lockfile, CI configuration, Skill metadata and references, model provenance documentation, and local verification coverage.
- Added fictional JSON/Markdown output examples, setup and troubleshooting FAQs, cache-retention guidance, and privacy-conscious GitHub issue forms.
- Hardened configuration path validation and doctor diagnostics: explicit empty paths are rejected, invalid configuration errors remain specific, and doctor avoids probing an unknown output target.
- Reduced terminology-correction metadata written to Markdown to a ruleset fingerprint and aggregate counts; the fingerprint's comparability to a known dictionary remains documented.
- Added a generator for the complete locked-dependency SPDX inventory; package licenses remain unasserted until individually verified.
- Improved mixed-directory retry summaries and redacted URL paths, sensitive headers, and signed query values from persisted and displayed errors.

## Known release gaps

- A real authorized ASR run has measured processing time, but transcript quality has not been checked against the audio by a human listener. One Agent-default-model proofread was performed; it is not an acoustic quality result.
- Real Douyin capture, authentication, redirects, and media download have not been verified.
- macOS/Linux and remote CI results have not been verified.
- Clean remote installation and a fresh target-Agent-host discovery/invocation with data-flow acceptance have not been accepted.
- Project license remains unapproved: the owner could not confirm authority to license all original contributions. No project reuse grant is made until rights and a license are established.
- Legacy failed tasks created before processing-option snapshots are skipped by default. Passing `--use-current-defaults` explicitly accepts current settings and saves them as the retry snapshot; new tasks restore their saved options automatically. See the project audit for details.
- Regression and cross-account verification of the legacy output-path retry guard remain open. Unsafe or unknown saved destinations are blocked until the operator explicitly provides `--output-dir`.
