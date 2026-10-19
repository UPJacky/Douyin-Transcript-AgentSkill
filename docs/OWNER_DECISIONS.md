# 项目完成所需的所有者决定与外部材料

更新日期：2026-10-19。本文记录用户范围决定；不构成发布批准。

## 当前决定：个人自用交付

2026-10-19 用户在成果已可查看后明确选择“按个人工作流结项”。本次交付以三条真实授权 URL 的采集、本地 ASR、当前默认模型文本校对及独立注册输出为完成范围；不继续原文件的 WSB/WFP 隔离工程。声学未验证与后两条视频 ID 文件名限制保留，未据此批准公开发行。

2026-10-17 用户明确软件只供自己使用，要求停止扩大工程范围。当前交付收敛为现有 Windows 普通账号、一次一个授权 URL：采集媒体→复用本地 ASR→Agent 默认模型校对和标点→独立文件输出。截至 2026-10-19，三条不同授权 URL 的原稿均已成功，随后三份当前默认模型校对稿亦已独立保存并注册；见[原稿验收](PERSONAL_USE_CHECK_2026-10-19_6e485c91.json)与[校对验收](PERSONAL_REVIEW_CHECK_2026-10-19_98eb3da2.json)。原稿哈希不变、校对范围声明和格式有效。源码与此前 313 passed、4 skipped 的[相关回归](PERSONAL_USE_CHECK_2026-10-17_0caf9a07.json)一致，本次未重跑测试。后两条网页仅有长文案摘录，保留 ID 文件名和现有 `--title`，不宣称三条正式标题验收通过；声学听审未验证。

2026-10-19 用户针对上述三份新原稿同意经本会话专用文件读取与结构化保存工具将正文送入当前默认模型，并接受正文可能保留在工具记录中；终端、诊断报告和聊天回复不得展示正文。该决定仅限视频 ID `7680762646522124938`、`7698028556051352873`、`7687249761632999089`，不扩展为未来使用者的同意。此次校对已按该通道完成，三份均为 `task_binding=registered`；该绑定只证明文件关联，不证明听审或外部事实核查。

当前交付不建设管理员服务、WFP/每租约身份、WSB/HCS 证明框架，也不承诺操作系统网络隔离。历史 Sandbox B2 失败与 HCS 错误原样留存；旧 WFP/ACL smoke stubs 保持禁用。把抗宿主 SYSTEM 伪造或 HCS 映射当成所有 B2 验收前置条件是先前解释错误，已在 [当前架构决定](P2_ISOLATION_DECISION.md)更正。

公开发行、远端 CI、跨平台支持与新使用者安装不作为本次个人可用的前置条件。许可证权利仍未确认，现有媒体、原稿、校对稿及隐私边界保留；未授权发布代码。声学听审与实际 URL 成功仍分别按证据报告，不以机器转写代替听审。

## 历史发行与隔离决定（保留溯源）

以下为此前源码发行及隔离产品范围的决定和验收记录；其范围与当前个人自用决定冲突时，以上述新决定为准。

## 2026-10-15 发行决策与验收摘要（历史）

首阶段发行范围仍为源码、Skill 与 CLI，目标平台为 Windows 11 x64、Python 3.11/3.12；项目许可证未确定。2026-10-15 用户明确答复不能确认其拥有或取得所有原创贡献采用 MIT 的授权，因此此前 MIT 选择不构成可用的版权授权或发布决定。原 MIT 文本保存在 [LICENSE_DRAFT_MIT.txt](LICENSE_DRAFT_MIT.txt)，标明未采纳且不纳入候选；README 和包元数据已撤下 MIT 声明。最小解锁条件是由权利人确认对全部原创贡献有许可权，或收集覆盖这些贡献的授权，再确定项目许可证。最新 Python 3.11.15 收尾全套为 765 passed、46 skipped、0 failed（543.43 秒，退出码 0）；此前 Python 3.12.13 的 760/48 是较早快照。2 个 PyAV 用例因环境缺 av 而跳过，并已在既有 Python 3.11.15 环境补测通过。URL 链路、声学听审、新 Agent 调用、目标 CI 与远端发布验收仍开放。
用户提供的目标仓库 `https://github.com/UPJacky/Douyin-Transcript-AgentSkill` 已由 GitHub connector 复核：`visibility=public`、当前账号 `admin=true`、默认分支 `main`、仓库 size 为 0；branches API 返回空列表，读取 README 返回 `This repository is empty.`。本机已将该 URL 配为 `origin`，`git ls-remote --heads origin` 退出码 0 且 refs 数为 0。远端没有项目代码或 CI 运行记录；本轮未更改仓库可见性、未提交或推送代码。目标仓库已有公开状态不等于本项目代码已发布；远端 CI/干净安装须在固定提交后执行。

## §284 历史验收状态（2026-10-13）

§284 Windows Python 3.11.15 全套 **728 passed、46 skipped、0 failed**（171.52 秒）；WFP Runtime harness **17/17**、Runtime/harness .NET format、敏感文件扫描通过。最新 sealed Diff Scan 仍为 §283（`0e0f14d7-0ce0-44a3-935c-b003aac7f88c`，123/123、0 finding、partial），其冻结字节不含 §284 WFP ACL source/test 改动。§284 只对原型 ACL 做代码级收紧：LocalSystem 持有对象，受保护 DACL 仅授予 SYSTEM/service SID `GRGWGX`；无 live WFP/service SID 验证，P2 仍未通过。P1/P3 仅按已有证据范围通过。P2 仍没有 production WFP/service/rollback、多 lease native readback 与授权捕获。P4 三段 WAV 与听审 manifest 哈希相符，但当前会话无法听辨；人工听审、`focus_08m59.wav` 年份争议与 fresh Desktop 隐私验收未做。Skill 要求调用 Agent 使用默认模型校对和标点，CLI 本身不调用模型，fresh Desktop trace 尚未证明实际调用。P5 的 CLI `doctor` 不是 fresh Desktop Skill trace。P6 首阶段交付范围当时已由用户授权确定；截至 2026-10-15，项目许可证因授权无法确认而未获批准。远端 CI、clean install 与发布证据仍待处理。不得把旧的 P2 授权解释为这些 owner 决策。

## 1. P2：浏览器进程级出口隔离

锁定 Chromium 在现有代理和启动参数下仍能向本机 loopback/LAN 接收端发送合成 UDP。隔离必须覆盖 Chromium 整个子进程树，只允许精确受控代理流量，并在设置失败或辅助进程退出时 fail closed。详细证据见 [P2_REPORT.md](P2_REPORT.md) 与 [项目审核报告 §1.1、§50、§80](PROJECT_AUDIT_REPORT.md)。

**隔离架构已根据用户授权选定：实现项目维护、管理员安装的 Windows 用户态 WFP service，首阶段仅支持 Windows 11 x64。** 旧的“外部预配置沙箱”方案因本机没有 broker/provider 而被可行性复核取代。当前已有 SCM dispatcher、named-pipe host、受保护配置读取器及 Python adapter 的未安装源码原型；`CaptureServiceFactory` 仍注入 `FailClosedCaptureWorker`，生产 per-lease worker、WFP apply/readback/rollback、生产 permit provider、installer 和默认 CLI client 尚未实现。普通 Python CLI 不得修改高权限规则。

当前主机是 Windows 11 Enterprise LTSC，Codex 主进程为普通用户令牌；§173 的标准 UAC 只读管理员子进程已成功启动，早期 §108 的执行器拒绝结论已过时。Sandbox 内 guest SYSTEM 的临时 WFP 规则用于可丢弃验证，不会提升宿主权限。§114 记录 AppContainer/Crashpad 候选路径故障；§115 验证 `ALE_USER_ID` dynamic WFP 规则可按临时低权限用户 SID 阻断 curl、保留 SYSTEM 对照并在关闭 session 后恢复，但浏览器尚未通过过滤前后探针。§116 只修复进程树清理证据。最新 §117 以 `CreateProcessAsUser` 启动目标 SID/session 的 Chromium 根进程及子进程；guest 临时补充 desktop ACL 后 USER32 延迟加载异常消失，但 Chromium 仍以退出码 21 报告 `ProcessSingleton` 创建失败，未生成截图。同一 SID 的锁文件探针成功，尚未定位失败 API；§118 的离线 PML 导出未产出可分析 CSV。§119 的两个早期 SwiftShader 对照因同时传入 `--disable-gpu` 而无效。§120 修正后，实际 SwiftShader 截图和 `--dump-dom` 都在 30 秒后超时、无输出；详细日志尾部未定位 mutex、lockfile 或消息窗口失败。项目 WFP service/provider、认证 IPC、持久默认拒绝与安装回滚仍不存在；宿主防火墙/网络策略未改动。Linux/macOS 暂不纳入隔离支持范围。P2 仍未通过；实施/验收路径见 P2_ISOLATION_DECISION.md 与项目审核报告 §§93–178。

**2026-10-12 管理员环境状态更正（见项目审核报告 §173）：** 上述关于最近一次提权启动被拒绝的记录是历史状态。当前主机上的标准 UAC 只读探针已成功启动高完整性管理员子进程；Codex 主进程仍为普通令牌。Windows Sandbox/`wsb` 可用，但本轮未触碰已有运行实例，也未在宿主安装项目服务或改动 WFP/Firewall。此结果只证明本机可承载显式 UAC 确认的管理员测试子进程，不代表存在可连接的管理员 endpoint 或生产隔离服务。P2 仍 **OPEN / NOT PASSED**。

**§123 最新诊断：** session 1 中的低权限目标账户可创建未命名 mutex、profile lockfile 和消息窗口，但创建 `Local\ChromeProcessSingletonStartup!` 或随机 `Local\...` 命名 mutex、打开已有命名 mutex均返回 Win32 5；Sandbox `ExistingLogin` 账户可创建并读取 `BaseNamedObjects` ACL。这使 session 命名对象 ACL 成为 `ProcessSingleton` 故障的强候选原因，尚无 Chromium 返回码或成功页面证明因果。一次禁网 Sandbox 的 SYSTEM harness 复测在 helper、mutex 或 Chromium 启动前被本机执行策略拦截；Sandbox 随后已停止。没有更宽的 session-wide ACL 修复或 mutex 预创建试验，也没有改变宿主 WFP/Firewall。P2 保持 **OPEN / NOT PASSED**，capture 继续 fail closed。实施边界和证据要求见 [P2_ISOLATION_DECISION.md](P2_ISOLATION_DECISION.md) 与 [项目审核报告 §§117–123](PROJECT_AUDIT_REPORT.md)。

**§125/§127 / AUD-86 P2 架构缺口：** 旧应用契约原计划把 broker listener socket 副本交给普通 Python CONNECT relay；该 relay 未验证本机客户端身份，上游 TCP 由普通 Python 进程创建。当前没有 production broker/listener，capture 在启动浏览器前 fail closed。目标架构中管理员主服务只做 control plane；每 lease 受保护低权限 worker 以独有 OS SID 持有 listener、DNS 和 upstream socket，并从同 SID 启动 Chromium/Playwright。WFP 用 endpoint catch-all deny 和 lease browser AppID+SID permit 限制本地接入；worker AppID+SID 的出口只允许受信 numeric resolver 与该 lease 完整 A/AAAA/CNAME 公网验证后 pinned 的 numeric IP:443。共享管理员 service AppID/SID 的动态目的地许可会形成跨租约并集，不能称为 per-lease egress。capture browser route 已移除普通 Python/Windows DNS Client 查询，只保留 URL/scheme/hostname 检查；worker DNS 身份和完整 IP pinning 尚未实现。worker/Chromium 目标 token 未通过启动验收时必须 fail closed。任何实现都要在可回滚 Win11 环境动态验收后才能关闭 AUD-86。证据和门槛见 [P2_ISOLATION_DECISION.md](P2_ISOLATION_DECISION.md)、[项目审核报告 §§125–127](PROJECT_AUDIT_REPORT.md)。

**§151 URL pipeline 收紧：** 非空 URL 作业必须使用完整作业 service client；没有 client 时在解析、任务恢复/存储、profile、browser 或 downloader 前 fail closed。`capture_factory`、调用方浏览器重试和普通 downloader 分支已从 `TranscriptionPipeline` 移除；产品 CLI 仍未接入已验证服务。未连接的 `BrowserCapture` 和旧 lease 模块仍需在生产集成前清理或严格隔离。该源码改动不代表 service/WFP 已实现或 P2 通过，详情见审核报告 §151。

**§181 numeric-IP TCP connector：** capture-pipe 新增独立 connector 源码，要求先通过注入的 lease-scoped endpoint permit provider，再以已验证 DNS 地址直连 TCP/443 并校验远端 endpoint；它保留 hostname 供 TLS SNI 使用。Fake-dialer harness 覆盖本地策略顺序和释放，但没有 production WFP permit provider、worker wiring 或真实连接。P2 仍 **OPEN / NOT PASSED**，默认 CLI 仍 fail closed。

**§208 HTTPS CONNECT handler：** native capture-pipe 现在有一个未注册的单流 CONNECT handler，连接 existing allowlist、数值 DNS policy、lease TCP connector 与有界 relay；pinned .NET build、native self-test 和 format check 通过。它只检查 CONNECT authority，不验证 TLS SNI/加密 HTTP Host，因此未来受保护浏览器 route 仍须执行 URL allowlist。它没有 listener、peer authentication、DNS egress permit、per-lease 并发限制或 WFP 接线，不能改变 P2 的未通过结论；工厂仍 fail closed。

**2026-10-11 原型补充：** §112 验证 package SID 可区分两个同路径 curl.exe 子进程，目标 profile 的动态 WFP block 命中、旁路 profile 放行、session-close 后恢复。§114 在已连接的 Sandbox 用户 session 捕获 Chromium 153.0.8010.12 AppContainer 失败：CreateProcess 成功、package SID 匹配；递归 SID ACL 后 executable AccessCheck 错误消失，但 Crashpad CreateNamedPipe 返回 access denied (0x5)，随后 STATUS_BREAKPOINT。Microsoft 的 AppContainer LOCAL pipe 要求与普通 Win32 Crashpad 命名空间不一致，是最强根因假设；没有匹配锁定二进制的源码 revision，也未运行页面/进程树。可选路径为维护可溯源的 LOCAL 修复 Chromium，或改用不要求 browser 根进程在 AppContainer 中的系统网络边界。P2 仍 OPEN/NOT PASSED，未改宿主策略。

§146 已确认当前没有活动的 Windows Sandbox 环境；重复启动一次 guest 只会重做有限的临时 WFP 原语检查，不能验证缺失的 production service/worker 信任边界。优先实现并审阅 service、每 lease worker、token/identity provider、安装回滚和默认拒绝逻辑；只有出现具体的新原语问题且可在一次性 guest 中隔离验证时，才运行新的 Sandbox 实验。生产验收仍需在可回滚的 Win11 x64 管理员环境证明无 lease 时 Chromium 全部出站被拒、有 lease 时只有精确受控代理可达、断管/服务崩溃/重启均 fail closed、现有流量重新授权行为正确，并完成授权 HTTPS 捕获。不能在日常主机试加 WFP 规则，也不能以 mock 代替系统动态验证。

**§115 更新：** 低权限账户的 `ALE_USER_ID` WFP block/recovery curl 验收通过；浏览器探针在过滤前后均未完成，交互 headless Sandbox 也未生成截图。这些结果不能证明 WFP 导致浏览器故障，也不闭合 P2。服务原型仍需验证正确的 user-session token/profile/desktop 启动和完整 Chromium 进程树，之后才可选择 per-user WFP。详情见项目审核报告 §115。

## 2. P2：真实媒体

目前只有一条用户授权页面记录，修复后的重试仍为 `CAPTURE_NO_MEDIA`，不计成功。验收要求是 **三条不同、获授权视频都成功端到端捕获**，每条取得标题和可解码音频；失败候选不计数。请提供可访问的候选视频链接，直到累计三次成功。不要为通过验收而放宽未经确认归属和必要性的页面 host allowlist。

## 3. P4：音频质量与长样本

P1 的本地样本约 5 分 16 秒；P4 的独立长样本现已达到 938.968435 秒，原始转写及默认模型校对侧车记录于 `PROJECT_AUDIT_REPORT.md` §176。§179 新增了 533 个单调时间点的私有复听侧车；主题定位为 01:11 流量来源/ASIN、05:40 竞价示例、08:41 年份/排名、08:59 词根分类。10 分钟门槛已满足。仍需人工对照音频听审至少三处，并在新 Desktop 会话核验模型调用与宿主数据流；记录漏词、增词、术语和不确定片段，但不要把转写正文复制进报告。模型校对不等于声学真值。

## 4. P6：许可证、交付范围与远端

当前没有远端 CI 或远端干净安装证据。SBOM 有 121 个 package records 和 137 个 relationships：`uv.lock` 的 42 条包记录，加上锁定 Playwright Windows x64 wheel sidecar 列出的 79 个 npm 组件。§162 的 SPDX member verifier 记录 41 个锁定第三方包、210 个 artifacts、41 个 metadata、9 个 license、2 个 notice 和 1,149 个 supplemental 成员；§172 另覆盖全部 235 个锁定 wheel/sdist 的打包元数据，并将 Windows RECORD 路径规范化后核实 419/419 个 PE 成员。PE import map 有 2,654 项直接导入；这些制品证据不证明 native provenance、实际链接关系或许可适用性。Playwright 8 个平台 wheel 的 64 个许可证/通知候选均与 RECORD 一致（§87），NumPy 40 个锁定 wheel 的 800 个许可/通知候选也与 RECORD 一致（§145）。另有独立 NumPy 原生文件清单，覆盖 1,130 个归档成员且逐条通过 RECORD 字节核验（§147）；这些证据不证明实际链接关系、完整 native BOM、provenance 或许可证适用性。41/41 个锁定第三方包有 evidence-backed `licenseDeclared`；另外 78 个 sidecar npm 组件有可识别许可证正文，`proxy-agent-negotiate@1.1.0` 只有 MIT 声明、没有正文（§91）。所有 121 个 SBOM package records 的 `licenseConcluded` 仍为 `NOASSERTION`。`python-dateutil` 依据锁定 sdist 中与 `uv.lock` artifact SHA 绑定的 LICENSE 文件声明 `BSD-3-Clause`。证据边界见项目审核报告 §§86、89、91、145、147、161–166；286 项新增成员的内容类别见 `P6_286_MEMBER_CONTENT_AUDIT_2026-10-11.md`，不代表许可适用性结论。

**2026-10-14 用户授权我确定首阶段范围：**

1. **项目许可证未定。** 2026-10-14 曾按用户委托将 MIT 作为候选，但 2026-10-15 用户答复“不能确认”对全部原创贡献有授权；该候选决定已撤回，不得作为授权或发布依据。根级许可证、README 许可声明及包的 `license` 元数据均已撤下；MIT 文本保存在内部草案文件中，不进入发行候选。最小解锁条件：确认所有原创贡献的权利人/许可权或取得覆盖授权，然后由所有者批准许可证。该状态不改变第三方包、sidecar、模型、浏览器或平台条款的许可结论；SBOM 的 `licenseConcluded` 仍为 `NOASSERTION`。
2. 首阶段只交付源码仓库、Agent Skill 与 CLI，由安装者按锁文件获取依赖；不随项目分发 wheel、模型、浏览器或预构建原生二进制。Windows WFP service 目前也仅为源码原型。
3. 官方支持范围为 Windows 11 x64、Python 3.11/3.12（包元数据要求 `>=3.11,<3.13`）。本机已验证 Windows 11 x64 / Python 3.11.15；Python 3.12 的目标平台 CI 仍待运行，不将 macOS/Linux 列为支持平台。
4. 用户提供的目标仓库 URL 为 `https://github.com/UPJacky/Douyin-Transcript-AgentSkill`。GitHub connector 当前观察到它是 public、默认分支 `main`、仓库为空且当前账号具有 admin 权限；根据用户将其余发行范围委托给我的授权，决定沿用现有 public 可见性，不更改仓库设置。本机 `origin` 已指向该 URL，但没有 refs、远端 CI 或远端干净安装证据；尚未提交、推送或发布。固定并审核 release commit 后执行目标平台 CI 与远端干净安装。

不得把 `NOASSERTION` 当成第三方许可结论。未选择的平台不纳入发布承诺；本地测试不能替代 Python 3.12 目标平台 CI、远端 CI 或远端干净安装。项目许可证目前没有批准；未经权利确认和所有者决定，不得发行或声称某一项目许可证。

**§209 NuGet 签名证据：** `dotnet nuget verify --all` 对四个锁定的 WFP build-only `.nupkg` 全部返回退出码 0，签名内容哈希与 lockfile 匹配。该验证不确定 root license、SDK/WDK 条款对生成输出的适用范围，也不授权任何发行。

### 发行范围与证据清单映射

下表把已选的源码、Skill、CLI 范围及未选的打包形态对应到所需证据；它不预设任何许可结论。未来如扩大交付范围，应按新增制品重新补证。

| 可能的交付内容 | 决定范围时需点明 | 范围确定后要补的证据 |
|---|---|---|
| 源码仓库、Agent Skill、CLI | 是否只交付项目源码，依赖由用户按锁文件安装；是否提供源码包或二进制包 | 根目录项目许可证；锁文件依赖和源码内复制内容的来源；可见 LICENSE/NOTICE；远端安装和支持平台 CI |
| Python wheel 或安装包 | 是否将依赖或可选 extra 一并打包 | 打包成员清单；每个内含组件的锁定制品、元数据和许可证/NOTICE；PyAV、NumPy、CTranslate2、ONNX Runtime 等原生组件的 provenance 与链接方式 |
| 固定 ASR 模型 | 模型只由用户运行时下载，还是会被镜像/随安装包分发 | 锁定模型仓库与 revision、权重摘要、模型许可及上游使用条款；分别记录下载和再分发路径 |
| Playwright 浏览器 | 浏览器由 Playwright 首次运行时下载，还是由项目镜像/随包分发 | Playwright wheel 与 npm sidecar、Chromium revision/制品摘要、浏览器 LICENSE/NOTICE、运行时下载与再分发范围 |
| Windows WFP service 或其他原生二进制 | 只交付 C# 源码，还是构建并分发 service、安装器或原生依赖 | 对应平台和架构的可复现构建来源、二进制 SBOM、依赖链接/加载关系、LICENSE/NOTICE、签名与安装产物清单 |

仅源代码交付也仍需审阅仓库内直接复制的第三方代码和运行时依赖说明；未分发模型/浏览器不等于其上游条款已自动满足。当前证据中的字节哈希和 `licenseDeclared` 不构成完整 provenance、适用性或法律结论。

## 当前已验证的本机条件

- 当前工作树基于 `b166778`，本地改动尚未形成最终 release commit。
- `origin` 已指向用户提供的 GitHub URL；本机没有 `gh`、Docker 或 `act`。WSL 可执行程序存在，但没有已安装的 Linux 发行版。远端 public 空仓库无 refs；本地 `ls-remote` 只验证匿名读取成功，不验证本机认证。
- 当前 Codex 进程仍为标准用户；§173 已通过标准 UAC 启动只读管理员子进程，未安装服务或修改宿主 WFP/Firewall。§173 之前“提权子进程被执行器拒绝”的结论已过时。项目 service/installer 仍不存在；动态部署验收仍要求可回滚的 Sandbox/VM。
- 最新 Python 3.11.15 收尾全套为 765 passed、46 skipped、0 failed（543.43 秒，退出码 0）；此前 Python 3.12.13 的 760/48 是较早快照。2 个 PyAV 用例因该环境缺 av 而跳过，已在既有 Python 3.11.15 环境补测通过。其余跳过项涉及未配置 native interop、当前账户 link/junction 权限与 POSIX-only 行为，不代表 Windows reparse race 或 Linux/macOS 已通过。§280 的 728/46 更早。§283 targeted C# 和敏感文件复验已通过。已通过显式 UAC 安装 VS Build Tools（安装器退出码 3010，要求重启）和 Windows SDK（退出码 0）；未重启、未修改持久 PATH。本机全套不替代目标 CI、远端 CI 或远端干净安装。
- 最新冻结差异扫描为 §283（`0e0f14d7-0ce0-44a3-935c-b003aac7f88c`），123/123 源代码 worklist 项复核、0 个报告级 finding、coverage partial。当前安全对策见 [SECURITY_REVIEW_REPORT_2026-10-13.md](SECURITY_REVIEW_REPORT_2026-10-13.md)。ASR worker 同身份运行，不是 OS sandbox；没有 production WFP/service 或 live isolation 证据。P2 的 ACL/SID 与 WFP 对象可见性、rollback、per-lease worker 仍未解决。三段 WAV 附件与听审包相符，但当前会话没有音频感知能力，P4 仍待实际音频对照和 fresh Desktop 数据流/隐私验收。P5 fresh Desktop trace 与 P6 owner/远端发布门槛继续开放。
- P6 制品元数据与 PE 成员核验基线见项目审核报告 §172；NuGet build-only 依赖盘点见 §§199、209、231、255。§234/§247 是旧快照；§258 是此前已封存 Diff Scan，coverage 为 partial（116 个 work items / 264 个变更文件），早于 §260；§261 后续冻结快照已在 §262 封存，记录两个静态 finding，但仍为 partial（116 个 work items / 265 个变化路径）。§246 full-tree Deep Scan 未启动，因为缺少 managed filesystem permission profile，因此不能称全仓无发现。§236 已从现存私有 SHA-256 cache 重放 SPDX evidence：41 packages、210 artifacts、41 metadata、9 license、2 notice、1,149 supplemental members；§242 已对 2,654 条 PE import name 做分类，但两项结果都不替代许可/来源结论。§255 的本地 build BOM 与 copied-Skill clean-install smoke 已通过，不代表远端复现。所有 SBOM `licenseConcluded` 为 `NOASSERTION`。首阶段发行范围已确定，但项目许可证未定，目标 GitHub 仓库现为 public 空仓库，尚无远端 CI/干净安装或代码发布证据。

