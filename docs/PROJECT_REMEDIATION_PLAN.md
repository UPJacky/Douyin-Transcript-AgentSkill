# 项目整改与验收对策

- 更新日期：2026-10-13
- 关联审核：[PROJECT_AUDIT_REPORT.md](PROJECT_AUDIT_REPORT.md)
- 项目状态：**NOT READY**

## §284 当前证据同步与剩余门槛（2026-10-13）

- **已复核：** §284 Windows Python 3.11.15 全套 **728 passed、46 skipped、0 failed**（171.52 秒）；WFP Runtime harness **17/17**、Runtime/harness format、敏感文件扫描通过。最新 sealed Diff Scan §283（`0e0f14d7-0ce0-44a3-935c-b003aac7f88c`）为 **123/123、0 finding、partial**，但不覆盖 §284 的 ACL source/test 改动；最终稳定树仍须扫描。
- **P2 进展与限制：** §284 将 prototype ACL 改为 SYSTEM owner、protected DACL 和仅 SYSTEM/service SID `GRGWGX`，并以 harness 检查权限掩码。此改动未接入 native producer/Runtime adapter，也没有安装服务 SID、live WFP ACL/readback、完整可见性、rollback 或生产 isolation 证据；multi-lease shared-sublayer DTO 仍是 offline contract。CONNECT/SNI 仍待集成约束。
- **P4/P5 状态：** 三段 WAV 的身份、格式、时长与私有清单相符，但当前会话无法听辨；未改 raw/reviewed 稿。Skill 已要求调用 Agent 用当前默认模型校对和补自然标点，CLI 仍只产 raw ASR；侧车绑定不证明模型身份或句读质量。fresh Desktop 模型调用/隐私 trace 与 08:50–09:08 年份声学核验仍开放。当前宿主的 `doctor --json` 是 CLI 证据，不能替代 fresh Desktop Skill invocation trace。
- **对策：** 实现 native 全范围读回和生产服务接线前先解决对象可见性、已安装 service SID、ACL 授权、BFE transaction scope、rollback 和 close 清理，并在可回滚 VM 中验证多 lease/arbitration。P4 需具备音频感知能力的审阅者记录至少三段时间点和术语差异；P5 需真实 Desktop trace；P6 需所有者决定根 LICENSE、发行范围和仓库归属后才能执行远端门禁。最终 release tree 还要重新扫描。整体仍 **NOT READY**。

## §271 P6 新鲜 pinned build 身份对照（2026-10-13）

- **已完成：** 使用锁定 .NET SDK 10.0.401 运行 BOM generator 对当前源码执行三个构建；生成到仓库外临时文件。CI 对照逻辑在本地复验：41 条构建输出的 path/size/SHA-256 全部匹配，主构建与两个 related build 的源码及锁定依赖字段与 checked-in BOM 一致。
- **尚未完成：** 远端 Windows CI、clean install、跨平台重现，以及 owner 的 license/发行范围/仓库决定仍开放。此本机构建证据不构成 P6 完成或发布批准；整体仍 **NOT READY**。见审核报告 §271。

## §270 报告输出控制字符缓解与当前树续验（2026-10-13）

- **已完成：** 锁文件 URL 中的 Unicode `Cc` 控制字符在解析阶段被拒绝；Markdown cell 将控制字符编码为十进制 HTML 实体，防止换行/回车改变表格结构。§269 的低危报告注入 finding 已在当前工作树缓解。
- **验证：** 封存 Diff Scan `c5cbf587-9810-463b-a7e0-e9af6f7d6a00` 覆盖 118/118 worklist 项，0 个当前报告级 finding；271 个变更路径中 153 个未逐行审查，coverage partial。Windows Python 3.11.15 全量 **723 passed、46 skipped、0 failed**，格式化后定向测试 **13 passed、2 skipped**；Ruff check/format 通过。
- **边界与剩余工作：** 该 scan 不覆盖其余 153 路径及生产环境。P2 生产隔离、P4 声学/Desktop 隐私、P5 Desktop trace、P6 owner/license/remote 门槛仍开放。三段 WAV 已在私有听审包匹配，但本会话不能直接听音；不把 ASR 候选算作声学通过，整体保持 **NOT READY**。见审核报告 §270。

## §266 P2 离线 reader 标量枚举补齐（2026-10-13）

- **已完成：** 为 WFP classify-options reader 增加 multicast-state (`0/1/2`) 与 loose-source-mapping (`0/1`) 的有界 `FWP_UINT32` 解码，只接受微软文档列出的枚举值；未知类型、错误 tag、重复项及越界值继续 fail closed。实现、fixture 和官方结构依据见审核报告 §266。
- **本机验证：** pinned .NET SDK 10.0.401 locked restore，x64 Release build **0 warnings / 0 errors**，native unmanaged harness **35/35**，reader/harness format verify 通过；全量 .NET build BOM 重生成。`test_dotnet_build_bom.py` **14 passed、1 skipped**（Windows symlink 权限）。
- **仍开放：** 这不接通生产 WFP store/service，也没有真实 BFE、ACL 可见性、Sandbox 或网络矩阵证据。P2 保持 fail closed；P4/P5/P6 与完整当前树安全审查继续开放，整体 **NOT READY**。

## §268 P6 CI evidence freshness mitigation（2026-10-13）

- **已实现：** CI 对已提交 SPDX 执行锁/许可证证据渲染新鲜度检查，并在 Windows pinned BOM build 后比对主构建及两个 related build 的输出路径、大小和 SHA-256。两项当前清单检查通过，针对性测试 **19 passed**，Ruff check/format 通过。
- **边界：** SPDX check 不重新验证归档成员字节；必须在完整 cache 可用时运行原始 verifier。当前 .NET 本地对照只以 checked-in BOM 自比较，实际生成产物与 BOM 的核对须由更新后的 Windows CI 证明。P2/P4/P5/P6 其他门槛仍开放，项目保持 **NOT READY**。

## §267 冻结差异安全复核与证据链整改（2026-10-13）

- **已完成：** 最新 Codex Security Diff Scan 封存，116/116 源码/配置审查项无可报告漏洞。扫描仅覆盖 266 个变化路径中的 116 个，覆盖为 partial；150 个路径和扫描后变化仍需审查。范围、限制与对策见 [SECURITY_REVIEW_REPORT_2026-10-13.md](SECURITY_REVIEW_REPORT_2026-10-13.md)。
- **待整改：** CI 从当前锁定依赖及许可证证据重建/比较 SPDX SBOM；锁定 .NET SDK 构建后逐项比对 BOM 输出路径、大小和 SHA-256，并加入漂移负向用例。当前未发现已提交证据已经失配，这两项用于防止之后漂移。
- **风险说明：** ASR worker 使用与 CLI 相同的 OS 身份和继承环境，不是 OS sandbox。面向不可信媒体的部署应增加低权限隔离、文件/网络限制和资源配额，或明确披露边界。
- **验收状态：** P2 生产服务/WFP/per-lease 与 live 验收、P4 人工听审/Desktop 隐私、P5 fresh Desktop trace、P6 owner/license/remote 门槛继续开放。三段 WAV 仅完成身份核对，本会话不能听辨；未修改转写稿。整体 **NOT READY**。

## §265 最新验证与未关闭对策（2026-10-13）

- Windows Python 3.11.15 全量回归 **693 passed、46 skipped、0 failed**（258.19 秒）；Ruff check/format、`uv.lock --check`、两份 Agent Skills validation、敏感文件扫描及 `git diff --check` 通过。跳过项包含未配置的 native interop、Windows link/junction 权限限制与 POSIX-only 用例，不能推导出跨平台或 reparse race 验收通过。
- 只读 `doctor --json` 显示本地 ASR/浏览器前置条件就绪，但 `browser_isolation=unavailable`、`douyin_urls=setup_required`；认证 broker/policy validator 未接入，URL capture 必须继续 fail closed。主机当前没有 .NET SDK，因此不能声称本轮重新构建 native reader。
- §264 安全差异扫描已封存，116/116 源码/配置审阅项为 0 个可报告 finding；总体 coverage 为 partial（266 个变化路径中 150 个未逐行审查），且工作台指出扫描期间工作树变化。需在支持的环境对当前树做完整安全复审，不能把 §264 作为全仓 clean 结论。
- 三段 P4 WAV 与既有听审清单身份相符，但当前会话无法感知音频。不得把 ASR 结果写成人工听审结论；需要具备音频感知能力的审阅者记录至少三段的时间点/差异，并覆盖 `08:50–09:08` 年份争议，同时完成 fresh Desktop 隐私/数据流验收。
- P2 生产 WFP/service/per-lease 隔离与三条授权成功捕获、P5 fresh Desktop 调用追踪、P6 所有者许可证/发行范围/远端决定和远端 CI/clean install 均未关闭。保持 **NOT READY**，不修改宿主 WFP/Firewall，也不发布。证据见审核报告 §265、[ACCEPTANCE.md](ACCEPTANCE.md) 与 [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)。

## 本轮已完成

**§262 安全扫描封存状态确认（2026-10-13）：** Codex Security scan `bcb4d896-63ef-4c58-a2f2-2ee56e68f7b3` 已完成并封存；§261 快照覆盖 116/116 worklist 项、265 个变化路径，coverage 仍为 partial，保留 CWE-400 与 CWE-269 两个静态问题。封存不代表全仓 clean。P4 附件不能由当前会话直接听辨，声学听审仍开放；P2/P4/P5/P6 gates 继续开放，项目 **NOT READY**。详见审核报告 §§261–262 和 [SECURITY_REVIEW_REPORT_2026-10-12.md](SECURITY_REVIEW_REPORT_2026-10-12.md)。

**§260 P2/P6 本地续验（2026-10-12）：** P2 managed adapter 现在拒绝缺失的整体 native readback projection，并保留事务视图投影用于一致性比较；fake-store/native adapter harness **16/16**，Runtime 与 harness whitespace format check 通过。锁定 .NET SDK 10.0.401 BOM 已随 source 更新成功重建，含 **235 条身份记录 / 218 个唯一路径**，SHA-256 `A0BE288F06FFCAEB6357312D12212099A7512EBD3374B5FCCE4610FF24700B39`；BOM 定向测试 **14 passed、1 skipped**（Windows symlink privilege）。生产 native WFP backend/service wiring、live isolation、P4/P5 Desktop 验收、P6 owner/license/remote gates 和当前树安全覆盖仍开放，项目保持 **NOT READY**。详见审核报告 §260。

**§255 本地发布证据续验（2026-10-12）：** 使用锁定 .NET SDK 10.0.401 刷新 build BOM，233 项仓库源输入/生成源码/构建输出哈希核验 0 missing/0 mismatches，`--skip-build` SHA 稳定，BOM 定向回归 **10 passed、1 skipped**。修复 copied-Skill clean-install smoke 对 URL dry-run `ready/0` 的过期预期；当前产品无 broker 时应为 `needs_attention/2` 并 fail closed。定向单测 **13 passed**，仓库外临时 locked 安装冒烟全流程通过。P2/P4/P5/P6 外部验收与完整当前树安全扫描仍开放；项目保持 **NOT READY**。详见审核报告 §255。

**§254 当前树全量回归（2026-10-12）：** Windows Python 3.11.15 全套 **679 passed、46 skipped、0 failed**（259.78 秒），覆盖 §250 RECORD bounded parser/output-path regressions、§252 evidence-writer parent-link and write-contract regressions、§253 sentence-ending punctuation checks。Ruff check/format、`git diff --check` 通过。跳过项为 native interop host 未配置、Windows 当前无 symlink 创建权限，以及 POSIX-only FIFO/dir-fd/权限场景；不表示 Windows reparse race 或 Linux/macOS 验收通过。P2 live isolation、P4 acoustic/Desktop、P5 Desktop trace、P6 owner/license/remote 与完整当前树安全扫描仍开放；整体 **NOT READY FOR RELEASE**。详见审核报告 §254。

**§253 reviewed sidecar 句末标点门槛：** 每段必须含 `。！？…` 之一；逗号、顿号、冒号、分号不再单独满足句末标点要求。定向测试 **23 passed、2 skipped**；全量结果见 §254。此格式检查不判定断句自然度，也不证明模型实际完成校对。详见审核报告 §253。

**§252 审计证据写入器路径边界：** 新增安全 create-only writer，迁移七个离线 evidence 输出调用方，拒绝 symlink/reparse 父目录并保留 create-only、原子替换、父目录是否预建和 POSIX 文件模式约定。最终定向测试 **36 passed、13 skipped**；Ruff、format、py_compile 通过。Windows 对抗性链接竞态与 POSIX dirfd 动态行为仍需适用 CI 验证。详见审核报告 §252。

**§251 P2 native reader 本地修复：** `FwpmEngineOpen0` 使用 `RPC_C_AUTHN_WINNT` (10)；对象恰好达到上限时以一个 bounded sentinel page 区分“正好到上限”和“超限”。锁定 .NET 10.0.401 x64 Release build **0 warnings / 0 errors**，离线 reader harness **34/34**。没有连接 BFE/WFP；生产 service/backend 和 isolation 验收仍缺失，P2 保持 fail closed。详见审核报告 §251。

**§250 安全审计工具资源与输出路径缓解（2026-10-12）：** RECORD 在调用 `csv.reader` 前新增列数/行数扫描，避免宽行先被 materialize；证据输出 helper 在写临时文件和 replace 期间固定父目录（POSIX 相对 dirfd 操作，Windows reparse-point-aware 目录句柄并拒绝 delete sharing）。新增两项回归用例；本轮只做 Ruff format/check 和 `py_compile`，未运行 pytest。Windows handle 路径和 POSIX 竞态用例仍须由 CI 动态验证。P2/P4/P5/P6 gate 均未通过，整体仍 **NOT READY FOR RELEASE**。详见审核报告 §250。

**§248 P2 layer security-descriptor readback（2026-10-12）：** native reader 现在在同一只读 transaction 内调用 `FwpmLayerGetSecurityInfoByKey0`，将 layer owner/group/DACL 规范化结果附加到 `LayerSnapshot`。读取失败或 descriptor 无法规范化会保留 incomplete issue；成功读取仍标为 `SecurityDescriptorPolicyUnverified`，等待批准的 service ACL policy comparison。Native reader harness **32/32**、pinned .NET 10.0.401 x64 Release build **0 warnings/errors**、reader 与 harness format check 通过，完整 .NET build BOM 已重新生成。只有离线 fake API 证据；没有 live BFE/WFP/Firewall 操作。全对象可见性、批准 ACL 基线、生产 store/apply/readback/rollback、service wiring 和 live isolation 仍开放，P2 继续 fail closed。详见审核报告 §248。

**§246 全工作树安全扫描未启动（2026-10-12）：** Codex Security Deep Scan 要求 managed filesystem permission profile；当前会话无法提供，发现 worker 未启动，没有报告或 findings 数量。不能解释为全仓无发现。§234 的 111/111 源码/配置 Diff Scan coverage 仍为 partial，且早于 §245；须在支持 managed profile 的执行上下文对当前未提交树重新扫描。详情见审核报告 §246。

**§245 P2 layer/default-sublayer 与 provider 引用闭包（2026-10-12）：** native reader 在同一只读 transaction 中枚举 `FWPM_LAYER0`，按 layer 的 `defaultSubLayerKey` 解析空 filter sublayer key，并闭合 filter→layer/sublayer 与四类对象→provider refs；缺少/重复目标报告为此次读取未解析，不武断认定 dangling。Native fixture **31/31**、Runtime fake-store **15/15**、pinned .NET Release builds **0 warnings/errors**、四个 format check 和完整 BOM 更新通过。以上均为离线证据；layer ACL policy comparison、read ACL 下全对象可见性、生产 store/wiring/live BFE 仍未完成。P2 继续 fail closed。详见审核报告 §245。

**§244 Windows Python 3.11.15 当前树全量回归（2026-10-12）：** 当前工作树 **664 passed、30 skipped、0 failed**（165.99 秒）。跳过项受 native interop host 配置、Windows symlink 权限和 POSIX 专属行为限制。结果不替代 live WFP/P2、P4 听审、P5 Desktop 或 P6 远端验收。详见审核报告 §244。

**§243 P2 provider-context 引用闭包与 inspection callout 修正（2026-10-12）：** reader 在同一只读 transaction 枚举 provider-context 并闭合 filter context key；支持 general blob 与有界 classify-options lifetime values。官方 Microsoft 样例证明 `FWP_ACTION_CALLOUT_INSPECTION` 可合法引用 provider context，已修正 decoder 并加入 fixture。Native harness **25/25**、Runtime harness **15/15**、pinned SDK Release build **0 warnings/errors**、格式与完整 BOM 检查通过。对象 ACL policy comparison、隐藏对象可见性、未实现的 IPsec union、生产 store/接线/live BFE 仍开放，P2 未通过。详见审核报告 §243。

**§242 P6 Windows PE 导入名称分类（2026-10-12）：** 基于当前锁文件与 419/419 RECORD verified 的 Windows PE 清单生成 2,654 行分类边图，区分 API-set 前缀、显式 system-DLL 名称、同/跨制品候选、歧义及未解析项；新 evidence SHA-256 为 `e026eef783bce270fc26f65e52bed80db6af66d63f4cc13628ac493238d1d5a9`，旧边图未覆盖。定向测试 **26 passed**，Ruff check/format 通过。名称和清单仅形成候选，不证明 loader 选择、共安装、动态链接或许可适用性；P6 owner/license/provenance/remote gates 仍开放。详见审核报告 §242。
**§241 P4 三段附件身份复核（2026-10-12）：** 用户提交的三段 WAV 与既有听审包的 SHA-256 身份匹配，均为 18 秒、16 kHz、单声道、16-bit PCM。当前环境没有音频感知能力，因此这只确认附件身份，不构成声学听审；没有重跑 ASR、读取逐字稿正文或修改 raw/reviewed 文件。P4 的至少三段声学对照与 fresh Desktop 数据流/隐私验收仍开放；P2/P5/P6 也未通过，项目仍 **NOT READY**。详见审核报告 §241。

**§240 P2 native callout readback（2026-10-12；provider-context 引用随后于 §243 闭合）：** reader 在只读事务中分页枚举 callout，并读取 owner/group/DACL descriptor；完成枚举后验证 filter callout key 唯一存在且 applicable layer 与 filter layer 相符。native unmanaged harness **18/18**、Runtime fake-store harness **15/15**，固定 .NET SDK 10.0.401 x64 Release build **0 warnings、0 errors**；完整 build BOM 已重生成。验证仅来自离线 fake API。descriptor policy comparison、对象级 ACL 下的完整可见性、production store 与 live BFE 验收仍未完成；P2 继续 fail closed。详见审核报告 §240。

**§239 Windows Python 3.11.15 全量回归（2026-10-12）：** 当前工作树完整套件 **660 passed、30 skipped、0 failed**（166.08 秒）。这次运行晚于 §235 敏感文件扫描器改动；跳过项受 POSIX 行为、Windows symlink 权限和未配置 native interop 环境限制。结果不改变 P2/P4/P5/P6 gate，项目仍 **NOT READY FOR RELEASE**。详见审核报告 §239。

**§238 P2 native security-descriptor readback（2026-10-12）：** reader 现在在只读 transaction 内请求 provider/sublayer/filter 的 owner/group/DACL；根据 Microsoft WFP 文档，BFE 忽略 SACL ACE，因此不请求 SACL。对自相对描述符进行长度限制和规范化，拒绝非规范 DACL，保存 SDDL/hash 元数据，并在成功与失败路径释放 WFP 分配。native unmanaged fixture harness **14/14**、Runtime harness **15/15**、pinned .NET SDK 10.0.401 x64 Release build **0 warnings、0 errors**、格式检查和完整 build BOM 重生成均通过。此结果仅来自离线 fixture：descriptor policy comparison 和服务枚举覆盖仍未证明，引用对象未枚举，也没有生产 store 或 live BFE 验收。P2 继续 fail closed。详见审核报告 §238。

**§237 P2 native effectiveWeight 标量校验（2026-10-12）：** reader 现在只接受有效 `FWP_UINT64` 的 BFE `effectiveWeight`；错误 tag/null 指针保留 incomplete issue。Pinned .NET SDK 10.0.401 x64 Release build **0 warnings、0 errors**，无 BFE/WFP 的 unmanaged harness **10/10**，格式检查通过，build BOM 已重生成。该字段修复不解决对象 ACL/security descriptor、权限导致的枚举盲区、引用对象或生产 store/apply/readback/rollback 接线；P2 仍 fail closed。没有触碰宿主策略。详见审核报告 §237。

**§236 P4 片段接收与 P6 SPDX 字节重放（2026-10-12）：** 用户补交三段现有 WAV；执行环境没有音频感知接口，因此没有宣称完成听审，也未重跑 ASR、读取逐字稿或修改 raw/reviewed 文件。既有 ASR 候选仅供复听定位，P4 仍未通过。对现有私有 SHA-256 cache 运行离线 SPDX verifier，通过 41 packages、210 artifacts、41 metadata、9 license、2 notice、1,149 supplemental members；这只核验字节和元数据，不能证明许可、来源、native 链接或分发适用性。完整 P6 owner/生成输出/远端验收、P2 生产隔离、P5 fresh Desktop trace 与完整安全复核仍开放。没有改代码、安装依赖或触碰宿主策略。详见审核报告 §236。

**§235 文档、测试夹具与隐私复审（2026-10-12）：** 修复审计报告中两处本机 .NET SDK 账户路径和 `MEMORY.md` 中一处用户媒体完整路径；定向检索测试、fixtures 与结构化 SPDX/BOM/PE 证据，未发现真实转写正文、凭据或其它个人路径。敏感文件扫描器新增 Windows 用户目录路径检测；定向回归 **19 passed、1 skipped**，仓库扫描通过。核对私有听审 manifest 元数据后，确认四段剪辑当前均保存精确起止时间，纠正了“片段偏移仍未记录”的过期摘要。发布摘要、安全报告、README、变更日志、owner/remediation/implementation 计划和 MEMORY 已同步到 §235。§234 安全差异扫描已封存 111/111 源码/配置项、0 findings，但覆盖 partial、机器 receipt 未完全解析；不能视作完整仓库安全审核。此轮未运行全套测试或修改宿主策略。P2/P4/P5/P6 仍未通过。详见审核报告 §235。

**§232 P2 native readback adapter、P4 本地模型交叉检查与回归（2026-10-12）：** Runtime 增加对 native readback snapshot 的适配，保留 canonical native projection，并在任何 mutation 前拒绝 incomplete 或 API failure；Runtime fake-store harness **15/15**，native reader fixture harness **9/9**，锁定 .NET SDK 10.0.401 x64 Release build **0 warnings/0 errors**。Reader 仍因对象 ACL/security descriptor 与 effectiveWeight 语义未规范化而始终标为 incomplete，且没有具体 `IWfpPolicyStore` 使用该 adapter；CaptureService 保持 fail closed，P2 未通过。四段私有音频片段用本地 balanced ASR 复跑并和绑定校对稿比较，仅生成候选提示，不是听音验证；raw/reviewed 文稿未改。Windows Python 3.11.15 全套 **653 passed、30 skipped（263.33 秒）**；Ruff、format、lock、敏感文件、Skill validator、.NET format、BOM generator 与 diff check 通过。至少三段人工对照和 fresh Desktop 隐私/数据流验收仍开放。详见审核报告 §232。

**§231 P6 NuGet 锁定摘要语义复核（2026-10-12）：** 从官方 NuGet v3 source 在新的临时 package/HTTP cache 中对 WFP plan 执行 `--locked-mode --force` restore，四个精确锁定包全部成功。每个 lock `contentHash` 与新缓存 `.nupkg.metadata` 一致；完整签名归档 SHA-512 与 `.nupkg.sha512` sidecar 一致。NuGet 将 lock contentHash 定义为排除签名元数据的包内容摘要，因此原始签名归档 SHA-512 不同是预期现象；四包 `dotnet nuget verify --all` 全部通过。§228 原始哈希观察保留为历史事实，不再视为 lock mismatch。已知 94 项 SHA-keyed SPDX cache 的离线 verifier 在缺少 hash `001ed726c9bd5e2bc92faade7d37d889e9606a350b7d5529f0227df2e3bb57fd` 时失败；未扫描整盘或下载其余制品。P6 的完整 SPDX replay、发行/许可证 owner decision、Win32Docs 与 SDK/WDK 对生成输出的适用性、完整 native provenance/linkage/notice、远端 CI 和 clean install 仍开放。详见审核报告 §231 和 [DOTNET_BUILD_DEPENDENCY_REVIEW.md](DOTNET_BUILD_DEPENDENCY_REVIEW.md)。

**§230 P2 只读 native WFP 快照原型（2026-10-12）：** 新增独立 reader，通过只读 transaction 分页枚举 provider/sublayer/filter；不支持值、异常清理和边界问题均 fail closed，DTO 不可由公开调用方注入可变集合。Pinned .NET SDK 10.0.401 reader/fixture Release build 均 **0 warnings/0 errors**，unmanaged fake-API harness **8/8**，CI 已纳入 locked restore、format、build 和 harness。BOM 仅做 inventory-only 更新（11 inputs、45 generated bindings、10 Release outputs），未跑完整 BOM generator、远端 CI 或 NuGet archive verifier。reader 没有接入 Runtime/CaptureService，不读取 ACL/security descriptor、不规范化 effectiveWeight，且没有 live BFE/WFP 验证。§230 当时使用既有 cache 的 restore 未核验归档摘要；§231 已从官方 source 在隔离 cache 完成 NuGet lock-contentHash 语义复核。P2 仍 **NOT PASSED**。本轮 P4 提交路径对应 15:38.968 AAC 音频、无视频流，满足时长门槛，但人工听审与 Desktop 隐私验收仍开放。详见审核报告 §230。

**§229 P4 默认模型校对可验证性审核（2026-10-12）：** Skill 要求默认模型校对，CLI 则明确只产出 raw ASR；侧车能绑定原稿哈希，但不证明模型身份/听音/质量。CLI 可能在侧车已保存但未登记任务时仍返回保存状态，因此宿主编排交付前必须检查 `task_binding=registered`。如需强制产品门槛，应由宿主提供可信回执和独立最终接受状态，不信任调用方自报模型名。格式标点检查不代表语义正确。此项为只读审核，无代码或测试变更；人工听审与 Desktop 隐私验收仍开放。详见审核报告 §229。

**§228 P6 缓存身份复核（2026-10-12，NuGet 解释已由 §231 更正）：** verifier 清单要求的 210 个 SPDX 制品在默认 uv cache 的平铺路径命中 0/210；缓存本身分层，未检查其它路径或整盘。WFP prototype 的 4 个默认 NuGet 缓存 `.nupkg` 原始 SHA-512 确实均与锁的 `contentHash` 不同，且 sidecar 与原始归档字节匹配；§231 通过全新 locked restore 证实这是签名归档 SHA-512 与排除签名元数据的 lock contentHash 口径差异，不是包/lock mismatch。已知 94 项私有 SHA-keyed SPDX cache 仍不足以重放 210 项 evidence；未扫描整盘、未下载其余制品。P2/P4/P5/P6 及完整安全审核未闭合，整体仍 **NOT READY**。详见审核报告 §§228、231。

**§227 P4 样本身份和试听材料复核（2026-10-12）：** 用户补充的长样本路径存在，文件大小 22,715,944 字节，当前 SHA-256 与私有试听 manifest 的源文件摘要一致；manifest 记载 938.968435 秒、双声道 AAC、无视频轨。raw/timeline/reviewed sidecar 映射未变，四段 WAV hash 仍 4/4 一致。未重跑 ASR、读取正文或覆盖文件。试听片段没有精确起止秒数；至少三段人工对照记录及 fresh Desktop 数据流/隐私验收仍开放。整体 **NOT READY**。详见审核报告 §227。

**§226 WFP readback projection v1（2026-10-12）：** managed schema v1 现在要求 provider/sublayer/filter projection 完整、受支持且字段闭世界精确匹配；fake-store harness **12/12**、锁定 .NET SDK 10.0.401 Release/x64 build **0 warnings/0 errors**、格式校验和定向 BOM **9/9** 通过，BOM 纳入 14 个 Runtime source inputs、17 个 outputs。此 projection 不是 `FWPM_*0` 原生解码；对象 ACL/security descriptor、BFE effectiveWeight、真实枚举/事务/backend 和生产接线均未完成，P2 仍 **NOT PASSED**。详见审核报告 §226。

**§220 纯托管 WFP 规则核心边界与当前 P4 样本核验（2026-10-12）：** 将 `LeasePolicyCompiler` 和规则 DTO 拆入无 CsWin32/WFP 调用的 `WfpPolicy.Core` 类库，预览 CLI 经项目引用使用；未接入生产 service，默认捕获仍 fail closed。锁定 restore、Release/win-x64 构建（0 warnings/0 errors）、WFP harness **14/14**、三项目格式检查通过；构建 BOM 更新为 14 个源输入、4 个 NuGet 包、38 个生成源码、7 个输出，定向 BOM 测试 **7 passed**。用户提供路径与既有 938.968435 秒音频样本一致，未重跑 ASR；P4 人工听审及 fresh Desktop 数据流隐私验收仍开放。P2 生产 coordinator、apply/readback/rollback、Job Object、Sandbox/真实捕获，P5 trace、P6 owner/远端发布门槛和完整安全扫描均未关闭。整体仍 **NOT READY**。详见审核报告 §220。

**§218 P2 baseline 与 lease 组合约束及 fail-closed 服务启动（2026-10-12）：** 新增 service-wide policy compiler，要求每个动态 lease 的 browser/worker AppID 分别出现在对应角色的持久基线；materializer 收为程序集内部，并严格验证 loopback、公共 DNS:53 和公共 TCP:443 permits 及完整 lease 规则组。新增错配 AppID、私网 DNS 和任意端口拒绝回归，WFP harness **14/14 passed**。capture-pipe 启动必须先经过 baseline readiness gate，再创建管道和报告 RUNNING；默认 gate 因生产 WFP coordinator 缺失而失败关闭，生命周期 harness 与完整 capture-pipe self-test 通过。三个 .NET 项目格式校验通过。未调用 BFE/WFP、未改宿主策略；生产 coordinator、事务/读回/回滚、Job Object、Sandbox 动态验收和真实捕获仍未完成，P2 继续 **NOT PASSED**。Python 全套本轮未重跑，最新 646/30 仍是 §217 结果。详见审核报告 §218。

**§217 全套回归、P2 生命周期修订与 P6 构建 BOM（2026-10-12）：** 锁定 Windows Python 3.11.15 全套 **646 passed、30 skipped（260.76 秒）**；Ruff、format、lock、Skill validator、敏感文件和 pinned SPDX schema 检查通过。WFP non-deployable preview 现只将 AppID catch-all 标为 persistent；临时 lease SID deny、listener block 和 permits 归入 dynamic session，native 离线 harness **11/11 passed**。这只是语义预览修正；需先实现 fixed protected AppID baseline、Job Object kill-on-close、runtime coordinator/readback/rollback 和 BFE/Sandbox 验收，再考虑接线。P6 生成单独 win-x64 本机构建 BOM，记录 11 个源输入、4 包、38 个生成文件和 5 个输出；不证明清洁构建可复现或许可适用。完整 SPDX verifier 仍缺已知缓存制品，Deep Scan 未启动且旧扫描仍 partial。P4 人工听审/Desktop、P5 fresh Desktop trace、P2 生产隔离/真实捕获、P6 owner/远端发布决定仍开放。详见审核报告 §217。

**§216 全套回归、P2 生命周期设计门槛与 P6 SPDX 复核（2026-10-12）：** 修正三项仍期待旧 Sandbox/WFP 写入口运行的清理测试，改为确认 fail-closed stub 在副作用前拒绝；定向 **7 passed**，锁定 Windows Python 3.11.15 全套 **641 passed、30 skipped（258.73 秒）**。Ruff、format、锁、Skill validator、敏感文件和 pinned SPDX schema 检查通过。WFP preview 把每 lease 的 principal catch-all deny 标为 persistent；接线前需固定 provider/sublayer 所有权、精确读回/清理陈旧 lease 规则，并证明 Chromium 子进程、worker、listener 和 socket 已终止后再删除持久 deny；当前无 apply 路径，P2 继续 fail closed。已知 94 项缓存缺少完整 verifier 所需文件，完整 SPDX 字节验证未能重放；未扫描整盘，也未完成 Deep Scan。P4 人工听审/Desktop、P5 fresh Desktop trace、P2 生产隔离/真实捕获、P6 owner/远端发布决定仍开放。详见审核报告 §216。

**§215 P4 长样本重复提交路径核验（2026-10-12）：** 用户再次提供的本机 MP4 与既有 P4 样本一致；只读核验为 22,715,944 字节、938.968435 秒、双声道 AAC 且无视频轨。复用已有 ASR、默认模型文本校对侧车、timeline 和四段私有试听片段，没有重跑转写或读取逐字稿正文。至少三段人工听审和 fresh Desktop 数据流/隐私验收仍开放；P2/P5/P6 仍有发布阻断项。详见审核报告 §215。

**§214 P2/P6 当前状态校正（2026-10-12）：** P2 已有未安装的 SCM/named-pipe 服务源码原型，但生产工厂仍注入 `FailClosedCaptureWorker`，逐租约 worker、生产 WFP permits/apply/rollback、浏览器树监督和 installer 均未完成。一个可见临时 cache 有 94 个制品，不足以重放完整清单引用的 210 制品 verifier；没有证明其他 cache 不存在。Deep Scan 因缺少 managed filesystem permission profile 未启动，没有新增 scan result。整体仍 **NOT READY**。详见审核报告 §214。

**§213 `review-sidecar` TTY 快速拒绝（2026-10-12）：** 正文接口需要结构化 JSON stdin；若误从交互终端启动，原实现会等待 EOF。现在先检查 `isatty()` 并立即返回清晰错误，不触碰正文。定向 `test_cli.py -k review_sidecar` **6 passed、81 deselected**，Ruff check/format 与 diff-check 通过；全套测试未重跑。该可用性修复不关闭 P2/P4/P5/P6 外部验收。详见审核报告 §213。

**§211 CONNECT DNS 许可前置、地址回退与 WFP smoke 停用（2026-10-12）：** `NumericDnsQuestioner` 强制注入 lease DNS permit provider，UDP/TCP 各自先许可后建 socket、关闭 socket 后撤销 permit；CONNECT 最多回退 4 个已验证 pin。C# BFE 直达写入口和 host wrapper 已在任何 bootstrap/WFP/Sandbox side effect 前拒绝；`ScopedNetworkWfpSmoke.ps1`、`UserSidChromiumSmoke.ps1` 和 AppContainer 默认 WFP 模式也在加载写入代码前停止。使用锁定 .NET SDK 10.0.401 的两个 Release x64 build 均 0 warning/0 error，capture-pipe self-test 通过，WFP 离线 harness **11/11 passed**，格式检查通过。没有动态 WFP/Sandbox 验证或生产 provider，P2 仍 NOT PASSED。详见审核报告 §211。

**§210 当前审查与 dry-run readiness 修复（2026-10-12）：** URL 语法有效不再被等同于捕获可用；未注册 broker 时 dry-run 显示 `capture_unavailable` / `needs_attention`。定向回归 **5 passed、81 deselected**。同轮只读审查发现 SYSTEM BFE 测试入口未证明 Windows Sandbox 身份，以及 CONNECT DNS 缺逐 lease permit；建议先停用可信 guest 边界未成立的 BFE 写入口，按 resolver IP/协议/53 端口取得并回收 DNS permits，并在有界 deadline 内尝试同一已校验 IP 集合。P2/P4/P5/P6 仍开放；详情见审核报告 §210。

**§209 P6 NuGet 签名本机核验（2026-10-12）：** 四个 WFP build-only 锁定 `.nupkg` 均通过 `dotnet nuget verify --all`，验证器识别 author/repository 签名且 contentHash 与 lockfile 对应。该项关闭本地包签名核验缺口，不关闭 Win32Docs 条款/生成输出适用性审查、许可证和发行范围所有者决定、独立下载、远端 CI 或 clean install。详见审核报告 §209 与 [DOTNET_BUILD_DEPENDENCY_REVIEW.md](DOTNET_BUILD_DEPENDENCY_REVIEW.md)。

**§208 native HTTPS CONNECT 离线源码切片（2026-10-12）：** 增加未注册、有界 CONNECT relay 与 fake-backed harness；Pinned .NET 10.0.401 build、capture-pipe self-test、format verify 通过。没有 listener/对端认证、DNS permit、逐租约并发、生产 worker/WFP 接线或真实网络验证；P2 继续 OPEN / NOT PASSED。详见审核报告 §208。

**§207 当前完整 Python 回归（2026-10-12）：** 锁定 Windows Python 3.11.15 全套 **638 passed、30 skipped（256.93 秒）**。P4 长音频及默认模型文本校对门槛已满足；仍待至少三处人工听审差异记录和 fresh Desktop 数据流/隐私验收。整体仍 **NOT READY**。详见审核报告 §207。

**§204 当前工作树全套回归（2026-10-12）：** 锁定 Windows Python 3.11.15 全套 **636 passed、30 skipped（255.06 秒）**；两个 native interop 因宿主路径未配置跳过，其余为 Windows 缺少的 POSIX/FIFO/symlink 能力。CI 范围 Ruff、锁文件、clean-copy Skill 安装、canonical/`.codex` Skill validator、敏感文件扫描和 SPDX 2.3 schema 验证通过。没有执行 Sandbox/BFE/WFP 或远端矩阵，不能据此关闭 P2。详见审核报告 §204。

**§203 BFE Sandbox wrapper 结果目录加固（2026-10-12）：** 移除任意 `ResultsDirectory` 参数，将 Sandbox guest 的可写结果 share 固定到专用目录，并拒绝重解析点。PowerShell AST 解析和 `git diff --check` 通过；没有执行 Sandbox/BFE 或项目测试。此项只收紧测试工具的 host-share 边界，不实现产品隔离。详见审核报告 §203。

**§202 AUD-130 WFP 探针代码级停用（2026-10-12）：** 将有全局 IPv4 block 能力的 `NetworkWfpWriteSmoke.ps1` 实现替换为立即抛错的 fail-closed stub，避免旧 Sandbox profile 误触发。PowerShell AST parse 与 `git diff --check` 通过；未运行脚本、Sandbox 或 BFE。该修复不验证新的 C# BFE probe，也不关闭 P2。详见审核报告 §202。

**§201 当前工作树安全审阅补充（2026-10-12）：** 发现一个仅在管理员手动运行 WFP 诊断脚本时触发的低风险操作隐患：Sandbox 外运行可能暂时阻断主机 IPv4 connect。对策是停用全局无条件阻断探针，或将规则收窄至专用测试进程，并只在新建可销毁 Sandbox 动态验收。扫描仍未封存（12/93 审阅项），不代表全量安全审查通过；P2/P4/P5/P6 门槛保持开放。详见审核报告 §201。

**§199 P6 .NET 构建期依赖审查（2026-10-12，历史状态）：** 当时独立盘点 WFP policy-plan 的 4 个 NuGet 构建期依赖并核对 lock/cache 元数据与包 SHA-512 sidecar；capture-pipe 无 PackageReference。§209 后续已完成四个精确缓存包的本机签名核验。Win32Docs 条款、SDK/WDK 条款对生成输出的适用范围仍未闭合；没有 restore、执行包代码或扩展应用 SBOM。整体保持 **NOT READY**。

**§198 P4 长样本路径复核与报告隐私脱敏（2026-10-12）：** 用户本次给出的路径对应 §196 已审计的 938.968435 秒 AAC 音频样本，已有 ASR、默认模型校对侧车和时间轴，本轮不重复转写。长音频门槛满足；人工听审和 fresh Desktop 数据流/隐私验收仍开放。已将三份历史报告中的本机设备/账户标识改为通用角色描述；未改动系统账户、Sandbox 或网络策略。项目仍 **NOT READY**。详见审核报告 §198。

**§197 P2 BFE 探针静态缺陷与 P5 干净副本安装（2026-10-12）：** §195 探针将 `S-1-5-18` 作为 `UserSid`，而 `LeasePolicyCompiler` 只接受非内置普通用户 SID，因此在打开 BFE 前就会失败；后续连接也由 SYSTEM 当前进程发起，不能验证真实 lease 身份或隔离。对策是在一次性 guest 创建两个普通账户，取得真实 SID，由对应 token 启动不同路径的 browser/worker helper，再验证互相隔离、精确许可、BFE 读回和清理。锁定 Skill 的干净副本安装冒烟已通过，但不替代远端安装或 Desktop 新会话验收。Windows Python 3.11.15 全套 **636 passed、30 skipped（255.59 秒）**；2 项 native interop 因未配置宿主路径跳过，其余为平台能力限制。项目保持 **NOT READY**。详见审核报告 §197。

**§196 P4 长样本模型校对侧车（2026-10-12）：** 用户新给路径对应已有完成任务；锁定 PyAV 确认 938.968435 秒、双声道 AAC、无视频轨。本轮不重复 ASR；当前 Agent 默认模型对 `__2.md` 正文做文本校对并由 helper 新建 `.reviewed.md`，raw mtime 未变。长音频 ASR/模型文本校对通过，但四段剪辑至少三处人工听审差异记录、fresh Desktop 数据流/隐私验收仍开放；无视频轨和 A/V 同步结论。详见审核报告 §196。

**§195 C# materializer→BFE 探针与 Sandbox 运行阻塞（2026-10-12）：** 实现 test-only synchronous native-filter visitor、CsWin32 BFE API 绑定、一租约 actual-filter readback/traffic/cleanup 探针，以及创建并在 `finally` 销毁独立 Sandbox 的 wrapper。Release build 0 warning/error、离线 harness 10/10、self-contained publish、host SYSTEM/token guard 和 format verify 通过。真实 probe 未执行：已有 Sandbox 占用 Windows launcher，`wsb start` 返回 `CO_E_APPSINGLEUSE`；没有触碰既有 guest 或 host WFP。待现有 Sandbox 关闭后在新 guest 验收，详情见审核报告 §195。

**§194 WFP IPv4 主机序修复（2026-10-12）：** materializer 之前把 IPv4 地址字节按小端解释，且快照用同一转换反向呈现，导致自检掩盖了 native `FWP_UINT32` 值错误。现转换为 WFP 主机序整数，快照公开 raw 值，harness 断言 `127.0.0.1 → 0x7F000001` 和 `93.184.216.34 → 0x5DB8D822`。Pinned .NET SDK 10.0.401 Release 构建 **0 warning / 0 error**，native materializer harness **10/10**，format verify 通过。未打开 BFE 或更改 Sandbox/宿主策略。下一步必须把 C# 物化结果提交到新的可销毁 Sandbox BFE，验证地址匹配和 dynamic-session 清理，再扩展多租约和失败回滚；P2 仍 OPEN / NOT PASSED。详情见审核报告 §194。

**§193 P6 审计工具回归（2026-10-12）：** metadata audit 与 NumPy inventory 新增 ZIP 预检先于 `ZipFile`、超大 RECORD 在读取前拒绝、CLI 终端控制符转义用例。相关测试 **41 passed、2 POSIX-only skipped**；Ruff、格式和 diff 检查通过。没有重跑全套、Deep Scan 或远端安装。P6 owner 许可证/发行决定、原生组件来源/notice、远端 CI 和干净安装仍开放。详情见审核报告 §193。

**§192 P2 生产集成缺口审查（2026-10-12）：** 复核确认 URL 工厂仍使用安全失败 worker，WFP materializer 只创建内存预览，Sandbox smoke 与 C# 物化器还没有数据/执行路径连接。对策是先在新建可销毁 Windows Sandbox 中建立 C# 规则到实际 BFE filters 的 runtime consistency harness，覆盖双租约互隔、精确许可、默认拒绝和清理/回滚；通过后再推进 service、worker、CLI 和三条真实捕获。此次仅源码审查，没有运行 harness 或修改宿主网络策略。P2 继续 OPEN / NOT PASSED，详情见审核报告 §192。

**§191 sdist 元数据审核器加固（2026-10-12）：** `verify_locked_wheel_metadata_audit.py` 不再直接让 `tarfile` 解压 gzip；它经带总解压字节预算和读取期限的 `_BoundedDecompressedReader` 处理后再解析 tar/PAX。3 项新增回归覆盖正常元数据、PAX 头超限和 deadline 拒绝；与相邻审计器用例合计 **39 passed、2 skipped**。Ruff、敏感文件扫描和 whitespace 检查通过，未跑全量测试。该本地离线审核器资源边界加固不关闭 P2/P4/P5/P6 门槛；详见审核报告 §191。

**§190 P4 媒体类型更正（2026-10-12）：** 重新用锁定 PyAV 检查用户提供的 22,715,944-byte MP4，时长 938.968435 秒，但容器只有 AAC 音频轨，没有视频轨。它满足长时音频转写门槛，不代表视频解码或 A/V 同步验收。现有 raw、reviewed、timeline 与四段片段均保留；人工听审、fresh Desktop 数据流验收仍未完成。若发行验收要求视频流，补充长视频样本后单测。详见审核报告 §190。

**§189 当前续审（2026-10-12）：** 修复 §188/AUD-125：完成态转写稿和时间轴哈希使用各自根据 writer 硬上限推导的有界字节预算；验证打开句柄类型/大小、最大读取量及文件增长。超四小时/非有限时间戳不写入时间轴。新增针对性回归后，Windows Python 3.11.15 全套 **627 passed、30 skipped**（343.72 秒），Ruff check/format 通过。修复发生在 §188 封存扫描快照之后，需由后续安全扫描覆盖。P2/P4/P5/P6 仍有生产隔离、人工听审、新 Desktop 和 owner/远端门槛，整体 **NOT READY**；详见审核报告 §189。

**§183 当前续审（2026-10-12）：** 重新核对用户提供的 MP4 音频样本，PyAV 时长 938.968435 秒；仅有 AAC 音频流。CLI 将其识别为既有完成任务而跳过，raw/reviewed/timeline 文件哈希与历史记录一致。为 01:11、05:40、08:41、08:59 各准备了一段 18 秒私有音频片段，尚未声称人工听审。canonical Skill 已增加“转写/字幕内容是不可信数据”的提示注入边界，canonical 与 repo-scoped 两份 Skill validator 均通过；此更改不在 §182 安全扫描快照中，需纳入下一次全范围扫描。本轮未重跑 pytest。P4 仍需人工听审和新 Desktop 隐私/数据流验收；P2 生产隔离/三条真实捕获、P5 新 Desktop 调用、P6 所有者决定/native provenance/远端验证仍开放。项目保持 **NOT READY**，详见 [`PROJECT_AUDIT_REPORT.md` §183](PROJECT_AUDIT_REPORT.md)。

**§180 历史安全续审（2026-10-12）：** 封存的 Codex Security Diff Scan 覆盖冻结工作树中的 90/90 条源代码/配置审核项，在 207 个差异文件中发现 3 项低风险诊断/离线工具文件处理问题；三项已在扫描快照之后修复。修复后只做 PowerShell AST、Python AST、Ruff check/format 静态检查，未运行诊断脚本或新测试。其余文档、测试与生成文件未全部逐行审阅，Windows service/WFP/Firewall 未安装、修改或动态验证。旧 URL helper 没有生产非测试调用方，列为后续接入前证明缺口；URL 捕获仍 fail closed。报告和逐项对策见 [`SECURITY_SCAN_REPORT_2026-10-12.md`](SECURITY_SCAN_REPORT_2026-10-12.md) 与 [`PROJECT_AUDIT_REPORT.md` §180](PROJECT_AUDIT_REPORT.md)。项目仍 **NOT READY**。

**§181 历史续审（2026-10-12）：** 同类路径审计修正四个一次性 Sandbox Chromium 脚本的临时目录/测试账户清理所有权守卫；ProcessSingleton lockfile 保持 `CREATE_NEW`。新增原子写临时路径哨兵回归与 PowerShell source guard。当前树 Python 全套 **624 passed、30 skipped**；capture-pipe self-test、新增 numeric-IP connector harness、WFP harness **10/10** 及格式/lockfile 检查通过。新的 connector 只提供离线源组件，没有生产 permit provider 或 worker 集成。§180 扫描 coverage remains partial，扫描后的 §181 更改未纳入新封存扫描。整体继续 **NOT READY**，详见 [`PROJECT_AUDIT_REPORT.md` §181](PROJECT_AUDIT_REPORT.md)。

**§179 历史增补（2026-10-12）：** §176 的 938.968435 秒 P4 样本已通过 `--timestamps --force` 生成另存的 533 点时间轴侧车（00:00–15:37，单调递增），并给出 01:11、05:40、08:41、08:59 四个主题复听位置；原稿未覆盖，正文未复制进报告。时间轴只辅助人工复听，不能替代人工判断。§178 的 capture-pipe / WFP harness、Python 618/29 回归和静态 checks 结果仍有效。P2 service/per-lease worker/真实捕获、P4 人工听审/fresh Desktop 数据流、P5 新 Desktop trace、P6 所有者发行决定及远端验收仍未完成。整体仍 **NOT READY**；详情见 [`PROJECT_AUDIT_REPORT.md` §§177–179](PROJECT_AUDIT_REPORT.md)。

**§161 P6 补充：** 更正后的归档成员清单覆盖 235/235 个锁定制品（86,827 个成员行、6,239 个名称/路径候选行）；修复 50 个 ZIP 文件类型误分类。精确对账得到 286 个未绑定普通文件候选，已全部哈希并加入 SPDX 的字节身份补充证据；verifier 为 41 packages、210 artifacts、1,149 supplemental members，SBOM 与 schema 校验通过。旧 §160 的 297 是粗略对账误差。该补充不作许可证适用性结论，native provenance/link map、所有者发行范围决定和远端验收仍待完成。

**§165 native DNS 校验切片：** capture-pipe 增加注入式、离线可测的 A/AAAA/CNAME 响应校验；限制解析跳数、查询数、答案量和总时限，拒绝私网/保留地址、环、截断及问题不匹配。capture-pipe 与 WFP 计划器共用公网地址规则。这还没有真实 DNS 传输/解析器、upstream connector、service 或 per-lease worker，默认 capture 仍 fail closed；不能当作 P2 生产隔离通过。

**§166 P6 native import map 扩围：** PE 清点器覆盖当前锁定的 40/40 Windows wheel（win32、win_amd64、win_arm64），得到 419 个 PE 成员和 2,654 项直接导入，与完整成员索引 419/419 对账。原 416/3 RECORD 计数是路径分隔符误报；§172 规范化 Windows RECORD 路径后 419/419 验证通过。Playwright 的 win32 wheel 中发现 AMD64 `node.exe`，V1 捕获目标仍是 Windows 11 x64，32 位兼容性声明需保持关闭。此证据不证明运行时或静态链接、构建来源或许可适用性。

**§167 P2 DNS 测试补齐：** capture-pipe self-test 增至 14 个离线 DNS 场景，覆盖跨响应 CNAME、累计答案和地址 pin 上限、deadline、caller cancellation，以及无关私网 Answer 不污染可达公网结果；x64 Release build 为 0 warnings/0 errors。测试 fake 遵循取消 token；真实 transport、socket 关闭、connector 和 worker 仍未实现，因此 P2 仍未通过。验证器已修正全 Answer 私网地址导致误拒绝的问题，对所有记录保留结构与地址格式校验，只对查询名及可达 CNAME 链终点应用公网地址策略。

**§168 P2 DNS wire 切片：** capture-pipe 增加有界 DNS wire codec/numeric resolver questioner，校验事务 ID、响应问题、记录边界和压缩指针标签边界；UDP 截断回退 TCP，取消时关闭 UDP/TCP socket。仅使用 loopback fixture；TTL 按解析耗时扣减并封顶 300 秒，包含未计算 SOA negative TTL 的结果不可缓存。§169 增加 socket-handle closure 和 TTL/名称边界回归，native self-test 现为 18 个 policy 场景。无 DNSSEC/加密认证或完整 RRset 保证，也未连接 per-lease worker、numeric-IP upstream connector、服务或 WFP；默认捕获仍 fail closed。

**§170 P6 PE import 候选边图：** 新增离线映射器，逐行验证 inventory 的包/版本/wheel/platform/artifact SHA 确实绑定当前 `uv.lock`，再只将同 artifact 内 basename 相同的 PE 文件标为候选。2,654 个导入 occurrence 中，266 个匹配、2,388 个未在同制品 PE inventory 匹配，0 歧义；重复导入和 8 个 delay import 保留。输出 `windows-pe-import-edges.jsonl` SHA-256 为 `fac1648ddee9333cff8025a7f7cd5a431be553dd778e840c884974f4ac2df29b`。未匹配不是“缺失依赖”，匹配不是运行时 loader/linkage 证明。定向 PE 组 21 passed，Ruff/py_compile 通过。

**§171 P6 wheel 元数据补证：** 新增离线脚本和 `locked-wheel-metadata-audit.json`，覆盖 CTranslate2 4.8.2 的 10 个锁定 wheel、Tokenizers 0.23.2 的 16 个锁定 wheel；wheel SHA-256/大小与 `uv.lock` 一致，26 个 METADATA 的包名/版本/摘要及 RECORD 中对应摘要/大小均通过。CTranslate2 元数据显示 `License: MIT`；Tokenizers wheel 的两个许可证字段均缺失。记录不推断许可证适用性、不更改 SPDX 字段，Tokenizers Rust 依赖与发行范围审查仍开放。JSON SHA-256：`b4b06ab0d6a9ab28087dd59b699e79c6a6c2ee23134e30ed24a269c97146c7a0`。

**历史验收快照（§171，2026-10-11；已由 §172 更新）：** Windows Python 3.11.15 全套 **617 passed、29 skipped**（94.35 秒）。当时报告的 RECORD 计数 416/3 是反斜杠路径误判，当前结果见下面的 §172。P2/P4/P5/P6 仍开放。

**当前验收快照（§179，2026-10-12）：** P6 元数据核验覆盖 235/235 个锁定制品（199 wheel、36 sdist）；PE inventory 为 419/419 RECORD verified，edge map 保留 2,654 项导入、266 项同制品候选、2,388 项清单内未匹配、0 歧义。Windows Python 3.11.15 全套 **618 passed、29 skipped**（163.66 秒）；capture-pipe 与 WFP 离线 harness 在安装 pinned SDK 后通过。P4 的 938.968435 秒长样本、模型校对侧车和 533 点时间轴定位均完成，仍缺人工听审与新 Desktop 数据流验收。P2 production service/worker/WFP/Chromium 隔离与真实三媒体验收、P5 新 Desktop 调用、P6 所有者决定/native provenance/notice/远端 CI/干净安装继续开放。整体 **NOT READY**。

| 项目 | 整改结果 | 当前证据 |
|---|---|---|
| SEC-30/33 显示控制字符 | 标题采集、任务存储/读取、文件名、Markdown、CLI 和 JSON 摘要清理 bidi 与 C0/C1 控制字符；未知 TOML limits 键也在 doctor 文本输出前清理。 | 第 47 节当时的 Windows Python 3.11.15 全套为 435 passed、20 skipped；第 51 节工作树快照为 459 passed、23 skipped；第 64–65 节历史快照中 Python 3.11/3.12 各为 477 passed、23 skipped；§80 历史快照为 495/23；§92 历史快照为 510/23；§100 历史全套为 520/23；§131 修复前最近一次全套见审核报告 §§128–129（Python 3.11/3.12 各 519/23）；§131 后未重跑全套。其他终端和 Markdown 查看器渲染未逐一验证。 |
| SEC-31 HLS 二级资源 | PyAV 打开本地媒体时传入拒绝二级资源的 `io_open` 回调；需要 HLS 分段的输入按设计拒绝。 | 锁定 PyAV 15.1.0 / FFmpeg libavformat 61.7.100 在 Windows 临时环境动态测试：loopback 子请求回调 1 次、服务请求 0 次、合成 1 秒 WAV 验证通过。Linux/macOS wheel 与更多媒体格式尚未测试。 |
| SEC-32 敏感文件扫描 | 无法检查的 Git 可见文件现在会失败关闭，不再静默当作通过。 | 本地扫描通过；脚本不是通用 secret scanner，也不扫描 Git 历史。 |
| DOC-16/17 用户文档 | 中英文指南已说明输出目录环境变量、优先级和资源限制。 | 本地静态复核完成。 |
| DOC-18/19 路径与扫描器文档 | 架构文档现在说明配置锚点和 Hugging Face 外部缓存；发布清单已对齐扫描器 fail-closed 行为。 | 本次审核后完成文档修正。 |
| DOC-20 输出路径隐私口径 | 仅向请求转写的操作者返回结果路径；转发给其他接收方前删除私人路径和个人信息。 | SECURITY、架构文档和 Skill 说明已统一；与实施计划的验收目标及 README 示例一致，未改变 CLI 行为。 |
| DOC-21 发布状态时序 | Release report 与审核报告首页已改用最新差异扫描和锁定 PyAV 15.1.0 动态验收结论，并把早期快照标为历史；实施计划拆分 SEC-15 的源码整改与平台验收。 | 与审核报告第 9–11 节和当前证据对齐；跨平台验收仍保持未完成。 |
| SEC-34 术语元数据最小化 | Markdown 归档改为 schema v2，仅保留规则集哈希、汇总匹配规则数和替换次数；完整规则留在受保护任务库用于重试。 | 定向回归通过；该修复时的 Windows Python 3.11/3.12 全套各 387 passed、20 skipped，随后快照为 424/20（第 45 节）；第 51 节历史快照为 459/23；第 64–65 节历史快照中 Python 3.11/3.12 各为 477/23；§80 历史快照为 495/23；§92 历史快照为 510/23；§100 历史全套为 520/23；§131 修复前最近一次全套见审核报告 §§128–129（Python 3.11/3.12 各 519/23）；§131 后未重跑全套。旧输出不会自动改写。 |
| DOC-22/23 与 CLI-01 | 配置锚点/数据目录说明对齐；实施计划示例标注虚构并改用占位值；显式空 data/output 路径现在作为输入错误拒绝。 | 文档静态复核及空路径参数化回归通过；`git diff --check` 通过。 |
| DOC-24 测试状态数字 | §64–65 的 Python 3.11/3.12 各 477 passed、23 skipped 是后续干净安装与进程崩溃测试编辑前的快照。§80 纳入 AUD-81–85 后是历史快照（495 passed、23 skipped）；§92 的 510/23 也是历史快照。 | §131 修复前最近一次双版本全套证据见审核报告 §§128–129：Windows Python 3.11.15 与隔离 Python 3.12.13 各 519 passed、23 skipped；最终发布提交、远端 CI 和跨平台矩阵仍需验证。 |
| AUD-71/72 浏览器捕获 | 元数据 locator 等待限制为 1 秒；单条 capture 的默认绝对 deadline 为 45 秒并覆盖导航、元数据和 route DNS 检查；调用 `Request.is_navigation_request()`，分别执行导航和子资源 host 策略。 | 捕获/代理/pipeline 定向回归 **53 passed, 1 skipped**，Ruff 通过。真实授权页面仍无媒体候选；13/14 资源主机在 allowlist 外，未在缺少归属和必要性证据时放行。 |
| CLI-02 doctor 无效输出路径诊断 | 显式空输出路径配置无效时，doctor 将输出状态标为 `unknown` 并跳过目标路径权限探测，避免回退检查当前工作目录。 | CLI-03 完成时的 Windows Python 3.11/3.12 快照为 387 passed、20 skipped；后续历史快照为 424/20（第 45 节），第 51 节历史快照为 459/23；第 64–65 节历史快照中 Python 3.11/3.12 各为 477/23；§80 历史快照为 495/23；§92 历史快照为 510/23；§100 历史全套为 520/23；§131 修复前最近一次全套见审核报告 §§128–129（Python 3.11/3.12 各 519/23）；§131 后未重跑全套，Ruff 通过。 |
| AUD-73 doctor 测试环境假设 | Windows UTF-8 CLI 测试不再假定 ASR/浏览器可选依赖缺失；检查 UTF-8 中文、合法 JSON 及退出码/doctor 状态一致。 | AUD-73 修复阶段 Windows Python 3.11.15/3.12.13 全套各 404 passed、20 skipped；后续历史快照为 424/20（第 45 节），第 51 节历史快照为 459/23；第 64–65 节历史快照中 Python 3.11/3.12 各为 477/23；§80 历史快照为 495/23；§92 历史快照为 510/23；§100 历史全套为 520/23；§131 修复前最近一次全套见审核报告 §§128–129（Python 3.11/3.12 各 519/23）；§131 后未重跑全套。 |
| AUD-74 多输出目录重试摘要 | `retry-failed` 恢复不同任务各自保存的目录；混合目录时 JSON `output_dir` 为 `null`，各 item 保留实际路径，文本摘要标记“多个目录”。 | 两个不同保存目录的回归用例和 CLI/pipeline 定向回归通过；该修复阶段完整套件各 404 passed、20 skipped，后续历史快照为 424/20（第 45 节），第 51 节历史快照为 459/23；第 64–65 节历史快照中 Python 3.11/3.12 各为 477/23；§80 历史快照为 495/23；§92 历史快照为 510/23；§100 历史全套为 520/23；§131 修复前最近一次全套见审核报告 §§128–129（Python 3.11/3.12 各 519/23）；§131 后未重跑全套。 |
| SEC-35 错误摘要中的 URL 路径 | 持久化错误、`status --json`、JSON/文本失败摘要统一隐藏完整 URL、敏感头与敏感查询值，并清除显示控制字符。 | 回归覆盖 URL 路径令牌、查询签名、legacy status 行和 JSON/stdout/quiet stderr；CLI、tasks、pipeline 定向回归 **8 passed**，Ruff 通过；该修复阶段完整套件各 404/20，后续历史快照为 424/20（第 45 节），第 51 节历史快照为 459/23；第 64–65 节历史快照中 Python 3.11/3.12 各为 477/23；§80 历史快照为 495/23；§92 历史快照为 510/23；§100 历史全套为 520/23；§131 修复前最近一次全套见审核报告 §§128–129（Python 3.11/3.12 各 519/23）；§131 后未重跑全套。 |
| 正式差异安全审查 | 最新封存差异扫描 `81745f42-fe5b-4151-845c-95c70da451ee` 完成 16 个源码/配置审查项并复用 P2 动态证据，确认既有 AUD-77 一项，其他已审查面无新增可报告问题；扫描覆盖仅限冻结差异快照。 | 冻结摘要为 `codex-security-snapshot/v1:sha256:9142fc74cb252800be19259804af998e48c322ca17957d291b4c04f00ac50a1f`。扫描未重跑动态网络或测试；扫描封存后的少量脚本/文档跟进变更另做定向验收，详见审核报告第 66 节。第 50 节修复前扫描的 CWE-923 仍需进程级隔离；CWE-150 已在第 51 节修复且在后续复核中未再报告。最新结果见审核报告第 66 节。静态审查不替代真实媒体、Agent 宿主、远端网络或跨平台验收。 |
| CWE-400 SPDX 验证资源耗尽 | 离线 SPDX verifier 为输入文件、包行、制品数/体积、单成员、总时间、tar 展开、ZIP 中央目录/成员遍历设置硬预算；哈希前预检大小并在超限时失败关闭。 | 整改时本机 Python 3.11 全套为 435 passed、20 skipped；离线复核 35 artifacts、33 metadata、4 license、1 notice。第 51/53 节历史快照为 459/23；第 64/65 节历史快照中 Python 3.11/3.12 各为 477/23；§80 历史快照为 495/23；§92 历史快照为 510/23；§100 历史全套为 520/23；§131 修复前最近一次全套见审核报告 §§128–129（Python 3.11/3.12 各 519/23）；§131 后未重跑全套；Linux/macOS 仍待跨平台实机验收。 |
| CWE-345 SPDX 证据去重身份冲突 | 去重时比较完整成员证据与包身份，拒绝同一 archive/member 被不兼容包记录复用；有效 SPDX 声明限制为规范 License 字段/值。 | 冲突与伪造字段回归通过；整改时 Windows Python 3.11 全套为 435/20。见审核报告第 47 节；之后第 48 节复扫发现生成器另一条证据绑定问题，该问题已在第 49 节整改。 |
| CWE-400 SPDX 生成器解析资源预算（已整改） | 生成器对 evidence JSON 设置字节/行预算，并限制表达式长度、token 和递归深度；锁/evidence 只读常规文件且校验打开身份。 | 发现记录于历史 Diff Scan §48；本地整改在 §49。第 51/53 节历史快照为 459/23；第 64/65 节历史快照中 Python 3.11/3.12 各为 477/23；§80 历史快照为 495/23；§92 历史快照为 510/23；§100 历史全套为 520/23；§131 修复前最近一次全套见审核报告 §§128–129（Python 3.11/3.12 各 519/23）；§131 后未重跑全套；Linux/macOS 仍需复验。 |
| CWE-345 SPDX 生成器证据绑定（已整改） | 生成前由离线 verifier 对照锁定 artifacts 字节验证 metadata、license 和 notice 成员，并将 file-level license 声明绑定到精确审阅 identity。 | 发现记录于历史 Diff Scan §48；本地整改在 §49。第 51/53 节历史快照为 459/23；第 64/65 节历史快照中 Python 3.11/3.12 各为 477/23；§80 历史快照为 495/23；§92 历史快照为 510/23；§100 历史全套为 520/23；§131 修复前最近一次全套见审核报告 §§128–129（Python 3.11/3.12 各 519/23）；§131 后未重跑全套；完整 artifact cache 复核证据见第三方许可报告，Linux/macOS 仍需复验。 |
| CWE-150 doctor 配置路径控制字符（已整改） | doctor 文本诊断在输出边界清理路径、动态诊断及 bidi/C0/C1 控制字符，JSON 输出保持转义。 | 发现记录于历史 Diff Scan §48；本地整改及回归见 §49。第 51 节历史快照为 459/23；第 64–65 节历史快照中 Python 3.11/3.12 各为 477/23；§80 历史快照为 495/23；§92 历史快照为 510/23；§100 历史全套为 520/23；§131 修复前最近一次全套见审核报告 §§128–129（Python 3.11/3.12 各 519/23）；§131 后未重跑全套。 |
| SEC-SC-01 / CWE-829 CI Skill 校验器依赖图 | `skills-ref==0.1.1` 及传递依赖已加入 `dev` 组与 `uv.lock`；CI 从锁定环境离线运行 `agentskills validate`，去掉 `uvx` 临时解析。 | 本机 `uv --offline run --locked --no-sync --group dev agentskills validate skills/douyin-transcript` 返回 `Valid skill`；远端 Actions 矩阵尚未运行，见审核报告 §64。 |
| SEC-SC-02 / CWE-829 PEP 517 构建后端 | `editables==0.5`、`hatchling==1.27.0` 纳入默认锁定 `build` 组；仅对本项目禁用构建隔离，使同步先安装锁定后端。 | 第一次仓库外安装发现 editable 构建所需的 `editables` 缺失，已加入 `build-system.requires` 和锁。修复后的仓库外 `uv sync --locked --no-dev`、导入来源与 CLI smoke 全部通过；见审核报告 §64。 |
| AUD-79 默认逐字稿 ACL（本地实现与回归完成；跨平台 ACL 待验收） | 未配置输出目录时使用 `<data_dir>/output`；若默认目标权限不安全或未知，pipeline 拒绝启动。有效 schema 1/2 失败任务快照重试前也检查保存目录，`unsafe`/`unknown` 时要求显式传入 `--output-dir`；路径解析 `RuntimeError` 视为无效快照，并将校验后的配置一路带入处理阶段。 | 主路径见审核报告 §58；schema 1/2、符号链接异常、显式输出覆盖及单次快照解析回归见 §63。§80 的 Windows Python 3.11/3.12 全套各为 495 passed、23 skipped。Linux/macOS 和第二 Windows 账户 ACL 验收仍开放。 |
| AUD-10 Windows 真实媒体超时切片 | 用户授权的真实本地音频由 PyAV 子进程解码，固定 faster-whisper 模型成功加载；45 秒 CLI deadline 将任务持久化为 `PROCESSING_TIMEOUT`，worker 随 CLI 退出而结束，未留下输出、缓存或 `.part` 文件。 | Windows 本机结果见审核报告 §68。macOS/Linux worker 终止行为及授权远端下载的 `.part` 清理仍需实机验收；此次本地运行没有分阶段计时。 |
| SEC-36 敏感文件诊断终端控制符（已整改） | `check_sensitive_files.py` 在 stderr 边界转义 Git 文件名中的控制字符，复用 SPDX 终端安全 helper。 | ESC、CR/LF、bidi 和 Unicode 行分隔符输出回归、Ruff 与敏感文件扫描结果见审核报告 §58；远端 CI 日志仍需验证。 |
| CWE-150 SPDX evidence 终端控制字符（已整改） | `_safe_member_path()` 拒绝 Unicode 控制/格式字符及行/段落分隔符；共享 helper 转义两个 SPDX CLI 的异常、生成器写入错误和成功输出路径。 | 第 50 节发现；§51 新增路径和输出回归。第 51 节当时 SPDX 定向组 50 passed、3 skipped、全套 459 passed、23 skipped；第 64/65 节历史全套为 477 passed、23 skipped；§80 历史快照为 495/23；§92 历史快照为 510/23；§100 历史全套为 520/23；§131 修复前最近一次全套见审核报告 §§128–129（Python 3.11/3.12 各 519/23）；§131 后未重跑全套；§52 修复后正式复扫未再次发现该问题，但 coverage partial。 |
| AUD-76 恢复缓存媒体时启动等待无界累加 | 恢复阶段现在只做快速完整文件检查；任务领取后仍在正常处理 deadline 内严格解码并校验媒体，损坏缓存继续触发重新捕获。 | 两项 stale 缓存端到端回归确认有效缓存延迟验证及损坏缓存回退；`test_tasks.py` 为 37 passed、1 skipped；与 AUD-77 回归合计 4 passed。第 47 节时全套为 435/20，第 51 节历史快照为 459/23；第 64–65 节历史快照中 Python 3.11/3.12 各为 477/23；§80 历史快照为 495/23；§92 历史快照为 510/23；§100 历史全套为 520/23；§131 修复前最近一次全套见审核报告 §§128–129（Python 3.11/3.12 各 519/23）；§131 后未重跑全套；最终 release commit、真实长媒体和跨平台实机仍待验收。 |
| AUD-77 Chromium WebRTC UDP 绕过 CONNECT 代理 | 锁定 Chromium revision 1243 在策略参数出现在实际命令行时，仍将合成 STUN UDP 包送达 loopback 与本机局域网接口接收端。Playwright route、HTTP 代理、host allowlist 和 DNS pinning 均未拦截；仅作为纵深防护保留该参数。 | 未解决，P2 网络边界门槛未通过。按用户授权，目标仍是项目维护、管理员安装的 Windows WFP service（Windows 11 x64 首发）。guest-only WFP 临时规则、固定 SHA 预览和 curl 级 per-user/package-SID 探针均不构成 Chromium、broker 或生产服务验证。§123 的 session 命名对象权限只是 `ProcessSingleton` 故障强候选；SYSTEM harness 在启动前被执行策略拦截。§125/§127 的 AUD-86 发现：旧 lease 契约会把 listener socket 副本交给普通 Python relay，未验证本机客户端身份，且 Python 创建上游 socket；目前没有 production listener，应用仍在启动浏览器前 fail closed。capture route 的本机 DNS 调用现已移除，但它只做 URL/scheme/hostname 检查，完整 DNS A/AAAA/CNAME 公网验证与 numeric IP pinning 必须归属每 lease worker。管理员主服务只能做 control plane；独有低权限 SID worker 持有 listener、DNS 和 upstream，WFP worker AppID+SID 只允许受信 resolver 与该 lease pinned IP:443。共享管理员 service AppID/SID 的动态目的地 permits 会形成跨租约并集，不能声称逐 lease egress。worker/Chromium 目标 token 尚无可启动验证，未满足时必须 fail closed。broker/IPC、可信状态/策略核验、持久默认拒绝、installer/rollback 均未完成；需在可回滚 Win11 环境验证完整进程树和 IPv4/IPv6/loopback/LAN/UDP/raw-socket 拒绝，完成 worker 代理 HTTPS 以及三条授权视频端到端捕获。宿主 WFP/Firewall 未改动，P2 保持 fail closed。详见 `P2_ISOLATION_DECISION.md` 和审核报告 §§93–97、106–110、123–127。 |
| AUD-77 方案决定（已选，未实施） | 按用户授权选择项目维护、管理员安装的 Windows 用户态 WFP service；首阶段支持 Windows 11 x64。 | 临时 .NET 10/CsWin32 API 绑定探针构建通过，但它不是服务实现。管理员 service 仅作 control plane；每 lease 独有低权限 SID worker 才能持有 listener、DNS 与 upstream socket，并由 worker AppID+SID 限制 resolver 和 pinned IP 出口。服务、认证 IPC、worker/Chromium 目标 token 启动、受保护 Chromium 安装、安装器和回滚仍未完成；当前 Codex 进程是普通用户令牌，不能以用户授权推导管理员 token，也没有因此写入 WFP/Firewall。AUD-77/AUD-86 仍开放；见审核报告 §§94、125、127。 |
| P2 WFP API 可构建性探针 | 临时安装 .NET SDK 10.0.401，使用 CsWin32 0.3.360 和完整 WFP 元数据命名空间生成并编译 WFP 管理 API 绑定，结果 0 warnings / 0 errors。 | 只验证绑定生成/编译，不构成 WFP 结构布局、过滤器仲裁、服务安全或运行时验收。SDK 和探针均在用户临时目录；无服务代码或系统策略变更，具体边界见审核报告 §94。 |
| AUD-83 延迟媒体观察窗口 | 导航与元数据检查后若仍无获准候选，额外观察最多 2 秒，按 200 ms 间隔泵送 Playwright 事件，并受共享 capture deadline 限制。 | `test_p2_capture.py` 覆盖 900 ms 延迟的候选；用获准真实页面复试仍为 `CAPTURE_NO_MEDIA`（审核报告 §78），不放宽 host 策略，不算捕获成功。 |
| AUD-84 页面元数据/登录提示读取无上限 | 标题、作者、日期的 DOM 文本与属性现限制长度和文本节点数；登录提示搜索只返回 bool，不复制整页 body；Python 对返回值再截断。 | `test_p2_capture.py` **24 passed**，§80 双版本全套各 495/23，Ruff 通过。登录提示最多检查 16,384 字符/4,096 节点；成功媒体路径下的真实浏览器集成和跨平台仍待验收。 |
| AUD-85 缓存命中枚举先排序/物化全部文件 | `_find_valid_cache()` 现改为目录流式枚举，每条目检查取消和共享 deadline，再匹配当前视频/类型前缀；避免目录候选数较大时将扫描/排序成本前置到期限检查之外。 | `tests/unit/test_p2_downloader.py` **55 passed, 1 skipped**；慢目录迭代器用例验证 deadline 到期时 decoder 未调用。§80 双版本全套各 **495 passed, 23 skipped**；单次 OS 枚举仍由文件系统响应时间决定，跨平台验收开放。 |
| DOC-26 当前状态与历史快照标注 | Release 报告将 SEC-17 本地真实推理、SEC-23 未知时长覆盖、历史 §70/§80 测试结果和扫描先后顺序按最新证据校正；实施计划拆分已完成的本机隐私/静态检查与待完成的 Agent 宿主/远端验收；P2 文字改为三条成功捕获门槛。 | §92 为历史快照（两版本各 510 passed、23 skipped）；§100/§109 是历史结果（520/23）；§131 修复前最近一次双版本全套见审核报告 §§128–129（519/23）。§106–110 依次记录 scoped smoke、C#/PowerShell 规则自校验、负向检查/提权受阻、预览 JSON 驱动复验和探测器归因加固；这些不构成最终发布验收。`git diff --check` 与两个 Agent Skills validator 曾通过；当前所有者外部决定仍见 `docs/OWNER_DECISIONS.md`。 |
| CLI-03 doctor 配置错误诊断 | 保留 `ConfigurationError` 的具体原因；只在 CLI 或 `DOUYIN_TRANSCRIPT_OUTPUT` 明确给出目标时探测输出目录，否则状态为 `unknown` 并跳过探测。 | `tests/test_doctor.py` 定向 19 passed；CLI-03 后的全套复验结果见审核报告第 16 节。 |
| 锁定依赖 SBOM | 从完整 `uv.lock` 生成 SPDX 2.3 JSON，列出项目与全部第三方锁定组件、平台版本变体、extras、build 与 dev 依赖。 | SPDX 2.3 Schema 校验通过。SBOM 包含 121 个 package records/137 个 relationships：42 个 `uv.lock` 记录加 79 个由 Playwright sidecar 明确列出的 npm 组件；官方 schema SHA 和子组件证据见 §91。41 个锁定第三方发行物的 artifact SHA-256 均已核验；§161 离线 verifier 按 lock/manifest 字节复核 210 个 artifact、41 个 metadata、9 个 license、2 个 notice 和 1,149 个 supplemental 成员。Playwright 的 8 个锁定平台 wheel 中 64 个许可证/通知类候选均与 wheel RECORD 一致（§87）。41/41 个锁定第三方包有 evidence-backed `licenseDeclared`；79 个 npm 组件也逐项记录 sidecar 声明，其中 78 个许可证正文可识别，1 个只有 MIT 声明而无正文；所有 `licenseConcluded` 仍为 `NOASSERTION`。`python-dateutil` 依据锁定 sdist LICENSE 声明 BSD-3-Clause（§86）。早期已安装包的 65 个候选仍只覆盖审查时的 32 个发行包。ONNX Runtime notice 到链接组件映射、原生及 Cargo 依赖、其他平台 wheel 和 PyAV/FFmpeg 仍未完成。当前证据见审核报告 §§86、89、91、145、147、161 及 `THIRD_PARTY_LICENSE_REVIEW.md`。 |

## 发布前必须完成

| 优先级 | 对策 | 完成证据 |
|---|---|---|
| P1 | 锁定 ASR 依赖和 medium 模型已按用户授权安装。用户提供的 315.907 秒本地 MP4 已成功完成转写并生成非空私有 Markdown；PyAV 检测到 AAC 立体声音轨、没有视频流。 | 实际模型、平台、耗时、输出大小及 CLI/status 正文泄漏检查已记录于 `P1_REPORT.md` 和 `BENCHMARK.md`。人工听审保留给 P4。 |
| P2 | 已选项目维护、管理员安装的 Windows WFP service，首阶段支持 Windows 11 x64；当前有 CsWin32 API 绑定探针、应用侧 lease contract、guest WFP block/release 与 PowerShell AppID scoped smoke、逐规则预览校验和 package-SID/curl 原型（§§96、105–112）。§114 的 Chromium AppContainer 在 ACL 修正后仍因 Crashpad CreateNamedPipe 访问拒绝而以 STATUS_BREAKPOINT 退出；LOCAL pipe 冲突是强推断但尚未匹配精确源码 revision。§115 的 `ALE_USER_ID` / `FWP_SECURITY_DESCRIPTOR_TYPE` 动态规则通过独立低权限账户 curl 阻断、SYSTEM 对照和 session-close 恢复，但 Chromium 在过滤前后均未通过非交互账户启动；交互 Sandbox headless 复测也未产生截图。该证据只能支持继续评估 per-user WFP，不能宣称浏览器隔离通过。当前 capture route 仅执行 HTTPS/WSS、URL 与 hostname allowlist 校验，不触发本机 DNS；完整 A/AAAA/CNAME 公网检查和 numeric IP pinning 需由每 lease 独有 SID 的低权限 worker 执行。管理员主服务仅为 control plane；worker 持有 listener、DNS、upstream，WFP worker AppID+SID 只允许受信 resolver 和该 lease pinned IP:443。共享管理员 service AppID/SID 无法提供逐租约 egress；worker 或 Chromium token 启动失败时必须 fail closed。生产服务/IPC/worker/Chromium 启动/installer、IPv6/UDP/QUIC、持久 deny、provider arbitration、故障/回滚仍未完成。唯一获授权页面仍为 CAPTURE_NO_MEDIA。最终仍需三条不同获授权视频端到端成功捕获。 | 依据 P2_ISOLATION_DECISION.md 先验证 user-session token/profile/desktop、每 lease worker SID、DNS 查询和 Chromium 完整进程树，再证明精确代理边界。服务须验证 IPC caller 和有效系统 filters；动态 WFP endpoint deny/permit 与 worker 出口许可按 lease worker identity 管理。服务或策略缺失、lease 断开时拒绝/终止捕获并保留持久 deny。后续结果写入 P2_REPORT.md；不得提交 Cookie、签名 URL 或媒体。 |
| P3 | 在新测试中由真实 pipeline 子进程于 SQLite 的 `downloaded`、`transcribing`、`writing` 状态提交后突然退出；第二个独立进程恢复同一任务，复用缓存且不重复抓取/下载，并生成有效 Markdown。 | `tests/unit/test_pipeline.py::test_pipeline_recovers_after_real_subprocess_crash` 三个阶段全部通过；当时完整 pipeline 文件结果为 37 passed、1 skipped（审核报告 §71）。测试使用确定性外部依赖替身，不替代 P2 的实时媒体验收。 |
| SEC-31 | 已在 Windows 临时环境对锁定 PyAV 15.1.0 用本地 mock HTTP 服务提供含 loopback 片段地址的 HLS 清单，并验证普通本地媒体。 | 审核报告记录 PyAV/FFmpeg 版本、拒绝回调 1 次、mock 请求 0 次与 WAV 通过；发布前仍需在 macOS/Linux 对目标 wheel 复核。 |
| P4 | 10 分钟以上运行、默认模型文本校对、中文标点及保留原稿已由 §176 验证；听审至少三处代表段并在 fresh Desktop 核验宿主数据流。 | 长样本与侧车哈希记录在 `PROJECT_AUDIT_REPORT.md` §176。听审由操作者对照音频记录漏词、增词、术语和不确定片段；只记录观察，不复制逐字稿正文。Fresh Desktop trace 另记录实际模型调用/输出边界。 |
| P5 | 已新增 repo-scoped `.codex/skills/douyin-transcript/SKILL.md` 入口并通过固定版 validator；它指向 canonical Skill/CLI。需在新 Codex Desktop 会话确认发现，再用结构化参数执行只读 `doctor` 或获授权 URL `--dry-run`。 | 记录宿主版本、安装来源、技能列表/触发证据、实际参数数组和脱敏调用结果；回复仅包含简短状态与路径。P1 本地 CLI 隐私检查已完成；目标 Agent 宿主仍需单独验收。 |
| P6 | 由仓库所有者决定 LICENSE、仓库归属/名称/可见性、发行范围和是否授权推送或发布。之后检查待提交树与完整 Git 历史，提交阶段结果并运行远端 Windows/macOS/Linux × Python 3.11/3.12 CI 和最终远端干净安装；继续审阅 41 个依赖及平台发行物。2026-10-10 新增跨平台 CTranslate2 原生库、ONNX Runtime notice/二进制映射、Tokenizers/Ruff Cargo wheel 与 NumPy license 文件复核；artifact 身份检查已覆盖，许可与 build provenance 仍未关闭。 | 所有者决定与 LICENSE、最终提交 SHA、完整 CI 矩阵链接、远端安装记录、历史敏感数据审查记录及与拟分发 artifact 哈希绑定的依赖 SBOM/license/notice。`licenseConcluded` 保持 `NOASSERTION`，直到有足够证据完成判断。详见审核报告 §§41、64、172、193 及 `THIRD_PARTY_LICENSE_REVIEW.md`。 |
| SEC-SC-01 / CWE-829 CI 校验器远端验证 | 本地锁定和离线运行整改已完成；发布前仍需在 Windows/macOS/Linux × Python 3.11/3.12 远端矩阵运行，确认 validator 所在环境不联网也能通过。 | 本机 validator 与锁定 clean install 证据见 §64；关闭需远端 Actions run URL 和六项矩阵结果。 |
| SEC-SC-02 / CWE-829 PEP 517 构建远端验证 | 本地 Hatchling/editables 锁定和仓库外 source install 已通过；发布前仍需在目标 OS/Python 矩阵确认安装器使用同一锁定构建组。 | 本地证据见 §64；关闭需远端干净安装/CI 日志以及最终提交 SHA。 |

## P2 最新执行状态（2026-10-11）

§115 在联网 Sandbox 中验证 `ALE_USER_ID` dynamic filter：随机低权限账户的 curl 被阻断、SYSTEM 对照成功、关闭 session 后 curl 恢复。§116 修正了不受 guest runtime 支持的 `.Kill($true)`，并确认 headless harness 能清理进程树；这没有通过浏览器启动。§117 的 `CreateProcessAsUser` 原型在临时 guest desktop ACL 下能启动目标 SID/session 的 Chromium 树并越过 USER32 延迟加载，但仍以退出码 21 和 `ProcessSingleton` 错误退出，无截图；同一 SID 的锁文件探针成功，具体失败 API 未知。§118 的离线 PML 导出没有产生 CSV，不能用于归因。§119 的早期 SwiftShader 运行因同时使用 `--disable-gpu` 而不是有效对照。§120 修正参数后，实际 SwiftShader 截图和 `--dump-dom` 在 30 秒后都超时、无输出；详细日志尾部未定位具体启动 API。§123 发现低权限目标 SID 对 session `BaseNamedObjects` 命名 mutex 的访问被拒绝，是 `ProcessSingleton` 故障的强候选解释；SYSTEM harness 后续复测在启动前被执行策略拦截，没有新的 Chromium 证据。§125/AUD-86 又发现旧代理契约未绑定本机客户端 lease identity，且 upstream socket 由普通 Python 进程创建。最新 route 回归（26 passed）确认 browser request/WebSocket route 不调用本机 DNS resolver，仅做 URL/scheme/host allowlist 检查；downloader 和通用 URL validator 不变。管理员主服务只能做 control plane；每 lease 独有低权限 SID worker 持有 listener、DNS 和 upstream，WFP worker AppID+SID 只允许受信 resolver 与该 lease pinned IP:443。共享管理员 service AppID/SID 的目的地许可会形成跨 lease 并集。worker 与 Chromium 目标 token 尚无可启动验证；DNS 身份和 worker/Chromium 启动均列为 AUD-86 阻断项，capture 继续 fail closed。上述 WFP 规则仍只有 curl 级证据，browser/worker launch、lease endpoint、worker egress、installer/rollback 均未验收；宿主 WFP/Firewall 未改动。详见项目审核报告 §§115–127。

**对策：** 继续将管理员安装的项目 WFP service 作为架构方向，但不选定尚未验证的进程身份实现。先在可回滚 guest/service prototype 中验证适当的 user-session token、profile、desktop 和 Chromium 启动/退出，再把 per-lease WFP user SID 规则绑定到完整子进程树；AppContainer 可溯源 LOCAL 修复 Chromium 是独立备选。不得用 `--no-sandbox` 绕过启动问题。两条候选都必须通过正反向流量矩阵、故障/回滚和三条获授权媒体验收；生产服务/IPC、持久默认拒绝与全流量覆盖仍未实现，URL capture 保持 fail closed。详情见 PROJECT_AUDIT_REPORT.md §§115–120。

## 后续风险与操作建议

- **输出目录权限按路径来源处理。** 运行 `doctor --output-dir PATH` 检查实际目标；隐私稿件先写入权限状态为 `ok` 的个人目录。隐式默认目录为 `unsafe`/`unknown` 时，pipeline 失败关闭；显式指定的共享目录仍显示告警并允许有意使用。有效 schema 1/2 快照若保存目录权限为 `unsafe`/`unknown`，`retry-failed` 在重试入队前阻止它，除非操作者显式传入 `--output-dir`。AUD-79 本机回归已完成；Linux/macOS 和第二 Windows 账户 ACL 验收仍开放。
- **媒体缓存不会自动清理。** 用 `cache inspect` 查看体积，先用 `cache clean --max-age-hours N` 或 `--max-bytes N` 预览，再复核路径后加 `--apply`。
- **Git 历史自动扫描范围有限。** 当前 HEAD `b166778` 的 5 个可达提交已按仓库敏感路径、高置信度凭据模式及工作区/用户目录标记做只读扫描，120 个唯一路径/blob 对均为小型 UTF-8 文本且无命中；这不是通用 secret scanner。最终提交后仍须重跑并人工复核完整历史和待发布树。
- **未经所有者决定不得发布。** 项目目前无 LICENSE、无配置的远端仓库，远端 CI 与目标 Agent 宿主尚未验收；在这些门槛关闭前保持 `NOT READY`。

## 推荐执行顺序

1. 先在可回滚的管理员 Win11 x64 测试环境实现并验证认证 IPC、per-lease worker、WFP/Chromium egress 和失败关闭；这些门槛通过后，再用三条不同且获授权的视频完成 P2。当前 URL capture 保持 fail closed，暂不重复提交实时链接。并行在新 Codex Desktop 会话执行 P5 宿主验收。
2. P1 本地实测已完成；听审至少三处代表性片段、取得 10 分钟以上音频运行记录并完成 P4 Agent 上下文检查。SEC-31 的 Linux/macOS wheel 检查仍待目标平台环境。
3. 完成 P2 和 P5，并把真实结果写入对应报告。
4. 请仓库所有者决定许可证、仓库信息和远端操作授权，随后完成 P6。
5. 仅在最终提交通过矩阵 CI、远端安装和历史审查后更新发布状态。

## 历史工作区快照（§135，2026-10-11）

- **P2 网络边界：** 默认 pipeline、CLI `--dry-run` 和批量解析对抖音短链只做本地处理，不会在普通调用进程先发起 DNS/HTTPS；短链在隔离服务可用前 fail closed。直链媒体捕获后的 CDN 下载仍在当前调用方 pipeline，未来必须把短链解析、浏览器捕获、候选校验、重定向和媒体下载整体迁移到同一个 per-lease worker。
- **IPC 契约：** 已添加有界 JSON codec/schema。响应解码必须带原始请求，核验 request ID 和该请求的媒体字节数/时长限制。定向回归 77 passed、1 skipped；完整 Windows Python 3.11.15 套件 539 passed、24 skipped（333.89 秒）。协议代码不等于 IPC transport、service、worker 或媒体字节通道。
- **P5 本地 CI：** 固定版 Agent Skills validator 现在覆盖 canonical Skill 和 `.codex` repo-scoped 入口；两个入口本地验证通过。真实 Desktop 发现/调用仍要在新会话验收。
- **原生预览构建：** 锁定的用户临时 .NET SDK 10.0.401 对 WFP 预览器当前源码构建成功（0 warnings、0 errors）；`--plan`、`--filter-plan`、`--layout` JSON 输出和 SHA-pinned filter-plan artifact 校验通过。该项目明确不部署 WFP、不含服务/安装器，不能作为 P2 策略生效证明，详见审核报告 §136。
- **本地检查：** Ruff、两个 `uv.lock --check`、SPDX 2.3 schema 检查、Git 可见敏感文件检查和 `git diff --check` 均通过。artifact-bound SBOM 字节检查仍按 §124 的既有证据记录；本次未重建制品缓存。
- **不能据授权推导的系统权限：** 用户已授权代理选择 P2 方案，但当前任务没有管理员 host/session 或远程运维通道，工作进程仍为普通 Windows token。因此没有安装系统服务、尝试网络扫描或更改宿主 WFP/Firewall；捕获入口继续 fail closed。需要把工作区接入可回滚的管理员测试主机/会话，且先实现和审阅服务代码，才能做动态验收。
- **剩余验收：** P2 仍缺认证 IPC、worker/WFP/Chromium 动态证明和 3 条成功的授权视频。P4 的 10 分钟长样本已达标，仍缺三处人工听审及新 Desktop 宿主数据流验收。P5 仍缺新 Desktop 会话调用证据。P6 仍缺所有者确定 LICENSE、发行范围、仓库/可见性及远端授权，另有平台原生许可/来源审查、远端 CI 和远端干净安装。
- **状态：** P2/P4/P5/P6 及最终发布门槛保持 OPEN，整体 **NOT READY**。最终提交及 Linux/macOS 测试尚未进行。
- **历史表格时点：** 上方表格中的测试数量均对应相应问题修复快照；截至当前，最新记录分别为 §143 的 Python 3.11.15 **579 passed、27 skipped** 和 §144 的 Python 3.12.13 **578 passed、28 skipped**，不能视为同一提交的配对结果。最终 release commit 与 Linux/macOS 实测仍未完成。

## 2026-10-13 P2 process-tree lifecycle source slice (§272)

An unnamed kill-on-close Job Object component now supports a future per-lease worker launcher. It requires an exactly configured no-breakaway job, assigns a newly suspended root before resuming it, and terminates/drains the process tree on stop or failed startup. The pinned Windows build and complete offline harness pass, including a real harmless root/child pair. This is not production integration: service and worker wiring, low-privilege per-lease identity, WFP policy, rollback, egress probes, and three successful authorized captures remain required. Keep URL capture fail closed until those gates pass.
