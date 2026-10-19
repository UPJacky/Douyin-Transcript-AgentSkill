using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Text;

namespace WfpPolicy.NativeReadback;

internal static class SecurityDescriptorNormalizer
{
    internal const int MaxDescriptorBytes = 1024 * 1024;

    internal static bool TryNormalize(
        ReadOnlySpan<byte> descriptorBytes,
        out SecurityDescriptorSnapshot? snapshot,
        out string error)
    {
        snapshot = null;
        if (descriptorBytes.Length is < 20 or > MaxDescriptorBytes)
        {
            error = $"Security descriptor length is outside the supported 20..{MaxDescriptorBytes} byte range.";
            return false;
        }

        try
        {
            var raw = new RawSecurityDescriptor(descriptorBytes.ToArray(), 0);
            if ((raw.ControlFlags & ControlFlags.SelfRelative) == 0)
            {
                error = "Security descriptor is not self-relative.";
                return false;
            }

            var common = new CommonSecurityDescriptor(isContainer: false, isDS: false, raw);
            if (!common.IsDiscretionaryAclCanonical)
            {
                error = "Security descriptor contains a noncanonical DACL.";
                return false;
            }

            var sddl = common.GetSddlForm(AccessControlSections.Owner | AccessControlSections.Group | AccessControlSections.Access);
            if (string.IsNullOrWhiteSpace(sddl))
            {
                error = "Security descriptor normalized to an empty SDDL value.";
                return false;
            }

            var sha256 = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(sddl))).ToLowerInvariant();
            bool daclPresent = (raw.ControlFlags & ControlFlags.DiscretionaryAclPresent) != 0;
            snapshot = new SecurityDescriptorSnapshot(
                sddl,
                sha256,
                descriptorBytes.Length,
                daclPresent,
                daclPresent && raw.DiscretionaryAcl is null);
            error = "";
            return true;
        }
        catch (Exception exception) when (exception is ArgumentException or InvalidOperationException or NotSupportedException or OverflowException or System.Security.SecurityException)
        {
            error = $"Security descriptor could not be parsed: {exception.GetType().Name}.";
            return false;
        }
    }
}
