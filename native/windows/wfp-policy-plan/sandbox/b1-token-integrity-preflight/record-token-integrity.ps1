param(
  [Parameter(Mandatory = $true)]
  [ValidateSet('Host', 'GuestControl', 'BrowserTarget')]
  [string]$Role,

  [Parameter(Mandatory = $true)]
  [string]$OutputPath,

  [Parameter(Mandatory = $true)]
  [string]$EnvironmentLabel
)

$ErrorActionPreference = 'Stop'

Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;

public static class B1TokenNative
{
    public const int TokenUser = 1;
    public const int TokenType = 8;
    public const int TokenElevationType = 18;
    public const int TokenElevation = 20;
    public const int TokenIntegrityLevel = 25;
    public const int TokenIsAppContainer = 29;
    public const uint TokenQuery = 0x0008;

    [DllImport("kernel32.dll")]
    public static extern IntPtr GetCurrentProcess();

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool OpenProcessToken(IntPtr process, uint access, out IntPtr token);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool GetTokenInformation(
        IntPtr token, int informationClass, IntPtr information,
        int informationLength, out int returnLength);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool CloseHandle(IntPtr handle);
}
'@

function Get-TokenUInt32 {
  param([IntPtr]$Token, [int]$InformationClass, [string]$ApiName)

  $buffer = [Runtime.InteropServices.Marshal]::AllocHGlobal(4)
  try {
    $returned = 0
    if (-not [B1TokenNative]::GetTokenInformation(
          $Token, $InformationClass, $buffer, 4, [ref]$returned)) {
      $code = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
      throw [ComponentModel.Win32Exception]::new($code, "$ApiName failed")
    }
    if ($returned -lt 4) {
      throw [InvalidOperationException]::new("$ApiName returned $returned bytes; expected 4")
    }
    return [Runtime.InteropServices.Marshal]::ReadInt32($buffer)
  }
  finally {
    [Runtime.InteropServices.Marshal]::FreeHGlobal($buffer)
  }
}

function Get-TokenSid {
  param([IntPtr]$Token, [int]$InformationClass, [string]$ApiName)

  $required = 0
  if ([B1TokenNative]::GetTokenInformation(
        $Token, $InformationClass, [IntPtr]::Zero, 0, [ref]$required)) {
    if ($required -le [IntPtr]::Size) {
      throw [InvalidOperationException]::new("$ApiName returned an invalid size")
    }
  }
  else {
    $sizeError = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
    if ($sizeError -ne 122 -or $required -le [IntPtr]::Size -or $required -gt 1048576) {
      throw [ComponentModel.Win32Exception]::new($sizeError, "$ApiName size query failed")
    }
  }

  $buffer = [Runtime.InteropServices.Marshal]::AllocHGlobal($required)
  try {
    $returned = 0
    if (-not [B1TokenNative]::GetTokenInformation(
          $Token, $InformationClass, $buffer, $required, [ref]$returned)) {
      $code = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
      throw [ComponentModel.Win32Exception]::new($code, "$ApiName read failed")
    }
    if ($returned -lt [IntPtr]::Size -or $returned -gt $required) {
      throw [InvalidOperationException]::new("$ApiName returned an invalid buffer length")
    }
    $sidPointer = [Runtime.InteropServices.Marshal]::ReadIntPtr($buffer)
    if ($sidPointer -eq [IntPtr]::Zero) {
      throw [InvalidOperationException]::new("$ApiName returned a null SID")
    }
    return [Security.Principal.SecurityIdentifier]::new($sidPointer)
  }
  finally {
    [Runtime.InteropServices.Marshal]::FreeHGlobal($buffer)
  }
}

function Get-IntegrityClass {
  param([uint32]$Rid)

  if ($Rid -eq 0) { return 'Untrusted' }
  if ($Rid -ge 0x1000 -and $Rid -lt 0x2000) { return 'Low' }
  if ($Rid -ge 0x2000 -and $Rid -lt 0x2100) { return 'Medium' }
  if ($Rid -ge 0x2100 -and $Rid -lt 0x3000) { return 'MediumPlus' }
  if ($Rid -ge 0x3000 -and $Rid -lt 0x4000) { return 'High' }
  if ($Rid -ge 0x4000 -and $Rid -lt 0x5000) { return 'System' }
  if ($Rid -ge 0x5000 -and $Rid -lt 0x6000) { return 'ProtectedProcess' }
  if ($Rid -ge 0x6000) { return 'SecureProcess' }
  return 'Unknown'
}

function Convert-QueryError {
  param([string]$ApiName, [Exception]$Exception)

  $code = $null
  if ($Exception -is [ComponentModel.Win32Exception]) {
    $code = $Exception.NativeErrorCode
  }
  return [ordered]@{
    api = $ApiName
    status = 'error'
    win32_error = $code
    error_type = $Exception.GetType().FullName
    detail = $Exception.Message
  }
}

$now = [DateTime]::UtcNow.ToString('o')
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$process = [Diagnostics.Process]::GetCurrentProcess()
$identityName = $identity.Name
$processId = $process.Id
$sessionId = $process.SessionId
$token = [IntPtr]::Zero
$failures = [Collections.Generic.List[object]]::new()
$tokenFields = [ordered]@{
  user_sid = $null
  integrity_sid = $null
  integrity_rid = $null
  integrity_class = 'unknown'
  token_type = 'unknown'
  token_elevation_type = 'unknown'
  elevated = $null
  is_app_container = $null
  admin_role_enabled = $null
}

try {
  if (-not [B1TokenNative]::OpenProcessToken(
        [B1TokenNative]::GetCurrentProcess(), [B1TokenNative]::TokenQuery, [ref]$token)) {
    $code = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
    throw [ComponentModel.Win32Exception]::new($code, 'OpenProcessToken(TokenQuery) failed')
  }

  foreach ($query in @(
      @{ Name = 'GetTokenInformation(TokenUser)'; Action = { $script:tokenFields.user_sid = (Get-TokenSid $token ([B1TokenNative]::TokenUser) 'GetTokenInformation(TokenUser)').Value } },
      @{ Name = 'GetTokenInformation(TokenIntegrityLevel)'; Action = {
          $sid = Get-TokenSid $token ([B1TokenNative]::TokenIntegrityLevel) 'GetTokenInformation(TokenIntegrityLevel)'
          $bytes = [byte[]]::new($sid.BinaryLength)
          $sid.GetBinaryForm($bytes, 0)
          $script:tokenFields.integrity_sid = $sid.Value
          $script:tokenFields.integrity_rid = [BitConverter]::ToUInt32($bytes, $bytes.Length - 4)
          $script:tokenFields.integrity_class = Get-IntegrityClass $script:tokenFields.integrity_rid
        }
      },
      @{ Name = 'GetTokenInformation(TokenType)'; Action = {
          $value = Get-TokenUInt32 $token ([B1TokenNative]::TokenType) 'GetTokenInformation(TokenType)'
          $script:tokenFields.token_type = switch ($value) { 1 { 'Primary' } 2 { 'Impersonation' } default { "Unknown($value)" } }
        }
      },
      @{ Name = 'GetTokenInformation(TokenElevationType)'; Action = {
          $value = Get-TokenUInt32 $token ([B1TokenNative]::TokenElevationType) 'GetTokenInformation(TokenElevationType)'
          $script:tokenFields.token_elevation_type = switch ($value) { 1 { 'Default' } 2 { 'Full' } 3 { 'Limited' } default { "Unknown($value)" } }
        }
      },
      @{ Name = 'GetTokenInformation(TokenElevation)'; Action = {
          $script:tokenFields.elevated = ((Get-TokenUInt32 $token ([B1TokenNative]::TokenElevation) 'GetTokenInformation(TokenElevation)') -ne 0)
        }
      },
      @{ Name = 'GetTokenInformation(TokenIsAppContainer)'; Action = {
          $script:tokenFields.is_app_container = ((Get-TokenUInt32 $token ([B1TokenNative]::TokenIsAppContainer) 'GetTokenInformation(TokenIsAppContainer)') -ne 0)
        }
      },
      @{ Name = 'WindowsPrincipal.IsInRole(Administrator)'; Action = {
          $principal = [Security.Principal.WindowsPrincipal]::new($identity)
          $script:tokenFields.admin_role_enabled = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        }
      }
    )) {
    try { & $query.Action }
    catch { $failures.Add((Convert-QueryError $query.Name $_.Exception)) }
  }
}
catch {
  $failures.Add((Convert-QueryError 'OpenProcessToken(TokenQuery)' $_.Exception))
}
finally {
  if ($token -ne [IntPtr]::Zero) { [void][B1TokenNative]::CloseHandle($token) }
  $identity.Dispose()
  $process.Dispose()
}

$guestSystemCandidate = $null
$browserDistinctFromSystem = $null
$actualIdentityType = 'unknown'
if ($tokenFields.user_sid -and $tokenFields.integrity_class -ne 'unknown') {
  $actualIdentityType = if ($tokenFields.is_app_container) {
    'AppContainer'
  }
  elseif ($tokenFields.user_sid -eq 'S-1-5-18') {
    'LocalSystem'
  }
  elseif ($tokenFields.token_type -eq 'Impersonation') {
    'ImpersonationToken'
  }
  else {
    'UserToken'
  }
  $guestSystemCandidate = (
    $Role -eq 'GuestControl' -and
    $tokenFields.user_sid -eq 'S-1-5-18' -and
    $tokenFields.integrity_class -eq 'System'
  )
  if ($Role -eq 'BrowserTarget') {
    $browserDistinctFromSystem = ($tokenFields.user_sid -ne 'S-1-5-18')
  }
}

$requiredCapabilities = switch ($Role) {
  'Host' { 'Host supervisor must start, execute in, and stop only this task-owned guest; verify externally.' }
  'GuestControl' { 'Guest SYSTEM token is a control-identity candidate only; verify host-mediated execution and cleanup externally.' }
  'BrowserTarget' { 'Record the exact low-privilege token identity; compare it with the approved browser/worker identity policy before B2.' }
}

$result = [ordered]@{
  schema = 'douyin-transcript-sandbox-b1-token-observation/v2'
  checked_at_utc = $now
  environment_label = $EnvironmentLabel
  observed_role = $Role
  machine_name = [Environment]::MachineName
  process_id = $processId
  session_id = $sessionId
  identity_name = $identityName
  actual_identity_type = $actualIdentityType
  token = $tokenFields
  control_capability_assessment = [ordered]@{
    guest_system_identity_candidate = $guestSystemCandidate
    browser_target_distinct_from_system = $browserDistinctFromSystem
    sandbox_start_execute_and_stop = 'not_tested_by_token_probe'
    wfp_policy_control = 'not_tested_by_token_probe'
  }
  required_control_capabilities = @($requiredCapabilities)
  observation_status = if ($failures.Count -eq 0) { 'complete' } else { 'error' }
  api_failures = @($failures)
}

$destination = [IO.Path]::GetFullPath($OutputPath)
$parent = [IO.Path]::GetDirectoryName($destination)
if (-not [IO.Directory]::Exists($parent)) {
  throw "Evidence directory does not exist: $parent"
}
$json = $result | ConvertTo-Json -Depth 8
[IO.File]::WriteAllText($destination, $json + "`n", [Text.UTF8Encoding]::new($false))

if ($failures.Count -gt 0) { exit 30 }
exit 0
