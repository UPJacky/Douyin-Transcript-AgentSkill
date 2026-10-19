using System.ComponentModel;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace DouyinTranscript.CapturePipe;

internal sealed record PeerIdentity(
    uint ProcessId,
    uint SessionId,
    string UserSid,
    IReadOnlySet<string> GroupSids,
    IReadOnlySet<string> EnabledGroupSids,
    string AuthenticationId,
    string ImagePath)
{
    public bool HasSid(string sid) =>
        UserSid.Equals(sid, StringComparison.OrdinalIgnoreCase)
        || EnabledGroupSids.Contains(sid);

    internal static bool IsEffectiveGroup(uint attributes) =>
        (attributes & NativeMethods.GroupEnabled) != 0
        && (attributes & NativeMethods.GroupUseForDenyOnly) == 0;
}

internal sealed record ClientPeerPolicy(
    IReadOnlySet<string> UserSids,
    IReadOnlySet<uint> SessionIds,
    bool AllowAnyInteractiveSession = false)
{
    public static ClientPeerPolicy Create(IEnumerable<string> userSids, IEnumerable<uint> sessionIds)
    {
        string[] normalized = userSids.Select(value => new SecurityIdentifier(value).Value).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        if (normalized.Length == 0)
        {
            throw new ArgumentException("At least one client user SID is required.", nameof(userSids));
        }
        uint[] sessions = sessionIds.Distinct().ToArray();
        if (sessions.Length == 0)
        {
            throw new ArgumentException("At least one allowed client session is required.", nameof(sessionIds));
        }
        return new ClientPeerPolicy(normalized.ToHashSet(StringComparer.OrdinalIgnoreCase), sessions.ToHashSet());
    }

    public static ClientPeerPolicy CreateForInteractiveSessions(IEnumerable<string> userSids)
    {
        string[] normalized = userSids.Select(value => new SecurityIdentifier(value).Value)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        if (normalized.Length == 0)
        {
            throw new ArgumentException("At least one client user SID is required.", nameof(userSids));
        }
        return new ClientPeerPolicy(
            normalized.ToHashSet(StringComparer.OrdinalIgnoreCase),
            new HashSet<uint>(),
            AllowAnyInteractiveSession: true);
    }

    public void Validate(PeerIdentity identity)
    {
        bool sessionAllowed = AllowAnyInteractiveSession
            ? identity.SessionId != 0
            : SessionIds.Contains(identity.SessionId);
        if (!UserSids.Contains(identity.UserSid) || !sessionAllowed)
        {
            throw new PipeAuthenticationException("The named pipe client is not authorized.");
        }
    }
}

internal sealed record ServicePeerPolicy(string ServiceSid, uint RequiredSessionId = 0)
{
    public ServicePeerPolicy Validate()
    {
        _ = new SecurityIdentifier(ServiceSid);
        return this;
    }

    public void Validate(PeerIdentity identity)
    {
        string expectedServiceSid = NormalizeServiceSid();
        if (identity.SessionId != RequiredSessionId || !identity.HasSid(expectedServiceSid))
        {
            throw new PipeAuthenticationException("The named pipe server identity is not trusted.");
        }
    }

    public void ValidateCurrentProcess()
    {
        PeerIdentity identity = PeerAuthenticator.ReadCurrentProcessIdentity();
        string expectedServiceSid = NormalizeServiceSid();
        if (identity.SessionId != RequiredSessionId || !identity.HasSid(expectedServiceSid))
        {
            throw new PipeAuthenticationException("The service process does not hold its configured service SID.");
        }
    }

    public string NormalizeServiceSid() => new SecurityIdentifier(ServiceSid).Value;
}

internal sealed class PipeAuthenticationException(string message) : Exception(message);

internal static class PeerAuthenticator
{
    private const uint TokenQuery = NativeMethods.TokenQuery;

    public static PeerIdentity AuthenticateClient(NamedPipeServerStream pipe)
    {
        SafePipeHandle handle = pipe.SafePipeHandle;
        if (!NativeMethods.GetNamedPipeClientProcessId(handle, out uint processId)
            || !NativeMethods.GetNamedPipeClientSessionId(handle, out uint pipeSessionId))
        {
            throw NativeMethods.LastError("Could not identify the named pipe client.");
        }

        PeerIdentity? impersonatedIdentity = null;
        pipe.RunAsClient(() =>
        {
            if (!NativeMethods.OpenThreadToken(
                    NativeMethods.GetCurrentThread(),
                    TokenQuery,
                    openAsSelf: true,
                    out SafeAccessTokenHandle impersonationToken))
            {
                throw NativeMethods.LastError("Could not read the named pipe client's OS token.");
            }

            using (impersonationToken)
            {
                impersonatedIdentity = ReadTokenIdentity(
                    impersonationToken,
                    processId,
                    pipeSessionId,
                    processHandle: null);
            }
        });

        PeerIdentity identity = impersonatedIdentity
            ?? throw new PipeAuthenticationException("The named pipe client token is unavailable.");

        using SafeProcessHandle process = OpenPeerProcess(processId);
        if (!NativeMethods.ProcessIdToSessionId(processId, out uint processSessionId))
        {
            throw NativeMethods.LastError("Could not read the named pipe client's session.");
        }
        using SafeAccessTokenHandle processToken = OpenPeerProcessToken(process);
        PeerIdentity processIdentity = ReadTokenIdentity(processToken, processId, processSessionId, process);
        EnsureSameLogon(identity, processIdentity, pipeSessionId);
        if (!NativeMethods.GetNamedPipeClientProcessId(handle, out uint verifiedProcessId)
            || !NativeMethods.GetNamedPipeClientSessionId(handle, out uint verifiedSessionId)
            || verifiedProcessId != processId
            || verifiedSessionId != pipeSessionId)
        {
            throw new PipeAuthenticationException("The named pipe client identity changed during verification.");
        }
        return identity with { ImagePath = processIdentity.ImagePath };
    }

    public static PeerIdentity AuthenticateServer(NamedPipeClientStream pipe, ServicePeerPolicy policy)
    {
        SafePipeHandle handle = pipe.SafePipeHandle;
        if (!NativeMethods.GetNamedPipeServerProcessId(handle, out uint processId)
            || !NativeMethods.GetNamedPipeServerSessionId(handle, out uint pipeSessionId))
        {
            throw NativeMethods.LastError("Could not identify the named pipe server.");
        }
        using SafeProcessHandle process = OpenPeerProcess(processId);
        if (!NativeMethods.ProcessIdToSessionId(processId, out uint processSessionId))
        {
            throw NativeMethods.LastError("Could not read the named pipe server's session.");
        }
        if (processSessionId != pipeSessionId)
        {
            throw new PipeAuthenticationException("The named pipe server session does not match its process.");
        }
        using SafeAccessTokenHandle processToken = OpenPeerProcessToken(process);
        PeerIdentity identity = ReadTokenIdentity(processToken, processId, processSessionId, process);
        policy.Validate(identity);
        if (!NativeMethods.GetNamedPipeServerProcessId(handle, out uint verifiedProcessId)
            || !NativeMethods.GetNamedPipeServerSessionId(handle, out uint verifiedSessionId)
            || verifiedProcessId != processId
            || verifiedSessionId != pipeSessionId)
        {
            throw new PipeAuthenticationException("The named pipe server identity changed during verification.");
        }
        return identity;
    }

    public static PeerIdentity ReadCurrentProcessIdentity()
    {
        uint processId = checked((uint)Environment.ProcessId);
        using SafeProcessHandle process = OpenPeerProcess(processId);
        if (!NativeMethods.ProcessIdToSessionId(processId, out uint sessionId))
        {
            throw NativeMethods.LastError("Could not read the current process session.");
        }
        using SafeAccessTokenHandle processToken = OpenPeerProcessToken(process);
        return ReadTokenIdentity(processToken, processId, sessionId, process);
    }

    private static PeerIdentity ReadTokenIdentity(
        SafeAccessTokenHandle token,
        uint processId,
        uint expectedSessionId,
        SafeProcessHandle? processHandle)
    {
        using var identity = new WindowsIdentity(token.DangerousGetHandle());
        string userSid = identity.User?.Value
            ?? throw new PipeAuthenticationException("The OS token has no user SID.");
        (HashSet<string> groups, HashSet<string> enabledGroups) = ReadTokenGroups(token);
        uint tokenSessionId = ReadTokenSessionId(token);
        string authenticationId = ReadAuthenticationId(token);
        string imagePath = processHandle is null ? string.Empty : QueryImagePath(processHandle);
        if (tokenSessionId != expectedSessionId)
        {
            throw new PipeAuthenticationException("The OS token session does not match the pipe peer.");
        }
        return new PeerIdentity(processId, tokenSessionId, userSid, groups, enabledGroups, authenticationId, imagePath);
    }

    private static void EnsureSameLogon(PeerIdentity pipeToken, PeerIdentity processToken, uint pipeSessionId)
    {
        if (pipeToken.ProcessId != processToken.ProcessId
            || pipeToken.SessionId != pipeSessionId
            || processToken.SessionId != pipeSessionId
            || !pipeToken.UserSid.Equals(processToken.UserSid, StringComparison.OrdinalIgnoreCase)
            || !pipeToken.GroupSids.SetEquals(processToken.GroupSids)
            || !pipeToken.AuthenticationId.Equals(processToken.AuthenticationId, StringComparison.Ordinal))
        {
            throw new PipeAuthenticationException("The pipe client token does not match its connected process.");
        }
    }

    private static SafeProcessHandle OpenPeerProcess(uint processId)
    {
        SafeProcessHandle process = NativeMethods.OpenProcess(
            NativeMethods.ProcessQueryLimitedInformation,
            inheritHandle: false,
            processId);
        if (process.IsInvalid)
        {
            process.Dispose();
            throw NativeMethods.LastError("Could not open the named pipe peer process.");
        }
        return process;
    }

    private static SafeAccessTokenHandle OpenPeerProcessToken(SafeProcessHandle process)
    {
        if (!NativeMethods.OpenProcessToken(process, TokenQuery, out SafeAccessTokenHandle token))
        {
            throw NativeMethods.LastError("Could not read the named pipe peer process token.");
        }
        return token;
    }

    private static uint ReadTokenSessionId(SafeAccessTokenHandle token)
    {
        IntPtr buffer = Marshal.AllocHGlobal(sizeof(uint));
        try
        {
            if (!NativeMethods.GetTokenInformation(
                    token,
                    NativeMethods.TokenSessionId,
                    buffer,
                    sizeof(uint),
                    out int returned)
                || returned != sizeof(uint))
            {
                throw NativeMethods.LastError("Could not read the OS token session.");
            }
            return unchecked((uint)Marshal.ReadInt32(buffer));
        }
        finally
        {
            Marshal.FreeHGlobal(buffer);
        }
    }

    private static (HashSet<string> AllGroups, HashSet<string> EnabledGroups) ReadTokenGroups(
        SafeAccessTokenHandle token)
    {
        int headerSize = Marshal.OffsetOf<NativeMethods.TokenGroupsHeader>(nameof(NativeMethods.TokenGroupsHeader.FirstGroup)).ToInt32();
        if (NativeMethods.GetTokenInformation(
                token,
                NativeMethods.TokenGroups,
                IntPtr.Zero,
                0,
                out int requiredBytes))
        {
            throw new PipeAuthenticationException("The OS token group size query unexpectedly succeeded.");
        }
        int sizeQueryError = Marshal.GetLastWin32Error();
        if (sizeQueryError != 122 || requiredBytes < headerSize || requiredBytes > 1_048_576)
        {
            throw new Win32Exception(sizeQueryError, "Could not determine the OS token group buffer size.");
        }

        IntPtr buffer = Marshal.AllocHGlobal(requiredBytes);
        try
        {
            if (!NativeMethods.GetTokenInformation(
                    token,
                    NativeMethods.TokenGroups,
                    buffer,
                    requiredBytes,
                    out int returnedBytes))
            {
                Exception error = NativeMethods.LastError("Could not read the OS token groups.");
                throw error;
            }
            if (returnedBytes < headerSize || returnedBytes > requiredBytes)
            {
                throw new PipeAuthenticationException("The OS token group buffer length is invalid.");
            }

            NativeMethods.TokenGroupsHeader header = Marshal.PtrToStructure<NativeMethods.TokenGroupsHeader>(buffer);
            int groupSize = Marshal.SizeOf<NativeMethods.SidAndAttributes>();
            long expectedEnd = (long)headerSize + ((long)header.GroupCount * groupSize);
            if (header.GroupCount > 65_536 || expectedEnd > returnedBytes)
            {
                throw new PipeAuthenticationException("The OS token group list is malformed or over limit.");
            }

            var groups = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var enabledGroups = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            for (uint index = 0; index < header.GroupCount; index++)
            {
                int offset = checked(headerSize + (int)index * groupSize);
                NativeMethods.SidAndAttributes entry = Marshal.PtrToStructure<NativeMethods.SidAndAttributes>(
                    IntPtr.Add(buffer, offset));
                string sid = new SecurityIdentifier(entry.Sid).Value;
                groups.Add(sid);
                if (PeerIdentity.IsEffectiveGroup(entry.Attributes))
                {
                    enabledGroups.Add(sid);
                }
            }
            return (groups, enabledGroups);
        }
        finally
        {
            Marshal.FreeHGlobal(buffer);
        }
    }

    private static string ReadAuthenticationId(SafeAccessTokenHandle token)
    {
        int size = Marshal.SizeOf<NativeMethods.TokenStatisticsInfo>();
        IntPtr buffer = Marshal.AllocHGlobal(size);
        try
        {
            if (!NativeMethods.GetTokenInformation(
                    token,
                    NativeMethods.TokenStatistics,
                    buffer,
                    size,
                    out int returned)
                || returned != size)
            {
                throw NativeMethods.LastError("Could not read the OS token logon identity.");
            }
            NativeMethods.TokenStatisticsInfo statistics = Marshal.PtrToStructure<NativeMethods.TokenStatisticsInfo>(buffer);
            return $"{statistics.AuthenticationId.HighPart:x8}{statistics.AuthenticationId.LowPart:x8}";
        }
        finally
        {
            Marshal.FreeHGlobal(buffer);
        }
    }

    private static string QueryImagePath(SafeProcessHandle process)
    {
        var imagePath = new StringBuilder(32768);
        uint size = (uint)imagePath.Capacity;
        if (!NativeMethods.QueryFullProcessImageNameW(process, 0, imagePath, ref size))
        {
            throw NativeMethods.LastError("Could not read the named pipe peer image path.");
        }
        return imagePath.ToString();
    }

}
