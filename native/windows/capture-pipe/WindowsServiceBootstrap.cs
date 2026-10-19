using System.ComponentModel;
using System.Runtime.InteropServices;

namespace DouyinTranscript.CapturePipe;

internal enum CaptureServiceState : uint
{
    Stopped = 1,
    StartPending = 2,
    StopPending = 3,
    Running = 4,
}

internal sealed record CaptureServiceStatus(
    CaptureServiceState State,
    uint ControlsAccepted,
    uint Win32ExitCode = 0,
    uint ServiceSpecificExitCode = 0,
    uint CheckPoint = 0,
    uint WaitHintMilliseconds = 0);

internal interface ICapturePipeServiceServer
{
    Task Started { get; }
    Task ServeAsync(CancellationToken stoppingToken);
}

internal interface ICaptureServiceStatusSink
{
    void Report(CaptureServiceStatus status);
}

internal interface IServiceReadinessGate
{
    // The runtime awaits this task through cancellation. A production gate must
    // observe cancellation and finish or roll back all readiness work before
    // completing its task; it must not leave a background mutation running.
    Task EnsureReadyAsync(CancellationToken cancellationToken);
}

internal sealed class WfpBaselineUnavailableGate : IServiceReadinessGate
{
    public Task EnsureReadyAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        throw new InvalidOperationException("The persistent WFP baseline coordinator is not installed.");
    }
}

internal sealed class CaptureServiceRuntime(
    ICaptureServiceStatusSink statusSink,
    IServiceReadinessGate readinessGate)
{
    internal const uint ServiceControlStop = 0x00000001;
    internal const uint ServiceControlInterrogate = 0x00000004;
    internal const uint ServiceControlShutdown = 0x00000005;
    internal const uint ErrorSuccess = 0;
    internal const uint ErrorCallNotImplemented = 120;

    private static readonly TimeSpan StartupTimeout = TimeSpan.FromSeconds(30);
    private readonly object stateGate = new();
    private CancellationTokenSource? stopping;
    private CaptureServiceStatus currentStatus = new(CaptureServiceState.Stopped, 0);

    public async Task<int> RunAsync(Func<ICapturePipeServiceServer> createServer)
    {
        ArgumentNullException.ThrowIfNull(createServer);
        using var shutdown = new CancellationTokenSource();
        using var startupDeadline = CancellationTokenSource.CreateLinkedTokenSource(shutdown.Token);
        startupDeadline.CancelAfter(StartupTimeout);
        lock (stateGate)
        {
            stopping = shutdown;
            currentStatus = new CaptureServiceStatus(
                CaptureServiceState.StartPending,
                ControlsAccepted: 0,
                CheckPoint: 1,
                WaitHintMilliseconds: checked((uint)StartupTimeout.TotalMilliseconds));
            statusSink.Report(currentStatus);
        }

        ICapturePipeServiceServer? server = null;
        Task? serving = null;
        int exitCode = 1;
        try
        {
            // Do not race this task against the deadline token: cancellation of
            // a wait does not prove that the gate's underlying operation stopped.
            // The gate owns draining or rolling back readiness work before it
            // completes, so the service stays pending until that contract holds.
            await readinessGate.EnsureReadyAsync(startupDeadline.Token).ConfigureAwait(false);
            startupDeadline.Token.ThrowIfCancellationRequested();
            server = createServer();
            serving = server.ServeAsync(shutdown.Token);
            await server.Started.WaitAsync(startupDeadline.Token).ConfigureAwait(false);

            bool stopAlreadyRequested;
            lock (stateGate)
            {
                stopAlreadyRequested = currentStatus.State == CaptureServiceState.StopPending;
                if (!stopAlreadyRequested)
                {
                    currentStatus = new CaptureServiceStatus(
                        CaptureServiceState.Running,
                        ControlsAccepted: 0x00000001 | 0x00000004);
                    statusSink.Report(currentStatus);
                }
            }

            if (stopAlreadyRequested)
            {
                shutdown.Cancel();
            }

            await serving.ConfigureAwait(false);
            exitCode = shutdown.IsCancellationRequested ? 0 : 1;
        }
        catch (OperationCanceledException) when (shutdown.IsCancellationRequested)
        {
            // A STOP/SHUTDOWN received during START_PENDING is a normal stop. Drain the
            // host task before reporting STOPPED, while retaining failure if it faults.
            if (serving is not null)
            {
                try
                {
                    await serving.ConfigureAwait(false);
                    exitCode = 0;
                }
                catch (OperationCanceledException) when (shutdown.IsCancellationRequested)
                {
                    exitCode = 0;
                }
                catch
                {
                    exitCode = 1;
                }
            }
            else
            {
                exitCode = 0;
            }
        }
        catch
        {
            shutdown.Cancel();
            if (serving is not null)
            {
                try
                {
                    await serving.ConfigureAwait(false);
                }
                catch
                {
                    // The SCM status reports only a stable failure code; no URL or path is logged.
                }
            }
            exitCode = 1;
        }
        finally
        {
            lock (stateGate)
            {
                currentStatus = exitCode == 0
                    ? new CaptureServiceStatus(CaptureServiceState.Stopped, 0)
                    : new CaptureServiceStatus(
                        CaptureServiceState.Stopped,
                        0,
                        Win32ExitCode: 1066,
                        ServiceSpecificExitCode: 1);
                statusSink.Report(currentStatus);
                stopping = null;
            }
        }
        return exitCode;
    }

    public uint HandleControl(uint control)
    {
        CaptureServiceStatus statusToReport;
        CancellationTokenSource? cancellation = null;
        lock (stateGate)
        {
            if (control == ServiceControlInterrogate)
            {
                statusToReport = currentStatus;
            }
            else if (control is ServiceControlStop or ServiceControlShutdown
                     && currentStatus.State is CaptureServiceState.StartPending or CaptureServiceState.Running)
            {
                currentStatus = new CaptureServiceStatus(
                    CaptureServiceState.StopPending,
                    ControlsAccepted: 0,
                    CheckPoint: 1,
                    WaitHintMilliseconds: 30_000);
                statusToReport = currentStatus;
                cancellation = stopping;
            }
            else
            {
                return ErrorCallNotImplemented;
            }
        }

        try
        {
            statusSink.Report(statusToReport);
            cancellation?.Cancel();
            return ErrorSuccess;
        }
        catch
        {
            cancellation?.Cancel();
            return 6; // ERROR_INVALID_HANDLE
        }
    }
}

internal static class CaptureServiceFactory
{
    public static IServiceReadinessGate CreateReadinessGate() => new WfpBaselineUnavailableGate();

    public static ICapturePipeServiceServer Create()
    {
        CaptureServiceConfiguration configuration = CaptureServiceConfiguration.LoadDefault();
        string serviceSid = CaptureServiceConfiguration.ResolveServiceSid();
        var servicePolicy = new ServicePeerPolicy(serviceSid, RequiredSessionId: 0);
        ClientPeerPolicy clientPolicy = ClientPeerPolicy.CreateForInteractiveSessions(configuration.ClientUserSids);
        return new CapturePipeHost(
            ProtocolLimits.PipeName,
            servicePolicy,
            clientPolicy,
            new FailClosedCaptureWorker());
    }
}

internal static class WindowsServiceDispatcher
{
    private const uint ErrorFailedServiceControllerConnect = 1063;

    [UnmanagedFunctionPointer(CallingConvention.Winapi)]
    private delegate void ServiceMainCallback(uint argumentCount, IntPtr arguments);

    [UnmanagedFunctionPointer(CallingConvention.Winapi)]
    private delegate uint ServiceControlHandler(uint control, uint eventType, IntPtr eventData, IntPtr context);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct ServiceTableEntry
    {
        [MarshalAs(UnmanagedType.LPWStr)]
        public string? ServiceName;
        public ServiceMainCallback? ServiceProcedure;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct NativeServiceStatus
    {
        public uint ServiceType;
        public uint CurrentState;
        public uint ControlsAccepted;
        public uint Win32ExitCode;
        public uint ServiceSpecificExitCode;
        public uint CheckPoint;
        public uint WaitHint;
    }

    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, ExactSpelling = true, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool StartServiceCtrlDispatcherW([In] ServiceTableEntry[] serviceTable);

    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, ExactSpelling = true, SetLastError = true)]
    private static extern IntPtr RegisterServiceCtrlHandlerExW(
        string serviceName,
        ServiceControlHandler handler,
        IntPtr context);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetServiceStatus(IntPtr serviceStatusHandle, ref NativeServiceStatus serviceStatus);

    private static readonly ServiceMainCallback ServiceMainRoot = ServiceMain;
    private static int serviceExitCode = 1;

    public static int Dispatch()
    {
        if (!OperatingSystem.IsWindows())
        {
            return 50; // ERROR_NOT_SUPPORTED
        }

        serviceExitCode = 1;
        ServiceTableEntry[] table =
        [
            new ServiceTableEntry
            {
                ServiceName = CaptureServiceConfiguration.ServiceName,
                ServiceProcedure = ServiceMainRoot,
            },
            new ServiceTableEntry(),
        ];
        if (!StartServiceCtrlDispatcherW(table))
        {
            int error = Marshal.GetLastWin32Error();
            if (error == ErrorFailedServiceControllerConnect)
            {
                Console.Error.WriteLine("The capture service can only run under the Windows Service Control Manager.");
            }
            else
            {
                Console.Error.WriteLine($"The Service Control Manager dispatcher failed with Win32 error {error}.");
            }
            return error;
        }
        return serviceExitCode;
    }

    private static void ServiceMain(uint argumentCount, IntPtr arguments)
    {
        _ = argumentCount;
        _ = arguments;
        try
        {
            var service = new WindowsCaptureService(CaptureServiceConfiguration.ServiceName);
            serviceExitCode = service.Run();
        }
        catch
        {
            serviceExitCode = 1;
        }
    }

    private sealed class WindowsCaptureService
    {
        private readonly ServiceControlHandler controlHandler;
        private readonly string serviceName;
        private CaptureServiceRuntime? runtime;
        private IntPtr statusHandle;

        public WindowsCaptureService(string serviceName)
        {
            this.serviceName = serviceName;
            controlHandler = HandleControl;
        }

        public int Run()
        {
            statusHandle = RegisterServiceCtrlHandlerExW(serviceName, controlHandler, IntPtr.Zero);
            if (statusHandle == IntPtr.Zero)
            {
                return Marshal.GetLastWin32Error();
            }

            runtime = new CaptureServiceRuntime(
                new WindowsStatusSink(statusHandle),
                CaptureServiceFactory.CreateReadinessGate());
            try
            {
                return runtime.RunAsync(CaptureServiceFactory.Create).GetAwaiter().GetResult();
            }
            catch
            {
                return 1;
            }
        }

        private uint HandleControl(uint control, uint eventType, IntPtr eventData, IntPtr context)
        {
            _ = eventType;
            _ = eventData;
            _ = context;
            return runtime?.HandleControl(control) ?? CaptureServiceRuntime.ErrorCallNotImplemented;
        }
    }

    private sealed class WindowsStatusSink(IntPtr statusHandle) : ICaptureServiceStatusSink
    {
        public void Report(CaptureServiceStatus status)
        {
            var native = new NativeServiceStatus
            {
                ServiceType = 0x00000010, // SERVICE_WIN32_OWN_PROCESS
                CurrentState = (uint)status.State,
                ControlsAccepted = status.ControlsAccepted,
                Win32ExitCode = status.Win32ExitCode,
                ServiceSpecificExitCode = status.ServiceSpecificExitCode,
                CheckPoint = status.CheckPoint,
                WaitHint = status.WaitHintMilliseconds,
            };
            if (!SetServiceStatus(statusHandle, ref native))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not report capture service state.");
            }
        }
    }
}
