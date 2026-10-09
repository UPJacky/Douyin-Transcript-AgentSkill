# P1 real local transcription report

## Status: NOT VERIFIED

No authorized Chinese speech sample has been processed with the real pinned model in this worktree. The project has no committed test media; do not add private or copyrighted media to Git. The preflight facts below describe this machine only; they are not transcription or benchmark results.

## Preflight (2026-10-09; no media processed)

- OS: Windows 11 Enterprise LTSC, version 10.0.26100 (build 26100)
- Python: 3.11.15 (CPython)
- CPU: 12th Gen Intel(R) Core(TM) i5-12400; 12 logical processors
- Installed RAM: 31.7 GiB
- `doctor --json`: `setup_required`; the Skill project's Python environment lacks faster-whisper, PyAV, model weights, Playwright, and Chromium (a separate system Python has faster-whisper 1.2.1 and PyAV 18.0.0, outside the Skill runtime)
- Effective application data path: `%USERPROFILE%\.local\share\douyin-transcript`; not created
- Default workspace output directory: `unsafe` on this host because the D: root grants Authenticated Users directory-replacement rights; do not use it for private transcripts
- Explicit candidate `%USERPROFILE%\Transcripts`: `doctor --output-dir ... --json` reports output permissions `ok` by checking the existing profile parent; the candidate directory was not created. This permission check does not change the overall `setup_required` state or establish real transcription readiness.
- Repository media fixture: none found; no real media was read
- Setup/download behavior: dependencies, model weights, browser, and data directories were not created or downloaded
- Follow-up: AUD-45 checks the actual output directory selected for dry-run, transcription, retry, or `doctor --output-dir`. AUD-51 fixed a false positive for foreign Windows ACEs that grant only traversal/synchronization rights. The default D: workspace output remains unsafe; the profile-local candidate above is permission-checked but not created.

## Authorization and input

- Media owner / authorization basis: NOT PROVIDED
- Media location (outside the repository): NOT PROVIDED
- Duration (must be at least 60 seconds): NOT MEASURED
- Format and audio stream: NOT MEASURED
- SHA-256 (optional; keep the media itself out of Git): NOT MEASURED

## Runtime environment

- OS and version: Windows 11 Enterprise LTSC, version 10.0.26100 (build 26100)
- Python version: 3.11.15 (CPython)
- CPU and logical cores: 12th Gen Intel(R) Core(TM) i5-12400; 12 logical processors
- Installed RAM: 31.7 GiB
- faster-whisper / PyAV versions: NOT INSTALLED
- Model repository and pinned revision: NOT DOWNLOADED
- Model file digest / provenance: NOT MEASURED

## Run and output

- Command (omit private paths if this report will be shared): NOT RUN
- Model load time: NOT MEASURED
- Inference time: NOT MEASURED
- End-to-end time: NOT MEASURED
- Peak memory: NOT MEASURED
- Markdown output path and non-empty check: NOT PRODUCED
- Stdout/stderr/body privacy check: NOT RUN

## Human listening review

Do not paste the transcript into this report. Listen to the source and compare several short passages locally; record only aggregate observations.

| Passage | Omission / insertion / terminology observations | Transcript remains verbatim (yes/no) |
|---|---|---|
| 1 | NOT REVIEWED | NOT REVIEWED |
| 2 | NOT REVIEWED | NOT REVIEWED |
| 3 | NOT REVIEWED | NOT REVIEWED |

## Result and limitations

- Result: NOT VERIFIED
- Limitation: Real model, transcript quality, runtime, memory, and output have not been measured.
- Required next step: Obtain an authorized Chinese media sample of at least 60 seconds and explicit authorization to install the pinned ASR dependencies/model into the selected data directory; then complete this report without committing the media or transcript.
