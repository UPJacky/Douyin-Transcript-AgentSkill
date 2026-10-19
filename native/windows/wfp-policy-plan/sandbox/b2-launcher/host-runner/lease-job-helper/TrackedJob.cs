using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
using DouyinTranscript.CapturePipe;

namespace DouyinTranscript.LeaseJobHelper;

internal sealed class TrackedJobNative : ILeaseProcessJobNative, IDisposable
{
    internal const uint MessageActiveProcessZero = 4;
    internal const uint MessageNewProcess = 6;
    internal const uint MessageExitProcess = 7;
    internal const uint MessageAbnormalExitProcess = 8;

    private const long CompletionKeyValue = 0x42324A4F42;
    private readonly WindowsLeaseProcessJobNative _inner = new();
    private SafeNativeHandle? _monitorJob;
    private SafeNativeHandle? _completionPort;
    private bool _disposed;

    internal SafeJobObjectHandle MonitorJob => _monitorJob is { IsInvalid: false, IsClosed: false }
        ? new SafeJobObjectHandle(_monitorJob.DangerousGetHandle(), ownsHandle: false)
        : throw new InvalidOperationException("The monitor job handle is not initialized.");
    internal SafeNativeHandle CompletionPort => _completionPort is { IsInvalid: false, IsClosed: false }
        ? _completionPort
        : throw new InvalidOperationException("The job completion port is not initialized.");
    internal IntPtr CompletionKey => new(CompletionKeyValue);

    public SafeJobObjectHandle CreateUnnamedJob() => _inner.CreateUnnamedJob();

    public void SetKillOnClose(SafeJobObjectHandle job)
    {
        _inner.SetKillOnClose(job);
        if (!NativeMethods.DuplicateHandle(NativeMethods.GetCurrentProcess(), job.DangerousGetHandle(),
                NativeMethods.GetCurrentProcess(), out SafeNativeHandle monitor, 0, false, NativeMethods.DuplicateSameAccess))
        {
            throw LastError("DuplicateHandle.JobMonitor");
        }
        _monitorJob = monitor;

        IntPtr port = NativeMethods.CreateIoCompletionPort(new IntPtr(-1), IntPtr.Zero, CompletionKey, 1);
        if (port == IntPtr.Zero)
        {
            throw LastError("CreateIoCompletionPort");
        }
        _completionPort = new SafeNativeHandle(port);
        var association = new NativeMethods.JobObjectAssociateCompletionPort
        {
            CompletionKey = CompletionKey,
            CompletionPort = port,
        };
        if (!NativeMethods.SetInformationJobObject(job, NativeMethods.JobObjectAssociateCompletionPortInformation,
                ref association, (uint)Marshal.SizeOf<NativeMethods.JobObjectAssociateCompletionPort>()))
        {
            throw LastError("SetInformationJobObject.AssociateCompletionPort");
        }
    }

    public uint GetLimitFlags(SafeJobObjectHandle job) => _inner.GetLimitFlags(job);
    public void AssignProcess(SafeJobObjectHandle job, SafeProcessHandle process) => _inner.AssignProcess(job, process);
    public uint ResumePrimaryThread(SafeThreadHandle thread) => _inner.ResumePrimaryThread(thread);
    public void TerminateProcess(SafeProcessHandle process, uint exitCode) => _inner.TerminateProcess(process, exitCode);
    public void WaitForProcessExit(SafeProcessHandle process, TimeSpan timeout) => _inner.WaitForProcessExit(process, timeout);
    public void TerminateJob(SafeJobObjectHandle job, uint exitCode) => _inner.TerminateJob(job, exitCode);
    public uint GetActiveProcessCount(SafeJobObjectHandle job) => _inner.GetActiveProcessCount(job);
    public bool IsProcessInJob(SafeProcessHandle process, SafeJobObjectHandle job) => _inner.IsProcessInJob(process, job);

    internal uint GetActiveProcessCountAfterStop()
    {
        using SafeJobObjectHandle monitor = MonitorJob;
        return _inner.GetActiveProcessCount(monitor);
    }

    internal void EmergencyTerminateAndDrain(TimeSpan timeout)
    {
        using SafeJobObjectHandle monitor = MonitorJob;
        if (_inner.GetActiveProcessCount(monitor) > 0)
        {
            _inner.TerminateJob(monitor, 0xD7010002);
            long deadline = Environment.TickCount64 + (long)Math.Ceiling(timeout.TotalMilliseconds);
            while (_inner.GetActiveProcessCount(monitor) > 0)
            {
                if (Environment.TickCount64 >= deadline)
                {
                    throw new TimeoutException("The tracked process job did not drain after emergency termination.");
                }
                Thread.Sleep(20);
            }
        }
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }
        _disposed = true;
        _completionPort?.Dispose();
        _completionPort = null;
        _monitorJob?.Dispose();
        _monitorJob = null;
    }

    private static NativeApiException LastError(string api) => new(api, Marshal.GetLastWin32Error());
}
