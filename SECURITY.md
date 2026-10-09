# Security policy

## Reporting a vulnerability

Please do not post exploitable details in a public issue. If the hosting platform has private vulnerability reporting enabled for this repository, use that private channel. If it is not enabled, the maintainers need to configure a private reporting channel before receiving a detailed vulnerability report. This checkout does not define an email address, repository URL, or response-time commitment.

Include the affected file or command, the relevant version or commit if known, a concise impact description, and a minimal reproduction using synthetic data where possible. Do not include transcript text, private media, account credentials, browser cookies, signed media URLs, or a browser profile.

## Scope and data handling

Reports may concern the CLI, local storage, browser capture, URL handling, dependency setup, or Agent Skill behavior. The tool is intended to process only content the operator is authorized to access. It does not bypass authentication, CAPTCHA, DRM, or access controls.

The application is designed to keep transcript bodies in local Markdown files and omit them from CLI JSON summaries. Treat diagnostic output and local task data as potentially sensitive. The selected output path may be returned to the operator who requested the transcription so they can find the file; redact private paths or other personal information before forwarding diagnostics to another recipient.

## Supported versions

No released-version support window is declared in this checkout. When reporting an issue, identify the version or commit that you reviewed. Fixes and support status should be confirmed by the maintainers.
