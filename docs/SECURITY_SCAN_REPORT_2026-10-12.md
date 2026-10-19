# 2026-10-12 项目安全审核报告与整改对策

> **历史扫描快照（§254，已由后续扫描取代）：** 本文件下方记录的是此前扫描，不代表当前工作树。§258 Diff Scan 覆盖 116 个 work items、264 个变更文件，coverage partial，且早于 §260。当前最新快照见项目审核报告 §§261–262：扫描已封存，覆盖 116 个 worklist 项、265 个变化路径，记录两个静态问题，coverage 仍为 partial。不能将旧扫描的 0 findings 当作当前结论。Codex Security 草稿扫描 `76ea53f9-a902-414b-bf70-ed654262c616` 的摘要为 `codex-security-snapshot/v1:sha256:70fc254afcc34626e64d9f0a8c95e4ffe519d01668baf393248ef3d91b94adaf`，启动于 §§251–253 后续代码改动之前；当时停在 threat-model 阶段，256 个文件中 closed review rows 为 0，尚未完成 discovery/validation/attack-path/reporting。P2/P4/P5/P6 gates 仍开放，项目 **NOT READY FOR RELEASE**。

## 结论

Codex Security Diff Scan `02fce2a3-db34-4838-888c-1be56d1914b3` 已完成并封存。本轮在冻结工作树中确认 3 项低风险文件处理问题，均位于人工运行的 Windows 诊断脚本或离线维护工具；当前工作树已在扫描快照之后修复这 3 项。修复后完成了语法/格式静态检查，没有运行受影响脚本或测试套件，因此本报告不把它们称为动态复验通过。

扫描是部分覆盖：差异清单有 207 个文件，其中 90/90 条源代码/配置 worklist 审核项完成逐文件审查；剩余文档、测试夹具和生成文件未逐个进行源代码级审查。Windows service、WFP/Firewall、Chromium 隔离和生产网络出口均未在主机上安装、修改或动态验证。项目仍为 **NOT READY FOR RELEASE**。

## 扫描身份与范围

- 扫描 ID：`02fce2a3-db34-4838-888c-1be56d1914b3`
- 冻结 revision：`b166778ee5283591a1b799535b746ba198e38653`
- 快照摘要：`codex-security-snapshot/v1:sha256:a1955fc7b05089cdccc2973e99dc9c895f5262426ce1c3ea9aea4abfe3faa273`
- 结果：3 项低风险 finding；1 项旧网络 helper proof gap；1 项 CIDR 误报已排除。
- 覆盖：90/90 条源代码/配置审查项完成；207 个差异文件并非全部逐行检查。
- 运行时：静态源码审查。未安装 service，未运行诊断 harness，未修改 WFP/Firewall。

扫描期间工作树继续变化，安全工件保留的是上述冻结快照。下列源代码修复晚于该快照，必须在后续扫描中重新纳入。

## 发现与对策

| 编号 | 严重度 | 问题 | 修复与状态 |
|---|---|---|---|
| AUD-120 | 低 | 两个 Chromium 诊断脚本发现固定暂存/profile 目录已存在后，旧版 `finally` 仍无条件递归删除该目录。以高权限手动运行可能删除目录内既有数据。 | [`ChromiumAsUserTokenSmoke.ps1`](../native/windows/wfp-policy-plan/sandbox/ChromiumAsUserTokenSmoke.ps1) 与 [`UserSidChromiumSmoke.ps1`](../native/windows/wfp-policy-plan/sandbox/UserSidChromiumSmoke.ps1) 增加严格创建及所有权标记，只清理由本次调用创建的目录；AST 解析通过，脚本未运行。 |
| AUD-121 | 低 | ProcessSingleton 探针用 `CREATE_ALWAYS` 和 `DELETE_ON_CLOSE` 打开调用者选定 profile 中的 `lockfile`，可截断并删除既有文件。 | [`ProcessSingletonApiProbe.ps1`](../native/windows/wfp-policy-plan/sandbox/ProcessSingletonApiProbe.ps1) 改为排他 `CREATE_NEW`，现有文件拒绝打开；AST 解析通过，探针未运行。 |
| AUD-122 | 低 | 离线 artifact inventory writer 使用可预测 `.tmp` 路径并普通写入，可能跟随预置的符号链接并截断目标。 | [`inventory_locked_artifact_members.py`](../scripts/inventory_locked_artifact_members.py) 改用同目录随机独占临时文件，写入并 `fsync` 后原子替换，失败时只清理本次创建的临时文件；AST、Ruff check、Ruff format 通过，工具和测试未运行。 |

所有发现都要求手动运行相应工具，并且攻击者能够预置目标路径；当前没有发现它们被生产/CI 自动调用。修复后的动态验证建议在可回滚的临时目录完成：预先放入哨兵目录或文件，运行安全测试入口，然后确认哨兵内容仍在、既有 lockfile 未改动、输出替换只影响目标报告文件。

## 排除项与未闭合风险

- **CIDR 候选是误报。** `0xFF << 6` 为 `0x3FC0`，低八位 `0xC0` 正确判定 `100.68.0.1` 属于 `100.64.0.0/10`。现有拒绝逻辑正确；新增断言是策略回归覆盖，不是修复证据。
- **旧调用方网络 helper 是 deferred proof gap。** `urls.resolve_input()` 和 `downloader.download_media()` 有调用进程网络请求能力，但全仓调用关系审查未发现非测试生产调用者。当前 `run_urls()` 需要完整作业 capture client，缺少时在 URL 解析、profile、browser 和下载前失败关闭。该候选不是已确认的生产绕行或 SSRF。
- **P2 未通过。** 仍缺安装器/回滚、生产 capture client、per-lease worker/identity、Chromium 进程树约束、数字 IP connector 和真实 WFP enforcement。离线 harness 通过不等于主机出口隔离。
- **P4 未通过。** 用户提供的 938.968435 秒 MP4 只有 AAC 音频流，没有视频流；本机转写和默认模型文本校对已存在，20 段包含标点，原稿保留，另有 533 点时间戳侧车。侧车只是复听定位工具，人工听审和新 Desktop 会话的数据流/隐私验收仍待完成。它满足长时音频门槛，不验证视频解码或 A/V 同步。
- **P5/P6 仍开放。** 新 Desktop Skill 发现/调用 trace、许可证和发行范围决定、native provenance/linkage/notice 审阅、远端 CI 与远端干净安装仍待完成。

## 建议的下一步

1. 将 `skills/douyin-transcript/SKILL.md` 纳入下一轮全项目审查清单，并复核转写正文的指令/数据边界。
2. 如加固 sdist 解压预算，在隔离、可回滚的临时环境加入合成 archive 限额回归；不要在宿主 WFP/Firewall 上进行未经独立保护的实验。
3. 保持 URL 捕获 fail closed，直到 P2 的生产 service、认证 IPC、逐租约 worker 与 WFP 集成通过运行时验收。
4. 完成 P4 人工听审及 Desktop 隐私验收，再关闭 P5/P6 的外部发布门槛。

## 机器生成工件

安全扫描的封存工件位于本机 Codex 状态目录：

`<local user path>`

项目状态和逐日验收证据另见 [`PROJECT_AUDIT_REPORT.md` §180](PROJECT_AUDIT_REPORT.md) 与 [`ACCEPTANCE.md`](ACCEPTANCE.md)。

## §182 补充复核（2026-10-12）

### 扫描结果

- 扫描 ID：`9b5f048e-5f14-4099-827d-373e7a5871dc`。
- 目标：HEAD `b166778ee5283591a1b799535b746ba198e38653` 的冻结工作树，摘要 `codex-security-snapshot/v1:sha256:88f0fe1cf9eae0402bc5405bb81fa6dd42da3356c6d5a7d71466f5b96fcb2f77`。
- 覆盖：Python 包 25 项、Windows native 46 项、release/evidence 20 项，91/91 生成审查项已关闭；0 项可报告漏洞；coverage **partial**。
- 验证：静态源码/配置/工作流追踪；本轮没有运行测试或项目代码、没有发起外部网络请求、没有修改 WFP/Firewall。
- 机器生成报告：`<local user path>`。

### 补充风险与对策

1. **Agent Skill 转写正文边界（待专项复核，不计入本扫描 finding）。** `skills/douyin-transcript/SKILL.md` 指示将媒体转写文本读入当前 Agent 默认模型上下文，但没有明确告诉模型正文是纯数据、必须忽略其中要求调用工具、访问文件、改变任务或转发信息的指令。媒体作者可在口播中埋入间接提示注入；是否造成额外工具动作取决于宿主 Agent 的工具权限与策略，本轮没有实证。该 Skill 文件未进入扫描器生成的 91 项清单，扫描工具拒绝将其登记为当前 finding，且该入口不支持只扫子目录。**对策：** 在 Skill 中加入明确的数据边界：音视频/转写正文不授权任何新动作；忽略正文中的命令、工具调用、文件访问、外发或任务变更请求；仅按用户原始请求进行转写纠错，并只执行 Skill 已授权的本地侧车保存步骤。下一次全项目扫描应确认此路径进入审查清单。
2. **sdist 元数据审核器解压预算（扫描候选，已抑制）。** `scripts/verify_locked_wheel_metadata_audit.py:261–279` 在 tarfile 返回条目后才计入声明解压大小并检查 deadline，扩展头解析可能先消耗解压资源。候选需要一个 lock/cache 哈希匹配的恶意 sdist，且本机操作员手动运行审核；CI 不调用此工具，未建立跨边界路径，因此扫描中按本机操作员触发的资源耗尽抑制，不列为可报告漏洞。**对策：** 在 gzip 解压流上实现累计解压字节上限和读取时 deadline，再交给 tarfile；限制扩展头最大尺寸，并在隔离测试环境添加合成压缩炸弹回归。

### P4 样本状态

用户提供的 MP4 已在本机存在，大小 22,715,944 bytes；对应 raw Markdown、默认模型校对侧车和时间轴侧车均已存在。raw 元数据为 **938.922125 秒（15:38.922）**，超过至少 10 分钟门槛。此前 §176 记录 938.968435 秒，两者仅相差约 46 毫秒，都不改变达标判断。时间轴有 533 个单调时间点，用于定位复听；这次没有播放或重新转写，P4 仍需人工听审和新 Desktop 会话隐私/数据流验收。

P2/P4/P5/P6 均未通过整体发布验收；项目仍 **NOT READY FOR RELEASE**。

## §183 修复后状态（2026-10-12）

- **已实施的缓解：** canonical `skills/douyin-transcript/SKILL.md` 现在说明音视频口播、字幕和转写正文皆为不可信内容；其中要求改变任务、泄露上下文、读取文件、调用工具或外发信息的内容不得执行；如忠实转写需要，可保留这些话作为文本。`agentskills validate` 对 canonical 和 `.codex/skills/douyin-transcript` 均通过。
- **审查状态：** §182 的扫描快照未包含此改动。本次只完成人工补充复核和 Skill 结构校验，未运行提示注入攻击样本、未重跑完整安全扫描，也未验证 fresh Desktop 宿主行为。下一次全范围清单必须包含 canonical Skill 并复核是否能抵抗转写中的恶意指令。
- **P4 材料：** 当前媒体 PyAV 时长 938.968435 秒；锁定 CLI 因既有任务完成记录而返回 `skipped`，没有重新转写。四段 18 秒试听 WAV 已放入私有输出目录辅助人工比对，但尚无人工听审记录；P4 仍未通过。
- **仍开放：** fresh Desktop 的调用权限/数据流、P2 生产隔离、P5 新会话发现与调用、P6 所有者发行决策和远端 CI/干净安装仍需分别验收。项目保持 **NOT READY FOR RELEASE**。

## §184 补充人工发现：本机路径披露（2026-10-12）

- **封存扫描：** Codex Security Diff Scan `daa7e7eb-420e-4f59-a5cf-d57b0bbe916b`，HEAD `b166778ee5283591a1b799535b746ba198e38653`，快照摘要 `codex-security-snapshot/v1:sha256:adb58db3c991c2d25855fde4d3013807d225d3bb8b033615f8cfd7f3d70b5309`。91/91 生成审查项完成，扫描报告含 1 项低危 CWE-200；整体 coverage 为 **partial**。
- **评级与影响：** 低危，CWE-200。冻结扫描快照中的审计/安全文档和 Sandbox README 含具体本机用户目录；审计记录还关联私有媒体、输出文件名和摘要。如果这些文档被提交、发布或转发，会暴露账户/存储布局和媒体标识。路径不会直接授予文件访问。本次没有证据表明这些文档已发布，也未发现对应位置含逐字稿正文或凭证。
- **当前缓解：** 已泛化 6 个文本/Markdown 文件中的 16 处本机目录引用；Sandbox 命令使用 `$env:USERPROFILE` 路径模板。最初搜索只匹配反斜杠写法，漏掉一条 Markdown 链接中的正斜杠用户路径；§185 记录了补充发现与扩展复查。改动发生在扫描冻结快照之后，故不改变扫描快照的原始证据。
- **扫描覆盖说明：** 该候选位于 91 项生成审查清单遗漏的文档中，机器候选记录器未接受文档位置；本项由发布分片人工发现并手工记录于 `PROJECT_AUDIT_REPORT.md` §184。91 项清单的安全结论不能被解读为文档/所有生成证据均无问题。下一次全范围扫描应纳入文档和生成证据；发布前再次检查绝对路径。
- **验证及余项：** 全仓路径模式搜索无命中，`git diff --check` 无空白错误；本轮未重跑项目测试。项目仍 **NOT READY FOR RELEASE**。

## §185 补充文档与结构化证据审阅（2026-10-12）

- **新增文档问题（AUD-124，低风险证据引用不一致）：** 第三方许可证审查文档曾把 `windows-pe-import-evidence-complete.jsonl` 描述成 §172 分隔符修正后的当前 PE 清单。该文件是 §166 历史快照，419 行中仍保留 3 条 Ruff `missing_from_record`；当前更正证据位于 `windows-pe-import-evidence.jsonl`，419/419 行均验证通过。已更正文档指向并保留旧文件原始内容；PE edge map 的 `inventory_sha256` 与当前文件摘要相符。未修改 JSON/JSONL 证据。
- **其他补充复核：** 指定的项目/安全/许可证文档和维护说明发现若干不一致，已修正 P1 私有样本标识、Skill 校对流程授权描述、远端依赖 pinning 提醒、Benchmark RAM 标签，以及登录错误诊断前置条件。未发现其他需要改动的证据映射。
- **结构化检查：** 23 个变更 JSON/JSONL 文件均通过所做的解析、重复键、敏感路径/文本与已记录完整性核查；该检查不等于从私有缓存重新读取 wheel、许可证判断或 native provenance/linkage 验证。历史 PE JSONL 的 3 条状态被确认为已知路径分隔符误报，而不是当前证据状态。
- **范围与验证：** 本节是 §184 冻结扫描之后的人工补充审核；不改写该扫描快照或将其 partial coverage 升级为完整。修订后再次检查路径模式及 `git diff --check`；本轮未运行项目代码或测试。P4 人工听审及 Desktop 隐私/数据流、P2 生产隔离、P5 新 Desktop trace、P6 所有者与远端发布验收仍未完成，整体继续 **NOT READY FOR RELEASE**。
- **路径/样本脱敏更正：** 扩展扫描覆盖 Windows 用户目录路径的反斜杠、正斜杠和 JSON 转义写法，并搜索私有媒体文件名与报告中保留的短识别例词；发现的旧路径、文件名和转写派生例词已从审计文档移除。修正后的全仓文本扫描没有命中具体用户目录或该样本标识。此补充更正此前 §184 仅做反斜杠搜索的覆盖限制。

## §201 当前工作树补充审阅（未封存）

- **范围与状态：** 当前工作树差异扫描 ID `fc1d8e78-569a-42ac-b59e-943f351c3f86`，基线 `b166778ee5283591a1b799535b746ba198e38653`，快照摘要 `codex-security-snapshot/v1:sha256:999bd7c21b8225842163be32577d49fe2a18f12d4830f60f0e4ff3bceeb377eb`。生成清单包含 220 个差异文件、93 条源码/配置审阅项；扫描工具记录 12/93 项完成，仍是未封存草稿。因此这不是全工作树安全扫描结论，剩余源码、文档、测试夹具与生成物仍需审阅。
- **AUD-130（低风险操作隐患，快照后已做代码级缓解）：** 冻结扫描快照中的 `NetworkWfpWriteSmoke.ps1` 不强制限定 Sandbox，管理员手动在宿主执行时可暂时阻断全部 IPv4 connect。快照后已用 fail-closed stub 取代全应用规则实现，旧 `.wsb` 配置调用该入口只会抛错，不会打开 BFE。未在 Sandbox/宿主运行 stub；后续动态规则验证必须走新的 C# materializer wrapper，不能恢复全局无条件阻断。
- **AUD-131（低风险报告隐私，已修正）：** §196 审计段落曾含私有媒体文件名、任务标识和侧车文件名；现已移除，仅留时长、媒体流类型和验收结论。该文档修订不改写冻结扫描快照。
- **Deferred proof gap：** `BrowserCapture.close()` 在上下文关闭前清空 lease 状态；未来接入 broker 前应先拒绝 route callback，并等服务确认 Chromium 进程树退出后释放租约。当前 broker factory 恒不可用、CLI 未注入 capture client、pipeline 在 URL 处理前失败关闭，所以未确认当前产品攻击路径。legacy `resolve_input()` 仍有调用进程 DNS/HTTPS 能力，但全仓源码调用审查未发现当前非测试生产调用者；保持 direct-only/fail-closed URL 路径。
- **产品边界与发布门槛：** P2 service、per-lease worker/WFP/浏览器隔离与三条真实捕获仍未验收。P4 长音频 ASR/模型文本校对已具备，但至少三处人工听审和 fresh Desktop 数据流/隐私验收未完成。P5 Desktop Skill 发现/调用 trace，P6 owner license/distribution decision、native provenance/linkage/notice、remote CI 与 clean install 仍开放。项目继续 **NOT READY FOR RELEASE**。
- **运行时限制：** 本次只读源码和文档；没有运行 Windows Sandbox wrapper、BFE/WFP 探针、WFP/Firewall 修改、测试或媒体处理。§188 仍是最近封存的全工作树扫描，coverage partial。

## §202 AUD-130 旧 WFP 探针停用

- 将 `NetworkWfpWriteSmoke.ps1` 的原始 all-app IPv4 block 实现替换为立即抛错的 fail-closed stub；旧 `.wsb` profile 不会再执行 BFE 写入。两个 Sandbox/policy README 同步标注该入口 retired，并把未来动态规则验证指向 C# materializer wrapper。
- PowerShell AST parse 通过，源文件中不再有 WFP P/Invoke、`Add-Type` 或 filter-add 代码。未执行脚本或 wrapper，也未修改宿主 WFP/Firewall。修复发生在 scan snapshot 后，原 finding 仍是冻结扫描结果，当前代码只获得静态缓解证据。
- 全工作树扫描仍未封存（12/93 个源码/配置 review rows 记录关闭）；P2 生产集成和 P4/P5/P6 验收仍开放，项目 **NOT READY FOR RELEASE**。

## §203 Sandbox BFE wrapper 结果目录边界加固

- Wrapper 以前接受任意 `ResultsDirectory`，并把该 host directory 映射为 Sandbox guest 可写目录。调用者可指定本不应暴露给 guest 的路径；这是测试工具输入边界风险，没有自动调用或远程触发证据。
- 已移除该参数，将结果固定到脚本旁的 `sandbox-results`，并在目录是 reparse point 时拒绝继续。按本机测试操作边界加固记录，不列为远程漏洞 finding。
- PowerShell AST 与 `git diff --check` 为静态验证；没有执行 wrapper、启动 Sandbox、打开 BFE 或改动 WFP/Firewall。该修订晚于扫描快照，12/93 清单状态与 partial coverage 不变；P2/P4/P5/P6 仍未通过。

## §204 Python 全套回归（扫描后验证）

- 锁定 Windows Python 3.11.15 全套回归为 **636 passed、30 skipped（255.06 秒）**。两项 native interop 因未配置宿主路径跳过；其他跳过项需要本机不支持的 POSIX/FIFO/symlink 行为。
- CI 命令范围内的 Ruff check/format、lock check、clean-copy Skill install、canonical/`.codex` Skill validation、敏感文件扫描和 SPDX 2.3 schema validation 通过。
- 这是回归测试结果，不是安全扫描。它不覆盖新增/修改的 PowerShell wrapper 动态行为、C# BFE、Sandbox/WFP 或宿主网络状态。差异扫描仍未封存，仍为 12/93 项与 partial coverage；不能据此报告安全扫描通过。

## §205 当前工作树分区静态审查补充

- Python 产品源码、native capture/WFP 关键路径和 CI/发布工具由分区只读复核；未发现新的当前产品可达候选。Python URL 捕获仍在缺少已验证 service client 时 fail closed；WFP compiler/materializer 仍为不可部署预览。具体范围和未审文件见 `PROJECT_AUDIT_REPORT.md` §205。
- 发现一个未确认为漏洞的低置信度操作风险：旧 `sandbox/ScopedNetworkWfpSmoke.ps1` 只验证 SYSTEM 身份，特权操作者若在宿主误运行，可能短暂限制当前 PowerShell 映像的网络；动态 session/finally 清理限制影响。建议先加专用 Sandbox 启动门控，或退休该旧 probe。它不构成当前产品入口或普通用户攻击路径。
- 当前分区审查不能重建扫描冻结版本。Diff Scan `fc1d8e78-569a-42ac-b59e-943f351c3f86` 仍包含 220 个变更文件、93 条源码/配置审阅项，当前记录 12 项完成，未封存、coverage partial。未执行测试、Sandbox、BFE/WFP 或宿主策略变更；不据此宣称扫描通过。

## §206 当前源码/配置差异安全审核（2026-10-12）

- **扫描身份：** Codex Security Diff Scan `a5372a38-3d67-4fb7-a5fd-a38e197a0a3d`；revision `b166778ee5283591a1b799535b746ba198e38653`；冻结摘要 `codex-security-snapshot/v1:sha256:bbc0679427e5baa29cdfcdc5aa1d6a0946a92446ea2ebd967d5b110b444def0b`。
- **结果：** 111/111 个生成的源码/配置 review items 已审阅；0 个确认的可报告漏洞。捕获 service 仍 fail closed；WFP code 仍是不可部署预览/拒绝不完整读回；没有集成 broker、生产 WFP store 或可达策略修改路径。聚焦审阅的 Skill/隐私条款把媒体正文视为不可信内容，并披露模型校对会将正文放入当前 Agent 默认模型上下文、可能发送到服务商。
- **覆盖限制：** 本扫描是静态源代码/配置审阅，coverage **partial**。非源码文档、测试、fixtures 与生成证据未逐项审阅；扫描快照后的 P4 更新只有文档差异。最终封存器没有解析到 5 个 surface receipt 引用，因为 receipt 文件保存在临时目录而非 canonical scan directory；机器生成的本机 `report.md` 因此将这些 surface 标记为 “Needs follow-up”。此报告保留此限制，不宣称完整全仓审核。
- **本机报告状态：** 安全工作台已封存扫描并记录 0 findings。完整源码分组摘要及 P2/P4/P5/P6 对策见 [`PROJECT_AUDIT_REPORT.md`](PROJECT_AUDIT_REPORT.md) §234。
- **发布门槛：** 0 个安全 finding 不代表产品验收通过。P2 生产 service/WFP/浏览器隔离及真实捕获，P4 实际声学听审与 Desktop 隐私检查，P5 新 Desktop 调用 trace，P6 owner 许可/发行决定、完整 SPDX 重放和远端验收仍未关闭。项目继续 **NOT READY FOR RELEASE**。

## §207 文档与 fixture 审查跟进（2026-10-12）

- §206 的路径扫描当时没有命中个人目录；之后两条历史构建记录又写入本机 SDK 路径，`MEMORY.md` 也出现了媒体绝对路径。§235 已将三处改为泛化描述，并检查仓库文档中无该账户路径残留。该回归不属于 §234 冻结扫描发现，因此以当前树修复记录，不改写其 0-finding 结果。
- 对测试、fixtures 及 SPDX/BOM/PE 结构化生成证据进行了定向只读审查：未发现真实转写正文、凭据或额外个人路径。之后为防止同类文档回归，敏感文件检查新增 Windows 用户目录路径模式；定向测试 **19 passed、1 skipped**，仓库级检查通过。没有运行媒体处理或全套测试。机器 Diff Scan 仍是 partial；该跟进不声称完成全仓逐行安全审阅。

## §208 当前工作树 Deep Scan 启动受限（2026-10-12）

- **结果：** Codex Security Deep Scan discovery 没有启动。工具返回的明确前置条件是父任务必须提供 managed filesystem permission profile，才能安全启动只读 worker；当前会话没有配置入口。没有产出扫描报告，也没有 finding 计数。
- **解释：** 不把启动失败记作 0 findings，也不把 §234 partial Diff Scan 或 §235 定向人工复核等同于完整全仓审核。§245 新增的 WFP layer/default-sublayer 与 provider-reference reader/fixture 修改不在 §234 冻结快照里。
- **后续：** 需要在支持该 managed profile 的执行上下文，对当前未提交工作树重新运行全树 Deep Scan，并按其结果校验新改动。此处不重复请求相同前置条件失败的启动。项目继续 **NOT READY FOR RELEASE**。

## §209 当前工作树安全差异审核封存（2026-10-12）

- **扫描身份：** Codex Security Diff Scan `d8950f81-800f-4f3d-8b63-550c6dbc8161`，基线/HEAD `b166778ee5283591a1b799535b746ba198e38653`，冻结摘要 `codex-security-snapshot/v1:sha256:6c79d920544c2b2acdc4f003f6fb1e9863af18bdea2e8f874d1573ffbe4bbb06`。扫描已封存，报告 5 个 low finding。
- **覆盖：** 112/112 个生成的安全相关源代码/配置审阅项已完成：Windows native 66 项、Python Skill 28 项、离线审计脚本和 CI/build 配置 18 项。生成清单外的其余改动未逐项审查，因此对 253 个变更路径的总体 coverage 为 **partial**。这是静态源代码/配置审查，没有运行测试、利用样例、真实服务、浏览器隔离、BFE/WFP/Firewall/Sandbox 或远端 CI。

### 发现与整改建议

| 严重度 | 位置 | 风险 | 对策 |
|---|---|---|---|
| Low / CWE-150 | `scripts/hash_locked_license_candidates.py:286-290,609-612` | 非普通文件分支在路径校验前把归档成员名写入异常，终端控制字符可能操纵本地显示。 | 任何错误输出前统一转义归档路径与控制字符，并覆盖 ANSI/OSC 输入。 |
| Low / CWE-400 | `scripts/map_locked_pe_import_edges.py:368-454,503-516` | 输入虽有行数/导入数上限，同名候选扇出仍可能在序列化上限生效前构造大量对象。 | 增加累计候选/边数和工作预算，预建有界索引，采用增量有界输出。 |
| Low / CWE-400 | `scripts/inventory_locked_pe_imports.py:200-230,498-503` | RECORD 只有字节上限，没有行数上限或相对 ZIP 成员的条目数约束。 | 解析时立即执行行数上限，并校验 RECORD 路径集合与归档成员闭包。 |
| Low / CWE-400 | `scripts/check_spdx_schema.py:130-145`、`scripts/schemas/spdx-2.3.schema.json:239-243` | 将全部 JSON Schema 错误排序和保留，但仅需输出首个错误；packages 数组无数量上限。 | 限制错误数并提前停止，显示错误截断提示；增加合理的 package 数量/复杂度上限。 |
| Low / CWE-59 | `scripts/generate_dotnet_build_bom.py:891-900,918-934`、`scripts/generate_spdx_sbom.py:1238-1244` | 固定仓库输出路径可能是符号链接；在恶意检出内容中运行本地生成器可能覆盖链接目标。 | 拒绝 symlink/reparse point 和仓库外目标；用 no-follow 创建、同目录临时文件及安全原子替换。 |

以上前置条件均需要本地操作者运行相应工具；没有远程服务触发证据。风险主要是本地终端显示、审计进程资源消耗或操作者可写文件被覆盖。§250 记录后续实现的代码级缓解和未完成的动态验证。

### 其他验收边界

- 用户提供的三段 P4 WAV 文件可在听审包中访问，但当前会话无音频感知能力；没有声学听辨或漏词/增词判断。既有 ASR 差异只能作为复听线索。
- P2 的生产 broker/WFP 隔离与真实捕获、P4 声学及 Desktop 数据流验收、P5 Desktop 调用 trace、P6 发行/许可证与远端验收仍开放。项目继续 **NOT READY FOR RELEASE**。

## §250 补充发现与缓解（2026-10-12）

- **CWE-400，RECORD 行字段放大：** 在 CSV parser 建立完整字段列表前，新增字符级边界预检，拒绝超过三列的行并限制逻辑记录数。代码已修改并加入超宽行回归用例；本轮未运行测试。
- **CWE-59，输出父目录竞态：** POSIX 写入改为 no-follow 目录句柄与相对目录原子替换；Windows 打开每级目录时拒绝 reparse point，并通过不共享 delete 的句柄固定路径链，再用同目录临时文件替换。已加入 POSIX 父目录切换用例；未运行测试，Windows handle 行为也未动态验证。
- **本节状态：** 这是 §249 冻结扫描之后的补充人工复核与代码修复，不更改冻结报告的 finding 数量/coverage。静态 Ruff 与 `py_compile` 检查已运行；新回归用例和完整当前树安全扫描仍待完成。项目仍 **NOT READY FOR RELEASE**。
