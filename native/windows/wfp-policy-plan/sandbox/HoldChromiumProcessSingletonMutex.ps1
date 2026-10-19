param(
    [Parameter(Mandatory = $true)]
    [string]$RequestPath,
    [Parameter(Mandatory = $true)]
    [string]$ReadyPath,
    [Parameter(Mandatory = $true)]
    [string]$ReleasePath,
    [ValidateRange(15, 180)]
    [int]$ReleaseTimeoutSeconds = 90
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$source = @'
using System;
using System.Runtime.InteropServices;
using System.Security.AccessControl;

[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
public struct ChromiumSingletonMutexSecurityAttributes
{
    public int Length;
    public IntPtr SecurityDescriptor;
    [MarshalAs(UnmanagedType.Bool)] public bool InheritHandle;
}

public static class ChromiumSingletonMutexLeaseNative
{
    [DllImport("advapi32.dll", EntryPoint = "ConvertStringSecurityDescriptorToSecurityDescriptorW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool ConvertStringSecurityDescriptorToSecurityDescriptor(string sddl, uint revision, out IntPtr descriptor, out uint size);
    [DllImport("kernel32.dll", EntryPoint = "CreateMutexW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr CreateMutex(ref ChromiumSingletonMutexSecurityAttributes attributes, bool initialOwner, string name);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern void SetLastError(uint error);
    [DllImport("advapi32.dll", EntryPoint = "GetKernelObjectSecurity", SetLastError = true)]
    private static extern bool GetKernelObjectSecurity(IntPtr handle, uint securityInformation, byte[] descriptor, uint length, out uint needed);
    [DllImport("kernel32.dll", EntryPoint = "LocalFree", SetLastError = true)] private static extern IntPtr LocalFree(IntPtr memory);
    [DllImport("kernel32.dll", EntryPoint = "CloseHandle", SetLastError = true)] private static extern bool CloseHandle(IntPtr handle);

    public static IntPtr Create(string name, string targetSid, out int win32Error)
    {
        IntPtr descriptor = IntPtr.Zero;
        try
        {
            string sddl = "D:P(A;;0x001F0001;;;S-1-5-18)(A;;0x001F0001;;;" + targetSid + ")";
            uint descriptorSize;
            if (!ConvertStringSecurityDescriptorToSecurityDescriptor(sddl, 1, out descriptor, out descriptorSize))
                throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "ConvertStringSecurityDescriptorToSecurityDescriptorW");
            ChromiumSingletonMutexSecurityAttributes attributes = new ChromiumSingletonMutexSecurityAttributes
            {
                Length = Marshal.SizeOf(typeof(ChromiumSingletonMutexSecurityAttributes)),
                SecurityDescriptor = descriptor,
                InheritHandle = false
            };
            SetLastError(0);
            IntPtr handle = CreateMutex(ref attributes, false, name);
            win32Error = Marshal.GetLastWin32Error();
            return handle;
        }
        finally
        {
            if (descriptor != IntPtr.Zero) LocalFree(descriptor);
        }
    }

    public static string ReadSddl(IntPtr handle)
    {
        const uint ownerGroupDacl = 0x00000001 | 0x00000002 | 0x00000004;
        uint needed;
        GetKernelObjectSecurity(handle, ownerGroupDacl, null, 0, out needed);
        int error = Marshal.GetLastWin32Error();
        if (needed == 0 || error != 122) throw new System.ComponentModel.Win32Exception(error, "GetKernelObjectSecurity(size)");
        byte[] bytes = new byte[needed];
        if (!GetKernelObjectSecurity(handle, ownerGroupDacl, bytes, (uint)bytes.Length, out needed))
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "GetKernelObjectSecurity(data)");
        RawSecurityDescriptor descriptor = new RawSecurityDescriptor(bytes, 0);
        return descriptor.GetSddlForm(AccessControlSections.Owner | AccessControlSections.Group | AccessControlSections.Access);
    }

    public static void Close(long handle)
    {
        if (handle != 0 && !CloseHandle(new IntPtr(handle)))
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "CloseHandle(mutex lease)");
    }
}
'@

if (-not ('ChromiumSingletonMutexLeaseNative' -as [type])) { Add-Type -TypeDefinition $source -Language CSharp }

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$sessionId = [uint32][Diagnostics.Process]::GetCurrentProcess().SessionId
$mutexName = 'Local\ChromeProcessSingletonStartup!'
$result = [ordered]@{
    reportKind = 'chromium-process-singleton-mutex-lease'
    capturedAtUtc = [DateTime]::UtcNow.ToString('o')
    runToken = $null
    userSid = $identity.User.Value
    sessionId = $sessionId
    targetUserSid = $null
    targetSessionId = $null
    mutexName = $mutexName
    createdNew = $false
    initialOwner = $false
    mutexOwned = $false
    win32Error = $null
    handle = 0L
    securityDescriptorSddl = $null
    releaseObserved = $false
    errors = @()
    status = 'fail'
}
$handle = IntPtr.Zero

try {
    if ($identity.User.Value -eq 'S-1-5-18' -or $sessionId -eq 0) { throw 'Mutex lease helper must run as ExistingLogin in its interactive Sandbox session.' }
    if (-not (Test-Path -LiteralPath $RequestPath -PathType Leaf)) { throw 'Mutex lease request is missing.' }
    $request = Get-Content -LiteralPath $RequestPath -Raw | ConvertFrom-Json
    $result.runToken = [string]$request.runToken
    $result.targetUserSid = [string]$request.targetUserSid
    $result.targetSessionId = [uint32]$request.targetSessionId
    $requestTime = [DateTime]::Parse($request.requestedAtUtc).ToUniversalTime()
    if ($request.reportKind -ne 'chromium-process-singleton-mutex-precreate-request' -or $request.runToken -notmatch '^[0-9a-fA-F-]{36}$' -or $requestTime -lt [DateTime]::UtcNow.AddMinutes(-2) -or $requestTime -gt [DateTime]::UtcNow.AddSeconds(10)) {
        throw 'Mutex lease request has an invalid kind, token, or timestamp.'
    }
    if ([uint32]$request.targetSessionId -ne $sessionId) { throw 'Mutex lease request targets a different session.' }
    $targetSid = [Security.Principal.SecurityIdentifier]::new([string]$request.targetUserSid)
    if ($targetSid.Value -eq $identity.User.Value -or $targetSid.Value -eq 'S-1-5-18') { throw 'Mutex lease target SID must be the disposable low-privilege account.' }
    $existingChromium = @(Get-Process -Name 'chrome' -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq $sessionId })
    if ($existingChromium.Count -gt 0) { throw 'A chrome.exe process already exists in the target Sandbox session.' }

    $win32Error = 0
    $handle = [ChromiumSingletonMutexLeaseNative]::Create($mutexName,$targetSid.Value,[ref]$win32Error)
    $result.win32Error = $win32Error
    if ($handle -eq [IntPtr]::Zero) { throw "CreateMutexW failed with Win32 $win32Error." }
    $result.handle = $handle.ToInt64()
    $result.createdNew = $win32Error -ne 183
    if (-not $result.createdNew) { throw 'The named mutex already existed; refusing to adopt an object with an unknown prior DACL.' }
    $result.securityDescriptorSddl = [ChromiumSingletonMutexLeaseNative]::ReadSddl($handle)
    $result.status = 'ready'
    [IO.File]::WriteAllText($ReadyPath,($result | ConvertTo-Json -Depth 6) + [Environment]::NewLine,[Text.UTF8Encoding]::new($false))

    $deadline = [DateTime]::UtcNow.AddSeconds($ReleaseTimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline -and -not (Test-Path -LiteralPath $ReleasePath -PathType Leaf)) { Start-Sleep -Milliseconds 100 }
    $result.releaseObserved = Test-Path -LiteralPath $ReleasePath -PathType Leaf
    if (-not $result.releaseObserved) { throw 'Timed out waiting for the host to release the temporary mutex handle.' }
}
catch {
    $result.errors += $_.Exception.Message
}
finally {
    if ($handle -ne [IntPtr]::Zero) {
        try { [ChromiumSingletonMutexLeaseNative]::Close($handle.ToInt64()); $result.handle = 0L }
        catch { $result.errors += $_.Exception.Message }
    }
    if ($result.status -eq 'ready' -and $result.releaseObserved -and $result.errors.Count -eq 0) { $result.status = 'released' }
    elseif ($result.status -eq 'ready') { $result.status = 'release-failed' }
    $result.releasedAtUtc = [DateTime]::UtcNow.ToString('o')
    $directory = Split-Path -Parent $ReadyPath
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) { New-Item -ItemType Directory -Path $directory | Out-Null }
    [IO.File]::WriteAllText($ReadyPath,($result | ConvertTo-Json -Depth 6) + [Environment]::NewLine,[Text.UTF8Encoding]::new($false))
}

if ($result.status -ne 'released') { exit 1 }
exit 0
