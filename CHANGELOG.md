# Changelog

This changelog describes the current implementation in the local worktree. It does not indicate that a package or repository release has been published.

## Unreleased — implementation version 0.1.0

- Added a command-line interface for read-only diagnostics, setup, transcription, task status, failed-task retries, and media-cache inspection or cleanup.
- Added local audio/video transcription and Douyin URL capture flows. URL capture may require a user to sign in manually in a persistent browser profile.
- Added Markdown transcript output and optional separate timeline output. JSON summaries contain task metadata and paths, not transcript bodies.
- Added opt-in literal terminology replacement through a UTF-8 JSON dictionary.
- Added bounded media duration and transcript output limits, URL batch/input limits, bounded download concurrency, and configurable retries.
- Added persistent task state, duplicate-task handling, and cache cleanup previews that protect media referenced by non-completed tasks.
- Added explicit `--skip-existing` behavior, mutually exclusive with `--force`, and documented the V1 retained-cache cleanup policy.
- Added persisted page-duration checks for downloaded and cached media, bounded cache-entry size/deadline checks, browser DNS deadlines, and redacted candidate error summaries.
- Changed the general ASR default to omit domain-specific prompting; callers can still provide an explicit prompt through the API.
- Added bounded, non-transcript processing-option snapshots so new failed tasks can retry with their original language, timestamp, terminology, resource-limit, download, timeout, and output settings. Legacy tasks without a valid snapshot are skipped unless the user explicitly selects current settings.
- Added private-permission checks for application-owned data storage and read-only environment diagnostics.
- Added a uv lockfile, CI configuration, Skill metadata and references, model provenance documentation, and local verification coverage.
- Added fictional JSON/Markdown output examples, setup and troubleshooting FAQs, cache-retention guidance, and privacy-conscious GitHub issue forms.

## Known release gaps

- Real ASR quality and performance have not been measured on an authorized sample.
- Real Douyin capture, authentication, redirects, and media download have not been verified.
- macOS/Linux and remote CI results have not been verified.
- Clean remote installation and actual Agent invocation have not been accepted.
- The repository owner still needs to choose a license.
- Legacy failed tasks created before processing-option snapshots are skipped by default. Passing `--use-current-defaults` explicitly accepts current settings and saves them as the retry snapshot; new tasks restore their saved options automatically. See the project audit for details.
