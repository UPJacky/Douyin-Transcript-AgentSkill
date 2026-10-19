# 项目审核报告与整改对策

> 2026-10-13 交付范围复核：见 [项目为何迟迟未完成及收尾对策](PROJECT_DELIVERY_REVIEW_2026-10-13.md)。本机本地转写可用，URL 生产链仍有实现缺口；建议分别验收本地试用、URL 服务和公开发布。该复核未将既有未通过门槛改为通过。最新封存安全扫描应以独立安全报告 §285 为准（2 项 Low、partial）；下方旧摘要中的 §283 扫描为历史状态。

- 审核日期：2026-10-13（Asia/Shanghai）
- 项目：Douyin-Transcript-AgentSkill / `douyin-transcript`
- 审核对象：历史基线为 HEAD 154d9ef，主要整改记录于本地检查点 b166778。最新封存 Codex Security Diff Scan 仍为 §283（`0e0f14d7-0ce0-44a3-935c-b003aac7f88c`）：冻结 worklist **123/123** 项完成，0 个报告级 finding，coverage 为 **partial**。该冻结快照早于 §284 的 WFP ACL 源码/测试改动，不能代表当前完整差异；§284 只记录本地回归和手动代码复核。完整范围见 [SECURITY_REVIEW_REPORT_2026-10-13.md](SECURITY_REVIEW_REPORT_2026-10-13.md)。
- 审核范围：CLI、URL 与网络边界、浏览器代理、下载、ASR、缓存、SQLite、文件权限、Markdown 输出、Skill 包、CI 与项目验收清单
- 审核方式：源码与验收清单复核、Windows 本地离线单元/模拟测试、Codex Security 差异扫描、Ruff、锁文件检查、Agent Skills 标准校验及仓库外 clean-install 命令验证。历史记录见第 9 节及 §§145–283；当前续审见 §284。最新 sealed scan 及其静态范围见 [安全审核报告](SECURITY_REVIEW_REPORT_2026-10-13.md)；扫描摘要不覆盖 §284 源码/测试。静态审查不等于运行时、远端或发布安全验收。
- **P6 状态：** §268 已将 SPDX freshness 和 .NET build-output identity 比较接入 CI；§271 又用 pinned .NET SDK 10.0.401 在本机生成新 BOM，三个构建的 41 条输出身份全部匹配，主构建和两个 related build 的锁定源字段也与仓库清单一致；§273 新鲜复验了四个锁定 signed NuGet 包的 canonical contentHash 和签名；§277 新增 PyAV 15.1.0 的 14-wheel/98-native-member configure 字符串证据，§278 在 scanner hardening 后重跑，输出仍与清单摘要一致；§279 重放了完整本机 lock cache、SPDX bytes、freshness 与官方 schema。SPDX 当前 121 个 package records 重建匹配。还缺远端 CI、clean install、所有者许可证/发行范围决定及完整 native provenance/linkage/notice；本地构建和二进制内字符串不证明远端复现或发布批准。
- **P2/P4 状态：** §281 的 shared-sublayer DTO/验证器和合并 fake fixture 仍无 native producer，也未接入 adapter/native reader；不能证明多租约 WFP。§284 将 prototype WFP object DACL 从服务 SID 所有权与 `GENERIC_ALL` 收窄为 LocalSystem 所有、受保护 DACL 和仅 LocalSystem/service SID 的 `GRGWGX`，并用 Runtime harness 验证。此为 ACL 配置代码级改进，不证明安装服务 SID、真实 WFP 权限或完整可见性。生产隔离、回滚、live BFE 与三次授权捕获仍未完成。P4 三段 WAV 的文件身份/格式/长度与私有 manifest 一致，但本会话没有音频感知能力，不能给出听辨结论，也没有修改逐字稿。Skill 要求调用 Agent 默认模型校对和补标点，但 CLI 仅产 raw ASR；侧车哈希/任务绑定不证明模型身份或句读语义，fresh Desktop 调用与隐私数据流验收开放。`08:50–09:08` 年份冲突仍需听审。
- **最新 Python 全量回归（§284）：** Windows Python 3.11.15 完整套件 **728 passed、46 skipped、0 failed**（171.52 秒）。跳过项包括 native interop 未配置、Windows symlink 权限及 POSIX-only 检查；不证明 Windows 对抗性 reparse race 或 Linux/macOS 行为通过。
- **发布门槛：** 最新 sealed scan §283 的 123/123 worklist 与 0 finding 仅适用于其冻结摘要，coverage 为 partial，且不包含 §284 变更。最终发布前要等 P2/P4/P5/P6 与最终文档稳定后重跑当前树扫描。P2 live isolation、P4 声学/Desktop、P5 fresh Desktop trace、P6 owner/license/remote gates 仍开放。项目整体 **NOT READY FOR RELEASE**。
- 初始静态复核限制（历史基线）：当时未访问真实媒体、未下载模型或 Chromium、未执行远端 CI；之后的本地 P1 真实转写证据见第 62、69 节，P2 页面访问与失败复验见第 17、78 节。Linux/macOS 实机行为及远端 CI 仍未验证。

## 257. 2026-10-12 NuGet canonical contentHash 绑定修复

- **修复：** 移除 §256 中把完整 `.nupkg` raw SHA-512 直接与 lock `contentHash` 比较的错误条件。新增锁定 .NET SDK 10.0.401 helper，直接调用该 SDK 自带的 `NuGet.Packaging.PackageArchiveReader.GetContentHash` 从实际归档流重算 NuGet canonical SHA-512；helper 限定单一输入、64 MiB 上限、固定 SHA-512 输出，不打印本地路径。BOM 生成器分别保留三项校验：raw archive SHA-512 对 `.nupkg.sha512` sidecar、缓存 metadata contentHash 对 lock、NuGet API 计算出的归档 contentHash 对 lock，并继续对每个 exact package 执行 `dotnet nuget verify --all`。
- **真实包验证：** 对锁文件四个真实 signed `.nupkg` 通过 SDK NuGet API 重算，4/4 与 lock `contentHash` 匹配；四个 raw archive SHA-512 均与 lock 值不同，符合 NuGet 对签名包摘要范围的定义。重新运行 BOM 生成器的 locked x64 Release 构建路径成功，四包签名验证均通过；BOM 对 233 项源/生成/输出 identity 的核验为 0 missing / 0 mismatches。
- **回归：** `tests/unit/test_dotnet_build_bom.py` 为 **14 passed、1 skipped**；新用例分别覆盖“canonical hash 匹配但 raw archive hash 不同仍接受”、“sidecar 与 metadata 彼此匹配、但归档计算 hash 与 lock 不同则拒绝”，以及 malformed helper output 拒绝。NuGet helper 在锁定 SDK 下 Release build **0 warnings、0 errors**；Ruff check/format 通过。跳过项仅为当前账户缺少创建 symlink 的权限。
- **审计边界：** §256 的 CWE-345 finding 在当前工作树已按正确摘要口径缓解，但该代码/helper 是冻结扫描之后加入，必须纳入下一次当前树安全扫描；旧扫描仍为 partial，分区回执链接缺口和未审文档/测试/fixtures/证据仍未关闭。这里的锁定包验证不证明所有权、许可证适用性、远端复现或发行批准。
- **其他发布门槛：** 用户提供的三段 WAV 与私有 manifest 一致；当前会话没有音频感知接口，未形成听辨结论、未改动逐字稿。P2 生产 service/WFP/per-lease isolation、P4 声学与 Desktop 隐私数据流、P5 fresh Desktop trace，以及 P6 owner/license/remote gates 仍开放；项目继续 **NOT READY FOR RELEASE**。

## 258. 2026-10-12 P2 WFP store 原型与当前工作树安全差异审核

- **扫描身份与覆盖：** Codex Security Diff Scan `39e165f7-f0c9-4f58-bed9-4793b64e301c`；基线/HEAD `b166778ee5283591a1b799535b746ba198e38653`；冻结摘要 `codex-security-snapshot/v1:sha256:7e3a70b3671b7c4a9cdbe30876e0189ff8d44683b770d49ac2816caa32ebcd22`。扫描关闭 116 个安全 review work items：Python/Skill/脚本/工具 49 项，Windows native 67 项；未发现可报告 finding。覆盖仍为 **partial**，WFP enumeration/ACL visibility 与 DNS 完整答案/DNSSEC 证明仍是生产启用前门槛。工作台还报告 `filesTotal: 264`，所以 116 不能解释为所有改动文件或所有运行时表面均已检查。
- **P2 本轮变化：** `NativeWfpPolicyStoreAdapter` 及 fake-store harness 进入扫描快照；此前 Release build 与 harness 结果为 **0 warnings/0 errors、16/16**。生产 `CaptureServiceFactory` 仍使用 fail-closed gate/worker，adapter 尚未接线；没有执行 live BFE/WFP/host firewall 操作。上线前还需审查 SYSTEM/service SID `GENERIC_ALL` ACL 范围、证明真实 native API 的 Abort/Dispose deadline 可控，并验证 commit 失败语义。30 秒 deadline 是协作检查，不能抢占已阻塞的 native 调用。
- **扫描发现与对策：** 本次未确认新增报告级安全缺陷。继续保持 URL 捕获 fail closed；在连接任何生产路径前，在 disposable guest 中证明 WFP 对象枚举和 ACL 可见性完整、DNS 回答集完整且 DNSSEC 行为明确，再验证 apply/readback/rollback 失败语义及服务 ACL。README 中暗示当前可打开 Chromium 登录的文案已由 §259 修正为“当前不启动浏览器、不能继续登录；未来只有经验证的 broker 启用后才由用户手动登录”。逐项对策见 [SECURITY_REVIEW_REPORT_2026-10-12.md](SECURITY_REVIEW_REPORT_2026-10-12.md)。
- **P4 听审：** 已收到 `focus_01m11.wav`、`focus_05m40.wav`、`focus_08m41.wav`；私有听审包有 balanced 与 SenseVoice 的本地 ASR 对照。自动识别只提供 01:11 关键词/ASIN、05:40 bid 术语、08:32–08:50 年份等复听候选；08:50–09:08 的 2016/2026 冲突仍需人工听音。当前会话没有音频感知接口，未形成声学结论，也未改 raw/reviewed 逐字稿。P4 声学验收和 Desktop 数据流/隐私验收仍开放。
- **项目状态：** P2 生产 service/WFP/per-lease 隔离、P4 声学/Desktop、P5 Desktop trace、P6 owner/license/remote gates 均未关闭；项目整体 **NOT READY FOR RELEASE**。

## 259. 2026-10-12 README 当前 URL 登录行为更正

- **修正：** `README.md` FAQ 过去暗示当前 URL 任务会打开 Chromium 并等待人工登录，与无 broker 时的 fail-closed 实际行为不一致。现在明确说明当前在浏览器启动前失败，不会打开 Chromium，也无法继续当前任务；仅未来 broker 已集成且经 `doctor` 验收后，才由用户在可见浏览器中手动登录。英文 README 原有“future verified URL integration”说明与当前代码一致，无需修改。
- **验证：** 对 `README.md`、`README_EN.md` 与 canonical Skill 做关键词复核；用户登录指示现在受 future verified broker 条件约束。该文档修正不启用 URL 捕获，不改变程序、浏览器、WFP、BFE 或主机网络策略；P2 仍 **OPEN / NOT PASSED**。

## 262. 2026-10-13 Codex Security 冻结快照封存状态确认

- **封存结果：** 读取 canonical scan 后确认 Codex Security Diff Scan `bcb4d896-63ef-4c58-a2f2-2ee56e68f7b3` 状态为 `completed`，`sealedAt=2026-10-12T16:15:59.114456Z`（北京时间 2026-10-13 00:15:59）。扫描仍固定在 §261 所述快照摘要；116/116 worklist 项已审阅，记录两个静态问题。
- **覆盖边界：** manifest 记录 265 个变化路径、116 个 worklist 项和 partial coverage；未逐项审阅的其它差异、测试/文档/fixture/生成证据以及 live WFP/BFE、Sandbox、真实捕获、压力测试、远端 CI 均不因封存而关闭。两个问题的细节与对策见 [SECURITY_REVIEW_REPORT_2026-10-12.md](SECURITY_REVIEW_REPORT_2026-10-12.md)。
- **P4 附件：** 当前收到的三段 WAV 仍不能由本会话直接听辨。附件重提或身份匹配不构成声学核对；不报告漏词/增词/术语的听审结论，也没有修改 raw/reviewed 逐字稿。P4 声学听审和 Desktop 数据流/隐私验收仍开放。
- **状态：** 此次只确认封存状态并同步报告；P2/P4/P5/P6 发布门槛继续开放，项目仍 **NOT READY FOR RELEASE**。

## 261. 2026-10-13 P4 附件重提、当前树安全复核与文档状态同步

- **P4 附件与听审：** 用户再次提交 `focus_01m11.wav`、`focus_05m40.wav`、`focus_08m41.wav`。三段仍与私有听审包既有清单对应；本会话没有可感知音频的接口，不能给出漏词、增词、术语或年份的声学判定。balanced/SenseVoice 结果只作为复听线索；未修改 raw/reviewed 逐字稿。P4 声学听审和 fresh Desktop 数据流/隐私验收仍未通过。
- **安全快照身份与覆盖：** Codex Security Diff Scan `bcb4d896-63ef-4c58-a2f2-2ee56e68f7b3`，HEAD `b166778ee5283591a1b799535b746ba198e38653`，快照摘要 `codex-security-snapshot/v1:sha256:058ece6601497d92c65823f6d67a0bbb8daaa759dc60d88a5158228fb8a1c3e1`。全部 **116/116** 个生成的安全 worklist 项已静态审阅：Python/Skill/scripts/tools/CI 49 项，Windows native/WFP 67 项。工作区当时含 **265** 个变化路径，worklist 外文件未逐项覆盖，整体 coverage 仍 **partial**。记录最初生成时尚未封存；最终状态见 §262。
- **新增静态问题与对策：** (1) [`inventory_locked_artifact_members.py`](../scripts/inventory_locked_artifact_members.py#L166)、[`inventory_numpy_native_members.py`](../scripts/inventory_numpy_native_members.py#L72) 和 [`inventory_locked_pe_imports.py`](../scripts/inventory_locked_pe_imports.py#L86) 在 TOML 解析前无界 `read_bytes()`，调用者可指定锁文件，可能使离线工具内存/CPU 耗尽（CWE-400）。对策是共用分块有界读取，在超上限时、解析前拒绝，并覆盖上限边界与超限稀疏文件测试。当前未发现仓库 CI 自动调用这些工具。
- **新增静态问题与对策：** (2) [`ChromiumAsUserTokenSmoke.ps1`](../native/windows/wfp-policy-plan/sandbox/ChromiumAsUserTokenSmoke.ps1#L505) 只以 SYSTEM SID 当作 Sandbox guest 证明，后续会创建本机用户、复制文件和改 ACL；[`GrantInteractiveDesktopAccess.ps1`](../native/windows/wfp-policy-plan/sandbox/GrantInteractiveDesktopAccess.ps1#L112) 只校验交互会话/请求字段，后续会改桌面 ACL（CWE-269）。风险需已有高权限操作者在宿主误运行；不是远程提权。对策是在副作用前验证可信 host controller 签发、绑定一次性 guest ID 与 run token 的 attestation；请求改用受保护 IPC，只允许本次创建的确切低权 SID，并在 ack 失败时回滚 ACL。
- **文档隐私与状态一致性：** 安全报告第 63 行的本机用户目录已替换为泛化占位，`scripts/check_sensitive_files.py` 通过。`docs/PROJECT_AUDIT_REPORT.md` §256 已标为被 §257 取代的历史快照；相关验收文档已注明 §261 冻结扫描的最终封存状态、partial coverage 和两项发现，不把封存误写成 clean 结论。
- **本轮验证：** Python 全套 **683 passed、46 skipped、0 failed**；`scripts/check_sensitive_files.py` 通过，`git diff --check` 通过（仅 Git 的 LF/CRLF 提示）。本轮未执行 PowerShell、Sandbox、BFE/WFP/Firewall、超大锁文件压力测试、远端 CI 或声学听审。
- **发布状态：** P2 生产 WFP/service/per-lease 隔离、P4 声学/Desktop、P5 Desktop trace、P6 owner/license/remote gates 仍未关闭。项目继续 **NOT READY FOR RELEASE**。

## 260. 2026-10-12 P2 transaction readback 与 P6 BOM 身份续验

- **P2 修复：** NativeWfpPolicyStoreAdapter 现在在任何写入前拒绝缺失整体 native readback projection；新增 transaction snapshot 接口，使协调器比较写事务同一视图中的完整投影，而不是丢弃该证据再拼出 DTO。Runtime fake-store harness **16/16 passed**，含缺失投影不进入变更的用例；Runtime 与 harness 的 dotnet format whitespace verify 检查均通过。该实现仍只有注入式原生 API seam 与 fake，生产 native backend、服务接线和 live BFE/WFP 验收未完成，捕获路径保持 fail closed。
- **P6 BOM：** 锁定 .NET SDK 10.0.401 下的 BOM 生成器已在本次 source/harness 更新后成功重建清单；合计 **235 条身份记录 / 218 个唯一相对路径**，docs/dotnet-windows-build-bom.json SHA-256 为 `A0BE288F06FFCAEB6357312D12212099A7512EBD3374B5FCCE4610FF24700B39`。tests/unit/test_dotnet_build_bom.py **14 passed、1 skipped**；跳过项是当前账户没有 Windows symlink 创建权限。
- **验收状态：** §258 安全 Diff Scan 是上述新 source patch 之前的冻结快照，不能覆盖本次改动；P2 live isolation、P4 acoustic/Desktop、P5 fresh Desktop trace、P6 owner/license/remote gates仍开放。项目继续 **NOT READY FOR RELEASE**。

## 1. 结论

**历史状态 §163（2026-10-11；后续快照见 §§168–169）：** Windows Python 3.11.15 全套回归为 **604 passed、27 skipped**（63.63 秒；JUnit 在仓库外，SHA-256 `338965271573B362DBC148E545DAFD36CF1B953B4A0671CE6AD70D7AE26D2DA7`）；两项同用户 named-pipe 互操作通过。sidecar 现要求每段均含中文句读标点。P6 离线 verifier 覆盖 41 packages、210 artifacts、41 metadata、9 license、2 notice、1,149 supplemental members；FlatBuffers 版本特定 Apache-2.0 legacy mapping 与 SBOM 声明一致，schema 通过且 `licenseConcluded=NOASSERTION`。格式化生成器源码后按原 creation timestamp 重生成 SBOM，当前 SHA-256 `5A861F6A4AF4D7FA027A236C1979D3CC37DF0323844996B84A162756D09FD091`，schema 与 byte verifier 均通过。P2 编译器仍 `not-deployable`；当前进程无管理员令牌/远端 endpoint，且标准 UAC 探针在进程创建前被执行器策略拒绝。没有安装服务或修改 WFP/Firewall。P2/P4/P5/P6 外部门槛仍开放，项目 **NOT READY**，详见 §163。
**历史状态 §171（2026-10-11；已由 §172 更新）：** 当前工作树 Windows Python 3.11.15 全套当时为 **617 passed、29 skipped**（94.35 秒）。P2/P4/P5/P6 外部门槛仍开放；该快照中的 wheel metadata 与 PE RECORD 计数已由 §172 全量复核及路径规范化结果取代。

**历史状态 §172（2026-10-12；本地样本和安全扫描由 §§175–176 更新）：** 当前工作树 Windows Python 3.11.15 全套为 **618 passed、29 skipped**（269.56 秒）；两个 native interop 因未配置 host path 跳过，其余跳过项要求当前 Windows 不支持的 POSIX/FIFO/symlink 行为。P6 离线 metadata audit 现核验 `uv.lock` 与私有 SHA-256 缓存中的 **235/235 个制品（199 wheel、36 sdist，41 个包）**，包括制品大小/SHA-256、METADATA/PKG-INFO 包名/版本/摘要和 wheel 内 RECORD 对应行；evidence JSON SHA-256 为 `b1dbbf4bb7a636cebe11cee8017ffdecfaa6a57eeb8b73383537c63c80421b9c`。44 个制品元数据缺少两种许可证字段，涉及 6 个包；这不是许可证结论。唯一字段差异为 Protobuf 7.36.2：sdist 为 `BSD-3-Clause`，wheel 是旧式 `3-Clause BSD License`；现有 SPDX 声明继续基于有效 SPDX 表达式，不作修改。Windows RECORD 反斜杠路径已规范化比对，PE 清单现在是 419/419 RECORD 成员核验通过；三个 Ruff EXE 旧 `missing_from_record` 结果是路径分隔符误报，原始 RECORD 路径仍保留。更新后的 PE inventory SHA-256 为 `18236b199a2cd5e8d6db98beec04447546e799c9153a46085274c14c2ff570ae`，候选边图 SHA-256 为 `b7d594ec44d3d7af758b66140de1fa93fbee8e9e0cb898eb2bf0a86221662099`。边图仍有 2,654 项导入、266 项同制品候选、2,388 项未在清点的 PE 成员中匹配、0 歧义；不匹配不表示缺失依赖，候选匹配也不是 loader/linkage 证明。

**当前状态 §176（2026-10-12）：** 新提供的本地中文 MP4 时长为 **938.968 秒（15 分 38.968 秒）**，超过 P4 的 10 分钟样本门槛；CLI 原始 ASR 成功，输出目录权限检查为 `ok`。已按用户授权由当前 Agent 默认模型完成文本校对并保存独立侧车；原始稿 SHA-256 `已在本机验证（具体值未列入报告）` 未改变。侧车保留原稿框架，20 段均含句读标点，最长无标点连续长度 26 字；校对只基于文本，没有听音确认。流量来源/ASIN 术语、词根分类末项、案例专名、词级年份和部分数字仍需人工复听。P4 长样本转写与模型文本校对已完成，三处人工听审及新 Desktop 默认模型端到端调用仍未完成。

**当前状态 §178（2026-10-12）：** §177 的 Windows Python 3.11.15 全套复测为 **618 passed、29 skipped**（163.66 秒）；Pinned .NET SDK 10.0.401 下，capture-pipe source harness 通过，WFP policy/native structure harness **10/10**，相关 C# 格式检查也通过。Ruff、两个锁文件、敏感文件扫描、SPDX 2.3 schema 和 `git diff --check` 同样通过。P4 长样本/校对已完成，仍需人工听审及 fresh Desktop 数据流验收。P2 仍缺生产 service、逐 lease worker/identity、实际 WFP/Chromium egress 隔离和三条成功真实捕获；P5 缺新 Desktop Skill 调用 trace；P6 缺所有者许可证/发行/远端决定及 native provenance/linkage/notice 与远端验收。整体仍 **NOT READY FOR RELEASE**。

**当前状态 §179（2026-10-12）：** 为 §176 的长样本使用 `--timestamps --force` 再跑一次本地 ASR，CLI 返回 `success`、`raw_asr_only`；另存时间轴文件 `私有时间轴侧车`（19,887 bytes，SHA-256 `已在本机验证（具体值未列入报告）`），原始稿 `__2.md` 为 13,860 bytes。时间轴含 **533 个单调递增时间点**，从 00:00 至 15:37，位于 938.968 秒源媒体时长内；只用于定位复听，不代表人工听审或新模型校对。当前私有 output 目录 ACL 检查为 `ok`，此前原始稿哈希仍未改变。按主题匹配得到可供操作者复听的时间位置：流量来源/ASIN 01:11、竞价示例 05:40、年份/排名 08:41、词根分类 08:59；正文未复制到报告。P4 仍需人对照音频听审并记录差异，另需 fresh Desktop 数据流验收；P2/P5/P6 门槛仍开放，项目仍 **NOT READY FOR RELEASE**。

**当前状态 §180（2026-10-12）：** 最新 Codex Security Diff Scan 已封存；其冻结快照覆盖 207 个变更文件中的 90/90 条源代码/配置审核项，报告整体 coverage 为 partial。快照后修复 3 项低危维护脚本/工具问题，尚未运行动态回归或重新扫描。三项整改有静态 AST/Ruff/格式证据；§177/§178 的历史全套测试和原生 harness 通过记录不能替代对扫描后工作树的回归。安全报告详见 [SECURITY_SCAN_REPORT_2026-10-12.md](SECURITY_SCAN_REPORT_2026-10-12.md)。

**当前状态 §181（2026-10-12）：** 当前工作树 Windows Python 3.11 全套 **624 passed、30 skipped，255.56 秒**；Pinned .NET SDK 10.0.401 capture-pipe harness 通过（新增 connector fake-dialer 场景），WFP policy/materializer harness **10/10**，两个 .NET 项目格式检查、Ruff check/format、Skill 与 SPDX 工具锁文件检查及 `git diff --check` 通过。新增 AUD-123 清理所有权修复和 P2 数值 IP TCP connector 尚未包含在任何新的封存 Codex Security 扫描中；扫描覆盖仍 partial。P2 仍无生产 service/worker/WFP permit provider、隔离 Chromium 或三条成功真实捕获；P4 仍缺人工听审及 fresh Desktop 数据流验收；P5/P6 外部门槛仍开放，整体 **NOT READY FOR RELEASE**。

**历史状态 §195（2026-10-12）：** §193 的 P6 离线审计工具定向回归为 **41 passed、2 POSIX-only skipped**，Ruff/格式/diff 检查通过；未重跑全套或 Deep Scan。§194 修复 WFP IPv4 主机序并添加 raw UINT32 断言：`127.0.0.1 → 0x7F000001`、`93.184.216.34 → 0x5DB8D822`；.NET 10.0.401 x64 Release build **0 warning、0 error**，离线策略/materializer harness **10/10**，格式检查通过。§195 新增受 SYSTEM 与随机 guest token 双重限制的 C#→BFE 测试探针，已 self-contained publish，普通离线自测 10/10，宿主调用探针时正确在策略修改前拒绝。实际 Sandbox BFE 测试没有开始：宿主已有一个活动的 Windows Sandbox，`wsb start` 返回 `CO_E_APPSINGLEUSE`；没有停止、进入该实例或修改宿主 WFP/Firewall。需等当前 Sandbox 关闭，再用 wrapper 创建一台新 guest 实测 BFE add/readback、精确 loopback、错误端口/外网阻断和清理。P2 源码复核 §192 确认 URL capture 继续 fail closed，无生产 BFE apply/rollback、逐 lease worker/identity 或 permit provider。用户给出的 938.968435 秒 MP4 复核只有 AAC 音频轨；长时音频 ASR/默认模型校对已完成，至少三处人工听审和 fresh Desktop 数据流/隐私验收仍未完成。P5 Desktop trace、P6 owner LICENSE/发行决定、完整 native provenance/linkage/notice、远端 CI 和干净安装仍未完成。§188 是最近封存的全工作树扫描，coverage partial；§189、§191、§193–§195 修改及 §192 源码审查均在该快照之后。整体 **NOT READY FOR RELEASE**。

**历史状态 §197（2026-10-12）：** 静态复核发现 Sandbox BFE 探针使用 SYSTEM SID 且由 SYSTEM 进程发起网络测试，不能证明真实 lease 隔离。P5 锁定 clean-copy 安装冒烟通过。Windows Python 3.11.15 全套回归为 **636 passed、30 skipped（255.59 秒）**。项目仍 **NOT READY FOR RELEASE**。

**历史状态 §198（2026-10-12）：** 用户再次给出的 P4 长样本与 §196 已验证的本地文件相同（22,715,944 bytes，既有锁定 PyAV 时长 938.968435 秒，只有双声道 AAC 音轨）。长时音频 ASR 与默认模型文本校对已完成，因此本轮未重复转写；P4 的 10 分钟以上音频门槛满足，但人工听审和 fresh Desktop 数据流/隐私验收仍开放。历史报告中的设备/账户标识已脱敏，见 AUD-128。P2 有效 BFE/双租户与生产隔离验收、P5 Desktop 调用 trace、P6 owner/native/远端验收仍开放；§188 是最近封存的全树安全扫描且 coverage partial。项目整体仍 **NOT READY FOR RELEASE**。

**历史状态 §199（2026-10-12）：** P6 单独盘点了 wfp-policy-plan 的 4 个 NuGet build-only 依赖；本地 lock contentHash 与缓存元数据相符、nupkg SHA-512 与 sidecar 相符。应用 SBOM 范围未扩大，capture-pipe 当前无 NuGet 依赖。Win32Docs 包级许可条款和生成输出的再分发适用性仍未闭合，未作许可结论。P4 长音频门槛已满足；P4 人工听审/Desktop、P2 Sandbox/生产隔离、P5 新 Desktop 调用和 P6 所有者/远端验收仍开放。最近封存全树安全扫描为 §188 且 coverage partial；整体仍 NOT READY FOR RELEASE。

**历史状态 §201（2026-10-12）：** 当前差异安全审阅发现一个低风险的手动 WFP 诊断误操作隐患；扫描尚未封存，93 条源码/配置清单中 12 条记录为已关闭，覆盖不完整。P2 生产隔离、P4 人工听审与 fresh Desktop 数据流、P5 Desktop 调用 trace、P6 所有者/许可证/远端发布条件仍未完成。项目仍 **NOT READY FOR RELEASE**。

**历史状态 §202（2026-10-12；当前修订见 §203）：** AUD-130 的旧全应用 WFP block 入口已替换为 fail-closed stub，PowerShell AST 解析通过；没有运行脚本或打开 BFE。

**历史状态 §203（2026-10-12；当前验证见 §204）：** C#→BFE Sandbox wrapper 的 guest 可写结果目录已固定为专用 `sandbox-results`，并拒绝 reparse point；PowerShell AST 解析和 `git diff --check` 通过。没有运行 wrapper、Sandbox 或 BFE/WFP。

**当前状态 §204（2026-10-12）：** 锁定 Windows Python 3.11.15 全套回归命令 `uv run --project .\skills\douyin-transcript --locked --no-sync --group dev pytest -q` 完成，**636 passed、30 skipped（255.06 秒）**。两个 native interop 因宿主路径未配置而跳过，其余为当前 Windows 不支持的 POSIX/FIFO/符号链接行为。CI 等价本地检查也通过：Ruff check/format（82 个文件）、Skill lock 检查、仓库外 clean-copy 安装、canonical 与 `.codex` Skill 校验、Git 可见敏感文件扫描及 SPDX 2.3 schema 校验。此次没有运行 Sandbox/BFE/WFP、C# probe 或远端矩阵；测试结果不能关闭 P2。§201 的安全扫描仍未封存（12/93 项）且不覆盖 §§202–203。P2/P4/P5/P6 验收门槛仍开放，整体仍 **NOT READY FOR RELEASE**。

**当前补充审阅 §205（2026-10-12）：** 对当前工作树的 Python 产品源码、native capture/WFP 关键路径和本地 CI/发布工具完成了分区只读复核；未发现新的、可由当前产品入口触达的安全问题。发现一项低置信度手工操作风险：旧 `ScopedNetworkWfpSmoke.ps1` 只门控 SYSTEM 身份，特权操作者若在宿主直接运行，可能短暂限制当前 PowerShell 映像的网络；动态 session 与 finally 清理降低影响，尚无自动/低权调用路径。对策是在复用该 probe 前增加可验证的专用 Sandbox 启动门控，或退休该旧 probe 并只保留新的隔离 wrapper。冻结工作树扫描仍为 12/93 项、未封存；本次只读复核不能替代剩余清单。P2 生产隔离、P4 人工听审/Desktop、P5 新会话 trace、P6 owner/许可/远端验收仍未通过，整体 **NOT READY FOR RELEASE**。

P6 离线归档审核工具的两个低危问题已在 §174 完成源码整改：ZIP/RECORD 资源边界提前到解析前生效，stderr 错误统一转义终端控制符。§174 当时只运行语法编译、Ruff 和格式检查；§193 后续补入 ZIP/RECORD 预检和终端转义回归测试。

**§160 清单状态更正：** §160 初版清单把 ZIP 元数据中未设置 Unix 类型位的普通文件误记为 `other`；§161 的更正扫描重分类 50 行。§160 报告中的“297 个未绑定候选”为粗略对账结果，已由精确 `(包名, 版本, 制品 SHA-256, 成员路径)` 复算纠正为 286 个普通文件候选。旧计数由本节更正并取代；报告、manifest 与 JSONL 的正式路径保持 `artifact-member-inventory-complete*`。

> 下方原结论正文是 §159 的历史快照；§160–163 已更新测试、证据覆盖及当前验收状态。

**§159 历史状态快照（由 §§162–163 更新）：** 本地 ASR 环境就绪；浏览器隔离不可用，Douyin URL 仍为 `setup_required`，P2 继续 fail closed。Windows Python 3.12.13 的 §156 全套结果为历史 **590 passed、29 skipped**；Python 3.11.15 的 §152 全套结果为历史 **584 passed、29 skipped**。当时 `test_p2_downloader.py` 为 57 passed、1 skipped，socket-handoff 与下载 smoke 为 2 passed。当前 Python 3.11.15 全套结果见 §163。先前已用当前 Agent 默认模型为用户原始转写创建独立私有校对侧车：原稿哈希不变、frontmatter 保留，已补齐标点；校对依据是文本，没有逐字听音。helper 的格式守卫不证明模型校对质量或声学准确。P4 仍缺 10 分钟以上样本、至少三处人工听审及新 Desktop 端到端验收，P5 缺新 Desktop 会话验收。

P2 的 `run_urls()` 只允许完整作业 client 处理非空 URL 批次，但 CLI 没有已验证 service client。§140 的 named-pipe 原型、§142 的 Python adapter 和 §143 的预认证握手仍未接入生产 SCM service、per-lease worker/SID 或默认 CLI；§136 的 WFP policy preview 不可部署。AppContainer/低权限 SID 原型均未证明锁定 Chromium 可以启动，当前没有管理员主机/端点或管理员令牌；本轮只读复核仍为 `IsAdministrator=false`、`IsSystem=false`，没有宿主服务或 WFP/Firewall 修改。P6 的离线 SPDX verifier 当前复核 41 packages、210 artifacts、41 metadata、9 license、2 notice、1,149 supplemental members；SBOM 为 121 package records / 137 relationships，NumPy 原生成员清单为 1,130 行/40 个 wheel。§158 已用另一个私有缓存补齐全部 6 个 CTranslate2/ONNX Runtime Windows 目标 wheel，记录 20 个 PE 成员和 250 个普通/延迟导入项；§159 又对全部 235 个锁定 artifact（2,097,567,472 字节）逐项验明大小和 SHA-256，并单独写入私有缓存。字节身份清单不等于完整许可审查；上述结果均不能证明动态加载、静态链接、完整 provenance 或许可适用性；另缺完整 native provenance/link map、许可适用结论、根目录 `LICENSE`、仓库归属决定、远端 CI 与干净安装。项目整体仍 **NOT READY**。

**最新续审 §§145–163：** 完成全部 40 个 NumPy 锁定 wheel 的许可候选和 native-member/RECORD 字节清点；AUD-92 修复缓存路径替换竞态；AUD-93 从 `TranscriptionPipeline` 移除调用方浏览器/downloader 回退。§153 收紧 P4 侧车 JSON/UTF-8 输入，§154 加入长无标点片段拒绝，§156 增加 MP4/AAC 解码覆盖；§163 再加强逐段标点守卫。§157 刷新 P2 管理员环境可实现性复核、Python 3.11 定向回归和 P6 离线证据校验；§158 补充用户原稿的文本校对侧车证据与 Windows PE 导入映射；§159 补齐全部锁定制品字节复核。§162 增加纯代码 per-lease 策略编译器和 286 个成员内容分类。§163 的本机全套复测为 604/27；两项 named-pipe 互操作通过。标准 UAC 探针再次在子进程创建前被执行器拒绝，未出现提升令牌或主机连接。以上均未关闭生产 P2/P4/P5/P6 门槛。历史 WFP/AppContainer guest 测试不证明产品服务或隔离浏览器可运行。详见下方 §§145–163；整体 **NOT READY**。

以下历史整改与冻结扫描段落保留其原记录时点；当时完整套件证据为 §156（Python 3.12.13 **590 passed、29 skipped**）和 §152（Python 3.11.15 **584 passed、29 skipped**）。当前完整套件见 §163：Python 3.11.15 **604 passed、27 skipped**；两条 named-pipe 互操作已在配置本机原型路径后通过。§140–143 增加的 named-pipe 原型、Python adapter 和预认证握手不关闭生产 P2/P6 门槛。

项目已有多轮源码整改与离线回归，覆盖敏感路径、配置句柄读取、任务/输出完整性、网络 deadline、下载取消、缓存清理和发布材料。SEC-23 修复后的历史 §70 Windows Python 3.11.15/3.12.13 全套各为 **485 passed, 23 skipped**；§75/79 为逐步更新的历史快照。§80 是纳入 AUD-81–85 后的历史快照（两套各 495 passed, 23 skipped）；§92 两个 Python 版本各为 510 passed、23 skipped。§100（双版本 520/23）与 §109（Python 3.11.15 520/23）是此前工作树的历史快照；§131 修复前最近一次双版本全套见 §§128–129，两个版本均为 **519 passed、23 skipped**。§132 与 §135 的后续结果取代这些全套快照；§137 加入 VBR 用例，§138 加入应用侧 client 后再跑完整套件。24 项跳过依赖本 Windows 主机不支持的 POSIX FIFO、权限、目录句柄或符号链接行为。第 57 节正式 Standard 扫描覆盖为 partial，97 个范围文件未逐项对账；第 66 节后续 Diff Scan 对冻结差异覆盖 complete。AUD-79 默认输出路径、旧快照重试保护和路径解析异常处理已整改，见第 58、60、63 节；AUD-80 媒体无效错误提示分类已整改，见第 71 节。SEC-36 Git 文件名控制字符诊断已转义。SEC-SC-01/02 的本地整改与离线验证见第 64 节；远端 CI 仍待运行。CWE-923 Chromium WebRTC UDP 出口隔离仍未解决；既有动态证据证明合成 UDP 到达本机接收端，没有证明公网送达、响应读取或服务利用。P3 的三个 pipeline 子进程突然退出/重启边界已通过离线回归（§67）；capture、download、ASR 和 media validation 使用确定性替身，不能替代实时媒体验收。固定 ASR/浏览器环境已准备；第 62、69 节记录用户提供的 315.907 秒本地 MP4（仅含 AAC 音轨）真实转写通过，P1 已通过。唯一用于 P2 的抖音链接在 AUD-83 修复后仍返回 `CAPTURE_NO_MEDIA`，不计成功；Sandbox 的 package-SID/curl/WFP 前置验证通过；§114 在交互 guest 中把 Chromium 文件 ACL 修正后，AppContainer 仍在 Crashpad CreateNamedPipe access denied 处以 STATUS_BREAKPOINT 退出。Microsoft AppContainer 命名管道 LOCAL 约束与当前 Chromium Win32 Crashpad 路径不符，是有证据支持的根因推断；没有运行页面或进程树检查（§§112–114）；P2 仍需三条不同授权视频成功捕获及进程级隔离。P4 人工听审、10 分钟以上长运行和目标 Agent 上下文检查未完成。历史 P6 快照曾核验 94 个 artifact、41 个 metadata、9 个 license、2 个 notice 和 863 个 supplemental 成员；§161–162 当前离线校验器覆盖 210 个 artifact、41 个 metadata、9 个 license、2 个 notice 和 1,149 个 supplemental 成员；§145 已补齐 40 个 NumPy wheel 的 800 个 RECORD 校验文件；Playwright 的 8 个锁定平台 wheel 含 64 个经 RECORD 核验的许可证/通知类成员（§87）。41/41 个第三方包均有 evidence-backed `licenseDeclared`（§86–87）。FFmpeg/native 组件、Rust/NumPy 构建来源及 license/notice 义务仍待确认。目标 Agent、远端 CI、项目许可证选择和发布授权尚未完成，整体 NOT READY。

**最近一次双版本全套复测（§132）：** §131 扫描器修复后的当前树在 Windows Python 3.11.15 下为 **522 passed、24 skipped**（64.54 秒），在 Python 3.12.13 下为 **521 passed、25 skipped**（336.05 秒），均无失败。两次总测试数一致；Python 3.12 的临时 junction 回归因本机权限未能创建而跳过，3.11 下该用例通过。其余跳过项依赖 Windows 未提供的 POSIX FIFO、权限、符号链接或目录句柄语义；这不代表 Linux/macOS 实机通过。§100/§109/§122 的 520/522 结果是更早工作树快照。§131 定向回归、改动文件 Ruff、敏感文件扫描和 `git diff --check` 均通过；§132 后全仓 Ruff、Agent Skills validator、两个锁文件检查、Git 可见敏感文件扫描和 `git diff --check` 也全部通过。P2 的 Sandbox 动态 WFP 复验及后续数值地址/字段白名单修正见 §110；这些本机结果不关闭 P2、P4、P5、P6 或远端/跨平台门槛。

**2026-10-11 P2 原型补充：** §112 在一次性 Sandbox guest 以 SYSTEM 验证 per-lease AppContainer package SID：同一 `curl.exe` 路径的两个 SID 可被一条动态 `FWPM_CONDITION_ALE_PACKAGE_ID` filter 分开，目标 profile 被阻断、第二 profile 放行，session 关闭后目标恢复。该原型不验证 Chromium/Playwright 或生产 service，P2 仍 OPEN/NOT PASSED。

**2026-10-11 P2 Chromium 续验：** §114 使用已连接的 ExistingLogin guest session（WDAGUtilityAccount，session 1）、网络关闭的 Sandbox 和受限标准流捕获。给 staged browser tree 的 316 个节点显式授予 profile SID 后，executable AccessCheck 错误消失；但 Chromium 153.0.8010.12 的 --version 与 --no-sandbox --version 均因 Crashpad CreateNamedPipe access denied（0x5）以 STATUS_BREAKPOINT 退出，WER 指向 chrome_elf.dll。Microsoft 要求 AppContainer 管道名使用 LOCAL 命名空间，Chromium 普通 Win32 Crashpad 源码路径未使用 LOCAL，构成强根因推断，尚未与锁定二进制的源码提交匹配。页面和进程树未运行；Sandbox 已停止。P2 不通过、URL capture 保持 fail closed。

**2026-10-11 P2 user-SID WFP 续验：** §115 在联网 Sandbox 中验证 `ALE_USER_ID` dynamic filter 可阻断随机低权限账户的 HTTPS curl，同时保留 SYSTEM 正向对照，并在 dynamic session 关闭后恢复账户联网。该 WFP 子项通过，但 Chromium 在凭据启动下过滤前后均未完成；真实交互 Sandbox headless 子项也未生成截图，日志有 DNS/GPU virtualization 警告。因此浏览器隔离仍未验证，且不能把启动失败归因于 WFP。修正后的组合结果是 `status=fail`；Sandbox 已停止、宿主策略未改。

> **本次状态更新：** 第 66 节 Codex Security Diff Scan 已覆盖其冻结工作树差异内 16 个源码/配置审查项，并复用 P2 动态证据；报告一项既有 AUD-77，其他已审查面无新增可报告问题。第 67 节补充干净安装、三阶段 pipeline 硬崩溃恢复和 Python 3.11/3.12 当前树回归；第 68 节补充 Windows 本地真实媒体 deadline、`PROCESSING_TIMEOUT` 状态与 worker 回收证据。第 73/74 节修复浏览器候选状态资源上限和缓存完整解码前的 deadline 检查；第 75/79 节记录更新阶段全量回归。第 76–78 节记录延迟候选观察、页面元数据扫描限量和真实 P2 失败复试；第 80 节记录当时纳入 AUD-81–85 后的历史全量回归，各 495 passed、23 skipped；§92 为历史 510 passed/23 skipped；§131 修复前最近一次全量复测见 §§128–129，各 519 passed、23 skipped；§131 后尚未重跑全套。后续代码及测试不属于已封存扫描摘要。§57 完整仓库 Standard 扫描仍为 partial coverage；§96 的新 Deep Scan worker 因父任务缺少 managed filesystem permission profile 未启动，没有产生扫描覆盖或“无发现”结论。任何一轮静态扫描都不关闭实时媒体质量、跨平台、Agent 宿主或发布决策门槛。

**2026-10-10 复核摘要：** §88–91 补齐 Skill 入口、锁定 wheel notice 与 SPDX sidecar 证据；§92 是历史 510 passed/23 skipped 快照；§93 将 P2 架构改为项目维护的管理员 WFP service。§96 收紧应用侧 broker lease 契约（当时 Python 3.11.15 全套 515 passed/23 skipped，目标测试 41 passed）；§100（双版本 520/23）和 §109（Python 3.11.15 520/23）是历史工作树快照；§131 修复前最近一次双版本全套见 §§128–129，均为 519/23；§131 后尚未重跑全套。当前 SBOM 共 121 package records / 137 relationships，离线证据校验为 41 packages、54 artifacts、41 metadata、9 license、2 notice、63 supplemental members。§101–104 记录管理员令牌、Sandbox 准备和只读 WFP API 能力；§109–110 记录 guest-only 动态 WFP 验收及探测器加固。服务实现、Chromium 隔离验收仍未完成。P4 人工听审与长样本、P5 新 Desktop 会话、P6 组件许可和构建来源及所有者决定仍开放，整体 NOT READY。

**此前续审 §§97–110：** SPDX 2.3 官方 schema 的哈希锁定校验已加入本地 CI 流程；review-only x64/.NET WFP 语义计划与 managed-layout 工具通过 locked restore/build，Python 跨进程 socket-share 回归通过。§100 澄清 macOS/Linux 仅是 CLI/本地媒体兼容性目标，V1 URL 捕获仅面向 Windows 11 x64，并重新跑过两个 Python 版本的 Windows 全套测试。§102 将 IPv4 精确例外拆为三个 mismatch block；§103 完成 Windows Sandbox 启用和重启；§104 修正了 guest/宿主 WFP 只读探针结论；§105 在 disposable Sandbox 验证全 IPv4 ALE_CONNECT block/release。§106 增加五规则 typed construction preview，并在一次性 Sandbox 通过 PowerShell AppID 动态验证 exact loopback/TCP permit、wrong-port/address/protocol/IPv6 loopback block、独立 curl HTTPS 正向路径和 dynamic-session cleanup；同时发现并修正 `FWP_UINT8` 权重必须使用 0–15 区间索引的问题。§107 收紧 C# 五规则精确自校验；§108 记录提权启动被执行器策略阻止及错误常量负向校验。§109 让 Sandbox smoke 从固定 SHA-256 的 C# 预览 JSON 构造五条临时规则，并完成 SYSTEM guest 动态复验；当时 Python 3.11.15 全套 520/23、Ruff 通过。§110 修复外网探测反复 DNS 可能产生的误归因：先选定并成功连接一个 IPv4 数值地址，再用同一地址验证阻断和恢复；新增逐规则字段白名单，并在内存篡改 GUID 后确认拒绝。此 guest-only smoke 仍不验证 Chromium identity、持久过滤器、公网 IPv6、broker lease、外部 provider 仲裁、service/IPC/rollback 或实际媒体捕获；预览仍没有原生生产服务。P1 私有输出元数据发现一份 4,689-byte Markdown 的 provenance 未记入验收台账；未读取正文、未将其计入证据且未删除。现有 Playwright Chromium cache 可由普通用户修改，未来服务必须使用受管理员保护的浏览器路径。P2/AUD-77 继续 OPEN/NOT PASSED，项目仍 NOT READY。

2026-10-09 独立复核发现 AUD-56（已整改）：缓存扫描与批量规划已移出 SQLite 写事务，删除前按单个候选短暂协调任务引用并复核文件身份；两个写连接和活动下载竞态已有回归。后续复核另发现 AUD-57（已整改）：已记录的本地源文件也纳入缓存保护。AUD-58 至 AUD-63 已完成本地代码整改和回归；真实 Chromium 集成仍待 P2 验收，见第 4 节及 P2 门槛。DOC-07 至 DOC-11 和 ENG-02 已修复并加入回归覆盖。

P6 固定版本上游文本对照消除了 ONNX Runtime notice 的一项误报：锁定环境文件与 v1.30.0 上游 notice 的文本在换行归一化后完全一致，原始大小/hash 差异来自 CRLF/LF；notice 到实际链接组件的映射仍未完成。CTranslate2、Rust 扩展和 PyAV/FFmpeg 仍缺与具体 wheel 哈希绑定的构建清单。详细证据和对策见第 34 节及 `docs/THIRD_PARTY_LICENSE_REVIEW.md`。

本轮曾发现重试解析失败后的任务状态、缓存恢复、并发本地重试和 claim generation 参数校验缺口；现已在任务/CLI/pipeline 路径修复，并覆盖相应回归。Skill 正文隐私规则、基础环境安装授权步骤、`--no-sync` 入口及干净安装环境隔离也已统一。修复依据和剩余集成限制见 AUD-59 至 AUD-63、DOC-07 至 DOC-09、ENG-02。

源码与计划复核新增 AUD-24 至 AUD-29。AUD-24/25/26/28/29 已完成源码整改和离线回归；AUD-27 通过实现显式 `--skip-existing` 并将首版媒体缓存/可选 turbo 范围写清，完成了计划与实现对齐。本轮整改 AUD-45，为 doctor、dry-run、转写和重试加入实际目标目录权限提示；复核重试参数时另发现 AUD-46，显式重试输出目录未写回配置快照，也已修复。CLI/doctor 定向回归 **58 passed, 2 skipped**，改动文件 Ruff 通过。真实 CDN、浏览器 DNS、ASR 质量和执行时间尚未验证。

P6 本地清单复核另发现 CI 只运行测试与 Ruff，没有项目计划要求的敏感文件检查；现已添加 [check_sensitive_files.py](../scripts/check_sensitive_files.py) 并纳入 GitHub Actions。它对 Git 可见路径拦截已知媒体/数据库/浏览器资料目录，并对不超过 16 MiB 的 UTF-8 文本整文件检查高置信度凭据模式；超限、NUL、非 UTF-8、符号链接、非普通文件或读取错误均失败关闭，诊断不会打印匹配的凭据值。该检查不是通用 secret scanner，也不扫描完整 Git 历史；发布前仍需审阅历史。本次 7,294,065 字节 artifact inventory 曾因旧 2 MiB 上限使检查失败，修复与复验见第 122 节。

复核新增 SEC-20 至 SEC-26 与 AUD-30 至 AUD-44。SEC-20 的词法 `..` 路径差异已拒绝，配置读取现在从通过权限检查的同一文件句柄解析；POSIX 使用目录句柄逐组件打开，Windows 对叶文件使用 reparse-aware handle 并从该句柄读取 ACL。SEC-21 的词典匹配工作量现在有累计预算；SEC-22 通过私有 SQLite 摘要绑定主稿；AUD-30/34/35 修复了旧配置 opt-in、本地失败重试状态和 force 快照更新。AUD-32/33 已将短链与浏览器 CONNECT 的解析、连接和响应步骤纳入 deadline，超时关闭 socket 并释放代理槽。SEC-23 已按解码帧累计时长并逐帧检查配置上限；§70 的锁定 PyAV 合成 AAC-ADTS 对照发现 `container.decode()` 遇到 `InvalidDataError` 后迭代器关闭，当前实现已改为 `MEDIA_DECODE_FAILED` 失败关闭。低报时长/编码填充及损坏包有合成证据，未知时长按解码样本计时已由 §75 覆盖；Windows VBR MP3 本地回归已由 §137 验证，Linux/macOS 与更多格式仍待验收。AUD-38 的重复全解码已通过验证身份交接整改并有回归，长媒体性能基准仍待授权样本。AUD-10 使用有界 JSON IPC worker；下载阶段现在受共享 deadline 限制，重试恢复原超时值，显式覆盖会更新快照。SEC-24 和 AUD-44 对敏感配置、URL 清单及词典 FIFO 使用非阻塞打开并按文件类型拒绝。SEC-25/26 的 Python 子进程已启用 safe-path，影子模块回归通过。AUD-39 统一 downloader 校验类型；AUD-43 现先将时间轴路径和摘要写入任务库，再原子发布；完成、skip、crash recovery 都验证 sidecar。旧 schema 中 completed/writing 且时间轴设置未知的任务 fail closed。上一轮结构化扫描的 5 项发现和此前 28 项 Diff Scan 的 1 项发现均绑定各自启动快照。2026-10-09 又完成一轮正式 Codex Security Diff Scan（Scan ID `8537ef61-e6e5-4b6a-8fc7-f162382c098a`，快照 digest `aa0314f296588ea1f7b0944b5e02167cfac1d57dea4fe9427d84f6c37f88e84a`）：28/28 个变更审查项完成复核，未发现新的可报告安全候选，扫描器 coverage 对该冻结差异为 complete。该结果不覆盖运行时行为和产品验收；POSIX 扩展 ACL、真实媒体/浏览器、Agent 宿主、远端 CI 等仍待验证。

`retry-failed` 为新任务恢复非正文配置快照；旧任务无有效快照时默认跳过，只有显式 `--use-current-defaults` 才按当前配置排队。AUD-45 已将权限提示应用到配置目录和本次实际输出目标；AUD-46 已确保显式重试输出目录覆盖值写回快照。AUD-54/55/59–69 与 SEC-29 的本地整改均有回归覆盖；此前 Windows Python 3.11.15 和 3.12.13 全套 376/20、384/20、385/20 均为阶段历史快照。第 16 节记录的 387/20 已被第 17 节的 393/20 取代。POSIX 扩展 ACL、真实媒体格式、SEC-15 其他 pathname-only/TOCTOU 边界、SEC-16 fallback、SEC-18 的具体 Hub cache 信任边界、AUD-21 多机/第二账户集成仍待验收。SEC-17 的本地真实模型推理已由第 62、69 节样本验收；SEC-14 需目标 Agent 宿主验证。P1 本地真实转写已通过，但真实 Chromium/抖音媒体捕获仍未成功；跨平台远端 CI、目标 Agent 新会话和许可证决定仍未完成。缓存需用户主动清理。项目仍未达到真实产品与发布门槛。

### 1.1 当前未完成项与对策（按项目阶段排序）

| 优先级 | 当前证据 / 问题 | 完成对策 |
|---|---|---|
| P1，本地真实转写 | **已通过**：用户提供的 MP4 时长 315.907 秒，容器只有 AAC 音轨、没有视频流；真实 ASR 成功，输出 4,658 bytes，耗时 302.50 秒（第 62 节）。该样本满足本地中文音频门槛，不算 P2 视频捕获 | P1 结果已写入 `P1_REPORT.md` / `BENCHMARK.md`。P4 仍需人工抽听，并完成 10 分钟以上长运行与目标 Agent 隐私检查。默认输出已移至 `<data_dir>/output`，不安全/未知权限 fail closed（第 58 节） |
| P2，真实抖音捕获与网络边界 | Playwright 1.63.0/Chromium 已安装。获授权链接在 AUD-83 延迟观察修复后重试仍返回 `CAPTURE_NO_MEDIA`，不计入计划要求的三条成功真实视频捕获；13 个第三方页面资源主机仍在 allowlist 外。AUD-77 动态测试还确认 Chromium 在策略参数存在时仍能向本机 UDP 接收端直连。只靠仓库内代理/启动参数无法证明操作系统级出口隔离 | §82 的外部沙箱方案已在 §93 复核后取代，当前架构方向为项目维护、管理员安装的 Windows WFP service（先支持 Win11 x64）；应用无 broker 时的 fail-closed gate 已有定向回归。服务、安装器和可信 IPC 尚不存在；仍需构建并在可回滚 Windows 测试环境动态证明完整进程树与规则有效。保持第三方 host 默认拒绝；为三条不同且获授权的真实视频取得成功端到端捕获，失败尝试不计数，须继续提供候选链接直到三次成功。隔离策略必须覆盖 Chromium 子进程完整生命周期，仅允许到精确本机代理端点的 TCP，并阻断 IPv4/IPv6 直连、UDP、loopback 与 LAN；验证阻断和代理 HTTPS 正常后再关闭 AUD-77。不得通过放宽 allowlist 替代隔离 |
| P3，离线 pipeline 恢复 | **pipeline 突然退出/重启已通过**：在 `downloaded`、`transcribing`、`writing` 三个已提交状态边界分别用子进程 `os._exit(86)` 硬退出；新进程使用同一任务库恢复并完成，且没有重新捕获/下载（第 67 节）。capture、下载、ASR、媒体校验为确定性替身，不代表实时媒体验收 | 保留真实进程崩溃恢复回归；继续单独验收真实媒体与浏览器链路，不用模拟结果替代实时媒体验收 |
| AUD-10，Windows 真实处理超时 | **本机部分通过**：用户样本在默认流水线下以 45 秒 processing deadline 运行，实际 CLI 墙钟 46.49 秒；任务以 `PROCESSING_TIMEOUT` 结束，worker PID 被观察到并在 CLI 退出后消失，输出、media-cache、`.part` 文件和 stderr 均为空。PyAV worker 报告音轨时长 315.907 秒，固定 faster-whisper 模型可加载 | 在 macOS/Linux 重复真实 worker 的超时/回收检查；用授权远端媒体单独验证下载 `.part` 清理。该次本地验收没有阶段计时点，不能拆分模型加载与推理耗时 |
| AUD-81，浏览器媒体候选状态无界 | **已整改并通过回归**：单页最多保留 16 个音频和 16 个视频候选；URL 和候选元数据长度均有限制 | §73 时 `tests/unit/test_p2_capture.py` 为 20 passed；当前 capture 定向组 24 passed、§80 双版本全套均通过。此本地限制不关闭真实捕获及 AUD-77 出口隔离门槛 |
| AUD-82，缓存完整解码前的 deadline 复查不足 | **已整改并通过定向回归**：缓存路径属性检查耗时后，在调用完整媒体解码前再次检查共享 deadline | `tests/unit/test_p2_downloader.py` 为 54 passed、1 skipped；确定性时钟回归覆盖目录检查期间期限耗尽。全套复验另行记录 |
| AUD-83，页面延迟媒体响应可能被过早判为无候选 | **已加短窗口**：无候选时，在共享 deadline 内以 200 ms 轮询响应事件，最多额外等待 2 秒；出现获准候选即停止 | `tests/unit/test_p2_capture.py` 覆盖延迟 900 ms 到达的音频响应；获授权真实页面复试仍返回 `CAPTURE_NO_MEDIA`（§78），未证明该问题是原失败原因。§79 全量套件通过；其他授权视频和出口隔离仍需验收 |
| AUD-84，浏览器页面元数据与登录提示文本未限量 | **已整改并通过回归**：标题/作者/发布日期按字段限长，DOM 文字只遍历有限文本节点并最多返回上限加 1 字符，属性值在浏览器端截断；登录提示扫描只返回布尔值，不把完整 body 传回 Python | `tests/unit/test_p2_capture.py` 24 passed，Ruff 通过，§79/80 全量套件通过。登录词扫描限于前 16,384 个字符/4,096 个文本节点，深埋提示可能仅由 URL/显式登录控件发现；真实浏览器交互边界仍需验收 |
| AUD-85，缓存命中扫描先排序并物化全部候选 | **已改为流式遍历**：缓存目录逐项枚举，每项先检查 cancellation 和共享 deadline，再筛选当前视频/媒体类型的前缀；不再先排序构造完整列表 | `tests/unit/test_p2_downloader.py` 新增慢目录迭代器 deadline 回归；定向组 55 passed、1 skipped，§80 两个 Python 全套各 495 passed、23 skipped。目录枚举的单次 OS 迭代调用仍受文件系统响应约束，非-Windows 平台需要 CI 验收 |
| P4，部分完成 | 938.968435 秒本地音频样本、默认模型文本校对稿、时间轴和试听片段均已存在；尚无至少三处人工对照听审记录，也无 fresh Desktop 数据流/隐私验收 | 对照至少三段原音频并记录漏词、增词、术语与不确定项；在新 Desktop 会话核验默认模型输入、stdout/stderr、Agent 摘要与保存稿的数据流，不复制转写正文 |
| AUD-65，动态依赖空间无法精确预估 | setup 仍无法准确估算 uv 环境、缓存和 Chromium 的平台相关体积；已调整安装顺序，并在 uv 与 Chromium 完成后、模型下载前复查模型卷至少 2 GiB | 继续把未知组件的空间值作为快照提示，不声称容量保证；真实授权安装后记录各目标卷消耗。若空间不足，模型下载前停止，避免继续占用模型目标卷 |
| SEC-15，安全整改部分完成 | 目录/文件创建路径已局部加固；SQLite、Playwright、模型等第三方接口仍按路径名工作。当前未证实跨账户利用 | POSIX 使用 dir-fd 相对创建并在同一 fd 上核验；Windows 使用受保护 DACL 创建并复核目录/文件句柄身份。当前 Windows 回归通过；POSIX 实机、Windows 多账户和第三方 pathname-only 边界仍待验收 |
| SEC-27，映射网络盘识别 | **源代码已整改并通过 Windows mock 回归**：`GetDriveTypeW()` 拒绝 `DRIVE_REMOTE`，对未知/无根盘类型 fail closed；本机 C:、D: API 结果均为固定盘，当前没有真实映射盘可供集成验证 | 在有映射盘的 Windows 环境确认诊断结果；UNC/device namespace 仍按原规则拒绝 |
| AUD-52，安全创建失败后留下新对象 | **已加入失败提示与排障说明，按安全策略保留残留**：对象仍可能存在，但错误会告知并提醒先核对身份；Windows 与 POSIX 回归均有残留提示断言 | 不做有 name-based 竞态的通用自动回滚；后续若做 Windows 文件句柄绑定清理，必须失败关闭。POSIX 分支已加断言但本机为 Windows，仍待 Linux/macOS CI 运行 |
| AUD-53，崩溃恢复期间媒体校验占用 SQLite 写锁 | **事务锁问题已整改；恢复阶段全媒体解码的时限残留由 AUD-76 修复**：校验从写事务移出，提交前比对原任务快照；恢复时快速检查文件完整性，实际解码延后至已领取的处理路径 | 两连接写入、任务续租和延迟校验回归通过；真实长媒体和跨平台 SQLite 集成仍待验收 |
| AUD-56，缓存清理长时间占用 SQLite 写锁 | **已整改**：目录扫描/计划在事务外完成；每个候选仅在短事务内复查任务引用并做一次身份绑定删除；两连接并发回归通过 | Python 3.11/3.12 本轮全套均通过；极慢的单次文件系统删除仍可能延长单个事务 |
| AUD-57，缓存清理可能误删本地输入 | **已整改**：TaskStore 查询并保护所有已记录的 local_path，含已完成任务；新增回归 | app media-cache 是程序管理目录；尚未登记为任务、但由用户自行放入且恰好匹配下载器命名的文件无法仅凭名称识别为原始输入。建议不要把未登记的源文件放入该保留目录 |
| AUD-58，浏览器流量边界（P2 集成待验收） | **代码已加固**：context 请求路由在建页前注册、阻断 Service Worker、校验 WSS 域名和公网解析、代理设置 `bypass="<-loopback>"` | Fake Playwright/proxy 回归 21 passed；真实 Chromium、popup、loopback/链路本地和抖音 WSS 集成仍需 P2 授权验收 |
| AUD-59，远端重试解析失败后留在 pending | **已整改**：未认领的 pending retry 在 URL 解析失败时按 task/generation 条件恢复 failed；worker 写入要求 claim generation | CLI/task/pipeline 回归覆盖解析失败状态回退和并发认领保护；相关回归组 110 passed，Ruff 通过 |
| AUD-60，失败重试未直接从任务缓存恢复 | **已整改**：claimed retry 先验证任务记录的 `media_path`，有效缓存直接进入 downloaded，缓存无效才回到捕获/下载 | pipeline 回归覆盖缓存恢复和无效缓存回退；相关回归组 110 passed，Ruff 通过 |
| AUD-61，并发本地重试产生误报失败 | **已整改**：本地 retry 使用原子 claim；竞争进程重新读取任务状态，已推进的任务按状态返回 skipped/locked | 两个 CLI 并发重试和状态变化回归；相关回归组 110 passed，Ruff 通过 |
| AUD-62，TaskStore claim generation 可省略 | **已整改**：有 worker ID 的状态写入必须带 claim generation，旧 generation/缺少 generation 均不能通过 owner fencing | tasks/pipeline/downloader/CLI 定向回归覆盖旧 worker 与同 ID 复用；相关回归组 110 passed，Ruff 通过 |
| AUD-63，Python 3.12 全套测试时间戳敏感失败 | **已整改**：缓存竞态 fixture 显式回拨 mtime；媒体身份测试从校验所用句柄采集身份，避免事后路径 stat 的 ctime 竞态 | 整改时 Windows Python 3.11.15 和 3.12.13 全套均为 356 passed, 20 skipped；当前结果见第 2 节。缓存竞态及句柄身份用例各重复 5 次通过。POSIX 专属跳过项仍需相应平台验证 |
| DOC-07，Skill 对逐字稿正文处理规则不一致 | **按后续用户要求更新**：授权后由调用 Agent 的当前默认模型校对正文并生成独立 `.reviewed.md`；正文可能发送给模型服务商，Skill 须先说明数据流。CLI JSON/聊天/诊断仍不回显正文。 | 原先的“禁止 Agent 读取全文”规则已由 2026-10-10 产品要求取代；当前 Skill、README、架构与安全文档按新边界同步。实际样本记录见 §72；新宿主验收仍在 P4/P5 跟踪。 |
| DOC-08，首次 Skill 调用可能隐式同步安装 | **已整改**：首次运行前说明基础 sync 的网络与文件写入影响并取得用户同意；初始化后的 CLI 命令使用 `--no-sync` | SKILL、INSTALL 和中英文 README 已同步更新；固定版 Agent Skills validator 通过 |
| DOC-09，wrapper 与部分 CLI 示例仍可能隐式同步 | **已整改**：Windows/Unix wrapper、CLI reference、README 和开发命令均加入 `--no-sync` | 新增静态回归扫描 Skill/安装文档/README/wrapper 的锁定 `uv run` 命令；Windows Python 3.11/3.12 全套回归通过 |
| ENG-02，干净安装检查可能写入调用者指定的虚拟环境 | **已整改**：子进程环境现将 `UV_PROJECT_ENVIRONMENT` 固定在复制的 Skill `.venv` 中 | 新增环境隔离单元回归；设置外部目标环境变量后，仓库外离线安装冒烟通过且外部路径未创建 |
| DOC-10，CI job 名称暗示整个流程离线 | **已整改**：job 改名为 `ci-checks`，验收材料说明冷 runner 的依赖安装可访问包索引，lint/test 进程离线 | 只调整名称和说明，不改变 CI 执行方式；远端矩阵尚未运行 |
| DOC-11，安装材料未标明已验证的 uv 版本 | **已整改**：中英文 README、INSTALL 和 Skill metadata/instructions 指出 CI 当前固定 uv 0.12.7，旧版本未经验证 | 根据当前 CI pin 和本机 `uv 0.12.7` 记录可复现基线；没有宣称更早版本可用 |
| AUD-54，恢复后旧 worker 仍可改变任务状态 | **已整改**：pipeline 丢失 heartbeat 会取消该任务处理，TaskStore worker 状态写入强制 claim generation，见 AUD-62 | 旧 worker、worker ID 重用、claim recovery 与子任务取消回归通过；Windows Python 3.11/3.12 全套均通过 |
| AUD-55，Python 3.12 Windows 缓存删除身份不匹配 | **已整改并通过本轮全套门禁**：Python 3.12+ Windows 使用 FILE_ID_INFO 的 64 位 volume serial 与 128 位 file ID；3.11 保留旧 API 路径 | 缓存清理定向回归及 Python 3.11/3.12 全套均通过；远端 CI 尚未运行 |
| SEC-28，敏感文件扫描遗漏通用 cache/ 目录 | **已整改并通过回归**：扫描器现在按路径拒绝任何 Git 可见的 `cache/` 目录内容，不依赖文件扩展名/文本解码 | 离线扫描器回归通过；发布前仍须人工审查完整 Git 历史 |
| AUD-45/AUD-46，输出隐私诊断与重试快照 | 源码现检查配置目录、显式目录及重试快照目录；显式 `retry-failed --output-dir` 现在也持久化为该任务的新输出路径 | 已完成本机实现和回归；在 macOS/Linux 及 Windows 多账户 ACL 环境验证共享/未知路径诊断和继承行为，保持对已有目录只提示、不擅改 ACL |
| P5，部分完成 | canonical Skill 与新建的 repo-scoped Codex 入口均通过固定版 validator；当前会话在入口创建前启动，尚无新会话发现/调用证据 | 在新 Codex Desktop 会话确认技能列表包含该 Skill，显式触发并记录桌面工具轨迹；确认只返回状态/路径。若调用真实媒体，仍须遵循 P1/P2 授权门槛 |
| P6，尚未发布就绪 | 当前无 remote、无远端 CI/GitHub 安装记录、无项目 LICENSE 决定。41 个锁定第三方发行物均有 artifact identity 记录；当前离线 verifier 核验 54 个 artifacts、41 个 metadata、9 个 license、2 个 notice 和 63 个 supplemental 成员（Playwright wheel 证据见 §87；第二个 ONNX notice 见 §89）。41/41 个第三方包有 evidence-backed `licenseDeclared`（有效作者表达式、固定审阅映射或锁定发行物内许可证文件；`python-dateutil` 的精确锁定 sdist LICENSE 支持 BSD-3-Clause，§86）。项目包及所有 `licenseConcluded` 保持 `NOASSERTION`。ONNX Runtime notice 到链接组件映射、CTranslate2/Tokenizers/Ruff/PyAV 原生或构建 BOM 证据仍未完成；另有 65 个安装包 license/notice 候选文件的 RECORD 哈希一致 | 所有者确认交付范围、仓库归属/名称/可见性、项目许可证和远端授权；取得精确 wheel build manifest/native/Rust/FFmpeg 组件材料并将 notice 映射到实际组件，再配置 remote、运行矩阵 CI 并验证远端干净安装。证据清单字节与声明对应关系由离线 verifier 和 SBOM generator 强制核验；这些记录不构成分发批准 |
| 安全覆盖 | 最新差异扫描 `81745f42-fe5b-4151-845c-95c70da451ee` 覆盖冻结差异中的 16 个源码/配置审查项，报告 1 项低严重度 AUD-77；该差异审查 coverage complete。更广的 §57 Standard 扫描仍为 partial | 实施并动态验收 AUD-77 进程级 egress 隔离。完整仓库覆盖、运行时和产品验收仍需单独完成；扫描后脚本/文档改动见 §66 定向回归说明 |
| AUD-47，代理隧道转发反压 | **已修复并本机回归**：非阻塞双向转发有 256 KiB 缓冲上限和 60 秒写等待上限；目的端停读后关闭隧道并释放槽位 | Linux/macOS 与真实 Chromium CONNECT 集成仍待平台验收；无新增代码对策 |
| AUD-48，批量转写 Ctrl+C | **已修复并本机回归**：取消信号关闭活动下载连接、打断退避、取消待执行任务，并尽快关闭捕获/处理子进程；任务记为可重试的 `CANCELLED` | 有 deadline/取消的 DNS 现由 AUD-50 子进程处理并在退出时终止、回收；不带 deadline/取消的直接 helper 调用仍同步使用系统 resolver。真实 DNS、Chromium 与跨平台下载中断仍待集成验证 |
| AUD-49，sidecar 崩溃恢复覆盖 | **已补齐回归**：先持久化预期 sidecar 路径/摘要，再模拟成功发布、缺失和摘要不符；只有绑定内容有效时才完成恢复 | Linux/macOS 文件系统行为仍待平台验收；无新增代码对策 |
| AUD-50，DNS 查询线程耗尽解析名额 | **源码已整改并通过回归**：有 deadline/取消的解析由隔离子进程执行，超时或取消后强制停止并回收；两个阻塞 worker 取消后名额可复用 | 无 deadline/取消的直接 helper 仍同步调用系统 resolver；当前 CLI 网络路径提供时限。需在真实 DNS、Chromium 与 POSIX 平台集成中验证进程终止语义 |
| AUD-51，Windows 权限诊断误报 | **本机已修复并回归**：foreign ACE 仅授予目录遍历/同步权限时不再判为可读取或可修改；读取、写入、删除及通用读取权限仍拒绝 | `%USERPROFILE%\Transcripts` 当时报告 `ok`（只检查最近现存父目录，未创建目标）；旧 D: 工作区路径的 ACL 当时为 `unsafe`，第 58 节已将其移出隐式默认。需在更多 Windows ACL 组合与多账户环境验证继承/有效权限语义 |

## 2. 验证结果

| 检查 | 结果 | 适用范围与限制 |
|---|---|---|
| P0 CLI/doctor（安装前历史状态） | **符合预期** | 安装前 `--help` 返回 0；`doctor --json` 报告 `setup_required` 且没有创建目录或下载。当前安装后状态见第 17 节 |
| Windows Python 3.11.15 全套 pytest（§132，§131 修复后） | **522 passed, 24 skipped** | 用时 64.54 秒；跳过项依赖 POSIX FIFO、权限、symlink 或目录句柄语义，不代表 Linux/macOS 实机行为 |
| Windows Python 3.12.13 全套 pytest（§132，§131 修复后） | **521 passed, 25 skipped** | 用时 336.05 秒；另有临时 junction 用例因当前进程权限无法创建而跳过。跳过项不代表 Linux/macOS 实机行为 |
| AUD-76/77 定向 pytest | **通过：4 passed** | 当前工作树；覆盖 stale media recovery 延迟解码与损坏缓存回退、Chromium 策略参数和拒绝调用方覆盖。另已对锁定 Chromium 做本机 STUN UDP 动态验收，结果显示参数未阻止直连；AUD-77 未解决 |
| `tests/unit/test_tasks.py` | **通过：37 passed, 1 skipped** | 当前工作树；验证 TaskStore 状态机、恢复与并发行为。symlink 用例因本机文件系统能力跳过 |
| AUD-64–66 定向 pytest | **通过：107 passed, 3 skipped** | 覆盖不可信 fallback 输出 containment、依赖安装后模型空间复查、由控制字符扩大的真实术语 archive frontmatter、超限元数据在发布前拒绝。跳过为本机 symlink/FIFO 限制 |
| SEC-15 独立复核及本轮整改 | **SEC-27 源码已整改；AUD-52 已加入提示并按私有残留策略处置** | 映射盘拒绝、unknown 诊断、失败创建残留提示有 Windows mock 回归；本机 GetDriveTypeW 将 C:、D: 识别为固定盘。没有真实映射盘可做集成验证，POSIX 消息行为未在本机实测 |
| 配置、存储、doctor 与 CLI 定向 pytest | **通过：92 passed, 14 skipped** | 覆盖 Windows 创建/目录身份、配置句柄读取、doctor 与 CLI 路径检查；POSIX dir-fd、symlink、FIFO 和替换回归在本机跳过 |
| 最新全仓 Ruff | **通过** | 本轮复跑 `uv run --project .\skills\douyin-transcript --locked --no-sync --group dev ruff check .\scripts .\skills\douyin-transcript\src .\skills\douyin-transcript\scripts .\tests` 返回 `All checks passed!` |
| Skill 仓库外干净副本安装 | **通过** | `scripts/check_clean_skill_install.py` 在独立副本执行 locked no-dev 安装，确认 import 来自副本并通过 `--version`、已解析/校验的 dry-run JSON 和 `doctor --json`；13 个定向测试与本地端到端 smoke 通过（第 66 节）。远端矩阵/仓库安装尚未运行 |
| AUD-32/33 网络定向 pytest | **通过：26 passed** | 覆盖多跳共用 deadline、阻塞 DNS 超时、CONNECT 超时关闭及代理槽位恢复；未访问网络 |
| `uv lock --project .\\skills\\douyin-transcript --check` | **通过** | 锁文件和项目依赖元数据一致 |
| `git diff --check` | **通过（跟踪文件）** | 仅有 Git 的 LF/CRLF 转换提示；命令不检查未跟踪文件 |
| `uv run --project .\skills\douyin-transcript --locked --no-sync --group dev agentskills validate .\skills\douyin-transcript` | **通过** | 固定版本标准校验器返回 `Valid skill` |
| `python scripts/check_sensitive_files.py` | **通过（§122 当前树复验）** | 扫描 Git 可见路径；对最多 16 MiB 的 UTF-8 文本整文件检查高置信度凭据模式。超过上限、NUL、非 UTF-8、symlink、非普通文件或读取错误均失败关闭；不打印匹配值。只检查当前树，不代替完整历史审查或通用 secret scanner |
| `setup` 确认前来源/目标披露 | **通过（本机回归）** | 确认前显示模型 repo/revision、锁文件 registry、uv 环境、HF_ENDPOINT 和模型/浏览器目标；自定义源只显示 scheme/host/port。新增测试确认 HF_ENDPOINT 覆盖值可见且用户、密码和 query token 均脱敏 |
| `setup` 磁盘预检（AUD-65） | **已加模型下载前复查；组件空间仍是快照** | Chromium 安装现在先于模型下载；uv 和 Chromium 完成后重新检查模型目标卷，低于 2 GiB 或无法查询时停止模型下载。uv/Chromium 的实际空间需求随环境变化，未构造固定容量保证 |
| 输出完整性前置元数据解析（AUD-66） | **已修复并通过回归** | serializer 与 `_frontmatter()` 共用 4 Mi 字符上限；解析器在该边界内逐行找结束分隔符，生成端超限会在原子发布前拒绝。控制字符扩大的真实术语归档测试及超限无文件发布测试均通过 |
| 初始提交历史检查 | **通过（初始提交 1 个、15 个路径）** | 对初始化提交 `3e06080` 的文件路径和高置信度凭据模式检查未发现敏感文件名或命中。实现检查点 `f298f11` 的当前 Git 可见树提交前已通过敏感文件扫描；完整历史仍须在发布前复核。当前无 remote，因此没有远端分支/历史可查 |
| 新增功能差异复核 | **五项源码整改通过离线回归；一项通过范围对齐** | AUD-24/25/26/28/29 已修改；AUD-27 的 `--skip-existing` 已实现，V1 明确保留媒体缓存并通过 `cache clean` 管理；可选 turbo 档推迟到真实模型验收后 |
| 上一轮结构化安全扫描与修复复核 | **已完成：5 项源码发现（1 项中危、4 项低危），coverage partial** | 涵盖配置路径检查/读取不一致、术语匹配 CPU 工作量、远端输出关联真实性、短链 deadline、浏览器代理二次 DNS deadline。SEC-23 源码已改为计数实际解码帧，但真实畸形时长样本与损坏帧兼容性仍待确认；项目估算 75 个文件，本轮没有逐文件覆盖全仓。扫描工具提示扫描期间工作树变化，结构化报告对应启动时快照。 |
| 上一轮 Codex Security Deep Scan | **未启动；不能视为无发现** | 当时扫描协调器拒绝启动只读 worker，原始原因是缺少 managed filesystem permission profile。此结果仅说明 Deep Scan 未运行；本轮另行成功完成了工作树差异扫描。 |
| 上一轮 Codex Security Diff Scan（历史快照） | **完成：28/28 项变更文件全文件复核，发现 1 项中危；coverage partial** | Scan ID `422a6e6d-f1d0-45c7-8bba-d1f3a739f489`，快照 digest `895ffbacea7923b7dfd387f768b7131c7c88fe34e1b786724c20c9f48b41b7d3`。该快照不包含之后的 SEC-25/26 修复。 |
| 上一轮 Codex Security Diff Scan（2026-10-09 历史快照） | **完成：6 项安全敏感源码/配置审查，0 findings，coverage complete** | Scan ID `3ecab5a0-71ce-4dc8-a614-2b3af2e2eadb`，快照 digest `codex-security-snapshot/v1:sha256:5774937a34e1c76184f73e98fbbeb132b47410000633a2a875c5bcdec00449a5`。本次为静态、冻结差异扫描；未运行测试或动态验证，不替代真实媒体、浏览器、Agent 宿主、POSIX ACL、远端 CI 或全仓验收。 |
| 前次 Codex Security Diff Scan（2026-10-09） | **完成：6 个变更源码项及相关测试差异，0 个候选项，coverage complete** | Scan ID `06b2789a-8835-4dfb-a214-4ac550fcaba0`，快照 digest `codex-security-snapshot/v1:sha256:d9865be8ca3153ecaa2beab9f38b5c04c24c5435adc59291b60e1281f1fd77dd`。静态冻结差异扫描；未运行测试或动态验证。详细记录见第 33 节。 |
| 仓库外独立干净副本安装 | **最新复测通过** | 从 Skill 副本排除源 `.venv`、pytest/Ruff 缓存，在 `%TEMP%` 创建显式独立虚拟环境；`UV_OFFLINE=1` 锁定 no-dev 安装通过。从仓库外验证导入路径来自副本，`--version` 和直链 `--dry-run --json` 通过。未下载 ASR/浏览器依赖，dry-run 未访问媒体或创建运行时 data/output 目录 |
| `doctor --json`（安装前历史快照） | `setup_required`；敏感数据路径权限 `ok` | 当时缺 faster-whisper、PyAV、模型、Playwright、Chromium；该状态已由第 17 节的用户授权 setup 取代 |
| `doctor --json`（用户授权 setup 后） | **最近复验 `ready`；本地转写与 Douyin URL 能力均就绪** | setup 后历史检查曾用私有 data directory 和 `%USERPROFILE%\Transcripts` 输出覆盖；第 58 节复验确认当前隐式输出为 `<data_dir>/output`，data/output 权限状态均 `ok`。历史 D: 工作区路径 ACL 不安全，但已不再作为隐式默认输出 |
| GitHub Actions 矩阵 | **未运行** | 工作流已添加，但没有远端 GitHub 运行记录 |
| 真实本地媒体与抖音链接 | **部分证据，未通过** | 无本地媒体文件和真实 ASR；修复 Playwright 请求类型判定后，一条授权精选页的主文档 HTTP 200，但 CLI 新尝试返回 `CAPTURE_NO_MEDIA`。13/14 个观察到的页面资源主机不在 allowlist，未生成媒体文件。其余两条 URL 未提供 |
| 前次续审全套本地复测 | **通过：308 passed, 17 skipped** | 此为 AUD-47/48 修复前快照；使用离线锁定依赖与 profile 下新建的 pytest 临时目录。跳过项是 POSIX 专属行为和本机 symlink 创建受限用例 |
| 最近一次 Codex Security Deep Scan 尝试 | **未启动** | 协调器返回“the parent must provide a managed filesystem permission profile”；没有扫描工件，不能据此推断无漏洞。既有 28 文件 Diff Scan 不等价于全仓 Deep Scan |
| 本次定向源码复核与 AUD-45/AUD-46 修复 | **通过：58 passed, 2 skipped；Ruff 通过** | 检查 pipeline、ASR/worker、URL/下载、浏览器捕获与代理、输出命名及 CLI；回归覆盖 doctor 显式目录、dry-run/转写 JSON、文本警告、重试快照目标和显式重试覆盖持久化。两个跳过项为 Windows 不支持的 POSIX FIFO 用例；未执行真实媒体/网络或 POSIX ACL 集成 |

## 3. 上轮问题状态

本节部分问题的测试数量记录的是整改完成时的历史快照；P2/AUD-73 阶段的 393/20 见第 17 节，P3 和 SPDX 回归后的 399/20 见第 30、32 节。第 36 节所录 404/20 是当时快照；后续 AUD-76/77 后的当前树全套为 407/20，见第 38、40 节。此前 303/17、308/17、315/17、316/17、323/17、325/20、331/20、334/20、337/20、340/20、356/20、366/20、375/20、376/20、382/20、384/20、385/20、387/20、389/20 均为对应阶段历史快照。

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
| AUD-17 50 条混合批次 | **已补齐当前树回归** | `tests/unit/test_pipeline.py::test_fifty_item_mixed_batch_bounds_downloads_and_keeps_asr_serial` 覆盖缓存、失败、重复、下载并发上限、串行 ASR、输出与任务计数；本轮定向测试通过。历史记录缺少可复核代码的问题已由 AUD-75 纠正。 |
| AUD-18 发布文档 | **本地材料已补齐；真实验收待做** | 新增英文 README、CHANGELOG、SECURITY、独立 Skill 安装说明和示例配置；P1/P2/benchmark 文件目前是 `NOT VERIFIED` 模板，许可证和外部验收证据仍未完成。 |
| AUD-22 setup 来源与目标披露 | **已整改并覆盖回归** | 确认前显示锁定模型 revision、软件包 registry、可见自定义源主机、HF_ENDPOINT 主机、uv 环境及模型/浏览器目录；新增测试确认 HF_ENDPOINT 覆盖及凭据脱敏。 |
| AUD-23 setup 磁盘空间预检缺失 | **已整改** | 确认前显示各安装目标卷可用空间；模型卷低于 2 GiB 或无法查询时 fail closed。低空间回归确认不提示授权、不安装、不下载、不建数据目录。 |
| AUD-24/25/26/28/29 | **已整改并通过离线回归；真实服务待验收** | 分别覆盖媒体时长、缓存字节/时限、浏览器 DNS deadline、候选失败码摘要和通用 ASR 默认提示词。AUD-27 已通过实现显式跳过选项并对齐 V1 媒体缓存/可选 turbo 范围关闭。 |
| SEC-19/20 配置路径及句柄读取 | **源码整改；POSIX 与多账户集成待验收** | 拒绝 `..` 组件；POSIX 从已打开目录 FD 逐段 `O_NOFOLLOW` 打开，Windows 对叶文件以 reparse-aware handle 校验 ACL 并从同一 handle 读取。配置解析消费完成校验的同一描述符。 |
| SEC-15 敏感目录检查与按路径名使用的竞态 | **创建边界已缩小；跨账户攻击未证实，集成待验收** | `ensure_private_directory()` 在 POSIX 使用目录 fd 相对逐段创建/打开并核对对象身份；Windows 新文件在 `CREATE_NEW` 时设置私有 DACL，并通过句柄核验文件和目录身份。`TaskStore` 已保留数据库路径的词法别名。SQLite、Playwright、模型下载、下载器缓存和输出验证仍有 pathname-only 检查/使用边界。当前 Windows 文件系统不允许创建 symlink 的用例会跳过。POSIX mode 与 Windows ACL 用于阻止不可信账户替换受保护祖先；同 UID、管理员/root 和非标准 ACL 不在保证范围。详见下方限制与对策。 |
| SEC-21 术语匹配资源消耗 | **已整改并通过定向离线回归** | 前缀树匹配保留最长有效规则和 ASCII 边界；规则/Trie 大小有硬上限，正文与时间轴共用 2,500 万次转换预算。 |
| SEC-22 输出关联完整性 | **已整改并通过定向回归；文件句柄集成待后续评估** | pipeline 和 Markdown writer 不再按公开 `video_id` 复用既有文件；任务库保存本次渲染预期字节的 SHA-256，完成/跳过/恢复均验证私有摘要和任务关联。旧 schema 没有摘要的完成记录需要 `--force` 重建。 |
| SEC-23 媒体时长上限与解码完整性 | **真实 AAC/MP4、合成 AAC-ADTS 与 Windows 合成 VBR 已验；跨平台及更多格式仍开放** | 用户提供的 315.907 秒 AAC/MP4 由 PyAV worker 完整解码，启动加完整校验耗时 0.953 秒（§68）。§70 的锁定 PyAV 合成 AAC-ADTS 显示容器声明略短于解码帧时长，校验器按解码时长处理；中间包损坏会导致解码器提前结束，当前校验器改为拒绝。未知时长按解码样本计时有回归并进入 §75 全套。§137 在 Windows 用锁定 PyAV/libmp3lame 生成并核对了真实 VBR MP3 帧码率，再由产品校验器完整解码；Linux/macOS 和更多封装/编解码器仍待验收。 |
| AUD-38 完整解码重复扫描 | **源码整改并通过回归；真实性能基准待授权媒体** | 默认本地和新下载远端任务现在各做一次完整时长校验；校验结果携带解码句柄的文件身份交给 ASR，ASR 核对身份后从打开的文件对象读取，不再重复预检。缓存恢复路径也只做一次当前校验。真实长音频 CPU/总耗时仍未测量。 |
| AUD-10 媒体下载/预检/ASR 墙钟超时 | **Windows 本地真实媒体超时部分通过；POSIX 与远端下载清理待验收** | 第 68 节使用用户样本与真实 PyAV/faster-whisper 环境运行 CLI：45 秒 deadline 后任务记录 `PROCESSING_TIMEOUT`，worker PID 随 CLI 退出而消失，且没有输出或临时残留。该本地文件路径不覆盖远端下载 `.part` 清理，macOS/Linux 尚未测试。 |
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

### SEC-17：显式模型路径校验后仍把原始路径交给 ASR（已整改；旧快照的真实推理限制已关闭）

- **证据与整改：** `LocalASR.model_path` 现在先解析 canonical path、校验固定 revision/provenance，再把同一路径保存并传给 `WhisperModel`；不再校验 canonical 后回退加载调用方 alias。测试模拟 alias 校验后目标切换。模型/ASR 定向测试 **18 passed, 1 skipped**，Ruff 通过。
- **后续证据：** 该次复核时尚未下载权重或运行推理。此后用户授权安装固定模型，`doctor` 来源/必需文件检查通过，用户提供的真实本地样本推理也通过（见第 62、69 节），故“未做真实推理”这一限制已关闭。校验与 native model open 仍不是同一文件句柄，不能抵御同 UID 并发改写。

### SEC-18：外部 Hugging Face 缓存完整性和目录信任（已整改，主机缓存验收待做）

- **证据与整改：** pinned snapshot 现在要求受信任的 owner/祖先写权限链；符号链接 blob 必须落在对应 `blobs/` 内并匹配 Hub 文件名的 SHA-256 或 Git blob SHA-1 ETag。普通文件副本仅在整个目录链受信时接受，因为其缓存形式可能来自禁用 symlink 的环境。共享可写缓存和替换内容测试已添加；模型/ASR 定向测试 **18 passed, 1 skipped**。
- **剩余限制与对策：** 这条记录的旧快照中，Windows Hub cache 祖先 ACL 检查失败关闭、权重尚未下载。之后固定模型已成功完成真实样本推理（§62/69），但现有记录未证明加载路径实际经过此处描述的外部 Hub cache 目录信任分支，也未覆盖普通副本缺少 ETag 的情况。确认真实模型路径/缓存分支，并保留失败关闭策略；content hash 也不是上游签名。

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

### SEC-23：媒体时长上限信任容器声明值（P2 候选，常见格式和部分合成边界已验收）

- **修复前证据：** `_validate_with_pyav()` 只解码第一个音频帧即停止，并优先使用 `container.duration`、其次 `stream.duration` 作为实际时长。Pipeline 与 ASR 都检查这个值，但 ASR 最终收到原文件路径并处理整段输入，没有把解码终点限制为校验时长。
- **风险与结论：** 如果受支持的容器能声明低于实际音频长度的 duration，超出 `max_media_duration_seconds` 的文件可能通过旧校验。当前没有真实媒体样本确认具体格式能触发此条件，因此仍标为候选问题，不报告为已利用漏洞。
- **整改与验证：** `_validate_with_pyav()` 遍历音轨可解码帧，累计 `samples / sample_rate` 与 PTS 时间跨度，并逐帧检查配置上限；正容器声明超限时在解码前拒绝，较小声明不会压低观测时长。曾对 `InvalidDataError` 重试迭代器，但 §70 的真实 PyAV 合成样本证明 `container.decode()` 在异常后关闭，不能到达后续包；当前改为 `MEDIA_DECODE_FAILED`，防止容器声明值掩盖半截解码并进入 ASR。模拟回归现在要求该异常失败关闭。常规真实 AAC/MP4 worker 证据见 §68；合成 ADTS 的声明/解码时长对比和损坏包对照见 §70。`validate_media_file()` 的直接调用默认上限为 1 小时，与 pipeline/ASR 默认一致。此前 303/17 为历史套件结果。
- **剩余限制与对策：** §70 验证锁定 PyAV 生成的低报时长/编码填充与单个中间损坏包；未知时长按解码样本计时已有离线回归并进入 §75 全套。§137 补上 Windows 锁定 PyAV/libmp3lame 的真实 VBR MP3 生成、帧尺寸变化和产品解码器验收；Linux/macOS、其他封装/编解码器以及 faster-whisper 对照仍需验证。

### AUD-38：完整音频时长校验在一次任务中重复解码（P2，源码整改，真实性能基准待做）

- **修复前证据：** 逐帧 SEC-23 校验会完整消费音轨。默认本地路径在 `run_local()`、`_transcribe_claimed()` 和 `LocalASR.transcribe()` 各扫描一次；默认远端路径还会在 `download_media()` 校验，因此新远端任务最多额外完整扫描四遍，ASR 随后还要读取音频用于转写。
- **整改与验证：** `MediaFile` 现在带有从实际解码校验文件描述符取得的设备号、文件号、大小、修改时间和变更时间；PyAV 从该文件对象解码，前后身份变化会拒绝。pipeline 在本地预检或远端下载后将该结果传给 ASR；ASR 再打开文件并核对同一身份，然后把这个已核对的文件句柄直接交给 faster-whisper，转写结束前持续保持打开并再次核对。项目锁定版本的 [faster-whisper 1.2.1 转写 API](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/transcribe.py) 接受文件对象。路径被替换或媒体在校验后变化时会失败关闭；直接调用 ASR、缓存恢复或不提供身份的自定义 downloader/validator 仍执行独立校验。回归确认 PyAV 收到可读文件对象、校验期间媒体变化会被拒绝、默认本地 pipeline 只调用一次 validator，以及 ASR 在加载模型前拒绝替换文件。当前全套 Windows 离线测试 **303 passed, 17 skipped**，Ruff 通过。
- **剩余限制与对策：** 真实授权长媒体的 CPU 时间和总耗时尚未测量，不能量化具体性能收益；需要用 16.5 分钟样本和接近配置上限的样本记录校验次数、CPU 与完整任务耗时。AUD-10 的 Windows 本地真实媒体超时切片后来见第 68 节；分阶段计时、远端下载清理和 macOS/Linux worker 集成仍待验收。

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

- **证据（该次复核快照）：** 当时机器没有 ASR 模型、PyAV、Playwright 和 Chromium；doctor 显示 `setup_required`。该轮只运行离线模拟测试，没有获授权媒体或真实视频链接。用户随后授权安装并下载固定模型；当前就绪状态与未完成的真实验收见第 17 节。
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
- **验证：** 覆盖短绝对 deadline 限制下载、任务超时时错误码持久化、worker JSON 协议复用/超时终止、CLI 超时快照恢复/显式覆盖和失败任务状态。Windows 全套离线测试 **303 passed, 17 skipped**。后续第 68 节补充 Windows 本地真实媒体集成：PyAV worker 成功报告 315.907 秒音轨，固定 faster-whisper 模型可加载；CLI 设 45 秒 deadline 后总墙钟 46.49 秒返回 `PROCESSING_TIMEOUT`，任务状态一致，观察到的 worker PID 在 CLI 退出后已不存在，且无 Markdown、media-cache、`.part` 或 stderr 残留。此运行没有细分 deadline 内的模型加载/推理阶段；本地文件不触发远端下载临时文件路径。Linux/macOS 的终止行为与真实远端下载清理仍待验证。

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
- **整改：** medium 和 small 下载已固定完整 Hugging Face commit revision，并记录官方 API/tree 证据与选择日期，见 `skills/douyin-transcript/references/MODEL_PROVENANCE.md`。这条记录的权重哈希/推理状态是旧快照；之后用户授权下载的模型已通过真实样本推理（§62/69）。模型升级仍需做质量/性能回归。

### AUD-16：失败重试没有复现首次运行配置（P1，功能一致性；新任务已整改）

- **修复前证据：** `retry-failed` 按任务 profile 构造默认 pipeline；数据库没有保存 `language`、`timestamps`、术语规则或资源上限快照。
- **影响：** 首次运行使用 `--language auto`、`--timestamps` 或词典后失败，重试可能按默认中文、无时间轴、关闭词典运行；输出会与原请求不同。
- **整改与限制：** schema v3 增加 `processing_options_json`，本地/远端任务建立时保存白名单非正文设置和词典规则快照；重试验证并恢复快照，支持显式 `--output-dir` 覆盖。`--force` 重开完成任务会刷新最近 attempt 的 profile/title/options。旧任务缺少或无法校验快照时默认 skipped；只有显式 `--use-current-defaults` 才按当前配置重试，并将被选择的快照持久化。端到端用例覆盖 auto、时间轴、词典、资源限制、输出目录及摘要/日志/数据库不含逐字稿正文。

### AUD-17：50 条批次验收仍不完整（P1，稳定性；已由 AUD-75 补齐）

- **修复前证据：** 原集成批次仅覆盖 10 条；虽有 50 条输入接受测试和 100 条硬上限，但没有 50 条混合任务调度用例。
- **影响：** 单测边界不能证明批量混合状态下的结果数量、任务最终状态、下载并发和缓存/输出增长受控。
- **此前记录与补齐：** 当时报告称新增假 downloader/ASR 的 50 条模拟并通过，但 AUD-75 复核发现当前 checkout 未保存该用例，先前结果无法复核。本轮重新实现 `test_fifty_item_mixed_batch_bounds_downloads_and_keeps_asr_serial`，覆盖要求项并通过定向回归，现以当前源码和结果替代旧记录。
- **限制：** 模拟不验证真实媒体、真实磁盘耗尽、网络服务或所有 OS 调度行为。

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

当前的发布前条件、证据与限制汇总见 [RELEASE_REPORT.md](RELEASE_REPORT.md)。架构、逐阶段证据和发布清单见 [ARCHITECTURE.md](ARCHITECTURE.md)、[ACCEPTANCE.md](ACCEPTANCE.md) 与 [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)。上一轮 Codex Security 结构化扫描记录 5 项源码发现、此前 Diff Scan 记录 SEC-25；两者都绑定启动时快照。较早的 Diff Scan `484bb340-323c-4bec-a20a-368b2fcd077d` 覆盖其冻结清单内 30 个源码/配置审查项且未发现新候选；之后的扫描与动态验收见第 9、10 节。SEC-26 与 AUD-40 至 AUD-55 的后续修复情况以本报告各条记录为准。SEC-14 仍待目标 Agent 宿主验收；SEC-15 创建路径边界已进一步收紧，但 SQLite/Playwright/模型等 pathname-only API 仍有 TOCTOU 和多平台测试；SEC-16 fallback 需多主机验证，SEC-17 真实模型推理已通过（§§62/69），SEC-18 的具体 Hub cache 路径仍待确认，AUD-21 需第二账户集成。SEC-19/20 配置路径及同句柄读取已整改，SEC-24 与 AUD-44 的 POSIX FIFO 行为待 Linux/macOS 运行验证；AUD-43 sidecar 路径/摘要已绑定并由完成、跳过和恢复流程校验，跨平台文件系统验收仍待完成。AUD-39 已通过 downloader 和默认 pipeline 回归。

## 6. 审核范围说明

本报告审阅当前本地工作树与可见 Git 历史，不代表远端分支或已发布版本。SEC-19/20 的 Windows 配置回归通过；POSIX symlink/`..`、替换竞态与 FIFO 用例因当前主机是 Windows 而跳过。SEC-22 有伪造 frontmatter、文件修改及恢复行为回归；共享输出目录并发替换仍需平台集成。AUD-36 已实现 POSIX 目录同步和 Windows 写穿透发布，AUD-37 的通用 Win32 错误分类已整改；Linux/macOS 和其他文件系统的断电耐久性未验证。AUD-32/33 由阻塞 resolver 模拟回归覆盖，但真实 DNS/Chromium 链路未验证；SEC-23 源码修复有模拟覆盖，真实媒体格式仍待样本确认；AUD-38 的实际时耗尚无基准。截至该段形成时最新的 Codex Security Diff Scan 已复核冻结差异内 28 个审查项且无新候选，包括 SEC-25/26 修复所在文件；该扫描不代表全仓动态审计。POSIX 扩展 ACL 语义无法在 Windows 环境确认，故整体项目验收 coverage 仍为 partial。AUD-39 已由下载器缓存/新下载测试及默认远端 pipeline 回归修复。本机当时尚未动态验证真实抖音媒体、在线 CDN、ASR、远端 CI、第三方二进制、Linux/macOS 和 Agent 宿主行为。第 6 节形成时的 `doctor --json` 为 `setup_required`，ASR/PyAV/模型/Playwright/Chromium 尚未安装；这是安装前历史快照。用户随后授权安装后，2026-10-09 的显式私有路径复查报告 ASR 与抖音 URL 能力均为 `ready`（见第 17 节），但未提供本地媒体且抖音页面未捕获媒体，P1 真实转写仍是最早未通过阶段。该段形成时 D: 工作区输出路径为 `unsafe`；该目录现已不再是隐式默认（第 58 节）。

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
- **影响与前提（AUD-51 阶段快照）：** 这是权限诊断误报，会产生不必要警告并影响用户判断输出目录是否适用；本机 profile 祖先中的该 ACE 不授予目录列表、文件读取、写入或删除权限。当时默认 D: 工作区输出目录仍存在真实目录替换权限问题并报告 `unsafe`；第 58 节已将其移出隐式默认。
- **整改：** 新增 `_foreign_windows_ace_grants_sensitive_access()`，仅忽略遍历/同步位；其他访问位仍视为 foreign sensitive access。新增 7 组掩码策略回归，覆盖 traversal、synchronization、两者组合、读取、写入、删除子项和 generic read。
- **验证（AUD-51 阶段快照）：** ACL 策略定向测试 **7 passed**；AUD-51 完成时全套 Windows 离线测试 **323 passed, 17 skipped**（历史快照），当前全套结果见第 2 节；Ruff、锁文件、敏感文件扫描和固定 `skills-ref==0.1.1` 校验通过。`doctor --output-dir "$env:USERPROFILE\Transcripts" --json` 报告权限 `ok`，且目标目录未创建；当时默认 `doctor --json` 对 D: 工作区输出报告 `unsafe`，整体状态为 `setup_required`。后续用户授权安装后的能力状态见第 17 节；第 58 节已将 D: 路径移出隐式默认。
- **剩余对策：** 在其他 Windows 版本、实际继承 DACL 和多账户环境验证诊断与新目录继承权限；POSIX ACL 和权限语义仍需 Linux/macOS 实机验收。该修正不表示 SEC-15 的 pathname-only/TOCTOU 边界已消除。

### SEC-27：映射网络盘未被 UNC 拒绝规则覆盖（源代码已整改，真实映射盘验收待做）

- **修复前证据：** `storage_security.py` 原先仅通过 `PureWindowsPath(...).anchor` 的 UNC/device namespace 前缀拒绝路径。盘符路径（例如一个带盘符的绝对路径）的 anchor 是 `Z:`，不匹配该条件，因此可能继续进入权限检查和存储流程。
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
- **验证（AUD-58 阶段快照）：** Fake Playwright 回归覆盖上下文路由先于页面创建、Service Worker 阻断、代理 bypass 参数，以及 WebSocket scheme/域名/DNS allowlist；capture/proxy 定向测试 **21 passed**，相关 Ruff 通过。当时本机未安装 Playwright Python 包、未运行 Chromium；用户后来授权安装并进行一次可见页面访问，但没有捕获媒体（见第 17 节）。popup、预注册 Service Worker、真实 loopback/链路本地和抖音 WebSocket 行为仍需集成验收。阻断 Service Worker 若影响平台功能，需以真实站点测试确认兼容性。

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
- **文档复核（DOC-12 修复当时）：** 状态文档当时均指向 Windows Python 3.11.15 与 3.12.13 各 **376 passed, 20 skipped**；多 Python 本地测试要求先同步环境并核实解释器；旧测试数字只保留在明确标为历史快照的记录中；跨平台 CI 仅保留一个发布门。随后一轮第 9 节记录的当期结果为 382/20；该数字现为历史快照。整体仍为 **NOT READY**。
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
- **DOC-15（P3，审核报告首页测试数字过时，已修正）：** 首页曾把 AUD-64–66 阶段的 366/20 写成未标注的当前结论，和当时报告后文的 376/20 当前结果冲突。现已标明旧结果为历史快照；当时续审记录的结果为 Python 3.11.15 与 3.12.13 均 382/20。
- **DOC-16（P3，输出目录环境变量未见于用户指南，发现时待补文档）：** `config.py` 接受 `DOUYIN_TRANSCRIPT_OUTPUT` 并将其作为输出目录覆盖值；发现时 README、CLI Reference 和 INSTALL 未说明该变量或优先级。调用者仅看用户指南可能无法解释环境变量为何覆盖配置文件。
  - **对策：** 在中文/英文 README、CLI Reference 和 INSTALL 中列出该变量，并写清优先级：`--output-dir` → `DOUYIN_TRANSCRIPT_OUTPUT` → `config.toml` 的 `paths.output_dir` → 默认目录。若不希望承诺环境变量接口，则移除该实现并保留明确的 CLI/config 行为。
- **SEC-31（P2，中危，HLS 子请求可能绕过下载网络边界，发现时待动态确认）：** 页面捕获会接受 `application/vnd.apple.mpegurl`，下载器先校验首个 HLS URL 并下载清单；发现时 `validate_media_file()` 将文件包装成 file-like 对象交给 `av.open()`，没有设置 `protocol_whitelist` 或限制 PyAV 的 `io_open`。如果锁定版本 FFmpeg 的 HLS demuxer 按清单中的绝对 URI 打开片段，它可能自行请求 loopback/内网 HTTP 地址，绕过下载器的主机、DNS pinning、重定向和累计字节数边界。默认 CLI 在受监管子进程中执行媒体校验，超时可终止该进程；当前证据不支持声称此路径绕过整体处理 deadline。FFmpeg 文档说明协议可通过 `protocol_whitelist` 限制，HLS 源码会处理清单引用资源；PyAV 文档说明 `io_open` 用于格式额外打开的文件对象。尚未在项目锁定的 PyAV 15.1.0 wheel 上动态确认该调用链，因此按条件风险记录。参考：[FFmpeg Protocols](https://ffmpeg.org/ffmpeg-protocols.html)、[FFmpeg HLS 源码](https://ffmpeg.org/doxygen/7.1/hls_8c_source.html)、[PyAV 15.1 `av.open`](https://pyav.basswood.io/docs/15.1/api/_globals.html)。
  - **对策：** 若不需要 HLS，拒绝 HLS 清单；否则在 PyAV `av.open()` 上设置严格协议白名单，并通过自定义 `io_open` 拒绝不经应用校验的网络/文件子请求。需要支持 HLS 时，将每个片段 URL、DNS 地址、跳转、总字节和总时间纳入与下载器相同的受限请求器。用本地 mock HTTP 服务提供含 loopback/private URL 的 HLS 清单，验证不会产生未授权请求，并验证正常授权 HLS 仍可用。
- **SEC-32（P3，敏感文件检查对部分文件静默跳过内容扫描，低危，发现时待整改）：** CI 会执行 `scripts/check_sensitive_files.py`，但发现时超过 2 MiB、含 NUL 或 UTF-8 解码失败的文件会被静默跳过内容模式扫描。若凭据放在路径规则未覆盖的这类文件中，当前 CI 检查不会报告未检查状态。该检查本来就不是通用 secret scanner。
  - **对策：** 对大文本改用分块扫描；对二进制/非 UTF-8 文件记录路径并要求显式分类或人工复核，不把“未检查”呈现为“通过”。保持已知敏感路径拦截，并在 CI 输出文件数、跳过数及跳过原因。
- **历史存储风险记录（AUD-11，非本轮新发现）：** 该段形成时，输出目录权限检查是提示性策略，当前工作区默认输出路径的祖先 ACL 已检查为不安全；隐私敏感的逐字稿需显式输出到权限检查为安全的用户目录。此风险已由 AUD-79 在第 58 节整改：隐式默认改用 `<data_dir>/output`，权限不安全或未知时拒绝处理。
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
- **审查范围限制：** 这是一份静态差异审查，coverage 对 HLS 动态行为保持 partial；没有访问抖音、下载模型/浏览器组件、运行真实 ASR 或检查远端 CI。安全审查的 0 项候选不代表产品验收完成，P1/P2/P4/P5/P6 门槛、当时记录的输出目录 advisory 风险、历史敏感文件审查和许可证/远端所有者决定仍按发布清单执行；输出默认权限风险后来已按第 58 节整改。上述文档更改发生在安全扫描冻结快照之后，不属于该扫描快照。

## 9. 2026-10-09 本机验收续审

- Windows Python 3.11.15 项目虚拟环境与 Python 3.12.13 独立临时环境重新运行全套离线 pytest，均为 **382 passed, 20 skipped**。跳过项是 POSIX 专属行为或当前文件系统不能创建 symlink 的用例。
- 本节形成时（用户授权安装前）的 P0 CLI 冒烟：`python -m douyin_transcript --help` 退出码 0；`doctor --json` 退出码 1，`overall` 与两种能力均为 `setup_required`，符合当时尚未安装 Skill 运行依赖和模型的预期。安装后状态见第 17 节。
- GitHub Actions 中使用的 Ruff 路径 `scripts skills/douyin-transcript/src skills/douyin-transcript/scripts tests` 通过；`uv lock --project skills/douyin-transcript --check`、Git 可见敏感文件扫描和 `git diff --check` 均通过。工作树中统一应用项目 Ruff 配置的检查也已修复格式问题并通过。
- Python 3.12.13 使用锁定开发依赖在仓库外独立临时环境运行全套测试，结果 **382 passed, 20 skipped**；该环境通过 `UV_OFFLINE=1` 创建，未改动项目的 Python 3.11 虚拟环境。此前的 **376 passed, 20 skipped** 属于旧工作树快照。
- **SEC-31 动态检查：** 系统 Hermes Python 3.11.15 使用 PyAV 18.0.0 / FFmpeg libavformat 62.12.102 的补充结果是：合成 HLS loopback 分段触发拒绝回调 1 次、服务请求 0 次，1 秒 PCM WAV 验证通过。随后在仓库外临时环境安装锁定 PyAV 15.1.0 / FFmpeg libavformat 61.7.100 重做验收，得到相同结果：回调 1 次、服务请求 0 次、HLS 以 `MEDIA_DECODE_FAILED` 失败关闭，1 秒 PCM WAV 验证为 `wav`。临时环境与素材在仓库外创建。
- **SEC-33 C1 回归：** 标题采集、CLI 摘要、Markdown frontmatter/heading/body 的 U+0085、U+009B 回归通过；现有文件名清理使用 Unicode 类别 `Cc`，包含 C1。该修复发生在之前的正式安全扫描之后，后续差异扫描快照及其覆盖范围见单独审查记录。
- 截至此前复审时 HEAD `154d9ef`（4 个可达本地提交）的只读历史扫描覆盖 **101 个唯一路径/blob 对**；101 个均为 2 MiB 内 UTF-8 文本，未命中仓库敏感路径规则或高置信度凭据模式，也未命中工作区根目录/用户目录标记。当前 HEAD 的新一轮历史扫描见第 11 节。该扫描不是通用 secret scanner；发布前仍须复核最终提交和历史。
- 本轮续审修改了文档中的 Python 3.12 当前测试结果和安全验收状态，并修复 SEC-33 的 C1 控制字符清理及回归测试；该源码差异包含在后续 Codex Security Diff Scan `fd9a73df-3590-47b3-aada-ab36bde2fd61` 的冻结快照中。锁定 PyAV/HLS 动态验收已在 Windows 通过；真实 P1/P2/P4、Agent 宿主、跨平台远端 CI、许可证和仓库所有者决定仍未完成，项目保持 **NOT READY**。

## 10. 2026-10-09 C1 控制字符差异复审

- **正式扫描结论：** Codex Security Diff Scan `fd9a73df-3590-47b3-aada-ab36bde2fd61` 已完成。扫描冻结在 base/head `154d9ef1d8fd8a75b6a8870bb2d99dc602ceae62`，snapshot digest 为 `codex-security-snapshot/v1:sha256:310d9cb80df88511cea4e51cd1e9e7e4ea8a7e01d71f958eba88ab6465775dcf`。冻结差异中的 3 个源码审查项逐项完成；本次差异未发现新的可报告安全问题。SEC-33 是本次修改前已记录并正在修复的低危问题，不是修复差异引入的新问题。
- **快照边界：** 扫描工具提示扫描期间工作树发生变化，结果仍绑定上述冻结快照；本报告随后追加的文字不属于扫描输入。三个源码审查项及其代码状态按该快照记录。
- **复核证据：** `capture.py:400-408` 在页面标题、作者及发布时间进入任务/展示前剔除 C0、C1 和双向控制符；`text_safety.py:16-26` 为 CLI 与任务展示提供同类过滤；`markdown.py:20-58,97-112` 过滤 Markdown 正文控制字符，并清理 frontmatter/标题。新增测试用 U+0085、U+009B 覆盖采集标题、CLI 摘要及 Markdown frontmatter、标题和正文。此处结论是源码差异复核；不同终端和 Markdown 查看器的实际渲染仍未逐一测试。
- **仍待处理的问题及对策：**
  1. **真实 ASR / P1（第 10 节快照）：** 当时诊断为 `setup_required`，尚无获授权的中文样本或真实识别结果。用户后来授权安装锁定 ASR 依赖和固定模型；当前仍缺至少 60 秒且有权处理的本地媒体，因此真实推理、Markdown、人工抽听和性能记录未完成，见第 17 节。
  2. **真实抖音链路 / P2（第 10 节快照）：** 当时尚未安装并运行 Playwright/Chromium，也没有三条授权链接的集成结果。用户后来授权安装并提供 1 条链接；可见浏览器访问主文档返回 HTTP 200，但 CLI 为 `CAPTURE_NO_MEDIA`。目前仍需另外 2 条授权链接和成功捕获，见第 17 节。
  3. **质量与性能 / P4：** 真实逐字稿听审、长音频计时和重复内容检查待 P1 样本。验收至少三处文本，并记录耗时、漏转/幻觉/重复及 stdout/stderr 泄漏检查。
  4. **Agent 宿主 / P5：** Skill 标准校验和仓库外干净安装冒烟通过，但真实宿主调用未验收。确定目标宿主后，使用结构化参数完成一次端到端调用并检查正文未进入 Agent 上下文。
  5. **发布 / P6：** 远端 CI、仓库所有者/可见性、LICENSE 选择和推送授权未落实。由仓库所有者确定许可证和目标仓库；再运行 Windows/macOS/Linux CI、复核提交历史中的敏感材料，最后按发布清单审批。
  6. **本地输出隐私（历史快照）：** 该段形成时输出目录权限诊断仍是 advisory，默认工作区输出路径祖先 ACL 不安全。第 58 节已将隐式默认移至 `<data_dir>/output`，并对不安全或未知权限失败关闭；明确选择的共享目录仍由调用者负责。
  7. **第三方许可证：** Windows 锁定 PyAV wheel 的临时检查发现 x264/x265 DLL 和可用编码器，需在任何二进制分发前核验实际 FFmpeg 构建配置、许可证文本和分发义务，并由所有者决定许可证策略；详见 `THIRD_PARTY_LICENSE_REVIEW.md`。
- **项目状态（该节快照）：** 当时本地 Python 3.11.15/3.12.13 全套测试各 382 passed、20 skipped；该快照已被后续 385/20 结果取代。锁定 PyAV 15.1.0 的合成 HLS loopback 拒绝及 WAV 解码通过，详见第 9 节。静态差异扫描通过不等于产品验收完成；P1/P2/P4/P5/P6 与发布审查完成前，项目维持 **NOT READY**。

## 11. 2026-10-09 项目完成目标续审

- **第 11 节运行状态快照（安装前）：** 当时在 Windows 工作区执行锁定环境 `doctor --json`，结果为 `setup_required`；未安装依赖、下载模型或创建数据目录。报告显示固定 medium 模型、faster-whisper、PyAV、Playwright 和 Chromium 均未就绪；默认工作区输出目录的权限为 `unsafe`，原因是其 `D:` 祖先向 Authenticated Users (`S-1-5-11`) 授予目录替换权限。用户授权安装后的能力状态见第 17 节；第 58 节已将 D: 输出路径移出隐式默认。
- **P1 预检补充：** 只读测得当前主机 CPU 为 Intel Core i5-12400、12 个逻辑处理器、已安装内存 31.7 GiB，已同步写入 `docs/P1_REPORT.md`。本次没有处理媒体，未测量模型加载、推理、峰值内存或逐字稿质量，因此 P1/P4 仍 **NOT VERIFIED**。
- **可用平台与远端：** 当前系统没有注册的 WSL Linux 发行版；本地 `git remote -v` 为空。因此本机无法补跑 POSIX 分支，远端矩阵 CI 和 GitHub 安装仍无执行目标。没有据此把未验收项标成通过。
- **状态文档一致性整改：** `docs/RELEASE_REPORT.md` 现将 Diff Scan `fd9a73df-3590-47b3-aada-ab36bde2fd61` 作为已记录的最新差异扫描，并说明锁定 PyAV 15.1.0 在 Windows 的 HLS loopback 拒绝/WAV 动态验收已通过；DOC-12 的 376/20 记录与早期 SEC-31 动态状态改为明确的历史阶段说明。实施计划将 SEC-15 本地源码整改与跨平台/多账户验收拆分记录，后者继续未完成。
- **当前工作树门禁复跑（该节快照）：** Windows Python 3.11.15/3.12.13 全套离线 pytest 各 **384 passed, 20 skipped**；此结果随后被 CLI-02 修复后的 385/20 取代。20 项跳过涉及 POSIX 权限/FIFO/dir-fd 语义，或本机文件系统不允许创建 symlink。GitHub Actions 使用的 Ruff 路径、`uv lock --check`、敏感文件扫描、固定 `skills-ref==0.1.1` Skill 校验及 `git diff --check` 均通过。
- **提交后历史检查：** 本地检查点 `b166778` 是当前 HEAD，5 个可达提交共覆盖 120 个唯一路径/blob 对。只读扫描确认 120 项均为 2 MiB 内 UTF-8 文本，仓库敏感路径规则、高置信度凭据模式及本机工作区/用户目录标记均无命中；没有跳过项。该检查不是通用 secret scanner，也不代替最终发布树的人工审查。
- **当时尚需用户/所有者输入的真实门槛：** P1/P4/AUD-10/38/SEC-23 需要授权媒体；ASR 安装与固定模型下载后来已按用户授权完成（见第 17 节）。P2 需要三条获授权链接并由操作者在可见浏览器手动登录（如需要）；P5/SEC-14 需要指定目标 Agent 宿主；P6 需要所有者决定许可证、仓库归属/可见性以及是否创建远端或发布。输出默认策略后来按原实施计划更正为 `<data_dir>/output`，并对不安全/未知权限失败关闭（第 58 节）。
- **续审边界：** 本次重跑了 Windows Python 3.11.15 全套离线测试及静态发布前检查，补录硬件预检，扫描更新后的本地 Git 历史并修正文档状态；没有执行真实媒体、安装或联网流程，也没有新增源代码差异安全扫描。完整项目状态保持 **NOT READY**。

## 12. 2026-10-09 全仓库独立复核

- **范围与结论：** 针对本轮冻结快照 `b166778ee5283591a1b799535b746ba198e38653`（snapshot digest：`codex-security-snapshot/v1:sha256:9245825be6b863e9cd10e561f93f95cfa115b1daa2097a8356fa2431acf22cb2`）完成 88 个 Git 跟踪文件的静态复核。发现 1 项有条件触发的低危隐私问题、2 项文档准确性问题；没有在其余受审源码路径中确认新的漏洞，也没有发现真实凭据、私钥、Cookie 或用户媒体。正式扫描 ID：`df8a49e4-a749-406f-b846-81083659c53a`。本节是在冻结扫描快照之后写入，因此不属于扫描输入。
- **复核限制：** 未在本轮处理真实媒体、安装模型或浏览器、访问抖音、调用目标 Agent 宿主、运行远端 CI，或验证 POSIX/macOS/Linux ACL。已有 Windows Python 3.11.15/3.12.13 测试结果见第 9 节，本轮没有重跑测试。静态源码结论不代替这些环境和产品验收。

### SEC-34：Markdown 逐字稿元数据暴露术语词典原文（P3，已整改并通过回归）

- **冻结快照中的证据：** 正式扫描快照中，`AppliedCorrection.to_dict()` 会把匹配规则的 `rule_id`、`source`、`replacement`、`occurrences` 和 `note` 写入主稿的 `terminology_corrections` frontmatter。该问题只在调用方显式启用词典时触发。
- **整改：** 移除逐规则序列化。新 Markdown 元数据仅记录 `schema_version`、`ruleset_sha256`、汇总匹配规则数 `applied_rule_count` 和替换总次数 `replacement_count`；不写规则 ID、词条、替换值、备注、逐规则次数、启用状态或词典总条数。完整词典仍保存在权限受保护的本地任务数据库，用于失败重试。
- **剩余隐私边界：** 规则集 SHA-256 可以与已知词典比对，不应视为匿名化承诺；替换结果按用户要求出现在逐字稿正文中。已生成的旧 Markdown 不会自动改写；如果此前生成过包含规则详情的文件，应复核并自行清理，`--force` 重跑会写新文件但不会删除旧文件。
- **验证：** 定向 `corrections`、`pipeline`、`tasks` 回归覆盖汇总计数、敏感规则值不进 frontmatter、正文替换保持正确及大 frontmatter 完整性。该阶段 Windows Python 3.11 和 3.12 离线全套均为 **384 passed, 20 skipped**；当前最新结果见第 2 节。

### DOC-22：配置文件查找位置说明与实际行为不一致（P2，已修正文档并验证）

- **证据：** `config.py` 先按 `--data-dir`、`DOUYIN_TRANSCRIPT_HOME` 或平台默认位置选择配置锚点并读取其 `config.toml`，之后才应用 `[paths].data_dir`。因此 `[paths].data_dir` 不会移动配置文件。原 README 让用户在 `doctor --json` 显示的有效数据目录下编辑 `config.toml`，其余文档也没有统一说明锚点与有效 data directory 的区别。
- **影响：** 操作者把配置文件放到有效数据目录后，配置可能不会被读取，资源上限或 `output_dir` 会静默回退默认值。
- **整改：** 中文/英文 README、CLI Reference、INSTALL、配置示例和项目实施计划现在统一说明配置锚点选择、有效数据目录与输出目录优先级，并说明有效 retry snapshot 会保留原输出目录，除非传入 `--output-dir`。
- **验证：** 对照 `resolve_paths()` 实际解析顺序复核各文档；`uv lock --check`、Ruff、敏感文件检查、`skills-ref==0.1.1` 校验和 `git diff --check` 均通过。

### DOC-23：实施计划示例未标注为虚构（P4，已整理）

- **整改：** 进度汇报模板已明确标为虚构格式示例，删除虚构测试通过数字和文件路径，改用待填实测结果占位符。
- **验证：** 静态检查确认模板标识虚构内容，不再把示例结果展示为项目实测证据。



### CLI-01：显式空路径被解释为工作目录（P3，已修复）

- **证据：** `resolve_paths()` 过去用路径字符串的 truthiness 选择配置锚点，却用 `is not None` 选择有效数据/输出目录。传入空的 `--data-dir` 时会从平台默认锚点读取配置，但把任务数据目录解析到当前工作目录；空的 `--output-dir` 也会被 `Path("")` 解析成当前工作目录。
- **影响：** 调用方若通过结构化参数误传空字符串，任务数据或逐字稿可能落到意外位置；不构成已确认的跨账户访问漏洞。
- **整改与验证：** `resolve_paths()` 现在对显式空字符串分别返回 `--data-dir` 或 `--output-dir` 配置错误；参数化配置测试覆盖两种情况。更新后的 Windows Python 3.11 和 3.12 全套各为 384 passed、20 skipped。
### 现有发布门槛

- 第 12 节形成时，本机 `doctor --json` 为 `setup_required`；默认工作区输出路径的权限检查为 `unsafe`。用户授权安装后的能力状态见第 17 节；第 58 节已将隐式默认路径改为权限为 `ok` 的应用数据目录下 `output/`。
- P1/P4 的真实 ASR、听审和性能记录需要获授权的本地媒体并批准安装锁定依赖/模型；P2 需要获授权的抖音链接及可见浏览器验收；P5 需要指定目标 Agent 宿主；P6 需要完成许可证、远端仓库与发布决定。POSIX/macOS/Linux、远端 CI 和许可证分发审查也尚未完成。
- SEC-34 的本地整改已完成，但旧输出文件需由操作者自行复核；上述真实验收门槛完成之前，项目保持 **NOT READY**。本审核报告不构成发布批准。

## 13. 2026-10-09 后续整改复核

本节记录冻结扫描之后完成的代码、文档整改及本轮复验，不改变第 12 节正式 Codex Security 扫描绑定的快照范围。

| 项目 | 本轮结果 | 证据 |
|---|---|---|
| SEC-34 术语词典元数据最小化 | **已整改** | Archive schema v2 仅保留规则集 hash、汇总命中规则数和替换次数；新增/更新单元及 pipeline 用例检查规则 ID、原词、替换值、备注不进入主稿 frontmatter。 |
| DOC-22 配置锚点说明 | **已修正** | 中英文 README、CLI Reference、INSTALL、配置示例及实施计划均说明锚点与有效数据目录的区别，以及输出路径和 retry snapshot 行为。 |
| DOC-23 虚构示例 | **已修正** | 示例标明虚构，数字和路径改成待填实测占位值。 |
| CLI 显式空路径 | **已修复，P3 输入边界** | `resolve_paths(data_dir="")` 和 `resolve_paths(output_dir="")` 现在返回带选项名的配置错误；参数化回归覆盖两种输入。 |
| 定向回归 | **通过** | 配置、词典、pipeline 和大 frontmatter 用例：27 passed, 1 skipped。 |
| Windows Python 3.11/3.12 全套离线 pytest（第 13 节快照） | **均通过** | 各 384 passed, 20 skipped；跳过项是 POSIX 专用权限/FIFO/symlink 语义或本机文件系统不支持的 symlink 用例。该结果已被后续 385/20 取代。 |
| 本地发布前静态门禁 | **通过** | `uv lock --check`、Ruff、敏感文件检查、`skills-ref==0.1.1` Skill 校验和 `git diff --check` 均通过。 |

正式扫描仍绑定第 12 节所列冻结快照，没有对本次后续差异重新运行正式 Codex Security 扫描。P1/P2/P4 实际媒体验收、目标 Agent 宿主、macOS/Linux 与 Windows 多账户集成、远端 CI 和所有者发布决定仍未完成，项目状态仍是 **NOT READY**。

## 14. 2026-10-09 后续项目与差异复核

- **正式安全差异扫描：** Codex Security Diff Scan `9dd6de80-b0ed-4131-ac02-9fbc7dfaa779` 已封存，绑定 base/head `b166778ee5283591a1b799535b746ba198e38653`、快照摘要 `codex-security-snapshot/v1:sha256:a3b0fb0e2267999536c94548080bf98e4a12abf0a62c66d72bb84aead3f88510`，findings 为空。三个变更源/配置审查项均已人工复核，独立架构审阅也未发现新增安全问题；但正式扫描的 coverage 被工具标记为 **partial**，因为临时回执未能复制进扫描目录，最终 coverage 没有保留有效回执引用。因此该结果只能表述为“已检查的差异项未发现可报告问题”，不能称为正式全覆盖结论。扫描为静态检查，不代表真实 ASR、抖音/浏览器、跨平台 ACL 或远端 CI 验收。
- **SEC-34 复核结论：** 术语 frontmatter 不再写出规则 ID、原词、替换值、备注或逐规则计数；只留 hash 与汇总计数。hash 仍可和已知词典比对，转换后的词语也按用户要求保留在正文中。若词典身份本身必须保密，应去掉确定性 hash，或改用不随 Markdown 暴露密钥的 keyed fingerprint。该残余已披露，不是本次新发现。
- **CLI-02（P4，诊断路径一致性，已修复）：** `doctor.collect_report()` 捕获显式空 `output_dir_override` 的配置错误后，不再将空值转成 `Path("")` 检查当前工作目录；输出状态报告为 `unknown`，跳过输出路径写入能力和权限探测，同时保留配置错误状态。新增回归确认当前工作目录不在检查列表、不会做输出权限探测且不会创建目录，见 `doctor.py` 与 `tests/test_doctor.py`。
- **DOC-24（P3，当前测试基线过时，已修正并再次同步）：** README 中英文版、验收页、整改计划、审核报告和发布材料已同步到最新 Windows Python 3.11.15/3.12.13 各 385/20；382/20 与 384/20 保留为较早快照。
- **复核证据：** CLI-02 修复后的 Windows Python 3.11.15 与 3.12.13 全套测试各 385 passed、20 skipped；全仓 Ruff、敏感文件检查和 `git diff --check` 通过。第 14 节的 Diff Scan 绑定早先冻结快照，未覆盖本次 `doctor.py` 修复；其 coverage 仍为 partial。本节的代码整改和测试证据不代表新增正式安全扫描。
- **剩余门槛：** P1/P4 实际 ASR、P2 三条授权抖音链接、P5 目标 Agent 宿主、POSIX/macOS/Linux 与多账户验收、远端 CI、依赖 SPDX/PyAV 许可核查、项目 LICENSE 和仓库所有者发布决定仍未完成。项目保持 **NOT READY**。

本轮对策摘要见 [`PROJECT_AUDIT_FOLLOWUP_2026-10-09.md`](PROJECT_AUDIT_FOLLOWUP_2026-10-09.md)。

## 15. 2026-10-09 CLI-02 修复与复验

- **修复：** 配置解析因显式空 `--output-dir` 失败时，doctor 不再把空字符串退化成当前工作目录。输出目录与相关权限状态返回 `unknown`，跳过输出路径探测；配置保持无效并报告 setup required。
- **回归：** `test_doctor_does_not_check_current_directory_for_empty_output_override` 检查无效配置、输出状态未知、仅检查 data directory、没有输出权限探测、没有检查当前目录且没有创建目录。定向 doctor 回归 2 项通过。
- **验证：** Windows Python 3.11.15 和 Python 3.12.13 全套离线测试各 **385 passed, 20 skipped**；`doctor.py` 与 `tests/test_doctor.py` 的 Ruff 检查通过。跳过项涉及 POSIX 语义或本机 symlink 能力。
- **扫描范围：** 第 14 节正式 Diff Scan 绑定 `b166778` 冻结快照，未覆盖之后的 `doctor.py` 修复；本次未产生新的正式 Codex Security 扫描结果。第 14 节扫描 coverage 仍为 partial。
- **项目状态：** CLI-02 与 DOC-24 已关闭；真实 ASR、获授权抖音链路、目标 Agent 宿主、POSIX/macOS/Linux 与多账户、远端 CI、第三方许可证及所有者发布决定仍未完成，整体 **NOT READY**。

## 16. 2026-10-09 CLI-03、SBOM 与当前差异复核

- **CLI-03（P4，doctor 输出目标诊断）：** `collect_report()` 捕获配置错误后，旧逻辑若无 CLI 输出覆盖值就猜测当前目录的默认输出路径，忽略更高优先级的 `DOUYIN_TRANSCRIPT_OUTPUT`，并把所有配置错误都报告成 TOML 格式错误。该问题只影响只读诊断准确性，不会创建或写入输出目录。
- **整改：** doctor 保留具体配置错误；配置解析失败时仅探测明确 CLI 输出目录或非空 `DOUYIN_TRANSCRIPT_OUTPUT`。没有可信目标时把输出目录和权限设为 `unknown` 并跳过探测；显式空 CLI 值仍按 CLI-02 处理。
- **验证：** `tests/test_doctor.py` 定向测试 **19 passed**，覆盖配置错误时环境变量输出优先级、无可信输出目标时不检查当前目录，以及显式空路径行为。CLI-03 后 Windows Python 3.11.15 与 3.12.13 全套离线测试各 **387 passed, 20 skipped**；Python 3.12 使用仓库外临时环境及锁定依赖。
- **依赖清单：** 新增 `docs/third-party-sbom.spdx.json` 与 `scripts/generate_spdx_sbom.py`。清单包含 `uv.lock` 的 34 个包记录（项目本身 1 个、第三方依赖 33 个），包括两个 NumPy 平台/Python 解析版本、`asr`/`browser` extras 及 dev 组。SPDX 2.3 JSON Schema 校验通过，包/版本集与 `uv export --format cyclonedx1.5 --all-extras --all-groups --frozen` 的 33 个第三方组件一致，`uv lock --check` 通过。
- **SBOM-01（P3，文档标识）：** 首版生成器只把 `uv.lock` 摘要用于 SPDX namespace，而每次重生成会更新 `creationInfo.created`，导致不同文档内容复用相同 namespace。现已将锁文件摘要、生成器摘要和创建时间共同纳入 namespace；清单已按修复后脚本重新生成。
- **许可证状态：** `uv.lock` 没有许可证字段，清单按 SPDX 规范将包的声明/结论许可证记为 `NOASSERTION`。这完成了锁定依赖组件盘点，但没有完成逐包许可证/notice 审核；PyAV/FFmpeg wheel 发行审查、项目自身 LICENSE 和所有者决定仍开放。
- **正式差异扫描：** Codex Security Diff Scan `db94ca43-2337-42d0-ab6a-7369aeb6ad8e` 已完成，base/head 为 `b166778ee5283591a1b799535b746ba198e38653`，快照 digest 为 `codex-security-snapshot/v1:sha256:d7551c22631fad5ddf12438498f5e587fa6ed4dbaad1b06be51284a506843135`。扫描对 `scripts/generate_spdx_sbom.py`、示例配置、`config.py`、`corrections.py` 和 `doctor.py` 共 5/5 项完成复核，findings 为空，coverage 为 complete。它只覆盖冻结差异的静态审查，不替代 P1/P2、跨平台、多账户、Agent 宿主或远端 CI 验收。
- **其他门禁复验：** 全仓 Ruff、`uv lock --check`、敏感文件检查和 `git diff --check` 通过。SPDX 2.3 JSON Schema 校验通过；34 个包记录（项目 1 个、第三方 33 个）与 uv CycloneDX 导出的第三方名称/版本集一致。包许可证字段为 `NOASSERTION`，不能视为已获许可。
- **项目状态：** CLI-03 本地修复完成；真实媒体验收、P5/P6 外部决定、POSIX/macOS/Linux、多账户和远端 CI 仍未完成，整体 **NOT READY**。

## 17. 2026-10-09 ASR 环境与真实抖音页面复核

本节更新第 16 节之后的验收状态。ASR、Playwright/Chromium 安装由用户明确授权；本节没有将安装就绪误记为真实转写或媒体捕获通过。

- **ASR 环境：** 按 `uv.lock` 安装 `faster-whisper==1.2.1`、`av==15.1.0` 和依赖，并将 `Systran/faster-whisper-medium` 固定 revision `08e178d48790749d25932bbc082711ddcfdfbc4f` 下载到权限为 `ok` 的用户私有数据目录。随后 `doctor --json` 报告 `local_transcription=ready`。用户提供的是抖音网页链接，不是本地媒体；捕获未产生媒体文件，因此真实 ASR、听审和性能仍未运行，P1/P4 保持未通过。
- **浏览器环境（2026-10-09 快照）：** 已按用户授权安装 `playwright==1.63.0` 和 Chromium revision 1243。指定私有数据目录权限为 `ok`，显式个人输出目录 `%USERPROFILE%\Transcripts` 的权限检查为 `ok`；当时默认工作区输出目录因 D: 根 ACL 报告 `unsafe`。第 58 节已将该路径移出隐式默认；`doctor --json` 对当前选定数据目录及默认输出权限报告 `ready`。
- **真实链接结果：** 用户提供的一条精选页链接经项目 URL 解析为有效视频 ID。修正请求类型判定后，可见浏览器诊断的主文档返回 HTTP 200；页面请求中观察到 14 个资源主机，其中 13 个不在资源 allowlist，且没有媒体候选。通过 `retry-failed` 对该链接执行的新 CLI 尝试返回 `CAPTURE_NO_MEDIA`，没有生成媒体或正文，也未到达 ASR。诊断只保留主机名、资源类型和安全策略结论；没有保留 Cookie、签名媒体 URL、页面正文或逐字稿。P2 仅有 1/3 条链接且未完成媒体捕获，仍未通过。

### AUD-70：抖音页面资源主机未进入浏览器白名单（P2，阻断真实捕获）

- **证据：** 修正导航请求判定后，用户授权的真实页面主文档可返回 HTTP 200；诊断记录到 14 个资源主机，其中 13 个不在 `capture.py`/`browser_proxy.py` 资源白名单内并被拒绝，资源类型包含脚本、样式表和 XHR。最新 CLI 尝试以 `CAPTURE_NO_MEDIA` 结束，未产生媒体路径。补查公开 .com RDAP 时，所查域名的注册组织信息被隐去；本机 DNS CNAME 链指向共享 CDN 基础设施。这些信息仍不能证明具体主机归属或页面功能必要性。现有 `MEDIA_HOST_SUFFIXES` 面向媒体下载，不能直接作为网页脚本/API 允许列表。
- **影响：** 当前浏览器可启动并访问主文档，但不一定能运行页面脚本或触发媒体请求；真实抖音转写验收无法继续。若用过宽通配符仓促放开外域，会扩大代理的网络信任边界。
- **对策：** 逐项核实观察到的主机归属和必要性；只有确认必要且可信的页面资源主机才进入独立、精确的浏览器 allowlist，媒体下载 allowlist 继续独立管理。保持 HTTPS、公共 IP 验证和 DNS pinning；为批准域名、非批准域名、相似域名与导航重定向增加回归。不得根据一次失败自动放行外域。
- **状态：** 捕获阻断已复现，域名审查仍待证据；本轮未扩大白名单。

### AUD-71：页面元数据元素查找未设短超时（P2/P3，已整改）

- **证据：** locator 原先继承 Playwright 默认等待时间，缺失标题、作者或时间信息可能在多个 selector 上累积等待。
- **整改：** `BrowserCapture` 现在为 locator 设置 1 秒上限，并以默认 45 秒单调时钟绝对 deadline 约束导航、登录判断、元数据查询和浏览器 route DNS 校验；每次 DNS 校验同时保留原有 5 秒上限，自定义导航 timeout 不得超过总期限。截止时间耗尽返回稳定码 `CAPTURE_TIMEOUT`。回归模拟了导航、登录/元数据 locator 和 route DNS 的 deadline 行为。
- **验证：** 捕获、代理和 pipeline 定向回归 **53 passed, 1 skipped**；Ruff 通过。真实链接仍因没有可用媒体响应而未到 ASR；该问题与缺失 locator 的等待已分开记录。
- **状态：** 本地源码整改完成；真实媒体可用性仍由 AUD-70 和 P2 验收门槛覆盖。

### AUD-72：Playwright 导航请求方法被当作布尔属性（P2，可用性，已整改）

- **证据：** 锁定 Playwright 1.63.0 的 `Request.is_navigation_request` 是方法。浏览器请求守卫原先直接读取方法对象，导致它始终 truthy，子资源也被按精确导航 host 规则处理；即使某个子资源 host 已被资源策略信任，也会因此误拒绝。原 Fake Request 用布尔字段模拟，未发现 API 形状差异。
- **整改：** 守卫现在调用 `is_navigation_request()`，再分别执行导航精确 host 集和子资源 suffix 策略。回归 Fake Request 改为与 Playwright API 一样的无参方法，并覆盖获准媒体子资源通过、媒体域名不能作为顶层导航、非批准主机和 loopback 仍拒绝。
- **验证：** 捕获、代理和 pipeline 定向回归 **53 passed, 1 skipped**；Ruff 通过。修复后的可见浏览器仍未发现媒体候选，故未声称 P2 通过。

### AUD-73：doctor CLI 回归测试依赖可选组件缺失（P3，测试健壮性，已整改）

- **证据：** 安装 ASR、模型和浏览器后，完整测试发现 Windows UTF-8 CLI 用例仍断言 `doctor` 必须返回 `setup_required`。该断言把测试机可选依赖未安装当成固定条件，导致已正确返回 `ready` 的环境中测试失败。
- **整改：** 用例改为验证中文 UTF-8 输出、JSON 结构有效，并确认退出码与 doctor 实际状态一致；不再规定可选组件必须处于缺失状态。
- **验证：** 修复后 Windows Python 3.11.15 和 3.12.13 全套 pytest 各 **393 passed, 20 skipped**；全仓 Ruff 通过。
- **状态：** 本地修复完成。该项是测试环境假设问题，不是生产 `doctor` 功能缺陷。

- **第 17 节当时的测试基线：** Windows Python 3.11.15 与 3.12.13 各为 **393 passed, 20 skipped**，包含 P2 捕获和 AUD-73 修复，20 项为 POSIX 能力或 symlink 条件跳过。第 30 节记录新增 P3 回归后的更新基线。此前正式 Diff Scan `db94ca43-2337-42d0-ab6a-7369aeb6ad8e` 绑定 5 个源码/配置项的冻结快照，不覆盖第 17 节诊断证据或后续文档更新；后续扫描记录见第 18、27、33、36、39 节，其中第 39 节为最新扫描，第 36 节扫描为较早的 0 发现快照。
- **P6 许可盘点进展：** 当前 Windows Python 3.11 环境中 32/33 个锁定第三方版本已安装；29/32 个包提供许可证元数据。Colorama/Ruff 的安装包许可证文本已与精确发行版本核对；Tokenizers 通过精确 tag 的上游许可证文件确认。另已从内存检查锁定的 NumPy 2.5.3 CPython 3.12 Windows x64 wheel：SHA-256 与 `uv.lock` 相同，METADATA 声明 `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`，发现 20 个 license/notice 文件名条目；具体 bundled 文本及 macOS/Linux wheel 仍未逐项审阅，SPDX 保持 `NOASSERTION`。本机没有 WSL 发行版，POSIX 实机测试仍待其他环境。
- **仍需关闭：** 获取/成功捕获至少 60 秒媒体后完成 P1/P4；用可核验证据审查 AUD-70 的 13 个第三方资源主机，取得 P2 另外两条授权 URL 并完成三条端到端捕获；完成 Agent 宿主、远端矩阵、POSIX/macOS/Linux、多账户与所有者发布决定。AUD-71/72 本地代码整改已完成；整体保持 **NOT READY**。

## 18. 2026-10-09 冻结工作树差异安全复审

- **范围与快照：** Codex Security Diff Scan `3ecab5a0-71ce-4dc8-a614-2b3af2e2eadb`，base/head 均为 `b166778ee5283591a1b799535b746ba198e38653`，内容摘要为 `codex-security-snapshot/v1:sha256:5774937a34e1c76184f73e98fbbeb132b47410000633a2a875c5bcdec00449a5`。生成的安全敏感清单包含 6 项源码/配置，另复核相关文档与测试；威胁模型覆盖配置/本地存储、浏览器捕获、媒体下载、ASR、输出和第三方安装边界。
- **结果：** 候选项 0、报告级发现 0、coverage complete。没有确认此次冻结差异引入的可利用安全缺陷；空路径拒绝、浏览器请求分类与捕获 deadline、术语归档脱敏、doctor 路径回退以及 SPDX 生成器均未发现新的安全问题。此结果只适用于上述冻结快照。
- **方法限制：** 本次为静态代码和差异审查；没有运行测试或动态命令。相关测试文件仅作源码阅读。安全扫描报告由 Codex Security 在本机状态目录生成。
- **未关闭的项目验收：** 本次安全扫描不改变 P1/P4 状态：仍缺至少 60 秒且获授权的本地中文媒体样本，因此真实 ASR、听审和性能未验收。P2 目前仍只有 1/3 条链接的记录；已授权链接访问到 HTTP 200，但返回 `CAPTURE_NO_MEDIA`，没有下载媒体。需补另两条授权链接，并在有媒体归属/必要性证据后再审 AUD-70 的 13 个资源主机；在此之前保持 allowlist 严格。整体仍为 **NOT READY**。

## 19. 2026-10-09 状态文档一致性复核

- **DOC-25（阶段状态过期，已修正文案）：** 独立复核发现实施计划仍把安装前 `doctor=setup_required` 和“真实权重未下载”写成现状；主审核报告第 6 节及 SEC-17/AUD-58 阶段记录也有未注明时点的同类表述。用户授权安装后，固定模型、ASR 与 Playwright/Chromium 已准备，见第 17 节。此条写作时真实推理仍未完成；之后的真实样本结果见第 62、69 节，SEC-17 推理门槛已通过，P4 听审/长运行仍开放。发布报告已更新为第 18 节最新冻结差异扫描；补充审核报告已标明只记录第 15–16 节阶段证据。
- **2026-10-09 只读诊断：** 使用锁定项目环境和显式用户私有 data/output 路径复查 `doctor --json`，退出码 0，`overall=ready`，`local_transcription=ready`、`douyin_urls=ready`。这仅证明依赖/模型/浏览器能力就绪；本地音视频仍未提供，P1/P4 未通过。已授权页面仍为 `CAPTURE_NO_MEDIA`，P2 未通过；该次快照中的 D: 工作区输出权限为 `unsafe`，此路径已不再是隐式默认（第 58 节）。
- **复核范围与验证：** 本轮更改限审核/计划/发布记录；`git diff --check` 对所改文档未报空白错误。未运行测试或真实转写，也未重复抖音浏览器访问。整体保持 **NOT READY**。

## 20. 2026-10-09 NumPy 锁定 wheel 许可材料补查

- **发行物身份：** `uv.lock` 为 Python 3.12/Windows x86-64 锁定 NumPy 2.5.3 wheel SHA-256 `0a59a421a32580a009e8a1751345bf829631b990dc1794b80514ab722b435def`。从 PyPI 对应固定发行链接读取的 12,567,828 字节 wheel，其哈希与锁文件一致；未安装，未写入项目或持久缓存。
- **许可证元数据与包内材料：** wheel `METADATA` 的 `License-Expression` 为 `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`，与 [PyPI 固定版本页面](https://pypi.org/project/numpy/2.5.3/) 一致。wheel 含 20 个文件名包含 `LICENSE`、`LICENCE`、`COPYING` 或 `NOTICE` 的条目；这次只清点名称/大小，没有逐条判断许可证适用范围，也没有审阅 Linux/macOS wheel。
- **P6 状态：** 本次缩小了 NumPy 2.5.3 发行物身份和元数据的不确定性，但没有完成逐包许可证/notice、捆绑组件、PyAV/FFmpeg、项目 LICENSE、远端仓库或所有者发布决定。SPDX 继续使用 `NOASSERTION`，不得据此分发 wheel。项目整体仍为 **NOT READY**。
- **验证范围：** 下载到内存后计算 SHA-256 并读取 ZIP `METADATA`/文件名；未安装、未运行测试。文档 `git diff --check` 结果另见本轮工作记录。

## 21. 2026-10-09 重点锁定 Windows wheel 许可材料补查

- **发行物身份：** 按 `uv.lock` 固定 URL 读取 CTranslate2 4.8.2、FlatBuffers 25.12.19、ONNX Runtime 1.30.0、Tokenizers 0.23.2 和 Ruff 0.14.14 的 Windows wheel，并逐个核对 SHA-256；未安装或保留 wheel。详细上游链接和 ZIP 观察见 `docs/THIRD_PARTY_LICENSE_REVIEW.md`。
- **观察结果：** CTranslate2 wheel ZIP 没有 license/notice 路径，但含 CTranslate2、cuDNN、Intel OpenMP DLL 和原生扩展；FlatBuffers wheel 未见 license/notice 路径或原生二进制；Tokenizers wheel 未见 license/notice 路径但含原生扩展；Ruff wheel 含其 MIT `LICENSE` 和编译的 Rust 程序。ONNX Runtime 1.30.0 CPython 3.11/Windows x64 wheel（14,309,136 字节，SHA-256 `0edd0145a6e3fce8a1276491dc784d615e3c58bcb952c9b4e5c876d5c6a12ad7`）与 `uv.lock` 一致，ZIP 含 `onnxruntime/ThirdPartyNotices.txt`；该文件 344,457 字节、SHA-256 `c53a76501ef60db6f865f20599f220761201ac4057683acefdab37d861b86622`，安装副本哈希及大小也与 RECORD 一致。
- **许可边界：** 精确版本的上游许可证声明和 wheel 哈希核对并不能证明 wheel 内二进制及 Cargo/DLL 依赖的许可与归属已完整。ONNX Runtime notice 的内容及覆盖范围未逐条审阅；cuDNN、Intel OpenMP、Tokenizers/Ruff Cargo 子依赖、其他平台 wheel、PyAV/FFmpeg 配置/notice，以及发行是否包含 dev 工具仍待审查。
- **P6 状态：** 保留所有 SPDX 许可证字段为 `NOASSERTION`；项目 LICENSE、所有者决定、远端 CI/干净安装和任何二进制再分发审查未完成。上述补查不构成发布或再分发批准；项目整体仍为 **NOT READY**。
- **验证范围：** 只读检查精确锁定 wheel 哈希、固定版本上游许可证来源和有限 ZIP 清单；未安装、未运行测试。

## 22. 2026-10-09 当前工作树全套回归与发行包清单补查

- **全套回归：** 使用 Skill 目录已有的锁定 Windows Python 3.11 环境执行 `uv run --project .\skills\douyin-transcript --locked --no-sync pytest -q`；结果 **393 passed, 20 skipped, 0 failed**，耗时 316.31 秒。20 项跳过由 Windows 无法提供 POSIX FIFO/权限语义或当前文件系统不允许 symlink 创建导致；不代表 macOS/Linux 通过。
- **安装发行包清单：** 逐一比对 `uv.lock` 和该 Python 3.11 环境的 32 个已安装第三方版本，版本均一致；29 个提供 `License-Expression` 或 `License` 原值。安装记录中名称含 `license`/`notice`/`copying` 的 65 个候选文件均存在，逐个计算的 SHA-256 均与相应 `dist-info/RECORD` 一致。该验证不等于与每个平台锁定 wheel 的整体哈希比对，也没有逐份判断文本适用范围或许可义务；完整元数据表见 `THIRD_PARTY_LICENSE_REVIEW.md`。
- **PyPI 元数据交叉核对：** 对 32 个精确安装版本查询 PyPI 固定版本 JSON API；29 个提供 License 字段的值在忽略大小写和空白差异后与本地 `METADATA` 一致，Colorama/Ruff/Tokenizers 两侧均无该字段。该核对确认字段来源一致，不构成许可证批准。
- **ONNX Runtime notice：** 除第 21 节精确锁定 wheel 核验外，安装副本中 `onnxruntime/ThirdPartyNotices.txt` 的 344,457 字节和 SHA-256 也与该发行包 RECORD 相符。notice 存在性已确认，逐项条款解释和组件覆盖审查未完成。
- **P6 状态：** 本次关闭“ONNX Runtime 固定 Windows wheel 是否含第三方 notices”的存在性问题，并补齐当前 Windows 环境各安装包许可证元数据/文件清单证据；仍未完成第三方文本逐项审阅、DLL/Cargo/FFmpeg 组件核查、其他平台 wheel、项目 LICENSE、所有者发布决定、远端 CI 和干净安装。SPDX 保持 `NOASSERTION`，项目整体仍为 **NOT READY**。
- **本轮范围：** 只读核验与报告更新；未安装依赖、未改变源码。本轮测试结果为上述真实命令输出。

## 23. 2026-10-09 Codex Desktop Skill 发现验收准备

- **当前状态：** 本次对话启动时的 Codex Desktop Skill 清单没有 `douyin-transcript`；因此只有 CLI/标准校验/离线副本冒烟证据，没有新会话宿主发现或真实对话调用证据，P5 仍 **PARTIAL**。
- **repo-scoped 入口：** 已新增 `.codex/skills/douyin-transcript/SKILL.md`，明确指向 canonical `skills/douyin-transcript/SKILL.md` 和该目录中的 CLI 项目，不复制实现代码。canonical 与入口目录均通过固定 `skills-ref==0.1.1 agentskills validate`；当前目标 repo/user Codex skill 路径检查结果均为不存在（入口创建前）。OpenAI 的 [Codex Skill eval guide](https://developers.openai.com/blog/eval-skills) 展示 repo-scoped `.codex/skills/<name>/SKILL.md` 与 user-scoped `~/.codex/skills/<name>/SKILL.md`，并建议显式触发和验证 Agent 调用。
- **验收步骤：** 在新 Codex Desktop 会话确认 `/skills` 能列出入口并显式调用 `$douyin-transcript`。先用安全的 `doctor --json` 或获授权链接 `--dry-run --json`，将可执行文件和参数分开传递；保留 Desktop 工具轨迹并确认回复只含状态/路径摘要，不把正文放入上下文。
- **范围限制：** 本次只添加 repo-scoped 入口，没有修改用户级 Codex 配置；当前会话不会因文件新增而刷新技能清单，也未运行新的宿主会话。真实转写、正文隔离、听审与性能仍需 P1/P4 的授权本地媒体样本。P5 不能代替这些阶段门。

## 24. 2026-10-09 锁定发行物许可证声明证据与 SPDX 更新

- **发行物身份：** 对 `uv.lock` 中 33 个第三方版本，读取了 28 个精确 sdist 与 5 个无 sdist 记录的 Windows/Python 3.11 wheel，共 135,567,678 字节；全部 artifact SHA-256 与锁文件一致。发行物仅在内存中读取，未安装或保留。
- **作者元数据：** 从每个精确发行物的 `PKG-INFO` 或 `.dist-info/METADATA` 提取包作者字段，并记录元数据条目 SHA-256。新证据清单 `docs/third-party-license-evidence.json` 保存版本、字段原值、artifact URL/hash/size 和元数据路径/hash；生成器对照 `uv.lock` 验证 artifact 身份，只复制有效 SPDX 表达式，不转换旧式自由文本。
- **SPDX 更新：** 28/33 个第三方包的有效表达式现进入 `licenseDeclared`；Colorama（无声明字段）、FlatBuffers（`Apache 2.0`）、ONNX Runtime（`MIT License`）、Ruff（无字段）和 Tokenizers（无字段）仍为 `NOASSERTION`。项目包也因所有者尚未选择许可证而保留 `NOASSERTION`。所有包的 `licenseConcluded` 均保持 `NOASSERTION`，因为文件级、notice、捆绑组件与发行范围审查未完成。
- **发行物差异：** Protobuf 锁定 sdist 的 `PKG-INFO` 将 License 写为 `BSD-3-Clause`，当前安装 Windows wheel 的 `METADATA` 则为旧式 `3-Clause BSD License`。SBOM 中该包声明明确采用证据清单所列精确 sdist 来源；这不替代 wheel 内容和组件义务审查。
- **生成与验证：** 使用更新后的 `scripts/generate_spdx_sbom.py` 重建 `docs/third-party-sbom.spdx.json`，生成 34 个包记录和 47 个依赖关系。生成器把许可证证据清单摘要纳入 document namespace，并在锁定 artifact 或元数据证据不匹配时失败关闭。
- **本轮质量检查：** `tests/unit/test_spdx_sbom.py` **2 passed**；生成器 Ruff 检查、敏感文件检查和 `git diff --check` 通过；JSON 计数核对为 34 个包、28 个第三方声明、5 个未声明第三方包和 47 个关系。本次未重跑全套测试；上一轮完整结果见第 22 节。
- **未关闭门禁：** 当前元数据抽样只使用锁定 sdist 或 Windows/Python 3.11 wheel，不代表每个平台 wheel 的元数据、notice、DLL/Cargo/FFmpeg 捆绑组件或文件内容均已审查。项目 LICENSE、所有者决定、远端 CI/干净安装，以及 P1/P4、P2、P5 与跨平台验收仍开放，项目整体保持 **NOT READY**。

## 25. 2026-10-09 锁定许可证文件证据与跨版本回归复核

- **许可证文件核验：** 从 `uv.lock` 对应 Colorama 0.4.6 wheel、ONNX Runtime 1.30.0 Windows/Python 3.11 wheel、Ruff 0.14.14 Windows x64 wheel 和 Tokenizers 0.23.2 sdist 提取许可证文件。四个完整发行物的 SHA-256 与锁文件一致；各 license 文件哈希已记录在 `docs/third-party-license-evidence.json`。ONNX wheel 内的 `ThirdPartyNotices.txt` 为 344,457 字节，SHA-256 `c53a76501ef60db6f865f20599f220761201ac4057683acefdab37d861b86622`，同样绑定到锁定 wheel。临时提取目录在检查结束后清理，没有把这些发行物留在仓库。
- **SPDX 变化：** 生成器现校验附加许可证文件/notice 所属发行物是否被 `uv.lock` 固定，并检查路径、文件哈希格式、许可证表达式及 notice 大小。Colorama `BSD-3-Clause`、ONNX Runtime `MIT`、Ruff `MIT`、Tokenizers `Apache-2.0` 进入 `licenseDeclared`；FlatBuffers 继续为 `NOASSERTION`，因为固定 wheel 没带许可证文件，旧式 `Apache 2.0` 也不是 SPDX 表达式。清单为 34 个包（含项目）、47 个关系、32 个第三方 `licenseDeclared`；当前生成回归确认包/关系集合可由 `uv.lock` 重现。项目和 FlatBuffers 未断言。34 个包的 `licenseConcluded` 全部保持 `NOASSERTION`。ONNX 第三方 notice 所列条目尚未映射到链接二进制。
- **回归：** 完成 Windows Python 3.11.15 全套 pytest **393 passed, 20 skipped**（227.50 秒）和 Python 3.12.13 全套 pytest **393 passed, 20 skipped**（411.46 秒）。跳过项涉及 Windows 无法提供的 POSIX FIFO/权限语义或文件系统 symlink 能力。随后修改的仅为 SBOM 生成器、证据与文档，针对 `tests/unit/test_spdx_sbom.py` 的当前代码快照再跑 **4 passed**。生成 SBOM 通过 SPDX 2.3 官方 JSON Schema 校验；全仓 Ruff、`uv lock --check`（34 packages）、敏感文件检查和 `git diff --check` 均通过。
- **安全扫描范围：** 第 18 节正式 Diff Scan 早于本次生成器证据校验逻辑更新；本轮未运行新的正式差异扫描。新增逻辑有锁文件身份失败关闭回归和全仓 Ruff，但不能把先前冻结快照扫描描述为覆盖本次改动。
- **未关闭门禁：** 许可证文本声明不等于对 DLL/Cargo/FFmpeg 捆绑材料和最终交付义务的结论。PyAV/FFmpeg、ONNX notice 组件映射、其他平台 wheel、项目 LICENSE、所有者发布决定、远端 CI/干净安装，以及 P1/P4 本地媒体、P2 另两条 URL 和媒体捕获、P5 新 Desktop 会话与 POSIX/macOS/Linux/多账户仍未完成；整体保持 **NOT READY**。

## 26. 2026-10-09 ONNX Runtime 第三方 notice 内容复核

- **发行物身份：** 重新读取 `uv.lock` 固定的 ONNX Runtime 1.30.0 CPython 3.11/Windows x64 wheel，14,309,136 字节，SHA-256 `0edd0145a6e3fce8a1276491dc784d615e3c58bcb952c9b4e5c876d5c6a12ad7`，与锁记录一致。`onnxruntime/ThirdPartyNotices.txt` 为 344,457 字节、6,369 行，SHA-256 `c53a76501ef60db6f865f20599f220761201ac4057683acefdab37d861b86622`。wheel 内有 `onnxruntime.dll`、`onnxruntime_providers_shared.dll` 和 `onnxruntime_pybind11_state.pyd`。
- **notice 条款：** notice 中的 Intel MKL / Intel Simplified Software License 写有再分发条件，并明确禁止反向工程、反编译和反汇编。Mbed TLS 条款虽列出 Apache-2.0 或 GPL 2+ 两种许可，但明确说明该发行选择 Apache-2.0。因此，仅凭 notice 中出现 GPL/LGPL 名称，不能推断该 Windows wheel 的二进制就受这些许可约束。
- **证据边界：** notice 是较广的 third-party attribution 清单，未映射到 wheel 的具体链接组件；未观察到独立 MKL DLL 也不能排除静态链接。wheel 内 `onnxruntime/LICENSE` 支持该发行包的 `licenseDeclared=MIT`，但不构成整个二进制组件清单的 `licenseConcluded`，也不是本仓库的项目许可证（当前仓库根目录没有 `LICENSE`）。若把该 wheel 或含它的二进制纳入本项目交付，仍需确认实际链接/使用组件、保留 notice 并逐项核对适用义务。
- **对策与状态：** 将 ONNX notice/链接映射和二进制交付范围保留为 P6 发布前门槛；当前 Skill 仓库不包含该 wheel。此复核仅记录锁定 Windows wheel 的 notice 内容，不构成法律意见或再分发批准；P6 和项目整体仍为 **NOT READY**。
- **复核范围：** 精确 wheel 通过固定 URL 读取至内存并核对大小/SHA-256，只检查 notice 条款上下文及二进制成员名称；未安装、未保留 wheel，也未核对其他平台 wheel、构建配置、静态链接或完成法律判断。
- **后续上游文本对照：** 固定版本 `v1.30.0` 上游 `ThirdPartyNotices.txt` 与项目锁定环境中的安装 notice 均含 Intel MKL 与 Mbed TLS；6370 行内容在 CRLF/LF 归一化后完全相同，原始大小/hash 差异来自换行格式。notice 条目尚未映射到实际链接组件，见第 34 节。

## 27. 2026-10-09 冻结工作树正式 Codex Security Diff Scan

- **扫描身份与快照：** Scan ID `a8580877-90c1-4c8f-9a68-ed0580c3c827`，目标 HEAD `b166778ee5283591a1b799535b746ba198e38653`，工作树快照 digest `codex-security-snapshot/v1:sha256:b8398d388b5369a3bebde2903ead279f65909278b6535968bb9f262a890debc2`。正式扫描报告保存在 Codex Security 本机私有状态中；具体本机路径不写入项目报告。
- **覆盖与结论：** 六个变更审查项全部完成，coverage 为 complete，无排除项或延后项，0 个可报告发现。覆盖文件为 `scripts/generate_spdx_sbom.py`、`skills/douyin-transcript/assets/config.example.toml`、`skills/douyin-transcript/src/douyin_transcript/capture.py`、`config.py`、`corrections.py` 和 `doctor.py`；相关架构、CLI、路径安全、下载、输出和 SPDX 证据代码也一并复核。
- **驳回候选：** `doctor` 的默认文本诊断会输出配置异常文本，其中可能含所选配置路径。静态追踪确认，路径源为本机 `--data-dir`、`DOUYIN_TRANSCRIPT_HOME` 或本机默认目录，JSON 模式会转义控制字符；没有证据表明远端或更低权限输入能控制该路径，因此按 self-only 本机触发候选驳回，不计为安全发现。若维护者希望进一步统一终端显示，可在 doctor 的文本详情输出应用 `strip_display_controls`，并增加 POSIX 合成路径回归。
- **方法与限制：** 本次为静态源码审查，没有运行测试、真实浏览器捕获或 ASR；Windows 环境没有 POSIX 终端动态复现。审查绑定上述冻结快照；本节和补充报告的状态指针在扫描封存后更新，不属于该快照。
- **仍开放的验收门槛：** 安全差异扫描通过不关闭产品验收项。P1/P4 仍需至少 60 秒且获授权的本地中文媒体；P2 已提供的一条抖音链接未捕获媒体，仍需另外两条授权链接；P5 需要新 Codex Desktop 会话确认 Skill 发现与真实调用；P6 仍需所有者确定项目许可证、远端仓库/CI 与发行授权，并完成依赖和目标平台二进制审查。整体继续 **NOT READY**。

## 28. P3 多进程数据库争用验收

- **计划要求：** P3 步骤 7 明确要求数据库由两个进程同时打开时，同一任务不能被并行处理；P6 发布门还要求批量断点测试通过。
- **现有证据：** `tests/unit/test_pipeline.py::test_ten_item_batch_isolates_failures_reuses_cache_and_deduplicates` 覆盖 10 项混合批次。新增的 `tests/unit/test_tasks.py::test_separate_processes_claim_one_database_task_only_once` 启动两个独立 Python 子进程，使用同一临时数据库并同时 claim 同一待处理任务。
- **结果：** 两进程回归通过；恰有一个进程获得 claim，任务的 `claim_generation` 和 `attempt_count` 均为 1。没有发现生产代码缺陷，计划明确要求的数据库 claim 互斥已有进程级证据。
- **限制与后续：** 该回归直接验证 TaskStore 的 SQLite claim 边界，不驱动两个完整 CLI 到真实下载/ASR，也不验证进程中断后重启的跨进程端到端恢复；这些仍需真实批次或 CLI 集成证据。
- **状态：** 进程级数据库 claim 回归已补充；真实 P1/P2 媒体链路和发布断点验收仍保持开放。

## 29. P3 50 项混合批次测试补齐

- **原记录：** 第 9 节 AUD-17、`docs/PROJECT_IMPLEMENTATION_PLAN.md` 的 P3 勾选项和 `docs/ACCEPTANCE.md` 曾称 50 项混合任务模拟已覆盖缓存命中、失败、重复、并发上限、串行 ASR 与输出计数。
- **发现：** 先前检查在 `tests/` 中只找到 50 条输入上限用例，没有混合调度用例；然而 AUD-17 曾记录该测试已通过，导致计划状态和仓库源码不一致。
- **整改：** 新增 `tests/unit/test_pipeline.py::test_fifty_item_mixed_batch_bounds_downloads_and_keeps_asr_serial`。用例建立 8 项成功缓存，再提交 50 项混合清单，覆盖缓存跳过、失败隔离、重复失败/成功项、两并发下载、串行 ASR、48 个唯一任务、45 个成功输出/缓存文件及完整结果计数。
- **验证：** 与独立进程 claim 用例一同定向运行，**2 passed**；当时 Python 3.11.15 全套 pytest **397 passed, 20 skipped**（143.31 秒），Python 3.12.13 全套 **397 passed, 20 skipped**（322.67 秒）；当前回归结果见第 32 节。
- **限制与状态：** 这是离线模拟，不验证真实网络、媒体或 ASR。当前测试源码证据已补齐；此前缺失的历史版本不再作为验收依据。

## 30. P3 回归后的当前本机验证

- **Python 3.11.15 全套：** 当前工作树下完成，**399 passed, 20 skipped**，耗时 321.02 秒。跳过项为 Windows 主机不可提供的 POSIX FIFO/权限语义或符号链接能力。
- **Python 3.12.13 全套：** 在独立虚拟环境完成 **399 passed, 20 skipped**，耗时 230.71 秒；没有替换项目默认 Python 3.11 环境。
- **P3 新增用例：** 50 项混合批次和两个独立进程争抢同一任务 claim 的定向回归 **2 passed**。
- **其他定向验证：** `tests/unit/test_spdx_sbom.py` 在两个 Python 版本下各 **6 passed**。全仓 Ruff、`uv lock --check`、`python scripts/check_sensitive_files.py` 和 `git diff --check` 均通过。Git 输出了已知的 LF→CRLF 转换提示，没有空白错误；敏感文件检查覆盖 Git 可见路径。
- **版本限制：** 两套完整回归已包含本轮新增 P3 测试；最终发布快照仍须按发布清单重跑本地检查。该工作树扫描不改变 P1/P2/P4/P5/P6 的真实验收缺口，整体仍为 **NOT READY**。

## 31. FlatBuffers 25.12.19 上游许可证来源补核

- **发行物：** `uv.lock` 固定的 `flatbuffers 25.12.19` universal wheel SHA-256 为 `7634f50c427838bb021c2d66a3d1168e9d199b0607e6329399f04846d42e20b4`。锁定 wheel 中没有许可证文件，元数据 `License` 字段为旧式字符串 `Apache 2.0`，不是 SPDX 表达式。
- **新增来源证据：** PyPI 固定版本页将该版标为 Apache Software License (Apache 2.0)；上游 [v25.12.19 `python/setup.py`](https://github.com/google/flatbuffers/blob/v25.12.19/python/setup.py) 将包版本写为 `25.12.19`、许可证写为 `Apache 2.0`；同一标签的 [`LICENSE`](https://github.com/google/flatbuffers/blob/v25.12.19/LICENSE) 是 Apache License 2.0。详见 [PyPI 固定版本页](https://pypi.org/project/flatbuffers/25.12.19/)和 `docs/THIRD_PARTY_LICENSE_REVIEW.md`。
- **结论边界：** 这项来源采集没有证明标签文件属于锁定 wheel，也没有构建证明把该 wheel 绑定到 Git 标签。采集后的单项声明映射及其约束见第 32 节；不把上游文件记作 wheel 内容，也不据此得出 `licenseConcluded` 或批准二进制再分发。

## 32. FlatBuffers 旧式许可证值的精确 SPDX 映射

- **变更：** 对锁定 `flatbuffers 25.12.19` 的旧式 `License: Apache 2.0` 元数据值，更新证据清单与 SPDX 生成器，将 `licenseDeclared` 映射为 `Apache-2.0`。映射键完整限定包名、版本、metadata 字段和值、metadata SHA-256 与锁定 artifact SHA-256；三条固定来源为 PyPI 版本页、上游同版本 `python/setup.py` 和该标签 `LICENSE`。
- **限制：** 生成器只接受上述完整键及固定来源列表。锁定 wheel 内没有许可证文件，外部标签文件不被当作 wheel 内容。FlatBuffers 的 `licenseConcluded`、项目自身 `licenseDeclared` 以及全部 34 个包的 `licenseConcluded` 仍为 `NOASSERTION`；该映射不构成法律审阅或二进制分发批准。
- **回归：** `tests/unit/test_spdx_sbom.py` 在 Python 3.11.15 和 3.12.13 上均为 **6 passed**，覆盖映射写入、清单重建，以及被篡改旧式值或来源的拒绝。两套全仓 pytest 均为 **399 passed, 20 skipped**（Python 3.11：321.02 秒；Python 3.12：230.71 秒）。全仓 Ruff、`uv lock --check`、敏感文件检查和 `git diff --check` 均通过。生成物为 34 个包记录、47 个关系、33 个第三方声明；前一节记录的 SPDX 2.3 JSON Schema 校验保持适用，本轮未改变文档结构或 SPDX 字段集。
- **安全扫描范围：** 第 27 节既有正式 Diff Scan 绑定较早冻结快照，不覆盖本节新增映射逻辑。映射加入后另行完成正式 Codex Security Diff Scan，编号 `06b2789a-8835-4dfb-a214-4ac550fcaba0`；结果和范围见第 33 节。
- **剩余门禁：** 其余依赖捆绑组件/notice、其他平台 wheel、PyAV/FFmpeg、项目 LICENSE、远端 CI 和所有者发布决定仍未完成。P1/P4 样本、P2 另外两条授权链接、P5 新 Desktop 会话及 POSIX 实机验证也仍开放，项目整体 **NOT READY**。

## 33. 2026-10-09 前次工作树正式 Codex Security Diff Scan

- **扫描身份：** Codex Security Diff Scan `06b2789a-8835-4dfb-a214-4ac550fcaba0`，比较 HEAD/base `b166778ee5283591a1b799535b746ba198e38653` 与同一工作树快照，摘要 `codex-security-snapshot/v1:sha256:d9865be8ca3153ecaa2beab9f38b5c04c24c5435adc59291b60e1281f1fd77dd`。
- **结果：** coverage 为 **complete**，审阅 6 个变更源码项及相关测试差异，0 个候选项、0 个报告漏洞。覆盖面包括 SPDX 映射和生成器、示例配置路径说明、浏览器捕获 deadline 与请求守卫、空路径解析、术语更正归档隐私，以及 doctor 输出路径诊断。
- **审阅边界：** 扫描是静态工作树差异审阅；不表示整个仓库所有历史代码无问题，也没有执行真实媒体处理、对抗性运行时测试或跨平台文件系统验收。完整扫描报告保存在 Codex Security 本机私有状态中；具体本机路径不写入项目报告。
- **发布状态：** 本次扫描没有关闭 P1/P4 本地样本与听审、P2 另外两条链接及真实媒体捕获、P5 新 Desktop 会话、P6 许可证/仓库/CI 所有者决定，或 POSIX 实机验收；项目整体继续 **NOT READY**。本节及扫描指针在扫描封存后加入报告，报告文字本身不属于该扫描快照。

## 34. 2026-10-10 P6 固定版本依赖上游来源对照

- **范围确认：** `skills/douyin-transcript/pyproject.toml` 的基础运行依赖为空；PyAV/faster-whisper 在 `asr` extra、Playwright 在 `browser` extra、Ruff 在 dev group，wheel 构建配置仅包含 `src/douyin_transcript`。当前是源 Skill 交付范围；`uv.lock`/SBOM 还包含可选和开发组件，未来改变交付形态时需重新圈定清单。详细证据和链接见 `docs/THIRD_PARTY_LICENSE_REVIEW.md`。
- **CTranslate2 / Rust wheel：** CTranslate2 v4.8.2 上游文档列出 OpenMP、cuDNN、MKL 等可选构建后端，但不证明锁定 PyPI wheel 的实际配置。Tokenizers v0.23.2 的上游 Cargo manifest 排除了 `Cargo.lock`；Ruff v0.14.14 的上游 LICENSE 除 MIT 正文外含外部维护库归属材料。仍缺与具体 wheel 哈希绑定的构建清单、解析后依赖图及完整 license/notice 文件映射。
- **ONNX Runtime notice 核对：** 本轮在项目锁定环境中只读核对版本 1.30.0 的安装 notice：344,457 字节，SHA-256 `c53a76501ef60db6f865f20599f220761201ac4057683acefdab37d861b86622`，包含 Intel MKL 与 Mbed TLS 文本；官方标签原始文件为 338,088 字节，SHA-256 `143764b952fdb1a7c69ce653bfba74a7744d6a8a573bfb73e235fba356c83de3`，同样含这两个条目。6370 行文本在 CRLF/LF 统一后完全相同，故字节哈希不同是换行格式差异，不是 notice 内容差异。实际链接组件映射仍未完成，ONNX 的 `licenseConcluded` 继续 `NOASSERTION`。
- **安装目录许可证材料抽查：** 当前 Python 3.11 Windows 环境的 32 个锁定第三方安装包中找到 65 个候选 license/notice 文件；文件均存在，SHA-256 与各自安装 `RECORD` 一致。候选文件名筛选会误收 `AUTHORS` 等非许可证材料及 `packaging/licenses/` 下的 Python 源码，也可能漏掉名称不含 license/notice/copying 的材料。Playwright 安装内容含 Node driver、`ThirdPartyNotices.txt` 和若干组件许可证文件；NumPy 安装内容含多份 vendored 组件许可材料。此清点是本机安装记录的完整性/内容线索，不是独立 wheel 哈希、构建来源、组件适用性或法律结论；详见 `docs/THIRD_PARTY_LICENSE_REVIEW.md`。
- **PyAV / FFmpeg：** PyAV v15.1.0 `scripts/build-deps` 源码 helper 含 `--enable-gpl` 与 `--enable-libx264`，属于上游构建线索，不能证明锁定的 PyPI wheel 使用同一配置。FFmpeg 官方材料区分默认 LGPL 与启用 GPL 组件后的许可路径，并点名 libx264；仍需对 Win/macOS/Linux 每个锁定 wheel 获取对应 FFmpeg 版本、configure 参数、捆绑组件、notice、源码及构建来源。
- **发布对策：** 先由仓库所有者确定只分发源代码还是把可选依赖/native binaries 纳入产品，再索取每个实际交付 wheel 的 build manifest、BOM/依赖图、license/notice 和必要源码。只在证据绑定到 artifact 后更新组件映射与 SBOM；保留所有未证实的 `licenseConcluded=NOASSERTION`。本节是固定版本技术来源复核，不是法律意见或分发批准，也不在第 33 节冻结扫描快照内；项目 LICENSE、remote、远端 CI/干净安装和所有者授权仍未完成，P6 与整体项目继续 **NOT READY**。

## 35. 2026-10-10 P0 锁定环境就绪复核

- **命令范围：** 从项目锁定环境以 `uv run --project skills/douyin-transcript --locked --no-sync` 调用 `douyin-transcript doctor --json`，显式提供用户私有数据目录和安全输出目录；没有运行同步、安装或下载步骤，报告中不记录本机目录值。
- **结果：** 退出码 0，`overall=ready`，`local_transcription=ready`、`douyin_urls=ready`。Python、faster-whisper、decoder、固定模型、Playwright、Chromium、config、data directory、task database、browser profile、media cache、output directory、相关权限及磁盘空间共 15 项检查均为 `ok`。
- **验收边界：** 这项复核确认当时 P0 本机环境就绪；不表示已处理本地媒体或成功捕获抖音视频。P1/P4 仍需授权本地样本，P2 仍为 `CAPTURE_NO_MEDIA` 且缺另外两条授权链接；当时检查的 D: 工作区输出权限为 `unsafe`，但第 58 节已将其移出隐式默认。项目整体继续 **NOT READY**。

## 36. 2026-10-10 AUD-74/SEC-35 回归与正式差异安全审查

- **整改与回归：** AUD-74 修复混合输出目录重试摘要：顶层 JSON `output_dir` 变为 `null`，各 item 保留真实目录，文本摘要明确报告多个目录。SEC-35 将 URL 路径令牌、敏感头和敏感查询值在任务持久化、旧版 `status --json`、JSON/文本摘要和 quiet stderr 中统一脱敏，并移除显示控制字符。CLI、tasks、pipeline 定向回归 **8 passed**（1.14 秒）；全仓 Ruff、敏感文件检查和 `git diff --check` 通过。
- **完整回归：** Windows Python 3.11.15 全套 **404 passed, 20 skipped**（231.47 秒）；Python 3.12.13 全套 **404 passed, 20 skipped**（411.48 秒，profile-local 锁定开发环境）。跳过项为 Windows 无法提供的 POSIX FIFO/权限语义和符号链接能力；不能据此声称 POSIX 实机通过。未在本节重新运行测试。
- **正式扫描身份：** Codex Security Diff Scan `db5f86a0-b1ce-4b8b-a354-8c63fb68d1d4`，冻结快照 digest `codex-security-snapshot/v1:sha256:3fb485452862ea12fc202f4a41af615bb3810c557082d76d42360c7f0678d5a5`，对比基线/HEAD `b166778ee5283591a1b799535b746ba198e38653`。coverage 为 **complete**，94 个变更路径中安全审查工作清单含 10 个源代码项，全部审阅，0 个候选、0 个报告漏洞。完整扫描报告保存在 Codex Security 本机私有状态中；具体本机路径不写入项目报告。审查项为 SPDX 生成器、示例配置、capture、CLI、config、corrections、doctor、output、tasks、text_safety。
- **扫描边界与记录：** 静态冻结差异审阅，没有运行应用或外部网络测试；不表示全仓代码、真实抖音捕获、模型推理、Agent 宿主或跨平台行为没有问题。扫描预检 helper 结果为 ready，未发现 unmet/unknown 检查；但在工作台推进到 threat-model phase 后才尝试写入预检结果，因此封存记录中的 `preflightProgress` 为 0/0。后续扫描应先登记预检，再推进阶段。
- **剩余问题与对策：** P1/P4 仍没有本地音视频样本，需用户提供至少 60 秒且授权处理的中文媒体，完成真实推理、三处听审、10 分钟以上运行及 stdout/stderr/Agent 正文隔离检查。P2 仅有 1 条授权 URL，页面 HTTP 200 但 CLI 返回 `CAPTURE_NO_MEDIA`；还需另外 2 条授权 URL，并完成三条端到端捕获。在证明页面资源主机归属与必要性前保持 allowlist 不变。P5 需在新 Codex Desktop 会话确认发现和实际调用；P6 需所有者作出 LICENSE/仓库/发布决定并完成远端 CI、干净安装和第三方依赖/二进制通知审查。项目整体继续 **NOT READY**。

## 37. 2026-10-10 AUD-76/77 恢复解码时限与浏览器 UDP 边界

### AUD-76：stale task recovery 同步完整解码缓存媒体（P2，可用性，已整改）

- **复核证据：** `_recover_stale_tasks()` 原将完整 `_validate_media()` 交给 `TaskStore.recover_interrupted()`；恢复器会逐项串行处理 stale 任务。supervised worker 在 deadline 缺省时为每次校验使用两小时固定时限，因此多个大型或畸形缓存会在新任务开始前累加阻塞。AUD-53 已将校验移出 SQLite 写事务，但没有消除启动等待。
- **整改：** 恢复阶段使用 `TaskStore` 默认的快速完整文件检查，不解码媒体。缓存被认领并开始处理后，现有 `_transcribe_claimed()` 仍执行严格解码和媒体身份校验，并受该任务 `max_processing_seconds` 期限限制；不完整文件不会被恢复为可复用缓存。
- **验证：** 新回归构造带缓存的 stale `transcribing` 任务，确认 recovery 不调用媒体解码器、任务随后正常认领并在转写路径只校验一次；另一回归确认损坏缓存仍触发原有重新捕获回退。与浏览器策略两项新增回归合计 **4 passed**（1.12 秒）；变更 Python 文件 Ruff 检查通过。该节记录时尚未重跑全套，随后于第 38、40 节分别完成两次当前树全套复验。
- **剩余限制：** 实际超长媒体性能、损坏缓存行为和 Linux/macOS 实机尚未验证；真实 ASR/P1 仍待用户提供授权样本。

### AUD-77：Chromium WebRTC UDP 可绕过 HTTP CONNECT 代理（P2，网络边界，未解决）

- **复核证据：** 浏览器代理仅代理 HTTP(S) CONNECT、WebSocket 和受 Playwright 路由检查的页面请求；WebRTC UDP 不经过这些控制。Chromium 官方 `WebRtcIPHandling` 文档称 `disable_non_proxied_udp` 会限制非代理 UDP：[Chromium WebRtcIPHandling policy](https://chromium.googlesource.com/chromium/src/+/376fc41e87a058f7a7b300b0ec3a4982b4ec0960/components/policy/resources/templates/policy_definitions/Miscellaneous/WebRtcIPHandling.yaml)。但锁定环境的动态结果与文档预期不符：Playwright 1.63.0 / Chromium revision 1243 的正向对照能把合成 STUN UDP 送达本机接收端；实际 `BrowserCapture` 使用本机 HTTP 代理、启动参数中已确认含 `--force-webrtc-ip-handling-policy=disable_non_proxied_udp` 时，合成 UDP 仍分别到达 loopback 和当前局域网接口上的本机接收端。
- **测试边界：** 所有接收端只绑定本机回环或本机私有接口，没有访问外网。策略参数已在 Chromium 实际命令行中确认；故这不是单纯的单元测试参数缺失。现有 Playwright route、代理、host allowlist 与 DNS pinning 未拦截这些 UDP 包。当前证据来自一次性本机验证 harness，尚未纳入仓库集成回归；应把 loopback/LAN 拒绝与受控代理 HTTPS 正向用例纳入可重复验收。官方策略文档与本次锁定二进制行为存在差异，需要以目标二进制实测为准。
- **影响：** 页面脚本可诱发浏览器向 loopback 与局域网地址发送不受 host allowlist/DNS pinning 约束的 UDP 流量，可能探测本机或局域网服务。当前证据只确认 UDP 到达本机接收端；没有证明响应读取、数据外传或对服务的进一步利用。
- **当前代码：** Chromium 仍强制设置 `--force-webrtc-ip-handling-policy=disable_non_proxied_udp` 并拒绝调用方覆盖。该配置只能作为纵深防护；本次动态验收证明它没有关闭当前 Chromium 中的直连路径，不能计为漏洞修复。
- **对策与发布门槛：** 在 Chromium 进程级部署并验证出站隔离，拒绝未代理 UDP、loopback 与私网连接，只允许其连接受控代理；加入锁定 Chromium 的本机 loopback/LAN 拒绝验收，再验证代理 HTTPS 页面仍能正常捕获。可额外禁用页面的 WebRTC API 作为纵深防护，但不能替代操作系统或沙箱网络隔离。当前未修改系统防火墙，也未声称该边界已修复；在具备隔离和动态拒绝证据前，严格 host allowlist 的 P2 安全门槛保持未通过。
- **实现约束 / 所有者决策：** 没有通用 Playwright/Chromium 参数能提供这个进程级边界。Windows 可评估按 Chromium 规范化应用路径匹配的 WFP ALE 过滤器；它必须覆盖 IPv4/IPv6，并把唯一例外精确限制为受控代理的 TCP loopback 端口。普通 Windows Firewall 规则中显式 block 优先于冲突 allow，不能简单叠加“阻止 Chromium”与“允许本地代理”；动态 WFP session 结束时过滤器会清除，因此 native helper 还需监督并终止 Chromium 进程树、验证异常退出生命周期。WFP 应用身份与访问模型见 [ALE](https://learn.microsoft.com/en-us/windows/win32/fwp/application-layer-enforcement--ale-)、[filter conditions](https://learn.microsoft.com/en-us/windows-hardware/drivers/network/filtering-condition-identifiers)、[WFP access control](https://learn.microsoft.com/en-us/windows/win32/fwp/access-control)、[dynamic sessions](https://learn.microsoft.com/en-us/windows/win32/fwp/object-management)；普通规则优先级见 [Windows Firewall rules](https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/rules)。Linux 可评估受限 network namespace + nftables，并通过受控接口暴露代理；[network namespaces](https://man7.org/linux/man-pages/man7/network_namespaces.7.html) 隔离网络设备、路由、防火墙和 socket，配置通常需要相应系统能力。macOS 可评估签名和获准的 [Network Extension content filter](https://developer.apple.com/documentation/BundleResources/Entitlements/com.apple.developer.networking.networkextension)，部署条件见 [TN3134](https://developer.apple.com/documentation/technotes/tn3134-network-extension-provider-deployment)。这些方案涉及特权、原生组件、崩溃恢复与多平台维护。需项目所有者决定是否接受随项目交付并申请提升权限的系统适配，还是要求使用者预先配置并验证组织级进程隔离；当前都尚未实施。

## 38. 2026-10-10 当前工作树回归与剩余门槛复核（较早复跑）

本节记录当时完成的 407/20 全套复跑；后续第 40 节重复运行得到相同通过/跳过数量。第 38 节记录的耗时 232.06/413.75 秒已由第 40 节更晚的 141.59/407.76 秒取代，当前状态指针以第 40 节为准。

- **全套回归：** Windows Python 3.11.15 使用 `uv run --project .\skills\douyin-transcript --locked --no-sync --group dev pytest -q`，结果 **407 passed, 20 skipped**，232.06 秒。Python 3.12.13 使用锁定 profile-local 开发环境运行 `python -m pytest -q`，结果 **407 passed, 20 skipped**，413.75 秒；该环境导入路径指向当前工作树的 `skills/douyin-transcript/src/douyin_transcript`。20 项跳过为 POSIX FIFO/权限及当前 Windows 不支持的 symlink 行为，不证明 POSIX 实机通过。
- **本机静态检查：** `uv lock --project .\skills\douyin-transcript --check`、锁定开发环境全仓 Ruff、`python scripts/check_sensitive_files.py` 和两份固定版 `skills-ref==0.1.1` Skill validator 均通过。报告更新后运行 `git diff --check` 通过（详见第 39–40 节）。没有在本节重跑 P0 doctor、P2 实时捕获或正式 Codex Security Diff Scan。
- **安全边界复核：** AUD-77 的一次性本机动态 harness 证据及跨平台隔离架构见第 37 节；未触碰系统 firewall/registry/policy。现有命令行策略仍不能关闭本机 UDP 直连，项目所有者需确定是否批准特权原生适配或组织预配置的进程隔离。
- **当前工作树与发布：** HEAD 仍为 `b166778`，Git remote 为空，工作区包含修改文件和未跟踪交付材料；尚无最终发布 commit、远端 CI 或干净远端安装。Windows 当前 Python 两版离线全套通过，只关闭对应本机回归项，不关闭 macOS/Linux 实机、远端矩阵、发布树/历史复核或发布授权。
- **仍未验收：** P1/P4 无至少 60 秒授权中文媒体；P2 只有 1/3 URL 且 `CAPTURE_NO_MEDIA`，缺两条授权 URL、端到端捕获与进程级隔离；P5 需要在新 Codex Desktop 会话中发现并实际调用 repo-scoped Skill；P6 缺所有者的许可证/仓库/分发范围选择、未完成的精确二进制许可材料、remote CI 和远端干净安装。项目仍为 **NOT READY**。

## 39. 2026-10-10 正式差异安全扫描与 PyAV 跨平台发行物复核

- **正式扫描身份与覆盖：** Codex Security Diff Scan `aa2b1804-d96a-4db1-8983-1a5eb886f6a8` 已完成，目标基线为 `b166778ee5283591a1b799535b746ba198e38653`，冻结工作树摘要为 `codex-security-snapshot/v1:sha256:6525187514d395e2bc9e0ba0ed2cc2e417151ef0a68bfef2b0fc1bfff94da50d`。coverage 为 **complete**，11/11 个变更源码/配置审查项已关闭；发现 1 项低严重度、置信度中等的问题。封存报告和 SARIF 保存在本机 Codex Security 私有状态目录，不随仓库分发；Scan ID 和冻结摘要可用于定位。此冻结扫描不覆盖本节文档修改及之后的工作树状态。
- **AUD-77 正式差异发现（CWE-923，低严重度 / 中等置信度）：** 锁定 Playwright 1.63.0 / Chromium revision 1243 中，合成 STUN UDP 包在设置 `--force-webrtc-ip-handling-policy=disable_non_proxied_udp`、HTTP CONNECT 代理、host allowlist、Playwright route 和 DNS 检查后，仍到达本机 loopback 与私有网卡接收端。此前第 37 节记录的动态证据与正式扫描结论相符。证据只确认本机 UDP 投递；没有证明联系外部地址、读取服务响应或进一步利用。攻击者控制的脚本能否经获准抖音页面路径执行仍未确认，属于影响成立前提。
- **对策与门槛：** 把浏览器进程放入操作系统或沙箱级网络隔离，阻止直接 UDP、loopback 和私网连接，仅允许连接受控代理；监督浏览器进程及隔离生命周期。增加可重复的 loopback/LAN UDP 拒绝测试，并确认经受控代理的 HTTPS 捕获可正常工作。Chromium 参数仅作为纵深防护。此项未解决，P2 安全门槛仍未通过；本轮没有更改系统网络策略。
- **PyAV 锁定 wheel 复核：** 只读审阅了 PyAV 15.1.0 对应 14 个 CPython 3.11/3.12、Windows/macOS/Linux PyPI wheels，全部 14 个 SHA-256 均与 `uv.lock` 相符；wheel 均含 FFmpeg 7.1.1 字符串、x264/x265 原生库及 `--enable-libx264` / `--enable-libx265` 构建参数。wheel 含 PyAV `LICENSE.txt`，其内容与上游文件一致，PyPI 声明 BSD-3-Clause。扫描未发现 `--enable-gpl` 字符串，但这不能证明相应 GPL 组件、许可证例外、完整构建参数或 notice 义务不存在。PyPI 未以 Trusted Publishing 上传这些发行物，缺少绑定完整 wheel 构建过程及组件许可证的来源证明；上游 v15.1.0 helper 使用 FFmpeg 8.0 且构建参数与 wheel 观察不同，不能代替实际 wheel 配置证据。详细状态见 `docs/THIRD_PARTY_LICENSE_REVIEW.md`。
- **P6 对策：** 先由所有者确定源代码、可选依赖及二进制的实际交付范围，再为每个拟交付 wheel 索取并核对与 artifact 哈希绑定的完整 FFmpeg configure/build manifest、组件 BOM、license/notice 和必要源码。没有足够证据前，继续将未确定结论保留为 `NOASSERTION`，不把 PyAV wheel 或含其 native libraries 的二进制纳入发行。此技术复核不构成法律意见或再分发批准。
- **验收缺口及状态：** P1/P4 仍缺至少 60 秒、获授权的本地中文音视频样本；此前提供的抖音网页链接已用于一次 P2 尝试，结果为 `CAPTURE_NO_MEDIA`，且尚缺另外两条授权链接。P2 还需三条成功端到端捕获和 AUD-77 进程级隔离证据。P5 需新 Codex Desktop 会话确认 Skill 发现和真实调用。P6 仍缺项目 LICENSE、所有者仓库/可见性/分发范围决定、远端 CI 和干净安装。此前 Windows 双 Python 全套结果为各 **407 passed, 20 skipped**（见第 40 节）；不代表 POSIX/macOS/Linux 通过。本轮没有运行测试或重新访问抖音。项目整体继续 **NOT READY**。
- **本轮文档检查：** 审计/发布文档更新后，`git diff --check` 退出码为 0（Git 仅提示工作树 LF 文件在 Windows 后续写入时可能转为 CRLF），`python scripts/check_sensitive_files.py` 通过。本轮未运行测试。

## 40. 2026-10-10 项目续审：当前树回归与文档一致性

- **当前树回归：** 使用项目锁定 Windows Python 3.11.15 环境运行 `uv run --project .\skills\douyin-transcript --locked --no-sync --group dev pytest -q`，结果 **407 passed, 20 skipped**（141.59 秒）。另使用已有 profile-local Python 3.12.13 环境直接运行全套 pytest，结果 **407 passed, 20 skipped**（407.76 秒）；运行前确认该环境的包导入路径指向当前工作树。20 个跳过项是 Windows 不支持 POSIX FIFO/权限语义或当前文件系统无法创建 symlink 的用例。
- **当前树静态门禁：** `uv lock --project .\skills\douyin-transcript --check` 解析 34 个锁定包并通过；全仓 Ruff、Git-visible 敏感文件检查、canonical Skill 与 repo-scoped Skill 的固定版 `skills-ref==0.1.1` 验证均通过。最后文档更新后 `git diff --check` 退出码 0。此为本机验证，不代替最终发布提交上的复跑或远端平台矩阵。
- **文档缺陷修复：** `docs/ACCEPTANCE.md` 曾笼统称 SPDX license values 全为 `NOASSERTION`，与该页及 SBOM 中 33 个第三方包 `licenseDeclared` 已有声明不一致。现明确区分第三方 `licenseDeclared`、项目包 `licenseDeclared` 和所有包的 `licenseConcluded`；另同步了最新扫描、PyAV wheel 证据与当前全套测试结果至审核报告、验收页、发布报告、发布清单和整改材料。
- **补充代码审阅：** 本轮只读复核没有确认 AUD-77 之外的新增生产缺陷。有一项低置信度的时限覆盖候选：`BrowserCapture.capture()` 在创建 `page` 前启动 deadline，但同步 `context.new_page()` 和 `finally` 中的 `page.close()` 调用没有可取消的硬超时；浏览器 IPC 若卡住，可能延后该函数返回。当前没有锁定 Chromium 卡死复现证据，故不作为确证缺陷。若产品要保证整个捕获调用的严格 45 秒 wall-clock 上限，应由可终止的子进程监督整个浏览器捕获生命周期，并对新建/关闭页面卡死场景及正常可见浏览器流程做动态验收；否则明确该上限只约束被设置了 Playwright timeout 的导航和 locator 操作。
- **主要阻断项未变：** AUD-77 需要所有者选择随产品交付有权限要求的平台适配，或要求用户预先配置并验证系统级隔离。P1/P4 等待本地授权媒体；P2 等待另外两条 URL、三次成功捕获和隔离验收；P5 等待新 Codex Desktop 会话；P6 等待项目 LICENSE、仓库/可见性/分发范围/远端操作决定和远端 CI/干净安装。POSIX/macOS/Linux、映射盘和 Windows 多账户实机证据仍缺失。没有进行真实 ASR、重访抖音、改变系统网络策略、建立 Git remote 或发布；项目继续 **NOT READY**。

## 41. 2026-10-10 P6 锁定发行物与原生依赖续审

- **CTranslate2 4.8.2：** 10 个 CPython 3.11/3.12 Windows、macOS、manylinux wheel 的字节数和 SHA-256 均匹配 `uv.lock`。Windows wheel 含 cuDNN 9 runtime 和 Intel OpenMP DLL，macOS x86-64 wheel 含 Intel OpenMP dylib，Linux wheel 含 `libgomp`；10 个 wheel 均未见 license/notice 路径。上游 Windows 构建脚本指向 cuDNN 9.10.2 与 oneAPI 2025.3，但缺绑定到具体 wheel 哈希的构建证明、DLL 哈希和完整许可/notice。Linux `libgomp` 的具体 GCC 构建版本也未绑定。包级 MIT 不足以完成这些组件的分发判断；详见 `docs/THIRD_PARTY_LICENSE_REVIEW.md`。
- **ONNX Runtime 1.30.0：** 锁定 CPython 3.11 Windows x64 wheel 包含 344,457 字节、SHA-256 `c53a76501ef60db6f865f20599f220761201ac4057683acefdab37d861b86622` 的 `ThirdPartyNotices.txt`。对三个原生文件的字符串/符号检查支持 pybind11、Protobuf、ONNX、FlatBuffers、RE2、Abseil、WIL、nlohmann JSON 等依赖的进一步审查，但不等价于已确认链接范围。DNNL 执行提供程序显示未启用；未发现独立 MKL/OpenMP 二进制或 Mbed TLS 标记，仍不能排除静态链接。需要对应构建日志、CMake 配置、链接映射和依赖清单才能完成 notice 映射。
- **Tokenizers、Ruff 与 NumPy：** PyPI 固定版本 JSON 中的所有锁定文件名/大小/SHA-256 与 `uv.lock` 一致：Tokenizers 17 条、Ruff 19 条、NumPy 2.4.6 共 30 条、NumPy 2.5.3 共 12 条。另对 Windows x64、Linux x86-64、macOS arm64 的 12 个目标 wheel 逐字节核对哈希；文件名和哈希见 `docs/THIRD_PARTY_LICENSE_REVIEW.md`。Tokenizers sdist Cargo.lock 有 153 个记录，抽查 wheel 无 license/notice 文件；Ruff sdist Cargo.lock 有 528 个记录，抽查 wheel 仅带主许可证，没有第三方 Rust notice。六个 NumPy 目标 wheel 各有 20 个许可文件（19 个路径名含 `LICENSE`，另有一个 `COPYING`，合计 120 个），其大小与 RECORD 哈希均匹配；除平台相关顶层 LICENSE 外，其余 19 个文本经换行归一后六 wheel 一致。已识别多项组件许可证，但平台相关 GCC/libquadmath notice 与实际二进制的映射、其他 wheel 的文件覆盖、NCSA 双重许可表达式和 SplitMix64 public-domain 表达仍需复核。PyPI 对四个发行版本没有提供 provenance/attestation；Cargo 源锁文件不能证明已发布 wheel 的实际依赖和构建配置。
- **P6 对策：** 在所有者明确源代码、可选依赖、dev 工具和二进制的发行范围后，为所有拟交付 wheel 建立 artifact 哈希绑定的组件清单、依赖构建证明、实际启用配置和完整 license/notice 存档。CTranslate2 需补 cuDNN、Intel OpenMP、libgomp 的版本匹配证据；ONNX Runtime 需把 notice 条目映射至实际链接组件；Tokenizers/Ruff 需提供 wheel 对应 Cargo 依赖 SBOM 与 notices；NumPy 需在其余拟交付平台 wheel 上复核文件覆盖，并将平台 GCC/libquadmath notice 关联到实际二进制和链接配置。项目包和所有 `licenseConcluded` 继续为 `NOASSERTION`，本次复核不构成法律意见或再分发批准。
- **状态与限制：** 本节为只读 P6 发行物检查，没有安装或保存 wheel，也没有改动运行时代码，因此不需要重跑测试；Python 3.11.15 的后续当前树复跑见第 42 节，Python 3.12.13 结果见第 40 节。本机没有 Linux/macOS 实机、远端 CI、项目许可证和所有者分发决策。六个 NumPy wheel 的 120 个许可文件已逐项通过 RECORD 大小/hash 一致性并形成有限文本映射；该证据不覆盖其他平台 wheel，也不确证 notice 中的 native linkage。P1/P4 样本、P2 两条补充链接和真实捕获/隔离、P5 新 Desktop 会话也仍待完成；项目继续 **NOT READY**。

## 42. 2026-10-10 当前环境复核与 Python 3.11 回归

- **本机 P0 复核：** 使用 `docs/P1_REPORT.md` 记录的私有数据目录和个人输出目录重新运行锁定环境 `doctor --json`，退出码 0，`overall=ready`、`local_transcription=ready`、`douyin_urls=ready`，15 项依赖、模型、浏览器、目录权限和磁盘检查全部为 `ok`。未安装或下载内容，也未创建这些目标目录。此前对 `%LOCALAPPDATA%\\douyin-transcript` 的诊断失败是另一条不安全默认候选路径，不是本次所用 fallback 私有目录的状态。
- **Windows Python 3.11.15 全套回归：** 重新运行 `uv run --project .\skills\douyin-transcript --locked --no-sync --group dev pytest -q`，结果 **407 passed, 20 skipped**，232.34 秒。20 项跳过仍由 POSIX FIFO/权限语义和本机 symlink 能力导致；本轮没有重跑 Python 3.12。
- **静态门禁：** `uv lock --project .\skills\douyin-transcript --check`、全仓 Ruff、`python scripts/check_sensitive_files.py` 和 `git diff --check` 全部通过。Git 提示部分工作树 LF 文件未来可能转为 CRLF，不影响 `git diff --check` 退出码 0。
- **合成 ASR 冒烟：** 通过 Windows `System.Speech` 的 Microsoft Huihui Desktop 语音生成 190.477 秒 zh-CN WAV，并在私有数据目录内运行锁定的 medium 模型。CLI 返回成功（退出码 0），生成 1 个 2,625-byte Markdown 文件，端到端 101.98 秒；模型加载/纯推理耗时未拆分，峰值内存未测量。JSON 仅检查了摘要字段，未读取或复制逐字稿正文。该结果验证合成输入的本地模型与输出流程，不代表用户真实媒体的识别准确度、听审或 P1/P4 验收；完整记录见 `P1_REPORT.md` 与 `BENCHMARK.md`。
- **外部环境与验收缺口：** 本机 WSL 未配置 Linux 发行版，未发现 Docker 或本地 Actions runner；Git remote 为空。当前 PowerShell token 未提升（`IsElevated=false`），因此本轮没有尝试安装 WFP 过滤规则或改变系统网络策略。工作区没有用户提供或仓库内的本地音视频；仅有上述私有合成样本。P1/P4 真实转写与听审、P2 两条补充授权 URL/三条端到端捕获/进程级隔离、P5 新 Desktop 会话，以及 P6 所有者许可证/分发范围/仓库决定、远端 CI 和干净安装仍未完成。项目继续 **NOT READY**。

## 43. 2026-10-10 P1/P4 隐私回归与 P6 SPDX 字节校验

- **P1/P4 输出隔离回归：** 新增 `tests/unit/test_cli.py::test_transcribe_cli_keeps_synthetic_transcript_out_of_terminal_and_status`，以合成 sentinel 文本和测试 ASR 覆盖 JSON、普通文本、quiet 三种转写输出；确认全文只进入临时 Markdown，不出现在 stdout、stderr、摘要 JSON 或后续 `status --json`。定向 CLI 文件结果为 **58 passed, 2 skipped**；两个跳过项是 POSIX FIFO 用例在 Windows 不适用。该回归验证 CLI/管线边界，不验证真实 ASR worker 的原生启动输出、Agent 宿主上下文或用户媒体准确度，故 P1/P4 仍未通过。
- **P6 校验器：** 新增离线只读脚本 `scripts/verify_spdx_evidence.py`，按 `uv.lock` 固定 artifact URL、类型、大小与 SHA-256 校验本地缓存，并在内存中核对证据记录中的 METADATA/PKG-INFO、license 和 notice 成员哈希；校验器不联网、不安装、不解包落盘。uv 原始缓存缺少所需归档后，按证据清单的锁定 HTTPS URL 将 35 个 artifact 下载到本机临时 SHA-keyed cache，总计 147,223,499 字节；每个下载都匹配 `uv.lock` 的 URL 主机、大小与 SHA-256。随后真实离线运行成功：**33 packages, 35 artifacts, 33 metadata, 4 license, 1 notice members**。这证明证据表所列成员字节与锁定发行物相符，不证明未列出的 bundled 文件/notice 已完整，也不判断许可证适用性、`licenseConcluded` 或再分发义务。
- **本轮回归与静态门禁：** 完整 Windows Python 3.11.15 套件 **419 passed, 20 skipped**（139.31 秒），含新增 CLI 隐私和 SPDX verifier 用例；20 项为 Windows 不支持的 POSIX FIFO、权限或 symlink 场景。定向 CLI 文件为 **58 passed, 2 skipped**，SPDX SBOM/verifier 文件为 **15 passed**（90.64 秒）。全仓 Ruff、`uv lock --check`（34 个锁定包）、Git 可见敏感文件检查、校验器 `--help` 和 `git diff --check` 通过。本轮未重跑 Python 3.12。
- **正式全仓安全扫描限制：** 本轮 Codex Security Deep Scan 未启动，工具明确要求 parent 提供 managed filesystem permission profile；当前调用环境不提供该 profile。按扫描技能规则未重试，也未以手工审阅替代并宣称扫描通过。第 39 节冻结的正式 Diff Scan 仍只覆盖其记录的 11 项变更源代码/配置；当前工作树的后续变更没有新的正式全仓扫描结论。继续把 AUD-77 进程级 UDP/loopback/LAN 隔离作为 P2 门槛。
- **仍开放的验收门槛：** 用户授权的抖音 URL 已用于一次获授权、可见浏览器的 P2 尝试，结果仍为 `CAPTURE_NO_MEDIA`；仍缺另外两条授权 URL、三条端到端媒体捕获及 AUD-77 隔离决策和证据。P1/P4 仍需至少 60 秒的授权本地中文媒体和真实转写听审；P5 需新 Codex Desktop 会话真实发现/调用；P6 需项目所有者决定 LICENSE、仓库与发行范围，并完成实际依赖/原生组件审阅、远端 CI 和干净安装。整体继续 **NOT READY**。

## 44. 2026-10-10 当前快照正式差异安全扫描与 Python 3.12 回归

- **扫描身份与范围：** Codex Security Diff Scan `590875be-d08c-4c82-918a-c8c5021c422e`，基线/HEAD 均为 `b166778ee5283591a1b799535b746ba198e38653`，冻结工作树摘要为 `codex-security-snapshot/v1:sha256:1f5fe3709bedefe17ca871596a662002bde3ec0dcd50fa736214fa7451d336d6`。12 项变更源码/配置审查项全部完成，coverage 为 complete、无排除项；支持性复核包括 `SECURITY.md`、browser proxy、downloader、P2 动态证据和当前 CI workflow。此结果是限定变更的差异审查，不表示对工作树内全部 96 个文件逐行审阅，也不替代全仓 Deep Scan、平台集成或产品验收。
- **发现 1 — CWE-923，低严重度 / 中等置信度：** Chromium 在设置 `--force-webrtc-ip-handling-policy=disable_non_proxied_udp`、Playwright HTTP(S)/WSS 路由、公开 DNS 检查和 CONNECT 代理后，仍能把 WebRTC/STUN UDP 包送达本机 loopback 与私有网卡接收端。此判断沿用此前锁定 Playwright 1.63.0 / Chromium revision 1243 的一次性动态 harness 证据；本次扫描没有重新发送网络流量。证据只确认本机收包，没有证明外部通信、UDP 响应读取、服务利用，或恶意脚本可通过普通获准抖音页面投递。
- **对策 1：** 在 Chromium 进程级提供操作系统或沙箱网络隔离，默认阻止直接 UDP、loopback 与私网连接，仅允许受控代理所需的连接；隔离初始化失败时拒绝启动 Chromium，并监督隔离/helper 与 Chromium 的生命周期。增加锁定 Chromium 的 loopback/LAN UDP 拒绝回归，同时确认经受控代理的 HTTPS 捕获仍成功。浏览器启动参数只能作纵深防护；现有 P2 网络边界门槛仍未通过。
- **发现 2 — CWE-400，低严重度 / 中等置信度：** 新增离线 SPDX verifier 对所需归档成员设置了 64 MiB 单成员上限，但 `tarfile.open(..., "r:gz")` 后执行 `getmembers()` 会先遍历并物化整个 sdist。总解压字节数、归档成员数和解析时限没有上限；恶意或被篡改锁定的 sdist 可在维护者主动运行该本地工具时耗尽资源。Artifact 的锁定 SHA-256/大小校验确认输入身份，不限制解压工作的总量。该脚本当前不在已提交 CI workflow 中调用，没有动态构造归档验证耗尽效果。
- **对策 2：** 为解压总字节数、归档成员数和墙钟时间设置硬上限，或使用具备全局预算的流式检查器；超限时失败关闭，不落盘解包。补充高压缩率/大量成员/重复路径的合成归档回归，确认正常锁定 artifact 仍能完成成员哈希核对。
- **回归结果：** Windows Python 3.11.15 **419 passed, 20 skipped**（第 43 节，139.31 秒）；Windows Python 3.12.13 当前树 **419 passed, 20 skipped**（141.74 秒）。跳过项为本机 Windows 无法提供的 POSIX FIFO、权限或符号链接能力，不代表 Linux/macOS 实机验证。两轮全套回归均未新增或运行动态 WebRTC/恶意归档测试。35 个 SPDX artifact、33 个 metadata、4 个 license 与 1 个 notice 成员字节校验成功的证据及边界见第 43 节。
- **其余阻断项：** P1/P4 仍缺至少 60 秒且获授权的本地中文媒体和真实听审；用户给出的抖音链接已用于一次可见 P2 尝试，结果为 `CAPTURE_NO_MEDIA`，仍缺另外两条授权链接和三条成功捕获；P2 还需落实并验收进程级隔离。P5 需新 Codex Desktop 会话验证 Skill 实际发现/调用；P6 需所有者决定项目 LICENSE、仓库与分发范围，并完成原生依赖/notice 审阅、远端 CI 和干净安装。整体继续 **NOT READY**。

## 45. 2026-10-10 CWE-400 扫描后修复与复验

- **修复范围：** 保留第 44 节正式差异扫描及冻结快照原文；本节记录其后工作树的整改，不修改或重新打开该次扫描。`scripts/verify_spdx_evidence.py` 对 sdist 改用 gzip 包装的 tar 流式读取，删除预先 `getmembers()` 枚举；设置每个归档最多 512 MiB 解压数据、50,000 次 tar 成员访问和 30 秒总解析时间。三个预算由同一对象在该 artifact 的全部证据成员查找间共享，避免通过重复扫描同一 sdist 重置限制。任何预算超限均失败关闭，不将成员解压到磁盘。单个成员仍受 64 MiB 限制。
- **预算依据：** 本机临时缓存中的 35 个锁定 artifact 以完整流式核验成功；sdist 中最大展开数据为 109,661,139 字节、最多 8,367 个成员，低于新增上限。该数据只说明当前证据集可通过这些限制，不是对所有未来发行物的容量保证。
- **回归证据：** `tests/unit/test_spdx_evidence_verifier.py` 共 **14 passed**，Windows Python 3.11.15 和 3.12.13 均通过；新增测试覆盖解压字节、tar 成员访问和总解析时间限制，并验证同一 artifact 的预算跨多条证据成员查找累计。整改后全套 pytest 在 Windows Python 3.11.15 为 **424 passed, 20 skipped**（139.58 秒），Python 3.12.13 为 **424 passed, 20 skipped**（139.10 秒）；跳过均为本机 Windows/POSIX 功能限制。全仓 Ruff、`uv lock --check`、敏感文件检查和 `git diff --check` 通过。两个 Python 版本均再次离线核验临时 SHA-256 缓存，结果为 **33 packages, 35 artifacts, 33 metadata, 4 license, 1 notice members**。随后仓库外 clean-install 检查通过，canonical Skill 和 `.codex/skills` 入口的固定版 Agent Skills validator 均返回 `Valid skill`；这不替代远端 CI 或新 Desktop 会话验收。
- **状态与限制：** 本次是 CWE-400 静态发现的代码整改及有界合成/真实缓存回归，不是正式安全复扫；第 44 节扫描的覆盖范围与两项扫描时发现保持不变。CWE-923 进程级网络出口隔离、P1/P4 授权真实媒体与听审、P2 额外链接和成功捕获、P5 新 Desktop 会话、P6 所有者决策和远端 CI 仍未完成，整体保持 **NOT READY**。Windows WFP/ALE 实施需要专用 Chromium 路径、管理员级隔离组件和 fail-closed 生命周期验证；其设计约束及官方来源记录在 `docs/P2_REPORT.md`。


## 46. 2026-10-10 当前工作树正式差异安全复扫与整改对策

- **扫描身份：** Codex Security Diff Scan 8b48bd50-c3a7-4837-8992-53e6806f49d0；基线与 HEAD 均为 b166778ee5283591a1b799535b746ba198e38653；冻结摘要为 codex-security-snapshot/v1:sha256:d60fe44ded9b502eda645323f5eb92fcf03eb4fb7461fc4907be2e0b7b3203b9。此前第 44 节扫描保持封存，没有改写。
- **范围与限制：** 工作台报告 96 条 review rows；review-item API 返回 12 个源码路径；本次 Git 盘点为 33 个已修改跟踪文件和 8 个未跟踪文件，共 41 个路径项。12 个源码审查项已完成，覆盖状态仍为 partial，未能把 96 条工作台记录映射到可见路径。复核含源码静态追踪、独立架构复核和既有 P2 动态证据；本轮未运行项目测试或新增运行时攻击样本。
- **发现 1 — CWE-923，低严重度 / 中等置信度：Chromium WebRTC UDP 绕过代理边界。** 浏览器启动设置 disable_non_proxied_udp 并配置 HTTP(S)/WSS 检查，但既有锁定 Chromium 动态记录显示 STUN UDP 包仍到达 loopback 与私有网卡接收端。源码没有建立进程级网络隔离；恶意脚本经普通获准页面投递、外部通信或读取 UDP 响应均未证实。
  - **对策：** Chromium 启动前必须确认进程级 egress 隔离已成功建立；隔离不可用时 fail closed。监督隔离 helper 与 Chromium 生命周期。用锁定 Chromium 验证 loopback/私网 UDP 被阻止，同时确认经受控代理的获准 HTTPS 捕获仍成功。
- **发现 2 — CWE-150，低严重度 / 高置信度：doctor 原样打印配置控制字符。** config.py 把未知 TOML [limits] 键插入错误信息，doctor.py 将错误写入报告 detail，普通文本 CLI 输出未调用控制字符清理。TOML v1.0 的 quoted key 遵循 basic string 转义规则，Unicode 转义可表示控制字符；因此含 ESC 的未知键会进入终端输出。JSON 路径使用 ensure_ascii=True。参考 [TOML v1.0.0 规范](https://toml.io/en/v1.0.0)。
  - **对策：** 在普通文本输出边界使用现有 strip_display_controls，或在构造错误时将 key 安全转义。增加 plain/JSON 两种 doctor 回归，覆盖带 ESC 转义的未知配置键。此问题需要用户选中的本地配置和交互式 doctor 调用，没有远程入口证据。
- **发现 3 — CWE-400，低严重度 / 高置信度：SPDX wheel 哈希与 ZIP 目录解析没有总量预算。** 第 45 节修复了 sdist tar 流式解析；但 _hash_file 在比较锁定文件大小之前会读取整个 wheel，wheel 路径的 ZipFile.infolist 会先物化完整中央目录，且没有共享条目、目录字节或时间预算。恶意 lock/evidence 与已缓存的异常 wheel 需要由维护者主动交给本地验证器处理；没有发现远程触发或 CI 调用。
  - **对策：** 哈希前实施制品硬大小上限，并在分块读取期间设置字节/时限；为 ZIP 中央目录和成员遍历设置大小、条目、展开字节和时间预算，超限失败关闭。补充超大制品与高成员数 wheel 回归，并确认当前锁定 artifact 仍能核验。
- **发现 4 — CWE-345，低严重度 / 中等置信度：SPDX 元数据去重跳过包级验证。** verifier 将 artifact 按 digest 合并，再按 member path 去重；重复成员只比较摘要、大小和 role，没有比较包名、版本、metadata 状态及 license 字段/值。若两个证据行复用同一 digest/member path，后续行的包级检查可能被跳过；SBOM generator 仍从该行读取 licenseDeclared。此路径需要协调修改本地 uv.lock 与证据清单并运行生成流程，尚未构造 fixture。
  - **对策：** 按包行保留元数据验证，或在去重时比较包身份、状态、字段和值并拒绝不兼容记录。增加两个包共享 digest/member path、声明冲突的合成回归，要求验证失败。
- **回归与验收状态：** 本轮没有重跑测试；第 45 节记载的 Python 3.11/3.12 全套结果和 35 个锁定 artifact 离线核验仍是上一次回归证据，不覆盖本节新增边界。P1/P4 仍需用户提供至少 60 秒且获授权的本地中文媒体和真实听审；已给抖音链接的 P2 捕获仍为 CAPTURE_NO_MEDIA，仍缺另外两条授权链接、三次成功捕获和进程级隔离验收。P5 新 Desktop 会话验证、P6 所有者许可证决定、原生组件审阅及远端 CI 也未完成，项目维持 NOT READY。

## 47. 2026-10-10 CWE-150/400/345 整改及本机复验

- **CWE-150：** 未知 TOML `[limits]` 键进入 `ConfigurationError` 前会经过 `strip_display_controls`，避免 `doctor` 普通文本诊断把 ESC 等终端控制符原样写出。新增配置层与 human doctor 输出回归；测试使用 TOML quoted key 的 `\u001b` 转义并确认 ESC 不出现在终端输出中。该问题仍需本地操作者选中的配置文件触发，没有增加远程入口。
- **CWE-400：** 离线 SPDX verifier 现对 lock/evidence 文件各限 16 MiB、每份最多 5,000 包行、最多 1,000 个唯一 artifact、artifact 合计最多 2 GiB、单个 artifact 最多 512 MiB、单证据成员最多 64 MiB，并将总验证限制为 300 秒、单 artifact 解析限制为 30 秒。哈希前先核对文件大小，分块读取遵守大小和时限；gzip/tar 共享 512 MiB 解压、50,000 次成员访问和 30 秒解析预算。Wheel 在构造 `ZipFile` 前预检 ZIP64/EOCD、最多 64 MiB 中央目录和 50,000 条目录记录，逐条核对实际记录数与结束记录，随后共享 archive byte/member/time budget 读取证据成员。超限均失败关闭，不落盘解包。
- **CWE-345：** 同一 artifact/member 路径被多条证据复用时，现在比较完整 `MemberEvidence`（包身份、版本、状态、metadata/license 字段和值以及成员属性）；冲突会拒绝。验证器还要求 `valid_spdx_declaration` 的字段只能是 `License` 或 `License-Expression`，值必须与声明表达式一致，且不能同时伪装为外部映射。新增冲突身份、ZIP 实际目录记录与 EOCD 计数不一致、超限前置拒绝及伪造 SPDX 字段回归。
- **本机验证：** Windows Python 3.11.15 全套 pytest **435 passed, 20 skipped**（52.20 秒）。跳过项来自 Windows 不提供的 POSIX FIFO、权限或符号链接能力，不代表 POSIX 验收。当前修改的 verifier/config/CLI 定向回归 **25 passed**；Ruff（当前改动文件）、`uv lock --check`、敏感文件扫描、`git diff --check` 通过。离线 verifier 对本机 SHA-256 缓存复核 **33 packages, 35 artifacts, 33 metadata, 4 license, 1 notice members**。全套仅在 Python 3.11.15 复跑；最终发布仍需最终提交、Python 3.12 和远端跨平台矩阵。
- **正式扫描关系：** 第 46 节扫描是整改前冻结快照，仍按历史记录保留。本节整改经过本机回归，但尚未由新的正式 Codex Security Diff Scan 覆盖；静态复审不声称为正式漏洞关闭。
- **P2 浏览器后续：** 用户授权将该抖音链接用于 P2，并允许安装锁定 Playwright/Chromium 和可见浏览器打开。BrowserSkill 共享 daemon 的命名管道仍因 Windows OS error 5 不可访问，没有重启该 daemon。使用项目锁定 Playwright 1.63.0 / Chromium revision 1243 重新执行一次 `retry-failed --limit 1` 后，默认可见浏览器打开页面但返回 `CAPTURE_NO_MEDIA`；无媒体、输出文件或逐字稿。两条额外授权链接、成功媒体捕获和进程级 egress 隔离仍缺。
- **未关闭门槛：** P1/P4 仍缺至少 60 秒且获授权的本地中文音视频和人工听审；P2 仍缺两条额外授权 URL、成功媒体捕获及进程级隔离；P5 需要新 Codex Desktop 会话实际发现/调用 Skill；P6 需要所有者决定项目许可证、仓库与分发范围，并完成原生组件/notice 审阅、远端 CI 与干净安装。项目整体仍 **NOT READY**。

## 49. 2026-10-10 CWE-150/400/345 生成器与 doctor 整改

- **范围：** 本节记录第 48 节冻结正式扫描之后的本地整改，不改写扫描快照、覆盖状态或正式发现状态。正式报告仍为 partial coverage；本节本机回归不等于新的 Codex Security Diff Scan。
- **CWE-400 SPDX 输入与表达式预算：** `scripts/generate_spdx_sbom.py` 对 lock/evidence 仅允许常规非符号链接文件，并在一次读取中分别限制 16 MiB；单份 evidence 最多 5,000 个 package rows。JSON 解码错误/深层输入受控失败；表达式限制 65,536 字符、4,096 个 token 和最多 64 层括号嵌套，tokenization 在达到上限后停止。文件以 `lstat` 后打开，再用 `fstat` 比对常规文件与身份；可用时启用 nonblocking/no-follow flags，替换成 FIFO 或其他文件会失败关闭，避免竞态阻塞和读取替换目标。校验器复用同一安全打开策略，cache entries 也受覆盖。
- **CWE-345 生成前证据绑定：** `build_document()` 和 CLI 现在必须得到已有 SHA-256 artifact cache。生成器先读取有界 lock/evidence 字节，再把这同一字节快照传入离线 verifier；verifier 根据 `uv.lock` 核对所有 evidence 指向的归档与 metadata/license/notice 成员摘要、大小、包身份及许可证字段/值。返回的 lock/evidence 摘要再与生成器输入比较，输入发生变化时拒绝。文件级 SPDX 表达式和写入 `licenseComments` 的审阅说明均绑定至包版本、制品类型和摘要、归档路径、许可证文件摘要组成的固定审阅映射；对 manifest 中已核验的 Colorama、ONNX Runtime、Ruff、Tokenizers，单独更改表达式或说明会失败。任何 verifier/cache/证据错误在输出文件打开前失败关闭。
- **SPDX 生成物与回归：** 使用本机临时 SHA-256 cache 完整验证并重新生成 `docs/third-party-sbom.spdx.json`，得到 34 个 package records、47 个 relationships；33 个第三方声明仍按精确证据写入 `licenseDeclared`，项目包和全部 `licenseConcluded` 仍为 `NOASSERTION`。离线 verifier 最新直接确认 33 个 packages、35 个 artifacts、33 个 metadata、4 个 license、1 个 notice members。定向运行 **103 passed, 5 skipped**；全套 Windows Python 3.11.15 回归 **450 passed, 23 skipped**（143.06 秒）。其余 skip 包括 Windows 不支持的 POSIX FIFO/权限/符号链接测试。
- **CWE-150 CLI 文本出口：** doctor 纯文本分支在打印每个动态检查名称、状态、诊断 detail 和 data directory 前应用 `strip_display_controls`；JSON 输出继续使用 `ensure_ascii=True`。CLI 捕获配置错误后写入 stderr 时也清理 ESC/C1 与 bidi 控制符。doctor 与通用 CLI 配置错误合成诊断在纯文本中移除控制符，JSON doctor 输出保留转义序列；新增 CLI 回归已纳入 **103 passed** 定向组及本节 **450 passed** 全套回归。
- **复审状态：** 一次独立只读 bypass/regression review 已完成，提出两项高置信度发现并在本地修复：文件级 evidence 的 SPDX expression 可在文件摘要不变时被篡改；generator/verifier 的 `lstat` 与 `open` 之间存在 FIFO 替换阻塞窗口。前者加入基于审阅 artifact identity 的 expression 与 review note 固定映射和篡改回归；后者加入 nonblocking/no-follow 打开、opened file 身份比对及 FIFO 竞态回归。第 50 节已封存后续正式 Diff Scan；全套 Python 3.12 回归、跨平台 CI 与完整 diff 覆盖仍待后续门禁。
- **其余项目门槛：** P1/P4 仍无用户提供的真实本地中文媒体与人工听审；P2 的一条已授权链接在本轮重新打开页面后仍返回 `CAPTURE_NO_MEDIA`，另缺两条链接、成功捕获和进程级出口隔离；P5 仍需新 Desktop 会话发现/调用验收；P6 仍需所有者决定项目许可证、仓库/分发范围，并审阅原生依赖/notice，完成远端 CI 和干净安装。整体保持 **NOT READY**。

## 48. 2026-10-10 当前工作树正式差异安全扫描

- **扫描身份：** Codex Security Diff Scan `d19d0e4e-3fa3-4435-8232-84958a159c43`；base/head 均为 `b166778ee5283591a1b799535b746ba198e38653`；冻结工作树摘要为 `codex-security-snapshot/v1:sha256:66da6a263d7d28919f5cfc68bf0fd4a5bfb3440d6215bad28488d16fc1106a44`。正式扫描报告与 SARIF 保存在本机 Codex Security 私有状态目录，不随仓库分发；Scan ID 和冻结摘要可用于定位。扫描已封存，覆盖状态为 **partial**，不能视为全仓库或完整 diff 覆盖。
- **覆盖范围与限制：** 12/12 个 API 审查路径已由源码复核；工作台同时显示 96 个 diff review rows，无法与 12 项路径清单逐项映射。41 个 Git 可见改动路径中的文档、测试与生成材料没有全部独立源码审阅，因此保留 coverage partial。扫描为冻结快照的静态审查，使用先前记录的 Chromium 本机动态证据；本次未执行项目测试、浏览器或媒体处理。
- **发现 1 — CWE-400，低严重度 / 高置信度：SPDX 生成器对证据文件及许可证表达式没有解析预算。** `scripts/generate_spdx_sbom.py` 对证据文件使用无界 `read_bytes()`/`json.loads()`，表达式解析器则对括号嵌套递归调用。超大或深层输入可导致本地 SBOM 生成失败、内存压力或 `RecursionError`。当前工具为离线维护者命令，没有发现远程入口或 CI 自动调用。**对策：** JSON 解码前限制文件字节数，对 SPDX 表达式限制 token 数和嵌套深度，并对超限返回受控错误；覆盖超大/深层输入与当前证据正常生成回归。
- **发现 2 — CWE-345，低严重度 / 高置信度：生成器未核对元数据证据字节。** 生成器将 evidence manifest 的 `metadata_sha256` 只作格式检查，没有将该摘要与锁定制品内的元数据成员比较，也不要求先有独立 verifier 的成功结果；它随后把 manifest 表达式写入 SPDX `licenseDeclared`。当前证据已有独立离线验证通过，但未来维护者单独运行文档中的 generator 命令时，陈旧或被改写的证据可生成未经支持的许可声明。**对策：** 让生成器直接对照锁定 artifact 字节验证 metadata 字段、摘要和值，或要求绑定确切 lockfile 与证据 manifest 的验证收据；验证失败时不输出声明。增补有效格式但错误 digest/field 的负向用例。
- **发现 3 — CWE-150，低严重度 / 高置信度：doctor 文本诊断可显示路径中的控制字符。** `DOUYIN_TRANSCRIPT_HOME` 或调用参数提供的配置路径会进入 `ConfigurationError`，由 doctor 作为 `config.detail` 返回，并由纯文本 CLI 原样打印。若路径含 ESC 等控制字符且读取失败，终端可能显示控制序列；JSON 输出通过 `ensure_ascii=True` 转义，但纯文本分支没有清理。该入口需本地环境/参数控制。**对策：** 在 doctor 纯文本输出边界对路径和错误详情调用 `strip_display_controls`，并保留 JSON 的有效转义；增加含 ESC 路径的 human CLI 回归。
- **发现 4 — CWE-923，低严重度 / 中等置信度：Chromium WebRTC UDP 仍绕过 HTTP 代理。** 当前代码设置 `disable_non_proxied_udp` 并对 HTTP(S)/WSS 做路由检查，但没有 Chromium 进程级 egress 隔离。先前锁定 Chromium 实测记录合成 STUN UDP 包到达 loopback 与局域网接收端。证据只证明本机接口收包，没有证明外部送达、响应读取或进一步利用。**对策：** Chromium 启动前必须建立生命周期受控的进程级/沙箱隔离，只允许受控代理，拒绝直连 UDP、loopback 与私网；隔离失败时 fail closed。用锁定 Chromium 验证 IPv4/IPv6 loopback/LAN UDP 被阻止，同时确认代理 HTTPS 页面捕获成功。
- **与历史问题区分：** 第 46 节的 SPDX verifier wheel 哈希/ZIP 预算缺口和重复 metadata 去重问题，在第 47 节修复并有本机回归证据；本节 CWE-400 与 CWE-345 指向新添加的 SBOM generator，不是同一实现路径。doctor 的未知 TOML limits 键控制符路径已修复；本节是另一条配置路径错误的终端输出流。
- **回归与剩余验收：** 本机 Windows Python 3.11.15 全套最近为 **435 passed, 20 skipped**；正式扫描本身没有重跑这些测试。2026-10-10 新一轮 BrowserSkill 状态检查及诊断因共享守护进程命名管道返回 Windows OS error 5 而未打开新页面；先前 HTTP 200 / `CAPTURE_NO_MEDIA` 仍是唯一可见导航结果。P1/P4 缺至少 60 秒授权中文媒体与真实听审；P2 缺两条授权 URL、三次成功媒体捕获及进程级隔离；P5 缺新 Desktop 会话发现/调用记录；P6 缺所有者许可证决定、未决原生/notice 审阅、远端 CI 与干净安装。项目仍 **NOT READY**。

## 50. 2026-10-10 正式差异安全扫描收尾与验收状态

- **扫描身份与范围：** Codex Security Diff Scan `9286b01e-39e1-4db8-bdc2-f484889a18ea` 已封存；base/head 均为 `b166778ee5283591a1b799535b746ba198e38653`，工作树冻结摘要为 `codex-security-snapshot/v1:sha256:cd126778b3c4ae71d9667bb1799077661894564f28cce9400b2c8fbd29c5e64c`。正式报告与 SARIF 保存在本机 Codex Security 私有状态目录，不随仓库分发；Scan ID 和冻结摘要可用于定位。复核了准备清单中的 12 项源码/配置路径；工作台同时报告 96 条 review rows，Git 状态包含 33 个改动路径，无法将这些数量完整映射，故 coverage 标记为 **partial**。
- **发现 1 — CWE-923，低严重度 / 中等置信度：Chromium WebRTC UDP 绕过配置的代理出口。** Playwright 对 HTTPS/WSS 的路由及 `disable_non_proxied_udp` 启动参数没有提供进程级 UDP 隔离；项目既有锁定 Chromium 动态记录观察到合成 STUN 包抵达 loopback 与局域网接收端。没有证明包到达外网、读取响应或后续利用。**对策：** 在 Chromium 进程生命周期内强制 fail-closed 的出口隔离，只允许受控代理并阻断直连 UDP；在 Windows 使用专用浏览器身份，验证 helper 失败、浏览器子进程及过滤器生命周期。增加 IPv4/IPv6 loopback/LAN UDP 拦截和代理 HTTPS 成功的动态验收。
- **发现 2 — CWE-150，低严重度 / 高置信度：SPDX evidence 归档路径可注入终端控制序列。** `scripts/verify_spdx_evidence.py` 的 `_safe_member_path()` 接受 ESC、CR、LF 等控制字符；缺失成员异常会插入该路径，CLI 再将异常原样写到 stderr，可能伪造维护者终端输出或污染 CI 日志。影响限于诊断展示/日志完整性，未证明代码执行。**对策：** 在归档路径入口拒绝 Unicode 控制字符，并在 SPDX 两个 CLI 的统一输出边界对所有非可信诊断做终端安全转义；为 ESC、CR、LF、C0/C1 和失败查找补充负向回归。
- **待跟进 — CWE-400 候选：** `context.new_page()` 和 `page.close()` 是没有硬取消上限的同步 Playwright IPC 调用；静态代码可见，但本轮没有复现 IPC 卡死或证明页面内容可触发，因此不列为已确认发现。若产品要求整个 capture 严格受 45 秒墙钟限制，应以可终止的 supervisor 包围浏览器生命周期并验收创建/清理卡死路径。
- **验收进度：** 用户已授权提供的精选页作为 P2 第 1 条，并授权安装锁定依赖、在可见 Chromium 中打开。页面已打开，但返回 `CAPTURE_NO_MEDIA`，未生成媒体或转写；另两条 URL、三条成功端到端捕获及进程级出口隔离仍缺。P1/P4 仍需至少 60 秒且有权处理的本地中文音视频及人工听审；P5 仍需新 Codex Desktop 会话验收；P6 仍需所有者确认许可证、仓库/分发范围，审阅原生依赖与 notice，完成远端 CI 和干净安装。项目整体保持 **NOT READY**。
- **扫描限制：** 本次是冻结工作树的静态差异扫描，没有执行新测试或网络探测；引用的 Chromium UDP 动态证据来自既有验收记录。第 50 节与第 1 节摘要是在扫描封存后补写的报告更新，不属于该冻结摘要；这些文档改动只记录已封存结果和验收状态，没有修改被扫描的实现。完整审查报告包含 findings、覆盖表和可执行整改建议。

## 51. 2026-10-10 SPDX evidence 终端控制字符修复与本机验收

- **问题与影响：** 第 50 节扫描确认 `scripts/verify_spdx_evidence.py::_safe_member_path()` 接受归档 evidence 路径中的 ESC、CR、LF 等 Unicode 控制字符；失败查找会把路径放进异常，两个 SPDX CLI 曾将动态诊断原样写入终端。影响为维护者终端输出和 CI 日志完整性，未证明代码执行。
- **整改：** 新增 `scripts/spdx_terminal_safety.py`，将 Unicode 控制/格式类别以及行/段落分隔符转义为可见 `\\u`/`\\U` 序列，同时保留普通 Unicode 文本。Verifier 在归档成员路径校验入口拒绝这些字符；verifier 和 generator 的失败诊断均转义。Generator 还转义输出写入错误和成功信息中的用户输出路径，写入失败返回受控错误。
- **回归：** 新增用例覆盖 ESC、CR、LF、C1 NEL、bidi override、中文合法归档路径、两个 CLI 的注入诊断和生成器输出路径。独立只读 bypass/regression review 未发现可操作的控制字符绕过或回归（高置信度）。
- **本机验证：** Windows Python 3.11.15 当前全套 pytest **459 passed, 23 skipped**（144.16 秒）；SPDX verifier/generator 定向组 **50 passed, 3 skipped**。Whole-tree Ruff、`uv lock --check`、敏感文件扫描及 `git diff --check` 在当前工作树通过。跳过项需要 Windows 不提供的 POSIX FIFO、权限或 symlink 行为。
- **SPDX 文档生成物：** `docs/third-party-sbom.spdx.json` 的 `documentNamespace` 已依据锁文件、证据清单、当前生成器 SHA-256 和原有创建时间更新。生成器的 SPDX package/relationship 数据逻辑没有因本次显示安全修补而改变。此轮未取得先前使用的完整 SHA-256 artifact cache，故未重跑全部 35 个发行物的离线 verifier 和全量 SBOM 生成；历史字节核验证据仍见 `THIRD_PARTY_LICENSE_REVIEW.md`。
- **状态与未完成门槛：** 第 52 节修复后正式复扫未再次发现 CWE-150；该扫描覆盖仍为 partial。此前确认的 CWE-923 仍需进程级出口隔离。P1/P4 仍需获授权真实中文媒体及人工听审；P2 缺另外两条授权 URL、成功捕获和进程级出口隔离；P5 缺新 Desktop 会话发现/调用；P6 缺所有者许可/仓库/发行范围决定、原生组件/notice 审阅、远端 CI 和远端干净安装。项目整体仍 **NOT READY**。

## 52. 2026-10-10 SPDX 修复后正式差异安全复扫

- **扫描身份：** Codex Security Diff Scan `01945fea-4fe9-4e85-8c8b-b635c0647efc` 已封存，base/head 均为 `b166778ee5283591a1b799535b746ba198e38653`，冻结摘要为 `codex-security-snapshot/v1:sha256:bd0b9d74ee2befde85a5c1bb086699e375c6d35eae829cd58c13bb5d195b6781`。正式报告与 SARIF 保存在本机 Codex Security 私有状态目录，不随仓库分发；Scan ID 和冻结摘要可用于定位。
- **审查结果：** 复核生成清单列出的 13 个源码/配置项，涵盖 SPDX generator/verifier、浏览器网络与捕获、配置/doctor/CLI、任务恢复、输出和错误文本安全；未记录新的候选或可报告发现。第 50 节确认的 SPDX CWE-150 已在第 51 节整改，本次复扫未再次发现。扫描没有重跑测试或做新的网络探测；本地回归证据见第 51 节。
- **覆盖限制：** 工作台记录 97 个 `filesTotal`、13 条工作清单项且 13 项已关闭，但 97 与 13 的差额未被生成清单映射，因此正式报告 coverage 为 **partial**，不代表全仓库审计。扫描使用静态差异审查，没有动态外网或真实媒体验证。
- **仍未关闭：** 第 50 节的 CWE-923 Chromium WebRTC UDP 出口绕过仍要求进程级 fail-closed 隔离及动态拒绝/正向捕获验收。P1/P4 真实媒体与听审、P2 额外授权 URL 和成功捕获、P5 新 Desktop 会话、P6 所有者决策/原生依赖 notice/远端 CI 与干净安装仍未完成，项目继续 **NOT READY**。
- **快照说明：** 本节和首页摘要在扫描封存后补写，只记录扫描结果与当前验收状态，不属于上述冻结摘要。

## 53. 2026-10-10 Python 3.12 当前树回归与剩余验收复核

- **当前树完整回归：** 在隔离 uv 环境运行 `uv run --isolated --python 3.12 --project .\skills\douyin-transcript --locked --group dev pytest -q`，Python 3.12.13 结果为 **459 passed, 23 skipped**（53.03 秒）。该结果与第 51 节 Windows Python 3.11.15 当前树 **459 passed, 23 skipped**（144.16 秒）一起构成两个 Python 版本的当前源码树证据。23 项跳过受本机 Windows 缺少 POSIX FIFO、权限或 symlink 能力影响；这不代表 Linux/macOS 验收。最终 release commit 和远端六项 OS/Python CI 矩阵仍需运行。本节之后只修改验收文档，没有修改被测源代码。
- **P2 隔离审查（§53 决策前快照，后续选择见 §82）：** 只读复核确认 `BrowserCapture` 配置 HTTP 代理和 WebRTC 参数，但不会建立 Chromium 进程级网络隔离；现有单测不验证操作系统出口边界。此前锁定 Chromium 的动态记录显示合成 UDP 可到达本机 loopback/LAN 接收端，不能据此声称外网送达、响应读取或利用。仓库参数或 route 测试不能关闭 AUD-77。当时提出的方向是要求预先配置并验收的系统 sandbox，或决定交付管理员级 Windows WFP 组件；用户后来授权代理选择，并在 §82 选定由主机管理员预配置的外部系统级沙箱。该方案需要 Windows 侧 broker/provider 集成和管理员策略，覆盖 Chromium 子进程生命周期，仅允许到精确 loopback 代理端点的 TCP，并拒绝其他 IPv4/IPv6 TCP/UDP；动态验收须证明 loopback/LAN UDP 被拦且代理 HTTPS 捕获成功。当前进程非管理员，环境没有 Docker/gh，未对系统防火墙或网络策略作修改。
- **P2 链接进展（截至本节快照）：** 用户授权的精选页的锁定 Chromium 捕获尝试返回 `CAPTURE_NO_MEDIA`，没有保存媒体或转写，不计入实施方案要求的三条成功真实视频捕获；本节当时未再访问该链接。AUD-83 修复后的复试见第 78 节，仍为 `CAPTURE_NO_MEDIA`。需取得三条不同且获授权视频的成功端到端捕获，若候选 URL 失败则需继续补充；链接样本不能代替进程级隔离验收。
- **P5 Skill 宿主验收：** 只读复核确认 `.codex/skills/douyin-transcript/SKILL.md` 入口指向 canonical Skill，入口与 canonical Skill 的固定版 validator 通过结果属于此前记录。本轮没有新 Desktop 会话，不能证明宿主发现或实际调用。关闭条件为记录宿主版本/安装来源、`/skills` 列表、显式 `$douyin-transcript` 调用、可分辨的 executable 与 argv，以及仅含状态/路径摘要的脱敏结果；`doctor --json` 可用于低副作用 smoke，不代替真实转写和正文隐私验收。
- **P6 决策与发布门槛（§53 时点快照，隔离方案已由 §82 决定）：** 独立复核确认没有根目录 `LICENSE`、Git remote 或 tracking branch；CI 文件定义 Windows/macOS/Linux × Python 3.11/3.12 六项矩阵，但没有远端运行证据。项目 SPDX `licenseConcluded` 及项目包结论仍为 `NOASSERTION`，PyAV/FFmpeg、CTranslate2、ONNX Runtime、Rust/NumPy 原生组件、notice 映射和部分构建 provenance 仍需针对选定交付范围审阅。该节当时要求所有者决定项目许可证及 `LICENSE`、仓库账户/组织/名称/可见性、交付内容与支持平台、远端操作授权；其中浏览器隔离部署方案已由用户授权代理选择，并在 §82 选择外部系统级沙箱。在决定和证据齐全前，不推断许可结论，不推送或发布。
- **P1/P4 真实样本（截至本节快照）：** 用户先选了提供样本，随后给出的是抖音网页链接，因此本节当时本地中文媒体验收仍无样本。此后用户提供的本地 MP4 已通过 P1 真实转写，见第 62、69 节；P4 仍需人工抽听、长运行和 stdout/stderr/Agent 摘要检查。项目整体继续 **NOT READY**。

## 54. 2026-10-10 当前审核报告校准与源码复核

- **P2 验收口径：** 用户授权的抖音精选页已在可见锁定 Chromium 中尝试，但返回 `CAPTURE_NO_MEDIA`，未产生媒体或转写，不能计入项目计划要求的成功数。P2 仍要求三条不同且获授权真实视频的成功端到端捕获；失败候选不计数，需继续补充候选直至三次成功。另需完成 Chromium 进程级出口隔离验收。已同步校准 `P2_REPORT.md`、`PROJECT_REMEDIATION_PLAN.md` 和 `RELEASE_REPORT.md` 的当前状态文字。
- **只读源码复核：** 独立复核检查了 `capture.py`、`browser_proxy.py`、`urls.py`、`downloader.py`、媒体处理/存储边界、SPDX 生成器与仓库检查脚本；没有报告超出已记录问题范围的新具体安全发现。该结论只适用于上述复核范围，不替代完整代码审计。AUD-77 已知 UDP/loopback/LAN 边界仍开放。
- **正式全仓扫描限制：** 本轮尝试启动 Codex Security Deep Scan，但工具在开始扫描前返回“Deep Scan cannot safely start a read-only worker: the parent must provide a managed filesystem permission profile.” 没有生成 Deep Scan 报告或覆盖数据；按扫描工作流未重试，也未将人工复核描述成正式扫描通过。最新正式差异扫描仍为第 52 节记录的 partial coverage，不能据此声称全仓覆盖。
- **本轮文档检查：** 仅更新验收状态与审核记录；未修改产品源代码、未访问用户给出的抖音链接，也未重跑测试。`git diff --check` 通过。第 51、53 节的 Windows Python 3.11/3.12 全套结果仍是当前源码树最近一次回归证据，不等同于最终 release commit 或远端矩阵结果。
- **剩余门槛：** P1/P4 需至少 60 秒且获授权的本地中文音视频、真实转写与人工听审；P2 需三次成功捕获、合规的资源主机审查及进程级网络隔离；P5 需新 Codex Desktop 会话发现并实际调用 Skill；P6 需所有者确定许可证、仓库/交付范围及远端操作授权，并完成目标平台依赖/notice 审阅、远端 CI 和干净安装。项目继续 **NOT READY**。

## 56. 2026-10-10 AUD-78 CLI 人类可读输出控制字符

- **发现：** CLI 将调用者或环境配置的路径、文件读取异常、权限诊断和摘要路径写入纯文本终端输出时，没有统一去除 ESC、C1 与双向文本控制符。构造带控制字符的 `--file` 路径可触发异常回显；dry-run 输入路径、setup 目标路径、输出目录警告及 quiet/普通摘要也存在同类显示边界。归类为 CWE-150，影响依赖终端文本的调用者或日志查看器；当前证据没有证明远端输入可直接控制本机路径。
- **整改：** 在 CLI 的纯文本输出边界调用 `strip_display_controls`，异常文本使用现有 `sanitize_error_message` 清理控制字符并脱敏 URL/凭据。覆盖 doctor、dry-run、权限警告、未创建的缓存目录、setup 路径/磁盘预检、敏感存储错误及成功/跳过摘要路径。独立只读盲审还发现 argparse 诊断绕过主异常处理器；现已通过安全 parser 的消息输出边界清理。JSON 结构和路径字段保持原有值，通过 `ensure_ascii=True` 序列化，不把纯文本清理规则混入机器接口。
- **回归证据：** 新增用例覆盖 ESC、C1、CR/LF、bidi 控制符的 argparse 诊断、异常路径、dry-run 路径、摘要路径及权限提示，并核对 JSON 路径字段保持原值。`tests/unit/test_cli.py` 全文件 **71 passed, 2 skipped**（188.39 秒）；跳过项是 Windows 不提供的 POSIX FIFO 场景。变更文件 Ruff 和敏感文件检查通过；`git diff --check` 通过（只有 LF→CRLF 提示）。本节不代表全仓测试或正式 Codex Security 扫描。
- **隐私校准：** 已从本报告中的历史扫描指针和测试环境说明移除用户 profile 的绝对目录，改为说明扫描报告留存在 Codex Security 本机私有状态。针对审核报告、发布报告、整改计划和第三方许可证报告的个人路径标记复扫为 0。
- **边界与状态：** 修补覆盖 CLI 自行格式化的终端文本，包括主异常处理器外的 argparse 消息。setup 启动的 uv/Playwright 子进程直接继承终端输出，其输出控制边界未在本轮动态验证。当前修复未改变 AUD-77 进程级 Chromium UDP 隔离缺口，也不关闭真实媒体、P2 三次成功捕获、P5 Skill 宿主和 P6 发布决定等门槛；项目继续 **NOT READY**。

## 55. 2026-10-10 当前会话 P0 CLI 健康检查

- **调用方式：** 阅读 repo-scoped 入口及 canonical `skills/douyin-transcript/SKILL.md` 后，通过 PowerShell 结构化参数运行项目锁定环境的 `douyin-transcript doctor --json`，显式指定既有私有数据目录和 `%USERPROFILE%\Transcripts` 安全输出目标。命令未安装、下载、创建或修改目录；只向审核记录保存汇总状态，不保存绝对个人路径。
- **结果：** 退出码 **0**，`overall=ready`，`local_transcription=ready`，`douyin_urls=ready`；Python、faster-whisper、解码器、固定模型、Playwright、Chromium、配置、数据目录/数据库/浏览器资料/媒体缓存权限、输出路径权限与磁盘空间 **15 项全部为 `ok`**。
- **范围限制：** 这是当前会话中的直接 CLI 健康检查，不是新 Desktop 会话中的自动 Skill 发现或显式 `$douyin-transcript` 宿主调用；不关闭 P5。它只证明环境准备就绪，不处理真实媒体，也不改变 P1/P4/P2 的状态。项目整体继续 **NOT READY**。

## 57. 2026-10-10 正式 Codex Security Standard 扫描与当前树回归

- **扫描身份与覆盖：** Codex Security Standard Scan ID `0fe7a185-fe73-4d18-94d4-4ace973d59b6`，目标工作树 HEAD `b166778ee5283591a1b799535b746ba198e38653`，冻结摘要 `codex-security-snapshot/v1:sha256:9d653647f0da39c661d29695f1ac13532f5d54c2f1ad45c28c8b97be6a7fcb18`。扫描已封存并生成安全报告；coverage 为 **partial**，工作台显示 97 项范围文件，本轮聚焦并交叉复核浏览器出口、存储隐私、CLI/doctor 输出、敏感文件 CI 与 SPDX 工具，未逐项对账全部 97 项。扫描本身未运行测试或外网检查；报告留在 Codex Security 本机工作区。
- **发现 AUD-77 — CWE-923，低严重度 / 中等置信度：Chromium WebRTC UDP 可绕过配置代理。** 当前代码加入 `disable_non_proxied_udp` 并以受控代理处理 HTTP(S)/WSS，但没有覆盖 Chromium 完整进程树的操作系统网络隔离。既有锁定 Chromium 动态记录显示合成 STUN UDP 到达本机 loopback 和私有网卡接收端；仅证明本机 UDP 送达，没有证明外网送达、响应读取、服务利用或允许页面上的恶意脚本投递。
- **AUD-77 对策（扫描时快照，方案后由 §82 决定）：** 当时建议所有者在预配置系统 sandbox 与随项目交付的隔离组件之间选择。用户已授权代理选择，并在 §82 选定由主机管理员预配置的外部系统级沙箱。隔离必须 fail closed 并覆盖 Chromium 子进程生命周期，只允许到受控代理的 TCP，阻断直连 UDP、loopback 与私网。使用锁定 Chromium 验证 UDP 阻断及获准代理 HTTPS 捕获成功，保留现有 URL/host 校验。
- **发现 AUD-79 — CWE-732，低严重度 / 中等置信度：默认转写输出可能继承共享 ACL。** Windows 默认输出在当前工作目录下的 `douyin-transcripts/output`。CLI 会检查并提示不安全权限，但仍继续写入；Markdown 暂存/发布不设置私有 DACL。若用户从其他本地账户可读的共享目录运行，生成正文可能沿用父目录权限。该风险限定于不安全的隐式默认路径；文档允许调用者明确选择共享输出。文本模式会在处理前提示；JSON 结果会携带结构化权限状态。
- **AUD-79 对策：** 将默认输出改到私有数据目录，或在隐式默认路径权限不安全时要求明确 opt-in；保留显式共享输出能力。增加 Windows ACL 回归，确认默认拒绝/确认路径与显式共享路径的行为。
- **发现 SEC-36 — CWE-150/CWE-117，低严重度 / 高置信度：敏感文件检查器原样打印 Git 文件名。** `scripts/check_sensitive_files.py` 以 `surrogateescape` 保留 Git 可见文件名，并把违规名称直接写入 stderr。PR 可提交带 ESC/CR/LF 等控制字符且同时命中敏感路径规则的名字；Ubuntu CI 会运行该检查器，部分终端或日志查看器可能因此显示误导诊断。检查仍以非零退出；没有证明代码执行或 CI 权限提升。
- **SEC-36 对策：** 在诊断输出边界复用 `scripts/spdx_terminal_safety.py` 转义文件名中的终端控制字符；补充 ESC、CR、LF、C1 与 bidi 文件名用例，并确认违规仍使检查失败。当前正常仓库文件扫描通过不覆盖这种对抗文件名回归。
- **本轮候选复核：** 先前 SPDX wheel 全量哈希/ZIP 目录无界候选在当前快照已有单 artifact/总 artifact 上限、hash 超长即拒绝、ZIP 中央目录大小/成员数/解析时限预算；共享 artifact/member 的重复证据现要求完整 `MemberEvidence` 相等，否则拒绝冲突。配置未知项和 doctor/CLI 错误输出也在纯文本边界剥离显示控制符。因此这些旧候选没有作为当前新增发现。该结论来自静态源码核验，本轮未运行恶意 wheel 或恶意配置夹具。
- **扫描快照全套回归：** Windows Python 3.11.15 运行 `uv run --project skills/douyin-transcript --group dev pytest -q`，结果 **468 passed, 23 skipped**（325.89 秒）。跳过项涉及本机不支持的 POSIX FIFO、权限或 symlink 语义；不代表 Linux/macOS 实机通过。Python 3.12 最新结果仍为第 53 节所录 459 passed, 23 skipped，未在本次之后重跑。整改后的当前 Python 3.11.15 结果见第 58 节。
- **扫描时验收状态：** P1/P4 仍缺至少 60 秒且获授权的本地中文媒体、真实 ASR 结果与人工听审；用户提供的 P2 链接已做一次获授权可见浏览器尝试，结果为 `CAPTURE_NO_MEDIA`，不计成功，另两条链接及三次成功捕获仍缺。P5 新 Desktop 会话调用、P6 许可证/仓库/分发决定、原生依赖 notice 审阅、远端 CI 与干净安装仍未完成。冻结扫描时 AUD-77、AUD-79、SEC-36 均未整改；AUD-79 与 SEC-36 的后续整改见第 58 节，AUD-77 和其余验收门槛仍使项目 **NOT READY**。

## 58. 2026-10-10 AUD-79/SEC-36 整改与复验

- **扫描边界：** 本节处理第 57 节冻结 Standard 安全扫描的 AUD-79（CWE-732）和 SEC-36（CWE-150/CWE-117）。第 57 节的 97 项范围仍为 partial，未逐项对账；该扫描快照早于本节修改，因此不能视作对这些修复的复扫或完整覆盖。
- **AUD-79 默认输出隐私整改：** 未通过 CLI、环境变量或配置文件显式指定输出目录时，`resolve_paths()` 现在将输出设为选定应用数据目录下的 `output/`，并在 `RuntimePaths` 中标记其为隐式默认值。pipeline 在开始处理前调用目录权限诊断；若该隐式目录权限为 `unsafe` 或 `unknown`，则失败关闭并要求调用者明确选择 `--output-dir` 或修复应用数据目录权限。显式选择的共享目录仍可使用。配置快照有效的重试保留原输出目录；旧任务按当前默认值重试时仍触发默认目录保护。此结论适用于按当前默认值重建配置的旧任务；有效 schema 1/2 快照保留修复前默认路径的残留见第 59 节。
- **AUD-79 文档和回归：** 中英文 README、安装/CLI 参考、架构、实施计划、验收与发布报告已改为 `<data_dir>/output` 口径。配置回归覆盖默认目录与显式路径标记；pipeline 回归确认不安全隐式目录拒绝启动、显式共享目录仍可用；doctor 和 CLI 回归覆盖默认路径诊断及重试行为。当前 Windows `doctor --json` 报告 `overall=ready`、`data_dir_permissions=ok`、`output_dir_permissions=ok`；配置解析确认 `output_dir_is_default=True` 且 `output_dir == data_dir / "output"`。记录中不保存本机绝对路径。
- **SEC-36 终端诊断整改：** `scripts/check_sensitive_files.py` 现在复用 `scripts/spdx_terminal_safety.py` 的 `escape_terminal_controls()`，只在错误诊断输出边界转义 Git 文件名。新增回归涵盖 ESC、CR/LF、双向控制符及 Unicode 行分隔符，并断言敏感文件违规仍以非零退出。敏感文件检查器使用 Git 可见路径，该测试通过伪造扫描结果直接覆盖恶意名称，不在工作树留下此类文件。
- **定向复验：** SEC-36 的敏感文件单测 **8 passed**。AUD-79 相关 config/pipeline/doctor/CLI 定向组合 **133 passed, 4 skipped**；跳过项为当前 Windows 文件系统不支持的 POSIX symlink/FIFO 行为。
- **完整本地复验：** Windows Python 3.11.15 执行 `uv run --project skills/douyin-transcript --group dev pytest -q`，结果 **472 passed, 23 skipped**（141.24 秒）。跳过项依赖 POSIX FIFO、mode/ownership 权限或 symlink 行为，不能视为 Linux/macOS 验收。`ruff check scripts skills/douyin-transcript/src/douyin_transcript tests`、`python scripts/check_sensitive_files.py` 均通过；`git diff --check` 无空白错误（Git 提示部分文件将由 LF 转为 CRLF）。
- **最新验收状态：** SEC-36 的本地整改及 Windows 回归已完成；AUD-79 的当前默认输出路径整改和回归已完成，但第 59 节发现旧版 schema 1/2 失败任务快照可能保留共享默认目录，重试分支仍需整改。AUD-77 进程级浏览器出口隔离仍未解决。P1/P4 仍缺用户提供且获授权的本地中文音视频样本、真实 ASR 结果和人工听审；唯一授权用于 P2 的抖音链接此前返回 `CAPTURE_NO_MEDIA`，另两条链接和三次成功捕获仍缺。P5 新 Desktop 会话 Skill 调用、P6 所有者许可证/仓库/分发决定、依赖许可证与 notice 复核、远端 CI 和最终干净安装仍未完成，整体 **NOT READY**。

## 59. 2026-10-10 当前工作树正式 Codex Security Standard 复扫

- **扫描身份与范围：** Codex Security Standard Scan ID `9d565b94-4fc8-47b9-8939-ca8c43ad6fe2`；目标 revision `b166778ee5283591a1b799535b746ba198e38653`，快照摘要 `codex-security-snapshot/v1:sha256:82e718d7013ed031e38e032d3d7026b579e6c9bd1448e9bbd447b7fdb124c62e`。工作台库存为 97 个文件；定向检查了浏览器出口、任务/输出权限、URL/下载/媒体处理、CLI/doctor、CI 和本地构建依赖。覆盖结论为 **partial**：测试与文档未逐文件完整审计，忽略的本机缓存和归档也未检查。扫描是离线、静态、只读的；没有运行测试、浏览器、包解析或网络请求。完整生成报告副本见 [`SECURITY_SCAN_REPORT_2026-10-10.md`](SECURITY_SCAN_REPORT_2026-10-10.md)，原始工作台报告留在 Codex 本地扫描目录。
- **AUD-77 — CWE-923，低严重度 / 中置信度：** Chromium 可绕过受控 HTTP(S) 代理发 WebRTC UDP。已有锁定 Chromium 记录确认 UDP 能到 loopback/LAN 接收端；没有证明公网送达、读取响应或服务利用。**对策：** 对 Chromium 全进程树实施 fail-closed 出口隔离，仅放行到受控代理的 TCP，阻断直接 UDP、loopback 和私网；用锁定 Chromium 验证 IPv4/IPv6 UDP 被阻断且批准的 HTTPS 捕获仍成功。
- **AUD-79 残留 — CWE-732，低严重度 / 高置信度：** 有效 schema 1/2 失败任务快照只保存 `output_dir`，不保存其来源。重试未传 `--output-dir` 时会沿用修复前的共享默认目录；CLI 权限检查只告警，流水线的 fail-closed 检查只保护标记为当前隐式默认的目录，因此该重试可能写入 ACL 可被其他本机账户读取的转写。**对策：** 对不安全或来源不明的快照路径要求显式 `retry-failed --output-dir`，或迁移/拒绝旧版隐式默认路径；新快照保存输出路径来源。增加 schema 1/2 重试拒绝、显式覆盖成功和当前默认路径保护的回归用例。
- **供应链 — CWE-829，低严重度 / 中置信度，两项：** CI 通过 `uvx --from skills-ref==0.1.1` 安装执行校验器，但临时依赖图未纳入仓库哈希锁；本地 `uv sync --locked` 的 PEP 517 构建后端 `hatchling==1.27.0` 及隔离构建依赖也未被 `uv.lock` 中的制品哈希绑定。**对策：** 将 Skill 校验器及完整传递依赖加入哈希锁定的 CI 环境；为构建后端/隔离构建依赖建立受信且可校验的独立锁，或发布并验证预构建制品。现有直接版本固定和 least-privilege CI 是缓解因素；没有发现已遭攻陷制品。
- **未发现额外 URL/媒体解析器问题：** 定向审查未找到源码支持的 SSRF 路径；URL/重定向逐跳复验、公共地址校验、HTTPS 目标 IP 固定、大小和时间限制以及受监管解码进程均有现存控制。此结论不等同于全仓覆盖完成。
- **扫描时状态与后续：** 四项发现均为低严重度，项目继续 **NOT READY**。扫描完成后，AUD-79 旧快照保护的实现进度记录在第 60 节；其回归验收仍开放。AUD-77 浏览器出口隔离和 CI/build 工具哈希锁尚未整改。远端多平台 CI、P1/P4 真实媒体听审、P2 三条成功捕获、P5 新 Desktop 会话 Skill 调用及 P6 所有者许可证/分发决定仍是独立验收门槛。

## 60. 2026-10-10 AUD-79 旧版失败任务重试保护

- **整改：** `_run_retry()` 现在在任务状态从 failed 变为待重试之前检查有效 schema 1/2 快照保存的输出目录权限。若权限为 `unsafe` 或 `unknown` 且调用未显式提供 `--output-dir`，该任务保持失败状态，不会进入处理流水线；结果返回 `OUTPUT_PATH_UNSAFE`，提示使用 `--output-dir` 选择新目标。显式指定目录仍沿用既有共享输出行为，并把新目录写回重试快照。
- **静态复核：** 检查发生在 `TaskStore.retry_failed()` 之前，因此被阻止的任务不会被领取后遗留为处理中；被跳过目录仍计入 JSON 输出权限摘要。没有改变无效快照的 `--use-current-defaults` 语义。
- **验证状态：** 本节只记录源代码与控制流复核；`ruff check skills/douyin-transcript/src/douyin_transcript/cli.py` 和 `git diff --check` 通过。按当前任务约束未新增或运行测试。schema 1/2 旧路径拒绝、显式覆盖成功、当前默认路径仍受保护等回归以及完整测试套件均待执行；AUD-79 在这些回归和跨账户 ACL 验收完成前仍是开放发布门槛。

## 61. 2026-10-10 AUD-79 重试保护独立静态复核

- **复核范围：** 独立只读检查 `tasks.py`、`cache.py`、`storage_security.py`、`markdown.py`、`output.py`、`config.py`、`naming.py`，并抽查 `cli.py`、`pipeline.py`、`doctor.py` 的重试调用路径和相关测试片段；未运行测试或联网。
- **结果：** 未发现 AUD-79 重试保护的明确绕过或重复入队问题。旧 schema 1/2 快照的权限检查在 `retry_failed()` 前执行；不安全/未知目录会维持 `failed`，显式 `--output-dir` 会覆盖并写回快照。权限摘要保留被跳过目录。结论仅为所列路径的静态数据流复核，不替代 schema 回归、跨账户 ACL 或完整套件。
- **低优先级健壮性建议：** `_retry_processing_options()` 在 `Path.resolve(strict=False)` 上只捕获 `KeyError`、`TypeError`、`ValueError`、`OSError` 和 JSON 错误；符号链接环可能抛出未捕获的 `RuntimeError`，使 CLI 返回异常而不是将快照按无效数据安全跳过。当时尚未动态复现；随后以确定性异常注入复现并修复，见第 63 节。该项属于健壮性问题，没有证据表明它构成安全利用。
- **权限时序限制：** ACL 在入队前按路径检查并缓存；检查结束后至文件发布前若权限发生变化，检查结果不会自动刷新。当前未发现普通其他账户能够利用该时序窗口的路径。若要覆盖并发 ACL 变化，应在发布前再次核验，或由写入层对目录身份和权限作绑定验证。
- **状态：** AUD-79 的已记录整改和待验收项见第 60 节；上述健壮性建议未改变发布门槛判断，项目继续 **NOT READY**。

## 62. 2026-10-10 P1 本地真实媒体转写验收

- **样本与边界：** 用户提供本机 MP4 文件并要求试跑。PyAV 检查到容器内是一条 AAC 立体声音轨、没有视频流；文件大小 7,643,581 字节，时长 315.907 秒。该样本满足 P1 的 60 秒本地音频验收门槛，但不能用于 P2 视频抓取验收。媒体留在用户目录，未上传或复制进仓库；报告不记录文件名及个人绝对路径。
- **运行：** Windows 11 Enterprise LTSC 10.0.26100、Python 3.11.15、Intel i5-12400 / 12 逻辑核、31.7 GiB RAM，锁定 `faster-whisper==1.2.1` / PyAV 15.1.0 / `Systran/faster-whisper-medium` 固定 revision `08e178d48790749d25932bbc082711ddcfdfbc4f`。CLI JSON 转写退出码 0，1 条成功、0 跳过、0 失败；墙钟 302.50 秒，输出为私有目录中的非空 UTF-8 Markdown，4,658 字节。模型加载和推理时间未拆分。
- **隐私检查：** 捕获的 CLI JSON 摘要与后续 `status --json` 未包含正文；stderr 为 0 字节。对正文中 1,357 个不同的、含至少 10 个 CJK 字符的 16 字符窗口进行本地匹配，CLI stdout/stderr 与状态 JSON 中命中数为 0。该证据覆盖本次 CLI/状态路径，不代表所有 Agent 宿主。
- **资源观测：** 转写期间一次进程工作集采样达到至少 2.07 GiB；未持续采样，不能称作真实峰值。
- **结论：** P1 的真实本地音频处理、非空输出和运行时间证据已通过并写入 `P1_REPORT.md` / `BENCHMARK.md`。P4 仍部分开放：本轮未进行人工听审；样本不足 10 分钟，未完成要求的长运行；目标 Agent 宿主上下文检查仍待完成。项目继续 **NOT READY**。

## 63. 2026-10-10 AUD-79 重试快照路径解析健壮性修复

- **发现确认：** Python `Path.expanduser().resolve(strict=False)` 遇到符号链接环或无法确定 home 时可抛出 `RuntimeError`。原 `_retry_processing_options()` 未捕获该异常，导致 `retry-failed` 在入队前退出异常。另一个调用链细节是旧流程入队后再次解析同一快照；若第二次解析失败，代码会错误地回退到当前默认值。
- **整改：** 快照解析将 `RuntimeError` 视为无效快照并返回 `None`；未显式选择 `--use-current-defaults` 时，任务在入队前跳过并保持 `failed`。重试流程把首次校验出的有效选项带入执行阶段，不在入队后重读数据库快照。ACL 检查阶段若路径再次解析失败，则记为 `unknown` 并在入队前拒绝。显式 `--output-dir` 会在校验其他快照字段后替换旧输出路径，因此无法解析的旧路径可安全覆盖；其余无效字段仍须通过 `--use-current-defaults` 显式接受当前配置。
- **回归验证：** 新用例覆盖快照解析 `RuntimeError`、ACL 检查阶段的二次解析异常、显式输出目录覆盖，以及 schema 1/2 不安全输出目录拒绝入队；有效重试控制用例断言快照仅解析一次。定向回归 **7 passed**；完整 `tests/unit/test_cli.py` **76 passed, 2 skipped**（99.13 秒，跳过 POSIX FIFO）。随后 Windows Python 3.11.15 全套 **477 passed, 23 skipped**（327.03 秒）。全仓 Ruff 通过，`git diff --check` 无空白错误。symlink loop 通过 `Path.resolve` 异常注入模拟，Windows 本机未创建真实符号链接环；POSIX 实机行为仍需跨平台 CI 验证。
- **剩余边界：** 权限状态仍是对路径的瞬时检查；检查后若其他主体改变目标 ACL，写入层没有目录身份与 ACL 的原子绑定。第 61 节已记录该 TOCTOU 限制，未由本次异常处理关闭。AUD-77 浏览器进程级隔离、P2 三次真实捕获、P4 人工听审/长运行/Agent 上下文、P5 新 Desktop 会话调用、P6 许可证与分发决策、远端 CI 等仍待完成，项目继续 **NOT READY**。

## 64. 2026-10-10 SEC-SC-01/02 锁定校验器与构建依赖

- **CI Skill 校验器：** `skills-ref==0.1.1` 及其传递依赖已加入项目 `dev` 组和 `uv.lock`。CI 移除 `uvx` 临时解析，在完成 `uv sync --locked --group dev` 后用 `UV_OFFLINE=1` 和 `uv run --locked --no-sync` 执行 `agentskills validate`。本机同一锁定命令在离线模式返回 `Valid skill`；尚未运行远端 Actions 矩阵。
- **PEP 517 构建：** `editables==0.5` 与 `hatchling==1.27.0` 进入默认启用的 `build` 依赖组；`no-build-isolation-package = ["douyin-transcript"]` 使项目构建使用先从锁定环境安装的后端工具，制品散列由 `uv.lock` 校验。第一次仓库外干净安装发现 Hatchling editable 构建还需要 `editables`；将其加入 `build-system.requires` 与锁定组后，`scripts/check_clean_skill_install.py` 在仓库外临时副本成功完成 `uv sync --locked --no-dev`、导入来源、CLI 版本和 dry-run 检查。uv 输出确认项目在无 build isolation 模式构建。
- **SPDX 同步（§64 历史快照，后续补证见 §83）：** 锁文件从 34 增至 42 个包记录（项目包 1 个、第三方包 41 个）。新增 8 个发行物的精确锁定 sdist 已下载到 SHA-256 命名的本地审阅缓存，并逐个检查 URL 主机、大小、散列、METADATA/PKG-INFO 名称/版本及许可证字段。**截至本节**离线 verifier 结果为 **41 packages, 43 artifacts, 41 metadata, 4 license, 1 notice members**；当时生成的 SPDX 文档含 42 个 package records、58 个 relationships，37 个第三方包具有有效或已审阅映射的 `licenseDeclared`。其后 §83 为三个包补充了 artifact-bound 许可证文件证据；当前计数以 §83 为准。该证据不能据此批准分发。
- **本机验证：** SPDX 定向回归 **50 passed, 3 skipped**；完整 Windows Python 3.11.15 套件 **477 passed, 23 skipped**（238.86 秒）。跳过项受 POSIX FIFO、权限和符号链接能力限制。`uv lock --check`、干净 Skill 安装、离线 Agent Skills 校验、Ruff、敏感文件扫描、SPDX 离线证据核验及 `git diff --check` 均通过。该证据仍不替代远端 Windows/macOS/Linux × Python 3.11/3.12 CI。
- **状态：** SEC-SC-01/02 的本地整改与验证完成；远端 CI 与最终发布提交仍待验收。AUD-77 浏览器出口隔离、P2 三次成功捕获、P4 听审/长运行/Agent 上下文、P5 新 Desktop 会话、P6 所有者许可证和分发决定、原生组件许可审阅等门槛仍开放，项目继续 **NOT READY**。

## 65. 2026-10-10 Python 3.12 全套回归与验收证据复核

- **Python 3.12 回归：** 在当前工作树运行 `uv run --isolated --python 3.12 --project .\skills\douyin-transcript --locked --group dev pytest -q`，Python 3.12.13 结果为 **477 passed, 23 skipped**（233.88 秒）。23 项跳过涉及本 Windows 主机不支持的 POSIX FIFO、权限或符号链接行为。与第 64 节 Python 3.11.15 的 **477 passed, 23 skipped**（238.86 秒）一起，覆盖当前锁定构建/校验依赖和源码树；最终发布提交及远端 Windows/macOS/Linux × Python 3.11/3.12 CI 仍需验证。
- **用户提供媒体：** 第 62 节所记 315.907 秒 MP4 已用固定 medium 模型成功转写，结果只验证本地音频路径：容器含 AAC 立体声音轨、没有视频流。该运行的非空输出保存在私有数据目录，正文未纳入仓库；不能计作 P2 抖音捕获。P1 通过，P4 仍需人工听审三处片段、10 分钟以上样本和目标 Agent 上下文检查。
- **Skill 与 SPDX 复核（§65 历史快照，后续补证见 §§83、86）：** 用锁定的 `skills-ref==0.1.1` 和离线命令分别验证 canonical Skill 与 `.codex` 入口，均返回 `Valid skill`；这不能代替新 Codex Desktop 会话中的发现和实际调用。独立只读 SPDX 核对确认锁文件 42 个包记录（项目 1、第三方 41）与当时 SBOM package/version 集相同，43 个 artifact 引用以及 metadata/license/notice 摘要验证通过；当时 37 个第三方 `licenseDeclared` 有证据来源，4 个仍为 `NOASSERTION`。§86 跟进后当前 41/41 个第三方声明均有证据；全部 `licenseConcluded` 仍为 `NOASSERTION`。未发现该历史快照中的清单计数或逐包声明错配；此核对不构成许可批准或完整性结论。
- **剩余门槛：** P2 仍缺三次不同授权视频的成功捕获和经动态验证的 Chromium 进程出口隔离；P4/P5 仍需人工/新会话证据；P6 仍需所有者许可证、仓库与分发决定、原生组件/notice 审查、远端 CI 和远端干净安装。项目整体保持 **NOT READY**。

## 66. 2026-10-10 验收文档校准、干净安装检查与当前差异复核

- **差异安全扫描：** Codex Security Diff Scan `81745f42-fe5b-4151-845c-95c70da451ee` 已完成并封存，目标为相对 `b166778ee5283591a1b799535b746ba198e38653` 的工作树快照，摘要 `codex-security-snapshot/v1:sha256:9142fc74cb252800be19259804af998e48c322ca17957d291b4c04f00ac50a1f`。扫描覆盖本次变更的 16 个源码/配置审查项及浏览器动态证据报告；静态源码复核并复用既有本机 Chromium 证据，没有在扫描中重跑测试或网络动态检查。确认 1 项低严重度、中置信度的 AUD-77；其他审查面未发现额外可报告缺陷。此结论只适用于该冻结快照，不代表完整仓库逐文件审计。扫描封存后才修改了干净安装检查器、对应单元测试和文档；这些后续改动经过本机代码检查与定向验收，但不属于该扫描摘要。
- **AUD-77 — Chromium WebRTC UDP 绕过代理：** 锁定 Playwright 1.63.0 / Chromium revision 1243 的既有动态记录证明合成 STUN UDP 到达 loopback 与本机私网接收端，即使 HTTP 代理、请求路由、公网 DNS 校验和 Chromium WebRTC 策略均已启用。没有证明公网 UDP、响应读取或服务利用。**历史对策快照（本节早于 §82）：** 当时架构选择尚未作出。用户已在 §82 授权代理选择，当前已选择由主机管理员预配置的外部系统级网络沙箱。**当前对策：** 项目需要接入可信、固定身份的 provider/broker；只有在系统策略核验通过后才允许启动 Chromium，broker/策略缺失时拒绝启动。由管理员部署并用锁定浏览器复验阻断和获准 HTTPS 捕获，覆盖辅助程序崩溃、浏览器退出及子进程生命周期。此前“未获所有者明确选择前不修改系统过滤策略”是当时的环境边界记录；本机仍没有管理员沙箱可安装或验收，AUD-77 保持 OPEN。
- **P1 文档状态：** 第 62 节及 `P1_REPORT.md` 记录的 315.907 秒 AAC 音频样本已成功生成 4,658 字节私有 UTF-8 Markdown，运行 302.50 秒；样本无视频流。实施计划的“生成非空 Markdown”已标记通过；主文是否逐字忠实仍未人工听审，不将模型运行成功表述为质量验收。P4 仍需三处听审、10 分钟以上样本和 Agent 宿主隐私检查。
- **验收文档一致性：** `ACCEPTANCE.md` 将 459/23 明确为历史 §51/§52 结果，以 §64/§65 的 477/23 作为最新 Windows Python 3.11/3.12 本地套件结果，并将 Agent Skills 校验命令改为仓库哈希锁定的 dev 环境。P3 状态恢复单元测试通过，但现有恢复用例通过注入陈旧任务状态进行，不是在下载完成、转写前及 Markdown 发布前杀进程并重启；因此计划清单保持未勾选，须补三个真实进程恢复边界用例。
- **干净 Skill 安装检查：** `scripts/check_clean_skill_install.py` 增加 `--dry-run --json` schema/status 验证，并在仓库外复制的 Skill 上运行 `doctor --json`，验证 JSON、项目/能力字段、预期 `setup_required` 状态和退出码 1；最后确认健康检查没有创建应用数据或输出目录。`tests/unit/test_skill_install.py` 定向回归 **13 passed**；`uv run --project .\skills\douyin-transcript --locked --no-sync --group dev python scripts/check_clean_skill_install.py` 通过，报告 `Clean Skill installation passed`；Ruff 对新增脚本和测试通过。以上运行复用了已有锁定依赖/缓存，没有重新安装模型，也没有处理新媒体。
- **整体状态：** P1 真实本地处理已通过；P2 三次成功抓取与隔离、P3 真实杀进程恢复边界、P4 听审/长运行/Agent 上下文、P5 新 Desktop 会话发现及调用、P6 所有者许可证/仓库/分发选择、原生依赖 notice 审阅、远端 CI/干净安装仍未完成。项目整体 **NOT READY**。

## 67. 2026-10-10 P3 子进程崩溃恢复与当前树回归

- **崩溃恢复测试：** 新增 `tests/fixtures/pipeline_crash_worker.py`，由独立子进程运行实际 `TranscriptionPipeline`，在 `TaskStore.transition` 已提交 `downloaded`、`transcribing`、`writing` 后分别调用 `os._exit(86)` 突然退出，不经过 Python 清理流程。测试进程确认数据库保留目标状态及媒体缓存，再启动全新 pipeline 进程复跑同一任务；断言没有重新 capture/download，任务进入 completed，输出 Markdown 含预期正文且 `is_completed_valid()` 为真。ASR、capture、downloader、媒体验证器和 URL 解析都使用确定性替身；该测试验证任务/缓存/写出状态恢复，不代表真实 Douyin 捕获或真实 ASR 在硬崩溃中的行为。
- **定向结果：** 三个崩溃边界参数用例 **3 passed**（pipeline file 内）；完整 `tests/unit/test_pipeline.py` **36 passed, 1 skipped**（13.06 秒）。唯一跳过项要求当前 Windows 文件系统提供 symlink 创建能力。
- **§67 当时的 Windows 全套：** Python 3.11.15 为 **485 passed, 23 skipped**（328.64 秒），隔离 Python 3.12.13 为 **485 passed, 23 skipped**（239.07 秒）；SEC-23 修复后的最新复跑见 §70。23 个跳过项依赖本机不提供的 POSIX FIFO、mode/ownership、directory-handle 或 symlink 语义；不能据此宣称 Linux/macOS 已验收。
- **静态检查：** 当前改动文件及全仓 Python 源/测试 Ruff 检查通过，`uv lock --check` 通过，`git diff --check` 无空白错误（Git 对既有 LF→CRLF 转换输出提示）。本轮没有修改产品运行时代码。正式 Codex Security Diff Scan 仍是第 66 节封存的旧快照；新测试与文档不在该摘要内，未声称其经过正式安全扫描。
- **文档校准：** P3 计划和 release checklist 已标记该硬崩溃恢复验收完成；历史 §64/65 的 477/23 结果明确作为旧快照保留。P2 的失败链接不计数，需继续补充候选直到三条不同授权视频都成功。P2 的 BrowserSkill 共享守护进程 IPC 错误从项目 Playwright 状态表移除，避免与项目捕获结果混淆。README 中的安全报告链接标明它是覆盖部分的历史 Standard Scan，§66 单独记录后续 Diff Scan。
- **整体状态：** P3 的离线 pipeline 崩溃恢复边界通过；P2 媒体抓取/进程级隔离、P4 听审/长运行/Agent 上下文、P5 新 Desktop 会话发现与调用、P6 所有者许可证/仓库/分发选择、原生依赖 notice 审阅及远端 CI/安装仍未完成。项目继续 **NOT READY**。

## 68. 2026-10-10 AUD-10 Windows 真实媒体超时集成

- **隔离与环境：** 使用用户已授权的 315.907 秒本地音频样本，不上传或复制媒体；在应用私有数据目录下创建独立临时验收根目录和任务库。锁定 medium 模型文件以同卷硬链接供本次只读加载，验收目录的 `doctor --json` 报告 `overall=ready`，数据目录、任务库、输出目录和模型检查均为 `ok`。临时任务库与模型目录不在仓库内。
- **真实组件检查：** `SupervisedProcessingWorker.validate_media()` 在真实子进程中通过 PyAV 打开文件句柄、完整解码并返回 MP4 容器和 315.907 秒时长；从启动 worker 到收到完整解码响应的单独墙钟为 **0.953 秒**，包含 worker 启动时间，不代表纯解码 CPU 时间。固定模型内容可由 `LocalASR` / faster-whisper 成功加载为 `WhisperModel`。检查不读取或展示转写正文。
- **超时运行：** 真实 CLI 调用 `transcribe --input-file`，设置 `--processing-timeout-seconds 45`。从父进程启动到 CLI 退出的总墙钟为 **46.49 秒**；退出码为 5（单条任务失败的 CLI 约定），JSON 摘要及随后 `status --json` 均记录一条 `failed/PROCESSING_TIMEOUT`。PowerShell 进程监视观察到 `douyin_transcript.processing_worker` PID；CLI 返回后该 PID 已不存在。CLI stderr 为 0 字节。
- **清理：** 隔离输出目录没有文件，media-cache 没有文件，全验收根目录没有 `.part` 文件。输入是本地文件，因此该运行不覆盖远端下载过程及下载器 `.part` 清理；没有记录模型加载/ASR 推理分阶段时间，也没有单独的推理阶段遥测，不对期限内具体子阶段作断言。
- **范围与状态：** 该结果为 Windows 本机真实 PyAV/固定模型 worker 的 deadline、失败状态持久化和进程回收证据，补充而不替代成功 P1 转写报告。AUD-10 的 Windows 本地真实媒体切片部分通过；macOS/Linux 进程行为和授权远端媒体下载清理仍待实机集成验收。隐私正文未写入报告；两个隔离验收根目录仍保留在应用私有数据目录，未进入仓库，包含任务元数据和 CLI 日志，不含媒体副本或转写 Markdown。

## 69. 2026-10-10 P1 默认处理期限真实媒体复跑

- **运行与结果：** 对第 62 节同一用户授权的 315.907 秒本地音频 MP4，再执行 `transcribe --input-file ... --language zh --force --json`，不传 `--processing-timeout-seconds`，使用默认 7,200 秒期限。Windows CLI 退出码为 0，JSON 摘要为 1 条成功、0 跳过、0 失败，识别时长为 315.907 秒；私有输出目录权限为 `ok`，生成非空 Markdown，4,656 字节。未单独计时，不覆盖模型分阶段性能或长样本验收。
- **隐私与边界：** CLI 返回结构化任务摘要，没有包含转写正文；本报告不记录文件名、绝对源路径或逐字稿正文。样本仍是 AAC 音频 MP4、没有视频流，因此这补充 P1 默认期限路径证据，不计为 P2 抖音视频捕获成功，也不完成 P4 人工质量听审。
- **文档同步：** 复跑结果已补入 `P1_REPORT.md`、`BENCHMARK.md`、`ACCEPTANCE.md` 和 README。先前 45 秒隔离超时结果见第 68 节，成功转写的原始单次计时仍为第 62 节记录的 302.50 秒。

## 70. 2026-10-10 SEC-23 PyAV AAC-ADTS 边界与损坏包失败关闭

- **合成有效样本：** 使用项目锁定 PyAV 15.1.0 生成约 3 秒、142 包的 AAC-ADTS 音频。PyAV 容器声明时长为 3.010407 秒，完整解码帧累计 3.029333 秒；项目校验器返回 3.029333 秒，锁定 faster-whisper 音频解码器得到 3.029313 秒。该结果说明 AAC 编码延迟/填充下不能用略短的容器估算压低实际解码时长；它是确定性合成音调，不是 VBR 或用户录制样本。
- **中间包损坏：** 将第 72 个 ADTS 包的负载清零，文件仍保留该包之后的有效 ADTS 包。PyAV 解码 71 帧后抛出 `InvalidDataError` 并关闭迭代器；faster-whisper 同样只输出 1.514687 秒，不会继续到后半段。修复前校验器因容器仍声明 3.010407 秒而放行，存在把部分解码输入送入 ASR 的风险。
- **整改与验证：** `_validate_open_container()` 现遇到此异常即返回 `MEDIA_DECODE_FAILED`，不再重试已关闭的迭代器，也不信任容器时长掩盖解码提前终止。回归使用已关闭的 Python 生成器模拟该错误边界；`tests/unit/test_p2_downloader.py` 通过 52 项、跳过 1 项 Windows symlink 能力测试，相关 Ruff 检查通过。SEC-23 修复后完整套件 Python 3.11.15 为 485 passed/23 skipped（147.40 秒），隔离 Python 3.12.13 为 485 passed/23 skipped（237.58 秒）。锁定 PyAV/faster-whisper 对照确认有效合成文件完整解码时长一致；真实 supervised worker 对损坏文件返回 `MEDIA_DECODE_FAILED`。隔离 CLI 复验退出码 5、任务状态 `failed` / `MEDIA_DECODE_FAILED`，没有 Markdown 输出且 stderr 为空。
- **剩余范围：** 合成验证不覆盖未知 duration、真正 VBR/尾部 padding 差异、更多封装/编解码器及 Linux/macOS；这些仍是 SEC-23 的跨平台格式验收项。真实用户样本和远端媒体未修改，临时合成文件在运行结束后移除。

## 71. 2026-10-10 AUD-80 媒体错误恢复提示分支

- **发现：** `MediaInvalidError` 继承自 `DownloadError`，但 `_error_details()` 先匹配父类，导致 `MEDIA_DECODE_FAILED` 等媒体校验错误没有返回“确认媒体文件完整且包含可解码音轨”的专用提示。错误码和失败状态仍然正确；受影响的是操作指引，不是失败关闭行为。
- **整改：** 将 `MediaInvalidError` 分类移到通用 `DownloadError` 分支之前，并新增回归，断言稳定错误码、消息和媒体修复提示均返回。
- **验证范围：** `tests/unit/test_pipeline.py` 为 **37 passed, 1 skipped**（当前 Windows 文件系统不支持 symlink）；修改文件的 Ruff 检查通过。没有在该小改动后重跑完整 Python 3.11/3.12 套件；SEC-23 后完整套件结果仍以第 70 节为准。
- **发布状态：** AUD-80 本地源码整改完成。P2 隔离与三次成功捕获、P4 听审/长运行/Agent 上下文、P5 新 Desktop 会话、P6 所有者决定/原生依赖审查/远端 CI 等发布门槛仍开放，整体保持 **NOT READY**。

## 72. 2026-10-10 Agent 默认模型校对、标点与术语纠错

- **用户要求：** 转写结果最终由大模型校对纠错，并使用逗号、句号等中文标点；模型选择遵循调用 Agent 自身默认模型。此要求取代早期实施计划中“Agent 不读取全文”和“LLM 校对延后”的产品规则。
- **精确术语回跑：** 使用用户确认的本地术语词典和 `--force` 对同一授权媒体重新转写，CLI 成功，生成新的 **4,878-byte** 原始稿；此前输出未覆盖。对私有原稿作本地精确计数，用户指出的源词残留 **0**，目标词共 **7** 次；Markdown 元数据记录 1 条匹配规则和 3 次替换。扫描只输出计数，没有输出摘录。
- **Agent 校对：** 当前调用 Agent 的默认模型检查原稿正文、修正上下文足够明确的识别错误、添加中文标点和段落，并生成独立 **5,764-byte** `.reviewed.md`。本地完整性检查确认 frontmatter 保持一致、原始 ASR 文件未修改；校对稿正文包含 141 个中文/句末标点，7 处明确的“需听音确认”提示。没有把正文写入本报告或最终聊天答复，也没有为该校对指定固定供应商 API。
- **相似错误排查：** 除用户提供的词条外，复核发现其他候选集中于英文/模型/公司专名的语音转写、同音词及少数上下文不通的数字/短语。仅改正高置信度名称和词语；无法仅凭文本确定的内容保留为待听音项，不作猜测。词典可以稳定修复用户确认的精确字面匹配；它不能自动判断未知近音词或判断事实真伪。后续校对按两遍执行：先做语义和标点校对，再专门扫可疑词；若宿主提供词频/token 检测器，可用来提名候选，不能单凭低频或未登录就自动替换。
- **产品规则和数据边界：** canonical Skill 现在使用当前 Agent 默认模型；若用户未直接要求/授权校对，先说明正文将进入模型上下文且可能发送给模型服务商并取得同意。保留本地 CLI 原稿，校对写入碰撞安全的 `.reviewed.md`；不在 CLI JSON、错误诊断或聊天回复中回显正文；本地模式跳过模型校对。词频或 token 检测只提供可疑词候选，必须由默认模型结合上下文判断，无法确认时保留原词并标记听音复核。README、SECURITY、ARCHITECTURE、安装说明、实施计划和 release checklist 已同步。
- **验收边界：** 这证明了当前 Agent 对一个获授权样本的模型校对流程，并非音频真值、完整事实核查或跨宿主验收。人工听审至少三处片段、10 分钟以上样本、新 Desktop 会话及宿主数据流仍需验收；P4/P5 与项目发布状态继续 **NOT READY**。

## 73. 2026-10-10 AUD-81 浏览器媒体候选状态限额

- **问题：** `BrowserCapture.capture()` 对识别出的媒体 URL 去重，但保留数量没有上限；`_candidate_from_response()` 也没有限制候选 URL、Content-Type、Expires 和 Referer 的长度。异常页面可扩大内存状态和后续候选下载次数。
- **整改：** 每页最多保留 16 个音频和 16 个视频候选，继续保持音频优先；单个媒体 URL 最长 8,192 字符。超长 Content-Type / Expires 候选被拒绝；Referer 超过 2,048 字符时不保留。限制作用在页面事件回调和候选构造处，不放宽现有 HTTPS、host allowlist、DNS pinning 或手动登录边界。
- **验证：** `tests/unit/test_p2_capture.py` 为 **20 passed**；新增用例验证候选计数、超长 URL/头字段拒绝及音频优先。修改源码与测试的 Ruff 检查通过。该验证使用 Playwright 替身，不证明真实页面成功捕获，AUD-77 进程出口隔离仍未解决。

## 74. 2026-10-10 AUD-82 缓存解码前 deadline 复查

- **问题与影响：** `_find_valid_cache()` 在进入缓存循环时检查期限，随后执行文件 `lstat()` 和大小检查，再调用可能完整解码音轨的 decoder。期限可能在路径元数据操作期间耗尽，导致已超时任务仍启动昂贵解码。
- **整改：** 在确认缓存为普通文件且大小有效后、调用 decoder 前再次调用 `_require_time_remaining()`。超时立即返回 `TIMEOUT`，不启动缓存解码，也不尝试远端下载。
- **回归与结果：** 将原先依赖 `1e-12` 秒墙钟精度的测试改为确定性单调时钟：首轮期限检查有效，缓存路径属性检查后过期；断言 decoder 和 requester 均未调用。完整 `tests/unit/test_p2_downloader.py` **54 passed, 1 skipped**（当前 Windows 文件系统不支持 symlink），覆盖未知容器/流时长时按采样帧计算真实时长并执行媒体上限的用例亦通过。该 focused test 的结束时间为 93.45 秒。
- **边界：** deadline 检查不具备与第三方 decoder 调用的原子性；期限仍可能在检查后立即耗尽。修复确保开始昂贵工作前复查，并在解码完成后继续检查；它不声称能中断一个已启动的同步调用，worker 终止由既有 supervised processing deadline 负责。SEC-23 真正 VBR 与跨平台格式验收仍未完成。

## 75. 2026-10-10 AUD-81/AUD-82 修复后的当前树全量回归

- **Python 3.11：** `uv run --project .\skills\douyin-transcript --locked --no-sync --group dev pytest -vv` 的 verbose 记录结果为 **490 passed, 23 skipped**（Python 3.11.15，331.46 秒）。
- **Python 3.12：** `uv run --isolated --python 3.12 --project .\skills\douyin-transcript --locked --group dev pytest -vv` 结果为 **490 passed, 23 skipped**（Python 3.12.13，420.61 秒）。两套都覆盖 §73 的候选数/长度限制、§74 的缓存解码前期限复查、未知时长按解码样本计时等本轮代码与回归。
- **跳过范围：** 两次均为当前 Windows 主机不具备的 POSIX FIFO、Unix 权限/目录句柄/ownership 或 symlink 能力测试；这不能替代 Linux/macOS 实测。相关文件 Ruff 检查和 `git diff --check` 通过。
- **状态：** 本轮本地工作树在两个 Windows Python 版本上全套通过；不是最终发布提交验证，也不是远端 CI。P2 三次真实视频捕获及 Chromium 进程级 egress isolation、P4 人工听审/长运行/宿主上下文、P5 fresh Desktop 会话、P6 所有者决策/原生依赖 notice 和远端 CI/干净安装继续开放，项目保持 **NOT READY**。

## 76. 2026-10-10 AUD-83 延迟媒体响应观察窗口

- **问题与证据边界：** `capture()` 在页面导航后等待固定 500 ms；如果主文档之后才触发获准媒体请求，候选会一直为空并可能返回 `CAPTURE_NO_MEDIA`。这是一项可改进的观察窗口，不是已证实的既有失败原因；先前真实页面仍有 13/14 个资源 host 被严格策略拒绝。
- **整改：** 没有候选时，在当前总 capture deadline 内每 200 ms 泵送 Playwright 事件，最多额外观察 2 秒；一旦候选到达即停止。候选必须通过现有 HTTPS、host allowlist 与 DNS 检查，不放宽页面或媒体 host allowlist，也不延长 45 秒总时限。
- **验证：** `tests/unit/test_p2_capture.py` **21 passed**（1.19 秒）；新增用例模拟导航后 900 ms 到达的获准音频响应并断言它被发现。改动文件 Ruff 检查通过。
- **剩余验收：** 本节变更发生在 §75 的 490/23 全量回归之后；其定向回归为 21 passed，真实页面复试见 §78，仍为 `CAPTURE_NO_MEDIA`，不能声称捕获改善。AUD-83 已纳入 §79 两版本全量回归（494/23）。13 个资源 host 的归属/必要性、三条成功授权视频、AUD-77 进程级出口隔离及跨平台 CI 继续开放，项目状态 **NOT READY**。

## 77. 2026-10-10 AUD-84 页面元数据和登录提示扫描限量

- **问题：** 页面标题/作者/日期曾通过 `inner_text()` 或属性读取完整 DOM 字符串后才检查长度；登录提示检测也把完整 `body.inner_text()` 传入 Python。恶意或异常页面可在 IPC 之前制造很大的返回值，且只为寻找登录提示无需复制整页正文。
- **整改：** 标题、作者、日期分别限制为 160、256、128 个字符。浏览器端 TreeWalker 至多遍历 4,096 个文本节点，只收集上限加 1 个字符；`content`/`datetime` 属性在浏览器端截断。登录提示扫描最多看 16,384 个字符/4,096 个文本节点，并只返回布尔值。Python wrapper 再做一次 `max_chars + 1` 防御性截断，超限字段不进入元数据/Markdown。
- **验证：** `tests/unit/test_p2_capture.py` **24 passed**，覆盖超长标题、作者、日期、浏览器端返回截断和登录正文仅返回布尔值；capture 源码及测试的 Ruff 检查通过。
- **限制：** 受限登录扫描可能看不到页面很靠后的提示；仍同时检查 passport URL 和显式登录控件。AUD-84 已包含在 §79 双版本全量套件中；获授权真实页面复试仍无媒体，没有完成成功捕获路径下的页面集成验收。

## 78. 2026-10-10 AUD-83 修复后的真实 P2 重试

- **执行：** 使用此前获授权的页面和可见 Playwright/Chromium，经 `retry-failed --limit 1 --json` 重新捕获。返回 `CAPTURE_NO_MEDIA`；没有媒体候选、标题或转写输出，私有输出目标未创建。
- **结论：** 这次重试确认短暂延迟观察窗口没有让该页面出现可获准媒体候选；它仍然只算一次失败，不满足三条成功视频要求。未读取页面转写正文，也未记录 cookie 或签名媒体 URL。
- **后续：** 保持资源 host allowlist 不变；取得另外获授权且能通过现有策略的候选链接，完成三条成功端到端捕获，并解决 AUD-77 的进程级出口隔离。P2 与发布状态继续为 **NOT PASSED / NOT READY**。

## 79. 2026-10-10 AUD-81–84 最新 Windows 全量回归

- **Python 3.11.15：** `uv run --project .\skills\douyin-transcript --locked --no-sync --group dev pytest -vv`，结果为 **494 passed, 23 skipped**（237.60 秒）。
- **Python 3.12.13：** `uv run --isolated --python 3.12 --project .\skills\douyin-transcript --locked --group dev pytest -vv`，结果为 **494 passed, 23 skipped**（341.52 秒）。该测试在隔离临时环境安装锁定 dev 组。
- **跳过范围：** 23 项均依赖 Windows 主机无法提供的 POSIX FIFO、Unix 权限/目录句柄/ownership 或 symlink 创建能力；不代表 Linux/macOS 行为已通过。
- **范围：** 此次两套全量回归都覆盖 AUD-83 延迟响应观察与 AUD-84 浏览器侧元数据/登录文本限量。capture 与测试的 Ruff 定向检查也通过。最终发布提交、远端 CI 和跨平台矩阵仍未验证；P2、P4 和所有者决策仍开放，整体 **NOT READY**。

## 80. 2026-10-10 AUD-85 缓存枚举 deadline 与最终回归

- **问题：** `_find_valid_cache()` 先对 `cache.glob(...)` 全部结果排序/物化，再进入循环检查 cancellation 和共享 deadline。目录中有大量同 ID/类型的旧媒体文件时，扫描和列表分配可能先于 deadline 检查发生。
- **整改：** 改为 `cache.iterdir()` 流式枚举；每取得一个条目即检查取消和 deadline，再按当前 `video_id`/媒体类型前缀筛选，逐个验证匹配文件。不再对整个 glob 结果排序。
- **定向验证：** `tests/unit/test_p2_downloader.py` **55 passed, 1 skipped**（3.74 秒）；新回归模拟慢目录条目，并断言期限耗尽时不调用媒体 decoder；downloader 源码/测试 Ruff 通过。
- **最终本机全套：** Windows Python 3.11.15 **495 passed, 23 skipped**（509.57 秒）；隔离 Windows Python 3.12.13 **495 passed, 23 skipped**（520.52 秒）。23 项为本 Windows 主机不能提供的 POSIX FIFO、Unix 权限/目录句柄/ownership 或 symlink 能力。
- **限制与状态：** 两个全套覆盖 AUD-81–85；未提供 Linux/macOS 实测或远端 CI。目录枚举逐项检查 deadline，但单次底层文件系统枚举调用仍受 OS 响应时间约束。P2 页面仍为 `CAPTURE_NO_MEDIA`，P2、P4、所有者发布决策与远端 CI 仍开放，项目 **NOT READY**。

## 81. 2026-10-10 项目续审与所有者决策清单

- **截至 §81 的状态快照（后续进展见 §§82–83 及其后续章节）：** 本地工作树仍基于 `master` / `b166778`，尚无最终 release commit。最新全套代码回归见 §80，为 Windows Python 3.11.15/3.12.13 各 **495 passed, 23 skipped**；23 个 POSIX 能力跳过项不是 Linux/macOS 验收。当前远端列表为空；本机无 `gh`、Docker 或 `act`，WSL 没有安装 Linux 发行版；当前 PowerShell 非管理员。本轮未改系统网络设置。
- **P2 复核：** AUD-83 窗口调整后，唯一获授权链接仍为 `CAPTURE_NO_MEDIA`。失败不计入验收；必须累计三条不同授权视频的成功端到端捕获。AUD-77 仍缺覆盖 Chromium 子进程树的 OS 级出口隔离；用户已授权代理选择方案，§82 选定主机管理员预配置的外部系统沙箱。当前主机没有已配置/已验证的沙箱，应用也未接入 fail-closed provider 检查；选型不代表修复完成。仍需完成集成、管理员配置，并用锁定 Chromium 做真实拒绝与授权代理 HTTPS 正向测试。
- **P4 复核：** 已有 315.907 秒本地样本及调用 Agent 默认模型生成的标点校对稿；仍未达到 10 分钟以上样本和至少三处人工听审要求。校对 Skill 已说明可疑 token/词频检查只能提名候选，低频本身不得触发替换。
- **P6 复核（§81 时点）：** 无根目录 `LICENSE`、无 Git remote、未运行远端矩阵。该节当时记录 SPDX/uv.lock 为 42 个 package records、37 个第三方 `licenseDeclared`；§83 随后补充三项锁定发行物许可证文件证据，当前计数见 §83。所有 `licenseConcluded` 仍为 `NOASSERTION`。项目许可证、账户/可见性、发行范围、远端操作授权是所有者决策；发行范围确定后仍须按范围完成构建 provenance 与 bundled/native license/notice 审阅。
- **文档状态修复：** 更新 `RELEASE_REPORT.md` 中 SEC-17 本地模型验收、SEC-23 未知时长覆盖、§70/§80 测试时序、流水线定向测试和扫描快照先后关系；更新 `RELEASE_CHECKLIST.md` 的旧版测试数字引用；拆分实施计划中已完成的本机检查与尚未完成的远端/Agent 宿主验收。新增 `docs/OWNER_DECISIONS.md` 汇总上述输入与当前环境证据。
- **静态复核：** 当前树 Ruff、锁文件、敏感文件检查及两个 Agent Skills validator 通过；`git diff --check` 退出码为 0。完整测试没有因本节文档编辑重跑；代码全套证据仍是 §80。
- **下一步与状态：** 本地可继续做代码和发行范围内的只读许可证研究；P2 外部沙箱运行器/证明集成与管理员配置、真实视频/P4 样本、许可证/发行范围及远端发布仍需代码工作或外部环境。未完成以上门槛前维持 **NOT READY**。输入清单见 `docs/OWNER_DECISIONS.md` 和 `docs/P2_ISOLATION_DECISION.md`。

## 82. 2026-10-10 AUD-77 隔离方案选择与环境能力审计

- **用户授权与方案决定：** 用户明确授权代理自行选择 P2 隔离方案。选择由主机管理员预配置的外部系统级网络沙箱；项目不分发/安装高权限 Windows WFP、Linux network namespace/firewall 或 macOS Network Extension 适配器。理由、策略要求、动态验收和限制见 `docs/P2_ISOLATION_DECISION.md`。Windows WFP ALE 能按应用身份过滤 TCP connect 与首个 UDP flow；Linux network namespace 提供隔离网络设备/路由/防火墙规则的机制；macOS Network Extension 可实现连接过滤并有签名/entitlement 部署要求。平台机制不等于本项目已配置或验证隔离。
- **当前主机检查：** Windows 11 Enterprise LTSC build 10.0.26100；PowerShell 不是管理员，Docker 未安装，WSL 未安装 Linux 发行版。本轮没有修改 Windows Firewall、WFP、注册表或系统网络设置，也没有尝试以 Chromium 参数或代理状态冒充隔离。
- **实施差距与当前技术决策（截至 §82 审查时点；应用侧 gate 后续见 §84）：** 当时工作树尚未集成 provider；当前也无外部沙箱供锁定 Chromium 动态测试。Windows 侧实施目标已细化为管理员预装的 WFP broker：`BrowserCapture.start()` 核验锁定 Chromium 身份、启动受控 loopback 代理、通过 ACL 保护且验证服务身份的固定 IPC 获取绑定本次浏览器身份/代理端口的 lease，只有 lease 有效后才启动 Chromium；broker/策略缺失或 lease 中断时应停止捕获并关闭浏览器。不得把环境变量、配置布尔值或代理可达性当作证明。该时点的契约尚未实现，当前环境不是管理员，因此不能证明无沙箱时应用拒绝启动或验证 WFP filters。§84 已新增应用侧 fail-closed refusal gate，但没有真实 broker transport、管理员策略或动态 WFP 验收。AUD-77 保持 OPEN，P2 保持 NOT PASSED；仍须管理员部署外部策略并动态验证规则失败/管理面退出、Chromium 全进程树、IPv4/IPv6、loopback/LAN/UDP 拒绝及获授权 HTTPS 正向捕获。
- **真实媒体门槛：** 唯一用户提供链接之前的修复重试均返回 `CAPTURE_NO_MEDIA`，不计成功；仍需三条不同获授权视频端到端成功，且不放宽未确认归属的 13/14 页面资源 host allowlist。
- **回归口径：** 本节为架构/环境/文档审查，不改动代码，不增加或运行测试。最新代码全套回归仍引用 §80；本节决策不是 P2 功能完成或发布批准。

## 83. 2026-10-10 P6 锁定构建依赖许可证文件补证

- **目标：** 检查先前因元数据缺少 `License` 字段而未写入 `licenseDeclared` 的 `editables`、`pathspec`、`trove-classifiers`，避免仅因为元数据缺项就把锁定包留作未解析。
- **制品身份与文件证据：** 直接从 `uv.lock` 取出三个 PyPI wheel URL；对下载完整字节分别核对锁定 SHA-256 和大小，再从 ZIP 中读取许可证成员，并验证 wheel `RECORD` 中的成员 hash/size。

| 包/版本 | 锁定 wheel SHA-256 | `RECORD` 验证成员 | 文件 SHA-256 | 支持的 `licenseDeclared` |
|---|---|---|---|---|
| editables 0.5 | `61e5ffa82629e0d8bfe09bc44a07db3c1ab8ed1ce78a6980732870f19b5e7d4c` | `editables-0.5.dist-info/LICENSE.txt` | `c73e08a04e1557fdb49525fb7a579f73bcab84a254910b9350ee56daf143932d` | MIT |
| pathspec 1.1.1 | `a00ce642f577bf7f473932318056212bc4f8bfdf53128c78bbd5af0b9b20b189` | `pathspec-1.1.1.dist-info/licenses/LICENSE` | `fab3dd6bdab226f1c08630b1dd917e11fcb4ec5e1e020e2c16f83a0a13863e85` | MPL-2.0 |
| trove-classifiers 2026.9.21.13 | `8b1ff4f9c191b1040b71c37f1e445ab99732911e3cd91de52838453a854d7a17` | `trove_classifiers-2026.9.21.13.dist-info/licenses/LICENSE` | `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` | Apache-2.0 |

- **整改：** 将三项加入 artifact-bound evidence，并在生成器固定审阅表绑定 package/version、完整 wheel SHA、路径、文件 SHA、SPDX 表达式及审阅说明。项目包的 `licenseConcluded` 未变化；未把许可证文件存在等同于对应用整体或捆绑组件作法律结论。
- **验证：** 当前离线 verifier 报告 **41 packages, 46 artifacts, 41 metadata, 7 license, 1 notice members**；SBOM 已重生成，含 42 个 package records 和 58 个 relationships。41 个第三方包中 40 个具有 evidence-backed `licenseDeclared`；唯一仍为 `NOASSERTION` 的 `python-dateutil==2.9.0.post0` 声明是未映射的 `Dual License`。所有包 `licenseConcluded` 仍是 `NOASSERTION`。锁定包名/版本与 SBOM 完全对齐（42/42），生成物通过 SPDX 2.3 官方 JSON Schema 验证。定向 `tests/unit/test_spdx_evidence_verifier.py tests/unit/test_spdx_sbom.py` 为 **50 passed, 3 skipped**（92.40 秒）；跳过项依赖 Windows 不支持的 POSIX FIFO。生成器 Ruff 和 `git diff --check` 通过。
- **边界与项目状态：** 该检查只补充三个包级文件证据，不完成可选依赖/dev 组是否分发的所有者决定，也不关闭 NumPy/ONNX/CTranslate2/Rust/FFmpeg 组件、notice 到二进制映射、远端 CI、仓库与项目许可证决定。P6、P2、P4、P5 均仍开放，整体保持 **NOT READY**。

## 84. 2026-10-10 AUD-77 应用侧 fail-closed gate

- **实施范围：** 新增 `isolation_broker.py`，定义 Chromium 规范路径/SHA-256/Playwright 版本/revision、调用者 PID、精确 `127.0.0.1:<port>` 代理端点及 lease 生命周期的数据契约。没有定义未经确认的服务名、命名管道路径或 IPC wire protocol；没有 broker transport 或受信任锚，所以生产 `open_system_broker()` 明确返回 unavailable。`BrowserCapture.start()` 在创建 profile、启动 Playwright driver、代理和 Chromium 之前返回 `BROWSER_ISOLATION_UNAVAILABLE`。调用方不能用 `executable_path`、`args`、`proxy`、`channel`、`env` 或 `ignore_default_args` 覆盖浏览器身份/网络选项。
- **Lease 生命周期：** 未来 broker adapter 的 `ensure_active()` 必须是异步 heartbeat/IPC monitor 缓存的非阻塞读取；当前没有实现该 monitor。应用在 HTTP/WebSocket route、启动和捕获边界检查状态；route 检查失效时 abort，随后按 context→lease→proxy→Playwright 关闭。broker 必须负责 idle/同步操作期间的即时 WFP 撤销、默认拒绝和子进程覆盖。Chromium SHA 只是易变文件快照，broker 仍须解决身份信任、替换/TOCTOU 和策略摘要验证。
- **doctor：** 新增 `browser_isolation=unavailable`，即使 Playwright/Chromium 已安装，`douyin_urls` 也保持 `setup_required`；普通服务可达不能单独成为策略证据。
- **定向验证：** `tests/unit/test_p2_capture.py` 与 broker 缺失 doctor 回归合计 **29 passed**；相关源码/测试 Ruff 检查通过；`git diff --check` 通过。测试只证明应用拒绝与关闭顺序，不证明 WFP 规则或网络边界。
- **结论与未完成项：** 当前无 IPC endpoint、broker service、策略证明或管理员预配置系统沙箱，因此 URL 捕获会安全拒绝，无法做真实成功 lease、WFP 正负向 egress、renderer/utility 进程树或代理 HTTPS 动态验收。唯一获授权视频仍 `CAPTURE_NO_MEDIA`；三条成功视频门槛未满足。AUD-77 **OPEN**、P2 **NOT PASSED**，整体保持 **NOT READY**。

## 85. 2026-10-10 AUD-77 方案复核与宿主能力核验

- **用户授权与选择：** 用户再次授权代理自行选择最优隔离方案。复核后继续选择由主机管理员管理的外部系统级 WFP broker/沙箱：它避免在当前本地 Python 项目中引入未经部署和动态审计的高权限网络组件，同时可让系统策略所有者负责持久默认拒绝。该决定是架构选择，不代表 provider 已部署。WFP 官方说明硬阻断是最终决定，且动态会话对象在管理会话结束时自动删除；因此 provider 必须保留持久阻断，只为本次捕获添加精确、短期的代理例外。见 Microsoft [filter arbitration](https://learn.microsoft.com/en-us/windows/win32/fwp/filter-arbitration) 和 [object management](https://learn.microsoft.com/en-us/windows/win32/fwp/object-management)。
- **宿主权限证据：** 当前进程为 medium integrity；Administrators 组 SID 标记为 deny-only，没有管理员令牌。BFE 与 Windows Defender Firewall 服务运行，但该状态不证明存在 Chromium 过滤器或 broker。`wsl --list --quiet` 无发行版，Docker CLI/server 不可用。对 Windows Sandbox、Hyper-V、Virtual Machine Platform 和 WSL 的 `Get-WindowsOptionalFeature -Online` 查询均返回 `COMException`，故其功能状态记作未知，而非禁用。未改动防火墙、WFP、注册表或网络设置。
- **当前应用侧验证：** `uv run --project skills/douyin-transcript --no-sync pytest -q tests/unit/test_p2_capture.py tests/test_doctor.py`：**48 passed**。结果只验证 broker 不可用时应用在 Playwright/Chromium 启动前拒绝，以及 doctor 的 setup-required 状态；没有 broker transport、WFP 正负向网络探测、浏览器子进程动态测试或媒体成功捕获。
- **未通过项与对策：** `open_system_broker()` 仍无认证 transport/provider，`doctor` 继续显示 `browser_isolation=unavailable` 与 `douyin_urls=setup_required`。AUD-77 **OPEN**、P2 **NOT PASSED**。需由管理员在此主机部署可信 broker/策略，或在已有受管沙箱上运行；随后验证 lease/服务丢失时默认阻断、完整 Chromium 子进程、IPv4/IPv6、loopback/LAN、UDP 拒绝及获准代理 HTTPS 正向路径，再对三条不同授权视频完成端到端捕获。用户授权代理作方案选择不会自动提供 OS 管理员令牌，也不会创建缺失的系统组件。
- **整体状态：** P1 真实本地处理与 P3 离线恢复已通过；P2 系统级隔离和三条成功捕获、P4 长样本/抽听/目标 Agent 数据流、P5 新 Desktop 会话及 P6 所有者许可证/发行决策、原生依赖审阅和远端 CI 仍未完成，项目继续 **NOT READY**。

## 86. 2026-10-10 python-dateutil 锁定许可证文件补证

- **问题与处理：** §83/§85 的离线 SBOM 证据仍有一个第三方包没有 evidence-backed `licenseDeclared`：`python-dateutil==2.9.0.post0` 的 `PKG-INFO` 将许可证写作非 SPDX 表达式 `Dual License`。检查了 `uv.lock` 锁定的精确 sdist，而不是依赖本机安装元数据或泛化项目页面。
- **制品绑定证据：** 锁定 sdist 的大小为 **342,432 bytes**，SHA-256 为 `37dd54208da7e1cd875388217d5e00ebd4179249f90fb72437e91a35459a0ad3`；归档内 `PKG-INFO` SHA-256 为 `d19fba9fe39f32faf5f738882f3f368893b0a5f1ad2fe33e20920657cb0b52b1`；`python-dateutil-2.9.0.post0/LICENSE` 为 2,889 bytes，SHA-256 为 `ba00f51a0d92823b5a1cde27d8b5b9d2321e67ed8da9bc163eff96d5e17e577e`。上游同版本的 [LICENSE](https://github.com/dateutil/dateutil/blob/2.9.0.post0/LICENSE) 说明 BSD 条款适用于所有代码，包括同时受 Apache 2.0 覆盖的代码。因此，SBOM 采用对包内代码均适用的 `BSD-3-Clause` 作为包级 `licenseDeclared`，并在 comment 中保留依据与范围边界。
- **审计边界：** 该声明修复 `Dual License` 到 SPDX 表达式的证据映射；`licenseConcluded` 仍为 `NOASSERTION`，也没有推断所有捆绑内容、构建产物或发行义务已完成审阅。上游 [2.9.0.post0 PyPI release](https://pypi.org/project/python-dateutil/2.9.0.post0/) 可用于核对版本/发布文件；本地清单绑定完整 artifact 与许可证成员摘要，生成器固定审阅映射并拒绝不匹配的证据字节。
- **整改与验证：** 更新 `docs/third-party-license-evidence.json`、`scripts/generate_spdx_sbom.py` 和 SBOM 定向回归，使映射绑定包版本、锁定归档摘要、成员路径和许可证文件摘要。离线 verifier 当前结果为 **41 packages, 46 artifacts, 41 metadata, 8 license, 1 notice members**；SBOM 包含 42 个 package records、58 个 relationships，41/41 个第三方包都有 evidence-backed `licenseDeclared`。SPDX 定向回归 **51 passed, 3 skipped**（3 项依赖 Windows 不支持的 POSIX FIFO）；Ruff 通过。生成物通过 SPDX 上游 [support/2.3 JSON schema](https://github.com/spdx/spdx-spec/blob/support/2.3/schemas/spdx-schema.json) 校验；使用 schema SHA-256 `4126dc29f15e92feec92e9622f4939131ad58b125d6f578aa93e980a6e6f3212`。`uv.lock` 包身份/生成器清单的一致性也由通过的定向测试覆盖。
- **剩余工作：** P6 仍需所有者确认项目 LICENSE、实际分发范围、仓库归属/可见性与远端授权；还需将 ONNX Runtime notices 映射到链接组件、取得 CTranslate2/Tokenizers/Ruff/PyAV 等精确原生构建 provenance 和平台组件证据，并运行远端矩阵 CI 与干净安装。该补证不关闭这些事项；P6 及整体仍 **NOT READY**。

## 87. 2026-10-10 Playwright 锁定 wheel 许可证/通知成员补证

- **问题与范围：** 既有环境扫描注意到 Playwright 1.63.0 wheel 有 8 个许可证/通知类候选文件，但没有把其余锁定平台 wheel 的成员摘要加入可重复的离线证据。用户已授权使用 Playwright；本次只读取 `uv.lock` 固定的 Python wheels，不安装 wheel，也不改动浏览器/网络设置。
- **制品身份：** 从锁文件读取并校验 8 个平台 wheel（macOS x86-64/arm64/universal2、Linux x86-64/aarch64、Windows x86/amd64/arm64），累计 **339,357,074 bytes**。每个归档大小与 SHA-256 都与 `uv.lock` 一致。逐个读取 ZIP 的 `RECORD`，发现每个 wheel 均含相同的 8 个许可证/通知类路径；共 **64 个成员**，64/64 的内容摘要和字节数都与各自 `RECORD` 一致。
- **成员观察：** 8 个候选路径为 `playwright/driver/LICENSE`、`playwright/driver/package/LICENSE`、`playwright/driver/package/NOTICE`、`playwright/driver/package/ThirdPartyNotices.txt`、`playwright/driver/package/lib/serverRegistry.js.LICENSE`、`playwright/driver/package/lib/utilsBundle.js.LICENSE`、`playwright/driver/package/lib/webp_codec.LICENSE` 和 `playwright-1.63.0.dist-info/licenses/LICENSE`。除平台相关的 `driver/LICENSE` 外，其余 7 个文件在 8 个 wheel 中内容摘要相同。`ThirdPartyNotices.txt` 说明 `lib/` 下的 bundled JavaScript 输出以相邻 `.js.LICENSE` 文件记录内联 npm 包和许可文本；wheel 还携带独立的 driver 级 LICENSE。完整的 wheel URL/锁定 hash、成员路径/hash/size 已写入 `docs/third-party-license-evidence.json` 的 Playwright `artifact_members`，可用离线 verifier 重验。
- **SBOM 与验证：** Playwright 的 `licenseDeclared=Apache-2.0` 由锁定 Windows wheel 的 `.dist-info/licenses/LICENSE` 文件证据支持，并绑定生成器固定审阅映射。离线 verifier 当前结果为 **41 packages, 53 artifacts, 41 metadata, 9 license, 1 notice, 63 supplemental members**；63 个 supplemental 成员加 1 个主 LICENSE 对应上述 64 个 wheel 成员。SBOM 仍有 42 个 package records、58 个 relationships。定向回归 **56 passed, 3 skipped**；Ruff 通过，SPDX 上游 support/2.3 JSON Schema 校验通过。
- **边界：** 文件摘要、RECORD 一致性和上游 wheel 内提示证明文件存在并对应锁定 wheel，不构成每个 Node/JavaScript/native 组件的完整许可结论；Playwright setup 另外下载的 Chromium/browser binaries 也不在这些 Python wheel 中。需继续取得目标浏览器下载制品和实际组件来源/许可审阅，并解决 P6 项目 LICENSE、分发范围、原生依赖 provenance 与远端 CI。`licenseConcluded` 继续为 `NOASSERTION`，P6 和项目整体仍 **NOT READY**。

## 88. 2026-10-10 Codex Skill 发现描述与实际能力对齐

- **发现：** 仓库入口 `.codex/skills/douyin-transcript/SKILL.md` 的 frontmatter 仍宣传可处理 Douyin URL 和批次请求；canonical `skills/douyin-transcript/SKILL.md` 已明确 URL 捕获因缺少认证 WFP broker 而关闭。该描述不一致可能让 Agent 在执行前向用户承诺当前不可用的能力。
- **整改：** 将 repo-scoped discovery 描述改为支持本地媒体转写及 URL readiness 查询，并明确 URL 捕获当前被阻断；canonical Skill 内容与 CLI 未改变。
- **验证：** 使用锁定的 `skills-ref` validator 分别验证 `.codex/skills/douyin-transcript` 和 `skills/douyin-transcript`，两者均返回 `Valid skill`。Windows Python 3.11.15 全套 pytest 为 **506 passed, 23 skipped**（333.86 秒）；Python 3.12.13 全套为 **506 passed, 23 skipped**（328.29 秒）。23 项跳过为 Windows 不支持的 POSIX FIFO、symlink、ownership 或 mode-bit 行为；它们不等同于 Linux/macOS 验收。该结果不代表真实新 Desktop 会话已发现或调用 Skill。
- **状态：** 该修复关闭 repo 入口发现描述与实际功能不一致的问题。P5 仍为 **PARTIAL**，仍需新 Desktop 会话记录宿主版本/来源、`/skills` 发现、显式 `$douyin-transcript` 调用、argv 与脱敏结果；P2/P4/P6 外部门槛未变，整体继续 **NOT READY**。

## 89. 2026-10-10 ONNX Runtime CPython 3.12 wheel notice 补证

- **范围：** 检查 `uv.lock` 固定的 `onnxruntime==1.30.0` CPython 3.12 Windows x64 wheel，未安装该 wheel。归档 `onnxruntime-1.30.0-cp312-cp312-win_amd64.whl` 为 **14,311,470 bytes**，SHA-256 `f3501472571f1b1eee50e017851e7929f5ea37312d2d8c2494a19e8fc58b4a38`，与锁文件一致。
- **成员证据：** wheel 内 `onnxruntime/ThirdPartyNotices.txt` 为 **344,457 bytes**，SHA-256 `c53a76501ef60db6f865f20599f220761201ac4057683acefdab37d861b86622`；成员大小和哈希与 wheel 的 `RECORD` 相符。其内容哈希与已记录的 CPython 3.11 wheel notice 相同，因此证据清单新增了第二个 artifact-bound notice 引用。它证明这个锁定归档含该 notice，不证明其中列出的组件实际链接到该 wheel 二进制。
- **生成与离线核验：** 按更新后的证据清单重建 `docs/third-party-sbom.spdx.json`。离线 verifier 报告 **41 lock packages, 54 artifacts, 41 metadata, 9 license, 2 notice, 63 supplemental members**；截至本节生成的快照有 42 个 `uv.lock` package records 和 58 个 relationships。41 个锁定第三方包 `licenseDeclared` 均有证据，所有 `licenseConcluded` 仍为 `NOASSERTION`。§91 随后将 Playwright sidecar 列出的 79 个 npm 组件加入 SBOM，并补做官方 SPDX 2.3 JSON Schema 验证。
- **本机回归：** Windows Python 3.11.15 全套 pytest **506 passed, 23 skipped**（333.86 秒）；Windows Python 3.12.13 全套 **506 passed, 23 skipped**（328.29 秒）。23 项跳过是 Windows 上不可用的 POSIX FIFO、symlink、ownership 或 mode-bit 行为。证据 verifier 通过；后续定向 SPDX 回归和 Schema 校验仍需在本轮其它 SPDX 组件清单完成后记录。
- **状态：** 该补证把第二个锁定 Windows wheel 中 notice 文件的字节证据纳入清单，不代表 notice 条款到链接组件的映射已完成，不关闭项目许可证、分发范围、原生依赖审阅或远端 CI 门槛。P6 和整体仍为 **NOT READY**。

## 90. 2026-10-10 UAC 探针与 WFP broker 可行性复核

- **用户授权与探针：** 用户授权代理自主选择路径。本机普通 Codex shell 仍是非管理员令牌；通过标准 UAC 启动只读 PowerShell 探针成功取得管理员令牌。探针仅查询管理员组令牌、BFE/Windows Defender Firewall 服务与 Windows 可选功能，没有调用 WFP 修改 API，也没有更改防火墙、注册表或网络设置。
- **本机环境：** BFE 与 Windows Defender Firewall 服务运行。Windows Sandbox (`Containers-DisposableClientVM`)、Hyper-V、Virtual Machine Platform 和 WSL 可选功能均报告 Disabled。当前代码仍没有项目 broker 服务、IPC 名称、签名/服务身份锚或可读回验证的策略摘要；因此可提升的管理员会话没有替代缺失 broker/provider。
- **可行路径与限制：** Microsoft WFP ALE/FWPM 支持在用户态管理按应用身份匹配的过滤器，基础连接过滤不必然需要自写 kernel callout；但可靠的 per-capture proxy exception 要与默认拒绝策略协调在同一 sublayer 的 filter arbitration 中，且要测试动态 lease 消失后的现有 flow 重新授权。WFP block 可能压过冲突 allow，ALE 的规范化路径身份也不是可执行文件签名或哈希。关联文档：[ALE layers](https://learn.microsoft.com/en-us/windows/win32/fwp/ale-layers)、[WFP access control](https://learn.microsoft.com/en-us/windows/win32/fwp/access-control)、[object management](https://learn.microsoft.com/en-us/windows/win32/fwp/object-management)、[filter arbitration](https://learn.microsoft.com/en-us/windows/win32/fwp/filter-arbitration)。只读技术结论由 `p2_broker_client` 复核。
- **风险处置：** 保持 `docs/P2_ISOLATION_DECISION.md` 选定的管理员管理 WFP broker 与应用侧 fail-closed。没有尝试用通用 Windows Firewall block/allow 规则模拟进程沙箱，也没有启用/安装 Windows 可选组件或创建系统策略；自行新增项目级高权限服务还需服务身份锚、受限 IPC、持久默认拒绝、代理精确许可、启动/卸载策略、升级回滚和完整 Chromium 子进程覆盖的设计及独立验收。
- **状态：** UAC 提升成功只解决了“能否运行一次管理员探针”的问题，不证明宿主安装了系统隔离组件。AUD-77 **OPEN**、P2 **NOT PASSED**；下一步是接入受信任管理员 broker，或完成并审阅项目 broker/service 及 installer，之后动态验证 IPv4/IPv6、loopback/LAN/UDP deny、批准 HTTPS proxy path、lease 崩溃和已建立连接撤销，并完成三条不同授权媒体的成功捕获。

## 91. 2026-10-10 Playwright npm sidecar 组件清单与 SPDX 补充

- **锁定制品和 sidecar：** 以锁定的 Playwright 1.63.0 Windows x64 wheel 为证据来源，wheel SHA-256 `2f9a707a6c6c91157ed77bff2b8caeb04b3c8d46e70d585fc134298cbe4b5cc6`。`serverRegistry.js.LICENSE` 为 2,982 bytes、SHA-256 `3098a6efcbc11752cbdf6075fa65480f5470f78c8d981fab9c0796dc9a41cefe`；`utilsBundle.js.LICENSE` 为 106,591 bytes、SHA-256 `2495f30be29620d54b58339821eda0ebabdfb6ee9b09455f7285a06fd46fb9f3`。两份成员路径、大小及 SHA-256 与 wheel `RECORD` 相符。
- **组件盘点：** 两个 sidecar 出现 81 次 package@version，去重后是 79 个 npm 组件。78 个条目含可识别许可证正文：MIT 65、ISC 7、BSD-3-Clause 4、BSD-2-Clause 1、BlueOak-1.0.0 1；`proxy-agent-negotiate@1.1.0` 仅显示 MIT 声明，没有许可证正文。重复出现在两份 sidecar 的组件在 SBOM 中只建一个 package，并保留各自 sidecar evidence links。
- **SPDX 结构：** SBOM 加入 79 个 npm package records，各声明均绑定 sidecar 的 package catalog 摘要和 wheel/member 摘要，Playwright 父包有 79 条 `CONTAINS` 关系。无正文条目的 `licenseDeclared=MIT` 明确标注仅来自 sidecar 声明；79 个新 package records 的 `licenseConcluded` 全部为 `NOASSERTION`。无版本的 WebP sidecar 注释仅记录 libwebp 与 Emscripten 线索，不创建无版本 SPDX packages，也不把 Node.js/musl 文本推断为当前 Windows wheel 的直接依赖。
- **生成与验证：** SBOM 从 42 个 `uv.lock` records 扩展为 **121 package records / 137 relationships**。使用官方 SPDX `support/2.3` schema，schema SHA-256 `4126dc29f15e92feec92e9622f4939131ad58b125d6f578aa93e980a6e6f3212`；2026-10-10 的本机结构验证通过，validator 为临时 `jsonschema==4.25.1`。SPDX verifier 报告 **41 lock packages, 54 artifacts, 41 metadata, 9 license, 2 notice, 63 supplemental members**；Windows Python 3.11.15 下 `tests/unit/test_spdx_evidence_verifier.py` 与 `tests/unit/test_spdx_sbom.py` 合计 **60 passed, 3 skipped**（92.91 秒），Ruff 通过。最终固定时间戳为 `2026-10-10T10:47:01Z`。
- **剩余边界：** Sidecar 本身明确关联内联 JavaScript 输出；这些记录是归档内声明/文本证据，不是上游构建 attestation，也不能确定所有包在运行中的使用路径、完整 native BOM 或再分发义务。Playwright 另外下载的 Chromium binary 不在 Python wheel 内。ONNX Runtime notice 到链接二进制的映射、CTranslate2/Rust/FFmpeg 构建 provenance、其他平台 wheel 组件、项目 LICENSE、发行范围、远端 CI 仍开放；所有 packages `licenseConcluded=NOASSERTION`，P6/整体仍 **NOT READY**。

## 92. 2026-10-10 当前工作树复验与 npm 许可正文缺口复核

- **全套回归：** 在当前工作树重新运行完整 pytest。Windows Python 3.11.15 为 **510 passed, 23 skipped**（245.28 秒）；独立 Windows Python 3.12.13 临时环境为 **510 passed, 23 skipped**（144.51 秒）。23 个跳过项依赖本机不支持的 POSIX FIFO、符号链接、ownership、权限或目录句柄行为，不构成 Linux/macOS 通过证据。
- **本机发布检查：** Ruff 全仓相关目录检查、Git 可见敏感文件检查、`uv lock --check`、canonical 与 repo-scoped 两个 Agent Skills validator、仓库外 clean Skill install、SPDX 离线证据 verifier 均通过。SPDX verifier 当前确认 **41 lock packages、54 artifacts、41 metadata、9 license、2 notice、63 supplemental members**；这只验证已记录的字节和元数据，不结论许可证适用性或发行义务。当前工作树已有修改尚未形成最终 release commit，未运行远端 CI。
- **未覆盖的正式扫描：** 本轮当前任务没有暴露 Codex Security Deep Scan coordinator 工具，因此未生成新 sealed scan。§66 的正式 Diff Scan 是冻结工作树结果，不覆盖随后加入的 SBOM generator/组件目录等文件；本次本机回归和定向只读审阅不能冒称完整仓库安全扫描。
- **npm 精确版本核验：** 从官方 npm registry 获取 `proxy-agent-negotiate@1.1.0` metadata 和 tarball。registry 声明 `MIT`，tarball integrity 为 `sha512-N8IBcM3UgCVzz2L2Lqv8DVntDnnC8/hiV4nEDUPkqq72TPUgYWjQc+bdZlBPZK9LzPAvOY//gAt0S0DApoOXWQ==`；下载文件 1,924 bytes，SHA-256 `6eec23d5d381a8b0ffafe91c19876d3a052e463618695981a7529f3a8bca1997`，registry integrity 核验通过。tarball 只有五个文件，含 `package/package.json`（972 bytes，SHA-256 `7b7c2579ea138d20d4f7699ca78ef16c526f35168dbf694f1d47cc861b0954d`），没有 LICENSE 文件；该 package.json 再次声明 `MIT`。GitHub 项目的 `proxy-agent-negotiate@1.1.0` release 页面指向已验证签名的 commit `b7e5f7c`；其精确 commit tree 中没有仓库根 LICENSE 或 `packages/negotiate/LICENSE`。这支持“上游公开声明 MIT，但已核查发行 tarball/对应源码树未提供许可正文”的记录，不推定其许可全文或发行义务。
- **状态：** 保持 sidecar `licenseDeclared=MIT` 且 `licenseConcluded=NOASSERTION`；P6 仍需项目所有者决定 LICENSE/交付范围/仓库与远端操作授权，并取得范围内 native/build provenance 和许可/notice 结论。P2 仍无可信 broker 与动态隔离验收；P4 仍无 10 分钟以上样本和人工听审；P5 仍无新 Desktop 会话记录。项目整体继续 **NOT READY**。
## 93. 2026-10-10 P2 隔离架构修订与安全实施前置条件（当时工具链快照，后由 §§94–95 更新）

- **授权与架构变更：** 用户授权代理自主选择并操作解决方案。前次选择的“主机管理员预配置外部沙箱”在本机没有 broker/provider 或可验证策略，无法接通。基于 WFP 用户态 API 可按应用身份管理 ALE filters 的技术复核，改为项目维护、由管理员安装的 Windows WFP service；首阶段范围仅为 Windows 11 x64。此为可行性选择，不表示实现已开始或安全门槛已通过。
- **最小策略设计：** 持久 provider/sublayer 在 `ALE_AUTH_CONNECT_V4` 与 `ALE_AUTH_CONNECT_V6` 对受管理员保护路径下的锁定 Chromium 默认拒绝；每个 capture lease 使用独立 WFP dynamic session，仅许可 TCP 连接到精确 `127.0.0.1:<port>`。许可与拒绝须按 filter arbitration 在同一受控 sublayer 内验证权重，不能压过其他产品的 block。broker 应从受保护安装路径自行计算应用身份，不信任 Python 客户端单独提交的路径或 SHA；服务 IPC 使用显式 DACL，核验客户端 PID/令牌身份及服务端进程身份。lease/IPC 丢失时关闭浏览器，动态许可撤销，持久默认拒绝留存。
- **失效与动态验收：** WFP dynamic session 结束会清理其动态对象，但必须实测它是否在本机 Windows build 上及时撤销新建和已建立连接；ALE 重授权时序、loopback 精确许可、renderer/utility 进程树身份、BFE 停止/恢复和服务崩溃行为均需验证。验收须包含无 lease 全出站拒绝、有 lease 仅代理端点可连、IPv4/IPv6、TCP/UDP、LAN/loopback、DNS/QUIC、浏览器全子进程和批准代理 HTTPS 的正反探测。
- **安全边界：** Windows WFP 用户态管理 API 是候选实现机制，不能抵抗本机管理员主动停用/篡改策略；不得宣称抵御本机管理员。Linux/macOS 不在首阶段支持范围。不要在日常开发主机安装/试加拒绝规则来替代隔离测试环境。
- **当前阻塞与处置：** 本机没有 MSVC/Windows SDK、.NET SDK、CMake、WiX 或可回滚 VM；仓库仍没有 WFP service、IPC、安装器或卸载/升级事务。此前 UAC 仅用于只读管理员探针，没有修改防火墙/WFP/注册表/网络策略。先取得可构建的 Windows SDK/MSVC 工具链并在专用可回滚 Windows VM/测试机实现、审阅和动态验证；未完成前 Python app 保持 fail closed。
- **状态：** AUD-77 **OPEN**、P2 **NOT PASSED**。现有 `isolation_broker.py` 和拒绝路径只证明无服务时不启动 Chromium。仍需在相同隔离方案下为三条不同获授权视频逐一完成成功端到端捕获；当前唯一链接返回 `CAPTURE_NO_MEDIA` 不计数。参考 Microsoft [WFP overview](https://learn.microsoft.com/en-us/windows/win32/fwp/windows-filtering-platform-start-page)、[ALE layers](https://learn.microsoft.com/en-us/windows/win32/fwp/ale-layers)、[filter arbitration](https://learn.microsoft.com/en-us/windows/win32/fwp/filter-arbitration)、[object management](https://learn.microsoft.com/en-us/windows/win32/fwp/object-management) 与[命名管道安全](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights)。

## 94. 2026-10-10 P2 WFP 绑定可构建性探针与宿主安全边界（令牌状态后由 §95 更新）

- **已推进的工具链工作：** 用户授权代理自主选择和推进 P2 后，从 Microsoft 官方 `dotnet-install.ps1` 将 .NET SDK 10.0.401 安装到当前用户临时目录 `<local user path>`，未写入仓库、系统 PATH 或服务/注册表设置。使用微软 CsWin32 0.3.360 在另一个临时目录建立 API 绑定探针；`NativeMethods.txt` 必须使用 `Windows.Win32.NetworkManagement.WindowsFilteringPlatform.*` 完整命名空间消除 Win32 与 WDK 元数据重名。经命名空间修正，探针构建为 **0 warnings / 0 errors**，生成了 WFP `FwpmEngineOpen0`、`FwpmFilterAdd0`、provider/sublayer/filter/session 等签名与类型。
- **证据边界：** 该探针只证明当前 Win32 metadata 和 CsWin32 能生成可编译绑定；未实现仓库服务、WFP filter builder、命名管道、服务身份锚、安装器或卸载/升级事务。没有调用任何 WFP policy mutation API，也没有更改 Firewall/WFP、注册表或网络设置。生成成功不证明 x64 结构布局、权重/仲裁、loopback、已建立流撤销或运行时行为安全。
- **当前环境：** .NET SDK 已可在临时安装路径运行；本机仍无 MSVC/Windows SDK headers 可用于 `sizeof/offsetof` 对照，也无可回滚的 Windows VM/测试机（硬件虚拟化不可用）。当前登录进程非管理员。不得在日常主机上试装服务或写入默认拒绝过滤器；先完成静态布局交叉核对、服务/IPC/回滚实现与独立代码审查，再在专用可回滚 Windows 环境做动态验收。
- **架构待落实约束：** 管理服务不得直接信任客户端提交的 Chromium 路径、摘要或任意代理端口。部署方案必须把 Chromium 放在普通用户不可写的固定路径，并让服务验证锁定身份；代理许可需绑定到服务持有的监听 socket/受控 handle handoff 或等效受保护代理前端和本次 lease，不能因端口被释放/复用而形成旁路。WFP 候选规则为持久 app-wide hard block 加每 lease 动态精确 loopback/TCP soft permit，放在同一 sublayer 时 permit 权重必须高于 deny，且不得清除其他 provider 的 block action right；原生结构仍需 SDK 头文件布局交叉核对。还须单独评审 ALE_RESOURCE_ASSIGNMENT/raw socket 需要，不能仅凭 ALE_AUTH_CONNECT 正向结果推断覆盖完整。具体服务实现仍需证明 renderer/utility 子进程覆盖、动态许可到期后的既有连接撤销和服务/BFE 故障处理。
- **状态：** 此工具链探针不是 P2 实现或验收。AUD-77 **OPEN**、P2 **NOT PASSED**；仍需完成可审阅服务/安装部署/回滚、隔离环境动态正反向流量测试，以及三条不同获授权视频的成功端到端捕获。

## 95. 2026-10-10 UAC 自助提权与本机管理员探针

- **授权与方法：** 用户明确授权代理自行选择并操作解决方案。当前 Codex 进程原本是中完整性令牌；使用标准 Windows UAC 启动一次隐藏、只读 PowerShell helper，未使用凭据提取、令牌复制或绕过 UAC 的方式。
- **结果：** 提升子进程退出码为 0，`whoami /groups` 显示 `BUILTIN\Administrators` SID `S-1-5-32-544` 已启用，完整性级别为 High。`BFE` 和 `MpsSvc` 均为 Running/Automatic。服务枚举没有发现项目 Douyin/WFP broker；搜索到的 `BrokerInfrastructure`、`IsoEnvBroker` 等 Windows 服务不构成 WFP 策略或项目隔离 broker。
- **系统变更边界：** helper 只查询令牌组和服务列表；未调用 WFP mutation API，未导出或修改过滤器状态，未创建/安装/启动服务，也未修改 Firewall、WFP、注册表或网络策略。高完整性令牌只存在于这次探针子进程，当前 Codex 进程仍为中完整性。
- **效果与下一步：** 不再需要外部管理员主机来执行本机开发阶段，但用户授权和 UAC 提权本身不会实现服务。Windows 11 x64 的项目 WFP service、认证 IPC、受保护 Chromium、lease 代理端点、安装/卸载/升级回滚及动态验收均仍缺失；MSVC/Windows SDK headers 与回滚 VM 也仍不可用。故 AUD-77 **OPEN**、P2 **NOT PASSED**，捕获入口继续 fail-closed。三条真实媒体的统一门槛是各自完成隔离正反探测、标题、媒体获取/解码、ASR、非空 Markdown 和正文隐私检查；`CAPTURE_NO_MEDIA` 不计数。
- **应用健康状态：** 当前锁定命令 `uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript doctor --json` 退出码为 0；`overall=ready`、`local_transcription=ready`、`browser_isolation=unavailable`、`douyin_urls=setup_required`。依赖、模型、路径权限等检查正常不等于 URL 捕获可用；fail-closed 结果是预期状态。

## 96. 2026-10-10 P2 lease 接口收紧与代理 socket 生命周期

- **复核发现：** 旧 Python contract 让客户端预先启动随机端口代理，再把 Chromium path/hash、caller PID 和 proxy port 一起交给 broker。未来服务若把这些请求字段用于 WFP policy，会把身份和端点信任放错一侧；释放应用 listener 后到 WFP lease 撤销前也可能出现端口复用窗口。
- **修正：** `IsolationBroker.acquire()` 改为无参数。正式 transport 必须从已认证 IPC peer 的 OS 信息获取 caller PID/token，由服务选择并返回管理员保护的 Chromium identity、精确 `127.0.0.1` endpoint，以及服务原始 listener 的客户端 socket 副本；服务在 lease 关闭前持有原 socket。应用校验 broker 提供的二进制路径/hash、Playwright 版本和 Chromium revision，代理仅接管 socket 副本。关闭顺序为 browser context、代理副本、lease、Playwright。
- **回归：** 新增真实 loopback socket duplicate 测试，验证 proxy 接管服务 listener 副本、原始 listener 在 proxy 关闭后仍存活、拒绝错误 endpoint 和非 listening socket；新增 capture 集成单元测试，验证 broker 无请求参数且启动使用 broker 返回的 Chromium 和 proxy endpoint。全仓 pytest 在最终小型端口类型/listener 阻塞校验之前为 **515 passed, 23 skipped**（245.26 秒）；这两处最后调整后的目标测试组 **41 passed**（6.61 秒）。Ruff 全仓检查通过，`git diff --check` 无空白错误（Git 仅输出现有 LF→CRLF 提醒）。
- **安全扫描限制：** 本次尝试启动整仓 Codex Security Deep Scan 时，扫描器因父任务未提供 managed filesystem permission profile 而拒绝启动只读 worker；因此没有新的 sealed scan。此工具限制不是用户授权不足，本机测试和手工代码复核也不冒充整仓扫描结果。
- **状态/边界：** 当前 doctor 为 `overall=ready`、`local_transcription=ready`、`browser_isolation=unavailable`、`douyin_urls=setup_required`。这只把应用侧未来服务的 trust contract 收紧，不实现 WFP service、认证 IPC、socket 传输、lease monitor、安装/回滚或系统策略验证；`open_system_broker()` 仍 fail closed。没有执行 UAC、安装服务、调用 WFP mutation API 或修改 Firewall/注册表/网络策略。AUD-77 仍 **OPEN**、P2 **NOT PASSED**；动态隔离和三条真实视频端到端验收仍未完成。

## 97. 2026-10-10 固定 SPDX 2.3 Schema 校验纳入 CI

- **缺口与整改：** 既有 SPDX Schema 验证曾使用临时 `jsonschema` 环境手工执行，CI 单测只对照锁文件/evidence 的 package identity，不持续验证已提交 SBOM 符合正式 Schema。将 SPDX 官方 `support/2.3` 文件固定到 `scripts/schemas/spdx-2.3.schema.json`，文件大小 **47,602 bytes**，SHA-256 `4126dc29f15e92feec92e9622f4939131ad58b125d6f578aa93e980a6e6f3212`。新增 `scripts/check_spdx_schema.py`：验证该 SHA 后使用 Draft 2019-09 validator 检查 SPDX JSON Schema 自身及 `docs/third-party-sbom.spdx.json`；校验器版本 `jsonschema==4.25.1` 锁在独立 `tools/spdx-schema-check/uv.lock`。该校验器是 CI 专用工具，不随应用交付，故有意不纳入应用 SBOM；若 BOM 目标范围扩展到整个仓库/CI 工具链，应另行盘点依赖并审查许可证。本次未改变产品 `uv.lock`、证据清单或 SBOM package 集。CI 先按该工具锁安装隔离环境，再以 `--no-sync`/offline 执行校验。
- **回归结果：** 对实际 SBOM 的官方 Schema 校验通过；测试覆盖当前 SBOM 通过、修改 schema 摘要失败、SBOM 不符合 schema 失败及无效 JSON 失败。SPDX 定向套件 `tests/unit/test_spdx_schema.py`、`test_spdx_sbom.py`、`test_spdx_evidence_verifier.py` 合计 **64 passed, 3 skipped**；3 项跳过是当前 Windows 不提供的 POSIX FIFO 行为。新增 checker 与测试的 Ruff 检查通过。产品依赖与独立 checker 两个 `uv.lock --check` 均通过。
- **边界：** 本次没有运行完整测试套件或远端 Actions matrix。Schema 验证只证明文档结构符合锁定的官方 SPDX Schema，不证明组件枚举完整、制品证据正确、许可适用性或 `licenseConcluded`；P6 与整体发布状态仍 **NOT READY**。

## 98. 2026-10-10 原生 WFP 策略计划工具依赖范围

- `native/windows/wfp-policy-plan/packages.lock.json` 为仅供审阅的策略计划工具锁定构建期依赖：CsWin32 `0.3.360`，以及传递依赖 Win32Docs `0.1.42-alpha`、Win32Metadata `71.0.30-preview` 和 WDK Win32Metadata `0.13.25-experimental`。这些包不随当前应用交付，按现有应用 SBOM 范围不纳入 `docs/third-party-sbom.spdx.json`。
- 当前未对这些 NuGet 包的精确制品、许可证正文或来源/构建 provenance 做独立核验，也未作许可证批准结论。若该原生项目成为随包交付的服务代码，需重新界定 SBOM 范围，并单独盘点、取证和审查这些包及相关原生组件。

## 99. 2026-10-10 P2 非变更 WFP 计划与跨进程 socket 交接

- **原生源码里程碑：** 新增 `native/windows/wfp-policy-plan/`，固定 x64、.NET SDK 10.0.401（`global.json`，允许同 feature band 补丁）和 CsWin32 0.3.360 package lock。工具只生成 semantic policy JSON 与 `Marshal.SizeOf/OffsetOf` managed layout JSON；`NativeMethods.txt` 仅要求 8 个 WFP 类型，没有 WFP/BFE 函数导入、服务入口、安装器或策略写入命令。语义计划明确 `not-deployable`。
- **构建/输出验证：** `dotnet restore --locked-mode` 通过；x64 Release build **0 warnings / 0 errors**；`--plan` 输出含 3 条语义规则，`--layout` 输出 9 个结构且 `NativeSdkComparisonPerformed=false`，二者经 JSON parser 检查通过。managed 结构尺寸不等于 Windows SDK `sizeof/offsetof` 对照，也不证明过滤行为。
- **socket 交接回归：** 新增 `tests/integration/test_windows_socket_handoff.py`，在 Windows 以独立 Python 子进程验证父进程 `socket.share(child_pid)`、子进程 `socket.fromshare()` 后可通过共享 listener 接收；子进程关闭副本后，父进程原 listener 仍工作。定向测试 **1 passed**，Ruff 通过。它只证明 Python 的 Winsock share 路径，不测试 C# `WSADuplicateSocketW` 服务端实现、IPC 身份认证或 WFP lease。
- **浏览器身份核查：** 当前锁定 Playwright Chromium revisions 1234/1243 位于 `%LOCALAPPDATA%\ms-playwright`；目录归当前用户所有并可由其修改。WFP AppID 只按可执行路径匹配，故可写 cache 路径不能作为服务信任锚。安装器必须把浏览器部署到普通用户不可写的固定路径，服务核验该受保护文件的版本/哈希，并控制检查到启动之间的替换竞态。
- **未关闭风险：** 计划工具未构造/安装过滤器。hard block 与精确 lease permit 的权重/action rights 与其他 provider 仲裁、ALE loopback 行为、raw socket/bind/`ALE_RESOURCE_ASSIGNMENT` 覆盖、native SDK layout、跨进程 C# handoff、认证命名管道、heartbeat/服务生命周期、BFE 故障、安装回滚和已建流撤销均未验证。当前主机无可回滚 Windows VM；没有改动 WFP、Firewall、服务、注册表或网络策略，不在日常主机上试加规则。
- **状态：** 此里程碑只为后续服务实现建立可审阅的语义/布局材料。`open_system_broker()` 仍 fail closed，`doctor` 为 `browser_isolation=unavailable`、`douyin_urls=setup_required`；AUD-77 **OPEN**、P2 **NOT PASSED**。仍需 rollback-capable Win11 x64 正负向隔离验收和三条不同授权视频端到端验收，项目整体 **NOT READY**。

## 100. 2026-10-10 平台范围文档与双版本全套复验

- **支持范围文案：** 复核中文/英文 README 后发现“macOS/Linux CI 目标”容易被读成抖音 URL 捕获也受支持。两份 README 现明确：macOS/Linux 仅为 CLI/本地文件转写兼容性目标，未完成跨平台 CI 或实机验证；V1 抖音 URL 捕获范围仅为 Windows 11 x64。没有改变运行时代码或对未验证平台作兼容性承诺。`README.md`、`README_EN.md` 的 Windows 全套结果及 P2 报告引用已同步到本节和当前验收状态。
- **报告格式修正：** P2 报告和本报告把 Chromium cache 路径中的双反斜线改为普通 Windows 路径分隔符，便于核对 `%LOCALAPPDATA%\ms-playwright` 的实际位置。浏览器 cache ACL 结论不变：普通用户可修改的 Playwright 下载目录不能充当 WFP 服务的信任锚。
- **完整回归：** 当前工作树运行 `uv run --project .\skills\douyin-transcript --locked --no-sync --group dev pytest -q`，Windows Python 3.11.15 结果 **520 passed, 23 skipped**（250.28 秒）；使用隔离 Python 3.12.13 同命令复验为 **520 passed, 23 skipped**（342.53 秒）。23 项均要求本机不具备的 POSIX FIFO、symlink、ownership、mode-bit 或目录句柄行为；它们不是 macOS/Linux 通过证据。
- **发布检查：** 全仓 Ruff、产品 `uv.lock --check`、独立 `tools/spdx-schema-check/uv.lock --check`、`scripts/check_sensitive_files.py` 和离线 SPDX 2.3 schema checker 均通过；`git diff --check` 通过，仅有既有 LF→CRLF 工作树提醒。未运行远端 CI 或 macOS/Linux 实机验收。
- **P2/系统状态：** 本轮只复核和更新代码/文档，没有启动管理员策略变更、安装服务、修改 Firewall/WFP、注册表或网络配置。P2 source 仍只有不写系统策略的语义计划/managed-layout 工具；没有 WFP service、IPC、installer、rollback 或动态过滤器验证。浏览器 URL 捕获保持 fail-closed；唯一授权链接 `CAPTURE_NO_MEDIA` 不计成功，三条不同授权视频及隔离正反测试仍须完成。
- **状态：** 本次回归没有发现新的 Python 测试失败，修正了平台支持范围的文档歧义。它不能关闭 P2/AUD-77、P4 长样本与人工听审、P5 新 Desktop Agent 调用、P6 所有者许可证/分发决定、跨平台 CI 或正式安全扫描门槛；项目整体继续 **NOT READY**。

## 101. 2026-10-10 管理员能力与回滚环境只读复核

- **当前权限：** 当前 Codex shell 仍为普通用户和 Medium Integrity；Administrators 组在此令牌中为 deny-only。用户已授权自主选择和推进 P2 方案，但授权没有改变当前进程令牌。
- **只读 UAC 探针（启用前快照）：** 使用标准 UAC 启动仅查询 Windows 状态的子进程。Windows 11 Enterprise LTSC build 26100 上 `BFE` 与 `MpsSvc` 为 Running/Automatic；`HypervisorPresent=True`。当时 Windows Sandbox、Hyper-V、Virtual Machine Platform 与 WSL 可选功能均为 Disabled；没有 VMMS 服务、Windows Sandbox 可执行文件或 Hyper-V PowerShell 模块。Sandbox 后续启用/重启及当前 WFP guest 探针见 §103–104。hypervisor 正在运行不等于已配置可用的 WFP 测试 VM。
- **构建工具：** 临时目录中的 .NET SDK 10.0.401 可用；当前进程 PATH 没有 SDK、MSVC/Visual Studio 与 Windows SDK headers 也未安装。没有改动任何 Windows 可选功能、服务、Firewall/WFP、注册表、驱动或网络设置。
- **安全扫描边界：** §96 记录的 Codex Security Deep Scan worker 因父任务缺少 managed filesystem permission profile 而未启动。没有 sealed scan 或新的安全扫描覆盖；这不是“无发现”，也不是权限授权不足。正式扫描门槛仍开放。
- **状态与下一步：** 当前本机不能安全完成 WFP 运行时验收。要继续系统级隔离验证，需要先准备可丢弃/可回滚的 Windows 11 x64 测试环境，再在其中补齐 Windows SDK/MSVC、实现并审阅服务/installer/rollback，最后做系统动态正反向流量测试；不得在日常主机安装拒绝规则。P2/AUD-77 仍 **OPEN/NOT PASSED**，项目整体仍 **NOT READY**。

## 102. 2026-10-10 WFP 精确例外计划的逻辑拆分

- **复核：** 旧语义计划将“目标不是 TCP `127.0.0.1:<lease-port>`”作为单个 `destination != tuple` 条件。但普通 WFP filter 的条件以 AND 组合；不同协议、地址或端口的并集不能由该单条抽象条件表示。
- **计划修正：** 语义预览现明确使用同一专用 sublayer 中的更高权重精确 TCP/IPv4 loopback/lease-port permit，并把 IPv4 默认拒绝拆成三个各自按浏览器 AppID 匹配的 block：protocol 不等于 TCP、remote address 不等于 `127.0.0.1`、remote port 不等于当前 lease port。任一不匹配时命中 block；全部匹配时先命中精确 permit。IPv6 仍为 AppID 级默认 block。预览和样例 JSON 的 `Deployability` 均保持 `not-deployable`。
- **待验证项：** WFP 的 `FWP_MATCH_NOT_EQUAL` 只支持 sortable 类型；remote IPv4 address 需要以 sortable `FWP_UINT32` 表示，且要确认地址字节序及 `ALE_AUTH_CONNECT_V4` 接受该条件。还未构造原生过滤器，也未测试同一 sublayer 权重、其他 provider 的 block/硬 permit、loopback 或运行时连接结果。
- **构建验证：** 使用临时 .NET SDK 10.0.401 对策略计划工具做 x64 Release build，结果 **0 warnings / 0 errors**。此项只校验 C# 计划生成器可编译，不验证 WFP native API 或操作系统隔离。
- **官方语义依据：** Microsoft 文档说明 `FWPM_FILTER0.filterCondition` 中所有条件均须成立，并说明匹配层/子层的权重仲裁；`FWP_MATCH_NOT_EQUAL` 仅支持 sortable 数据类型。参考 [FWPM_FILTER0](https://learn.microsoft.com/en-us/windows/win32/api/fwpmtypes/ns-fwpmtypes-fwpm_filter0)、[Filter Arbitration](https://learn.microsoft.com/en-us/windows/win32/fwp/filter-arbitration)、[FWP_MATCH_TYPE](https://learn.microsoft.com/en-us/windows/win32/api/fwptypes/ne-fwptypes-fwp_match_type)。
- **状态：** 这是对策略描述可表达性的修正，不实现 service、IPC、installer、rollback 或 WFP 写入，也不能证明隔离。AUD-77 **OPEN**、P2 **NOT PASSED**、项目整体 **NOT READY**。

## 103. 2026-10-10 Windows Sandbox 准备请求

- **目的：** 用户授权自主选择并操作后，选择 Windows Sandbox 作为隔离的、可丢弃的 Win11 x64 WFP 测试 VM。Sandbox 功能此前为 Disabled；当前 Windows build/Enterprise edition 对应的可选功能已在管理员只读探针中确认。
- **执行：** 通过标准 UAC 运行 `Enable-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM -All -NoRestart`。Windows 返回 `RestartNeeded=true`。后续已安排并完成一次正常宿主重启；重启后 Sandbox 可启动，具体能力探针见 §104。
- **边界：** 没有在宿主写入任何 WFP 过滤器，没改 Firewall、服务、驱动或网络策略。功能启用和重启只完成了 Sandbox 客户端准备，不等于 WFP 管理 API 在 Sandbox 中可用。
- **状态：** §103 是准备操作记录，运行时能力结论由 §104 更新。P2/AUD-77 仍 **OPEN/NOT PASSED**，项目整体仍 **NOT READY**。

## 104. 2026-10-10 Sandbox 与宿主 WFP 只读能力探针

- **环境与隔离：** Windows 11 Enterprise LTSC build 26100 重启后可启动 Windows Sandbox。使用 `.wsb` 关闭 guest 网络、剪贴板和打印机重定向；脚本目录只读挂载，单独结果目录可写。第一次配置误用了无效的 `<FolderName>` 元素，未产生报告；依据 Microsoft 配置格式改为 `<SandboxFolder>` 后重新启动并成功生成结果。宿主 Sandbox API 每次只允许一个活动实例，按本轮启动 ID 执行 `wsb stop` 结束了空白初始实例后重试。
- **guest 身份与服务：** 默认 `WDAGUtilityAccount` 和 `wsb exec --run-as System` 两种上下文均在 guest 中报告管理员组成员为 true；BFE 为 `Running`，OS 版本为 `10.0.26100.0`，进程架构为 x64。报告不保留主机名或账户名。
- **WFP API 结果：** 修正后的 P/Invoke 将可选 `serverName` 显式传为原生空指针 `IntPtr.Zero`。默认 guest 与 `wsb exec --run-as System` 两种上下文中，`RPC_C_AUTHN_WINNT`（10）均打开成功；`FwpmFilterCreateEnumHandle0`、`FwpmFilterEnum0` 均返回 0，并各枚举到 1 个请求项。`RPC_C_AUTHN_DEFAULT`（0）在两种上下文返回 Win32 50（`ERROR_NOT_SUPPORTED`）。此前使用托管 `string` 参数的失败结果已被这次复测取代；因为未在同一上下文做严格 A/B，不能断言旧失败只由字符串封送导致。另以 guest SYSTEM 运行 `netsh wfp show state` 成功，生成 1,598,830 字节状态 XML。Win32 50 的含义见 Microsoft [系统错误码](https://learn.microsoft.com/en-us/windows/win32/debug/system-error-codes--0-499-)。
- **系统状态边界：** 探针只调用 `FwpmEngineOpen0`、过滤器枚举、关闭/释放 API；没有调用 `FwpmFilterAdd*`、服务控制或 Firewall 配置 API，也没有修改 WFP、Firewall、注册表、服务、驱动或网络策略。`netsh` 只导出状态。当前 Codex shell 仍为普通令牌；另一项 host elevated WFP 只读对照已请求标准 UAC，但提示仍待交互确认，未取得结果，不能记作成功。
- **宿主普通令牌对照：** 当前非管理员 PowerShell 进程上，认证服务 10 打开 engine 返回 0，但创建 filter enum handle 返回 5（access denied）；认证服务 0 打开返回 50。该结果只覆盖普通用户只读访问，不能代替高完整性管理员对照。高完整性探针已请求标准 UAC，但提示仍待桌面交互确认。
- **结论与后续：** 本节的 `ReadOnlyWfpSmoke.wsb` 关闭网络，只证明 guest 可用认证服务 10 执行 WFP 管理 API 的只读打开和枚举；宿主普通令牌可打开 engine，但无权枚举。后续 network-enabled disposable smoke 的有限动态结果先见 §105，后续 PowerShell AppID scoped 规则 smoke 见 §106。高完整性 host 对照只用于额外权限比较，不是继续 P2 的前提。不要在日常宿主试写默认拒绝规则。AUD-77 **OPEN**、P2 **NOT PASSED**、项目整体 **NOT READY**。
- **官方依据：** Microsoft 的 `.wsb` 配置文档规定 `SandboxFolder`、说明共享目录权限与 LogonCommand 顺序；WFP API 文档列明 `FwpmEngineOpen0` 支持认证服务 10 和 0。[Windows Sandbox 配置](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-configure-using-wsb-file)、[FwpmEngineOpen0](https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmengineopen0)。

## 105. 2026-10-10 一次性 Sandbox 动态 WFP block/release smoke

- **隔离配置：** 新增 `sandbox/NetworkWfpSmoke.wsb`，guest 网络启用，脚本只读挂载、结果目录可写挂载，并关闭剪贴板/打印机重定向。用 `wsb exec --run-as System` 在一次性 Windows Sandbox guest 执行；测试结束后已停止该 Sandbox。此次没有在宿主增加过滤器、修改防火墙/网络设置或安装服务。
- **安全前置条件：** helper 先核对其 x64 `FWPM_SESSION0`、`FWPM_SUBLAYER0`、`FWPM_FILTER0` `Marshal.SizeOf` 分别为 72/72/200，再尝试 TCP 基线连接。`1.1.1.1:443` 与 `8.8.8.8:443` 不通，用户授权的 `www.douyin.com:443` TCP 握手成功；仅在基线成功后才进入写入步骤。该结构检查与既有 CsWin32 managed layout 数值一致，但仍不是 Windows SDK 原生头文件编译得到的 `sizeof/offsetof` 对照。
- **动态结果：** 以 `RPC_C_AUTHN_WINNT`（10）打开 `FWPM_SESSION_FLAG_DYNAMIC` session 成功（0）；临时高权重 sublayer 添加成功（0）；在 `FWPM_LAYER_ALE_AUTH_CONNECT_V4` 添加无条件 `FWP_ACTION_BLOCK` filter 成功（0）。新 TCP 连接在 filter 生效时失败；`FwpmEngineClose0` 返回 0 后，新的 TCP 握手成功。脚本只执行这一种 guest 级 all-app IPv4 ALE connect block，filter/sublayer 属于 dynamic session，未设为 persistent。Microsoft 说明该层处理 outbound TCP connect，且 dynamic-session 对象会在 session close 或进程终止时删除；见 [ALE layers](https://learn.microsoft.com/en-us/windows/win32/fwp/ale-layers)、[object management](https://learn.microsoft.com/en-us/windows/win32/fwp/object-management)、[FwpmFilterAdd0](https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmfilteradd0)。
- **证据边界/下一步：** 这验证了当前 guest build 上的 API 写入、基础 IPv4 TCP 阻断和 session close 后放行；没有验证目标 Chromium AppID、代理精确 permit、同 sublayer 的 hard-block/soft-permit 仲裁、其他 provider、IPv6、UDP/QUIC、raw socket、loopback、进程树、BFE/服务崩溃、安装/升级/卸载或 rollback。也没有运行真实 Chromium 捕获。可继续用 disposable Sandbox 测 service primitives，但生产策略仍需完整动态正反向验收。P2/AUD-77 **OPEN/NOT PASSED**。

## 106. 2026-10-10 WFP 条件/动作/权重构造预览

- **实现：** `native/windows/wfp-policy-plan/` 新增 `--filter-plan`，输出五条规则的 `FWPM_CONDITION_*` GUID、`FWP_MATCH_*` 类型、条件数据类型和值、action、flags、持久性和过滤器权重。规则包括一个绑定应用身份、TCP、`127.0.0.1` 和示例 lease port 的动态软 permit；三个 IPv4 mismatch deny；以及一个 IPv6 默认 deny。AppID 标明必须由服务从受保护浏览器路径取得；示例路径、端口、filter key 和 sublayer key 均不是可部署值。
- **真实验收发现与修复：** 第一次 scoped Sandbox 写入因 lease permit 用了 `FWP_UINT8=255` 收到 `FWP_E_INVALID_WEIGHT`（`0x80320025`），没有添加过滤器，dynamic session 正常关闭。查对 Microsoft `FWPM_FILTER0.weight` 规范后发现 `FWP_UINT8` 是 **0–15 的权重区间索引**；现将 exact permit 设为 15、deny 设为 1，并在代码校验中拒绝超范围值。Microsoft 说明高区间拥有更高优先级，`FWP_UINT64` 才是直接提供值；见 [FWPM_FILTER0.weight](https://learn.microsoft.com/en-us/windows/win32/api/fwpmtypes/ns-fwpmtypes-fwpm_filter0)。
- **动作权语义：** exact endpoint permit 保持 soft，不设置 `FWPM_FILTER_FLAG_CLEAR_ACTION_RIGHT`；WFP 缺省 filter permit 是 soft permit，filter block 是 hard block，且跨子层 arbitration 的 block 会优先于 permit。预览对例外使用 `Flags=0`，持久拒绝过滤器只加 `FWPM_FILTER_FLAG_PERSISTENT`。这仍不能替代外部 provider 仲裁实测。[Filter Arbitration](https://learn.microsoft.com/en-us/windows/win32/fwp/filter-arbitration)、[FWPM_FILTER0](https://learn.microsoft.com/en-us/windows/win32/api/fwpmtypes/ns-fwpmtypes-fwpm_filter0)。
- **Sandbox 结果：** 新增 `sandbox/ScopedNetworkWfpSmoke.ps1`，仅在 network-enabled disposable Windows Sandbox 的 SYSTEM 进程中运行。脚本先确认 x64 结构尺寸为 session/sublayer/filter/condition/value **72/72/200/40/16**，并要求精确 loopback TCP、错误端口 loopback TCP、外部 IPv4 TCP、loopback UDP 接收、IPv6 loopback TCP 和独立 `curl.exe` HTTPS 均有正向基线；基线有任何缺项就不写 WFP。第二次运行中，AppID 获取、engine open、sublayer add 和五个 filter add 都返回 0。生效期间精确 `127.0.0.1:43127/TCP` 成功，另一个本机端口、外部 IPv4、UDP、IPv6 均阻断，独立 `curl.exe` HTTPS 成功。关闭 dynamic session 后所有基线流恢复，结果为 `pass`；Sandbox 随后已停止。结果保存在忽略的 `sandbox-results/wfp-scoped-policy-smoke.json`。
- **构建与安全边界：** .NET 10.0.401 x64 Release build 为 **0 warnings / 0 errors**；`--filter-plan` JSON 的五条规则、权重范围、动作 flags、placeholder keys 经 PowerShell parser 核验。Sandbox helper 的 PowerShell 语法和 C# ABI 声明通过解析/编译，结构尺寸与现有 managed CsWin32 数据一致。过滤器都由 dynamic session 管理，仅匹配 guest 的 `powershell.exe` AppID；没有创建 persistent filter，也没有修改宿主机 Firewall/WFP、服务、注册表或网络策略。`FWPM_FILTER0` native SDK `sizeof/offsetof` 仍无对照。
- **证据边界：** 这验证了当前 Sandbox build 上五条 WFP 规则的基础条件/值/动态生命周期和一个非目标应用正向路径，不是 Chromium AppID、受保护浏览器路径、服务持久 deny、外部 sublayer/provider arbitration、硬许可冲突、BFE/服务崩溃、资源分配/raw socket、安装回滚或真实抖音捕获验收；也没有验证 across servicing levels。工具仍不构造或提交原生 `FWPM_FILTER0`，不提供 service/IPC/installer，不能证明生产隔离。
- **状态：** AUD-77 **OPEN**、P2 **NOT PASSED**；三条不同获授权视频成功捕获仍未完成。P4/P5/P6 的人工听审、长样本、新 Desktop 会话、许可证所有者决定和远端 CI 等开放项不变，项目整体仍 **NOT READY**。

## 107. 2026-10-10 WFP 预览精确自校验与验收文档对齐

- **复核发现：** 独立只读代码审阅发现 `NativeFilterPlan.Validate()` 先前仅检查条件字段种类、数据类型和总体规则数，未逐条确认 rule ID 对应的 layer/GUID、action、flags、weight、operator、具体常量值与字段 GUID。未来将 TCP/地址/端口常量改错时，预览有可能仍通过自校验。
- **本地修复：** 校验器现在逐条对比五条规则的完整预期：精确代理 permit 必须是动态 soft permit，绑定 TCP=6、host-order `127.0.0.1` 与示例端口 43127；三个持久 IPv4 block 分别拒绝非 TCP、非 loopback 地址和非 lease 端口；IPv6 block 只匹配受保护 AppID。各条件同时核对 `FWPM_CONDITION_*` GUID、`FWP_MATCH_*` 类型、数值类型和值、value source 与说明字段；filter key/sublayer placeholder 和权重/action/lifetime 也需完全匹配。
- **核验：** 使用锁定的临时 .NET SDK 10.0.401 执行 x64 Release `build --no-restore`，0 warnings / 0 errors；随后运行 `--filter-plan` 并用 PowerShell 解析 JSON，确认恰有五条规则且 `deployability=not-deployable`。本轮没有运行完整 pytest、没有重新运行 Sandbox smoke；该编译与预览验证只覆盖构造器自校验和输出，不覆盖系统运行时行为。`git diff --check` 通过，仅有工作区既有 LF→CRLF 提示。
- **P1 证据台账：** 元数据检查确认私有 output 目录当前有 4,656、4,658、4,689、4,878 和 5,764 bytes 五个 Markdown 文件。P1 报告已说明 4,656/4,658 为成功转写，4,878 为术语词典 rerun 的原稿、5,764 为默认 Agent 模型校对稿；4,689-byte 文件来源未识别。没有读取任何正文，没有删除/改写私有文件，也不将未识别文件计入验收。BENCHMARK 与 ACCEPTANCE 已同步 4,878/5,764 的未计时复核信息，并标注 4,689-byte 文件的证据限制。
- **文档对齐：** 更新 P2 architecture/owner 状态，注明 §106 的 PowerShell-only scoped smoke；P2 汇总指向 §§104–106，P5 新 Desktop 会话与 P6 远端 CI 拆分；当时 Release Report 区分全套测试快照 §100（两版本各 520 passed / 23 skipped）与审计记录 §107，并准确说明 Sandbox guest 临时规则已创建/清理、宿主策略未改。§92/§100 保留为历史结果；当前树全套结果见 §§128–129。
- **边界/状态：** 本变更不构造或提交 native `FWPM_FILTER0`，不含 service/IPC/installer，不验证 Chromium、外部 provider arbitration、持久默认拒绝、服务/BFE 故障、安装回滚或真实视频捕获。P2/AUD-77 仍 **OPEN/NOT PASSED**；P4/P5/P6 仍依赖真实听审/长样本、新 Desktop 会话、所有者决定和远端验收，项目整体仍 **NOT READY**。

## 108. 2026-10-10 管理员启动受限与精确校验负向检查

- **用户授权与权限边界：** 用户授权代理自行寻找并操作解决方案。当前 Codex shell 的 Administrators 组仍为 deny-only。尝试通过标准 `Start-Process -Verb RunAs` 启动一个只读取当前身份和 BFE 状态的诊断 helper，但执行器自动审批策略在启动前以 `blocked by policy` 拒绝该命令；没有创建子进程，也没有系统变更。§95 记录的历史只读 UAC helper 结果不等于当前存在可复用的高完整性进程或本轮 UAC 启动已获准。此前一次性 Sandbox guest 已停止，当前 `wsb list --raw` 返回空环境列表。
- **自校验负向检查：** 在临时 PowerShell 反射 harness 中，将内存中的第一条 permit 规则之 `FWPM_CONDITION_IP_PROTOCOL` 值从 `6` 改为 `17`，再调用 `NativeFilterPlan.Validate()`；校验器以“rule does not match its exact expected …”拒绝该计划。该检查未修改项目文件、WFP 或网络策略；harness 未加入持续集成，因此记录为本机一次性负向检查。
- **当前结论：** C# 精确构造校验器的正向构建/预览证据仍见 §107，本节增加一个错误常量被拒绝的负向样例。当前没有可用的管理员 shell 或运行中的隔离 guest；不能据此安装服务或继续 host WFP 操作。管理员 service、IPC、受保护 Chromium、安装/回滚和 Chromium 运行时动态验收仍未实现，P2/AUD-77 **OPEN/NOT PASSED**；P4/P5/P6 与整体 **NOT READY** 状态不变。

## 109. 2026-10-10 预览驱动的 Sandbox WFP 复验与当前树回归

- **策略来源收敛：** 从 .NET 10.0.401 x64 Release 工具的 `--filter-plan` 输出生成 `native/windows/wfp-policy-plan/artifacts/native-filter-plan.example.json`，SHA-256 为 `51bf789b93e250a431b4c0ca756b4b86ad69d0a161a02bb561fd51a2a6553f0d`。`NetworkWfpSmoke.wsb` 将 artifacts 目录只读映射到 guest。`ScopedNetworkWfpSmoke.ps1` 在任何策略写入前检查该 SHA、计划类型、不可部署标记及五条有序 rule ID；之后逐条读取计划中的 layer GUID、action、weight、condition GUID、match type、value type 与值来构造测试过滤器，删除了脚本内原先重复的规则 GUID、条件值、动作和权重硬编码。Sandbox 结果现在包含被校验计划的摘要和规则 ID。
- **动态验证：** 在一次性 Windows Sandbox 中以 SYSTEM 运行脚本。计划验证成功；x64 managed structure sizes 为 72/72/200/40/16；所有先决正向基线通过；五条 filter add 均返回 0。精确 loopback TCP 成功，错误端口、外部 IPv4、loopback UDP 与 IPv6 被阻断，独立 `curl.exe` HTTPS 成功。关闭 dynamic session 后各基线流恢复，结果 JSON `status=pass`，filter plan SHA 与仓库 artifact 相同。Sandbox 已停止，`wsb list --raw` 为空。宿主 WFP/Firewall 未写入或改动。
- **回归：** `uv run --project .\skills\douyin-transcript --locked --no-sync --group dev pytest -q`：Windows Python 3.11.15 **520 passed, 23 skipped**（249.23 秒）；23 项因当前 Windows 不支持 POSIX FIFO、symlink、ownership、mode-bit 或目录句柄行为而跳过。全仓 Ruff 通过。策略工具 x64 Release build 为 0 warnings / 0 errors；PowerShell parser 与嵌入的 C# source 解析/编译通过。
- **边界/状态：** 该 smoke 仍把所有 deny 过滤器放进 disposable guest 的 dynamic session；它没有验证持久默认拒绝、真实原生 Windows SDK `sizeof/offsetof`、Chromium AppID、受保护浏览器路径、生产 service/IPC/installer/rollback、外部 provider 仲裁、已有流撤销、raw-socket/resource-assignment 或真实抖音捕获。计划 JSON 是被 pin 的构造样例，C# 主程序仍不分配/提交生产 `FWPM_FILTER0`。当前提权尝试仍被执行器策略阻止。P2/AUD-77 **OPEN/NOT PASSED**；P4/P5/P6 和跨平台/远端验收未关闭，整体 **NOT READY**。

## 110. 2026-10-10 Sandbox 外网探测归因与逐规则白名单

- **独立复核发现：** 只读复核指出 §109 的 `TryConnectTcpHostV4` 在每次探测时都会重新解析 `www.douyin.com`，且把 DNS 失败和连接失败都合并成 `false`。因此过滤期 DNS 或短暂网络异常也可能被记为外网被 WFP 阻断。复核还指出 Sandbox 只检查 JSON SHA、元数据和规则 ID，没有独立逐条核对每个字段 GUID、match、value type 与规则的预期关系。
- **探测器修正：** 现在先解析一次目标域名，尝试数值 IPv4 候选直到找到一个基线可连接的地址，并将该数值地址记入结果 JSON；基线、过滤生效期和 dynamic session 关闭后的 TCP 探测均直连同一地址。这样过滤期不再发生 DNS 重查。它降低 DNS 误归因，但单次过滤期连接失败仍可能受瞬态链路异常影响，结果应与过滤前后同地址成功及 WFP 调用记录一并解释。
- **规则校验修正：** 新增独立 PowerShell allowlist，逐条核对五条规则的顺序、layer/GUID、action/value、flags、persistence、clear-action-right、weight/type、placeholder key，以及条件数量、字段/GUID、match/operator、value type、值和 source。lease port 同时须为安全范围内的十进制字符串，且与规则及顶层 endpoint 一致。当前固定 SHA 仍用于确认 guest 读取的是已审 artifact；allowlist 负责独立校验其语义。只读 `.wsb` 映射不变。
- **负向与动态验证：** 在宿主 PowerShell 中解析脚本并校验原始 JSON，成功得到示例端口 `43127`；随后仅在内存中篡改 remote-address condition GUID，allowlist 按预期拒绝。重新启动 disposable Windows Sandbox，在 guest SYSTEM 下运行 scoped smoke：allowlist 与 hash 均通过，固定数值地址为 `113.96.140.56`，x64 layout 为 72/72/200/40/16，五条 filter add 均返回 0，exact loopback/TCP permit、wrong-port/address/protocol block、loopback UDP 和 IPv6 loopback block、独立 `curl.exe` HTTPS、同一 IPv4 地址过滤期失败及关闭后恢复均通过，最终 `status=pass`。Sandbox 已停止且 `wsb list --raw` 为空；没有更改宿主 WFP/Firewall。仅测试 `::1` loopback，不代表公网 IPv6 验证。
- **权限与状态：** 用户已再次授权代理自主操作；但标准 `Start-Process -Verb RunAs` 的只读 helper 仍在启动前被执行器策略 `blocked by policy` 拒绝，当前 Codex 进程没有管理员令牌。通过 `wsb exec --run-as System` 在可丢弃 guest 内获得的 SYSTEM 能力只支持隔离验收，不会提升宿主权限。未安装宿主 service 或写入宿主策略。生产 WFP service/IPC/installer/rollback、Chromium 身份、持久默认拒绝、外部 provider 仲裁和三条真实捕获仍未实现；P2/AUD-77 **OPEN/NOT PASSED**，项目整体仍 **NOT READY**。

## 111. 2026-10-10 P2 lease 级 Chromium 身份边界复核

- **发现：** 独立只读安全调查检查了 Python broker contract、capture gate、WFP 预览与 P2 决策。`FWPM_CONDITION_ALE_APP_ID` 依规范化可执行文件路径匹配，不是 PID 或 lease 标识。当前候选方案中的受保护 Chromium 固定路径只能区分其他安装路径；若两个进程/捕获使用同一路径，它们会匹配同一 AppID 过滤器。因此，未来只按固定 Chromium AppID 添加的 lease permit 不能单独证明“只有本次捕获进程树可连接代理”。
- **候选对策：** 评估每个 lease 分配独有 AppContainer package SID，并让 ALE IPv4/IPv6 connect policy 同时匹配 `FWPM_CONDITION_ALE_PACKAGE_ID`。Microsoft 文档确认 ALE auth-connect 层可使用此条件，值为 AppContainer package SID；不过 Chromium/Playwright 在 AppContainer 下启动、browser/network/renderer/utility token 覆盖、loopback 代理可达性、所需 network capability/loopback exemption 及 lease 失败后的持久 deny 都未验证。应用侧无 broker 仍 fail closed。
- **文档修正：** `P2_ISOLATION_DECISION.md` 和 `P2_REPORT.md` 现把路径 AppID 与 lease 进程身份区分开，新增按 lease 身份绑定的 Sandbox 原型门槛。在原型通过前，不实现或宣称 lease 级 WFP 隔离；该候选方案尚未选定。
- **来源：** Microsoft [ALE application identity](https://learn.microsoft.com/en-us/windows/win32/fwp/application-layer-enforcement--ale-)、[ALE filtering conditions](https://learn.microsoft.com/en-us/windows/win32/fwp/filtering-conditions-available-at-each-filtering-layer)、[AppContainer launch and capabilities](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)、[AppContainer loopback/IPC](https://learn.microsoft.com/en-us/windows/apps/develop/communication/interprocess-communication)。
- **范围与状态：** 本节仅记录设计发现与验收门槛；没有添加 named-pipe/service/WFP mutation API，没有启动 Chromium AppContainer 原型，也没有更改 Sandbox/host 网络策略。§110 的 PowerShell AppID smoke 不覆盖该身份边界。AUD-77 **OPEN**、P2 **NOT PASSED**，项目整体 **NOT READY**。

## 112. 2026-10-11 AppContainer lease SID 与 WFP package-ID Sandbox 原型

- **授权与边界：** 用户授权代理自行寻找可行路径。当前 Codex 工作进程仍是普通令牌；没有依赖该授权尝试宿主提权。使用 `wsb start` 创建 network-enabled disposable Windows Sandbox，再经 `wsb exec --run-as System` 在 guest 内运行。脚本目录只读挂载，结果目录可写挂载。每轮结束都执行 `wsb stop`，最后 `wsb list --raw` 为空。没有在宿主写入 WFP/Firewall、服务、注册表或网络设置。
- **身份与 loopback 前置检查：** guest SYSTEM 创建两个独立 AppContainer profile，得到不同 package SID。通过 `PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES` 启动系统 `curl.exe` 后，读取子进程 token package SID 并与对应 profile 对比。没有 exemption 时 loopback listener 没收到连接，curl 退出码为 28（连接超时）；为第一个 profile 添加 `CheckNetIsolation LoopbackExempt` 后，该命令返回 0，listener 收到连接。curl 随后也返回 28，因为测试 listener 故意不提供 HTTP 响应；这里以 listener 是否 accept 作为 TCP 建立证据。删除 exemption 返回 0。
- **WFP package-SID 验证：** 两个 profile 在 filter 前用同一 `curl.exe` 对固定域名/同一数值 IPv4 `121.12.111.50` 发起 HTTPS 请求，退出码均为 0。guest SYSTEM 打开 dynamic WFP session、添加临时 sublayer，再添加一条 `FWPM_LAYER_ALE_AUTH_CONNECT_V4` hard block filter，条件为 `FWPM_CONDITION_ALE_PACKAGE_ID` / `FWP_SID`，值为第一个 profile SID。engine open、sublayer add、filter add 和 engine close 均返回 0，filter ID 为 `69110`。过滤期间第一个 profile curl 连接失败（exit 7），第二个 profile 用同一路径仍成功（exit 0）。关闭 dynamic session 后第一个 profile 恢复（exit 0）。最终 `status=pass`；单独保留的 WFP pass JSON 位于忽略文件 `native/windows/wfp-policy-plan/sandbox-results/appcontainer-package-id-wfp-pass.json`。
- **Interop 与测试迭代：** PowerShell parser 和 embedded C# 编译通过。managed x64 session/sublayer/filter/condition/value/SID-value sizes 为 `72/72/200/40/16/16`，相关 offset 为 `8/24/120/128/152/184`；这只是代码内布局自检，没有同 Windows SDK 原生 `sizeof/offsetof` 对照。第一次用 PowerShell child 得到 `STATUS_DLL_INIT_FAILED`，因此该结果没有作为网络策略判据；探针改为 native `curl.exe`。一次后续运行因 `[ulong]` PowerShell 类型名无效在 filter 构造前失败，filter add 未发生且 engine close 返回 0；修正为 `[UInt64]` 后完成最终正负向运行。
- **结论与剩余边界：** 这验证当前 Sandbox build 上 AppContainer SID 可作为两个相同 executable path 进程的区分条件，`ALE_PACKAGE_ID` 单条动态 IPv4 filter 的匹配与 cleanup 有效；它支持继续推进该候选方案，不代表完整 lease/browser isolation。未启动 Chromium/Playwright，也没有测 browser/network/renderer/utility 子进程身份、代理 socket/精确 loopback 许可、IPv6/UDP/QUIC deny、持久 default deny、其他 provider 仲裁、raw socket/resource assignment、服务/BFE 故障、IPC、installer/rollback 或真实抖音捕获。Microsoft 文档将 ALE auth-connect 的 `ALE_PACKAGE_ID` 说明为 AppContainer SID，条件值类型为 `FWP_SID`：[过滤条件按 layer](https://learn.microsoft.com/en-us/windows/win32/fwp/filtering-conditions-available-at-each-filtering-layer)、[条件值类型](https://learn.microsoft.com/en-us/windows-hardware/drivers/network/filtering-condition-data-types)、[V4 ALE package SID field](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/fwpsu/ne-fwps_fields_ale_auth_connect_v4)。应用无 broker 时仍 fail closed；AUD-77 **OPEN**、P2 **NOT PASSED**，P4/P5/P6 未关闭，整体 **NOT READY**。

## 113. 2026-10-11 Playwright Chromium AppContainer 启动对照

- **执行范围：** 用户授权代理自主寻找方案后，继续使用一次性、联网的 Windows Sandbox。主机 Playwright Chromium 1243 目录以只读方式映射，脚本和结果目录分别只读/可写映射；为排除共享目录读取问题，Chromium 目录的 308 个文件复制到 guest 临时目录，并给一次性 AppContainer SID `ReadAndExecute` 权限，独立 guest 临时用户数据目录只授予该 SID 写权限。测试完成后停止 Sandbox，`wsb list --raw` 为空。没有在宿主安装服务、启动提权命令或修改 WFP/Firewall、注册表和网络策略。
- **启动上下文对照：** `ExistingLogin` 探测返回 `0x80070520`（Sandbox 内没有活动登录会话）。guest SYSTEM 在 AppContainer 外启动同一 `chrome.exe --version`，进程在 10 秒内正常退出、exit code `0`。这只证明该二进制在该 guest SYSTEM 上下文可执行，不证明网页渲染或 Playwright 启动。
- **AppContainer 结果：** `CreateProcess` 成功，子进程 package SID 与独立 profile SID 相同；普通 `--version` 返回 `-2147483645`（`0x80000003`，`STATUS_BREAKPOINT`）。添加 `--no-sandbox` 后的 `--version` 仍返回同一状态。因为这两个版本探针均未成功，后续 headless `about:blank` 命令没有执行；没有测到 Chromium browser/network/renderer/utility 全进程树或代理网络策略。把文件本地暂存和授予显式 ACL 没有改变失败，故“主机共享目录读取限制”不是已验证的解释；根因尚未查明。`--no-sandbox` 仅作诊断尝试，不是可接受的产品设置。
- **同轮 WFP 复验：** AppContainer/curl 子流程仍按预期通过：两 profile 的 HTTPS 基线成功；临时 `ALE_PACKAGE_ID` block 添加返回 `0`（filter ID `69145`），目标 profile curl 返回 `7`、第二 profile 返回 `0`，关闭 session 后目标恢复为 `0`。这与 Chromium 启动探针分开解释；本轮总脚本因 Chromium 失败报告 `status=fail`。最新综合结果在忽略的 `native/windows/wfp-policy-plan/sandbox-results/appcontainer-identity-smoke.json`；独立 SYSTEM 对照在 `chromium-system-baseline.json`。此前单独 WFP pass 的留存结果为 `appcontainer-package-id-wfp-pass.json`。
- **对策与结论：** 本节中的 `STATUS_BREAKPOINT` 仅来自 guest SYSTEM 父进程创建的 AppContainer 子进程；由于 `ExistingLogin` 会话不可用且 harness 未捕获 stdout/stderr，不能将其外推为交互用户启动结论，也不能据此定位根因。Windows Sandbox CLI 要求先连接并建立活动用户会话，才能使用 `ExistingLogin`（[Microsoft Sandbox CLI](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-cli)）。先修正 Sandbox 结果目录映射，连接 guest 交互会话并运行非 AppContainer 基线，再从相同用户父 token 创建 AppContainer 子进程；按 Microsoft 句柄继承要求用显式 `PROC_THREAD_ATTRIBUTE_HANDLE_LIST` 捕获标准输出/错误（[Microsoft process handle inheritance](https://learn.microsoft.com/en-us/windows/win32/procthread/inheritance)），并检查 guest user-data-dir 的 Crashpad 记录和 Application Error/WER 事件。WER `LocalDumps` 仅作为 guest 内的可选 fallback，因为官方文档指出它不支持应用自带的 crash reporter（[Microsoft LocalDumps](https://learn.microsoft.com/en-us/windows/win32/wer/collecting-user-mode-dumps)）；如仍需进程 dump，再评估只在一次性 guest 使用 ProcDump。之后对照 parent token、AppContainer capabilities、profile ACL、user-data-dir 与 Playwright 的真实 launch 参数。在原因定位前不据此选定 AppContainer 生产架构，也不把 `--no-sandbox` 作为规避项。若浏览器或其必要子进程不支持所需低权限 token，应重新评估可验证的隔离边界并保持 fail closed。AUD-77 **OPEN**、P2 **NOT PASSED**，真实服务/IPC/安装回滚、全流量矩阵和三条不同授权媒体捕获仍未完成。

## 114. 2026-10-11 交互用户 Chromium/AppContainer 崩溃根因线索

- **隔离和身份：** 使用 `ChromiumDiagnostic.wsb`（guest 网络关闭、浏览器映射只读、结果目录单独可写），连接 Sandbox 桌面后以 `wsb exec --run-as ExistingLogin` 运行；实际 token 为 `WDAGUtilityAccount`、session 1。主机 Playwright Chromium 1243 的 308 个文件复制到 guest 本地临时目录。整个过程没有在宿主安装服务、提权或写入 WFP/Firewall、注册表及网络策略；结束后 Sandbox 已停止，`wsb list --raw` 为空。
- **权限修正和复测：** 在 AppContainer profile SID 与 Chromium 临时 user-data-dir ACL 配置之外，又对 staged browser tree 的 316 个文件/目录项逐项授予该 SID `ReadAndExecute`。这消除了此前 `sandbox_win.cc` 报 `Sandbox cannot access executable ... 0x5` 的首个错误。AppContainer `CreateProcess` 成功，子进程 package SID 与预期 profile 一致；但 `--version`、`--no-sandbox --version` 均立刻输出 `crashpad_client_win.cc:323 ... CreateNamedPipe: 拒绝访问 (0x5)` 并以 `-2147483645`（`0x80000003`，`STATUS_BREAKPOINT`）退出。带 `--disable-crashpad-for-testing` 的诊断也出现同一错误。stderr 已捕获；Application Error/WER 事件记录 `chrome_elf.dll` 与异常码 `0x80000003`，没有收集 minidump。headless `about:blank` 未运行，因此仍没有 Chromium/Playwright 进程树或页面网络策略结果。逐结果见忽略的 `sandbox-results/chromium-appcontainer-acl.json` 与 `chromium-appcontainer-no-crashpad.json`。
- **根因判断（来源推断）：** Microsoft 文档指出 Windows 10 1709 之后 AppContainer 内的命名管道必须使用 `\\.\pipe\LOCAL` 名称（[ConnectNamedPipe 文档](https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-connectnamedpipe)）。Chromium Crashpad Windows 源码创建随机 `crashpad_<pid>_...` 命名管道；源码仅在 `WINDOWS_UWP` 构建时添加 `LOCAL`，普通 Win32 构建使用 `\\.\pipe\crashpad_...`（[Crashpad Windows client source](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/third_party/crashpad/crashpad/client/crashpad_client_win.cc)，[pipe creation](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/third_party/crashpad/crashpad/util/win/exception_handler_server.cc)）。这与本次 `CreateNamedPipe` 的拒绝访问相符，是当前最强根因假设；仓库尚未固定 Playwright 二进制对应的 Chromium 源码提交，也没有对精确源码版本作逐行核对，故记为高可信推断而非源码级确认。
- **对策与状态：** 文件 ACL 和父进程上下文已排除为本次首要失败点。若保留每次 lease 独立 AppContainer SID，需要使用经维护、可溯源的 Chromium 构建，让 Crashpad 管道位于 AppContainer 支持的 `LOCAL` 命名空间，并重新验证崩溃处理、Playwright 启动、完整子进程 SID/网络能力及代理连接；不能把实验性关闭 crash reporter 或 `--no-sandbox` 当产品规避。另一条路是重新设计不要求 browser 根进程进入 AppContainer 的 OS 网络边界，并重新完成完整正反向验收。在这两条路之一通过前，不启动 Chromium URL capture，应用继续因 broker 不可用而 fail closed。P2/AUD-77 **OPEN/NOT PASSED**，项目 WFP service、IPC、installer/rollback、全流量矩阵和三条授权媒体捕获仍未完成；P4/P5/P6 开放项不变。

## 115. 2026-10-11 专用用户 SID WFP 与 Chromium 交互启动复核

- **授权与隔离：** 用户授权代理自主选择后续路径。所有写入性 WFP 操作都只发生在一次性、联网 Windows Sandbox 的 guest SYSTEM dynamic session；每轮结束调用 `wsb stop`，最后 `wsb list --raw` 为空。Codex 主机令牌仍为普通用户；没有在宿主安装服务、提升权限、改写 WFP/Firewall、注册表或网络设置。
- **用户 SID 规则动态验证：** `UserSidChromiumSmoke.ps1` 在 guest 中创建随机低权限本地账户，并对只读映射后暂存的 Chromium 目录授予该账户和 `ALL APPLICATION PACKAGES` 读取/执行。过滤前，相同数值 IPv4 目标的账户与 SYSTEM HTTPS 基线均成功。guest SYSTEM 成功打开动态 session、添加 sublayer 和一条 `FWPM_LAYER_ALE_AUTH_CONNECT_V4` / `FWPM_CONDITION_ALE_USER_ID` 条件过滤器，条件类型为 `FWP_SECURITY_DESCRIPTOR_TYPE`；三项 API 返回 0。过滤期间测试账户 curl 连接失败（exit 7），SYSTEM 对照保持成功（exit 0）；关闭 session 后测试账户恢复（exit 0），close 返回 0。Microsoft 的官方示例说明该条件使用自相对安全描述符，DACL 授予 `FWP_ACTRL_MATCH_FILTER` 时条件匹配为真；这不是授权流量本身，而是条件判断。[官方用户条件示例](https://learn.microsoft.com/en-us/windows/win32/fwp/permitting-and-blocking-applications-and-users)、[条件标识与数据类型](https://learn.microsoft.com/en-us/windows-hardware/drivers/network/filtering-condition-identifiers)
- **浏览器失败及 harness 修正：** 同一脚本使用 `CreateProcessWithLogonW` 测试专用账户的 Chromium `--version` 与 headless `about:blank`。两项在安装 WFP 规则前就超时，隔离期间仍超时或以 `0xC06D007E` 退出，且没有截图或 Chromium 日志；因此不能把浏览器失败归因于 WFP，也没有得到浏览器流量隔离结果。首次迭代的脚本曾只凭 curl 子项把总体标为 pass；已修正验收判定，最新忽略结果为 `status=fail`，只将 WFP curl 隔离子项记为通过。该浏览器探针在 SYSTEM/session 0 通过凭据创建进程，不等于受支持的交互用户会话启动；Microsoft 文档指出 `CreateProcessWithLogonW` 的 profile/environment 行为与普通交互登录相关但并不保证相同，故此结果仅是启动上下文诊断，不可外推为产品失败的最终根因。[CreateProcessWithLogonW 文档](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createprocesswithlogonw)
- **交互会话补充：** 另在网络关闭的 Sandbox 中，将 308 个锁定 Chromium 文件复制到 guest 本地目录，校验源/目标 `chrome.exe` SHA-256 相同，并逐项向 `WDAGUtilityAccount` 和 `ALL APPLICATION PACKAGES` 授予读取/执行（317 个文件/目录 ACL 项）。以真实交互用户 `WDAGUtilityAccount`、session 1 启动 Chromium headless 后，进程树运行超过 20 秒、未生成 `about:blank` 截图；日志有 DNS 配置读取告警和 GPU virtualization shared-context 错误。Sandbox 停止时一并终止残留进程。此结果排除了此前最简单的共享路径 ACL 解释，但网络关闭与 Sandbox GPU 环境限制本身可能影响 headless 完成；它不是普通 Windows 桌面、项目 Playwright pipeline 或 WFP 状态下的最终验收。辅助记录位于忽略的 `native/windows/wfp-policy-plan/sandbox-results/chromium-interactive-acl-baseline.json`、`chromium-interactive-headless.json` 与 `chromium-user-sid-wfp-smoke.json`。
- **结论与对策：** 按 `ALE_USER_ID` 区分低权限账户的 WFP 规则已获得 guest curl 级动态证据；这是可继续评估的服务隔离候选，不是 Chromium/Playwright 通过。AppContainer package SID 路径仍受 §114 Crashpad 故障阻断；普通低权限用户路径的浏览器进程启动方式也未通过。下一步应在可回滚环境中由可信服务原型验证受支持的用户会话 token、环境/profile、桌面/无头 Chromium 启动与退出，再将 WFP lease 与整个 browser 子进程生命周期绑定；不把 `--no-sandbox` 或绕过启动失败作为产品方案。服务、认证 IPC、持久默认拒绝、IPv4/IPv6 与 TCP/UDP/raw-socket 覆盖、故障回滚、真实代理流量和三条获授权视频捕获仍未实现。P2/AUD-77 **OPEN/NOT PASSED**，应用继续 fail closed；P4/P5/P6 和整体 **NOT READY** 状态不变。

## 116. 2026-10-11 Chromium 交互 headless harness 清理兼容性修复

- **复核发现：** §115 使用的 `chromium-interactive-headless.json` 记有 `Process-tree kill failed: Cannot find an overload for "Kill" and the argument count: "1"`。当时脚本调用 `.Kill($true)`，但 guest 的 PowerShell/.NET `Process` API 不支持带 `entireProcessTree` 参数的重载。脚本随后仍尝试按 staging 路径停止进程，但旧结果未包含当前脚本定义的 `browserProcessCleanup` 结构，因此进程树清理状态没有被机器可读地证实。已记录的 20 秒超时和无截图仍然有效；它仍然是一次浏览器探针失败，不能归因为 WFP。
- **本地修复：** `ChromiumInteractiveHeadlessSmoke.ps1` 现在使用 `Win32_Process` 的父 PID 关系从本次 Chromium 根 PID 枚举进程树，且只跟踪锁定 staging 目录中的映像；按最近创建的后代优先停止，再停止根进程。结果记录根 PID、根退出确认、已停止 PID 和残留 PID。status 仍要求无超时、exit code 0、有截图且无残留进程；清理成功不会把超时探针判为通过。
- **验证与结论：** 更新脚本通过 PowerShell AST 解析，并在禁网 disposable Sandbox 中完成复跑。guest staging 的 308 个 Chromium 文件源/目标 `chrome.exe` SHA-256 一致；交互用户 session 1 启动后仍超时 20 秒、未生成截图，结果为 `status=fail`。修复后的 JSON 记录根进程已退出、停止了 9 个 Chromium 后代与根进程，`remainingProcessIds` 为空；日志仍有 DNS 配置和 GPU virtualization 警告。该结果确认诊断进程清理，不确认页面渲染、正常浏览器启动或网络隔离。Sandbox 已停止且 `wsb list --raw` 为空；没有在宿主安装服务、启动提权命令或修改 WFP/Firewall、注册表和网络策略。P2/AUD-77 仍 OPEN/NOT PASSED，项目整体仍 **NOT READY**。

## 117. 2026-10-11 CreateProcessAsUser Chromium 用户会话原型

- **目的与隔离：** 为解决 §115 的 `CreateProcessWithLogonW`/session 0 诊断局限，新增 `ChromiumAsUserTokenSmoke.ps1`、`ProbeInteractiveSession.ps1`、`ProbeInteractiveDesktopAcl.ps1` 与 `GrantInteractiveDesktopAccess.ps1`。所有启动测试均在 guest 网络关闭的 disposable Windows Sandbox 中进行。guest SYSTEM 创建随机低权限账户，执行 `LogonUserW`、设置 token session、`LoadUserProfileW`、`DuplicateTokenEx`、`CreateEnvironmentBlock` 和 `CreateProcessAsUserW`，并记录 Chromium 进程树的 SID/session。桌面 ACL 授权通过 `ExistingLogin` 进程的短期 RunToken 握手完成。脚本没有 WFP API，也没有改宿主 WFP/Firewall、注册表或网络策略。
- **静态检查与暂存 ACL：** 浏览器文件树在 guest 本地暂存；随机用户与 `ALL APPLICATION PACKAGES` 获得 `ReadAndExecute`，独立 user-data 根目录授予两者 `Modify`。本轮 PowerShell AST 解析和内嵌 C# interop 编译通过。初始 `WinSta0\Default` ACL 中没有随机目标 SID；只在 Sandbox guest 内给随机 SID 临时加入 window-station mask `0x000F037F` 和 desktop mask `0x000F01FF`，然后重试。该权限较宽，仅用于确认交互桌面初始化假设；不能照搬到产品或宿主。每个测试结束都关闭 Sandbox，最后 `wsb list --raw` 为空。
- **首个异常已定位：** 对 ProcDump 生成的 352 MiB minidump 解析 ExceptionStream、Memory64List、DelayLoadInfo 与模块映射，确认 `0xC06D007E` 来自 `chrome.exe` 的延迟导入，目标是 `USER32.dll!GetProcessWindowStation`，`dwLastError=1114`。Microsoft 定义 1114 为 DLL 初始化例程失败；MSVC 对此延迟加载异常的说明表明异常参数指向 DelayLoadInfo。[Win32 1114](https://learn.microsoft.com/en-us/windows/win32/debug/system-error-codes--1000-1299-)；[MSVC delay-load error handling](https://learn.microsoft.com/en-us/cpp/build/reference/error-handling-and-notification?view=msvc-170)。在授予随机 SID 交互 station/desktop ACL 后，后续运行不再出现该异常，说明桌面 ACL 缺失是强因果候选；尚未证明该授权本身就是唯一修正。
- **当前启动结果仍失败：** 最近三次授权后的运行均能以目标随机 SID/session 1 创建 Chromium root 与子进程，且未再出现 `0xC06D007E`，但未生成 `about:blank` 截图，退出码为十进制 `21`。stderr 报告 `Failed to create a ProcessSingleton for your profile directory`。Chromium 153.0.8010.12 的锁定源码提交 `971a7443b0c9b0a9b2860529b33331b76077ec62` 将 `LOCK_ERROR` 映射到 `PROFILE_IN_USE`；Windows 实现依次创建 session-local 命名 mutex、profile `lockfile` 和消息窗口，但锁文件/窗口路径中的实际失败 API 尚未核实。[版本锁定的 Windows ProcessSingleton 源码](https://chromium.googlesource.com/chromium/src/+/971a7443b0c9b0a9b2860529b33331b76077ec62/chrome/browser/process_singleton_win.cc)；[Chrome startup handling](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/chrome/app/chrome_main_delegate.cc)。同一 SID 对相同目录成功执行 `CreateFileW` 删除即关闭锁文件探针，因此单纯文件 ACL 不是当前已证实根因。Process Monitor 记录了 125,371,651 字节 PML，但 CSV 导出未完成；未将轨迹用于根因判断。
- **解释边界与后续：** 这证明 SYSTEM 可以创建目标 SID/session 的进程树，并且补上 guest desktop ACL 后 USER32 初始化阶段继续向前；不证明 Chromium 渲染、Playwright、WFP `ALE_USER_ID`、代理连通、外网阻断、lease 清理或产品 service/IPC。下一步先以窄过滤的文件/窗口对象跟踪定位 `ProcessSingleton` 失败，再用完全相同的会话方式通过 headless `about:blank` 和 Playwright；之后才进行浏览器 WFP 正负向流量验收。产品应为受控的专用用户会话/desktop 配置最小 ACL，不能修改当前登录用户的宿主桌面 ACL；不得禁用 Crashpad 或 Chromium sandbox。
- **保留的诊断文件：** 352 MiB minidump `sandbox-results/chrome.exe_261011_024450.dmp`（SHA-256 `3DEBBAD066F9CB3B7FA122670C7EB5A80E463DD70CC7FEAC21A204DC04EF841F`）和 125,371,651 字节 `sandbox-results/chromium-startup.pml` 均位于忽略目录。它们没有媒体/逐字稿内容。清理这两个精确文件的命令被本机执行策略拒绝，因此保留在原位；ProcDump/PsExec/Process Monitor 也只下载到 `%LOCALAPPDATA%\Temp\codex-*`，没有安装到系统。
- **权限边界与状态：** 用户授权全部操作，但宿主没有可用的管理员令牌；此前 UAC 提权启动被执行策略拦截。未尝试绕过该策略，也没有接入管理员主机。guest SYSTEM 权限只存在于一次性 Windows Sandbox；宿主 WFP/Firewall 仍未改动。管理员 WFP 服务、认证 IPC、持久默认拒绝、安装/回滚、真实代理流量及三条获授权媒体仍未完成。P2/AUD-77 **OPEN/NOT PASSED**，应用继续 fail closed，整体 **NOT READY**。

## 118. 2026-10-11 Process Monitor 轨迹离线导出尝试

- **范围：** 为继续定位 §117 的 Chromium `ProcessSingleton` 失败，只读处理已保存的 `chromium-startup.pml`（125,371,651 字节）。未重新启动 Chromium，也未读取用户媒体或逐字稿。
- **结果：** 普通宿主令牌下运行 Procmon `/OpenLog` 与 `/SaveAs` 返回退出码 1，没有生成 CSV。随后在禁网 disposable Windows Sandbox 中将轨迹映射给 guest SYSTEM；Procmon 在 session 0 保持运行，但一分钟后仍未产生 CSV。关闭 Sandbox 后 `wsb list --raw` 为空。两次操作均未得到可用于归因的事件，也没有修改宿主 WFP/Firewall、注册表或网络设置。
- **限制与下一步：** 这不证明 PML 无效或内容中不存在相关事件。要继续分析，需先在 Procmon 中建立只保留锁定 Chromium 进程、profile `lockfile` 及命名对象操作的过滤配置，再对原日志导出；若仍不可行，则在禁网 Sandbox 重新捕获带预设窄过滤器的短启动轨迹。不得据当前失败日志推断 `ProcessSingleton` 根因。P2/AUD-77 仍 **OPEN/NOT PASSED**，项目整体 **NOT READY**。

## 119. 2026-10-11 Chromium headless 渲染环境对照

- **目的：** 检查 §117 的 Chromium 启动失败是否可由 Sandbox 的 GPU virtualization 或关闭网络单独解释。使用锁定的 Chromium 文件树和 `ExistingLogin`（`WDAGUtilityAccount`，session 1），打开 `about:blank`，仅在 guest 内运行；网络版本只访问本地空白页，不访问抖音页面。每次结束都按本次 root PID 与 staged browser 路径清理进程树。
- **对照结果：** 默认 GPU、禁网运行 120 秒后超时且没有截图，日志出现 `Failed to create shared context for virtualization`。早先标为 SwiftShader 的两次运行实际同时传入了 `--disable-gpu` 与 SwiftShader 参数，不能用作有效 SwiftShader 验证；联网版本仍超时且无截图，但这一组参数冲突须结合 §120 的修正测试解释。原结果均为 `status=fail`，进程树停止且 `remainingProcessIds` 为空。Sandbox 均已停止，`wsb list --raw` 为空。结果保存在忽略文件 `chromium-interactive-headless.json`、`chromium-interactive-headless-swiftshader.json` 和 `chromium-interactive-headless-swiftshader-network.json`。
- **结论边界：** 该初始对照不能证明 SwiftShader 已实际启用，也不能据此断定 GPU warning 是或不是根因。联网版本未能完成页面，但对网络变量的解释需保持谨慎。DNS/功能 warning 也未与卡住建立因果关系。该探针仍不是普通桌面环境、Playwright、用户 SID 的 `ProcessSingleton` 定位、WFP 规则或抖音捕获验收，不能据此判断产品隔离是否有效。
- **下一步与状态：** §120 修复了参数冲突并新增独立 DOM 输出检查；现有 `ProcessSingleton` 错误和 API 根因仍未定位。继续需取得可分析的窄过滤 Procmon/对象跟踪，优先区分命名 mutex、profile lockfile 和消息窗口创建，再在目标会话完成短时 headless 渲染及 Playwright smoke。禁止以关闭 Chromium sandbox/Crashpad 当作修复。没有修改宿主 WFP/Firewall、服务、注册表或网络策略。P2/AUD-77 仍 **OPEN/NOT PASSED**，项目仍 **NOT READY**。

## 120. 2026-10-11 Chromium GPU 参数修正与 DOM 启动探针

- **Harness 修正：** 复核 §119 后发现 `-UseSoftwareGl` 分支还同时传入 `--disable-gpu`，使 SwiftShader 对照存在冲突。现在 `ChromiumInteractiveHeadlessSmoke.ps1` 在默认模式使用 `--disable-gpu`，在 SwiftShader 模式改用 `--use-gl=angle --use-angle=swiftshader`，二者互斥。另加 `-UseDumpDom` 诊断模式，以异步读取 Chromium stdout，并在 JSON 中记录 DOM 是否含 HTML。PowerShell AST 解析通过。
- **有效 SwiftShader 复测：** 在禁网 disposable Sandbox 的交互 `WDAGUtilityAccount` session 1 中运行正确且无冲突的 SwiftShader `about:blank` 截图 smoke，30 秒后超时、无截图。10 个跟踪到的 Chromium 进程已停止，`remainingProcessIds` 为空，Sandbox 停止且 `wsb list --raw` 为空。另一个同样使用有效 SwiftShader 的 `--dump-dom` smoke 运行 30 秒后超时，未输出 DOM（长度 0）；11 个跟踪进程停止且无残留，Sandbox 同样已停止。该结果说明不只是 screenshot 文件输出路径没有产生结果，但仍不能确定卡在浏览器初始化、导航还是渲染。
- **日志和归因边界：** 一次 30 秒详细日志运行展示了 Blink、浏览器 profile 和若干后台子系统已开始工作；脚本截取的 160 行日志尾部未包含 `ProcessSingleton`、`CreateLockFile`、`CreateWindow`、`PROFILE_IN_USE` 或 `lockfile` 匹配项。该有限日志不覆盖完整事件轨迹，不能推翻 §117 的 exit 21/`ProcessSingleton` 失败，也没有指出哪个 API 卡住。此前 §119 标为 SwiftShader 的两个旧结果保留作历史记录，但不作为有效 SwiftShader 证据；联网对照只说明当时相同冲突参数下开启网络仍超时。
- **状态与对策：** 不使用 `--no-sandbox`、不关闭 Crashpad，也没有修改宿主 WFP/Firewall、服务、注册表或网络策略。后续应使用可分析的进程/文件/窗口对象窄过滤跟踪定位阻塞阶段，再验证截图和 Playwright。结果文件 `chromium-interactive-headless-verbose.json`、`chromium-interactive-headless-swiftshader-valid.json`、`chromium-interactive-dump-dom-swiftshader.json` 均位于忽略目录，不含媒体或逐字稿。P2/AUD-77 **OPEN/NOT PASSED**，项目仍 **NOT READY**。

## 121. 2026-10-11 转写完成状态与 Agent 校对门槛

- **复核要求：** 用户要求最终逐字稿必须由调用 Agent 的默认模型校对纠错并添加自然标点。CLI 不具备读取宿主当前 Agent 模型或调用该模型的能力；将 CLI 的 ASR job 状态误称为最终产品完成会掩盖尚未完成的模型校对。
- **本地修复：** transcribe/retry JSON 摘要新增 `result_scope=raw_asr_only` 与 `llm_review_status=not_performed_by_cli`。普通文本成功行显示 `RAW_ASR_READY`；汇总行也标明 raw ASR 范围和未执行模型校对。CLI 的既有 success/exit-code 语义仍代表 raw ASR 输出成功，不表示 Agent review 完成。Canonical Skill 现在精确区分 CLI 的 `status=success`、任务库 `state=completed` 与 Agent 端到端完成；模型校对获授权时，只有另存并核验非空 `.reviewed.md` 后才允许报告完成。未能校对或用户选择本地模式时明确返回未校对 raw 状态。
- **隐私及产品边界：** CLI 不接收 transcript body 来调用固定 provider，也不在摘要中输出正文；review 仍通过当前 Agent 默认模型进行，按 Skill 在读取正文前披露可能的数据传输并取得授权，保留 raw 文件，reviewed 内容写入独立副本。
- **同步与验证：** 更新中英文 README、CLI reference、安装说明、架构说明和 canonical Skill；新增 CLI JSON/text 状态回归。Python 3.11.15 锁定环境定向 CLI summary 测试 **8 passed, 71 deselected**；`agentskills validate` 返回 `Valid skill`；`git diff --check` 退出码为 0（仅有仓库现存 LF→CRLF 提示）。本轮未读取用户逐字稿正文，未调用 ASR 或模型 API。
- **验收边界：** 该修改让 CLI 状态清楚表达其 raw-ASR 范围，并把 Agent 任务完成门槛写入 Skill；它不让 CLI 自动调用宿主模型。跨 Agent 宿主的模型数据流/默认模型和实际审校动作仍须按 P4/P5 清单验收；项目总体保持 **NOT READY**。

## 122. 2026-10-11 敏感文件扫描大小上限与跨块凭据回归

- **发现与复现：** 当前 Git 可见的 `docs/artifact-member-inventory.jsonl` 为 7,294,065 字节。原 2 MiB 内容扫描上限使扫描器按 `exceeds content scan size limit` 失败关闭，导致本地敏感文件检查整体失败；这是大小策略不匹配，不是该清单命中凭据。清单是项目生成的 SPDX artifact 成员证据，需在保留失败关闭的前提下纳入扫描。
- **跨块风险复核：** 原 64 KiB 分块实现使用固定 256 字符 overlap，但 credential assignment 模式允许 key/delimiter 与 16 字符值之间出现任意长 `\s*`。当 key 位于块边界前而超长空白和值位于后续块时，固定 overlap 会丢弃 key，可能漏报。针对任意空白长度推算足够 overlap 没有有限解。
- **修复：** `scripts/check_sensitive_files.py` 将单文件上限提高至 16 MiB，并对上限内文件读取整个 UTF-8 内容再执行完整凭据模式扫描；读取最多 16 MiB+1 字节，超限立即失败关闭。移除依赖固定 overlap 的分块检测。NUL、非 UTF-8、符号链接、非普通文件及读取错误继续失败关闭；诊断不打印匹配值。内存用量受单文件上限约束。
- **回归与当前树证据：** 新增测试在旧 64 KiB 边界前放入 `sessionid` key，随后加入超过 64 KiB 的空白和 16 字符值，并附加大于 2 MiB 的文本；扫描必须报告 `credential assignment`。`tests/unit/test_sensitive_files.py` 为 **9 passed**；实际仓库扫描通过并完整扫描 7,294,065 字节清单；变更文件 Ruff、`git diff --check` 通过。修复后的 Windows Python 3.11.15 全套 pytest 为 **522 passed, 23 skipped**（245.38 秒）；跳过项依赖本机不支持的 POSIX FIFO、权限、目录句柄或符号链接能力。
- **范围：** 该检查仍只扫描当前 Git 可见树，不是通用 secret scanner，也不检查完整提交历史。16 MiB 以上文件显式拒绝；最终发布树与历史仍须复核。P6 的远端 CI/跨平台及授权发布门槛不因本次扫描通过而关闭，项目整体保持 **NOT READY**。

## 123. 2026-10-11 Chromium ProcessSingleton 命名对象权限线索与受限复测

- **现有线索：** 对 §117 的 `ProcessSingleton` 启动失败继续作只读定位时，低权限目标 token 对自己的 token 默认 DACL 有授权，但该账户被放入 session 1 后，对 `\Sessions\1\BaseNamedObjects` 没有已观察到的 ACE。目标 SID 创建未命名 mutex 成功；创建精确名称 `Local\ChromeProcessSingletonStartup!` 和随机 `Local\...` mutex、打开已有命名 mutex 均返回 Win32 5。目标 SID 的 profile lockfile 创建/删除和消息窗口创建探针成功。Sandbox 的 `ExistingLogin` 账户能够创建这些命名 mutex 并读取该目录 ACL。该差异使 session 命名对象命名空间权限成为 `ProcessSingleton` 失败的强候选，但仍没有通过 Chromium API 返回码或完整启动实验确认因果。
- **静态与一次受限复测：** 三个 PowerShell 脚本 AST 解析和 probe/harness/mutex helper 的 C# interop 编译通过；新建禁网 disposable Sandbox 并确认 `ExistingLogin` 位于 session 1，记录随机 SID 与 run prefix 后，启动 SYSTEM harness 的长命令被本机执行策略拦截；拦截发生在 helper、Chromium 和 mutex 测试启动之前。按既定边界停止重试，随后停止 Sandbox，`wsb list --raw` 为空。目标 mutex 没有被预创建，Chromium PID、截图和 API 结果均不适用；宿主 WFP/Firewall 未操作。
- **对策与验收门槛：** 不以授予目标账户更宽的 session-wide `BaseNamedObjects` ACL 作为未经验证的修复；固定名称 mutex 预创建方案也尚未试验，且须先证明其 ownership/handle 生命周期、与普通 Chrome 的冲突行为及并发 lease 隔离。后续诊断若有合规执行通道，应在 disposable guest 中先验证精确 mutex 权限和无主 mutex 的生命周期，再用同一 token/session 启动锁定 Chromium，要求 `about:blank` 页面/截图成功、Chromium 进程树完整且可清理，然后才测 Playwright 和 WFP egress。当前没有可执行管理员 SYSTEM harness 的运行通道；不绕过本机策略。P2/AUD-77 仍 **OPEN/NOT PASSED**，URL 捕获保持 fail closed，项目仍 **NOT READY**。

## 124. 2026-10-11 P6 artifact/SBOM 离线证据复核

- 两个项目锁定环境均通过 `uv lock --check`；固定 SHA-256 的 SPDX 2.3 schema 检查、Git 可见敏感文件扫描与 `git diff --check` 通过。离线 verifier 按 SHA-256 清单检查 41 个锁定包、54 个发行物、41 个 metadata、9 个 license、2 个 notice 和 63 个补充成员。
- 使用记录中的生成时间重建 SPDX 清单，121 个 package records、137 个 relationships 与工作树 `docs/third-party-sbom.spdx.json` 逐字节一致（164,499 bytes）。这只证明当前已登记 artifact 和成员字节一致，不构成许可证适用性、依赖完整性或构建来源结论。
- P6 仍 **NOT READY**：仓库无根 `LICENSE`、无 Git remote；native 组件/许可证与构建来源审阅、远端 CI、远端干净安装及许可证/发行范围/仓库与可见性/远端操作授权均未完成。没有推送或发布。详见 `docs/RELEASE_REPORT.md`、`docs/OWNER_DECISIONS.md`。

## 125. 2026-10-11 AUD-86：P2 代理客户端身份与出口所有权未绑定

- **发现：** 当前应用契约把 broker 监听 socket 的副本交给普通 Python 进程中的 `PinnedHttpsConnectProxy`；CONNECT handler 不验证本机客户端身份。代理仅允许特定 Douyin/IESDouyin HTTPS 主机及 TCP 443、检查 DNS 为公网并固定目标 IP，因此该路径不是任意目标代理或内网 SSRF，但可被能连接该 loopback 端口的其他本机进程复用来访问 allowlist 主机，并可能耗尽最多 64 个连接槽。上游 socket 也由普通 Python 进程创建。WFP 预览按固定 Chromium AppID 定义例外，不能区分 lease；浏览器路径相同的另一进程也可能命中该 AppID。
- **影响边界：** 当前没有生产 broker/service listener，`open_system_broker()` 明确失败；`BrowserCapture.start()` 在启动浏览器前返回 `BROWSER_ISOLATION_UNAVAILABLE`。所以这是计划集成契约中的可达性/租约绑定缺口，不是当前已启用产品运行路径的漏洞。代理隧道测试用例确实可在无客户端认证下连接本地 fake listener；该用例证明 relay 行为，不证明任何生产隔离。
- **对策：** 管理员主服务只做 control plane，不持有每 lease listener、DNS 或 upstream socket。每个 lease 必须由受保护的低权限 worker 在独有 OS SID 下运行；该 worker 持有 listener、处理 CONNECT、发起 DNS 查询并创建固定 IP upstream socket，也负责以同一 lease SID 启动 Chromium/Playwright。WFP 用 endpoint catch-all deny，仅允许目标 browser AppID + lease SID 连接该 lease endpoint；worker AppID + SID 的出口只允许受信 numeric resolver endpoint 和该 lease 完整 A/AAAA/CNAME 公网验证后固定的 numeric IP:443。共享管理员 service AppID/SID 上的动态目的地许可会形成跨 lease 并集，不能声称逐 lease egress；除非另有经验证的逐流 callout 隔离，否则必须用独有 worker OS identity。capture route 只做 scheme/hostname allowlist 与 URL 语法校验，不通过普通 Python/Windows DNS Client 解析；真实 DNS 完整性检查和 numeric IP pinning 留给 worker。若独立 worker 或 Chromium 目标 token 无法可靠启动，保持 fail closed，不写成已实现。
- **验收门槛：** 在隔离、可回滚 Win11 环境验证每个目标 lease 浏览器可以完成获授权 HTTPS；同 SID/同路径的其他 Chromium 与其他本机进程连接 lease 端点被 endpoint catch-all deny 拒绝。两个并发 lease 的 DNS 查询和 upstream socket 必须分别归属各自 worker AppID + SID；A/AAAA（含 CNAME 链终值）全集均须为公网地址，并且 worker 只能连受信 numeric resolver 与该 lease pinned IP:443，不能访问另一 lease 的 resolver/IP 或其他目的地。还需验证其他 loopback/端口、私网/LAN、IPv4/IPv6 直连和 UDP 被拒绝；错误 endpoint、lease 断开、IPC 断开、worker/Chromium 无法启动及 service 退出后无 listener 或代理例外残留。当前均未验收，AUD-77/AUD-86 保持 **OPEN / NOT PASSED**。

## 126. 2026-10-11 P2 应用侧 lease 契约收紧与当前树回归

- **实现调整：** `IsolationLease` 只返回 broker 选定的 `BrowserIdentity`、精确 `ProxyEndpoint` 和健康/生命周期接口，不再暴露 `proxy_socket`。`BrowserCapture` 当前接口仍让调用方取得浏览器身份和代理 endpoint，并由调用方进程内 Playwright 启动 Chromium；这不符合 §125/§127 的每 lease worker 目标。由于 `open_system_broker()` 仍 fail closed，该路径目前不可达。实现真实 IPC 前，必须改成 CLI 只发送 capture 请求、worker 在 lease SID 下启动浏览器并经 IPC 返回结果。`open_system_broker()` 仍不可用，缺少服务时仍在 profile/browser 启动前 fail closed。
- **代理测试边界：** `browser_proxy.py` 保留为独立测试/诊断 CONNECT relay，已从 `BrowserCapture` 产品路径移除。它的本地 relay 测试只验证该模块行为，不证明代理客户端认证、服务 WFP policy 或 upstream egress。旧 socket-handoff 回归留作明确标记的历史实验。
- **验收与结果：** P2 capture/proxy 定向回归 **41 passed**（6.16 秒），proxy 测试重命名后追加 smoke **1 passed**；相关 Ruff 与 `git diff --check` 通过。当前工作树 Windows Python 3.11.15 全套为 **522 passed、23 skipped**（333.21 秒）。Python 3.12.13 当前树尚未重跑；23 个跳过项依赖 POSIX FIFO、权限、目录句柄或本机不支持的 symlink 行为。
- **范围：** 此变更只修正应用侧 socket ownership 契约，不实现管理员服务、认证 IPC、唯一 lease worker OS identity、代理 listener catch-all deny、服务端 allowlist/DNS/IP pinning、受限 worker egress、安装器或故障回滚。当前 `BrowserCapture` 仍由调用进程内的 Playwright 启动 Chromium，没有按 lease SID 启动 worker/browser 的路径；service、worker 和 Chromium token 尚未启动验证。P2/AUD-77 与 AUD-86 仍 **OPEN / NOT PASSED**，没有修改宿主 WFP/Firewall。服务上线仍须完成 §125/§127 动态验收及三条获授权视频端到端验收。

## 127. 2026-10-11 AUD-86 路由 DNS 与逐 lease 出口身份收紧

- **代码调整：** capture 的 browser request 与 WebSocket route 不再调用 `_require_public_host`、`getaddrinfo` 或系统 DNS Client；route 仅验证 HTTPS/WSS scheme、URL 语法、导航主机 allowlist 与资源主机 allowlist。普通 downloader 和通用 URL validator 保持原样。新增测试将 `socket.getaddrinfo` 和 DNS 子进程调用设为失败，并同时验证未授权主机、HTTP/无效 URL 仍拒绝，授权 HTTPS/WSS 可继续路由。
- **架构与阻断项：** route 侧不解析 DNS 不能代替网络边界；完整 A/AAAA 与 CNAME 链公共地址检查、数值 IP pinning 必须由每 lease worker 完成。管理员主服务只做 control plane；每 lease 受保护低权限 worker 用独有 SID 持有 listener、DNS 和 upstream socket。WFP worker 出口按 worker AppID + SID 限制到受信 numeric resolver 和该 lease pinned IP:443。共享管理员 service AppID/SID 无法提供逐 lease 动态目的地隔离；其许可会汇成所有租约的目的地并集。当前 service/worker/Chromium 目标 token 均未实机启动验证，仍须 fail closed；DNS 身份和 worker/Chromium 启动已纳入 AUD-86 阻断项，不新增 AUD。
- **验收与结果：** `tests/unit/test_p2_capture.py` 定向回归 **26 passed**（0.75 秒）；Ruff 对 capture.py 与 test_p2_capture.py 检查通过，`git diff --check` 通过。本地单元测试不证明 DNS 查询的 OS identity、WFP worker egress、worker 启动或真实浏览器网络隔离。没有部署服务、启动 WFP 或修改宿主网络策略。

## 128. 2026-10-11 P2 路由修正后的当前树回归

- **全套测试：** Windows Python 3.11.15 下执行 `uv run --project .\skills\douyin-transcript --locked --no-sync --group dev pytest -q`，结果 **519 passed、23 skipped**（243.88 秒）。23 项跳过依赖本机不可用的 POSIX FIFO、符号链接、权限模式或目录句柄语义。该结果取代 §122/§126 的旧单版本数字；那些结果仍是对应历史工作树的有效记录。
- **静态检查：** 全仓 Ruff、敏感文件扫描、Agent Skills validator、`uv lock --check` 均通过，`git diff --check` 退出码为 0（仅显示现有 LF→CRLF 提示）。本机 doctor 的 ASR 相关检查为 ready，`browser_isolation=unavailable`、`douyin_urls=setup_required`。
- **范围：** 回归验证 CLI 路由不在本机解析 DNS 的应用契约，不证明 per-lease worker、DNS resolver identity、IP pinning、WFP 出口、受保护 Chromium 身份或真实抖音媒体可用。P2/AUD-77/AUD-86 仍 **OPEN / NOT PASSED**，项目仍 **NOT READY**。

## 129. 2026-10-11 管理员令牌状态对账与 Python 3.12 当前树回归

- **权限状态对账：** 当前 Windows identity 为 `local-machine\local-user`，本进程不是管理员；Administrators 组仅为 deny-only。当前 Codex shell 没有高完整性令牌，也没有可调用的项目 WFP broker/service。§95 的历史只读 UAC helper 成功仅说明当时可以启动那个 helper，不会提升本 Codex 进程；§108/110/123 记录后续 elevation helper 在启动前被执行策略阻止。用户已授权自主操作，但授权不能创建 OS 管理员令牌；没有尝试绕过执行策略、没有接入管理员主机，也没有对宿主安装服务或改动 WFP/Firewall。`docs/P2_REPORT.md` 原先把历史 UAC 探针写成可用管理员实现通道，现已改为明确标注历史，并同步当前 token 状态与实际阻断点。
- **Python 3.12 全量回归：** 在隔离 Python 3.12.13 环境运行当前树 `pytest -q`，结果 **519 passed、23 skipped**（156.08 秒）。首次运行时外层 `UV_PROJECT_ENVIRONMENT` 被 SPDX 测试子进程继承，导致四个 checker 测试错误地复用主 Skill 环境并找不到 `jsonschema`；清除该全局覆盖后直接用 Python 3.12 venv 启动 pytest，checker 使用自身锁定项目环境，最终全套通过。没有修改产品代码。23 个跳过项依赖 Windows 主机不提供的 POSIX FIFO、符号链接、权限模式、所有权或目录句柄语义。
- **结论与剩余项：** §128 的 Python 3.11.15 与本节 Python 3.12.13 当前树结果一致，均为 519/23。权限对账和回归不能替代管理员 WFP service、authenticated IPC、per-lease worker/Chromium identity、回滚验收及三条真实媒体验收。P2/AUD-77/AUD-86 仍 **OPEN / NOT PASSED**；P4/P5/P6 未关闭，整体 **NOT READY**。

## 130. 2026-10-11 管理员主机接入授权复核

- **用户指示：** 用户授权代理自行寻找管理员接入方式并处理。回复没有包含可连接的管理员主机名、远程管理端点、已接入高权限会话或现有 broker 地址；本地连接信息不能从授权文本推导。
- **当前执行边界：** Codex 工作进程仍是普通令牌，Administrators SID 为 deny-only。标准 `Start-Process -Verb RunAs` 只读 helper 在进程创建前被执行器策略拦截，未产生 elevated child process。一次性 Sandbox guest 的 SYSTEM 身份是隔离 guest 权限，不等于宿主管理员令牌；该 Sandbox 已停止。没有通过网络扫描猜测管理员主机，也没有改写宿主 WFP、Windows Firewall、服务或网络设置。
- **可继续与受阻工作：** WFP service/worker 的源代码可以在普通开发工作树中审阅和构建；但没有经验证的管理员安装/运行环境，不能安装宿主服务、写入宿主过滤器或完成 P2 动态验收。现有项目继续 fail closed。实际安装和动态验收需要连接到已授权的管理员会话或提供可用的管理员主机管理通道。
- **状态：** 该授权不会改变 OS token 或执行器策略；P2/AUD-77/AUD-86 继续 **OPEN / NOT PASSED**，项目仍 **NOT READY**。P4/P5/P6 的独立验收门槛不变。

## 131. 2026-10-11 敏感文件扫描器父目录 junction 越界与架构文档一致性

- **发现（CWE-59）：** `scripts/check_sensitive_files.py` 原先只检查 Git 可见路径的叶节点是否为符号链接。若中间目录是 Windows junction/reparse point，路径读取可越出仓库；合成 fixture 将 `nested/` 指向仓库外目录后，扫描器没有检查到仓库声明路径实际经过目录别名这一点。该问题会让本地敏感文件检查依赖别名目标的内容，而不是安全地拒绝不可信路径。
- **修复：** 先验证 Git 路径为跨平台规范的相对路径；每个 Windows 组件还拒绝盘符/ADS 冒号、尾随点或空格及设备保留名。POSIX 逐级使用 `O_DIRECTORY | O_NOFOLLOW` 固定父目录句柄，并以 `O_NOFOLLOW | O_NONBLOCK` 打开普通文件。Windows 从卷/共享根开始，用 `NtCreateFile` 按父句柄相对打开每个组件并设置 `FILE_OPEN_REPARSE_POINT`；检查 reparse 属性，且在叶文件打开前保留全部祖先句柄、拒绝 `FILE_SHARE_DELETE`，避免父目录在检查与打开之间被替换或移动。所有系统只在确认普通文件后才读取内容。
- **验证：** `tests/unit/test_sensitive_files.py` 定向回归 **12 passed、1 skipped**；Windows junction、盘符/ADS/设备名拒绝及 supplementary Unicode 路径精确打开用例通过，POSIX descriptor-walk 用例因当前 Windows 主机跳过。Ruff 两个改动文件通过，`python scripts/check_sensitive_files.py` 通过。未读取真实用户数据，回归只使用临时合成文件。POSIX 行为仍需在 Linux/macOS CI 实机覆盖。
- **架构契约问题（AUD-86 延伸）：** `isolation_broker.py` 当前 fail-closed 占位接口把 Chromium identity/代理 endpoint 返回给 CLI 调用方，`BrowserCapture` 代码路径会在调用方进程启动 Playwright/Chromium。这与 §§23–32 规定的“普通 CLI 只发 IPC capture 请求；每 lease worker 在唯一 SID 下启动浏览器并持有网络 socket”不一致。由于 `open_system_broker()` 仍明确失败，该启动路径当前不可达；但在接入真实 IPC 前必须改为 worker 执行/IPC 返回结果契约，不能把占位接口直接接到服务。对策已同步到 `P2_ISOLATION_DECISION.md` 和本报告 §126。P2 仍 **OPEN / NOT PASSED**。
- **整体状态：** 本次静态修复不替代 P2 管理员服务及动态 WFP/Chromium 验收，也不关闭 P4 长媒体人工听审、P5 新 Desktop 会话或 P6 许可证/发行决策。最近一次全套结果是修复前 §§128–129 的 Python 3.11/3.12 各 **519 passed、23 skipped**；§131 当前代码只完成定向回归，尚未重跑全套。项目仍 **NOT READY**。

## 132. 2026-10-11 §131 修复后的双版本全套回归与管理员授权边界

- **全套回归：** 在当前工作树运行锁定依赖的 pytest。Windows Python 3.11.15：**522 passed、24 skipped**（64.54 秒）；隔离 Python 3.12.13：**521 passed、25 skipped**（336.05 秒）。无失败，两个运行的总测试数相同。跳过项主要依赖 Windows 不支持的 POSIX FIFO、symlink、mode/owner 或 directory-handle 行为；3.12 另外因本次进程没有创建目录 junction 的权限，跳过一项 Windows junction 用例。该环境差异不等于 Linux/macOS 已通过。
- **静态验证：** 全仓 Ruff、Agent Skills validator、Skill/SPDX 两个 `uv.lock --check`、Git 可见敏感文件扫描与 `git diff --check` 均通过。Diff check 只显示工作树既有的 LF→CRLF 提示。
- **权限答复：** 用户再次授权代理自行处理管理员问题，但没有给出管理员主机名、可连接的远程管理端点、现存管理员会话或 broker 地址。当前本地 Codex 仍是普通令牌；历史 elevation helper 曾在创建进程前被执行器策略拦截。本次没有重试提权、扫描网络寻找主机、安装 Windows service 或修改宿主 WFP/Firewall。仅凭用户授权无法生成 Windows 管理员令牌，也无法推导远程连接信息。
- **安全边界与后续动作：** 普通权限下的代码审阅、编译和测试可继续；但仓库当前没有管理员 service、认证 IPC、lease worker 或生产安装器，故无法通过在现有主机“以管理员身份运行”来完成 P2。需要把工作区接入真实管理员会话，或由管理员提供已授权主机/运维通道；然后仍须先实现并评审 service/worker/IPC，再做可回滚 Win11 x64 WFP、Chromium 与三条获授权视频的动态验收。不得把一次性 Sandbox SYSTEM 结果当作宿主管理员执行或生产 service 验收。
- **剩余门槛：** P2/AUD-77/AUD-86 仍 **OPEN / NOT PASSED**；URL capture 保持 fail closed。P4 仍需至少 10 分钟授权样本和三处人工听审，P5 仍需新 Desktop 会话调用证据，P6 仍需所有者许可/发行范围/远端决定、native 组件来源与远端 CI/干净安装。项目整体 **NOT READY**。

## 133. 2026-10-11 短链与媒体下载的调用方网络绕行

- **AUD-87（P2，网络出口所有权缺口）：** `TranscriptionPipeline.run_urls()` 原先在启动浏览器/broker 之前调用完整 `resolve_input()`；`v.douyin.com` 因而可以在普通 CLI 进程执行 DNS 与 HTTPS，即使之后 `open_system_broker()` 失败。捕获后，`VideoMetadata.media_candidates` 又返回 pipeline，普通下载线程调用 `download_media()` 执行 CDN DNS、连接、重定向跟随和媒体传输。若未来只把浏览器捕获接入 worker，媒体网络流量仍会在隔离边界外。
- **当前整改：** 默认 pipeline、`--dry-run` 和 `resolve_many()` 改用不联网的 `resolve_direct_input()`。直接视频 URL 仍可本地规范化；短链现在返回 `BROWSER_ISOLATION_UNAVAILABLE`，直到 worker 可在 lease 身份下解析。此次源码收紧阻止默认入口在 broker 检查前访问网络；没有部署服务或修改系统网络策略。
- **必须先完成的服务契约：** IPC 应接收原始 URL 和受限资源参数，由同一个 per-lease worker 完成短链解析、浏览器捕获、媒体候选校验、CDN 重定向与下载。CLI 只能收到受限安全元数据与已校验媒体流/文件；不能收到签名 URL、请求头、媒体候选列表、DNS/连接能力或 socket。现新增协议切片 `capture_ipc.py` + `capture-ipc-v1.schema.json` 定义了有界请求/结果模型，但媒体字节传输仍需独立认证 stream/handle；当前下载调用链尚未迁移，`open_system_broker()` 仍 fail closed，service/worker/IPC transport 未实现。因此这次修复只关闭当前短链预解析，不构成 P2 通过，远端 capture 仍须保持 fail closed。
- **验证状态：** 本节对应源码与文档整理后未运行测试或 lint；§132 的 522/24 和 521/25 是之前的代码快照，不能作为 §133 改动的回归证据。IPC codec/schema 也未运行回归。未尝试访问抖音链接。P2/AUD-77/AUD-86/AUD-87 仍 **OPEN / NOT PASSED**，项目整体 **NOT READY**。


## 134. 2026-10-11 浏览器 profile 与手动登录生命周期

- **AUD-88（P2，隔离 worker 与浏览器登录态边界）：** `BrowserCapture` 当前将 profile 保存在调用方用户的数据目录并跨运行持久化；目标 worker 使用独立 SID，不能直接假定能读写此 profile。多个 lease 共享 profile 会共享认证状态，项目也没有 cookie/profile 的保护、交接、撤销或并发锁契约。当前 `LOGIN_REQUIRED` 会快速失败并关闭 capture，没有等待用户在可见窗口登录并继续任务的交互路径。
- **建议对策：** V1 每个 lease 使用临时独立 profile；在可见的授权浏览器中由用户手动登录，提供明确暂停/恢复步骤，lease 结束时关闭完整进程树并清理 profile。跨 lease 持久登录态须另行设计并验收；不要复制 cookie。
- **验证与状态：** 该发现来自只读代码审计，未运行测试。P2/AUD-88 保持 **OPEN / NOT PASSED**；P2 profile 生命周期、登录续用和可见 worker 启动仍未验收。

## 135. 2026-10-11 IPC 结果绑定、Skill CI 覆盖与当前回归

- **AUD-89（P2，响应未绑定请求配额）：** 原 `decode_capture_result()` 仅按全局 512 MiB/4 小时上限校验结果；函数文档要求调用方自行核对 request ID，但 API 没有接收对应请求，也无法检查某个请求更严格的 `max_media_bytes` 与时长上限。失配或超请求配额的 worker 结果可能被普通调用方误认作本次任务结果。
- **修复：** `decode_capture_result(frame, request)` 现在必须接收并验证原始请求，拒绝不匹配 request ID；成功媒体的字节数、媒体时长和（若有）视频时长均不得超过该请求配额。`tests/unit/test_capture_ipc.py` 覆盖错配 ID、超字节数和超时长。
- **AUD-90（P5，CI 未验证 repo-scoped Skill 入口）：** CI 原来只对 canonical `skills/douyin-transcript` 运行 Agent Skills validator，未覆盖 `.codex/skills/douyin-transcript`。现在增加独立 validator 步骤；本地锁定环境下两个入口均验证通过。新 Desktop 会话中的发现和实际调用仍需宿主证据。
- **验证：** 第一次全套运行暴露了 `test_dry_run_parses_input_and_checks_paths_without_creating_them` 仍 monkeypatch 已替换的 `cli.resolve_input`。测试已改为替换 `cli.resolve_direct_input`，该用例单独通过。随后完整套件 **539 passed、24 skipped**（Windows Python 3.11.15，333.89 秒，无失败）。本地全仓 Ruff、两个 `uv.lock --check`、两个 Skill validator、SPDX 2.3 schema、敏感文件扫描和 `git diff --check` 均通过。跳过项包括当前 Windows 主机不支持的 POSIX FIFO、symlink、mode/owner、目录句柄行为；这不等于 Linux/macOS CI 已通过。
- **管理员接入边界：** 用户授权代理自行选择方案，但没有接入管理员主机名、远程管理通道或 elevated session；当前进程仍为普通令牌。授权文本本身不能提升 Windows token 或生成远程连接凭据。本次没有尝试网络扫描、UAC 提权、安装服务或修改宿主 WFP/Firewall；未部署 service，capture 仍 fail closed。
- **其他验收缺口：** P2 仍缺认证 IPC transport、per-lease worker、媒体字节传输、WFP/Chromium 动态证明和三条成功的获授权视频。P4 现有授权样本为 315.907 秒，尚无至少 10 分钟真实样本和人工听审记录。P5 仍需新的 Codex Desktop 会话；P6 仍需所有者决定许可证、发行范围、仓库目标与远端发布授权，并完成平台原生依赖审查、远端 CI 与远端干净安装。
- **总体状态：** AUD-89 修复并由本地测试覆盖，AUD-90 的 CI 配置缺口已补齐；P2/AUD-77/AUD-86/AUD-87/AUD-88、P4/P5/P6 仍开放，项目保持 **NOT READY**。

## 136. 2026-10-11 WFP 预览器当前源码构建复核

- **构建：** 系统标准 .NET 安装目录没有可用 SDK；工作区锁定的 .NET SDK 10.0.401 仍位于用户临时目录。使用该 SDK 对 `native/windows/wfp-policy-plan/WfpPolicyPlan.csproj` 运行 x64 Release `build --no-restore`，当前源码构建成功，**0 warnings、0 errors**。
- **输出复核：** `--plan`、`--filter-plan`、`--layout` 三个命令均输出可解析 JSON，前两个继续标记 `Deployability=not-deployable`。`VerifyFilterPlanArtifact.ps1` 重建并校验检查入库的 filter-plan JSON，摘要仍为 `51bf789b93e250a431b4c0ca756b4b86ad69d0a161a02bb561fd51a2a6553f0d`。
- **范围：** 该项目仍是只读策略预览器：没有 BFE/WFP API 调用、服务入口、安装器或策略写入命令。构建/摘要通过只证明预览源码与固定 artifact 一致，不能证明规则在宿主或 Sandbox 生效，也不提供 per-lease worker、认证 IPC、浏览器网络隔离或回滚能力。未安装/启动服务，未改动 WFP/Firewall。
- **后续：** P2 仍需按 `P2_ISOLATION_DECISION.md` 实现可审查的 service/worker/IPC，随后在可回滚管理员 Win11 环境做动态验收；P2/AUD-77/AUD-86 保持 **OPEN / NOT PASSED**，项目仍 **NOT READY**。

## 137. 2026-10-11 SEC-23 Windows 真实 VBR MP3 解码验收

- **样本构造：** 新增 `test_real_vbr_mp3_is_fully_decoded_and_duration_is_measured`，使用锁定的 PyAV 15.1.0/libmp3lame VBR（qscale）编码器，在 pytest 临时目录生成确定性 8 秒立体声 MP3。样本包含静音、正弦、固定随机种子的噪声与变频片段；没有把媒体文件加入仓库。
- **VBR 证据：** 本机生成样本含 308 个非空音频包，观测到 10 种包尺寸（104–835 字节），最小与最大相差超过 2 倍，确认不是仅有 MP3 padding 导致的一字节抖动。产品 `validate_media_file()` 完整解码文件并测得 8.045714 秒，落在编码延迟容差范围内。
- **回归与状态：** Windows 锁定环境下 `pytest tests/unit/test_p2_downloader.py -k real_vbr_mp3 -q` 为 **1 passed**；目标文件 Ruff 检查通过。加入测试后重跑完整锁定套件，结果 **540 passed、24 skipped**（245.39 秒）；全仓 Ruff 检查通过。24 个跳过项依赖当前 Windows 主机不可用的 POSIX FIFO/权限/目录句柄或文件系统 symlink 能力。
- **范围与对策：** 此结果关闭 SEC-23 “Windows 存在真实 VBR MP3 的合成生成与产品解码测试”这一子项，不代表用户录音、ASR/faster-whisper 对照、其他容器/编解码器或跨平台验收。Linux/macOS 和更多真实媒体格式仍须在原生环境验证；SEC-23 整体保持部分通过。

## 138. 2026-10-11 P2 应用侧 capture client 与媒体流接收切片

- **实现：** 新增 `capture_client.py`，把原始链接封装为有界 IPC 请求；解码结果时绑定同一 request ID 和媒体配额；失败响应映射为不回显链接或 IPC 细节的安全错误；成功媒体通过 `receive_capture_artifact()` 写入私有缓存，并校验声明字节数、SHA-256、chunk 上限、结束边界、deadline 与取消状态。所有 exchange 在成功和失败时关闭，关闭失败会删除本次刚接收的文件。
- **验证：** `tests/unit/test_capture_client.py` 与 `tests/unit/test_capture_ipc.py` 定向回归 **29 passed**；两个新文件 Ruff 通过。Windows Python 3.11.15 全套锁定测试 **554 passed、24 skipped**（245.72 秒）；全仓 Ruff、敏感文件扫描和 `git diff --check` 通过。全套在最后两处 deadline hardening 小改动前启动，新增 deadline/取消边界由之后的定向 29 项回归覆盖。所有 capture client 用例使用合成 transport 和内存媒体，不访问网络或真实服务。
- **边界：** 这是普通应用侧编排接口，不是 authenticated IPC transport。传输实现仍必须验证两端身份、同次 request/result/artifact 绑定、独占 endpoint 访问并能中断超时/取消 I/O；当前仓库没有实现该 transport，也没有将 client 接入 CLI/pipeline。媒体还必须由 pipeline 完整解码验证。无 administrator service、per-lease worker、WFP/Chromium 进程身份或真实视频验收，因此 P2/AUD-77/AUD-86 仍 **OPEN / NOT PASSED**，URL capture 继续 fail closed。
- **管理员访问复核：** 本轮发起的标准 UAC 只读 token helper 未产生完成标记；当前 Codex shell 仍为 medium integrity，未得到可用 elevated process。没有扫描网络寻找主机、接入远程主机、安装服务或修改宿主 WFP/Firewall。

## 139. 2026-10-11 P2 ID-only 解析协议与 pipeline 注入切片

- **实现：** 在 v1 codec 增加独立的 `capture_resolve_request/result` 消息，只返回 1–32 位数字视频 ID，不携带重定向 URL、路径或媒体流。`CaptureServiceClient.resolve_source()` 对请求 ID、失败重试属性、deadline、取消与 exchange close 做校验。`resolved_short_link()` 把 worker ID 绑定到安全的本地任务 URL，避免把短链 query token 写入任务库。
- **Pipeline：** `run_urls()` 可选注入 capture client。短链先调用隔离解析，之后按现有 video ID 创建/认领任务并使用缓存/并发锁；需要下载时由 client 收取 worker artifact，核验返回 video ID、缓存目录边界、媒体解码和时长后才进入 `downloaded` 并开始 ASR。短链与直接链接同 ID 会在完整采集前去重。遇到 ID 不匹配或媒体/目录校验失败会拒绝 ASR，并清理尚未被任务引用的新文件。client 错误代码保持稳定，重试只遵循协议给出的 retryable 标记，并受既有次数和绝对 deadline 限制。
- **验证：** Windows Python 3.11.15 锁定全套 **566 passed、24 skipped**（157.85 秒）；Python 3.12.13 锁定全套 **564 passed、26 skipped**（158.40 秒）。跳过项为当前 Windows 不提供的 POSIX 权限/FIFO/符号链接或目录句柄能力；Python 3.12 另有一项 `av` 未安装跳过。项目 CI Ruff 命令通过；capture IPC schema JSON 语法有效。定向测试使用 fake transport/client 和合成媒体，不产生网络请求、真实 service/WFP 或 Chromium 运行证据；完整套件包含两项重试边界用例。
- **边界：** `CaptureServiceClient` 仍需由宿主注入，仓库无生产接入的 system-default transport、service、worker、安装包或 WFP 动态 policy；§140 的独立 named-pipe 源码原型没有接入 Python `CaptureTransport` 或默认 CLI，`doctor` 仍应报告隔离不可用，现有 broker 继续 fail closed。P2/AUD-77/AUD-86/AUD-87/AUD-88 均保持 **OPEN / NOT PASSED**，项目仍 **NOT READY**。仍须通过真实 Windows service/WFP/Chromium 与 3 个授权视频验收。
- **管理员 host 说明：** 用户授权自主选项，但未提供远程管理员主机名、连接方式或本机可用提升令牌。授权不能产生连接端点或提升当前进程；没有尝试扫描其他主机、绕过 UAC 或修改宿主防火墙。

## 140. 2026-10-11 Windows named-pipe source prototype

- **新增隔离项目：** `native/windows/capture-pipe/` 提供独立 .NET 10 x64 named-pipe host/client 原型。服务端使用 protected DACL（SYSTEM、配置的 service SID、显式 allowlist 用户 SID）和 `PIPE_REJECT_REMOTE_CLIENTS`；固定 endpoint 为 `\\.\pipe\DouyinTranscript.Capture.v1`。连接后 host 读取有界 request，按 pipe API 获取 client PID/session，并通过 `RunAsClient` 读取 OS token；再打开相同 PID 的 process token，要求 User SID、session、logon AuthenticationId 相符后才调用 handler。client 反向检查 server PID/session/token SID，并要求配置的 service SID 与 session（生产预期 0）。进程 image path 仅作诊断，不是信任锚。
- **协议和上限：** JSON payload 字段遵循 capture IPC v1；自定义 transport wrapper 用 4 字节 little-endian 长度前缀包裹请求/结果。媒体流使用每块 4 字节 little-endian 长度（1–65,536 字节）+ 数据，最后用长度 0 结束；双方验证 descriptor 的 request ID、媒体长度、SHA-256 与 EOF。请求帧上限 32 KiB、结果帧 16 KiB、源 URL UTF-8 8 KiB、媒体 512 MiB、并发连接 4；连接 5 秒、服务端请求读取 15 秒、单次完整 exchange 15 分钟。
- **默认安全行为：** 唯一内置 handler 对 capture 与 resolve 请求均返回 `BROWSER_ISOLATION_UNAVAILABLE`，没有成功 worker 实现。named-pipe 自身 framing 未存在于 Python `CaptureTransport` 中；README 明确标注需要适配器，不可把该原型接入现有 Python client 后宣称 transport 已打通。
- **验证：** 使用审核报告此前记录位置的临时 .NET SDK 10.0.401 构建 x64 Release，**0 warnings、0 errors**；`--self-test` PASS，覆盖同进程 OS PID/session/token 配对、默认 fail closed、resolve 响应、超限请求拒绝、U+202E 源 URL 拒绝、133,777 字节多块媒体传输与 SHA-256 校验，以及客户端取消后 worker 收到断连取消。Harness 以当前用户 SID/session 充当测试“服务身份”；这只验证本机管道 API 路径，不是 SCM service SID、Session 0、跨用户 ACL、remote-client flag 动态拦截或安装验收。
- **剩余信任缺口：** 无 SCM service entry/安装器/升级与回滚；无生产 service SID 配置和客户端 SID 管理；允许用户 SID 下的任意进程仍可发起连接，尚无 client executable attestation；无独立 per-lease worker、任务/进程树监督、浏览器、DNS pinning、媒体下载、WFP 策略或 Python named-pipe adapter。媒体源要求可 seek，client 验证失败时调用方须丢弃目标文件。P2/AUD-77/AUD-86/AUD-87/AUD-88 继续 **OPEN / NOT PASSED**，项目仍 **NOT READY**。

## 141. 2026-10-11 native CI 与校对验收边界跟进

- **CI 配置：** 新增独立 Windows GitHub Actions job，使用 pinned `actions/setup-dotnet` v6.0.0 commit，按 `native/windows/capture-pipe/global.json` 安装 .NET SDK 10.0.401，并执行 x64 Release build 和本机 named-pipe `--self-test`。workflow YAML 在本机以 PyYAML 6.0.3 解析成功；当前 checkout 没有 Git remote，因此该 job 尚无远端 CI 运行证据。
- **原型依赖范围：** `CapturePipe.csproj` 无 NuGet `PackageReference`，本机 restore assets 未解析 NuGet package library。该原型不增加第三方 NuGet SBOM package record；若发行包将来携带自包含 .NET runtime 或原生 worker，仍需按实际交付物补齐运行时组件、来源和 notices 审阅。见 `THIRD_PARTY_LICENSE_REVIEW.md`。
- **验收说明修正：** `ACCEPTANCE.md` 已区分 §140 standalone named-pipe prototype 与生产 authenticated service/worker，也将 §§125–140 作为当前 P2 记录范围。`RELEASE_CHECKLIST.md` 保持 P2、管理员、远端 CI 和发行门槛未通过。
- **模型校对边界：** `SKILL.md` 现在要求 `.reviewed.md` 清楚标注“Agent 默认模型做了文本校对/标点整理，但没有逐字对照音视频听审”，保留原始 frontmatter 和文件；历史 P1 sidecar 没有记录是否包含该提示，不能将其算作格式验收。LLM 校对仍是 Agent Skill orchestration，而不是 CLI 内置阶段；新 Desktop 会话验收和人工听审仍未完成。
- **本地验证与修复：** 按 CI 命令重建 x64 Release，结果 **0 warnings / 0 errors**；本机 `--self-test` PASS。首次构建后的敏感文件扫描将 `bin/`、`obj/` 里的生成 DLL/EXE/PDB 当作 Git-visible binary 拒绝；根 `.gitignore` 现排除 .NET build output，重跑扫描通过。workflow YAML 经 PyYAML 6.0.3 解析通过，canonical 与 `.codex` Skill 两入口均通过锁定 Agent Skills validator，`git diff --check` exit 0（仅 CRLF 转换提示）。远端 CI、管理员 WFP/service、P2 三视频、P4 人工听审/长样本、P5 Desktop invocation、项目许可证及发行范围均未关闭。整体仍 **NOT READY**。

## 142. 2026-10-11 named-pipe 首实例、token group 与 Python 适配器

- **首实例保护：** native host 现在先以 `FILE_FLAG_FIRST_PIPE_INSTANCE` 创建首个 server handle，只有服务持有该名称的首实例后才并行创建后续 listener。Harness 用随机 endpoint 模拟先到的同名 pipe，再断言第二次首实例创建返回 `ERROR_ACCESS_DENIED`；这检查本机 API 语义，不替代跨账户/管理员服务竞争验收。
- **服务 SID 属性：** C# peer token 读取改用 `GetTokenInformation(TokenGroups)`，分别保留所有组和 enabled 组；服务 SID 只匹配 User SID 或 `SE_GROUP_ENABLED` 且非 `SE_GROUP_USE_FOR_DENY_ONLY` 的组。Harness 覆盖 enabled、deny-only 和两 flag 并存三种判定。Windows Python adapter 使用相同规则，且要求管道 server PID/session、进程 session、token session 都符合配置的 Session 0，再要求配置 SID 出现在 user/enabled groups 中。
- **Python transport：** 新增 `capture_pipe_windows.py`，适配 native 的四字节 JSON 长度前缀与媒体 block/terminal framing；named-pipe I/O 使用可取消的 overlapped read/write，按不超过 50ms 检查 deadline/cancel，并在释放 `OVERLAPPED` 与 event 前取消、排空未完成 I/O。服务身份验证发生在 URL request frame 发送之前。收到媒体时校验 block 不超过 64 KiB、不超过 descriptor 剩余字节，最后消费零长度终止块并要求 pipe EOF；无媒体响应也要求 EOF。`CaptureServiceClient` 现在把 transport timeout/cancel 映射为稳定错误码。
- **默认行为：** adapter 仅作为显式构造的 transport 存在；当前没有已安装服务、产品 service SID 配置或生产安装包，因此没有将它注入默认 CLI，也未改动 `open_system_broker()` 的 fail-closed 行为。native worker 仍对全部请求返回 `BROWSER_ISOLATION_UNAVAILABLE`。当前没有 per-lease worker、SCM service/installer、WFP、Chromium、媒体网络捕获或服务生命周期。
- **验证：** `.NET 10.0.401` x64 Release build **0 warnings / 0 errors**；native `--self-test` PASS（first-instance、SID flag logic、peer identity、fail-closed、JSON framing、133,777 字节 artifact、digest 与 disconnect cancel）。Windows Python 3.11.15 adapter/client/IPC 定向回归 **50 passed、1 skipped**；跨进程 Python/.NET interop **2 passed**：错误 service SID 被拒绝；当前用户 SID/session 成功收取 artifact；第二用例在真实 pending overlapped read 中发出 cancel，验证 `CancelIoEx` 排空后 Python 调用按 `CANCELLED` 返回。Win32 token P/Invoke 直接读取当前普通进程的 TokenUser/TokenGroups/TokenSessionId 也通过；全仓 Ruff 通过。之前完整锁定套件 **579 passed、26 skipped**（246.51 秒）；本次新增的第二个无配置 interop case 会在默认全套中按预期跳过，完整套件尚未在该测试新增后重跑。互通测试没有连接真实 SCM service，也没有验证 Session 0 服务身份、跨账户 DACL、生产 worker 或 WFP。
- **状态：** 这关闭了源码层的首次管道占用与 deny-only SID 误认缺口，并提供了 Python/native 协议适配切片；不构成 service 身份/ACL、管理员部署、P2 网络隔离或真实 Douyin capture 验收。P2/AUD-77/AUD-86/AUD-87/AUD-88 仍 **OPEN / NOT PASSED**；P4/P5/P6 的证据门槛仍未关闭，项目整体 **NOT READY**。

## 143. 2026-10-11 named-pipe 客户端预认证握手与验收记录同步

- **AUD-91（P2，未认证请求帧先读）：** §140–142 的服务端先读取并解析完整 URL-bearing JSON，再通过 `RunAsClient` 验证 PID、token、session 和 allowlist。可连接的同用户进程因此能在 15 秒请求期限内占用 listener；原顺序还让 URL 在认证之前进入服务端解析。
- **修复：** 加入固定四字节 `DTP1` 请求前导与 `DTA1` 服务端认证确认。服务端在 1 秒 deadline 内仅读取固定前导，随后依据最近一次 pipe read impersonate 客户端，并验证其令牌/进程身份及 user/session allowlist；认证成功后才发送 `DTA1`。符合协议的 C# 与 Python 客户端必须先收到该确认才发送 URL 请求帧，服务端只在认证后读取/解析 JSON，使用独立 15 秒期限。客户端等待确认的期限为 5 秒。绕过协议的恶意客户端仍可写任意管道字节，但未认证正文不会被服务读取/解析并会随连接关闭而丢弃；协议不替代 pipe DACL，也不阻止获准用户下的其他进程连接。
- **本机验证：** .NET 10.0.401 x64 Release build **0 warnings / 0 errors**。`--self-test` PASS，新增拒绝会话仅发送 preamble 后即被关闭且 worker 未调用；四个不发送 preamble 的客户端在 1 秒期限后被清理，随后 listener 可继续服务。C# 和 Python 客户端在发送 JSON 前都等待 DTA1 确认。跨进程 Python/.NET tests **2 passed**（artifact/hash/EOF、错误 service SID 拒绝、取消与排空）；adapter/client/IPC tests **50 passed、1 skipped**。Windows Python 3.11.15 锁定全套 **579 passed、27 skipped**（247.40 秒）；默认运行中的两个 native-host interop tests 因未配置临时测试 host 路径而跳过，并已单独运行通过。全仓 Ruff、敏感文件扫描、两个 Skill 入口验证、两处 lock 检查均通过；`git diff --check` exit 0，只有工作树文件的 LF/CRLF 转换提示。
- **P4 侧车检查：** 对私有输出做仅报告结构的检查后，确认历史 `.reviewed.md` 缺少规定的模型校对/未逐字听审提示。依据 Skill 不覆盖规则，另存编号 reviewed sibling，仅更换范围提示，未改动逐字稿正文；脚本确认 raw SHA-256 未变、frontmatter 一致、提示存在、中文标点与段落存在。此项不构成真实听审、10 分钟运行或事实校验。
- **文档对账：** `ACCEPTANCE.md`、`P2_REPORT.md`、`RELEASE_CHECKLIST.md` 与 `RELEASE_REPORT.md` 同步到 §143，标明 adapter/互通原型已有本地证据，默认 CLI/service/WFP 仍未实现，CI 配置尚无远端运行结果。P6 无根 LICENSE、无 Git remote、所有者发行决定和 native 来源/许可待处理；P5 仍需新 Desktop 会话验收。
- **权限与状态：** 当前进程权限复核为 `IsAdministrator=false`、`IsSystem=false`；用户授权不会创建 OS 管理员令牌，当前也没有管理员主机名或连接通道可用。没有安装宿主服务或更改 WFP/Firewall。AUD-91 的服务端请求读取顺序已在源码层修复并本机验证；P2/AUD-77/AUD-86/AUD-87/AUD-88 仍 **OPEN / NOT PASSED**，管理员服务、per-lease worker、WFP、Chromium 与三条成功媒体仍未验收；P4/P5/P6 未关闭，项目整体 **NOT READY**。

## 144. 2026-10-11 Python 3.12、native interop 与 checker 环境隔离复测

- **完整 Python 回归：** 在仓库外的 Python 3.12.13 环境按 `skills/douyin-transcript/uv.lock` 同步全部 extras/groups 后运行完整树，第一次 574 passed、28 skipped、4 failed。四项失败都属于 SPDX checker 的子项目启动：父测试进程设置的 `UV_PROJECT_ENVIRONMENT` 被 `uv run --project tools/spdx-schema-check --no-sync` 继承，令它用主应用临时环境而非已锁定 checker 环境；错误为缺少 `jsonschema`，与 checker 断言无关。为确认全套产品代码，当次隔离环境补入锁定 `jsonschema==4.25.1` 及锁定依赖后，当前树全套 **578 passed、28 skipped**（343.55 秒）。
- **测试 helper 修正与独立复核：** `tests/unit/test_spdx_schema.py` 现在让子进程使用 `DOUYIN_SPDX_SCHEMA_TEST_ENV` 指定的 checker 环境；未指定时移除父级 `UV_PROJECT_ENVIRONMENT`，由 uv 按工具项目路径选取其 `.venv`。单独以锁定的 Python 3.12 checker 环境重跑四项，结果 **4 passed**（3.71 秒）。主项目 lock 和 checker lock 均未修改。
- **Python/.NET interop：** 以隔离临时副本构建当前 native capture-pipe 源码，.NET SDK 10.0.401 x64 Release 为 **0 warnings、0 errors**。在 Python 3.12.13 下补跑默认跳过的两项跨进程用例，**2 passed**：校验 artifact hash/EOF、错误服务 SID 拒绝、取消并排空 overlapped I/O。测试身份仍是当前普通用户 SID/session，不涉及安装服务、Session 0、WFP、Chromium 或真实视频。
- **边界：** 28 项跳过覆盖 Windows 不支持的 POSIX 权限、FIFO、目录句柄、symlink/junction 行为，以及显式配置的 native host 用例（后者已单独补跑）。checker helper 的修正只影响测试子进程环境选择。P2 仍无生产 service/worker/WFP/Chromium/真实视频验收，P4/P5/P6 继续开放，项目整体 **NOT READY**。

## 145. 2026-10-11 NumPy 锁定 wheel 许可文件覆盖

- **发行物身份：** 从 `uv.lock` 读取全部 40 个 NumPy wheel（2.4.6 共 29 个，2.5.3 共 11 个），从官方 `files.pythonhosted.org` 下载到独立临时目录。40 个文件合计 508,969,989 bytes；每个文件的字节数和 SHA-256 均与锁记录一致。没有安装或解压 wheel。锁定文件哈希见 `skills/douyin-transcript/uv.lock`，简表与结论见 `docs/NUMPY_WHEEL_LICENSE_REVIEW.md`。
- **归档内容：** 成员扫描读取 43,630 个 ZIP 条目。每个 wheel 的 METADATA 均有相同有效 `License-Expression`：`BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`。每个 wheel 有 20 个 license/notice 文件名候选；共 800 个成员，其压缩归档内大小、SHA-256 与各自 `RECORD` 行全部一致。`docs/numpy-wheel-license-evidence.jsonl` 保存 800 行；文件 SHA-256 为 `0bf010302e664ffec7a1eb15feea2629b46c1b30f5365d879cd7efd94cef96f9`。每行绑定 lock SHA、wheel URL/hash/size、metadata hash、member 路径/size/hash、归一化文本 hash 和 RECORD 校验结果。
- **文本一致性：** 对换行归一并去除版本化 `.dist-info/licenses/` 前缀后，800 个成员映射到 18 个候选路径。17 个路径在全部版本、OS、架构和 CPython/PyPy wheel 中只有一个文本哈希；唯一差异路径是顶层 `LICENSE.txt`，存在 macOS、Linux、Windows 三种平台文本，每种文本在两个版本和该平台所有目标中一致。这为先前抽查的许可证文本补齐其余锁定 wheel 的字节完整性覆盖，不解释其法律适用范围。
- **离线 SPDX 闭环：** 将 40 个 wheel 身份及 800 个候选成员加入 `docs/third-party-license-evidence.json`，由项目自带离线 verifier 重新校验：**41 packages, 94 artifacts, 41 metadata, 9 license, 2 notice, 863 supplemental members**。随后根据当前 lock/evidence 重新生成 `docs/third-party-sbom.spdx.json`（121 个 package records、137 个 relationships）；固定 SPDX 2.3 schema 校验通过。所有 `licenseDeclared` 保持原值，所有 `licenseConcluded` 仍为 `NOASSERTION`。
- **未关闭项：** 归档哈希和 RECORD 完整性不等于完整组件 BOM、二进制链接关系或来源证明。GCC/libquadmath notice 到精确二进制/链接输入的映射、NCSA alternative expression、SplitMix64 dedication、项目 LICENSE、拟发行依赖范围和 owner 批准仍待处理。Linux/macOS 远端 CI、P2 管理服务/worker/WFP/Chromium 及三条真实媒体、P4 听审、P5 新 Desktop 会话均未完成；项目仍 **NOT READY FOR RELEASE**。

## 146. 2026-10-11 Renewed administrator authorization and available-host check

- **授权与主机事实：** 用户再次授权代理自行选择方案并操作。当前工作区仍运行于 `local-machine\local-user` 的交互式 Windows 11 Enterprise LTSC 会话；本轮通过当前进程身份检查得到 `IsAdministrator=false`、`IsSystem=false`、session 1。`wsb.exe` 可用，但 `wsb list --raw` 返回空环境列表；没有提供或配置远程管理员主机名、WinRM/SSH/RDP 工作区或其他已授权连接端点。此授权不会创建管理员 token、远程主机地址或凭据。
- **边界动作：** 没有扫描局域网、触发 UAC/凭据输入、尝试绕过权限边界、安装服务或更改宿主 WFP/Windows Firewall。没有启动新的 Sandbox：既有 guest-only WFP 探针已经覆盖了所需的有限动态规则机制，重复运行不能补足产品 service/worker 信任边界。
- **代码与验收判断：** `native/windows/capture-pipe/` 仍是 source prototype，唯一内置 worker fail closed；仓库没有 SCM service entry、安装/回滚、per-lease OS identity provider 或受监督 worker，也没有 WFP 写策略 service。仅添加 Job Object 或在同一普通用户 token 下拉起子进程，不能证明 lease SID 隔离、WFP 的每 lease egress 或 worker-owned DNS/upstream；把它接进默认捕获路径会制造虚假的安全保证。故本轮不加入这种未接 identity provider 的占位 supervisor，URL capture 继续 fail closed。
- **对策与状态：** 下一步必须在项目实现 review 后，接入真实 Windows 11 x64 管理员 service 环境，提供受保护的 per-lease token/identity provider 与 worker executable，再实现 suspended launch、独立核验目标 token、限制继承句柄和无 breakaway 的 Job Object 生命周期。随后才可在 disposable/rollback-capable 环境做跨 lease、DNS/upstream socket 归属、IPv4/IPv6/UDP 与故障清理验收。当前可继续的仓库内工作是实现并审阅 service/worker 源码和失败关闭默认值；不能把 guest SYSTEM 冒充宿主管理员或生产 service。P2/AUD-77/AUD-86/AUD-87/AUD-88 保持 **OPEN / NOT PASSED**，P4/P5/P6 外部验收项仍开放，项目整体 **NOT READY**。

## 147. 2026-10-11 NumPy 原生 wheel 成员与 RECORD 交叉核验

- **新增可复现工具：** `scripts/inventory_numpy_native_members.py` 只读取 SHA-256 缓存中的归档，不下载或安装 wheel，也不把归档成员解压到磁盘。对 `uv.lock` 中全部 40 个 NumPy wheel，检查文件大小与 SHA-256，再流式解压候选成员以计算 native-file 哈希，并与该 wheel 的 `RECORD` 路径、大小和 SHA-256 对照。运行命令为 `python scripts/inventory_numpy_native_members.py --lock skills/douyin-transcript/uv.lock --cache-dir <sha256-keyed-wheel-cache> --output docs/numpy-native-member-evidence.jsonl`。
- **结果：** 共 1,130 个成员，未压缩成员大小合计 1,209,167,565 bytes，覆盖 Windows `win32`/`win_amd64`/`win_arm64` 10 个 wheel、macOS 16 个、manylinux 8 个和 musllinux 6 个；全部逐条与所属 RECORD 一致。JSONL 的 SHA-256 为 `69b43a4fe83282af8a856890308f964308edecc636c520c84fc7dae514cd717e`。它把成员路径、内容哈希、所属锁定 wheel 哈希及 RECORD 校验状态固定在仓库内。
- **观察到的归档成员：** 有 `libgfortran` 名称的文件出现在 8 个 manylinux、6 个 musllinux 和 8 个 macOS wheel；`libquadmath` 名称出现在 4 个 manylinux x86-64、3 个 musllinux x86-64 和 8 个 macOS wheel；`libgcc_s` 名称出现在 6 个 musllinux 和 8 个 macOS wheel。OpenBLAS 名称成员出现在 29 个 wheel，覆盖 Windows x64/arm64、macOS、manylinux 与 musllinux。此为归档成员存在性证据，不能证明程序实际导入/加载/链接了哪个文件，也不推断其适用许可证。
- **文档同步与剩余项：** 结果和审查边界同步到 `docs/NUMPY_WHEEL_LICENSE_REVIEW.md`、`docs/THIRD_PARTY_LICENSE_REVIEW.md` 与 `docs/ACCEPTANCE.md`。脚本和清单不能替代二进制 import/link map、构建配置、制品来源证明或适格人员的许可适用性审查；NCSA alternative、SplitMix64 dedication、发行范围、项目 LICENSE 与 owner decision 仍开放。P6 继续 **NOT READY**；P2 管理员 service/WFP/浏览器验收、P4 人工听审、P5 新 Desktop 会话也仍未关闭，整体 **NOT READY**。

## 149. 2026-10-11 NumPy 原生索引器缓存替换竞态修复

- **AUD-92（P6，证据快照绑定）：** §147 脚本先以一个文件句柄校验 SHA-256，关闭句柄后再按缓存路径重新打开 wheel 解析 ZIP。并发替换或原地改写缓存对象可使后续成员来自与已校验摘要不同的字节，虽然本次保留的清单和归档数据一致，代码本身仍未严格保证绑定关系。
- **修复：** 索引器现在先检查路径/文件身份，再从同一身份核验的文件句柄将 wheel 复制到临时快照，并在复制过程中计算大小及 SHA-256。只有快照匹配 `uv.lock` 后才使用该同一快照解析 ZIP；复制字节数有锁定大小和 512 MiB 上限。这样缓存路径在后续阶段被替换不再影响扫描内容。归档成员仍以流方式解压读取来做哈希，不落盘提取成员。
- **范围：** `docs/numpy-native-member-evidence.jsonl` 的内容与 wheel/RECORD 记录未更改；该修复强化可复现工具的读取原子性，不改变许可适用性结论、native linkage/provenance 缺口或发布状态。旧清单没有发现被替换或损坏迹象。固定证据仍不是完整 native BOM，P6 继续 **NOT READY**。
- **验证：** `python -m py_compile scripts/inventory_numpy_native_members.py` 通过；锁定 Ruff 对脚本检查通过。使用已有本地缓存重新扫描 40 个锁定 wheel，输出仍为 1,130 个成员；新生成 JSONL 与已保存清单逐字节一致，SHA-256 仍为 `69b43a4fe83282af8a856890308f964308edecc636c520c84fc7dae514cd717e`。未下载或安装 wheel，未运行测试套件；全套测试仍以 §§143–144 为最近记录，未因本修复重跑。

## 150. 2026-10-11 默认 URL pipeline 的隔离服务门禁

- **AUD-93（P2，默认入口保留调用方浏览器回退）：** 虽然 CLI 没有注入 service client，`run_urls()` 仍保留 `capture_service_client is None` 时调用 `BrowserCapture` 并把下载提交给普通本地 downloader 的生产分支。如果将来仅让 broker 返回 lease，这会重新让 CLI 在调用方进程启动浏览器，不符合完整作业 worker 的目标边界。
- **修复：** 默认 `BrowserCapture` factory 且未提供 full-job service client 时，`run_urls()` 立即为每个输入返回 `BROWSER_ISOLATION_UNAVAILABLE`，发生在 URL resolver、任务 store、browser profile、Playwright 或 downloader 之前。空批次仍返回空结果。显式注入自定义 capture factory 仍可访问旧路径；现有测试使用该接缝，但它不属于支持的生产隔离接口，旧路径尚未从模块/API 完全移除。
- **范围与剩余风险：** 默认 CLI URL capture 更早 fail closed；没有接入服务、身份提供器、worker、WFP、浏览器或网络，也未声称 P2 通过。完整消除风险仍需移除 legacy caller-side browser/downloader 分支及旧 `IsolationLease` endpoint/identity 形式，并把生产入口限制为经过认证的完整作业 client。三条真实媒体与进程级隔离动态验收仍开放。
- **验证：** 对修改模块执行 `python -m py_compile` 和锁定 Ruff 静态检查；未运行测试套件。不要把该门禁或测试 seam 当作实际隔离证明。P2/AUD-77/AUD-86/AUD-87/AUD-88/AUD-93 仍 **OPEN / NOT PASSED**。

## 151. 2026-10-11 移除调用方 URL 浏览器与下载回退

- **AUD-93 完成：** `TranscriptionPipeline.__init__()` 不再接受 `capture_factory`、caller-side downloader 或 `url_resolver`。`run_urls()` 对非空批次先要求完整作业 `CaptureServiceClient`；缺 client 时逐项返回 `BROWSER_ISOLATION_UNAVAILABLE`，早于 direct URL 解析、stale-task recovery、TaskStore、browser profile 或 downloader。短链解析和完整媒体采集均通过该 client。`BrowserCapture` 与旧 lease 模块仍存在于代码树，但产品 pipeline 不再引用它们；CLI 仍无已验证的 service client。
- **顺带修复与回归：** 默认标题缺失时以 service 返回的标题落库，后续重复提交仍返回该标题；短链解析现在接收 deadline 和取消回调，Ctrl+C 会取消并释放处理；错误映射继续保留 `PROCESSING_TIMEOUT`、`MEDIA_INCOMPLETE` 和 `MediaInvalidError` 专用提示。恢复了三个真实子进程硬退出/重启用例，覆盖 `downloaded`、`transcribing`、`writing` 已提交状态，确认复用一次 capture/media transfer 并产出通过完整性检查的 Markdown。CLI 的 retry-failed 短链解析失败用例改用隔离 client 替身，不再传旧 `url_resolver`。
- **验证：** Windows Python 3.11.15 锁定全套 **579 passed、27 skipped**（159.25 秒，无失败）。两个 native interop host 未配置，相关 2 项按预期跳过；其余跳过项依赖 POSIX FIFO/权限/目录句柄或当前文件系统不支持的符号链接。全仓锁定 Ruff、`uv lock --check`、`py_compile`、敏感文件扫描和 `git diff --check` 通过；源码扫描未在 `pipeline.py` 找到 `BrowserCapture`、`capture_factory`、`url_resolver`、`download_media` 或 legacy caller-side helper 的引用。
- **权限与状态边界：** 当前 `local-machine\local-user` 进程 `IsAdministrator=false`、`IsSystem=false`，虽在 Administrators 组但该组于 token 中是 deny-only，完整性级别为 Medium；没有可接入管理员主机或 broker endpoint。此前标准 UAC 探针已被执行器在进程创建前拦截，不通过其他启动通道绕过。没有安装 service 或更改宿主 WFP/Firewall。P2 仍缺生产 service/worker、认证 IPC/SID、WFP egress、Chromium 身份与三条成功授权视频；P4/P5/P6 门槛仍开放，整体 **NOT READY**。

## 148. 2026-10-11 UAC 身份只读自检被执行器拦截

- **尝试范围：** 用户再次授权自主处理管理员门槛后，只尝试以标准 `Start-Process -Verb RunAs` 启动一个只读身份探针，不包含服务安装、防火墙/WFP 命令或其他宿主修改。
- **执行结果：** 执行器在创建子进程前返回 `CreateProcess ... Rejected ... blocked by policy`。未启动探针，未出现 UAC/凭据界面，因此本轮无法取得管理员令牌，也没有任何宿主状态改变。这与 2026-10-10 曾在不同调用上下文成功的一次隐藏只读检查不同；先前高完整性子进程不向当前会话传递权限。
- **对策与边界：** 不通过替代引号、脚本宿主或其他启动通道规避该执行器拦截。P2 必须在管理员令牌可用的工作区继续 service/WFP 动态实现；当前用户授权无法覆盖执行器策略。可以继续的仓库内静态工作不应冒充管理员验收，URL 捕获仍 fail closed。P2/AUD-77/AUD-86/AUD-87/AUD-88 保持 **OPEN / NOT PASSED**，整体仍 **NOT READY**。

## 152. 2026-10-11 P4 侧车写入守卫、P6 证据复放与双版本回归

- **P4 侧车入口：** 新增 `douyin-transcript review-sidecar --raw-file PATH`，从 stdin 读取仅含 `reviewed_body` 的 JSON；不会调用模型或回显正文，只返回侧车状态和路径。读取时复用 `open_private_regular_file()` 对已核验文件句柄做有界读取，拒绝共享/非普通文件和 symlink/reparse；发布前再次检查父目录私密性。保存时保留原稿与 frontmatter/标题/章节框架，换成“当前 Agent 默认模型文本校对、未经逐字听审”的范围提示，转义 Markdown，要求中文句读标点且 300 字以上正文需空行分段，并以原子 no-replace 方式选择未占用的 `.reviewed.md` sibling。合成用例覆盖保留/不覆盖、输入正文不回显、目录隐私和格式拒绝；这不证明模型真正审阅过稿件，也不证明声学准确性。
- **P4/P5 限制：** 本轮没有打开或读取任何私有转写正文。新 helper 只改善安全保存和格式检查；10 分钟以上授权样本、至少三处人工听审、默认模型数据流以及新 Desktop 会话发现/调用仍未验收，P4/P5 继续未通过。
- **P2 源码与权限复核：** `native/windows/capture-pipe` 仍只有测试/interop 入口，`FailClosedCaptureWorker` 对生产捕获请求均返回隔离不可用；没有 SCM service/installer、per-lease 身份提供器/worker、受监督 Chromium、DNS/IP pinning 或 WFP 实施。pipeline 在无完整作业 client 时 fail closed。当前会话为 Medium integrity，`IsAdministrator=false`、`IsSystem=false`，也没有管理员主机连接端点；用户授权本身不会提供 OS token 或接入方式。没有尝试替代提权通道、没有安装 service 或更改宿主 WFP/Firewall。P2/AUD-77/AUD-86/AUD-87/AUD-88/AUD-93 继续 **OPEN / NOT PASSED**。
- **P6 本机证据复核：** 修正 `THIRD_PARTY_LICENSE_REVIEW.md` 中把 §124 的 54 artifact/63 supplemental 历史快照写成当前计数的歧义。离线 evidence verifier 当前通过 **41 packages、94 artifacts、41 metadata、9 license、2 notice、863 supplemental members**；使用原始 ISO creation timestamp 重生成 SBOM，与 121 package records/137 relationships 的已存文件逐字节一致；40 个 NumPy wheels 的 1,130-row member index 复放与保留哈希一致。SPDX schema 校验通过。通用成员索引尝试因触及 2 GiB 解压预算而按设计停止，没有放宽上限。以上不证明完整 native BOM、链接关系、来源或许可适用性；项目 LICENSE/发行范围/仓库归属与可见性仍待所有者决定，Git remote 为空，也没有远端 CI 或干净安装证据。
- **验证：** 当前 Windows 工作树全套测试：Python 3.11.15 **584 passed、29 skipped**（249.22 秒）；Python 3.12.13 **583 passed、30 skipped**（243.44 秒）。两版均无失败；跳过项为 POSIX 专属文件系统行为、未配置 native interop host，另 3.12 基础环境没有可选 PyAV。当前树的离线干净 Skill 副本安装、两个 `uv lock --check`、全仓 Ruff、敏感文件扫描、canonical/`.codex` Skill validator、SPDX 2.3 schema 和 `git diff --check` 均通过。该本机验证不等同于 Linux/macOS/远端 CI、管理员隔离或发布提交验收。
- **整体状态：** P1 与 P3 本地证据保留通过；P2/P4/P5/P6 及最终发布门槛仍开放，整体继续 **NOT READY**。

## 153. 2026-10-11 P4 侧车 JSON 输入边界与 P2 启动门槛复核

- **AUD-94（P4，重复 JSON 键产生歧义）：** `review-sidecar` 原先用默认 `json.loads()` 解析 stdin，重复的 `reviewed_body` 键会静默采用最后一个值；调用方看到的是单字段对象，但输入实际上存在冲突。
- **AUD-95（P4，Windows stdin 代码页错读 UTF-8）：** CLI 原先读取 `sys.stdin` 文本流，Windows 的文本包装器可能按系统代码页而非 Skill 示例要求的 UTF-8 解码中文正文，造成乱码后写入侧车。
- **AUD-96（P4，合法非 BMP 正文被错误拒绝）：** 输入字符上限按正文上限的 6 倍计算；`ensure_ascii=True` 下每个非 BMP 字符可编码为 12 个 JSON ASCII 字符，因此不超过正文 100 万字符上限的有效稿件可能在 JSON 层被拒。
- **修复：** 侧车现在从二进制 stdin 有界读取，按严格 UTF-8 解码，采用 12× 正文字符上限加 1,024 字节 framing 空间；仅用于测试/进程内调用的文本流回退也先做严格 UTF-8 编码并按字节核限。JSON `object_pairs_hook` 拒绝所有对象中的重复键，深层输入触发的 `RecursionError` 作为无效 JSON 安全处理。Skill 与 CLI 文档说明 UTF-8、字节限制和重复键行为。Raw Markdown 读取、父目录隐私校验、frontmatter 保留及原子不覆盖写入逻辑未改。
- **回归：** 新增重复键拒绝、UTF-8 中文独立解码、非法 UTF-8 拒绝及 100 万字符非 BMP 极限正文接收测试。Windows Python 3.12.13 当前树全套 **587 passed、30 skipped**（249.66 秒）；`ruff check .` 通过，本次两个 Python 文件 `ruff format --check` 通过。全树 format 检查另报告 47 个未由本次修改的文件需重新格式化；为避免无关大面积改写未运行全树 formatter。跳过项为 POSIX/Windows 文件系统能力、未配置 native interop host 和本环境缺少可选 PyAV。Python 3.11 的最近全套仍是 §152 的 584/29；尚未在本次改动后重跑 3.11。
- **P2 可实现性复核：** 未发现能在当前权限与验收条件下真实推进生产 per-lease 隔离的安全代码切片。现有 AppContainer Chromium 原型在 Crashpad 命名管道遇到 access denied，后续进程初始化失败于 ProcessSingleton；低权限用户 SID 原型也遇到命名对象 ACL/ProcessSingleton 问题。生产树仍无 SCM 服务入口、身份提供器、受监督 worker、WFP 策略写入或 service client，唯一生产 worker继续 fail closed。下一步应先在可回滚管理员环境证明明确租户身份可以启动锁定 Chromium/headless 页面，并记录 browser、renderer、utility 子进程 token/SID；再依据通过的身份设计 service、进程树监督与 WFP 绑定。没有改动活动 Sandbox、宿主 WFP/Firewall 或网络策略。
- **自动审计能力限制：** 本会话的托管 Deep Scan 无法启动，工具返回缺少 managed filesystem permission profile；本节结论来自定向源码审查与本地回归，不把它表述为全仓自动安全扫描通过。
- **未关闭的验收项：** P4 仍缺 10 分钟以上真实样本、至少三处人工听审及新 Desktop 默认模型端到端调用；P2 缺生产管理员服务/隔离身份与动态网络证据；P5 缺新 Desktop 会话发现/调用；P6 缺项目许可证、发行范围、仓库归属决定及远端 CI/安装。整体仍为 **NOT READY**。

## 154. 2026-10-11 P4 长无标点片段检查与文档快照对账

- **AUD-97（P4，存在一个标点即可通过）：** `review-sidecar` 原来的格式检查只要求全文至少含一个中文标点；一段长文即使只有一个逗号、其余连续 1,000 字没有标点，仍可能写入 reviewed sibling。这无法满足“不要一段下来没有任何标点”的可读性要求。
- **修复：** Markdown sidecar writer 现在逐段检查，超过 160 个字符的连续无标点片段会拒绝写入并要求 Agent 再整理；逗号、句号、问号、冒号、顿号和常见 ASCII 标点作为断点。Skill 增加保存前最后一轮标点检查指引，CLI Reference 说明 160 字符限制。该启发式只设可读性下限，不自动插入标点或判断语义。
- **回归：** 新增“长无标点片段在句尾前已有一个逗号仍拒绝”的合成测试。P4 定向组 **10 passed、2 skipped**；两个跳过项分别依赖 Windows 文件系统未提供的 symlink 与 POSIX mode bits。Windows Python 3.12.13 当前树全套 **588 passed、30 skipped**（162.67 秒）。Python 3.11.15 当前树 `test_markdown.py` 与 `test_cli.py` 定向组 **102 passed、4 skipped**（161.47 秒）。
- **文档一致性复核：** 独立 P6 audit 曾发现 `RELEASE_CHECKLIST.md`、`RELEASE_REPORT.md` 与根 `README.md` 的当前快照指针落后；已将主要发布/验收入口同步到 §§154–155 和当前可复现结果，历史章节仍保留为历史证据。当前仍无根 `LICENSE`、Git remote、远端 CI 或干净安装；所有者选择和 native 来源/适用性审查仍未闭合。
- **状态：** P2/P4/P5/P6 及发布门槛保持 **OPEN / NOT READY**；本次只推进 P4 格式检查和静态文档一致性，不声称模型审阅质量、长样本听审或端到端 Desktop 调用已验证。

## 155. 2026-10-11 Python 3.11 验证边界与发布入口同步

- **AUD-98（验证证据不完整）：** 多次尝试在当前树上运行 Python 3.11.15 全套时，执行只返回部分进度输出（曾见失败标记），没有 pytest 最终汇总；因而不能据此判定全套通过、失败数量或失败原因，也不覆盖 §152 的最近完整结果。针对性复跑 `tests/unit/test_markdown.py` 与 `tests/unit/test_cli.py` 为 **102 passed、4 skipped**（161.47 秒），确认 P4 本轮主要代码路径在 Python 3.11 上可通过。需要在可保留完整进程输出的环境中重跑全套并保留完整 pytest/JUnit 汇总，再处理任何具体失败；在此之前 Python 3.11 当前树全套保持 **未验收**。
- **其他本地检查：** Python 3.12.13 当前树全套 **588 passed、30 skipped**（162.67 秒）；`ruff check .`、修改的 `markdown.py` 与 `test_markdown.py` 格式检查、敏感文件扫描、canonical Skill 与 `.codex` Skill 的 `agentskills validate`、`uv lock --check --project skills/douyin-transcript`、`git diff --check` 及使用 `tools/spdx-schema-check/uv.lock` 的 SPDX 2.3 schema 检查均通过。`git diff --check` 仅有既有 LF/CRLF 转换提示。
- **文档快照同步：** `README.md`、`ACCEPTANCE.md`、`RELEASE_CHECKLIST.md`、`RELEASE_REPORT.md` 和 `PROJECT_REMEDIATION_PLAN.md` 的当前状态入口已指向 §154/§155 与真实测试证据；旧章节记录保留为历史。根 README 的本地回归行不再把 §132 的历史快照当成当前状态。
- **状态：** Python 3.11 完整回归、P2 管理员 service/WFP/worker 与真实视频、P4 长样本听审/新 Desktop 调用、P6 所有者决策/远端发布验收仍开放。该证据缺口不改变 **NOT READY** 结论。

## 156. 2026-10-11 P2 多容器解码回归与 Python 3.11 证据边界

- **AUD-99（媒体容器覆盖）：** 既有合成媒体回归覆盖了纯音频 WAV 与 VBR MP3；缺少带视频流的常见 MP4 容器样例，无法证明验证器会选择并完整解码音频流、而非仅靠容器声明的时长通过。
- **回归：** `tests/unit/test_p2_downloader.py` 新增完全合成的 MP4/MPEG-4 视频 + AAC 音频样本，先确认文件同时含有音视频流，再调用真实 PyAV 解码路径并校验时长；既有 VBR MP3 回归也在锁定编码器环境中运行。该组在 Python 3.12.13 + 锁定 ASR extras 下 **57 passed、1 skipped**（94.82 秒）。测试不访问网络、不读取用户媒体，不代表真实平台媒体或生产捕获成功。
- **当前整套回归：** Windows Python 3.12.13 当前树全套 **590 passed、29 skipped**（341.06 秒），无失败；与前一快照 588/30 的差异来自新增媒体用例通过、可选 PyAV 测试不再跳过。29 个跳过项仍包括平台不支持的 POSIX 文件系统能力和未配置路径的 native interop host。锁定 `av==15.1.0`、NumPy 与 ASR/dev 依赖安装于现有 3.12 项目 venv；没有下载模型权重。
- **Python 3.11 边界：** 单独审计 venv 按锁文件同步了 ASR/dev extras；`test_download_streams_to_hashed_atomic_file_and_reuses_verified_cache` **1 passed**（90.35 秒）、新 MP4/AAC 回归 **1 passed**（91.16 秒），另一个单独的 `test_module_check_reports_import_error_as_broken` **1 passed**（90.91 秒）。显式传入 `--basetemp` 的一次全树运行绕过 `tests/conftest.py` 为 Windows 选择私有临时根的逻辑，在 442/619 项后以 `KeyboardInterrupt` 结束，pytest/JUnit 记录为 129 failed、298 passed、15 skipped；权限拒绝集中源于不安全临时根，且当时审计 venv 未安装锁定 ASR extras，故该运行不能计作产品失败或有效套件结论。撤掉 `--basetemp` 后的默认根运行约 120 秒时结束，没有 pytest 汇总或 JUnit。当前树 Python 3.11 全套继续标为 **UNVERIFIED**，最近有效完整结果仍是 §152 的 584 passed、29 skipped；§155 的 Markdown/CLI 定向组 102/4 仍是其余最新定向证据。
- **发布与验收状态：** P2 生产 service/per-lease worker/WFP/Chromium identity 和三条授权视频仍未验收；P4 长样本人工听审与新 Desktop 默认模型调用、P5 新会话调用、P6 所有者决定及远端 CI/安装也仍开放。没有管理员 endpoint 或提升后的 OS token；没有安装系统服务、扫描网络或更改宿主 WFP/Firewall。总体 **NOT READY**。

## 157. 2026-10-11 P2/P4/P6 复核与 Python 3.11 定向证据

- **P2 管理员环境与可实现性复核：** 用户再次授权代理自行选择方案；本机仍是普通 Windows 交互令牌，没有管理员主机地址、可达 broker 或管理员令牌。本轮未触发 UAC、扫描网络、安装服务或修改 WFP/Firewall。源码复核确认：`pipeline.py` 在没有完整作业 client 时对 URL 批次 fail closed；`CaptureWorker.cs` 对全部请求返回隔离不可用；`Program.cs` 只有原型/interop 入口；`open_system_broker()` 固定不可用。当前安全边界正确阻止未隔离捕获，但 P2 生产功能尚不存在。下一步应在可回滚的管理员 Win11 x64 环境先证明锁定 Chromium 在目标低权限身份下启动并记录 browser/renderer/utility token，再实现 SCM service、每 lease 身份和受监督 worker、worker 自有 DNS/IP 固定、WFP 出口规则、安装/回滚，最后验证多 lease、失败清理、IPv4/IPv6/TCP/UDP/WebRTC/DNS 阻断与三条授权真实视频。单纯同用户子进程或孤立 Job Object 不足以关闭边界。
- **Python 3.11 测试诊断：** 独立诊断将 pytest 8.4.2 `tmp_path` 首次 setup 的 31–91 秒波动定位到 `_pytest.pathlib._force_symlink()` 更新的可选 `current` 符号链接；普通临时目录创建和项目 ACL hook 均为毫秒级。审核 launcher 仅跳过 pytest 这个 best-effort 指针更新，独立 `tmp_path` 目录和产品符号链接测试仍保留。最初的临时 launcher 遗漏 Windows multiprocessing `__main__` 守卫，会让 spawn 子进程递归调用 pytest；该次完整运行及其失败标记无效。加守卫后，Windows socket-handoff 子进程用例和 downloader 原子缓存 smoke **2 passed**（0.74 秒）；当前 `tests/unit/test_p2_downloader.py` 全组 **57 passed、1 skipped**（33.87 秒）。另一次 guarded 全树运行仍在 58% 前后结束，未产生 pytest 汇总或 JUnit；中间进度标记不能作为失败/通过结论。最新完整证据仍为 Python 3.12.13 的 §156 **590 passed、29 skipped**；当前树 Python 3.11 全套继续 **UNVERIFIED**，最近完整 3.11 证据仍为 §152 的 **584 passed、29 skipped**。应在最终发布提交、可保留完整运行时的 CI 中重跑并保存 junit/退出码。
- **P4 侧车边界复核：** 校对侧车从有界二进制 stdin 严格解码 UTF-8、拒绝重复 JSON 键，保留 raw/frontmatter，检查私有目录并原子地创建不覆盖的 `.reviewed.md`；长稿逐段拒绝超过 160 字的连续无标点文本。合成 Markdown 用例 **4 passed、2 skipped**，CLI 不回显正文用例 **1 passed**；跳过项分别依赖 Windows 不提供的 symlink 创建和 POSIX mode bits。该机制只验证 Agent 提交的校对文本及其保存安全，不证明默认模型实际审过内容，也不等同于听音纠错。仍需对至少 10 分钟授权样本完成三处人工听审，并在新 Desktop 会话验证由调用方默认模型校对、保存、检查与披露。
- **P6 离线证据刷新：** 当前可复用缓存命中 235 个锁定 artifact 摘要中的 94 个（约 972 MB），其余 141 个不在该缓存；仓库 SPDX verifier 对现存证据成功复核 **41 packages、94 artifacts、41 metadata、9 license、2 notice、863 supplemental members**。固定 SPDX 2.3 schema 校验通过；依原 creation timestamp 重建的 SBOM 经 Windows 换行规范后与现文件一致，共 **121 package records / 137 relationships**；NumPy 原生文件清单包含 **1,130 行、40 个 artifact identity**，与锁定 hash 及保存摘要匹配。`licenseConcluded` 仍为 `NOASSERTION`。这些是已缓存产物的字节/结构证据，不补足另外 141 个制品、完整原生依赖来源/链接映射或许可适用结论。根目录仍无 `LICENSE`、Git remote、owner 发行范围决定、远端 CI 或干净安装证据。
- **未关闭门槛：** P2 仍缺管理员 service/per-lease 隔离与三条真实捕获；P4 仍缺长样本听审和新 Desktop 端到端调用；P5 仍缺新会话发现/调用证据；P6 仍缺 owner 决策、完整发行物来源/许可审查与远端验证。整体继续 **NOT READY FOR RELEASE**。

## 158. 2026-10-11 用户原稿模型校对验收与 Windows PE 导入映射

- **P4 原稿归属复核：** 在本机私有输出目录仅按文件元数据检查时，发现两份较早的校对侧车对应另一份编号原稿，并不对应用户当时指定的原稿；其中较早一份缺少当前模型校对范围说明。因此不能据此认定目标原稿已被校对。具体媒体名称、输出文件名及识别词例不在本报告保留。
- **P4 文本校对：** 用户已授权调用当前 Agent 默认模型纠错。本轮仅以文本方式校对目标原稿，调用项目 `write_reviewed_transcript_markdown()` 新建独立校对侧车。校对后原稿 SHA-256 未变；报告不保留其具体摘要、路径或媒体标识。侧车保留 frontmatter 和章节框架，范围提示注明“当前 Agent 默认模型文本校对、未经逐字听审”；输出父目录权限检查为 `private`。正文为 1,793 字、12 段，最长连续无标点片段 35 字；三个无法从文本可靠恢复的片段标记为建议复听，没有猜写成确定事实。原稿未覆盖，完整转写正文未复制到审计报告或 Git 文件。
- **P4 验收边界：** 上述侧车证明本轮 Agent 完成了文本校对并安全保存，不证明声音中的人名/数字/专名准确，也不证明文本与音视频逐字一致。没有播放或逐句听审媒体；本机样本约 315.907 秒，短于 10 分钟门槛。仍须对至少 10 分钟授权样本完成三处人工听审，并在新 Desktop 会话确认调用方默认模型、保存、复核和数据流披露。P4 继续未通过。
- **P4 对策（文本纠错与事实核查分层）：** 模型校对应保留视频实际表达，不要静默修正其中的数字、专名或事实主张。若产品要附加当前事实核查，应另存带来源和日期的批注，不能覆盖逐字稿；文本本身无法可靠还原的内容应保留为复听标记。
- **P6 Windows PE 导入候选映射：** 新增 [`inventory_locked_pe_imports.py`](../scripts/inventory_locked_pe_imports.py)、[`test_locked_pe_imports.py`](../tests/unit/test_locked_pe_imports.py) 与 [`windows-pe-import-evidence.jsonl`](windows-pe-import-evidence.jsonl)。另外创建了私有 PE 审核缓存，从 `files.pythonhosted.org` 下载 6 个锁定目标 wheel（95,405,677 字节）；每个 artifact 大小及 SHA-256 与 `uv.lock` 完全一致，未安装 wheel 或提取归档成员。离线解析器覆盖 **6/6 wheel、20 个 PE 成员、250 项导入**（242 normal、8 delay-load）；JSONL SHA-256 为 `f7eae8f513d60e18b33413c1377441758ab2a379e88d743e404c717d21339d91`。所有成员摘要、大小与 wheel `RECORD` 相符；AMD64/ARM64 machine 字段符合对应目标。CTranslate2 扩展直接导入 `ctranslate2.dll`，后者导入 `libiomp5md.dll`；ONNX Runtime 主要 DLL 和扩展含对 `SHELL32.dll` 的延迟导入，逐成员详情见 JSONL。
- **P6 证据边界与验证：** PE 导入表不能证明运行时动态加载、静态链接组件、完整构建来源、组件许可证适用性或再分发义务；`cudnn64_9.dll` 只观察到其 PE 普通导入 `KERNEL32.dll`，不代表没有其他加载关系。映射命令退出码 0；新增合成 PE 测试 **6 passed**，Ruff check/format、`py_compile` 与 `git diff --check` 通过。该私有缓存单独保存 6 个目标 wheel；原 SPDX 证据缓存仍覆盖 94/235 个唯一 artifact。详细局限与复现命令见 `docs/THIRD_PARTY_LICENSE_REVIEW.md`。
- **整体门槛：** P2 仍缺可接入管理员环境、生产 service/per-lease worker/WFP 和三条真实捕获；P4 仍缺长样本听审与 Desktop 端到端证据；P5/P6 的宿主验收、所有者许可证/发行决定、完整 native 来源和远端 CI/干净安装仍开放。整体 **NOT READY FOR RELEASE**。

## 159. 2026-10-11 全部锁定依赖制品字节复核

- **P6 artifact gap 复核：** §157 统计的是 SPDX member-level 证据使用的原 SHA-256 缓存：41 个第三方包对应 94 个制品。当时其余 141 个锁定制品不在该缓存。为确认全部 lockfile 发行字节，本轮新增离线只读工具 [verify_locked_artifact_cache.py](../scripts/verify_locked_artifact_cache.py) 和合成边界测试 [test_locked_artifact_cache.py](../tests/unit/test_locked_artifact_cache.py)，并从 uv.lock 中逐条读取 sdist 与 wheel 身份。
- **下载与身份验证：** 用户此前授权下载锁定依赖。本轮只从锁定的 HTTPS files.pythonhosted.org URL 下载，没有安装、导入或解压包内容。所有 235 个 artifact reference（42 个包；本锁文件 digest 唯一数也是 235）共 2,097,567,472 bytes，均匹配锁定 size 与 SHA-256，存放于 <local user path> 私有目录。最终目录只有 235 个 SHA-256 文件，没有临时项；路径权限状态为 private。新增 JSONL 记录 lock SHA、package/version、URL、hash、size 与本地校验状态，文件为 [locked-artifact-cache-evidence.jsonl](locked-artifact-cache-evidence.jsonl)，SHA-256 5c2f50c8a87d2117aeae60ab3b90ae61b084b90e8e11d15d5584be046a44afa0；所引用 uv.lock SHA-256 f4fc838d6f52555ca03ccf378c67e2a988666928904ff14bfab6d4af7c88f31b。
- **可复核验证：** python scripts/verify_locked_artifact_cache.py --lockfile skills/douyin-transcript/uv.lock --cache-dir <private-sha256-cache> 成功报告 42 packages, 235 unique artifacts, 235 lock references, 2,097,567,472 bytes。新增定向测试在 Python 3.11.15 为 4 passed（152.96 秒），在 Python 3.12.13 为 4 passed（0.35 秒）；该脚本 Ruff check/format 与 py_compile 均通过；git diff --check exit 0（存在工作树既有 LF/CRLF 转换提示）。该工具只校验锁定 artifact 字节，不读取压缩成员。原 SPDX evidence JSON 仍只有 94 个已审 artifact 的成员级 metadata/license/notice 信息；它并未因完整缓存自动扩展为 235 个，也不能据 artifact hash 推断包内容完整、发布来源、组件链接、许可证适用性或再分发权限。
- **权限续验：** 当前进程管理员 token 仍为 false，且没有可连接管理员主机/端点；本轮未做 UAC 绕过、系统服务安装或宿主网络策略修改。P2 生产 service/per-lease worker/WFP/真实媒体，P4 长样本人工听审和新 Desktop 默认模型端到端验收，P5 新 Desktop 调用，P6 owner/license/repository 决策、native provenance/link map、远端 CI 与干净安装仍开放，项目整体 NOT READY。

## 160. 2026-10-11 全部锁定制品归档成员清点

- **审查缺口：** §159 已验证 235 个锁定归档的压缩字节、大小和 SHA-256，但没有枚举其他 141 个 SPDX 缓存外制品的成员路径；先前通用成员清单只覆盖 54 个 artifact，NumPy 有独立的 40-wheel 清单。仅验证归档哈希不足以发现其他平台 wheel/sdist 中需要人工复核的许可证、原生二进制和构建元数据候选。
- **工具改进：** 新增 `scripts/inventory_locked_artifact_members_batched.py`，以一个锁定 SHA-256 制品为单位调用现有有界 ZIP/tar 索引器。批处理严格传递剩余展开预算，默认聚合上限 16 GiB、运行上限 3 小时；临时快照使用私有工作目录，输出 JSONL 按每片最多 8 MiB 分片。归档内容不被解压到文件、导入、安装或执行。现有索引器新增可配置总展开上限，默认保持旧行为。
- **完整覆盖结果：** 当前 lock SHA-256 `f4fc838d6f52555ca03ccf378c67e2a988666928904ff14bfab6d4af7c88f31b` 对应的 235/235 个唯一 artifact 全部成功扫描，0 failed、0 not-scanned。合计压缩字节 `2,097,567,472`；索引遍历/声明的展开字节 `6,531,851,175`；成员行 `86,827`，名称/路径候选成员行 `6,239`。详细清单为 [`artifact-member-inventory-complete.md`](artifact-member-inventory-complete.md)，机器 manifest 为 [`artifact-member-inventory-complete-manifest.json`](artifact-member-inventory-complete-manifest.json)，明细分为三个 JSONL 文件，manifest 固定各片 SHA-256。报告 SHA-256 `25ae6671426be79907a153dcab07823e46ca7dcb9cb2a91f3f44d1767d4e8fb3`；manifest SHA-256 `38dc8c7e3d67c445e39a29cdd75a998beb98e0e279748c456b47684c648ee531`。
- **验证：** 全量离线扫描在 11.6 秒内完成；两脚本 `py_compile`、完整 Ruff check、Ruff format check 和 `git diff --check` 通过。额外的一字节展开预算探针按预期拒绝归档。为满足完整 Ruff 规则，基础索引器既有 Markdown 报告长字符串已折行，报告内容保持一致。随后 sensitive-file 检查通过；SPDX verifier 复核 41 packages、94 artifacts、41 metadata、9 license、2 notice、863 supplemental members，固定 SPDX 2.3 schema 检查也通过。扫描程序先全量复验 cache，并在每个归档解析前再次验证同一硬链接快照与锁定 SHA/大小；没有依赖缓存文件名以外的身份信息。
- **发现和处理：** 新清单新增的候选行覆盖 `license-notice-name`、`native-binary-extension`、`native-dependency-name` 与 `dependency-metadata-name`。这些是路径名称启发式提示，并不等于组件发现或许可证正文审查。当前可复用 SPDX `third-party-license-evidence.json` / verifier 仍为 94 个 artifact、41 metadata、9 license、2 notice、863 supplemental members；未把其余候选自动升级为许可证结论，也没有改 `licenseConcluded=NOASSERTION`。native provenance/link map、NOTICE 到确切动态/静态链接组件映射、发行范围和所有者批准仍开放。P6 与整体发布状态继续 **NOT READY**。
- **新增的许可证候选覆盖差额：** 将 1,160 个非空 `license-notice-name` 路径候选与 SPDX 清单按 `(artifact SHA-256, member path)` 精确比对，发现 297 个候选没有显式的成员证据绑定。按路径启发式计数较多的包是 NumPy 55、PyAV 44、greenlet 42、Ruff 23、ONNX Runtime 20、PyYAML 20；这些数字包含不同平台/版本制品的重复路径，也可能包含 AUTHORS 等名称误报，不能直接视为 297 个不同许可文本或 297 项违规。优先对候选正文流式计算 SHA-256，与相同包的已审文件去重，再对不同摘要和 ONNX/FFmpeg/native notice 做人工核对；把需支持的成员以精确 artifact/path/hash 加入 SPDX evidence，重跑 verifier/schema，并在所有者审阅前维持 `licenseConcluded=NOASSERTION`。该差额作为开放 P6 对策，不把路径名直接推断成许可结论。
- **复现：** 在已验证私有 SHA-256 cache 上执行 `python scripts/inventory_locked_artifact_members_batched.py --cache-dir <sha256-cache> --work-dir <private-work-dir> --output-dir docs --output-prefix artifact-member-inventory-complete --expanded-budget-bytes 17179869184 --runtime-seconds 10800`。不联网，不修改系统策略。

## 161. 2026-10-11 ZIP 成员类型修复、候选哈希绑定与 SPDX 校验器单遍读取

- **AUD-96（P6，ZIP 普通文件被误标成 `other`）：** ZIP 外部属性包含 Unix 权限位但未带 `S_IFREG`/`S_IFDIR` 类型位时，索引器此前将类型位为 `0` 的常规成员判作 `other`。修复 `scripts/inventory_locked_artifact_members.py`：对 ZIP 将“未提供类型位”解释为普通文件；明确 symlink、目录和特殊文件仍使用独立类别。合成 ZIP 类型回归覆盖该编码。
- **清单复核：** 对全部 235 个锁定制品重新执行离线、预算受限索引。制品/成员集合与初版完全相同（235 个、86,827 行）；更正 50 行成员类型。压缩字节 `2,097,567,472`，展开/遍历字节 `6,531,851,175`，候选行 `6,239`，0 失败/未扫描。正式报告 SHA-256 `2d582c78288aed1f6f384e021e1ff2e61e007b88849f6f22ef803185d8159024`；manifest SHA-256 `03d71d849d5be4d057d567dc309c18cdf4c66716d38d55712df912f3f285f634`；三个固定 JSONL 部分 SHA-256 分别为 `d06ca8eea88114ea86b320de644738cd9447b3b9e45c7c672a789d00a7ed1098`、`5234e00063624366774147ad38be91cbf46241027018f518e7ce7cd8d5c20a67`、`6e288088d473604a8100e84d9f15676c8d0af884ce86ead5d380ee41c47ed341`。
- **候选哈希与证据绑定：** 1,160 个非空 `license-notice-name` 候选中，按包、版本、锁定制品摘要和成员路径精确比对得到 286 个未绑定普通文件候选（36 个包，90 个不同成员 SHA-256）；其中 60 条记录的内容摘要与同包已有成员证据匹配，共对应 24 个不同 SHA-256。旧 §160 的 297 是粗略对账误差，按修正后的精确键复算应为 286。新脚本对候选逐项检查锁定制品缓存身份，流式读取成员、比较清单大小并算 SHA-256；不提取、安装或执行归档成员。新增 286 条 `artifact_members`，只记录精确制品/路径/摘要/大小，不改 `licenseDeclared`、既有许可证字段或 `licenseConcluded=NOASSERTION`。完整哈希行见 [`unbound-license-candidate-hashes-2026-10-11-final.json`](unbound-license-candidate-hashes-2026-10-11-final.json)，SHA-256 `c13a600cb2faa017a050502ef606f030802d3af558340312459fd30c877ead66`；SPDX evidence SHA-256 `8d5de21ce8d728e0b6343c71fa7028ee5a02dabb58b5fd38d2bd69037b28770e`。
- **AUD-97（P6，sdist 多成员校验重复解压）：** evidence verifier 此前对 tar.gz 每个证据路径都从头流式解压；如 NumPy sdist 上数十条成员记录，会重复计入单制品 `512 MiB` 解压预算并错误失败。现在 `verify_evidence()` 对每个 sdist 一次有界流式遍历，逐个验证请求成员的唯一性、普通文件类型、SHA-256/大小与 metadata 内容；每次遍历仍受 50,000 成员限制，每制品解压字节和 deadline 预算仍按原上限累计。ZIP 的 50,000 中央目录预检也继续按单个 archive 执行。
- **验证：** Windows Python 3.11.15 全部 `test_spdx_evidence_verifier.py`：**32 passed、2 skipped**（POSIX FIFO 专用项）；包含单次解压、成员数上限、缺失成员和共享字节预算回归。哈希更新工具通过离线 SPDX verifier：**41 packages、210 artifacts、41 metadata、9 license、2 notice、1,149 supplemental members**。SBOM 在保留原 creation timestamp 后重生成，共 121 packages/137 relationships，SPDX 2.3 schema 通过（schema SHA-256 `4126dc29f15e92feec92e9622f4939131ad58b125d6f578aa93e980a6e6f3212`）；新 SBOM SHA-256 `4205e0d1c6d470227ad069ced573382284f947f9616083c02c41ba1563642e3a`。更正 inventory、哈希、Ruff/format 和 `py_compile` 检查通过。
- **P2 权限边界与未关闭工作：** 按用户最新授权复查当前 Windows 身份，`IsAdministrator=false`、`IsSystem=false`；用户授权本身不创建管理员 token，也没有提供管理员主机名或远程连接端点，本机没有既存 PowerShell 远程会话。§148 的标准 UAC 只读探针曾被执行器在子进程创建前拒绝。未安装服务、未执行替代提权、未修改 WFP/Firewall。P2 仍缺生产 service/per-lease worker/WFP、认证隔离和三条真实捕获；P4/P5 仍缺长样本人工听审与新 Desktop 验收；P6 仍缺所有者许可/发行范围决定、完整 native provenance/link map、远端 CI 和干净安装。286 条哈希补充记录不代表许可证适用性审阅或再分发批准；整体 **NOT READY FOR RELEASE**。


## 162. 2026-10-11 本机全套复测、P2 租约策略切片与 P6 证据对账

- **AUD-100（P2 harness 的 IPv6 用例输入不完整，已修正）：** 首次从已构建输出复跑 no-network harness 时，IPv6 上游规则断言失败（7/8）；测试 fixture 只传入 IPv4，却断言存在 `2606:4700:4700::1111` permit。更新后的 fixture 明确传入这条 IPv6 pin 后，重新构建并运行 harness 为 **8/8**。该差异属于测试输入，不是编译器丢弃有效 IPv6 目标；没有据此宣称真实 WFP IPv6 行为通过。
- **P2 纯代码改进：** 新增 `LeasePolicyCompiler` 以 service 提供的 lease UUID、唯一 user/package SID、browser/worker AppID、端口、numeric resolver 与完整 pinned A/AAAA 集合生成确定性语义 plan。除每个 browser/worker AppID 的持久 IPv4/IPv6 catch-all block 外，现在也为每个独立 lease principal 生成 `ALE_USER_ID` 或 `ALE_PACKAGE_ID` 的 v4/v6 principal-wide catch-all block（省略 AppID/remote/protocol/port 条件），避免同一 lease SID 下未登记 helper/child AppID 脱离默认拒绝；精确 listener、DNS 53 和 upstream TCP/443 permits 绑定 AppID 与对应 principal。校验覆盖重复/交叉身份、SID 形状与 package SID 8 个 RID 数量、numeric/canonical IP、非公网目标、端口及确定性输出。Microsoft package SID 常量依据见官方 [App Container SID constants](https://learn.microsoft.com/en-us/windows/win32/secauthz/app-container-sid-constants)。
- **P2 验证边界：** 本机以缓存中的 .NET SDK 10.0.401 重建 `WfpPolicyPlan.csproj`（Release，0 warnings/0 errors），no-network console harness **8/8 passed**，`VerifyFilterPlanArtifact.ps1` 通过且历史 artifact SHA-256 保持 `51bf789b93e250a431b4c0ca756b4b86ad69d0a161a02bb561fd51a2a6553f0d`。输出永久标记 `not-deployable`；没有 WFP/BFE API、service/installer、真实 token/SID 校验、Chromium 进程树或实际 filter。仍需在受控管理员 Win11 环境检查 token、filter fields/layers、soft/hard arbitration、v4/v6 flow、heartbeat/撤销和 failure recovery；用户授权不能创建当前进程没有的管理员 token，也没有可连接的管理员主机或 broker endpoint。本轮未安装 service、未改 host WFP/Firewall。
- **全套 Python 回归：** Windows Python 3.11.15 全树 **601 passed、29 skipped，62.58 秒**，JUnit 文件保存在仓库外 `<local user path>`，SHA-256 `87892566AD1C006CB38C6F616DCAB47CE1D13A9498B784F4609B4DB3FDF1C491`。临时 launcher 只将 pytest 非产品用的 best-effort `current` symlink updater 替换为空操作；正常 `tmp_path` 独立目录、fixture 与产品测试照常运行。29 个 skip 包括 POSIX 专属/本机文件系统不支持项及 2 个未配置 host path 的 native interop 项。Python 3.12.13 最近完整套件仍为历史 §156 的 590/29；本轮没有在 3.12 重跑，也未运行远端/跨平台 CI。
- **P6 FlatBuffers 声明对账：** `third-party-license-evidence.json` 中 FlatBuffers 25.12.19 是 `reviewed_legacy_value_mapping`，固定版本 PyPI/setup.py/LICENSE 来源映射为 `Apache-2.0`；先前 `evidence_policy` 却仍把它描述为未解决，与 `licenseDeclared` 不一致。现已修正文案并重生成 SPDX；离线 verifier 为 **41 packages、210 artifacts、41 metadata、9 license、2 notice、1,149 supplemental members**。SPDX 2.3 schema 通过，121 packages / 137 relationships，所有 `licenseConcluded` 仍 `NOASSERTION`。Evidence SHA-256 `3E065DBD1DF88250DA0FB9AB5B63C18D3F37AC91B1B894F73C20ECE1AB439ED4`；SBOM SHA-256 `47647242AB72DFDEB56EE36B961972FE33FF257F6E0ACFEACEE6C049AC7A5967`；schema SHA-256 `4126dc29f15e92feec92e9622f4939131ad58b125d6f578aa93e980a6e6f3212`。SPDX verifier/SBOM/schema focused test group **64 passed、3 skipped**。本地 210/1,149 成员覆盖只证明锁定制品/成员身份和字节；不决定许可适用性。
- **P6 286 个新成员内容分类：** 新增 `docs/P6_286_MEMBER_CONTENT_AUDIT_2026-10-11.md`。对 152 个私有缓存制品复核 286 条记录，归并为 92 个 `(package, member SHA-256)` 组、90 个正文 hash；284 个 UTF-8、2 个 RTF，未发现二进制。分类为许可证正文 223 条/68 组，NOTICE 8/2，作者名单 16/4，源码/构建误报 26/9，文档/模板误报 8/6，短许可引用 3/2，版权短声明 2/1。该复核更准确区分了正文与路径命中误报；不修改 license expression，不作适用性或法律结论。
- **仍未通过：** P2 尚无生产服务、可接入管理员环境、动态 WFP/浏览器身份证据或三条端到端授权视频；P4 缺 10 分钟以上样本和至少三处人工听审；P5 缺新 Desktop 会话发现/实际调用 trace；P6 缺所有者项目许可证/发行范围/仓库决定、完整 native provenance/linkage 审查、远端 CI/干净安装。总体 **NOT READY**。下一步由所有者在真实可达管理员环境中运行 service/WFP 验收；本机继续只维护 fail-closed 产品行为和非部署静态校验，不以本次 compiler/harness 通过替代 OS 隔离结果。

## 163. 2026-10-11 逐段标点守卫、Windows 互操作复测与权限状态

- **AUD-101（P4，段落级标点缺口，已整改）：** 旧 `review-sidecar` 只检查全文是否至少出现一个中文标点，并限制连续无标点 run 不超过 160 字；因此，一段有标点可掩盖另一段完全无标点的文本。现改为逐段要求至少一个中文句读标点，并保留 160 字 run 限制、300 字正文的分段要求。`tests/unit/test_markdown.py` 新增“第一段有逗号、第二段 151 字无标点”的拒绝回归。同步更新 canonical Skill 与 CLI reference，说明这是格式守卫，不代表模型校对或声学核验质量。
- **AUD-102（代码风格检查未覆盖格式化，已整改）：** CI 原先只运行 `ruff check`。额外执行 `ruff format --check` 发现 CI 检查范围内 42 个 Python 文件格式不一致；已按锁定 Ruff 格式化这 42 个文件，并在 workflow 增加独立 `ruff format --check` 步骤。格式化只改空白/布局，没有预期语义变化；后续全树测试复验见本节。
- **P4 验证：** 标点/CLI 定向组为 **103 passed、4 skipped**（106.23 秒）；skip 是当前 Windows 主机不支持的 symlink 和 POSIX FIFO/mode-bit 用例。Ruff 对变更的 Python 文件通过。
- **P2 Windows named-pipe 原型互操作：** 使用缓存 .NET SDK 10.0.401，以 x64 Release/no-restore 重建 `native/windows/capture-pipe/CapturePipe.csproj`，0 warning、0 error。配置测试专用 executable/DLL 路径后，`test_windows_capture_pipe.py` **2 passed**，覆盖同用户身份握手、错误 service SID 拒绝、有限 artifact 收取/摘要校验，以及取消 overlapped read 后清理。它只验证同用户本地命名管道原型；不证明 SCM service、service SID、Session 0、生产 ACL、浏览器身份或 WFP 已部署。
- **全树复测：** Windows Python 3.11.15 为 **604 passed、27 skipped、63.63 秒**。为避免 pytest 在本机尝试更新 best-effort `pytest-current` 符号链接造成 30–90 秒停顿，仓库外 launcher 仅把 `_pytest.pathlib._force_symlink` 替换为空操作，并加入标准 `__main__` guard；pytest、fixture、产品代码与 `tmp_path` 测试均正常运行。两项 named-pipe 集成测试本轮通过，不再跳过。其余 27 项是本机未支持的 symlink/POSIX 专属文件系统行为。JUnit 位于仓库外 `<local user path>`，SHA-256 `338965271573B362DBC148E545DAFD36CF1B953B4A0671CE6AD70D7AE26D2DA7`。
- **测试启动器错误及更正记录：** 首次完整复测使用的临时 launcher 漏掉 `if __name__ == "__main__"`；Windows `multiprocessing` spawn 重导入该脚本后再次启动 pytest，使 socket-share 集成用例表面超时。单项失败在复查 traceback 后定位为测试 launcher 重入，并非产品 socket 代码；加入 guard 后单项 **1 passed**，继而受保护 launcher 的全套复测 **604/27** 通过。首次失败结果不作为产品缺陷结论，也未从测试中删除该用例。
- **P2 管理员权限门槛：** 当前是普通 Windows 本机用户；Administrators 组仅为 deny-only，medium-integrity，`IsAdministrator=false`，PowerShell 远程会话数为 0。经用户授权尝试一次只读标准 UAC `RunAs` 身份探针，但执行器策略在创建子进程前拒绝该调用；没有 UAC 提示、提升进程或管理员主机 endpoint。没有改用其他启动路径，没有安装服务，也没有修改宿主 WFP/Firewall。用户授权不会创建 OS token 或连接端点；P2 仍需真实管理员环境。
- **审核代理副作用与恢复：** 一条只为临时重建 SBOM 的 `uv run --offline --locked --project ...` 命令意外触发 uv 自动同步并删除/重建 `skills/douyin-transcript/.venv`。已通过 `uv --offline sync --locked --all-groups --all-extras --project skills/douyin-transcript` 按当前 lockfile 成功恢复（Resolved 42、Installed 34；ASR、browser、dev 与 build 组可用）。这是基于锁文件的恢复，不证明与被替换 venv 的所有自定义状态逐字节一致；该环境被 Git 忽略，未发现已跟踪文件因该操作变化。本记录用于披露操作，不作为产品缺陷。
- **SPDX 再生成与验证：** AUD-102 的格式化改变了 `generate_spdx_sbom.py` 字节，因此依赖生成器 SHA-256 的 SBOM namespace 回归先按预期失败；保留 `2026-10-11T02:42:31Z` creation timestamp 重生成后，121 packages / 137 relationships 的 inventory test 与 SPDX 2.3 pinned schema 均通过。`third-party-license-evidence.json` 未变化；SBOM SHA-256 为 `5A861F6A4AF4D7FA027A236C1979D3CC37DF0323844996B84A162756D09FD091`。离线 evidence verifier 复核 41 packages、210 artifacts、41 metadata、9 license、2 notice、1,149 supplemental members。
- **当前门槛：** P2 仍缺生产 service/per-lease worker/WFP、服务认证与三条真实媒体捕获；P4 缺 10 分钟以上样本、至少三处人工听审和新 Desktop 默认模型端到端验收；P5 缺新 Desktop Skill 发现与真实调用 trace；P6 缺 owner 许可证/发行/仓库决定、完整 native provenance/link map、远端 CI 与远端干净安装。项目仍 **NOT READY FOR RELEASE**。

## 164. 2026-10-11 P2 原生过滤器内存构造与结构审阅

- **AUD-103（P2，语义规则与 CsWin32 原生结构之间缺少可验证映射）：** `LeasePolicyCompiler` 的结果之前只有 JSON 意图；独立 Sandbox 脚本实现了自己的 native builder，项目 C# 源码没有把每条租约规则转成 `FWPM_FILTER0`/`FWPM_FILTER_CONDITION0` 供回归检查。该缺口使 SID descriptor、地址字节顺序、过滤器 flags 和值联合体不能在同一个受控源码路径中核对。
- **整改：** 新增 Windows-only `WfpFilterMaterializer.MaterializeForInspection()`，为编译器生成的受限、永久 `not-deployable` plan 构造真实 CsWin32 WFP 原生结构，复制为不含指针的审阅 DTO 后清零并释放所有非托管 arena。显式 provider/sublayer GUID 必须非空；过滤器 key 按 provider+rule ID 稳定生成。映射覆盖 AppID `FWP_BYTE_BLOB_TYPE`、`ALE_USER_ID` 的 self-relative SID ACL（仅 `FWPM_ACTRL_MATCH_FILTER` allow ACE）、`ALE_PACKAGE_ID` 的 `FWP_SID`、IPv4 host-order `FWP_UINT32`、IPv6 `FWP_BYTE_ARRAY16_TYPE`、协议 `FWP_UINT8`、端口 `FWP_UINT16`、weight range index 和持久默认拒绝 flag。AppID 原始字节不写入审阅结果，只输出长度与 SHA-256。WFP condition GUID 统一改用锁定 CsWin32 生成符号，新增 user/package condition 声明。
- **安全边界：** 方法不打开 BFE、不调用任何 WFP API、不应用或保存过滤器、不返回 native pointer，也不安装 service；CLI 的可执行命令未调用它。DTO 固定标记 `PolicyMutated=false` 与 `not-deployable`。该源码测试不能证明 BFE 接受结构、动态 session 生命周期、条件在目标 layer 的运行时可用性、跨 provider 仲裁或真实网络隔离。
- **验证：** Windows x64 .NET SDK 10.0.401 Release/no-restore build 为 **0 warnings、0 errors**；无 NuGet 测试框架的本地策略 harness **10/10 passed**，新增测试检查 user/package SID 编码、descriptor ACE、filter key、provider/sublayer、v4/v6 地址、协议/端口、动作、权重、持久 flag 和对歧义/伪 deployable 输入的拒绝。项目级 `.editorconfig` 与 `.gitattributes` 统一 C# 使用 LF；WFP 主项目与 harness 的 `dotnet format whitespace --verify-no-changes` 均通过。`VerifyFilterPlanArtifact.ps1` 通过，原五规则 artifact SHA-256 保持 `51bf789b93e250a431b4c0ca756b4b86ad69d0a161a02bb561fd51a2a6553f0d`。CI 的 Windows native job 现会锁定 restore、格式检查、build、跑该 harness 并核对 artifact pin。
- **权限与发布门槛：** 当前会话没有管理员令牌或可接入管理员主机，标准 UAC 探针仍受执行器策略阻止；没有尝试其他提权路径，没有修改宿主 WFP/Firewall。P2 尚缺 BFE 动态验收、SCM service/worker、进程 token、浏览器身份、失败清理及三条授权视频；P4/P5/P6 验收门槛同 §163，项目仍 **NOT READY FOR RELEASE**。

## 165. 2026-10-11 P2 DNS/CNAME 有界校验与 native 格式门槛

- **AUD-104（P2，DNS 结果完整性只停留在策略输入契约）：** `LeasePolicyCompiler` 要求调用方提供完整 A/AAAA 固定地址，但 capture-pipe 没有源代码处理 CNAME 链、截断、回答上限和混合公网/私网答案。新增 `LeaseEgressPolicy.ResolveAsync()` 作为纯校验层，接受注入的 `INumericDnsQuestioner`，只使用数值 resolver 与固定 DNS 端口号契约 53，不接受系统 hostname 解析回退；UDP/TCP 的实际传输由尚未实现的适配器负责。同时解析 A 与 AAAA，校验问题名和类型，沿 CNAME 前进，拒绝 CNAME 环、冲突 alias、CNAME 与地址记录混合、截断/错误响应、非公网地址及超限输入。上限为 8 跳、20 个 DNS 问题、每个响应 64 条、总计 128 条、最终 64 个地址和 10 秒总 deadline。成功结果按地址族和字节稳定排序并只暴露只读列表。
- **策略一致性：** 将 IPv4/IPv6 公网单播规则提取到 `native/windows/shared/PublicUnicastAddressPolicy.cs`，由 capture-pipe 校验和 `LeasePolicyCompiler` 共用，避免二者的特殊用途地址 allow/deny 清单产生漂移。`LeaseEgressPolicy` 仍不执行真实 DNS 或 socket I/O，也没有生产 DNS wire parser、事务 ID/响应来源/RRset 完整性校验、TCP fallback、TTL 生命周期管理或固定 IP upstream connector；没有调用它的 service/worker，默认 capture handler 仍以 `BROWSER_ISOLATION_UNAVAILABLE` 失败关闭。它只能成为后续集成的源代码构件，不能视作 worker DNS/IP pinning 已完成。
- **AUD-105（native C# 行尾设置与 repo 根格式冲突）：** 首轮全项目 `dotnet format` 发现根 `.editorconfig` 为 C# 强制 CRLF，而既有 WFP native C# 源码已按 LF 保存，导致 capture-pipe 全项目验证输出大量行尾差异。根配置现为 `native/windows/**/*.cs` 明确选择 LF，其他文件仍遵循原始项目默认值。格式化检查随后对 capture-pipe、WFP 项目和 WFP harness 均通过；Windows CI 已增加 capture-pipe C# 格式门禁，尚未运行远端 CI。
- **验证：** 使用本机已缓存、项目锁定的 .NET SDK 10.0.401（未安装 SDK 或其他系统工具）。capture-pipe Release build **0 warnings、0 errors**；其 self-test 通过，新增 offline fake transport 覆盖成功 A/AAAA/CNAME、固定 resolver/53 端口、混合私网、CNAME 环、超过跳数、超大 answer、截断、问题不匹配及 loopback resolver 拒绝。WFP Release build **0 warnings、0 errors**，语义与 native materializer harness **10/10 passed**；五规则预览制品哈希仍为 `51bf789b93e250a431b4c0ca756b4b86ad69d0a161a02bb561fd51a2a6553f0d`。没有重跑 Python 全套；最新完整 Python 证据仍为 §163 的 **604 passed、27 skipped**。
- **权限与剩余门槛：** 用户已授权自主处理，但本次会话仍无管理员 token、管理员 host endpoint 或已验证 broker；授权不会让普通进程获得管理员 SID。没有尝试旁路 UAC、安装服务、修改 WFP/Firewall 或发起管理员远程连接。P2 仍需生产 DNS/connector/worker、SCM 安装与服务身份、真实 BFE/WFP、Chromium 身份/进程树验证和三条授权视频；P4 的长样本人工听审与新 Desktop 默认模型验收、P5 新 Desktop invocation、P6 owner 决策/native provenance/远程 CI 与干净安装仍未通过。整体 **NOT READY FOR RELEASE**。

## 166. 2026-10-11 锁定 Windows wheel 全量 PE 导入映射

- **AUD-106（P6，native import map 只覆盖两个包）：** 既有 `inventory_locked_pe_imports.py` 仅选择 CTranslate2/ONNX Runtime，且只寻找 `.dll`/`.pyd`。其余锁定 Windows wheel 中的 PyAV、NumPy、Playwright、Ruff 等原生文件未进入 direct-import 快照，`ruff.exe` 等可执行文件也未被解析。
- **清点器扩展：** 现在处理 `uv.lock` 中全部 Windows wheel，包括 `win32`、`win_amd64`、`win_arm64`，不按包名筛选；PE 候选后缀包含 `.exe`、`.dll`、`.pyd`。每个 wheel 仍从同一身份核验句柄复制到临时快照，并与锁定大小/SHA-256 对照；所有候选成员流式读取，不落盘提取，解析器有界读取 PE 结构并记录 PE machine 与 wheel 平台标签是否相符，另以 ZIP CRC 和可用的 wheel `RECORD` 做校验。总 PE 成员展开字节保留 1 GiB 硬上限；任一锁定 Windows wheel 缓存缺失时不生成部分成功清单。`RECORD` 已核验、未提供摘要和缺失成员行分别记录，后两种不会标成验证通过。
- **全量结果：** 本地缓存中的 **40/40** 个锁定 Windows wheel 均匹配 `uv.lock`，共 11 个包。解析得到 **419 个 PE 成员**：97 DLL、6 EXE、316 PYD；其中 PE32 为 62 个、PE32+ 为 357 个，machine 分布为 x86 62、AMD64 277、ARM64 80。导入表共有 **2,654 项**（2,646 normal、8 delay-load）。与 §161 完整归档成员清单按 `(artifact SHA-256, member path)` 对账为 **419/419 完全覆盖**，无缺失/额外路径，成员大小均一致。该初始清单曾按原始路径统计 416 个 `RECORD` 摘要/大小匹配，并将 3 个 Ruff wheel 的 `ruff.exe` 标为 `missing_from_record`；§172 证明这是反斜杠路径未规范化造成的误报，当前重建后的 419 个 PE 成员全部匹配 RECORD。
- **AUD-107（P6，win32 wheel 的 PE 架构不符）：** `playwright-1.63.0-py3-none-win32.whl` 的 wheel 标签为 `win32`，但其 `playwright/driver/node.exe` 是 AMD64 PE；该成员 RECORD 摘要/大小和所属锁定 wheel 均通过。项目实施计划将 V1 URL 捕获目标定为 Windows 11 x64，因此这不直接证明受支持目标故障；但若声称 32 位 Windows/Playwright 支持，需从上游制品/打包配置核对该架构并决定移除该 wheel 或另行修正。当前输出以 `machine_matches_wheel_platform=false` 明确保留，不把标签一致性误报为通过。
- **解析器修正：** 全量扫描发现一个有效 PyAV DLL 的 PE import-directory 声明长度比 20 字节描述符边界多 8 字节。解析器此前要求目录长度可整除描述符大小，导致合法 DLL 被误拒。现在仅把目录声明长度当作有界解析范围，仍要求在范围内找到全零终止描述符；另有带尾部 padding 的结构回归。
- **产物与验证：** 新清单 [`windows-pe-import-evidence-complete.jsonl`](windows-pe-import-evidence-complete.jsonl) 共 419 行、420,779 字节，SHA-256 `1e620e1ee71ada28f2e958d43017eb15ce311061507e168673611a8104780ca0`，锁文件 SHA-256 为 `f4fc838d6f52555ca03ccf378c67e2a988666928904ff14bfab6d4af7c88f31b`。PE 成员展开字节总量为 1,032,642,852，低于 1 GiB 上限。定向回归 **15 passed**；Ruff check/format 与 `py_compile` 通过。没有下载或安装 wheel；所用的是已有私有 SHA-256 缓存。未运行完整 Python 套件或远端 CI。
- **解释边界：** 此为归档中 PE 直接导入表的更广覆盖，不是完整 transitive/native BOM、运行时 `LoadLibrary`/`GetProcAddress` 模块图、符号/静态链接图、构建来源证明或许可证适用性结论。未改变 SPDX 的 `licenseDeclared` 或 `licenseConcluded=NOASSERTION`。P6 仍需所有者确定项目许可证、发行范围和仓库/远端操作；还需 artifact-bound 构建来源与 native 链接/notice 审查、远端 CI 和干净安装。P2/P4/P5 门槛亦仍开放，项目整体 **NOT READY FOR RELEASE**。

## 167. 2026-10-11 P2 DNS deadline、取消与累计上限回归

- **AUD-108（P2，DNS policy harness 未覆盖真实 deadline 与多响应边界）：** §165 的离线用例覆盖单响应 CNAME、单响应答案上限等，但没有验证跨响应 CNAME、128 条总答案限制、64 个最终 pin 上限、10 秒解析 deadline 或 caller cancellation。
- **整改：** `LeaseEgressPolicy.ResolveAsync()` 保留生产最大 10 秒 deadline，并新增仅供同程序集回归使用、且只能缩短 deadline 的 overload。LocalHarness 现在覆盖：A/AAAA 的 CNAME 分别在后续响应闭合、三次各 64 答案时拒绝超过总上限、64 个 IPv4 加 1 个 IPv6 时拒绝过量 pins、100 ms 测试 deadline 转成 `TimeoutException` 并令遵守 token 的 fake 结束、caller cancellation 传递到 questioner 并令 fake 结束，以及无关 owner 的私网 A/AAAA 不污染可达公网地址。native self-test 打印 **14 bounded lease DNS policy scenarios**。
- **AUD-109（P2，可用性保守拒绝，已修正）：** 原先 `IndexAndValidateAnswers()` 对 Answer 集所有 owner 都执行公网地址校验，使无关 owner 的私有/特殊地址也会令解析 fail closed。现在仍对所有记录校验 DNS 名称、类型、IP 语法、地址族和 IPv6 scope，但只对查询名及其可达 CNAME 链上的 terminal A/AAAA 应用公网单播策略；可达 owner 仍拒绝 CNAME 与地址记录混合。新增回归证明无关私网记录不会污染公网 pin，同时原有私网 terminal 负向用例仍拒绝。
- **未关闭的 transport 风险：** cancellation harness 的 fake 明确响应 cancellation；真实 `INumericDnsQuestioner` 尚不存在。若未来实现忽略 cancellation，`WaitAsync` 只会停止调用方等待，不能关闭底层 socket/task。因此生产 transport 必须拥有并在取消/deadline 时 dispose socket，再以本机 UDP fixture 验证来源端点、事务 ID、截断和 socket 生命周期。
- **验证与状态：** 使用已缓存 .NET SDK 10.0.401 进行 capture-pipe x64 Release build，**0 warnings、0 errors**；`dotnet format whitespace --verify-no-changes` 通过；native `--self-test` 通过 14 个场景，覆盖跨响应链、累计 bounds、无关私网记录、deadline 和取消。WFP 源码未变，其上次 §165 的 build/harness 仍为 0/0、10/10，本轮未重跑；Python 全套也未重跑。测试均为离线 fake，不证明真实 DNS、socket pinning、worker/service、管理员 WFP 或三条媒体验收。用户当前会话仍 `IsAdministrator=false` 且没有管理员 host endpoint；未安装 service、未改 WFP/Firewall。P2/P4/P5/P6 与 release gate 继续开放，整体 **NOT READY FOR RELEASE**。

## 168. 2026-10-11 P2 数值 DNS wire transport 与取消关闭

- **AUD-110（P2，DNS 只验证 typed fake、没有实际 wire transport）：** §167 的策略 harness 只能证明 typed DNS 结果校验；还没有解析 DNS 报文、关联响应事务/问题，或证明取消能结束实际 socket I/O。生产 capture worker 和 connector 仍不存在。
- **整改：** 新增 `DnsWireCodec` 与 `NumericDnsQuestioner`。查询由数值 resolver endpoint 和 A/AAAA 类型构造，使用随机事务 ID；响应检查来源 endpoint、ID、QR/opcode、问题名/类型/class、分段记录数、报文长度、压缩指针边界和 A/AAAA/CNAME RDATA。UDP 回答置 TC 时按 DNS TCP 长度前缀重试；TCP 再截断仍交由策略拒绝。UDP/TCP 查询 token 取消时 dispose 对应客户端 socket，而非只取消调用方等待。reachable CNAME 与 terminal 地址的 TTL 取最小值并限制为 300 秒；缺少 TTL 时返回不可缓存标记，当前不实现缓存。
- **安全边界：** connected UDP/TCP socket 加来源 endpoint、随机 transaction ID 和问题字段匹配可约束响应来源与关联，但不提供 DNSSEC 或其他密码学认证；配置的 resolver 与网络路径仍是信任前提。解析完整报文、拒绝 TC 后的 TCP 回答和传递 TTL 不证明 resolver 返回了真实/完整权威 RRset，也不证明已有 upstream socket 使用 numeric IP。新 queryer 尚未接入 lease worker；没有 per-lease DNS identity/WFP 规则、固定 IP connector、浏览器捕获、SCM service 或安装器。
- **验证：** 使用仅绑定 `127.0.0.1` 的本地 UDP/TCP fixtures，无外部 DNS 查询。native self-test 通过 **15** 个 lease DNS policy 场景，以及 wire parser 的错 ID/错问题、压缩指针自引用、过量记录、错误 A 长度、CNAME 解码、UDP 查询、TC→TCP fallback 和 UDP/TCP cancellation 场景；capture-pipe x64 Release build **0 warnings、0 errors**，`dotnet format whitespace --verify-no-changes` 通过。Windows Python 3.11.15 全套在该 native 切片前完成 **611 passed、29 skipped**（268.36 秒）；本轮 native 变更由独立 build/self-test 覆盖。未重跑 WFP harness 或 Python 3.12。
- **状态与后续：** 当前 token 仍非管理员且无管理员 endpoint；没有安装 service 或修改 WFP/Firewall。下一步应把 questioner、完整 RRset/TTL 策略和 numeric-IP connector 一起放入逐租约 worker，再在可回滚管理员环境验证 resolver/upstream 身份、WFP 与失败回收。三条不同授权视频、P4 长样本人工听审、P5 新 Desktop 调用、P6 所有者决定/远端 CI/干净安装仍未完成，项目保持 **NOT READY FOR RELEASE**。

## 169. 2026-10-11 P2 DNS TTL、名称与 parser 边界复核

- **AUD-111（P2/P3，后续集成可能误用过期 TTL）：** §168 原先把首个回答 TTL 作为 resolve 完成后的剩余秒数；串行 A/AAAA 与 CNAME 查询耗时会让 consumer 从完成时开始缓存，可能超过 DNS TTL。DNS authority SOA 的 negative TTL 也未进入数据模型。
- **AUD-112（P2/P3，无关但合法 DNS 名称造成误拒绝）：** 将每个 Answer owner/CNAME target 当作 URL hostname 校验，会误拒绝 `_service.example` 等合法 DNS label，即使该记录与查询链无关。此为可用性问题；capture-pipe 仍未接入产品路径。
- **AUD-113（P3，DNS 压缩指针仅检查字节位置）：** 只拒绝 forward/self/out-of-range 指针，不足以确保 backward pointer 指向已解析的名称标签；畸形报文可能令 parser 从任意 RDATA 字节解码出伪造名称语义。尚未发现可绕过 terminal 公网 IP 策略的直接路径，且 queryer 尚未集成。
- **整改：** `LeaseDnsResponse` 保存单调时钟接收时间；policy 在汇总时扣除已耗时并将剩余 TTL 限制到 300 秒。因未解析 authority SOA，任何空 family 或无该 QTYPE terminal answer 都使合并地址集不可缓存。record owner/CNAME 先用宽松但有界的 DNS wire-name 规范化；URL hostname 规则仅应用于初始查询名和可达 CNAME 目标。wire parser 仅允许压缩指针指向此前成功解析的 label/root/pointer 边界。取消 harness 通过注入 socket factory 保存真实 `SafeSocketHandle`，检查 UDP 与 TCP handle 在取消后已关闭。
- **回归与验证：** 新增已过期 TTL、耗时扣减、无 SOA negative TTL 不缓存、无关 underscore label、指向非名称 RDATA 的 backward pointer 拒绝，以及 UDP/TCP handle closure 场景。native self-test 通过 **18** 个 offline lease DNS policy 场景和 loopback wire/UDP/TCP tests；capture-pipe x64 Release build 为 **0 warnings、0 errors**，`dotnet format whitespace --verify-no-changes` 通过。仅绑定 loopback，无外部 DNS。Python 3.11.15 的 **611 passed、29 skipped** 是 §168 本轮 native-only 改动前的结果，不是本节 source delta 后的 Python 重跑。
- **边界与状态：** 未解析 DNSSEC、authority SOA 或完整 RRset；保守不缓存含 negative-family 结果。DNS questioner 仍未接入 worker/connector/WFP，因此这些是源码切片，不是线上漏洞修复证明或生产隔离证据。当前 Windows token 非管理员，也无管理员 endpoint；没有提权、连接远程主机或修改 WFP/Firewall。P2/P4/P5/P6 仍未通过，项目 **NOT READY FOR RELEASE**。

## 170. 2026-10-11 P6 锁定 Windows wheel 的 PE 导入候选边图

- **AUD-114（P6，PE 导入清单尚未区分制品内候选与跨制品同名）：** §166 的 2,654 项直接导入只有来源 PE 文件和 DLL 名，无法直接审阅同一 wheel 归档中是否存在同名 PE 成员；跨 wheel 按 DLL 名合并又会把“同名”误说成实际链接关系。
- **整改：** 新增 [`map_locked_pe_import_edges.py`](../scripts/map_locked_pe_import_edges.py)，按 `uv.lock` 的包名、版本、wheel 文件名、平台与 artifact SHA-256 复核输入行，再以 Windows 大小写不敏感的 basename 只查找同一个 artifact 内的 PE 成员。每个普通/延迟导入出现位置各保留一行；歧义目标会显式列出，不合并重复导入。source/target 都保留 artifact/member SHA-256、成员路径、架构、wheel 平台及 RECORD 状态。
- **结果：** [`windows-pe-import-edges.jsonl`](windows-pe-import-edges.jsonl) 为 2,654 行，SHA-256 `fac1648ddee9333cff8025a7f7cd5a431be553dd778e840c884974f4ac2df29b`。其中 266 项成为 44 个 DLL 名的同制品文件名候选；2,388 项、53 个 DLL 名在各自来源制品所清点的 PE 成员中没有同名候选（全量 PE 成员共 419 个）；0 个歧义，所有已匹配候选的 source 与 target wheel-machine 布尔核对均为 true。8 项为 delay import。输入 PE 清单 SHA-256 `1e620e1ee71ada28f2e958d43017eb15ce311061507e168673611a8104780ca0`；锁文件 SHA-256 `f4fc838d6f52555ca03ccf378c67e2a988666928904ff14bfab6d4af7c88f31b`。该历史边图沿用初版路径比对产生的 RECORD 状态；§172 规范化反斜杠后重建，当前 419/419 RECORD 状态通过。
- **验证：** `tests/unit/test_locked_pe_imports.py` **21 passed**；Ruff check 和 `py_compile` 通过。覆盖同制品大小写匹配、重复/延迟导入保留、歧义、其他 wheel 同名文件不连边、错误锁文件绑定、伪造 artifact SHA、重复 JSON 键和输入边界。该定向结果不代表完整 Python 套件重跑；611 passed / 29 skipped 仍是 §168 历史快照。
- **解释边界与状态：** “候选”仅由已哈希 wheel 归档内 basename 匹配得出，不证明 Windows loader 会选择/加载该文件，也不是动态加载、OS/API-set、Python runtime、静态链接、构建来源或完整 native BOM 图。其余 2,388 项标为 `unmatched_in_inventory`，不推断为依赖缺失；本图也不做跨 wheel 推断。P6 仍缺所有者发行/许可证决定、完整 native provenance/linkage 与 notice 适用性审查、远端 CI 和干净安装；P2/P4/P5 门槛也未关闭，项目继续 **NOT READY FOR RELEASE**。

## 171. 2026-10-11 P6 wheel 元数据覆盖与当前全套回归

- **AUD-115（P6，多个锁定 wheel 的 METADATA 未逐制品记录）：** SPDX 主 evidence 每个包只保存一个主 METADATA 条目。复核锁定 `uv.lock` 和私有 SHA-256 cache 后，发现 CTranslate2 4.8.2 的 10 个 wheel 和 Tokenizers 0.23.2 的 16 个 wheel 合计 26 个制品；其中 CTranslate2 的一个 Windows cp311 wheel 已是主证据，其余 25 个 wheel 尚未逐制品记录。Tokenizers 的 16 个 wheel 均没有 `License` 或 `License-Expression` 字段。
- **整改与证据：** 新增 [`verify_locked_wheel_metadata_audit.py`](../scripts/verify_locked_wheel_metadata_audit.py) 和 [`locked-wheel-metadata-audit.json`](locked-wheel-metadata-audit.json)。离线审计将每个 wheel 的 URL、SHA-256、大小与当前 `uv.lock` 对齐，再校验归档内 `METADATA` 的包名/版本/内容摘要，以及该成员在 `RECORD` 中的摘要和大小。26/26 个 wheel 通过；CTranslate2 10/10 个 METADATA 均显示 `License: MIT`，Tokenizers 16/16 个 METADATA 均未含两种许可证字段。JSON evidence SHA-256 为 `b4b06ab0d6a9ab28087dd59b699e79c6a6c2ee23134e30ed24a269c97146c7a0`。复核命令见本节下方。
- **边界与处置：** 这是制品身份、打包元数据和 RECORD 一致性证据，不是上游构建证明、Rust/C++ 原生组件 BOM、许可适用性结论或再分发批准。没有从 Tokenizers 缺失的 wheel 字段推断许可证；未更改 SPDX 的 `licenseDeclared` 或 `licenseConcluded`。后续应将 Tokenizers wheel 与固定源码版本、Cargo 依赖和随包 notice 对照，并由项目所有者确定实际发行范围。P6 仍未通过。
- **当前全套回归：** 当前 Windows Python 3.11.15 全套为 **617 passed、29 skipped**（94.35 秒）。29 项跳过包含 2 项未配置 native interop host path 的测试；其他为 Windows 不支持的 POSIX/FIFO/symlink 行为。该 Python 全套不覆盖 C# native harness、管理员服务/WFP、真实 P2 捕获、P4 听审或 P5 Desktop 会话。

```powershell
python scripts/verify_locked_wheel_metadata_audit.py --cache-dir <private-sha256-cache>
```

## 172. 2026-10-12 P6 全量制品元数据与 Windows RECORD 路径更正

- **AUD-116（P6，锁定制品元数据只覆盖少量 wheel）：** §171 只逐制品复核 CTranslate2 与 Tokenizers 的 26 个 wheel，无法说明其余锁定 wheel 和 source distribution（sdist）的元数据完整性。
- **整改与证据：** 扩展 [`verify_locked_wheel_metadata_audit.py`](../scripts/verify_locked_wheel_metadata_audit.py)，离线覆盖私有缓存及当前 `uv.lock` 锁定的全部 **235/235 制品：199 个 wheel、36 个 sdist、41 个包**。逐项核对锁定文件名、大小和 SHA-256，读取 wheel `METADATA` 或 sdist `PKG-INFO`，检查包名、版本与元数据摘要；对 wheel 另核验该元数据在 `RECORD` 中的哈希和大小。sdist 扫描设有成员数、解压总量、单成员与时间上限。结构化结果为 [`locked-wheel-metadata-audit.json`](locked-wheel-metadata-audit.json)，SHA-256 `b1dbbf4bb7a636cebe11cee8017ffdecfaa6a57eeb8b73383537c63c80421b9c`；缓存总大小 **2,097,567,472 bytes**。重放验证命令见本节末尾。
- **许可证元数据观察（不作结论）：** 44/235 条记录缺少 `License` 与 `License-Expression` 字段，分属 colorama、editables、pathspec、ruff、tokenizers、trove-classifiers；缺失字段不能推出许可证。唯一出现 wheel/sdist 字段值差异的是 Protobuf 7.36.2：sdist 写 `BSD-3-Clause`，7 个 wheel 写旧式文本 `3-Clause BSD License`（不是 SPDX 表达式）。当前 SPDX evidence 选用 sdist 中有效的 `BSD-3-Clause`；源码和 wheel 内对应 LICENSE 文件哈希一致。本次不改 `licenseDeclared`/`licenseConcluded`，仍需所有者确定发行范围并复核许可证适用性。
- **AUD-117（P6，Windows wheel 的 RECORD 项被误报缺失）：** §166/§170 的 PE 清单把 3 个 Ruff Windows wheel 中 `ruff.exe` 的 RECORD 行判成缺失。归档成员路径使用 `/`，这三个 RECORD 路径使用 ``；路径键未规范化，造成误判，而不是 wheel 缺少哈希/大小记录。
- **更正与 PE 证据：** `inventory_locked_pe_imports.py` 现在仅将路径分隔符规范为 `/` 后比对，同时在每行证据中保留原始 `record_path`。单元回归覆盖该 Windows 格式。重建后 419/419 PE 成员均有匹配且校验通过的 RECORD 哈希/大小；三种 Ruff 平台的 `ruff.exe` 均已验证。[`windows-pe-import-evidence.jsonl`](windows-pe-import-evidence.jsonl) SHA-256 为 `18236b199a2cd5e8d6db98beec04447546e799c9153a46085274c14c2ff570ae`；[`windows-pe-import-edges.jsonl`](windows-pe-import-edges.jsonl) SHA-256 为 `b7d594ec44d3d7af758b66140de1fa93fbee8e9e0cb898eb2bf0a86221662099`。边图 2,654 项导入中有 266 项同 wheel 文件名候选、2,388 项在清点 PE 成员中未匹配、0 歧义；这些候选不等于实际 loader 关系，未匹配也不说明依赖缺失。Playwright win32-tagged wheel 内 `node.exe` 是 AMD64 的架构观察仍保留。
- **验证：** PE 定向测试 **22 passed**；全量 Windows Python 3.11.15 套件 **618 passed、29 skipped**（269.56 秒）。metadata audit 脚本的 Ruff check、格式检查、`py_compile` 与 evidence 重放检查通过。Python 与静态归档检查都不代替 native harness、真实 WFP/service 或发布环境验收。
- **门槛与处置：** P2 生产 service/worker/WFP 和三条真实捕获，P4 长样本及人工听审，P5 新 Desktop invocation trace，P6 所有者发行范围决定、完整 native provenance/linkage/notice 审查、远端 CI 与干净安装仍开放。当前进程无管理员令牌或可连接管理员 endpoint；没有更改宿主 WFP/Firewall。项目保持 **NOT READY FOR RELEASE**。

```powershell
python scripts/verify_locked_wheel_metadata_audit.py --cache-dir <private-sha256-cache>
uv run --project skills/douyin-transcript --locked --no-sync pytest -q tests/unit/test_locked_pe_imports.py
uv run --project skills/douyin-transcript --locked --no-sync pytest -q
```

## 173. 2026-10-12 本机标准 UAC 管理员子进程探测

- **问题：** §172 记录当前 Codex shell 没有管理员令牌或可连接管理员 endpoint。用户授权代理自行查找可行的管理员操作方式后，需要区分“本机账号是否能通过标准 UAC 提权”与“Codex 主进程本身已提权”。
- **只读探测：** 本机为一台 Windows 11 Enterprise LTSC 设备，当前账户属于本地 Administrators 组；普通 Codex PowerShell 的 `IsAdministrator=false`。首次探测仅因调用了不存在的 Codex bundled PowerShell 路径而失败，未启动进程。改用系统 Windows PowerShell 后，通过标准 `Start-Process -Verb RunAs` 运行一次临时只读身份探针，返回 `IsAdministrator=true`、高完整性令牌；探针同时只读取了 `CodexSandboxService.OpenAI.Codex` 与 `IsoEnvBroker` 服务状态。没有通过替代路径绕过 UAC。
- **环境与边界：** 主机有 `wsb` CLI 和 Windows Sandbox 可执行文件，`wsb list --raw` 显示已有一个运行中的 Sandbox；本轮没有连接、修改或停止该既有环境。没有安装服务、创建 WFP session、添加防火墙/WFP 规则或改变系统网络策略。临时探针仅写入用户临时目录。
- **处置：** 本机可作为管理员测试主机，通过每次显式 UAC 确认的短期管理员子进程执行授权检查；这不等于当前 Codex shell 已提升，也不提供持久 broker/服务 endpoint。后续动态 WFP 验收应只在新建的可丢弃 Sandbox 或专用回滚环境内进行，不得在宿主执行全局 smoke filter。此结果只移除“本机无法取得管理员子进程”这一环境阻塞；项目仍缺生产 service、per-lease worker/identity、数值 IP connector、正式 WFP 策略与回滚、Chromium 受控启动及三条真实捕获。P2 继续 **OPEN / NOT PASSED**；P4/P5/P6 和总体发布门槛仍未通过。

## 174. 2026-10-12 P6 离线审计工具安全收口

- **审查范围：** 冻结工作树 Diff Scan 共 87 个审查项全部完成。脚本审查确认两个低危、需要本地操作者运行离线审计且制品哈希已被 `uv.lock` 接受的风险。当前 CI 未调用相关制品清点命令；这些问题位于维护工具，不是转写运行时路径。
- **AUD-118（CWE-400，wheel ZIP/RECORD 解析可造成维护工具内存耗尽）：** wheel metadata 审计和 NumPy native inventory 在检查成员数前构造完整 `ZipInfo` 列表；metadata 审计把 RECORD 全量转成 CSV 行列表，NumPy inventory 则无字节或行数限制地把 RECORD 写入字典。512 MiB 压缩制品上限无法限制这些对象开销。整改是在创建 `ZipFile` 前调用已有有界 ZIP 目录扫描器，拒绝超成员数或超中央目录上限的输入；metadata 审计另限制累计声明展开量及 RECORD 行数，NumPy inventory 将 RECORD 限制为 16 MiB/50,000 行。
- **AUD-119（CWE-150，归档路径可注入终端控制符）：** 成员名出现在验证异常中，多个 CLI 直接打印异常；原有处理只转义 CR/LF，未转义 ESC、双向控制和其他 Unicode 控制符。整改是在离线归档审计工具的 stderr 边界统一调用 `escape_terminal_controls()`，并覆盖 metadata/native/PE inventory、批处理、edge mapper 与 cache verifier。
- **证据与边界：** 安全 Diff Scan 使用冻结目标 `b166778ee5283591a1b799535b746ba198e38653`，扫描内容摘要 `codex-security-snapshot/v1:sha256:ae8633831a564f49bd80ddc6f19b20c999c89993fe57c03fe3d912f507ab9d19`。两项 findings 的本地复核结论均为低严重度；没有尝试触发内存耗尽或控制终端。该扫描报告描述冻结修复前源码；上述修复发生在冻结快照之后。
- **静态验证：** 7 个修改后的脚本通过 Python `compile()`；Ruff check 全通过；初次格式检查发现 `inventory_numpy_native_members.py` 需要重排，格式化后完成格式检查。未运行测试套件，也未下载或安装制品。
- **后续：** 可为这两个边界补充回归用例，验证超限 ZIP/RECORD 在 `ZipFile`/CSV 对象构造前拒绝，并确认异常里的 ESC、Bidi 和 Unicode 控制字符以可见转义形式输出。P6 的 LICENSE/发行范围、native provenance/linkage/notice、远端 CI 与干净安装门槛仍开放；项目仍 **NOT READY FOR RELEASE**。

## 175. 2026-10-12 冻结差异安全扫描封存

- **封存状态：** Codex Security Diff Scan `6ae4517b-7403-441d-a62c-5a4484fa3d07` 已完成并封存，87/87 个工作项关闭，覆盖 9 个源码安全面；发现 2 项低危，均为离线制品审计维护工具问题（CWE-400、CWE-150）。完整机器生成报告：`<local user path>`，SARIF：同目录 `exports\results.sarif`。
- **快照边界：** 报告针对 HEAD `b166778ee5283591a1b799535b746ba198e38653` 与冻结摘要 `codex-security-snapshot/v1:sha256:ae8633831a564f49bd80ddc6f19b20c999c89993fe57c03fe3d912f507ab9d19`。工作区在扫描进行中变化；两项修补在冻结快照之后完成，不能视作已被该报告重新审查。静态语法与 Ruff 检查通过，但本轮没有运行测试套件。
- **扫描覆盖边界：** 已完成的 87 项仅说明该冻结源码差异复核完成，不是项目发布验收。报告保留部署主机实际 ACL/路径与默认 Agent 模型供应商数据处理条款两个开放问题；P2、P4、P5、P6 外部验收门槛仍按 §174 记录。扫描用量记录为 26,672,311 tokens。


## 176. 2026-10-12 P4 长样本转写与默认模型文本校对

- **样本验收：** 用户提供 `<local user path>`。本地 PyAV 与 CLI 报告时长分别为 938.968 秒和 938.968435 秒（15 分 38.968 秒），满足 P4 至少 10 分钟的媒体长度门槛。CLI 状态为 `success`、`result_scope=raw_asr_only`、`llm_review_status=not_performed_by_cli`；私有输出目录 DACL 检查为 `ok`。
- **输出与完整性：** 原始稿为 `<local user path>`，SHA-256 `已在本机验证（具体值未列入报告）`。按用户早先授权，当前 Agent 默认模型完成文本校对和标点整理，CLI 创建独立侧车 `<local user path>`，SHA-256 `已在本机验证（具体值未列入报告）`。复核确认侧车非空、包含模型文本校对范围提示、原始“未经人工逐字校对”提示已替换；原稿哈希前后相同，未覆盖。
- **格式检查：** 侧车有 20 段，每段都含中文句读标点；最长连续无标点片段为 26 字。校对纠正了语境支持度较高的 ASR 同音术语并补足逗号、句号等。该检查是文本整理证据，不证明文字与音频逐字一致。
- **人工复听项：** 建议听审开场对流量来源/ASIN 的说明；词根分类与其案例名；词级打法对应年份、排名数字，以及竞价示例的局部表达。逐字稿没有带时间戳，因此本报告按段落主题标出复听位置，不推测时间码。正文未复制到仓库或报告。
- **验收状态：** P4 的 10 分钟以上样本、原始转写、默认模型文本校对和标点侧车已完成；仍需对上述三处人工听审，并在新 Desktop 会话验证默认模型调用、校对披露及端到端保存。P2 生产隔离、P5 新会话发现/调用和 P6 所有者发行决策/远端发布验收仍开放，整体仍 **NOT READY FOR RELEASE**。


## 177. 2026-10-12 P4/P6 当前证据复核、全套回归与状态同步

- **P4 证据复核：** 用户给出的第二个样本仍可从其本地位置读取；§176 记录的 938.968435 秒时长超过 10 分钟。复核 raw 与 `.reviewed.md` 私有侧车的 SHA-256 均与 §176 一致；侧车非空，20 个逐字稿段落都有中文句读标点，最长连续无标点片段 26 字。正文未复制到本报告。人工听审仍未完成；没有逐字稿时间戳，§176 的主题提示不冒充时间码或听审结果。
- **Python 回归：** 在当前 Windows Python 3.11.15 环境运行 `uv run --project skills/douyin-transcript --locked --no-sync pytest -q`，结果为 **618 passed、29 skipped**，用时 163.66 秒。两个 native interop 用例因未配置 host path 跳过；其他平台跳过项要求当前 Windows 不具备的 POSIX FIFO、权限或 symlink 行为。与 §172 相同的通过/跳过计数得到再次确认；本次不能代替 Python 3.12 或 Linux/macOS 矩阵。
- **P2 原生 harness 边界：** 尝试用 `dotnet run --no-restore` 执行 capture-pipe 与 WFP policy harness，两个命令均因当前环境没有安装 .NET SDK 而失败（系统仅报告 runtime/未发现 SDK）。因此本轮不对原生代码作构建或 harness 通过声明；§169 的 18 个 DNS policy 场景和 Release 构建仍是历史证据。P2 继续缺可安装 SCM service、认证完整作业 IPC 客户端、per-lease worker/identity、Chromium process-tree 与 egress isolation、DNS numeric-IP connector、WFP 实际策略及三条成功真实 capture。
- **管理员探针状态更正：** §173 的后续证据表明，标准 UAC 启动的只读高完整性子进程成功；§148“执行器阻止在创建前”的结论已过时。调用中的 Codex 仍是标准用户，且没有安装服务或修改宿主 WFP/Firewall。只读提权探针不闭合 P2 动态验收。
- **P6 当前检查：** 独立复核再次确认两份锁文件的 `uv lock --check`、235 个锁定制品 SHA/大小和 package metadata 审计、SPDX member evidence（41 packages / 210 artifacts / 1,149 supplemental members）及固定 SPDX 2.3 schema 校验通过。现有 CI 全套 pytest 包含 `test_checked_in_inventory_matches_lock_and_evidence_identity`，对照 lock、evidence 与 checked-in SBOM 的包身份、namespace digest 和声明字段；这项已有检查不需要重复新增一个静态脚本。它仍不证明 license applicability、native provenance/linkage 或发行许可。
- **文档状态：** `ACCEPTANCE.md`、`RELEASE_CHECKLIST.md`、`RELEASE_REPORT.md`、`P1_REPORT.md`、`P2_REPORT.md` 与 `OWNER_DECISIONS.md` 的当前摘要现按 §176/§177 区分 P1 5 分钟样本与 P4 长样本，并修正 §173 UAC 只读探针状态。旧快照保留为历史记录。P4 人工听审、新 Desktop P5 调用、P2 生产隔离/真实捕获，以及 P6 所有者决定和远端验收仍开放；整体仍 **NOT READY FOR RELEASE**。


## 178. 2026-10-12 pinned .NET SDK、原生 harness 与静态检查

- **SDK setup:** 为重跑仓库要求的 native harness，依据 `native/windows/capture-pipe/global.json` 固定版本 10.0.401，使用通过 Authenticode 校验的 Microsoft `dotnet-install.ps1` 安装到用户 LocalAppData 私有目录；没有改系统 PATH、Windows 服务、WFP 或 Firewall。SDK 报告 `10.0.401`，Windows x64。
- **P2 source harnesses:** Capture-pipe x64 Release `dotnet run --no-restore` 通过：18 个 bounded lease DNS policy 场景、bounded DNS wire parser/UDP-TCP fallback/socket-cancellation fixtures，以及 named-pipe first-instance/identity/fail-closed/framing/artifact/disconnect harness。WFP policy harness **10/10** 通过，覆盖双 lease 不可互借、明确 default deny 与精确 permits、确定性、SID/输入拒绝和 native filter DTO materialization。两个项目的 `dotnet format whitespace --verify-no-changes` 均通过。以上均为离线源码/harness 证据：没有 SCM service、worker identity、真实 Chromium、真实 WFP filter 或网络 capture；不能关闭 P2。
- **Python / P6 static checks:** §177 全套 Python 结果为 **618 passed、29 skipped**。随后 Ruff check、Ruff format（79 files）、应用与 schema-check 两份 `uv lock --check`、Git-visible sensitive-file scan、SPDX 2.3 schema check，以及全仓库 `git diff --check` 均通过。Git 仅提示若干工作副本的 LF 将在后续 Git 写入时规范成 CRLF；没有 whitespace error。
- **Remaining gates:** P2 缺生产服务/逐 lease 隔离/真实 capture；P4 缺人工听审和 fresh Desktop 数据流验收；P5 缺 fresh Desktop skill-discovery/invocation trace；P6 缺所有者许可证/发行范围/仓库远端决定及获授权的远端矩阵与干净安装。项目仍 **NOT READY FOR RELEASE**。


## 179. 2026-10-12 P4 时间戳侧车与人工复听定位

- **运行：** 对 §176 的 938.968435 秒本地 MP4 执行锁定 CLI `transcribe --timestamps --force --processing-timeout-seconds 1800 --json`。CLI 返回 `status=success`、`result_scope=raw_asr_only`、`llm_review_status=not_performed_by_cli`，并报告输出目录 DACL `ok`。`--force` 使用另存策略；原 §176 raw 文件未覆盖、SHA-256 仍为 `已在本机验证（具体值未列入报告）`。
- **时间轴：** 新 raw ASR sibling `私有 raw ASR 侧车`（13,860 bytes）；时间轴 sibling `私有时间轴侧车`（19,887 bytes，SHA-256 `已在本机验证（具体值未列入报告）`）。仅解析时间戳得到 **533** 项，按秒单调不减，范围 00:00–15:37，不超出源媒体时长。它是未经新模型复核的 ASR 时间轴，不能当作校正稿或声学真值。
- **复听定位（只报告时间与主题，不复制逐字稿）：** 01:11 流量来源/ASIN；05:40 竞价示例；08:41 年份/排名；08:59 词根分类。主题由时间轴文本匹配定位；没有播放或听审音频，不能据此声称任何段落准确。
- **边界：** 原始稿和新时间轴保存在私有应用 output 目录。此次再转写仍无转写正文进入 CLI JSON 输出/本报告的证据边界与原产品约束一致；这不是 fresh Desktop 宿主隐私验收。P4 人工听审和新 Desktop 验收继续开放。


## 180. 2026-10-12 冻结差异安全扫描、扫描后修复与验收边界

- **扫描记录：** Codex Security Diff Scan `02fce2a3-db34-4838-888c-1be56d1914b3` 已封存。扫描目标是冻结的未提交工作树快照，revision `b166778ee5283591a1b799535b746ba198e38653`，snapshot digest `codex-security-snapshot/v1:sha256:a1955fc7b05089cdccc2973e99dc9c895f5262426ce1c3ea9aea4abfe3faa273`。差异清单共 207 个文件，90/90 条源代码/配置 worklist 审核项已完成逐文件复核。其余文档、测试夹具和生成物没有全部逐行做源代码审查，所以本次覆盖标记为 partial。扫描期间工作树继续发生变化；封存结果只对应上述快照，不能把后续修复算作已由该快照扫描。
- **AUD-120（低，诊断脚本 cleanup ownership）：** `ChromiumAsUserTokenSmoke.ps1` 与 `UserSidChromiumSmoke.ps1` 在检测固定暂存/profile 目录已存在并拒绝继续后，旧版 `finally` 仍无条件递归删除同一路径；如果手动在权限较高的宿主执行，可能删除预置数据。修复加入严格创建和创建所有权标记，只清理由本次调用创建的目录；`UserSidChromiumSmoke` 的固定 profile 清理也改为所有权保护。修复晚于扫描快照；两个脚本的 PowerShell AST 解析通过，未运行脚本或删除操作。对策是以后所有清理都必须由本次成功创建记录授权，禁止通过固定路径推断所有权。
- **AUD-121（低，ProcessSingleton lockfile 覆盖）：** `ProcessSingletonApiProbe.ps1` 旧版把调用方的 `ProfileDirectory` 拼成 `lockfile`，以 `CREATE_ALWAYS` 和 `DELETE_ON_CLOSE` 打开，可能截断并删除既有文件。现改为排他 `CREATE_NEW`，发现既有文件即失败且不改动它。PowerShell AST 解析通过；未执行探针或 Windows 文件操作。对策是对 caller-selected 文件只使用排他新建，禁止覆盖及无所有权删除。
- **AUD-122（低，inventory 临时文件符号链接）：** `inventory_locked_artifact_members.py` 旧版使用可预测的相邻 `.tmp` 路径并以普通写模式打开；若路径被预置为符号链接，会跟随并截断目标。现改为在同目录随机、排他创建临时文件，写入后 `fsync` 并用 `os.replace` 替换，失败时仅清理自有临时文件。Python AST、Ruff check 与 Ruff format 检查通过；未执行此工具或测试套件。对策是继续保持随机独占创建，并避免对攻击者可写输出目录运行离线维护工具。
- **候选排除与保留风险：** CIDR 候选确认是误报：`0xFF << 6` 得到 `0x3FC0`，其低字节 `0xC0` 正确匹配 `100.64.0.0/10`，`100.68.0.1` 会被拒绝；新增断言仅是策略回归覆盖，不是缺陷修复。`urls.resolve_input()` 与 `downloader.download_media()` 仍保留调用进程网络能力，但全仓静态调用检查未找到非测试生产调用方；当前 pipeline 经完整 capture client 门禁且缺 client 时 fail closed。因此将其记为未来接入前的证明缺口，不作为当前可利用生产漏洞或 SSRF 结论。
- **扫描范围与验证限制：** 三项问题均来自人工调用的 Windows 诊断脚本或离线维护工具，评级为 low；三项修复均发生在冻结快照之后。修复后只做了 PowerShell AST、Python AST、Ruff 与格式静态检查，没有执行破坏性脚本、没有为这些补丁运行测试套件。此前 §177 Python 全套为 618 passed/29 skipped，§178 原生 harness 与格式检查通过；这些历史结果不是本轮扫描后修复的动态回归。未安装 SCM service，未修改宿主 WFP/Firewall，没有验证生产出口隔离。
- **P4 当前证据：** §176 的 938.968435 秒样本已本地转写并由当前 Agent 默认模型生成独立校对稿，原始稿 SHA-256 保持不变，20 段均有句读标点；§179 的独立时间轴有 533 个单调时间点。时间轴只帮助定位复听片段，不是听审证据。用户已提供样本路径，但人工逐段复听和新 Desktop 会话的数据流/隐私验收仍开放。
- **后续对策与总体状态：** 发布前应对修改后的当前工作树再做一次安全差异审查；在隔离且可回滚的环境中，针对三项修复补充“不删除/不覆盖既有哨兵文件”的动态回归；补完剩余差异文件审阅。P2 仍需生产 service、认证完整作业 client、per-lease worker/identity、Chromium 进程树与 WFP 集成，以及三条不同授权视频的成功端到端捕获；P4 需人工听审和 Desktop 隐私验收；P5/P6 外部门槛仍开放。项目整体保持 **NOT READY FOR RELEASE**。逐项安全审核与对策另见 [`SECURITY_SCAN_REPORT_2026-10-12.md`](SECURITY_SCAN_REPORT_2026-10-12.md)。

## 181. 2026-10-12 扫描后清理所有权复核与 P2 数值 IP connector

- **AUD-123（低，诊断临时数据清理仍有未绑定路径）：** 对 §180 修复路径做同类清理复核时，发现 `ChromiumInteractiveHeadlessSmoke.ps1`、`ChromiumAsUserTokenSmoke.ps1`、`AppContainerIdentitySmoke.ps1` 和 `UserSidChromiumSmoke.ps1` 还有一次性工作目录、测试账户 profile 或 Chromium staging 的清理分支仅凭路径存在执行删除。即使路径由 GUID/随机账户名构造，创建失败或临时路径碰撞后也不应推断本次拥有该对象。现在这些脚本显式记录当前调用成功创建的目录/账户，仅在所有权标记为真时清理；目录创建失败也不会由 `finally` 删除既有内容。该问题仅涉及手动 Sandbox 诊断脚本，不是产品 URL 捕获路径。
- **AUD-120–123 安全回归：** 新增 `tests/unit/test_sandbox_cleanup_ownership.py` 对关键脚本的创建/清理所有权守卫及 ProcessSingleton `CREATE_NEW` 锁文件契约作回归检查。`test_artifact_member_inventory.py` 新增相邻旧式 `.tmp` 哨兵文件用例，确认原子写入不改写其内容；本机 Python 定向组 **7 passed、1 skipped**。符号链接变体因当前 Windows 未授予创建 symlink 的权限而跳过（WinError 1314），不把该跳过记作通过。五个修改/相关 PowerShell 文件 AST 解析 **5/5**；两个 Python 测试文件 Ruff check 与 format check 均通过。完成后的当前工作树全套 Python 回归为 **624 passed、30 skipped，255.56 秒**。没有运行会修改 Sandbox、用户账户或 WFP 的诊断脚本。
- **P2 数值 IP TCP connector：** 新增 `LeaseTcpConnector`，只接受已验证 DNS 固定地址集合中的公网地址，先从按租约提供者取得精确 IP:443 许可，再使用数值 `IPEndPoint` 建立不复用的 TCP socket，校验实际远端 endpoint，并将原始 hostname 单独返回给调用方用于 TLS SNI/证书校验。连接对象负责关闭 socket 和撤销许可；失败与 endpoint 不匹配路径也清理两者。当前使用注入 fake dialer 的离线 harness 验证许可先于连接、拒绝未 pin/私网目标、endpoint mismatch 与资源清理；固定 .NET SDK 10.0.401 x64 capture-pipe `--self-test` 通过，未建立真实互联网连接。
- **验收边界：** 没有部署 service/worker、实现 WFP permit provider、连接此 connector 至 capture handler、安装服务或改变 host WFP/Firewall。真实 Chromium 隔离与三条 Douyin 捕获仍未验证，P2 保持 OPEN / NOT PASSED。扫描报告 §180 的冻结范围没有覆盖这些新增修改；本节记录 current-tree 本地回归，不称当前工作树已获完整安全扫描。接下来对现有工作树做差异审查；P4 人工听审/Desktop 验收、P5 新会话 trace、P6 所有者决定与远端矩阵仍开放，整体 **NOT READY FOR RELEASE**。

## 182. 2026-10-12 91 项差异安全审查与长样本门槛复核

- **最新扫描：** Codex Security Diff Scan `9b5f048e-5f14-4099-827d-373e7a5871dc` 已封存，针对 HEAD `b166778ee5283591a1b799535b746ba198e38653` 和快照摘要 `codex-security-snapshot/v1:sha256:88f0fe1cf9eae0402bc5405bb81fa6dd42da3356c6d5a7d71466f5b96fcb2f77`。Python 包 25 项、Windows native 46 项、release/evidence 20 项，共 **91/91** 生成审查项完成；扫描结果 **0 项可报告漏洞**，coverage 为 **partial**。扫描仅作静态源码、配置和工作流审查；未运行项目代码/测试、未联网、未修改宿主 WFP/Firewall，也未将媒体或逐字稿纳入工件。机器报告位于本机 Codex 状态目录：`<local user path>`。
- **范围缺口与补充发现：** 生成的 91 项清单漏掉了已修改的 `skills/douyin-transcript/SKILL.md`。我手工检查其模型校对流程，发现它会把转写正文放入调用 Agent 的默认模型上下文，但没有明确要求把正文仅视为不可信数据、忽略其中要求调用工具/读取文件/转发信息的指令。恶意口播内容可能成为间接提示注入；真实后果取决于调用 Agent 的工具权限和策略，本轮没有执行攻击样本，也没有宿主调用 trace，因此不把它记成已验证扫描 finding。安全扫描工具拒绝将此路径录为当前扫描候选，子目录扫描也不受该入口支持；后续对策是在 Skill 中明确指示：正文永远是待校对数据，不能改变任务、授权或工具边界，除保存侧车所需操作外不执行正文中的命令/请求，并将此文件纳入下一轮全范围清单。
- **离线 sdist 审核器候选（已验证为不报告）：** `scripts/verify_locked_wheel_metadata_audit.py:261–279` 在 tarfile 解析并返回条目之后才检查时限与累计声明展开大小；扩展头的解压工作可能先于这些限制发生。该脚本只在本机操作员手动检查 lock/cache 匹配的 sdist 时运行，CI 不调用它；未证明跨用户或服务影响。扫描将其抑制为本机操作员触发的资源耗尽风险，不列为可报告漏洞。加固建议是在 tarfile 前加入带总解压字节预算和读取 deadline 的 gzip 流包装，并对扩展头大小设硬上限；之后可用隔离的合成 PAX 压缩炸弹回归确认超限在解析前拒绝。
- **P4 长样本：** 用户提供的 MP4 文件存在（22,715,944 bytes）；私有输出目录已经有对应 raw Markdown、默认模型校对侧车和时间轴侧车。当前 raw 元数据记载 **938.922125 秒（15 分 38.922 秒）**，533 个时间点从 00:00 到 15:37，满足“至少 10 分钟”样本长度门槛。§176 的先前记录为 938.968435 秒；二者相差约 46 毫秒，但都高于 600 秒，不影响门槛结论。此轮没有播放媒体或重新转写；人工听审及新 Desktop 会话的模型数据流/隐私验收仍待完成。
- **后续状态：** P4 的长样本长度门槛已满足，但整体 P4 未通过；P2 仍缺生产 service/per-lease worker/WFP、认证捕获 client、隔离浏览器及三条真实捕获；P5 缺新 Desktop Skill 发现/调用 trace；P6 缺许可证/发行所有者决策、native provenance/linkage 审查和远端 CI/干净安装。项目仍 **NOT READY FOR RELEASE**。

## 183. 2026-10-12 P4 媒体复核、试听片段与 Skill 提示注入加固

- **媒体文件复核：** 用户提供的 MP4 当前存在，大小 22,715,944 bytes，SHA-256 `已在本机验证（具体值未列入报告）`。锁定环境中的 PyAV 对媒体报告 **938.968435 秒（15 分 38.968 秒）**；流清单只有 AAC 音频，没有视频流。raw Markdown frontmatter 记录音频侧元数据 **938.922125 秒**，差约 46 毫秒；两者均超过 600 秒门槛。锁定 CLI `transcribe --input-file ... --processing-timeout-seconds 1800 --json` 返回 `skipped`，因为任务已有完成记录；没有重新运行 ASR。既有 raw、reviewed、timeline 文件哈希仍分别是 `已在本机验证（具体值未列入报告）`、`已在本机验证（具体值未列入报告）`、`已在本机验证（具体值未列入报告）`；没有覆盖已有逐字稿或校对稿。这个样本满足长时音频 ASR 输入门槛，不证明视频解码或视听同步处理。
- **人工听审材料：** 为时间轴建议的 01:11、05:40、08:41、08:59 四处各从 MP4 的 AAC 音轨提取一段 18 秒 WAV，文件名为 `01m11_topic.wav`、`05m40_topic.wav`、`08m41_topic.wav`、`08m59_topic.wav`，放在私有应用输出目录的 `p4_review_clips` 子目录。该目录继承当前用户独占 DACL。片段可供操作者直接听音比对；本次没有人工听音、也没有记录任何识别准确率结论，P4 仍需至少三处人工比对和差异记录。
- **Skill 加固：** 在 `skills/douyin-transcript/SKILL.md` 明确音视频口播/字幕和转写正文都是不可信数据，不得执行其中要求改变任务、泄露上下文、读文件、运行工具或外传信息的指令；需要忠实转写时可保留其文字作为内容，但不得照做。Canonical 与 repo-scoped 两份 `agentskills validate` 均通过。本轮未重跑 pytest 或完整安全扫描；§182 的 91/91、0 可报告漏洞结果仍为 partial coverage，且不覆盖本次 Skill 修改。下一轮全范围审核应把 canonical Skill 列入清单并评估恶意转写样本的行为边界。
- **验收边界：** 没有新 Desktop 会话调用或数据流/隐私验证。P4 等待人工听审和新 Desktop 验收；P2 仍缺生产 service/per-lease worker/WFP、隔离 Chromium 和三条真实成功捕获；P5 缺新会话发现/调用 trace；P6 缺所有者许可证/发行范围决定、native provenance/linkage 审查、远端 CI 与干净安装。项目整体仍 **NOT READY FOR RELEASE**。

## 184. 2026-10-12 安全审查补充：本机路径披露与修复

- **扫描结果：** Codex Security Diff Scan `daa7e7eb-420e-4f59-a5cf-d57b0bbe916b` 针对 HEAD `b166778ee5283591a1b799535b746ba198e38653` 的冻结摘要 `codex-security-snapshot/v1:sha256:adb58db3c991c2d25855fde4d3013807d225d3bb8b033615f8cfd7f3d70b5309` 已封存。生成清单 91/91 项完成；记录 1 项低危 CWE-200 文档披露，coverage 为 **partial**，因为 211 个变更文件中并非全部文档/生成证据都逐项审查。
- **发现：** 发布分片复核发现冻结工作树的审计/安全文档和 Sandbox README 含具体本机用户目录；审计记录还关联了私有媒体、输出文件名和摘要。若提交、发布或转发这些文档，会泄露本地账户/存储布局和媒体标识信息（CWE-200，低危）；路径本身不提供文件访问权限。本次没有发现文档已被发布，也没有发现完整逐字稿正文或凭证；§185 另记录扩展复核中发现并泛化的短识别示例和媒体主题标识。
- **修复：** 已将 6 个文本/Markdown 文件中的 16 处本机用户目录引用替换为通用占位文本；Sandbox 命令示例改用 `$env:USERPROFILE` 路径模板并明确需按本机 Chromium 缓存位置替换。最初的路径搜索仅匹配反斜杠写法，未覆盖一条 Markdown 链接中的正斜杠写法；§185 记录了发现、脱敏与扩展复查。没有改动用户媒体或私有输出目录。
- **扫描边界：** 此问题由人工补充审查在冻结扫描快照中发现，发生在 91 项生成清单之外；安全扫描候选记录器要求候选至少锚定一个生成清单文件，因此未接受这些文档路径作为机器候选。故正式扫描的 91 项结果不能覆盖这项文档发现；修复发生在扫描快照之后，仍应在下一次全范围差异扫描纳入文档/生成文件。发布前继续执行路径脱敏检查。
- **验证：** 当时的反斜杠路径模式搜索无命中，但未匹配到正斜杠路径写法；该遗漏及后续扩展扫描见 §185。`git diff --check` 无空白错误，仅报告既有 LF/CRLF 转换提示。未运行项目代码或测试。项目总体仍 **NOT READY FOR RELEASE**，P2/P4/P5/P6 门槛保持开放。

## 185. 2026-10-12 补充文档与结构化证据审阅

- **范围：** 对补充审阅中指出的项目计划、许可证审查、基准、排障指南、P1/安全报告及其他指定文档作一致性复核；另对 23 个变更 JSON/JSONL 文件进行结构、重复键、敏感路径/文本和已记录完整性检查。没有修改结构化证据文件，也没有运行项目测试或代码。
- **AUD-124（P6，历史 PE 清单被误称为当前修正证据）：** `THIRD_PARTY_LICENSE_REVIEW.md` 曾将 `windows-pe-import-evidence-complete.jsonl` 指为经过 §172 RECORD 分隔符修正的当前清单。但该 419 行文件是 §166 初始快照，仍有 416 个 `verified` 和 3 个 Ruff `missing_from_record` 状态；正确的当前证据是 `windows-pe-import-evidence.jsonl`，419 行均为 `verified`。已修注文档区分历史与当前文件，并注明 PE import edge map 绑定到修正文件摘要；两个 JSONL 证据本身保持原样，避免重写历史记录。
- **其他文档更正：** 扩展路径扫描后发现一条旧审计记录使用带用户目录结构的正斜杠路径，且同段落带有短识别纠错例词和媒体主题标识；已删除路径与样本标识，并将纠错例子改写为一般流程说明。初次 §184 搜索只检查反斜杠路径，因此此前“无命中”结论范围不足。另将计划中的 Skill 草稿指示改为先前用户授权下由调用 Agent 默认模型审阅独立侧车，不把转写正文贴入对话；远端安装示例要求使用已审阅的固定版本；Benchmark 将“Peak RAM”修正为实测 RAM；Troubleshooting 的登录诊断增加 `browser_isolation=ready` 与 `douyin_urls=ready` 前置条件。其余所审文档/清单交叉引用未发现新的可行动不一致。
- **结构化证据检查：** 23/23 个审阅对象解析与结构/重复键检查通过，未发现凭证、具体用户路径或逐字稿正文；PE 历史 JSONL 中 3 条旧 `missing_from_record` 状态与当前更正清单差异一致，属于已标明的历史误判。此检查不重新读取私有 wheel 缓存，不构成许可证适用性、制品来源或运行时链接结论。
- **安全扫描边界：** §184 的正式 Diff Scan 仍封存于此前冻结摘要；上述文档修订晚于快照，不会反向覆盖该扫描 finding。扫描记录 91/91 生成审查项完成、1 项低危 CWE-200，整体 coverage partial；本节是当前树的人工/结构化补充复核，不是全仓重新扫描。未运行项目测试；路径检查及 `git diff --check` 在修订后复核通过。
- **状态与对策：** P4 的 15 分 38.968 秒样本长度已达标，四段试听剪辑尚待人工对照；P2 仍缺生产 service/逐租约隔离/WFP/浏览器隔离与真实捕获；P5 缺新 Desktop 调用 trace；P6 缺所有者发行/许可证决定、native provenance/linkage/notice 审阅及远端 CI/干净安装。整体仍 **NOT READY FOR RELEASE**。下一步按 §185 所列补齐人工听审与各外部验收，并在发布前将文档和生成证据纳入完整差异审查。

## 186. 2026-10-12 当前工作树回归与 P2 IPC 身份上下文

- **P2 代码变更：** `CapturePipeHost` 在固定握手认证并通过 `ClientPeerPolicy` 后，创建内部 `CaptureExecutionContext`，把可信 `PeerIdentity` 和服务端生成的 operation ID 显式传给 `ICaptureWorker`。worker 不再只能收到 URL-bearing request；调用方 JSON schema 没有身份字段，不能伪造该上下文。`FailClosedCaptureWorker` 仍是服务 bootstrap 默认实现，继续对捕获请求返回 `BROWSER_ISOLATION_UNAVAILABLE`。该变更只是租约执行架构的身份传递基础，不会创建 Windows 隔离身份、启动进程监督、安装 WFP 策略或启用 URL 捕获。
- **原生回归：** 固定 .NET SDK **10.0.401 x64** Release `--self-test` 通过，涵盖 SCM 生命周期/受保护配置 fail-closed harness、18 个离线 DNS policy 场景、数值 IP connector fake-dialer、DNS wire/UDP/TCP/cancellation，以及 named-pipe identity/framing/artifact/disconnect harness。新增断言验证 worker 收到的 PID、session ID、user SID 与服务端认证到的当前调用方一致。配置 `DOUYIN_CAPTURE_PIPE_DOTNET` 与 `DOUYIN_CAPTURE_PIPE_DLL` 后，Python/.NET Windows named-pipe integration **2 passed**，覆盖认证、artifact digest 和取消/排空。
- **Python 回归：** Windows Python 3.11.15 全套 **624 passed、30 skipped，435.43 秒**。这次全套在 C# context change 之前完成；C# 变更后的相关覆盖由上述 native Release harness 与 2 项互操作用例提供。默认回归的两个互操作测试因未配置 host 路径跳过；其他跳过项涵盖 Windows 本机 symlink 权限限制、POSIX 专属行为。`ruff check` 与 `ruff format --check` 通过（80 个文件）；`dotnet format --verify-no-changes` 通过；`git diff --check` 退出码 0，仅显示仓库当前 LF/CRLF 自动转换提示。
- **长样本核验：** 用户新给路径对应的媒体由锁定 PyAV 读得 **938.968435 秒**，AAC 音轨；长度和既有 §183 样本一致。既有任务已有 raw、默认模型校对和时间轴结果，因此未重复 ASR、未覆盖私人输出。P4 仍待至少三处人工听音比对与新 Desktop 模型/数据流验收；四段私有试听剪辑已在 §183 记录。
- **验收边界与下一步：** 未安装 Windows service，未修改宿主 WFP/Firewall，没有公网捕获或三条视频验收。P2 继续 fail closed；还需逐租约低权限身份、受监督 Chromium/worker、生产 WFP provider、service 安装/回滚及隔离环境动态矩阵。P5 需要新 Desktop Skill 调用 trace；P6 仍待 owner LICENSE/发行范围决策、native provenance/linkage 审阅、远端 CI 和干净远端安装。§184 正式 security scan 是冻结且 coverage partial 的快照，不覆盖本节 C# 和当前文档改动；发布前需新的全范围审核。项目总体 **NOT READY FOR RELEASE**。

## 187. 2026-10-12 当前工作树安全差异扫描

- **结果：** Codex Security 工作树差异扫描以 HEAD `b166778ee5283591a1b799535b746ba198e38653` 为基线；扫描器生成 91 条源码/配置审查项，全部关闭，0 项可报告漏洞。该结果没有发现本次 C# 身份上下文变更的新漏洞。
- **覆盖：** 当前差异总计 211 个文件。91 条源码/配置审查项完成；剩余非 worklist 的测试、文档和生成证据没有在本扫描中全部逐项审查，因此整体 coverage 为 **partial**。§185 已另行检查选定文档和 23 个 JSON/JSONL；该补充审阅不能替代其余文件的完整覆盖。扫描没有 delegated reviewer，按父线程顺序审查。
- **边界：** 扫描报告由 Codex Security 工具生成并保存在其私有扫描工作区，没有复制进项目目录。没有安装服务或更改宿主 WFP/Firewall。P2 仍缺生产隔离与三条真实捕获；P4 仍缺至少三处人工听审及新 Desktop 数据流验收；P5/P6 仍缺新会话调用、所有者许可证/发行决策及远端验证。项目整体 **NOT READY FOR RELEASE**。

## 188. 2026-10-12 当前工作树安全审查与本地资源耗尽对策

- **扫描记录：** Codex Security 全工作树扫描 `8dae9a5d-b5d9-4626-9c82-448e023bae2c` 针对 HEAD `b166778ee5283591a1b799535b746ba198e38653` 的冻结快照 `codex-security-snapshot/v1:sha256:e4df3d78f98a4834f4420e95b49698c2d9602f81b973a3420c947f63d2e2eac8`。扫描清点 211 个文件，39 个完成重点源码复核，172 个文件尚未逐项审查，整体 coverage 为 **partial**；属于静态源码审查，不代表运行时或远端验收。正式扫描报告保存在本机 Codex Security 私有状态目录，未复制进仓库。
- **AUD-125（P3/低危，显式共享输出目录中的无界本地哈希）：** 当操作者显式选择共享输出目录，其他本地用户又能写入已完成任务的 Markdown 或时间轴文件时，后续默认 `--skip-existing` 会重新校验文件；`tasks.py` 的 SHA-256 读取按 1 MiB 分块直到 EOF，却没有总字节上限。攻击者可以用超大文件令重复任务消耗无界本地读取 I/O。需要同时具备共享目录写权限并等待/诱使操作者再次运行本地任务；默认隐式输出路径会做私有目录检查，不能把该条件性风险泛化为远程攻击。
- **对策：** 在单个已打开文件句柄上先检查文件类型和大小，再按输出生成器的硬上限读取、计算摘要；将 Markdown 与时间轴的容量上限分别绑定到其格式约束，并对尺寸变化或读取超限安全失败。保留对媒体文件的独立哈希策略。建议补充超限 Markdown/时间轴拒绝以及文件替换竞态回归。此次没有修改该代码，也没有运行测试，因此该发现仍未修复。
- **入口/文档一致性：** 源码复核未发现当前默认 CLI URL 入口可绕过隔离直接联网：短链 dry-run 是本地检查，URL 捕获在捕获服务/浏览器隔离未就绪时 fail closed。扫描发现 CLI 参考文档仍称 dry-run 会发起有界 HTTPS；已更新 `skills/douyin-transcript/references/CLI_REFERENCE.md`，明确 dry-run 不联网且短链不解析。捕获 broker、native worker 与 WFP 仍是未启用/默认 fail-closed 的实现，不能视为生产隔离或真实捕获证明。
- **P4 与总体状态：** 用户最新提供的本地 MP4 路径对应已处理的 938.968 秒样本；本轮未重复 ASR、未覆盖原稿或侧车。P4 仍待至少三处人工听音比对和新 Desktop 模型数据流验收；P2 仍缺生产逐租约隔离、服务/WFP 与真实捕获；P5 缺新会话 Skill 调用 trace；P6 缺所有者发行决策及远端验证。项目总体仍 **NOT READY FOR RELEASE**。
- **本轮验证边界：** 没有运行项目测试或被审查项目代码，也没有修改服务、防火墙或网络策略。文档更新后只做 whitespace/diff 检查；上述正式扫描快照早于本次 CLI 文档修正，不能宣称扫描覆盖该后续改动。

## 189. 2026-10-12 AUD-125 有界哈希修复与完整 Python 回归

- **修复：** `_sha256_file` 现在通过单个只读文件句柄检查普通文件属性及打开句柄的初始大小；超出调用方格式上限时在读取前拒绝。哈希只读取初始字节数，最多额外探测 1 字节，并在结束时检查文件大小未变化。完成态转写稿与时间轴分别使用由 frontmatter、ASR 字符/段数硬上限及 Markdown 转义扩展推导出的字节上限；本地媒体内容摘要仍按原有策略处理。
- **时间戳预算闭合：** `normalize_segments` 只为 0 到四小时硬媒体时长范围内的起止时间生成时间轴；超界/非有限/不可表示时间只舍弃时间戳，保留正文。`format_timestamp` 对越界输入明确报错。最长格式为 `[240:00]`，每段时间戳、分隔符与换行低于时间轴预算中每段 16 字符的额度，避免输出写出后因哈希上限而无法完成任务。
- **回归证据：** 新增测试验证超限文件在读取前被拒绝、转写稿与时间轴使用不同的上限，以及 `1e308` 时间戳不生成异常时间轴但正文保留。Windows Python 3.11.15 全套结果为 **627 passed、30 skipped**（343.72 秒）；跳过项是未配置 host 路径的 native interop 及 Windows 上不可用的 POSIX/symlink 行为。定向 `test_tasks.py`/`test_normalize.py` 为 **45 passed、1 skipped**；Ruff check 与格式检查通过。
- **安全审查：** 独立只读复核确认新时间戳范围使每段预算闭合，所有转写稿/时间轴摘要绑定与完成态复验均带格式上限。§188 封存扫描早于该修复，本节代码未由那份快照扫描；下一次安全审查应验证补丁并继续扩大 211 文件清单中剩余未审范围。未重跑 .NET harness 或远端平台矩阵。
- **验收状态：** AUD-125 已在当前工作树修复并通过 Windows 回归，但 P2 生产逐租约隔离/WFP/三条真实捕获、P4 人工听审与新 Desktop 数据流、P5 新会话调用 trace、P6 所有者发行决定及远端/跨平台证据仍未完成。项目仍 **NOT READY FOR RELEASE**。

## 190. 2026-10-12 P4 长样本媒体流类型更正

- **直接复核：** 对用户给定 MP4 使用项目锁定环境中的 PyAV 重新读取容器信息，时长为 **938.968435 秒（15 分 38.968 秒）**，媒体大小 22,715,944 bytes。流清单仅包含 AAC 音频轨，没有视频轨。raw Markdown frontmatter 中的时长是 938.922125 秒，相差约 46 毫秒；两者都超过 600 秒。
- **验收含义：** 该文件足以验证 10 分钟以上的本地长时音频转写流程，且已有 raw、默认模型文本校对稿、时间轴和四段私有听审剪辑；不证明视频轨解码或视听同步功能。没有重复运行 ASR，也没有读取或复制逐字稿正文进本报告。
- **P4 对策：** 至少三处听审及差异记录、fresh Desktop 默认模型调用与数据流/隐私验收仍未完成。若验收范围要求验证真实视频轨或视听同步，还需提供带视频流的长样本并单独验证；当前长音频门槛不能代替该项。
- **本轮检查：** `git diff --check`、AUD-125 修改文件的 Ruff check 和 format check 均通过；本轮未运行项目测试。扫描后代码改动已在 §189 记录。P2 生产隔离/真实捕获、P5 新 Desktop 调用 trace、P6 owner 与远端发布门槛仍开放，项目继续 **NOT READY FOR RELEASE**。
- **安全扫描限制：** 尝试启动当前工作树的 Codex Security Deep Scan，但安全扫描工具在创建只读 worker 前拒绝启动，原因是 parent 缺少 managed filesystem permission profile。没有新扫描结果，也不能将本次尝试描述为“无发现”或完成扫描；§188 仍是最近封存的全工作树扫描，coverage partial。未尝试绕过该权限限制。

## 191. 2026-10-12 sdist 元数据审核器解压预算修复

- **修复背景：** §182 指出 `verify_locked_wheel_metadata_audit.py` 使用 `tarfile` 流式读取 gzip sdist，但此前在 tar 条目返回后才检查时限和声明展开大小；极端 PAX 扩展头可能在条目检查前触发额外解压。该审核器由本机操作员手动运行并读取 lock/cache 匹配的依赖包，不是产品网络入口，也未证明跨用户攻击路径，因此此项属于本地资源边界加固，不提升为远程漏洞。
- **实现：** sdist 现在先用 `gzip.GzipFile` 解压，再经 `_BoundedDecompressedReader` 喂给 `tarfile` 的 `r|` 模式。读取器在每段最多 1 MiB 的解压读取前后检查期限，并在解析 tar/PAX 头之前累计解压字节预算；原有成员数量、声明展开大小、PKG-INFO 路径和大小校验仍保留。
- **回归证据：** 新增 3 项用例覆盖有效 PKG-INFO、超限 PAX 扩展头在条目校验前触发预算拒绝，以及过期 deadline 在解压读取前失败。新增用例与相邻 SPDX/archive-cache 组共 **39 passed、2 skipped**；跳过项是仅支持 POSIX 的 FIFO 行为。修改文件 Ruff check/format 通过，敏感文件扫描通过，`git diff --check` 通过；未重跑全量 Python suite。
- **扫描及发布边界：** §188 封存扫描不包含此后修改；本轮启动新的 Deep Scan 时，安全工具因宿主缺少 managed filesystem permission profile 而拒绝创建只读 worker，因此没有产生新扫描结果。继续保留 §188 的 partial coverage 描述，不作“无发现”结论。P2 生产服务/逐租约隔离/WFP/三条捕获、P4 人工听审与 Desktop 数据流、P5 Desktop 调用、P6 owner 决定/远端验收仍未完成，整体 **NOT READY FOR RELEASE**。

## 192. 2026-10-12 P2 生产集成缺口与下一步验收对策

- **默认入口仍安全失败：** 源码复核确认 `WindowsServiceBootstrap` 仍把 `FailClosedCaptureWorker` 注入服务工厂；该 worker 对捕获请求返回 `BROWSER_ISOLATION_UNAVAILABLE`。没有可供产品 CLI 使用的已验证生产 job client、可安装 SCM service/installer、逐租约 worker/OS identity、Chromium 进程树监督或 worker-owned media download。因此 URL 入口保持 fail closed；不得把 standalone pipe/worker adapter 或离线 harness 描述成可用的真实采集功能。
- **WFP 仅构造预览对象：** `WfpFilterMaterializer.MaterializeForInspection()` 会在内存中构造并检查 `FWPM_FILTER0` 相关结构，但源码明确声明不会打开 BFE 或调用 WFP API。它没有生产 provider/sublayer/filter 的创建、枚举、更新、撤销、失败回滚路径，也没有生产 permit provider。`LeaseTcpConnector` 仍未接到 capture handler；单测/fake dialer 不证明真实 lease 出口受限。
- **身份传递与执行隔离仍有缺口：** 已有 named-pipe peer identity context 只证明服务端认证身份可以传给 in-process worker；没有每 lease 独立 OS 身份、真实低权限 worker 生命周期、浏览器/子进程身份核验，或 worker 持有 listener/DNS/upstream sockets 的已验证生产路径。故当前不能证明不同 lease 互相隔离或浏览器无法绕过代理。
- **测试覆盖错位：** 当前 PowerShell Sandbox WFP smoke 使用独立结构构造器；它没有从 C# `LeasePolicyCompiler` / `WfpFilterMaterializer` 输出装载规则，因而不能发现 C# 预览结构与实际 BFE 过滤器间的漂移。§178 的 10/10 是离线策略/native materialization harness，不是活动 filter 验收。
- **对策与阶段门槛：** 下一里程碑应先在新建、可销毁且网络/回滚边界明确的 Windows Sandbox 中构建 runtime consistency harness：直接消费当前 C# 编译/物化结果，在 Sandbox BFE 创建临时 provider/sublayer/filter，并枚举核对实际规则；至少覆盖两个 lease 的互不借用、仅精确 loopback/DNS/pinned-TCP permit、默认拒绝、会话关闭后规则清理，以及中途失败回滚。此 harness 与项目安装器/service 分开，不向宿主安装服务或写宿主 WFP。只有该原型通过后，才能接着实现生产 SCM service、受保护安装/升级/回滚、per-lease worker 和默认 CLI client，再完成锁定 Chromium 的完整进程树验证与三条不同授权视频端到端捕获。任一身份/规则/清理状态未知时继续返回 `BROWSER_ISOLATION_UNAVAILABLE`。
- **验收状态：** 本节为只读源码审查和缺口归纳，没有构建或运行新的 Sandbox/WFP harness，没有安装服务或修改宿主 WFP/Firewall，也没有新的安全扫描结果。P2 保持 **OPEN / NOT PASSED**；P4 目前通过的是 10 分钟以上长音频转写门槛，样本没有视频轨，人工听审和 fresh Desktop 数据流验收未完成；P5/P6 继续开放，整体 **NOT READY FOR RELEASE**。

## 193. 2026-10-12 P6 离线审计工具回归覆盖

- **新增回归：** `tests/unit/test_locked_metadata_audit.py` 现在确认 wheel ZIP 成员数超限会在构造 `ZipFile` 前拒绝、超大 RECORD 会在读取成员前拒绝，并覆盖 metadata audit CLI 对 ESC 与双向控制符的错误输出转义。新增 `tests/unit/test_numpy_native_member_inventory.py` 覆盖 NumPy wheel ZIP 预检先于 `ZipFile`、超大 RECORD 在读取前拒绝，以及对应 CLI 的终端控制字符转义。
- **验证：** 定向 metadata/SPDX/archive-cache/NumPy inventory 测试组为 **41 passed、2 skipped**（91.89 秒）；两个跳过用例需要 POSIX FIFO。两份新增/修改测试文件的 Ruff check、format check 与 `git diff --check` 通过。没有重跑全套 Python 测试、Deep Scan、远端 CI 或干净安装。
- **边界与对策：** 这些用例补足 §174 AUD-118/119 后续指出的本地输入边界回归证据，不代表 wheel 元数据或 NumPy 原生依赖的许可适用性、构建来源、实际链接关系已确认。P6 仍需所有者决定许可证/仓库/发行范围，补齐原生组件来源与 notice 审阅，并完成远端 CI/干净安装；不得据此推断可发布。
- **总体状态：** 本节只增加离线审计器回归用例，没有安装服务或修改宿主 WFP/Firewall。P2 生产集成与真实捕获、P4 人工听审和 Desktop 数据流验收、P5 新会话 Skill trace、P6 owner/远端发布门槛仍开放，项目继续 **NOT READY FOR RELEASE**。

## 194. 2026-10-12 WFP IPv4 主机序表示修复

- **发现：** `WfpFilterMaterializer` 之前把 `IPAddress.GetAddressBytes()` 用 `BinaryPrimitives.ReadUInt32LittleEndian()` 读取。该值再由同样小端的快照逆向转换，因此旧断言只证明了自洽往返；它没有验证真实 `FWP_UINT32`。对 `127.0.0.1`，旧代码会将 native 字段填为 `0x0100007F`，而 WFP IPv4 条件要求主机序整数 `0x7F000001`。这会使精确地址条件指向错误目标，足以阻止后续真实 Sandbox 验收。
- **修复：** 编码和快照解码现都用 big-endian 解释/写入网络地址字节，以得到主机序整数；`NativeConditionSnapshot.RawUInt32Value` 另行保留 native 字段，不能再由纯地址字符串往返掩盖错误。harness 明确断言 `127.0.0.1 → 0x7F000001` 和 `93.184.216.34 → 0x5DB8D822`。Microsoft 文档将 `FWP_V4_ADDR_AND_MASK` 的 IPv4 地址和掩码定义为 host order，且将 `FWP_UINT32` 列为 IPv4 filtering condition 的可用类型。
- **验证：** .NET SDK 10.0.401 x64 Release 构建 **0 warning、0 error**；策略和 materializer harness **10/10 passed**；主项目与 harness `dotnet format whitespace --verify-no-changes --no-restore` 均通过。仅运行离线构造测试；没有打开 BFE、添加 WFP filter、启动或修改宿主/现有 Sandbox。
- **剩余风险与对策：** 下一步在单独新建且可销毁的 Windows Sandbox 中，以 SYSTEM 用 C# materializer 创建/核对临时 BFE filter，验证 loopback 正向/错误地址负向匹配和 dynamic-session 清理；再扩展双租约、DNS/pinned-TCP、default-deny 和失败回滚覆盖。Sandbox 结果不能替代生产 service/逐 lease identity/浏览器进程树与三条真实捕获验收。P2 继续 **OPEN / NOT PASSED**，整体仍 **NOT READY FOR RELEASE**。

## 195. 2026-10-12 C# 到 BFE Sandbox 探针准备与运行阻塞

- **实现：** `tests/SandboxBfeSmoke.cs` 提供测试专用的一租约 BFE 探针，通过 `InternalsVisibleTo` 仅开放给 native test assembly 的同步 materializer callback，在 unmanaged arena 生命周期内把相同 `FWPM_FILTER0` 交给 CsWin32 `FwpmFilterAdd0`。所需 engine/transaction/provider/sublayer/filter/AppID/free-memory API 均来自锁定 CsWin32 生成绑定。探针源码预设建立独立 persistent 与 dynamic session，并按预期 filter GUID 调用 `FwpmFilterGetByKey0` 读回对象；源码还包含 listener、外网 TCP 和 session 清理断言，但 §195 的 Sandbox 启动阻塞，任何 BFE/filter/流量断言都没有实际执行。§197 进一步发现当前 SID 和流量发起身份使这些断言按现状无法证明租户隔离。新增 `RunMaterializerBfeSandboxSmoke.ps1` 使用新 GUID 创建 Sandbox，映射只读探针/命令与单独可写结果目录，并在 `finally` 中仅停止它自己创建的 Sandbox。Guest probe 在处理任何 filter 前要求匹配 run token、显式 guest 标记和 SYSTEM SID；普通 host invocation 已测试并在策略修改前拒绝。
- **离线验证：** .NET 10.0.401 x64 Release build **0 warning、0 error**；普通策略/materializer harness **10/10 passed**；Self-contained win-x64 publish 成功，发布目录中的无参数自测也 **10/10 passed**；主项目和测试 harness `dotnet format whitespace --verify-no-changes --no-restore` 通过。Self-contained publish 首次因缺少本地 `Microsoft.NETCore.App.Runtime.win-x64` 包失败，随后按授权执行 SDK restore/publish 成功；没有改项目 packages.lock，也没有部署到宿主。
- **真实 BFE 运行状态：** 探针本轮没有运行。尝试启动新 Sandbox 时 Windows launcher 返回 `CO_E_APPSINGLEUSE (0x800401F6)`，`wsb list` 显示另有一个已运行实例。为避免影响该会话，没有停止、连接或复用既有 Sandbox；启动失败没有创建测试 guest，且没有任何 filter 被添加。宿主 WFP/Firewall 状态未触碰。
- **限制与对策：** 这是单租约、SYSTEM 当前进程的 BFE 集成检查；复制出的 worker helper 只用于取得不同 AppID，并未作为真实 worker 启动。因此即使未来 Sandbox 全项通过，也不证明两用户隔离、worker/browser 身份传递、服务部署、Chromium 进程树或 WebRTC/UDP 防绕过。等当前 Sandbox 结束后，用 wrapper 在新 guest 实跑并保存 JSON 结果；随后再扩展两个实际 lease principal 与 worker/browser helper。P2 仍 **OPEN / NOT PASSED**，项目保持 **NOT READY FOR RELEASE**。

## 196. 2026-10-12 P4 长样本默认模型校对侧车补齐

- **输入与既有任务：** 用户给出的长样本对应已完成的本地 ASR 任务；本轮没有重复运行 ASR，复用已有 raw 稿与时间轴。锁定 PyAV 读到 **938.968435 秒（15 分 38.968 秒）**，仅双声道 AAC 音频轨，没有视频轨；raw frontmatter 记载的时长相差约 46 毫秒，二者都超过 600 秒。
- **模型校对：** 在用户此前授权下，当前 Agent 默认模型只读取 raw 正文，整理中文句读和段落，并按上下文纠正高置信 ASR 同音词/术语；不确定的年份、术语和专名没有音频依据，仍需复听。`review-sidecar` 新建非空校对侧车，含“模型文本校对、未逐字听审”的范围说明。原始稿未被覆盖，正文和本机文件名未复制进本报告。CLI doctor 显示本地 ASR 与输出目录 DACL 均为 `ok`。
- **P4 验收与对策：** 十分钟以上长音频转写和默认模型文本校对已满足；四段私有 18 秒剪辑保存在本机受限输出目录的 `p4_review_clips` 子目录，至少三处人工听音差异记录、新 Desktop 会话的数据流/隐私验收仍未完成。该文件没有视频轨，所以不证明视频解码或 A/V 同步；如验收要求真实视频轨，另需一份带画面的长样本。整体项目保持 **NOT READY FOR RELEASE**，P2/P5/P6 门槛也仍开放。

## 197. 2026-10-12 P2 BFE 探针身份缺陷与 P5 干净副本安装复核

- **AUD-126（P2 探针无法到达 BFE，阻断 Sandbox 验收）：** 静态复核 §195 的 `SandboxBfeSmoke.RunCore` 发现它将 `S-1-5-18`（SYSTEM）传给 `LeasePolicyInput` 的 `UserSid` 主体。`LeasePolicyCompiler.NormalizeLeaseSid` 明确拒绝内置 SID，只接受格式有效的普通本地用户 SID 或 AppContainer SID，因此 `Compile()` 会在 `OpenEngine()` 之前抛出参数异常。§195 的 Sandbox 运行曾在启动阶段受 `CO_E_APPSINGLEUSE` 阻断；即使 launcher 可用，这个探针也无法按当前源码跑到 BFE。
- **新增发现（流量断言不代表租户隔离）：** 探针以 SYSTEM 进程本身发起 loopback/外网 TCP 检查；复制出的 worker helper 只用于生成另一个 AppID，并未启动。故改成任意普通 SID 只能绕过编译器形状拒绝，不能让检查流量满足该 lease 的 SID/AppID 条件。现有读回逻辑按预期 GUID 调用 `FwpmFilterGetByKey0` 检查对象，不是枚举 BFE 中全部 filters；§195 中“枚举所有 filter”的描述应理解为过宽，不能据此断言没有额外 filter。
- **对策：** 在新建且可销毁的 Sandbox guest 中创建两个普通测试账户并取得真实 SID；分别用对应令牌启动具有独立路径/AppID 的 browser 和 worker helper。将两个 lease 编入同一策略，验证各自 listener 与 resolver/pinned-IP 正向访问、跨 lease 和错误目标负向访问、按 key 读回预期 filter、dynamic session 清理与 persistent deny 生命周期，并在异常路径回滚全部测试对象。未完成前，§195 只算离线原型准备，不算真实 BFE 或双租户隔离验收。当前没有停止/连接既有 Sandbox，也没有改动宿主 WFP/Firewall。
- **P5 干净安装复核：** 使用锁定的 `uv 0.12.7` 运行 `scripts/check_clean_skill_install.py`，仓库外临时副本安装、包导入路径、CLI 版本、URL dry-run JSON、`doctor --json` 的 setup-required 结果及不创建 app-data/output 的断言均通过。临时目录由脚本上下文清理。该本地安装冒烟不证明远端 CI、发布安装或新 Desktop 会话的 Skill 发现/调用。
- **AUD-127（CWE-200，低危；本地报告内路径已修正）：** §196 的 P4 片段说明误写入本机用户目录，现已改为不含账户名的受限目录描述。该类路径会泄露本地账户/存储布局；项目文档应继续避免提交本机账户路径和私有媒体标识。
- **当前状态：** 同一长样本已在 §196 完成 ASR 和默认模型文本校对侧车，本轮没有重复 ASR；`doctor --json` 仍报告本地转写 ready、URL 捕获因缺管理员 WFP broker 而 unavailable。Windows Python 3.11.15 全套回归 **636 passed、30 skipped（255.59 秒）**；2 项 native interop 因未配置宿主路径跳过，其余跳过项依赖当前 Windows 不具备的 POSIX/FIFO/符号链接或平台专属能力。P2 探针缺陷与真实生产隔离、P4 人工听审与 Desktop、P5 Desktop trace、P6 所有者/远端/原生依赖证据仍未通过，项目 **NOT READY FOR RELEASE**。
## 198. 2026-10-12 P4 长样本路径复核与报告隐私脱敏

- **P4 输入复核：** 用户本次提供的长样本路径指向 §196 已审计的同一媒体文件（22,715,944 bytes）；既有锁定 PyAV 结果为 938.968435 秒（15 分 38.968 秒），容器只有双声道 AAC 音轨。该文件已有本地 ASR、默认模型 reviewed sidecar 和 timeline，本轮没有重新转写，也没有改动这些私人输出。P4 的至少 10 分钟长音频转写门槛满足；该样本不验证视频流解码或 A/V 同步。至少三处人工听审差异记录及 fresh Desktop 数据流/隐私验收仍未完成。
- **AUD-128（CWE-200，低危；文档脱敏）：** 历史审核正文曾保留本机 Windows 设备名和当前账户名，未给出必要的技术证据增益。已在 `PROJECT_AUDIT_REPORT.md`、`P2_REPORT.md` 与 `P2_ISOLATION_DECISION.md` 中改为通用本机/账户角色描述，保留令牌权限与环境能力的结论。该项只修改文档，没有触碰 Windows Sandbox、账户、服务或网络策略。
- **状态与验证：** `git diff --check` 通过。最近全套 Python 回归仍是 §197 的 **636 passed、30 skipped（255.59 秒）**；本节只做了媒体既有记录对照和文档编辑，没有重跑转写、测试或安全扫描。P2、P4 人工听审/Desktop、P5 Desktop trace、P6 所有者/原生依赖/远端验收仍开放，整体 **NOT READY FOR RELEASE**。
## 199. 2026-10-12 WFP .NET 构建期 NuGet 依赖审查

- **范围与分类：** wfp-policy-plan/packages.lock.json 有四个包节点：CsWin32 0.3.360 直接依赖，Win32Docs 0.1.42-alpha、SDK.Win32Metadata 71.0.30-preview 和 WDK.Win32Metadata 0.13.25-experimental 为传递依赖。wfp-policy-plan.csproj 对 CsWin32 设置 PrivateAssets=all；这些是检查工具构建/源生成输入，不在当前 Python 应用运行依赖或 SBOM 范围内。capture-pipe 没有 PackageReference 或 NuGet lockfile。逐包许可元数据、来源、SHA-256 与未闭合项见 docs/DOTNET_BUILD_DEPENDENCY_REVIEW.md。
- **本地证据（截至 §199）：** 只读取锁文件和 NuGet cache；四个 lock contentHash 分别与 .nupkg.metadata 一致，对 nupkg 原始 bytes 计算的 SHA-512 与旁置 .nupkg.sha512 sidecar 一致，4 个签名文件存在。当时没有验证签名、restore 或执行包代码；后续签名验证结果见 §209。本机 SHA-256 见审查表。
- **AUD-129（P6 build dependency license gap）：** Win32Docs nuspec 未给 <license>/包内许可证，只标记需要接受许可并链接 aka.ms/WinSDKLicenseURL；本轮审查环境无法读取该链接，故保留为未闭合项。SDK/WDK metadata 包各自随附 Windows SDK license terms 文件；CsWin32 包内有 51,294-byte NOTICE，列出 17 条 bundled component notices。不要据此作适用性或再分发法律结论。
- **当时对策：** 保持构建工具链与应用 SBOM 分开；确认 Win32Docs 条款、SDK/WDK 条款对生成输出的适用性，并在任何原生服务/工具发行前审查包内 NOTICE、生成代码和 source provenance。§209 后续完成了四个本机锁定包的签名核验；独立下载重现、远端 CI 与 owner release decision 仍未完成。没有修改系统策略或依赖 lock。整体 NOT READY FOR RELEASE。

## 200. 2026-10-12 双租约 BFE 探针源码续审与离线验证

- **AUD-126 对策进展（测试探针，不是产品修复）：** `SandboxBfeSmoke` 现在从 guest runner 接收两个随机普通本地账户及真实 SID；C# SYSTEM 控制器分别启动 browser/worker 四个不同路径的 helper。每个 helper 在 `GO` 前报告身份，父进程再以 TokenUser 与 `QueryFullProcessImageName` 独立核对 SID、PID 和映像路径。两个 lease 一起编译，正向基线包含各自 listener、resolver UDP/TCP 与 pinned endpoint，负向基线覆盖跨 lease、错误 listener 和未授权目标；正向基线缺失时不写 BFE。源码还实现按 key 读回 filters、动态 session 关闭后的 persistent deny 检查，以及清理后连接恢复核验。
- **隔离声明修正：** README 原先把每个账户目录权限描述为“仅能访问自己的两个目录”，但实现只添加显式 RX grant，没有证明继承 ACE 已被移除。现已更正为“应用显式授权”，并明确探针依靠 SID 与 AppID 联合匹配；不把目录 ACL 当作独立隔离证据。DNS-over-TCP 探针只连接 resolver 的 53 端口，不发送 DNS 查询。
- **本轮离线验证：** 锁定 .NET SDK 10.0.401 下 WFP test harness `dotnet build --no-restore` 成功，0 warnings / 0 errors；普通无参数策略/materializer harness **10/10** 通过。两个 Sandbox PowerShell runner 经 PowerShell Parser 静态解析通过。上述操作没有运行 Sandbox wrapper、打开 BFE、写入 WFP/Firewall 或执行真实网络矩阵。
- **剩余缺口与状态：** 新探针的 BFE add/readback、跨 lease 阻断、dynamic/persistent 生命周期和清理路径仍未动态执行；listener/DNS/pinned probes 只覆盖 IPv4，DNS/TCP 仅连接性检查。它也不实现生产 service、认证 IPC、每租约 worker 生命周期、Chromium 进程树、IPv6/QUIC/WebRTC 防绕过、installer/rollback 或三条真实授权捕获。探针 runtime 通过前，不关闭 AUD-126 或 P2；P4 人工听审与 fresh Desktop 验收、P5 新 Desktop Skill trace、P6 许可/来源/远端 CI/owner 决策也仍开放。整体 **NOT READY FOR RELEASE**。

## 201. 2026-10-12 当前工作树安全审阅补充与发布门槛

- **审阅范围：** 针对当前工作树的安全差异扫描 `fc1d8e78-569a-42ac-b59e-943f351c3f86` 以 HEAD `b166778ee5283591a1b799535b746ba198e38653` 为基线，冻结摘要为 `codex-security-snapshot/v1:sha256:999bd7c21b8225842163be32577d49fe2a18f12d4830f60f0e4ff3bceeb377eb`。扫描清单包含 220 个变更文件、93 条源码/配置审阅项；工具记录 12/93 项已关闭，扫描仍为草稿、尚未封存，故本节是针对已核对区域的补充审阅，不能证明其余差异不存在问题，也不能替代后续完整安全审查。`ARCHITECTURE.md` 的流程图原先将浏览器采集/下载画成现有 URL 路径，现已更正为当前 fail-closed、隔离 worker 尚未集成。
- **AUD-130（低风险、需管理员手动误操作；已做代码级缓解）：** 冻结扫描快照中的 `NetworkWfpWriteSmoke.ps1` 只记录 `runContext`，不阻止 Sandbox 外执行；有足够权限的操作者可添加位于 `ALE_AUTH_CONNECT_V4`、没有条件、动作是 `FWP_ACTION_BLOCK` 的动态 filter，暂时阻断本机所有 IPv4 connect。未发现自动生产调用或远程触发路径，因此这是低风险操作隐患，而非远程利用。扫描后已将入口替换为立即抛错的 fail-closed stub；旧 `.wsb` profile 仍可启动脚本，但不会执行 BFE 或网络操作。历史 guest 结果见 §110。
- **AUD-130 后续验证：** 已逐字检查 stub，不再含 BFE P/Invoke、`Add-Type` 或 filter 写入代码；README 已标记旧入口 retired。尚未在任何 Sandbox/宿主运行脚本验证异常路径。本轮没有打开 BFE、运行 Sandbox wrapper 或修改 WFP/Firewall；后续 C# materializer BFE 验收仍须走新建可销毁 Sandbox wrapper，且不能恢复全局无条件 block。
- **AUD-131（低风险，报告隐私；已修正）：** §196 曾保留私有媒体文件名、本地任务标识及转写侧车文件名。现已移除这些标识，仅保留审计需要的时长、音轨类型和验收结论；报告未包含逐字稿正文。该文档修订晚于冻结安全扫描，不改变其扫描快照。
- **潜在生命周期问题（deferred，当前不可达）：** `BrowserCapture.close()` 在关闭上下文前清空租约并重置丢失状态；若未来把该旧类接入 broker，关闭期间的 route callback 可能把“无租约”判为可用。现有 `open_system_broker()` 不可用、CLI 未注入 capture client、pipeline 在 URL 处理前失败关闭，故当前没有产品攻击路径。接入前应先进入 closing/deny 状态，拒绝 route callback，并由 broker 确认 Chromium 进程树退出后再释放 lease。旧 `resolve_input()` 仍具备调用进程网络解析能力，但目前没有生产调用者；继续使用 direct-only/fail-closed URL 路径，并避免把旧 helper 暴露为未来默认入口。
- **P2 与操作边界：** §200 的双租约 BFE probe 只有离线构建/harness 证据，本次没有进入或停止任何现有 Sandbox，也没有运行 Sandbox wrapper、BFE/WFP 探针或宿主网络策略操作。没有生产 service、per-lease worker/identity、WFP apply/rollback、Chromium 进程树隔离或三条真实捕获证据，P2 仍 **OPEN / NOT PASSED**。
- **P4/P5/P6：** 用户新给的长样本路径对应 §196/§198 已处理的同一私有媒体；时长为 938.968435 秒且只有 AAC 音轨，本轮未重跑 ASR、未打开逐字稿正文。长音频和默认模型文本校对门槛已满足；四段剪辑仍需至少三处人工听审差异记录和 fresh Desktop 数据流/隐私验收，样本不验证视频轨或 A/V 同步。P5 仍缺 fresh Desktop `/skills` 发现、显式调用与脱敏 trace。P6 仍缺所有者批准的根许可证、发行范围、仓库/远端决定，native provenance/linkage/notice 结论以及远端矩阵和干净安装；§199 的 NuGet 盘点不构成许可结论。
- **结论与后续：** §201 冻结快照中的 AUD-130 手动诊断风险已在 §202 通过停用旧入口做代码级缓解；其余捕获生命周期和 URL helper 属于尚不可达的后续接入风险。当前差异审阅和运行时证据仍未补全，安全扫描未封存且覆盖部分；P2/P4/P5/P6 均未通过，项目保持 **NOT READY FOR RELEASE**。

## 202. 2026-10-12 AUD-130 旧全应用 WFP 探针停用

- **修复：** 将 `native/windows/wfp-policy-plan/sandbox/NetworkWfpWriteSmoke.ps1` 的可写 BFE 实现替换为 fail-closed stub。无论旧 `NetworkWfpSmoke.wsb` 是否仍调用它，入口都会立即抛错；当前文件不再导入 `fwpuclnt.dll`、`Add-Type` 或包含 WFP add/filter 实现。Sandbox README 和 policy-plan README 已将旧 probe 标记为 retired，并指向之后的 C# materializer Sandbox probe。
- **静态验证：** 当前 Windows PowerShell 的 `System.Management.Automation.Language.Parser` 对 stub AST 解析通过；源码搜索确认该文件不再包含 `Fwpm*`、`Add-Type`、`FWP_ACTION_BLOCK` 或无条件 filter 字段。`git diff --check` 对本次修改文件通过。没有执行脚本、启动 Sandbox wrapper、打开 BFE 或更改宿主 WFP/Firewall。
- **边界：** 这是源代码级停用，不是动态 Sandbox 验收，也没有实现生产 service/worker/WFP provider。冻结安全扫描仍描述修改前快照（220 个差异文件、93 条源码/配置 worklist，12 条记录关闭），当前扫描不因此变成完整或封存。P2 仍 **OPEN / NOT PASSED**；P4 人工听审与 fresh Desktop、P5 Desktop trace、P6 owner/remote release gates 继续开放。项目整体 **NOT READY FOR RELEASE**。

## 203. 2026-10-12 BFE Sandbox wrapper 可写结果目录边界

- **发现与风险：** `RunMaterializerBfeSandboxSmoke.ps1` 原先接受调用者指定的 `ResultsDirectory`，并将其整个目录映射为 Sandbox guest 可写共享目录。默认目录是脚本旁的专用 `sandbox-results`，但自定义路径可能让测试 guest 接触操作者不打算暴露的其他文件。该脚本和 guest probe 都是测试工具；未发现自动调用或远程入口。本项按本地测试操作边界加固处理，不作为远程漏洞报告。
- **修复：** 移除可调用参数 `ResultsDirectory`。结果固定写入脚本旁的 `sandbox-results` 目录；目录为重解析点/符号链接时立即失败，避免可写 share 被重定向到其他位置。
- **验证与限制：** 本轮进行 PowerShell AST 静态解析和 `git diff --check`；没有执行 wrapper、启动/停止 Sandbox、打开 BFE、写入 WFP/Firewall，或运行项目测试。该静态检查不证明主机文件系统/guest 动态隔离性质。
- **整体状态：** 此改动不实现生产 service、WFP provider 或 worker。P2 继续 **OPEN / NOT PASSED**；§201 安全扫描仍是修改前冻结且未封存的部分扫描，不能覆盖本节。P4 人工听审/fresh Desktop、P5 Desktop trace、P6 owner/远端发布门槛继续开放，项目 **NOT READY FOR RELEASE**。

## 204. 2026-10-12 当前 Windows Python 全套回归

- **命令与结果：** `uv run --project .\skills\douyin-transcript --locked --no-sync --group dev pytest -q` 使用锁定 Skill 环境完成 **636 passed、30 skipped（255.06 秒）**。
- **跳过范围：** 两项 Windows native interop 因未配置宿主路径跳过；其余跳过项依赖当前 Windows 不支持的 POSIX FIFO、POSIX mode/dir-fd 行为或 symlink 创建能力。它们仍需适合的平台/环境矩阵验证。
- **其他本地发布检查：** 锁文件验证、CI 范围 Ruff check 和 format（82 个文件）、仓库外 clean-copy Skill 安装、canonical/`.codex` `agentskills validate`、Git 可见敏感文件扫描及 pinned SPDX 2.3 schema check 均通过。
- **边界：** 这次 Python 回归晚于 §§202–203，但不执行 PowerShell Sandbox wrapper、C# BFE probe、宿主 WFP/Firewall 或真实 Douyin 捕获，不证明 P2 运行时隔离。§201 安全扫描仍未封存，记录 12/93 条源码/配置审阅项；P2/P4/P5/P6 仍未通过，项目 **NOT READY FOR RELEASE**。

## 205. 2026-10-12 当前工作树分区静态安全复核

- **Python 产品源码：** 复核 `skills/douyin-transcript/src/douyin_transcript/` 现有与新增源码，以及直接相关的 URL、ASR、存储、输出调用点。未发现新的可达安全候选。当前 CLI/pipeline 缺少捕获服务 client 时在解析/下载前 fail closed；direct URL 路径拒绝短链；system broker factory 恒不可用，Windows pipe adapter 未作为默认产品路径。旧 `resolve_input()` 仍有网络解析能力，但当前源码没有调用点；服务集成前应继续避免将其接回默认入口。IPC 帧限制、请求绑定、工件长度/摘要检查和私有 no-overwrite 写入均有源码控制。
- **Native capture/WFP：** 复核 capture-pipe 对端身份、字段和帧限制、服务 worker 当前 fail-closed 路径、数值 DNS/TCP 约束，以及 WFP compiler/materializer 关键路径。未发现新的可报告产品缺陷；计划编译器/materializer 仍为不可部署预览，不调用 BFE/WFP。未审全文的 `LocalHarness`、`ServiceLifecycleHarness`、若干测试与 Sandbox harness 继续属于明确覆盖缺口。
- **AUD-132（低置信度操作风险候选，不确认为产品漏洞）：** `native/windows/wfp-policy-plan/sandbox/ScopedNetworkWfpSmoke.ps1` 的执行门控只检查当前身份为 SYSTEM；随后会以当前 PowerShell 映像派生 AppID，并在动态 WFP session 中添加限制性 filters。特权操作者若在宿主机误运行，可能暂时影响该映像的网络。该脚本是手动 Sandbox smoke，README 明确要求 guest SYSTEM；dynamic session 和 finally 关闭引擎提供回收，没有发现自动/普通用户触发路径。**对策：** 在继续复用前增加明确的专用 Sandbox 启动门控和新鲜运行令牌，或退休该旧 probe；环境变量/身份字段只能作为误操作防护，不能被记作 Sandbox 隔离证明。不得在宿主运行验证。
- **CI 与发布工具：** 复核当前 CI 权限和 pinning、敏感文件扫描器、SBOM/SPDX 与锁定归档审核工具及其 schema。未发现新候选；审查范围内工具离线处理数据，不执行归档成员，并对成员/字节/时间施加上限。此次为静态读码，没有新增动态文件系统测试。
- **快照及验收限制：** 以上是当前工作树分区人工复核；native 目录在工作树相对基线为 untracked，无法从冻结差异重建原始快照，因此不能把当前代码结论套用于旧快照。Codex Security scan `fc1d8e78-569a-42ac-b59e-943f351c3f86` 仍是 220 个文件、93 个源码/配置审阅项中 12 项关闭的未封存草稿；分区复核不改变其 coverage。未访问 URL、未读取逐字稿、未处理媒体、未运行测试或 Sandbox/BFE/WFP，也未改宿主网络策略。P2、P4、P5、P6 的外部验收仍开放，项目保持 **NOT READY FOR RELEASE**。

## 206. 2026-10-12 BFE Sandbox guest 可写共享逐次隔离

- **发现：** §203 已固定 host 结果根目录并拒绝根 reparse point，但 guest SYSTEM 仍可写入整个 sandbox-results。该目录可能同时保存其他诊断产物，造成本次 Sandbox 访问无关文件的风险。
- **修复：** wrapper 为每次运行创建 GUID 命名子目录，只把该子目录映射为可写共享；根与子目录均拒绝 reparse point。guest 要求共享目录在创建账户和启动 BFE controller 前为空，并验证输出路径中的 GUID 与本次 token 完全一致。host 只在确认本次 Sandbox 已停止后读取结果，并拒绝额外目录项、reparse point、超过 1 MiB 或无效 JSON；guest 控制台输出不回显到 host。
- **独立复核：** 两次只读候选复核确认固定 wrapper 的 guest 写入边界只包含本次子目录，guest 路径与 C# probe 兼容，空目录检查早于账户/BFE 操作；未发现可通过该共享访问兄弟目录的直接绕过。
- **验证：** 两个 PowerShell 文件 AST 解析通过；tests/unit/test_sandbox_cleanup_ownership.py **7 passed**；默认 git diff --check 退出码为 0。真实运行 wrapper 时 wsb start 返回 CO_APPSINGLEUSE；当前已有 Sandbox 仍是唯一列出的实例。wrapper 未连接、停止或复用该实例，未映射共享、执行 guest probe 或修改宿主 BFE/WFP/Firewall。
- **剩余限制：** host 目录/文件检查与后续路径读取之间仍是 path-based 操作；同一主机进程若并发替换本次结果目录，存在条件性竞态。若启动失败且 wsb list 也失败或遗漏新 ID，可能留下未确认的 Sandbox；本次失败时列表未出现新 ID。host 校验 JSON 语法和文件形状，不校验应用级 schema 或 JSON 内的 RunToken。以上更改晚于 §201 的未封存 partial scan；P2 动态矩阵与生产 service/worker 隔离、P4 人工听审/Desktop、P5 Desktop trace、P6 owner/发行及远端验收仍开放，整体 **NOT READY FOR RELEASE**。

## 207. 2026-10-12 当前完整回归与 P4 长样本试听准备

- **全套回归：** 锁定 Windows Python 3.11.15 环境执行 `uv run --project .\skills\douyin-transcript --locked --no-sync --group dev pytest -q`，结果 **638 passed、30 skipped（256.93 秒）**。两项 native interop 因未配置宿主路径跳过；其余跳过项依赖当前 Windows 不支持的 POSIX/FIFO/symlink 能力。该回归不验证 Sandbox/BFE/WFP 或真实捕获。
- **P4 样本：** 核对用户提供的本地媒体为 **938.968435 秒**，含双声道 AAC 音轨且没有视频轨。既有 ASR、默认模型 reviewed sidecar 和时间轴均已存在，本轮未重跑 ASR、未覆盖文件、未读取逐字稿正文。长音频和模型文本校对门槛满足；这不验证视频解码或 A/V 同步。
- **人工听审准备：** 已定位四段各 18 秒私有试听片段，对应约 01:11、05:40、08:41、08:59。至少三段与原音的人工对照及差异记录仍未完成；fresh Desktop stdout/stderr/Agent 摘要隐私验收也仍开放。
- **发布门槛：** P2 仍缺生产 per-lease worker/identity、WFP permit/apply、浏览器进程树隔离和三条授权真实捕获；P5 仍缺 fresh Desktop Skill 发现/调用 trace；P6 仍缺所有者许可证、发行范围、仓库/发布授权决定，以及未完成的 native provenance/linkage/notice 和远端 CI/干净安装。§201 安全扫描仍未封存且 coverage partial。项目整体 **NOT READY FOR RELEASE**。

## 208. 2026-10-12 native HTTPS CONNECT 离线源码切片

- **实现：** 新增未注册的 `HttpsConnectTunnel`，只消费一个已接受 TCP 流，不创建 listener、不参与 `ICaptureWorker`。请求解析限制为 16 KiB、请求行 2 KiB、32 个头字段和最多 1 KiB 预读数据；拒绝非 HTTP/1.1 CONNECT、非 443、IP 字面量、非法/冲突 Host、重复或非零 Content-Length、Transfer-Encoding、Proxy-Authorization、Expect、裸 LF、折叠头和非 ASCII 字节。仅允许现有 Douyin 与已登记 CDN 精确/边界后缀名单。
- **网络和生命周期：** host 通过 allowlist 后，handler 调用数值 resolver 与 `LeaseEgressPolicy`，从经过完整 A/AAAA/CNAME 校验的公网地址集合中选数值 IP，调用 `LeaseTcpConnector` 取得 endpoint permit 后拨号；远端 endpoint 校验通过后才发 200。之后只转发原始字节，不解密 TLS。单隧道有 512 MiB、30 分钟总时长和 2 分钟空闲限制；双向转发使用 32 KiB 缓冲和背压，保留 CONNECT 头后读到的早期字节，并传播 TCP 半关闭。协议失败只发固定 400/403/502/504，不回显输入或内部错误。
- **资源修复与验证：** `ILeaseTcpConnectionHandle` 增加发送半关闭能力，使上游 socket 能在单向 EOF 后保持另一方向工作。Pinned .NET 10.0.401 x64 Release build **0 warnings/0 errors**；capture-pipe `--self-test` 全部通过。新增 fake-stream/DNS/dialer 场景验证成功 relay、permit-before-dial、错误 framing/Host/IP/port 在 DNS 前拒绝、站点拒绝不发 DNS、私网 DNS 答案不取 permit、远端 endpoint 不匹配时清理 socket 和 permit。
- **安全边界与状态：** 这不是生产代理或隔离服务：没有 listener 创建/绑定、accepted-peer 认证、DNS egress permit、per-lease 并发上限、worker/factory 接线、lease token/AppID+SID/WFP 实现或 rollback。它只检查 CONNECT authority，不解析 TLS SNI 或加密 HTTP Host；未来已认证的浏览器 worker 仍须在 URL route 层拒绝非允许的 navigation/resource，不能把这个 handler 当作可独立服务任意本机客户端的通用代理。`CaptureServiceFactory` 仍使用 `FailClosedCaptureWorker`；本节 CONNECT 场景使用 fake DNS/dialer，没有访问 Sandbox、BFE、WFP、宿主 Firewall 或外部 DNS。新切片发生在 §201 Codex Security 冻结扫描之后，该 scan 仍是 12/93 审阅行的未封存 partial draft，不能覆盖本节。P2 仍 **NOT PASSED**；P4 人工复听/Desktop 隐私、P5 Desktop trace、P6 owner/远端发布门槛仍开放，项目 **NOT READY FOR RELEASE**。

## 209. 2026-10-12 WFP 构建依赖 NuGet 签名本机核验

- **核验范围：** 本机 NuGet 缓存中的 `Microsoft.Windows.CsWin32 0.3.360`、`Microsoft.Windows.SDK.Win32Docs 0.1.42-alpha`、`Microsoft.Windows.SDK.Win32Metadata 71.0.30-preview` 和 `Microsoft.Windows.WDK.Win32Metadata 0.13.25-experimental`，均为 `native/windows/wfp-policy-plan/packages.lock.json` 锁定版本的 build/source-generator 依赖，不属于 Python 产品运行时 SBOM。`capture-pipe` 没有 PackageReference。
- **结果：** `dotnet nuget verify --all` 对四个本机 `.nupkg` 全部返回退出码 0，识别出 Microsoft author 与 NuGet.org repository 签名。验证器输出的包 `contentHash` 与 lockfile 对应项一致。Win32Docs author 与 repository 证书显示的有效期止于 2023/2024；验证器仍接受签名，不能据此推断包未签名或许可失效。NuGet 签名验证只支持包身份/完整性判断，不解决许可条款的法律适用范围。
- **剩余事项：** Win32Docs 的 licenseUrl 条款、SDK/WDK 条款是否适用于未来生成源码/原生服务仍须 owner/legal review；独立下载重现、远端 CI、发行范围和仓库发布授权仍未完成。继续保持 tool packages 与应用 runtime SBOM 分开，P6 与总体发布状态仍 **NOT READY**。

## 210. 2026-10-12 最新审查：dry-run readiness、BFE 探针边界与 CONNECT DNS 许可

- **P4 用户新给样本路径：** 本次提供的媒体与 §§196、198、207 记录的是同一个 938.968435 秒样本，文件已有 raw ASR、模型 reviewed sidecar、timeline 和四段试听片段。本轮未重跑 ASR、未打开或复制私人转写正文。它达到十分钟长音频门槛；媒体只有双声道 AAC 音轨，没有视频轨，不能证明视频解码/A/V 同步。至少三处人工听审差异记录及 fresh Desktop stdout/stderr/Agent 摘要隐私验收仍开放。
- **AUD-133（P2/P3，已修复：dry-run 将 URL 误报为 ready）：** `transcribe <URL> --dry-run --json` 以前只做本地 URL 语法解析，却把可用直链标为 `ready` 并返回 0；真实调用在没有 capture client 时会返回 `BROWSER_ISOLATION_UNAVAILABLE`。现 dry-run 将语法有效但无法捕获的条目标为 `capture_unavailable`，顶层返回 `needs_attention` / exit 2，并区分 `input_status` 与实际捕获能力；本地文件仍可单独报告 ready，短链仍本地拒绝。更新 CLI reference 并新增针对性回归；定向 pytest **5 passed、81 deselected**，没有跑全套。
- **AUD-134（P1 操作边界，待修复：BFE Sandbox probe 缺少 Sandbox 身份证明）：** `SandboxBfeSmoke.Run` 的门控只核对可设置环境变量、GUID 参数、SYSTEM SID 和结果路径，不证明执行环境是 Windows Sandbox。通过后，测试程序以无会话方式打开 BFE 并创建 persistent provider/sublayer/filter；在 SYSTEM host 上直接运行仍可触及宿主 BFE，异常终止也可能跳过清理。触发需要特权的人工/测试工具调用；未发现产品自动入口或普通用户远程路径，因此不把它描述为生产 URL 绕过。**对策：** 在可信 guest 身份边界能成立前，停用可直接调用的 BFE 写入口；不可把 env 标记或 SYSTEM 身份当作 Sandbox attestation。优先只在新建、可销毁 Sandbox 中运行；若无法给出可靠 guest 证明，则不要执行 persistent mutation。
- **AUD-135（P2 集成缺口：CONNECT DNS 查询没有逐 lease permit）：** 未注册的 `HttpsConnectTunnel` 直接调用 `NumericDnsQuestioner` 进行 DNS 网络 I/O，但只为后续上游 TCP 取得 `ILeaseUpstreamPermitProvider` permit。计划中的 worker 默认拒绝出口时，未获准的 resolver UDP/TCP 53 查询不能工作；为了让它工作而开放通用 DNS 会破坏逐 lease 出口边界。**对策：** DNS 查询前按 resolver IP、UDP/TCP 协议及 53 端口申请 lease permit，socket 关闭后撤销；双 lease 动态矩阵验证 resolver 互隔和异常回收。另一个可用性缺口是 handler 只尝试排序后首个已验证地址；应在总 deadline/尝试数上限内尝试同一 pin 集合的其余地址，并逐次取得/回收准确 permit。
- **CONNECT 主机策略前置条件：** handler 只知道 CONNECT authority，之后转发 opaque TLS，不能证明加密连接内的 SNI/HTTP Host 一致。它仍不可注册或作为通用本地代理；未来需受保护 listener、已认证 lease peer 和浏览器 navigation/resource URL allowlist。该点在 §208 已说明，本节确认必须作为接线门槛持续保留。
- **P6 发布证据范围：** §209 已完成四个 NuGet build-only 包的本机签名核验，修正了旧审查文档中过期的“签名未验证”状态。项目根 `LICENSE` 和 Git remote 仍不存在；许可证、发行范围、仓库目标/可见性及发布授权属于 owner 决定。当前 CI 的 SPDX 专项检查验证 pinned schema，pytest 核对 SBOM 身份/声明一致性，但不重建并逐字节复核全部锁定归档；发行前应使用精确 SHA-256 cache 复现离线 SBOM verifier/generator，再执行获批的远端 CI 与 clean install。
- **低优先级待确认：** `setup --browser` 仍可能在 URL broker 不可用时安装 Chromium，但不会使 pipeline 绕过 fail-closed；可在 CLI 显示“安装不启用 URL capture”，或能力 unavailable 时拒绝该用途。`review-sidecar` 在交互终端缺少 JSON stdin 时可能等到 EOF；源码审查未运行确认，建议后续增加 TTY 快速失败及回归。两项均不是已证实的隔离绕过。
- **本轮验证边界：** 仅执行 dry-run 定向测试；没有重跑 Python 全套、ASR、媒体正文审阅或 native/BFE/Sandbox/WFP harness，也没有修改 host 防火墙/网络策略。§201 冻结安全扫描仍是未封存 partial draft（12/93 源码/配置审阅行），不覆盖本节新改动。P2、P4 人工听审/Desktop、P5 Desktop trace 和 P6 owner/远端发布门槛继续开放，项目整体 **NOT READY FOR RELEASE**。


## 211. 2026-10-12 收紧 CONNECT DNS 出口与停用未认证的 BFE 写入口

- **P4 长样本状态：** 用户本轮给出的长视频路径与既有样本字节数及输出记录匹配；原始 ASR、默认模型校对侧车和时间轴均已存在。本轮不重复处理或读取转写正文。样本经先前 PyAV 核验为 938.968435 秒、双声道 AAC、无视频轨，满足 10 分钟音频门槛；至少三处人工对照听审与 fresh Desktop 数据流/隐私验收仍未关闭。
- **AUD-134 对策（操作风险缓解）：** 移除测试 EXE 的 --sandbox-bfe-smoke 直达命令分支；SandboxBfeSmoke.Run 现在无条件返回拒绝，且在 bootstrap 读取、账户创建、BFE open 或 WFP 调用之前退出。Sandbox host wrapper 与 guest runner（.ps1/.cmd）现为 fail-closed stubs，在创建目录/账户、启动 Sandbox 或运行控制器前退出。sandbox/README.md 已明确说明旧 env/GUID/SYSTEM 字段不能证明 Sandbox 身份，并移除可复制执行的 wrapper 命令。未来只有具备独立可信 guest attestation 的新设计通过审核后才可考虑恢复动态验证；当前不是 Sandbox BFE 验收通过。
- **AUD-135 对策（源码接口及假传输验证）：** NumericDnsQuestioner 现要求调用方提供 ILeaseDnsPermitProvider，分别按数值 resolver endpoint 和 UDP/TCP transport 取得 permit；permit 获取失败时不创建 socket。成功、异常及取消路径均先关闭 socket 再释放 permit；UDP 截断响应先释放 UDP permit，随后独立获取 TCP permit。当前只是必需注入的接口和 fake provider，尚无按真实 lease SID/AppID 安装/撤销 WFP 规则的生产 provider。
- **已验证地址回退：** CONNECT handler 在原 30 秒 setup deadline 中最多尝试 4 个已验证 DNS pin，单地址连接最多 5 秒；只在 socket 错误或该次尝试超时后继续，每次尝试重新取精确 IP:443 permit。未扩展到 pin 集之外。Harness 覆盖首地址失败后第二地址成功、尝试上限以及失败 permit 回收。
- **构建与离线验证：** 使用本机锁定 .NET SDK 10.0.401。CapturePipe.csproj 和 LeasePolicyCompiler.Tests.csproj Release x64 build 均为 0 warnings / 0 errors；capture-pipe --self-test 全部通过，覆盖 DNS permit 前置顺序/拒绝/socket 关闭和取消/UDP→TCP permit 生命周期，以及 CONNECT fallback；WFP policy/materializer offline tests 11/11 passed，其中新增 direct BFE entry 拒绝检查。两个项目的 dotnet format --verify-no-changes --no-restore 均通过，git diff --check 退出码为 0（仅报告现有工作树的 CRLF 转换提示）。
- **未执行操作与仍未关闭事项：** 没有运行 Sandbox wrapper、BFE/WFP 动态探针或触碰 host firewall；未访问外部 DNS 或 CONNECT 目标；capture-pipe self-test 只使用 loopback fixtures。生产 permit provider、双 lease 真实 WFP 矩阵/rollback、listener peer authentication、Chromium 进程树隔离、worker/service 接线及三条授权真实捕获均缺失，P2 仍 NOT PASSED。P4 人工听审/Desktop、P5 Desktop Skill trace、P6 owner/远端发布门槛继续开放；§201 冻结安全扫描仍是 12/93 行的未封存 partial scan，不覆盖本节。项目整体 NOT READY FOR RELEASE。

- **AUD-136（P1 操作边界，已做 fail-closed 缓解：其他 Sandbox-only WFP smoke 缺少独立 guest attestation）：** 旧 `ScopedNetworkWfpSmoke.ps1` 会从当前 PowerShell 映像派生 AppID 并添加动态 ALE block/permit 规则；旧 `UserSidChromiumSmoke.ps1` 会按目标用户 SID 添加动态阻断规则；`AppContainerIdentitySmoke.ps1` 默认模式会创建 AppContainer profile 并添加 package-SID WFP block。它们以“在 Sandbox guest 内运行”为流程假设，但脚本本身无法证明该边界。若由宿主高权限进程误运行，潜在影响是临时改变所选 PowerShell/用户/AppContainer 的网络行为；不是全机断网或产品 URL 入口。对策：前两者的写入主体已移除，只剩 fail-closed stub；AppContainer 默认 WFP 模式在任何账户/profile/WFP 工作前拒绝，仅保留明确跳过 WFP 的 -ChromiumOnly。CapabilitySmoke.ps1 仅查询 BFE/WFP，不写规则。5 个相关 PowerShell 文件均通过 AST 静态解析；未运行这些脚本。动态矩阵仍待一个可独占且可认证的新 Sandbox 方案。

## 212. 2026-10-12 P4 样本路径复核与当前 Skill 运行环境检查

- **P4 输入确认：** 用户再次提供的 `发现更多精彩视频 - 抖音搜索_4.mp4` 与既有记录相符，文件大小 22,715,944 bytes；先前 PyAV 核验时长 938.968435 秒，只有双声道 AAC 音频轨。对应 raw ASR、Agent 默认模型 reviewed sidecar、时间轴和四段 18 秒私有试听剪辑均已存在。本次仅核对文件元数据和产物是否存在，没有读取逐字稿正文、重跑 ASR 或覆盖输出。长音频和文本校对门槛满足，但不代表视频流/A/V 同步或声学准确性通过。
- **P4 后续验收：** 仍须至少三处人工对照试听并记录遗漏、插入、术语误识别和不确定处；四段剪辑位于本机私有输出目录。Fresh Desktop 中的 Agent 摘要、stdout/stderr、模型数据流和隐私复核尚未完成。需把听审差异以不含转写原文的摘要记入报告。
- **当前 Skill/CLI 能力：** 使用锁定环境的 `uv 0.12.7` 执行只读 `douyin-transcript doctor --json`，报告 `overall=ready`、`local_transcription=ready`，模型、ASR/解码依赖和私有输出目录权限检查均为 `ok`；同时明确给出 `browser_isolation=unavailable`、`douyin_urls=setup_required`。这确认本机可以继续处理本地媒体、URL 捕获仍安全失败关闭。该命令是在当前任务上下文运行的 CLI，不是新 Desktop 会话的 `/skills` 发现，也没有 Agent Skill 工具调用 trace，因此不能关闭 P5。
- **总体状态与验证范围：** 本次只读运行 doctor；未运行测试、重转写、访问 Douyin、启动浏览器、访问外部网络或改动 Sandbox/BFE/WFP/宿主防火墙。P2 仍缺生产服务/逐 lease 身份、可回滚 WFP provider、Chromium 进程树隔离及三条真实捕获；P4 人工听审与 fresh Desktop 数据流验收、P5 新会话发现/调用 trace、P6 owner 的许可/发行/仓库决定与远端 CI/clean install 仍开放。§201 冻结扫描仍是 12/93 审阅项的未封存 partial draft，不能覆盖本节。项目整体保持 **NOT READY FOR RELEASE**。

## 213. 2026-10-12 review-sidecar 交互输入阻塞修复

- **发现与影响：** `review-sidecar` 的正文接口要求结构化 JSON stdin；当操作者误在交互终端直接运行时，原实现会读取 stdin 并等待 EOF，容易被误认为命令挂起。该路径不泄露正文或改变任务结果，但属于可避免的 CLI 可用性问题。
- **修复：** 在任何 stdin 读取前检查输入流的 `isatty()`；检测到交互终端时立即以 `INVALID_INPUT` 退出，提示通过 stdin 提供一个 JSON 对象。非交互 pipe/结构化调用的 UTF-8、体积和唯一键校验保持原样；不读取或回显逐字稿正文。
- **验证：** 新回归用会在被读取时主动失败的 fake TTY 验证立即拒绝。`tests/unit/test_cli.py -k review_sidecar` 为 **6 passed、81 deselected**；Ruff check、format check 和针对两处代码的 `git diff --check` 通过。没有运行全量 Python 套件。
- **范围与总体状态：** 此项不改变 ASR、默认模型文本校对或原始稿/侧车分离策略。P2 生产捕获隔离、P4 人工听审与 Desktop 隐私验收、P5 新会话 Skill trace、P6 owner/远端发行门槛仍开放；§201 安全扫描是未封存 partial draft，不能覆盖该修复。项目整体仍 **NOT READY FOR RELEASE**。

## 214. 2026-10-12 P2/P6 当前状态复核与扫描权限阻塞

- **P2 源码状态校正：** 只读复核确认 SCM dispatcher、named-pipe host、受保护配置读取器及客户端 adapter 已有源码，但服务未安装，`CaptureServiceFactory` 仍使用 `FailClosedCaptureWorker`。WFP materializer 是不可部署结构预览；真实 provider/apply/readback/rollback、逐 lease worker/身份、浏览器树监督和 CLI production client 均未集成。因此准确状态是“存在未安装服务/IPC 原型，生产捕获与隔离尚未实现”，不是“完全没有 service 源码”。未运行服务安装或任何 Sandbox/BFE/WFP/host firewall 操作。
- **P6 当前状态：** 本地 root license、远端及 owner 对发行范围/仓库/许可的决定仍缺失。只读核对现有可见临时 SHA 缓存时，确认的候选缓存含 94 个制品，少于成员级证据清单涉及的 210 个制品；该候选不足以重放完整 `verify_spdx_evidence.py`。本次没有扫描整个用户磁盘、下载制品或运行一个必然因缺件失败的全量 verifier；因此不把旧 235 artifact 字节检查写作本轮复现。其他位置是否保留完整 cache 未证明。
- **安全扫描尝试：** 按 `codex-security:deep-security-scan` 流程请求对当前工作树做 repository-wide Deep Scan；工具在启动/加入前返回：`Codex Security Deep Scan discovery did not start or rejoin. Deep Scan cannot safely start a read-only worker: the parent must provide a managed filesystem permission profile.` 没有创建本轮 scan ID、worker、canonical manifest/findings/coverage 或新 findings。遵循工具返回，未重试、未启动替代扫描，也未把旧 §201 的 12/93 部分草稿当作当前全量扫描。
- **文档同步与范围：** 已把 release report/checklist checkpoint 更新到 §213，并将 P2 decision 首页改为准确描述“SCM/pipe prototype exists but is uninstalled; production worker/WFP absent”。本轮只做源码/文档读取和现有本地目录项元数据读取；未访问网络、转写正文、媒体、Sandbox 或系统策略。P2、P4、P5、P6 仍有硬性未完成项，项目整体保持 **NOT READY FOR RELEASE**。

## 215. 2026-10-12 P4 长样本重复提交路径核验

- **媒体复核：** 用户再次提供的本机 MP4 与既有 P4 产物对应；本次只核验文件大小、SHA-256、容器时长及流信息，结果为 22,715,944 字节、938.968435 秒、双声道 AAC 音轨且无视频轨。既有 raw ASR、默认模型文本校对侧车、timeline 和四段 18 秒试听片段均已存在；没有重新转写、覆盖输出或读取逐字稿正文。
- **验收状态：** 十分钟以上音频与模型文本校对门槛已满足，但样本不证明视频解码或 A/V 同步。至少三段人工对照听审及新 Desktop 会话的 stdout/stderr/Agent 摘要与数据流隐私复核仍需完成。试听片段留在本机受限输出目录，不复制进仓库。
- **范围：** 本轮为本机只读媒体元数据核验和文档状态同步；没有访问网络、启动 Sandbox、修改 WFP/Firewall 或重新运行 ASR/测试/安全扫描。P2、P5、P6 仍有未通过的发布门槛，整体 **NOT READY FOR RELEASE**。

## 216. 2026-10-12 全套回归、WFP 生命周期设计与 SPDX 复核

- **测试修正与结果：** 全套测试初次运行有 3 项失败，原因是 `tests/unit/test_sandbox_cleanup_ownership.py` 仍断言 Sandbox/WFP 脚本会继续执行，而当前脚本已按安全决策改为立即 fail closed。测试现改为断言 PowerShell/CMD 入口在任何副作用前抛错。定向文件 **7 passed**；随后锁定 Windows Python 3.11.15 全套 **641 passed、30 skipped（258.73 秒）**。跳过项包括两项未配置宿主路径的 native interop，以及 Windows 上不可用的 POSIX/FIFO/符号链接等行为。该测试不证明生产 WFP、Sandbox 或真实视频捕获。
- **本地检查：** 全仓 Ruff check、format、`uv lock --check`、canonical Agent Skill 校验、敏感文件扫描、SPDX 2.3 pinned schema 检查均通过；schema 工具使用隔离锁定环境执行。`git diff --check` 退出码为 0（存在既有 CRLF 转换提示）。
- **P2/AUD-137（部署前设计缺口：每 lease 的默认拒绝过滤器被标为持久）：** 只读复核 `LeasePolicyCompiler.AddPersistentPrincipalDenies()` 发现每个 lease principal 的 IPv4/IPv6 catch-all block 都标记为 `PersistentDefaultDeny`；其意图是提供服务或 worker 意外退出后的 fail-closed 底线。若未来直接按每个 job 写入，正常结束和崩溃都要求准确清理由服务拥有的持久对象，避免遗留 SID deny 和过滤器累积；不能在尚无 worker/job kill-on-close 证明时简单改成 dynamic，因为 dynamic session 关闭会自动删除对象，可能同时移除唯一默认拒绝。Microsoft WFP 文档说明 dynamic session 对象会随 session 终止删除，persistent 对象会保留到显式删除；显式事务可原子化相关更改。[WFP Object Management](https://learn.microsoft.com/en-us/windows/win32/fwp/object-management)、[WFP Best Practices](https://learn.microsoft.com/en-us/windows/win32/fwp/best-practices)。
- **对策与当前边界：** 在生产接线前先定义单一、固定的 service-owned persistent provider/sublayer 与可审计的 stale-lease 清理策略；将每次 lease 的临时 permit 放入独立 dynamic session/事务。默认拒绝的删除必须排在 Chromium/worker/后代进程终止、listener/socket 关闭和 job containment 证明之后；启动和异常回收都要 enumerate/read back 精确 provider-owned filter 集合并校验 SID、AppID、lease ID，再提交或回滚。当前 `NativeMethods.txt` 有 filter get-by-key/delete，但未绑定 provider/sublayer get-by-key 或 filter enumeration API，materializer 仍是 `not-deployable` 内存预览，`CaptureServiceFactory` 仍使用 `FailClosedCaptureWorker`，因此本节是接线前设计门槛，不是已发现的活动过滤器故障。不得加入 apply CLI 或在宿主试写 WFP。
- **P6/SPDX：** 使用 `uv run --project .\\tools\\spdx-schema-check --locked --no-sync python scripts/check_spdx_schema.py` 通过 pinned SPDX 2.3 schema 校验，schema SHA-256 为 `4126dc29f15e92feec92e9622f4939131ad58b125d6f578aa93e980a6e6f3212`。对当前已知 94 个制品的临时 cache 执行完整 `verify_spdx_evidence.py` 时，在清单要求但缓存缺失的 SHA-256 `001ed726c9bd5e2bc92faade7d37d889e9606a350b7d5529f0227df2e3bb57fd` 处失败；该 cache 仍不足以重现完整字节证据。证据清单列出 210 个制品；未扫描整盘，也未证明别处不存在完整 cache。SBOM 的 121 个 package 仍全部为 `licenseConcluded=NOASSERTION`，不得推断许可适用性或发行批准。
- **Skill/验收边界：** 当前 injected Skill catalog 中可见项目 `douyin-transcript`，但这只证明当前上下文发现；没有 fresh Desktop `/skills` 调用 trace。P4 至少三段人工听审和 Desktop 数据流隐私检查仍开放。P2、P4、P5、P6 均未全部通过，整体 **NOT READY FOR RELEASE**。
- **操作范围：** 本轮没有运行 Sandbox、打开 BFE/WFP、修改 host Firewall、访问外网、重转写或读取逐字稿正文。§201 冻结安全扫描仍为未封存 partial scan（12/93 行），Deep Scan 因环境缺少 managed filesystem permission profile 未启动；不得宣称本轮完成全量安全扫描。

## 217. 2026-10-12 per-lease WFP 生命周期修订、构建 BOM 与长样本复核

- **全套回归：** 添加 .NET 构建 BOM 生成器及其元数据边界回归后，锁定 Windows Python 3.11.15 全套为 **646 passed、30 skipped（260.76 秒）**。30 项平台跳过原因与 §216 相同类别，包括未配置 native interop 路径、POSIX/FIFO/符号链接行为及 Windows ACL 限制。Ruff check 通过，format 检查显示 84 个文件已格式化；`uv lock --check`、canonical Skill validator、敏感文件扫描、pinned SPDX 2.3 schema 及 `git diff --check` 均通过。Git 仅报告工作区既有 LF→CRLF 提示。
- **P2/AUD-137 设计修正：** `LeasePolicyCompiler` 不再把临时 lease SID 的 IPv4/IPv6 catch-all block 标为持久；预览现只将 browser/worker AppID catch-all 标为 persistent，并把 SID catch-all、listener block 和精确 permits 统一标为 lease-dynamic。原生编译器/物化器离线 harness **11/11 passed**。该改动降低失效 SID 规则永久积累的风险，但 dynamic SID deny 只能在 service 用禁止 breakaway 的 `KILL_ON_JOB_CLOSE` Job Object 约束整个 browser/worker 子进程树、suspended 创建后先入 job 再 resume，并证明进程树与 socket 已终止后关闭 session 时接线。service-owned 固定 AppID baseline、typed persistent/dynamic runtime plans、策略协调器、transaction/readback/rollback、启动前 baseline gate、job 生命周期和 BFE 失效恢复仍未实现。当前 AppID 仍是不可部署预览输入，尚未绑定固定受保护二进制。 `NativeMethods.txt` 已有 filter get-by-key/delete；provider/sublayer get-by-key 缺失，baseline reconcile 所需 filter enumeration 也未绑定。没有打开 BFE/WFP、调用 materializer 写入或更改 host Firewall；P2 仍 fail closed / **NOT PASSED**。§216 的逐 lease 持久 deny 与 stale SID 清理建议由本节修订。
- **P6 独立构建 BOM：** 使用 lockfile 指定的 .NET SDK **10.0.401**，执行 WFP policy-plan `Release/win-x64` no-restore build，并生成 [dotnet-windows-build-bom.json](dotnet-windows-build-bom.json)。BOM 含 11 项仓库相对源输入、4 个锁定 NuGet 包、38 个目标配置 CsWin32 生成源码及 5 个构建输出的大小/SHA-256；四个精确缓存 `.nupkg` 均由 `dotnet nuget verify --all` 再次验证通过。输出不含机器绝对路径、用户/账户标识或时间戳。它绑定这次本机源/生成/输出文件身份，但没有固定 SDK 安装包哈希、没有独立干净环境重现，不是运行时 SBOM，也不解决 Win32Docs/SDK/WDK 许可适用性、法律结论或发行授权。P6 远端 CI、clean install 与 owner 决定仍开放。
- **P4 长样本：** 再次只读检查用户给出的 `发现更多精彩视频 - 抖音搜索_4.mp4`，PyAV 报告 **938.968435 秒**、一条双声道 AAC 音轨、无视频流。现有 raw ASR、default-model reviewed sidecar、timeline 和四段私有 18 秒听审片段均已存在，本轮没有重复转写、覆盖输出或读取逐字稿正文。十分钟以上音频和文本校对门槛满足；至少三段人工听审差异记录及 fresh Desktop stdout/stderr/Agent-summary 数据流隐私检查仍待完成。该文件不提供视频解码/A/V 同步证据。
- **其他未闭合项与范围：** P5 仍无 fresh Desktop `/skills` 调用 trace；P6 完整 SPDX 字节 verifier 仍无法从已知 94 项 cache 重放其 210 项证据清单，未扫描整盘，其他 cache 是否存在未知。Deep Scan 因缺少 managed filesystem permission profile 未启动；§201 partial scan 仍不等于全量安全审查。全项目仍 **NOT READY FOR RELEASE**。本轮没有访问网络、运行 Sandbox、停止或附着现有 Sandbox、执行 BFE/WFP、修改 host Firewall、运行 ASR 或读取 transcript body。

## 218. 2026-10-12 P2 类型边界复核修复与服务启动门禁

- **独立复核发现：** 对 `LeasePolicyCompiler`、`WfpFilterMaterializer`、原生 harness 和 README 的只读复核发现两个 P2 源码缺口。其一，公共 `MaterializeForInspection(LeasePolicyDocument, …)` 接受可手工构造的公共 record，而 permit 形状只验证了非空 endpoint，未强制 browser→准确 loopback listener、worker→公网 DNS:53/TCP/UDP 或 worker→公网 pinned TCP:443。其二，persistent baseline 与动态 lease 分别编译，缺少组合 API 确认 lease browser/worker AppID 以正确角色受持久默认拒绝保护。当前 materializer 仅做内存结构预览，没有 WFP apply 路径；两项会误导审阅和未来接线，尚非当前宿主策略变更。
- **对策 1 — 限定物化边界与完整 permit 形状：** 将 `WfpFilterMaterializer` 和 `MaterializeForInspection` 收为原生构建程序集内部 API；规则校验现在识别唯一的 browser listener、DNS 和 upstream permit 名称/用途/完整条件，要求 DNS resolver 和 upstream IP 为数值公网地址，分别固定端口/协议，并核对每条动态 lease 的完整默认拒绝、listener、browser、DNS、upstream 规则组及身份一致性。新增伪造 `10.0.0.1` DNS permit 和任意 browser listener 端口拒绝回归。
- **对策 2 — 将 baseline 和租约绑定编译：** 新增内部 `CompileServiceWidePlan`，有界接收 protected browser/worker AppID 清单和完整活动 lease 集；校验 lease 集唯一性，并要求每个 browser AppID 出现在 browser baseline 角色、每个 worker AppID 出现在 worker baseline 角色。新增 browser/worker 两种 AppID 错配均 fail closed 的测试。独立 baseline/dynamic typed plan 可继续用于审阅，但 README 明确生产服务必须从组合入口构建；这仍是纯编译器结果，不验证 AppID 来源、实际部署或 WFP 状态。
- **对策 3 — 启动前拒绝开放 service IPC：** `CaptureServiceRuntime` 现在接受 `IServiceReadinessGate`，从 `START_PENDING` 进入后，在任何 named-pipe server 创建前、并受 30 秒启动期限约束调用 gate；gate 实现必须响应取消，并在任务完成前结束或回滚准备动作。只有 gate 成功且 pipe `Started` 后才报告 `RUNNING`。`CaptureServiceFactory` 注入的 `WfpBaselineUnavailableGate` 当前总是抛出明确的 coordinator-unavailable 错误。因此当前服务原型不会创建 pipe，也不会报告可运行状态，保持 fail closed。生命周期 harness 覆盖 baseline-before-pipe 顺序、gate 失败时工厂调用次数为零，以及 readiness 等待期间 STOP 后未创建 pipe。真正的 baseline coordinator、BFE transaction/readback/rollback、Job Object containment 与 service 安装仍未实现。
- **验证结果：** 使用用户 LocalAppData 中的锁定 .NET SDK **10.0.401 host** 进行 no-restore Release/win-x64 构建：WFP test project 和 CapturePipe 均 **0 warnings / 0 errors**。WFP compiler/materializer harness **14/14 passed**；capture-pipe `--self-test` 通过，覆盖启动门禁、18 个 DNS 策略场景、TCP pin connector、CONNECT、named-pipe 身份/帧/工件/断连等既有 harness。WFP、WFP test、capture-pipe 三个项目的 `dotnet format whitespace --verify-no-changes --no-restore` 通过。`test_dotnet_build_bom.py` **5 passed**；更新后的构建 BOM 记录 11 项源码输入、4 个 NuGet 包、38 项 generated source 和 5 项 build output。敏感文件扫描通过；`git diff --check` 返回 0，只有工作树现有 LF→CRLF 提示。
- **P4 样本与运行边界：** 用户再次给出的本机文件与既有 P4 长样本相同，当前确认文件存在、大小 22,715,944 字节；沿用先前 PyAV 的 **938.968435 秒**双声道 AAC、无视频轨证据。该音频样本满足 10 分钟音频门槛，既有 ASR/校对 sidecar/timeline/私有试听片段没有重跑或覆盖。本轮没有读取转写正文；至少三段人工对照听审与 fresh Desktop 数据流/隐私验收仍开放。
- **范围及总体状态：** 本轮没有打开 BFE/WFP、运行 Sandbox、改变 host Firewall、访问外部网络或运行 ASR。Python 全套没有重跑，§217 的 **646 passed、30 skipped** 仍是最新完整 Python 结果。P2 仍无生产 WFP coordinator、readback/rollback、Job Object/Chromium 进程树证据、安装器或三条成功授权捕获；P4 人工听审/Desktop、P5 fresh Desktop trace、P6 owner/clean install/远端 CI、完整 Deep Scan 仍未关闭。项目整体 **NOT READY FOR RELEASE**。

## 219. 2026-10-12 readiness 取消边界修复与 P4 术语复核

- **P2/AUD-138 — readiness 取消时可能提前报告停止：** `CaptureServiceRuntime` 曾用 `Task.WaitAsync(startupDeadline.Token)` 取消等待，而不等待 gate 自身的底层操作完成。若将来的 WFP coordinator 在取消后仍进行事务回滚，runtime 可能先报告 `STOPPED`，后台操作随后才结束。现已移除外层 `WaitAsync`，runtime 会等待 readiness gate 完成；接口契约要求 gate 在任务完成前观察取消，并完成或回滚所有准备操作。gate 成功返回后还会再次检查 deadline/STOP token，避免取消后继续创建 pipe。
- **回归与剩余生命周期要求：** 新增 deferred/non-cooperative readiness gate 场景，验证 gate 收到 STOP 后，在显式 drain 完成前服务不报告 `STOPPED`、不调用 pipe factory；drain 完成后才按正常 STOP 退出。CapturePipe Release/win-x64 build 为 **0 warnings / 0 errors**，离线 `--self-test` 中 SCM lifecycle、DNS、TCP connector、CONNECT、DNS wire 和 named-pipe 六组 harness 全部通过。完整 Python 回归未运行。若未来 gate 永不完成，服务会保持 `START_PENDING` 而不是假报停止；生产 gate 仍须保证取消、事务 rollback 和有界 drain。生产 factory 继续注入始终失败的 unavailable gate，没有 WFP apply 接线。
- **P4 长样本与 token 候选：** 用户给出的 MP4 与既有样本一致，重新只读核验为 938.968435 秒、22,715,944 字节、双声道 AAC、没有视频轨。raw ASR 与默认模型校对侧车已存在；本轮没有重跑 ASR。对已校对文本进行模型语境复核及本地 token 计数后，发现一个只出现一次、语境不匹配的行业词，按上下文改为更常见的术语并保存新的 numbered review-sidecar。该修正是语境推断，不是音频证据；原始 ASR SHA-256 前后不变，新侧车非空并含有“未对照音视频逐字听审”的范围说明。低频只用于提名候选，不能单独触发替换。
- **验收边界：** 十分钟以上音频及模型文本校对满足；至少三段人工对照听审、需复听的年份/术语、fresh Desktop stdout/stderr/Agent 摘要数据流隐私检查仍开放。样本没有视频轨，不能证明视频解码或 A/V 同步。P2 仍 **NOT PASSED**，P4 仍未完成人工听审和 Desktop 隐私验收；P5/P6 及完整安全审查也未关闭，项目仍 **NOT READY FOR RELEASE**。
- **本轮范围：** 未访问 BFE/WFP、Sandbox、host Firewall 或外部媒体站点；未重新 ASR。transcript 正文只在本机默认模型上下文中复核，没有复制到仓库或审核报告。没有运行安全扫描或全套回归。

## 220. 2026-10-12 纯托管 WFP 规则核心程序集与长样本路径复核

- **P2 程序集边界：** 将纯 managed `LeasePolicyCompiler`、输入 DTO、语义 plan 与共享公网地址策略放入 `native/windows/wfp-policy-core/WfpPolicy.Core.csproj`。WFP 预览 CLI 通过 project reference 使用该类库；Core 不引用 CsWin32、不包含 BFE/WFP API，也不执行策略写入。Core 仅授予 WfpPolicyPlan、当前语义 harness 和未来 `WfpPolicy.Runtime` friend access，以保持组合 plan 的内部边界。`CapturePipe` 仍未依赖 Core，未来生产服务须经高层 runtime facade 接线；当前 factory 仍 fail closed。
- **P2/P6 本地验证：** 使用锁定 .NET SDK 10.0.401，WFP Release/win-x64 构建为 **0 warnings、0 errors**；离线编译器/物化器 harness **14/14 passed**；Core、WFP plan、harness 的 whitespace verify 均通过；`dotnet restore ... --locked-mode` 成功。构建 BOM generator 现在纳入 Core 的项目引用与源码，处理 lockfile 中显式的 Project 依赖记录；新 BOM 包含 **14 项源输入、4 个 NuGet 包、38 个生成源码、7 个构建输出**。`test_dotnet_build_bom.py` **7 passed**。完整 Python 套件未重跑，最新完整结果仍为 §217 的 **646 passed、30 skipped**。
- **P4 用户提供路径：** 该路径与既有长样本一致，文件大小 **22,715,944 字节**；先前 PyAV 记录时长 **938.968435 秒**、双声道 AAC、无视频流。原始 ASR、默认模型校对稿、时间轴和试听片段已存在；本轮未重跑 ASR，也未读取或复制逐字稿正文。十分钟音频门槛已满足，但至少三段人工听审、术语/年份的声学核对，以及 fresh Desktop 的模型输入、stdout/stderr、Agent 摘要和数据流隐私验收仍开放。
- **不变的验收边界：** 本轮未访问 BFE/WFP、Sandbox、host Firewall 或外网；没有生产 coordinator、apply/readback/rollback、保护身份来源、Job Object/Chromium 进程树、安装器或三条获授权真实 URL 捕获证据。P5 fresh Desktop trace、P6 许可证/范围/仓库与远端 CI/clean install、完整 SPDX 字节 verifier replay 和完整安全扫描仍开放。项目仍 **NOT READY FOR RELEASE**。

## 221. 2026-10-12 P4 长样本任务状态复核与文档同步

- **用户给出的本地媒体：** 文件存在，大小 **22,715,944 字节**；锁定 PyAV 检查为 **938.968435 秒（15:38.968）**、双声道 AAC 音频轨、无视频轨。CLI 环境检查报告本地转写、balanced 模型、私有输出目录及权限检查就绪；Douyin URL capture 仍 `setup_required`，browser isolation 为 unavailable。
- **任务与产物：** 对该路径运行锁定 CLI 的 timestamps 请求后，返回 `status=success`、单项 `skipped=1`、`failed=0`，并指向已有 raw 输出；对应时间轴和 reviewed sidecar 已存在。本轮没有重复 ASR、覆盖输出、读取或复制转写正文。故 P4 的 10 分钟以上音频与 Agent 默认模型文本校对门槛已满足。
- **报告修订：** 更新 §1.1 的 P4 摘要，避免将长样本/耗时仍列为缺项；同步 `P2_ISOLATION_DECISION.md` 到 §219–§220 的 readiness 取消边界和 `WfpPolicy.Core` 程序集边界。
- **未关闭的验收：** 至少三处人工对照听审及差异记录、术语/年份声学确认、fresh Desktop 默认模型与 stdout/stderr/Agent summary 数据流隐私检查仍待完成。由于样本无视频轨，它不能证明视频解码或 A/V 同步。P2 生产 coordinator/WFP/worker/Job Object 与三条真实捕获、P5 fresh Desktop trace、P6 所有者/远端门槛和完整当前树安全审查仍未关闭。项目整体 **NOT READY FOR RELEASE**。

## 222. 2026-10-12 fail-closed WFP baseline coordinator prototype and CI coverage

- **Runtime prototype:** Added `native/windows/wfp-policy-runtime/WfpPolicy.Runtime.csproj`, a pure managed coordinator around an abstract transactional `IWfpPolicyStore`. It compiles the fixed persistent AppID baseline, checks stable provider/sublayer/filter ownership, compares the transaction snapshot before mutation, verifies complete desired readback, and attempts a compensating transaction if post-commit verification fails. No native BFE/WFP adapter exists, so the coordinator is not production-capable and is not connected to `CaptureServiceFactory`.
- **AUD-139 — incomplete filter enumeration at the managed baseline sublayer:** The first store contract enumerated only service-provider filters, which could miss another provider's filter attached to the service baseline sublayer. The snapshot contract now unions all filters owned by the service provider with all filters on its baseline sublayer; any foreign-provider or unrecognized sublayer object fails closed before mutation. Offline regression coverage includes both a legacy unmarked service filter and a foreign-provider filter. Unrelated filters under other sublayers remain untouched.
- **AUD-140 — duplicate deletion during policy drift:** Reconciliation now removes each stale or changed managed filter once, then adds the desired version. A same-key AppID drift regression confirms exactly one delete and desired readback.
- **AUD-141 — unsafe compensation after unexpected post-commit change:** Before applying inverse operations, rollback now reads the complete transaction snapshot and requires an exact match with the expected committed state. If a same-key foreign-provider replacement or any other unexpected change exists, the transaction aborts without compensating mutations and readiness remains closed. The fake store verifies that the replacement remains intact.
- **Verification and CI:** With pinned .NET SDK 10.0.401, runtime/harness whitespace verification passed, Release/x64 build completed with **0 warnings / 0 errors**, and the fake-store harness passed **9/9** (create/readback, idempotence, unrelated object preservation, drift replacement, provider conflict, unknown sublayer filter, readback compensation, uncertain rollback preservation, rollback failure and pre-commit abort). The focused BOM suite passed **9/9**. The Windows native CI job restores locked projects, performs formatting/build/harness checks, regenerates the .NET build BOM, compares stable source/lock/package fields, and requires Runtime build outputs. These are managed fake-store tests; no BFE/WFP/Sandbox/host firewall operation occurred.
- **P4 media:** The supplied path maps to the already processed 938.968435-second stereo-AAC sample with no video stream. The CLI found the existing task and skipped it; this update did not repeat ASR, overwrite sidecars, or access transcript text. The duration requirement is met; human comparisons and fresh Desktop data-flow/privacy review remain open.
- **P4 artifact identity:** The private task database associates this media with raw `发现更多精彩视频 - 抖音搜索_4__2.md` and timeline `发现更多精彩视频 - 抖音搜索_4__2_timeline.md`. Multiple reviewed siblings exist, including `发现更多精彩视频 - 抖音搜索_4__2.reviewed.md` and `发现更多精彩视频 - 抖音搜索_4__3.reviewed.md`; the latter has the newest file timestamp, but no durable sidecar-to-source mapping establishes which reviewed version was accepted. This report records the ambiguity rather than selecting by timestamp. The sidecar bodies were not read or copied; P4 listening evidence should name the exact sidecar and raw-file hash.
- **P6/provenance:** The build BOM now keeps the WFP plan/Core build and the Runtime/harness build as separate records. The related Runtime record includes 13 repository-relative source inputs, three project-only NuGet lockfiles, zero NuGet packages, and 17 Release outputs; the plan/Core record remains four verified NuGet packages. This is local build identity evidence, not native provenance, a runtime SBOM, a license conclusion, or remote reproduction. The full SPDX artifact replay and owner/remote release decisions remain open.
- **Overall status:** Production WFP backend, provider/sublayer native enumeration, real transaction/readback/rollback, CaptureService integration, Job Object/Chromium containment, disposable guest validation and three successful authorized captures remain outstanding. P4 human listening/Desktop privacy, P5 Desktop trace, P6 owner/remote gates and complete current-tree security review are also open. No Python full suite, remote CI, Sandbox, BFE/WFP, host firewall, or external URL was run. Project remains **NOT READY FOR RELEASE**.

## 223. 2026-10-12 P4 审校侧车持久绑定与试听材料溯源

- **AUD-142 — reviewed sidecar 未绑定原始任务：** 任务库此前只保存 raw Markdown 和 timeline 的路径/哈希，无法证明多个 `.reviewed.md` 候选中哪份属于某次已完成 raw 任务。SQLite schema v9 新增私有 `task_review_sidecars` 记录，保存 task ID、精确 raw 路径/哈希、reviewed 路径/哈希、模型文本校对/未听审 scope 与登记时间；不保存正文，不声称声学验证或用户接受。
- **登记规则与兼容：** `review-sidecar` 在任务库存在时尝试将新文件绑定到唯一 completed raw task；旧文件可通过 `bind-review-sidecar` 显式登记。绑定要求 raw 路径与哈希匹配任务、reviewed 文件为同目录同名 sibling、frontmatter task association 与 scope notice 正确、两文件位于已验证私有存储。修改时间不会用于选择。已有未登记文件不自动迁移；验证失败时仍保留已保存侧车，并显示未登记状态。
- **P4 当前任务映射：** 对用户提供的 938.968435 秒音频，任务库记录的 raw 与 timeline 文件均通过自身 SHA-256 核验；精确 `__2.reviewed.md` 已通过显式命令绑定到对应 `__2.md` raw 任务，raw 未改动。其摘要只保存在私有 DB 与私有听审 manifest；报告不复制转写正文或文件摘要。试听目录新增 `review-manifest.json`，记录媒体摘要、raw/timeline/reviewed 摘要及四段 WAV 摘要，四段实际 SHA-256 与 manifest **4/4 匹配**，未记录逐字稿正文。四段各约 18 秒；原始剪辑的确切起止秒数没有保存，因此 manifest 将其标为未知，文件名时间仅作听审提示。
- **验证：** schema 迁移、路径/哈希/scope 校验、新侧车 CLI 自动登记、重复登记幂等及 unmatched/misnamed 失败路径均通过。`test_tasks.py` 与 `test_cli.py` **127 passed、3 skipped（105.86 秒）**；Ruff check 与 format 检查通过；canonical Skill 与 `.codex` repo-scoped Skill validators 均通过。`doctor --json` 报告私有数据目录、任务库和试听目录权限均为 `ok`，本地转写就绪，URL capture 仍 `setup_required`。
- **仍开放：** 至少三段人工音频对照与差异记录、年份/术语声学核对、新 Desktop 会话的模型输入/stdout/stderr/Agent 摘要数据流隐私复核仍未完成。样本无视频流，不验证画面解码或 A/V 同步。P2 native WFP backend 仍未实现或接入，捕获继续 fail closed；P5 fresh Desktop trace、P6 owner/远端/clean install/完整 SPDX replay 与完整安全扫描也未关闭。未运行 ASR、Sandbox、BFE/WFP、宿主防火墙或外部 URL；整体仍 **NOT READY FOR RELEASE**。

## 224. 2026-10-12 P2 native backend 的 lossless readback 前置条件

- **AUD-143 — managed identity 不能表达完整 WFP 对象：** 只读复核发现 `WfpFilterIdentity` 保存稳定 key、provider/sublayer、显示字段、持久标志和语义 `LeasePolicyRule`，但没有可供 comparator 核验的完整 canonical native projection；provider/sublayer DTO 也未保留完整 flags、provider data 和安全描述符。将来若 adapter 把原生对象压缩成这些字段，可能把带未知 native 条件/标志/上下文/ACL 的 filter 当成期望对象。当前没有 native backend，因此这是接线前设计缺口，不是已发生的宿主策略错误。
- **对策：** 先定义 versioned canonical WFP provider/sublayer/filter projection，覆盖所有创建时可控和运行时有安全意义的字段，包括 layer GUID、完整 flags/action/weight、全部 typed conditions、provider/context/callout 数据、对象安全描述符，以及 system-assigned 字段的明确忽略规则。expected 和 actual 必须经同一规范化/序列化过程比较；未知枚举、字段或无法读取的安全信息一律 fail closed。明确 provider/filter/sublayer 的最小 ACL 与服务身份，并测试不具备 read 权限时不能将“未返回对象”当作对象不存在。
- **事务/枚举边界：** 固定 WFP enumeration 只返回 caller 有权读取的对象；[WFP access-control](https://learn.microsoft.com/en-us/windows/win32/fwp/access-control) 权限必须纳入后端失败策略。[FwpmFilterCreateEnumHandle0](https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmfiltercreateenumhandle0) 的枚举结果不是 live view；获取当前快照需在同一显式 transaction 内创建 enum handle 并完成枚举，且释放 handle/缓冲区。现有 `IWfpPolicyStore` 已要求事务内稳定视图，但仍缺能实现并验证该合同的 native API adapter。
- **范围与状态：** 本节只记录设计审核，没有新增 WFP API 调用、BFE 写入、Sandbox 或宿主 Firewall 操作；没有运行新的测试或安全扫描。`CaptureServiceFactory` 保持 unavailable readiness gate 和 fail-closed worker。应按“canonical native projection 与 ACL → 可注入 native API adapter → disposable Windows guest 的真实事务/readback/rollback 矩阵 → service 接线”的顺序推进，未完成前 P2 仍 **NOT PASSED**。

## 225. 2026-10-12 task review sidecar schema v9 后的完整 Python 回归

- **全套回归：** 锁定 Windows Python 3.11.15 的完整 `pytest -q` 为 **653 passed、30 skipped（252.90 秒）**。30 项平台/环境跳过包括两项未配置的 native interop 路径，以及当前 Windows 主机无法执行的 POSIX FIFO/symlink/dir-fd/mode-bit 场景；没有新的失败。
- **覆盖变更：** 本次全套回归覆盖 task database schema v9、`task_review_sidecars` 表、审校侧车登记 API、新建 sidecar 自动绑定 CLI 和旧 sidecar 显式绑定 CLI。它不覆盖 native WFP provider/backend、BFE、Sandbox 或真实 URL isolation。此前记录的 `test_tasks.py` + `test_cli.py` 定向合计 **127 passed、3 skipped**。
- **其它本地检查：** Ruff check/format、canonical 与 repo-scoped Skill validators、`git diff --check` 均通过；`git diff --check` 输出工作树既有 LF→CRLF 提示。P4 长样本没有重跑 ASR；reviewed sidecar 已与 raw 任务绑定，四段 WAV hash 与私有 manifest **4/4 匹配**，但人工听审和 Desktop 数据流/隐私验收未收到结果。
- **状态：** P2 仍缺 canonical native readback/backend、生产 worker 与 guest 动态验收，捕获 fail closed；P5 Desktop Skill trace、P6 owner/远端/clean install/完整 SPDX replay 和全量安全扫描仍未关闭。整体仍 **NOT READY FOR RELEASE**。

## 226. 2026-10-12 WFP readback projection v1 和假存储回归

- **AUD-143 后续：** 新增 `WfpNativeObjectProjection` schema v1，为 managed provider、sublayer、filter 定义字段有序、closed-world 的 expected projection。`BaselineCoordinator` 在核对现有对象和开始 reconcile 前要求快照投影类型/版本受支持、完整标记为 true、字段集合无缺失/额外/重排且值完全匹配；否则 fail closed，不修改 store。当前投影明确包括已建模的持久标志、显示字段、provider data、filter layer/action/weight、条件、context/reserved 与语义规则字段。
- **范围限制：** 这是纯托管 expected/actual DTO 合同，不是原生完整对象解析器。当前没有 native WFP adapter；fake store 由托管代码生成投影，不能证明真实 `FWPM_*0` 解码完整。schema v1 尚未解决对象 security descriptor/ACL、BFE 派生字段（例如 effective weight）、native 枚举/指针缓冲区安全读取及系统生成字段策略。未来 adapter 只有逐字段完成独立 native decode、在同一显式 transaction 里枚举并验证安全信息后，才可设置 complete；未知或不可读字段一律 fail closed。
- **验证：** 使用锁定 .NET SDK 10.0.401 host 在 `native/windows/wfp-policy-runtime` 运行 harness 格式检查、Release/x64 build 和 fake-store harness：格式检查通过，构建 **0 warnings、0 errors**，**12/12** 通过。新增回归覆盖 provider/sublayer/filter 投影字段缺失与额外字段，以及 incomplete projection 和不支持版本；异常投影在任何 store mutation 前被拒绝。BOM 清单生成器的定向回归 **9/9**，并重新生成 [dotnet-windows-build-bom.json](dotnet-windows-build-bom.json)，将新增投影源纳入 Runtime build 的 14 项 source inputs（17 项 outputs）。首轮尝试使用系统 `dotnet` host 时因它未解析锁定 SDK 而失败，改用锁定 SDK host 后成功。没有运行 WFP/BFE/Sandbox/host firewall 操作，也没有真实 native readback 测试。
- **P4 样本确认：** 用户再次提供的文件与当前 P4 样本相同：15:38.968、双声道 AAC 音频、无视频流；已登记 sidecar 与试听材料映射不变。本轮未重跑 ASR、未读取逐字稿正文。人工试听至少三段及 fresh Desktop 数据流/隐私验收仍待用户结果。
- **状态：** §224 的接线前风险已有部分源码缓解，但完整 native projection、对象 ACL、生产 backend、CaptureService 接线、Job Object/Chromium containment、disposable guest 与真实捕获仍未完成；P2 仍 **NOT PASSED**。P4、P5、P6 及完整当前树安全审查的开放项不变。项目仍 **NOT READY FOR RELEASE**。

## 227. 2026-10-12 P4 用户补充长样本路径与私有材料复核

- **文件身份：** 本轮检查用户补充的 `发现更多精彩视频 - 抖音搜索_4.mp4`。文件存在，大小为 **22,715,944 字节**；当前 SHA-256 与私有听审 manifest 中记录的源媒体摘要一致。manifest 记载的媒体时长为 **938.968435 秒（15:38.968）**、双声道 AAC、无视频流。此处没有重新运行 PyAV。
- **既有验收材料：** 私有 manifest 关联已有 raw、timeline、已绑定 reviewed sidecar 及四段听审片段；四段 WAV 的当前文件 SHA-256 与 manifest **4/4 匹配**。片段精确起止位置仍未记录，文件名时间仅是定位提示。
- **操作边界：** 本轮没有运行 ASR、读取/复制逐字稿正文或覆盖任何转写产物；也没有听音，因此不能据此给出声学准确率结论。P4 仍需操作者至少对照三段并简要记录漏词、增词、术语及不确定处，还需 fresh Desktop 数据流/隐私验收。
- **总体状态：** P2 native WFP backend、事务内真实枚举/readback/rollback、service 接线、Job Object/Chromium 进程树和三条不同授权真实捕获仍未通过；P5 fresh Desktop Skill trace、P6 owner/发行/远端验收、完整 SPDX replay 与完整当前树安全审查仍开放。未操作 BFE/WFP/Sandbox/host firewall，项目仍 **NOT READY FOR RELEASE**。

## 228. 2026-10-12 P6 当前缓存制品可重放性与 NuGet 哈希复核

- **SPDX 制品缓存：** 从 `docs/third-party-license-evidence.json` 按 verifier 实际使用的主 artifact、`license_file`、`license_notices` 与 `artifact_members` 字段去重，清单引用 **210 个唯一 SHA-256**。在当前默认 uv 缓存根目录按 verifier 预期的 `<cache>/<lowercase-sha256>` 平铺布局检查，找到 **0/210**。该目录实际是分层缓存（包括 `archive-v0`、`wheels-v6`）；本轮只检查了 verifier 可直接读取的平铺路径，不能据此断言其它分层缓存或其它已知路径没有制品。没有扫描整盘、下载制品或运行 SPDX verifier；完整字节证据仍不可复现。
- **NuGet 锁定包身份：** `native/windows/wfp-policy-plan/packages.lock.json` 的四个包均在默认 NuGet global-packages 目录存在 `.nupkg`。独立对当前 `.nupkg` 原始归档计算 SHA-512 后，四者均与 lock 的 `contentHash` 不同；四个 `.nupkg.sha512` sidecar 分别与其当前归档字节摘要一致。§228 当时把不同摘要范围当作待核验信号；后续 §231 确认这是 signed archive SHA-512 与排除签名元数据的 lock `contentHash` 语义差异，不代表当前缓存字节不符合 lock。§209 的签名验证与本轮 raw-digest 观察是不同证据层。
- **对策与范围：** 不改 lockfile 来接受当前缓存字节。用独立临时 NuGet cache 和获准来源执行 locked restore，逐项验证归档哈希与签名；若官方来源交付字节仍与 lock 不符，再审查 lock 版本、生成来源和差异后决定是否更新。对 SPDX 清单须提供含全部 210 个精确 SHA-256 文件名的受信缓存并重放 verifier，或明确记录不可得；不要把 0/210 的单一路径检查写成“制品不存在”。
- **状态：** 本 P6 复核只读本地缓存元数据/归档哈希；未访问网络、改动 NuGet/uv cache 或运行 SPDX verifier。另一个 P2 reader 子任务使用临时空 NuGet source 和既有 package cache 离线 restore/build，结果单列于 §230，不验证本节发现的原始归档哈希差异。P6 完整 SPDX replay、native 依赖 provenance/license notice、owner/发行决定和远端 clean install 仍未通过；P2 生产 native backend 仍 fail closed，整体 **NOT READY FOR RELEASE**。

> **后续更正（§231）：** 当时记录的 raw `.nupkg` SHA-512 与 lock `contentHash` 不同确实存在，但这不是锁定内容不匹配。NuGet 的锁定 `contentHash` 针对不含签名元数据的包内容；`.nupkg.sha512` 针对完整签名归档。两种摘要本来就可能不同。

## 229. 2026-10-12 P4 默认模型校对流程的可验证性边界

- **已实现的流程边界：** Agent Skill 要求调用 Agent 使用默认模型完成逐字稿校对；CLI 本身只做 raw ASR，并在摘要中明确输出 `result_scope=raw_asr_only`、`llm_review_status=not_performed_by_cli`。因此不能把 CLI 的任务 `success` 解释为模型已校对或内容已验收。
- **审计发现：** 审校侧车可通过 SHA-256 和任务 ID 绑定到具体 raw 输出，但 sidecar 元数据没有可信的宿主回执证明模型身份/参与，也没有“已接受为最终稿”的受信任务状态。`review-sidecar` 写盘成功后，即使任务登记失败，仍返回 `status=sidecar_saved`，另附 `task_binding` 说明失败/未登记；依赖方若只检查保存状态，可能误把未绑定侧车当最终结果。标点检查仅校验格式规则，不能证明语义断句正确。
- **对策：** Agent 编排应把“默认模型校对”作为交付前必经步骤，确认校对侧车与对应 raw 哈希绑定且 `task_binding=registered`；未满足时明确报告待处理，不称最终稿。若未来需要机器强制门槛，应由宿主提供不可由调用方伪填的最小校对完成回执，并维护单独的 final-accepted 状态；不要仅接受可任意填写的模型名称。保留 CLI 的 `raw_asr_only` 语义，并将句读标点检查表述为格式检查。
- **范围与状态：** 本节是只读流程/代码审查，没有读取样本正文、改代码或运行测试。当前长样本存在绑定的 reviewed sidecar，但这条绑定记录本身不证明听音、模型质量或模型身份；P4 人工对照与 fresh Desktop 数据流/隐私验收仍开放。项目整体仍 **NOT READY FOR RELEASE**。

## 230. 2026-10-12 P2 只读原生 WFP 快照 reader 与离线 fixture

- **实现：** 新增独立 `native/windows/wfp-policy-native-readback` 程序集，只绑定打开/关闭 engine、只读事务、provider/sublayer/filter 分页枚举、枚举句柄销毁和 `FwpmFreeMemory0`。Reader 把有界 native 字段复制到只读 snapshot DTO；字符串、blob、condition 数组、标量值、null 指针、计数上限和 enumeration 对象数均有边界处理。公开 DTO 使用 get-only 属性并在内部构造时复制集合，外部不能通过传入可变 collection 改写快照。
- **失败处理：** Readback 使用单一只读 transaction；每页 native array 与 enum handle 都在 `finally` 路径释放。API 错误、unsupported 值、字段边界异常、enum destroy 失败均保留失败或 incomplete 状态；显式 enum destroy 失败时 SafeHandle 再尝试清理，但快照仍带 `NativeApiFailure`。因为尚未读取并规范化 provider/sublayer/filter ACL/security descriptor、也未将 `effectiveWeight` 的系统排序语义规范化，reader 当前始终不能给出 `IsComplete=true`。WFP 访问权限本身也可能使枚举省略调用者不可读的对象。
- **离线验证：** pinned .NET SDK 10.0.401 下 Release/x64 reader 与 fixture harness 构建均为 **0 warnings、0 errors**；unmanaged fake-API harness **8/8 passed**，覆盖有效/unsupported snapshot、指针/数组/blob/string 边界、正常与异常释放、null enum handle、destroy 失败重试及 DTO 不可变性。CI 已加入 locked restore、format、build 和 harness 命令；BOM inventory-only 更新记录 **11 source inputs、45 generated bindings、10 Release outputs**。本轮没有运行完整 BOM generator、远端 CI 或 NuGet raw-archive verifier。
- **依赖证据边界：** 新 reader 的 locked restore 使用临时空 NuGet source 和现有 global package cache；新项目 lock 复用了 WFP plan 中的锁定版本/哈希。restore/build 本身没有检查原始归档摘要；§231 后续从官方源在全新隔离 cache 的 locked restore 和签名核验已确认，§228 归档 SHA-512 与 lock `contentHash` 不同源于签名摘要定义，而非 locked content mismatch。
- **P4 样本：** 用户本轮再次提供的路径对应 §227 已核验的 938.968435 秒双声道 AAC 样本；无视频流。时长门槛满足，人工对照至少三段及 fresh Desktop 数据流/隐私验收仍未完成。没有重跑 ASR、读取逐字稿正文或覆盖产物。
- **范围和状态：** 该程序集未引用 `WfpPolicy.Runtime`、`CapturePipe` 或 readiness/activation gate；未调用 BFE/WFP、Sandbox 或 host Firewall，未改变主机策略。它不是生产 policy backend，也没有证明真实 BFE 读取、ACL 可见性或实际 egress 隔离。P2 仍 **NOT PASSED**；P4、P5、P6 和完整当前树安全审核仍开放，整体 **NOT READY FOR RELEASE**。

## 231. 2026-10-12 P6 NuGet locked restore 摘要语义与已知 artifact cache 复核

- **NuGet 摘要口径：** §228 的四个原始归档 SHA-512 确实不等于 lock `contentHash`，但 fresh locked restore 证明这不是包内容或 lock mismatch。NuGet 的 `.nupkg.metadata` `ContentHash` 是排除签名元数据的包内容 SHA-512；历史 `.nupkg.sha512` sidecar 则是完整 `.nupkg` 文件 SHA-512。签名包的这两种值预期不同，不能把 sidecar/raw archive digest 直接与 lock `contentHash` 比较。[NuGet 的 metadata 设计说明](https://github.com/NuGet/Home/wiki/Nupkg-Metadata-File)明确区分了二者。
- **独立 locked restore：** 使用仓库固定的 .NET SDK 10.0.401，为 NuGet global packages、HTTP cache 和 plan/Core `obj` 创建新的临时隔离路径；显式设置 `NUGET_HTTP_CACHE_PATH=<fresh-temp>\http-cache`，并用临时 `Directory.Build.props` 将每个项目的 MSBuild intermediate/restore assets 导向 `<fresh-temp>\obj\$(MSBuildProjectName)`。恢复命令为 `dotnet restore native/windows/wfp-policy-plan/WfpPolicyPlan.csproj --locked-mode --force --source https://api.nuget.org/v3/index.json --packages <fresh-temp>\packages -p:NuGetAudit=false -p:NugetScratchRoot=<fresh-temp> -p:DirectoryBuildPropsPath=<fresh-temp>\Directory.Build.props`。restore 成功，空 global package cache 中取得四个锁定包；项目及 package lockfile 均未改动。之后对每个新下载归档执行 `dotnet nuget verify --all`，四次均以退出码 0 完成并识别 author 与 NuGet.org repository signature。

| NuGet 包 | lock / `.nupkg.metadata` `contentHash` | 新下载 `.nupkg` 原始 SHA-512 Base64 | `.nupkg.sha512` sidecar | `dotnet nuget verify --all` |
|---|---|---|---|---|
| Microsoft.Windows.CsWin32 0.3.360 | `hz2kh3RP3CaQWSfOYx8Oy5fyZQvQtjR7DERp0cH6YO/CKoV8tuFhVaWWHA51OHDqIFmas65uJuas1zHSaWZojw==` | `MsmgL4zaHSxZPitRrH5aOw92Sm4dGB7BKlZJS3psxPldc69u6p5GZFl5jUv1NQ9HIrm88HJfMEQ9Cbu/JZN6vg==` | 原始摘要匹配 | 通过 |
| Microsoft.Windows.SDK.Win32Docs 0.1.42-alpha | `Z/9po23gUA9aoukirh2ItMU2ZS9++Js9Gdds9fu5yuMojDrmArvY2y+tq9985tR3cxFxpZO1O35Wjfo0khj5HA==` | `/nmzaNfPY3CLP/iEsb2egDnX5Mn0YKF4Hm11PhB/6oH9ko9zR/s483vwP7nDabHDzZ4ZKzrcyFIMRvyeo7Ersg==` | 原始摘要匹配 | 通过 |
| Microsoft.Windows.SDK.Win32Metadata 71.0.30-preview | `h/FD+SrIlxgr+HD/WrJnLvpTdyWFAX7F0FCMPRxPJFTt4Qz70wGXKEBZvvIDX7om4hP0Tb7O0s1ND3aUvigL8g==` | `lEg58PTbUOMlLgBJeHEsdIvM0ldRuU9V4n5DUehlKuJ9b71dHRCZkpm/0jK+QeqIgOP5EYwOdCZvkzrH0aqI+g==` | 原始摘要匹配 | 通过 |
| Microsoft.Windows.WDK.Win32Metadata 0.13.25-experimental | `IM50tb/+UIwBr9FMr6ZKcZjCMW+Axo6NjGqKxgjUfyCY8dRnYUfrJEXxAaXoWtYP4X8EmASmC1Jtwh4XucseZg==` | `a+ckO4IT8LbPX1UrlF2R9yKr7/uNFu/stDh6TupyA3A2v/R2CQbNahW1u1DCMn+ueM2Zf3OADc2etel3YgXQfw==` | 原始摘要匹配 | 通过 |

- **工具检查：** `scripts/generate_dotnet_build_bom.py` 已分别核对完整归档摘要与 `.nupkg.sha512`、lock `contentHash` 与 `.nupkg.metadata`，并运行 `dotnet nuget verify --all`；其证据字段划分正确，本轮无需改工具或新增测试。NuGet 签名验证不构成许可证适用性或发行授权结论。
- **已知 SPDX cache：** 只复核文档中已知的 94 项本机 SHA-256 cache，没有整盘扫描或下载。对其运行 `python scripts/verify_spdx_evidence.py --cache-dir <known-private-cache>` 在缺少 SHA-256 `001ed726c9bd5e2bc92faade7d37d889e9606a350b7d5529f0227df2e3bb57fd` 时失败；210 项 SPDX member evidence 仍无法完整重放。本轮没有获取其余 artifact。
- **仍开放的 P6 门槛：** 完整 210-artifact SPDX evidence replay；项目 LICENSE、所有者批准的发行范围/仓库可见性及许可决定；Win32Docs 条款以及 SDK/WDK 许可对生成代码/输出的适用性审阅；锁定 Python/native artifact 的完整 source/build provenance、native linkage 与 notice 适用性结论；授权的远端 CI 矩阵与干净远端安装。P6 仍 **NOT PASSED**；P2、P4、P5 与完整当前树安全审查也未完成，项目整体仍 **NOT READY FOR RELEASE**。

## 232. 2026-10-12 P2 native readback adapter 与 P4 本地模型交叉检查

- **P2 adapter：** `WfpPolicy.Runtime` 现在项目引用 `WfpPolicy.NativeReadback` 并提供明确的 value adapter。Adapter 只接受 `IsComplete` 且无 native API failure 的 snapshot；仅映射当前 coordinator 理解的持久 AppID block 形状，保留 provider/sublayer/filter 的 canonical source projection，并拒绝未知条件和不匹配字段。新增 harness 覆盖完整 snapshot 映射、incomplete snapshot 和 readback failure 在 mutation 前拒绝。锁定 .NET SDK 10.0.401 x64 Release build 为 **0 warnings、0 errors**；Runtime fake-store harness **15/15**，native reader unmanaged fixture harness **9/9**。
- **P2 限制和对策：** 当前 native reader 仍显式记录对象 ACL/security descriptor 未取回/规范化、effectiveWeight 排序语义未规范化，以及尚未枚举/绑定的引用对象信息，因此它始终返回 incomplete。WFP enumeration 也可能省略调用者无权读取的对象；未来必须在服务身份下证明拥有枚举相关对象所需权限，不能把“未返回”推断为“不存在”。没有具体 `IWfpPolicyStore` 调用 adapter，也没有 production apply/readback/rollback 或 CaptureService 接线；服务 readiness 和 URL capture 继续 fail closed。下一步先实现并测试同一显式 transaction 内的完整枚举、ACL/security descriptor 读取/规范化、effectiveWeight 安全比较及服务身份枚举权限；增加 concrete native store 与端到端 mutation/readback/compensating rollback fixture；随后在 disposable Windows guest 验证权限、竞争、回滚与进程退出边界。只有这些成立后再接入服务。不得将 fake harness 作为真实 BFE/隔离证据。
- **P4 本地交叉检查：** 用户授权由 Agent 处理四段听审片段。本轮尝试取得固定版本的 fast ASR 模型时，下载在建立连接阶段失败（`ConnectError`）；未把用户音频上传到云端。随后使用本地已安装的 balanced profile 对四段 WAV 复跑 ASR，并和已绑定的 reviewed sidecar 做了文本对照。发现项仅作为复听候选：ASIN/专名识别、竞价术语归一、与上下文年代冲突的年份；最后一段没有额外高置信候选。四段复跑均来自同一 profile，不是独立模型对照；词频/token 信号或语境也不能确定音频内容。raw 与 reviewed 文稿均未修改，报告不含转写正文。候选类别与每段定位记录在私有听审目录的 `model-crosscheck_20261012.md`。
- **听审边界：** 当前执行环境没有将本机 WAV 输入到可感知音频的接口，因此不能声称完成了人工/Agent 听音。至少三段真实声学对照、对年份/术语的确认，以及 fresh Desktop 模型输入、stdout/stderr、Agent 摘要隐私复核仍未完成；P4 仍 **NOT PASSED**。用户可用私有听审包按 manifest 的精确片段位置复核，记录漏词、增词、术语差异或不确定项。该样本只有 AAC 音轨，不验证视频解码或 A/V 同步。
- **当前回归与静态检查：** 锁定 Windows Python 3.11.15 全套 **653 passed、30 skipped（263.33 秒）**。跳过项为未配置的两个 native interop 路径，以及当前 Windows 不提供的 POSIX/FIFO/符号链接/目录句柄语义。Ruff check/format、Python lock check、敏感文件扫描、canonical Skill validator、Runtime 与 native-reader `dotnet format --verify-no-changes`、BOM generator `--skip-build` 和 `git diff --check` 均通过。Runtime fake-store 和 native-reader unmanaged fixture 分别 **15/15、9/9**；两者 Release build 均为 **0 warnings/0 errors**。以上不等同于远端 OS matrix 或 live isolation 验收。
- **其它开放门槛：** 既有 Codex Security prompt-only Diff scan 仍是冻结旧快照的未封存 partial 状态（12/93 review rows）；它不覆盖本节后的 P2 适配器改动。本轮按 scan ID 尝试恢复，工具拒绝继续，提示所选工作树已变化、需重新选择 Uncommitted changes；未启动重复扫描。预检为 ready，但 scan 已在 discovery 阶段，因此工作台拒绝更新其 preflight 状态。需在 Codex Review 中重新选择当前未提交变更后，才能继续正式 diff scan。P5 仍缺 fresh Desktop Skill trace；P6 仍缺 210 项 SPDX replay、许可证/发行 owner 决策、完整 native provenance/linkage/notice、远端 CI 与 clean install。没有访问 BFE/WFP、启动/停止 Sandbox、修改 host Firewall，也没有运行真实 URL 捕获。项目仍 **NOT READY FOR RELEASE**。

## 233. 2026-10-12 P4 独立中文 ASR 交叉检查与年份冲突

- **新增本地复核：** 用户授权由 Agent 处理至少三段音频。本执行环境不能把本机 WAV 交给可感知音频的模型，因此没有声学听审。为增加候选检查，本轮从 ModelScope 获取官方 SenseVoiceSmall Q8 GGUF，并使用已校验 SHA-256 的 FunASR Windows CPU runtime 对四段既有 18 秒 WAV 离线识别；所有音频处理留在本机，未上传音频。模型/runtime 只存于私有数据目录。预缓存的 Distil Whisper 在中文片段上输出英语文本，故排除为无效对照。项目固定 fast 模型从 Hugging Face 下载仍以 `ConnectError` 失败。
- **候选结果：** 01:02–01:20 的独立 ASR 对“类型/关键词”较原 balanced 结果更贴合，但 ASIN 的实际发音仍需核对；05:31–05:49 两模型都把 bid 相关发音混写为同音字，术语归一有亚马逊语境支持但未经听音；08:32–08:50 两模型均识别为 2019；08:50–09:08 独立 SenseVoice 识别为 2026，而原 balanced ASR 与 reviewed sidecar 为 2016。后一区间属于最高优先级年份冲突；2019→2022→“当前”的上下文使 2026 有合理性，但不足以代替声学证据。08:59 片段后半的词项也有模型间分歧。
- **产物与隐私：** 识别候选和方法记录在私有输出目录的 `model-crosscheck_20261012.md`；独立模型输出也留在私有目录。审计报告不复制逐字稿正文。raw、reviewed sidecar 和空白听审表均未修改；没有基于 token 频率或语境自动改词。
- **结论与对策：** 本轮完成的是独立 ASR 候选交叉检查，不是听审验收。优先让具备音频感知能力的人/宿主确认 08:50–09:08 的年份，其次核实 01:02–01:20 的 ASIN、05:31–05:49 的 bid 术语；在确认前保留现有 sidecar。P4 至少三段真实声学对照与 fresh Desktop 输入、stdout/stderr、Agent 摘要数据流隐私复核仍未完成，P4 **NOT PASSED**。整体仍 **NOT READY FOR RELEASE**。

## 234. 2026-10-12 当前源码差异安全审核（已封存，覆盖部分）

- **扫描身份与结论：** Codex Security Diff Scan `a5372a38-3d67-4fb7-a5fd-a38e197a0a3d`；基线/目标 revision `b166778ee5283591a1b799535b746ba198e38653`；冻结快照摘要 `codex-security-snapshot/v1:sha256:bbc0679427e5baa29cdfcdc5aa1d6a0946a92446ea2ebd967d5b110b444def0b`。111/111 条生成的源码/配置审查项均已完成；未确认可报告安全发现，finding 数为 0。
- **审查分组：** Windows 捕获命名管道与启动路径 21 项；WFP 编译、读回、计划和 runtime adapter 44 项；Python 捕获/存储、CI、依赖与 SPDX 证据工具 46 项。另对 `.codex` Skill 入口、规范 Skill 的提示注入/模型数据流条款、`SECURITY.md` 及项目状态文档中的相关段落作了聚焦审阅。
- **结论边界：** 未发现当前生产入口可达的 WFP/捕获安全绕过。捕获 service 仍在 ready gate 失败关闭；WFP 物化器只是预览，读回快照不完整时 adapter 拒绝继续；缺少可信系统 broker 时 URL 捕获与短链解析拒绝工作。这些是 P2 集成/发布门槛，不是已确认漏洞。检查到的构建 stderr 与锁文件 URL 也未形成独立攻击路径或凭据泄露发现。
- **覆盖与工件限制：** 扫描已封存，但 coverage 是 **partial**：剩余变更文档、测试、fixtures 和生成证据没有在本轮逐行审阅；扫描快照之后的 P4 文档更新仅为文档差异，代码/配置仍与冻结目标一致。最终封存器提示 4 份临时保存的 review receipt 不在 canonical scan directory，因而未能解析 5 个 surface receipt 引用；机器报告仍把这些 surface 标为 “Needs follow-up”。本节从实际审查分组结果记录结论，不把 coverage partial 改写成全仓完整审查。没有运行测试、构建、安装、URL 捕获、WFP/Firewall 或 Sandbox 操作。
- **P4 听审状态：** 本执行环境仍不能实际感知本地 WAV 音频。SenseVoice 与 balanced ASR 的交叉识别在 08:50–09:08 对 2016/2026 有冲突；未据上下文自动改稿。需由具备音频感知能力的人确认年份，再核实 ASIN 与 bid 术语。P4 仍 **NOT PASSED**。

## 235. 2026-10-12 文档、测试夹具与隐私复审

- **AUD-144（已修复）：** 只读文档/测试/夹具/生成证据审阅发现，审核报告两处历史构建记录把本机用户目录写入仓库文档；同一审核资料的 `MEMORY.md` 还保留了用户媒体的完整本机路径。三处均已改写为锁定 SDK host 或“用户提供的长样本”，不再包含实际账户/媒体路径。对测试、fixture、SPDX/BOM/PE 结构化证据的定向审阅未发现真实转写正文、凭据或额外个人路径；其中可见的用户目录例子是明确的 `Example` 占位符。
- **AUD-146（已修复）：** 原 `check_sensitive_files.py` 检查敏感文件名、目录和高置信凭据，但不检测普通 Markdown 正文中的本机账户路径；因此本次路径回归未被旧扫描器发现。现在增加 Windows 用户目录的反斜杠、正斜杠和 JSON 双反斜杠检测，且错误输出只报告文件名与类别、不回显匹配路径。`Example`、`USERNAME` 和 `<account>` 模板仍可用于文档。
- **AUD-145（已澄清）：** `MEMORY.md` 曾称四段剪辑已绑定精确源区间，而较早的 §227 文本说起止秒数未知。只读取私有听审 manifest 的时间字段后确认，四段当前均有精确起止秒数；较早说法是后续 manifest 修订前的历史状态。已把当前摘要统一为“精确区间已在私有 manifest 登记”。没有读取剪辑文本、ASR 输出或转写正文。
- **状态摘要同步：** `ACCEPTANCE.md`、`RELEASE_REPORT.md`、`RELEASE_CHECKLIST.md`、`PROJECT_REMEDIATION_PLAN.md`、`PROJECT_IMPLEMENTATION_PLAN.md`、`OWNER_DECISIONS.md`、`THIRD_PARTY_LICENSE_REVIEW.md`、本期安全报告、两份 README、`CHANGELOG.md` 与 `MEMORY.md` 的当前状态摘要已更新到 §235。§234 安全差异扫描已封存，111/111 生成的源码/配置项完成、0 个 reportable findings，但覆盖仍为 partial 且 machine receipt 有 unresolved 状态；这不是完整全仓安全验收。NuGet 摘要范围差异已由 §231 澄清；完整 SPDX replay、license/distribution owner decisions、native provenance/linkage/notices 和远端 CI/clean install 仍开放。
- **P4 与操作边界：** 用户已授权处理听审，但此执行环境没有音频感知输入能力；现有独立 ASR 交叉结果只能定位风险候选，不能确认 2016/2026、ASIN 或 bid 术语。raw/reviewed 文稿均未更改；P4 听审和 fresh Desktop 数据流隐私验收仍未通过。除 §235 记录的目标测试与扫描外，未运行全套测试、构建或依赖安装，也未操作 BFE/WFP/Sandbox/host Firewall。
- **结论与验证：** 定向 `test_sensitive_files.py` **19 passed、1 skipped**（POSIX 专属目录句柄用例在 Windows 跳过）；仓库级 `check_sensitive_files.py` 通过。原始 Windows Python 全套 §232 仍是最新全套结果，本节没有重跑。测试和生成证据审阅没有发现其它个人路径、凭据或媒体正文；AUD-144 的路径回归已修复，AUD-145 的时间字段冲突已澄清，AUD-146 增加防回归扫描。P2/P4/P5/P6 验收门槛仍未关闭，整体 **NOT READY FOR RELEASE**。
- **后续对策：** P2 先完成 ACL/security descriptor/effectiveWeight 规范化、具体 transaction-scoped WFP store/readback/rollback、逐 lease worker/Chromium 进程树隔离，并在 disposable guest 验收真实捕获；P4 完成至少三段真实听审和 fresh Desktop 数据流隐私验收；P5 获取新 Desktop Skill 调用 trace；P6 完成 owner 的许可证/发行决定、210 项 SPDX 字节重放、native provenance/linkage/notice 审阅及远端 CI/clean install。项目整体继续 **NOT READY FOR RELEASE**。

## 236. 2026-10-12 用户补交 P4 片段与 SPDX 离线重放

- **P4 样本接收：** 用户补交 `focus_01m11.wav`、`focus_05m40.wav`、`focus_08m41.wav` 三段现有听审片段。它们与已登记听审包中的同名样本一致；这次没有重跑 ASR、读取逐字稿或修改 raw/reviewed 文件。当前执行环境没有音频感知接口，因此不能把文件接收或既有 ASR 候选写成听审结论。01:02–01:20 的 ASIN/专名、05:31–05:49 的 bid 术语仍待听音；08:32–08:50 的年份候选以先前模型交叉结果为线索，均未由本节声学确认。更高优先级的 08:50–09:08 年份分歧对应 `focus_08m59.wav`，不在本次三段附件内。P4 仍 **NOT PASSED**，还需至少三段真实声学对照及 fresh Desktop 数据流/隐私验收。
- **P6 字节重放：** 在不下载、不执行制品的情况下，对已存在的私有 SHA-256 cache 重新运行 `scripts/verify_spdx_evidence.py`。cache 目录有 235 个普通文件、共 2,097,567,472 字节，非 reparse point；verifier 通过并报告 41 packages、210 artifacts、41 metadata、9 license、2 notice、1,149 supplemental members。此前 §231 记录“已知 cache 仅 94 项”是当时检查范围的历史快照，不再代表当前 cache 内容；没有整盘扫描或下载其余制品。该命令只验证已记录字节及元数据，不判断许可证适用性、notice 完整性、来源、链接关系或再分发许可。
- **状态与边界：** P6 仍 **NOT PASSED**：项目根 LICENSE、所有者发行范围/仓库归属与可见性决定、Win32Docs/SDK/WDK 条款对生成输出的适用性、完整 native provenance/linkage/notices、授权的远端 CI 与 clean install 均未完成。P2 生产 WFP store/ACL 规范化/真实隔离、P5 fresh Desktop trace、完整安全审核也仍开放。没有改动源码、听审或转写产物；没有重跑测试、安装依赖或触碰 WFP/Sandbox/Firewall。项目整体 **NOT READY FOR RELEASE**。

## 237. 2026-10-12 native readback 的 effectiveWeight 标量校验

- **修复：** `FWPM_FILTER0.effectiveWeight` 现在仅在 tag 为 `FWP_UINT64` 且值指针有效时作为已解码标量证据；其他 tag 与 null `UINT64` 指针都会保留 `EffectiveWeightNotNormalized` issue，原有 native decode error 仍保留。根据 Microsoft [FWPM_FILTER0](https://learn.microsoft.com/en-us/windows/win32/api/fwpmtypes/ns-fwpmtypes-fwpm_filter0)，该字段是读取/枚举返回的、分配给对应 `FWPS_FILTER0` 的权重；[Filter Weight Assignment](https://learn.microsoft.com/en-us/windows/win32/fwp/filter-weight-assignment) 说明 BFE 使用的 filter weight 是 `FWP_UINT64`。输入 `weight` 字段的 `FWP_EMPTY`/`FWP_UINT8` 自动或范围分配规则不应用于把返回值误判为未规范化。该读取器不会用单个标量推断跨 sublayer 的全局 arbitration 顺序。
- **离线验证：** pinned .NET SDK 10.0.401 x64 Release build 为 **0 warnings、0 errors**；无 BFE/WFP 的 unmanaged fixture harness **10/10 passed**，新用例覆盖有效 `UINT64`、错误 tag 和 null 指针；`dotnet format` 校验通过。`docs/dotnet-windows-build-bom.json` 已重新生成，纳入当前 native reader 与 fixture 源码/产物摘要。
- **边界：** 这只关闭了一个保守解码标记，不会让 snapshot complete。provider/sublayer/filter 安全描述符与 ACL 仍未读取/规范化，调用者无权读取的对象可能未枚举，callout/provider-context 引用未完整清点；没有具体 `IWfpPolicyStore` 或生产 apply/readback/rollback 接线。没有对 BFE/WFP、Sandbox 或 host Firewall 做操作。P2 继续 **NOT PASSED**；P4 声学听审/Desktop 隐私、P5 fresh Desktop trace、P6 owner/许可/远端门槛及完整当前树安全复核仍开放。整体 **NOT READY FOR RELEASE**。

## 238. 2026-10-12 native readback 的 security descriptor 读取与规范化

- **实现：** 只读 reader 在同一只读 transaction 内为每个枚举出的 provider、sublayer、filter 请求 owner/group/DACL（`SECURITY_INFORMATION=0x7`，即微软定义的 `OWNER=0x1 | GROUP=0x2 | DACL=0x4`）。provider、sublayer、filter security-info API 都返回一份 descriptor；该 WFP 指针由 `FwpmFreeMemory0` 释放，其他 SID/ACL 出参是该缓冲区的别名。读取器以 `GetSecurityDescriptorLength` 获取长度，将上限设为 1 MiB，复制后解析 self-relative descriptor，要求 DACL 顺序规范，保存 owner/group/DACL SDDL、规范 SDDL 的 SHA-256、原二进制长度及 DACL 状态。provider/sublayer/filter snapshot 会保留该数据。无论 API 成功或错误，只要函数返回非空 descriptor 指针，finally 路径都会调用 `FwpmFreeMemory0` 释放。微软文档说明 [provider](https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmprovidergetsecurityinfobykey0)、[sublayer](https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmsublayergetsecurityinfobykey0) 与 [filter](https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmfiltergetsecurityinfobykey0) security-info API 返回 descriptor；[SECURITY_INFORMATION](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-dtyp/23e75ca3-98fd-4396-84e5-86cd9d40d343) 定义组合 flag；[WFP access-control 模型](https://learn.microsoft.com/en-us/windows/win32/fwp/access-control)说明 BFE 忽略 SACL ACE 并使用其自有审计，因此读取器不请求 SACL。
- **Fail-closed 语义：** descriptor 成功解析仍会为每个对象留下 `SecurityDescriptorPolicyUnverified`，因为尚未与批准的服务 ACL 逐项比较；失败、超长、损坏或非规范 descriptor 留下 `SecurityDescriptorNotNormalized`。snapshot 还会附加全局 `EnumerationCompletenessUnverified`：当前无法证明服务身份能枚举被对象级 read ACL 隐藏的全部对象。此处没有把“未返回”当作对象不存在，也没有声称 ACL 策略已通过。
- **验证：** pinned .NET SDK 10.0.401 x64 Release 构建 **0 warnings、0 errors**；native unmanaged fixture harness **14/14**，新增覆盖有效 self-relative descriptor、损坏/非规范 DACL、区分 null 与 absent DACL、按 0x7 只请求 owner/group/DACL、成功返回但 API 报错时的内存释放、枚举失败及 enum destroy 失败的描述符清理。由于 snapshot 构造器新增 descriptor 字段，Runtime fake-store harness 夹具已同步更新并通过 **15/15**。native reader 与 Runtime `dotnet format` `--verify-no-changes` 均通过；`scripts/generate_dotnet_build_bom.py` 完整构建并重生成 BOM 成功。
- **边界与状态：** 所有新验证均为离线 unmanaged fixture；未连接 live BFE，也未执行 WFP/Sandbox/host Firewall 操作。descriptor 值目前没有期望服务 ACL policy comparison；服务身份枚举覆盖未知；callout/provider-context 引用对象仍未完整枚举；不存在具体生产 `IWfpPolicyStore`、apply/readback/rollback 或 CaptureService 接线。P2 仍 **NOT PASSED**，URL capture 继续 fail closed。
- **P4 样本：** 用户再次提交 `focus_01m11.wav`、`focus_05m40.wav`、`focus_08m41.wav`。文件在此前登记的私有听审位置可见，但当前执行环境没有声学感知接口；没有声称听过，也没有将 ASR 候选当成听音结论。既有 08:50–09:08 年份争议对应 `focus_08m59.wav`，不在这三段附件中；至少三段真实声学核对及 fresh Desktop 数据流/隐私验收仍开放。未重跑 ASR、读取逐字稿正文或修改 raw/reviewed 产物。
- **整体状态：** 没有重跑 Python 全套、远端 CI 或真实 BFE；P2/P4/P5/P6 和完整当前树安全审阅仍未全部通过。项目整体 **NOT READY FOR RELEASE**。

## 239. 2026-10-12 Windows Python 3.11.15 全量回归复跑

- **执行：** 在当前工作树使用 `.venv-audit-py311` 运行 `python -m pytest -q`；结果 **660 passed, 30 skipped, 0 failed**，耗时 166.08 秒。
- **跳过边界：** 30 个 skip 来自 POSIX 专属行为、此 Windows 会话的 symlink 创建权限、未配置 native capture interop server 等环境条件；该结果不补足这些平台/运行时覆盖。
- **音频请求边界：** 本轮收到三段 P4 WAV 附件，但当前会话没有可实际感知音频的接口。既有 ASR 交叉核对只能定位候选差异，不能报告为人工听辨或验证漏词/增词；P4 仍待具备音频感知的听审者完成。
- **状态：** 本次只复跑测试并更新证据；未修改转写产物、未触发 WFP/BFE/Firewall/Sandbox 操作，也未改变 P2/P4/P5/P6 gate。整体仍 **NOT READY FOR RELEASE**。

## 240. 2026-10-12 P2 callout readback 与 filter 引用闭包

- **实现：** `WfpPolicy.NativeReadback` 在既有显式只读事务中新增 callout 分页枚举、owner/group/DACL 描述符读取和有界 DTO 解码，记录 callout key、显示字段、flags、provider key/data、applicable layer 与 BFE callout ID。完成全部枚举后，reader 检查 filter 的 callout GUID 是否唯一存在，并核对 callout applicable layer 与 filter layer 一致；缺失、空 key、重复 key 或错层均留下 incomplete issue。没有添加 WFP 写 API，也未连接 store 或服务。
- **接口依据：** Microsoft 文档说明 null template 会枚举全部 callout，并要求在同一显式事务中创建和使用枚举器；调用方还需要容器 `FWPM_ACTRL_ENUM` 和对象 `FWPM_ACTRL_READ` 权限，故枚举不可见性仍不能排除隐藏对象。字段来自 [`FWPM_CALLOUT0`](https://learn.microsoft.com/en-us/windows/win32/api/fwpmtypes/ns-fwpmtypes-fwpm_callout0)，管理 API 为 [`FwpmCalloutCreateEnumHandle0`](https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmcalloutcreateenumhandle0)、[`FwpmCalloutEnum0`](https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmcalloutenum0) 和 [`FwpmCalloutGetSecurityInfoByKey0`](https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmcalloutgetsecurityinfobykey0)。
- **验证：** pinned .NET SDK 10.0.401 下 Release/x64 build 为 **0 warnings、0 errors**；native unmanaged harness **18/18**；Runtime fake-store harness **15/15**；native reader `dotnet format --verify-no-changes` 通过。完整 .NET build BOM 重新生成，plan/Core 记录 15 source inputs、38 generated sources、7 outputs，Runtime/harness 记录 12 source inputs、52 generated sources、10 outputs。测试覆盖引用存在、缺失、错层、重复 key、调用失败清理，以及现有 transaction/descriptor/handle 边界。
- **仍开放：** filter provider-context 引用及其类型联合仍未读取；每个对象的安全描述符仍未与批准的 service ACL 比较；BFE 的对象级 read ACL 仍使完整可见性无法证明。所有新增证据均来自离线 fake API；没有 live BFE、宿主 WFP/Firewall/Sandbox 操作或生产 `IWfpPolicyStore`。Runtime 仍在 mutation 前拒绝 incomplete snapshot，URL capture 继续 fail closed，P2 仍 **NOT PASSED**；P4/P5/P6 也保持开放，整体 **NOT READY FOR RELEASE**。

## 241. 2026-10-12 P4 三段附件身份复核

- **文件身份：** 用户本轮附上的 `focus_01m11.wav`、`focus_05m40.wav`、`focus_08m41.wav` 与私有听审包中的同名文件 SHA-256 一致。三段均为 18 秒、16 kHz、单声道、16-bit PCM WAV；manifest 中记录的片段长度和文件摘要与本地文件相符。
- **验收边界：** 这只确认附件没有与既有听审样本错配或损坏，不能判断漏词、增词、术语或年份是否正确。当前会话没有音频感知接口；没有声称听过，也没有复跑 ASR、读取逐字稿正文或修改 raw/reviewed 文件。既有 ASR 候选仍只是复听线索。
- **状态：** P4 至少三段声学对照及 fresh Desktop 输入/输出数据流和隐私验收仍未完成，P4 **NOT PASSED**。P2/P5/P6 门槛也仍开放；项目整体 **NOT READY FOR RELEASE**。

## 242. 2026-10-12 P6 Windows PE 导入名称分类

- **证据输入与输出：** 使用当前 `uv.lock`（SHA-256 `f4fc838d6f52555ca03ccf378c67e2a988666928904ff14bfab6d4af7c88f31b`）及修正后的 PE 清单（419 行，419/419 RECORD 已验证；SHA-256 `18236b199a2cd5e8d6db98beec04447546e799c9153a46085274c14c2ff570ae`）生成新的 [`windows-pe-import-edges-classified.jsonl`](windows-pe-import-edges-classified.jsonl)，2,654 行、3,198,994 字节，SHA-256 `e026eef783bce270fc26f65e52bed80db6af66d63f4cc13628ac493238d1d5a9`。原 `windows-pe-import-edges.jsonl` 保持不变。
- **分类结果：** 互斥 resolution 为 API-set 前缀名 1,041、显式 Windows system-DLL 名称 641、单一同制品 PE 候选 11、多个合格 inventory 候选造成的歧义 255、未解析到 inventory 706。候选指标有交叠：266 条导入边含同制品候选，255 条含跨制品候选，对应 276 个跨制品目标记录；交叉检查未发现跨包候选，跨制品目标均是同包的锁定 Windows wheel 变体。
- **实现和验证：** [`map_locked_pe_import_edges.py`](../scripts/map_locked_pe_import_edges.py) 对 basename 做大小写不敏感匹配；候选必须绑定锁定 artifact、校验 RECORD 且 PE machine 与 wheel 平台和源 PE 一致。system-DLL 仅依据 29 个显式名称，API-set 仅依据已列前缀。输出创建采用拒绝覆盖。当前锁和清单的独立重建摘要与新 evidence 相同；定向 mapper 回归 **26 passed**，Ruff check 与 format 均通过。没有下载或安装制品。
- **证明边界与 P6 状态：** 分类只根据名字、锁定制品身份和 PE inventory；系统 DLL 名称不证明 loader 实际选中的文件，歧义仅表示 inventory 有多个合格候选，跨制品候选不证明共安装或动态链接，706 个未解析项也不表示依赖缺失。它不证明构建来源、运行时 native loading 或许可证/notice 适用性。根 LICENSE、owner 发行范围/仓库决定、Win32Docs/SDK/WDK 适用性、完整 native provenance/linkage/notices、远端 CI 与干净远端安装仍开放。P6 继续 **NOT PASSED**；P2/P4/P5 与完整当前树安全审查也未完成，整体 **NOT READY FOR RELEASE**。

## 243. 2026-10-12 P2 provider-context 引用闭包与合法 inspection callout 修正

- **实现与发现：** native reader 在同一显式只读 transaction 内枚举 `FWPM_PROVIDER_CONTEXT0`，复制 bounded DTO 与 provider-data/context ID，检查 filter `HAS_PROVIDER_CONTEXT` key 是否唯一存在；空、重复、dangling key 和未支持 union payload 均保持 incomplete。Classify-options 只对有界数组中的 unicast/multicast-broadcast lifetime 项按 `FWP_UINT32` 规范化，其他种类或 malformed 数据 fail closed。独立复核发现此前 decoder 误把 `FWP_ACTION_CALLOUT_INSPECTION` 排除为不能带 provider context；微软 [`Using Classify Options`](https://learn.microsoft.com/en-us/windows/win32/fwp/using-classify-options) 的官方样例明确组合 inspection action、`HAS_PROVIDER_CONTEXT` 与 providerContextKey。reader 已纳入 inspection action，并新增 fixture 覆盖该合法组合。此前对 `PERMIT_IF_CALLOUT_UNREGISTERED` 的 action 限制不适用于 `HAS_PROVIDER_CONTEXT`。
- **接口依据：** [`FWPM_PROVIDER_CONTEXT0`](https://learn.microsoft.com/en-us/windows/win32/api/fwpmtypes/ns-fwpmtypes-fwpm_provider_context0) 定义 provider-context union 与字段；[`FwpmProviderContextCreateEnumHandle0`](https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmprovidercontextcreateenumhandle0) 要求为一致枚举在同一显式 transaction 内创建/使用 enum，且只返回调用者可读的对象；[`FwpmProviderContextEnum0`](https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmprovidercontextenum0) 要求释放返回的数组而非单项；[`FwpmProviderContextGetSecurityInfoByKey0`](https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmprovidercontextgetsecurityinfobykey0) 说明 key 为空时获取的是 container descriptor，故空对象 key 不用 container ACL 冒充对象 ACL。
- **验证：** 锁定 .NET SDK 10.0.401 x64 Release build 为 **0 warnings、0 errors**；native unmanaged fake-API harness **25/25**、Runtime fake-store harness **15/15**；native reader、reader harness、Runtime、Runtime harness 的 `dotnet format whitespace --verify-no-changes --no-restore` 均通过。完整 native build BOM 已重新生成。没有 live BFE/WFP/Firewall/Sandbox API、生产 store/apply/readback/rollback 或 service/CaptureService wiring；没有变更主机策略。
- **仍开放：** 未把各对象 descriptor 与批准的 service ACL policy 比较；对象级 read ACL 仍可能隐藏未枚举对象；IPsec provider-context union variants 未实现；不存在生产 `IWfpPolicyStore` 或 service 接线。P2 继续 **NOT PASSED** 并 fail closed。用户本轮再次提交的三段 P4 WAV 与现有私有 listening pack 身份匹配，但会话没有音频感知接口；未声称听过，P4 声学听审和 fresh Desktop 数据流/隐私验收仍开放。P5 Desktop trace、P6 owner/许可/远端门槛和全工作树安全复核也仍未完成，项目继续 **NOT READY FOR RELEASE**。

## 244. 2026-10-12 Windows Python 3.11.15 当前树全量回归

- **结果：** 在 `.venv-audit-py311` 对当前工作树运行 `python -m pytest -q`，**664 passed、30 skipped、0 failed**，用时 165.99 秒。跳过项包括未配置 native interop server、Windows 当前权限不允许创建 symlink，以及 POSIX FIFO、目录句柄、权限位和其他 POSIX 专属行为；这不是 Linux/macOS 覆盖结果。
- **范围与状态：** 本轮全套涵盖 §242 PE import mapper 和当前 Python 项目代码，但不验证 live WFP/BFE、URL 捕获、P4 声学听审、P5 Desktop invocation 或 P6 远端发布门槛。没有修改 raw/reviewed 转写产物，没有触发 host WFP/Firewall/Sandbox 操作。整体 **NOT READY FOR RELEASE**。

## 245. 2026-10-12 P2 native layer/default-sublayer 与 provider 引用闭包

- **发现：** 独立 WFP reader 复核发现，snapshot 之前只闭合 filter→callout 和 filter→provider-context 引用。filter 的 `layerKey`/非空 `subLayerKey` 以及 filter、sublayer、callout、provider-context 的可选 `providerKey` 没有校验。顶层 reader 一直因 `EnumerationCompletenessUnverified` fail closed，但单个对象可能错误显示 `IsComplete`。Microsoft 文档说明 filter 的 `IID_NULL` sublayer 表示该 layer 的默认 sublayer；实际默认 key 在 `FWPM_LAYER0.defaultSubLayerKey`，不能把空 key 当普通 dangling key，也不能不读 layer 元数据就声称闭包完成。
- **修复：** reader 在同一只读 transaction 内新增分页 layer enumeration，只复制 `layerKey` 和 `defaultSubLayerKey`；验证 filter 的 layer 存在、根据空/非空 sublayer key 解析有效 sublayer 并闭合到枚举列表。检测重复/空 layer、sublayer keys 和未解析引用。对四类拥有者检查 provider key；空指针作为无关联接受，非空空 GUID、重复 provider key 与未由本次枚举返回的 provider 均留下 issue。缺失项记录为“未从此次读取返回”，不推断必然 dangling，因为对象级 READ ACL 可能隐藏目标。
- **接口依据：** Microsoft [`FWPM_FILTER0`](https://learn.microsoft.com/en-us/windows/win32/api/fwpmtypes/ns-fwpmtypes-fwpm_filter0) 与 [`FWPM_LAYER0`](https://learn.microsoft.com/en-us/windows/win32/api/fwpmtypes/ns-fwpmtypes-fwpm_layer0) 定义 null/default sublayer 语义；[`FwpmLayerCreateEnumHandle0`](https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmlayercreateenumhandle0) 和 [`FwpmLayerEnum0`](https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmlayerenum0) 规定同 transaction 一致性、read-ACL 可见性和返回数组释放规则。provider 关联字段见 [`FWPM_SUBLAYER0`](https://learn.microsoft.com/en-us/windows/win32/api/fwpmtypes/ns-fwpmtypes-fwpm_sublayer0)、[`FWPM_CALLOUT0`](https://learn.microsoft.com/en-us/windows/win32/api/fwpmtypes/ns-fwpmtypes-fwpm_callout0)、[`FWPM_PROVIDER_CONTEXT0`](https://learn.microsoft.com/en-us/windows/win32/api/fwpmtypes/ns-fwpmtypes-fwpm_provider_context0) 与 `FWPM_FILTER0`。
- **验证：** pinned .NET SDK 10.0.401 x64 Release build **0 warnings、0 errors**；unmanaged native reader harness **31/31**，Runtime fake-store harness **15/15**；native reader、两个 harness 和 Runtime 的四项 `dotnet format whitespace --verify-no-changes --no-restore` 均通过；完整 .NET build BOM 已重生成。fixture 覆盖 null 默认和显式 sublayer、missing layer/default/explicit target、重复 layer/sublayer/provider、四类 provider refs、null/empty provider pointer 和 layer enumeration 失败清理。
- **边界：** 结果来自离线 fake API；没有 live BFE 检查，也未读取/比较 layer ACL。对象级 read ACL 下的全量可见性、descriptor 与批准策略比较、IPsec context union、生产 `IWfpPolicyStore`、apply/readback/rollback、service/CaptureService wiring、Chromium 进程树隔离与三条成功真实捕获仍开放。没有改动 host WFP/Firewall/Sandbox。没有因 C# reader 修改重跑 §244 Python 全套。P2 继续 **NOT PASSED**，项目 **NOT READY FOR RELEASE**。

## 246. 2026-10-12 全工作树 Deep Scan 未能启动

- **工具结果：** Codex Security Deep Scan discovery 没有启动或加入 worker。工具明确要求父任务提供 managed filesystem permission profile，才能安全启动只读 worker；当前会话没有可设置该 profile 的入口。没有生成新的 Deep Scan 报告，finding 数量未知。
- **覆盖状态：** 这不是“0 findings”或全仓通过。最近的 §234 machine Diff Scan 是 111/111 个生成源码/配置 review items、0 个可报告 finding，但 coverage partial、receipt refs unresolved；§235 是定向文档/测试/fixture/生成证据审查。两者都没有覆盖全部当前工作树，且都早于 §245 新的 native reader 更改。
- **对策：** 在 Codex Security 可提供 managed filesystem profile 的受支持执行上下文中，基于当前未提交工作树启动新的全工作树 Deep Scan，并纳入本轮 WFP reader、NativeMethods 与 fixture。完成前保留“安全结论未知/覆盖不完整”，继续维持 fail-closed 产品状态与 **NOT READY FOR RELEASE**。本节没有把未启动的扫描报告成无发现，也没有再次触发相同失败的启动请求。

## 247. 2026-10-12 冻结工作树完整安全差异扫描

- **扫描身份与覆盖：** Codex Security Diff Scan `c6e0428c-f74d-449b-ad4b-f138af0f0bf4`；基线/HEAD `b166778ee5283591a1b799535b746ba198e38653`；冻结工作树摘要 `codex-security-snapshot/v1:sha256:8d5c56403df51e304838f3ca6ab0eaeb290b262ae8a7a40d4385b36110fa04d3`。扫描请求范围为仓库根目录；112/112 个生成的源码/配置审查项已关闭，coverage 为 **complete**，可报告 finding 为 **0**。
- **审查分组：** Python CLI、配置、ASR/存储、Skill sidecar、CI、依赖及 SPDX 审计工具共 46 项；Windows named-pipe、capture-pipe、WFP plan/runtime/native readback 与相关配置共 66 项。两组独立只读审查均未确认当前可触达的报告级安全缺陷。
- **关键边界：** URL 捕获在产品 CLI 中继续 fail-closed；本机 ASR worker 通过受限 JSON 协议通信，但不是 OS 级沙箱。Windows service、WFP policy/apply/readback、per-lease worker/Chromium 隔离仍未构成生产接线。未部署原型不能证明真实机器上的出口隔离、BFE 权限或完整对象可见性。
- **范围限制与对策：** 本次只审查固定工作树快照的静态差异；没有运行测试、修改代码、联网、访问 BFE/WFP、操作 Sandbox 或修改 host Firewall。实际主机 ACL、环境覆写、模型提供方保留行为及远端 CI 仍需独立验收。继续保持 P2/P4/P5/P6 发布门槛；尤其 P4 附件身份匹配不等于音频听审，当前会话没有直接音频感知能力，不能据此声称声学验收通过。项目整体仍 **NOT READY FOR RELEASE**。

## 248. 2026-10-12 P2 WFP layer security-descriptor readback

- **实现：** 根据 Microsoft [`FwpmLayerGetSecurityInfoByKey0`](https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmlayergetsecurityinfobykey0) API，在只读 BFE transaction 中为每个枚举到的 layer 请求 owner/group/DACL，并由同一受限解析器完成 self-relative descriptor 长度限制、规范化、hash 和 WFP 分配释放。`LayerSnapshot` 现保存 descriptor 与 issues；缺失、获取失败或非规范 descriptor 使 layer 不完整。正常解析仍会留下 `SecurityDescriptorPolicyUnverified`，不把“已读取”误当成“符合预期 ACL”。
- **离线验证：** 固定 .NET SDK 10.0.401 x64 Release harness build **0 warnings、0 errors**；native unmanaged reader fixture **32/32**；reader 与 fixture harness 的 whitespace format 检查通过；`scripts/generate_dotnet_build_bom.py` 已成功重建完整 .NET build BOM。新增用例覆盖 layer API 返回失败且仍交付由 WFP 拥有的 descriptor 时，reader 保持 incomplete 并释放内存。fixture 未连接 BFE。
- **缺口与安全边界：** 没有与批准的 service ACL policy 比较；对象级 READ ACL 仍可能隐藏 enumeration rows；IPsec provider-context union variants、具体 `IWfpPolicyStore`、生产 WFP apply/readback/rollback、service/CaptureService wiring、per-lease Chromium 隔离和 live BFE/Sandbox 验收仍开放。没有改动 host WFP/Firewall/Sandbox。§247 Diff Scan 在该实现之前冻结，因此本节代码尚未纳入完整安全扫描；下一轮当前树扫描需包含 `NativeMethods.txt`、reader、decoder、snapshot model 和 fixture。P2 **NOT PASSED**，项目仍 **NOT READY FOR RELEASE**。

## 249. 2026-10-12 冻结差异安全扫描封存与 P4 音频边界

- **扫描身份与范围：** Codex Security Diff Scan `d8950f81-800f-4f3d-8b63-550c6dbc8161`；基线/HEAD `b166778ee5283591a1b799535b746ba198e38653`；快照摘要 `codex-security-snapshot/v1:sha256:6c79d920544c2b2acdc4f003f6fb1e9863af18bdea2e8f874d1573ffbe4bbb06`。生成的安全相关源码/配置审阅清单 **112/112** 完成；总变更路径为 253，整体 coverage 仍为 **partial**，因为清单外的文件没有逐一审查。
- **发现：** 5 项均为低严重度、需要本地操作者运行相关审计工具的发现：① `hash_locked_license_candidates.py` 在某个错误分支中未转义归档成员名，可能控制终端显示；② `map_locked_pe_import_edges.py` 在输出上限检查前构造高扇出的完整边图，可能放大本地 CPU/内存；③ `inventory_locked_pe_imports.py` 限制 RECORD 字节数但未限制行数，可能膨胀内存索引；④ `check_spdx_schema.py` 会保留并排序全部校验错误，可能放大本地资源消耗；⑤ .NET BOM 与 SPDX 生成器可能跟随仓库输出路径上的符号链接并覆盖链接目标。
- **对策：** 所有终端诊断先转义控制字符；PE mapper 在构造中间对象前实施累计边数/工作预算并有界流式输出；RECORD 行数上限与 ZIP 成员数量绑定；SPDX 校验设置错误数及 package 数量预算并提前终止；两个证据生成器拒绝 symlink/reparse point 和仓库外目标，使用安全的 no-follow 临时文件与原子替换。此轮只记录对策，未改动产品/审计工具代码，也未运行测试。
- **限制与发布状态：** 这是冻结快照上的静态源代码/配置审查，不是全仓逐行审计或动态验证；没有运行测试/利用样例、live BFE/WFP、宿主 Firewall/Sandbox、浏览器隔离或远端 CI。P2/P4/P5/P6 仍开放，项目 **NOT READY FOR RELEASE**。
- **P4 音频：** 用户提交的 `focus_01m11.wav`、`focus_05m40.wav`、`focus_08m41.wav` 文件在私有听审包中可访问，但本会话没有音频感知工具，没有声学听辨结论。既有 ASR 交叉检查中的术语候选只是复听定位，不能证明对错；没有修改 raw/reviewed 逐字稿。P4 至少三段声学核对和 08:50 后年份争议复听仍未通过。

## 250. 2026-10-12 安全审计工具复核与两项资源/路径修复

- **AUD-147（低危资源消耗，CWE-400）：** `inventory_locked_pe_imports.py` 原先在 `csv.reader` 已把整行拆成 Python 列表后才检查字段数；一个字节受限但包含大量逗号的 RECORD 行仍可造成大规模列表分配。现新增 `_check_record_csv_bounds`，先逐字符扫描并在超过 3 列或 RECORD 行数预算时立即拒绝，再运行 CSV parser。新增超宽行回归用例，但本轮未运行 pytest。
- **AUD-148（低危路径重定向，CWE-59）：** `safe_output.py` 原先在最终路径检查和 `os.replace` 之间存在父目录 junction/symlink 切换窗口，可能把生成文件重定向到另一目录。现 POSIX 使用 `O_NOFOLLOW` 目录句柄与相对目录 `os.replace`；Windows 逐级以 `FILE_FLAG_OPEN_REPARSE_POINT` 打开目录并拒绝 delete sharing，在文件生成和替换期间固定父目录链。新增 POSIX 确定性父目录切换回归用例；本轮未运行 pytest，Windows symlink 权限和 handle 路径也未做动态验证。
- **静态检查：** Ruff format/check 和 Python `py_compile` 针对改动文件执行且无报告错误。没有运行测试、打开 BFE/WFP、操作 Sandbox/Firewall 或改动音视频/转写产物。代码级缓解尚需在受支持的 Windows/Linux CI 运行回归用例并审阅结果。
- **P4 附件：** 本轮再次收到三段约 18 秒 WAV。当前会话没有音频感知接口；附件身份核对不等于听辨，不能据此确认漏词、增词或术语。raw/reviewed 逐字稿没有修改，三段听审与 `focus_08m59.wav` 年份争议复听仍开放。
- **整体状态：** P2 生产隔离、P4 声学及 Desktop 数据流/隐私验收、P5 fresh Desktop trace、P6 owner/许可/远端发布门槛和完整当前树安全审查均未关闭；项目继续 **NOT READY FOR RELEASE**。

## 251. 2026-10-12 P2 native reader authentication and exact paging cap

- **本地代码修复：** `WindowsWfpApi.OpenEngine` now supplies `RPC_C_AUTHN_WINNT` (10) to `FwpmEngineOpen0`; its injectable boundary lets the offline harness assert the argument without opening BFE. The object cap no longer rejects a full page merely because its count lands exactly on `MaxObjects`. Since requests remain bounded to `PageSize` (64), the reader performs one sentinel query after a full page at the cap: zero rows completes the enumeration, while any row exceeds the cap and is rejected before decoding/appending.
- **回归与执行状态：** Added two fixture checks: the adapter passes authentication service 10, and paging accepts exactly `MaxObjects`, completes on an empty sentinel, and rejects one extra object. Using the pinned .NET SDK 10.0.401, locked restore completed, x64 Release build succeeded with **0 warnings / 0 errors**, and the unmanaged offline reader harness passed **34/34**. The API-open regression injects a fake call boundary; no test called BFE.
- **隔离边界与剩余门槛：** The reader continues to report incomplete enumeration visibility, and Runtime continues to reject an incomplete snapshot before mutation. No production store, WFP write API, service wiring, or activation path was added. Administrator-installed service and identity authorization, live BFE/WFP readback, object-ACL enumeration coverage, approved ACL comparison, unsupported IPsec context decoding, production apply/readback/rollback, per-lease worker/Chromium isolation, disposable Sandbox acceptance, and authorized successful capture evidence remain external gates. This work did not access BFE/WFP, host Firewall, Sandbox, service state, or media/capture inputs. P2 remains **OPEN / NOT PASSED** and the project **NOT READY FOR RELEASE**.

## 252. 2026-10-12 审计证据写入器拒绝链接父路径

- **共享边界：** 新增 `scripts/safe_output.py` 的安全文本 create-only 写入接口，并将 PE import inventory、locked artifact inventory、NumPy native inventory、wheel metadata audit、license candidate hashing、PE import edge mapper 与 batched artifact inventory 的手工证据写入迁移到固定父目录、拒绝 symlink/reparse point 的 helper。原子替换写入继续允许更新普通文件；仅支持新建的输出仍拒绝覆盖既有叶文件。Metadata audit 与 hash report 仍要求目标父目录预先存在；batch 输出目录也仍必须预先存在。Hash report 保留排他创建语义；mapper 与 batch 文件保留旧有的 `0666 & umask` POSIX 创建模式，hash report 保留 `0600` 模式。
- **回归与检查：** 全迁移测试集曾通过 **47 passed / 15 skipped**。mapper mode 调整后又运行 helper、evidence-writer 与 PE import 针对测试：**36 passed / 13 skipped**。Ruff check、Ruff format check 与 Python `py_compile` 对改动文件通过。跳过项来自当前 Windows 用户缺少创建 symlink 的权限（`WinError 1314`）以及 POSIX `dir_fd` 父目录切换测试不适用于该主机；模拟 reparse-point 检查仍执行。
- **Windows 验证限制：** 本轮在 Windows 主机运行了普通路径写入回归，但没有通过真实 junction/symlink 进行动态重定向测试，也没有验证对抗性目录交换竞态；这些行为仍需具备链接权限的 Windows CI 覆盖。未访问 BFE/WFP、host Firewall、Sandbox，未触碰 transcript 或媒体内容。

## 253. 2026-10-12 reviewed sidecar 句末标点门槛

- **发现：** `write_reviewed_transcript_markdown` 曾将逗号、顿号、冒号和分号也视为“中文句末标点”。因此，只有逗号或列举符号而没有一句真正结束标记的段落，可以通过格式门槛；这不足以落实 Skill 要求的逐段句末标点。
- **修复：** 按段落单独要求至少出现 `。`、`！`、`？` 或 `…`；逗号、顿号、冒号等仍可用来切分 160 字无标点连续长度检查，但不再满足句末标点门槛。新增仅含逗号/冒号或顿号/分号段落的回归拒绝用例。
- **验证与边界：** `tests/unit/test_markdown.py` 定向回归 **23 passed、2 skipped**；全量回归由 §254 记录。此校验只判断结束符是否存在，不判断标点是否自然、断句是否正确，也不能证明模型真正审校了正文。
- **项目状态：** P2 生产隔离、P4 人工声学听审与 fresh Desktop 数据流/隐私验收、P5 fresh Desktop trace、P6 所有者/许可/远端门槛和完整当前树安全审查仍开放；整体 **NOT READY FOR RELEASE**。附件身份核验和 ASR 交叉候选均不等于人工听审。

## 254. 2026-10-12 当前树 Python 全量回归

- **结果：** Windows Python 3.11.15 当前树全套 `pytest -q` 为 **679 passed、46 skipped、0 failed**（259.78 秒）。该套件包含 §250 RECORD parser/output-path 测试、§252 证据写入器 parent-link/contract 测试和 §253 reviewed-sidecar 句末标点回归。
- **跳过项：** 包括未配置 native interop server（2）、当前 Windows 账户缺少创建 symlink/junction 权限、POSIX FIFO/`dir_fd`/权限位专属行为和一个非 Windows 主机检查。这些跳过不证明 Windows 对抗性 reparse-point 竞态，也不证明 Linux/macOS 行为通过。
- **静态检查：** 全仓 Ruff check 通过；scripts、Skill Python 源码与 tests 的 Ruff format check 为 **87 files already formatted**；`git diff --check` 通过（只有 Git 的 LF→CRLF 提示）。本轮没有运行真实 WFP/BFE、Sandbox、host Firewall、URL capture、远端 CI 或音频听辨。
- **结论：** Python 离线回归通过不关闭产品环境验收。P2 live isolation/service wiring、P4 声学听审与 Desktop 数据流隐私、P5 Desktop trace、P6 owner/license/remote gates 及完整当前工作树安全扫描仍开放；整体 **NOT READY FOR RELEASE**。

## 255. 2026-10-12 .NET BOM 刷新与 clean-install smoke 校正

- **P6 本地 build identity：** 使用仓库锁定 .NET SDK 10.0.401 运行 BOM 生成器的常规 pinned build 路径，刷新 `docs/dotnet-windows-build-bom.json`。清单保留 4 条精确 NuGet 包记录，并覆盖 wfp-policy-plan、WfpPolicy.Core 与 native reader 的源输入、生成源码及构建输出；按各 MSBuild 项目根目录解析后合计 **233 项**，核验为 **0 项缺失、0 项大小/摘要不匹配**。`--skip-build` 再生成后，文件 SHA-256 保持 `D18946CD54E144A0E45D80FD782A32D4E1C331D25B5B9D2D6D286483437C5223`。`tests/unit/test_dotnet_build_bom.py` 定向结果 **10 passed、1 skipped**；跳过项是当前 Windows 账户缺少 symlink privilege。此证据只刷新本地构建身份，不证明远端可复现、运行时 SBOM、许可适用性或发布批准。
- **P5 clean-install smoke 假设修复：** 原脚本把 URL dry-run 的期望固定为 `ready/0`，与产品当前明确的无 WFP broker 时 `needs_attention/2`、`BROWSER_ISOLATION_UNAVAILABLE` fail-closed 行为冲突。脚本现验证输入 URL 语法有效、捕获状态明确 unavailable、错误码正确及路径权限可写，并按 CLI 契约接受退出码 2。`tests/unit/test_skill_install.py` **13 passed**；随后仓库外临时副本的 locked no-dev 安装、导入来源、`--version`、dry-run、`doctor --json` 及不创建 app-data/output 目录检查全部通过。临时目录由脚本上下文清理。
- **P4 附件处理：** 用户本轮提交的三段 18 秒 WAV 位于既有私有听审包，哈希与 manifest 一致。当前会话没有音频感知接口；没有把文件身份或既有 ASR 候选当作听辨结论，没有修改 raw/reviewed 逐字稿。P4 声学核对和 fresh Desktop 数据流/隐私验收仍开放。
- **边界与状态：** 本轮没有访问 BFE/WFP、Sandbox、host Firewall，没有新下载媒体或触碰转写正文，也没有运行远端 CI。P2 生产隔离、P4 声学/Desktop 验收、P5 fresh Desktop trace、P6 owner/license/remote gates 及当前树完整安全扫描仍未关闭；项目继续 **NOT READY FOR RELEASE**。


## 256. 2026-10-12 当前源码/配置差异审核与 BOM 锁哈希复核

> **历史快照说明：** 本节冻结快照中的 NuGet lock-contentHash mitigation 结论已由 §257 的修复和真实签名包验证取代。以下只描述 §256 当时的发现和证据，不代表当前实现状态。

- **扫描身份与范围：** Codex Security Diff Scan `612a66d5-68a3-4e1c-9bf9-521634f6cbcc`；基线/HEAD `b166778ee5283591a1b799535b746ba198e38653`；冻结摘要 `codex-security-snapshot/v1:sha256:f779936469719881e3d969fdfa833263df3bf3335e94e540b1bdc15b238a8c2b`。生成的 113 条源码/配置审阅项全部完成：native 66、Python 25、脚本 17、Skill 配置/schema 3、CI 1、工具配置 1。扫描目标共 257 个变更文件，其他变更文件未逐项审查，故总体 coverage 为 **partial**。
- **Finding 状态（Low / CWE-345）：** 冻结版本只将实际 `.nupkg` SHA-512 与同一缓存中的 sidecar 比较，并将缓存 `.nupkg.metadata` 的 `contentHash` 与 `packages.lock.json` 比较；没有从归档字节独立计算 NuGet `contentHash`。能写入该本地缓存的攻击者可以协调替换归档、sidecar 和 metadata，使缓存内部记录一致而未证明归档内容与 lock 值对应。影响限于本机 BOM 来源证明完整性；未发现远程触发或直接代码执行路径。签名验证证明签名状态，不替代锁定内容摘要绑定。该静态 finding 仍成立，正确 mitigation 尚未完成。
- **当时的错误摘要口径与无效修复（§256 快照，已由 §257 取代）：** 在 §256 冻结版本中，完整 `.nupkg` raw SHA-512 曾被错误地直接与 lock `contentHash` 比较。这与 §231 记录的 NuGet 语义冲突：签名归档的原始 SHA-512（与 `.nupkg.sha512` sidecar 比较的值）包含签名归档字节；lock `contentHash` 使用 NuGet canonical package content hash。§231 的四个有效签名包原始 SHA-512 与 lock hash 不同，但 metadata `contentHash` 与 lock hash相同。因此该旧条件会拒绝合法签名包。§256 当时的单元测试也没有调用真实 NuGet API；§257 已加入实际 canonical hash 计算、签名包接受/错误摘要拒绝用例和真实包验证，见本报告 §257。
- **当时的验证限制（历史记录）：** §256 审核回合所在的执行环境没有可用 .NET SDK，故当时未能计算归档 canonical 摘要或验证签名包回归；没有改生成器或运行测试。这个限制不代表当前环境。§257 后续使用锁定 SDK 10.0.401 完成正确摘要实现与真实包验证；§273 又在当前工作树进行了新鲜复验。
- **审查限制：** native、Python、脚本分区静态审阅未发现其他当前产品可达的报告级候选。扫描期间工作树发生变化；finalizer 未能在 canonical scan 目录找到保存在临时位置的分区回执，因此跳过 receipt references 并将 surfaces 标为 `needs_follow_up`。113/113 是 worklist 进度，不代表封存器验证了分区回执；其余变更文档、测试、fixture 与生成证据仍未逐项审核。细节见 [SECURITY_REVIEW_FOLLOWUP_2026-10-12.md](SECURITY_REVIEW_FOLLOWUP_2026-10-12.md)。
- **P4 与发布状态：** 用户上传的三段 WAV 与私有听审包清单一致。听审包已有 balanced/medium 与 SenseVoice 本地交叉识别记录，另一个 Distil Whisper 对中文输出不适用；这些机器结果只用于标记复听候选。当前模型接口不能听辨，未形成声学结论，也未改逐字稿。P2 生产隔离、P4 声学/Desktop、P5 Desktop trace、P6 owner/license/remote gates 仍开放；项目继续 **NOT READY FOR RELEASE**。

## 263. 2026-10-13 两项安全 finding 的本地缓解与验证

- **CWE-400 锁文件读取：** 在 `scripts/verify_spdx_evidence.py` 增加共享有界字节读取器，复用 16 MiB 锁文件上限、常规文件/路径身份检查、`fstat` 预检及最多 `limit + 1` 字节的读取复核。`inventory_locked_artifact_members.py`、`inventory_numpy_native_members.py` 和 `inventory_locked_pe_imports.py` 均先经该边界读取，再计算摘要或解析 TOML。共享 `_lock_identities` 入口也保护批处理清单与许可候选哈希调用方。
- **CWE-400 验证：** `tests/unit/test_bounded_lock_readers.py` 覆盖三种 reader 的精确上限接受、稀疏超限文件在字节读取及 TOML 解析前拒绝，以及 fstat 后增长时的 `limit + 1` 复核。含三个 reader 及共享调用方的定向回归为 **46 passed、10 skipped**；跳过项为当前 Windows 账户缺少创建 symlink/junction 权限。Ruff check/format、`py_compile` 和 `git diff --check` 通过。该结果说明当前工作树的本地缓解通过定向验证，不会改写 §262 冻结扫描记录，也尚未由新扫描复审。
- **CWE-269 Sandbox guest 边界：** 在没有可信 broker/guest attestation 时，将 `ChromiumAsUserTokenSmoke.ps1` 和 `GrantInteractiveDesktopAccess.ps1` 收缩为入口立即失败的 stub，删除账号创建、文件复制、ACL 修改、进程启动、结果写入及清理实现。参数仍可绑定，旧调用会得到明确的禁用错误。Sandbox README 已移除旧 `wsb exec` 操作流程，并说明 SYSTEM SID、session 字段和共享 JSON RunToken 不是 guest 证明。`tests/unit/test_sandbox_cleanup_ownership.py` **8 passed**；两个脚本的 PowerShell AST 解析通过，Ruff check 通过。此处采用 fail-closed 缓解；若要恢复诊断功能，需先实现并验证 host controller 的受保护 guest-bound attestation。
- **扫描和发布边界：** §262 封存扫描覆盖 116 个 worklist 项、对应 265 个变化路径，coverage 为 partial。它不是当前工作树的完整安全审查，新补丁尚未进入新的扫描。P2 生产 WFP/service/lease 隔离及三条成功授权捕获、P4 声学听审和 fresh Desktop 隐私数据流、P5 Desktop trace、P6 owner/license/remote gates 均未关闭；当前音频输入也不能由本会话模型听辨。项目继续 **NOT READY FOR RELEASE**。

## 264. 2026-10-13 冻结工作树差异安全审查与剩余项目问题

- **扫描结论：** Codex Security Diff Scan `ab9dc137-f377-4b64-814c-d70da142b016` 已封存，可在 Codex Security 工作台按 scan ID 查看正式报告。静态差异复核记录 **0 个可报告安全 finding**；工作台进度为 **116/116** 个源码/配置 review items，扫描 coverage 为 **partial**。这不是全仓安全通过结论。
- **快照和范围限制：** 基线/HEAD `b166778ee5283591a1b799535b746ba198e38653`，冻结快照摘要 `codex-security-snapshot/v1:sha256:570af32f9fa92c17b2430f8d2608d1f0488602e3097c9efa880be75bf610447a`。变更清单共 266 条路径；116 条生成源码/配置 worklist 已复核，另 150 条（主要为文档、测试、fixture 与生成证据）没有逐行审查。安全工作台还警告扫描运行期间工作树发生变化，结果仅适用于冻结快照；扫描没有运行测试/构建、live WFP/BFE/Sandbox、生产捕获或远端 CI。
- **复核面：** Windows native/WFP 与 sandbox、Python capture IPC/转写/输出、脚本/CI/schema/项目配置分组均未发现当前可报告的安全问题。此前 §263 的有界 lock reader 和 Sandbox guest-mutating stub 缓解属于本轮快照中的代码；该结论不替代未覆盖文件或运行环境验证。
- **仍存在的功能/验收问题与对策：**
  1. CLI 未注入 `CaptureServiceClient`，因此真实 URL capture 当前不可用。继续保持 fail-closed；只有在认证 capture service、隔离/broker 路径和权限边界实现后，才接入 CLI 并做端到端授权测试。
  2. `StageChromiumForInteractiveUser.ps1` 是具有副作用的 SYSTEM 手动辅助脚本；本次没有找到产品或当前 WSB 调用者。保持手动禁用/受控状态；恢复自动化前，先增加并验证 host 到 guest 的可信绑定 attestation，或删除该入口。
  3. 150 条差异路径未纳入逐行 worklist。对剩余文档、测试、fixture、生成证据及本次冻结后新增改动做分区审查，并生成新快照；不能沿用本次 0 finding 作为证明。
  4. P2 生产 WFP/service/lease 隔离与三条真实授权捕获、P4 声学听审和 fresh Desktop 数据流/隐私验收、P5 fresh Desktop trace、P6 owner/license/remote gates 仍未关闭。按各门槛补齐真实环境证据前，项目维持 **NOT READY FOR RELEASE**。
- **P4 音频边界：** 用户提交的 `focus_01m11.wav`、`focus_05m40.wav`、`focus_08m41.wav` 已与既有听审包身份核对一致；当前会话模型明确不支持音频输入，故没有听辨结论，也没有把 ASR 候选当成人工确认。请由具备音频感知能力的审阅者记录时间点和术语差异；另需覆盖既有 `08:50–09:08` 的 `2016/2026` 冲突片段。
- **报告解释：** “0 个可报告安全 finding”仅是上述冻结快照、静态方法和 116 条 worklist 范围内的结论。对未审路径、机器配置、生产服务、实际音频内容、模型提供方数据保留策略和发布批准均不作推断。

## 265. 2026-10-13 当前树回归与验收状态续核

- **Windows 当前树回归：** Python 3.11.15 `pytest -q` 为 **693 passed、46 skipped、0 failed**（258.19 秒）。跳过项包括两个未配置 native interop 路径、当前 Windows 权限下无法创建的 symlink/junction 用例，以及 POSIX-only 场景；不能据此声称 Windows reparse 竞态或 Linux/macOS 验收通过。
- **静态/仓库检查：** Ruff check 与 format、`uv lock --project skills/douyin-transcript --check`、canonical/repo-scoped 两份 Agent Skills validation、Git 可见敏感文件扫描及 `git diff --check` 通过。`skills-ref` 不在锁定环境中；改用环境里已有的 `agentskills` validator 后，两份 Skill 均验证有效。
- **运行状态：** 只读 `doctor --json` 报告本地 ASR 和浏览器依赖已就绪，但 `browser_isolation=unavailable`、`douyin_urls=setup_required`；认证 capture broker 与 policy validator 未集成。普通 URL capture 继续 fail closed，本轮未尝试绕过或捕获。
- **安全复审边界：** §264 Diff Scan 已封存，0 个可报告 finding 仅覆盖 116/116 个生成源码/配置 review items。总体 coverage 为 partial：266 个变化路径中 150 个未逐行审查，且工作台报告扫描期间工作树有变化。扫描未执行测试、构建、live WFP/BFE/Sandbox、生产 capture 或远端 CI；不能当作完整当前树安全 clearance。
- **Native 与 P4 证据：** 当前主机没有 .NET SDK，故本轮未能重新构建 Native WFP reader 或运行其 fixture。用户再次提供的三段 WAV 文件存在，并与既有私有听审包记录相符；本会话模型不支持音频输入，因此没有声学判断或转写正文修改。另一个 `08:50–09:08` 年份争议需要对应片段 `focus_08m59.wav`，不在本轮这三段附件中。
- **未关闭门槛：** P2 生产 WFP/service/per-lease 隔离、rollback 与三条授权成功捕获仍开放；P4 实际音频听审和 fresh Desktop 隐私/数据流验收、P5 fresh Desktop Skill invocation trace，以及 P6 所有者许可证/发行范围/仓库及远端授权、远端 CI/clean install 仍未完成。项目继续 **NOT READY FOR RELEASE**；执行 §263 本地缓解和当前 Python/静态检查不替代这些外部环境证据。

## 266. 2026-10-13 WFP classify-options 有界枚举解码

- **发现与范围：** Native reader 原本只归一化 `FWPM_CLASSIFY_OPTIONS_CONTEXT` 的单播和多播/广播 lifetime 标量；微软结构文档还定义了 multicast-state 与 loose-source-mapping 两类 `FWP_UINT32` 枚举值。由于它们有有限且公开的取值，本轮增加这两类的解析，不扩展到复杂 secure-socket/IPsec union。
- **实现与 fail-closed：** `NativeObjectDecoder` 现在接受 multicast-state 的 `0/1/2` 与 loose-source-mapping 的 `0/1`，要求值 tag 为 `FWP_UINT32`；错误 tag、越界枚举、重复项、未知类型和其余尚未归一化选项仍生成 issue，使快照保持 incomplete。依据微软 [`FWPM_CLASSIFY_OPTION0`](https://learn.microsoft.com/en-us/windows/win32/api/fwpmtypes/ns-fwpmtypes-fwpm_classify_option0) 中公开的 allowed values 和 [`FWP_CLASSIFY_OPTION_TYPE`](https://learn.microsoft.com/en-us/windows/win32/api/fwptypes/ne-fwptypes-fwp_classify_option_type)。
- **验证：** 仓库锁定 .NET SDK 10.0.401 在 task-local 目录可用；native reader 与 harness locked restore 成功，x64 Release build **0 warnings / 0 errors**，unmanaged fixture harness **35/35**，reader 和 harness `dotnet format whitespace --verify-no-changes --no-restore` 均通过。完整 .NET build BOM 已重新生成；`tests/unit/test_dotnet_build_bom.py` 为 **14 passed、1 skipped**（当前 Windows 账户无法创建 symlink）。
- **限制与后续：** 测试都走 unmanaged fake API，没有打开 BFE/WFP、Sandbox 或 host Firewall。reader 仍因服务 ACL policy 未批准、枚举可见性无法证明及其他未支持 union 等原因报告 incomplete，Runtime adapter 仍拒绝不完整投影，CaptureService 仍无生产 store 接线；P2 没有通过。P2 service/WFP/rollback/live isolation、P4 听审/Desktop、P5 Desktop trace、P6 owner/license/remote gates 和完整当前树安全审查仍开放；项目 **NOT READY FOR RELEASE**。

## 267. 2026-10-13 冻结差异安全复核、P6 证据对策与音频附件边界

- **安全复核：** Codex Security Diff Scan `3e601534-a09f-483a-8f4f-c908dbbd725c` 已封存。冻结摘要为 `codex-security-snapshot/v1:sha256:926546808209fbb8368e6e7c7473db4d42359795d09b6728d909068febca2633`，基线/HEAD 为 `b166778ee5283591a1b799535b746ba198e38653`。116/116 个源码/配置 worklist 项完成静态复核，未发现可报告安全漏洞；覆盖仍为 partial，266 个变化路径中 150 个没有逐行审查。扫描期间工作树变化，结果仅适用于冻结快照。没有运行测试、构建、利用载荷、live BFE/WFP、生产捕获、host Firewall/Sandbox 或远端 CI。
- **安全对策：** 记录两项 P6 证据质量改进：CI 应把 SPDX SBOM 与当前锁定依赖/许可证证据重建结果比对；CI/release 应把 .NET build BOM 里的输出路径、大小和摘要绑定到当前锁定工具链构建。当前证据未发现 SBOM 或 build-output 摘要已经失配；这是防漂移措施，不是已确认漏洞。另记录 ASR worker 与 CLI 同身份、继承环境变量且不是 OS sandbox 的纵深防御边界。具体验收建议见 [SECURITY_REVIEW_REPORT_2026-10-13.md](SECURITY_REVIEW_REPORT_2026-10-13.md)。
- **P4 附件：** 用户本轮提供的 `focus_01m11.wav`、`focus_05m40.wav`、`focus_08m41.wav` 可访问并与私有听审包身份记录匹配。本会话不能听辨音频；文件身份不是声学结论，没有声称核对漏词/增词/术语，也没有修改 raw/reviewed 逐字稿。`08:50–09:08` 年份争议需另听 `focus_08m59.wav`。
- **未关闭门槛：** P2 生产 WFP/service/per-lease 隔离和三条授权成功捕获、P4 人工声学及 fresh Desktop 数据流/隐私验收、P5 fresh Desktop trace、P6 owner/license/remote gates 仍未完成。新报告和状态同步文档是在扫描快照之后编辑的，不属于该扫描覆盖；项目继续 **NOT READY FOR RELEASE**。

## 268. 2026-10-13 P6 SBOM freshness 与 .NET build-output identity CI 缓解

- **SPDX freshness：** 新增 `scripts/check_spdx_sbom_freshness.py`，以当前 `uv.lock`、许可证证据、生成器语义和已提交 SPDX 的 creation timestamp 在内存重建预期文档，严格比较全部 package、license 声明、relationships、namespace 和序列化字节；锁/证据关联不一致、重复 JSON key、畸形时间戳或生成物漂移会 fail closed。该 CI 检查不下载制品，也不重新哈希 artifact cache 字节；完整成员字节验证仍由 `verify_spdx_evidence.py` 在完整离线 cache 可用时单独执行。
- **.NET BOM 输出身份：** 新增 `scripts/check_dotnet_build_bom_outputs.py`，验证主构建和两个 related build 的输出清单结构，并逐项比较 `path`、`sizeBytes`、`sha256`；相对路径越界、坏摘要、重复或漏记输出均拒绝。CI 在 pinned build BOM 生成后调用此比较器，避免只检查 related build outputs 非空。
- **验证：** 当前锁/许可证证据重建匹配 **121 个 SPDX package records**；当前已提交 .NET BOM 的三组自身输出身份检查通过，共 **41 条记录**。新增两个 checker 的针对性回归 **19 passed**（91.22 秒）；Ruff check 和 format check 通过。没有在本轮重新执行 pinned .NET builds，因此输出对照的真实构建侧将由 Windows CI step 验收；没有运行完整 Python 测试套件或远端 GitHub Actions。
- **范围边界：** §267 安全扫描是旧冻结快照，本节代码和 workflow 修改没有进入该快照。两个证据改进已写入本地 CI，但没有远端 CI 结果、P6 owner/license/repository decision 或 clean remote install。P2 生产隔离、P4 人工音频听审/Desktop 隐私、P5 fresh Desktop trace 和 P6 远端发布门槛仍开放；项目继续 **NOT READY FOR RELEASE**。

## 269. 2026-10-13 当前差异安全复核、低危报告注入问题与项目验收续核

- **扫描身份与覆盖：** Codex Security Diff Scan `c7c4b264-8b26-456c-9964-a5c3f1aa8812` 已封存；冻结摘要 `codex-security-snapshot/v1:sha256:c34fbf2bd13c8629bc332871443519d1a0ed200ebf7a35a4c88ad41266981f9c`，目标 `b166778ee5283591a1b799535b746ba198e38653`。271 个变更路径中，118 个 worklist 项完成复核，另 153 个未逐行审查，coverage 为 partial。
- **发现与风险（冻结快照时）：** 1 项低严重度、高置信度 finding（CWE-116，`improper-output-neutralization.markdown-cell`）：[scripts/inventory_locked_artifact_members.py](../scripts/inventory_locked_artifact_members.py#L400) 将来自 `uv.lock` 的 URL 写入 Markdown 表格前未转义 `CR`。离线合成输入可让生成报告出现额外行/伪造标题，影响本地审计报告完整性和可读性；未观察到代码执行或路径越界，下游渲染影响未验证。PoC 不需要网络。该快照之后已在 §270 缓解。
- **整改对策：** 输入 URL 时拒绝 ASCII 控制字符；Markdown 表格 cell 使用专门编码器处理 CR/LF、反斜线、竖线和 HTML 特殊字符；添加控制字符与 Markdown 注入回归用例，并执行离线端到端负向测试。完成修复后需做新的冻结扫描。另将 `check_dotnet_build_bom_outputs.py` 对 `.` 路径段的归一化行为列为低优先级硬化建议；当前仅做字符串清单比较，没有文件访问行为，未认定为漏洞。
- **扫描分区结论：** Python 产品 28 项、Windows native 67 项、CI/脚本 23 项均完成 worklist 复核，除上述一项外未发现其他报告级候选。扫描报告仅覆盖生成清单，不能外推到其余 153 个路径或全仓；本报告和文档状态同步是在冻结快照后进行的。
- **回归：** Windows Python 3.11 当前全套 **712 passed、46 skipped、0 failed**（260.07 秒）；Ruff check/format、SPDX freshness（121 package records）、`git diff --check` 通过。Dotnet build-output comparator 对已有清单的自比较覆盖 41 条记录；本机 PATH 无 .NET SDK，因此本轮没有执行 fresh pinned build。
- **P4 音频边界：** 三个 WAV 仅有机器交叉检查提供的复听候选：01:11 附近术语、05:40 附近 bid/出价术语；08:41 片段到 08:50 为止，不能判定 08:50–09:08 的 2016/2026 年份差异。当前会话没有音频感知能力，未产出人工听审结论、未修改 raw/reviewed 逐字稿；年份争议还需 `focus_08m59.wav`。
- **剩余门槛：** P2 生产 WFP/service/per-lease 隔离、回滚和授权捕获；P4 声学听审及 fresh Desktop 数据流/隐私验收；P5 fresh Desktop trace；P6 owner/license/远端 CI/clean install 均仍开放。项目继续 **NOT READY FOR RELEASE**。详细发现与证据见 [安全审核报告](SECURITY_REVIEW_REPORT_2026-10-13.md)。

## 270. 2026-10-13 当前差异安全复核与 Markdown finding 缓解

- **扫描身份与覆盖：** Codex Security Diff Scan `c5cbf587-9810-463b-a7e0-e9af6f7d6a00` 已封存，目标 HEAD `b166778ee5283591a1b799535b746ba198e38653`，快照摘要 `codex-security-snapshot/v1:sha256:621e8f1c096142cfbf0f7891b2b8bdea98da23539562f138a18f41f72688b8d5`。118/118 个 worklist 项完成复核：Python 28、Windows native 67、CI/脚本 23；当前 0 个报告级 finding。271 个变化路径中 153 个未逐行审查，coverage 仍为 partial。
- **修复与回归：** lock URL 解析拒绝 Unicode `Cc` 控制字符；Markdown cell 对控制字符输出十进制 HTML 实体。新增测试覆盖 C0/C1、lock URL 拒绝及真实 Markdown renderer 的行列边界。全量 Windows Python 3.11.15 **723 passed、46 skipped、0 failed**（350.39 秒）；测试文件格式化后定向复测 **13 passed、2 skipped**。Ruff check 与 format check 通过。
- **P4 附件：** 本轮再次确认三段 WAV 位于私有听审包；当前模型会话没有直接音频感知接口，因此不声称已听审，也没有修改 raw/reviewed 逐字稿。ASR 结果只能作为复听线索；08:50–09:08 年份争议还需 `focus_08m59.wav`。fresh Desktop 数据流/隐私验收仍开放。
- **发布门槛：** §270 是 partial diff scan，不代表全仓安全通过。P2 生产 service/WFP/per-lease 隔离与授权捕获、P4 声学/Desktop、P5 fresh Desktop trace、P6 owner/license/远端 CI/clean install 仍未关闭；项目整体 **NOT READY FOR RELEASE**。

## 271. 2026-10-13 P6 pinned .NET 构建输出身份复验

- **实际构建：** 使用仓库锁定的 .NET SDK **10.0.401** 运行 `scripts/generate_dotnet_build_bom.py`，输出 BOM 放在仓库外临时目录；生成器完成主构建及两个 related build，并记录 4 条 NuGet package records。
- **对照结果：** `scripts/check_dotnet_build_bom_outputs.py --actual <temporary-bom>` 成功，三个构建合计 **41 条 Release 输出记录**的相对路径、大小和 SHA-256 均与已提交 BOM 一致。另按 CI workflow 逐字段比较 schema/scope/toolchain/sourceInputs/nugetLock/packages，以及两个 related build 的锁定源字段，均匹配；两组实际 buildOutputs 非空。
- **边界：** 这是当前本地 Windows 与 pinned SDK 的新鲜构建对照，不是远端 CI、干净安装、跨平台复现、所有者许可决定或发布批准。没有修改 WFP/Firewall、安装服务或进行 live capture。远端 CI、P6 owner/license/native provenance、P2/P4/P5 门槛仍开放，整体 **NOT READY FOR RELEASE**。

## 272. 2026-10-13 P2 lease 进程树生命周期源组件

- **实现：** 新增独立 `LeaseProcessJob` Windows 组件：创建 unnamed Job Object，将 extended limits 设为且复读确认为仅 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`（未启用 breakaway）；调用方提供 suspended 根进程后，先 assign 再 resume，并且只接受初始 suspend count 恰为 1。启动失败时分别清理未分配进程或终止并 drain 已分配进程树；停止时调用 `TerminateJobObject`、有界轮询 active-process count 至 0，再释放句柄，Job handle 的 kill-on-close 是兜底。
- **验证：** 锁定 .NET SDK 10.0.401 的 Windows x64 Release build **0 warnings / 0 errors**；新增 self-test 覆盖假 API 调用顺序、错误 breakaway 配置在启动前拒绝、assign 失败清理和 resume 失败 drain。另以同一测试程序的 suspended 根进程启动无网络子进程，检查两者都在 Job 内，停止后分别等待根/子进程退出。完整 `--self-test` 全部通过，包括原有 SCM、DNS、TCP、CONNECT、DNS wire 和 named-pipe fixtures；`dotnet format whitespace --verify-no-changes --no-restore` 通过。
- **限制：** 这是可在普通用户令牌下验证的本地生命周期基础，不会安装服务或更改 WFP/Firewall。组件尚未接入 SCM handler、capture worker 或 per-lease identity；它不证明 Chromium 同身份进程树、egress 隔离、回滚、三条成功捕获或生产服务权限。Capture worker 仍 fail closed，URL capture 仍不可用，P2 继续 **OPEN / NOT PASSED**。
- **P4 附件：** 用户重新提供的 `focus_01m11.wav`、`focus_05m40.wav`、`focus_08m41.wav` 可读取，但当前会话没有音频听辨接口，未产生声学结论、未引用 ASR 猜测为人工验证，也未修改任何逐字稿。08:50–09:08 年份冲突仍需 `focus_08m59.wav`；fresh Desktop 隐私/数据流验收仍开放。
- **后续门槛：** P2 仍需 service/worker/identity/WFP 接线与 rollback、live 隔离探测及三条授权媒体端到端成功；P4 仍需具备音频感知能力的审阅者记录三处时间点和 fresh Desktop 验收；P5 需新 Desktop trace；P6 需 owner/license/repository/remote CI/clean install 决策与证据。§270 安全扫描为旧冻结快照、partial coverage，不覆盖本节新增文件和文档。本地 harness 通过不能替代上述门槛，项目继续 **NOT READY FOR RELEASE**。

## 273. 2026-10-13 NuGet canonical contentHash 当前工作树复验

- **复验目的：** §256 历史记录里“当前状态/当前代码”的措辞与 §257 已完成的修复相冲突。本节以前进中的当前工作树和锁定依赖缓存为准，并已将 §256 两段改写为明确的历史快照说明。
- **实现核对：** `scripts/generate_dotnet_build_bom.py` 仍分别校验归档 raw SHA-512 与 `.nupkg.sha512`、`.nupkg.metadata` 的 `contentHash` 与 lock，以及 pinned .NET SDK helper 通过 `NuGet.Packaging.PackageArchiveReader.GetContentHash` 从归档计算出的 canonical contentHash 与 lock；随后对每个精确归档运行 `dotnet nuget verify --all`。测试包含 raw archive hash 不等于 lock 但 canonical hash 匹配时接受，以及 canonical hash 与 lock 不匹配时拒绝的用例。
- **新鲜实测：** 使用 .NET SDK **10.0.401** 重新运行 BOM 生成器，实际处理 4 个锁定签名包。**4/4** 的 canonical hash 与 lock 匹配、**4/4** 的原始归档 SHA-512 与 lock 不同、**4/4** `dotnet nuget verify --all` 通过。这验证了 §256 所述原始摘要差异不会导致合法 signed package 被拒绝，也确认当前缓存中的四个精确包满足各自 lock 值。
- **结论边界：** §256 的 CWE-345 finding 已由 §257 修复；本轮没有发现它在当前生成器中复现。定向 BOM 回归最近结果 **24 passed、1 skipped**，跳过原因仍是当前账户无法创建 symlink。此次复验没有扩展 BOM 到未纳入其 scope 的 `capture-pipe` 服务项目，也不是远端 CI 或完整当前树安全扫描。P2/P4/P5/P6 生产与外部验收门槛仍开放，项目继续 **NOT READY FOR RELEASE**。

## 274. 2026-10-13 当前冻结差异安全扫描与 P4 附件候选复核

- **扫描身份与范围：** Codex Security Diff Scan `dcc6d32b-a735-4a2e-bbbd-184823ad5f31` 已封存，基线/HEAD 为 `b166778ee5283591a1b799535b746ba198e38653`，快照摘要 `codex-security-snapshot/v1:sha256:bc76e21a943fc819fe00196882fe1e1aa6b12d99cfd898f3a5c3cfdded744f1a`。120/120 个权威 worklist 项完成静态复核：应用/Skill 28、Windows native/WFP 69、脚本/CI 23；本轮没有保留可信候选，报告级 finding 为 0。
- **覆盖边界：** 安全工作台报告 `filesTotal=273` 是全量文件数，权威 worklist 有 120 项。当前独立枚举为 273 个文件：251 条当前变更路径、22 个未变更文件；120 条当前变更路径在 worklist 内，另有 131 条当前变更路径不在其中。`git status --short` 的 145 行（66 个 tracked changes、79 个折叠后的 untracked entries）不是展开后的路径数；`--untracked-files=all` 的 251 条才与当前变更路径枚举相符。131 条是扫描后当前工作树差异，可能包括冻结快照后的编辑，需逐项分类；它们不能全部断言为扫描当时遗漏。coverage 为 **partial**。扫描未运行应用、浏览器、Windows service、BFE/WFP 或网络，不代表全仓、生产部署或远端仓库安全通过。当前 URL capture/生产 WFP enforcement 仍未接线，产品保持 fail closed。
- **P4 附件与自动识别：** 收到的 `focus_01m11.wav`、`focus_05m40.wav`、`focus_08m41.wav` 均与本地听审包 manifest 身份匹配。已有两种本地 ASR 的交叉识别只给出复听候选：01:02–01:20 的“关键词/ASIN”术语差异，05:31–05:49 的 bid/出价同音写法，08:32–08:50 两路均为 2019。08:50–09:08 的 2016/2026 冲突不在这三段中，需另核 `focus_08m59.wav`。
- **声学验收状态：** 当前会话无法感知或播放音频内容，故不把 ASR 共识写成听审结论；未判断漏词/增词，也未修改 raw/reviewed 逐字稿。P4 声学验收和 fresh Desktop 数据流/隐私验收仍 **OPEN**。
- **后续对策：** 导出当前 131 条 worklist 外变更路径，并与冻结快照逐项比较，标记扫描后新增/修改文件；完成的只读分区审查覆盖 `native/`、`tests/` 的 74 条路径及根目录、`.github/`、`scripts/`、`skills/`、`.codex/`、`tools/`、`docs/` 的 57 条路径。静态补审未发现其他可确认的产品漏洞或隐私泄露；测试专用 Sandbox 探针有低风险边界候选，处理建议见 [安全审核报告](SECURITY_REVIEW_REPORT_2026-10-13.md)。由于当前树不等于冻结映像，131 条中哪些在扫描时已存在仍需逐路径比对，并应在新扫描中刷新 coverage。由具备音频感知能力的审阅者核对上述术语片段以及 `focus_08m59.wav`，保留时间点和裁决证据。P2 live isolation、P5 fresh Desktop trace、P6 owner/license/远端 CI/clean install 仍未完成。项目整体继续 **NOT READY FOR RELEASE**。扫描封存后的文档同步不属于冻结快照；逐字稿未修改。

## 275. 2026-10-13 禁用未认证 Sandbox 网络探针入口

- **问题来源：** §274 的 worklist 外补审发现测试程序仍接收 `--sandbox-probe-client`。旧实现把调用者可自行设置的 guest 环境变量和 run token 当成 guest 标记，并可在显式命令下向参数目标发 TCP/UDP DNS 探测。没有普通产品调用点，这不是已确认的产品漏洞，但不符合 Sandbox 文档要求的“缺少可信 guest 验身时禁用探针”。
- **修复：** 从 `Program.Main` 移除该命令分发；`SandboxProbeClient.Run` 改为拒绝 stub，不创建套接字或 listener。新增直接回归：即使伪造旧环境标记和 run token，CLI 参数与 helper 都返回 2、无 `ready` 标记且输出 disabled 原因。
- **验证：** 使用项目锁定 .NET SDK 10.0.401，执行 `dotnet run --no-restore --configuration Release --project tests/LeasePolicyCompiler.Tests.csproj`，**15/15** harness 检查通过。验证仅启动本地离线 harness；没有连接网络、打开 Sandbox、调用 BFE/WFP 或修改主机策略。
- **边界与后续：** 此修复在 §274 扫描封存后进行，不追溯改变该扫描结果。要恢复 guest 探针，必须先实现独立可信的 Sandbox 创建与 guest 身份证明，并限制探测目标；环境变量/run token 不能作为隔离证明。生产 WFP service、apply/readback/rollback、per-lease worker、真实隔离矩阵和三条授权捕获仍未完成；P2 保持 **NOT PASSED**。

## 276. 2026-10-13 当前工作区差异安全复核封存

- **扫描身份与覆盖：** Codex Security Diff Scan `68b37df7-96b7-4606-a38c-e73b09536f79` 已封存；基线/HEAD 为 `b166778ee5283591a1b799535b746ba198e38653`，冻结摘要 `codex-security-snapshot/v1:sha256:9f9017b8689484cbc1096dde0690b4383486db9190abe458648005511050439d`。权威 worklist **120/120** 项完成，工作台 `filesTotal=273`；另有独立只读复核覆盖 worklist 外 **131** 条当前变更路径（`native/tests` 74 条，其他目录 57 条）。报告级 finding 为 **0**。该结论限于当前冻结 diff 的静态审查。
- **探针修复与诊断代理：** 静态复核确认 §275 的探针 CLI 参数已拒绝，helper 无条件 fail closed；先前锁定 .NET 10.0.401 离线 harness 为 **15/15**，本扫描未重跑。独立启动的 loopback HTTPS 诊断代理不在 CLI 捕获路径，且不是进程出口隔离；若未来用作隔离边界，需另行加入认证/进程绑定并动态验证。
- **安全与运行时边界：** 本扫描未执行应用、测试、网络、Sandbox、BFE 或 WFP；不会证明生产服务部署、宿主/浏览器隔离、远端 CI、实际用户目录 ACL 或许可证适用性。项目仍有 P2 生产 WFP/service 与捕获验收、P4 声学及 Desktop 隐私验收、P5 fresh Desktop trace、P6 owner/license/远端 CI/clean install 未关闭，整体继续 **NOT READY FOR RELEASE**。
- **P4 附件状态：** 三段附件已对应听审包的 18 秒时间窗（01:02–01:20、05:31–05:49、08:32–08:50）。现有 ASR 对照只提供复听候选；当前会话没有音频感知能力，故未作听音裁决、未修改 raw/reviewed 稿。08:50–09:08 的年份争议仍需单独核对。
- **报告同步边界：** §276 与本报告摘要是在冻结扫描封存后更新的文档，不属于扫描快照；下次差异扫描应包含这些文档变更。

## 277. 2026-10-13 PyAV 锁定 wheel 的 FFmpeg configure 字符串取证

- **目的与边界：** 补充 P6 已知 PyAV/FFmpeg build-configuration 缺口，不作许可证或再分发结论。新增离线只读脚本 `scripts/inventory_pyav_ffmpeg_build_config.py`，仅读取 `skills/douyin-transcript/uv.lock` 锁定的 `av==15.1.0` wheels 和既有 SHA-256 cache；不联网、不安装、不执行 wheel，也不解压归档成员到磁盘。
- **制品绑定结果：** 14 个 CPython 3.11/3.12 Windows、macOS、Linux wheels 共 478,395,975 bytes，SHA-256 与锁文件相符。脚本扫描了 1,328,624,710 bytes native members；14/14 wheel 都找到可读 configure 字符串，共 98 个 native member 字符串（每 wheel 7 个），且每项成员 SHA-256 与大小均匹配 wheel 内 `RECORD`。配置字符串归并为 3 种平台变体：Windows 14 项、macOS 28 项、Linux 56 项；都含 `--enable-libx264` 与 `--enable-libx265`。机器清单 SHA-256 为 `d466263aeb893a0ae7e131591b09098309efc022df72f5625579abceb290352e`，见 `docs/pyav-ffmpeg-build-config-inventory.json`。
- **实现与验证：** 新增 5 个定向合成测试，Windows Python 3.11.15 为 **5 passed**；覆盖 artifact/member `RECORD` 错配、缺轮子、非普通 native 成员及 configure 字符串误识别。Ruff lint、format check、py_compile 通过；在本机 235 项锁定 artifact 缓存上运行清点为 **14 wheels / 98 RECORD-verified members**。`git diff --check` 通过，仅报告工作区既有 LF→CRLF 转换提示。
- **审计结论与后续：** 读取出的二进制字符串不是发布方签署的完整构建清单；字符串缺失也不能证明组件不存在。字符串中的 `--enable-libx264` / `--enable-libx265` 是需继续由适格许可人员审查的线索；`--enable-gpl` 是否出现在字符串中都不能独自决定法律义务。还需取得每个拟发行 artifact 的完整 provenance/build manifest、组件 BOM、notice 与对应源码，核对运行时 linkage，并由所有者决定发行范围；不批准 PyAV/native binary 再分发，SPDX `licenseConcluded` 继续为 `NOASSERTION`，P6 **NOT READY**。
- **快照关系：** 本节代码、机器清单与文档在 §276 Diff Scan 冻结后新增，未被 §276 的 120 项 worklist 扫描覆盖；下一次当前差异复核应纳入这些改动。此项离线清点未触碰 WFP/BFE、网络、管理员设置或音视频内容。整体项目仍因 P2/P4/P5/P6 等门槛未关闭而 **NOT READY FOR RELEASE**。

## 278. 2026-10-13 离线动态 lease 生命周期合同、范围阻塞与附件复核

- **P2 源码切片：** 新增 `native/windows/wfp-policy-runtime/DynamicLeaseCoordinator.cs` 和 fake-session harness。它从公开 `LeasePolicyInput` 经现有编译器构造计划；每次 open 先执行 persistent baseline reconcile/readback，再校验 lease/SID 与动态规则，打开独立 session、应用规则并要求完整预期投影读回。Apply/readback/cancel 失败会尝试关闭 session；不能确认清理时保留句柄并隔离后续 opens。worker 已启动后必须先收到 lease 匹配、Job 已终止且活动进程为零的 drain receipt 才能关闭 session；重复 close 保持安全。
- **验证：** pinned .NET SDK 10.0.401 下 Runtime/harness Release 执行成功，**17/17** harness 检查通过、0 warnings / 0 errors；两个项目的 `dotnet format whitespace --verify-no-changes --no-restore` 与 `git diff --check` 通过。额外负向 fixture 将第一条 lease 的过滤器注入 baseline 快照，确认第二次 open fail closed，且不分配/关闭歧义 session。独立复跑 harness 得到相同 17/17。没有调用真实 WFP/BFE。
- **发现的集成阻塞：** 当前 dynamic filter projection 使用与 persistent AppID baseline 相同的固定 service ProviderKey/SublayerKey。`PersistentBaselineCoordinator` 对该完整读回 scope 只接受已识别的 persistent baseline filter；如果未来 native session 在这里加了第一批动态过滤器，下一次 baseline readback 可能因发现非 persistent filter 而 fail closed。Fake store 没有把 session filters 合并进 baseline snapshot，因此“双 lease”用例只测 coordinator lifecycle，不能证明 WFP 中的真实多 lease 共存或隔离。新增负向 fixture 仅验证冲突已暴露时安全拒绝；它不证明 native WFP coexistence。阻塞和要求见 [DYNAMIC_LEASE_SCOPE_LIMITATIONS.md](../native/windows/wfp-policy-runtime/DYNAMIC_LEASE_SCOPE_LIMITATIONS.md)；native 接线前必须建立可验证的 baseline 与动态规则所有权/读回分界，且不能静默漏掉未知或遗留对象。
- **范围设计审查（候选，未实现）：** 独立源码审查发现不能直接把每条 lease 放进独立 sublayer：当前 allow/block 依赖同一 sublayer 内 filter weight；WFP 会评估所有 sublayer，基本仲裁中 Block 覆盖 Permit，而 sublayer weight 改变遍历顺序（[Microsoft Filter Arbitration](https://learn.microsoft.com/en-us/windows/win32/fwp/filter-arbitration)、[FWPM_SUBLAYER0](https://learn.microsoft.com/en-us/windows/win32/api/fwpmtypes/ns-fwpmtypes-fwpm_sublayer0)）。较保守的源码原型候选是每 lease 唯一 dynamic provider、继续使用 baseline sublayer，同时让 baseline 读回遍历并严格分类整个 shared sublayer、只接受已注册 lease rows；但 enum template 不能按 sublayer/session 选取，且只有调用者有 READ 的对象会返回（[FWPM_FILTER_ENUM_TEMPLATE0](https://learn.microsoft.com/en-us/windows/win32/api/fwpmtypes/ns-fwpmtypes-fwpm_filter_enum_template0)、[FwpmFilterCreateEnumHandle0](https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmfiltercreateenumhandle0)、[WFP access control](https://learn.microsoft.com/en-us/windows/win32/fwp/access-control)）。ACL visibility、native arbitration 与关闭后清理均未验证；因此候选尚未实现，不能关闭上述集成阻塞或 P2 gate。
- **P2 状态：** 没有 production dynamic-session adapter；未改 `CaptureServiceFactory`、service/worker 接线、宿主 WFP/Firewall 或捕获路径。URL capture 继续 fail closed，P2 **NOT PASSED**。§276 冻结扫描不覆盖本节新源文件与说明。
- **P4 附件：** 用户本轮提供的 `focus_01m11.wav`、`focus_05m40.wav`、`focus_08m41.wav` SHA-256 与听审包 manifest 匹配，格式/长度也符合清单。当前会话没有音频感知接口；未声称听辨，没有用 ASR 代替听审，也没有修改 raw/reviewed 稿。P4 至少三处声学对照、08:50–09:08 的 `2016/2026` 冲突和 fresh Desktop 数据流/隐私验收仍开放。
- **P6 复验：** 在最近 scanner hardening 后重新对本机锁定缓存运行 PyAV 配置 inventory，仍为 **14 wheels / 98 RECORD-verified native members**；临时输出 SHA-256 与仓库清单一致：`d466263aeb893a0ae7e131591b09098309efc022df72f5625579abceb290352e`。它仍只是二进制字符串证据，不关闭 provenance、许可、owner/repository decision、远端 CI 或 clean install 门槛。
- **总体状态：** P2 生产隔离/捕获、P4 声学与 Desktop 隐私、P5 fresh Desktop trace、P6 owner/license/remote gates 及完整当前树安全复审均未关闭；项目保持 **NOT READY FOR RELEASE**。

## 279. 2026-10-13 P6 本机 SPDX evidence 全量离线重放

- **执行环境与输入身份：** Windows PowerShell，复用本机已存在的 SHA-256 cache；没有下载、安装或执行被审计的 Python 制品。`uv.lock` SHA-256 为 `f4fc838d6f52555ca03ccf378c67e2a988666928904ff14bfab6d4af7c88f31b`，许可证 evidence JSON SHA-256 为 `3e065dbd1df88250da0fb9ab5b63c18d3f37ac91b1b894f73c20ece1ab439ed4`，SPDX JSON SHA-256 为 `c3005cb59d9173d6a93992636d04aea6e9357ffac089736754d54bd804e73a78`；固定 SPDX 2.3 schema SHA-256 为 `4126dc29f15e92feec92e9622f4939131ad58b125d6f578aa93e980a6e6f3212`。
- **准确重放命令：**
  ```powershell
  $cache = Join-Path $env:USERPROFILE '.local\share\douyin-transcript\lock-artifact-audit-cache'
  .venv-audit-py311\Scripts\python.exe scripts\verify_locked_artifact_cache.py --lockfile skills\douyin-transcript\uv.lock --cache-dir $cache
  .venv-audit-py311\Scripts\python.exe scripts\verify_spdx_evidence.py --lockfile skills\douyin-transcript\uv.lock --cache-dir $cache
  .venv-audit-py311\Scripts\python.exe scripts\check_spdx_sbom_freshness.py
  $env:UV_PROJECT_ENVIRONMENT = Join-Path $env:TEMP 'douyin-spdx-schema-check-20261013'
  uv run --offline --project tools/spdx-schema-check --frozen python scripts/check_spdx_schema.py
  ```
- **结果：** lock-cache verifier 通过，核对 42 package records、235/235 unique artifacts、235 lock references、2,097,567,472 bytes；SPDX evidence verifier 通过，覆盖 41 packages、210 artifacts、41 metadata members、9 license members、2 notice members 和 1,149 supplemental members；freshness checker 通过，按当前 lock/evidence/生成器重建并精确匹配 121 SPDX packages；官方 SPDX 2.3 schema checker 通过，schema 摘要与上述固定值一致。对提交的 SPDX JSON 另行读取计数为 121 package records、137 relationships，121/121 个 package 的 `licenseConcluded` 均为 `NOASSERTION`。初次直接从 `.venv-audit-py311` 调 schema checker 因该环境没有 `jsonschema` 而返回 `ModuleNotFoundError`；随后改用锁定的独立 checker 项目和 `uv --offline`，从本地缓存建立临时环境后成功，没有网络回退。
- **范围与状态：** 这是本机缓存的字节/元数据完整性、提交 SPDX 对当前输入的新鲜度以及 JSON Schema 结构复验；它不证明未记录成员的完整枚举、发布方构建来源、native 组件闭包/链接关系、notice 的适用性/完整性、许可证结论或再分发权。所有 `licenseConcluded` 仍为 `NOASSERTION`；项目根 LICENSE、所有者批准的发行范围/仓库决定、native provenance/linkage/notices、远端 CI 与 clean install 仍开放。P6 继续 **NOT PASSED**，项目整体 **NOT READY FOR RELEASE**。

## 280. 2026-10-13 当前冻结差异安全扫描、离线 P2 源码进展与 P4 附件边界

- **安全扫描：** Codex Security Diff Scan `379ff356-fc08-46cf-ab1a-a1edd44da9e9` 已封存；冻结摘要为 `codex-security-snapshot/v1:sha256:2cf348876c4bae76151c58ef850cea109b7186fea79351ede4eb8c28212616bc`，基线/HEAD 为 `b166778ee5283591a1b799535b746ba198e38653`。权威清单 **122/122** 项完成，报告级 finding **0**。候选处置：测试 fixture 资源消耗为不适用；宿主 SYSTEM 可满足 Sandbox guest 脚本的 SYSTEM SID 检查，但该脚本需要管理员/操作者手动运行且没有产品调用路径，按 privileged-only 条件忽略为漏洞，保留身份校验加固建议；原型 WFP ACL 接受规范 SID 并授权 GENERIC_ALL，因真实服务 SID、native backend 与 live ACL 证据缺失继续 deferred。
- **覆盖限制：** coverage 为 **partial**。扫描区没有冻结源码副本；`DynamicLeaseCoordinator.cs` 与 `WfpNativeObjectProjection.cs` 的修改时间晚于扫描冻结点。审阅者阅读的是当前工作树版本，无法将其 byte-for-byte 绑定到冻结摘要；下一次当前树安全扫描须纳入这两文件。扫描完成期间工作树仍有变化，封存结果严格对应原冻结摘要，不代表现在的全工作树。
- **P2 源码更新：** coordinator 使用每租约唯一的非持久 provider key、共享持久 baseline sublayer，并以离线 fake-store 验证生命周期与精确读回；锁定 .NET SDK 10.0.401 harness **17/17**。这只是纯托管源码/夹具证据。native baseline 仍可能把另一 lease 的动态 filter 作为外部对象而拒绝后续 lease；没有生产 native backend、service identity/wiring、WFP 应用/回读/回滚或 live 多租约测试。P2 继续 **NOT PASSED**。
- **P4 附件：** 用户本轮提供 `focus_01m11.wav`、`focus_05m40.wav`、`focus_08m41.wav`。当前会话没有可听辨这些文件的音频感知接口；未填写听审结果、未把 ASR 推测当作人工听辨，也未改 raw/reviewed 逐字稿。`08:50–09:08` 年份冲突仍需 `focus_08m59.wav` 的听审。
- **整改对策：** Sandbox staging helper 应改用可验证的 guest 身份/一次性运行凭证，限定源树与 staging 目标并防止 reparse 路径逃逸；WFP ACL 应由已安装服务身份派生 SID、采用经 native 审核的最小权限掩码，并在 incomplete/foreign/stale filter 情况下保持 fail closed；native harness 需覆盖并发 lease、共享 sublayer 跨 provider 枚举、清理和 rollback。先对两份冻结后变化的源文件做新快照扫描，再进入真实管理员隔离环境验收。
- **最新回归与剩余门槛：** Python 3.11.15 全量测试为 **728 passed、46 skipped、0 failed**。P2 实际隔离/授权捕获、P4 人工声学与 Desktop 隐私、P5 fresh Desktop trace、P6 owner/license/provenance/remote CI/clean install 仍开放；总体 **NOT READY FOR RELEASE**。

## 281. 2026-10-13 shared-sublayer 离线合同与 P4 样本复核

- **P2 离线合同：** 新增 `SharedSublayerPolicyReadback` DTO 与闭世界 `SharedSublayerReadbackContract`。验证器从 persistent baseline 编译器和 coordinator 的 active-lease registry 生成期望集合，逐项核对 provider、filter、shared sublayer、动态 lifetime 和 owner/DACL evidence；缺项、重复、外部或陈旧对象、错误 provider/sublayer、持久化动态 filter、ACL 不匹配、不完整快照及越界注册数均拒绝。active registry 导出不包含伪造的 WFP session ID；`FWPM_FILTER0` 不提供该字段。
- **真实合并夹具：** Runtime harness 将 baseline fake store 与两个仍活动 fake session 的 provider/filter/ACL evidence 合并，验证两租约共存、任一 lease 关闭后只余另一个、全部关闭后回到 baseline-only；并覆盖错误对象与缺失/重复/不完整读回拒绝。使用锁定 .NET SDK 10.0.401 运行 Runtime Release harness **17/17**；Runtime 与 harness 的 `dotnet format whitespace --verify-no-changes --no-restore` 均通过；`git diff --check` 通过（仅有既存 LF→CRLF 提示）。
- **P2 边界：** 这只是独立 managed DTO/验证器和合成夹具，没有 native producer，未接入 `NativeWfpPolicyStoreAdapter` 或 native reader。它不证明真实 WFP 可见性、ACL 授权、跨 provider 的 BFE 事务一致性、动态 session 生命周期、close 清理或仲裁；native baseline 仍可能因共享 sublayer 内出现外部 provider filter 而 fail closed。未运行 live BFE/WFP、Sandbox、网络、服务安装或宿主策略修改，P2 仍 **NOT PASSED**。安全扫描 §280 早于本节代码、测试与文档，coverage 仍 partial；需纳入下一次当前树扫描。
- **P4 附件身份：** 重新计算 `focus_01m11.wav`、`focus_05m40.wav`、`focus_08m41.wav` SHA-256，三者均与私有 listening manifest 相符；每段为 576,044 bytes、18 秒、mono PCM 16 kHz/16-bit。已有两路本地 ASR 仅给出候选差异（01:11 关键词/ASIN、05:40 bid/出价、08:32–08:50 为 2019）；本会话没有音频感知接口，未声称听辨、未填写人工 comparison form、未改 raw/reviewed 逐字稿。08:50–09:08 的 2016/2026 冲突不在这三段范围，仍需 `focus_08m59.wav` 的声学核验。
- **P5 部分证据：** 当前宿主已发现 repo-scoped `douyin-transcript` Skill；只读 CLI `doctor --json` 的脱敏结果为 `overall=ready`、`local_transcription=ready`、`douyin_urls=setup_required`、`browser_isolation=unavailable`。这证明本地发现与 CLI 诊断的一段路径，不是 fresh Desktop `/skills`/`$douyin-transcript` 实际任务 trace，P5 继续 **PARTIAL / OPEN**。
- **总体状态与对策：** P2 需要 native 全范围 shared-sublayer producer/adapter、实际服务 SID 与 ACL 审批、同一 BFE 事务中的基线与 active leases 核对、close 后原生对象消失证明和 disposable VM 仲裁/并发验收；P4 需要具备音频感知能力的审阅者完成至少三段声学比对，并验收 fresh Desktop 数据流/隐私；P5 需要真实 Desktop Skill invocation trace；P6 所有者 LICENSE/发行范围/仓库与远端决策仍待办。项目整体 **NOT READY FOR RELEASE**。

## 282. 2026-10-13 管道 artifact 校验后发布

- **问题与修复：** `CapturePipeClient` 原先在读取每个媒体块时就写入调用方目标流，只有完整读取后才检查终止标记、额外尾随字节和 SHA-256。现在先把不超过协议上限的内容写入随机命名、`CreateNew`、`FileShare.None`、`DeleteOnClose` 暂存流；长度、终止标记、无尾随数据和摘要全部通过后，才从暂存流复制到调用方目标。非法摘要参数及越过 512 MiB 上限也会在开始传输前拒绝。暂存流始终在方法退出时关闭。
- **回归验证：** 锁定 .NET SDK 10.0.401 命令 `dotnet run --project native/windows/capture-pipe/CapturePipe.csproj --configuration Release -- --self-test` 成功；完整 Windows harness 各模块通过，新增直接覆盖错误终止标记、尾随数据、摘要不匹配、超出声明长度的数据块以及有效内容追加到已有目标前缀。四种拒绝输入都验证目标字节和位置不变。`dotnet format whitespace ... --verify-no-changes --no-restore` 和 `git diff --check` 通过。
- **安全与范围边界：** 本次实现是 native 管道原型内的防御性修复，尚未接入生产 worker/CLI，也没有生产调用者。目标流在**源验证失败**时不再暴露任何部分媒体；若之后将已验证数据写入调用方流时发生 I/O 错误，该目标流仍可能只收到部分已验证内容，调用方必须丢弃失败目标。新 Codex Security Diff Scan `0ffcb65f-c76a-489f-9370-ffd0a60069ce` 针对冻结摘要 `codex-security-snapshot/v1:sha256:d78de105745e25e48fe868798e43b3d5d1ccb0edeb37241f0ae0d463480fb1cd`，复核 123/123 权威变更源代码项，0 个报告级可达漏洞；coverage 仍为 partial。artifact candidate 已按本地修复/回归证据关闭，CONNECT/SNI 与 WFP 服务 SID/ACL 两个集成候选仍 deferred。扫描没有运行 service、WFP/BFE、浏览器、网络或宿主策略操作；本段扫描身份同步在扫描快照之后，不属于该摘要覆盖字节。
- **总体状态：** 该增量不关闭 P2 的生产 service/WFP/per-lease isolation 和 live capture 门槛；P4 声学/Desktop、P5 fresh Desktop trace、P6 所有者许可证/发行/远端 CI 与 clean install 仍开放。项目继续 **NOT READY FOR RELEASE**。

## 283. 2026-10-13 敏感文件误报修复与最终当前差异复核

- **误报与处理：** 仓库敏感文件扫描器将一个名为 `sessionId` 的 GUID 局部变量和 `session.SessionId` 属性链误识别为凭据赋值。检查器只报告了路径/类别，没有打印匹配值。将局部名改为 `sessionGuid`；这是标识符改名，不改变 session 行为，也不触及逐字稿或媒体内容。修改后 `scripts/check_sensitive_files.py` 通过。
- **回归：** 修改前后相关 WFP Runtime harness 均为 **17/17**；最终快照下用锁定 .NET SDK 10.0.401 再运行 Runtime harness **17/17**，`dotnet format whitespace --verify-no-changes --no-restore` 通过。管道 artifact 的接收/发布回归与 CapturePipe 完整 `--self-test` 见 §282，本节仅变更 DynamicLeaseCoordinator 局部变量名。
- **安全复核：** Codex Security Diff Scan `0e0f14d7-0ce0-44a3-935c-b003aac7f88c` 已封存，冻结摘要 `codex-security-snapshot/v1:sha256:7f53743d69df9b89ceeefed5d05c9a9e133b7b151549d05e1ec03ed5803f75f6`，基线/HEAD `b166778ee5283591a1b799535b746ba198e38653`。280 个工作树文件中，123/123 权威变更源代码行完成复核，0 个报告级可达漏洞，coverage 仍为 **partial**。artifact validation-before-publish 候选已按当前源码和本地 harness 证据关闭；CONNECT/SNI 与 WFP service SID/ACL 两项仅作为未来集成门槛保留 deferred。没有运行生产 service、浏览器、网络、WFP/BFE、Sandbox 或宿主策略。

## 284. 2026-10-13 WFP 原型对象 ACL 收紧与当前回归

- **发现与修正：** WFP 原型曾把 service SID 设为对象 owner，并向 SYSTEM 和 service SID 授予 `GENERIC_ALL`。对象所有者天然可获得 `WRITE_DAC`，因此仅在 DACL 中限制 ACE 仍不足以阻止该 service SID 自行改写对象 ACL。现在 owner/group 固定为 LocalSystem，DACL 为 protected，仅给 SYSTEM 与配置的 service SID `GRGWGX`（WFP generic read/write/execute）；不再给服务所有权、`GENERIC_ALL` 或 `WRITE_OWNER`。
- **依据与验证范围：** Microsoft WFP 文档说明 owner 可更新对象 DACL；WFP 的 generic rights 展开为通用读、写、执行的标准权限和 WFP 操作权限，`GENERIC_WRITE` 覆盖新增、关联、删除和写事务等操作。[WFP access control](https://learn.microsoft.com/en-us/windows/win32/fwp/access-control)、[WFP access right identifiers](https://learn.microsoft.com/en-us/windows/win32/fwp/access-right-identifiers)。Runtime harness 新增对 owner/group、受保护 DACL、两个允许主体、ACE 标志、精确通用权限掩码以及拒绝 `GENERIC_ALL` 回退的检查。
- **验证结果：** 锁定 .NET SDK 10.0.401 的 WFP Runtime harness **17/17**；Runtime 与 harness 的 `dotnet format whitespace --verify-no-changes --no-restore` 均通过。Windows Python 3.11.15 全量测试 **728 passed、46 skipped、0 failed**（171.52 秒）；敏感文件扫描通过；`git diff --check` 通过（Git 仍提示既有 LF/CRLF 工作树转换）。
- **安全边界：** 这是 source/fake-harness 验证，没有 live BFE/WFP、已安装服务或真实 ACL 读回。尚未从 SCM 推导并验证 service SID，也未证明 service token 对 filter container、layer 及对象集合有足够且完整的权限。generic rights 仍是 prototype policy，不是完成的最小权限/产品批准结论。
- **模型校对与标点验收边界：** canonical Skill 要求当前调用 Agent 使用其默认模型校对、纠错和补自然标点；CLI 明确标记 raw-only，归一化不擅自改写 ASR 文本，侧车只验证文本格式与 raw/task 绑定。该接口不能自行证明实际模型调用、模型身份或逗号/句号语义位置。需在 fresh Desktop 会话保留脱敏调用 trace，并按“默认模型→review-sidecar→绑定成功→最终交付”验收；未绑定或没有模型调用证据时只标 raw/sidecar 草稿，不标最终稿。
- **扫描状态：** 最新封存扫描 §283 的 digest 早于本节源码与测试改动。新启动的整树扫描在 review inventory 尚未开始时取消，未产生新的扫描结论。最终稳定树仍需 canonical diff scan；不得将 §283 的 0 findings 归于当前整树。
- **项目结论：** P2 仍未通过；native producer/Runtime wiring、多 lease 完整读回、transaction rollback、service 安装/身份、实际出口隔离与三次授权捕获仍开放。P4 听审与 Desktop 数据流、P5 Desktop trace、P6 owner/license/remote CI/clean-install 仍开放。整体 **NOT READY FOR RELEASE**。
- **P4 与总体状态：** 用户再次提供的三段 WAV 只核对为听审附件；本环境没有音频感知能力，未声称听辨、未修改逐字稿。年份争议 `08:50–09:08` 还需 `focus_08m59.wav`；P4 Desktop 隐私、P5 fresh Desktop Skill trace、P2 生产 service/WFP/授权捕获和 P6 owner/license/远端发布门槛仍开放。安全扫描报告和状态文档同步晚于冻结时间，不属于其摘要。项目整体继续 **NOT READY FOR RELEASE**。

## 285. 2026-10-13 WFP shared-sublayer 可见性证明审查

- **发现：** `FWPM_FILTER_ENUM_TEMPLATE0` 没有 sublayer-key 成员；传入空模板会请求枚举全局 filter，但 WFP 只返回调用者有 `FWPM_ACTRL_READ` 权限的对象，枚举句柄本身还要求 filter container 的 `FWPM_ACTRL_ENUM`。因此“枚举成功且返回列表为空/完整”不能证明没有被隐藏的 filter。按 sublayer 读安全描述符也只能检查已知 key，不能发现未枚举对象。当前 `WfpNativeReadbackReader` 明确保留 `EnumerationCompletenessUnverified`，离线 `SharedSublayerReadbackContract` 没有 native producer；这两个边界不应被 `IsComplete` 或 DTO 字段绕过。
- **建议：** 不为既有固定 shared sublayer 背书“完整可见”。在隔离 VM 原型一个全新、不可预先占用的专用 sublayer key；服务创建时使用显式事务，若 key 已存在则拒绝接管。以 LocalSystem 为 owner、受保护 DACL 限制可创建 filter link 的主体；仅授予服务读取已知 provider/filter、安全描述符和枚举所需的权限。先用 WFP 原生测试收敛到精确权限，不把当前 `GRGWGX` 直接当成最小权限批准。读回在同一只读事务中分页枚举、核对已登记 baseline/active leases、逐个读取 ACL，并对任何 API 错误、未知对象、上限溢出或 ACL 差异 fail closed。
- **验收：** disposable VM 覆盖隐藏的 READ-denied 旧 filter、低权主体无法对专用 sublayer 建立 filter link、服务重启、多 lease 并发、关闭时真实对象清理、BFE 事务与 filter arbitration；管理员、LocalSystem 和内核驱动仍属于可信边界。旧 sublayer 如需迁移，先做可信特权清点/清理或换新 key，不能靠其自身 DACL 排除历史对象。
- **依据与状态：** [Microsoft filter enumeration template](https://learn.microsoft.com/en-us/windows/win32/api/fwpmtypes/ns-fwpmtypes-fwpm_filter_enum_template0)、[FwpmFilterCreateEnumHandle0](https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmfiltercreateenumhandle0)、[WFP access control](https://learn.microsoft.com/en-us/windows/win32/fwp/access-control)、[WFP access-right identifiers](https://learn.microsoft.com/en-us/windows/win32/fwp/access-right-identifiers)。以上为源码/官方文档审查，没有 live BFE/WFP 或宿主策略操作；方案仍须原生实现与隔离 VM 验证，P2 仍 **NOT PASSED**。

## 286. 2026-10-13 本地 ASR 强制重试修复与三段文本侧校

- **运行问题与修复：** `focus_01m11.wav` 的旧 `fast` 任务记录为 `MODEL_NOT_FOUND`；CLI 的 `--force` 对失败本地任务仍直接返回旧失败，提示却错误地称可以 `--force` 重跑。显式强制重跑现在会先校验原始本地路径与内容哈希，再原子地重新排队该本地任务，并更新到本次指定的模型 profile 与处理选项。该行为只针对同一份本地文件；不会顺带重试其他失败 URL。新回归覆盖从 `fast` 失败任务切换到当前 `balanced`/当前选项。
- **P4 片段处理：** 对 `focus_01m11.wav`、`focus_05m40.wav`、`focus_08m41.wav` 各运行一次本地 `balanced` ASR，均成功（18 秒、单声道 16 kHz PCM）。Agent 默认模型完成了三份独立文本校对侧稿，标点已补齐，scope notice 明确标记“未对照音视频逐字听审”；三个侧稿均绑定到各自精确 raw task，原始稿未覆盖。候选术语只按上下文校正，没有将这一步记为听审。
- **验收边界：** 当前会话没有音频感知接口，因此没有人工/声学确认任何词、数字或年份。08:41 片段末尾的年份、01:11 的关键词/ASIN 短语、05:40 的 `bid` 术语仍须对照音频确认；`08:50–09:08` 的年份分歧仍需要 `focus_08m59.wav`。P4 声学听审与 Desktop 数据流验收仍 **OPEN**。不得以 ASR 一致性、模型文本校对、侧稿绑定或格式检查宣称听审通过。
- **回归与扫描边界：** 完整 Python 套件 **729 passed、46 skipped、0 failed**（260.33 秒）；新增定向重试回归包含在内。Ruff check、Ruff format check、敏感文件检查通过；定向重试测试复跑 **2 passed**；`git diff --check` 退出码 0，仅有仓库既存 LF/CRLF 提示。最新封存安全扫描仍为 §283，早于 §284–§286 变更；本节没有产生新的当前树扫描结论，不能将 §283 的 0 finding 归于当前工作树。
