[CmdletBinding()]
param(
  [string]$AttemptRoot,
  [string]$ConfigPath,
  [string]$InputPath,
  [string]$GuestRunnerPath,
  [string]$TestPagePath,
  [string]$EvidenceDirectory,
  [string]$WsbPath,
  [switch]$Execute,
  [switch]$ConnectBeforeExec,
  [switch]$InventoryParserSelfTest,
  [switch]$WtsNativeControlOnly,
  [switch]$WtsDesktopAclDiagnosticOnly,
  [switch]$WtsLoaderSnapsOnly,
  [switch]$WtsProcessSingletonDiagnosticOnly,
  [string]$CdbPath,
  [string]$LoaderTargetPath
)

$ErrorActionPreference = 'Stop'
$WtsSessionDiagnosticOnly = $WtsNativeControlOnly -or $WtsDesktopAclDiagnosticOnly -or $WtsLoaderSnapsOnly -or $WtsProcessSingletonDiagnosticOnly
if ([string]::IsNullOrWhiteSpace($AttemptRoot)) {
  $policyRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
  $AttemptRoot = Join-Path $policyRoot 'sandbox-results\b2-launcher-reliability-20261016'
}
if ([string]::IsNullOrWhiteSpace($ConfigPath)) { $ConfigPath = Join-Path $AttemptRoot 'host-control\sandbox-config.xml' }
if ([string]::IsNullOrWhiteSpace($InputPath)) { $InputPath = Join-Path $AttemptRoot 'host-control\locked-chromium-input.json' }
if ([string]::IsNullOrWhiteSpace($GuestRunnerPath)) { $GuestRunnerPath = Join-Path (Join-Path $AttemptRoot 'host-runner') 'run-b2-locked-chromium.ps1' }
if ([string]::IsNullOrWhiteSpace($TestPagePath)) { $TestPagePath = Join-Path (Join-Path $AttemptRoot 'host-runner') 'test-page.html' }
if ([string]::IsNullOrWhiteSpace($EvidenceDirectory)) { $EvidenceDirectory = Join-Path $AttemptRoot 'guest-evidence' }
if (-not [IO.Path]::IsPathRooted($AttemptRoot)) {
  [Console]::Error.WriteLine('AttemptRoot must be an absolute path.')
  exit 2
}
$AttemptRoot = [IO.Path]::GetFullPath($AttemptRoot).TrimEnd('\')

$manifestPath = Join-Path $AttemptRoot 'host-control\run-manifest.json'
$observationPath = Join-Path $EvidenceDirectory 'b2-observation.json'
if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
  [Console]::Error.WriteLine("Refusing to overwrite an existing run manifest: $manifestPath")
  exit 3
}
if (Test-Path -LiteralPath $EvidenceDirectory -PathType Container) {
  $existingEvidence = @(Get-ChildItem -LiteralPath $EvidenceDirectory -Force -ErrorAction Stop)
  if ($existingEvidence.Count -gt 0) {
    [Console]::Error.WriteLine("Refusing to reuse a non-empty evidence directory: $EvidenceDirectory")
    exit 3
  }
}
$script:manifestCreated = $false
$startWasInvoked = $false
$manifest = [ordered]@{
  schema = 'b2-locked-chromium-run/v2'
  prepared_at_utc = [DateTime]::UtcNow.ToString('o')
  attempt_root = $AttemptRoot
  run_id = 'unknown'
  task_owned_sandbox_id = 'unknown'
  launch_requested = [bool]$Execute
  native_control_mode = if ($WtsProcessSingletonDiagnosticOnly) { 'wts-medium-process-singleton-diagnostic-only' } elseif ($WtsLoaderSnapsOnly) { 'wts-medium-loader-snaps-diagnostic-only' } elseif ($WtsDesktopAclDiagnosticOnly) { 'wts-medium-desktop-acl-diagnostic-only' } elseif ($WtsNativeControlOnly) { 'wts-medium-native-only' } else { 'standard-b2' }
  b2_acceptance = if ($WtsSessionDiagnosticOnly) { 'not_evaluated_diagnostic_only' } else { 'pending' }
  phase = 'validation'
  side_effects_started = $false
  validation = [ordered]@{ status = 'pending'; errors = @(); config_path = $ConfigPath; config_sha256 = 'unknown'; input_path = $InputPath; input_sha256 = 'unknown'; networking = 'unknown'; clipboard_redirection = 'unknown'; mapped_folders = @(); browser_path = 'unknown'; browser_file_version = 'unknown'; browser_product_version = 'unknown'; browser_sha256 = 'unknown'; browser_length = 'unknown'; probe_path = 'unknown'; probe_sha256 = 'unknown'; desktop_acl_probe_path = 'unknown'; desktop_acl_probe_sha256 = 'unknown'; helper_path = 'unknown'; helper_sha256 = 'unknown'; helper_assembly_path = 'unknown'; helper_assembly_sha256 = 'unknown'; helper_assembly_length = 'unknown'; native_diagnostic_path = 'not_required'; native_diagnostic_sha256 = 'not_required'; native_diagnostic_length = 'not_required'; cdb_source_path = 'not_requested'; cdb_sha256 = 'not_requested'; cdb_authenticode_status = 'not_requested'; loader_target_source_path = 'not_requested'; loader_target_sha256 = 'not_requested'; staged_debugger_files = @(); guest_runner_sha256 = 'unknown'; test_page_sha256 = 'unknown' }
  staging = [ordered]@{ status = if ($WtsLoaderSnapsOnly) { 'pending; occurs only with -Execute before WSB commands' } else { 'not_requested' }; debugger_runtime_manifest = $null; staged_files = @(); failure = $null }
  preflight = [ordered]@{ wsb_outer_exit_code = 'unknown'; raw_output = ''; raw_stderr = ''; timed_out = 'unknown'; timeout_seconds = 'unknown'; command_termination = 'unknown'; launch_error = $null; running_sandbox_ids = 'unknown'; status = 'not_run' }
  start = [ordered]@{ wsb_outer_exit_code = 'unknown'; requested_id = 'unknown'; returned_id = 'unknown'; raw_output = ''; raw_stderr = ''; timed_out = 'unknown'; timeout_seconds = 'unknown'; command_termination = 'unknown'; launch_error = $null; config_path = $ConfigPath; status = 'not_run'; ownership_resolution = 'not_started'; post_start_inventory = 'not_run' }
  connect = [ordered]@{ requested = [bool]$ConnectBeforeExec; wsb_outer_exit_code = 'not_run'; raw_output = ''; raw_stderr = ''; timed_out = 'not_run'; timeout_seconds = 'not_run'; command_termination = 'not_run'; launch_error = $null; status = if ($ConnectBeforeExec) { 'not_started' } else { 'not_requested' } }
  desktop_acl_probe = [ordered]@{ attempts = @(); wsb_outer_exit_code = 'unknown'; guest_process_exit_code = 'unknown'; raw_output = ''; raw_stderr = ''; timed_out = 'unknown'; timeout_seconds = 'unknown'; command_termination = 'unknown'; launch_error = $null; command = 'unknown'; run_as = 'ExistingLogin'; evidence_file = (Join-Path $EvidenceDirectory 'interactive-desktop-acl.json'); status = 'not_run'; user_sid = 'unknown'; logon_sid = 'unknown'; session_id = 'unknown'; token = $null; window_station_name = 'unknown'; desktop_name = 'unknown'; window_station_sddl_sha256 = 'unknown'; desktop_sddl_sha256 = 'unknown' }
  desktop_access_check = [ordered]@{ status = if ($WtsSessionDiagnosticOnly) { 'not_performed' } else { 'unknown' }; reason = if ($WtsSessionDiagnosticOnly) { 'WTS diagnostic-only modes never use guest-written DACL JSON as a launch gate; the dedicated ACL mode records strictly bound read-only desktop and BaseNamedObjects AccessChecks.' } else { 'unknown' }; target_user_sid = 'unknown'; target_logon_sid = 'unknown'; target_session_id = 'unknown'; window_station_access = 'unknown'; desktop_access = 'unknown'; window_station_api_succeeded = 'unknown'; desktop_api_succeeded = 'unknown'; window_station_desired_access = 'unknown'; desktop_desired_access = 'unknown'; probe_user_sid_matches_target = 'unknown'; probe_logon_sid_matches_target = 'unknown'; untrusted_dacl_hint_used = $false; base_named_objects_access_check = [ordered]@{ status = if ($WtsDesktopAclDiagnosticOnly) { 'not_measured' } else { 'not_requested' }; api_succeeded = 'unknown'; access_granted = 'unknown'; desired_access = 'unknown'; granted_access = 'unknown'; win32_error = 'unknown'; acl_mutated = $false; target_process_started = $false } }
  wts_medium_identity = 'unknown'
  desktop_acl_hint = [ordered]@{ status = if ($WtsSessionDiagnosticOnly) { 'not_read; guest-writable ExistingLogin DACL report is untrusted and non-gating' } else { 'not_requested' }; trust = 'untrusted guest-produced diagnostic'; gating = $false }
  guest_control = [ordered]@{ wsb_outer_exit_code = 'unknown'; guest_process_exit_code = 'unknown'; helper_exit_code = 'unknown'; raw_output = ''; raw_stderr = ''; timed_out = 'unknown'; timeout_seconds = 'unknown'; command_termination = 'unknown'; launch_error = $null; command = 'unknown'; run_as = 'System'; runner_invoked = 'unknown'; evidence_file = (Join-Path $EvidenceDirectory 'b2-observation.json'); status = 'not_run' }
  probe = [ordered]@{ status = 'unknown'; process_exit_code = 'unknown' }
  native_diagnostic = [ordered]@{ status = 'unknown'; root_exit_code = 'unknown'; cleanup_status = 'unknown'; active_processes_after = 'unknown' }
  browser = [ordered]@{ process_exit_code = if ($WtsProcessSingletonDiagnosticOnly) { 'not_run' } else { 'unknown' }; timed_out = if ($WtsProcessSingletonDiagnosticOnly) { 'not_run' } else { 'unknown' }; status = if ($WtsProcessSingletonDiagnosticOnly) { 'not_run; WTS ProcessSingleton diagnostic-only mode' } else { 'unknown' }; observation_file = (Join-Path $EvidenceDirectory 'b2-observation.json') }
  loader_diagnostic = [ordered]@{ status = if ($WtsLoaderSnapsOnly) { 'not_run' } else { 'not_requested' }; observation_file = $null; helper_status = 'unknown'; helper_reported_exit_code = 'unknown'; helper_exit_code_consistency = 'unknown'; helper_exit_code_matches_report = 'unknown'; process_tree_status = 'unknown'; ifeo_restore_status = 'unknown'; b2_pass = $false }
  page = [ordered]@{ status = if ($WtsProcessSingletonDiagnosticOnly) { 'not_run; WTS ProcessSingleton diagnostic-only mode' } else { 'unknown' } }
  process_singleton_diagnostic = [ordered]@{ status = if ($WtsProcessSingletonDiagnosticOnly) { 'not_run' } else { 'not_requested' }; observation_file = (Join-Path $EvidenceDirectory 'b2-observation.json'); runner_status_file = 'not_run'; runner_status = 'not_reported'; runner_wrapper_stage = 'not_reported'; runner_helper_process_exit_code = 'unknown'; runner_helper_timed_out = 'unknown'; helper_status = 'unknown'; helper_exit_code = 'unknown'; helper_exit_code_consistency = 'unknown'; probe_status = 'unknown'; probe_result = 'unknown'; probe_process_exit_code = 'unknown'; probe_timed_out = 'unknown'; probe_report_path = 'not_requested'; probe_report_bytes = 'unknown'; probe_report_sha256 = 'unknown'; process_tree_cleanup_status = 'unknown'; active_processes_after = 'unknown'; identity = $null }
  process_tree = [ordered]@{ cleanup_status = 'unknown'; active_processes_after = 'unknown' }
  stop = [ordered]@{ wsb_outer_exit_code = 'unknown'; task_owned_sandbox_id = 'unknown'; raw_output = ''; raw_stderr = ''; timed_out = 'unknown'; timeout_seconds = 'unknown'; command_termination = 'unknown'; launch_error = $null; pre_stop_manifest_save_error = $null; status = 'not_run' }
  post_stop_inventory = [ordered]@{ wsb_outer_exit_code = 'unknown'; raw_output = ''; raw_stderr = ''; timed_out = 'unknown'; timeout_seconds = 'unknown'; command_termination = 'unknown'; launch_error = $null; running_sandbox_ids = 'unknown'; status = 'not_run' }
  manifest_write_errors = @()
  failure = $null
}

function Save-Manifest {
  $temporaryPath = "$manifestPath.$PID.$([Guid]::NewGuid().ToString('N')).tmp"
  $json = $manifest | ConvertTo-Json -Depth 20
  [IO.File]::WriteAllText($temporaryPath, $json, [Text.UTF8Encoding]::new($false))
  if (-not $script:manifestCreated) {
    [IO.File]::Move($temporaryPath, $manifestPath)
    $script:manifestCreated = $true
  }
  else { Move-Item -LiteralPath $temporaryPath -Destination $manifestPath -Force }
}

function Get-CanonicalPath {
  param([string]$Path, [ValidateSet('File','Directory')][string]$Kind)
  if ([string]::IsNullOrWhiteSpace($Path) -or -not [IO.Path]::IsPathRooted($Path)) {
    throw "Expected an absolute $Kind path: '$Path'"
  }
  $item = Get-Item -LiteralPath $Path -ErrorAction Stop
  if ($Kind -eq 'File' -and $item.PSIsContainer) { throw "Expected a file path: '$Path'" }
  if ($Kind -eq 'Directory' -and -not $item.PSIsContainer) { throw "Expected a directory path: '$Path'" }
  return [IO.Path]::GetFullPath($item.FullName).TrimEnd('\')
}

function Test-JsonField {
  param($Object, [string]$Name)
  return $null -ne $Object -and $null -ne $Object.PSObject.Properties[$Name]
}

function Assert-JsonFields {
  param($Object, [string[]]$Names)
  $missing = @($Names | Where-Object { -not (Test-JsonField $Object $_) })
  if ($missing.Count -gt 0) { throw "Input JSON is missing required fields: $($missing -join ', ')" }
}

function ConvertTo-ValidatedGuid {
  param([string]$Value, [string]$FieldName)
  $parsed = [Guid]::Empty
  if (-not [Guid]::TryParseExact($Value, 'D', [ref]$parsed) -or $parsed -eq [Guid]::Empty) {
    throw "Input field '$FieldName' must be a non-empty D-format GUID."
  }
  return $parsed.ToString('D')
}

function Test-PathEqual {
  param([string]$Left, [string]$Right)
  return [string]::Equals([IO.Path]::GetFullPath($Left).TrimEnd('\'), [IO.Path]::GetFullPath($Right).TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)
}

function Get-FileSha256 {
  param([Parameter(Mandatory = $true)][string]$Path)
  $algorithm = [Security.Cryptography.SHA256]::Create()
  try {
    $stream = [IO.File]::OpenRead($Path)
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose() }
  }
  finally { $algorithm.Dispose() }
}

function Get-TextSha256 {
  param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text)
  $algorithm = [Security.Cryptography.SHA256]::Create()
  try {
    $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
    return [BitConverter]::ToString($algorithm.ComputeHash($bytes)).Replace('-', '').ToLowerInvariant()
  }
  finally { $algorithm.Dispose() }
}

function Get-PortableExecutableMachine {
  param([Parameter(Mandatory = $true)][string]$Path)
  $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
  try {
    if ($stream.Length -lt 70) { throw 'PE file is too short.' }
    $reader = [IO.BinaryReader]::new($stream)
    try {
      if ($reader.ReadUInt16() -ne 0x5A4D) { throw 'PE DOS signature is invalid.' }
      $stream.Position = 0x3C
      $peOffset = $reader.ReadInt32()
      if ($peOffset -lt 64 -or $peOffset -gt ($stream.Length - 6)) { throw 'PE header offset is invalid.' }
      $stream.Position = $peOffset
      if ($reader.ReadUInt32() -ne 0x00004550) { throw 'PE signature is invalid.' }
      return '0x{0:X4}' -f $reader.ReadUInt16()
    }
    finally { $reader.Dispose() }
  }
  finally { $stream.Dispose() }
}

function Write-NewUtf8File {
  param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)][string]$Content)
  $bytes = [Text.UTF8Encoding]::new($false).GetBytes($Content)
  $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
  try {
    $stream.Write($bytes, 0, $bytes.Length)
    $stream.Flush()
  }
  finally { $stream.Dispose() }
}

function Copy-NewVerifiedFile {
  param(
    [Parameter(Mandatory = $true)][string]$SourcePath,
    [Parameter(Mandatory = $true)][string]$DestinationPath,
    [Parameter(Mandatory = $true)][string]$ExpectedSha256
  )
  if (Test-Path -LiteralPath $DestinationPath) { throw "Refusing to overwrite staged debugger input: $DestinationPath" }
  $source = [IO.File]::Open($SourcePath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
  try {
    $destination = [IO.File]::Open($DestinationPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
      $buffer = [byte[]]::new(131072)
      while (($read = $source.Read($buffer, 0, $buffer.Length)) -gt 0) { $destination.Write($buffer, 0, $read) }
      $destination.Flush()
    }
    finally { $destination.Dispose() }
  }
  finally { $source.Dispose() }
  $copiedSha256 = Get-FileSha256 $DestinationPath
  $sourceSha256AfterCopy = Get-FileSha256 $SourcePath
  if ($copiedSha256 -ne $ExpectedSha256 -or $sourceSha256AfterCopy -ne $ExpectedSha256) {
    throw "Staged file hash did not match the validated source: $([IO.Path]::GetFileName($SourcePath))"
  }
  return [ordered]@{ relative_path = $DestinationPath; sha256 = $copiedSha256; length = (Get-Item -LiteralPath $DestinationPath).Length }
}

function Stage-LoaderSnapsRuntime {
  param(
    [Parameter(Mandatory = $true)][string]$RunnerDirectory,
    [Parameter(Mandatory = $true)][string]$CdbSourcePath,
    [Parameter(Mandatory = $true)][string]$TargetSourcePath,
    [Parameter(Mandatory = $true)][string]$RunId
  )
  if ([IO.Path]::GetFileName($CdbSourcePath) -ine 'cdb.exe' -or [IO.Path]::GetFileName($TargetSourcePath) -ine 'exit-only-probe.exe') {
    throw 'Loader Snaps staging requires cdb.exe and exit-only-probe.exe source basenames.'
  }
  $cdbSignature = Get-AuthenticodeSignature -LiteralPath $CdbSourcePath -ErrorAction Stop
  if ($cdbSignature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) { throw 'CDB Authenticode signature is not Valid.' }
  $cdbSignerSubject = [string]$cdbSignature.SignerCertificate.Subject
  if ($cdbSignerSubject -notmatch '(?i)Microsoft') { throw 'CDB Authenticode signer is not identified as Microsoft.' }
  if ((Get-PortableExecutableMachine $CdbSourcePath) -ne '0x8664' -or (Get-PortableExecutableMachine $TargetSourcePath) -ne '0x8664') { throw 'CDB and loader target must be x64 PE files.' }
  foreach ($sourcePath in @($CdbSourcePath, $TargetSourcePath)) {
    $sourceItem = Get-Item -LiteralPath $sourcePath -ErrorAction Stop
    if (($sourceItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Refusing to stage a reparse-point input: $([IO.Path]::GetFileName($sourcePath))" }
  }

  $sourceDirectory = Split-Path -Parent $CdbSourcePath
  $runtimeDlls = @(Get-ChildItem -LiteralPath $sourceDirectory -File -Filter '*.dll' -ErrorAction Stop | Sort-Object Name)
  $requiredRuntimeNames = @('dbgeng.dll','dbghelp.dll','dbgcore.dll')
  foreach ($requiredName in $requiredRuntimeNames) {
    if (@($runtimeDlls | Where-Object { [string]::Equals($_.Name, $requiredName, [StringComparison]::OrdinalIgnoreCase) }).Count -ne 1) {
      throw "CDB runtime closure is missing required member '$requiredName'."
    }
  }

  $debuggerRoot = Join-Path $RunnerDirectory 'debuggers'
  $targetRoot = Join-Path $RunnerDirectory 'loader-diagnostic'
  if (Test-Path -LiteralPath $debuggerRoot) { throw 'Refusing to reuse a pre-existing runner debugger directory.' }
  if (Test-Path -LiteralPath $targetRoot) { throw 'Refusing to reuse a pre-existing runner loader-diagnostic directory.' }
  $debuggerDirectory = Join-Path $debuggerRoot 'x64'

  $sourceInventory = [Collections.Generic.List[object]]::new()
  $sourceInventory.Add([ordered]@{ source_path = $CdbSourcePath; relative_path = 'debuggers/x64/cdb.exe'; sha256 = Get-FileSha256 $CdbSourcePath; authenticode_status = [string]$cdbSignature.Status; signer_subject = $cdbSignerSubject })
  foreach ($dll in $runtimeDlls) {
    if (($dll.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Refusing to stage a debugger runtime reparse point: $($dll.Name)" }
    if ((Get-PortableExecutableMachine $dll.FullName) -ne '0x8664') { throw "Debugger runtime member is not x64: $($dll.Name)" }
    $dllSignature = Get-AuthenticodeSignature -LiteralPath $dll.FullName -ErrorAction Stop
    if ($dllSignature.Status -ne [System.Management.Automation.SignatureStatus]::Valid -or [string]$dllSignature.SignerCertificate.Subject -notmatch '(?i)Microsoft') { throw "Debugger runtime member is not Validly signed by a Microsoft publisher: $($dll.Name)" }
    $sourceInventory.Add([ordered]@{ source_path = $dll.FullName; relative_path = "debuggers/x64/$($dll.Name)"; sha256 = Get-FileSha256 $dll.FullName; authenticode_status = [string]$dllSignature.Status; signer_subject = [string]$dllSignature.SignerCertificate.Subject })
  }
  $symSrvMarker = Join-Path $sourceDirectory 'symsrv.yes'
  if (Test-Path -LiteralPath $symSrvMarker -PathType Leaf) {
    $sourceInventory.Add([ordered]@{ source_path = $symSrvMarker; relative_path = 'debuggers/x64/symsrv.yes'; sha256 = Get-FileSha256 $symSrvMarker; authenticode_status = 'not_applicable_data_file'; signer_subject = 'not_applicable' })
  }
  $targetSha256 = Get-FileSha256 $TargetSourcePath
  New-Item -ItemType Directory -Path $debuggerRoot | Out-Null
  New-Item -ItemType Directory -Path $debuggerDirectory | Out-Null
  New-Item -ItemType Directory -Path $targetRoot | Out-Null
  $stagedMembers = [Collections.Generic.List[object]]::new()
  foreach ($member in $sourceInventory) {
    $destinationPath = Join-Path $RunnerDirectory ([string]$member.relative_path.Replace('/', '\'))
    $staged = Copy-NewVerifiedFile -SourcePath ([string]$member.source_path) -DestinationPath $destinationPath -ExpectedSha256 ([string]$member.sha256)
    $stagedMembers.Add([ordered]@{ relative_path = [string]$member.relative_path; sha256 = $staged.sha256; length = $staged.length; authenticode_status = [string]$member.authenticode_status; signer_subject = [string]$member.signer_subject })
  }
  $targetDestination = Join-Path $targetRoot 'exit-only-probe.exe'
  $targetStaged = Copy-NewVerifiedFile -SourcePath $TargetSourcePath -DestinationPath $targetDestination -ExpectedSha256 $targetSha256
  $stagedMembers.Add([ordered]@{ relative_path = 'loader-diagnostic/exit-only-probe.exe'; sha256 = $targetStaged.sha256; length = $targetStaged.length; authenticode_status = 'not_required_fixture_hash_bound'; signer_subject = 'not_applicable' })
  $stagedCdbPath = Join-Path $debuggerDirectory 'cdb.exe'
  $stagedSignature = Get-AuthenticodeSignature -LiteralPath $stagedCdbPath -ErrorAction Stop
  if ($stagedSignature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) { throw 'Staged CDB Authenticode signature is not Valid.' }

  $runtimeManifestPath = Join-Path $debuggerDirectory 'runtime-manifest.json'
  $runtimeManifest = [ordered]@{
    schema = 'b2-loader-snaps-debugger-runtime/v1'
    run_id = $RunId
    closure = 'cdb.exe plus every adjacent x64 DLL and symsrv.yes when present; every PE member must have a Valid Microsoft Authenticode signature; only cdb.exe is designated for launch'
    cdb_authenticode_status = [string]$stagedSignature.Status
    cdb_signer_subject = if ($stagedSignature.SignerCertificate) { [string]$stagedSignature.SignerCertificate.Subject } else { 'unknown' }
    files = @($stagedMembers | Where-Object { $_.relative_path -like 'debuggers/x64/*' })
  }
  Write-NewUtf8File -Path $runtimeManifestPath -Content ($runtimeManifest | ConvertTo-Json -Depth 8)
  return [pscustomobject]@{
    cdb_path = $stagedCdbPath
    cdb_sha256 = Get-FileSha256 $stagedCdbPath
    cdb_signature_status = [string]$stagedSignature.Status
    target_path = $targetDestination
    target_sha256 = Get-FileSha256 $targetDestination
    runtime_manifest_path = $runtimeManifestPath
    runtime_manifest_sha256 = Get-FileSha256 $runtimeManifestPath
    staged_files = @($stagedMembers.ToArray())
  }
}

function Read-SecureXml {
  param([string]$Path)
  $settings = New-Object System.Xml.XmlReaderSettings
  $settings.DtdProcessing = [System.Xml.DtdProcessing]::Prohibit
  $settings.XmlResolver = $null
  $reader = [System.Xml.XmlReader]::Create($Path, $settings)
  try {
    $document = New-Object System.Xml.XmlDocument
    $document.XmlResolver = $null
    $document.Load($reader)
    return $document
  }
  finally { $reader.Dispose() }
}

function ConvertFrom-WsbSandboxInventory {
  param($Inventory)

  $unrecognized = [pscustomobject]@{ recognized = $false; sandbox_ids = [string[]]@(); reason = 'inventory root must contain exactly WindowsSandboxEnvironments' }
  if ($Inventory -isnot [pscustomobject]) { return $unrecognized }

  $rootProperties = @($Inventory.PSObject.Properties)
  if ($rootProperties.Count -ne 1 -or $rootProperties[0].Name -cne 'WindowsSandboxEnvironments') {
    return $unrecognized
  }

  $environments = $rootProperties[0].Value
  if ($environments -isnot [Array]) {
    $unrecognized.reason = 'WindowsSandboxEnvironments must be an array'
    return $unrecognized
  }

  $identityNames = @('Id','SandboxId','InstanceId')
  $ids = [Collections.Generic.List[string]]::new()
  foreach ($environment in $environments) {
    if ($environment -isnot [pscustomobject]) {
      $unrecognized.reason = 'each WindowsSandboxEnvironments item must be an object'
      return $unrecognized
    }

    $identityProperties = @()
    foreach ($property in @($environment.PSObject.Properties)) {
      foreach ($identityName in $identityNames) {
        if ([string]::Equals([string]$property.Name, $identityName, [StringComparison]::OrdinalIgnoreCase)) {
          $identityProperties += $property
          break
        }
      }
    }
    if ($identityProperties.Count -ne 1) {
      $unrecognized.reason = 'each Sandbox item must have exactly one identity field (Id, SandboxId, or InstanceId)'
      return $unrecognized
    }

    $identityProperty = $identityProperties[0]
    if ($identityNames -cnotcontains [string]$identityProperty.Name -or $identityProperty.Value -isnot [string]) {
      $unrecognized.reason = 'Sandbox identity field name or value type is not canonical'
      return $unrecognized
    }

    $parsedId = [Guid]::Empty
    if (-not [Guid]::TryParseExact([string]$identityProperty.Value, 'D', [ref]$parsedId) -or $parsedId -eq [Guid]::Empty) {
      $unrecognized.reason = 'Sandbox identity field is not a non-empty D-format GUID'
      return $unrecognized
    }

    $normalizedId = $parsedId.ToString('D')
    if ($ids.Contains($normalizedId)) {
      $unrecognized.reason = 'Sandbox inventory contains a duplicate identity GUID'
      return $unrecognized
    }
    $ids.Add($normalizedId)
  }

  return [pscustomobject]@{ recognized = $true; sandbox_ids = [string[]]$ids.ToArray(); reason = $null }
}

function Invoke-InventoryParserSelfTest {
  $validId = 'd94db7e0-e5d0-4733-93e7-2bfc66ad1887'
  $otherId = 'e0f4a4b7-52b3-4f66-82b5-5b91d1e80c04'
  $cases = @(
    [pscustomobject]@{ name = 'observed empty inventory'; json = '{"WindowsSandboxEnvironments":[]}'; recognized = $true; ids = @() },
    [pscustomobject]@{ name = 'one GUID inventory'; json = '{"WindowsSandboxEnvironments":[{"Id":"' + $validId + '"}]}'; recognized = $true; ids = @($validId) },
    [pscustomobject]@{ name = 'unknown root empty array'; json = '{"Unexpected":[]}'; recognized = $false; ids = @() },
    [pscustomobject]@{ name = 'unknown root nested array'; json = '{"Metadata":{"WindowsSandboxEnvironments":[]}}'; recognized = $false; ids = @() },
    [pscustomobject]@{ name = 'missing identity field'; json = '{"WindowsSandboxEnvironments":[{}]}'; recognized = $false; ids = @() },
    [pscustomobject]@{ name = 'invalid GUID'; json = '{"WindowsSandboxEnvironments":[{"Id":"not-a-guid"}]}'; recognized = $false; ids = @() },
    [pscustomobject]@{ name = 'multiple identity fields'; json = '{"WindowsSandboxEnvironments":[{"Id":"' + $validId + '","SandboxId":"' + $otherId + '"}]}'; recognized = $false; ids = @() },
    [pscustomobject]@{ name = 'mixed valid and missing identity'; json = '{"WindowsSandboxEnvironments":[{"Id":"' + $validId + '"},{}]}'; recognized = $false; ids = @() },
    [pscustomobject]@{ name = 'duplicate GUID rows'; json = '{"WindowsSandboxEnvironments":[{"Id":"' + $validId + '"},{"InstanceId":"' + $validId + '"}]}'; recognized = $false; ids = @() }
  )

  foreach ($case in $cases) {
    $fixture = ConvertFrom-Json -InputObject $case.json -ErrorAction Stop
    $result = ConvertFrom-WsbSandboxInventory $fixture
    $actualIds = @($result.sandbox_ids)
    if ($result.recognized -ne $case.recognized -or $actualIds.Count -ne $case.ids.Count) {
      throw "Inventory parser self-test failed: $($case.name)"
    }
    for ($index = 0; $index -lt $case.ids.Count; $index++) {
      if ($actualIds[$index] -cne $case.ids[$index]) { throw "Inventory parser self-test failed: $($case.name)" }
    }
    Write-Output "PASS $($case.name)"
  }
  Write-Output "Inventory parser self-test passed: $($cases.Count) cases; no WSB command was invoked."
}

if ($InventoryParserSelfTest) {
  Invoke-InventoryParserSelfTest
  exit 0
}

function Get-PostStartOwnership {
  param([string]$RequestedId)
  $inventory = Invoke-Wsb -Operation 'list' -Arguments @('list','--raw')
  if ($inventory.outer_exit_code -ne 0 -or $inventory.timed_out) {
    return [ordered]@{ status = 'unknown; post-start inventory command failed or timed out'; outer_exit_code = $inventory.outer_exit_code; raw_output = $inventory.raw_output; raw_stderr = $inventory.raw_stderr; timed_out = $inventory.timed_out; timeout_seconds = $inventory.timeout_seconds; command_termination = $inventory.command_termination; launch_error = $inventory.launch_error; running_ids = 'unknown'; requested_id_present = $false }
  }
  try {
    $parsed = $inventory.raw_output | ConvertFrom-Json -ErrorAction Stop
    $inventoryParse = ConvertFrom-WsbSandboxInventory $parsed
    if (-not $inventoryParse.recognized) {
      return [ordered]@{ status = "unknown; post-start inventory shape unrecognized: $($inventoryParse.reason)"; outer_exit_code = $inventory.outer_exit_code; raw_output = $inventory.raw_output; raw_stderr = $inventory.raw_stderr; timed_out = $inventory.timed_out; timeout_seconds = $inventory.timeout_seconds; command_termination = $inventory.command_termination; launch_error = $inventory.launch_error; running_ids = 'unknown'; requested_id_present = $false }
    }
    $ids = @($inventoryParse.sandbox_ids)
    $present = $ids -contains $RequestedId
    return [ordered]@{ status = if ($present) { 'exact requested ID found after a preflight-proven-empty inventory' } else { 'exact requested ID absent; other listed IDs left untouched' }; outer_exit_code = $inventory.outer_exit_code; raw_output = $inventory.raw_output; raw_stderr = $inventory.raw_stderr; timed_out = $inventory.timed_out; timeout_seconds = $inventory.timeout_seconds; command_termination = $inventory.command_termination; launch_error = $inventory.launch_error; running_ids = @($ids); requested_id_present = [bool]$present }
  }
  catch {
    return [ordered]@{ status = "unknown; post-start inventory parse failed: $($_.Exception.Message)"; outer_exit_code = $inventory.outer_exit_code; raw_output = $inventory.raw_output; raw_stderr = $inventory.raw_stderr; timed_out = $inventory.timed_out; timeout_seconds = $inventory.timeout_seconds; command_termination = $inventory.command_termination; launch_error = $inventory.launch_error; running_ids = 'unknown'; requested_id_present = $false }
  }
}

function ConvertTo-WindowsCommandLineArgument {
  param([AllowEmptyString()][string]$Value)
  $builder = [Text.StringBuilder]::new()
  [void]$builder.Append('"')
  $backslashes = 0
  foreach ($character in $Value.ToCharArray()) {
    if ($character -eq '\') { $backslashes++; continue }
    if ($character -eq '"') {
      if ($backslashes -gt 0) { [void]$builder.Append(('\' * (2 * $backslashes))) }
      [void]$builder.Append('\"')
      $backslashes = 0
      continue
    }
    if ($backslashes -gt 0) { [void]$builder.Append(('\' * $backslashes)); $backslashes = 0 }
    [void]$builder.Append($character)
  }
  if ($backslashes -gt 0) { [void]$builder.Append(('\' * (2 * $backslashes))) }
  [void]$builder.Append('"')
  return $builder.ToString()
}

function Invoke-Wsb {
  param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('list','start','connect','exec','stop')]
    [string]$Operation,
    [Parameter(Mandatory = $true)]
    [string[]]$Arguments
  )
  $timeoutSeconds = switch ($Operation) {
    'list' { 20 }
    'start' { 90 }
    'connect' { 90 }
    'exec' { 135 }
    'stop' { 60 }
  }
  $process = $null
  $processStarted = $false
  $stdoutTask = $null
  $stderrTask = $null
  $timedOut = $false
  $outerCode = 'unknown'
  $rawOutput = 'unknown; stdout capture unavailable'
  $rawStderr = 'unknown; stderr capture unavailable'
  $termination = 'not_started'
  $launchError = $null
  try {
    if ([string]::IsNullOrWhiteSpace($WsbPath) -or -not [IO.Path]::IsPathRooted($WsbPath)) { throw 'WSB executable path is not an absolute path.' }
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $WsbPath
    $startInfo.Arguments = (@($Arguments | ForEach-Object { ConvertTo-WindowsCommandLineArgument ([string]$_) }) -join ' ')
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.StandardOutputEncoding = [Text.Encoding]::UTF8
    $startInfo.StandardErrorEncoding = [Text.Encoding]::UTF8
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    if (-not $process.Start()) { throw 'Process.Start returned false for WSB.' }
    $processStarted = $true
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit($timeoutSeconds * 1000)) {
      $timedOut = $true
      try {
        if ($process.HasExited) { $termination = 'process exited at timeout boundary' }
        else { $process.Kill(); $termination = 'WSB root process termination requested; descendants were not directly terminated' }
      }
      catch {
        $termination = "WSB root process termination failed: $($_.Exception.Message)"
        try {
          if (-not $process.HasExited) { $process.Kill(); $termination += '; second root-process termination request issued' }
        }
        catch { $termination += "; retry failed: $($_.Exception.Message)" }
      }
      if (-not $process.WaitForExit(5000)) { $termination += '; WSB process still alive after 5 second cleanup bound' }
      elseif ($termination -like 'WSB root process termination requested*') { $termination += '; root process exited within cleanup bound' }
    }
    else {
      $outerCode = [int]$process.ExitCode
      $termination = 'not_needed'
    }

    $streamsComplete = $false
    try { $streamsComplete = [Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]@($stdoutTask,$stderrTask),2000) }
    catch { $launchError = "Standard stream capture failed: $($_.Exception.Message)" }
    if ($streamsComplete -or $stdoutTask.IsCompleted) {
      try { $rawOutput = $stdoutTask.GetAwaiter().GetResult() }
      catch { $rawOutput = "unknown; stdout capture failed: $($_.Exception.Message)" }
    }
    else { $rawOutput = 'unknown; stdout stream did not close within the bounded capture wait' }
    if ($streamsComplete -or $stderrTask.IsCompleted) {
      try { $rawStderr = $stderrTask.GetAwaiter().GetResult() }
      catch { $rawStderr = "unknown; stderr capture failed: $($_.Exception.Message)" }
    }
    else { $rawStderr = 'unknown; stderr stream did not close within the bounded capture wait' }
  }
  catch {
    $launchError = $_.Exception.Message
    if ($process -and $processStarted) {
      try {
        if (-not $process.HasExited) { $process.Kill(); $termination = 'WSB root process termination requested after invocation error; descendants were not directly terminated' }
        else { $termination = 'root process had already exited after invocation error' }
      }
      catch { $termination = "unknown; root process cleanup after invocation error failed: $($_.Exception.Message)" }
      try { [void]$process.WaitForExit(5000) } catch { }
    }
  }
  finally {
    if ($process) { $process.Dispose() }
  }
  return [ordered]@{
    operation = $Operation
    timeout_seconds = $timeoutSeconds
    timed_out = [bool]$timedOut
    outer_exit_code = $outerCode
    raw_output = $rawOutput
    raw_stderr = $rawStderr
    command_termination = $termination
    launch_error = $launchError
  }
}

function Get-GuestExitCode {
  param([string]$RawOutput)
  try {
    $parsed = $RawOutput | ConvertFrom-Json -ErrorAction Stop
    if (-not (Test-JsonField $parsed 'ExitCode')) { return 'unknown' }
    $number = 0
    if (-not [int]::TryParse([string]$parsed.ExitCode, [ref]$number)) { return 'unknown' }
    return $number
  }
  catch { return 'unknown' }
}

function Get-SafeProcessExitOutcome {
  param($Failure)
  $outcome = [ordered]@{
    process_exit_code = 'unknown'
    process_exit_code_hex = 'unknown'
    process_exit_code_raw = 'unknown'
    timed_out = 'unknown'
  }
  if ($null -eq $Failure -or -not (Test-JsonField $Failure 'process_exit_code')) { return $outcome }
  $value = $Failure.PSObject.Properties['process_exit_code'].Value
  $exitCode = 0
  if ($value -isnot [bool] -and [int]::TryParse([string]$value, [Globalization.NumberStyles]::Integer,
      [Globalization.CultureInfo]::InvariantCulture, [ref]$exitCode)) {
    $outcome.process_exit_code = $exitCode
    $expectedHex = '0x' + [BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$exitCode), 0).ToString('X8', [Globalization.CultureInfo]::InvariantCulture)
    $outcome.process_exit_code_hex = $expectedHex
    $outcome.process_exit_code_raw = $expectedHex
  }
  elseif ($value -is [string] -and $value -ceq 'unknown') {
    $outcome.process_exit_code = 'unknown'
  }
  if (Test-JsonField $Failure 'timed_out') {
    $timeoutValue = $Failure.PSObject.Properties['timed_out'].Value
    if ($timeoutValue -is [bool]) { $outcome.timed_out = $timeoutValue }
    elseif ($timeoutValue -is [string] -and $timeoutValue -ceq 'unknown') { $outcome.timed_out = 'unknown' }
  }
  if (Test-JsonField $Failure 'process_failure_stage') {
    $processFailureStage = [string]$Failure.PSObject.Properties['process_failure_stage'].Value
    if ($processFailureStage -match '^[A-Za-z0-9_]{1,64}$') { $outcome.process_failure_stage = $processFailureStage }
  }
  return $outcome
}

function Update-BrowserObservation {
  if (-not (Test-Path -LiteralPath $manifest.browser.observation_file -PathType Leaf)) {
    $manifest.browser.status = 'unknown; observation file missing'
    return
  }
  try {
    $observation = Get-Content -LiteralPath $manifest.browser.observation_file -Raw | ConvertFrom-Json -ErrorAction Stop
    $expectedWtsObservationMode = if ($WtsDesktopAclDiagnosticOnly) { 'b2-wts-desktop-acl-diagnostic' } else { 'b2-wts-native-control' }
    if (($WtsNativeControlOnly -or $WtsDesktopAclDiagnosticOnly) -and ([string]$observation.mode -ne $expectedWtsObservationMode -or [string]$observation.run_id -ne [string]$manifest.run_id)) {
      $manifest.failure = [ordered]@{ stage = 'wts_observation_binding'; message = 'WTS observation mode/run ID did not match the current attempt.' }
      $manifest.guest_control.helper_exit_code = 'unknown'
      $manifest.browser.status = 'unknown; WTS observation binding mismatch'
      return
    }
    if ((Test-JsonField $observation 'probe')) {
      if (Test-JsonField $observation.probe 'status') { $manifest.probe.status = [string]$observation.probe.status }
      if (Test-JsonField $observation.probe 'process_exit_code' -and $null -ne $observation.probe.process_exit_code) { $manifest.probe.process_exit_code = $observation.probe.process_exit_code }
    }
    if ((Test-JsonField $observation 'helper_exit_code') -and $null -ne $observation.helper_exit_code) { $manifest.guest_control.helper_exit_code = $observation.helper_exit_code }
    elseif ((Test-JsonField $observation 'helper') -and (Test-JsonField $observation.helper 'exit_code') -and $null -ne $observation.helper.exit_code) { $manifest.guest_control.helper_exit_code = $observation.helper.exit_code }
    if ((Test-JsonField $observation 'page') -and (Test-JsonField $observation.page 'status')) { $manifest.page.status = [string]$observation.page.status }
    if ((Test-JsonField $observation 'native_diagnostic') -and $null -ne $observation.native_diagnostic) {
      $nativeDiagnostic = $observation.native_diagnostic
      $guestNativeHash = if (Test-JsonField $nativeDiagnostic 'native_executable_sha256') { [string]$nativeDiagnostic.native_executable_sha256 } else { '' }
      $hashMatchesHost = -not [string]::IsNullOrWhiteSpace($guestNativeHash) -and [string]::Equals($guestNativeHash, [string]$manifest.validation.native_diagnostic_sha256, [StringComparison]::OrdinalIgnoreCase)
      $nativeDiagnostic | Add-Member -NotePropertyName guest_executable_sha256 -NotePropertyValue $guestNativeHash -Force
      $nativeDiagnostic | Add-Member -NotePropertyName executable_sha256_matches_host -NotePropertyValue $hashMatchesHost -Force
      $manifest.native_diagnostic = $nativeDiagnostic
    }
    if ((Test-JsonField $observation 'desktop_access_check') -and $null -ne $observation.desktop_access_check) {
      if (Test-JsonField $observation.desktop_access_check 'status') { $manifest.desktop_access_check.status = [string]$observation.desktop_access_check.status }
      if (Test-JsonField $observation.desktop_access_check 'target_user_sid') { $manifest.desktop_access_check.target_user_sid = [string]$observation.desktop_access_check.target_user_sid }
      if (Test-JsonField $observation.desktop_access_check 'target_logon_sid') { $manifest.desktop_access_check.target_logon_sid = [string]$observation.desktop_access_check.target_logon_sid }
      if (Test-JsonField $observation.desktop_access_check 'target_session_id') { $manifest.desktop_access_check.target_session_id = $observation.desktop_access_check.target_session_id }
      if ((Test-JsonField $observation.desktop_access_check 'window_station_access_check') -and (Test-JsonField $observation.desktop_access_check.window_station_access_check 'access_granted')) { $manifest.desktop_access_check.window_station_access = $observation.desktop_access_check.window_station_access_check.access_granted }
      if ((Test-JsonField $observation.desktop_access_check 'desktop_access_check') -and (Test-JsonField $observation.desktop_access_check.desktop_access_check 'access_granted')) { $manifest.desktop_access_check.desktop_access = $observation.desktop_access_check.desktop_access_check.access_granted }
    if ((Test-JsonField $observation.desktop_access_check 'window_station_access_check') -and (Test-JsonField $observation.desktop_access_check.window_station_access_check 'api_succeeded')) { $manifest.desktop_access_check.window_station_api_succeeded = $observation.desktop_access_check.window_station_access_check.api_succeeded }
    if ((Test-JsonField $observation.desktop_access_check 'desktop_access_check') -and (Test-JsonField $observation.desktop_access_check.desktop_access_check 'api_succeeded')) { $manifest.desktop_access_check.desktop_api_succeeded = $observation.desktop_access_check.desktop_access_check.api_succeeded }
    if ((Test-JsonField $observation.desktop_access_check 'window_station_access_check') -and (Test-JsonField $observation.desktop_access_check.window_station_access_check 'desired_access')) { $manifest.desktop_access_check.window_station_desired_access = [string]$observation.desktop_access_check.window_station_access_check.desired_access }
    if ((Test-JsonField $observation.desktop_access_check 'desktop_access_check') -and (Test-JsonField $observation.desktop_access_check.desktop_access_check 'desired_access')) { $manifest.desktop_access_check.desktop_desired_access = [string]$observation.desktop_access_check.desktop_access_check.desired_access }
    if (Test-JsonField $observation.desktop_access_check 'same_user_sid_as_target') { $manifest.desktop_access_check.probe_user_sid_matches_target = $observation.desktop_access_check.same_user_sid_as_target }
    if (Test-JsonField $observation.desktop_access_check 'same_logon_sid_as_target') { $manifest.desktop_access_check.probe_logon_sid_matches_target = $observation.desktop_access_check.same_logon_sid_as_target }
    if ((Test-JsonField $observation.desktop_access_check 'base_named_objects_access_check') -and $null -ne $observation.desktop_access_check.base_named_objects_access_check) {
      $baseNamedObjects = $observation.desktop_access_check.base_named_objects_access_check
      if (Test-JsonField $baseNamedObjects 'status') { $manifest.desktop_access_check.base_named_objects_access_check.status = [string]$baseNamedObjects.status }
      if ((Test-JsonField $baseNamedObjects 'directory_create_object_access') -and $null -ne $baseNamedObjects.directory_create_object_access) {
        $baseNamedObjectsAccess = $baseNamedObjects.directory_create_object_access
        if (Test-JsonField $baseNamedObjectsAccess 'api_succeeded') { $manifest.desktop_access_check.base_named_objects_access_check.api_succeeded = $baseNamedObjectsAccess.api_succeeded }
        if (Test-JsonField $baseNamedObjectsAccess 'access_granted') { $manifest.desktop_access_check.base_named_objects_access_check.access_granted = $baseNamedObjectsAccess.access_granted }
        if (Test-JsonField $baseNamedObjectsAccess 'desired_access') { $manifest.desktop_access_check.base_named_objects_access_check.desired_access = [string]$baseNamedObjectsAccess.desired_access }
        if (Test-JsonField $baseNamedObjectsAccess 'granted_access') { $manifest.desktop_access_check.base_named_objects_access_check.granted_access = [string]$baseNamedObjectsAccess.granted_access }
        if (Test-JsonField $baseNamedObjectsAccess 'win32_error') { $manifest.desktop_access_check.base_named_objects_access_check.win32_error = $baseNamedObjectsAccess.win32_error }
      }
      if (Test-JsonField $baseNamedObjects 'acl_mutated') { $manifest.desktop_access_check.base_named_objects_access_check.acl_mutated = $baseNamedObjects.acl_mutated }
      if (Test-JsonField $baseNamedObjects 'target_process_started') { $manifest.desktop_access_check.base_named_objects_access_check.target_process_started = $baseNamedObjects.target_process_started }
    }
      if (Test-JsonField $observation.desktop_access_check 'reason') { $manifest.desktop_access_check.reason = [string]$observation.desktop_access_check.reason }
    }
    if (($WtsNativeControlOnly -or $WtsDesktopAclDiagnosticOnly) -and (Test-JsonField $observation 'identity')) { $manifest.wts_medium_identity = $observation.identity }
    if ((Test-JsonField $observation 'process_tree')) {
      if (Test-JsonField $observation.process_tree 'cleanup_status') { $manifest.process_tree.cleanup_status = [string]$observation.process_tree.cleanup_status }
      if (Test-JsonField $observation.process_tree 'active_processes_after') { $manifest.process_tree.active_processes_after = $observation.process_tree.active_processes_after }
    }
    $guestFailureCanRefineExit = $null -eq $manifest.failure -or [string]$manifest.failure.stage -eq 'guest_process_exit'
    if ((Test-JsonField $observation 'status') -and ([string]$observation.status -eq 'fail') -and (Test-JsonField $observation 'failure') -and ($null -ne $observation.failure) -and $guestFailureCanRefineExit) {
      $failureStage = if (Test-JsonField $observation.failure 'stage') { [string]$observation.failure.stage } else { 'unknown' }
      $processOutcome = Get-SafeProcessExitOutcome $observation.failure
      $manifest.failure = [ordered]@{
        stage = "guest_$failureStage"
        api = if (Test-JsonField $observation.failure 'api') { $observation.failure.api } else { $null }
        win32_error = if (Test-JsonField $observation.failure 'win32_error') { $observation.failure.win32_error } else { $null }
        message = if (Test-JsonField $observation.failure 'message') { [string]$observation.failure.message } else { 'Guest helper reported failure.' }
        helper_exit_code = $manifest.guest_control.helper_exit_code
        process_exit_code = $processOutcome.process_exit_code
        process_exit_code_hex = $processOutcome.process_exit_code_hex
        process_exit_code_raw = $processOutcome.process_exit_code_raw
        timed_out = $processOutcome.timed_out
      }
      if ($processOutcome.Contains('process_failure_stage')) { $manifest.failure.process_failure_stage = $processOutcome.process_failure_stage }
      if ($manifest.probe.status -eq 'not_run') { $manifest.phase = 'fixture_failed_before_probe' }
    }
    if ((Test-JsonField $observation 'browser') -and (Test-JsonField $observation.browser 'status') -and ([string]$observation.browser.status -like 'not_run*')) {
      $manifest.browser.process_exit_code = 'not_run'
      $manifest.browser.timed_out = 'not_run'
      $manifest.browser.status = [string]$observation.browser.status
      return
    }
    if ((Test-JsonField $observation 'browser') -and (Test-JsonField $observation.browser 'timed_out') -and $null -ne $observation.browser.timed_out) { $manifest.browser.timed_out = $observation.browser.timed_out }
    if ((Test-JsonField $observation 'browser') -and (Test-JsonField $observation.browser 'process_exit_code') -and $null -ne $observation.browser.process_exit_code) {
      $code = 0
      if ([int]::TryParse([string]$observation.browser.process_exit_code, [ref]$code)) {
        $manifest.browser.process_exit_code = $code
        $manifest.browser.status = 'observed'
        return
      }
    }
    $manifest.browser.status = 'unknown; browser process exit code absent or invalid'
  }
  catch { $manifest.browser.status = "unknown; observation parse failed: $($_.Exception.Message)" }
}

function Update-LoaderSnapsObservation {
  $observationPath = [string]$manifest.loader_diagnostic.observation_file
  if (-not (Test-Path -LiteralPath $observationPath -PathType Leaf)) {
    $manifest.loader_diagnostic.status = 'unknown; unique loader diagnostic report is missing'
    return
  }
  try {
    $observation = Get-Content -LiteralPath $observationPath -Raw | ConvertFrom-Json -ErrorAction Stop
    if ([string]$observation.schema -ne 'b2-wts-loader-snaps-observation/v1' -or [string]$observation.mode -ne 'b2-wts-loader-snaps' -or [string]$observation.run_id -ne [string]$manifest.run_id) {
      $manifest.failure = [ordered]@{ stage = 'loader_observation_binding'; message = 'Loader Snaps observation schema, mode, or run_id did not match the current attempt.' }
      $manifest.loader_diagnostic.status = 'unknown; observation binding mismatch'
      return
    }
    $manifest.loader_diagnostic.helper_status = if (Test-JsonField $observation 'status') { [string]$observation.status } else { 'unknown' }
    $manifest.loader_diagnostic.status = [string]$manifest.loader_diagnostic.helper_status
    $reportedHelperExitCode = 'unknown'
    $observedHelperExitCode = 'unknown'
    $parsedHelperExitCode = 0
    if ((Test-JsonField $observation 'helper_exit_code') -and $null -ne $observation.helper_exit_code -and [int]::TryParse([string]$observation.helper_exit_code, [ref]$parsedHelperExitCode)) {
      $reportedHelperExitCode = $parsedHelperExitCode
    }
    $parsedObservedHelperExitCode = 0
    if ((Test-JsonField $observation 'helper') -and (Test-JsonField $observation.helper 'exit_code') -and $null -ne $observation.helper.exit_code -and [int]::TryParse([string]$observation.helper.exit_code, [ref]$parsedObservedHelperExitCode)) {
      $observedHelperExitCode = $parsedObservedHelperExitCode
      $manifest.guest_control.helper_exit_code = $observedHelperExitCode
    }
    $manifest.loader_diagnostic.helper_reported_exit_code = $reportedHelperExitCode
    $manifest.loader_diagnostic.helper_exit_code_consistency = if ($reportedHelperExitCode -eq 'unknown') { 'reported_code_missing_or_invalid' }
      elseif ($observedHelperExitCode -eq 'unknown') { 'observed_code_unknown_or_invalid' }
      elseif ([int]$reportedHelperExitCode -ne [int]$observedHelperExitCode) { 'mismatch' }
      else { 'match' }
    $manifest.loader_diagnostic.helper_exit_code_matches_report = $manifest.loader_diagnostic.helper_exit_code_consistency -eq 'match'
    if ($manifest.loader_diagnostic.helper_exit_code_consistency -ne 'match') {
      $manifest.loader_diagnostic.exit_code_contract_stage = 'loader_helper_exit_code_contract'
      if (-not $manifest.failure) {
        $manifest.failure = [ordered]@{ stage = 'loader_helper_exit_code_contract'; message = 'Reported and observed helper exit codes were missing, invalid, or inconsistent.' }
      }
    }
    if ((Test-JsonField $observation 'loader_diagnostic') -and (Test-JsonField $observation.loader_diagnostic 'status')) { $manifest.loader_diagnostic.status = [string]$observation.loader_diagnostic.status }
    if ($manifest.loader_diagnostic.helper_exit_code_consistency -ne 'match') { $manifest.loader_diagnostic.status = 'fail' }
    if (Test-JsonField $observation 'identity') { $manifest.wts_medium_identity = $observation.identity }
    if (Test-JsonField $observation 'process_tree') {
      if (Test-JsonField $observation.process_tree 'cleanup_status') { $manifest.process_tree.cleanup_status = [string]$observation.process_tree.cleanup_status }
      if (Test-JsonField $observation.process_tree 'active_processes_after') { $manifest.process_tree.active_processes_after = $observation.process_tree.active_processes_after }
      $manifest.loader_diagnostic.process_tree_status = [string]$manifest.process_tree.cleanup_status
    }
    if ((Test-JsonField $observation 'ifeo_restore') -and (Test-JsonField $observation.ifeo_restore 'status')) {
      $manifest.loader_diagnostic.ifeo_restore_status = [string]$observation.ifeo_restore.status
    }
    if ([string]$observation.status -notin @('diagnostic_complete','fail')) {
      $manifest.failure = [ordered]@{ stage = 'loader_observation_status'; message = 'Loader Snaps helper returned a status outside diagnostic_complete/fail.' }
    }
    if ([string]$observation.status -eq 'fail') {
      $failureStage = if ((Test-JsonField $observation 'failure') -and (Test-JsonField $observation.failure 'stage')) { [string]$observation.failure.stage } else { 'unknown' }
      $manifest.failure = [ordered]@{ stage = "loader_$failureStage"; message = 'WTS Loader Snaps diagnostic did not complete.' }
    }
    $manifest.b2_acceptance = 'not_evaluated_diagnostic_only'
    $manifest.loader_diagnostic.b2_pass = $false
  }
  catch {
    $manifest.loader_diagnostic.status = 'unknown; observation parse failed'
    $manifest.failure = [ordered]@{ stage = 'loader_observation_parse'; message = 'Loader Snaps report could not be parsed.'; error_type = $_.Exception.GetType().FullName }
  }
}

function Read-WtsProcessSingletonRunnerStatus {
  param([Parameter(Mandatory = $true)][string]$StatusPath, [Parameter(Mandatory = $true)][string]$ExpectedRunId)
  $item = Get-Item -LiteralPath $StatusPath -ErrorAction Stop
  if ($item.PSIsContainer -or $item.Length -le 0 -or $item.Length -gt 4096) { throw 'Runner-status sidecar size or type is invalid.' }
  $sidecar = Get-Content -LiteralPath $StatusPath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
  if ($sidecar -isnot [System.Management.Automation.PSCustomObject]) { throw 'Runner-status sidecar must be a JSON object.' }
  $expectedFields = @('schema','mode','run_id','wrapper_stage','wrapper_status','helper_process_exit_code','helper_timed_out')
  $actualFields = @($sidecar.PSObject.Properties | ForEach-Object { $_.Name })
  if ($actualFields.Count -ne $expectedFields.Count) { throw 'Runner-status sidecar field set is invalid.' }
  foreach ($field in $expectedFields) {
    if (-not $sidecar.PSObject.Properties[$field]) { throw 'Runner-status sidecar is missing a required field.' }
  }
  foreach ($field in @('schema','mode','run_id','wrapper_stage','wrapper_status')) {
    if ($sidecar.PSObject.Properties[$field].Value -isnot [string]) { throw 'Runner-status sidecar string field type is invalid.' }
  }
  if ([string]$sidecar.schema -cne 'b2-wts-process-singleton-runner-status/v1' -or
      [string]$sidecar.mode -cne 'b2-wts-process-singleton-diagnostic' -or
      [string]$sidecar.run_id -cne $ExpectedRunId -or
      [string]$sidecar.wrapper_status -cne 'failed') { throw 'Runner-status sidecar schema, mode, run ID, or status is invalid.' }
  $allowedStages = @('runner_preflight','helper_launch','helper_wait','helper_exit_observation',
    'helper_report_presence','helper_report_parse','helper_report_contract','helper_report_evidence',
    'runner_observation_write','unknown')
  if ([string]$sidecar.wrapper_stage -notin $allowedStages) { throw 'Runner-status sidecar wrapper stage is invalid.' }
  if ($sidecar.helper_timed_out -isnot [bool]) { throw 'Runner-status sidecar timeout field type is invalid.' }
  $observedExitCode = $sidecar.helper_process_exit_code
  if ($observedExitCode -is [bool]) { throw 'Runner-status sidecar helper exit field type is invalid.' }
  if ($observedExitCode -is [string]) {
    if ([string]$observedExitCode -cne 'unknown') { throw 'Runner-status sidecar helper exit field value is invalid.' }
  }
  elseif ($observedExitCode -is [int] -or $observedExitCode -is [long]) {
    if ([long]$observedExitCode -lt -2147483648 -or [long]$observedExitCode -gt 2147483647) { throw 'Runner-status sidecar helper exit code is out of range.' }
    $observedExitCode = [int]$observedExitCode
  }
  else { throw 'Runner-status sidecar helper exit field type is invalid.' }
  return [ordered]@{
    wrapper_stage = [string]$sidecar.wrapper_stage
    wrapper_status = [string]$sidecar.wrapper_status
    helper_process_exit_code = $observedExitCode
    helper_timed_out = [bool]$sidecar.helper_timed_out
  }
}

function Update-ProcessSingletonObservation {
  $observationPath = [string]$manifest.process_singleton_diagnostic.observation_file
  $manifest.b2_acceptance = 'not_evaluated_diagnostic_only'
  $manifest.browser.process_exit_code = 'not_run'
  $manifest.browser.timed_out = 'not_run'
  $manifest.browser.status = 'not_run; WTS ProcessSingleton diagnostic-only mode'
  $manifest.page.status = 'not_run; WTS ProcessSingleton diagnostic-only mode'
  $manifest.probe.status = 'not_run; this diagnostic is separate from the B2 low-token browser probe'
  $manifest.probe.process_exit_code = 'not_run'
  $runnerStatusPath = [string]$manifest.process_singleton_diagnostic.runner_status_file
  if ([string]::IsNullOrWhiteSpace($runnerStatusPath) -or $runnerStatusPath -eq 'not_run') {
    $manifest.process_singleton_diagnostic.status = 'failed; runner-status path missing'
    $manifest.guest_control.helper_exit_code = 'unknown'
    $manifest.failure = [ordered]@{ stage = 'process_singleton_runner_status_path'; message = 'WTS ProcessSingleton runner-status sidecar path was not established during preflight.' }
    return
  }
  if (Test-Path -LiteralPath $runnerStatusPath) {
    try {
      $runnerStatus = Read-WtsProcessSingletonRunnerStatus -StatusPath $runnerStatusPath -ExpectedRunId ([string]$manifest.run_id)
      $manifest.process_singleton_diagnostic.runner_status = $runnerStatus.wrapper_status
      $manifest.process_singleton_diagnostic.runner_wrapper_stage = $runnerStatus.wrapper_stage
      $manifest.process_singleton_diagnostic.runner_helper_process_exit_code = $runnerStatus.helper_process_exit_code
      $manifest.process_singleton_diagnostic.runner_helper_timed_out = $runnerStatus.helper_timed_out
      $manifest.process_singleton_diagnostic.status = 'failed; runner status sidecar reported failure'
      $manifest.guest_control.helper_exit_code = $runnerStatus.helper_process_exit_code
      $manifest.failure = [ordered]@{
        stage = "process_singleton_runner_$($runnerStatus.wrapper_stage)"
        message = 'WTS ProcessSingleton runner failure was recorded in its separate run-bound status sidecar; helper-authored observation was not used.'
      }
      return
    }
    catch {
      $manifest.process_singleton_diagnostic.runner_status = 'invalid'
      $manifest.process_singleton_diagnostic.runner_wrapper_stage = 'unknown'
      $manifest.process_singleton_diagnostic.runner_helper_process_exit_code = 'unknown'
      $manifest.process_singleton_diagnostic.runner_helper_timed_out = 'unknown'
      $manifest.process_singleton_diagnostic.status = 'failed; runner status sidecar invalid'
      $manifest.guest_control.helper_exit_code = 'unknown'
      $manifest.failure = [ordered]@{ stage = 'process_singleton_runner_status_invalid'; message = 'WTS ProcessSingleton runner-status sidecar failed validation.' }
      return
    }
  }
  if (-not (Test-Path -LiteralPath $observationPath -PathType Leaf)) {
    $manifest.process_singleton_diagnostic.status = 'failed; observation report missing'
    $manifest.failure = [ordered]@{ stage = 'process_singleton_observation_missing'; message = 'WTS ProcessSingleton diagnostic observation report is missing.' }
    return
  }
  try {
    $observation = Get-Content -LiteralPath $observationPath -Raw | ConvertFrom-Json -ErrorAction Stop
    if ([string]$observation.schema -cne 'b2-wts-process-singleton-observation/v1' -or
        [string]$observation.mode -cne 'b2-wts-process-singleton-diagnostic' -or
        [string]$observation.run_id -cne [string]$manifest.run_id) {
      $manifest.process_singleton_diagnostic.status = 'failed; observation binding mismatch'
      $manifest.failure = [ordered]@{ stage = 'process_singleton_observation_binding'; message = 'WTS ProcessSingleton schema, mode, or run_id did not match the current attempt.' }
      return
    }
    $helperStatus = [string]$observation.status
    if ($helperStatus -notin @('diagnostic_complete','fail')) {
      $manifest.process_singleton_diagnostic.status = 'failed; invalid helper status'
      $manifest.failure = [ordered]@{ stage = 'process_singleton_observation_status'; message = 'WTS ProcessSingleton helper status was outside the allowed contract.' }
      return
    }
    $reportedHelperExitCode = 0
    $observedHelperExitCode = 0
    $helperCodesValid = [int]::TryParse([string]$observation.helper_exit_code, [ref]$reportedHelperExitCode) -and
      (Test-JsonField $observation 'helper') -and
      (Test-JsonField $observation.helper 'exit_code') -and
      [int]::TryParse([string]$observation.helper.exit_code, [ref]$observedHelperExitCode)
    $helperCodesMatch = $helperCodesValid -and $reportedHelperExitCode -eq $observedHelperExitCode
    $manifest.process_singleton_diagnostic.helper_status = $helperStatus
    $manifest.process_singleton_diagnostic.helper_exit_code = if ($helperCodesValid) { $reportedHelperExitCode } else { 'unknown' }
    $manifest.process_singleton_diagnostic.helper_exit_code_consistency = if (-not $helperCodesValid) { 'reported_or_observed_code_missing_or_invalid' } elseif ($helperCodesMatch) { 'match' } else { 'mismatch' }
    if ($helperCodesValid) { $manifest.guest_control.helper_exit_code = $observedHelperExitCode }

    $probe = if (Test-JsonField $observation 'probe') { $observation.probe } else { $null }
    if ($null -eq $probe -or $probe -isnot [System.Management.Automation.PSCustomObject]) {
      $manifest.process_singleton_diagnostic.status = 'failed; probe summary missing'
      $manifest.failure = [ordered]@{ stage = 'process_singleton_probe_summary'; message = 'WTS ProcessSingleton probe summary was missing or invalid.' }
      return
    }
    $probeStatus = [string]$probe.status
    $probeReportPath = [string]$probe.report_path
    $probeBytes = 0L
    $probeBytesValid = [long]::TryParse([string]$probe.report_bytes, [ref]$probeBytes) -and $probeBytes -ge 0 -and $probeBytes -le 1048576
    $probeHash = [string]$probe.report_sha256
    $probeTimedOut = $probe.timed_out
    $probeExitCode = 'unknown'
    $parsedProbeExitCode = 0
    if ([int]::TryParse([string]$probe.process_exit_code, [ref]$parsedProbeExitCode)) { $probeExitCode = $parsedProbeExitCode }
    elseif ([string]$probe.process_exit_code -ne 'unknown') { $probeExitCode = 'invalid' }
    $manifest.process_singleton_diagnostic.probe_status = if ($probeStatus -in @('pass','fail','unknown')) { $probeStatus } else { 'unknown' }
    $manifest.process_singleton_diagnostic.probe_process_exit_code = $probeExitCode
    $manifest.process_singleton_diagnostic.probe_timed_out = if ($probeTimedOut -is [bool]) { $probeTimedOut } else { 'unknown' }
    $manifest.process_singleton_diagnostic.probe_report_path = if ($probeReportPath -ceq 'C:\b2\evidence\process-singleton-probe.json') { 'C:\b2\evidence\process-singleton-probe.json' } else { 'invalid' }
    $manifest.process_singleton_diagnostic.probe_report_bytes = if ($probeBytesValid) { $probeBytes } else { 'unknown' }
    $manifest.process_singleton_diagnostic.probe_report_sha256 = if ($probeHash -match '^[0-9a-fA-F]{64}$') { $probeHash.ToLowerInvariant() } else { 'unknown' }

    $probeEvidencePathValid = $probeReportPath -ceq 'C:\b2\evidence\process-singleton-probe.json' -and
      $probeStatus -in @('pass','fail','unknown') -and $probeBytesValid -and $probeTimedOut -is [bool] -and $probeExitCode -ne 'invalid'
    $actualProbePath = Join-Path $EvidenceDirectory 'process-singleton-probe.json'
    $probeEvidenceMatches = $false
    if ($probeEvidencePathValid -and $probeBytes -gt 0 -and $probeHash -match '^[0-9a-fA-F]{64}$' -and (Test-Path -LiteralPath $actualProbePath -PathType Leaf)) {
      $actualProbeItem = Get-Item -LiteralPath $actualProbePath -ErrorAction Stop
      $actualProbeHash = (Get-FileHash -LiteralPath $actualProbePath -Algorithm SHA256 -ErrorAction Stop).Hash
      $probeEvidenceMatches = ([long]$actualProbeItem.Length -eq $probeBytes) -and [string]::Equals($actualProbeHash, $probeHash, [StringComparison]::OrdinalIgnoreCase)
    }
    elseif ($probeEvidencePathValid -and $probeBytes -eq 0 -and $probeHash -eq 'unknown' -and $probeStatus -eq 'unknown' -and -not (Test-Path -LiteralPath $actualProbePath)) {
      $probeEvidenceMatches = $true
    }

    $safeIdentity = $null
    $identityGate = $false
    if ((Test-JsonField $observation 'identity') -and $null -ne $observation.identity) {
      $identity = $observation.identity
      $finalToken = if (Test-JsonField $identity 'final_token') { $identity.final_token } else { $null }
      $safeFinalToken = if ($finalToken) {
        [ordered]@{
          status = if ((Test-JsonField $finalToken 'status') -and [string]$finalToken.status -in @('pass','fail','unknown')) { [string]$finalToken.status } else { 'unknown' }
          readback_gate_pass = if ((Test-JsonField $finalToken 'readback_gate_pass') -and $finalToken.readback_gate_pass -is [bool]) { $finalToken.readback_gate_pass } else { $false }
          token_elevation = if ((Test-JsonField $finalToken 'token_elevation') -and $finalToken.token_elevation -is [bool]) { $finalToken.token_elevation } else { $null }
          integrity_level = if ((Test-JsonField $finalToken 'integrity_level') -and [string]$finalToken.integrity_level -in @('low','medium','high','system','unknown')) { [string]$finalToken.integrity_level } else { 'unknown' }
          checked_builtin_privileged_alias_enabled_groups_absent = if ((Test-JsonField $finalToken 'checked_builtin_privileged_alias_enabled_groups_absent') -and $finalToken.checked_builtin_privileged_alias_enabled_groups_absent -is [bool]) { $finalToken.checked_builtin_privileged_alias_enabled_groups_absent } else { $false }
        }
      } else { $null }
      $safeTargetSessionId = 'unknown'
      $parsedTargetSessionId = 0
      if ((Test-JsonField $identity 'target_session_id') -and [int]::TryParse([string]$identity.target_session_id, [ref]$parsedTargetSessionId) -and $parsedTargetSessionId -ge 0) { $safeTargetSessionId = $parsedTargetSessionId }
      $safeIdentity = [ordered]@{
        target_session_is_interactive = if ((Test-JsonField $identity 'target_session_is_interactive') -and $identity.target_session_is_interactive -is [bool]) { $identity.target_session_is_interactive } else { $false }
        target_session_id = $safeTargetSessionId
        source_account_is_local = if ((Test-JsonField $identity 'source_account_is_local') -and $identity.source_account_is_local -is [bool]) { $identity.source_account_is_local } else { $false }
        final_token = $safeFinalToken
      }
      $identityGate = $safeIdentity.target_session_is_interactive -eq $true -and
        $safeIdentity.source_account_is_local -eq $true -and
        $safeFinalToken -and
        $safeFinalToken.status -eq 'pass' -and
        $safeFinalToken.readback_gate_pass -eq $true -and
        $safeFinalToken.token_elevation -eq $false -and
        $safeFinalToken.integrity_level -eq 'medium' -and
        $safeFinalToken.checked_builtin_privileged_alias_enabled_groups_absent -eq $true
    }

    $processTree = if (Test-JsonField $observation 'process_tree') { $observation.process_tree } else { $null }
    $treeCleanup = if ($processTree -and (Test-JsonField $processTree 'cleanup_status')) { [string]$processTree.cleanup_status } else { 'unknown' }
    $activeProcesses = 'unknown'
    $activeCount = 0
    if ($processTree -and (Test-JsonField $processTree 'active_processes_after') -and [int]::TryParse([string]$processTree.active_processes_after, [ref]$activeCount) -and $activeCount -ge 0) { $activeProcesses = $activeCount }
    $manifest.process_singleton_diagnostic.process_tree_cleanup_status = if ($treeCleanup -match '^(?i)complete(?:\b|$)') { 'complete' } elseif ($treeCleanup -match '^(?i)fail(?:ed)?(?:\b|$)') { 'failed' } else { 'unknown' }
    $manifest.process_singleton_diagnostic.active_processes_after = $activeProcesses
    $manifest.process_tree.cleanup_status = $manifest.process_singleton_diagnostic.process_tree_cleanup_status
    $manifest.process_tree.active_processes_after = $activeProcesses
    if ($safeIdentity) { $manifest.process_singleton_diagnostic.identity = $safeIdentity }

    $diagnosticComplete = $helperStatus -eq 'diagnostic_complete' -and
      $helperCodesMatch -and $reportedHelperExitCode -eq 0 -and
      $probeEvidencePathValid -and $probeEvidenceMatches -and
      $manifest.process_singleton_diagnostic.probe_status -in @('pass','fail','unknown') -and
      $manifest.process_singleton_diagnostic.process_tree_cleanup_status -eq 'complete' -and $activeProcesses -eq 0 -and $identityGate
    $manifest.process_singleton_diagnostic.status = if ($diagnosticComplete) { 'diagnostic_complete' } else { 'failed; diagnostic contract incomplete' }
    $manifest.process_singleton_diagnostic.runner_status = 'not_reported; valid report path'
    $manifest.process_singleton_diagnostic.runner_wrapper_stage = 'not_reported'
    $manifest.process_singleton_diagnostic.runner_helper_process_exit_code = $observedHelperExitCode
    $manifest.process_singleton_diagnostic.runner_helper_timed_out = $false
    if ($helperStatus -eq 'fail' -or -not $diagnosticComplete) {
      $failureStage = 'process_singleton_diagnostic_incomplete'
      if ((Test-JsonField $observation 'failure') -and (Test-JsonField $observation.failure 'stage') -and [string]$observation.failure.stage -match '^[A-Za-z0-9_.-]{1,96}$' -and [string]$observation.failure.stage -notmatch '(?i)\bS-\d-(?:\d+-){1,}\d+\b') {
        $failureStage = 'process_singleton_' + [string]$observation.failure.stage
      }
      $manifest.failure = [ordered]@{ stage = $failureStage; message = 'WTS ProcessSingleton diagnostic did not satisfy the separate completion, identity, evidence, and Job-drain gates.' }
    }
    if ($manifest.process_singleton_diagnostic.probe_status -eq 'pass') { $manifest.process_singleton_diagnostic.probe_result = 'probe_pass' }
    elseif ($manifest.process_singleton_diagnostic.probe_status -eq 'fail') { $manifest.process_singleton_diagnostic.probe_result = 'probe_fail' }
    else { $manifest.process_singleton_diagnostic.probe_result = 'probe_unknown' }
  }
  catch {
    $manifest.process_singleton_diagnostic.status = 'failed; observation parse or evidence check failed'
    $manifest.failure = [ordered]@{ stage = 'process_singleton_observation_parse'; message = 'WTS ProcessSingleton report failed safe parsing or evidence verification.'; error_type = $_.Exception.GetType().Name }
  }
}

$ownedSandboxStarted = $false
$validationFailed = $false
$loaderCdbCanonical = $null
$loaderTargetCanonical = $null
try {
  $wtsModeCount = [int][bool]$WtsNativeControlOnly + [int][bool]$WtsDesktopAclDiagnosticOnly + [int][bool]$WtsLoaderSnapsOnly + [int][bool]$WtsProcessSingletonDiagnosticOnly
  if ($wtsModeCount -gt 1) { throw 'WTS diagnostic-only modes are mutually exclusive.' }
  if (($WtsLoaderSnapsOnly -or $WtsProcessSingletonDiagnosticOnly) -and (-not $ConnectBeforeExec)) { throw 'WTS diagnostic mode requires ConnectBeforeExec so the WTS token is checked in Session 1.' }
  $attemptRootCanonical = Get-CanonicalPath $AttemptRoot Directory
  $configCanonical = Get-CanonicalPath $ConfigPath File
  $inputCanonical = Get-CanonicalPath $InputPath File
  $runnerCanonical = Get-CanonicalPath $GuestRunnerPath File
  $pageCanonical = Get-CanonicalPath $TestPagePath File
  $evidenceCanonical = Get-CanonicalPath $EvidenceDirectory Directory
  $manifest.attempt_root = $attemptRootCanonical
  $manifest.validation.config_path = $configCanonical
  $manifest.validation.input_path = $inputCanonical
  $manifest.guest_control.evidence_file = Join-Path $evidenceCanonical 'b2-observation.json'
  $manifest.browser.observation_file = Join-Path $evidenceCanonical 'b2-observation.json'
  $manifest.desktop_acl_probe.evidence_file = Join-Path $evidenceCanonical 'interactive-desktop-acl.json'

  $input = Get-Content -LiteralPath $inputCanonical -Raw | ConvertFrom-Json -ErrorAction Stop
  Assert-JsonFields $input @('schema','run_id','sandbox_id','browser_directory','executable','guest_browser','test_page','guest_test_page','guest_runner','probe_script','guest_probe_script','desktop_acl_probe_script','guest_desktop_acl_probe_script','helper_executable','guest_helper_executable','evidence_directory','guest_evidence_directory','networking','networking_allowed','mapped_browser_read_only','mapped_runner_read_only','mapped_evidence_writable','expected_browser_sha256','expected_browser_file_version','expected_browser_product_version','expected_browser_length')
  foreach ($field in @('schema','run_id','sandbox_id','browser_directory','executable','guest_browser','test_page','guest_test_page','guest_runner','probe_script','guest_probe_script','desktop_acl_probe_script','guest_desktop_acl_probe_script','helper_executable','guest_helper_executable','evidence_directory','guest_evidence_directory','networking','expected_browser_sha256','expected_browser_file_version','expected_browser_product_version')) {
    if ($input.PSObject.Properties[$field].Value -isnot [string]) { throw "Input JSON field '$field' must be a string." }
  }
  foreach ($field in @('networking_allowed','mapped_browser_read_only','mapped_runner_read_only','mapped_evidence_writable')) {
    if ($input.PSObject.Properties[$field].Value -isnot [bool]) { throw "Input JSON field '$field' must be a JSON boolean." }
  }
  if ($input.expected_browser_length -is [bool] -or $input.expected_browser_length -is [string] -or $input.expected_browser_length -is [double] -or $input.expected_browser_length -is [decimal]) { throw 'Input JSON field expected_browser_length must be an integer number.' }
  if ($input.expected_browser_length -le 0) { throw 'Input JSON field expected_browser_length must be positive.' }
  if ($input.schema -ne 'b2-locked-chromium-input/v3') { throw "Unsupported input schema '$($input.schema)'" }
  $runId = ConvertTo-ValidatedGuid ([string]$input.run_id) 'run_id'
  $sandboxId = ConvertTo-ValidatedGuid ([string]$input.sandbox_id) 'sandbox_id'
  if ($runId -ne $sandboxId) { throw 'Input run_id and sandbox_id must be the same GUID.' }
  $manifest.run_id = $runId
  $manifest.task_owned_sandbox_id = $sandboxId
  if ($WtsLoaderSnapsOnly) {
    $manifest.loader_diagnostic.observation_file = Join-Path $evidenceCanonical "loader-snaps-$runId.json"
    $manifest.guest_control.evidence_file = [string]$manifest.loader_diagnostic.observation_file
  }
  if ([string]$input.networking -ne 'Disabled' -or $input.networking_allowed -ne $false) { throw 'Input JSON must declare networking Disabled and networking_allowed false.' }
  if ($input.mapped_browser_read_only -ne $true -or $input.mapped_runner_read_only -ne $true -or $input.mapped_evidence_writable -ne $true) { throw 'Input JSON does not declare the required read-only/read-write mapping contract.' }
  if (-not $ConnectBeforeExec) {
    if ($WtsSessionDiagnosticOnly) { throw 'WTS diagnostic-only control requires an explicit WSB connect before verifying the active Session 1 token.' }
    throw 'B2 requires a connected ExistingLogin session before the read-only desktop diagnostic.'
  }

  $browserDirectory = Get-CanonicalPath ([string]$input.browser_directory) Directory
  $browserExecutable = Get-CanonicalPath ([string]$input.executable) File
  $inputPage = Get-CanonicalPath ([string]$input.test_page) File
  $inputRunner = Get-CanonicalPath ([string]$input.guest_runner) File
  $probePath = Get-CanonicalPath ([string]$input.probe_script) File
  $desktopAclProbePath = Get-CanonicalPath ([string]$input.desktop_acl_probe_script) File
  $helperPath = Get-CanonicalPath ([string]$input.helper_executable) File
  $helperAssemblyPath = Get-CanonicalPath (Join-Path (Split-Path -Parent $helperPath) 'LeaseProcessJobRunner.dll') File
  $nativeDiagnosticPath = $null
  if (-not $WtsLoaderSnapsOnly -and -not $WtsProcessSingletonDiagnosticOnly) { $nativeDiagnosticPath = Get-CanonicalPath (Join-Path (Split-Path -Parent $runnerCanonical) 'native-desktop-probe.exe') File }
  if ($WtsLoaderSnapsOnly) {
    if ([string]::IsNullOrWhiteSpace($CdbPath) -or [string]::IsNullOrWhiteSpace($LoaderTargetPath)) { throw 'WTS Loader Snaps mode requires explicit CdbPath and LoaderTargetPath host files.' }
    $loaderCdbCanonical = Get-CanonicalPath $CdbPath File
    $loaderTargetCanonical = Get-CanonicalPath $LoaderTargetPath File
    if ([IO.Path]::GetFileName($loaderCdbCanonical) -ine 'cdb.exe' -or [IO.Path]::GetFileName($loaderTargetCanonical) -ine 'exit-only-probe.exe') { throw 'WTS Loader Snaps mode requires cdb.exe and exit-only-probe.exe source basenames.' }
    $sourceCdbSignature = Get-AuthenticodeSignature -LiteralPath $loaderCdbCanonical -ErrorAction Stop
    if ($sourceCdbSignature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) { throw 'CDB Authenticode signature is not Valid.' }
    if ((Get-PortableExecutableMachine $loaderCdbCanonical) -ne '0x8664' -or (Get-PortableExecutableMachine $loaderTargetCanonical) -ne '0x8664') { throw 'CDB and loader target must be x64 PE files.' }
    $manifest.validation.cdb_source_path = $loaderCdbCanonical
    $manifest.validation.cdb_sha256 = Get-FileSha256 $loaderCdbCanonical
    $manifest.validation.cdb_authenticode_status = [string]$sourceCdbSignature.Status
    $manifest.validation.loader_target_source_path = $loaderTargetCanonical
    $manifest.validation.loader_target_sha256 = Get-FileSha256 $loaderTargetCanonical
  }
  $inputEvidence = Get-CanonicalPath ([string]$input.evidence_directory) Directory
  if (-not (Test-PathEqual ([IO.Path]::GetDirectoryName($browserExecutable)) $browserDirectory)) { throw 'The executable is outside the declared browser directory.' }
  if (-not (Test-PathEqual $inputPage $pageCanonical)) { throw 'Input test_page does not match the supplied test-page path.' }
  if (-not (Test-PathEqual $inputRunner $runnerCanonical)) { throw 'Input guest_runner does not match the supplied guest-runner path.' }
  if (($WtsLoaderSnapsOnly -or $WtsProcessSingletonDiagnosticOnly) -and -not (Test-PathEqual (Split-Path -Parent $runnerCanonical) (Join-Path $attemptRootCanonical 'host-runner'))) { throw 'WTS diagnostic tools must be staged only beneath this attempt root host-runner mapped directory.' }
  if (-not (Test-PathEqual $probePath (Join-Path (Split-Path -Parent $runnerCanonical) 'ProcessSingletonApiProbe.ps1'))) { throw 'Input probe_script does not point to the copied ProcessSingleton API probe in host-runner.' }
  if (-not (Test-PathEqual $desktopAclProbePath (Join-Path (Split-Path -Parent $runnerCanonical) 'ProbeInteractiveDesktopAcl.ps1'))) { throw 'Input desktop_acl_probe_script does not point to the copied read-only desktop ACL probe in host-runner.' }
  if (-not (Test-PathEqual $helperPath (Join-Path (Join-Path (Split-Path -Parent $runnerCanonical) 'lease-job-helper') 'LeaseProcessJobRunner.exe'))) { throw 'Input helper_executable does not point to the linked-source helper in host-runner/lease-job-helper.' }
  if (-not $WtsLoaderSnapsOnly -and -not $WtsProcessSingletonDiagnosticOnly -and -not (Test-PathEqual $nativeDiagnosticPath (Join-Path (Split-Path -Parent $runnerCanonical) 'native-desktop-probe.exe'))) { throw 'Native diagnostic must be the reviewed native-desktop-probe.exe inside the read-only mapped host-runner folder.' }
  if (-not (Test-PathEqual $inputEvidence $evidenceCanonical)) { throw 'Input evidence_directory does not match the supplied evidence directory.' }
  if ($WtsProcessSingletonDiagnosticOnly) {
    $manifest.process_singleton_diagnostic.runner_status_file = Join-Path $evidenceCanonical "b2-runner-status-$runId.json"
    if (Test-Path -LiteralPath $manifest.process_singleton_diagnostic.runner_status_file) { throw 'Refusing to reuse a pre-existing WTS ProcessSingleton runner-status sidecar.' }
  }
  if ([string]$input.guest_browser -ne 'C:\b2\browser\chrome.exe' -or [string]$input.guest_test_page -ne 'C:\b2\runner\test-page.html' -or [string]$input.guest_probe_script -ne 'C:\b2\runner\ProcessSingletonApiProbe.ps1' -or [string]$input.guest_desktop_acl_probe_script -ne 'C:\b2\runner\ProbeInteractiveDesktopAcl.ps1' -or [string]$input.guest_helper_executable -ne 'C:\b2\runner\lease-job-helper\LeaseProcessJobRunner.exe' -or [string]$input.guest_evidence_directory -ne 'C:\b2\evidence') { throw 'Guest mapping paths do not match the runner contract.' }

  $browserVersion = [Diagnostics.FileVersionInfo]::GetVersionInfo($browserExecutable)
  $browserHash = Get-FileSha256 $browserExecutable
  $browserLength = (Get-Item -LiteralPath $browserExecutable).Length
  if ($browserHash -ne ([string]$input.expected_browser_sha256).ToLowerInvariant() -or $browserVersion.FileVersion -ne [string]$input.expected_browser_file_version -or $browserVersion.ProductVersion -ne [string]$input.expected_browser_product_version -or $browserLength -ne [long]$input.expected_browser_length) {
    throw 'Locked Chromium path metadata, version, length, or SHA-256 does not match the reviewed input JSON.'
  }

  $xml = Read-SecureXml $configCanonical
  if ($xml.DocumentElement.LocalName -ne 'Configuration') { throw 'Sandbox config root must be Configuration.' }
  $networkingNodes = @($xml.SelectNodes('/Configuration/Networking'))
  if ($networkingNodes.Count -ne 1 -or $networkingNodes[0].InnerText.Trim() -ne 'Disabled') { throw 'Sandbox config must contain exactly one Networking=Disabled setting.' }
  $clipboardNodes = @($xml.SelectNodes('/Configuration/ClipboardRedirection'))
  if ($clipboardNodes.Count -ne 1 -or $clipboardNodes[0].InnerText.Trim() -ne 'Disable') { throw 'Sandbox config must contain exactly one ClipboardRedirection=Disable setting.' }
  $folderNodes = @($xml.SelectNodes('/Configuration/MappedFolders/MappedFolder'))
  if ($folderNodes.Count -ne 3) { throw "Sandbox config must have exactly 3 mapped folders; found $($folderNodes.Count)." }

  $expectedMappings = @(
    [ordered]@{ host = $browserDirectory; guest = 'C:\b2\browser'; read_only = $true },
    [ordered]@{ host = [IO.Path]::GetDirectoryName($runnerCanonical); guest = 'C:\b2\runner'; read_only = $true },
    [ordered]@{ host = $evidenceCanonical; guest = 'C:\b2\evidence'; read_only = $false }
  )
  $actualMappings = @()
  $seenMappings = @{}
  foreach ($node in $folderNodes) {
    $hostNodes = @($node.SelectNodes('HostFolder'))
    $guestNodes = @($node.SelectNodes('SandboxFolder'))
    $readOnlyNodes = @($node.SelectNodes('ReadOnly'))
    if ($hostNodes.Count -ne 1 -or $guestNodes.Count -ne 1 -or $readOnlyNodes.Count -ne 1) { throw 'Each mapped folder must declare one HostFolder, SandboxFolder, and ReadOnly value.' }
    $hostPath = Get-CanonicalPath $hostNodes[0].InnerText.Trim() Directory
    $guestPath = $guestNodes[0].InnerText.Trim().TrimEnd('\')
    $readOnly = $false
    if (-not [bool]::TryParse($readOnlyNodes[0].InnerText.Trim(), [ref]$readOnly)) { throw "Invalid ReadOnly value '$($readOnlyNodes[0].InnerText)'" }
    $match = @($expectedMappings | Where-Object { (Test-PathEqual $hostPath $_.host) -and [string]::Equals($guestPath, $_.guest, [StringComparison]::OrdinalIgnoreCase) -and $readOnly -eq $_.read_only })
    if ($match.Count -ne 1) { throw "Unexpected mapped folder: host='$hostPath', guest='$guestPath', read_only=$readOnly" }
    $mappingRole = [string]$match[0].guest
    if ($seenMappings.ContainsKey($mappingRole)) { throw "Duplicate mapped folder role '$mappingRole'." }
    $seenMappings[$mappingRole] = $true
    $actualMappings += [ordered]@{ host_folder = $hostPath; guest_folder = $guestPath; read_only = $readOnly }
  }
  if ($actualMappings.Count -ne $expectedMappings.Count) { throw 'Sandbox mappings do not satisfy the exact three-path contract.' }
  foreach ($expectedMapping in $expectedMappings) {
    if (-not $seenMappings.ContainsKey([string]$expectedMapping.guest)) { throw "Required mapped folder role '$($expectedMapping.guest)' is missing." }
  }

  $manifest.validation.status = 'passed'
  $manifest.validation.networking = 'Disabled'
  $manifest.validation.clipboard_redirection = 'Disable'
  $manifest.validation.mapped_folders = @($actualMappings)
  $manifest.validation.config_sha256 = Get-FileSha256 $configCanonical
  $manifest.validation.input_sha256 = Get-FileSha256 $inputCanonical
  $manifest.validation.browser_path = $browserExecutable
  $manifest.validation.browser_file_version = $browserVersion.FileVersion
  $manifest.validation.browser_product_version = $browserVersion.ProductVersion
  $manifest.validation.browser_sha256 = $browserHash
  $manifest.validation.browser_length = $browserLength
  $manifest.validation.probe_path = $probePath
  $manifest.validation.probe_sha256 = Get-FileSha256 $probePath
  $manifest.validation.desktop_acl_probe_path = $desktopAclProbePath
  $manifest.validation.desktop_acl_probe_sha256 = Get-FileSha256 $desktopAclProbePath
  $manifest.validation.helper_path = $helperPath
  $manifest.validation.helper_sha256 = Get-FileSha256 $helperPath
  $manifest.validation.helper_assembly_path = $helperAssemblyPath
  $manifest.validation.helper_assembly_sha256 = Get-FileSha256 $helperAssemblyPath
  $manifest.validation.helper_assembly_length = (Get-Item -LiteralPath $helperAssemblyPath).Length
  if (-not $WtsLoaderSnapsOnly -and -not $WtsProcessSingletonDiagnosticOnly) {
    $manifest.validation.native_diagnostic_path = $nativeDiagnosticPath
    $manifest.validation.native_diagnostic_sha256 = Get-FileSha256 $nativeDiagnosticPath
    $manifest.validation.native_diagnostic_length = (Get-Item -LiteralPath $nativeDiagnosticPath).Length
  }
  $manifest.validation.guest_runner_sha256 = Get-FileSha256 $runnerCanonical
  $manifest.validation.test_page_sha256 = Get-FileSha256 $pageCanonical
}
catch {
  $validationFailed = $true
  $manifest.validation.status = 'failed'
  $manifest.validation.errors = @([ordered]@{ message = $_.Exception.Message; error_type = $_.Exception.GetType().FullName })
  $manifest.phase = 'validation_failed'
  $manifest.failure = [ordered]@{ stage = 'preflight_validation'; message = $_.Exception.Message }
}

Save-Manifest
if ($validationFailed) {
  [Console]::Error.WriteLine("B2 configuration validation failed before any WSB command: $($manifest.failure.message)")
  exit 2
}

if (-not $Execute) {
  $manifest.phase = 'validated_not_started'
  Save-Manifest
  Write-Output "Validated run $($manifest.run_id); no WSB commands were invoked."
  exit 0
}

try {
  if ($WtsLoaderSnapsOnly) {
    $manifest.phase = 'stage_loader_debugger_runtime'
    $manifest.staging.status = 'staging; no WSB command has run'
    Save-Manifest
    try {
      $stagedLoaderInputs = Stage-LoaderSnapsRuntime -RunnerDirectory (Split-Path -Parent $runnerCanonical) -CdbSourcePath $loaderCdbCanonical -TargetSourcePath $loaderTargetCanonical -RunId ([string]$manifest.run_id)
      $manifest.validation.staged_debugger_files = @($stagedLoaderInputs.staged_files)
      $manifest.validation.cdb_sha256 = [string]$stagedLoaderInputs.cdb_sha256
      $manifest.validation.loader_target_sha256 = [string]$stagedLoaderInputs.target_sha256
      $manifest.staging.runtime_manifest_path = [string]$stagedLoaderInputs.runtime_manifest_path
      $manifest.staging.runtime_manifest_sha256 = [string]$stagedLoaderInputs.runtime_manifest_sha256
      $manifest.staging.staged_files = @($stagedLoaderInputs.staged_files)
      $manifest.staging.status = 'complete; all files copied with CreateNew and source/destination hashes matched'
      Save-Manifest
    }
    catch {
      $manifest.staging.status = 'failed; partial files are preserved and this AttemptRoot cannot be reused'
      $manifest.staging.failure = [ordered]@{ error_type = $_.Exception.GetType().FullName; message = $_.Exception.Message }
      $manifest.failure = [ordered]@{ stage = 'loader_runtime_staging'; message = $_.Exception.Message }
      throw
    }
  }
  if ([string]::IsNullOrWhiteSpace($WsbPath)) {
    $wsbCommand = Get-Command 'wsb.exe' -ErrorAction Stop
    $WsbPath = $wsbCommand.Source
  }
  $WsbPath = Get-CanonicalPath $WsbPath File
  $manifest.phase = 'preflight_inventory'
  Save-Manifest
  $inventory = Invoke-Wsb -Operation 'list' -Arguments @('list','--raw')
  $manifest.preflight.wsb_outer_exit_code = $inventory.outer_exit_code
  $manifest.preflight.raw_output = $inventory.raw_output
  $manifest.preflight.raw_stderr = $inventory.raw_stderr
  $manifest.preflight.timed_out = $inventory.timed_out
  $manifest.preflight.timeout_seconds = $inventory.timeout_seconds
  $manifest.preflight.command_termination = $inventory.command_termination
  $manifest.preflight.launch_error = $inventory.launch_error
  if ($inventory.outer_exit_code -ne 0 -or $inventory.timed_out) { throw 'Bounded wsb list failed or timed out; refusing to start a Sandbox.' }
  $inventoryJson = $inventory.raw_output | ConvertFrom-Json -ErrorAction Stop
  $inventoryParse = ConvertFrom-WsbSandboxInventory $inventoryJson
  if (-not $inventoryParse.recognized) { throw "wsb list output shape was not recognized ($($inventoryParse.reason)); refusing to start a Sandbox." }
  $runningIds = @($inventoryParse.sandbox_ids)
  $manifest.preflight.running_sandbox_ids = @($runningIds)
  if ($runningIds.Count -gt 0) { throw 'A Sandbox is already running; refusing to start or stop any instance.' }
  $manifest.preflight.status = 'passed; no running Sandbox instances'
  $manifest.start.requested_id = $manifest.task_owned_sandbox_id
  $manifest.start.config_path = $manifest.validation.config_path
  $manifest.start.status = 'starting'
  $manifest.phase = 'start_in_progress'
  $manifest.side_effects_started = $true
  Save-Manifest

  $startWasInvoked = $true
  $configurationXml = [IO.File]::ReadAllText([string]$manifest.validation.config_path)
  $startResult = Invoke-Wsb -Operation 'start' -Arguments @('start','--id',[string]$manifest.task_owned_sandbox_id,'--config',$configurationXml,'--raw')
  $manifest.start.wsb_outer_exit_code = $startResult.outer_exit_code
  $manifest.start.raw_output = $startResult.raw_output
  $manifest.start.raw_stderr = $startResult.raw_stderr
  $manifest.start.timed_out = $startResult.timed_out
  $manifest.start.timeout_seconds = $startResult.timeout_seconds
  $manifest.start.command_termination = $startResult.command_termination
  $manifest.start.launch_error = $startResult.launch_error
  if ($startResult.outer_exit_code -ne 0 -or $startResult.timed_out) {
    $manifest.start.status = if ($startResult.timed_out) { 'timed_out; outer command exit code unknown' } else { 'failed; outer command nonzero or unknown' }
    throw 'Bounded wsb start failed or timed out.'
  }
  $startJson = $startResult.raw_output | ConvertFrom-Json -ErrorAction Stop
  if (-not (Test-JsonField $startJson 'Id')) { throw 'wsb start output did not contain returned Id.' }
  $returnedId = ConvertTo-ValidatedGuid ([string]$startJson.Id) 'wsb start returned Id'
  $manifest.start.returned_id = $returnedId
  if ($returnedId -ne $manifest.task_owned_sandbox_id) { throw 'wsb returned an ID different from the requested task-owned ID; ownership is unverified.' }
  $ownedSandboxStarted = $true
  $manifest.start.status = 'started; returned ID matches task-owned ID'
  if ($ConnectBeforeExec) {
    $manifest.connect.status = 'connecting'
    $manifest.phase = 'interactive_session_connect'
    Save-Manifest
    $connectResult = Invoke-Wsb -Operation 'connect' -Arguments @('connect','--id',[string]$manifest.task_owned_sandbox_id,'--raw')
    $manifest.connect.wsb_outer_exit_code = $connectResult.outer_exit_code
    $manifest.connect.raw_output = $connectResult.raw_output
    $manifest.connect.raw_stderr = $connectResult.raw_stderr
    $manifest.connect.timed_out = $connectResult.timed_out
    $manifest.connect.timeout_seconds = $connectResult.timeout_seconds
    $manifest.connect.command_termination = $connectResult.command_termination
    $manifest.connect.launch_error = $connectResult.launch_error
    if ($connectResult.outer_exit_code -ne 0 -or $connectResult.timed_out) {
      $manifest.connect.status = if ($connectResult.timed_out) { 'timed_out; connection completion unknown' } else { 'failed or unknown' }
      throw 'Bounded wsb connect failed or timed out; guest execution will not proceed.'
    }
    $manifest.connect.status = if ($WtsProcessSingletonDiagnosticOnly) { 'connect command completed; WTS Session 1 token readback gates the ProcessSingleton diagnostic' } elseif ($WtsLoaderSnapsOnly) { 'connect command completed; WTS Session 1 token readback gates the loader diagnostic' } elseif ($WtsNativeControlOnly) { 'connect command completed; WTS Session 1 token readback and native User32 fixture are the only session/desktop gates' } else { 'connect command completed; ExistingLogin readiness is checked by the bounded desktop probe and target-token session is checked before process launch' }
  }
  $manifest.phase = 'guest_control'
  Save-Manifest

  if ($WtsNativeControlOnly -or $WtsLoaderSnapsOnly -or $WtsProcessSingletonDiagnosticOnly) {
    $manifest.desktop_acl_probe.status = 'not_run; WTS diagnostic-only mode gates on WTS token readback; guest-produced DACL JSON is untrusted and non-gating'
    $manifest.desktop_access_check.status = 'not_performed'
    $manifest.desktop_access_check.reason = 'No guest-written DACL report is accepted as trusted input or used as a launch gate.'
    $manifest.desktop_acl_hint.status = 'not_read; guest-writable DACL evidence is untrusted and non-gating'
    $manifest.desktop_acl_hint.gating = $false
    Save-Manifest
  }
  else {
  $desktopProbeCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\b2\runner\ProbeInteractiveDesktopAcl.ps1 -ResultPath C:\b2\evidence\interactive-desktop-acl.json -RunToken $($manifest.run_id)"
  $manifest.desktop_acl_probe.command = $desktopProbeCommand
  $manifest.desktop_acl_probe.status = 'running'
  $manifest.phase = 'desktop_acl_probe'
  Save-Manifest
  $desktopProbeResult = $null
  $desktopProbeGuestExitCode = 'unknown'
  for ($probeAttempt = 1; $probeAttempt -le 6; $probeAttempt++) {
    if (Test-Path -LiteralPath $manifest.desktop_acl_probe.evidence_file) {
      $manifest.desktop_acl_probe.status = 'failed; evidence file already exists before ExistingLogin probe attempt'
      throw 'Refusing to overwrite an existing desktop ACL probe report.'
    }
    $desktopProbeResult = Invoke-Wsb -Operation 'exec' -Arguments @('exec','--id',[string]$manifest.task_owned_sandbox_id,'--command',$desktopProbeCommand,'--run-as','ExistingLogin','--raw')
    $desktopProbeGuestExitCode = Get-GuestExitCode $desktopProbeResult.raw_output
    $manifest.desktop_acl_probe.attempts += [ordered]@{
      attempt = $probeAttempt
      wsb_outer_exit_code = $desktopProbeResult.outer_exit_code
      guest_process_exit_code = $desktopProbeGuestExitCode
      timed_out = $desktopProbeResult.timed_out
      timeout_seconds = $desktopProbeResult.timeout_seconds
      command_termination = $desktopProbeResult.command_termination
      evidence_file_created = [bool](Test-Path -LiteralPath $manifest.desktop_acl_probe.evidence_file -PathType Leaf)
      status = if ($desktopProbeResult.outer_exit_code -eq 0 -and -not $desktopProbeResult.timed_out -and $desktopProbeGuestExitCode -eq 0) { 'completed' } elseif ($desktopProbeResult.outer_exit_code -eq -2147023584 -and -not $desktopProbeResult.timed_out) { 'retryable; ERROR_NO_LOGON_SESSION (0x80070520)' } else { 'failed' }
    }
    $manifest.desktop_acl_probe.wsb_outer_exit_code = $desktopProbeResult.outer_exit_code
    $manifest.desktop_acl_probe.raw_output = $desktopProbeResult.raw_output
    $manifest.desktop_acl_probe.raw_stderr = $desktopProbeResult.raw_stderr
    $manifest.desktop_acl_probe.timed_out = $desktopProbeResult.timed_out
    $manifest.desktop_acl_probe.timeout_seconds = $desktopProbeResult.timeout_seconds
    $manifest.desktop_acl_probe.command_termination = $desktopProbeResult.command_termination
    $manifest.desktop_acl_probe.launch_error = $desktopProbeResult.launch_error
    $manifest.desktop_acl_probe.guest_process_exit_code = $desktopProbeGuestExitCode
    Save-Manifest
    if ($desktopProbeResult.outer_exit_code -eq 0 -and -not $desktopProbeResult.timed_out -and $desktopProbeGuestExitCode -eq 0) { break }
    $retryableLogonSession = $desktopProbeResult.outer_exit_code -eq -2147023584 -and -not $desktopProbeResult.timed_out -and -not (Test-Path -LiteralPath $manifest.desktop_acl_probe.evidence_file) -and $probeAttempt -lt 6
    if ($retryableLogonSession) {
      $manifest.desktop_acl_probe.status = 'waiting; ExistingLogin reported ERROR_NO_LOGON_SESSION; retrying read-only readiness probe after 2 seconds'
      Save-Manifest
      Start-Sleep -Seconds 2
      continue
    }
    break
  }
  if ($desktopProbeResult.outer_exit_code -ne 0 -or $desktopProbeResult.timed_out -or $desktopProbeGuestExitCode -ne 0) {
    $manifest.desktop_acl_probe.status = 'failed; read-only guest probe exit contract not satisfied'
    throw 'Read-only interactive desktop ACL probe did not complete successfully; low-token launch was skipped.'
  }
  if (-not (Test-Path -LiteralPath $manifest.desktop_acl_probe.evidence_file -PathType Leaf)) {
    $manifest.desktop_acl_probe.status = 'failed; evidence file missing'
    throw 'Read-only interactive desktop ACL probe did not write its evidence file; low-token launch was skipped.'
  }
  $desktopObservation = Get-Content -LiteralPath $manifest.desktop_acl_probe.evidence_file -Raw | ConvertFrom-Json -ErrorAction Stop
  $expectedProbeSession = if ($WtsNativeControlOnly) { 1 } else { [int]$desktopObservation.sessionId }
  $desktopReportValid = ([string]$desktopObservation.runToken -eq [string]$manifest.run_id) -and ([string]$desktopObservation.status -eq 'pass') -and ([string]$desktopObservation.windowStationName -ieq 'WinSta0') -and ([string]$desktopObservation.desktopName -ieq 'Default') -and ([int]$desktopObservation.sessionId -eq $expectedProbeSession) -and -not [string]::IsNullOrWhiteSpace([string]$desktopObservation.userSid) -and -not [string]::IsNullOrWhiteSpace([string]$desktopObservation.logonSid) -and -not [string]::IsNullOrWhiteSpace([string]$desktopObservation.windowStationSddl) -and -not [string]::IsNullOrWhiteSpace([string]$desktopObservation.desktopSddl)
  if ($desktopReportValid) {
    try {
      $probeSid = [Security.Principal.SecurityIdentifier]::new([string]$desktopObservation.userSid)
      if ($probeSid.Value -ne [string]$desktopObservation.userSid) { $desktopReportValid = $false }
      foreach ($sddl in @([string]$desktopObservation.windowStationSddl, [string]$desktopObservation.desktopSddl)) {
        $descriptor = [Security.AccessControl.RawSecurityDescriptor]::new($sddl)
        if ($null -eq $descriptor.Owner -or $null -eq $descriptor.Group -or $null -eq $descriptor.DiscretionaryAcl -or (($descriptor.ControlFlags -band [Security.AccessControl.ControlFlags]::DiscretionaryAclPresent) -eq 0)) { $desktopReportValid = $false }
      }
    }
    catch { $desktopReportValid = $false }
  }
  if (-not $desktopReportValid) {
    $manifest.desktop_acl_probe.status = 'failed; report contract mismatch'
    throw 'Read-only interactive desktop ACL probe report failed its session/object/DACL contract; low-token launch was skipped.'
  }
  $manifest.desktop_acl_probe.user_sid = [string]$desktopObservation.userSid
  $manifest.desktop_acl_probe.logon_sid = [string]$desktopObservation.logonSid
  $manifest.desktop_acl_probe.session_id = [int]$desktopObservation.sessionId
  $manifest.desktop_acl_probe.token = $desktopObservation.token
  $manifest.desktop_acl_probe.window_station_name = [string]$desktopObservation.windowStationName
  $manifest.desktop_acl_probe.desktop_name = [string]$desktopObservation.desktopName
  $manifest.desktop_acl_probe.window_station_sddl_sha256 = Get-TextSha256 ([string]$desktopObservation.windowStationSddl)
  $manifest.desktop_acl_probe.desktop_sddl_sha256 = Get-TextSha256 ([string]$desktopObservation.desktopSddl)
  $manifest.desktop_acl_probe.status = 'pass; same-session guest DACL captured for diagnostics only; it is not treated as trusted evidence'
  $manifest.phase = 'desktop_acl_probe_recorded'
  }

  if ($WtsDesktopAclDiagnosticOnly) {
    $manifest.desktop_access_check.status = 'pending; exact filtered WTS-token AccessCheck will be recorded as diagnostic-only evidence'
    $manifest.desktop_access_check.reason = 'Guest-produced DACL is untrusted and does not gate execution; the helper binds User SID, Logon SID, session, run ID and object names before a read-only AccessCheck.'
    $manifest.desktop_access_check.untrusted_dacl_hint_used = $false
    $manifest.desktop_acl_hint.status = 'read_only diagnostic input; not an attestation or launch gate'
    $manifest.desktop_acl_hint.gating = $false
    Save-Manifest
  }

  $guestWorkDirectory = "C:\b2\work\b2-$($manifest.run_id)"
  if ($WtsLoaderSnapsOnly) {
    $manifest.loader_diagnostic.observation_file = Join-Path $evidenceCanonical "loader-snaps-$($manifest.run_id).json"
    $manifest.guest_control.evidence_file = [string]$manifest.loader_diagnostic.observation_file
    $manifest.guest_control.command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\b2\runner\run-b2-locked-chromium.ps1 -EvidencePath C:\b2\evidence -HelperPath C:\b2\runner\lease-job-helper\LeaseProcessJobRunner.exe -WorkDirectory $guestWorkDirectory -TimeoutSeconds 45 -WtsLoaderSnapsOnly -CdbPath C:\b2\runner\debuggers\x64\cdb.exe -LoaderTargetPath C:\b2\runner\loader-diagnostic\exit-only-probe.exe -CdbSha256 $($manifest.validation.cdb_sha256) -LoaderTargetSha256 $($manifest.validation.loader_target_sha256) -RunId $($manifest.run_id)"
    $guestCommand = [string]$manifest.guest_control.command
  }
  elseif ($WtsProcessSingletonDiagnosticOnly) {
    $manifest.guest_control.command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\b2\runner\run-b2-locked-chromium.ps1 -EvidencePath C:\b2\evidence -HelperPath C:\b2\runner\lease-job-helper\LeaseProcessJobRunner.exe -ProbeScriptPath C:\b2\runner\ProcessSingletonApiProbe.ps1 -WorkDirectory $guestWorkDirectory -TimeoutSeconds 45 -WtsProcessSingletonDiagnosticOnly -RunId $($manifest.run_id)"
    $guestCommand = [string]$manifest.guest_control.command
  }
  elseif ($WtsDesktopAclDiagnosticOnly) {
    $guestCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\b2\runner\run-b2-locked-chromium.ps1 -EvidencePath C:\b2\evidence -HelperPath C:\b2\runner\lease-job-helper\LeaseProcessJobRunner.exe -ProbeScriptPath C:\b2\runner\ProbeInteractiveDesktopAcl.ps1 -DesktopAclEvidencePath C:\b2\evidence\interactive-desktop-acl.json -WorkDirectory $guestWorkDirectory -TimeoutSeconds 45 -WtsDesktopAclDiagnosticOnly -RunId $($manifest.run_id)"
  }
  elseif ($WtsNativeControlOnly) {
    $guestCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\b2\runner\run-b2-locked-chromium.ps1 -EvidencePath C:\b2\evidence -HelperPath C:\b2\runner\lease-job-helper\LeaseProcessJobRunner.exe -NativeDiagnosticPath C:\b2\runner\native-desktop-probe.exe -WorkDirectory $guestWorkDirectory -TimeoutSeconds 45 -WtsNativeControlOnly -RunId $($manifest.run_id)"
  }
  else {
    $guestCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\b2\runner\run-b2-locked-chromium.ps1 -EvidencePath C:\b2\evidence -HelperPath C:\b2\runner\lease-job-helper\LeaseProcessJobRunner.exe -ProbeScriptPath C:\b2\runner\ProcessSingletonApiProbe.ps1 -DesktopAclEvidencePath C:\b2\evidence\interactive-desktop-acl.json -NativeDiagnosticPath C:\b2\runner\native-desktop-probe.exe -BrowserPath C:\b2\browser\chrome.exe -TestPagePath C:\b2\runner\test-page.html -WorkDirectory $guestWorkDirectory -TimeoutSeconds 45"
  }
  $manifest.guest_control.command = $guestCommand
  $manifest.guest_control.status = 'running'
  Save-Manifest
  $guestResult = Invoke-Wsb -Operation 'exec' -Arguments @('exec','--id',[string]$manifest.task_owned_sandbox_id,'--command',$guestCommand,'--run-as','System','--raw')
  $manifest.guest_control.wsb_outer_exit_code = $guestResult.outer_exit_code
  $manifest.guest_control.raw_output = $guestResult.raw_output
  $manifest.guest_control.raw_stderr = $guestResult.raw_stderr
  $manifest.guest_control.timed_out = $guestResult.timed_out
  $manifest.guest_control.timeout_seconds = $guestResult.timeout_seconds
  $manifest.guest_control.command_termination = $guestResult.command_termination
  $manifest.guest_control.launch_error = $guestResult.launch_error
  $manifest.guest_control.guest_process_exit_code = Get-GuestExitCode $guestResult.raw_output
  $manifest.guest_control.runner_invoked = if ($manifest.guest_control.guest_process_exit_code -eq 'unknown') { 'unknown' } else { $true }
  if ($guestResult.timed_out) {
    $manifest.guest_control.status = 'timed_out; WSB outer root process termination requested; guest completion may be unknown'
    $manifest.failure = [ordered]@{ stage = 'guest_exec_timeout'; message = "Bounded wsb exec exceeded $($guestResult.timeout_seconds) seconds; guest exit code and browser result may be unknown."; command_termination = $guestResult.command_termination }
  }
  elseif ($guestResult.outer_exit_code -ne 0) {
    $manifest.guest_control.status = 'WSB outer command failed or unknown'
    $manifest.failure = [ordered]@{ stage = 'guest_exec_outer'; message = 'Bounded wsb exec returned a nonzero or unknown outer exit code.'; raw_stderr = $guestResult.raw_stderr }
  }
  elseif ($manifest.guest_control.guest_process_exit_code -eq 'unknown') {
    $manifest.guest_control.status = 'guest exit code unknown'
    $manifest.failure = [ordered]@{ stage = 'guest_process_exit'; message = 'WSB completed but raw guest ExitCode was missing or invalid.' }
  }
  elseif ($manifest.guest_control.guest_process_exit_code -ne 0) {
    $manifest.guest_control.status = 'guest process returned nonzero'
    $manifest.failure = [ordered]@{ stage = 'guest_process_exit'; message = 'Raw guest ExitCode was nonzero.' }
  }
  else { $manifest.guest_control.status = 'guest result observed' }
  if ($WtsProcessSingletonDiagnosticOnly) { Update-ProcessSingletonObservation }
  elseif ($WtsLoaderSnapsOnly) { Update-LoaderSnapsObservation }
  else { Update-BrowserObservation }
  $manifest.phase = 'guest_result_recorded'
}
catch {
  $manifest.failure = [ordered]@{ stage = [string]$manifest.phase; message = $_.Exception.Message; error_type = $_.Exception.GetType().FullName }
  if ($null -eq $manifest.preflight.running_sandbox_ids -or $manifest.preflight.running_sandbox_ids -eq 'unknown') { $manifest.preflight.status = 'failed; inventory not proven empty' }
  if ($manifest.start.status -eq 'starting') { $manifest.start.status = 'failed or unknown' }
  if ($startWasInvoked -and -not $ownedSandboxStarted) {
    $ownership = Get-PostStartOwnership ([string]$manifest.task_owned_sandbox_id)
    $manifest.start.post_start_inventory = $ownership
    $manifest.start.ownership_resolution = $ownership.status
    if ($ownership.requested_id_present) {
      $ownedSandboxStarted = $true
      $manifest.side_effects_started = $true
      $manifest.start.status = 'started; exact requested task-owned ID recovered from inventory after uncertain start response'
    }
    else {
      $manifest.start.status = 'uncertain; requested instance was not confirmed'
      $manifest.uncertain_orphan_state = [ordered]@{ status = 'possible orphan; no Sandbox was stopped because exact requested ID ownership was not proven'; inventory = $ownership }
    }
  }
}
finally {
  if ($ownedSandboxStarted) {
    $manifest.stop.task_owned_sandbox_id = $manifest.task_owned_sandbox_id
    $manifest.stop.status = 'stopping task-owned Sandbox'
    $manifest.phase = 'stop_in_progress'
    try { Save-Manifest }
    catch {
      $manifest.stop.pre_stop_manifest_save_error = $_.Exception.Message
      $manifest.manifest_write_errors += "pre-stop save: $($_.Exception.Message)"
    }

    try {
      try {
        $stopResult = Invoke-Wsb -Operation 'stop' -Arguments @('stop','--id',[string]$manifest.task_owned_sandbox_id,'--raw')
        $manifest.stop.wsb_outer_exit_code = $stopResult.outer_exit_code
        $manifest.stop.raw_output = $stopResult.raw_output
        $manifest.stop.raw_stderr = $stopResult.raw_stderr
        $manifest.stop.timed_out = $stopResult.timed_out
        $manifest.stop.timeout_seconds = $stopResult.timeout_seconds
        $manifest.stop.command_termination = $stopResult.command_termination
        $manifest.stop.launch_error = $stopResult.launch_error
        $manifest.stop.status = if ($stopResult.timed_out) { 'timed_out; WSB stop completion unknown' } elseif ($stopResult.outer_exit_code -eq 0) { 'stop command succeeded' } else { 'stop failed or unknown' }
      }
      catch {
        $stopError = $_.Exception.Message
        $manifest.stop.launch_error = "Stop invocation or result recording threw: $stopError"
        $manifest.stop.status = 'failed; stop invocation or result recording threw; post-stop inventory will still be attempted'
        $manifest.stop.recording_error = $stopError
      }
    }
    finally {
      try {
        $inventoryAfter = Invoke-Wsb -Operation 'list' -Arguments @('list','--raw')
        $manifest.post_stop_inventory.wsb_outer_exit_code = $inventoryAfter.outer_exit_code
        $manifest.post_stop_inventory.raw_output = $inventoryAfter.raw_output
        $manifest.post_stop_inventory.raw_stderr = $inventoryAfter.raw_stderr
        $manifest.post_stop_inventory.timed_out = $inventoryAfter.timed_out
        $manifest.post_stop_inventory.timeout_seconds = $inventoryAfter.timeout_seconds
        $manifest.post_stop_inventory.command_termination = $inventoryAfter.command_termination
        $manifest.post_stop_inventory.launch_error = $inventoryAfter.launch_error
        if ($inventoryAfter.outer_exit_code -eq 0 -and -not $inventoryAfter.timed_out) {
          try {
            $postJson = $inventoryAfter.raw_output | ConvertFrom-Json -ErrorAction Stop
            $postParse = ConvertFrom-WsbSandboxInventory $postJson
            if ($postParse.recognized) {
              $postIds = @($postParse.sandbox_ids)
              $manifest.post_stop_inventory.running_sandbox_ids = @($postIds)
              $manifest.post_stop_inventory.status = if ($postIds -notcontains $manifest.task_owned_sandbox_id) { 'task-owned Sandbox absent' } else { 'task-owned Sandbox still listed' }
            }
            else { $manifest.post_stop_inventory.status = "unknown; inventory shape unrecognized: $($postParse.reason)" }
          }
          catch { $manifest.post_stop_inventory.status = "unknown; inventory parse failed: $($_.Exception.Message)" }
        }
        else { $manifest.post_stop_inventory.status = 'unknown; inventory command failed or timed out' }
      }
      catch {
        $inventoryError = $_.Exception.Message
        $manifest.post_stop_inventory.status = 'unknown; post-stop inventory invocation or recording threw'
        $manifest.post_stop_inventory.launch_error = $inventoryError
        $manifest.post_stop_inventory.recording_error = $inventoryError
      }
    }
  }
  if ($WtsProcessSingletonDiagnosticOnly) {
    $manifest.phase = if ($null -ne $manifest.failure) { 'process_singleton_diagnostic_failed' } elseif ($manifest.process_singleton_diagnostic.status -eq 'diagnostic_complete') { 'process_singleton_diagnostic_complete' } else { 'process_singleton_diagnostic_unknown' }
    $manifest.b2_acceptance = 'not_evaluated_diagnostic_only'
  }
  elseif ($WtsLoaderSnapsOnly) {
    $manifest.phase = if ($null -ne $manifest.failure) { 'loader_diagnostic_failed' } elseif ($manifest.loader_diagnostic.status -eq 'diagnostic_complete') { 'loader_diagnostic_complete' } else { 'loader_diagnostic_unknown' }
    $manifest.b2_acceptance = 'not_evaluated_diagnostic_only'
    $manifest.loader_diagnostic.b2_pass = $false
  }
  elseif (($null -ne $manifest.failure) -and ($manifest.browser.process_exit_code -eq 'not_run') -and ($manifest.probe.status -eq 'not_run')) {
    $manifest.phase = 'fixture_failed_before_probe'
  }
  elseif ($null -ne $manifest.failure) {
    $manifest.phase = 'execution_failed'
  }
  elseif ($null -eq $manifest.failure -and $manifest.browser.process_exit_code -eq 'unknown') {
    $manifest.phase = if ($ownedSandboxStarted) { 'completed_with_unknown_browser_exit' } else { 'execution_failed' }
  }
  elseif ($null -eq $manifest.failure) { $manifest.phase = 'completed' }
  $manifest.completed_at_utc = [DateTime]::UtcNow.ToString('o')
  try { Save-Manifest }
  catch {
    $finalSaveError = $_.Exception.Message
    $manifest.final_manifest_save_error = $finalSaveError
    $manifest.manifest_write_errors += "final save: $finalSaveError"
    try { Save-Manifest }
    catch {
      $retrySaveError = $_.Exception.Message
      $manifest.final_manifest_save_retry_error = $retrySaveError
      [Console]::Error.WriteLine("Final manifest save failed twice; first error: $finalSaveError; retry error: $retrySaveError")
    }
  }
}

if ($manifest.failure) {
  $failurePrefix = if ($WtsProcessSingletonDiagnosticOnly) { 'ProcessSingleton diagnostic stopped' } elseif ($WtsLoaderSnapsOnly) { 'Loader Snaps diagnostic stopped' } else { 'B2 coordinator stopped' }
  [Console]::Error.WriteLine("$failurePrefix at '$($manifest.failure.stage)': $($manifest.failure.message)")
  exit 12
}
if (-not $ownedSandboxStarted) { exit 10 }
if ($WtsProcessSingletonDiagnosticOnly) {
  $diagnosticIdentity = $manifest.process_singleton_diagnostic.identity
  $processSingletonDiagnosticComplete = (
    $manifest.guest_control.wsb_outer_exit_code -eq 0 -and
    $manifest.guest_control.guest_process_exit_code -eq 0 -and
    $manifest.guest_control.helper_exit_code -eq 0 -and
    $manifest.process_singleton_diagnostic.status -eq 'diagnostic_complete' -and
    $manifest.process_singleton_diagnostic.helper_exit_code_consistency -eq 'match' -and
    $manifest.process_singleton_diagnostic.helper_exit_code -eq 0 -and
    $manifest.process_singleton_diagnostic.probe_status -in @('pass','fail','unknown') -and
    $manifest.process_singleton_diagnostic.probe_report_path -ceq 'C:\b2\evidence\process-singleton-probe.json' -and
    $manifest.process_singleton_diagnostic.probe_report_bytes -gt 0 -and
    $manifest.process_singleton_diagnostic.probe_report_sha256 -match '^[0-9a-f]{64}$' -and
    [string]$manifest.process_tree.cleanup_status -like 'complete*' -and
    $manifest.process_tree.active_processes_after -eq 0 -and
    $diagnosticIdentity.target_session_is_interactive -eq $true -and
    $diagnosticIdentity.source_account_is_local -eq $true -and
    $diagnosticIdentity.final_token.status -eq 'pass' -and
    $diagnosticIdentity.final_token.readback_gate_pass -eq $true -and
    $diagnosticIdentity.final_token.token_elevation -eq $false -and
    [string]$diagnosticIdentity.final_token.integrity_level -eq 'medium' -and
    $diagnosticIdentity.final_token.checked_builtin_privileged_alias_enabled_groups_absent -eq $true -and
    [string]$manifest.browser.process_exit_code -eq 'not_run' -and
    [string]$manifest.page.status -like 'not_run*' -and
    $manifest.b2_acceptance -eq 'not_evaluated_diagnostic_only'
  )
  if (-not $processSingletonDiagnosticComplete) { exit 12 }
  if ($manifest.stop.wsb_outer_exit_code -ne 0 -or $manifest.post_stop_inventory.status -ne 'task-owned Sandbox absent') { exit 13 }
  Write-Output ("WTS ProcessSingleton diagnostic completed; probe status is '{0}'; B2 acceptance remains unevaluated." -f $manifest.process_singleton_diagnostic.probe_status)
  exit 20
}
if ($WtsDesktopAclDiagnosticOnly) {
  $finalTokenReadback = if (Test-JsonField $manifest.wts_medium_identity 'final_token') { $manifest.wts_medium_identity.final_token } else { $null }
  $baseNamedObjectsAccess = $manifest.desktop_access_check.base_named_objects_access_check
  $desktopAclDiagnosticComplete = (
    $manifest.guest_control.wsb_outer_exit_code -eq 0 -and
    $manifest.guest_control.guest_process_exit_code -eq 0 -and
    $manifest.guest_control.helper_exit_code -eq 0 -and
    [string]$manifest.desktop_access_check.status -in @('pass','denied') -and
    $manifest.desktop_access_check.probe_user_sid_matches_target -eq $true -and
    $manifest.desktop_access_check.probe_logon_sid_matches_target -eq $true -and
    $manifest.desktop_access_check.untrusted_dacl_hint_used -eq $false -and
    [string]$baseNamedObjectsAccess.status -in @('pass','denied') -and
    $baseNamedObjectsAccess.api_succeeded -eq $true -and
    [string]$baseNamedObjectsAccess.desired_access -eq '0x00000004' -and
    $baseNamedObjectsAccess.acl_mutated -eq $false -and
    $baseNamedObjectsAccess.target_process_started -eq $false -and
    $manifest.desktop_acl_hint.gating -eq $false -and
    $manifest.wts_medium_identity.target_session_is_interactive -eq $true -and
    $manifest.wts_medium_identity.source_account_is_local -eq $true -and
    $finalTokenReadback.status -eq 'pass' -and
    $finalTokenReadback.readback_gate_pass -eq $true -and
    $finalTokenReadback.token_elevation -eq $false -and
    [string]$finalTokenReadback.integrity_level -eq 'medium' -and
    $finalTokenReadback.checked_builtin_privileged_alias_enabled_groups_absent -eq $true -and
    [string]$manifest.browser.process_exit_code -eq 'not_run' -and
    [string]$manifest.page.status -like 'not_run*'
  )
  if (-not $desktopAclDiagnosticComplete) { exit 12 }
  if ($manifest.stop.wsb_outer_exit_code -ne 0 -or $manifest.post_stop_inventory.status -ne 'task-owned Sandbox absent') { exit 13 }
  $manifest.b2_acceptance = 'not_evaluated_diagnostic_only'
  Write-Output 'WTS desktop and BaseNamedObjects AccessCheck diagnostics completed; B2 acceptance remains unpassed and unevaluated.'
  exit 20
}
if ($WtsNativeControlOnly) {
  $finalTokenReadback = if (Test-JsonField $manifest.wts_medium_identity 'final_token') { $manifest.wts_medium_identity.final_token } else { $null }
  $wtsNativePass = (
    $manifest.guest_control.wsb_outer_exit_code -eq 0 -and
    $manifest.guest_control.guest_process_exit_code -eq 0 -and
    $manifest.guest_control.helper_exit_code -eq 0 -and
    $manifest.desktop_access_check.status -eq 'not_performed' -and
    $manifest.desktop_access_check.untrusted_dacl_hint_used -eq $false -and
    [string]$manifest.desktop_acl_hint.trust -eq 'untrusted guest-produced diagnostic' -and
    $manifest.desktop_acl_hint.gating -eq $false -and
    $manifest.wts_medium_identity.target_session_is_interactive -eq $true -and
    $manifest.wts_medium_identity.source_account_is_local -eq $true -and
    $finalTokenReadback.status -eq 'pass' -and
    $finalTokenReadback.readback_gate_pass -eq $true -and
    $finalTokenReadback.token_elevation -eq $false -and
    [string]$finalTokenReadback.integrity_level -eq 'medium' -and
    $finalTokenReadback.checked_builtin_privileged_alias_enabled_groups_absent -eq $true -and
    $manifest.native_diagnostic.status -eq 'pass' -and
    $manifest.native_diagnostic.root_exit_code -eq 0 -and
    $manifest.native_diagnostic.executable_sha256_matches_host -eq $true -and
    [string]$manifest.native_diagnostic.cleanup_status -like 'complete*' -and
    $manifest.native_diagnostic.active_processes_after -eq 0 -and
    $manifest.process_tree.active_processes_after -eq 0 -and
    [string]$manifest.browser.process_exit_code -eq 'not_run' -and
    [string]$manifest.page.status -like 'not_run*'
  )
  if (-not $wtsNativePass) { exit 12 }
  if ($manifest.stop.wsb_outer_exit_code -ne 0 -or $manifest.post_stop_inventory.status -ne 'task-owned Sandbox absent') { exit 13 }
  exit 0
}
if ($WtsLoaderSnapsOnly) {
  $finalTokenReadback = if (Test-JsonField $manifest.wts_medium_identity 'final_token') { $manifest.wts_medium_identity.final_token } else { $null }
  $loaderDiagnosticComplete = (
    $manifest.guest_control.wsb_outer_exit_code -eq 0 -and
    $manifest.guest_control.guest_process_exit_code -eq 0 -and
    $manifest.guest_control.helper_exit_code -eq 0 -and
    $manifest.loader_diagnostic.helper_exit_code_consistency -eq 'match' -and
    $manifest.loader_diagnostic.helper_exit_code_matches_report -eq $true -and
    $manifest.loader_diagnostic.helper_status -eq 'diagnostic_complete' -and
    $manifest.loader_diagnostic.status -eq 'diagnostic_complete' -and
    $manifest.loader_diagnostic.ifeo_restore_status -eq 'pass' -and
    [string]$manifest.process_tree.cleanup_status -like 'complete*' -and
    $manifest.process_tree.active_processes_after -eq 0 -and
    $manifest.wts_medium_identity.target_session_is_interactive -eq $true -and
    $manifest.wts_medium_identity.source_account_is_local -eq $true -and
    $finalTokenReadback.status -eq 'pass' -and
    $finalTokenReadback.readback_gate_pass -eq $true -and
    $finalTokenReadback.token_elevation -eq $false -and
    [string]$finalTokenReadback.integrity_level -eq 'medium' -and
    $finalTokenReadback.checked_builtin_privileged_alias_enabled_groups_absent -eq $true
  )
  if (-not $loaderDiagnosticComplete) { exit 12 }
  if ($manifest.stop.wsb_outer_exit_code -ne 0 -or $manifest.post_stop_inventory.status -ne 'task-owned Sandbox absent') { exit 13 }
  $manifest.b2_acceptance = 'not_evaluated_diagnostic_only'
  $manifest.loader_diagnostic.b2_pass = $false
  Write-Output 'Loader Snaps diagnostic completed; B2 acceptance remains unpassed and unevaluated.'
  exit 20
}
$nativeDiagnosticPass = $manifest.native_diagnostic.status -eq 'pass' -and $manifest.native_diagnostic.root_exit_code -eq 0 -and $manifest.native_diagnostic.executable_sha256_matches_host -eq $true
$nativeDiagnosticCleanupPass = [string]$manifest.native_diagnostic.cleanup_status -like 'complete*' -and $manifest.native_diagnostic.active_processes_after -eq 0
if ($manifest.guest_control.wsb_outer_exit_code -ne 0 -or $manifest.guest_control.guest_process_exit_code -ne 0 -or $manifest.guest_control.helper_exit_code -ne 0 -or -not $nativeDiagnosticPass -or -not $nativeDiagnosticCleanupPass -or $manifest.probe.status -ne 'pass' -or $manifest.probe.process_exit_code -ne 0 -or $manifest.browser.process_exit_code -ne 0 -or [string]$manifest.browser.timed_out -ne 'False' -or $manifest.page.status -notin @('pass','screenshot_created') -or $manifest.process_tree.cleanup_status -notlike 'complete*' -or $manifest.process_tree.active_processes_after -ne 0) { exit 12 }
if ($manifest.stop.wsb_outer_exit_code -ne 0 -or $manifest.post_stop_inventory.status -ne 'task-owned Sandbox absent') { exit 13 }
exit 0
