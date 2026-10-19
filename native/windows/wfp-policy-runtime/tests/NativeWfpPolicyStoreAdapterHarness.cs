using System.Collections.ObjectModel;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using WfpPolicy.Runtime;
using WfpPolicy.NativeReadback;
using WfpPolicyPlan;

namespace WfpPolicy.Runtime.Harness;

internal static class NativeWfpPolicyStoreAdapterHarness
{
    private const string ServiceSid = "S-1-5-80-1-2-3-4-5";
    private static readonly ProtectedApplicationInput[] Applications =
    [
        new(ProtectedApplicationRole.Browser, "01020304"),
        new(ProtectedApplicationRole.Worker, "05060708"),
    ];

    internal static void Run()
    {
        RequiresProtectedSystemOwnershipAndBoundedWfpRights();
        CreatesAndReadsBackWithExactServiceAcl();
        RejectsWrongAclBeforeMutation();
        RejectsNoncanonicalAppIdBeforeMutation();
        RejectsIncompleteScopeBeforeMutation();
        RejectsMissingReadbackProjectionBeforeMutation();
        RejectsTransactionReadbackMismatchBeforeCommit();
        RejectsOutOfScopeKeys();
        DisposalAbortsUncommittedTransaction();
    }

    private static void RequiresProtectedSystemOwnershipAndBoundedWfpRights()
    {
        WfpObjectSecurityPolicy security = WfpObjectSecurityPolicy.CreateProtectedServicePolicy(ServiceSid);
        const int expectedGenericRights = unchecked((int)0xe0000000u); // GENERIC_READ | GENERIC_WRITE | GENERIC_EXECUTE
        string[] descriptors = [security.ProviderSddl, security.SublayerSddl, security.FilterSddl];
        foreach (string sddl in descriptors)
        {
            var descriptor = new RawSecurityDescriptor(sddl);
            Assert(descriptor.Owner?.Value == "S-1-5-18", "LocalSystem must own the WFP object so the service SID does not own its DACL");
            Assert(descriptor.Group?.Value == "S-1-5-18", "the WFP object group must be LocalSystem");
            Assert(descriptor.ControlFlags.HasFlag(ControlFlags.DiscretionaryAclProtected), "WFP object DACL must not inherit broader access");
            Assert(descriptor.DiscretionaryAcl?.Count == 2, "WFP object DACL must contain exactly the LocalSystem and service ACEs");

            var allowedSids = new HashSet<string>(StringComparer.Ordinal);
            foreach (GenericAce? entry in descriptor.DiscretionaryAcl!)
            {
                Assert(entry is CommonAce ace && ace.AceQualifier == AceQualifier.AccessAllowed,
                    "WFP object DACL contains an unsupported ACE type");
                var allowed = (CommonAce)entry;
                Assert(allowed.AceFlags == AceFlags.None, "WFP object ACEs must not inherit to other objects");
                Assert(allowed.AccessMask == expectedGenericRights, "WFP object ACE grants rights outside the documented generic read/write/execute set");
                allowedSids.Add(allowed.SecurityIdentifier.Value);
            }

            Assert(allowedSids.SetEquals(["S-1-5-18", ServiceSid]), "WFP object ACL grants a right to an unexpected principal");
        }

        Expect<WfpBaselineOwnershipException>(() => (security with
        {
            FilterSddl = security.FilterSddl.Replace("GRGWGX", "GA", StringComparison.Ordinal),
        }).Validate());
    }

    private static void CreatesAndReadsBackWithExactServiceAcl()
    {
        var api = new FakeNativeWfpPolicyApi();
        WfpObjectSecurityPolicy security = WfpObjectSecurityPolicy.CreateProtectedServicePolicy(ServiceSid);
        var store = new NativeWfpPolicyStoreAdapter(api, security);

        new PersistentBaselineCoordinator(store).EnsureReady(Applications, CancellationToken.None);

        WfpPolicySnapshot snapshot = store.ReadSnapshot(WfpServicePolicyIdentity.ProviderKey, WfpServicePolicyIdentity.SublayerKey);
        Assert(snapshot.Provider == WfpServicePolicyIdentity.Provider, "provider was not read back exactly");
        Assert(snapshot.Sublayer == WfpServicePolicyIdentity.Sublayer, "sublayer was not read back exactly");
        Assert(snapshot.Filters.Count == 4, "expected four persistent AppID baseline filters");
        Assert(api.CommitCount == 1, "baseline did not commit exactly once");
        Assert(api.TransactionReadCount >= 3, "the adapter did not read the transaction before and after staging");
        Assert(api.AppliedSecurityDescriptors.Count == 6, "every added provider, sublayer, and filter must receive an ACL");
        Assert(api.AppliedSecurityDescriptors.All(value => value == security.ProviderSddl), "an add used a different ACL than the approved service policy");
    }

    private static void RejectsWrongAclBeforeMutation()
    {
        WfpObjectSecurityPolicy security = WfpObjectSecurityPolicy.CreateProtectedServicePolicy(ServiceSid);
        var api = new FakeNativeWfpPolicyApi();
        api.SeedProvider(WfpServicePolicyIdentity.Provider, Descriptor(security.ProviderSddl + "(A;;GA;;;WD)"));
        var store = new NativeWfpPolicyStoreAdapter(api, security);

        Expect<WfpBaselineOwnershipException>(() => new PersistentBaselineCoordinator(store)
            .EnsureReady(Applications, CancellationToken.None));

        Assert(api.MutationCount == 0 && api.CommitCount == 0, "a provider ACL mismatch reached mutation");
    }

    private static void RejectsNoncanonicalAppIdBeforeMutation()
    {
        WfpObjectSecurityPolicy security = WfpObjectSecurityPolicy.CreateProtectedServicePolicy(ServiceSid);
        var api = new FakeNativeWfpPolicyApi();
        api.SeedProvider(WfpServicePolicyIdentity.Provider, Descriptor(security.ProviderSddl));
        api.SeedSublayer(WfpServicePolicyIdentity.Sublayer, Descriptor(security.SublayerSddl));

        const string noncanonicalAppId = "AABBCCDD";
        string identityHash = Convert.ToHexString(SHA256.HashData(Convert.FromHexString(noncanonicalAppId)))[..16];
        var rule = new LeasePolicyRule(
            RuleId: $"default-deny-browser-{identityHash}-v4",
            Purpose: "Persistent catch-all block for every browser process from this protected AppID; higher-weight exact lease permits are the only intended exceptions.",
            AddressFamily: LeasePolicyAddressFamily.IPv4,
            Action: LeasePolicyAction.Block,
            WeightRangeIndex: LeasePolicyCompiler.DefaultDenyWeightRangeIndex,
            Lifetime: LeasePolicyLifetime.PersistentDefaultDeny,
            LeaseId: null,
            AppIdHex: noncanonicalAppId,
            LeaseSid: null,
            IdentityCondition: "ALE_APP_ID",
            RemoteAddress: null,
            Protocol: null,
            RemotePort: null,
            ClearActionRight: false);
        var filter = new WfpFilterIdentity(
            WfpServicePolicyIdentity.FilterKey(rule.RuleId),
            WfpServicePolicyIdentity.ProviderKey,
            WfpServicePolicyIdentity.SublayerKey,
            WfpServicePolicyIdentity.FilterNamePrefix + rule.RuleId,
            rule.Purpose,
            Persistent: true,
            rule);
        api.SeedFilter(filter, Descriptor(security.FilterSddl));

        var store = new NativeWfpPolicyStoreAdapter(api, security);
        Expect<WfpBaselineOwnershipException>(() => store.ReadSnapshot(
            WfpServicePolicyIdentity.ProviderKey,
            WfpServicePolicyIdentity.SublayerKey));

        Assert(api.BeginTransactionCount == 0 && api.MutationCount == 0, "a noncanonical AppID reached transaction mutation");
    }

    private static void RejectsIncompleteScopeBeforeMutation()
    {
        WfpObjectSecurityPolicy security = WfpObjectSecurityPolicy.CreateProtectedServicePolicy(ServiceSid);
        var api = new FakeNativeWfpPolicyApi { ScopeComplete = false };
        var store = new NativeWfpPolicyStoreAdapter(api, security);

        Expect<WfpBaselineOwnershipException>(() => new PersistentBaselineCoordinator(store)
            .EnsureReady(Applications, CancellationToken.None));

        Assert(api.BeginTransactionCount == 0, "an incomplete service-scope readback started a mutation transaction");
    }

    private static void RejectsMissingReadbackProjectionBeforeMutation()
    {
        WfpObjectSecurityPolicy security = WfpObjectSecurityPolicy.CreateProtectedServicePolicy(ServiceSid);
        var api = new FakeNativeWfpPolicyApi { OmitNativeReadbackProjection = true };
        var store = new NativeWfpPolicyStoreAdapter(api, security);

        Expect<WfpBaselineOwnershipException>(() => new PersistentBaselineCoordinator(store)
            .EnsureReady(Applications, CancellationToken.None));

        Assert(api.BeginTransactionCount == 0 && api.MutationCount == 0,
            "a native snapshot without its canonical readback projection reached mutation");
    }

    private static void RejectsTransactionReadbackMismatchBeforeCommit()
    {
        WfpObjectSecurityPolicy security = WfpObjectSecurityPolicy.CreateProtectedServicePolicy(ServiceSid);
        var api = new FakeNativeWfpPolicyApi { CorruptTransactionReadbackAfterMutation = true };
        var store = new NativeWfpPolicyStoreAdapter(api, security);

        Expect<WfpBaselineVerificationException>(() => new PersistentBaselineCoordinator(store)
            .EnsureReady(Applications, CancellationToken.None));

        Assert(api.CommitCount == 0, "a mismatched transaction readback committed WFP objects");
        Assert(api.AbortCount == 1, "a failed pre-commit readback did not abort the transaction");
        Assert(api.ReadSnapshot(WfpServicePolicyIdentity.ProviderKey, WfpServicePolicyIdentity.SublayerKey).Snapshot.Provider is null,
            "an aborted native transaction leaked staged provider state");
    }

    private static void RejectsOutOfScopeKeys()
    {
        WfpObjectSecurityPolicy security = WfpObjectSecurityPolicy.CreateProtectedServicePolicy(ServiceSid);
        var store = new NativeWfpPolicyStoreAdapter(new FakeNativeWfpPolicyApi(), security);
        Expect<WfpBaselineOwnershipException>(() => store.ReadSnapshot(Guid.NewGuid(), Guid.NewGuid()));
    }

    private static void DisposalAbortsUncommittedTransaction()
    {
        WfpObjectSecurityPolicy security = WfpObjectSecurityPolicy.CreateProtectedServicePolicy(ServiceSid);
        var api = new FakeNativeWfpPolicyApi();
        var store = new NativeWfpPolicyStoreAdapter(api, security);
        using (store.BeginTransaction())
        {
        }
        Assert(api.AbortCount == 1, "disposing an open transaction did not abort it");
        Assert(api.CommitCount == 0, "disposing an open transaction committed it");
    }

    private static SecurityDescriptorSnapshot Descriptor(string sddl)
    {
        byte[] digest = SHA256.HashData(Encoding.UTF8.GetBytes(sddl));
        return new SecurityDescriptorSnapshot(
            sddl,
            Convert.ToHexString(digest).ToLowerInvariant(),
            BinaryLength: 64,
            DaclPresent: true,
            HasNullDacl: false);
    }

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

    private sealed class FakeNativeWfpPolicyApi : INativeWfpPolicyApi
    {
        private WfpProviderIdentity? provider;
        private WfpSublayerIdentity? sublayer;
        private readonly Dictionary<Guid, WfpFilterIdentity> filters = [];
        private readonly Dictionary<WfpPolicyObjectKey, SecurityDescriptorSnapshot> securityDescriptors = [];

        internal bool ScopeComplete { get; init; } = true;
        internal bool OmitNativeReadbackProjection { get; init; }
        internal bool CorruptTransactionReadbackAfterMutation { get; init; }
        internal int BeginTransactionCount { get; private set; }
        internal int TransactionReadCount { get; private set; }
        internal int MutationCount { get; private set; }
        internal int CommitCount { get; private set; }
        internal int AbortCount { get; private set; }
        internal List<string> AppliedSecurityDescriptors { get; } = [];

        public NativeWfpPolicyReadback ReadSnapshot(Guid providerKey, Guid sublayerKey) =>
            this.CreateReadback(this.provider, this.sublayer, this.filters.Values, this.securityDescriptors);

        public INativeWfpPolicyTransaction BeginTransaction()
        {
            this.BeginTransactionCount++;
            return new FakeTransaction(this);
        }

        internal void SeedProvider(WfpProviderIdentity value, SecurityDescriptorSnapshot descriptor)
        {
            this.provider = value with { NativeProjection = WfpNativeObjectProjection.ForProvider(value) };
            this.securityDescriptors[new WfpPolicyObjectKey(WfpPolicyObjectKind.Provider, value.Key)] = descriptor;
        }

        internal void SeedSublayer(WfpSublayerIdentity value, SecurityDescriptorSnapshot descriptor)
        {
            this.sublayer = value with { NativeProjection = WfpNativeObjectProjection.ForSublayer(value) };
            this.securityDescriptors[new WfpPolicyObjectKey(WfpPolicyObjectKind.Sublayer, value.Key)] = descriptor;
        }

        internal void SeedFilter(WfpFilterIdentity value, SecurityDescriptorSnapshot descriptor)
        {
            WfpFilterIdentity projected = value with { NativeProjection = WfpNativeObjectProjection.ForFilter(value) };
            this.filters.Add(projected.Key, projected);
            this.securityDescriptors[new WfpPolicyObjectKey(WfpPolicyObjectKind.Filter, projected.Key)] = descriptor;
        }

        private NativeWfpPolicyReadback CreateReadback(
            WfpProviderIdentity? providerValue,
            WfpSublayerIdentity? sublayerValue,
            IEnumerable<WfpFilterIdentity> filterValues,
            IReadOnlyDictionary<WfpPolicyObjectKey, SecurityDescriptorSnapshot> descriptorValues,
            bool corrupt = false)
        {
            this.TransactionReadCount++;
            WfpFilterIdentity[] selected = filterValues
                .Where(filter => filter.ProviderKey == WfpServicePolicyIdentity.ProviderKey
                    || filter.SublayerKey == WfpServicePolicyIdentity.SublayerKey)
                .OrderBy(filter => filter.Key)
                .ToArray();
            if (corrupt && selected.Length > 0)
            {
                selected = selected[..^1];
            }
            WfpPolicySnapshot snapshot = new(
                providerValue,
                sublayerValue,
                Array.AsReadOnly(selected));
            if (!this.OmitNativeReadbackProjection)
            {
                snapshot = snapshot with
                {
                    NativeReadbackProjection = CreateProjection(providerValue, sublayerValue, selected),
                };
            }
            var descriptors = new Dictionary<WfpPolicyObjectKey, SecurityDescriptorSnapshot>();
            if (providerValue is not null)
            {
                CopyDescriptor(WfpPolicyObjectKind.Provider, providerValue.Key);
            }
            if (sublayerValue is not null)
            {
                CopyDescriptor(WfpPolicyObjectKind.Sublayer, sublayerValue.Key);
            }
            foreach (WfpFilterIdentity filter in selected)
            {
                CopyDescriptor(WfpPolicyObjectKind.Filter, filter.Key);
            }

            return new NativeWfpPolicyReadback(
                snapshot,
                new ReadOnlyDictionary<WfpPolicyObjectKey, SecurityDescriptorSnapshot>(descriptors),
                this.ScopeComplete,
                this.ScopeComplete ? null : "fake omitted an ACL-visible service object");

            void CopyDescriptor(WfpPolicyObjectKind kind, Guid key)
            {
                WfpPolicyObjectKey objectKey = new(kind, key);
                if (descriptorValues.TryGetValue(objectKey, out SecurityDescriptorSnapshot? value))
                {
                    descriptors.Add(objectKey, value);
                }
            }
        }

        private static WfpNativeReadbackProjection CreateProjection(
            WfpProviderIdentity? providerValue,
            WfpSublayerIdentity? sublayerValue,
            IEnumerable<WfpFilterIdentity> filterValues)
        {
            var objects = new List<WfpNativeReadbackObjectProjection>();
            Add("FWPM_PROVIDER0", providerValue?.Key, providerValue?.NativeProjection);
            Add("FWPM_SUBLAYER0", sublayerValue?.Key, sublayerValue?.NativeProjection);
            foreach (WfpFilterIdentity filter in filterValues)
            {
                Add("FWPM_FILTER0", filter.Key, filter.NativeProjection);
            }

            var source = new WfpSnapshot(
                DateTimeOffset.UnixEpoch,
                Array.Empty<ProviderSnapshot>(),
                Array.Empty<SublayerSnapshot>(),
                Array.Empty<FilterSnapshot>(),
                Array.Empty<SnapshotIssue>());
            WfpNativeReadbackObjectProjection[] ordered = objects
                .OrderBy(item => item.ObjectKind, StringComparer.Ordinal)
                .ThenBy(item => item.ObjectKey, StringComparer.Ordinal)
                .ToArray();
            return new WfpNativeReadbackProjection(
                WfpNativeReadbackProjection.CurrentSchemaVersion,
                source,
                ordered);

            void Add(string kind, Guid? key, WfpNativeObjectProjection? projection)
            {
                if (key is not Guid objectKey)
                {
                    return;
                }
                WfpNativeObjectProjection actual = projection
                    ?? throw new InvalidOperationException("The fake native API needs an object projection.");
                objects.Add(new WfpNativeReadbackObjectProjection(
                    kind,
                    objectKey.ToString("D").ToLowerInvariant(),
                    actual.Fields
                        ?? throw new InvalidOperationException("The fake native API object projection is incomplete.")));
            }
        }

        private sealed class FakeTransaction : INativeWfpPolicyTransaction
        {
            private readonly FakeNativeWfpPolicyApi owner;
            private WfpProviderIdentity? provider;
            private WfpSublayerIdentity? sublayer;
            private readonly Dictionary<Guid, WfpFilterIdentity> filters;
            private readonly Dictionary<WfpPolicyObjectKey, SecurityDescriptorSnapshot> securityDescriptors;
            private bool complete;
            private bool mutated;

            internal FakeTransaction(FakeNativeWfpPolicyApi owner)
            {
                this.owner = owner;
                this.provider = owner.provider;
                this.sublayer = owner.sublayer;
                this.filters = new Dictionary<Guid, WfpFilterIdentity>(owner.filters);
                this.securityDescriptors = new Dictionary<WfpPolicyObjectKey, SecurityDescriptorSnapshot>(owner.securityDescriptors);
            }

            public NativeWfpPolicyReadback ReadSnapshot(Guid providerKey, Guid sublayerKey) =>
                this.owner.CreateReadback(
                    this.provider,
                    this.sublayer,
                    this.filters.Values,
                    this.securityDescriptors,
                    this.owner.CorruptTransactionReadbackAfterMutation && this.mutated);

            public void AddProvider(WfpProviderIdentity value, string securityDescriptorSddl)
            {
                this.EnsureOpen();
                if (this.provider is not null || value != WfpServicePolicyIdentity.Provider)
                {
                    throw new InvalidOperationException("invalid provider add");
                }
                this.provider = value with { NativeProjection = WfpNativeObjectProjection.ForProvider(value) };
                this.AddSecurity(WfpPolicyObjectKind.Provider, value.Key, securityDescriptorSddl);
                this.MarkMutation();
            }

            public void DeleteProvider(Guid key)
            {
                this.EnsureOpen();
                if (this.provider?.Key != key || this.sublayer is not null || this.filters.Count != 0)
                {
                    throw new InvalidOperationException("invalid provider delete");
                }
                this.provider = null;
                this.securityDescriptors.Remove(new WfpPolicyObjectKey(WfpPolicyObjectKind.Provider, key));
                this.MarkMutation();
            }

            public void AddSublayer(WfpSublayerIdentity value, string securityDescriptorSddl)
            {
                this.EnsureOpen();
                if (this.provider != WfpServicePolicyIdentity.Provider
                    || this.sublayer is not null
                    || value != WfpServicePolicyIdentity.Sublayer)
                {
                    throw new InvalidOperationException("invalid sublayer add");
                }
                this.sublayer = value with { NativeProjection = WfpNativeObjectProjection.ForSublayer(value) };
                this.AddSecurity(WfpPolicyObjectKind.Sublayer, value.Key, securityDescriptorSddl);
                this.MarkMutation();
            }

            public void DeleteSublayer(Guid key)
            {
                this.EnsureOpen();
                if (this.sublayer?.Key != key || this.filters.Values.Any(filter => filter.SublayerKey == key))
                {
                    throw new InvalidOperationException("invalid sublayer delete");
                }
                this.sublayer = null;
                this.securityDescriptors.Remove(new WfpPolicyObjectKey(WfpPolicyObjectKind.Sublayer, key));
                this.MarkMutation();
            }

            public void AddFilter(WfpFilterIdentity filter, string securityDescriptorSddl)
            {
                this.EnsureOpen();
                if (this.provider != WfpServicePolicyIdentity.Provider
                    || this.sublayer != WfpServicePolicyIdentity.Sublayer
                    || this.filters.ContainsKey(filter.Key))
                {
                    throw new InvalidOperationException("invalid filter add");
                }
                WfpFilterIdentity projected = filter with { NativeProjection = WfpNativeObjectProjection.ForFilter(filter) };
                this.filters.Add(projected.Key, projected);
                this.AddSecurity(WfpPolicyObjectKind.Filter, projected.Key, securityDescriptorSddl);
                this.MarkMutation();
            }

            public void DeleteFilter(Guid key)
            {
                this.EnsureOpen();
                if (!this.filters.Remove(key))
                {
                    throw new InvalidOperationException("invalid filter delete");
                }
                this.securityDescriptors.Remove(new WfpPolicyObjectKey(WfpPolicyObjectKind.Filter, key));
                this.MarkMutation();
            }

            public void Commit()
            {
                this.EnsureOpen();
                this.owner.provider = this.provider;
                this.owner.sublayer = this.sublayer;
                this.owner.filters.Clear();
                foreach ((Guid key, WfpFilterIdentity filter) in this.filters)
                {
                    this.owner.filters.Add(key, filter);
                }
                this.owner.securityDescriptors.Clear();
                foreach ((WfpPolicyObjectKey key, SecurityDescriptorSnapshot descriptor) in this.securityDescriptors)
                {
                    this.owner.securityDescriptors.Add(key, descriptor);
                }
                this.owner.CommitCount++;
                this.complete = true;
            }

            public void Abort()
            {
                this.EnsureOpen();
                this.owner.AbortCount++;
                this.complete = true;
            }

            public void Dispose()
            {
                if (!this.complete)
                {
                    this.Abort();
                }
            }

            private void AddSecurity(WfpPolicyObjectKind kind, Guid key, string sddl)
            {
                this.owner.AppliedSecurityDescriptors.Add(sddl);
                this.securityDescriptors.Add(new WfpPolicyObjectKey(kind, key), Descriptor(sddl));
            }

            private void MarkMutation()
            {
                this.owner.MutationCount++;
                this.mutated = true;
            }

            private void EnsureOpen() => ObjectDisposedException.ThrowIf(this.complete, this);
        }
    }
}
