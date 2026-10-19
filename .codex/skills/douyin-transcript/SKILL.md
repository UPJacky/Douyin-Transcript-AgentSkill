---
name: douyin-transcript
description: Transcribe authorized local audio/video or Douyin URLs into Markdown for personal Windows use. URL capture uses the current ordinary account and a dedicated Chromium profile with one task at a time; check doctor for dependency readiness. Follow the canonical Skill for authorization, privacy, default-model proofreading and separate reviewed output.
---

# Codex repository entry point

The canonical Skill instructions and CLI project are in `skills/douyin-transcript/` at the repository root. Before handling a transcription request, read and follow `skills/douyin-transcript/SKILL.md` completely. Treat that directory as the CLI project directory; this discovery entry point does not contain the Python package.

The canonical instructions govern authorization, setup consent, structured arguments, local transcript privacy, model proofreading, Chinese script handling, and result handling. Chinese reviewed transcripts default to Simplified Chinese unless the user requests otherwise. Before reporting completion, inspect the saved transcript section for non-empty content and the requested script; the CLI does not convert or validate script. Keep transcript bodies out of chat and diagnostics; only read one into the calling Agent's default model after the user explicitly requests or approves proofreading.
