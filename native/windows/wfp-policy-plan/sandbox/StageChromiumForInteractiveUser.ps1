param(
    [string]$SourcePath = 'C:\sandbox-chromium-source',
    [string]$DestinationPath = 'C:\sandbox-chromium-interactive',
    [string]$ResultPath = 'C:\sandbox-results\chromium-interactive-staging.json'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not ([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -eq 'S-1-5-18')) { throw 'The staging helper must run as guest SYSTEM.' }
if (-not (Test-Path -LiteralPath (Join-Path $SourcePath 'chrome.exe') -PathType Leaf)) { throw 'The mapped Chromium source executable is missing.' }
if (Test-Path -LiteralPath $DestinationPath) { throw 'The guest staging target already exists.' }

$interactiveUser = Get-LocalUser -Name 'WDAGUtilityAccount' -ErrorAction Stop
$interactiveSid = [Security.Principal.SecurityIdentifier]::new($interactiveUser.SID.Value)
$packageSid = [Security.Principal.SecurityIdentifier]::new('S-1-15-2-1')
$inherit = [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit
$entryCount = 0
New-Item -ItemType Directory -Path $DestinationPath | Out-Null
Get-ChildItem -LiteralPath $SourcePath -Force | Copy-Item -Destination $DestinationPath -Recurse -Force

$rootAcl = Get-Acl -LiteralPath $DestinationPath
$rootAcl.SetAccessRule([Security.AccessControl.FileSystemAccessRule]::new($interactiveSid,[Security.AccessControl.FileSystemRights]::ReadAndExecute,$inherit,[Security.AccessControl.PropagationFlags]::None,[Security.AccessControl.AccessControlType]::Allow))
$rootAcl.SetAccessRule([Security.AccessControl.FileSystemAccessRule]::new($packageSid,[Security.AccessControl.FileSystemRights]::ReadAndExecute,$inherit,[Security.AccessControl.PropagationFlags]::None,[Security.AccessControl.AccessControlType]::Allow))
Set-Acl -LiteralPath $DestinationPath -AclObject $rootAcl
$entryCount++
foreach ($entry in @(Get-ChildItem -LiteralPath $DestinationPath -Force -Recurse)) {
    $inheritFlags = if ($entry.PSIsContainer) { $inherit } else { [Security.AccessControl.InheritanceFlags]::None }
    $acl = Get-Acl -LiteralPath $entry.FullName
    $acl.SetAccessRule([Security.AccessControl.FileSystemAccessRule]::new($interactiveSid,[Security.AccessControl.FileSystemRights]::ReadAndExecute,$inheritFlags,[Security.AccessControl.PropagationFlags]::None,[Security.AccessControl.AccessControlType]::Allow))
    $acl.SetAccessRule([Security.AccessControl.FileSystemAccessRule]::new($packageSid,[Security.AccessControl.FileSystemRights]::ReadAndExecute,$inheritFlags,[Security.AccessControl.PropagationFlags]::None,[Security.AccessControl.AccessControlType]::Allow))
    Set-Acl -LiteralPath $entry.FullName -AclObject $acl
    $entryCount++
}

$result = [ordered]@{
    reportKind = 'chromium-interactive-user-staging'
    capturedAtUtc = [DateTime]::UtcNow.ToString('o')
    guestUser = $interactiveUser.Name
    guestUserSid = $interactiveSid.Value
    destinationPath = $DestinationPath
    fileCount = @(Get-ChildItem -LiteralPath $DestinationPath -File -Recurse -Force).Count
    aclEntryCount = $entryCount
    sourceExecutableSha256 = (Get-FileHash -LiteralPath (Join-Path $SourcePath 'chrome.exe') -Algorithm SHA256).Hash
    stagedExecutableSha256 = (Get-FileHash -LiteralPath (Join-Path $DestinationPath 'chrome.exe') -Algorithm SHA256).Hash
    status = 'pass'
}
$resultDirectory = Split-Path -Parent $ResultPath
if (-not (Test-Path -LiteralPath $resultDirectory -PathType Container)) { New-Item -ItemType Directory -Path $resultDirectory | Out-Null }
[IO.File]::WriteAllText($ResultPath,($result | ConvertTo-Json -Depth 5) + [Environment]::NewLine,[Text.UTF8Encoding]::new($false))
