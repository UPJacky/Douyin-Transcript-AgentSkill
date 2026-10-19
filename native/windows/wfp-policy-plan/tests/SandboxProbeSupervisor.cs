using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.Security;
using System.Text;
using System.Text.Json;

namespace WfpPolicyPlanTests;

internal sealed class SandboxProbeAccount(string userName, string sid, SecureString password) : IDisposable
{
    internal string UserName { get; } = userName;
    internal string Sid { get; } = sid;
    internal SecureString Password { get; } = password;

    public void Dispose() => Password.Dispose();
}

[SupportedOSPlatform("windows6.0.6000")]
internal sealed class SandboxProbeSupervisor : IDisposable
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    private readonly string runToken;
    private readonly List<ManagedProbe> children = [];
    private readonly List<HelperIdentityEvidence> helperIdentities = [];
    private int verifiedHelperStarts;

    internal SandboxProbeSupervisor(string runToken) => this.runToken = runToken;
    internal int VerifiedHelperStarts => verifiedHelperStarts;
    internal IReadOnlyList<HelperIdentityEvidence> HelperIdentities => helperIdentities.AsReadOnly();

    internal ManagedProbe Start(
        string executable,
        SandboxProbeAccount account,
        string mode,
        string address,
        int port)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = executable,
            WorkingDirectory = Path.GetDirectoryName(executable)!,
            UseShellExecute = false,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UserName = account.UserName,
            Domain = ".",
            Password = account.Password,
            LoadUserProfile = true,
            CreateNoWindow = true,
        };
        startInfo.Environment["WFP_DISPOSABLE_SANDBOX_GUEST"] = "1";
        startInfo.Environment["WFP_DISPOSABLE_SANDBOX_RUN_TOKEN"] = runToken;
        startInfo.ArgumentList.Add("--sandbox-probe-client");
        startInfo.ArgumentList.Add(runToken);
        startInfo.ArgumentList.Add(mode);
        startInfo.ArgumentList.Add(address);
        startInfo.ArgumentList.Add(port.ToString(System.Globalization.CultureInfo.InvariantCulture));

        var process = new Process { StartInfo = startInfo, EnableRaisingEvents = true };
        if (!process.Start())
            throw new InvalidOperationException("Could not start a probe helper under its lease user.");

        var child = new ManagedProbe(process, account.Sid, Path.GetFullPath(executable));
        children.Add(child);
        try
        {
            helperIdentities.Add(child.VerifyReadyAndIdentity());
            verifiedHelperStarts++;
            return child;
        }
        catch
        {
            child.Dispose();
            children.Remove(child);
            throw;
        }
    }

    internal bool Probe(
        string executable,
        SandboxProbeAccount account,
        string mode,
        string address,
        int port)
    {
        using ManagedProbe child = Start(executable, account, mode, address, port);
        child.Continue();
        SandboxProbeClient.HelperMessage outcome = child.ReadMessage(TimeSpan.FromSeconds(6));
        if (outcome.Type != "result" || outcome.Succeeded is null)
            throw new InvalidOperationException("A network helper returned an invalid result record.");
        child.WaitForExit(TimeSpan.FromSeconds(2));
        if (child.ExitCode != 0)
            throw new InvalidOperationException("A network helper exited unsuccessfully.");
        return outcome.Succeeded.Value;
    }

    public void Dispose()
    {
        Exception? firstFailure = null;
        foreach (ManagedProbe child in children.ToArray())
        {
            try { child.Dispose(); }
            catch (Exception error) { firstFailure ??= error; }
        }
        children.Clear();
        if (firstFailure is not null)
            throw new InvalidOperationException("At least one helper process could not be stopped.", firstFailure);
    }

    internal sealed record HelperIdentityEvidence(int Pid, string Sid, string ImagePath, bool ParentTokenVerified, bool ParentImageVerified);

    internal sealed class ManagedProbe(Process process, string expectedSid, string expectedImagePath) : IDisposable
    {
        private bool disposed;

        internal int ExitCode => process.ExitCode;

        internal HelperIdentityEvidence VerifyReadyAndIdentity()
        {
            SandboxProbeClient.HelperMessage ready = ReadMessage(TimeSpan.FromSeconds(10));
            if (ready.Type != "ready" || ready.Sid != expectedSid || ready.Pid != process.Id
                || !string.Equals(Path.GetFullPath(ready.ImagePath), expectedImagePath, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException("A helper reported an unexpected pre-network identity.");
            }

            string actualSid = ProcessIdentity.GetUserSid(process);
            string actualImagePath = ProcessIdentity.GetImagePath(process);
            if (actualSid != expectedSid
                || !string.Equals(actualImagePath, expectedImagePath, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException("The parent process token or image path did not match the helper report.");
            }
            return new HelperIdentityEvidence(process.Id, actualSid, actualImagePath,
                ParentTokenVerified: true, ParentImageVerified: true);
        }

        internal void Continue()
        {
            process.StandardInput.WriteLine("GO");
            process.StandardInput.Flush();
        }

        internal void WaitUntilListening()
        {
            Continue();
            SandboxProbeClient.HelperMessage listening = ReadMessage(TimeSpan.FromSeconds(10));
            if (listening.Type != "listening" || listening.Succeeded != true || listening.Pid != process.Id
                || !string.Equals(Path.GetFullPath(listening.ImagePath), expectedImagePath, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("A worker-owned listener could not bind its configured loopback port.");
        }

        internal SandboxProbeClient.HelperMessage ReadMessage(TimeSpan timeout)
        {
            string line;
            try
            {
                line = process.StandardOutput.ReadLineAsync().WaitAsync(timeout).GetAwaiter().GetResult()
                    ?? throw new InvalidOperationException("A helper exited before reporting its state.");
            }
            catch (TimeoutException)
            {
                throw new InvalidOperationException("A helper did not report its state before the deadline.");
            }

            try
            {
                return JsonSerializer.Deserialize<SandboxProbeClient.HelperMessage>(line, JsonOptions)
                    ?? throw new InvalidOperationException("A helper emitted an empty state record.");
            }
            catch (JsonException)
            {
                throw new InvalidOperationException("A helper emitted an invalid state record.");
            }
        }

        internal void WaitForExit(TimeSpan timeout)
        {
            if (!process.WaitForExit((int)timeout.TotalMilliseconds))
                throw new InvalidOperationException("A network helper did not exit before the deadline.");
        }

        public void Dispose()
        {
            if (disposed)
                return;
            disposed = true;
            try
            {
                if (!process.HasExited)
                {
                    try
                    {
                        process.StandardInput.WriteLine("STOP");
                        process.StandardInput.Flush();
                    }
                    catch (IOException) { }
                    if (!process.WaitForExit(1000))
                        process.Kill(entireProcessTree: true);
                    process.WaitForExit(3000);
                }
            }
            finally
            {
                process.Dispose();
            }
        }
    }

    private static class ProcessIdentity
    {
        private const uint TokenQuery = 0x0008;
        private const int TokenUser = 1;

        internal static string GetUserSid(Process process)
        {
            if (!OpenProcessToken(process.Handle, TokenQuery, out IntPtr token))
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not inspect the helper's actual process token.");
            try
            {
                _ = GetTokenInformation(token, TokenUser, IntPtr.Zero, 0, out int required);
                int error = Marshal.GetLastWin32Error();
                if (required <= IntPtr.Size || error != 122)
                    throw new Win32Exception(error, "Could not size the helper's token SID record.");
                IntPtr buffer = Marshal.AllocHGlobal(required);
                try
                {
                    if (!GetTokenInformation(token, TokenUser, buffer, required, out _))
                        throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not read the helper's token SID.");
                    IntPtr sid = Marshal.ReadIntPtr(buffer);
                    if (!ConvertSidToStringSid(sid, out IntPtr sidText))
                        throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not format the helper's token SID.");
                    try
                    {
                        return Marshal.PtrToStringUni(sidText) ?? throw new InvalidOperationException("The helper SID was empty.");
                    }
                    finally
                    {
                        _ = LocalFree(sidText);
                    }
                }
                finally
                {
                    Marshal.FreeHGlobal(buffer);
                }
            }
            finally
            {
                _ = CloseHandle(token);
            }
        }

        internal static string GetImagePath(Process process)
        {
            var path = new StringBuilder(32_768);
            int length = path.Capacity;
            if (!QueryFullProcessImageName(process.Handle, 0, path, ref length))
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not inspect the helper's actual image path.");
            return Path.GetFullPath(path.ToString());
        }

        [DllImport("advapi32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool OpenProcessToken(IntPtr processHandle, uint desiredAccess, out IntPtr tokenHandle);

        [DllImport("advapi32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool GetTokenInformation(IntPtr tokenHandle, int tokenInformationClass,
            IntPtr tokenInformation, int tokenInformationLength, out int returnLength);

        [DllImport("advapi32.dll", EntryPoint = "ConvertSidToStringSidW", CharSet = CharSet.Unicode, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool ConvertSidToStringSid(IntPtr sid, out IntPtr stringSid);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool QueryFullProcessImageName(IntPtr process, uint flags, StringBuilder imageName, ref int size);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool CloseHandle(IntPtr handle);

        [DllImport("kernel32.dll")]
        private static extern IntPtr LocalFree(IntPtr memory);
    }
}

[SupportedOSPlatform("windows6.0.6000")]
internal static class SandboxProbeImageStager
{
    internal static string[] StagePublishedImageSet(string sourceDirectory, string stagingRoot,
        IReadOnlyList<SandboxProbeAccount> accounts)
    {
        string source = Path.GetFullPath(sourceDirectory);
        string root = Path.GetFullPath(stagingRoot);
        Directory.CreateDirectory(root);
        string[] roles = ["browser-a", "worker-a", "browser-b", "worker-b"];
        var result = new string[roles.Length];
        for (int i = 0; i < roles.Length; i++)
        {
            string roleDirectory = Path.Combine(root, roles[i]);
            Directory.CreateDirectory(roleDirectory);
            foreach (string sourceFile in Directory.EnumerateFiles(source, "*", SearchOption.AllDirectories))
            {
                string relative = Path.GetRelativePath(source, sourceFile);
                string destination = Path.Combine(roleDirectory, relative);
                Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
                File.Copy(sourceFile, destination, overwrite: false);
            }

            int accountIndex = i < 2 ? 0 : 1;
            GrantReadExecute(roleDirectory, accounts[accountIndex].Sid);
            string image = Path.Combine(roleDirectory, Path.GetFileName(Environment.ProcessPath
                ?? throw new InvalidOperationException("Could not resolve the self-contained helper path.")));
            if (!File.Exists(image))
                throw new FileNotFoundException("The staged self-contained helper image is missing.", image);
            result[i] = image;
        }

        if (result.Select(Path.GetFullPath).Distinct(StringComparer.OrdinalIgnoreCase).Count() != 4)
            throw new InvalidOperationException("The four helper roles must have distinct executable paths.");
        return result;
    }

    private static void GrantReadExecute(string directory, string sid)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = Path.Combine(Environment.SystemDirectory, "icacls.exe"),
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
        };
        startInfo.ArgumentList.Add(directory);
        startInfo.ArgumentList.Add("/grant");
        startInfo.ArgumentList.Add($"*{sid}:(OI)(CI)(RX)");
        startInfo.ArgumentList.Add("/T");
        using Process process = Process.Start(startInfo) ?? throw new InvalidOperationException("Could not start icacls for helper image staging.");
        _ = process.StandardOutput.ReadToEnd();
        _ = process.StandardError.ReadToEnd();
        process.WaitForExit();
        if (process.ExitCode != 0)
            throw new InvalidOperationException("Could not grant a lease user read/execute access to its helper image.");
    }
}
