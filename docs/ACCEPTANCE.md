# Acceptance status

This file records the evidence available in the current local worktree. A unit test or mock is not evidence of a real model, real Douyin, remote CI, or Agent-host acceptance. The release report contains the current environment and remaining external gates.

## Stage summary

| Stage | Current status | Evidence and remaining gate |
|---|---|---|
| P0 — Project environment | **PASS locally** | Current `--help` exits 0; `doctor --json` reports `setup_required` and the expected missing ASR/decoder/model/browser components without creating data directories. Locked dependencies and a clean-copy offline CLI smoke test are also verified. |
| P1 — Real local transcription | **NOT VERIFIED** | ASR adapter, duration/segment/text limits, safe Markdown output, and no-body summaries have automated coverage. No authorized Chinese media was transcribed with the real model; quality and wall-clock runtime remain outstanding. The `P1_REPORT.md` and `BENCHMARK.md` files are explicit NOT VERIFIED templates, not evidence of real runs. |
| P2 — Douyin capture | **NOT VERIFIED** | URL policy, persistent browser capture, audio-first/video fallback, bounded download, and error handling have offline/mock coverage. No authorized real Douyin URL was opened; the three-video acceptance remains outstanding. `P2_REPORT.md` is a NOT VERIFIED template, not live-site evidence. |
| P3 — Batch and recovery | **PASS in offline simulation** | URL parsing/deduplication, bounded batches, SQLite states/retry, interruption handling, 50-item mixed batch, download concurrency, serial ASR, cache protection, and collision-safe output have automated coverage. Real-network behavior remains part of P2. |
| P4 — Transcript quality and low context | **PARTIAL** | Transcript text is written locally and summaries omit the body; optional terminology rules are explicit. A real transcript sample, human listening review, and measured performance record are missing. |
| P5 — Skill distribution | **PARTIAL** | The intended artifact is the Skill repository directory, not a wheel/sdist release. `SKILL.md` passes the Agent Skills validator. `scripts/check_clean_skill_install.py` tests a copied Skill without `.venv` or caches, pins `UV_PROJECT_ENVIRONMENT` inside that copy, and keeps application data inside the temporary root; local offline sync, import-origin, `--version`, and direct-URL dry-run passed. CI runs this smoke check in the Windows/macOS/Linux × Python 3.11/3.12 matrix. A remote matrix run, installation from the eventual GitHub repository, and a real invocation through the selected target Agent host remain unverified. |
| P6 — Release | **NOT READY** | Local checks, a Git-visible sensitive-file checker, and a CI workflow exist. Remote CI, GitHub installation, license selection, real P1/P2 evidence, and publication authorization remain open. No remote was configured for this checkout. |

## Local verification

Latest local rerun (2026-10-09): Python 3.11.15 and Python 3.12.13 full suites each reported **382 passed, 20 skipped**. Python 3.12.13 ran in a separate temporary environment outside the repository with locked development dependencies and `UV_OFFLINE=1`. The GitHub Actions Ruff paths, lock consistency, sensitive-file scan, and `git diff --check` passed. Platform-specific skips remain; older 376/20 results apply to an earlier worktree snapshot.

SEC-31 was dynamically checked with the locked PyAV 15.1.0 Windows wheel in a temporary environment: a synthetic HLS playlist referencing a loopback segment invoked the deny callback once and made zero mock-server requests; a synthetic 1-second PCM WAV validated. This confirms the tested Windows wheel behavior only; macOS/Linux wheels and additional media formats remain unverified.

Run from the repository root in PowerShell:

```powershell
uv lock --project .\skills\douyin-transcript --check
uv run --project .\skills\douyin-transcript --locked --no-sync --group dev ruff check .\scripts .\skills\douyin-transcript\src .\skills\douyin-transcript\scripts .\tests
uv run --project .\skills\douyin-transcript --locked --no-sync --group dev pytest -q
python scripts/check_sensitive_files.py
git diff --check
uvx --from skills-ref==0.1.1 agentskills validate .\skills\douyin-transcript
```

To run the suite under a different Python version, first synchronize that interpreter into the project environment, then verify the selected interpreter before testing. Do not combine `--python VERSION` with `--no-sync` against an existing environment created for another Python version: uv can warn and still run the existing environment.

```powershell
uv sync --project .\skills\douyin-transcript --python 3.12 --locked --group dev
uv run --project .\skills\douyin-transcript --python 3.12 --locked --no-sync python --version
$env:UV_OFFLINE = "1"
uv run --project .\skills\douyin-transcript --python 3.12 --locked --no-sync --group dev pytest -q
```

Repeat with `3.11` to test that interpreter. CI uses separate matrix jobs and synchronizes dependencies in each job before running the suite.

The current Windows test harness selects a private profile-based temporary root when the system temp directory's ancestor ACL is not trusted. Platform-specific permission and symlink tests may be skipped when the host cannot provide their required OS behavior; record those skips instead of treating them as cross-platform evidence.

The sensitive-file check scans Git-visible paths for known media/database/cookie locations and scans small UTF-8 text files for high-confidence credential patterns. It reports filenames and finding types only, never matched values. It is a guardrail for the current tree, not a full secret-history scanner or a substitute for reviewing Git history before publication. The GitHub Actions matrix runs this check and the pinned Agent Skills validator before the test job. Cold CI runners need network access for the clean-copy and development dependency installs; lint and test processes run with `UV_OFFLINE=1`. The CI workflow pins uv 0.12.7; older versions have not been verified.

## Evidence required to close remaining acceptance

### P1: local ASR

- Obtain an authorized Chinese audio/video sample at least 60 seconds long and permission to install/download the selected ASR dependencies and model into the chosen data directory.
- Run the CLI against the actual file; record command, model revision, OS, CPU, memory, source duration, model load time, inference time, output path, and whether a nonempty `.md` was produced.
- Compare several passages against careful human listening. Record omissions, insertions, terminology errors, and whether the output remains a transcript rather than a summary.
- Save the result and limitations in `docs/P1_REPORT.md` and `docs/BENCHMARK.md`; include the planned 16.5-minute benchmark only if that authorized input is actually available.

### P2: Douyin capture

- Use three URLs that the operator is authorized to access. Complete any login manually in the visible browser; do not automate access-control bypasses.
- Record capture, audio/video fallback, download, transcription, login-required, and failure behavior without including cookies, signed media URLs, private transcript text, or account data in the repository.
- Replace the NOT VERIFIED fields in `docs/P2_REPORT.md` with real results. Mocked capture tests do not close this gate.

### P5: Agent Skill invocation

- Invoke the installed Skill from the actual target Agent host and verify the Agent returns only a short status/path summary.
- The offline clean-copy installation used an isolated temporary environment outside the repository and overrides any inherited `UV_PROJECT_ENVIRONMENT` to keep writes inside the copy; it does not prove a real Agent call or remote installation.

### P6: remote distribution and release

- Run the Windows/macOS/Linux CI matrix on a configured remote and archive its run URL and commit.
- Select and add a repository license; verify third-party model/browser notices.
- The initial technical license inventory is in `docs/THIRD_PARTY_LICENSE_REVIEW.md`. Exact PyAV wheel FFmpeg components/notices and a full SPDX inventory of locked transitive dependencies remain open before any binary distribution.
- Install from the remote repository into a clean environment and run the documented smoke command.
- Complete `RELEASE_CHECKLIST.md` only after the owner-authorized repo/visibility and distribution decisions are settled.
