param(
    [string]$ExecutablePath = 'C:\sandbox-chromium-interactive\chrome.exe',
    [string]$ResultPath = 'C:\sandbox-results\chromium-interactive-headless.json',
    [ValidateRange(1000,120000)]
    [int]$TimeoutMilliseconds = 20000,
    [switch]$UseSoftwareGl,
    [switch]$VerboseStartupLogging,
    [switch]$UseDumpDom
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-ChromiumProcessTreeSnapshot {
    param(
        [Parameter(Mandatory = $true)]
        [int]$RootProcessId,
        [Parameter(Mandatory = $true)]
        [string]$BrowserRoot
    )

    $snapshot = @(Get-CimInstance -ClassName Win32_Process -ErrorAction Stop)
    $knownIds = [System.Collections.Generic.HashSet[int]]::new()
    [void]$knownIds.Add($RootProcessId)
    $tree = [System.Collections.Generic.List[object]]::new()
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($item in $snapshot) {
            $processId = [int]$item.ProcessId
            if ($knownIds.Contains($processId) -or -not $item.ExecutablePath) { continue }
            try { $imagePath = [IO.Path]::GetFullPath($item.ExecutablePath) }
            catch { continue }
            if (-not $imagePath.StartsWith($BrowserRoot,[StringComparison]::OrdinalIgnoreCase)) { continue }
            if ($knownIds.Contains([int]$item.ParentProcessId)) {
                [void]$knownIds.Add($processId)
                $tree.Add($item)
                $changed = $true
            }
        }
    }
    return $tree.ToArray()
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$workRoot = Join-Path $env:TEMP ('chromium-headless-' + [Guid]::NewGuid().ToString('N'))
$userData = Join-Path $workRoot 'profile'
$screenshot = Join-Path $workRoot 'about-blank.png'
$logPath = Join-Path $workRoot 'chrome.log'
$result = [ordered]@{
    reportKind = 'chromium-interactive-headless-smoke'
    capturedAtUtc = [DateTime]::UtcNow.ToString('o')
    user = $identity.Name
    userSid = $identity.User.Value
    sessionId = [Diagnostics.Process]::GetCurrentProcess().SessionId
    executablePath = $ExecutablePath
    workingDirectory = Split-Path -Parent $ExecutablePath
    started = $false
    timedOut = $false
    terminationConfirmed = $null
    exitCode = $null
    screenshotExists = $false
    probeMode = if ($UseDumpDom) { 'dump-dom' } else { 'screenshot' }
    domDumpHasHtml = $false
    domDumpLength = 0
    gpuMode = if ($UseSoftwareGl) { 'swiftshader' } else { 'default' }
    browserProcessCleanup = $null
    chromeLogPath = $logPath
    chromeLogTail = ''
    errors = [System.Collections.Generic.List[string]]::new()
    status = 'fail'
}
$process = $null
$standardOutputTask = $null
$workRootCreated = $false
try {
    if (-not (Test-Path -LiteralPath $ExecutablePath -PathType Leaf)) { throw 'The staged browser executable is missing.' }
    if (Test-Path -LiteralPath $workRoot) { throw 'The temporary Chromium work directory already exists.' }
    New-Item -ItemType Directory -Path $workRoot -ErrorAction Stop | Out-Null
    $workRootCreated = $true
    $gpuArguments = if ($UseSoftwareGl) { '--use-gl=angle --use-angle=swiftshader' } else { '--disable-gpu' }
    $pageOutputArguments = if ($UseDumpDom) { '--dump-dom' } else { "--window-size=640,480 --screenshot=`"$screenshot`"" }
    $arguments = "--headless=new $gpuArguments --disable-background-networking --disable-component-update --disable-extensions --disable-sync --no-first-run --no-default-browser-check --enable-logging --log-file=`"$logPath`" --user-data-dir=`"$userData`" $pageOutputArguments"
    if ($VerboseStartupLogging) { $arguments += ' --v=1 --vmodule=process_singleton_win=2' }
    $arguments += ' about:blank'
    $process = [Diagnostics.Process]::new()
    $process.StartInfo.FileName = $ExecutablePath
    $process.StartInfo.Arguments = $arguments
    $process.StartInfo.WorkingDirectory = $result.workingDirectory
    $process.StartInfo.UseShellExecute = $false
    $process.StartInfo.CreateNoWindow = $true
    $process.StartInfo.RedirectStandardOutput = $UseDumpDom
    if (-not $process.Start()) { throw 'Process.Start returned false.' }
    $result.started = $true
    if ($UseDumpDom) { $standardOutputTask = $process.StandardOutput.ReadToEndAsync() }
    if ($process.WaitForExit($TimeoutMilliseconds)) {
        $result.terminationConfirmed = $true
        $result.exitCode = $process.ExitCode
    }
    else {
        $result.timedOut = $true
    }
    $browserRoot = [IO.Path]::GetFullPath((Split-Path -Parent $ExecutablePath)).TrimEnd('\') + '\'
    $stoppedProcessIds = [System.Collections.Generic.List[int]]::new()
    $remaining = @()
    for ($attempt = 0; $attempt -lt 10; $attempt++) {
        $remaining = @(Get-ChromiumProcessTreeSnapshot -RootProcessId $process.Id -BrowserRoot $browserRoot)
        if ($remaining.Count -eq 0 -and $process.HasExited) { break }
        foreach ($item in @($remaining | Sort-Object -Property CreationDate -Descending)) {
            try {
                Stop-Process -Id ([int]$item.ProcessId) -Force -ErrorAction Stop
                $stoppedProcessIds.Add([int]$item.ProcessId)
            }
            catch {
                if (Get-Process -Id ([int]$item.ProcessId) -ErrorAction SilentlyContinue) { $result.errors.Add("Failed to stop Chromium process $($item.ProcessId): $($_.Exception.Message)") }
            }
        }
        if (-not $process.HasExited) {
            try { Stop-Process -Id $process.Id -Force -ErrorAction Stop; $stoppedProcessIds.Add($process.Id) }
            catch { if (-not $process.HasExited) { $result.errors.Add("Failed to stop Chromium root process $($process.Id): $($_.Exception.Message)") } }
        }
        Start-Sleep -Milliseconds 250
    }
    $remaining = @(Get-ChromiumProcessTreeSnapshot -RootProcessId $process.Id -BrowserRoot $browserRoot)
    $rootStillRunning = -not $process.HasExited
    $result.terminationConfirmed = -not $rootStillRunning
    if ($result.terminationConfirmed) { $result.exitCode = $process.ExitCode }
    $result.browserProcessCleanup = [ordered]@{
        rootProcessId = $process.Id
        rootProcessExited = $result.terminationConfirmed
        stoppedProcessIds = @($stoppedProcessIds)
        remainingProcessIds = @($remaining | ForEach-Object { [int]$_.ProcessId })
    }
    $result.screenshotExists = Test-Path -LiteralPath $screenshot -PathType Leaf
    if ($UseDumpDom -and $standardOutputTask -and $standardOutputTask.IsCompleted) {
        $dump = $standardOutputTask.Result
        $result.domDumpLength = $dump.Length
        $result.domDumpHasHtml = $dump -match '(?is)<html[\s>].*</html>'
    }
    if (Test-Path -LiteralPath $logPath -PathType Leaf) { $result.chromeLogTail = (Get-Content -LiteralPath $logPath -Tail 160 -ErrorAction SilentlyContinue) -join "`n" }
    if ($result.screenshotExists) { Copy-Item -LiteralPath $screenshot -Destination (Join-Path (Split-Path -Parent $ResultPath) 'chromium-interactive-about-blank.png') -Force }
    $pageOutputSucceeded = if ($UseDumpDom) { $result.domDumpHasHtml } else { $result.screenshotExists }
    if (-not $result.timedOut -and $result.exitCode -eq 0 -and $pageOutputSucceeded -and @($result.browserProcessCleanup.remainingProcessIds).Count -eq 0) { $result.status = 'pass' }
}
catch { $result.errors.Add($_.Exception.Message) }
finally {
    if ($null -ne $process) { $process.Dispose() }
    if ($workRootCreated -and (Test-Path -LiteralPath $workRoot -PathType Container)) { Remove-Item -LiteralPath $workRoot -Recurse -Force -ErrorAction SilentlyContinue }
    $resultDirectory = Split-Path -Parent $ResultPath
    if (-not (Test-Path -LiteralPath $resultDirectory -PathType Container)) { New-Item -ItemType Directory -Path $resultDirectory | Out-Null }
    [IO.File]::WriteAllText($ResultPath,($result | ConvertTo-Json -Depth 6) + [Environment]::NewLine,[Text.UTF8Encoding]::new($false))
}

if ($result.status -ne 'pass') { throw "Interactive Chromium headless smoke failed; see $ResultPath." }
