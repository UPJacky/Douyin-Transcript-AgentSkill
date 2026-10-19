param(
    [Parameter(Mandatory = $true)]
    [string]$DotNetPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectDirectory = $PSScriptRoot
$assemblyPath = Join-Path $projectDirectory 'bin\Release\net10.0\win-x64\WfpPolicyPlan.dll'
$artifactPath = Join-Path $projectDirectory 'artifacts\native-filter-plan.example.json'
$smokePath = Join-Path $projectDirectory 'sandbox\ScopedNetworkWfpSmoke.ps1'

foreach ($path in @($DotNetPath, $assemblyPath, $artifactPath, $smokePath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required filter-plan artifact input is missing: $path"
    }
}

$generatedLines = & $DotNetPath $assemblyPath --filter-plan
if ($LASTEXITCODE -ne 0) {
    throw "WfpPolicyPlan --filter-plan failed with exit code $LASTEXITCODE"
}
$generated = [string]::Join("`n", [string[]]$generatedLines) + "`n"
$checkedIn = [IO.File]::ReadAllText($artifactPath, [Text.Encoding]::UTF8)
if (-not [string]::Equals($generated, $checkedIn, [StringComparison]::Ordinal)) {
    throw 'Checked-in native filter plan is stale; regenerate it from --filter-plan and review the SHA pin.'
}

$artifactHash = (Get-FileHash -LiteralPath $artifactPath -Algorithm SHA256).Hash.ToLowerInvariant()
$smokeSource = [IO.File]::ReadAllText($smokePath, [Text.Encoding]::UTF8)
$pin = [regex]::Match($smokeSource, "(?m)^\`$expectedFilterPlanSha256 = '([a-f0-9]{64})'\s*$")
if (-not $pin.Success -or $pin.Groups[1].Value -ne $artifactHash) {
    throw 'Sandbox smoke SHA-256 pin does not match the generated native filter plan.'
}

Write-Output "Filter-plan artifact verified: $artifactHash"
