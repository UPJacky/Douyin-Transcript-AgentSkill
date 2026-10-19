using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace DouyinTranscript.CapturePipe;

internal static class LeaseProcessJobHarness
{
    private const uint CreateSuspended = 0x00000004;
    private const uint CreateNoWindow = 0x08000000;
    private const uint ProcessSynchronize = 0x00100000;
    private const uint ProcessQueryLimitedInformation = 0x00001000;
    private const uint ProcessExitVerificationAccess = ProcessSynchronize | ProcessQueryLimitedInformation;
    private const string FixtureDirectoryPrefix = "douyin-lease-job-";
    private const string FixtureOwnerFileName = ".lease-job-fixture-owner";
    private const int ProcessObservationWindowMilliseconds = 100;

    internal static async Task RunAsync()
    {
        RunFakeApiCases();
        await RunRealProcessTreeScenarioAsync("observation-timeout", injectException: false).ConfigureAwait(false);
        await RunRealProcessTreeScenarioAsync("exception-cleanup", injectException: true).ConfigureAwait(false);
        await RunAbruptOwnerTerminationScenarioAsync().ConfigureAwait(false);
        Console.WriteLine("PASS lease process job: fake API paths and real parent/child timeout, exception, and owner-termination cleanup");
    }

    internal static async Task<int> RunFixtureRootAsync(string markerPath)
    {
        try
        {
            string fullMarkerPath = Path.GetFullPath(markerPath);
            string? markerDirectory = Path.GetDirectoryName(fullMarkerPath);
            if (string.IsNullOrWhiteSpace(markerDirectory))
            {
                throw new ArgumentException("The process-tree marker needs a parent directory.", nameof(markerPath));
            }

            ProcessStartInfo childStart = CreateSelfStartInfo("--lease-job-fixture-leaf");
            using Process child = Process.Start(childStart)
                ?? throw new InvalidOperationException("The lease process fixture could not start its child.");
            Directory.CreateDirectory(markerDirectory);
            string temporaryMarker = Path.Combine(markerDirectory, $"{Guid.NewGuid():N}.tmp");
            await File.WriteAllTextAsync(
                temporaryMarker,
                $"{Environment.ProcessId}\n{child.Id}\n",
                new UTF8Encoding(encoderShouldEmitUTF8Identifier: false)).ConfigureAwait(false);
            File.Move(temporaryMarker, fullMarkerPath, overwrite: false);
            await Task.Delay(Timeout.InfiniteTimeSpan).ConfigureAwait(false);
            return 0;
        }
        catch (TaskCanceledException)
        {
            return 0;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine($"Lease process fixture failed: {exception.GetType().Name}");
            return 1;
        }
    }

    internal static int RunFixtureLeaf()
    {
        Thread.Sleep(Timeout.Infinite);
        return 0;
    }

    internal static async Task<int> RunFixtureSupervisorAsync(string processTreeMarkerPath, string supervisorReadyMarkerPath)
    {
        LeaseProcessJob? job = null;
        try
        {
            string fullTreeMarkerPath = Path.GetFullPath(processTreeMarkerPath);
            string fullReadyMarkerPath = Path.GetFullPath(supervisorReadyMarkerPath);
            if (string.Equals(fullTreeMarkerPath, fullReadyMarkerPath, StringComparison.OrdinalIgnoreCase))
            {
                throw new ArgumentException("The process-tree and supervisor markers must use separate files.");
            }

            job = LeaseProcessJob.Start(() => CreateSuspendedFixtureProcess(fullTreeMarkerPath));
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
            while (!File.Exists(fullTreeMarkerPath))
            {
                timeout.Token.ThrowIfCancellationRequested();
                await Task.Delay(20, timeout.Token).ConfigureAwait(false);
            }

            string[] processIds = await File.ReadAllLinesAsync(fullTreeMarkerPath, timeout.Token).ConfigureAwait(false);
            if (processIds.Length != 2
                || !uint.TryParse(processIds[0], out uint rootPid)
                || !uint.TryParse(processIds[1], out uint childPid)
                || rootPid != job.RootProcessId
                || childPid == 0
                || childPid == rootPid)
            {
                throw new InvalidDataException("The supervised process-tree marker did not match the started Job root and child.");
            }

            string markerDirectory = Path.GetDirectoryName(fullReadyMarkerPath)
                ?? throw new ArgumentException("The supervisor-ready marker needs a parent directory.");
            Directory.CreateDirectory(markerDirectory);
            string temporaryMarkerPath = Path.Combine(markerDirectory, $"{Guid.NewGuid():N}.tmp");
            try
            {
                await File.WriteAllTextAsync(
                    temporaryMarkerPath,
                    $"{Environment.ProcessId}\n{rootPid}\n{childPid}\n",
                    new UTF8Encoding(encoderShouldEmitUTF8Identifier: false),
                    timeout.Token).ConfigureAwait(false);
                File.Move(temporaryMarkerPath, fullReadyMarkerPath, overwrite: false);
            }
            finally
            {
                try { File.Delete(temporaryMarkerPath); }
                catch (IOException) { }
                catch (UnauthorizedAccessException) { }
            }

            await Task.Delay(Timeout.InfiniteTimeSpan).ConfigureAwait(false);
            return 0;
        }
        catch (TaskCanceledException)
        {
            Console.Error.WriteLine("Lease process supervisor fixture timed out before becoming ready.");
            return 1;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine($"Lease process supervisor fixture failed: {exception.GetType().Name}");
            return 1;
        }
        finally
        {
            // The abrupt-termination test intentionally bypasses this path. It
            // verifies that process-handle closure alone enforces kill-on-close.
            job?.Dispose();
        }
    }

    private static void RunFakeApiCases()
    {
        var successfulNative = new FakeNative();
        LeaseProcessJob successfulJob = LeaseProcessJob.Start(
            successfulNative.CreateSuspendedProcess,
            successfulNative);
        Assert(successfulNative.Events.SequenceEqual(
                ["create-job", "set-limits", "query-limits", "create-suspended", "assign", "resume"]),
            "the root process was not created, assigned, and resumed in the required order");
        Assert(successfulNative.ConfiguredFlags == LeaseProcessJob.KillOnJobClose,
            "the fixture job did not use kill-on-close alone");
        Assert(successfulJob.RootProcessId == 42 && successfulJob.IsProcessInJob(successfulNative.ProcessHandle),
            "the fake root process was not retained as the job root");
        successfulJob.Dispose();
        successfulJob.Dispose();
        Assert(successfulNative.Events.Contains("terminate-job") && successfulNative.JobHandle.IsClosed,
            "disposing the running lease job did not terminate and close it");
        Assert(successfulNative.ProcessHandle.IsClosed && successfulNative.ThreadHandle.IsClosed,
            "disposing the lease job did not release the suspended-process handles");

        var invalidFlagsNative = new FakeNative
        {
            ConfiguredFlags = LeaseProcessJob.KillOnJobClose | LeaseProcessJob.BreakawayOk,
        };
        bool launcherCalled = false;
        ExpectThrows<InvalidOperationException>(() => LeaseProcessJob.Start(() =>
        {
            launcherCalled = true;
            return invalidFlagsNative.CreateSuspendedProcess();
        }, invalidFlagsNative));
        Assert(!launcherCalled && invalidFlagsNative.JobHandle.IsClosed,
            "an invalid breakaway configuration did not fail before launching the process");

        var assignFailureNative = new FakeNative { AssignError = new InvalidOperationException("fixture assign failure") };
        ExpectThrows<InvalidOperationException>(() => LeaseProcessJob.Start(
            assignFailureNative.CreateSuspendedProcess,
            assignFailureNative));
        Assert(assignFailureNative.Events.Contains("terminate-process")
               && assignFailureNative.Events.Contains("wait-process")
               && assignFailureNative.JobHandle.IsClosed
               && assignFailureNative.ProcessHandle.IsClosed,
            "assign failure did not stop and dispose the unassigned suspended process");

        var resumeFailureNative = new FakeNative { ResumeCount = 0 };
        ExpectThrows<InvalidOperationException>(() => LeaseProcessJob.Start(
            resumeFailureNative.CreateSuspendedProcess,
            resumeFailureNative));
        Assert(resumeFailureNative.Events.Contains("terminate-job")
               && resumeFailureNative.Events.Contains("wait-job-drain")
               && resumeFailureNative.JobHandle.IsClosed
               && resumeFailureNative.ProcessHandle.IsClosed,
            "resume failure did not terminate and drain the assigned process");
    }

    private static async Task RunRealProcessTreeScenarioAsync(string scenario, bool injectException)
    {
        (string fixtureDirectory, string fixtureRoot, string ownerToken) = CreateOwnedFixtureDirectory();
        string markerPath = Path.Combine(fixtureDirectory, "process-tree.txt");
        LeaseProcessJob? job = null;
        SafeProcessHandle? rootHandle = null;
        SafeProcessHandle? childHandle = null;
        uint rootPid = 0;
        uint childPid = 0;
        bool injectedExceptionObserved = false;
        bool jobCleanupCompleted = false;
        try
        {
            try
            {
                job = LeaseProcessJob.Start(() => CreateSuspendedFixtureProcess(markerPath));
                using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
                while (!File.Exists(markerPath))
                {
                    timeout.Token.ThrowIfCancellationRequested();
                    await Task.Delay(20, timeout.Token).ConfigureAwait(false);
                }

                string[] pids = await File.ReadAllLinesAsync(markerPath, timeout.Token).ConfigureAwait(false);
                Assert(pids.Length == 2, "the helper process did not write both process ids");
                Assert(uint.TryParse(pids[0], out rootPid), "the helper root pid was invalid");
                Assert(uint.TryParse(pids[1], out childPid), "the helper child pid was invalid");
                Assert(rootPid == job.RootProcessId, "the suspended root pid did not match the job root");
                rootHandle = LeaseProcessJobHarnessNativeMethods.OpenProcess(
                    ProcessExitVerificationAccess,
                    inheritHandle: false,
                    rootPid);
                Assert(!rootHandle.IsInvalid, "the helper root process could not be opened for exit verification");
                childHandle = LeaseProcessJobHarnessNativeMethods.OpenProcess(
                    ProcessExitVerificationAccess,
                    inheritHandle: false,
                    childPid);
                Assert(!childHandle.IsInvalid, "the helper child process could not be opened for job verification");
                Assert(job.IsProcessInJob(job.RootProcessHandle), "the root process was not assigned to its job");
                Assert(job.IsProcessInJob(childHandle), "the child process escaped its parent job");

                if (injectException)
                {
                    throw new FixtureScenarioException("injected after the real process tree was observed in its job");
                }

                uint rootObservation = LeaseProcessJobHarnessNativeMethods.WaitForSingleObject(
                    rootHandle,
                    ProcessObservationWindowMilliseconds);
                uint childObservation = LeaseProcessJobHarnessNativeMethods.WaitForSingleObject(
                    childHandle,
                    ProcessObservationWindowMilliseconds);
                Assert(rootObservation == LeaseProcessJobHarnessNativeMethods.WaitTimeout,
                    $"the root process did not remain alive through the bounded observation window (wait=0x{rootObservation:X8})");
                Assert(childObservation == LeaseProcessJobHarnessNativeMethods.WaitTimeout,
                    $"the child process did not remain alive through the bounded observation window (wait=0x{childObservation:X8})");
            }
            catch (FixtureScenarioException) when (injectException)
            {
                injectedExceptionObserved = true;
            }
            finally
            {
                if (job is not null)
                {
                    await job.StopAndWaitAsync(TimeSpan.FromSeconds(10)).ConfigureAwait(false);
                    jobCleanupCompleted = true;
                }
            }

            if (injectException)
            {
                Assert(injectedExceptionObserved, "the fixture exception was not observed after the process tree started");
            }

            Assert(rootHandle is not null && !rootHandle.IsInvalid, "the root exit-verification handle was not retained through cleanup");
            Assert(childHandle is not null && !childHandle.IsInvalid, "the child exit-verification handle was not retained through cleanup");
            uint rootWait = LeaseProcessJobHarnessNativeMethods.WaitForSingleObject(rootHandle!, 5000);
            uint childWait = LeaseProcessJobHarnessNativeMethods.WaitForSingleObject(childHandle!, 5000);
            Assert(rootWait == LeaseProcessJobHarnessNativeMethods.WaitObject0,
                $"the root process did not signal exit after {scenario} cleanup (wait=0x{rootWait:X8})");
            Assert(childWait == LeaseProcessJobHarnessNativeMethods.WaitObject0,
                $"the child process did not signal exit after {scenario} cleanup (wait=0x{childWait:X8})");
            Console.WriteLine(
                $"PASS lease process job {scenario}: root pid={rootPid} exit=signaled; child pid={childPid} exit=signaled");
        }
        finally
        {
            if (job is null)
            {
                jobCleanupCompleted = true;
            }
            else if (!jobCleanupCompleted)
            {
                await job.DisposeAsync().ConfigureAwait(false);
                jobCleanupCompleted = true;
            }
            bool rootExited = rootHandle is null
                || LeaseProcessJobHarnessNativeMethods.WaitForSingleObject(rootHandle, 5000)
                    == LeaseProcessJobHarnessNativeMethods.WaitObject0;
            bool childExited = childHandle is null
                || LeaseProcessJobHarnessNativeMethods.WaitForSingleObject(childHandle, 5000)
                    == LeaseProcessJobHarnessNativeMethods.WaitObject0;
            rootHandle?.Dispose();
            childHandle?.Dispose();
            if (jobCleanupCompleted && rootExited && childExited)
            {
                DeleteOwnedFixtureDirectory(fixtureDirectory, fixtureRoot, ownerToken);
            }
        }
    }

    private static async Task RunAbruptOwnerTerminationScenarioAsync()
    {
        (string fixtureDirectory, string fixtureRoot, string ownerToken) = CreateOwnedFixtureDirectory();
        string processTreeMarkerPath = Path.Combine(fixtureDirectory, "process-tree.txt");
        string supervisorReadyMarkerPath = Path.Combine(fixtureDirectory, "supervisor-ready.txt");
        Process? supervisor = null;
        SafeProcessHandle? rootHandle = null;
        SafeProcessHandle? childHandle = null;
        uint rootPid = 0;
        uint childPid = 0;
        bool supervisorStopped = false;
        bool processTreeStopped = false;

        try
        {
            supervisor = Process.Start(CreateSelfStartInfo(
                    "--lease-job-fixture-supervisor",
                    processTreeMarkerPath,
                    supervisorReadyMarkerPath))
                ?? throw new InvalidOperationException("The lease process supervisor fixture could not start.");

            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(20));
            while (!File.Exists(supervisorReadyMarkerPath))
            {
                timeout.Token.ThrowIfCancellationRequested();
                if (supervisor.HasExited)
                {
                    throw new InvalidOperationException(
                        $"The lease process supervisor exited before readiness (exit={supervisor.ExitCode}).");
                }
                await Task.Delay(20, timeout.Token).ConfigureAwait(false);
            }

            string[] readyLines = await File.ReadAllLinesAsync(supervisorReadyMarkerPath, timeout.Token).ConfigureAwait(false);
            Assert(readyLines.Length == 3, "the supervisor-ready marker did not contain exactly three process ids");
            Assert(uint.TryParse(readyLines[0], out uint ownerPid), "the supervisor pid in the ready marker was invalid");
            Assert(uint.TryParse(readyLines[1], out rootPid) && rootPid != 0, "the root pid in the ready marker was invalid");
            Assert(uint.TryParse(readyLines[2], out childPid) && childPid != 0, "the child pid in the ready marker was invalid");
            Assert(ownerPid == (uint)supervisor.Id, "the ready marker owner pid did not match the launched supervisor");
            Assert(rootPid != childPid, "the ready marker root and child pids were equal");

            string[] treeLines = await File.ReadAllLinesAsync(processTreeMarkerPath, timeout.Token).ConfigureAwait(false);
            Assert(treeLines.Length == 2, "the process-tree marker did not contain exactly two process ids");
            Assert(uint.TryParse(treeLines[0], out uint markedRootPid) && markedRootPid == rootPid,
                "the process-tree root pid did not match the supervisor-ready marker");
            Assert(uint.TryParse(treeLines[1], out uint markedChildPid) && markedChildPid == childPid,
                "the process-tree child pid did not match the supervisor-ready marker");

            rootHandle = OpenProcessForExitVerification(rootPid);
            childHandle = OpenProcessForExitVerification(childPid);
            Assert(WaitForProcess(rootHandle, 0) == LeaseProcessJobHarnessNativeMethods.WaitTimeout,
                "the root process was not alive immediately before forced supervisor termination");
            Assert(WaitForProcess(childHandle, 0) == LeaseProcessJobHarnessNativeMethods.WaitTimeout,
                "the child process was not alive immediately before forced supervisor termination");
            Assert(!supervisor.HasExited, "the supervisor exited before the forced termination check");

            // Kill only the Job owner. The root and child remain alive unless
            // closing the owner's last Job handles enforces KILL_ON_JOB_CLOSE.
            supervisor.Kill(entireProcessTree: false);
            Assert(supervisor.WaitForExit(5000), "the forced-termination request did not stop the supervisor");
            supervisorStopped = true;

            uint rootWait = WaitForProcess(rootHandle, 5000);
            uint childWait = WaitForProcess(childHandle, 5000);
            Assert(rootWait == LeaseProcessJobHarnessNativeMethods.WaitObject0,
                $"the Job root did not exit after owner termination (wait=0x{rootWait:X8})");
            Assert(childWait == LeaseProcessJobHarnessNativeMethods.WaitObject0,
                $"the Job child did not exit after owner termination (wait=0x{childWait:X8})");
            processTreeStopped = true;
            Console.WriteLine(
                $"PASS lease process job abrupt owner termination: supervisor pid={ownerPid} stopped; root pid={rootPid} and child pid={childPid} signaled");
        }
        finally
        {
            if (supervisor is null)
            {
                supervisorStopped = true;
                processTreeStopped = true;
            }
            else
            {
                if (!supervisor.HasExited)
                {
                    // Retain the direct process handles before killing the
                    // owner. Never reopen by PID after termination, when a
                    // quickly reused PID could point at an unrelated process.
                    if (rootHandle is null && rootPid != 0)
                    {
                        rootHandle = OpenProcessForExitVerification(rootPid);
                    }
                    if (childHandle is null && childPid != 0)
                    {
                        childHandle = OpenProcessForExitVerification(childPid);
                    }

                    supervisor.Kill(entireProcessTree: false);
                    supervisorStopped = supervisor.WaitForExit(5000);
                }
                else
                {
                    supervisorStopped = true;
                }

                if (supervisorStopped && rootHandle is not null && childHandle is not null)
                {
                    bool rootExited = WaitForProcess(rootHandle, 5000) == LeaseProcessJobHarnessNativeMethods.WaitObject0;
                    bool childExited = WaitForProcess(childHandle, 5000) == LeaseProcessJobHarnessNativeMethods.WaitObject0;
                    processTreeStopped = processTreeStopped || (rootExited && childExited);
                }
            }

            rootHandle?.Dispose();
            childHandle?.Dispose();
            supervisor?.Dispose();
            if (supervisorStopped && processTreeStopped)
            {
                DeleteOwnedFixtureDirectory(fixtureDirectory, fixtureRoot, ownerToken);
            }
        }
    }

    private static SafeProcessHandle OpenProcessForExitVerification(uint processId)
    {
        SafeProcessHandle process = LeaseProcessJobHarnessNativeMethods.OpenProcess(
            ProcessExitVerificationAccess,
            inheritHandle: false,
            processId);
        if (!process.IsInvalid)
        {
            return process;
        }

        int error = Marshal.GetLastWin32Error();
        process.Dispose();
        throw new System.ComponentModel.Win32Exception(error, "Could not open a fixture process for exit verification.");
    }

    private static uint WaitForProcess(SafeProcessHandle process, uint milliseconds) =>
        LeaseProcessJobHarnessNativeMethods.WaitForSingleObject(process, milliseconds);

    private static (string Path, string Root, string OwnerToken) CreateOwnedFixtureDirectory()
    {
        string fixtureRoot = Path.GetFullPath(Path.GetTempPath()).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        string ownerToken = Guid.NewGuid().ToString("N");
        string fixtureDirectory = Path.Combine(fixtureRoot, FixtureDirectoryPrefix + ownerToken);
        if (!LeaseProcessJobHarnessNativeMethods.CreateDirectoryW(fixtureDirectory, IntPtr.Zero))
        {
            throw new System.ComponentModel.Win32Exception(
                Marshal.GetLastWin32Error(),
                "Could not exclusively create the lease process fixture directory.");
        }

        try
        {
            string ownerPath = Path.Combine(fixtureDirectory, FixtureOwnerFileName);
            using var ownerFile = new FileStream(ownerPath, FileMode.CreateNew, FileAccess.Write, FileShare.None);
            byte[] ownerBytes = Encoding.ASCII.GetBytes(ownerToken);
            ownerFile.Write(ownerBytes);
            ownerFile.Flush(flushToDisk: true);
        }
        catch
        {
            DeleteOwnedFixtureDirectory(fixtureDirectory, fixtureRoot, ownerToken, allowMissingOwnerFile: true);
            throw;
        }

        return (fixtureDirectory, fixtureRoot, ownerToken);
    }

    private static void DeleteOwnedFixtureDirectory(
        string fixtureDirectory,
        string fixtureRoot,
        string ownerToken,
        bool allowMissingOwnerFile = false)
    {
        string fullRoot = Path.GetFullPath(fixtureRoot).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        string fullDirectory = Path.GetFullPath(fixtureDirectory).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        string? parent = Path.GetDirectoryName(fullDirectory);
        string expectedName = FixtureDirectoryPrefix + ownerToken;
        if (!string.Equals(parent, fullRoot, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(Path.GetFileName(fullDirectory), expectedName, StringComparison.Ordinal)
            || !Guid.TryParseExact(ownerToken, "N", out _))
        {
            throw new InvalidOperationException("Refusing to remove a lease fixture directory outside its unique temp child.");
        }
        if (!Directory.Exists(fullDirectory))
        {
            return;
        }

        var rootInfo = new DirectoryInfo(fullDirectory);
        if ((rootInfo.Attributes & FileAttributes.ReparsePoint) != 0)
        {
            throw new InvalidOperationException("Refusing to recursively remove a reparse-point lease fixture directory.");
        }

        string ownerPath = Path.Combine(fullDirectory, FixtureOwnerFileName);
        if (!File.Exists(ownerPath))
        {
            if (!allowMissingOwnerFile)
            {
                throw new InvalidOperationException("Refusing to remove a lease fixture directory without its owner marker.");
            }
        }
        else if ((File.GetAttributes(ownerPath) & FileAttributes.ReparsePoint) != 0
            || !string.Equals(File.ReadAllText(ownerPath, Encoding.ASCII), ownerToken, StringComparison.Ordinal))
        {
            throw new InvalidOperationException("Refusing to remove a lease fixture directory with a mismatched owner marker.");
        }

        string requiredPrefix = fullDirectory + Path.DirectorySeparatorChar;
        var pendingDirectories = new Stack<string>();
        pendingDirectories.Push(fullDirectory);
        while (pendingDirectories.Count > 0)
        {
            string currentDirectory = pendingDirectories.Pop();
            foreach (string entry in Directory.EnumerateFileSystemEntries(currentDirectory))
            {
                string fullEntry = Path.GetFullPath(entry);
                if (!fullEntry.StartsWith(requiredPrefix, StringComparison.OrdinalIgnoreCase))
                {
                    throw new InvalidOperationException("Refusing to remove a lease fixture entry outside its unique temp child.");
                }
                FileAttributes attributes = File.GetAttributes(fullEntry);
                if ((attributes & FileAttributes.ReparsePoint) != 0)
                {
                    throw new InvalidOperationException("Refusing to recursively remove a lease fixture containing a reparse point.");
                }
                if ((attributes & FileAttributes.Directory) != 0)
                {
                    pendingDirectories.Push(fullEntry);
                }
            }
        }

        Directory.Delete(fullDirectory, recursive: true);
    }

    private static SuspendedLeaseProcess CreateSuspendedFixtureProcess(string markerPath)
    {
        (string application, IReadOnlyList<string> arguments) = GetSelfCommand(
            "--lease-job-fixture-root",
            markerPath);
        var commandLine = new StringBuilder(BuildCommandLine(application, arguments), 32_768);
        var startup = new LeaseProcessJobHarnessNativeMethods.StartupInfo
        {
            Size = Marshal.SizeOf<LeaseProcessJobHarnessNativeMethods.StartupInfo>(),
        };
        if (!LeaseProcessJobHarnessNativeMethods.CreateProcessW(
                application,
                commandLine,
                IntPtr.Zero,
                IntPtr.Zero,
                inheritHandles: false,
                CreateSuspended | CreateNoWindow,
                IntPtr.Zero,
                Environment.CurrentDirectory,
                ref startup,
                out LeaseProcessJobHarnessNativeMethods.ProcessInformation information))
        {
            throw new System.ComponentModel.Win32Exception(
                Marshal.GetLastWin32Error(),
                "Could not create the suspended lease process fixture.");
        }

        SafeProcessHandle processHandle = new(information.Process, ownsHandle: true);
        SafeThreadHandle threadHandle = new(information.Thread, ownsHandle: true);
        try
        {
            return new SuspendedLeaseProcess(processHandle, threadHandle, information.ProcessId);
        }
        catch
        {
            threadHandle.Dispose();
            processHandle.Dispose();
            throw;
        }
    }

    private static ProcessStartInfo CreateSelfStartInfo(params string[] arguments)
    {
        (string application, IReadOnlyList<string> fullArguments) = GetSelfCommand(arguments);
        var startInfo = new ProcessStartInfo(application) { UseShellExecute = false };
        foreach (string argument in fullArguments)
        {
            startInfo.ArgumentList.Add(argument);
        }
        return startInfo;
    }

    private static (string Application, IReadOnlyList<string> Arguments) GetSelfCommand(params string[] arguments)
    {
        string application = Environment.ProcessPath
            ?? throw new InvalidOperationException("The current process path is unavailable.");
        var fullArguments = new List<string>();
        if (string.Equals(Path.GetFileNameWithoutExtension(application), "dotnet", StringComparison.OrdinalIgnoreCase))
        {
            string assemblyPath = System.Reflection.Assembly.GetEntryAssembly()?.Location
                ?? throw new InvalidOperationException("The current entry assembly path is unavailable.");
            fullArguments.Add(assemblyPath);
        }
        fullArguments.AddRange(arguments);
        return (application, fullArguments);
    }

    private static string BuildCommandLine(string application, IReadOnlyList<string> arguments) =>
        string.Join(" ", new[] { application }.Concat(arguments).Select(QuoteWindowsArgument));

    private static string QuoteWindowsArgument(string argument)
    {
        var result = new StringBuilder(argument.Length + 2);
        result.Append('"');
        int backslashes = 0;
        foreach (char character in argument)
        {
            if (character == '\\')
            {
                backslashes++;
                continue;
            }

            if (character == '"')
            {
                result.Append('\\', (backslashes * 2) + 1);
                result.Append('"');
                backslashes = 0;
                continue;
            }

            result.Append('\\', backslashes);
            result.Append(character);
            backslashes = 0;
        }

        result.Append('\\', backslashes * 2);
        result.Append('"');
        return result.ToString();
    }

    private static void ExpectThrows<TException>(Action action) where TException : Exception
    {
        try
        {
            action();
        }
        catch (TException)
        {
            return;
        }
        throw new InvalidOperationException($"Expected {typeof(TException).Name} from the lease process job fixture.");
    }

    private static void Assert(bool condition, string message)
    {
        if (!condition)
        {
            throw new InvalidOperationException(message);
        }
    }

    private sealed class FixtureScenarioException(string message) : Exception(message)
    {
    }

    private sealed class FakeNative : ILeaseProcessJobNative
    {
        internal List<string> Events { get; } = [];
        internal SafeJobObjectHandle JobHandle { get; } = new(new IntPtr(1), ownsHandle: false);
        internal SafeProcessHandle ProcessHandle { get; } = new(new IntPtr(2), ownsHandle: false);
        internal SafeThreadHandle ThreadHandle { get; } = new(new IntPtr(3), ownsHandle: false);
        internal uint ConfiguredFlags { get; set; } = LeaseProcessJob.KillOnJobClose;
        internal uint ResumeCount { get; set; } = 1;
        internal Exception? AssignError { get; set; }
        private uint _activeProcesses;

        public SafeJobObjectHandle CreateUnnamedJob()
        {
            Events.Add("create-job");
            return JobHandle;
        }

        public void SetKillOnClose(SafeJobObjectHandle job)
        {
            Events.Add("set-limits");
        }

        public uint GetLimitFlags(SafeJobObjectHandle job)
        {
            Events.Add("query-limits");
            return ConfiguredFlags;
        }

        public void AssignProcess(SafeJobObjectHandle job, SafeProcessHandle process)
        {
            Events.Add("assign");
            if (AssignError is not null)
            {
                throw AssignError;
            }
            _activeProcesses = 1;
        }

        public uint ResumePrimaryThread(SafeThreadHandle thread)
        {
            Events.Add("resume");
            return ResumeCount;
        }

        public void TerminateProcess(SafeProcessHandle process, uint exitCode) => Events.Add("terminate-process");

        public void WaitForProcessExit(SafeProcessHandle process, TimeSpan timeout) => Events.Add("wait-process");

        public void TerminateJob(SafeJobObjectHandle job, uint exitCode)
        {
            Events.Add("terminate-job");
            _activeProcesses = 0;
        }

        public uint GetActiveProcessCount(SafeJobObjectHandle job)
        {
            Events.Add("wait-job-drain");
            return _activeProcesses;
        }

        public bool IsProcessInJob(SafeProcessHandle process, SafeJobObjectHandle job) => _activeProcesses > 0;

        internal SuspendedLeaseProcess CreateSuspendedProcess()
        {
            Events.Add("create-suspended");
            return new SuspendedLeaseProcess(ProcessHandle, ThreadHandle, processId: 42);
        }
    }
}

internal static class LeaseProcessJobHarnessNativeMethods
{
    internal const uint WaitObject0 = 0;
    internal const uint WaitTimeout = 258;

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, EntryPoint = "CreateDirectoryW", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool CreateDirectoryW(string path, IntPtr securityAttributes);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    internal struct StartupInfo
    {
        public int Size;
        public string? Reserved;
        public string? Desktop;
        public string? Title;
        public int X;
        public int Y;
        public int XSize;
        public int YSize;
        public int XCountChars;
        public int YCountChars;
        public int FillAttribute;
        public int Flags;
        public short ShowWindow;
        public short Reserved2Size;
        public IntPtr Reserved2;
        public IntPtr StandardInput;
        public IntPtr StandardOutput;
        public IntPtr StandardError;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct ProcessInformation
    {
        public IntPtr Process;
        public IntPtr Thread;
        public uint ProcessId;
        public uint ThreadId;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, EntryPoint = "CreateProcessW", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool CreateProcessW(
        string applicationName,
        StringBuilder commandLine,
        IntPtr processAttributes,
        IntPtr threadAttributes,
        [MarshalAs(UnmanagedType.Bool)] bool inheritHandles,
        uint creationFlags,
        IntPtr environment,
        string? currentDirectory,
        ref StartupInfo startupInfo,
        out ProcessInformation processInformation);

    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern SafeProcessHandle OpenProcess(
        uint desiredAccess,
        [MarshalAs(UnmanagedType.Bool)] bool inheritHandle,
        uint processId);

    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern uint WaitForSingleObject(SafeProcessHandle handle, uint milliseconds);
}
