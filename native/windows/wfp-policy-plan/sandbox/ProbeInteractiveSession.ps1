param(
    [string]$ResultPath = 'C:\sandbox-results\chromium-interactive-session.json',
    [guid]$RunToken = [guid]::Empty
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$process = [Diagnostics.Process]::GetCurrentProcess()
$session = [uint32]$process.SessionId
if ($session -eq 0) { throw 'ExistingLogin did not start in an interactive session.' }
if ($RunToken -eq [guid]::Empty) { throw 'Pass a fresh RunToken for this Sandbox diagnostic run.' }

$result = [ordered]@{
    reportKind = 'sandbox-interactive-session-probe'
    capturedAtUtc = [DateTime]::UtcNow.ToString('o')
    runToken = $RunToken.ToString('D')
    userSid = $identity.User.Value
    sessionId = $session
    processId = $process.Id
    status = 'pass'
}
$directory = Split-Path -Parent $ResultPath
if (-not (Test-Path -LiteralPath $directory -PathType Container)) { New-Item -ItemType Directory -Path $directory | Out-Null }
[IO.File]::WriteAllText($ResultPath,($result | ConvertTo-Json -Depth 4) + [Environment]::NewLine,[Text.UTF8Encoding]::new($false))
