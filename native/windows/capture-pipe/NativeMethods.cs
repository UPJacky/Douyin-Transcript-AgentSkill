using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace DouyinTranscript.CapturePipe;

internal static class NativeMethods
{
    internal const uint PipeAccessDuplex = 0x00000003;
    internal const uint FileFlagOverlapped = 0x40000000;
    internal const uint FileFlagFirstPipeInstance = 0x00080000;
    internal const uint PipeTypeMessage = 0x00000004;
    internal const uint PipeReadModeByte = 0x00000000;
    internal const uint PipeWait = 0x00000000;
    internal const uint PipeRejectRemoteClients = 0x00000008;
    internal const uint ProcessQueryLimitedInformation = 0x1000;
    internal const uint TokenQuery = 0x0008;
    internal const int TokenSessionId = 12;
    internal const int TokenStatistics = 10;
    internal const int TokenGroups = 2;
    internal const int SddlRevision1 = 1;
    internal const uint GroupEnabled = 0x00000004;
    internal const uint GroupUseForDenyOnly = 0x00000010;

    [StructLayout(LayoutKind.Sequential)]
    internal struct SecurityAttributes
    {
        public int Length;
        public IntPtr SecurityDescriptor;
        [MarshalAs(UnmanagedType.Bool)] public bool InheritHandle;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct Luid
    {
        public uint LowPart;
        public int HighPart;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct TokenStatisticsInfo
    {
        public Luid TokenId;
        public Luid AuthenticationId;
        public long ExpirationTime;
        public int TokenType;
        public int ImpersonationLevel;
        public int DynamicCharged;
        public int DynamicAvailable;
        public int GroupCount;
        public int PrivilegeCount;
        public Luid ModifiedId;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct SidAndAttributes
    {
        public IntPtr Sid;
        public uint Attributes;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct TokenGroupsHeader
    {
        public uint GroupCount;
        public SidAndAttributes FirstGroup;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true, SetLastError = true)]
    internal static extern SafePipeHandle CreateNamedPipeW(
        string pipeName,
        uint openMode,
        uint pipeMode,
        uint maxInstances,
        uint outBufferSize,
        uint inBufferSize,
        uint defaultTimeout,
        ref SecurityAttributes securityAttributes);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool GetNamedPipeClientProcessId(SafePipeHandle pipe, out uint clientProcessId);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool GetNamedPipeClientSessionId(SafePipeHandle pipe, out uint clientSessionId);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool GetNamedPipeServerProcessId(SafePipeHandle pipe, out uint serverProcessId);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool GetNamedPipeServerSessionId(SafePipeHandle pipe, out uint serverSessionId);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool ProcessIdToSessionId(uint processId, out uint sessionId);

    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern SafeProcessHandle OpenProcess(uint desiredAccess, bool inheritHandle, uint processId);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool OpenProcessToken(
        SafeProcessHandle processHandle,
        uint desiredAccess,
        out SafeAccessTokenHandle tokenHandle);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool OpenThreadToken(
        IntPtr threadHandle,
        uint desiredAccess,
        [MarshalAs(UnmanagedType.Bool)] bool openAsSelf,
        out SafeAccessTokenHandle tokenHandle);

    [DllImport("kernel32.dll")]
    internal static extern IntPtr GetCurrentThread();

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool QueryFullProcessImageNameW(
        SafeProcessHandle processHandle,
        uint flags,
        StringBuilder imagePath,
        ref uint size);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool GetTokenInformation(
        SafeAccessTokenHandle tokenHandle,
        int tokenInformationClass,
        IntPtr tokenInformation,
        int tokenInformationLength,
        out int returnLength);

    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, ExactSpelling = true, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool ConvertStringSecurityDescriptorToSecurityDescriptorW(
        string stringSecurityDescriptor,
        int stringSdRevision,
        out IntPtr securityDescriptor,
        out uint securityDescriptorSize);

    [DllImport("kernel32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool LocalFree(IntPtr memory);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool PeekNamedPipe(
        SafePipeHandle pipe,
        IntPtr buffer,
        uint bufferSize,
        IntPtr bytesRead,
        out uint totalBytesAvailable,
        IntPtr bytesLeftThisMessage);

    internal static Exception LastError(string operation) =>
        new Win32Exception(Marshal.GetLastWin32Error(), operation);

    internal static SafePipeHandle CreateSecurePipe(
        string pipeName,
        IReadOnlyCollection<string> allowedClientSids,
        string serviceSid,
        bool firstPipeInstance)
    {
        if (!OperatingSystem.IsWindows())
        {
            throw new PlatformNotSupportedException("Windows named pipes are required.");
        }

        var aceParts = new List<string>
        {
            "(A;;GA;;;SY)",
            $"(A;;GA;;;{new SecurityIdentifier(serviceSid).Value})",
        };
        foreach (var sidText in allowedClientSids.Distinct(StringComparer.OrdinalIgnoreCase))
        {
            var sid = new SecurityIdentifier(sidText);
            aceParts.Add($"(A;;GRGW;;;{sid.Value})");
        }

        string sddl = "D:P" + string.Concat(aceParts);
        if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(
                sddl,
                SddlRevision1,
                out var descriptor,
                out _))
        {
            throw LastError("Could not create the named pipe security descriptor.");
        }

        try
        {
            var attributes = new SecurityAttributes
            {
                Length = Marshal.SizeOf<SecurityAttributes>(),
                SecurityDescriptor = descriptor,
                InheritHandle = false,
            };
            uint openMode = PipeAccessDuplex | FileFlagOverlapped;
            if (firstPipeInstance)
            {
                openMode |= FileFlagFirstPipeInstance;
            }
            var pipe = CreateNamedPipeW(
                pipeName,
                openMode,
                PipeTypeMessage | PipeReadModeByte | PipeWait | PipeRejectRemoteClients,
                ProtocolLimits.MaxConcurrentConnections,
                ProtocolLimits.PipeBufferBytes,
                ProtocolLimits.PipeBufferBytes,
                0,
                ref attributes);
            if (pipe.IsInvalid)
            {
                Exception error = LastError("Could not create the capture named pipe.");
                pipe.Dispose();
                throw error;
            }
            return pipe;
        }
        finally
        {
            _ = LocalFree(descriptor);
        }
    }
}
