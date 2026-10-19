using System.Text.Json;
using System.Text.Json.Serialization;
using DouyinTranscript.CapturePipe;

namespace DouyinTranscript.LeaseJobHelper;

internal sealed record HelperOptions(
    string Mode,
    string? ReportPath,
    string? ProbeScript,
    string? ProfileDirectory,
    string? BrowserPath,
    string? TestPage,
    string? WorkDirectory,
    string? EvidenceDirectory,
    string? DesktopAclEvidencePath,
    string? NativeDiagnosticPath,
    int TimeoutSeconds,
    string? ExpectedRunId,
    string? CdbPath = null,
    string? LoaderTargetPath = null,
    string? ExpectedCdbSha256 = null,
    string? ExpectedLoaderTargetSha256 = null);

internal static class Program
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    };

    public static async Task<int> Main(string[] args)
    {
        if (args.Length == 2 && args[0] == "--lease-job-fixture-root")
        {
            return await LeaseProcessJobHarness.RunFixtureRootAsync(args[1]).ConfigureAwait(false);
        }
        if (args.Length == 3 && args[0] == "--lease-job-fixture-supervisor")
        {
            return await LeaseProcessJobHarness.RunFixtureSupervisorAsync(args[1], args[2]).ConfigureAwait(false);
        }
        if (args.Length == 1 && args[0] == "--lease-job-fixture-leaf")
        {
            return LeaseProcessJobHarness.RunFixtureLeaf();
        }
        if (args.Length == 2 && args[0] == "--fixture-leaf")
        {
            return await FixtureRuntime.RunLeafAsync(args[1]).ConfigureAwait(false);
        }
        if (args.Length == 3 && args[0] == "--fixture-root")
        {
            return await FixtureRuntime.RunRootAsync(args[1], args[2]).ConfigureAwait(false);
        }

        HelperOptions options;
        try
        {
            options = Parse(args);
        }
        catch (ArgumentException)
        {
            Console.Error.WriteLine("Usage: LeaseProcessJobRunner.exe --mode self-test --report-path <path> | --mode b2-wts-desktop-acl-diagnostic --report-path <path> --evidence-directory <path> --desktop-acl-evidence-path <path> --run-id <guid> --timeout-seconds <1..120> | --mode b2-wts-native-control --report-path <path> --native-diagnostic-path <path> --evidence-directory <path> --run-id <guid> --timeout-seconds <1..120> | --mode b2-wts-process-singleton-diagnostic --report-path <path> --probe-script <path> --evidence-directory <path> --run-id <guid> --timeout-seconds <1..120> | --mode b2-wts-loader-snaps --report-path <path> --cdb-path <path> --loader-target-path <path> --cdb-sha256 <sha256> --loader-target-sha256 <sha256> --evidence-directory <path> --run-id <guid> --timeout-seconds <1..120> | --mode b2 --report-path <path> --probe-script <path> --profile-directory <path> --browser-path <path> --test-page <path> --work-directory <path> --evidence-directory <path> --desktop-acl-evidence-path <path> --native-diagnostic-path <path> --timeout-seconds <1..300>");
            return 2;
        }

        if (options.Mode == "self-test")
        {
            try
            {
                await LeaseProcessJobHarness.RunAsync().ConfigureAwait(false);
                await ProcessOutputCapture.ValidateSynchronousPipeCaptureAsync().ConfigureAwait(false);
                await ProcessOutputCapture.ValidateHardOutputByteLimitCaptureAsync().ConfigureAwait(false);
                TargetProcessLauncher.ValidatePostCreateRollbackSelfTest();
                GuestRunCoordinator.ValidateFailureDiagnosticSerialization();
                GuestRunCoordinator.ValidateProcessExitCodeDiagnostics();
                GuestRunCoordinator.ValidateNativeDiagnosticMarkerContract();
                GuestRunCoordinator.ValidateNativeDesktopMarkerWaitClassification();
                IfeoGlobalFlagLease.ValidateSelfTest();
                DesktopAccessCheck.ValidateSelfTest();
                ProcessTracker.ValidateCurrentTokenElevationQuery();
                (bool usersGroupEnabled, bool administratorsGroupEnabled) =
                    TargetIdentityContext.ValidateCurrentProcessGroupMembershipChecks();
                (uint activeConsoleSessionId, int activeSessionCount) =
                    TargetIdentityContext.ValidateCurrentSessionEnumerationApis();
                WriteSelfTestReport(options.ReportPath, usersGroupEnabled, administratorsGroupEnabled,
                    activeConsoleSessionId, activeSessionCount);
                return 0;
            }
            catch (Exception exception)
            {
                WriteFailureReport(options.ReportPath, "self-test", exception);
                Console.Error.WriteLine($"FAIL self-test: {exception.GetType().Name}");
                return 1;
            }
        }

        if (options.Mode == "b2-wts-native-control")
        {
            return await GuestRunCoordinator.RunWtsNativeControlAsync(options, JsonOptions).ConfigureAwait(false);
        }

        if (options.Mode == "b2-wts-desktop-acl-diagnostic")
        {
            return await GuestRunCoordinator.RunWtsDesktopAclDiagnosticAsync(options, JsonOptions).ConfigureAwait(false);
        }

        if (options.Mode == "b2-wts-process-singleton-diagnostic")
        {
            return await GuestRunCoordinator.RunWtsProcessSingletonDiagnosticAsync(options, JsonOptions).ConfigureAwait(false);
        }

        if (options.Mode == "b2-wts-loader-snaps")
        {
            return await GuestRunCoordinator.RunWtsLoaderSnapsAsync(options, JsonOptions).ConfigureAwait(false);
        }

        return await GuestRunCoordinator.RunAsync(options, JsonOptions).ConfigureAwait(false);
    }

    private static HelperOptions Parse(IReadOnlyList<string> args)
    {
        var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        for (int index = 0; index < args.Count; index += 2)
        {
            if (index + 1 >= args.Count || !args[index].StartsWith("--", StringComparison.Ordinal))
            {
                throw new ArgumentException("Arguments must be named values.");
            }
            if (!values.TryAdd(args[index], args[index + 1]))
            {
                throw new ArgumentException("An argument was repeated.");
            }
        }

        string mode = Required(values, "--mode");
        string reportPath = Path.GetFullPath(Required(values, "--report-path"));
        if (mode == "self-test")
        {
            if (values.Keys.Any(key => key is not "--mode" and not "--report-path"))
            {
                throw new ArgumentException("Unexpected self-test arguments.");
            }
            return new HelperOptions(mode, reportPath, null, null, null, null, null, null, null, null, 20, null);
        }

        if (mode == "b2-wts-native-control")
        {
            if (values.Keys.Any(key => key is not "--mode" and not "--report-path" and not "--native-diagnostic-path"
                and not "--evidence-directory" and not "--run-id" and not "--timeout-seconds"))
            {
                throw new ArgumentException("An unsupported WTS diagnostic argument was supplied.");
            }
            int wtsTimeoutSeconds = int.TryParse(Required(values, "--timeout-seconds"), out int parsedWtsTimeout)
                ? parsedWtsTimeout
                : throw new ArgumentException("The timeout is invalid.");
            if (wtsTimeoutSeconds is < 1 or > 120)
            {
                throw new ArgumentException("The timeout must be between 1 and 120 seconds.");
            }
            return new HelperOptions(
                mode,
                reportPath,
                null,
                null,
                null,
                null,
                null,
                Path.GetFullPath(Required(values, "--evidence-directory")),
                null,
                Path.GetFullPath(Required(values, "--native-diagnostic-path")),
                wtsTimeoutSeconds,
                Required(values, "--run-id"));
        }

        if (mode == "b2-wts-desktop-acl-diagnostic")
        {
            if (values.Keys.Any(key => key is not "--mode" and not "--report-path" and not "--evidence-directory"
                and not "--desktop-acl-evidence-path" and not "--run-id" and not "--timeout-seconds"))
            {
                throw new ArgumentException("An unsupported WTS desktop-ACL diagnostic argument was supplied.");
            }
            int diagnosticTimeoutSeconds = int.TryParse(Required(values, "--timeout-seconds"), out int parsedDiagnosticTimeout)
                ? parsedDiagnosticTimeout
                : throw new ArgumentException("The timeout is invalid.");
            if (diagnosticTimeoutSeconds is < 1 or > 120)
            {
                throw new ArgumentException("The timeout must be between 1 and 120 seconds.");
            }
            return new HelperOptions(
                mode,
                reportPath,
                null,
                null,
                null,
                null,
                null,
                Path.GetFullPath(Required(values, "--evidence-directory")),
                Path.GetFullPath(Required(values, "--desktop-acl-evidence-path")),
                null,
                diagnosticTimeoutSeconds,
                Required(values, "--run-id"));
        }

        if (mode == "b2-wts-process-singleton-diagnostic")
        {
            if (values.Keys.Any(key => key is not "--mode" and not "--report-path" and not "--probe-script"
                and not "--evidence-directory" and not "--run-id" and not "--timeout-seconds"))
            {
                throw new ArgumentException("An unsupported WTS ProcessSingleton diagnostic argument was supplied.");
            }
            int processSingletonTimeoutSeconds = int.TryParse(Required(values, "--timeout-seconds"), out int parsedProcessSingletonTimeout)
                ? parsedProcessSingletonTimeout
                : throw new ArgumentException("The timeout is invalid.");
            if (processSingletonTimeoutSeconds is < 1 or > 120)
            {
                throw new ArgumentException("The timeout must be between 1 and 120 seconds.");
            }
            return new HelperOptions(
                mode,
                reportPath,
                Path.GetFullPath(Required(values, "--probe-script")),
                null,
                null,
                null,
                null,
                Path.GetFullPath(Required(values, "--evidence-directory")),
                null,
                null,
                processSingletonTimeoutSeconds,
                Required(values, "--run-id"));
        }

        if (mode == "b2-wts-loader-snaps")
        {
            if (values.Keys.Any(key => key is not "--mode" and not "--report-path" and not "--cdb-path"
                and not "--loader-target-path" and not "--cdb-sha256" and not "--loader-target-sha256"
                and not "--evidence-directory" and not "--run-id" and not "--timeout-seconds"))
            {
                throw new ArgumentException("An unsupported WTS Loader Snaps argument was supplied.");
            }
            int loaderTimeoutSeconds = int.TryParse(Required(values, "--timeout-seconds"), out int parsedLoaderTimeout)
                ? parsedLoaderTimeout
                : throw new ArgumentException("The timeout is invalid.");
            if (loaderTimeoutSeconds is < 1 or > 120)
            {
                throw new ArgumentException("The timeout must be between 1 and 120 seconds.");
            }
            return new HelperOptions(
                mode,
                reportPath,
                null,
                null,
                null,
                null,
                null,
                Path.GetFullPath(Required(values, "--evidence-directory")),
                null,
                null,
                loaderTimeoutSeconds,
                Required(values, "--run-id"),
                Path.GetFullPath(Required(values, "--cdb-path")),
                Path.GetFullPath(Required(values, "--loader-target-path")),
                Required(values, "--cdb-sha256"),
                Required(values, "--loader-target-sha256"));
        }

        if (mode != "b2")
        {
            throw new ArgumentException("Unknown helper mode.");
        }

        int timeoutSeconds = int.TryParse(Required(values, "--timeout-seconds"), out int parsedTimeout)
            ? parsedTimeout
            : throw new ArgumentException("The timeout is invalid.");
        if (timeoutSeconds is < 1 or > 300)
        {
            throw new ArgumentException("The timeout must be between 1 and 300 seconds.");
        }
        if (values.Keys.Any(key => key is not "--mode" and not "--report-path" and not "--probe-script"
            and not "--profile-directory" and not "--browser-path" and not "--test-page"
            and not "--work-directory" and not "--evidence-directory" and not "--desktop-acl-evidence-path"
            and not "--native-diagnostic-path"
            and not "--timeout-seconds"))
        {
            throw new ArgumentException("An unsupported argument was supplied.");
        }

        return new HelperOptions(
            mode,
            reportPath,
            Path.GetFullPath(Required(values, "--probe-script")),
            Path.GetFullPath(Required(values, "--profile-directory")),
            Path.GetFullPath(Required(values, "--browser-path")),
            Path.GetFullPath(Required(values, "--test-page")),
            Path.GetFullPath(Required(values, "--work-directory")),
            Path.GetFullPath(Required(values, "--evidence-directory")),
            Path.GetFullPath(Required(values, "--desktop-acl-evidence-path")),
            Path.GetFullPath(Required(values, "--native-diagnostic-path")),
            timeoutSeconds,
            null);
    }

    private static string Required(IReadOnlyDictionary<string, string> values, string key) =>
        values.TryGetValue(key, out string? value) && !string.IsNullOrWhiteSpace(value)
            ? value
            : throw new ArgumentException("A required argument is missing.");

    private static void WriteSelfTestReport(
        string? reportPath,
        bool usersGroupEnabled,
        bool administratorsGroupEnabled,
        uint activeConsoleSessionId,
        int activeSessionCount)
    {
        if (reportPath is null)
        {
            return;
        }
        var report = new Dictionary<string, object?>
        {
            ["schema"] = "lease-process-job-helper/v1",
            ["mode"] = "self-test",
            ["status"] = "pass",
            ["captured_at_utc"] = DateTimeOffset.UtcNow,
            ["scope"] = "Local LeaseProcessJob harness including real parent/child timeout, exception, and abrupt owner-termination cleanup; process exit-code formatting and wrapper NTSTATUS preservation; token membership/session/elevation queries; desktop evidence binding and AccessCheck self-tests; and post-CreateProcess suspended-root rollback. No temporary account or browser launch.",
            ["lease_process_job_tree_cleanup"] = "pass",
            ["job_owner_termination_kill_on_close"] = "pass",
            ["current_token_membership_checks"] = "pass",
            ["failure_diagnostic_sanitization"] = "pass",
            ["process_exit_code_diagnostics"] = "pass",
            ["synchronous_pipe_capture"] = "pass",
            ["post_create_suspended_root_rollback"] = "pass",
            ["desktop_access_check"] = "pass",
            ["desktop_evidence_binding"] = "pass",
            ["process_token_elevation_query"] = "pass",
            ["current_users_group_enabled"] = usersGroupEnabled,
            ["current_administrators_group_enabled"] = administratorsGroupEnabled,
            ["current_console_session_id"] = activeConsoleSessionId,
            ["current_active_session_count"] = activeSessionCount,
        };
        WriteJson(reportPath, report, JsonOptions);
    }

    private static void WriteFailureReport(string? reportPath, string stage, Exception exception)
    {
        if (reportPath is null)
        {
            return;
        }
        int? win32Error = exception is System.ComponentModel.Win32Exception win32
            ? win32.NativeErrorCode
            : exception.InnerException is System.ComponentModel.Win32Exception inner
                ? inner.NativeErrorCode
                : null;
        var report = new Dictionary<string, object?>
        {
            ["schema"] = "lease-process-job-helper/v1",
            ["status"] = "fail",
            ["captured_at_utc"] = DateTimeOffset.UtcNow,
            ["failure"] = new Dictionary<string, object?>
            {
                ["stage"] = stage,
                ["win32_error"] = win32Error,
                ["message"] = exception is System.ComponentModel.Win32Exception
                    ? "A Windows API call failed."
                    : exception.GetType().Name,
            },
        };
        WriteJson(reportPath, report, JsonOptions);
    }

    internal static void WriteJson(string path, object report, JsonSerializerOptions options)
    {
        string directory = Path.GetDirectoryName(path)
            ?? throw new ArgumentException("The report path must have a parent directory.", nameof(path));
        Directory.CreateDirectory(directory);
        string temporaryPath = Path.Combine(directory, $".{Path.GetFileName(path)}.{Guid.NewGuid():N}.tmp");
        try
        {
            File.WriteAllText(temporaryPath, JsonSerializer.Serialize(report, options));
            File.Move(temporaryPath, path, overwrite: true);
        }
        finally
        {
            try
            {
                File.Delete(temporaryPath);
            }
            catch (IOException)
            {
            }
            catch (UnauthorizedAccessException)
            {
            }
        }
    }
}
