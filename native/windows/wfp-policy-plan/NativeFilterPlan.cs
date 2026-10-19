using Win32 = Windows.Win32;

namespace WfpPolicyPlan;

internal sealed record NativeFilterPlanDocument(
    string SchemaVersion,
    string PlanKind,
    string Deployability,
    string BrowserIdentitySource,
    string SublayerKey,
    string SublayerKeyStatus,
    string LeaseEndpoint,
    IReadOnlyList<NativeFilterRule> Rules,
    IReadOnlyList<string> UnresolvedValidationItems,
    string SafetyBoundary);

internal sealed record NativeFilterRule(
    string Id,
    string FilterKey,
    string FilterKeyStatus,
    string Layer,
    Guid LayerKey,
    string Action,
    uint ActionValue,
    uint Flags,
    bool Persistent,
    bool ClearActionRight,
    byte Weight,
    string WeightType,
    string WeightMeaning,
    IReadOnlyList<NativeFilterCondition> Conditions);

internal sealed record NativeFilterCondition(
    string Field,
    Guid FieldKey,
    string Match,
    uint MatchValue,
    string ValueType,
    string Value,
    string ValueSource,
    string Representation);

internal static class NativeFilterPlan
{
    private const uint FwpMatchEqual = 0;
    private const uint FwpMatchNotEqual = 10;
    private const uint FwpActionBlock = 0x1001;
    private const uint FwpActionPermit = 0x1002;
    private const uint FwpmFilterFlagPersistent = 0x00000001;
    private const uint FwpmFilterFlagClearActionRight = 0x00000008;

    private const uint LoopbackAddressHostOrder = 0x7F000001;
    private const ushort ExampleLeasePort = 43127;

    public static NativeFilterPlanDocument CreateAndValidate()
    {
        var appId = Condition(
            "FWPM_CONDITION_ALE_APP_ID",
            Win32.PInvoke.FWPM_CONDITION_ALE_APP_ID,
            "FWP_MATCH_EQUAL",
            FwpMatchEqual,
            "FWP_BYTE_BLOB_TYPE",
            "not-serialized",
            "FwpmGetAppIdFromFileName0(service-protected-browser-path)",
            "Runtime app ID must be derived by the service from its protected executable path.");

        var protocolTcp = Condition(
            "FWPM_CONDITION_IP_PROTOCOL",
            Win32.PInvoke.FWPM_CONDITION_IP_PROTOCOL,
            "FWP_MATCH_EQUAL",
            FwpMatchEqual,
            "FWP_UINT8",
            "6",
            "constant",
            "TCP protocol number.");
        var protocolNotTcp = protocolTcp with
        {
            Match = "FWP_MATCH_NOT_EQUAL",
            MatchValue = FwpMatchNotEqual,
        };

        var loopbackAddress = Condition(
            "FWPM_CONDITION_IP_REMOTE_ADDRESS",
            Win32.PInvoke.FWPM_CONDITION_IP_REMOTE_ADDRESS,
            "FWP_MATCH_EQUAL",
            FwpMatchEqual,
            "FWP_UINT32",
            $"{LoopbackAddressHostOrder} (0x{LoopbackAddressHostOrder:X8})",
            "constant",
            "127.0.0.1 represented as host-order FWP_UINT32.");
        var nonLoopbackAddress = loopbackAddress with
        {
            Match = "FWP_MATCH_NOT_EQUAL",
            MatchValue = FwpMatchNotEqual,
        };

        var leasePort = Condition(
            "FWPM_CONDITION_IP_REMOTE_PORT",
            Win32.PInvoke.FWPM_CONDITION_IP_REMOTE_PORT,
            "FWP_MATCH_EQUAL",
            FwpMatchEqual,
            "FWP_UINT16",
            ExampleLeasePort.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "illustrative-only",
            "Example port only; a service must select and retain its actual listener port.");
        var unexpectedPort = leasePort with
        {
            Match = "FWP_MATCH_NOT_EQUAL",
            MatchValue = FwpMatchNotEqual,
        };

        var appIdOnly = new[] { appId };
        var rules = new[]
        {
            Rule(
                "allow-exact-broker-endpoint",
                WfpIdentifiers.AleAuthConnectV4,
                "FWPM_LAYER_ALE_AUTH_CONNECT_V4",
                "FWP_ACTION_PERMIT",
                FwpActionPermit,
                persistent: false,
                clearActionRight: false,
                weight: 15,
                [appId, protocolTcp, loopbackAddress, leasePort]),
            Rule(
                "deny-ipv4-non-tcp",
                WfpIdentifiers.AleAuthConnectV4,
                "FWPM_LAYER_ALE_AUTH_CONNECT_V4",
                "FWP_ACTION_BLOCK",
                FwpActionBlock,
                persistent: true,
                clearActionRight: false,
                weight: 1,
                [appId, protocolNotTcp]),
            Rule(
                "deny-ipv4-non-loopback-address",
                WfpIdentifiers.AleAuthConnectV4,
                "FWPM_LAYER_ALE_AUTH_CONNECT_V4",
                "FWP_ACTION_BLOCK",
                FwpActionBlock,
                persistent: true,
                clearActionRight: false,
                weight: 1,
                [appId, nonLoopbackAddress]),
            Rule(
                "deny-ipv4-non-lease-port",
                WfpIdentifiers.AleAuthConnectV4,
                "FWPM_LAYER_ALE_AUTH_CONNECT_V4",
                "FWP_ACTION_BLOCK",
                FwpActionBlock,
                persistent: true,
                clearActionRight: false,
                weight: 1,
                [appId, unexpectedPort]),
            Rule(
                "deny-all-ipv6-destinations",
                WfpIdentifiers.AleAuthConnectV6,
                "FWPM_LAYER_ALE_AUTH_CONNECT_V6",
                "FWP_ACTION_BLOCK",
                FwpActionBlock,
                persistent: true,
                clearActionRight: false,
                weight: 1,
                appIdOnly),
        };

        var document = new NativeFilterPlanDocument(
            SchemaVersion: "1",
            PlanKind: "native-filter-construction-preview",
            Deployability: "not-deployable",
            BrowserIdentitySource: "FWPM_CONDITION_ALE_APP_ID must be populated from FwpmGetAppIdFromFileName0 using an administrator-protected browser path.",
            SublayerKey: Guid.Empty.ToString("D"),
            SublayerKeyStatus: "placeholder; no provider or sublayer is installed",
            LeaseEndpoint: $"illustrative TCP 127.0.0.1:{ExampleLeasePort}",
            Rules: rules,
            UnresolvedValidationItems:
            [
                "The exact permit is a dynamic soft permit with higher filter weight than the three persistent IPv4 mismatch blocks in the same project sublayer; external-provider arbitration still requires runtime validation.",
                "The current Sandbox confirmed the host-order 127.0.0.1 FWP_UINT32 condition for PowerShell on this Windows build; the protected Chromium identity and other servicing levels remain unverified.",
                "No native FWPM_FILTER0 instance is allocated or submitted. Filter and sublayer keys, provider ownership, sublayer weight, transaction behavior, and service ACLs are placeholders.",
                "ALE loopback behavior, other providers' hard blocks, IPv6, UDP/raw-socket coverage, process-tree identity, service/BFE failure, rollback, and established-connection revocation remain unverified.",
            ],
            SafetyBoundary: "This command emits a construction preview only. It does not open BFE, create a WFP session, install or delete filters, configure a service, or establish that isolation is active.");

        Validate(document);
        return document;
    }

    private static NativeFilterCondition Condition(
        string field,
        Guid fieldKey,
        string match,
        uint matchValue,
        string valueType,
        string value,
        string valueSource,
        string representation) => new(field, fieldKey, match, matchValue, valueType, value, valueSource, representation);

    private static NativeFilterRule Rule(
        string id,
        Guid layerKey,
        string layer,
        string action,
        uint actionValue,
        bool persistent,
        bool clearActionRight,
        byte weight,
        IReadOnlyList<NativeFilterCondition> conditions)
    {
        uint flags = (persistent ? FwpmFilterFlagPersistent : 0) |
                     (clearActionRight ? FwpmFilterFlagClearActionRight : 0);
        return new NativeFilterRule(
            Id: id,
            FilterKey: Guid.Empty.ToString("D"),
            FilterKeyStatus: "placeholder; a service must assign and own a unique stable key",
            Layer: layer,
            LayerKey: layerKey,
            Action: action,
            ActionValue: actionValue,
            Flags: flags,
            Persistent: persistent,
            ClearActionRight: clearActionRight,
            Weight: weight,
            WeightType: "FWP_UINT8",
            WeightMeaning: "filter-weight range index from 0 through 15; higher range has higher priority",
            Conditions: conditions);
    }

    private static void Validate(NativeFilterPlanDocument document)
    {
        if (document.SchemaVersion != "1" ||
            document.PlanKind != "native-filter-construction-preview" ||
            document.Deployability != "not-deployable" ||
            document.Rules.Count != 5 ||
            document.Rules.Select(rule => rule.Id).Distinct(StringComparer.Ordinal).Count() != 5)
        {
            throw new InvalidOperationException("The filter preview must remain non-deployable and contain five uniquely named rules.");
        }

        if (document.Rules.Any(rule => rule.FilterKey != Guid.Empty.ToString("D")) ||
            document.SublayerKey != Guid.Empty.ToString("D"))
        {
            throw new InvalidOperationException("The preview must not contain usable WFP object keys.");
        }

        foreach (var rule in document.Rules)
        {
            if (rule.Conditions.Count == 0 ||
                rule.Conditions.All(condition => condition.Field != "FWPM_CONDITION_ALE_APP_ID") ||
                rule.Conditions.Any(condition => condition.FieldKey == Guid.Empty))
            {
                throw new InvalidOperationException("Every filter must be scoped to a generated browser AppID condition.");
            }
        }

        var appId = ExpectedCondition(
            "FWPM_CONDITION_ALE_APP_ID",
            Win32.PInvoke.FWPM_CONDITION_ALE_APP_ID,
            "FWP_MATCH_EQUAL",
            FwpMatchEqual,
            "FWP_BYTE_BLOB_TYPE",
            "not-serialized",
            "FwpmGetAppIdFromFileName0(service-protected-browser-path)",
            "Runtime app ID must be derived by the service from its protected executable path.");
        var expectedRules = new[]
        {
            ExpectedRule(
                "allow-exact-broker-endpoint",
                WfpIdentifiers.AleAuthConnectV4,
                "FWPM_LAYER_ALE_AUTH_CONNECT_V4",
                FwpActionPermit,
                persistent: false,
                weight: 15,
                appId,
                ExpectedCondition("FWPM_CONDITION_IP_PROTOCOL", Win32.PInvoke.FWPM_CONDITION_IP_PROTOCOL, "FWP_MATCH_EQUAL", FwpMatchEqual, "FWP_UINT8", "6", "constant", "TCP protocol number."),
                ExpectedCondition("FWPM_CONDITION_IP_REMOTE_ADDRESS", Win32.PInvoke.FWPM_CONDITION_IP_REMOTE_ADDRESS, "FWP_MATCH_EQUAL", FwpMatchEqual, "FWP_UINT32", $"{LoopbackAddressHostOrder} (0x{LoopbackAddressHostOrder:X8})", "constant", "127.0.0.1 represented as host-order FWP_UINT32."),
                ExpectedCondition("FWPM_CONDITION_IP_REMOTE_PORT", Win32.PInvoke.FWPM_CONDITION_IP_REMOTE_PORT, "FWP_MATCH_EQUAL", FwpMatchEqual, "FWP_UINT16", ExampleLeasePort.ToString(System.Globalization.CultureInfo.InvariantCulture), "illustrative-only", "Example port only; a service must select and retain its actual listener port.")),
            ExpectedRule(
                "deny-ipv4-non-tcp",
                WfpIdentifiers.AleAuthConnectV4,
                "FWPM_LAYER_ALE_AUTH_CONNECT_V4",
                FwpActionBlock,
                persistent: true,
                weight: 1,
                appId,
                ExpectedCondition("FWPM_CONDITION_IP_PROTOCOL", Win32.PInvoke.FWPM_CONDITION_IP_PROTOCOL, "FWP_MATCH_NOT_EQUAL", FwpMatchNotEqual, "FWP_UINT8", "6", "constant", "TCP protocol number.")),
            ExpectedRule(
                "deny-ipv4-non-loopback-address",
                WfpIdentifiers.AleAuthConnectV4,
                "FWPM_LAYER_ALE_AUTH_CONNECT_V4",
                FwpActionBlock,
                persistent: true,
                weight: 1,
                appId,
                ExpectedCondition("FWPM_CONDITION_IP_REMOTE_ADDRESS", Win32.PInvoke.FWPM_CONDITION_IP_REMOTE_ADDRESS, "FWP_MATCH_NOT_EQUAL", FwpMatchNotEqual, "FWP_UINT32", $"{LoopbackAddressHostOrder} (0x{LoopbackAddressHostOrder:X8})", "constant", "127.0.0.1 represented as host-order FWP_UINT32.")),
            ExpectedRule(
                "deny-ipv4-non-lease-port",
                WfpIdentifiers.AleAuthConnectV4,
                "FWPM_LAYER_ALE_AUTH_CONNECT_V4",
                FwpActionBlock,
                persistent: true,
                weight: 1,
                appId,
                ExpectedCondition("FWPM_CONDITION_IP_REMOTE_PORT", Win32.PInvoke.FWPM_CONDITION_IP_REMOTE_PORT, "FWP_MATCH_NOT_EQUAL", FwpMatchNotEqual, "FWP_UINT16", ExampleLeasePort.ToString(System.Globalization.CultureInfo.InvariantCulture), "illustrative-only", "Example port only; a service must select and retain its actual listener port.")),
            ExpectedRule(
                "deny-all-ipv6-destinations",
                WfpIdentifiers.AleAuthConnectV6,
                "FWPM_LAYER_ALE_AUTH_CONNECT_V6",
                FwpActionBlock,
                persistent: true,
                weight: 1,
                appId),
        };

        if (document.Rules.Where((rule, index) => !RuleMatches(rule, expectedRules[index])).Any())
        {
            throw new InvalidOperationException("A WFP rule does not match its exact expected layer, action, lifetime, weight, or condition values.");
        }
    }

    private static NativeFilterRule ExpectedRule(
        string id,
        Guid layerKey,
        string layer,
        uint actionValue,
        bool persistent,
        byte weight,
        params NativeFilterCondition[] conditions)
    {
        var flags = persistent ? FwpmFilterFlagPersistent : 0;
        return new NativeFilterRule(
            Id: id,
            FilterKey: Guid.Empty.ToString("D"),
            FilterKeyStatus: "placeholder; a service must assign and own a unique stable key",
            Layer: layer,
            LayerKey: layerKey,
            Action: actionValue == FwpActionPermit ? "FWP_ACTION_PERMIT" : "FWP_ACTION_BLOCK",
            ActionValue: actionValue,
            Flags: flags,
            Persistent: persistent,
            ClearActionRight: false,
            Weight: weight,
            WeightType: "FWP_UINT8",
            WeightMeaning: "filter-weight range index from 0 through 15; higher range has higher priority",
            Conditions: conditions);
    }

    private static NativeFilterCondition ExpectedCondition(
        string field,
        Guid fieldKey,
        string match,
        uint matchValue,
        string valueType,
        string value,
        string valueSource,
        string representation) =>
        new(field, fieldKey, match, matchValue, valueType, value, valueSource, representation);

    private static bool RuleMatches(NativeFilterRule actual, NativeFilterRule expected) =>
        actual.Id == expected.Id &&
        actual.FilterKey == expected.FilterKey &&
        actual.FilterKeyStatus == expected.FilterKeyStatus &&
        actual.Layer == expected.Layer &&
        actual.LayerKey == expected.LayerKey &&
        actual.Action == expected.Action &&
        actual.ActionValue == expected.ActionValue &&
        actual.Flags == expected.Flags &&
        actual.Persistent == expected.Persistent &&
        actual.ClearActionRight == expected.ClearActionRight &&
        actual.Weight == expected.Weight &&
        actual.WeightType == expected.WeightType &&
        actual.WeightMeaning == expected.WeightMeaning &&
        actual.Conditions.SequenceEqual(expected.Conditions);
}
