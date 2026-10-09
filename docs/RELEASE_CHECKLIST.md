# Release checklist

Release state: **NOT READY**. Keep this checklist as a gate; checked boxes require evidence in the repository or a linked run, not intention.

## Product and verification

- [ ] P1 real local-media transcription completed and documented in `P1_REPORT.md` with quality/runtime notes.
- [ ] P2 three authorized Douyin URL checks completed and documented in `P2_REPORT.md`.
- [ ] P4 real transcript review completed: listen to at least three passages across clear Mandarin, Chinese with English terms, and speech with background music/pauses; record a 10+ minute run and check that stdout/stderr/Agent summaries do not contain the transcript body in `P1_REPORT.md` and `BENCHMARK.md`.
- [x] Current worktree full Windows offline suite passed on Python 3.11.15: 382 passed, 20 skipped.
- [ ] Re-run the full Windows offline suite on Python 3.12.13 after the latest worktree changes. Python 3.12.13 is available, but pytest is not installed in that interpreter environment; `compileall` passed and does not replace this test gate. The previous 376 passed, 20 skipped result predates this worktree.
- [ ] Run and pass the Windows/macOS/Linux CI matrix on the release commit; explain any skipped platform tests.
- [ ] Re-run both full suites and local release checks on the final release commit; run `git diff --check` and review untracked/staged files before committing.
- [ ] Clean installation from the remote repository succeeds without access to the developer's checkout, model cache, or browser profile.
- [ ] Target Agent host invokes the installed Skill safely and returns only concise results.

## Security and privacy

- [ ] Review the latest `docs/PROJECT_AUDIT_REPORT.md`; close or explicitly accept each remaining item.
- [ ] Verify SEC-27 on a Windows host with a mapped network drive, and verify AUD-52 error messaging on POSIX. Private residue is intentionally retained; do not add name-based rollback without an identity-bound platform guarantee.
- [x] AUD-53 recovery media/output checks run outside the SQLite write transaction; a second connection can write during slow validation, and a refreshed claim is preserved by snapshot recheck.
- [x] SEC-28 sensitive-file checker rejects Git-visible files under generic `cache/` directories, including unknown extensions.
- [x] Current worktree `python scripts/check_sensitive_files.py` passed for Git-visible files. The check fails closed on symlinks, non-regular files, files over 2 MiB, binary/NUL content, non-UTF-8 content, or read errors; it does not scan Git history and is not a general secret scanner.
- [x] A read-only scan of all 3 current local commits covered 98 unique path/blob pairs with the known sensitive-path and high-confidence credential rules and found no hits; a targeted search found no exact workstation/user-profile markers. This is limited automated evidence, not a general secret-history scanner.
- [ ] Before release, check the staged/release tree and full Git history for Cookie, token, private transcript, media cache, model weights, browser profile, task database, or local path data. The automated check is not a full secret-history scan.
- [ ] Verify `doctor` reports the effective private data location and permissions on supported hosts.
- [ ] Verify `doctor --output-dir`, dry-run, transcription, and retry report the actual output directory permissions on Windows/macOS/Linux; confirm shared-folder warnings do not change existing ACLs.
- [ ] Recheck setup prompts before dependency/model/Chromium downloads and preserve no-bypass behavior for login, CAPTCHA, DRM, and access controls.
- [ ] After authorized installation of the locked PyAV wheel, verify SEC-31 with a local HLS mock whose playlist references loopback; confirm no child request occurs and ordinary local media still validates.
- [x] Initial upstream license review for the pinned ASR code/model and Playwright Python package recorded in `docs/THIRD_PARTY_LICENSE_REVIEW.md`.
- [ ] Audit the exact PyAV wheels' bundled FFmpeg configuration/notices for supported platforms and complete an SPDX inventory of all locked transitive dependencies before binary distribution.

## Repository owner decisions

- [ ] Owner selected a license and committed the corresponding `LICENSE` file.
- [ ] Owner confirmed repository name, account/org, and visibility.
- [ ] Owner explicitly authorized remote creation/push/publication if those actions are intended.
- [ ] CHANGELOG and version metadata describe the release candidate accurately.

## Release evidence

- [ ] Record the release commit ID and CI run URL.
- [ ] Record the clean-install command and result.
- [ ] Link `P1_REPORT.md`, `P2_REPORT.md`, and the Agent-host invocation evidence.
- [ ] Verify README support claims distinguish tested platforms from intended compatibility.
- [ ] Publish only after the owner-approved license and repository decisions are in place.
