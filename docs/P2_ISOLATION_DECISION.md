# P2 浏览器出口隔离架构决定

## 2026-10-17 当前决定：个人 Windows 自用

用户明确软件只供自己使用，要求收敛范围。当前目标为在现有 Windows 普通账号下，串行处理获授权的抖音 URL，完成采集、已有本地 ASR、Agent 默认模型校对及独立文件输出。截至 2026-10-19，三条真实授权链接的个人采集→下载→ASR→Markdown 均已通过，见[原稿证据](PERSONAL_USE_CHECK_2026-10-19_6e485c91.json)；随后当前默认模型已逐份校对，独立校对稿均注册且原稿不变，见[校对证据](PERSONAL_REVIEW_CHECK_2026-10-19_98eb3da2.json)。源码仍与此前 313 passed、4 skipped 的[回归证据](PERSONAL_USE_CHECK_2026-10-17_0caf9a07.json)一致。后两条网页没有可可靠提取的独立短标题，保留视频 ID 文件名；声学听审未验证，不宣称旧隔离路线或三条正式标题验收通过。

当前个人路径不再建设管理员服务、WFP backend、每租约系统身份、安装器或 WSB/HCS 证明框架。保留 URL/hostname allowlist、TLS/媒体校验、资源上限、取消和进程清理等应用层边界；不宣称拥有操作系统网络隔离，浏览器仍能使用当前普通账号已有的网络能力。此前 WFP/Sandbox 原型、失败证据和禁用入口保留；旧 WFP/ACL smoke stubs 不启用。

此前把抗宿主 SYSTEM 伪造的 guest attestation 或 WSB→HCS/VM 映射扩为 B2 总闸门，是对需求范围的错误解释。原 [LUNA 指令中的 B2 四项条件](LUNA_EXECUTION_INSTRUCTIONS_2026-10-16.md)要求锁定浏览器、实际低权身份、页面成功和完整进程树结束；原手动 WFP/ACL 入口的恢复门槛不自动适用于全部 B2 证据。历史 B2 仍未通过，不据范围调整改写成功结论；该路线已退出当前个人交付依赖。当前验收只按上述个人路径的真实运行证据判断，详见 [当前交付状态](CURRENT_DELIVERY_STATUS.md)。

## 历史隔离架构与实验记录（由上述当前决定取代）

以下保留原设计、原型状态及实验结论，供定位旧代码和证据；其中“当前”“必须”“上线门槛”等措辞均属于当时的隔离产品范围。

- 决定日期：2026-10-10
- 状态：**架构于 2026-10-10 修订；SCM/命名管道源码原型已存在但未安装；服务启动需 baseline readiness gate，默认 gate fail closed；生产 worker/WFP 集成、部署和验收未完成**
- 授权：用户明确授权代理选择解决方案
- 当前环境（2026-10-13；新增安全缓解记录见审核报告 §263；生产集成源码复核见 §§192、201–202、214，readiness/程序集/协调器见 §§219–§222，readback 投影跟进见 §226）：SCM dispatcher、受保护命名管道 host、service 配置读取器和客户端 adapter 源码已存在；它们尚未作为已安装服务/生产 worker 接线。`CaptureServiceFactory` 仍注入 `FailClosedCaptureWorker` 和当前不可用的 `WfpBaselineUnavailableGate`；gate 在创建管道、报告 RUNNING 前失败关闭。纯托管 `WfpPolicy.Core` 已承载内部 service-wide compiler，将 lease browser/worker AppID 与 persistent baseline 角色绑定；预览 materializer 检查精确许可形状。WFP 离线 harness 14/14、capture-pipe self-test 通过。WFP preview/materializer 不打开 BFE；没有生产 filter apply/readback/rollback、provider/sublayer reconciliation 或 lease permit provider/coordinator。Windows Sandbox/`wsb` 曾可用，但不能把历史实例视作本轮可信 guest；本轮未操作 Sandbox、BFE、WFP 或 host firewall。旧 Sandbox 假设 smoke 写入入口现已改为立即失败 stub，README 已撤下旧操作步骤。P2 仍缺安装器、受保护 AppID 来源证明、逐 lease worker/身份、生产 WFP 集成、Job Object/Chromium 进程树验收及三条真实捕获；详见审核报告 §§192、200–202、211、214、218–220、224、226、263。
- §§168–169 后续源码切片加入数值 DNS wire codec/questioner、loopback UDP→TCP fallback、TTL 剩余期限处理、negative-family 保守不缓存、名称标签边界解析及取消时 socket-handle 回归。§178 重跑的 harness 仍只是离线原型检查；这些代码未接入 service/worker/WFP，真实捕获保持 fail closed。§189 的 627/30 Python 全套结果和 §191 的本地审核器定向回归不验证 native service/WFP。详见审核报告 §§168–192。
- 最新原型证据：§112 在 disposable Sandbox 验证 AppContainer package SID WFP 规则能区分同路径 `curl.exe` 并在 dynamic session 关闭后恢复。§114 发现锁定 Chromium 153.0.8010.12 在 AppContainer 下因 Crashpad `CreateNamedPipe` access denied（0x5）/`STATUS_BREAKPOINT` 退出；LOCAL 命名空间冲突是强推断，尚未与精确 Chromium 源码提交核实。§115 验证 `ALE_USER_ID` / `FWP_SECURITY_DESCRIPTOR_TYPE` dynamic filter 可阻断随机低权限账户 curl、保留 SYSTEM 对照并在 session close 后恢复。§117 的用户 token 原型通过临时授予 guest `WinSta0\Default` ACL 后不再出现 USER32 延迟加载异常，但 Chromium 随后以 `ProcessSingleton`/退出码 21 失败，没有页面截图；§118 的 PML 未取得 CSV；§120 正确 SwiftShader 的截图和 `--dump-dom` 测试仍分别超时 30 秒、无输出。§123 将 session named-mutex ACL 列为强但未确认的启动故障候选，复测 helper 在启动前被执行策略阻止。§125–127 明确每 lease SID worker 必须拥有 listener、DNS 和 upstream socket，并从当前普通调用进程移除 route DNS。§128–129 是 §131 扫描器修复前最近一次双版本全套，各 519/23；§130 记录用户授权没有提供管理员连接信息，§131 记录本机仍无管理员令牌或可用 broker。详细边界见审核报告 §§112–131。
- §118 尝试在普通宿主和禁网 Sandbox guest SYSTEM 中离线导出 §117 的 PML，均未生成 CSV；没有取得新的根因证据。§120 也未定位页面启动停滞。下一步需用只保留锁定 Chromium、profile `lockfile`、命名 mutex 和消息窗口创建操作的过滤配置缩小启动跟踪，然后在同一会话复测短时 headless 页面，再验证 Playwright。项目仍无可用宿主管理员令牌，授权不能提升当前 medium-integrity 进程；不得在日常宿主写入 WFP 策略。详见审核报告 §§117–120。

**历史状态 §163（2026-10-11；当前更新见 §169）：** §123 的 session named-mutex ACL 仍只是未确认的 Chromium 启动故障候选；后续 SYSTEM harness 在启动 helper/Chromium 前被本机策略阻拦，不能通过换包装重试相同受限执行。§125/§127/AUD-86 发现并记录旧应用契约的本机代理客户端身份与上游 socket 所有权缺口，并收紧了目标：管理员主服务只做 control plane；每 lease 独有低权限 SID worker 持有 listener、DNS 和 upstream。§126 已在应用侧移除 listener socket handoff 和 Python upstream relay；capture request/WebSocket route 现只做 URL/scheme/hostname 检查，不查询普通 Python/Windows DNS Client。worker DNS 身份、完整 A/AAAA/CNAME 校验、numeric IP pinning、worker/Chromium token 启动路径及其 WFP policy 均尚未实现或验证；共享管理员 service AppID/SID 不能声称逐 lease egress。§162 的 LeasePolicyCompiler 只生成 `not-deployable` 语义 plan；§163 的两项 named-pipe 互操作仅在当前用户身份下通过，不证明生产 service/WFP。当前进程仍无管理员令牌或可接入 endpoint；§163 的标准只读 UAC 身份探针在子进程创建前被执行器策略拒绝，无提示/无提权。用户授权没有产生主机连接通道，Sandbox guest SYSTEM 不等于宿主管理员会话。doctor 当前把 browser isolation 标为 unavailable，URL capture 保持 fail closed；P2 仍 OPEN / NOT PASSED。

**历史状态 §169：** capture-pipe 的数值 DNS questioner、wire parser、TTL aging 和 loopback UDP/TCP/socket-cancellation fixtures 已通过本机 source harness；这些代码未连到 service、per-lease worker、upstream connector 或 WFP。DNSSEC、完整 RRset 与 negative SOA 解析仍未覆盖，含未验证 negative TTL 的地址集会禁用缓存。当前 Windows 会话仍非管理员且没有可连接管理员 endpoint；授权代理自行选择方案不等于可以创建一台管理员主机或提升 OS token。未安装服务、未变更宿主网络策略，URL capture 继续 fail closed。

**历史状态 §171（2026-10-11）：** 本机全套 Python 回归为 617 passed、29 skipped。该检查点的会话没有管理员 token、管理员主机连接信息或已部署 broker/service；后续环境状态以本节开头和审核报告 §263 为准。未尝试绕过系统策略，也没有修改宿主 WFP/Firewall。项目级 service、per-lease worker/identity、Chromium 启动、生产 WFP、安装/回滚和三条真实视频捕获仍未实现/验收，P2 继续 OPEN / NOT PASSED；应用保持 fail closed。

## 选择

使用项目维护、由管理员安装的**Windows 用户态 WFP broker/service**；第一阶段只支持 Windows 11 x64。该服务必须将 Chromium 的持久默认拒绝策略与每次捕获的短期代理许可分开管理。此前依赖外部管理员沙箱的决定已被 2026-10-10 可行性复核取代。浏览器不可仅凭 Playwright 代理、Chromium 参数或应用内请求路由视为已隔离。

理由：Chromium 已被实测可绕过 HTTP CONNECT 代理发送 UDP；浏览器进程和子进程需要由操作系统网络层约束。外部 broker 在本机不存在，无法验收或集成，因此选择项目维护独立管理员服务；普通 Python CLI 只通过受保护 IPC 请求短期 lease，不直接改系统策略。项目承担 Windows 服务生命周期，首期不声称支持 Linux/macOS。

平台相关的操作系统基础能力由官方文档描述：Windows WFP 的 ALE `AUTH_CONNECT` 层涵盖 TCP connect 和首个 UDP flow，并可按应用身份匹配（[ALE layers](https://learn.microsoft.com/en-us/windows/win32/fwp/ale-layers)、[ALE overview](https://learn.microsoft.com/en-us/windows/win32/fwp/application-layer-enforcement--ale-)）；Linux network namespace 隔离网络设备、IPv4/IPv6 协议栈、路由和防火墙规则（[network_namespaces(7)](https://www.man7.org/linux/man-pages/man7/network_namespaces.7.html)）；macOS Network Extension content filter 可决定是否允许连接，需启用相应 entitlement，macOS 可作为 system extension 部署（[Network Extension setup](https://developer.apple.com/documentation/xcode/configuring-network-extensions/)、[deployment note](https://developer.apple.com/documentation/technotes/tn3134-network-extension-provider-deployment)）。这些是可用平台机制的说明，**不是本项目已配置或已验证它们的证据**。

## 集成契约

当前没有可信的跨平台“沙箱正在生效”探测 API。环境变量、可写配置中的布尔标记、代理可达性、Chromium 启动参数和普通 `provider.isolated` 返回值都不能证明系统过滤规则仍然生效。项目需提供受管理员安装的可信服务和认证 IPC；服务缺失、身份不可信、策略未知或动态规则验证失败时，URL 捕获应返回稳定的 `BROWSER_ISOLATION_UNAVAILABLE`，且不得启动 Chromium。

Windows 首个受支持实现由独立、管理员安装的项目 WFP 服务管理规则；普通 Python CLI 不得创建或修改高权限规则，也不得由同一个管理员服务进程承载所有 lease 的 upstream socket。管理员服务是控制面，只认证调用方、分配 lease 身份、启动/监督低权限 worker 并管理 WFP。每个 lease 使用受保护的低权限 worker 和独有 OS SID；该 worker 持有本 lease 的代理 listener、DNS 查询和 upstream socket，并在该身份下启动 Chromium/Playwright 捕获进程树。若目标 Windows session 中无法以该身份可靠启动 worker/Chromium，URL 捕获继续 fail closed。

WFP 规则同时匹配身份和应用：浏览器 AppID + lease SID 仅允许到该 lease 精确 loopback endpoint；worker AppID + 同一 lease SID 只允许连接配置的数值 DNS resolver endpoint，以及当前 lease 完成公共地址校验并固定的数值 IP:443。管理员控制服务自身不得获得所有 lease pinned IP 的并集许可。若多个 lease 的上游 socket 都由相同 AppID/SID 的服务进程创建，动态 WFP permits 对该进程形成可互用的目标并集，不能宣称 WFP 已提供 per-lease egress；除非另行实现并动态验证 per-flow callout 身份绑定。必须实测其他 provider 的 block 始终优先。是否还需 ALE_RESOURCE_ASSIGNMENT 规则以覆盖 bind/raw socket，不能从 AUTH_CONNECT 策略推断，需单独评审与验证。loopback ALE 行为、已建连接重授权和 BFE 生命周期仍需专用环境动态验证。捕获应由受认证 IPC 请求受监督 worker 执行；普通 CLI 不直接启动 Chromium。

1. 将锁定 Chromium、捕获 worker 和 proxy worker 运行时安装到普通用户不可写的固定路径；服务从管理员保护策略核验路径、摘要、版本和签名，不能接受客户端指定的可执行文件或启动参数。
2. 通过 OS ACL 保护并验证服务身份的固定 IPC 建立 lease 会话。服务从已认证 IPC peer 的操作系统信息获取调用者 PID/token/session；客户端不能提交 PID、Chromium 路径/哈希、SID 或代理端口作为策略输入。
3. 服务创建每 lease 唯一的临时低权限 SID/token，启动受保护 worker，并将浏览器与 worker 子进程树限制在此 lease identity。管理员服务仅控制 worker 生命周期和 WFP，不创建 listener/upstream socket，不把所有 leases 的目标许可放在自己的共享 AppID/SID 上。
4. worker 为本 lease 创建并持有 loopback HTTP proxy listener；浏览器只获得该精确 endpoint。WFP 在 loopback connect 层默认拒绝其他客户端，只允许目标 lease browser AppID + SID；worker AppID + SID 只允许到配置的数值 resolver endpoint 和当前 lease 已固定的数值 IP:443。不得把 endpoint 地址/端口本身当作客户端认证。
5. worker 只接受现有导航/资源 hostname allowlist 内的 HTTPS CONNECT。它必须在自身 lease identity 下查询配置的数值 resolver，校验完整 A/AAAA 结果（含解析链得到的终值）均为公网地址，拒绝混有私网/保留地址的结果，选择一个数值 IP 并以该数值 IP 建立 TCP/443；TLS SNI/证书校验仍使用原 hostname，连接过程不得再次 DNS 解析。不要调用共享 Windows DNS Client/getaddrinfo 作为 per-lease DNS 证明。
6. 捕获 worker 在相同 lease SID 下启动锁定 Chromium/Playwright，并核对实际 executable path/hash/revision。普通 CLI 只通过 IPC 请求捕获并接收状态/结果；它不取得 lease token、listener handle 或上游连接能力。worker/IPC/lease 中断时关闭整个 Chromium 进程树、撤销本次许可、关闭 listener/resolver/upstream sockets；持久默认拒绝策略必须继续生效。

服务还必须核实 renderer、utility、捕获 worker 和 proxy worker 的实际 AppID/SID，并证明完整进程树都命中正确过滤器。DNS 查询不能从普通 CLI、共享管理员服务或共享 Windows DNS Client 产生并被误记为 lease 受限流量；需对 resolver 出口单独做 OS 身份与目的端点归属验证。若 worker 与 Chromium 必须拆成不同进程，分别分配每 lease 受保护身份并验证两者之间仅有受控 IPC/loopback 路径。服务缺失、身份不可信、策略未知、规则核验失败或 lease 中断时，捕获必须停止。Linux/macOS 在各自平台 adapter 与动态验收完成前不得宣称 URL 捕获具备隔离保证。

### 上线阻断门槛：服务代理边界

以下三项在 Windows 11 x64 rollback-capable 环境中完成实现和动态验收前，P2 保持 OPEN，URL 捕获保持 fail closed：

1. **唯一 lease OS identity 与 listener 入口控制：** 每次 capture 的完整 Chromium 进程树使用独立 lease SID。WFP 对该 worker 的精确 loopback endpoint 默认拒绝其他进程，仅允许目标 browser AppID + SID；验证过滤器权重、loopback 分类及其他 provider 的 block 仲裁。固定路径 AppID 不能区分同一路径启动的其他 Chromium。
2. **每 lease worker 与上游限制：** 管理员主服务只做控制面；每 lease 低权限 worker 拥有 listener、DNS 与 upstream sockets，且使用独有 OS identity。worker WFP 出站仅允许其受保护 AppID + lease SID 访问固定 resolver endpoint 和本 lease 已校验并 pin 的 IP:443。不得将共享管理员 service AppID/SID 的“活动 pinned IP 并集”描述为 per-lease WFP 限制。
3. **DNS 身份与数值 IP pinning：** 浏览器 request/WebSocket route 仅执行 scheme/hostname/URL allowlist，不在普通 Python 或 Windows DNS Client 中解析。worker 必须查询受信数值 resolver、验证完整 A/AAAA 解析结果均为公网地址，再以选中的数值 IP 建立连接；验证 DNS 与 upstream socket 均归属 worker SID/AppID，重绑定或二次解析不能改变目标。
4. **浏览器身份与启动身份一致：** 安装器把锁定 Chromium 和 worker 运行时放在普通用户不可写的管理员保护路径；服务核验路径、SHA-256、revision，并由受控 worker 在唯一 lease SID 下启动 Chromium。应用目前仍由调用方的 Python/Playwright 直接 launch；在受支持的 worker/token 启动路径通过动态验证前，不能声称浏览器身份已按 lease 隔离。

服务代理必须拒绝未获授权的本机客户端；不要用未经评估的 Basic/token proxy-auth 代替 OS/WFP 身份控制。测试应在独立可回滚 Sandbox 中运行，不能在日常宿主写 WFP。

Windows 常规 `getaddrinfo` 解析可能经由系统 DNS Client；应用侧验证到的地址并不能证明服务 worker 的 WFP 出口策略绑定了同一个 DNS 请求。若无法把 DNS query、完整回答验证和 numeric-IP connect 全部放入 per-lease worker，必须将“per-lease DNS egress”标为未实现，继续 fail closed。

### 按 lease 区分进程的身份限制

`FWPM_CONDITION_ALE_APP_ID` 按规范化的应用可执行文件路径匹配，不是 PID 或 lease 身份。因此，仅把一份受保护 Chromium 安装路径加入 WFP 规则，不能证明规则只授权当前 lease 的 Chromium 进程树；同一路径启动的其他进程也会命中相同 AppID 规则。固定路径保护可以区分其他 Chrome 安装，但不能提供每次捕获之间的进程隔离。[Microsoft ALE 文档](https://learn.microsoft.com/en-us/windows/win32/fwp/application-layer-enforcement--ale-)说明 ALE 按规范化文件名识别应用。

候选强化身份边界有两种：每个 lease 使用独有 AppContainer package SID 并匹配 `FWPM_CONDITION_ALE_PACKAGE_ID`，或由服务为 lease 创建独立低权限本地用户并匹配 `FWPM_CONDITION_ALE_USER_ID`。§112 证明 package SID 可区分两个 curl profile，但 §114 的 Chromium AppContainer 仍被 Crashpad 管道阻断。§115 证明用户 SID WFP 条件可区分账户并通过 curl 阻断/恢复，但浏览器没有完成启动验收。不要把任何候选直接作为产品实现；下一原型需先解决受支持的 Chromium 用户会话/desktop/token 启动，随后验证完整子进程树、精确 loopback 代理连接、IPv4/IPv6/TCP/UDP egress、lease 断开和服务崩溃。Microsoft 的命名管道条件与 WFP 用户条件依据分别见 §§114–115。

在原型完成前，不得把“固定路径的 AppID 规则”描述成 lease 级进程隔离。验证至少要覆盖两个独立 lease 的 package SID 互不通行、同一 Chromium 的所有子进程身份、仅精确 loopback 代理端口可达、错误端口与公网 IPv4/IPv6/UDP 被阻断、lease/服务异常后持久 deny 仍生效，以及 loopback exemption 的创建和清理。若这些条件不能成立，应保持 URL 捕获 fail closed，并调整威胁模型或更换进程隔离设计。

## 沙箱必须提供的保证

1. 规则绑定到本次捕获的 lease 身份并覆盖整个 Chromium 进程树；不能仅凭固定路径 AppID 推断 lease 级隔离。普通 Chrome/Chromium 和其他 lease 不得命中当前 lease 的代理例外。
2. 浏览器只能连到捕获使用的受控本机代理监听端点；阻断其他 loopback、私网/LAN、IPv4/IPv6 直连、DNS 旁路、UDP、QUIC、WebRTC/STUN 和原始套接字。
3. 代理仅按项目现有 HTTPS、精确 hostname allowlist、DNS pinning 与媒体下载策略放行；不能借沙箱配置扩大站点 allowlist。
4. 沙箱缺失、状态未知、规则装载失败或管理面连接中断时，捕获必须停止；浏览器进程不能在规则消失后继续拥有直连网络。
5. 手动登录仅能通过已授权的可见浏览器操作；不得绕过登录、验证码、DRM 或访问控制。

### 当前应用侧契约和实现状态

`skills/douyin-transcript/src/douyin_transcript/isolation_broker.py` 目前是 fail-closed 占位接口，没有真实 transport 或系统策略证明。较早的 lease contract 曾把 broker 选定的 Chromium identity 和 proxy endpoint 返回给调用方；这是未接入且不可达的遗留路径，不能作为当前默认调用链的描述或接通服务的接口。当前 `TranscriptionPipeline` 要求完整作业 client，但 CLI 没有已验证 client；`BrowserCapture.start()` 在创建 profile、启动 Playwright、代理或 Chromium 前返回 `BROWSER_ISOLATION_UNAVAILABLE`。真实架构要求普通 CLI 只经认证 IPC 提交 capture 请求，由独有 SID 的 lease worker 启动 Chromium、持有 listener/DNS/upstream sockets，并经 IPC 返回结果。不能把旧 lease contract 直接连到服务。

现已存在独立的 Windows named-pipe 源码原型和 Python transport adapter，但仓库**没有已安装服务、生产 service SID 配置或默认 CLI 接入**，所以 `open_system_broker()` 仍明确失败；`BrowserCapture.start()` 在创建 profile、启动 Playwright、启动代理和 Chromium 之前返回 `BROWSER_ISOLATION_UNAVAILABLE`。调用者传入 `executable_path`、`args`、`proxy`、`channel`、`env` 或 `ignore_default_args` 会得到 `BROWSER_SECURITY_OVERRIDE`。这些代码和错误路径只证明应用默认拒绝和 IPC 代码路径，不证明任何系统 WFP 策略。

`doctor` 将 `browser_isolation` 标为 `unavailable`，即使 Playwright 和 Chromium 已安装也会将 `douyin_urls` 保持为 `setup_required`；IPC 可连接本身不会被当作策略证明。

未来实现中，普通 CLI 只通过认证 IPC 提交 capture 请求并接收状态/结果；独有 SID 的受保护 lease worker 执行导航和媒体发现、启动锁定 Chromium，并持有 listener、DNS 与 upstream sockets。调用方不得取得浏览器身份、lease endpoint 或直接启动 Chromium。浏览器路由在 worker 内只校验 URL/scheme/hostname，不通过普通 Python 解析 DNS；worker 负责完整 A/AAAA/CNAME 校验与 numeric-IP pinning。`browser_proxy.py` 是 standalone 测试/诊断模块，不接入 `BrowserCapture`，也不构成 isolation service。IPC/heartbeat 必须异步监测；规则撤销后 worker 关闭浏览器进程树及所有 sockets，并继续应用持久默认拒绝。当前这些 worker/IPC 行为均未实现或验证。

远端任务必须保持在 worker 边界内端到端执行。IPC 请求提交原始 URL 和有界资源限制；worker 在 lease 身份下解析短链、捕获页面、校验媒体候选、跟随 CDN 重定向并下载媒体，再返回有界安全元数据和已校验媒体流/文件。禁止把签名媒体 URL、请求头、浏览器候选或上游 socket 能力回传给 CLI。当前 `pipeline.py` 的历史流程会在 capture 后把媒体候选交给调用方下载线程，若未来只接通 capture IPC，这些 CDN 请求仍可能绕过 worker。为封住当前无 broker 状态下的短链前置网络请求，默认 pipeline 与 `--dry-run` 现在只做本地直链解析；短链会以 `BROWSER_ISOLATION_UNAVAILABLE` 失败，不会在普通调用进程执行 DNS/HTTPS。此局部收紧不代表完整 worker 契约已实现，也不改变 `open_system_broker()` 的 fail-closed 状态。

`capture_ipc.py` 与 `references/capture-ipc-v1.schema.json` 定义严格有界 JSON 消息：请求只含原始 HTTPS 抖音 URL 和资源限制；成功结果只含安全视频元数据与不透明媒体 artifact UUID、大小、摘要、MIME 和时长。codec 拒绝重复/未知字段、非法域名、非 HTTPS、非 443 端口与超限帧；结果解码必须带原请求，并校验请求 ID、媒体字节数和时长未超出该请求上限。当前 `capture_pipe_windows.py` 将该 JSON 帧与 native 固定四字节 `DTP1` preamble、四字节 `DTA1` authentication acknowledgment、长度前缀及媒体 block 格式互转。服务端先读取 preamble 并认证客户端 PID/token/session 与 caller allowlist，只有成功后才回 `DTA1`；客户端收到确认后才发送 URL-bearing 请求。Python 客户端则先认证 server PID/session/token SID 再启动握手。定向 IPC/adapter/client 回归见审核报告 §§142–143。adapter 未接入默认 CLI，且没有已安装 service identity；它不证明 worker 或 WFP 隔离有效。

当前 persistent Chromium profile 属于调用方用户，并跨命令保留登录状态；这不能直接迁移给每 lease 新建的 SID worker。多个 lease 共用同一 profile 会让不同 worker 触及同一认证状态，也没有已定义的加密、授权、撤销或锁处理契约。此外，当前 `LOGIN_REQUIRED` 路径会报错并收尾浏览器，没有“用户在可见窗口登录后继续当前任务”的暂停/恢复流程。首版建议使用每 lease 独立的临时 profile，不复制 cookie；在获授权的可见会话中暂停等待用户手动登录后继续当前任务，lease 关闭时结束整个浏览器树并清理 profile。跨运行持久登录态需另作凭据设计与验收，不能隐式复用旧 profile。

broker 的真实身份锚、策略版本/摘要、有效 WFP filters 核验、renderer/utility 进程树覆盖、断线行为和系统级网络隔离均尚未实现或验证。因此应用的“无 broker 时拒绝启动”已在代码中 fail closed，但方案选择和该拒绝路径都不代表 AUD-77 已修复，也不代表 P2 通过或可将浏览器称为隔离运行。

## 验收门槛

- 从项目锁定 Chromium 动态验证隔离：IPv4/IPv6、loopback/LAN UDP 与直接外网连接被阻止；只有目标 lease identity 能连接该 lease 的服务代理端点。
- 由其他本机进程和另一个 lease 对 listener 发起负向连接，确认在 WFP/connect 层拒绝且 worker 未 accept/未创建 upstream；目标 Chromium 的 lease SID 可连精确 endpoint。并发运行两个 leases，证明 worker A 无法连接 lease B 的 resolver 或 pinned IP，反向也成立。
- 由每 lease worker 直接查询受信 numeric DNS resolver，检查完整 A/AAAA/CNAME 结果和混合公网/私网负向回答；证明 DNS 与 upstream socket 的 WFP 事件均属于预期 worker AppID/SID。worker 仅能连接该 resolver endpoint 和本 lease 已 pin 的 numeric IP:443，且 connect 不会再次解析 hostname。
- 对照 Playwright 实际启动的 Chromium 路径/摘要/revision、browser lease SID 与管理员保护安装路径和服务策略 identity 完全一致；检查所有 renderer/utility 子进程同属 lease SID。
- 通过相同沙箱和代理完成获授权 HTTPS 页面的正向媒体捕获。
- 覆盖规则加载失败、沙箱/管理进程退出、Chromium renderer/utility 子进程退出和清理；证明浏览器既不会在无规则时继续联网，也不会遗留可用的网络例外。
- 对三条不同获授权视频分别完成隔离正反探测、标题、媒体捕获、音频解码/转写、非空 Markdown 及正文隐私检查；`CAPTURE_NO_MEDIA` 和任何隔离探测失败都不计成功。
- 记录 OS build、sandbox/provider 身份与版本、规则摘要、Chromium revision、正负探测结果及捕获状态；不得记录 Cookie、签名媒体 URL 或逐字稿正文。

## 当前实施状态

- 2026-10-10 的架构选择仍是项目维护、管理员安装的 Windows WFP 用户态服务；暂不实现 Linux namespace 或 macOS Network Extension adapter。§115 的用户 SID WFP curl smoke 将独立低权限账户列为服务身份策略候选，但没有改变架构选择或关闭 P2。
- 当前应用侧 fail-closed gate 尚未达到目标 IPC 契约：`acquire()` 不接收客户端身份或端口字段，但 lease 仍把 Chromium executable metadata 和 loopback endpoint 暴露给调用方；如果真实 broker 返回 lease，`BrowserCapture` 会在普通调用进程运行 Playwright 并启动 Chromium。`open_system_broker()` 明确失败，因此该路径当前不可达。`browser_proxy.py` 不在 capture 路径，Python 也不持有 listener socket或创建上游 relay。浏览器 request/WebSocket route 只校验 scheme/hostname/URL，不从 CLI 进程查询 DNS；完整 A/AAAA/CNAME 校验和 numeric-IP pinning 必须由未来 per-lease worker 完成。目标要求 CLI 只发 capture 请求并通过认证 IPC 接收结果，worker 独占浏览器身份、endpoint、DNS 和 upstream sockets。native pipe 与 Python adapter 的协议切片已有源码，但项目 WFP service、per-lease worker/token 启动、生产服务身份配置、服务代理、过滤器核验、策略版本/摘要和服务端 lease 行为均仍未实现。
- 当前 Codex 进程为普通令牌；§173 的标准 UAC 只读管理员子进程成功启动，§108 的执行器拦截结论已过时。没有 Douyin/WFP broker 服务。此前 Sandbox guest 的 WFP smokes仅覆盖 curl/规则阻断与恢复，没有 Chromium 或项目 broker，且 IPv6 仅测试 `::1`，不能证明公网 IPv6 或浏览器策略。宿主 WFP/Firewall 本轮未改动。§178 按 `global.json` 在用户 LocalAppData 安装 pinned .NET SDK 10.0.401，并重跑 capture-pipe 与 WFP source harness；结果通过，但仍没有服务实现、per-lease token/worker 或 WFP runtime integration。仍缺 MSVC/Windows SDK headers、CMake/WiX 工具链，部署验收继续限定在可回滚 Win11 环境。
- 该提权探针没有修改 Windows Firewall、WFP、注册表或其他系统网络策略；也没有安装、启动或创建项目服务/过滤器。
- AUD-77 保持 **OPEN**。现有单元测试证明没有 broker 时应用在 browser spawn 前拒绝；项目 WFP 服务、构建/安装器、有效策略证明和隔离环境中的 Chromium 动态验收均未完成。

### 2026-10-11 §132 regression and administrator access update

The §131 scanner fix is covered by full-suite runs on Windows Python 3.11.15 (**522 passed, 24 skipped**) and 3.12.13 (**521 passed, 25 skipped**); no test failed. The latest user authorization to “handle it” still does not provide an administrator host or remote access endpoint. The Codex process has no elevated token and no broker is available. No host WFP/Firewall changes were made. The selected Windows service architecture remains unimplemented; capture stays fail closed pending a worker-owned execution path and a real administrator validation environment.

## 2026-10-11 per-user SID WFP smoke 与 Chromium 失败

guest SYSTEM 在网络开启的 Sandbox 中为随机低权限本地账户创建动态 `ALE_USER_ID` / `FWP_SECURITY_DESCRIPTOR_TYPE` block。账户 HTTPS 基线成功；过滤时 curl 失败、SYSTEM 同目标对照成功；关闭动态会话后账户 curl 恢复。WFP engine、sublayer、filter 和 session close 均返回 0。Microsoft 的官方用户条件示例确认自相对安全描述符 DACL 使用 `FWP_ACTRL_MATCH_FILTER` 判断是否匹配，而非代表允许网络流量：[用户/应用过滤示例](https://learn.microsoft.com/en-us/windows/win32/fwp/permitting-and-blocking-applications-and-users)。

相同 harness 的 Chromium 在过滤前后均未通过：凭据启动的 `--version`/headless probe 超时或退出 `0xC06D007E`，没有浏览器日志/截图；另在网络关闭 Sandbox 的真实交互 session 中，正确 ACL 后 Chromium 进程树仍未在 20 秒内完成 headless 页面。该差异尚不能定位到 WFP 或一般 Windows 桌面；service 需要用受支持的 user-session token/profile/desktop 启动路径另做验证。最终 JSON 为 `sandbox-results/chromium-user-sid-wfp-smoke.json`（忽略文件），总体 `status=fail`；curl 规则子项可继续作为候选证据。§115 保留了详情。

**对策：** §117 已证明 guest 临时 station/desktop ACL 能让 Chromium 越过 `USER32.dll!GetProcessWindowStation` 延迟加载失败，但这组宽 ACL 只能作为诊断，不能直接用于产品。当前下一步是用窄过滤事件跟踪定位 `ProcessSingleton` 中命名 mutex、profile lockfile、消息窗口创建的实际失败 API；§118 的 PML 导出无可用 CSV，§119 的早期 SwiftShader 结果因 GPU 参数冲突不能用于归因，§120 的正确 SwiftShader 截图和 `--dump-dom` 对照仍超时且没有输出。随后在专用会话中证明锁定 Chromium 稳定渲染，再验证完整进程树、必要代理端点以及 WFP user-SID lease，并为产品定义最小 ACL。不能以 `--no-sandbox` 或关闭 Crashpad 规避，也不能在当前普通 host token 下安装/改写宿主策略。服务/IPC/installer/rollback 与全部 P2 运行时验收均未完成，应用继续 fail closed。

## 2026-10-10 Sandbox 准备状态

经用户授权，已通过标准 UAC 启用 Windows Sandbox 的 `Containers-DisposableClientVM` 功能并完成宿主重启。Sandbox 可启动，默认 `WDAGUtilityAccount` 为管理员组成员且 BFE 运行。修正为原生空指针并使用 `RPC_C_AUTHN_WINNT`（10）后，默认 guest 与 SYSTEM 均成功打开 `FwpmEngineOpen0`、创建枚举句柄并读到一个 filter；`RPC_C_AUTHN_DEFAULT`（0）返回 Win32 50。guest SYSTEM 也成功导出 WFP 状态。read-only `.wsb` 关闭网络；`NetworkWfpSmoke.wsb` 启用网络并通过 §105 的 dynamic IPv4 TCP block/release smoke；§106 的 `ScopedNetworkWfpSmoke.ps1` 通过 PowerShell AppID 的临时五规则条件验证；§109 从带 SHA-256 pin 的预览 JSON 构造规则；§110 增加逐规则语义 allowlist，并使用单一成功基线的数值 IPv4 地址复验拦截及清理。所有结果仅适用于当前 Sandbox build 和 PowerShell image；IPv6 只探测 `::1`，不验证公网 IPv6、Chromium 身份、项目 service/IPC、持久 deny 或生产策略。没有修改宿主 Firewall/WFP、服务、注册表或网络策略。项目 WFP service/IPC/installer/rollback 仍未实现；详见 `PROJECT_AUDIT_REPORT.md` §§104–110。

## 2026-10-10 管理员能力与本机方案复核（§90 历史快照，已由 §93 取代）

- 用户授权代理自主查找解决路径并已成功触发 UAC；提升的进程只查询管理员令牌、BFE/Windows Defender Firewall 服务状态和 Windows 可选功能。本机读写权限并未用于改动 WFP/Firewall。
- 此处的 Sandbox/Hyper-V/WSL `Disabled` 是 §90 历史快照。该段关于 `Fwpm*` 管理 API 的一般支持不构成当前 guest 可调用证明；启用后的只读探针见 §104，有限 dynamic block/release smoke 见 §105。后者只覆盖一次性 guest 里的 IPv4 TCP 连接，不是项目策略或浏览器隔离证明。
- 只读技术评估确认基础 ALE 过滤器不必然需要自写 kernel callout；但可部署方案仍缺固定服务身份/签名锚、受限且认证的 IPC、跨 IPv4/IPv6 的持久默认拒绝、同 sublayer 权重设计、临时精确代理许可、断线与已建连接复核、安装/更新/卸载回滚及锁定 Chromium 路径防替换。Windows Firewall 中普通显式 block 可能压过冲突 allow，因此临时创建一组通用规则不能作为有效代理例外或隔离证明；参见 Microsoft [filter arbitration](https://learn.microsoft.com/en-us/windows/win32/fwp/filter-arbitration)。
- **决策：** 保持已选的管理员管理 WFP broker 架构与应用侧 fail-closed。当前 UAC 能力只证明可运行管理员探针，不提供可信 broker 或其生命周期/策略承诺；这轮不创建过滤器、不安装服务，也不将 AUD-77/P2 标为通过。应先提供管理员维护的已验证 broker，或另行完成经审查的项目服务、安装器和完整失效验收，再运行真实 Chromium 正负向网络测试。评估细节见 `PROJECT_AUDIT_REPORT.md` §90。

## 2026-10-10 架构修订（取代外部 broker 选择）

可行性复核认为，项目自带的管理员安装 WFP 用户态服务是本机可推进的路径。首阶段仅支持 Windows 11 x64：对受保护路径下的锁定 Chromium 设置持久 ALE IPv4/IPv6 默认拒绝；每次 capture 使用独立 dynamic session 精确允许 TCP 到 `127.0.0.1:<port>`；服务负责验证规则、IPC 身份与 lease 生命周期，Python 进程不直接改策略。§105/§106 验证基础 filter block/release 与 PowerShell AppID 的五规则条件/动态生命周期；§109 让 Sandbox probe 从带 SHA-256 pin 的 typed preview JSON 构造五条规则；§110 为五规则增加独立 allowlist，并以固定数值 IPv4 地址重新验证阻断与恢复。filter arbitration、Chromium identity、服务 lease、已建立连接撤销和服务/BFE 故障恢复仍须实测。项目还没有服务/安装器源码；当前 .NET 10/CsWin32 API 绑定探针已构建。宿主仍无 MSVC/Windows SDK headers 可用于结构布局对照；继续动态验证应只在 Sandbox 或其他可回滚环境进行，不能在日常主机写策略。应用继续 fail closed，AUD-77/P2 保持 OPEN/NOT PASSED。实施进展与证据边界见 `PROJECT_AUDIT_REPORT.md` §§93–110。

## 2026-10-10 UAC 自助提权复核（§95）

用户授权代理自行继续操作后，已在本机通过标准 UAC 启动只读管理员探针。高完整性子进程确认本机 Administrators SID 已启用、BFE 与 Windows Defender Firewall 服务运行；未发现项目 WFP broker/service。调用中的 Codex 进程本身仍是普通令牌，提权只作用于该次子进程。未创建、安装或修改任何服务、WFP/Firewall 规则、注册表或网络策略。最新证据见 `PROJECT_AUDIT_REPORT.md` §95。该结果消除了“没有管理员主机”的本机操作障碍，但不替代尚未实现的服务、IPC、安装回滚和动态隔离验收。

## 2026-10-11 AppContainer package-SID Sandbox smoke

§112 的 guest-only 原型验证了 per-lease AppContainer identity 的一个关键前置条件：两个独立 profile 产生不同 package SID，`curl.exe` 子进程 token 与各自 SID 一致；无 loopback exemption 时 listener 未收到连接，添加 profile exemption 后收到连接；两个 profile 对同一 pinned IPv4 HTTPS baseline 均成功。guest SYSTEM 创建一个 `FWPM_CONDITION_ALE_PACKAGE_ID` / `FWP_SID` 动态 IPv4 ALE connect block 后，第一个 profile 的 curl 返回连接失败码 7，第二个 profile 的同路径 curl 返回 0；关闭 dynamic session 后第一个恢复为 0。engine/sublayer/filter/session close 与 exemption removal 均返回 0。

这把 AppContainer SID 从未测试候选推进为可在当前 Sandbox build 中工作的 curl lease 区分机制候选，但尚不是产品决定或生产隔离证明。该 smoke 没有测试 Chromium/Playwright 启动及 browser/network/renderer/utility process SID、精确代理 allowlist、IPv6/UDP/QUIC、持久默认拒绝、provider arbitration、服务/IPC/安装回滚、BFE failure 或真实媒体捕获。§114 已在交互 Sandbox user session 捕获 Chromium AppContainer 的 Crashpad CreateNamedPipe 拒绝访问（0x5），随后 STATUS_BREAKPOINT；LOCAL 命名空间约束与当前 Win32 Crashpad 路径冲突是强根因推断。未与锁定二进制源码提交匹配，也没有运行页面或进程树。修复路径为维护可溯源的 LOCAL 管道 Chromium 构建，或重新设计不把 browser 根进程置于 AppContainer 的 OS 网络边界。URL capture 保持 fail closed，AUD-77/P2 OPEN/NOT PASSED。WFP package-SID pass 见忽略的 appcontainer-package-id-wfp-pass.json，Chromium 诊断见审核报告 §114。

## 2026-10-11 Chromium AppContainer 续验结果

同一 Sandbox 已连接桌面并成功使用 ExistingLogin（WDAGUtilityAccount，session 1）。在网络关闭 guest 中把 308 个锁定 Chromium 文件暂存到本地，并对 316 个文件/目录项显式授予 profile SID 读取/执行后，原先的 executable AccessCheck 错误消失；AppContainer 子进程 token 的 package SID 与测试 profile 相同。但 --version 和 --no-sandbox --version 都报告 Crashpad CreateNamedPipe 拒绝访问 (0x5)，随后以 STATUS_BREAKPOINT 退出。stderr 和 Application Error/WER 已保存；没有收集 dump、运行页面或验证进程树。Microsoft 要求 AppContainer 命名管道采用 LOCAL 命名空间，当前 Chromium Win32 Crashpad 源码默认路径没有 LOCAL，与实测错误吻合；根因尚未和精确二进制源码提交核对。见审核报告 §114、忽略的 Sandbox 结果 JSON。关闭 Sandbox 后 wsb list --raw 为空，宿主 WFP/Firewall 未修改。

对策：不能继续把原始 AppContainer SID 原型直接当作当前 Chromium 的生产隔离方式。可继续评估的两条路径是：基于已锁定 Chromium/Crashpad 源码维护 LOCAL 管道修复版并验收完整 Playwright/子进程/代理行为；或重新设计无需把 browser 根进程置于 AppContainer 的系统网络隔离边界。每条路径都需经真实正反向流量矩阵及至少三条获授权媒体验证，之后才能实现/部署服务。当前应用继续 fail closed，AUD-77/P2 保持 OPEN/NOT PASSED。

2026-10-11 复核发现交互 headless harness 的 `.Kill($true)` 与 Sandbox guest .NET 不兼容，修订版已改为按根 PID 和 staging 路径枚举、停止浏览器进程树并输出残留 PID。禁网 Sandbox 重跑确认根进程和 9 个后代均停止且无残留；Chromium 仍超时、无截图，结果仍 fail。该结果只关闭清理证据缺口，不算 Chromium 或隔离验收。详见审核报告 §116 和 P2_REPORT.md。P2/AUD-77 仍 OPEN/NOT PASSED。

## 2026-10-12 offline CONNECT handler source slice (§208)

The new native `HttpsConnectTunnel` is a single accepted-stream handler with no listener or service registration. It composes strict CONNECT/Host framing, the current exact and boundary-aware host allowlist, numeric DNS validation, permit-before-dial TCP connection, raw TLS relay, early-byte preservation, half-close, and per-tunnel bounds. The pinned .NET build and offline fake-stream harness pass. This source slice does not authenticate the accepted peer, obtain DNS egress permits, enforce per-lease concurrency, start Chromium, apply WFP, or prove isolation. `CaptureServiceFactory` remains fail closed; use this code only after the listener, lease identity, trusted resolver, WFP, and live validation gates are implemented.

2026-10-11 又在网络关闭的 Sandbox 中以 guest SYSTEM 使用 `CreateProcessAsUserW`，结合 `ExistingLogin` 探针取得的 session 1、低权限随机账户、用户 profile/environment 和显式 AppContainer 文件 ACL 启动同一 Chromium。初始转储把 `0xC06D007E` 定位到 `USER32.dll!GetProcessWindowStation`/Win32 1114；只在 guest 临时授予随机 SID station/desktop ACL 后该延迟加载异常消失，但浏览器随后以 exit code 21 报告 `ProcessSingleton` 初始化失败，仍无截图。相同 SID 的 `lockfile` 创建/删除探针成功，故具体失败 API 尚未定位。未调用任何 WFP API；Sandbox 已停止，宿主 Firewall/WFP 未改。§118 的 PML 离线导出未产出 CSV，也未取得根因证据。§120 进一步修正 headless harness 的 GPU 参数，并发现有效 SwiftShader 截图和 `--dump-dom` 均超时且无输出，仍未定位启动停滞。详见审核报告 §§117–120。下一步先定位 ProcessSingleton/启动卡点，再验证页面及完整子进程树，之后才继续 per-user WFP lease 和代理正反向流量验收；不能以关闭 Crashpad 或 Chromium sandbox 作为规避。P2/AUD-77 继续 OPEN/NOT PASSED，应用继续 fail closed。

## 2026-10-11 ProcessSingleton 命名 mutex 权限线索

进一步 guest-only 探针观察到，低权限目标 SID 在 session 1 能创建未命名 mutex，但对 `Local\ChromeProcessSingletonStartup!` 和随机 `Local\...` mutex 的创建/打开返回 Win32 5；相同 SID 的 lockfile 与窗口探针成功。`ExistingLogin` 能创建这些命名 mutex 并读取 `BaseNamedObjects` ACL，因此 session 命名对象命名空间 ACL 是强候选原因，尚不是已确认根因。唯一新 Sandbox 在 SYSTEM harness 启动前即被本机执行策略拦截；没有运行 mutex helper、Chromium 或预创建测试。Sandbox 已停止、列表为空，宿主 WFP/Firewall 未改。不得把宽 session-wide ACL 或固定名称 mutex 预创建作为产品修复，除非其安全边界、并发与生命周期已验证。详见 `PROJECT_AUDIT_REPORT.md` §123。P2/AUD-77 仍 OPEN/NOT PASSED，应用继续 fail closed。

## 2026-10-11 URL pipeline 收紧 (§151)

`TranscriptionPipeline` 已移除 caller-side `BrowserCapture` factory、普通 downloader 和 URL resolver 的注入参数及回退分支。任何非空 URL 批次必须经过完整作业 `CaptureServiceClient`；无 client 时在解析、任务恢复/存储和 browser profile 访问前 fail closed。短链解析与视频采集都由该 client 完成。legacy `BrowserCapture` 与 placeholder lease 类仍留在代码树中，但当前 `run_urls()` 不再调用它们；不可把旧 lease→调用方 Chromium 路径重新接回默认产品入口。产品 CLI 仍没有已验证的 service client，所以本次只收紧了调用边界，没有实现 service、worker、WFP 或真实 capture。Windows Python 3.11 管线回归 **42 passed、1 skipped**；管理员动态验收仍受当前进程无管理员令牌、无可接入管理员 endpoint 限制。P2/AUD-77/AUD-86 仍 **OPEN / NOT PASSED**。

## 2026-10-12 手动 WFP 诊断脚本范围风险（§201）

冻结扫描中的 `NetworkWfpWriteSmoke.ps1` 把 `runContext` 作为报告字段记录，但没有用它阻止 Sandbox 外执行。该入口现已替换为 fail-closed stub，在加载 native code 或打开 BFE 前立即抛错；旧 `.wsb` 调用不会添加 filter。没有通过环境变量或账户标记伪造 Sandbox 身份，也没有运行脚本/Sandbox wrapper/BFE/WFP。

AUD-130 的宿主误操作入口已代码级停用，动态验证尚未完成。未来只允许使用 C# materializer wrapper，在新建可销毁 Sandbox 中测试专用规则范围和退出清理；不得恢复全应用无条件 block。此问题不属于当前 URL capture 路径；生产 URL 入口继续 fail closed，P2 仍 **OPEN / NOT PASSED**。完整记录见 `PROJECT_AUDIT_REPORT.md` §201。

## 2026-10-12 per-lease 默认拒绝规则生命周期门槛（§216）

当前 `LeasePolicyCompiler` 的 non-deployable preview 为每个 lease SID/package identity 生成 IPv4 和 IPv6 catch-all block，并把 lifetime 标为 `PersistentDefaultDeny`；精确 lease permits 是预览中的例外。该选择有安全理由：服务/worker 意外退出时不能让浏览器在无规则状态下继续联网。但它与“每个任务仅用 dynamic WFP session 自动清理”的简化设计不同：持久 deny 必须由 service-owned provider/sublayer 管理，并在正常完成、崩溃恢复、服务重启和用户账户删除路径中精确读回、去重、回收；否则会遗留失效 SID 规则并持续累积。反过来，不能在证明 worker 与 Chromium 全部后代被 job kill-on-close 终止、listener 和 socket 已关闭之前先删除默认拒绝。动态 permit session 的关闭时序须与该底线协调。

在生产实现前，需补 provider/sublayer/filter 查询和 enumeration 的最小 native bindings，用稳定 service-owned keys 及 lease ID 识别本服务对象；事务内校验对象归属、SID、AppID、action、layer、address family 和 exact endpoint，启动时清理只属于本服务且确认过期的规则，运行时读回实际对象并注入故障覆盖 commit/abort/rollback。安全验证在新建可销毁 Sandbox 中进行，不在宿主应用。当前 materializer 只返回 `not-deployable` 内存预览，`CaptureServiceFactory` 仍注入 `FailClosedCaptureWorker`，此项是部署前设计门槛，不是当前生效规则问题。WFP 生命周期参考 [Object Management](https://learn.microsoft.com/en-us/windows/win32/fwp/object-management) 与 [Best Practices](https://learn.microsoft.com/en-us/windows/win32/fwp/best-practices)。P2 仍 **OPEN / NOT PASSED**；完整证据见审核报告 §216。

## 2026-10-12 per-lease 规则生命周期设计修订（§217）

离线策略编译器和物化器测试现只把 browser/worker AppID 的 IPv4/IPv6 catch-all default deny 标记为 persistent；lease SID 的 catch-all block、精确 listener block 与 permit 统一属于该 lease 的 dynamic session。此处 AppID 仍来自预览输入，尚未绑定固定且受保护的浏览器/worker 文件，也没有分离的 runtime plan 类型。此前 §216 关于“每个 lease SID 默认拒绝为 persistent、正常/崩溃路径需精确删除”的建议由此修订，避免持久 SID filter 在 lease 结束后积累。

动态 SID deny 只有与服务持有、禁止 breakaway 的 `KILL_ON_JOB_CLOSE` Job Object 配合才可安全接线：进程必须 suspended 创建、加入 job 后再 resume；服务崩溃/回收时先终止完整 browser/worker 后代并关闭 listener/socket，再结束动态 WFP session。固定 AppID baseline 必须在 service 接受 IPC/SCM 报告运行前建立、读回和校验。当前没有这些 job/lifecycle/runtime coordinator，也未在 disposable Sandbox 验证，因此这里只修正 `not-deployable` 预览语义；生产 URL path 仍 fail closed，未调用 BFE/WFP，也未修改宿主策略。

`NativeMethods.txt` 已有 filter get-by-key/delete，仍缺 provider/sublayer get-by-key；filter enumeration 也未绑定，持久 baseline 的启动重协调仍需最小 API 设计。可用确定性 key 对 lease dynamic object 按 session 管理，避免把 enumeration 误列为每次 lease close 的必需步骤。编译器/物化器离线 harness 为 **11/11**。P2 仍 **OPEN / NOT PASSED**；实施与证据见审核报告 §217。

## 2026-10-12 readiness、程序集与基线协调器边界（§219–§222）

`CaptureServiceRuntime` 的启动取消现在等待 readiness gate 完成或回滚后才报告停止；gate 成功返回后会再次检查取消/期限，避免取消后创建 pipe。纯托管 `WfpPolicy.Core` 已从 CsWin32 预览程序集拆出规则编译器、DTO 和 typed plans；WFP preview 仅引用 Core，Core 不调用 BFE/WFP。现新增独立 `WfpPolicy.Runtime` 程序集，内含基线协调器、固定 provider/sublayer/filter keys、交易型 store 接口、完整 readback 对比与补偿逻辑。store 合同要求快照覆盖本服务 provider 的过滤器，以及不论 provider 归属、挂在本服务 baseline sublayer 的全部过滤器；对后者的外部或未知对象 fail closed。策略漂移时旧 filter 只删除一次；补偿前会在事务内核对完整预期提交快照，遇到同 key 外部替换则 abort、不改写未知对象，并保持 readiness closed。fake-store harness **9/9**，覆盖漂移替换、未知 sublayer 对象和不确定状态回滚。这个原型尚无 native BFE/WFP backend，未接到 `CaptureServiceFactory`，也没有真实 WFP 对象读取或写入。CI 已对该 runtime/harness 做格式、锁定还原、Release 构建、harness 与 BOM 比对。`CaptureServiceFactory` 继续通过 unavailable readiness gate fail closed；不得在真实 backend、生产接线和一次性 guest 验收完成前开放 URL capture。生产实施仍须使用固定 service-owned keys，读回并校验持久 AppID baseline，再按 lease 建立独立动态策略；worker 和 Chromium 必须处于已核验身份与禁止 breakaway 的 Job Object 中，确认进程树和 socket 关闭后才能结束该 lease session。构建 BOM 已以单独的 related build 纳入 Runtime 项目与 harness，但仅是本地构建身份清单。以上是 source/fake-store 设计证据，不构成当前隔离证明；详见审核报告 §§219–222。

## 2026-10-12 native store 接线前的 readback 合同（§224；跟进 §226）

`WfpNativeObjectProjection` schema v1 现已为 managed provider/sublayer/filter 定义字段有序的 closed-world 对比；coordinator 在 mutation 前拒绝缺失/额外/乱序/不匹配字段、不完整标记和不支持版本。锁定 SDK 的 Release 构建与 fake-store harness **12/12** 通过。但它不是完整 native WFP 对象读取器：假存储从 managed desired values 派生投影，当前没有真实 adapter 解码原生结构。接入前仍须审核全部 native 字段、独立读取并规范化 `FWPM_*0` 对象、明确对象 security descriptor/ACL 和系统字段策略、处理 BFE 派生 effective weight，并保证实际 enum 在同一显式 transaction 内创建/消费且释放所有句柄/缓冲区；unknown/unreadable 必须 fail closed。没有在宿主或 Sandbox 调用 BFE/WFP，CaptureService factory 继续 fail closed，P2 未通过。详见审核报告 §§224、226。

## 2026-10-12 native reader layer/provider references (§245)

The separate `WfpPolicy.NativeReadback` prototype now enumerates `FWPM_LAYER0` in the same read transaction. It resolves `GUID_NULL` filter sublayer keys through the layer's `defaultSubLayerKey`, closes filter layer/effective-sublayer references, and checks nullable provider ownership keys on filters, sublayers, callouts, and provider contexts. Null provider pointers mean no association; unresolved provider rows stay inconclusive because read ACLs can hide objects. Native unmanaged fixture harness passes **31/31** and Runtime fake-store harness passes **15/15**; Release builds have **0 warnings/errors**, four format checks pass, and the .NET BOM is refreshed.

This adds no production backend or service connection. Follow-up §248 now reads and normalizes each enumerated layer descriptor, but no descriptor is compared to an approved service policy and enumeration visibility is still unproven. The global snapshot remains incomplete; Runtime rejects it before mutation. No live BFE/WFP/Sandbox/host Firewall call occurred. P2 remains **OPEN / NOT PASSED**; see audit report §§245, 248.

## 2026-10-12 native reader authentication and paging boundary (§251)

`WindowsWfpApi.OpenEngine` now calls `FwpmEngineOpen0` with `RPC_C_AUTHN_WINNT` (10), matching the prior read-only Sandbox capability probe, which observed service 10 succeeding and service 0 returning Win32 50. A fixture injects the native-call boundary and asserts that the production adapter passes 10 without invoking BFE. Enumeration still requests at most 64 objects per page. A full page that reaches exactly `MaxObjects` remains accepted and triggers one bounded sentinel query: an empty sentinel completes enumeration, while any returned row is rejected before it is appended. The pinned .NET SDK 10.0.401 locked restore completed, x64 Release build passed with **0 warnings / 0 errors**, and the unmanaged offline fixture harness passed **34/34**, including the two new checks. No fixture opened BFE.

These changes only fix the local read-only adapter contract. They do not create a production WFP backend or enable mutation; the snapshot still carries an enumeration-coverage issue and Runtime rejects incomplete snapshots before mutation. Service installation/identity authorization, live BFE/WFP readback under that identity, complete visibility under object READ ACLs, approved ACL comparison, unsupported IPsec provider-context decoding, production apply/readback/rollback and service wiring, per-lease worker/Chromium isolation, disposable Sandbox checks, and authorized successful capture evidence remain open. No BFE/WFP, host Firewall, Sandbox, service, or capture operation was performed for this change. P2 remains **OPEN / NOT PASSED**.
