param(
    [string]$SourcePath = 'C:\sandbox-chromium-source',
    [string]$DestinationPath = '',
    [string]$ResultPath = 'C:\sandbox-results\chromium-staging.json'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$source = [IO.Path]::GetFullPath($SourcePath)
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
if ([string]::IsNullOrWhiteSpace($DestinationPath)) {
    $DestinationPath = Join-Path $tempRoot ('DouyinChromiumDiagnostic-' + [Guid]::NewGuid().ToString('N'))
}
$destination = [IO.Path]::GetFullPath($DestinationPath)
$tempPrefix = $tempRoot.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if (-not $destination.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'DestinationPath must be a new guest-local subdirectory of the current user temporary directory.'
}
if (Test-Path -LiteralPath $destination) { throw 'DestinationPath already exists; choose a fresh guest-local path.' }

$sourceExe = Join-Path $source 'chrome.exe'
if (-not (Test-Path -LiteralPath $sourceExe -PathType Leaf)) { throw 'The mapped Chromium source executable is missing.' }
New-Item -ItemType Directory -Path $destination | Out-Null
foreach ($entry in Get-ChildItem -LiteralPath $source -Force) {
    Copy-Item -LiteralPath $entry.FullName -Destination $destination -Recurse -Force
}

$destinationExe = Join-Path $destination 'chrome.exe'
$sourceHash = (Get-FileHash -LiteralPath $sourceExe -Algorithm SHA256).Hash
$destinationHash = (Get-FileHash -LiteralPath $destinationExe -Algorithm SHA256).Hash
if ($sourceHash -ne $destinationHash) { throw 'The staged Chromium executable hash differs from the read-only source.' }
$files = @(Get-ChildItem -LiteralPath $destination -File -Recurse -Force)
$totalBytes = [Int64](($files | Measure-Object -Property Length -Sum).Sum)

$result = [ordered]@{
    reportKind = 'chromium-guest-local-staging'
    capturedAtUtc = [DateTime]::UtcNow.ToString('o')
    user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    userSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    sessionId = [Diagnostics.Process]::GetCurrentProcess().SessionId
    sourcePath = $source
    destinationPath = $destination
    fileCount = $files.Count
    totalBytes = $totalBytes
    sourceExecutableSha256 = $sourceHash
    stagedExecutableSha256 = $destinationHash
    status = 'pass'
}
$resultDirectory = Split-Path -Parent $ResultPath
if (-not (Test-Path -LiteralPath $resultDirectory -PathType Container)) { New-Item -ItemType Directory -Path $resultDirectory | Out-Null }
[IO.File]::WriteAllText($ResultPath, ($result | ConvertTo-Json -Depth 5) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
