# Douyin Transcript — 抖音口播逐字稿批量转写 Agent Skill
## 可交给执行型 Agent 的详细项目实施方案（V2.0）

> 文档类型：PRD + 技术架构 + 文件级任务清单 + 阶段验收标准 + 故障处理规范 + 开源发布说明
> 制定日期：2026-10-08
> 项目暂定名：`douyin-transcript`
> 优先支持环境：Windows 10/11（无独立 GPU、中文口播、D 盘优先）；兼容性目标为 macOS 和 Linux。
> 交付形式：**一个 GitHub 仓库 + 一个符合 Agent Skills 标准的可安装 Skill + 可独立运行的 Python CLI**。
> 文档状态：**执行规格，不代表功能已经开发或完成测试**。

---

# 0. 给执行 Agent 的最高优先级指令

**你是项目实施者，不是产品经理。严格按照本方案编写真实可执行的代码，不要只创建 README、空文件或伪代码。**

1. 不要反复询问已在本文档明确的技术选择、文件命名、默认路径或参数；按本文默认值执行。
2. 每个阶段都必须交付**真实文件、实际运行命令、测试结果、失败事项**，才允许进入下一阶段。
3. 如果某个环节无法验证，明确标注 `NOT VERIFIED`；不得写“已完成”“已验证”或伪造实测耗时。
4. 优先实现单视频本地转写，再实现抖音获取、批处理、Skill 安装、发布；不要反过来先做漂亮的界面。
5. 所有媒体下载、语音识别、分段、Markdown 保存应在 Python 程序中完成；**禁止把整篇转写文本送回 Agent 上下文进行加工**。
6. 不允许为加速而悄悄删除口头禅、概括原文、补写没说的话、转换为营销文案。目标是“口播逐字稿”，不是摘要。
7. 必须保护用户浏览器登录态及文件；禁止提交 Cookie、Token、个人数据、视频缓存或实际转写稿到 GitHub。
8. 不得尝试绕过验证码、登录验证、DRM、访问控制或平台风控；需要登录时提示用户在浏览器中自行完成，抓取失败时可用本地媒体文件兜底。
9. 禁止在使用者不知情时下载安装大型模型或修改系统级环境；首次初始化应告知依赖、磁盘空间、下载源和目标目录。
10. 最终必须让**另一个干净 Agent 环境**能从 GitHub 安装和调用，不能依赖开发者自己的绝对路径、预先安装的模型或浏览器登录态。
11. 每阶段结束做一个 Git 提交，提交信息参考 `feat(p1): ...`；不能以提交代码代替测试。
12. **完成定义是：真实的 `.md` 文件被正确生成 + 安装/离线/异常测试通过 + 可复现说明完整。**

---

# 1. 目标、范围与优先级

## 1.1 用户核心目标（P0）

- 输入一个或多个抖音视频链接，获得该视频中文口播的**完整机器逐字转写稿**。
- 自动读取视频标题，以 **`视频标题.md`** 命名；Windows 合法字符处理、同名不覆盖、标题缺失兜底。
- Markdown 保存到用户指定的目录；默认保存在当前工作目录的 `douyin-transcripts/output/`，**不得默认保存到 Skill 安装目录**。
- 本地 `faster-whisper` 转写，不依赖付费的在线 ASR/LLM API；默认无需上传音频给外部 AI 服务。
- 批量输入、多链接去重、失败隔离、缓存、断点续跑。
- 一键在 Claude Code、Codex 等兼容 Agent Skills 的 Agent 安装；支持非 Agent 的命令行用法。
- 面向长期、频繁运行：启动时复用模型和浏览器会话，不重复安装或重复转写。
- 运行期间 Agent 只接收简短状态和路径，不读取逐字稿全文。

## 1.2 次要目标（P1）

- `fast`/`balanced` 模型档位、可选 `turbo` 实验档。
- 可选带 `[mm:ss]` 时间轴的 `_timeline.md` 文件。
- Amazon/跨境电商专有名词词典；只做高置信度、可配置的纠错，默认不开激进替换。
- 失败报告、结构化 JSON 汇总、机器可解析退出码。
- Windows 友好的 `run.cmd` 或 PowerShell 启动入口。
- 支持本地音频/视频文件的同一套转写流程，以便离线测试及网页失败时兜底。

## 1.3 延后功能（P2，不阻塞首版）

- 大模型校对（必须显式开启并说明会使用 API Token、隐私与费用）。
- GPU 自动优化、批量推理和多个 GPU 工作者。
- 浏览器桌面 GUI、网页后台、手机 App、云服务、账号系统。
- 抖音视频字幕视觉 OCR、说话人分离、自动翻译、摘要、爆款文案改写。
- 公众号/其他平台通用下载器（可做适配器，但首版不承诺）。

## 1.4 不承诺的事项

- 不承诺抖音任意链接永久可抓取：网络、登录状态、平台页面和权限可能变化。
- 不承诺 100% 字字准确：Whisper 是自动语音识别，专业术语、方言、背景音乐等会造成误差。
- 不承诺任何电脑都达到既有报告的 3.5 / 8.5 分钟：速度与 CPU、内存、音频和模型配置相关。
- 不承诺“安装 Skill 就立刻无需配置可跑”：第一次可能需要安装 Python 依赖、浏览器、下载模型，并由用户登录。

---

# 2. 现有两份方案的依据与最终决策

| 项目 | 第一份方案的内容 | 第二份方案的内容 | V2 决定 |
|---|---|---|---|
| 抓取 | Playwright 连接 CDP，已在原测试环境获取音频流 | Playwright 获取标题及视频 CDN | 采用**可复用的持久化浏览器**，音频优先、视频兜底、CDP 作为可选模式 |
| 模型 | 预测 `large-v3-turbo` CPU int8 | 本机实测 `medium/small` int8 beam=1 | **默认 medium**；small 快速；turbo 待同机测试 |
| 速度 | turbo 5–10 分钟为预估 | 16.5 分钟音频：medium 约 8.5 分钟、small 约 3.5 分钟 | 将第二份数据当成既有机器基线，而非其他机器的保证 |
| 下载 | 优先单独音频流 | 先下载完整视频 | **音频优先**，失败或不完整改用视频 |
| 批量 | 清单、多链接、缓存 | SQLite/manifest 思路、断点记录 | SQLite 状态机 + 原子文件写入 |
| Token | 不打印全文 | 纯脚本完成纠错和写入 | 默认整套程序不调用 LLM API |
| Skill | 可单独创建 | 建议扩展既有 `douyin-transcribe-lz` | **可复用原 Skill 的测试经验和模型缓存，但开源仓库必须可独立安装** |

特别注意：来源方案提到 `faster-whisper 1.2.1 + av 15.1.0` 在测试环境可用，`av 19.x` 曾触发兼容问题；本项目使用**锁文件固定经验证依赖**，不可随意全局写“所有版本 av 必须小于 16”。如切换新版本，先跑回归测试。

---

# 3. 用户使用场景（必须实现）

## 场景 A：单个抖音链接

用户对 Agent 说：

> 提取这个抖音视频的完整口播逐字稿，按视频标题保存为 md：https://www.douyin.com/video/xxxxxxxx

预期：Agent 读取 `SKILL.md`，检查环境/必要时征得安装许可，执行一个本地 CLI 命令，返回输出 MD 的路径、成功/失败和简短原因，**不把全文贴回对话**。

## 场景 B：一次多个链接

用户粘贴 5～50 个 URL，或者把 URL 写到 `urls.txt`；支持每行一个链接、空行、`#` 注释、重复 URL，允许混合 `/video/<id>`、`?modal_id=<id>`、分享短链。

预期：同一视频 ID 只转写一次；其余按队列处理；中途失败不影响下一条；结束生成汇总。

## 场景 C：同一任务中断重启

已成功 6 条，第 7 条掉网，第 8～10 条未处理，重启后只处理剩下的；第 7 条如果已完整下载音频，应复用缓存；若只下载了不完整临时文件则重新下载。

## 场景 D：不打开 Agent、纯命令行

用户在自己电脑上运行：

```powershell
# 以下命令是当前 CLI 的使用示例
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript transcribe --file .\urls.txt
```

预期：与 Agent 模式调用**相同核心代码**，输出完全一致。

## 场景 E：网页抓取失效时

用户手动提供合法取得的 `.mp3`、`.m4a`、`.wav`、`.mp4`、`.mov` 文件：

```powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript transcribe --input-file "D:\Videos\sample.mp4" --output-dir "D:\Transcripts"
```

预期：直接本地转写，文件名取媒体文件名（支持 `--title` 显式覆盖），不依赖抖音网站。

---

# 4. 总体架构与边界

```text
用户 / Agent / CMD
       │
       ▼
统一 CLI（参数校验、日志与状态码）
       │
       ├── doctor/setup：环境和模型准备（经用户确认）
       │
       └── transcribe：单任务 / 多任务调度
                  │
                  ├── URL 标准化和 Video ID 去重
                  ├── BrowserCapture：持久化浏览器抓标题与媒体候选地址
                  ├── MediaDownloader：音频优先、视频兜底、内容完整性检查
                  ├── LocalASR：一次加载 faster-whisper，多次调用转写
                  ├── Normalizer：保留口播、保守断段、可控词典
                  ├── MarkdownWriter：安全文件名、frontmatter、原子保存
                  └── TaskStore：SQLite 去重、失败重试、任务恢复
       │
       ▼
用户 output/*.md + 状态汇总（stdout 不含全文）
```

明确接口边界：**Skill 只负责让 Agent 知道何时及怎样调用 CLI；CLI 拥有全部业务逻辑**。不能在 `SKILL.md` 中教 Agent 每次临时编写下载器或手工复制整篇逐字稿。

---

# 5. 目标 GitHub 仓库结构（每个文件有职责）

```text
douyin-transcript/
├── README.md                         # 中文项目首页：安装、使用、限制、示例
├── README_EN.md                      # 英文简版文档
├── LICENSE                           # 建议 MIT，但须由仓库所有者最终确认
├── CHANGELOG.md                      # 版本变更记录
├── CONTRIBUTING.md                   # 开发/测试和贡献指南
├── SECURITY.md                       # Cookie 与安全报告说明
├── .gitignore                        # 过滤模型、媒体、输出、账号数据等
├── .editorconfig
├── .github/
│   └── workflows/
│       └── ci.yml                    # Windows/macOS/Linux 单元+安装测试
├── skills/
│   └── douyin-transcript/
│       ├── SKILL.md                  # 标准 Agent Skills 入口：短、可执行
│       ├── pyproject.toml            # Python 项目定义、CLI entrypoint
│       ├── uv.lock                   # 经过验证的锁文件
│       ├── scripts/
│       │   ├── run.cmd               # Windows 入口（可选封装）
│       │   ├── run.sh                # macOS/Linux 入口（可选封装）
│       │   └── doctor.py             # CLI 入口的薄封装，勿复制业务逻辑
│       ├── references/
│       │   ├── CLI_REFERENCE.md      # 完整命令与参数
│       │   ├── TROUBLESHOOTING.md    # 常见故障
│       │   └── INSTALL.md            # 不同系统首次安装步骤
│       ├── assets/
│       │   ├── config.example.toml   # 默认配置样板（不含密钥）
│       │   └── corrections.example.json
│       └── src/
│           └── douyin_transcript/
│               ├── __init__.py
│               ├── __main__.py
│               ├── cli.py            # argparse/Typer CLI 层
│               ├── config.py         # 配置加载与路径选择
│               ├── doctor.py         # 运行前检测
│               ├── models.py         # 模型路径、下载和设备选择
│               ├── urls.py           # URL/短链解析与合法性
│               ├── capture.py        # Playwright 页面、标题及媒体捕获
│               ├── downloader.py     # 音视频下载及文件校验
│               ├── asr.py            # faster-whisper 常驻转写
│               ├── normalize.py      # 保守分段与可选术语替换
│               ├── naming.py         # Windows 安全文件名与冲突处理
│               ├── markdown.py       # Frontmatter、MD 原子保存
│               ├── tasks.py          # SQLite 状态存储及恢复
│               ├── pipeline.py       # 业务编排
│               ├── output.py         # 状态汇总、机器友好输出
│               └── errors.py         # 明确的异常和错误码
├── tests/
│   ├── unit/
│   │   ├── test_urls.py
│   │   ├── test_naming.py
│   │   ├── test_markdown.py
│   │   ├── test_normalize.py
│   │   ├── test_tasks.py
│   │   └── test_config.py
│   ├── integration/
│   │   ├── test_local_media.py      # 本地样例端到端
│   │   ├── test_mock_capture.py     # 模拟网页响应，不依赖公网
│   │   └── test_resume.py           # 中断、失败与恢复
│   └── fixtures/                     # 只放有许可的小型测试素材
├── examples/
│   ├── urls.example.txt
│   ├── sample_output.md
│   └── sample_summary.json
└── docs/
    ├── ARCHITECTURE.md
    ├── ACCEPTANCE.md
    └── RELEASE_CHECKLIST.md
```

注意：Skill 内的核心代码、`pyproject.toml`、运行脚本必须完整自包含，因为安装器可能只复制 `skills/douyin-transcript/` 子目录。仓库根目录的 `tests/`、`docs/`、`README` 不应成为安装后运行的硬依赖。**不能从 Skill 内 import 仓库根目录之外的业务源码**。

---

# 6. 环境与依赖规范

## 6.1 目标平台

| 项目 | V1 要求 |
|---|---|
| Windows | Windows 10/11 + x64 CPU，优先正式验收 |
| macOS/Linux | 最低 CLI/本地文件转写可用；浏览器模式尽可能支持并列出已验证版本 |
| Python | 优先 3.11 或 3.12；其他版本只有测试通过才宣称支持 |
| 包管理 | 优先 `uv`；不硬依赖用户安装 Node 才能运行 Python CLI |
| 模型 | CPU `int8` 作为最低可用基线，不要求 NVIDIA GPU |
| 浏览器 | Playwright 管理的 Chromium 持久化配置；可选 CDP 接入现有授权浏览器 |
| 解码 | 优先验证 PyAV；视频格式需要时提供 FFmpeg 检测和有说明的 fallback |

## 6.2 依赖固定

首个被验证的依赖候选：`faster-whisper==1.2.1`，`av==15.1.0`，其余依赖由锁文件固定。**以上为既有测试基线，不代表现在已经在此仓库验证**。若新版本已修复问题，可升级，但必须在 3 个操作系统上至少完成依赖解析、导入和本地音频测试。

建议项目依赖：`faster-whisper`、`playwright`、`httpx`、`pydantic`（可选）或 Python 标准库、`platformdirs`（可选）、`PyYAML`（如读取 YAML）、`typer`（可选）；减少不必要的大型依赖。单元测试使用 `pytest`，格式检查使用 `ruff`。**不要安装 `openai-whisper` 和 `torch` 作为 CPU 必需依赖**。

## 6.3 用户数据路径（不能写死开发机器）

优先级：

1. CLI `--data-dir`、`--output-dir` 显式参数。
2. 环境变量 `DOUYIN_TRANSCRIPT_HOME`、`DOUYIN_TRANSCRIPT_OUTPUT`。
3. 首次配置文件中记录的路径。
4. 平台用户数据目录（使用 `platformdirs` 或等效逻辑），并在下载前检查可用磁盘空间。

在 Windows 首次安装向用户**推荐** `D:\DouyinTranscriptData`，前提是 D 盘存在且可写；否则询问或选择用户同意的目录。不可硬编码 `D:\` 导致无 D 盘用户失败。`uv` 缓存、模型和 Playwright 浏览器等大型依赖如果用户希望全部放 D 盘，应明确支持 `UV_CACHE_DIR`、`PLAYWRIGHT_BROWSERS_PATH`、`HF_HOME`/模型目录设置，先做磁盘空间检查，不能只把 MD 输出放 D 盘。

建议运行时数据：

```text
<data_dir>/
├── config.toml              # 用户配置（非仓库）
├── models/                  # medium/small 等模型
├── browser-profile/         # 登录浏览器资料（敏感）
├── cache/media/             # 按视频 ID 保存的完整媒体
├── cache/temp/              # 下载中的 .part 文件
├── state/tasks.sqlite       # 任务库
└── logs/                    # 不含 Cookie、密钥或正文的日志
```

用户输出独立：`<output_dir>/<视频标题>.md`。不得默认写入安装的 Skill 文件夹，否则升级/卸载时会丢用户数据。

## 6.4 首次初始化

CLI 要提供：

```text
douyin-transcript doctor
douyin-transcript setup
douyin-transcript setup --model balanced
douyin-transcript setup --browser
```

`doctor` **只检查**：Python 版本、导入依赖、模型文件、音频解码、Chromium、目录可写、磁盘空间，并输出修复建议，不能暗中安装。

`setup`：展示即将安装/下载的组件与路径，用户明确同意后执行；若在 Agent 中由 Agent 请求许可。支持跳过浏览器，仅启用本地媒体模式。需要登录时开启**有界面**浏览器让用户自行登录；不得用反爬绕过方案代替用户操作。

---

# 7. CLI 的完整命令与参数契约

**首版必须实现以下命令名，勿随意改名造成 Skill 与 README 不一致。**

```text
douyin-transcript --help
douyin-transcript doctor [--json]
douyin-transcript setup [--model balanced|fast] [--browser] [--data-dir PATH]
douyin-transcript transcribe URL [URL ...] [OPTIONS]
douyin-transcript transcribe --file urls.txt [OPTIONS]
douyin-transcript transcribe --input-file local.mp4 [OPTIONS]
douyin-transcript status [--json]
douyin-transcript retry-failed [--limit N]
```

`transcribe` 选项：

| 参数 | 默认值 | 功能 |
|---|---|---|
| `--file PATH` | 空 | UTF-8 文本，一行一条链接，支持注释 |
| `--input-file PATH` | 空 | 本地媒体文件；与 URL 输入互斥（首版） |
| `--output-dir PATH` | `./douyin-transcripts/output` | MD 输出目录 |
| `--data-dir PATH` | 配置目录 | 数据/模型/任务所在目录 |
| `--profile balanced\|fast` | `balanced` | 当前实现档位；turbo 是可选实验档，待真实模型验收后再评估 |
| `--language zh\|auto` | `zh` | 识别输入语言；`auto` 支持非中文 |
| `--timestamps` | `false` | 另存 `_timeline.md`，不破坏主 MD |
| `--skip-existing` | `true` | 已完成且文件有效则跳过；与 `--force` 互斥 |
| `--force` | `false` | 明确要求重新识别；仍不得无提示覆盖他人文件 |
| 媒体缓存 | 保留至显式清理 | V1 为失败恢复和避免重复下载保留远端媒体；使用 `cache clean` 预览并显式清理。自动删除及 `--keep-media` 暂不属于 V1 |
| `--title TEXT` | 空 | 本地文件等场景下指定标题 |
| `--json` | `false` | 仅输出一个固定 schema JSON 摘要 |
| `--quiet` | `false` | 仅输出最终摘要、错误码 |
| `--dry-run` | `false` | 解析任务、检查路径、不下载或转写 |
| `--max-downloads N` | `2` | 媒体下载并发数，取值 1–2（首版） |
| `--retry N` | `2` | 网络下载/页面临时失败的重试次数，带退避 |
| `--processing-timeout-seconds N` | `7200` | 单条媒体解码/下载/ASR 共用绝对墙钟时限；硬上限 86,400 秒，超时终止处理子进程 |

规范：输入链接无效应给出明确错误；不能把所有异常折叠成“未知失败”；参数缺失时不触发自动大下载。`--force` 只重转写相关视频，不覆盖手工编辑过的 MD；若无法确认归属，另存安全后缀或请求用户明确允许覆盖。

## 7.1 stdout 与文件日志

正常模式输出一行/视频 + 最终汇总，但**不输出逐字稿正文**：

```text
[1/3] OK   id=123...  title=亚马逊广告的底层逻辑  audio=08:31  asr=04:11  file=D:\Transcripts\亚马逊广告的底层逻辑.md
[2/3] SKIP id=456...  reason=already_completed
[3/3] FAIL id=789...  code=DOWNLOAD_FAILED  hint=请检查网络或提供本地文件
SUMMARY total=3 success=1 skipped=1 failed=1 output=D:\Transcripts
```

`--json` 输出**一个机器可解析 JSON 对象**，不要把进度文本掺杂在 stdout；细节写入 stderr 或日志文件：

```json
{
  "status": "partial",
  "total": 3,
  "success": 1,
  "skipped": 1,
  "failed": 1,
  "output_dir": "D:\\Transcripts",
  "items": [
    {"video_id":"123", "status":"success", "output_path":"D:\\Transcripts\\亚马逊广告的底层逻辑.md", "error_code":null},
    {"video_id":"456", "status":"skipped", "output_path":"D:\\Transcripts\\已完成.md", "error_code":null},
    {"video_id":"789", "status":"failed", "output_path":null, "error_code":"DOWNLOAD_FAILED"}
  ]
}
```

建议退出码：`0` 全部成功或已跳过；`2` 输入错误；`3` 环境不满足；`4` 存在失败但有部分成功；`5` 全部失败。必须编写测试保证退出码与 JSON `status` 一致。

---

# 8. 模块功能接口（弱 Agent 必须照此拆分）

## 8.1 `urls.py` — URL 规范化

输入 `str`，输出 `ResolvedInput`（`source_url`、`canonical_url`、`video_id`、`source_type`）或抛 `UnsupportedUrlError`。

要求：

- 支持 `https://www.douyin.com/video/<数字>`。
- 支持 `https://www.douyin.com/jingxuan?modal_id=<数字>`。
- 支持短链接跳转；限制重定向次数与只允许合理的 `https` 目标域，防 SSRF。
- 去除分享文案中的多余文本，只抽取合法 URL；不将后面的跟踪参数全部拿来当 ID。
- 不允许 `file://`、`localhost`、私有内网地址作为远端下载 URL；本地媒体请使用显式 `--input-file`。
- 重复视频 ID 归并，保留首次出现顺序。
- 对无法提取 ID 的视频可尝试在页面获取，但必须防止不同视频错误合并。

验收：不少于 12 个 URL 测试用例（正常、短链模拟、追踪参数、空值、非法协议、重复、跳转环、恶意 URL）。

## 8.2 `capture.py` — 浏览器媒体信息捕获

输入 `ResolvedInput`；输出：

```python
@dataclass
class VideoMetadata:
    video_id: str
    title: str | None
    author: str | None
    publish_date: str | None
    source_url: str
    duration_seconds: float | None
    media_candidates: list[MediaCandidate]
```

`MediaCandidate` 至少包含：`url`、`kind`(`audio`/`video`)、`mime_type`、`headers`（白名单必要项）、`observed_at`、`source`。

具体流程：

1. 一批任务只建立一个 Playwright 浏览器上下文；优先 `launch_persistent_context`，可选经授权连接已有 CDP 端口。
2. **先注册 `page.on('response')` 监听，再导航 URL**；每次处理单条时清除旧监听，防止响应事件叠加。
3. 用 `data-e2e="video-desc"`、页面标题和可访问的页面 metadata 多种来源取标题；过滤 hashtag 等页面噪声，但不把整段正文错当标题。
4. 从媒体网络响应中筛选候选 URL，优先独立音频流；不得把 `blob:` 字符串当成可下载媒体链接。
5. 对响应的域名、Content-Type、状态码、有效期进行基本校验；网页结构变化时给出 `CAPTURE_NO_MEDIA` 等错误。
6. 不输出或持久化包含鉴权信息的完整请求头；不在 debug 日志中记录 Cookie/签名的完整值。
7. 捕获超时和重试后仍失败则记录异常、关闭当前页面、继续下一个任务。
8. 若需登录，显示 `LOGIN_REQUIRED` 并引导用户在有界面浏览器中操作；**不得自动破解验证码**。

注意：第一份材料中的 CDP/音频响应是已有实验结论，不等于对抖音所有视频结构的永久保证。抓取策略需要可替换，可独立测试。

## 8.3 `downloader.py` — 下载与校验

输入候选媒体地址 + 本地缓存路径；输出完整的 `MediaFile(path, format, size_bytes, duration_seconds)`。

- 下载采用流式写入 `.part`，成功后原子改名；失败不得把半截文件当缓存。
- 只对安全域名发请求，限制重定向、连接与读取超时、最大文件体积（可配）。
- 优先 audio；无音频、解码失败或时长严重不完整时才尝试 video。
- 下载完成用 PyAV/FFprobe 验证至少一个可解码音轨和正时长；内容为 HTML 验证页不能当媒体。
- 缓存用 `video_id` + 媒体类型/哈希命名，防止标题变动使缓存丢失。
- 媒体 URL 不长期入库；再次使用缓存校验媒体哈希或文件完整性。
- 支持 429/503 指数退避与有限重试；不要无限轮询平台。
- 原则上把抓到的短时效媒体 URL 立即开始下载，避免排队过期。

## 8.4 `models.py` 和 `asr.py` — 本地 Whisper

模型档位（先实现这两个）：

```text
balanced: medium, CPU, int8, beam_size=1
fast:     small,  CPU, int8, beam_size=1
turbo:    large-v3-turbo, 实验档，必须先验证模型文件和兼容性
```

已提供两份材料显示，原环境 `medium`（16.5 分钟音频）约 8.5 分钟、`small` 约 3.5 分钟；这是前期资料的实测记录，**新的实现必须重新记录硬件和耗时**。

ASR 标准参数候选：

```python
segments, info = model.transcribe(
    media_path,
    language="zh",
    task="transcribe",
    beam_size=1,
    vad_filter=True,
    initial_prompt=None,  # 通用内容不注入行业先验；需要时由调用方显式提供
)
# 按段消费并受数量/字符上限约束；正常输入会完整消费，超限则关闭迭代器并失败。
bounded_segments = []
for segment in segments:
    ...
```

要求：

- **一次模型加载，多视频复用**。CPU 密集推理默认**串行一个任务**，不要 10 个进程同时抢核。
- `language=zh` 用于中文主要场景，提供 `auto` 处理非中文；不得默认翻译成英文。
- 通用转写默认不设置 `initial_prompt`。行业提示词仅允许调用方显式提供，并应在获授权样例上做同机 A/B 验证；提示词不能保证中文标点或术语准确。
- VAD 阈值保守，不要误删停顿后音量较低的人声；至少测试一个带静音/弱声音的样例。
- 处理每个 ASR `segment` 的文本和 `start/end`；确保最终段落与源顺序一致。
- 模型首次从**明确可信**的仓库下载并校验需要的文件；候选包括原材料已测试的 ModelScope 模型镜像；模型 ID、许可证、完整性和 CTranslate2 兼容性需单独核查，不允许只下载 `model.bin` 就默认可运行。
- 优先复用同版本可用的模型缓存；Hugging Face 与 ModelScope 多源切换由配置控制，不把模型文件放进 Git。
- GPU 可作为后续档位，首版不要自动启用未经验证的 CUDA/FP16，避免在普通 Windows 电脑上报错。

## 8.5 `normalize.py` — 逐字稿保真规则

输入 ASR segments，输出正文段落和可选时间轴文本。**必须遵守：**

- 不总结、不改写、不编造；默认保留“嗯、啊、然后、就是说”等口语词，ASR 识别到就保留。
- 仅清理不影响原意的多余空格、明显乱码标点、连续空白行。
- 依据 ASR 自带分段、停顿时长、标点和最大段落长度断段；不能为了凑段落切断专有名词。
- 默认不启用大规模正则错字替换。术语词典应可开关，并记录每个替换规则；任何高歧义词需要上下文保护或人工确认。
- 不要把 `插屏 → 差评` 之类可能误伤的替换无条件应用到全部文本。
- `--timestamps` 额外生成带时间的版本，主稿保持纯正文。
- 不需要 Agent/LLM 承担标点或整理工作。

## 8.6 `naming.py` — Windows 安全文件名

标题提取优先级：页面清晰可识别的视频标题 → HTML document title 清理平台后缀 → 视频 ID。用户显式 `--title` 优先（仅本地文件或有明确需求时）。

必须处理：

- Windows 非法字符 `\\ / : * ? " < > |`，替换为安全字符或删除；中文全角标点可保留。
- 首尾空格、句点、控制字符和 `CON`、`PRN`、`AUX`、`NUL`、`COM1` 等保留设备名。
- 标题限制建议 80 个 Unicode 字符，并考虑 Windows 完整路径过长情形；不能只做字数校验。
- 同名不同视频**不覆盖**：先尝试 `<标题>.md`，已被别的视频占用时改 `<标题>__<id后8位>.md`。
- 同一视频曾成功生成 MD，再运行须稳定指向旧路径（以 SQLite 映射为准），不能生成无穷 `_2`、`_3`。
- 缺标题时 `<video_id>.md`；标题将来恢复不自动重命名用户编辑过的文件。
- 文件名冲突以完整路径/数据库确认，不能只看内存队列。

必须写单元测试覆盖中英文、emoji、Windows 保留名、路径极长、非法字符、同名多视频、已有人工文件、重复执行。

## 8.7 `markdown.py` — 统一 MD 输出

使用 UTF-8、LF（Windows 上允许 LF），含 YAML frontmatter：

```markdown
---
title: "亚马逊新品广告选词最大误区"
source: "douyin"
source_url: "https://www.douyin.com/video/7691282242751991074"
video_id: "7691282242751991074"
author: null
publish_date: null
duration_seconds: 990
language: "zh"
model: "faster-whisper-medium-int8"
transcript_type: "machine-verbatim"
generated_at: "2026-10-08T19:30:00+08:00"
---

# 亚马逊新品广告选词最大误区

> 本文为自动语音识别逐字稿，未经人工逐字校对。

## 口播逐字稿

今天我们来聊一下亚马逊新品广告选词的问题。

很多人在推广新品的时候……
```

说明：上面日期、作者和时长仅是**格式示例**，程序必须读取实际数据；抓不到作者/发布日期则写 `null` 或省略，绝不能伪造。

- YAML 内容必须安全转义（推荐可靠序列化），不能用字符串拼接把冒号/引号搞坏。
- 写入前先写同目录临时文件、关闭 flush 后用 `os.replace` 原子提交；但对于不属于本程序的既有目标文件，严禁不经判断直接 `replace` 覆盖。
- SQLite 仅当 MD 写成功且路径有效时更新为 `completed`。
- 默认为干净正文；时间轴放在单独文件 `标题_timeline.md`，与主文件关联。
- 生成时不往 stdout 打印全文，只有统计和路径。

## 8.8 `tasks.py` — 任务状态与断点续跑

使用内置 SQLite；最小表字段：

```sql
CREATE TABLE IF NOT EXISTS tasks (
  task_id TEXT PRIMARY KEY,
  source_url TEXT NOT NULL,
  video_id TEXT,
  title TEXT,
  state TEXT NOT NULL,
  profile TEXT NOT NULL,
  media_path TEXT,
  output_path TEXT,
  error_code TEXT,
  error_message TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  completed_at TEXT
);
```

状态及合法迁移：

```text
pending -> resolving -> downloading -> downloaded -> transcribing
        -> writing -> completed
任意非 completed 阶段 -> failed
failed -> pending（显式重试/下次恢复）
中断残留 resolving/downloading/transcribing/writing -> 启动时校验缓存和文件再恢复
```

- `task_id`：远端使用 canonical `video_id`；本地文件使用 `absolute_path + content_hash` 的稳定标识，避免不同文件误合并。
- 每次任务完成/失败立即写状态，不能全部结束时才统一提交。
- `completed` 必须再次验证目标 MD 文件存在、非空、与当前视频关联；不只判断文件名是否存在。
- 已下载媒体通过校验后无需重下；`.part` 文件不能视为成功缓存。
- 允许按 error_code `retry-failed`，但是 `LOGIN_REQUIRED` 不做死循环自动重试。
- 多进程同时运行时必须有数据库事务/文件锁，禁止两个进程同时覆盖同一 MD；锁被占用时提示用户。

## 8.9 `pipeline.py` — 编排

建议按以下顺序实现：

```text
read input -> normalize & dedupe -> DB get/create
         -> if completed AND md valid: skip
         -> capture metadata -> download & verify media
         -> load ASR model (once per profile, lazy)
         -> ASR -> normalize -> safe filename
         -> atomic write MD -> commit DB completed
         -> clean temporary media per policy
         -> return one Result record
```

下载可采用**小型有界预取队列**（最多 2 个并发），转写始终 1 个 CPU worker，队列应有上限，避免 50 个视频同时下载占满磁盘。若做并发很容易引入死锁，第一版先串行跑通，再开 2 个下载 worker；同一浏览器抓取建议串行。

---

# 9. 标准 SKILL.md 设计

应放在 `skills/douyin-transcript/SKILL.md`，精简且可操作。正式文件必须符合 [Agent Skills Specification](https://agentskills.io/specification)，其中 `name` 和 `description` 是必需字段。

建议参考内容：

```markdown
---
name: douyin-transcript
description: Transcribe one or many Douyin (抖音) video links or local audio/video files to Chinese machine-verbatim Markdown transcripts named after video titles. Uses local faster-whisper, supports batch resume, no LLM text rewrite. Use when the user wants 抖音口播逐字稿、视频转文字、批量转写、MD 输出.
compatibility: Requires permission to run local Python commands. First-time setup needs network/model download; Douyin pages may require user login. Supports Windows first, macOS/Linux where verified.
---

# Douyin Transcript

1. Determine whether the user provided links, a text list, or local media paths.
2. Locate this skill directory. Do not assume the current working directory is the repo root.
3. Check `uv` and run the project CLI `doctor`; if setup is needed, explain downloads and request approval before invoking setup.
4. For one or more URLs, pass them through the CLI; prefer a UTF-8 URL list file for many links.
5. Do not read, rewrite, summarize, or print transcript bodies to the conversation.
6. Return only the count of completed/skipped/failed jobs, output folder, generated file names, and concise troubleshooting tips.
7. On login/captcha/access problems, ask the user to log in or provide a local media file; do not bypass controls.
8. Consult `references/INSTALL.md` and `references/TROUBLESHOOTING.md` only when needed.

## Commands
- `uv run --project <THIS_SKILL_DIR> --locked --no-sync douyin-transcript doctor`
- `uv run --project <THIS_SKILL_DIR> --locked --no-sync douyin-transcript transcribe --file <URL_LIST> --json`
- `uv run --project <THIS_SKILL_DIR> --locked --no-sync douyin-transcript transcribe <URL> --json`

Never assume successful output until the CLI confirms and files exist.
```

**重要修订：** 此片段只是待实现 Skill 草稿，命令中的 `<THIS_SKILL_DIR>` 必须由调用 Agent 在实际环境中解析为安装路径，不能原样传入；应在 `references/INSTALL.md` 给 Windows PowerShell、CMD、Bash 具体例子。`SKILL.md` 不应放巨量方案正文；详细内容放 `references/`，减少 Agent 每次调用的 Token。

## 9.1 兼容性与安装

推荐 GitHub 公共仓库，安装命令（`<owner>` 为发布后实际 GitHub 用户名）：

```bash
npx skills add <owner>/douyin-transcript --skill douyin-transcript -g -a claude-code -a codex
```

也支持从 GitHub URL 进行安装（按当时 `skills` CLI 文档验证），或手动复制 `skills/douyin-transcript` 目录到 Agent 的 skills 路径。明确区分两步：**安装 Skill 文件** 与 **首次 setup 下载运行环境/模型**。不能写成“`npx skills add` 会自动下载语音模型并打开抖音”。

要在**非仓库当前工作目录**验证安装；不要依赖未包含在 Skill 目录里的 `../../src`、`../../pyproject.toml` 之类引用。所有运行命令都使用安装目录的绝对路径或可靠定位函数。

---

# 10. 开发阶段拆分：严格按顺序实施

## P0 — 项目初始化 / 文档 / 开发环境

**要创建：** 全部基本目录、`pyproject.toml`、固定 `.python-version`（如适用）、`.gitignore`、`README.md` 雏形、`ruff`/`pytest` 配置、CLI 骨架、基本 `doctor`。

**操作：**
1. 检查当前目录是否已有仓库、已有 Skill、既有可用模型缓存；先备份或复用，不删除用户数据。
2. 创建 Git 项目及上述目标目录，不建重复嵌套项目。
3. 用 `uv` 建立锁文件，记录准确 Python 和包版本。
4. `python -m` 与 CLI entrypoint 保证能够启动 `--help`。
5. 在 `README` 写当前完成功能和“未实现”状态，严禁提前夸大。

**验收命令（在仓库根目录）：**

```powershell
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript --help
uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript doctor --json
```

**通过标准：** help 显示正确命令；doctor 能明确说明缺少模型/浏览器，不崩溃；`uv.lock` 存在。允许 doctor 返回环境缺失退出码。

## P1 — 本地媒体转写 MVP（最优先）

**实现文件：** `models.py`、`asr.py`、`naming.py`、`markdown.py`、`normalize.py`、本地 `transcribe --input-file`、相关单元和集成测试。

**步骤：**
1. 支持给定本地音频/视频路径，检查可读与可解码。
2. 模型下载/加载本地模型（首次确认，后续缓存），默认 medium；fast 用 small。
3. 在加载模型前校验媒体时长；按段消费 ASR generator，正常输入完整识别，超过可配置分段数/字符数上限时关闭迭代器并失败；取真实时长。
4. 构造保真正文与有效 YAML frontmatter。
5. 清理文件名并原子生成 MD，返回文件路径。
6. 再跑一次相同输入，检查跳过或有明确重做逻辑。

**真实验收：** 一个至少 60 秒的授权中文口播样例；`output/<原文件名>.md` 存在，UTF-8 正常，正文非空，含实际口播内容；stdout 无全文。使用 `--timestamps` 时额外生成文件且时间递增。写 `P1_REPORT.md` 记录实际用时、CPU 和模型。

**禁止进入 P2 的情况：** 只有零散 Python 脚本、无法通过统一 CLI 跑通；出现空 MD 或转写 0 字却报告成功。

## P2 — URL/标题/音视频捕获

**实现文件：** `urls.py`、`capture.py`、`downloader.py`、浏览器 setup、自检、模拟网页测试。

**步骤：**
1. 先实现本地模拟服务器/模拟响应的媒体捕获和下载测试。
2. 再对用户有访问权限的真实抖音链接测试标题与媒体获取。
3. 浏览器持久化上下文，监听注册在导航之前；一批复用会话。
4. 优先抓独立音频流；失败自动尝试合法获得的视频流。
5. 缓存文件下载后校验时长、解码、大小，拒绝假 HTML 音频。
6. 测试常规 `/video/`、`?modal_id=`、分享短链；无法访问的内容要给出适当错误码。

**验收：** 至少 3 个获授权的真实公开视频（普通短视频、较长口播、精选页），从 URL 得到标题/可解码音轨；未登录时能明示登录要求；不记录 Cookie 原文。如果真实站点不可访问，只能给出 `MOCK PASSED, LIVE NOT VERIFIED`，不能声称 P2 完成真实集成。

## P3 — 批量调度、SQLite、恢复和冲突处理

**实现文件：** `tasks.py`、`pipeline.py`、批量 CLI、结构化状态输出。

**步骤：**
1. 输入 `urls.txt`：忽略注释、空行、重复链接、重复 ID。
2. 多条任务逐条持久化状态，不要在循环结束才保存。
3. 下载有界队列（先串行验证，再最多 2 并发）；转写串行且模型常驻。
4. 任意一条失败继续其他任务，最后汇总失败原因。
5. 进程模拟中断（下载后、转写前、写 MD 前），测试恢复。
6. 同视频重复运行 SKIP；不同视频同标题安全追加视频 ID 后缀。
7. 数据库被两个进程同时打开时避免同一任务并行处理。

**验收：** 10 条测试任务（可混合本地输入/模拟媒体），包含：2 条重复、2 条失败、3 条已有成功缓存、3 条新任务。重试不能覆写已完成 MD；失败不导致成功数据丢失；`status --json` 可用。

## P4 — Token 优化和输出质量

**实现文件：** `normalize.py` 完善、配置词典、`--quiet`/`--json`、时间轴和日志脱敏。

**步骤：**
1. Agent 调用过程不读取整个 MD 内容；运行命令带 `--json` 或 `--quiet`。
2. 逐字稿不删除口头禅、不自动摘要；按语音段落形成可读 MD。
3. 术语词典默认采取审慎原则；仅白名单安全映射自动修正。
4. 进行“抽样对照”：听至少 3 处音频，确认未漏转、没有大量幻觉或循环文字。
5. 保留错误统计、识别时间、视频时长、模型信息；正文仅写文件。

**验收：** 对 10 分钟以上视频，stdout/stderr/Agent 工具摘要不能含完整正文；同一测试音频的 MD 段落完整、无重复大段；模型/术语词典不同的结果可归档比较（无需公开真实视频）。

## P5 — Skill 打包 + 干净安装测试

**实现文件：** `SKILL.md`、`references/*.md`、`run.cmd`、`run.sh`、`README` 安装说明。

**步骤：**
1. `SKILL.md` 使用标准 YAML frontmatter，检查 name/description。
2. 使用标准校验命令 `skills-ref validate ./skills/douyin-transcript`（如果环境已安装官方校验工具；否则按官方安装说明安装并记录结果）。
3. 在干净临时目录执行 `npx skills add <owner>/<repo> --skill douyin-transcript`（未推送 GitHub 前使用本地路径进行同等安装测试）。
4. 检查实际复制/链接后 `pyproject.toml`、代码、scripts、references 均存在。
5. 在**离开仓库根目录**的工作目录调用 Skill 的 CLI，确保没有相对路径依赖。
6. 分别在 Claude Code 和 Codex（可实际使用时）测试 Agent 是否命中 Skill、能启动命令、只回复结果路径。

**验收：** Skill 在不依赖仓库工作目录的独立安装副本中能运行 `doctor`；模型准备后能转写本地媒体；至少一个目标 Agent 宿主的真实对话调用成功。离线干净副本测试与真实 Agent 调用是两项独立证据；从 GitHub 远端安装归入 P6。**如果尚未实际测试 Codex 或 Claude Code，要分别标注未验证。**

## P6 — CI、发布与维护

**实现文件：** GitHub Actions、正式 README、LICENSE、CHANGELOG、tag、发布检查清单。

**步骤：**
1. 在 GitHub Actions Windows/macOS/Linux 矩阵运行基础依赖安装、lint、unit tests、离线模拟集成测试。
2. 不在 CI 中自动登录抖音，不存个人 Cookie、不假设可以稳定下载真实平台媒体。
3. README 展示安装命令、首次 setup、单条/批量/本地文件示例、资源占用、失败说明及免责使用边界。
4. 安全扫描检查是否误提交 Cookie、浏览器配置、音视频、模型、MD 逐字稿。
5. 由用户确认 GitHub 仓库名、是否公开、许可证后发布 `v0.1.0`。
6. 从 GitHub 远端重新安装一次，而不是只验证本地工作区。
7. 生成 `RELEASE_REPORT.md`，列出已验证平台、版本、功能、已知限制、操作视频或日志证明（脱敏）。

**发布门槛：** CI 绿灯 + 远端安装成功 + 至少 3 条真实授权视频端到端验收成功（与 P2 阶段验收对齐）+ 批量断点测试通过 + 隐私数据检查通过。

---

# 11. 测试矩阵：逐项勾选才算完成

| 编号 | 测试场景 | 期望结果 | 阻塞级别 |
|---|---|---|---|
| T01 | URL `/video/ID` | 正确解析 ID | P0 |
| T02 | `?modal_id=ID` | 正确解析 ID | P0 |
| T03 | 分享短链/非法重定向 | 正常解析或安全拒绝 | P0 |
| T04 | `urls.txt` 10 行含重复/注释 | 归并并保留首次顺序 | P0 |
| T05 | 本地 MP3/MP4 | 成功输出非空 MD | P1 |
| T06 | 16.5 分钟中文音频基准 | 记录 CPU/模型/耗时/转写片段质检 | P1 |
| T07 | title 含 `:?*<>/\\|` | Windows 可创建文件 | P0 |
| T08 | 2 个不同视频同标题 | 分别保存，互不覆盖 | P0 |
| T09 | 同视频重复运行 | SKIP 或明确强制重跑，不产生副本 | P0 |
| T10 | 网络中断、短暂 503 | 有限重试，失败状态可恢复 | P0 |
| T11 | 首个视频失败 | 后面的任务继续执行 | P0 |
| T12 | 假 HTML 音视频返回 | 检测为无效媒体，不能成功 | P0 |
| T13 | 进程中断后重启 | 复用完整缓存，修复未完成状态 | P0 |
| T14 | browser profile 无登录 | `LOGIN_REQUIRED`，允许用户人工登录 | P0 |
| T15 | 输出目录只有只读权限 | 明确报错，数据库不记成功 | P0 |
| T16 | stdout 静默模式 | 不回显全文，JSON 可解析 | P0 |
| T17 | 无 D 盘的 Windows | 不崩溃，可选择可写数据路径 | P0 |
| T18 | 一台干净机器/目录安装 Skill | 不依赖开发仓库根目录 | P0 |
| T19 | Windows/macOS/Linux CI | 环境基础测试与单元测试通过 | P1 |
| T20 | `--timestamps` | 额外时间轴文件，递增且不改变主 MD | P1 |
| T21 | Amazon 词典开关 | 词典关闭时不误替换，开启仅按明确规则 | P1 |
| T22 | 50 条模拟任务批处理 | 内存/磁盘有界，无死锁和遗漏 | P1 |
| T23 | 失败日志脱敏 | 不含 Cookie、authorization、签名完整 URL | P0 |
| T24 | MP4 不含音轨 | 失败信息明确，不生成伪稿 | P0 |
| T25 | 不同视频共用一个模型进程 | 模型只加载一次/同一 profile 复用 | P0 |

特别说明：CI 可大量使用 mock/local fixtures；真实抖音 URL 测试需由有访问权限的人在具备网络的环境中执行，并明确记录成功/失败，不能以 mock 测试代替真实平台验收。

---

# 12. 速度、质量、Token、磁盘评估与记录模板

## 12.1 速度评估（不夸大预估）

已有材料记录：16.5 分钟口播在原机器上的数据：

| 引擎 | 既有测试耗时 | 状态 |
|---|---:|---|
| openai-whisper medium FP32 | 约 34–36 分钟 | 既有基线 |
| faster-whisper medium int8 beam=1 | 约 8.5 分钟 | 第二份方案本机实测 |
| faster-whisper small int8 beam=1 | 约 3.5 分钟 | 第二份方案本机实测 |
| faster-whisper large-v3-turbo int8 | 第一份预计 5–10 分钟 | **尚无同机实测，不作保证** |

新项目必须提供 `benchmarks/` 或 `docs/BENCHMARK.md` 记录：OS、Python、CPU、内存、模型哈希、音频时长、抓取时长、下载时长、模型加载时长、推理时长、写入时长、峰值内存、识别错词备注。同机同视频比较才有意义。

**可接受的发布验收：** 不要求所有机器一律 8.5 分钟，但必须证明相比同一机器、同一音频的旧 Whisper medium 基线有可重复的加速效果（如不可运行旧模型，明确记录仅有新的模型耗时）。

## 12.2 质量评估

抽样至少 3 种音频：纯中文清晰口播、包含亚马逊英文缩略词的中文口播、含背景音乐/停顿的口播。抽样对比人工听写片段，记录漏词、插词、严重错词以及专有名词误识别；**先报告准确率问题，不默默改写内容。**

## 12.3 Token 控制

- 本地 Python CLI 转写本身：**无需调用 LLM API**。
- Agent 使用 Skill：只运行 CLI 并返回简短 JSON/日志；仍会花费一定工具调用和摘要上下文 Token。
- Agent **不得**将转写原文放入对话做分段、全文润色、修正，否则失去低 Token 目标。
- 可以做可选 AI 校对模块，但首版必须默认关闭，且必须取得用户明确要求。

## 12.4 磁盘

- 模型可能占数百 MB 到约 1.5 GB 或更多，具体依所选模型文件和镜像而定；首次 setup 必须提示预估所需空间。
- V1 远端媒体缓存默认保留，以支持失败恢复和避免重复下载；用 `cache clean` 设置显式容量/保留期，默认只预览，复核后添加 `--apply` 执行。程序不删除原始用户本地音视频文件。自动清理及 `--keep-media` 暂不属于 V1。
- 不将完整浏览器 profile、模型、音视频与 transcript 输出纳入 Git。

---

# 13. 错误代码与处理约定

| 错误码 | 原因 | 自动处理 | 对用户的提示 |
|---|---|---|---|
| INVALID_URL | URL 不受支持 | 否 | 检查或改用本地文件 |
| NETWORK_ERROR | 超时/临时网络故障 | 最多重试 2 次 | 检查网络，稍后重试 |
| LOGIN_REQUIRED | 需要账号登录 | 不自动破解 | 打开浏览器手动登录 |
| CAPTURE_NO_MEDIA | 网页没有捕获到媒体 | 有限重试 | 页面可能改版，提供本地文件 |
| DOWNLOAD_FAILED | 下载失败/过期/403 | 尝试重新捕获一次 | 检查网络或另提供文件 |
| MEDIA_INVALID | 不可解码/无音轨/残缺 | 尝试候选视频 | 确认视频有声音 |
| MODEL_NOT_FOUND | 模型未安装 | 不自动大下载 | 运行 setup --model |
| MODEL_INCOMPATIBLE | 模型/库不兼容 | 否 | 查看锁文件/doctor |
| ASR_FAILED | 推理异常 | 可人工重试 | 参照日志排查 |
| OUTPUT_NOT_WRITABLE | 输出目录不可写 | 否 | 改目录权限或路径 |
| OUTPUT_COLLISION | 目标文件由其他任务占用 | 安全另名 | 未覆盖原文件 |
| TASK_LOCKED | 另一进程占用 | 否 | 稍后重试 |

要求失败信息清楚，但日志不能泄露 Cookie、鉴权 Header 和媒体 URL 中完整签名参数。日志中不允许打印音频原文或未经处理的完整视频页面文本。

---

# 14. 安全、合规与开源项目边界

1. 只处理用户有权访问、合法取得且适合转录的视频与本地媒体；尊重平台条款、作者版权及隐私。
2. 不开发验证码破解、反爬防护绕过、私有 API 签名伪造、DRM 绕过、账号批量登录等能力。
3. Cookie 保存在用户个人浏览器 profile 中，权限尽量限制；禁止自动导出为仓库可见的明文 `cookies.txt`。
4. 可选择只存储非敏感的元信息；下载媒体缓存和逐字稿默认只留本地，不自动上传第三方。
5. 用户提供的 URL、标题、发布文案、MD 内容都应被视作**不可信输入**，不可拼接后作为 Shell 命令执行；全部用 subprocess 参数数组传递。
6. 下载端禁止 SSRF、非法协议、任意本地文件读取；文件名严格清洗，不能含 `../` 路径穿越。
7. 碰到页面要求登录或验证时提示人工操作，不允许试图自动突破访问控制。
8. `LICENSE` 由仓库所有者确认后加入，README 明确第三方模型和浏览器依赖的许可证边界。
9. GitHub 仓库公开之前必须检查 Git 历史：若曾把 Cookie/密钥提交过，单纯删除文件不足以消除泄露风险，需要撤销凭据并清理历史。

---

# 15. GitHub 发布说明和 README 最低内容

README 中文首页必须按以下顺序写：

1. 30 秒理解功能：链接/本地视频 → 逐字稿 `.md`；支持批量、离线 ASR。
2. 兼容性表格（哪些 OS/Agent **真实测过**，哪些只是预期）。
3. 安装 Agent Skill：`npx skills add <owner>/douyin-transcript --skill douyin-transcript -g`。
4. 非 Agent 命令行使用方式：clone → 安装 uv/依赖 → doctor → setup → transcribe。
5. Windows 用户的 D 盘数据目录推荐方法。
6. 第一次模型下载大小/耗时因网络环境而异，登录抖音的方法。
7. 3 个最常见命令：单链接、批量列表、本地文件。
8. 输出示例（虚构/公开授权测试样本，不包含私人视频）。
9. 模型速度档位说明，严禁拿原环境基线当所有机器承诺。
10. 重复、断点、缓存、`--force` 风险和默认覆盖保护。
11. FAQ：403/登录、抓不到音频、`av` 冲突、模型源慢、C 盘空间、无 GPU、路径问题。
12. 安全和平台合规说明、许可证、贡献指南、Issues 模板。

GitHub Release `v0.1.0` 需包含 CHANGELOG、安装验证命令及对应测试记录。不要求将模型文件或大型可执行包作为 release 附件；发布 GitHub 源码 Skill 即可。

---

# 16. 每阶段 Agent 进度汇报格式（强制）

每完成一个阶段，必须按如下模板回复，正文简洁，不贴完整代码或逐字稿：

```text
阶段：P1 — 本地媒体转写
状态：PASS / PARTIAL / FAIL
完成文件：
- skills/douyin-transcript/src/douyin_transcript/asr.py
- skills/douyin-transcript/src/douyin_transcript/markdown.py
...
实际执行的命令：
- uv run --project ... pytest ...
- uv run --project ... douyin-transcript transcribe --input-file ...
测试结果：
- unit: 32 passed / 0 failed
- integration: 1 passed / 0 failed
真实输出文件：
- D:\Transcripts\某视频标题.md
未完成与风险：
- 真实抖音网址尚未测试（若属实）
下一步：P2
Git commit：<commit id>
```

**任何输出 `TODO`、`pass`、`NotImplementedError`、空函数壳、假测评数字、虚构文件路径，不算该模块已交付。**

---

# 17. 给弱 Agent 的一键执行指令（原样复制）

> 建议先把本文档放到仓库根目录 `docs/PROJECT_IMPLEMENTATION_PLAN.md`，然后把下面这一段作为新会话第一条指令提交给执行 Agent。

```text
你是 Python 工程开发 Agent，不负责重新讨论方案。请读取并严格执行 docs/PROJECT_IMPLEMENTATION_PLAN.md。

任务：开发可发布到 GitHub 的 douyin-transcript 开源项目，交付符合 Agent Skills 标准的 SKILL.md、完整的 Python CLI、本地 faster-whisper 转写、抖音浏览器取音频、批量处理、SQLite 断点续跑、Markdown 按视频标题命名、跨 Agent 安装和测试。

工作规则：
1. 从 P0 开始按 P0→P1→P2→P3→P4→P5→P6 严格顺序实现，不跳阶段。
2. 优先本地文件真实转写，再实现抖音抓取；禁止先做空 Skill、纯 README 或伪代码。
3. 每个阶段实际写代码、运行测试、生成产物，达到方案列出的验收条件才能进入下一阶段。
4. 不允许调用大模型处理整个逐字稿，完整正文只落盘 MD，工具输出仅摘要。
5. 首版默认 CPU faster-whisper medium int8 beam=1；small 快速档；turbo 先不做默认模型。
6. 对 URL、文件名、Cookie、下载请求做安全处理，不绕过验证码或平台访问控制。
7. Windows 优先，不能硬编码开发机器路径；将数据、浏览器 profile、模型、媒体缓存与安装目录分离。允许用户优先选 D 盘。
8. 遇到依赖问题：先看原始错误、锁定有效版本、跑回归测试；不得直接升级所有依赖，也不得伪称修复。
9. 每阶段必须回复：完成文件、真实运行命令、测试结果、输出文件、尚未验证项、Git commit。
10. 只在用户明确授权后创建远端 GitHub 仓库、推送代码或进行公开发布。许可证和仓库归属未确定时先本地准备。

现在开始 P0。如果已经有可复用的 douyin-transcribe-lz 环境，先检查并复用测试结果、模型缓存，但新仓库不能依赖旧环境才能运行。
```

---

# 18. 最终交付核对清单

**P0：项目环境**
- [x] 存在标准目录和可运行的 CLI entrypoint（本地 CLI 冒烟通过）
- [x] `uv.lock` 由实际依赖解析生成（`uv lock --check` 通过）
- [x] `doctor` 输出环境状态，不进行未经授权的安装（当前环境返回 `setup_required`，未创建目录或下载）

**P1：真实转写**
- [ ] 本地中文音频/视频能生成非空 `.md`
- [ ] 主文是口播逐字稿，不是摘要或润色稿
- [x] 识别函数按段消费 faster-whisper generator；超出时长/分段/字符上限时在模型加载前或迭代期间明确失败
- [x] 输出 UTF-8、YAML 合法、安全命名、无全文 stdout（单元/模拟测试通过；真实模型输出未验证）

**P2：抖音获取**
- [ ] 至少 3 个真实授权视频的获取与转写验证有记录
- [x] 优先音频，必要时视频兜底；缓存完整性验证（模拟测试通过）
- [x] 登录需求提示用户，不绕过验证码（错误处理和模拟测试已覆盖；真实页面未验证）

**P3：批量恢复**
- [x] URL 清单、去重、任务状态和跳过逻辑正确（离线测试通过）
- [x] URL 清单限制 1 MiB、单行 8192 字符、每批最多 100 条；50 条输入可接受
- [x] 异常不中断、失败可恢复、同名不覆盖（模拟测试通过）
- [x] 下载有限并发、CPU ASR 串行、模型复用（单元/模拟测试通过）
- [x] 50 条混合任务完整模拟验收（覆盖缓存命中、失败、重复、并发上限、ASR 串行及结果/缓存/输出计数；不代替真实网络与模型验收）

**P4：质量/低 Token**
- [x] 日志、stdout、Agent 上下文不包含完整逐字稿（静态与模拟测试通过）
- [x] 标题终端控制字符过滤、术语输出预算、`--quiet` 最终计数和时间轴顺序回归测试
- [ ] 有可控术语词典和逐字稿抽样复核（显式词典已实现；真实逐字稿抽样待验收）
- [ ] 真实耗时有实测记录，不写虚假倍速

**P5：Skill 分发**
- [x] `SKILL.md` 完全符合标准（`skills-ref` 校验器通过）
- [x] Skill 内代码自包含、可从非仓库目录启动（干净副本离线安装和 CLI 冒烟通过）
- [x] Skill 将 URL、清单和媒体路径示例写为独立 argv，并要求 shell-only 宿主使用 shell 专属参数转义（标准校验通过）
- [ ] 至少一个目标 Agent 宿主的真实安装与对话调用成功；Codex、Claude Code 等其他宿主按实际测试情况分别标注。离线干净副本安装已通过，GitHub 远端安装仍属 P6 未验证项

**P6：GitHub 发布**
- [ ] CI 测试通过、敏感文件检查通过（当前 Git 可见文件检查脚本已加入 CI 配置并本机通过；远端矩阵仍未运行，完整 Git 历史需发布前人工审查）
- [x] GitHub Actions 加入固定版本 `skills-ref==0.1.1` 的 Agent Skills 格式校验；该工作流远端尚未运行
- [x] CI Action 固定完整 SHA，ASR 模型下载固定 Hugging Face revision（官方来源记于 Skill references）
- [x] SEC-10 修复：拒绝由非当前用户、SYSTEM 或 Administrators 所有的既有敏感 Windows 路径；owner 策略回归测试通过，真实多账户 ACL 集成仍待验证
- [x] SEC-09 修复：Skill 明确规定 argv 传参或 shell 专属转义；真实 Agent 宿主调用仍待验证
- [x] SEC-11：总下载时限覆盖 DNS/连接/TLS、响应头、重定向、正文及解码提交，并可中断慢响应；真实 TLS/多平台集成仍待验证
- [x] SEC-12：运行时只接受固定 revision；应用目录模型校验 setup 来源清单和必需文件摘要
- [x] SEC-13：POSIX 敏感目标同时校验有效 UID 与 mode 位；完整祖先链另见 SEC-15
- [ ] SEC-14：在目标 Agent 宿主验证远端标题/路径作为不可信输出数据处理（候选风险，尚未确认为漏洞）
- [x] AUD-19：cache clean 在事务外扫描/规划，对每个候选用短事务重核任务 claim、媒体引用及本地输入路径，并在事务中做身份绑定删除；直接 cache API 默认保留 partial。AUD-56/57 回归见审核报告；单次 OS unlink 仍无严格时限保证。
- [x] SEC-15 本地源码整改：敏感路径使用词法绝对路径；Windows 新目录在创建时应用 protected DACL；配置通过权限检查过的句柄读取；`TaskStore` 保留词法路径。目录树和排他文件创建已加固：POSIX 使用 dir-fd 相对操作并核验对象身份，Windows 通过句柄校验目录/文件身份并在创建文件时应用私有 DACL。源码与 Windows/模拟回归证据见审核报告 SEC-15。
- [ ] SEC-15 平台与剩余边界验收：SQLite、Playwright、模型下载等第三方接口仍按 pathname 使用；Windows ABA 窗口/DACL 继承属性、第二账户和 POSIX 实机行为仍待验收。当前没有证实跨账户利用；不能把本地源码整改表述为跨平台边界已完全消除。
- [x] SEC-16：不安全且不存在的 `%LOCALAPPDATA%` 数据目录改用受信用户 profile fallback；已有旧目录保留并拒绝写入，避免静默隐藏用户数据。本机 `doctor`/目录创建测试通过；多 Windows 环境验证待 CI
- [x] SEC-17：ASR 显式模型路径校验后使用 canonical path；alias 替换回归通过。真实权重未下载
- [x] SEC-18：外部 Hugging Face cache 检查 owner/祖先；blob ETag 内容摘要校验；共享缓存和替换内容回归通过。真实 Hub cache 未运行
- [x] AUD-21：Windows cache clean 固定目录与文件句柄、复核身份后按句柄标记删除；本机竞态用例通过，跨账户集成待验收
- [x] SEC-19：读取 `config.toml` 前验证配置文件及路径链，拒绝不可信配置重定向数据/输出路径
- [x] SEC-19/20：拒绝 `..` 路径组件；配置解析从权限检查过的同一句柄读取；POSIX 逐组件目录 FD/O_NOFOLLOW，Windows 使用 reparse-aware leaf handle 与同句柄 ACL 校验。POSIX symlink/替换/FIFO 和 Windows 多账户集成仍待实机验收
- [x] SEC-21：术语匹配改用前缀树；最长有效命中和 ASCII 边界保持；正文/时间轴共享 2,500 万次转换预算；词典字段和 Trie 大小有硬上限，定向回归通过
- [x] SEC-22：schema v5 在私有任务库保存本次预期 Markdown 摘要；写入不按公开 `video_id` 复用文件；完成/恢复校验摘要，旧任务无摘要时需显式 `--force` 重建。定向回归通过
- [x] SEC-24：POSIX 配置文件以 `O_NONBLOCK` 打开后先按句柄类型检查，拒绝 FIFO，再对普通文件清除非阻塞标志；POSIX 回归因 Windows 开发环境跳过，仍待 Linux/macOS 验收
- [x] SEC-25：`doctor` 的依赖和 Chromium 子解释器使用 Python `-P`，防止从当前工作目录导入影子模块；无害影子模块和两个探测参数回归通过。后续 Diff Scan `8537ef61-e6e5-4b6a-8fc7-f162382c098a` 覆盖相关文件，未发现新候选
- [x] SEC-26：默认处理 worker 和 Chromium 安装子进程使用 Python `-P`；临时影子包与 setup 参数回归通过。后续 Diff Scan `8537ef61-e6e5-4b6a-8fc7-f162382c098a` 覆盖相关文件，未发现新候选；真实 Agent/跨平台行为仍待验收
- [x] AUD-39：downloader 统一接受 `_Validation`、二元组或 `MediaFile` decoder 结果并保留媒体身份；新下载、缓存命中及默认远端 pipeline 回归通过
- [x] AUD-40/41：默认 pipeline 将单条任务绝对 deadline 传给 downloader；使用任务期限与 downloader 自身 300 秒上限的较小值，任务期限到期映射为 `PROCESSING_TIMEOUT` 并写入任务库
- [x] AUD-42：任务快照 schema v2 保存 `max_processing_seconds`；旧 v1 保持兼容，retry 默认恢复原值，显式超时参数覆盖并持久化
- [x] AUD-43：schema v6 将 `timeline_required`、词法 sidecar 路径和 SHA-256 写入 TaskStore；在原子发布前绑定，完成、skip 与 crash recovery 校验完整性；旧任务时间轴需求未知时 fail closed。定向测试 51 passed, 2 skipped；symlink 冲突用例受当前 Windows 文件系统限制跳过，Linux/macOS 发布行为仍待验收
- [x] AUD-44：URL 清单和术语词典以非阻塞方式读取并验证普通文件；FIFO 回归设有子进程超时，在 Windows 跳过
- [x] AUD-45/46：doctor 支持检查显式输出路径；dry-run、转写和重试输出结构化目录权限状态并在文本模式提示；retry 的显式 output-dir 覆盖写入 schema v2 快照。Windows 定向与全套回归通过，POSIX/多账户 ACL 行为仍待验收
- [x] AUD-47：浏览器 CONNECT relay 使用有界缓冲与非阻塞双向读写；目的端反压超时关闭隧道并释放代理槽位，回归通过
- [x] AUD-48：Ctrl+C 取消传播至活动下载、退避等待和待执行 future；关闭浏览器/处理 worker 并将任务记为可重试 `CANCELLED`。AUD-50 已将有期限/可取消的 DNS 解析改为可终止子进程；无期限的直接 helper 仍可能等待系统 resolver，跨平台行为待集成验证
- [x] AUD-49：sidecar 恢复回归遵循先绑定预期路径/摘要、后发布文件的生产顺序；覆盖缺失及摘要不符并确认恢复重跑
- [x] AUD-36 源码与本机回归：POSIX 同步临时文件、发布后的父目录及新建目录祖先链；Windows 以 `MoveFileExW(MOVEFILE_WRITE_THROUGH)` 无覆盖发布文件和新建目录，失败时不返回成功。Windows 同会话创建互斥与并发目录回归通过。 [ ] Linux/macOS、远程/第三方文件系统和断电语义仍待多平台验证
- [x] AUD-37：Windows 仅将明确的 Win32 已存在错误码映射成文件名冲突；通用移动失败保留原错误，新增目标同时出现时的错误码回归
- [x] SEC-23 源码与模拟回归：PyAV 逐帧累计 `samples / sample_rate` 与时间戳跨度，并在每帧后检查配置上限；正容器声明超限时在解码前拒绝，声明偏小时仍以解码结果为准；可恢复 `InvalidDataError` 继续消费后续帧。模拟覆盖低报时长、声明/解码超限早停、下载/ASR 默认上限传递及坏帧恢复
- [ ] SEC-23 真实媒体格式验收：授权的低报/未知时长、VBR/尾部 padding、坏包后有效帧样本；与 faster-whisper 解码行为对照
- [x] AUD-38 源码与回归：本地/新下载远端任务各只做一次完整时长校验；验证结果携带实际解码文件身份传给 ASR，ASR 核对身份后从文件句柄读取，路径替换时失败关闭；直接 ASR 和缓存恢复仍单独校验
- [ ] AUD-38 真实性能验收：用获授权的 16.5 分钟及接近配置上限媒体记录校验次数、CPU 和端到端耗时
- [x] AUD-53：恢复任务的媒体/输出校验移出 SQLite 写事务，提交前重读并比对完整 Task 快照；慢 validator 下并发写入、heartbeat 续租保护回归通过
- [x] SEC-28：敏感文件检查器拒绝 Git 可见树中的通用 `cache/` 目录，不依赖媒体扩展名；未知扩展名路径回归通过
- [x] AUD-10 源码与本机回归：默认 pipeline 用有界 JSON IPC 子进程执行媒体解码和 ASR；单条任务共用绝对 deadline，超时杀死并回收 worker，下载 `.part` 清理、任务写入失败态；worker 在批次内复用模型。默认 7,200 秒，CLI 可调，硬上限 86,400 秒
- [ ] AUD-10 真实集成：用授权媒体和真实 PyAV/faster-whisper 验证子进程文件句柄、超时阈值和 Windows/macOS/Linux 终止/清理行为
- [x] AUD-32/33：短链所有跳转共用 30 秒 deadline；浏览器 CONNECT deadline 覆盖请求头、DNS、连接和成功响应，超时关闭 socket 并释放代理槽位；allowlist/公网地址校验保留。阻塞 resolver、共享短链 deadline 和槽位恢复定向测试通过；真实 Chromium/跨平台 DNS 集成待验收
- [x] AUD-30：缺少/无效配置快照的旧任务默认跳过；`--use-current-defaults` 明确 opt-in 并持久化当前快照；schema 版本严格要求整数 `1`，拒绝布尔、浮点和字符串类型，CLI 回归通过
- [x] AUD-34/35：本地 retry 验证原路径和内容摘要后才转为 `downloaded`；`--force` 在同一事务刷新最近 attempt 的 profile/title/options；定向回归通过
- [x] AUD-31：第 12.4 节已与 V1 缓存行为对齐；远端媒体默认保留，显式 `cache clean` 管理
- [x] AUD-20：并发首次打开数据库时 WAL 对 SQLite locking protocol 状态限时重试；确定性回归和全套测试通过
- [x] README、CHANGELOG、SECURITY、安全报告指引、Skill 安装说明及示例配置齐备；[ ] LICENSE 仍待仓库所有者决定
- [ ] GitHub 安装命令已真实验证
- [ ] 只有获得用户授权才推送/公开项目
- [x] 产出 `docs/RELEASE_REPORT.md`，明确通过项与未验证项
- [x] 产出 `docs/ARCHITECTURE.md`、`docs/ACCEPTANCE.md` 和 `docs/RELEASE_CHECKLIST.md`，仅记录现有实现和证据，不伪造真实 P1/P2 结果

> 2026-10-09 复审基线：当时 Windows 完整测试 **245 passed, 10 skipped**；Ruff、敏感文件检查、锁文件检查、`git diff --check` 与 Agent Skills 校验通过。AUD-24/25/26/28/29 源码整改及离线回归通过；AUD-27 已通过显式 `--skip-existing` 和 V1 媒体缓存范围对齐关闭，可选 turbo 待真实模型验收后再评估。SEC-11/12/13、AUD-19/20 已整改；SEC-17/18、AUD-21 有本机代码与定向回归；SEC-15/16 的平台集成仍待验收。追加复核发现 SEC-20 至 SEC-23、AUD-30 至 AUD-35，其中 SEC-23 仍待媒体样本确认；SEC-19 的 handle-bound 读取仍未完成，AUD-30 旧任务重试策略待定，AUD-31 的第 12.4 节缓存策略文案已修正。Codex Security 结构化扫描完成并记录 5 项源码发现（1 项中危、4 项低危），coverage partial；扫描工具提示结果对应启动时工作树快照。该轮没有修改实现代码或运行新测试。真实媒体/平台/Agent 验收、远端 CI 和许可证决定仍未完成，发布状态为 `NOT READY`。

> 2026-10-09 AUD-32/33 整改复核的历史中间快照：短链 deadline 与浏览器 CONNECT DNS/连接 deadline 已实现，网络定向测试 **26 passed**，4 个相关源码/测试文件 Ruff 通过。当时共享工作树全套 pytest 为 **244 passed, 10 skipped, 9 failed**（失败涉及并行修改中的 markdown、pipeline、storage_security、tasks）；全仓 Ruff 被 `storage_security.py` 的 E501/F821 阻断。该临时快照已由下方最终本地离线复核取代。真实 Chromium、系统 DNS 和 Windows/macOS/Linux 集成仍待验收；详见 `docs/PROJECT_AUDIT_REPORT.md` 与 `docs/RELEASE_REPORT.md`。

> SEC-21 专项整改补记（2026-10-09）：以 Trie 匹配替代逐位置逐规则扫描，最长有效命中、ASCII 边界、原文匹配和不级联替换语义保持；正文与时间轴共用单任务 25,000,000 次转换预算。增加 1,000 规则 × 200,000 字符确定性工作量用例、共享长前缀预算耗尽用例和 pipeline 共享预算用例。`uv run --offline --project .\skills\douyin-transcript --locked --no-sync --group dev pytest -q tests/unit/test_corrections.py tests/unit/test_cli.py tests/unit/test_pipeline.py` 最新定向复跑 **60 passed**；先前共享工作树全套离线测试快照为 **260 passed, 12 skipped**，当时全仓 Ruff 通过。后续当前快照全仓 Ruff 仅被并行 AUD-30 文案的 `cli.py:505`、`cli.py:521` 两条 E501 阻断，完整源码/测试检查加 `--ignore E501` 通过；最终全套测试和 Ruff 待收尾统一复跑确认。超预算时返回 `TERMINOLOGY_WORK_LIMIT`，不是静默截断。

> SEC-22/AUD-30/34/35 整改补记（2026-10-09）：实现 output SHA-256 attempt 凭据及完成/skip/recovery 校验；旧任务无快照默认跳过，`--use-current-defaults` 持久化 opt-in 快照；本地 retry 保持 failed 直至原文件路径/内容验证通过；force reopen 原子更新最近 attempt 设置。相关定向测试 **76 passed**，实现与测试 Ruff 检查通过。此时全套 pytest 尚未重跑；该状态已由下方最终本地离线复核取代。SEC-22 的跨平台共享目录并发替换和旧 schema 输出重建体验仍需集成验收。

> 2026-10-09 最终本地离线复核：Windows 全套 **283 passed, 14 skipped**；全仓 Ruff、`uv lock --check`、敏感文件扫描和 Agent Skills 校验均通过。14 个跳过项是 POSIX 专属权限/symlink/句柄替换/FIFO 用例，或当前 Windows 文件系统不允许创建 symlink。SEC-15 的 TaskStore 路径别名预处理已修复并有确定性回归；实际 symlink 用例本机跳过。SEC-19/20 配置同句柄读取修复已实现；AUD-36 POSIX 目录同步及 Windows 写穿透发布已实现并通过 Windows 本机回归，AUD-37 通用 Win32 错误码保留原样并通过回归。SEC-23 已完成逐帧解码时长检查的源码与模拟回归；AUD-38 的重复全解码已通过身份绑定校验结果整改并有模拟回归，真实长媒体基准仍待授权样本；AUD-10 子进程超时源码与 Windows 本机回归已通过；真实媒体和跨平台 worker 集成仍待验收。Linux/macOS 和其他文件系统耐久性仍待验证。以上结果不替代真实抖音/ASR/Agent、远端 CI、许可证决策和发布授权。

> 2026-10-09 追加本地缺陷收尾：SEC-25/26 子进程加入 `-P` 并通过影子模块回归；AUD-39 的 downloader 接受 `MediaFile` 验证结果；AUD-10 绝对下载 deadline、超时错误码与重试快照已修复；AUD-43 schema v6 sidecar 路径/摘要绑定及完成、skip、crash recovery 校验已实现；AUD-44 FIFO 输入阻塞已拒绝。全套 Windows 离线测试 **303 passed, 17 skipped**，Ruff、锁文件、敏感文件与 Skill 标准校验通过。真实模型、获授权媒体、跨平台 CI、远端 Agent、许可证和仓库发布仍未验收。

> 2026-10-09 早期续审快照（后续情况见下方记录）：再次复跑 Windows 离线全套为 **303 passed, 17 skipped**；Ruff、`uv lock --check`、敏感文件检查和 Agent Skills 校验均通过。`doctor --json` 返回 `setup_required`：faster-whisper、PyAV、模型、Playwright 和 Chromium 均缺失；默认 workspace 输出路径因 `D:\` 向 Authenticated Users 授予目录替换权限而为 `unsafe`。按阶段门槛，P1 真实本地转写是最早未通过阶段，需要获授权的至少 60 秒中文口播样本、用户批准安装依赖/下载固定模型，并使用经验证的私有输出目录。最近一次 Deep Scan 尝试未启动，协调器要求 parent 提供 managed filesystem permission profile；既有 Diff Scan 不能证明全仓无问题。SEC-15 仍为部分整改：POSIX/Windows 目录创建、SQLite、Playwright 与模型第三方接口仍有 pathname-only 边界，需按当前威胁模型继续收紧并完成平台集成验证。

> 2026-10-09 AUD-45/46 续审整改：`doctor --output-dir`、dry-run、转写和 `retry-failed` 现在检查本次实际输出目录的权限；JSON 汇总携带目录状态，文本模式在 stderr 提示 `unsafe`/`unknown`，共享目录仍允许使用且不改既有 ACL。另修复 `retry-failed --output-dir` 单独使用时没有持久化到配置快照的问题。CLI/doctor 定向回归 **58 passed, 2 skipped**；全套 Windows 离线测试 **308 passed, 17 skipped**；全仓 Ruff、锁文件、敏感文件与 Agent Skills 校验通过。macOS/Linux、Windows 多账户 ACL、真实媒体/抖音/Agent、远端 CI、LICENSE 决策和发布仍未验收。

> 2026-10-09 AUD-47/48/49 续审整改：浏览器 CONNECT relay 改为有界非阻塞双向转发，反压超时可释放代理槽；批量下载新增取消传播，Ctrl+C 会关闭活动网络连接、停止重试、取消待执行任务并尽快清理浏览器/处理 worker，活动任务以 `CANCELLED` 标记为可重试。原生 `getaddrinfo` 无法强杀；调用方会及时返回，后台 daemon 解析并发限制为 2。sidecar recovery 回归改为先持久化预期路径/摘要再模拟发布，并覆盖 sidecar 缺失和摘要不符。全套 Windows 离线测试 **315 passed, 17 skipped**；全仓 Ruff、离线锁文件检查、敏感文件检查和 Agent Skills 校验均通过。POSIX、真实 Chromium/DNS、ASR、抖音、远端 CI、Agent 宿主、LICENSE 和发布授权仍未验收。

> 2026-10-09 AUD-50 DNS 可用性续审：带 deadline/取消的 DNS 解析改用 `sys.executable -I` 隔离子进程；超时/取消时终止并回收 worker 后释放两个共享解析名额。主进程仍执行公网 IP 校验。新增阻塞解析超时、双 worker 同时阻塞后取消与名额复用回归；首次全套测试发现 downloader 旧测试的父进程 `getaddrinfo` mock 不再适用于子进程，已改成本地模拟 resolver worker。相关定向回归 **29 passed**，AUD-50 完成时全套 Windows 离线测试 **316 passed, 17 skipped**；Ruff、锁文件、敏感文件和 Agent Skills validator 通过。无 deadline/cancellation 的直接 helper 调用仍同步使用系统 resolver，调用方应提供期限。Linux/macOS、真实 DNS/Chromium、ASR、抖音、远端 CI、Agent 宿主、LICENSE 和发布授权仍未验收。

---

# 19. 参考资料及其证据等级

## 来自用户提供的两份方案（作为旧环境资料，不代表当前项目已实现）

1. 《抖音逐字稿批量工具-方案.md》：原环境 Playwright/CDP 已捕获音频；原 Whisper medium/CPU FP32 慢；提议 `large-v3-turbo` 加速（该档在该文中是预估）。
2. 《方案_抖音口播逐字稿批量转写.md》：原环境 12 核 CPU 无 GPU，`faster-whisper medium int8 beam=1` 约 8.5 分钟，small 约 3.5 分钟；ModelScope 镜像较快；曾遇到 PyAV 兼容问题。

## 本次核对的官方/上游材料（供实施时再次校验）

- Agent Skills 标准：<https://agentskills.io/specification>
- Skills CLI GitHub 安装和参数：<https://github.com/vercel-labs/skills>
- Faster-whisper 官方 README / CPU INT8 / VAD / generator：<https://github.com/SYSTRAN/faster-whisper>
- Faster-whisper 转写参数定义：<https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/transcribe.py>
- uv 项目运行方式：<https://docs.astral.sh/uv/concepts/projects/run/>
- PyAV 19 兼容问题讨论（2026 年）：<https://github.com/SYSTRAN/faster-whisper/issues/1492>

**注意：** 以上网页是当前的设计依据，未来具体版本可能变化。实现时以锁定的依赖、当前官方说明及真实测试结果为准；不得将网页上“支持某能力”等同于项目已集成成功。

---

# 20. 一句话验收标准

> 另一个人拿到 GitHub 地址后，能在受支持的 Agent 上安装 Skill，经一次明确的环境初始化和必要的人工登录，就能用一条命令将多个有访问权限的抖音视频转成以视频标题命名的 Markdown 逐字稿；既能批量断点续跑，又不会把正文塞进 Agent 上下文；失败有可理解的原因，整个功能在干净环境下可复现。

> 2026-10-09 AUD-51 Windows ACL 诊断续审历史快照（由下一条续审刷新）：按权限掩码识别 foreign ACE；只含 `FILE_EXECUTE`/目录遍历和 `SYNCHRONIZE` 的 ACE 不再误报为可读取或可修改。7 组策略回归通过；`%USERPROFILE%\Transcripts` 检查为 `ok` 且未创建，默认 D: 输出仍 `unsafe`。当时全套 Windows 离线测试 **323 passed, 17 skipped**；Ruff、锁文件、敏感文件检查和固定 Agent Skills validator 通过。跨账户和平台权限继承仍待验收。
> 2026-10-09 SEC-15 创建路径续审：POSIX 目录树使用 dir-fd 相对逐组件创建/打开与身份核验；排他文件通过父目录 fd 创建并从同一 fd 检查。Windows 文件通过 `CREATE_NEW` 在创建时应用私有 DACL，固定目录/文件句柄并复核 volume/file ID。Windows 父目录替换回归通过；文件身份不一致用确定性扰动验证 fail-closed（本机拒绝替换仍打开的叶文件）。配置、存储、doctor、CLI 定向测试 **92 passed, 14 skipped**；全套 Windows 离线测试 **325 passed, 20 skipped**。Ruff、离线锁、敏感文件扫描及 `skills-ref==0.1.1` validator 通过。POSIX 实机、Windows 多账户/ABA 边界和第三方 pathname-only API 仍待验收，SEC-15 继续保持未关闭。

> 2026-10-09 SEC-27/AUD-52 续审历史快照：SEC-27 已通过 `GetDriveTypeW()` 拒绝远程映射盘并对未知盘类型失败关闭；mock 回归通过，本机 C:、D: 均识别为固定盘，当前无映射共享可做实测。AUD-52 对创建后身份核验失败的情况加入私有残留提示和排障说明；实现保留对象，避免按可变路径名进行有竞态的清理。Windows 回归覆盖提示，POSIX 分支仍待实机验证。全套 Windows 离线测试 **331 passed, 20 skipped**；storage_security 定向测试 **33 passed, 11 skipped**；Ruff、锁文件、敏感文件检查和 Agent Skills 校验通过。仓库外离线干净副本通过锁定 no-dev 安装、`--version` 与直链 `--dry-run --json`；首次选择 `%TEMP%` 下的数据路径被本机不安全祖先 ACL 拒绝，改用 doctor 确认为安全的用户 profile 候选路径后通过，且未创建运行时数据目录。该历史阶段的 P1/P2/P4/P5/P6 验收与所有者决定仍未完成。

> 2026-10-09 AUD-53/SEC-28 续审与最新本机快照：恢复前的媒体/输出验证现移出 SQLite 写事务；提交时比对完整任务快照，避免长解码持锁或覆盖期间已续租的任务。敏感文件检查器现拒绝 Git 可见树中任意通用 `cache/` 目录内容。新增的两项并发回归与扫描器回归通过；全套 Windows 离线测试 **334 passed, 20 skipped**；全仓 Ruff、锁文件、敏感文件检查和 Agent Skills 校验通过。仓库外 Skill 副本排除源 `.venv`/缓存，在独立临时虚拟环境中 `UV_OFFLINE=1` 锁定 no-dev 安装成功；从仓库外确认模块导入路径来自副本，`--version` 与直链 `--dry-run --json` 通过，未启动 ASR/Chromium 或创建运行时数据目录。`docs/PROJECT_AUDIT_REPORT.md` 记录证据与对策。真实 P1/P2/P4、Agent 宿主、远端 CI、许可证和发布授权仍未完成，整体 `NOT READY`。

> 2026-10-09 AUD-54/AUD-55 修复续审：tasks schema v7 增加 `claim_generation`，所有 worker 写入检查 owner 与代次；heartbeat claim 丢失时取消对应 pipeline 处理。Windows Python 3.12+ 缓存清理改用 `FILE_ID_INFO` 的 64 位卷序列号和 128 位文件 ID，Python 3.11 保留兼容路径。Windows Python 3.11.15 和 3.12.13 全套离线测试各 **337 passed, 20 skipped**；两环境 Ruff 通过，`uv lock --check`、敏感文件扫描和 Agent Skills validator 通过。AUD-54 定向任务/pipeline/downloader 测试 **109 passed, 3 skipped**；AUD-55 Python 3.12 缓存/CLI 定向测试 **26 passed, 2 skipped**。真实 ASR、抖音/Chromium、人工听审、性能记录、Linux/macOS、远端 CI、目标 Agent、许可证和发布授权仍未完成，整体 `NOT READY`。

> 2026-10-09 审核续订（该时点快照）：AUD-56/57 缓存清理已改为事务外扫描与逐文件协调，并保护已记录的本地源路径。AUD-58 已加固浏览器 context、Service Worker、WebSocket 和代理 loopback 边界；AUD-59 至 AUD-62 修复重试状态、缓存恢复、并发本地 retry 和 claim-generation 强制；AUD-63 修复时间戳敏感测试 fixture；DOC-07/08 统一正文隐私规则和基础安装授权说明。后续续审发现 DOC-09（wrapper/示例漏用 `--no-sync`）和 ENG-02（干净安装脚本继承外部 `UV_PROJECT_ENVIRONMENT`），已修复并加入回归；DOC-10/11 对齐 CI 网络语义并写明 uv 0.12.7 验证基线。当时 Windows Python 3.11.15 与 3.12.13 全套离线测试各为 356 passed, 20 skipped；安装隔离定向用例 8 passed；Ruff、锁文件、敏感文件扫描及 Skill validator 通过。真实 Chromium/抖音、ASR、人工听审、Linux/macOS、远端 CI、Agent 宿主、许可证与发布授权仍未完成；项目仍 NOT READY。详见 PROJECT_AUDIT_REPORT.md。

> 2026-10-09 后续安全差异复核：Codex Security Diff Scan `8537ef61-e6e5-4b6a-8fc7-f162382c098a` 对冻结工作树快照 `aa0314f296588ea1f7b0944b5e02167cfac1d57dea4fe9427d84f6c37f88e84a` 的 28 个代码审查项全部完成复核，未发现新的可报告候选；SEC-25/26 修复所在文件在范围内。此结果只覆盖该静态差异快照，未完成真实 ASR/抖音、Agent 宿主、Linux/macOS/Windows 多账户、远端 CI、许可证与发布授权门槛，项目仍为 `NOT READY`。

> 2026-10-09 文档续审：中文 README 已补虚构 JSON/Markdown 输出样例和计划要求的 7 类 FAQ；新增 `.github/ISSUE_TEMPLATE/bug_report.yml` 与 `feature_request.yml`，明确不收集私人媒体和认证信息。`docs/PROJECT_AUDIT_REPORT.md` 的 DOC-04 记录证据和对策。表单的 GitHub 在线渲染仍待目标仓库发布后确认；不改变真实媒体、Agent、跨平台、远端 CI、许可证与发布授权的未完成状态。

> 2026-10-09 缓存运维文档补记：README 增加每月人工检查建议，以 720 小时为预览示例，并说明先审阅后 `--apply`、可自行设定容量，以及活动/非完成任务媒体受保护。此为手动操作起点，未启用自动清理；`docs/PROJECT_AUDIT_REPORT.md` 记录为 DOC-05。

> 2026-10-09 SEC-15 独立边界复核：对照 `ARCHITECTURE.md` 威胁模型检查 SQLite、Playwright profile、模型下载、缓存写入与输出发布调用链；在私有祖先不可被其他账户修改的假设下，未确认新的跨账户可利用缺陷。第三方 pathname-only API 的 ABA 边界及 POSIX/Windows 多账户实机证据仍未闭合，SEC-15 保持部分整改；详细边界、输出目录例外和平台验收要求见审核报告。

> 2026-10-09 文案一致性复核：修正 CHANGELOG 对旧失败任务的错误描述。无有效配置快照的旧任务默认跳过；只有显式 `--use-current-defaults` 才接受并持久化当前设置。审核报告以 DOC-06 记录。

> 2026-10-09 AUD-64–66 整改续审：文件名 fallback 现在与标题使用相同 basename 清理，空标题/恶意 video ID 的 writer 回归通过；setup 在 uv 与 Chromium 安装后、模型下载前复查模型卷 2 GiB 余量，安装后空间不足则停止下载，并将动态组件空间说明为快照；Markdown frontmatter serializer/task parser 共用 4 Mi 字符上限，解析器逐行有界读取，超限内容在发布前拒绝。Python 3.11.15 Windows 定向测试 107 passed, 3 skipped，全套 366 passed, 20 skipped；Python 3.12.13 全套 366 passed, 20 skipped；全仓 Ruff 通过。Linux/macOS、远端 CI、真实媒体/浏览器/Agent 和发布决定仍待完成。项目仍 NOT READY，详见 `docs/PROJECT_AUDIT_REPORT.md`。

> 2026-10-09 源码续审收尾：AUD-67 将无 deadline 的处理 worker 请求转为一次性默认绝对时限，堵住 stale-task recovery 卡住后无限等待；AUD-68 按解析结果接受大小写不敏感的 HTTPS scheme 和末尾点 Douyin host；SEC-29 将 Markdown 输出 extension 限制为普通后缀，拒绝路径注入。新增回归后，定向测试 57 passed；Windows Python 3.11.15 与 3.12.13 全套各 375 passed, 20 skipped；全仓 Ruff、锁文件、敏感文件检查、Agent Skills validator、仓库外离线干净安装均通过。单提交 Git 历史敏感路径/凭据模式扫描无命中。Linux/macOS、真实媒体/抖音、目标 Agent、远端 CI、许可证与仓库发布授权仍未完成；整体保持 NOT READY，详见 `docs/PROJECT_AUDIT_REPORT.md` 与 `docs/RELEASE_REPORT.md`。

> 2026-10-09 AUD-69 归一续审：修复英文字幕相邻分段的尾随空格丢失，并保留 CJK 不插空格的行为。五个定向测试模块 62 passed；Python 3.11.15 和 3.12.13 Windows 全套各 376 passed, 20 skipped。完整 Ruff、锁文件、敏感文件扫描、Agent Skills validator、仓库外离线干净安装均复核通过。真实音频听审、浏览器/抖音、Linux/macOS、目标 Agent、远端 CI、许可证和发布授权仍未完成；整体保持 NOT READY，详见 `docs/PROJECT_AUDIT_REPORT.md` 与 `docs/RELEASE_REPORT.md`。

> 2026-10-09 本机阶段门复核：本轮在现有 Python 3.11.15 环境及独立 Python 3.12.13 环境分别重跑完整 Windows 离线套件，各 376 passed, 20 skipped；`doctor --json` 返回 `setup_required`，未安装 ASR/浏览器组件或下载模型。AST 检查未发现仅含 `pass` 的函数壳或 `NotImplementedError`。另发现 `uv run --python 3.12 --no-sync` 会在已有 3.11 venv 上警告后继续使用 3.11，已在 `docs/ACCEPTANCE.md` 记录切换前 `uv sync` 并检查 `python --version` 的步骤，审核报告记为 DOC-14。真实媒体、Linux/macOS、Agent 宿主、远端 CI 和许可证/仓库决策仍待完成。

> 2026-10-09 P6 初步许可来源复核：核对了锁定的 faster-whisper 1.2.1、Medium 模型固定 revision、Playwright 1.63.0 与 PyAV 15.1.0 的上游许可证/安装路径，新增 `docs/THIRD_PARTY_LICENSE_REVIEW.md`。PyAV wheel 链接 FFmpeg，但该版本各平台 wheel 内的 FFmpeg 构建配置/notice 尚未核查；完整依赖 SPDX 清单、项目 LICENSE 选择及二进制分发审阅仍待完成，发布门保持 NOT READY。

> 2026-10-09 本轮项目收尾：整改 SEC-30 标题双向控制字符、SEC-31 PyAV 二次资源打开边界、SEC-32 敏感文件扫描静默跳过，并补齐 DOC-16/17 和计划中的三个 examples 文件；后续新增 SEC-33 C1 控制字符边界修复。Windows Python 3.11.15 与 3.12.13 全套均 **382 passed, 20 skipped**，全仓 Ruff、敏感文件扫描和 `git diff --check` 通过。锁定 PyAV 15.1.0 / FFmpeg libavformat 61.7.100 的 Windows 临时环境动态验收通过：HLS 子请求被拒绝且 loopback 请求为 0，合成 WAV 通过。真实 P1/P2/P4/P5、跨平台 CI、许可证及发布决定仍未完成，整体 NOT READY；详见 `docs/PROJECT_AUDIT_REPORT.md`。
