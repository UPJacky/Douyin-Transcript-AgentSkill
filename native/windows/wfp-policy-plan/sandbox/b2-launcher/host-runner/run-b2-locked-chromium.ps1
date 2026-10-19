param(
  [Parameter(Mandatory = $true)][string]$EvidencePath,
  [Parameter(Mandatory = $true)][string]$HelperPath,
  [string]$NativeDiagnosticPath,
  [Parameter(Mandatory = $true)][string]$WorkDirectory,
  [string]$ProbeScriptPath,
  [string]$DesktopAclEvidencePath,
  [string]$BrowserPath,
  [string]$TestPagePath,
  [ValidateRange(1, 120)][int]$TimeoutSeconds = 45,
  [switch]$WtsNativeControlOnly,
  [switch]$WtsDesktopAclDiagnosticOnly,
  [switch]$WtsLoaderSnapsOnly,
  [switch]$WtsProcessSingletonDiagnosticOnly,
  [string]$CdbPath,
  [string]$LoaderTargetPath,
  [string]$CdbSha256,
  [string]$LoaderTargetSha256,
  [string]$RunId
)

$ErrorActionPreference = 'Stop'
$reportPath = Join-Path $EvidencePath 'b2-observation.json'
$isWtsSessionDiagnostic = $WtsNativeControlOnly -or $WtsDesktopAclDiagnosticOnly -or $WtsLoaderSnapsOnly -or $WtsProcessSingletonDiagnosticOnly
$workRoot = Split-Path -Parent $WorkDirectory
$stdoutPath = Join-Path $workRoot 'b2-helper.stdout.log'
$stderrPath = Join-Path $workRoot 'b2-helper.stderr.log'
$helperProcess = $null
$helperExitCode = 'unknown'
$runnerStatusPath = $null
$runnerStage = 'runner_preflight'
$helperReportedExitCode = 'unknown'
$helperExitCodeMatchesReport = 'unknown'
$helperExitCodeConsistency = 'unknown'
$report = $null
$processSingletonDiagnosticComplete = $false
$helperTimedOut = $false
$launchError = $null
$reportPathReservedForRun = $false
$runnerClaimPath = Join-Path $EvidencePath 'runner-exclusive-claim.json'
$observedAtUtc = [DateTime]::UtcNow.ToString('o')

function Get-HelperExitCodeConsistency {
  param($ReportedExitCode, $ObservedExitCode)
  $parsedReportedExitCode = 0
  $parsedObservedExitCode = 0
  $reportedValid = $null -ne $ReportedExitCode -and [int]::TryParse([string]$ReportedExitCode, [ref]$parsedReportedExitCode)
  $observedValid = $null -ne $ObservedExitCode -and [int]::TryParse([string]$ObservedExitCode, [ref]$parsedObservedExitCode)
  $status = if (-not $reportedValid) { 'reported_code_missing_or_invalid' }
    elseif (-not $observedValid) { 'observed_code_unknown_or_invalid' }
    elseif ($parsedReportedExitCode -ne $parsedObservedExitCode) { 'mismatch' }
    else { 'match' }
  return [ordered]@{
    status = $status
    reported_exit_code = if ($reportedValid) { $parsedReportedExitCode } else { 'unknown' }
    observed_exit_code = if ($observedValid) { $parsedObservedExitCode } else { 'unknown' }
    reported_exit_code_raw = if ($null -eq $ReportedExitCode) { 'missing' } else { [string]$ReportedExitCode }
    observed_exit_code_raw = if ($null -eq $ObservedExitCode) { 'missing' } else { [string]$ObservedExitCode }
    matches = $reportedValid -and $observedValid -and $parsedReportedExitCode -eq $parsedObservedExitCode
  }
}

function Add-LoaderHelperExitCodeContract {
  param($Report, $ObservedExitCode)
  $reportedExitCodeValue = if ($Report.PSObject.Properties['helper_exit_code']) { $Report.helper_exit_code } else { $null }
  $contract = Get-HelperExitCodeConsistency -ReportedExitCode $reportedExitCodeValue -ObservedExitCode $ObservedExitCode
  $Report | Add-Member -NotePropertyName helper_exit_code_consistency -NotePropertyValue $contract -Force
  if ($contract.status -ne 'match') {
    $Report.status = 'fail'
    if (-not $Report.PSObject.Properties['failure'] -or $null -eq $Report.failure) {
      $Report | Add-Member -NotePropertyName failure -NotePropertyValue ([ordered]@{ stage = 'helper_exit_code_contract'; message = 'Reported and observed helper exit codes were missing, invalid, or inconsistent.' }) -Force
    }
  }
  return $contract
}

function Write-FallbackReport {
  param([string]$Stage, [string]$Message)
  $fallbackBrowser = if ($isWtsSessionDiagnostic) {
    [ordered]@{ process_id = $null; process_exit_code = 'not_run'; timed_out = 'not_run'; command_line = 'not_run'; status = if ($WtsProcessSingletonDiagnosticOnly) { 'not_run; WTS ProcessSingleton diagnostic-only mode' } else { 'not_run; WTS native-only control' } }
  }
  else {
    [ordered]@{ process_id = $null; process_exit_code = 'unknown'; timed_out = $false; command_line = 'unknown'; status = 'unknown' }
  }
  $fallbackPageStatus = if ($isWtsSessionDiagnostic) { 'not_run; WTS diagnostic-only mode' } else { 'unknown' }
  $fallback = [ordered]@{
    schema = if ($WtsProcessSingletonDiagnosticOnly) { 'b2-wts-process-singleton-observation/v1' } elseif ($WtsLoaderSnapsOnly) { 'b2-wts-loader-snaps-observation/v1' } else { 'b2-locked-chromium-observation/v2' }
    mode = if ($WtsProcessSingletonDiagnosticOnly) { 'b2-wts-process-singleton-diagnostic' } elseif ($WtsLoaderSnapsOnly) { 'b2-wts-loader-snaps' } elseif ($WtsDesktopAclDiagnosticOnly) { 'b2-wts-desktop-acl-diagnostic' } elseif ($WtsNativeControlOnly) { 'b2-wts-native-control' } else { 'b2' }
    status = if ($WtsProcessSingletonDiagnosticOnly -or $WtsLoaderSnapsOnly) { 'fail' } else { 'unknown' }
    run_id = if ($isWtsSessionDiagnostic) { $RunId } else { $null }
    observed_at_utc = [DateTime]::UtcNow.ToString('o')
    probe = if ($WtsProcessSingletonDiagnosticOnly) { [ordered]@{ status = 'unknown'; process_exit_code = 'unknown'; process_exit_code_hex = 'unknown'; timed_out = 'unknown'; report_path = 'C:\b2\evidence\process-singleton-probe.json'; report_bytes = 0; report_sha256 = 'unknown' } } else { [ordered]@{ status = 'unknown'; process_exit_code = 'unknown'; report_path = (Join-Path $EvidencePath 'process-singleton-probe.json') } }
    helper_exit_code = if ($WtsProcessSingletonDiagnosticOnly) { 'unknown' } else { $null }
    identity = if ($WtsProcessSingletonDiagnosticOnly) { $null } else { $null }
    desktop_access_check = if ($isWtsSessionDiagnostic) { [ordered]@{ status = 'not_performed'; reason = 'WTS diagnostic-only mode excludes untrusted guest DACL JSON.'; untrusted_dacl_hint_used = $false } } else { [ordered]@{ status = 'not_run'; evidence_path = $DesktopAclEvidencePath } }
    browser = $fallbackBrowser
    page = [ordered]@{ status = $fallbackPageStatus; screenshot_path = $null; screenshot_bytes = $null; screenshot_sha256 = $null }
    loader_diagnostic = $null
    ifeo = $null
    process_tree = [ordered]@{ cleanup_status = 'unknown'; active_processes_after = 'unknown'; observed_processes = @() }
    helper = [ordered]@{ exit_code = $helperExitCode; timed_out = $helperTimedOut; stdout_path = $stdoutPath; stderr_path = $stderrPath }
    failure = if ($WtsProcessSingletonDiagnosticOnly) { [ordered]@{ stage = $Stage; api = $null; win32_error = $null; error_type = 'DiagnosticWrapperFailure' } } else { [ordered]@{ stage = $Stage; win32_error = $null; message = $Message } }
  }
  $writeId = if ($isWtsSessionDiagnostic -and $RunId) { $RunId } else { [Guid]::NewGuid().ToString('D') }
  $temporaryPath = "$reportPath.$writeId.$([Guid]::NewGuid().ToString('N')).tmp"
  if (-not $WtsProcessSingletonDiagnosticOnly) {
    $fallback.Remove('helper_exit_code')
    $fallback.Remove('identity')
  }
  Write-NewUtf8File -Path $temporaryPath -Content ($fallback | ConvertTo-Json -Depth 12)
  if (Test-Path -LiteralPath $reportPath) { throw 'Refusing to replace an observation file while writing fallback evidence.' }
  [IO.File]::Move($temporaryPath, $reportPath)
}

function Write-NewUtf8File {
  param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Content)
  $bytes = [Text.UTF8Encoding]::new($false).GetBytes($Content)
  $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
  try {
    $stream.Write($bytes, 0, $bytes.Length)
    $stream.Flush()
  }
  finally { $stream.Dispose() }
}

function Write-WtsProcessSingletonRunnerStatus {
  if (-not $WtsProcessSingletonDiagnosticOnly -or [string]::IsNullOrWhiteSpace($runnerStatusPath) -or
      $null -eq $parsedRunId -or $parsedRunId -eq [Guid]::Empty) { return }
  $observedExitCode = 'unknown'
  $parsedExitCode = 0
  if ($null -ne $helperExitCode -and [int]::TryParse([string]$helperExitCode, [ref]$parsedExitCode)) {
    $observedExitCode = $parsedExitCode
  }
  elseif ($null -ne $helperProcess) {
    try {
      $helperProcess.Refresh()
      if ($helperProcess.HasExited) { $observedExitCode = [int]$helperProcess.ExitCode }
    }
    catch { }
  }
  $allowedStages = @('runner_preflight','helper_launch','helper_wait','helper_exit_observation',
    'helper_report_presence','helper_report_parse','helper_report_contract','helper_report_evidence',
    'runner_observation_write')
  $safeStage = if ($runnerStage -in $allowedStages) { $runnerStage } else { 'unknown' }
  $sidecar = [ordered]@{
    schema = 'b2-wts-process-singleton-runner-status/v1'
    mode = 'b2-wts-process-singleton-diagnostic'
    run_id = $parsedRunId.ToString('D')
    wrapper_stage = $safeStage
    wrapper_status = 'failed'
    helper_process_exit_code = $observedExitCode
    helper_timed_out = [bool]$helperTimedOut
  }
  Write-NewUtf8File -Path $runnerStatusPath -Content ($sidecar | ConvertTo-Json -Depth 3)
}

function Replace-FileWithPreservedBackup {
  param(
    [Parameter(Mandatory = $true)][string]$SourcePath,
    [Parameter(Mandatory = $true)][string]$DestinationPath,
    [Parameter(Mandatory = $true)][string]$RunLabel
  )
  if (-not (Test-Path -LiteralPath $SourcePath -PathType Leaf)) { throw 'Replacement source file is missing.' }
  if (-not (Test-Path -LiteralPath $DestinationPath -PathType Leaf)) { throw 'Replacement destination file is missing.' }
  $safeRunLabel = $RunLabel -replace '[^A-Za-z0-9_.-]', '_'
  $backupPath = "$DestinationPath.$safeRunLabel.$([Guid]::NewGuid().ToString('N')).preserved.bak"
  if (Test-Path -LiteralPath $backupPath) { throw 'Refusing to reuse a pre-existing replacement backup path.' }
  [IO.File]::Replace($SourcePath, $DestinationPath, $backupPath)
}

function Get-SafeEventQueryFailure {
  param([Parameter(Mandatory = $true)][System.Management.Automation.ErrorRecord]$ErrorRecord)

  $exception = $ErrorRecord.Exception
  $exceptionType = if ($exception) { $exception.GetType().Name } else { 'unknown' }
  if ($exceptionType -notmatch '^[A-Za-z_][A-Za-z0-9_]{0,127}$') { $exceptionType = 'OtherException' }

  $errorIdPrefix = ''
  if (-not [string]::IsNullOrWhiteSpace([string]$ErrorRecord.FullyQualifiedErrorId)) {
    $errorIdPrefix = ([string]$ErrorRecord.FullyQualifiedErrorId -split ',', 2)[0]
  }
  $errorIdClass = switch -CaseSensitive ($errorIdPrefix) {
    'NoMatchingEventsFound' { 'no_matching_events'; break }
    'EventLogNotFound' { 'event_log_not_found'; break }
    'LogNotFound' { 'event_log_not_found'; break }
    'UnauthorizedAccess' { 'access_denied'; break }
    'AccessDenied' { 'access_denied'; break }
    default { 'unclassified' }
  }

  $categoryName = 'Other'
  try {
    $candidateCategory = [string]$ErrorRecord.CategoryInfo.Category
    if ($candidateCategory -in @('PermissionDenied', 'ObjectNotFound', 'InvalidArgument', 'ResourceUnavailable', 'NotSpecified')) {
      $categoryName = $candidateCategory
    }
  }
  catch { }

  $exceptionHResult = $null
  if ($exception) {
    try { $exceptionHResult = [int]$exception.HResult } catch { }
  }
  $nativeErrorCode = $null
  if ($exception -and $null -ne $exception.PSObject.Properties['NativeErrorCode']) {
    try { $nativeErrorCode = [int]$exception.NativeErrorCode } catch { }
  }

  $failureCategory = if ($errorIdClass -ne 'unclassified') { $errorIdClass }
    elseif ($exception -is [System.UnauthorizedAccessException] -or $categoryName -eq 'PermissionDenied') { 'access_denied' }
    elseif ($exceptionType -in @('EventLogNotFoundException', 'EventLogNotFound')) { 'event_log_not_found' }
    else { 'query_error' }

  return [ordered]@{
    phase = 'Get-WinEvent'
    category = $failureCategory
    fully_qualified_error_id_class = $errorIdClass
    error_category = $categoryName
    exception_type = $exceptionType
    exception_hresult = $exceptionHResult
    native_error_code = $nativeErrorCode
    raw_message_stored = $false
    raw_fully_qualified_error_id_stored = $false
  }
}

function Get-WtsNativeFailureEventCorrelation {
  param(
    [Parameter(Mandatory = $true)]$Report,
    [Parameter(Mandatory = $true)][DateTime]$StartedAtUtc
  )

  $providerAllowlist = @('Application Error', 'Windows Error Reporting')
  $eventIdAllowlist = @(1000, 1001)
  $query = [ordered]@{
    status = 'unknown'
    query_status = 'not_started'
    log_names = @('Application')
    provider_allowlist = $providerAllowlist
    event_id_allowlist = $eventIdAllowlist
    system_log_status = 'not_queried; no System provider/event allowlist is configured'
    query_start_utc = $StartedAtUtc.AddSeconds(-5).ToString('o')
    query_end_utc = $null
    root_pid = $null
    expected_image_basename = 'native-desktop-probe.exe'
    matched_count = 0
    parse_failure_count = 0
    query_failure_diagnostic = $null
    raw_message_stored = $false
    raw_xml_stored = $false
    association_note = 'PID, image basename, and time-window correlation is not proof of causation.'
    events = @()
  }

  $rootPidValue = $null
  try {
    $native = $Report.native_diagnostic
    if ($null -eq $native -or $null -eq $native.root_pid) {
      $query.status = 'unknown'
      $query.query_status = 'root_pid_unavailable'
      return [pscustomobject]$query
    }
    $parsedPid = [uint32]0
    if (-not [uint32]::TryParse([string]$native.root_pid, [ref]$parsedPid) -or $parsedPid -eq 0) {
      $query.status = 'unknown'
      $query.query_status = 'root_pid_invalid'
      return [pscustomobject]$query
    }
    $rootPidValue = $parsedPid
    $query.root_pid = $rootPidValue

    $startLocal = $StartedAtUtc.AddSeconds(-5).ToLocalTime()
    $endLocal = [DateTime]::Now.AddSeconds(2)
    $query.query_end_utc = $endLocal.ToUniversalTime().ToString('o')
    $filter = @{
      LogName = 'Application'
      ProviderName = $providerAllowlist
      Id = $eventIdAllowlist
      StartTime = $startLocal
      EndTime = $endLocal
    }
    try {
      $records = @(Get-WinEvent -FilterHashtable $filter -MaxEvents 200 -ErrorAction Stop)
      $query.query_status = 'queried'
    }
    catch {
      $safeFailure = Get-SafeEventQueryFailure -ErrorRecord $_
      $query.query_failure_diagnostic = $safeFailure
      if (($safeFailure.category -eq 'no_matching_events') -or ($safeFailure.exception_type -in @('EventLogNoMatchingEventsException', 'NoMatchingEventsFound'))) {
        $records = @()
        $query.query_status = 'queried_no_events'
      }
      else {
        $query.status = 'unknown'
        $query.query_status = 'query_failed:' + $safeFailure.exception_type
        return [pscustomobject]$query
      }
    }

    $matchedEvents = [System.Collections.Generic.List[object]]::new()
    foreach ($record in $records) {
      if ($record.ProviderName -notin $providerAllowlist -or $record.Id -notin $eventIdAllowlist) { continue }
      try {
        [xml]$eventXml = $record.ToXml()
        $data = @{}
        foreach ($item in @($eventXml.Event.EventData.Data)) {
          if ($null -ne $item) {
            $fieldName = [string]$item.GetAttribute('Name')
            if (-not [string]::IsNullOrWhiteSpace($fieldName)) { $data[$fieldName] = [string]$item.InnerText }
          }
        }

        $pidText = $null
        foreach ($name in @('ProcessId', 'ProcessID', 'ApplicationProcessId')) {
          if ($data.ContainsKey($name) -and -not [string]::IsNullOrWhiteSpace($data[$name])) { $pidText = [string]$data[$name]; break }
        }
        $eventPid = $null
        if ($pidText -match '^0x([0-9a-fA-F]{1,8})$') {
          $eventPid = [Convert]::ToUInt32($Matches[1], 16)
        }
        elseif ($pidText -match '^\d{1,10}$') {
          $eventPid = [Convert]::ToUInt32($pidText, 10)
        }

        $imageValue = $null
        foreach ($name in @('AppName', 'ApplicationName', 'FaultingApplicationName', 'ProcessName', 'ImageName', 'AppPath', 'ApplicationPath')) {
          if ($data.ContainsKey($name) -and -not [string]::IsNullOrWhiteSpace($data[$name])) { $imageValue = [string]$data[$name]; break }
        }
        $imageBasename = $null
        if ($imageValue) { $imageBasename = [IO.Path]::GetFileName($imageValue.Trim().Trim('"')) }
        if ($null -eq $eventPid -or $eventPid -ne $rootPidValue -or -not [string]::Equals($imageBasename, 'native-desktop-probe.exe', [StringComparison]::OrdinalIgnoreCase)) {
          continue
        }

        $moduleValue = $null
        foreach ($name in @('ModuleName', 'FaultingModuleName', 'ModulePath', 'FaultingModulePath')) {
          if ($data.ContainsKey($name) -and -not [string]::IsNullOrWhiteSpace($data[$name])) { $moduleValue = [string]$data[$name]; break }
        }
        $moduleBasename = if ($moduleValue) { [IO.Path]::GetFileName($moduleValue.Trim().Trim('"')) } else { $null }
        if ($moduleBasename -and $moduleBasename -notmatch '^[A-Za-z0-9_.-]{1,128}$') { $moduleBasename = $null }

        $exceptionCode = $null
        foreach ($name in @('ExceptionCode', 'ExceptionStatus', 'FaultingExceptionCode')) {
          if ($data.ContainsKey($name) -and [string]$data[$name] -match '^(?:0x)?([0-9a-fA-F]{1,8})$') {
            $exceptionCode = '0x' + $Matches[1].ToUpperInvariant().PadLeft(8, '0')
            break
          }
        }
        $matchedEvents.Add([ordered]@{
          log_name = [string]$record.LogName
          provider = [string]$record.ProviderName
          event_id = [int]$record.Id
          time_created_utc = $record.TimeCreated.ToUniversalTime().ToString('o')
          process_id = [uint32]$eventPid
          image_basename = $imageBasename
          faulting_module_basename = $moduleBasename
          exception_code = $exceptionCode
          parse_status = 'matched_exact_pid_image_and_time_window'
        })
      }
      catch {
        $query.parse_failure_count = [int]$query.parse_failure_count + 1
      }
    }
    $query.events = $matchedEvents.ToArray()
    $query.matched_count = $matchedEvents.Count
    $query.status = if ($query.parse_failure_count -gt 0) { 'partial' } elseif ($matchedEvents.Count -gt 0) { 'matched' } else { 'not_found' }
    if ($query.query_status -eq 'queried' -and $records.Count -eq 0) { $query.query_status = 'queried_no_events' }
    return [pscustomobject]$query
  }
  catch {
    $query.status = 'unknown'
    $query.query_status = 'processing_failed:' + $_.Exception.GetType().Name
    return [pscustomobject]$query
  }
}

function Add-WtsNativeFailureEventCorrelation {
  if (-not $WtsNativeControlOnly -or -not $reportPathReservedForRun -or -not (Test-Path -LiteralPath $reportPath -PathType Leaf)) { return }
  if ($helperProcess -and -not $helperProcess.HasExited) {
    $pendingPath = Join-Path $EvidencePath "wts-event-correlation-$RunId.json"
    if (-not (Test-Path -LiteralPath $pendingPath)) {
      try {
        $pending = [ordered]@{ schema = 'wts-native-event-correlation-error/v1'; run_id = $RunId; status = 'unknown'; query_status = 'not_queried_helper_not_exited'; raw_message_stored = $false; raw_xml_stored = $false }
        Write-NewUtf8File -Path $pendingPath -Content ($pending | ConvertTo-Json -Depth 4)
      }
      catch { Write-Warning ('WTS event correlation status persistence failed; error_type=' + $_.Exception.GetType().Name) }
    }
    return
  }
  try {
    $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json -ErrorAction Stop
    if ([string]$report.run_id -ne [string]$RunId) { return }
    $correlation = Get-WtsNativeFailureEventCorrelation -Report $report -StartedAtUtc ([DateTime]::Parse($observedAtUtc).ToUniversalTime())
    $report | Add-Member -NotePropertyName native_failure_event_correlation -NotePropertyValue $correlation -Force
    $temporaryPath = "$reportPath.$($RunId).$([Guid]::NewGuid().ToString('N')).event.tmp"
    Write-NewUtf8File -Path $temporaryPath -Content ($report | ConvertTo-Json -Depth 18)
    $currentReport = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json -ErrorAction Stop
    if ([string]$currentReport.run_id -ne [string]$RunId) { throw 'Refusing to replace an observation file with a mismatched run_id.' }
    Replace-FileWithPreservedBackup -SourcePath $temporaryPath -DestinationPath $reportPath -RunLabel $RunId
  }
  catch {
    $sidecarPath = Join-Path $EvidencePath "wts-event-correlation-$RunId.json"
    if (-not (Test-Path -LiteralPath $sidecarPath)) {
      try {
        $failure = [ordered]@{
          schema = 'wts-native-event-correlation-error/v1'
          run_id = $RunId
          status = 'unknown'
          query_status = 'correlation_persistence_failed:' + $_.Exception.GetType().Name
          raw_message_stored = $false
          raw_xml_stored = $false
        }
        Write-NewUtf8File -Path $sidecarPath -Content ($failure | ConvertTo-Json -Depth 4)
      }
      catch { Write-Warning ('WTS event correlation persistence failed; error_type=' + $_.Exception.GetType().Name) }
    }
  }
}

function Test-SafeDiagnosticText {
  param([AllowNull()][string]$Value)
  if ([string]::IsNullOrWhiteSpace($Value) -or $Value.Length -gt 128) { return $false }
  if ($Value -match '(?i)\bS-\d-(?:\d+-){1,}\d+\b|(?:^|;)\s*(?:O|G|D|S):') { return $false }
  return $Value -match '^[A-Za-z0-9_.: -]+$'
}

function Copy-SafeDiagnosticFields {
  param($Source, [System.Collections.IDictionary]$Destination, [string[]]$Names)
  if ($null -eq $Source) { return }
  foreach ($name in $Names) {
    if (-not $Source.PSObject.Properties[$name]) { continue }
    $value = $Source.PSObject.Properties[$name].Value
    if ($null -eq $value) { continue }
    if ($value -is [bool]) { $Destination[$name] = $value; continue }
    $number = 0L
    if (($value -is [int] -or $value -is [long] -or $value -is [uint32] -or $value -is [uint64]) -and [long]::TryParse([string]$value, [ref]$number)) {
      $Destination[$name] = $number
      continue
    }
    if ($value -is [string] -and (Test-SafeDiagnosticText -Value $value)) { $Destination[$name] = $value }
  }
}

function Get-SafeWtsIdentityEvidence {
  param($Identity)
  if ($null -eq $Identity -or $Identity -isnot [System.Management.Automation.PSCustomObject]) { return $null }
  $safe = [ordered]@{}
  Copy-SafeDiagnosticFields $Identity $safe @('source','helper_is_local_system','requested_session_id','wts_session_1_active','target_session_is_interactive','target_session_id','source_account_is_local','profile_loaded_by_helper','profile_unloaded_by_helper','acl_mutated','source_account_verification')
  foreach ($nested in @(
      [ordered]@{ name = 'desktop'; fields = @('requested_lpDesktop','selection','acl_mutated') },
      [ordered]@{ name = 'token_filter'; fields = @('create_restricted_token_flags','sids_to_restrict_count','privileges_to_delete_count','administrators_deny_only','checked_builtin_privileged_alias_enabled_groups_absent','all_privileges_disabled_except_change_notify','token_is_restricted','token_is_restricted_expected') },
      [ordered]@{ name = 'final_token'; fields = @('status','session_id','token_type','token_elevation','integrity_level','users_group_enabled','administrators_group_deny_only','checked_builtin_privileged_alias_enabled_groups_absent','all_enabled_privileges_limited_to_change_notify','restricted_sid_list_count','token_is_restricted','same_user_and_logon_sid_as_wts_source','readback_gate_pass') },
      [ordered]@{ name = 'profile'; fields = @('hive_loaded','profile_loaded_by_helper','profile_unloaded_by_helper') },
      [ordered]@{ name = 'environment'; fields = @('created_from_existing_wts_token','userprofile_matches_token_profile','tmp_matches_temp','username_present','all_required_variables_present') }
    )) {
    if (-not $Identity.PSObject.Properties[$nested.name] -or $null -eq $Identity.PSObject.Properties[$nested.name].Value) { continue }
    $safeNested = [ordered]@{}
    Copy-SafeDiagnosticFields $Identity.PSObject.Properties[$nested.name].Value $safeNested $nested.fields
    $safe[$nested.name] = $safeNested
  }
  return $safe
}

function Get-SafeProcessTreeEvidence {
  param($ProcessTree)
  if ($null -eq $ProcessTree -or $ProcessTree -isnot [System.Management.Automation.PSCustomObject]) { return $null }
  $cleanupText = if ($ProcessTree.PSObject.Properties['cleanup_status']) { [string]$ProcessTree.cleanup_status } else { '' }
  $cleanup = if ($cleanupText -match '^(?i)complete(?:\b|$)') { 'complete' } elseif ($cleanupText -match '^(?i)fail(?:ed)?(?:\b|$)') { 'failed' } else { 'unknown' }
  $active = 'unknown'
  $activeNumber = 0L
  if ($ProcessTree.PSObject.Properties['active_processes_after'] -and [long]::TryParse([string]$ProcessTree.active_processes_after, [ref]$activeNumber) -and $activeNumber -ge 0) { $active = $activeNumber }
  $observations = @()
  $sourceObservations = if ($ProcessTree.PSObject.Properties['observations']) { @($ProcessTree.observations) } elseif ($ProcessTree.PSObject.Properties['observed_processes']) { @($ProcessTree.observed_processes) } else { @() }
  foreach ($item in $sourceObservations) {
    if ($null -eq $item) { continue }
    $safeItem = [ordered]@{}
    foreach ($numericName in @('process_id','parent_process_id','exit_code')) {
      if (-not $item.PSObject.Properties[$numericName]) { continue }
      $parsed = 0L
      if ([long]::TryParse([string]$item.PSObject.Properties[$numericName].Value, [ref]$parsed)) { $safeItem[$numericName] = $parsed }
    }
    foreach ($textName in @('image_basename','status')) {
      if ($item.PSObject.Properties[$textName] -and (Test-SafeDiagnosticText ([string]$item.PSObject.Properties[$textName].Value))) { $safeItem[$textName] = [string]$item.PSObject.Properties[$textName].Value }
    }
    if ($safeItem.Count -gt 0) { $observations += $safeItem }
  }
  return [ordered]@{ cleanup_status = $cleanup; active_processes_after = $active; observations = @($observations) }
}

function ConvertTo-SafeWin32Error {
  param($Value)
  if ($null -eq $Value -or $Value -is [bool]) { return $null }
  $errorNumber = 0L
  if ($Value -is [string]) {
    $errorText = [string]$Value
    if ($errorText -match '^[0-9]{1,10}$') {
      if (-not [long]::TryParse($errorText, [Globalization.NumberStyles]::None, [Globalization.CultureInfo]::InvariantCulture, [ref]$errorNumber)) { return $null }
    }
    elseif ($errorText -match '^0x[0-9A-Fa-f]{1,8}$') {
      if (-not [long]::TryParse($errorText.Substring(2), [Globalization.NumberStyles]::HexNumber, [Globalization.CultureInfo]::InvariantCulture, [ref]$errorNumber)) { return $null }
    }
    else { return $null }
  }
  elseif ($Value -is [int] -or $Value -is [long] -or $Value -is [uint32] -or $Value -is [uint64]) {
    if (-not [long]::TryParse([string]$Value, [Globalization.NumberStyles]::Integer, [Globalization.CultureInfo]::InvariantCulture, [ref]$errorNumber)) { return $null }
  }
  else { return $null }
  if ($errorNumber -lt 0 -or $errorNumber -gt [uint32]::MaxValue) { return $null }
  return $errorNumber
}

function Get-SafeDiagnosticFailure {
  param($Failure)
  if ($null -eq $Failure -or $Failure -isnot [System.Management.Automation.PSCustomObject]) { return $null }
  $safe = [ordered]@{}
  foreach ($name in @('stage','api')) {
    if ($Failure.PSObject.Properties[$name] -and (Test-SafeDiagnosticText ([string]$Failure.PSObject.Properties[$name].Value))) { $safe[$name] = [string]$Failure.PSObject.Properties[$name].Value }
  }
  $errorTypeProperty = $Failure.PSObject.Properties['error_type']
  if (-not $errorTypeProperty -or $null -eq $errorTypeProperty.Value) { $errorTypeProperty = $Failure.PSObject.Properties['exception_type'] }
  if ($errorTypeProperty -and (Test-SafeDiagnosticText ([string]$errorTypeProperty.Value))) { $safe.error_type = [string]$errorTypeProperty.Value }

  $errorProperty = $Failure.PSObject.Properties['win32_error']
  if (-not $errorProperty -or $null -eq $errorProperty.Value) { $errorProperty = $Failure.PSObject.Properties['error_code'] }
  if ($errorProperty) {
    $safeError = ConvertTo-SafeWin32Error $errorProperty.Value
    if ($null -ne $safeError) { $safe.win32_error = $safeError }
  }

  if ($Failure.PSObject.Properties['process_exit_code']) {
    $exitValue = $Failure.PSObject.Properties['process_exit_code'].Value
    $exitCode = 0
    if ($exitValue -isnot [bool] -and [int]::TryParse([string]$exitValue, [Globalization.NumberStyles]::Integer, [Globalization.CultureInfo]::InvariantCulture, [ref]$exitCode)) {
      $safe.process_exit_code = $exitCode
      $expectedExitHex = '0x' + [BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$exitCode), 0).ToString('X8', [Globalization.CultureInfo]::InvariantCulture)
      $rawExitHex = if ($Failure.PSObject.Properties['process_exit_code_hex']) { [string]$Failure.PSObject.Properties['process_exit_code_hex'].Value } else { $expectedExitHex }
      if ($rawExitHex -match '^0x[0-9A-Fa-f]{8}$' -and [string]::Equals($rawExitHex, $expectedExitHex, [StringComparison]::OrdinalIgnoreCase)) {
        $safe.process_exit_code_hex = $expectedExitHex
      }
    }
    elseif ([string]$exitValue -ceq 'unknown') {
      $safe.process_exit_code = 'unknown'
      if (-not $Failure.PSObject.Properties['process_exit_code_hex'] -or [string]$Failure.PSObject.Properties['process_exit_code_hex'].Value -ceq 'unknown') {
        $safe.process_exit_code_hex = 'unknown'
      }
    }
  }
  if ($Failure.PSObject.Properties['timed_out']) {
    $timeoutValue = $Failure.PSObject.Properties['timed_out'].Value
    if ($timeoutValue -is [bool]) { $safe.timed_out = $timeoutValue }
    elseif ($timeoutValue -is [string] -and $timeoutValue -ceq 'unknown') { $safe.timed_out = 'unknown' }
  }
  return $safe
}

try {
  $wtsModeCount = [int][bool]$WtsNativeControlOnly + [int][bool]$WtsDesktopAclDiagnosticOnly + [int][bool]$WtsLoaderSnapsOnly + [int][bool]$WtsProcessSingletonDiagnosticOnly
  if ($wtsModeCount -gt 1) { throw 'WTS diagnostic-only modes are mutually exclusive.' }
  if ($WtsLoaderSnapsOnly) {
    if ([string]::IsNullOrWhiteSpace($RunId)) { throw 'WTS Loader Snaps mode requires RunId.' }
    $parsedRunId = [Guid]::Empty
    if (-not [Guid]::TryParseExact($RunId, 'D', [ref]$parsedRunId) -or $parsedRunId -eq [Guid]::Empty) { throw 'WTS Loader Snaps RunId must be a non-empty D-format GUID.' }
    if ([string]::IsNullOrWhiteSpace($CdbPath) -or [string]::IsNullOrWhiteSpace($LoaderTargetPath)) { throw 'WTS Loader Snaps mode requires CdbPath and LoaderTargetPath.' }
    if ($CdbSha256 -notmatch '^[0-9a-fA-F]{64}$' -or $LoaderTargetSha256 -notmatch '^[0-9a-fA-F]{64}$') { throw 'WTS Loader Snaps mode requires valid CDB and target SHA-256 values.' }
    $reportPath = Join-Path $EvidencePath "loader-snaps-$($parsedRunId.ToString('D')).json"
  }
  if ($WtsProcessSingletonDiagnosticOnly) {
    if ([string]::IsNullOrWhiteSpace($RunId)) { throw 'WTS ProcessSingleton diagnostic mode requires RunId.' }
    $parsedRunId = [Guid]::Empty
    if (-not [Guid]::TryParseExact($RunId, 'D', [ref]$parsedRunId) -or $parsedRunId -eq [Guid]::Empty) { throw 'WTS ProcessSingleton diagnostic RunId must be a non-empty D-format GUID.' }
    $runnerStatusPath = Join-Path $EvidencePath "b2-runner-status-$($parsedRunId.ToString('D')).json"
  }
  $requiredPaths = @($EvidencePath, $HelperPath, $WorkDirectory)
  if (($WtsNativeControlOnly -or (-not $WtsLoaderSnapsOnly -and -not $WtsProcessSingletonDiagnosticOnly)) -and -not $WtsDesktopAclDiagnosticOnly) { $requiredPaths += $NativeDiagnosticPath }
  if (-not $isWtsSessionDiagnostic) {
    foreach ($required in @($ProbeScriptPath, $DesktopAclEvidencePath, $BrowserPath, $TestPagePath)) {
      if ([string]::IsNullOrWhiteSpace($required)) { throw 'Standard B2 mode requires probe, DACL diagnostic, browser, and test-page paths.' }
    }
    $requiredPaths += @($ProbeScriptPath, $DesktopAclEvidencePath, $BrowserPath, $TestPagePath)
  }
  if ($WtsLoaderSnapsOnly) { $requiredPaths += @($CdbPath, $LoaderTargetPath) }
  if ($WtsProcessSingletonDiagnosticOnly) {
    if ([string]::IsNullOrWhiteSpace($ProbeScriptPath)) { throw 'WTS ProcessSingleton diagnostic mode requires the copied probe script.' }
    $requiredPaths += $ProbeScriptPath
  }
  foreach ($required in $requiredPaths) {
    if (-not [IO.Path]::IsPathRooted($required)) { throw "Guest path must be absolute: $required" }
  }
  if ($WtsNativeControlOnly) {
    if ([string]::IsNullOrWhiteSpace($RunId)) { throw 'WTS native-only mode requires RunId.' }
    $parsedRunId = [Guid]::Empty
    if (-not [Guid]::TryParseExact($RunId, 'D', [ref]$parsedRunId) -or $parsedRunId -eq [Guid]::Empty) { throw 'WTS RunId must be a non-empty D-format GUID.' }
  }
  if ($WtsDesktopAclDiagnosticOnly) {
    if ([string]::IsNullOrWhiteSpace($RunId)) { throw 'WTS desktop ACL diagnostic mode requires RunId.' }
    $parsedRunId = [Guid]::Empty
    if (-not [Guid]::TryParseExact($RunId, 'D', [ref]$parsedRunId) -or $parsedRunId -eq [Guid]::Empty) { throw 'WTS desktop ACL diagnostic RunId must be a non-empty D-format GUID.' }
    foreach ($required in @($ProbeScriptPath, $DesktopAclEvidencePath)) {
      if ([string]::IsNullOrWhiteSpace($required)) { throw 'WTS desktop ACL diagnostic mode requires probe and evidence paths.' }
    }
    $requiredPaths += @($ProbeScriptPath, $DesktopAclEvidencePath)
  }
  if ($WtsLoaderSnapsOnly) {
    if ([IO.Path]::GetFileName($CdbPath) -ine 'cdb.exe' -or [IO.Path]::GetFileName($LoaderTargetPath) -ine 'exit-only-probe.exe') { throw 'WTS Loader Snaps mode requires cdb.exe and exit-only-probe.exe basenames.' }
    if (-not [string]::Equals((Get-FileHash -LiteralPath $CdbPath -Algorithm SHA256).Hash, $CdbSha256, [StringComparison]::OrdinalIgnoreCase)) { throw 'CDB SHA-256 does not match the host-validated value.' }
    if (-not [string]::Equals((Get-FileHash -LiteralPath $LoaderTargetPath -Algorithm SHA256).Hash, $LoaderTargetSha256, [StringComparison]::OrdinalIgnoreCase)) { throw 'Loader target SHA-256 does not match the host-validated value.' }
  }
  $helperAssemblyPath = Join-Path (Split-Path -Parent $HelperPath) 'LeaseProcessJobRunner.dll'
  $requiredFiles = @($HelperPath, $helperAssemblyPath)
  if (($WtsNativeControlOnly -or (-not $WtsLoaderSnapsOnly -and -not $WtsProcessSingletonDiagnosticOnly)) -and -not $WtsDesktopAclDiagnosticOnly) { $requiredFiles += $NativeDiagnosticPath }
  if (-not $isWtsSessionDiagnostic) { $requiredFiles += @($ProbeScriptPath, $DesktopAclEvidencePath, $BrowserPath, $TestPagePath) }
  if ($WtsDesktopAclDiagnosticOnly) { $requiredFiles += @($ProbeScriptPath, $DesktopAclEvidencePath) }
  if ($WtsLoaderSnapsOnly) { $requiredFiles += @($CdbPath, $LoaderTargetPath) }
  if ($WtsProcessSingletonDiagnosticOnly) { $requiredFiles += $ProbeScriptPath }
  foreach ($requiredFile in $requiredFiles) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) { throw "Required guest file does not exist: $requiredFile" }
  }
  if (-not (Test-Path -LiteralPath $EvidencePath -PathType Container)) { throw "Evidence directory does not exist: $EvidencePath" }
  $workDirectoryCanonical = [IO.Path]::GetFullPath($WorkDirectory).TrimEnd('\')
  $workRootCanonical = [IO.Path]::GetFullPath($workRoot).TrimEnd('\')
  if (-not [string]::Equals((Split-Path -Parent $workDirectoryCanonical), $workRootCanonical, [StringComparison]::OrdinalIgnoreCase)) { throw 'WorkDirectory must be one unique child beneath the guest C:\b2\work root.' }
  if ((Split-Path -Leaf $workDirectoryCanonical) -notmatch '^b2-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') { throw 'WorkDirectory leaf must be named b2-<run GUID>.' }
  if (-not (Test-Path -LiteralPath $workRootCanonical -PathType Container)) { New-Item -ItemType Directory -Path $workRootCanonical | Out-Null }
  if (Test-Path -LiteralPath $workDirectoryCanonical) { throw "Refusing to reuse an existing work leaf: $workDirectoryCanonical" }
  foreach ($logPath in @($stdoutPath, $stderrPath)) { if (Test-Path -LiteralPath $logPath) { throw "Refusing to overwrite an existing helper log: $logPath" } }
  if (Test-Path -LiteralPath $reportPath) { throw "Refusing to overwrite an existing observation file: $reportPath" }
  if ($WtsProcessSingletonDiagnosticOnly -and (Test-Path -LiteralPath $runnerStatusPath)) { throw 'Refusing to reuse a pre-existing WTS ProcessSingleton runner-status sidecar.' }
  if (Test-Path -LiteralPath $runnerClaimPath) { throw 'Refusing to reuse an existing runner-exclusive claim.' }
  $claimId = if ($isWtsSessionDiagnostic) { $parsedRunId.ToString('D') } else { [Guid]::NewGuid().ToString('D') }
  $claim = [ordered]@{ schema = 'b2-runner-exclusive-claim/v1'; run_id = $claimId; created_at_utc = [DateTime]::UtcNow.ToString('o') }
  Write-NewUtf8File -Path $runnerClaimPath -Content ($claim | ConvertTo-Json -Depth 3)
  if (Test-Path -LiteralPath $reportPath) { throw 'Observation file appeared while reserving this runner; preserving it.' }
  $reportPathReservedForRun = $true

  if ($WtsLoaderSnapsOnly) {
    $arguments = @(
      '--mode', 'b2-wts-loader-snaps',
      '--report-path', $reportPath,
      '--cdb-path', $CdbPath,
      '--loader-target-path', $LoaderTargetPath,
      '--cdb-sha256', $CdbSha256.ToLowerInvariant(),
      '--loader-target-sha256', $LoaderTargetSha256.ToLowerInvariant(),
      '--evidence-directory', $EvidencePath,
      '--run-id', $parsedRunId.ToString('D'),
      '--timeout-seconds', [string]$TimeoutSeconds
    )
  }
  elseif ($WtsProcessSingletonDiagnosticOnly) {
    $arguments = @(
      '--mode', 'b2-wts-process-singleton-diagnostic',
      '--report-path', $reportPath,
      '--probe-script', $ProbeScriptPath,
      '--evidence-directory', $EvidencePath,
      '--run-id', $parsedRunId.ToString('D'),
      '--timeout-seconds', [string]$TimeoutSeconds
    )
  }
  elseif ($WtsDesktopAclDiagnosticOnly) {
    $arguments = @(
      '--mode', 'b2-wts-desktop-acl-diagnostic',
      '--report-path', $reportPath,
      '--desktop-acl-evidence-path', $DesktopAclEvidencePath,
      '--evidence-directory', $EvidencePath,
      '--run-id', $parsedRunId.ToString('D'),
      '--timeout-seconds', [string]$TimeoutSeconds
    )
  }
  elseif ($WtsNativeControlOnly) {
    $arguments = @(
      '--mode', 'b2-wts-native-control',
      '--report-path', $reportPath,
      '--native-diagnostic-path', $NativeDiagnosticPath,
      '--evidence-directory', $EvidencePath,
      '--run-id', $parsedRunId.ToString('D'),
      '--timeout-seconds', [string]$TimeoutSeconds
    )
  }
  else {
    $arguments = @(
      '--mode', 'b2',
      '--report-path', $reportPath,
      '--probe-script', $ProbeScriptPath,
      '--desktop-acl-evidence-path', $DesktopAclEvidencePath,
      '--native-diagnostic-path', $NativeDiagnosticPath,
      '--profile-directory', (Join-Path $WorkDirectory 'profile'),
      '--browser-path', $BrowserPath,
      '--test-page', $TestPagePath,
      '--work-directory', $WorkDirectory,
      '--evidence-directory', $EvidencePath,
      '--timeout-seconds', [string]$TimeoutSeconds
    )
  }
  $runnerStage = 'helper_launch'
  $helperProcess = Start-Process -FilePath $HelperPath -ArgumentList $arguments -WorkingDirectory $workRootCanonical -WindowStyle Hidden -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
  $runnerStage = 'helper_wait'
  $boundedWaitSeconds = $TimeoutSeconds + 60
  if (-not $helperProcess.WaitForExit($boundedWaitSeconds * 1000)) {
    $helperTimedOut = $true
    Stop-Process -Id $helperProcess.Id -Force -ErrorAction Stop
    [void]$helperProcess.WaitForExit(5000)
    throw "B2 helper exceeded its $boundedWaitSeconds second host-side bound and was terminated. Job cleanup remains unknown unless the helper report proves it."
  }
  $helperProcess.Refresh()
  $helperExitCode = [int]$helperProcess.ExitCode
  $runnerStage = 'helper_exit_observation'
  $runnerStage = 'helper_report_presence'
  if (-not (Test-Path -LiteralPath $reportPath -PathType Leaf)) {
    throw "B2 helper exited with code $helperExitCode without writing its observation report."
  }
  $runnerStage = 'helper_report_parse'
  $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json -ErrorAction Stop
  $runnerStage = 'helper_report_contract'
  if (-not $WtsProcessSingletonDiagnosticOnly -and (-not $report.PSObject.Properties['browser'] -or -not $report.PSObject.Properties['process_tree'])) {
    throw 'B2 helper observation is missing required browser/process_tree objects.'
  }
  $expectedWtsMode = if ($WtsProcessSingletonDiagnosticOnly) { 'b2-wts-process-singleton-diagnostic' } elseif ($WtsLoaderSnapsOnly) { 'b2-wts-loader-snaps' } elseif ($WtsDesktopAclDiagnosticOnly) { 'b2-wts-desktop-acl-diagnostic' } else { 'b2-wts-native-control' }
  if ($isWtsSessionDiagnostic -and ([string]$report.run_id -ne [string]$parsedRunId.ToString('D') -or [string]$report.mode -ne $expectedWtsMode)) {
    throw 'WTS helper observation mode or run_id does not match the reserved attempt.'
  }
  if ($WtsProcessSingletonDiagnosticOnly -and ([string]$report.schema -ne 'b2-wts-process-singleton-observation/v1' -or [string]$report.status -notin @('diagnostic_complete','fail'))) { throw 'WTS ProcessSingleton observation schema or status is invalid.' }
  if ($WtsLoaderSnapsOnly -and ([string]$report.schema -ne 'b2-wts-loader-snaps-observation/v1' -or [string]$report.status -notin @('diagnostic_complete','fail'))) { throw 'WTS Loader Snaps observation schema or status is invalid.' }
  if ($WtsProcessSingletonDiagnosticOnly) {
    if (-not $report.PSObject.Properties['helper_exit_code'] -or -not $report.PSObject.Properties['probe'] -or -not $report.PSObject.Properties['process_tree'] -or -not $report.PSObject.Properties['identity']) {
      throw 'WTS ProcessSingleton report is missing the sanitized helper, probe, identity, or process-tree contract.'
    }
    $reportedProcessSingletonExit = 0
    if (-not [int]::TryParse([string]$report.helper_exit_code, [ref]$reportedProcessSingletonExit)) { throw 'WTS ProcessSingleton report helper_exit_code is invalid.' }
    $helperReportedExitCode = $reportedProcessSingletonExit
    $helperExitCodeMatchesReport = $reportedProcessSingletonExit -eq [int]$helperExitCode
    $helperExitCodeConsistency = if ($helperExitCodeMatchesReport) { 'match' } else { 'mismatch' }

    $probeSource = $report.probe
    if ($probeSource -isnot [System.Management.Automation.PSCustomObject]) { throw 'WTS ProcessSingleton probe summary is not an object.' }
    $probeStatus = [string]$probeSource.status
    if ($probeStatus -notin @('pass','fail','unknown')) { throw 'WTS ProcessSingleton probe status is invalid.' }
    $guestProbeReportPath = [string]$probeSource.report_path
    if ($guestProbeReportPath -cne 'C:\b2\evidence\process-singleton-probe.json') { throw 'WTS ProcessSingleton probe report path did not match the fixed evidence mapping.' }
    $reportedProbeBytes = 0L
    if (-not [long]::TryParse([string]$probeSource.report_bytes, [ref]$reportedProbeBytes) -or $reportedProbeBytes -lt 0 -or $reportedProbeBytes -gt 1048576) { throw 'WTS ProcessSingleton probe report_bytes is invalid.' }
    $reportedProbeHash = [string]$probeSource.report_sha256
    $probeTimedOut = $probeSource.timed_out
    if ($probeTimedOut -isnot [bool] -and -not ($probeTimedOut -is [string] -and $probeTimedOut -ceq 'unknown')) { throw 'WTS ProcessSingleton probe timed_out must be a JSON boolean or the literal unknown.' }
    $probeProcessExit = 'unknown'
    $parsedProbeExit = 0
    if ([int]::TryParse([string]$probeSource.process_exit_code, [ref]$parsedProbeExit)) { $probeProcessExit = $parsedProbeExit }
    elseif ([string]$probeSource.process_exit_code -ne 'unknown') { throw 'WTS ProcessSingleton probe process_exit_code is invalid.' }
    $reportedProbeExitHex = [string]$probeSource.process_exit_code_hex
    if ($probeProcessExit -is [int]) {
      $expectedProbeExitHex = '0x' + [BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$probeProcessExit), 0).ToString('X8', [Globalization.CultureInfo]::InvariantCulture)
      if ($reportedProbeExitHex -notmatch '^0x[0-9A-Fa-f]{8}$' -or -not [string]::Equals($reportedProbeExitHex, $expectedProbeExitHex, [StringComparison]::OrdinalIgnoreCase)) { throw 'WTS ProcessSingleton probe process_exit_code_hex is invalid or inconsistent.' }
      $probeProcessExitHex = $expectedProbeExitHex
    }
    else {
      if ($reportedProbeExitHex -cne 'unknown') { throw 'WTS ProcessSingleton probe process_exit_code_hex is invalid for an unknown exit code.' }
      $probeProcessExitHex = 'unknown'
    }

    $probeArtifactPath = Join-Path $EvidencePath 'process-singleton-probe.json'
    $probeArtifactValid = $false
    $actualProbeBytes = 0L
    $actualProbeHash = 'unknown'
    if (Test-Path -LiteralPath $probeArtifactPath -PathType Leaf) {
      $runnerStage = 'helper_report_evidence'
      $probeArtifact = Get-Item -LiteralPath $probeArtifactPath -ErrorAction Stop
      $actualProbeBytes = [long]$probeArtifact.Length
      $actualProbeHash = (Get-FileHash -LiteralPath $probeArtifactPath -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
      $probeArtifactValid = $actualProbeBytes -gt 0 -and $actualProbeBytes -le 1048576 -and $actualProbeBytes -eq $reportedProbeBytes -and $reportedProbeHash -match '^[0-9a-fA-F]{64}$' -and [string]::Equals($actualProbeHash, $reportedProbeHash, [StringComparison]::OrdinalIgnoreCase)
    }
    elseif ($reportedProbeBytes -eq 0 -and $reportedProbeHash -eq 'unknown' -and $probeStatus -eq 'unknown') {
      $probeArtifactValid = $true
    }

    $safeIdentity = Get-SafeWtsIdentityEvidence $report.identity
    $safeTree = Get-SafeProcessTreeEvidence $report.process_tree
    $safeFailure = Get-SafeDiagnosticFailure $report.failure
    $identityToken = if ($safeIdentity -and $safeIdentity.final_token) { $safeIdentity.final_token } else { $null }
    $identityGate = $safeIdentity -and
      $safeIdentity.target_session_is_interactive -eq $true -and
      $safeIdentity.source_account_is_local -eq $true -and
      $identityToken -and
      $identityToken.status -eq 'pass' -and
      $identityToken.readback_gate_pass -eq $true -and
      $identityToken.token_elevation -eq $false -and
      [string]$identityToken.integrity_level -eq 'medium' -and
      $identityToken.checked_builtin_privileged_alias_enabled_groups_absent -eq $true
    $treeDrained = $safeTree -and [string]$safeTree.cleanup_status -like 'complete*' -and $safeTree.active_processes_after -eq 0
    $completeStatus = [string]$report.status -eq 'diagnostic_complete'
    if ($reportedProcessSingletonExit -eq 0 -and (-not $completeStatus -or -not $treeDrained -or -not $probeArtifactValid -or -not $identityGate)) {
      throw 'WTS ProcessSingleton helper_exit_code=0 lacked a complete identity, evidence, and drained-Job contract.'
    }
    $processSingletonDiagnosticComplete = $completeStatus -and
      $reportedProcessSingletonExit -eq 0 -and
      $helperExitCode -eq 0 -and
      $helperExitCodeMatchesReport -eq $true -and
      $treeDrained -and $probeArtifactValid -and $identityGate
    $report = [ordered]@{
      schema = 'b2-wts-process-singleton-observation/v1'
      mode = 'b2-wts-process-singleton-diagnostic'
      status = if ($processSingletonDiagnosticComplete) { 'diagnostic_complete' } else { 'fail' }
      run_id = $parsedRunId.ToString('D')
      helper_exit_code = $reportedProcessSingletonExit
      identity = $safeIdentity
      probe = [ordered]@{
        status = $probeStatus
        process_exit_code = $probeProcessExit
        process_exit_code_hex = $probeProcessExitHex
        timed_out = $probeTimedOut
        report_path = 'C:\b2\evidence\process-singleton-probe.json'
        report_bytes = if ($probeArtifactValid) { $actualProbeBytes } else { 0 }
        report_sha256 = if ($probeArtifactValid -and $actualProbeBytes -gt 0) { $actualProbeHash } else { 'unknown' }
      }
      process_tree = $safeTree
      failure = $safeFailure
    }
  }
  if ($WtsLoaderSnapsOnly) {
    $helperExitContract = Add-LoaderHelperExitCodeContract -Report $report -ObservedExitCode $helperExitCode
    $helperReportedExitCode = $helperExitContract.reported_exit_code
    $helperExitCodeMatchesReport = $helperExitContract.matches
    $helperExitCodeConsistency = $helperExitContract.status
  }
  $helperEvidence = [ordered]@{
    exit_code = $helperExitCode
    timed_out = $false
    stdout_path = $stdoutPath
    stderr_path = $stderrPath
    observed_at_utc = $observedAtUtc
  }
  if ($WtsLoaderSnapsOnly) {
    $helperEvidence['reported_exit_code'] = $helperReportedExitCode
    $helperEvidence['exit_code_matches_report'] = $helperExitCodeMatchesReport
    $helperEvidence['exit_code_consistency'] = $helperExitCodeConsistency
  }
  if ($WtsProcessSingletonDiagnosticOnly) {
    $helperEvidence['reported_exit_code'] = $helperReportedExitCode
    $helperEvidence['exit_code_matches_report'] = $helperExitCodeMatchesReport
    $helperEvidence['exit_code_consistency'] = $helperExitCodeConsistency
  }
  if ($WtsProcessSingletonDiagnosticOnly) { $report['helper'] = $helperEvidence }
  else { $report | Add-Member -NotePropertyName helper -NotePropertyValue $helperEvidence -Force }
  $runnerStage = 'runner_observation_write'
  $temporaryPath = "$reportPath.$([Guid]::NewGuid().ToString('N')).tmp"
  Write-NewUtf8File -Path $temporaryPath -Content ($report | ConvertTo-Json -Depth 16)
  if ($isWtsSessionDiagnostic) {
    $currentReport = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json -ErrorAction Stop
    if ([string]$currentReport.run_id -ne [string]$parsedRunId.ToString('D')) { throw 'Refusing to replace an observation file with a mismatched run_id.' }
  }
  $replaceRunLabel = if ($isWtsSessionDiagnostic) { $parsedRunId.ToString('D') } else { [Guid]::NewGuid().ToString('D') }
  Replace-FileWithPreservedBackup -SourcePath $temporaryPath -DestinationPath $reportPath -RunLabel $replaceRunLabel
}
catch {
  $launchError = if ($WtsProcessSingletonDiagnosticOnly) { 'WTS ProcessSingleton diagnostic report contract did not complete.' } else { $_.Exception.Message }
  if ($helperExitCode -eq 'unknown' -and $helperProcess) {
    try {
      $helperProcess.Refresh()
      if ($helperProcess.HasExited) { $helperExitCode = [int]$helperProcess.ExitCode }
    }
    catch { }
  }
  if ($WtsProcessSingletonDiagnosticOnly) {
    try { Write-WtsProcessSingletonRunnerStatus }
    catch { $launchError = 'WTS ProcessSingleton diagnostic failed and its runner-status sidecar could not be created.' }
  }
  if (-not (Test-Path -LiteralPath $reportPath -PathType Leaf)) {
    if ($reportPathReservedForRun) {
      Write-FallbackReport -Stage $(if ($helperTimedOut) { 'helper_timeout' } else { 'helper_launch_or_report' }) -Message $launchError
    }
  }
  elseif (-not $reportPathReservedForRun) {
    $launchError = 'Refused to read or modify a pre-existing observation file.'
  }
  elseif ($WtsProcessSingletonDiagnosticOnly) {
    # Preserve helper-authored evidence without serializing unvalidated fields into a wrapper report.
  }
  else {
    try {
      $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json -ErrorAction Stop
      $expectedWtsMode = if ($WtsLoaderSnapsOnly) { 'b2-wts-loader-snaps' } elseif ($WtsDesktopAclDiagnosticOnly) { 'b2-wts-desktop-acl-diagnostic' } else { 'b2-wts-native-control' }
      if ($isWtsSessionDiagnostic -and ([string]$report.run_id -ne [string]$parsedRunId.ToString('D') -or [string]$report.mode -ne $expectedWtsMode)) {
        throw 'WTS report mode or run_id mismatch; preserving the report without modification.'
      }
      $report | Add-Member -NotePropertyName helper -NotePropertyValue ([ordered]@{ exit_code = $helperExitCode; timed_out = $helperTimedOut; stdout_path = $stdoutPath; stderr_path = $stderrPath; wrapper_error = $launchError }) -Force
      if ($helperTimedOut) { $report | Add-Member -NotePropertyName wrapper_cleanup_claim -NotePropertyValue 'unknown; helper process was force-terminated' -Force }
      $temporaryPath = "$reportPath.$([Guid]::NewGuid().ToString('N')).tmp"
      Write-NewUtf8File -Path $temporaryPath -Content ($report | ConvertTo-Json -Depth 16)
      if ($isWtsSessionDiagnostic) {
        $currentReport = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json -ErrorAction Stop
        if ([string]$currentReport.run_id -ne [string]$parsedRunId.ToString('D')) { throw 'Refusing to replace an observation file with a mismatched run_id.' }
      }
      $replaceRunLabel = if ($isWtsSessionDiagnostic) { $parsedRunId.ToString('D') } else { [Guid]::NewGuid().ToString('D') }
      Replace-FileWithPreservedBackup -SourcePath $temporaryPath -DestinationPath $reportPath -RunLabel $replaceRunLabel
    }
    catch {
      $rewriteErrorType = $_.Exception.GetType().Name
      $errorRunId = if ($isWtsSessionDiagnostic) { $parsedRunId.ToString('D') } else { [guid]::NewGuid().ToString('D') }
      $sidecarPath = Join-Path $EvidencePath "b2-runner-report-error-$errorRunId.json"
      if (-not (Test-Path -LiteralPath $sidecarPath)) {
        $rewriteFailure = [ordered]@{
          schema = 'b2-runner-report-error/v1'
          run_id = if ($isWtsSessionDiagnostic) { $errorRunId } else { $null }
          stage = 'helper_report_rewrite'
          helper_exit_code = $helperExitCode
          wrapper_error_type = $rewriteErrorType
          exception_message_stored = $false
        }
        Write-NewUtf8File -Path $sidecarPath -Content ($rewriteFailure | ConvertTo-Json -Depth 4)
      }
    }
  }
}
finally {
  Add-WtsNativeFailureEventCorrelation
  if ($helperProcess) { $helperProcess.Dispose() }
}

$helperReportFailed = $false
if ($WtsProcessSingletonDiagnosticOnly) {
  $helperReportFailed = -not $processSingletonDiagnosticComplete -or
    $helperExitCodeConsistency -ne 'match' -or
    $helperReportedExitCode -ne 0 -or
    $helperExitCodeMatchesReport -ne $true
}
elseif ($WtsLoaderSnapsOnly) {
  $helperReportFailed = $helperExitCodeConsistency -ne 'match' -or
    $helperReportedExitCode -ne 0 -or
    $helperExitCodeMatchesReport -ne $true -or
    [string]$report.status -ne 'diagnostic_complete'
}
elseif ($WtsDesktopAclDiagnosticOnly) {
  $baseNamedObjects = if ($report.desktop_access_check -and $report.desktop_access_check.PSObject.Properties['base_named_objects_access_check']) { $report.desktop_access_check.base_named_objects_access_check } else { $null }
  $baseNamedObjectsAccess = if ($baseNamedObjects -and $baseNamedObjects.PSObject.Properties['directory_create_object_access']) { $baseNamedObjects.directory_create_object_access } else { $null }
  $helperReportFailed = [string]$report.status -ne 'diagnostic_complete' -or
    [string]$report.mode -ne 'b2-wts-desktop-acl-diagnostic' -or
    [string]$report.run_id -ne [string]$parsedRunId.ToString('D') -or
    [int]$report.helper_exit_code -ne 0 -or
    [string]$report.desktop_access_check.status -notin @('pass','denied') -or
    $report.desktop_access_check.same_user_sid_as_target -ne $true -or
    $report.desktop_access_check.same_logon_sid_as_target -ne $true -or
    [string]$baseNamedObjects.status -notin @('pass','denied') -or
    $null -eq $baseNamedObjectsAccess -or
    $baseNamedObjectsAccess.api_succeeded -ne $true -or
    [string]$baseNamedObjectsAccess.desired_access -ne '0x00000004' -or
    $baseNamedObjects.acl_mutated -ne $false -or
    $baseNamedObjects.target_process_started -ne $false
}
if ($launchError -or $helperExitCode -eq 'unknown' -or $helperExitCode -ne 0 -or $helperReportFailed) { exit 43 }
exit 0
