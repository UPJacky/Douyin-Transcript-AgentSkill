# Installation

These steps assume you already have a checkout of this repository. They do not require a published package or repository URL. Use Python 3.11 or 3.12 and install [uv](https://docs.astral.sh/uv/) for your operating system. CI currently pins uv 0.12.7; older versions have not been verified.

**Support status:** The supported target is Windows 11 x64 with Python 3.11 or 3.12. The macOS and Linux commands below are compatibility-check examples only; those platforms are not supported release targets.

Basic installation creates or updates the project environment from the lockfile. It installs the CLI and its hash-locked Hatchling build toolchain; it does not install faster-whisper, PyAV, a speech model, Playwright, or Chromium. `uv sync --locked` may download locked packages from the configured package index and writes `.venv` under the Skill directory. If an Agent runs it, the Agent must explain these effects and obtain the user's approval first. Commands below use `--no-sync` after the explicit initialization so a later CLI call does not silently synchronize dependencies.

## Windows PowerShell

Run from the repository checkout root:

~~~powershell
uv sync --project .\skills\douyin-transcript --locked
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript --version
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript doctor --json
~~~

To use a different application data location in the current PowerShell session:

~~~powershell
$env:DOUYIN_TRANSCRIPT_HOME = 'D:\douyin-transcript-data'
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript doctor --json
~~~

## Windows Command Prompt

Run from the repository checkout root:

~~~bat
uv sync --project skills\douyin-transcript --locked
uv run --project skills\douyin-transcript --locked --no-sync douyin-transcript --version
uv run --project skills\douyin-transcript --locked --no-sync douyin-transcript doctor --json
~~~

To select a different application data location in the current Command Prompt:

~~~bat
set DOUYIN_TRANSCRIPT_HOME=D:\douyin-transcript-data
uv run --project skills\douyin-transcript --locked --no-sync douyin-transcript doctor --json
~~~

## macOS and Linux

Run from the repository checkout root:

~~~sh
uv sync --project ./skills/douyin-transcript --locked
uv run --project ./skills/douyin-transcript --locked --no-sync douyin-transcript --version
uv run --project ./skills/douyin-transcript --locked --no-sync douyin-transcript doctor --json
~~~

To select a different application data location in the current shell:

~~~sh
export DOUYIN_TRANSCRIPT_HOME="$HOME/douyin-transcript-data"
uv run --project ./skills/douyin-transcript --locked --no-sync douyin-transcript doctor --json
~~~

Default application data locations are %LOCALAPPDATA%\douyin-transcript on Windows when its ancestor ACL passes the trust check. If it is unsafe and does not yet exist, the application falls back to %USERPROFILE%\.local\share\douyin-transcript; an existing unsafe directory stays selected and is not changed or silently hidden. macOS uses ~/Library/Application Support/douyin-transcript; Linux uses $XDG_DATA_HOME/douyin-transcript, or ~/.local/share/douyin-transcript when XDG_DATA_HOME is unset. Use `doctor --json` to see the effective data directory. An explicit DOUYIN_TRANSCRIPT_HOME must also pass the permission-chain check.

## Optional local ASR setup

Run doctor first to see which capabilities are available. To prepare local transcription, choose one model profile:

Run the command for your shell from the repository checkout root. Choose one profile; balanced selects the medium model and fast selects the small model.

PowerShell:

~~~powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript setup --model balanced
~~~

Command Prompt:

~~~bat
uv run --project skills\douyin-transcript --locked --no-sync douyin-transcript setup --model balanced
~~~

macOS or Linux:

~~~sh
uv run --project ./skills/douyin-transcript --locked --no-sync douyin-transcript setup --model balanced
~~~

Replace balanced with fast to prepare the smaller model profile. Setup displays the dependencies, model, destination, and expected resource use, then asks for confirmation before installation or download. The model can require substantial disk space and network transfer. The command's --yes option skips this prompt; use it only when you have already reviewed and accepted the displayed actions.

After setup, run doctor again:

~~~powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript doctor --profile balanced --json
~~~

## Optional Douyin URL capture setup

Personal URL capture uses the current Windows ordinary account and a dedicated visible Chromium profile. It requires Playwright and Chromium, but no administrator WFP service. It does not provide OS network isolation. `doctor --json` reports `capture_mode=personal` and `checks.browser_isolation.status=not_used`; `capabilities.douyin_urls=ready` checks local dependencies and paths, not URL access or successful capture.

If browser dependencies are missing, review and authorize `setup --browser` before running it through the same CLI prefix. Existing dependencies and authorization can be reused.

PowerShell:

~~~powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript doctor --json
~~~

Command Prompt:

~~~bat
uv run --project skills\douyin-transcript --locked --no-sync douyin-transcript doctor --json
~~~

macOS or Linux:

~~~sh
uv run --project ./skills/douyin-transcript --locked --no-sync douyin-transcript doctor --json
~~~

The dedicated browser profile is persistent and may retain login cookies. If authentication is required, run `login [--data-dir PATH]`, sign in manually, then close the window to save state. Rerun only that failed target with `transcribe <original-URL> --force --max-downloads 1 --json`. Use the same data directory for both commands. The tool does not automate authentication or bypass CAPTCHA, DRM, or access controls. Do not share the browser profile.

## Transcribe

The CLI's success status means that a raw transcript was written; it does not mean the requested model review is finished. When the user authorizes model review, complete and verify a separate non-empty `.reviewed.md` file before reporting completion. If review is declined or unavailable, label the raw output unreviewed; the CLI does not select or call an LLM provider itself.

For local input, use authorized media:

~~~powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript transcribe --input-file 'D:\Videos\sample.mp4' --output-dir 'D:\Transcripts' --json
~~~

After the URL capability check, process an authorized URL with the same prefix and `transcribe <URL> --max-downloads 1 --json`. URL batches and retries are serial in personal mode.

For macOS or Linux, use the same local-media command with a POSIX project path and quote file paths as needed.

The summary printed to the terminal, including --json output, contains status and paths but not the transcript body. The CLI's raw Markdown can be reviewed locally. With the user's authorization, the Agent Skill can also pass the body to the calling Agent's configured/default model for proofreading and punctuation, saving a separate .reviewed.md file; explain that this may send text to the model provider before review. The output directory can be set with --output-dir or DOUYIN_TRANSCRIPT_OUTPUT; precedence is CLI option, environment variable, [paths].output_dir in the selected config anchor's config.toml, then <data_dir>/output. The implicit default uses the application's private data-directory permissions and is rejected if they are unsafe or unknown; explicit shared output remains available. A valid retry snapshot keeps its saved output directory unless --output-dir is explicitly passed. A schema 1/2 snapshot with unsafe or unknown saved output permissions is skipped before requeue unless --output-dir explicitly selects a new destination. Persistent settings are documented in the CLI reference.

## Agent Skill files

The portable Skill directory is skills/douyin-transcript and contains SKILL.md, the Python project, and its references. This checkout does not define a host-specific Agent installer or a published remote installation URL. Use the local Skill discovery or installation procedure documented by your Agent host and point it to this directory. Installing the CLI environment with uv does not by itself prove that an Agent host can load or invoke the Skill.

## Configuration and follow-up

The application reads config.toml from a config anchor selected by --data-dir, DOUYIN_TRANSCRIPT_HOME, or the platform default, in that order. [paths].data_dir can select a different task/cache data location but does not move the config file. Copy and edit [config.example.toml](../assets/config.example.toml) in the selected config anchor; do not overwrite an existing configuration without reviewing it. An example terminology dictionary is [corrections.example.json](../assets/corrections.example.json). It is inert unless explicitly passed with --terminology-dictionary.

Read the [CLI reference](CLI_REFERENCE.md) for all options and [troubleshooting](TROUBLESHOOTING.md) for common setup and media issues. The [model provenance record](MODEL_PROVENANCE.md) documents the model revisions selected by setup.

Setup and doctor do not establish that real ASR, a real Douyin page, or cross-platform behavior works. See the repository's release and audit reports for current acceptance gaps.
