# Douyin Transcript

把**有权处理的**抖音视频链接或本地音视频转成按标题命名的 Markdown 口播逐字稿。ASR 在本机运行，程序不调用 LLM，也不会把逐字稿正文输出到终端或 JSON。

## 当前验证情况

| 项目 | 状态 |
|---|---|
| Windows 本地离线回归 | Python 3.11.15 和 3.12.13 最新工作树均为 382 passed、20 skipped；Ruff 全仓检查和敏感文件检查通过（2026-10-09）。20 项跳过包含 POSIX 专属用例和本机 symlink 能力限制 |
| 本地媒体真实 ASR、速度和识别质量 | 未验证；未下载模型 |
| 真实抖音登录、媒体捕获和 CDN 下载 | 未验证；没有使用账号或授权链接 |
| macOS / Linux | CI 目标，尚未验证 |
| Agent Skills 标准文件 | 已通过标准校验；仓库外离线干净副本安装和 CLI 冒烟通过；真实 Agent 调用待验证 |

## 安装和首次准备

项目要求 Python 3.11/3.12 和 [uv](https://docs.astral.sh/uv/)。CI 固定使用 uv 0.12.7；更早版本尚未验证。基础安装只安装轻量 CLI。`uv sync --locked` 会在 Skill 目录创建或更新 `.venv`，并可能从配置的软件源下载锁定依赖；由 Agent 执行前，应先说明这些网络和文件写入行为并取得用户同意：

```powershell
uv sync --project .\skills\douyin-transcript --locked
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript doctor --json
```

首次需要转写时，明确选择模型档位；命令会先显示操作并要求确认。balanced 使用 medium，fast 使用 small：

```powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript setup --model balanced
```

抖音链接抓取需要 Chromium，可另行准备。首次启动会打开浏览器；需要登录时请在浏览器中手动登录：

```powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript setup --browser
```

Windows 优先使用 `%LOCALAPPDATA%\douyin-transcript`；若祖先 ACL 不安全且该数据目录尚不存在，会退回当前用户目录下的 `%USERPROFILE%\.local\share\douyin-transcript`。如果旧目录已经存在但不安全，程序保留原路径并拒绝写入，不会静默切换或迁移数据。用 `doctor --json` 查看实际选中的 `data_dir`。也可以显式把模型、数据库、浏览器 profile 与媒体缓存放到经确认私有的其他目录：

```powershell
$env:DOUYIN_TRANSCRIPT_HOME = "$env:USERPROFILE\douyin-transcript-data"
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript doctor --output-dir "$env:USERPROFILE\Transcripts"
```

模型文件可能占用数百 MB 到约 1.5 GB，实际大小、下载时间取决于模型和网络。setup 不会自动执行；数据只保存在本机。

程序为自己新建的数据目录设置私有权限：POSIX 使用目录 `0700`、新建 SQLite 文件 `0600`；Windows 在创建目录时直接设置只允许当前用户的受保护 DACL。`doctor` 会只读检查敏感目标和已有祖先，拒绝无法确认或可被其他主体替换的路径；数据目录不安全时不会修改已有权限。浏览器 profile 会长期保留登录状态，任务数据库和媒体缓存也包含本地信息，请勿把数据目录放入共享盘、公开同步目录或提交到仓库。路径检查保留原始词法组件并拒绝 symlink/reparse 别名及 UNC 存储路径；检查与 SQLite、Playwright 等依赖按路径重开的操作仍不是同一文件句柄，存在残余 TOCTOU，不抵御同一 UID 进程、管理员/root 或所有网络文件系统行为。POSIX 扩展 ACL 与 Windows 多账户 ACL 尚需跨平台实机验收。`doctor` 默认检查配置中的输出目录；用 `doctor --output-dir PATH` 检查指定目标。转写、dry-run 和失败重试都会检查本次实际输出目录，并对 `unsafe`/`unknown` 状态发出提示；这是提醒，不会阻止你有意保存到共享目录，也不会改写既有权限。

逐字稿目录依次使用命令行 `--output-dir`、环境变量 `DOUYIN_TRANSCRIPT_OUTPUT`、数据目录 `config.toml` 的 `[paths].output_dir`，最后回退到当前工作目录下的 `douyin-transcripts/output`。数据目录可由 `DOUYIN_TRANSCRIPT_HOME` 指定。

## 使用

单条链接：

```powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript transcribe 'https://www.douyin.com/video/1234567890' --json
```

URL 清单每行一个链接，空行和 `#` 注释会忽略；任务逐条入库，重复视频会跳过：

```powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript transcribe --file .\urls.txt --json
```

本地音视频：

```powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript transcribe --input-file 'D:\Videos\sample.mp4' --output-dir "$env:USERPROFILE\Transcripts" --json
```

查看状态或重试可重试的失败任务：

```powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript status --json
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript retry-failed --json
```

已完成结果默认跳过，也可显式写 `--skip-existing`；它与 `--force` 互斥。`--force` 会重新处理并另存新文件，不覆盖已有逐字稿。默认会保留远端媒体缓存以支持恢复；本地源文件不会被修改。

## 示例输出（虚构数据）

下面的标题、文字、任务 ID 和文件路径均为虚构示例，不来自真实视频或用户数据。JSON 只含任务摘要和路径，不含逐字稿正文：

可下载的示例文件：[`examples/sample_summary.json`](examples/sample_summary.json)、[`examples/sample_output.md`](examples/sample_output.md)；批量 URL 清单模板见 [`examples/urls.example.txt`](examples/urls.example.txt)，运行前需替换为你获授权处理的链接。

```json
{"status":"success","total":1,"success":1,"skipped":0,"failed":0,"output_dir":"C:\\Users\\Example\\Transcripts","output_dir_permissions":{"status":"ok","directories":[{"path":"C:\\Users\\Example\\Transcripts","status":"ok","detail":"private output directory"}]},"items":[{"status":"success","title":"阳台种植入门（虚构样例）","video_id":null,"output_path":"C:\\Users\\Example\\Transcripts\\阳台种植入门-虚构样例.md","error_code":null,"hint":null,"duration_seconds":18.2}]}
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
- `--json` 返回任务状态与计数、标题/视频 ID、路径、目录权限状态、错误码/提示和时长，不含逐字稿正文。Agent 应只回复摘要与文件路径，不读取全文。
- 需要本地模型及 PyAV 解码；`doctor` 可检查依赖、所选档位模型、目录可写性和磁盘空间；使用 `--output-dir` 可检查具体转写目录的隐私权限状态。
- 资源默认上限为媒体 60 分钟、20,000 个识别分段和 2,000,000 个识别字符；超限媒体会在模型加载前拒绝。可在实际数据目录（`doctor --json` 中的 `data_dir`）下的 `config.toml` 的 `[limits]` 中调整，或对单次转写使用 `--max-duration-minutes`、`--max-output-segments` 和 `--max-output-characters`。硬上限分别为 4 小时、100,000 段和 10,000,000 字符。
- 每条媒体的解码、远端下载和 ASR 共用绝对处理时限，默认 7,200 秒。超时会终止负责解码/推理的子进程并将已创建任务标记失败；可通过 `--processing-timeout-seconds N` 调整，最高 86,400 秒。单条任务的 ASR 模型在子进程内复用。
- 抖音页面、登录状态和媒体域名会变化；工具不绕过验证码、登录、DRM 或访问控制。失败时请使用自己有权处理的本地媒体。
- ASR 可能错词，尤其是专有名词、方言和背景音乐；输出未经过人工校对。

## 常见问题

**遇到 403 或 `LOGIN_REQUIRED` 怎么办？** 若页面要求登录，请在打开的 Chromium 窗口中手动登录。工具不绕过登录、验证码、DRM 或访问控制。链接不可用时，改用你有权处理的本地音视频。

**抓不到音频或提示 `DECODER_UNAVAILABLE` 怎么办？** 页面、登录状态和媒体域名可能变化；本地文件还必须包含可解码的音频流。运行 `doctor --json` 检查 PyAV 和模型状态，再使用有音轨且你有权处理的文件排查。

**安装 `av` 时发生依赖冲突怎么办？** 本项目用 `uv.lock` 固定依赖版本。先运行 `uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript doctor --json` 查看状态；按确认提示运行 `setup --model balanced` 安装锁定的 ASR 依赖。不要在系统 Python 或其他项目环境中单独升级 `av`；若仍失败，请在 Issue 中提供脱敏后的操作系统、Python 版本和错误类型，不要附媒体或完整日志中的私人路径。

**模型下载很慢怎么办？** 模型从锁定版本的 Hugging Face 仓库下载，速度取决于网络和所选档位。先确认网络可访问 Hugging Face，并用 `doctor --json` 检查可用磁盘空间；网络中断后可重新运行相同的 setup 命令。不要通过修改模型修订号来绕过下载问题。

**如何减少 C 盘占用？** 在同一个 PowerShell 会话中，先把应用数据、uv 缓存和 Playwright 浏览器目录指向有足够空间且权限合适的本地磁盘，再执行安装或 setup：

```powershell
$env:DOUYIN_TRANSCRIPT_HOME = 'D:\douyin-transcript-data'
$env:UV_CACHE_DIR = 'D:\uv-cache'
$env:PLAYWRIGHT_BROWSERS_PATH = 'D:\playwright-browsers'
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

Use `--dry-run` to resolve inputs, check path writability, and report output-directory permissions without creating directories, downloading, or running ASR. URL batches can use `--max-downloads 1|2`; ASR remains serial. Set bounded retries with `--retry 0|1|2`. Each item's decoding, download, and ASR share a 7,200-second absolute deadline by default; adjust it with `--processing-timeout-seconds N` (maximum 86,400 seconds). A timeout terminates the processing child and marks a created task failed.

An optional UTF-8 JSON terminology whitelist is applied only when passed through `--terminology-dictionary PATH`. Rules use literal, case-sensitive matching and are recorded as metadata without transcript text. Use `--force` to rerun a completed task after changing the dictionary.

Failed tasks save the non-transcript processing options used for that run, and `retry-failed` restores them. Older task records without a valid snapshot are skipped by default; add `--use-current-defaults` only when you accept processing with current defaults. That choice is saved as the task's new retry snapshot. `retry-failed --output-dir PATH` explicitly overrides the saved output directory.

`cache inspect` reports application-owned media cache files. `cache clean --max-bytes N` and/or `--max-age-hours N` preview cleanup by default; add `--apply` after reviewing the paths. Media referenced by non-completed tasks is protected. Cache cleanup serializes against task claims; the direct Python cache API leaves `.part` files alone unless the caller explicitly coordinates task state.

## Agent Skill

Skill 位于 [`skills/douyin-transcript`](skills/douyin-transcript/)。待仓库归属和安装源确定后，可以使用 Agent Skills CLI 安装。单独目录包含运行所需的 Python 包定义、锁文件、脚本和参考文档；仓库外离线干净副本的基础安装与 CLI 冒烟已通过，远端仓库安装、模型准备和真实 Agent 调用尚未验收。

## 开发检查

```powershell
uv run --project .\skills\douyin-transcript --locked --no-sync --group dev pytest -q
uv run --project .\skills\douyin-transcript --locked --no-sync --group dev ruff check .\skills\douyin-transcript\src .\tests
```

项目实施状态、架构、验收与发布门槛见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)、[`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md) 和 [`docs/RELEASE_CHECKLIST.md`](docs/RELEASE_CHECKLIST.md)。审核结论见 [`docs/PROJECT_AUDIT_REPORT.md`](docs/PROJECT_AUDIT_REPORT.md)，分优先级的整改与验收对策见 [`docs/PROJECT_REMEDIATION_PLAN.md`](docs/PROJECT_REMEDIATION_PLAN.md)；阶段计划见 [`docs/PROJECT_IMPLEMENTATION_PLAN.md`](docs/PROJECT_IMPLEMENTATION_PLAN.md)。

## 贡献与问题反馈

贡献前请阅读 [`CONTRIBUTING.md`](CONTRIBUTING.md)。GitHub Issue 表单提供 Bug 报告和功能建议入口；公开问题请勿附带视频、音频、逐字稿、Cookie、签名链接、账户信息或未经脱敏的完整日志。安全漏洞按 [`SECURITY.md`](SECURITY.md) 指引报告。

## 安全与版权

只处理你有权访问和转录的内容，并尊重平台条款、作者版权及隐私。Cookie 保留在用户浏览器 profile；仓库不导出 Cookie，也不上传媒体或逐字稿。faster-whisper、PyAV、Playwright/Chromium 受各自许可证约束。本仓库尚未添加 LICENSE，需仓库所有者确认许可证后再发布。
