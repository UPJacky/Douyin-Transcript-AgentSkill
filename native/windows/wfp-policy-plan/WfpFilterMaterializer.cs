using System.Buffers.Binary;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Security.Cryptography;
using DouyinTranscript.NetworkPolicy;
using Windows.Win32.NetworkManagement.WindowsFilteringPlatform;

[assembly: System.Runtime.CompilerServices.InternalsVisibleTo("LeasePolicyCompiler.Tests")]

namespace WfpPolicyPlan;

/// <summary>
/// A copied, pointer-free view of a native filter built for static review.
/// Values that could disclose an application path or raw security descriptor
/// are represented by digests or parsed identity data.
/// </summary>
public sealed record NativeConditionSnapshot(
    string Field,
    string Match,
    string DataType,
    string Value,
    uint? RawUInt32Value = null);

public sealed record NativeFilterSnapshot(
    string RuleId,
    Guid FilterKey,
    Guid ProviderKey,
    Guid SublayerKey,
    Guid LayerKey,
    string Action,
    bool ClearActionRight,
    bool Persistent,
    byte WeightRangeIndex,
    IReadOnlyList<NativeConditionSnapshot> Conditions);

public sealed record NativeFilterPreview(
    string Deployability,
    bool PolicyMutated,
    string Boundary,
    IReadOnlyList<NativeFilterSnapshot> Filters);

/// <summary>
/// Builds CsWin32 FWPM_FILTER0 and condition structures in a bounded unmanaged
/// arena, copies their fields into a review DTO, and frees the arena. It never
/// opens BFE, calls a WFP API, writes an artifact, or exposes native pointers.
/// It is not an apply path and does not attest identity provenance.
/// </summary>
[SupportedOSPlatform("windows")]
internal static unsafe class WfpFilterMaterializer
{
    private const int MaxRules = 10_000;
    private const int MaxAppIdBytes = 32_768;
    private const int MaxDisplayNameChars = 256;
    private const int MaxDescriptionChars = 2_048;
    private const uint FwpmActrlMatchFilter = 0x00000001;

    /// <summary>
    /// Materialize only a bounded, permanently non-deployable plan that passes
    /// the compiler's complete rule-shape checks. Provider and sublayer IDs
    /// must be explicit.
    /// </summary>
    internal static NativeFilterPreview MaterializeForInspection(
        LeasePolicyDocument document,
        Guid providerKey,
        Guid sublayerKey)
    {
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("The CsWin32 WFP materializer requires Windows.");
        ArgumentNullException.ThrowIfNull(document);
        ValidateDocument(document, providerKey, sublayerKey);

        var snapshots = new List<NativeFilterSnapshot>(document.Rules.Count);
        using var arena = new UnmanagedArena();
        foreach (LeasePolicyRule rule in document.Rules)
        {
            FWPM_FILTER0 filter = BuildFilter(arena, rule, providerKey, sublayerKey);
            snapshots.Add(Inspect(filter, rule.RuleId, providerKey, sublayerKey));
        }

        return new NativeFilterPreview(
            Deployability: "not-deployable",
            PolicyMutated: false,
            Boundary: "Native structures were constructed and inspected in memory, then freed. No BFE/WFP API was called; this is not evidence of active isolation.",
            Filters: Array.AsReadOnly(snapshots.ToArray()));
    }

    internal static NativeFilterPreview MaterializeAppIdBaselineForInspection(
        PersistentAppIdBaselinePlan plan,
        Guid providerKey,
        Guid sublayerKey)
    {
        ArgumentNullException.ThrowIfNull(plan);
        if (plan.SchemaVersion != LeasePolicyCompiler.SchemaVersion
            || plan.PlanKind != "persistent-app-id-baseline"
            || plan.Deployability != "not-deployable"
            || plan.Rules is null
            || plan.Rules.Count is 0 or > MaxRules
            || plan.UnresolvedValidationItems is null
            || plan.Rules.Any(rule => rule is null
                || rule.Lifetime != LeasePolicyLifetime.PersistentDefaultDeny
                || rule.Action != LeasePolicyAction.Block
                || rule.LeaseId is not null
                || rule.AppIdHex is null
                || rule.LeaseSid is not null
                || rule.IdentityCondition != "ALE_APP_ID"))
        {
            throw new ArgumentException("Only a bounded AppID-only persistent baseline can be inspected.", nameof(plan));
        }

        return MaterializeForInspection(ToInspectionDocument(
            plan.SchemaVersion, plan.Rules, plan.UnresolvedValidationItems, plan.SafetyBoundary),
            providerKey,
            sublayerKey);
    }

    internal static NativeFilterPreview MaterializeDynamicLeaseForInspection(
        DynamicLeasePlan plan,
        Guid providerKey,
        Guid sublayerKey)
    {
        ArgumentNullException.ThrowIfNull(plan);
        if (plan.SchemaVersion != LeasePolicyCompiler.SchemaVersion
            || plan.PlanKind != "dynamic-lease"
            || plan.Deployability != "not-deployable"
            || string.IsNullOrWhiteSpace(plan.LeaseId)
            || string.IsNullOrWhiteSpace(plan.LeaseSid)
            || !Enum.IsDefined(plan.PrincipalKind)
            || plan.Rules is null
            || plan.Rules.Count is 0 or > MaxRules
            || plan.UnresolvedValidationItems is null
            || plan.Rules.Any(rule => rule is null
                || rule.Lifetime != LeasePolicyLifetime.LeaseDynamic
                || rule.LeaseId != plan.LeaseId
                || (rule.LeaseSid is not null && rule.LeaseSid != plan.LeaseSid)))
        {
            throw new ArgumentException("Only a bounded single-lease dynamic plan can be inspected.", nameof(plan));
        }

        return MaterializeForInspection(ToInspectionDocument(
            plan.SchemaVersion, plan.Rules, plan.UnresolvedValidationItems, plan.SafetyBoundary),
            providerKey,
            sublayerKey);
    }

    private static LeasePolicyDocument ToInspectionDocument(
        string schemaVersion,
        IReadOnlyList<LeasePolicyRule> rules,
        IReadOnlyList<string> unresolvedValidationItems,
        string safetyBoundary) =>
        new(
            schemaVersion,
            PlanKind: "per-lease-semantic-preview",
            Deployability: "not-deployable",
            Sublayer: "service-owned sublayer required; placeholder only",
            Rules: rules,
            UnresolvedValidationItems: unresolvedValidationItems,
            SafetyBoundary: safetyBoundary);

    /// <summary>
    /// Visit the exact native structures synchronously while their unmanaged
    /// backing arena is alive. Only the friend test harness can use this hook;
    /// it is not exposed through the product executable or a policy command.
    /// </summary>
    internal static IReadOnlyList<NativeFilterSnapshot> VisitForSandboxBfeValidation(
        LeasePolicyDocument document,
        Guid providerKey,
        Guid sublayerKey,
        Action<FWPM_FILTER0> visitor)
    {
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("The CsWin32 WFP materializer requires Windows.");
        ArgumentNullException.ThrowIfNull(document);
        ArgumentNullException.ThrowIfNull(visitor);
        ValidateDocument(document, providerKey, sublayerKey);

        var snapshots = new List<NativeFilterSnapshot>(document.Rules.Count);
        using var arena = new UnmanagedArena();
        foreach (LeasePolicyRule rule in document.Rules)
        {
            FWPM_FILTER0 filter = BuildFilter(arena, rule, providerKey, sublayerKey);
            NativeFilterSnapshot snapshot = Inspect(filter, rule.RuleId, providerKey, sublayerKey);
            visitor(filter);
            snapshots.Add(snapshot);
        }
        return Array.AsReadOnly(snapshots.ToArray());
    }

    internal static NativeFilterSnapshot InspectForSandboxBfeValidation(
        FWPM_FILTER0* filter,
        string ruleId,
        Guid providerKey,
        Guid sublayerKey)
    {
        if (filter is null)
            throw new ArgumentNullException(nameof(filter));
        return Inspect(*filter, ruleId, providerKey, sublayerKey);
    }

    private static void ValidateDocument(LeasePolicyDocument document, Guid providerKey, Guid sublayerKey)
    {
        if (document.SchemaVersion != LeasePolicyCompiler.SchemaVersion
            || document.PlanKind != "per-lease-semantic-preview"
            || document.Deployability != "not-deployable"
            || document.UnresolvedValidationItems is null
            || document.UnresolvedValidationItems.Count == 0
            || document.Rules is null
            || document.Rules.Count is 0 or > MaxRules)
        {
            throw new ArgumentException("Only a bounded non-deployable lease plan can be materialized.", nameof(document));
        }
        if (providerKey == Guid.Empty || sublayerKey == Guid.Empty)
        {
            throw new ArgumentException("Explicit non-empty provider and sublayer GUIDs are required.");
        }

        var ids = new HashSet<string>(StringComparer.Ordinal);
        foreach (LeasePolicyRule rule in document.Rules)
        {
            if (rule is null || string.IsNullOrWhiteSpace(rule.RuleId)
                || rule.RuleId.Length > MaxDisplayNameChars
                || string.IsNullOrWhiteSpace(rule.Purpose)
                || rule.Purpose.Length > MaxDescriptionChars
                || !ids.Add(rule.RuleId)
                || rule.WeightRangeIndex > 15
                || !Enum.IsDefined(rule.AddressFamily)
                || !Enum.IsDefined(rule.Action)
                || !Enum.IsDefined(rule.Lifetime)
                || rule.ClearActionRight)
            {
                throw new ArgumentException("A rule has an unsupported identifier, annotation, enum, weight, or action-right setting.", nameof(document));
            }

            if (rule.Lifetime == LeasePolicyLifetime.PersistentDefaultDeny
                && (rule.Action != LeasePolicyAction.Block || rule.WeightRangeIndex != LeasePolicyCompiler.DefaultDenyWeightRangeIndex))
            {
                throw new ArgumentException("Persistent rules must remain low-weight default-deny blocks.", nameof(document));
            }
            if (rule.Lifetime == LeasePolicyLifetime.LeaseDynamic
                && (rule.Action == LeasePolicyAction.Block
                    ? rule.WeightRangeIndex != LeasePolicyCompiler.DefaultDenyWeightRangeIndex
                    : rule.WeightRangeIndex != LeasePolicyCompiler.LeasePermitWeightRangeIndex))
            {
                throw new ArgumentException("Dynamic rules must retain the compiler's block/permit range-index ordering.", nameof(document));
            }

            ValidateIdentity(rule);
            if (rule.Protocol is < 0 or > byte.MaxValue || rule.RemotePort is < 1 or > ushort.MaxValue)
            {
                throw new ArgumentException("Protocol or remote port is outside its native WFP value range.", nameof(document));
            }
            if (rule.RemoteAddress is not null)
            {
                if (rule.RemoteAddress != rule.RemoteAddress.Trim() || rule.RemoteAddress.Contains('%')
                    || !IPAddress.TryParse(rule.RemoteAddress, out IPAddress? address)
                    || address.AddressFamily != (rule.AddressFamily == LeasePolicyAddressFamily.IPv4
                        ? AddressFamily.InterNetwork : AddressFamily.InterNetworkV6)
                    || !StringComparer.Ordinal.Equals(address.ToString(), rule.RemoteAddress)
                    || (address.AddressFamily == AddressFamily.InterNetworkV6 && address.ScopeId != 0))
                {
                    throw new ArgumentException("RemoteAddress must be a plain numeric literal matching its rule family.", nameof(document));
                }
            }
            ValidateRuleShape(rule);
        }

        ValidateLeaseRuleGroups(document.Rules);
    }

    private static void ValidateRuleShape(LeasePolicyRule rule)
    {
        bool hasEndpoint = rule.RemoteAddress is not null && rule.Protocol is not null && rule.RemotePort is not null;
        bool noEndpoint = rule.RemoteAddress is null && rule.Protocol is null && rule.RemotePort is null;
        bool principalIdentity = rule.IdentityCondition is "ALE_USER_ID" or "ALE_PACKAGE_ID";

        bool valid = rule.Lifetime switch
        {
            LeasePolicyLifetime.PersistentDefaultDeny => rule.Action == LeasePolicyAction.Block && noEndpoint
                && ((rule.IdentityCondition == "ALE_APP_ID" && rule.AppIdHex is not null && rule.LeaseSid is null)
                    || (principalIdentity && rule.AppIdHex is null && rule.LeaseSid is not null)),
            LeasePolicyLifetime.LeaseDynamic when rule.Action == LeasePolicyAction.Block =>
                (rule.IdentityCondition == "none; endpoint-wide listener block"
                    && rule.LeaseId is { Length: 32 }
                    && Guid.TryParseExact(rule.LeaseId, "N", out _)
                    && rule.RuleId == $"lease-{rule.LeaseId}-deny-other-listener-clients"
                    && rule.Purpose == "Block every local process except the matching lease browser from connecting to this worker listener."
                    && rule.AddressFamily == LeasePolicyAddressFamily.IPv4
                    && rule.RemoteAddress == "127.0.0.1" && rule.Protocol == 6 && rule.RemotePort is not null)
                || (principalIdentity && rule.AppIdHex is null && rule.LeaseSid is not null && noEndpoint
                    && rule.LeaseId is { Length: 32 }
                    && Guid.TryParseExact(rule.LeaseId, "N", out _)
                    && Enum.GetValues<LeasePolicyAddressFamily>().Any(family =>
                        rule.RuleId == $"default-deny-principal-{rule.LeaseId}-{FamilyToken(family)}")),
            LeasePolicyLifetime.LeaseDynamic when rule.Action == LeasePolicyAction.Permit =>
                IsRecognizedLeasePermit(rule, principalIdentity, hasEndpoint),
            _ => false,
        };
        if (!valid)
            throw new ArgumentException("Rule shape does not match one of the compiler's narrow default-deny, listener-block, or exact-permit forms.");
    }

    private static bool IsRecognizedLeasePermit(LeasePolicyRule rule, bool principalIdentity, bool hasEndpoint)
    {
        if (!principalIdentity || rule.AppIdHex is null || rule.LeaseSid is null || !hasEndpoint
            || rule.LeaseId is not { Length: 32 } || !Guid.TryParseExact(rule.LeaseId, "N", out _))
        {
            return false;
        }

        string leasePrefix = $"lease-{rule.LeaseId}";
        if (rule.RuleId == $"{leasePrefix}-browser-allow-worker-listener")
        {
            return rule.Purpose == "Allow only this browser AppID and lease principal to connect to this lease's IPv4 loopback worker listener."
                && rule.AddressFamily == LeasePolicyAddressFamily.IPv4
                && rule.RemoteAddress == "127.0.0.1"
                && rule.Protocol == 6
                && rule.RemotePort is >= 1 and <= ushort.MaxValue;
        }

        if (rule.Purpose == "Allow this lease worker to contact only its configured numeric DNS resolver on TCP/UDP port 53.")
        {
            foreach (int protocol in new[] { 6, 17 })
            {
                string familyToken = FamilyToken(rule.AddressFamily);
                string protocolToken = protocol == 6 ? "tcp" : "udp";
                if (rule.RuleId == $"{leasePrefix}-worker-allow-dns-{familyToken}-{protocolToken}"
                    && rule.Protocol == protocol
                    && rule.RemotePort == LeasePolicyCompiler.DnsPort
                    && IsPublicNumericAddress(rule.RemoteAddress, rule.AddressFamily))
                {
                    return true;
                }
            }
            return false;
        }

        if (rule.Purpose == "Allow this lease worker to connect to one fully validated, numerically pinned public address on TCP port 443."
            && rule.Protocol == 6
            && rule.RemotePort == LeasePolicyCompiler.HttpsPort
            && IsPublicNumericAddress(rule.RemoteAddress, rule.AddressFamily))
        {
            IPAddress address = IPAddress.Parse(rule.RemoteAddress!);
            string addressFamily = rule.AddressFamily.ToString().ToLowerInvariant();
            string addressKey = Convert.ToHexString(address.GetAddressBytes());
            return rule.RuleId == $"{leasePrefix}-worker-allow-upstream-{addressFamily}-{addressKey}";
        }

        return false;
    }

    private static bool IsPublicNumericAddress(string? value, LeasePolicyAddressFamily family) =>
        value is not null
        && IPAddress.TryParse(value, out IPAddress? address)
        && address.AddressFamily == (family == LeasePolicyAddressFamily.IPv4
            ? AddressFamily.InterNetwork
            : AddressFamily.InterNetworkV6)
        && LeasePolicyCompiler.IsPublicUnicast(address);

    private static string FamilyToken(LeasePolicyAddressFamily family) =>
        family == LeasePolicyAddressFamily.IPv4 ? "v4" : "v6";

    private static void ValidateLeaseRuleGroups(IReadOnlyList<LeasePolicyRule> rules)
    {
        foreach (IGrouping<string, LeasePolicyRule> leaseRules in rules
            .Where(rule => rule.Lifetime == LeasePolicyLifetime.LeaseDynamic)
            .GroupBy(rule => rule.LeaseId!, StringComparer.Ordinal))
        {
            LeasePolicyRule[] group = leaseRules.ToArray();
            LeasePolicyRule[] principalBlocks = group.Where(rule => rule.RuleId.StartsWith(
                $"default-deny-principal-{leaseRules.Key}-", StringComparison.Ordinal)).ToArray();
            LeasePolicyRule[] listenerBlocks = group.Where(rule => rule.RuleId ==
                $"lease-{leaseRules.Key}-deny-other-listener-clients").ToArray();
            LeasePolicyRule[] browserPermits = group.Where(rule => rule.RuleId ==
                $"lease-{leaseRules.Key}-browser-allow-worker-listener").ToArray();
            LeasePolicyRule[] dnsPermits = group.Where(rule => rule.RuleId.StartsWith(
                $"lease-{leaseRules.Key}-worker-allow-dns-", StringComparison.Ordinal)).ToArray();
            LeasePolicyRule[] upstreamPermits = group.Where(rule => rule.RuleId.StartsWith(
                $"lease-{leaseRules.Key}-worker-allow-upstream-", StringComparison.Ordinal)).ToArray();

            if (principalBlocks.Length != 2 || listenerBlocks.Length != 1 || browserPermits.Length != 1
                || dnsPermits.Length != 2 || upstreamPermits.Length == 0
                || principalBlocks.Select(rule => rule.AddressFamily).Distinct().Count() != 2
                || dnsPermits.Select(rule => rule.Protocol).Order().SequenceEqual([6, 17]) is false
                || dnsPermits.Select(rule => rule.RemoteAddress).Distinct(StringComparer.Ordinal).Count() != 1
                || group.Where(rule => rule.IdentityCondition != "none; endpoint-wide listener block")
                    .Any(rule => rule.LeaseSid != principalBlocks[0].LeaseSid
                        || rule.IdentityCondition != principalBlocks[0].IdentityCondition)
                || group.Where(rule => rule.Action == LeasePolicyAction.Permit)
                    .Where(rule => rule.RuleId.Contains("worker-allow-", StringComparison.Ordinal))
                    .Select(rule => rule.AppIdHex).Distinct(StringComparer.Ordinal).Count() != 1
                || browserPermits[0].AppIdHex == upstreamPermits[0].AppIdHex
                || listenerBlocks[0].RemotePort != browserPermits[0].RemotePort)
            {
                throw new ArgumentException("A dynamic lease must have one complete, identity-consistent listener/DNS/upstream rule set.");
            }
        }
    }

    private static void ValidateIdentity(LeasePolicyRule rule)
    {
        switch (rule.IdentityCondition)
        {
            case "ALE_APP_ID":
                if (rule.AppIdHex is null || rule.LeaseSid is not null)
                    throw new ArgumentException("ALE_APP_ID rules must contain exactly an AppID identity.");
                ValidateAppId(rule.AppIdHex);
                break;
            case "ALE_USER_ID":
            case "ALE_PACKAGE_ID":
                if (rule.LeaseSid is null)
                    throw new ArgumentException("Principal identity rules require a lease SID.");
                ValidateSid(rule.LeaseSid, rule.IdentityCondition);
                if (rule.AppIdHex is not null)
                    ValidateAppId(rule.AppIdHex);
                break;
            case "none; endpoint-wide listener block":
                if (rule.AppIdHex is not null || rule.LeaseSid is not null)
                    throw new ArgumentException("Endpoint-wide rules must omit both identity conditions.");
                break;
            default:
                throw new ArgumentException("Unsupported identity condition; refusing to create a broad or ambiguous native rule.");
        }
    }

    private static void ValidateAppId(string value)
    {
        if (string.IsNullOrEmpty(value) || value.Length > MaxAppIdBytes * 2 || value.Length % 2 != 0)
            throw new ArgumentException("AppID byte blob is empty or exceeds the materializer bound.");
        try
        {
            byte[] bytes = Convert.FromHexString(value);
            try
            {
                if (bytes.All(item => item == 0))
                    throw new ArgumentException("AppID byte blob cannot be all zero.");
            }
            finally
            {
                CryptographicOperations.ZeroMemory(bytes);
            }
        }
        catch (FormatException exception)
        {
            throw new ArgumentException("AppID must be hexadecimal.", exception);
        }
    }

    private static void ValidateSid(string value, string condition)
    {
        var sid = new SecurityIdentifier(value);
        if (!StringComparer.Ordinal.Equals(sid.Value, value))
            throw new ArgumentException("SID must use its canonical textual representation.");

        string[] parts = value.Split('-');
        bool valid = condition == "ALE_USER_ID"
            ? parts.Length == 8 && value.StartsWith("S-1-5-21-", StringComparison.Ordinal)
                && parts.Skip(4).Take(3).All(IsPositiveDecimal)
                && uint.TryParse(parts[7], out uint rid) && rid >= 1000
            : parts.Length == 11 && value.StartsWith("S-1-15-2-", StringComparison.Ordinal)
                && parts.Skip(2).All(IsCanonicalDecimal);
        if (!valid)
            throw new ArgumentException("SID does not match the allowed lease-user or AppContainer-package shape.");
    }

    private static bool IsCanonicalDecimal(string value) =>
        uint.TryParse(value, out uint number) && number.ToString(System.Globalization.CultureInfo.InvariantCulture) == value;

    private static bool IsPositiveDecimal(string value) =>
        uint.TryParse(value, out uint number) && number > 0
        && number.ToString(System.Globalization.CultureInfo.InvariantCulture) == value;

    private static FWPM_FILTER0 BuildFilter(UnmanagedArena arena, LeasePolicyRule rule, Guid providerKey, Guid sublayerKey)
    {
        FWPM_FILTER0 filter = default;
        filter.filterKey = StableFilterKey(providerKey, rule.RuleId);
        filter.displayData.name = arena.AllocateUtf16(rule.RuleId);
        filter.displayData.description = arena.AllocateUtf16(rule.Purpose);
        filter.flags = rule.Lifetime == LeasePolicyLifetime.PersistentDefaultDeny
            ? FWPM_FILTER_FLAGS.FWPM_FILTER_FLAG_PERSISTENT
            : FWPM_FILTER_FLAGS.FWPM_FILTER_FLAG_NONE;
        Guid* provider = arena.Allocate<Guid>();
        *provider = providerKey;
        filter.providerKey = provider;
        filter.layerKey = rule.AddressFamily == LeasePolicyAddressFamily.IPv4
            ? WfpIdentifiers.AleAuthConnectV4 : WfpIdentifiers.AleAuthConnectV6;
        filter.subLayerKey = sublayerKey;
        filter.weight.type = FWP_DATA_TYPE.FWP_UINT8;
        filter.weight.uint8 = rule.WeightRangeIndex;
        filter.action.type = rule.Action == LeasePolicyAction.Block
            ? FWP_ACTION_TYPE.FWP_ACTION_BLOCK : FWP_ACTION_TYPE.FWP_ACTION_PERMIT;

        List<ConditionValue> values = BuildConditionValues(arena, rule);
        FWPM_FILTER_CONDITION0* conditions = arena.AllocateArray<FWPM_FILTER_CONDITION0>(values.Count);
        for (int index = 0; index < values.Count; index++)
        {
            conditions[index] = new FWPM_FILTER_CONDITION0
            {
                fieldKey = values[index].FieldKey,
                matchType = FWP_MATCH_TYPE.FWP_MATCH_EQUAL,
                conditionValue = values[index].Value,
            };
        }
        filter.numFilterConditions = checked((uint)values.Count);
        filter.filterCondition = conditions;
        return filter;
    }

    private static List<ConditionValue> BuildConditionValues(UnmanagedArena arena, LeasePolicyRule rule)
    {
        var values = new List<ConditionValue>(capacity: 5);
        if (rule.AppIdHex is not null)
        {
            byte[] appId = Convert.FromHexString(rule.AppIdHex);
            FWP_BYTE_BLOB* blob;
            try
            {
                blob = arena.Allocate<FWP_BYTE_BLOB>();
                blob->size = checked((uint)appId.Length);
                blob->data = arena.AllocateBytes(appId);
            }
            finally
            {
                CryptographicOperations.ZeroMemory(appId);
            }
            values.Add(new ConditionValue(WfpIdentifiers.AleAppId, BlobValue(FWP_DATA_TYPE.FWP_BYTE_BLOB_TYPE, blob)));
        }

        if (rule.IdentityCondition == "ALE_USER_ID")
        {
            string sddl = $"D:(A;;0x{FwpmActrlMatchFilter:X};;;{rule.LeaseSid})";
            var descriptor = new RawSecurityDescriptor(sddl);
            byte[] bytes = new byte[descriptor.BinaryLength];
            descriptor.GetBinaryForm(bytes, 0);
            FWP_BYTE_BLOB* blob = arena.Allocate<FWP_BYTE_BLOB>();
            blob->size = checked((uint)bytes.Length);
            blob->data = arena.AllocateBytes(bytes);
            values.Add(new ConditionValue(WfpIdentifiers.AleUserId, BlobValue(FWP_DATA_TYPE.FWP_SECURITY_DESCRIPTOR_TYPE, blob)));
        }
        else if (rule.IdentityCondition == "ALE_PACKAGE_ID")
        {
            var sid = new SecurityIdentifier(rule.LeaseSid!);
            byte[] bytes = new byte[sid.BinaryLength];
            sid.GetBinaryForm(bytes, 0);
            values.Add(new ConditionValue(WfpIdentifiers.AlePackageId, PointerValue(FWP_DATA_TYPE.FWP_SID, arena.AllocateBytes(bytes))));
        }

        if (rule.Protocol is int protocol)
        {
            FWP_CONDITION_VALUE0 value = default;
            value.type = FWP_DATA_TYPE.FWP_UINT8;
            value.uint8 = checked((byte)protocol);
            values.Add(new ConditionValue(WfpIdentifiers.IpProtocol, value));
        }
        if (rule.RemoteAddress is not null)
        {
            IPAddress address = IPAddress.Parse(rule.RemoteAddress);
            byte[] bytes = address.GetAddressBytes();
            FWP_CONDITION_VALUE0 value = default;
            if (address.AddressFamily == AddressFamily.InterNetwork)
            {
                value.type = FWP_DATA_TYPE.FWP_UINT32;
                // WFP IPv4 address conditions are represented as host-order UINT32 values.
                value.uint32 = BinaryPrimitives.ReadUInt32BigEndian(bytes);
            }
            else
            {
                FWP_BYTE_ARRAY16* addressBytes = arena.Allocate<FWP_BYTE_ARRAY16>();
                addressBytes->byteArray16 = bytes;
                value.type = FWP_DATA_TYPE.FWP_BYTE_ARRAY16_TYPE;
                value.byteArray16 = addressBytes;
            }
            values.Add(new ConditionValue(WfpIdentifiers.IpRemoteAddress, value));
        }
        if (rule.RemotePort is int port)
        {
            FWP_CONDITION_VALUE0 value = default;
            value.type = FWP_DATA_TYPE.FWP_UINT16;
            value.uint16 = checked((ushort)port);
            values.Add(new ConditionValue(WfpIdentifiers.IpRemotePort, value));
        }
        return values;
    }

    private static FWP_CONDITION_VALUE0 BlobValue(FWP_DATA_TYPE type, FWP_BYTE_BLOB* blob)
    {
        FWP_CONDITION_VALUE0 value = default;
        value.type = type;
        if (type == FWP_DATA_TYPE.FWP_BYTE_BLOB_TYPE) value.byteBlob = blob;
        else if (type == FWP_DATA_TYPE.FWP_SECURITY_DESCRIPTOR_TYPE) value.sd = blob;
        else throw new ArgumentOutOfRangeException(nameof(type));
        return value;
    }

    private static FWP_CONDITION_VALUE0 PointerValue(FWP_DATA_TYPE type, byte* pointer)
    {
        FWP_CONDITION_VALUE0 value = default;
        value.type = type;
        value.sid = (Windows.Win32.Security.SID*)pointer;
        return value;
    }

    private static NativeFilterSnapshot Inspect(FWPM_FILTER0 filter, string ruleId, Guid providerKey, Guid sublayerKey)
    {
        if (filter.filterKey == Guid.Empty || filter.providerKey is null || *filter.providerKey != providerKey
            || filter.layerKey == Guid.Empty || filter.subLayerKey != sublayerKey
            || filter.filterCondition is null || filter.numFilterConditions > 5
            || filter.displayData.name.Value is null
            || (filter.flags & FWPM_FILTER_FLAGS.FWPM_FILTER_FLAG_CLEAR_ACTION_RIGHT) != 0
            || filter.weight.type != FWP_DATA_TYPE.FWP_UINT8
            || filter.action.type is not (FWP_ACTION_TYPE.FWP_ACTION_BLOCK or FWP_ACTION_TYPE.FWP_ACTION_PERMIT))
        {
            throw new InvalidOperationException("The constructed native filter failed its in-memory structural checks.");
        }

        var conditions = new NativeConditionSnapshot[filter.numFilterConditions];
        for (int index = 0; index < conditions.Length; index++)
            conditions[index] = InspectCondition(filter.filterCondition[index]);

        return new NativeFilterSnapshot(
            ruleId,
            filter.filterKey,
            *filter.providerKey,
            filter.subLayerKey,
            filter.layerKey,
            filter.action.type.ToString(),
            (filter.flags & FWPM_FILTER_FLAGS.FWPM_FILTER_FLAG_CLEAR_ACTION_RIGHT) != 0,
            (filter.flags & FWPM_FILTER_FLAGS.FWPM_FILTER_FLAG_PERSISTENT) != 0,
            filter.weight.uint8,
            Array.AsReadOnly(conditions));
    }

    private static NativeConditionSnapshot InspectCondition(FWPM_FILTER_CONDITION0 condition)
    {
        string field = ConditionFieldName(condition.fieldKey);
        if (condition.matchType != FWP_MATCH_TYPE.FWP_MATCH_EQUAL)
            throw new InvalidOperationException("Only exact-match conditions are supported by this materializer.");

        FWP_CONDITION_VALUE0 value = condition.conditionValue;
        string text = value.type switch
        {
            FWP_DATA_TYPE.FWP_UINT8 => value.uint8.ToString(System.Globalization.CultureInfo.InvariantCulture),
            FWP_DATA_TYPE.FWP_UINT16 => value.uint16.ToString(System.Globalization.CultureInfo.InvariantCulture),
            FWP_DATA_TYPE.FWP_UINT32 when condition.fieldKey == WfpIdentifiers.IpRemoteAddress
                => new IPAddress(UInt32ToAddressBytes(value.uint32)).ToString(),
            FWP_DATA_TYPE.FWP_BYTE_BLOB_TYPE => DescribeBlob(value.byteBlob, "app-id"),
            FWP_DATA_TYPE.FWP_SECURITY_DESCRIPTOR_TYPE => DescribeSecurityDescriptor(value.sd),
            FWP_DATA_TYPE.FWP_SID => DescribeSid((byte*)value.sid),
            FWP_DATA_TYPE.FWP_BYTE_ARRAY16_TYPE => new IPAddress(new ReadOnlySpan<byte>((byte*)&value.byteArray16->byteArray16, 16)).ToString(),
            _ => throw new InvalidOperationException($"Unsupported native condition data type {value.type}.")
        };
        uint? rawUInt32Value = value.type == FWP_DATA_TYPE.FWP_UINT32
            && condition.fieldKey == WfpIdentifiers.IpRemoteAddress
                ? value.uint32
                : null;
        return new NativeConditionSnapshot(field, condition.matchType.ToString(), value.type.ToString(), text, rawUInt32Value);
    }

    private static string DescribeBlob(FWP_BYTE_BLOB* blob, string label)
    {
        if (blob is null || blob->data is null || blob->size == 0 || blob->size > MaxAppIdBytes)
            throw new InvalidOperationException("A native byte blob has an invalid pointer or size.");
        ReadOnlySpan<byte> bytes = new(blob->data, checked((int)blob->size));
        return $"{label};bytes={blob->size};sha256={Convert.ToHexString(SHA256.HashData(bytes))}";
    }

    private static string DescribeSecurityDescriptor(FWP_BYTE_BLOB* blob)
    {
        if (blob is null || blob->data is null || blob->size is 0 or > 4096)
            throw new InvalidOperationException("A native security descriptor has an invalid pointer or size.");
        byte[] bytes = new ReadOnlySpan<byte>(blob->data, checked((int)blob->size)).ToArray();
        var descriptor = new RawSecurityDescriptor(bytes, 0);
        if ((descriptor.ControlFlags & ControlFlags.SelfRelative) == 0 || descriptor.DiscretionaryAcl is null
            || descriptor.DiscretionaryAcl.Count != 1
            || descriptor.DiscretionaryAcl[0] is not CommonAce ace
            || ace.AccessMask != FwpmActrlMatchFilter || ace.AceQualifier != AceQualifier.AccessAllowed)
            throw new InvalidOperationException("ALE_USER_ID security descriptor did not preserve the narrow match-filter ACE.");
        return $"self-relative;allow=0x{ace.AccessMask:X};sid={ace.SecurityIdentifier.Value}";
    }

    private static string DescribeSid(byte* pointer)
    {
        if (pointer is null) throw new InvalidOperationException("An ALE_PACKAGE_ID SID pointer is null.");
        if (pointer[1] > 15) throw new InvalidOperationException("The SID subauthority count exceeds the Windows limit.");
        return new SecurityIdentifier((IntPtr)pointer).Value;
    }

    private static byte[] UInt32ToAddressBytes(uint value)
    {
        byte[] bytes = new byte[4];
        BinaryPrimitives.WriteUInt32BigEndian(bytes, value);
        return bytes;
    }

    private static string ConditionFieldName(Guid fieldKey) => fieldKey switch
    {
        var key when key == WfpIdentifiers.AleAppId => "ALE_APP_ID",
        var key when key == WfpIdentifiers.AleUserId => "ALE_USER_ID",
        var key when key == WfpIdentifiers.AlePackageId => "ALE_PACKAGE_ID",
        var key when key == WfpIdentifiers.IpProtocol => "IP_PROTOCOL",
        var key when key == WfpIdentifiers.IpRemoteAddress => "IP_REMOTE_ADDRESS",
        var key when key == WfpIdentifiers.IpRemotePort => "IP_REMOTE_PORT",
        _ => throw new InvalidOperationException("The native condition has an unrecognized field GUID.")
    };

    private static Guid StableFilterKey(Guid providerKey, string ruleId)
    {
        byte[] identity = System.Text.Encoding.UTF8.GetBytes($"DouyinTranscript.Wfp.v1\0{providerKey:D}\0{ruleId}");
        return new Guid(SHA256.HashData(identity).AsSpan(0, 16));
    }

    private readonly record struct ConditionValue(Guid FieldKey, FWP_CONDITION_VALUE0 Value);

    private sealed class UnmanagedArena : IDisposable
    {
        private readonly List<(IntPtr Pointer, int Size)> _allocations = [];
        private bool _disposed;

        public T* Allocate<T>() where T : unmanaged => (T*)AllocateBytes(sizeof(T));

        public T* AllocateArray<T>(int count) where T : unmanaged
        {
            if (count is < 1 or > 5) throw new ArgumentOutOfRangeException(nameof(count));
            return (T*)AllocateBytes(checked(sizeof(T) * count));
        }

        public byte* AllocateBytes(ReadOnlySpan<byte> value)
        {
            if (value.IsEmpty) throw new ArgumentException("Zero-byte unmanaged allocations are not allowed.", nameof(value));
            byte* pointer = (byte*)AllocateBytes(value.Length);
            value.CopyTo(new Span<byte>(pointer, value.Length));
            return pointer;
        }

        public char* AllocateUtf16(string value)
        {
            char* pointer = (char*)AllocateBytes(checked((value.Length + 1) * sizeof(char)));
            value.AsSpan().CopyTo(new Span<char>(pointer, value.Length));
            pointer[value.Length] = '\0';
            return pointer;
        }

        public void Dispose()
        {
            if (_disposed) return;
            for (int index = _allocations.Count - 1; index >= 0; index--)
            {
                (IntPtr pointer, int size) = _allocations[index];
                CryptographicOperations.ZeroMemory(new Span<byte>((void*)pointer, size));
                Marshal.FreeHGlobal(pointer);
            }
            _allocations.Clear();
            _disposed = true;
        }

        private void* AllocateBytes(int size)
        {
            ObjectDisposedException.ThrowIf(_disposed, this);
            if (size is < 1 or > 1_048_576) throw new ArgumentOutOfRangeException(nameof(size));
            IntPtr pointer = Marshal.AllocHGlobal(size);
            _allocations.Add((pointer, size));
            new Span<byte>((void*)pointer, size).Clear();
            return (void*)pointer;
        }
    }
}
