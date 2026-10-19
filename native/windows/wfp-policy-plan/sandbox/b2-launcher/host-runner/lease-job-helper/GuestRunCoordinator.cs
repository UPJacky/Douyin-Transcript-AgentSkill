using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Security.Cryptography;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using DouyinTranscript.CapturePipe;
using Microsoft.Win32.SafeHandles;

namespace DouyinTranscript.LeaseJobHelper;

internal static class GuestRunCoordinator
{
    private const string ControlledDomMarker = "B2-CONTROLLED-PAGE-READY";
    private const int HelperSuccess = 0;
    private const int HelperFailure = 12;

    internal static Task<int> RunWtsDesktopAclDiagnosticAsync(HelperOptions options, JsonSerializerOptions jsonOptions)
    {
        Dictionary<string, object?> report = CreateInitialReport(options);
        report["mode"] = "b2-wts-desktop-acl-diagnostic";
        report["run_id"] = options.ExpectedRunId;
        report["browser"] = new Dictionary<string, object?>
        {
            ["process_id"] = null,
            ["process_exit_code"] = "not_run",
            ["timed_out"] = "not_run",
            ["status"] = "not_run; read-only WTS desktop ACL diagnostic",
        };
        report["page"] = new Dictionary<string, object?>
        {
            ["status"] = "not_run; read-only WTS desktop ACL diagnostic",
            ["dom_marker_found"] = false,
            ["screenshot_path"] = null,
        };
        WtsMediumIdentityContext? identity = null;
        TokenPrivilegeScope? privileges = null;
        int helperExitCode = HelperFailure;
        string stage = "preflight";
        try
        {
            ValidateWtsDesktopAclDiagnosticInputs(options);
            privileges = TokenPrivilegeScope.EnableWtsQueryUserTokenOnly();
            stage = "wts_identity_filter";
            identity = new WtsMediumIdentityContext();
            Dictionary<string, object?> identityReport = identity.Initialize();
            report["identity"] = identityReport;

            stage = "same_logon_station_desktop_access_check";
            Dictionary<string, object?> accessCheck = DesktopAccessCheck.EvaluateEvidence(
                options.DesktopAclEvidencePath!, options.EvidenceDirectory!, options.ExpectedRunId!, identity.Token,
                identity.UserSid, identity.LogonSid, identity.SessionId);
            accessCheck["evidence_trust"] = "guest-produced observation; run/session/object binding and reporter SID formats checked; reporter SID equality is recorded but not required; snapshot diagnostic only and never a launch gate";
            accessCheck["required_for_launcher"] = "explicit WinSta0\\Default full-access contract masks; no ACL was changed";
            report["desktop_access_check"] = accessCheck;
            report["status"] = "diagnostic_complete";
            helperExitCode = HelperSuccess;
        }
        catch (Exception exception)
        {
            report["status"] = "fail";
            report["failure"] = Failure(stage, exception);
            if (identity?.LastIdentityReport is not null) report["identity"] = identity.LastIdentityReport;
        }
        finally
        {
            if (identity is not null)
            {
                identity.Dispose();
                report["identity_cleanup"] = new Dictionary<string, object?>
                {
                    ["environment_status"] = identity.EnvironmentCleanupStatus,
                    ["token_handles_closed"] = identity.TokenHandlesClosed,
                    ["profile_unloaded"] = false,
                    ["profile_unload_not_attempted"] = true,
                    ["account_deleted"] = false,
                    ["account_deletion_not_applicable"] = true,
                };
                if (identity.EnvironmentCleanupStatus == "failed" || !identity.TokenHandlesClosed)
                {
                    report["status"] = "fail";
                    report["failure"] ??= Failure("identity_cleanup", new IOException("WTS identity environment/token cleanup was not confirmed."));
                    helperExitCode = HelperFailure;
                }
            }
            privileges?.Dispose();
            report["helper_exit_code"] = helperExitCode;
            report["completed_at_utc"] = DateTimeOffset.UtcNow;
            try { Program.WriteJson(options.ReportPath!, report, jsonOptions); }
            catch (Exception writeError)
            {
                Console.Error.WriteLine($"report-write:{writeError.GetType().Name}");
                helperExitCode = HelperFailure;
            }
        }
        return Task.FromResult(helperExitCode);
    }

    internal static async Task<int> RunWtsProcessSingletonDiagnosticAsync(
        HelperOptions options,
        JsonSerializerOptions jsonOptions)
    {
        string? evidencePath = options.EvidenceDirectory is null
            ? null
            : Path.Combine(options.EvidenceDirectory, "process-singleton-probe.json");
        var report = new Dictionary<string, object?>
        {
            ["schema"] = "b2-wts-process-singleton-observation/v1",
            ["mode"] = "b2-wts-process-singleton-diagnostic",
            ["run_id"] = options.ExpectedRunId,
            ["status"] = "pending",
            ["captured_at_utc"] = DateTimeOffset.UtcNow,
            ["identity"] = null,
            ["probe"] = new Dictionary<string, object?>
            {
                ["status"] = "unknown",
                ["process_exit_code"] = "unknown",
                ["process_exit_code_hex"] = "unknown",
                ["timed_out"] = false,
                ["report_path"] = evidencePath,
                ["report_bytes"] = 0,
                ["report_sha256"] = "unknown",
            },
            ["process_tree"] = new Dictionary<string, object?>
            {
                ["cleanup_status"] = "not_started",
                ["active_processes_after"] = null,
                ["observed_processes"] = Array.Empty<Dictionary<string, object?>>(),
            },
            ["work_area"] = null,
            ["scratch_cleanup"] = null,
            ["identity_cleanup"] = null,
            ["failure"] = null,
            ["helper_exit_code"] = null,
        };

        WtsMediumIdentityContext? identity = null;
        TokenPrivilegeScope? privileges = null;
        Dictionary<string, object?>? processObservation = null;
        bool jobDrained = false;
        bool probeReportCaptured = false;
        int helperExitCode = HelperFailure;
        string stage = "preflight";
        string? workDirectory = null;

        try
        {
            ValidateWtsProcessSingletonInputs(options);
            privileges = TokenPrivilegeScope.EnableWtsQueryUserTokenOnly();
            stage = "wts_identity_filter";
            identity = new WtsMediumIdentityContext();
            Dictionary<string, object?> identityReport = identity.Initialize();
            report["identity"] = CreateLoaderIdentityEvidence(identityReport);

            stage = "target_profile_temp_work_leaf";
            workDirectory = identity.CreateWorkDirectory();
            string scratchProfile = CreateWtsProcessSingletonScratchProfile(identity, workDirectory);
            report["work_area"] = new Dictionary<string, object?>
            {
                ["leaf_name"] = Path.GetFileName(workDirectory.TrimEnd('\\')),
                ["profile_leaf_name"] = Path.GetFileName(scratchProfile.TrimEnd('\\')),
                ["created_under_target_token"] = true,
                ["acl_mutated"] = false,
                ["profile_load_requested"] = false,
                ["purpose"] = "unique ProcessSingleton probe scratch profile and report staging",
            };

            string stagedProbeReport = Path.Combine(workDirectory, "process-singleton-probe.json");
            string powershellPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),
                "WindowsPowerShell", "v1.0", "powershell.exe");
            string[] arguments =
            [
                "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", options.ProbeScript!,
                "-ProfileDirectory", scratchProfile,
                "-OutputPath", stagedProbeReport,
                "-ExpectedUserSid", identity.UserSid,
                "-ExpectedSessionId", identity.SessionId.ToString(System.Globalization.CultureInfo.InvariantCulture),
            ];

            stage = "process_singleton_probe";
            processObservation = await RunSupervisedProcessAsync(identity, workDirectory, powershellPath, arguments,
                options.TimeoutSeconds, TargetProcessLauncher.InteractiveDefaultDesktop).ConfigureAwait(false);
            jobDrained = processObservation.GetValueOrDefault("cleanup_complete") is true
                && processObservation.GetValueOrDefault("active_processes_after") is uint activeAfter && activeAfter == 0;
            report["process_tree"] = CreateWtsProcessSingletonProcessTree(processObservation, identity.UserSid);
            Dictionary<string, object?> probe = (Dictionary<string, object?>)report["probe"]!;
            int? processExitCode = processObservation.GetValueOrDefault("process_exit_code") is int observedExitCode
                ? observedExitCode
                : null;
            bool? processTimedOut = processObservation.GetValueOrDefault("timed_out") is bool observedTimedOut
                ? observedTimedOut
                : null;
            Dictionary<string, object?>? processFailure = processObservation.GetValueOrDefault("failure")
                as Dictionary<string, object?>;
            probe["process_exit_code"] = processExitCode is int knownExitCode ? knownExitCode : "unknown";
            probe["process_exit_code_hex"] = processExitCode is int codeForHex
                ? FormatWtsProcessExitCodeHex(codeForHex)
                : "unknown";
            probe["timed_out"] = processTimedOut is bool knownTimeout ? knownTimeout : "unknown";

            string? processOutcomeFailureStage = ClassifyWtsProcessSingletonProcessFailureStage(
                processTimedOut, processExitCode);
            if (processOutcomeFailureStage is not null)
            {
                stage = processOutcomeFailureStage;
                report["failure"] = CreateWtsProcessSingletonProcessOutcomeFailure(
                    processOutcomeFailureStage, processTimedOut, processExitCode, processFailure);
            }
            else if (processFailure is not null)
            {
                stage = "process_supervision";
                report["failure"] = CreateWtsProcessSingletonObservationFailure(processFailure);
            }

            if (stage == "process_singleton_probe" || stage == "process_supervision")
            {
                stage = "process_singleton_report_capture";
            }
            if (jobDrained && File.Exists(stagedProbeReport))
            {
                byte[] rawReport = ReadAndValidateWtsProcessSingletonProbeReport(stagedProbeReport, out string probeStatus);
                (long copiedBytes, string copiedHash) = CopyWtsProcessSingletonEvidenceCreateNew(rawReport, evidencePath!);
                probe["status"] = probeStatus;
                probe["report_bytes"] = copiedBytes;
                probe["report_sha256"] = copiedHash;
                probeReportCaptured = true;
            }

            if (!jobDrained)
            {
                stage = "process_job_drain";
                throw new NativeApiException("WtsProcessSingleton.JobDrainNotConfirmed", NativeMethods.ErrorAccessDenied);
            }
            if (!probeReportCaptured)
            {
                stage = ClassifyWtsProcessSingletonReportFailureStage(
                    processTimedOut, processExitCode, probeReportCaptured)
                    ?? processOutcomeFailureStage
                    ?? "process_supervision";
                throw new InvalidDataException("Probe report was not captured.");
            }
            if (report["failure"] is not null)
            {
                stage = report["failure"] is Dictionary<string, object?> existingFailure
                    && existingFailure.GetValueOrDefault("stage") is string failureStage
                    ? failureStage
                    : "process_supervision";
                throw new InvalidOperationException("Process supervision reported a failure.");
            }

            report["status"] = "diagnostic_complete";
            helperExitCode = HelperSuccess;
        }
        catch (Exception exception)
        {
            report["status"] = "fail";
            report["failure"] ??= CreateWtsProcessSingletonFailure(stage, exception);
            if (identity?.LastIdentityReport is not null)
            {
                report["identity"] = CreateLoaderIdentityEvidence(identity.LastIdentityReport);
            }
            if (processObservation is not null)
            {
                report["process_tree"] = CreateWtsProcessSingletonProcessTree(processObservation, identity?.UserSid);
                Dictionary<string, object?> probe = (Dictionary<string, object?>)report["probe"]!;
                probe["process_exit_code"] = processObservation.GetValueOrDefault("process_exit_code");
                probe["timed_out"] = processObservation.GetValueOrDefault("timed_out");
            }
        }
        finally
        {
            if (identity is not null)
            {
                try
                {
                    Dictionary<string, object?> scratch = identity.CleanupWorkDirectory(jobDrained);
                    scratch.Remove("path");
                    scratch["leaf_name"] = identity.WorkDirectory is null
                        ? null
                        : Path.GetFileName(identity.WorkDirectory.TrimEnd('\\'));
                    report["scratch_cleanup"] = scratch;
                    if (workDirectory is not null && jobDrained && scratch.GetValueOrDefault("removed") is not true)
                    {
                        report["status"] = "fail";
                        report["failure"] ??= CreateWtsProcessSingletonFailure("scratch_cleanup",
                            new IOException("Scratch cleanup was not confirmed."));
                        helperExitCode = HelperFailure;
                    }
                }
                catch (Exception cleanupError)
                {
                    report["scratch_cleanup"] = new Dictionary<string, object?>
                    {
                        ["status"] = "failed",
                        ["exception_type"] = cleanupError.GetType().Name,
                        ["deferred_to_sandbox_teardown"] = !jobDrained,
                    };
                    report["status"] = "fail";
                    report["failure"] ??= CreateWtsProcessSingletonFailure("scratch_cleanup", cleanupError);
                    helperExitCode = HelperFailure;
                }

                identity.Dispose();
                report["identity_cleanup"] = new Dictionary<string, object?>
                {
                    ["environment_status"] = identity.EnvironmentCleanupStatus,
                    ["token_handles_closed"] = identity.TokenHandlesClosed,
                    ["profile_unloaded"] = false,
                    ["profile_unload_not_attempted"] = true,
                    ["acl_mutated"] = false,
                };
                if (identity.EnvironmentCleanupStatus == "failed" || !identity.TokenHandlesClosed)
                {
                    report["status"] = "fail";
                    report["failure"] ??= CreateWtsProcessSingletonFailure("identity_cleanup",
                        new IOException("WTS identity cleanup was not confirmed."));
                    helperExitCode = HelperFailure;
                }
            }
            privileges?.Dispose();
            if (report["status"] as string != "diagnostic_complete") helperExitCode = HelperFailure;
            report["helper_exit_code"] = helperExitCode;
            report["completed_at_utc"] = DateTimeOffset.UtcNow;
            try { Program.WriteJson(options.ReportPath!, report, jsonOptions); }
            catch (Exception writeError)
            {
                Console.Error.WriteLine($"report-write:{writeError.GetType().Name}");
                helperExitCode = HelperFailure;
            }
        }
        return helperExitCode;
    }

    private static void ValidateWtsProcessSingletonInputs(HelperOptions options)
    {
        if (!OperatingSystem.IsWindows()) throw new PlatformNotSupportedException("This helper requires Windows.");
        if (options.ReportPath is null || options.ProbeScript is null || options.EvidenceDirectory is null
            || options.ExpectedRunId is null)
        {
            throw new ArgumentException("Required WTS ProcessSingleton inputs are missing.");
        }
        if (!Guid.TryParseExact(options.ExpectedRunId, "D", out Guid runId) || runId == Guid.Empty)
        {
            throw new NativeApiException("WtsProcessSingleton.RunId.Invalid", NativeMethods.ErrorAccessDenied);
        }
        if (File.Exists(options.ReportPath) || Directory.Exists(options.ReportPath))
        {
            throw new NativeApiException("WtsProcessSingleton.ReportPath.MustBeNew", NativeMethods.ErrorAlreadyExists);
        }
        if (!Directory.Exists(options.EvidenceDirectory)
            || !string.Equals(Path.GetDirectoryName(Path.GetFullPath(options.ReportPath))?.TrimEnd('\\'),
                Path.GetFullPath(options.EvidenceDirectory).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase))
        {
            throw new NativeApiException("WtsProcessSingleton.ReportPath.MustBeInEvidenceDirectory", NativeMethods.ErrorAccessDenied);
        }
        string evidencePath = Path.Combine(options.EvidenceDirectory, "process-singleton-probe.json");
        if (File.Exists(evidencePath) || Directory.Exists(evidencePath))
        {
            throw new NativeApiException("WtsProcessSingleton.EvidencePath.MustBeNew", NativeMethods.ErrorAlreadyExists);
        }

        string helperDirectory = Path.GetDirectoryName(Environment.ProcessPath)
            ?? throw new InvalidOperationException("The helper path has no directory.");
        string runnerDirectory = Directory.GetParent(helperDirectory)?.FullName
            ?? throw new NativeApiException("WtsProcessSingleton.RunnerDirectory.Missing", NativeMethods.ErrorAccessDenied);
        string expectedProbe = Path.Combine(runnerDirectory, "ProcessSingletonApiProbe.ps1");
        if (!string.Equals(Path.GetFullPath(options.ProbeScript), expectedProbe, StringComparison.OrdinalIgnoreCase)
            || !File.Exists(expectedProbe))
        {
            throw new NativeApiException("WtsProcessSingleton.ProbeMustBeMappedRunnerSibling", NativeMethods.ErrorAccessDenied);
        }
    }

    private static string CreateWtsProcessSingletonScratchProfile(WtsMediumIdentityContext identity, string workDirectory)
    {
        string profileDirectory = Path.Combine(workDirectory, "profile-" + Guid.NewGuid().ToString("N"));
        if (File.Exists(profileDirectory) || Directory.Exists(profileDirectory))
        {
            throw new NativeApiException("WtsProcessSingleton.ProfilePath.MustBeNew", NativeMethods.ErrorAlreadyExists);
        }
        WindowsIdentity.RunImpersonated(identity.Token, () => { Directory.CreateDirectory(profileDirectory); });
        if (!Directory.Exists(profileDirectory)
            || (File.GetAttributes(profileDirectory) & FileAttributes.ReparsePoint) != 0)
        {
            throw new NativeApiException("WtsProcessSingleton.ProfilePath.Invalid", NativeMethods.ErrorAccessDenied);
        }
        return profileDirectory;
    }

    private static byte[] ReadAndValidateWtsProcessSingletonProbeReport(string path, out string probeStatus)
    {
        const int maximumReportBytes = 1024 * 1024;
        var file = new FileInfo(path);
        if (!file.Exists || file.Length is <= 0 or > maximumReportBytes)
        {
            throw new InvalidDataException("Probe report size was outside the accepted bound.");
        }
        byte[] bytes = File.ReadAllBytes(path);
        if (bytes.Length is <= 0 or > maximumReportBytes)
        {
            throw new InvalidDataException("Probe report size changed outside the accepted bound.");
        }

        using JsonDocument document = JsonDocument.Parse(bytes, new JsonDocumentOptions { MaxDepth = 16 });
        if (document.RootElement.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidDataException("Probe report was not a JSON object.");
        }
        ValidateWtsProcessSingletonJson(document.RootElement);
        if (!document.RootElement.TryGetProperty("reportKind", out JsonElement reportKind)
            || reportKind.ValueKind != JsonValueKind.String
            || reportKind.GetString() != "chromium-process-singleton-api-probe")
        {
            throw new InvalidDataException("Probe report kind was not recognized.");
        }
        JsonElement statusElement = document.RootElement.GetProperty("status");
        string? rawStatus = statusElement.ValueKind == JsonValueKind.String ? statusElement.GetString() : null;
        probeStatus = rawStatus is "pass" or "fail" ? rawStatus : "unknown";
        return bytes;
    }

    private static void ValidateWtsProcessSingletonJson(JsonElement element)
    {
        switch (element.ValueKind)
        {
            case JsonValueKind.Object:
                foreach (JsonProperty property in element.EnumerateObject())
                {
                    string normalized = property.Name.Replace("_", string.Empty, StringComparison.Ordinal)
                        .Replace("-", string.Empty, StringComparison.Ordinal).ToLowerInvariant();
                    if (normalized is "usersid" or "expectedusersid" or "logonsid" or "ownersid"
                        or "integritysid" or "sddl" or "daclsummary" or "commandline" or "transcript"
                        or "cmdline" or "stdout" or "stderr" or "output" or "logs")
                    {
                        throw new InvalidDataException("Probe report contained a disallowed identity or output field.");
                    }
                    ValidateWtsProcessSingletonJson(property.Value);
                }
                break;
            case JsonValueKind.Array:
                foreach (JsonElement item in element.EnumerateArray()) ValidateWtsProcessSingletonJson(item);
                break;
            case JsonValueKind.String:
                string value = element.GetString() ?? string.Empty;
                if (Regex.IsMatch(value, @"(?i)\bS-\d-\d+(?:-\d+)+\b")
                    || Regex.IsMatch(value, @"(?i)\b[OGDS]:(?:P|AI|AR|NO_ACCESS_CONTROL)?(?:AI|AR)?\([^)]*;;"))
                {
                    throw new InvalidDataException("Probe report contained serialized SID or SDDL data.");
                }
                break;
        }
    }

    private static (long Bytes, string Sha256) CopyWtsProcessSingletonEvidenceCreateNew(byte[] bytes, string destination)
    {
        using (var output = new FileStream(destination, FileMode.CreateNew, FileAccess.Write, FileShare.None))
        {
            output.Write(bytes, 0, bytes.Length);
            output.Flush(flushToDisk: true);
        }
        string sha256 = HashFile(destination, out long copiedBytes);
        if (copiedBytes != bytes.LongLength)
        {
            throw new InvalidDataException("Evidence copy size did not match the validated probe report.");
        }
        return (copiedBytes, sha256);
    }

    private static Dictionary<string, object?> CreateWtsProcessSingletonProcessTree(
        Dictionary<string, object?> observation,
        string? expectedUserSid)
    {
        var safeProcesses = new List<Dictionary<string, object?>>();
        if (observation.GetValueOrDefault("observed_processes") is List<Dictionary<string, object?>> processes)
        {
            foreach (Dictionary<string, object?> process in processes)
            {
                var safe = new Dictionary<string, object?>();
                CopyFields(process, safe, "pid", "parent_pid", "parent_pid_source", "image_name", "session_id",
                    "integrity_level", "token_is_elevated", "not_elevated", "job_member", "exited", "query_status", "win32_error");
                safe["sid_matches_target"] = expectedUserSid is not null
                    && string.Equals(process.GetValueOrDefault("sid") as string, expectedUserSid, StringComparison.Ordinal);
                safeProcesses.Add(safe);
            }
        }
        return new Dictionary<string, object?>
        {
            ["cleanup_status"] = observation.GetValueOrDefault("cleanup_status"),
            ["active_processes_after"] = observation.GetValueOrDefault("active_processes_after"),
            ["observed_processes"] = safeProcesses,
        };
    }

    private static Dictionary<string, object?> CreateWtsProcessSingletonFailure(string stage, Exception exception)
    {
        NativeApiException? native = FindNativeApiException(exception);
        return new Dictionary<string, object?>
        {
            ["stage"] = stage,
            ["api"] = native?.Api,
            ["win32_error"] = GetNonNegativeWin32ErrorCode(native?.ErrorCode
                ?? (exception is System.ComponentModel.Win32Exception win32 ? win32.NativeErrorCode : null)),
            ["error_type"] = exception.GetType().Name,
        };
    }

    private static Dictionary<string, object?> CreateWtsProcessSingletonObservationFailure(
        Dictionary<string, object?> observationFailure)
    {
        return new Dictionary<string, object?>
        {
            ["stage"] = "process_supervision",
            ["api"] = ReadSafeFailureText(observationFailure, "api"),
            ["win32_error"] = ReadFailureErrorCode(observationFailure),
            ["error_type"] = ReadSafeFailureText(observationFailure, "error_type", "exception_type"),
        };
    }

    private static Dictionary<string, object?> CreateWtsProcessSingletonProcessOutcomeFailure(
        string stage,
        bool? timedOut,
        int? processExitCode,
        Dictionary<string, object?>? observationFailure)
    {
        Dictionary<string, object?>? supervisionFailure = observationFailure is null
            ? null
            : CreateWtsProcessSingletonObservationFailure(observationFailure);
        string errorType = stage switch
        {
            "process_singleton_probe_timeout" => "ProcessTimedOut",
            "process_singleton_probe_completion_unknown" => "ProcessCompletionUnknown",
            "process_singleton_probe_exit_unknown" => "ProcessExitCodeUnknown",
            _ => "ProcessExitedNonZero",
        };
        var failure = new Dictionary<string, object?>
        {
            ["stage"] = stage,
            ["api"] = supervisionFailure?.GetValueOrDefault("api"),
            ["win32_error"] = supervisionFailure?.GetValueOrDefault("win32_error"),
            ["error_type"] = errorType,
            ["process_exit_code"] = processExitCode is int exitCode ? exitCode : "unknown",
            ["process_exit_code_hex"] = processExitCode is int codeForHex
                ? FormatWtsProcessExitCodeHex(codeForHex)
                : "unknown",
            ["timed_out"] = timedOut is bool knownTimeout ? knownTimeout : "unknown",
        };
        return failure;
    }

    private static string? ClassifyWtsProcessSingletonProcessFailureStage(bool? timedOut, int? processExitCode)
    {
        if (timedOut is true) return "process_singleton_probe_timeout";
        if (timedOut is not false) return "process_singleton_probe_completion_unknown";
        if (processExitCode is not int exitCode) return "process_singleton_probe_exit_unknown";
        return exitCode == 0 ? null : "process_singleton_probe_exit_nonzero";
    }

    private static string? ClassifyWtsProcessSingletonReportFailureStage(
        bool? timedOut, int? processExitCode, bool reportCaptured)
    {
        return ClassifyWtsProcessSingletonProcessFailureStage(timedOut, processExitCode)
            ?? (reportCaptured ? null : "process_singleton_report_capture");
    }

    private static string FormatWtsProcessExitCodeHex(int exitCode) => FormatProcessExitCodeHex(exitCode);

    private static object? GetNonNegativeWin32ErrorCode(int? errorCode) =>
        errorCode is >= 0 ? errorCode.Value : null;

    private static object? ReadFailureErrorCode(IReadOnlyDictionary<string, object?> failure)
    {
        object? raw = failure.GetValueOrDefault("win32_error") ?? failure.GetValueOrDefault("error_code");
        switch (raw)
        {
            case int intCode when intCode >= 0:
                return intCode;
            case uint uintCode:
                return (long)uintCode;
            case long longCode when longCode is >= 0 and <= uint.MaxValue:
                return longCode;
            case JsonElement jsonCode when jsonCode.TryGetUInt32(out uint jsonNumber):
                return (long)jsonNumber;
            case string decimalText when uint.TryParse(decimalText, System.Globalization.NumberStyles.None,
                System.Globalization.CultureInfo.InvariantCulture, out uint decimalNumber):
                return (long)decimalNumber;
            case string hexText when hexText.StartsWith("0x", StringComparison.OrdinalIgnoreCase)
                && uint.TryParse(hexText.AsSpan(2), System.Globalization.NumberStyles.HexNumber,
                    System.Globalization.CultureInfo.InvariantCulture, out uint hexNumber):
                return (long)hexNumber;
            default:
                return null;
        }
    }

    private static string? ReadSafeFailureText(
        IReadOnlyDictionary<string, object?> failure, string primaryName, string? aliasName = null)
    {
        object? raw = failure.GetValueOrDefault(primaryName);
        if (raw is null && aliasName is not null) raw = failure.GetValueOrDefault(aliasName);
        return raw is string value && value.Length <= 128
            && value.All(character => char.IsAsciiLetterOrDigit(character)
                || character is '_' or '.' or ':' or ' ' or '-')
            && !Regex.IsMatch(value, @"(?i)\bS-\d-\d+(?:-\d+)+\b|(?:^|;)\s*(?:O|G|D|S):")
            ? value
            : null;
    }

    private static void ValidateWtsDesktopAclDiagnosticInputs(HelperOptions options)
    {
        if (!OperatingSystem.IsWindows()) throw new PlatformNotSupportedException("This helper requires Windows.");
        if (options.ReportPath is null || options.EvidenceDirectory is null
            || options.DesktopAclEvidencePath is null || options.ExpectedRunId is null)
        {
            throw new ArgumentException("Required WTS desktop-ACL diagnostic inputs are missing.");
        }
        if (!Guid.TryParseExact(options.ExpectedRunId, "D", out Guid runId) || runId == Guid.Empty)
        {
            throw new NativeApiException("WtsDesktopAcl.RunId.Invalid", NativeMethods.ErrorAccessDenied);
        }
        if (File.Exists(options.ReportPath) || Directory.Exists(options.ReportPath))
        {
            throw new NativeApiException("WtsDesktopAcl.ReportPath.MustBeNew", NativeMethods.ErrorAlreadyExists);
        }
        if (!Directory.Exists(options.EvidenceDirectory)) throw new NativeApiException("WtsDesktopAcl.EvidenceDirectory.Missing", NativeMethods.ErrorNotFound);
        string canonicalEvidence = Path.GetFullPath(options.EvidenceDirectory).TrimEnd('\\');
        if (!string.Equals(Path.GetDirectoryName(Path.GetFullPath(options.ReportPath))?.TrimEnd('\\'),
                canonicalEvidence, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(Path.GetDirectoryName(Path.GetFullPath(options.DesktopAclEvidencePath))?.TrimEnd('\\'),
                canonicalEvidence, StringComparison.OrdinalIgnoreCase))
        {
            throw new NativeApiException("WtsDesktopAcl.Paths.MustBeInEvidenceDirectory", NativeMethods.ErrorAccessDenied);
        }
        FileInfo evidence = new(options.DesktopAclEvidencePath);
        if (!evidence.Exists || evidence.Length is <= 0 or > 65536)
        {
            throw new NativeApiException("WtsDesktopAcl.Evidence.MissingOrInvalidSize", NativeMethods.ErrorNotFound);
        }
    }

    internal static async Task<int> RunWtsNativeControlAsync(HelperOptions options, JsonSerializerOptions jsonOptions)
    {
        Dictionary<string, object?> report = CreateInitialReport(options);
        report["mode"] = "b2-wts-native-control";
        report["run_id"] = options.ExpectedRunId;
        report["browser"] = new Dictionary<string, object?>
        {
            ["process_id"] = null,
            ["process_exit_code"] = null,
            ["timed_out"] = null,
            ["status"] = "not_run; WTS native-only control",
        };
        report["page"] = new Dictionary<string, object?>
        {
            ["status"] = "not_run; WTS native-only control",
            ["dom_marker_found"] = false,
            ["screenshot_path"] = null,
        };
        WtsMediumIdentityContext? identity = null;
        Dictionary<string, object?>? nativeDiagnostic = null;
        bool jobDrained = false;
        int helperExitCode = HelperFailure;
        string stage = "preflight";
        TokenPrivilegeScope? privileges = null;
        try
        {
            ValidateWtsNativeControlInputs(options);
            privileges = TokenPrivilegeScope.EnableWtsQueryUserTokenOnly();
            stage = "wts_identity_filter";
            identity = new WtsMediumIdentityContext();
            Dictionary<string, object?> identityReport = identity.Initialize();
            report["identity"] = identityReport;

            report["desktop_access_check"] = new Dictionary<string, object?>
            {
                ["status"] = "not_performed",
                ["reason"] = "WTS native-only control gates on the filtered token readback and observed User32 station/desktop markers; guest-written ExistingLogin DACL JSON is untrusted and non-gating",
                ["target_user_sid"] = identity.UserSid,
                ["target_logon_sid"] = identity.LogonSid,
                ["target_session_id"] = identity.SessionId,
                ["acl_mutated"] = false,
                ["untrusted_dacl_hint_used"] = false,
            };

            stage = "target_profile_temp_work_leaf";
            string workDirectory = identity.CreateWorkDirectory();
            report["work_area"] = new Dictionary<string, object?>
            {
                ["path"] = workDirectory,
                ["parent"] = identity.TempDirectory,
                ["profile_directory"] = identity.ProfileDirectory,
                ["acl_mutated"] = false,
                ["created_under_final_target_token"] = true,
                ["purpose"] = "native marker files only",
            };

            stage = "native_user32_diagnostic";
            nativeDiagnostic = await RunNativeDesktopDiagnosticAsync(options.NativeDiagnosticPath!, identity, workDirectory,
                TargetProcessLauncher.InteractiveDefaultDesktop)
                .ConfigureAwait(false);
            report["native_diagnostic"] = nativeDiagnostic;
            jobDrained = nativeDiagnostic["cleanup_complete"] is true
                && nativeDiagnostic["active_processes_after"] is uint activeAfter && activeAfter == 0;
            report["process_tree"] = new Dictionary<string, object?>
            {
                ["cleanup_status"] = nativeDiagnostic["cleanup_status"],
                ["active_processes_after"] = nativeDiagnostic["active_processes_after"],
                ["observed_processes"] = nativeDiagnostic["observed_processes"],
            };
            if (nativeDiagnostic["status"] as string != "pass" || !jobDrained)
            {
                throw new NativeApiException("WtsMedium.NativeFixtureOrJobGateFailed", NativeMethods.ErrorAccessDenied);
            }
            report["status"] = "pass";
            helperExitCode = HelperSuccess;
        }
        catch (Exception exception)
        {
            report["status"] = "fail";
            report["failure"] = Failure(stage, exception);
            if (identity?.LastIdentityReport is not null)
            {
                report["identity"] = identity.LastIdentityReport;
            }
        }
        finally
        {
            if (identity is not null)
            {
                report["scratch_cleanup"] = identity.CleanupWorkDirectory(jobDrained);
                if (jobDrained && ((Dictionary<string, object?>)report["scratch_cleanup"]!)["removed"] is not true)
                {
                    report["status"] = "fail";
                    report["failure"] ??= Failure("scratch_cleanup", new IOException("The unique WTS scratch leaf was not removed after job drain."));
                    helperExitCode = HelperFailure;
                }
                identity.Dispose();
                report["identity_cleanup"] = new Dictionary<string, object?>
                {
                    ["environment_status"] = identity.EnvironmentCleanupStatus,
                    ["token_handles_closed"] = identity.TokenHandlesClosed,
                    ["profile_unloaded"] = false,
                    ["profile_unload_not_attempted"] = true,
                    ["account_deleted"] = false,
                    ["account_deletion_not_applicable"] = true,
                };
                if (identity.EnvironmentCleanupStatus == "failed" || !identity.TokenHandlesClosed)
                {
                    report["status"] = "fail";
                    report["failure"] ??= Failure("identity_cleanup", new IOException("WTS identity environment/token cleanup was not confirmed."));
                    helperExitCode = HelperFailure;
                }
            }
            privileges?.Dispose();
            report["helper_exit_code"] = helperExitCode;
            report["completed_at_utc"] = DateTimeOffset.UtcNow;
            try { Program.WriteJson(options.ReportPath!, report, jsonOptions); }
            catch (Exception writeError)
            {
                Console.Error.WriteLine($"report-write:{writeError.GetType().Name}");
                helperExitCode = HelperFailure;
            }
        }
        return helperExitCode;
    }

    internal static async Task<int> RunWtsLoaderSnapsAsync(HelperOptions options, JsonSerializerOptions jsonOptions)
    {
        var report = new Dictionary<string, object?>
        {
            ["schema"] = "b2-wts-loader-snaps-observation/v1",
            ["mode"] = "b2-wts-loader-snaps",
            ["status"] = "pending",
            ["run_id"] = options.ExpectedRunId,
            ["captured_at_utc"] = DateTimeOffset.UtcNow,
            ["browser"] = new Dictionary<string, object?> { ["status"] = "not_run" },
            ["page"] = new Dictionary<string, object?> { ["status"] = "not_run" },
            ["loader_diagnostic"] = null,
            ["ifeo"] = null,
            ["process_tree"] = null,
            ["identity"] = null,
            ["failure"] = null,
        };
        WtsMediumIdentityContext? identity = null;
        IfeoGlobalFlagLease? ifeoLease = null;
        Dictionary<string, object?>? diagnostic = null;
        TokenPrivilegeScope? privileges = null;
        bool jobDrained = false;
        int helperExitCode = HelperFailure;
        string stage = "preflight";
        try
        {
            ValidateWtsLoaderSnapsInputs(options, out string cdbHash, out long cdbBytes,
                out string targetHash, out long targetBytes);
            privileges = TokenPrivilegeScope.EnableWtsQueryUserTokenOnly();
            stage = "wts_identity_filter";
            identity = new WtsMediumIdentityContext();
            identity.Initialize();
            report["identity"] = CreateLoaderIdentityEvidence(identity.LastIdentityReport!);

            stage = "target_profile_temp_work_leaf";
            string workDirectory = identity.CreateWorkDirectory();
            report["work_area"] = new Dictionary<string, object?>
            {
                ["leaf_name"] = Path.GetFileName(workDirectory.TrimEnd('\\')),
                ["created_under_final_target_token"] = true,
                ["acl_mutated"] = false,
                ["purpose"] = "unique loader-diagnostic target and bounded capture only",
            };

            string runId = Guid.ParseExact(options.ExpectedRunId!, "D").ToString("N");
            string stagedTargetName = $"loader-probe-{runId}.exe";
            string stagedTargetPath = Path.Combine(workDirectory, stagedTargetName);
            if (File.Exists(stagedTargetPath) || Directory.Exists(stagedTargetPath))
            {
                throw new NativeApiException("LoaderSnaps.TargetCopy.MustBeNew", NativeMethods.ErrorAlreadyExists);
            }
            File.Copy(options.LoaderTargetPath!, stagedTargetPath, overwrite: false);
            string stagedTargetHash = HashFile(stagedTargetPath, out long stagedTargetBytes);
            if (!string.Equals(stagedTargetHash, targetHash, StringComparison.OrdinalIgnoreCase)
                || stagedTargetBytes != targetBytes)
            {
                throw new NativeApiException("LoaderSnaps.TargetCopy.HashMismatch", NativeMethods.ErrorAccessDenied);
            }

            stage = "ifeo_global_flag_acquire";
            ifeoLease = IfeoGlobalFlagLease.Acquire(stagedTargetName);
            report["ifeo"] = new Dictionary<string, object?>
            {
                ["registry_view"] = "Registry64",
                ["key_previously_existed"] = ifeoLease.Original.KeyExists,
                ["global_flag_previously_existed"] = ifeoLease.Original.ValueExists,
                ["original_global_flag_dword"] = ifeoLease.Original.Value is uint originalFlags ? $"0x{originalFlags:X8}" : null,
                ["enabled_global_flag_dword"] = $"0x{ifeoLease.EnabledValue:X8}",
                ["loader_snaps_flag"] = "0x00000002",
                ["image_name_is_run_unique"] = stagedTargetName == $"loader-probe-{runId}.exe",
                ["coordination"] = "named semaphore serializes cooperating helper runs for this image name",
                ["external_writer_compare_and_swap"] = false,
                ["status"] = "enabled; exact restore pending after Job drain",
            };

            stage = "cdb_loader_snaps_diagnostic";
            diagnostic = await RunLoaderSnapsDiagnosticAsync(options.CdbPath!, options.LoaderTargetPath!,
                cdbHash, cdbBytes, targetHash, targetBytes, stagedTargetPath, stagedTargetName,
                identity, workDirectory, TimeSpan.FromSeconds(options.TimeoutSeconds)).ConfigureAwait(false);
            report["loader_diagnostic"] = diagnostic;
            jobDrained = diagnostic.GetValueOrDefault("cleanup_complete") is true
                && diagnostic.GetValueOrDefault("active_processes_after") is uint activeProcessCount && activeProcessCount == 0;
            report["process_tree"] = new Dictionary<string, object?>
            {
                ["cleanup_status"] = diagnostic.GetValueOrDefault("cleanup_status"),
                ["active_processes_after"] = diagnostic.GetValueOrDefault("active_processes_after"),
                ["observed_processes"] = diagnostic.GetValueOrDefault("observed_processes"),
            };
            if (diagnostic.GetValueOrDefault("status") as string != "diagnostic_complete" || !jobDrained)
            {
                throw new NativeApiException("LoaderSnaps.DiagnosticOrJobGateFailed", NativeMethods.ErrorAccessDenied);
            }
            report["status"] = "diagnostic_complete";
            helperExitCode = HelperSuccess;
        }
        catch (Exception exception)
        {
            report["status"] = "fail";
            report["failure"] = Failure(stage, exception);
        }
        finally
        {
            if (ifeoLease is not null)
            {
                if (!jobDrained)
                {
                    report["ifeo_restore"] = new Dictionary<string, object?>
                    {
                        ["status"] = "deferred_to_sandbox_teardown",
                        ["reason"] = "Job drain was not confirmed; the Loader Snaps lease remains until the one-off Sandbox is discarded.",
                    };
                    report["status"] = "fail";
                    report["failure"] ??= Failure("ifeo_global_flag_restore", new IOException("Job drain was not confirmed; exact IFEO restoration was deferred to Sandbox teardown."));
                    helperExitCode = HelperFailure;
                    try { ifeoLease.ReleaseForSandboxTeardown(); }
                    catch (Exception releaseError)
                    {
                        report["ifeo_mutex_cleanup"] = Failure("ifeo_mutex_cleanup", releaseError);
                    }
                }
                else
                {
                    try
                    {
                        IfeoGlobalFlagSnapshot restored = ifeoLease.Restore();
                        report["ifeo_restore"] = new Dictionary<string, object?>
                        {
                            ["status"] = "pass",
                            ["key_exists_after_restore"] = restored.KeyExists,
                            ["global_flag_exists_after_restore"] = restored.ValueExists,
                            ["value_matches_original"] = restored.Value == ifeoLease.Original.Value,
                        };
                    }
                    catch (Exception restoreError)
                    {
                        report["ifeo_restore"] = new Dictionary<string, object?>
                        {
                            ["status"] = "fail",
                            ["failure"] = Failure("ifeo_global_flag_restore", restoreError),
                        };
                        report["status"] = "fail";
                        report["failure"] ??= Failure("ifeo_global_flag_restore", restoreError);
                        helperExitCode = HelperFailure;
                    }
                    finally
                    {
                        try { ifeoLease.Dispose(); }
                        catch (Exception disposeError)
                        {
                            report["status"] = "fail";
                            report["ifeo_mutex_cleanup"] = Failure("ifeo_mutex_cleanup", disposeError);
                            helperExitCode = HelperFailure;
                        }
                    }
                }
            }

            if (identity is not null)
            {
                try
                {
                    Dictionary<string, object?> scratch = identity.CleanupWorkDirectory(jobDrained);
                    scratch.Remove("path");
                    scratch["leaf_name"] = identity.WorkDirectory is null
                        ? null
                        : Path.GetFileName(identity.WorkDirectory.TrimEnd('\\'));
                    report["scratch_cleanup"] = scratch;
                    if (jobDrained && scratch.GetValueOrDefault("removed") is not true)
                    {
                        report["status"] = "fail";
                        report["failure"] ??= Failure("scratch_cleanup", new IOException("The WTS loader scratch leaf was not removed after Job drain."));
                        helperExitCode = HelperFailure;
                    }
                }
                catch (Exception scratchError)
                {
                    report["scratch_cleanup"] = Failure("scratch_cleanup", scratchError);
                    report["status"] = "fail";
                    helperExitCode = HelperFailure;
                }
                identity.Dispose();
                report["identity_cleanup"] = new Dictionary<string, object?>
                {
                    ["environment_status"] = identity.EnvironmentCleanupStatus,
                    ["token_handles_closed"] = identity.TokenHandlesClosed,
                    ["profile_unloaded"] = false,
                    ["profile_unload_not_attempted"] = true,
                };
                if (identity.EnvironmentCleanupStatus == "failed" || !identity.TokenHandlesClosed)
                {
                    report["status"] = "fail";
                    report["failure"] ??= Failure("identity_cleanup", new IOException("WTS identity cleanup was not confirmed."));
                    helperExitCode = HelperFailure;
                }
            }
            privileges?.Dispose();
            if (report["status"] as string != "diagnostic_complete") helperExitCode = HelperFailure;
            report["helper_exit_code"] = helperExitCode;
            report["completed_at_utc"] = DateTimeOffset.UtcNow;
            try { Program.WriteJson(options.ReportPath!, report, jsonOptions); }
            catch (Exception writeError)
            {
                Console.Error.WriteLine($"report-write:{writeError.GetType().Name}");
                helperExitCode = HelperFailure;
            }
        }
        return helperExitCode;
    }

    private static async Task<Dictionary<string, object?>> RunLoaderSnapsDiagnosticAsync(
        string cdbPath,
        string sourceTargetPath,
        string cdbSha256,
        long cdbBytes,
        string targetSha256,
        long targetBytes,
        string stagedTargetPath,
        string stagedTargetName,
        WtsMediumIdentityContext identity,
        string workDirectory,
        TimeSpan timeout)
    {
        const long maxBytesPerStream = 256 * 1024;
        string[] arguments = ["-g", "-G", "-hd", "-xn", "0xC0000142", stagedTargetPath];
        var result = new Dictionary<string, object?>
        {
            ["status"] = "pending",
            ["diagnostic_only"] = true,
            ["debugger_image"] = "cdb.exe",
            ["debugger_bytes"] = cdbBytes,
            ["debugger_sha256"] = cdbSha256,
            ["target_image"] = stagedTargetName,
            ["target_bytes"] = targetBytes,
            ["target_sha256"] = targetSha256,
            ["target_exit_code"] = null,
            ["target_exit_code_raw"] = null,
            ["target_exit_code_status"] = "not_observed",
            ["cdb_exit_code_raw"] = null,
            ["cdb_exited_naturally"] = false,
            ["output_byte_limit_per_stream"] = maxBytesPerStream,
            ["output"] = null,
            ["loader_output_line_count"] = 0,
            ["loader_output_observed"] = false,
            ["loader_module_basenames"] = Array.Empty<string>(),
            ["loader_status_codes"] = Array.Empty<string>(),
            ["root_pid"] = null,
            ["target_pid"] = null,
            ["root_process_observation"] = null,
            ["target_process_observation"] = null,
            ["identity_checks"] = null,
            ["cleanup_status"] = "not_started",
            ["active_processes_after"] = null,
            ["cleanup_complete"] = false,
            ["observed_processes"] = new List<Dictionary<string, object?>>(),
            ["failure"] = null,
        };

        TrackedJobNative native = new();
        SuspendedLaunch? launch = null;
        LeaseProcessJob? job = null;
        ProcessTracker? tracker = null;
        SafeProcessHandle? targetExitHandle = null;
        var newProcessHandles = new Dictionary<uint, SafeProcessHandle>();
        int newProcessHandleOpenFailures = 0;
        Exception? bodyFailure = null;
        bool rootExitedNaturally = false;
        bool identityChecksPass = false;
        bool targetExitCodeObserved = false;
        bool outputCaptureComplete = false;
        bool outputLimitExceeded = false;
        uint? rootProcessId = null;
        uint? targetProcessId = null;

        SafeProcessHandle? CaptureNewProcessHandle(uint processId)
        {
            if (targetExitHandle is not null || newProcessHandles.ContainsKey(processId)) return null;
            if (newProcessHandles.Count >= 128)
            {
                throw new InvalidDataException("The Loader Snaps Job produced more than 128 unresolved process notifications.");
            }

            SafeProcessHandle candidate = NativeMethods.OpenProcess(
                NativeMethods.ProcessQueryInformation | NativeMethods.ProcessQueryLimitedInformation
                    | NativeMethods.ProcessSynchronize,
                false, processId);
            if (candidate.IsInvalid)
            {
                newProcessHandleOpenFailures++;
                candidate.Dispose();
                return null;
            }
            newProcessHandles.Add(processId, candidate);
            return candidate;
        }

        void DisposeNonTargetProcessHandles(uint targetPid)
        {
            foreach ((uint processId, SafeProcessHandle processHandle) in newProcessHandles.ToArray())
            {
                newProcessHandles.Remove(processId);
                if (processId == targetPid)
                {
                    targetExitHandle ??= processHandle;
                }
                else
                {
                    processHandle.Dispose();
                }
            }
        }

        try
        {
            string actualCdbHash = HashFile(cdbPath, out long actualCdbBytes);
            string actualTargetHash = HashFile(sourceTargetPath, out long actualTargetBytes);
            if (!string.Equals(actualCdbHash, cdbSha256, StringComparison.OrdinalIgnoreCase)
                || actualCdbBytes != cdbBytes
                || !string.Equals(actualTargetHash, targetSha256, StringComparison.OrdinalIgnoreCase)
                || actualTargetBytes != targetBytes)
            {
                throw new NativeApiException("LoaderSnaps.InputHashChanged", NativeMethods.ErrorAccessDenied);
            }
            if (!File.Exists(stagedTargetPath)
                || !string.Equals(HashFile(stagedTargetPath, out long stagedBytes), targetSha256, StringComparison.OrdinalIgnoreCase)
                || stagedBytes != targetBytes)
            {
                throw new NativeApiException("LoaderSnaps.StagedTargetHashMismatch", NativeMethods.ErrorAccessDenied);
            }

            job = LeaseProcessJob.Start(() =>
            {
                launch = TargetProcessLauncher.CreateSuspended(identity.Token, identity.Environment,
                    cdbPath, arguments, workDirectory, TargetProcessLauncher.SystemSelectedDesktop,
                    maxBytesPerStream);
                return launch.Process;
            }, native);
            rootProcessId = job.RootProcessId;
            launch!.Output.Start();
            tracker = new ProcessTracker(native, CaptureNewProcessHandle);
            result["root_pid"] = rootProcessId.Value;

            long deadline = Environment.TickCount64 + (long)Math.Ceiling(timeout.TotalMilliseconds);
            while (Environment.TickCount64 < deadline)
            {
                tracker.CaptureTree(job.RootProcessId, job, identity.UserSid, identity.SessionId);
                ProcessObservation? targetObservation = tracker.Processes.FirstOrDefault(process =>
                    string.Equals(process.ImageName, stagedTargetName, StringComparison.OrdinalIgnoreCase)
                    && process.ParentProcessId == job.RootProcessId);
                if (targetObservation is not null)
                {
                    targetProcessId = targetObservation.ProcessId;
                    result["target_pid"] = targetProcessId.Value;
                    if (targetExitHandle is null)
                    {
                        if (newProcessHandles.Remove(targetObservation.ProcessId, out SafeProcessHandle? retained))
                        {
                            targetExitHandle = retained;
                        }
                        else
                        {
                            SafeProcessHandle candidate = NativeMethods.OpenProcess(
                                NativeMethods.ProcessQueryLimitedInformation | NativeMethods.ProcessSynchronize,
                                false, targetObservation.ProcessId);
                            if (candidate.IsInvalid)
                            {
                                result["target_exit_code_open_error"] = Marshal.GetLastWin32Error();
                                candidate.Dispose();
                            }
                            else
                            {
                                targetExitHandle = candidate;
                            }
                        }
                    }
                    DisposeNonTargetProcessHandles(targetObservation.ProcessId);
                }
                if (launch.Output.OutputLimitExceeded)
                {
                    outputLimitExceeded = true;
                    throw new InvalidDataException("CDB output exceeded its configured byte limit.");
                }
                uint wait = NativeMethods.WaitForSingleObject(job.RootProcessHandle, 0);
                if (wait == NativeMethods.WaitObject0)
                {
                    rootExitedNaturally = true;
                    result["cdb_exited_naturally"] = true;
                    break;
                }
                if (wait != NativeMethods.WaitTimeout)
                {
                    throw LastError("WaitForSingleObject.LoaderSnapsCdb");
                }
                await Task.Delay(10).ConfigureAwait(false);
            }
            if (!rootExitedNaturally)
            {
                throw new TimeoutException("The bounded Loader Snaps debugger wait expired.");
            }

            tracker.CaptureTree(job.RootProcessId, job, identity.UserSid, identity.SessionId);
            ProcessObservation rootObservation = FindObservation(tracker, job.RootProcessId);
            ProcessObservation? finalTargetObservation = tracker.Processes.FirstOrDefault(process =>
                string.Equals(process.ImageName, stagedTargetName, StringComparison.OrdinalIgnoreCase)
                && process.ParentProcessId == job.RootProcessId);
            if (finalTargetObservation is not null)
            {
                targetProcessId = finalTargetObservation.ProcessId;
                result["target_pid"] = targetProcessId.Value;
            }
            result["root_process_observation"] = ToLoaderProcessEvidence(rootObservation, identity.UserSid);
            result["target_process_observation"] = finalTargetObservation is null
                ? null
                : ToLoaderProcessEvidence(finalTargetObservation, identity.UserSid);
            identityChecksPass = finalTargetObservation is not null
                && rootObservation.ImageName.Equals("cdb.exe", StringComparison.OrdinalIgnoreCase)
                && rootObservation.UserSid == identity.UserSid
                && finalTargetObservation.UserSid == identity.UserSid
                && rootObservation.SessionId == identity.SessionId
                && finalTargetObservation.SessionId == identity.SessionId
                && rootObservation.IntegrityLevel == "medium"
                && finalTargetObservation.IntegrityLevel == "medium"
                && rootObservation.IntegritySid is not null
                && string.Equals(rootObservation.IntegritySid, finalTargetObservation.IntegritySid, StringComparison.Ordinal)
                && rootObservation.TokenIsElevated is false
                && finalTargetObservation.TokenIsElevated is false
                && rootObservation.JobMember is true
                && finalTargetObservation.JobMember is true
                && rootObservation.QueryStatus == "verified"
                && finalTargetObservation.QueryStatus == "verified"
                && finalTargetObservation.ParentProcessId == rootObservation.ProcessId;
            result["identity_checks"] = new Dictionary<string, object?>
            {
                ["cdb_is_job_root"] = rootObservation.ProcessId == job.RootProcessId,
                ["target_parent_is_cdb"] = finalTargetObservation?.ParentProcessId == rootObservation.ProcessId,
                ["both_sid_match_target"] = rootObservation.UserSid == identity.UserSid
                    && finalTargetObservation?.UserSid == identity.UserSid,
                ["both_session_match_target"] = rootObservation.SessionId == identity.SessionId
                    && finalTargetObservation?.SessionId == identity.SessionId,
                ["both_medium_integrity"] = rootObservation.IntegrityLevel == "medium"
                    && finalTargetObservation?.IntegrityLevel == "medium",
                ["both_not_elevated"] = rootObservation.TokenIsElevated is false
                    && finalTargetObservation?.TokenIsElevated is false,
                ["both_in_job"] = rootObservation.JobMember is true && finalTargetObservation?.JobMember is true,
                ["both_process_tokens_verified"] = rootObservation.QueryStatus == "verified"
                    && finalTargetObservation?.QueryStatus == "verified",
                ["pass"] = identityChecksPass,
            };
            if (NativeMethods.GetExitCodeProcess(job.RootProcessHandle, out uint cdbExitCode))
            {
                result["cdb_exit_code_raw"] = $"0x{cdbExitCode:X8}";
            }
            else
            {
                result["cdb_exit_code_query_error"] = Marshal.GetLastWin32Error();
            }
            if (targetExitHandle is null)
            {
                result["target_exit_code_status"] = "target_process_handle_not_captured";
            }
            else
            {
                uint targetWait = NativeMethods.WaitForSingleObject(targetExitHandle, 0);
                if (targetWait == NativeMethods.WaitObject0
                    && NativeMethods.GetExitCodeProcess(targetExitHandle, out uint targetExitCode))
                {
                    result["target_exit_code"] = unchecked((int)targetExitCode);
                    result["target_exit_code_raw"] = $"0x{targetExitCode:X8}";
                    result["target_exit_code_status"] = "observed_from_target_process_handle";
                    targetExitCodeObserved = true;
                }
                else
                {
                    result["target_exit_code_status"] = targetWait == NativeMethods.WaitTimeout
                        ? "target_process_not_signaled"
                        : targetWait == NativeMethods.WaitObject0 ? "get_exit_code_failed" : "target_wait_failed";
                    if (targetWait != NativeMethods.WaitTimeout) result["target_exit_code_query_error"] = Marshal.GetLastWin32Error();
                }
            }
        }
        catch (Exception exception)
        {
            bodyFailure = exception;
            result["failure"] = Failure("loader_snaps_debugger", exception);
            if (exception is InvalidDataException && launch?.Output.OutputLimitExceeded is true)
            {
                outputLimitExceeded = true;
            }
        }
        finally
        {
            if (job is not null)
            {
                try
                {
                    await job.StopAndWaitAsync(TimeSpan.FromSeconds(8)).ConfigureAwait(false);
                    uint activeAfter = native.GetActiveProcessCountAfterStop();
                    result["active_processes_after"] = activeAfter;
                    result["cleanup_complete"] = activeAfter == 0;
                    result["cleanup_status"] = activeAfter == 0
                        ? "complete; Loader Snaps Job drained"
                        : "failed; active process count nonzero";
                }
                catch (Exception cleanupError)
                {
                    result["cleanup_status"] = "failed; " + cleanupError.GetType().Name;
                    result["cleanup_failure"] = Failure("loader_snaps_job_cleanup", cleanupError);
                    try
                    {
                        native.EmergencyTerminateAndDrain(TimeSpan.FromSeconds(8));
                        uint activeAfter = native.GetActiveProcessCountAfterStop();
                        result["active_processes_after"] = activeAfter;
                        result["cleanup_complete"] = activeAfter == 0;
                        if (activeAfter == 0) result["cleanup_status"] = "complete after emergency termination";
                    }
                    catch (Exception emergencyError)
                    {
                        result["cleanup_emergency_failure"] = Failure("loader_snaps_emergency_cleanup", emergencyError);
                    }
                }
            }
            else
            {
                result["cleanup_status"] = "no job started";
                result["active_processes_after"] = 0;
                result["cleanup_complete"] = true;
            }

            if (launch is not null)
            {
                try
                {
                    (CapturedStream stdout, CapturedStream stderr, bool captureComplete) =
                        await launch.Output.CompleteAsync(TimeSpan.FromSeconds(3)).ConfigureAwait(false);
                    outputCaptureComplete = captureComplete;
                    outputLimitExceeded |= stdout.LimitExceeded || stderr.LimitExceeded;
                    int loaderLines = CountLoaderSnapsLines(stdout.Text) + CountLoaderSnapsLines(stderr.Text);
                    result["loader_output_line_count"] = loaderLines;
                    result["loader_output_observed"] = loaderLines > 0;
                    result["loader_module_basenames"] = ExtractLoaderModuleBasenames(stdout.Text + "\n" + stderr.Text);
                    result["loader_status_codes"] = ExtractLoaderStatusCodes(stdout.Text + "\n" + stderr.Text);
                    result["output"] = new Dictionary<string, object?>
                    {
                        ["stdout"] = SafeCaptureSummary(stdout),
                        ["stderr"] = SafeCaptureSummary(stderr),
                        ["capture_complete"] = captureComplete,
                        ["limit_exceeded"] = outputLimitExceeded,
                    };
                }
                catch (Exception captureError)
                {
                    result["output_capture_failure"] = Failure("loader_snaps_output_capture", captureError);
                }
                await launch.Output.DisposeAsync().ConfigureAwait(false);
            }

            if (job is not null && tracker is not null)
            {
                try
                {
                    if (rootProcessId is uint trackedRootPid)
                    {
                        tracker.CaptureTree(trackedRootPid, job, identity.UserSid, identity.SessionId);
                    }
                }
                catch (Exception trackingError)
                {
                    result["final_process_observation_failure"] = Failure("loader_snaps_final_process_observation", trackingError);
                }
            }
            targetExitHandle?.Dispose();
            foreach (SafeProcessHandle processHandle in newProcessHandles.Values)
            {
                processHandle.Dispose();
            }
            newProcessHandles.Clear();
            result["new_process_handle_capture"] = new Dictionary<string, object?>
            {
                ["retained_candidates_at_end"] = 0,
                ["open_failures"] = newProcessHandleOpenFailures,
                ["candidate_limit"] = 128,
            };
            job?.Dispose();
            native.Dispose();
            if (tracker is not null)
            {
                result["observed_processes"] = tracker.Processes
                    .Select(process => ToLoaderProcessEvidence(process, identity.UserSid)).ToList();
            }
        }

        bool diagnosticComplete = bodyFailure is null
            && rootExitedNaturally
            && identityChecksPass
            && targetProcessId is not null
            && targetExitCodeObserved
            && result["loader_output_observed"] is true
            && !outputLimitExceeded
            && outputCaptureComplete
            && result["cleanup_complete"] is true
            && result["active_processes_after"] is uint finalActiveProcessCount && finalActiveProcessCount == 0
            && !result.ContainsKey("cleanup_failure")
            && !result.ContainsKey("cleanup_emergency_failure")
            && !result.ContainsKey("output_capture_failure")
            && !result.ContainsKey("final_process_observation_failure");
        result["status"] = diagnosticComplete ? "diagnostic_complete" : "fail";
        if (!diagnosticComplete && result["failure"] is null)
        {
            result["failure"] = new Dictionary<string, object?>
            {
                ["stage"] = "loader_snaps_evidence_gate",
                ["api"] = null,
                ["win32_error"] = null,
                ["message"] = outputLimitExceeded ? "output_byte_limit_exceeded"
                    : result["loader_output_observed"] is not true ? "loader_output_not_observed; no retry permitted"
                    : !identityChecksPass ? "debugger_or_target_identity_not_verified"
                    : "bounded_diagnostic_incomplete",
            };
        }
        return result;
    }

    private static Dictionary<string, object?> SafeCaptureSummary(CapturedStream capture) => new()
    {
        ["bytes"] = capture.Bytes,
        ["sha256"] = capture.Sha256,
        ["truncated"] = capture.Truncated,
        ["limit_exceeded"] = capture.LimitExceeded,
    };

    private static Dictionary<string, object?> CreateLoaderIdentityEvidence(Dictionary<string, object?> source)
    {
        var evidence = new Dictionary<string, object?>();
        CopyFields(source, evidence,
            "source", "helper_is_local_system", "requested_session_id", "wts_session_1_active",
            "target_session_is_interactive", "target_session_id", "source_account_is_local",
            "profile_loaded_by_helper", "profile_unloaded_by_helper", "acl_mutated");

        if (source.TryGetValue("source_account", out object? sourceAccountValue)
            && sourceAccountValue is Dictionary<string, object?> sourceAccount
            && sourceAccount.TryGetValue("status", out object? accountStatus))
        {
            evidence["source_account_verification"] = accountStatus;
        }

        if (source.TryGetValue("desktop", out object? desktopValue)
            && desktopValue is Dictionary<string, object?> desktop)
        {
            var safeDesktop = new Dictionary<string, object?>();
            CopyFields(desktop, safeDesktop, "requested_lpDesktop", "selection", "acl_mutated");
            evidence["desktop"] = safeDesktop;
        }

        if (source.TryGetValue("token_filter", out object? filterValue)
            && filterValue is Dictionary<string, object?> filter)
        {
            var safeFilter = new Dictionary<string, object?>();
            CopyFields(filter, safeFilter,
                "create_restricted_token_flags", "sids_to_restrict_count", "privileges_to_delete_count",
                "administrators_deny_only", "checked_builtin_privileged_alias_enabled_groups_absent",
                "all_privileges_disabled_except_change_notify", "token_is_restricted",
                "token_is_restricted_expected");
            evidence["token_filter"] = safeFilter;
        }

        if (source.TryGetValue("final_token", out object? finalTokenValue)
            && finalTokenValue is Dictionary<string, object?> finalToken)
        {
            var safeFinalToken = new Dictionary<string, object?>();
            CopyFields(finalToken, safeFinalToken,
                "status", "session_id", "token_type", "token_elevation", "integrity_level",
                "users_group_enabled", "administrators_group_deny_only",
                "checked_builtin_privileged_alias_enabled_groups_absent",
                "all_enabled_privileges_limited_to_change_notify", "restricted_sid_list_count",
                "token_is_restricted", "same_user_and_logon_sid_as_wts_source", "readback_gate_pass");
            evidence["final_token"] = safeFinalToken;
        }

        if (source.TryGetValue("profile", out object? profileValue)
            && profileValue is Dictionary<string, object?> profile)
        {
            var safeProfile = new Dictionary<string, object?>();
            CopyFields(profile, safeProfile, "hive_loaded", "profile_loaded_by_helper", "profile_unloaded_by_helper");
            evidence["profile"] = safeProfile;
        }

        if (source.TryGetValue("environment", out object? environmentValue)
            && environmentValue is Dictionary<string, object?> environment)
        {
            var safeEnvironment = new Dictionary<string, object?>();
            CopyFields(environment, safeEnvironment,
                "created_from_existing_wts_token", "userprofile_matches_token_profile",
                "tmp_matches_temp", "username_present", "all_required_variables_present");
            evidence["environment"] = safeEnvironment;
        }

        return evidence;
    }

    private static void CopyFields(
        Dictionary<string, object?> source,
        Dictionary<string, object?> destination,
        params string[] fieldNames)
    {
        foreach (string fieldName in fieldNames)
        {
            if (source.TryGetValue(fieldName, out object? value)) destination[fieldName] = value;
        }
    }

    private static string[] GetLoaderSnapsLines(string text) => text
        .Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries)
        .Where(line => line.Contains("LDR:", StringComparison.OrdinalIgnoreCase)
            || line.TrimStart().StartsWith("Ldrp", StringComparison.OrdinalIgnoreCase)
            || line.Contains("Loader Snaps", StringComparison.OrdinalIgnoreCase))
        .ToArray();

    private static int CountLoaderSnapsLines(string text) => GetLoaderSnapsLines(text).Length;

    private static string[] ExtractLoaderModuleBasenames(string text) => GetLoaderSnapsLines(text)
        .SelectMany(line => Regex.Matches(line, @"(?i)\b([A-Za-z0-9_.-]+\.(?:dll|exe))\b")
            .Select(match => match.Groups[1].Value))
        .Distinct(StringComparer.OrdinalIgnoreCase)
        .Take(32)
        .ToArray();

    private static string[] ExtractLoaderStatusCodes(string text) => GetLoaderSnapsLines(text)
        .Where(line => Regex.IsMatch(line, @"(?i)\b(?:status|error|failed|failure|exception|ntstatus|return(?:ed)?\s+code)\b"))
        .SelectMany(line => Regex.Matches(line, @"(?i)\b0x[0-9a-f]{8}\b")
            .Select(match => match.Value.ToUpperInvariant()))
        .Distinct(StringComparer.Ordinal)
        .Take(32)
        .ToArray();

    private static void ValidateWtsLoaderSnapsInputs(
        HelperOptions options,
        out string cdbSha256,
        out long cdbBytes,
        out string targetSha256,
        out long targetBytes)
    {
        if (!OperatingSystem.IsWindows()) throw new PlatformNotSupportedException("This helper requires Windows.");
        if (options.ReportPath is null || options.EvidenceDirectory is null || options.ExpectedRunId is null
            || options.CdbPath is null || options.LoaderTargetPath is null
            || options.ExpectedCdbSha256 is null || options.ExpectedLoaderTargetSha256 is null)
        {
            throw new ArgumentException("Required WTS Loader Snaps inputs are missing.");
        }
        if (!Guid.TryParseExact(options.ExpectedRunId, "D", out Guid runId) || runId == Guid.Empty)
        {
            throw new NativeApiException("LoaderSnaps.RunId.Invalid", NativeMethods.ErrorAccessDenied);
        }
        if (File.Exists(options.ReportPath) || Directory.Exists(options.ReportPath))
        {
            throw new NativeApiException("LoaderSnaps.ReportPath.MustBeNew", NativeMethods.ErrorAlreadyExists);
        }
        if (!Directory.Exists(options.EvidenceDirectory)
            || !string.Equals(Path.GetDirectoryName(Path.GetFullPath(options.ReportPath))?.TrimEnd('\\'),
                Path.GetFullPath(options.EvidenceDirectory).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase))
        {
            throw new NativeApiException("LoaderSnaps.ReportPath.MustBeInEvidenceDirectory", NativeMethods.ErrorAccessDenied);
        }
        if (!IsSha256(options.ExpectedCdbSha256) || !IsSha256(options.ExpectedLoaderTargetSha256))
        {
            throw new NativeApiException("LoaderSnaps.ExpectedHash.Invalid", NativeMethods.ErrorAccessDenied);
        }

        string helperDirectory = Path.GetDirectoryName(Environment.ProcessPath)
            ?? throw new InvalidOperationException("The helper path has no directory.");
        string runnerDirectory = Directory.GetParent(helperDirectory)?.FullName
            ?? throw new NativeApiException("LoaderSnaps.RunnerDirectory.Missing", NativeMethods.ErrorAccessDenied);
        string expectedCdb = Path.Combine(runnerDirectory, "debuggers", "x64", "cdb.exe");
        string expectedTarget = Path.Combine(runnerDirectory, "loader-diagnostic", "exit-only-probe.exe");
        if (!string.Equals(Path.GetFullPath(options.CdbPath), expectedCdb, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(Path.GetFullPath(options.LoaderTargetPath), expectedTarget, StringComparison.OrdinalIgnoreCase)
            || !File.Exists(expectedCdb) || !File.Exists(expectedTarget))
        {
            throw new NativeApiException("LoaderSnaps.Tools.MustBeMappedRunnerFiles", NativeMethods.ErrorAccessDenied);
        }

        cdbSha256 = HashFile(expectedCdb, out cdbBytes);
        targetSha256 = HashFile(expectedTarget, out targetBytes);
        if (!string.Equals(cdbSha256, options.ExpectedCdbSha256, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(targetSha256, options.ExpectedLoaderTargetSha256, StringComparison.OrdinalIgnoreCase))
        {
            throw new NativeApiException("LoaderSnaps.ToolHashMismatch", NativeMethods.ErrorAccessDenied);
        }
    }

    private static bool IsSha256(string value) => value.Length == 64 && value.All(char.IsAsciiHexDigit);

    private static void ValidateWtsNativeControlInputs(HelperOptions options)
    {
        if (!OperatingSystem.IsWindows()) throw new PlatformNotSupportedException("This helper requires Windows.");
        if (options.ReportPath is null || options.EvidenceDirectory is null
            || options.NativeDiagnosticPath is null || options.ExpectedRunId is null)
        {
            throw new ArgumentException("Required WTS native-control inputs are missing.");
        }
        if (!Guid.TryParseExact(options.ExpectedRunId, "D", out Guid runId) || runId == Guid.Empty)
        {
            throw new NativeApiException("WtsMedium.RunId.Invalid", NativeMethods.ErrorAccessDenied);
        }
        if (File.Exists(options.ReportPath) || Directory.Exists(options.ReportPath))
        {
            throw new NativeApiException("WtsMedium.ReportPath.MustBeNew", NativeMethods.ErrorAlreadyExists);
        }
        if (!Directory.Exists(options.EvidenceDirectory)) throw new NativeApiException("WtsMedium.EvidenceDirectory.Missing", NativeMethods.ErrorNotFound);
        if (!string.Equals(Path.GetDirectoryName(Path.GetFullPath(options.ReportPath))?.TrimEnd('\\'),
                Path.GetFullPath(options.EvidenceDirectory).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase))
        {
            throw new NativeApiException("WtsMedium.ReportPath.MustBeInEvidenceDirectory", NativeMethods.ErrorAccessDenied);
        }
        string helperDirectory = Path.GetDirectoryName(Environment.ProcessPath)
            ?? throw new InvalidOperationException("The helper path has no directory.");
        string runnerDirectory = Directory.GetParent(helperDirectory)?.FullName
            ?? throw new NativeApiException("WtsMedium.RunnerDirectory.Missing", NativeMethods.ErrorAccessDenied);
        string expectedNative = Path.Combine(runnerDirectory, "native-desktop-probe.exe");
        if (!string.Equals(Path.GetFullPath(options.NativeDiagnosticPath), expectedNative, StringComparison.OrdinalIgnoreCase)
            || !File.Exists(expectedNative))
        {
            throw new NativeApiException("WtsMedium.NativeFixture.MustBeMappedRunnerSibling", NativeMethods.ErrorAccessDenied);
        }
    }

    internal static async Task<int> RunAsync(HelperOptions options, JsonSerializerOptions jsonOptions)
    {
        Dictionary<string, object?> report = CreateInitialReport(options);
        TargetIdentityContext? identity = null;
        Dictionary<string, object?>? identityReport = null;
        WorkAreaResult? workArea = null;
        int helperExitCode = HelperFailure;
        string currentStage = "preflight";
        var allProcesses = new List<Dictionary<string, object?>>();
        bool allJobsDrained = true;
        var jobCleanupStatuses = new List<string>();

        try
        {
            ValidateInputs(options);
            using TokenPrivilegeScope privileges = TokenPrivilegeScope.EnableRequired();
            identity = new TargetIdentityContext();
            currentStage = "identity_setup";
            identityReport = identity.Initialize();
            report["identity"] = identityReport;

            currentStage = "desktop_acl_diagnostic";
            Dictionary<string, object?> interactiveDesktopDiagnostic = DesktopAccessCheck.EvaluateEvidence(
                options.DesktopAclEvidencePath!, options.EvidenceDirectory!,
                Path.GetFileName(Path.GetFullPath(options.WorkDirectory!).TrimEnd('\\'))[3..],
                identity.Token, identity.UserSid, identity.LogonSid, identity.SessionId);
            Dictionary<string, object?> desktopAccess = new()
            {
                ["status"] = "probe_explicit_requested; remaining_launches_auto_selected; effective_objects_unobserved",
                ["launch_lpDesktop"] = TargetProcessLauncher.SystemSelectedDesktop,
                ["probe_lpDesktop"] = TargetProcessLauncher.InteractiveDefaultDesktop,
                ["launch_contract"] = "The target PowerShell probe explicitly requests WinSta0\\Default so its launch is evaluated against the read-only same-session DACL snapshot. No ACL is changed. The remaining standard fixtures and browser retain an allocated empty lpDesktop and use Windows logon-session selection; their effective objects remain unknown until markers.",
                ["effective_object_access_check"] = "not_performed; effective object has not been observed",
                ["interactive_desktop_diagnostic"] = interactiveDesktopDiagnostic,
            };
            report["desktop_access_check"] = desktopAccess;
            ((Dictionary<string, object?>)identityReport["desktop"]!)["access_check"] = desktopAccess;

            currentStage = "work_area_setup";
            workArea = WorkArea.Create(options.WorkDirectory!, options.ProfileDirectory!, options.EvidenceDirectory!, identity.UserSid);
            report["work_area"] = new Dictionary<string, object?>
            {
                ["path"] = workArea.WorkDirectory,
                ["profile_directory"] = workArea.ProfileDirectory,
                ["acl"] = new Dictionary<string, object?>
                {
                    ["work_directory"] = workArea.WorkDirectoryAcl,
                    ["profile_directory"] = workArea.ProfileDirectoryAcl,
                    ["evidence_directory"] = workArea.EvidenceDirectoryAccess,
                },
            };

            // Capture the target-token ProcessSingleton result before unrelated
            // native desktop fixtures can gate the probe or browser path.
            currentStage = "probe_launch";
            Dictionary<string, object?> probe = await RunProbeAsync(options, identity, workArea).ConfigureAwait(false);
            report["probe"] = probe;
            allProcesses.AddRange((List<Dictionary<string, object?>>)probe["observed_processes"]!);
            bool probeDrained = (bool)probe["cleanup_complete"]!;
            allJobsDrained &= probeDrained;
            jobCleanupStatuses.Add("probe:" + (string)probe["cleanup_status"]!);
            if (!probeDrained)
            {
                throw new NativeApiException("ProbeJobCleanupFailed", NativeMethods.ErrorAccessDenied);
            }

            if (probe["status"] as string != "pass" || probe["process_exit_code"] is not int probeExitCode || probeExitCode != 0)
            {
                report["browser"] = new Dictionary<string, object?>
                {
                    ["process_id"] = null,
                    ["process_exit_code"] = null,
                    ["timed_out"] = false,
                    ["status"] = "skipped; probe did not report pass with process exit code 0",
                    ["command_line"] = null,
                    ["stdout"] = null,
                    ["stderr"] = null,
                };
                report["page"] = new Dictionary<string, object?>
                {
                    ["status"] = "skipped; probe failed",
                    ["dom_marker_found"] = false,
                    ["screenshot_path"] = null,
                    ["screenshot_bytes"] = null,
                    ["screenshot_sha256"] = null,
                };
                throw new NativeApiException("ProbeGateFailed.BrowserSkipped", NativeMethods.ErrorAccessDenied);
            }

            currentStage = "native_user32_diagnostic";
            Dictionary<string, object?> nativeDiagnostic = await RunNativeDesktopDiagnosticAsync(
                options.NativeDiagnosticPath!, identity, workArea.WorkDirectory,
                TargetProcessLauncher.SystemSelectedDesktop).ConfigureAwait(false);
            report["native_diagnostic"] = nativeDiagnostic;
            allProcesses.AddRange((List<Dictionary<string, object?>>)nativeDiagnostic["observed_processes"]!);
            bool nativeDiagnosticDrained = (bool)nativeDiagnostic["cleanup_complete"]!;
            allJobsDrained &= nativeDiagnosticDrained;
            jobCleanupStatuses.Add("native_user32_diagnostic:" + (string)nativeDiagnostic["cleanup_status"]!);
            if (!nativeDiagnosticDrained || nativeDiagnostic["status"] as string != "pass")
            {
                throw new NativeApiException("NativeUser32DiagnosticFailed.BrowserSkipped", NativeMethods.ErrorAccessDenied);
            }

            currentStage = "fixture_timeout";
            Dictionary<string, object?> timeoutFixture = await RunFixtureCaseAsync(identity, workArea, "timeout", injectException: false)
                .ConfigureAwait(false);
            report["fixture_timeout"] = timeoutFixture;
            allProcesses.AddRange((List<Dictionary<string, object?>>)timeoutFixture["observed_processes"]!);
            bool timeoutDrained = (bool)timeoutFixture["cleanup_complete"]!;
            allJobsDrained &= timeoutDrained;
            jobCleanupStatuses.Add("fixture_timeout:" + (string)timeoutFixture["cleanup_status"]!);
            if (!timeoutDrained || timeoutFixture["status"] as string != "pass")
            {
                throw new NativeApiException("FixtureTimeoutBranchFailed", NativeMethods.ErrorAccessDenied);
            }

            currentStage = "fixture_injected_exception";
            Dictionary<string, object?> exceptionFixture = await RunFixtureCaseAsync(identity, workArea, "injected-exception", injectException: true)
                .ConfigureAwait(false);
            report["fixture_injected_exception"] = exceptionFixture;
            allProcesses.AddRange((List<Dictionary<string, object?>>)exceptionFixture["observed_processes"]!);
            bool exceptionDrained = (bool)exceptionFixture["cleanup_complete"]!;
            allJobsDrained &= exceptionDrained;
            jobCleanupStatuses.Add("fixture_injected_exception:" + (string)exceptionFixture["cleanup_status"]!);
            if (!exceptionDrained || exceptionFixture["status"] as string != "pass")
            {
                throw new NativeApiException("FixtureInjectedExceptionFinallyFailed", NativeMethods.ErrorAccessDenied);
            }

            currentStage = "browser_launch";
            Dictionary<string, object?> browser = await RunBrowserAsync(options, identity, workArea).ConfigureAwait(false);
            report["browser"] = browser;
            allProcesses.AddRange((List<Dictionary<string, object?>>)browser["observed_processes"]!);
            bool browserDrained = (bool)browser["cleanup_complete"]!;
            allJobsDrained &= browserDrained;
            jobCleanupStatuses.Add("browser:" + (string)browser["cleanup_status"]!);
            report["page"] = browser["page"];
            if (!browserDrained)
            {
                throw new NativeApiException("BrowserJobCleanupFailed", NativeMethods.ErrorAccessDenied);
            }
            if (browser["timed_out"] is not false || browser["process_exit_code"] is not int browserExitCode || browserExitCode != 0)
            {
                throw new NativeApiException("BrowserExitOrTimeoutFailed", NativeMethods.ErrorAccessDenied);
            }
            Dictionary<string, object?> page = (Dictionary<string, object?>)browser["page"]!;
            if (page["status"] as string != "pass" || page["dom_marker_found"] is not true
                || page["screenshot_sha256"] is not string screenshotHash || screenshotHash.Length != 64)
            {
                throw new NativeApiException("ControlledPageEvidenceFailed", NativeMethods.ErrorAccessDenied);
            }

            report["status"] = "pass";
            helperExitCode = HelperSuccess;
        }
        catch (Exception exception)
        {
            if (identity?.LastIdentityReport is not null)
            {
                report["identity"] = identity.LastIdentityReport;
            }
            report["status"] = "fail";
            Dictionary<string, object?> failure = Failure(currentStage, exception);
            PreserveProcessOutcome(failure, report, currentStage);
            report["failure"] = failure;
            helperExitCode = HelperFailure;
        }
        finally
        {
            if (identity is not null)
            {
                if (allJobsDrained)
                {
                    Dictionary<string, object?> cleanup = identity.Cleanup();
                    report["identity_cleanup"] = cleanup;
                    if (cleanup["account_deleted"] is not true || cleanup["profile_unloaded"] is not true
                        || cleanup["environment_destroyed"] is not true)
                    {
                        report["status"] = "fail";
                        report["failure"] ??= Failure("identity_cleanup", new NativeApiException("IdentityCleanupIncomplete", NativeMethods.ErrorAccessDenied));
                        helperExitCode = HelperFailure;
                    }
                }
                else
                {
                    report["identity_cleanup"] = new Dictionary<string, object?>
                    {
                        ["account_deleted"] = false,
                        ["profile_unloaded"] = false,
                        ["environment_destroyed"] = false,
                        ["status"] = "deferred; at least one supervised process job did not prove drain, so identity/profile cleanup is left to task-owned Sandbox destruction",
                        ["cleanup_deferred_until_sandbox_stop"] = true,
                    };
                    report["status"] = "fail";
                    report["failure"] ??= Failure("identity_cleanup_deferred", new NativeApiException("IdentityCleanupDeferredUntilSandboxStop", NativeMethods.ErrorAccessDenied));
                    helperExitCode = HelperFailure;
                }
            }
            report["process_tree"] = new Dictionary<string, object?>
            {
                ["cleanup_status"] = allJobsDrained
                    ? "complete; all started LeaseProcessJob instances reported drain"
                    : "incomplete; at least one job did not report drain",
                ["active_processes_after"] = allJobsDrained ? 0 : null,
                ["job_results"] = jobCleanupStatuses,
                ["observed_processes"] = allProcesses,
            };
            report["helper_exit_code"] = helperExitCode;
            report["completed_at_utc"] = DateTimeOffset.UtcNow;
            try
            {
                Program.WriteJson(options.ReportPath!, report, jsonOptions);
            }
            catch (Exception writeError)
            {
                Console.Error.WriteLine($"report-write:{writeError.GetType().Name}");
                helperExitCode = HelperFailure;
            }
            if (allJobsDrained) identity?.Dispose();
        }
        return helperExitCode;
    }

    private static async Task<Dictionary<string, object?>> RunNativeDesktopDiagnosticAsync(
        string nativeExecutable,
        ITargetProcessIdentity identity,
        string workDirectory,
        string launchLpDesktop)
    {
        string launchSelection = launchLpDesktop.Length == 0
            ? "empty lpDesktop; Windows logon-session connection path"
            : "explicit interactive window station and desktop; no ACL mutation";
        string[] markerNames =
        [
            "native-root-pre.json",
            "native-root-post.json",
            "native-child-pre.json",
            "native-child-post.json",
            "native-root-summary.json",
        ];
        var markerPaths = markerNames.ToDictionary(
            name => name,
            name => Path.Combine(workDirectory, name),
            StringComparer.Ordinal);
        var result = new Dictionary<string, object?>
        {
            ["status"] = "pending",
            ["diagnostic_completed"] = false,
            ["diagnostic_outcome"] = "unknown",
            ["launch_lpDesktop"] = launchLpDesktop,
            ["launch_contract"] = launchSelection,
            ["native_executable_path"] = nativeExecutable,
            ["native_executable_bytes"] = null,
            ["native_executable_sha256"] = null,
            ["root_pid"] = null,
            ["child_pid"] = null,
            ["root_exit_code"] = null,
            ["root_exit_code_raw"] = null,
            ["root_exited_naturally"] = false,
            ["marker_presence"] = null,
            ["markers"] = null,
            ["root_process_observation"] = null,
            ["child_process_observation"] = null,
            ["token_checks"] = null,
            ["desktop_checks"] = null,
            ["cleanup_status"] = "not_started",
            ["active_processes_after"] = null,
            ["cleanup_complete"] = false,
            ["observed_processes"] = new List<Dictionary<string, object?>>(),
            ["output"] = null,
            ["failure"] = null,
        };

        TrackedJobNative native = new();
        SuspendedLaunch? launch = null;
        LeaseProcessJob? job = null;
        ProcessTracker? tracker = null;
        Exception? bodyFailure = null;
        bool rootExitedNaturally = false;
        uint? rootProcessId = null;
        try
        {
            string executableHash = HashFile(nativeExecutable, out long executableBytes);
            result["native_executable_bytes"] = executableBytes;
            result["native_executable_sha256"] = executableHash;
            if (markerPaths.Values.Any(path => File.Exists(path) || Directory.Exists(path)))
            {
                throw new NativeApiException("NativeDiagnosticMarkers.MustBeNew", NativeMethods.ErrorAlreadyExists);
            }

            job = LeaseProcessJob.Start(() =>
            {
                launch = TargetProcessLauncher.CreateSuspended(identity.Token, identity.Environment,
                    nativeExecutable, ["--root"], workDirectory,
                    launchLpDesktop);
                return launch.Process;
            }, native);
            rootProcessId = job.RootProcessId;
            launch!.Output.Start();
            tracker = new ProcessTracker(native);
            result["root_pid"] = rootProcessId.Value;
            ((Dictionary<string, object?>)identity.LastIdentityReport!["desktop"]!)["native_diagnostic_launch"] = new
            {
                selection = launchSelection,
                root_pid = rootProcessId.Value,
                lpDesktop = launchLpDesktop,
                native_executable_sha256 = executableHash,
            };

            result["marker_wait_outcome"] = "waiting";
            result["marker_wait_bound_seconds"] = 8;
            string markerWaitOutcome = await WaitForNativeDesktopMarkersAsync(markerPaths, job, tracker,
                identity, TimeSpan.FromSeconds(8)).ConfigureAwait(false);
            result["marker_wait_outcome"] = markerWaitOutcome;
            bool allMarkersPresent = markerWaitOutcome == "markers_complete";
            result["marker_presence"] = markerPaths.ToDictionary(
                pair => pair.Key,
                pair => File.Exists(pair.Value),
                StringComparer.Ordinal);
            var markers = new Dictionary<string, Dictionary<string, object?>>(StringComparer.Ordinal);
            foreach ((string name, string path) in markerPaths)
            {
                if (File.Exists(path))
                {
                    markers[name] = await ReadJsonObjectAsync(path).ConfigureAwait(false);
                }
            }
            result["markers"] = markers;
            if (!allMarkersPresent)
            {
                if (markerWaitOutcome == "root_exited_before_markers")
                {
                    rootExitedNaturally = true;
                    result["root_exited_naturally"] = true;
                    if (NativeMethods.GetExitCodeProcess(job.RootProcessHandle, out uint earlyExitCode))
                    {
                        result["root_exit_code"] = unchecked((int)earlyExitCode);
                        result["root_exit_code_raw"] = $"0x{earlyExitCode:X8}";
                    }
                    else
                    {
                        result["root_exit_code_query_error"] = Marshal.GetLastWin32Error();
                    }
                }
                if (markerWaitOutcome == "root_exited_before_markers")
                {
                    result["diagnostic_outcome"] = "root_exited_before_markers";
                    throw new InvalidOperationException("The native fixture root exited before writing all required markers.");
                }
                if (markerWaitOutcome == "bounded_timeout")
                {
                    result["diagnostic_outcome"] = "bounded_timeout";
                    throw new TimeoutException("The native fixture did not write all required markers before the bound while its root remained running.");
                }
                result["diagnostic_outcome"] = "wait_error";
                throw new InvalidOperationException("The native fixture marker wait ended without a recognized outcome.");
            }

            Dictionary<string, object?> rootPre = markers["native-root-pre.json"];
            Dictionary<string, object?> rootPost = markers["native-root-post.json"];
            Dictionary<string, object?> childPre = markers["native-child-pre.json"];
            Dictionary<string, object?> childPost = markers["native-child-post.json"];
            Dictionary<string, object?> rootSummary = markers["native-root-summary.json"];
            uint rootPrePid = GetUInt32(rootPre, "pid");
            uint rootPid = GetUInt32(rootPost, "pid");
            uint childPrePid = GetUInt32(childPre, "pid");
            uint childPid = GetUInt32(childPost, "pid");
            result["root_pid"] = rootPid;
            result["child_pid"] = childPid;

            Dictionary<string, bool> markerContractChecks = EvaluateNativeDiagnosticMarkerContract(
                rootPre, rootPost, childPre, childPost, rootSummary, rootPid, childPid);
            bool rootPreContractPass = markerContractChecks["root_pre_schema_kind_stage_and_pid_match"];
            bool childPreContractPass = markerContractChecks["child_pre_schema_kind_stage_and_pid_match"];
            bool markerContractPass = markerContractChecks["pass"];
            result["marker_contract_checks"] = markerContractChecks;

            tracker.CaptureTree(job.RootProcessId, job, identity.UserSid, identity.SessionId);
            ProcessObservation rootObservation = FindObservation(tracker, rootPid);
            ProcessObservation childObservation = FindObservation(tracker, childPid);
            result["root_process_observation"] = rootObservation.ToDictionary();
            result["child_process_observation"] = childObservation.ToDictionary();
            bool markerSessionChecks = rootPid == job.RootProcessId
                && GetJsonBoolean(rootPre, "session_id_known")
                && GetInt32(rootPre, "session_id") == identity.SessionId
                && GetInt32(rootPost, "session_id") == identity.SessionId
                && GetJsonBoolean(childPre, "session_id_known")
                && GetInt32(childPre, "session_id") == identity.SessionId
                && GetInt32(childPost, "session_id") == identity.SessionId;
            bool tokenChecks = markerSessionChecks
                && rootObservation.UserSid == identity.UserSid
                && childObservation.UserSid == identity.UserSid
                && rootObservation.SessionId == identity.SessionId
                && childObservation.SessionId == identity.SessionId
                && rootObservation.IntegritySid is not null
                && string.Equals(rootObservation.IntegritySid, childObservation.IntegritySid, StringComparison.Ordinal)
                && string.Equals(rootObservation.IntegrityLevel, "medium", StringComparison.Ordinal)
                && string.Equals(childObservation.IntegrityLevel, "medium", StringComparison.Ordinal)
                && rootObservation.TokenIsElevated is false
                && childObservation.TokenIsElevated is false
                && rootObservation.JobMember is true
                && childObservation.JobMember is true
                && rootObservation.QueryStatus == "verified"
                && childObservation.QueryStatus == "verified"
                && childObservation.ParentProcessId == rootPid;
            result["token_checks"] = new Dictionary<string, object?>
            {
                ["root_marker_pid_matches_job_root"] = rootPid == job.RootProcessId,
                ["root_and_child_marker_sessions_match_target"] = markerSessionChecks,
                ["root_and_child_sid_match_target"] = rootObservation.UserSid == identity.UserSid
                    && childObservation.UserSid == identity.UserSid,
                ["root_and_child_session_match_target"] = rootObservation.SessionId == identity.SessionId
                    && childObservation.SessionId == identity.SessionId,
                ["integrity_sids_match"] = rootObservation.IntegritySid is not null
                    && string.Equals(rootObservation.IntegritySid, childObservation.IntegritySid, StringComparison.Ordinal),
                ["root_and_child_medium_integrity"] = rootObservation.IntegrityLevel == "medium"
                    && childObservation.IntegrityLevel == "medium",
                ["root_and_child_not_elevated"] = rootObservation.TokenIsElevated is false
                    && childObservation.TokenIsElevated is false,
                ["root_and_child_job_membership_verified"] = rootObservation.JobMember is true
                    && childObservation.JobMember is true,
                ["root_and_child_process_tokens_verified"] = rootObservation.QueryStatus == "verified"
                    && childObservation.QueryStatus == "verified",
                ["child_parent_is_root"] = childObservation.ParentProcessId == rootPid,
                ["pass"] = tokenChecks,
            };

            bool rootUser32Pass = NativeUser32MarkerPasses(rootPost);
            bool childUser32Pass = NativeUser32MarkerPasses(childPost);
            bool expectedDesktopPass = string.Equals(GetJsonString(rootPost, "window_station"), "WinSta0", StringComparison.OrdinalIgnoreCase)
                && string.Equals(GetJsonString(rootPost, "desktop"), "Default", StringComparison.OrdinalIgnoreCase)
                && string.Equals(GetJsonString(childPost, "window_station"), "WinSta0", StringComparison.OrdinalIgnoreCase)
                && string.Equals(GetJsonString(childPost, "desktop"), "Default", StringComparison.OrdinalIgnoreCase);
            bool sameDesktopPass = string.Equals(GetJsonString(rootPost, "window_station"), GetJsonString(childPost, "window_station"), StringComparison.Ordinal)
                && string.Equals(GetJsonString(rootPost, "desktop"), GetJsonString(childPost, "desktop"), StringComparison.Ordinal);
            bool targetSessionInteractive = identity.LastIdentityReport!.TryGetValue("target_session_is_interactive", out object? interactiveValue)
                && interactiveValue is true;
            result["desktop_checks"] = new Dictionary<string, object?>
            {
                ["root_pre_user32_marker"] = GetJsonString(rootPre, "stage") == "pre_user32" && rootPreContractPass,
                ["child_pre_user32_marker"] = GetJsonString(childPre, "stage") == "pre_user32" && childPreContractPass,
                ["root_user32_load_trigger_and_queries_pass"] = rootUser32Pass,
                ["child_user32_load_trigger_and_queries_pass"] = childUser32Pass,
                ["root_window_station"] = GetJsonString(rootPost, "window_station"),
                ["root_desktop"] = GetJsonString(rootPost, "desktop"),
                ["child_window_station"] = GetJsonString(childPost, "window_station"),
                ["child_desktop"] = GetJsonString(childPost, "desktop"),
                ["target_session_is_interactive"] = targetSessionInteractive,
                ["expected_window_station"] = "WinSta0",
                ["expected_desktop"] = "Default",
                ["both_processes_report_expected_desktop"] = expectedDesktopPass,
                ["root_and_child_report_same_desktop"] = sameDesktopPass,
            };

            bool summaryPass = GetUInt32(rootSummary, "pid") == rootPid
                && GetJsonBoolean(rootSummary, "child_created")
                && GetUInt32(rootSummary, "child_process_id") == childPid
                && GetInt32(rootSummary, "child_create_error") == 0
                && GetInt32(rootSummary, "child_wait_error") == 0
                && GetJsonBoolean(rootSummary, "child_exit_observed")
                && GetInt32(rootSummary, "child_exit_code") == 0;
            result["root_summary_checks"] = new Dictionary<string, object?>
            {
                ["pass"] = summaryPass,
                ["child_exit_code"] = rootSummary["child_exit_code"],
                ["child_exit_observed"] = GetJsonBoolean(rootSummary, "child_exit_observed"),
            };

            rootExitedNaturally = await WaitForRootAsync(job, tracker, identity, TimeSpan.FromSeconds(7))
                .ConfigureAwait(false);
            result["root_exited_naturally"] = rootExitedNaturally;
            if (rootExitedNaturally && NativeMethods.GetExitCodeProcess(job.RootProcessHandle, out uint rootExitCode))
            {
                SetExitCode(result, rootExitCode);
                result["root_exit_code"] = unchecked((int)rootExitCode);
                result["root_exit_code_raw"] = $"0x{rootExitCode:X8}";
                result["diagnostic_completed"] = true;
            }
            else if (!rootExitedNaturally)
            {
                result["diagnostic_outcome"] = "bounded_timeout";
                throw new TimeoutException("The native fixture root did not exit after its bounded child wait.");
            }

            if (!markerContractPass || !tokenChecks || !targetSessionInteractive
                || !rootUser32Pass || !childUser32Pass || !expectedDesktopPass
                || !sameDesktopPass || !summaryPass || result["process_exit_code"] is not int exitCode || exitCode != 0)
            {
                result["diagnostic_outcome"] = "fail; completed evidence did not satisfy the marker, token, interactive-session, User32, desktop, or exit contract";
                throw new NativeApiException("VerifyNativeUser32DiagnosticTokensDesktopAndExit", NativeMethods.ErrorAccessDenied);
            }
            result["diagnostic_outcome"] = "pass";
        }
        catch (Exception exception)
        {
            bodyFailure = exception;
            string markerWaitState = result["marker_wait_outcome"] as string ?? "not_started";
            if (markerWaitState == "waiting")
            {
                bool nativeWaitApiFailure = exception is NativeApiException nativeFailure
                    && (nativeFailure.Api == "WaitForSingleObject.NativeDiagnosticRoot"
                        || nativeFailure.Api == "WaitForSingleObject.NativeDiagnosticRootAtDeadline");
                markerWaitState = nativeWaitApiFailure ? "wait_error" : "marker_pipeline_error";
                result["marker_wait_outcome"] = markerWaitState;
            }
            if (result["diagnostic_outcome"] as string == "unknown")
            {
                result["diagnostic_outcome"] = job is null ? "not_run"
                    : markerWaitState is "wait_error" or "marker_pipeline_error" ? markerWaitState
                    : "incomplete";
            }
            result["failure"] = Failure("native_user32_diagnostic", exception);
        }
        finally
        {
            if (job is not null)
            {
                try
                {
                    await job.StopAndWaitAsync(TimeSpan.FromSeconds(8)).ConfigureAwait(false);
                    uint activeAfter = native.GetActiveProcessCountAfterStop();
                    result["active_processes_after"] = activeAfter;
                    result["cleanup_complete"] = activeAfter == 0;
                    result["cleanup_status"] = activeAfter == 0
                        ? "complete; StopAndWaitAsync drained native diagnostic job"
                        : "failed; active process count nonzero";
                }
                catch (Exception cleanupError)
                {
                    result["cleanup_status"] = "failed; " + cleanupError.GetType().Name;
                    result["cleanup_failure"] = Failure("native_diagnostic_finally_cleanup", cleanupError);
                    try
                    {
                        native.EmergencyTerminateAndDrain(TimeSpan.FromSeconds(8));
                        uint activeAfter = native.GetActiveProcessCountAfterStop();
                        result["active_processes_after"] = activeAfter;
                        result["cleanup_complete"] = activeAfter == 0;
                        if (activeAfter == 0) result["cleanup_status"] = "complete after emergency termination";
                    }
                    catch (Exception emergencyError)
                    {
                        result["cleanup_emergency_failure"] = Failure("native_diagnostic_emergency_cleanup", emergencyError);
                    }
                }
            }
            else
            {
                result["cleanup_status"] = "no job started";
                result["active_processes_after"] = 0;
                result["cleanup_complete"] = true;
            }

            if (launch is not null)
            {
                try
                {
                    (CapturedStream stdout, CapturedStream stderr, bool captureComplete) =
                        await launch.Output.CompleteAsync(TimeSpan.FromSeconds(3)).ConfigureAwait(false);
                    result["output"] = new Dictionary<string, object?>
                    {
                        ["stdout"] = stdout.Summary(),
                        ["stderr"] = stderr.Summary(includeTail: true),
                        ["output_capture_incomplete"] = !captureComplete,
                    };
                }
                catch (Exception captureError)
                {
                    result["output_capture_failure"] = Failure("native_diagnostic_output_capture", captureError);
                }
                await launch.Output.DisposeAsync().ConfigureAwait(false);
            }

            if (job is not null && tracker is not null)
            {
                try
                {
                    if (rootProcessId is uint trackedRootPid)
                    {
                        tracker.CaptureTree(trackedRootPid, job, identity.UserSid, identity.SessionId);
                    }
                }
                catch (Exception trackingError)
                {
                    result["final_process_observation_failure"] = Failure("native_diagnostic_final_process_observation", trackingError);
                }
            }
            job?.Dispose();
            native.Dispose();
            if (tracker is not null)
            {
                result["observed_processes"] = tracker.Processes.Select(process => process.ToDictionary()).ToList();
            }
        }

        bool casePass = bodyFailure is null && rootExitedNaturally
            && result["root_exit_code"] is int verifiedRootExitCode && verifiedRootExitCode == 0
            && result["cleanup_complete"] is true && result["active_processes_after"] is uint active && active == 0
            && result["output"] is Dictionary<string, object?> output
            && output["output_capture_incomplete"] is false
            && !result.ContainsKey("cleanup_failure") && !result.ContainsKey("cleanup_emergency_failure")
            && !result.ContainsKey("final_process_observation_failure");
        result["status"] = casePass ? "pass" : "fail";
        return result;
    }

    private static async Task<string> WaitForNativeDesktopMarkersAsync(
        IReadOnlyDictionary<string, string> markerPaths,
        LeaseProcessJob job,
        ProcessTracker tracker,
        ITargetProcessIdentity identity,
        TimeSpan timeout)
    {
        long deadline = Environment.TickCount64 + (long)Math.Ceiling(timeout.TotalMilliseconds);
        while (Environment.TickCount64 < deadline)
        {
            tracker.CaptureTree(job.RootProcessId, job, identity.UserSid, identity.SessionId);
            if (ClassifyNativeDesktopMarkerWait(markerPaths.Values.All(File.Exists), rootExited: false, deadlineReached: false) == "markers_complete")
            {
                return "markers_complete";
            }
            uint wait = NativeMethods.WaitForSingleObject(job.RootProcessHandle, 0);
            if (wait == NativeMethods.WaitObject0)
            {
                return ClassifyNativeDesktopMarkerWait(markerPaths.Values.All(File.Exists), rootExited: true, deadlineReached: false);
            }
            if (wait != NativeMethods.WaitTimeout) throw LastError("WaitForSingleObject.NativeDiagnosticRoot");
            await Task.Delay(50).ConfigureAwait(false);
        }
        tracker.CaptureTree(job.RootProcessId, job, identity.UserSid, identity.SessionId);
        bool markersComplete = markerPaths.Values.All(File.Exists);
        if (markersComplete) return ClassifyNativeDesktopMarkerWait(markersComplete, rootExited: false, deadlineReached: true);
        uint finalWait = NativeMethods.WaitForSingleObject(job.RootProcessHandle, 0);
        if (finalWait == NativeMethods.WaitObject0) return ClassifyNativeDesktopMarkerWait(markerPaths.Values.All(File.Exists), rootExited: true, deadlineReached: true);
        if (finalWait != NativeMethods.WaitTimeout) throw LastError("WaitForSingleObject.NativeDiagnosticRootAtDeadline");
        return ClassifyNativeDesktopMarkerWait(markersComplete, rootExited: false, deadlineReached: true);
    }

    internal static void ValidateNativeDesktopMarkerWaitClassification()
    {
        (bool MarkersComplete, bool RootExited, bool DeadlineReached, string Expected)[] cases =
        [
            (true, false, false, "markers_complete"),
            (false, true, false, "root_exited_before_markers"),
            (false, false, true, "bounded_timeout"),
            (false, false, false, "waiting"),
        ];
        foreach ((bool markersComplete, bool rootExited, bool deadlineReached, string expected) in cases)
        {
            string actual = ClassifyNativeDesktopMarkerWait(markersComplete, rootExited, deadlineReached);
            if (!string.Equals(actual, expected, StringComparison.Ordinal))
            {
                throw new InvalidOperationException("Native marker wait classification did not preserve the observed process state.");
            }
        }
    }

    private static string ClassifyNativeDesktopMarkerWait(bool markersComplete, bool rootExited, bool deadlineReached)
    {
        if (markersComplete) return "markers_complete";
        if (rootExited) return "root_exited_before_markers";
        if (deadlineReached) return "bounded_timeout";
        return "waiting";
    }

    internal static void ValidateNativeDiagnosticMarkerContract()
    {
        static Dictionary<string, object?> Marker(string kind, string stage, uint pid) => new()
        {
            ["schema"] = "native-desktop-diagnostic/v1",
            ["kind"] = kind,
            ["stage"] = stage,
            ["pid"] = pid,
        };

        Dictionary<string, object?> rootPre = Marker("root", "pre_user32", 101);
        Dictionary<string, object?> rootPost = Marker("root", "post_user32", 101);
        Dictionary<string, object?> childPre = Marker("child", "pre_user32", 202);
        Dictionary<string, object?> childPost = Marker("child", "post_user32", 202);
        Dictionary<string, object?> summary = Marker("root_summary", "summary", 101);
        if (!EvaluateNativeDiagnosticMarkerContract(rootPre, rootPost, childPre, childPost, summary, 101, 202)["pass"])
        {
            throw new InvalidOperationException("Valid native diagnostic markers did not satisfy the marker contract.");
        }

        rootPre["schema"] = "wrong-schema";
        if (EvaluateNativeDiagnosticMarkerContract(rootPre, rootPost, childPre, childPost, summary, 101, 202)["pass"])
        {
            throw new InvalidOperationException("Native diagnostic marker contract accepted an invalid schema.");
        }
        rootPre["schema"] = "native-desktop-diagnostic/v1";
        childPost["pid"] = 303U;
        if (EvaluateNativeDiagnosticMarkerContract(rootPre, rootPost, childPre, childPost, summary, 101, 202)["pass"])
        {
            throw new InvalidOperationException("Native diagnostic marker contract accepted a mismatched child PID.");
        }
    }

    private static Dictionary<string, bool> EvaluateNativeDiagnosticMarkerContract(
        Dictionary<string, object?> rootPre,
        Dictionary<string, object?> rootPost,
        Dictionary<string, object?> childPre,
        Dictionary<string, object?> childPost,
        Dictionary<string, object?> rootSummary,
        uint rootPid,
        uint childPid)
    {
        bool rootPrePass = GetJsonString(rootPre, "schema") == "native-desktop-diagnostic/v1"
            && GetJsonString(rootPre, "kind") == "root"
            && GetJsonString(rootPre, "stage") == "pre_user32"
            && GetUInt32(rootPre, "pid") == rootPid;
        bool rootPostPass = GetJsonString(rootPost, "schema") == "native-desktop-diagnostic/v1"
            && GetJsonString(rootPost, "kind") == "root"
            && GetJsonString(rootPost, "stage") == "post_user32"
            && GetUInt32(rootPost, "pid") == rootPid;
        bool childPrePass = GetJsonString(childPre, "schema") == "native-desktop-diagnostic/v1"
            && GetJsonString(childPre, "kind") == "child"
            && GetJsonString(childPre, "stage") == "pre_user32"
            && GetUInt32(childPre, "pid") == childPid;
        bool childPostPass = GetJsonString(childPost, "schema") == "native-desktop-diagnostic/v1"
            && GetJsonString(childPost, "kind") == "child"
            && GetJsonString(childPost, "stage") == "post_user32"
            && GetUInt32(childPost, "pid") == childPid;
        bool summaryPass = GetJsonString(rootSummary, "schema") == "native-desktop-diagnostic/v1"
            && GetJsonString(rootSummary, "kind") == "root_summary"
            && GetUInt32(rootSummary, "pid") == rootPid;
        return new Dictionary<string, bool>(StringComparer.Ordinal)
        {
            ["root_pre_schema_kind_stage_and_pid_match"] = rootPrePass,
            ["root_post_schema_kind_stage_and_pid_match"] = rootPostPass,
            ["child_pre_schema_kind_stage_and_pid_match"] = childPrePass,
            ["child_post_schema_kind_stage_and_pid_match"] = childPostPass,
            ["root_summary_schema_kind_and_pid_match"] = summaryPass,
            ["root_pre_post_pid_match"] = GetUInt32(rootPre, "pid") == GetUInt32(rootPost, "pid"),
            ["child_pre_post_pid_match"] = GetUInt32(childPre, "pid") == GetUInt32(childPost, "pid"),
            ["pass"] = rootPrePass && rootPostPass && childPrePass && childPostPass && summaryPass,
        };
    }

    private static bool NativeUser32MarkerPasses(Dictionary<string, object?> marker) =>
        GetJsonString(marker, "stage") == "post_user32"
        && GetJsonBoolean(marker, "user32_loaded")
        && GetInt32(marker, "user32_load_error") == 0
        && GetJsonBoolean(marker, "get_sys_color_resolved")
        && GetInt32(marker, "get_sys_color_resolve_error") == 0
        && GetJsonBoolean(marker, "get_sys_color_called")
        && GetJsonBoolean(marker, "get_process_window_station_resolved")
        && GetJsonBoolean(marker, "get_thread_desktop_resolved")
        && GetJsonBoolean(marker, "get_user_object_information_resolved")
        && GetInt32(marker, "station_query_error") == 0
        && GetInt32(marker, "station_name_query_error") == 0
        && GetInt32(marker, "desktop_query_error") == 0
        && GetInt32(marker, "desktop_name_query_error") == 0;

    private static async Task<Dictionary<string, object?>> RunFixtureCaseAsync(
        TargetIdentityContext identity,
        WorkAreaResult workArea,
        string label,
        bool injectException)
    {
        string rootMarkerPath = Path.Combine(workArea.WorkDirectory, $"fixture-{label}-root.json");
        string childMarkerPath = Path.Combine(workArea.WorkDirectory, $"fixture-{label}-child.json");
        var result = new Dictionary<string, object?>
        {
            ["name"] = label,
            ["status"] = "pending",
            ["timed_out"] = false,
            ["process_exit_code"] = "unknown",
            ["process_exit_code_hex"] = "unknown",
            ["process_exit_code_raw"] = "unknown",
            ["injected_exception_observed"] = false,
            ["root_pid"] = null,
            ["child_pid"] = null,
            ["same_sid"] = false,
            ["same_integrity"] = false,
            ["same_session"] = false,
            ["desktop_checks"] = null,
            ["cleanup_status"] = "not_started",
            ["active_processes_after"] = null,
            ["cleanup_complete"] = false,
            ["observed_processes"] = new List<Dictionary<string, object?>>(),
            ["output"] = null,
            ["failure"] = null,
        };
        TrackedJobNative native = new();
        SuspendedLaunch? launch = null;
        LeaseProcessJob? job = null;
        ProcessTracker? tracker = null;
        var heldProcessHandles = new List<SafeProcessHandle>();
        Exception? bodyFailure = null;
        bool expectedException = false;
        try
        {
            job = LeaseProcessJob.Start(() =>
            {
                launch = TargetProcessLauncher.CreateSuspended(identity.Token, identity.Environment,
                    Environment.ProcessPath!, ["--fixture-root", rootMarkerPath, childMarkerPath], workArea.WorkDirectory,
                    TargetProcessLauncher.SystemSelectedDesktop);
                return launch.Process;
            }, native);
            launch!.Output.Start();
            tracker = new ProcessTracker(native);
            ((Dictionary<string, object?>)identity.LastIdentityReport!["desktop"]!)["fixture_launch_desktop"] = new
            {
                selection = "system-selected by Windows logon-session rules; effective station/desktop unknown until markers",
                root_pid = job.RootProcessId,
                lpDesktop = TargetProcessLauncher.SystemSelectedDesktop,
            };

            (Dictionary<string, object?> rootMarker, Dictionary<string, object?> childMarker) =
                await WaitForFixtureMarkersAsync(rootMarkerPath, childMarkerPath, job, tracker, identity, TimeSpan.FromSeconds(8))
                    .ConfigureAwait(false);
            uint rootPid = GetUInt32(rootMarker, "pid");
            uint childPid = GetUInt32(childMarker, "pid");
            bool targetSessionInteractive = identity.LastIdentityReport!.TryGetValue("target_session_is_interactive", out object? interactiveValue)
                && interactiveValue is true;
            string? rootStation = GetJsonString(rootMarker, "window_station");
            string? rootDesktop = GetJsonString(rootMarker, "desktop");
            string? childStation = GetJsonString(childMarker, "window_station");
            string? childDesktop = GetJsonString(childMarker, "desktop");
            result["root_pid"] = rootPid;
            result["child_pid"] = childPid;
            result["same_sid"] = string.Equals(GetJsonString(rootMarker, "sid"), GetJsonString(childMarker, "sid"), StringComparison.Ordinal)
                && string.Equals(GetJsonString(rootMarker, "sid"), identity.UserSid, StringComparison.Ordinal);
            result["same_session"] = GetInt32(rootMarker, "session_id") == identity.SessionId
                && GetInt32(childMarker, "session_id") == identity.SessionId;
            result["desktop_checks"] = new Dictionary<string, object?>
            {
                ["root_window_station"] = GetJsonString(rootMarker, "window_station"),
                ["root_desktop"] = GetJsonString(rootMarker, "desktop"),
                ["child_window_station"] = GetJsonString(childMarker, "window_station"),
                ["child_desktop"] = GetJsonString(childMarker, "desktop"),
                ["launch_lpDesktop"] = TargetProcessLauncher.SystemSelectedDesktop,
                ["target_session_is_interactive"] = targetSessionInteractive,
                ["expected_window_station"] = targetSessionInteractive ? "WinSta0" : null,
                ["expected_desktop"] = targetSessionInteractive ? "Default" : null,
                ["root_station_nonempty"] = !string.IsNullOrWhiteSpace(rootStation),
                ["root_desktop_nonempty"] = !string.IsNullOrWhiteSpace(rootDesktop),
                ["child_station_nonempty"] = !string.IsNullOrWhiteSpace(childStation),
                ["child_desktop_nonempty"] = !string.IsNullOrWhiteSpace(childDesktop),
                ["root_station_expected"] = targetSessionInteractive && string.Equals(rootStation, "WinSta0", StringComparison.OrdinalIgnoreCase),
                ["root_desktop_expected"] = targetSessionInteractive && string.Equals(rootDesktop, "Default", StringComparison.OrdinalIgnoreCase),
                ["child_station_expected"] = targetSessionInteractive && string.Equals(childStation, "WinSta0", StringComparison.OrdinalIgnoreCase),
                ["child_desktop_expected"] = targetSessionInteractive && string.Equals(childDesktop, "Default", StringComparison.OrdinalIgnoreCase),
                ["same_window_station"] = string.Equals(rootStation, childStation, StringComparison.Ordinal),
                ["same_desktop"] = string.Equals(rootDesktop, childDesktop, StringComparison.Ordinal),
            };
            tracker.CaptureTree(job.RootProcessId, job, identity.UserSid, identity.SessionId);
            ProcessObservation rootObservation = FindObservation(tracker, rootPid);
            ProcessObservation childObservation = FindObservation(tracker, childPid);
            result["same_integrity"] = rootObservation.IntegritySid is not null
                && string.Equals(rootObservation.IntegritySid, childObservation.IntegritySid, StringComparison.Ordinal);
            result["integrity_level"] = rootObservation.IntegrityLevel;
            result["not_elevated"] = rootObservation.TokenIsElevated is false
                && childObservation.TokenIsElevated is false;
            heldProcessHandles.Add(OpenProcessForExitVerification(rootPid));
            heldProcessHandles.Add(OpenProcessForExitVerification(childPid));

            bool markerChecks = result["same_sid"] is true && result["same_session"] is true
                && result["same_integrity"] is true
                && result["not_elevated"] is true
                && string.Equals(rootObservation.IntegrityLevel, "medium", StringComparison.Ordinal)
                && string.Equals(childObservation.IntegrityLevel, "medium", StringComparison.Ordinal)
                && ((Dictionary<string, object?>)result["desktop_checks"]!)["root_station_nonempty"] is true
                && ((Dictionary<string, object?>)result["desktop_checks"]!)["root_desktop_nonempty"] is true
                && ((Dictionary<string, object?>)result["desktop_checks"]!)["child_station_nonempty"] is true
                && ((Dictionary<string, object?>)result["desktop_checks"]!)["child_desktop_nonempty"] is true
                && ((Dictionary<string, object?>)result["desktop_checks"]!)["target_session_is_interactive"] is true
                && ((Dictionary<string, object?>)result["desktop_checks"]!)["root_station_expected"] is true
                && ((Dictionary<string, object?>)result["desktop_checks"]!)["root_desktop_expected"] is true
                && ((Dictionary<string, object?>)result["desktop_checks"]!)["child_station_expected"] is true
                && ((Dictionary<string, object?>)result["desktop_checks"]!)["child_desktop_expected"] is true
                && ((Dictionary<string, object?>)result["desktop_checks"]!)["same_window_station"] is true
                && ((Dictionary<string, object?>)result["desktop_checks"]!)["same_desktop"] is true
                && rootObservation.JobMember is true && childObservation.JobMember is true
                && rootObservation.QueryStatus == "verified" && childObservation.QueryStatus == "verified";
            if (!markerChecks)
            {
                throw new NativeApiException("VerifyFixtureTokensJobAndDesktop", NativeMethods.ErrorAccessDenied);
            }
            ((Dictionary<string, object?>)identity.LastIdentityReport!["desktop"]!)[label] = result["desktop_checks"];

            if (injectException)
            {
                throw new InjectedFixtureException();
            }

            bool rootExitedWithinTimeout = await WaitForRootAsync(job, tracker, identity, TimeSpan.FromMilliseconds(500))
                .ConfigureAwait(false);
            result["wait_timeout_observed"] = !rootExitedWithinTimeout;
            result["timed_out"] = !rootExitedWithinTimeout;
            if (rootExitedWithinTimeout)
            {
                throw new InvalidOperationException("The fixture root exited instead of reaching the bounded wait timeout.");
            }
        }
        catch (InjectedFixtureException)
        {
            expectedException = true;
            result["injected_exception_observed"] = true;
        }
        catch (Exception exception)
        {
            bodyFailure = exception;
            Dictionary<string, object?> failure = Failure("fixture_body", exception);
            if (exception.Data["fixture_root_exit_code_raw"] is string exitCode
                && IsSafeHexExitCode(exitCode))
            {
                if (TryParseRawProcessExitCode(exitCode, out int signedExitCode))
                {
                    SetProcessExitCodeFields(result, signedExitCode);
                    SetProcessExitCodeFields(failure, signedExitCode);
                }
                else
                {
                    failure["process_exit_code_raw"] = exitCode;
                }
            }
            if (exception.Data["fixture_root_exit_code_query_error"] is int queryError)
            {
                failure["process_exit_code_query_win32_error"] = queryError;
            }
            result["failure"] = failure;
        }
        finally
        {
            if (job is not null)
            {
                try
                {
                    await job.StopAndWaitAsync(TimeSpan.FromSeconds(8)).ConfigureAwait(false);
                    uint activeAfter = native.GetActiveProcessCountAfterStop();
                    result["active_processes_after"] = activeAfter;
                    result["cleanup_complete"] = activeAfter == 0;
                    result["cleanup_status"] = activeAfter == 0 ? "complete; StopAndWaitAsync drained job" : "failed; active count nonzero";
                }
                catch (Exception cleanupError)
                {
                    result["cleanup_status"] = "failed; " + cleanupError.GetType().Name;
                    result["cleanup_failure"] = Failure("fixture_finally_cleanup", cleanupError);
                    try
                    {
                        native.EmergencyTerminateAndDrain(TimeSpan.FromSeconds(8));
                        uint activeAfter = native.GetActiveProcessCountAfterStop();
                        result["active_processes_after"] = activeAfter;
                        result["cleanup_complete"] = activeAfter == 0;
                        if (activeAfter == 0) result["cleanup_status"] = "complete after emergency termination";
                    }
                    catch (Exception emergencyError)
                    {
                        result["cleanup_emergency_failure"] = Failure("fixture_emergency_cleanup", emergencyError);
                    }
                }
            }
            else
            {
                result["cleanup_status"] = "no job started";
                result["active_processes_after"] = 0;
                result["cleanup_complete"] = true;
            }

            if (launch is not null)
            {
                try
                {
                    (CapturedStream stdout, CapturedStream stderr, bool captureComplete) =
                        await launch.Output.CompleteAsync(TimeSpan.FromSeconds(3)).ConfigureAwait(false);
                    result["output"] = new Dictionary<string, object?>
                    {
                        ["stdout"] = stdout.Summary(),
                        ["stderr"] = stderr.Summary(includeTail: true),
                        ["output_capture_incomplete"] = !captureComplete,
                    };
                }
                catch (Exception captureError)
                {
                    result["output_capture_failure"] = Failure("fixture_output_capture", captureError);
                }
                await launch.Output.DisposeAsync().ConfigureAwait(false);
            }

            bool allSignalsVerified = true;
            foreach (SafeProcessHandle processHandle in heldProcessHandles)
            {
                allSignalsVerified &= !processHandle.IsInvalid
                    && NativeMethods.WaitForSingleObject(processHandle, 3000) == NativeMethods.WaitObject0;
                processHandle.Dispose();
            }
            result["signal_exit_verified"] = heldProcessHandles.Count == 2 && allSignalsVerified;
            job?.Dispose();
            native.Dispose();
            if (tracker is not null)
            {
                result["observed_processes"] = tracker.Processes.Select(process => process.ToDictionary()).ToList();
            }
        }

        if (bodyFailure is not null)
        {
            result["status"] = "fail";
            return result;
        }
        bool casePass = injectException
            ? expectedException && result["injected_exception_observed"] is true
            : result["timed_out"] is true;
        casePass &= !result.ContainsKey("cleanup_failure") && !result.ContainsKey("cleanup_emergency_failure");
        casePass &= result["cleanup_complete"] is true && result["active_processes_after"] is uint active && active == 0
            && result["signal_exit_verified"] is true && result["output"] is Dictionary<string, object?> output
            && output["output_capture_incomplete"] is false;
        result["status"] = casePass ? "pass" : "fail";
        return result;
    }

    private static async Task<Dictionary<string, object?>> RunProbeAsync(
        HelperOptions options,
        TargetIdentityContext identity,
        WorkAreaResult workArea)
    {
        string probeReportPath = Path.Combine(workArea.WorkDirectory, "process-singleton-probe.json");
        string powershellPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),
            "WindowsPowerShell", "v1.0", "powershell.exe");
        var arguments = new[]
        {
            "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", options.ProbeScript!,
            "-ProfileDirectory", workArea.ProfileDirectory,
            "-OutputPath", probeReportPath,
            "-ExpectedUserSid", identity.UserSid,
            "-ExpectedSessionId", identity.SessionId.ToString(System.Globalization.CultureInfo.InvariantCulture),
        };
        Dictionary<string, object?> observation = await RunSupervisedProcessAsync(identity, workArea.WorkDirectory,
            powershellPath, arguments, options.TimeoutSeconds,
            TargetProcessLauncher.InteractiveDefaultDesktop).ConfigureAwait(false);
        int? processExitCode = observation["process_exit_code"] is int exitCodeValue ? exitCodeValue : null;
        Dictionary<string, object?>? probeJson = null;
        if (File.Exists(probeReportPath))
        {
            try
            {
                await using FileStream input = File.OpenRead(probeReportPath);
                probeJson = await JsonSerializer.DeserializeAsync<Dictionary<string, object?>>(input).ConfigureAwait(false);
            }
            catch (Exception parseError)
            {
                observation["report_parse_failure"] = Failure("probe_report_parse", parseError);
            }
        }
        bool probeReportedPass = probeJson is not null && TryGetJsonString(probeJson, "status") == "pass";
        List<Dictionary<string, object?>> observedProcesses =
            (List<Dictionary<string, object?>>)observation["observed_processes"]!;
        Dictionary<string, object?> tokenVerification = VerifyObservedNotElevated(
            observedProcesses, observation["root_pid"] is uint rootPid ? rootPid : 0);
        string status = processExitCode == 0 && probeReportedPass && observation["timed_out"] is false
            && observation["failure"] is null && observation["output_capture_incomplete"] is false
            && tokenVerification["pass"] is true ? "pass" : "fail";
        string? evidencePath = null;
        string? evidenceHash = null;
        long? evidenceBytes = null;
        object? copyFailure = null;
        if (probeJson is not null)
        {
            evidencePath = Path.Combine(options.EvidenceDirectory!, "process-singleton-probe.json");
            try
            {
                CopyEvidenceFile(probeReportPath, evidencePath, out evidenceBytes, out evidenceHash);
            }
            catch (Exception exception)
            {
                copyFailure = Failure("probe_evidence_copy", exception);
                status = "fail";
            }
        }
        object? probeFailure = observation["failure"] ?? (status == "pass" ? null : new Dictionary<string, object?>
        {
            ["stage"] = processExitCode is null ? "probe_exit_unknown" : processExitCode == 0 ? "probe_status_not_pass" : "probe_nonzero_exit",
            ["win32_error"] = null,
            ["message"] = "Probe status requires process exit code 0, report status pass, and complete non-timeout execution.",
        });
        if (probeFailure is Dictionary<string, object?> probeFailureFields)
        {
            AddProcessExitOutcomeToFailure(probeFailureFields, processExitCode, observation.GetValueOrDefault("timed_out"));
        }
        return new Dictionary<string, object?>
        {
            ["status"] = status,
            ["process_exit_code"] = processExitCode is int knownExitCode ? knownExitCode : "unknown",
            ["process_exit_code_hex"] = FormatProcessExitCodeHex(processExitCode),
            ["process_exit_code_raw"] = FormatProcessExitCodeHex(processExitCode),
            ["launch_lpDesktop"] = TargetProcessLauncher.InteractiveDefaultDesktop,
            ["timed_out"] = observation["timed_out"],
            ["report_available"] = probeJson is not null,
            ["report_status"] = probeReportedPass ? "pass" : probeJson is null ? "unknown" : TryGetJsonString(probeJson, "status"),
            ["report_path"] = evidencePath,
            ["report_bytes"] = evidenceBytes,
            ["report_sha256"] = evidenceHash,
            ["staged_report_path"] = probeJson is null ? probeReportPath : null,
            ["command_line"] = BuildCommandLine(powershellPath,
            [
                "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", options.ProbeScript!,
                "-ProfileDirectory", workArea.ProfileDirectory,
                "-OutputPath", probeReportPath,
                "-ExpectedUserSid", "<redacted>",
                "-ExpectedSessionId", identity.SessionId.ToString(System.Globalization.CultureInfo.InvariantCulture),
            ]),
            ["root_pid"] = observation["root_pid"],
            ["stdout"] = observation["stdout"],
            ["stderr"] = observation["stderr"],
            ["output_capture_incomplete"] = observation["output_capture_incomplete"],
            ["process_token_verification"] = tokenVerification,
            ["cleanup_status"] = observation["cleanup_status"],
            ["active_processes_after"] = observation["active_processes_after"],
            ["cleanup_complete"] = observation["cleanup_complete"],
            ["observed_processes"] = observation["observed_processes"],
            ["evidence_copy_failure"] = copyFailure,
            ["failure"] = probeFailure,
        };
    }

    private static async Task<Dictionary<string, object?>> RunBrowserAsync(
        HelperOptions options,
        TargetIdentityContext identity,
        WorkAreaResult workArea)
    {
        string screenshotStagedPath = Path.Combine(workArea.WorkDirectory, "controlled-page.png");
        if (File.Exists(screenshotStagedPath))
        {
            throw new NativeApiException("ScreenshotPath.MustBeNew", NativeMethods.ErrorAlreadyExists);
        }
        string pageUri = new Uri(Path.GetFullPath(options.TestPage!)).AbsoluteUri;
        string[] arguments =
        [
            "--headless=new",
            "--disable-gpu",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-extensions",
            "--disable-sync",
            "--no-first-run",
            "--no-default-browser-check",
            "--enable-logging=stderr",
            "--user-data-dir=" + workArea.ProfileDirectory,
            "--window-size=800,600",
            "--screenshot=" + screenshotStagedPath,
            "--dump-dom",
            pageUri,
        ];
        Dictionary<string, object?> observation = await RunSupervisedProcessAsync(identity, workArea.WorkDirectory,
            options.BrowserPath!, arguments, options.TimeoutSeconds).ConfigureAwait(false);
        CapturedStream? stdout = observation["stdout_data"] as CapturedStream;
        CapturedStream? stderr = observation["stderr_data"] as CapturedStream;
        bool markerFound = stdout?.Text.Contains(ControlledDomMarker, StringComparison.Ordinal) == true;
        List<Dictionary<string, object?>> observedProcesses =
            (List<Dictionary<string, object?>>)observation["observed_processes"]!;
        Dictionary<string, object?> tokenVerification = VerifyObservedBrowserTokens(
            observedProcesses, observation["root_pid"] is uint rootPid ? rootPid : 0,
            identity.UserSid, identity.SessionId);

        string stderrStagedPath = Path.Combine(workArea.WorkDirectory, "browser-stderr.log");
        string stderrEvidencePath = Path.Combine(options.EvidenceDirectory!, "browser-stderr.log");
        string? stderrLogHash = null;
        long? stderrLogBytes = null;
        string? stderrEvidenceHash = null;
        long? stderrEvidenceBytes = null;
        object? stderrEvidenceFailure = null;
        if (stderr is not null)
        {
            try
            {
                if (File.Exists(stderrStagedPath))
                    throw new NativeApiException("BrowserStderr.MustBeNew", NativeMethods.ErrorAlreadyExists);
                string safeLog = SanitizeBrowserStderr(stderr.Text);
                byte[] logBytes = System.Text.Encoding.UTF8.GetBytes(safeLog);
                await File.WriteAllBytesAsync(stderrStagedPath, logBytes).ConfigureAwait(false);
                stderrLogBytes = logBytes.LongLength;
                stderrLogHash = Convert.ToHexString(SHA256.HashData(logBytes)).ToLowerInvariant();
                CopyEvidenceFile(stderrStagedPath, stderrEvidencePath,
                    out stderrEvidenceBytes, out stderrEvidenceHash);
            }
            catch (Exception exception)
            {
                stderrEvidenceFailure = Failure("browser_stderr_evidence", exception);
            }
        }
        string? stagedScreenshotHash = null;
        long? stagedScreenshotBytes = null;
        string? evidenceScreenshotPath = null;
        string? evidenceScreenshotHash = null;
        long? evidenceScreenshotBytes = null;
        object? screenshotCopyFailure = null;
        if (File.Exists(screenshotStagedPath))
        {
            try
            {
                stagedScreenshotHash = HashFile(screenshotStagedPath, out long bytes);
                stagedScreenshotBytes = bytes;
                evidenceScreenshotPath = Path.Combine(options.EvidenceDirectory!, "controlled-page.png");
                CopyEvidenceFile(screenshotStagedPath, evidenceScreenshotPath, out evidenceScreenshotBytes, out evidenceScreenshotHash);
            }
            catch (Exception exception)
            {
                screenshotCopyFailure = Failure("screenshot_evidence_copy", exception);
            }
        }
        bool screenshotValid = stagedScreenshotHash is { Length: 64 } && evidenceScreenshotHash == stagedScreenshotHash;
        bool stderrEvidenceValid = stderr is not null && stderrEvidenceFailure is null
            && stderrEvidenceHash is { Length: 64 } && stderrEvidenceHash == stderrLogHash;
        string pageStatus = markerFound && screenshotValid && observation["timed_out"] is false
            && observation["failure"] is null && screenshotCopyFailure is null && stderrEvidenceValid
            && observation["output_capture_incomplete"] is false && tokenVerification["pass"] is true
            && observation["process_exit_code"] is int exitCode && exitCode == 0
            ? "pass"
            : "fail";
        var page = new Dictionary<string, object?>
        {
            ["status"] = pageStatus,
            ["controlled_dom_marker"] = ControlledDomMarker,
            ["dom_marker_found"] = markerFound,
            ["dom_stdout_bytes"] = stdout?.Bytes,
            ["dom_stdout_sha256"] = stdout?.Sha256,
            ["dom_body_recorded"] = false,
            ["screenshot_path"] = evidenceScreenshotPath,
            ["screenshot_bytes"] = evidenceScreenshotBytes,
            ["screenshot_sha256"] = evidenceScreenshotHash,
            ["screenshot_staged_path"] = screenshotStagedPath,
            ["screenshot_staged_sha256"] = stagedScreenshotHash,
            ["copy_sha256_match"] = evidenceScreenshotHash is not null && evidenceScreenshotHash == stagedScreenshotHash,
            ["evidence_copy_failure"] = screenshotCopyFailure,
            ["process_token_verification"] = tokenVerification,
            ["observed_processes_are_snapshot"] = true,
            ["enumeration_is_complete"] = false,
            ["output_capture_incomplete"] = observation["output_capture_incomplete"],
            ["stderr_log_path"] = stderrEvidenceHash is null ? null : stderrEvidencePath,
            ["stderr_log_bytes"] = stderrEvidenceBytes,
            ["stderr_log_sha256"] = stderrEvidenceHash,
            ["stderr_log_staged_path"] = stderrStagedPath,
            ["stderr_log_staged_bytes"] = stderrLogBytes,
            ["stderr_log_staged_sha256"] = stderrLogHash,
            ["stderr_capture_bytes"] = stderr?.Bytes,
            ["stderr_capture_sha256"] = stderr?.Sha256,
            ["stderr_capture_truncated"] = stderr?.Truncated,
            ["stderr_evidence_copy_failure"] = stderrEvidenceFailure,
        };
        object? browserFailure = observation["failure"] ?? screenshotCopyFailure ?? stderrEvidenceFailure;
        int? browserExitCode = observation.GetValueOrDefault("process_exit_code") is int knownBrowserExitCode
            ? knownBrowserExitCode
            : null;
        object? browserTimedOut = observation.GetValueOrDefault("timed_out");
        if (browserFailure is null && (browserTimedOut is true || browserExitCode is not 0))
        {
            browserFailure = new Dictionary<string, object?>
            {
                ["stage"] = browserTimedOut is true ? "browser_timeout" : browserExitCode is int ? "browser_nonzero_exit" : "browser_exit_unknown",
                ["win32_error"] = null,
                ["message"] = "Browser status requires exit code 0 and complete non-timeout execution.",
            };
        }
        if (browserFailure is Dictionary<string, object?> browserFailureFields)
        {
            AddProcessExitOutcomeToFailure(browserFailureFields, browserExitCode, browserTimedOut);
        }
        return new Dictionary<string, object?>
        {
            ["process_id"] = observation["root_pid"],
            ["process_exit_code"] = observation["process_exit_code"] is int observedExitCode ? observedExitCode : "unknown",
            ["process_exit_code_hex"] = observation["process_exit_code_hex"] as string ?? "unknown",
            ["process_exit_code_raw"] = observation["process_exit_code_raw"] as string ?? "unknown",
            ["timed_out"] = observation["timed_out"],
            ["status"] = observation["process_exit_code"] is int browserReportedExitCode && browserReportedExitCode == 0
                && observation["timed_out"] is false ? "exited_zero" : "failed_or_timed_out",
            ["command_line"] = BuildCommandLine(options.BrowserPath!, arguments),
            ["stdout"] = observation["stdout"],
            ["stderr"] = observation["stderr"],
            ["output_capture_incomplete"] = observation["output_capture_incomplete"],
            ["page"] = page,
            ["cleanup_status"] = observation["cleanup_status"],
            ["active_processes_after"] = observation["active_processes_after"],
            ["cleanup_complete"] = observation["cleanup_complete"],
            ["observed_processes"] = observation["observed_processes"],
            ["observed_processes_are_snapshot"] = true,
            ["enumeration_is_complete"] = false,
            ["failure"] = browserFailure,
        };
    }

    private static Dictionary<string, object?> VerifyObservedBrowserTokens(
        IReadOnlyList<Dictionary<string, object?>> observed,
        uint rootPid,
        string expectedSid,
        int expectedSession)
    {
        bool IsExpected(Dictionary<string, object?> process) =>
            TryGetUInt32(process, "pid", out _)
            && string.Equals(TryGetString(process, "query_status"), "verified", StringComparison.Ordinal)
            && string.Equals(TryGetString(process, "sid"), expectedSid, StringComparison.Ordinal)
            && TryGetInt32(process, "session_id", out int sessionId) && sessionId == expectedSession
            && TryGetBoolean(process, "job_member", out bool jobMember) && jobMember
            && TryGetBoolean(process, "not_elevated", out bool notElevated) && notElevated
            && string.Equals(TryGetString(process, "integrity_level"), "medium", StringComparison.Ordinal);

        Dictionary<string, object?>? root = observed.FirstOrDefault(process =>
            TryGetUInt32(process, "pid", out uint pid) && pid == rootPid);
        List<Dictionary<string, object?>> children = observed.Where(process =>
            TryGetUInt32(process, "pid", out uint pid) && pid != rootPid).ToList();
        int verifiedChildren = children.Count(IsExpected);
        bool rootVerified = root is not null && IsExpected(root);
        bool allObservedVerified = observed.Count > 0 && observed.All(IsExpected);
        int exitedUnqueryableTransientCount = observed.Count(IsExitedUnqueryableTransient);
        bool allStillLiveVerified = observed.Count > 0
            && observed.Where(process => !IsExitedUnqueryableTransient(process)).All(IsExpected);
        List<Dictionary<string, object?>> exitedUnqueryableTransients = observed
            .Where(IsExitedUnqueryableTransient)
            .Select(process => new Dictionary<string, object?>
            {
                ["pid"] = process.GetValueOrDefault("pid"),
                ["parent_pid"] = process.GetValueOrDefault("parent_pid"),
                ["query_status"] = process.GetValueOrDefault("query_status"),
                ["win32_error"] = process.GetValueOrDefault("win32_error"),
                ["exited_event_observed"] = process.GetValueOrDefault("exited"),
            }).ToList();
        bool pass = rootVerified && verifiedChildren >= 1 && allStillLiveVerified;
        return new Dictionary<string, object?>
        {
            ["pass"] = pass,
            ["root_pid"] = rootPid == 0 ? null : rootPid,
            ["root_verified"] = rootVerified,
            ["observed_child_count"] = children.Count,
            ["verified_child_count"] = verifiedChildren,
            ["all_observed_verified"] = allObservedVerified,
            ["all_still_live_observed_verified"] = allStillLiveVerified,
            ["exited_unqueryable_transient_count"] = exitedUnqueryableTransientCount,
            ["exited_unqueryable_transients"] = exitedUnqueryableTransients,
            ["required_sid"] = expectedSid,
            ["required_session_id"] = expectedSession,
            ["required_integrity_level"] = "medium",
            ["required_not_elevated"] = true,
            ["required_job_member"] = true,
            ["observed_processes_are_snapshot"] = true,
            ["enumeration_is_complete"] = false,
        };
    }

    private static Dictionary<string, object?> VerifyObservedNotElevated(
        IReadOnlyList<Dictionary<string, object?>> observed,
        uint rootPid)
    {
        Dictionary<string, object?>? root = observed.FirstOrDefault(process =>
            TryGetUInt32(process, "pid", out uint pid) && pid == rootPid);
        bool rootNotElevated = root is not null
            && TryGetBoolean(root, "not_elevated", out bool notElevated) && notElevated;
        bool allLiveNotElevated = observed.Count > 0 && observed
            .Where(process => !IsExitedUnqueryableTransient(process))
            .All(process => TryGetBoolean(process, "not_elevated", out bool notElevated) && notElevated);
        int exitedUnqueryableTransientCount = observed.Count(IsExitedUnqueryableTransient);
        return new Dictionary<string, object?>
        {
            ["pass"] = rootNotElevated && allLiveNotElevated,
            ["root_pid"] = rootPid == 0 ? null : rootPid,
            ["root_not_elevated"] = rootNotElevated,
            ["all_still_live_not_elevated"] = allLiveNotElevated,
            ["observed_process_count"] = observed.Count,
            ["exited_unqueryable_transient_count"] = exitedUnqueryableTransientCount,
            ["required_not_elevated"] = true,
            ["observed_processes_are_snapshot"] = true,
            ["enumeration_is_complete"] = false,
        };
    }

    private static bool IsExitedUnqueryableTransient(Dictionary<string, object?> process) =>
        TryGetBoolean(process, "exited", out bool exited) && exited
        && string.Equals(TryGetString(process, "query_status"), "process could not be opened for query", StringComparison.Ordinal)
        && TryGetInt32(process, "win32_error", out int error) && error != 0;

    private static string SanitizeBrowserStderr(string text)
    {
        string[] lines = text.Split(['\r', '\n']);
        return string.Join(Environment.NewLine, lines.Select(line =>
        {
            string lower = line.ToLowerInvariant();
            if (lower.Contains("http://", StringComparison.Ordinal)
                || lower.Contains("https://", StringComparison.Ordinal)
                || lower.Contains("cookie", StringComparison.Ordinal)
                || lower.Contains("authorization", StringComparison.Ordinal)
                || lower.Contains("bearer ", StringComparison.Ordinal)
                || lower.Contains("password", StringComparison.Ordinal)
                || lower.Contains("signature", StringComparison.Ordinal)
                || lower.Contains("token=", StringComparison.Ordinal))
            {
                return "[redacted sensitive-looking browser stderr line]";
            }
            return line.Length <= 4096 ? line : line[..4096];
        }));
    }

    private static bool TryGetUInt32(Dictionary<string, object?> value, string key, out uint result)
    {
        object? raw = value.GetValueOrDefault(key);
        switch (raw)
        {
            case uint typed: result = typed; return true;
            case int typed when typed >= 0: result = (uint)typed; return true;
            case JsonElement element when element.TryGetUInt32(out uint parsed): result = parsed; return true;
            default: result = 0; return false;
        }
    }

    private static bool TryGetInt32(Dictionary<string, object?> value, string key, out int result)
    {
        object? raw = value.GetValueOrDefault(key);
        switch (raw)
        {
            case int typed: result = typed; return true;
            case uint typed when typed <= int.MaxValue: result = (int)typed; return true;
            case JsonElement element when element.TryGetInt32(out int parsed): result = parsed; return true;
            default: result = 0; return false;
        }
    }

    private static bool TryGetBoolean(Dictionary<string, object?> value, string key, out bool result)
    {
        object? raw = value.GetValueOrDefault(key);
        switch (raw)
        {
            case bool typed: result = typed; return true;
            case JsonElement element when element.ValueKind == JsonValueKind.True: result = true; return true;
            case JsonElement element when element.ValueKind == JsonValueKind.False: result = false; return true;
            default: result = false; return false;
        }
    }

    private static string? TryGetString(Dictionary<string, object?> value, string key) => value.GetValueOrDefault(key) as string;

    private static async Task<Dictionary<string, object?>> RunSupervisedProcessAsync(
        ITargetProcessIdentity identity,
        string currentDirectory,
        string applicationPath,
        IReadOnlyList<string> arguments,
        int timeoutSeconds,
        string? lpDesktop = null)
    {
        TrackedJobNative native = new();
        SuspendedLaunch? launch = null;
        LeaseProcessJob? job = null;
        SafeNativeHandle? rootExitMonitor = null;
        ProcessTracker? tracker = null;
        var result = new Dictionary<string, object?>
        {
            ["root_pid"] = null,
            ["process_exit_code"] = null,
            ["process_exit_code_hex"] = "unknown",
            ["process_exit_code_raw"] = "unknown",
            ["timed_out"] = false,
            ["stdout"] = null,
            ["stderr"] = null,
            ["stdout_data"] = null,
            ["cleanup_status"] = "not_started",
            ["active_processes_after"] = null,
            ["cleanup_complete"] = false,
            ["observed_processes"] = new List<Dictionary<string, object?>>(),
            ["failure"] = null,
        };
        try
        {
            job = LeaseProcessJob.Start(() =>
            {
                launch = TargetProcessLauncher.CreateSuspended(identity.Token, identity.Environment,
                    applicationPath, arguments, currentDirectory,
                    lpDesktop ?? TargetProcessLauncher.SystemSelectedDesktop);
                return launch.Process;
            }, native);
            result["root_pid"] = job.RootProcessId;
            rootExitMonitor = DuplicateProcessHandle(job.RootProcessHandle, "DuplicateHandle.RootExitMonitor");
            launch!.Output.Start();
            tracker = new ProcessTracker(native);
            bool exited = await WaitForRootAsync(job, tracker, identity, TimeSpan.FromSeconds(timeoutSeconds))
                .ConfigureAwait(false);
            result["timed_out"] = !exited;
            if (exited && NativeMethods.GetExitCodeProcess(job.RootProcessHandle, out uint rawExitCode))
            {
                SetExitCode(result, rawExitCode);
            }
            else if (exited)
            {
                result["failure"] = Failure("GetExitCodeProcess", LastError("GetExitCodeProcess"));
            }
        }
        catch (Exception exception)
        {
            result["failure"] = Failure("supervised_process", exception);
        }
        finally
        {
            if (job is not null)
            {
                try
                {
                    await job.StopAndWaitAsync(TimeSpan.FromSeconds(10)).ConfigureAwait(false);
                    uint activeAfter = native.GetActiveProcessCountAfterStop();
                    result["active_processes_after"] = activeAfter;
                    result["cleanup_complete"] = activeAfter == 0;
                    result["cleanup_status"] = activeAfter == 0 ? "complete; StopAndWaitAsync drained job" : "failed; active count nonzero";
                }
                catch (Exception cleanupError)
                {
                    result["failure"] ??= Failure("job_cleanup", cleanupError);
                    result["cleanup_status"] = "failed; " + cleanupError.GetType().Name;
                    try
                    {
                        native.EmergencyTerminateAndDrain(TimeSpan.FromSeconds(10));
                        uint activeAfter = native.GetActiveProcessCountAfterStop();
                        result["active_processes_after"] = activeAfter;
                        result["cleanup_complete"] = activeAfter == 0;
                        if (activeAfter == 0) result["cleanup_status"] = "complete after emergency termination";
                    }
                    catch (Exception emergencyError)
                    {
                        result["failure_emergency_cleanup"] = Failure("job_emergency_cleanup", emergencyError);
                    }
                }
            }
            else
            {
                result["active_processes_after"] = 0;
                result["cleanup_complete"] = true;
                result["cleanup_status"] = "no job started";
            }
            if (rootExitMonitor is not null && result["process_exit_code"] is null)
            {
                using var monitorProcess = new SafeProcessHandle(rootExitMonitor.DangerousGetHandle(), ownsHandle: false);
                if (NativeMethods.WaitForSingleObject(monitorProcess, 0) == NativeMethods.WaitObject0
                    && NativeMethods.GetExitCodeProcess(monitorProcess, out uint postCleanupExitCode))
                {
                    SetExitCode(result, postCleanupExitCode);
                    result["process_exit_code_observed_after_job_cleanup"] = true;
                }
                else
                {
                    result["process_exit_code_observed_after_job_cleanup"] = false;
                    result["process_exit_code_observation_error"] = Marshal.GetLastWin32Error();
                }
            }
            if (launch is not null)
            {
                try
                {
                    (CapturedStream stdout, CapturedStream stderr, bool captureComplete) =
                        await launch.Output.CompleteAsync(TimeSpan.FromSeconds(3)).ConfigureAwait(false);
                    result["stdout"] = stdout.Summary();
                    result["stderr"] = stderr.Summary(includeTail: true);
                    result["stdout_data"] = stdout;
                    result["stderr_data"] = stderr;
                    result["output_capture_incomplete"] = !captureComplete;
                }
                catch (Exception outputError)
                {
                    result["failure_output_capture"] = Failure("process_output_capture", outputError);
                }
                await launch.Output.DisposeAsync().ConfigureAwait(false);
            }
            job?.Dispose();
            native.Dispose();
            rootExitMonitor?.Dispose();
            if (tracker is not null)
            {
                result["observed_processes"] = tracker.Processes.Select(process => process.ToDictionary()).ToList();
            }
        }
        return result;
    }

    private static async Task<bool> WaitForRootAsync(
        LeaseProcessJob job,
        ProcessTracker tracker,
        ITargetProcessIdentity identity,
        TimeSpan timeout,
        Func<bool>? stopCondition = null)
    {
        long deadline = Environment.TickCount64 + (long)Math.Ceiling(timeout.TotalMilliseconds);
        while (Environment.TickCount64 < deadline)
        {
            if (stopCondition?.Invoke() is true)
            {
                throw new InvalidDataException("Process output exceeded its configured byte limit.");
            }
            tracker.CaptureTree(job.RootProcessId, job, identity.UserSid, identity.SessionId);
            uint wait = NativeMethods.WaitForSingleObject(job.RootProcessHandle, 0);
            if (wait == NativeMethods.WaitObject0)
            {
                return true;
            }
            if (wait != NativeMethods.WaitTimeout)
            {
                throw LastError("WaitForSingleObject.RootProcess");
            }
            await Task.Delay(100).ConfigureAwait(false);
        }
        if (stopCondition?.Invoke() is true)
        {
            throw new InvalidDataException("Process output exceeded its configured byte limit.");
        }
        tracker.CaptureTree(job.RootProcessId, job, identity.UserSid, identity.SessionId);
        return NativeMethods.WaitForSingleObject(job.RootProcessHandle, 0) == NativeMethods.WaitObject0;
    }

    private static async Task<(Dictionary<string, object?> Root, Dictionary<string, object?> Child)> WaitForFixtureMarkersAsync(
        string rootPath,
        string childPath,
        LeaseProcessJob job,
        ProcessTracker tracker,
        ITargetProcessIdentity identity,
        TimeSpan timeout)
    {
        long deadline = Environment.TickCount64 + (long)Math.Ceiling(timeout.TotalMilliseconds);
        while (Environment.TickCount64 < deadline)
        {
            tracker.CaptureTree(job.RootProcessId, job, identity.UserSid, identity.SessionId);
            if (File.Exists(rootPath) && File.Exists(childPath))
            {
                Dictionary<string, object?> root = await ReadJsonObjectAsync(rootPath).ConfigureAwait(false);
                Dictionary<string, object?> child = await ReadJsonObjectAsync(childPath).ConfigureAwait(false);
                return (root, child);
            }
            if (NativeMethods.WaitForSingleObject(job.RootProcessHandle, 0) == NativeMethods.WaitObject0)
            {
                var failure = new NativeApiException("FixtureRootExitedBeforeMarkers", NativeMethods.ErrorAccessDenied);
                if (NativeMethods.GetExitCodeProcess(job.RootProcessHandle, out uint exitCode))
                {
                    failure.Data["fixture_root_exit_code_raw"] = $"0x{exitCode:X8}";
                }
                else
                {
                    failure.Data["fixture_root_exit_code_query_error"] = Marshal.GetLastWin32Error();
                }
                throw failure;
            }
            await Task.Delay(50).ConfigureAwait(false);
        }
        throw new TimeoutException("The fixture root and child did not write their identity markers before the bound.");
    }

    private static async Task<Dictionary<string, object?>> ReadJsonObjectAsync(string path)
    {
        await using FileStream stream = File.OpenRead(path);
        return await JsonSerializer.DeserializeAsync<Dictionary<string, object?>>(stream).ConfigureAwait(false)
            ?? throw new InvalidDataException("A fixture identity marker was empty.");
    }

    private static ProcessObservation FindObservation(ProcessTracker tracker, uint pid) => tracker.Processes.FirstOrDefault(process => process.ProcessId == pid)
        ?? throw new NativeApiException("ProcessObservationMissing", NativeMethods.ErrorNotFound);

    private static Dictionary<string, object?> ToLoaderProcessEvidence(ProcessObservation process, string expectedSid)
    {
        Dictionary<string, object?> evidence = process.ToDictionary();
        evidence.Remove("sid");
        evidence["sid_matches_target"] = string.Equals(process.UserSid, expectedSid, StringComparison.Ordinal);
        return evidence;
    }

    private static SafeProcessHandle OpenProcessForExitVerification(uint pid)
    {
        SafeProcessHandle process = NativeMethods.OpenProcess(
            NativeMethods.ProcessQueryLimitedInformation | NativeMethods.ProcessSynchronize, false, pid);
        if (process.IsInvalid)
        {
            int error = Marshal.GetLastWin32Error();
            process.Dispose();
            throw new NativeApiException("OpenProcess.ExitVerification", error);
        }
        return process;
    }

    private static SafeNativeHandle DuplicateProcessHandle(SafeProcessHandle process, string api)
    {
        if (!NativeMethods.DuplicateHandle(NativeMethods.GetCurrentProcess(), process.DangerousGetHandle(),
                NativeMethods.GetCurrentProcess(), out SafeNativeHandle duplicate, 0, false, NativeMethods.DuplicateSameAccess))
        {
            throw LastError(api);
        }
        return duplicate;
    }

    private static void SetExitCode(Dictionary<string, object?> report, uint rawExitCode)
    {
        SetProcessExitCodeFields(report, unchecked((int)rawExitCode));
    }

    private static void SetProcessExitCodeFields(Dictionary<string, object?> report, int? exitCode)
    {
        string formattedHex = FormatProcessExitCodeHex(exitCode);
        report["process_exit_code"] = exitCode is int knownExitCode ? knownExitCode : "unknown";
        report["process_exit_code_hex"] = formattedHex;
        report["process_exit_code_raw"] = formattedHex;
    }

    internal static string FormatProcessExitCodeHex(int? exitCode) => exitCode is int knownExitCode
        ? "0x" + unchecked((uint)knownExitCode).ToString("X8", System.Globalization.CultureInfo.InvariantCulture)
        : "unknown";

    private static bool TryParseRawProcessExitCode(string rawExitCode, out int signedExitCode)
    {
        signedExitCode = 0;
        if (!IsSafeHexExitCode(rawExitCode)
            || !uint.TryParse(rawExitCode.AsSpan(2), System.Globalization.NumberStyles.AllowHexSpecifier,
                System.Globalization.CultureInfo.InvariantCulture, out uint unsignedExitCode))
        {
            return false;
        }

        signedExitCode = unchecked((int)unsignedExitCode);
        return true;
    }

    private static void PreserveProcessOutcome(
        Dictionary<string, object?> failure,
        Dictionary<string, object?> report,
        string stage)
    {
        string? resultKey = stage switch
        {
            "probe_launch" => "probe",
            "browser_launch" => "browser",
            "fixture_timeout" => "fixture_timeout",
            "fixture_injected_exception" => "fixture_injected_exception",
            _ => null,
        };
        if (resultKey is null
            || report.GetValueOrDefault(resultKey) is not Dictionary<string, object?> processResult)
        {
            return;
        }

        int? processExitCode = processResult.GetValueOrDefault("process_exit_code") is int knownExitCode
            ? knownExitCode
            : null;
        AddProcessExitOutcomeToFailure(failure, processExitCode, processResult.GetValueOrDefault("timed_out"));

        if (processResult.GetValueOrDefault("failure") is Dictionary<string, object?> processFailure
            && processFailure.GetValueOrDefault("stage") is string processFailureStage
            && IsSafeDiagnosticIdentifier(processFailureStage))
        {
            failure["process_failure_stage"] = processFailureStage;
        }
    }

    private static void AddProcessExitOutcomeToFailure(
        Dictionary<string, object?> failure,
        int? processExitCode,
        object? timedOut)
    {
        SetProcessExitCodeFields(failure, processExitCode);
        failure["timed_out"] = timedOut is bool timeoutValue ? timeoutValue : "unknown";
    }

    private static Dictionary<string, object?> CreateInitialReport(HelperOptions options) => new()
    {
        ["schema"] = "b2-locked-chromium-observation/v2",
        ["mode"] = "b2",
        ["status"] = "pending",
        ["observed_at_utc"] = DateTimeOffset.UtcNow,
        ["helper_exit_code"] = null,
        ["identity"] = null,
        ["desktop_access_check"] = null,
        ["identity_cleanup"] = null,
        ["work_area"] = null,
        ["native_diagnostic"] = new Dictionary<string, object?>
        {
            ["status"] = "not_run",
            ["root_exit_code_raw"] = null,
            ["cleanup_status"] = "not_started",
            ["active_processes_after"] = null,
            ["cleanup_complete"] = false,
            ["observed_processes"] = new List<Dictionary<string, object?>>(),
        },
        ["fixture_timeout"] = null,
        ["fixture_injected_exception"] = null,
        ["probe"] = new Dictionary<string, object?>
        {
            ["status"] = "not_run",
            ["process_exit_code"] = "unknown",
            ["process_exit_code_hex"] = "unknown",
            ["process_exit_code_raw"] = "unknown",
            ["timed_out"] = "unknown",
            ["report_path"] = null,
            ["observed_processes"] = new List<Dictionary<string, object?>>(),
        },
        ["browser"] = new Dictionary<string, object?>
        {
            ["process_id"] = null,
            ["process_exit_code"] = "unknown",
            ["process_exit_code_hex"] = "unknown",
            ["process_exit_code_raw"] = "unknown",
            ["timed_out"] = "unknown",
            ["status"] = "not_run",
        },
        ["page"] = new Dictionary<string, object?>
        {
            ["status"] = "not_run",
            ["dom_marker_found"] = false,
            ["dom_body_recorded"] = false,
        },
        ["process_tree"] = new Dictionary<string, object?>
        {
            ["cleanup_status"] = "not_started",
            ["active_processes_after"] = null,
            ["observed_processes"] = new List<Dictionary<string, object?>>(),
        },
        ["failure"] = null,
    };

    private static void ValidateInputs(HelperOptions options)
    {
        if (!OperatingSystem.IsWindows()) throw new PlatformNotSupportedException("This helper requires Windows.");
        if (options.ReportPath is null || options.ProbeScript is null || options.ProfileDirectory is null
            || options.BrowserPath is null || options.TestPage is null || options.WorkDirectory is null
            || options.EvidenceDirectory is null || options.DesktopAclEvidencePath is null
            || options.NativeDiagnosticPath is null)
        {
            throw new ArgumentException("Required B2 inputs are missing.");
        }
        if (File.Exists(options.ReportPath) || Directory.Exists(options.ReportPath))
        {
            throw new NativeApiException("ReportPath.MustBeNew", NativeMethods.ErrorAlreadyExists);
        }
        if (!string.Equals(Path.GetFullPath(Path.GetDirectoryName(options.ReportPath)!).TrimEnd('\\'),
                Path.GetFullPath(options.EvidenceDirectory).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase))
        {
            throw new NativeApiException("ReportPath.MustBeInEvidenceDirectory", NativeMethods.ErrorAccessDenied);
        }
        if (!string.Equals(Path.GetFullPath(Path.GetDirectoryName(options.DesktopAclEvidencePath)!).TrimEnd('\\'),
                Path.GetFullPath(options.EvidenceDirectory).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase))
        {
            throw new NativeApiException("DesktopAclEvidence.MustBeInEvidenceDirectory", NativeMethods.ErrorAccessDenied);
        }
        if (!File.Exists(options.DesktopAclEvidencePath))
        {
            throw new NativeApiException("DesktopAclEvidence.Missing", NativeMethods.ErrorNotFound);
        }
        if (!File.Exists(options.ProbeScript)) throw new NativeApiException("ProbeScript.Missing", NativeMethods.ErrorNotFound);
        if (!File.Exists(options.NativeDiagnosticPath)) throw new NativeApiException("NativeDiagnostic.Missing", NativeMethods.ErrorNotFound);
        if (!File.Exists(options.BrowserPath)) throw new NativeApiException("Browser.Missing", NativeMethods.ErrorNotFound);
        if (!File.Exists(options.TestPage)) throw new NativeApiException("TestPage.Missing", NativeMethods.ErrorNotFound);
        if (!Directory.Exists(options.EvidenceDirectory)) throw new NativeApiException("EvidenceDirectory.Missing", NativeMethods.ErrorNotFound);
        string page = File.ReadAllText(options.TestPage);
        if (!page.Contains(ControlledDomMarker, StringComparison.Ordinal))
        {
            throw new NativeApiException("TestPage.ControlledMarkerMissing", NativeMethods.ErrorAccessDenied);
        }
        string leaf = Path.GetFileName(Path.GetFullPath(options.WorkDirectory).TrimEnd('\\'));
        if (!leaf.StartsWith("b2-", StringComparison.OrdinalIgnoreCase)
            || !Guid.TryParseExact(leaf[3..], "D", out _))
        {
            throw new NativeApiException("WorkDirectory.MustBeUniqueRunLeaf", NativeMethods.ErrorAccessDenied);
        }
        string stagedProfile = Path.GetFullPath(options.ProfileDirectory).TrimEnd('\\');
        string stagedWork = Path.GetFullPath(options.WorkDirectory).TrimEnd('\\');
        if (!string.Equals(Path.GetDirectoryName(stagedProfile)?.TrimEnd('\\'), stagedWork, StringComparison.OrdinalIgnoreCase))
        {
            throw new NativeApiException("ProfileDirectory.MustBeWorkLeafChild", NativeMethods.ErrorAccessDenied);
        }
        string? helperDirectory = Path.GetDirectoryName(Environment.ProcessPath);
        string? runnerDirectory = helperDirectory is null ? null : Directory.GetParent(helperDirectory)?.FullName;
        string expectedNativeDiagnostic = runnerDirectory is null
            ? string.Empty
            : Path.Combine(runnerDirectory, "native-desktop-probe.exe");
        if (string.IsNullOrEmpty(expectedNativeDiagnostic)
            || !string.Equals(Path.GetFullPath(options.NativeDiagnosticPath), Path.GetFullPath(expectedNativeDiagnostic), StringComparison.OrdinalIgnoreCase))
        {
            throw new NativeApiException("NativeDiagnostic.MustBeMappedRunnerSibling", NativeMethods.ErrorAccessDenied);
        }
    }

    private static void CopyEvidenceFile(string source, string destination, out long? bytes, out string? sha256)
    {
        if (File.Exists(destination) || Directory.Exists(destination))
        {
            throw new NativeApiException("EvidenceFile.MustBeNew", NativeMethods.ErrorAlreadyExists);
        }
        File.Copy(source, destination, overwrite: false);
        string computed = HashFile(destination, out long length);
        bytes = length;
        sha256 = computed;
    }

    private static string HashFile(string path, out long bytes)
    {
        using FileStream stream = File.OpenRead(path);
        bytes = stream.Length;
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }

    private static string BuildCommandLine(string applicationPath, IReadOnlyList<string> arguments)
    {
        var commandArguments = new List<string> { applicationPath };
        commandArguments.AddRange(arguments);
        return string.Join(" ", commandArguments.Select(TargetProcessLauncher.QuoteArgument));
    }

    private static string? TryGetJsonString(Dictionary<string, object?> json, string key)
    {
        if (!json.TryGetValue(key, out object? value)) return null;
        return value switch
        {
            JsonElement element when element.ValueKind == JsonValueKind.String => element.GetString(),
            string text => text,
            _ => null,
        };
    }

    private static string? GetJsonString(Dictionary<string, object?> json, string key)
    {
        if (!json.TryGetValue(key, out object? value)) return null;
        return value switch
        {
            JsonElement element when element.ValueKind == JsonValueKind.String => element.GetString(),
            string text => text,
            _ => null,
        };
    }

    private static bool GetJsonBoolean(Dictionary<string, object?> json, string key)
    {
        if (!json.TryGetValue(key, out object? value))
        {
            throw new InvalidDataException($"Native diagnostic marker is missing {key}.");
        }
        return value switch
        {
            JsonElement element when element.ValueKind == JsonValueKind.True => true,
            JsonElement element when element.ValueKind == JsonValueKind.False => false,
            bool boolean => boolean,
            _ => throw new InvalidDataException($"Native diagnostic marker has invalid {key}."),
        };
    }

    private static uint GetUInt32(Dictionary<string, object?> json, string key)
    {
        if (!json.TryGetValue(key, out object? value)) throw new InvalidDataException($"Fixture marker is missing {key}.");
        if (value is JsonElement element && element.TryGetUInt32(out uint jsonValue)) return jsonValue;
        return value switch
        {
            uint number => number,
            int number when number >= 0 => (uint)number,
            long number when number is >= 0 and <= uint.MaxValue => (uint)number,
            _ => throw new InvalidDataException($"Fixture marker has invalid {key}."),
        };
    }

    private static int GetInt32(Dictionary<string, object?> json, string key)
    {
        if (!json.TryGetValue(key, out object? value)) throw new InvalidDataException($"Fixture marker is missing {key}.");
        if (value is JsonElement element && element.TryGetInt32(out int jsonValue)) return jsonValue;
        return value switch
        {
            int number => number,
            uint number when number <= int.MaxValue => (int)number,
            long number when number is >= int.MinValue and <= int.MaxValue => (int)number,
            _ => throw new InvalidDataException($"Fixture marker has invalid {key}."),
        };
    }

    internal static Dictionary<string, object?> Failure(string stage, Exception exception)
    {
        NativeApiException? native = FindNativeApiException(exception);
        MethodBase? targetSite = exception.TargetSite;
        var failure = new Dictionary<string, object?>
        {
            ["stage"] = stage,
            ["api"] = native?.Api,
            ["win32_error"] = native?.ErrorCode ?? (exception is System.ComponentModel.Win32Exception win32 ? win32.NativeErrorCode : null),
            ["message"] = native?.Api ?? (exception is TimeoutException ? "bounded_wait_timeout" : exception.GetType().Name),
            ["exception_type"] = exception.GetType().Name,
            ["exception_origin"] = targetSite is null
                ? null
                : $"{targetSite.DeclaringType?.Name ?? "unknown"}.{targetSite.Name}",
        };
        if (exception is ArgumentException argument && IsSafeDiagnosticIdentifier(argument.ParamName))
        {
            failure["argument_parameter"] = argument.ParamName;
        }
        return failure;
    }

    internal static void ValidateFailureDiagnosticSerialization()
    {
        const string sensitiveMarker = "fixture-path-must-not-be-serialized";
        Dictionary<string, object?> failure;
        try
        {
            throw new ArgumentException(sensitiveMarker, "processHandle");
        }
        catch (ArgumentException exception)
        {
            failure = Failure("diagnostic_self_test", exception);
        }
        string serialized = JsonSerializer.Serialize(failure);
        if (failure["argument_parameter"] as string != "processHandle"
            || failure["exception_origin"] is not string origin || string.IsNullOrWhiteSpace(origin)
            || serialized.Contains(sensitiveMarker, StringComparison.Ordinal))
        {
            throw new InvalidOperationException("Failure diagnostics did not retain safe location data while redacting exception text.");
        }

        Dictionary<string, object?> directWtsFailure = CreateWtsProcessSingletonFailure(
            "wts_identity_filter", new NativeApiException("CreateProcessAsUser", 5));
        string directWtsFailureJson = JsonSerializer.Serialize(directWtsFailure);
        if (directWtsFailure.GetValueOrDefault("win32_error") is not int directError || directError != 5
            || directWtsFailure.GetValueOrDefault("error_type") as string != nameof(NativeApiException)
            || directWtsFailure.ContainsKey("error_code") || directWtsFailure.ContainsKey("exception_type")
            || !directWtsFailureJson.Contains("\"win32_error\":5", StringComparison.Ordinal)
            || !directWtsFailureJson.Contains("\"error_type\":\"NativeApiException\"", StringComparison.Ordinal))
        {
            throw new InvalidOperationException("WTS failure diagnostics did not emit the canonical failure schema.");
        }

        var legacyObservationFailure = new Dictionary<string, object?>
        {
            ["api"] = "CreateProcessAsUser",
            ["error_code"] = "0x00000057",
            ["exception_type"] = "Win32Exception",
        };
        Dictionary<string, object?> normalizedObservationFailure =
            CreateWtsProcessSingletonObservationFailure(legacyObservationFailure);
        string normalizedObservationFailureJson = JsonSerializer.Serialize(normalizedObservationFailure);
        if (normalizedObservationFailure.GetValueOrDefault("win32_error") is not long legacyError || legacyError != 87
            || normalizedObservationFailure.GetValueOrDefault("error_type") as string != "Win32Exception"
            || normalizedObservationFailure.ContainsKey("error_code")
            || normalizedObservationFailure.ContainsKey("exception_type")
            || !normalizedObservationFailureJson.Contains("\"win32_error\":87", StringComparison.Ordinal)
            || !normalizedObservationFailureJson.Contains("\"error_type\":\"Win32Exception\"", StringComparison.Ordinal))
        {
            throw new InvalidOperationException("Legacy supervision failure aliases were not normalized to the canonical schema.");
        }

        const int ntStatusFailure = unchecked((int)0xC0000142);
        string? nonzeroStage = ClassifyWtsProcessSingletonProcessFailureStage(false, ntStatusFailure);
        Dictionary<string, object?> nonzeroFailure = CreateWtsProcessSingletonProcessOutcomeFailure(
            nonzeroStage!, false, ntStatusFailure, null);
        if (nonzeroStage != "process_singleton_probe_exit_nonzero"
            || nonzeroFailure.GetValueOrDefault("process_exit_code") is not int signedExit || signedExit != ntStatusFailure
            || nonzeroFailure.GetValueOrDefault("process_exit_code_hex") as string != "0xC0000142"
            || nonzeroFailure.GetValueOrDefault("win32_error") is not null)
        {
            throw new InvalidOperationException("A nonzero NTSTATUS process exit was not retained as an exit code.");
        }

        if (ClassifyWtsProcessSingletonProcessFailureStage(false, 0) is not null
            || ClassifyWtsProcessSingletonProcessFailureStage(true, 0) != "process_singleton_probe_timeout"
            || ClassifyWtsProcessSingletonProcessFailureStage(null, null) != "process_singleton_probe_completion_unknown"
            || ClassifyWtsProcessSingletonProcessFailureStage(false, null) != "process_singleton_probe_exit_unknown"
            || ClassifyWtsProcessSingletonReportFailureStage(false, ntStatusFailure, false)
                != "process_singleton_probe_exit_nonzero"
            || ClassifyWtsProcessSingletonReportFailureStage(false, null, false)
                != "process_singleton_probe_exit_unknown"
            || ClassifyWtsProcessSingletonReportFailureStage(false, 0, false)
                != "process_singleton_report_capture")
        {
            throw new InvalidOperationException("Process outcome classification did not keep report-capture failure limited to exit-zero missing reports.");
        }
    }

    internal static void ValidateProcessExitCodeDiagnostics()
    {
        const int ntStatusFailure = unchecked((int)0xC0000142);
        if (FormatProcessExitCodeHex(0) != "0x00000000"
            || FormatProcessExitCodeHex(ntStatusFailure) != "0xC0000142"
            || FormatProcessExitCodeHex(null) != "unknown")
        {
            throw new InvalidOperationException("Process exit-code hexadecimal formatting did not preserve success, NTSTATUS, and unknown values.");
        }

        var unknownOutcome = new Dictionary<string, object?>();
        SetProcessExitCodeFields(unknownOutcome, null);
        if (unknownOutcome.GetValueOrDefault("process_exit_code") as string != "unknown"
            || unknownOutcome.GetValueOrDefault("process_exit_code_hex") as string != "unknown"
            || unknownOutcome.GetValueOrDefault("process_exit_code_raw") as string != "unknown")
        {
            throw new InvalidOperationException("An unknown process exit was serialized as a numeric success or omitted from its hex field.");
        }

        var timeoutOutcome = new Dictionary<string, object?> { ["timed_out"] = true };
        SetProcessExitCodeFields(timeoutOutcome, null);
        var timeoutFailure = new Dictionary<string, object?>();
        AddProcessExitOutcomeToFailure(timeoutFailure, null, timeoutOutcome["timed_out"]);
        if (timeoutOutcome.GetValueOrDefault("timed_out") is not true
            || timeoutFailure.GetValueOrDefault("timed_out") is not true
            || timeoutFailure.GetValueOrDefault("process_exit_code") as string != "unknown"
            || timeoutFailure.GetValueOrDefault("process_exit_code_hex") as string != "unknown")
        {
            throw new InvalidOperationException("A timed-out process with no observed exit code was not retained as timed out/unknown.");
        }

        var probeResult = new Dictionary<string, object?>
        {
            ["process_exit_code"] = ntStatusFailure,
            ["process_exit_code_raw"] = "0xC0000142",
            ["timed_out"] = false,
            ["failure"] = new Dictionary<string, object?> { ["stage"] = "probe_nonzero_exit" },
        };
        var report = new Dictionary<string, object?> { ["probe"] = probeResult };
        Dictionary<string, object?> wrapperFailure = Failure(
            "probe_launch", new NativeApiException("ProbeGateFailed.BrowserSkipped", NativeMethods.ErrorAccessDenied));
        PreserveProcessOutcome(wrapperFailure, report, "probe_launch");
        if (wrapperFailure.GetValueOrDefault("win32_error") is not int win32Error || win32Error != NativeMethods.ErrorAccessDenied
            || wrapperFailure.GetValueOrDefault("process_exit_code") is not int signedExitCode || signedExitCode != ntStatusFailure
            || wrapperFailure.GetValueOrDefault("process_exit_code_hex") as string != "0xC0000142"
            || wrapperFailure.GetValueOrDefault("process_exit_code_raw") as string != "0xC0000142"
            || wrapperFailure.GetValueOrDefault("timed_out") is not false
            || wrapperFailure.GetValueOrDefault("process_failure_stage") as string != "probe_nonzero_exit")
        {
            throw new InvalidOperationException("The B2 wrapper failure did not preserve the child NTSTATUS separately from its Win32 gate error.");
        }
    }

    private static bool IsSafeDiagnosticIdentifier(string? value) =>
        !string.IsNullOrEmpty(value)
        && value.Length <= 64
        && value.All(character => char.IsAsciiLetterOrDigit(character) || character == '_');

    private static bool IsSafeHexExitCode(string value) =>
        value.Length == 10
        && value.StartsWith("0x", StringComparison.Ordinal)
        && value.AsSpan(2).ToString().All(character => char.IsAsciiHexDigit(character));

    private static NativeApiException? FindNativeApiException(Exception exception)
    {
        if (exception is NativeApiException native) return native;
        if (exception is AggregateException aggregate)
        {
            foreach (Exception inner in aggregate.InnerExceptions)
            {
                NativeApiException? found = FindNativeApiException(inner);
                if (found is not null) return found;
            }
        }
        return exception.InnerException is null ? null : FindNativeApiException(exception.InnerException);
    }

    private static NativeApiException LastError(string api) => new(api, Marshal.GetLastWin32Error());

    private sealed class InjectedFixtureException : Exception;
}
