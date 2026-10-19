# Douyin Transcript

把**有权处理的**本地音视频或抖音链接转成 Markdown 口播逐字稿，优先按标题命名，缺失时使用视频 ID。当前面向个人 Windows 自用：以现有普通账号运行专用 Chromium profile，一次处理一个 URL，不要求管理员服务。三条不同真实授权链接已完成采集、下载、本地 ASR、当前默认模型文本校对及独立校对稿注册；原稿保留，声学听审未验证。后两条没有独立短标题，使用视频 ID 文件名，见[当前交付状态](docs/CURRENT_DELIVERY_STATUS.md)。ASR 在本机运行；CLI 不调用 LLM，也不会把逐字稿正文输出到终端或 JSON。经用户要求或授权后，Agent Skill 使用调用它的 Agent 当前默认模型检查明显的 ASR 错词并补充中文标点，另存并核验 `.reviewed.md` 校对稿；只有完成这一步才报告端到端任务完成。校对会将正文放入该 Agent 的模型上下文，可能发送给模型服务商；首次校对前须说明这一数据流。用户可要求本地模式跳过此步骤，此时结果仍是未校对的原始稿。

## 能力范围

- 官方支持目标为 Windows 11 x64、Python 3.11/3.12；macOS 和 Linux 暂不支持。
- 本地音视频可使用 faster-whisper 在本机转写。首次安装和准备模型会写入本地环境，并可能从配置的软件源下载锁定依赖或模型。
- 个人 URL 采集使用当前账号的可见 Chromium 和专用 profile，串行下载并复用本地 ASR；没有操作系统网络隔离保证。`doctor` 的 URL ready 只表示依赖和路径就绪，不表示某条链接已抓取成功。
- Agent Skill 可在用户明确要求或授权后调用当前 Agent 默认模型校对 ASR 文本。校对会将正文放入模型上下文，首次处理前应说明该数据流；用户也可选择仅保留本地原稿。

## 安装和首次准备

项目要求 Python 3.11/3.12 和 [uv](https://docs.astral.sh/uv/)。CI 固定使用 uv 0.12.7；更早版本尚未验证。基础安装只安装轻量 CLI。`uv sync --locked` 会在 Skill 目录创建或更新 `.venv`，并可能从配置的软件源下载锁定依赖；由 Agent 执行前，应先说明这些网络和文件写入行为并取得用户同意：

官方支持目标为 Windows 11 x64、Python 3.11/3.12；macOS 和 Linux 暂不支持。

```powershell
uv sync --project .\skills\douyin-transcript --locked
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript doctor --json
```

首次需要转写时，明确选择模型档位；命令会先显示操作并要求确认。balanced 使用 medium，fast 使用 small：

```powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript setup --model balanced
```

个人 URL 采集需要 Playwright/Chromium。先运行 `doctor --json`；缺少浏览器时，确认安装行为后运行 `setup --browser`。个人模式报告 `capture_mode=personal`、`checks.browser_isolation.status=not_used`；`capabilities.douyin_urls=ready` 只表示本地依赖和所需路径就绪，不证明某条抖音链接可访问。

Windows 优先使用 `%LOCALAPPDATA%\douyin-transcript`；若祖先 ACL 不安全且该数据目录尚不存在，会退回当前用户目录下的 `%USERPROFILE%\.local\share\douyin-transcript`。如果旧目录已经存在但不安全，程序保留原路径并拒绝写入，不会静默切换或迁移数据。用 `doctor --json` 查看实际选中的 `data_dir`。也可以显式把模型、数据库、浏览器 profile 与媒体缓存放到经确认私有的其他目录：

```powershell
$env:DOUYIN_TRANSCRIPT_HOME = "$env:USERPROFILE\douyin-transcript-data"
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript doctor --output-dir "$env:USERPROFILE\Transcripts"
```

模型文件可能占用数百 MB 到约 1.5 GB，实际大小、下载时间取决于模型和网络。setup 不会自动执行；数据只保存在本机。

程序会为自己新建的数据目录设置仅当前用户可访问的权限。`doctor` 可检查有效数据和输出路径；如果隐式默认目录不安全，转写会停止且不会改写已有权限。浏览器 profile 可能长期保留登录状态，任务数据库和媒体缓存也包含本地信息；请勿把它们放入共享盘、公开同步目录或提交到仓库。显式指定的输出目录可按需要共享，但程序会报告其权限状态。旧任务保存的输出路径不安全或无法确认时，重试需要用户明确指定新的 `--output-dir`。

逐字稿目录依次使用命令行 `--output-dir`、环境变量 `DOUYIN_TRANSCRIPT_OUTPUT`、配置锚点 `config.toml` 的 `[paths].output_dir`，最后回退到所选应用数据目录下的 `output/`。配置锚点依次由 `--data-dir`、`DOUYIN_TRANSCRIPT_HOME` 和平台默认位置确定；没有显式覆盖时，`[paths].data_dir` 选择任务库、浏览器资料、媒体缓存和本地模型所在的数据目录，不会移动正在读取的 `config.toml`。默认输出沿用应用数据目录的私有权限；若默认目录权限不安全或无法确认，转写会停止并要求指定 `--output-dir` 或修复数据目录权限。显式输出目录仍可按需共享并会显示权限提示。新任务按当前设置选择输出目录；失败重试默认恢复任务保存的输出目录，但有效 schema 1/2 快照若保存目录权限为 `unsafe`/`unknown`，在未显式指定 `retry-failed --output-dir` 时会跳过。

## 使用

在 `doctor` 报告 `capabilities.douyin_urls=ready` 后处理一条获授权链接；个人模式一次下载一个任务。同一数据目录的登录与采集通过跨进程占用锁串行；如返回 `CAPTURE_BUSY`，等当前操作完成后重试。`--dry-run` 不创建锁文件：

```powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript transcribe 'https://www.douyin.com/video/1234567890' --max-downloads 1 --json
```

URL 清单按串行任务处理：

```powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript transcribe --file .\urls.txt --max-downloads 1 --json
```

本地音视频：

```powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript transcribe --input-file "$env:USERPROFILE\Videos\sample.mp4" --output-dir "$env:USERPROFILE\Transcripts" --json
```

查看状态或重试可重试的失败任务：

```powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript status --json
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript retry-failed --json
```

`status --json` 保留原稿任务的 `state` 与 `output_path`，并新增 `review_status`、`reviewed_output_path`、`review_scope`。状态会按登记顺序检查最新校对稿以及原稿的登记哈希；只有两者均可检查且哈希匹配时才返回校对稿路径。`completed` 仍只表示原稿任务完成，文本校对范围会明确标为未听审。JSON 和文本摘要都不包含正文。

已完成结果默认跳过，也可显式写 `--skip-existing`；它与 `--force` 互斥。`--force` 会重新处理并另存新文件，不覆盖已有逐字稿。默认会保留远端媒体缓存以支持恢复；本地源文件不会被修改。

## 示例输出（虚构数据）

下面的标题、文字、任务 ID 和文件路径均为虚构示例，不来自真实视频或用户数据。JSON 只含任务摘要和路径，不含逐字稿正文：

可下载的示例文件：[`examples/sample_summary.json`](examples/sample_summary.json)、[`examples/sample_output.md`](examples/sample_output.md)；批量 URL 清单模板见 [`examples/urls.example.txt`](examples/urls.example.txt)，运行前需替换为你获授权处理的链接。

```json
{"status":"success","result_scope":"raw_asr_only","llm_review_status":"not_performed_by_cli","total":1,"success":1,"skipped":0,"failed":0,"output_dir":"<output-dir>","output_dir_permissions":{"status":"ok","directories":[{"path":"<output-dir>","status":"ok","detail":"private output directory"}]},"items":[{"status":"success","title":"阳台种植入门（虚构样例）","video_id":null,"output_path":"<output-file>","error_code":null,"hint":null,"duration_seconds":18.2}]}
```

生成的 Markdown 正文大致如下；自动识别内容未经逐字校对：

```markdown
---
title: "阳台种植入门（虚构样例）"
duration_seconds: 18.2
language: "zh"
model: "faster-whisper-medium-int8"
profile: "balanced"
source: "local_file"
task_id: "example-task-001"
---

# 阳台种植入门（虚构样例）

> 本文为自动语音识别逐字稿，未经人工逐字校对。

## 口播逐字稿

我们先准备一个有排水孔的花盆，再铺一层疏松的土。
种好以后放在有散射光的位置，土壤干了再浇水。
```

## 输出与限制

- Markdown frontmatter 记录标题、来源、模型、语言和时长；时间轴可用 `--timestamps` 另存。
- `--json` 返回任务状态与计数、标题/视频 ID、路径、目录权限状态、错误码/提示和时长，不含逐字稿正文。转写的 `status=success` 表示 raw ASR 文件已写入；`result_scope=raw_asr_only` 和 `llm_review_status=not_performed_by_cli` 明确 CLI 不会做模型校对。经授权的 Agent Skill 必须用调用 Agent 的默认模型校对、补充标点并保存/核验 `.reviewed.md` 后，才能报告端到端请求完成；聊天回复仍只包含状态和文件路径。
- 需要本地模型及 PyAV 解码；`doctor` 可检查依赖、所选档位模型、目录可写性和磁盘空间；使用 `--output-dir` 可检查具体转写目录的隐私权限状态。
- 资源默认上限为媒体 60 分钟、20,000 个识别分段和 2,000,000 个识别字符；超限媒体会在模型加载前拒绝。可在配置锚点所读取的 `config.toml` 的 `[limits]` 中调整，或对单次转写使用 `--max-duration-minutes`、`--max-output-segments` 和 `--max-output-characters`。配置锚点由 `--data-dir`、`DOUYIN_TRANSCRIPT_HOME` 或平台默认位置确定；`[paths].data_dir` 不改变配置文件位置。硬上限分别为 4 小时、100,000 段和 10,000,000 字符。
- 每条媒体的解码、远端下载和 ASR 共用绝对处理时限，默认 7,200 秒。超时会终止负责解码/推理的子进程并将已创建任务标记失败；可通过 `--processing-timeout-seconds N` 调整，最高 86,400 秒。单条任务的 ASR 模型在子进程内复用。
- 抖音页面、登录状态和媒体域名会变化；工具不绕过验证码、登录、DRM 或访问控制。失败时请使用自己有权处理的本地媒体。
- CLI 原始稿可能有错词，尤其是专有名词、方言和背景音乐；Agent 模型校对可修复上下文明确的错误并补标点，但不能替代听音，也不会验证事实或数字。

## 常见问题

**遇到 403 或 `LOGIN_REQUIRED` 怎么办？** 页面可能要求登录或当前账号没有访问权。运行 `uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript login`，在专用可见浏览器中手动登录，关闭窗口保存状态后用同一命令前缀执行 `transcribe <原URL> --force --max-downloads 1 --json`，仅重跑这个失败目标。工具不绕过登录、验证码、DRM 或访问控制。仍无法访问时，使用你有权处理的本地音视频。

**抓不到音频或提示 `DECODER_UNAVAILABLE` 怎么办？** 页面、登录状态和媒体域名可能变化；本地文件还必须包含可解码的音频流。运行 `doctor --json` 检查 PyAV 和模型状态，再使用有音轨且你有权处理的文件排查。

**安装 `av` 时发生依赖冲突怎么办？** 本项目用 `uv.lock` 固定依赖版本。先运行 `uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript doctor --json` 查看状态；按确认提示运行 `setup --model balanced` 安装锁定的 ASR 依赖。不要在系统 Python 或其他项目环境中单独升级 `av`；若仍失败，请在 Issue 中提供脱敏后的操作系统、Python 版本和错误类型，不要附媒体或完整日志中的私人路径。

**模型下载很慢怎么办？** 模型从锁定版本的 Hugging Face 仓库下载，速度取决于网络和所选档位。先确认网络可访问 Hugging Face，并用 `doctor --json` 检查可用磁盘空间；网络中断后可重新运行相同的 setup 命令。不要通过修改模型修订号来绕过下载问题。

**如何减少 C 盘占用？** 在同一个 PowerShell 会话中，先把应用数据、uv 缓存和 Playwright 浏览器目录指向有足够空间且权限合适的本地磁盘，再执行安装或 setup：

```powershell
$env:DOUYIN_TRANSCRIPT_HOME = "$env:LOCALAPPDATA\douyin-transcript"
$env:UV_CACHE_DIR = "$env:LOCALAPPDATA\uv\cache"
$env:PLAYWRIGHT_BROWSERS_PATH = "$env:LOCALAPPDATA\ms-playwright"
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript doctor --json
```

`DOUYIN_TRANSCRIPT_HOME` 包含模型、任务数据库、浏览器 profile 和媒体缓存；它必须通过私有目录权限检查。`UV_CACHE_DIR` 与 `PLAYWRIGHT_BROWSERS_PATH` 分别移动 uv 和 Chromium 缓存。setup 会检查目标盘空间；不要把含登录状态的浏览器 profile 放到共享目录。

**没有 GPU 能运行吗？** 可以。当前模型配置使用 CPU 和 int8；`fast` 选择较小的 small 模型，`balanced` 使用 medium。实际速度取决于 CPU、媒体和模型，项目没有通用速度承诺。

**路径报错或权限状态是 `unsafe` / `unknown` 怎么办？** 运行 `doctor --json` 查看选中的 `data_dir`，用 `DOUYIN_TRANSCRIPT_HOME` 选择受信任的本地数据目录；用 `doctor --output-dir PATH` 检查逐字稿目标目录。doctor 只读检查，不会创建目录或自动修改已有权限。公开 Issue 前请删除用户名、完整路径和其他私人信息。

**媒体缓存会一直增长吗？** 远端媒体默认保留以便恢复和复用，不会自动清理。可把每月查看作为手动维护起点：

```powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript cache inspect --json
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript cache clean --max-age-hours 720 --json
```

第二条命令只预览清理计划。检查列出的文件并确认保留期后，再运行同一命令并加上 `--apply`；也可按自己的磁盘预算设置 `--max-bytes N`。非完成任务引用的媒体会受保护，原始本地音视频不会被清理。

### Preview, concurrency, terminology, and cache

Use `--dry-run` to resolve inputs, check path writability, and report output-directory permissions without creating directories, downloading, or running ASR. Personal URL batches use `--max-downloads 1`; capture, download, and ASR remain serial. Set bounded retries with `--retry 0|1|2`. Each item's decoding, download, and ASR share a 7,200-second absolute deadline by default; adjust it with `--processing-timeout-seconds N` (maximum 86,400 seconds). A timeout terminates the processing child and marks a created task failed.

An optional UTF-8 JSON terminology whitelist is applied only when passed through `--terminology-dictionary PATH`. Rules use literal, case-sensitive matching. Markdown metadata contains the ruleset hash and aggregate applied-rule/replacement counts, not rule IDs, source or replacement strings, notes, or per-rule counts. The hash can still be compared with a known dictionary. Full rules are kept in the protected local task database so failed tasks can be retried with the same settings. Use `--force` to rerun a completed task after changing the dictionary.

Failed tasks save the non-transcript processing options used for that run, and `retry-failed` restores them. Older task records without a valid snapshot are skipped by default; add `--use-current-defaults` only when you accept processing with current defaults. That choice is saved as the task's new retry snapshot. A valid schema 1/2 snapshot with unsafe or unknown saved output permissions is also skipped before requeue unless `retry-failed --output-dir PATH` explicitly selects and saves a new destination.

`cache inspect` reports application-owned media cache files. `cache clean --max-bytes N` and/or `--max-age-hours N` preview cleanup by default; add `--apply` after reviewing the paths. Media referenced by non-completed tasks is protected. Cache cleanup serializes against task claims; the direct Python cache API leaves `.part` files alone unless the caller explicitly coordinates task state.

## Agent Skill

Canonical Skill 文件为 [`skills/douyin-transcript/SKILL.md`](skills/douyin-transcript/SKILL.md)。它描述本地媒体转写、个人 URL 采集、用户授权后的默认模型校对和独立校对稿保存流程。CLI 本身只运行本地 ASR，不调用 LLM。

## 开发检查

SPDX Schema 校验器使用独立锁定环境；首次运行前准备该环境：

```powershell
uv sync --project .\tools\spdx-schema-check --locked
uv run --project .\tools\spdx-schema-check --locked --no-sync python .\scripts\check_spdx_schema.py
uv run --project .\skills\douyin-transcript --locked --no-sync --group dev pytest -q
uv run --project .\skills\douyin-transcript --locked --no-sync --group dev ruff check .\skills\douyin-transcript\src .\tests
```

用户说明见 [安装指南](skills/douyin-transcript/references/INSTALL.md)、[CLI 参考](skills/douyin-transcript/references/CLI_REFERENCE.md) 和[故障排查](skills/douyin-transcript/references/TROUBLESHOOTING.md)。

## 贡献与问题反馈

贡献前请阅读 [`CONTRIBUTING.md`](CONTRIBUTING.md)。GitHub Issue 表单提供 Bug 报告和功能建议入口；公开问题请勿附带视频、音频、逐字稿、Cookie、签名链接、账户信息或未经脱敏的完整日志。安全漏洞按 [`SECURITY.md`](SECURITY.md) 指引报告。

## 安全与版权

只处理你有权访问和转录的内容，并尊重平台条款、作者版权及隐私。Cookie 保留在用户浏览器 profile；仓库不导出 Cookie，也不上传媒体或逐字稿。项目许可证尚未确定；请勿将本仓库视为已授予其中原创内容的复用许可。第三方依赖仍按各自许可和 NOTICE。当前计划交付范围不包含 wheel、模型、浏览器或预构建二进制。
