# Douyin Transcript

将抖音视频或本地媒体转为按标题命名的 Markdown 口播逐字稿。目标是本地优先处理、批量断点续跑，并让 Agent 只收到结果路径和状态摘要。

## 当前状态

项目处于 **P0 初始化阶段**。当前交付 Python CLI、只读 `doctor` 环境检查和项目锁文件。语音转写、抖音媒体获取、批处理、Agent Skill 安装均尚未实现；不要将当前版本用于生产转写。

## 环境

- Windows 10/11 优先；项目要求 Python 3.11 或 3.12。
- 使用 `uv` 管理项目和锁文件。
- `doctor` 不会安装依赖、下载模型或创建用户数据目录。
- 默认用户数据目录遵循平台约定；可通过 `DOUYIN_TRANSCRIPT_HOME` 覆盖。Windows 默认使用 `%LOCALAPPDATA%\douyin-transcript`，不会假设 D 盘一定存在。

## 开发命令

从仓库根目录运行：

```powershell
uv run --project .\skills\douyin-transcript --locked douyin-transcript --help
uv run --project .\skills\douyin-transcript --locked douyin-transcript doctor --json
```

环境检查返回 `setup_required` 是当前阶段的预期结果，因为尚未接入 faster-whisper、模型下载和 Playwright 浏览器初始化。

## 计划

实施阶段和验收要求见 [`docs/PROJECT_IMPLEMENTATION_PLAN.md`](docs/PROJECT_IMPLEMENTATION_PLAN.md)。
