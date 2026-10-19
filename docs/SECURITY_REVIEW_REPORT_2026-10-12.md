# 2026-10-13 冻结快照安全审核报告与整改对策

> **历史专项报告：** 本文记录较早冻结快照的 116 项 worklist 和 2 个报告项。其结果仅适用于该快照；当前状态以 [2026-10-13 §274 安全审核报告](SECURITY_REVIEW_REPORT_2026-10-13.md) 为准，不能把本文当作最新扫描结论。

## 审核结论

本次对冻结工作树快照的安全复核覆盖全部 **116 个安全相关源码/配置 worklist 项**，确认 **2 个报告项**：无界读取调用者指定的锁文件（中风险，CWE-400）以及 Sandbox 诊断脚本未验证 guest 边界（低风险，CWE-269）。扫描 ID 为 `bcb4d896-63ef-4c58-a2f2-2ee56e68f7b3`，快照摘要为 `codex-security-snapshot/v1:sha256:058ece6601497d92c65823f6d67a0bbb8daaa759dc60d88a5158228fb8a1c3e1`。URL 捕获和生产 WFP 写入路径当前保持 fail closed，原型代码没有被当作已部署服务。

本结论是**部分覆盖的静态差异审查**，不能解释为全仓安全通过。工作台进度记录 `worklistRows: 116`、`filesTotal: 265`；因此本报告只把 116 当作已逐项审阅的工作项，不把它当作所有项目文件均已审查的证明。代码没有通过 live BFE/WFP、真实捕获或跨平台运行时验收；文档、测试、fixture 和生成证据也未在此次安全扫描中逐项完成全量审查。扫描发现由独立静态审阅核实，未执行恶意输入或宿主副作用。

## 审核身份与方法

- **项目：** `Douyin-Transcript-AgentSkill`
- **扫描 ID：** `bcb4d896-63ef-4c58-a2f2-2ee56e68f7b3`
- **封存状态：** Codex Security canonical scan 已于 `2026-10-12T16:15:59.114456Z` 完成并封存（北京时间 2026-10-13 00:15:59）。机器报告可读取，工作台状态为 `completed`；封存只固定本次结果，不改变下方明确的 partial coverage 与静态审查限制。
- **基线 / HEAD：** `b166778ee5283591a1b799535b746ba198e38653`
- **快照摘要：** `codex-security-snapshot/v1:sha256:058ece6601497d92c65823f6d67a0bbb8daaa759dc60d88a5158228fb8a1c3e1`
- **范围：** 仓库当前 working tree 的安全差异；Python/Skill/脚本工具与 Windows native/WFP 两个不重叠分片，父任务汇总。
- **结果：** 116 个 review items 关闭，2 个候选经静态验证后报告；覆盖为 `partial`，生产运行时验证工作保持开放。
- **动态验证边界：** 本轮安全扫描没有更改或访问宿主 WFP/BFE/Firewall，没有部署服务，也没有执行 P4 声学听审或远端 CI。

## 当前风险与对策

### 1. P2 原生 WFP 捕获仍是原型，尚未达到生产验收

本轮差异包含 `NativeWfpPolicyStoreAdapter` 和 fake-store harness。之前的 Release build 与 harness 记录为 0 warnings、0 errors、16/16；此结果是离线 contract/fake 验证，不证明生产 API 或系统策略行为。生产 `CaptureServiceFactory` 仍使用 fail-closed gate/worker，adapter 尚未接线，未发现一条可由当前产品实际触发的 WFP 政策写入路径。

主要未证明事项：

- **完整读回与 ACL 可见性：** 即使枚举 API 成功，当前证据不能证明 ACL 隐藏的对象也都能被枚举。完整枚举、descriptor 可读性和批准的 service ACL policy 比较需在真实隔离 guest 中验证。
- **DNS 结果完整性：** 验证 DNS 回答集完整、负响应语义和 DNSSEC 行为；不得把“不完整但通过”的 DNS 结果用于生成放行规则。
- **Native 调用的时间上界：** Adapter 的 30 秒 deadline 是协作式检查，不能抢占已阻塞的 native call。接入生产前应为每个 native 调用证明可中断/可回收，或移至可被可靠终止的隔离进程；单元测试 watchdog 不足以证明这一点。
- **事务失败语义：** 在真实实现中验证 begin/apply/readback/commit/abort/dispose 的故障路径；尤其 commit 失败时必须证明状态是已回滚、可检测且不会留下部分策略。
- **最小权限：** 复核 SYSTEM 和 service SID 的 `GENERIC_ALL` SDDL 是否必要；将服务访问和对象 DACL 收紧到完成功能所需的最小权限，并用正反向 SID/ACL 测试证明。
- **生产接线前置条件：** 保持 `WfpBaselineUnavailableGate` 和 fail-closed worker；只有上述 guest 验证通过、生产 adapter/readback/rollback 可复现后，才进入 CaptureService 集成验收。不要用 fake harness 通过替代该门槛。

### 2. 锁文件解析没有输入大小上限（中风险 / CWE-400）

三个离线审计工具在解析 TOML 前调用 `Path.read_bytes()`，一次性读取完整锁文件：

- [`inventory_locked_artifact_members.py#L166`](../scripts/inventory_locked_artifact_members.py#L166)
- [`inventory_numpy_native_members.py#L72`](../scripts/inventory_numpy_native_members.py#L72)
- [`inventory_locked_pe_imports.py#L86`](../scripts/inventory_locked_pe_imports.py#L86)

这些工具的 CLI 接收调用者指定的 `--lock`/lockfile 路径。若操作者或未来自动化将恶意或异常大的文件交给工具，完整分配和 TOML 解析会消耗与输入大小相关的内存和 CPU。当前没有发现仓库 CI 会自动运行这些工具，因此这是有条件的本地/自动化可用性风险，不是转写产品的远程入口。

**对策：** 三个工具共用同一个有界文件读取 helper，按块读取，最多读到配置上限加 1 字节；超限时在 UTF-8 解码和 TOML parser 之前拒绝。用有效小文件、上限边界、超限稀疏文件以及“超限时 parser 未调用”回归用例验证。

### 3. Sandbox 诊断脚本未验证 guest 隔离边界（低风险 / CWE-269）

`ChromiumAsUserTokenSmoke.ps1:505` 仅检查当前 SID 是 `S-1-5-18`，然后会创建本机账户、复制 Chromium 并更改文件 ACL（526–544），再启动浏览器（699）。宿主 SYSTEM 同样满足该条件。`GrantInteractiveDesktopAccess.ps1:112–123` 校验 token、时间戳、会话和目标 SID，却没有检查 Sandbox membership；第 126 行会更改 `WinSta0`/`Default` ACL。它们是 disposable Windows Sandbox 诊断，但身份或非零交互会话不能证明进程位于 guest。

风险需已有管理员/SYSTEM 操作者在宿主误运行这些诊断；没有确认远程路径或低权限提权。部分临时文件有清理逻辑，但这不能代替隔离边界检查。

**对策：** 副作用前要求可信 host-side controller 出具与当前 guest ID 和一次性 run token 绑定、不可伪造的 Sandbox attestation；缺少或不匹配时立即 fail closed。桌面 ACL grant 改为受保护的私有 IPC，只允许 harness 本次创建的确切低权限本地 SID；ack 校验失败时回滚本次 ACE。回归验证应确认宿主 SYSTEM、普通宿主登录、过期/伪造证明均在任何副作用前被拒绝。

### 4. README URL 登录说明与当前行为不一致（已由 §259 修复）

README 曾在无 broker 时同时说明“浏览器启动前失败”和“在已打开 Chromium 中登录”，与当前行为不一致；§259 已改为明确当前不会启动 Chromium，只有未来经过验证的 broker 集成后才可手动登录。该修复只改文档，不启用 URL 捕获。

**状态：** 文档差异已由项目审核报告 §259 修复；保留手动登录和有效 broker 前置条件，不自动化绕过访问控制。

### 5. P4 转写准确率仍缺少声学证据

已收到 `focus_01m11.wav`、`focus_05m40.wav`、`focus_08m41.wav`。现有 balanced 与 SenseVoice 本地 ASR 交叉检查可用于定位复听点：01:11 附近的关键词/ASIN，05:40 的 bid 术语，08:32–08:50 的年份候选；听审包另记录 08:50–09:08 的 2016/2026 冲突。它们是模型候选差异，不是实际发音结论。

当前会话没有音频感知/听辨工具，故本报告不声称已听过这三段，也没有自动改写 raw 或 reviewed 逐字稿。**对策：** 由具备播放能力的人工听审者逐段记录时间点、遗漏、插入、术语和不确定项，并对照原音及两路识别；完成 08:50–09:08 的年份核验。随后再验收默认 Agent 模型校对的数据流、用户告知和 provider 保留边界。

### 6. Agent 默认模型校对的数据边界需保留为显式验收项

Skill 的模型校对路径会把逐字稿放入调用 Agent 的模型上下文；具体 provider、地区和保留条件由 Agent 配置决定，仓库无法证明。用户已选择使用不同 Agent 的默认模型，但该决定不等于每个具体 Agent/部署的 provider 保留行为都已验收。

**对策：** 在每种目标 Agent 的实测中显示将发送全文的告知，保留必要授权步骤，记录实际 provider/model 标识与结果路径而不把逐字稿正文写入日志；确认默认模型确实能返回有标点的校对稿、不会摘要或增删事实，并将 reviewed sidecar 与 raw 文件隔离保存。

## 持续开放的发布门槛

- **P2：** 生产 service/store/apply/readback/rollback、service ACL、per-lease worker/Chromium 网络与进程树隔离、至少三条成功真实捕获，以及上述 WFP/DNS 证明。
- **P4：** 三段以上人工声学听审、08:50 后年份争议，以及 fresh Desktop 模型数据流/隐私验收。
- **P5：** 新会话 Desktop Skill 发现与实际调用 trace。
- **P6：** 所有者对仓库/发行范围的决定、LICENSE 与第三方 notices/provenance、适用 SDK/WDK 生成物审核、远端 CI 与干净安装。

上述事项未完成前，项目维持 **NOT READY FOR RELEASE**。本扫描没有验证或改变任何宿主网络策略。

## 相关证据

- Codex Security 生成的机器报告：`[本机用户目录及其余私有路径已省略]`
- 项目持续验收记录：[ACCEPTANCE.md](ACCEPTANCE.md)
- 项目审计时间线：[PROJECT_AUDIT_REPORT.md](PROJECT_AUDIT_REPORT.md) §260
- 旧 NuGet BOM finding 的修复复核：[SECURITY_REVIEW_FOLLOWUP_2026-10-12.md](SECURITY_REVIEW_FOLLOWUP_2026-10-12.md)
- 本地 P4 ASR 候选记录：位于用户私有数据目录 `output/p4_listening_pack_20261012/`，不是仓库内证据，也不构成听审验收。
