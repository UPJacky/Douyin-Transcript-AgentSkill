using System.Text;

namespace DouyinTranscript.CapturePipe;

internal static class ServiceLifecycleHarness
{
    public static async Task RunAsync()
    {
        VerifyServiceConfigurationParsing();
        VerifyInteractiveClientPolicy();
        await VerifyStopAndShutdownLifecycleAsync(CaptureServiceRuntime.ServiceControlStop).ConfigureAwait(false);
        await VerifyStopAndShutdownLifecycleAsync(CaptureServiceRuntime.ServiceControlShutdown).ConfigureAwait(false);
        await VerifyBaselineGateRunsBeforePipeStartupAsync().ConfigureAwait(false);
        await VerifyBaselineFailurePreventsPipeStartupAsync().ConfigureAwait(false);
        await VerifyStopDuringReadinessGateAsync().ConfigureAwait(false);
        await VerifyStopDoesNotReportStoppedUntilReadinessDrainedAsync().ConfigureAwait(false);
        await VerifyStopDuringStartupAsync().ConfigureAwait(false);
        await VerifyUnexpectedExitIsFailureAsync().ConfigureAwait(false);
        await VerifyStartupFailureIsReportedAsync().ConfigureAwait(false);
        Console.WriteLine("PASS SCM lifecycle state, readiness-gated startup, cancellation, fail-closed worker wiring, and service configuration harness");
    }

    private static void VerifyServiceConfigurationParsing()
    {
        const string valid = "{\"schema_version\":1,\"client_user_sids\":[\"S-1-5-21-1-2-3-1001\"]}";
        CaptureServiceConfiguration parsed = CaptureServiceConfiguration.Parse(Encoding.UTF8.GetBytes(valid));
        Assert(parsed.ClientUserSids.SequenceEqual(["S-1-5-21-1-2-3-1001"]), "service caller SID was not canonicalized");

        ExpectInvalidConfiguration("{\"schema_version\":2,\"client_user_sids\":[\"S-1-5-21-1-2-3-1001\"]}",
            "unsupported config schema");
        ExpectInvalidConfiguration("{\"schema_version\":1,\"client_user_sids\":[]}", "empty caller allowlist");
        ExpectInvalidConfiguration("{\"schema_version\":1,\"client_user_sids\":[\"bad-sid\"]}", "invalid caller SID");
        ExpectInvalidConfiguration("{\"schema_version\":1,\"client_user_sids\":[\"S-1-5-21-1-2-3-1001\",\"S-1-5-21-1-2-3-1001\"]}",
            "duplicate caller SID");
        ExpectInvalidConfiguration("{\"schema_version\":1,\"client_user_sids\":[\"S-1-5-21-1-2-3-1001\"],\"pipe_name\":\"attacker\"}",
            "unknown config field");
        ExpectInvalidConfiguration("{\"schema_version\":1,\"schema_version\":1,\"client_user_sids\":[\"S-1-5-21-1-2-3-1001\"]}",
            "duplicate config field");

        const string serviceSid = "S-1-5-80-100-101-102-103-104";
        CaptureServiceConfiguration.ValidateProtectedAclSddl(
            $"O:SYG:BAD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;GR;;;{serviceSid})");
        ExpectInvalidAcl("O:SYG:BAD:(A;;FA;;;SY)(A;;FA;;;BA)", "inheritable DACL");
        ExpectInvalidAcl("O:SYG:BAD:P(A;;GW;;;BU)(A;;FA;;;SY)(A;;FA;;;BA)", "generic-write ACE");
        ExpectInvalidAcl("O:SYG:BAD:P(A;;FA;;;BU)(A;;FA;;;SY)(A;;FA;;;BA)", "generic-all ACE");
        ExpectInvalidAcl("O:S-1-5-21-1-2-3-1001G:SYD:P(A;;FA;;;SY)(A;;FA;;;BA)", "untrusted owner");

        bool overLimitRejected = false;
        try
        {
            CaptureServiceConfiguration.Parse(new byte[CaptureServiceConfiguration.MaxConfigurationBytes + 1]);
        }
        catch (InvalidDataException)
        {
            overLimitRejected = true;
        }
        Assert(overLimitRejected, "oversized service configuration was accepted");
    }

    private static void VerifyInteractiveClientPolicy()
    {
        const string userSid = "S-1-5-21-1-2-3-1001";
        ClientPeerPolicy policy = ClientPeerPolicy.CreateForInteractiveSessions([userSid]);
        policy.Validate(CreatePeer(userSid, 3));
        ExpectPipeAuthentication(() => policy.Validate(CreatePeer(userSid, 0)), "session-0 caller was accepted");
        ExpectPipeAuthentication(() => policy.Validate(CreatePeer("S-1-5-21-1-2-3-1002", 3)),
            "unconfigured caller SID was accepted");

        const string serviceSid = "S-1-5-80-100-101-102-103-104";
        var servicePolicy = new ServicePeerPolicy(serviceSid);
        servicePolicy.Validate(CreatePeer("S-1-5-18", 0, serviceSid));
        ExpectPipeAuthentication(() => servicePolicy.Validate(CreatePeer("S-1-5-18", 1, serviceSid)),
            "service peer from an interactive session was accepted");
        ExpectPipeAuthentication(() => servicePolicy.Validate(CreatePeer("S-1-5-18", 0)),
            "service peer without its enabled service SID was accepted");
    }

    private static async Task VerifyStopAndShutdownLifecycleAsync(uint control)
    {
        var status = new RecordingStatusSink();
        var server = new BlockingFakeServer();
        var runtime = new CaptureServiceRuntime(status, new ReadyReadinessGate());
        Task<int> running = runtime.RunAsync(() => server);
        status.WaitForState(CaptureServiceState.Running);
        uint controlResult = runtime.HandleControl(control);
        Assert(controlResult == CaptureServiceRuntime.ErrorSuccess, "SCM stop/shutdown was rejected");
        int exitCode = await running.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);

        CaptureServiceState[] states = status.States;
        Assert(exitCode == 0, "requested service stop returned a failure exit code");
        Assert(states.SequenceEqual([
            CaptureServiceState.StartPending,
            CaptureServiceState.Running,
            CaptureServiceState.StopPending,
            CaptureServiceState.Stopped,
        ]), "SCM lifecycle states were not reported in order");
        Assert(server.CancellationObserved, "service stop did not cancel the named-pipe host");
        Assert(runtime.HandleControl(0x00000002) == CaptureServiceRuntime.ErrorCallNotImplemented,
            "unsupported pause control was accepted");
    }

    private static async Task VerifyUnexpectedExitIsFailureAsync()
    {
        var status = new RecordingStatusSink();
        var server = new CompletedFakeServer();
        var runtime = new CaptureServiceRuntime(status, new ReadyReadinessGate());
        int exitCode = await runtime.RunAsync(() => server).WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
        CaptureServiceStatus stopped = status.LastStatus;
        Assert(exitCode != 0, "unexpected pipe-host exit was reported as success");
        Assert(stopped.State == CaptureServiceState.Stopped && stopped.Win32ExitCode == 1066,
            "unexpected pipe-host exit did not report a stable service-specific failure");
    }

    private static async Task VerifyStopDuringStartupAsync()
    {
        var status = new RecordingStatusSink();
        var server = new PendingStartupFakeServer();
        var runtime = new CaptureServiceRuntime(status, new ReadyReadinessGate());
        Task<int> starting = runtime.RunAsync(() => server);
        status.WaitForState(CaptureServiceState.StartPending);
        uint controlResult = runtime.HandleControl(CaptureServiceRuntime.ServiceControlStop);
        int exitCode = await starting.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);

        Assert(controlResult == CaptureServiceRuntime.ErrorSuccess, "STOP during startup was rejected");
        Assert(exitCode == 0, "STOP during startup was reported as a service failure");
        Assert(status.States.SequenceEqual([
            CaptureServiceState.StartPending,
            CaptureServiceState.StopPending,
            CaptureServiceState.Stopped,
        ]), "STOP during startup reported an incoherent SCM state sequence");
        Assert(server.CancellationObserved, "STOP during startup did not cancel the named-pipe host");
    }

    private static async Task VerifyStartupFailureIsReportedAsync()
    {
        var status = new RecordingStatusSink();
        var server = new StartupFailureFakeServer();
        var runtime = new CaptureServiceRuntime(status, new ReadyReadinessGate());
        int exitCode = await runtime.RunAsync(() => server).WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
        CaptureServiceStatus stopped = status.LastStatus;
        Assert(exitCode != 0, "pipe-host startup failure was reported as success");
        Assert(stopped.State == CaptureServiceState.Stopped && stopped.ServiceSpecificExitCode == 1,
            "pipe-host startup failure did not report the stable service failure code");
    }

    private static async Task VerifyBaselineGateRunsBeforePipeStartupAsync()
    {
        var status = new RecordingStatusSink();
        var steps = new List<string>();
        var gate = new RecordingReadinessGate(() => steps.Add("baseline"));
        var server = new BlockingFakeServer();
        var runtime = new CaptureServiceRuntime(status, gate);
        Task<int> running = runtime.RunAsync(() =>
        {
            steps.Add("pipe");
            return server;
        });
        status.WaitForState(CaptureServiceState.Running);
        Assert(steps.SequenceEqual(["baseline", "pipe"]),
            "named-pipe startup ran before persistent baseline readiness was confirmed");

        Assert(runtime.HandleControl(CaptureServiceRuntime.ServiceControlStop) == CaptureServiceRuntime.ErrorSuccess,
            "service stop failed after readiness-gated startup");
        Assert(await running.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false) == 0,
            "readiness-gated service did not stop cleanly");
    }

    private static async Task VerifyBaselineFailurePreventsPipeStartupAsync()
    {
        var status = new RecordingStatusSink();
        var gate = new FailingReadinessGate();
        var runtime = new CaptureServiceRuntime(status, gate);
        int pipeFactoryCalls = 0;
        int exitCode = await runtime.RunAsync(() =>
        {
            pipeFactoryCalls++;
            return new BlockingFakeServer();
        }).WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
        CaptureServiceStatus stopped = status.LastStatus;

        Assert(exitCode != 0, "baseline readiness failure was reported as success");
        Assert(pipeFactoryCalls == 0, "named-pipe server was created after baseline readiness failed");
        Assert(gate.Calls == 1, "baseline readiness gate was not called exactly once");
        Assert(status.States.SequenceEqual([CaptureServiceState.StartPending, CaptureServiceState.Stopped]),
            "baseline failure reported an incoherent SCM state sequence");
        Assert(stopped.Win32ExitCode == 1066 && stopped.ServiceSpecificExitCode == 1,
            "baseline failure did not report the stable service-specific failure code");
    }

    private static async Task VerifyStopDuringReadinessGateAsync()
    {
        var status = new RecordingStatusSink();
        var runtime = new CaptureServiceRuntime(status, new PendingReadinessGate());
        int pipeFactoryCalls = 0;
        Task<int> starting = runtime.RunAsync(() =>
        {
            pipeFactoryCalls++;
            return new BlockingFakeServer();
        });
        status.WaitForState(CaptureServiceState.StartPending);
        uint controlResult = runtime.HandleControl(CaptureServiceRuntime.ServiceControlStop);
        int exitCode = await starting.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);

        Assert(controlResult == CaptureServiceRuntime.ErrorSuccess, "STOP during baseline readiness was rejected");
        Assert(exitCode == 0 && pipeFactoryCalls == 0,
            "STOP during baseline readiness did not stop before pipe creation");
        Assert(status.States.SequenceEqual([
            CaptureServiceState.StartPending,
            CaptureServiceState.StopPending,
            CaptureServiceState.Stopped,
        ]), "STOP during baseline readiness reported an incoherent SCM state sequence");
    }

    private static async Task VerifyStopDoesNotReportStoppedUntilReadinessDrainedAsync()
    {
        var status = new RecordingStatusSink();
        var gate = new DeferredReadinessGate();
        var runtime = new CaptureServiceRuntime(status, gate);
        int pipeFactoryCalls = 0;
        Task<int> starting = runtime.RunAsync(() =>
        {
            pipeFactoryCalls++;
            return new BlockingFakeServer();
        });

        status.WaitForState(CaptureServiceState.StartPending);
        Assert(runtime.HandleControl(CaptureServiceRuntime.ServiceControlStop) == CaptureServiceRuntime.ErrorSuccess,
            "STOP during deferred readiness drain was rejected");
        await gate.CancellationObserved.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);

        Assert(!starting.IsCompleted, "service reported STOPPED before readiness work drained");
        Assert(status.LastStatus.State == CaptureServiceState.StopPending,
            "service left STOP_PENDING before readiness work drained");
        Assert(pipeFactoryCalls == 0, "pipe factory ran before readiness work drained");

        gate.CompleteAfterDrain();
        int exitCode = await starting.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
        Assert(exitCode == 0, "STOP after readiness drain was reported as a failure");
        Assert(pipeFactoryCalls == 0, "pipe factory ran after STOP and readiness drain");
        Assert(status.States.SequenceEqual([
            CaptureServiceState.StartPending,
            CaptureServiceState.StopPending,
            CaptureServiceState.Stopped,
        ]), "service reported STOPPED before readiness drain completed");
    }

    private static PeerIdentity CreatePeer(string userSid, uint sessionId, params string[] enabledGroups)
    {
        HashSet<string> groups = enabledGroups.ToHashSet(StringComparer.OrdinalIgnoreCase);
        return new PeerIdentity(
            ProcessId: 10,
            SessionId: sessionId,
            UserSid: userSid,
            GroupSids: groups,
            EnabledGroupSids: groups,
            AuthenticationId: "auth",
            ImagePath: string.Empty);
    }

    private static void ExpectInvalidConfiguration(string json, string label)
    {
        bool rejected = false;
        try
        {
            CaptureServiceConfiguration.Parse(Encoding.UTF8.GetBytes(json));
        }
        catch (Exception exception) when (exception is InvalidDataException or ArgumentException or System.Text.Json.JsonException)
        {
            rejected = true;
        }
        Assert(rejected, $"{label} was accepted");
    }

    private static void ExpectPipeAuthentication(Action action, string message)
    {
        bool rejected = false;
        try
        {
            action();
        }
        catch (PipeAuthenticationException)
        {
            rejected = true;
        }
        Assert(rejected, message);
    }

    private static void ExpectInvalidAcl(string sddl, string label)
    {
        bool rejected = false;
        try
        {
            CaptureServiceConfiguration.ValidateProtectedAclSddl(sddl);
        }
        catch (Exception exception) when (exception is InvalidDataException or ArgumentException)
        {
            rejected = true;
        }
        Assert(rejected, $"{label} was accepted");
    }

    private static void Assert(bool condition, string message)
    {
        if (!condition)
        {
            throw new InvalidOperationException(message);
        }
    }

    private sealed class ReadyReadinessGate : IServiceReadinessGate
    {
        public Task EnsureReadyAsync(CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            return Task.CompletedTask;
        }
    }

    private sealed class RecordingReadinessGate(Action onReady) : IServiceReadinessGate
    {
        public Task EnsureReadyAsync(CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            onReady();
            return Task.CompletedTask;
        }
    }

    private sealed class FailingReadinessGate : IServiceReadinessGate
    {
        public int Calls { get; private set; }

        public Task EnsureReadyAsync(CancellationToken cancellationToken)
        {
            Calls++;
            cancellationToken.ThrowIfCancellationRequested();
            throw new InvalidOperationException("test baseline failure");
        }
    }

    private sealed class PendingReadinessGate : IServiceReadinessGate
    {
        public Task EnsureReadyAsync(CancellationToken cancellationToken) =>
            Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
    }

    private sealed class DeferredReadinessGate : IServiceReadinessGate
    {
        private readonly TaskCompletionSource<bool> cancellationObserved =
            new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly TaskCompletionSource<bool> completion =
            new(TaskCreationOptions.RunContinuationsAsynchronously);
        private CancellationToken cancellationToken;
        private CancellationTokenRegistration cancellationRegistration;

        public Task CancellationObserved => cancellationObserved.Task;

        public Task EnsureReadyAsync(CancellationToken token)
        {
            cancellationToken = token;
            cancellationRegistration = token.Register(() => cancellationObserved.TrySetResult(true));
            return completion.Task;
        }

        public void CompleteAfterDrain()
        {
            cancellationRegistration.Dispose();
            completion.TrySetCanceled(cancellationToken);
        }
    }

    private sealed class RecordingStatusSink : ICaptureServiceStatusSink
    {
        private readonly object gate = new();
        private readonly List<CaptureServiceStatus> statuses = [];

        public CaptureServiceState[] States
        {
            get
            {
                lock (gate)
                {
                    return statuses.Select(status => status.State).ToArray();
                }
            }
        }

        public CaptureServiceStatus LastStatus
        {
            get
            {
                lock (gate)
                {
                    return statuses[^1];
                }
            }
        }

        public void Report(CaptureServiceStatus status)
        {
            lock (gate)
            {
                statuses.Add(status);
            }
        }

        public void WaitForState(CaptureServiceState expected)
        {
            var deadline = DateTime.UtcNow + TimeSpan.FromSeconds(5);
            while (DateTime.UtcNow < deadline)
            {
                lock (gate)
                {
                    if (statuses.Any(status => status.State == expected))
                    {
                        return;
                    }
                }
                Thread.Sleep(1);
            }
            throw new TimeoutException($"Service did not report {expected}.");
        }
    }

    private sealed class BlockingFakeServer : ICapturePipeServiceServer
    {
        private readonly TaskCompletionSource<bool> started = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly TaskCompletionSource<bool> stopped = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public Task Started => started.Task;
        public bool CancellationObserved { get; private set; }

        public Task ServeAsync(CancellationToken stoppingToken)
        {
            started.TrySetResult(true);
            stoppingToken.Register(() =>
            {
                CancellationObserved = true;
                stopped.TrySetResult(true);
            });
            return stopped.Task;
        }
    }

    private sealed class CompletedFakeServer : ICapturePipeServiceServer
    {
        public Task Started => Task.CompletedTask;
        public Task ServeAsync(CancellationToken stoppingToken) => Task.CompletedTask;
    }

    private sealed class StartupFailureFakeServer : ICapturePipeServiceServer
    {
        public Task Started => Task.FromException(new InvalidOperationException("startup failed"));
        public Task ServeAsync(CancellationToken stoppingToken) => Task.FromException(new InvalidOperationException("startup failed"));
    }

    private sealed class PendingStartupFakeServer : ICapturePipeServiceServer
    {
        private readonly TaskCompletionSource<bool> started = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public Task Started => started.Task;
        public bool CancellationObserved { get; private set; }

        public async Task ServeAsync(CancellationToken stoppingToken)
        {
            using CancellationTokenRegistration registration = stoppingToken.Register(() => CancellationObserved = true);
            await Task.Delay(Timeout.InfiniteTimeSpan, stoppingToken).ConfigureAwait(false);
        }
    }
}
