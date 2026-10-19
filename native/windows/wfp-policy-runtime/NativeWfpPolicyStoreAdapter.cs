using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using WfpPolicy.NativeReadback;
using WfpPolicyPlan;

namespace WfpPolicy.Runtime;

internal enum WfpPolicyObjectKind
{
    Provider,
    Sublayer,
    Filter,
}

internal readonly record struct WfpPolicyObjectKey(WfpPolicyObjectKind Kind, Guid Key);

/// <summary>
/// The exact normalized owner/group/DACL value approved for service-owned WFP
/// objects. This prototype policy is deliberately supplied at construction;
/// it is not loaded from caller-controlled configuration.
/// </summary>
internal sealed record WfpObjectSecurityPolicy(
    string ServiceSid,
    string ProviderSddl,
    string SublayerSddl,
    string FilterSddl)
{
    internal static WfpObjectSecurityPolicy CreateProtectedServicePolicy(string serviceSid)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(serviceSid);
        var sid = new System.Security.Principal.SecurityIdentifier(serviceSid);
        if (!string.Equals(sid.Value, serviceSid, StringComparison.Ordinal))
        {
            throw new ArgumentException("The service SID must use canonical string form.", nameof(serviceSid));
        }

        // Use WFP's documented generic read/write/execute rights for the
        // prototype's object-management operations. LocalSystem owns the
        // objects so the service SID does not gain implicit WRITE_DAC through
        // ownership; neither ACE grants GENERIC_ALL / WRITE_OWNER.
        string sddl = ExpectedSecurityDescriptorSddl(serviceSid);
        return new WfpObjectSecurityPolicy(serviceSid, sddl, sddl, sddl);
    }

    internal string For(WfpPolicyObjectKind kind) => kind switch
    {
        WfpPolicyObjectKind.Provider => this.ProviderSddl,
        WfpPolicyObjectKind.Sublayer => this.SublayerSddl,
        WfpPolicyObjectKind.Filter => this.FilterSddl,
        _ => throw new ArgumentOutOfRangeException(nameof(kind)),
    };

    internal void Validate()
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(this.ServiceSid);
        var sid = new System.Security.Principal.SecurityIdentifier(this.ServiceSid);
        if (!string.Equals(sid.Value, this.ServiceSid, StringComparison.Ordinal))
        {
            throw new WfpBaselineOwnershipException("The WFP service SID is not canonical.");
        }

        string expectedSddl = ExpectedSecurityDescriptorSddl(this.ServiceSid);
        foreach (WfpPolicyObjectKind kind in Enum.GetValues<WfpPolicyObjectKind>())
        {
            string sddl = this.For(kind);
            if (sddl.Length is < 16 or > 4096
                || !string.Equals(sddl, expectedSddl, StringComparison.Ordinal))
            {
                throw new WfpBaselineOwnershipException($"The {kind} security descriptor does not match the protected WFP object-access policy.");
            }
        }
    }

    private static string ExpectedSecurityDescriptorSddl(string serviceSid) =>
        $"O:SYG:SYD:P(A;;GRGWGX;;;SY)(A;;GRGWGX;;;{serviceSid})";
}

/// <summary>
/// A bounded value read from one explicit BFE transaction. A production native
/// API implementation must set ScopeComplete only after it has proved read
/// coverage for the service-owned provider and sublayer under their verified
/// ACLs. The ordinary global reader does not provide that proof today.
/// </summary>
internal sealed record NativeWfpPolicyReadback(
    WfpPolicySnapshot Snapshot,
    IReadOnlyDictionary<WfpPolicyObjectKey, SecurityDescriptorSnapshot> SecurityDescriptors,
    bool ScopeComplete,
    string? IncompleteReason = null);

/// <summary>
/// Narrow seam for a native WFP implementation. All returned values must be
/// copied/normalized before native allocations are freed. BeginTransaction
/// must use one explicit write transaction, and its ReadSnapshot must read that
/// same transaction view. This interface intentionally has no live production
/// implementation in this source slice; the harness supplies a fake. The
/// adapter uses cooperative deadline checks around synchronous calls and cannot
/// preempt a blocked native call. A live implementation must bound its own
/// calls, make failed commits unambiguous, and keep Abort/Dispose bounded.
/// </summary>
internal interface INativeWfpPolicyApi
{
    NativeWfpPolicyReadback ReadSnapshot(Guid providerKey, Guid sublayerKey);
    INativeWfpPolicyTransaction BeginTransaction();
}

internal interface INativeWfpPolicyTransaction : IDisposable
{
    NativeWfpPolicyReadback ReadSnapshot(Guid providerKey, Guid sublayerKey);
    void AddProvider(WfpProviderIdentity provider, string securityDescriptorSddl);
    void DeleteProvider(Guid key);
    void AddSublayer(WfpSublayerIdentity sublayer, string securityDescriptorSddl);
    void DeleteSublayer(Guid key);
    void AddFilter(WfpFilterIdentity filter, string securityDescriptorSddl);
    void DeleteFilter(Guid key);
    void Commit();
    void Abort();
}

/// <summary>
/// Adapts a transaction-scoped native WFP API to the baseline coordinator's
/// store contract. It validates exact service keys, normalized security
/// descriptors, complete scoped readback, operation bounds, and the native
/// transaction's installed values before allowing Commit to return.
/// </summary>
internal sealed class NativeWfpPolicyStoreAdapter : IWfpPolicyStore
{
    internal const int MaxScopedFilters = 4096;
    internal const int MaxTransactionMutations = 1024;
    private const int MaxAppIdBytes = 1024 * 1024;
    private const int MaxSecurityDescriptorSddlCharacters = 4096;
    private static readonly TimeSpan MaxTransactionDuration = TimeSpan.FromSeconds(30);
    private readonly INativeWfpPolicyApi api;
    private readonly WfpObjectSecurityPolicy securityPolicy;

    internal NativeWfpPolicyStoreAdapter(INativeWfpPolicyApi api, WfpObjectSecurityPolicy securityPolicy)
    {
        this.api = api ?? throw new ArgumentNullException(nameof(api));
        this.securityPolicy = securityPolicy ?? throw new ArgumentNullException(nameof(securityPolicy));
        this.securityPolicy.Validate();
    }

    public WfpPolicySnapshot ReadSnapshot(Guid providerKey, Guid sublayerKey)
    {
        RequireServiceKeys(providerKey, sublayerKey);
        var elapsed = Stopwatch.StartNew();
        NativeWfpPolicyReadback readback = this.api.ReadSnapshot(providerKey, sublayerKey);
        if (elapsed.Elapsed >= MaxTransactionDuration)
        {
            throw new TimeoutException("The native WFP snapshot read exceeded its bounded duration.");
        }
        return this.ValidateReadback(readback);
    }

    public IWfpPolicyTransaction BeginTransaction()
    {
        var elapsed = Stopwatch.StartNew();
        INativeWfpPolicyTransaction transaction = this.api.BeginTransaction()
            ?? throw new WfpBaselineOwnershipException("The native WFP API returned no transaction.");
        if (elapsed.Elapsed >= MaxTransactionDuration)
        {
            var timeout = new TimeoutException("The native WFP transaction could not be opened within its bounded duration.");
            Exception? cleanupFailure = null;
            try
            {
                transaction.Abort();
            }
            catch (Exception exception)
            {
                cleanupFailure = exception;
            }
            try
            {
                transaction.Dispose();
            }
            catch (Exception exception)
            {
                cleanupFailure ??= exception;
            }
            if (cleanupFailure is not null)
            {
                throw new WfpBaselineRollbackException(timeout, cleanupFailure);
            }
            throw timeout;
        }
        return new Transaction(this, transaction, elapsed);
    }

    private WfpPolicySnapshot ValidateReadback(NativeWfpPolicyReadback readback)
    {
        ArgumentNullException.ThrowIfNull(readback);
        if (!readback.ScopeComplete)
        {
            throw new WfpBaselineOwnershipException("The native WFP store cannot prove complete service-scope readback.");
        }

        WfpPolicySnapshot snapshot = readback.Snapshot
            ?? throw new WfpBaselineOwnershipException("The native WFP store returned no policy snapshot.");
        if (snapshot.Filters is null
            || readback.SecurityDescriptors is null)
        {
            throw new WfpBaselineOwnershipException("The native WFP store exceeded the service-scope filter bound.");
        }
        WfpFilterIdentity[] filters = snapshot.Filters.ToArray();
        if (filters.Length > MaxScopedFilters || filters.Any(filter => filter is null))
        {
            throw new WfpBaselineOwnershipException("The native WFP store returned a null filter row or exceeded the service-scope filter bound.");
        }

        if (snapshot.Provider is { } provider && provider.Key != WfpServicePolicyIdentity.ProviderKey)
        {
            throw new WfpBaselineOwnershipException("The native WFP store returned a provider outside the requested service identity.");
        }
        if (snapshot.Sublayer is { } sublayer && sublayer.Key != WfpServicePolicyIdentity.SublayerKey)
        {
            throw new WfpBaselineOwnershipException("The native WFP store returned a sublayer outside the requested service identity.");
        }

        if ((snapshot.Sublayer is not null && snapshot.Provider is null)
            || (filters.Any(filter => filter.ProviderKey == WfpServicePolicyIdentity.ProviderKey)
                && snapshot.Provider is null)
            || (filters.Any(filter => filter.SublayerKey == WfpServicePolicyIdentity.SublayerKey)
                && snapshot.Sublayer is null))
        {
            throw new WfpBaselineOwnershipException("The service-owned WFP provider, sublayer, and filters have inconsistent parent state.");
        }

        var expectedSecurity = new HashSet<WfpPolicyObjectKey>();
        if (snapshot.Provider is { } actualProvider)
        {
            ValidateProvider(actualProvider);
            ValidateSecurity(readback, new WfpPolicyObjectKey(WfpPolicyObjectKind.Provider, actualProvider.Key));
            expectedSecurity.Add(new WfpPolicyObjectKey(WfpPolicyObjectKind.Provider, actualProvider.Key));
        }
        if (snapshot.Sublayer is { } actualSublayer)
        {
            ValidateSublayer(actualSublayer);
            ValidateSecurity(readback, new WfpPolicyObjectKey(WfpPolicyObjectKind.Sublayer, actualSublayer.Key));
            expectedSecurity.Add(new WfpPolicyObjectKey(WfpPolicyObjectKind.Sublayer, actualSublayer.Key));
        }

        var filterKeys = new HashSet<Guid>();
        foreach (WfpFilterIdentity filter in filters)
        {
            if (!filterKeys.Add(filter.Key))
            {
                throw new WfpBaselineOwnershipException("The native WFP store returned a null or duplicate filter row.");
            }
            if (filter.ProviderKey != WfpServicePolicyIdentity.ProviderKey
                && filter.SublayerKey != WfpServicePolicyIdentity.SublayerKey)
            {
                throw new WfpBaselineOwnershipException("The native WFP store returned a filter outside both service-owned scopes.");
            }
            if (filter.ProviderKey == WfpServicePolicyIdentity.ProviderKey
                && filter.SublayerKey != WfpServicePolicyIdentity.SublayerKey)
            {
                throw new WfpBaselineOwnershipException("A service-provider filter is attached to an unexpected sublayer.");
            }
            if (filter.SublayerKey == WfpServicePolicyIdentity.SublayerKey
                && filter.ProviderKey != WfpServicePolicyIdentity.ProviderKey)
            {
                throw new WfpBaselineOwnershipException("A foreign-provider filter occupies the service-owned sublayer.");
            }
            ValidateFilter(filter);
            WfpPolicyObjectKey objectKey = new(WfpPolicyObjectKind.Filter, filter.Key);
            ValidateSecurity(readback, objectKey);
            expectedSecurity.Add(objectKey);
        }

        if (readback.SecurityDescriptors.Count != expectedSecurity.Count
            || !readback.SecurityDescriptors.Keys.ToHashSet().SetEquals(expectedSecurity))
        {
            throw new WfpBaselineOwnershipException("The native WFP store returned missing or unexpected object ACL evidence.");
        }

        WfpNativeReadbackProjection readbackProjection = snapshot.NativeReadbackProjection
            ?? throw new WfpBaselineOwnershipException("The native WFP store returned no canonical readback projection.");
        readbackProjection.RequireCanonical();
        return snapshot with
        {
            Filters = Array.AsReadOnly(filters.OrderBy(filter => filter.Key).ToArray()),
        };
    }

    private void ValidateProvider(WfpProviderIdentity provider)
    {
        if (provider != WfpServicePolicyIdentity.Provider)
        {
            throw new WfpBaselineOwnershipException("The provider key is occupied by an object with unexpected service identity values.");
        }
        WfpNativeObjectProjection.RequireExact(
            provider.NativeProjection,
            WfpNativeObjectProjection.ForProvider(WfpServicePolicyIdentity.Provider),
            "provider");
    }

    private void ValidateSublayer(WfpSublayerIdentity sublayer)
    {
        if (sublayer != WfpServicePolicyIdentity.Sublayer)
        {
            throw new WfpBaselineOwnershipException("The sublayer key is occupied by an object with unexpected service identity values.");
        }
        WfpNativeObjectProjection.RequireExact(
            sublayer.NativeProjection,
            WfpNativeObjectProjection.ForSublayer(WfpServicePolicyIdentity.Sublayer),
            "sublayer");
    }

    private static void ValidateFilter(WfpFilterIdentity filter)
    {
        LeasePolicyRule rule = filter.Rule
            ?? throw new WfpBaselineOwnershipException("The native WFP filter has no semantic rule projection.");
        WfpNativeObjectProjection.RequireExact(
            filter.NativeProjection,
            WfpNativeObjectProjection.ForFilter(filter),
            "filter");

        if (rule.AppIdHex is null
            || rule.AppIdHex.Length is < 2 or > MaxAppIdBytes * 2
            || rule.AppIdHex.Length % 2 != 0)
        {
            throw new WfpBaselineOwnershipException("A persistent AppID baseline filter has an invalid or oversized AppID blob.");
        }

        byte[] appIdBytes;
        try
        {
            appIdBytes = Convert.FromHexString(rule.AppIdHex);
        }
        catch (FormatException)
        {
            throw new WfpBaselineOwnershipException("A persistent AppID baseline filter has a malformed AppID blob.");
        }
        if (!string.Equals(Convert.ToHexString(appIdBytes).ToLowerInvariant(), rule.AppIdHex, StringComparison.Ordinal))
        {
            throw new WfpBaselineOwnershipException("A persistent AppID baseline filter has noncanonical AppID hexadecimal.");
        }

        bool browser = rule.RuleId.StartsWith("default-deny-browser-", StringComparison.Ordinal);
        bool worker = rule.RuleId.StartsWith("default-deny-worker-", StringComparison.Ordinal);
        if (browser == worker)
        {
            throw new WfpBaselineOwnershipException("A persistent AppID baseline filter has an unsupported application role.");
        }
        string role = browser ? "browser" : "worker";
        string identityHash = Convert.ToHexString(SHA256.HashData(appIdBytes))[..16];
        string family = rule.AddressFamily switch
        {
            LeasePolicyAddressFamily.IPv4 => "v4",
            LeasePolicyAddressFamily.IPv6 => "v6",
            _ => throw new WfpBaselineOwnershipException("A persistent AppID baseline filter has an unsupported address family."),
        };
        string expectedRuleId = $"default-deny-{role}-{identityHash}-{family}";
        string expectedPurpose = $"Persistent catch-all block for every {role} process from this protected AppID; higher-weight exact lease permits are the only intended exceptions.";

        if (filter.Key != WfpServicePolicyIdentity.FilterKey(filter.Rule.RuleId)
            || filter.ProviderKey != WfpServicePolicyIdentity.ProviderKey
            || filter.SublayerKey != WfpServicePolicyIdentity.SublayerKey
            || !filter.Persistent
            || filter.Name != WfpServicePolicyIdentity.FilterNamePrefix + rule.RuleId
            || filter.Description != rule.Purpose
            || rule.RuleId != expectedRuleId
            || rule.Purpose != expectedPurpose
            || rule.Lifetime != LeasePolicyLifetime.PersistentDefaultDeny
            || rule.Action != LeasePolicyAction.Block
            || rule.LeaseId is not null
            || rule.LeaseSid is not null
            || rule.IdentityCondition != "ALE_APP_ID"
            || rule.RemoteAddress is not null
            || rule.Protocol is not null
            || rule.RemotePort is not null
            || rule.WeightRangeIndex != LeasePolicyCompiler.DefaultDenyWeightRangeIndex
            || rule.ClearActionRight)
        {
            throw new WfpBaselineOwnershipException("A filter does not match the service-owned persistent AppID baseline shape.");
        }
    }

    private void ValidateSecurity(NativeWfpPolicyReadback readback, WfpPolicyObjectKey key)
    {
        if (!readback.SecurityDescriptors.TryGetValue(key, out SecurityDescriptorSnapshot? descriptor)
            || descriptor is null
            || string.IsNullOrEmpty(descriptor.Sddl)
            || descriptor.Sddl.Length > MaxSecurityDescriptorSddlCharacters
            || string.IsNullOrEmpty(descriptor.Sha256)
            || descriptor.Sha256.Length != 64
            || !descriptor.DaclPresent
            || descriptor.HasNullDacl
            || descriptor.BinaryLength is < 20 or > 1_048_576
            || !descriptor.Sddl.StartsWith("O:SYG:SYD:P", StringComparison.Ordinal)
            || !string.Equals(descriptor.Sddl, this.securityPolicy.For(key.Kind), StringComparison.Ordinal))
        {
            throw new WfpBaselineOwnershipException($"The service-owned WFP {key.Kind} has a missing or unexpected owner/DACL.");
        }

        byte[] expectedHash = SHA256.HashData(Encoding.UTF8.GetBytes(descriptor.Sddl));
        byte[] reportedHash;
        try
        {
            reportedHash = Convert.FromHexString(descriptor.Sha256);
        }
        catch (FormatException)
        {
            throw new WfpBaselineOwnershipException($"The WFP {key.Kind} ACL digest is malformed.");
        }
        if (!CryptographicOperations.FixedTimeEquals(expectedHash, reportedHash))
        {
            throw new WfpBaselineOwnershipException($"The WFP {key.Kind} ACL digest does not match its normalized SDDL.");
        }
    }

    private static void RequireServiceKeys(Guid providerKey, Guid sublayerKey)
    {
        if (providerKey != WfpServicePolicyIdentity.ProviderKey
            || sublayerKey != WfpServicePolicyIdentity.SublayerKey)
        {
            throw new WfpBaselineOwnershipException("The native WFP store only accepts fixed service-owned provider and sublayer keys.");
        }
    }

    private sealed class Transaction : IWfpPolicyTransaction, IWfpPolicySnapshotTransaction
    {
        private readonly NativeWfpPolicyStoreAdapter owner;
        private readonly INativeWfpPolicyTransaction native;
        private readonly Stopwatch elapsed;
        private WfpPolicySnapshot? working;
        private int mutationCount;
        private bool completed;

        internal Transaction(NativeWfpPolicyStoreAdapter owner, INativeWfpPolicyTransaction native, Stopwatch elapsed)
        {
            this.owner = owner;
            this.native = native;
            this.elapsed = elapsed;
        }

        public WfpPolicySnapshot ReadSnapshot() => this.ReadWorking();

        public WfpProviderIdentity? GetProvider(Guid key)
        {
            this.RequireServiceProviderKey(key);
            return this.ReadWorking().Provider;
        }

        public WfpSublayerIdentity? GetSublayer(Guid key)
        {
            this.RequireServiceSublayerKey(key);
            return this.ReadWorking().Sublayer;
        }

        public IReadOnlyList<WfpFilterIdentity> EnumerateProviderFilters(Guid providerKey)
        {
            this.RequireServiceProviderKey(providerKey);
            return Array.AsReadOnly(this.ReadWorking().Filters
                .Where(filter => filter.ProviderKey == providerKey)
                .OrderBy(filter => filter.Key)
                .ToArray());
        }

        public IReadOnlyList<WfpFilterIdentity> EnumerateSublayerFilters(Guid sublayerKey)
        {
            this.RequireServiceSublayerKey(sublayerKey);
            return Array.AsReadOnly(this.ReadWorking().Filters
                .Where(filter => filter.SublayerKey == sublayerKey)
                .OrderBy(filter => filter.Key)
                .ToArray());
        }

        public void AddProvider(WfpProviderIdentity provider)
        {
            this.RequireMutation();
            if (provider != WfpServicePolicyIdentity.Provider || this.ReadWorking().Provider is not null)
            {
                throw new WfpBaselineOwnershipException("Only the absent fixed service-owned provider may be added.");
            }
            WfpProviderIdentity projected = provider with
            {
                NativeProjection = WfpNativeObjectProjection.ForProvider(provider),
            };
            this.native.AddProvider(projected, this.owner.securityPolicy.For(WfpPolicyObjectKind.Provider));
            this.working = this.ReadWorking() with { Provider = projected };
            this.RecordMutation();
        }

        public void DeleteProvider(Guid key)
        {
            this.RequireMutation();
            if (key != WfpServicePolicyIdentity.ProviderKey
                || this.ReadWorking().Provider is null
                || this.ReadWorking().Sublayer is not null
                || this.ReadWorking().Filters.Count != 0)
            {
                throw new WfpBaselineOwnershipException("The service provider cannot be deleted while dependent objects remain.");
            }
            this.native.DeleteProvider(key);
            this.working = this.ReadWorking() with { Provider = null };
            this.RecordMutation();
        }

        public void AddSublayer(WfpSublayerIdentity sublayer)
        {
            this.RequireMutation();
            WfpPolicySnapshot current = this.ReadWorking();
            if (sublayer != WfpServicePolicyIdentity.Sublayer
                || current.Provider != WfpServicePolicyIdentity.Provider
                || current.Sublayer is not null)
            {
                throw new WfpBaselineOwnershipException("Only the absent fixed service-owned sublayer may be added beneath its provider.");
            }
            WfpSublayerIdentity projected = sublayer with
            {
                NativeProjection = WfpNativeObjectProjection.ForSublayer(sublayer),
            };
            this.native.AddSublayer(projected, this.owner.securityPolicy.For(WfpPolicyObjectKind.Sublayer));
            this.working = this.ReadWorking() with { Sublayer = projected };
            this.RecordMutation();
        }

        public void DeleteSublayer(Guid key)
        {
            this.RequireMutation();
            WfpPolicySnapshot current = this.ReadWorking();
            if (key != WfpServicePolicyIdentity.SublayerKey
                || current.Sublayer is null
                || current.Filters.Any(filter => filter.SublayerKey == key))
            {
                throw new WfpBaselineOwnershipException("The service sublayer cannot be deleted while dependent filters remain.");
            }
            this.native.DeleteSublayer(key);
            this.working = this.ReadWorking() with { Sublayer = null };
            this.RecordMutation();
        }

        public void AddFilter(WfpFilterIdentity filter)
        {
            this.RequireMutation();
            ArgumentNullException.ThrowIfNull(filter);
            ValidateFilter(filter);
            WfpPolicySnapshot current = this.ReadWorking();
            if (current.Provider != WfpServicePolicyIdentity.Provider
                || current.Sublayer != WfpServicePolicyIdentity.Sublayer
                || current.Filters.Count >= MaxScopedFilters
                || current.Filters.Any(existing => existing.Key == filter.Key))
            {
                throw new WfpBaselineOwnershipException("A service baseline filter requires the verified provider/sublayer and an unused stable key.");
            }
            WfpFilterIdentity projected = filter with
            {
                NativeProjection = WfpNativeObjectProjection.ForFilter(filter),
            };
            this.native.AddFilter(projected, this.owner.securityPolicy.For(WfpPolicyObjectKind.Filter));
            this.working = this.ReadWorking() with
            {
                Filters = Array.AsReadOnly(current.Filters.Append(projected).OrderBy(item => item.Key).ToArray()),
            };
            this.RecordMutation();
        }

        public void DeleteFilter(Guid key)
        {
            this.RequireMutation();
            WfpPolicySnapshot current = this.ReadWorking();
            WfpFilterIdentity? filter = current.Filters.SingleOrDefault(item => item.Key == key);
            if (filter is null)
            {
                throw new WfpBaselineOwnershipException("The native WFP store cannot delete an unread or unknown filter.");
            }
            ValidateFilter(filter);
            this.native.DeleteFilter(key);
            this.working = this.ReadWorking() with
            {
                Filters = Array.AsReadOnly(current.Filters.Where(item => item.Key != key).ToArray()),
            };
            this.RecordMutation();
        }

        public void Commit()
        {
            this.RequireOpen();
            this.CheckDeadline();
            WfpPolicySnapshot expected = this.ReadWorking();
            WfpPolicySnapshot observed = this.owner.ValidateReadback(this.native.ReadSnapshot(
                WfpServicePolicyIdentity.ProviderKey,
                WfpServicePolicyIdentity.SublayerKey));
            if (!Equivalent(expected, observed))
            {
                throw new WfpBaselineVerificationException(
                    new InvalidOperationException("The transaction-scoped native readback did not match the staged service-owned values."));
            }

            this.CheckDeadline();
            this.native.Commit();
            this.completed = true;
        }

        public void Abort()
        {
            if (this.completed)
            {
                return;
            }
            try
            {
                this.native.Abort();
            }
            finally
            {
                this.completed = true;
            }
        }

        public void Dispose()
        {
            if (this.completed)
            {
                this.native.Dispose();
                return;
            }
            try
            {
                this.native.Abort();
            }
            finally
            {
                this.completed = true;
                this.native.Dispose();
            }
        }

        private WfpPolicySnapshot ReadWorking()
        {
            this.RequireOpen();
            if (this.working is null)
            {
                this.working = this.owner.ValidateReadback(this.native.ReadSnapshot(
                    WfpServicePolicyIdentity.ProviderKey,
                    WfpServicePolicyIdentity.SublayerKey));
            }
            this.CheckDeadline();
            return this.working;
        }

        private void RequireMutation()
        {
            this.RequireOpen();
            this.CheckDeadline();
            if (this.mutationCount >= MaxTransactionMutations)
            {
                throw new WfpBaselineOwnershipException("The native WFP transaction mutation bound was exceeded.");
            }
        }

        private void RecordMutation()
        {
            this.mutationCount++;
            this.CheckDeadline();
        }

        private void RequireServiceProviderKey(Guid key)
        {
            this.RequireOpen();
            if (key != WfpServicePolicyIdentity.ProviderKey)
            {
                throw new WfpBaselineOwnershipException("The native WFP transaction may only inspect the fixed service provider.");
            }
        }

        private void RequireServiceSublayerKey(Guid key)
        {
            this.RequireOpen();
            if (key != WfpServicePolicyIdentity.SublayerKey)
            {
                throw new WfpBaselineOwnershipException("The native WFP transaction may only inspect the fixed service sublayer.");
            }
        }

        private void RequireOpen()
        {
            if (this.completed)
            {
                throw new InvalidOperationException("The native WFP transaction is already complete.");
            }
            this.CheckDeadline();
        }

        private void CheckDeadline()
        {
            if (this.elapsed.Elapsed >= MaxTransactionDuration)
            {
                throw new TimeoutException("The native WFP transaction exceeded its bounded lifetime.");
            }
        }

        private static bool Equivalent(WfpPolicySnapshot left, WfpPolicySnapshot right) =>
            left.Provider == right.Provider
            && left.Sublayer == right.Sublayer
            && left.Filters.OrderBy(filter => filter.Key).SequenceEqual(right.Filters.OrderBy(filter => filter.Key));
    }
}
