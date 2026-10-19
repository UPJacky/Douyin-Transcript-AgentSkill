using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text.Json;
using Microsoft.Win32.SafeHandles;

namespace DouyinTranscript.LeaseJobHelper;

internal readonly record struct DesktopObjectAccessResult(
    bool ApiSucceeded,
    bool AccessGranted,
    uint DesiredAccess,
    uint GrantedAccess,
    int? Win32Error);

internal static class DesktopAccessCheck
{
    private readonly record struct EvidenceBinding(bool SameUserSidAsTarget, bool SameLogonSidAsTarget);

    private const uint WinStaAllAccess = 0x000F037F;
    private const uint DesktopAllAccess = 0x000F01FF;
    private const uint DirectoryCreateObject = 0x00000004;
    private const uint ErrorInsufficientBuffer = 122;
    private const uint MaximumPrivilegeSetBytes = 65536;
    private const uint SecurityInformationOwnerGroupDacl = 0x00000007;
    private const uint ReadControl = 0x00020000;
    private const uint ObjectAttributesCaseInsensitive = 0x00000040;
    private const uint StatusBufferOverflow = 0x80000005;
    private const uint StatusBufferTooSmall = 0xC0000023;
    private const int MaximumSecurityDescriptorBytes = 65536;

    private static readonly NativeMethods.GenericMapping WindowStationMapping = new()
    {
        GenericRead = 0x00020303,
        GenericWrite = 0x0002001C,
        GenericExecute = 0x00020060,
        GenericAll = WinStaAllAccess,
    };

    private static readonly NativeMethods.GenericMapping DesktopMapping = new()
    {
        GenericRead = 0x00020041,
        GenericWrite = 0x000200BE,
        GenericExecute = 0x00020100,
        GenericAll = DesktopAllAccess,
    };

    private static readonly NativeMethods.GenericMapping BaseNamedObjectsDirectoryMapping = new()
    {
        GenericRead = 0x00020003,
        GenericWrite = 0x0002000C,
        GenericExecute = 0x00020002,
        GenericAll = 0x000F000F,
    };

    [StructLayout(LayoutKind.Sequential)]
    private struct UnicodeString
    {
        public ushort Length;
        public ushort MaximumLength;
        public IntPtr Buffer;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct ObjectAttributes
    {
        public uint Length;
        public IntPtr RootDirectory;
        public IntPtr ObjectName;
        public uint Attributes;
        public IntPtr SecurityDescriptor;
        public IntPtr SecurityQualityOfService;
    }

    private sealed class SafeObjectDirectoryHandle : SafeHandleZeroOrMinusOneIsInvalid
    {
        private SafeObjectDirectoryHandle() : base(true) { }

        protected override bool ReleaseHandle() => NtClose(handle) >= 0;
    }

    [DllImport("ntdll.dll")]
    private static extern int NtOpenDirectoryObject(out SafeObjectDirectoryHandle directoryHandle,
        uint desiredAccess, ref ObjectAttributes objectAttributes);

    [DllImport("ntdll.dll")]
    private static extern int NtQuerySecurityObject(SafeObjectDirectoryHandle handle, uint securityInformation, byte[]? securityDescriptor,
        uint length, out uint resultLength);

    [DllImport("ntdll.dll")]
    private static extern int NtClose(IntPtr handle);

    [DllImport("ntdll.dll")]
    private static extern uint RtlNtStatusToDosError(int status);

    internal static Dictionary<string, object?> EvaluateEvidence(
        string evidencePath,
        string evidenceDirectory,
        string expectedRunId,
        SafeAccessTokenHandle targetToken,
        string targetUserSid,
        string targetLogonSid,
        int targetSessionId)
    {
        string canonicalPath = Path.GetFullPath(evidencePath);
        string canonicalDirectory = Path.GetFullPath(evidenceDirectory).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        if (!string.Equals(Path.GetDirectoryName(canonicalPath)?.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar),
                canonicalDirectory, StringComparison.OrdinalIgnoreCase))
        {
            throw new NativeApiException("DesktopAclEvidence.MustBeInEvidenceDirectory", NativeMethods.ErrorAccessDenied);
        }
        var info = new FileInfo(canonicalPath);
        if (!info.Exists || info.Length is <= 0 or > 65536)
        {
            throw new NativeApiException("DesktopAclEvidence.MissingOrInvalidSize", NativeMethods.ErrorNotFound);
        }

        using JsonDocument document = JsonDocument.Parse(File.ReadAllBytes(canonicalPath));
        JsonElement root = document.RootElement;
        string runToken = ReadRequiredString(root, "runToken");
        string status = ReadRequiredString(root, "status");
        string stationName = ReadRequiredString(root, "windowStationName");
        string desktopName = ReadRequiredString(root, "desktopName");
        string stationSddl = ReadRequiredString(root, "windowStationSddl");
        string desktopSddl = ReadRequiredString(root, "desktopSddl");
        string probeUserSid = ReadRequiredString(root, "userSid");
        string probeLogonSid = ReadRequiredString(root, "logonSid");
        int probeSessionId = ReadRequiredInt32(root, "sessionId");

        EvidenceBinding binding = ValidateEvidenceContext(runToken, status, stationName, desktopName,
            probeUserSid, probeLogonSid, probeSessionId, expectedRunId, targetUserSid, targetLogonSid, targetSessionId);

        DesktopObjectAccessResult station = CheckSddl(stationSddl, targetToken, WinStaAllAccess, WindowStationMapping);
        DesktopObjectAccessResult desktop = CheckSddl(desktopSddl, targetToken, DesktopAllAccess, DesktopMapping);
        DesktopObjectAccessResult baseNamedObjects = CheckBaseNamedObjectsDirectory(targetToken, targetSessionId);
        return new Dictionary<string, object?>
        {
            ["status"] = station.AccessGranted && desktop.AccessGranted ? "pass" : "denied",
            ["evidence_scope"] = "read-only WinSta0\\Default SDDL snapshot; the target process effective station and desktop remain unobserved",
            ["effective_target_station_observed"] = false,
            ["evidence_path"] = canonicalPath,
            ["run_token_match"] = true,
            ["probe_user_sid"] = probeUserSid,
            ["probe_logon_sid"] = probeLogonSid,
            ["same_user_sid_as_target"] = binding.SameUserSidAsTarget,
            ["same_logon_sid_as_target"] = binding.SameLogonSidAsTarget,
            ["probe_session_id"] = probeSessionId,
            ["target_user_sid"] = targetUserSid,
            ["target_logon_sid"] = targetLogonSid,
            ["target_session_id"] = targetSessionId,
            ["window_station_name"] = stationName,
            ["window_station_sddl"] = stationSddl,
            ["window_station_access_check"] = Format(station),
            ["desktop_name"] = desktopName,
            ["desktop_sddl"] = desktopSddl,
            ["desktop_access_check"] = Format(desktop),
            ["base_named_objects_access_check"] = FormatBaseNamedObjects(baseNamedObjects),
        };
    }

    internal static void ValidateSelfTest()
    {
        const string expectedRunId = "f3c41741-f778-4955-a152-6f2a56be06b8";
        const string reporterUserSid = "S-1-5-21-111111111-222222222-333333333-1001";
        const string targetUserSid = "S-1-5-21-111111111-222222222-333333333-1002";
        const string reporterLogonSid = "S-1-5-5-101-202";
        const string targetLogonSid = "S-1-5-5-303-404";
        EvidenceBinding crossIdentityBinding = ValidateEvidenceContext(expectedRunId, "pass", "WinSta0", "Default",
            reporterUserSid, reporterLogonSid, 17, expectedRunId, targetUserSid, targetLogonSid, 17);
        if (crossIdentityBinding.SameUserSidAsTarget || crossIdentityBinding.SameLogonSidAsTarget)
        {
            throw new InvalidOperationException("A same-session desktop snapshot unexpectedly matched the different target SIDs.");
        }
        AssertEvidenceContextRejected(expectedRunId, "pass", "WinSta0", "Default", reporterUserSid, reporterLogonSid,
            18, expectedRunId, targetUserSid, targetLogonSid, 17, "DesktopAclEvidence.ContextMismatch");
        AssertEvidenceContextRejected(expectedRunId, "pass", "WinSta0", "Default", reporterUserSid, reporterLogonSid,
            17, "ce9822de-574c-44df-81b9-061b0d4b14f8", targetUserSid, targetLogonSid, 17,
            "DesktopAclEvidence.RunTokenMismatch");

        if (!NativeMethods.OpenProcessToken(NativeMethods.GetCurrentProcess(), NativeMethods.TokenQuery | NativeMethods.TokenDuplicate,
                out SafeAccessTokenHandle token))
        {
            throw new NativeApiException("OpenProcessToken.DesktopAccessCheckSelfTest", Marshal.GetLastWin32Error());
        }
        using (token)
        {
            const string allowEveryone = "O:SYG:SYD:(A;;0x000F037F;;;WD)";
            const string denyEveryone = "O:SYG:SYD:(D;;0x000F037F;;;WD)";
            DesktopObjectAccessResult allow = CheckSddl(allowEveryone, token, WinStaAllAccess, WindowStationMapping);
            DesktopObjectAccessResult deny = CheckSddl(denyEveryone, token, WinStaAllAccess, WindowStationMapping);
            if (!allow.AccessGranted || allow.GrantedAccess != WinStaAllAccess || deny.AccessGranted || deny.GrantedAccess != 0)
            {
                throw new InvalidOperationException("Desktop access check self-test did not distinguish allow and deny descriptors.");
            }

            const string allowDirectoryCreateObject = "O:SYG:SYD:(A;;0x00000004;;;WD)";
            const string denyDirectoryCreateObject = "O:SYG:SYD:(D;;0x00000004;;;WD)";
            DesktopObjectAccessResult directoryAllow = CheckSddl(
                allowDirectoryCreateObject, token, DirectoryCreateObject, BaseNamedObjectsDirectoryMapping);
            DesktopObjectAccessResult directoryDeny = CheckSddl(
                denyDirectoryCreateObject, token, DirectoryCreateObject, BaseNamedObjectsDirectoryMapping);
            if (!directoryAllow.AccessGranted || directoryAllow.GrantedAccess != DirectoryCreateObject
                || directoryDeny.AccessGranted || directoryDeny.GrantedAccess != 0)
            {
                throw new InvalidOperationException("BaseNamedObjects directory access check self-test did not distinguish allow and deny descriptors.");
            }
        }
    }

    private static EvidenceBinding ValidateEvidenceContext(
        string runToken,
        string status,
        string stationName,
        string desktopName,
        string probeUserSid,
        string probeLogonSid,
        int probeSessionId,
        string expectedRunId,
        string targetUserSid,
        string targetLogonSid,
        int targetSessionId)
    {
        if (!Guid.TryParseExact(runToken, "D", out Guid parsedRunId)
            || !Guid.TryParseExact(expectedRunId, "D", out Guid expectedGuid)
            || parsedRunId == Guid.Empty || expectedGuid == Guid.Empty
            || parsedRunId != expectedGuid)
        {
            throw new NativeApiException("DesktopAclEvidence.RunTokenMismatch", NativeMethods.ErrorAccessDenied);
        }

        bool validProbeSid;
        bool validProbeLogonSid;
        try
        {
            _ = new SecurityIdentifier(probeUserSid);
            validProbeSid = true;
        }
        catch (ArgumentException)
        {
            validProbeSid = false;
        }
        try
        {
            _ = new SecurityIdentifier(probeLogonSid);
            validProbeLogonSid = probeLogonSid.StartsWith("S-1-5-5-", StringComparison.Ordinal);
        }
        catch (ArgumentException)
        {
            validProbeLogonSid = false;
        }
        if (!string.Equals(status, "pass", StringComparison.Ordinal)
            || !string.Equals(stationName, "WinSta0", StringComparison.OrdinalIgnoreCase)
            || !string.Equals(desktopName, "Default", StringComparison.OrdinalIgnoreCase)
            || probeSessionId != targetSessionId
            || !validProbeSid
            || !validProbeLogonSid)
        {
            throw new NativeApiException("DesktopAclEvidence.ContextMismatch", NativeMethods.ErrorAccessDenied);
        }

        return new EvidenceBinding(
            string.Equals(probeUserSid, targetUserSid, StringComparison.Ordinal),
            string.Equals(probeLogonSid, targetLogonSid, StringComparison.Ordinal));
    }

    private static void AssertEvidenceContextRejected(
        string runToken,
        string status,
        string stationName,
        string desktopName,
        string probeUserSid,
        string probeLogonSid,
        int probeSessionId,
        string expectedRunId,
        string targetUserSid,
        string targetLogonSid,
        int targetSessionId,
        string expectedFailureStage)
    {
        try
        {
            _ = ValidateEvidenceContext(runToken, status, stationName, desktopName, probeUserSid, probeLogonSid,
                probeSessionId, expectedRunId, targetUserSid, targetLogonSid, targetSessionId);
        }
        catch (NativeApiException exception) when (exception.Api == expectedFailureStage)
        {
            return;
        }
        throw new InvalidOperationException($"Desktop evidence self-test expected rejection at {expectedFailureStage}.");
    }

    private static DesktopObjectAccessResult CheckBaseNamedObjectsDirectory(SafeAccessTokenHandle targetToken, int sessionId)
    {
        if (sessionId <= 0)
        {
            throw new NativeApiException("BaseNamedObjects.SessionId.Invalid", NativeMethods.ErrorAccessDenied);
        }

        string path = $"\\Sessions\\{sessionId}\\BaseNamedObjects";
        IntPtr pathBuffer = IntPtr.Zero;
        IntPtr unicodeStringPointer = IntPtr.Zero;
        try
        {
            pathBuffer = Marshal.StringToHGlobalUni(path);
            var objectName = new UnicodeString
            {
                Length = checked((ushort)(path.Length * sizeof(char))),
                MaximumLength = checked((ushort)((path.Length + 1) * sizeof(char))),
                Buffer = pathBuffer,
            };
            unicodeStringPointer = Marshal.AllocHGlobal(Marshal.SizeOf<UnicodeString>());
            Marshal.StructureToPtr(objectName, unicodeStringPointer, false);
            var attributes = new ObjectAttributes
            {
                Length = checked((uint)Marshal.SizeOf<ObjectAttributes>()),
                RootDirectory = IntPtr.Zero,
                ObjectName = unicodeStringPointer,
                Attributes = ObjectAttributesCaseInsensitive,
                SecurityDescriptor = IntPtr.Zero,
                SecurityQualityOfService = IntPtr.Zero,
            };

            int openStatus = NtOpenDirectoryObject(out SafeObjectDirectoryHandle directoryHandle, ReadControl, ref attributes);
            using (directoryHandle)
            {
                if (openStatus < 0 || directoryHandle.IsInvalid)
                {
                    int win32Error = unchecked((int)RtlNtStatusToDosError(openStatus));
                    throw new NativeApiException($"NtOpenDirectoryObject.BaseNamedObjects:0x{unchecked((uint)openStatus):X8}", win32Error);
                }

                int sizeStatus = NtQuerySecurityObject(directoryHandle, SecurityInformationOwnerGroupDacl, null, 0, out uint requiredBytes);
                uint unsignedSizeStatus = unchecked((uint)sizeStatus);
                if (unsignedSizeStatus is not (StatusBufferTooSmall or StatusBufferOverflow)
                    || requiredBytes is 0 or > MaximumSecurityDescriptorBytes)
                {
                    int win32Error = unchecked((int)RtlNtStatusToDosError(sizeStatus));
                    throw new NativeApiException($"NtQuerySecurityObject.BaseNamedObjects.Size:0x{unsignedSizeStatus:X8}", win32Error);
                }

                byte[] descriptorBytes = new byte[checked((int)requiredBytes)];
                int queryStatus = NtQuerySecurityObject(directoryHandle, SecurityInformationOwnerGroupDacl,
                    descriptorBytes, checked((uint)descriptorBytes.Length), out uint returnedBytes);
                if (queryStatus < 0 || returnedBytes == 0 || returnedBytes > descriptorBytes.Length)
                {
                    int win32Error = unchecked((int)RtlNtStatusToDosError(queryStatus));
                    throw new NativeApiException($"NtQuerySecurityObject.BaseNamedObjects.Data:0x{unchecked((uint)queryStatus):X8}", win32Error);
                }
                if (returnedBytes != descriptorBytes.Length)
                {
                    Array.Resize(ref descriptorBytes, checked((int)returnedBytes));
                }

                return CheckBinaryDescriptor(descriptorBytes, targetToken, DirectoryCreateObject, BaseNamedObjectsDirectoryMapping);
            }
        }
        finally
        {
            if (unicodeStringPointer != IntPtr.Zero) Marshal.FreeHGlobal(unicodeStringPointer);
            if (pathBuffer != IntPtr.Zero) Marshal.FreeHGlobal(pathBuffer);
        }
    }

    private static DesktopObjectAccessResult CheckSddl(
        string sddl,
        SafeAccessTokenHandle primaryToken,
        uint desiredAccess,
        NativeMethods.GenericMapping mapping)
    {
        RawSecurityDescriptor descriptor;
        try
        {
            descriptor = new RawSecurityDescriptor(sddl);
        }
        catch (ArgumentException)
        {
            throw new NativeApiException("DesktopAclEvidence.InvalidSecurityDescriptor", 13);
        }
        if (descriptor.Owner is null || descriptor.Group is null || descriptor.DiscretionaryAcl is null
            || (descriptor.ControlFlags & ControlFlags.DiscretionaryAclPresent) == 0)
        {
            throw new NativeApiException("DesktopAclEvidence.OwnerGroupOrDaclMissing", 13);
        }
        byte[] descriptorBytes = new byte[descriptor.BinaryLength];
        descriptor.GetBinaryForm(descriptorBytes, 0);
        return CheckBinaryDescriptor(descriptorBytes, primaryToken, desiredAccess, mapping);
    }

    private static DesktopObjectAccessResult CheckBinaryDescriptor(
        byte[] descriptorBytes,
        SafeAccessTokenHandle primaryToken,
        uint desiredAccess,
        NativeMethods.GenericMapping mapping)
    {
        RawSecurityDescriptor descriptor;
        try
        {
            descriptor = new RawSecurityDescriptor(descriptorBytes, 0);
        }
        catch (ArgumentException)
        {
            throw new NativeApiException("AccessCheck.InvalidSecurityDescriptor", 13);
        }
        if (descriptor.Owner is null || descriptor.Group is null || descriptor.DiscretionaryAcl is null
            || (descriptor.ControlFlags & ControlFlags.DiscretionaryAclPresent) == 0)
        {
            throw new NativeApiException("AccessCheck.OwnerGroupOrDaclMissing", 13);
        }
        IntPtr descriptorPointer = Marshal.AllocHGlobal(descriptorBytes.Length);
        try
        {
            Marshal.Copy(descriptorBytes, 0, descriptorPointer, descriptorBytes.Length);
            if (!NativeMethods.DuplicateTokenEx(primaryToken, NativeMethods.TokenQuery, IntPtr.Zero,
                    NativeMethods.SecurityImpersonation, NativeMethods.TokenImpersonation,
                    out SafeAccessTokenHandle impersonationToken))
            {
                throw new NativeApiException("DuplicateTokenEx.DesktopAccessCheck", Marshal.GetLastWin32Error());
            }
            using (impersonationToken)
            {
                int privilegeBytes = 1024;
                IntPtr privilegeBuffer = Marshal.AllocHGlobal(privilegeBytes);
                try
                {
                    while (true)
                    {
                        uint privilegeLength = checked((uint)privilegeBytes);
                        if (NativeMethods.AccessCheck(descriptorPointer, impersonationToken, desiredAccess, ref mapping,
                                privilegeBuffer, ref privilegeLength, out uint grantedAccess, out bool accessStatus))
                        {
                            return new DesktopObjectAccessResult(true, accessStatus, desiredAccess, grantedAccess, null);
                        }

                        int error = Marshal.GetLastWin32Error();
                        if (error != ErrorInsufficientBuffer || privilegeLength <= privilegeBytes || privilegeLength > MaximumPrivilegeSetBytes)
                        {
                            throw new NativeApiException("AccessCheck.SecurityDescriptor", error);
                        }
                        int replacementBytes = checked((int)privilegeLength);
                        IntPtr replacementBuffer = Marshal.AllocHGlobal(replacementBytes);
                        Marshal.FreeHGlobal(privilegeBuffer);
                        privilegeBytes = replacementBytes;
                        privilegeBuffer = replacementBuffer;
                    }
                }
                finally
                {
                    Marshal.FreeHGlobal(privilegeBuffer);
                }
            }
        }
        finally
        {
            Marshal.FreeHGlobal(descriptorPointer);
        }
    }

    private static Dictionary<string, object?> Format(DesktopObjectAccessResult result) => new()
    {
        ["api_succeeded"] = result.ApiSucceeded,
        ["access_granted"] = result.AccessGranted,
        ["desired_access"] = $"0x{result.DesiredAccess:X8}",
        ["granted_access"] = $"0x{result.GrantedAccess:X8}",
        ["win32_error"] = result.Win32Error,
    };

    private static Dictionary<string, object?> FormatBaseNamedObjects(DesktopObjectAccessResult result) => new()
    {
        ["status"] = !result.ApiSucceeded ? "api_error" : result.AccessGranted ? "pass" : "denied",
        ["object"] = "session_base_named_objects_directory",
        ["directory_create_object_access"] = Format(result),
        ["acl_mutated"] = false,
        ["target_process_started"] = false,
    };

    private static string ReadRequiredString(JsonElement root, string name)
    {
        if (!root.TryGetProperty(name, out JsonElement value) || value.ValueKind != JsonValueKind.String
            || string.IsNullOrWhiteSpace(value.GetString()))
        {
            throw new NativeApiException($"DesktopAclEvidence.{name}.Missing", 13);
        }
        return value.GetString()!;
    }

    private static int ReadRequiredInt32(JsonElement root, string name)
    {
        if (!root.TryGetProperty(name, out JsonElement value) || !value.TryGetInt32(out int parsed))
        {
            throw new NativeApiException($"DesktopAclEvidence.{name}.Missing", 13);
        }
        return parsed;
    }
}
