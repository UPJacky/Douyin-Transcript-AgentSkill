# 项目审核报告与整改对策

- 审核日期：2026-10-09（Asia/Shanghai）
- 项目：Douyin-Transcript-AgentSkill / `douyin-transcript`
- 审核对象：HEAD `154d9ef` 与当前工作树差异，结合 `f298f11` 以来的实现和历史复核记录；不代表远端仓库或已发布版本
- 审核范围：CLI、URL 与网络边界、浏览器代理、下载、ASR、缓存、SQLite、文件权限、Markdown 输出、Skill 包、CI 与项目验收清单
- 审核方式：源码与验收清单复核、Windows 本地离线单元/模拟测试、Codex Security 工作树差异扫描、Ruff、锁文件检查、Agent Skills 标准校验、仓库外干净安装命令验证；本地补充复测记录见第 9 节
- 范围限制：未访问抖音或真实媒体，未登录账号，未下载模型或 Chromium，未执行远端 CI；Linux/macOS 实机行为未验证

## 1. 结论

项目已有多轮源码整改与离线回归，覆盖敏感路径、配置句柄读取、任务/输出完整性、网络 deadline、下载取消、缓存清理和发布材料。AUD-64 至 AUD-66 阶段的 Windows Python 3.11.15 和 3.12.13 全套离线测试均为 **366 passed, 20 skipped**；此前统一快照为 **376 passed, 20 skipped**。本次本地续审后 Windows Python 3.11.15 和 3.12.13 全套均为 **382 passed, 20 skipped**。AUD-64/66 已完成本地整改与回归；AUD-65 已加入模型下载前的空间复查，uv/Chromium 动态占用仍只能预估，setup 明确预检只是快照。DOC-07 至 DOC-11 的 Skill 隐私、安装和 CI 说明已统一，ENG-02 已隔离干净安装脚本的虚拟环境。跳过项是 POSIX 专属权限/FIFO/symlink 用例或本机 symlink 能力限制，不能替代 Linux/macOS 实测。AUD-52 仍开放：安全创建后的身份校验失败可能留下私有文件或目录，当前策略保留对象并明确提示，避免按可变名称竞态删除。真实 ASR、抖音/Chromium、人工听审、性能记录、目标 Agent、远端 CI、许可证选择和发布授权尚未完成，整体 **NOT READY**。

2026-10-09 独立复核发现 AUD-56（已整改）：缓存扫描与批量规划已移出 SQLite 写事务，删除前按单个候选短暂协调任务引用并复核文件身份；两个写连接和活动下载竞态已有回归。后续复核另发现 AUD-57（已整改）：已记录的本地源文件也纳入缓存保护。AUD-58 至 AUD-63 已完成本地代码整改和回归；真实 Chromium 集成仍待 P2 验收，见第 4 节及 P2 门槛。DOC-07 至 DOC-11 和 ENG-02 已修复并加入回归覆盖。

本轮曾发现重试解析失败后的任务状态、缓存恢复、并发本地重试和 claim generation 参数校验缺口；现已在任务/CLI/pipeline 路径修复，并覆盖相应回归。Skill 正文隐私规则、基础环境安装授权步骤、`--no-sync` 入口及干净安装环境隔离也已统一。修复依据和剩余集成限制见 AUD-59 至 AUD-63、DOC-07 至 DOC-09、ENG-02。

源码与计划复核新增 AUD-24 至 AUD-29。AUD-24/25/26/28/29 已完成源码整改和离线回归；AUD-27 通过实现显式 `--skip-existing` 并将首版媒体缓存/可选 turbo 范围写清，完成了计划与实现对齐。本轮整改 AUD-45，为 doctor、dry-run、转写和重试加入实际目标目录权限提示；复核重试参数时另发现 AUD-46，显式重试输出目录未写回配置快照，也已修复。CLI/doctor 定向回归 **58 passed, 2 skipped**，改动文件 Ruff 通过。真实 CDN、浏览器 DNS、ASR 质量和执行时间尚未验证。

P6 本地清单复核另发现 CI 只运行测试与 Ruff，没有项目计划要求的敏感文件检查；现已添加 [check_sensitive_files.py](../scripts/check_sensitive_files.py) 并纳入 GitHub Actions。它对 Git 可见路径拦截已知媒体/数据库/浏览器资料目录，对小型 UTF-8 文本检查高置信度凭据模式，诊断不会打印匹配的凭据值。该检查不是通用 secret scanner，也不扫描完整 Git 历史；发布前仍需审阅历史。

复核新增 SEC-20 至 SEC-26 与 AUD-30 至 AUD-44。SEC-20 的词法 `..` 路径差异已拒绝，配置读取现在从通过权限检查的同一文件句柄解析；POSIX 使用目录句柄逐组件打开，Windows 对叶文件使用 reparse-aware handle 并从该句柄读取 ACL。SEC-21 的词典匹配工作量现在有累计预算；SEC-22 通过私有 SQLite 摘要绑定主稿；AUD-30/34/35 修复了旧配置 opt-in、本地失败重试状态和 force 快照更新。AUD-32/33 已将短链与浏览器 CONNECT 的解析、连接和响应步骤纳入 deadline，超时关闭 socket 并释放代理槽。SEC-23 已按实际解码样本累计时长并逐帧检查配置上限，也会跳过与 faster-whisper 一致的可恢复 `InvalidDataError`；真实媒体格式样本尚未验收。AUD-38 的重复全解码已通过验证身份交接整改并有回归，长媒体性能基准仍待授权样本。AUD-10 使用有界 JSON IPC worker；下载阶段现在受共享 deadline 限制，重试恢复原超时值，显式覆盖会更新快照。SEC-24 和 AUD-44 对敏感配置、URL 清单及词典 FIFO 使用非阻塞打开并按文件类型拒绝。SEC-25/26 的 Python 子进程已启用 safe-path，影子模块回归通过。AUD-39 统一 downloader 校验类型；AUD-43 现先将时间轴路径和摘要写入任务库，再原子发布；完成、skip、crash recovery 都验证 sidecar。旧 schema 中 completed/writing 且时间轴设置未知的任务 fail closed。上一轮结构化扫描的 5 项发现和此前 28 项 Diff Scan 的 1 项发现均绑定各自启动快照。2026-10-09 又完成一轮正式 Codex Security Diff Scan（Scan ID `8537ef61-e6e5-4b6a-8fc7-f162382c098a`，快照 digest `aa0314f296588ea1f7b0944b5e02167cfac1d57dea4fe9427d84f6c37f88e84a`）：28/28 个变更审查项完成复核，未发现新的可报告安全候选，扫描器 coverage 对该冻结差异为 complete。该结果不覆盖运行时行为和产品验收；POSIX 扩展 ACL、真实媒体/浏览器、Agent 宿主、远端 CI 等仍待验证。

`retry-failed` 为新任务恢复非正文配置快照；旧任务无有效快照时默认跳过，只有显式 `--use-current-defaults` 才按当前配置排队。AUD-45 已将权限提示应用到配置目录和本次实际输出目标；AUD-46 已确保显式重试输出目录覆盖值写回快照。AUD-54/55/59–69 与 SEC-29 的本地整改均有回归覆盖；此前 Windows Python 3.11.15 和 3.12.13 全套均为 376 passed, 20 skipped。本次 Python 3.11.15 和 3.12.13 全套均为 382 passed, 20 skipped。POSIX 扩展 ACL、真实媒体格式、SEC-15 其他 pathname-only/TOCTOU 边界、SEC-16 fallback、SEC-17/18、AUD-21 多机/真实缓存/第二账户集成仍待验收。SEC-14 需目标 Agent 宿主验证。真实本地 ASR、真实 Chromium/抖音链路、跨平台远端 CI、真实 Agent 调用和许可证决定仍未完成。缓存需用户主动清理。项目仍未达到真实产品与发布门槛。

### 1.1 当前未完成项与对策（按项目阶段排序）

| 优先级 | 当前证据 / 问题 | 完成对策 |
|---|---|---|
| P1，最早未通过阶段 | `doctor --json` 为 `setup_required`；Skill 项目虚拟环境中未安装 faster-whisper、PyAV，也未下载固定模型；没有获授权的至少 60 秒中文口播样本，故真实逐字稿质量、资源占用和运行时间未验证 | 由用户提供仓库外的授权样本，并明确批准在线安装锁定依赖、下载固定 medium 模型到私有数据目录；使用 `doctor` 确认的安全输出目录，实际生成非空 UTF-8 Markdown、人工抽听并填写 `P1_REPORT.md`。默认工作区输出目录因 `D:\` 祖先 ACL 不安全；本机显式检查 `%USERPROFILE%\Transcripts` 返回权限 `ok`，但该目录尚未创建且不代表 ASR 已就绪 |
| P2，须在 P1 后 | 未安装 Playwright/Chromium，未打开任何抖音页面；三条授权视频和登录/失败路径均未验收 | P1 通过后，用户提供至少 3 条有权访问的视频链接并授权可见浏览器测试；手动登录，不绕过验证码、DRM 或访问控制，记录脱敏验收结果到 `P2_REPORT.md` |
| P3，本地模拟通过，正式阶段门受 P1/P2 限制 | 去重、任务持久化、重试、恢复、中断、并发和 50 条模拟批次有离线回归；没有真实下载/ASR 批次 | 保留离线证据；P1/P2 真实链路可用后再做授权批次和断点恢复验收，不以模拟结果代替阶段门 |
| P4，部分完成 | 正文不进入 CLI 摘要、输出质量规则和词典控制有源码/测试覆盖；没有真实逐字稿听审、长音频耗时和重复内容记录 | P1 后完成至少三处听审与 10 分钟以上样本检查，记录真实耗时、漏转/幻觉/重复情况及 stdout/stderr 泄漏检查 |
| AUD-65，动态依赖空间无法精确预估 | setup 仍无法准确估算 uv 环境、缓存和 Chromium 的平台相关体积；已调整安装顺序，并在 uv 与 Chromium 完成后、模型下载前复查模型卷至少 2 GiB | 继续把未知组件的空间值作为快照提示，不声称容量保证；真实授权安装后记录各目标卷消耗。若空间不足，模型下载前停止，避免继续占用模型目标卷 |
| SEC-15，安全整改部分完成 | 目录/文件创建路径已局部加固；SQLite、Playwright、模型等第三方接口仍按路径名工作。当前未证实跨账户利用 | POSIX 使用 dir-fd 相对创建并在同一 fd 上核验；Windows 使用受保护 DACL 创建并复核目录/文件句柄身份。当前 Windows 回归通过；POSIX 实机、Windows 多账户和第三方 pathname-only 边界仍待验收 |
| SEC-27，映射网络盘识别 | **源代码已整改并通过 Windows mock 回归**：`GetDriveTypeW()` 拒绝 `DRIVE_REMOTE`，对未知/无根盘类型 fail closed；本机 C:、D: API 结果均为固定盘，当前没有真实映射盘可供集成验证 | 在有映射盘的 Windows 环境确认诊断结果；UNC/device namespace 仍按原规则拒绝 |
| AUD-52，安全创建失败后留下新对象 | **已加入失败提示与排障说明，按安全策略保留残留**：对象仍可能存在，但错误会告知并提醒先核对身份；Windows 与 POSIX 回归均有残留提示断言 | 不做有 name-based 竞态的通用自动回滚；后续若做 Windows 文件句柄绑定清理，必须失败关闭。POSIX 分支已加断言但本机为 Windows，仍待 Linux/macOS CI 运行 |
| AUD-53，崩溃恢复期间媒体校验占用 SQLite 写锁 | **已整改并通过并发回归**：媒体校验与输出摘要校验移到事务外，提交前比对原任务快照，跳过已续租或已变化任务 | 两连接写入和任务续租回归通过；真实长媒体和跨平台 SQLite 集成仍待验收 |
| AUD-56，缓存清理长时间占用 SQLite 写锁 | **已整改**：目录扫描/计划在事务外完成；每个候选仅在短事务内复查任务引用并做一次身份绑定删除；两连接并发回归通过 | Python 3.11/3.12 本轮全套均通过；极慢的单次文件系统删除仍可能延长单个事务 |
| AUD-57，缓存清理可能误删本地输入 | **已整改**：TaskStore 查询并保护所有已记录的 local_path，含已完成任务；新增回归 | app media-cache 是程序管理目录；尚未登记为任务、但由用户自行放入且恰好匹配下载器命名的文件无法仅凭名称识别为原始输入。建议不要把未登记的源文件放入该保留目录 |
| AUD-58，浏览器流量边界（P2 集成待验收） | **代码已加固**：context 请求路由在建页前注册、阻断 Service Worker、校验 WSS 域名和公网解析、代理设置 `bypass="<-loopback>"` | Fake Playwright/proxy 回归 21 passed；真实 Chromium、popup、loopback/链路本地和抖音 WSS 集成仍需 P2 授权验收 |
| AUD-59，远端重试解析失败后留在 pending | **已整改**：未认领的 pending retry 在 URL 解析失败时按 task/generation 条件恢复 failed；worker 写入要求 claim generation | CLI/task/pipeline 回归覆盖解析失败状态回退和并发认领保护；相关回归组 110 passed，Ruff 通过 |
| AUD-60，失败重试未直接从任务缓存恢复 | **已整改**：claimed retry 先验证任务记录的 `media_path`，有效缓存直接进入 downloaded，缓存无效才回到捕获/下载 | pipeline 回归覆盖缓存恢复和无效缓存回退；相关回归组 110 passed，Ruff 通过 |
| AUD-61，并发本地重试产生误报失败 | **已整改**：本地 retry 使用原子 claim；竞争进程重新读取任务状态，已推进的任务按状态返回 skipped/locked | 两个 CLI 并发重试和状态变化回归；相关回归组 110 passed，Ruff 通过 |
| AUD-62，TaskStore claim generation 可省略 | **已整改**：有 worker ID 的状态写入必须带 claim generation，旧 generation/缺少 generation 均不能通过 owner fencing | tasks/pipeline/downloader/CLI 定向回归覆盖旧 worker 与同 ID 复用；相关回归组 110 passed，Ruff 通过 |
| AUD-63，Python 3.12 全套测试时间戳敏感失败 | **已整改**：缓存竞态 fixture 显式回拨 mtime；媒体身份测试从校验所用句柄采集身份，避免事后路径 stat 的 ctime 竞态 | 整改时 Windows Python 3.11.15 和 3.12.13 全套均为 356 passed, 20 skipped；当前结果见第 2 节。缓存竞态及句柄身份用例各重复 5 次通过。POSIX 专属跳过项仍需相应平台验证 |
| DOC-07，Skill 对逐字稿正文处理规则不一致 | **已整改**：Skill 现在明确禁止将正文载入 Agent 上下文，包括审阅/引用请求，并指向本地 Markdown | README、Skill 和计划口径统一；固定版 Agent Skills validator 通过 |
| DOC-08，首次 Skill 调用可能隐式同步安装 | **已整改**：首次运行前说明基础 sync 的网络与文件写入影响并取得用户同意；初始化后的 CLI 命令使用 `--no-sync` | SKILL、INSTALL 和中英文 README 已同步更新；固定版 Agent Skills validator 通过 |
| DOC-09，wrapper 与部分 CLI 示例仍可能隐式同步 | **已整改**：Windows/Unix wrapper、CLI reference、README 和开发命令均加入 `--no-sync` | 新增静态回归扫描 Skill/安装文档/README/wrapper 的锁定 `uv run` 命令；Windows Python 3.11/3.12 全套回归通过 |
| ENG-02，干净安装检查可能写入调用者指定的虚拟环境 | **已整改**：子进程环境现将 `UV_PROJECT_ENVIRONMENT` 固定在复制的 Skill `.venv` 中 | 新增环境隔离单元回归；设置外部目标环境变量后，仓库外离线安装冒烟通过且外部路径未创建 |
| DOC-10，CI job 名称暗示整个流程离线 | **已整改**：job 改名为 `ci-checks`，验收材料说明冷 runner 的依赖安装可访问包索引，lint/test 进程离线 | 只调整名称和说明，不改变 CI 执行方式；远端矩阵尚未运行 |
| DOC-11，安装材料未标明已验证的 uv 版本 | **已整改**：中英文 README、INSTALL 和 Skill metadata/instructions 指出 CI 当前固定 uv 0.12.7，旧版本未经验证 | 根据当前 CI pin 和本机 `uv 0.12.7` 记录可复现基线；没有宣称更早版本可用 |
| AUD-54，恢复后旧 worker 仍可改变任务状态 | **已整改**：pipeline 丢失 heartbeat 会取消该任务处理，TaskStore worker 状态写入强制 claim generation，见 AUD-62 | 旧 worker、worker ID 重用、claim recovery 与子任务取消回归通过；Windows Python 3.11/3.12 全套均通过 |
| AUD-55，Python 3.12 Windows 缓存删除身份不匹配 | **已整改并通过本轮全套门禁**：Python 3.12+ Windows 使用 FILE_ID_INFO 的 64 位 volume serial 与 128 位 file ID；3.11 保留旧 API 路径 | 缓存清理定向回归及 Python 3.11/3.12 全套均通过；远端 CI 尚未运行 |
| SEC-28，敏感文件扫描遗漏通用 cache/ 目录 | **已整改并通过回归**：扫描器现在按路径拒绝任何 Git 可见的 `cache/` 目录内容，不依赖文件扩展名/文本解码 | 离线扫描器回归通过；发布前仍须人工审查完整 Git 历史 |
| AUD-45/AUD-46，输出隐私诊断与重试快照 | 源码现检查配置目录、显式目录及重试快照目录；显式 `retry-failed --output-dir` 现在也持久化为该任务的新输出路径 | 已完成本机实现和回归；在 macOS/Linux 及 Windows 多账户 ACL 环境验证共享/未知路径诊断和继承行为，保持对已有目录只提示、不擅改 ACL |
| P5，部分完成 | Skill validator 与离开仓库目录的离线干净副本安装/CLI dry-run 通过；真实 Agent 宿主调用未验证 | 在目标 Agent 宿主进行一次真实对话调用并确认只返回路径/简短状态；若调用真实媒体，仍须遵循 P1/P2 授权门槛 |
| P6，尚未发布就绪 | 本机实现检查点 `f298f11` 已提交；无 remote、无远端 CI/GitHub 安装记录、无 LICENSE 决定 | 仓库所有者确认归属、名称、可见性、许可证和远端授权；配置 remote 后运行矩阵 CI 并验证远端干净安装 |
| 安全覆盖 | 最新记录的 Diff Scan `fd9a73df-3590-47b3-aada-ab36bde2fd61` 完成该冻结差异内 3/3 个源码审查项，0 项新候选；较早的 `484bb340-323c-4bec-a20a-368b2fcd077d` 完成 30/30 项；此前 Deep Scan 因缺少 managed filesystem permission profile 未启动 | 两次差异扫描都不覆盖全仓和平台运行时；POSIX ACL、Windows 多账户、真实浏览器/媒体和 Agent 宿主验收完成前，项目整体验收 coverage 仍为 partial |
| AUD-47，代理隧道转发反压 | **已修复并本机回归**：非阻塞双向转发有 256 KiB 缓冲上限和 60 秒写等待上限；目的端停读后关闭隧道并释放槽位 | Linux/macOS 与真实 Chromium CONNECT 集成仍待平台验收；无新增代码对策 |
| AUD-48，批量转写 Ctrl+C | **已修复并本机回归**：取消信号关闭活动下载连接、打断退避、取消待执行任务，并尽快关闭捕获/处理子进程；任务记为可重试的 `CANCELLED` | 有 deadline/取消的 DNS 现由 AUD-50 子进程处理并在退出时终止、回收；不带 deadline/取消的直接 helper 调用仍同步使用系统 resolver。真实 DNS、Chromium 与跨平台下载中断仍待集成验证 |
| AUD-49，sidecar 崩溃恢复覆盖 | **已补齐回归**：先持久化预期 sidecar 路径/摘要，再模拟成功发布、缺失和摘要不符；只有绑定内容有效时才完成恢复 | Linux/macOS 文件系统行为仍待平台验收；无新增代码对策 |
| AUD-50，DNS 查询线程耗尽解析名额 | **源码已整改并通过回归**：有 deadline/取消的解析由隔离子进程执行，超时或取消后强制停止并回收；两个阻塞 worker 取消后名额可复用 | 无 deadline/取消的直接 helper 仍同步调用系统 resolver；当前 CLI 网络路径提供时限。需在真实 DNS、Chromium 与 POSIX 平台集成中验证进程终止语义 |
| AUD-51，Windows 权限诊断误报 | **本机已修复并回归**：foreign ACE 仅授予目录遍历/同步权限时不再判为可读取或可修改；读取、写入、删除及通用读取权限仍拒绝 | `%USERPROFILE%\Transcripts` 当前报告 `ok`（只检查最近现存父目录，未创建目标）；默认 D: 工作区输出目录仍为 `unsafe`。需在更多 Windows ACL 组合与多账户环境验证继承/有效权限语义 |

## 2. 验证结果

| 检查 | 结果 | 适用范围与限制 |
|---|---|---|
| P0 CLI 启动与 doctor | **符合预期** | `douyin-transcript --help` 返回 0；`doctor --json` 返回 `setup_required`/退出码 1，并明确列出尚未安装的组件。doctor 没有创建数据目录或下载文件；缺少依赖是 P1 的环境门槛，不是 CLI 崩溃 |
| Windows Python 3.11.15 离线 pytest（本轮源码与文档整改后） | **通过：382 passed, 20 skipped** | 当前代码全套结果；POSIX FIFO、权限、symlink 和 dir-fd 替换用例因平台限制跳过，不代表 Linux/macOS 行为已实机验证 |
| Windows Python 3.12.13 离线 pytest（本轮续审后，独立临时环境） | **通过：382 passed, 20 skipped** | 使用锁定开发依赖在仓库外独立环境运行；POSIX FIFO、权限、symlink 和 dir-fd 替换用例因平台限制跳过；远端 GitHub Actions 尚未运行 |
| AUD-64–66 定向 pytest | **通过：107 passed, 3 skipped** | 覆盖不可信 fallback 输出 containment、依赖安装后模型空间复查、由控制字符扩大的真实术语 archive frontmatter、超限元数据在发布前拒绝。跳过为本机 symlink/FIFO 限制 |
| SEC-15 独立复核及本轮整改 | **SEC-27 源码已整改；AUD-52 已加入提示并按私有残留策略处置** | 映射盘拒绝、unknown 诊断、失败创建残留提示有 Windows mock 回归；本机 GetDriveTypeW 将 C:、D: 识别为固定盘。没有真实映射盘可做集成验证，POSIX 消息行为未在本机实测 |
| 配置、存储、doctor 与 CLI 定向 pytest | **通过：92 passed, 14 skipped** | 覆盖 Windows 创建/目录身份、配置句柄读取、doctor 与 CLI 路径检查；POSIX dir-fd、symlink、FIFO 和替换回归在本机跳过 |
| 最新全仓 Ruff | **通过** | 本轮复跑 `uv run --project .\skills\douyin-transcript --locked --no-sync --group dev ruff check .\scripts .\skills\douyin-transcript\src .\skills\douyin-transcript\scripts .\tests` 返回 `All checks passed!` |
| Skill 仓库外干净副本安装 | **通过** | `scripts/check_clean_skill_install.py` 在独立副本执行 locked no-dev 安装，确认 import 来自副本并通过 `--version` 与 URL dry-run；本机 `UV_OFFLINE=1` 通过。远端矩阵尚未运行 |
| AUD-32/33 网络定向 pytest | **通过：26 passed** | 覆盖多跳共用 deadline、阻塞 DNS 超时、CONNECT 超时关闭及代理槽位恢复；未访问网络 |
| `uv lock --project .\\skills\\douyin-transcript --check` | **通过** | 锁文件和项目依赖元数据一致 |
| `git diff --check` | **通过（跟踪文件）** | 仅有 Git 的 LF/CRLF 转换提示；命令不检查未跟踪文件 |
| `uvx --offline --from skills-ref==0.1.1 agentskills validate skills/douyin-transcript` | **通过** | 固定版本标准校验器返回 `Valid skill` |
| `python scripts/check_sensitive_files.py` | **通过** | 扫描 Git 可见路径和小型 UTF-8 文本中的高置信度敏感文件/凭据模式；不打印匹配值。只检查当前树，不代替完整历史审查或通用 secret scanner |
| `setup` 确认前来源/目标披露 | **通过（本机回归）** | 确认前显示模型 repo/revision、锁文件 registry、uv 环境、HF_ENDPOINT 和模型/浏览器目标；自定义源只显示 scheme/host/port。新增测试确认 HF_ENDPOINT 覆盖值可见且用户、密码和 query token 均脱敏 |
| `setup` 磁盘预检（AUD-65） | **已加模型下载前复查；组件空间仍是快照** | Chromium 安装现在先于模型下载；uv 和 Chromium 完成后重新检查模型目标卷，低于 2 GiB 或无法查询时停止模型下载。uv/Chromium 的实际空间需求随环境变化，未构造固定容量保证 |
| 输出完整性前置元数据解析（AUD-66） | **已修复并通过回归** | serializer 与 `_frontmatter()` 共用 4 Mi 字符上限；解析器在该边界内逐行找结束分隔符，生成端超限会在原子发布前拒绝。控制字符扩大的真实术语归档测试及超限无文件发布测试均通过 |
| 初始提交历史检查 | **通过（初始提交 1 个、15 个路径）** | 对初始化提交 `3e06080` 的文件路径和高置信度凭据模式检查未发现敏感文件名或命中。实现检查点 `f298f11` 的当前 Git 可见树提交前已通过敏感文件扫描；完整历史仍须在发布前复核。当前无 remote，因此没有远端分支/历史可查 |
| 新增功能差异复核 | **五项源码整改通过离线回归；一项通过范围对齐** | AUD-24/25/26/28/29 已修改；AUD-27 的 `--skip-existing` 已实现，V1 明确保留媒体缓存并通过 `cache clean` 管理；可选 turbo 档推迟到真实模型验收后 |
| 上一轮结构化安全扫描与修复复核 | **已完成：5 项源码发现（1 项中危、4 项低危），coverage partial** | 涵盖配置路径检查/读取不一致、术语匹配 CPU 工作量、远端输出关联真实性、短链 deadline、浏览器代理二次 DNS deadline。SEC-23 源码已改为计数实际解码帧，但真实畸形时长样本与损坏帧兼容性仍待确认；项目估算 75 个文件，本轮没有逐文件覆盖全仓。扫描工具提示扫描期间工作树变化，结构化报告对应启动时快照。 |
| 上一轮 Codex Security Deep Scan | **未启动；不能视为无发现** | 当时扫描协调器拒绝启动只读 worker，原始原因是缺少 managed filesystem permission profile。此结果仅说明 Deep Scan 未运行；本轮另行成功完成了工作树差异扫描。 |
| 上一轮 Codex Security Diff Scan（历史快照） | **完成：28/28 项变更文件全文件复核，发现 1 项中危；coverage partial** | Scan ID `422a6e6d-f1d0-45c7-8bba-d1f3a739f489`，快照 digest `895ffbacea7923b7dfd387f768b7131c7c88fe34e1b786724c20c9f48b41b7d3`。该快照不包含之后的 SEC-25/26 修复。 |
| 最新 Codex Security Diff Scan（2026-10-09） | **完成：3/3 项源码审查项复核，0 项新候选** | Scan ID `fd9a73df-3590-47b3-aada-ab36bde2fd61`，快照 digest `310d9cb80df88511cea4e51cd1e9e7e4ea8a7e01d71f958eba88ab6465775dcf`。这是静态、冻结差异扫描；不替代真实媒体、浏览器、Agent 宿主、POSIX ACL、远端 CI 或全仓验收。较早扫描 `484bb340-323c-4bec-a20a-368b2fcd077d` 的 30/30 项仍按其快照有效；SEC-31 锁定 PyAV 15.1.0 的 Windows 动态验收随后已通过，见第 9 节。 |
| 仓库外独立干净副本安装 | **最新复测通过** | 从 Skill 副本排除源 `.venv`、pytest/Ruff 缓存，在 `%TEMP%` 创建显式独立虚拟环境；`UV_OFFLINE=1` 锁定 no-dev 安装通过。从仓库外验证导入路径来自副本，`--version` 和直链 `--dry-run --json` 通过。未下载 ASR/浏览器依赖，dry-run 未访问媒体或创建运行时 data/output 目录 |
| `doctor --json` | `setup_required`；敏感数据路径权限 `ok` | 缺 faster-whisper、PyAV、模型、Playwright、Chromium；未创建数据目录或下载。当前 `%LOCALAPPDATA%` 链被拒后，默认选择 `%USERPROFILE%\.local\share\douyin-transcript`，其尚未创建状态和数据库/profile/cache 父路径报告 `ok`。默认工作区输出路径仍因 `D:\` 向 Authenticated Users 授予目录替换权限报告 `unsafe`；显式 `%USERPROFILE%\Transcripts` 检查为 `ok`，目标未创建 |
| GitHub Actions 矩阵 | **未运行** | 工作流已添加，但没有远端 GitHub 运行记录 |
| 真实本地媒体与抖音链接 | **未验证** | 本轮按范围约束不读取真实素材或访问抖音 |
| 前次续审全套本地复测 | **通过：308 passed, 17 skipped** | 此为 AUD-47/48 修复前快照；使用离线锁定依赖与 profile 下新建的 pytest 临时目录。跳过项是 POSIX 专属行为和本机 symlink 创建受限用例 |
| 最近一次 Codex Security Deep Scan 尝试 | **未启动** | 协调器返回“the parent must provide a managed filesystem permission profile”；没有扫描工件，不能据此推断无漏洞。既有 28 文件 Diff Scan 不等价于全仓 Deep Scan |
| 本次定向源码复核与 AUD-45/AUD-46 修复 | **通过：58 passed, 2 skipped；Ruff 通过** | 检查 pipeline、ASR/worker、URL/下载、浏览器捕获与代理、输出命名及 CLI；回归覆盖 doctor 显式目录、dry-run/转写 JSON、文本警告、重试快照目标和显式重试覆盖持久化。两个跳过项为 Windows 不支持的 POSIX FIFO 用例；未执行真实媒体/网络或 POSIX ACL 集成 |

## 3. 上轮问题状态

本节部分问题的测试数量记录的是整改完成时的历史快照；最新结果见第 2 节和文末 2026-10-09 续审记录：Windows Python 3.11.15 与 3.12.13 均为 382 passed, 20 skipped。此前 303/17、308/17、315/17、316/17、323/17、325/20、331/20、334/20、337/20、340/20、356/20、366/20、375/20 和 3.12 的 376/20 均为对应阶段历史快照。

| 原编号 | 当前状态 | 复核摘要 |
|---|---|---|
| AUD-01 CLI 选项和有界下载队列 | **已实现** | 有 `--dry-run`、`--max-downloads`（1–2）、`--retry`（0–2）；下载并发有界，ASR 串行；有对应 CLI/pipeline 模拟测试。短链 dry-run 可能发起 HTTPS 跳转解析，文档已说明。 |
| AUD-02 术语词典 | **已实现** | 需要显式提供 JSON 词典才生效；逐字面、区分大小写、默认不替换，并记录规则哈希和替换计数。 |
| AUD-03 CI 与发布材料 | **部分完成** | Windows/macOS/Linux 与 Python 3.11/3.12 矩阵、贡献指南、英文 README、CHANGELOG、SECURITY、独立安装指南和示例配置已添加；Action 已固定完整 SHA，但远端未运行。许可证尚未由仓库所有者选择。 |
| AUD-04 Skill 与真实链路验收 | **部分完成** | Agent Skills 校验器和仓库外干净副本 CLI 冒烟通过；真实 Agent 对话调用、真实模型、真实视频仍未验证。 |
| AUD-05 缓存策略 | **部分完成** | `cache inspect` 与默认预览的 `cache clean` 已实现，支持显式容量/保留期；没有自动上限或自动清理，长期使用仍可能持续占用磁盘。 |
| AUD-06 / AUD-07 | **仍待外部验收** | 真实 ASR、真实抖音捕获、跨平台远端 CI 未验证；具体门槛见下文。 |
| AUD-09 / AUD-13 | **已整改** | CI Action 固定到完整 commit SHA；medium/small 模型下载使用完整 Hugging Face revision，来源与范围记于 `references/MODEL_PROVENANCE.md`。未下载权重或运行真实模型。 |
| SEC-06 至 SEC-08 | **已整改** | 标题控制字符在 CLI/Markdown 边界过滤；词典输出逐段执行字符预算；URL 文件和批次有字节、行长、条数限制。该项整改时的完整离线测试为 **303 passed, 17 skipped**；当前全套结果见第 2 节。 |
| SEC-09 Skill 命令参数未要求安全传递 | **已整改；宿主调用待验收** | Skill 现在把命令示例写成 argv 数组，并要求宿主对所有动态 URL/路径使用结构化参数；仅支持 shell 文本的宿主须使用 shell 专属转义。`agentskills validate` 通过，真实宿主调用未验证。 |
| SEC-10 Windows 既有敏感路径未校验所有者 | **已整改；多账户 ACL 实机验证待完成** | `_inspect_windows_path` 现在先验证 owner SID 是否属于当前用户、SYSTEM 或 Administrators，再检查 allow ACE。新增策略回归用例拒绝其他账户 SID；本机没有进行第二账户目录 ACL 实测。 |
| AUD-14 setup extras | **已整改** | `setup` 使用 `uv sync --inexact`，避免分两次安装模型和浏览器依赖时精确同步移除此前 extra；补充 CLI 测试。uv 的同步语义见 [官方说明](https://docs.astral.sh/uv/concepts/projects/sync/)。 |
| AUD-15 quiet / 时间轴 | **已整改** | `--quiet` 保留成功路径、失败码和最终计数；异常乱序 ASR 分段的时间轴按起始时间排序，主稿仍按 ASR 输入顺序保留。新增回归测试。 |
| AUD-16 retry 配置快照 | **已整改（旧记录显式选择配置）** | 新任务保存并恢复语言、时间轴、资源限制、重试/并发设置、词典规则和输出目录；`--force` 重跑会刷新最近一次快照，`--output-dir` 可显式覆盖。旧任务缺快照时默认跳过；`--use-current-defaults` 会明确采用并持久化当前配置。 |
| AUD-17 50 条混合批次 | **已通过离线模拟** | 新增 50 条任务集成用例，覆盖缓存命中、失败、重复、下载并发上限、ASR 串行、结果与任务数及模拟缓存/输出占用。该模拟不代替真实网络、ASR 或跨平台验收。 |
| AUD-18 发布文档 | **本地材料已补齐；真实验收待做** | 新增英文 README、CHANGELOG、SECURITY、独立 Skill 安装说明和示例配置；P1/P2/benchmark 文件目前是 `NOT VERIFIED` 模板，许可证和外部验收证据仍未完成。 |
| AUD-22 setup 来源与目标披露 | **已整改并覆盖回归** | 确认前显示锁定模型 revision、软件包 registry、可见自定义源主机、HF_ENDPOINT 主机、uv 环境及模型/浏览器目录；新增测试确认 HF_ENDPOINT 覆盖及凭据脱敏。 |
| AUD-23 setup 磁盘空间预检缺失 | **已整改** | 确认前显示各安装目标卷可用空间；模型卷低于 2 GiB 或无法查询时 fail closed。低空间回归确认不提示授权、不安装、不下载、不建数据目录。 |
| AUD-24/25/26/28/29 | **已整改并通过离线回归；真实服务待验收** | 分别覆盖媒体时长、缓存字节/时限、浏览器 DNS deadline、候选失败码摘要和通用 ASR 默认提示词。AUD-27 已通过实现显式跳过选项并对齐 V1 媒体缓存/可选 turbo 范围关闭。 |
| SEC-19/20 配置路径及句柄读取 | **源码整改；POSIX 与多账户集成待验收** | 拒绝 `..` 组件；POSIX 从已打开目录 FD 逐段 `O_NOFOLLOW` 打开，Windows 对叶文件以 reparse-aware handle 校验 ACL 并从同一 handle 读取。配置解析消费完成校验的同一描述符。 |
| SEC-15 敏感目录检查与按路径名使用的竞态 | **创建边界已缩小；跨账户攻击未证实，集成待验收** | `ensure_private_directory()` 在 POSIX 使用目录 fd 相对逐段创建/打开并核对对象身份；Windows 新文件在 `CREATE_NEW` 时设置私有 DACL，并通过句柄核验文件和目录身份。`TaskStore` 已保留数据库路径的词法别名。SQLite、Playwright、模型下载、下载器缓存和输出验证仍有 pathname-only 检查/使用边界。当前 Windows 文件系统不允许创建 symlink 的用例会跳过。POSIX mode 与 Windows ACL 用于阻止不可信账户替换受保护祖先；同 UID、管理员/root 和非标准 ACL 不在保证范围。详见下方限制与对策。 |
| SEC-21 术语匹配资源消耗 | **已整改并通过定向离线回归** | 前缀树匹配保留最长有效规则和 ASCII 边界；规则/Trie 大小有硬上限，正文与时间轴共用 2,500 万次转换预算。 |
| SEC-22 输出关联完整性 | **已整改并通过定向回归；文件句柄集成待后续评估** | pipeline 和 Markdown writer 不再按公开 `video_id` 复用既有文件；任务库保存本次渲染预期字节的 SHA-256，完成/跳过/恢复均验证私有摘要和任务关联。旧 schema 没有摘要的完成记录需要 `--force` 重建。 |
| SEC-23 媒体时长上限 | **源码与模拟回归已整改；真实样本待验收** | PyAV 逐帧累计样本时长并及时检查配置上限；低报元数据、超限早停和可恢复坏帧均有模拟回归。真实容器样本仍未验证。 |
| AUD-38 完整解码重复扫描 | **源码整改并通过回归；真实性能基准待授权媒体** | 默认本地和新下载远端任务现在各做一次完整时长校验；校验结果携带解码句柄的文件身份交给 ASR，ASR 核对身份后从打开的文件对象读取，不再重复预检。缓存恢复路径也只做一次当前校验。真实长音频 CPU/总耗时仍未测量。 |
| AUD-10 媒体下载/预检/ASR 墙钟超时 | **源码整改并通过本机回归；真实解码器和跨平台待验收** | pipeline 将每条任务的绝对 deadline 传给 downloader，下载器在自身 300 秒上限和该 deadline 中取较短值；处理期限到期返回 `PROCESSING_TIMEOUT`，ASR/解码由超时可杀的 JSON IPC worker 执行。默认 2 小时，可通过 CLI 调整，硬上限 24 小时。重试快照恢复同一时限。真实 PyAV/模型运行仍未验证。 |
| AUD-32/33 网络等待上限 | **已修复并通过定向回归；平台集成待验收** | 短链全跳共用 30 秒 deadline；CONNECT 的解析、连接、响应写入在一个 deadline 内，超时关闭客户端并释放代理槽；allowlist 和公网 IP 校验保留。 |
| AUD-30/34/35 retry 行为 | **源码整改并通过定向回归** | 缺少配置快照的任务默认不重试，显式 opt-in 会持久化所选当前设置；本地 retry 先验证原路径和内容摘要；`--force` 重开任务原子更新 profile/title/options。 |
| SEC-24 配置 FIFO 阻塞 | **加入非阻塞保护；POSIX 实机测试待跑** | 打开配置叶时设置 `O_NONBLOCK`，先通过 `fstat` 拒绝非普通文件，再对同一普通文件描述符清除该标志；加入带 3 秒超时的 POSIX FIFO 回归。本次 Windows 全套跳过该 POSIX 用例。 |
| AUD-36 输出目录项断电持久性 | **已加入同步；POSIX/多文件系统验收待做** | POSIX 发布后 `fsync` 文件及父目录，并同步新建目录的祖先链；Windows 通过 `MoveFileExW(MOVEFILE_WRITE_THROUGH)` 无覆盖发布文件，并以同样的写穿透语义逐级发布新目录。同步失败会抛错，避免把未确认写入登记为完成。当前 Windows 回归通过，Linux/macOS 与其他文件系统尚未验证。 |
| AUD-37 Windows 写穿透移动错误分类 | **已整改并新增回归** | 仅将 Win32 `ERROR_FILE_EXISTS`/`ERROR_ALREADY_EXISTS` 识别为文件名冲突；目标同时出现时其他错误码仍原样失败，避免掩盖权限或存储错误。 |
| SEC-25 doctor 子进程导入当前工作目录模块 | **已整改并通过回归；最新差异扫描未发现新候选** | 两处子解释器命令加入 Python `-P`。无害 `json.py` 影子模块不能再被 doctor 子进程加载，且参数回归确认依赖和 Chromium 两处探测均启用 safe-path。 |
| SEC-26 处理 worker / Playwright setup 子进程从当前目录加载同名包 | **已整改并通过回归；最新差异扫描覆盖相关文件且未发现新候选** | 默认处理 worker 和 Playwright 安装子进程加入 Python `-P`；临时当前目录的同名 `douyin_transcript` 包不能在 worker 启动前执行，setup 参数回归确认启用 safe-path。 |
| AUD-39 默认远端下载 decoder 返回类型不匹配 | **已整改并通过 downloader/pipeline 回归** | `_coerce_validation()` 接受并校验 `MediaFile`，保留身份信息；新下载返回最终缓存路径，缓存命中无需再下载。默认远端 pipeline 的离线集成回归通过。 |
| AUD-40 下载未受单条任务绝对超时限制 | **已整改并通过回归** | pipeline 将绝对 deadline 传给默认 downloader；下载器采用 `min(自身 300 秒上限, 任务 deadline)`，短期限请求回归确认超时前停止并清理 `.part`。 |
| AUD-41 下载阶段任务超时错误码与文档不一致 | **已整改并通过 pipeline 回归** | 任务绝对 deadline 到期时将 downloader `TIMEOUT` 映射为 `PROCESSING_TIMEOUT`，自身 300 秒下载上限仍保留 `TIMEOUT`；任务库记录同一错误码。 |
| AUD-42 重试未恢复原处理时限 | **已整改并通过 CLI 回归** | 新快照 schema v2 保存 `max_processing_seconds`；旧 schema v1 兼容并使用原默认值 7,200 秒。重试不传参数恢复快照，显式 `--processing-timeout-seconds` 覆盖并持久化新值。 |
| AUD-43 时间轴 sidecar 完整性与恢复 | **本机源码与回归已通过；跨平台待验收** | schema v6 保存 sidecar 必需标志、路径和摘要；发布前先绑定预期摘要，完成、skip 和 recovery 同时验证主稿与 sidecar。v5 的 true/未知旧设置在缺少绑定时 fail closed。 |
| AUD-44 URL 清单/术语词典 FIFO 可阻塞 CLI | **已整改并加入有界回归** | 两个入口以 POSIX `O_NONBLOCK` 打开后用 `fstat` 确认普通文件，再清除非阻塞标志读取；子进程测试用 2 秒上限验证 FIFO 被拒绝。该 POSIX 用例在 Windows 跳过。 |

## 4. 当前问题与整改对策

优先级说明：**P1** 为发布前关闭项；**P2** 为稳定使用或后续安全加固项。未验证项不等于已发生故障。

### SEC-06：远端标题可包含终端控制字符（低危，已整改）

- **修复前证据：** 页面标题经 `_clean_plain_text` 折叠空白后仍保留 ESC/BEL 等控制字符；普通文本摘要会直接打印 `item.title`，Markdown 转义也只处理标点，不移除终端控制码。
- **前置条件与影响：** 用户处理攻击者控制标题的视频时，标题可清屏、改写终端显示或影响终端 Markdown 阅读器。该问题不执行 CLI 命令，也不影响 JSON 输出中的转义文本。
- **整改：** 页面标题在普通 CLI 输出和 Markdown 标题/正文边界过滤 C0/DEL 控制字符；增加 ESC、BEL、DEL 和 CSI 序列测试。JSON 输出仍由 JSON 编码器转义控制字符。

### SEC-07：术语替换在分配结果前没有检查输出预算（低危，已整改）

- **修复前证据：** 词典文件限制为 256 KiB 和最多 1,000 条规则，但替换字符串长度没有上限。替换函数先将匹配文本逐个追加到列表并整体 `join`，pipeline 在替换完成后才检查字符数；术语词典只有用户显式提供时才启用。
- **前置条件与影响：** 用户启用了恶意或误配置词典，且输入文本大量匹配短 source、替换值远长于 source 时，进程可能在事后检查前尝试分配极大字符串，造成内存压力或进程崩溃。
- **整改：** 替换函数接受最大输出字符预算，每次追加前先检查预计结果长度并立即失败；主稿和时间轴分别受限。新增大扩张替换与时间轴扩张用例。

### SEC-08：URL 清单和批次没有总输入上限（低危，已整改）

- **修复前证据：** `_read_url_file` 将整个清单读入内存并 `splitlines()`；`run_urls` 再次物化全部输入、结果槽和已解析任务。下载并发上限为 1–2，但它不限制总行数、清单字节或任务数。
- **前置条件与影响：** 操作者处理超大或不可信 URL 文件时，内存和 SQLite 任务数可随输入无界增长。项目原定批量规模为 5–50 条，正常用量不受影响。
- **整改：** URL 清单限制为 1 MiB、单行最多 8192 字符、每批最多 100 条；CLI 在创建数据目录前拒绝超限输入，pipeline 也对直接调用的 iterable 有界消费。保留 50 条正常批次并拒绝第 101 条，覆盖了边界测试。

### SEC-09：Skill 命令模板没有约束用户参数的 shell 传递方式（中危，条件性，已整改）

- **修复前证据：** 修复前的 [SKILL.md](../skills/douyin-transcript/SKILL.md) 第 25、31、37 行将 URL、清单路径和本地媒体路径直接放入命令模板，没有要求 Agent 宿主用结构化参数传值。
- **前置条件与影响：** 若宿主把调用方提供的 URL 或路径拼接进 shell 命令文本，shell 元字符会在 CLI 校验之前执行，可能以 Agent 当前用户权限运行。采用 argv 参数数组的宿主不受此路径影响。
- **整改与验证：** [SKILL.md](../skills/douyin-transcript/SKILL.md) 第 22 行明确要求通过宿主结构化进程接口单独传递 executable 和每个 argv；命令示例改成 JSON 参数数组。shell-only 宿主必须调用对应 shell 的参数转义函数。`uvx --from skills-ref agentskills validate skills/douyin-transcript` 返回 `Valid skill`。真实 Codex/Claude Code 宿主调用尚未执行，不能据此声称所有宿主已动态验收。

### SEC-10：Windows 既有敏感路径的所有者 SID 未纳入私有判定（中危，已整改）

- **修复前证据：** `_inspect_windows_path` 读取 owner SID，但只根据显式 allow ACE 判定 `private`。`ensure_private_directory` 按此结果接受既有目录；`capture.py` 和 `tasks.py` 将其用于浏览器配置目录和任务数据。
- **前置条件与影响：** 修复前，若应用使用由其他 Windows 账户拥有、但 DACL 授权当前用户访问的既有敏感路径，所有者可以改写 DACL 并读取内容；浏览器配置目录可能含登录 Cookie，任务数据含本地路径和任务元数据。新建路径原本就设置受保护 DACL。
- **整改与验证：** [storage_security.py](../skills/douyin-transcript/src/douyin_transcript/storage_security.py) 先拒绝 owner SID 不属于当前用户、SYSTEM 或本机 Administrators 的既有路径，再检查显式 ACE；[test_storage_security.py](../tests/unit/test_storage_security.py) 覆盖当前用户、SYSTEM、Administrators 和其他账户 SID。当前全套离线测试 **303 passed, 17 skipped**。仍需在有第二个 Windows 账户的环境验证真实 DACL 集成行为。

### SEC-11：慢速响应可突破下载总时限（低危，已整改；集成边界待验收）

- **证据：** `urls.open_pinned_https()` 在 `getresponse()` 中读取响应头；`downloader.py` 到响应返回后才创建 `deadline`，并在循环中调用 `HTTPResponse.read(64 * 1024)`。socket 超时是单次无数据等待限制，不等同于整次读取的墙钟上限。离线 `socketpair` 实验将 6 个字节按 70 毫秒间隔发送，在配置 150 毫秒总时限时，单次 `read(64 KiB)` 耗时 422 毫秒。
- **前置条件与影响：** 操作者处理来自允许域的公开视频，且允许的媒体端点持续慢速发送响应；本地 CLI 会超过配置的总下载时限并继续占用进程，临时文件也可能保留到后续清理。该路径没有代码执行或数据泄露影响；尚无证据表明具体抖音 CDN 可被攻击者控制。
- **整改与验证：** 单调时钟 deadline 现在从候选下载开始，覆盖 DNS 等待、连接/TLS、请求和响应头、重定向、候选回退、重试等待、正文读取及解码后的最终提交检查；超时定时器会关闭活动 socket，body 使用 `read1()`。socketpair 慢响应头/慢速正文、慢 DNS、重定向/候选 deadline 共享和慢解码用例通过。残余限制：阻塞中的系统 DNS 查询无法由 Python 取消，最多可能暂留 2 个 daemon 查询线程；真实 SSLSocket/TLS 与 Windows 多平台集成仍未验证；测试注入用自定义 requester 时，requester 自身在返回前阻塞无法被内置 socket timer 中断；本地文件系统写入和解码若自身阻塞，也只能在返回控制权后检测超时，无法被当前进程内的计时器强制终止。

### SEC-12：运行时模型发现不校验固定 revision（低危，已整改）

- **证据：** `ModelSpec` 配置了完整 Hugging Face commit，setup 下载时也传入 `spec.revision`；但 `resolve_model_path()` 对应用目录下的模型只检查文件完整性，`_valid_snapshot()` 则按修改时间选择最新的完整快照，均未比较所选模型与固定 revision。
- **前置条件与影响：** 搜索路径中已存在同 profile、但来源或 revision 不同的完整模型。运行时可能使用与配置版本不一致的模型，影响转写结果一致性和可复现性；当前证据不支持任意代码执行的结论。
- **整改与验证：** Hugging Face cache 现在只接受目录名等于固定 commit 的 snapshot；应用目录模型和 ASR 显式路径必须有 setup 生成的来源清单，匹配仓库、revision、schema 和必需文件 SHA-256。回归覆盖不匹配 snapshot、未标记本地模型、清单 revision 错误和模型文件变化。模型解析/ASR/setup 定向用例通过。来源清单不是上游数字签名；它用于防止版本误选和下载后文件变化，不证明主机本身或同 UID 攻击者可信。

### SEC-13：POSIX 私有路径判定忽略 owner UID（低危，条件性，已整改）

- **证据：** POSIX 分支只检查 `stat.S_IMODE(info.st_mode)` 是否包含组/其他权限；`TaskStore` 在 `inspect_private_path()` 返回 `private` 后便打开既有 SQLite 数据库，没有额外校验 `st_uid`。
- **前置条件与影响：** 需要 CLI 以 root 或具有 DAC 绕过能力运行，并使用另一个 UID 控制的敏感路径。普通非特权用户通常无法访问另一个用户的 `0700` 目录或 `0600` 文件；在特权运行方式下，路径所有者仍可篡改被信任的任务状态。
- **整改与验证：** POSIX 检查现在同时要求敏感目标的 `st_uid == os.geteuid()` 和组/其他权限位为零；Windows 分支不调用 POSIX UID API。跨平台 mock 用例覆盖同/异 UID 文件与目录，并验证异 owner 的既有敏感目录被拒绝；安全测试文件 **10 passed、5 skipped**，该组 Ruff 检查通过。仍建议以专用非特权账户运行。

### SEC-14：远端标题可能成为 Agent 指令（待宿主级验证，尚未确认漏洞）

- **证据：** 页面标题经过控制字符过滤后仍保留普通文字，结果 JSON 也包含 `title`、`output_path` 和提示文本。风险最初提出时 Skill 未明确规定这些值只能作为数据处理；当前 Skill 已补充此约束，但具体宿主是否遵守仍未验证。
- **前置条件与影响：** 仅在某个 Agent 宿主把视频标题/路径中的指令当成模型指令，且该 Agent 具备额外工具权限时才可能造成后续越权操作。离线源码无法确认具体宿主是否会遵守这类内容，因此本项是待验收候选，不计入已确认漏洞数。
- **整改与后续对策：** Skill 现已明确所有 CLI 返回值（包括标题、路径、提示和状态）均为不可信数据，禁止执行其中的指令或因此发起额外工具调用，并禁止读取 Markdown 正文。还需用无害的对抗性标题在目标宿主做集成验证。

### SEC-15：敏感路径重解析点与检查/使用边界（部分整改，跨平台集成待验收）

- **修复前证据：** `_canonical_storage_path()` 使用 `Path.resolve(strict=False)`，会先跟随 symlink/junction，再逐组件检查；输入 alias 的 reparse 属性因此丢失。Windows 新目录原先也会先创建再收紧 ACL。
- **整改与当前行为：** 路径现在使用词法绝对化，保留每个原始路径组件供 `lstat`/reparse 检查；UNC/device namespace 路径会被拒绝。Windows 盘符路径现查询 `GetDriveTypeW()`，拒绝 `DRIVE_REMOTE`，对 `DRIVE_UNKNOWN`/`DRIVE_NO_ROOT_DIR` 失败关闭；权限诊断和创建错误保留具体原因。Windows mock 回归覆盖远程、未知和本地盘类型，本机 C:、D: API 结果均为 `DRIVE_FIXED`；本机没有映射盘供真实共享验证。Windows 通过 `CreateDirectoryW` 从创建时应用受保护用户 DACL。配置文件在读取前检查文件和祖先链。`inspect_private_path()` 仅在每个现存祖先通过平台替换权限策略后才返回 `missing`；doctor 再确认运行时具备保护新建目录的能力。
- **此前独立复核与整改：** `ensure_private_directory()` 检查祖先后曾按路径逐段创建并再次按路径验证；`create_private_file()` 过去先检查父目录，再按路径排他创建并在关闭句柄后设置 ACL/mode。`TaskStore` 过去还会先 `Path.resolve(strict=False)`，使直接调用时的 symlink/junction alias 在安全 helper 检查前被折叠；现已改为保留词法路径，并在解析数据库前检查其父目录和叶文件。新增确定性回归确认安全检查收到未经 `resolve()` 的数据库路径；端到端 symlink alias 回归已添加，但本机 Windows 无法创建 symlink，故跳过。当前源码不足以确认跨用户可利用：路径祖先的 POSIX mode/owner 与 Windows ACL 策略用于阻止其他账户替换条目；同 UID、管理员/root 的路径操作不在现有威胁保证内。
- **本轮续审整改：** POSIX 目录树现在通过 `dir_fd`、`O_NOFOLLOW` 和逐组件 `fstat`/目录项身份比较创建与核验；新文件相对固定父目录 fd 以 `O_CREAT|O_EXCL` 创建，并在同一 fd 检查类型、owner 和权限。Windows 目录使用 `CreateDirectoryW` 原子应用受保护用户 DACL；新文件使用 `CreateFileW(CREATE_NEW)` 并在创建时提供私有 DACL，保留文件/目录句柄检查 ACL、reparse 状态及 volume/file ID，再复核路径仍指向该对象。没有使用 Nt* 私有 API。测试覆盖 POSIX dir-fd 链及替换、Windows 父目录实际替换和文件身份不一致 fail-closed；定向测试 **92 passed, 14 skipped**，改动文件 Ruff 通过。Windows 当前文件系统拒绝替换仍打开的叶文件，因此文件竞态用例通过确定性身份扰动验证，不宣称完成真实叶文件替换测试。
- **剩余风险与对策：** 创建竞态整改缩小了目录/文件创建的路径竞态，但没有消除所有 pathname-only 边界。Win32 创建仍接受路径；身份复核无法排除两次检查之间的 ABA 交换。同 UID、管理员/root 不在既定威胁保证内。SQLite、Playwright、Hugging Face、下载器缓存和输出验证仍使用路径名。此前 Python 3.11/3.12 全套历史快照均为 **337 passed, 20 skipped**；本轮结果见第 2 节和 AUD-63；POSIX dir-fd 分支本机未执行。后续在 Linux/macOS CI/实机、Windows 第二账户和多种 ACL 继承环境验证，并继续要求第三方 pathname-only API 使用受保护祖先。SEC-15 仍为部分整改，不确认跨账户漏洞已被利用或彻底消除；创建失败后的私有残留见 AUD-52。
- **独立边界复核（2026-10-09）：** 对照 `ARCHITECTURE.md` 的信任模型和当前调用链复核 `TaskStore.__init__`、`BrowserCapture.start`、模型 `snapshot_download`、下载 `.part` 与 Markdown 发布。它们先使用经策略检查的应用数据根，再向 SQLite、Playwright、Hugging Face 或文件 API 传路径；在假设其他账户不能修改私有祖先的条件下，没有确认可由其他账户利用的残余缺陷。`part.open("wb")` 换成独占创建可提供纵深保护，但随机名和私有缓存目录使其不构成已确认跨账户漏洞，且重试需同步改用新临时名。SQLite/Playwright/Hugging Face 要实现句柄绑定需其 API 支持句柄或引入专用适配层；单次 post-check 不能消除 ABA。用户选择的逐字稿输出目录是独立边界，权限状态只提示、不阻止保存，不能宣称为私有数据根。建议保持当前明确的威胁边界与部分完成状态，完成 POSIX 实机、Windows 第二账户和 ACL 继承集成后再审结；未运行测试。

### SEC-16：Windows 默认数据目录祖先 ACL 不兼容（本机 fallback 已实现，跨主机验证待做）

- **证据：** 默认先尝试 `%LOCALAPPDATA%\\douyin-transcript`。[doctor.py](../skills/douyin-transcript/src/douyin_transcript/doctor.py) 在该路径不安全且目标目录不存在时改用 `%USERPROFILE%\\.local\\share\\douyin-transcript`；本机 `doctor --json` 此前报告 fallback 下 data/database/profile/cache 权限为 `ok`。若旧 `%LOCALAPPDATA%` 目录已存在但不安全，仍保留该路径供诊断并拒绝写入，防止静默隐藏旧任务。新目录使用 `CreateDirectoryW` 原子设置受保护 DACL。
- **整改与限制：** fallback 选择和 doctor 均依赖逐组件祖先替换权限检查；若没有安全候选会保留实际候选供诊断，但其权限状态不会被误标为 `ok`。定向测试覆盖 LocalAppData fallback、保留旧目录和缺失路径的祖先策略；多 Windows 安装、账户与非标准 ACL 组合仍待验证。
- **对策：** 在 Windows 10/11 多账户和 CI 主机验证 LocalAppData 正常、fallback、既有不安全目录保留拒绝、显式 override 和 DACL 子项继承。由用户主动选择安全新目录迁移旧数据；不自动移动、不放宽为允许任意外部主体替换祖先。UNC profile 不支持作为敏感数据根。

### SEC-17：显式模型路径校验后仍把原始路径交给 ASR（已整改，真实模型待验收）

- **证据与整改：** `LocalASR.model_path` 现在先解析 canonical path、校验固定 revision/provenance，再把同一路径保存并传给 `WhisperModel`；不再校验 canonical 后回退加载调用方 alias。测试模拟 alias 校验后目标切换。模型/ASR 定向测试 **18 passed, 1 skipped**，Ruff 通过。
- **剩余限制：** 真实权重未下载，未运行推理；校验和 native model open 仍不是同一个文件句柄，不能抵御同 UID 并发改写。取得授权后应在受保护目录运行真实模型并记录 revision、哈希与输出验收。

### SEC-18：外部 Hugging Face 缓存完整性和目录信任（已整改，主机缓存验收待做）

- **证据与整改：** pinned snapshot 现在要求受信任的 owner/祖先写权限链；符号链接 blob 必须落在对应 `blobs/` 内并匹配 Hub 文件名的 SHA-256 或 Git blob SHA-1 ETag。普通文件副本仅在整个目录链受信时接受，因为其缓存形式可能来自禁用 symlink 的环境。共享可写缓存和替换内容测试已添加；模型/ASR 定向测试 **18 passed, 1 skipped**。
- **剩余限制与对策：** 当前 Windows 主机的 Hub cache 祖先 ACL 检查失败关闭，所以没有证明真实 Hub cache 可被接受；权重未下载。普通副本依赖目录信任链，没有本地 ETag 可比；content hash 也不是上游签名。授权下载后验证一次受信 Windows cache 和完整加载，并保留失败关闭策略。

### AUD-21：Windows cache clean 路径删除竞态（代码整改并通过本机回归，跨账户待验收）

- **修复前证据：** Windows 先检查 pathname 元数据、再按路径 unlink，替换时可能误删别的文件。
- **整改与验证：** 清理快照记录 cache 根和文件身份；Windows 打开并固定根目录句柄、相对根句柄打开 basename、拒绝 reparse 并通过句柄核对 file ID/元数据/硬链接数，然后用 `SetFileInformationByHandle(FileDispositionInfo)` 删除该对象。系统 API 或身份无法确认时跳过；不支持的非 Windows 路径也失败关闭。回归测试尝试在 relative-open 和 disposition 前替换目录/文件；cache/CLI 定向测试 **26 passed, 2 skipped, 15 deselected**，本机 Windows 竞态用例通过。
- **剩余限制与对策：** 这不是第二账户对抗性验收；native API 可用性/权限拒绝时不会清理。保持默认预览，在独立 Windows 账户与 CI 验证 handle/share 行为后再关闭跨平台集成门槛。

### SEC-19：不安全 config.toml 可重定向输出（源码已整改，跨平台集成待验收）

- **修复前证据：** `resolve_paths()` 在验证数据目录安全性前打开 `config.toml`，并采用其中的 `paths.output_dir`；其他账户可改写不安全旧数据目录中的配置，从而把逐字稿输出重定向到其可读位置。
- **整改与验证：** `config._read_config()` 现在使用 `open_private_regular_file()`，从完成类型、owner 和权限校验的同一文件描述符/句柄读取 TOML；共享或未知权限 fail closed，缺失配置仍采用默认值。POSIX 使用 pinned directory FD、逐组件 `O_NOFOLLOW` 和 leaf `fstat`；Windows 打开 leaf 时使用 `FILE_FLAG_OPEN_REPARSE_POINT`，并通过同一 handle 的 `GetSecurityInfo` 检查 DACL。Windows 配置/存储定向测试 **24 passed, 9 skipped**；全套测试 **303 passed, 17 skipped**。
- **剩余风险与对策：** Windows 祖先目录仍按 pathname 检查，安全边界依靠拒绝其他主体的目录替换权限；同 UID、管理员/root 及非标准 POSIX ACL 不在承诺范围。POSIX 目录句柄、FIFO 与 symlink 竞态用例在本 Windows 主机跳过；Linux/macOS CI 或实机仍需验收。SEC-15 下 SQLite、Playwright 等其他 pathname-only 操作仍保留各自的 TOCTOU 限制。

### SEC-20：配置路径中的 `..` 可使权限检查与实际读取指向不同位置（源码已整改）

- **证据：** `storage_security._canonical_storage_path()` 使用 `os.path.abspath()`，会词法消去 `.`/`..`；但 `config._read_config()` 把传入的原始 `path` 交给 `inspect_private_path()` 后，仍对原始路径执行 `path.open("rb")`。`resolve_paths()` 的 `config_anchor` 可来自 `--data-dir`、`DOUYIN_TRANSCRIPT_HOME` 或默认路径，再拼接 `config.toml`。
- **攻击路径与影响：** POSIX 路径解析会先跟随 symlink 再处理其后的 `..`，而 `abspath()` 只做词法归一化。若受影响进程使用了含 `symlink/..` 的数据根路径，攻击者能影响该路径上的 symlink/目录布局，并令原路径最终落到其可控配置文件，程序可能检查另一个词法目标的权限后读取恶意 TOML。配置可改变 data/output 目录，进而把后续数据或逐字稿导向攻击者可读位置。需要调用方采用受影响路径且攻击者能够控制该路径布局；同 UID 进程本身不在既有保护保证内。Windows junction/reparse 与 `..` 的组合尚未实机验证，因此不据此宣称 Windows 可利用。
- **严重度与置信度：** P2（中危、条件性）；POSIX 的两种解析语义差异及代码路径有源码依据，完整端到端利用要求可控的路径布局，Windows 行为未确认。
- **整改与验证：** `_canonical_storage_path()` 在 `abspath()` 归一化前拒绝任一 `..` 组件；配置由 SEC-19 的同一已校验句柄读取。Windows 回归覆盖含 `..` 的配置路径直接拒绝；POSIX `symlink/..` 与打开后替换文件的测试已加入，但本 Windows 环境会跳过这些测试。当前配置/存储定向结果 **24 passed, 9 skipped**。
- **剩余风险与对策：** Windows 父目录 reparse 竞争仍由祖先 DACL 替换权限检查约束，未使用逐级目录 handle 固定；需在 Windows 多账户及 Linux/macOS CI 验证。遇到不支持安全句柄语义的平台时配置读取失败关闭。

### AUD-30：旧失败任务缺少配置快照时仍会按当前默认值重试（已整改，旧配置需显式选择）

- **原始证据与影响：** schema v3 以前的任务没有 `processing_options_json`，无法恢复首次请求的语言、时间轴、限制、词典、输出目录或现在新增的处理时限；无提示地使用当前值会改变输出结果或落盘位置。
- **整改：** `retry-failed` 默认不排队缺少或无法校验快照的旧任务，在 JSON 项中标为 skipped，并在 stderr 提示显式参数 `--use-current-defaults`。使用该参数时，当前默认值连同 schema 版本和有效输出目录在 `retry_failed()` 的同一数据库事务中写入任务后再处理；即使本地输入随后失效，该任务也保留新选定快照。
- **验证：** CLI 回归覆盖默认跳过且任务状态不变、显式 opt-in 后使用当前配置并持久化快照；retry schema 只接受精确整数 `1`/`2`，schema v1 兼容默认时限，schema v2 严格校验 `max_processing_seconds`，拒绝 JSON `true`、`1.0`、字符串及越界值。AUD-34/35 原定向测试为 **76 passed**；当前全套 Windows 离线测试为 **303 passed, 17 skipped**。

### AUD-31：实施计划仍描述与 V1 缓存行为冲突的自动删除策略（文档缺陷）

- **证据：** 实施计划第 7 节与 CLI/README 规定远端媒体缓存默认保留、由 `cache clean` 显式管理；第 12.4 节却仍写“默认只删除成功转写后的临时媒体”。
- **影响：** 按计划开发或审核的维护者可能错误实现自动清理，从而破坏失败恢复/缓存复用；用户也无法从同一计划判断真实缓存生命周期。
- **对策：** 以 V1 现有实现为准统一表述：远端缓存默认保留，`cache clean` 默认预览并在显式 `--apply` 后清理；本地源文件不由程序删除。自动清理和 `--keep-media` 暂不纳入 V1。

### SEC-21：术语字典导致的匹配工作量没有累计上限（已整改，P2 条件性资源耗尽）

- **原始证据与攻击路径：** 旧匹配器对每个文本位置逐条执行 `text.startswith()`。启用 `--terminology-dictionary` 并处理长 ASR 文本时，攻击者控制的无匹配内容可使 CPU 工作量接近“文本长度 × 规则数”。词典默认关闭，任务需要用户启动；影响限于本地单进程。
- **整改：** `corrections.py` 改用前缀树逐字符匹配。每个起始位置持续记录边界有效的最深终止规则，因而保留最长有效命中；替换仍只对原始文本匹配，不级联，ASCII 单词边界规则不变。每个任务以 `CorrectionWorkBudget` 限制总 Trie 转换数为 25,000,000，pipeline 将同一个预算用于正文和时间轴。规则数上限为 1,000，规则字段 UTF-8 总量上限为 256 KiB，Trie 节点上限为 65,536；CLI 读取词典也改为最多读取上限加 1 字节，避免先检查文件大小再无界读取。
- **回归与证据：** 定向用例确认重叠规则、最长有效规则回退、ASCII 左右边界和替换不级联；1,000 条规则处理 200,000 字符未命中文本时预算恰减少 200,000 次 Trie 转换；共享长前缀输入确定性耗尽预算并返回 `TERMINOLOGY_WORK_LIMIT`；pipeline 正文与时间轴共用同一预算。定向测试 **60 passed**；本轮统一 Windows 全套 **303 passed, 17 skipped**，全仓 Ruff `All checks passed!`。
- **剩余限制：** 超过规则、Trie 或转换预算的输入会安全失败，提示精简词典或关闭纠错；25,000,000 是算法工作上限，不是特定机器上的墙钟耗时保证。真实 ASR 输出性能未测量。

### SEC-22：远端 Markdown 的公开 frontmatter 可伪造已完成任务关联（已整改，定向回归通过）

- **原始证据与影响：** 旧实现按公开 frontmatter `video_id` 复用文件，并在完成/崩溃恢复时仅用该 ID 验证关联；可写共享输出目录的写入者能构造旧实现信任的文件。
- **整改：** schema v5 在私有 `tasks.sqlite3` 任务行记录 `output_sha256`。pipeline 在发布前从内存中的 transcript 与 metadata 渲染预期 Markdown UTF-8 字节并计算摘要；原子 no-overwrite writer 不再按 `video_id` 复用任何现存文件，碰撞时选择新文件名。TaskStore 只在实际文件字节等于预期摘要且 frontmatter 关联正确时保存摘要；`complete_task()`、`is_completed_valid()` 和 `recover_interrupted()` 都要求路径、公开关联和私有摘要匹配。既有 schema v4 completed 任务没有此凭据，会按无效输出处理，需显式 `--force` 创建新文件。
- **验证：** 回归覆盖同 ID 伪造文件不被复用、只有公开 ID 不能完成任务、文件被修改后失效、没有私有摘要的 writing 任务不能在恢复时升级。AUD-30/34/35 所用四组定向测试 **76 passed**；对应 Ruff 检查通过。
- **剩余限制：** 本地 SHA-256 记录依赖任务数据库的私有权限；能修改该数据库的同一用户/进程不在这条边界保证内。输出仍通过路径读取而非长期固定文件句柄；并发替换集成行为和跨平台 ACL 尚未验收，后续可评估将输出创建/验证绑定到 OS 文件句柄或仅允许私有目录。

### SEC-23：媒体时长上限信任容器声明值（P2 候选，源码已整改，真实样本待验收）

- **修复前证据：** `_validate_with_pyav()` 只解码第一个音频帧即停止，并优先使用 `container.duration`、其次 `stream.duration` 作为实际时长。Pipeline 与 ASR 都检查这个值，但 ASR 最终收到原文件路径并处理整段输入，没有把解码终点限制为校验时长。
- **风险与结论：** 如果受支持的容器能声明低于实际音频长度的 duration，超出 `max_media_duration_seconds` 的文件可能通过旧校验。当前没有真实媒体样本确认具体格式能触发此条件，因此仍标为候选问题，不报告为已利用漏洞。
- **整改与验证：** `_validate_with_pyav()` 现在遍历音轨全部可解码帧，累计 `samples / sample_rate` 并跟踪 PTS 时间跨度；每帧后检查配置上限，超限即停止解码。正容器声明超过配置上限时在解码前拒绝；较小或缺失声明不能降低实际累计时长。对 `av.error.InvalidDataError` 的恢复行为与项目锁定的 faster-whisper 1.2.1 [音频解码器](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/audio.py) 一致，避免坏包后仍可解码的媒体被预检提前拒绝。`validate_media_file()` 的直接调用默认也改为 1 小时，与 pipeline/ASR 默认一致。模拟回归覆盖元数据低报、声明上限早停、首个超限帧早停、默认下载/ASR/独立验证上限传递及可恢复错误后续帧。Windows 全套 **303 passed, 17 skipped**；真实 PyAV/媒体样本仍未运行。
- **剩余限制与对策：** 用授权样本构造声明时长偏短、未知时长、VBR/尾部 padding 和坏包后有效帧等容器用例，与 faster-whisper 的实际解码结果对照；在 Linux/macOS 与 Windows 上验证。

### AUD-38：完整音频时长校验在一次任务中重复解码（P2，源码整改，真实性能基准待做）

- **修复前证据：** 逐帧 SEC-23 校验会完整消费音轨。默认本地路径在 `run_local()`、`_transcribe_claimed()` 和 `LocalASR.transcribe()` 各扫描一次；默认远端路径还会在 `download_media()` 校验，因此新远端任务最多额外完整扫描四遍，ASR 随后还要读取音频用于转写。
- **整改与验证：** `MediaFile` 现在带有从实际解码校验文件描述符取得的设备号、文件号、大小、修改时间和变更时间；PyAV 从该文件对象解码，前后身份变化会拒绝。pipeline 在本地预检或远端下载后将该结果传给 ASR；ASR 再打开文件并核对同一身份，然后把这个已核对的文件句柄直接交给 faster-whisper，转写结束前持续保持打开并再次核对。项目锁定版本的 [faster-whisper 1.2.1 转写 API](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/transcribe.py) 接受文件对象。路径被替换或媒体在校验后变化时会失败关闭；直接调用 ASR、缓存恢复或不提供身份的自定义 downloader/validator 仍执行独立校验。回归确认 PyAV 收到可读文件对象、校验期间媒体变化会被拒绝、默认本地 pipeline 只调用一次 validator，以及 ASR 在加载模型前拒绝替换文件。当前全套 Windows 离线测试 **303 passed, 17 skipped**，Ruff 通过。
- **剩余限制与对策：** 真实授权长媒体的 CPU 时间和总耗时尚未测量，不能量化具体性能收益；需要用 16.5 分钟样本和接近配置上限的样本记录校验次数、CPU 与完整任务耗时。AUD-10 的源码隔离已加入，但真实 PyAV/faster-whisper 子进程链路仍待验收。

### SEC-24：FIFO 配置文件可在类型检查前阻塞读取（P2，可用性，源码已加防护）

- **证据：** 若 POSIX `config.toml` 是 FIFO，普通只读 `open()` 会等待 writer；此前的类型检查发生在打开之后，因而尚未执行到拒绝非普通文件的逻辑。
- **影响：** 使用受信数据目录、但配置叶被替换为 FIFO 时，CLI 启动可停在配置加载阶段。攻击者必须能在数据目录中创建/替换配置路径；这主要影响可用性，不代表可绕过权限校验读取配置。
- **整改与验证：** POSIX leaf open 现在带 `O_NONBLOCK`，随后以 `fstat` 拒绝任何非普通文件；普通文件通过权限检查后，在同一描述符上清除 `O_NONBLOCK` 再交给 TOML parser。新增 FIFO 回归在子进程中运行，3 秒超时会终止并回收进程，防止回归让测试套件永久挂起。本 Windows 全套 **303 passed, 17 skipped**，FIFO 测试因平台限制跳过。
- **剩余限制与对策：** POSIX `O_NONBLOCK` 和 `fcntl` 行为尚未在 Linux/macOS 实机验证；将当前 FIFO 与普通配置读取回归纳入两平台 CI，并在不支持安全标志的平台继续 fail closed。

### AUD-32：短链解析没有覆盖 DNS 与多跳的绝对 deadline（P2，可用性，已修复）

- **修复前证据：** `resolve_input()` 对短链最多跳转若干次，但 `_request_short_redirect()` 调用 `open_pinned_https(timeout=10.0)` 时没有传入 `deadline`。`open_pinned_https` 的 DNS 调用因此可进入无 deadline 的 `getaddrinfo()`；每次 socket 超时也只是单次等待上限，不是覆盖 DNS、响应头和全部跳转的总时限。
- **整改：** `resolve_input()` 为一次短链解析建立 30 秒单调时钟绝对 deadline，并将同一值传给每一跳。`open_pinned_https()` 将剩余时限用于有界 DNS、连接/TLS、响应头和 socket 中断；deadline 到期映射为稳定 `TIMEOUT`。直接视频 URL 路径保持原行为。
- **验证与剩余限制：** 定向测试确认多跳共用同一 deadline，阻塞 resolver 时解析在预算内失败。AUD-50 后，带期限的 worker 在超时后会被终止并回收；无真实 DNS/TLS 或跨平台集成证据。无 deadline/cancellation 的直接 helper 调用仍同步使用系统 resolver。

### AUD-33：浏览器代理在有界预检后再次无界解析 DNS（P2，可用性，已修复）

- **修复前证据：** `capture._require_public_host()` 使用 5 秒 deadline 检查浏览器目标；请求继续后，`browser_proxy.resolve_browser_destination()` 再次调用 `validate_https_url(resolve_dns=True)`，但没有传 deadline。代理 `ThreadingTCPServer` 最多允许 64 个活动客户端槽，阻塞在 DNS 的请求线程会在 resolver 返回前占用槽位。
- **整改：** 每个 CONNECT 请求建立 10 秒绝对 deadline，覆盖请求行/请求头、有界 DNS、连接以及写入 CONNECT 成功响应；剩余时限传给解析器和连接器。deadline 定时器关闭客户端 socket，处理线程 `finally` 关闭上游并归还客户端槽。allowlist 与公网 IP 校验继续在建立隧道前执行。
- **验证与剩余限制：** 定向回归阻塞首个 DNS resolver，确认 CONNECT 在时限到达后客户端关闭且唯一代理槽可被下一 CONNECT 获取；第二个请求成功建立隧道。AUD-50 后 DNS 子进程也会在期限到达时终止并回收；真实 Chromium、系统 DNS 和 Windows/macOS/Linux 集成仍待验收。

### AUD-34：本地失败任务在输入文件失效后无法通过 retry-failed 再次排队（已整改）

- **原始证据与影响：** CLI 曾在媒体验证前将本地任务改为未认领 `downloaded`；输入若失效，pipeline 在打开任务库前返回失败，留下不能被标准 retry 或 stale recovery 处理的状态。
- **整改：** `retry_failed()` 对本地任务保留 `failed`，CLI 将原 `task_id` 传给 `run_local(retry_task_id=...)`。pipeline 先做 media validator 与时长校验；TaskStore 随后要求规范化源路径和 `content_hash` 都与原记录相符，才在事务内改为 `downloaded`。前置错误通过 `update_failed_retry_error()` 更新稳定错误信息，状态继续为 `failed`。替换成不同内容时拒绝沿用旧 task ID。
- **验证：** 单测覆盖文件删除、内容替换时保持 failed，以及原文件恢复后才可重新排队；CLI 回归覆盖 retry-failed 遇到缺失本地源仍返回失败并保持同一任务 failed。定向测试 **76 passed**。

### AUD-35：`--force` 重跑失败后 retry-failed 恢复旧配置快照（已整改）

- **原始证据与影响：** `create_local_task()`/`create_remote_task()` 使用 `INSERT OR IGNORE`；旧 `reopen_completed()` 只重置状态。于是新配置 `--force` 失败后，后续重试读取首次成功的旧快照。
- **整改：** `reopen_completed()` 在同一个 SQLite 写事务内更新当前 profile、title 和白名单 `processing_options_json`，清除旧输出路径/摘要及远端旧 duration，再开放本次 attempt。输出保留旧文件但新 attempt 只创建新的 no-overwrite 文件；失败后的 `retry-failed` 从最近保存快照恢复。
- **验证：** CLI 回归先成功完成任务，再以新 profile、auto 语言、时间轴和不同输出目录 force 运行并注入模型启动失败，随后 retry-failed 验证 pipeline 收到新设置并在新输出目录成功完成。定向测试 **76 passed**。

### AUD-36：Markdown 发布与新建目录项未确认持久化（已整改，跨平台耐久性验收待做）

- **证据：** 修复前 `markdown._atomic_publish()` 只同步临时文件内容，发布链接和临时名删除后没有确认父目录项；输出目录逐级创建时也没有同步新目录的父目录。Linux `fsync(2)` 文档说明文件 `fsync` 不一定同步目录项，需要对目录 FD 单独同步。[Linux `fsync(2)` 文档](https://man7.org/linux/man-pages/man2/fsync.2.html)。
- **整改：** POSIX 在同步临时文件后以 hard-link 无覆盖发布，清理临时名，再对输出父目录 FD 执行 `fsync`；创建输出目录后同步相关祖先链。Windows 文件和逐级创建的目录都通过同卷 `MoveFileExW(MOVEFILE_WRITE_THROUGH)` 发布，不使用覆盖或跨卷复制标志。Windows 新目录先在父目录内创建唯一的空暂存目录，再移动到目标名；路径级命名 mutex 串行化同一登录会话内的协作创建者，发现外部创建竞态时失败关闭。Microsoft 文档说明 `MOVEFILE_WRITE_THROUGH` 会等待移动落盘；移动目录要求来源和目标位于同一卷，目标目录不能已存在。[Microsoft `MoveFileExW` 文档](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw)、[Microsoft 移动目录说明](https://learn.microsoft.com/en-us/windows/win32/fileio/moving-directories)。同步或发布失败时抛出 `OSError`，任务流程不会登记输出完成；已发布 Markdown 可能留在目录，重试使用新文件名。
- **验证：** 回归覆盖真实 Windows writer 无覆盖发布、同步失败不返回成功、并发线程创建嵌套输出目录，以及临时项清理。Markdown 定向测试 **11 passed**；当前 Windows 全套 **303 passed, 17 skipped**，全仓 Ruff 通过。
- **剩余限制与对策：** Linux/macOS 与非本机 Windows 文件系统尚未实机验证。Windows 命名 mutex 只协调当前登录会话，远端/外部进程仍可能并发创建；暂存目录的原子移动需要父目录删除权限，崩溃在移动前可能留下无害的隐藏空暂存目录。远程、可移动或第三方文件系统及硬件缓存未必兑现断电保证；在支持平台矩阵验证前保留 NOT VERIFIED，写穿透或目录同步失败继续显式失败。POSIX `fsync` 也受设备实际 flush 行为限制；[Apple 文档](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/fsync.2.html) 对硬件缓存的限制有说明。

### AUD-37：Windows 写穿透移动可能把通用错误误报为文件名冲突（已整改）

- **证据与影响：** `_move_path_write_through()` 在 `MoveFileExW` 失败后还检查目标路径是否出现；若外部进程恰好创建目标，这会把权限、I/O 等其他 Win32 错误改写成 `FileExistsError`。调用方可能继续尝试后缀文件名，从而掩盖原始失败原因。
- **整改：** 只把 Win32 `ERROR_FILE_EXISTS`（80）和 `ERROR_ALREADY_EXISTS`（183）映射为 `FileExistsError`；其他错误保留 `ctypes.WinError` 原始错误。新增 Windows 回归模拟目标已出现且移动返回 `ERROR_ACCESS_DENIED`，确认异常仍保留原错误码。
- **剩余限制：** 不同文件系统返回的 Win32 错误语义仍需支持平台集成验证；目标名无覆盖保护仍由操作系统原子移动完成。

### AUD-22：setup 确认前没有充分披露下载来源和目标（已整改）

- **修复前证据：** `setup` 的确认提示只列出大致操作和磁盘范围；没有展示模型的固定 Hugging Face revision、uv 锁文件中的 registry、Playwright 下载源、依赖环境和 Chromium 的保存位置。
- **影响：** 操作者可能在不知道依赖从何处下载、写入何处的情况下确认联网与磁盘操作；自定义源还可能改变依赖或浏览器二进制的信任边界。
- **整改与验证：** 现在在确认前显示 pinned repo/revision、锁文件 registry、uv 项目环境、模型目录、Playwright 下载服务、浏览器缓存位置及 `HF_ENDPOINT` 有效主机，并说明磁盘占用区间/变量。环境变量配置的源只展示 scheme/host/port，避免把 URL 中的凭据或 query token 写到终端。新增 CLI 回归确认 `HF_ENDPOINT` 覆盖值和凭据脱敏；当前全套 **303 passed, 17 skipped**。
- **剩余限制：** uv 仍可能受用户级配置、激活环境以及其他环境变量影响；Playwright CDN 实际对象地址由版本和平台决定。提示展示锁文件与已识别环境覆盖，运行时以 uv/Playwright 最终选择为准；远端安装尚未验证。

### AUD-23：setup 下载前没有检查所有目标卷的可用空间（已整改）

- **证据：** `doctor` 曾只报告数据目录所在卷的空间；`setup` 虽提示模型约占数百 MB 至约 1.5 GB，却没有读取模型、项目环境、uv 缓存和 Chromium 安装目标卷的剩余空间，仍会继续到用户确认和依赖安装。
- **影响：** 多目标分布在不同卷或剩余空间过低时，安装可能中途失败，造成部分依赖/缓存残留，甚至耗尽系统盘。
- **整改与验证：** setup 在确认前逐一显示 Python 环境、uv cache、模型、Chromium 目标的可用空间；模型目录所在卷少于 `doctor` 现有建议 2 GiB 时拒绝继续，任一目标卷空间查询失败也停止。AUD-65 后续增加 uv 和 Chromium 安装后的模型卷复查；低于 2 GiB 或无法查询时停止模型下载。对应低空间回归在当时 107/3 定向组和 366/20 全套快照中通过；最新全套结果见第 2 节。
- **剩余限制：** 2 GiB 是最低门槛而非模型文件大小保证；uv 环境、缓存、Chromium/CDN 实际占用依版本、平台与索引而变。初始检查是空间快照，仍可能被其他进程影响；代码只对已知模型余量在下载前再次 fail closed，不声称动态组件容量有保证。

### AUD-24：远端媒体时长未与页面声明时长核对（P1，完整性；源码已整改）

- **修复前证据：** `pipeline.py` 只检查页面时长上限，下载器和缓存没有比较页面声明值与实际解码时长。过短音频可能作为成功候选，导致转写漏掉后半段。
- **整改：** SQLite schema v4 为任务增加 nullable `source_duration_seconds`；页面时长被捕获后持久化并传入下载器。下载文件、缓存命中和进入 ASR 前都进行比对。当前容差为 `max(0.25 秒, min(5 秒, 页面时长的 1%))`，对短视频使用较小的绝对容差，明显偏短的媒体返回 `MEDIA_INCOMPLETE`；音频候选失败后继续尝试视频。v1-v3 旧任务没有页面时长时沿用兼容路径。
- **验证与限制：** 新增 v3 已有任务行迁移、音频截短/视频回退、缓存截短、全部候选截短、短视频与长视频容差边界及未知时长测试。真实抖音 CDN 的流时长可能带尾部 padding，容差仍需通过获授权媒体校准。

### AUD-25：缓存命中绕过最大字节数和总处理时限（P1，资源边界；源码已整改）

- **修复前证据：** 匹配缓存可超过 `max_bytes`；缓存解码不检查总下载 deadline。
- **整改：** `_find_valid_cache()` 现在用 `lstat` 排除 symlink、目录等非普通文件，跳过空文件和超限文件，并在遍历/解码前及解码后检查与网络下载共享的绝对 deadline。超时以稳定 `TIMEOUT` 失败。
- **验证与限制：** 新增超大缓存跳过、目录/符号链接跳过、过期 deadline 不进入 decoder、慢 decoder 返回后判定超时等测试。默认 pipeline 已把 decoder 放进可终止子进程；独立调用 downloader/validator Python API 时，调用方提供的 decoder 仍在调用进程运行。缓存 pathname 在 `lstat` 与 decoder 打开之间仍有 TOCTOU 边界。

### AUD-26：浏览器请求的 DNS 解析没有有界等待（P2，可用性；源码已整改）

- **整改：** `urls.py` 暴露共用 `resolve_public_addresses()`，browser route 现在使用最多 5 秒的绝对 deadline；DNS 超时或解析失败时 fail closed 并转换为安全的 `UNSAFE_PAGE_REQUEST`，继续拒绝任何非公网地址。本项原因为等待上限缺失，不是已确认 SSRF 绕过。
- **验证与限制：** 新增 route 传入 deadline、DNS 超时 fail closed 测试，现有有界 DNS 测试仍通过。测试使用 mock resolver；Windows/macOS/Linux 的系统 DNS、Chromium route 实际回调和抖音导航还未实测。

### AUD-27：CLI 与项目计划的模型/媒体保留选项不一致（P1，已通过范围对齐关闭）

- **证据与整改：** CLI 现在提供默认开启的 `--skip-existing`，并与 `--force` 互斥；参数回归覆盖默认、显式跳过和冲突行为。V1 计划已明确远端媒体默认保留以支持失败恢复和缓存复用，通过 `cache clean` 显式管理；`--keep-media` 自动删除开关不纳入首版。`turbo` 保留为可选实验档，等真实模型文件与质量/速度验收后再评估。
- **影响与结论：** 源码行为、CLI 文档和 V1 计划现在一致。缓存持续增长仍由 AUD-08 的手动清理提醒覆盖；缺少 turbo 不阻塞首版核心验收。
- **后续对策：** 维持缓存清理的默认预览、活动任务保护和句柄身份校验。只有在模型来源与获授权样例验收后，才评估增加 turbo；若未来要支持自动删除，需先定义失败恢复与并发清理约束。

### AUD-28：多个媒体候选全部失败时错误原因被折叠（P2，可诊断性；源码已整改）

- **整改：** 下载器最多保留 8 个去重的“音频/视频 + 稳定错误码”分类，并在最终安全提示中展示；顶层错误码保持兼容的 `ALL_MEDIA_CANDIDATES_FAILED`。不会包含候选 URL、签名、响应头或任意异常文本。
- **验证与限制：** 多候选 `HTTP_STATUS`/`NOT_MEDIA` 失败和签名 query 脱敏回归通过。真实 CDN 的错误分布和用户可诊断性尚未验证。

### AUD-29：ASR 默认提示词偏向电商内容（P2，识别质量风险；默认行为已整改）

- **整改：** `LocalASR.transcribe()` 默认 `initial_prompt=None`，通用逐字稿不注入亚马逊专属术语。调用方仍可通过 API 显式提供提示词；CLI/pipeline 暂未增加自定义提示词选项。
- **验证与限制：** 新增默认不传 prompt 及显式 prompt 透传测试。没有真实媒体 A/B 数据，无法量化提示词对特定行业词汇的识别影响；若后续加入 CLI 配置，应把它纳入任务快照且不写入日志。

### AUD-06：真实转写和浏览器媒体链路仍未验收（P1）

- **证据：** 当前机器没有 ASR 模型、PyAV、Playwright 和 Chromium；doctor 显示 `setup_required`。本轮只运行离线模拟测试，没有获授权媒体或真实视频链接。
- **影响：** 单元测试不能证明中文转写质量、模型耗时、Chromium 代理配置、页面重定向或媒体下载兼容性。
- **对策：** 在可控机器上准备获授权的本地中文样例，记录模型、CPU、耗时和抽样听写质检；再由有权限的操作者按计划测试获授权公开链接。将 `P1_REPORT.md`、`P2_REPORT.md` 与 `BENCHMARK.md` 中的模板替换为真实结果，不以 mock 结果替代验收。

### AUD-07：macOS/Linux 与远端 CI 结果未验证（P1）

- **证据：** 当前只有 Windows 本地结果。CI 配置覆盖 Windows、macOS、Linux 与 Python 3.11/3.12，但该工作流尚未在 GitHub 执行。
- **影响：** POSIX 目录/文件权限、符号链接清理、媒体解码和浏览器启动仍有平台差异风险。
- **对策：** 在授权的 GitHub 仓库运行完整矩阵；修复并记录各平台失败。至少在 Linux 和 macOS 验证权限、依赖安装及 `doctor`，完成前不要宣称跨平台已验收。

### AUD-08：缓存清理依赖用户主动执行（P2）

- **证据：** 缓存命令能查看容量，并按显式容量或保留期进行预览/清理；正常转写不自动淘汰缓存。
- **影响：** 长期批量使用时，媒体缓存可能持续增长。
- **对策：** 保留当前默认预览，同时在文档给出定期检查/清理指引；稳定使用前考虑容量阈值提示或明确开启的自动保留策略。执行清理前继续保护活动任务引用的媒体，并保留预览、身份复核和非递归删除。

### AUD-09：CI Action 版本标签可移动（P2，供应链加固，已整改）

- **修复前证据：** `.github/workflows/ci.yml` 中 `actions/checkout`、`actions/setup-python`、`astral-sh/setup-uv` 使用发布标签。标签便于升级，但仓库端若标签被移动，后续构建会使用不同代码。
- **影响：** CI 会执行外部 Action 代码；Action 仓库遭到入侵或标签被重定向时，构建环境存在供应链风险。当前 workflow 的 `contents: read` 已限制 GITHUB_TOKEN 权限。
- **整改：** checkout、setup-python 和 setup-uv 已固定到核验的完整 SHA，并保留版本注释。升级时仍需审阅并更新 SHA；GitHub 的说明见 [Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)。远端 workflow 结果尚未运行。

### AUD-10：下载、媒体预检解码和 ASR 的可强制墙钟超时（P2，源码整改并有本机回归）

- **修复前证据：** 媒体时长、分段数和文本字符数有硬上限；修复前 SEC-23 在当前进程同步解码全部音频帧，ASR 也同步运行。解码调用没有 deadline 或可终止的取消点。
- **影响：** 极慢 CPU、异常媒体/解码器或底层推理卡住时，命令可能长时间不返回；时长上限限制解码样本数量，不能保证处理时间。
- **整改：** 默认流水线现在通过有界 UTF-8 JSON 帧把媒体解码与 ASR 放在可监督子进程；每条本地任务从预检开始、每条远端任务从下载开始共享绝对 deadline。pipeline 把 deadline 传给默认 downloader，下载器使用它与自身 300 秒总上限的较小值；下载器自己的上限先到时保留 `TIMEOUT`，任务总期限先到时 pipeline 归一为 `PROCESSING_TIMEOUT`。超时会清理远端 `.part` 文件、将已创建任务写入 `failed/PROCESSING_TIMEOUT`，并终止/回收处理 worker。worker 在同一批次内复用模型，媒体描述与转写结果不使用 pickle。新处理快照 schema v2 保存 `max_processing_seconds`，`retry-failed` 默认恢复该值，显式参数会覆盖并更新快照；旧 schema v1 的行为兼容为 7,200 秒。硬上限为 86,400 秒。
- **验证：** 覆盖短绝对 deadline 限制下载、任务超时时错误码持久化、worker JSON 协议复用/超时终止、CLI 超时快照恢复/显式覆盖和失败任务状态。Windows 全套离线测试 **303 passed, 17 skipped**。真实 PyAV/faster-whisper 子进程集成、Linux/macOS 终止行为和长媒体超时阈值仍待实际环境验收；本机模拟不能替代真实解码器卡死实验。

### AUD-11：输出目录共享权限可能暴露逐字稿（P2，条件性；已加入诊断提示）

- **证据：** `doctor` 返回 `output_dir_permissions`，检查指定输出目录或最近存在父目录；共享目录标为 `unsafe`，但不阻止用户有意使用共享目录，也不修改 ACL。当前工作区默认输出目录实测含 `S-1-5-11`（Authenticated Users）ACE，因此返回 `unsafe`。新增测试确认权限检查不改变 mode，并检查不存在的输出目录的最近现有父目录。pipeline 对模拟的 `PermissionError` 返回 `OUTPUT_NOT_WRITABLE` 并将任务留在失败态；Windows ACL 和 POSIX 权限的实机行为仍未跨平台验证。
- **影响：** 若用户把逐字稿写到其他账户可读的共享目录，输出可能被共享目录的权限策略暴露。用户主动选择共享目录时可能是预期行为。
- **整改与后续对策：** 已按提示方式实现，不因用户主动选择共享目录而阻断转写，且不擅自更改既有 ACL。后续在 Windows 与 POSIX CI/实机验证 ACL/mode 检查准确性；共享权限提示属于风险线索，不保证识别所有继承权限策略。

### AUD-12：许可证和远端发布证据未齐（P1，发布前）

- **证据：** 当前没有 `LICENSE`，许可证决定留给仓库所有者；英文 README、CHANGELOG、SECURITY、独立安装说明、贡献指南和示例配置已补齐。远端 CI、远端安装与真实链路证据仍缺。
- **影响：** 未确定许可条件前，第三方无法明确复制、修改和分发权限；也不能把未跑的远端 CI 或未测的真实链路写成发布通过。
- **对策：** 由仓库所有者选择许可证；在此之后记录许可证与第三方模型/浏览器依赖的边界，再运行远端 CI 和干净安装。未取得许可证决定前，不公开分发项目或发行包。

### AUD-13：模型下载没有固定版本修订号（P2，供应链可复现性，已整改）

- **修复前证据：** 模型仓库 ID 按 profile 固定，但 `snapshot_download` 调用没有指定 revision；当前完整性检查主要确认所需文件存在并解析配置。
- **影响：** 同一命令在不同时间可能取得仓库不同版本的模型文件，复测和回滚难以精确复现；恶意或错误上游变更也难以通过本地完整性检查识别。
- **整改：** medium 和 small 下载已固定完整 Hugging Face commit revision，并记录官方 API/tree 证据与选择日期，见 `skills/douyin-transcript/references/MODEL_PROVENANCE.md`。权重未下载，文件哈希和真实推理仍未验证；模型升级需做质量/性能回归。

### AUD-16：失败重试没有复现首次运行配置（P1，功能一致性；新任务已整改）

- **修复前证据：** `retry-failed` 按任务 profile 构造默认 pipeline；数据库没有保存 `language`、`timestamps`、术语规则或资源上限快照。
- **影响：** 首次运行使用 `--language auto`、`--timestamps` 或词典后失败，重试可能按默认中文、无时间轴、关闭词典运行；输出会与原请求不同。
- **整改与限制：** schema v3 增加 `processing_options_json`，本地/远端任务建立时保存白名单非正文设置和词典规则快照；重试验证并恢复快照，支持显式 `--output-dir` 覆盖。`--force` 重开完成任务会刷新最近 attempt 的 profile/title/options。旧任务缺少或无法校验快照时默认 skipped；只有显式 `--use-current-defaults` 才按当前配置重试，并将被选择的快照持久化。端到端用例覆盖 auto、时间轴、词典、资源限制、输出目录及摘要/日志/数据库不含逐字稿正文。

### AUD-17：50 条批次验收仍不完整（P1，稳定性；离线模拟已补齐）

- **修复前证据：** 原集成批次仅覆盖 10 条；虽有 50 条输入接受测试和 100 条硬上限，但没有 50 条混合任务调度用例。
- **影响：** 单测边界不能证明批量混合状态下的结果数量、任务最终状态、下载并发和缓存/输出增长受控。
- **整改与限制：** 新增假 downloader/ASR 的 50 条模拟，包含 8 条预先完成缓存、下载失败、重复链接和新增成功任务；断言 50 项结果无遗漏、状态计数、47 条唯一任务、最大 2 个并发下载、ASR 同时最多 1 个，以及媒体缓存和 Markdown 输出数量/字节。此测试不验证真实媒体、真实磁盘耗尽、网络服务或所有 OS 调度行为。

### AUD-18：发布文档与验证材料尚未齐备（P1，发布前；本地材料已补齐）

- **证据：** 已新增英文 README、CHANGELOG、SECURITY、Skill 独立安装说明、示例配置和术语 JSON；仍没有 P1/P2 真实验收报告，且仓库所有者尚未选择 LICENSE。
- **影响：** 用户缺少英文安装、安全报告渠道和版本变更说明；真实模型、平台和发布门槛没有可审阅证据。未选许可证时不应公开分发。
- **整改与后续对策：** 本地文档和示例已补齐；`P1_REPORT.md`、`P2_REPORT.md`、`BENCHMARK.md` 已作为 `NOT VERIFIED` 模板提交到工作树，尚无真实结果。由仓库所有者决定 LICENSE；获得授权媒体后再填写真实验收结果，并将远端 CI、Agent 调用和干净远端安装证据纳入发布报告。不得用模拟结果代替真实验收。

### AUD-19：并发清理可能删除活动下载临时文件（低危可靠性问题）

- **修复前证据：** 下载器开始下载时创建 `.part` 文件，但只有完整下载后 pipeline 才把 `media_path` 写入任务；原清理流程只基于已提交的 `media_path` 保护活动任务，并允许清除过期临时文件。
- **前置条件与影响：** 用户在下载仍进行时，另一个进程显式运行 `cache clean --apply` 且保留期覆盖该临时文件。POSIX 上可能解除临时文件名并使下载最终替换失败；这是操作者并发清理导致的可用性问题，不是远端攻击路径。
- **整改与验证（后续 AUD-56 已替换协调方式）：** 早期实现曾在完整清理期间持有 `BEGIN IMMEDIATE`；当前 `cache clean --apply` 在事务外扫描和规划，并通过 `cache_entry_cleanup_guard()` 对每个候选分别核对任务引用与 claim，再在该短事务内完成身份绑定的单文件删除。活动下载竞态、两个 `TaskStore` 写入者可在文件间推进、stale claim recovery 及无任务库 preview 均有回归。默认仍是 dry-run。

### AUD-20：Windows 并发首次打开数据库时 WAL 初始化可能失败（低危可靠性问题，已整改）

- **证据：** 全量复测中的 `test_concurrent_task_store_opening_survives_wal_sidecar_lifecycle` 曾在并发创建 `TaskStore` 时失败，SQLite 抛出 `OperationalError: locking protocol`。原 `_enable_wal()` 仅重试错误文本含 `locked` 的情形，因而立即终止；同一用例单独重跑通过，符合首次并发初始化的瞬时竞争特征。
- **影响：** 多个进程/线程第一次同时打开同一任务库时，某个调用可能无法启用 WAL 并中止。
- **整改与验证：** WAL 初始化现在对 `SQLITE_BUSY`、`SQLITE_LOCKED`、`SQLITE_PROTOCOL` 和相应瞬时错误文本在配置等待窗口内重试；新增模拟 `locking protocol` 的确定性测试。当前全量离线测试 **303 passed, 17 skipped**，并发首次打开用例通过。

### SEC-25：doctor 子进程可能从当前工作目录导入模块（中危，已整改；后续差异扫描复核无新候选）

- **位置与证据：** `skills/douyin-transcript/src/douyin_transcript/doctor.py:71-81` 和 `:120-129` 分别启动可选依赖导入检查及 Playwright Chromium 路径检查，参数均为 `[sys.executable, "-c", ...]`，未开启 Python safe-path 模式。父进程检查依赖是否已安装，但没有把子进程导入绑定到已解析的包路径。
- **攻击前置与影响：** 本地攻击者须能在用户将要运行 `douyin-transcript doctor` 的当前目录放置 `av.py`、`faster_whisper.py` 或 `playwright` 同名模块。用户运行诊断后，子解释器可能优先导入当前目录模块并以当前用户权限执行代码；需要用户运行命令，不提升权限。
- **验证状态：** Codex Security Diff Scan 将该项评为中危、高置信度（finding `csf_0773548c9743b8b2a7b7a7ca`）。原扫描前用无害影子模块确认缺陷；随后两处 Python 子进程均加入 `-P`。新增测试在临时工作目录放置 `json.py` 并确认子进程不执行其副作用，同时验证两个探测命令均传入 safe-path 参数。doctor/downloader/pipeline 定向测试 **82 passed, 1 skipped**；全套 Windows 离线测试 **303 passed, 17 skipped**。之后的 Codex Security Diff Scan `8537ef61-e6e5-4b6a-8fc7-f162382c098a` 覆盖该修复所在文件，28 项差异复核没有保留新的安全候选；该静态结果不替代宿主或跨平台运行验收。

- **处理结论：** 本地触发路径已关闭。修复不会拦截依赖环境的 site-packages 导入；Python 3.11+ 支持 `-P`。保留环境变量 `PYTHONPATH` 的既有语义，该环境变量应由操作者信任。

### SEC-26：处理 worker 和浏览器 setup 子进程可能导入当前目录影子包（中危，源码复核发现并已整改）

- **位置与证据：** `processing.py` 以 `sys.executable -m douyin_transcript.processing_worker` 启动处理 worker，并为导入项目包添加可信源码根路径，但 Python 默认仍可能把当前目录放在更高优先级；同类地，`cli.py` 的 Chromium 安装命令以 `python -m playwright` 启动模块。两处原先都没有启用 safe-path。
- **攻击前置与影响：** 用户在含恶意同名 `douyin_transcript` 或 `playwright` 包的目录中触发远端转写或显式安装 Chromium 时，子进程可能在目标模块加载前执行攻击者代码，权限为当前用户权限。需要用户主动运行对应命令，不提升权限。
- **整改与验证：** 两处默认子进程命令加入 Python `-P`。处理 worker 回归在临时当前目录创建带副作用标记的影子 `douyin_transcript` 包，确认 worker仍从已配置源码根启动且标记未出现；setup 参数回归确认调用为 `python -P -m playwright ...`。整改时的 Windows 全套离线测试 **303 passed, 17 skipped**。SEC-26 不在先前冻结的 Diff Scan 中；后续扫描 `8537ef61-e6e5-4b6a-8fc7-f162382c098a` 已覆盖相关源文件，没有发现新的可报告候选。真实 Agent 和跨平台子进程行为仍待验收。

### AUD-39：默认远端下载 decoder 返回类型与 downloader 接口不匹配（P1，功能阻断，已整改）

- **位置与证据：** `pipeline.py` 的默认远端路径将 `lambda path: self._validate_media(...)` 传给 `download_media()`，而该校验器返回 `MediaFile`。`downloader.py:_coerce_validation()` 只识别 `_Validation` 或 `(format, duration)` 二元组，随后按下标读取返回值，因而接收 `MediaFile` 时抛出 `TypeError`。新下载路径把异常转换成 `MEDIA_DECODE_FAILED`；缓存校验路径捕获泛化异常并跳过该缓存，之后重新下载仍会遇到同一类型错误。
- **影响：** 使用默认 pipeline 处理远端 URL 时，新下载媒体不能通过校验，任务失败；已有远端缓存也无法正常命中。这阻断项目核心的远端转写功能。该项为代码路径复核确认的可靠性问题，不是本轮安全扫描的安全 finding。
- **整改：** `_coerce_validation()` 现在明确接受 `MediaFile`，以其 `format`、`duration_seconds`、`identity` 形成统一验证结果；下载器仍用发布后的 `final` path 构造输出对象，并保留对 `.part` 文件校验取得的身份信息。默认 pipeline 无需改变 callback。
- **验证：** 新增 downloader 回归同时覆盖临时下载文件解码和后续缓存命中，断言网络只请求一次、缓存再次校验且文件身份一致；新增默认远端 pipeline 离线集成回归，确认 `MediaFile` 校验结果进入 ASR。相关 doctor/downloader/pipeline 定向测试 **82 passed, 1 skipped**；全套 Windows 离线测试 **303 passed, 17 skipped**。真实 CDN、PyAV 和 ASR 仍待集成验收。

### AUD-40：下载阶段没有遵守单条任务共享 deadline（P2，已整改）

- **位置与证据：** pipeline 为远端任务生成 `processing_deadline`，但原先没有传给 `download_media()`；下载器另建默认 300 秒总时限。因此 `--processing-timeout-seconds 1` 不能约束下载，任务可能先等待更长的下载器上限。
- **影响：** 配置超时与实际任务最长等待不一致，批量任务在网络停滞时会超出用户设定。
- **整改与验证：** 默认 pipeline 现在传递绝对 deadline，downloader 取自身 `total_timeout` 与该期限的最小值；原来的默认 300 秒 cap 保持有效。新增短 deadline 请求回归断言下载提前返回超时并清理 `.part`，pipeline 集成回归确认期限已传递。Windows 全套离线测试 **303 passed, 17 skipped**。

### AUD-41：远端下载耗尽任务时限时错误码不一致（P2，已整改）

- **证据：** downloader 对任何自身 deadline 都返回 `TIMEOUT`，但 Skill/CLI 合同要求单条处理期限统一返回 `PROCESSING_TIMEOUT`。
- **影响：** 相同的用户设置在下载与 ASR 阶段显示不同错误码，自动化调用方无法一致识别任务时限到期。
- **整改与验证：** pipeline 检查 `TIMEOUT` 是否与共享 `processing_deadline` 同时到期；如果是，则持久化为 `PROCESSING_TIMEOUT`。仅 downloader 自身 300 秒上限先到时仍为 `TIMEOUT`。新增远端 pipeline 回归检查返回值和 TaskStore 错误码一致，全套测试 **303 passed, 17 skipped**。

### AUD-42：重试未恢复首次执行的处理时限（P2，已整改）

- **证据：** 初版处理选项快照未包含 `max_processing_seconds`，`retry-failed` 每次都采用当前 CLI 默认值。
- **影响：** 使用较短时限（例如 60 秒）失败的任务可能按默认 7,200 秒重新排队，任务行为不能重现。
- **整改与验证：** 快照升级为 schema v2 并保存 `max_processing_seconds`；旧 schema v1 仍接受并按其原先默认 7,200 秒解释。未传重试参数时恢复快照；显式传入 `--processing-timeout-seconds` 时更新并保存该次选择。CLI 回归覆盖恢复、自定义覆盖、持久化及拒绝无效值，全套测试 **303 passed, 17 skipped**。

### AUD-43：时间轴 sidecar 缺少任务完整性绑定（P2，已整改并通过本机回归）

- **证据：** 原 `_write_timeline()` 直接创建并写入最终 sidecar，且任务库没有 sidecar 路径/摘要；崩溃可能留下截断文件，完成任务也不检测 sidecar 缺失或修改。
- **整改：** schema 升级到 v6，保存 `timeline_required`、sidecar 词法路径和预期 SHA-256。pipeline 在原子发布前持久化路径/摘要；`complete_task()`、完成任务 skip 判断和 `recover_interrupted()` 同时校验主稿及 sidecar。候选文件名发生普通文件或 symlink 碰撞时保留原文件并尝试数字后缀。v5 迁移对 timestamps 明确为 false 的旧任务保留主稿校验；true、缺键或坏 JSON 的 completed/writing 任务因缺 sidecar 绑定而失效，要求显式重跑。
- **验证：** 回归覆盖 v5→v6 迁移（true/false/缺键/坏 JSON）、缺 sidecar 拒绝完成、摘要正确后完成、sidecar 修改后失效、崩溃恢复仅在 sidecar 完整时完成，以及 pipeline 成功/重复跳过/修改后不再跳过。普通文件碰撞通过；symlink 碰撞用例因 Windows 环境无法创建 symlink 而跳过。定向测试 **51 passed, 2 skipped**；最新全套测试 **303 passed, 17 skipped**。Linux/macOS 文件系统和原子发布行为仍待平台验收。

### AUD-44：URL 清单与术语词典读取 FIFO 可能永久阻塞（P2，已整改）

- **证据：** `_read_url_file()` 与 `_read_correction_dictionary()` 原先按路径直接 `open("rb")`；POSIX FIFO 在 `open()` 阶段等待 writer，后续字节长度限制无法生效。
- **影响：** 用户或 Agent 若把 FIFO 误传为清单/词典，CLI 会挂起；需要退出进程才能恢复。
- **整改与验证：** 两个读取入口现在使用 POSIX `O_NONBLOCK` 打开文件，先通过 `fstat` 拒绝非普通文件，再清除 nonblocking 标志并按原字节上限读取。子进程回归以 2 秒 timeout 防止测试自身挂起，并覆盖 URL 清单和词典两种入口；本次 Windows 全套 17 个跳过项中含这两项 POSIX 专属用例，因此未在本机动态执行。

### AUD-45：自定义输出目录绕过逐字稿权限提示（P2，条件性；本机已整改，跨平台待验收）

- **修复前证据：** `doctor` 仅接受 `--data-dir`，`collect_report()` 按配置解析默认 `output_dir` 并检查它的 ACL/mode。`transcribe --output-dir` 可以覆盖本次目标；`retry-failed --output-dir` 可以覆盖失败任务保存的目标，未提供时重试会从任务配置快照读取原目标。`transcribe --dry-run` 的 `_path_writable_without_create()` 只判断路径是否可写，不检查共享权限；正常转写和重试也没有在写入前检查实际目标目录。Windows 新建输出目录通过 `CreateDirectoryW` 使用继承的默认安全描述符，未在该调用中设置私有 DACL。
- **影响与条件：** 用户或 Agent 显式指定共享目录，或重试恢复了共享目录快照时，逐字稿可能继承允许其他账户读取的权限。`doctor` 检查另一个默认目录时不会提示这次目标；用户有意保存到共享位置时也可能符合预期，因此属于条件性隐私风险，而非未授权远程写入。
- **整改：** `doctor` 增加 `--output-dir` 覆盖；dry-run、转写和 `retry-failed` 都检查本次实际目录或最近现存父目录。JSON 摘要包含聚合状态和目录明细；文本模式在 stderr 对 `unsafe`/`unknown` 提示，即使启用 `--quiet` 也会保留隐私警告。权限状态为 advisory，不阻止用户有意选择共享目录，也不修改已有 ACL。
- **验证与限制：** CLI/doctor 定向回归覆盖显式目标、未创建目录、JSON 结构和 stderr 警告；本机 Windows 通过。真实 Windows 多账户 ACL、POSIX mode/扩展 ACL、目录在长时间处理期间权限被并发修改的情形尚未跨平台验证。检查是运行前提示，不构成对抗并发 ACL 变更的保证。

### AUD-46：重试输出目录覆盖没有持久化（P2，功能一致性；已整改）

- **修复前证据：** `_run_retry()` 只有显式传入 `--processing-timeout-seconds` 时才生成并传递新的 `processing_options`。`--output-dir` 虽被用于本次 `task_paths`，但单独使用时 `TaskStore.retry_failed()` 收到 `processing_options=None`，保留旧快照中的输出目录。
- **影响：** 该次运行按命令行覆盖目录输出，但任务仍保存旧目录；后续失败重试、状态恢复或 `--force` 无法复现最近一次显式目录选择，与 CLI/发布文档承诺不符。
- **整改与验证：** 传入 `--output-dir` 或处理超时覆盖的任一项时，均创建 schema v2 快照；路径覆盖写入选中的有效输出目录，超时值在显式提供时更新，否则沿用任务快照规范化出的值。新增独立回归只传 `--output-dir`，检查 pipeline 实际路径及 TaskStore 中持久化后的目录和超时。CLI/doctor 定向测试集 **58 passed, 2 skipped**；Ruff 通过。

## 5. 复测命令

从仓库根目录执行：

```powershell
uv lock --project .\skills\douyin-transcript --check
uv run --project .\skills\douyin-transcript --locked --no-sync --group dev ruff check .\skills\douyin-transcript\src .\skills\douyin-transcript\scripts .\tests
uv run --project .\skills\douyin-transcript --locked --no-sync --group dev pytest -q --basetemp "$env:USERPROFILE\.codex-private-test-temp"
git diff --check
```

当前的发布前条件、证据与限制汇总见 [RELEASE_REPORT.md](RELEASE_REPORT.md)。架构、逐阶段证据和发布清单见 [ARCHITECTURE.md](ARCHITECTURE.md)、[ACCEPTANCE.md](ACCEPTANCE.md) 与 [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)。上一轮 Codex Security 结构化扫描记录 5 项源码发现、此前 Diff Scan 记录 SEC-25；两者都绑定启动时快照。较早的 Diff Scan `484bb340-323c-4bec-a20a-368b2fcd077d` 覆盖其冻结清单内 30 个源码/配置审查项且未发现新候选；之后的扫描与动态验收见第 9、10 节。SEC-26 与 AUD-40 至 AUD-55 的后续修复情况以本报告各条记录为准。SEC-14 仍待目标 Agent 宿主验收；SEC-15 创建路径边界已进一步收紧，但 SQLite/Playwright/模型等 pathname-only API 仍有 TOCTOU 和多平台测试；SEC-16 fallback 需多主机验证，SEC-17/18 需真实模型/Hub cache 验收，AUD-21 需第二账户集成。SEC-19/20 配置路径及同句柄读取已整改，SEC-24 与 AUD-44 的 POSIX FIFO 行为待 Linux/macOS 运行验证；AUD-43 sidecar 路径/摘要已绑定并由完成、跳过和恢复流程校验，跨平台文件系统验收仍待完成。AUD-39 已通过 downloader 和默认 pipeline 回归。

## 6. 审核范围说明

本报告审阅当前本地工作树与可见 Git 历史，不代表远端分支或已发布版本。SEC-19/20 的 Windows 配置回归通过；POSIX symlink/`..`、替换竞态与 FIFO 用例因当前主机是 Windows 而跳过。SEC-22 有伪造 frontmatter、文件修改及恢复行为回归；共享输出目录并发替换仍需平台集成。AUD-36 已实现 POSIX 目录同步和 Windows 写穿透发布，AUD-37 的通用 Win32 错误分类已整改；Linux/macOS 和其他文件系统的断电耐久性未验证。AUD-32/33 由阻塞 resolver 模拟回归覆盖，但真实 DNS/Chromium 链路未验证；SEC-23 源码修复有模拟覆盖，真实媒体格式仍待样本确认；AUD-38 的实际时耗尚无基准。截至该段形成时最新的 Codex Security Diff Scan 已复核冻结差异内 28 个审查项且无新候选，包括 SEC-25/26 修复所在文件；该扫描不代表全仓动态审计。POSIX 扩展 ACL 语义无法在 Windows 环境确认，故整体项目验收 coverage 仍为 partial。AUD-39 已由下载器缓存/新下载测试及默认远端 pipeline 回归修复。本机未动态验证真实抖音媒体、在线 CDN、ASR、远端 CI、第三方二进制、Linux/macOS 和 Agent 宿主行为。当前 `doctor --json` 仍为 `setup_required`：ASR/PyAV/模型/Playwright/Chromium 未安装，默认 D: 工作区输出路径仍报告 `unsafe`；显式 profile 下候选输出目录检查为 `ok` 且未创建。P1 真实转写是项目计划的最早未通过阶段。

## 7. 追加复审与整改验证（2026-10-09）

### 范围与结论

SEC-27/AUD-52 阶段复审历史快照：当时检查 `browser_proxy.py` 的 CONNECT 数据转发、`pipeline.py` 的批次取消/线程池收尾、AUD-43 sidecar 崩溃恢复测试顺序、SEC-15 的路径创建/数据库/缓存清理/第三方 API 边界，以及 `urls.py` 的 DNS 等待和名额释放；未访问网络或真实媒体。AUD-47 至 AUD-50 的本地整改均有回归。首次全套测试发现一条旧 DNS 超时测试仍 mock 父进程的 `getaddrinfo`，与子进程实现不匹配；将其改为本地阻塞 worker 回归后，当时全套为 **316 passed, 17 skipped**。AUD-51 后全套为 **323 passed, 17 skipped**；SEC-15 创建竞态加固后为 **325 passed, 20 skipped**。当时新增 SEC-27 映射盘检测/诊断回归后，全套为 **331 passed, 20 skipped**；全仓 Ruff 通过，锁文件、敏感文件和 Agent Skills 检查通过。以上数字均为历史快照；彼时最新 334/20 及 AUD-53/SEC-28 结果记于下方续审；当前测试结果见第 2 节。

初始复审发现两项源码可确认的 P2 可用性问题，以及一项测试覆盖缺口，三项现均在本地修复并通过回归；没有确认新的跨账户路径漏洞。SEC-15 仍应保持“部分整改”：cache clean 的删除实现已有 POSIX dir-fd 和 Windows 根目录句柄相对处理；本轮进一步收紧了目录树和排他文件创建。剩余 pathname-only 边界主要在 SQLite、Playwright profile、模型下载、下载器缓存读写和输出校验。此结论没有跨平台集成证据。

随后追加复核 DNS 线程名额耗尽问题（AUD-50），确认在两个系统 resolver 长时间阻塞时会导致后续 DNS 请求失败；现已改为在有 deadline/取消的路径使用可终止子进程，并有名额回收回归。之后在 Windows 输出路径预检中发现权限诊断把只授予目录遍历/同步的 foreign ACE 也判作可读取，造成 `%USERPROFILE%\Transcripts` 误报（AUD-51）；已按权限掩码修复并增加 7 组策略回归。当前本轮发现的源码级可用性问题均已有本机整改；跨平台文件系统、真实 DNS/Chromium、ASR 及 Agent 宿主等项目验收仍未通过或缺少证据，因此整体仍未达到发布门槛。

### AUD-47：CONNECT 隧道数据转发的 `sendall()` 可无限阻塞（P2，可用性）

- **证据：** `skills/douyin-transcript/src/douyin_transcript/browser_proxy.py:138-139` 在 CONNECT 成功后把 client/upstream socket 设为阻塞模式。`_relay()` 在 `:184-201` 只用 `select()` 限制等待可读事件；读取到数据后对目标 socket 调用没有 timeout/deadline 的 `sendall()`。如果目标端保持连接但停止读取，发送缓冲区耗尽后该代理线程可卡在写入中。
- **影响与前提：** 每个处理线程占用 `_client_slots` 一个名额，容量为 64（同文件 `:30, 219`）。多个被反压的隧道可能耗尽槽位，使后续 Chromium CONNECT 请求收到 503 或挂起。触发需要连接端/对端形成持续写入反压；本轮未通过实际 socket 压力实验验证。
- **整改：** 已改为非阻塞双向转发，用有界缓冲区配合 `select` 监控读写；空闲或写入等待超时后关闭双端。新增回归验证目的端停止读取后 handler 有界退出且代理槽位可再次获取。
- **状态：** 本地已修复；`tests/unit/test_browser_proxy.py` 覆盖反压和槽位恢复，全套 Windows 离线测试通过。真实 Chromium 与 Linux/macOS socket 行为仍待验收。

### AUD-48：批量下载期间 Ctrl+C 可能长时间不能退出（P2，可用性）

- **证据：** `skills/douyin-transcript/src/douyin_transcript/pipeline.py:281-286` 的 `flush_downloads()` 同步调用 `future.result()`；`:300` 使用 `ThreadPoolExecutor` 上下文管理器。Ctrl+C 抛出 `KeyboardInterrupt`（不属于 `Exception`），离开 executor 上下文时仍会等待运行中的 worker 完成；finally 中的 `capture.close()` 要等 executor 退出后才执行（`:403-408`）。单条处理时限允许配置到 86,400 秒。
- **影响与前提：** 用户在远端批次下载期间按 Ctrl+C 后，主进程可能等待运行中的下载任务结束；最坏等待接近剩余处理时限，且浏览器资源的清理被延后。普通网络读超时不等价于用户取消。
- **整改：** 已增加可传播取消对象。中断时关闭活动下载响应/连接、打断重试等待、取消未启动 future、终止处理子进程、关闭捕获对象，并将活动任务记为可重试的 `CANCELLED`；CLI 返回 130。慢响应体、退避、捕获启动和 worker 收尾均有回归。
- **状态：** 本地已修复并通过定向及全套回归。带 deadline/取消的 DNS worker 在超时/取消时被终止并回收，再释放并发名额。无 deadline/取消的直接 helper 仍同步运行系统 `getaddrinfo`；该通用调用方式不属于当前 CLI 有时限的网络路径。真实 DNS 和跨平台进程终止语义未实测，详见 AUD-50。

### AUD-49：sidecar recovery 回归没有模拟生产中的崩溃顺序（P2，测试覆盖缺口）

- **证据：** `tests/unit/test_tasks.py:695-745` 的 `test_recovery_requires_the_expected_timeline_sidecar` 先 `timeline.write_bytes()`，之后才调用 `prepare_timeline_integrity()`。生产顺序是在发布 sidecar 前先将预期路径和摘要持久化（`skills/douyin-transcript/src/douyin_transcript/pipeline.py:895`），再原子发布侧车。当前用例覆盖“完整侧车已绑定”和“无侧车绑定”，但没有精确模拟“绑定已提交、sidecar 尚未发布即崩溃”或“发布后摘要不一致”的恢复边界。
- **影响与前提：** 不能仅凭该用例确认生产关键交错状态的恢复行为。源码检查显示缺失/无效 sidecar 会使任务重新进入下载态而非完成；本项是证据缺口，不代表已经确认实现错误。
- **整改：** 回归现按生产顺序先持久化预期路径/摘要，再创建 sidecar；覆盖匹配 sidecar、未绑定、绑定后缺失及摘要不符。缺失或不匹配时恢复到 `downloaded`，清除过期主稿和 sidecar 绑定。
- **状态：** 测试覆盖缺口已补齐，`tests/unit/test_tasks.py` 定向测试通过并纳入全套 **315 passed, 17 skipped**。Linux/macOS 文件系统行为仍待平台验收。

### AUD-50：系统 DNS resolver 卡住会耗尽全局解析名额（P2，可用性，源码已整改）

- **证据：** `urls.py` 原先通过 daemon 线程调用系统 `socket.getaddrinfo()`，以两个全局名额限制后台 resolver。Python 只能停止等待线程，不能终止阻塞中的系统调用；若两个查询都长期未返回，后续短链、下载和浏览器 CONNECT 解析会因名额耗尽立即失败，直到系统 resolver 返回或进程重启。
- **影响与前提：** 需要系统 DNS/名称服务查询至少有两个并发请求长期卡住。此时后续需要新 DNS 的任务无法继续；不是 SSRF 绕过，公网 IP 和域名 allowlist 校验仍在父进程执行。
- **整改：** 带 deadline 或取消信号的查询现在通过 `sys.executable -I -c` 启动隔离、无 shell 的 resolver 子进程；输入主机名限 253 字符，worker 地址列表最多 64 项，输出最多 8 KiB。父进程持续检查 deadline/取消；退出前终止并回收子进程后才释放两个共享名额。IP 解析和 `is_global` 判定仍在父进程。无 deadline/取消的直接 helper 调用保留同步语义，若调用方不设时限仍可能等待系统 resolver。
- **验证：** 新增阻塞 DNS 超时、两个 worker 同时阻塞后取消/回收、名额复用、公网/私网结果验证；更新 CONNECT 超时回归，并将下载器超时用例改为真实本地模拟 worker。相关定向回归 **29 passed**；最新 Windows 离线全套 **316 passed, 17 skipped**，全仓 Ruff、离线锁检查、敏感文件检查和 Agent Skills validator 通过。没有外网访问。
- **剩余对策：** 当前 CLI 的短链、下载、页面请求和 CONNECT 解析都传入期限；调用库 helper 时也应提供 deadline/cancellation。需在 Linux/macOS 和获授权的 Chromium/DNS 环境确认进程终止、管道关闭和槽位恢复行为。

### AUD-51：Windows 权限诊断将 traversal-only ACE 误报为可读取（P2，可用性/诊断，源码已整改）

- **证据：** Windows 用户 profile 祖先目录对一个 foreign AppContainer capability ACE 仅授予 `FILE_EXECUTE`/目录遍历（`0x20`）和 `SYNCHRONIZE`（`0x00100000`）。旧的 `_inspect_windows_acl()` 对任何 foreign allow ACE 都返回 `shared`，未考虑权限掩码；因此对尚未创建的 `%USERPROFILE%\Transcripts` 也会报告 `unsafe`。
- **影响与前提：** 这是权限诊断误报，会产生不必要警告并影响用户判断输出目录是否适用；本机 profile 祖先中的该 ACE 不授予目录列表、文件读取、写入或删除权限。默认 D: 工作区输出目录仍存在真实目录替换权限问题，继续报告 `unsafe`。
- **整改：** 新增 `_foreign_windows_ace_grants_sensitive_access()`，仅忽略遍历/同步位；其他访问位仍视为 foreign sensitive access。新增 7 组掩码策略回归，覆盖 traversal、synchronization、两者组合、读取、写入、删除子项和 generic read。
- **验证：** ACL 策略定向测试 **7 passed**；AUD-51 完成时全套 Windows 离线测试 **323 passed, 17 skipped**（历史快照），当前全套结果见第 2 节；Ruff、锁文件、敏感文件扫描和固定 `skills-ref==0.1.1` 校验通过。`doctor --output-dir "$env:USERPROFILE\Transcripts" --json` 报告权限 `ok`，且目标目录未创建；默认 `doctor --json` 仍对 D: 工作区输出报告 `unsafe`，整体状态为 `setup_required`。
- **剩余对策：** 在其他 Windows 版本、实际继承 DACL 和多账户环境验证诊断与新目录继承权限；POSIX ACL 和权限语义仍需 Linux/macOS 实机验收。该修正不表示 SEC-15 的 pathname-only/TOCTOU 边界已消除。

### SEC-27：映射网络盘未被 UNC 拒绝规则覆盖（源代码已整改，真实映射盘验收待做）

- **修复前证据：** `storage_security.py` 原先仅通过 `PureWindowsPath(...).anchor` 的 UNC/device namespace 前缀拒绝路径。盘符路径（例如 `Z:\private`）的 anchor 是 `Z:\`，不匹配该条件，因此可能继续进入权限检查和存储流程。
- **影响与前提：** 用户将 Windows 盘符映射到网络共享，并把敏感数据库、浏览器配置或缓存放在其下。该共享可能由网络端 ACL/管理员控制，和项目只支持本地私有存储的预期不同。当前没有证据表明实际共享权限可被未授权账户读取，故这是未覆盖的策略边界，不是已确认的数据泄露。
- **整改与验证：** `_canonical_storage_path()` 对盘符根调用 `GetDriveTypeW()`；`DRIVE_REMOTE` 被拒绝，`DRIVE_UNKNOWN`/`DRIVE_NO_ROOT_DIR` 失败关闭。错误诊断保留拒绝原因。Windows mock 回归覆盖远程盘、未知盘、无根盘、本地固定盘，以及 inspector/创建接口的可读诊断；本机真实 API 将 C:、D: 识别为 `DRIVE_FIXED`。相关文件定向测试 **33 passed, 11 skipped**，Ruff 通过；全套 **331 passed, 20 skipped**。本机没有映射网络盘，真实共享环境仍待验证。
- **剩余对策：** 在实际映射盘环境确认 `GetDriveTypeW()` 的结果及权限诊断；当前代码只对盘符根做盘型查询，UNC/device namespace 仍由路径语法拒绝。

### AUD-52：创建后的身份校验失败会留下私有残留对象（已加入明确提示；对象保留是安全默认）

- **证据：** `ensure_private_directory()` 和 POSIX `create_private_file()` 的异常收尾关闭 descriptor/handle，但未删除本次创建对象；Windows `_create_windows_private_file()` 和目录链创建同样只释放句柄。`tests/unit/test_storage_security.py:427-448` 的 Windows 目录替换用例显示新目录留在被移动的原父目录下；`:452-485` 的叶文件身份失败用例显式断言目标仍存在。创建对象在创建时设私有权限，因此当前证据支持“残留/重试语义问题”，不支持“残留可被其他账户读取”。
- **影响与前提：** 权限核验失败或路径在创建期间变化，操作向调用方报错，但新建的空目录/空文件可能留在路径或移出位置。反复重试可累积残留；已有同名目标会改变后续流程判断，也可能使用户误以为失败任务从未写入任何数据。
- **整改与设计复核：** 通用路径不执行自动删除。`ensure_private_directory()` 和文件创建的身份/权限失败会说明新建私有对象可能残留、祖先移动时位置也可能变化，并提醒先核对对象身份再清理；[TROUBLESHOOTING.md](../skills/douyin-transcript/references/TROUBLESHOOTING.md) 记录相同处理方式。Windows 目录替换和叶文件身份失败回归现在断言错误包含残留提示。设计复核确认 POSIX 先比较 inode 再按名称 unlink/rmdir 仍有竞态；Windows 文件可以另行评估句柄绑定删除，但目录创建 API 不返回新目录句柄。当前支持 Windows 10，不能依赖仅 Windows 11 24H2 提供的 `CreateDirectory2W` 作为通用方案。
- **剩余验收：** Windows 相关错误回归在 AUD-52 整改时纳入全套 **331 passed, 20 skipped**（历史快照）；当前 Python 3.11/3.12 全套见第 2 节。POSIX 分支在本机被平台跳过。当前处理不消除残留，只确保失败时明确告知并避免误删替换对象。

### 处置顺序

1. AUD-47 至 AUD-51 本地整改和离线回归已完成；SEC-27 的映射盘源代码整改和 Windows 模拟回归已完成，真实共享环境待验收。AUD-52 已加入错误提示、排障说明与 Windows 回归；POSIX 实机错误路径仍待验证。将相关回归纳入 Windows/macOS/Linux CI，并在获授权的 Chromium 环境验证 CONNECT 转发、DNS worker 回收、目录句柄创建和 Windows ACL 诊断。
2. 仍按 P1→P2→P4→P5/P6 验收门槛推进；当前真实 ASR、抖音/Chromium、人工听审与性能记录、Agent 宿主、跨平台 CI、许可证决定及发布授权均未完成，整体状态仍为 **NOT READY**。

### DOC-01：审核与发布文档的验证状态落后于当前工作树（P2，已修复）

- **修复前证据：** README 显示旧的 **323 passed, 17 skipped**；英文 README 称最新安全加固后没有复测干净副本；发布报告把 SEC-27/AUD-52 写成“检测映射盘”和“定义失败清理方案”，与已完成的代码整改及安全残留策略不一致。
- **影响：** 维护者和使用者会据此误判最新本地验证结果和剩余工作，审核报告、发布报告与 README 的项目状态不一致。
- **对策与结果：** 当时中文/英文 README 同步为 **334 passed, 20 skipped**；该次后续测试快照为 **356 passed, 20 skipped**，当前结果见第 2 节。干净副本说明明确为仓库外离线 no-dev 安装、版本和 dry-run 冒烟通过，远端安装/真实 Agent 调用仍未验证；发布报告将 SEC-27/AUD-52 改为实映射盘与 POSIX 提示验证，并保留不做路径名竞态清理的措施。实施计划追加了本轮验证快照。该次文档同步复核未发现其他源码问题；后续续审新增 AUD-53 与 SEC-28，见下文。项目仍有 P1/P2/P4/P5/P6 验收与所有者决定未完成，整体 **NOT READY**。

### DOC-02：发布清单缺少 P4 人工听审门槛（P2，已修复）

- **修复前证据：** 项目计划要求对多种音频抽样听审、记录 10 分钟以上媒体的耗时，并检查 stdout/stderr/Agent 摘要不包含逐字稿正文；`docs/RELEASE_CHECKLIST.md` 原先只列 P1/P2 和本地代码检查，没有独立的 P4 勾选项。
- **影响：** 发布审阅者可能在 P1 的转写命令成功后漏掉听审、性能及正文泄漏验收，尽管这些是项目计划明确要求。
- **对策与结果：** 发布清单现要求涵盖清晰中文、英文术语、背景音乐/停顿的至少三处听审，记录 10 分钟以上运行，并验证 stdout/stderr/Agent 摘要不泄漏正文；发布报告也将 P4 作为独立未完成门槛。真实素材仍需授权后验证。

### AUD-53：恢复任务在 SQLite 写事务内校验缓存媒体（P3，可用性，已整改）

- **证据：** `TaskStore.recover_interrupted()` 原先在 `BEGIN IMMEDIATE` 写事务中调用 `media_validator`。生产调用链传入 `_validate_media()`，默认由受监管的处理子进程完整解码缓存媒体；校验未传 deadline，可能等待很久。并发 CLI 的数据库 busy timeout 为 5 秒，因此一个恢复任务可能阻塞其他进程的 claim/create/update，随后报 SQLite busy/locked。
- **影响：** 重启时若有 stale cache，恢复阶段可长时间阻止同一数据目录下的其他任务继续运行；耗时取决于媒体长度和主机。
- **对策与结果：** 恢复现在先短暂读取候选任务，在事务外校验媒体和已发布输出；提交阶段重新读取行并要求完整 `Task` 快照未变化。若 worker heartbeat、状态转换或另一个恢复过程已更新任务，旧恢复结果会跳过，不清除新 claim。新增慢 validator 回归：校验暂停时第二个连接仍可写入；另一个回归确认并发 heartbeat 后恢复不会清除续租任务。定向任务/扫描器测试 **37 passed, 1 skipped**；Python 3.11.15 Windows 离线测试 **334 passed, 20 skipped**。Python 3.12 兼容性另见 AUD-55。
- **剩余验收：** Windows 本机并发回归通过；Linux/macOS 与真实长媒体解码集成尚未运行。事务外文件检查结束到提交之间文件仍可能变化，后续转写仍须执行处理阶段的媒体身份校验。

### SEC-28：敏感文件检查器遗漏通用 cache/ 目录（P2，扫描覆盖，已整改）

- **证据：** `.gitignore` 将 `cache/` 定义为用户数据目录，项目计划把媒体放入 `cache/media/`；但 `scripts/check_sensitive_files.py` 原禁用目录表只包含 `media-cache`，不会按路径拒绝通用 `cache/` 下未知后缀。内容扫描对二进制、非 UTF-8 文件及大于 2 MiB 的文件会跳过。
- **影响：** 若敏感媒体或缓存文件被强制加入 Git，即使扩展名不在已知列表中且内容无法解码，路径检查也可能漏报。
- **对策与结果：** 检查器现将任意路径分量名为 `cache` 的 Git 可见文件列为敏感数据目录，新增未知扩展名路径回归。完整 Windows 离线套件 **334 passed, 20 skipped**；`python scripts/check_sensitive_files.py` 在当前 Git 可见树通过。
- **剩余验收：** 检查器只覆盖 Git 可见路径，无法替代发布前对完整 Git 历史、强制暂存路径和远端仓库的人工审查；大文件/二进制凭据扫描仍不在其能力范围内。

### DOC-03：发布清单把有限文本扫描描述得过宽（P3，已修复）

- **修复前证据：** 清单称敏感文件检查覆盖 Git 可见“文本文件”；实际扫描仅读取不超过 2 MiB、无 NUL 且可解码为 UTF-8 的文件，二进制和较大文件会跳过。
- **对策与结果：** `docs/RELEASE_CHECKLIST.md` 现明确列出 Git 可见路径、2 MiB 限制及 UTF-8 解码条件，并说明二进制/大文件与完整历史扫描不在覆盖范围。

### AUD-54：恢复器释放 claim 后旧 worker 仍能写入失败状态（P2，并发状态完整性，已整改）

- **修复前证据：** `tasks.py` 的 `transition()` 与 `fail_task()` 原先仅在 `claimed_by` 非空且不等于传入 `worker_id` 时拒绝；恢复路径会清除 `claimed_by` 和 `claimed_at`，所以 claim 清空时旧 worker 的带 ID 调用仍被允许。`pipeline.py` 的 heartbeat 线程遇到 claim 丢失后只退出线程，不通知正在等待 ASR 的主线程；主线程恢复后因状态转换非法进入异常处理，再用旧 ID 调用 `fail_task()`。
- **修复前复现：** 本机只读最小复现将 stale 的 `transcribing` 任务恢复为 `downloaded`，确认恢复后 `claimed_by=None`；随后旧 worker 调用 `fail_task()` 成功将其改成 `failed`。本节下方记录了修复和当前正式回归结果。
- **影响：** 修复前，恢复器已确认可复用的缓存任务可能在新 worker 重新认领前被旧处理线程再次标为失败，导致后续重试或重新下载。若新 worker 已用不同 ID 认领，旧 owner 检查会阻止旧 worker；缺少 generation token 无法稳健覆盖 claim 释放、重用和交错顺序。
- **对策与结果：** tasks schema 升至 v7，新增单调递增 `claim_generation`。每次 claim 递增代次；release、失败、完成与 recovery 使旧代次失效。worker 状态写入同时要求当前 worker ID 和 claim generation 匹配；旧 API 调用传有 worker ID 但任务无人认领时也会拒绝。heartbeat 通过带 generation 的原子更新续租。pipeline heartbeat 发现 claim 丢失后取消任务级处理 token，下载/ASR 子任务继承取消信号，批次取消仍只作用于对应任务。
- **验证：** 新增恢复后旧 worker 失败写入被拒绝、worker ID 重用仍被 generation 拒绝、pipeline claim recovery 后取消处理及 linked-child 取消回归。原定向 suite **109 passed, 3 skipped**；当时 Python 3.11.15 和 3.12.13 Windows 全套均 **356 passed, 20 skipped**（当前结果见第 2 节）。Ruff 通过。
- **剩余验收：** Windows 本地并发回归通过；Linux/macOS CI、真实长时间 ASR 被回收时的集成行为仍待验收。

### AUD-55：Python 3.12 Windows 文件身份变化使缓存清理 fail closed（P1，兼容性，已整改）

- **证据：** 项目声明支持 Python `>=3.11,<3.13`，GitHub Actions 矩阵包含 3.11 和 3.12。`cache.py::_unlink_windows_by_handle()` 使用旧版 `BY_HANDLE_FILE_INFORMATION` 结构（卷序列号为 32 位 `DWORD`、文件索引为 64 位），并直接与 `os.stat()` 的 `st_dev`/`st_ino` 比较。Python 3.12 的 Windows `os.stat()` 已允许 `st_dev` 为 64 位、`st_ino` 为 128 位；本机 Python 3.12.13 实测 `st_dev=16912900303482848603`，而同一路径的旧 API 返回 32 位卷序列号 `3065054555`，因此目录身份比较失败并跳过删除。参见 [Python 3.12 发布说明](https://docs.python.org/3.12/whatsnew/3.12.html) 和 Microsoft 的 [FILE_ID_INFO 文档](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info)。
- **验证（修复前）：** Python 3.12.13 全套曾为 **8 failed, 326 passed, 20 skipped**，8 个失败集中在缓存 age/capacity 清理、活动任务保护与 handle-race 清理。Python 3.12 Ruff 通过。
- **对策：** Windows Python >=3.12 现在通过 `GetFileInformationByHandleEx(FileIdInfo)` 获取 `FILE_ID_INFO`，用 64 位 volume serial 和 128 位 file ID 与 Python `os.stat()` 身份字段对齐；3.11 保留 `BY_HANDLE_FILE_INFORMATION` 路径。无法取得稳定身份时仍失败关闭并跳过删除。当前本机实测新结构与 `st_dev`/`st_ino` 一致。
- **验证（修复后）：** Python 3.12 缓存相关 pytest **26 passed, 2 skipped, 40 deselected**；当时 Python 3.12.13 与 Python 3.11.15 Windows 全套均 **356 passed, 20 skipped**（当前结果见第 2 节）。两套环境的 Ruff 均通过。GitHub Actions 远端矩阵尚未运行。
- **状态：** 本机实现与 Python 3.11/3.12 离线验证已完成；远端 CI 和 Linux/macOS 行为仍待验收。

### AUD-56：批量缓存清理占用 SQLite 写锁时间无上限（P2，可用性，已整改）

- **原问题：** 早期 CLI 在一个 `BEGIN IMMEDIATE` 事务中扫描并删除整个缓存，其他数据库写入者可能等待文件系统 I/O。
- **对策：** `cache.py` 在事务外完成扫描、候选排序和最终复查；CLI 为每个待删文件调用 `TaskStore.cache_entry_cleanup_guard()`。短事务只重读对应 video ID 的任务状态、活动下载 claim 和 local_path，然后执行一个身份校验后的 unlink。schema v8 增加 `video_id` 与 `local_path` 索引。
- **回归：** `tests/unit/test_cli.py` 覆盖缓存计划期间新 claim 生成 partial、两个写连接在不同文件删除之间推进、完成任务的本地输入不被误删；`tests/unit/test_tasks.py` 检查新索引。该阶段 Python 3.11.15 全套 **356 passed, 20 skipped**；当前结果见第 2 节。
- **剩余边界：** 单次操作系统文件删除本身无法由 SQLite 事务设定硬时间上限；一个特别慢的 unlink 仍会占用一次短事务。跨平台/真实慢盘集成待验收。

### AUD-57：缓存清理可能删除已完成任务的本地原始输入（P2，数据保留，已整改）

- **证据：** 缓存清理按下载器文件名识别媒体。旧保护逻辑排除 completed 任务的 media_path，也未保护 local_path；若用户把源文件直接放在应用 media-cache，且文件名碰巧符合下载器格式，它会成为清理候选。README 承诺本地源文件不会被清理。
- **对策：** CLI 现在把每条任务记录的 local_path（无论任务是否完成）交给 cache inspection；删除前的 `cache_entry_cleanup_guard()` 也在数据库事务内复核 local_path，避免预览后新插入/变化的引用逃过保护。数据库新增 local_path 索引。
- **回归：** `tests/unit/test_cli.py::test_cache_clean_preserves_completed_local_source_matching_cache_name` 验证已完成本地输入不被删除。
- **剩余边界：** 应用 media-cache 保留给程序管理；从未提交为任务、但用户自行放入此目录的源文件无法仅凭命名与应用缓存可靠区分。建议避免把未登记输入放进该目录。

### 续审：2026-10-09 工作树安全差异扫描

- **范围：** Codex Security Diff Scan `8537ef61-e6e5-4b6a-8fc7-f162382c098a`，基线/HEAD `3e06080e6b9eb7e8843de4de2fec4a03f5c91d5c`，冻结快照 digest `codex-security-snapshot/v1:sha256:aa0314f296588ea1f7b0944b5e02167cfac1d57dea4fe9427d84f6c37f88e84a`。扫描器生成 28 个代码审查项，全部完成静态复核。
- **结论：** 未识别出新的可报告安全候选。结果只说明该冻结差异中已检查的代码项没有确认新问题；此前已登记的 AUD-52 残留对象风险仍是已知限制，真实运行环境与全仓审计门槛也不因此关闭。
- **后续对策：** 保持 AUD-52 的失败关闭和明确残留提示；在授权后完成真实 ASR 与浏览器/抖音验收、人工听审和性能记录；在 Linux/macOS 与 Windows 多账户环境验证 ACL/文件句柄行为，并运行远端 CI；由仓库所有者决定许可证和发布授权。完成前维持 **NOT READY** 状态。

### DOC-04：中文 README 与 GitHub 问题收集材料不完整（P2，已修复）

- **证据：** 实施计划第 15 节要求中文 README 给出虚构或授权样本的 JSON/Markdown 输出示例，并覆盖 403/登录、音频捕获、`av` 冲突、模型源速度、C 盘空间、无 GPU 和路径问题；GitHub 仓库还应提供 Bug/功能请求模板。复核时中文 README 没有输出样例，缺少上述 FAQ，`.github` 目录只有 CI 工作流，没有 Issue 模板。英文 README 有 JSON 摘要样例，但不能替代中文 README 的指定交付。
- **影响：** 中文用户无法快速确认输出格式和常见故障处理；公开问题容易缺少环境/复现信息，也可能误传私有媒体、Cookie、签名链接或完整本地路径。
- **对策与结果：** 中文 README 新增明确标注虚构数据的 JSON 与 Markdown 样例，以及 7 类 FAQ；`--json` 输出字段说明同步到实际摘要 schema。C 盘说明按源码支持的 `DOUYIN_TRANSCRIPT_HOME`、`UV_CACHE_DIR` 和 `PLAYWRIGHT_BROWSERS_PATH` 分别说明数据、uv、浏览器目录，CPU FAQ 对齐默认 CPU/int8 配置。新增 GitHub Bug 与 Feature Request 表单，要求脱敏复现并显式禁止提交媒体、逐字稿、Cookie、签名 URL、账户信息和未经脱敏日志；漏洞报告引导到 `SECURITY.md`。
- **验证范围：** 文档和表单静态复核；未改动程序代码，未运行测试。模板不请求或收集私人媒体与认证材料。
- **剩余验收：** GitHub 表单实际渲染需推送后在目标仓库验证；仓库当前未配置 remote，且未授权发布。本地文档缺口已关闭，整体项目仍受 P1/P2/P4/P5/P6、SEC-15 平台验收和所有者决定阻塞，状态保持 **NOT READY**。

### DOC-05：媒体缓存增长缺少操作层面的保留期建议（P3，已补充）

- **证据：** V1 默认保留远端媒体以支持重试，并提供预览优先的 `cache clean`；README 和 CLI reference 说明了清理参数，却未给普通用户一个定期检查的操作起点。发布报告仍将“补充保留策略”列为本地文档缺口。
- **影响：** 长期批量使用时，用户可能不清楚何时检查缓存或如何安全执行清理，造成磁盘占用持续增长。
- **对策与结果：** README 新增每月手动检查建议和两步示例：先 `cache inspect --json`、再用 `cache clean --max-age-hours 720 --json` 预览；审阅计划后才添加 `--apply`。说明 `--max-bytes` 可按个人磁盘预算设定，非完成任务引用的媒体受保护，本地源文件不受清理影响。此处是可调整的运维建议，不代表程序自动清理或强制 30 天保留期。
- **验证范围：** 命令选项与保护规则对照 `references/CLI_REFERENCE.md` 和现有实现静态核对；文档链接、示例 JSON、空白检查与 `git diff --check` 通过。本轮未运行测试。

### DOC-06：CHANGELOG 对旧失败任务重试行为描述相反（P2，已修复）

- **证据：** `CHANGELOG.md` 曾称没有配置快照的旧失败任务会默认用当前设置重试；当前 CLI 文档、AUD-30/AUD-16 实现和 `retry_failed()` 证据均规定这类任务默认跳过，只有用户传 `--use-current-defaults` 才接受并持久化当前设置。
- **影响：** 用户可能以为一次普通 `retry-failed` 会重新处理旧任务，或没有意识到当前处理配置会替代历史配置，导致遗漏或意外的重试行为。
- **对策与结果：** CHANGELOG 现准确说明：旧任务默认跳过，显式 `--use-current-defaults` 才会按当前配置重试并保存新快照；新任务自动恢复已保存设置。更新后的说明与 CLI reference、README 中英文及审核条目一致。
- **验证范围：** 对照 CLI reference 和现有实现/审核证据做静态核对；未改动程序代码，未运行测试。

### AUD-58：浏览器捕获可能绕开请求 allowlist 访问本机网络（P2，已整改，真实浏览器验收待完成）

- **修复前证据：** capture.py 只为当前 page 注册 page.route("**/*", guard_request)；持久化上下文没有配置 service_workers="block"，也没有安装 context 级或 WebSocket 路由。代理仅监听 127.0.0.1、只处理 HTTPS CONNECT，并在代理侧拒绝非公网解析结果。
- **边界依据：** [Playwright Page 文档](https://playwright.dev/python/docs/api/class-page)明确说明页面 route 不处理 Service Worker 接管的请求，也不处理 popup 页面首个请求；[BrowserContext 文档](https://playwright.dev/python/docs/api/class-browsercontext)提供可在创建页面前注册的 context route 与 WebSocket route。[Chromium 代理文档](https://github.com/chromium/chromium/blob/main/net/docs/proxy.md#implicit-bypass-rules)说明手动代理默认隐式绕过 localhost、127.0.0.0/8、169.254.0.0/16 和 IPv6 link-local，流量会直连。
- **触发条件与影响：** 页面脚本触发 popup 首请求、Service Worker 请求或 WebSocket 连接到本机/链路本地地址，且对应服务在监听时，部分请求可能既不进入 page route，也不经过受限 CONNECT 代理。可能造成服务探测或触发本机服务操作；读取响应能力取决于浏览器策略与目标服务。
- **整改：** 持久化上下文设置 `service_workers="block"`；浏览器页创建前安装 context 级 HTTPS/主机/DNS 路由；WebSocket 经独立 route，仅允许资源域名 allowlist 中解析到公网地址的 `wss`；Chromium 代理添加 `bypass="<-loopback>"`，撤销 localhost/链路本地隐式直连。
- **验证：** Fake Playwright 回归覆盖上下文路由先于页面创建、Service Worker 阻断、代理 bypass 参数，以及 WebSocket scheme/域名/DNS allowlist；capture/proxy 定向测试 **21 passed**，相关 Ruff 通过。本机未安装 Playwright Python 包，未运行 Chromium；popup、预注册 Service Worker、真实 loopback/链路本地和抖音 WebSocket 行为仍需集成验收。阻断 Service Worker 若影响平台功能，需以真实站点测试确认兼容性。

### AUD-59：远端失败任务在重试 URL 解析失败后永久停在 pending（P2，可靠性，已整改）

- **证据：** cli.py::_run_retry() 先调用 TaskStore.retry_failed() 将远端任务从 failed 改为 pending；随后 pipeline.py::run_urls() 在创建/认领任务前解析 URL。解析异常只产生 ItemResult，不更新数据库。此路径不会进入 resolving claim，recover_interrupted() 也不会处理这个无 claim 的 pending 行；后续 retry-failed 只选 failed 状态，因此任务不再出现在可重试列表。
- **触发条件与影响：** 重试时短链服务、DNS 或网络解析临时失败。CLI 报告失败，但任务行保留 pending；用户再次运行 retry-failed 时看不到它，status 会显示一个无法继续的待处理项。
- **整改：** retry 的 URL 解析失败后，按任务 ID、状态和 claim generation 条件恢复未认领的任务为 failed，并保存可重试错误；worker 的所有状态写入都要求 claim generation，避免覆盖并发认领。
- **验证：** task/CLI/pipeline 回归覆盖 URL 解析失败恢复和并发认领；重试相关定向测试组 **110 passed, 4 skipped**，Ruff 通过。

### AUD-60：远端失败重试未直接从任务记录的媒体缓存恢复（P2，可用性，已整改）

- **证据：** 下载成功后若 ASR、输出写入或其他后续阶段失败，fail_task() 保留 media_path；retry_failed() 却将远端任务统一重置为 pending。pipeline 在 pending 状态下先重新打开浏览器获取媒体候选，之后 downloader 才按 video ID 和媒体类型搜索可复用缓存。因此，下载器可能免于再次传输媒体，但重试没有先检查任务行已经绑定的 media_path。
- **触发条件与影响：** 上次下载的媒体仍有效，但重试时视频页、浏览器捕获或 CDN 候选发现失败；pipeline 在利用任务行记录的本地文件前就失败。该问题增加远端依赖，不代表每次都会重新下载媒体字节。
- **整改：** claimed retry 现在验证任务记录的 `media_path`、身份与可解码性；在重新确认任务快照后，有效缓存直接恢复到 `downloaded`，无效缓存才继续捕获/下载。
- **验证：** pipeline 回归覆盖有效任务缓存的直接恢复和缓存失效后的安全回退；重试相关定向测试组 **110 passed, 4 skipped**，Ruff 通过。

### AUD-61：并发重试本地失败任务时竞争进程误报失败（P2，用户体验/可靠性，已整改）

- **证据：** 本地 retry 记录刻意保持 failed，直到原文件校验成功。两个 CLI 可先后同时读取同一 failed 候选；第一个 prepare_local_retry() 将任务转为 downloaded，另一个随后因状态不再为 failed 而抛出异常。pipeline 返回失败结果，没有重新读取任务状态区分“另一个进程已完成/正在处理”。
- **影响：** 同一任务被两个终端并发 retry 时，数据库只允许一个胜者，但另一个终端会报告处理失败；胜者可能已经成功完成，造成误导和重复排障。
- **整改：** 本地重试通过状态与 generation 条件原子认领；竞争进程遇到状态变化后重读任务，若其他进程已推进/完成则返回相应 skipped/locked 结果，不报告为任务处理失败。
- **验证：** 并发本地 retry 和状态变化回归通过；重试相关定向测试组 **110 passed, 4 skipped**，Ruff 通过。

### AUD-62：TaskStore worker 写入 API 可省略 claim generation（P2，任务隔离，已整改）

- **证据：** tasks.py::_require_claim_owner() 对带有 worker_id 但不传 claim_generation 的调用，只核对当前 claimed_by。如果旧 worker 与恢复后新 worker 复用同一 ID，旧的 transition()/fail_task() 调用在新 claim 仍归该 ID 时可以通过 owner 校验。pipeline 自身传 generation，因此目前限定于直接复用 TaskStore 的调用方。
- **影响：** AUD-54 的 generation fencing 对该 API 路径不是强制约束；同 ID worker 重用时，省略 generation 的旧调用可能改变新尝试的状态。
- **整改：** 所有携带 worker ID 的状态写入现在必须提供 claim generation；无 generation 或过期 generation 会失败。管理路径保留为不携带 worker ID 的独立调用。
- **验证：** 回归覆盖省略 generation、旧 generation 及同 ID 重用；重试相关定向测试组 **110 passed, 4 skipped**，Ruff 通过。

### AUD-63：Python 3.12 Windows 全套测试存在时间戳敏感失败（P2，CI 稳定性，已整改）

- **修复前证据：** Python 3.12.13 离线全套曾两次出现不同的时间戳敏感失败：缓存竞态 fixture 未保证文件已过期；媒体身份断言在校验结束后另行读取路径元数据，遇到 Windows ctime 更新。
- **整改：** 缓存 fixture 显式回拨 mtime，媒体身份 fixture 从 fake decoder 持有的同一文件句柄读取身份。
- **验证：** Python 3.11.15 与 3.12.13 全套离线套件各 **356 passed, 20 skipped**；两个受影响用例在 Python 3.12 环境各重复 5 次通过。跳过项均为 POSIX 专属检查或本机 symlink 能力限制。

### DOC-07：Skill 的逐字稿正文隐私规则互相冲突（P2，已整改）

- **修复前证据：** SKILL.md 第 11 行禁止把正文复制/摘要到对话或交给 LLM；第 56 行却允许用户单独要求 review/quote 时读取 Markdown。实施计划及 README 约定正文不进入 Agent 上下文。特别是“quote”请求究竟允许把正文读入上下文再引用，Skill 没有明确说明。
- **影响：** Agent 可能因文档解释不同而泄露用户逐字稿，或拒绝一个本来允许的本地操作。
- **整改与验证：** `SKILL.md` 已明确全文不得进入 Agent 上下文，包括用户提出审阅或引用请求时；指引用户在本地 Markdown 文件中查看。Skill 标准 validator 通过，文案与实施计划/README 一致。

### DOC-08：Skill 首次 doctor 命令可能隐式联网安装基础环境（P2，安装知情同意，已整改）

- **修复前证据：** SKILL.md 首步要求直接执行 uv run --project ... --locked ... doctor，但未先说明基础安装。项目目录下 uv run 会在命令前创建并同步环境；[uv 官方项目运行文档](https://docs.astral.sh/uv/concepts/projects/run/)与[CLI 说明](https://docs.astral.sh/uv/reference/cli/)说明 uv run 会保持项目环境同步，并可用 --no-sync 禁止同步。首次执行可能创建 .venv、安装构建/项目依赖并访问配置的软件源；Skill 目前只在后续步骤询问 ASR/模型和 Playwright/Chromium 设置。
- **影响：** Agent 首次诊断就可能修改本地环境或联网取包，用户尚未看到基础安装的副作用说明。
- **整改与验证：** `SKILL.md` 首次使用前现要求说明 `uv sync --locked` 会创建/更新 Skill `.venv` 并可能下载轻量依赖，先取得用户同意；初始化后所有 CLI 调用都使用 `uv run --locked --no-sync`。中英文 README 同步说明基础安装的网络和文件写入行为；Skill 标准 validator 通过。

### ENG-01：CI 没有验证 Skill 子目录的仓库外干净安装（P3，已整改，远端矩阵待执行）

- **修复前证据：** 本地验收曾将 skills/douyin-transcript 复制到仓库外，排除 .venv 和缓存后做 locked no-dev sync 与 CLI 冒烟；GitHub Actions 当时只验证校验器、锁文件、敏感文件扫描、lint 和 tests，没有这项子目录独立安装检查。
- **影响：** 日后新增仓库外导入/资源依赖时，本地人工验收可能通过，而发布的 Skill 子目录不再自包含。
- **整改与验证：** 新增 `scripts/check_clean_skill_install.py`，复制 Skill 子目录时排除 `.venv` 与缓存，在用户私有目录下执行 locked no-dev sync，确认导入来自副本、CLI `--version` 和 direct-URL dry-run 成功，且不创建运行时数据/输出目录；GitHub Actions 的六平台/版本矩阵已加入此步骤。本机 Windows Python 3.11 使用 `UV_OFFLINE=1` 运行脚本通过。远端矩阵尚未运行。

### DOC-09：部分 Skill 入口仍允许 `uv run` 隐式同步（P2，已整改）

- **证据：** DOC-08 修复后，`SKILL.md` 和 `INSTALL.md` 已要求初始化后用 `--no-sync`，但 `scripts/run.cmd`、`scripts/run.sh`、`references/CLI_REFERENCE.md` 与 README 中仍有省略参数的锁定 `uv run` 示例。用户经 wrapper 或参考命令调用时，uv 仍可自动同步环境。
- **影响：** wrapper/复制的命令可能在没有新的环境变更提示时写入 `.venv` 或访问包索引，DOC-08 的知情同意边界未覆盖所有入口。
- **整改：** Windows 与 Unix wrapper、CLI reference、中英文 README、验收/发布/项目计划中的有效开发命令现都包含 `--no-sync`；显式初始化仍通过 `uv sync --locked` 完成。
- **验证：** 新增 `tests/unit/test_skill_install.py`，扫描 Skill、安装文档、CLI reference、中英文 README 和两个 wrapper 的锁定 `uv run` 命令；本次定向复跑 **8 passed**，当时 Python 3.11.15 与 3.12.13 全套均为 **356 passed, 20 skipped**。

### ENG-02：干净安装脚本继承环境变量后可能写入调用者的虚拟环境（P2，已整改）

- **证据：** `scripts/check_clean_skill_install.py` 复制整个进程环境后运行 `uv sync --project <copied-skill>`。若调用者设置 `UV_PROJECT_ENVIRONMENT`，uv 会将安装目标重定向到该变量所指的路径，干净副本检查可能改写外部环境，也不再验证副本内的独立安装。
- **整改：** smoke 子进程现显式设置 `UV_PROJECT_ENVIRONMENT` 为复制 Skill 下的 `.venv`，保留 `UV_OFFLINE` 等调用环境选项，其余应用数据目录也留在临时副本根下。
- **验证：** 单元回归预设调用者的外部环境变量及带哨兵文件的目录，确认子进程目标在副本内且调用者环境/哨兵未改变；本次定向测试 **8 passed**。另用外部路径环境变量运行 `UV_OFFLINE=1 python scripts/check_clean_skill_install.py`，冒烟通过且外部路径未被创建。当时 Python 3.11.15 与 3.12.13 全套均为 **356 passed, 20 skipped**。

### DOC-10：CI job 名称误称全流程离线（P3，已修正）

- **证据：** 原名为 `offline-checks` 的 job 在 clean-copy 检查和开发依赖安装阶段执行 `uv sync`，冷 runner 可能从包索引下载依赖；只有 Ruff 和 pytest 步骤显式设置 `UV_OFFLINE=1`。模型与 Playwright 的离线环境变量也不等于整个 job 无网络。
- **影响：** 运维人员可能错误地认为 CI 可在无包索引访问的环境完成，或无法解释冷缓存 runner 的网络需求。
- **对策：** job ID 已改为 `ci-checks`；验收与发布材料明确说明依赖安装阶段可访问包索引，lint/test 进程离线。CI 的当前发行目标是 Skill 仓库目录，不要求构建 wheel/sdist；如未来增加 Python 包发布，再添加构建产物和隔离安装门禁。
- **验证：** 静态复核 workflow 步骤和环境变量；本机 Windows lint 与双 Python 全套离线测试通过。没有远端 workflow 运行记录。

### DOC-11：安装指南未说明 uv 验证基线（P3，已修正）

- **证据：** README 与 INSTALL 只要求安装 `uv`，而 CI 固定 `uv 0.12.7`，项目没有记录更早版本兼容性。
- **对策：** 中英文 README、INSTALL 和 SKILL metadata/instructions 说明当前验证基线为 `uv 0.12.7`，旧版本尚未验证；未将猜测的旧版兼容范围写成支持承诺。
- **验证：** 当前 CI workflow pin 和本机 `uv --version` 均为 `0.12.7`；无需修改依赖锁文件。

### 2026-10-09 追加审核结论

- 本次先确认 AUD-64 至 AUD-66 三项源码问题，再完成本地整改和回归。修改涉及文件命名、setup 安装次序与磁盘复查、Markdown frontmatter 限额及任务关联读取。
- **AUD-64（P2，接口安全边界，已整改）：** [naming.py](../skills/douyin-transcript/src/douyin_transcript/naming.py) 现在以同一组件清理逻辑处理标题和 fallback，包含 Windows 非法字符、控制字符、保留设备名及截断后的再次校验。恶意 `video_id="../escape"` 不再生成目录外候选。[test_naming.py](../tests/unit/test_naming.py) 覆盖分隔符、父目录、盘符、根路径和保留名；[test_markdown.py](../tests/unit/test_markdown.py) 验证实际 writer 仍在输出目录内。远端主链路 ID 约束仍提供额外限制。
- **AUD-65（P2，可用性，已部分整改）：** [cli.py](../skills/douyin-transcript/src/douyin_transcript/cli.py) 现在先安装 uv 依赖和请求的 Chromium，再在模型下载前重新检查模型卷至少 2 GiB；空间不足或查询失败时明确说明依赖已安装、模型未下载。setup 也说明预检只是瞬时快照。回归模拟 `uv sync` 后余量降至 1 GiB，确认不调用模型下载器。uv/Chromium 的实际占用依平台和版本变化，仍未建立精确容量保证；真实安装获授权后需记录实际空间消耗。
- **AUD-66（P2，任务完成状态/输出一致性，已整改）：** [markdown.py](../skills/douyin-transcript/src/douyin_transcript/markdown.py) 与 [tasks.py](../skills/douyin-transcript/src/douyin_transcript/tasks.py) 共用 4 Mi 字符 frontmatter 上限；解析器逐行读取至结束分隔符且受同一上限约束，serializer 在生成超限 frontmatter 时先拒绝。pipeline 预先渲染输出，因此超限不会留下已发布 Markdown。回归使用含 20,000 个控制字符的合法 `CorrectionRule.note` 生成实际 archive 元数据，确认超 128 Ki 旧窗口的输出可通过任务绑定；超共享上限的 writer 回归确认无 Markdown 文件被发布。
- AUD-64–66 阶段快照为 Windows Python 3.11.15/3.12.13 各 **366 passed, 20 skipped**；本次续审新增修复后的最新测试结果见下方 2026-10-09 续审记录。
- 项目仍未达到真实产品与发布门槛：ASR、真实抖音/Chromium、人工听审、性能记录、目标 Agent、Linux/macOS、远端 CI、许可证选择和发布授权尚未完成；SEC-15/AUD-52 边界仍有平台/多账户验收待做，整体保持 **NOT READY**。

### 2026-10-09 文档一致性续审

- **DOC-12（P2，验证状态陈旧且相互矛盾，已修复）：** 修复前中文和英文 README 将当时当前 Windows Python 3.11/3.12 全套离线结果写为 **356 passed, 20 skipped**，而工作树实测为 **366 passed, 20 skipped**；发布报告第 44 行也把旧的 356 结果称为“latest”，与第 10 行冲突。此类差异会使用户和发布审阅者无法判断验证基线。DOC-12 修复后，两份 README、清单、审核报告及发布报告当时均指向 **376 passed, 20 skipped**，旧数字明确标注为历史快照；后续 382/20 续审结果见第 9 节和 DOC-15。
- **DOC-13（P3，跨平台 CI 发布门重复，已修复）：** 发布清单原有两条独立未勾选项分别要求运行 Windows/macOS/Linux 矩阵和矩阵通过，属于同一门槛的重复记录，可能导致执行与通过状态被分别维护。已合并为一项“运行并通过”并要求解释跳过项。
- **DOC-14（P3，本地多 Python 验证可能使用错误解释器，已修复文档）：** 在已由 Python 3.11 创建的 `.venv` 上运行 `uv run --python 3.12 --no-sync ...` 时，uv 发出环境不兼容警告但仍使用 Python 3.11.15；如果只记录命令参数，可能把 3.11 结果误记成 3.12。`docs/ACCEPTANCE.md` 现要求切换版本前先 `uv sync --python VERSION`，再运行 `python --version` 验证实际解释器，最后执行 pytest。CI 各矩阵 job 会独立创建/同步环境，本次远端矩阵仍未运行。
- **文档复核（DOC-12 修复当时）：** 状态文档当时均指向 Windows Python 3.11.15 与 3.12.13 各 **376 passed, 20 skipped**；多 Python 本地测试要求先同步环境并核实解释器；旧测试数字只保留在明确标为历史快照的记录中；跨平台 CI 仅保留一个发布门。后续当前结果更新为 382/20，见第 9 节。整体仍为 **NOT READY**。
- **复核范围与结果：** 对照 README 中英文版本、发布报告、发布清单和当前审核报告，扫描了当前验证计数及 TODO/FIXME 标记；除上述文档问题外，本次没有确认新的源码缺陷。代码层结论仍受既有报告所列边界约束：真实 ASR/抖音/浏览器、POSIX 与 macOS/Linux、目标 Agent 和远端 CI 尚未完成，因此“未发现”仅指本轮本地源码与文档复核，不能视为全平台无缺陷或发布批准。

### 2026-10-09 源码续审与整改

- **AUD-67（P2，默认 worker 时限失效，已整改）：** `SupervisedProcessingWorker._request()` 在未传入 deadline 时，每次轮询都重设为完整的默认 7,200 秒，导致 stale-task recovery 调用 `_validate_media()` 时若解码卡住，处理子进程可无限等待。现于请求入口生成一次单调时钟绝对 deadline，锁等待、响应轮询及结束检查都复用该值；新增短时默认时限回归，验证卡住的子进程按 `PROCESSING_TIMEOUT` 终止。
- **AUD-68（P2，合法 HTTPS URL 形式误拒绝，已整改）：** 原始 scheme 前缀检查只接受小写 `https://`；同时直接视频和短链跳转判断未去掉允许主机名尾部的点，导致大写 scheme 的短链被网络校验拒绝，以及 `www.douyin.com.` 视频地址被错当短链。网络层现在按解析后的 HTTPS scheme 判断，视频主机分支统一小写并去尾点；回归覆盖大写 scheme、直接视频尾点和短链跳转目标尾点。
- **SEC-29（P2，Markdown 扩展名导致输出根目录逃逸，已整改）：** 公共 writer 接受任意 `extension` 并拼入文件名；如传入 `/../../escape.md` 且标题同名目录存在，候选路径可指向输出根外。`sanitize_filename()` 现在拒绝非简单后缀格式，允许 `.md`、`.timestamps.md` 等普通扩展名；新增候选路径和实际 writer 回归，确认路径式扩展名被拒绝且根外文件不产生。
- **验证（AUD-69 之前的阶段快照）：** 四组定向测试 **57 passed**；Windows Python 3.11.15 与 3.12.13 全套离线测试各 **375 passed, 20 skipped**；该阶段的 Ruff、锁文件一致性、敏感文件扫描、Agent Skills validator 与仓库外离线干净安装冒烟均通过。当前 376/20 结果及 AUD-69 新增回归见下一节。平台跳过仍需 Linux/macOS 及支持 symlink 的 Windows/文件系统验证。真实媒体、浏览器与远端 CI 尚未执行。
- **范围边界：** 本次源代码复核仅为当前指定模块的只读独立审查，未确认其他新增问题；Codex Security Diff Scan 的 28 项完整结果绑定此前冻结快照，不覆盖本次新代码。项目整体仍 **NOT READY**。

### 2026-10-09 AUD-69 文本归一续审

- **AUD-69（P2，英文分段间空格丢失，已整改）：** `normalize_segments()` 对每段清理时使用 `.strip()`，只记住下一段的前导空白，没有保留上一段末尾空格。输入 `"Hello, "` 与 `"world."` 因而可能拼成 `Hello,world.`，降低字幕可读性并改变单词边界。现记录原始段尾空白，并在 ASCII 词语边界恢复一个空格；CJK 边界仍不凭空添加空格。新增归一回归覆盖英文尾空格及中日韩无空格文本。
- **验证：** 五个定向测试模块 **62 passed**；Windows Python 3.11.15 与 3.12.13 全套离线测试各 **376 passed, 20 skipped**。20 项平台跳过仍需 Linux/macOS 及支持 symlink 的 Windows/文件系统验证。其余静态检查和离线干净安装已在本次续审后重跑，结果见发布报告更新。
- **范围边界：** 此项修复提升分段文本的边界保真，不证明 ASR 内容准确性；真实音频听审、真实浏览器/抖音、跨平台远端 CI、目标 Agent 和发布授权仍待完成，项目整体仍 **NOT READY**。

### 2026-10-09 第三方许可发行路径复核

- **REL-01（P6，第三方二进制许可材料未闭合，待发布前完成）：** 当前锁定 PyAV 15.1.0 的上游源码许可为 BSD-3-Clause，但 PyAV wheel 链接 FFmpeg。续审在 Windows wheel 中观察到 `libx264`、`libx265` DLL，且 PyAV 报告对应编码器可用；这是需要按 GPL 构建路径审查的强烈信号，但尚未提取完整 build configuration，也未确认潜在的商业许可例外或其他组件的 notice/源码材料。Windows wheel 未纳入 Git 或本项目发行，macOS/Linux wheel 未检查；因此尚不能确定所有目标二进制的分发义务。没有据此认定工作树违法。Playwright 1.63.0 的 Python 包声明 Apache-2.0，固定 Medium 模型仓库页声明 MIT；浏览器与模型由运行时另行下载，Git 可见树未包含权重或浏览器/依赖二进制。
- **对策与进度：** 新增 `docs/THIRD_PARTY_LICENSE_REVIEW.md` 记录锁定版本、上游来源、当前发行边界和未决事项；验收清单已将已完成的初步来源核对与待完成的 wheel/完整 SPDX 审核分开。任何二进制分发前，应按 Windows/macOS/Linux 实际 wheel 收集 FFmpeg 版本、编译选项、许可证与源码/notice，并生成全锁定依赖 SPDX SBOM。项目自身 LICENSE 仍由仓库所有者选择。
- **范围限制：** 本记录是技术许可来源核对，不构成法律意见；当前 Skill 以源代码目录分发，不随仓库提交 PyAV wheel、模型或浏览器。P6 仍 **NOT READY**。

### 2026-10-09 后续安全与文档复核

- **SEC-30（P3，远端标题中的双向控制字符可伪装输出标题，发现时待整改）：** 抖音页面标题经 `capture.py` 清理后进入 pipeline，再用于输出文件名、Markdown frontmatter/标题和 CLI 摘要。发现时的清理只删除 C0/DEL；文件名清理只替换 Unicode `Cc`/`Cs`，未处理双向控制字符。恶意发布者可设置含有此类字符的标题，使支持双向文本的终端、文件管理器或 Markdown 查看器重排显示，造成文件名/内容误认。影响是本地显示欺骗；未发现代码执行、任意路径写入或跨用户权限提升。
  - **对策：** 在不可信标题进入 pipeline 前统一移除 Unicode `Bidi_Control` 字符（至少覆盖 U+061C、U+200E–U+200F、U+202A–U+202E、U+2066–U+2069）；`naming.clean_component()` 和 Markdown 输出边界再做防御性处理，并让任务标题、文件名、frontmatter/heading 使用同一规范化值。加入覆盖文件名、Markdown、JSON/CLI 摘要的回归。
  - **证据与限制：** 代码数据流为 `capture.py:336-342` → `pipeline.py:470-476` → `naming.py:38-47` / `markdown.py:30-43,103-112`。具体视觉效果依赖 viewer，尚未逐一实测；严重度评估为低。
- **DOC-15（P3，审核报告首页测试数字过时，已修正）：** 首页曾把 AUD-64–66 阶段的 366/20 写成未标注的当前结论，和当时报告后文的 376/20 当前结果冲突。现已标明旧结果为历史快照；续审后的当前结果为 Python 3.11.15 与 3.12.13 均 382/20。
- **DOC-16（P3，输出目录环境变量未见于用户指南，发现时待补文档）：** `config.py` 接受 `DOUYIN_TRANSCRIPT_OUTPUT` 并将其作为输出目录覆盖值；发现时 README、CLI Reference 和 INSTALL 未说明该变量或优先级。调用者仅看用户指南可能无法解释环境变量为何覆盖配置文件。
  - **对策：** 在中文/英文 README、CLI Reference 和 INSTALL 中列出该变量，并写清优先级：`--output-dir` → `DOUYIN_TRANSCRIPT_OUTPUT` → `config.toml` 的 `paths.output_dir` → 默认目录。若不希望承诺环境变量接口，则移除该实现并保留明确的 CLI/config 行为。
- **SEC-31（P2，中危，HLS 子请求可能绕过下载网络边界，发现时待动态确认）：** 页面捕获会接受 `application/vnd.apple.mpegurl`，下载器先校验首个 HLS URL 并下载清单；发现时 `validate_media_file()` 将文件包装成 file-like 对象交给 `av.open()`，没有设置 `protocol_whitelist` 或限制 PyAV 的 `io_open`。如果锁定版本 FFmpeg 的 HLS demuxer 按清单中的绝对 URI 打开片段，它可能自行请求 loopback/内网 HTTP 地址，绕过下载器的主机、DNS pinning、重定向和累计字节数边界。默认 CLI 在受监管子进程中执行媒体校验，超时可终止该进程；当前证据不支持声称此路径绕过整体处理 deadline。FFmpeg 文档说明协议可通过 `protocol_whitelist` 限制，HLS 源码会处理清单引用资源；PyAV 文档说明 `io_open` 用于格式额外打开的文件对象。尚未在项目锁定的 PyAV 15.1.0 wheel 上动态确认该调用链，因此按条件风险记录。参考：[FFmpeg Protocols](https://ffmpeg.org/ffmpeg-protocols.html)、[FFmpeg HLS 源码](https://ffmpeg.org/doxygen/7.1/hls_8c_source.html)、[PyAV 15.1 `av.open`](https://pyav.basswood.io/docs/15.1/api/_globals.html)。
  - **对策：** 若不需要 HLS，拒绝 HLS 清单；否则在 PyAV `av.open()` 上设置严格协议白名单，并通过自定义 `io_open` 拒绝不经应用校验的网络/文件子请求。需要支持 HLS 时，将每个片段 URL、DNS 地址、跳转、总字节和总时间纳入与下载器相同的受限请求器。用本地 mock HTTP 服务提供含 loopback/private URL 的 HLS 清单，验证不会产生未授权请求，并验证正常授权 HLS 仍可用。
- **SEC-32（P3，敏感文件检查对部分文件静默跳过内容扫描，低危，发现时待整改）：** CI 会执行 `scripts/check_sensitive_files.py`，但发现时超过 2 MiB、含 NUL 或 UTF-8 解码失败的文件会被静默跳过内容模式扫描。若凭据放在路径规则未覆盖的这类文件中，当前 CI 检查不会报告未检查状态。该检查本来就不是通用 secret scanner。
  - **对策：** 对大文本改用分块扫描；对二进制/非 UTF-8 文件记录路径并要求显式分类或人工复核，不把“未检查”呈现为“通过”。保持已知敏感路径拦截，并在 CI 输出文件数、跳过数及跳过原因。
- **已知存储残余风险（AUD-11，非本轮新发现）：** 输出目录权限检查是提示性策略，写作不会因目录可被其他账户访问而阻止。当前工作区默认输出路径的祖先 ACL 已检查为不安全；隐私敏感的逐字稿应显式输出到权限检查为安全的用户目录。可另行考虑严格模式，在不安全时拒绝写出。
- **策略待确认（非已证实漏洞）：** 浏览器资源允许 `*.douyin.com`、`*.iesdouyin.com` 子域。网络边界复核未发现 SSRF 或 DNS rebinding 绕过；仍建议按真实页面需求盘点目标主机，缩小通配范围并为必要 CDN 单独加白。
- **DOC-17（P3，英文 CLI 文档漏列资源限制项，发现时待补文档）：** `README_EN.md` 引导读者到 `CLI_REFERENCE.md` 查可配置资源限制；发现时该参考未列出 `max_media_duration_seconds`、`max_output_segments`、`max_output_characters` 与 `[limits]` 配置名。中文 README 已列出对应设置，英文读者较难找到。
  - **对策：** 在英文 CLI Reference 补齐三个 CLI 选项和 `[limits]` 示例，或把英文 README 链接改到已有完整说明处；确认中英文默认值一致。
- **安全扫描记录：** Codex Security Diff Scan 已完成（Scan ID `fd600a5b-b3a7-46ba-a403-bd01542eb386`，快照 digest `e578a87e4325acc27ab997fd18da7deab881f34750364ae9dee39f71e825d640`）：29/29 个代码/配置审查项完成，记录 3 项低/中危候选。扫描器提示工作树在扫描期间发生变化；这是因为本报告追加内容晚于冻结快照，扫描结论绑定上述快照，不涵盖本段新增报告文本。
- **该次扫描边界：** 对照冻结差异审查清单的 29 个源码/配置项已逐项静态复核，并由独立审计复核；工作树差异共登记 83 个变更文件，其他文档/测试文件不属于这 29 项代码审查清单。未访问抖音、未运行真实 ASR/Chromium、未检查 Linux/macOS ACL 或远端 CI；HLS 子请求行为仍需在锁定的 PyAV/FFmpeg 构建上动态确认。该次扫描时的 Python 3.11.15/3.12.13 结果各 376 passed、20 skipped；本轮后续测试结果见下方整改跟进。此报告不代表发布批准，项目仍为 **NOT READY**。

### 2026-10-09 发现项整改跟进

- **SEC-30，本地整改完成：** 新增 `text_safety.py`，在远端标题清洗、任务标题写入/读取、文件名、Markdown 标题、CLI 文本和 JSON 摘要边界移除终端与 bidi 控制符；Markdown 正文将 bidi 控制符显示为 `<U+XXXX>`，并保留 ZWNJ/ZWJ 等普通文字格式符。补充 capture、任务库、文件名、Markdown、summary JSON 与 `status --json` 回归用例。真实终端/查看器渲染仍未逐一验证。
- **SEC-31，源码 mitigation 已实现（本阶段记录时动态验收仍开放）：** PyAV `av.open()` 现在传入拒绝所有二次资源打开的 `io_open` 回调，下载后的 HLS 清单如果需要分段请求会失败；CLI Reference 明确该限制。添加回归用例验证回调拒绝 loopback URL。Skill 项目 venv 未安装 PyAV；当时尚未用系统 Hermes Python 的 PyAV 18.0.0 做补充动态检查，因此该阶段只通过 mock 回归验证回调被传入。锁定的 PyAV 15.1.0 wheel 后续动态验证已通过，见第 9 节；Linux/macOS wheel 和更多媒体格式仍未验收。处理子进程的总 deadline 仍有效。
- **SEC-32，仓库内整改完成：** scanner 不再静默忽略 symlink、非普通文件、超 2 MiB 文件、NUL 文件或非 UTF-8 文件，遇到这些情况会报告具体路径并让 CI 失败关闭。新加覆盖大文件、二进制和编码失败的回归用例。当前 `python scripts/check_sensitive_files.py` 在 Git 可见工作树扫描通过；该脚本依然不是通用 secret scanner，也不检查完整 Git 历史。
- **DOC-16/17，本地文档整改完成：** 中英文 README、CLI Reference 和 INSTALL 已说明 `DOUYIN_TRANSCRIPT_OUTPUT` 与输出目录优先级；英文 CLI Reference 已列明三项资源限制、默认值、硬上限和 `[limits]` 配置键。
- **计划结构差异已补：** 新增 `examples/urls.example.txt`、`examples/sample_output.md`、`examples/sample_summary.json`，均为明确的虚构/占位示例，并在中文 README 加链接。
- **本轮验证结果与限制：** Python 3.11.15 项目 venv 全套 pytest 为 **382 passed, 20 skipped**，全仓 Ruff 通过；敏感文件扫描、示例 JSON 解析、Python 编译、`git diff --check` 和本地安全 smoke checks 通过。该轮的 Skill venv 没有 PyAV，因此只记录了 mock 回归结果；后续 PyAV 18.0.0 动态补充验证见第 9 节，仍不替代锁定 15.1.0。Python 3.12.13 的全套复跑结果见第 9 节。整体仍为 **NOT READY**，因 P1/P2/P4/P5/P6 外部验收门槛尚未完成。

### 2026-10-09 当前工作树完整差异复审

- **安全审查结果：** Codex Security Diff Scan `484bb340-323c-4bec-a20a-368b2fcd077d` 审查冻结快照 `codex-security-snapshot/v1:sha256:c09e0d0e5a42fbd769931e234c5317c45f01d10e2d7e2633f1398663bc8c2fab`。工作树登记 87 个变更文件，30/30 个源码/配置审查项完成；未发现新的可报告安全候选。URL 重定向、浏览器代理出口、媒体下载、标题显示、任务存储、子进程与 setup 下载、敏感文件扫描均有源码控制和调用路径证据。
- **SEC-31 动态验证已在本机锁定版本通过：** 当前源码给 PyAV `av.open()` 传入拒绝所有二级资源打开的回调。Windows 临时环境安装锁定 PyAV 15.1.0 后，合成 HLS 清单的 loopback 分段触发 `io_open` 回调 1 次，mock 服务收到 0 次请求；合成 WAV 验证通过。结果与系统 PyAV 18.0.0 补测一致。Linux/macOS 构建及更多媒体格式尚未动态验收；HLS 分段输入按当前设计会被拒绝。
- **SEC-33（P3，C1 控制字符可能进入显示输出，已整改）：** 独立复审发现不可信标题清洗遗漏 Unicode C1 控制区 U+0080–U+009F。页面标题可能经 capture 进入任务/CLI 摘要和 Markdown frontmatter，Markdown 正文过滤也未移除 C1；U+009B 在部分终端可被解释为控制序列，具体效果依终端而异。没有证据表明其造成代码执行或权限提升。
  - **对策与验证：** 标题采集、通用显示文本及 Markdown 正文过滤现覆盖 C1；文件名清理此前已按 Unicode `Cc` 处理。新增 U+0085/U+009B 回归，Windows Python 3.11.15 与 3.12.13 全套各 **382 passed, 20 skipped**，两套 Ruff 通过。此项为低危显示边界问题，仍需其他终端/查看器的渲染实测。
- **DOC-18（P3，架构文档未准确描述路径配置，已修正文档）：** 原文笼统地说模型与全部用户数据都位于选定 data directory，没有说明 `config.toml` 先从命令行/环境/平台默认锚点读取，也没有说明模型可以从 `HF_HUB_CACHE`、`HF_HOME/hub` 或默认 Hugging Face cache 加载。现已在 `docs/ARCHITECTURE.md` 说明配置锚点、有效 data directory、模型缓存查找顺序和输出目录优先级。
- **DOC-19（P3，发布清单描述的敏感文件检查行为过时，已修正文档）：** 清单曾称大于 2 MiB、二进制或非 UTF-8 文件会被跳过；当前扫描器遇到这些文件会报错并使检查失败。清单已改为记录 fail-closed 行为，同时说明 Git 历史与通用凭据扫描仍需单独审阅。
- **DOC-20（P3，输出路径的隐私说明与产品验收目标含义不清，已修正文档）：** `SECURITY.md` 原文要求分享诊断前一概 redacting 私人路径，但项目验收要求 Agent 把生成的 Markdown 路径返回给发起请求的操作者（`docs/PROJECT_IMPLEMENTATION_PLAN.md` 的单链接场景）。两种说法可能让宿主误以为连请求者也不能收到结果路径，或忽略路径只应发给请求者的隐私边界。现已在 `SECURITY.md`、`docs/ARCHITECTURE.md` 和 Skill 中统一为：仅向请求转写的操作者返回所选路径；向其他接收方转发诊断前移除私人路径及个人信息。README 的 JSON 示例和行为说明与此一致；没有改变 CLI 输出或路径权限策略。
- **DOC-21（P2，发布报告的“最新”安全状态滞后，已修正）：** `docs/RELEASE_REPORT.md` 将较早的 Diff Scan `484bb340-323c-4bec-a20a-368b2fcd077d` 称为最新，并称锁定 PyAV 15.1.0 的动态验证尚未完成；审核报告第 9/10 节已有更新扫描 `fd9a73df-3590-47b3-aada-ab36bde2fd61` 及锁定 wheel 的 HLS/WAV 动态结果。实施计划的 SEC-15 单一未勾选项也把已完成的本地源码整改与尚未完成的平台验收混在一起。过时说法会让发布审阅者误判证据时序。现已更新发布报告，并将 SEC-15 拆成本地源码整改（完成）与跨平台/多账户验收（未完成）；远端 CI、POSIX、真实 ASR/浏览器与发布门槛仍未完成。
- **审查范围限制：** 这是一份静态差异审查，coverage 对 HLS 动态行为保持 partial；没有访问抖音、下载模型/浏览器组件、运行真实 ASR 或检查远端 CI。安全审查的 0 项候选不代表产品验收完成，P1/P2/P4/P5/P6 门槛、输出目录 advisory 风险、历史敏感文件审查和许可证/远端所有者决定仍按发布清单执行。上述文档更改发生在安全扫描冻结快照之后，不属于该扫描快照。

## 9. 2026-10-09 本机验收续审

- Windows Python 3.11.15 项目虚拟环境与 Python 3.12.13 独立临时环境重新运行全套离线 pytest，均为 **382 passed, 20 skipped**。跳过项是 POSIX 专属行为或当前文件系统不能创建 symlink 的用例。
- 当前检查点的 P0 CLI 冒烟：`python -m douyin_transcript --help` 退出码 0；`doctor --json` 退出码 1，`overall` 与两种能力均为 `setup_required`，符合尚未安装 Skill 运行依赖和模型的预期。
- GitHub Actions 中使用的 Ruff 路径 `scripts skills/douyin-transcript/src skills/douyin-transcript/scripts tests` 通过；`uv lock --project skills/douyin-transcript --check`、Git 可见敏感文件扫描和 `git diff --check` 均通过。工作树中统一应用项目 Ruff 配置的检查也已修复格式问题并通过。
- Python 3.12.13 使用锁定开发依赖在仓库外独立临时环境运行全套测试，结果 **382 passed, 20 skipped**；该环境通过 `UV_OFFLINE=1` 创建，未改动项目的 Python 3.11 虚拟环境。此前的 **376 passed, 20 skipped** 属于旧工作树快照。
- **SEC-31 动态检查：** 系统 Hermes Python 3.11.15 使用 PyAV 18.0.0 / FFmpeg libavformat 62.12.102 的补充结果是：合成 HLS loopback 分段触发拒绝回调 1 次、服务请求 0 次，1 秒 PCM WAV 验证通过。随后在仓库外临时环境安装锁定 PyAV 15.1.0 / FFmpeg libavformat 61.7.100 重做验收，得到相同结果：回调 1 次、服务请求 0 次、HLS 以 `MEDIA_DECODE_FAILED` 失败关闭，1 秒 PCM WAV 验证为 `wav`。临时环境与素材在仓库外创建。
- **SEC-33 C1 回归：** 标题采集、CLI 摘要、Markdown frontmatter/heading/body 的 U+0085、U+009B 回归通过；现有文件名清理使用 Unicode 类别 `Cc`，包含 C1。该修复发生在之前的正式安全扫描之后，后续差异扫描快照及其覆盖范围见单独审查记录。
- 截至当前 HEAD `154d9ef`（4 个可达本地提交）的只读历史扫描覆盖 **101 个唯一路径/blob 对**；101 个均为 2 MiB 内 UTF-8 文本，未命中仓库敏感路径规则或高置信度凭据模式，也未命中工作区根目录/用户目录标记。当前 Git 可见工作树的敏感文件检查也通过。该扫描不是通用 secret scanner；发布前仍须复核最终提交和历史。
- 本轮续审修改了文档中的 Python 3.12 当前测试结果和安全验收状态，并修复 SEC-33 的 C1 控制字符清理及回归测试；该源码差异包含在后续 Codex Security Diff Scan `fd9a73df-3590-47b3-aada-ab36bde2fd61` 的冻结快照中。锁定 PyAV/HLS 动态验收已在 Windows 通过；真实 P1/P2/P4、Agent 宿主、跨平台远端 CI、许可证和仓库所有者决定仍未完成，项目保持 **NOT READY**。

## 10. 2026-10-09 C1 控制字符差异复审

- **正式扫描结论：** Codex Security Diff Scan `fd9a73df-3590-47b3-aada-ab36bde2fd61` 已完成。扫描冻结在 base/head `154d9ef1d8fd8a75b6a8870bb2d99dc602ceae62`，snapshot digest 为 `codex-security-snapshot/v1:sha256:310d9cb80df88511cea4e51cd1e9e7e4ea8a7e01d71f958eba88ab6465775dcf`。冻结差异中的 3 个源码审查项逐项完成；本次差异未发现新的可报告安全问题。SEC-33 是本次修改前已记录并正在修复的低危问题，不是修复差异引入的新问题。
- **快照边界：** 扫描工具提示扫描期间工作树发生变化，结果仍绑定上述冻结快照；本报告随后追加的文字不属于扫描输入。三个源码审查项及其代码状态按该快照记录。
- **复核证据：** `capture.py:400-408` 在页面标题、作者及发布时间进入任务/展示前剔除 C0、C1 和双向控制符；`text_safety.py:16-26` 为 CLI 与任务展示提供同类过滤；`markdown.py:20-58,97-112` 过滤 Markdown 正文控制字符，并清理 frontmatter/标题。新增测试用 U+0085、U+009B 覆盖采集标题、CLI 摘要及 Markdown frontmatter、标题和正文。此处结论是源码差异复核；不同终端和 Markdown 查看器的实际渲染仍未逐一测试。
- **仍待处理的问题及对策：**
  1. **真实 ASR / P1：** 当前诊断仍为 `setup_required`，尚无获授权的中文样本或真实识别结果。由用户提供至少 60 秒且有权处理的本地媒体，并批准安装锁定 ASR 依赖和固定模型；随后生成 Markdown、人工抽听、记录质量和资源数据。
  2. **真实抖音链路 / P2：** 尚未安装并运行 Playwright/Chromium，也没有三条授权链接的集成结果。用户提供可访问视频并授权后，手动登录执行可见浏览器验收；不绕过验证码、DRM 或访问控制。
  3. **质量与性能 / P4：** 真实逐字稿听审、长音频计时和重复内容检查待 P1 样本。验收至少三处文本，并记录耗时、漏转/幻觉/重复及 stdout/stderr 泄漏检查。
  4. **Agent 宿主 / P5：** Skill 标准校验和仓库外干净安装冒烟通过，但真实宿主调用未验收。确定目标宿主后，使用结构化参数完成一次端到端调用并检查正文未进入 Agent 上下文。
  5. **发布 / P6：** 远端 CI、仓库所有者/可见性、LICENSE 选择和推送授权未落实。由仓库所有者确定许可证和目标仓库；再运行 Windows/macOS/Linux CI、复核提交历史中的敏感材料，最后按发布清单审批。
  6. **本地输出隐私：** 输出目录权限诊断仍是 advisory；默认工作区输出路径祖先 ACL 不安全。逐字稿应写入权限检查为安全的用户目录；后续可考虑严格模式，在目标目录不安全时拒绝写出。
  7. **第三方许可证：** Windows 锁定 PyAV wheel 的临时检查发现 x264/x265 DLL 和可用编码器，需在任何二进制分发前核验实际 FFmpeg 构建配置、许可证文本和分发义务，并由所有者决定许可证策略；详见 `THIRD_PARTY_LICENSE_REVIEW.md`。
- **项目状态：** 本地 Python 3.11.15/3.12.13 全套测试各 382 passed、20 skipped；锁定 PyAV 15.1.0 的合成 HLS loopback 拒绝及 WAV 解码通过，详见第 9 节。静态差异扫描通过不等于产品验收完成；P1/P2/P4/P5/P6 与发布审查完成前，项目维持 **NOT READY**。

## 11. 2026-10-09 项目完成目标续审

- **当前运行状态：** 在当前 Windows 工作区重新执行锁定环境 `doctor --json`，结果仍为 `setup_required`；未安装依赖、下载模型或创建数据目录。报告显示固定 medium 模型、faster-whisper、PyAV、Playwright 和 Chromium 均未就绪；默认工作区输出目录的权限为 `unsafe`，原因是其 `D:\` 祖先向 Authenticated Users (`S-1-5-11`) 授予目录替换权限。隐私敏感的 P1 输出需明确指定并再次检查权限为 `ok` 的个人目录。
- **P1 预检补充：** 只读测得当前主机 CPU 为 Intel Core i5-12400、12 个逻辑处理器、已安装内存 31.7 GiB，已同步写入 `docs/P1_REPORT.md`。本次没有处理媒体，未测量模型加载、推理、峰值内存或逐字稿质量，因此 P1/P4 仍 **NOT VERIFIED**。
- **可用平台与远端：** 当前系统没有注册的 WSL Linux 发行版；本地 `git remote -v` 为空。因此本机无法补跑 POSIX 分支，远端矩阵 CI 和 GitHub 安装仍无执行目标。没有据此把未验收项标成通过。
- **状态文档一致性整改：** `docs/RELEASE_REPORT.md` 现将 Diff Scan `fd9a73df-3590-47b3-aada-ab36bde2fd61` 作为已记录的最新差异扫描，并说明锁定 PyAV 15.1.0 在 Windows 的 HLS loopback 拒绝/WAV 动态验收已通过；DOC-12 的 376/20 记录与早期 SEC-31 动态状态改为明确的历史阶段说明。实施计划将 SEC-15 本地源码整改与跨平台/多账户验收拆分记录，后者继续未完成。
- **当前工作树门禁复跑：** Windows Python 3.11.15 全套离线 pytest **382 passed, 20 skipped**。20 项跳过涉及 POSIX 权限/FIFO/dir-fd 语义，或本机文件系统不允许创建 symlink。GitHub Actions 使用的 Ruff 路径、`uv lock --check`、敏感文件扫描、固定 `skills-ref==0.1.1` Skill 校验及 `git diff --check` 均通过；未在本轮重跑 Python 3.12，全套 3.12.13 结果仍以第 9 节既有记录为准。
- **仍需用户/所有者输入的真实门槛：** P1/P4/AUD-10/38/SEC-23 需要授权媒体和 ASR 安装/固定模型下载同意；P2 需要三条获授权链接并由操作者在可见浏览器手动登录（如需要）；P5/SEC-14 需要指定目标 Agent 宿主；P6 需要所有者决定许可证、仓库归属/可见性以及是否创建远端或发布。输出目录默认策略是否从 advisory 改为拒绝 unsafe/unknown 仍是产品策略选择；本续审保留原实施计划指定的当前工作目录默认路径，不擅自改变其含义。
- **续审边界：** 本次重跑了 Windows Python 3.11.15 全套离线测试及静态发布前检查，补录硬件预检并修正文档状态；没有执行真实媒体、安装或联网流程，也没有新增源代码安全扫描。完整项目状态保持 **NOT READY**。
