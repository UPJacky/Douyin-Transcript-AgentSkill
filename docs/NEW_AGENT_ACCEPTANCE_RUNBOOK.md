# 新 Agent 安装与调用验收

## 必要前提

真实验收必须由用户在新项目聊天中执行。该聊天必须连接同一项目目录和主机，使已安装的锁定依赖、balanced 模型及授权本地样本可访问，并提供能将 UTF-8 stdin 独立传给进程的结构化调用接口。

开始前先记录不含正文的会话预检：用户已在同一项目/主机打开新聊天；该聊天实际发现的 Skill 名称和发现入口；该会话当前默认模型；本地文件如何交给默认模型；以及结构化调用工具如何提供非 TTY UTF-8 stdin 并隐藏 stdin/stdout 正文。仅手动读取 Skill 路径不算“已发现 Skill”。必须在运行 ASR 前完成该预检；这些接口或隐私属性任一无法在该新会话中确认时，不运行 ASR，也不读取或传输原稿正文，只记录缺失项；不得凭当前会话或旧 reviewed 文件推定通过。

在读取原稿正文前，确认该会话有不把正文回显到工具输出或日志的本地文件到默认模型通道；提交正文给 CLI 前，确认结构化进程接口为非 TTY，且 stdin 不会被命令、终端回显或日志记录。“支持 stdin”本身不构成证明。任一条件缺失或无法确认时，在正文传输前停止；不得用真实正文试探通道。

正文只允许进入该会话的默认模型上下文和本机进程的 stdin。不得把正文放入 shell 命令、命令参数、临时文件、日志、报告或用户可见聊天。若新聊天没有独立 stdin 传输接口，立即停止校对步骤并只报告缺少该接口；不得用命令拼接、临时文件或其他回退方式传送正文。

预检记录模板（只填写工具名、能力状态和通过/停止；不要填正文、媒体内容或个人路径）：

```text
项目/主机一致：通过 / 停止
实际发现并调用的 Skill 入口：<名称和入口>
当前默认模型标识：<实际可见值 / 不可见>
本地文件读取工具：<工具名>；正文不进入工具输出/日志：已核验 / 未核验
结构化进程工具：<工具名>；argv 分项、shell=false、非 TTY、UTF-8 stdin；stdout/stderr/日志不含正文：已核验 / 未核验
预检结果：通过 / 停止；停止原因：<不含正文的缺失项>
```

所有隐私属性必须来自该宿主工具的实际行为或可信接口说明，不能仅凭工具名称或“支持 stdin”推定。预检不通过时不得运行 ASR 或打开原稿正文。

不要创建额外聊天；由用户在项目目录开启真实新聊天。复用已有 copied-Skill locked clean-install 证据（ACCEPTANCE §255），不要重装依赖或模型。

## 发给新 Agent 的验收要求

```text
请按项目中的 douyin-transcript Skill 完成一次真实新 Agent 验收。先记录本会话宿主实际发现的 Skill 名称和入口（例如 `/skills` 列表中的项目入口）；随后调用 `$douyin-transcript`，并按该入口指示读取 canonical `skills/douyin-transcript/SKILL.md`，核对其命令和隐私要求。手动读取路径不能代替 Skill 发现或调用。复用已安装的锁定依赖、balanced 模型和本地授权样本，不运行 sync/setup。运行 doctor，再对现存授权媒体执行 balanced 中文本地 ASR。仅在本会话默认模型上下文中读取原稿正文，保守纠错并补中文标点，保留不确定的人名、金额、年份等原文，不把正文输出到聊天、命令行、日志、临时文件或报告。用 review-sidecar 的结构化进程调用：uv 的参数逐项传入，stdin 只写一个 UTF-8 JSON 对象 {"reviewed_body":"…"}；不得把正文放入参数或 shell 字符串。保存独立校对稿，检查 sidecar_saved、路径、非空、校对范围提示、原稿 SHA-256 前后相同及 task_binding=registered；未注册时调用 bind-review-sidecar 并复核。最后只报告实际发现并调用的 Skill 名称/入口、宿主实际默认模型标识（能取得时）、命令退出码、状态、精确原稿/校对稿路径、哈希相同与 registered 结果，不贴正文。
```

复用现存媒体；下列 PowerShell 只将 JSON 摘要保存在进程内变量，不打印媒体正文：

```powershell
$ErrorActionPreference = 'Stop'
$sample = Join-Path $env:USERPROFILE 'Downloads\Video\发现更多精彩视频 - 抖音搜索_4.mp4'
if (-not (Test-Path -LiteralPath $sample -PathType Leaf)) { throw 'Existing authorized sample is unavailable.' }
$doctor = & uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript doctor --json
$doctorExit = $LASTEXITCODE
$doctorReport = ($doctor -join "`n") | ConvertFrom-Json
if ($doctorExit -ne 0 -or $doctorReport.capabilities.local_transcription -ne 'ready' -or $doctorReport.checks.model.status -ne 'ok' -or $doctorReport.checks.output_dir_permissions.status -ne 'ok') { throw 'Local ASR or private output-directory prerequisites are not ready; do not run ASR.' }
$preflightJson = & uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript transcribe --input-file $sample --profile balanced --language zh --dry-run --json
$preflightExit = $LASTEXITCODE
$preflight = ($preflightJson -join "`n") | ConvertFrom-Json
if ($preflightExit -ne 0 -or $preflight.items.Count -ne 1 -or $preflight.items[0].status -ne 'ready' -or $preflight.output_dir_permissions.status -ne 'ok') { throw 'ASR dry-run or private output-directory check failed; do not run ASR.' }
$asrJson = & uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript transcribe --input-file $sample --profile balanced --language zh --force --json
$asrExit = $LASTEXITCODE
$asr = ($asrJson -join "`n") | ConvertFrom-Json
if ($asrExit -ne 0 -or $asr.items.Count -ne 1 -or $asr.items[0].status -ne 'success' -or $asr.output_dir_permissions.status -ne 'ok') { throw 'Local ASR or output-directory privacy check failed; do not open the raw transcript.' }
$raw = [string]$asr.items[0].output_path
$rawHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $raw).Hash
```

新 Agent 在本地读取 raw、用该会话默认模型保守纠错并补中文标点。将正文通过结构化进程接口的 UTF-8 stdin 交给以下调用（每个参数单独传入）：

```text
Executable: uv
Arguments: ["run", "--project", ".\\skills\\douyin-transcript", "--locked", "--no-sync", "douyin-transcript", "review-sidecar", "--raw-file", "<raw-path>"]
Stdin: one UTF-8 JSON object: {"reviewed_body":"…"}
```

该命令没有 `--json` 开关，成功时直接返回 JSON 摘要。结构化调用同时记录其退出码到 `$sidecarExit`、标准输出到 `$sidecarJson`。正文不得出现在参数、shell 字符串、临时文件、日志或报告中。将命令输出保存在变量并只解析摘要：

```powershell
$sidecar = ($sidecarJson -join "`n") | ConvertFrom-Json
if ($sidecarExit -ne 0 -or $sidecar.status -ne 'sidecar_saved' -or -not (Test-Path -LiteralPath $sidecar.output_path -PathType Leaf)) { throw 'Review sidecar was not saved; report status only.' }
$reviewed = [string]$sidecar.output_path
if ((Get-Item -LiteralPath $reviewed).Length -le 0 -or -not (Select-String -LiteralPath $reviewed -SimpleMatch -Quiet '本文已由当前 Agent 默认模型进行文本校对和标点整理；未对照音视频逐字听审，存疑处需复听确认。')) { throw 'Review sidecar content/scope check failed; do not print file content.' }
$rawHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $raw).Hash
if ($rawHashAfter -ne $rawHashBefore) { throw 'Raw transcript changed during review.' }
$taskBinding = [string]$sidecar.task_binding
if ($sidecar.task_binding -ne 'registered') {
  $bindJson = & uv run --project .\skills\douyin-transcript --locked --no-sync douyin-transcript bind-review-sidecar --raw-file $raw --reviewed-file $reviewed
  $bindExit = $LASTEXITCODE
  $binding = ($bindJson -join "`n") | ConvertFrom-Json
  if ($bindExit -ne 0 -or $binding.task_binding -ne 'registered') { throw 'Review binding did not register; report status only.' }
  $taskBinding = [string]$binding.task_binding
}
if ($taskBinding -ne 'registered') { throw 'Review is not registered; report status only.' }
```

`$sidecarJson` 来自前述 stdin 调用；侧车 CLI JSON 只含状态、路径与绑定，不含正文。只核验并报告本会话实际发现/调用的 Skill 名称与入口、默认模型标识（能取得时）、`sidecar_saved`、reviewed 路径、非空、范围提示、raw 哈希前后相同及 `task_binding=registered`；不要把 doctor 原始 JSON 或任何正文贴入聊天。

其他开放项：当前执行环境无法听音，故不声明声学准确性；URL、声学听审、新 Agent 调用及远端发布验收仍未完成。SPDX PURL 拒绝非法 PyPI 名称/版本并对合法版本编码，当前 SBOM freshness 已通过。

本记录不含逐字稿正文或个人文件路径。复用原有 ASR 只证明“本次校对交付”，不代表新 ASR 的完整端到端验收。
