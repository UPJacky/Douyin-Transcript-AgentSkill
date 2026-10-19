using System.Security.Cryptography;
using System.Text;
using WfpPolicy.NativeReadback;
using WfpPolicyPlan;

namespace WfpPolicy.Runtime;

/// <summary>
/// One copied, complete view of every provider and filter in the shared
/// baseline sublayer, with ACL evidence for every returned object. This DTO
/// defines the offline contract only; this source slice has no native producer.
/// </summary>
internal sealed record SharedSublayerPolicyReadback(
    bool IsComplete,
    IReadOnlyList<WfpProviderIdentity>? Providers,
    WfpSublayerIdentity? Sublayer,
    IReadOnlyList<WfpFilterIdentity>? Filters,
    IReadOnlyDictionary<WfpPolicyObjectKey, SecurityDescriptorSnapshot>? SecurityDescriptors);

/// <summary>
/// Closed-world validator for a shared sublayer. The expected dynamic rows
/// come from the coordinator's active registry; all other providers/filters
/// are rejected. It does not prove that a native enumerator saw hidden rows.
/// </summary>
internal static class SharedSublayerReadbackContract
{
    private const int MaxProviders = LeasePolicyCompiler.MaxLeasesPerPlan + 1;
    private const int MaxFilters = NativeWfpPolicyStoreAdapter.MaxScopedFilters;
    private const int MaxDescriptorCharacters = 4096;

    internal static void Validate(
        SharedSublayerPolicyReadback readback,
        IEnumerable<ProtectedApplicationInput> baselineApplications,
        IReadOnlyList<ActiveDynamicLeaseExpectation> registeredLeases,
        WfpObjectSecurityPolicy securityPolicy)
    {
        ArgumentNullException.ThrowIfNull(readback);
        ArgumentNullException.ThrowIfNull(baselineApplications);
        ArgumentNullException.ThrowIfNull(registeredLeases);
        ArgumentNullException.ThrowIfNull(securityPolicy);
        securityPolicy.Validate();

        if (!readback.IsComplete
            || readback.Providers is null
            || readback.Sublayer is null
            || readback.Filters is null
            || readback.SecurityDescriptors is null
            || registeredLeases.Count > LeasePolicyCompiler.MaxLeasesPerPlan)
        {
            throw new WfpBaselineOwnershipException("The shared-sublayer readback is incomplete, omitted a required collection, or exceeded the active-lease bound.");
        }

        WfpProviderIdentity[] providers = readback.Providers.ToArray();
        WfpFilterIdentity[] filters = readback.Filters.ToArray();
        if (providers.Length is 0 or > MaxProviders
            || providers.Any(provider => provider is null)
            || filters.Length > MaxFilters
            || filters.Any(filter => filter is null))
        {
            throw new WfpBaselineOwnershipException("The shared-sublayer readback contains null rows or exceeds a fixed bound.");
        }

        WfpNativeObjectProjection.RequireExact(
            readback.Sublayer.NativeProjection,
            WfpNativeObjectProjection.ForSublayer(WfpServicePolicyIdentity.Sublayer),
            "shared baseline sublayer");
        if (readback.Sublayer != WfpServicePolicyIdentity.Sublayer)
        {
            throw new WfpBaselineOwnershipException("The shared-sublayer readback returned an unexpected sublayer identity.");
        }

        var expectedProviders = new Dictionary<Guid, (WfpProviderIdentity Identity, WfpNativeObjectProjection Projection)>();
        AddExpectedProvider(
            expectedProviders,
            WfpServicePolicyIdentity.Provider,
            WfpNativeObjectProjection.ForProvider(WfpServicePolicyIdentity.Provider));

        var expectedFilters = new Dictionary<Guid, WfpFilterIdentity>();
        foreach (LeasePolicyRule rule in LeasePolicyCompiler
            .CompilePersistentAppIdBaseline(baselineApplications)
            .Rules)
        {
            WfpFilterIdentity filter = PersistentBaselineCoordinator.ToFilterIdentity(rule);
            if (!expectedFilters.TryAdd(filter.Key, filter))
            {
                throw new WfpBaselineOwnershipException("The expected persistent baseline contains duplicate filter keys.");
            }
        }

        var seenLeaseIds = new HashSet<Guid>();
        foreach (ActiveDynamicLeaseExpectation lease in registeredLeases)
        {
            if (lease is null
                || lease.LeaseId == Guid.Empty
                || !seenLeaseIds.Add(lease.LeaseId)
                || lease.Provider is null
                || lease.Provider.LeaseId != lease.LeaseId
                || lease.Provider.Key == Guid.Empty
                || lease.Provider.Key == WfpServicePolicyIdentity.ProviderKey
                || lease.Filters is null
                || lease.Filters.Count is 0 or > DynamicLeaseCoordinator.MaxDynamicRulesPerLease)
            {
                throw new WfpBaselineOwnershipException("The coordinator's active-lease registry is malformed or duplicated.");
            }

            WfpNativeObjectProjection providerProjection = WfpNativeObjectProjection.ForDynamicLeaseProvider(lease.Provider);
            WfpNativeObjectProjection.RequireExact(lease.Provider.NativeProjection, providerProjection, "registered dynamic provider");
            var dynamicProvider = new WfpProviderIdentity(
                lease.Provider.Key,
                lease.Provider.Name,
                lease.Provider.Description,
                "null",
                lease.Provider.NativeProjection);
            AddExpectedProvider(expectedProviders, dynamicProvider, providerProjection);

            var perLeaseKeys = new HashSet<Guid>();
            foreach (WfpFilterIdentity filter in lease.Filters)
            {
                if (filter is null
                    || filter.Key == Guid.Empty
                    || !perLeaseKeys.Add(filter.Key)
                    || filter.ProviderKey != lease.Provider.Key
                    || filter.SublayerKey != WfpServicePolicyIdentity.SublayerKey
                    || filter.Persistent
                    || filter.Rule is null
                    || filter.Rule.Lifetime != LeasePolicyLifetime.LeaseDynamic
                    || !string.Equals(filter.Rule.LeaseId, lease.LeaseId.ToString("N"), StringComparison.Ordinal))
                {
                    throw new WfpBaselineOwnershipException("A registered dynamic filter has the wrong provider, sublayer, lifetime, lease, or key uniqueness.");
                }
                WfpNativeObjectProjection.RequireExact(
                    filter.NativeProjection,
                    WfpNativeObjectProjection.ForFilter(filter),
                    "registered dynamic filter");
                if (!expectedFilters.TryAdd(filter.Key, filter))
                {
                    throw new WfpBaselineOwnershipException("A dynamic filter key collides with another registered filter or the persistent baseline.");
                }
            }
        }

        var observedProviderKeys = new HashSet<Guid>();
        foreach (WfpProviderIdentity provider in providers)
        {
            if (!observedProviderKeys.Add(provider.Key)
                || !expectedProviders.TryGetValue(provider.Key, out var expected))
            {
                throw new WfpBaselineOwnershipException("The shared sublayer contains a duplicate or unregistered provider.");
            }
            WfpNativeObjectProjection.RequireExact(provider.NativeProjection, expected.Projection, "shared-sublayer provider");
            if (provider != expected.Identity)
            {
                throw new WfpBaselineOwnershipException("A shared-sublayer provider differs from its registered identity.");
            }
        }
        if (!observedProviderKeys.SetEquals(expectedProviders.Keys))
        {
            throw new WfpBaselineOwnershipException("The shared-sublayer readback omitted a registered provider.");
        }

        var observedFilterKeys = new HashSet<Guid>();
        foreach (WfpFilterIdentity filter in filters)
        {
            if (!observedFilterKeys.Add(filter.Key)
                || !expectedFilters.TryGetValue(filter.Key, out WfpFilterIdentity? expected)
                || filter != expected)
            {
                throw new WfpBaselineOwnershipException("The shared sublayer contains a duplicate, stale, external, or mismatched filter.");
            }
            WfpNativeObjectProjection.RequireExact(
                filter.NativeProjection,
                expected.NativeProjection!,
                "shared-sublayer filter");
        }
        if (!observedFilterKeys.SetEquals(expectedFilters.Keys))
        {
            throw new WfpBaselineOwnershipException("The shared-sublayer readback omitted a baseline or registered active-lease filter.");
        }

        var expectedAclKeys = new HashSet<WfpPolicyObjectKey>
        {
            new(WfpPolicyObjectKind.Sublayer, WfpServicePolicyIdentity.SublayerKey),
        };
        expectedAclKeys.UnionWith(expectedProviders.Keys.Select(key => new WfpPolicyObjectKey(WfpPolicyObjectKind.Provider, key)));
        expectedAclKeys.UnionWith(expectedFilters.Keys.Select(key => new WfpPolicyObjectKey(WfpPolicyObjectKind.Filter, key)));
        if (readback.SecurityDescriptors.Count != expectedAclKeys.Count
            || !readback.SecurityDescriptors.Keys.ToHashSet().SetEquals(expectedAclKeys))
        {
            throw new WfpBaselineOwnershipException("The shared-sublayer readback has missing or unexpected ACL evidence.");
        }
        foreach (WfpPolicyObjectKey key in expectedAclKeys)
        {
            ValidateAcl(readback.SecurityDescriptors, key, securityPolicy);
        }
    }

    private static void AddExpectedProvider(
        IDictionary<Guid, (WfpProviderIdentity Identity, WfpNativeObjectProjection Projection)> expected,
        WfpProviderIdentity identity,
        WfpNativeObjectProjection projection)
    {
        if (identity.Key == Guid.Empty || !expected.TryAdd(identity.Key, (identity, projection)))
        {
            throw new WfpBaselineOwnershipException("The registered providers contain a duplicate or empty provider key.");
        }
    }

    private static void ValidateAcl(
        IReadOnlyDictionary<WfpPolicyObjectKey, SecurityDescriptorSnapshot> descriptors,
        WfpPolicyObjectKey key,
        WfpObjectSecurityPolicy policy)
    {
        if (!descriptors.TryGetValue(key, out SecurityDescriptorSnapshot? descriptor)
            || descriptor is null
            || string.IsNullOrEmpty(descriptor.Sddl)
            || descriptor.Sddl.Length > MaxDescriptorCharacters
            || !string.Equals(descriptor.Sddl, policy.For(key.Kind), StringComparison.Ordinal)
            || string.IsNullOrEmpty(descriptor.Sha256)
            || descriptor.Sha256.Length != 64
            || !descriptor.DaclPresent
            || descriptor.HasNullDacl
            || descriptor.BinaryLength is < 20 or > 1_048_576)
        {
            throw new WfpBaselineOwnershipException($"The shared-sublayer {key.Kind} ACL is missing or differs from the service policy.");
        }
        byte[] expectedHash = SHA256.HashData(Encoding.UTF8.GetBytes(descriptor.Sddl));
        byte[] reportedHash;
        try
        {
            reportedHash = Convert.FromHexString(descriptor.Sha256);
        }
        catch (FormatException exception)
        {
            throw new WfpBaselineOwnershipException($"The shared-sublayer {key.Kind} ACL digest is malformed: {exception.Message}");
        }
        if (!CryptographicOperations.FixedTimeEquals(expectedHash, reportedHash))
        {
            throw new WfpBaselineOwnershipException($"The shared-sublayer {key.Kind} ACL digest does not match its normalized SDDL.");
        }
    }
}
