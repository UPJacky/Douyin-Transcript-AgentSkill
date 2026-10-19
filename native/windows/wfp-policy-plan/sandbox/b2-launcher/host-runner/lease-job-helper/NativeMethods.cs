using System.Runtime.InteropServices;
using System.Text;
using DouyinTranscript.CapturePipe;
using Microsoft.Win32.SafeHandles;

namespace DouyinTranscript.LeaseJobHelper;

internal sealed class SafeNativeHandle : SafeHandleZeroOrMinusOneIsInvalid
{
    internal SafeNativeHandle() : base(true) { }
    internal SafeNativeHandle(IntPtr handle, bool ownsHandle = true) : base(ownsHandle) => SetHandle(handle);
    protected override bool ReleaseHandle() => NativeMethods.CloseHandle(handle);
}

internal static class NativeMethods
{
    internal const int ErrorInsufficientBuffer = 122;
    internal const int ErrorNotAllAssigned = 1300;
    internal const int ErrorAlreadyMember = 1378;
    internal const int ErrorNoSuchUser = 1317;
    internal const int ErrorNotFound = 1168;
    internal const int ErrorSuccess = 0;
    internal const int ErrorAccessDenied = 5;
    internal const int ErrorAlreadyExists = 183;

    internal const uint TokenQuery = 0x0008;
    internal const uint TokenDuplicate = 0x0002;
    internal const uint TokenAssignPrimary = 0x0001;
    internal const uint TokenAdjustPrivileges = 0x0020;
    internal const uint TokenAdjustDefault = 0x0080;
    internal const uint TokenAdjustSessionId = 0x0100;
    internal const uint TokenImpersonateAccess = 0x0004;
    internal const uint TokenAllForLaunch = TokenQuery | TokenDuplicate | TokenAssignPrimary
        | TokenAdjustPrivileges | TokenAdjustDefault | TokenAdjustSessionId;

    internal const int TokenUser = 1;
    internal const int TokenGroups = 2;
    internal const int TokenPrivilegesClass = 3;
    internal const int TokenElevation = 20;
    internal const int TokenType = 8;
    internal const int TokenElevationType = 18;
    internal const int TokenRestrictedSids = 11;
    internal const int TokenIntegrityLevel = 25;
    internal const int TokenSessionId = 12;
    internal const uint CreateRestrictedTokenDisableMaxPrivilege = 0x00000001;
    internal const uint GroupEnabled = 0x00000004;
    internal const uint GroupUseForDenyOnly = 0x00000010;
    internal const uint GroupLogonId = 0xC0000000;
    internal const int SidTypeUser = 1;
    internal const uint PrivilegeEnabled = 0x00000002;
    internal const uint MandatoryLabelIntegrityEnabled = 0x00000020;

    internal const uint Logon32LogonInteractive = 2;
    internal const uint Logon32ProviderDefault = 0;
    internal const int SecurityImpersonation = 2;
    internal const int TokenImpersonation = 2;
    internal const int TokenPrimary = 1;

    internal const uint CreateSuspended = 0x00000004;
    internal const uint CreateUnicodeEnvironment = 0x00000400;
    internal const uint CreateNoWindow = 0x08000000;
    internal const uint ExtendedStartupInfoPresent = 0x00080000;
    internal const uint StartfUseShowWindow = 0x00000001;
    internal const uint StartfUseStdHandles = 0x00000100;
    internal const short SwHide = 0;

    internal const uint HandleFlagInherit = 0x00000001;
    internal const uint ProcThreadAttributeHandleList = 0x00020002;

    internal const uint GenericRead = 0x80000000;
    internal const uint FileShareRead = 0x00000001;
    internal const uint FileShareWrite = 0x00000002;
    internal const uint FileShareDelete = 0x00000004;
    internal const uint OpenExisting = 3;
    internal const uint FileAttributeNormal = 0x00000080;
    internal const uint FileReadAttributes = 0x00000080;
    internal const uint FileFlagBackupSemantics = 0x02000000;
    internal const uint JobObjectAssociateCompletionPortInformation = 7;
    internal const uint DuplicateSameAccess = 0x00000002;
    internal const uint SecurityInformationDacl = 0x00000004;
    internal const uint ProtectedDaclSecurityInformation = 0x80000000;
    internal const uint SeFileObject = 1;
    internal const uint GrantAccess = 1;
    internal const uint FileModifyRights = 0x001301BF;
    internal const uint FileAllAccess = 0x001F01FF;
    internal const uint ObjectInheritAce = 0x00000001;
    internal const uint ContainerInheritAce = 0x00000002;
    internal const uint TrusteeIsSid = 0;
    internal const uint TrusteeIsUser = 1;
    internal const int UoiName = 2;
    internal const uint SecurityDescriptorRevision = 1;

    internal const uint ProcessQueryLimitedInformation = 0x00001000;
    internal const uint ProcessQueryInformation = 0x00000400;
    internal const uint ProcessSynchronize = 0x00100000;
    internal const int ProcessBasicInformationClass = 0;
    internal const uint Th32csSnapProcess = 0x00000002;
    internal const uint WaitObject0 = 0;
    internal const uint WaitTimeout = 258;
    internal const uint StillActive = 259;

    internal const uint UfScript = 0x0001;
    internal const uint UfDontExpirePasswd = 0x10000;
    internal const uint UserPrivUser = 1;
    internal const uint WtsActive = 0;
    internal const uint WtsDisconnected = 4;
    internal const int WtsCurrentServerHandle = 0;

    [StructLayout(LayoutKind.Sequential)]
    internal struct StartupInfo
    {
        public int Size;
        public IntPtr Reserved;
        public IntPtr Desktop;
        public IntPtr Title;
        public uint X;
        public uint Y;
        public uint XSize;
        public uint YSize;
        public uint XCountChars;
        public uint YCountChars;
        public uint FillAttribute;
        public uint Flags;
        public short ShowWindow;
        public short Reserved2Size;
        public IntPtr Reserved2;
        public IntPtr StandardInput;
        public IntPtr StandardOutput;
        public IntPtr StandardError;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct StartupInfoEx
    {
        public StartupInfo StartupInfo;
        public IntPtr AttributeList;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct ProcessInformation
    {
        public IntPtr Process;
        public IntPtr Thread;
        public uint ProcessId;
        public uint ThreadId;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct SecurityAttributes
    {
        public int Length;
        public IntPtr SecurityDescriptor;
        [MarshalAs(UnmanagedType.Bool)] public bool InheritHandle;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct UserInfo1Raw
    {
        public IntPtr Name;
        public IntPtr Password;
        public uint PasswordAge;
        public uint Privilege;
        public IntPtr HomeDirectory;
        public IntPtr Comment;
        public uint Flags;
        public IntPtr ScriptPath;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct LocalGroupMembersInfo0
    {
        public IntPtr Sid;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct SidAndAttributes
    {
        public IntPtr Sid;
        public uint Attributes;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct TokenMandatoryLabel
    {
        public SidAndAttributes Label;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct UserModalsInfo2
    {
        public IntPtr DomainName;
        public IntPtr DomainId;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct TokenGroupsHeader
    {
        public uint GroupCount;
        public SidAndAttributes FirstGroup;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct GenericMapping
    {
        public uint GenericRead;
        public uint GenericWrite;
        public uint GenericExecute;
        public uint GenericAll;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct ProfileInfo
    {
        public int Size;
        public int Flags;
        public IntPtr UserName;
        public IntPtr ProfilePath;
        public IntPtr DefaultPath;
        public IntPtr ServerName;
        public IntPtr PolicyPath;
        public IntPtr ProfileHandle;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct WtsSessionInfo
    {
        public int SessionId;
        public IntPtr WinStationName;
        public int State;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct Luid
    {
        public uint LowPart;
        public int HighPart;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct LuidAndAttributes
    {
        public Luid Luid;
        public uint Attributes;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct TokenPrivileges
    {
        public uint PrivilegeCount;
        public LuidAndAttributes Privileges;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct JobObjectAssociateCompletionPort
    {
        public IntPtr CompletionKey;
        public IntPtr CompletionPort;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct Trustee
    {
        public IntPtr MultipleTrustee;
        public uint MultipleTrusteeOperation;
        public uint TrusteeForm;
        public uint TrusteeType;
        public IntPtr Name;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct ExplicitAccess
    {
        public uint AccessPermissions;
        public uint AccessMode;
        public uint Inheritance;
        public Trustee Trustee;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    internal struct ProcessEntry32
    {
        public uint Size;
        public uint Usage;
        public uint ProcessId;
        public UIntPtr DefaultHeapId;
        public uint ModuleId;
        public uint ThreadCount;
        public uint ParentProcessId;
        public int BasePriority;
        public uint Flags;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)] public string ExecutableFile;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct ProcessBasicInformation
    {
        public int ExitStatus;
        public IntPtr PebBaseAddress;
        public UIntPtr AffinityMask;
        public int BasePriority;
        public UIntPtr UniqueProcessId;
        public UIntPtr InheritedFromUniqueProcessId;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct ByHandleFileInformation
    {
        public uint FileAttributes;
        public System.Runtime.InteropServices.ComTypes.FILETIME CreationTime;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastAccessTime;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastWriteTime;
        public uint VolumeSerialNumber;
        public uint FileSizeHigh;
        public uint FileSizeLow;
        public uint NumberOfLinks;
        public uint FileIndexHigh;
        public uint FileIndexLow;
    }

    [DllImport("advapi32.dll", EntryPoint = "LogonUserW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern unsafe bool LogonUser(
        string userName,
        string domain,
        char* password,
        uint logonType,
        uint logonProvider,
        out SafeAccessTokenHandle token);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool DuplicateTokenEx(
        SafeAccessTokenHandle existingToken,
        uint desiredAccess,
        IntPtr tokenAttributes,
        int impersonationLevel,
        int tokenType,
        out SafeAccessTokenHandle newToken);

    [DllImport("advapi32.dll", EntryPoint = "CheckTokenMembership", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool CheckTokenMembership(
        SafeAccessTokenHandle tokenHandle,
        IntPtr sidToCheck,
        [MarshalAs(UnmanagedType.Bool)] out bool isMember);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool OpenProcessToken(IntPtr processHandle, uint desiredAccess, out SafeAccessTokenHandle tokenHandle);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool GetTokenInformation(
        SafeAccessTokenHandle tokenHandle,
        int tokenInformationClass,
        IntPtr tokenInformation,
        int tokenInformationLength,
        out int returnLength);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool AccessCheck(
        IntPtr securityDescriptor,
        SafeAccessTokenHandle clientToken,
        uint desiredAccess,
        ref GenericMapping genericMapping,
        IntPtr privilegeSet,
        ref uint privilegeSetLength,
        out uint grantedAccess,
        [MarshalAs(UnmanagedType.Bool)] out bool accessStatus);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool SetTokenInformation(
        SafeAccessTokenHandle tokenHandle,
        int tokenInformationClass,
        ref uint tokenInformation,
        int tokenInformationLength);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool SetTokenInformation(
        SafeAccessTokenHandle tokenHandle,
        int tokenInformationClass,
        IntPtr tokenInformation,
        int tokenInformationLength);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool CreateRestrictedToken(
        SafeAccessTokenHandle existingToken,
        uint flags,
        uint disableSidCount,
        IntPtr sidsToDisable,
        uint deletePrivilegeCount,
        IntPtr privilegesToDelete,
        uint restrictedSidCount,
        IntPtr sidsToRestrict,
        out SafeAccessTokenHandle restrictedToken);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool IsTokenRestricted(SafeAccessTokenHandle tokenHandle);

    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool LookupPrivilegeValue(string? systemName, string name, out Luid luid);

    [DllImport("advapi32.dll", EntryPoint = "LookupPrivilegeNameW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool LookupPrivilegeName(string? systemName, ref Luid luid, System.Text.StringBuilder name, ref uint nameLength);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool AdjustTokenPrivileges(
        SafeAccessTokenHandle tokenHandle,
        [MarshalAs(UnmanagedType.Bool)] bool disableAllPrivileges,
        ref TokenPrivileges newState,
        int bufferLength,
        out TokenPrivileges previousState,
        out int returnLength);

    [DllImport("advapi32.dll", EntryPoint = "CreateProcessAsUserW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool CreateProcessAsUser(
        SafeAccessTokenHandle token,
        string applicationName,
        System.Text.StringBuilder commandLine,
        IntPtr processAttributes,
        IntPtr threadAttributes,
        [MarshalAs(UnmanagedType.Bool)] bool inheritHandles,
        uint creationFlags,
        IntPtr environment,
        string? currentDirectory,
        ref StartupInfoEx startupInfo,
        out ProcessInformation processInformation);

    [DllImport("userenv.dll", EntryPoint = "LoadUserProfileW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool LoadUserProfile(SafeAccessTokenHandle token, ref ProfileInfo profileInfo);

    [DllImport("userenv.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool UnloadUserProfile(SafeAccessTokenHandle token, SafeNativeHandle profileHandle);

    [DllImport("userenv.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool CreateEnvironmentBlock(out IntPtr environment, SafeAccessTokenHandle token, [MarshalAs(UnmanagedType.Bool)] bool inherit);

    [DllImport("userenv.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool DestroyEnvironmentBlock(IntPtr environment);

    [DllImport("userenv.dll", EntryPoint = "GetUserProfileDirectoryW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool GetUserProfileDirectory(SafeAccessTokenHandle token, System.Text.StringBuilder profileDirectory, ref uint size);

    [DllImport("wtsapi32.dll", EntryPoint = "WTSEnumerateSessionsW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool WtsEnumerateSessions(IntPtr server, int reserved, int version, out IntPtr sessions, out int count);

    [DllImport("wtsapi32.dll", EntryPoint = "WTSFreeMemory")]
    internal static extern void WtsFreeMemory(IntPtr memory);

    [DllImport("kernel32.dll", EntryPoint = "WTSGetActiveConsoleSessionId")]
    internal static extern uint WtsGetActiveConsoleSessionId();

    [DllImport("wtsapi32.dll", EntryPoint = "WTSQueryUserToken", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool WtsQueryUserToken(uint sessionId, out SafeAccessTokenHandle token);

    [DllImport("netapi32.dll", EntryPoint = "NetUserAdd", CharSet = CharSet.Unicode)]
    internal static extern int NetUserAdd(string? serverName, int level, IntPtr buffer, out uint parameterError);

    [DllImport("netapi32.dll", EntryPoint = "NetUserDel", CharSet = CharSet.Unicode)]
    internal static extern int NetUserDel(string? serverName, string userName);

    [DllImport("netapi32.dll", EntryPoint = "NetLocalGroupAddMembers", CharSet = CharSet.Unicode)]
    internal static extern int NetLocalGroupAddMembers(string? serverName, string groupName, int level, IntPtr buffer, uint totalEntries);

    [DllImport("netapi32.dll", EntryPoint = "NetUserGetLocalGroups", CharSet = CharSet.Unicode)]
    internal static extern int NetUserGetLocalGroups(
        string? serverName,
        string userName,
        int level,
        uint flags,
        out IntPtr buffer,
        uint preferredMaximumLength,
        out uint entriesRead,
        out uint totalEntries);

    [DllImport("netapi32.dll", EntryPoint = "NetUserModalsGet", CharSet = CharSet.Unicode)]
    internal static extern int NetUserModalsGet(string? serverName, int level, out IntPtr buffer);

    [DllImport("advapi32.dll", EntryPoint = "ConvertSidToStringSidW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool ConvertSidToStringSid(IntPtr sid, out IntPtr stringSid);

    [DllImport("advapi32.dll", EntryPoint = "LookupAccountNameW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool LookupAccountName(
        string? systemName,
        string accountName,
        IntPtr sid,
        ref uint sidSize,
        System.Text.StringBuilder referencedDomainName,
        ref uint domainNameSize,
        out int use);

    [DllImport("advapi32.dll", EntryPoint = "LookupAccountSidW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool LookupAccountSid(
        string? systemName,
        IntPtr sid,
        System.Text.StringBuilder name,
        ref uint nameSize,
        System.Text.StringBuilder referencedDomainName,
        ref uint domainNameSize,
        out int use);

    [DllImport("advapi32.dll", EntryPoint = "CreateWellKnownSid", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool CreateWellKnownSid(int wellKnownSidType, IntPtr domainSid, IntPtr sid, ref uint sidSize);

    [DllImport("user32.dll", SetLastError = true)]
    internal static extern IntPtr GetProcessWindowStation();

    [DllImport("user32.dll", SetLastError = true)]
    internal static extern IntPtr GetThreadDesktop(uint threadId);

    [DllImport("kernel32.dll")]
    internal static extern uint GetCurrentThreadId();

    [DllImport("user32.dll", EntryPoint = "GetUserObjectInformationW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool GetUserObjectInformation(IntPtr handle, int index, IntPtr information, int length, out int needed);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool CreatePipe(out SafeFileHandle readPipe, out SafeFileHandle writePipe, ref SecurityAttributes attributes, uint size);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool SetHandleInformation(SafeFileHandle handle, uint mask, uint flags);

    [DllImport("kernel32.dll", EntryPoint = "CreateFileW", CharSet = CharSet.Unicode, SetLastError = true)]
    internal static extern SafeFileHandle CreateFile(
        string fileName,
        uint desiredAccess,
        uint shareMode,
        ref SecurityAttributes securityAttributes,
        uint creationDisposition,
        uint flagsAndAttributes,
        IntPtr templateFile);

    [DllImport("kernel32.dll", EntryPoint = "CreateFileW", CharSet = CharSet.Unicode, SetLastError = true)]
    internal static extern SafeFileHandle OpenDirectoryHandle(
        string fileName,
        uint desiredAccess,
        uint shareMode,
        IntPtr securityAttributes,
        uint creationDisposition,
        uint flagsAndAttributes,
        IntPtr templateFile);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool GetFileInformationByHandle(SafeFileHandle file, out ByHandleFileInformation information);

    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern bool InitializeProcThreadAttributeList(IntPtr attributeList, int attributeCount, int flags, ref IntPtr size);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool UpdateProcThreadAttribute(
        IntPtr attributeList,
        uint flags,
        IntPtr attribute,
        IntPtr value,
        IntPtr size,
        IntPtr previousValue,
        IntPtr returnSize);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool DuplicateHandle(IntPtr sourceProcess, IntPtr sourceHandle, IntPtr targetProcess,
        out SafeNativeHandle targetHandle, uint desiredAccess, [MarshalAs(UnmanagedType.Bool)] bool inheritHandle,
        uint options);

    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern IntPtr CreateIoCompletionPort(IntPtr fileHandle, IntPtr existingCompletionPort,
        IntPtr completionKey, uint numberOfConcurrentThreads);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool GetQueuedCompletionStatus(SafeNativeHandle completionPort, out uint message,
        out IntPtr completionKey, out IntPtr overlapped, uint milliseconds);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool SetInformationJobObject(SafeJobObjectHandle job, uint informationClass,
        ref JobObjectAssociateCompletionPort information, uint informationLength);

    [DllImport("kernel32.dll")]
    internal static extern void DeleteProcThreadAttributeList(IntPtr attributeList);

    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern SafeNativeHandle CreateToolhelp32Snapshot(uint flags, uint processId);

    [DllImport("kernel32.dll", EntryPoint = "Process32FirstW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool Process32First(SafeNativeHandle snapshot, ref ProcessEntry32 entry);

    [DllImport("kernel32.dll", EntryPoint = "Process32NextW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool Process32Next(SafeNativeHandle snapshot, ref ProcessEntry32 entry);

    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern SafeProcessHandle OpenProcess(uint desiredAccess, [MarshalAs(UnmanagedType.Bool)] bool inheritHandle, uint processId);

    [DllImport("kernel32.dll", EntryPoint = "QueryFullProcessImageNameW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool QueryFullProcessImageName(SafeProcessHandle process, uint flags, StringBuilder imageName, ref uint size);

    [DllImport("ntdll.dll")]
    internal static extern int NtQueryInformationProcess(SafeProcessHandle process, int processInformationClass,
        out ProcessBasicInformation processInformation, int processInformationLength, out int returnLength);

    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern uint WaitForSingleObject(SafeProcessHandle handle, uint milliseconds);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool GetExitCodeProcess(SafeProcessHandle process, out uint exitCode);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool CloseHandle(IntPtr handle);

    [DllImport("kernel32.dll")]
    internal static extern IntPtr GetCurrentProcess();

    [DllImport("kernel32.dll", EntryPoint = "LocalFree")]
    internal static extern IntPtr LocalFree(IntPtr memory);

    [DllImport("netapi32.dll")]
    internal static extern int NetApiBufferFree(IntPtr buffer);

    [DllImport("advapi32.dll", EntryPoint = "GetNamedSecurityInfoW", CharSet = CharSet.Unicode)]
    internal static extern int GetNamedSecurityInfo(string objectName, uint objectType, uint securityInfo,
        out IntPtr owner, out IntPtr group, out IntPtr dacl, out IntPtr sacl, out IntPtr securityDescriptor);

    [DllImport("advapi32.dll", EntryPoint = "SetEntriesInAclW", CharSet = CharSet.Unicode)]
    internal static extern int SetEntriesInAcl(uint count, IntPtr entries, IntPtr oldAcl, out IntPtr newAcl);

    [DllImport("advapi32.dll", EntryPoint = "SetNamedSecurityInfoW", CharSet = CharSet.Unicode)]
    internal static extern int SetNamedSecurityInfo(string objectName, uint objectType, uint securityInfo,
        IntPtr owner, IntPtr group, IntPtr dacl, IntPtr sacl);

    [DllImport("advapi32.dll", EntryPoint = "ConvertSecurityDescriptorToStringSecurityDescriptorW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool ConvertSecurityDescriptorToStringSecurityDescriptor(IntPtr securityDescriptor,
        uint revision, uint securityInfo, out IntPtr stringSecurityDescriptor, out uint stringLength);

    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern uint GetLengthSid(IntPtr sid);

}
