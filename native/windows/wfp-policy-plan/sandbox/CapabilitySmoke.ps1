param([string]$ResultPath = 'C:\sandbox-results\wfp-capability-smoke.json')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$resultPath = $ResultPath
$result = [ordered]@{
    reportKind = 'wfp-read-only-capability-smoke'
    capturedAtUtc = [DateTime]::UtcNow.ToString('o')
    runContext = $null
    osVersion = [Environment]::OSVersion.Version.ToString()
    processArchitecture = [Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString()
    isAdministrator = $false
    bfeState = $null
    wfpEngineOpenAttempts = [System.Collections.Generic.List[object]]::new()
    wfpEngineOpenWin32Code = $null
    filterEnumCreateWin32Code = $null
    filterEnumWin32Code = $null
    enumeratedFilterCount = $null
    sdkHeaderPathPresent = $false
    errors = [System.Collections.Generic.List[string]]::new()
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
$result.isAdministrator = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$result.runContext = if ($identity.User.Value -eq 'S-1-5-18') { 'SYSTEM' } else { 'sandbox-default-account' }

try {
    $result.bfeState = (Get-Service -Name BFE -ErrorAction Stop).Status.ToString()
}
catch {
    $result.errors.Add("BFE query: $($_.Exception.Message)")
}

$sdkHeaderCandidates = @(
    "$env:ProgramFiles(x86)\Windows Kits\10\Include\$($env:WindowsSDKVersion)\um\fwpmu.h",
    "$env:ProgramFiles(x86)\Windows Kits\10\Include\$($env:WindowsSDKVersion)\shared\fwptypes.h"
)
$result.sdkHeaderPathPresent = @($sdkHeaderCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) }).Count -gt 0

$nativeSource = @'
using System;
using System.Runtime.InteropServices;

public static class ReadOnlyWfpProbe
{
    [DllImport("fwpuclnt.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    public static extern uint FwpmEngineOpen0(IntPtr serverName, uint authenticationService, IntPtr authenticationIdentity, IntPtr session, out IntPtr engineHandle);

    [DllImport("fwpuclnt.dll", ExactSpelling = true)]
    public static extern uint FwpmEngineClose0(IntPtr engineHandle);

    [DllImport("fwpuclnt.dll", ExactSpelling = true)]
    public static extern uint FwpmFilterCreateEnumHandle0(IntPtr engineHandle, IntPtr enumTemplate, out IntPtr enumHandle);

    [DllImport("fwpuclnt.dll", ExactSpelling = true)]
    public static extern uint FwpmFilterEnum0(IntPtr engineHandle, IntPtr enumHandle, uint entriesRequested, out IntPtr entries, out uint entriesReturned);

    [DllImport("fwpuclnt.dll", ExactSpelling = true)]
    public static extern uint FwpmFilterDestroyEnumHandle0(IntPtr engineHandle, IntPtr enumHandle);

    [DllImport("fwpuclnt.dll", ExactSpelling = true)]
    public static extern void FwpmFreeMemory0(ref IntPtr memory);
}
'@

$engineHandle = [IntPtr]::Zero
$enumHandle = [IntPtr]::Zero
$entries = [IntPtr]::Zero
try {
    Add-Type -TypeDefinition $nativeSource -ErrorAction Stop
    # Try both documented services: RPC_C_AUTHN_WINNT = 10 and RPC_C_AUTHN_DEFAULT = 0.
    # IntPtr.Zero guarantees the optional serverName is a native NULL pointer.
    # Keep one successful, default non-transactional engine session for read-only enumeration.
    foreach ($authnService in @(10, 0)) {
        $candidateHandle = [IntPtr]::Zero
        $openCode = [ReadOnlyWfpProbe]::FwpmEngineOpen0([IntPtr]::Zero, [uint32]$authnService, [IntPtr]::Zero, [IntPtr]::Zero, [ref]$candidateHandle)
        $result.wfpEngineOpenAttempts.Add([ordered]@{ authenticationService = $authnService; win32Code = $openCode })
        if ($openCode -eq 0) {
            if ($engineHandle -eq [IntPtr]::Zero) {
                $engineHandle = $candidateHandle
            }
            else {
                [void][ReadOnlyWfpProbe]::FwpmEngineClose0($candidateHandle)
            }
        }
        elseif ($candidateHandle -ne [IntPtr]::Zero) {
            [void][ReadOnlyWfpProbe]::FwpmEngineClose0($candidateHandle)
        }
    }
    $result.wfpEngineOpenWin32Code = if ($engineHandle -ne [IntPtr]::Zero) { 0 } else { $result.wfpEngineOpenAttempts[-1].win32Code }
    if ($result.wfpEngineOpenWin32Code -eq 0) {
        $result.filterEnumCreateWin32Code = [ReadOnlyWfpProbe]::FwpmFilterCreateEnumHandle0($engineHandle, [IntPtr]::Zero, [ref]$enumHandle)
        if ($result.filterEnumCreateWin32Code -eq 0) {
            $count = [uint32]0
            $result.filterEnumWin32Code = [ReadOnlyWfpProbe]::FwpmFilterEnum0($engineHandle, $enumHandle, 1, [ref]$entries, [ref]$count)
            if ($result.filterEnumWin32Code -eq 0) {
                $result.enumeratedFilterCount = [int]$count
            }
        }
    }
}
catch {
    $result.errors.Add("WFP read-only query: $($_.Exception.Message)")
}
finally {
    if ($entries -ne [IntPtr]::Zero) {
        [ReadOnlyWfpProbe]::FwpmFreeMemory0([ref]$entries)
    }
    if ($enumHandle -ne [IntPtr]::Zero -and $engineHandle -ne [IntPtr]::Zero) {
        [void][ReadOnlyWfpProbe]::FwpmFilterDestroyEnumHandle0($engineHandle, $enumHandle)
    }
    if ($engineHandle -ne [IntPtr]::Zero) {
        [void][ReadOnlyWfpProbe]::FwpmEngineClose0($engineHandle)
    }
}

$result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $resultPath -Encoding UTF8
Write-Output "Read-only WFP capability report written to $resultPath"
