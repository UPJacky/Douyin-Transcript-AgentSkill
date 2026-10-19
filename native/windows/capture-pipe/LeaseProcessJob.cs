using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace DouyinTranscript.CapturePipe;

internal sealed class SafeJobObjectHandle : SafeHandleZeroOrMinusOneIsInvalid
{
    internal SafeJobObjectHandle() : base(true) { }

    internal SafeJobObjectHandle(IntPtr handle, bool ownsHandle = true) : base(ownsHandle) => SetHandle(handle);

    protected override bool ReleaseHandle() => LeaseProcessJobNativeMethods.CloseHandle(handle);
}

internal sealed class SafeThreadHandle : SafeHandleZeroOrMinusOneIsInvalid
{
    internal SafeThreadHandle() : base(true) { }

    internal SafeThreadHandle(IntPtr handle, bool ownsHandle = true) : base(ownsHandle) => SetHandle(handle);

    protected override bool ReleaseHandle() => LeaseProcessJobNativeMethods.CloseHandle(handle);
}

internal sealed class SuspendedLeaseProcess : IDisposable
{
    private bool _transferred;

    internal SuspendedLeaseProcess(SafeProcessHandle processHandle, SafeThreadHandle primaryThreadHandle, uint processId)
    {
        if (processHandle.IsInvalid || processHandle.IsClosed)
        {
            throw new ArgumentException("The suspended process handle is invalid.", nameof(processHandle));
        }
        if (primaryThreadHandle.IsInvalid || primaryThreadHandle.IsClosed)
        {
            throw new ArgumentException("The suspended primary-thread handle is invalid.", nameof(primaryThreadHandle));
        }
        if (processId == 0)
        {
            throw new ArgumentOutOfRangeException(nameof(processId));
        }

        ProcessHandle = processHandle;
        PrimaryThreadHandle = primaryThreadHandle;
        ProcessId = processId;
    }

    internal SafeProcessHandle ProcessHandle { get; }
    internal SafeThreadHandle PrimaryThreadHandle { get; }
    internal uint ProcessId { get; }

    internal void TransferToJob()
    {
        if (_transferred)
        {
            throw new InvalidOperationException("The suspended process was already transferred to a job.");
        }
        _transferred = true;
    }

    public void Dispose()
    {
        PrimaryThreadHandle.Dispose();
        ProcessHandle.Dispose();
    }
}

internal interface ILeaseProcessJobNative
{
    SafeJobObjectHandle CreateUnnamedJob();
    void SetKillOnClose(SafeJobObjectHandle job);
    uint GetLimitFlags(SafeJobObjectHandle job);
    void AssignProcess(SafeJobObjectHandle job, SafeProcessHandle process);
    uint ResumePrimaryThread(SafeThreadHandle thread);
    void TerminateProcess(SafeProcessHandle process, uint exitCode);
    void WaitForProcessExit(SafeProcessHandle process, TimeSpan timeout);
    void TerminateJob(SafeJobObjectHandle job, uint exitCode);
    uint GetActiveProcessCount(SafeJobObjectHandle job);
    bool IsProcessInJob(SafeProcessHandle process, SafeJobObjectHandle job);
}

internal sealed class WindowsLeaseProcessJobNative : ILeaseProcessJobNative
{
    public SafeJobObjectHandle CreateUnnamedJob()
    {
        EnsureWindows();
        SafeJobObjectHandle job = LeaseProcessJobNativeMethods.CreateJobObjectW(IntPtr.Zero, null);
        if (job.IsInvalid)
        {
            Exception error = LastError("Could not create the lease process job.");
            job.Dispose();
            throw error;
        }
        return job;
    }

    public void SetKillOnClose(SafeJobObjectHandle job)
    {
        var limits = LeaseProcessJobNativeMethods.ExtendedLimitInformation.CreateKillOnCloseOnly();
        if (!LeaseProcessJobNativeMethods.SetInformationJobObject(
                job,
                LeaseProcessJobNativeMethods.JobObjectExtendedLimitInformation,
                ref limits,
                (uint)Marshal.SizeOf<LeaseProcessJobNativeMethods.ExtendedLimitInformation>()))
        {
            throw LastError("Could not enable kill-on-close for the lease process job.");
        }
    }

    public uint GetLimitFlags(SafeJobObjectHandle job)
    {
        LeaseProcessJobNativeMethods.ExtendedLimitInformation limits = default;
        if (!LeaseProcessJobNativeMethods.QueryInformationJobObject(
                job,
                LeaseProcessJobNativeMethods.JobObjectExtendedLimitInformation,
                ref limits,
                (uint)Marshal.SizeOf<LeaseProcessJobNativeMethods.ExtendedLimitInformation>(),
                out _))
        {
            throw LastError("Could not read lease process job limits.");
        }
        return limits.BasicLimitInformation.LimitFlags;
    }

    public void AssignProcess(SafeJobObjectHandle job, SafeProcessHandle process)
    {
        if (!LeaseProcessJobNativeMethods.AssignProcessToJobObject(job, process))
        {
            throw LastError("Could not assign the suspended lease process to its job.");
        }
    }

    public uint ResumePrimaryThread(SafeThreadHandle thread)
    {
        uint previousSuspendCount = LeaseProcessJobNativeMethods.ResumeThread(thread);
        if (previousSuspendCount == uint.MaxValue)
        {
            throw LastError("Could not resume the lease process primary thread.");
        }
        return previousSuspendCount;
    }

    public void TerminateProcess(SafeProcessHandle process, uint exitCode)
    {
        if (!LeaseProcessJobNativeMethods.TerminateProcess(process, exitCode))
        {
            int error = Marshal.GetLastWin32Error();
            if (LeaseProcessJobNativeMethods.WaitForSingleObject(process, 0) == LeaseProcessJobNativeMethods.WaitObject0)
            {
                return;
            }
            throw new Win32Exception(error, "Could not terminate a suspended lease process.");
        }
    }

    public void WaitForProcessExit(SafeProcessHandle process, TimeSpan timeout)
    {
        uint result = LeaseProcessJobNativeMethods.WaitForSingleObject(process, ToMilliseconds(timeout));
        if (result == LeaseProcessJobNativeMethods.WaitObject0)
        {
            return;
        }
        if (result == LeaseProcessJobNativeMethods.WaitTimeout)
        {
            throw new TimeoutException("The lease process did not exit before the timeout.");
        }
        throw LastError("Could not wait for the lease process.");
    }

    public void TerminateJob(SafeJobObjectHandle job, uint exitCode)
    {
        if (!LeaseProcessJobNativeMethods.TerminateJobObject(job, exitCode))
        {
            throw LastError("Could not terminate the lease process job.");
        }
    }

    public uint GetActiveProcessCount(SafeJobObjectHandle job)
    {
        LeaseProcessJobNativeMethods.BasicAccountingInformation accounting = default;
        if (!LeaseProcessJobNativeMethods.QueryInformationJobObject(
                job,
                LeaseProcessJobNativeMethods.JobObjectBasicAccountingInformation,
                ref accounting,
                (uint)Marshal.SizeOf<LeaseProcessJobNativeMethods.BasicAccountingInformation>(),
                out _))
        {
            throw LastError("Could not read the active lease process count.");
        }
        return accounting.ActiveProcesses;
    }

    public bool IsProcessInJob(SafeProcessHandle process, SafeJobObjectHandle job)
    {
        if (!LeaseProcessJobNativeMethods.IsProcessInJob(process, job, out bool isInJob))
        {
            throw LastError("Could not verify lease process job membership.");
        }
        return isInJob;
    }

    private static uint ToMilliseconds(TimeSpan timeout)
    {
        if (timeout <= TimeSpan.Zero || timeout.TotalMilliseconds > int.MaxValue)
        {
            throw new ArgumentOutOfRangeException(nameof(timeout));
        }
        return (uint)Math.Ceiling(timeout.TotalMilliseconds);
    }

    private static void EnsureWindows()
    {
        if (!OperatingSystem.IsWindows())
        {
            throw new PlatformNotSupportedException("Windows Job Objects are required for lease process supervision.");
        }
    }

    private static Exception LastError(string operation) => new Win32Exception(Marshal.GetLastWin32Error(), operation);
}

internal sealed class LeaseProcessJob : IDisposable, IAsyncDisposable
{
    internal const uint KillOnJobClose = 0x00002000;
    internal const uint BreakawayOk = 0x00000800;
    internal const uint SilentBreakawayOk = 0x00001000;
    private const uint CleanupExitCode = 0xD7010001;
    private const int JobDrainPollMilliseconds = 20;
    private const int SuspendedProcessCleanupMilliseconds = 5000;
    private const int MaximumJobDrainMilliseconds = 30000;

    private readonly ILeaseProcessJobNative _native;
    private readonly SafeJobObjectHandle _job;
    private readonly SemaphoreSlim _lifecycle = new(1, 1);
    private SuspendedLeaseProcess? _rootProcess;
    private bool _closed;

    private LeaseProcessJob(ILeaseProcessJobNative native, SafeJobObjectHandle job)
    {
        _native = native;
        _job = job;
    }

    internal uint RootProcessId => _rootProcess?.ProcessId ?? throw new InvalidOperationException("No lease process has started.");
    internal SafeProcessHandle RootProcessHandle => _rootProcess?.ProcessHandle ?? throw new InvalidOperationException("No lease process has started.");

    internal static LeaseProcessJob Start(
        Func<SuspendedLeaseProcess> createSuspendedProcess,
        ILeaseProcessJobNative? native = null)
    {
        ArgumentNullException.ThrowIfNull(createSuspendedProcess);
        native ??= new WindowsLeaseProcessJobNative();
        SafeJobObjectHandle jobHandle = native.CreateUnnamedJob();
        if (jobHandle.IsInvalid || jobHandle.IsClosed)
        {
            jobHandle.Dispose();
            throw new InvalidOperationException("The native job factory returned an invalid handle.");
        }

        var job = new LeaseProcessJob(native, jobHandle);
        SuspendedLeaseProcess? suspended = null;
        try
        {
            native.SetKillOnClose(jobHandle);
            uint configuredFlags = native.GetLimitFlags(jobHandle);
            if (configuredFlags != KillOnJobClose)
            {
                throw new InvalidOperationException("The lease job did not retain exactly kill-on-close with breakaway disabled.");
            }

            suspended = createSuspendedProcess()
                ?? throw new InvalidOperationException("The process launcher returned no suspended process.");
            SuspendedLeaseProcess ownedSuspended = suspended;
            suspended = null;
            job.AssignAndResume(ownedSuspended);
            return job;
        }
        catch (Exception startError)
        {
            List<Exception> cleanupErrors = [];
            if (suspended is not null)
            {
                try
                {
                    native.TerminateProcess(suspended.ProcessHandle, CleanupExitCode);
                    native.WaitForProcessExit(
                        suspended.ProcessHandle,
                        TimeSpan.FromMilliseconds(SuspendedProcessCleanupMilliseconds));
                }
                catch (Exception cleanupError)
                {
                    cleanupErrors.Add(cleanupError);
                }
                suspended.Dispose();
            }
            try
            {
                job.Dispose();
            }
            catch (Exception cleanupError)
            {
                cleanupErrors.Add(cleanupError);
            }

            if (cleanupErrors.Count > 0)
            {
                throw new AggregateException("Lease process startup failed and cleanup was incomplete.",
                    [startError, .. cleanupErrors]);
            }
            throw;
        }
    }

    internal bool IsProcessInJob(SafeProcessHandle process) => _native.IsProcessInJob(process, _job);

    internal async Task StopAndWaitAsync(TimeSpan timeout)
    {
        if (timeout <= TimeSpan.Zero || timeout.TotalMilliseconds > MaximumJobDrainMilliseconds)
        {
            throw new ArgumentOutOfRangeException(nameof(timeout));
        }

        await _lifecycle.WaitAsync().ConfigureAwait(false);
        try
        {
            if (_closed)
            {
                return;
            }

            try
            {
                if (_native.GetActiveProcessCount(_job) > 0)
                {
                    _native.TerminateJob(_job, CleanupExitCode);
                    long deadline = Environment.TickCount64 + (long)Math.Ceiling(timeout.TotalMilliseconds);
                    while (_native.GetActiveProcessCount(_job) > 0)
                    {
                        if (Environment.TickCount64 >= deadline)
                        {
                            throw new TimeoutException("The lease process tree did not drain before the timeout.");
                        }
                        await Task.Delay(JobDrainPollMilliseconds).ConfigureAwait(false);
                    }
                }
            }
            catch
            {
                CloseCore();
                throw;
            }

            CloseCore();
        }
        finally
        {
            _lifecycle.Release();
        }
    }

    public void Dispose()
    {
        StopAndWaitAsync(TimeSpan.FromSeconds(10)).GetAwaiter().GetResult();
    }

    public async ValueTask DisposeAsync()
    {
        await StopAndWaitAsync(TimeSpan.FromSeconds(10)).ConfigureAwait(false);
    }

    private void AssignAndResume(SuspendedLeaseProcess suspended)
    {
        try
        {
            _native.AssignProcess(_job, suspended.ProcessHandle);
        }
        catch (Exception assignError)
        {
            List<Exception> cleanupErrors = [];
            try
            {
                _native.TerminateProcess(suspended.ProcessHandle, CleanupExitCode);
                _native.WaitForProcessExit(
                    suspended.ProcessHandle,
                    TimeSpan.FromMilliseconds(SuspendedProcessCleanupMilliseconds));
            }
            catch (Exception cleanupError)
            {
                cleanupErrors.Add(cleanupError);
            }
            suspended.Dispose();
            CloseCore();
            if (cleanupErrors.Count > 0)
            {
                throw new AggregateException("Assigning the lease process failed and the unassigned process could not be confirmed stopped.",
                    [assignError, .. cleanupErrors]);
            }
            throw;
        }

        try
        {
            uint previousSuspendCount = _native.ResumePrimaryThread(suspended.PrimaryThreadHandle);
            if (previousSuspendCount != 1)
            {
                throw new InvalidOperationException(
                    "The primary thread did not have exactly one initial suspension; the process was not accepted.");
            }
            suspended.TransferToJob();
            _rootProcess = suspended;
        }
        catch (Exception resumeError)
        {
            List<Exception> cleanupErrors = [];
            try
            {
                _native.TerminateJob(_job, CleanupExitCode);
                WaitForJobDrainSynchronously(TimeSpan.FromMilliseconds(SuspendedProcessCleanupMilliseconds));
            }
            catch (Exception cleanupError)
            {
                cleanupErrors.Add(cleanupError);
            }
            suspended.Dispose();
            CloseCore();
            if (cleanupErrors.Count > 0)
            {
                throw new AggregateException("Resuming the lease process failed and the assigned tree could not be confirmed stopped.",
                    [resumeError, .. cleanupErrors]);
            }
            throw;
        }
    }

    private void WaitForJobDrainSynchronously(TimeSpan timeout)
    {
        long deadline = Environment.TickCount64 + (long)Math.Ceiling(timeout.TotalMilliseconds);
        while (_native.GetActiveProcessCount(_job) > 0)
        {
            if (Environment.TickCount64 >= deadline)
            {
                throw new TimeoutException("The failed lease process tree did not drain before the timeout.");
            }
            Thread.Sleep(JobDrainPollMilliseconds);
        }
    }

    private void CloseCore()
    {
        if (_closed)
        {
            return;
        }
        _closed = true;
        _job.Dispose();
        _rootProcess?.Dispose();
        _rootProcess = null;
    }
}

internal static class LeaseProcessJobNativeMethods
{
    internal const int JobObjectBasicAccountingInformation = 1;
    internal const int JobObjectExtendedLimitInformation = 9;
    internal const uint WaitObject0 = 0;
    internal const uint WaitTimeout = 258;

    [StructLayout(LayoutKind.Sequential)]
    internal struct BasicLimitInformation
    {
        public long PerProcessUserTimeLimit;
        public long PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize;
        public UIntPtr MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass;
        public uint SchedulingClass;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct IoCounters
    {
        public ulong ReadOperationCount;
        public ulong WriteOperationCount;
        public ulong OtherOperationCount;
        public ulong ReadTransferCount;
        public ulong WriteTransferCount;
        public ulong OtherTransferCount;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct ExtendedLimitInformation
    {
        public BasicLimitInformation BasicLimitInformation;
        public IoCounters IoInfo;
        public UIntPtr ProcessMemoryLimit;
        public UIntPtr JobMemoryLimit;
        public UIntPtr PeakProcessMemoryUsed;
        public UIntPtr PeakJobMemoryUsed;

        public static ExtendedLimitInformation CreateKillOnCloseOnly() => new()
        {
            BasicLimitInformation = new BasicLimitInformation { LimitFlags = LeaseProcessJob.KillOnJobClose },
        };
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct BasicAccountingInformation
    {
        public long TotalUserTime;
        public long TotalKernelTime;
        public long ThisPeriodTotalUserTime;
        public long ThisPeriodTotalKernelTime;
        public uint TotalPageFaultCount;
        public uint TotalProcesses;
        public uint ActiveProcesses;
        public uint TotalTerminatedProcesses;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true, SetLastError = true)]
    internal static extern SafeJobObjectHandle CreateJobObjectW(IntPtr jobAttributes, string? name);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool SetInformationJobObject(
        SafeJobObjectHandle job,
        int informationClass,
        ref ExtendedLimitInformation information,
        uint informationLength);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool QueryInformationJobObject(
        SafeJobObjectHandle job,
        int informationClass,
        ref BasicAccountingInformation information,
        uint informationLength,
        out uint returnLength);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool QueryInformationJobObject(
        SafeJobObjectHandle job,
        int informationClass,
        ref ExtendedLimitInformation information,
        uint informationLength,
        out uint returnLength);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool AssignProcessToJobObject(SafeJobObjectHandle job, SafeProcessHandle process);

    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern uint ResumeThread(SafeThreadHandle thread);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool TerminateProcess(SafeProcessHandle process, uint exitCode);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool TerminateJobObject(SafeJobObjectHandle job, uint exitCode);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool IsProcessInJob(SafeProcessHandle process, SafeJobObjectHandle job, [MarshalAs(UnmanagedType.Bool)] out bool result);

    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern uint WaitForSingleObject(SafeProcessHandle handle, uint milliseconds);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool CloseHandle(IntPtr handle);
}
