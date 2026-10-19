using System.Globalization;
using System.Net;
using System.Net.Sockets;

namespace DouyinTranscript.NetworkPolicy;

/// <summary>
/// Shared conservative address policy for lease DNS validation and WFP planning.
/// </summary>
internal static class PublicUnicastAddressPolicy
{
    private static readonly Prefix[] NonPublicIPv4Prefixes =
    [
        Prefix.Parse("0.0.0.0/8"),
        Prefix.Parse("10.0.0.0/8"),
        Prefix.Parse("100.64.0.0/10"),
        Prefix.Parse("127.0.0.0/8"),
        Prefix.Parse("169.254.0.0/16"),
        Prefix.Parse("172.16.0.0/12"),
        Prefix.Parse("192.0.0.0/24"),
        Prefix.Parse("192.0.2.0/24"),
        Prefix.Parse("192.88.99.0/24"),
        Prefix.Parse("192.168.0.0/16"),
        Prefix.Parse("198.18.0.0/15"),
        Prefix.Parse("198.51.100.0/24"),
        Prefix.Parse("203.0.113.0/24"),
        Prefix.Parse("224.0.0.0/4"),
        Prefix.Parse("240.0.0.0/4"),
    ];

    private static readonly Prefix[] NonPublicIPv6Prefixes =
    [
        Prefix.Parse("2001::/23"),
        Prefix.Parse("2001:db8::/32"),
        Prefix.Parse("2002::/16"),
        Prefix.Parse("3fff::/20"),
    ];

    public static bool IsPublicUnicast(IPAddress address)
    {
        ArgumentNullException.ThrowIfNull(address);
        byte[] bytes = address.GetAddressBytes();
        if (address.AddressFamily == AddressFamily.InterNetwork)
        {
            return !NonPublicIPv4Prefixes.Any(prefix => prefix.Contains(bytes));
        }
        if (address.AddressFamily != AddressFamily.InterNetworkV6 || address.IsIPv4MappedToIPv6 || address.ScopeId != 0)
        {
            return false;
        }
        if ((bytes[0] & 0xE0) != 0x20)
        {
            return false;
        }
        return !NonPublicIPv6Prefixes.Any(prefix => prefix.Contains(bytes));
    }

    private sealed record Prefix(byte[] Network, int Length)
    {
        public static Prefix Parse(string value)
        {
            string[] parts = value.Split('/');
            if (parts.Length != 2 || !IPAddress.TryParse(parts[0], out IPAddress? network)
                || !int.TryParse(parts[1], NumberStyles.None, CultureInfo.InvariantCulture, out int length))
            {
                throw new InvalidOperationException("Invalid built-in address prefix.");
            }
            return new Prefix(network.GetAddressBytes(), length);
        }

        public bool Contains(byte[] address)
        {
            if (address.Length != Network.Length)
            {
                return false;
            }
            int fullBytes = Length / 8;
            int remainingBits = Length % 8;
            for (int index = 0; index < fullBytes; index++)
            {
                if (address[index] != Network[index])
                {
                    return false;
                }
            }
            if (remainingBits == 0)
            {
                return true;
            }
            int mask = 0xFF << (8 - remainingBits);
            return (address[fullBytes] & mask) == (Network[fullBytes] & mask);
        }
    }
}
