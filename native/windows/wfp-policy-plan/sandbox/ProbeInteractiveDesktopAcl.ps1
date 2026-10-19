param(
    [string]$ResultPath = 'C:\sandbox-results\chromium-interactive-desktop-acl.json',
    [guid]$RunToken = [guid]::Empty
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($RunToken -eq [guid]::Empty) { throw 'Pass a fresh RunToken for this Sandbox diagnostic run.' }

$nativeSource = @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;

public static class InteractiveDesktopAclProbe
{
    private const uint ReadControl = 0x00020000;
    private const uint DesktopReadObjects = 0x0001;
    private const uint DesktopWriteObjects = 0x0080;
    private const int UserObjectName = 2;
    private const int TokenGroups = 2;
    private const uint LogonIdGroup = 0xC0000000;
    private const uint ErrorInsufficientBuffer = 122;
    private const uint MaximumTokenInformationBytes = 1048576;

    [StructLayout(LayoutKind.Sequential)]
    private struct SidAndAttributes
    {
        public IntPtr Sid;
        public uint Attributes;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct TokenGroupsHeader
    {
        public uint GroupCount;
        public SidAndAttributes FirstGroup;
    }

    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr GetProcessWindowStation();

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr OpenDesktop(string name, uint flags, bool inherit, uint desiredAccess);

    [DllImport("kernel32.dll")]
    private static extern IntPtr GetCurrentProcess();

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr handle);

    [DllImport("advapi32.dll", SetLastError = true)]
    private static extern bool OpenProcessToken(IntPtr process, uint desiredAccess, out IntPtr token);

    [DllImport("advapi32.dll", SetLastError = true)]
    private static extern bool GetTokenInformation(IntPtr token, int tokenInformationClass, IntPtr information, uint length, out uint needed);

    [DllImport("user32.dll", EntryPoint = "GetUserObjectInformationW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool GetUserObjectInformation(IntPtr handle, int index, IntPtr buffer, uint length, out uint needed);

    [DllImport("user32.dll", EntryPoint = "GetUserObjectSecurity", SetLastError = true)]
    private static extern bool GetUserObjectSecurity(IntPtr handle, ref uint securityInformation, byte[] descriptor, uint length, out uint needed);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool CloseDesktop(IntPtr handle);

    public static string GetObjectName(IntPtr handle)
    {
        uint needed;
        GetUserObjectInformation(handle, UserObjectName, IntPtr.Zero, 0, out needed);
        int error = Marshal.GetLastWin32Error();
        if (needed == 0 || (error != 122 && error != 0))
            throw new System.ComponentModel.Win32Exception(error, "GetUserObjectInformationW(UOI_NAME)");

        IntPtr buffer = Marshal.AllocHGlobal((int)needed);
        try
        {
            if (!GetUserObjectInformation(handle, UserObjectName, buffer, needed, out needed))
                throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "GetUserObjectInformationW(UOI_NAME)");
            return Marshal.PtrToStringUni(buffer);
        }
        finally { Marshal.FreeHGlobal(buffer); }
    }

    public static string GetSddl(IntPtr handle)
    {
        uint securityInformation = 0x00000007; // OWNER_SECURITY_INFORMATION | GROUP_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION
        uint needed;
        GetUserObjectSecurity(handle, ref securityInformation, null, 0, out needed);
        int error = Marshal.GetLastWin32Error();
        if (needed == 0 || error != 122)
            throw new System.ComponentModel.Win32Exception(error, "GetUserObjectSecurityW(size)");

        byte[] descriptor = new byte[needed];
        if (!GetUserObjectSecurity(handle, ref securityInformation, descriptor, (uint)descriptor.Length, out needed))
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "GetUserObjectSecurityW(data)");
        return new RawSecurityDescriptor(descriptor, 0).GetSddlForm(
            AccessControlSections.Owner | AccessControlSections.Group | AccessControlSections.Access);
    }

    public static IntPtr GetStation() { return GetProcessWindowStation(); }
    public static IntPtr OpenDefaultDesktop() { return OpenDesktop("Default", 0, false, ReadControl | DesktopReadObjects | DesktopWriteObjects); }
    public static int LastError { get { return Marshal.GetLastWin32Error(); } }
    public static void CloseDesk(IntPtr handle) { if (handle != IntPtr.Zero) CloseDesktop(handle); }

    public static Dictionary<string, object> GetCurrentTokenSnapshot()
    {
        const uint TokenQuery = 0x0008;
        IntPtr token;
        if (!OpenProcessToken(GetCurrentProcess(), TokenQuery, out token))
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "OpenProcessToken(TokenSnapshot)");
        try
        {
            uint tokenElevation = ReadTokenUInt32(token, 20, "TokenElevation");
            if (tokenElevation > 1) throw new InvalidOperationException("TokenElevation returned an invalid value.");
            Dictionary<string, object> snapshot = new Dictionary<string, object>();
            snapshot["user_sid"] = ReadTokenSid(token, 1, "TokenUser");
            snapshot["logon_sids"] = ReadLogonSids(token);
            snapshot["session_id"] = ReadTokenUInt32(token, 12, "TokenSessionId");
            snapshot["token_type"] = ReadTokenUInt32(token, 8, "TokenType").ToString(System.Globalization.CultureInfo.InvariantCulture);
            snapshot["token_elevation_type"] = ReadTokenUInt32(token, 18, "TokenElevationType").ToString(System.Globalization.CultureInfo.InvariantCulture);
            snapshot["token_elevation"] = tokenElevation == 1;
            snapshot["integrity_sid"] = ReadTokenSid(token, 25, "TokenIntegrityLevel");
            return snapshot;
        }
        finally { CloseHandle(token); }
    }

    private static uint ReadTokenUInt32(IntPtr token, int informationClass, string name)
    {
        uint allocatedBytes = sizeof(uint);
        IntPtr buffer = Marshal.AllocHGlobal(checked((int)allocatedBytes));
        try
        {
            uint returnedBytes;
            if (!GetTokenInformation(token, informationClass, buffer, allocatedBytes, out returnedBytes))
            {
                int error = Marshal.GetLastWin32Error();
                throw new System.ComponentModel.Win32Exception(error, "GetTokenInformation(" + name + ",data; Win32 " + error + ")");
            }
            if (returnedBytes < sizeof(uint) || returnedBytes > allocatedBytes)
                throw new InvalidOperationException("GetTokenInformation(" + name + ") returned an invalid length.");
            return unchecked((uint)Marshal.ReadInt32(buffer));
        }
        finally { Marshal.FreeHGlobal(buffer); }
    }

    private static string ReadTokenSid(IntPtr token, int informationClass, string name)
    {
        uint needed;
        GetTokenInformation(token, informationClass, IntPtr.Zero, 0, out needed);
        int error = Marshal.GetLastWin32Error();
        if (error != ErrorInsufficientBuffer || needed < (uint)IntPtr.Size || needed > MaximumTokenInformationBytes)
            throw new System.ComponentModel.Win32Exception(error, "GetTokenInformation(" + name + ",size)");
        uint allocatedBytes = needed;
        IntPtr buffer = Marshal.AllocHGlobal(checked((int)allocatedBytes));
        try
        {
            uint returnedBytes;
            if (!GetTokenInformation(token, informationClass, buffer, allocatedBytes, out returnedBytes))
                throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "GetTokenInformation(" + name + ",data)");
            if (returnedBytes < (uint)IntPtr.Size || returnedBytes > allocatedBytes)
                throw new InvalidOperationException("GetTokenInformation(" + name + ") returned an invalid length.");
            IntPtr sid = Marshal.ReadIntPtr(buffer);
            if (sid == IntPtr.Zero) throw new InvalidOperationException("GetTokenInformation(" + name + ") returned a null SID.");
            return new SecurityIdentifier(sid).Value;
        }
        finally { Marshal.FreeHGlobal(buffer); }
    }

    private static string[] ReadLogonSids(IntPtr token)
    {
        uint needed;
        GetTokenInformation(token, TokenGroups, IntPtr.Zero, 0, out needed);
        int error = Marshal.GetLastWin32Error();
        int groupsOffset = Marshal.OffsetOf(typeof(TokenGroupsHeader), "FirstGroup").ToInt32();
        int groupStride = Marshal.SizeOf(typeof(SidAndAttributes));
        if (error != ErrorInsufficientBuffer || needed <= 0 || needed > MaximumTokenInformationBytes || needed < groupsOffset)
            throw new System.ComponentModel.Win32Exception(error, "GetTokenInformation(TokenGroups,size)");
        uint allocatedBytes = needed;
        IntPtr buffer = Marshal.AllocHGlobal(checked((int)allocatedBytes));
        try
        {
            uint returnedBytes;
            if (!GetTokenInformation(token, TokenGroups, buffer, allocatedBytes, out returnedBytes))
                throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "GetTokenInformation(TokenGroups,data)");
            if (returnedBytes < groupsOffset || returnedBytes > allocatedBytes)
                throw new InvalidOperationException("GetTokenInformation(TokenGroups) returned an invalid length.");
            uint groupCount = unchecked((uint)Marshal.ReadInt32(buffer));
            long availableBytes = returnedBytes - (long)groupsOffset;
            if (groupCount > availableBytes / groupStride)
                throw new InvalidOperationException("GetTokenInformation(TokenGroups) returned an invalid group count.");

            List<string> logonSids = new List<string>();
            for (uint index = 0; index < groupCount; index++)
            {
                int entryOffset = checked(groupsOffset + checked((int)index * groupStride));
                IntPtr entry = IntPtr.Add(buffer, entryOffset);
                SidAndAttributes group = (SidAndAttributes)Marshal.PtrToStructure(entry, typeof(SidAndAttributes));
                if ((group.Attributes & LogonIdGroup) != LogonIdGroup) continue;
                if (group.Sid == IntPtr.Zero)
                    throw new InvalidOperationException("TokenGroups contains a null Logon SID.");
                logonSids.Add(new SecurityIdentifier(group.Sid).Value);
            }
            return logonSids.ToArray();
        }
        finally { Marshal.FreeHGlobal(buffer); }
    }
}
'@

$identity = $null
$station = [IntPtr]::Zero
$desktop = [IntPtr]::Zero
$stage = 'initialize'
$result = [ordered]@{
    reportKind = 'sandbox-interactive-desktop-acl-probe'
    capturedAtUtc = [DateTime]::UtcNow.ToString('o')
    runToken = $RunToken.ToString('D')
    userSid = $null
    logonSid = $null
    logonSidCount = 0
    sessionId = $null
    token = [ordered]@{
        token_type = $null
        token_elevation_type = $null
        token_elevation = $null
        integrity_sid = $null
    }
    windowStationName = $null
    windowStationSddl = $null
    desktopName = $null
    desktopSddl = $null
    desktopOpenError = 0
    errors = @()
    failureStage = $null
    status = 'fail'
}

try {
    if (-not ('InteractiveDesktopAclProbe' -as [type])) {
        Add-Type -TypeDefinition $nativeSource -Language CSharp
    }

    $stage = 'current_identity'
    $tokenSnapshot = [InteractiveDesktopAclProbe]::GetCurrentTokenSnapshot()
    $result.userSid = [string]$tokenSnapshot['user_sid']
    $logonSids = @($tokenSnapshot['logon_sids'])
    $result.logonSidCount = $logonSids.Count
    if ($logonSids.Count -ne 1) { throw "Expected exactly one logon SID in the current token; found $($logonSids.Count)." }
    if ([string]$logonSids[0] -notmatch '^S-1-5-5-[0-9]+-[0-9]+$') { throw 'The unique SE_GROUP_LOGON_ID SID has an invalid form.' }
    $result.logonSid = $logonSids[0]
    $result.sessionId = [int]$tokenSnapshot['session_id']
    $result.token.token_type = [string]$tokenSnapshot['token_type']
    $result.token.token_elevation_type = [string]$tokenSnapshot['token_elevation_type']
    $result.token.token_elevation = [bool]$tokenSnapshot['token_elevation']
    $result.token.integrity_sid = [string]$tokenSnapshot['integrity_sid']

    $stage = 'window_station'
    $station = [InteractiveDesktopAclProbe]::GetStation()
    if ($station -eq [IntPtr]::Zero) { throw [ComponentModel.Win32Exception]::new([InteractiveDesktopAclProbe]::LastError, 'GetProcessWindowStation') }
    $result.windowStationName = [InteractiveDesktopAclProbe]::GetObjectName($station)
    $result.windowStationSddl = [InteractiveDesktopAclProbe]::GetSddl($station)

    $stage = 'default_desktop'
    $desktop = [InteractiveDesktopAclProbe]::OpenDefaultDesktop()
    if ($desktop -eq [IntPtr]::Zero) {
        $result.desktopOpenError = [InteractiveDesktopAclProbe]::LastError
        throw [ComponentModel.Win32Exception]::new($result.desktopOpenError, 'OpenDesktopW(Default, READ_CONTROL|DESKTOP_READOBJECTS|DESKTOP_WRITEOBJECTS)')
    }
    $result.desktopName = [InteractiveDesktopAclProbe]::GetObjectName($desktop)
    $result.desktopSddl = [InteractiveDesktopAclProbe]::GetSddl($desktop)
    $result.status = 'pass'
}
catch {
    $result.errors += $_.Exception.Message
    $result.failureStage = $stage
}
finally {
    [InteractiveDesktopAclProbe]::CloseDesk($desktop)
}

$directory = Split-Path -Parent $ResultPath
if (-not (Test-Path -LiteralPath $directory -PathType Container)) { New-Item -ItemType Directory -Path $directory | Out-Null }
[IO.File]::WriteAllText($ResultPath,($result | ConvertTo-Json -Depth 5) + [Environment]::NewLine,[Text.UTF8Encoding]::new($false))
if ($result.status -ne 'pass') { exit 1 }
