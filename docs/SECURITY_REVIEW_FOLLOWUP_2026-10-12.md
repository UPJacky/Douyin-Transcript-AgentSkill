# 历史专项安全审核补充报告（2026-10-12）

> **历史状态：** 本文跟进的是当时的 §258/§263 与 2026-10-12 冻结扫描，不代表当前验收状态。最新状态、coverage 与剩余对策见 [2026-10-13 §274 安全审核报告](SECURITY_REVIEW_REPORT_2026-10-13.md)。

- 日期：2026-10-12
- 项目：Douyin-Transcript-AgentSkill
- 关联主报告：[PROJECT_AUDIT_REPORT.md §§256–258](PROJECT_AUDIT_REPORT.md)
- 安全扫描：Codex Security Diff Scan `612a66d5-68a3-4e1c-9bf9-521634f6cbcc`
- 冻结快照：`codex-security-snapshot/v1:sha256:f779936469719881e3d969fdfa833263df3bf3335e94e540b1bdc15b238a8c2b`
- 扫描用量：工作台报告 6,655,957 total tokens（其中 6,440,448 cached input、6,607,442 input、48,515 output）。

## 审核结论

冻结扫描分区静态审查覆盖生成的 **113/113** 个源码/配置审阅项：Windows native 66、Python 25、脚本 17、Skill 配置/schema 3、CI 1、工具配置 1。扫描发现 **1 项 Low / CWE-345** NuGet BOM 来源证明问题；该 finding 已在当前工作树由主报告 §257 实施并定向验证正确摘要绑定。冻结扫描结论没有被追改，新 helper/生成器修复仍要进入下一次安全扫描。

该结论不等于全仓安全通过：工作台统计 257 个变更文件，非源码配置范围的文档、测试、fixture 和生成证据未逐项审查，整体 coverage 为 **partial**。封存器也报告扫描期间工作树发生变化，并因回执文件存放在临时目录而无法链接分区回执；正式扫描报告将 surfaces 标记为 `needs_follow_up`。应把它视为当前源码/配置范围的静态审查结果，不能提升为完整全仓结论。

## 发现与整改

### Low / CWE-345：NuGet BOM 未将实际包内容摘要绑定到锁文件

冻结快照中的 `scripts/generate_dotnet_build_bom.py::_package_record` 分别验证：

- `.nupkg` 实际 SHA-512 与同一可写缓存中的 `.nupkg.sha512` sidecar 一致；
- `.nupkg.metadata` 中的 `contentHash` 与仓库 `packages.lock.json` 一致。

但没有从归档字节独立计算 NuGet canonical `contentHash` 并与锁值比较。缓存 sidecar 与 `.nupkg.metadata` 可由同一缓存写入者协调替换，因此它们彼此吻合并不直接证明归档内容符合锁值。攻击前提是攻击者能写入生成器读取的本地 NuGet 缓存；影响限于本机 BOM 来源证明完整性，当前证据没有显示远程触发路径或直接代码执行。

**修复复核：** §256 中把 `sha512_actual` 与 lock 值直接比较的错误条件已移除。当前生成器构建锁定 SDK 附带的 helper，通过 NuGet `PackageArchiveReader.GetContentHash` 从 `.nupkg` 归档实际字节计算 canonical contentHash，再与 lock 比较。完整归档 raw SHA-512 仍独立对 sidecar，`.nupkg.metadata` 的 contentHash 仍独立对 lock；每个精确包继续运行 `dotnet nuget verify --all`。

**验证：** 使用用户 LocalAppData 中仓库锁定的 .NET SDK 10.0.401；NuGet hash helper Release build 为 **0 warnings、0 errors**。四个真实 signed locked packages 的 SDK API canonical hash 均匹配 lock（4/4），而各自 raw archive SHA-512 均不匹配 lock；BOM 生成成功，四个 `dotnet nuget verify --all` 均通过。BOM 的 233 项 source/generated/output identities 为 **0 missing / 0 mismatches**。`tests/unit/test_dotnet_build_bom.py` **14 passed、1 skipped**，新用例覆盖 raw ≠ canonical 时接受、metadata/sidecar 对齐但实际 canonical hash 与 lock 不同则拒绝，以及 malformed helper output 拒绝。§256 之前的 **11 passed、1 skipped** 属于错误摘要口径，不是 mitigation 证据。

**缓解状态：** 原始 finding 在当前工作树 **mitigated and locally verified**。四个真实缓存签名包提供 API-to-lock 证据，单元测试覆盖接受/拒绝控制流。下次安全扫描须审查 helper 的 SDK assembly 固定引用、输入边界、错误处理和生成器接线，并重放同一攻击模型。

## 其他审查事项

- BOM 目录枚举的静态 symlink/junction 重定向已被当前源码中的 reparse-point 检查拒绝；检查与打开之间仍有并发路径替换的 TOCTOU 边界，需要具备对抗性目录交换的动态验证。
- native/Python/CI 审查未发现其它当前产品路径可达的报告级候选。浏览器捕获仍在缺少验证 broker 时 fail closed；native WFP 代码没有接入可部署的生产写入后端。宿主运行策略没有被更改。
- 用户上传的三段 WAV 与既有听审清单核对一致。私有听审包已有 balanced/medium 与 SenseVoice 本地交叉识别记录；Distil Whisper 对中文输出不适用。当前模型接口不能实际听辨音频，这些 ASR 结果不构成声学验收。没有修改逐字稿。

## 后续对策与项目状态

1. 已由主报告 §258 的最新 Diff Scan 审查 §257 NuGet helper/生成器修复；该扫描覆盖 116 个安全工作项、0 个可报告 finding，但 coverage 仍为 partial。仍需用可审计清单核对未进入 worklist 的改动及其文档、测试、fixtures 和生成证据，避免将 116 条工作项误读为全仓逐文件覆盖。
2. 用人工听辨记录 P4 三段音频的时间点、漏词/增词、术语差异或不确定项；并完成 fresh Desktop 数据流/隐私检查。当前会话没有音频感知接口，ASR 结果不替代人工听审。
3. 保持 P2 生产 service/WFP/per-lease worker 验收、P5 Desktop trace、P6 owner/license/remote 发布门槛开放，直到各自有可复核证据。

项目仍为 **NOT READY FOR RELEASE**。

## 后续状态更新（2026-10-12）

上文记录的是 NuGet finding 的专项复核和当时的待办。§257 已修复 canonical contentHash 与 lock 的绑定，最新 §258 Diff Scan 已审查 helper/生成器及其它安全工作项，未确认新增可报告漏洞。新的、带当前扫描身份和覆盖限制的对策报告见 [SECURITY_REVIEW_REPORT_2026-10-12.md](SECURITY_REVIEW_REPORT_2026-10-12.md)。P2 生产启用前证明、P4 人工听审/Desktop 隐私、P5 Desktop trace、P6 owner/license/remote 发布门槛仍未关闭。

## 本地缓解更新（2026-10-13）

本补充报告对应的冻结扫描记录保持不变。当前工作树已对后续 §262 扫描报告的两项 finding 实施本地缓解：三条 lockfile 解析路径复用 16 MiB 有界读取器，覆盖 shared `_lock_identities` 的 batch/hash 调用；两个未验证 Sandbox guest 边界的 Chromium 诊断脚本改为入口失败 stub，并从 README 移除旧运行步骤。

定向验证：锁文件 reader 与共享调用方 **46 passed、10 skipped**；Sandbox stub 测试 **8 passed**；Ruff、Python `py_compile`、PowerShell AST parsing 与 `git diff --check` 通过。跳过项来自当前 Windows 账户缺少 symlink/junction 创建权限。尚未对这两个修复或当前工作树执行新的 Codex Security 扫描，也未完成全仓安全审查；不要把本地缓解或旧扫描 seal 当作 release clearance。
