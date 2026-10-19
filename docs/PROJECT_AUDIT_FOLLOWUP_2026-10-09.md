# 项目后续审核报告

> 本补充报告记录主审核报告第 15–16 节形成时的阶段证据；后续 ASR/浏览器实测、冻结差异安全扫描、锁定发行物许可证证据、P3 回归补验、最新正式安全差异扫描和 P6 上游来源对照见主报告第 17–34 节。评估当前状态时应以主报告第 1 节结论、第 27–34 节以及 `P1_REPORT.md`、`P2_REPORT.md` 为准。

- 审核日期：2026-10-09（Asia/Shanghai）
- 项目：Douyin-Transcript-AgentSkill
- 审核范围：前段记录 SEC-34、DOC-22/23、CLI-01/02 阶段复核；第 15 节增补 CLI-03、SBOM-01 与最新冻结差异复核
- 历史安全差异扫描：Codex Security Diff Scan `9dd6de80-b0ed-4131-ac02-9fbc7dfaa779`，coverage 为 partial；该结果仅属于当时的冻结快照。
- 本次最新续审：CLI-03、SBOM-01 完成后重新执行全套测试与 Codex Security Diff Scan，完整结果见第 15 节。早期 partial 扫描不代表最新扫描的覆盖情况。
- 总结：CLI-02/03 诊断问题已修复，测试基线数字已更新，依赖 SBOM 已生成并通过结构与组件集校验。最新差异扫描对 5/5 项源码/配置完成审查，coverage complete、findings 为空。仍有真实产品验收、跨平台、多账户和发布决策门槛未关闭，项目保持 **NOT READY**。

## 审核结论

以下第 1–14 节保留 CLI-02 阶段的历史证据；其测试和扫描状态由本文件第 15 节的最新续审结果更新。

术语纠错 frontmatter 已从逐规则内容改为仅保存规则集 SHA-256 和汇总计数，解决规则 ID、原词、替换值、备注及逐条次数直接进入 Markdown 元数据的问题，见 `corrections.py:105-112` 和 `pipeline.py:988-993`。完整规则仍保存在受保护的本地任务快照中以供失败重试。规则集 hash 可与已知词典比对；转换后的词语按设计会出现在逐字稿正文。若规则集本身必须保密，应删除确定性 hash，或采用密钥不暴露在 Markdown 的 keyed fingerprint。

`resolve_paths()` 现在拒绝显式空的 `--data-dir` 和 `--output-dir`，避免写任务数据或逐字稿时把空字符串解释成当前目录，见 `config.py:85-99`。配置锚点说明与解析顺序一致。

独立架构复核与人工完成的三项源/配置差异审查均未发现这些源码改动引入新的可报告安全问题。正式扫描已封存且 findings 为空；扫描工具因临时回执文件未能复制到扫描目录，将 canonical coverage 标为 partial 并舍弃无效回执引用。扫描本身是静态复核，不验证真实 ASR、真实抖音链路、跨平台 ACL 或远端 CI。

## 问题与对策

| 编号 | 优先级 | 问题与证据 | 影响 | 对策 | 状态 |
|---|---|---|---|---|---|
| CLI-02 | P4 | `doctor.collect_report()` 捕获无效配置后，旧实现仍将显式空 `output_dir_override` 转成 `Path("")` 并检查当前工作目录；见审计时的 `doctor.py:249-263`。 | 只读诊断目标与配置错误不一致；不会创建目录、写文件或启动转写，不构成已确认的安全漏洞。 | 显式输出路径无效时，将输出路径状态设为 `unknown` 并跳过其可写性和权限探测；回归确认不检查当前工作目录。 | 已修复并复验 |
| DOC-24 | P3 | README 中英文版、`docs/ACCEPTANCE.md` 和整改计划曾把较早测试结果记录为最新。 | 读者可能误判当前测试基线和验证范围。 | README、验收页、整改计划、审核报告和发布报告已统一为 Python 3.11.15/3.12.13 各 385 passed、20 skipped；382/20 与 384/20 保留为历史快照。 | 已修正并再次同步 |

## 当前发布门槛

- P1/P4：需要获授权的真实媒体、ASR 依赖与模型安装许可，以及人工听审和性能记录。
- P2：需要三条获授权的抖音链接，并通过可见浏览器完成真实捕获验收；登录由操作者手动完成。
- P5：需要指定并验证目标 Agent 宿主。
- P6：需要远端 CI、项目所有者的 LICENSE 和仓库决定，以及依赖 SPDX 清单、PyAV/FFmpeg wheel 许可核查。
- POSIX/macOS/Linux 权限、多账户行为和真实浏览器/媒体集成仍未完成。

以上门槛关闭前，项目仍为 **NOT READY**。本报告不构成发布批准。

## 验证记录与限制

- 本次安全审阅为静态代码复核；未运行真实媒体、模型下载、浏览器登录、抖音请求或远端 CI。
- CLI-02 修复后 Windows Python 3.11.15 和 3.12.13 全套离线测试各为 **385 passed、20 skipped**；针对 doctor 的定向回归 2 项通过，全仓 Ruff、敏感文件检查和 `git diff --check` 通过。Python 3.12.13 使用仓库外临时环境和 `UV_OFFLINE=1`。
- CLI-02 回归验证确认：配置状态仍为 invalid，输出目录和权限状态为 unknown，跳过输出权限探测，不检查当前工作目录，也不创建目录。该修复不在上方正式扫描冻结快照中。
- Codex Security 扫描针对冻结工作树摘要，审查清单包含 `config.example.toml`、`config.py` 和 `corrections.py` 三项；人工逐项复核完成。扫描 findings 为空，但正式 coverage 为 partial，因为保存的临时回执不在最终扫描目录中。独立架构复核发现的 CLI-02 已通过后续代码修复和回归关闭，但未纳入该差异扫描。
- Windows 上跳过的 POSIX 权限、FIFO、目录句柄和 symlink 用例不能替代 Linux/macOS 实机验收。

详细历史与整改证据见 [`PROJECT_AUDIT_REPORT.md`](PROJECT_AUDIT_REPORT.md)。

## 15. 2026-10-09 CLI-03、SBOM 与最新复核

- **CLI-03 对策：** `doctor` 保留具体配置错误；只有 CLI 或非空 `DOUYIN_TRANSCRIPT_OUTPUT` 明确提供输出目标时才探测权限。目标不可信或缺失时返回 `unknown` 并跳过探测。定向 `tests/test_doctor.py` 为 **19 passed**。
- **测试结果：** CLI-03 与 SBOM-01 后，Windows Python 3.11.15 和 3.12.13 全套 pytest 各为 **387 passed, 20 skipped**。Python 3.12 使用仓库外临时环境、锁定开发依赖与 `UV_OFFLINE=1`。全仓 Ruff、`uv lock --check`、敏感文件检查和 `git diff --check` 通过。20 项跳过限于 POSIX 专属行为和本机 symlink 能力，仍需跨平台验证。
- **SBOM 与许可证对策（第 15 节阶段状态）：** 当时 `uv.lock` 尚无独立作者声明证据，因此 SPDX 许可证字段标为 `NOASSERTION`；后续对精确锁定发行物的补查及当前声明状态见主审核报告第 24 节。逐包 license/notice 核查和 PyAV/FFmpeg wheel 审查仍需完成。
- **最新安全差异扫描：** Codex Security Diff Scan `db94ca43-2337-42d0-ab6a-7369aeb6ad8e`，base/head `b166778ee5283591a1b799535b746ba198e38653`，snapshot digest `codex-security-snapshot/v1:sha256:d7551c22631fad5ddf12438498f5e587fa6ed4dbaad1b06be51284a506843135`。5/5 项源码/配置审查完成，coverage 为 **complete**，findings 为空。此结论仅限静态差异审查，不代表全仓、运行时或跨平台验收。
- **仍需关闭的门槛与对策：** 授权真实媒体及 ASR/模型安装后完成 P1/P4 听审和耗时记录；取得三条授权抖音链接并手动完成可见浏览器验收；指定 Agent 宿主并确认正文不进入上下文；运行 Windows/macOS/Linux CI 和 Windows 多账户 ACL 验收；完成 33 个依赖的许可证/notice 与 PyAV/FFmpeg wheel 审查；由仓库所有者决定 LICENSE、仓库归属、可见性和发布授权。关闭前保持 **NOT READY**。

## 16. 2026-10-09 真实验收续审

- **用户授权与安装：** 用户批准从锁文件安装 ASR 依赖、下载固定 medium 模型到私有数据目录，并为其提供的 1 条抖音精选页链接批准安装 Playwright/Chromium 和可见浏览器访问。ASR 版本为 faster-whisper 1.2.1、PyAV 15.1.0；模型为 `Systran/faster-whisper-medium@08e178d48790749d25932bbc082711ddcfdfbc4f`。Playwright 1.63.0、Chromium revision 1243 安装成功。`doctor --json` 在显式私有数据与安全输出目录下报告本地转写和 Douyin URL 能力 `ready`。
- **P1/P4：** 尚无本地音视频文件。用户给的是网页链接；本轮没有产出媒体文件、Markdown 或推理结果，所以质量、听审、时间和内存均未测量。P1/P4 仍未通过。
- **P2 实测：** 修正请求类型判定后，可见浏览器的主文档返回 HTTP 200；观察到 14 个页面资源主机，其中 13 个不在 allowlist。新 `retry-failed` CLI 尝试返回 `CAPTURE_NO_MEDIA`，未产出媒体或逐字稿，也未到 ASR。没有记录 Cookie、签名媒体地址、页面正文或转写内容。P2 有 1 条授权链接的部分证据，另外 2 条和三条端到端捕获仍未完成。
- **AUD-70（P2，仍待证据）：** 13 个页面资源主机超出现有浏览器资源 allowlist。仅凭请求元数据无法验证域名归属和必要性，因此本轮没有增加外域；获得可靠证据后再考虑精确 allowlist，并继续与媒体下载 allowlist 分离，保留 HTTPS、公网 IP 校验、DNS pinning 和 lookalike 拒绝。
- **AUD-71（P2/P3，本地整改完成）：** locator 等待现限制为 1 秒；页面导航、登录/元数据查询和浏览器 route DNS 校验共享默认 45 秒绝对 deadline，耗尽时返回 `CAPTURE_TIMEOUT`。各类等待均有超时回归。
- **AUD-72（P2，本地整改完成）：** Playwright 1.63 的 `Request.is_navigation_request` 是方法，原守卫把方法对象当 bool 导致子资源错误套用精确导航 host 策略。现已调用该方法，并用 API 形状一致的 Fake Request 覆盖允许资源与严格导航边界。
- **AUD-73（P3，测试健壮性，已整改）：** Windows UTF-8 CLI 测试原先假设 ASR/浏览器可选依赖未安装，运行环境完成授权设置后错误断言 `setup_required`。现改为校验中文 UTF-8 输出、有效 JSON 及状态与退出码一致，不限定机器依赖状态。
- **本轮验证：** capture/proxy/pipeline 定向回归 **53 passed, 1 skipped**；修复 doctor 用例后，Windows Python 3.11.15 和 3.12.13 完整测试各 **393 passed, 20 skipped**，全仓 Ruff 通过。20 项跳过涉及 POSIX 能力或本机 symlink 支持。
- **域名补查：** 公开 .com RDAP 的注册组织字段被隐去；本机 DNS CNAME 指向共享 CDN 基础设施。无法据此证实 13 个资源主机的归属或页面必要性，故没有扩大 allowlist。第 15 节正式 Diff Scan 仍绑定冻结差异，不覆盖本轮联网行为或后续报告更新。
- **P6 元数据抽查：** 当前 Windows Python 3.11 环境精确安装了 33 个锁记录中的 32 个版本，29 个发行包带 `License-Expression` 或 `License` 字段；Colorama 与 Ruff wheel 有许可文本，Tokenizers 按精确上游 tag 核对。Python 3.12 的 NumPy 2.5.3 未在本环境安装；捆绑组件和 notice 尚未逐包复核，SBOM 继续保留 `NOASSERTION`。本机没有 WSL 发行版，不能在此完成 POSIX 测试。
- **最新完整测试：** 当前 Windows Python 3.11.15/3.12.13 各 **393 passed、20 skipped**；这是 P2 捕获和 AUD-73 修复后的源码证据。第 15 节正式 Diff Scan 仍绑定冻结差异，不覆盖本轮联网行为或这些后续报告更新。
- **发布状态（第 16 节快照）：** 整体仍 **NOT READY**。P1/P4、P2、目标 Agent 宿主、远端 CI、POSIX/macOS/Linux、多账户、第三方许可证审查以及仓库所有者决定仍未关闭。后续状态详见主报告第 17–27 节及 `P1_REPORT.md`、`P2_REPORT.md`。

> 2026-10-09 P6 五个重点 wheel 补查：CTranslate2 4.8.2、FlatBuffers 25.12.19、ONNX Runtime 1.30.0、Tokenizers 0.23.2 和 Ruff 0.14.14 的 Windows wheel 均按 `uv.lock` SHA-256 读取核对；ONNX Runtime wheel 含 `ThirdPartyNotices.txt`，但其内容和组件覆盖仍待审阅。CTranslate2 的 DLL 依赖、Rust 子依赖、其他平台 wheel 与 PyAV/FFmpeg 仍待审查；当时 SPDX 未断言结论，不构成二进制分发批准。详见主审核报告第 21–22 节。

> 2026-10-09 P6 FlatBuffers 映射及最新回归：固定 `flatbuffers 25.12.19` 的旧式 `License: Apache 2.0` 通过严格限定版本、metadata/artifact SHA-256 和三个固定来源的单项规则映射为 `Apache-2.0`；33 个第三方包均有 `licenseDeclared`，项目包与全部 `licenseConcluded` 仍为 `NOASSERTION`。Python 3.11.15/3.12.13 全套各 **399 passed, 20 skipped**，定向 SPDX 各 **6 passed**。项目仍 **NOT READY**；未决验收条件见主审核报告第 1、32 节和 `ACCEPTANCE.md`。
