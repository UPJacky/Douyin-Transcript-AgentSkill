using System.Text.Json.Serialization;

namespace WfpPolicyPlan;

internal sealed record PolicyPlan(
    string SchemaVersion,
    string PlanKind,
    string Deployability,
    string IdentitySource,
    BrowserIdentity Identity,
    BrokerEndpoint Endpoint,
    IReadOnlyList<SemanticRule> IntendedRules,
    IReadOnlyList<string> UnresolvedValidationItems,
    string SafetyBoundary)
{
    public static PolicyPlan CreateAndValidate()
    {
        var plan = new PolicyPlan(
            SchemaVersion: "1",
            PlanKind: "semantic-preview-only",
            Deployability: "not-deployable",
            IdentitySource: "A future broker must derive the application ID from its own protected browser path; caller-supplied paths are not trusted.",
            Identity: new BrowserIdentity(
                ExecutablePath: @"C:\Program Files\DouyinTranscript\Browser\chrome.exe",
                PathProtection: "illustrative-only; administrator-protected ACL has not been installed or verified",
                ContentPin: "not-provided"),
            Endpoint: new BrokerEndpoint(
                Address: "127.0.0.1",
                Port: 43127,
                Transport: "TCP",
                AddressFamily: "IPv4",
                Lifetime: "illustrative lease endpoint; a service must choose and own the actual port"),
            IntendedRules:
            [
                new SemanticRule(
                    Id: "allow-exact-broker-endpoint",
                    Effect: "allow-only-this-destination",
                    FilterOrder: "highest weight in the dedicated sublayer; soft permit",
                    Layer: "ALE_AUTH_CONNECT_V4",
                    LayerKey: WfpIdentifiers.AleAuthConnectV4,
                    Conditions:
                    [
                        new RuleCondition("ALE_APP_ID", WfpIdentifiers.AleAppId, "equals service-derived protected browser identity"),
                        new RuleCondition("IP_PROTOCOL", WfpIdentifiers.IpProtocol, "equals TCP (6)"),
                        new RuleCondition("IP_REMOTE_ADDRESS", WfpIdentifiers.IpRemoteAddress, "equals 127.0.0.1/32"),
                        new RuleCondition("IP_REMOTE_PORT", WfpIdentifiers.IpRemotePort, "equals the service-owned lease port"),
                    ],
                    Lifetime: "only while the authenticated broker lease and listener are active"),
                new SemanticRule(
                    Id: "deny-ipv4-non-tcp",
                    Effect: "block-if-condition-matches",
                    FilterOrder: "lower weight than the exact endpoint permit in the same dedicated sublayer; hard block",
                    Layer: "ALE_AUTH_CONNECT_V4",
                    LayerKey: WfpIdentifiers.AleAuthConnectV4,
                    Conditions:
                    [
                        new RuleCondition("ALE_APP_ID", WfpIdentifiers.AleAppId, "equals service-derived protected browser identity"),
                        new RuleCondition("IP_PROTOCOL", WfpIdentifiers.IpProtocol, "does not equal TCP (6)"),
                    ],
                    Lifetime: "persistent app-wide default-deny filter; must be present before the browser starts"),
                new SemanticRule(
                    Id: "deny-ipv4-address-outside-loopback-proxy",
                    Effect: "block-if-condition-matches",
                    FilterOrder: "lower weight than the exact endpoint permit in the same dedicated sublayer; hard block",
                    Layer: "ALE_AUTH_CONNECT_V4",
                    LayerKey: WfpIdentifiers.AleAuthConnectV4,
                    Conditions:
                    [
                        new RuleCondition("ALE_APP_ID", WfpIdentifiers.AleAppId, "equals service-derived protected browser identity"),
                        new RuleCondition("IP_REMOTE_ADDRESS", WfpIdentifiers.IpRemoteAddress, "does not equal 127.0.0.1/32"),
                    ],
                    Lifetime: "persistent app-wide default-deny filter; must be present before the browser starts"),
                new SemanticRule(
                    Id: "deny-ipv4-port-outside-active-lease",
                    Effect: "block-if-condition-matches",
                    FilterOrder: "lower weight than the exact endpoint permit in the same dedicated sublayer; hard block",
                    Layer: "ALE_AUTH_CONNECT_V4",
                    LayerKey: WfpIdentifiers.AleAuthConnectV4,
                    Conditions:
                    [
                        new RuleCondition("ALE_APP_ID", WfpIdentifiers.AleAppId, "equals service-derived protected browser identity"),
                        new RuleCondition("IP_REMOTE_PORT", WfpIdentifiers.IpRemotePort, "does not equal the service-owned lease port"),
                    ],
                    Lifetime: "persistent app-wide default-deny filter; must be present before the browser starts"),
                new SemanticRule(
                    Id: "deny-all-ipv6-destinations",
                    Effect: "block",
                    FilterOrder: "default hard block in the dedicated sublayer",
                    Layer: "ALE_AUTH_CONNECT_V6",
                    LayerKey: WfpIdentifiers.AleAuthConnectV6,
                    Conditions:
                    [
                        new RuleCondition("ALE_APP_ID", WfpIdentifiers.AleAppId, "equals service-derived protected browser identity"),
                    ],
                    Lifetime: "must be present before the browser starts"),
            ],
            UnresolvedValidationItems:
            [
                "The IPv4 exception is decomposed into three single-mismatch filters because conditions within one WFP filter are conjunctive; native filter synthesis and action-right behavior remain unimplemented.",
                "The IPv4 address mismatch requires a sortable UINT32 representation for FWP_MATCH_NOT_EQUAL; address byte order and supported-layer acceptance are not yet verified against the Windows SDK/runtime.",
                "ALE loopback classification and the exact behavior of this endpoint on supported Windows builds have not been tested.",
                "Raw sockets, bind/resource-assignment paths, broker/IPC authentication, socket duplication, service lifecycle, and rollback are outside this semantic plan.",
                "The example browser path and endpoint are placeholders; no protected executable identity or service-owned listener was verified.",
                "Other providers' blocks must remain effective; conflicting hard permits and cross-sublayer action-right arbitration are unresolved.",
            ],
            SafetyBoundary: "This is an intended-policy description only. It is not a concrete FWPM_FILTER0 plan, does not query or mutate BFE/WFP, and cannot establish that isolation is active.");

        plan.Validate();
        return plan;
    }

    private void Validate()
    {
        if (SchemaVersion != "1" || PlanKind != "semantic-preview-only" || Deployability != "not-deployable")
        {
            throw new InvalidOperationException("The preview must remain explicitly non-deployable.");
        }

        if (!Identity.ExecutablePath.StartsWith(@"C:\Program Files\", StringComparison.OrdinalIgnoreCase) ||
            Identity.PathProtection == "verified" || Identity.ContentPin != "not-provided")
        {
            throw new InvalidOperationException("The illustrative browser identity must not be reported as protected or verified.");
        }

        if (Endpoint.Address != "127.0.0.1" || Endpoint.AddressFamily != "IPv4" || Endpoint.Transport != "TCP" ||
            Endpoint.Port != 43127 || !Endpoint.Lifetime.Contains("illustrative", StringComparison.Ordinal))
        {
            throw new InvalidOperationException("The preview endpoint must remain a valid, explicitly illustrative IPv4 TCP loopback endpoint.");
        }

        if (IntendedRules.Count != 5 ||
            IntendedRules[0].Id != "allow-exact-broker-endpoint" ||
            IntendedRules[1].Id != "deny-ipv4-non-tcp" ||
            IntendedRules[2].Id != "deny-ipv4-address-outside-loopback-proxy" ||
            IntendedRules[3].Id != "deny-ipv4-port-outside-active-lease" ||
            IntendedRules[4].Id != "deny-all-ipv6-destinations")
        {
            throw new InvalidOperationException("The semantic policy must include the exact permit, all three IPv4 mismatch blocks, and IPv6 default deny.");
        }

        var scopedAllow = IntendedRules[0];
        if (scopedAllow.Effect != "allow-only-this-destination" ||
            scopedAllow.FilterOrder != "highest weight in the dedicated sublayer; soft permit" ||
            scopedAllow.Layer != "ALE_AUTH_CONNECT_V4" ||
            scopedAllow.LayerKey != WfpIdentifiers.AleAuthConnectV4 ||
            !HasExactConditions(scopedAllow.Conditions,
            [
                ("ALE_APP_ID", WfpIdentifiers.AleAppId, "equals service-derived protected browser identity"),
                ("IP_PROTOCOL", WfpIdentifiers.IpProtocol, "equals TCP (6)"),
                ("IP_REMOTE_ADDRESS", WfpIdentifiers.IpRemoteAddress, "equals 127.0.0.1/32"),
                ("IP_REMOTE_PORT", WfpIdentifiers.IpRemotePort, "equals the service-owned lease port"),
            ]))
        {
            throw new InvalidOperationException("The endpoint allow description must stay app-, protocol-, address-, and port-scoped.");
        }

        var ipv4Block = IntendedRules[1];
        if (ipv4Block.Effect != "block-if-condition-matches" ||
            ipv4Block.FilterOrder != "lower weight than the exact endpoint permit in the same dedicated sublayer; hard block" ||
            ipv4Block.Layer != "ALE_AUTH_CONNECT_V4" ||
            ipv4Block.LayerKey != WfpIdentifiers.AleAuthConnectV4 ||
            !HasExactConditions(ipv4Block.Conditions,
            [
                ("ALE_APP_ID", WfpIdentifiers.AleAppId, "equals service-derived protected browser identity"),
                ("IP_PROTOCOL", WfpIdentifiers.IpProtocol, "does not equal TCP (6)"),
            ]))
        {
            throw new InvalidOperationException("The first IPv4 mismatch block must reject non-TCP traffic for the browser.");
        }

        var ipv4AddressBlock = IntendedRules[2];
        if (ipv4AddressBlock.Effect != "block-if-condition-matches" ||
            ipv4AddressBlock.FilterOrder != ipv4Block.FilterOrder ||
            ipv4AddressBlock.Layer != "ALE_AUTH_CONNECT_V4" ||
            ipv4AddressBlock.LayerKey != WfpIdentifiers.AleAuthConnectV4 ||
            !HasExactConditions(ipv4AddressBlock.Conditions,
            [
                ("ALE_APP_ID", WfpIdentifiers.AleAppId, "equals service-derived protected browser identity"),
                ("IP_REMOTE_ADDRESS", WfpIdentifiers.IpRemoteAddress, "does not equal 127.0.0.1/32"),
            ]))
        {
            throw new InvalidOperationException("The second IPv4 mismatch block must reject destinations outside the exact loopback address.");
        }

        var ipv4PortBlock = IntendedRules[3];
        if (ipv4PortBlock.Effect != "block-if-condition-matches" ||
            ipv4PortBlock.FilterOrder != ipv4Block.FilterOrder ||
            ipv4PortBlock.Layer != "ALE_AUTH_CONNECT_V4" ||
            ipv4PortBlock.LayerKey != WfpIdentifiers.AleAuthConnectV4 ||
            !HasExactConditions(ipv4PortBlock.Conditions,
            [
                ("ALE_APP_ID", WfpIdentifiers.AleAppId, "equals service-derived protected browser identity"),
                ("IP_REMOTE_PORT", WfpIdentifiers.IpRemotePort, "does not equal the service-owned lease port"),
            ]))
        {
            throw new InvalidOperationException("The third IPv4 mismatch block must reject ports outside the current lease endpoint.");
        }

        var ipv6Block = IntendedRules[4];
        if (ipv6Block.Effect != "block" || ipv6Block.Layer != "ALE_AUTH_CONNECT_V6" ||
            ipv6Block.FilterOrder != "default hard block in the dedicated sublayer" ||
            ipv6Block.LayerKey != WfpIdentifiers.AleAuthConnectV6 ||
            !HasExactConditions(ipv6Block.Conditions,
            [
                ("ALE_APP_ID", WfpIdentifiers.AleAppId, "equals service-derived protected browser identity"),
            ]))
        {
            throw new InvalidOperationException("The IPv6 deny description must remain scoped to the browser identity.");
        }

        if (UnresolvedValidationItems.Count < 5 ||
            !UnresolvedValidationItems.Any(item => item.Contains("conjunctive", StringComparison.Ordinal)) ||
            !UnresolvedValidationItems.Any(item => item.Contains("Raw sockets", StringComparison.Ordinal)) ||
            !UnresolvedValidationItems.Any(item => item.Contains("Other providers'", StringComparison.Ordinal)))
        {
            throw new InvalidOperationException("Critical unresolved WFP and isolation limitations must remain visible.");
        }

        if (!SafetyBoundary.Contains("does not query or mutate BFE/WFP", StringComparison.Ordinal))
        {
            throw new InvalidOperationException("The non-mutating safety boundary must remain explicit.");
        }
    }

    private static bool HasExactConditions(
        IReadOnlyList<RuleCondition> actual,
        IReadOnlyList<(string Name, Guid? FieldKey, string Predicate)> expected)
    {
        return actual.Count == expected.Count && actual.Zip(expected).All(pair =>
            pair.First.Name == pair.Second.Name &&
            pair.First.FieldKey == pair.Second.FieldKey &&
            pair.First.Predicate == pair.Second.Predicate);
    }
}

internal sealed record BrowserIdentity(string ExecutablePath, string PathProtection, string ContentPin);

internal sealed record BrokerEndpoint(string Address, int Port, string Transport, string AddressFamily, string Lifetime);

internal sealed record SemanticRule(
    string Id,
    string Effect,
    string FilterOrder,
    string Layer,
    Guid LayerKey,
    IReadOnlyList<RuleCondition> Conditions,
    string Lifetime);

internal sealed record RuleCondition(string Name, Guid? FieldKey, string Predicate);

internal static class WfpIdentifiers
{
    public static readonly Guid AleAuthConnectV4 = new("c38d57d1-05a7-4c33-904f-7fbceee60e82");
    public static readonly Guid AleAuthConnectV6 = new("4a72393b-319f-44bc-84c3-ba54dcb3b6b4");
    public static readonly Guid AleAppId = Windows.Win32.PInvoke.FWPM_CONDITION_ALE_APP_ID;
    public static readonly Guid AleUserId = Windows.Win32.PInvoke.FWPM_CONDITION_ALE_USER_ID;
    public static readonly Guid AlePackageId = Windows.Win32.PInvoke.FWPM_CONDITION_ALE_PACKAGE_ID;
    public static readonly Guid IpProtocol = Windows.Win32.PInvoke.FWPM_CONDITION_IP_PROTOCOL;
    public static readonly Guid IpRemoteAddress = Windows.Win32.PInvoke.FWPM_CONDITION_IP_REMOTE_ADDRESS;
    public static readonly Guid IpRemotePort = Windows.Win32.PInvoke.FWPM_CONDITION_IP_REMOTE_PORT;
}
