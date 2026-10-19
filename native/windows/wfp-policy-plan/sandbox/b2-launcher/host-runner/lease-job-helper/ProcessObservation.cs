using System.Security.Principal;
using System.Runtime.InteropServices;
using DouyinTranscript.CapturePipe;
using Microsoft.Win32.SafeHandles;

namespace DouyinTranscript.LeaseJobHelper;

internal sealed class ProcessObservation
{
    internal uint ProcessId { get; init; }
    internal uint ParentProcessId { get; set; }
    internal string ParentProcessIdSource { get; set; } = "unknown";
    internal string ImageName { get; set; } = "unknown";
    internal string? UserSid { get; set; }
    internal int? SessionId { get; set; }
    internal string? IntegritySid { get; set; }
    internal string? IntegrityLevel { get; set; }
    internal bool? TokenIsElevated { get; set; }
    internal bool? JobMember { get; set; }
    internal bool Exited { get; set; }
    internal int? Win32Error { get; set; }
    internal string? QueryStatus { get; set; }

    internal Dictionary<string, object?> ToDictionary() => new()
    {
        ["pid"] = ProcessId,
        ["parent_pid"] = ParentProcessId,
        ["parent_pid_source"] = ParentProcessIdSource,
        ["image_name"] = ImageName,
        ["sid"] = UserSid,
        ["session_id"] = SessionId,
        ["integrity_sid"] = IntegritySid,
        ["integrity_level"] = IntegrityLevel,
        ["token_is_elevated"] = TokenIsElevated,
        ["not_elevated"] = TokenIsElevated is false,
        ["job_member"] = JobMember,
        ["exited"] = Exited,
        ["query_status"] = QueryStatus,
        ["win32_error"] = Win32Error,
    };
}

internal sealed class ProcessTracker
{
    private readonly Dictionary<uint, ProcessObservation> _processes = [];
    private readonly HashSet<uint> _exitEvents = [];
    private readonly TrackedJobNative _native;
    private readonly Func<uint, SafeProcessHandle?>? _onNewProcess;

    internal ProcessTracker(TrackedJobNative native, Func<uint, SafeProcessHandle?>? onNewProcess = null)
    {
        _native = native;
        _onNewProcess = onNewProcess;
    }

    internal IReadOnlyList<ProcessObservation> Processes => _processes.Values.OrderBy(process => process.ProcessId).ToArray();

    internal void CaptureTree(uint rootPid, LeaseProcessJob job, string expectedSid, int expectedSession)
    {
        DrainNotifications(job, expectedSid, expectedSession);
        IReadOnlyDictionary<uint, NativeMethods.ProcessEntry32> snapshot = TakeProcessSnapshot();
        var reachable = new HashSet<uint> { rootPid };
        bool changed;
        do
        {
            changed = false;
            foreach (NativeMethods.ProcessEntry32 process in snapshot.Values)
            {
                if (reachable.Contains(process.ParentProcessId) && reachable.Add(process.ProcessId))
                {
                    changed = true;
                }
            }
        } while (changed);

        foreach (uint pid in reachable)
        {
            if (snapshot.TryGetValue(pid, out NativeMethods.ProcessEntry32 process))
            {
                Observe(pid, process.ParentProcessId, process.ExecutableFile, job, expectedSid, expectedSession);
            }
            else if (!_processes.ContainsKey(pid))
            {
                Observe(pid, 0, "unknown", job, expectedSid, expectedSession);
            }
        }
    }

    internal void DrainNotifications(LeaseProcessJob job, string expectedSid, int expectedSession)
    {
        while (true)
        {
            bool success = NativeMethods.GetQueuedCompletionStatus(_native.CompletionPort, out uint message,
                out IntPtr completionKey, out IntPtr overlapped, 0);
            if (!success)
            {
                int error = Marshal.GetLastWin32Error();
                if (error == NativeMethods.WaitTimeout)
                {
                    return;
                }
                throw new NativeApiException("GetQueuedCompletionStatus.JobTracker", error);
            }
            if (completionKey != _native.CompletionKey)
            {
                continue;
            }
            uint pid = unchecked((uint)overlapped.ToInt64());
            if (message == TrackedJobNative.MessageNewProcess && pid != 0)
            {
                // A short-lived child can exit between this notification and
                // the next Toolhelp snapshot. Let diagnostic callers retain a
                // process handle before the normal token observation runs.
                SafeProcessHandle? retainedHandle = _onNewProcess?.Invoke(pid);
                Observe(pid, 0, "unknown", job, expectedSid, expectedSession, retainedHandle);
            }
            else if ((message == TrackedJobNative.MessageExitProcess || message == TrackedJobNative.MessageAbnormalExitProcess)
                && pid != 0)
            {
                _exitEvents.Add(pid);
                if (_processes.TryGetValue(pid, out ProcessObservation? observation))
                {
                    observation.Exited = true;
                }
            }
        }
    }

    internal bool HasLiveDescendants(uint rootPid) => _processes.Values.Any(process => process.ProcessId != rootPid && !process.Exited && IsLive(process.ProcessId));

    private void Observe(
        uint pid,
        uint parentPid,
        string imageName,
        LeaseProcessJob job,
        string expectedSid,
        int expectedSession,
        SafeProcessHandle? retainedHandle = null)
    {
        if (_processes.TryGetValue(pid, out ProcessObservation? existing))
        {
            if (parentPid != 0)
            {
                existing.ParentProcessId = parentPid;
                existing.ParentProcessIdSource = "toolhelp_snapshot";
            }
            if (imageName != "unknown")
            {
                existing.ImageName = imageName;
            }
            if (existing.UserSid is not null)
            {
                return;
            }
        }
        else
        {
            existing = new ProcessObservation { ProcessId = pid, ParentProcessId = parentPid, ImageName = imageName };
            _processes.Add(pid, existing);
        }

        bool ownsProcessHandle = retainedHandle is null;
        SafeProcessHandle process = retainedHandle ?? NativeMethods.OpenProcess(
            NativeMethods.ProcessQueryLimitedInformation | NativeMethods.ProcessSynchronize, false, pid);
        if (process.IsInvalid)
        {
            existing.Win32Error = Marshal.GetLastWin32Error();
            existing.QueryStatus = "process could not be opened for query";
            existing.Exited |= _exitEvents.Contains(pid);
            if (ownsProcessHandle) process.Dispose();
            return;
        }
        try
        {
            if (existing.ImageName == "unknown" && TryReadProcessImageName(process, out string observedImageName))
            {
                existing.ImageName = observedImageName;
            }
            if (existing.ParentProcessId == 0 && TryReadParentProcessId(process, out uint observedParentProcessId))
            {
                existing.ParentProcessId = observedParentProcessId;
                existing.ParentProcessIdSource = "process_basic_information";
            }

            try
            {
                if (!NativeMethods.OpenProcessToken(process.DangerousGetHandle(), NativeMethods.TokenQuery, out SafeAccessTokenHandle token))
                {
                    throw LastError("OpenProcessToken.ProcessObservation");
                }
                using (token)
                {
                    existing.UserSid = ReadTokenSid(token, NativeMethods.TokenUser);
                    existing.IntegritySid = ReadIntegritySid(token);
                    existing.IntegrityLevel = GetIntegrityLabel(existing.IntegritySid);
                    existing.SessionId = checked((int)ReadTokenSessionId(token));
                    existing.TokenIsElevated = ReadTokenElevation(token);
                }
                existing.JobMember = job.IsProcessInJob(process);
                existing.Exited |= _exitEvents.Contains(pid);
                var failures = new List<string>();
                if (existing.UserSid != expectedSid) failures.Add("sid_mismatch");
                if (existing.SessionId != expectedSession) failures.Add("session_mismatch");
                if (existing.TokenIsElevated is not false) failures.Add("token_elevated_or_unverified");
                if (existing.JobMember != true) failures.Add("job_membership_not_verified");
                existing.QueryStatus = failures.Count == 0 ? "verified" : string.Join(",", failures);
            }
            catch (NativeApiException error)
            {
                existing.Win32Error = error.ErrorCode;
                existing.QueryStatus = error.Api;
            }
        }
        finally
        {
            if (ownsProcessHandle) process.Dispose();
        }
    }

    private static bool TryReadProcessImageName(SafeProcessHandle process, out string imageName)
    {
        var buffer = new System.Text.StringBuilder(32768);
        uint size = (uint)buffer.Capacity;
        if (!NativeMethods.QueryFullProcessImageName(process, 0, buffer, ref size) || size == 0 || size > buffer.Capacity)
        {
            imageName = string.Empty;
            return false;
        }
        imageName = Path.GetFileName(buffer.ToString());
        return !string.IsNullOrWhiteSpace(imageName);
    }

    private static bool TryReadParentProcessId(SafeProcessHandle process, out uint parentProcessId)
    {
        parentProcessId = 0;
        if (IntPtr.Size != 8) return false;
        int status = NativeMethods.NtQueryInformationProcess(process, NativeMethods.ProcessBasicInformationClass,
            out NativeMethods.ProcessBasicInformation information,
            Marshal.SizeOf<NativeMethods.ProcessBasicInformation>(), out _);
        ulong rawParentProcessId = information.InheritedFromUniqueProcessId.ToUInt64();
        if (status < 0 || rawParentProcessId == 0 || rawParentProcessId > uint.MaxValue) return false;
        parentProcessId = (uint)rawParentProcessId;
        return true;
    }

    private static IReadOnlyDictionary<uint, NativeMethods.ProcessEntry32> TakeProcessSnapshot()
    {
        using SafeNativeHandle snapshot = NativeMethods.CreateToolhelp32Snapshot(NativeMethods.Th32csSnapProcess, 0);
        if (snapshot.IsInvalid)
        {
            throw LastError("CreateToolhelp32Snapshot");
        }
        var processes = new Dictionary<uint, NativeMethods.ProcessEntry32>();
        var entry = new NativeMethods.ProcessEntry32 { Size = (uint)Marshal.SizeOf<NativeMethods.ProcessEntry32>() };
        if (!NativeMethods.Process32First(snapshot, ref entry))
        {
            int error = Marshal.GetLastWin32Error();
            if (error != NativeMethods.ErrorNotFound)
            {
                throw new NativeApiException("Process32First", error);
            }
            return processes;
        }
        do
        {
            processes[entry.ProcessId] = entry;
            entry = new NativeMethods.ProcessEntry32 { Size = (uint)Marshal.SizeOf<NativeMethods.ProcessEntry32>() };
        } while (NativeMethods.Process32Next(snapshot, ref entry));
        return processes;
    }

    private static bool IsLive(uint pid)
    {
        using SafeProcessHandle process = NativeMethods.OpenProcess(NativeMethods.ProcessSynchronize, false, pid);
        if (process.IsInvalid)
        {
            return false;
        }
        return NativeMethods.WaitForSingleObject(process, 0) == NativeMethods.WaitTimeout;
    }

    private static string ReadTokenSid(SafeAccessTokenHandle token, int informationClass)
    {
        IntPtr buffer = ReadTokenInfo(token, informationClass, out _);
        try
        {
            NativeMethods.SidAndAttributes user = Marshal.PtrToStructure<NativeMethods.SidAndAttributes>(buffer);
            return ConvertSidToString(user.Sid);
        }
        finally
        {
            Marshal.FreeHGlobal(buffer);
        }
    }

    private static string ReadIntegritySid(SafeAccessTokenHandle token)
    {
        IntPtr buffer = ReadTokenInfo(token, NativeMethods.TokenIntegrityLevel, out _);
        try
        {
            NativeMethods.SidAndAttributes label = Marshal.PtrToStructure<NativeMethods.SidAndAttributes>(buffer);
            return ConvertSidToString(label.Sid);
        }
        finally
        {
            Marshal.FreeHGlobal(buffer);
        }
    }

    private static uint ReadTokenSessionId(SafeAccessTokenHandle token)
    {
        IntPtr buffer = ReadTokenInfo(token, NativeMethods.TokenSessionId, out int returned);
        try
        {
            if (returned < sizeof(uint)) throw new NativeApiException("GetTokenInformation.TokenSessionId", 13);
            return unchecked((uint)Marshal.ReadInt32(buffer));
        }
        finally
        {
            Marshal.FreeHGlobal(buffer);
        }
    }

    private static bool ReadTokenElevation(SafeAccessTokenHandle token)
    {
        // TOKEN_ELEVATION is a fixed-size ULONG. Unlike variable-size token
        // information, the null-buffer size probe can return ERROR_BAD_LENGTH
        // instead of ERROR_INSUFFICIENT_BUFFER on supported Windows builds.
        IntPtr buffer = Marshal.AllocHGlobal(sizeof(uint));
        try
        {
            if (!NativeMethods.GetTokenInformation(token, NativeMethods.TokenElevation,
                    buffer, sizeof(uint), out int returned))
            {
                throw LastError("GetTokenInformation.ProcessObservation.TokenElevation");
            }
            if (returned < sizeof(uint)) throw new NativeApiException("GetTokenInformation.ProcessObservation.TokenElevation", 13);
            uint elevated = unchecked((uint)Marshal.ReadInt32(buffer));
            if (elevated > 1) throw new NativeApiException("VerifyTokenElevation.ProcessObservation.InvalidValue", 13);
            return elevated != 0;
        }
        finally
        {
            Marshal.FreeHGlobal(buffer);
        }
    }

    internal static void ValidateCurrentTokenElevationQuery()
    {
        if (!NativeMethods.OpenProcessToken(NativeMethods.GetCurrentProcess(), NativeMethods.TokenQuery,
                out SafeAccessTokenHandle token))
        {
            throw LastError("OpenProcessToken.ProcessObservationSelfTest");
        }
        using (token)
        {
            _ = ReadTokenElevation(token);
        }
    }

    private static IntPtr ReadTokenInfo(SafeAccessTokenHandle token, int informationClass, out int returned)
    {
        _ = NativeMethods.GetTokenInformation(token, informationClass, IntPtr.Zero, 0, out int required);
        int error = Marshal.GetLastWin32Error();
        if (required <= 0 || error != NativeMethods.ErrorInsufficientBuffer)
        {
            throw new NativeApiException("GetTokenInformation.ProcessObservation.Size", error);
        }
        IntPtr buffer = Marshal.AllocHGlobal(required);
        if (!NativeMethods.GetTokenInformation(token, informationClass, buffer, required, out returned))
        {
            error = Marshal.GetLastWin32Error();
            Marshal.FreeHGlobal(buffer);
            throw new NativeApiException("GetTokenInformation.ProcessObservation", error);
        }
        return buffer;
    }

    private static string ConvertSidToString(IntPtr sid)
    {
        if (!NativeMethods.ConvertSidToStringSid(sid, out IntPtr text))
        {
            throw LastError("ConvertSidToStringSid.ProcessObservation");
        }
        try
        {
            return Marshal.PtrToStringUni(text) ?? throw new NativeApiException("ConvertSidToStringSid.ProcessObservation.Read", 13);
        }
        finally
        {
            _ = NativeMethods.LocalFree(text);
        }
    }

    private static string GetIntegrityLabel(string? sid)
    {
        if (sid is null) return "unknown";
        string[] components = sid.Split('-');
        if (!uint.TryParse(components.LastOrDefault(), out uint rid)) return "unknown";
        return rid switch
        {
            < 0x1000 => "untrusted",
            < 0x2000 => "low",
            < 0x2100 => "medium",
            < 0x3000 => "medium-plus",
            < 0x4000 => "high",
            _ => "system-or-protected",
        };
    }

    private static NativeApiException LastError(string api) => new(api, Marshal.GetLastWin32Error());
}
