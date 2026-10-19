using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Principal;

namespace DouyinTranscript.LeaseJobHelper;

internal sealed record WorkAreaResult(
    string WorkDirectory,
    string ProfileDirectory,
    Dictionary<string, object?> WorkDirectoryAcl,
    Dictionary<string, object?> ProfileDirectoryAcl,
    Dictionary<string, object?> EvidenceDirectoryAccess);

internal static class WorkArea
{
    internal static WorkAreaResult Create(string workDirectory, string profileDirectory, string evidenceDirectory, string targetSid)
    {
        workDirectory = Path.GetFullPath(workDirectory).TrimEnd(Path.DirectorySeparatorChar);
        profileDirectory = Path.GetFullPath(profileDirectory).TrimEnd(Path.DirectorySeparatorChar);
        evidenceDirectory = Path.GetFullPath(evidenceDirectory).TrimEnd(Path.DirectorySeparatorChar);
        string? parent = Path.GetDirectoryName(workDirectory);
        if (string.IsNullOrWhiteSpace(parent) || !Directory.Exists(parent))
        {
            throw new NativeApiException("WorkDirectory.ParentMustExist", NativeMethods.ErrorNotFound);
        }
        if (Directory.Exists(workDirectory) || File.Exists(workDirectory))
        {
            throw new NativeApiException("WorkDirectory.MustBeNew", NativeMethods.ErrorAlreadyExists);
        }
        if (!IsDirectChild(profileDirectory, workDirectory))
        {
            throw new NativeApiException("ProfileDirectory.MustBeInsideNewWorkDirectory", NativeMethods.ErrorAccessDenied);
        }
        if (Directory.Exists(profileDirectory) || File.Exists(profileDirectory))
        {
            throw new NativeApiException("ProfileDirectory.MustBeNew", NativeMethods.ErrorAlreadyExists);
        }
        if (!Directory.Exists(evidenceDirectory))
        {
            throw new NativeApiException("EvidenceDirectory.MustExist", NativeMethods.ErrorNotFound);
        }

        Directory.CreateDirectory(workDirectory);
        EnsurePlainDirectory(workDirectory, "WorkDirectory.ReparsePoint");
        Dictionary<string, object?> workAcl = GrantModifyToExactSid(workDirectory, targetSid);

        Directory.CreateDirectory(profileDirectory);
        EnsurePlainDirectory(profileDirectory, "ProfileDirectory.ReparsePoint");
        Dictionary<string, object?> profileAcl = ReadAclObservation(profileDirectory, targetSid);
        string profileSddl = (string)profileAcl["dacl_sddl"]!;
        bool profileNoBroadWrites = !profileSddl.Contains(";;;WD)", StringComparison.Ordinal)
            && !profileSddl.Contains(";;;AU)", StringComparison.Ordinal)
            && !profileSddl.Contains(";;;BU)", StringComparison.Ordinal);
        if (profileAcl["contains_target_sid"] is not true || !profileNoBroadWrites
            || !profileSddl.Contains(";;;SY)", StringComparison.Ordinal)
            || !profileSddl.Contains(";;;BA)", StringComparison.Ordinal))
        {
            throw new NativeApiException("VerifyProfileDirectoryInheritedDacl", NativeMethods.ErrorAccessDenied);
        }
        profileAcl["acl_mutated"] = false;
        profileAcl["inherited_from_work_directory"] = true;
        profileAcl["broad_users_write_aces_absent"] = profileNoBroadWrites;

        EnsurePlainDirectory(evidenceDirectory, "EvidenceDirectory.ReparsePoint");
        var evidence = new Dictionary<string, object?>
        {
            ["path"] = evidenceDirectory,
            ["mapping_write_access_required"] = true,
            ["written_by"] = "SYSTEM helper after target jobs drain",
            ["target_sid_acl_mutated"] = false,
        };
        return new WorkAreaResult(workDirectory, profileDirectory, workAcl, profileAcl, evidence);
    }

    private static Dictionary<string, object?> GrantModifyToExactSid(string path, string sidString)
    {
        IntPtr targetSidPointer = GetSidPointer(sidString);
        IntPtr systemSidPointer = GetSidPointer("S-1-5-18");
        IntPtr administratorsSidPointer = GetSidPointer("S-1-5-32-544");
        IntPtr accessArray = IntPtr.Zero;
        IntPtr securityDescriptor = IntPtr.Zero;
        IntPtr newAcl = IntPtr.Zero;
        try
        {
            int result = NativeMethods.GetNamedSecurityInfo(path, NativeMethods.SeFileObject,
                NativeMethods.SecurityInformationDacl, out _, out _, out IntPtr oldAcl, out _, out securityDescriptor);
            if (result != NativeMethods.ErrorSuccess)
            {
                throw new NativeApiException("GetNamedSecurityInfo.WorkDirectory.Before", result);
            }
            string before = ReadDaclSddl(securityDescriptor);
            NativeMethods.ExplicitAccess[] entries =
            [
                CreateAccess(NativeMethods.FileAllAccess, systemSidPointer),
                CreateAccess(NativeMethods.FileAllAccess, administratorsSidPointer),
                CreateAccess(NativeMethods.FileModifyRights, targetSidPointer),
            ];
            int entrySize = Marshal.SizeOf<NativeMethods.ExplicitAccess>();
            accessArray = Marshal.AllocHGlobal(checked(entrySize * entries.Length));
            for (int index = 0; index < entries.Length; index++)
            {
                Marshal.StructureToPtr(entries[index], IntPtr.Add(accessArray, index * entrySize), false);
            }
            result = NativeMethods.SetEntriesInAcl((uint)entries.Length, accessArray, IntPtr.Zero, out newAcl);
            if (result != NativeMethods.ErrorSuccess)
            {
                throw new NativeApiException("SetEntriesInAcl.WorkDirectory", result);
            }
            result = NativeMethods.SetNamedSecurityInfo(path, NativeMethods.SeFileObject,
                (uint)NativeMethods.SecurityInformationDacl | NativeMethods.ProtectedDaclSecurityInformation,
                IntPtr.Zero, IntPtr.Zero, newAcl, IntPtr.Zero);
            if (result != NativeMethods.ErrorSuccess)
            {
                throw new NativeApiException("SetNamedSecurityInfo.WorkDirectory", result);
            }
            string after = ReadAclObservation(path, sidString)["dacl_sddl"] as string ?? string.Empty;
            bool broadWriteAcesAbsent = !after.Contains(";;;WD)", StringComparison.Ordinal)
                && !after.Contains(";;;AU)", StringComparison.Ordinal)
                && !after.Contains(";;;BU)", StringComparison.Ordinal);
            if (!after.Contains(";;;SY)", StringComparison.Ordinal)
                || !after.Contains(";;;BA)", StringComparison.Ordinal)
                || !after.Contains(sidString, StringComparison.Ordinal)
                || !broadWriteAcesAbsent
                || !after.Contains("D:P", StringComparison.Ordinal))
            {
                throw new NativeApiException("VerifyWorkDirectoryProtectedDacl", NativeMethods.ErrorAccessDenied);
            }
            return new Dictionary<string, object?>
            {
                ["path"] = path,
                ["path_was_absent_before_creation"] = true,
                ["target_sid"] = sidString,
                ["granted_rights"] = "Modify",
                ["inheritance"] = "object and container",
                ["protected_dacl"] = true,
                ["parent_acl_inherited"] = false,
                ["broad_users_write_aces_absent"] = broadWriteAcesAbsent,
                ["before_dacl_sddl"] = before,
                ["after_dacl_sddl"] = after,
                ["acl_mutated"] = true,
                ["win32_error"] = NativeMethods.ErrorSuccess,
            };
        }
        finally
        {
            if (accessArray != IntPtr.Zero)
            {
                int entrySize = Marshal.SizeOf<NativeMethods.ExplicitAccess>();
                for (int index = 0; index < 3; index++)
                {
                    Marshal.DestroyStructure<NativeMethods.ExplicitAccess>(IntPtr.Add(accessArray, index * entrySize));
                }
                Marshal.FreeHGlobal(accessArray);
            }
            Marshal.FreeHGlobal(targetSidPointer);
            Marshal.FreeHGlobal(systemSidPointer);
            Marshal.FreeHGlobal(administratorsSidPointer);
            if (securityDescriptor != IntPtr.Zero)
            {
                _ = NativeMethods.LocalFree(securityDescriptor);
            }
            if (newAcl != IntPtr.Zero)
            {
                _ = NativeMethods.LocalFree(newAcl);
            }
        }
    }

    private static NativeMethods.ExplicitAccess CreateAccess(uint rights, IntPtr sid) => new()
    {
        AccessPermissions = rights,
        AccessMode = NativeMethods.GrantAccess,
        Inheritance = NativeMethods.ObjectInheritAce | NativeMethods.ContainerInheritAce,
        Trustee = new NativeMethods.Trustee
        {
            MultipleTrustee = IntPtr.Zero,
            MultipleTrusteeOperation = 0,
            TrusteeForm = NativeMethods.TrusteeIsSid,
            TrusteeType = NativeMethods.TrusteeIsUser,
            Name = sid,
        },
    };

    private static IntPtr GetSidPointer(string sidString)
    {
        SecurityIdentifier sid = new(sidString);
        byte[] bytes = new byte[sid.BinaryLength];
        sid.GetBinaryForm(bytes, 0);
        IntPtr pointer = Marshal.AllocHGlobal(bytes.Length);
        Marshal.Copy(bytes, 0, pointer, bytes.Length);
        return pointer;
    }

    private static Dictionary<string, object?> ReadAclObservation(string path, string sidString)
    {
        int result = NativeMethods.GetNamedSecurityInfo(path, NativeMethods.SeFileObject,
            NativeMethods.SecurityInformationDacl, out _, out _, out _, out _, out IntPtr descriptor);
        if (result != NativeMethods.ErrorSuccess)
        {
            throw new NativeApiException("GetNamedSecurityInfo.Read", result);
        }
        try
        {
            string sddl = ReadDaclSddl(descriptor);
            return new Dictionary<string, object?>
            {
                ["path"] = path,
                ["target_sid"] = sidString,
                ["dacl_sddl"] = sddl,
                ["contains_target_sid"] = sddl.Contains(sidString, StringComparison.Ordinal),
            };
        }
        finally
        {
            _ = NativeMethods.LocalFree(descriptor);
        }
    }

    private static string ReadDaclSddl(IntPtr descriptor)
    {
        if (!NativeMethods.ConvertSecurityDescriptorToStringSecurityDescriptor(descriptor,
                NativeMethods.SecurityDescriptorRevision, NativeMethods.SecurityInformationDacl,
                out IntPtr text, out _))
        {
            throw LastError("ConvertSecurityDescriptorToStringSecurityDescriptor");
        }
        try
        {
            return Marshal.PtrToStringUni(text) ?? throw new NativeApiException("ReadDaclSddl", 13);
        }
        finally
        {
            _ = NativeMethods.LocalFree(text);
        }
    }

    private static bool IsDirectChild(string child, string parent)
    {
        string? childParent = Path.GetDirectoryName(child.TrimEnd(Path.DirectorySeparatorChar));
        return childParent is not null && string.Equals(Path.GetFullPath(childParent).TrimEnd(Path.DirectorySeparatorChar),
            parent, StringComparison.OrdinalIgnoreCase);
    }

    private static void EnsurePlainDirectory(string path, string api)
    {
        FileAttributes attributes = File.GetAttributes(path);
        if ((attributes & FileAttributes.Directory) == 0 || (attributes & FileAttributes.ReparsePoint) != 0)
        {
            throw new NativeApiException(api, NativeMethods.ErrorAccessDenied);
        }
    }

    private static NativeApiException LastError(string api) => new(api, Marshal.GetLastWin32Error());
}
