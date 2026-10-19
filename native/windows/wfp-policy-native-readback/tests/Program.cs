using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using Microsoft.Win32.SafeHandles;
using Windows.Win32.NetworkManagement.WindowsFilteringPlatform;
using WfpPolicy.NativeReadback;

return Harness.Run();

internal static unsafe class Harness
{
    internal static int Run()
    {
        var tests = new (string Name, Action Body)[]
        {
            ("decodes supported provider, sublayer, filter fields and stays incomplete for ACL evidence", DecodeSupportedFields),
            ("requires a valid UINT64 effective weight", EffectiveWeightMustBeUInt64),
            ("normalizes canonical self-relative security descriptors", SecurityDescriptorNormalization),
            ("rejects malformed and noncanonical security descriptors", SecurityDescriptorRejection),
            ("copies bounded native byte-blob conditions into immutable hex", ByteBlobConditionIsCopied),
            ("unsupported native condition is not treated as complete", UnsupportedCondition),
            ("rejects null pointers, malformed arrays, oversized blobs, and unterminated strings", DecoderBoundaries),
            ("public snapshot values cannot be constructed with caller-owned mutable lists", SnapshotCollectionsAreImmutable),
            ("opens the native engine with RPC_C_AUTHN_WINNT", WindowsApiUsesWinNtAuthentication),
            ("accepts an exact page cap and checks one bounded sentinel page", ReaderPagingCapUsesSentinelPage),
            ("releases BFE-style buffers, enum handles, transaction, and engine on success", ReaderCleanupOnSuccess),
            ("reads and frees object security descriptors within the snapshot", ReaderReadsSecurityDescriptors),
            ("keeps failed layer security-descriptor reads incomplete and frees returned memory", ReaderLayerSecurityDescriptorFailureStaysIncomplete),
            ("resolves filter callout references from the same bounded snapshot", ReaderResolvesCalloutReferences),
            ("rejects dangling and layer-mismatched callout references", ReaderRejectsInvalidCalloutReferences),
            ("rejects duplicate callout keys", ReaderRejectsDuplicateCalloutKeys),
            ("resolves filters through layer default and explicit sublayer keys", ReaderResolvesSublayerReferences),
            ("rejects missing layers, default sublayers, and explicit sublayers", ReaderRejectsInvalidLayerAndSublayerReferences),
            ("releases layer buffers and handles on enumeration failure", ReaderLayerEnumerationFailureCleansUp),
            ("closes optional provider references across WFP object families", ReaderResolvesProviderReferences),
            ("rejects dangling and empty provider references", ReaderRejectsInvalidProviderReferences),
            ("rejects duplicate provider keys", ReaderRejectsDuplicateProviderKeys),
            ("releases callout buffers and handles on enumeration failure", ReaderCalloutEnumerationFailureCleansUp),
            ("resolves provider-context references and copies a general context payload", ReaderResolvesProviderContextReferences),
            ("decodes bounded classify-options provider contexts", ReaderDecodesClassifyOptionsProviderContext),
            ("decodes only documented multicast and loose-source option values", ReaderDecodesScalarClassifyOptions),
            ("rejects malformed and unsupported classify-options payloads", ReaderRejectsMalformedClassifyOptionsProviderContext),
            ("rejects dangling and malformed provider-context references", ReaderRejectsInvalidProviderContextReferences),
            ("keeps unsupported provider-context payloads incomplete", ReaderRejectsUnsupportedProviderContextPayloads),
            ("rejects empty and duplicate context keys without requesting container ACLs", ReaderRejectsDuplicateProviderContextKeys),
            ("releases provider-context buffers and handles on enumeration failure", ReaderProviderContextEnumerationFailureCleansUp),
            ("security descriptor read failure remains incomplete", ReaderSecurityDescriptorFailureStaysIncomplete),
            ("releases returned buffers and all handles when enumeration fails", ReaderCleanupOnApiFailure),
            ("destroy failure remains incomplete while SafeHandle cleanup retries", ReaderDestroyFailureStaysIncomplete),
            ("fails closed when enum creation succeeds with a null handle", ReaderRejectsNullEnumHandle),
        };

        var failures = 0;
        foreach (var (name, body) in tests)
        {
            try
            {
                body();
                Console.WriteLine($"PASS {name}");
            }
            catch (Exception exception)
            {
                failures++;
                Console.Error.WriteLine($"FAIL {name}: {exception.Message}");
            }
        }

        Console.WriteLine($"RESULT {tests.Length - failures}/{tests.Length} fixture checks passed");
        return failures == 0 ? 0 : 1;
    }

    private static void DecodeSupportedFields()
    {
        using var arena = new FixtureArena();
        arena.BeginBatch();
        var provider = arena.Alloc<FWPM_PROVIDER0>();
        provider->providerKey = Guid.NewGuid();
        provider->displayData.name = arena.AllocUtf16("fixture provider");
        provider->displayData.description = arena.AllocUtf16("read-only fixture");
        provider->serviceName = arena.AllocUtf16("FixtureService");
        provider->flags = 3;
        provider->providerData.size = 3;
        provider->providerData.data = arena.AllocBytes([0x11, 0x22, 0x33]);

        var decodedProvider = NativeObjectDecoder.DecodeProvider(provider);
        Equal(provider->providerKey, decodedProvider.Key, "provider key");
        Equal("fixture provider", decodedProvider.Name, "provider name");
        Equal("FixtureService", decodedProvider.ServiceName, "provider service");
        SequenceEqual(new byte[] { 0x11, 0x22, 0x33 }, decodedProvider.ProviderData, "provider data");
        Assert(!decodedProvider.IsComplete, "provider ACL omission must keep the object incomplete");
        AssertReadOnly(decodedProvider.ProviderData, "provider data");

        var sublayer = arena.Alloc<FWPM_SUBLAYER0>();
        sublayer->subLayerKey = Guid.NewGuid();
        sublayer->providerKey = arena.Alloc<Guid>();
        *sublayer->providerKey = provider->providerKey;
        sublayer->displayData.name = arena.AllocUtf16("fixture sublayer");
        sublayer->weight = 17;
        sublayer->providerData.size = 0;
        var decodedSublayer = NativeObjectDecoder.DecodeSublayer(sublayer);
        Equal(provider->providerKey, decodedSublayer.ProviderKey, "sublayer provider key");
        Equal((ushort)17, decodedSublayer.Weight, "sublayer weight");
        Assert(!decodedSublayer.IsComplete, "sublayer ACL omission must keep the object incomplete");

        var filter = arena.Alloc<FWPM_FILTER0>();
        filter->filterKey = Guid.NewGuid();
        filter->displayData.name = arena.AllocUtf16("fixture filter");
        filter->providerData.size = 0;
        filter->layerKey = Guid.NewGuid();
        filter->subLayerKey = sublayer->subLayerKey;
        filter->weight.type = FWP_DATA_TYPE.FWP_UINT32;
        filter->weight.uint32 = 91;
        filter->effectiveWeight.type = FWP_DATA_TYPE.FWP_UINT64;
        filter->effectiveWeight.uint64 = arena.Alloc<ulong>();
        *filter->effectiveWeight.uint64 = 1234;
        filter->filterId = 9876;
        filter->action.type = FWP_ACTION_TYPE.FWP_ACTION_BLOCK;
        filter->numFilterConditions = 1;
        filter->filterCondition = arena.Alloc<FWPM_FILTER_CONDITION0>();
        filter->filterCondition->fieldKey = Guid.NewGuid();
        filter->filterCondition->matchType = FWP_MATCH_TYPE.FWP_MATCH_EQUAL;
        filter->filterCondition->conditionValue.type = FWP_DATA_TYPE.FWP_UINT16;
        filter->filterCondition->conditionValue.uint16 = 443;

        var decodedFilter = NativeObjectDecoder.DecodeFilter(filter);
        Equal("91", decodedFilter.Weight.ScalarValue, "filter weight");
        Equal("1234", decodedFilter.EffectiveWeight.ScalarValue, "filter effective weight");
        Equal((ulong)9876, decodedFilter.FilterId, "filter id");
        Equal("443", decodedFilter.Conditions.Single().Value.ScalarValue, "condition value");
        Assert(!decodedFilter.Issues.Any(issue => issue.Code == SnapshotIssueCode.EffectiveWeightNotNormalized), "a valid BFE-assigned UINT64 weight is normalized readback evidence");
        Assert(decodedFilter.Issues.Any(issue => issue.Code == SnapshotIssueCode.SecurityDescriptorNotNormalized), "filter ACL omission must remain incomplete");
        Assert(!decodedFilter.IsComplete, "filter must remain incomplete while ACL evidence is open");

        arena.FreeCurrentBatch();
        Equal(0, arena.OutstandingAllocations, "fixture allocations after explicit free");
    }

    private static void EffectiveWeightMustBeUInt64()
    {
        using var arena = new FixtureArena();
        arena.BeginBatch();
        var filter = arena.Alloc<FWPM_FILTER0>();
        filter->filterKey = Guid.NewGuid();
        filter->providerData.size = 0;
        filter->effectiveWeight.type = FWP_DATA_TYPE.FWP_UINT32;
        filter->effectiveWeight.uint32 = 12;

        var wrongTag = NativeObjectDecoder.DecodeFilter(filter);
        Assert(wrongTag.Issues.Any(issue => issue.Code == SnapshotIssueCode.EffectiveWeightNotNormalized), "non-UINT64 effective weight must be incomplete");

        filter->effectiveWeight.type = FWP_DATA_TYPE.FWP_UINT64;
        filter->effectiveWeight.uint64 = null;
        var missingValue = NativeObjectDecoder.DecodeFilter(filter);
        Assert(missingValue.Issues.Any(issue => issue.Code == SnapshotIssueCode.EffectiveWeightNotNormalized), "null UINT64 pointer must be incomplete");
        Assert(missingValue.Issues.Any(issue => issue.Code == SnapshotIssueCode.UnsupportedNativeValue), "null UINT64 pointer must preserve the native-value error");

        arena.FreeCurrentBatch();
    }

    private static void SecurityDescriptorNormalization()
    {
        byte[] binary = CreateFixtureSecurityDescriptor(canonical: true);
        Assert(SecurityDescriptorNormalizer.TryNormalize(binary, out var snapshot, out var error), $"canonical descriptor should normalize: {error}");
        Assert(snapshot is not null, "normalized descriptor should be returned");
        Assert(snapshot!.Sddl.Length != 0, "normalized SDDL should be present");
        Equal(binary.Length, snapshot.BinaryLength, "security descriptor length");
        Assert(snapshot.DaclPresent && !snapshot.HasNullDacl, "present DACL should not be treated as a null DACL");
        Equal(Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(snapshot.Sddl))).ToLowerInvariant(), snapshot.Sha256, "normalized SDDL hash");

        var owner = new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null);
        var group = new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid, null);
        var nullDaclDescriptor = new RawSecurityDescriptor(
            ControlFlags.SelfRelative | ControlFlags.DiscretionaryAclPresent,
            owner,
            group,
            null,
            null);
        var nullDaclBytes = new byte[nullDaclDescriptor.BinaryLength];
        nullDaclDescriptor.GetBinaryForm(nullDaclBytes, 0);
        Assert(SecurityDescriptorNormalizer.TryNormalize(nullDaclBytes, out var nullDaclSnapshot, out error), $"null DACL descriptor should normalize for explicit policy comparison: {error}");
        Assert(nullDaclSnapshot!.DaclPresent && nullDaclSnapshot.HasNullDacl, "null DACL must be distinguished from an absent DACL");

        var absentDaclDescriptor = new RawSecurityDescriptor(ControlFlags.SelfRelative, owner, group, null, null);
        var absentDaclBytes = new byte[absentDaclDescriptor.BinaryLength];
        absentDaclDescriptor.GetBinaryForm(absentDaclBytes, 0);
        Assert(SecurityDescriptorNormalizer.TryNormalize(absentDaclBytes, out var absentDaclSnapshot, out error), $"absent DACL descriptor should normalize for explicit policy comparison: {error}");
        Assert(!absentDaclSnapshot!.DaclPresent && !absentDaclSnapshot.HasNullDacl, "absent DACL must remain distinct from a null DACL");
    }

    private static void SecurityDescriptorRejection()
    {
        Assert(!SecurityDescriptorNormalizer.TryNormalize(new byte[] { 1, 2, 3 }, out _, out _), "short malformed descriptor must reject");
        byte[] noncanonical = CreateFixtureSecurityDescriptor(canonical: false);
        Assert(!SecurityDescriptorNormalizer.TryNormalize(noncanonical, out _, out string error), "noncanonical DACL must reject");
        Assert(error.Contains("noncanonical", StringComparison.OrdinalIgnoreCase), "rejection should explain DACL order failure");
    }

    internal static byte[] CreateFixtureSecurityDescriptor(bool canonical)
    {
        var owner = new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null);
        var group = new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid, null);
        var dacl = new RawAcl(GenericAcl.AclRevision, 2);
        var deny = new CommonAce(AceFlags.None, AceQualifier.AccessDenied, 1, owner, isCallback: false, opaque: null);
        var allow = new CommonAce(AceFlags.None, AceQualifier.AccessAllowed, 1, owner, isCallback: false, opaque: null);
        if (canonical)
        {
            dacl.InsertAce(0, deny);
            dacl.InsertAce(1, allow);
        }
        else
        {
            dacl.InsertAce(0, allow);
            dacl.InsertAce(1, deny);
        }

        var descriptor = new RawSecurityDescriptor(
            ControlFlags.SelfRelative | ControlFlags.DiscretionaryAclPresent,
            owner,
            group,
            null,
            dacl);
        var bytes = new byte[descriptor.BinaryLength];
        descriptor.GetBinaryForm(bytes, 0);
        return bytes;
    }

    private static void UnsupportedCondition()
    {
        using var arena = new FixtureArena();
        arena.BeginBatch();
        var filter = arena.Alloc<FWPM_FILTER0>();
        filter->filterKey = Guid.NewGuid();
        filter->providerData.size = 0;
        filter->numFilterConditions = 1;
        filter->filterCondition = arena.Alloc<FWPM_FILTER_CONDITION0>();
        filter->filterCondition->conditionValue.type = FWP_DATA_TYPE.FWP_V4_ADDR_MASK;

        var decoded = NativeObjectDecoder.DecodeFilter(filter);
        Assert(!decoded.IsComplete, "unsupported values cannot be reported complete");
        Assert(decoded.Issues.Any(issue => issue.Code == SnapshotIssueCode.UnsupportedNativeValue), "unsupported value issue is required");
        Assert(!decoded.Conditions.Single().Value.IsDecoded, "unsupported value must be explicit");
        arena.FreeCurrentBatch();
    }

    private static void ByteBlobConditionIsCopied()
    {
        using var arena = new FixtureArena();
        arena.BeginBatch();
        var filter = arena.Alloc<FWPM_FILTER0>();
        filter->filterKey = Guid.NewGuid();
        filter->providerData.size = 0;
        filter->numFilterConditions = 1;
        filter->filterCondition = arena.Alloc<FWPM_FILTER_CONDITION0>();
        filter->filterCondition->conditionValue.type = FWP_DATA_TYPE.FWP_BYTE_BLOB_TYPE;
        var blob = arena.Alloc<FWP_BYTE_BLOB>();
        blob->size = 4;
        blob->data = arena.AllocBytes([0x01, 0x02, 0xab, 0xcd]);
        filter->filterCondition->conditionValue.byteBlob = blob;

        var decoded = NativeObjectDecoder.DecodeFilter(filter);
        NativeValueSnapshot value = decoded.Conditions.Single().Value;
        Equal("0102abcd", value.BlobHex, "native blob hex");
        Assert(value.IsDecoded && value.ScalarValue is null, "blob condition should be explicitly decoded without a scalar alias");

        arena.FreeCurrentBatch();
        Equal("0102abcd", value.BlobHex, "copied native blob after native memory release");
    }

    private static void DecoderBoundaries()
    {
        var nullProvider = NativeObjectDecoder.DecodeProvider(null);
        Assert(!nullProvider.IsComplete && nullProvider.Issues.Any(issue => issue.Code == SnapshotIssueCode.InvalidNativePointer), "null provider pointer");

        using var arena = new FixtureArena();
        arena.BeginBatch();
        var provider = arena.Alloc<FWPM_PROVIDER0>();
        provider->providerKey = Guid.NewGuid();
        provider->providerData.size = NativeObjectDecoder.MaxBlobBytes + 1;
        var decodedProvider = NativeObjectDecoder.DecodeProvider(provider);
        Assert(decodedProvider.Issues.Any(issue => issue.Code == SnapshotIssueCode.BlobTooLarge), "oversized provider data");

        var malformedFilter = arena.Alloc<FWPM_FILTER0>();
        malformedFilter->filterKey = Guid.NewGuid();
        malformedFilter->providerData.size = 0;
        malformedFilter->numFilterConditions = 1;
        malformedFilter->filterCondition = null;
        var decodedFilter = NativeObjectDecoder.DecodeFilter(malformedFilter);
        Assert(decodedFilter.Issues.Any(issue => issue.Code == SnapshotIssueCode.InvalidConditionArray), "nonzero count with null conditions");
        Assert(!decodedFilter.IsComplete, "malformed array cannot be complete");
        arena.FreeCurrentBatch();

        arena.BeginBatch();
        var unterminated = arena.Alloc<FWPM_PROVIDER0>();
        unterminated->providerKey = Guid.NewGuid();
        unterminated->displayData.name = arena.AllocUnterminatedString(NativeObjectDecoder.MaxStringCharacters);
        unterminated->providerData.size = 0;
        var decodedUnterminated = NativeObjectDecoder.DecodeProvider(unterminated);
        Assert(decodedUnterminated.Issues.Any(issue => issue.Code == SnapshotIssueCode.UnterminatedString), "unterminated bounded string");
        arena.FreeCurrentBatch();
    }

    private static void ReaderCleanupOnSuccess()
    {
        var api = new FixtureWfpApi();
        var snapshot = new WfpNativeReadbackReader(api).ReadSnapshot();
        Assert(snapshot.Providers.Count == 1 && snapshot.Sublayers.Count == 1 && snapshot.Layers.Count == 1 && snapshot.Filters.Count == 1 && snapshot.Callouts.Count == 1 && snapshot.ProviderContexts.Count == 1, "all object families returned");
        Assert(!snapshot.IsComplete, "prototype snapshot must remain incomplete");
        Equal(6, api.DestroyedEnumHandles, "destroyed enum handles");
        Equal(6, api.FreedBatches, "freed BFE-style batches");
        Equal(6, api.FreedSecurityDescriptors, "freed BFE security descriptors");
        Equal(0, api.Arena.OutstandingAllocations, "outstanding fixture allocations");
        Assert(api.EngineDisposed, "engine handle closed");
        Equal(1, api.CommitCount, "read transaction committed");
        Equal(0, api.AbortCount, "successful transaction not aborted");
        AssertReadOnlyList(snapshot.Providers, "snapshot providers");
        AssertReadOnlyList(snapshot.Sublayers, "snapshot sublayers");
        AssertReadOnlyList(snapshot.Layers, "snapshot layers");
        AssertReadOnlyList(snapshot.Filters, "snapshot filters");
        AssertReadOnlyList(snapshot.Callouts, "snapshot callouts");
        AssertReadOnlyList(snapshot.ProviderContexts, "snapshot provider contexts");
        AssertReadOnlyList(snapshot.Issues, "snapshot issues");
    }

    private static void WindowsApiUsesWinNtAuthentication()
    {
        uint? observedAuthenticationService = null;
        var api = new WindowsWfpApi(authenticationService =>
        {
            observedAuthenticationService = authenticationService;
            return (0U, (SafeHandle?)new FixtureSafeHandle(10, () => true));
        });

        Equal(0U, api.OpenEngine(out var engine), "injected engine-open result");
        Equal<uint?>(10U, observedAuthenticationService, "FwpmEngineOpen0 authentication service");
        Assert(engine is not null && !engine.IsInvalid, "injected engine handle should be returned");
        engine!.Dispose();
    }

    private static void ReaderPagingCapUsesSentinelPage()
    {
        FWPM_PROVIDER0* entry = null;
        FWPM_PROVIDER0** entries = &entry;
        var exactCapIssues = new List<SnapshotIssue>();
        bool done;
        Assert(
            WfpNativeReadbackReader.ValidateBatch(
                entries,
                WfpReadbackLimits.PageSize,
                WfpReadbackLimits.MaxObjects - (int)WfpReadbackLimits.PageSize,
                "provider",
                exactCapIssues,
                out done),
            "a full page that reaches exactly MaxObjects should be accepted");
        Assert(!done, "a full page at the cap must request one bounded sentinel page");
        Assert(exactCapIssues.Count == 0, "the exact cap should not produce a limit issue");

        var sentinelIssues = new List<SnapshotIssue>();
        Assert(
            WfpNativeReadbackReader.ValidateBatch<FWPM_PROVIDER0>(null, 0, WfpReadbackLimits.MaxObjects, "provider", sentinelIssues, out done),
            "an empty sentinel page should establish that the object count is exactly MaxObjects");
        Assert(done, "the empty sentinel page should finish enumeration");
        Assert(sentinelIssues.Count == 0, "an empty sentinel page should not produce a limit issue");

        var excessIssues = new List<SnapshotIssue>();
        Assert(
            !WfpNativeReadbackReader.ValidateBatch(entries, 1, WfpReadbackLimits.MaxObjects, "provider", excessIssues, out done),
            "one additional object after MaxObjects should be rejected");
        Assert(excessIssues.Any(issue => issue.Code == SnapshotIssueCode.EnumerationLimitReached), "the extra object should report the enumeration cap");
    }

    private static void ReaderReadsSecurityDescriptors()
    {
        var api = new FixtureWfpApi();
        var snapshot = new WfpNativeReadbackReader(api).ReadSnapshot();
        Assert(snapshot.Providers.Single().SecurityDescriptor is not null, "provider descriptor should be attached");
        Assert(snapshot.Sublayers.Single().SecurityDescriptor is not null, "sublayer descriptor should be attached");
        Assert(snapshot.Layers.Single().SecurityDescriptor is not null, "layer descriptor should be attached");
        Assert(snapshot.Filters.Single().SecurityDescriptor is not null, "filter descriptor should be attached");
        Assert(snapshot.Callouts.Single().SecurityDescriptor is not null, "callout descriptor should be attached");
        Assert(snapshot.ProviderContexts.Single().SecurityDescriptor is not null, "provider-context descriptor should be attached");
        Assert(snapshot.Providers.Single().Issues.Any(issue => issue.Code == SnapshotIssueCode.SecurityDescriptorPolicyUnverified), "provider descriptor still needs policy comparison");
        Assert(snapshot.Layers.Single().Issues.Any(issue => issue.Code == SnapshotIssueCode.SecurityDescriptorPolicyUnverified), "layer descriptor still needs policy comparison");
        Assert(snapshot.Issues.Any(issue => issue.Code == SnapshotIssueCode.EnumerationCompletenessUnverified), "hidden-object enumeration remains unverified");
        Equal(6, api.SecurityInformationRequests.Count, "security information request count");
        Assert(api.SecurityInformationRequests.All(value => value == WfpSecurityInformation.OwnerGroupDacl), "only owner, group, and DACL information should be requested");
        Equal(6, api.FreedSecurityDescriptors, "each descriptor returned by WFP must be freed");
        Equal(0, api.OutstandingSecurityDescriptors, "security descriptor allocations after read");
    }

    private static void ReaderSecurityDescriptorFailureStaysIncomplete()
    {
        var api = new FixtureWfpApi { FailFilterSecurityDescriptor = true };
        var snapshot = new WfpNativeReadbackReader(api).ReadSnapshot();
        FilterSnapshot filter = snapshot.Filters.Single();
        Assert(filter.SecurityDescriptor is null, "failed descriptor must not be represented as observed");
        Assert(filter.Issues.Any(issue => issue.Code == SnapshotIssueCode.SecurityDescriptorNotNormalized), "failed descriptor must create an incomplete issue");
        Assert(!snapshot.IsComplete, "descriptor retrieval failure must not produce a complete snapshot");
        Equal(6, api.FreedSecurityDescriptors, "all returned descriptors must be freed even when the API reports failure");
        Equal(0, api.OutstandingSecurityDescriptors, "no descriptor allocation should leak after a failed read");
    }

    private static void ReaderLayerSecurityDescriptorFailureStaysIncomplete()
    {
        var api = new FixtureWfpApi { FailLayerSecurityDescriptor = true };
        var snapshot = new WfpNativeReadbackReader(api).ReadSnapshot();
        LayerSnapshot layer = snapshot.Layers.Single();
        Assert(layer.SecurityDescriptor is null, "failed layer descriptor must not be represented as observed");
        Assert(layer.Issues.Any(issue => issue.Code == SnapshotIssueCode.SecurityDescriptorNotNormalized), "failed layer descriptor must create an incomplete issue");
        Assert(!layer.IsComplete, "a layer without normalized ACL evidence must not be complete");
        Assert(!snapshot.IsComplete, "a layer descriptor failure must not produce a complete snapshot");
        Equal(6, api.FreedSecurityDescriptors, "all descriptors must be freed when the layer API returns owned memory with an error");
        Equal(0, api.OutstandingSecurityDescriptors, "no descriptor allocation should leak after layer read failure");
    }

    private static void ReaderResolvesCalloutReferences()
    {
        var api = new FixtureWfpApi { FilterReferencesCallout = true };
        var snapshot = new WfpNativeReadbackReader(api).ReadSnapshot();
        var callout = snapshot.Callouts.Single();
        var filter = snapshot.Filters.Single();
        Equal(api.CalloutKey, filter.CalloutKey, "filter callout reference");
        Equal(filter.LayerKey, callout.ApplicableLayer, "callout applicable layer");
        Assert(!snapshot.Issues.Any(issue => issue.Code == SnapshotIssueCode.ReferencedObjectNotIncluded), "enumerated callout reference must close");
        Assert(snapshot.Issues.Any(issue => issue.Code == SnapshotIssueCode.EnumerationCompletenessUnverified), "object visibility proof must remain open");
        Assert(callout.Issues.Any(issue => issue.Code == SnapshotIssueCode.SecurityDescriptorPolicyUnverified), "callout ACL must remain policy-unverified");
    }

    private static void ReaderRejectsInvalidCalloutReferences()
    {
        var danglingApi = new FixtureWfpApi { FilterReferencesCallout = true, UseMissingCalloutKey = true };
        var dangling = new WfpNativeReadbackReader(danglingApi).ReadSnapshot();
        Assert(dangling.Issues.Any(issue => issue.Code == SnapshotIssueCode.ReferencedObjectNotIncluded), "missing callout reference must remain incomplete");

        var mismatchApi = new FixtureWfpApi { FilterReferencesCallout = true, MismatchCalloutLayer = true };
        var mismatch = new WfpNativeReadbackReader(mismatchApi).ReadSnapshot();
        Assert(mismatch.Issues.Any(issue => issue.Code == SnapshotIssueCode.UnsupportedNativeValue && issue.ObjectKind == "filter"), "callout on a different layer must remain incomplete");
    }

    private static void ReaderRejectsDuplicateCalloutKeys()
    {
        var api = new FixtureWfpApi { DuplicateCalloutKey = true };
        var snapshot = new WfpNativeReadbackReader(api).ReadSnapshot();
        Assert(snapshot.Issues.Any(issue => issue.Code == SnapshotIssueCode.UnsupportedNativeValue && issue.ObjectKind == "callout"), "duplicate callout keys must keep the snapshot incomplete");
    }

    private static void ReaderResolvesSublayerReferences()
    {
        var defaultSublayer = new WfpNativeReadbackReader(new FixtureWfpApi()).ReadSnapshot();
        Assert(defaultSublayer.Filters.Single().SublayerKey == Guid.Empty, "fixture must preserve the null/default sublayer representation");
        Equal(defaultSublayer.Sublayers.Single().Key, defaultSublayer.Layers.Single().DefaultSublayerKey, "layer default sublayer key");
        Assert(!defaultSublayer.Issues.Any(issue => issue.Code == SnapshotIssueCode.ReferencedObjectNotIncluded), "the layer default sublayer must resolve to an enumerated sublayer");

        var explicitSublayer = new WfpNativeReadbackReader(new FixtureWfpApi { FilterReferencesSublayer = true }).ReadSnapshot();
        Equal(explicitSublayer.Sublayers.Single().Key, explicitSublayer.Filters.Single().SublayerKey, "explicit filter sublayer reference");
        Assert(!explicitSublayer.Issues.Any(issue => issue.Code == SnapshotIssueCode.ReferencedObjectNotIncluded), "enumerated explicit sublayer reference must close");
    }

    private static void ReaderRejectsInvalidLayerAndSublayerReferences()
    {
        var missingLayer = new WfpNativeReadbackReader(new FixtureWfpApi { FilterReferencesMissingLayer = true }).ReadSnapshot();
        Assert(missingLayer.Issues.Any(issue => issue.Code == SnapshotIssueCode.ReferencedObjectNotIncluded && issue.ObjectKind == "filter" && issue.Detail.Contains("layer", StringComparison.Ordinal)), "missing filter layer must remain incomplete");

        var missingDefault = new WfpNativeReadbackReader(new FixtureWfpApi { LayerReferencesMissingDefaultSublayer = true }).ReadSnapshot();
        Assert(missingDefault.Issues.Any(issue => issue.Code == SnapshotIssueCode.ReferencedObjectNotIncluded && issue.ObjectKind == "filter"), "missing layer default sublayer must remain incomplete");

        var missingExplicit = new WfpNativeReadbackReader(new FixtureWfpApi { FilterReferencesMissingSublayer = true }).ReadSnapshot();
        Assert(missingExplicit.Issues.Any(issue => issue.Code == SnapshotIssueCode.ReferencedObjectNotIncluded && issue.ObjectKind == "filter"), "missing explicit sublayer must remain incomplete");

        var duplicateLayer = new WfpNativeReadbackReader(new FixtureWfpApi { DuplicateLayerKey = true }).ReadSnapshot();
        Assert(duplicateLayer.Issues.Any(issue => issue.Code == SnapshotIssueCode.UnsupportedNativeValue && issue.ObjectKind == "layer"), "duplicate layer keys must remain incomplete");

        var duplicateSublayer = new WfpNativeReadbackReader(new FixtureWfpApi { DuplicateSublayerKey = true }).ReadSnapshot();
        Assert(duplicateSublayer.Issues.Any(issue => issue.Code == SnapshotIssueCode.UnsupportedNativeValue && issue.ObjectKind == "sublayer"), "duplicate sublayer keys must remain incomplete");
    }

    private static void ReaderLayerEnumerationFailureCleansUp()
    {
        var api = new FixtureWfpApi { FailLayerEnumeration = true };
        Throws<WfpReadbackException>(() => new WfpNativeReadbackReader(api).ReadSnapshot(), "layer enumeration failure");
        Equal(3, api.DestroyedEnumHandles, "provider, sublayer, and failed layer handles destroyed");
        Equal(3, api.FreedBatches, "failed layer page freed with earlier pages");
        Equal(2, api.FreedSecurityDescriptors, "only provider and sublayer descriptors read before layer failure freed");
        Equal(1, api.AbortCount, "failed layer enumeration aborts the read transaction");
        Assert(api.EngineDisposed, "engine closes after layer enumeration failure");
    }

    private static void ReaderResolvesProviderReferences()
    {
        var snapshot = new WfpNativeReadbackReader(new FixtureWfpApi { ReferenceProviderFromAllObjects = true }).ReadSnapshot();
        Assert(snapshot.Sublayers.Single().ProviderKey == snapshot.Providers.Single().Key, "sublayer provider reference");
        Assert(snapshot.Filters.Single().ProviderKey == snapshot.Providers.Single().Key, "filter provider reference");
        Assert(snapshot.Callouts.Single().ProviderKey == snapshot.Providers.Single().Key, "callout provider reference");
        Assert(snapshot.ProviderContexts.Single().ProviderKey == snapshot.Providers.Single().Key, "provider-context reference");
        Assert(!snapshot.Issues.Any(issue => issue.Code == SnapshotIssueCode.ReferencedObjectNotIncluded), "all returned provider references must close");

        var unassociated = new WfpNativeReadbackReader(new FixtureWfpApi()).ReadSnapshot();
        Assert(!unassociated.Issues.Any(issue => issue.Code == SnapshotIssueCode.ReferencedObjectNotIncluded), "null optional provider associations must be accepted");
    }

    private static void ReaderRejectsInvalidProviderReferences()
    {
        var dangling = new WfpNativeReadbackReader(new FixtureWfpApi
        {
            ReferenceProviderFromAllObjects = true,
            UseMissingProviderReference = true,
        }).ReadSnapshot();
        Assert(dangling.Issues.Count(issue => issue.Code == SnapshotIssueCode.ReferencedObjectNotIncluded) == 4, "each missing provider reference must be reported");

        var empty = new WfpNativeReadbackReader(new FixtureWfpApi
        {
            ReferenceProviderFromAllObjects = true,
            UseEmptyProviderReference = true,
        }).ReadSnapshot();
        Assert(empty.Issues.Count(issue => issue.Code == SnapshotIssueCode.UnsupportedNativeValue && issue.Detail.Contains("providerKey", StringComparison.Ordinal)) == 4, "each non-null empty provider reference must be rejected");
    }

    private static void ReaderRejectsDuplicateProviderKeys()
    {
        var snapshot = new WfpNativeReadbackReader(new FixtureWfpApi { DuplicateProviderKey = true }).ReadSnapshot();
        Assert(snapshot.Issues.Any(issue => issue.Code == SnapshotIssueCode.UnsupportedNativeValue && issue.ObjectKind == "provider"), "duplicate provider keys must remain incomplete");
    }

    private static void ReaderCalloutEnumerationFailureCleansUp()
    {
        var api = new FixtureWfpApi { FailCalloutEnumeration = true };
        Throws<WfpReadbackException>(() => new WfpNativeReadbackReader(api).ReadSnapshot(), "callout enumeration failure");
        Equal(4, api.DestroyedEnumHandles, "provider, sublayer, layer, and failed callout enum handles destroyed");
        Equal(4, api.FreedBatches, "failed callout page freed with earlier pages");
        Equal(3, api.FreedSecurityDescriptors, "provider, sublayer, and layer descriptors read before callout failure freed");
        Equal(0, api.OutstandingSecurityDescriptors, "no descriptor leaks after callout failure");
        Equal(1, api.AbortCount, "failed callout enumeration aborts the read transaction");
        Assert(api.EngineDisposed, "engine closes after callout enumeration failure");
    }

    private static void ReaderResolvesProviderContextReferences()
    {
        var api = new FixtureWfpApi { FilterReferencesCallout = true, FilterReferencesProviderContext = true, UseInspectionCalloutAction = true };
        var snapshot = new WfpNativeReadbackReader(api).ReadSnapshot();
        var context = snapshot.ProviderContexts.Single();
        var filter = snapshot.Filters.Single();
        Equal(api.ProviderContextKey, filter.ProviderContextKey, "filter provider-context reference");
        Equal((ulong)44, context.ProviderContextId, "BFE provider-context id");
        Equal("010203", context.GeneralDataHex, "general provider-context data");
        Assert(!snapshot.Issues.Any(issue => issue.Code == SnapshotIssueCode.ReferencedObjectNotIncluded), "enumerated provider-context reference must close");
        Assert(snapshot.Issues.Any(issue => issue.Code == SnapshotIssueCode.EnumerationCompletenessUnverified), "object visibility proof must remain open");
        Assert(context.Issues.Any(issue => issue.Code == SnapshotIssueCode.SecurityDescriptorPolicyUnverified), "provider-context ACL must remain policy-unverified");
        Assert(!context.Issues.Any(issue => issue.Code == SnapshotIssueCode.ProviderContextPayloadNotNormalized), "general context payload should be decoded");
    }

    private static void ReaderDecodesClassifyOptionsProviderContext()
    {
        var api = new FixtureWfpApi { ProviderContextType = FWPM_PROVIDER_CONTEXT_TYPE.FWPM_CLASSIFY_OPTIONS_CONTEXT };
        var snapshot = new WfpNativeReadbackReader(api).ReadSnapshot();
        var context = snapshot.ProviderContexts.Single();
        Equal(2, context.ClassifyOptions.Count, "classify option count");
        Equal("30", context.ClassifyOptions[0].Value.ScalarValue, "first classify option value");
        Equal("60", context.ClassifyOptions[1].Value.ScalarValue, "second classify option value");
        Assert(!context.Issues.Any(issue => issue.Code == SnapshotIssueCode.ProviderContextPayloadNotNormalized), "known classify options should be decoded");
    }

    private static void ReaderDecodesScalarClassifyOptions()
    {
        var multicast = new WfpNativeReadbackReader(new FixtureWfpApi
        {
            ProviderContextType = FWPM_PROVIDER_CONTEXT_TYPE.FWPM_CLASSIFY_OPTIONS_CONTEXT,
            FirstClassifyOptionType = FWP_CLASSIFY_OPTION_TYPE.FWP_CLASSIFY_OPTION_MULTICAST_STATE,
            FirstClassifyOptionValue = 2,
        }).ReadSnapshot().ProviderContexts.Single();
        Equal("2", multicast.ClassifyOptions[0].Value.ScalarValue, "global multicast state option value");
        Assert(!multicast.Issues.Any(issue => issue.Code == SnapshotIssueCode.UnsupportedNativeValue), "documented multicast state value should be decoded");

        var looseSource = new WfpNativeReadbackReader(new FixtureWfpApi
        {
            ProviderContextType = FWPM_PROVIDER_CONTEXT_TYPE.FWPM_CLASSIFY_OPTIONS_CONTEXT,
            FirstClassifyOptionType = FWP_CLASSIFY_OPTION_TYPE.FWP_CLASSIFY_OPTION_LOOSE_SOURCE_MAPPING,
            FirstClassifyOptionValue = 1,
        }).ReadSnapshot().ProviderContexts.Single();
        Equal("1", looseSource.ClassifyOptions[0].Value.ScalarValue, "enabled loose-source mapping option value");
        Assert(!looseSource.Issues.Any(issue => issue.Code == SnapshotIssueCode.UnsupportedNativeValue), "documented loose-source value should be decoded");

        var invalid = new WfpNativeReadbackReader(new FixtureWfpApi
        {
            ProviderContextType = FWPM_PROVIDER_CONTEXT_TYPE.FWPM_CLASSIFY_OPTIONS_CONTEXT,
            FirstClassifyOptionType = FWP_CLASSIFY_OPTION_TYPE.FWP_CLASSIFY_OPTION_MULTICAST_STATE,
            FirstClassifyOptionValue = 3,
        }).ReadSnapshot().ProviderContexts.Single();
        Assert(invalid.Issues.Any(issue => issue.Code == SnapshotIssueCode.UnsupportedNativeValue), "out-of-enum multicast state must fail closed");

        var invalidLooseSource = new WfpNativeReadbackReader(new FixtureWfpApi
        {
            ProviderContextType = FWPM_PROVIDER_CONTEXT_TYPE.FWPM_CLASSIFY_OPTIONS_CONTEXT,
            FirstClassifyOptionType = FWP_CLASSIFY_OPTION_TYPE.FWP_CLASSIFY_OPTION_LOOSE_SOURCE_MAPPING,
            FirstClassifyOptionValue = 2,
        }).ReadSnapshot().ProviderContexts.Single();
        Assert(invalidLooseSource.Issues.Any(issue => issue.Code == SnapshotIssueCode.UnsupportedNativeValue), "out-of-enum loose-source value must fail closed");
    }

    private static void ReaderRejectsMalformedClassifyOptionsProviderContext()
    {
        var nullStructure = new WfpNativeReadbackReader(new FixtureWfpApi
        {
            ProviderContextType = FWPM_PROVIDER_CONTEXT_TYPE.FWPM_CLASSIFY_OPTIONS_CONTEXT,
            NullClassifyOptionsStructure = true,
        }).ReadSnapshot();
        Assert(nullStructure.ProviderContexts.Single().Issues.Any(issue => issue.Code == SnapshotIssueCode.ProviderContextPayloadNotNormalized), "null classify-options structure must fail closed");

        var nullArray = new WfpNativeReadbackReader(new FixtureWfpApi
        {
            ProviderContextType = FWPM_PROVIDER_CONTEXT_TYPE.FWPM_CLASSIFY_OPTIONS_CONTEXT,
            NullClassifyOptionsArray = true,
        }).ReadSnapshot();
        Assert(nullArray.ProviderContexts.Single().Issues.Any(issue => issue.Code == SnapshotIssueCode.InvalidNativePointer), "nonzero option count with null array must fail closed");

        var oversized = new WfpNativeReadbackReader(new FixtureWfpApi
        {
            ProviderContextType = FWPM_PROVIDER_CONTEXT_TYPE.FWPM_CLASSIFY_OPTIONS_CONTEXT,
            OversizedClassifyOptionsArray = true,
        }).ReadSnapshot();
        Assert(oversized.ProviderContexts.Single().Issues.Any(issue => issue.Code == SnapshotIssueCode.NativeCountOutOfRange), "option count above the bound must fail closed");

        var unknown = new WfpNativeReadbackReader(new FixtureWfpApi
        {
            ProviderContextType = FWPM_PROVIDER_CONTEXT_TYPE.FWPM_CLASSIFY_OPTIONS_CONTEXT,
            UnknownClassifyOption = true,
        }).ReadSnapshot();
        Assert(unknown.ProviderContexts.Single().Issues.Any(issue => issue.Code == SnapshotIssueCode.UnsupportedNativeValue), "unknown option type must fail closed");

        var unsupportedKnownType = new WfpNativeReadbackReader(new FixtureWfpApi
        {
            ProviderContextType = FWPM_PROVIDER_CONTEXT_TYPE.FWPM_CLASSIFY_OPTIONS_CONTEXT,
            UnsupportedClassifyOption = true,
        }).ReadSnapshot();
        Assert(unsupportedKnownType.ProviderContexts.Single().Issues.Any(issue => issue.Code == SnapshotIssueCode.UnsupportedNativeValue), "recognized but unnormalized option type must fail closed");

        var wrongValueType = new WfpNativeReadbackReader(new FixtureWfpApi
        {
            ProviderContextType = FWPM_PROVIDER_CONTEXT_TYPE.FWPM_CLASSIFY_OPTIONS_CONTEXT,
            WrongClassifyOptionValueType = true,
        }).ReadSnapshot();
        Assert(wrongValueType.ProviderContexts.Single().Issues.Any(issue => issue.Code == SnapshotIssueCode.UnsupportedNativeValue), "lifetime option with a non-UINT32 value must fail closed");

        var duplicate = new WfpNativeReadbackReader(new FixtureWfpApi
        {
            ProviderContextType = FWPM_PROVIDER_CONTEXT_TYPE.FWPM_CLASSIFY_OPTIONS_CONTEXT,
            DuplicateClassifyOptionType = true,
        }).ReadSnapshot();
        Assert(duplicate.ProviderContexts.Single().Issues.Any(issue => issue.Code == SnapshotIssueCode.UnsupportedNativeValue), "duplicate option types must fail closed");
    }

    private static void ReaderRejectsInvalidProviderContextReferences()
    {
        var danglingApi = new FixtureWfpApi { FilterReferencesCallout = true, FilterReferencesProviderContext = true, UseMissingProviderContextKey = true };
        var dangling = new WfpNativeReadbackReader(danglingApi).ReadSnapshot();
        Assert(dangling.Issues.Any(issue => issue.Code == SnapshotIssueCode.ReferencedObjectNotIncluded && issue.ObjectKind == "filter"), "missing provider-context reference must remain incomplete");

        var inconsistentApi = new FixtureWfpApi { FilterHasUnflaggedProviderContextKey = true };
        var inconsistent = new WfpNativeReadbackReader(inconsistentApi).ReadSnapshot();
        Assert(inconsistent.Filters.Single().Issues.Any(issue => issue.Code == SnapshotIssueCode.UnsupportedNativeValue), "context key without HAS_PROVIDER_CONTEXT must remain incomplete");
    }

    private static void ReaderRejectsUnsupportedProviderContextPayloads()
    {
        var unknown = new WfpNativeReadbackReader(new FixtureWfpApi { ProviderContextType = (FWPM_PROVIDER_CONTEXT_TYPE)999 }).ReadSnapshot();
        Assert(unknown.ProviderContexts.Single().Issues.Any(issue => issue.Code == SnapshotIssueCode.ProviderContextPayloadNotNormalized), "unknown context type must fail closed");

        var unsupported = new WfpNativeReadbackReader(new FixtureWfpApi { ProviderContextType = FWPM_PROVIDER_CONTEXT_TYPE.FWPM_IPSEC_KEYING_CONTEXT }).ReadSnapshot();
        Assert(unsupported.ProviderContexts.Single().Issues.Any(issue => issue.Code == SnapshotIssueCode.ProviderContextPayloadNotNormalized), "unimplemented IPsec policy union must fail closed");

        var malformed = new WfpNativeReadbackReader(new FixtureWfpApi { MalformedProviderContextDataBuffer = true }).ReadSnapshot();
        Assert(malformed.ProviderContexts.Single().Issues.Any(issue => issue.Code == SnapshotIssueCode.BlobPointerMissing), "general context with a nonzero blob and null bytes must fail closed");
    }

    private static void ReaderRejectsDuplicateProviderContextKeys()
    {
        var snapshot = new WfpNativeReadbackReader(new FixtureWfpApi { DuplicateProviderContextKey = true }).ReadSnapshot();
        Assert(snapshot.Issues.Any(issue => issue.Code == SnapshotIssueCode.UnsupportedNativeValue && issue.ObjectKind == "provider-context"), "duplicate provider-context keys must keep the snapshot incomplete");

        var emptyApi = new FixtureWfpApi { EmptyProviderContextKey = true };
        var emptySnapshot = new WfpNativeReadbackReader(emptyApi).ReadSnapshot();
        var emptyContext = emptySnapshot.ProviderContexts.Single();
        Assert(emptyContext.Issues.Any(issue => issue.Code == SnapshotIssueCode.UnsupportedNativeValue), "empty provider-context key must remain incomplete");
        Assert(emptyContext.SecurityDescriptor is null, "empty object key must not attach the container descriptor as object evidence");
        Equal(5, emptyApi.SecurityInformationRequests.Count, "empty provider-context key must skip object descriptor lookup");
    }

    private static void ReaderProviderContextEnumerationFailureCleansUp()
    {
        var api = new FixtureWfpApi { FailProviderContextEnumeration = true };
        Throws<WfpReadbackException>(() => new WfpNativeReadbackReader(api).ReadSnapshot(), "provider-context enumeration failure");
        Equal(5, api.DestroyedEnumHandles, "provider, sublayer, layer, callout, and failed provider-context handles destroyed before filter enumeration");
        Equal(5, api.FreedBatches, "failed provider-context page freed with earlier pages");
        Equal(4, api.FreedSecurityDescriptors, "descriptors read before provider-context failure freed");
        Equal(0, api.OutstandingSecurityDescriptors, "no descriptor leaks after provider-context failure");
        Equal(1, api.AbortCount, "failed provider-context enumeration aborts the read transaction");
        Assert(api.EngineDisposed, "engine closes after provider-context enumeration failure");
    }

    private static void ReaderCleanupOnApiFailure()
    {
        var api = new FixtureWfpApi { FailFilterEnumeration = true };
        Throws<WfpReadbackException>(() => new WfpNativeReadbackReader(api).ReadSnapshot(), "native enumeration failure");
        Equal(6, api.DestroyedEnumHandles, "enum handles destroyed after failure");
        Equal(6, api.FreedBatches, "returned memory freed after failure");
        Equal(5, api.FreedSecurityDescriptors, "descriptors fetched before enumeration failure freed");
        Equal(0, api.OutstandingSecurityDescriptors, "no security descriptor leaks after enumeration failure");
        Equal(0, api.Arena.OutstandingAllocations, "fixture allocations after failure");
        Assert(api.EngineDisposed, "engine handle closed after failure");
        Equal(0, api.CommitCount, "failed transaction not committed");
        Equal(1, api.AbortCount, "failed transaction aborted");
    }

    private static void ReaderDestroyFailureStaysIncomplete()
    {
        var api = new FixtureWfpApi { FailFilterDestroyOnce = true };
        var snapshot = new WfpNativeReadbackReader(api).ReadSnapshot();
        Assert(!snapshot.IsComplete, "failed enum destroy must keep snapshot incomplete");
        Assert(snapshot.Issues.Any(issue => issue.Code == SnapshotIssueCode.NativeApiFailure), "destroy failure issue must be recorded");
        Equal(6, api.DestroyedEnumHandles, "all enum handles eventually released");
        Equal(1, api.SafeHandleFallbackCleanupCount, "SafeHandle fallback cleanup used for failed destroy");
        Equal(7, api.DestroyAttempts, "explicit destroy plus fallback retry");
        Equal(6, api.FreedBatches, "all returned BFE-style arrays freed");
        Equal(6, api.FreedSecurityDescriptors, "all security descriptors freed after destroy failure");
        Equal(0, api.OutstandingSecurityDescriptors, "no security descriptor leaks after destroy failure");
        Equal(0, api.Arena.OutstandingAllocations, "fixture allocations after destroy failure");
        Assert(api.EngineDisposed, "engine handle closed after destroy failure");
    }

    private static void ReaderRejectsNullEnumHandle()
    {
        var api = new FixtureWfpApi { ReturnNullProviderEnumHandle = true };
        Throws<WfpReadbackException>(() => new WfpNativeReadbackReader(api).ReadSnapshot(), "null enum handle");
        Equal(0, api.DestroyedEnumHandles, "no destroy on absent enum handle");
        Assert(api.EngineDisposed, "engine handle closed after null enum handle");
        Equal(1, api.AbortCount, "transaction aborted after null enum handle");
    }

    private static void AssertReadOnly(IReadOnlyList<byte> bytes, string label)
    {
        if (bytes is IList<byte> list)
        {
            Assert(list.IsReadOnly, $"{label} should be exposed as read-only");
            Throws<NotSupportedException>(() => list[0] = 0xff, $"{label} mutation");
        }
    }

    private static void SnapshotCollectionsAreImmutable()
    {
        Assert(typeof(ProviderSnapshot).GetConstructors().Length == 0, "provider snapshots must only be constructible inside the reader assembly");
        Assert(typeof(SublayerSnapshot).GetConstructors().Length == 0, "sublayer snapshots must only be constructible inside the reader assembly");
        Assert(typeof(LayerSnapshot).GetConstructors().Length == 0, "layer snapshots must only be constructible inside the reader assembly");
        Assert(typeof(FilterSnapshot).GetConstructors().Length == 0, "filter snapshots must only be constructible inside the reader assembly");
        Assert(typeof(CalloutSnapshot).GetConstructors().Length == 0, "callout snapshots must only be constructible inside the reader assembly");
        Assert(typeof(ProviderContextSnapshot).GetConstructors().Length == 0, "provider-context snapshots must only be constructible inside the reader assembly");
        Assert(typeof(WfpSnapshot).GetConstructors().Length == 0, "WFP snapshots must only be constructible inside the reader assembly");
    }

    private static void AssertReadOnlyList<T>(IReadOnlyList<T> values, string label)
    {
        if (values is IList<T> list)
        {
            Assert(list.IsReadOnly, $"{label} should be read-only");
            if (list.Count != 0)
            {
                Throws<NotSupportedException>(() => list[0] = default!, $"{label} mutation");
            }
        }
    }

    private static void SequenceEqual<T>(IReadOnlyList<T> expected, IReadOnlyList<T> actual, string label)
    {
        Assert(expected.SequenceEqual(actual), $"{label}: expected [{string.Join(",", expected)}], actual [{string.Join(",", actual)}]");
    }

    private static void Equal<T>(T expected, T actual, string label)
    {
        Assert(EqualityComparer<T>.Default.Equals(expected, actual), $"{label}: expected {expected}, actual {actual}");
    }

    private static void Assert(bool condition, string message)
    {
        if (!condition)
        {
            throw new InvalidOperationException(message);
        }
    }

    private static void Throws<TException>(Action action, string label) where TException : Exception
    {
        try
        {
            action();
        }
        catch (TException)
        {
            return;
        }
        throw new InvalidOperationException($"Expected {typeof(TException).Name}: {label}");
    }
}

internal sealed unsafe class FixtureArena : IDisposable
{
    private readonly Dictionary<nint, List<nint>> batches = [];
    private List<nint>? currentBatch;

    internal int OutstandingAllocations => this.batches.Values.Sum(allocations => allocations.Count);

    internal void BeginBatch() => this.currentBatch = [];

    internal T* Alloc<T>() where T : unmanaged
    {
        var pointer = (T*)NativeMemory.AllocZeroed((nuint)sizeof(T));
        this.Track(pointer);
        return pointer;
    }

    internal T* AllocArray<T>(int length) where T : unmanaged
    {
        if (length <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(length));
        }
        var pointer = (T*)NativeMemory.AllocZeroed(checked((nuint)(sizeof(T) * length)));
        this.Track(pointer);
        return pointer;
    }

    internal byte* AllocBytes(byte[] bytes)
    {
        var pointer = (byte*)NativeMemory.Alloc((nuint)bytes.Length);
        bytes.CopyTo(new Span<byte>(pointer, bytes.Length));
        this.Track(pointer);
        return pointer;
    }

    internal char* AllocUtf16(string value)
    {
        var pointer = (char*)NativeMemory.AllocZeroed((nuint)((value.Length + 1) * sizeof(char)));
        value.AsSpan().CopyTo(new Span<char>(pointer, value.Length));
        this.Track(pointer);
        return pointer;
    }

    internal char* AllocUnterminatedString(int length)
    {
        var pointer = (char*)NativeMemory.Alloc((nuint)(length * sizeof(char)));
        new Span<char>(pointer, length).Fill('x');
        this.Track(pointer);
        return pointer;
    }

    internal void* AllocBytes(nuint size)
    {
        var pointer = NativeMemory.AllocZeroed(size);
        this.Track(pointer);
        return pointer;
    }

    internal void FreeCurrentBatch()
    {
        if (this.currentBatch is null)
        {
            return;
        }
        foreach (var allocation in this.currentBatch)
        {
            NativeMemory.Free((void*)allocation);
        }
        this.currentBatch.Clear();
        this.currentBatch = null;
    }

    internal void FreeBatch(void** allocation)
    {
        if (allocation is null || *allocation is null)
        {
            return;
        }
        var key = (nint)(*allocation);
        if (!this.batches.Remove(key, out var ownedAllocations))
        {
            throw new InvalidOperationException("Fixture attempted to free an unknown native batch.");
        }
        foreach (var owned in ownedAllocations)
        {
            NativeMemory.Free((void*)owned);
        }
        *allocation = null;
    }

    private void Track(void* pointer)
    {
        if (this.currentBatch is null)
        {
            throw new InvalidOperationException("BeginBatch must precede fixture allocations.");
        }
        this.currentBatch.Add((nint)pointer);
    }

    internal void RegisterCurrentBatch(void* returnedArray)
    {
        if (this.currentBatch is null || returnedArray is null)
        {
            throw new InvalidOperationException("Cannot register an empty fixture batch.");
        }
        this.batches.Add((nint)returnedArray, this.currentBatch);
        this.currentBatch = null;
    }

    public void Dispose()
    {
        if (this.currentBatch is not null)
        {
            foreach (var allocation in this.currentBatch)
            {
                NativeMemory.Free((void*)allocation);
            }
            this.currentBatch.Clear();
            this.currentBatch = null;
        }
        foreach (var allocations in this.batches.Values)
        {
            foreach (var allocation in allocations)
            {
                NativeMemory.Free((void*)allocation);
            }
        }
        this.batches.Clear();
    }
}

internal sealed unsafe class FixtureWfpApi : IReadOnlyWfpApi
{
    private const uint Failure = 0x80070005;
    private readonly Dictionary<int, int> enumCalls = [];
    private readonly Dictionary<nint, uint> securityDescriptorLengths = [];
    internal List<uint> SecurityInformationRequests { get; } = [];
    internal Guid ProviderKey { get; } = Guid.NewGuid();
    internal Guid SublayerKey { get; } = Guid.NewGuid();
    internal Guid CalloutKey { get; } = Guid.NewGuid();
    internal Guid ProviderContextKey { get; } = Guid.NewGuid();
    internal Guid FixtureLayerKey { get; } = Guid.NewGuid();
    private int nextEnumId = 100;
    private bool filterDestroyFailureObserved;

    internal FixtureArena Arena { get; } = new();
    internal bool FailFilterEnumeration { get; init; }
    internal bool FailFilterSecurityDescriptor { get; init; }
    internal bool ReturnNullProviderEnumHandle { get; init; }
    internal bool FailFilterDestroyOnce { get; init; }
    internal bool FilterReferencesCallout { get; init; }
    internal bool UseMissingCalloutKey { get; init; }
    internal bool MismatchCalloutLayer { get; init; }
    internal bool DuplicateCalloutKey { get; init; }
    internal bool FilterReferencesSublayer { get; init; }
    internal bool FilterReferencesMissingSublayer { get; init; }
    internal bool FilterReferencesMissingLayer { get; init; }
    internal bool LayerReferencesMissingDefaultSublayer { get; init; }
    internal bool DuplicateLayerKey { get; init; }
    internal bool DuplicateSublayerKey { get; init; }
    internal bool FailLayerEnumeration { get; init; }
    internal bool FailLayerSecurityDescriptor { get; init; }
    internal bool ReferenceProviderFromAllObjects { get; init; }
    internal bool UseMissingProviderReference { get; init; }
    internal bool UseEmptyProviderReference { get; init; }
    internal bool DuplicateProviderKey { get; init; }
    internal bool FailCalloutEnumeration { get; init; }
    internal bool FilterReferencesProviderContext { get; init; }
    internal bool UseInspectionCalloutAction { get; init; }
    internal bool FilterHasUnflaggedProviderContextKey { get; init; }
    internal bool UseMissingProviderContextKey { get; init; }
    internal bool FailProviderContextEnumeration { get; init; }
    internal bool DuplicateProviderContextKey { get; init; }
    internal bool EmptyProviderContextKey { get; init; }
    internal bool MalformedProviderContextDataBuffer { get; init; }
    internal bool NullClassifyOptionsStructure { get; init; }
    internal bool NullClassifyOptionsArray { get; init; }
    internal bool OversizedClassifyOptionsArray { get; init; }
    internal bool UnknownClassifyOption { get; init; }
    internal bool UnsupportedClassifyOption { get; init; }
    internal bool DuplicateClassifyOptionType { get; init; }
    internal bool WrongClassifyOptionValueType { get; init; }
    internal FWP_CLASSIFY_OPTION_TYPE FirstClassifyOptionType { get; init; } = FWP_CLASSIFY_OPTION_TYPE.FWP_CLASSIFY_OPTION_UNICAST_LIFETIME;
    internal uint FirstClassifyOptionValue { get; init; } = 30;
    internal FWPM_PROVIDER_CONTEXT_TYPE ProviderContextType { get; init; } = FWPM_PROVIDER_CONTEXT_TYPE.FWPM_GENERAL_CONTEXT;
    internal int DestroyedEnumHandles { get; private set; }
    internal int DestroyAttempts { get; private set; }
    internal int SafeHandleFallbackCleanupCount { get; private set; }
    internal int FreedBatches { get; private set; }
    internal int FreedSecurityDescriptors { get; private set; }
    internal int OutstandingSecurityDescriptors => this.securityDescriptorLengths.Count;
    internal int CommitCount { get; private set; }
    internal int AbortCount { get; private set; }
    internal bool EngineDisposed { get; private set; }

    public uint OpenEngine(out SafeHandle? engine)
    {
        engine = new FixtureSafeHandle(10, () =>
        {
            this.EngineDisposed = true;
            return true;
        });
        return 0;
    }

    public uint BeginReadTransaction(SafeHandle engine) => 0;

    public uint CommitReadTransaction(SafeHandle engine)
    {
        this.CommitCount++;
        return 0;
    }

    public uint AbortReadTransaction(SafeHandle engine)
    {
        this.AbortCount++;
        return 0;
    }

    public uint CreateProviderEnumHandle(SafeHandle engine, out SafeHandle? enumHandle)
    {
        enumHandle = this.ReturnNullProviderEnumHandle ? new FixtureSafeHandle(0, () => true) : this.NewEnumHandle("provider");
        return 0;
    }

    public uint EnumerateProviders(SafeHandle engine, SafeHandle enumHandle, uint requested, out FWPM_PROVIDER0** entries, out uint count)
    {
        var id = (int)enumHandle.DangerousGetHandle();
        if (this.NextCall(id))
        {
            entries = this.CreateProviderBatch(out count);
        }
        else
        {
            entries = null;
            count = 0;
        }
        return 0;
    }

    public uint DestroyProviderEnumHandle(SafeHandle engine, SafeHandle enumHandle) => this.Destroy(enumHandle);

    public uint GetProviderSecurityDescriptor(SafeHandle engine, Guid key, uint securityInformation, out IntPtr descriptor)
    {
        this.SecurityInformationRequests.Add(securityInformation);
        return this.AllocateSecurityDescriptor(out descriptor);
    }

    public uint CreateSublayerEnumHandle(SafeHandle engine, out SafeHandle? enumHandle)
    {
        enumHandle = this.NewEnumHandle("sublayer");
        return 0;
    }

    public uint EnumerateSublayers(SafeHandle engine, SafeHandle enumHandle, uint requested, out FWPM_SUBLAYER0** entries, out uint count)
    {
        if (this.NextCall((int)enumHandle.DangerousGetHandle()))
        {
            entries = this.CreateSublayerBatch(out count);
        }
        else
        {
            entries = null;
            count = 0;
        }
        return 0;
    }

    public uint DestroySublayerEnumHandle(SafeHandle engine, SafeHandle enumHandle) => this.Destroy(enumHandle);

    public uint GetSublayerSecurityDescriptor(SafeHandle engine, Guid key, uint securityInformation, out IntPtr descriptor)
    {
        this.SecurityInformationRequests.Add(securityInformation);
        return this.AllocateSecurityDescriptor(out descriptor);
    }

    public uint CreateLayerEnumHandle(SafeHandle engine, out SafeHandle? enumHandle)
    {
        enumHandle = this.NewEnumHandle("layer");
        return 0;
    }

    public uint EnumerateLayers(SafeHandle engine, SafeHandle enumHandle, uint requested, out FWPM_LAYER0** entries, out uint count)
    {
        if (this.FailLayerEnumeration)
        {
            entries = this.CreateLayerBatch(out count);
            return Failure;
        }
        if (this.NextCall((int)enumHandle.DangerousGetHandle()))
        {
            entries = this.CreateLayerBatch(out count);
        }
        else
        {
            entries = null;
            count = 0;
        }
        return 0;
    }

    public uint DestroyLayerEnumHandle(SafeHandle engine, SafeHandle enumHandle) => this.Destroy(enumHandle);

    public uint GetLayerSecurityDescriptor(SafeHandle engine, Guid key, uint securityInformation, out IntPtr descriptor)
    {
        this.SecurityInformationRequests.Add(securityInformation);
        uint result = this.AllocateSecurityDescriptor(out descriptor);
        return this.FailLayerSecurityDescriptor ? Failure : result;
    }

    public uint CreateFilterEnumHandle(SafeHandle engine, out SafeHandle? enumHandle)
    {
        enumHandle = this.NewEnumHandle("filter");
        return 0;
    }

    public uint EnumerateFilters(SafeHandle engine, SafeHandle enumHandle, uint requested, out FWPM_FILTER0** entries, out uint count)
    {
        if (this.FailFilterEnumeration)
        {
            entries = this.CreateFilterBatch(out count);
            return Failure;
        }
        if (this.NextCall((int)enumHandle.DangerousGetHandle()))
        {
            entries = this.CreateFilterBatch(out count);
            return 0;
        }
        entries = null;
        count = 0;
        return 0;
    }

    public uint DestroyFilterEnumHandle(SafeHandle engine, SafeHandle enumHandle) => this.Destroy(enumHandle);

    public uint GetFilterSecurityDescriptor(SafeHandle engine, Guid key, uint securityInformation, out IntPtr descriptor)
    {
        this.SecurityInformationRequests.Add(securityInformation);
        uint result = this.AllocateSecurityDescriptor(out descriptor);
        return this.FailFilterSecurityDescriptor ? Failure : result;
    }

    public uint CreateCalloutEnumHandle(SafeHandle engine, out SafeHandle? enumHandle)
    {
        enumHandle = this.NewEnumHandle("callout");
        return 0;
    }

    public uint EnumerateCallouts(SafeHandle engine, SafeHandle enumHandle, uint requested, out FWPM_CALLOUT0** entries, out uint count)
    {
        if (this.FailCalloutEnumeration)
        {
            entries = this.CreateCalloutBatch(out count);
            return Failure;
        }
        if (this.NextCall((int)enumHandle.DangerousGetHandle()))
        {
            entries = this.CreateCalloutBatch(out count);
        }
        else
        {
            entries = null;
            count = 0;
        }
        return 0;
    }

    public uint DestroyCalloutEnumHandle(SafeHandle engine, SafeHandle enumHandle) => this.Destroy(enumHandle);

    public uint GetCalloutSecurityDescriptor(SafeHandle engine, Guid key, uint securityInformation, out IntPtr descriptor)
    {
        this.SecurityInformationRequests.Add(securityInformation);
        return this.AllocateSecurityDescriptor(out descriptor);
    }

    public uint CreateProviderContextEnumHandle(SafeHandle engine, out SafeHandle? enumHandle)
    {
        enumHandle = this.NewEnumHandle("provider-context");
        return 0;
    }

    public uint EnumerateProviderContexts(SafeHandle engine, SafeHandle enumHandle, uint requested, out FWPM_PROVIDER_CONTEXT0** entries, out uint count)
    {
        if (this.FailProviderContextEnumeration)
        {
            entries = this.CreateProviderContextBatch(out count);
            return Failure;
        }
        if (this.NextCall((int)enumHandle.DangerousGetHandle()))
        {
            entries = this.CreateProviderContextBatch(out count);
        }
        else
        {
            entries = null;
            count = 0;
        }
        return 0;
    }

    public uint DestroyProviderContextEnumHandle(SafeHandle engine, SafeHandle enumHandle) => this.Destroy(enumHandle);

    public uint GetProviderContextSecurityDescriptor(SafeHandle engine, Guid key, uint securityInformation, out IntPtr descriptor)
    {
        this.SecurityInformationRequests.Add(securityInformation);
        return this.AllocateSecurityDescriptor(out descriptor);
    }

    public uint GetSecurityDescriptorLength(IntPtr descriptor) => this.securityDescriptorLengths.TryGetValue((nint)descriptor, out uint length) ? length : 0;

    public void FreeMemory(void** memory)
    {
        if (memory is not null && *memory is not null)
        {
            if (this.securityDescriptorLengths.Remove((nint)(*memory)))
            {
                Marshal.FreeHGlobal((IntPtr)(*memory));
                *memory = null;
                this.FreedSecurityDescriptors++;
                return;
            }
            this.Arena.FreeBatch(memory);
            this.FreedBatches++;
        }
    }

    private uint AllocateSecurityDescriptor(out IntPtr descriptor)
    {
        byte[] bytes = Harness.CreateFixtureSecurityDescriptor(canonical: true);
        descriptor = Marshal.AllocHGlobal(bytes.Length);
        Marshal.Copy(bytes, 0, descriptor, bytes.Length);
        this.securityDescriptorLengths.Add((nint)descriptor, (uint)bytes.Length);
        return 0;
    }

    private SafeHandle NewEnumHandle(string kind)
    {
        this.nextEnumId++;
        return new FixtureSafeHandle(this.nextEnumId, () =>
        {
            this.SafeHandleFallbackCleanupCount++;
            this.DestroyAttempts++;
            this.DestroyedEnumHandles++;
            return true;
        });
    }

    private bool NextCall(int enumId)
    {
        this.enumCalls.TryGetValue(enumId, out var callIndex);
        this.enumCalls[enumId] = callIndex + 1;
        return callIndex == 0;
    }

    private uint Destroy(SafeHandle enumHandle)
    {
        this.DestroyAttempts++;
        if (this.FailFilterDestroyOnce && !this.filterDestroyFailureObserved && this.DestroyedEnumHandles == 5)
        {
            this.filterDestroyFailureObserved = true;
            return Failure;
        }
        this.DestroyedEnumHandles++;
        return 0;
    }

    private FWPM_PROVIDER0** CreateProviderBatch(out uint count)
    {
        this.Arena.BeginBatch();
        count = this.DuplicateProviderKey ? 2U : 1U;
        var result = (FWPM_PROVIDER0**)this.Arena.AllocBytes((nuint)(sizeof(FWPM_PROVIDER0*) * count));
        for (uint index = 0; index < count; index++)
        {
            var native = this.Arena.Alloc<FWPM_PROVIDER0>();
            native->providerKey = this.ProviderKey;
            native->displayData.name = this.Arena.AllocUtf16("fake provider");
            native->providerData.size = 0;
            result[index] = native;
        }
        this.Arena.RegisterCurrentBatch(result);
        return result;
    }

    private FWPM_SUBLAYER0** CreateSublayerBatch(out uint count)
    {
        this.Arena.BeginBatch();
        count = this.DuplicateSublayerKey ? 2U : 1U;
        var result = (FWPM_SUBLAYER0**)this.Arena.AllocBytes((nuint)(sizeof(FWPM_SUBLAYER0*) * count));
        for (uint index = 0; index < count; index++)
        {
            var native = this.Arena.Alloc<FWPM_SUBLAYER0>();
            native->subLayerKey = this.SublayerKey;
            native->providerKey = this.CreateProviderReference();
            native->displayData.name = this.Arena.AllocUtf16("fake sublayer");
            native->providerData.size = 0;
            result[index] = native;
        }
        this.Arena.RegisterCurrentBatch(result);
        return result;
    }

    private FWPM_LAYER0** CreateLayerBatch(out uint count)
    {
        this.Arena.BeginBatch();
        count = this.DuplicateLayerKey ? 2U : 1U;
        var result = (FWPM_LAYER0**)this.Arena.AllocBytes((nuint)(sizeof(FWPM_LAYER0*) * count));
        for (uint index = 0; index < count; index++)
        {
            var native = this.Arena.Alloc<FWPM_LAYER0>();
            native->layerKey = this.FixtureLayerKey;
            native->defaultSubLayerKey = this.LayerReferencesMissingDefaultSublayer ? Guid.NewGuid() : this.SublayerKey;
            result[index] = native;
        }
        this.Arena.RegisterCurrentBatch(result);
        return result;
    }

    private FWPM_FILTER0** CreateFilterBatch(out uint count)
    {
        this.Arena.BeginBatch();
        var native = this.Arena.Alloc<FWPM_FILTER0>();
        native->filterKey = Guid.NewGuid();
        native->displayData.name = this.Arena.AllocUtf16("fake filter");
        native->providerKey = this.CreateProviderReference();
        native->providerData.size = 0;
        native->layerKey = this.FilterReferencesMissingLayer ? Guid.NewGuid() : this.FixtureLayerKey;
        native->subLayerKey = this.FilterReferencesMissingSublayer
            ? Guid.NewGuid()
            : this.FilterReferencesSublayer ? this.SublayerKey : Guid.Empty;
        native->weight.type = FWP_DATA_TYPE.FWP_UINT32;
        native->weight.uint32 = 5;
        native->effectiveWeight.type = FWP_DATA_TYPE.FWP_UINT64;
        native->effectiveWeight.uint64 = this.Arena.Alloc<ulong>();
        *native->effectiveWeight.uint64 = 10;
        bool referencesCallout = this.FilterReferencesCallout || this.FilterReferencesProviderContext;
        native->action.type = referencesCallout
            ? this.UseInspectionCalloutAction
                ? FWP_ACTION_TYPE.FWP_ACTION_CALLOUT_INSPECTION
                : FWP_ACTION_TYPE.FWP_ACTION_CALLOUT_TERMINATING
            : FWP_ACTION_TYPE.FWP_ACTION_BLOCK;
        if (referencesCallout)
        {
            native->action.calloutKey = this.UseMissingCalloutKey ? Guid.NewGuid() : this.CalloutKey;
        }
        if (this.FilterReferencesProviderContext)
        {
            native->flags = FWPM_FILTER_FLAGS.FWPM_FILTER_FLAG_HAS_PROVIDER_CONTEXT;
            native->providerContextKey = this.UseMissingProviderContextKey ? Guid.NewGuid() : this.ProviderContextKey;
        }
        else if (this.FilterHasUnflaggedProviderContextKey)
        {
            native->providerContextKey = this.ProviderContextKey;
        }
        var result = (FWPM_FILTER0**)this.Arena.AllocBytes((nuint)sizeof(FWPM_FILTER0*));
        *result = native;
        this.Arena.RegisterCurrentBatch(result);
        count = 1;
        return result;
    }

    private FWPM_CALLOUT0** CreateCalloutBatch(out uint count)
    {
        this.Arena.BeginBatch();
        count = this.DuplicateCalloutKey ? 2U : 1U;
        var result = (FWPM_CALLOUT0**)this.Arena.AllocBytes((nuint)(sizeof(FWPM_CALLOUT0*) * count));
        for (uint index = 0; index < count; index++)
        {
            var native = this.Arena.Alloc<FWPM_CALLOUT0>();
            native->calloutKey = this.CalloutKey;
            native->providerKey = this.CreateProviderReference();
            native->displayData.name = this.Arena.AllocUtf16("fixture callout");
            native->providerData.size = 0;
            native->applicableLayer = this.MismatchCalloutLayer ? Guid.NewGuid() : this.FixtureLayerKey;
            native->calloutId = 21;
            result[index] = native;
        }
        this.Arena.RegisterCurrentBatch(result);
        return result;
    }

    private FWPM_PROVIDER_CONTEXT0** CreateProviderContextBatch(out uint count)
    {
        this.Arena.BeginBatch();
        count = this.DuplicateProviderContextKey ? 2U : 1U;
        var result = (FWPM_PROVIDER_CONTEXT0**)this.Arena.AllocBytes((nuint)(sizeof(FWPM_PROVIDER_CONTEXT0*) * count));
        for (uint index = 0; index < count; index++)
        {
            var native = this.Arena.Alloc<FWPM_PROVIDER_CONTEXT0>();
            native->providerContextKey = this.EmptyProviderContextKey ? Guid.Empty : this.ProviderContextKey;
            native->providerKey = this.CreateProviderReference();
            native->displayData.name = this.Arena.AllocUtf16("fixture provider context");
            native->providerData.size = 0;
            native->type = this.ProviderContextType;
            native->providerContextId = 44;
            if (this.ProviderContextType == FWPM_PROVIDER_CONTEXT_TYPE.FWPM_GENERAL_CONTEXT)
            {
                native->dataBuffer = this.Arena.Alloc<FWP_BYTE_BLOB>();
                native->dataBuffer->size = this.MalformedProviderContextDataBuffer ? 1U : 3U;
                native->dataBuffer->data = this.MalformedProviderContextDataBuffer ? null : this.Arena.AllocBytes([0x01, 0x02, 0x03]);
            }
            else if (this.ProviderContextType == FWPM_PROVIDER_CONTEXT_TYPE.FWPM_CLASSIFY_OPTIONS_CONTEXT)
            {
                if (this.NullClassifyOptionsStructure)
                {
                    result[index] = native;
                    continue;
                }
                native->classifyOptions = this.Arena.Alloc<FWPM_CLASSIFY_OPTIONS0>();
                native->classifyOptions->numOptions = this.OversizedClassifyOptionsArray
                    ? 65U
                    : this.NullClassifyOptionsArray ? 1U : 2U;
                native->classifyOptions->options = this.NullClassifyOptionsArray || this.OversizedClassifyOptionsArray
                    ? null
                    : this.Arena.AllocArray<FWPM_CLASSIFY_OPTION0>(2);
                if (native->classifyOptions->options is null)
                {
                    result[index] = native;
                    continue;
                }
                native->classifyOptions->options[0].type = this.UnknownClassifyOption
                    ? (FWP_CLASSIFY_OPTION_TYPE)999
                    : this.UnsupportedClassifyOption
                        ? FWP_CLASSIFY_OPTION_TYPE.FWP_CLASSIFY_OPTION_SECURE_SOCKET_SECURITY_FLAGS
                        : this.FirstClassifyOptionType;
                native->classifyOptions->options[0].value.type = this.WrongClassifyOptionValueType
                    ? FWP_DATA_TYPE.FWP_UINT16
                    : FWP_DATA_TYPE.FWP_UINT32;
                native->classifyOptions->options[0].value.uint32 = this.FirstClassifyOptionValue;
                native->classifyOptions->options[1].type = this.DuplicateClassifyOptionType
                    ? FWP_CLASSIFY_OPTION_TYPE.FWP_CLASSIFY_OPTION_UNICAST_LIFETIME
                    : FWP_CLASSIFY_OPTION_TYPE.FWP_CLASSIFY_OPTION_MCAST_BCAST_LIFETIME;
                native->classifyOptions->options[1].value.type = FWP_DATA_TYPE.FWP_UINT32;
                native->classifyOptions->options[1].value.uint32 = 60;
            }
            result[index] = native;
        }
        this.Arena.RegisterCurrentBatch(result);
        return result;
    }

    private Guid* CreateProviderReference()
    {
        if (!this.ReferenceProviderFromAllObjects)
        {
            return null;
        }

        var reference = this.Arena.Alloc<Guid>();
        *reference = this.UseEmptyProviderReference
            ? Guid.Empty
            : this.UseMissingProviderReference ? Guid.NewGuid() : this.ProviderKey;
        return reference;
    }
}

internal sealed class FixtureSafeHandle : SafeHandleZeroOrMinusOneIsInvalid
{
    private readonly Func<bool> release;

    internal FixtureSafeHandle(int value, Func<bool> release) : base(ownsHandle: true)
    {
        this.release = release;
        this.SetHandle(new IntPtr(value));
    }

    protected override bool ReleaseHandle()
    {
        return this.release();
    }
}
