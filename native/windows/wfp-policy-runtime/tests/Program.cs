using WfpPolicy.Runtime;
using WfpPolicy.NativeReadback;
using WfpPolicyPlan;
using System.Security.Cryptography;

namespace WfpPolicy.Runtime.Harness;

internal static class Program
{
    private static readonly ProtectedApplicationInput[] Applications =
    [
        new(ProtectedApplicationRole.Browser, "01020304"),
        new(ProtectedApplicationRole.Worker, "05060708"),
    ];

    public static int Main()
    {
        (string Name, Action Run)[] checks =
        [
            ("creates and verifies missing persistent baseline", CreatesBaseline),
            ("reconciliation is idempotent and preserves unrelated objects", ReconcilesIdempotently),
            ("managed filter drift is replaced with one delete", ReplacesManagedFilterDrift),
            ("missing native projection fields fail closed", RejectsMissingNativeProjectionFields),
            ("extra native projection fields fail closed", RejectsExtraNativeProjectionFields),
            ("incomplete and unsupported native projections fail closed", RejectsIncompleteNativeProjection),
            ("complete native readback maps canonically without dropping source fields", MapsCompleteNativeReadback),
            ("incomplete native readback is rejected before store mutation", RejectsIncompleteNativeReadbackBeforeMutation),
            ("native readback failure is rejected before store mutation", RejectsNativeReadbackFailureBeforeMutation),
            ("provider key ownership conflicts fail before mutation", RejectsProviderConflict),
            ("unrecognized baseline sublayer filters fail before mutation", RejectsUnrecognizedBaselineFilter),
            ("native WFP store adapter validates service ACLs and transaction readback", NativeWfpPolicyStoreAdapterHarness.Run),
            ("dynamic lease lifecycle enforces its offline session contracts", DynamicLeaseCoordinatorHarness.Run),
            ("commit readback mismatch compensates to the prior snapshot", CompensatesReadbackMismatch),
            ("commit replacement is preserved when rollback state is uncertain", PreservesReplacementOnUncertainRollback),
            ("unverified rollback keeps readiness closed", RejectsUnverifiedRollback),
            ("pre-commit failure aborts the complete transaction", AbortsPreCommitFailure),
        ];

        int passed = 0;
        foreach ((string name, Action run) in checks)
        {
            run();
            Console.WriteLine($"PASS {name}");
            passed++;
        }
        Console.WriteLine($"RESULT {passed}/{checks.Length}");
        return 0;
    }

    private static void CreatesBaseline()
    {
        var store = new FakeWfpPolicyStore();
        new PersistentBaselineCoordinator(store).EnsureReady(Applications, CancellationToken.None);
        WfpPolicySnapshot snapshot = store.ReadSnapshot(WfpServicePolicyIdentity.ProviderKey, WfpServicePolicyIdentity.SublayerKey);
        Assert(snapshot.Provider == WfpServicePolicyIdentity.Provider, "provider readback mismatch");
        Assert(snapshot.Sublayer == WfpServicePolicyIdentity.Sublayer, "sublayer readback mismatch");
        Assert(snapshot.Filters.Count == 4, "expected four AppID/family deny filters");
        Assert(snapshot.Filters.All(filter => filter.Persistent && filter.Rule.Action == LeasePolicyAction.Block), "baseline contains a non-persistent or non-block filter");
    }

    private static void ReconcilesIdempotently()
    {
        var store = new FakeWfpPolicyStore();
        var coordinator = new PersistentBaselineCoordinator(store);
        coordinator.EnsureReady(Applications, CancellationToken.None);
        int mutationCount = store.MutationCount;
        int filterCount = store.ReadSnapshot(WfpServicePolicyIdentity.ProviderKey, WfpServicePolicyIdentity.SublayerKey).Filters.Count;

        coordinator.EnsureReady(Applications, CancellationToken.None);
        Assert(store.MutationCount == mutationCount, "a second reconcile changed the stored objects");
        Assert(store.ReadSnapshot(WfpServicePolicyIdentity.ProviderKey, WfpServicePolicyIdentity.SublayerKey).Filters.Count == filterCount, "idempotent reconcile changed filter count");

        WfpFilterIdentity foreign = new(
            Guid.NewGuid(),
            WfpServicePolicyIdentity.ProviderKey,
            Guid.NewGuid(),
            "Unrelated provider object",
            "outside managed sublayer",
            Persistent: true,
            SnapshotRule());
        store.AddOutOfBandFilter(foreign);
        coordinator.EnsureReady(Applications, CancellationToken.None);
        Assert(
            store.ReadSnapshot(WfpServicePolicyIdentity.ProviderKey, WfpServicePolicyIdentity.SublayerKey)
                .Filters.Any(filter => filter.Key == foreign.Key),
            "unrelated object was removed");
    }

    private static void RejectsProviderConflict()
    {
        var store = new FakeWfpPolicyStore
        {
            Provider = WfpServicePolicyIdentity.Provider with { ServiceName = "DifferentService" },
        };
        int before = store.MutationCount;
        Expect<WfpBaselineOwnershipException>(() => new PersistentBaselineCoordinator(store)
            .EnsureReady(Applications, CancellationToken.None));
        Assert(store.MutationCount == before, "provider conflict mutated the store");
    }

    private static void ReplacesManagedFilterDrift()
    {
        var store = new FakeWfpPolicyStore();
        var coordinator = new PersistentBaselineCoordinator(store);
        coordinator.EnsureReady(Applications, CancellationToken.None);
        WfpFilterIdentity original = store.ReadSnapshot(
                WfpServicePolicyIdentity.ProviderKey,
                WfpServicePolicyIdentity.SublayerKey)
            .Filters[0];
        WfpFilterIdentity drifted = original with
        {
            Rule = original.Rule with { AppIdHex = "090a0b0c" },
        };
        store.ReplaceOutOfBandFilter(drifted);
        int deletesBefore = store.DeleteFilterCount;

        coordinator.EnsureReady(Applications, CancellationToken.None);

        Assert(store.DeleteFilterCount - deletesBefore == 1, "drifted filter was not deleted exactly once");
        WfpPolicySnapshot snapshot = store.ReadSnapshot(
            WfpServicePolicyIdentity.ProviderKey,
            WfpServicePolicyIdentity.SublayerKey);
        Assert(snapshot.Filters.Contains(original), "drifted filter was not restored to desired content");
    }

    private static void RejectsUnrecognizedBaselineFilter()
    {
        var store = new FakeWfpPolicyStore
        {
            Provider = WfpServicePolicyIdentity.Provider,
            Sublayer = WfpServicePolicyIdentity.Sublayer,
        };
        store.AddOutOfBandFilter(new WfpFilterIdentity(
            Guid.NewGuid(),
            WfpServicePolicyIdentity.ProviderKey,
            WfpServicePolicyIdentity.SublayerKey,
            "legacy-filter-without-ownership-marker",
            "unrecognized fixture",
            Persistent: true,
            SnapshotRule()));
        store.AddOutOfBandFilter(new WfpFilterIdentity(
            Guid.NewGuid(),
            Guid.NewGuid(),
            WfpServicePolicyIdentity.SublayerKey,
            "foreign-provider-filter-in-service-sublayer",
            "unrecognized fixture",
            Persistent: true,
            SnapshotRule()));
        int before = store.MutationCount;

        Expect<WfpBaselineOwnershipException>(() => new PersistentBaselineCoordinator(store)
            .EnsureReady(Applications, CancellationToken.None));

        Assert(store.MutationCount == before, "an unrecognized baseline filter was not rejected before mutation");
    }

    private static void RejectsMissingNativeProjectionFields()
    {
        RejectsProjectionCorruption("provider", store =>
        {
            WfpProviderIdentity provider = store.Provider
                ?? throw new InvalidOperationException("the fake provider is missing");
            store.Provider = provider with { NativeProjection = RemoveProjectionField(provider.NativeProjection) };
        });
        RejectsProjectionCorruption("sublayer", store =>
        {
            WfpSublayerIdentity sublayer = store.Sublayer
                ?? throw new InvalidOperationException("the fake sublayer is missing");
            store.Sublayer = sublayer with { NativeProjection = RemoveProjectionField(sublayer.NativeProjection) };
        });
        RejectsProjectionCorruption("filter", store =>
        {
            WfpFilterIdentity filter = FirstManagedFilter(store);
            store.SetFilterProjection(filter with
            {
                NativeProjection = RemoveProjectionField(filter.NativeProjection),
            });
        });
    }

    private static void RejectsExtraNativeProjectionFields()
    {
        RejectsProjectionCorruption("provider", store =>
        {
            WfpProviderIdentity provider = store.Provider
                ?? throw new InvalidOperationException("the fake provider is missing");
            store.Provider = provider with { NativeProjection = AddUnexpectedProjectionField(provider.NativeProjection) };
        });
        RejectsProjectionCorruption("sublayer", store =>
        {
            WfpSublayerIdentity sublayer = store.Sublayer
                ?? throw new InvalidOperationException("the fake sublayer is missing");
            store.Sublayer = sublayer with { NativeProjection = AddUnexpectedProjectionField(sublayer.NativeProjection) };
        });
        RejectsProjectionCorruption("filter", store =>
        {
            WfpFilterIdentity filter = FirstManagedFilter(store);
            store.SetFilterProjection(filter with
            {
                NativeProjection = AddUnexpectedProjectionField(filter.NativeProjection),
            });
        });
    }

    private static void RejectsIncompleteNativeProjection()
    {
        RejectsProjectionCorruption("incomplete provider", store =>
        {
            WfpProviderIdentity provider = store.Provider
                ?? throw new InvalidOperationException("the fake provider is missing");
            store.Provider = provider with
            {
                NativeProjection = ChangeProjection(provider.NativeProjection, isComplete: false),
            };
        });
        RejectsProjectionCorruption("unsupported sublayer", store =>
        {
            WfpSublayerIdentity sublayer = store.Sublayer
                ?? throw new InvalidOperationException("the fake sublayer is missing");
            store.Sublayer = sublayer with
            {
                NativeProjection = ChangeProjection(
                    sublayer.NativeProjection,
                    schemaVersion: WfpNativeObjectProjection.CurrentSchemaVersion + 1),
            };
        });
        RejectsProjectionCorruption("incomplete filter", store =>
        {
            WfpFilterIdentity filter = FirstManagedFilter(store);
            store.SetFilterProjection(filter with
            {
                NativeProjection = ChangeProjection(filter.NativeProjection, isComplete: false),
            });
        });
    }

    private static void MapsCompleteNativeReadback()
    {
        WfpSnapshot native = CompleteNativeBaselineSnapshot();
        WfpPolicySnapshot mapped = WfpNativeReadbackAdapter.ToPolicySnapshot(
            native,
            WfpServicePolicyIdentity.ProviderKey,
            WfpServicePolicyIdentity.SublayerKey);

        Assert(mapped.Provider == WfpServicePolicyIdentity.Provider, "native provider did not map exactly");
        Assert(mapped.Sublayer == WfpServicePolicyIdentity.Sublayer, "native sublayer did not map exactly");
        Assert(mapped.Filters.Count == 1, "expected one mapped native baseline filter");
        Assert(mapped.Filters[0].Rule.AppIdHex == "01020304", "native AppID bytes were changed during mapping");
        WfpNativeReadbackProjection readback = mapped.NativeReadbackProjection
            ?? throw new InvalidOperationException("native source evidence was dropped");
        Assert(ReferenceEquals(native, readback.SourceSnapshot), "native immutable snapshot was not retained");
        Assert(readback.Objects.Count == 3, "canonical native evidence omitted a provider, sublayer, or filter");
        Assert(readback.Objects.All(item => item.Fields.SequenceEqual(item.Fields.OrderBy(field => field.Name, StringComparer.Ordinal))),
            "native evidence fields are not canonically ordered");
        Assert(readback.SourceSnapshot.Filters[0].FilterId == 17, "native filter ID was lost");
        Assert(readback.SourceSnapshot.Filters[0].EffectiveWeight.ScalarValue == "1234", "native effective weight was lost");
    }

    private static void RejectsIncompleteNativeReadbackBeforeMutation()
    {
        WfpSnapshot complete = CompleteNativeBaselineSnapshot();
        var incomplete = new WfpSnapshot(
            complete.CapturedAtUtc,
            complete.Providers,
            complete.Sublayers,
            complete.Filters,
            [new SnapshotIssue(SnapshotIssueCode.SecurityDescriptorNotNormalized, "snapshot", "", "fixture incomplete")]);
        var store = new FakeWfpPolicyStore
        {
            SnapshotOverride = (providerKey, sublayerKey) => WfpNativeReadbackAdapter.ToPolicySnapshot(incomplete, providerKey, sublayerKey),
        };
        int before = store.MutationCount;

        Expect<WfpBaselineOwnershipException>(() => new PersistentBaselineCoordinator(store)
            .EnsureReady(Applications, CancellationToken.None));

        Assert(store.MutationCount == before, "an incomplete native snapshot reached the transaction mutators");
        Assert(store.CommitCount == 0, "an incomplete native snapshot committed a transaction");
    }

    private static void RejectsNativeReadbackFailureBeforeMutation()
    {
        var store = new FakeWfpPolicyStore
        {
            SnapshotOverride = (_, _) => throw new WfpReadbackException("fixture native enumeration failure"),
        };
        int before = store.MutationCount;

        Expect<WfpReadbackException>(() => new PersistentBaselineCoordinator(store)
            .EnsureReady(Applications, CancellationToken.None));

        Assert(store.MutationCount == before, "a failed native read reached the transaction mutators");
        Assert(store.CommitCount == 0, "a failed native read committed a transaction");
    }

    private static WfpSnapshot CompleteNativeBaselineSnapshot()
    {
        const string appIdHex = "01020304";
        string identityHash = Convert.ToHexString(SHA256.HashData(Convert.FromHexString(appIdHex)))[..16];
        string ruleId = $"default-deny-browser-{identityHash}-v4";
        var rule = new LeasePolicyRule(
            ruleId,
            "Persistent catch-all block for every browser process from this protected AppID; higher-weight exact lease permits are the only intended exceptions.",
            LeasePolicyAddressFamily.IPv4,
            LeasePolicyAction.Block,
            LeasePolicyCompiler.DefaultDenyWeightRangeIndex,
            LeasePolicyLifetime.PersistentDefaultDeny,
            LeaseId: null,
            AppIdHex: appIdHex,
            LeaseSid: null,
            IdentityCondition: "ALE_APP_ID",
            RemoteAddress: null,
            Protocol: null,
            RemotePort: null,
            ClearActionRight: false);
        var provider = new ProviderSnapshot(
            WfpServicePolicyIdentity.ProviderKey,
            WfpServicePolicyIdentity.ProviderName,
            WfpServicePolicyIdentity.ProviderDescription,
            flags: 1,
            WfpServicePolicyIdentity.ServiceName,
            Array.Empty<byte>(),
            null,
            Array.Empty<SnapshotIssue>());
        var sublayer = new SublayerSnapshot(
            WfpServicePolicyIdentity.SublayerKey,
            WfpServicePolicyIdentity.SublayerName,
            WfpServicePolicyIdentity.SublayerDescription,
            flags: 1,
            WfpServicePolicyIdentity.ProviderKey,
            WfpServicePolicyIdentity.SublayerWeight,
            Array.Empty<byte>(),
            null,
            Array.Empty<SnapshotIssue>());
        var filter = new FilterSnapshot(
            WfpServicePolicyIdentity.FilterKey(rule.RuleId),
            WfpServicePolicyIdentity.FilterNamePrefix + rule.RuleId,
            rule.Purpose,
            flags: 1,
            WfpServicePolicyIdentity.ProviderKey,
            Array.Empty<byte>(),
            new Guid("c38d57d1-05a7-4c33-904f-7fbceee60e82"),
            WfpServicePolicyIdentity.SublayerKey,
            new NativeValueSnapshot(1, "FWP_UINT8", "1", IsDecoded: true),
            [new FilterConditionSnapshot(
                WfpNativeConditionKeys.AleAppId,
                0,
                "FWP_MATCH_EQUAL",
                new NativeValueSnapshot(12, "FWP_BYTE_BLOB_TYPE", ScalarValue: null, IsDecoded: true, BlobHex: "01020304"))],
            actionTypeCode: 0x1001,
            "FWP_ACTION_BLOCK",
            calloutKey: null,
            rawContext: 0,
            providerContextKey: null,
            filterId: 17,
            new NativeValueSnapshot(4, "FWP_UINT64", "1234", IsDecoded: true),
            null,
            Array.Empty<SnapshotIssue>());
        return new WfpSnapshot(
            DateTimeOffset.UnixEpoch,
            [provider],
            [sublayer],
            [filter],
            Array.Empty<SnapshotIssue>());
    }

    private static void RejectsProjectionCorruption(string objectKind, Action<FakeWfpPolicyStore> corrupt)
    {
        var store = new FakeWfpPolicyStore();
        var coordinator = new PersistentBaselineCoordinator(store);
        coordinator.EnsureReady(Applications, CancellationToken.None);
        corrupt(store);
        int mutationCount = store.MutationCount;

        Expect<WfpBaselineOwnershipException>(() => coordinator.EnsureReady(Applications, CancellationToken.None));

        Assert(store.MutationCount == mutationCount, $"a malformed {objectKind} projection mutated the store");
    }

    private static WfpFilterIdentity FirstManagedFilter(FakeWfpPolicyStore store) => store.ReadSnapshot(
            WfpServicePolicyIdentity.ProviderKey,
            WfpServicePolicyIdentity.SublayerKey)
        .Filters[0];

    private static WfpNativeObjectProjection RemoveProjectionField(WfpNativeObjectProjection? projection)
    {
        if (projection?.Fields is null || projection.Fields.Count < 2)
        {
            throw new InvalidOperationException("the fake projection has too few fields to corrupt");
        }
        return new WfpNativeObjectProjection(
            projection.SchemaVersion,
            projection.ObjectKind,
            projection.IsComplete,
            projection.Fields.Skip(1));
    }

    private static WfpNativeObjectProjection AddUnexpectedProjectionField(WfpNativeObjectProjection? projection)
    {
        if (projection?.Fields is null)
        {
            throw new InvalidOperationException("the fake projection is missing");
        }
        return new WfpNativeObjectProjection(
            projection.SchemaVersion,
            projection.ObjectKind,
            projection.IsComplete,
            projection.Fields.Append(new WfpNativeObjectField("unexpectedExecutionField", "present"))
                .OrderBy(field => field.Name, StringComparer.Ordinal));
    }

    private static WfpNativeObjectProjection ChangeProjection(
        WfpNativeObjectProjection? projection,
        int? schemaVersion = null,
        bool? isComplete = null)
    {
        if (projection?.Fields is null)
        {
            throw new InvalidOperationException("the fake projection is missing");
        }
        return new WfpNativeObjectProjection(
            schemaVersion ?? projection.SchemaVersion,
            projection.ObjectKind,
            isComplete ?? projection.IsComplete,
            projection.Fields);
    }

    private static void CompensatesReadbackMismatch()
    {
        var store = new FakeWfpPolicyStore { CorruptNextPostCommitReadback = true };
        Expect<WfpBaselineVerificationException>(() => new PersistentBaselineCoordinator(store)
            .EnsureReady(Applications, CancellationToken.None));
        WfpPolicySnapshot restored = store.ReadSnapshot(WfpServicePolicyIdentity.ProviderKey, WfpServicePolicyIdentity.SublayerKey);
        Assert(restored.Provider is null && restored.Sublayer is null && restored.Filters.Count == 0, "rollback did not restore the empty prior snapshot");
        Assert(store.CommitCount == 2, "expected apply and compensating transactions");
    }

    private static void RejectsUnverifiedRollback()
    {
        var store = new FakeWfpPolicyStore
        {
            CorruptNextPostCommitReadback = true,
            FailCommitNumber = 2,
        };
        Expect<WfpBaselineRollbackException>(() => new PersistentBaselineCoordinator(store)
            .EnsureReady(Applications, CancellationToken.None));
    }

    private static void PreservesReplacementOnUncertainRollback()
    {
        var store = new FakeWfpPolicyStore { ReplaceManagedFilterWithForeignProviderAfterFirstCommit = true };
        Expect<WfpBaselineRollbackException>(() => new PersistentBaselineCoordinator(store)
            .EnsureReady(Applications, CancellationToken.None));

        WfpFilterIdentity replacement = store.InjectedForeignReplacement
            ?? throw new InvalidOperationException("fake store did not inject the foreign replacement");
        WfpPolicySnapshot current = store.ReadSnapshot(
            WfpServicePolicyIdentity.ProviderKey,
            WfpServicePolicyIdentity.SublayerKey);
        Assert(current.Filters.Contains(replacement), "rollback deleted or changed the unexpected same-key object");
        Assert(store.DeleteFilterCount == 0, "rollback mutated filters before confirming the committed snapshot");
        Assert(store.CommitCount == 1, "rollback committed after finding an unexpected same-key object");
    }

    private static void AbortsPreCommitFailure()
    {
        var store = new FakeWfpPolicyStore { FailAddFilterNumber = 2 };
        Expect<InvalidOperationException>(() => new PersistentBaselineCoordinator(store)
            .EnsureReady(Applications, CancellationToken.None));
        WfpPolicySnapshot snapshot = store.ReadSnapshot(WfpServicePolicyIdentity.ProviderKey, WfpServicePolicyIdentity.SublayerKey);
        Assert(snapshot.Provider is null && snapshot.Sublayer is null && snapshot.Filters.Count == 0, "aborted transaction leaked changes");
        Assert(store.AbortCount == 1, "transaction failure did not abort");
    }

    private static LeasePolicyRule SnapshotRule() => new(
        "foreign-test",
        "fixture only",
        LeasePolicyAddressFamily.IPv4,
        LeasePolicyAction.Block,
        LeasePolicyCompiler.DefaultDenyWeightRangeIndex,
        LeasePolicyLifetime.PersistentDefaultDeny,
        LeaseId: null,
        AppIdHex: "01020304",
        LeaseSid: null,
        IdentityCondition: "ALE_APP_ID",
        RemoteAddress: null,
        Protocol: null,
        RemotePort: null,
        ClearActionRight: false);

    private static void Expect<TException>(Action action) where TException : Exception
    {
        try
        {
            action();
        }
        catch (TException)
        {
            return;
        }
        throw new InvalidOperationException($"Expected {typeof(TException).Name}.");
    }

    private static void Assert(bool condition, string message)
    {
        if (!condition)
        {
            throw new InvalidOperationException(message);
        }
    }
}

internal sealed class FakeWfpPolicyStore : IWfpPolicyStore
{
    private readonly Dictionary<Guid, WfpFilterIdentity> filters = [];
    private bool corruptOnNextRead;
    private int addFilterCount;

    public WfpProviderIdentity? Provider { get; set; }
    public WfpSublayerIdentity? Sublayer { get; set; }
    public int MutationCount { get; private set; }
    public int ReadSnapshotCount { get; private set; }
    public int DeleteFilterCount { get; private set; }
    public int CommitCount { get; private set; }
    public int AbortCount { get; private set; }
    public int? FailCommitNumber { get; init; }
    public int? FailAddFilterNumber { get; init; }
    public bool CorruptNextPostCommitReadback { get; init; }
    public bool ReplaceManagedFilterWithForeignProviderAfterFirstCommit { get; init; }
    public WfpFilterIdentity? InjectedForeignReplacement { get; private set; }
    public Func<Guid, Guid, WfpPolicySnapshot>? SnapshotOverride { get; init; }

    public WfpPolicySnapshot ReadSnapshot(Guid providerKey, Guid sublayerKey)
    {
        this.ReadSnapshotCount++;
        if (providerKey != WfpServicePolicyIdentity.ProviderKey
            || sublayerKey != WfpServicePolicyIdentity.SublayerKey)
        {
            throw new InvalidOperationException("Unexpected ownership keys.");
        }

        if (SnapshotOverride is not null)
        {
            return SnapshotOverride(providerKey, sublayerKey);
        }

        WfpFilterIdentity[] values = filters.Values
            .Where(filter => filter.ProviderKey == providerKey || filter.SublayerKey == sublayerKey)
            .OrderBy(filter => filter.Key)
            .ToArray();
        if (corruptOnNextRead)
        {
            corruptOnNextRead = false;
            values = values.Take(Math.Max(0, values.Length - 1)).ToArray();
        }
        return new WfpPolicySnapshot(Provider, Sublayer, Array.AsReadOnly(values));
    }

    public IWfpPolicyTransaction BeginTransaction() => new FakeTransaction(this);

    public void AddOutOfBandFilter(WfpFilterIdentity filter)
    {
        WfpFilterIdentity projected = filter.NativeProjection is null
            ? filter with { NativeProjection = WfpNativeObjectProjection.ForFilter(filter) }
            : filter;
        filters.Add(projected.Key, projected);
    }

    public void RemoveOutOfBandFilter(Guid key)
    {
        if (!filters.Remove(key))
        {
            throw new InvalidOperationException("The fixture baseline filter did not exist.");
        }
    }

    public void ReplaceOutOfBandFilter(WfpFilterIdentity filter)
    {
        filters[filter.Key] = filter with { NativeProjection = WfpNativeObjectProjection.ForFilter(filter) };
    }

    public void SetFilterProjection(WfpFilterIdentity filter)
    {
        filters[filter.Key] = filter;
    }

    private sealed class FakeTransaction(FakeWfpPolicyStore owner) : IWfpPolicyTransaction
    {
        private WfpProviderIdentity? provider = owner.Provider;
        private WfpSublayerIdentity? sublayer = owner.Sublayer;
        private readonly Dictionary<Guid, WfpFilterIdentity> workingFilters = new(owner.filters);
        private bool complete;

        public WfpProviderIdentity? GetProvider(Guid key) => provider?.Key == key ? provider : null;
        public WfpSublayerIdentity? GetSublayer(Guid key) => sublayer?.Key == key ? sublayer : null;

        public IReadOnlyList<WfpFilterIdentity> EnumerateProviderFilters(Guid providerKey) =>
            Array.AsReadOnly(workingFilters.Values.Where(filter => filter.ProviderKey == providerKey).OrderBy(filter => filter.Key).ToArray());

        public IReadOnlyList<WfpFilterIdentity> EnumerateSublayerFilters(Guid sublayerKey) =>
            Array.AsReadOnly(workingFilters.Values.Where(filter => filter.SublayerKey == sublayerKey).OrderBy(filter => filter.Key).ToArray());

        public void AddProvider(WfpProviderIdentity value)
        {
            EnsureOpen();
            if (provider is not null)
            {
                throw new InvalidOperationException("provider already exists");
            }
            provider = value;
            owner.MutationCount++;
        }

        public void DeleteProvider(Guid key)
        {
            EnsureOpen();
            if (provider?.Key != key || sublayer is not null || workingFilters.Count != 0)
            {
                throw new InvalidOperationException("provider cannot be deleted");
            }
            provider = null;
            owner.MutationCount++;
        }

        public void AddSublayer(WfpSublayerIdentity value)
        {
            EnsureOpen();
            if (provider?.Key != value.ProviderKey || sublayer is not null)
            {
                throw new InvalidOperationException("sublayer cannot be added");
            }
            sublayer = value;
            owner.MutationCount++;
        }

        public void DeleteSublayer(Guid key)
        {
            EnsureOpen();
            if (sublayer?.Key != key || workingFilters.Values.Any(filter => filter.SublayerKey == key))
            {
                throw new InvalidOperationException("sublayer cannot be deleted");
            }
            sublayer = null;
            owner.MutationCount++;
        }

        public void AddFilter(WfpFilterIdentity filter)
        {
            EnsureOpen();
            owner.addFilterCount++;
            if (owner.FailAddFilterNumber == owner.addFilterCount)
            {
                throw new InvalidOperationException("injected add failure");
            }
            workingFilters.Add(filter.Key, filter);
            owner.MutationCount++;
        }

        public void DeleteFilter(Guid key)
        {
            EnsureOpen();
            if (!workingFilters.Remove(key))
            {
                throw new InvalidOperationException("filter does not exist");
            }
            owner.DeleteFilterCount++;
            owner.MutationCount++;
        }

        public void Commit()
        {
            EnsureOpen();
            owner.CommitCount++;
            if (owner.FailCommitNumber == owner.CommitCount)
            {
                throw new InvalidOperationException("injected commit failure");
            }
            owner.Provider = provider;
            owner.Sublayer = sublayer;
            owner.filters.Clear();
            foreach ((Guid key, WfpFilterIdentity filter) in workingFilters)
            {
                owner.filters.Add(key, filter);
            }
            if (owner.ReplaceManagedFilterWithForeignProviderAfterFirstCommit && owner.CommitCount == 1)
            {
                WfpFilterIdentity managed = owner.filters.Values.First(filter =>
                    filter.ProviderKey == WfpServicePolicyIdentity.ProviderKey
                    && filter.SublayerKey == WfpServicePolicyIdentity.SublayerKey);
                WfpFilterIdentity replacement = managed with
                {
                    ProviderKey = Guid.NewGuid(),
                    Name = "foreign same-key replacement",
                };
                owner.filters[managed.Key] = replacement;
                owner.InjectedForeignReplacement = replacement;
            }
            owner.corruptOnNextRead = owner.CorruptNextPostCommitReadback && owner.CommitCount == 1;
            complete = true;
        }

        public void Abort()
        {
            EnsureOpen();
            owner.AbortCount++;
            complete = true;
        }

        public void Dispose()
        {
            if (!complete)
            {
                Abort();
            }
        }

        private void EnsureOpen() => ObjectDisposedException.ThrowIf(complete, this);
    }
}
