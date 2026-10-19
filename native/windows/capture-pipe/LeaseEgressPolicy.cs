using System.Net;
using System.Net.Sockets;
using System.Diagnostics;
using DouyinTranscript.NetworkPolicy;

namespace DouyinTranscript.CapturePipe;

internal enum LeaseDnsQuestionType
{
    A,
    Aaaa,
}

internal enum LeaseDnsRecordType
{
    CName,
    A,
    Aaaa,
}

internal sealed record LeaseDnsRecord(
    string Owner,
    LeaseDnsRecordType Type,
    string Data,
    uint? TimeToLiveSeconds = null);

internal sealed record LeaseDnsResponse(
    string QuestionName,
    LeaseDnsQuestionType QuestionType,
    int ResponseCode,
    bool IsTruncated,
    IReadOnlyList<LeaseDnsRecord> Answers,
    long? ReceivedAtTimestamp = null);

internal interface INumericDnsQuestioner
{
    ValueTask<LeaseDnsResponse> QueryAsync(
        IPAddress resolver,
        int port,
        string questionName,
        LeaseDnsQuestionType questionType,
        CancellationToken cancellationToken);
}

internal sealed record LeaseResolvedAddressSet(
    string Hostname,
    IReadOnlyList<IPAddress> Addresses,
    uint? CacheTtlSeconds);

/// <summary>
/// Validates bounded A/AAAA answer chains from typed DNS responses. The transport
/// must validate response identity and completeness; this class performs no I/O.
/// </summary>
internal static class LeaseEgressPolicy
{
    public const int DnsPort = 53;
    public const int HttpsPort = 443;
    public const int MaxCnameHops = 8;
    public const int MaxAnswersPerResponse = 64;
    public const int MaxTotalAnswers = 128;
    public const int MaxQuestions = 20;
    public const int MaxPinnedAddresses = 64;
    public const uint MaxCacheTtlSeconds = 300;

    private static readonly TimeSpan ResolutionDeadline = TimeSpan.FromSeconds(10);

    public static Task<LeaseResolvedAddressSet> ResolveAsync(
        string hostname,
        IPAddress numericResolver,
        INumericDnsQuestioner questioner,
        CancellationToken cancellationToken) =>
        ResolveAsync(hostname, numericResolver, questioner, cancellationToken, ResolutionDeadline);

    internal static async Task<LeaseResolvedAddressSet> ResolveAsync(
        string hostname,
        IPAddress numericResolver,
        INumericDnsQuestioner questioner,
        CancellationToken cancellationToken,
        TimeSpan resolutionDeadline)
    {
        ArgumentNullException.ThrowIfNull(numericResolver);
        ArgumentNullException.ThrowIfNull(questioner);
        if (resolutionDeadline <= TimeSpan.Zero || resolutionDeadline > ResolutionDeadline)
        {
            throw new ArgumentOutOfRangeException(
                nameof(resolutionDeadline),
                "DNS resolution deadline must be positive and may not exceed the production limit.");
        }

        string canonicalHostname = NormalizeDnsName(hostname);
        if (!PublicUnicastAddressPolicy.IsPublicUnicast(numericResolver))
        {
            throw new InvalidOperationException("The DNS resolver must be a numeric public unicast address.");
        }

        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(resolutionDeadline);

        int queryCount = 0;
        int answerCount = 0;
        uint minimumCacheTtl = MaxCacheTtlSeconds;
        bool hasUncacheableRecord = false;
        void ObserveCacheTtl(uint? ttlSeconds, long? receivedAtTimestamp)
        {
            if (ttlSeconds is null)
            {
                hasUncacheableRecord = true;
                return;
            }
            uint boundedTtl = Math.Min(ttlSeconds.Value, MaxCacheTtlSeconds);
            long receivedAt = receivedAtTimestamp ?? Stopwatch.GetTimestamp();
            long elapsedTicks = Stopwatch.GetTimestamp() - receivedAt;
            if (elapsedTicks < 0)
            {
                hasUncacheableRecord = true;
                return;
            }
            double remainingSeconds = boundedTtl - (elapsedTicks / (double)Stopwatch.Frequency);
            uint wholeRemainingSeconds = remainingSeconds <= 0 ? 0 : (uint)Math.Floor(remainingSeconds);
            if (wholeRemainingSeconds == 0)
            {
                hasUncacheableRecord = true;
                return;
            }
            minimumCacheTtl = Math.Min(minimumCacheTtl, wholeRemainingSeconds);
        }

        var addresses = new HashSet<IPAddress>();
        try
        {
            await ResolveFamilyAsync(
                canonicalHostname,
                numericResolver,
                LeaseDnsQuestionType.A,
                questioner,
                deadline.Token,
                () => ++queryCount,
                count =>
                {
                    answerCount += count;
                    if (answerCount > MaxTotalAnswers)
                    {
                        throw new InvalidOperationException("DNS resolution exceeded the total answer limit.");
                    }
                },
                ObserveCacheTtl,
                addresses).ConfigureAwait(false);
            await ResolveFamilyAsync(
                canonicalHostname,
                numericResolver,
                LeaseDnsQuestionType.Aaaa,
                questioner,
                deadline.Token,
                () => ++queryCount,
                count =>
                {
                    answerCount += count;
                    if (answerCount > MaxTotalAnswers)
                    {
                        throw new InvalidOperationException("DNS resolution exceeded the total answer limit.");
                    }
                },
                ObserveCacheTtl,
                addresses).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            throw new TimeoutException("Bounded DNS resolution exceeded its deadline.");
        }

        if (queryCount > MaxQuestions || answerCount > MaxTotalAnswers)
        {
            throw new InvalidOperationException("DNS resolution exceeded a configured resource limit.");
        }
        if (addresses.Count == 0)
        {
            throw new InvalidOperationException("DNS resolution produced no terminal A or AAAA addresses.");
        }
        if (addresses.Count > MaxPinnedAddresses)
        {
            throw new InvalidOperationException("DNS resolution produced too many pinned addresses.");
        }

        IPAddress[] ordered = addresses
            .OrderBy(address => address.AddressFamily == AddressFamily.InterNetwork ? 0 : 1)
            .ThenBy(address => Convert.ToHexString(address.GetAddressBytes()), StringComparer.Ordinal)
            .ToArray();
        uint? cacheTtlSeconds = hasUncacheableRecord ? null : minimumCacheTtl;
        return new LeaseResolvedAddressSet(canonicalHostname, Array.AsReadOnly(ordered), cacheTtlSeconds);
    }

    private static async Task ResolveFamilyAsync(
        string initialName,
        IPAddress numericResolver,
        LeaseDnsQuestionType questionType,
        INumericDnsQuestioner questioner,
        CancellationToken cancellationToken,
        Func<int> incrementQuestionCount,
        Action<int> incrementAnswerCount,
        Action<uint?, long?> observeCacheTtl,
        HashSet<IPAddress> addresses)
    {
        string currentName = initialName;
        var visited = new HashSet<string>(StringComparer.Ordinal);
        var responseAnswers = new Dictionary<string, List<LeaseDnsRecord>>(StringComparer.Ordinal);
        long? responseReceivedAtTimestamp = null;
        int cnameHops = 0;

        while (true)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (!visited.Add(currentName))
            {
                throw new InvalidOperationException("DNS response contains a CNAME loop.");
            }

            if (!responseAnswers.TryGetValue(currentName, out List<LeaseDnsRecord>? ownerAnswers))
            {
                int queryCount = incrementQuestionCount();
                if (queryCount > MaxQuestions)
                {
                    throw new InvalidOperationException("DNS resolution exceeded the question limit.");
                }

                LeaseDnsResponse response = await questioner.QueryAsync(
                    numericResolver,
                    DnsPort,
                    currentName,
                    questionType,
                    cancellationToken).AsTask().WaitAsync(cancellationToken).ConfigureAwait(false);
                ValidateResponse(response, currentName, questionType);
                responseReceivedAtTimestamp = response.ReceivedAtTimestamp ?? Stopwatch.GetTimestamp();
                incrementAnswerCount(response.Answers.Count);
                if (response.Answers.Count > MaxAnswersPerResponse)
                {
                    throw new InvalidOperationException("DNS response exceeded the answer limit.");
                }

                responseAnswers = IndexAndValidateAnswers(response.Answers);
                ownerAnswers = responseAnswers.GetValueOrDefault(currentName);
            }

            if (ownerAnswers is null || ownerAnswers.Count == 0)
            {
                // A successful empty family response is negative DNS evidence. Since
                // authority SOA negative TTLs are not consumed here, do not cache the
                // combined A/AAAA pin set when either family has no terminal answer.
                observeCacheTtl(null, responseReceivedAtTimestamp);
                return;
            }

            if (ownerAnswers.Any(record => record.Type == LeaseDnsRecordType.CName)
                && ownerAnswers.Any(record => record.Type is LeaseDnsRecordType.A or LeaseDnsRecordType.Aaaa))
            {
                throw new InvalidOperationException("A reachable DNS owner cannot mix CNAME and address records.");
            }

            LeaseDnsRecord[] aliases = ownerAnswers
                .Where(record => record.Type == LeaseDnsRecordType.CName)
                .ToArray();
            LeaseDnsRecordType expectedAddressType = questionType == LeaseDnsQuestionType.A
                ? LeaseDnsRecordType.A
                : LeaseDnsRecordType.Aaaa;
            LeaseDnsRecord[] terminalRecords = ownerAnswers
                .Where(record => record.Type == expectedAddressType)
                .ToArray();

            if (aliases.Length > 0)
            {
                if (terminalRecords.Length > 0)
                {
                    throw new InvalidOperationException("A DNS owner cannot contain both a CNAME and terminal address records.");
                }
                string[] targets = aliases.Select(record => NormalizeDnsName(record.Data)).Distinct(StringComparer.Ordinal).ToArray();
                if (targets.Length != 1)
                {
                    throw new InvalidOperationException("A DNS owner has conflicting CNAME targets.");
                }
                foreach (LeaseDnsRecord alias in aliases)
                {
                    observeCacheTtl(alias.TimeToLiveSeconds, responseReceivedAtTimestamp);
                }
                cnameHops++;
                if (cnameHops > MaxCnameHops)
                {
                    throw new InvalidOperationException("DNS response exceeded the CNAME hop limit.");
                }
                currentName = targets[0];
                continue;
            }

            if (terminalRecords.Length == 0)
            {
                // A response can contain another address family at this owner,
                // while this question's NODATA TTL lives in the authority SOA.
                observeCacheTtl(null, responseReceivedAtTimestamp);
                return;
            }

            foreach (LeaseDnsRecord record in terminalRecords)
            {
                if (!IPAddress.TryParse(record.Data, out IPAddress? address)
                    || address is null
                    || !MatchesFamily(address, questionType)
                    || !PublicUnicastAddressPolicy.IsPublicUnicast(address))
                {
                    throw new InvalidOperationException("DNS response contained a malformed or non-public address.");
                }
                observeCacheTtl(record.TimeToLiveSeconds, responseReceivedAtTimestamp);
                addresses.Add(address);
                if (addresses.Count > MaxPinnedAddresses)
                {
                    throw new InvalidOperationException("DNS resolution produced too many pinned addresses.");
                }
            }
            return;
        }
    }

    private static Dictionary<string, List<LeaseDnsRecord>> IndexAndValidateAnswers(IReadOnlyList<LeaseDnsRecord> answers)
    {
        var byOwner = new Dictionary<string, List<LeaseDnsRecord>>(StringComparer.Ordinal);
        foreach (LeaseDnsRecord record in answers)
        {
            string owner = NormalizeDnsRecordName(record.Owner);
            string data = record.Type switch
            {
                LeaseDnsRecordType.CName => NormalizeDnsRecordName(record.Data),
                LeaseDnsRecordType.A when IPAddress.TryParse(record.Data, out IPAddress? ipv4Address)
                    && ipv4Address.AddressFamily == AddressFamily.InterNetwork => ipv4Address.ToString(),
                LeaseDnsRecordType.Aaaa when IPAddress.TryParse(record.Data, out IPAddress? ipv6Address)
                    && ipv6Address.AddressFamily == AddressFamily.InterNetworkV6
                    && ipv6Address.ScopeId == 0 => ipv6Address.ToString(),
                LeaseDnsRecordType.A or LeaseDnsRecordType.Aaaa => throw new InvalidOperationException("DNS answer has an address with the wrong family or invalid syntax."),
                _ => throw new InvalidOperationException("DNS answer has an unsupported record type."),
            };
            var normalized = new LeaseDnsRecord(owner, record.Type, data, record.TimeToLiveSeconds);
            if (!byOwner.TryGetValue(owner, out List<LeaseDnsRecord>? ownerRecords))
            {
                ownerRecords = [];
                byOwner.Add(owner, ownerRecords);
            }
            ownerRecords.Add(normalized);
        }

        return byOwner;
    }

    private static void ValidateResponse(LeaseDnsResponse response, string questionName, LeaseDnsQuestionType questionType)
    {
        ArgumentNullException.ThrowIfNull(response);
        if (response.Answers is null)
        {
            throw new InvalidOperationException("DNS response is missing its answer set.");
        }
        if (response.IsTruncated)
        {
            throw new InvalidOperationException("Truncated DNS responses are not accepted.");
        }
        if (response.ResponseCode != 0)
        {
            throw new InvalidOperationException("DNS response did not indicate success.");
        }
        if (!StringComparer.Ordinal.Equals(NormalizeDnsName(response.QuestionName), questionName)
            || response.QuestionType != questionType)
        {
            throw new InvalidOperationException("DNS response question does not match the request.");
        }
    }

    internal static string NormalizeDnsName(string name)
    {
        if (string.IsNullOrWhiteSpace(name) || name.Length > 253 || name.EndsWith(".", StringComparison.Ordinal))
        {
            throw new InvalidOperationException("DNS name is empty, overlong, or not canonical.");
        }

        string[] labels = name.Split('.');
        if (labels.Length < 2 || labels.Any(label => label.Length is 0 or > 63))
        {
            throw new InvalidOperationException("DNS name must contain valid multi-label hostname syntax.");
        }
        foreach (string label in labels)
        {
            if (!((label[0] is >= 'A' and <= 'Z') || (label[0] is >= 'a' and <= 'z') || (label[0] is >= '0' and <= '9'))
                || !((label[^1] is >= 'A' and <= 'Z') || (label[^1] is >= 'a' and <= 'z') || (label[^1] is >= '0' and <= '9'))
                || label.Any(character => !((character is >= 'A' and <= 'Z') || (character is >= 'a' and <= 'z')
                    || (character is >= '0' and <= '9') || character == '-')))
            {
                throw new InvalidOperationException("DNS name is not canonical ASCII hostname syntax.");
            }
        }
        return name.ToLowerInvariant();
    }

    private static string NormalizeDnsRecordName(string name)
    {
        ArgumentNullException.ThrowIfNull(name);
        string value = name.EndsWith(".", StringComparison.Ordinal) ? name[..^1] : name;
        if (value.Length > 253)
        {
            throw new InvalidOperationException("DNS record name exceeds the maximum text length.");
        }
        if (value.Length == 0)
        {
            return string.Empty;
        }

        string[] labels = value.Split('.');
        if (labels.Any(label => label.Length is 0 or > 63
            || label.Any(character => character is < '!' or > '~' || character == '.')))
        {
            throw new InvalidOperationException("DNS record name has an invalid label encoding or length.");
        }
        return value.ToLowerInvariant();
    }

    private static bool MatchesFamily(IPAddress address, LeaseDnsQuestionType questionType) =>
        questionType == LeaseDnsQuestionType.A
            ? address.AddressFamily == AddressFamily.InterNetwork
            : address.AddressFamily == AddressFamily.InterNetworkV6;

}
