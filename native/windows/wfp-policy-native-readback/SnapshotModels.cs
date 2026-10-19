namespace WfpPolicy.NativeReadback;

public enum SnapshotIssueCode
{
    InvalidNativePointer,
    NativeCountOutOfRange,
    NullEntry,
    UnterminatedString,
    BlobTooLarge,
    BlobPointerMissing,
    UnsupportedNativeValue,
    InvalidConditionArray,
    ReferencedObjectNotIncluded,
    SecurityDescriptorNotNormalized,
    SecurityDescriptorPolicyUnverified,
    EnumerationCompletenessUnverified,
    EffectiveWeightNotNormalized,
    EnumerationLimitReached,
    ProviderContextPayloadNotNormalized,
    NativeApiFailure,
}

public sealed record SnapshotIssue(
    SnapshotIssueCode Code,
    string ObjectKind,
    string ObjectKey,
    string Detail);

public sealed record NativeValueSnapshot(
    int TypeCode,
    string? TypeName,
    string? ScalarValue,
    bool IsDecoded,
    string? BlobHex = null);

/// <summary>
/// Canonical textual evidence for a native WFP object's self-relative owner, group, and DACL.
/// The hash is SHA-256 over the UTF-8 normalized SDDL. SACL data is omitted because BFE ignores SACL ACEs.
/// </summary>
public sealed record SecurityDescriptorSnapshot(
    string Sddl,
    string Sha256,
    int BinaryLength,
    bool DaclPresent,
    bool HasNullDacl);

/// <summary>
/// Layer metadata needed to resolve a filter's null sublayer key and retain
/// the layer object's normalized security descriptor.
/// </summary>
public sealed class LayerSnapshot
{
    internal LayerSnapshot(
        Guid key,
        Guid defaultSublayerKey,
        SecurityDescriptorSnapshot? securityDescriptor,
        IEnumerable<SnapshotIssue> issues)
    {
        this.Key = key;
        this.DefaultSublayerKey = defaultSublayerKey;
        this.SecurityDescriptor = securityDescriptor;
        this.Issues = Array.AsReadOnly(issues.ToArray());
    }

    public Guid Key { get; }
    public Guid DefaultSublayerKey { get; }
    public SecurityDescriptorSnapshot? SecurityDescriptor { get; }
    public IReadOnlyList<SnapshotIssue> Issues { get; }
    public bool IsComplete => this.Issues.Count == 0;
}

/// <summary>
/// Stable condition-key values needed by consumers that interpret a bounded
/// native snapshot. The snapshot itself keeps GUIDs so unknown keys remain
/// representable instead of being silently discarded.
/// </summary>
public static class WfpNativeConditionKeys
{
    public static Guid AleAppId => Windows.Win32.PInvoke.FWPM_CONDITION_ALE_APP_ID;
}

public sealed class ProviderSnapshot
{
    internal ProviderSnapshot(
        Guid key,
        string? name,
        string? description,
        uint flags,
        string? serviceName,
        IEnumerable<byte> providerData,
        SecurityDescriptorSnapshot? securityDescriptor,
        IEnumerable<SnapshotIssue> issues)
    {
        this.Key = key;
        this.Name = name;
        this.Description = description;
        this.Flags = flags;
        this.ServiceName = serviceName;
        this.ProviderData = Array.AsReadOnly(providerData.ToArray());
        this.SecurityDescriptor = securityDescriptor;
        this.Issues = Array.AsReadOnly(issues.ToArray());
    }

    public Guid Key { get; }
    public string? Name { get; }
    public string? Description { get; }
    public uint Flags { get; }
    public string? ServiceName { get; }
    public IReadOnlyList<byte> ProviderData { get; }
    public SecurityDescriptorSnapshot? SecurityDescriptor { get; }
    public IReadOnlyList<SnapshotIssue> Issues { get; }
    public bool IsComplete => this.Issues.Count == 0;
}

public sealed class SublayerSnapshot
{
    internal SublayerSnapshot(
        Guid key,
        string? name,
        string? description,
        uint flags,
        Guid? providerKey,
        ushort weight,
        IEnumerable<byte> providerData,
        SecurityDescriptorSnapshot? securityDescriptor,
        IEnumerable<SnapshotIssue> issues)
    {
        this.Key = key;
        this.Name = name;
        this.Description = description;
        this.Flags = flags;
        this.ProviderKey = providerKey;
        this.Weight = weight;
        this.ProviderData = Array.AsReadOnly(providerData.ToArray());
        this.SecurityDescriptor = securityDescriptor;
        this.Issues = Array.AsReadOnly(issues.ToArray());
    }

    public Guid Key { get; }
    public string? Name { get; }
    public string? Description { get; }
    public uint Flags { get; }
    public Guid? ProviderKey { get; }
    public ushort Weight { get; }
    public IReadOnlyList<byte> ProviderData { get; }
    public SecurityDescriptorSnapshot? SecurityDescriptor { get; }
    public IReadOnlyList<SnapshotIssue> Issues { get; }
    public bool IsComplete => this.Issues.Count == 0;
}

public sealed class CalloutSnapshot
{
    internal CalloutSnapshot(
        Guid key,
        string? name,
        string? description,
        uint flags,
        Guid? providerKey,
        IEnumerable<byte> providerData,
        Guid applicableLayer,
        uint calloutId,
        SecurityDescriptorSnapshot? securityDescriptor,
        IEnumerable<SnapshotIssue> issues)
    {
        this.Key = key;
        this.Name = name;
        this.Description = description;
        this.Flags = flags;
        this.ProviderKey = providerKey;
        this.ProviderData = Array.AsReadOnly(providerData.ToArray());
        this.ApplicableLayer = applicableLayer;
        this.CalloutId = calloutId;
        this.SecurityDescriptor = securityDescriptor;
        this.Issues = Array.AsReadOnly(issues.ToArray());
    }

    public Guid Key { get; }
    public string? Name { get; }
    public string? Description { get; }
    public uint Flags { get; }
    public Guid? ProviderKey { get; }
    public IReadOnlyList<byte> ProviderData { get; }
    public Guid ApplicableLayer { get; }
    public uint CalloutId { get; }
    public SecurityDescriptorSnapshot? SecurityDescriptor { get; }
    public IReadOnlyList<SnapshotIssue> Issues { get; }
    public bool IsComplete => this.Issues.Count == 0;
}

public sealed record ClassifyOptionSnapshot(
    int TypeCode,
    string? TypeName,
    NativeValueSnapshot Value);

public sealed class ProviderContextSnapshot
{
    internal ProviderContextSnapshot(
        Guid key,
        string? name,
        string? description,
        uint flags,
        Guid? providerKey,
        IEnumerable<byte> providerData,
        int typeCode,
        string? typeName,
        ulong providerContextId,
        string? generalDataHex,
        IEnumerable<ClassifyOptionSnapshot> classifyOptions,
        SecurityDescriptorSnapshot? securityDescriptor,
        IEnumerable<SnapshotIssue> issues)
    {
        this.Key = key;
        this.Name = name;
        this.Description = description;
        this.Flags = flags;
        this.ProviderKey = providerKey;
        this.ProviderData = Array.AsReadOnly(providerData.ToArray());
        this.TypeCode = typeCode;
        this.TypeName = typeName;
        this.ProviderContextId = providerContextId;
        this.GeneralDataHex = generalDataHex;
        this.ClassifyOptions = Array.AsReadOnly(classifyOptions.ToArray());
        this.SecurityDescriptor = securityDescriptor;
        this.Issues = Array.AsReadOnly(issues.ToArray());
    }

    public Guid Key { get; }
    public string? Name { get; }
    public string? Description { get; }
    public uint Flags { get; }
    public Guid? ProviderKey { get; }
    public IReadOnlyList<byte> ProviderData { get; }
    public int TypeCode { get; }
    public string? TypeName { get; }
    public ulong ProviderContextId { get; }
    public string? GeneralDataHex { get; }
    public IReadOnlyList<ClassifyOptionSnapshot> ClassifyOptions { get; }
    public SecurityDescriptorSnapshot? SecurityDescriptor { get; }
    public IReadOnlyList<SnapshotIssue> Issues { get; }
    public bool IsComplete => this.Issues.Count == 0;
}

public sealed record FilterConditionSnapshot(
    Guid FieldKey,
    int MatchTypeCode,
    string? MatchTypeName,
    NativeValueSnapshot Value);

public sealed class FilterSnapshot
{
    internal FilterSnapshot(
        Guid key,
        string? name,
        string? description,
        uint flags,
        Guid? providerKey,
        IEnumerable<byte> providerData,
        Guid layerKey,
        Guid sublayerKey,
        NativeValueSnapshot weight,
        IEnumerable<FilterConditionSnapshot> conditions,
        int actionTypeCode,
        string? actionTypeName,
        Guid? calloutKey,
        ulong? rawContext,
        Guid? providerContextKey,
        ulong filterId,
        NativeValueSnapshot effectiveWeight,
        SecurityDescriptorSnapshot? securityDescriptor,
        IEnumerable<SnapshotIssue> issues)
    {
        this.Key = key;
        this.Name = name;
        this.Description = description;
        this.Flags = flags;
        this.ProviderKey = providerKey;
        this.ProviderData = Array.AsReadOnly(providerData.ToArray());
        this.LayerKey = layerKey;
        this.SublayerKey = sublayerKey;
        this.Weight = weight;
        this.Conditions = Array.AsReadOnly(conditions.ToArray());
        this.ActionTypeCode = actionTypeCode;
        this.ActionTypeName = actionTypeName;
        this.CalloutKey = calloutKey;
        this.RawContext = rawContext;
        this.ProviderContextKey = providerContextKey;
        this.FilterId = filterId;
        this.EffectiveWeight = effectiveWeight;
        this.SecurityDescriptor = securityDescriptor;
        this.Issues = Array.AsReadOnly(issues.ToArray());
    }

    public Guid Key { get; }
    public string? Name { get; }
    public string? Description { get; }
    public uint Flags { get; }
    public Guid? ProviderKey { get; }
    public IReadOnlyList<byte> ProviderData { get; }
    public Guid LayerKey { get; }
    public Guid SublayerKey { get; }
    public NativeValueSnapshot Weight { get; }
    public IReadOnlyList<FilterConditionSnapshot> Conditions { get; }
    public int ActionTypeCode { get; }
    public string? ActionTypeName { get; }
    public Guid? CalloutKey { get; }
    public ulong? RawContext { get; }
    public Guid? ProviderContextKey { get; }
    public ulong FilterId { get; }
    public NativeValueSnapshot EffectiveWeight { get; }
    public SecurityDescriptorSnapshot? SecurityDescriptor { get; }
    public IReadOnlyList<SnapshotIssue> Issues { get; }
    public bool IsComplete => this.Issues.Count == 0;
}

public sealed class WfpSnapshot
{
    internal WfpSnapshot(
        DateTimeOffset capturedAtUtc,
        IEnumerable<ProviderSnapshot> providers,
        IEnumerable<SublayerSnapshot> sublayers,
        IEnumerable<FilterSnapshot> filters,
        IEnumerable<SnapshotIssue> issues,
        IEnumerable<CalloutSnapshot>? callouts = null,
        IEnumerable<ProviderContextSnapshot>? providerContexts = null,
        IEnumerable<LayerSnapshot>? layers = null)
    {
        this.CapturedAtUtc = capturedAtUtc;
        this.Providers = Array.AsReadOnly(providers.ToArray());
        this.Sublayers = Array.AsReadOnly(sublayers.ToArray());
        this.Filters = Array.AsReadOnly(filters.ToArray());
        this.Callouts = Array.AsReadOnly((callouts ?? []).ToArray());
        this.ProviderContexts = Array.AsReadOnly((providerContexts ?? []).ToArray());
        this.Layers = Array.AsReadOnly((layers ?? []).ToArray());
        this.Issues = Array.AsReadOnly(issues.ToArray());
    }

    public DateTimeOffset CapturedAtUtc { get; }
    public IReadOnlyList<ProviderSnapshot> Providers { get; }
    public IReadOnlyList<SublayerSnapshot> Sublayers { get; }
    public IReadOnlyList<FilterSnapshot> Filters { get; }
    public IReadOnlyList<CalloutSnapshot> Callouts { get; }
    public IReadOnlyList<ProviderContextSnapshot> ProviderContexts { get; }
    public IReadOnlyList<LayerSnapshot> Layers { get; }
    public IReadOnlyList<SnapshotIssue> Issues { get; }
    public bool IsComplete => this.Issues.Count == 0
        && this.Providers.All(item => item.IsComplete)
        && this.Sublayers.All(item => item.IsComplete)
        && this.Layers.All(item => item.IsComplete)
        && this.Filters.All(item => item.IsComplete)
        && this.Callouts.All(item => item.IsComplete)
        && this.ProviderContexts.All(item => item.IsComplete);
}
