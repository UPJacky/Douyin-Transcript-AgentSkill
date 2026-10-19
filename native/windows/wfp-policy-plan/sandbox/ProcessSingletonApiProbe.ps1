param(
    [Parameter(Mandatory = $true)]
    [string]$ProfileDirectory,
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,
    [Parameter(Mandatory = $true)]
    [string]$ExpectedUserSid,
    [Parameter(Mandatory = $true)]
    [uint32]$ExpectedSessionId,
    [string]$ChromiumPath = '',
    [string]$ScreenshotPath = '',
    [string]$ChromiumStdoutPath = '',
    [string]$ChromiumStderrPath = '',
    [ValidateRange(1, 60)]
    [int]$ChromiumTimeoutSeconds = 20
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$source = @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Text;

[UnmanagedFunctionPointer(CallingConvention.Winapi)]
public delegate IntPtr ProcessSingletonProbeWndProc(IntPtr hwnd, uint message, IntPtr wParam, IntPtr lParam);

[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
public struct ProcessSingletonProbeWndClassEx
{
    public uint Size;
    public uint Style;
    public ProcessSingletonProbeWndProc WindowProcedure;
    public int ClassExtraBytes;
    public int WindowExtraBytes;
    public IntPtr Instance;
    public IntPtr Icon;
    public IntPtr Cursor;
    public IntPtr BackgroundBrush;
    [MarshalAs(UnmanagedType.LPWStr)] public string MenuName;
    [MarshalAs(UnmanagedType.LPWStr)] public string ClassName;
    public IntPtr SmallIcon;
}

public sealed class ProcessSingletonProbeApiResult
{
    public bool Succeeded { get; set; }
    public long Value { get; set; }
    public int Win32Error { get; set; }
    public int? LastError { get; set; }
    public string Detail { get; set; }
    public string OwnerSid { get; set; }
    public string DaclSummary { get; set; }
}

public static class ProcessSingletonProbeNative
{
    public const uint GenericWrite = 0x40000000;
    public const uint FileShareRead = 0x00000001;
    public const uint CreateNew = 1;
    public const uint FileAttributeNormal = 0x00000080;
    public const uint FileFlagDeleteOnClose = 0x04000000;
    public const uint ReadControl = 0x00020000;
    public const uint MutexAllAccess = 0x001F0001;
    public const uint DirectoryQuery = 0x00000001;
    public const int StatusSuccess = 0;
    public const int StatusBufferOverflow = unchecked((int)0x80000005);
    public const int StatusBufferTooSmall = unchecked((int)0xC0000023);
    public const int ObjCaseInsensitive = 0x00000040;

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct UnicodeString
    {
        public ushort Length;
        public ushort MaximumLength;
        public IntPtr Buffer;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct ObjectAttributes
    {
        public int Length;
        public IntPtr RootDirectory;
        public IntPtr ObjectName;
        public uint Attributes;
        public IntPtr SecurityDescriptor;
        public IntPtr SecurityQualityOfService;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct SecurityAttributes
    {
        public int Length;
        public IntPtr SecurityDescriptor;
        [MarshalAs(UnmanagedType.Bool)] public bool InheritHandle;
    }
    public const int GwlExStyle = -20;
    public const int GwlpUserData = -21;
    public const uint UoiName = 2;
    public static readonly IntPtr HwndMessage = new IntPtr(-3);

    [DllImport("kernel32.dll", EntryPoint = "CreateMutexW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr CreateMutex(IntPtr attributes, bool initialOwner, string name);
    [DllImport("kernel32.dll", EntryPoint = "OpenMutexW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr OpenMutex(uint desiredAccess, bool inherit, string name);
    [DllImport("kernel32.dll", EntryPoint = "CreateFileW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr CreateFile(string path, uint access, uint share, IntPtr security, uint creation, uint flags, IntPtr template);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll", EntryPoint = "GetModuleHandleW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr GetModuleHandle(string moduleName);
    [DllImport("kernel32.dll", SetLastError = true)] public static extern uint GetCurrentThreadId();
    [DllImport("kernel32.dll", SetLastError = true)] private static extern void SetLastError(uint error);
    [DllImport("advapi32.dll", EntryPoint = "ConvertStringSecurityDescriptorToSecurityDescriptorW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool ConvertStringSecurityDescriptorToSecurityDescriptor(string sddl, uint revision, out IntPtr descriptor, out uint size);
    [DllImport("advapi32.dll", SetLastError = true)] private static extern bool OpenProcessToken(IntPtr process, uint access, out IntPtr token);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern IntPtr GetCurrentProcess();
    [DllImport("advapi32.dll", EntryPoint = "GetTokenInformation", SetLastError = true)]
    private static extern bool GetTokenInformation(IntPtr token, int informationClass, IntPtr information, uint informationLength, out uint returnLength);
    [DllImport("kernel32.dll", EntryPoint = "LocalFree", SetLastError = true)] private static extern IntPtr LocalFree(IntPtr memory);
    [DllImport("ntdll.dll", EntryPoint = "NtOpenDirectoryObject")]
    private static extern int NtOpenDirectoryObject(out IntPtr handle, uint desiredAccess, ref ObjectAttributes attributes);
    [DllImport("ntdll.dll", EntryPoint = "NtQuerySecurityObject")]
    private static extern int NtQuerySecurityObject(IntPtr handle, uint securityInformation, byte[] descriptor, uint length, out uint needed);
    [DllImport("ntdll.dll", EntryPoint = "RtlNtStatusToDosError")]
    private static extern uint RtlNtStatusToDosError(int status);
    [DllImport("user32.dll", SetLastError = true)] public static extern IntPtr GetProcessWindowStation();
    [DllImport("user32.dll", SetLastError = true)] public static extern IntPtr GetThreadDesktop(uint threadId);
    [DllImport("user32.dll", EntryPoint = "GetUserObjectInformationW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool GetUserObjectInformation(IntPtr handle, uint index, StringBuilder information, uint length, out uint needed);
    [DllImport("user32.dll", EntryPoint = "RegisterClassExW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern ushort RegisterClassEx(ref ProcessSingletonProbeWndClassEx windowClass);
    [DllImport("user32.dll", EntryPoint = "CreateWindowExW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr CreateWindowEx(uint extendedStyle, string className, string windowName, uint style, int x, int y, int width, int height, IntPtr parent, IntPtr menu, IntPtr instance, IntPtr parameter);
    [DllImport("user32.dll", EntryPoint = "DestroyWindow", SetLastError = true)] private static extern bool DestroyWindow(IntPtr window);
    [DllImport("user32.dll", EntryPoint = "UnregisterClassW", CharSet = CharSet.Unicode, SetLastError = true)] private static extern bool UnregisterClass(string className, IntPtr instance);
    [DllImport("user32.dll", EntryPoint = "DefWindowProcW", SetLastError = true)] private static extern IntPtr DefWindowProc(IntPtr window, uint message, IntPtr wParam, IntPtr lParam);

    public static string GetObjectName(IntPtr handle)
    {
        uint needed;
        GetUserObjectInformation(handle, UoiName, null, 0, out needed);
        int error = Marshal.GetLastWin32Error();
        if (needed == 0 && error != 122) throw new System.ComponentModel.Win32Exception(error, "GetUserObjectInformationW(size)");
        StringBuilder value = new StringBuilder((int)(needed / 2) + 2);
        if (!GetUserObjectInformation(handle, UoiName, value, (uint)(value.Capacity * 2), out needed))
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "GetUserObjectInformationW(name)");
        return value.ToString();
    }

    public static ProcessSingletonProbeApiResult ProbeMutex(string name)
    {
        return ProbeMutexWithAttributes(name, IntPtr.Zero);
    }

    public static ProcessSingletonProbeApiResult ProbeExistingMutexOpenOnly(string name)
    {
        ProcessSingletonProbeApiResult result = new ProcessSingletonProbeApiResult();
        IntPtr handle = IntPtr.Zero;
        try
        {
            SetLastError(0);
            handle = OpenMutex(MutexAllAccess, false, name);
            int openError = Marshal.GetLastWin32Error();
            if (handle == IntPtr.Zero)
            {
                result.Win32Error = openError;
                result.LastError = openError;
                result.Detail = "OpenMutexW(MUTEX_ALL_ACCESS) returned NULL; no object was created";
                return result;
            }
            result.Succeeded = true;
            result.Win32Error = 0;
            result.LastError = null;
            result.Detail = "opened the existing mutex with MUTEX_ALL_ACCESS; no creation, wait, or release was attempted";
            return result;
        }
        finally
        {
            if (handle != IntPtr.Zero) CloseHandle(handle);
        }
    }

    public static ProcessSingletonProbeApiResult ProbeExplicitDaclMutex(string name, string sid)
    {
        ProcessSingletonProbeApiResult result = new ProcessSingletonProbeApiResult();
        IntPtr descriptor = IntPtr.Zero;
        IntPtr attributesBuffer = IntPtr.Zero;
        try
        {
            string sddl = "D:P(A;;GA;;;" + sid + ")";
            uint descriptorSize;
            if (!ConvertStringSecurityDescriptorToSecurityDescriptor(sddl, 1, out descriptor, out descriptorSize))
            {
                result.Win32Error = Marshal.GetLastWin32Error();
                result.LastError = result.Win32Error;
                result.Detail = "ConvertStringSecurityDescriptorToSecurityDescriptorW failed";
                return result;
            }
            SecurityAttributes attributes = new SecurityAttributes { Length = Marshal.SizeOf(typeof(SecurityAttributes)), SecurityDescriptor = descriptor, InheritHandle = false };
            attributesBuffer = Marshal.AllocHGlobal(attributes.Length);
            Marshal.StructureToPtr(attributes, attributesBuffer, false);
            return ProbeMutexWithAttributes(name, attributesBuffer);
        }
        finally
        {
            if (attributesBuffer != IntPtr.Zero) Marshal.FreeHGlobal(attributesBuffer);
            if (descriptor != IntPtr.Zero) LocalFree(descriptor);
        }
    }

    private static ProcessSingletonProbeApiResult ProbeMutexWithAttributes(string name, IntPtr attributes)
    {
        ProcessSingletonProbeApiResult result = new ProcessSingletonProbeApiResult();
        IntPtr handle = IntPtr.Zero;
        try
        {
            SetLastError(0);
            handle = CreateMutex(attributes, false, name);
            int createError = Marshal.GetLastWin32Error();
            if (handle == IntPtr.Zero)
            {
                result.Win32Error = createError;
                result.LastError = createError;
                result.Detail = "CreateMutexW returned NULL";
                return result;
            }
            result.Value = handle.ToInt64();
            result.LastError = createError;
            if (createError == 183)
            {
                result.Win32Error = createError;
                result.Detail = "CreateMutexW returned a handle to an already-existing object; refused to wait or release it";
                return result;
            }
            result.Succeeded = true;
            result.Win32Error = 0;
            string objectKind = String.IsNullOrEmpty(name) ? "unnamed mutex" : "named mutex";
            result.Detail = "created a new " + objectKind + " without initial ownership; closed without waiting or releasing";
            return result;
        }
        finally
        {
            if (handle != IntPtr.Zero) CloseHandle(handle);
        }
    }

    public static ProcessSingletonProbeApiResult ProbeUnnamedMutex()
    {
        return ProbeMutex(null);
    }

    public static ProcessSingletonProbeApiResult ProbeTokenDefaultDacl()
    {
        ProcessSingletonProbeApiResult result = new ProcessSingletonProbeApiResult();
        IntPtr token = IntPtr.Zero;
        IntPtr buffer = IntPtr.Zero;
        try
        {
            if (!OpenProcessToken(GetCurrentProcess(), 0x0008, out token))
            {
                result.Win32Error = Marshal.GetLastWin32Error();
                result.LastError = result.Win32Error;
                result.Detail = "OpenProcessToken(TOKEN_QUERY) failed";
                return result;
            }
            uint needed;
            GetTokenInformation(token, 6, IntPtr.Zero, 0, out needed); // TokenDefaultDacl
            int sizeError = Marshal.GetLastWin32Error();
            if (needed == 0 || sizeError != 122)
            {
                result.Win32Error = sizeError;
                result.LastError = sizeError;
                result.Detail = "GetTokenInformation(TokenDefaultDacl size) failed";
                return result;
            }
            buffer = Marshal.AllocHGlobal((int)needed);
            if (!GetTokenInformation(token, 6, buffer, needed, out needed))
            {
                result.Win32Error = Marshal.GetLastWin32Error();
                result.LastError = result.Win32Error;
                result.Detail = "GetTokenInformation(TokenDefaultDacl) failed";
                return result;
            }
            IntPtr aclPointer = Marshal.ReadIntPtr(buffer);
            if (aclPointer == IntPtr.Zero)
            {
                result.Succeeded = true;
                result.DaclSummary = "null token default DACL";
                result.Win32Error = 0;
                result.LastError = null;
                result.Detail = "read TokenDefaultDacl; pointer is NULL";
                return result;
            }
            ushort aclSize = unchecked((ushort)Marshal.ReadInt16(aclPointer, 2));
            byte[] aclBytes = new byte[aclSize];
            Marshal.Copy(aclPointer, aclBytes, 0, aclSize);
            RawAcl dacl = new RawAcl(aclBytes, 0);
            result.Succeeded = true;
            result.Win32Error = 0;
            result.LastError = null;
            result.DaclSummary = SummarizeDacl(dacl);
            result.Detail = "read TokenDefaultDacl using TOKEN_QUERY";
            return result;
        }
        finally
        {
            if (buffer != IntPtr.Zero) Marshal.FreeHGlobal(buffer);
            if (token != IntPtr.Zero) CloseHandle(token);
        }
    }

    public static ProcessSingletonProbeApiResult ProbeSessionObjectDirectory(uint sessionId)
    {
        ProcessSingletonProbeApiResult result = new ProcessSingletonProbeApiResult();
        IntPtr pathBuffer = IntPtr.Zero;
        IntPtr unicodeBuffer = IntPtr.Zero;
        IntPtr directory = IntPtr.Zero;
        try
        {
            string path = "\\Sessions\\" + sessionId.ToString() + "\\BaseNamedObjects";
            pathBuffer = Marshal.StringToHGlobalUni(path);
            UnicodeString objectName = new UnicodeString { Length = (ushort)(path.Length * 2), MaximumLength = (ushort)((path.Length + 1) * 2), Buffer = pathBuffer };
            unicodeBuffer = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(UnicodeString)));
            Marshal.StructureToPtr(objectName, unicodeBuffer, false);
            ObjectAttributes attributes = new ObjectAttributes
            {
                Length = Marshal.SizeOf(typeof(ObjectAttributes)),
                RootDirectory = IntPtr.Zero,
                ObjectName = unicodeBuffer,
                Attributes = ObjCaseInsensitive,
                SecurityDescriptor = IntPtr.Zero,
                SecurityQualityOfService = IntPtr.Zero
            };
            int status = NtOpenDirectoryObject(out directory, ReadControl | DirectoryQuery, ref attributes);
            result.LastError = null;
            if (status != StatusSuccess)
            {
                result.Win32Error = (int)RtlNtStatusToDosError(status);
                result.Detail = "NtOpenDirectoryObject(" + path + ") failed with NTSTATUS 0x" + status.ToString("X8");
                return result;
            }
            result.Value = directory.ToInt64();
            const uint ownerAndDacl = 0x00000001 | 0x00000004;
            uint needed;
            int queryStatus = NtQuerySecurityObject(directory, ownerAndDacl, null, 0, out needed);
            if (queryStatus != StatusBufferTooSmall && queryStatus != StatusBufferOverflow)
            {
                result.Win32Error = (int)RtlNtStatusToDosError(queryStatus);
                result.Detail = "NtQuerySecurityObject(size) failed with NTSTATUS 0x" + queryStatus.ToString("X8");
                return result;
            }
            byte[] descriptorBytes = new byte[needed];
            queryStatus = NtQuerySecurityObject(directory, ownerAndDacl, descriptorBytes, (uint)descriptorBytes.Length, out needed);
            if (queryStatus != StatusSuccess)
            {
                result.Win32Error = (int)RtlNtStatusToDosError(queryStatus);
                result.Detail = "NtQuerySecurityObject(data) failed with NTSTATUS 0x" + queryStatus.ToString("X8");
                return result;
            }
            RawSecurityDescriptor descriptor = new RawSecurityDescriptor(descriptorBytes, 0);
            result.OwnerSid = descriptor.Owner == null ? null : descriptor.Owner.Value;
            result.DaclSummary = SummarizeDacl(descriptor.DiscretionaryAcl);
            result.Succeeded = true;
            result.Win32Error = 0;
            result.Detail = "opened session BaseNamedObjects with DIRECTORY_QUERY|READ_CONTROL and read owner/DACL";
            return result;
        }
        finally
        {
            if (directory != IntPtr.Zero) CloseHandle(directory);
            if (unicodeBuffer != IntPtr.Zero) Marshal.FreeHGlobal(unicodeBuffer);
            if (pathBuffer != IntPtr.Zero) Marshal.FreeHGlobal(pathBuffer);
        }
    }

    private static string SummarizeDacl(GenericAcl dacl)
    {
        if (dacl == null) return "null DACL";
        List<string> entries = new List<string>();
        foreach (GenericAce ace in dacl)
        {
            CommonAce common = ace as CommonAce;
            if (common != null)
                entries.Add(common.AceQualifier + " " + common.SecurityIdentifier.Value + " mask=0x" + common.AccessMask.ToString("X8") + " inherited=" + common.IsInherited);
            else
                entries.Add(ace.AceType.ToString() + " " + ace.AceFlags.ToString());
        }
        return String.Join("; ", entries.ToArray());
    }

    public static ProcessSingletonProbeApiResult ProbeLockFile(string path)
    {
        ProcessSingletonProbeApiResult result = new ProcessSingletonProbeApiResult();
        IntPtr handle = IntPtr.Zero;
        try
        {
            SetLastError(0);
            handle = CreateFile(path, GenericWrite, FileShareRead, IntPtr.Zero, CreateNew, FileAttributeNormal | FileFlagDeleteOnClose, IntPtr.Zero);
            int error = Marshal.GetLastWin32Error();
            if (handle == new IntPtr(-1))
            {
                result.Win32Error = error;
                result.LastError = error;
                result.Detail = "CreateFileW(lockfile) returned INVALID_HANDLE_VALUE";
                return result;
            }
            result.Succeeded = true;
            result.Value = handle.ToInt64();
            result.Win32Error = 0;
            result.LastError = null;
            result.Detail = "created a new lockfile exclusively with GENERIC_WRITE/FILE_SHARE_READ/CREATE_NEW/DELETE_ON_CLOSE; existing files are refused";
            return result;
        }
        finally
        {
            if (handle != IntPtr.Zero && handle != new IntPtr(-1)) CloseHandle(handle);
        }
    }

    public static ProcessSingletonProbeApiResult ProbeMessageWindow(string profilePath)
    {
        ProcessSingletonProbeApiResult result = new ProcessSingletonProbeApiResult();
        string className = "Chrome_MessageWindow";
        IntPtr instance = GetModuleHandle(null);
        ProcessSingletonProbeWndProc procedure = delegate(IntPtr window, uint message, IntPtr wParam, IntPtr lParam)
        {
            return DefWindowProc(window, message, wParam, lParam);
        };
        ushort atom = 0;
        IntPtr windowHandle = IntPtr.Zero;
        try
        {
            ProcessSingletonProbeWndClassEx windowClass = new ProcessSingletonProbeWndClassEx
            {
                Size = (uint)Marshal.SizeOf(typeof(ProcessSingletonProbeWndClassEx)),
                Style = 0,
                WindowProcedure = procedure,
                ClassExtraBytes = 0,
                WindowExtraBytes = 0,
                Instance = instance,
                Icon = IntPtr.Zero,
                Cursor = IntPtr.Zero,
                BackgroundBrush = IntPtr.Zero,
                MenuName = null,
                ClassName = className,
                SmallIcon = IntPtr.Zero
            };
            SetLastError(0);
            atom = RegisterClassEx(ref windowClass);
            int registerError = Marshal.GetLastWin32Error();
            if (atom == 0)
            {
                result.Win32Error = registerError;
                result.LastError = registerError;
                result.Detail = "RegisterClassExW(Chrome_MessageWindow) returned 0";
                return result;
            }
            SetLastError(0);
            windowHandle = CreateWindowEx(0, className, profilePath, 0, 0, 0, 0, 0, HwndMessage, IntPtr.Zero, instance, IntPtr.Zero);
            int createError = Marshal.GetLastWin32Error();
            if (windowHandle == IntPtr.Zero)
            {
                result.Win32Error = createError;
                result.LastError = createError;
                result.Detail = "CreateWindowExW(HWND_MESSAGE) returned NULL";
                return result;
            }
            result.Succeeded = true;
            result.Value = windowHandle.ToInt64();
            result.Win32Error = 0;
            result.Detail = "registered Chrome_MessageWindow class and created HWND_MESSAGE with profile path title";
            return result;
        }
        finally
        {
            if (windowHandle != IntPtr.Zero) DestroyWindow(windowHandle);
            if (atom != 0) UnregisterClass(className, instance);
            GC.KeepAlive(procedure);
        }
    }
}
'@

$result = [ordered]@{
    reportKind = 'chromium-process-singleton-api-probe'
    capturedAtUtc = [DateTime]::UtcNow.ToString('o')
    identityMatchesExpected = $false
    sessionMatchesExpected = $false
    processWindowStation = $null
    threadDesktop = $null
    preexistingChromeProcessCount = 0
    mutex = $null
    globalMutexControl = $null
    randomLocalMutexControl = $null
    unnamedMutexControl = $null
    explicitDaclMutexControl = $null
    tokenDefaultDacl = $null
    sessionObjectDirectory = $null
    lockFile = $null
    messageWindow = $null
    lockFileDeletedAfterClose = $false
    chromiumLaunch = $null
    errors = @()
    status = 'fail'
}

try {
    if (-not ('ProcessSingletonProbeNative' -as [type])) { Add-Type -TypeDefinition $source -Language CSharp }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $userSid = $identity.User.Value
    $sessionId = [uint32][Diagnostics.Process]::GetCurrentProcess().SessionId
    $result.identityMatchesExpected = $userSid -eq $ExpectedUserSid
    $result.sessionMatchesExpected = $sessionId -eq $ExpectedSessionId
    if (-not $result.identityMatchesExpected) { throw 'Probe child SID does not match the temporary Chromium target SID.' }
    if (-not $result.sessionMatchesExpected) { throw 'Probe child session does not match the interactive target session.' }
    $station = [ProcessSingletonProbeNative]::GetProcessWindowStation()
    $desktop = [ProcessSingletonProbeNative]::GetThreadDesktop([ProcessSingletonProbeNative]::GetCurrentThreadId())
    if ($station -eq [IntPtr]::Zero) { throw "GetProcessWindowStation failed with Win32 $([Runtime.InteropServices.Marshal]::GetLastWin32Error())." }
    if ($desktop -eq [IntPtr]::Zero) { throw "GetThreadDesktop failed with Win32 $([Runtime.InteropServices.Marshal]::GetLastWin32Error())." }
    $result.processWindowStation = [ProcessSingletonProbeNative]::GetObjectName($station)
    $result.threadDesktop = [ProcessSingletonProbeNative]::GetObjectName($desktop)
    if ($result.processWindowStation -ne 'WinSta0' -or $result.threadDesktop -ne 'Default') { throw 'Probe child is not attached to WinSta0\Default.' }

    $preexistingChromeProcesses = @(Get-Process -Name 'chrome' -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq $sessionId })
    $result.preexistingChromeProcessCount = $preexistingChromeProcesses.Count
    if ($result.preexistingChromeProcessCount -gt 0) { throw 'A pre-existing chrome.exe process is present in the fresh Sandbox; refusing to probe a potentially occupied ProcessSingleton namespace.' }

    if (-not (Test-Path -LiteralPath $ProfileDirectory -PathType Container)) { throw 'Profile directory does not exist.' }
    $mutexResult = [ProcessSingletonProbeNative]::ProbeExistingMutexOpenOnly('Local\ChromeProcessSingletonStartup!')
    $mutexState = if ($mutexResult.Succeeded) { 'opened_existing' } elseif ($mutexResult.Win32Error -eq 2) { 'absent' } elseif ($mutexResult.Win32Error -eq 5) { 'access_denied' } else { 'open_failed' }
    $result.mutex = [ordered]@{
        succeeded = $mutexResult.Succeeded
        state = $mutexState
        win32Error = $mutexResult.Win32Error
        lastError = $mutexResult.LastError
        rightsRequested = 'MUTEX_ALL_ACCESS (0x001F0001)'
        creationAttempted = $false
        waitOrReleaseAttempted = $false
        detail = $mutexResult.Detail
    }
    $globalMutexResult = [ProcessSingletonProbeNative]::ProbeExistingMutexOpenOnly('Global\ChromeProcessSingletonStartup!')
    $globalMutexState = if ($globalMutexResult.Succeeded) { 'opened_existing' } elseif ($globalMutexResult.Win32Error -eq 2) { 'absent' } elseif ($globalMutexResult.Win32Error -eq 5) { 'access_denied' } else { 'open_failed' }
    $result.globalMutexControl = [ordered]@{
        succeeded = $globalMutexResult.Succeeded
        state = $globalMutexState
        win32Error = $globalMutexResult.Win32Error
        lastError = $globalMutexResult.LastError
        rightsRequested = 'MUTEX_ALL_ACCESS (0x001F0001)'
        creationAttempted = $false
        waitOrReleaseAttempted = $false
        detail = $globalMutexResult.Detail
        interpretation = 'Global namespace control only; this does not prove cross-session access.'
    }
    $randomMutexName = 'Local\CodexProcessSingletonProbe-' + [Guid]::NewGuid().ToString('N')
    $randomMutexResult = [ProcessSingletonProbeNative]::ProbeMutex($randomMutexName)
    $result.randomLocalMutexControl = [ordered]@{
        name = $randomMutexName
        succeeded = $randomMutexResult.Succeeded
        win32Error = $randomMutexResult.Win32Error
        lastError = $randomMutexResult.LastError
        detail = $randomMutexResult.Detail
        interpretation = 'Unique Local name control to distinguish general session-local mutex creation from the Chromium object name.'
    }
    $unnamedMutexResult = [ProcessSingletonProbeNative]::ProbeUnnamedMutex()
    $result.unnamedMutexControl = [ordered]@{
        succeeded = $unnamedMutexResult.Succeeded
        win32Error = $unnamedMutexResult.Win32Error
        lastError = $unnamedMutexResult.LastError
        detail = $unnamedMutexResult.Detail
        interpretation = 'Unnamed mutex control; tests the API without the named-object namespace.'
    }
    $explicitMutexName = 'Local\CodexExplicitDaclProbe-' + [Guid]::NewGuid().ToString('N')
    $explicitMutexResult = [ProcessSingletonProbeNative]::ProbeExplicitDaclMutex($explicitMutexName,$userSid)
    $result.explicitDaclMutexControl = [ordered]@{
        name = $explicitMutexName
        succeeded = $explicitMutexResult.Succeeded
        win32Error = $explicitMutexResult.Win32Error
        lastError = $explicitMutexResult.LastError
        detail = $explicitMutexResult.Detail
        interpretation = 'Unique Local mutex with a temporary protected DACL granting full access only to this disposable target SID.'
    }
    $tokenDaclResult = [ProcessSingletonProbeNative]::ProbeTokenDefaultDacl()
    $result.tokenDefaultDacl = [ordered]@{
        succeeded = $tokenDaclResult.Succeeded
        win32Error = $tokenDaclResult.Win32Error
        lastError = $tokenDaclResult.LastError
        daclDetailsOmitted = $true
        detail = $tokenDaclResult.Detail
    }
    $directoryResult = [ProcessSingletonProbeNative]::ProbeSessionObjectDirectory($sessionId)
    $result.sessionObjectDirectory = [ordered]@{
        succeeded = $directoryResult.Succeeded
        win32Error = $directoryResult.Win32Error
        securityDescriptorDetailsOmitted = $true
        detail = $directoryResult.Detail
        rightsRequested = 'DIRECTORY_QUERY|READ_CONTROL (read-only)'
    }
    $lockPath = Join-Path $ProfileDirectory 'lockfile'
    $lockResult = [ProcessSingletonProbeNative]::ProbeLockFile($lockPath)
    $result.lockFile = [ordered]@{
        succeeded = $lockResult.Succeeded
        win32Error = $lockResult.Win32Error
        lastError = $lockResult.LastError
        detail = $lockResult.Detail
    }
    if ($lockResult.Succeeded) {
        $result.lockFileDeletedAfterClose = -not (Test-Path -LiteralPath $lockPath)
        if (-not $result.lockFileDeletedAfterClose) { $result.errors += 'DELETE_ON_CLOSE lockfile still exists after its handle was closed.' }
    }
    $windowResult = [ProcessSingletonProbeNative]::ProbeMessageWindow($ProfileDirectory)
    $result.messageWindow = [ordered]@{
        succeeded = $windowResult.Succeeded
        win32Error = $windowResult.Win32Error
        lastError = $windowResult.LastError
        detail = $windowResult.Detail
    }
    $localFixedMutexObserved = $mutexResult.Succeeded -or $mutexResult.Win32Error -in @(2, 5)
    $globalFixedMutexObserved = $globalMutexResult.Succeeded -or $globalMutexResult.Win32Error -in @(2, 5)
    if (-not $localFixedMutexObserved) { $result.errors += $mutexResult.Detail }
    if (-not $globalFixedMutexObserved) { $result.errors += $globalMutexResult.Detail }
    if (-not $randomMutexResult.Succeeded) { $result.errors += $randomMutexResult.Detail }
    if (-not $unnamedMutexResult.Succeeded) { $result.errors += $unnamedMutexResult.Detail }
    if (-not $explicitMutexResult.Succeeded) { $result.errors += $explicitMutexResult.Detail }
    if (-not $lockResult.Succeeded) { $result.errors += $lockResult.Detail }
    if (-not $windowResult.Succeeded) { $result.errors += $windowResult.Detail }
    if ($result.lockFileDeletedAfterClose -and $localFixedMutexObserved -and $globalFixedMutexObserved -and $randomMutexResult.Succeeded -and $unnamedMutexResult.Succeeded -and $explicitMutexResult.Succeeded -and $lockResult.Succeeded -and $windowResult.Succeeded) { $result.status = 'pass' }

    $launchParameters = @($ScreenshotPath, $ChromiumStdoutPath, $ChromiumStderrPath)
    if (-not [string]::IsNullOrWhiteSpace($ChromiumPath)) {
        if ($result.status -ne 'pass') { throw 'Chromium launch was requested, but one or more ProcessSingleton API probes failed.' }
        if ($launchParameters | Where-Object { [string]::IsNullOrWhiteSpace($_) }) { throw 'Chromium launch requires screenshot, stdout, and stderr paths.' }
        if (-not (Test-Path -LiteralPath $ChromiumPath -PathType Leaf)) { throw 'Pinned Chromium executable is missing.' }
        foreach ($path in $launchParameters) {
            if (Test-Path -LiteralPath $path) { throw "Chromium diagnostic output already exists: $path" }
        }

        $launch = [ordered]@{
            executablePath = [IO.Path]::GetFullPath($ChromiumPath)
            userDataDirectory = [IO.Path]::GetFullPath($ProfileDirectory)
            screenshotPath = [IO.Path]::GetFullPath($ScreenshotPath)
            stdoutPath = [IO.Path]::GetFullPath($ChromiumStdoutPath)
            stderrPath = [IO.Path]::GetFullPath($ChromiumStderrPath)
            processId = $null
            exitCode = $null
            timedOut = $false
            screenshotExists = $false
            screenshotLength = 0L
            stdoutTail = ''
            stderrTail = ''
            status = 'not_started'
            errors = @()
        }
        $chrome = $null
        try {
            # Keep Chromium's normal sandbox and Crashpad behavior. The guest has no network,
            # and the exact profile directory and token used by the API probes are reused.
            $chromeArguments = '--headless=new --disable-gpu --disable-background-networking --disable-component-update --disable-extensions --disable-sync --no-first-run --no-default-browser-check --enable-logging=stderr --user-data-dir="' + $launch.userDataDirectory + '" --window-size=640,480 --screenshot="' + $launch.screenshotPath + '" about:blank'
            $chrome = Start-Process -FilePath $launch.executablePath -ArgumentList $chromeArguments -WorkingDirectory (Split-Path -Parent $launch.executablePath) -WindowStyle Hidden -PassThru -RedirectStandardOutput $launch.stdoutPath -RedirectStandardError $launch.stderrPath
            $launch.processId = $chrome.Id
            if (-not $chrome.WaitForExit($ChromiumTimeoutSeconds * 1000)) {
                $launch.timedOut = $true
                $launch.errors += "Chromium exceeded the bounded $ChromiumTimeoutSeconds second wait."
            }
            else {
                $chrome.Refresh()
                $launch.exitCode = $chrome.ExitCode
            }
            $launch.screenshotExists = Test-Path -LiteralPath $launch.screenshotPath -PathType Leaf
            if ($launch.screenshotExists) { $launch.screenshotLength = (Get-Item -LiteralPath $launch.screenshotPath).Length }
            if (Test-Path -LiteralPath $launch.stdoutPath -PathType Leaf) { $launch.stdoutTail = (Get-Content -LiteralPath $launch.stdoutPath -Tail 80 -ErrorAction SilentlyContinue) -join "`n" }
            if (Test-Path -LiteralPath $launch.stderrPath -PathType Leaf) { $launch.stderrTail = (Get-Content -LiteralPath $launch.stderrPath -Tail 100 -ErrorAction SilentlyContinue) -join "`n" }
            if (-not $launch.timedOut -and $launch.exitCode -eq 0 -and $launch.screenshotExists -and $launch.screenshotLength -gt 0) {
                $launch.status = 'pass'
            }
            else {
                $launch.status = 'fail'
                if (-not $launch.timedOut -and $launch.exitCode -ne 0) { $launch.errors += "Chromium exited with code $($launch.exitCode)." }
                if (-not $launch.screenshotExists -or $launch.screenshotLength -eq 0) { $launch.errors += 'Chromium did not create a non-empty about:blank screenshot.' }
            }
        }
        catch {
            $launch.status = 'fail'
            $launch.errors += $_.Exception.Message
        }
        $result.chromiumLaunch = $launch
        if ($launch.status -ne 'pass') { $result.errors += @($launch.errors) }
    }
}
catch {
    $result.errors += $_.Exception.Message
    if (-not [string]::IsNullOrWhiteSpace($ChromiumPath) -and $null -eq $result.chromiumLaunch) {
        $result.chromiumLaunch = [ordered]@{ status = 'fail'; errors = @($_.Exception.Message) }
    }
}

$parent = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $parent -PathType Container)) { New-Item -ItemType Directory -Path $parent | Out-Null }
[IO.File]::WriteAllText($OutputPath,($result | ConvertTo-Json -Depth 8) + [Environment]::NewLine,[Text.UTF8Encoding]::new($false))
if ($result.status -ne 'pass' -or ($null -ne $result.chromiumLaunch -and $result.chromiumLaunch.status -ne 'pass')) { exit 1 }
exit 0
