# 安全审核报告（2026-10-13）

## §285 当前工作树差异扫描（2026-10-13）

扫描 `7412ed63-3347-4ffb-9753-d7c0ee5f121c` 已封存；冻结摘要为 `codex-security-snapshot/v1:sha256:da78cde0ce2ea800ecb645447aa7612132282a3ba36a059dbaa6bd475213dea4`，基线/HEAD 为 `b166778ee5283591a1b799535b746ba198e38653`。权威变更项 **123/123** 已复核，发现 **2 项低严重度问题**；coverage 为 **partial**。这是静态差异审查，不是全仓、生产运行时或发布安全认证。

| ID | 严重度 | 发现 | 对策 |
|---|---|---|---|
| `csf_598bf0f5748fb718677dab21` | Low | `scripts/generate_spdx_sbom.py:189-190, 577-591` 接受含换行的证据字段并将不匹配的包名写入异常；`scripts/check_spdx_sbom_freshness.py:323-332` 将异常原样写到 stderr。CI 的 `pull_request` 步骤调用此检查器。验证确认 GitHub Actions runner 将该步骤的 stderr 交给同一 workflow-command 解析器，因此可伪造 warning 注解或干扰日志显示。当前证据只支持日志/注解完整性影响；未证明代码执行、秘密读取或写权限。 | 对证据 `name`/`version` 拒绝 CR/LF 及控制/格式字符；异常只输出固定错误类型，不回显原始字段；在 CLI 错误边界统一安全转义。增加 `::warning::`、`::error::` 换行注入回归，验证输出中没有独立 workflow command。 |
| `csf_d19ed0b4209b7f091e76cbff` | Low | `scripts/inventory_locked_artifact_members.py` 与 batched renderer 将锁定包标签和归档成员名写入 JSONL/Markdown；现有转义处理 HTML/管道符和部分控制字符，但未显示编码 Unicode bidi `Cf` 字符。恶意或受损依赖归档可能使双向文本查看器重排审计清单中的标签，影响人工检查。需要归档/锁记录含该字符且操作员依赖相关报告；未发现当前锁定样本含此类成员，归档不会在该流程中执行。 | 共享格式化器对所有 Unicode `Cf` 字符采用可见 U+XXXX 表示，同时用于普通与批处理 JSONL/Markdown；添加 U+202A–U+202E、U+2066–U+2069 的合成成员名和包名回归。 |

第一项的 runner 证据来自官方实现：[ScriptHandler 将 stderr 接入 OutputManager](https://github.com/actions/runner/blob/main/src/Runner.Worker/Handlers/ScriptHandler.cs#L1489-L1497)，[OutputManager 将 command-shaped 行交给命令解析器](https://github.com/actions/runner/blob/main/src/Runner.Worker/Handlers/OutputManager.cs#L1140-L1158)。本地合成证据复现了 stderr 中独立 `::warning::` 行；没有运行远端 CI。

扫描范围仅为冻结的工作树差异。没有执行 GitHub-hosted workflow、浏览器/网络、管理员服务或 WFP/BFE；URL 捕获继续 fail-closed，WFP 完整可见性和真实 ACL 仍待管理员级集成验证。P4 音频听辨不属于本次安全扫描，未把模型文本校对当作声学确认。

本 §285 内容在扫描封存后写入；本报告文件本身不属于上述摘要。扫描生成的机器报告保存在 Codex Security 的私有扫描目录，仓库文档不复制用户本机路径。

## §284 历史代码补充（当时最新 sealed scan 为 §283，2026-10-13）

最新封存 Codex Security Diff Scan 为 `0e0f14d7-0ce0-44a3-935c-b003aac7f88c`，摘要 `codex-security-snapshot/v1:sha256:7f53743d69df9b89ceeefed5d05c9a9e133b7b151549d05e1ec03ed5803f75f6`，基线/HEAD `b166778ee5283591a1b799535b746ba198e38653`。其 123/123 worklist、0 个报告级 finding、partial coverage 只适用于 §283 的冻结字节；不覆盖 §284 WFP ACL 源码与回归测试，也不能作为当前整树零 finding 结论。

§284 将原型 WFP 对象由 service SID 所有权及 `GENERIC_ALL` 改为 LocalSystem owner/group、protected DACL 和 SYSTEM/service SID 两个 `GRGWGX` ACE。新 Runtime harness 验证描述符结构、主体集合和权限掩码，并拒绝回退至 `GENERIC_ALL`；WFP Runtime harness **17/17**、两项 .NET whitespace checks、敏感文件检查、全量 Python **728 passed、46 skipped** 均通过。Microsoft 文档将 generic read/write/execute 展开为 WFP 功能权限；对象 owner 可更新 DACL。当前实现因此去掉 service SID 的 owner 身份及 `GENERIC_ALL`，但尚未以真实 WFP token/API 验证最小权限或对象可见性。

仍延续 deferred 的集成风险：CONNECT authority 与 TLS SNI 未绑定；WFP service SID 未由安装服务推导，native backend/readback/rollback 与完整对象可见性未实现。没有运行生产 service、浏览器、网络、WFP/BFE、Sandbox 或宿主策略。下一次正式扫描必须使用最终稳定树，不沿用 §283 的摘要。

P4：三段 WAV 完成文件身份、时长和格式核验；当前环境没有音频感知能力，没有声学判定或稿件修改。08:50–09:08 年份分歧仍需听审；P4 fresh Desktop 隐私/数据流、P5 fresh Desktop Skill trace、P6 owner/license/remote CI/clean install/provenance 仍开放。项目继续 **NOT READY FOR RELEASE**。

本节及关联状态文档的更新晚于 §283 冻结；这些文档字节不属于该扫描摘要。报告仍避免暴露用户本机绝对路径。

## §281 扫描身份与范围

- Scan ID：`20e67e26-099e-432f-bf0e-9df5761e8841`；状态 completed/sealed；基线/HEAD `b166778ee5283591a1b799535b746ba198e38653`。
- 复核：123/123 权威变更源代码 worklist 项完成；三个条件性原型风险经验证后记为 deferred，没有报告级漏洞。
- 运行时限制：没有启动应用、浏览器、服务、WFP/BFE、网络或远端 CI。默认 URL 捕获和 Windows 服务入口继续 fail closed。

## 最新结论（§280，2026-10-13）

最新 Codex Security Diff Scan `379ff356-fc08-46cf-ab1a-a1edd44da9e9` 已封存。权威 frozen worklist **122/122** 项完成，**0 个报告级 finding**；coverage 为 **partial**，不能解释为全仓、运行时或发布安全认证。扫描器报告 `filesTotal=279`。扫描期间工作树有变化，结果保留为冻结摘要 `codex-security-snapshot/v1:sha256:2cf348876c4bae76151c58ef850cea109b7186fea79351ede4eb8c28212616bc` 对应的状态。

两份 P2 文件 `DynamicLeaseCoordinator.cs`、`WfpNativeObjectProjection.cs` 修改时间晚于冻结点。审阅者检查了当前工作树版本，但无法证明与冻结字节一致，必须纳入下一次 diff scan。另有原型 ACL 候选仍 deferred：只校验传入 SID 的格式并给该 SID GENERIC_ALL；未见生产 backend/wiring，需在真实服务 SID、最小访问掩码、native ACL 可见性及 live 验证完成后关闭。Sandbox staging helper 候选为高权限手工诊断入口，无产品调用路径，按 privileged-only 规则不作为报告级漏洞，建议增加可靠 guest 身份/运行凭证检查。

P2 新增的每租约 provider-key 离线源切片由 17/17 fake-store harness 验证，但不解决 shared-sublayer native readback 与真实 service/WFP 集成。P4 三段附件已收到，本会话无音频感知能力，不能声称听过或判断词句；raw/reviewed 稿没有因此修改。P2 live isolation、P4 人工声学/Desktop、P5 fresh Desktop trace、P6 owner/license/remote/provenance 门槛继续开放，项目仍 **NOT READY FOR RELEASE**。

## 本次扫描身份与范围（§280）

- Scan ID：`379ff356-fc08-46cf-ab1a-a1edd44da9e9`；状态 completed/sealed；冻结摘要 `codex-security-snapshot/v1:sha256:2cf348876c4bae76151c58ef850cea109b7186fea79351ede4eb8c28212616bc`；基线/HEAD `b166778ee5283591a1b799535b746ba198e38653`。
- Review inventory：122 条权威 worklist rows 均已复核；0 个报告级 finding。候选处置包含 1 项 not-applicable、1 项 ignore、1 项 deferred；deferred 原因和后续验证见上文。
- Coverage：**partial**。扫描目录不保留逐字节源码快照；冻结后 `DynamicLeaseCoordinator.cs`、`WfpNativeObjectProjection.cs` 的修改时间晚于冻结点。当前工作树字节虽已审阅，不能替代冻结内容核验。下一次安全扫描应更新到当前基线并保留逐路径回执。
- Runtime boundary：仅源码、调用点、配置和文档静态审查；未运行 app、浏览器、WFP/BFE、Sandbox、网络或远端 CI。源码/harness 不等于生产 service、ACL、WFP enforce/rollback 或隔离证明。
- 机器生成的封存报告：记录在 Codex Security Scan 的本机私有产物目录中；仓库文档仅保留 Scan ID，不保存个人绝对路径。

## 历史扫描结论（§274；保留作历史证据）

当时的 Codex Security Diff Scan `dcc6d32b-a735-4a2e-bbbd-184823ad5f31` 已封存；120/120 个权威 worklist 项完成静态复核，**0 项报告级 finding**。覆盖口径复核后，当前全量枚举为 273 个文件，其中 251 条是变更路径、22 个未变更；120 条当前变更路径出现在 worklist，131 条不在清单中。普通 `git status --short` 由于折叠未跟踪目录显示 145 行，展开后为 251 条路径。131 条是当前差异，可能包含扫描封存后的文档或代码编辑；在逐路径核对冻结时间前，不能全部称为扫描时遗漏。coverage 为 **partial**。结果不能外推成全仓 clean scan、生产环境验收或远端仓库结论。扫描封存后有文档同步，本报告不在冻结快照内。项目仍 **NOT READY FOR RELEASE**。

§274 扫描的威胁模型、coverage 与对策见其历史章节；§270 扫描及 §269 finding 修复记录也保留作历史证据。

## §274 历史扫描身份与范围

- Codex Security Diff Scan：`dcc6d32b-a735-4a2e-bbbd-184823ad5f31`，状态 completed/sealed；冻结摘要 `codex-security-snapshot/v1:sha256:bc76e21a943fc819fe00196882fe1e1aa6b12d99cfd898f3a5c3cfdded744f1a`；基线/HEAD：`b166778ee5283591a1b799535b746ba198e38653`。
- 复核范围：应用/Skill 28 项、Windows native/WFP 69 项、脚本/CI 23 项，共 120/120 项；未保留可信候选，报告级 finding 为 0。
- **覆盖差额：** workbench 的 `filesTotal=273` 是全量文件数；当前展开变更集为 251 条路径，其中 120 条与 worklist 重合，131 条当前变更路径不在 worklist；另有 22 个未变更文件。`git status --short` 折叠未跟踪目录显示 145 行，`--untracked-files=all` 显示 251 条路径。由于该集合按当前工作树计算，131 条中可能有扫描封存后的改动；只读复核已覆盖当前所有差异路径，但仍需逐路径与冻结时点分类，并在新 canonical scan 中刷新报告级 coverage。coverage 为 partial。
- 扫描为源码静态复核；未运行应用、浏览器、服务、BFE/WFP、网络或远端 CI。生产 URL 捕获和 WFP enforcement 当前未接线，仍必须 fail closed。
- P4 本地对照仍仅为自动识别候选，不能算声学审听；没有修改 raw/reviewed 逐字稿。P2/P4/P5/P6 发布门槛均未因此关闭。

### 当前变更路径补审摘要（2026-10-13）

当前 131 条 worklist 外差异路径已由只读静态复核分区检查：`native/` 与 `tests/` 涵盖 74 条（native 33、tests 41）；根目录、`.github/`、`scripts/`、`skills/`、`.codex/`、`tools/`、`docs/` 涵盖 57 条。该分区审查没有发现其他可确认的产品漏洞或隐私泄露。由于审查基于当前工作树而非扫描冻结映像，不能据此证明其中哪些改动在扫描封存时已经存在；后续应在下一次安全扫描覆盖当前基线，并保留逐路径回执。

<details><summary>131 条 worklist 外路径（当前工作树枚举，供复核复现）</summary>

- `.codex/skills/douyin-transcript/SKILL.md`
- `.editorconfig`
- `.gitignore`
- `CHANGELOG.md`
- `MEMORY.md`
- `README.md`
- `README_EN.md`
- `SECURITY.md`
- `docs/ACCEPTANCE.md`
- `docs/ARCHITECTURE.md`
- `docs/ARTIFACT_MEMBER_INVENTORY.md`
- `docs/BENCHMARK.md`
- `docs/DOTNET_BUILD_DEPENDENCY_REVIEW.md`
- `docs/NUMPY_WHEEL_LICENSE_REVIEW.md`
- `docs/OWNER_DECISIONS.md`
- `docs/P1_REPORT.md`
- `docs/P2_ISOLATION_DECISION.md`
- `docs/P2_REPORT.md`
- `docs/P6_286_MEMBER_CONTENT_AUDIT_2026-10-11.md`
- `docs/PROJECT_AUDIT_FOLLOWUP_2026-10-09.md`
- `docs/PROJECT_AUDIT_REPORT.md`
- `docs/PROJECT_IMPLEMENTATION_PLAN.md`
- `docs/PROJECT_REMEDIATION_PLAN.md`
- `docs/RELEASE_CHECKLIST.md`
- `docs/RELEASE_REPORT.md`
- `docs/SECURITY_REVIEW_FOLLOWUP_2026-10-12.md`
- `docs/SECURITY_REVIEW_REPORT_2026-10-12.md`
- `docs/SECURITY_REVIEW_REPORT_2026-10-13.md`
- `docs/SECURITY_SCAN_REPORT_2026-10-10.md`
- `docs/SECURITY_SCAN_REPORT_2026-10-12.md`
- `docs/THIRD_PARTY_LICENSE_REVIEW.md`
- `docs/artifact-member-inventory-complete-manifest.json`
- `docs/artifact-member-inventory-complete-part-001.jsonl`
- `docs/artifact-member-inventory-complete-part-002.jsonl`
- `docs/artifact-member-inventory-complete-part-003.jsonl`
- `docs/artifact-member-inventory-complete.md`
- `docs/artifact-member-inventory.jsonl`
- `docs/dotnet-windows-build-bom.json`
- `docs/locked-artifact-cache-evidence.jsonl`
- `docs/locked-wheel-metadata-audit.json`
- `docs/numpy-native-member-evidence.jsonl`
- `docs/numpy-wheel-license-evidence.jsonl`
- `docs/third-party-license-evidence.json`
- `docs/third-party-sbom.spdx.json`
- `docs/unbound-license-candidate-hashes-2026-10-11-final.json`
- `docs/windows-pe-import-edges-classified.jsonl`
- `docs/windows-pe-import-edges.jsonl`
- `docs/windows-pe-import-evidence-complete.jsonl`
- `docs/windows-pe-import-evidence.jsonl`
- `native/windows/capture-pipe/CapturePipe.csproj`
- `native/windows/capture-pipe/README.md`
- `native/windows/wfp-policy-core/WfpPolicy.Core.csproj`
- `native/windows/wfp-policy-native-readback/NativeMethods.txt`
- `native/windows/wfp-policy-native-readback/README.md`
- `native/windows/wfp-policy-native-readback/WfpPolicy.NativeReadback.csproj`
- `native/windows/wfp-policy-native-readback/tests/Program.cs`
- `native/windows/wfp-policy-native-readback/tests/WfpPolicy.NativeReadback.Harness.csproj`
- `native/windows/wfp-policy-native-readback/tests/packages.lock.json`
- `native/windows/wfp-policy-plan/.editorconfig`
- `native/windows/wfp-policy-plan/.gitattributes`
- `native/windows/wfp-policy-plan/.gitignore`
- `native/windows/wfp-policy-plan/NativeMethods.txt`
- `native/windows/wfp-policy-plan/README.md`
- `native/windows/wfp-policy-plan/WfpPolicyPlan.csproj`
- `native/windows/wfp-policy-plan/sandbox-results/.gitkeep`
- `native/windows/wfp-policy-plan/sandbox/AppContainerIdentitySmoke.wsb`
- `native/windows/wfp-policy-plan/sandbox/ChromiumDiagnostic.wsb`
- `native/windows/wfp-policy-plan/sandbox/ChromiumUserSidSmoke.wsb`
- `native/windows/wfp-policy-plan/sandbox/NetworkWfpSmoke.wsb`
- `native/windows/wfp-policy-plan/sandbox/README.md`
- `native/windows/wfp-policy-plan/sandbox/ReadOnlyWfpSmoke.wsb`
- `native/windows/wfp-policy-plan/sandbox/RunMaterializerBfeProbe.cmd`
- `native/windows/wfp-policy-plan/tests/LeasePolicyCompiler.Tests.csproj`
- `native/windows/wfp-policy-plan/tests/Program.cs`
- `native/windows/wfp-policy-plan/tests/SandboxBfeSmoke.cs`
- `native/windows/wfp-policy-plan/tests/SandboxProbeClient.cs`
- `native/windows/wfp-policy-plan/tests/SandboxProbeSupervisor.cs`
- `native/windows/wfp-policy-runtime/WfpPolicy.Runtime.csproj`
- `native/windows/wfp-policy-runtime/tests/NativeWfpPolicyStoreAdapterHarness.cs`
- `native/windows/wfp-policy-runtime/tests/Program.cs`
- `native/windows/wfp-policy-runtime/tests/WfpPolicy.Runtime.Harness.csproj`
- `native/windows/wfp-policy-runtime/tests/packages.lock.json`
- `scripts/nuget_content_hash/NuGet.Config`
- `scripts/nuget_content_hash/NuGetContentHash.csproj`
- `skills/douyin-transcript/SKILL.md`
- `skills/douyin-transcript/references/CLI_REFERENCE.md`
- `skills/douyin-transcript/references/INSTALL.md`
- `skills/douyin-transcript/references/TROUBLESHOOTING.md`
- `skills/douyin-transcript/uv.lock`
- `tests/fixtures/pipeline_crash_worker.py`
- `tests/integration/test_windows_capture_pipe.py`
- `tests/integration/test_windows_socket_handoff.py`
- `tests/test_doctor.py`
- `tests/unit/test_artifact_member_inventory.py`
- `tests/unit/test_batch_acceptance.py`
- `tests/unit/test_bounded_lock_readers.py`
- `tests/unit/test_browser_proxy.py`
- `tests/unit/test_capture_client.py`
- `tests/unit/test_capture_ipc.py`
- `tests/unit/test_capture_pipe_windows.py`
- `tests/unit/test_cli.py`
- `tests/unit/test_config.py`
- `tests/unit/test_corrections.py`
- `tests/unit/test_dotnet_build_bom.py`
- `tests/unit/test_dotnet_build_bom_output_verifier.py`
- `tests/unit/test_evidence_writer_paths.py`
- `tests/unit/test_license_candidate_hashing.py`
- `tests/unit/test_locked_artifact_cache.py`
- `tests/unit/test_locked_metadata_audit.py`
- `tests/unit/test_locked_pe_imports.py`
- `tests/unit/test_markdown.py`
- `tests/unit/test_models.py`
- `tests/unit/test_naming.py`
- `tests/unit/test_normalize.py`
- `tests/unit/test_numpy_native_member_inventory.py`
- `tests/unit/test_p2_capture.py`
- `tests/unit/test_p2_downloader.py`
- `tests/unit/test_p2_urls.py`
- `tests/unit/test_pipeline.py`
- `tests/unit/test_processing.py`
- `tests/unit/test_safe_output.py`
- `tests/unit/test_sandbox_cleanup_ownership.py`
- `tests/unit/test_sensitive_files.py`
- `tests/unit/test_skill_install.py`
- `tests/unit/test_spdx_evidence_verifier.py`
- `tests/unit/test_spdx_sbom.py`
- `tests/unit/test_spdx_sbom_freshness.py`
- `tests/unit/test_spdx_schema.py`
- `tests/unit/test_storage_security.py`
- `tests/unit/test_tasks.py`
- `tools/spdx-schema-check/uv.lock`

</details>

复核发现一个低风险的测试工具信任边界候选，不是已确认的产品漏洞：[`Program.cs`](../native/windows/wfp-policy-plan/tests/Program.cs#L13) 曾暴露 `--sandbox-probe-client`；旧 [`SandboxProbeClient.cs`](../native/windows/wfp-policy-plan/tests/SandboxProbeClient.cs#L8) 只用调用者可设置的环境变量/run token 判断 guest，并在显式命令下向参数指定的目标发送 TCP/UDP DNS 探测。它没有普通产品调用点、不修改 WFP/BFE；操作者显式运行时可能从宿主机发出探测。**§275 已在当前工作树缓解：**移除 CLI 分发，将 helper 改成拒绝 stub，并加入伪造旧 guest 标记/token 的直接回归；锁定 SDK 10.0.401 的离线 harness 为 **15/15**。此修复晚于 §274 冻结快照，不改变 §274 的封存结果。若要恢复 guest 探针，仍需可信 Sandbox 启动与 guest 身份验真，且把目标限制在验收清单内；环境变量或命令行 token 不可作为隔离证明。复核者也指出部分 `.wsb` 文件允许 guest 网络和可写结果共享目录但不自动启动命令；应将这些配置标为实验/停用并注明网络与共享写入范围，避免误作当前生产边界。

此补审没有启动 Sandbox、探针、BFE/WFP 或网络；其后 §275 的验证只运行本地离线 harness，仍不验证真实 guest 隔离效果。P2 仍需 live WFP、身份与回滚验收。

## 历史扫描身份与范围（§270，已由 §274 更新）

- Codex Security Diff Scan：`c5cbf587-9810-463b-a7e0-e9af6f7d6a00`，状态 completed/sealed；冻结摘要 `codex-security-snapshot/v1:sha256:621e8f1c096142cfbf0f7891b2b8bdea98da23539562f138a18f41f72688b8d5`；基线/HEAD：`b166778ee5283591a1b799535b746ba198e38653`。
- 271 个变更路径中，118 个生成 worklist 项全部完成复核；153 个路径未逐行审查。扫描 coverage 为 partial，不能外推成全仓安全结论。
- 覆盖 worklist 包括 Python 28 项、Windows native 67 项、CI/脚本 23 项；当前快照没有报告级 finding。§269 的 Markdown control-character finding 已在扫描快照中缓解。
- §270 没有执行 live BFE/WFP、安装服务、生产浏览器捕获、Sandbox/宿主防火墙操作、远端 CI 或部署；这些运行时门槛仍需独立验收。

## 安全发现

| 分类 | 结果 | 说明 |
|---|---|---|
| 可报告安全漏洞 | 0 | 仅适用于 §270 快照中已逐项复核的 118 个 worklist 项。 |
| 未审路径（历史 §270） | 153/271 | 此数只对应 §270 的历史快照；§274 当前路径核对见上文，不能与其混用。 |
| 生产隔离验收 | 未验证 | 当前默认 URL 捕获缺少已集成的认证 broker/策略验证器，保持 fail closed；原型和离线 fixture 不是生产 WFP 强制执行证据。 |

## 改进项与对策

以下是证据链与纵深防御改进建议，不是本轮确认的漏洞，也没有证据表明目前已发生制品错配或媒体逃逸。

### SEC-267-1（已缓解，仍需远端验收）：CI 未强制验证 SPDX SBOM 与当前锁定输入同步

**观察：** CI 验证已提交 SPDX 文件的 schema，但该检查本身不证明 package set 是由当前 `uv.lock`、Playwright 锁定 sidecar 和许可证证据重新生成的。当前检查材料没有发现已提交 SBOM 的 package set 过期；剩余风险是后续依赖更新时生成物可能漏更新。

**对策及当前状态：** §268 已将锁定输入与 SPDX 渲染新鲜度比较接入 CI，并加入针对性回归。该检查不会重新读取制品归档字节；完整缓存下的原始 verifier 和远端 CI 仍需运行。

**验收证据：** 当前本地 freshness check 与 targeted tests 通过；仍应取得更新后 Windows CI 的远端结果，并确认依赖/sidecar/许可证证据漂移时检查失败。保留输入摘要、生成器版本和输出摘要。

### SEC-267-2（已缓解，仍需新鲜构建验收）：CI 未把 .NET BOM 构建输出摘要与当前构建结果比对

**观察：** BOM 生成器会记录构建输出身份，但 CI 检查主要确认清单非空，未证明清单中的输出路径、大小和摘要与本次锁定 SDK 构建结果一致。当前 source-input hashes 匹配；本轮没有发现已提交输出摘要失配。

**对策及当前状态：** §268 已将路径、大小和 SHA-256 对比接入 Windows CI，并覆盖主构建与两个 related builds。当前本地自比较验证了现有清单与比较器行为；CI 仍须把实际新鲜构建产物与清单对照。

**验收证据：** 更新后的 Windows CI 需对新鲜 pinned build 运行比对；输出被修改/替换、漏记或多记时必须失败。不得把“BOM 存在”或清单自比较当成当前构建身份已验证。

### SEC-267-3：ASR 子进程不是操作系统隔离边界

**观察：** 当前处理 worker 与 CLI 使用相同 OS 身份并继承环境变量。审查没有确认可利用漏洞；该子进程监督和路径约束不等于 OS sandbox。恶意或异常媒体处理代码若被攻破，仍受同一用户权限边界限制。

**对策：** 在面向不可信媒体的部署中，把解码/ASR 放进低权限、资源受限的独立执行边界；限制可写目录和网络访问，传入最小环境变量，并设置 CPU、内存、时长和子进程上限。若暂不实现，应在产品威胁模型与用户文档中清楚保留此限制，不将 worker 描述为 sandbox。

**验收证据：** 在隔离测试环境验证 worker 身份、文件/网络权限、资源上限、取消和异常退出清理；失败时不影响已存在输出或其他任务。

## 仍未通过的项目验收门槛

- **P2：** 生产 WFP store/service/per-lease worker、ACL 与完整枚举可见性证明、安装/回滚、浏览器进程树隔离及 live BFE/Sandbox/网络验收和三条授权成功捕获仍未完成。URL 捕获须继续 fail closed。
- **P4：** 本轮三个 WAV 附件与私有听审包身份匹配，但当前会话无法听辨音频；因此没有漏词、增词、术语或年份判断，也没有修改逐字稿。仍需音频能力审阅者实际核对至少三段；`08:50–09:08` 年份争议还需要 `focus_08m59.wav`。fresh Desktop 模型数据流与隐私验收也未完成。
- **P5：** fresh Desktop Skill 发现与调用 trace 尚未提交。
- **P6：** 所有者的根许可证、发行范围、远端仓库/可见性及远端操作决定，远端 CI 与干净安装仍未完成。

## 建议执行顺序

1. 继续让 URL 捕获保持 fail closed；先补齐 P2 生产服务、身份、策略 readback/rollback 与可回滚环境验收，再考虑启用。
2. 运行更新后的 Windows CI，让它把新鲜 pinned build 与 .NET BOM 对照；补齐 SPDX 与 BOM 的漂移负向用例证据。
3. 对当前 131 条 worklist 外变更路径逐项与冻结快照比对，标记扫描后编辑；在下一次 canonical scan 纳入当前基线并产出可复核 coverage。不要把本报告的 0 finding 扩展成全仓结论。
4. 由可听辨音频的审阅者完成 P4 记录，再由新 Desktop 会话完成数据流/隐私核验和 P5 trace。
5. 获得 P6 所有者决定后，运行约定的远端 CI 与干净安装；在所有发布门槛关闭前保持 **NOT READY FOR RELEASE**。

## 本报告生成边界

本文件和本轮项目状态同步是在冻结安全扫描完成后添加的文档，不属于该扫描快照。没有运行测试；没有读取或复制转写正文、音频内容或私有媒体摘要。

## 后续整改状态（§268，2026-10-13）

- SPDX freshness 与 .NET BOM output identity 检查已加入本地 CI；两项当前清单检查通过，新增针对性测试 **19 passed**，Ruff check/format 通过。SPDX freshness 验证锁文件/许可证证据与完整 SPDX 渲染的一致性，但不会重新读取和哈希制品归档字节。
- .NET output identity 比较器覆盖主构建和两个 related builds 的 **41** 个输出记录。当前只用已提交清单自比较验证了比较器及负向回归；实际 pinned build 与已提交 BOM 的对照仍需 Windows CI 运行结果。
- 这些补丁是在 §267 安全快照封存后编写的，尚未由新的安全扫描审查；完整当前树覆盖、远端 CI、P2/P4/P5/P6 外部验收仍未完成。

## 历史扫描与 finding（§269，2026-10-13；已由 §270 更新）

- **扫描身份：** Codex Security Diff Scan `c7c4b264-8b26-456c-9964-a5c3f1aa8812`，状态 completed/sealed；冻结快照摘要 `codex-security-snapshot/v1:sha256:c34fbf2bd13c8629bc332871443519d1a0ed200ebf7a35a4c88ad41266981f9c`，目标 `b166778ee5283591a1b799535b746ba198e38653`。扫描覆盖 271 个变更路径中的 118 个生成 worklist 项，全部复核；153 个路径未逐行审查，整体 coverage 为 partial。
- **发现：** 1 项低严重度、high-confidence 问题 `csf_38fae865149b977ff5b03971`（CWE-116，规则 `improper-output-neutralization.markdown-cell`），位置为 [scripts/inventory_locked_artifact_members.py](../scripts/inventory_locked_artifact_members.py#L400)。锁文件中的 URL 被接受为任意字符串，Markdown cell 转义处理 HTML、竖线与换行，但未处理回车符；该值会进入生成报告的表格。
- **影响与复现边界：** 离线端到端 PoC 使用合成 TOML 锁文件和匹配摘要/大小的小型 ZIP，可让单个带 CR 的 URL 在生成报告中开始新行/伪造 Markdown 标题，影响本地审计报告的完整性与可读性。PoC 不需要网络；本轮未观察到代码执行或文件路径越界，且下游 Markdown 渲染器影响未验证。该脚本不在 CI 中运行。
- **对策与后续状态：** 建议拒绝 URL 控制字符并按 Markdown 表格上下文编码 CR/LF、反斜线、竖线和 HTML 特殊字符。§270 已落实 URL 控制字符拒绝与 Unicode `Cc` 数字实体编码，定向测试和当前差异扫描通过；本节只记录当时 finding 状态。
- **其他复核项：** Python 产品源码 28 项、Windows native 67 项、CI/脚本 23 项均完成 worklist 复核；未产生其他报告级候选。`check_dotnet_build_bom_outputs.py` 使用 `PurePosixPath.parts` 会折叠 `.` 路径段，但当前仅用于字符串清单校验、未用于文件访问，作为低优先级硬化建议记录，不定性为漏洞。
- **P4 音频状态：** 三个附件在私有听审包中存在。机器 ASR 交叉检查仅提供复听线索：01:11 附近术语有候选差异，05:40 附近 bid/出价术语有候选差异；08:41 片段中两种 ASR 对年份相符，但它在 08:50 结束，不能裁决 08:50–09:08 的 2016/2026 差异。当前会话没有可用的音频感知输入能力，因此没有人工声学结论，也没有改动原稿；该三段听审仍未通过。后一个年份争议还需 `focus_08m59.wav`。
- **回归与本地检查：** Windows Python 3.11 当前全套测试 **712 passed、46 skipped、0 failed**（260.07 秒）；Ruff check/format、SPDX freshness（121 package records）、`git diff --check` 通过。Dotnet build-output 比较器对现有清单的 41 条记录通过自比较，但当前 PATH 无 .NET SDK，本轮未执行新 .NET build；清单自比较不等于当前 pinned build 对照。
- **仍开放门槛：** P2 生产 WFP/service/per-lease 隔离与授权捕获、P4 人工听审及 fresh Desktop 数据流/隐私验收、P5 fresh Desktop trace、P6 owner/license/远端 CI/clean install 均未关闭。报告与项目总审计文档的本次同步发生在冻结快照后，只涉及文档，未进入本扫描。整体状态 **NOT READY FOR RELEASE**。

原始扫描报告保存在当前用户的私有 Codex Security 数据目录，未复制到项目。扫描 ID：`c7c4b264-8b26-456c-9964-a5c3f1aa8812`。

## 当前差异复核与 finding 缓解（§270，2026-10-13）

- **扫描身份与范围：** Codex Security Diff Scan `c5cbf587-9810-463b-a7e0-e9af6f7d6a00` 已封存；目标 HEAD `b166778ee5283591a1b799535b746ba198e38653`，冻结摘要 `codex-security-snapshot/v1:sha256:621e8f1c096142cfbf0f7891b2b8bdea98da23539562f138a18f41f72688b8d5`。118/118 个 worklist 项完成复核，其中 Python 28 项、Windows native 67 项、CI/脚本 23 项；当前扫描 0 个可报告 finding。271 个变化路径中有 153 个未逐行审查，因此 coverage 为 partial。
- **本地缓解：** `inventory_locked_artifact_members.py` 的锁解析器拒绝 URL 中 Unicode `Cc` 控制字符；`_escape_cell` 在 HTML/管道符转义后将所有 `Cc` 控制字符编码为十进制 HTML 实体，避免 CR/LF/TAB 改变 Markdown 行列。JSON/Markdown 产出路径仍使用现有安全写入器。上一轮确认的报表注入样例在此快照中不再复现。
- **验证：** `tests/unit/test_artifact_member_inventory.py` 新增控制字符表格编码、实际 renderer 同行/列检查及 lock URL 拒绝用例；全量测试在功能补丁后 **723 passed、46 skipped、0 failed**（350.39 秒），随后仅对测试源做 Ruff 格式化并重跑该文件：**13 passed、2 skipped**（symlink privilege unavailable）。Ruff 全仓 check 通过，format check 显示 **93 files already formatted**。
- **扫描边界：** 这是工作树差异扫描，不能覆盖未审的 153 个路径或生产运行环境；未执行 live WFP/BFE、Sandbox、浏览器捕获、远端 CI 或部署。报告的本次同步发生在 §270 冻结快照后，文档本身不属于该快照。
- **尚未关闭的验收：** P2 生产 service/WFP/per-lease 隔离、回滚和三条授权成功捕获；P4 人工声学听审与 fresh Desktop 数据流/隐私验收；P5 fresh Desktop trace；P6 所有者 license/发行范围/仓库身份、远端 CI 与 clean install 仍开放。项目继续 **NOT READY FOR RELEASE**。

## 当前工作区安全差异复核（§276，2026-10-13）

- **扫描身份与覆盖：** Codex Security Diff Scan `68b37df7-96b7-4606-a38c-e73b09536f79` 已封存；基线/HEAD 为 `b166778ee5283591a1b799535b746ba198e38653`，冻结摘要 `codex-security-snapshot/v1:sha256:9f9017b8689484cbc1096dde0690b4383486db9190abe458648005511050439d`。权威 worklist **120/120** 项完成；`filesTotal=273`。另有独立只读复核覆盖 worklist 外 **131** 条当前变更路径（`native/tests` 74 条、其他目录 57 条）。当前树 **0 个报告级 finding**。这是一份针对冻结 working-tree diff 的完整静态差异审查，不表示运行时、远端或发布环境已通过。
- **§275 修复复核：** 当前入口拒绝任何 harness 参数，`SandboxProbeClient.Run` 无条件返回 code 2；伪造旧 guest 标记和 run token 不能启用 TCP/DNS 探针。先前 §275 的锁定 .NET 10.0.401 离线 harness 为 **15/15**；本次安全扫描未重跑测试或启动探针。
- **代理边界：** 显式启动的 loopback HTTPS 诊断代理仍受 allowlist、public-IP 和 443 限制，未接入 CLI `BrowserCapture`；它不是服务身份认证或进程级出口隔离。未来若把它用于隔离浏览器，必须补充调用方认证/进程绑定和动态验收。此项作为边界提醒记录，未确认为当前产品漏洞。
- **限制与项目状态：** 本扫描未运行应用、测试、网络、Sandbox、BFE 或 WFP。生产 WFP 服务/策略应用与回滚、浏览器出口隔离、P4 声学听审、远端 CI、许可证和发行授权仍未验证；P2/P4/P5/P6 门槛保持开放，项目继续 **NOT READY FOR RELEASE**。
- **报告同步边界：** 本 §276 说明、项目审核报告的最新摘要及本文件本身是在冻结扫描封存后写入，均未进入扫描快照；它们只同步静态结果与未关闭门槛。
