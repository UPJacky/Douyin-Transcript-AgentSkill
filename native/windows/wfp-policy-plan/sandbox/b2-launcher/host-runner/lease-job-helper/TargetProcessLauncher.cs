using System.Security.Cryptography;
using System.Runtime.InteropServices;
using System.Text;
using DouyinTranscript.CapturePipe;
using Microsoft.Win32.SafeHandles;

namespace DouyinTranscript.LeaseJobHelper;

internal sealed class SuspendedLaunch
{
    internal SuspendedLaunch(SuspendedLeaseProcess process, ProcessOutputCapture output)
    {
        Process = process;
        Output = output;
    }

    internal SuspendedLeaseProcess Process { get; }
    internal ProcessOutputCapture Output { get; }
}

internal sealed class ProcessOutputCapture : IAsyncDisposable
{
    private readonly FileStream _stdout;
    private readonly FileStream _stderr;
    private readonly OutputCaptureState _stdoutState;
    private readonly OutputCaptureState _stderrState;
    private Task _stdoutTask = Task.CompletedTask;
    private Task _stderrTask = Task.CompletedTask;
    private bool _started;
    private bool _disposed;

    internal bool OutputLimitExceeded => _stdoutState.LimitExceeded || _stderrState.LimitExceeded;

    internal ProcessOutputCapture(SafeFileHandle stdoutRead, SafeFileHandle stderrRead, long? maxBytesPerStream = null)
    {
        ValidateMaxBytesPerStream(maxBytesPerStream);
        FileStream stdout;
        FileStream stderr;
        try
        {
            stdout = new FileStream(stdoutRead, FileAccess.Read, 16 * 1024, isAsync: false);
            try
            {
                stderr = new FileStream(stderrRead, FileAccess.Read, 16 * 1024, isAsync: false);
            }
            catch
            {
                stdout.Dispose();
                throw;
            }
        }
        catch
        {
            stdoutRead.Dispose();
            stderrRead.Dispose();
            throw;
        }
        _stdout = stdout;
        _stderr = stderr;
        _stdoutState = new OutputCaptureState(maxBytesPerStream);
        _stderrState = new OutputCaptureState(maxBytesPerStream);
    }

    internal static async Task ValidateSynchronousPipeCaptureAsync()
    {
        SafeFileHandle? stdoutRead = null;
        SafeFileHandle? stdoutWrite = null;
        SafeFileHandle? stderrRead = null;
        SafeFileHandle? stderrWrite = null;
        ProcessOutputCapture? capture = null;
        try
        {
            var attributes = new NativeMethods.SecurityAttributes
            {
                Length = Marshal.SizeOf<NativeMethods.SecurityAttributes>(),
                InheritHandle = false,
            };
            if (!NativeMethods.CreatePipe(out SafeFileHandle createdStdoutRead,
                    out SafeFileHandle createdStdoutWrite, ref attributes, 0))
            {
                throw new NativeApiException("CreatePipe.StdoutSelfTest", Marshal.GetLastWin32Error());
            }
            stdoutRead = createdStdoutRead;
            stdoutWrite = createdStdoutWrite;
            if (!NativeMethods.CreatePipe(out SafeFileHandle createdStderrRead,
                    out SafeFileHandle createdStderrWrite, ref attributes, 0))
            {
                throw new NativeApiException("CreatePipe.StderrSelfTest", Marshal.GetLastWin32Error());
            }
            stderrRead = createdStderrRead;
            stderrWrite = createdStderrWrite;

            capture = new ProcessOutputCapture(stdoutRead, stderrRead);
            stdoutRead = null;
            stderrRead = null;
            stdoutWrite.Dispose();
            stdoutWrite = null;
            stderrWrite.Dispose();
            stderrWrite = null;

            (CapturedStream stdout, CapturedStream stderr, bool complete) =
                await capture.CompleteAsync(TimeSpan.FromSeconds(2)).ConfigureAwait(false);
            if (!complete || stdout.Bytes != 0 || stderr.Bytes != 0)
            {
                throw new InvalidOperationException("Synchronous pipe output capture did not complete with empty closed streams.");
            }
        }
        finally
        {
            if (capture is not null) await capture.DisposeAsync().ConfigureAwait(false);
            stdoutRead?.Dispose();
            stdoutWrite?.Dispose();
            stderrRead?.Dispose();
            stderrWrite?.Dispose();
        }
    }

    internal static async Task ValidateHardOutputByteLimitCaptureAsync()
    {
        const int byteLimit = 4;
        byte[] sample = Encoding.ASCII.GetBytes("ABCDEF");
        var boundedProbe = new ReadProbeStream(sample);
        var boundedState = new OutputCaptureState(byteLimit);
        await CaptureAsync(boundedProbe, boundedState).ConfigureAwait(false);
        CapturedStream bounded = boundedState.Snapshot();
        if (!bounded.LimitExceeded || bounded.Bytes != byteLimit || bounded.Text != "ABCD"
            || boundedProbe.BytesRead != byteLimit + 1 || boundedProbe.ReadCalls != 1)
        {
            throw new InvalidOperationException("Bounded in-memory capture did not stop after reading the one-byte overflow sentinel.");
        }

        var exactProbe = new ReadProbeStream(sample.AsSpan(0, byteLimit).ToArray());
        var exactState = new OutputCaptureState(byteLimit);
        await CaptureAsync(exactProbe, exactState).ConfigureAwait(false);
        CapturedStream exact = exactState.Snapshot();
        if (exact.LimitExceeded || exact.Bytes != byteLimit || exact.Text != "ABCD")
        {
            throw new InvalidOperationException("Bounded in-memory capture marked an exact-limit stream as exceeding its limit.");
        }

        var defaultProbe = new ReadProbeStream(sample);
        var defaultState = new OutputCaptureState();
        await CaptureAsync(defaultProbe, defaultState).ConfigureAwait(false);
        CapturedStream defaultCapture = defaultState.Snapshot();
        if (defaultCapture.LimitExceeded || defaultCapture.Bytes != sample.Length || defaultCapture.Text != "ABCDEF")
        {
            throw new InvalidOperationException("Default in-memory capture behavior changed when no hard byte limit was configured.");
        }

        bool negativeLimitRejected = false;
        try { ValidateMaxBytesPerStream(-1); }
        catch (ArgumentOutOfRangeException) { negativeLimitRejected = true; }
        if (!negativeLimitRejected)
        {
            throw new InvalidOperationException("A negative output byte limit was not rejected.");
        }

        var attributes = new NativeMethods.SecurityAttributes
        {
            Length = Marshal.SizeOf<NativeMethods.SecurityAttributes>(),
            InheritHandle = false,
        };
        SafeFileHandle? stdoutRead = null;
        SafeFileHandle? stdoutWrite = null;
        SafeFileHandle? stderrRead = null;
        SafeFileHandle? stderrWrite = null;
        FileStream? stdoutWriter = null;
        FileStream? stderrWriter = null;
        ProcessOutputCapture? capture = null;
        try
        {
            if (!NativeMethods.CreatePipe(out SafeFileHandle createdStdoutRead,
                    out SafeFileHandle createdStdoutWrite, ref attributes, 0))
            {
                throw new NativeApiException("CreatePipe.BoundedSelfTest.Stdout", Marshal.GetLastWin32Error());
            }
            stdoutRead = createdStdoutRead;
            stdoutWrite = createdStdoutWrite;
            if (!NativeMethods.CreatePipe(out SafeFileHandle createdStderrRead,
                    out SafeFileHandle createdStderrWrite, ref attributes, 0))
            {
                throw new NativeApiException("CreatePipe.BoundedSelfTest.Stderr", Marshal.GetLastWin32Error());
            }
            stderrRead = createdStderrRead;
            stderrWrite = createdStderrWrite;

            capture = new ProcessOutputCapture(stdoutRead, stderrRead, byteLimit);
            stdoutRead = null;
            stderrRead = null;
            stdoutWriter = new FileStream(stdoutWrite, FileAccess.Write, 16 * 1024, isAsync: false);
            stdoutWrite = null;
            stderrWriter = new FileStream(stderrWrite, FileAccess.Write, 16 * 1024, isAsync: false);
            stderrWrite = null;

            capture.Start();
            stdoutWriter.Write(sample, 0, sample.Length);
            stderrWriter.Write(sample, 0, byteLimit);
            stdoutWriter.Dispose();
            stdoutWriter = null;
            stderrWriter.Dispose();
            stderrWriter = null;

            (CapturedStream stdout, CapturedStream stderr, bool complete) =
                await capture.CompleteAsync(TimeSpan.FromSeconds(2)).ConfigureAwait(false);
            if (!complete || !stdout.LimitExceeded || stdout.Bytes != byteLimit || stdout.Text != "ABCD"
                || stderr.LimitExceeded || stderr.Bytes != byteLimit || stderr.Text != "ABCD")
            {
                throw new InvalidOperationException("Bounded anonymous-pipe capture did not enforce independent per-stream byte limits.");
            }
        }
        finally
        {
            if (capture is not null) await capture.DisposeAsync().ConfigureAwait(false);
            stdoutWriter?.Dispose();
            stderrWriter?.Dispose();
            stdoutRead?.Dispose();
            stdoutWrite?.Dispose();
            stderrRead?.Dispose();
            stderrWrite?.Dispose();
        }
    }

    internal void Start()
    {
        if (_started) return;
        _started = true;
        _stdoutTask = CaptureAsync(_stdout, _stdoutState);
        _stderrTask = CaptureAsync(_stderr, _stderrState);
    }

    internal async Task<(CapturedStream Stdout, CapturedStream Stderr, bool Complete)> CompleteAsync(TimeSpan timeout)
    {
        Start();
        Task both = Task.WhenAll(_stdoutTask, _stderrTask);
        if (await Task.WhenAny(both, Task.Delay(timeout)).ConfigureAwait(false) != both)
        {
            _ = _stdoutState.Snapshot();
            _ = _stderrState.Snapshot();
            CloseReaders();
            return (_stdoutState.Snapshot(), _stderrState.Snapshot(), false);
        }
        await both.ConfigureAwait(false);
        return (_stdoutState.Snapshot(), _stderrState.Snapshot(), true);
    }

    public ValueTask DisposeAsync()
    {
        CloseReaders();
        return ValueTask.CompletedTask;
    }

    private void CloseReaders()
    {
        if (_disposed) return;
        _disposed = true;
        try { _stdout.Dispose(); } catch (IOException) { }
        try { _stderr.Dispose(); } catch (IOException) { }
    }

    private static async Task CaptureAsync(Stream input, OutputCaptureState state)
    {
        byte[] buffer = new byte[16 * 1024];
        try
        {
            while (true)
            {
                int requested = state.GetReadSize(buffer.Length);
                if (requested == 0) break;
                int read = await input.ReadAsync(buffer.AsMemory(0, requested)).ConfigureAwait(false);
                if (read == 0) break;
                if (state.Append(buffer, read)) break;
            }
        }
        catch (IOException) { }
        catch (ObjectDisposedException) { }
    }

    internal static void ValidateMaxBytesPerStream(long? maxBytesPerStream)
    {
        if (maxBytesPerStream is < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maxBytesPerStream), "The output byte limit cannot be negative.");
        }
    }

    private sealed class ReadProbeStream(byte[] data) : Stream
    {
        private int _position;

        internal int ReadCalls { get; private set; }
        internal int BytesRead => _position;
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => data.Length;
        public override long Position
        {
            get => _position;
            set => throw new NotSupportedException();
        }

        public override ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            ReadCalls++;
            int count = Math.Min(buffer.Length, data.Length - _position);
            data.AsMemory(_position, count).CopyTo(buffer);
            _position += count;
            return ValueTask.FromResult(count);
        }

        public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        public override void Flush() => throw new NotSupportedException();
    }
}

internal sealed class OutputCaptureState
{
    private const int MaxStoredBytes = 4 * 1024 * 1024;
    private readonly object _gate = new();
    private readonly IncrementalHash _hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
    private readonly MemoryStream _stored = new();
    private readonly long? _maxBytes;
    private long _bytes;
    private bool _truncated;
    private bool _limitExceeded;

    internal OutputCaptureState(long? maxBytes = null)
    {
        if (maxBytes is < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maxBytes), "The output byte limit cannot be negative.");
        }
        _maxBytes = maxBytes;
    }

    internal int GetReadSize(int maximumReadSize)
    {
        lock (_gate)
        {
            if (_limitExceeded) return 0;
            if (_maxBytes is not long limit) return maximumReadSize;
            long remaining = limit - _bytes;
            return remaining >= maximumReadSize ? maximumReadSize : checked((int)remaining + 1);
        }
    }

    internal bool Append(byte[] buffer, int count)
    {
        lock (_gate)
        {
            int acceptedCount = count;
            if (_maxBytes is long limit)
            {
                long remaining = limit - _bytes;
                if (count > remaining)
                {
                    acceptedCount = checked((int)remaining);
                    _limitExceeded = true;
                }
            }

            if (acceptedCount > 0)
            {
                _hash.AppendData(buffer, 0, acceptedCount);
                _bytes += acceptedCount;
                int remainingStorage = MaxStoredBytes - checked((int)_stored.Length);
                if (remainingStorage > 0)
                {
                    int keep = Math.Min(remainingStorage, acceptedCount);
                    _stored.Write(buffer, 0, keep);
                    _truncated |= keep < acceptedCount;
                }
                else
                {
                    _truncated = true;
                }
            }
            return _limitExceeded;
        }
    }

    internal CapturedStream Snapshot()
    {
        lock (_gate)
        {
            byte[] hash = _hash.GetCurrentHash();
            return new CapturedStream(_bytes, Convert.ToHexString(hash).ToLowerInvariant(),
                Encoding.UTF8.GetString(_stored.ToArray()), _truncated, _limitExceeded);
        }
    }

    internal bool LimitExceeded
    {
        get { lock (_gate) return _limitExceeded; }
    }
}

internal sealed record CapturedStream(long Bytes, string Sha256, string Text, bool Truncated, bool LimitExceeded = false)
{
    internal static CapturedStream Empty { get; } = new(0, Convert.ToHexString(SHA256.HashData([])).ToLowerInvariant(), string.Empty, false);

    internal Dictionary<string, object?> Summary(bool includeTail = false) => new()
    {
        ["bytes"] = Bytes,
        ["sha256"] = Sha256,
        ["captured"] = true,
        ["truncated_in_memory"] = Truncated,
        ["limit_exceeded"] = LimitExceeded,
        ["tail"] = includeTail ? GetSafeTail(Text) : null,
    };

    private static string GetSafeTail(string text)
    {
        string tail = text.Length <= 4096 ? text : text[^4096..];
        string[] lines = tail.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries);
        return string.Join(Environment.NewLine, lines.Select(line =>
        {
            string trimmed = line.Trim();
            if (trimmed.Contains("cookie", StringComparison.OrdinalIgnoreCase)
                || trimmed.Contains("authorization", StringComparison.OrdinalIgnoreCase)
                || trimmed.Contains("http://", StringComparison.OrdinalIgnoreCase)
                || trimmed.Contains("https://", StringComparison.OrdinalIgnoreCase))
            {
                return "[redacted sensitive-looking output line]";
            }
            return trimmed.Length <= 500 ? trimmed : trimmed[..500];
        }));
    }
}

internal static class TargetProcessLauncher
{
    private const uint RollbackExitCode = 0xD7020002;
    private const uint RollbackWaitMilliseconds = 5000;
    private const string RollbackSelfTestMarker = "injected post-create rollback self-test failure";

    private delegate bool ProcessCreationCall(
        SafeAccessTokenHandle token,
        string applicationName,
        StringBuilder commandLine,
        IntPtr processAttributes,
        IntPtr threadAttributes,
        bool inheritHandles,
        uint creationFlags,
        IntPtr environment,
        string? currentDirectory,
        ref NativeMethods.StartupInfoEx startupInfo,
        out NativeMethods.ProcessInformation processInformation);

    // An allocated empty string is distinct from a NULL lpDesktop pointer: it
    // prevents inheriting the SYSTEM helper's station and lets Windows select
    // the target logon session's station when the process first uses USER32.
    internal const string SystemSelectedDesktop = "";
    internal const string InteractiveDefaultDesktop = @"WinSta0\Default";

    internal static SuspendedLaunch CreateSuspended(
        SafeAccessTokenHandle token,
        IntPtr environment,
        string applicationPath,
        IReadOnlyList<string> arguments,
        string currentDirectory,
        string lpDesktop,
        long? maxOutputBytesPerStream = null)
    {
        return CreateSuspendedCore(token, environment, applicationPath, arguments, currentDirectory,
            lpDesktop, maxOutputBytesPerStream, NativeMethods.CreateProcessAsUser,
            "CreateProcessAsUser", null, null);
    }

    private static SuspendedLaunch CreateSuspendedCore(
        SafeAccessTokenHandle token,
        IntPtr environment,
        string applicationPath,
        IReadOnlyList<string> arguments,
        string currentDirectory,
        string lpDesktop,
        long? maxOutputBytesPerStream,
        ProcessCreationCall createProcess,
        string createProcessApi,
        Action<IntPtr>? afterNativeCreateForSelfTest,
        Action<IntPtr>? afterSafeHandleWrapForSelfTest)
    {
        ProcessOutputCapture.ValidateMaxBytesPerStream(maxOutputBytesPerStream);
        ArgumentNullException.ThrowIfNull(createProcess);
        if (lpDesktop is null || lpDesktop.Contains('\0'))
        {
            throw new ArgumentException("lpDesktop must be a valid string; use an empty string to select the target logon session desktop.", nameof(lpDesktop));
        }
        string fullApplicationPath = Path.GetFullPath(applicationPath);
        if (!File.Exists(fullApplicationPath))
        {
            throw new NativeApiException("CreateProcessAsUser.ApplicationMissing", NativeMethods.ErrorNotFound);
        }
        if (!Directory.Exists(currentDirectory))
        {
            throw new NativeApiException("CreateProcessAsUser.CurrentDirectoryMissing", NativeMethods.ErrorNotFound);
        }

        SafeFileHandle? stdoutRead = null;
        SafeFileHandle? stdoutWrite = null;
        SafeFileHandle? stderrRead = null;
        SafeFileHandle? stderrWrite = null;
        SafeFileHandle? stdin = null;
        ProcessOutputCapture? output = null;
        SafeProcessHandle? processHandle = null;
        SafeThreadHandle? threadHandle = null;
        IntPtr rawProcessHandle = IntPtr.Zero;
        IntPtr rawThreadHandle = IntPtr.Zero;
        IntPtr desktop = IntPtr.Zero;
        IntPtr attributeList = IntPtr.Zero;
        IntPtr handleArray = IntPtr.Zero;
        IntPtr attributeListBytes = IntPtr.Zero;
        bool attributeListInitialized = false;
        SuspendedLaunch? successfulLaunch = null;
        Exception? primaryFailure = null;
        List<Exception> cleanupFailures = [];
        try
        {
            var security = new NativeMethods.SecurityAttributes
            {
                Length = Marshal.SizeOf<NativeMethods.SecurityAttributes>(),
                InheritHandle = true,
            };
            stdoutRead = CreatePipeReadHandle(ref security, out SafeFileHandle createdStdoutWrite);
            stdoutWrite = createdStdoutWrite;
            stderrRead = CreatePipeReadHandle(ref security, out SafeFileHandle createdStderrWrite);
            stderrWrite = createdStderrWrite;
            stdin = NativeMethods.CreateFile("NUL", NativeMethods.GenericRead,
                NativeMethods.FileShareRead | NativeMethods.FileShareWrite, ref security, NativeMethods.OpenExisting,
                NativeMethods.FileAttributeNormal, IntPtr.Zero);
            if (stdin.IsInvalid)
            {
                throw LastError("CreateFile.NUL");
            }

            desktop = Marshal.StringToHGlobalUni(lpDesktop);
            if (!NativeMethods.SetHandleInformation(stdoutRead, NativeMethods.HandleFlagInherit, 0)
                || !NativeMethods.SetHandleInformation(stderrRead, NativeMethods.HandleFlagInherit, 0))
            {
                throw LastError("SetHandleInformation.ParentPipe");
            }
            output = new ProcessOutputCapture(stdoutRead, stderrRead, maxOutputBytesPerStream);
            stdoutRead = null;
            stderrRead = null;

            IntPtr requiredSize = IntPtr.Zero;
            _ = NativeMethods.InitializeProcThreadAttributeList(IntPtr.Zero, 1, 0, ref requiredSize);
            int sizeError = Marshal.GetLastWin32Error();
            if (requiredSize == IntPtr.Zero || sizeError != NativeMethods.ErrorInsufficientBuffer)
            {
                throw new NativeApiException("InitializeProcThreadAttributeList.Size", sizeError);
            }
            attributeListBytes = Marshal.AllocHGlobal(requiredSize);
            attributeList = attributeListBytes;
            if (!NativeMethods.InitializeProcThreadAttributeList(attributeList, 1, 0, ref requiredSize))
            {
                throw LastError("InitializeProcThreadAttributeList");
            }
            attributeListInitialized = true;

            handleArray = Marshal.AllocHGlobal(3 * IntPtr.Size);
            Marshal.WriteIntPtr(handleArray, 0, stdin.DangerousGetHandle());
            Marshal.WriteIntPtr(handleArray, IntPtr.Size, stdoutWrite.DangerousGetHandle());
            Marshal.WriteIntPtr(handleArray, 2 * IntPtr.Size, stderrWrite.DangerousGetHandle());
            if (!NativeMethods.UpdateProcThreadAttribute(attributeList, 0,
                    new IntPtr(NativeMethods.ProcThreadAttributeHandleList), handleArray,
                    new IntPtr(3 * IntPtr.Size), IntPtr.Zero, IntPtr.Zero))
            {
                throw LastError("UpdateProcThreadAttribute.HandleList");
            }

            var startup = new NativeMethods.StartupInfo
            {
                Size = Marshal.SizeOf<NativeMethods.StartupInfoEx>(),
                Desktop = desktop,
                Flags = NativeMethods.StartfUseStdHandles | NativeMethods.StartfUseShowWindow,
                ShowWindow = NativeMethods.SwHide,
                StandardInput = stdin.DangerousGetHandle(),
                StandardOutput = stdoutWrite.DangerousGetHandle(),
                StandardError = stderrWrite.DangerousGetHandle(),
            };
            var startupEx = new NativeMethods.StartupInfoEx { StartupInfo = startup, AttributeList = attributeList };
            var commandArguments = new List<string> { fullApplicationPath };
            commandArguments.AddRange(arguments);
            string commandLineText = string.Join(" ", commandArguments.Select(QuoteArgument));
            var commandLine = new StringBuilder(commandLineText);
            uint flags = NativeMethods.CreateSuspended | NativeMethods.CreateUnicodeEnvironment
                | NativeMethods.CreateNoWindow | NativeMethods.ExtendedStartupInfoPresent;
            if (!createProcess(token, fullApplicationPath, commandLine, IntPtr.Zero,
                    IntPtr.Zero, true, flags, environment, currentDirectory, ref startupEx,
                    out NativeMethods.ProcessInformation processInformation))
            {
                throw LastError(createProcessApi);
            }

            // Retain both raw handles before any managed wrapper allocation or
            // injected post-create work can fail. The catch path can therefore
            // terminate and close the process even if SafeHandle wrapping fails.
            rawProcessHandle = processInformation.Process;
            rawThreadHandle = processInformation.Thread;
            if (rawProcessHandle == IntPtr.Zero || rawThreadHandle == IntPtr.Zero || processInformation.ProcessId == 0)
            {
                throw new InvalidOperationException("CreateProcess returned success with incomplete PROCESS_INFORMATION handles or PID.");
            }
            afterNativeCreateForSelfTest?.Invoke(rawProcessHandle);

            processHandle = new SafeProcessHandle(rawProcessHandle, ownsHandle: true);
            rawProcessHandle = IntPtr.Zero;
            threadHandle = new SafeThreadHandle(rawThreadHandle, ownsHandle: true);
            rawThreadHandle = IntPtr.Zero;
            afterSafeHandleWrapForSelfTest?.Invoke(processHandle.DangerousGetHandle());

            stdoutWrite.Dispose();
            stdoutWrite = null;
            stderrWrite.Dispose();
            stderrWrite = null;
            stdin.Dispose();
            stdin = null;
            var suspended = new SuspendedLeaseProcess(processHandle, threadHandle, processInformation.ProcessId);
            successfulLaunch = new SuspendedLaunch(suspended, output);
        }
        catch (Exception exception)
        {
            primaryFailure = exception;
        }
        finally
        {
            // Capture each cleanup error and continue. In particular, an
            // attribute-list cleanup failure must not bypass suspended-process
            // rollback below.
            if (attributeListInitialized)
                TryCleanup(NativeMethods.DeleteProcThreadAttributeList, attributeList, cleanupFailures,
                    "DeleteProcThreadAttributeList");
            if (attributeListBytes != IntPtr.Zero)
                TryCleanup(Marshal.FreeHGlobal, attributeListBytes, cleanupFailures, "FreeProcThreadAttributeList");
            if (handleArray != IntPtr.Zero)
                TryCleanup(Marshal.FreeHGlobal, handleArray, cleanupFailures, "FreeHandleList");
            if (desktop != IntPtr.Zero)
                TryCleanup(Marshal.FreeHGlobal, desktop, cleanupFailures, "FreeDesktopString");
        }

        if (primaryFailure is null && cleanupFailures.Count == 0 && successfulLaunch is not null)
        {
            return successfulLaunch;
        }

        if (rawProcessHandle != IntPtr.Zero || rawThreadHandle != IntPtr.Zero
            || processHandle is not null || threadHandle is not null)
        {
            cleanupFailures.AddRange(TerminateAndReleaseCreatedProcess(
                rawProcessHandle, rawThreadHandle, processHandle, threadHandle));
            rawProcessHandle = IntPtr.Zero;
            rawThreadHandle = IntPtr.Zero;
            processHandle = null;
            threadHandle = null;
        }

        if (output is not null)
        {
            TryCleanup(() => output.DisposeAsync().AsTask().GetAwaiter().GetResult(),
                cleanupFailures, "DisposeOutputCapture");
            output = null;
            stdoutRead = null;
            stderrRead = null;
        }
        TryDispose(stdoutRead, cleanupFailures, "DisposeStdoutRead");
        TryDispose(stderrRead, cleanupFailures, "DisposeStderrRead");
        TryDispose(stdoutWrite, cleanupFailures, "DisposeStdoutWrite");
        TryDispose(stderrWrite, cleanupFailures, "DisposeStderrWrite");
        TryDispose(stdin, cleanupFailures, "DisposeStdin");

        if (primaryFailure is not null)
        {
            if (cleanupFailures.Count == 0)
            {
                System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(primaryFailure).Throw();
            }
            cleanupFailures.Insert(0, primaryFailure);
            throw new AggregateException("CreateProcessAsUser launch failed and one or more rollback/cleanup actions also failed.", cleanupFailures);
        }
        if (cleanupFailures.Count > 0)
        {
            throw new AggregateException("CreateProcessAsUser cleanup failed before ownership could be transferred to the job.", cleanupFailures);
        }
        throw new InvalidOperationException("The suspended process launcher produced no result and no recorded failure.");
    }

    internal static void ValidatePostCreateRollbackSelfTest()
    {
        if (!NativeMethods.OpenProcessToken(NativeMethods.GetCurrentProcess(), NativeMethods.TokenQuery,
                out SafeAccessTokenHandle token))
        {
            throw LastError("OpenProcessToken.RollbackSelfTest");
        }

        using (token)
        {
            string applicationPath = Environment.ProcessPath
                ?? throw new InvalidOperationException("The rollback self-test cannot resolve the current executable path.");
            applicationPath = Path.GetFullPath(applicationPath);
            string currentDirectory = Path.GetDirectoryName(applicationPath)
                ?? throw new InvalidOperationException("The rollback self-test executable has no parent directory.");

            ValidateInjectedRollbackCase(token, applicationPath, currentDirectory, failAfterSafeHandleWrap: false);
            ValidateInjectedRollbackCase(token, applicationPath, currentDirectory, failAfterSafeHandleWrap: true);
        }
    }

    private static void ValidateInjectedRollbackCase(
        SafeAccessTokenHandle token,
        string applicationPath,
        string currentDirectory,
        bool failAfterSafeHandleWrap)
    {
        SafeNativeHandle? independentProcess = null;
        void DuplicateAndInject(IntPtr processHandle)
        {
            if (!NativeMethods.DuplicateHandle(NativeMethods.GetCurrentProcess(), processHandle,
                    NativeMethods.GetCurrentProcess(), out SafeNativeHandle duplicate,
                    0, false, NativeMethods.DuplicateSameAccess))
            {
                throw LastError("DuplicateHandle.RollbackSelfTest");
            }
            independentProcess = duplicate;
            throw new InvalidOperationException(RollbackSelfTestMarker);
        }

        SuspendedLaunch? unexpectedLaunch = null;
        Exception? observedFailure = null;
        try
        {
            unexpectedLaunch = CreateSuspendedCore(token, IntPtr.Zero, applicationPath, [], currentDirectory,
                SystemSelectedDesktop, null,
                CreateProcessCurrentTokenForSelfTest,
                "CreateProcessW.RollbackSelfTest",
                failAfterSafeHandleWrap ? null : DuplicateAndInject,
                failAfterSafeHandleWrap ? DuplicateAndInject : null);
        }
        catch (Exception exception)
        {
            observedFailure = exception;
        }

        var cleanupErrors = new List<Exception>();
        if (unexpectedLaunch is not null)
        {
            cleanupErrors.AddRange(TerminateAndReleaseCreatedProcess(IntPtr.Zero, IntPtr.Zero,
                unexpectedLaunch.Process.ProcessHandle, unexpectedLaunch.Process.PrimaryThreadHandle));
            TryCleanup(() => unexpectedLaunch.Output.DisposeAsync().AsTask().GetAwaiter().GetResult(),
                cleanupErrors, "DisposeUnexpectedSelfTestLaunchOutput");
        }
        if (independentProcess is not null)
        {
            try
            {
                uint wait = WaitForSingleObjectRaw(independentProcess.DangerousGetHandle(), 0);
                if (wait != NativeMethods.WaitObject0)
                {
                    int error = wait == NativeMethods.WaitTimeout ? 0 : Marshal.GetLastWin32Error();
                    cleanupErrors.Add(new InvalidOperationException(
                        $"The injected suspended process was not signaled after rollback (wait={wait}, error={error})."));
                }
            }
            catch (Exception exception)
            {
                cleanupErrors.Add(new InvalidOperationException("WaitForSingleObject.RollbackSelfTest", exception));
            }
            TryDispose(independentProcess, cleanupErrors, "DisposeIndependentRollbackSelfTestHandle");
        }
        else
        {
            cleanupErrors.Add(new InvalidOperationException("Rollback self-test did not retain an independent process synchronization handle."));
        }

        if (cleanupErrors.Count > 0)
        {
            if (observedFailure is not null) cleanupErrors.Insert(0, observedFailure);
            throw new AggregateException("Post-create rollback self-test cleanup failed.", cleanupErrors);
        }
        if (observedFailure is null || !ContainsInjectedFailure(observedFailure))
        {
            throw new InvalidOperationException("The injected post-create failure did not abort the launcher.", observedFailure);
        }
        if (observedFailure is AggregateException aggregate && aggregate.Flatten().InnerExceptions.Count > 1)
        {
            throw new InvalidOperationException("Rollback self-test observed one or more production cleanup failures.", aggregate);
        }
    }

    private static bool ContainsInjectedFailure(Exception exception)
    {
        if (exception is InvalidOperationException invalid
            && invalid.Message == RollbackSelfTestMarker)
        {
            return true;
        }
        return exception is AggregateException aggregate
            && aggregate.Flatten().InnerExceptions.Any(ContainsInjectedFailure);
    }

    private static List<Exception> TerminateAndReleaseCreatedProcess(
        IntPtr rawProcessHandle,
        IntPtr rawThreadHandle,
        SafeProcessHandle? processHandle,
        SafeThreadHandle? threadHandle)
    {
        var errors = new List<Exception>();
        IntPtr process = processHandle is { IsInvalid: false, IsClosed: false }
            ? processHandle.DangerousGetHandle()
            : rawProcessHandle;

        if (process == IntPtr.Zero || process == new IntPtr(-1))
        {
            errors.Add(new InvalidOperationException("A process was created but no usable process handle remained for rollback."));
        }
        else
        {
            bool terminateRequested = false;
            int terminateError = 0;
            Exception? terminateFailure = null;
            try
            {
                terminateRequested = TerminateProcessRaw(process, RollbackExitCode);
                if (!terminateRequested)
                {
                    terminateError = Marshal.GetLastWin32Error();
                    terminateFailure = new NativeApiException("TerminateProcess.PostCreateRollback", terminateError);
                }
            }
            catch (Exception exception)
            {
                terminateFailure = new InvalidOperationException("TerminateProcess.PostCreateRollback threw before the suspended process was known to be stopped.", exception);
            }

            uint wait = uint.MaxValue;
            Exception? waitFailure = null;
            try
            {
                wait = WaitForSingleObjectRaw(process, RollbackWaitMilliseconds);
                if (wait == uint.MaxValue)
                {
                    waitFailure = new NativeApiException("WaitForSingleObject.PostCreateRollback", Marshal.GetLastWin32Error());
                }
            }
            catch (Exception exception)
            {
                waitFailure = new InvalidOperationException("WaitForSingleObject.PostCreateRollback threw.", exception);
            }

            if (wait != NativeMethods.WaitObject0)
            {
                if (terminateFailure is not null) errors.Add(terminateFailure);
                errors.Add(wait == NativeMethods.WaitTimeout
                    ? new TimeoutException($"The newly created suspended process did not signal within the {RollbackWaitMilliseconds} ms rollback bound.")
                    : waitFailure ?? new NativeApiException("WaitForSingleObject.PostCreateRollback", Marshal.GetLastWin32Error()));
            }
        }

        try
        {
            ReleaseProcessHandle(rawProcessHandle, processHandle, errors);
        }
        catch (Exception exception)
        {
            errors.Add(new InvalidOperationException("Process-handle release threw during post-create rollback.", exception));
            TryDispose(processHandle, errors, "DisposeProcessHandleAfterReleaseFailure");
            if (processHandle is null && rawProcessHandle != IntPtr.Zero && rawProcessHandle != new IntPtr(-1))
            {
                TryCloseRawHandle(rawProcessHandle, errors, "CloseHandle.PostCreateRollback.ProcessRawAfterReleaseFailure");
            }
        }
        try
        {
            ReleaseThreadHandle(rawThreadHandle, threadHandle, errors);
        }
        catch (Exception exception)
        {
            errors.Add(new InvalidOperationException("Thread-handle release threw during post-create rollback.", exception));
            TryDispose(threadHandle, errors, "DisposeThreadHandleAfterReleaseFailure");
            if (threadHandle is null && rawThreadHandle != IntPtr.Zero && rawThreadHandle != new IntPtr(-1))
            {
                TryCloseRawHandle(rawThreadHandle, errors, "CloseHandle.PostCreateRollback.ThreadRawAfterReleaseFailure");
            }
        }
        return errors;
    }

    private static void ReleaseProcessHandle(IntPtr rawHandle, SafeProcessHandle? safeHandle, List<Exception> errors)
    {
        if (safeHandle is { IsInvalid: false, IsClosed: false })
        {
            CloseSafeHandle(safeHandle, "CloseHandle.PostCreateRollback.Process", errors);
        }
        else if (rawHandle != IntPtr.Zero && rawHandle != new IntPtr(-1))
        {
            TryCloseRawHandle(rawHandle, errors, "CloseHandle.PostCreateRollback.ProcessRaw");
        }
        else
        {
            TryDispose(safeHandle, errors, "DisposeProcessHandle");
        }
    }

    private static void ReleaseThreadHandle(IntPtr rawHandle, SafeThreadHandle? safeHandle, List<Exception> errors)
    {
        if (safeHandle is { IsInvalid: false, IsClosed: false })
        {
            CloseSafeHandle(safeHandle, "CloseHandle.PostCreateRollback.Thread", errors);
        }
        else if (rawHandle != IntPtr.Zero && rawHandle != new IntPtr(-1))
        {
            TryCloseRawHandle(rawHandle, errors, "CloseHandle.PostCreateRollback.ThreadRaw");
        }
        else
        {
            TryDispose(safeHandle, errors, "DisposeThreadHandle");
        }
    }

    private static void CloseSafeHandle(SafeHandle handle, string api, List<Exception> errors)
    {
        bool closed = false;
        try
        {
            IntPtr raw = handle.DangerousGetHandle();
            closed = NativeMethods.CloseHandle(raw);
            if (!closed) errors.Add(new NativeApiException(api, Marshal.GetLastWin32Error()));
        }
        catch (Exception exception)
        {
            errors.Add(new InvalidOperationException(api + " threw.", exception));
        }
        if (closed)
        {
            try
            {
                handle.SetHandleAsInvalid();
            }
            catch (Exception exception)
            {
                errors.Add(new InvalidOperationException("SetHandleAsInvalid." + api + " threw after the native handle was closed.", exception));
            }
        }
        TryDispose(handle, errors, "Dispose" + api);
    }

    private static void TryCloseRawHandle(IntPtr rawHandle, List<Exception> errors, string api)
    {
        try
        {
            if (!NativeMethods.CloseHandle(rawHandle)) errors.Add(LastError(api));
        }
        catch (Exception exception)
        {
            errors.Add(new InvalidOperationException(api + " threw.", exception));
        }
    }

    private static void TryDispose(IDisposable? disposable, List<Exception> errors, string operation)
    {
        if (disposable is null) return;
        try { disposable.Dispose(); }
        catch (Exception exception) { errors.Add(new InvalidOperationException(operation, exception)); }
    }

    private static void TryCleanup(Action<IntPtr> cleanup, IntPtr value, List<Exception> errors, string operation)
    {
        try { cleanup(value); }
        catch (Exception exception) { errors.Add(new InvalidOperationException(operation, exception)); }
    }

    private static void TryCleanup(Action cleanup, List<Exception> errors, string operation)
    {
        try { cleanup(); }
        catch (Exception exception) { errors.Add(new InvalidOperationException(operation, exception)); }
    }

    private static bool CreateProcessCurrentTokenForSelfTest(
        SafeAccessTokenHandle ignoredToken,
        string applicationName,
        StringBuilder commandLine,
        IntPtr processAttributes,
        IntPtr threadAttributes,
        bool inheritHandles,
        uint creationFlags,
        IntPtr environment,
        string? currentDirectory,
        ref NativeMethods.StartupInfoEx startupInfo,
        out NativeMethods.ProcessInformation processInformation)
    {
        return CreateProcessW(applicationName, commandLine, processAttributes, threadAttributes,
            inheritHandles, creationFlags, environment, currentDirectory, ref startupInfo,
            out processInformation);
    }

    [DllImport("kernel32.dll", EntryPoint = "CreateProcessW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CreateProcessW(
        string applicationName,
        StringBuilder commandLine,
        IntPtr processAttributes,
        IntPtr threadAttributes,
        [MarshalAs(UnmanagedType.Bool)] bool inheritHandles,
        uint creationFlags,
        IntPtr environment,
        string? currentDirectory,
        ref NativeMethods.StartupInfoEx startupInfo,
        out NativeMethods.ProcessInformation processInformation);

    [DllImport("kernel32.dll", EntryPoint = "TerminateProcess", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool TerminateProcessRaw(IntPtr process, uint exitCode);

    [DllImport("kernel32.dll", EntryPoint = "WaitForSingleObject", SetLastError = true)]
    private static extern uint WaitForSingleObjectRaw(IntPtr handle, uint milliseconds);

    internal static string QuoteArgument(string value)
    {
        if (value.Length > 0 && !value.Any(char.IsWhiteSpace) && !value.Contains('"'))
        {
            return value;
        }
        var builder = new StringBuilder(value.Length + 2);
        builder.Append('"');
        int backslashes = 0;
        foreach (char character in value)
        {
            if (character == '\\')
            {
                backslashes++;
                continue;
            }
            if (character == '"')
            {
                builder.Append('\\', backslashes * 2 + 1);
                builder.Append('"');
                backslashes = 0;
                continue;
            }
            builder.Append('\\', backslashes);
            backslashes = 0;
            builder.Append(character);
        }
        builder.Append('\\', backslashes * 2);
        builder.Append('"');
        return builder.ToString();
    }

    private static SafeFileHandle CreatePipeReadHandle(ref NativeMethods.SecurityAttributes security, out SafeFileHandle write)
    {
        if (!NativeMethods.CreatePipe(out SafeFileHandle read, out write, ref security, 0))
        {
            throw LastError("CreatePipe");
        }
        return read;
    }

    private static NativeApiException LastError(string api) => new(api, Marshal.GetLastWin32Error());
}
