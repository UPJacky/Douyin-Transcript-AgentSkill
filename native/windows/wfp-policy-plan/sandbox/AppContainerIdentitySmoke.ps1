param(
    [string]$ResultPath = '',
    [string]$ChromiumPath = '',
    [switch]$ChromiumOnly,
    [switch]$IncludeChromiumPageProbe,
    [switch]$ChromiumPageOnly,
    [switch]$DisableHeadlessCrashReporter
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not $ChromiumOnly) {
    throw 'AppContainer WFP mutation smoke is disabled until the Sandbox guest boundary can be independently authenticated.'
}
if ($ChromiumPageOnly -and -not $IncludeChromiumPageProbe) {
    throw 'ChromiumPageOnly requires IncludeChromiumPageProbe.'
}
if ($DisableHeadlessCrashReporter -and -not $IncludeChromiumPageProbe) {
    throw 'DisableHeadlessCrashReporter requires IncludeChromiumPageProbe.'
}

if ([string]::IsNullOrWhiteSpace($ResultPath)) {
    $ResultPath = if ($ChromiumOnly) { 'C:\sandbox-results\chromium-appcontainer-diagnostic.json' } else { 'C:\sandbox-results\appcontainer-identity-smoke.json' }
}

$result = [ordered]@{
    reportKind = if ($ChromiumOnly) { 'chromium-appcontainer-diagnostic' } else { 'wfp-appcontainer-identity-and-filter-prerequisite-smoke' }
    capturedAtUtc = [DateTime]::UtcNow.ToString('o')
    validationScope = if ($ChromiumOnly) { 'chromium-appcontainer-diagnostics' } else { 'wfp-appcontainer-smoke' }
    runContext = $null
    userIdentity = $null
    userSid = $null
    sessionId = $null
    isSystem = $false
    wfpLayoutSizes = $null
    wfpLayoutOffsets = $null
    wfpLayoutMatchesKnownX64 = $false
    profilesCreated = 0
    distinctPackageSids = $false
    processCreated = $false
    childPackageSidMatches = $false
    childExitCode = $null
    failureStage = $null
    loopbackExemptionAddExitCode = $null
    loopbackExemptionDeleteExitCode = $null
    loopbackWithoutExemptionAllowed = $null
    loopbackWithoutExemptionChildExitCode = $null
    loopbackExemptionAllowsConnection = $null
    loopbackExemptionChildExitCode = $null
    externalBaselineAttempted = $false
    externalBaselineConnected = $null
    externalBaselineExitCode = $null
    externalTargetIpv4Address = $null
    secondProfileBaselineConnected = $null
    secondProfileBaselineExitCode = $null
    wfpEngineOpenCode = $null
    wfpSubLayerAddCode = $null
    packageSidFilterAddCode = $null
    packageSidFilterId = $null
    filteredFirstProfileBlocked = $null
    filteredFirstProfileExitCode = $null
    filteredSecondProfileAllowed = $null
    filteredSecondProfileExitCode = $null
    wfpEngineCloseCode = $null
    firstProfileAllowedAfterClose = $null
    firstProfileAfterCloseExitCode = $null
    chromiumProbeAttempted = $false
    chromiumPageProbeRequested = [bool]$IncludeChromiumPageProbe
    chromiumPageOnly = [bool]$ChromiumPageOnly
    chromiumHeadlessCrashReporterDisabled = [bool]$DisableHeadlessCrashReporter
    chromiumProbes = [ordered]@{
        normalVersion = $null
        noSandboxVersion = $null
        page = $null
    }
    chromiumCrashpadArtifacts = @()
    chromiumApplicationEvents = @()
    chromiumDiagnosticArtifactDirectory = $null
    chromiumDiagnosticsCollected = $false
    chromiumDiagnosticsCollectionErrors = [System.Collections.Generic.List[string]]::new()
    chromiumProcessCreated = $false
    chromiumTokenMatchesProfile = $false
    chromiumProfilePackageSid = $null
    chromiumStagedToGuest = $false
    chromiumStagedFileCount = 0
    chromiumReadAclEntriesApplied = 0
    chromiumVersionExitCode = $null
    chromiumNoSandboxVersionExitCode = $null
    chromiumExitCode = $null
    chromiumProcessId = $null
    chromiumLogTail = @()
    chromiumContext = $null
    status = 'not_started'
    errors = [System.Collections.Generic.List[string]]::new()
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$result.isSystem = $identity.User.Value -eq 'S-1-5-18'
$result.runContext = if ($result.isSystem) { 'SYSTEM' } else { 'non-system' }
$result.userIdentity = $identity.Name
$result.userSid = $identity.User.Value
$result.sessionId = [Diagnostics.Process]::GetCurrentProcess().SessionId
$source = @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

public sealed class AppContainerChildResult
{
    public bool Created { get; set; }
    public bool PackageSidMatches { get; set; }
    public int ProcessId { get; set; }
    public int? ExitCode { get; set; }
    public bool TimedOut { get; set; }
    public int Win32Error { get; set; }
    public string CleanupError { get; set; }
    public string PackageSid { get; set; }
    public string ChildPackageSid { get; set; }
}

public static class AppContainerNative
{
    private const uint ProcThreadAttributeSecurityCapabilities = 0x00020009;
    private const uint ProcThreadAttributeHandleList = 0x00020002;
    private const uint ExtendedStartupInfoPresent = 0x00080000;
    private const uint CreateUnicodeEnvironment = 0x00000400;
    private const uint CreateNoWindow = 0x08000000;
    private const uint TokenQuery = 0x0008;
    private const int TokenAppContainerSid = 31;
    private const uint GroupEnabled = 0x00000004;
    private const uint WaitTimeout = 0x00000102;
    private const uint GenericRead = 0x80000000;
    private const uint GenericWrite = 0x40000000;
    private const uint FileShareRead = 0x00000001;
    private const uint FileShareWrite = 0x00000002;
    private const uint CreateAlways = 2;
    private const uint OpenExisting = 3;
    private const uint FileAttributeNormal = 0x00000080;
    private const uint StartfUseStdHandles = 0x00000100;

    [StructLayout(LayoutKind.Sequential)]
    private struct SecurityAttributes
    {
        public int Length;
        public IntPtr SecurityDescriptor;
        [MarshalAs(UnmanagedType.Bool)] public bool InheritHandle;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct SidAndAttributes { public IntPtr Sid; public uint Attributes; }

    [StructLayout(LayoutKind.Sequential)]
    private struct SecurityCapabilities
    {
        public IntPtr AppContainerSid;
        public IntPtr Capabilities;
        public uint CapabilityCount;
        public uint Reserved;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct StartupInfo
    {
        public uint Cb;
        public string Reserved;
        public string Desktop;
        public string Title;
        public uint X;
        public uint Y;
        public uint XSize;
        public uint YSize;
        public uint XCountChars;
        public uint YCountChars;
        public uint FillAttribute;
        public uint Flags;
        public ushort ShowWindow;
        public ushort Reserved2Size;
        public IntPtr Reserved2;
        public IntPtr StdInput;
        public IntPtr StdOutput;
        public IntPtr StdError;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct StartupInfoEx { public StartupInfo StartupInfo; public IntPtr AttributeList; }

    [StructLayout(LayoutKind.Sequential)]
    private struct ProcessInformation
    {
        public IntPtr Process;
        public IntPtr Thread;
        public uint ProcessId;
        public uint ThreadId;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct TokenAppContainerInformation { public IntPtr TokenAppContainer; }

    [StructLayout(LayoutKind.Sequential)]
    private struct WfpDisplayData { public IntPtr Name; public IntPtr Description; }

    [StructLayout(LayoutKind.Sequential)]
    private struct WfpByteBlob { public uint Size; public IntPtr Data; }

    [StructLayout(LayoutKind.Explicit, Size = 16)]
    private struct WfpValue0
    {
        [FieldOffset(0)] public uint Type;
        [FieldOffset(8)] public byte UInt8;
    }

    [StructLayout(LayoutKind.Explicit, Size = 16)]
    private struct WfpConditionValue0
    {
        [FieldOffset(0)] public uint Type;
        [FieldOffset(8)] public IntPtr Sid;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct WfpFilterCondition0
    {
        public Guid FieldKey;
        public uint MatchType;
        public WfpConditionValue0 ConditionValue;
    }

    [StructLayout(LayoutKind.Explicit, Size = 20)]
    private struct WfpAction0
    {
        [FieldOffset(0)] public uint Type;
        [FieldOffset(4)] public Guid FilterType;
    }

    [StructLayout(LayoutKind.Explicit, Size = 16)]
    private struct WfpFilterContext { [FieldOffset(0)] public ulong RawContext; }

    [StructLayout(LayoutKind.Sequential)]
    private struct WfpSession0
    {
        public Guid SessionKey;
        public WfpDisplayData DisplayData;
        public uint Flags;
        public uint TxnWaitTimeoutInMSec;
        public uint ProcessId;
        public IntPtr Sid;
        public IntPtr Username;
        public int KernelMode;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct WfpSubLayer0
    {
        public Guid SubLayerKey;
        public WfpDisplayData DisplayData;
        public uint Flags;
        public IntPtr ProviderKey;
        public WfpByteBlob ProviderData;
        public ushort Weight;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct WfpFilter0
    {
        public Guid FilterKey;
        public WfpDisplayData DisplayData;
        public uint Flags;
        public IntPtr ProviderKey;
        public WfpByteBlob ProviderData;
        public Guid LayerKey;
        public Guid SubLayerKey;
        public WfpValue0 Weight;
        public uint NumFilterConditions;
        public IntPtr FilterCondition;
        public WfpAction0 Action;
        public WfpFilterContext Context;
        public IntPtr Reserved;
        public ulong FilterId;
        public WfpValue0 EffectiveWeight;
    }

    [DllImport("userenv.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    private static extern int CreateAppContainerProfile(string name, string displayName, string description, IntPtr capabilities, uint capabilityCount, out IntPtr appContainerSid);
    [DllImport("userenv.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    private static extern int DeriveAppContainerSidFromAppContainerName(string name, out IntPtr appContainerSid);
    [DllImport("userenv.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    private static extern int DeleteAppContainerProfile(string name);
    [DllImport("advapi32.dll", EntryPoint = "ConvertStringSidToSidW", CharSet = CharSet.Unicode, SetLastError = true, ExactSpelling = true)]
    private static extern bool ConvertStringSidToSid(string stringSid, out IntPtr sid);
    [DllImport("advapi32.dll", EntryPoint = "ConvertSidToStringSidW", CharSet = CharSet.Unicode, SetLastError = true, ExactSpelling = true)]
    private static extern bool ConvertSidToStringSid(IntPtr sid, out IntPtr stringSid);
    [DllImport("advapi32.dll", SetLastError = true, ExactSpelling = true)]
    private static extern bool OpenProcessToken(IntPtr process, uint desiredAccess, out IntPtr token);
    [DllImport("advapi32.dll", SetLastError = true, ExactSpelling = true)]
    private static extern bool GetTokenInformation(IntPtr token, int tokenInformationClass, IntPtr tokenInformation, int tokenInformationLength, out int returnLength);
    [DllImport("kernel32.dll", SetLastError = true, ExactSpelling = true)]
    private static extern IntPtr LocalFree(IntPtr memory);
    [DllImport("advapi32.dll", SetLastError = true, ExactSpelling = true)]
    private static extern IntPtr FreeSid(IntPtr sid);
    [DllImport("kernel32.dll", SetLastError = true, ExactSpelling = true)]
    private static extern bool InitializeProcThreadAttributeList(IntPtr attributeList, int attributeCount, int flags, ref IntPtr size);
    [DllImport("kernel32.dll", SetLastError = true, ExactSpelling = true)]
    private static extern bool UpdateProcThreadAttribute(IntPtr attributeList, uint flags, IntPtr attribute, IntPtr value, IntPtr size, IntPtr previousValue, IntPtr returnSize);
    [DllImport("kernel32.dll", SetLastError = true, ExactSpelling = true)]
    private static extern void DeleteProcThreadAttributeList(IntPtr attributeList);
    [DllImport("kernel32.dll", EntryPoint = "CreateProcessW", CharSet = CharSet.Unicode, SetLastError = true, ExactSpelling = true)]
    private static extern bool CreateProcess(string applicationName, StringBuilder commandLine, IntPtr processAttributes, IntPtr threadAttributes, bool inheritHandles, uint creationFlags, IntPtr environment, string currentDirectory, ref StartupInfoEx startupInfo, out ProcessInformation processInformation);
    [DllImport("kernel32.dll", SetLastError = true, ExactSpelling = true)]
    private static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);
    [DllImport("kernel32.dll", SetLastError = true, ExactSpelling = true)]
    private static extern bool GetExitCodeProcess(IntPtr process, out uint exitCode);
    [DllImport("kernel32.dll", SetLastError = true, ExactSpelling = true)]
    private static extern bool TerminateProcess(IntPtr process, uint exitCode);
    [DllImport("kernel32.dll", SetLastError = true, ExactSpelling = true)]
    private static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll", EntryPoint = "CreateFileW", CharSet = CharSet.Unicode, SetLastError = true, ExactSpelling = true)]
    private static extern IntPtr CreateFile(string fileName, uint desiredAccess, uint shareMode, ref SecurityAttributes securityAttributes, uint creationDisposition, uint flagsAndAttributes, IntPtr templateFile);
    [DllImport("fwpuclnt.dll", ExactSpelling = true)]
    private static extern uint FwpmEngineOpen0(IntPtr serverName, uint authnService, IntPtr authIdentity, ref WfpSession0 session, out IntPtr engineHandle);
    [DllImport("fwpuclnt.dll", ExactSpelling = true)]
    private static extern uint FwpmSubLayerAdd0(IntPtr engineHandle, ref WfpSubLayer0 subLayer, IntPtr securityDescriptor);
    [DllImport("fwpuclnt.dll", ExactSpelling = true)]
    private static extern uint FwpmFilterAdd0(IntPtr engineHandle, ref WfpFilter0 filter, IntPtr securityDescriptor, out ulong id);
    [DllImport("fwpuclnt.dll", ExactSpelling = true)]
    private static extern uint FwpmEngineClose0(IntPtr engineHandle);

    public static int[] WfpLayoutSizes()
    {
        return new[]
        {
            Marshal.SizeOf(typeof(WfpSession0)),
            Marshal.SizeOf(typeof(WfpSubLayer0)),
            Marshal.SizeOf(typeof(WfpFilter0)),
            Marshal.SizeOf(typeof(WfpFilterCondition0)),
            Marshal.SizeOf(typeof(WfpValue0)),
            Marshal.SizeOf(typeof(WfpConditionValue0)),
        };
    }

    public static int[] WfpLayoutOffsets()
    {
        return new[]
        {
            Marshal.OffsetOf(typeof(WfpConditionValue0), "Sid").ToInt32(),
            Marshal.OffsetOf(typeof(WfpFilterCondition0), "ConditionValue").ToInt32(),
            Marshal.OffsetOf(typeof(WfpFilter0), "FilterCondition").ToInt32(),
            Marshal.OffsetOf(typeof(WfpFilter0), "Action").ToInt32(),
            Marshal.OffsetOf(typeof(WfpFilter0), "Context").ToInt32(),
            Marshal.OffsetOf(typeof(WfpFilter0), "EffectiveWeight").ToInt32(),
        };
    }

    public static string CreateProfile(string name)
    {
        IntPtr sid;
        int hr = CreateAppContainerProfile(name, name, "Disposable WFP identity smoke", IntPtr.Zero, 0, out sid);
        if (hr == unchecked((int)0x800700B7))
            hr = DeriveAppContainerSidFromAppContainerName(name, out sid);
        if (hr < 0) Marshal.ThrowExceptionForHR(hr);
        try { return SidToString(sid); }
        finally { ReleaseAppContainerSid(sid); }
    }

    public static void DeleteProfile(string name)
    {
        int hr = DeleteAppContainerProfile(name);
        if (hr < 0 && hr != unchecked((int)0x80070002)) Marshal.ThrowExceptionForHR(hr);
    }

    public static uint OpenDynamicWfpSession(out IntPtr engine)
    {
        var session = new WfpSession0 { Flags = 1 };
        return FwpmEngineOpen0(IntPtr.Zero, 10, IntPtr.Zero, ref session, out engine);
    }

    public static uint AddDynamicWfpSubLayer(IntPtr engine, Guid subLayerKey)
    {
        IntPtr name = Marshal.StringToHGlobalUni("Disposable AppContainer package SID smoke");
        try
        {
            var subLayer = new WfpSubLayer0
            {
                SubLayerKey = subLayerKey,
                DisplayData = new WfpDisplayData { Name = name },
                Weight = 32767,
            };
            return FwpmSubLayerAdd0(engine, ref subLayer, IntPtr.Zero);
        }
        finally { Marshal.FreeHGlobal(name); }
    }

    public static uint AddPackageSidBlockFilter(IntPtr engine, Guid subLayerKey, string packageSid, out ulong filterId)
    {
        filterId = 0;
        IntPtr sid = IntPtr.Zero;
        IntPtr name = IntPtr.Zero;
        IntPtr conditionMemory = IntPtr.Zero;
        try
        {
            if (!ConvertStringSidToSid(packageSid, out sid)) return unchecked((uint)Marshal.GetLastWin32Error());
            name = Marshal.StringToHGlobalUni("Disposable per-lease AppContainer package SID deny");
            var condition = new WfpFilterCondition0
            {
                FieldKey = new Guid("71BC78FA-F17C-4997-A602-6ABB261F351C"),
                MatchType = 0,
                ConditionValue = new WfpConditionValue0 { Type = 13, Sid = sid },
            };
            conditionMemory = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(WfpFilterCondition0)));
            Marshal.StructureToPtr(condition, conditionMemory, false);

            var filter = new WfpFilter0
            {
                FilterKey = Guid.NewGuid(),
                DisplayData = new WfpDisplayData { Name = name },
                LayerKey = new Guid("C38D57D1-05A7-4C33-904F-7FBCEEE60E82"),
                SubLayerKey = subLayerKey,
                Weight = new WfpValue0 { Type = 1, UInt8 = 8 },
                NumFilterConditions = 1,
                FilterCondition = conditionMemory,
                Action = new WfpAction0 { Type = 0x1001 },
            };
            return FwpmFilterAdd0(engine, ref filter, IntPtr.Zero, out filterId);
        }
        finally
        {
            if (conditionMemory != IntPtr.Zero) Marshal.FreeHGlobal(conditionMemory);
            if (name != IntPtr.Zero) Marshal.FreeHGlobal(name);
            if (sid != IntPtr.Zero) LocalFree(sid);
        }
    }

    public static uint CloseWfpSession(IntPtr engine)
    {
        return FwpmEngineClose0(engine);
    }

    public static AppContainerChildResult LaunchExecutable(string profileName, string[] capabilitySids, string executablePath, string arguments)
    {
        return LaunchExecutable(profileName, capabilitySids, executablePath, arguments, null, null, 20000);
    }

    public static AppContainerChildResult LaunchExecutable(string profileName, string[] capabilitySids, string executablePath, string arguments, string standardOutputPath, string standardErrorPath, int timeoutMilliseconds)
    {
        var result = new AppContainerChildResult();
        IntPtr appSid = IntPtr.Zero;
        IntPtr caps = IntPtr.Zero;
        IntPtr attrList = IntPtr.Zero;
        IntPtr attrBytes = IntPtr.Zero;
        IntPtr securityCapabilitiesPtr = IntPtr.Zero;
        IntPtr handleListMemory = IntPtr.Zero;
        IntPtr stdinHandle = IntPtr.Zero;
        IntPtr stdoutHandle = IntPtr.Zero;
        IntPtr stderrHandle = IntPtr.Zero;
        ProcessInformation pi = new ProcessInformation();
        bool processSignaled = false;
        bool captureOutput = !String.IsNullOrWhiteSpace(standardOutputPath) && !String.IsNullOrWhiteSpace(standardErrorPath);
        try
        {
            int hr = DeriveAppContainerSidFromAppContainerName(profileName, out appSid);
            if (hr < 0) Marshal.ThrowExceptionForHR(hr);
            result.PackageSid = SidToString(appSid);

            if (capabilitySids.Length > 0)
            {
                int itemSize = Marshal.SizeOf(typeof(SidAndAttributes));
                caps = Marshal.AllocHGlobal(checked(itemSize * capabilitySids.Length));
                Marshal.Copy(new byte[checked(itemSize * capabilitySids.Length)], 0, caps, checked(itemSize * capabilitySids.Length));
                for (int i = 0; i < capabilitySids.Length; i++)
                {
                    IntPtr capSid;
                    if (!ConvertStringSidToSid(capabilitySids[i], out capSid)) throw new Win32Exception(Marshal.GetLastWin32Error());
                    Marshal.StructureToPtr(new SidAndAttributes { Sid = capSid, Attributes = GroupEnabled }, IntPtr.Add(caps, i * itemSize), false);
                }
            }

            var securityCapabilities = new SecurityCapabilities
            {
                AppContainerSid = appSid,
                Capabilities = caps,
                CapabilityCount = checked((uint)capabilitySids.Length),
            };
            securityCapabilitiesPtr = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(SecurityCapabilities)));
            Marshal.StructureToPtr(securityCapabilities, securityCapabilitiesPtr, false);

            int attributeCount = captureOutput ? 2 : 1;
            IntPtr required = IntPtr.Zero;
            InitializeProcThreadAttributeList(IntPtr.Zero, attributeCount, 0, ref required);
            if (required == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not size the process attribute list.");
            attrBytes = Marshal.AllocHGlobal(required);
            if (!InitializeProcThreadAttributeList(attrBytes, attributeCount, 0, ref required)) throw new Win32Exception(Marshal.GetLastWin32Error());
            attrList = attrBytes;
            if (!UpdateProcThreadAttribute(attrList, 0, new IntPtr(ProcThreadAttributeSecurityCapabilities), securityCapabilitiesPtr, new IntPtr(Marshal.SizeOf(typeof(SecurityCapabilities))), IntPtr.Zero, IntPtr.Zero))
                throw new Win32Exception(Marshal.GetLastWin32Error());

            var startup = new StartupInfoEx();
            startup.StartupInfo.Cb = checked((uint)Marshal.SizeOf(typeof(StartupInfoEx)));
            startup.AttributeList = attrList;
            if (captureOutput)
            {
                var securityAttributes = new SecurityAttributes
                {
                    Length = Marshal.SizeOf(typeof(SecurityAttributes)),
                    SecurityDescriptor = IntPtr.Zero,
                    InheritHandle = true,
                };
                stdinHandle = CreateFile("NUL", GenericRead, FileShareRead | FileShareWrite, ref securityAttributes, OpenExisting, FileAttributeNormal, IntPtr.Zero);
                stdoutHandle = CreateFile(standardOutputPath, GenericWrite, FileShareRead | FileShareWrite, ref securityAttributes, CreateAlways, FileAttributeNormal, IntPtr.Zero);
                stderrHandle = CreateFile(standardErrorPath, GenericWrite, FileShareRead | FileShareWrite, ref securityAttributes, CreateAlways, FileAttributeNormal, IntPtr.Zero);
                IntPtr invalidHandle = new IntPtr(-1);
                if (stdinHandle == IntPtr.Zero || stdinHandle == invalidHandle) throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not open the child stdin handle.");
                if (stdoutHandle == IntPtr.Zero || stdoutHandle == invalidHandle) throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not open the child stdout capture file.");
                if (stderrHandle == IntPtr.Zero || stderrHandle == invalidHandle) throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not open the child stderr capture file.");

                handleListMemory = Marshal.AllocHGlobal(checked(IntPtr.Size * 3));
                Marshal.WriteIntPtr(handleListMemory, 0, stdinHandle);
                Marshal.WriteIntPtr(handleListMemory, IntPtr.Size, stdoutHandle);
                Marshal.WriteIntPtr(handleListMemory, IntPtr.Size * 2, stderrHandle);
                if (!UpdateProcThreadAttribute(attrList, 0, new IntPtr(ProcThreadAttributeHandleList), handleListMemory, new IntPtr(IntPtr.Size * 3), IntPtr.Zero, IntPtr.Zero))
                    throw new Win32Exception(Marshal.GetLastWin32Error());

                startup.StartupInfo.Flags = StartfUseStdHandles;
                startup.StartupInfo.StdInput = stdinHandle;
                startup.StartupInfo.StdOutput = stdoutHandle;
                startup.StartupInfo.StdError = stderrHandle;
            }

            string exe = executablePath;
            var command = new StringBuilder("\"" + exe + "\" " + arguments);
            if (!CreateProcess(exe, command, IntPtr.Zero, IntPtr.Zero, captureOutput, ExtendedStartupInfoPresent | CreateUnicodeEnvironment | CreateNoWindow, IntPtr.Zero, System.IO.Path.GetDirectoryName(exe), ref startup, out pi))
            {
                result.Win32Error = Marshal.GetLastWin32Error();
                return result;
            }

            result.Created = true;
            result.ProcessId = checked((int)pi.ProcessId);
            result.PackageSid = SidToString(appSid);
            result.ChildPackageSid = ReadProcessPackageSid(pi.Process);
            result.PackageSidMatches = String.Equals(result.PackageSid, result.ChildPackageSid, StringComparison.OrdinalIgnoreCase);

            uint wait = WaitForSingleObject(pi.Process, checked((uint)timeoutMilliseconds));
            if (wait == WaitTimeout)
            {
                result.TimedOut = true;
                result.ExitCode = 124;
                if (!TerminateProcess(pi.Process, 124))
                    result.CleanupError = "Timed-out child could not be terminated: " + new Win32Exception(Marshal.GetLastWin32Error()).Message;
                else if (WaitForSingleObject(pi.Process, 5000) != 0)
                    result.CleanupError = "Timed-out child did not signal after termination: " + new Win32Exception(Marshal.GetLastWin32Error()).Message;
                else
                    processSignaled = true;
            }
            else
            {
                if (wait != 0) throw new Win32Exception(Marshal.GetLastWin32Error());
                processSignaled = true;
                uint exit;
                if (!GetExitCodeProcess(pi.Process, out exit)) throw new Win32Exception(Marshal.GetLastWin32Error());
                result.ExitCode = unchecked((int)exit);
            }
            return result;
        }
        finally
        {
            if (pi.Process != IntPtr.Zero && !processSignaled)
            {
                uint currentWait = WaitForSingleObject(pi.Process, 0);
                if (currentWait == 0)
                {
                    processSignaled = true;
                }
                else if (!TerminateProcess(pi.Process, 125))
                {
                    result.CleanupError = "Child cleanup could not terminate process: " + new Win32Exception(Marshal.GetLastWin32Error()).Message;
                }
                else if (WaitForSingleObject(pi.Process, 5000) != 0)
                {
                    result.CleanupError = "Child cleanup did not observe process exit: " + new Win32Exception(Marshal.GetLastWin32Error()).Message;
                }
                else
                {
                    processSignaled = true;
                }
            }
            if (pi.Thread != IntPtr.Zero) CloseHandle(pi.Thread);
            if (pi.Process != IntPtr.Zero) CloseHandle(pi.Process);
            if (stdinHandle != IntPtr.Zero && stdinHandle != new IntPtr(-1)) CloseHandle(stdinHandle);
            if (stdoutHandle != IntPtr.Zero && stdoutHandle != new IntPtr(-1)) CloseHandle(stdoutHandle);
            if (stderrHandle != IntPtr.Zero && stderrHandle != new IntPtr(-1)) CloseHandle(stderrHandle);
            if (attrList != IntPtr.Zero) DeleteProcThreadAttributeList(attrList);
            if (attrBytes != IntPtr.Zero) Marshal.FreeHGlobal(attrBytes);
            if (handleListMemory != IntPtr.Zero) Marshal.FreeHGlobal(handleListMemory);
            if (securityCapabilitiesPtr != IntPtr.Zero) Marshal.FreeHGlobal(securityCapabilitiesPtr);
            if (caps != IntPtr.Zero)
            {
                for (int i = 0; i < capabilitySids.Length; i++)
                {
                    IntPtr ptr = Marshal.ReadIntPtr(caps, i * Marshal.SizeOf(typeof(SidAndAttributes)));
                    if (ptr != IntPtr.Zero) LocalFree(ptr);
                }
                Marshal.FreeHGlobal(caps);
            }
            if (appSid != IntPtr.Zero) ReleaseAppContainerSid(appSid);
        }
    }

    private static string ReadProcessPackageSid(IntPtr process)
    {
        IntPtr token;
        if (!OpenProcessToken(process, TokenQuery, out token)) throw new Win32Exception(Marshal.GetLastWin32Error());
        try
        {
            int required;
            GetTokenInformation(token, TokenAppContainerSid, IntPtr.Zero, 0, out required);
            if (required <= 0) throw new Win32Exception(Marshal.GetLastWin32Error());
            IntPtr buffer = Marshal.AllocHGlobal(required);
            try
            {
                if (!GetTokenInformation(token, TokenAppContainerSid, buffer, required, out required)) throw new Win32Exception(Marshal.GetLastWin32Error());
                IntPtr sid = Marshal.PtrToStructure<TokenAppContainerInformation>(buffer).TokenAppContainer;
                return sid == IntPtr.Zero ? null : SidToString(sid);
            }
            finally { Marshal.FreeHGlobal(buffer); }
        }
        finally { CloseHandle(token); }
    }

    private static string SidToString(IntPtr sid)
    {
        IntPtr value;
        if (!ConvertSidToStringSid(sid, out value)) throw new Win32Exception(Marshal.GetLastWin32Error());
        try { return Marshal.PtrToStringUni(value); }
        finally { LocalFree(value); }
    }

    private static void ReleaseAppContainerSid(IntPtr sid)
    {
        if (sid != IntPtr.Zero) FreeSid(sid);
    }
}
'@

function New-ChromiumProbeRecord {
    return [ordered]@{
        attempted = $false
        arguments = $null
        created = $false
        processId = $null
        expectedPackageSid = $null
        childPackageSid = $null
        tokenMatchesProfile = $false
        timedOut = $false
        exitCode = $null
        win32Error = $null
        cleanupError = $null
        standardOutput = ''
        standardError = ''
        standardOutputBytes = 0
        standardErrorBytes = 0
        standardOutputTruncated = $false
        standardErrorTruncated = $false
        standardOutputPath = $null
        standardErrorPath = $null
        logPath = $null
        logTail = @()
        userDataDirectory = $null
        errors = [System.Collections.Generic.List[string]]::new()
    }
}

function Read-TextFileBounded {
    param([string]$Path, [int]$MaximumBytes = 65536)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return [pscustomobject]@{ Text = ''; Bytes = 0; Truncated = $false } }
    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete)
    try {
        $totalBytes = $stream.Length
        $truncated = $totalBytes -gt $MaximumBytes
        $length = [int][Math]::Min($totalBytes, $MaximumBytes)
        if ($truncated) { [void]$stream.Seek(-$length, [IO.SeekOrigin]::End) }
        $buffer = [byte[]]::new($length)
        $offset = 0
        while ($offset -lt $length) {
            $read = $stream.Read($buffer, $offset, $length - $offset)
            if ($read -le 0) { break }
            $offset += $read
        }
        $text = [Text.Encoding]::UTF8.GetString($buffer, 0, $offset)
        return [pscustomobject]@{ Text = $text; Bytes = $totalBytes; Truncated = $truncated }
    }
    finally { $stream.Dispose() }
}

function Invoke-ChromiumAppContainerProbe {
    param(
        [string]$ProbeName,
        [string]$ExecutablePath,
        [string]$ProfileName,
        [string]$PackageSid,
        [string]$UserDataDirectory,
        [string]$Arguments
    )

    $probe = New-ChromiumProbeRecord
    $probe.attempted = $true
    $probe.arguments = $Arguments
    $probe.expectedPackageSid = $PackageSid
    $probe.userDataDirectory = $UserDataDirectory
    $probe.standardOutputPath = Join-Path $UserDataDirectory ($ProbeName + '.stdout.txt')
    $probe.standardErrorPath = Join-Path $UserDataDirectory ($ProbeName + '.stderr.txt')
    $probe.logPath = Join-Path $UserDataDirectory 'chrome_debug.log'
    try {
        $child = [AppContainerNative]::LaunchExecutable(
            $ProfileName,
            @('S-1-15-3-1', 'S-1-15-3-2'),
            $ExecutablePath,
            $Arguments,
            $probe.standardOutputPath,
            $probe.standardErrorPath,
            30000
        )
        $probe.created = $child.Created
        if ($child.Created) { $probe.processId = $child.ProcessId }
        $probe.expectedPackageSid = $child.PackageSid
        $probe.childPackageSid = $child.ChildPackageSid
        $probe.tokenMatchesProfile = $child.PackageSidMatches -and $child.ChildPackageSid -eq $PackageSid
        $probe.timedOut = $child.TimedOut
        $probe.exitCode = $child.ExitCode
        if (-not $child.Created) { $probe.win32Error = $child.Win32Error; $probe.errors.Add("CreateProcess failed with Win32 $($child.Win32Error).") }
        if ($child.CleanupError) { $probe.cleanupError = $child.CleanupError; $probe.errors.Add($child.CleanupError) }
        if ($child.Created -and -not $probe.tokenMatchesProfile) { $probe.errors.Add('The child package SID did not match the AppContainer profile.') }
    }
    catch {
        $probe.errors.Add($_.Exception.Message)
    }

    try {
        $stdout = Read-TextFileBounded -Path $probe.standardOutputPath
        $probe.standardOutput = $stdout.Text
        $probe.standardOutputBytes = $stdout.Bytes
        $probe.standardOutputTruncated = $stdout.Truncated
    }
    catch { $probe.errors.Add("Could not read stdout capture: $($_.Exception.Message)") }
    try {
        $stderr = Read-TextFileBounded -Path $probe.standardErrorPath
        $probe.standardError = $stderr.Text
        $probe.standardErrorBytes = $stderr.Bytes
        $probe.standardErrorTruncated = $stderr.Truncated
    }
    catch { $probe.errors.Add("Could not read stderr capture: $($_.Exception.Message)") }
    if (Test-Path -LiteralPath $probe.logPath -PathType Leaf) {
        try { $probe.logTail = @(Get-Content -LiteralPath $probe.logPath -Tail 40 -Encoding UTF8 -ErrorAction Stop) }
        catch { $probe.errors.Add("Could not read Chromium debug log: $($_.Exception.Message)") }
    }
    return $probe
}

$profileNames = [System.Collections.Generic.List[string]]::new()
$loopbackExemptionNames = [System.Collections.Generic.List[string]]::new()
$chromiumUserDataDirectories = [System.Collections.Generic.List[string]]::new()
$listener = $null
$engine = [IntPtr]::Zero
$chromiumProfilePath = $null
$chromiumProfilePathCreated = $false
$chromiumPackagePath = $null
$chromiumPackagePathCreated = $false
$firstName = $null
$secondName = $null
$chromiumDiagnosticStartUtc = $null
$stage = 'compile'

try {
    Add-Type -TypeDefinition $source -Language CSharp
    if ($ChromiumOnly) {
        if ([string]::IsNullOrWhiteSpace($ChromiumPath)) { throw '-ChromiumOnly requires -ChromiumPath.' }
    }
    else {
        $stage = 'identity'
        if (-not $result.isSystem) { throw 'Run the WFP probe as guest SYSTEM.' }

    $stage = 'validate-wfp-layout'
    $result.wfpLayoutSizes = [AppContainerNative]::WfpLayoutSizes()
    $result.wfpLayoutOffsets = [AppContainerNative]::WfpLayoutOffsets()
    $result.wfpLayoutMatchesKnownX64 =
        ($result.wfpLayoutSizes -join ',') -eq '72,72,200,40,16,16' -and
        ($result.wfpLayoutOffsets -join ',') -eq '8,24,120,128,152,184'
    if (-not $result.wfpLayoutMatchesKnownX64) { throw 'The managed x64 WFP interop layout does not match the reviewed layout values.' }

    $firstName = 'DouyinWfpLease-' + [Guid]::NewGuid().ToString('N')
    $secondName = 'DouyinWfpLease-' + [Guid]::NewGuid().ToString('N')
    $firstSid = [AppContainerNative]::CreateProfile($firstName)
    $profileNames.Add($firstName)
    $secondSid = [AppContainerNative]::CreateProfile($secondName)
    $profileNames.Add($secondName)
    $result.profilesCreated = 2
    $result.distinctPackageSids = $firstSid -ne $secondSid
    if (-not $result.distinctPackageSids) { throw 'Two independent lease profiles resolved to the same package SID.' }

    $stage = 'loopback'
    $curl = Join-Path $env:windir 'System32\curl.exe'
    if (-not (Test-Path -LiteralPath $curl -PathType Leaf)) { throw 'The Windows curl.exe probe binary is unavailable.' }
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    $port = $listener.LocalEndpoint.Port
    $curlArguments = "--silent --show-error --noproxy * --connect-timeout 2 --max-time 3 --output NUL http://127.0.0.1:$port/"
    $child = [AppContainerNative]::LaunchExecutable($firstName, @('S-1-15-3-1', 'S-1-15-3-2'), $curl, $curlArguments)
    $result.processCreated = $child.Created
    $result.childPackageSidMatches = $child.PackageSidMatches -and $child.ChildPackageSid -eq $firstSid
    $result.childExitCode = $child.ExitCode
    $result.loopbackWithoutExemptionChildExitCode = $child.ExitCode
    if (-not $child.Created) { throw "AppContainer curl.exe child creation failed with Win32 $($child.Win32Error)." }
    if (-not $result.childPackageSidMatches) { throw 'The child process token package SID differs from its per-lease profile.' }
    if ($child.CleanupError) { throw $child.CleanupError }

    $accept = $listener.AcceptTcpClientAsync()
    $accepted = $accept.Wait(3000)
    $result.loopbackWithoutExemptionAllowed = $accepted
    if ($accepted -or $child.ExitCode -notin @(7, 28)) { throw 'AppContainer loopback was not denied before adding its scoped exemption (curl connection-failure/timeout exit expected, with no accepted connection).' }
    if ($accepted) { $accept.Result.Dispose() }
    $listener.Stop()

    $stage = 'loopback-exemption'
    $checkNetIsolation = Join-Path $env:windir 'System32\CheckNetIsolation.exe'
    $add = Start-Process -FilePath $checkNetIsolation -ArgumentList @('LoopbackExempt', '-a', "-n=$firstName") -Wait -PassThru -WindowStyle Hidden
    $result.loopbackExemptionAddExitCode = $add.ExitCode
    if ($add.ExitCode -ne 0) { throw "CheckNetIsolation add returned $($add.ExitCode)." }
    $loopbackExemptionNames.Add($firstName)

    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    $port = $listener.LocalEndpoint.Port
    $curlArguments = "--silent --show-error --noproxy * --connect-timeout 2 --max-time 3 --output NUL http://127.0.0.1:$port/"
    $child = [AppContainerNative]::LaunchExecutable($firstName, @('S-1-15-3-1', 'S-1-15-3-2'), $curl, $curlArguments)
    $result.processCreated = $result.processCreated -and $child.Created
    $result.childPackageSidMatches = $result.childPackageSidMatches -and $child.PackageSidMatches -and $child.ChildPackageSid -eq $firstSid
    $result.childExitCode = $child.ExitCode
    $result.loopbackExemptionChildExitCode = $child.ExitCode
    if (-not $child.Created -or -not $child.PackageSidMatches) { throw "AppContainer curl.exe identity check failed after loopback exemption (Win32 $($child.Win32Error))." }
    if ($child.CleanupError) { throw $child.CleanupError }
    $accept = $listener.AcceptTcpClientAsync()
    $accepted = $accept.Wait(3000)
    $result.loopbackExemptionAllowsConnection = $accepted
    if ($accepted) { $accept.Result.Dispose() }
    $listener.Stop()
    if (-not $accepted) { throw 'AppContainer child could not connect to the parent loopback listener after the scoped exemption.' }
    if ($child.ExitCode -eq 124) { throw 'AppContainer curl.exe timed out before the loopback probe process exited.' }

    $stage = 'external-baseline'
    $result.externalBaselineAttempted = $true
    $targetAddresses = [System.Net.Dns]::GetHostAddresses('www.douyin.com') |
        Where-Object { $_.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork }
    $baselineFound = $false
    foreach ($targetAddress in $targetAddresses) {
        $externalArguments = "--silent --show-error --noproxy * --connect-timeout 5 --max-time 10 --output NUL --resolve www.douyin.com:443:$($targetAddress.ToString()) https://www.douyin.com/"
        $firstBaseline = [AppContainerNative]::LaunchExecutable($firstName, @('S-1-15-3-1', 'S-1-15-3-2'), $curl, $externalArguments)
        $secondBaseline = [AppContainerNative]::LaunchExecutable($secondName, @('S-1-15-3-1', 'S-1-15-3-2'), $curl, $externalArguments)
        if (-not $firstBaseline.Created -or -not $secondBaseline.Created) { throw "AppContainer baseline child creation failed (Win32 $($firstBaseline.Win32Error)/$($secondBaseline.Win32Error))." }
        if ($firstBaseline.CleanupError) { throw $firstBaseline.CleanupError }
        if ($secondBaseline.CleanupError) { throw $secondBaseline.CleanupError }
        if (-not $firstBaseline.PackageSidMatches -or $firstBaseline.ChildPackageSid -ne $firstSid) { throw 'The first baseline process token package SID did not match its lease.' }
        if (-not $secondBaseline.PackageSidMatches -or $secondBaseline.ChildPackageSid -ne $secondSid) { throw 'The second baseline process token package SID did not match its lease.' }
        $result.externalBaselineExitCode = $firstBaseline.ExitCode
        $result.secondProfileBaselineExitCode = $secondBaseline.ExitCode
        $result.externalBaselineConnected = $firstBaseline.ExitCode -eq 0
        $result.secondProfileBaselineConnected = $secondBaseline.ExitCode -eq 0
        if ($result.externalBaselineConnected -and $result.secondProfileBaselineConnected) {
            $result.externalTargetIpv4Address = $targetAddress.ToString()
            $baselineFound = $true
            break
        }
    }
    if (-not $baselineFound) { throw 'The two AppContainer profiles did not share a successful pinned-IPv4 HTTPS baseline.' }

    $stage = 'open-dynamic-wfp-session'
    $result.wfpEngineOpenCode = [AppContainerNative]::OpenDynamicWfpSession([ref]$engine)
    if ($result.wfpEngineOpenCode -ne 0 -or $engine -eq [IntPtr]::Zero) { throw "FwpmEngineOpen0 returned $($result.wfpEngineOpenCode)." }

    $stage = 'add-dynamic-wfp-sublayer'
    $subLayerKey = [Guid]::NewGuid()
    $result.wfpSubLayerAddCode = [AppContainerNative]::AddDynamicWfpSubLayer($engine, $subLayerKey)
    if ($result.wfpSubLayerAddCode -ne 0) { throw "FwpmSubLayerAdd0 returned $($result.wfpSubLayerAddCode)." }

    $stage = 'add-package-sid-filter'
    [UInt64]$filterId = 0
    $result.packageSidFilterAddCode = [AppContainerNative]::AddPackageSidBlockFilter($engine, $subLayerKey, $firstSid, [ref]$filterId)
    $result.packageSidFilterId = $filterId
    if ($result.packageSidFilterAddCode -ne 0) { throw "FwpmFilterAdd0 for ALE_PACKAGE_ID returned $($result.packageSidFilterAddCode)." }

    $stage = 'test-package-sid-filter'
    $filteredFirst = [AppContainerNative]::LaunchExecutable($firstName, @('S-1-15-3-1', 'S-1-15-3-2'), $curl, $externalArguments)
    $filteredSecond = [AppContainerNative]::LaunchExecutable($secondName, @('S-1-15-3-1', 'S-1-15-3-2'), $curl, $externalArguments)
    if (-not $filteredFirst.Created -or -not $filteredSecond.Created) { throw "Filtered child creation failed (Win32 $($filteredFirst.Win32Error)/$($filteredSecond.Win32Error))." }
    if ($filteredFirst.CleanupError) { throw $filteredFirst.CleanupError }
    if ($filteredSecond.CleanupError) { throw $filteredSecond.CleanupError }
    if (-not $filteredFirst.PackageSidMatches -or $filteredFirst.ChildPackageSid -ne $firstSid) { throw 'The blocked process token package SID did not match the filter SID.' }
    if (-not $filteredSecond.PackageSidMatches -or $filteredSecond.ChildPackageSid -ne $secondSid) { throw 'The unfiltered process token package SID did not match its lease.' }
    $result.filteredFirstProfileExitCode = $filteredFirst.ExitCode
    $result.filteredFirstProfileBlocked = $filteredFirst.ExitCode -in @(7, 28)
    $result.filteredSecondProfileExitCode = $filteredSecond.ExitCode
    $result.filteredSecondProfileAllowed = $filteredSecond.ExitCode -eq 0
    if (-not $result.filteredFirstProfileBlocked -or -not $result.filteredSecondProfileAllowed) { throw 'The package SID filter did not block only the selected AppContainer profile.' }

    $stage = 'close-dynamic-wfp-session'
    $result.wfpEngineCloseCode = [AppContainerNative]::CloseWfpSession($engine)
    if ($result.wfpEngineCloseCode -ne 0) { throw "FwpmEngineClose0 returned $($result.wfpEngineCloseCode)." }
    $engine = [IntPtr]::Zero

    $stage = 'verify-dynamic-filter-cleanup'
    $afterClose = [AppContainerNative]::LaunchExecutable($firstName, @('S-1-15-3-1', 'S-1-15-3-2'), $curl, $externalArguments)
    if (-not $afterClose.Created) { throw "Post-close child creation failed with Win32 $($afterClose.Win32Error)." }
    if ($afterClose.CleanupError) { throw $afterClose.CleanupError }
    $result.firstProfileAfterCloseExitCode = $afterClose.ExitCode
    $result.firstProfileAllowedAfterClose = $afterClose.PackageSidMatches -and $afterClose.ChildPackageSid -eq $firstSid -and $afterClose.ExitCode -eq 0
    if (-not $result.firstProfileAllowedAfterClose) { throw 'Closing the dynamic WFP session did not restore the first AppContainer profile baseline.' }
    }

    if ($ChromiumOnly -or -not [string]::IsNullOrWhiteSpace($ChromiumPath)) {
        $stage = 'chromium-appcontainer-diagnostics'
        $result.chromiumProbeAttempted = $true
        $chromiumDiagnosticStartUtc = [DateTime]::UtcNow
        if (-not (Test-Path -LiteralPath $ChromiumPath -PathType Leaf)) { throw 'The mapped Chromium executable is unavailable.' }

        $chromiumProfileName = 'DouyinAppContainerChrome-' + [Guid]::NewGuid().ToString('N')
        $chromiumSid = [AppContainerNative]::CreateProfile($chromiumProfileName)
        $profileNames.Add($chromiumProfileName)
        $result.chromiumProfilePackageSid = $chromiumSid
        $chromiumTempRoot = [IO.Path]::GetTempPath()
        $chromiumProfilePath = Join-Path $chromiumTempRoot ('DouyinAppContainerChrome-' + [Guid]::NewGuid().ToString('N'))
        if (Test-Path -LiteralPath $chromiumProfilePath) { throw 'The temporary Chromium profile directory already exists.' }
        New-Item -ItemType Directory -Path $chromiumProfilePath -ErrorAction Stop | Out-Null
        $chromiumProfilePathCreated = $true
        $chromiumPackagePath = Join-Path $chromiumTempRoot ('DouyinAppContainerPackage-' + [Guid]::NewGuid().ToString('N'))
        if (Test-Path -LiteralPath $chromiumPackagePath) { throw 'The temporary Chromium package directory already exists.' }
        New-Item -ItemType Directory -Path $chromiumPackagePath -ErrorAction Stop | Out-Null
        $chromiumPackagePathCreated = $true
        Get-ChildItem -LiteralPath (Split-Path -Parent $ChromiumPath) -Force | Copy-Item -Destination $chromiumPackagePath -Recurse -Force
        $result.chromiumStagedToGuest = $true
        $result.chromiumStagedFileCount = @(Get-ChildItem -LiteralPath $chromiumPackagePath -File -Recurse -Force).Count
        $chromiumExecutablePath = Join-Path $chromiumPackagePath (Split-Path -Leaf $ChromiumPath)
        if (-not (Test-Path -LiteralPath $chromiumExecutablePath -PathType Leaf)) { throw 'The Chromium executable was not copied into the guest-local package directory.' }

        $chromiumSidObject = [Security.Principal.SecurityIdentifier]::new($chromiumSid)
        $chromiumAccess = [Security.AccessControl.FileSystemAccessRule]::new(
            $chromiumSidObject,
            [Security.AccessControl.FileSystemRights]::Modify,
            [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit,
            [Security.AccessControl.PropagationFlags]::None,
            [Security.AccessControl.AccessControlType]::Allow
        )
        $chromiumAcl = Get-Acl -LiteralPath $chromiumProfilePath
        $chromiumAcl.SetAccessRule($chromiumAccess)
        Set-Acl -LiteralPath $chromiumProfilePath -AclObject $chromiumAcl
        $chromiumReadAccess = [Security.AccessControl.FileSystemAccessRule]::new(
            $chromiumSidObject,
            [Security.AccessControl.FileSystemRights]::ReadAndExecute,
            [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit,
            [Security.AccessControl.PropagationFlags]::None,
            [Security.AccessControl.AccessControlType]::Allow
        )
        $chromiumPackageAcl = Get-Acl -LiteralPath $chromiumPackagePath
        $chromiumPackageAcl.SetAccessRule($chromiumReadAccess)
        Set-Acl -LiteralPath $chromiumPackagePath -AclObject $chromiumPackageAcl

        # Chromium's AppContainer policy performs an access check on the executable
        # itself. An inheritable ACE added after Copy-Item does not update DACLs that
        # already exist on copied files/directories, so apply a SID-specific ACE to
        # every staged node as well as the package root.
        $chromiumReadOnlyAccess = [Security.AccessControl.FileSystemAccessRule]::new(
            $chromiumSidObject,
            [Security.AccessControl.FileSystemRights]::ReadAndExecute,
            [Security.AccessControl.InheritanceFlags]::None,
            [Security.AccessControl.PropagationFlags]::None,
            [Security.AccessControl.AccessControlType]::Allow
        )
        $chromiumPackageEntries = @(Get-ChildItem -LiteralPath $chromiumPackagePath -Force -Recurse)
        foreach ($entry in $chromiumPackageEntries) {
            $entryAcl = Get-Acl -LiteralPath $entry.FullName
            if ($entry.PSIsContainer) {
                $entryReadAccess = [Security.AccessControl.FileSystemAccessRule]::new(
                    $chromiumSidObject,
                    [Security.AccessControl.FileSystemRights]::ReadAndExecute,
                    [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit,
                    [Security.AccessControl.PropagationFlags]::None,
                    [Security.AccessControl.AccessControlType]::Allow
                )
            }
            else {
                $entryReadAccess = $chromiumReadOnlyAccess
            }
            $entryAcl.SetAccessRule($entryReadAccess)
            Set-Acl -LiteralPath $entry.FullName -AclObject $entryAcl
            $result.chromiumReadAclEntriesApplied++
        }

        $result.chromiumContext = [ordered]@{
            userIdentity = $result.userIdentity
            userSid = $result.userSid
            sessionId = $result.sessionId
            isSystem = $result.isSystem
            pageProbeRequested = [bool]$IncludeChromiumPageProbe
            pageProbeDefault = 'not-launched'
        }
        $probeDirectoryNames = if ($ChromiumPageOnly) { @('page') } else { @('normal-version', 'no-sandbox-version') }
        if ($IncludeChromiumPageProbe -and -not $ChromiumPageOnly) { $probeDirectoryNames += 'page' }
        foreach ($probeDirectoryName in $probeDirectoryNames) {
            $probeDirectory = Join-Path $chromiumProfilePath $probeDirectoryName
            New-Item -ItemType Directory -Path $probeDirectory | Out-Null
            $chromiumUserDataDirectories.Add($probeDirectory)
        }

        $normalProbe = $null
        $noSandboxProbe = $null
        if (-not $ChromiumPageOnly) {
            $normalUserData = Join-Path $chromiumProfilePath 'normal-version'
            $normalArguments = "--version --enable-logging=stderr --v=1 --no-first-run --no-default-browser-check --user-data-dir=`"$normalUserData`""
            $normalProbe = Invoke-ChromiumAppContainerProbe -ProbeName 'normal-version' -ExecutablePath $chromiumExecutablePath -ProfileName $chromiumProfileName -PackageSid $chromiumSid -UserDataDirectory $normalUserData -Arguments $normalArguments
            $result.chromiumProbes.normalVersion = $normalProbe
            $result.chromiumVersionExitCode = $normalProbe.exitCode

            $noSandboxUserData = Join-Path $chromiumProfilePath 'no-sandbox-version'
            $noSandboxArguments = "--no-sandbox --version --enable-logging=stderr --v=1 --no-first-run --no-default-browser-check --user-data-dir=`"$noSandboxUserData`""
            $noSandboxProbe = Invoke-ChromiumAppContainerProbe -ProbeName 'no-sandbox-version' -ExecutablePath $chromiumExecutablePath -ProfileName $chromiumProfileName -PackageSid $chromiumSid -UserDataDirectory $noSandboxUserData -Arguments $noSandboxArguments
            $result.chromiumProbes.noSandboxVersion = $noSandboxProbe
            $result.chromiumNoSandboxVersionExitCode = $noSandboxProbe.exitCode
        }

        if ($IncludeChromiumPageProbe) {
            $pageUserData = Join-Path $chromiumProfilePath 'page'
            $crashReporterArgument = if ($DisableHeadlessCrashReporter) { ' --disable-crash-reporter' } else { '' }
            $pageArguments = "--headless=new --disable-gpu --disable-background-networking --disable-extensions --disable-sync --no-first-run --no-default-browser-check$crashReporterArgument --enable-logging=stderr --v=1 --user-data-dir=`"$pageUserData`" --dump-dom about:blank"
            $pageProbe = Invoke-ChromiumAppContainerProbe -ProbeName 'page' -ExecutablePath $chromiumExecutablePath -ProfileName $chromiumProfileName -PackageSid $chromiumSid -UserDataDirectory $pageUserData -Arguments $pageArguments
            $result.chromiumProbes.page = $pageProbe
            $result.chromiumProcessCreated = $pageProbe.created
            $result.chromiumProcessId = $pageProbe.processId
            $result.chromiumTokenMatchesProfile = $pageProbe.tokenMatchesProfile
            $result.chromiumExitCode = $pageProbe.exitCode
            $result.chromiumLogTail = $pageProbe.logTail
        }
        else {
            $result.chromiumProbes.page = New-ChromiumProbeRecord
            $result.chromiumProbes.page.userDataDirectory = $null
            $result.chromiumProcessCreated = $false
            $result.chromiumProcessId = $null
            $result.chromiumTokenMatchesProfile = if ($ChromiumPageOnly) { $false } else { $normalProbe.tokenMatchesProfile -and $noSandboxProbe.tokenMatchesProfile }
            $result.chromiumExitCode = $null
            $result.chromiumLogTail = $noSandboxProbe.logTail
        }

        $probeFailures = [System.Collections.Generic.List[string]]::new()
        if (-not $ChromiumPageOnly) {
            foreach ($probeEntry in @(
                [pscustomobject]@{ Name = 'normal --version'; Probe = $normalProbe },
                [pscustomobject]@{ Name = '--no-sandbox --version'; Probe = $noSandboxProbe }
            )) {
                $probe = $probeEntry.Probe
                if (-not $probe.created) { $probeFailures.Add("$($probeEntry.Name): process creation failed (Win32 $($probe.win32Error)).") }
                elseif (-not $probe.tokenMatchesProfile) { $probeFailures.Add("$($probeEntry.Name): package SID mismatch.") }
                elseif ($probe.timedOut) { $probeFailures.Add("$($probeEntry.Name): timed out.") }
                elseif ($probe.exitCode -ne 0) { $probeFailures.Add("$($probeEntry.Name): exit code $($probe.exitCode).") }
            }
        }
        if ($IncludeChromiumPageProbe) {
            $probe = $result.chromiumProbes.page
            if (-not $probe.created) { $probeFailures.Add("page probe: process creation failed (Win32 $($probe.win32Error)).") }
            elseif (-not $probe.tokenMatchesProfile) { $probeFailures.Add('page probe: package SID mismatch.') }
            elseif ($probe.timedOut) { $probeFailures.Add('page probe: timed out.') }
            elseif ($probe.exitCode -ne 0) { $probeFailures.Add("page probe: exit code $($probe.exitCode).") }
        }
        if ($probeFailures.Count -gt 0) { throw ($probeFailures -join ' ') }
    }

    $result.status = 'pass'
}
catch {
    $result.failureStage = $stage
    $result.errors.Add($_.Exception.Message)
    $result.status = 'fail'
}
finally {
    if ($null -ne $listener) { $listener.Stop() }
    if ($engine -ne [IntPtr]::Zero) {
        try {
            $result.wfpEngineCloseCode = [AppContainerNative]::CloseWfpSession($engine)
            if ($result.wfpEngineCloseCode -ne 0) { $result.errors.Add("WFP session cleanup returned $($result.wfpEngineCloseCode).") }
            $engine = [IntPtr]::Zero
        } catch { $result.errors.Add("WFP session cleanup failed: $($_.Exception.Message)") }
    }

    if ($result.chromiumProbeAttempted) {
        try {
            $resultDirectory = Split-Path -Parent $ResultPath
            if ([string]::IsNullOrWhiteSpace($resultDirectory)) { $resultDirectory = (Get-Location).Path }
            if (-not (Test-Path -LiteralPath $resultDirectory -PathType Container)) { New-Item -ItemType Directory -Path $resultDirectory | Out-Null }
            $artifactDirectoryName = 'chromium-diagnostics-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [Guid]::NewGuid().ToString('N')
            $result.chromiumDiagnosticArtifactDirectory = Join-Path $resultDirectory $artifactDirectoryName
            New-Item -ItemType Directory -Path $result.chromiumDiagnosticArtifactDirectory | Out-Null

            foreach ($probeName in @('normalVersion', 'noSandboxVersion', 'page')) {
                $probe = $result.chromiumProbes[$probeName]
                if ($null -eq $probe) { continue }
                foreach ($streamName in @('standardOutput', 'standardError')) {
                    $sourcePath = $probe["${streamName}Path"]
                    if (-not [string]::IsNullOrWhiteSpace($sourcePath) -and (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
                        $destinationName = "$probeName.$streamName.txt"
                        Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $result.chromiumDiagnosticArtifactDirectory $destinationName) -Force
                    }
                }
                if (-not [string]::IsNullOrWhiteSpace($probe.logPath) -and (Test-Path -LiteralPath $probe.logPath -PathType Leaf)) {
                    Copy-Item -LiteralPath $probe.logPath -Destination (Join-Path $result.chromiumDiagnosticArtifactDirectory "$probeName.chrome_debug.log") -Force
                }
            }

            $crashpadFiles = [System.Collections.Generic.List[object]]::new()
            foreach ($userDataDirectory in $chromiumUserDataDirectories) {
                $crashpadDirectory = Join-Path $userDataDirectory 'Crashpad'
                if (-not (Test-Path -LiteralPath $crashpadDirectory -PathType Container)) { continue }
                foreach ($file in Get-ChildItem -LiteralPath $crashpadDirectory -File -Recurse -Force -ErrorAction SilentlyContinue) {
                    $artifact = [ordered]@{
                        sourcePath = $file.FullName
                        name = $file.Name
                        bytes = $file.Length
                        lastWriteTimeUtc = $file.LastWriteTimeUtc.ToString('o')
                        copiedPath = $null
                    }
                    if ($file.Extension -ieq '.dmp') {
                        $probeFolderName = Split-Path -Leaf $userDataDirectory
                        $dumpName = "$probeFolderName-$($file.Name)"
                        $destination = Join-Path $result.chromiumDiagnosticArtifactDirectory $dumpName
                        Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
                        $artifact.copiedPath = $destination
                    }
                    $crashpadFiles.Add($artifact)
                }
            }
            $result.chromiumCrashpadArtifacts = @($crashpadFiles.ToArray())

            if ($null -ne $chromiumDiagnosticStartUtc) {
                $eventStartLocal = $chromiumDiagnosticStartUtc.ToLocalTime()
                $applicationEvents = Get-WinEvent -FilterHashtable @{ LogName = 'Application'; StartTime = $eventStartLocal } -ErrorAction SilentlyContinue |
                    Where-Object { $_.ProviderName -match 'Application Error|Windows Error Reporting|WER' -or $_.Message -match 'chrome(_crashpad_handler)?\.exe' } |
                    Sort-Object TimeCreated |
                    Select-Object -Last 50
                $result.chromiumApplicationEvents = @(
                    foreach ($event in $applicationEvents) {
                        $eventMessage = [string]$event.Message
                        [ordered]@{
                            timeCreatedUtc = $event.TimeCreated.ToUniversalTime().ToString('o')
                            eventId = $event.Id
                            provider = $event.ProviderName
                            level = $event.LevelDisplayName
                            message = if ($eventMessage.Length -gt 12000) { $eventMessage.Substring(0, 12000) } else { $eventMessage }
                        }
                    }
                )
            }
            $result.chromiumDiagnosticsCollected = $true
        }
        catch {
            $result.chromiumDiagnosticsCollectionErrors.Add($_.Exception.Message)
        }
    }

    if ($chromiumProfilePathCreated -and $null -ne $chromiumProfilePath -and (Test-Path -LiteralPath $chromiumProfilePath -PathType Container)) {
        try { Remove-Item -LiteralPath $chromiumProfilePath -Recurse -Force -ErrorAction Stop }
        catch { $result.errors.Add("Chromium profile cleanup failed: $($_.Exception.Message)") }
    }
    if ($chromiumPackagePathCreated -and $null -ne $chromiumPackagePath -and (Test-Path -LiteralPath $chromiumPackagePath -PathType Container)) {
        try { Remove-Item -LiteralPath $chromiumPackagePath -Recurse -Force -ErrorAction Stop }
        catch { $result.errors.Add("Chromium package cleanup failed: $($_.Exception.Message)") }
    }
    if ($loopbackExemptionNames.Count -gt 0) {
        $checkNetIsolation = Join-Path $env:windir 'System32\CheckNetIsolation.exe'
        foreach ($name in $loopbackExemptionNames) {
            try {
                $remove = Start-Process -FilePath $checkNetIsolation -ArgumentList @('LoopbackExempt', '-d', "-n=$name") -Wait -PassThru -WindowStyle Hidden -ErrorAction Stop
                if ($name -eq $firstName) { $result.loopbackExemptionDeleteExitCode = $remove.ExitCode }
                if ($remove.ExitCode -ne 0) { $result.errors.Add("Loopback exemption cleanup for $name returned $($remove.ExitCode).") }
            } catch {
                $result.errors.Add("Loopback exemption cleanup failed for $name`: $($_.Exception.Message)")
            }
        }
    }
    if ($profileNames.Count -gt 0) {
        foreach ($name in $profileNames) {
            try { [AppContainerNative]::DeleteProfile($name) } catch { $result.errors.Add("Profile cleanup failed: $($_.Exception.Message)") }
        }
    }
    if ($result.status -eq 'pass' -and $result.errors.Count -gt 0) {
        $result.status = 'fail'
        $result.failureStage = 'cleanup'
    }
    $json = $result | ConvertTo-Json -Depth 8
    $directory = Split-Path -Parent $ResultPath
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) { New-Item -ItemType Directory -Path $directory | Out-Null }
    [IO.File]::WriteAllText($ResultPath, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

if ($result.status -ne 'pass') { throw "AppContainer identity smoke failed at $($result.failureStage)." }
