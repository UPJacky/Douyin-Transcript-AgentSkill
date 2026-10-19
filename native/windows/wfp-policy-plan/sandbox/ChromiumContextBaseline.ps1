param(
    [string]$ExecutablePath = 'C:\sandbox-chromium\chrome.exe',
    [string]$ResultPath = 'C:\sandbox-results\chromium-context-baseline.json',
    [ValidateRange(1000, 120000)]
    [int]$TimeoutMilliseconds = 10000
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$result = [ordered]@{
    reportKind = 'chromium-context-version-baseline'
    capturedAtUtc = [DateTime]::UtcNow.ToString('o')
    user = $identity.Name
    userSid = $identity.User.Value
    sessionId = [Diagnostics.Process]::GetCurrentProcess().SessionId
    exe = $ExecutablePath
    workingDirectory = $null
    arguments = '--version'
    outputEncoding = 'utf-8'
    started = $false
    processId = $null
    timedOut = $false
    killAttempted = $false
    terminationConfirmed = $null
    exitCode = $null
    stdoutCaptureComplete = $false
    stderrCaptureComplete = $false
    stdout = ''
    stderr = ''
    errors = [System.Collections.Generic.List[string]]::new()
}

$process = $null
$stdoutTask = $null
$stderrTask = $null
try {
    if (-not (Test-Path -LiteralPath $ExecutablePath -PathType Leaf)) {
        throw "Chromium executable not found: $ExecutablePath"
    }
    $result.workingDirectory = Split-Path -Parent $ExecutablePath
    $utf8 = [Text.UTF8Encoding]::new($false)
    $process = [Diagnostics.Process]::new()
    $process.StartInfo.FileName = $ExecutablePath
    $process.StartInfo.Arguments = '--version'
    $process.StartInfo.WorkingDirectory = $result.workingDirectory
    $process.StartInfo.UseShellExecute = $false
    $process.StartInfo.CreateNoWindow = $true
    $process.StartInfo.RedirectStandardOutput = $true
    $process.StartInfo.RedirectStandardError = $true
    $process.StartInfo.StandardOutputEncoding = $utf8
    $process.StartInfo.StandardErrorEncoding = $utf8

    if (-not $process.Start()) { throw 'Process.Start returned false.' }
    $result.started = $true
    $result.processId = $process.Id
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()

    if ($process.WaitForExit($TimeoutMilliseconds)) {
        $result.terminationConfirmed = $true
        $result.exitCode = $process.ExitCode
    }
    else {
        $result.timedOut = $true
        $result.killAttempted = $true
        try { $process.Kill() }
        catch { $result.errors.Add("Kill failed: $($_.Exception.Message)") }
        $result.terminationConfirmed = $process.WaitForExit(2500)
        if ($result.terminationConfirmed) { $result.exitCode = $process.ExitCode }
        else { $result.errors.Add('Process did not signal exit within 2500 ms after Kill; output capture may be incomplete.') }
    }

    $captureTasks = [Threading.Tasks.Task[]]@($stdoutTask, $stderrTask)
    if ([Threading.Tasks.Task]::WaitAll($captureTasks, 3000)) {
        $result.stdout = $stdoutTask.Result
        $result.stderr = $stderrTask.Result
        $result.stdoutCaptureComplete = $true
        $result.stderrCaptureComplete = $true
    }
    else {
        $result.errors.Add('Redirected output streams did not close within 3000 ms; no blocking read was attempted.')
    }
}
catch {
    $result.errors.Add($_.Exception.Message)
}
finally {
    if ($null -ne $process) { $process.Dispose() }
    $directory = Split-Path -Parent $ResultPath
    if ([string]::IsNullOrWhiteSpace($directory)) { $directory = (Get-Location).Path }
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) { New-Item -ItemType Directory -Path $directory | Out-Null }
    $json = $result | ConvertTo-Json -Depth 6
    [IO.File]::WriteAllText($ResultPath, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

if (-not $result.started -or $result.timedOut -or $result.exitCode -ne 0) {
    throw "Chromium context baseline failed or timed out; see $ResultPath."
}
