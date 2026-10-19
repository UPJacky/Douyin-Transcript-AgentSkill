using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using WfpPolicy.NativeReadback;
using WfpPolicyPlan;

namespace WfpPolicy.Runtime;

/// <summary>
/// One copied, complete readback from a single lease-scoped session. A native
/// implementation must enumerate the dynamic provider and filters created on
/// this handle, include their normalized ACL evidence, and must not synthesize
/// projections from requested objects.
/// </summary>
internal sealed record DynamicLeaseSessionReadback(
    Guid LeaseId,
    Guid SessionId,
    bool IsComplete,
    DynamicLeaseProviderIdentity? Provider,
    IReadOnlyDictionary<WfpPolicyObjectKey, SecurityDescriptorSnapshot>? SecurityDescriptors,
    IReadOnlyList<WfpFilterIdentity>? Filters);

/// <summary>
/// Lease-specific non-persistent provider. Dynamic filters keep using the
/// persistent baseline sublayer so the policy's arbitration scope is stable.
/// </summary>
internal sealed record DynamicLeaseProviderIdentity(
    Guid LeaseId,
    Guid Key,
    string Name,
    string Description,
    WfpNativeObjectProjection? NativeProjection = null);

/// <summary>
/// Immutable coordinator-owned expectation for one currently registered
/// dynamic lease. Session IDs are deliberately absent: FWPM_FILTER0 does not
/// expose a session identity, so shared-sublayer readback can bind objects to
/// a lease provider and its exact filters, but cannot attest native session
/// ownership from a filter row.
/// </summary>
internal sealed record ActiveDynamicLeaseExpectation(
    Guid LeaseId,
    DynamicLeaseProviderIdentity Provider,
    IReadOnlyList<WfpFilterIdentity> Filters);

/// <summary>
/// Contract for one independent dynamic WFP session. Open must return a unique
/// session handle; AddProvider must create a non-persistent provider in that
/// session; AddFilter must use that provider and the fixed baseline sublayer;
/// and Readback must return complete values and ACL evidence for every object
/// in this session. Readback must not echo requested objects. Close must close
/// that session and remove its dynamic objects. No production WFP implementation
/// is provided by this source slice.
/// </summary>
internal interface IDynamicLeasePolicySession
{
    Guid LeaseId { get; }
    Guid SessionId { get; }
    void AddProvider(DynamicLeaseProviderIdentity provider);
    void AddFilter(WfpFilterIdentity filter);
    DynamicLeaseSessionReadback Readback();
    void Close();
}

/// <summary>
/// Opens a distinct dynamic session for each lease. If opening fails, the
/// factory must clean any native handle it created before throwing, because no
/// session handle would otherwise be available to the coordinator.
/// </summary>
internal interface IDynamicLeasePolicySessionFactory
{
    IDynamicLeasePolicySession Open(Guid leaseId);
}

/// <summary>
/// A worker-tree drain receipt. The coordinator accepts it only for its lease
/// and only when the job was terminated and its active process count is zero.
/// </summary>
internal sealed record LeaseJobTreeDrainReceipt(
    Guid LeaseId,
    bool JobTerminated,
    uint ActiveProcessCount);

/// <summary>
/// Offline lease lifecycle logic, not proof of native WFP isolation. Every
/// Open first reconciles and reads back the complete persistent AppID
/// baseline. Each lease now has its own dynamic provider, while all filters
/// retain the persistent baseline sublayer. A complete native enumeration of
/// that shared sublayer will therefore include dynamic filters, which the
/// current baseline adapter rejects as foreign-provider objects. Dynamic
/// session readback verifies each lease's provider, filter projections, and
/// ACL evidence, but it does not make the next baseline read safe. This
/// coordinator is not wired to a native adapter or product service factory.
/// </summary>
internal sealed class DynamicLeaseCoordinator
{
    internal const int MaxDynamicRulesPerLease =
        2 + 2 + 2 + LeasePolicyCompiler.MaxPinnedAddressesPerLease;
    internal const int MaxLeasesPerCoordinatorLifetime = 4096;

    private const string DynamicFilterNamePrefix = "DouyinTranscript:lease-dynamic:v1:";
    private const int MaxRuleIdCharacters = 256;
    private const int MaxPurposeCharacters = 1024;

    private readonly object sync = new();
    private readonly PersistentBaselineCoordinator baselineCoordinator;
    private readonly ProtectedApplicationInput[] baselineApplications;
    private readonly IDynamicLeasePolicySessionFactory sessionFactory;
    private readonly WfpObjectSecurityPolicy securityPolicy;
    private readonly Dictionary<Guid, DynamicLeaseScope> activeLeases = [];
    private readonly HashSet<Guid> seenLeaseIds = [];
    private readonly HashSet<Guid> seenSessionIds = [];
    private readonly HashSet<Guid> seenProviderKeys = [];
    private readonly List<IDynamicLeasePolicySession> retainedUnclosedSessions = [];
    private bool isolated;

    internal DynamicLeaseCoordinator(
        PersistentBaselineCoordinator baselineCoordinator,
        IEnumerable<ProtectedApplicationInput> baselineApplications,
        IDynamicLeasePolicySessionFactory sessionFactory,
        WfpObjectSecurityPolicy securityPolicy)
    {
        this.baselineCoordinator = baselineCoordinator ?? throw new ArgumentNullException(nameof(baselineCoordinator));
        ArgumentNullException.ThrowIfNull(baselineApplications);
        this.sessionFactory = sessionFactory ?? throw new ArgumentNullException(nameof(sessionFactory));
        this.securityPolicy = securityPolicy ?? throw new ArgumentNullException(nameof(securityPolicy));
        this.securityPolicy.Validate();

        this.baselineApplications = baselineApplications.Take(129).ToArray();
        if (this.baselineApplications.Length is 0 or > 128
            || this.baselineApplications.Any(application => application is null))
        {
            throw new ArgumentException("The persistent AppID baseline must contain between 1 and 128 non-null applications.", nameof(baselineApplications));
        }
    }

    internal bool IsIsolated
    {
        get
        {
            lock (this.sync)
            {
                return this.isolated;
            }
        }
    }

    /// <summary>
    /// Counts live lease handles and failed-open handles that remain retained
    /// after an unconfirmed close. It is diagnostic state, not readiness proof.
    /// </summary>
    internal int RetainedSessionHandleCount
    {
        get
        {
            lock (this.sync)
            {
                return this.activeLeases.Count + this.retainedUnclosedSessions.Count;
            }
        }
    }

    internal int OrphanedSessionHandleCount
    {
        get
        {
            lock (this.sync)
            {
                return this.retainedUnclosedSessions.Count;
            }
        }
    }

    /// <summary>
    /// Copies the coordinator's registered active lease identities for a
    /// shared-sublayer readback comparison. This is managed expected state,
    /// not native enumeration evidence.
    /// </summary>
    internal IReadOnlyList<ActiveDynamicLeaseExpectation> GetActiveReadbackExpectations()
    {
        lock (this.sync)
        {
            ActiveDynamicLeaseExpectation[] expectations = this.activeLeases.Values
                .OrderBy(lease => lease.LeaseId)
                .Select(lease => new ActiveDynamicLeaseExpectation(
                    lease.LeaseId,
                    lease.Provider,
                    Array.AsReadOnly(lease.Filters.ToArray())))
                .ToArray();
            return Array.AsReadOnly(expectations);
        }
    }

    internal DynamicLeaseScope Open(LeasePolicyInput lease, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(lease);
        ServiceWideLeasePolicyPlan combined = LeasePolicyCompiler.CompileServiceWidePlan(
            this.baselineApplications,
            [lease]);
        return this.OpenPlan(combined.DynamicLeases.Single(), cancellationToken);
    }

    private DynamicLeaseScope OpenPlan(DynamicLeasePlan plan, CancellationToken cancellationToken)
    {
        ValidatedPlan validated = ValidatePlan(plan);

        lock (this.sync)
        {
            if (this.isolated)
            {
                throw new WfpDynamicLeaseException("The dynamic lease coordinator is isolated after an unconfirmed session cleanup.");
            }
            if (this.seenLeaseIds.Contains(validated.LeaseId))
            {
                throw new WfpDynamicLeaseException("A lease ID cannot be reused by this coordinator.");
            }
            if (this.seenLeaseIds.Count >= MaxLeasesPerCoordinatorLifetime)
            {
                throw new WfpDynamicLeaseException("The coordinator lifetime lease bound was reached; readiness remains closed.");
            }
            if (this.activeLeases.Count >= LeasePolicyCompiler.MaxLeasesPerPlan)
            {
                throw new WfpDynamicLeaseException("The active dynamic lease bound was reached.");
            }

            // This call is intentionally repeated for every lease. The fake
            // store can model a baseline-only view, but a native enumeration
            // of the shared sublayer also sees filters from existing dynamic
            // providers. The baseline adapter currently rejects those rows;
            // see DYNAMIC_LEASE_SCOPE_LIMITATIONS.md before integration.
            this.baselineCoordinator.EnsureReady(this.baselineApplications, cancellationToken);
            cancellationToken.ThrowIfCancellationRequested();

            // Reserve the UUID before asking the session factory to allocate a
            // handle, so a partial apply cannot make the same lease identity
            // reusable.
            this.seenLeaseIds.Add(validated.LeaseId);
            IDynamicLeasePolicySession? session = null;
            try
            {
                cancellationToken.ThrowIfCancellationRequested();
                session = this.sessionFactory.Open(validated.LeaseId)
                    ?? throw new WfpDynamicLeaseException("The dynamic session factory returned no session handle.");

                Guid sessionGuid = session.SessionId;
                if (sessionGuid == Guid.Empty)
                {
                    throw new WfpDynamicLeaseException("The opened dynamic session has an empty session identity.");
                }
                if (this.seenSessionIds.Contains(sessionGuid)
                    || this.activeLeases.Values.Any(active => ReferenceEquals(active.Session, session)))
                {
                    // The handle may alias an already-live session. Do not
                    // close it, since that could remove another lease's rules.
                    this.isolated = true;
                    this.retainedUnclosedSessions.Add(session);
                    throw new WfpDynamicLeaseException("The session factory reused a live or previously used dynamic session identity.");
                }
                if (session.LeaseId != validated.LeaseId)
                {
                    throw new WfpDynamicLeaseException("The opened dynamic session is bound to a different lease identity.");
                }
                this.seenSessionIds.Add(sessionGuid);

                if (!this.seenProviderKeys.Add(validated.Provider.Key))
                {
                    throw new WfpDynamicLeaseException("A dynamic provider identity was already used by this coordinator.");
                }

                cancellationToken.ThrowIfCancellationRequested();
                session.AddProvider(validated.Provider);

                foreach (WfpFilterIdentity filter in validated.Filters)
                {
                    cancellationToken.ThrowIfCancellationRequested();
                    session.AddFilter(filter);
                }

                cancellationToken.ThrowIfCancellationRequested();
                VerifyReadback(session, validated);
                cancellationToken.ThrowIfCancellationRequested();

                var lease = new DynamicLeaseScope(this, session, validated.LeaseId, validated.Provider, validated.Filters);
                this.activeLeases.Add(validated.LeaseId, lease);
                return lease;
            }
            catch (Exception operationFailure)
            {
                if (session is null
                    || this.retainedUnclosedSessions.Any(retained => ReferenceEquals(retained, session)))
                {
                    throw;
                }

                try
                {
                    session.Close();
                }
                catch (Exception cleanupFailure)
                {
                    this.isolated = true;
                    this.retainedUnclosedSessions.Add(session);
                    throw new WfpDynamicLeaseCleanupException(operationFailure, cleanupFailure);
                }

                throw;
            }
        }
    }

    internal void MarkWorkerStarted(DynamicLeaseScope lease)
    {
        lock (this.sync)
        {
            this.RequireActiveLease(lease);
            lease.MarkWorkerStartedCore();
        }
    }

    internal void Close(
        DynamicLeaseScope lease,
        Func<CancellationToken, LeaseJobTreeDrainReceipt>? jobTreeDrain,
        CancellationToken cancellationToken)
    {
        bool workerStarted;
        lock (this.sync)
        {
            if (lease.IsClosedCore)
            {
                return;
            }
            this.RequireActiveLease(lease);
            if (lease.IsClosingCore)
            {
                throw new WfpDynamicLeaseException("A close operation is already in progress for this lease.");
            }
            workerStarted = lease.WorkerStartedCore;
            if (workerStarted && jobTreeDrain is null)
            {
                throw new WfpDynamicLeaseException("A started worker requires a successful job-tree drain before its dynamic session can close.");
            }
            lease.SetClosingCore(true);
        }

        try
        {
            if (workerStarted)
            {
                cancellationToken.ThrowIfCancellationRequested();
                LeaseJobTreeDrainReceipt receipt = jobTreeDrain!(cancellationToken)
                    ?? throw new WfpDynamicLeaseException("The job-tree drain callback returned no receipt.");
                cancellationToken.ThrowIfCancellationRequested();
                if (receipt.LeaseId != lease.LeaseId
                    || !receipt.JobTerminated
                    || receipt.ActiveProcessCount != 0)
                {
                    throw new WfpDynamicLeaseException("The lease job tree was not confirmed terminated and drained.");
                }
            }
        }
        catch
        {
            lock (this.sync)
            {
                lease.SetClosingCore(false);
            }
            throw;
        }

        // Once the job is drained, session close is cleanup and is not canceled.
        // A failure keeps the handle tracked and isolates future lease opens.
        try
        {
            lease.Session.Close();
        }
        catch (Exception exception)
        {
            lock (this.sync)
            {
                this.isolated = true;
                lease.SetClosingCore(false);
            }
            throw new WfpDynamicLeaseCleanupException(
                new InvalidOperationException("The lease job tree drained, but its dynamic session did not close.", exception),
                exception);
        }

        lock (this.sync)
        {
            this.activeLeases.Remove(lease.LeaseId);
            lease.MarkClosedCore();
        }
    }

    private void RequireActiveLease(DynamicLeaseScope lease)
    {
        if (!this.activeLeases.TryGetValue(lease.LeaseId, out DynamicLeaseScope? active)
            || !ReferenceEquals(active, lease))
        {
            throw new WfpDynamicLeaseException("The lease session is not owned by this coordinator.");
        }
    }

    private static ValidatedPlan ValidatePlan(DynamicLeasePlan plan)
    {
        ArgumentNullException.ThrowIfNull(plan);
        if (!string.Equals(plan.PlanKind, "dynamic-lease", StringComparison.Ordinal)
            || !string.Equals(plan.Deployability, "not-deployable", StringComparison.Ordinal))
        {
            throw new WfpDynamicLeaseException("Only the non-deployable dynamic-lease plan shape is accepted.");
        }

        if (!Guid.TryParseExact(plan.LeaseId, "N", out Guid leaseId)
            || leaseId == Guid.Empty
            || !string.Equals(plan.LeaseId, leaseId.ToString("N"), StringComparison.Ordinal))
        {
            throw new WfpDynamicLeaseException("The lease ID must be a canonical, non-empty UUID in N format.");
        }
        if (!Enum.IsDefined(plan.PrincipalKind))
        {
            throw new WfpDynamicLeaseException("The lease principal kind is unsupported.");
        }
        ValidateLeaseSid(plan.LeaseSid, plan.PrincipalKind);

        if (plan.Rules is null
            || plan.Rules.Count is 0 or > MaxDynamicRulesPerLease)
        {
            throw new WfpDynamicLeaseException("The dynamic lease rule set is empty or exceeds its fixed bound.");
        }

        string listenerPermitId = $"lease-{plan.LeaseId}-browser-allow-worker-listener";
        LeasePolicyRule[] listenerPermits = plan.Rules
            .Where(rule => rule is not null && string.Equals(rule.RuleId, listenerPermitId, StringComparison.Ordinal))
            .ToArray();
        if (listenerPermits.Length != 1
            || listenerPermits[0].LeaseId != plan.LeaseId
            || listenerPermits[0].LeaseSid != plan.LeaseSid
            || listenerPermits[0].Lifetime != LeasePolicyLifetime.LeaseDynamic
            || listenerPermits[0].Action != LeasePolicyAction.Permit
            || listenerPermits[0].AddressFamily != LeasePolicyAddressFamily.IPv4
            || listenerPermits[0].RemoteAddress != "127.0.0.1"
            || listenerPermits[0].Protocol != 6
            || listenerPermits[0].RemotePort is not (>= 1 and <= ushort.MaxValue))
        {
            throw new WfpDynamicLeaseException("The plan must contain one canonical lease-bound browser listener permit.");
        }
        int listenerPort = listenerPermits[0].RemotePort!.Value;

        DynamicLeaseProviderIdentity provider = CreateDynamicProvider(leaseId);
        var ruleIds = new HashSet<string>(StringComparer.Ordinal);
        var filterKeys = new HashSet<Guid>();
        var filters = new List<WfpFilterIdentity>(plan.Rules.Count);
        foreach (LeasePolicyRule? rule in plan.Rules)
        {
            if (rule is null
                || string.IsNullOrWhiteSpace(rule.RuleId)
                || rule.RuleId.Length > MaxRuleIdCharacters
                || string.IsNullOrWhiteSpace(rule.Purpose)
                || rule.Purpose.Length > MaxPurposeCharacters
                || !ruleIds.Add(rule.RuleId)
                || !Enum.IsDefined(rule.AddressFamily)
                || !Enum.IsDefined(rule.Action)
                || rule.WeightRangeIndex > 15
                || rule.Lifetime != LeasePolicyLifetime.LeaseDynamic
                || !string.Equals(rule.LeaseId, plan.LeaseId, StringComparison.Ordinal)
                || !RuleSidMatchesPlan(rule, plan, listenerPort))
            {
                throw new WfpDynamicLeaseException("Every dynamic rule must be bounded, unique, and match its lease ID and SID.");
            }

            Guid key = DynamicFilterKey(leaseId, provider.Key, rule.RuleId);
            if (!filterKeys.Add(key))
            {
                throw new WfpDynamicLeaseException("The dynamic lease rule set contains a duplicate filter key.");
            }

            var identity = new WfpFilterIdentity(
                key,
                provider.Key,
                WfpServicePolicyIdentity.SublayerKey,
                DynamicFilterName(leaseId, rule.RuleId),
                rule.Purpose,
                Persistent: false,
                Rule: rule);
            filters.Add(identity with { NativeProjection = WfpNativeObjectProjection.ForFilter(identity) });
        }

        return new ValidatedPlan(leaseId, plan.LeaseSid, provider, Array.AsReadOnly(filters.ToArray()));
    }

    private static void ValidateLeaseSid(string? leaseSid, LeasePrincipalKind principalKind)
    {
        if (string.IsNullOrWhiteSpace(leaseSid) || leaseSid.Length > 184 || leaseSid != leaseSid.Trim())
        {
            throw new WfpDynamicLeaseException("The lease SID must be non-empty, canonical, and bounded.");
        }

        SecurityIdentifier sid;
        try
        {
            sid = new SecurityIdentifier(leaseSid);
        }
        catch (ArgumentException exception)
        {
            throw new WfpDynamicLeaseException("The lease SID is not a valid Windows SID.", exception);
        }

        if (!string.Equals(sid.Value, leaseSid, StringComparison.Ordinal))
        {
            throw new WfpDynamicLeaseException("The lease SID is not in canonical string form.");
        }

        string[] parts = leaseSid.Split('-');
        bool validUserSid = principalKind == LeasePrincipalKind.UserSid
            && parts.Length == 8
            && leaseSid.StartsWith("S-1-5-21-", StringComparison.Ordinal)
            && parts.Skip(4).Take(3).All(IsPositiveCanonicalUInt32)
            && IsCanonicalUInt32AtLeast(parts[7], 1000);
        bool validPackageSid = principalKind == LeasePrincipalKind.AppContainerPackageSid
            && parts.Length == 11
            && leaseSid.StartsWith("S-1-15-2-", StringComparison.Ordinal)
            && parts.Skip(4).All(IsCanonicalUInt32);
        if (!validUserSid && !validPackageSid)
        {
            throw new WfpDynamicLeaseException("The lease SID does not match the supported non-built-in principal kind.");
        }
    }

    private static bool RuleSidMatchesPlan(LeasePolicyRule rule, DynamicLeasePlan plan, int listenerPort)
    {
        if (string.Equals(rule.LeaseSid, plan.LeaseSid, StringComparison.Ordinal))
        {
            return true;
        }

        // The current compiler has one deliberately endpoint-wide listener
        // denial with no identity condition. Allow only its exact shape; adding
        // the lease SID would change the native filter semantics. Every other
        // dynamic rule must carry the plan SID.
        return rule.LeaseSid is null
            && rule.RuleId == $"lease-{plan.LeaseId}-deny-other-listener-clients"
            && rule.Purpose == "Block every local process except the matching lease browser from connecting to this worker listener."
            && rule.IdentityCondition == "none; endpoint-wide listener block"
            && rule.AddressFamily == LeasePolicyAddressFamily.IPv4
            && rule.Action == LeasePolicyAction.Block
            && rule.WeightRangeIndex == LeasePolicyCompiler.DefaultDenyWeightRangeIndex
            && rule.AppIdHex is null
            && rule.RemoteAddress == "127.0.0.1"
            && rule.Protocol == 6
            && rule.RemotePort == listenerPort
            && !rule.ClearActionRight;
    }

    private static bool IsCanonicalUInt32(string value) =>
        uint.TryParse(value, System.Globalization.NumberStyles.None, System.Globalization.CultureInfo.InvariantCulture, out uint number)
        && string.Equals(number.ToString(System.Globalization.CultureInfo.InvariantCulture), value, StringComparison.Ordinal);

    private static bool IsPositiveCanonicalUInt32(string value) =>
        IsCanonicalUInt32(value)
        && uint.TryParse(value, out uint number)
        && number > 0;

    private static bool IsCanonicalUInt32AtLeast(string value, uint minimum) =>
        IsCanonicalUInt32(value)
        && uint.TryParse(value, out uint number)
        && number >= minimum;

    private static DynamicLeaseProviderIdentity CreateDynamicProvider(Guid leaseId)
    {
        Guid key = DynamicProviderKey(leaseId);
        var provider = new DynamicLeaseProviderIdentity(
            leaseId,
            key,
            $"DouyinTranscript:lease-provider:v1:{leaseId:N}",
            $"Dynamic WFP provider for capture lease {leaseId:N}.");
        return provider with { NativeProjection = WfpNativeObjectProjection.ForDynamicLeaseProvider(provider) };
    }

    private static Guid DynamicProviderKey(Guid leaseId)
    {
        byte[] identity = Encoding.UTF8.GetBytes(
            $"DouyinTranscript.Wfp.Runtime.dynamic-provider.v1\0{leaseId:D}");
        try
        {
            Guid key = new(SHA256.HashData(identity).AsSpan(0, 16));
            if (key == Guid.Empty || key == WfpServicePolicyIdentity.ProviderKey)
            {
                throw new WfpDynamicLeaseException("The derived dynamic provider key is reserved.");
            }
            return key;
        }
        finally
        {
            CryptographicOperations.ZeroMemory(identity);
        }
    }

    private static Guid DynamicFilterKey(Guid leaseId, Guid providerKey, string ruleId)
    {
        byte[] identity = Encoding.UTF8.GetBytes(
            $"DouyinTranscript.Wfp.Runtime.dynamic-lease.v1\0{providerKey:D}\0{leaseId:D}\0{ruleId}");
        try
        {
            return new Guid(SHA256.HashData(identity).AsSpan(0, 16));
        }
        finally
        {
            CryptographicOperations.ZeroMemory(identity);
        }
    }

    private static string DynamicFilterName(Guid leaseId, string ruleId) =>
        $"{DynamicFilterNamePrefix}{leaseId:N}:{ruleId}";

    private void VerifyReadback(IDynamicLeasePolicySession session, ValidatedPlan plan)
    {
        DynamicLeaseSessionReadback readback = session.Readback()
            ?? throw new WfpDynamicLeaseException("The dynamic session returned no readback.");
        if (readback.LeaseId != plan.LeaseId
            || readback.SessionId != session.SessionId
            || !readback.IsComplete
            || readback.Provider is null
            || readback.SecurityDescriptors is null
            || readback.Filters is null
            || readback.Filters.Count != plan.Filters.Count
            || readback.Filters.Count > MaxDynamicRulesPerLease)
        {
            throw new WfpDynamicLeaseException("The dynamic session readback is incomplete or has the wrong lease/session scope.");
        }

        DynamicLeaseProviderIdentity actualProvider = readback.Provider;
        try
        {
            WfpNativeObjectProjection.RequireExact(
                actualProvider.NativeProjection,
                plan.Provider.NativeProjection!,
                "dynamic lease provider");
        }
        catch (WfpBaselineOwnershipException exception)
        {
            throw new WfpDynamicLeaseException("The dynamic lease provider projection did not match exactly.", exception);
        }
        if (actualProvider != plan.Provider)
        {
            throw new WfpDynamicLeaseException("The dynamic lease provider did not match its expected identity.");
        }

        var expectedSecurity = new HashSet<WfpPolicyObjectKey>
        {
            new(WfpPolicyObjectKind.Provider, plan.Provider.Key),
        };
        foreach (WfpFilterIdentity filter in plan.Filters)
        {
            expectedSecurity.Add(new WfpPolicyObjectKey(WfpPolicyObjectKind.Filter, filter.Key));
        }
        if (readback.SecurityDescriptors.Count != expectedSecurity.Count
            || !readback.SecurityDescriptors.Keys.ToHashSet().SetEquals(expectedSecurity))
        {
            throw new WfpDynamicLeaseException("The dynamic session returned missing or unexpected provider/filter ACL evidence.");
        }
        foreach (WfpPolicyObjectKey objectKey in expectedSecurity)
        {
            ValidateSecurityDescriptor(readback.SecurityDescriptors, objectKey, this.securityPolicy);
        }

        Dictionary<Guid, WfpFilterIdentity> expectedByKey = plan.Filters.ToDictionary(filter => filter.Key);
        var actualKeys = new HashSet<Guid>();
        foreach (WfpFilterIdentity? actual in readback.Filters)
        {
            if (actual is null
                || !actualKeys.Add(actual.Key)
                || !expectedByKey.TryGetValue(actual.Key, out WfpFilterIdentity? expected))
            {
                throw new WfpDynamicLeaseException("The dynamic session returned a duplicate or unexpected filter key.");
            }

            try
            {
                WfpNativeObjectProjection.RequireExact(
                    actual.NativeProjection,
                    expected.NativeProjection!,
                    "dynamic lease filter");
            }
            catch (WfpBaselineOwnershipException exception)
            {
                throw new WfpDynamicLeaseException("A dynamic lease filter projection did not match exactly.", exception);
            }
            if (actual != expected)
            {
                throw new WfpDynamicLeaseException("A dynamic lease filter did not match its complete expected readback.");
            }
            if (actual.ProviderKey != plan.Provider.Key
                || actual.SublayerKey != WfpServicePolicyIdentity.SublayerKey
                || actual.Persistent)
            {
                throw new WfpDynamicLeaseException("A dynamic lease filter is outside its provider/sublayer/lifetime contract.");
            }
        }

        if (actualKeys.Count != expectedByKey.Count)
        {
            throw new WfpDynamicLeaseException("The dynamic session omitted an expected filter.");
        }
    }

    private sealed record ValidatedPlan(
        Guid LeaseId,
        string LeaseSid,
        DynamicLeaseProviderIdentity Provider,
        IReadOnlyList<WfpFilterIdentity> Filters);

    private static void ValidateSecurityDescriptor(
        IReadOnlyDictionary<WfpPolicyObjectKey, SecurityDescriptorSnapshot> descriptors,
        WfpPolicyObjectKey key,
        WfpObjectSecurityPolicy securityPolicy)
    {
        if (!descriptors.TryGetValue(key, out SecurityDescriptorSnapshot? descriptor)
            || descriptor is null
            || string.IsNullOrEmpty(descriptor.Sddl)
            || descriptor.Sddl.Length > 4096
            || string.IsNullOrEmpty(descriptor.Sha256)
            || descriptor.Sha256.Length != 64
            || !descriptor.DaclPresent
            || descriptor.HasNullDacl
            || descriptor.BinaryLength is < 20 or > 1_048_576
            || !string.Equals(descriptor.Sddl, securityPolicy.For(key.Kind), StringComparison.Ordinal))
        {
            throw new WfpDynamicLeaseException($"The dynamic lease {key.Kind} has missing or unexpected owner/DACL evidence.");
        }

        byte[] expectedHash = SHA256.HashData(Encoding.UTF8.GetBytes(descriptor.Sddl));
        byte[] reportedHash;
        try
        {
            reportedHash = Convert.FromHexString(descriptor.Sha256);
        }
        catch (FormatException exception)
        {
            throw new WfpDynamicLeaseException($"The dynamic lease {key.Kind} ACL digest is malformed.", exception);
        }
        if (!CryptographicOperations.FixedTimeEquals(expectedHash, reportedHash))
        {
            throw new WfpDynamicLeaseException($"The dynamic lease {key.Kind} ACL digest does not match its normalized SDDL.");
        }
    }
}

internal sealed class DynamicLeaseScope
{
    private readonly DynamicLeaseCoordinator owner;
    private bool workerStarted;
    private bool closing;
    private bool closed;

    internal DynamicLeaseScope(
        DynamicLeaseCoordinator owner,
        IDynamicLeasePolicySession session,
        Guid leaseId,
        DynamicLeaseProviderIdentity provider,
        IReadOnlyList<WfpFilterIdentity> filters)
    {
        this.owner = owner;
        this.Session = session;
        this.LeaseId = leaseId;
        this.Provider = provider;
        this.Filters = filters;
    }

    internal Guid LeaseId { get; }
    internal DynamicLeaseProviderIdentity Provider { get; }
    internal IDynamicLeasePolicySession Session { get; }
    internal IReadOnlyList<WfpFilterIdentity> Filters { get; }
    internal bool IsClosedCore => this.closed;
    internal bool IsClosingCore => this.closing;
    internal bool WorkerStartedCore => this.workerStarted;

    internal void MarkWorkerStarted() => this.owner.MarkWorkerStarted(this);

    internal void Close(
        Func<CancellationToken, LeaseJobTreeDrainReceipt>? jobTreeDrain = null,
        CancellationToken cancellationToken = default) =>
        this.owner.Close(this, jobTreeDrain, cancellationToken);

    internal void MarkWorkerStartedCore()
    {
        if (this.closed || this.closing)
        {
            throw new WfpDynamicLeaseException("A worker cannot start after lease close has begun.");
        }
        this.workerStarted = true;
    }

    internal void SetClosingCore(bool value) => this.closing = value;

    internal void MarkClosedCore()
    {
        this.closed = true;
        this.closing = false;
    }
}

internal sealed class WfpDynamicLeaseException(string message, Exception? innerException = null)
    : InvalidOperationException(message, innerException);

internal sealed class WfpDynamicLeaseCleanupException(Exception operationFailure, Exception cleanupFailure)
    : InvalidOperationException(
        "A dynamic lease operation or close failed; its session handle remains retained and future lease opens are isolated.",
        new AggregateException(operationFailure, cleanupFailure));
