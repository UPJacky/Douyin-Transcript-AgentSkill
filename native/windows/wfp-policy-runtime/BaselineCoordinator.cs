using System.Security.Cryptography;
using System.Text;
using WfpPolicyPlan;

namespace WfpPolicy.Runtime;

internal sealed record WfpProviderIdentity(
    Guid Key,
    string Name,
    string Description,
    string ServiceName,
    WfpNativeObjectProjection? NativeProjection = null);

internal sealed record WfpSublayerIdentity(
    Guid Key,
    Guid ProviderKey,
    string Name,
    string Description,
    ushort Weight,
    WfpNativeObjectProjection? NativeProjection = null);

/// <summary>
/// A value-only readback of a service-owned filter. Native pointers must be
/// decoded and copied by the backend before they are freed.
/// </summary>
internal sealed record WfpFilterIdentity(
    Guid Key,
    Guid ProviderKey,
    Guid SublayerKey,
    string Name,
    string Description,
    bool Persistent,
    LeasePolicyRule Rule,
    WfpNativeObjectProjection? NativeProjection = null);

internal sealed record WfpPolicySnapshot(
    WfpProviderIdentity? Provider,
    WfpSublayerIdentity? Sublayer,
    IReadOnlyList<WfpFilterIdentity> Filters,
    WfpNativeReadbackProjection? NativeReadbackProjection = null);

/// <summary>
/// Store contract for the baseline reconciler. Implementations must use one
/// explicit BFE transaction per mutation batch, abort on dispose unless commit
/// succeeded, and return complete copied readback values. Transaction reads and
/// writes must share a stable view for the transaction lifetime; a backend that
/// cannot prevent a check-then-mutate race must fail closed instead of applying
/// the batch.
/// </summary>
internal interface IWfpPolicyStore
{
    WfpPolicySnapshot ReadSnapshot(Guid providerKey, Guid sublayerKey);
    IWfpPolicyTransaction BeginTransaction();
}

internal interface IWfpPolicyTransaction : IDisposable
{
    WfpProviderIdentity? GetProvider(Guid key);
    WfpSublayerIdentity? GetSublayer(Guid key);
    IReadOnlyList<WfpFilterIdentity> EnumerateProviderFilters(Guid providerKey);
    IReadOnlyList<WfpFilterIdentity> EnumerateSublayerFilters(Guid sublayerKey);
    void AddProvider(WfpProviderIdentity provider);
    void DeleteProvider(Guid key);
    void AddSublayer(WfpSublayerIdentity sublayer);
    void DeleteSublayer(Guid key);
    void AddFilter(WfpFilterIdentity filter);
    void DeleteFilter(Guid key);
    void Commit();
    void Abort();
}

/// <summary>
/// Optional transaction contract for stores that can preserve complete native
/// readback evidence alongside the value-only coordinator view.
/// </summary>
internal interface IWfpPolicySnapshotTransaction
{
    WfpPolicySnapshot ReadSnapshot();
}

internal static class WfpServicePolicyIdentity
{
    // These keys are part of the installed service identity. Never derive
    // them from caller-controlled values or rotate them without a migration.
    internal static readonly Guid ProviderKey = new("b853c1c7-386c-4fd7-a086-c5aeb557ee95");
    internal static readonly Guid SublayerKey = new("507c6bb8-6ac7-41bf-842a-0de020dbe0a6");
    internal const string ServiceName = "DouyinTranscriptCapture";
    internal const string ProviderName = "Douyin Transcript Capture";
    internal const string ProviderDescription = "Service-owned policy objects for isolated transcript capture.";
    internal const string SublayerName = "Douyin Transcript Capture Baseline";
    internal const string SublayerDescription = "Persistent protected-application default-deny baseline.";
    internal const ushort SublayerWeight = 0x7fff;
    internal const string FilterNamePrefix = "DouyinTranscript:baseline:v1:";

    internal static WfpProviderIdentity Provider { get; } = CreateProvider();

    internal static WfpSublayerIdentity Sublayer { get; } = CreateSublayer();

    private static WfpProviderIdentity CreateProvider()
    {
        var provider = new WfpProviderIdentity(
            ProviderKey,
            ProviderName,
            ProviderDescription,
            ServiceName);
        return provider with { NativeProjection = WfpNativeObjectProjection.ForProvider(provider) };
    }

    private static WfpSublayerIdentity CreateSublayer()
    {
        var sublayer = new WfpSublayerIdentity(
            SublayerKey,
            ProviderKey,
            SublayerName,
            SublayerDescription,
            SublayerWeight);
        return sublayer with { NativeProjection = WfpNativeObjectProjection.ForSublayer(sublayer) };
    }

    internal static Guid FilterKey(string ruleId)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(ruleId);
        byte[] identity = Encoding.UTF8.GetBytes($"DouyinTranscript.Wfp.Runtime.v1\0{ProviderKey:D}\0{ruleId}");
        try
        {
            return new Guid(SHA256.HashData(identity).AsSpan(0, 16));
        }
        finally
        {
            CryptographicOperations.ZeroMemory(identity);
        }
    }
}

/// <summary>
/// Reconciles only this service's persistent AppID baseline. It never opens
/// BFE itself; a native store is still required before this can be installed.
/// </summary>
internal sealed class PersistentBaselineCoordinator(IWfpPolicyStore store)
{
    public void EnsureReady(IEnumerable<ProtectedApplicationInput> applications, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(applications);
        ArgumentNullException.ThrowIfNull(store);
        ProtectedApplicationInput[] inputs = applications.Take(129).ToArray();
        if (inputs.Length > 128)
        {
            throw new ArgumentException("The protected application set exceeds the baseline bound.", nameof(applications));
        }

        PersistentAppIdBaselinePlan plan = LeasePolicyCompiler.CompilePersistentAppIdBaseline(inputs);
        WfpFilterIdentity[] desiredFilters = plan.Rules
            .Select(ToFilterIdentity)
            .OrderBy(filter => filter.Key)
            .ToArray();
        WfpPolicySnapshot before = Normalize(store.ReadSnapshot(
            WfpServicePolicyIdentity.ProviderKey,
            WfpServicePolicyIdentity.SublayerKey));
        ValidateExistingOwnership(before);

        var desiredByKey = desiredFilters.ToDictionary(filter => filter.Key);
        var currentByKey = before.Filters.ToDictionary(filter => filter.Key);
        foreach (Guid key in desiredByKey.Keys.Intersect(currentByKey.Keys))
        {
            if (!IsManaged(currentByKey[key]))
            {
                throw new WfpBaselineOwnershipException("A WFP filter key collides with an object outside the service-owned baseline.");
            }
        }

        var inverseOperations = new Stack<Action<IWfpPolicyTransaction>>();
        bool committed = false;
        using (IWfpPolicyTransaction transaction = store.BeginTransaction())
        {
            try
            {
                cancellationToken.ThrowIfCancellationRequested();
                WfpPolicySnapshot transactionSnapshot = Normalize(ReadTransactionSnapshot(transaction));
                ValidateExistingOwnership(transactionSnapshot);
                if (!SnapshotsEqual(transactionSnapshot, before)
                    || !ReadbackProjectionsEqual(transactionSnapshot.NativeReadbackProjection, before.NativeReadbackProjection))
                {
                    throw new WfpBaselineOwnershipException("The service-owned WFP baseline changed while reconciliation was starting.");
                }

                if (transaction.GetProvider(WfpServicePolicyIdentity.ProviderKey) is null)
                {
                    transaction.AddProvider(WfpServicePolicyIdentity.Provider);
                    inverseOperations.Push(tx => tx.DeleteProvider(WfpServicePolicyIdentity.ProviderKey));
                }
                if (transaction.GetSublayer(WfpServicePolicyIdentity.SublayerKey) is null)
                {
                    transaction.AddSublayer(WfpServicePolicyIdentity.Sublayer);
                    inverseOperations.Push(tx => tx.DeleteSublayer(WfpServicePolicyIdentity.SublayerKey));
                }

                foreach (WfpFilterIdentity current in before.Filters.Where(IsManaged))
                {
                    if (!desiredByKey.TryGetValue(current.Key, out WfpFilterIdentity? desired)
                        || current != desired)
                    {
                        transaction.DeleteFilter(current.Key);
                        inverseOperations.Push(tx => tx.AddFilter(current));
                    }
                }

                foreach (WfpFilterIdentity desired in desiredFilters)
                {
                    if (currentByKey.TryGetValue(desired.Key, out WfpFilterIdentity? current)
                        && current == desired)
                    {
                        continue;
                    }

                    if (current is not null)
                    {
                        if (!IsManaged(current))
                        {
                            throw new WfpBaselineOwnershipException("A WFP filter key collides with an object outside the service-owned baseline.");
                        }
                    }

                    transaction.AddFilter(desired);
                    inverseOperations.Push(tx => tx.DeleteFilter(desired.Key));
                }

                cancellationToken.ThrowIfCancellationRequested();
                transaction.Commit();
                committed = true;
            }
            catch (Exception failure)
            {
                if (!committed)
                {
                    try
                    {
                        transaction.Abort();
                    }
                    catch (Exception abortFailure)
                    {
                        throw new WfpBaselineRollbackException(failure, abortFailure);
                    }
                }
                throw;
            }
        }

        WfpPolicySnapshot expectedAfter = ExpectedSnapshotAfter(before, desiredFilters);
        WfpPolicySnapshot after;
        try
        {
            after = Normalize(store.ReadSnapshot(
                WfpServicePolicyIdentity.ProviderKey,
                WfpServicePolicyIdentity.SublayerKey));
            ValidateExistingOwnership(after);
            if (!MatchesDesired(after, desiredFilters))
            {
                throw new InvalidOperationException("The committed WFP baseline did not match its complete expected readback.");
            }
        }
        catch (Exception verificationFailure)
        {
            try
            {
                RestoreBeforeSnapshot(inverseOperations, before, expectedAfter);
            }
            catch (Exception rollbackFailure)
            {
                throw new WfpBaselineRollbackException(verificationFailure, rollbackFailure);
            }
            throw new WfpBaselineVerificationException(verificationFailure);
        }

        cancellationToken.ThrowIfCancellationRequested();
    }

    private void RestoreBeforeSnapshot(
        Stack<Action<IWfpPolicyTransaction>> inverseOperations,
        WfpPolicySnapshot before,
        WfpPolicySnapshot expectedAfter)
    {
        using (IWfpPolicyTransaction rollback = store.BeginTransaction())
        {
            try
            {
                WfpPolicySnapshot current = Normalize(ReadTransactionSnapshot(rollback));
                ValidateExistingOwnership(current);
                if (!SnapshotsEqual(current, expectedAfter))
                {
                    throw new InvalidOperationException(
                        "The committed WFP baseline changed before compensation; rollback state is uncertain and was left untouched.");
                }

                foreach (Action<IWfpPolicyTransaction> inverse in inverseOperations)
                {
                    inverse(rollback);
                }
                rollback.Commit();
            }
            catch (Exception failure)
            {
                try
                {
                    rollback.Abort();
                }
                catch (Exception abortFailure)
                {
                    throw new AggregateException(failure, abortFailure);
                }
                throw;
            }
        }

        WfpPolicySnapshot restored = Normalize(store.ReadSnapshot(
            WfpServicePolicyIdentity.ProviderKey,
            WfpServicePolicyIdentity.SublayerKey));
        if (!SnapshotsEqual(restored, before))
        {
            throw new InvalidOperationException("The previous WFP baseline state could not be confirmed after rollback.");
        }
    }

    internal static WfpFilterIdentity ToFilterIdentity(LeasePolicyRule rule) => new(
        WfpServicePolicyIdentity.FilterKey(rule.RuleId),
        WfpServicePolicyIdentity.ProviderKey,
        WfpServicePolicyIdentity.SublayerKey,
        WfpServicePolicyIdentity.FilterNamePrefix + rule.RuleId,
        rule.Purpose,
        Persistent: true,
        Rule: rule,
        NativeProjection: WfpNativeObjectProjection.ForFilter(new WfpFilterIdentity(
            WfpServicePolicyIdentity.FilterKey(rule.RuleId),
            WfpServicePolicyIdentity.ProviderKey,
            WfpServicePolicyIdentity.SublayerKey,
            WfpServicePolicyIdentity.FilterNamePrefix + rule.RuleId,
            rule.Purpose,
            Persistent: true,
            Rule: rule)));

    private static bool IsManaged(WfpFilterIdentity filter) =>
        HasOwnershipMarker(filter)
        && filter.SublayerKey == WfpServicePolicyIdentity.SublayerKey
        && filter.Persistent;

    private static bool HasOwnershipMarker(WfpFilterIdentity filter) =>
        filter.ProviderKey == WfpServicePolicyIdentity.ProviderKey
        && filter.Name.StartsWith(WfpServicePolicyIdentity.FilterNamePrefix, StringComparison.Ordinal);

    private static bool IsSupportedBaselineRule(LeasePolicyRule rule) =>
        rule.Lifetime == LeasePolicyLifetime.PersistentDefaultDeny
        && rule.Action == LeasePolicyAction.Block
        && rule.WeightRangeIndex == LeasePolicyCompiler.DefaultDenyWeightRangeIndex
        && rule.LeaseId is null
        && rule.AppIdHex is not null
        && rule.LeaseSid is null
        && rule.IdentityCondition == "ALE_APP_ID"
        && rule.RemoteAddress is null
        && rule.Protocol is null
        && rule.RemotePort is null
        && !rule.ClearActionRight
        && rule.RuleId.StartsWith("default-deny-", StringComparison.Ordinal)
        && rule.Purpose.StartsWith("Persistent catch-all block for ", StringComparison.Ordinal)
        && Enum.IsDefined(rule.AddressFamily);

    private static bool IsValidOwnedFilter(WfpFilterIdentity filter) =>
        IsManaged(filter)
        && IsSupportedBaselineRule(filter.Rule)
        && filter.Name == WfpServicePolicyIdentity.FilterNamePrefix + filter.Rule.RuleId
        && filter.Description == filter.Rule.Purpose
        && filter.Key == WfpServicePolicyIdentity.FilterKey(filter.Rule.RuleId);

    private static void ValidateExistingOwnership(WfpPolicySnapshot snapshot)
    {
        if (snapshot.Provider is not null)
        {
            WfpNativeObjectProjection.RequireExact(
                snapshot.Provider.NativeProjection,
                WfpNativeObjectProjection.ForProvider(WfpServicePolicyIdentity.Provider),
                "provider");
        }
        if (snapshot.Sublayer is not null)
        {
            WfpNativeObjectProjection.RequireExact(
                snapshot.Sublayer.NativeProjection,
                WfpNativeObjectProjection.ForSublayer(WfpServicePolicyIdentity.Sublayer),
                "sublayer");
        }
        foreach (WfpFilterIdentity filter in snapshot.Filters)
        {
            WfpNativeObjectProjection.RequireExact(
                filter.NativeProjection,
                WfpNativeObjectProjection.ForFilter(filter),
                "filter");
        }

        if (snapshot.Provider is not null && snapshot.Provider != WfpServicePolicyIdentity.Provider)
        {
            throw new WfpBaselineOwnershipException("The service-owned WFP provider key is occupied by an object with different ownership metadata.");
        }
        if (snapshot.Sublayer is not null && snapshot.Sublayer != WfpServicePolicyIdentity.Sublayer)
        {
            throw new WfpBaselineOwnershipException("The service-owned WFP sublayer key is occupied by an object with different ownership metadata.");
        }
        if (snapshot.Provider is null && snapshot.Sublayer is not null)
        {
            throw new WfpBaselineOwnershipException("The service-owned WFP sublayer exists without its provider.");
        }
        if (snapshot.Filters.Any(filter =>
                filter.ProviderKey != WfpServicePolicyIdentity.ProviderKey
                && filter.SublayerKey != WfpServicePolicyIdentity.SublayerKey))
        {
            throw new InvalidOperationException("The WFP store returned a filter outside both requested ownership scopes.");
        }
        if (snapshot.Filters.Any(filter =>
                filter.SublayerKey == WfpServicePolicyIdentity.SublayerKey
                && filter.ProviderKey != WfpServicePolicyIdentity.ProviderKey))
        {
            throw new WfpBaselineOwnershipException("A filter from another provider occupies the service-owned baseline sublayer.");
        }
        if (snapshot.Filters.Any(filter => HasOwnershipMarker(filter) && !IsValidOwnedFilter(filter)))
        {
            throw new WfpBaselineOwnershipException("A service-marked WFP filter has mismatched ownership or baseline content.");
        }
        if (snapshot.Filters.Any(filter =>
                filter.ProviderKey == WfpServicePolicyIdentity.ProviderKey
                && filter.SublayerKey == WfpServicePolicyIdentity.SublayerKey
                && !IsValidOwnedFilter(filter)))
        {
            throw new WfpBaselineOwnershipException("The service baseline sublayer contains an unrecognized WFP filter.");
        }
        if (snapshot.Provider is null && snapshot.Filters.Any(filter => filter.ProviderKey == WfpServicePolicyIdentity.ProviderKey))
        {
            throw new WfpBaselineOwnershipException("Service-provider filters exist without the service-owned provider.");
        }
        if (snapshot.Filters.Select(filter => filter.Key).Distinct().Count() != snapshot.Filters.Count)
        {
            throw new InvalidOperationException("The WFP store returned duplicate filter keys.");
        }
    }

    private static bool MatchesDesired(WfpPolicySnapshot snapshot, IReadOnlyList<WfpFilterIdentity> desiredFilters)
    {
        if (snapshot.Provider != WfpServicePolicyIdentity.Provider
            || snapshot.Sublayer != WfpServicePolicyIdentity.Sublayer)
        {
            return false;
        }
        WfpFilterIdentity[] managed = snapshot.Filters.Where(IsManaged).OrderBy(filter => filter.Key).ToArray();
        return managed.SequenceEqual(desiredFilters.OrderBy(filter => filter.Key));
    }

    private static WfpPolicySnapshot ExpectedSnapshotAfter(
        WfpPolicySnapshot before,
        IReadOnlyList<WfpFilterIdentity> desiredFilters) => new(
            WfpServicePolicyIdentity.Provider,
            WfpServicePolicyIdentity.Sublayer,
            Array.AsReadOnly(before.Filters
                .Where(filter => !IsManaged(filter))
                .Concat(desiredFilters)
                .OrderBy(filter => filter.Key)
                .ToArray()));

    private static WfpPolicySnapshot Normalize(WfpPolicySnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        ArgumentNullException.ThrowIfNull(snapshot.Filters);
        snapshot.NativeReadbackProjection?.RequireCanonical();
        return snapshot with { Filters = Array.AsReadOnly(snapshot.Filters.OrderBy(filter => filter.Key).ToArray()) };
    }

    private static bool SnapshotsEqual(WfpPolicySnapshot left, WfpPolicySnapshot right) =>
        left.Provider == right.Provider
        && left.Sublayer == right.Sublayer
        && left.Filters.SequenceEqual(right.Filters);

    private static bool ReadbackProjectionsEqual(
        WfpNativeReadbackProjection? left,
        WfpNativeReadbackProjection? right) =>
        left is null ? right is null : left.Equals(right);

    private static WfpPolicySnapshot ReadTransactionSnapshot(IWfpPolicyTransaction transaction)
    {
        if (transaction is IWfpPolicySnapshotTransaction snapshotTransaction)
        {
            return snapshotTransaction.ReadSnapshot();
        }

        var filters = new Dictionary<Guid, WfpFilterIdentity>();
        foreach (WfpFilterIdentity filter in transaction.EnumerateProviderFilters(WfpServicePolicyIdentity.ProviderKey)
            .Concat(transaction.EnumerateSublayerFilters(WfpServicePolicyIdentity.SublayerKey)))
        {
            if (filters.TryGetValue(filter.Key, out WfpFilterIdentity? existing) && existing != filter)
            {
                throw new InvalidOperationException("The WFP transaction returned conflicting values for one filter key.");
            }
            filters[filter.Key] = filter;
        }

        return new WfpPolicySnapshot(
            transaction.GetProvider(WfpServicePolicyIdentity.ProviderKey),
            transaction.GetSublayer(WfpServicePolicyIdentity.SublayerKey),
            Array.AsReadOnly(filters.Values.OrderBy(filter => filter.Key).ToArray()));
    }
}

internal sealed class WfpBaselineVerificationException(Exception innerException)
    : InvalidOperationException("The WFP baseline could not be confirmed; readiness must remain closed.", innerException);

internal sealed class WfpBaselineOwnershipException(string message) : InvalidOperationException(message);

internal sealed class WfpBaselineRollbackException(Exception operationFailure, Exception rollbackFailure)
    : InvalidOperationException(
        "The WFP baseline operation or compensating rollback failed; readiness must remain closed.",
        new AggregateException(operationFailure, rollbackFailure));
