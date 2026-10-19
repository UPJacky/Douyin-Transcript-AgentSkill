using Windows.Win32.NetworkManagement.WindowsFilteringPlatform;

namespace WfpPolicy.NativeReadback;

internal static unsafe class NativeObjectDecoder
{
    private const uint FwpOptionValueAllowMulticastState = 0;
    private const uint FwpOptionValueDenyMulticastState = 1;
    private const uint FwpOptionValueAllowGlobalMulticastState = 2;
    private const uint FwpOptionValueDisableLooseSource = 0;
    private const uint FwpOptionValueEnableLooseSource = 1;

    internal const int MaxStringCharacters = 4096;
    internal const uint MaxBlobBytes = 1024 * 1024;
    internal const uint MaxConditionsPerFilter = 256;
    internal const uint MaxClassifyOptions = 64;

    internal static LayerSnapshot DecodeLayer(FWPM_LAYER0* native, SecurityDescriptorSnapshot? securityDescriptor = null)
    {
        var issues = new List<SnapshotIssue>();
        if (native is null)
        {
            issues.Add(Issue(SnapshotIssueCode.InvalidNativePointer, "layer", Guid.Empty, "Layer pointer is null."));
            return new LayerSnapshot(Guid.Empty, Guid.Empty, securityDescriptor, issues.AsReadOnly());
        }

        var key = native->layerKey;
        if (key == Guid.Empty)
        {
            issues.Add(Issue(SnapshotIssueCode.UnsupportedNativeValue, "layer", key, "Layer key is empty."));
        }
        AddSecurityDescriptorIssue(issues, "layer", key, securityDescriptor);
        return new LayerSnapshot(key, native->defaultSubLayerKey, securityDescriptor, issues.AsReadOnly());
    }

    internal static ProviderSnapshot DecodeProvider(FWPM_PROVIDER0* native, SecurityDescriptorSnapshot? securityDescriptor = null)
    {
        var issues = new List<SnapshotIssue>();
        if (native is null)
        {
            issues.Add(Issue(SnapshotIssueCode.InvalidNativePointer, "provider", Guid.Empty, "Provider pointer is null."));
            return new ProviderSnapshot(Guid.Empty, null, null, 0, null, Array.AsReadOnly(Array.Empty<byte>()), securityDescriptor, issues.AsReadOnly());
        }

        var name = ReadString(native->displayData.name.Value, "provider", native->providerKey, "name", issues);
        var description = ReadString(native->displayData.description.Value, "provider", native->providerKey, "description", issues);
        var serviceName = ReadString(native->serviceName.Value, "provider", native->providerKey, "serviceName", issues);
        var providerData = ReadBlob(&native->providerData, "provider", native->providerKey, issues);
        AddSecurityDescriptorIssue(issues, "provider", native->providerKey, securityDescriptor);
        return new ProviderSnapshot(native->providerKey, name, description, native->flags, serviceName, Array.AsReadOnly(providerData), securityDescriptor, issues.AsReadOnly());
    }

    internal static SublayerSnapshot DecodeSublayer(FWPM_SUBLAYER0* native, SecurityDescriptorSnapshot? securityDescriptor = null)
    {
        var issues = new List<SnapshotIssue>();
        if (native is null)
        {
            issues.Add(Issue(SnapshotIssueCode.InvalidNativePointer, "sublayer", Guid.Empty, "Sublayer pointer is null."));
            return new SublayerSnapshot(Guid.Empty, null, null, 0, null, 0, Array.AsReadOnly(Array.Empty<byte>()), securityDescriptor, issues.AsReadOnly());
        }

        Guid? providerKey = native->providerKey is null ? null : *native->providerKey;
        var name = ReadString(native->displayData.name.Value, "sublayer", native->subLayerKey, "name", issues);
        var description = ReadString(native->displayData.description.Value, "sublayer", native->subLayerKey, "description", issues);
        var providerData = ReadBlob(&native->providerData, "sublayer", native->subLayerKey, issues);
        AddSecurityDescriptorIssue(issues, "sublayer", native->subLayerKey, securityDescriptor);
        return new SublayerSnapshot(native->subLayerKey, name, description, native->flags, providerKey, native->weight, Array.AsReadOnly(providerData), securityDescriptor, issues.AsReadOnly());
    }

    internal static CalloutSnapshot DecodeCallout(FWPM_CALLOUT0* native, SecurityDescriptorSnapshot? securityDescriptor = null)
    {
        var issues = new List<SnapshotIssue>();
        if (native is null)
        {
            issues.Add(Issue(SnapshotIssueCode.InvalidNativePointer, "callout", Guid.Empty, "Callout pointer is null."));
            return new CalloutSnapshot(Guid.Empty, null, null, 0, null, [], Guid.Empty, 0, securityDescriptor, issues.AsReadOnly());
        }

        var key = native->calloutKey;
        Guid? providerKey = native->providerKey is null ? null : *native->providerKey;
        var name = ReadString(native->displayData.name.Value, "callout", key, "name", issues);
        var description = ReadString(native->displayData.description.Value, "callout", key, "description", issues);
        var providerData = ReadBlob(&native->providerData, "callout", key, issues);
        if (key == Guid.Empty)
        {
            issues.Add(Issue(SnapshotIssueCode.UnsupportedNativeValue, "callout", key, "Callout key is empty."));
        }
        AddSecurityDescriptorIssue(issues, "callout", key, securityDescriptor);

        return new CalloutSnapshot(key, name, description, native->flags, providerKey, providerData,
            native->applicableLayer, native->calloutId, securityDescriptor, issues.AsReadOnly());
    }

    internal static ProviderContextSnapshot DecodeProviderContext(FWPM_PROVIDER_CONTEXT0* native, SecurityDescriptorSnapshot? securityDescriptor = null)
    {
        var issues = new List<SnapshotIssue>();
        if (native is null)
        {
            issues.Add(Issue(SnapshotIssueCode.InvalidNativePointer, "provider-context", Guid.Empty, "Provider context pointer is null."));
            return new ProviderContextSnapshot(Guid.Empty, null, null, 0, null, [], 0, null, 0, null, [], securityDescriptor, issues.AsReadOnly());
        }

        Guid? providerKey = native->providerKey is null ? null : *native->providerKey;
        var key = native->providerContextKey;
        var name = ReadString(native->displayData.name.Value, "provider-context", key, "name", issues);
        var description = ReadString(native->displayData.description.Value, "provider-context", key, "description", issues);
        var providerData = ReadBlob(&native->providerData, "provider-context", key, issues);
        const uint knownFlags = 0x00000001; // FWPM_PROVIDER_CONTEXT_FLAG_PERSISTENT.
        if (((uint)native->flags & ~knownFlags) != 0)
        {
            issues.Add(Issue(SnapshotIssueCode.UnsupportedNativeValue, "provider-context", key, "Provider context contains unsupported flag bits."));
        }
        if (key == Guid.Empty)
        {
            issues.Add(Issue(SnapshotIssueCode.UnsupportedNativeValue, "provider-context", key, "Provider context key is empty."));
        }

        string? generalDataHex = null;
        var classifyOptions = new List<ClassifyOptionSnapshot>();
        switch (native->type)
        {
            case FWPM_PROVIDER_CONTEXT_TYPE.FWPM_GENERAL_CONTEXT:
                if (native->dataBuffer is null)
                {
                    issues.Add(Issue(SnapshotIssueCode.ProviderContextPayloadNotNormalized, "provider-context", key, "General provider context has a null dataBuffer."));
                }
                else
                {
                    var payload = ReadBlob(native->dataBuffer, "provider-context", key, issues);
                    generalDataHex = Convert.ToHexString(payload).ToLowerInvariant();
                }
                break;
            case FWPM_PROVIDER_CONTEXT_TYPE.FWPM_CLASSIFY_OPTIONS_CONTEXT:
                DecodeClassifyOptions(native->classifyOptions, key, classifyOptions, issues);
                break;
            default:
                issues.Add(Issue(
                    SnapshotIssueCode.ProviderContextPayloadNotNormalized,
                    "provider-context",
                    key,
                    $"Provider context payload type {(uint)native->type} is not normalized by the FWPM_PROVIDER_CONTEXT0 reader."));
                break;
        }

        AddSecurityDescriptorIssue(issues, "provider-context", key, securityDescriptor);
        return new ProviderContextSnapshot(
            key,
            name,
            description,
            (uint)native->flags,
            providerKey,
            providerData,
            (int)native->type,
            native->type.ToString(),
            native->providerContextId,
            generalDataHex,
            classifyOptions,
            securityDescriptor,
            issues.AsReadOnly());
    }

    internal static FilterSnapshot DecodeFilter(FWPM_FILTER0* native, SecurityDescriptorSnapshot? securityDescriptor = null)
    {
        var issues = new List<SnapshotIssue>();
        if (native is null)
        {
            issues.Add(Issue(SnapshotIssueCode.InvalidNativePointer, "filter", Guid.Empty, "Filter pointer is null."));
            return new FilterSnapshot(Guid.Empty, null, null, 0, null, Array.AsReadOnly(Array.Empty<byte>()), Guid.Empty, Guid.Empty,
                UnsupportedValue(0, null), [], 0, null, null, null, null, 0, UnsupportedValue(0, null), securityDescriptor, issues.AsReadOnly());
        }

        Guid? providerKey = native->providerKey is null ? null : *native->providerKey;
        var key = native->filterKey;
        var name = ReadString(native->displayData.name.Value, "filter", key, "name", issues);
        var description = ReadString(native->displayData.description.Value, "filter", key, "description", issues);
        var providerData = ReadBlob(&native->providerData, "filter", key, issues);

        var conditions = new List<FilterConditionSnapshot>();
        if (native->numFilterConditions > MaxConditionsPerFilter)
        {
            issues.Add(Issue(SnapshotIssueCode.NativeCountOutOfRange, "filter", key, $"Condition count exceeds {MaxConditionsPerFilter}."));
        }
        else if (native->numFilterConditions != 0 && native->filterCondition is null)
        {
            issues.Add(Issue(SnapshotIssueCode.InvalidConditionArray, "filter", key, "Condition count is nonzero but the condition pointer is null."));
        }
        else
        {
            for (uint index = 0; index < native->numFilterConditions; index++)
            {
                var condition = native->filterCondition[index];
                var value = DecodeValue(condition.conditionValue.type, condition.conditionValue.Anonymous, "filter", key, $"condition[{index}]", issues);
                conditions.Add(new FilterConditionSnapshot(condition.fieldKey, (int)condition.matchType, condition.matchType.ToString(), value));
            }
        }

        Guid? calloutKey = null;
        if (native->action.type is FWP_ACTION_TYPE.FWP_ACTION_CALLOUT_TERMINATING
            or FWP_ACTION_TYPE.FWP_ACTION_CALLOUT_INSPECTION
            or FWP_ACTION_TYPE.FWP_ACTION_CALLOUT_UNKNOWN)
        {
            calloutKey = native->action.calloutKey;
            if (calloutKey == Guid.Empty)
            {
                issues.Add(Issue(SnapshotIssueCode.ReferencedObjectNotIncluded, "filter", key, "Callout action contains an empty referenced key."));
            }
        }

        var hasProviderContext = (native->flags & FWPM_FILTER_FLAGS.FWPM_FILTER_FLAG_HAS_PROVIDER_CONTEXT) != 0;
        ulong? rawContext = hasProviderContext ? null : native->rawContext;
        Guid? providerContextKey = hasProviderContext ? native->providerContextKey : null;
        if (hasProviderContext)
        {
            if (native->providerContextKey == Guid.Empty)
            {
                issues.Add(Issue(SnapshotIssueCode.ReferencedObjectNotIncluded, "filter", key, "Filter declares a provider context but its key is empty."));
            }
            if (native->action.type is not (FWP_ACTION_TYPE.FWP_ACTION_CALLOUT_TERMINATING or FWP_ACTION_TYPE.FWP_ACTION_CALLOUT_INSPECTION or FWP_ACTION_TYPE.FWP_ACTION_CALLOUT_UNKNOWN))
            {
                issues.Add(Issue(SnapshotIssueCode.UnsupportedNativeValue, "filter", key, "HAS_PROVIDER_CONTEXT is set for an action type that cannot reference a provider context."));
            }
        }
        else if (native->providerContextKey != Guid.Empty)
        {
            issues.Add(Issue(SnapshotIssueCode.UnsupportedNativeValue, "filter", key, "Filter has a nonempty provider-context key without HAS_PROVIDER_CONTEXT."));
        }
        if (native->reserved is not null)
        {
            issues.Add(Issue(SnapshotIssueCode.UnsupportedNativeValue, "filter", key, "Reserved filter pointer is non-null."));
        }

        var weight = DecodeValue(native->weight.type, native->weight.Anonymous, "filter", key, "weight", issues);
        var effectiveWeight = DecodeValue(native->effectiveWeight.type, native->effectiveWeight.Anonymous, "filter", key, "effectiveWeight", issues);
        if (native->effectiveWeight.type != FWP_DATA_TYPE.FWP_UINT64 || !effectiveWeight.IsDecoded)
        {
            issues.Add(Issue(SnapshotIssueCode.EffectiveWeightNotNormalized, "filter", key, "BFE effectiveWeight must be a valid FWP_UINT64 value before it can be used as normalized readback evidence."));
        }
        AddSecurityDescriptorIssue(issues, "filter", key, securityDescriptor);

        return new FilterSnapshot(key, name, description, (uint)native->flags, providerKey, Array.AsReadOnly(providerData),
            native->layerKey, native->subLayerKey, weight, conditions.AsReadOnly(), (int)native->action.type,
            native->action.type.ToString(), calloutKey, rawContext, providerContextKey, native->filterId, effectiveWeight, securityDescriptor, issues.AsReadOnly());
    }

    internal static IReadOnlyList<SnapshotIssue> SecurityDescriptorNotObserved(string kind, Guid key) =>
        Array.AsReadOnly([Issue(SnapshotIssueCode.SecurityDescriptorNotNormalized, kind, key, "Object security descriptor was not fetched and canonically normalized.")]);

    private static void AddSecurityDescriptorIssue(List<SnapshotIssue> issues, string kind, Guid key, SecurityDescriptorSnapshot? securityDescriptor)
    {
        if (securityDescriptor is null)
        {
            issues.Add(Issue(SnapshotIssueCode.SecurityDescriptorNotNormalized, kind, key, "Object security descriptor was not fetched and canonically normalized."));
            return;
        }

        issues.Add(Issue(SnapshotIssueCode.SecurityDescriptorPolicyUnverified, kind, key, "The descriptor is normalized, but it has not been compared with the expected service policy."));
    }

    internal static NativeValueSnapshot DecodeValue(
        FWP_DATA_TYPE type,
        FWP_CONDITION_VALUE0._Anonymous_e__Union value,
        string kind,
        Guid key,
        string field,
        List<SnapshotIssue> issues)
    {
        if (type == FWP_DATA_TYPE.FWP_BYTE_BLOB_TYPE)
        {
            int issueCount = issues.Count;
            byte[] bytes = ReadBlob(value.byteBlob, kind, key, issues);
            return new NativeValueSnapshot(
                (int)type,
                type.ToString(),
                ScalarValue: null,
                IsDecoded: issues.Count == issueCount,
                BlobHex: Convert.ToHexString(bytes).ToLowerInvariant());
        }

        string? scalar = type switch
        {
            FWP_DATA_TYPE.FWP_EMPTY => "empty",
            FWP_DATA_TYPE.FWP_UINT8 => value.uint8.ToString(System.Globalization.CultureInfo.InvariantCulture),
            FWP_DATA_TYPE.FWP_UINT16 => value.uint16.ToString(System.Globalization.CultureInfo.InvariantCulture),
            FWP_DATA_TYPE.FWP_UINT32 => value.uint32.ToString(System.Globalization.CultureInfo.InvariantCulture),
            FWP_DATA_TYPE.FWP_INT8 => value.int8.ToString(System.Globalization.CultureInfo.InvariantCulture),
            FWP_DATA_TYPE.FWP_INT16 => value.int16.ToString(System.Globalization.CultureInfo.InvariantCulture),
            FWP_DATA_TYPE.FWP_INT32 => value.int32.ToString(System.Globalization.CultureInfo.InvariantCulture),
            _ => null,
        };

        if (scalar is not null)
        {
            return new NativeValueSnapshot((int)type, type.ToString(), scalar, true);
        }

        if (type == FWP_DATA_TYPE.FWP_UINT64 && value.uint64 is not null)
        {
            return new NativeValueSnapshot((int)type, type.ToString(), (*value.uint64).ToString(System.Globalization.CultureInfo.InvariantCulture), true);
        }
        if (type == FWP_DATA_TYPE.FWP_INT64 && value.int64 is not null)
        {
            return new NativeValueSnapshot((int)type, type.ToString(), (*value.int64).ToString(System.Globalization.CultureInfo.InvariantCulture), true);
        }

        issues.Add(Issue(SnapshotIssueCode.UnsupportedNativeValue, kind, key, $"{field} has unsupported or invalid native value type {(int)type}."));
        return UnsupportedValue((int)type, type.ToString());
    }

    private static void DecodeClassifyOptions(
        FWPM_CLASSIFY_OPTIONS0* native,
        Guid key,
        List<ClassifyOptionSnapshot> output,
        List<SnapshotIssue> issues)
    {
        if (native is null)
        {
            issues.Add(Issue(SnapshotIssueCode.ProviderContextPayloadNotNormalized, "provider-context", key, "Classify-options provider context has a null options structure."));
            return;
        }
        if (native->numOptions > MaxClassifyOptions)
        {
            issues.Add(Issue(SnapshotIssueCode.NativeCountOutOfRange, "provider-context", key, $"Classify option count exceeds {MaxClassifyOptions}."));
            return;
        }
        if (native->numOptions != 0 && native->options is null)
        {
            issues.Add(Issue(SnapshotIssueCode.InvalidNativePointer, "provider-context", key, "Classify option count is nonzero but the option array pointer is null."));
            return;
        }

        var seenTypes = new HashSet<FWP_CLASSIFY_OPTION_TYPE>();
        for (uint index = 0; index < native->numOptions; index++)
        {
            var option = native->options[index];
            bool knownOption = Enum.IsDefined(typeof(FWP_CLASSIFY_OPTION_TYPE), option.type)
                && option.type != FWP_CLASSIFY_OPTION_TYPE.FWP_CLASSIFY_OPTION_MAX;
            bool supportedLifetime = option.type is FWP_CLASSIFY_OPTION_TYPE.FWP_CLASSIFY_OPTION_UNICAST_LIFETIME
                or FWP_CLASSIFY_OPTION_TYPE.FWP_CLASSIFY_OPTION_MCAST_BCAST_LIFETIME;
            bool supportedScalarOption = option.type is FWP_CLASSIFY_OPTION_TYPE.FWP_CLASSIFY_OPTION_MULTICAST_STATE
                or FWP_CLASSIFY_OPTION_TYPE.FWP_CLASSIFY_OPTION_LOOSE_SOURCE_MAPPING;
            if (!knownOption)
            {
                issues.Add(Issue(SnapshotIssueCode.UnsupportedNativeValue, "provider-context", key, $"Classify option {index} has unknown type {(uint)option.type}."));
            }
            else if (!supportedLifetime && !supportedScalarOption)
            {
                issues.Add(Issue(SnapshotIssueCode.UnsupportedNativeValue, "provider-context", key, $"Classify option type {(uint)option.type} is not normalized by the reader."));
            }
            if ((supportedLifetime || supportedScalarOption) && option.value.type != FWP_DATA_TYPE.FWP_UINT32)
            {
                issues.Add(Issue(SnapshotIssueCode.UnsupportedNativeValue, "provider-context", key, $"Classify option {index} must use FWP_UINT32."));
            }
            else if (supportedScalarOption && !IsValidClassifyOptionScalar(option.type, option.value.uint32))
            {
                issues.Add(Issue(SnapshotIssueCode.UnsupportedNativeValue, "provider-context", key, $"Classify option {index} has a value outside its documented enum."));
            }
            if (!seenTypes.Add(option.type))
            {
                issues.Add(Issue(SnapshotIssueCode.UnsupportedNativeValue, "provider-context", key, $"Classify option type {(uint)option.type} is duplicated."));
            }
            var value = DecodeValue(option.value.type, option.value.Anonymous, "provider-context", key, $"classifyOptions[{index}].value", issues);
            output.Add(new ClassifyOptionSnapshot((int)option.type, option.type.ToString(), value));
        }
    }

    private static bool IsValidClassifyOptionScalar(FWP_CLASSIFY_OPTION_TYPE type, uint value) => type switch
    {
        // These values are the FWP_OPTION_VALUE_* constants documented for FWPM_CLASSIFY_OPTION0.
        FWP_CLASSIFY_OPTION_TYPE.FWP_CLASSIFY_OPTION_MULTICAST_STATE => value is FwpOptionValueAllowMulticastState
            or FwpOptionValueDenyMulticastState or FwpOptionValueAllowGlobalMulticastState,
        FWP_CLASSIFY_OPTION_TYPE.FWP_CLASSIFY_OPTION_LOOSE_SOURCE_MAPPING => value is FwpOptionValueDisableLooseSource
            or FwpOptionValueEnableLooseSource,
        _ => false,
    };

    internal static NativeValueSnapshot DecodeValue(
        FWP_DATA_TYPE type,
        FWP_VALUE0._Anonymous_e__Union value,
        string kind,
        Guid key,
        string field,
        List<SnapshotIssue> issues)
    {
        if (type == FWP_DATA_TYPE.FWP_BYTE_BLOB_TYPE)
        {
            int issueCount = issues.Count;
            byte[] bytes = ReadBlob(value.byteBlob, kind, key, issues);
            return new NativeValueSnapshot(
                (int)type,
                type.ToString(),
                ScalarValue: null,
                IsDecoded: issues.Count == issueCount,
                BlobHex: Convert.ToHexString(bytes).ToLowerInvariant());
        }

        string? scalar = type switch
        {
            FWP_DATA_TYPE.FWP_EMPTY => "empty",
            FWP_DATA_TYPE.FWP_UINT8 => value.uint8.ToString(System.Globalization.CultureInfo.InvariantCulture),
            FWP_DATA_TYPE.FWP_UINT16 => value.uint16.ToString(System.Globalization.CultureInfo.InvariantCulture),
            FWP_DATA_TYPE.FWP_UINT32 => value.uint32.ToString(System.Globalization.CultureInfo.InvariantCulture),
            FWP_DATA_TYPE.FWP_INT8 => value.int8.ToString(System.Globalization.CultureInfo.InvariantCulture),
            FWP_DATA_TYPE.FWP_INT16 => value.int16.ToString(System.Globalization.CultureInfo.InvariantCulture),
            FWP_DATA_TYPE.FWP_INT32 => value.int32.ToString(System.Globalization.CultureInfo.InvariantCulture),
            _ => null,
        };

        if (scalar is not null)
        {
            return new NativeValueSnapshot((int)type, type.ToString(), scalar, true);
        }
        if (type == FWP_DATA_TYPE.FWP_UINT64 && value.uint64 is not null)
        {
            return new NativeValueSnapshot((int)type, type.ToString(), (*value.uint64).ToString(System.Globalization.CultureInfo.InvariantCulture), true);
        }
        if (type == FWP_DATA_TYPE.FWP_INT64 && value.int64 is not null)
        {
            return new NativeValueSnapshot((int)type, type.ToString(), (*value.int64).ToString(System.Globalization.CultureInfo.InvariantCulture), true);
        }

        issues.Add(Issue(SnapshotIssueCode.UnsupportedNativeValue, kind, key, $"{field} has unsupported or invalid native value type {(int)type}."));
        return UnsupportedValue((int)type, type.ToString());
    }

    private static string? ReadString(char* value, string kind, Guid key, string field, List<SnapshotIssue> issues)
    {
        if (value is null)
        {
            return null;
        }

        var length = 0;
        while (length < MaxStringCharacters && value[length] != '\0')
        {
            length++;
        }
        if (length == MaxStringCharacters)
        {
            issues.Add(Issue(SnapshotIssueCode.UnterminatedString, kind, key, $"{field} did not terminate within {MaxStringCharacters} UTF-16 characters."));
            return null;
        }
        return new string(value, 0, length);
    }

    private static byte[] ReadBlob(FWP_BYTE_BLOB* blob, string kind, Guid key, List<SnapshotIssue> issues)
    {
        if (blob is null)
        {
            issues.Add(Issue(SnapshotIssueCode.InvalidNativePointer, kind, key, "Provider data blob pointer is null."));
            return [];
        }
        if (blob->size > MaxBlobBytes)
        {
            issues.Add(Issue(SnapshotIssueCode.BlobTooLarge, kind, key, $"Provider data exceeds {MaxBlobBytes} bytes."));
            return [];
        }
        if (blob->size != 0 && blob->data is null)
        {
            issues.Add(Issue(SnapshotIssueCode.BlobPointerMissing, kind, key, "Provider data has nonzero size and a null data pointer."));
            return [];
        }
        return blob->size == 0 ? [] : new ReadOnlySpan<byte>(blob->data, checked((int)blob->size)).ToArray();
    }

    private static SnapshotIssue Issue(SnapshotIssueCode code, string kind, Guid key, string detail) =>
        new(code, kind, key == Guid.Empty ? "" : key.ToString("D"), detail);

    private static NativeValueSnapshot UnsupportedValue(int type, string? name) => new(type, name, null, false);
}
