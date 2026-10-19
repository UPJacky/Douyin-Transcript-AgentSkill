# Security Review: Douyin-Transcript-AgentSkill

> Policy follow-up: this frozen scan report predates the user's model-proofreading requirement recorded in `PROJECT_AUDIT_REPORT.md` §72. Its recommendation to keep transcript bodies out of Agent context reflects the former policy. The current CLI remains body-free; the Agent Skill may read the body into its configured/default model only after the user requests or approves proofreading and is told the data may reach the model provider.

## Scope

Baseline and independent focused reviews validated four low-severity source-backed findings. Coverage remains partial because not every test, documentation file, or ignored artifact was exhaustively reviewed.

- Scan mode: repository
- Target kind: git_worktree
- Target ID: target_sha256_51308567ddc341b7af7a60bfc88767678a255177604e45c8ede430a3e588328a
- Revision: b166778ee5283591a1b799535b746ba198e38653
- Snapshot digest: codex-security-snapshot/v1:sha256:82e718d7013ed031e38e032d3d7026b579e6c9bd1448e9bbd447b7fdb124c62e
- Inventory strategy: repository
- Included paths: .
- Excluded paths: none
- Artifacts reviewed: skills/douyin-transcript/src/douyin_transcript/asr.py, skills/douyin-transcript/src/douyin_transcript/browser_proxy.py, skills/douyin-transcript/src/douyin_transcript/cache.py, skills/douyin-transcript/src/douyin_transcript/capture.py, skills/douyin-transcript/src/douyin_transcript/cli.py, skills/douyin-transcript/src/douyin_transcript/config.py, skills/douyin-transcript/src/douyin_transcript/corrections.py, skills/douyin-transcript/src/douyin_transcript/doctor.py, skills/douyin-transcript/src/douyin_transcript/downloader.py, skills/douyin-transcript/src/douyin_transcript/errors.py, skills/douyin-transcript/src/douyin_transcript/limits.py, skills/douyin-transcript/src/douyin_transcript/markdown.py, skills/douyin-transcript/src/douyin_transcript/models.py, skills/douyin-transcript/src/douyin_transcript/naming.py, skills/douyin-transcript/src/douyin_transcript/normalize.py, skills/douyin-transcript/src/douyin_transcript/output.py, skills/douyin-transcript/src/douyin_transcript/pipeline.py, skills/douyin-transcript/src/douyin_transcript/processing.py, skills/douyin-transcript/src/douyin_transcript/processing_worker.py, skills/douyin-transcript/src/douyin_transcript/storage_security.py, skills/douyin-transcript/src/douyin_transcript/tasks.py, skills/douyin-transcript/src/douyin_transcript/text_safety.py, skills/douyin-transcript/src/douyin_transcript/urls.py, scripts/check_clean_skill_install.py, scripts/check_sensitive_files.py, scripts/generate_spdx_sbom.py, scripts/spdx_terminal_safety.py, scripts/verify_spdx_evidence.py, skills/douyin-transcript/pyproject.toml, skills/douyin-transcript/uv.lock, skills/douyin-transcript/SKILL.md, skills/douyin-transcript/references/CLI_REFERENCE.md, skills/douyin-transcript/references/INSTALL.md, skills/douyin-transcript/scripts/douyin-transcript, skills/douyin-transcript/scripts/douyin-transcript.ps1, scripts/douyin-transcript, scripts/douyin-transcript.ps1, scripts/douyin-transcript-doctor, .github/workflows/ci.yml, .gitignore, pytest.ini, SECURITY.md, tests/unit/test_p2_capture.py, tests/unit/test_browser_proxy.py, tests/unit/test_p2_urls.py, tests/unit/test_p2_downloader.py, tests/unit/test_pipeline.py, tests/unit/test_tasks.py, tests/unit/test_sensitive_files.py, tests/unit/test_spdx_evidence_verifier.py, tests/unit/test_spdx_sbom.py, docs/ACCEPTANCE.md, docs/PROJECT_AUDIT_REPORT.md, docs/P2_REPORT.md, docs/RELEASE_REPORT.md
- Scan context: Offline Standard security review of current Douyin transcript CLI and Agent Skill, focusing on URL validation/download, Chromium capture, local transcript privacy, task persistence, media processing, and software supply-chain controls.

Limitations and exclusions:
- Static, offline, read-only review; no tests, browser run, package resolution, network requests or external URL access during this scan.
- Previously recorded local Chromium UDP evidence was not repeated; it establishes local packet delivery only, not public Internet delivery or response reading.
- P1/P4 media acceptance, P2 live capture, fresh Desktop Skill invocation, owner licensing/distribution choices and remote cross-platform CI remain outstanding.

### Scan Summary

| Field | Value |
| --- | --- |
| Scan outcome | completed |
| Reportable findings | 4 |
| Severity mix | low: 4 |
| Confidence mix | high: 1, medium: 3 |
| Coverage | partial |
| Validation mode | offline_read_only |

Canonical artifacts: `scan-manifest.json`, `findings.json`, and `coverage.json`. This report is a deterministic projection of those files.

## Threat Model

# Threat Model

The repository implements a local-first Douyin transcription CLI packaged as an Agent Skill. It normalizes a URL or validates a local file, records a task in SQLite, captures browser media when needed, downloads media to a local cache, runs local faster-whisper, and writes Markdown output. No service or tenant model is documented. This generated architecture model is based on offline source review and is not complete audit coverage. Evidence: docs/ARCHITECTURE.md:3-20,40-56.

## Assets

- Transcript text, timestamps, titles, and generated Markdown files; output summaries omit transcript bodies. Evidence: pipeline.py:1015-1063; output.py:13-80; CLI_REFERENCE.md:40,50.
- Task metadata in <data_dir>/tasks.sqlite3, including sanitized source URLs, local input paths, titles, state, output paths, digests, errors, and serialized task options. Evidence: tasks.py:498-530,704-745; pipeline.py:600-608.
- Browser profile and persistent login cookies under <data_dir>/browser-profile. Evidence: pipeline.py:469-474; capture.py:153-168; INSTALL.md:117.
- Downloaded media under <data_dir>/media-cache and selected local media read from its original path. Evidence: pipeline.py:640-645; downloader.py:268-272,364,481; tasks.py:704-745.
- Pinned ASR model artifacts and optional custom terminology rules. Evidence: models.py:37-53,363-423; cli.py:926-990,1045-1068; pipeline.py:600-608.

## Trust Boundaries

- An Agent or other caller invokes the CLI. The canonical Skill instructs callers to use structured argv, obtain authorization, require manual login, and avoid putting transcript bodies into agent context; these are host instructions, not Python-enforced filesystem isolation. Evidence: .codex/skills/douyin-transcript/SKILL.md:6-10; skills/douyin-transcript/SKILL.md:11,15-22,50-56.
- User-selected URLs and local files cross into URL validation, browser capture, download, and media decoding. The application applies separate validation in those components. Evidence: urls.py:107-166,194-252; downloader.py:168-212,523-599; asr.py:152-200.
- Browser HTTP(S)/WSS traffic passes through Playwright request controls and a local proxy; Chromium WebRTC UDP is a separate OS-network boundary not established by those controls. Evidence: capture.py:550-588; browser_proxy.py:36-57,94-141,303-350; docs/P2_REPORT.md:44-49.
- The processing worker receives local media paths and exchanges bounded JSON frames with its parent, but runs under the same account and inherited environment; supervision and timeouts do not establish privilege isolation. Evidence: processing.py:213-240,273-280; processing_worker.py:27-60,66-108.
- Setup/install crosses from the local CLI to package, model, and browser download sources and writes into separate environment, cache, model, and browser locations. Destinations and endpoint overrides depend on configuration. Evidence: cli.py:913-975,1012-1068,1113-1148.

## Attacker Capabilities

- A remote page or media host reached for an authorized URL can return untrusted content for browser handling or media decoding; URL, host, size, and timeout controls exist, but their full security effectiveness is not established by this model. Evidence: urls.py:107-166,194-252; capture.py:550-588; downloader.py:224-320,523-599.
- A user-selected local media file and explicitly selected terminology dictionary can contain malformed or sensitive content. Evidence: CLI_REFERENCE.md:27-33; downloader.py:168-212; cli.py:414-445.
- A local principal with sufficient rights to the process or files can access application data; the repository documents limits against same-user, administrator, or root access. Evidence: README.md:47; docs/ARCHITECTURE.md:46.
- A same-machine principal may matter where existing directory permissions, path races, or explicit shared output locations are involved. New private directories receive restrictive permissions, while existing path state is inspected rather than automatically repaired. Evidence: storage_security.py:215-248,324-406.

## Security Objectives

- Process content authorized by the user and do not bypass authentication, CAPTCHA, DRM, or access controls. Evidence: SECURITY.md; skills/douyin-transcript/SKILL.md:15-22.
- Keep transcript bodies in local Markdown and omit them from CLI JSON summaries and Agent context. Evidence: docs/ARCHITECTURE.md:40-46; output.py:13-80; skills/douyin-transcript/SKILL.md:50-56.
- Protect local task data, browser profile, media cache, model files, and output according to their configured locations and applicable permission checks. Evidence: storage_security.py:215-248,324-406,924-970,1003-1068; tasks.py:359-393.
- Restrict URL and media retrieval through validation, public-address checks, pinned connections, bounded redirects, and download limits; keep browser and downloader controls distinct. Evidence: urls.py:194-252,513-626; browser_proxy.py:94-141; downloader.py:224-320,523-599.
- Use pinned local ASR model revisions and avoid sending transcript content to a third-party LLM service. Evidence: models.py:37-53,397-423; asr.py:105-149; docs/ARCHITECTURE.md:44.

## Assumptions

- No actual deployment configuration, environment values, user config, mounts, container policy, or process profile was supplied. Paths and endpoints below are resolved as source precedence formulas, not asserted live values.
- The data root precedence is explicit --data-dir, DOUYIN_TRANSCRIPT_HOME, [paths].data_dir, then the platform default. Output separately resolves explicit CLI option, environment, config, then <data_dir>/output. No actual environment/config values were supplied. Evidence: config.py:88-159; doctor.py:25-58.
- Documentation conflicts on unsafe or unknown output permissions: README.md:47 and the remediation plan describe advisory behavior broadly, while README.md:49, CLI_REFERENCE.md:11, and pipeline.py:124-129 show that an implicit default path is refused and an explicitly configured path is advisory. This is a documentation discrepancy to correct.
- The P2 report records a synthetic WebRTC test reaching loopback/LAN receivers, while stating public Internet delivery and remote exploitability were not established. This is unresolved impact evidence, not proof of public egress. Evidence: docs/P2_REPORT.md:44-49; docs/PROJECT_REMEDIATION_PLAN.md:36,45.
- Root SECURITY.md defines reporting and privacy guidance, but the supplied context declares no released-version support window or repository reporting channel. The reviewed CI workflow is build/test oriented and does not establish a release workflow. Evidence: SECURITY.md; .github/workflows/ci.yml:1-75; docs/PROJECT_AUDIT_REPORT.md:1338.
- This scan is offline source inspection only. It did not execute the application, inspect Git history, verify live deployment settings, or complete file-by-file audit coverage. Evidence: docs/PROJECT_AUDIT_REPORT.md:1365.

---

## Saved Model Context

- Source: scan
- Scan: 9d565b94-4fc8-47b9-8939-ca8c43ad6fe2
- Target: Douyin-Transcript-AgentSkill
- Revision: b166778ee5283591a1b799535b746ba198e38653
- Snapshot: codex-security-snapshot/v1:sha256:82e718d7013ed031e38e032d3d7026b579e6c9bd1448e9bbd447b7fdb124c62e
- Result status: draft
- Model origin: not recorded
- Model scope: not recorded
- Scan scope: .
- Scan scope description: Generated threat model followed by baseline, independent architecture, and focused source reviews. The full worktree snapshot contains 97 files; coverage is partial because several source, test, documentation, and supply-chain files were not fully audited. No runtime tests or network requests were performed in this scan.

This is a provisional model saved before successful completion.


---

## Saved Model Context

- Source: scan
- Scan: 9d565b94-4fc8-47b9-8939-ca8c43ad6fe2
- Target: Douyin-Transcript-AgentSkill
- Revision: b166778ee5283591a1b799535b746ba198e38653
- Snapshot: codex-security-snapshot/v1:sha256:82e718d7013ed031e38e032d3d7026b579e6c9bd1448e9bbd447b7fdb124c62e
- Result status: draft
- Model origin: reconciled
- Model scope: not recorded
- Scan scope: .
- Scan scope description: Baseline and independent focused reviews validated four low-severity source-backed findings. Coverage remains partial because not every test, documentation file, or ignored artifact was exhaustively reviewed.

This is a provisional model saved before successful completion.



## Findings

| Finding | Severity | Confidence | Detailed write-up |
| --- | --- | --- | --- |
| [CI 动态安装的 Skill 校验器依赖未纳入哈希锁定环境](#finding-1) | low | medium | inline below |
| [浏览器捕获可向受控代理之外发送 WebRTC UDP](#finding-2) | low | medium | inline below |
| [失败任务重试可沿用旧版共享输出目录](#finding-3) | low | high | inline below |
| [本地安装时 PEP 517 构建后端未纳入制品哈希锁](#finding-4) | low | medium | inline below |

### Confidence Scale

| Label | Meaning |
| --- | --- |
| high | Direct evidence supports the finding with no material unresolved blocker. |
| medium | Evidence supports a plausible issue, but material runtime or reachability proof remains. |
| low | Evidence is incomplete and the item is retained only for explicit follow-up. |

<a id="finding-1"></a>

### [1] CI 动态安装的 Skill 校验器依赖未纳入哈希锁定环境

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | medium |
| Confidence rationale | 工作流直接调用 uvx 安装工具且仓库 uv.lock 中没有 skills-ref；本扫描未进行网络或制品来源校验。 |
| Category | software supply chain integrity |
| CWE | CWE-829 |
| Affected lines | .github/workflows/ci.yml:51-52, skills/douyin-transcript/uv.lock:93-125 |

#### Summary

CI 在 push 和 pull request 工作流中通过 `uvx --from skills-ref==0.1.1` 下载并运行 Skill 校验器。直接版本号固定，但该临时工具环境及其传递依赖不在仓库锁文件或哈希清单内；若配置的软件源或依赖制品被攻陷，安装/运行时可在 GitHub runner 上执行攻击者代码。

#### Root Cause

CI verifies app dependencies through `uv.lock`, but the Agent Skill metadata step runs `uvx` with only a direct version pin. Its ephemeral dependency graph is not bound to repository artifact hashes, so package installation integrity is weaker for executable validation code.

#### Validation

The workflow invokes `uvx --from skills-ref==0.1.1`; repository lock search found no `skills-ref` record. No package compromise was observed or verified.

Validation method: offline source and lockfile inspection

Evidence:
- .github/workflows/ci.yml:8-9,51-55
- skills/douyin-transcript/uv.lock:93-125

Counterevidence and remaining uncertainty:
- The direct skills-ref version is exact.
- All three GitHub Actions are pinned by full commit SHA.
- Workflow permissions are contents: read.

Limitations:
- No network request, package artifact verification or CI runner execution was performed.

#### Dataflow

CI push/pull_request trigger -\> uvx package resolution -\> skills-ref and transitive installation -\> validator process on GitHub runner

- **Source:** Configured package index and validator dependency graph

- **Sink:** Code executed on the GitHub-hosted CI runner

- **Outcome:** Runner executes unverified package code during metadata validation

#### Reachability

The attacker must compromise a dependency release or package-index artifact that the runner resolves. No evidence of such compromise was found.

- **Attacker:** Package maintainer or package-index attacker

- **Entry point:** Validate Agent Skill metadata CI step

- **Outcome:** Code executes within the runner permission boundary

Preconditions:
- A CI push, pull request, or manual run occurs.
- The package index supplies a compromised direct or transitive artifact.

#### Severity

**Low** — 安装型 CI 依赖带来 runner 代码执行的供应链风险，但需要软件源、版本发布或传递依赖遭到攻陷；当前没有恶意制品证据，工作流权限为 contents: read。

若该 job 可读取 secrets、写入制品/仓库，或校验器的传递依赖可被未授权替换，应提高严重度；若完整依赖图经哈希锁定且 CI 离线安装，应关闭。

Impact assessment:
- **Level:** low
- **Why:** Potential runner code execution is bounded by the current contents:read permission and no verified secrets exposure.

Likelihood assessment:
- **Level:** low
- **Why:** Requires upstream package or index compromise; direct package version is pinned.

#### Remediation

Add `skills-ref` and its complete transitive dependency graph to a hash-locked CI environment, then invoke it through `uv run --locked` or an equivalent verified offline tool environment.

Tests:
- Verify the validator command succeeds with network access disabled after installing the checked-in locked environment.
- Ensure lock updates include exact validator versions and artifact hashes.

Preventive controls:
- Require hash-locked environments for executable CI tools, not only application dependencies.
- Retain least-privilege workflow permissions and action SHA pinning.

<a id="finding-2"></a>

### [2] 浏览器捕获可向受控代理之外发送 WebRTC UDP

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | medium |
| Confidence rationale | 源代码和项目记录的锁定二进制实测共同支持代理旁路；试验本次未复跑，且允许页面上的远程脚本执行路径未证实。 |
| Category | network access control |
| CWE | CWE-923 |
| Affected lines | skills/douyin-transcript/src/douyin_transcript/capture.py:153-168, skills/douyin-transcript/src/douyin_transcript/browser_proxy.py:114-143, tests/unit/test_p2_capture.py:545-558 |

#### Summary

若获准打开的页面执行攻击者控制或已被攻陷的脚本，`BrowserCapture` 可使 Chromium 向 loopback 或局域网地址发送未经过 host allowlist、DNS pinning 和 HTTP CONNECT 代理的 WebRTC UDP。项目记录的锁定 Chromium 实测显示，即使启用 `disable_non_proxied_udp`，合成 STUN 数据仍到达本机接收端；当前未证明公网传输、读取响应或进一步利用。

#### Root Cause

The capture path relies on HTTP proxy and Playwright controls plus a Chromium policy flag. The proxy handles HTTPS CONNECT over TCP; none of these controls confines separate Chromium UDP sockets. The repository records a locked-Chromium test where synthetic STUN packets still reached local loopback and LAN receivers.

#### Validation

Source confirms proxy-only TCP mediation and no process-level network isolation. The prior local experiment reports UDP delivery despite the flag, allowlist, routes, proxy and DNS pinning.

Validation method: static source trace plus prior local locked-Chromium experiment recorded in repository

Evidence:
- capture.py:145-168
- browser_proxy.py:94-143,303-350
- tests/unit/test_p2_capture.py:500-634
- docs/P2_REPORT.md:44-49
- docs/PROJECT_AUDIT_REPORT.md:1182-1188

Counterevidence and remaining uncertainty:
- The application passes and protects the disable_non_proxied_udp flag.
- No external UDP destination, response reading or service exploitation was demonstrated.
- Attacker-controlled script execution on an allowed Douyin page is unconfirmed.

Limitations:
- Prior local UDP evidence was not repeated during this offline review.

#### Dataflow

Allowed page script -\> Chromium WebRTC UDP socket -\> local loopback/LAN receiver

- **Source:** Script executing in an allowed or compromised Douyin page

- **Sink:** Chromium UDP socket

- **Outcome:** Local receiver gets UDP packets outside host allowlist and DNS pinning

#### Reachability

The user must open an allowed page and attacker-controlled or compromised script must execute there; this prerequisite is unverified.

- **Attacker:** Remote party able to cause script execution on an allowed page

- **Entry point:** BrowserCapture navigation to an authorized Douyin URL

- **Outcome:** UDP packets reach a loopback or private-interface listener

Preconditions:
- User initiates browser capture.
- Attacker-controlled script executes in the allowed page context.

Limitations:
- Existing evidence does not establish public Internet egress or a successful exploit.

#### Severity

**Low** — 实测确认 UDP 包能到达本机 loopback/LAN 接收端，但没有证明公网外传、读取响应或进一步利用；攻击者还需先在允许页面上下文执行脚本。

若证明允许页面上的攻击者脚本可读取本地服务响应或向公网传输数据，应提高严重度；若锁定 Chromium 的进程级隔离证明所有直接 UDP 均被拒绝，应降低或关闭。

Impact assessment:
- **Level:** low
- **Why:** Only local UDP reachability is confirmed; response reading, exfiltration and further service impact are unproven.

Likelihood assessment:
- **Level:** low
- **Why:** Script execution on the allowed origin is unconfirmed.

#### Remediation

Add fail-closed process-level egress isolation for Chromium and its complete child-process tree. Permit only TCP to the controlled proxy and block direct UDP, loopback and private-network egress. Verify UDP denial and approved HTTPS capture using the locked Chromium build.

Tests:
- With locked Chromium, verify synthetic WebRTC UDP is denied to loopback and LAN receivers over IPv4 and IPv6.
- Verify browser descendants cannot outlive or bypass isolation after setup failure or helper termination.
- Verify approved HTTPS capture through the controlled proxy still succeeds.

Preventive controls:
- Keep host/DNS request controls and OS-level process egress isolation as separate required controls.
- Block release acceptance until locked-browser UDP-denial and HTTPS-positive tests pass on supported platforms.

<a id="finding-3"></a>

### [3] 失败任务重试可沿用旧版共享输出目录

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | high |
| Confidence rationale | 存储审查与当前 CLI、快照校验、流水线默认目录保护和 Markdown 发布调用链相互印证。 |
| Category | filesystem permissions |
| CWE | CWE-732 |
| Affected lines | skills/douyin-transcript/src/douyin_transcript/cli.py:697-715, skills/douyin-transcript/src/douyin_transcript/cli.py:831-850, skills/douyin-transcript/src/douyin_transcript/cli.py:893-908, skills/douyin-transcript/src/douyin_transcript/pipeline.py:124-129, skills/douyin-transcript/src/douyin_transcript/pipeline.py:585-608, skills/douyin-transcript/src/douyin_transcript/markdown.py:328-340 |

#### Summary

AUD-79 修复后，合法的 schema 1/2 失败任务快照仍可能保存旧版默认共享输出路径。重试时若未显式提供 `--output-dir`，CLI 会沿用快照路径；由于快照未记录该路径是默认值还是显式指定，重试不会把它标记为受保护的默认输出，CLI 只提示 ACL 风险，流水线保护也不会阻止写入。拥有该共享目录读取权限的本机用户可能读取重试生成的转写正文。

#### Root Cause

旧版处理快照只保存解析后的 output_dir，不记录该路径是用户显式选择还是旧版隐式默认值。重试逻辑因此无法区分历史默认路径与有意共享的路径，并把安全判断限制在当前默认值路径。

#### Validation

合法 schema 1/2 快照只要求 output_dir 为非空字符串并规范化路径；重试未传 --output-dir 时选择快照路径，权限检查只告警，而 pipeline 仅在 output_dir_is_default 为真时阻止不安全目录。

Validation method: offline source trace plus independent focused storage review

Evidence:
- skills/douyin-transcript/src/douyin_transcript/cli.py:697-715
- skills/douyin-transcript/src/douyin_transcript/cli.py:831-850,893-908
- skills/douyin-transcript/src/douyin_transcript/pipeline.py:124-129,585-608
- skills/douyin-transcript/src/douyin_transcript/markdown.py:328-340

Counterevidence and remaining uncertainty:
- 新任务默认写入 `<data_dir>/output`，当前默认值重试受流水线权限检查保护。
- 用户明确指定的共享输出路径属于受支持行为。

Limitations:
- 本轮为静态只读审查，未构造历史快照重跑。
- 跨账户读取取决于本机共享目录 ACL；未在本次审查中验证具体账户权限。

#### Dataflow

旧版失败任务快照 -\> retry-failed 无显式 --output-dir -\> 沿用历史共享 output_dir -\> Markdown 发布转写文件

- **Source:** schema 1/2 快照的 output_dir 字段

- **Sink:** Markdown 原子发布写入输出目录

- **Outcome:** 共享 ACL 下生成的转写正文可被其他本机账户读取

#### Reachability

本机其他用户需能读取旧版共享默认输出目录；操作员需执行对旧失败任务的重试。

- **Attacker:** 具有旧共享输出路径读取权限的本机用户

- **Entry point:** 对升级前生成的失败任务执行 retry-failed

- **Outcome:** 读取共享 ACL 下的转写文件

Preconditions:
- 任务有有效 schema 1 或 2 快照并保留旧版隐式默认目录。
- 重试未显式提供 --output-dir。
- 共享目录 ACL 允许另一账户读取输出。

#### Severity

**Low** — 影响限于旧版失败快照在未显式指定新输出目录时的重试；利用者需有旧共享目录读取权限，本次未证明更广泛的跨账户暴露。

若有效旧快照能在共享路径稳定复现跨账户读取，应提高影响评估；若重试已拒绝不安全或来源不明的快照路径，应关闭。

Impact assessment:
- **Level:** low
- **Why:** 只有拥有旧共享目录读取权限的本机用户能读取产物；未确认存在符合前置条件的真实旧任务。

Likelihood assessment:
- **Level:** low
- **Why:** 需要旧版本产生的有效失败任务快照，并且操作员重试时没有指定新的输出目录。

#### Remediation

对重试快照中的不安全或来源不明输出目录 fail closed：要求用户显式传入 `retry-failed --output-dir`，或迁移/拒绝已知旧版隐式默认路径。后续快照应保存输出目录来源，区分用户明确选择与默认配置。

Tests:
- 构造 schema 1 和 2 的旧失败任务快照并使用共享 ACL 路径；不传 --output-dir 时应拒绝写入并提示显式选择。
- 对同一快照显式传入私有 --output-dir 后，确认重试成功且结果只写入指定目录。
- 验证新任务与当前默认路径的重试仍保持现有 ACL 保护。

Preventive controls:
- 在任务快照中持久化 output_dir 来源。
- 将历史快照重试兼容场景加入输出权限回归用例。

<a id="finding-4"></a>

### [4] 本地安装时 PEP 517 构建后端未纳入制品哈希锁

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | medium |
| Confidence rationale | pyproject 声明 PEP 517 后端且安装文档使用 uv sync --locked；锁文件只有项目及应用/dev依赖，没有 hatchling 记录。uv 构建隔离行为未在本次只读扫描中动态验证。 |
| Category | software supply chain integrity |
| CWE | CWE-829 |
| Affected lines | skills/douyin-transcript/pyproject.toml:1-3, skills/douyin-transcript/references/INSTALL.md:5-14, skills/douyin-transcript/uv.lock:93-125 |

#### Summary

文档用 `uv sync --locked` 安装本地 Skill 包，但 `pyproject.toml` 的 PEP 517 后端是 `hatchling==1.27.0`，该构建依赖和隔离构建环境不在 `uv.lock` 的制品哈希记录中。被攻陷的构建制品可在安装时以当前用户权限执行代码。

#### Root Cause

The project lock protects the application's resolved requirements, but the backend declared in `[build-system]` is resolved in the separate PEP 517 build environment. The exact backend version limits version drift but does not bind the downloaded artifact to a recorded hash.

#### Validation

The project metadata declares hatchling as the PEP 517 backend, installation documentation instructs `uv sync --locked`, and the repository lock has no hatchling record. The build-isolation behavior was not dynamically tested.

Validation method: offline source and lockfile inspection

Evidence:
- skills/douyin-transcript/pyproject.toml:1-3
- skills/douyin-transcript/references/INSTALL.md:5,12
- skills/douyin-transcript/uv.lock:93-125

Counterevidence and remaining uncertainty:
- The hatchling version is exact.
- Application runtime and development requirements are locked and include artifact hashes.
- No malicious artifact was observed.

Limitations:
- No network/package verification or dynamic uv build was performed.

#### Dataflow

uv sync --locked -\> PEP 517 build isolation -\> hatchling artifact resolution -\> build backend execution under installer account

- **Source:** Configured Python package index and build-system requirement

- **Sink:** PEP 517 backend process during local installation

- **Outcome:** Build backend code runs with installer-user privileges

#### Reachability

The attacker must compromise an artifact or index used to satisfy the build requirement. No malicious artifact was observed.

- **Attacker:** Package maintainer or package-index attacker

- **Entry point:** Documented local source installation using uv sync --locked

- **Outcome:** Build backend code executes during installation

Preconditions:
- The user installs the source checkout.
- The package source supplies a compromised build backend artifact.

#### Severity

**Low** — 构建后端在安装阶段可执行代码，但需要软件源或制品遭到攻陷；后端版本已精确固定，应用正常依赖有锁文件和哈希，未发现恶意制品。

若用户依赖企业批准索引或可验证的构建制品，这一风险可降低；若构建环境还能访问高权限凭证或持续集成秘密，应提高严重度。

Impact assessment:
- **Level:** low
- **Why:** Code execution occurs under the installing user's privileges but requires upstream package/index compromise.

Likelihood assessment:
- **Level:** low
- **Why:** The backend is version-pinned and application dependencies are lock-pinned.

#### Remediation

Hash-lock the PEP 517 build backend and its isolated build dependencies in a dedicated trusted build environment, or distribute and verify a prebuilt package artifact rather than resolving the build environment during installation.

Tests:
- Verify source installation succeeds with network access disabled after provisioning the hash-locked build toolchain.
- Ensure the build environment rejects backend artifacts whose hashes do not match the reviewed lock.

Preventive controls:
- Track build-system dependencies and runtime dependencies in a reproducible, artifact-hash-verified toolchain.
- Require provenance or a trusted prebuilt artifact for release installation paths.

## Reviewed Surfaces

| Surface | Risk Area | Outcome | Notes |
| --- | --- | --- | --- |
| CLI、配置、安装与 doctor | CLI input handling, configuration precedence, installation behavior | Reported | Focused CLI/config/doctor review found no separate issue beyond the storage-linked retry path: valid legacy schema 1/2 snapshots can retain a historical shared output_dir and bypass the current-default fail-closed check unless retry supplies --output-dir. |
| URL 校验、DNS 与媒体下载 | SSRF, DNS rebinding, redirect and media-parser boundaries | No issue found | Focused review found no supported SSRF path: URL/redirect hops are revalidated; DNS answers must be public and HTTPS pins the validated IP; redirects, bytes and deadlines are bounded; media decoding uses a supervised worker and denies nested I/O. Evidence: urls.py:194-251,374-553; downloader.py:224-342,523-600,670-771; tests/unit/test_p2_urls.py; tests/unit/test_p2_downloader.py. |
| Playwright 浏览器捕获与代理 | Browser process network egress | Reported | Validated existing AUD-77. Locked Chromium delivered synthetic STUN UDP to loopback/LAN despite the WebRTC flag and HTTP proxy. This confirms local UDP delivery only; external delivery and response reading are unproven. |
| 媒体处理、ASR 与模型管理 | Untrusted media, process IPC, model loading | No issue found | Baseline reviewed ASR, model resolution, worker IPC and media processing controls. No additional concrete security finding survived; the worker is not a reduced-privilege sandbox. |
| 任务状态、权限与 Markdown 输出 | Filesystem permissions, task database, cache cleanup and output | Reported | Storage review fully covered tasks.py, cache.py, storage_security.py, markdown.py, output.py, config.py and naming.py; it validated a residual AUD-79 path where legacy schema 1/2 retries can reuse an old shared default output_dir. Focused tests were inspected by relevant sections, not end-to-end. |
| 测试、安全与发布文档 | Test coverage, repository policy, release and dependency evidence | Needs follow-up | SECURITY.md and CI were checked; general docs/tests remain partially reviewed. |
| CI and local package build-tool dependencies | Build and CI dependency integrity | Reported | Parent validation confirmed two low-severity CWE-829 findings: uvx installs the Agent Skill validator outside the repository hash lock, and the PEP 517 hatchling build backend is absent from uv.lock. Neither candidate implies a known compromised package. Evidence: .github/workflows/ci.yml:51-52; pyproject.toml:1-3; INSTALL.md:5,12; uv.lock:93-125. |

## Open Questions And Follow Up

- Can attacker-controlled or compromised script execute through an allowed Douyin page path?
- Can supported operating systems block Chromium loopback, private-network and direct UDP traffic while permitting approved HTTPS through the proxy?
- Does uv's actual configured build-isolation path resolve hatchling independently of uv.lock, as source configuration indicates?
- Which exact documentation and test files in the 97-file snapshot remain only partially reviewed?
- Does the current worktree match all target operating systems and remote CI release configurations?
- Which precise documentation and test files in the 97-file snapshot were not fully reviewed?
- Does uv's actual configured build-isolation path resolve hatchling independently of uv.lock, as the source configuration indicates?
- Can attacker-controlled or compromised script execute through a page path hosted on an allowed Douyin origin?
- Can the supported operating systems reliably block all Chromium loopback, private-network, and direct UDP traffic while permitting approved HTTPS through the controlled proxy?
- Which exact remaining docs and tests in the 97-file snapshot were not fully reviewed?
- 允许站点的哪些实际脚本执行路径可以触发未代理的 WebRTC UDP？
- 哪些浏览器进程隔离方案能在支持的 Windows 环境稳定阻断 loopback、私网及直接 UDP，同时保持批准的 HTTPS 捕获？
- 当前工作树是否与所有目标操作系统和远端 CI 的实际发布配置一致？
- Linux/macOS and remote CI results cannot be established by this offline Windows worktree review.
  - Follow-up prompt: Review deferred unit runtime_cross_platform_ci and close its stated proof gap.
- No authorized local Chinese media sample of at least 60 seconds was supplied.
  - Follow-up prompt: Review deferred unit p1_real_media and close its stated proof gap.
- Only one user URL was supplied and the prior attempt returned CAPTURE_NO_MEDIA; two more URLs and three successful distinct captures remain required.
  - Follow-up prompt: Review deferred unit p2_live_capture and close its stated proof gap.
- A fresh Desktop session must verify Skill discovery and invocation.
  - Follow-up prompt: Review deferred unit p5_desktop_skill and close its stated proof gap.
- Repository license, distribution scope and maintainer decisions remain owner choices.
  - Follow-up prompt: Review deferred unit p6_owner_choices and close its stated proof gap.
- Some in-scope repository paths were reviewed only partially; focused reviews covered storage and supply-chain source paths, but general tests/docs and ignored artifacts were not exhaustively reviewed.
  - Follow-up prompt: Review deferred unit unreviewed_paths and close its stated proof gap. Paths: tests/\*\* (focused cases/sections only), docs/\*\* (not all documents fully reviewed), ignored local build/test caches and user-provided project archive.
- This scan was offline and did not rerun the Windows runtime suite.
  - Follow-up prompt: Review deferred unit runtime_windows_execution and close its stated proof gap.
- Process-level egress isolation and locked Chromium UDP-denial/approved-HTTPS dynamic acceptance remain unimplemented and unverified.
  - Follow-up prompt: Review deferred unit browser_process_egress and close its stated proof gap.

## Follow-up diff scan — 2026-10-10

Codex Security Diff Scan `81745f42-fe5b-4151-845c-95c70da451ee` completed against working-tree snapshot `codex-security-snapshot/v1:sha256:9142fc74cb252800be19259804af998e48c322ca17957d291b4c04f00ac50a1f`, relative to `b166778ee5283591a1b799535b746ba198e38653`. It reviewed the changed-source/configuration inventory (16 items) plus the P2 dynamic-evidence record. The scan reported one finding, the existing AUD-77 Chromium WebRTC UDP proxy bypass (low severity, medium confidence); it found no additional reportable issue in the other reviewed surfaces. The scan reused prior locked-Chromium local UDP evidence and did not rerun tests or browser/network checks.

After that scan snapshot was sealed, the clean-install helper, its focused unit tests, and acceptance/audit documentation were updated. These follow-up edits were manually reviewed and validated with 13 passing `tests/unit/test_skill_install.py` cases, a successful repository-external clean Skill install/doctor/dry-run smoke check, and Ruff. They are not included in the scan digest above.

AUD-77 remains open. A Chromium process-tree egress boundary still needs an owner-selected implementation and dynamic acceptance proving loopback/private UDP is blocked while approved HTTPS capture remains available. This report does not establish full repository-wide review coverage, cross-platform behavior, or release readiness.
