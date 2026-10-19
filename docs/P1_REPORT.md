# P1 real local transcription report

## Status: P1 PASSED; P4 long-sample transcription and model text review complete, human review remains open

A user-provided local MP4 was processed successfully with the pinned medium model. The file contains an AAC stereo audio stream and no video stream, so this run verifies local audio transcription. The sample exceeds the 60-second P1 minimum. The media and transcript remain in the user's private data locations and are not included in Git.

## Sample and authorization

- User supplied a local file path and asked to process the sample. Processing stayed on this Windows machine; the media was not uploaded or copied into the repository.
- ASR dependency/model installation had been explicitly authorized earlier and was completed on 2026-10-09.
- Sample size: 7,643,581 bytes; duration: 315.907 seconds (5 minutes 15.9 seconds).
- Container/streams: MP4 container, one AAC audio stream, stereo; no video stream detected by PyAV.
- The file name and personal absolute path are omitted from this repository report.

## Runtime environment

- OS: Windows 11 Enterprise LTSC, version 10.0.26100 (build 26100)
- Python: 3.11.15 (CPython)
- CPU: 12th Gen Intel(R) Core(TM) i5-12400; 12 logical processors
- Installed RAM: 31.7 GiB
- ASR dependencies: `faster-whisper==1.2.1`, `av==15.1.0`, installed from the project lock file
- Model: `Systran/faster-whisper-medium` at pinned revision `08e178d48790749d25932bbc082711ddcfdfbc4f`
- `doctor --json`: exit 0; `local_transcription=ready`; all 15 dependency, model, browser, path-permission, and disk checks were `ok` before the run.
- The output was written under the private application data directory's `output/` directory, whose permission check was `ok`.

## Run and output

- Command shape: `douyin-transcript transcribe --input-file <private-local-media> --title <redacted-acceptance-label> --language zh --processing-timeout-seconds 1800 --json`
- Result: exit code 0; one task succeeded, none skipped or failed; detected duration 315.907 seconds.
- End-to-end wall time: 302.50 seconds (monotonic measurement), about 0.96× source duration. Model-load and inference-only time were not measured separately.
- Separate follow-up for SEC-23/AUD-10: a supervised worker fully decoded the same file with PyAV and reported 315.907 seconds; worker startup plus the full validation response took 0.953 seconds. This was a separate run and is not a model-load/inference split of the 302.50-second transcription.
- Output: one non-empty UTF-8 Markdown file, 4,658 bytes; transcript body 1,556 characters, including 1,352 CJK characters. The transcript body is not included in this report.
- Default-deadline re-run: on 2026-10-10, `--force --json` completed successfully with no `--processing-timeout-seconds` override, so the configured 7,200-second default applied. The CLI reported one success and duration 315.907 seconds; a separate non-empty 4,656-byte Markdown was saved privately. This re-run was not separately timed and does not add a human quality review.
- Memory: a single in-run process sample reached 2.07 GiB working set; this is not a continuously sampled peak-memory measurement.
- CLI stdout contained only the structured summary; stderr was 0 bytes. A local privacy check found none of 1,357 distinct 16-character transcript windows containing at least 10 CJK characters in CLI stdout/stderr or subsequent `status --json`; the entire body and its initial excerpt were also absent. This check covers this captured CLI/status path, not every Agent host.
- No stdout, stderr, or task status summary contained the transcript body. The output Markdown is stored privately and was not copied into the repository.

## Human listening review

The sample has not yet been manually compared against the source audio. Do not paste transcript text into this report; record only aggregate observations after listening.

| Passage | Omission / insertion / terminology observations | Transcript remains verbatim (yes/no) |
|---|---|---|
| 1 | NOT REVIEWED | NOT REVIEWED |
| 2 | NOT REVIEWED | NOT REVIEWED |
| 3 | NOT REVIEWED | NOT REVIEWED |

## Historical model proofreading follow-up — 2026-10-10 (§72; source lineage corrected below)

- At the user's request, the transcript was rerun with the explicitly selected local terminology dictionary and `--force`. The CLI succeeded for the same 315.907-second media and created a new 4,878-byte raw Markdown output; the previous output remained unchanged.
- A local token-count check found 0 remaining instances of the user-identified erroneous term and 7 instances of the intended term in the raw file. The output metadata records 1 matched dictionary rule and 3 replacements. The scan emitted counts only, not excerpts.
- The current Agent's configured/default model reviewed that output and saved a separate 5,764-byte `.reviewed.md` sibling. Its original frontmatter was preserved; a local check confirmed the raw file was not changed. This reviewed file contains Chinese punctuation and 7 explicit listen-again markers for uncertain ASR passages. Other likely terminology/name errors were corrected only where context was clear.
- The recorded check did not verify whether the reviewed sibling replaced the raw file's `未经人工逐字校对` notice with a model-review/no-audio-listening notice. A later follow-up found the historical sibling lacked the required scope marker; the corrective copy is recorded below.
- This was text-context proofreading, not acoustic validation or external fact-checking. The model cannot establish that the speaker said the corrected words; unresolved names and phrases still require listening to the source. P4 human review and the 10+ minute run remain open.

The later metadata-only source-lineage review (§158 below) found that the earlier reviewed siblings in the private output directory corresponded to a numbered raw Markdown output (`__2.md`), not the unnumbered raw Markdown the user had identified. Therefore the 7 listen-again markers above describe that historical numbered-output sidecar; they must not be combined with the 3 unresolved spans in the newer sidecar for the originally identified raw file.

## Reviewed-sidecar scope notice follow-up — 2026-10-11

A metadata-and-format-only check found that the historical reviewed sibling lacked the required notice distinguishing default-model text proofreading from acoustic listening. Under the Skill's no-overwrite rule, a new numbered sibling was created from the existing reviewed file with only that notice changed. The check confirmed the raw file's SHA-256 did not change, the new sibling's frontmatter exactly matches the raw file, and the new sibling is non-empty with Chinese punctuation, paragraph breaks, and the required scope notice. The reviewed transcript body was otherwise unchanged. This is a scope-label correction, not a new model review, human listening, or external fact-check.

## Review of the originally identified raw Markdown — 2026-10-11 (§158)

A metadata-only lineage check confirmed that the user's unnumbered raw Markdown was a different output artifact from the numbered raw file reviewed in §72. The raw file was unchanged, and its private digest was verified locally but is omitted here. At the user's request, the current Agent's default model reviewed only its text and the project writer created a separate private sidecar; its digest was also verified locally and omitted here. Frontmatter and section structure were preserved; the scope notice says this was model text review, not word-for-word listening. The sidecar has 1,793 characters in 12 paragraphs, with a longest punctuation-free run of 35 characters. One misrecognized term appeared 3 times in the raw and 0 times in the sidecar; context-supported corrections were applied. Three spans that could not be recovered from text alone were marked for listening. No transcript body was copied here, and no audio was played. This is the current source-matched text-review evidence; it does not close P4 listening or the 10+ minute sample requirement.

## Private output inventory note — 2026-10-10

A metadata-only check of the private output directory found five Markdown files with sizes 4,656, 4,658, 4,689, 4,878, and 5,764 bytes. This report accounts for the first, second, fourth, and fifth files above. The 4,689-byte file's originating run is not identified in the current acceptance ledger; its body was not read, it was not used as evidence, and it was left untouched. A later follow-up added one numbered sidecar copy with a scope-notice-only change. Do not treat the unidentified file as a successful or reviewed acceptance output until its provenance is established.

## Result and next step

- P1 local transcription: **PASSED** for successful processing of a real user-provided sample longer than 60 seconds, with a non-empty private output and recorded runtime.
- P4 quality review: **PARTIAL**. The exact originally identified raw Markdown has a source-matched default-model sidecar under §158; §72's 7-marker sidecar is a historical output for a numbered raw Markdown file. The separate 938.968-second user-provided sample and its model-reviewed sidecar are recorded in `PROJECT_AUDIT_REPORT.md` §176 and meet the 10+ minute media/run threshold. §179 adds a private 533-point timestamp sidecar with topic-based listening locations. Manual listening to representative clear Mandarin / English-term / background-music passages and fresh Desktop host-context/privacy acceptance remain open. The 315.907-second sample documented in this P1 report is historical P1 evidence and is not the P4 long sample.
- The body was not read into the report or shared in summaries. Continue to keep media, Markdown output, captured logs, and local task data outside Git.
