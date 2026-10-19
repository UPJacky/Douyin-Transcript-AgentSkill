using WfpPolicy.Runtime;
using WfpPolicy.NativeReadback;
using WfpPolicyPlan;
using System.Security.Cryptography;
using System.Text;

namespace WfpPolicy.Runtime.Harness;

internal static class DynamicLeaseCoordinatorHarness
{
    private static readonly ProtectedApplicationInput[] Applications =
    [
        new(ProtectedApplicationRole.Browser, "01020304"),
        new(ProtectedApplicationRole.Worker, "05060708"),
    ];
    private const string ServiceSid = "S-1-5-80-1-2-3-4-5";

    internal static void Run()
    {
        OpensSeparateFakeSessionsAndRechecksBaseline();
        ValidatesMergedSharedSublayerReadbackAgainstActiveRegistry();
        FailsClosedWhenBaselineScopeExposesDynamicFilters();
        RejectsInvalidDynamicProviderAndAclReadback();
        RejectsBaselineFailureAndRepairsMissingBaselineRow();
        RejectsMalformedPlansBeforeSessionCreation();
        ClosesAfterAddReadbackAndCancellationFailures();
        RetainsUnclosedHandleAndIsolatesCoordinator();
        RejectsDuplicateLeaseAndAllowsRepeatedClose();
        RejectsDuplicateSessionIdentityWithoutClosingAmbiguousHandle();
        RequiresSuccessfulDrainAfterWorkerStart();
        RetainsLeaseWhenNormalCloseFails();
    }

    // These assertions exercise the fake session/snapshot boundaries only;
    // they are not evidence that native provider/sublayer enumeration is isolated.
    private static void OpensSeparateFakeSessionsAndRechecksBaseline()
    {
        var store = new FakeWfpPolicyStore();
        var sessions = new FakeDynamicLeasePolicySessionFactory();
        DynamicLeaseCoordinator coordinator = CreateCoordinator(store, sessions);
        LeasePolicyInput firstPlan = Plan(1001, 45_301);
        LeasePolicyInput secondPlan = Plan(1002, 45_302);

        DynamicLeaseScope first = coordinator.Open(firstPlan, CancellationToken.None);
        int readsAfterFirst = store.ReadSnapshotCount;
        DynamicLeaseScope second = coordinator.Open(secondPlan, CancellationToken.None);

        Assert(sessions.Sessions.Count == 2, "two leases did not receive separate dynamic sessions");
        FakeDynamicLeasePolicySession firstSession = sessions.Sessions[0];
        FakeDynamicLeasePolicySession secondSession = sessions.Sessions[1];
        Assert(firstSession.SessionId != secondSession.SessionId, "two leases shared a session identity");
        Assert(firstSession.LeaseId != secondSession.LeaseId, "two sessions have the same lease identity");
        Assert(firstSession.Provider is not null && secondSession.Provider is not null,
            "a lease session did not create its own dynamic provider");
        DynamicLeaseProviderIdentity firstProvider = firstSession.Provider!;
        DynamicLeaseProviderIdentity secondProvider = secondSession.Provider!;
        Assert(firstProvider.Key != secondProvider.Key
            && firstProvider.Key != WfpServicePolicyIdentity.ProviderKey
            && secondProvider.Key != WfpServicePolicyIdentity.ProviderKey,
            "lease providers were not unique and separate from the persistent baseline provider");
        Assert(firstSession.Filters.Count == first.Filters.Count && secondSession.Filters.Count == second.Filters.Count,
            "one lease's rules appeared in the other session");
        Assert(first.Filters.All(filter => filter.ProviderKey == firstProvider.Key
            && filter.SublayerKey == WfpServicePolicyIdentity.SublayerKey
            && !filter.Persistent)
            && second.Filters.All(filter => filter.ProviderKey == secondProvider.Key
                && filter.SublayerKey == WfpServicePolicyIdentity.SublayerKey
                && !filter.Persistent),
            "dynamic filters did not keep per-lease providers, the shared baseline sublayer, and dynamic lifetime");
        Assert(!first.Filters.Select(filter => filter.Key).Intersect(second.Filters.Select(filter => filter.Key)).Any(),
            "two leases produced colliding filter keys");
        Assert(store.ReadSnapshotCount > readsAfterFirst, "opening the second lease skipped the persistent-baseline readback");
        Assert(store.ReadSnapshot(WfpServicePolicyIdentity.ProviderKey, WfpServicePolicyIdentity.SublayerKey).Filters.Count == 4,
            "dynamic session rules leaked into the persistent-baseline store scope");

        first.Close();
        Assert(firstSession.IsClosed && !secondSession.IsClosed, "closing one lease changed the other dynamic session");
        Assert(secondSession.Filters.Count == second.Filters.Count, "closing one lease removed another lease's filters");
        second.Close();
        Assert(secondSession.IsClosed, "the second dynamic session did not close");
    }

    private static void RejectsBaselineFailureAndRepairsMissingBaselineRow()
    {
        var unavailableStore = new FakeWfpPolicyStore
        {
            SnapshotOverride = (_, _) => throw new WfpReadbackException("fixture baseline readback failure"),
        };
        var unavailableSessions = new FakeDynamicLeasePolicySessionFactory();
        DynamicLeaseCoordinator unavailable = CreateCoordinator(unavailableStore, unavailableSessions);
        Expect<WfpReadbackException>(() => unavailable.Open(Plan(1010, 45_310), CancellationToken.None));
        Assert(unavailableSessions.Sessions.Count == 0, "a lease session opened before baseline readiness succeeded");

        var driftStore = new FakeWfpPolicyStore();
        var driftSessions = new FakeDynamicLeasePolicySessionFactory();
        DynamicLeaseCoordinator driftCoordinator = CreateCoordinator(driftStore, driftSessions);
        DynamicLeaseScope first = driftCoordinator.Open(Plan(1011, 45_311), CancellationToken.None);
        int readsBeforeSecondOpen = driftStore.ReadSnapshotCount;
        WfpFilterIdentity removed = driftStore.ReadSnapshot(
            WfpServicePolicyIdentity.ProviderKey,
            WfpServicePolicyIdentity.SublayerKey).Filters[0];
        driftStore.RemoveOutOfBandFilter(removed.Key);
        int readsBeforeReconcile = driftStore.ReadSnapshotCount;

        DynamicLeaseScope second = driftCoordinator.Open(Plan(1012, 45_312), CancellationToken.None);

        Assert(driftStore.ReadSnapshotCount > readsBeforeReconcile && readsBeforeReconcile >= readsBeforeSecondOpen,
            "the second lease did not re-read the baseline after drift");
        WfpPolicySnapshot restored = driftStore.ReadSnapshot(
            WfpServicePolicyIdentity.ProviderKey,
            WfpServicePolicyIdentity.SublayerKey);
        Assert(restored.Filters.Count == 4 && restored.Filters.Any(filter => filter.Key == removed.Key),
            "the verified persistent baseline did not reconcile the missing filter");
        Assert(driftSessions.Sessions.Count == 2, "baseline drift prevented a successful reconciliation and second lease open");

        first.Close();
        second.Close();
    }

    private static void FailsClosedWhenBaselineScopeExposesDynamicFilters()
    {
        var store = new FakeWfpPolicyStore();
        var sessions = new FakeDynamicLeasePolicySessionFactory();
        DynamicLeaseCoordinator coordinator = CreateCoordinator(store, sessions);
        LeasePolicyInput firstPlan = Plan(1005, 45_305);
        LeasePolicyInput nextPlan = Plan(1006, 45_306);

        DynamicLeaseScope first = coordinator.Open(firstPlan, CancellationToken.None);
        FakeDynamicLeasePolicySession firstSession = sessions.Sessions.Single();

        // Model a native provider/sublayer enumeration that exposes a prior
        // dynamic lease filter in the persistent baseline snapshot.
        foreach (WfpFilterIdentity filter in first.Filters)
        {
            store.AddOutOfBandFilter(filter);
        }

        Expect<WfpBaselineOwnershipException>(() => coordinator.Open(nextPlan, CancellationToken.None));
        Assert(sessions.Sessions.Count == 1 && !firstSession.IsClosed,
            "a baseline scope collision allocated a second session or disturbed the first lease");

        first.Close();
        foreach (WfpFilterIdentity filter in first.Filters)
        {
            store.RemoveOutOfBandFilter(filter.Key);
        }

        DynamicLeaseScope afterCleanup = coordinator.Open(nextPlan, CancellationToken.None);
        Assert(sessions.Sessions.Count == 2 && !coordinator.IsIsolated,
            "the coordinator did not recover after the surfaced dynamic rows were removed");
        afterCleanup.Close();
    }

    private static void ValidatesMergedSharedSublayerReadbackAgainstActiveRegistry()
    {
        var store = new FakeWfpPolicyStore();
        var sessions = new FakeDynamicLeasePolicySessionFactory();
        WfpObjectSecurityPolicy policy = WfpObjectSecurityPolicy.CreateProtectedServicePolicy(ServiceSid);
        DynamicLeaseCoordinator coordinator = CreateCoordinator(store, sessions);
        DynamicLeaseScope first = coordinator.Open(Plan(1080, 45_380), CancellationToken.None);
        DynamicLeaseScope second = coordinator.Open(Plan(1081, 45_381), CancellationToken.None);

        SharedSublayerPolicyReadback merged = CreateMergedReadback(store, sessions, policy);
        Assert(merged.Filters!.Count == 4 + first.Filters.Count + second.Filters.Count,
            "the merged fake snapshot did not include the persistent baseline and both live leases");
        Assert(merged.Providers!.Count == 3,
            "the merged fake snapshot did not include the baseline provider and both active lease providers");
        SharedSublayerReadbackContract.Validate(
            merged,
            Applications,
            coordinator.GetActiveReadbackExpectations(),
            policy);

        Expect<WfpBaselineOwnershipException>(() => SharedSublayerReadbackContract.Validate(
            merged with { IsComplete = false }, Applications, coordinator.GetActiveReadbackExpectations(), policy));
        ActiveDynamicLeaseExpectation registered = coordinator.GetActiveReadbackExpectations()[0];
        ActiveDynamicLeaseExpectation[] overBoundRegistry = Enumerable.Repeat(
            registered,
            LeasePolicyCompiler.MaxLeasesPerPlan + 1).ToArray();
        Expect<WfpBaselineOwnershipException>(() => SharedSublayerReadbackContract.Validate(
            merged, Applications, overBoundRegistry, policy));
        Expect<WfpBaselineOwnershipException>(() => SharedSublayerReadbackContract.Validate(
            merged with { Filters = merged.Filters!.Skip(1).ToArray() }, Applications, coordinator.GetActiveReadbackExpectations(), policy));
        Expect<WfpBaselineOwnershipException>(() => SharedSublayerReadbackContract.Validate(
            merged with { Filters = merged.Filters!.Append(merged.Filters.Last()).ToArray() }, Applications, coordinator.GetActiveReadbackExpectations(), policy));
        Expect<WfpBaselineOwnershipException>(() => SharedSublayerReadbackContract.Validate(
            merged with { Providers = merged.Providers!.Append(merged.Providers.Last()).ToArray() }, Applications, coordinator.GetActiveReadbackExpectations(), policy));
        Expect<WfpBaselineOwnershipException>(() => SharedSublayerReadbackContract.Validate(
            merged with { Providers = merged.Providers!.Where(provider => provider.Key != first.Provider.Key).ToArray() },
            Applications, coordinator.GetActiveReadbackExpectations(), policy));

        WfpProviderIdentity wrongProvider = ToWfpProvider(first.Provider) with { Name = "wrong-provider" };
        wrongProvider = wrongProvider with
        {
            NativeProjection = WfpNativeObjectProjection.ForDynamicLeaseProvider(first.Provider with { Name = wrongProvider.Name }),
        };
        Expect<WfpBaselineOwnershipException>(() => SharedSublayerReadbackContract.Validate(
            merged with
            {
                Providers = merged.Providers!.Select(provider => provider.Key == wrongProvider.Key ? wrongProvider : provider).ToArray(),
            },
            Applications, coordinator.GetActiveReadbackExpectations(), policy));

        WfpFilterIdentity dynamicFilter = first.Filters[0];
        WfpFilterIdentity emptyKeyFilter = dynamicFilter with { Key = Guid.Empty };
        emptyKeyFilter = emptyKeyFilter with { NativeProjection = WfpNativeObjectProjection.ForFilter(emptyKeyFilter) };
        ActiveDynamicLeaseExpectation[] emptyKeyRegistry = coordinator.GetActiveReadbackExpectations()
            .Select(lease => lease.LeaseId == first.LeaseId
                ? lease with
                {
                    Filters = Array.AsReadOnly(lease.Filters
                        .Select(filter => filter.Key == dynamicFilter.Key ? emptyKeyFilter : filter)
                        .ToArray()),
                }
                : lease)
            .ToArray();
        WfpFilterIdentity[] emptyKeyFilters = merged.Filters!
            .Select(filter => filter.Key == dynamicFilter.Key ? emptyKeyFilter : filter)
            .ToArray();
        Expect<WfpBaselineOwnershipException>(() => SharedSublayerReadbackContract.Validate(
            merged with { Filters = emptyKeyFilters }, Applications, emptyKeyRegistry, policy));

        WfpFilterIdentity external = dynamicFilter with
        {
            Key = Guid.NewGuid(),
            ProviderKey = Guid.NewGuid(),
            Name = "external-filter",
            NativeProjection = null,
        };
        external = external with { NativeProjection = WfpNativeObjectProjection.ForFilter(external) };
        Expect<WfpBaselineOwnershipException>(() => SharedSublayerReadbackContract.Validate(
            merged with { Filters = merged.Filters!.Append(external).ToArray() }, Applications, coordinator.GetActiveReadbackExpectations(), policy));

        WfpFilterIdentity wrongSublayer = dynamicFilter with { SublayerKey = Guid.NewGuid() };
        wrongSublayer = wrongSublayer with { NativeProjection = WfpNativeObjectProjection.ForFilter(wrongSublayer) };
        Expect<WfpBaselineOwnershipException>(() => SharedSublayerReadbackContract.Validate(
            merged with { Filters = merged.Filters!.Select(filter => filter.Key == dynamicFilter.Key ? wrongSublayer : filter).ToArray() },
            Applications, coordinator.GetActiveReadbackExpectations(), policy));

        WfpFilterIdentity persistentLeaseFilter = dynamicFilter with { Persistent = true };
        persistentLeaseFilter = persistentLeaseFilter with
        {
            NativeProjection = WfpNativeObjectProjection.ForFilter(persistentLeaseFilter),
        };
        Expect<WfpBaselineOwnershipException>(() => SharedSublayerReadbackContract.Validate(
            merged with
            {
                Filters = merged.Filters!.Select(filter => filter.Key == dynamicFilter.Key ? persistentLeaseFilter : filter).ToArray(),
            },
            Applications, coordinator.GetActiveReadbackExpectations(), policy));

        var badAcl = merged.SecurityDescriptors!.ToDictionary(entry => entry.Key, entry => entry.Value);
        WfpPolicyObjectKey dynamicFilterKey = new(WfpPolicyObjectKind.Filter, dynamicFilter.Key);
        badAcl[dynamicFilterKey] = Descriptor("O:SYG:SYD:(A;;GA;;;WD)");
        Expect<WfpBaselineOwnershipException>(() => SharedSublayerReadbackContract.Validate(
            merged with { SecurityDescriptors = badAcl }, Applications, coordinator.GetActiveReadbackExpectations(), policy));
        var missingAcl = merged.SecurityDescriptors!.Where(entry => entry.Key != dynamicFilterKey)
            .ToDictionary(entry => entry.Key, entry => entry.Value);
        Expect<WfpBaselineOwnershipException>(() => SharedSublayerReadbackContract.Validate(
            merged with { SecurityDescriptors = missingAcl }, Applications, coordinator.GetActiveReadbackExpectations(), policy));

        first.Close();
        SharedSublayerPolicyReadback afterFirstClose = CreateMergedReadback(store, sessions, policy);
        Assert(afterFirstClose.Filters!.All(filter => first.Filters.All(closed => closed.Key != filter.Key)),
            "a closed lease filter remained in the merged readback");
        SharedSublayerReadbackContract.Validate(
            afterFirstClose,
            Applications,
            coordinator.GetActiveReadbackExpectations(),
            policy);
        Expect<WfpBaselineOwnershipException>(() => SharedSublayerReadbackContract.Validate(
            afterFirstClose with
            {
                Filters = afterFirstClose.Filters!.Concat(first.Filters).ToArray(),
                Providers = afterFirstClose.Providers!.Append(ToWfpProvider(first.Provider)).ToArray(),
                SecurityDescriptors = AddLeaseAcl(afterFirstClose.SecurityDescriptors!, first, policy),
            },
            Applications,
            coordinator.GetActiveReadbackExpectations(),
            policy));

        second.Close();
        SharedSublayerPolicyReadback baselineOnly = CreateMergedReadback(store, sessions, policy);
        Assert(baselineOnly.Filters!.Count == 4 && baselineOnly.Providers!.Count == 1,
            "closed leases remained in the merged readback");
        SharedSublayerReadbackContract.Validate(baselineOnly, Applications, coordinator.GetActiveReadbackExpectations(), policy);
    }

    private static SharedSublayerPolicyReadback CreateMergedReadback(
        FakeWfpPolicyStore store,
        FakeDynamicLeasePolicySessionFactory sessions,
        WfpObjectSecurityPolicy policy)
    {
        WfpPolicySnapshot baseline = store.ReadSnapshot(
            WfpServicePolicyIdentity.ProviderKey,
            WfpServicePolicyIdentity.SublayerKey);
        FakeDynamicLeasePolicySession[] active = sessions.Sessions.Where(session => !session.IsClosed).ToArray();
        WfpProviderIdentity[] providers = new[] { baseline.Provider! }
            .Concat(active.Where(session => session.Provider is not null).Select(session => ToWfpProvider(session.Provider!)))
            .ToArray();
        WfpFilterIdentity[] filters = baseline.Filters
            .Concat(active.SelectMany(session => session.Filters.Values))
            .OrderBy(filter => filter.Key)
            .ToArray();
        var descriptors = new Dictionary<WfpPolicyObjectKey, SecurityDescriptorSnapshot>
        {
            [new(WfpPolicyObjectKind.Provider, WfpServicePolicyIdentity.ProviderKey)] = Descriptor(policy.ProviderSddl),
            [new(WfpPolicyObjectKind.Sublayer, WfpServicePolicyIdentity.SublayerKey)] = Descriptor(policy.SublayerSddl),
        };
        foreach (WfpProviderIdentity provider in providers.Where(provider => provider.Key != WfpServicePolicyIdentity.ProviderKey))
        {
            descriptors.Add(new WfpPolicyObjectKey(WfpPolicyObjectKind.Provider, provider.Key), Descriptor(policy.ProviderSddl));
        }
        foreach (WfpFilterIdentity filter in filters)
        {
            descriptors.Add(new WfpPolicyObjectKey(WfpPolicyObjectKind.Filter, filter.Key), Descriptor(policy.FilterSddl));
        }
        return new SharedSublayerPolicyReadback(
            IsComplete: true,
            Array.AsReadOnly(providers),
            baseline.Sublayer,
            Array.AsReadOnly(filters),
            descriptors);
    }

    private static WfpProviderIdentity ToWfpProvider(DynamicLeaseProviderIdentity provider) =>
        new(provider.Key, provider.Name, provider.Description, "null", provider.NativeProjection);

    private static IReadOnlyDictionary<WfpPolicyObjectKey, SecurityDescriptorSnapshot> AddLeaseAcl(
        IReadOnlyDictionary<WfpPolicyObjectKey, SecurityDescriptorSnapshot> source,
        DynamicLeaseScope lease,
        WfpObjectSecurityPolicy policy)
    {
        var result = source.ToDictionary(entry => entry.Key, entry => entry.Value);
        result.Add(new WfpPolicyObjectKey(WfpPolicyObjectKind.Provider, lease.Provider.Key), Descriptor(policy.ProviderSddl));
        foreach (WfpFilterIdentity filter in lease.Filters)
        {
            result.Add(new WfpPolicyObjectKey(WfpPolicyObjectKind.Filter, filter.Key), Descriptor(policy.FilterSddl));
        }
        return result;
    }

    private static void RejectsInvalidDynamicProviderAndAclReadback()
    {
        var missingProviderFactory = new FakeDynamicLeasePolicySessionFactory
        {
            ConfigureNewSession = session => session.ReadbackOverride = current => current with { Provider = null },
        };
        DynamicLeaseCoordinator missingProvider = CreateCoordinator(new FakeWfpPolicyStore(), missingProviderFactory);
        Expect<WfpDynamicLeaseException>(() => missingProvider.Open(Plan(1007, 45_307), CancellationToken.None));
        Assert(missingProviderFactory.Sessions.Single().IsClosed,
            "a missing dynamic provider readback did not close its session");

        var wrongProviderFactory = new FakeDynamicLeasePolicySessionFactory
        {
            ConfigureNewSession = session => session.ReadbackOverride = current =>
            {
                DynamicLeaseProviderIdentity provider = current.Provider!;
                DynamicLeaseProviderIdentity changed = provider with { Key = Guid.NewGuid() };
                return current with
                {
                    Provider = changed with { NativeProjection = WfpNativeObjectProjection.ForDynamicLeaseProvider(changed) },
                };
            },
        };
        DynamicLeaseCoordinator wrongProvider = CreateCoordinator(new FakeWfpPolicyStore(), wrongProviderFactory);
        Expect<WfpDynamicLeaseException>(() => wrongProvider.Open(Plan(1008, 45_308), CancellationToken.None));
        Assert(wrongProviderFactory.Sessions.Single().IsClosed,
            "a mismatched dynamic provider readback did not close its session");

        var missingAclFactory = new FakeDynamicLeasePolicySessionFactory
        {
            ConfigureNewSession = session => session.ReadbackOverride = current => current with
            {
                SecurityDescriptors = current.SecurityDescriptors!
                    .Where(entry => entry.Key.Kind != WfpPolicyObjectKind.Provider)
                    .ToDictionary(entry => entry.Key, entry => entry.Value),
            },
        };
        DynamicLeaseCoordinator missingAcl = CreateCoordinator(new FakeWfpPolicyStore(), missingAclFactory);
        Expect<WfpDynamicLeaseException>(() => missingAcl.Open(Plan(1009, 45_309), CancellationToken.None));
        Assert(missingAclFactory.Sessions.Single().IsClosed,
            "missing dynamic provider ACL evidence did not close its session");

        var broadAclFactory = new FakeDynamicLeasePolicySessionFactory
        {
            ConfigureNewSession = session => session.ReadbackOverride = current =>
            {
                var descriptors = current.SecurityDescriptors!.ToDictionary(entry => entry.Key, entry => entry.Value);
                WfpPolicyObjectKey providerKey = new(WfpPolicyObjectKind.Provider, current.Provider!.Key);
                descriptors[providerKey] = Descriptor("O:SYG:SYD:(A;;GA;;;WD)");
                return current with { SecurityDescriptors = descriptors };
            },
        };
        DynamicLeaseCoordinator broadAcl = CreateCoordinator(new FakeWfpPolicyStore(), broadAclFactory);
        Expect<WfpDynamicLeaseException>(() => broadAcl.Open(Plan(1013, 45_313), CancellationToken.None));
        Assert(broadAclFactory.Sessions.Single().IsClosed,
            "a broad dynamic provider ACL did not close its session");
    }

    private static void RejectsMalformedPlansBeforeSessionCreation()
    {
        var store = new FakeWfpPolicyStore();
        var sessions = new FakeDynamicLeasePolicySessionFactory();
        DynamicLeaseCoordinator coordinator = CreateCoordinator(store, sessions);
        LeasePolicyInput valid = Plan(1020, 45_320);

        Expect<ArgumentException>(() => coordinator.Open(valid with { LeaseId = Guid.Empty }, CancellationToken.None));
        Expect<ArgumentException>(() => coordinator.Open(valid with { LeaseSid = "not-a-sid" }, CancellationToken.None));
        Expect<ArgumentException>(() => coordinator.Open(valid with { LeaseSid = "S-1-5-18" }, CancellationToken.None));
        Expect<ArgumentException>(() => coordinator.Open(
            valid with { PinnedPublicAddresses = Enumerable.Repeat("93.184.216.34", LeasePolicyCompiler.MaxPinnedAddressesPerLease + 1).ToArray() },
            CancellationToken.None));
        Expect<ArgumentException>(() => coordinator.Open(valid with { BrowserAppIdHex = "AABBCCDD" }, CancellationToken.None));

        Assert(sessions.Sessions.Count == 0, "an invalid dynamic plan reached session creation");
    }

    private static void ClosesAfterAddReadbackAndCancellationFailures()
    {
        var store = new FakeWfpPolicyStore();
        var addFailureSessions = new FakeDynamicLeasePolicySessionFactory
        {
            ConfigureNewSession = session => session.FailAddAt = 2,
        };
        DynamicLeaseCoordinator addFailure = CreateCoordinator(store, addFailureSessions);
        Expect<InvalidOperationException>(() => addFailure.Open(Plan(1030, 45_330), CancellationToken.None));
        Assert(addFailureSessions.Sessions.Single().IsClosed, "an apply failure did not close its partial dynamic session");

        var missingReadbackSessions = new FakeDynamicLeasePolicySessionFactory
        {
            ConfigureNewSession = session => session.ReadbackOverride = current => current with
            {
                Filters = current.Filters!.Skip(1).ToArray(),
            },
        };
        DynamicLeaseCoordinator missingReadback = CreateCoordinator(new FakeWfpPolicyStore(), missingReadbackSessions);
        Expect<WfpDynamicLeaseException>(() => missingReadback.Open(Plan(1031, 45_331), CancellationToken.None));
        Assert(missingReadbackSessions.Sessions.Single().IsClosed, "a missing-filter readback did not close its dynamic session");

        var wrongProjectionSessions = new FakeDynamicLeasePolicySessionFactory
        {
            ConfigureNewSession = session => session.ReadbackOverride = current =>
            {
                WfpFilterIdentity first = current.Filters![0];
                WfpFilterIdentity changed = first with { Description = "wrong readback" };
                WfpFilterIdentity[] filters = current.Filters.ToArray();
                filters[0] = changed with { NativeProjection = WfpNativeObjectProjection.ForFilter(changed) };
                return current with { Filters = filters };
            },
        };
        DynamicLeaseCoordinator wrongProjection = CreateCoordinator(new FakeWfpPolicyStore(), wrongProjectionSessions);
        Expect<WfpDynamicLeaseException>(() => wrongProjection.Open(Plan(1032, 45_332), CancellationToken.None));
        Assert(wrongProjectionSessions.Sessions.Single().IsClosed, "a mismatched native projection did not close its session");

        using var cancellation = new CancellationTokenSource();
        var cancellationSessions = new FakeDynamicLeasePolicySessionFactory
        {
            ConfigureNewSession = session => session.AfterAdd = count =>
            {
                if (count == 2)
                {
                    cancellation.Cancel();
                }
            },
        };
        DynamicLeaseCoordinator canceled = CreateCoordinator(new FakeWfpPolicyStore(), cancellationSessions);
        Expect<OperationCanceledException>(() => canceled.Open(Plan(1033, 45_333), cancellation.Token));
        Assert(cancellationSessions.Sessions.Single().IsClosed, "cancellation after partial apply did not close its dynamic session");
    }

    private static void RetainsUnclosedHandleAndIsolatesCoordinator()
    {
        var sessions = new FakeDynamicLeasePolicySessionFactory
        {
            ConfigureNewSession = session =>
            {
                session.FailAddAt = 2;
                session.CloseFailuresRemaining = 1;
            },
        };
        DynamicLeaseCoordinator coordinator = CreateCoordinator(new FakeWfpPolicyStore(), sessions);

        Expect<WfpDynamicLeaseCleanupException>(() => coordinator.Open(Plan(1040, 45_340), CancellationToken.None));

        Assert(coordinator.IsIsolated, "a failed cleanup did not isolate the coordinator");
        Assert(coordinator.OrphanedSessionHandleCount == 1 && coordinator.RetainedSessionHandleCount == 1,
            "a failed cleanup lost its session handle");
        Expect<WfpDynamicLeaseException>(() => coordinator.Open(Plan(1041, 45_341), CancellationToken.None));
        Assert(sessions.Sessions.Count == 1, "an isolated coordinator opened another session");
    }

    private static void RejectsDuplicateLeaseAndAllowsRepeatedClose()
    {
        var sessions = new FakeDynamicLeasePolicySessionFactory();
        DynamicLeaseCoordinator coordinator = CreateCoordinator(new FakeWfpPolicyStore(), sessions);
        LeasePolicyInput plan = Plan(1050, 45_350);
        DynamicLeaseScope scope = coordinator.Open(plan, CancellationToken.None);
        Expect<WfpDynamicLeaseException>(() => coordinator.Open(plan, CancellationToken.None));
        Assert(sessions.Sessions.Count == 1, "a duplicate lease ID created another session");

        using var canceled = new CancellationTokenSource();
        canceled.Cancel();
        scope.Close(cancellationToken: canceled.Token);
        scope.Close(cancellationToken: canceled.Token);
        Assert(sessions.Sessions.Single().CloseCalls == 1, "repeated close did not remain idempotent");
        Assert(coordinator.RetainedSessionHandleCount == 0, "a successfully closed lease handle remained tracked");
    }

    private static void RejectsDuplicateSessionIdentityWithoutClosingAmbiguousHandle()
    {
        Guid reusedSessionId = Guid.Parse("c9fd537c-486d-4b85-9780-527a1caf49ea");
        var sessions = new FakeDynamicLeasePolicySessionFactory
        {
            SessionIdForLease = _ => reusedSessionId,
        };
        DynamicLeaseCoordinator coordinator = CreateCoordinator(new FakeWfpPolicyStore(), sessions);
        DynamicLeaseScope first = coordinator.Open(Plan(1055, 45_355), CancellationToken.None);

        Expect<WfpDynamicLeaseException>(() => coordinator.Open(Plan(1056, 45_356), CancellationToken.None));

        Assert(sessions.Sessions.Count == 2, "the duplicate session identity fixture did not reach both opens");
        Assert(!sessions.Sessions[1].IsClosed, "the ambiguous duplicate-session handle was closed unsafely");
        Assert(coordinator.IsIsolated
            && coordinator.OrphanedSessionHandleCount == 1
            && coordinator.RetainedSessionHandleCount == 2,
            "a duplicate session identity did not retain both ownership handles and isolate future opens");
        first.Close();
        Assert(sessions.Sessions[0].IsClosed && !sessions.Sessions[1].IsClosed,
            "closing the first lease incorrectly closed the ambiguous duplicate-session handle");
    }

    private static void RequiresSuccessfulDrainAfterWorkerStart()
    {
        var sessions = new FakeDynamicLeasePolicySessionFactory();
        DynamicLeaseCoordinator coordinator = CreateCoordinator(new FakeWfpPolicyStore(), sessions);
        DynamicLeaseScope scope = coordinator.Open(Plan(1060, 45_360), CancellationToken.None);
        FakeDynamicLeasePolicySession session = sessions.Sessions.Single();
        var order = new List<string>();
        session.EventSink = order;
        scope.MarkWorkerStarted();

        Expect<WfpDynamicLeaseException>(() => scope.Close());
        Assert(!session.IsClosed, "the dynamic session closed without a drain callback");

        Expect<WfpDynamicLeaseException>(() => scope.Close(
            _ =>
            {
                order.Add("drain-failed");
                return new LeaseJobTreeDrainReceipt(scope.LeaseId, JobTerminated: true, ActiveProcessCount: 1);
            }));
        Assert(!session.IsClosed && session.CloseCalls == 0, "a failed drain closed the dynamic session");

        scope.Close(_ =>
        {
            order.Add("drain");
            return new LeaseJobTreeDrainReceipt(scope.LeaseId, JobTerminated: true, ActiveProcessCount: 0);
        });
        Assert(session.IsClosed && order.SequenceEqual(["drain-failed", "drain", "session-close"]),
            "session close did not follow a successful job-tree drain");
    }

    private static void RetainsLeaseWhenNormalCloseFails()
    {
        var sessions = new FakeDynamicLeasePolicySessionFactory
        {
            ConfigureNewSession = session => session.CloseFailuresRemaining = 1,
        };
        DynamicLeaseCoordinator coordinator = CreateCoordinator(new FakeWfpPolicyStore(), sessions);
        DynamicLeaseScope scope = coordinator.Open(Plan(1070, 45_370), CancellationToken.None);
        scope.MarkWorkerStarted();
        LeaseJobTreeDrainReceipt Drain(CancellationToken _) =>
            new(scope.LeaseId, JobTerminated: true, ActiveProcessCount: 0);

        Expect<WfpDynamicLeaseCleanupException>(() => scope.Close(Drain));
        Assert(coordinator.IsIsolated && coordinator.RetainedSessionHandleCount == 1,
            "a failed normal close did not retain the live handle and isolate future opens");
        Expect<WfpDynamicLeaseException>(() => coordinator.Open(Plan(1071, 45_371), CancellationToken.None));

        scope.Close(Drain);
        scope.Close(Drain);
        Assert(sessions.Sessions.Single().IsClosed && sessions.Sessions.Single().CloseCalls == 2,
            "a retry did not close the retained session exactly once after the transient failure");
        Assert(coordinator.RetainedSessionHandleCount == 0 && coordinator.IsIsolated,
            "the retry either lost track of the handle or reopened an isolated coordinator");
    }

    private static DynamicLeaseCoordinator CreateCoordinator(
        FakeWfpPolicyStore store,
        FakeDynamicLeasePolicySessionFactory sessions) =>
        new(
            new PersistentBaselineCoordinator(store),
            Applications,
            sessions,
            WfpObjectSecurityPolicy.CreateProtectedServicePolicy(ServiceSid));

    private static SecurityDescriptorSnapshot Descriptor(string sddl)
    {
        string hash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(sddl))).ToLowerInvariant();
        return new SecurityDescriptorSnapshot(sddl, hash, BinaryLength: 128, DaclPresent: true, HasNullDacl: false);
    }

    private static LeasePolicyInput Plan(int rid, int port) =>
        new(
            Guid.Parse($"00000000-0000-0000-0000-{rid:000000000000}"),
            LeasePrincipalKind.UserSid,
            $"S-1-5-21-100-200-300-{rid}",
            "01020304",
            "05060708",
            port,
            "1.1.1.1",
            ["93.184.216.34", "142.250.72.14"]);

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

internal sealed class FakeDynamicLeasePolicySessionFactory : IDynamicLeasePolicySessionFactory
{
    public List<FakeDynamicLeasePolicySession> Sessions { get; } = [];
    public Action<FakeDynamicLeasePolicySession>? ConfigureNewSession { get; init; }
    public Func<Guid, Guid>? SessionIdForLease { get; init; }

    public IDynamicLeasePolicySession Open(Guid leaseId)
    {
        var session = new FakeDynamicLeasePolicySession(leaseId, this.SessionIdForLease?.Invoke(leaseId) ?? Guid.NewGuid());
        this.ConfigureNewSession?.Invoke(session);
        this.Sessions.Add(session);
        return session;
    }
}

internal sealed class FakeDynamicLeasePolicySession(Guid leaseId, Guid sessionId) : IDynamicLeasePolicySession
{
    private readonly Dictionary<Guid, WfpFilterIdentity> filters = [];
    private int addCount;

    public Guid LeaseId { get; } = leaseId;
    public Guid SessionId { get; } = sessionId;
    public DynamicLeaseProviderIdentity? Provider { get; private set; }
    public int FailAddAt { get; set; }
    public int CloseFailuresRemaining { get; set; }
    public int CloseCalls { get; private set; }
    public bool IsClosed { get; private set; }
    public Action<int>? AfterAdd { get; set; }
    public List<string>? EventSink { get; set; }
    public Func<DynamicLeaseSessionReadback, DynamicLeaseSessionReadback>? ReadbackOverride { get; set; }
    public IReadOnlyDictionary<Guid, WfpFilterIdentity> Filters => this.filters;

    public void AddProvider(DynamicLeaseProviderIdentity provider)
    {
        this.RequireOpen();
        if (this.Provider is not null || provider.LeaseId != this.LeaseId)
        {
            throw new InvalidOperationException("fixture dynamic provider identity conflict");
        }
        this.Provider = provider;
    }

    public void AddFilter(WfpFilterIdentity filter)
    {
        this.RequireOpen();
        if (this.Provider is null || filter.ProviderKey != this.Provider.Key
            || filter.SublayerKey != WfpServicePolicyIdentity.SublayerKey || filter.Persistent)
        {
            throw new InvalidOperationException("fixture dynamic filter is outside provider/sublayer/lifetime scope");
        }
        this.addCount++;
        if (this.FailAddAt == this.addCount)
        {
            throw new InvalidOperationException("fixture dynamic filter-add failure");
        }
        this.filters.Add(filter.Key, filter);
        this.AfterAdd?.Invoke(this.addCount);
    }

    public DynamicLeaseSessionReadback Readback()
    {
        this.RequireOpen();
        Dictionary<WfpPolicyObjectKey, SecurityDescriptorSnapshot> descriptors = [];
        if (this.Provider is { } provider)
        {
            descriptors.Add(
                new WfpPolicyObjectKey(WfpPolicyObjectKind.Provider, provider.Key),
                DescriptorFor(WfpObjectSecurityPolicy.CreateProtectedServicePolicy("S-1-5-80-1-2-3-4-5").ProviderSddl));
        }
        foreach (WfpFilterIdentity filter in this.filters.Values)
        {
            descriptors.Add(
                new WfpPolicyObjectKey(WfpPolicyObjectKind.Filter, filter.Key),
                DescriptorFor(WfpObjectSecurityPolicy.CreateProtectedServicePolicy("S-1-5-80-1-2-3-4-5").FilterSddl));
        }
        var readback = new DynamicLeaseSessionReadback(
            this.LeaseId,
            this.SessionId,
            IsComplete: true,
            this.Provider,
            descriptors,
            Array.AsReadOnly(this.filters.Values.OrderBy(filter => filter.Key).ToArray()));
        return this.ReadbackOverride?.Invoke(readback) ?? readback;
    }

    public void Close()
    {
        this.CloseCalls++;
        if (this.CloseFailuresRemaining > 0)
        {
            this.CloseFailuresRemaining--;
            throw new InvalidOperationException("fixture dynamic session close failure");
        }
        if (this.IsClosed)
        {
            return;
        }
        this.EventSink?.Add("session-close");
        this.filters.Clear();
        this.Provider = null;
        this.IsClosed = true;
    }

    private static SecurityDescriptorSnapshot DescriptorFor(string sddl)
    {
        string hash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(sddl))).ToLowerInvariant();
        return new SecurityDescriptorSnapshot(sddl, hash, BinaryLength: 128, DaclPresent: true, HasNullDacl: false);
    }

    private void RequireOpen()
    {
        if (this.IsClosed)
        {
            throw new ObjectDisposedException(nameof(FakeDynamicLeasePolicySession));
        }
    }
}
