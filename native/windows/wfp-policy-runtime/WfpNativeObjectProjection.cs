using WfpPolicyPlan;

namespace WfpPolicy.Runtime;

/// <summary>
/// One scalar in the versioned, closed-world projection returned by a WFP
/// store. Values use a canonical invariant representation; native pointers,
/// buffers, and arrays must be copied and normalized before this DTO is built.
/// </summary>
internal sealed record WfpNativeObjectField(string Name, string? Value);

/// <summary>
/// A copied projection of one native provider, sublayer, or filter. A store must
/// set IsComplete only when it decoded every field defined by this schema and
/// can prove that no execution-relevant field was unknown or unreadable. The
/// baseline coordinator rejects incomplete, old-version, malformed, missing,
/// extra, unordered, or value-mismatched projections.
///
/// Schema v1 covers the native creation fields modeled by the current managed
/// baseline. It intentionally does not make an absent native backend appear
/// complete: before production use, the Windows backend must separately settle
/// and project native access-control descriptors and BFE-derived filter fields
/// such as effective weight. Until then, an adapter that cannot meet the full
/// native readback contract must fail closed.
/// </summary>
internal sealed class WfpNativeObjectProjection : IEquatable<WfpNativeObjectProjection>
{
    internal const int CurrentSchemaVersion = 1;

    public WfpNativeObjectProjection(
        int schemaVersion,
        string? objectKind,
        bool isComplete,
        IEnumerable<WfpNativeObjectField>? fields)
    {
        SchemaVersion = schemaVersion;
        ObjectKind = objectKind;
        IsComplete = isComplete;
        Fields = fields is null ? null : Array.AsReadOnly(fields.ToArray());
    }

    public int SchemaVersion { get; }
    public string? ObjectKind { get; }
    public bool IsComplete { get; }
    public IReadOnlyList<WfpNativeObjectField>? Fields { get; }

    public static WfpNativeObjectProjection ForProvider(WfpProviderIdentity provider) => Create(
        "FWPM_PROVIDER0",
        ("displayData.description", provider.Description),
        ("displayData.name", provider.Name),
        ("flags", "FWPM_PROVIDER_FLAG_PERSISTENT"),
        ("providerData.hex", string.Empty),
        ("providerData.size", "0"),
        ("providerKey", FormatGuid(provider.Key)),
        ("serviceName", provider.ServiceName));

    public static WfpNativeObjectProjection ForDynamicLeaseProvider(DynamicLeaseProviderIdentity provider) => Create(
        "FWPM_PROVIDER0",
        ("displayData.description", provider.Description),
        ("displayData.name", provider.Name),
        // An empty flags value means FWPM_PROVIDER_FLAG_PERSISTENT is absent;
        // lifetime is owned by the lease's dynamic engine session.
        ("flags", string.Empty),
        ("providerData.hex", string.Empty),
        ("providerData.size", "0"),
        ("providerKey", FormatGuid(provider.Key)),
        ("serviceName", "null"));

    public static WfpNativeObjectProjection ForSublayer(WfpSublayerIdentity sublayer) => Create(
        "FWPM_SUBLAYER0",
        ("displayData.description", sublayer.Description),
        ("displayData.name", sublayer.Name),
        ("flags", "FWPM_SUBLAYER_FLAG_PERSISTENT"),
        ("providerData.hex", string.Empty),
        ("providerData.size", "0"),
        ("providerKey", FormatGuid(sublayer.ProviderKey)),
        ("subLayerKey", FormatGuid(sublayer.Key)),
        ("weight", sublayer.Weight.ToString(System.Globalization.CultureInfo.InvariantCulture)));

    public static WfpNativeObjectProjection ForFilter(WfpFilterIdentity filter)
    {
        ArgumentNullException.ThrowIfNull(filter);
        ArgumentNullException.ThrowIfNull(filter.Rule);

        LeasePolicyRule rule = filter.Rule;
        string layer = rule.AddressFamily switch
        {
            LeasePolicyAddressFamily.IPv4 => "FWPM_LAYER_ALE_AUTH_CONNECT_V4",
            LeasePolicyAddressFamily.IPv6 => "FWPM_LAYER_ALE_AUTH_CONNECT_V6",
            _ => $"unknown-address-family:{(int)rule.AddressFamily}",
        };
        string appId = rule.AppIdHex is null ? "null" : NormalizeHex(rule.AppIdHex);
        string action = rule.Action switch
        {
            LeasePolicyAction.Block => "FWP_ACTION_BLOCK",
            LeasePolicyAction.Permit => "FWP_ACTION_PERMIT",
            _ => $"unknown-action:{(int)rule.Action}",
        };
        string flags = string.Join(
            ",",
            new[]
            {
                filter.Persistent ? "FWPM_FILTER_FLAG_PERSISTENT" : null,
                rule.ClearActionRight ? "FWPM_FILTER_FLAG_CLEAR_ACTION_RIGHT" : null,
            }.Where(value => value is not null));

        return Create(
            "FWPM_FILTER0",
            ("action.calloutKey", FormatGuid(Guid.Empty)),
            ("action.type", action),
            ("clearActionRight", FormatBoolean(rule.ClearActionRight)),
            ("conditions.canonical", CanonicalConditions(rule)),
            ("conditions.count", ConditionCount(rule).ToString(System.Globalization.CultureInfo.InvariantCulture)),
            ("context", "zero"),
            ("displayData.description", filter.Description),
            ("displayData.name", filter.Name),
            ("filterKey", FormatGuid(filter.Key)),
            ("flags", flags),
            ("layerKey", layer),
            ("persistent", FormatBoolean(filter.Persistent)),
            ("providerData.hex", string.Empty),
            ("providerData.size", "0"),
            ("providerKey", FormatGuid(filter.ProviderKey)),
            ("reserved", "null"),
            ("subLayerKey", FormatGuid(filter.SublayerKey)),
            ("weight.type", "FWP_UINT8"),
            ("weight.value", rule.WeightRangeIndex.ToString(System.Globalization.CultureInfo.InvariantCulture)),
            ("rule.action", rule.Action.ToString()),
            ("rule.addressFamily", rule.AddressFamily.ToString()),
            ("rule.appIdHex", appId),
            ("rule.clearActionRight", FormatBoolean(rule.ClearActionRight)),
            ("rule.identityCondition", rule.IdentityCondition),
            ("rule.leaseId", rule.LeaseId ?? "null"),
            ("rule.leaseSid", rule.LeaseSid ?? "null"),
            ("rule.lifetime", rule.Lifetime.ToString()),
            ("rule.protocol", rule.Protocol?.ToString(System.Globalization.CultureInfo.InvariantCulture) ?? "null"),
            ("rule.remoteAddress", rule.RemoteAddress ?? "null"),
            ("rule.remotePort", rule.RemotePort?.ToString(System.Globalization.CultureInfo.InvariantCulture) ?? "null"),
            ("rule.ruleId", rule.RuleId),
            ("rule.weightRangeIndex", rule.WeightRangeIndex.ToString(System.Globalization.CultureInfo.InvariantCulture)));
    }

    /// <summary>
    /// Require an actual store projection to match the deterministic expected
    /// projection exactly. The ordered field list is part of the wire contract;
    /// silently dropping, adding, reordering, or failing to decode a field is an
    /// ownership/readiness failure, not a best-effort match.
    /// </summary>
    public static void RequireExact(
        WfpNativeObjectProjection? actual,
        WfpNativeObjectProjection expected,
        string objectDescription)
    {
        ArgumentNullException.ThrowIfNull(expected);
        if (actual is null)
        {
            throw new WfpBaselineOwnershipException($"The WFP {objectDescription} has no native-object projection.");
        }
        if (!actual.IsComplete)
        {
            throw new WfpBaselineOwnershipException($"The WFP {objectDescription} native-object projection is incomplete.");
        }
        if (actual.SchemaVersion != CurrentSchemaVersion
            || actual.SchemaVersion != expected.SchemaVersion
            || !string.Equals(actual.ObjectKind, expected.ObjectKind, StringComparison.Ordinal))
        {
            throw new WfpBaselineOwnershipException($"The WFP {objectDescription} native-object projection has an unsupported version or type.");
        }
        if (actual.Fields is null || expected.Fields is null || actual.Fields.Count != expected.Fields.Count)
        {
            throw new WfpBaselineOwnershipException($"The WFP {objectDescription} native-object projection has missing or extra fields.");
        }

        string? priorName = null;
        for (int index = 0; index < expected.Fields.Count; index++)
        {
            WfpNativeObjectField? actualField = actual.Fields[index];
            WfpNativeObjectField expectedField = expected.Fields[index];
            if (actualField is null
                || string.IsNullOrWhiteSpace(actualField.Name)
                || actualField.Value is null
                || (priorName is not null && string.CompareOrdinal(priorName, actualField.Name) >= 0))
            {
                throw new WfpBaselineOwnershipException($"The WFP {objectDescription} native-object projection is malformed or non-canonical.");
            }
            if (!string.Equals(actualField.Name, expectedField.Name, StringComparison.Ordinal))
            {
                throw new WfpBaselineOwnershipException($"The WFP {objectDescription} native-object projection contains an unknown or missing field.");
            }
            if (!string.Equals(actualField.Value, expectedField.Value, StringComparison.Ordinal))
            {
                throw new WfpBaselineOwnershipException($"The WFP {objectDescription} native-object projection differs from the expected object.");
            }
            priorName = actualField.Name;
        }
    }

    public bool Equals(WfpNativeObjectProjection? other) =>
        other is not null
        && SchemaVersion == other.SchemaVersion
        && string.Equals(ObjectKind, other.ObjectKind, StringComparison.Ordinal)
        && IsComplete == other.IsComplete
        && Fields is not null
        && other.Fields is not null
        && Fields.SequenceEqual(other.Fields);

    public override bool Equals(object? obj) => obj is WfpNativeObjectProjection other && Equals(other);

    public override int GetHashCode()
    {
        var hash = new HashCode();
        hash.Add(SchemaVersion);
        hash.Add(ObjectKind, StringComparer.Ordinal);
        hash.Add(IsComplete);
        if (Fields is not null)
        {
            foreach (WfpNativeObjectField field in Fields)
            {
                hash.Add(field);
            }
        }
        return hash.ToHashCode();
    }

    private static WfpNativeObjectProjection Create(string objectKind, params (string Name, string Value)[] fields) =>
        new(
            CurrentSchemaVersion,
            objectKind,
            isComplete: true,
            fields.OrderBy(field => field.Name, StringComparer.Ordinal)
                .Select(field => new WfpNativeObjectField(field.Name, field.Value)));

    private static string CanonicalConditions(LeasePolicyRule rule)
    {
        // This canonical value records every condition-bearing field understood
        // by the current policy model. The native adapter must independently
        // decode the FWPM_FILTER0 condition array and match this shape; it must
        // never populate this field by echoing the expected rule.
        return string.Join(
            ";",
            new[]
            {
                $"identity={rule.IdentityCondition}:{rule.AppIdHex ?? "null"}:{rule.LeaseSid ?? "null"}",
                $"remote={rule.RemoteAddress ?? "null"}",
                $"protocol={rule.Protocol?.ToString(System.Globalization.CultureInfo.InvariantCulture) ?? "null"}",
                $"port={rule.RemotePort?.ToString(System.Globalization.CultureInfo.InvariantCulture) ?? "null"}",
            });
    }

    private static int ConditionCount(LeasePolicyRule rule)
    {
        int count = (rule.AppIdHex is not null || rule.LeaseSid is not null) ? 1 : 0;
        if (rule.RemoteAddress is not null)
            count++;
        if (rule.Protocol is not null)
            count++;
        if (rule.RemotePort is not null)
            count++;
        return count;
    }

    private static string NormalizeHex(string value)
    {
        try
        {
            return Convert.ToHexString(Convert.FromHexString(value)).ToLowerInvariant();
        }
        catch (FormatException)
        {
            return $"invalid-hex:{value}";
        }
    }

    private static string FormatGuid(Guid value) => value.ToString("D").ToLowerInvariant();
    private static string FormatBoolean(bool value) => value ? "true" : "false";
}
