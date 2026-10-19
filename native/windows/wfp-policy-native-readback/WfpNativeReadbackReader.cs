using System.Runtime.InteropServices;
using Windows.Win32;
using Windows.Win32.Security;
using Windows.Win32.NetworkManagement.WindowsFilteringPlatform;

namespace WfpPolicy.NativeReadback;

/// <summary>
/// Reads a bounded BFE snapshot. This assembly contains no WFP add/delete bindings and is not connected to policy activation.
/// The returned snapshot remains incomplete until object ACLs and referenced-object coverage are resolved.
/// </summary>
public sealed unsafe class WfpNativeReadbackReader
{
    private readonly IReadOnlyWfpApi api;

    public WfpNativeReadbackReader() : this(new WindowsWfpApi())
    {
    }

    internal WfpNativeReadbackReader(IReadOnlyWfpApi api) => this.api = api;

    public WfpSnapshot ReadSnapshot()
    {
        var providers = new List<ProviderSnapshot>();
        var sublayers = new List<SublayerSnapshot>();
        var layers = new List<LayerSnapshot>();
        var filters = new List<FilterSnapshot>();
        var callouts = new List<CalloutSnapshot>();
        var providerContexts = new List<ProviderContextSnapshot>();
        var issues = new List<SnapshotIssue>();
        SafeHandle? engine = null;
        var transactionOpen = false;

        try
        {
            Check(this.api.OpenEngine(out engine), "FwpmEngineOpen0");
            if (engine is null || engine.IsInvalid)
            {
                throw new WfpReadbackException("FwpmEngineOpen0 returned success without a valid engine handle.");
            }

            Check(this.api.BeginReadTransaction(engine), "FwpmTransactionBegin0(read-only)");
            transactionOpen = true;

            this.ReadProviders(engine, providers, issues);
            this.ReadSublayers(engine, sublayers, issues);
            this.ReadLayers(engine, layers, issues);
            this.ReadCallouts(engine, callouts, issues);
            this.ReadProviderContexts(engine, providerContexts, issues);
            this.ReadFilters(engine, filters, issues);
            VerifyCalloutReferences(filters, callouts, issues);
            VerifyProviderContextReferences(filters, providerContexts, issues);
            VerifyLayerAndSublayerReferences(filters, layers, sublayers, issues);
            VerifyProviderReferences(providers, sublayers, filters, callouts, providerContexts, issues);

            Check(this.api.CommitReadTransaction(engine), "FwpmTransactionCommit0(read-only)");
            transactionOpen = false;
        }
        catch
        {
            if (transactionOpen && engine is not null && !engine.IsInvalid)
            {
                try
                {
                    _ = this.api.AbortReadTransaction(engine);
                }
                catch
                {
                    // Preserve the operation failure; closing the engine also aborts any open transaction.
                }
            }
            throw;
        }
        finally
        {
            engine?.Dispose();
        }

        issues.Add(new SnapshotIssue(
            SnapshotIssueCode.EnumerationCompletenessUnverified,
            "snapshot",
            "",
            "The reader cannot prove that the service identity can enumerate every object hidden by object-level read ACLs."));

        return new WfpSnapshot(
            DateTimeOffset.UtcNow,
            Array.AsReadOnly(providers.ToArray()),
            Array.AsReadOnly(sublayers.ToArray()),
            Array.AsReadOnly(filters.ToArray()),
            Array.AsReadOnly(issues.ToArray()),
            Array.AsReadOnly(callouts.ToArray()),
            Array.AsReadOnly(providerContexts.ToArray()),
            Array.AsReadOnly(layers.ToArray()));
    }

    private void ReadProviders(SafeHandle engine, List<ProviderSnapshot> output, List<SnapshotIssue> issues)
    {
        var createResult = this.api.CreateProviderEnumHandle(engine, out var enumHandle);
        if (createResult != 0)
        {
            if (enumHandle is not null && !enumHandle.IsInvalid)
            {
                if (this.api.DestroyProviderEnumHandle(engine, enumHandle) == 0)
                {
                    enumHandle.SetHandleAsInvalid();
                }
                enumHandle.Dispose();
            }
            Check(createResult, "FwpmProviderCreateEnumHandle0");
        }
        if (enumHandle is null || enumHandle.IsInvalid)
        {
            enumHandle?.Dispose();
            throw new WfpReadbackException("FwpmProviderCreateEnumHandle0 returned success without a valid enumeration handle.");
        }
        try
        {
            var done = false;
            while (!done)
            {
                var enumResult = this.api.EnumerateProviders(engine, enumHandle, WfpReadbackLimits.PageSize, out var entries, out var count);
                try
                {
                    Check(enumResult, "FwpmProviderEnum0");
                    if (!ValidateBatch(entries, count, output.Count, "provider", issues, out done))
                    {
                        break;
                    }
                    for (uint i = 0; i < count; i++)
                    {
                        var native = entries[i];
                        if (native is null)
                        {
                            issues.Add(new SnapshotIssue(SnapshotIssueCode.NullEntry, "provider", "", $"Provider batch entry {i} is null."));
                            continue;
                        }
                        var descriptor = this.ReadSecurityDescriptor(engine, "provider", native->providerKey, issues);
                        output.Add(NativeObjectDecoder.DecodeProvider(native, descriptor));
                    }
                }
                finally
                {
                    void* allocation = entries;
                    this.api.FreeMemory(&allocation);
                }
            }
        }
        finally
        {
            try
            {
                var result = this.api.DestroyProviderEnumHandle(engine, enumHandle);
                if (result != 0)
                {
                    issues.Add(ApiIssue("FwpmProviderDestroyEnumHandle0", result));
                }
                else
                {
                    enumHandle.SetHandleAsInvalid();
                }
            }
            finally
            {
                enumHandle.Dispose();
            }
        }
    }

    private void ReadSublayers(SafeHandle engine, List<SublayerSnapshot> output, List<SnapshotIssue> issues)
    {
        var createResult = this.api.CreateSublayerEnumHandle(engine, out var enumHandle);
        if (createResult != 0)
        {
            if (enumHandle is not null && !enumHandle.IsInvalid)
            {
                if (this.api.DestroySublayerEnumHandle(engine, enumHandle) == 0)
                {
                    enumHandle.SetHandleAsInvalid();
                }
                enumHandle.Dispose();
            }
            Check(createResult, "FwpmSubLayerCreateEnumHandle0");
        }
        if (enumHandle is null || enumHandle.IsInvalid)
        {
            enumHandle?.Dispose();
            throw new WfpReadbackException("FwpmSubLayerCreateEnumHandle0 returned success without a valid enumeration handle.");
        }
        try
        {
            var done = false;
            while (!done)
            {
                var enumResult = this.api.EnumerateSublayers(engine, enumHandle, WfpReadbackLimits.PageSize, out var entries, out var count);
                try
                {
                    Check(enumResult, "FwpmSubLayerEnum0");
                    if (!ValidateBatch(entries, count, output.Count, "sublayer", issues, out done))
                    {
                        break;
                    }
                    for (uint i = 0; i < count; i++)
                    {
                        var native = entries[i];
                        if (native is null)
                        {
                            issues.Add(new SnapshotIssue(SnapshotIssueCode.NullEntry, "sublayer", "", $"Sublayer batch entry {i} is null."));
                            continue;
                        }
                        var descriptor = this.ReadSecurityDescriptor(engine, "sublayer", native->subLayerKey, issues);
                        output.Add(NativeObjectDecoder.DecodeSublayer(native, descriptor));
                    }
                }
                finally
                {
                    void* allocation = entries;
                    this.api.FreeMemory(&allocation);
                }
            }
        }
        finally
        {
            try
            {
                var result = this.api.DestroySublayerEnumHandle(engine, enumHandle);
                if (result != 0)
                {
                    issues.Add(ApiIssue("FwpmSubLayerDestroyEnumHandle0", result));
                }
                else
                {
                    enumHandle.SetHandleAsInvalid();
                }
            }
            finally
            {
                enumHandle.Dispose();
            }
        }
    }

    private void ReadLayers(SafeHandle engine, List<LayerSnapshot> output, List<SnapshotIssue> issues)
    {
        var createResult = this.api.CreateLayerEnumHandle(engine, out var enumHandle);
        if (createResult != 0)
        {
            if (enumHandle is not null && !enumHandle.IsInvalid)
            {
                if (this.api.DestroyLayerEnumHandle(engine, enumHandle) == 0)
                {
                    enumHandle.SetHandleAsInvalid();
                }
                enumHandle.Dispose();
            }
            Check(createResult, "FwpmLayerCreateEnumHandle0");
        }
        if (enumHandle is null || enumHandle.IsInvalid)
        {
            enumHandle?.Dispose();
            throw new WfpReadbackException("FwpmLayerCreateEnumHandle0 returned success without a valid enumeration handle.");
        }
        try
        {
            var done = false;
            while (!done)
            {
                var enumResult = this.api.EnumerateLayers(engine, enumHandle, WfpReadbackLimits.PageSize, out var entries, out var count);
                try
                {
                    Check(enumResult, "FwpmLayerEnum0");
                    if (!ValidateBatch(entries, count, output.Count, "layer", issues, out done))
                    {
                        break;
                    }
                    for (uint i = 0; i < count; i++)
                    {
                        var native = entries[i];
                        if (native is null)
                        {
                            issues.Add(new SnapshotIssue(SnapshotIssueCode.NullEntry, "layer", "", $"Layer batch entry {i} is null."));
                            continue;
                        }
                        var descriptor = this.ReadSecurityDescriptor(engine, "layer", native->layerKey, issues);
                        output.Add(NativeObjectDecoder.DecodeLayer(native, descriptor));
                    }
                }
                finally
                {
                    void* allocation = entries;
                    this.api.FreeMemory(&allocation);
                }
            }
        }
        finally
        {
            try
            {
                var result = this.api.DestroyLayerEnumHandle(engine, enumHandle);
                if (result != 0)
                {
                    issues.Add(ApiIssue("FwpmLayerDestroyEnumHandle0", result));
                }
                else
                {
                    enumHandle.SetHandleAsInvalid();
                }
            }
            finally
            {
                enumHandle.Dispose();
            }
        }
    }

    private void ReadFilters(SafeHandle engine, List<FilterSnapshot> output, List<SnapshotIssue> issues)
    {
        var createResult = this.api.CreateFilterEnumHandle(engine, out var enumHandle);
        if (createResult != 0)
        {
            if (enumHandle is not null && !enumHandle.IsInvalid)
            {
                if (this.api.DestroyFilterEnumHandle(engine, enumHandle) == 0)
                {
                    enumHandle.SetHandleAsInvalid();
                }
                enumHandle.Dispose();
            }
            Check(createResult, "FwpmFilterCreateEnumHandle0");
        }
        if (enumHandle is null || enumHandle.IsInvalid)
        {
            enumHandle?.Dispose();
            throw new WfpReadbackException("FwpmFilterCreateEnumHandle0 returned success without a valid enumeration handle.");
        }
        try
        {
            var done = false;
            while (!done)
            {
                var enumResult = this.api.EnumerateFilters(engine, enumHandle, WfpReadbackLimits.PageSize, out var entries, out var count);
                try
                {
                    Check(enumResult, "FwpmFilterEnum0");
                    if (!ValidateBatch(entries, count, output.Count, "filter", issues, out done))
                    {
                        break;
                    }
                    for (uint i = 0; i < count; i++)
                    {
                        var native = entries[i];
                        if (native is null)
                        {
                            issues.Add(new SnapshotIssue(SnapshotIssueCode.NullEntry, "filter", "", $"Filter batch entry {i} is null."));
                            continue;
                        }
                        var descriptor = this.ReadSecurityDescriptor(engine, "filter", native->filterKey, issues);
                        output.Add(NativeObjectDecoder.DecodeFilter(native, descriptor));
                    }
                }
                finally
                {
                    void* allocation = entries;
                    this.api.FreeMemory(&allocation);
                }
            }
        }
        finally
        {
            try
            {
                var result = this.api.DestroyFilterEnumHandle(engine, enumHandle);
                if (result != 0)
                {
                    issues.Add(ApiIssue("FwpmFilterDestroyEnumHandle0", result));
                }
                else
                {
                    enumHandle.SetHandleAsInvalid();
                }
            }
            finally
            {
                enumHandle.Dispose();
            }
        }
    }

    private void ReadCallouts(SafeHandle engine, List<CalloutSnapshot> output, List<SnapshotIssue> issues)
    {
        var createResult = this.api.CreateCalloutEnumHandle(engine, out var enumHandle);
        if (createResult != 0)
        {
            if (enumHandle is not null && !enumHandle.IsInvalid)
            {
                if (this.api.DestroyCalloutEnumHandle(engine, enumHandle) == 0)
                {
                    enumHandle.SetHandleAsInvalid();
                }
                enumHandle.Dispose();
            }
            Check(createResult, "FwpmCalloutCreateEnumHandle0");
        }
        if (enumHandle is null || enumHandle.IsInvalid)
        {
            enumHandle?.Dispose();
            throw new WfpReadbackException("FwpmCalloutCreateEnumHandle0 returned success without a valid enumeration handle.");
        }
        try
        {
            var done = false;
            while (!done)
            {
                var enumResult = this.api.EnumerateCallouts(engine, enumHandle, WfpReadbackLimits.PageSize, out var entries, out var count);
                try
                {
                    Check(enumResult, "FwpmCalloutEnum0");
                    if (!ValidateBatch(entries, count, output.Count, "callout", issues, out done))
                    {
                        break;
                    }
                    for (uint i = 0; i < count; i++)
                    {
                        var native = entries[i];
                        if (native is null)
                        {
                            issues.Add(new SnapshotIssue(SnapshotIssueCode.NullEntry, "callout", "", $"Callout batch entry {i} is null."));
                            continue;
                        }
                        var descriptor = this.ReadSecurityDescriptor(engine, "callout", native->calloutKey, issues);
                        output.Add(NativeObjectDecoder.DecodeCallout(native, descriptor));
                    }
                }
                finally
                {
                    void* allocation = entries;
                    this.api.FreeMemory(&allocation);
                }
            }
        }
        finally
        {
            try
            {
                var result = this.api.DestroyCalloutEnumHandle(engine, enumHandle);
                if (result != 0)
                {
                    issues.Add(ApiIssue("FwpmCalloutDestroyEnumHandle0", result));
                }
                else
                {
                    enumHandle.SetHandleAsInvalid();
                }
            }
            finally
            {
                enumHandle.Dispose();
            }
        }
    }

    private void ReadProviderContexts(SafeHandle engine, List<ProviderContextSnapshot> output, List<SnapshotIssue> issues)
    {
        var createResult = this.api.CreateProviderContextEnumHandle(engine, out var enumHandle);
        if (createResult != 0)
        {
            if (enumHandle is not null && !enumHandle.IsInvalid)
            {
                if (this.api.DestroyProviderContextEnumHandle(engine, enumHandle) == 0)
                {
                    enumHandle.SetHandleAsInvalid();
                }
                enumHandle.Dispose();
            }
            Check(createResult, "FwpmProviderContextCreateEnumHandle0");
        }
        if (enumHandle is null || enumHandle.IsInvalid)
        {
            enumHandle?.Dispose();
            throw new WfpReadbackException("FwpmProviderContextCreateEnumHandle0 returned success without a valid enumeration handle.");
        }
        try
        {
            var done = false;
            while (!done)
            {
                var enumResult = this.api.EnumerateProviderContexts(engine, enumHandle, WfpReadbackLimits.PageSize, out var entries, out var count);
                try
                {
                    Check(enumResult, "FwpmProviderContextEnum0");
                    if (!ValidateBatch(entries, count, output.Count, "provider-context", issues, out done))
                    {
                        break;
                    }
                    for (uint i = 0; i < count; i++)
                    {
                        var native = entries[i];
                        if (native is null)
                        {
                            issues.Add(new SnapshotIssue(SnapshotIssueCode.NullEntry, "provider-context", "", $"Provider context batch entry {i} is null."));
                            continue;
                        }
                        var descriptor = this.ReadSecurityDescriptor(engine, "provider-context", native->providerContextKey, issues);
                        output.Add(NativeObjectDecoder.DecodeProviderContext(native, descriptor));
                    }
                }
                finally
                {
                    void* allocation = entries;
                    this.api.FreeMemory(&allocation);
                }
            }
        }
        finally
        {
            try
            {
                var result = this.api.DestroyProviderContextEnumHandle(engine, enumHandle);
                if (result != 0)
                {
                    issues.Add(ApiIssue("FwpmProviderContextDestroyEnumHandle0", result));
                }
                else
                {
                    enumHandle.SetHandleAsInvalid();
                }
            }
            finally
            {
                enumHandle.Dispose();
            }
        }
    }

    private static void VerifyCalloutReferences(
        IReadOnlyList<FilterSnapshot> filters,
        IReadOnlyList<CalloutSnapshot> callouts,
        List<SnapshotIssue> issues)
    {
        var keys = new HashSet<Guid>();
        foreach (var callout in callouts)
        {
            if (!keys.Add(callout.Key))
            {
                issues.Add(new SnapshotIssue(SnapshotIssueCode.UnsupportedNativeValue, "callout", callout.Key.ToString("D"), "Enumeration returned a duplicate callout key."));
            }
        }

        var byKey = callouts.GroupBy(item => item.Key).ToDictionary(group => group.Key, group => group.First());
        foreach (var filter in filters)
        {
            if (filter.CalloutKey is not Guid key || key == Guid.Empty)
            {
                continue;
            }

            if (!byKey.TryGetValue(key, out var callout))
            {
                issues.Add(new SnapshotIssue(SnapshotIssueCode.ReferencedObjectNotIncluded, "filter", filter.Key.ToString("D"), $"Referenced callout {key:D} was not returned by the callout enumeration."));
            }
            else if (callout.ApplicableLayer != filter.LayerKey)
            {
                issues.Add(new SnapshotIssue(SnapshotIssueCode.UnsupportedNativeValue, "filter", filter.Key.ToString("D"), "Referenced callout applicable layer does not match the filter layer."));
            }
        }
    }

    private static void VerifyProviderContextReferences(
        IReadOnlyList<FilterSnapshot> filters,
        IReadOnlyList<ProviderContextSnapshot> providerContexts,
        List<SnapshotIssue> issues)
    {
        var byKey = new Dictionary<Guid, ProviderContextSnapshot>();
        foreach (var context in providerContexts)
        {
            if (context.Key == Guid.Empty)
            {
                issues.Add(new SnapshotIssue(SnapshotIssueCode.UnsupportedNativeValue, "provider-context", "", "Enumeration returned an empty provider-context key."));
                continue;
            }
            if (!byKey.TryAdd(context.Key, context))
            {
                issues.Add(new SnapshotIssue(SnapshotIssueCode.UnsupportedNativeValue, "provider-context", context.Key.ToString("D"), "Enumeration returned a duplicate provider-context key."));
            }
        }

        foreach (var filter in filters)
        {
            if (filter.ProviderContextKey is not Guid key)
            {
                continue;
            }
            if (!byKey.ContainsKey(key))
            {
                issues.Add(new SnapshotIssue(SnapshotIssueCode.ReferencedObjectNotIncluded, "filter", filter.Key.ToString("D"), $"Referenced provider context {key:D} was not returned by the provider-context enumeration."));
            }
        }
    }

    private static void VerifyLayerAndSublayerReferences(
        IReadOnlyList<FilterSnapshot> filters,
        IReadOnlyList<LayerSnapshot> layers,
        IReadOnlyList<SublayerSnapshot> sublayers,
        List<SnapshotIssue> issues)
    {
        var sublayerKeys = new HashSet<Guid>();
        foreach (var sublayer in sublayers)
        {
            if (sublayer.Key == Guid.Empty)
            {
                issues.Add(new SnapshotIssue(SnapshotIssueCode.UnsupportedNativeValue, "sublayer", "", "Enumeration returned an empty sublayer key."));
                continue;
            }
            if (!sublayerKeys.Add(sublayer.Key))
            {
                issues.Add(new SnapshotIssue(SnapshotIssueCode.UnsupportedNativeValue, "sublayer", sublayer.Key.ToString("D"), "Enumeration returned a duplicate sublayer key."));
            }
        }

        var layersByKey = new Dictionary<Guid, LayerSnapshot>();
        foreach (var layer in layers)
        {
            if (layer.Key == Guid.Empty)
            {
                issues.Add(new SnapshotIssue(SnapshotIssueCode.UnsupportedNativeValue, "layer", "", "Enumeration returned an empty layer key."));
                continue;
            }
            if (!layersByKey.TryAdd(layer.Key, layer))
            {
                issues.Add(new SnapshotIssue(SnapshotIssueCode.UnsupportedNativeValue, "layer", layer.Key.ToString("D"), "Enumeration returned a duplicate layer key."));
            }
        }

        foreach (var filter in filters)
        {
            if (!layersByKey.TryGetValue(filter.LayerKey, out var layer))
            {
                issues.Add(new SnapshotIssue(
                    SnapshotIssueCode.ReferencedObjectNotIncluded,
                    "filter",
                    filter.Key.ToString("D"),
                    $"Referenced layer {filter.LayerKey:D} was not returned by the layer enumeration."));
                continue;
            }

            // FWPM_FILTER0 documents IID_NULL as the request to use the layer's default sublayer.
            var effectiveSublayerKey = filter.SublayerKey == Guid.Empty ? layer.DefaultSublayerKey : filter.SublayerKey;
            if (effectiveSublayerKey == Guid.Empty)
            {
                issues.Add(new SnapshotIssue(SnapshotIssueCode.UnsupportedNativeValue, "filter", filter.Key.ToString("D"), "The referenced layer returned an empty default sublayer key."));
                continue;
            }
            if (!sublayerKeys.Contains(effectiveSublayerKey))
            {
                issues.Add(new SnapshotIssue(
                    SnapshotIssueCode.ReferencedObjectNotIncluded,
                    "filter",
                    filter.Key.ToString("D"),
                    $"Effective sublayer {effectiveSublayerKey:D} was not returned by the sublayer enumeration."));
            }
        }
    }

    private static void VerifyProviderReferences(
        IReadOnlyList<ProviderSnapshot> providers,
        IReadOnlyList<SublayerSnapshot> sublayers,
        IReadOnlyList<FilterSnapshot> filters,
        IReadOnlyList<CalloutSnapshot> callouts,
        IReadOnlyList<ProviderContextSnapshot> providerContexts,
        List<SnapshotIssue> issues)
    {
        var keys = new HashSet<Guid>();
        foreach (var provider in providers)
        {
            if (provider.Key == Guid.Empty)
            {
                issues.Add(new SnapshotIssue(SnapshotIssueCode.UnsupportedNativeValue, "provider", "", "Enumeration returned an empty provider key."));
                continue;
            }
            if (!keys.Add(provider.Key))
            {
                issues.Add(new SnapshotIssue(SnapshotIssueCode.UnsupportedNativeValue, "provider", provider.Key.ToString("D"), "Enumeration returned a duplicate provider key."));
            }
        }

        foreach (var sublayer in sublayers)
        {
            VerifyProviderReference("sublayer", sublayer.Key, sublayer.ProviderKey, keys, issues);
        }
        foreach (var filter in filters)
        {
            VerifyProviderReference("filter", filter.Key, filter.ProviderKey, keys, issues);
        }
        foreach (var callout in callouts)
        {
            VerifyProviderReference("callout", callout.Key, callout.ProviderKey, keys, issues);
        }
        foreach (var context in providerContexts)
        {
            VerifyProviderReference("provider-context", context.Key, context.ProviderKey, keys, issues);
        }
    }

    private static void VerifyProviderReference(
        string objectKind,
        Guid objectKey,
        Guid? providerKey,
        HashSet<Guid> providerKeys,
        List<SnapshotIssue> issues)
    {
        if (providerKey is not Guid key)
        {
            return;
        }
        if (key == Guid.Empty)
        {
            issues.Add(new SnapshotIssue(SnapshotIssueCode.UnsupportedNativeValue, objectKind, objectKey.ToString("D"), "A non-null providerKey contains an empty GUID."));
            return;
        }
        if (!providerKeys.Contains(key))
        {
            issues.Add(new SnapshotIssue(
                SnapshotIssueCode.ReferencedObjectNotIncluded,
                objectKind,
                objectKey.ToString("D"),
                $"Referenced provider {key:D} was not returned by the provider enumeration."));
        }
    }

    internal static bool ValidateBatch<T>(T** entries, uint count, int currentCount, string kind, List<SnapshotIssue> issues, out bool done)
        where T : unmanaged
    {
        done = count < WfpReadbackLimits.PageSize;
        if (count > WfpReadbackLimits.PageSize)
        {
            issues.Add(new SnapshotIssue(SnapshotIssueCode.NativeCountOutOfRange, kind, "", $"Native batch count {count} exceeds requested page size."));
            return false;
        }
        if (count != 0 && entries is null)
        {
            issues.Add(new SnapshotIssue(SnapshotIssueCode.InvalidNativePointer, kind, "", "Native enumeration returned entries without a pointer."));
            return false;
        }
        if (currentCount > WfpReadbackLimits.MaxObjects - count)
        {
            issues.Add(new SnapshotIssue(SnapshotIssueCode.EnumerationLimitReached, kind, "", $"Enumeration exceeded the {WfpReadbackLimits.MaxObjects} object cap."));
            return false;
        }
        return true;
    }

    private static void Check(uint result, string operation)
    {
        if (result != 0)
        {
            throw new WfpReadbackException($"{operation} failed with 0x{result:X8}.", result);
        }
    }

    private static SnapshotIssue ApiIssue(string operation, uint result) =>
        new(SnapshotIssueCode.NativeApiFailure, "snapshot", "", $"{operation} failed during cleanup with 0x{result:X8}.");

    private SecurityDescriptorSnapshot? ReadSecurityDescriptor(SafeHandle engine, string kind, Guid key, List<SnapshotIssue> issues)
    {
        if (key == Guid.Empty)
        {
            issues.Add(new SnapshotIssue(
                SnapshotIssueCode.SecurityDescriptorNotNormalized,
                kind,
                key.ToString("D"),
                "An empty object key cannot identify an object security descriptor; container security information was not requested."));
            return null;
        }

        IntPtr nativeDescriptor = IntPtr.Zero;
        uint result;
        try
        {
            result = kind switch
            {
                "provider" => this.api.GetProviderSecurityDescriptor(engine, key, WfpSecurityInformation.OwnerGroupDacl, out nativeDescriptor),
                "sublayer" => this.api.GetSublayerSecurityDescriptor(engine, key, WfpSecurityInformation.OwnerGroupDacl, out nativeDescriptor),
                "layer" => this.api.GetLayerSecurityDescriptor(engine, key, WfpSecurityInformation.OwnerGroupDacl, out nativeDescriptor),
                "filter" => this.api.GetFilterSecurityDescriptor(engine, key, WfpSecurityInformation.OwnerGroupDacl, out nativeDescriptor),
                "callout" => this.api.GetCalloutSecurityDescriptor(engine, key, WfpSecurityInformation.OwnerGroupDacl, out nativeDescriptor),
                "provider-context" => this.api.GetProviderContextSecurityDescriptor(engine, key, WfpSecurityInformation.OwnerGroupDacl, out nativeDescriptor),
                _ => throw new ArgumentOutOfRangeException(nameof(kind)),
            };
            if (result != 0)
            {
                issues.Add(new SnapshotIssue(SnapshotIssueCode.SecurityDescriptorNotNormalized, kind, key.ToString("D"), $"Security descriptor retrieval failed with 0x{result:X8}."));
                return null;
            }
            if (nativeDescriptor == IntPtr.Zero)
            {
                issues.Add(new SnapshotIssue(SnapshotIssueCode.SecurityDescriptorNotNormalized, kind, key.ToString("D"), "Security descriptor retrieval returned success with a null descriptor."));
                return null;
            }

            uint byteLength = this.api.GetSecurityDescriptorLength(nativeDescriptor);
            if (byteLength > SecurityDescriptorNormalizer.MaxDescriptorBytes || byteLength > int.MaxValue)
            {
                issues.Add(new SnapshotIssue(SnapshotIssueCode.SecurityDescriptorNotNormalized, kind, key.ToString("D"), "Security descriptor exceeds the configured byte limit."));
                return null;
            }

            var bytes = new ReadOnlySpan<byte>(nativeDescriptor.ToPointer(), checked((int)byteLength));
            if (!SecurityDescriptorNormalizer.TryNormalize(bytes, out var snapshot, out var error))
            {
                issues.Add(new SnapshotIssue(SnapshotIssueCode.SecurityDescriptorNotNormalized, kind, key.ToString("D"), error));
                return null;
            }

            return snapshot;
        }
        catch (Exception exception) when (exception is WfpReadbackException or ArgumentException or InvalidOperationException or OverflowException)
        {
            issues.Add(new SnapshotIssue(SnapshotIssueCode.SecurityDescriptorNotNormalized, kind, key.ToString("D"), $"Security descriptor could not be normalized: {exception.GetType().Name}."));
            return null;
        }
        finally
        {
            if (nativeDescriptor != IntPtr.Zero)
            {
                void* memory = nativeDescriptor.ToPointer();
                this.api.FreeMemory(&memory);
            }
        }
    }
}

internal static class WfpReadbackLimits
{
    internal const uint PageSize = 64;
    internal const int MaxObjects = 16384;
}

internal static class WfpSecurityInformation
{
    // OWNER_SECURITY_INFORMATION | GROUP_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION.
    // BFE ignores SACL ACEs and uses its own auditing, so do not request SACL_SECURITY_INFORMATION.
    internal const uint OwnerGroupDacl = 0x00000007;
}

public sealed class WfpReadbackException(string message, uint? nativeError = null) : Exception(message)
{
    public uint? NativeError { get; } = nativeError;
}

internal unsafe interface IReadOnlyWfpApi
{
    uint OpenEngine(out SafeHandle? engine);
    uint BeginReadTransaction(SafeHandle engine);
    uint CommitReadTransaction(SafeHandle engine);
    uint AbortReadTransaction(SafeHandle engine);
    uint CreateProviderEnumHandle(SafeHandle engine, out SafeHandle? enumHandle);
    uint EnumerateProviders(SafeHandle engine, SafeHandle enumHandle, uint requested, out FWPM_PROVIDER0** entries, out uint count);
    uint DestroyProviderEnumHandle(SafeHandle engine, SafeHandle enumHandle);
    uint GetProviderSecurityDescriptor(SafeHandle engine, Guid key, uint securityInformation, out IntPtr descriptor);
    uint CreateSublayerEnumHandle(SafeHandle engine, out SafeHandle? enumHandle);
    uint EnumerateSublayers(SafeHandle engine, SafeHandle enumHandle, uint requested, out FWPM_SUBLAYER0** entries, out uint count);
    uint DestroySublayerEnumHandle(SafeHandle engine, SafeHandle enumHandle);
    uint GetSublayerSecurityDescriptor(SafeHandle engine, Guid key, uint securityInformation, out IntPtr descriptor);
    uint CreateLayerEnumHandle(SafeHandle engine, out SafeHandle? enumHandle);
    uint EnumerateLayers(SafeHandle engine, SafeHandle enumHandle, uint requested, out FWPM_LAYER0** entries, out uint count);
    uint DestroyLayerEnumHandle(SafeHandle engine, SafeHandle enumHandle);
    uint GetLayerSecurityDescriptor(SafeHandle engine, Guid key, uint securityInformation, out IntPtr descriptor);
    uint CreateFilterEnumHandle(SafeHandle engine, out SafeHandle? enumHandle);
    uint EnumerateFilters(SafeHandle engine, SafeHandle enumHandle, uint requested, out FWPM_FILTER0** entries, out uint count);
    uint DestroyFilterEnumHandle(SafeHandle engine, SafeHandle enumHandle);
    uint GetFilterSecurityDescriptor(SafeHandle engine, Guid key, uint securityInformation, out IntPtr descriptor);
    uint CreateCalloutEnumHandle(SafeHandle engine, out SafeHandle? enumHandle);
    uint EnumerateCallouts(SafeHandle engine, SafeHandle enumHandle, uint requested, out FWPM_CALLOUT0** entries, out uint count);
    uint DestroyCalloutEnumHandle(SafeHandle engine, SafeHandle enumHandle);
    uint GetCalloutSecurityDescriptor(SafeHandle engine, Guid key, uint securityInformation, out IntPtr descriptor);
    uint CreateProviderContextEnumHandle(SafeHandle engine, out SafeHandle? enumHandle);
    uint EnumerateProviderContexts(SafeHandle engine, SafeHandle enumHandle, uint requested, out FWPM_PROVIDER_CONTEXT0** entries, out uint count);
    uint DestroyProviderContextEnumHandle(SafeHandle engine, SafeHandle enumHandle);
    uint GetProviderContextSecurityDescriptor(SafeHandle engine, Guid key, uint securityInformation, out IntPtr descriptor);
    uint GetSecurityDescriptorLength(IntPtr descriptor);
    void FreeMemory(void** memory);
}

internal sealed unsafe class WindowsWfpApi : IReadOnlyWfpApi
{
    private const uint RpcAuthnWinNt = 10;
    private const uint FwpmTransactionReadOnly = 1;
    private readonly Func<uint, (uint Result, SafeHandle? Engine)> openEngine;

    internal WindowsWfpApi() : this(OpenNativeEngine)
    {
    }

    internal WindowsWfpApi(Func<uint, (uint Result, SafeHandle? Engine)> openEngine)
    {
        this.openEngine = openEngine ?? throw new ArgumentNullException(nameof(openEngine));
    }

    private static (uint Result, SafeHandle? Engine) OpenNativeEngine(uint authenticationService)
    {
        var result = PInvoke.FwpmEngineOpen0(authenticationService, null, null, out var handle);
        return (result, handle);
    }

    public uint OpenEngine(out SafeHandle? engine)
    {
        var (result, handle) = this.openEngine(RpcAuthnWinNt);
        if (result != 0)
        {
            handle?.Dispose();
            engine = null;
            return result;
        }
        engine = handle;
        return result;
    }

    public uint BeginReadTransaction(SafeHandle engine) => PInvoke.FwpmTransactionBegin0(engine, FwpmTransactionReadOnly);
    public uint CommitReadTransaction(SafeHandle engine) => PInvoke.FwpmTransactionCommit0(engine);
    public uint AbortReadTransaction(SafeHandle engine) => PInvoke.FwpmTransactionAbort0(engine);

    public uint CreateProviderEnumHandle(SafeHandle engine, out SafeHandle? enumHandle)
    {
        var result = PInvoke.FwpmProviderCreateEnumHandle0(engine, null, out FWPM_PROVIDER_ENUM_HANDLE nativeHandle);
        enumHandle = nativeHandle.IsNull ? null : new NativeEnumSafeHandle((IntPtr)nativeHandle,
            value => PInvoke.FwpmProviderDestroyEnumHandle0((FWPM_ENGINE_HANDLE)engine.DangerousGetHandle(), (FWPM_PROVIDER_ENUM_HANDLE)value) == 0);
        return result;
    }

    public uint EnumerateProviders(SafeHandle engine, SafeHandle enumHandle, uint requested, out FWPM_PROVIDER0** entries, out uint count) =>
        PInvoke.FwpmProviderEnum0(engine, enumHandle, requested, out entries, out count);

    public uint DestroyProviderEnumHandle(SafeHandle engine, SafeHandle enumHandle) =>
        PInvoke.FwpmProviderDestroyEnumHandle0((FWPM_ENGINE_HANDLE)engine.DangerousGetHandle(), (FWPM_PROVIDER_ENUM_HANDLE)enumHandle.DangerousGetHandle());

    public uint GetProviderSecurityDescriptor(SafeHandle engine, Guid key, uint securityInformation, out IntPtr descriptor)
    {
        uint result = PInvoke.FwpmProviderGetSecurityInfoByKey0(engine, key, securityInformation, out _, out _, out _, out _, out var nativeDescriptor);
        descriptor = (IntPtr)nativeDescriptor;
        return result;
    }

    public uint CreateSublayerEnumHandle(SafeHandle engine, out SafeHandle? enumHandle)
    {
        var result = PInvoke.FwpmSubLayerCreateEnumHandle0(engine, null, out FWPM_SUBLAYER_ENUM_HANDLE nativeHandle);
        enumHandle = nativeHandle.IsNull ? null : new NativeEnumSafeHandle((IntPtr)nativeHandle,
            value => PInvoke.FwpmSubLayerDestroyEnumHandle0((FWPM_ENGINE_HANDLE)engine.DangerousGetHandle(), (FWPM_SUBLAYER_ENUM_HANDLE)value) == 0);
        return result;
    }

    public uint EnumerateSublayers(SafeHandle engine, SafeHandle enumHandle, uint requested, out FWPM_SUBLAYER0** entries, out uint count) =>
        PInvoke.FwpmSubLayerEnum0(engine, enumHandle, requested, out entries, out count);

    public uint DestroySublayerEnumHandle(SafeHandle engine, SafeHandle enumHandle) =>
        PInvoke.FwpmSubLayerDestroyEnumHandle0((FWPM_ENGINE_HANDLE)engine.DangerousGetHandle(), (FWPM_SUBLAYER_ENUM_HANDLE)enumHandle.DangerousGetHandle());

    public uint GetSublayerSecurityDescriptor(SafeHandle engine, Guid key, uint securityInformation, out IntPtr descriptor)
    {
        uint result = PInvoke.FwpmSubLayerGetSecurityInfoByKey0(engine, key, securityInformation, out _, out _, out _, out _, out var nativeDescriptor);
        descriptor = (IntPtr)nativeDescriptor;
        return result;
    }

    public uint CreateLayerEnumHandle(SafeHandle engine, out SafeHandle? enumHandle)
    {
        var result = PInvoke.FwpmLayerCreateEnumHandle0(engine, null, out FWPM_LAYER_ENUM_HANDLE nativeHandle);
        enumHandle = nativeHandle.IsNull ? null : new NativeEnumSafeHandle((IntPtr)nativeHandle,
            value => PInvoke.FwpmLayerDestroyEnumHandle0((FWPM_ENGINE_HANDLE)engine.DangerousGetHandle(), (FWPM_LAYER_ENUM_HANDLE)value) == 0);
        return result;
    }

    public uint EnumerateLayers(SafeHandle engine, SafeHandle enumHandle, uint requested, out FWPM_LAYER0** entries, out uint count) =>
        PInvoke.FwpmLayerEnum0(engine, enumHandle, requested, out entries, out count);

    public uint DestroyLayerEnumHandle(SafeHandle engine, SafeHandle enumHandle) =>
        PInvoke.FwpmLayerDestroyEnumHandle0((FWPM_ENGINE_HANDLE)engine.DangerousGetHandle(), (FWPM_LAYER_ENUM_HANDLE)enumHandle.DangerousGetHandle());

    public uint GetLayerSecurityDescriptor(SafeHandle engine, Guid key, uint securityInformation, out IntPtr descriptor)
    {
        uint result = PInvoke.FwpmLayerGetSecurityInfoByKey0(engine, key, securityInformation, out _, out _, out _, out _, out var nativeDescriptor);
        descriptor = (IntPtr)nativeDescriptor;
        return result;
    }

    public uint CreateFilterEnumHandle(SafeHandle engine, out SafeHandle? enumHandle)
    {
        var result = PInvoke.FwpmFilterCreateEnumHandle0(engine, null, out FWPM_FILTER_ENUM_HANDLE nativeHandle);
        enumHandle = nativeHandle.IsNull ? null : new NativeEnumSafeHandle((IntPtr)nativeHandle,
            value => PInvoke.FwpmFilterDestroyEnumHandle0((FWPM_ENGINE_HANDLE)engine.DangerousGetHandle(), (FWPM_FILTER_ENUM_HANDLE)value) == 0);
        return result;
    }

    public uint EnumerateFilters(SafeHandle engine, SafeHandle enumHandle, uint requested, out FWPM_FILTER0** entries, out uint count) =>
        PInvoke.FwpmFilterEnum0(engine, enumHandle, requested, out entries, out count);

    public uint DestroyFilterEnumHandle(SafeHandle engine, SafeHandle enumHandle) =>
        PInvoke.FwpmFilterDestroyEnumHandle0((FWPM_ENGINE_HANDLE)engine.DangerousGetHandle(), (FWPM_FILTER_ENUM_HANDLE)enumHandle.DangerousGetHandle());

    public uint GetFilterSecurityDescriptor(SafeHandle engine, Guid key, uint securityInformation, out IntPtr descriptor)
    {
        uint result = PInvoke.FwpmFilterGetSecurityInfoByKey0(engine, key, securityInformation, out _, out _, out _, out _, out var nativeDescriptor);
        descriptor = (IntPtr)nativeDescriptor;
        return result;
    }

    public uint CreateCalloutEnumHandle(SafeHandle engine, out SafeHandle? enumHandle)
    {
        var result = PInvoke.FwpmCalloutCreateEnumHandle0(engine, null, out FWPM_CALLOUT_ENUM_HANDLE nativeHandle);
        enumHandle = nativeHandle.IsNull ? null : new NativeEnumSafeHandle((IntPtr)nativeHandle,
            value => PInvoke.FwpmCalloutDestroyEnumHandle0((FWPM_ENGINE_HANDLE)engine.DangerousGetHandle(), (FWPM_CALLOUT_ENUM_HANDLE)value) == 0);
        return result;
    }

    public uint EnumerateCallouts(SafeHandle engine, SafeHandle enumHandle, uint requested, out FWPM_CALLOUT0** entries, out uint count) =>
        PInvoke.FwpmCalloutEnum0(engine, enumHandle, requested, out entries, out count);

    public uint DestroyCalloutEnumHandle(SafeHandle engine, SafeHandle enumHandle) =>
        PInvoke.FwpmCalloutDestroyEnumHandle0((FWPM_ENGINE_HANDLE)engine.DangerousGetHandle(), (FWPM_CALLOUT_ENUM_HANDLE)enumHandle.DangerousGetHandle());

    public uint GetCalloutSecurityDescriptor(SafeHandle engine, Guid key, uint securityInformation, out IntPtr descriptor)
    {
        uint result = PInvoke.FwpmCalloutGetSecurityInfoByKey0(engine, key, securityInformation, out _, out _, out _, out _, out var nativeDescriptor);
        descriptor = (IntPtr)nativeDescriptor;
        return result;
    }

    public uint CreateProviderContextEnumHandle(SafeHandle engine, out SafeHandle? enumHandle)
    {
        var result = PInvoke.FwpmProviderContextCreateEnumHandle0(engine, null, out FWPM_PROVIDER_CONTEXT_ENUM_HANDLE nativeHandle);
        enumHandle = nativeHandle.IsNull ? null : new NativeEnumSafeHandle((IntPtr)nativeHandle,
            value => PInvoke.FwpmProviderContextDestroyEnumHandle0((FWPM_ENGINE_HANDLE)engine.DangerousGetHandle(), (FWPM_PROVIDER_CONTEXT_ENUM_HANDLE)value) == 0);
        return result;
    }

    public uint EnumerateProviderContexts(SafeHandle engine, SafeHandle enumHandle, uint requested, out FWPM_PROVIDER_CONTEXT0** entries, out uint count) =>
        PInvoke.FwpmProviderContextEnum0(engine, enumHandle, requested, out entries, out count);

    public uint DestroyProviderContextEnumHandle(SafeHandle engine, SafeHandle enumHandle) =>
        PInvoke.FwpmProviderContextDestroyEnumHandle0((FWPM_ENGINE_HANDLE)engine.DangerousGetHandle(), (FWPM_PROVIDER_CONTEXT_ENUM_HANDLE)enumHandle.DangerousGetHandle());

    public uint GetProviderContextSecurityDescriptor(SafeHandle engine, Guid key, uint securityInformation, out IntPtr descriptor)
    {
        uint result = PInvoke.FwpmProviderContextGetSecurityInfoByKey0(engine, key, securityInformation, out _, out _, out _, out _, out var nativeDescriptor);
        descriptor = (IntPtr)nativeDescriptor;
        return result;
    }

    public uint GetSecurityDescriptorLength(IntPtr descriptor) =>
        PInvoke.GetSecurityDescriptorLength((PSECURITY_DESCRIPTOR)descriptor);

    public void FreeMemory(void** memory) => PInvoke.FwpmFreeMemory0(memory);
}

internal sealed class NativeEnumSafeHandle : SafeHandle
{
    private readonly Func<IntPtr, bool> release;

    internal NativeEnumSafeHandle(IntPtr value, Func<IntPtr, bool> release) : base(IntPtr.Zero, ownsHandle: true)
    {
        this.release = release;
        this.SetHandle(value);
    }

    public override bool IsInvalid => this.handle == IntPtr.Zero || this.handle == new IntPtr(-1);

    protected override bool ReleaseHandle() => this.release(this.handle);
}
