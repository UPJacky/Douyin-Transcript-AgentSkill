param(
    [string]$ChromiumPath = 'C:\sandbox-chromium-source\chrome.exe',
    [string]$ResultPath = 'C:\sandbox-results\chromium-as-user-token-smoke.json',
    [string]$SessionProbePath = 'C:\sandbox-results\chromium-interactive-session.json',
    [guid]$SessionProbeRunToken = [guid]::Empty,
    [string]$ProcDumpPath = '',
    [switch]$ProbeProcessSingletonApis,
    [switch]$PrecreateProcessSingletonMutex,
    [guid]$ProcessSingletonMutexRunToken = [guid]::Empty,
    [switch]$LaunchChromiumAfterApiProbe,
    [string]$ProcessSingletonProbePath = 'C:\sandbox-readonly\ProcessSingletonApiProbe.ps1',
    [switch]$GrantInteractiveDesktopAccess,
    [guid]$DesktopAclGrantRunToken = [guid]::Empty,
    [ValidateRange(15, 180)]
    [int]$DesktopAclGrantTimeoutSeconds = 60,
    [ValidateRange(1000, 120000)]
    [int]$TimeoutMilliseconds = 30000
)
throw 'CreateProcessAsUser Chromium smoke is disabled until a trusted Sandbox guest attestation is implemented.'
