using System.Text.Json;
using System.Runtime.Versioning;
using WfpPolicyPlan;

namespace WfpPolicyPlanTests;

[SupportedOSPlatform("windows6.0.6000")]
internal static class Program
{
    [SupportedOSPlatform("windows6.0.6000")]
    private static int Main(string[] args)
    {
        if (args.Length != 0)
        {
            Console.Error.WriteLine("Unknown or disabled test-harness arguments.");
            return 2;
        }

        (string Name, Action Run)[] tests =
        [
            ("two leases cannot borrow each other's listener, resolver, or pinned upstream", TwoLeaseCrossAccessIsDenied),
            ("policy has persistent AppID defaults and dynamic lease-scoped rules", ExplicitDefaultDenyAndExactPermits),
            ("typed AppID baseline and dynamic lease plans cannot mix lifetimes", TypedPlansKeepLifetimesSeparate),
            ("service-wide plan binds every lease AppID to its persistent role baseline", ServiceWideCompositionBindsAppIds),
            ("compiler output is deterministic under input and address ordering", OutputIsDeterministic),
            ("compiler supports a service-selected AppContainer package SID", PackageSidConditionIsExplicit),
            ("duplicate and cross-role identities fail closed", DuplicateAndCrossRoleIdentitiesFailClosed),
            ("invalid identities, ports, and numeric addresses fail closed", InvalidInputsFailClosed),
            ("non-public resolver or pinned destinations fail closed", NonPublicDestinationsFailClosed),
            ("plan is always explicitly non-deployable", OutputIsNonDeployable),
            ("native filter materializer maps IDs, values, and lifetimes without applying policy", NativeFilterPreviewMapsCompilerRules),
            ("native filter materializer rejects ambiguous or deployable-looking input", NativeFilterPreviewRejectsUnsafeInput),
            ("native filter materializer rejects forged private and arbitrary-port permits", NativeFilterPreviewRejectsForgedPermitSemantics),
            ("direct Sandbox network probe entry point is disabled", SandboxNetworkProbeEntrypointFailsClosed),
            ("direct Sandbox BFE mutation entry point is disabled", BfeProbeEntrypointFailsClosed),
        ];

        int failures = 0;
        foreach ((string name, Action run) in tests)
        {
            try
            {
                run();
                Console.WriteLine($"PASS {name}");
            }
            catch (Exception exception)
            {
                failures++;
                Console.Error.WriteLine($"FAIL {name}: {exception.GetType().Name}: {exception.Message}");
            }
        }

        Console.WriteLine($"{tests.Length - failures}/{tests.Length} policy compiler tests passed.");
        return failures == 0 ? 0 : 1;
    }

    private static void TwoLeaseCrossAccessIsDenied()
    {
        LeasePolicyInput first = Lease("00000000-0000-0000-0000-000000000001", "S-1-5-21-1-2-3-1001", 41001,
            "1.1.1.1", ["93.184.216.34", "2606:4700:4700::1111"]);
        LeasePolicyInput second = Lease("00000000-0000-0000-0000-000000000002", "S-1-5-21-1-2-3-1002", 41002,
            "8.8.8.8", ["142.250.72.14", "2606:4700:4700::1001"]);
        LeasePolicyDocument plan = LeasePolicyCompiler.Compile([first, second]);

        LeasePolicyRule[] firstRules = plan.Rules.Where(rule => rule.LeaseId == first.LeaseId.ToString("N")).ToArray();
        LeasePolicyRule[] secondRules = plan.Rules.Where(rule => rule.LeaseId == second.LeaseId.ToString("N")).ToArray();
        Assert(firstRules.Length > 0 && secondRules.Length > 0, "both leases must have rules");

        string[] firstAllowed = firstRules
            .Where(rule => rule.Action == LeasePolicyAction.Permit)
            .Select(rule => rule.RemoteAddress)
            .OfType<string>()
            .ToArray();
        string[] secondAllowed = secondRules
            .Where(rule => rule.Action == LeasePolicyAction.Permit)
            .Select(rule => rule.RemoteAddress)
            .OfType<string>()
            .ToArray();
        Assert(!firstAllowed.Contains("142.250.72.14", StringComparer.Ordinal), "lease 1 must not permit lease 2's IPv4 target");
        Assert(!firstAllowed.Contains("2606:4700:4700::1001", StringComparer.Ordinal), "lease 1 must not permit lease 2's IPv6 target");
        Assert(!secondAllowed.Contains("93.184.216.34", StringComparer.Ordinal), "lease 2 must not permit lease 1's IPv4 target");
        Assert(!secondAllowed.Contains("2606:4700:4700::1111", StringComparer.Ordinal), "lease 2 must not permit lease 1's IPv6 target");
        Assert(!firstAllowed.Contains("8.8.8.8", StringComparer.Ordinal), "lease 1 must not permit lease 2's resolver");
        Assert(!secondAllowed.Contains("1.1.1.1", StringComparer.Ordinal), "lease 2 must not permit lease 1's resolver");

        Assert(firstRules.Where(rule => rule.Action == LeasePolicyAction.Permit)
            .All(rule => rule.LeaseSid == first.LeaseSid), "every first-lease permit must be bound to its SID");
        Assert(secondRules.Where(rule => rule.Action == LeasePolicyAction.Permit)
            .All(rule => rule.LeaseSid == second.LeaseSid), "every second-lease permit must be bound to its SID");
        Assert(firstRules.Where(rule => rule.Action == LeasePolicyAction.Permit)
            .All(rule => rule.AppIdHex is not null), "every first-lease permit must be bound to an AppID");
        Assert(secondRules.Where(rule => rule.Action == LeasePolicyAction.Permit)
            .All(rule => rule.AppIdHex is not null), "every second-lease permit must be bound to an AppID");
        Assert(firstRules.Where(rule => rule.RuleId.StartsWith("default-deny-principal-", StringComparison.Ordinal))
            .All(rule => rule.LeaseSid == first.LeaseSid && rule.IdentityCondition == "ALE_USER_ID"),
            "lease 1 dynamic principal defaults must be bound only to lease 1's unique user SID");
        Assert(secondRules.Where(rule => rule.RuleId.StartsWith("default-deny-principal-", StringComparison.Ordinal))
            .All(rule => rule.LeaseSid == second.LeaseSid && rule.IdentityCondition == "ALE_USER_ID"),
            "lease 2 dynamic principal defaults must be bound only to lease 2's unique user SID");
    }

    private static void ExplicitDefaultDenyAndExactPermits()
    {
        LeasePolicyInput lease = Lease("10000000-0000-0000-0000-000000000001", "S-1-5-21-10-20-30-1001", 42001,
            "1.1.1.1", ["93.184.216.34", "2606:4700:4700::1111"]);
        LeasePolicyDocument plan = LeasePolicyCompiler.Compile([lease]);

        LeasePolicyRule[] defaults = plan.Rules
            .Where(rule => rule.Lifetime == LeasePolicyLifetime.PersistentDefaultDeny)
            .ToArray();
        Assert(defaults.Length == 4, "one v4/v6 persistent deny is required for each protected browser and worker AppID");
        Assert(defaults.All(rule => rule.Action == LeasePolicyAction.Block), "default rules must block");
        Assert(defaults.Select(rule => rule.AddressFamily).Distinct().Count() == 2, "default deny must cover IPv4 and IPv6");
        LeasePolicyRule[] appDefaults = defaults.Where(rule => rule.AppIdHex is not null).ToArray();
        LeasePolicyRule[] principalDefaults = plan.Rules.Where(rule => rule.RuleId.StartsWith("default-deny-principal-", StringComparison.Ordinal)).ToArray();
        Assert(appDefaults.Length == 4, "per-AppID defaults must remain for browser and worker");
        Assert(appDefaults.All(rule => rule.LeaseSid is null && rule.IdentityCondition == "ALE_APP_ID"
            && rule.RemoteAddress is null && rule.Protocol is null && rule.RemotePort is null),
            "AppID defaults must remain persistent catch-all blocks");
        Assert(principalDefaults.Length == 2, "one principal-wide block is required per address family");
        Assert(principalDefaults.All(rule => rule.LeaseId == lease.LeaseId.ToString("N")
            && rule.LeaseSid == lease.LeaseSid && rule.IdentityCondition == "ALE_USER_ID"
            && rule.Lifetime == LeasePolicyLifetime.LeaseDynamic && rule.Action == LeasePolicyAction.Block
            && rule.RemoteAddress is null && rule.Protocol is null && rule.RemotePort is null),
            "principal-wide defaults must be dynamic catch-all blocks for this lease SID");
        Assert(principalDefaults.Select(rule => rule.AddressFamily).Distinct().Count() == 2,
            "principal-wide defaults must cover IPv4 and IPv6");
        foreach (string appId in new[] { lease.BrowserAppIdHex, lease.WorkerAppIdHex })
        {
            Assert(appDefaults.Where(rule => rule.AppIdHex == appId).Select(rule => rule.AddressFamily).Distinct().Count() == 2,
                "each protected AppID must have both IPv4 and IPv6 default deny");
        }

        const string arbitraryChildAppId = "A1A2A3A4A5A6";
        Assert(!plan.Rules.Any(rule => rule.Action == LeasePolicyAction.Permit
            && rule.LeaseSid == lease.LeaseSid && rule.AppIdHex == arbitraryChildAppId),
            "an arbitrary helper/child AppID must not receive a lease permit");
        Assert(principalDefaults.All(rule => rule.AppIdHex is null && rule.LeaseSid == lease.LeaseSid),
            "the dynamic principal deny must cover the helper/child AppID independently of its executable identity");

        LeasePolicyRule listenerBlock = plan.Rules.Single(rule =>
            rule.LeaseId == lease.LeaseId.ToString("N")
            && rule.Purpose.StartsWith("Block every local process", StringComparison.Ordinal));
        Assert(listenerBlock.Action == LeasePolicyAction.Block && listenerBlock.AppIdHex is null && listenerBlock.LeaseSid is null
            && listenerBlock.RemoteAddress == "127.0.0.1" && listenerBlock.RemotePort == lease.ListenerPort && listenerBlock.Protocol == 6,
            "listener block must deny all other local processes at the exact IPv4 endpoint");

        LeasePolicyRule browser = plan.Rules.Single(rule => rule.RuleId == $"lease-{lease.LeaseId:N}-browser-allow-worker-listener");
        Assert(browser.Action == LeasePolicyAction.Permit && browser.RemoteAddress == "127.0.0.1"
            && browser.RemotePort == lease.ListenerPort && browser.Protocol == 6,
            "browser permit must be exact TCP IPv4 loopback plus this listener port");
        Assert(browser.AppIdHex == lease.BrowserAppIdHex && browser.LeaseSid == lease.LeaseSid,
            "browser permit must bind both trusted executable identity and lease SID");
        Assert(browser.WeightRangeIndex > defaults[0].WeightRangeIndex, "exact permit must outrank the soft default block in the service sublayer");

        LeasePolicyRule[] workerPermits = plan.Rules.Where(rule =>
            rule.LeaseId == lease.LeaseId.ToString("N")
            && rule.Action == LeasePolicyAction.Permit
            && rule.AppIdHex == lease.WorkerAppIdHex).ToArray();
        Assert(workerPermits.Any(rule => rule.RemoteAddress == "1.1.1.1" && rule.RemotePort == 53 && rule.Protocol == 17),
            "worker must have one UDP numeric-resolver permit");
        Assert(workerPermits.Any(rule => rule.RemoteAddress == "1.1.1.1" && rule.RemotePort == 53 && rule.Protocol == 6),
            "worker must have one TCP numeric-resolver permit");
        Assert(workerPermits.Any(rule => rule.RemoteAddress == "93.184.216.34" && rule.RemotePort == 443 && rule.Protocol == 6),
            "worker must have one pinned TCP/443 permit");
        Assert(workerPermits.Any(rule => rule.RemoteAddress == "2606:4700:4700::1111"
            && rule.AddressFamily == LeasePolicyAddressFamily.IPv6 && rule.RemotePort == 443 && rule.Protocol == 6),
            "worker must retain a validated IPv6 pin in its own address family");
        Assert(workerPermits.All(rule => rule.RemotePort is 53 or 443), "worker must not receive an unbounded port permit");
    }

    private static void OutputIsDeterministic()
    {
        LeasePolicyInput first = Lease("20000000-0000-0000-0000-000000000001", "S-1-5-21-11-22-33-1001", 43001,
            "1.1.1.1", ["2606:4700:4700::1111", "93.184.216.34"]);
        LeasePolicyInput second = Lease("20000000-0000-0000-0000-000000000002", "S-1-5-21-11-22-33-1002", 43002,
            "8.8.8.8", ["142.250.72.14"]);
        string forward = JsonSerializer.Serialize(LeasePolicyCompiler.Compile([first, second]));
        string reverse = JsonSerializer.Serialize(LeasePolicyCompiler.Compile([
            second with { PinnedPublicAddresses = ["142.250.72.14"] },
            first with { PinnedPublicAddresses = ["93.184.216.34", "2606:4700:4700::1111"] },
        ]));
        Assert(forward == reverse, "same service inputs in a different enumeration order must compile to identical JSON");
    }

    private static void TypedPlansKeepLifetimesSeparate()
    {
        LeasePolicyInput lease = Lease("21000000-0000-0000-0000-000000000001", "S-1-5-21-11-22-33-1011", 43011,
            "1.1.1.1", ["93.184.216.34"]);
        PersistentAppIdBaselinePlan baseline = LeasePolicyCompiler.CompilePersistentAppIdBaseline([
            new(ProtectedApplicationRole.Browser, lease.BrowserAppIdHex),
            new(ProtectedApplicationRole.Worker, lease.WorkerAppIdHex),
        ]);
        DynamicLeasePlan dynamicLease = LeasePolicyCompiler.CompileDynamicLease(lease);

        Assert(baseline.PlanKind == "persistent-app-id-baseline"
            && baseline.Rules.Count == 4
            && baseline.Rules.All(rule => rule.Lifetime == LeasePolicyLifetime.PersistentDefaultDeny
                && rule.Action == LeasePolicyAction.Block
                && rule.AppIdHex is not null
                && rule.LeaseSid is null
                && rule.LeaseId is null),
            "persistent baseline must contain only AppID-wide v4/v6 blocks");
        Assert(dynamicLease.PlanKind == "dynamic-lease"
            && dynamicLease.LeaseId == lease.LeaseId.ToString("N")
            && dynamicLease.Rules.Count > 0
            && dynamicLease.Rules.All(rule => rule.Lifetime == LeasePolicyLifetime.LeaseDynamic
                && rule.LeaseId == dynamicLease.LeaseId
                && (rule.LeaseSid is null || rule.LeaseSid == dynamicLease.LeaseSid)),
            "lease plan must contain only this lease's dynamic rules");

        Guid provider = Guid.Parse("21000000-0000-0000-0000-000000000002");
        Guid sublayer = Guid.Parse("21000000-0000-0000-0000-000000000003");
        NativeFilterPreview baselinePreview = WfpFilterMaterializer.MaterializeAppIdBaselineForInspection(
            baseline, provider, sublayer);
        NativeFilterPreview leasePreview = WfpFilterMaterializer.MaterializeDynamicLeaseForInspection(
            dynamicLease, provider, sublayer);
        Assert(baselinePreview.Filters.All(filter => filter.Persistent && filter.Action == "FWP_ACTION_BLOCK"),
            "baseline inspection must preserve persistent block flags");
        Assert(leasePreview.Filters.All(filter => !filter.Persistent),
            "lease inspection must not materialize a persistent filter");

        LeasePolicyDocument mixedPreview = LeasePolicyCompiler.Compile([lease]);
        ExpectArgument(() => WfpFilterMaterializer.MaterializeAppIdBaselineForInspection(
            new PersistentAppIdBaselinePlan(
                mixedPreview.SchemaVersion,
                mixedPreview.Rules,
                mixedPreview.UnresolvedValidationItems,
                mixedPreview.SafetyBoundary),
            provider,
            sublayer), "baseline inspection receiving lease rules");
        ExpectArgument(() => WfpFilterMaterializer.MaterializeDynamicLeaseForInspection(
            new DynamicLeasePlan(
                mixedPreview.SchemaVersion,
                lease.LeaseId.ToString("N"),
                lease.PrincipalKind,
                lease.LeaseSid,
                mixedPreview.Rules,
                mixedPreview.UnresolvedValidationItems,
                mixedPreview.SafetyBoundary),
            provider,
            sublayer), "lease inspection receiving persistent baseline rules");

        ExpectArgument(() => LeasePolicyCompiler.CompilePersistentAppIdBaseline([
            new(ProtectedApplicationRole.Browser, lease.BrowserAppIdHex),
        ]), "baseline missing worker identity");
        ExpectArgument(() => LeasePolicyCompiler.CompilePersistentAppIdBaseline([
            new(ProtectedApplicationRole.Browser, lease.BrowserAppIdHex),
            new(ProtectedApplicationRole.Worker, lease.BrowserAppIdHex),
        ]), "AppID reused across protected roles");
    }

    private static void ServiceWideCompositionBindsAppIds()
    {
        LeasePolicyInput lease = Lease("22000000-0000-0000-0000-000000000001", "S-1-5-21-11-22-33-1021", 43021,
            "1.1.1.1", ["93.184.216.34"]);
        ProtectedApplicationInput[] applications =
        [
            new(ProtectedApplicationRole.Browser, lease.BrowserAppIdHex),
            new(ProtectedApplicationRole.Worker, lease.WorkerAppIdHex),
        ];

        ServiceWideLeasePolicyPlan plan = LeasePolicyCompiler.CompileServiceWidePlan(applications, [lease]);
        Assert(plan.PersistentBaseline.Rules.Count == 4 && plan.DynamicLeases.Count == 1
            && plan.DynamicLeases[0].LeaseId == lease.LeaseId.ToString("N"),
            "service-wide composition did not retain its baseline and covered lease");

        ExpectArgument(() => LeasePolicyCompiler.CompileServiceWidePlan(applications,
            [lease with { BrowserAppIdHex = "1112131415" }]), "lease browser AppID missing from browser baseline");
        ExpectArgument(() => LeasePolicyCompiler.CompileServiceWidePlan(applications,
            [lease with { WorkerAppIdHex = "161718191A" }]), "lease worker AppID missing from worker baseline");
    }

    private static void PackageSidConditionIsExplicit()
    {
        LeasePolicyInput lease = Lease("30000000-0000-0000-0000-000000000001", "S-1-15-2-123456-987654-314159-271828-141421-173205-223606", 44001,
            "1.1.1.1", ["93.184.216.34"]) with
        {
            PrincipalKind = LeasePrincipalKind.AppContainerPackageSid,
        };
        LeasePolicyDocument plan = LeasePolicyCompiler.Compile([lease]);
        LeasePolicyRule[] permits = plan.Rules.Where(rule =>
            rule.LeaseId == lease.LeaseId.ToString("N") && rule.Action == LeasePolicyAction.Permit).ToArray();
        Assert(permits.Length > 0, "package SID lease must produce permits");
        Assert(permits.All(rule => rule.IdentityCondition == "ALE_PACKAGE_ID"), "package SID must map to ALE_PACKAGE_ID");
        Assert(permits.All(rule => rule.LeaseSid == lease.LeaseSid), "package SID must remain attached to each permit");
        LeasePolicyRule[] principalDefaults = plan.Rules.Where(rule =>
            rule.RuleId.StartsWith("default-deny-principal-", StringComparison.Ordinal)).ToArray();
        Assert(principalDefaults.Length == 2 && principalDefaults.All(rule =>
            rule.IdentityCondition == "ALE_PACKAGE_ID" && rule.LeaseSid == lease.LeaseSid
            && rule.Lifetime == LeasePolicyLifetime.LeaseDynamic),
            "package SID must also receive dynamic principal-wide v4/v6 catch-all blocks");
    }

    private static void DuplicateAndCrossRoleIdentitiesFailClosed()
    {
        LeasePolicyInput first = Lease("40000000-0000-0000-0000-000000000001", "S-1-5-21-12-23-34-1001", 45001,
            "1.1.1.1", ["93.184.216.34"]);
        LeasePolicyInput second = Lease("40000000-0000-0000-0000-000000000002", "S-1-5-21-12-23-34-1002", 45002,
            "8.8.8.8", ["142.250.72.14"]);
        ExpectArgument(() => LeasePolicyCompiler.Compile([first, first with { ListenerPort = 45003 }]), "duplicate lease id");
        ExpectArgument(() => LeasePolicyCompiler.Compile([first, second with { LeaseSid = first.LeaseSid }]), "duplicate lease SID");
        ExpectArgument(() => LeasePolicyCompiler.Compile([first, second with { ListenerPort = first.ListenerPort }]), "duplicate listener port");
        ExpectArgument(() => LeasePolicyCompiler.Compile([first, second with { BrowserAppIdHex = first.WorkerAppIdHex }]), "cross-role AppID collision");
        ExpectArgument(() => LeasePolicyCompiler.Compile([first with { BrowserAppIdHex = first.WorkerAppIdHex }]), "same browser/worker AppID");
        ExpectArgument(() => LeasePolicyCompiler.Compile([first with { LeaseId = Guid.Empty }]), "empty lease id");
        ExpectArgument(() => LeasePolicyCompiler.Compile([first with { PrincipalKind = (LeasePrincipalKind)99 }]), "unknown principal type");
    }

    private static void InvalidInputsFailClosed()
    {
        LeasePolicyInput baseline = Lease("50000000-0000-0000-0000-000000000001", "S-1-5-21-13-24-35-1001", 46001,
            "1.1.1.1", ["93.184.216.34"]);
        ExpectArgument(() => LeasePolicyCompiler.Compile([baseline with { LeaseSid = "S-1-5-18" }]), "well-known system SID");
        ExpectArgument(() => LeasePolicyCompiler.Compile([baseline with { LeaseSid = "S-1-5-21-13-24-35-500" }]), "built-in administrator RID");
        ExpectArgument(() => LeasePolicyCompiler.Compile([baseline with { LeaseSid = "S-1-5-21-0-24-35-1001" }]), "zero local-account domain component");
        ExpectArgument(() => LeasePolicyCompiler.Compile([baseline with { LeaseSid = "S-1-5-21-13-24-35-1002", PrincipalKind = LeasePrincipalKind.AppContainerPackageSid }]), "principal kind mismatch");
        ExpectArgument(() => LeasePolicyCompiler.Compile([baseline with { LeaseSid = "S-1-15-2-123456-987654", PrincipalKind = LeasePrincipalKind.AppContainerPackageSid }]), "short non-built-in package SID cardinality");
        ExpectArgument(() => LeasePolicyCompiler.Compile([baseline with { BrowserAppIdHex = "" }]), "empty AppID");
        ExpectArgument(() => LeasePolicyCompiler.Compile([baseline with { WorkerAppIdHex = "0" }]), "odd-length AppID");
        ExpectArgument(() => LeasePolicyCompiler.Compile([baseline with { BrowserAppIdHex = "gg" }]), "non-hex AppID");
        ExpectArgument(() => LeasePolicyCompiler.Compile([baseline with { ListenerPort = 0 }]), "zero port");
        ExpectArgument(() => LeasePolicyCompiler.Compile([baseline with { ListenerPort = 65536 }]), "overflow port");
        ExpectArgument(() => LeasePolicyCompiler.Compile([baseline with { NumericResolverAddress = "dns.example" }]), "resolver hostname");
        ExpectArgument(() => LeasePolicyCompiler.Compile([baseline with { NumericResolverAddress = "127.1" }]), "non-canonical IPv4 resolver");
        ExpectArgument(() => LeasePolicyCompiler.Compile([baseline with { NumericResolverAddress = "fe80::1%3" }]), "scoped IPv6 resolver");
        ExpectArgument(() => LeasePolicyCompiler.Compile([baseline with { PinnedPublicAddresses = [] }]), "empty pinned set");
        ExpectArgument(() => LeasePolicyCompiler.Compile([baseline with { PinnedPublicAddresses = Enumerable.Repeat("93.184.216.34", 65).ToArray() }]), "oversized pinned input set");
        ExpectArgument(() => LeasePolicyCompiler.Compile([baseline with { PinnedPublicAddresses = ["not-an-ip"] }]), "hostname in pinned set");
        ExpectArgument(() => LeasePolicyCompiler.Compile([baseline with { PinnedPublicAddresses = ["::ffff:8.8.8.8"] }]), "IPv4-mapped IPv6 target");
        LeasePolicyInput[] tooManyLeases = Enumerable.Range(0, LeasePolicyCompiler.MaxLeasesPerPlan + 1)
            .Select(index => baseline with
            {
                LeaseId = Guid.Parse($"50000000-0000-0000-0000-{index + 2:x12}"),
                LeaseSid = $"S-1-5-21-13-24-35-{1001 + index}",
                ListenerPort = 46002 + index,
            })
            .ToArray();
        ExpectArgument(() => LeasePolicyCompiler.Compile(tooManyLeases), "lease count limit");
    }

    private static void NonPublicDestinationsFailClosed()
    {
        LeasePolicyInput baseline = Lease("60000000-0000-0000-0000-000000000001", "S-1-5-21-14-25-36-1001", 47001,
            "1.1.1.1", ["93.184.216.34"]);
        foreach (string address in new[]
        {
            "10.0.0.1", "100.64.0.1", "100.68.0.1", "127.0.0.1", "169.254.1.1", "172.16.0.1",
            "192.168.1.1", "198.18.0.1", "192.0.2.1", "224.0.0.1", "255.255.255.255",
            "::", "::1", "fc00::1", "fe80::1", "ff02::1", "2001:db8::1", "2002::1", "3fff::1",
        })
        {
            ExpectArgument(() => LeasePolicyCompiler.Compile([baseline with { PinnedPublicAddresses = [address] }]), $"non-public target {address}");
        }
        ExpectArgument(() => LeasePolicyCompiler.Compile([baseline with { NumericResolverAddress = "192.168.1.1" }]), "non-public resolver");
        ExpectArgument(() => LeasePolicyCompiler.Compile([baseline with { NumericResolverAddress = "224.0.0.1" }]), "multicast resolver");
    }

    private static void OutputIsNonDeployable()
    {
        LeasePolicyInput lease = Lease("70000000-0000-0000-0000-000000000001", "S-1-5-21-15-26-37-1001", 48001,
            "1.1.1.1", ["93.184.216.34"]);
        LeasePolicyDocument plan = LeasePolicyCompiler.Compile([lease]);
        Assert(plan.SchemaVersion == LeasePolicyCompiler.SchemaVersion, "schema version must be explicit");
        Assert(plan.PlanKind == "per-lease-semantic-preview", "plan kind must be explicit");
        Assert(plan.Deployability == "not-deployable", "compiler must never label its output deployable");
        Assert(plan.Sublayer.Contains("placeholder", StringComparison.Ordinal), "no WFP sublayer key may be implied");
        Assert(plan.SafetyBoundary.Contains("does not open BFE", StringComparison.Ordinal), "safety boundary must name missing runtime enforcement");
        Assert(plan.UnresolvedValidationItems.Count >= 5, "unverified identity, DNS, runtime and arbitration limits must stay visible");
        Assert(plan.Rules.All(rule => !rule.ClearActionRight), "preview permits remain soft and do not override hard blocks from other providers");
    }

    private static void NativeFilterPreviewMapsCompilerRules()
    {
        const string sid = "S-1-5-21-14-25-36-1001";
        const string packageSid = "S-1-15-2-111111-222222-333333-444444-555555-666666-777777";
        Guid provider = Guid.Parse("81000000-0000-0000-0000-000000000001");
        Guid sublayer = Guid.Parse("81000000-0000-0000-0000-000000000002");
        LeasePolicyDocument userPlan = LeasePolicyCompiler.Compile([
            Lease("81000000-0000-0000-0000-000000000003", sid, 49001, "1.1.1.1", ["93.184.216.34", "2606:4700:4700::1111"])]);
        NativeFilterPreview preview = WfpFilterMaterializer.MaterializeForInspection(userPlan, provider, sublayer);

        Assert(preview.Deployability == "not-deployable" && !preview.PolicyMutated,
            "preview must remain explicitly non-deployable and report no policy mutation");
        Assert(preview.Filters.Count == userPlan.Rules.Count, "every semantic rule must materialize once");
        Assert(preview.Filters.All(filter => filter.ProviderKey == provider && filter.SublayerKey == sublayer),
            "filters must use the explicitly selected provider and sublayer");
        Assert(preview.Filters.All(filter => !filter.ClearActionRight),
            "no generated soft action may clear a hard block from another provider");
        Assert(preview.Filters.Select(filter => filter.FilterKey).Distinct().Count() == preview.Filters.Count,
            "deterministic filter keys must remain unique for this policy");

        NativeFilterSnapshot appDeny = FindSingle(preview.Filters, filter => filter.RuleId.StartsWith("default-deny-browser-", StringComparison.Ordinal)
            && filter.RuleId.EndsWith("-v4", StringComparison.Ordinal), "IPv4 browser default deny");
        Assert(appDeny.Persistent && appDeny.Action == "FWP_ACTION_BLOCK" && appDeny.WeightRangeIndex == 1,
            "application default deny must map to persistent block with the low range index");
        NativeConditionSnapshot appId = FindSingle(appDeny.Conditions, condition => condition.Field == "ALE_APP_ID", "browser AppID condition");
        string expectedAppIdDigest = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(Convert.FromHexString("0102030405")));
        Assert(appId.DataType == "FWP_BYTE_BLOB_TYPE" && appId.Value == $"app-id;bytes=5;sha256={expectedAppIdDigest}",
            "ALE_APP_ID must map to a byte blob without exposing its raw path-bearing bytes");

        NativeFilterSnapshot principalDeny = FindSingle(preview.Filters, filter => filter.RuleId.StartsWith("default-deny-principal-", StringComparison.Ordinal)
            && filter.RuleId.EndsWith("-v4", StringComparison.Ordinal), "IPv4 principal default deny");
        Assert(!principalDeny.Persistent && principalDeny.Action == "FWP_ACTION_BLOCK"
            && principalDeny.WeightRangeIndex == LeasePolicyCompiler.DefaultDenyWeightRangeIndex,
            "lease principal default deny must live only in its dynamic session");
        NativeConditionSnapshot userCondition = FindSingle(principalDeny.Conditions, condition => condition.Field == "ALE_USER_ID", "ALE_USER_ID condition");
        Assert(userCondition.DataType == "FWP_SECURITY_DESCRIPTOR_TYPE"
            && userCondition.Value == $"self-relative;allow=0x1;sid={sid}",
            "ALE_USER_ID must map to a self-relative descriptor with only the match-filter ACE");

        NativeFilterSnapshot browserPermit = FindSingle(preview.Filters, filter => filter.RuleId.EndsWith("browser-allow-worker-listener", StringComparison.Ordinal), "browser listener permit");
        Assert(!browserPermit.Persistent && browserPermit.Action == "FWP_ACTION_PERMIT" && browserPermit.WeightRangeIndex == 15,
            "lease permit must be dynamic with the high range index");
        NativeConditionSnapshot loopbackAddress = FindSingle(browserPermit.Conditions,
            condition => condition.Field == "IP_REMOTE_ADDRESS", "IPv4 listener address condition");
        Assert(loopbackAddress.DataType == "FWP_UINT32" && loopbackAddress.Value == "127.0.0.1"
            && loopbackAddress.RawUInt32Value == 0x7F000001u,
            "127.0.0.1 must map to host-order FWP_UINT32 0x7F000001");
        Assert(browserPermit.Conditions.Any(condition => condition.Field == "IP_REMOTE_PORT" && condition.DataType == "FWP_UINT16" && condition.Value == "49001"),
            "remote port must map to UINT16");
        Assert(browserPermit.Conditions.Any(condition => condition.Field == "IP_PROTOCOL" && condition.DataType == "FWP_UINT8" && condition.Value == "6"),
            "protocol must map to UINT8");

        NativeFilterSnapshot ipv6Permit = FindSingle(preview.Filters, filter => filter.RuleId.Contains("upstream-ipv6", StringComparison.Ordinal), "IPv6 upstream permit");
        Assert(ipv6Permit.Conditions.Any(condition => condition.Field == "IP_REMOTE_ADDRESS"
            && condition.DataType == "FWP_BYTE_ARRAY16_TYPE" && condition.Value == "2606:4700:4700::1111"),
            "IPv6 destination must map to an exact 16-byte address");
        NativeFilterSnapshot ipv4Permit = FindSingle(preview.Filters,
            filter => filter.RuleId.Contains("upstream-ipv4", StringComparison.Ordinal), "IPv4 upstream permit");
        NativeConditionSnapshot publicAddress = FindSingle(ipv4Permit.Conditions,
            condition => condition.Field == "IP_REMOTE_ADDRESS", "IPv4 upstream address condition");
        Assert(publicAddress.DataType == "FWP_UINT32" && publicAddress.Value == "93.184.216.34"
            && publicAddress.RawUInt32Value == 0x5DB8D822u,
            "93.184.216.34 must map to host-order FWP_UINT32 0x5DB8D822");

        LeasePolicyInput packageInput = new(
            Guid.Parse("81000000-0000-0000-0000-000000000004"), LeasePrincipalKind.AppContainerPackageSid,
            packageSid, "1112131415", "161718191A", 49002, "8.8.8.8", ["142.250.72.14"]);
        LeasePolicyDocument packagePlan = LeasePolicyCompiler.Compile([packageInput]);
        NativeFilterPreview packagePreview = WfpFilterMaterializer.MaterializeForInspection(packagePlan, provider, sublayer);
        NativeFilterSnapshot packageDefault = FindSingle(packagePreview.Filters,
            filter => filter.RuleId.StartsWith("default-deny-principal-", StringComparison.Ordinal) && filter.RuleId.EndsWith("-v4", StringComparison.Ordinal),
            "IPv4 package principal default deny");
        Assert(!packageDefault.Persistent && packageDefault.Action == "FWP_ACTION_BLOCK",
            "package principal default deny must live only in its dynamic session");
        NativeConditionSnapshot packageCondition = FindSingle(packageDefault.Conditions,
            condition => condition.Field == "ALE_PACKAGE_ID", "ALE_PACKAGE_ID condition");
        Assert(packageCondition.DataType == "FWP_SID" && packageCondition.Value == packageSid,
            "ALE_PACKAGE_ID must map directly to the binary package SID");
    }

    private static void NativeFilterPreviewRejectsUnsafeInput()
    {
        LeasePolicyDocument plan = LeasePolicyCompiler.Compile([
            Lease("82000000-0000-0000-0000-000000000001", "S-1-5-21-16-27-38-1001", 49101,
                "1.1.1.1", ["93.184.216.34"])]);
        Guid provider = Guid.Parse("82000000-0000-0000-0000-000000000002");
        Guid sublayer = Guid.Parse("82000000-0000-0000-0000-000000000003");

        ExpectArgument(() => WfpFilterMaterializer.MaterializeForInspection(plan, Guid.Empty, sublayer), "empty provider GUID");
        ExpectArgument(() => WfpFilterMaterializer.MaterializeForInspection(plan, provider, Guid.Empty), "empty sublayer GUID");
        ExpectArgument(() => WfpFilterMaterializer.MaterializeForInspection(plan with { Deployability = "deployable" }, provider, sublayer),
            "deployable-looking plan");

        LeasePolicyRule[] ambiguousRules = plan.Rules.ToArray();
        ambiguousRules[0] = ambiguousRules[0] with { IdentityCondition = "unknown-identity" };
        ExpectArgument(() => WfpFilterMaterializer.MaterializeForInspection(plan with { Rules = ambiguousRules }, provider, sublayer),
            "unknown identity condition");

        LeasePolicyRule[] broadRules = plan.Rules.ToArray();
        int listenerIndex = Array.FindIndex(broadRules, rule => rule.RuleId.EndsWith("deny-other-listener-clients", StringComparison.Ordinal));
        broadRules[listenerIndex] = broadRules[listenerIndex] with { RemoteAddress = null, Protocol = null, RemotePort = null };
        ExpectArgument(() => WfpFilterMaterializer.MaterializeForInspection(plan with { Rules = broadRules }, provider, sublayer),
            "endpoint-wide rule missing its restrictive conditions");

        LeasePolicyRule[] nonCanonicalAddressRules = plan.Rules.ToArray();
        nonCanonicalAddressRules[listenerIndex] = nonCanonicalAddressRules[listenerIndex] with { RemoteAddress = "127.1" };
        ExpectArgument(() => WfpFilterMaterializer.MaterializeForInspection(plan with { Rules = nonCanonicalAddressRules }, provider, sublayer),
            "non-canonical IPv4 literal");
    }

    private static void NativeFilterPreviewRejectsForgedPermitSemantics()
    {
        LeasePolicyDocument plan = LeasePolicyCompiler.Compile([
            Lease("83000000-0000-0000-0000-000000000001", "S-1-5-21-16-27-38-1031", 49131,
                "1.1.1.1", ["93.184.216.34"])]);
        Guid provider = Guid.Parse("83000000-0000-0000-0000-000000000002");
        Guid sublayer = Guid.Parse("83000000-0000-0000-0000-000000000003");
        int browserPermitIndex = Array.FindIndex(plan.Rules.ToArray(),
            rule => rule.RuleId.EndsWith("browser-allow-worker-listener", StringComparison.Ordinal));
        int dnsPermitIndex = Array.FindIndex(plan.Rules.ToArray(),
            rule => rule.RuleId.EndsWith("worker-allow-dns-v4-tcp", StringComparison.Ordinal));

        LeasePolicyRule[] privatePermit = plan.Rules.ToArray();
        privatePermit[dnsPermitIndex] = privatePermit[dnsPermitIndex] with { RemoteAddress = "10.0.0.1" };
        ExpectArgument(() => WfpFilterMaterializer.MaterializeForInspection(
            plan with { Rules = privatePermit }, provider, sublayer), "private DNS permit in forged preview");

        LeasePolicyRule[] arbitraryPortPermit = plan.Rules.ToArray();
        arbitraryPortPermit[browserPermitIndex] = arbitraryPortPermit[browserPermitIndex] with { RemotePort = 4444 };
        ExpectArgument(() => WfpFilterMaterializer.MaterializeForInspection(
            plan with { Rules = arbitraryPortPermit }, provider, sublayer), "arbitrary-port browser permit in forged preview");
    }

    private static void BfeProbeEntrypointFailsClosed()
    {
        int exitCode = SandboxBfeSmoke.Run(["--sandbox-bfe-smoke", Guid.NewGuid().ToString("N"), "C:\\sandbox-results\\probe.json"]);
        Assert(exitCode == 2, "the disabled BFE probe entry point did not fail closed");
    }

    private static void SandboxNetworkProbeEntrypointFailsClosed()
    {
        const string guestEnvironment = "WFP_DISPOSABLE_SANDBOX_GUEST";
        const string runTokenEnvironment = "WFP_DISPOSABLE_SANDBOX_RUN_TOKEN";
        string? previousGuest = Environment.GetEnvironmentVariable(guestEnvironment);
        string? previousRunToken = Environment.GetEnvironmentVariable(runTokenEnvironment);
        TextReader previousInput = Console.In;
        TextWriter previousOutput = Console.Out;
        TextWriter previousError = Console.Error;
        using var input = new StringReader("NO\n");
        using var output = new StringWriter(System.Globalization.CultureInfo.InvariantCulture);
        using var error = new StringWriter(System.Globalization.CultureInfo.InvariantCulture);
        string token = Guid.NewGuid().ToString("N");

        try
        {
            Environment.SetEnvironmentVariable(guestEnvironment, "1");
            Environment.SetEnvironmentVariable(runTokenEnvironment, token);
            Console.SetIn(input);
            Console.SetOut(output);
            Console.SetError(error);

            int commandExitCode = Main(["--sandbox-probe-client", token, "tcp", "127.0.0.1", "1"]);
            int helperExitCode = SandboxProbeClient.Run(["--sandbox-probe-client", token, "tcp", "127.0.0.1", "1"]);
            Assert(commandExitCode == 2, "the disabled Sandbox network probe command did not fail closed");
            Assert(helperExitCode == 2, "the disabled Sandbox network probe helper did not fail closed");
            Assert(output.ToString().Length == 0,
                "the disabled Sandbox network probe emitted a ready message before refusing to run");
            Assert(error.ToString().Contains("disabled", StringComparison.OrdinalIgnoreCase),
                "the disabled Sandbox network probe did not explain the refusal");
        }
        finally
        {
            Console.SetIn(previousInput);
            Console.SetOut(previousOutput);
            Console.SetError(previousError);
            Environment.SetEnvironmentVariable(guestEnvironment, previousGuest);
            Environment.SetEnvironmentVariable(runTokenEnvironment, previousRunToken);
        }
    }

    private static LeasePolicyInput Lease(string id, string sid, int port, string resolver, IReadOnlyCollection<string> pinned) => new(
        Guid.Parse(id),
        LeasePrincipalKind.UserSid,
        sid,
        BrowserAppIdHex: "0102030405",
        WorkerAppIdHex: "060708090A",
        ListenerPort: port,
        NumericResolverAddress: resolver,
        PinnedPublicAddresses: pinned);

    private static void ExpectArgument(Action action, string description)
    {
        try
        {
            action();
        }
        catch (ArgumentException)
        {
            return;
        }
        throw new InvalidOperationException($"Expected invalid input to be rejected: {description}.");
    }

    private static T FindSingle<T>(IEnumerable<T> values, Func<T, bool> predicate, string description)
    {
        T[] matches = values.Where(predicate).ToArray();
        if (matches.Length != 1)
            throw new InvalidOperationException($"Expected one {description}; found {matches.Length}.");
        return matches[0];
    }

    private static void Assert(bool condition, string message)
    {
        if (!condition)
        {
            throw new InvalidOperationException(message);
        }
    }
}
