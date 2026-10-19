using System.Text;
using WfpPolicy.NativeReadback;
using WfpPolicyPlan;

namespace WfpPolicy.Runtime;

/// <summary>
/// Immutable, canonical evidence for the service-owned objects projected from
/// one native readback. The complete source snapshot is retained so consumers
/// do not lose fields that have no Runtime identity equivalent (for example,
/// filter IDs and BFE-derived effective weights).
/// </summary>
internal sealed class WfpNativeReadbackProjection : IEquatable<WfpNativeReadbackProjection>
{
    internal const int CurrentSchemaVersion = 1;

    internal WfpNativeReadbackProjection(
        int schemaVersion,
        WfpSnapshot sourceSnapshot,
        IEnumerable<WfpNativeReadbackObjectProjection> objects)
    {
        this.SchemaVersion = schemaVersion;
        this.SourceSnapshot = sourceSnapshot;
        this.Objects = Array.AsReadOnly(objects.ToArray());
    }

    internal int SchemaVersion { get; }
    internal WfpSnapshot SourceSnapshot { get; }
    internal IReadOnlyList<WfpNativeReadbackObjectProjection> Objects { get; }

    internal void RequireCanonical()
    {
        if (this.SchemaVersion != CurrentSchemaVersion || !this.SourceSnapshot.IsComplete)
        {
            throw new WfpBaselineOwnershipException("The native WFP readback projection is incomplete or has an unsupported version.");
        }

        WfpNativeReadbackObjectProjection[] sorted = this.Objects
            .OrderBy(item => item.ObjectKind, StringComparer.Ordinal)
            .ThenBy(item => item.ObjectKey, StringComparer.Ordinal)
            .ToArray();
        if (!this.Objects.SequenceEqual(sorted)
            || this.Objects.Select(item => (item.ObjectKind, item.ObjectKey)).Distinct().Count() != this.Objects.Count)
        {
            throw new WfpBaselineOwnershipException("The native WFP readback projection is not uniquely and canonically ordered.");
        }

        foreach (WfpNativeReadbackObjectProjection item in this.Objects)
        {
            if (string.IsNullOrWhiteSpace(item.ObjectKind)
                || string.IsNullOrWhiteSpace(item.ObjectKey)
                || item.Fields is null
                || item.Fields.Count == 0)
            {
                throw new WfpBaselineOwnershipException("The native WFP readback projection contains a malformed object.");
            }

            string? previousName = null;
            foreach (WfpNativeObjectField? field in item.Fields)
            {
                if (field is null
                    || string.IsNullOrWhiteSpace(field.Name)
                    || field.Value is null
                    || (previousName is not null && string.CompareOrdinal(previousName, field.Name) >= 0))
                {
                    throw new WfpBaselineOwnershipException("The native WFP readback projection contains a missing or non-canonical field.");
                }
                previousName = field.Name;
            }
        }
    }

    public bool Equals(WfpNativeReadbackProjection? other) =>
        other is not null
        && this.SchemaVersion == other.SchemaVersion
        && this.Objects.SequenceEqual(other.Objects);

    public override bool Equals(object? obj) => obj is WfpNativeReadbackProjection other && this.Equals(other);

    public override int GetHashCode()
    {
        var hash = new HashCode();
        hash.Add(this.SchemaVersion);
        foreach (WfpNativeReadbackObjectProjection item in this.Objects)
        {
            hash.Add(item);
        }
        return hash.ToHashCode();
    }
}

internal sealed class WfpNativeReadbackObjectProjection : IEquatable<WfpNativeReadbackObjectProjection>
{
    internal WfpNativeReadbackObjectProjection(
        string objectKind,
        string objectKey,
        IEnumerable<WfpNativeObjectField> fields)
    {
        this.ObjectKind = objectKind;
        this.ObjectKey = objectKey;
        this.Fields = Array.AsReadOnly(fields.OrderBy(field => field.Name, StringComparer.Ordinal).ToArray());
    }

    internal string ObjectKind { get; }
    internal string ObjectKey { get; }
    internal IReadOnlyList<WfpNativeObjectField> Fields { get; }

    public bool Equals(WfpNativeReadbackObjectProjection? other) =>
        other is not null
        && string.Equals(this.ObjectKind, other.ObjectKind, StringComparison.Ordinal)
        && string.Equals(this.ObjectKey, other.ObjectKey, StringComparison.Ordinal)
        && this.Fields.SequenceEqual(other.Fields);

    public override bool Equals(object? obj) => obj is WfpNativeReadbackObjectProjection other && this.Equals(other);

    public override int GetHashCode()
    {
        var hash = new HashCode();
        hash.Add(this.ObjectKind, StringComparer.Ordinal);
        hash.Add(this.ObjectKey, StringComparer.Ordinal);
        foreach (WfpNativeObjectField field in this.Fields)
        {
            hash.Add(field);
        }
        return hash.ToHashCode();
    }
}

/// <summary>
/// Bridges a copied native snapshot into the Runtime's value-only store DTO.
/// It deliberately accepts only the exact persistent AppID block objects the
/// baseline reconciler understands. All other native shapes fail before a
/// caller can open a mutation transaction.
/// </summary>
internal static class WfpNativeReadbackAdapter
{
    private const uint PersistentFlag = 0x00000001;
    private const int FwpUint8Type = 1;
    private const int FwpByteBlobType = 12;
    private const int FwpActionBlock = 0x1001;
    private const int FwpMatchEqual = 0;
    private const string AleAuthConnectV4 = "c38d57d1-05a7-4c33-904f-7fbceee60e82";
    private const string AleAuthConnectV6 = "4a72393b-319f-44bc-84c3-ba54dcb3b6b4";

    internal static WfpPolicySnapshot ToPolicySnapshot(
        WfpSnapshot source,
        Guid providerKey,
        Guid sublayerKey)
    {
        ArgumentNullException.ThrowIfNull(source);
        if (!source.IsComplete)
        {
            SnapshotIssue? issue = source.Issues.FirstOrDefault()
                ?? source.Providers.SelectMany(item => item.Issues).FirstOrDefault()
                ?? source.Sublayers.SelectMany(item => item.Issues).FirstOrDefault()
                ?? source.Callouts.SelectMany(item => item.Issues).FirstOrDefault()
                ?? source.ProviderContexts.SelectMany(item => item.Issues).FirstOrDefault()
                ?? source.Filters.SelectMany(item => item.Issues).FirstOrDefault();
            string reason = issue is null
                ? "The native WFP readback has no complete-read proof."
                : $"The native WFP readback is incomplete ({issue.Code} on {issue.ObjectKind}).";
            throw new WfpBaselineOwnershipException(reason);
        }

        RejectDuplicateKeys(source);

        ProviderSnapshot? nativeProvider = source.Providers.SingleOrDefault(item => item.Key == providerKey);
        SublayerSnapshot? nativeSublayer = source.Sublayers.SingleOrDefault(item => item.Key == sublayerKey);
        if (nativeSublayer is not null && nativeSublayer.ProviderKey != providerKey)
        {
            throw new WfpBaselineOwnershipException("The service-owned WFP sublayer is attached to a different provider.");
        }

        WfpProviderIdentity? provider = nativeProvider is null ? null : MapProvider(nativeProvider);
        WfpSublayerIdentity? sublayer = nativeSublayer is null ? null : MapSublayer(nativeSublayer, providerKey);
        FilterSnapshot[] nativeFilters = source.Filters
            .Where(item => item.ProviderKey == providerKey || item.SublayerKey == sublayerKey)
            .OrderBy(item => item.Key)
            .ToArray();
        if (nativeFilters.Length > 4096)
        {
            throw new WfpBaselineOwnershipException("The service-owned WFP filter set exceeds the adapter bound.");
        }

        WfpFilterIdentity[] filters = nativeFilters.Select(item => MapFilter(item, providerKey, sublayerKey)).ToArray();
        WfpNativeReadbackObjectProjection[] projectedObjects = [];
        if (nativeProvider is not null)
        {
            projectedObjects = [Project(nativeProvider)];
        }
        if (nativeSublayer is not null)
        {
            projectedObjects = projectedObjects.Append(Project(nativeSublayer)).ToArray();
        }
        projectedObjects = projectedObjects
            .Concat(nativeFilters.Select(Project))
            .OrderBy(item => item.ObjectKind, StringComparer.Ordinal)
            .ThenBy(item => item.ObjectKey, StringComparer.Ordinal)
            .ToArray();

        var readbackProjection = new WfpNativeReadbackProjection(
            WfpNativeReadbackProjection.CurrentSchemaVersion,
            source,
            projectedObjects);
        readbackProjection.RequireCanonical();
        return new WfpPolicySnapshot(
            provider,
            sublayer,
            Array.AsReadOnly(filters),
            readbackProjection);
    }

    private static WfpProviderIdentity MapProvider(ProviderSnapshot item)
    {
        if (item.Flags != PersistentFlag
            || item.ProviderData.Count != 0
            || item.Name is null
            || item.Description is null
            || item.ServiceName is null)
        {
            throw new WfpBaselineOwnershipException("The native WFP provider has unsupported or missing baseline fields.");
        }

        var provider = new WfpProviderIdentity(item.Key, item.Name, item.Description, item.ServiceName);
        return provider with { NativeProjection = WfpNativeObjectProjection.ForProvider(provider) };
    }

    private static WfpSublayerIdentity MapSublayer(SublayerSnapshot item, Guid providerKey)
    {
        if (item.Flags != PersistentFlag
            || item.ProviderData.Count != 0
            || item.ProviderKey != providerKey
            || item.Name is null
            || item.Description is null)
        {
            throw new WfpBaselineOwnershipException("The native WFP sublayer has unsupported or missing baseline fields.");
        }

        var sublayer = new WfpSublayerIdentity(
            item.Key,
            providerKey,
            item.Name,
            item.Description,
            item.Weight);
        return sublayer with { NativeProjection = WfpNativeObjectProjection.ForSublayer(sublayer) };
    }

    private static WfpFilterIdentity MapFilter(FilterSnapshot item, Guid providerKey, Guid sublayerKey)
    {
        if (item.ProviderKey != providerKey
            || item.SublayerKey != sublayerKey
            || item.Flags != PersistentFlag
            || item.ProviderData.Count != 0
            || item.Name is null
            || item.Description is null
            || item.ActionTypeCode != FwpActionBlock
            || !string.Equals(item.ActionTypeName, "FWP_ACTION_BLOCK", StringComparison.Ordinal)
            || item.CalloutKey is not null
            || item.RawContext.GetValueOrDefault() != 0
            || item.ProviderContextKey is not null
            || !item.EffectiveWeight.IsDecoded)
        {
            throw new WfpBaselineOwnershipException("The native WFP filter is not a complete persistent baseline block object.");
        }

        LeasePolicyAddressFamily addressFamily = item.LayerKey.ToString("D").ToLowerInvariant() switch
        {
            AleAuthConnectV4 => LeasePolicyAddressFamily.IPv4,
            AleAuthConnectV6 => LeasePolicyAddressFamily.IPv6,
            _ => throw new WfpBaselineOwnershipException("The native WFP filter uses an unsupported ALE layer."),
        };
        if (item.Weight.TypeCode != FwpUint8Type
            || !string.Equals(item.Weight.TypeName, "FWP_UINT8", StringComparison.Ordinal)
            || !string.Equals(item.Weight.ScalarValue, LeasePolicyCompiler.DefaultDenyWeightRangeIndex.ToString(System.Globalization.CultureInfo.InvariantCulture), StringComparison.Ordinal)
            || !item.Weight.IsDecoded
            || item.Weight.BlobHex is not null)
        {
            throw new WfpBaselineOwnershipException("The native WFP filter has an unsupported weight value.");
        }

        if (item.Conditions.Count != 1)
        {
            throw new WfpBaselineOwnershipException("The native WFP baseline filter must contain exactly one AppID condition.");
        }
        FilterConditionSnapshot condition = item.Conditions[0];
        if (condition.FieldKey != WfpNativeConditionKeys.AleAppId
            || condition.MatchTypeCode != FwpMatchEqual
            || !string.Equals(condition.MatchTypeName, "FWP_MATCH_EQUAL", StringComparison.Ordinal)
            || condition.Value.TypeCode != FwpByteBlobType
            || !string.Equals(condition.Value.TypeName, "FWP_BYTE_BLOB_TYPE", StringComparison.Ordinal)
            || !condition.Value.IsDecoded
            || condition.Value.ScalarValue is not null
            || condition.Value.BlobHex is null)
        {
            throw new WfpBaselineOwnershipException("The native WFP baseline filter has an unsupported identity condition.");
        }

        string appIdHex;
        try
        {
            appIdHex = Convert.ToHexString(Convert.FromHexString(condition.Value.BlobHex)).ToLowerInvariant();
        }
        catch (FormatException exception)
        {
            throw new WfpBaselineOwnershipException($"The native WFP AppID condition is not canonical hexadecimal: {exception.Message}");
        }
        if (appIdHex.Length == 0)
        {
            throw new WfpBaselineOwnershipException("The native WFP AppID condition is empty.");
        }

        if (!item.Name.StartsWith(WfpServicePolicyIdentity.FilterNamePrefix, StringComparison.Ordinal))
        {
            throw new WfpBaselineOwnershipException("A filter in the service-owned WFP scope has no recognized ownership marker.");
        }
        string ruleId = item.Name[WfpServicePolicyIdentity.FilterNamePrefix.Length..];
        if (ruleId.Length == 0 || item.Key != WfpServicePolicyIdentity.FilterKey(ruleId))
        {
            throw new WfpBaselineOwnershipException("The service-owned WFP filter key does not match its stable rule identity.");
        }

        var rule = new LeasePolicyRule(
            RuleId: ruleId,
            Purpose: item.Description,
            AddressFamily: addressFamily,
            Action: LeasePolicyAction.Block,
            WeightRangeIndex: LeasePolicyCompiler.DefaultDenyWeightRangeIndex,
            Lifetime: LeasePolicyLifetime.PersistentDefaultDeny,
            LeaseId: null,
            AppIdHex: appIdHex,
            LeaseSid: null,
            IdentityCondition: "ALE_APP_ID",
            RemoteAddress: null,
            Protocol: null,
            RemotePort: null,
            ClearActionRight: false);
        var filter = new WfpFilterIdentity(
            item.Key,
            providerKey,
            sublayerKey,
            item.Name,
            item.Description,
            Persistent: true,
            Rule: rule);
        return filter with { NativeProjection = WfpNativeObjectProjection.ForFilter(filter) };
    }

    private static void RejectDuplicateKeys(WfpSnapshot source)
    {
        if (source.Providers.Select(item => item.Key).Distinct().Count() != source.Providers.Count
            || source.Sublayers.Select(item => item.Key).Distinct().Count() != source.Sublayers.Count
            || source.Filters.Select(item => item.Key).Distinct().Count() != source.Filters.Count)
        {
            throw new WfpBaselineOwnershipException("The native WFP snapshot contains duplicate object keys.");
        }
    }

    private static WfpNativeReadbackObjectProjection Project(ProviderSnapshot item) => Object(
        "FWPM_PROVIDER0",
        item.Key,
        ("displayData.description", Text(item.Description)),
        ("displayData.name", Text(item.Name)),
        ("flags", Number(item.Flags)),
        ("providerData.hex", Convert.ToHexString(item.ProviderData.ToArray()).ToLowerInvariant()),
        ("providerData.size", Number(item.ProviderData.Count)),
        ("providerKey", GuidValue(item.Key)),
        ("serviceName", Text(item.ServiceName)));

    private static WfpNativeReadbackObjectProjection Project(SublayerSnapshot item) => Object(
        "FWPM_SUBLAYER0",
        item.Key,
        ("displayData.description", Text(item.Description)),
        ("displayData.name", Text(item.Name)),
        ("flags", Number(item.Flags)),
        ("providerData.hex", Convert.ToHexString(item.ProviderData.ToArray()).ToLowerInvariant()),
        ("providerData.size", Number(item.ProviderData.Count)),
        ("providerKey", item.ProviderKey is Guid providerKey ? GuidValue(providerKey) : "null"),
        ("subLayerKey", GuidValue(item.Key)),
        ("weight", Number(item.Weight)));

    private static WfpNativeReadbackObjectProjection Project(FilterSnapshot item)
    {
        var fields = new List<(string Name, string Value)>
        {
            ("action.calloutKey", item.CalloutKey is Guid callout ? GuidValue(callout) : "null"),
            ("action.type.code", Number(item.ActionTypeCode)),
            ("action.type.name", Text(item.ActionTypeName)),
            ("context.providerKey", item.ProviderContextKey is Guid context ? GuidValue(context) : "null"),
            ("context.raw", item.RawContext?.ToString(System.Globalization.CultureInfo.InvariantCulture) ?? "null"),
            ("displayData.description", Text(item.Description)),
            ("displayData.name", Text(item.Name)),
            ("effectiveWeight.blobHex", item.EffectiveWeight.BlobHex ?? "null"),
            ("effectiveWeight.decoded", Boolean(item.EffectiveWeight.IsDecoded)),
            ("effectiveWeight.scalar", item.EffectiveWeight.ScalarValue ?? "null"),
            ("effectiveWeight.typeCode", Number(item.EffectiveWeight.TypeCode)),
            ("effectiveWeight.typeName", Text(item.EffectiveWeight.TypeName)),
            ("filterId", item.FilterId.ToString(System.Globalization.CultureInfo.InvariantCulture)),
            ("filterKey", GuidValue(item.Key)),
            ("flags", Number(item.Flags)),
            ("layerKey", GuidValue(item.LayerKey)),
            ("providerData.hex", Convert.ToHexString(item.ProviderData.ToArray()).ToLowerInvariant()),
            ("providerData.size", Number(item.ProviderData.Count)),
            ("providerKey", item.ProviderKey is Guid provider ? GuidValue(provider) : "null"),
            ("subLayerKey", GuidValue(item.SublayerKey)),
            ("weight.blobHex", item.Weight.BlobHex ?? "null"),
            ("weight.decoded", Boolean(item.Weight.IsDecoded)),
            ("weight.scalar", item.Weight.ScalarValue ?? "null"),
            ("weight.typeCode", Number(item.Weight.TypeCode)),
            ("weight.typeName", Text(item.Weight.TypeName)),
            ("condition.count", Number(item.Conditions.Count)),
        };

        FilterConditionSnapshot[] conditions = item.Conditions
            .OrderBy(condition => condition.FieldKey)
            .ThenBy(condition => condition.MatchTypeCode)
            .ThenBy(condition => condition.Value.TypeCode)
            .ThenBy(condition => condition.Value.ScalarValue, StringComparer.Ordinal)
            .ThenBy(condition => condition.Value.BlobHex, StringComparer.Ordinal)
            .ToArray();
        for (int index = 0; index < conditions.Length; index++)
        {
            FilterConditionSnapshot condition = conditions[index];
            string prefix = $"condition[{index:D4}].";
            fields.Add((prefix + "fieldKey", GuidValue(condition.FieldKey)));
            fields.Add((prefix + "matchType.code", Number(condition.MatchTypeCode)));
            fields.Add((prefix + "matchType.name", Text(condition.MatchTypeName)));
            fields.Add((prefix + "value.blobHex", condition.Value.BlobHex ?? "null"));
            fields.Add((prefix + "value.decoded", Boolean(condition.Value.IsDecoded)));
            fields.Add((prefix + "value.scalar", condition.Value.ScalarValue ?? "null"));
            fields.Add((prefix + "value.typeCode", Number(condition.Value.TypeCode)));
            fields.Add((prefix + "value.typeName", Text(condition.Value.TypeName)));
        }

        return Object("FWPM_FILTER0", item.Key, fields.ToArray());
    }

    private static WfpNativeReadbackObjectProjection Object(
        string kind,
        Guid key,
        params (string Name, string Value)[] fields) =>
        new(kind, key.ToString("D").ToLowerInvariant(), fields.Select(field => new WfpNativeObjectField(field.Name, field.Value)));

    private static string Text(string? value) => value is null
        ? "null"
        : "text:" + Convert.ToBase64String(Encoding.UTF8.GetBytes(value));

    private static string Number<T>(T value) where T : IFormattable =>
        "number:" + value.ToString(null, System.Globalization.CultureInfo.InvariantCulture);

    private static string Boolean(bool value) => value ? "true" : "false";

    private static string GuidValue(Guid value) => value.ToString("D").ToLowerInvariant();
}
