using System.Globalization;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using DouyinTranscript.NetworkPolicy;

namespace WfpPolicyPlan;

/// <summary>
/// The kind of lease principal that the trusted service has already created.
/// The service must verify this SID against the actual suspended worker/browser
/// token before it starts either process.
/// </summary>
public enum LeasePrincipalKind
{
    UserSid,
    AppContainerPackageSid,
}

public enum LeasePolicyAddressFamily
{
    IPv4,
    IPv6,
}

public enum LeasePolicyAction
{
    Block,
    Permit,
}

public enum LeasePolicyLifetime
{
    PersistentDefaultDeny,
    LeaseDynamic,
}

public enum ProtectedApplicationRole
{
    Browser,
    Worker,
}

/// <summary>
/// An AppID derived and verified by the trusted service from a protected binary.
/// This input type documents the trust requirement; the compiler cannot attest
/// the source path or the caller.
/// </summary>
public sealed record ProtectedApplicationInput(
    ProtectedApplicationRole Role,
    string AppIdHex);

/// <summary>
/// Service-owned facts used to compile one lease's semantic WFP policy.
/// App IDs must be the exact byte blobs returned by FwpmGetAppIdFromFileName0,
/// encoded as hexadecimal. The complete, already-validated A/AAAA target set
/// must be supplied; this planner does not perform DNS or attest its provenance.
/// </summary>
public sealed record LeasePolicyInput(
    Guid LeaseId,
    LeasePrincipalKind PrincipalKind,
    string LeaseSid,
    string BrowserAppIdHex,
    string WorkerAppIdHex,
    int ListenerPort,
    string NumericResolverAddress,
    IReadOnlyCollection<string> PinnedPublicAddresses);

/// <summary>
/// A typed, deterministic policy intent. This document is deliberately not a
/// deployable FWPM_FILTER0 set and must not be used as proof that WFP is active.
/// </summary>
public sealed record LeasePolicyDocument(
    string SchemaVersion,
    string PlanKind,
    string Deployability,
    string Sublayer,
    IReadOnlyList<LeasePolicyRule> Rules,
    IReadOnlyList<string> UnresolvedValidationItems,
    string SafetyBoundary);

/// <summary>
/// Persistent AppID-only baseline rules. It cannot carry a lease SID, listener
/// endpoint, or temporary permit, so callers cannot add it to a lease session.
/// </summary>
internal sealed class PersistentAppIdBaselinePlan
{
    internal PersistentAppIdBaselinePlan(
        string schemaVersion,
        IReadOnlyList<LeasePolicyRule> rules,
        IReadOnlyList<string> unresolvedValidationItems,
        string safetyBoundary)
    {
        SchemaVersion = schemaVersion;
        Rules = rules;
        UnresolvedValidationItems = unresolvedValidationItems;
        SafetyBoundary = safetyBoundary;
    }

    public string SchemaVersion { get; }
    public string PlanKind => "persistent-app-id-baseline";
    public string Deployability => "not-deployable";
    public IReadOnlyList<LeasePolicyRule> Rules { get; }
    public IReadOnlyList<string> UnresolvedValidationItems { get; }
    public string SafetyBoundary { get; }
}

/// <summary>
/// One lease's dynamic-only rules. It cannot carry a persistent filter and is
/// kept separate from the service-wide AppID baseline.
/// </summary>
internal sealed class DynamicLeasePlan
{
    internal DynamicLeasePlan(
        string schemaVersion,
        string leaseId,
        LeasePrincipalKind principalKind,
        string leaseSid,
        IReadOnlyList<LeasePolicyRule> rules,
        IReadOnlyList<string> unresolvedValidationItems,
        string safetyBoundary)
    {
        SchemaVersion = schemaVersion;
        LeaseId = leaseId;
        PrincipalKind = principalKind;
        LeaseSid = leaseSid;
        Rules = rules;
        UnresolvedValidationItems = unresolvedValidationItems;
        SafetyBoundary = safetyBoundary;
    }

    public string SchemaVersion { get; }
    public string PlanKind => "dynamic-lease";
    public string Deployability => "not-deployable";
    public string LeaseId { get; }
    public LeasePrincipalKind PrincipalKind { get; }
    public string LeaseSid { get; }
    public IReadOnlyList<LeasePolicyRule> Rules { get; }
    public IReadOnlyList<string> UnresolvedValidationItems { get; }
    public string SafetyBoundary { get; }
}

/// <summary>
/// The service-authoritative composition of the persistent AppID baseline and
/// the dynamic leases that are covered by it. Service code must use this
/// compiler entry point rather than combining separately compiled plans.
/// </summary>
internal sealed class ServiceWideLeasePolicyPlan
{
    internal ServiceWideLeasePolicyPlan(
        PersistentAppIdBaselinePlan persistentBaseline,
        IReadOnlyList<DynamicLeasePlan> dynamicLeases)
    {
        PersistentBaseline = persistentBaseline;
        DynamicLeases = dynamicLeases;
    }

    public PersistentAppIdBaselinePlan PersistentBaseline { get; }
    public IReadOnlyList<DynamicLeasePlan> DynamicLeases { get; }
}

/// <summary>
/// One single-family ALE_AUTH_CONNECT rule. Null identity/remote fields mean
/// the condition is intentionally omitted, not wildcarded by client input.
/// Weight is a FWP_UINT8 range index (0..15), not a literal UINT8 weight.
/// </summary>
public sealed record LeasePolicyRule(
    string RuleId,
    string Purpose,
    LeasePolicyAddressFamily AddressFamily,
    LeasePolicyAction Action,
    byte WeightRangeIndex,
    LeasePolicyLifetime Lifetime,
    string? LeaseId,
    string? AppIdHex,
    string? LeaseSid,
    string IdentityCondition,
    string? RemoteAddress,
    int? Protocol,
    int? RemotePort,
    bool ClearActionRight);

/// <summary>
/// Compiles the current control-plane/worker/lease boundary into an auditable
/// semantic rule set. It does not call BFE, WFP, DNS, sockets, or Windows APIs
/// that mutate host policy.
/// </summary>
public static class LeasePolicyCompiler
{
    public const string SchemaVersion = "1";
    public const int MaxLeasesPerPlan = 64;
    public const int MaxPinnedAddressesPerLease = 64;
    public const int DnsPort = 53;
    public const int HttpsPort = 443;
    public const byte DefaultDenyWeightRangeIndex = 1;
    public const byte LeasePermitWeightRangeIndex = 15;

    private const string IPv4Loopback = "127.0.0.1";
    private static readonly string[] SafetyItems =
    [
        "This semantic lease plan is not deployable; no FWPM_FILTER0 is allocated and no BFE/WFP object is read or changed.",
        "A trusted service must derive both AppID blobs from administrator-protected executable paths and verify the lease SID in the actual process tokens.",
        "The service must keep application-level default-deny filters persistent and close each lease dynamic session only after terminating the complete browser/worker process trees and closing their sockets.",
        "All rules must be placed in one service-owned sublayer with the emitted range-index ordering; hard blocks from other providers must continue to win.",
        "The caller must supply the complete A/AAAA result set after validating every CNAME hop; this planner validates that supplied addresses are public but cannot prove DNS completeness or ownership.",
        "A browser permit must not be enabled until the worker listener is bound only to 127.0.0.1 and is owned by the matching lease worker.",
    ];

    private static readonly string[] BaselineSafetyItems =
    [
        "This AppID baseline is a non-deployable semantic plan; it does not open BFE or create WFP objects.",
        "The trusted service must derive each AppID from an administrator-protected executable and read back the installed baseline before accepting capture requests.",
        "The service must use stable service-owned provider and sublayer keys and preserve blocks from other providers.",
    ];

    private static readonly string[] DynamicLeaseSafetyItems =
    [
        "This lease plan contains only dynamic rules and is not a deployable FWPM_FILTER0 set.",
        "The service must create a dynamic WFP session per lease and close it only after a non-breakaway KILL_ON_JOB_CLOSE job has terminated the complete process tree and its sockets.",
        "The service must verify the lease SID in the actual suspended process tokens before resuming either process.",
    ];

    /// <summary>
    /// Compile the service-wide persistent AppID baseline separately from any
    /// lease plan. Both browser and worker roles are required.
    /// </summary>
    internal static PersistentAppIdBaselinePlan CompilePersistentAppIdBaseline(
        IEnumerable<ProtectedApplicationInput> applications)
    {
        ArgumentNullException.ThrowIfNull(applications);
        var normalized = new List<(string Role, string AppId)>();
        var seen = new HashSet<(ProtectedApplicationRole Role, string AppId)>();
        var roles = new HashSet<ProtectedApplicationRole>();
        foreach (ProtectedApplicationInput application in applications)
        {
            if (application is null || !Enum.IsDefined(application.Role))
            {
                throw new ArgumentException("Protected application role is missing or unsupported.", nameof(applications));
            }

            string appId = NormalizeAppId(application.AppIdHex, nameof(applications));
            if (!seen.Add((application.Role, appId)))
            {
                throw new ArgumentException("Protected AppID entries must be unique.", nameof(applications));
            }
            roles.Add(application.Role);
            normalized.Add((application.Role == ProtectedApplicationRole.Browser ? "browser" : "worker", appId));
        }

        if (normalized.Count is < 2 or > 128
            || !roles.Contains(ProtectedApplicationRole.Browser)
            || !roles.Contains(ProtectedApplicationRole.Worker))
        {
            throw new ArgumentException("The AppID baseline must contain browser and worker identities.", nameof(applications));
        }
        if (normalized.Select(item => item.AppId).Distinct(StringComparer.Ordinal).Count() != normalized.Count)
        {
            throw new ArgumentException("One AppID cannot be assigned to multiple protected roles or paths.", nameof(applications));
        }

        var rules = new List<LeasePolicyRule>();
        AddPersistentApplicationDenies(normalized, rules);
        return new PersistentAppIdBaselinePlan(
            SchemaVersion,
            Array.AsReadOnly(rules.OrderBy(rule => rule.RuleId, StringComparer.Ordinal).ToArray()),
            Array.AsReadOnly(BaselineSafetyItems.ToArray()),
            "Persistent AppID baseline only. Service installation, protected-path provenance, BFE state, readback, and arbitration are not verified.");
    }

    /// <summary>
    /// Compile one lease's deny/permit set without any persistent rules.
    /// </summary>
    internal static DynamicLeasePlan CompileDynamicLease(LeasePolicyInput lease)
    {
        ArgumentNullException.ThrowIfNull(lease);
        NormalizedLease normalized = Normalize(lease);
        ValidateUniqueLeaseSet([normalized]);

        var rules = new List<LeasePolicyRule>();
        AddLeasePrincipalDenies([normalized], rules);
        AddLeaseRules(normalized, rules);
        return new DynamicLeasePlan(
            SchemaVersion,
            normalized.LeaseId,
            normalized.PrincipalKind,
            normalized.LeaseSid,
            Array.AsReadOnly(rules.OrderBy(rule => rule.RuleId, StringComparer.Ordinal).ToArray()),
            Array.AsReadOnly(DynamicLeaseSafetyItems.ToArray()),
            "Dynamic lease rules only. No WFP session, job object, process token, listener, socket, or policy lifetime is created or verified.");
    }

    /// <summary>
    /// Compile the persistent baseline and active dynamic leases as one
    /// service-wide plan. Every lease browser and worker AppID must be covered
    /// by an entry with the matching protected role in the baseline.
    /// </summary>
    internal static ServiceWideLeasePolicyPlan CompileServiceWidePlan(
        IEnumerable<ProtectedApplicationInput> applications,
        IEnumerable<LeasePolicyInput> leases)
    {
        ArgumentNullException.ThrowIfNull(applications);
        ArgumentNullException.ThrowIfNull(leases);

        var applicationInputs = new List<ProtectedApplicationInput>();
        foreach (ProtectedApplicationInput application in applications)
        {
            if (applicationInputs.Count == 128)
            {
                throw new ArgumentException("The protected AppID baseline cannot exceed 128 entries.", nameof(applications));
            }
            applicationInputs.Add(application);
        }

        PersistentAppIdBaselinePlan baseline = CompilePersistentAppIdBaseline(applicationInputs);
        HashSet<string> browserAppIds = applicationInputs
            .Where(application => application.Role == ProtectedApplicationRole.Browser)
            .Select(application => NormalizeAppId(application.AppIdHex, nameof(applications)))
            .ToHashSet(StringComparer.Ordinal);
        HashSet<string> workerAppIds = applicationInputs
            .Where(application => application.Role == ProtectedApplicationRole.Worker)
            .Select(application => NormalizeAppId(application.AppIdHex, nameof(applications)))
            .ToHashSet(StringComparer.Ordinal);

        var leaseInputs = new List<LeasePolicyInput>(capacity: Math.Min(MaxLeasesPerPlan, 8));
        foreach (LeasePolicyInput lease in leases)
        {
            if (leaseInputs.Count == MaxLeasesPerPlan)
            {
                throw new ArgumentException($"A policy must contain between 1 and {MaxLeasesPerPlan} leases.", nameof(leases));
            }
            leaseInputs.Add(lease);
        }
        if (leaseInputs.Count == 0)
        {
            throw new ArgumentException($"A policy must contain between 1 and {MaxLeasesPerPlan} leases.", nameof(leases));
        }

        NormalizedLease[] normalizedLeases = leaseInputs.Select(Normalize).ToArray();
        ValidateUniqueLeaseSet(normalizedLeases);
        foreach (NormalizedLease lease in normalizedLeases)
        {
            if (!browserAppIds.Contains(lease.BrowserAppId) || !workerAppIds.Contains(lease.WorkerAppId))
            {
                throw new ArgumentException(
                    "Every lease browser and worker AppID must be covered by the matching role in the persistent baseline.",
                    nameof(leases));
            }
        }

        DynamicLeasePlan[] dynamicLeases = leaseInputs
            .Select(CompileDynamicLease)
            .OrderBy(plan => plan.LeaseId, StringComparer.Ordinal)
            .ToArray();
        return new ServiceWideLeasePolicyPlan(baseline, Array.AsReadOnly(dynamicLeases));
    }

    /// <summary>
    /// Compile a complete active-lease set. Duplicate lease IDs, principals,
    /// listener ports, and cross-role executable identities are rejected so a
    /// permit generated for one worker cannot become a second lease's permit.
    /// </summary>
    public static LeasePolicyDocument Compile(IEnumerable<LeasePolicyInput> leases)
    {
        ArgumentNullException.ThrowIfNull(leases);
        var source = new List<LeasePolicyInput>(capacity: Math.Min(MaxLeasesPerPlan, 8));
        foreach (LeasePolicyInput lease in leases)
        {
            if (source.Count == MaxLeasesPerPlan)
            {
                throw new ArgumentException($"A policy must contain between 1 and {MaxLeasesPerPlan} leases.", nameof(leases));
            }
            source.Add(lease);
        }
        if (source.Count == 0)
        {
            throw new ArgumentException($"A policy must contain between 1 and {MaxLeasesPerPlan} leases.", nameof(leases));
        }

        NormalizedLease[] normalized = source.Select(Normalize).ToArray();
        ValidateUniqueLeaseSet(normalized);

        var rules = new List<LeasePolicyRule>();
        AddPersistentApplicationDenies(normalized, rules);
        AddLeasePrincipalDenies(normalized, rules);
        foreach (NormalizedLease lease in normalized.OrderBy(value => value.LeaseId, StringComparer.Ordinal))
        {
            AddLeaseRules(lease, rules);
        }

        LeasePolicyRule[] orderedRules = rules.OrderBy(rule => rule.RuleId, StringComparer.Ordinal).ToArray();
        if (orderedRules.Select(rule => rule.RuleId).Distinct(StringComparer.Ordinal).Count() != orderedRules.Length)
        {
            throw new InvalidOperationException("The compiled policy contains duplicate rule identifiers.");
        }

        return new LeasePolicyDocument(
            SchemaVersion,
            PlanKind: "per-lease-semantic-preview",
            Deployability: "not-deployable",
            Sublayer: "service-owned sublayer required; placeholder only",
            Rules: Array.AsReadOnly(orderedRules),
            UnresolvedValidationItems: Array.AsReadOnly(SafetyItems.ToArray()),
            SafetyBoundary: "Pure rule planning only. It does not open BFE, allocate/add/delete WFP filters, start a service or worker, verify Chromium identity, perform DNS, or prove network isolation.");
    }

    private static NormalizedLease Normalize(LeasePolicyInput input)
    {
        ArgumentNullException.ThrowIfNull(input);
        if (input.LeaseId == Guid.Empty)
        {
            throw new ArgumentException("LeaseId must be a non-empty service-generated UUID.");
        }

        string sid = NormalizeLeaseSid(input.LeaseSid, input.PrincipalKind);
        string browserAppId = NormalizeAppId(input.BrowserAppIdHex, nameof(input.BrowserAppIdHex));
        string workerAppId = NormalizeAppId(input.WorkerAppIdHex, nameof(input.WorkerAppIdHex));
        if (browserAppId.Equals(workerAppId, StringComparison.Ordinal))
        {
            throw new ArgumentException("Browser and worker must have different protected AppID blobs.");
        }

        if (input.ListenerPort is < 1 or > ushort.MaxValue)
        {
            throw new ArgumentOutOfRangeException(nameof(input.ListenerPort), "ListenerPort must be between 1 and 65535.");
        }

        IPAddress resolver = ParseNumericAddress(input.NumericResolverAddress, nameof(input.NumericResolverAddress));
        if (!IsPublicUnicast(resolver))
        {
            throw new ArgumentException("The configured numeric resolver must be a public unicast address.", nameof(input.NumericResolverAddress));
        }

        if (input.PinnedPublicAddresses is null)
        {
            throw new ArgumentNullException(nameof(input.PinnedPublicAddresses));
        }

        var pinnedSet = new HashSet<string>(StringComparer.Ordinal);
        int suppliedAddressCount = 0;
        foreach (string suppliedAddress in input.PinnedPublicAddresses)
        {
            if (++suppliedAddressCount > MaxPinnedAddressesPerLease)
            {
                throw new ArgumentException($"A lease must contain at most {MaxPinnedAddressesPerLease} pinned addresses.", nameof(input.PinnedPublicAddresses));
            }
            IPAddress address = ParseNumericAddress(suppliedAddress, nameof(input.PinnedPublicAddresses));
            if (!IsPublicUnicast(address))
            {
                throw new ArgumentException("Every pinned upstream destination must be a public unicast address.", nameof(input.PinnedPublicAddresses));
            }
            pinnedSet.Add(FormatAddress(address));
        }

        string[] pinned = pinnedSet
            .OrderBy(AddressSortKey, StringComparer.Ordinal)
            .ToArray();

        if (pinned.Length is 0 or > MaxPinnedAddressesPerLease)
        {
            throw new ArgumentException($"A lease must contain between 1 and {MaxPinnedAddressesPerLease} distinct pinned public addresses.", nameof(input.PinnedPublicAddresses));
        }

        return new NormalizedLease(
            input.LeaseId.ToString("N", CultureInfo.InvariantCulture),
            input.PrincipalKind,
            sid,
            browserAppId,
            workerAppId,
            input.ListenerPort,
            FormatAddress(resolver),
            pinned);
    }

    private static void ValidateUniqueLeaseSet(IReadOnlyList<NormalizedLease> leases)
    {
        if (leases.Select(lease => lease.LeaseId).Distinct(StringComparer.Ordinal).Count() != leases.Count)
        {
            throw new ArgumentException("Lease IDs must be unique.", nameof(leases));
        }
        if (leases.Select(lease => lease.LeaseSid).Distinct(StringComparer.OrdinalIgnoreCase).Count() != leases.Count)
        {
            throw new ArgumentException("Every lease must have a distinct OS principal SID.", nameof(leases));
        }
        if (leases.Select(lease => lease.ListenerPort).Distinct().Count() != leases.Count)
        {
            throw new ArgumentException("Every lease must have a distinct listener port.", nameof(leases));
        }

        HashSet<string> browserIds = leases.Select(lease => lease.BrowserAppId).ToHashSet(StringComparer.Ordinal);
        HashSet<string> workerIds = leases.Select(lease => lease.WorkerAppId).ToHashSet(StringComparer.Ordinal);
        if (browserIds.Overlaps(workerIds))
        {
            throw new ArgumentException("Browser and worker AppID sets must be disjoint across all leases.", nameof(leases));
        }
    }

    private static void AddPersistentApplicationDenies(
        IEnumerable<NormalizedLease> leases,
        ICollection<LeasePolicyRule> rules)
    {
        AddPersistentApplicationDenies(
            leases.SelectMany(lease => new[]
            {
                (Role: "browser", AppId: lease.BrowserAppId),
                (Role: "worker", AppId: lease.WorkerAppId),
            }),
            rules);
    }

    private static void AddPersistentApplicationDenies(
        IEnumerable<(string Role, string AppId)> applications,
        ICollection<LeasePolicyRule> rules)
    {
        var appIds = applications
            .Distinct()
            .OrderBy(value => value.Role, StringComparer.Ordinal)
            .ThenBy(value => value.AppId, StringComparer.Ordinal);

        foreach ((string role, string appId) in appIds)
        {
            string identityHash = Convert.ToHexString(SHA256.HashData(Convert.FromHexString(appId)))[..16];
            foreach (LeasePolicyAddressFamily family in Enum.GetValues<LeasePolicyAddressFamily>())
            {
                rules.Add(new LeasePolicyRule(
                    RuleId: $"default-deny-{role}-{identityHash}-{FamilyToken(family)}",
                    Purpose: $"Persistent catch-all block for every {role} process from this protected AppID; higher-weight exact lease permits are the only intended exceptions.",
                    AddressFamily: family,
                    Action: LeasePolicyAction.Block,
                    WeightRangeIndex: DefaultDenyWeightRangeIndex,
                    Lifetime: LeasePolicyLifetime.PersistentDefaultDeny,
                    LeaseId: null,
                    AppIdHex: appId,
                    LeaseSid: null,
                    IdentityCondition: "ALE_APP_ID",
                    RemoteAddress: null,
                    Protocol: null,
                    RemotePort: null,
                    ClearActionRight: false));
            }
        }
    }

    private static void AddLeasePrincipalDenies(
        IEnumerable<NormalizedLease> leases,
        ICollection<LeasePolicyRule> rules)
    {
        foreach (NormalizedLease lease in leases.OrderBy(value => value.LeaseId, StringComparer.Ordinal))
        {
            string identityCondition = PrincipalCondition(lease);
            foreach (LeasePolicyAddressFamily family in Enum.GetValues<LeasePolicyAddressFamily>())
            {
                rules.Add(new LeasePolicyRule(
                    RuleId: $"default-deny-principal-{lease.LeaseId}-{FamilyToken(family)}",
                    Purpose: "Dynamic-session catch-all block for this unique lease principal, regardless of AppID; the service must pair it with a kill-on-close job that terminates the complete lease process tree before the session closes.",
                    AddressFamily: family,
                    Action: LeasePolicyAction.Block,
                    WeightRangeIndex: DefaultDenyWeightRangeIndex,
                    Lifetime: LeasePolicyLifetime.LeaseDynamic,
                    LeaseId: lease.LeaseId,
                    AppIdHex: null,
                    LeaseSid: lease.LeaseSid,
                    IdentityCondition: identityCondition,
                    RemoteAddress: null,
                    Protocol: null,
                    RemotePort: null,
                    ClearActionRight: false));
            }
        }
    }

    private static void AddLeaseRules(NormalizedLease lease, ICollection<LeasePolicyRule> rules)
    {
        string leasePrefix = $"lease-{lease.LeaseId}";
        string principalCondition = PrincipalCondition(lease);

        // The worker listens on IPv4 loopback only. The browser's IPv6 direct
        // traffic remains covered by its persistent IPv6 default-deny rule.
        rules.Add(new LeasePolicyRule(
            RuleId: $"{leasePrefix}-deny-other-listener-clients",
            Purpose: "Block every local process except the matching lease browser from connecting to this worker listener.",
            AddressFamily: LeasePolicyAddressFamily.IPv4,
            Action: LeasePolicyAction.Block,
            WeightRangeIndex: DefaultDenyWeightRangeIndex,
            Lifetime: LeasePolicyLifetime.LeaseDynamic,
            LeaseId: lease.LeaseId,
            AppIdHex: null,
            LeaseSid: null,
            IdentityCondition: "none; endpoint-wide listener block",
            RemoteAddress: IPv4Loopback,
            Protocol: 6,
            RemotePort: lease.ListenerPort,
            ClearActionRight: false));

        rules.Add(new LeasePolicyRule(
            RuleId: $"{leasePrefix}-browser-allow-worker-listener",
            Purpose: "Allow only this browser AppID and lease principal to connect to this lease's IPv4 loopback worker listener.",
            AddressFamily: LeasePolicyAddressFamily.IPv4,
            Action: LeasePolicyAction.Permit,
            WeightRangeIndex: LeasePermitWeightRangeIndex,
            Lifetime: LeasePolicyLifetime.LeaseDynamic,
            LeaseId: lease.LeaseId,
            AppIdHex: lease.BrowserAppId,
            LeaseSid: lease.LeaseSid,
            IdentityCondition: principalCondition,
            RemoteAddress: IPv4Loopback,
            Protocol: 6,
            RemotePort: lease.ListenerPort,
            ClearActionRight: false));

        IPAddress resolver = IPAddress.Parse(lease.NumericResolverAddress);
        LeasePolicyAddressFamily resolverFamily = AddressFamilyOf(resolver);
        foreach (int protocol in new[] { 6, 17 })
        {
            rules.Add(new LeasePolicyRule(
                RuleId: $"{leasePrefix}-worker-allow-dns-{FamilyToken(resolverFamily)}-{ProtocolToken(protocol)}",
                Purpose: "Allow this lease worker to contact only its configured numeric DNS resolver on TCP/UDP port 53.",
                AddressFamily: resolverFamily,
                Action: LeasePolicyAction.Permit,
                WeightRangeIndex: LeasePermitWeightRangeIndex,
                Lifetime: LeasePolicyLifetime.LeaseDynamic,
                LeaseId: lease.LeaseId,
                AppIdHex: lease.WorkerAppId,
                LeaseSid: lease.LeaseSid,
                IdentityCondition: principalCondition,
                RemoteAddress: lease.NumericResolverAddress,
                Protocol: protocol,
                RemotePort: DnsPort,
                ClearActionRight: false));
        }

        foreach (string pinnedAddress in lease.PinnedPublicAddresses)
        {
            IPAddress address = IPAddress.Parse(pinnedAddress);
            LeasePolicyAddressFamily family = AddressFamilyOf(address);
            rules.Add(new LeasePolicyRule(
                RuleId: $"{leasePrefix}-worker-allow-upstream-{family.ToString().ToLowerInvariant()}-{AddressSortKey(pinnedAddress)}",
                Purpose: "Allow this lease worker to connect to one fully validated, numerically pinned public address on TCP port 443.",
                AddressFamily: family,
                Action: LeasePolicyAction.Permit,
                WeightRangeIndex: LeasePermitWeightRangeIndex,
                Lifetime: LeasePolicyLifetime.LeaseDynamic,
                LeaseId: lease.LeaseId,
                AppIdHex: lease.WorkerAppId,
                LeaseSid: lease.LeaseSid,
                IdentityCondition: principalCondition,
                RemoteAddress: pinnedAddress,
                Protocol: 6,
                RemotePort: HttpsPort,
                ClearActionRight: false));
        }
    }

    private static string PrincipalCondition(NormalizedLease lease) =>
        lease.PrincipalKind == LeasePrincipalKind.UserSid ? "ALE_USER_ID" : "ALE_PACKAGE_ID";

    private static string NormalizeLeaseSid(string value, LeasePrincipalKind kind)
    {
        if (string.IsNullOrWhiteSpace(value) || value != value.Trim())
        {
            throw new ArgumentException("Lease SID must be a canonical, non-empty SID string.", nameof(value));
        }

        string normalized = value.ToUpperInvariant();
        string[] parts = normalized.Split('-');
        bool userSidShape = kind == LeasePrincipalKind.UserSid
            && parts.Length == 8
            && normalized.StartsWith("S-1-5-21-", StringComparison.OrdinalIgnoreCase);
        bool packageSid = kind == LeasePrincipalKind.AppContainerPackageSid
            // SECURITY_APP_PACKAGE_RID_COUNT is eight: the base RID 2 plus
            // seven package-derived RIDs. Exclude short built-in package SIDs.
            && parts.Length == 11
            && normalized.StartsWith("S-1-15-2-", StringComparison.OrdinalIgnoreCase);
        bool userSid = userSidShape
            && parts.Skip(4).Take(3).All(IsPositiveSubAuthority)
            && uint.TryParse(parts[7], NumberStyles.None, CultureInfo.InvariantCulture, out uint rid)
            && rid >= 1000;
        if ((!userSid && !packageSid) || parts[0] != "S" || parts[1] != "1"
            || !parts.Skip(2).All(IsCanonicalSubAuthority))
        {
            throw new ArgumentException("Lease SID must be a canonical non-built-in local account SID or AppContainer package SID matching PrincipalKind.", nameof(value));
        }
        return normalized;
    }

    private static bool IsCanonicalSubAuthority(string value) =>
        uint.TryParse(value, NumberStyles.None, CultureInfo.InvariantCulture, out uint number)
        && number.ToString(CultureInfo.InvariantCulture) == value;

    private static bool IsPositiveSubAuthority(string value) =>
        uint.TryParse(value, NumberStyles.None, CultureInfo.InvariantCulture, out uint number)
        && number > 0
        && number.ToString(CultureInfo.InvariantCulture) == value;

    private static string NormalizeAppId(string value, string parameterName)
    {
        if (string.IsNullOrEmpty(value) || value.Length % 2 != 0 || value.Length > 65_536)
        {
            throw new ArgumentException("AppID must be a non-empty, even-length hexadecimal byte blob.", parameterName);
        }
        try
        {
            byte[] bytes = Convert.FromHexString(value);
            if (bytes.Length == 0 || bytes.All(item => item == 0))
            {
                throw new ArgumentException("AppID byte blob cannot be empty or all zero.", parameterName);
            }
            return Convert.ToHexString(bytes);
        }
        catch (FormatException)
        {
            throw new ArgumentException("AppID must contain hexadecimal digits only.", parameterName);
        }
    }

    private static IPAddress ParseNumericAddress(string? value, string parameterName)
    {
        if (string.IsNullOrEmpty(value) || value != value.Trim() || value.Contains('%') || value.Contains('[') || value.Contains(']'))
        {
            throw new ArgumentException("Destination must be a plain numeric IPv4 or IPv6 address without a zone or brackets.", parameterName);
        }

        if (value.Contains('.') && value.Contains(':'))
        {
            throw new ArgumentException("IPv4-embedded IPv6 notation is not accepted.", parameterName);
        }

        IPAddress address;
        if (value.Contains(':'))
        {
            if (!IPAddress.TryParse(value, out address!) || address.AddressFamily != AddressFamily.InterNetworkV6 || address.ScopeId != 0)
            {
                throw new ArgumentException("Destination is not a valid unscoped IPv6 literal.", parameterName);
            }
        }
        else
        {
            string[] octets = value.Split('.');
            if (octets.Length != 4 || octets.Any(octet =>
                    octet.Length is < 1 or > 3
                    || (octet.Length > 1 && octet[0] == '0')
                    || !byte.TryParse(octet, NumberStyles.None, CultureInfo.InvariantCulture, out _))
            || !IPAddress.TryParse(value, out address!)
                || address.AddressFamily != AddressFamily.InterNetwork)
            {
                throw new ArgumentException("Destination is not a canonical dotted-decimal IPv4 literal.", parameterName);
            }
        }
        return address;
    }

    internal static bool IsPublicUnicast(IPAddress address) => PublicUnicastAddressPolicy.IsPublicUnicast(address);

    private static string FormatAddress(IPAddress address) => address.ToString().ToLowerInvariant();

    private static LeasePolicyAddressFamily AddressFamilyOf(IPAddress address) =>
        address.AddressFamily switch
        {
            AddressFamily.InterNetwork => LeasePolicyAddressFamily.IPv4,
            AddressFamily.InterNetworkV6 => LeasePolicyAddressFamily.IPv6,
            _ => throw new ArgumentException("Only IPv4 and IPv6 are supported."),
        };

    private static string FamilyToken(LeasePolicyAddressFamily family) =>
        family == LeasePolicyAddressFamily.IPv4 ? "v4" : "v6";

    private static string ProtocolToken(int protocol) => protocol == 6 ? "tcp" : "udp";

    private static string AddressSortKey(string address) => Convert.ToHexString(IPAddress.Parse(address).GetAddressBytes());

    private sealed record NormalizedLease(
        string LeaseId,
        LeasePrincipalKind PrincipalKind,
        string LeaseSid,
        string BrowserAppId,
        string WorkerAppId,
        int ListenerPort,
        string NumericResolverAddress,
        IReadOnlyList<string> PinnedPublicAddresses);

}
