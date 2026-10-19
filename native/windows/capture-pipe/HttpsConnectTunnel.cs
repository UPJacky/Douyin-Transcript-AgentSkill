using System.Net;
using System.Net.Sockets;
using System.Text;

namespace DouyinTranscript.CapturePipe;

/// <summary>
/// Represents one already-accepted TCP peer. A future caller must authenticate
/// and WFP-restrict that peer before invoking the CONNECT handler.
/// </summary>
internal interface IHttpsConnectPeer : IAsyncDisposable
{
    Stream Stream { get; }
    void ShutdownSend();
}

/// <summary>
/// Handles one HTTPS CONNECT request on an accepted stream. This class does not
/// create a listener, authenticate a local process, or apply network policy.
/// </summary>
internal static class HttpsConnectTunnel
{
    internal const int MaximumRequestBytes = 16 * 1024;
    internal const int MaximumRequestLineBytes = 2048;
    internal const int MaximumHeaderCount = 32;
    internal const int MaximumEarlyTunnelBytes = 1024;
    internal const long MaximumTunnelBytes = 512L * 1024 * 1024;
    internal const int MaximumAddressAttempts = 4;

    private static readonly TimeSpan SetupDeadline = TimeSpan.FromSeconds(30);
    private static readonly TimeSpan PerAddressConnectDeadline = TimeSpan.FromSeconds(5);
    private static readonly TimeSpan TunnelLifetime = TimeSpan.FromMinutes(30);
    private static readonly TimeSpan TunnelIdleTimeout = TimeSpan.FromMinutes(2);
    private static readonly TimeSpan FailureResponseDeadline = TimeSpan.FromSeconds(1);

    private static readonly HashSet<string> ExactHosts = new(StringComparer.Ordinal)
    {
        "douyin.com",
        "www.douyin.com",
        "v.douyin.com",
        "passport.douyin.com",
        "www.iesdouyin.com",
    };

    private static readonly string[] AllowedHostSuffixes =
    [
        ".douyin.com",
        ".iesdouyin.com",
        ".douyinvod.com",
        ".douyinpic.com",
        ".bytecdn.cn",
        ".bytecdntp.com",
        ".ibytedtos.com",
        ".byteimg.com",
    ];

    public static async Task HandleAsync(
        IHttpsConnectPeer client,
        IPAddress numericResolver,
        INumericDnsQuestioner dnsQuestioner,
        ILeaseUpstreamPermitProvider permitProvider,
        ILeaseTcpDialer dialer,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(client);
        ArgumentNullException.ThrowIfNull(numericResolver);
        ArgumentNullException.ThrowIfNull(dnsQuestioner);
        ArgumentNullException.ThrowIfNull(permitProvider);
        ArgumentNullException.ThrowIfNull(dialer);

        bool responseStarted = false;
        try
        {
            using var setupDeadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            setupDeadline.CancelAfter(SetupDeadline);

            ConnectRequest request;
            try
            {
                request = await ReadRequestAsync(client.Stream, setupDeadline.Token).ConfigureAwait(false);
            }
            catch (ConnectRequestRejectedException)
            {
                await TryWriteStatusAsync(client.Stream, 400, "Bad Request").ConfigureAwait(false);
                responseStarted = true;
                return;
            }

            if (!IsAllowedHostname(request.Hostname))
            {
                await TryWriteStatusAsync(client.Stream, 403, "Forbidden").ConfigureAwait(false);
                responseStarted = true;
                return;
            }

            LeaseResolvedAddressSet resolved = await LeaseEgressPolicy.ResolveAsync(
                request.Hostname,
                numericResolver,
                dnsQuestioner,
                setupDeadline.Token).ConfigureAwait(false);
            await using LeaseTcpConnection upstream = await ConnectPinnedAddressSetAsync(
                resolved,
                permitProvider,
                dialer,
                setupDeadline.Token).ConfigureAwait(false);

            responseStarted = true;
            await client.Stream.WriteAsync(
                "HTTP/1.1 200 Connection Established\r\n\r\n"u8.ToArray(),
                setupDeadline.Token).ConfigureAwait(false);
            await client.Stream.FlushAsync(setupDeadline.Token).ConfigureAwait(false);

            // Keep the caller's cancellation linked, but do not let the setup
            // deadline terminate a tunnel that was already established.
            setupDeadline.CancelAfter(Timeout.InfiniteTimeSpan);
            await RelayAsync(client, upstream, request.EarlyTunnelData, cancellationToken).ConfigureAwait(false);
        }
        catch (TimeoutException)
        {
            if (!responseStarted && !cancellationToken.IsCancellationRequested)
            {
                await TryWriteStatusAsync(client.Stream, 504, "Gateway Timeout").ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            if (!responseStarted)
            {
                await TryWriteStatusAsync(client.Stream, 504, "Gateway Timeout").ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            // Lease shutdown closes both peers below without reflecting details.
        }
        catch (Exception)
        {
            if (!responseStarted)
            {
                await TryWriteStatusAsync(client.Stream, 502, "Bad Gateway").ConfigureAwait(false);
            }
        }
        finally
        {
            try
            {
                await client.DisposeAsync().ConfigureAwait(false);
            }
            catch (Exception)
            {
                // A failed close must not expose peer or endpoint details.
            }
        }
    }

    private static async Task<LeaseTcpConnection> ConnectPinnedAddressSetAsync(
        LeaseResolvedAddressSet resolved,
        ILeaseUpstreamPermitProvider permitProvider,
        ILeaseTcpDialer dialer,
        CancellationToken cancellationToken)
    {
        Exception? lastConnectionFailure = null;
        int attempts = 0;
        foreach (IPAddress address in resolved.Addresses)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (attempts >= MaximumAddressAttempts)
            {
                break;
            }
            attempts++;

            try
            {
                return await LeaseTcpConnector.ConnectAsync(
                    resolved,
                    address,
                    permitProvider,
                    dialer,
                    PerAddressConnectDeadline,
                    cancellationToken).ConfigureAwait(false);
            }
            catch (TimeoutException exception) when (!cancellationToken.IsCancellationRequested)
            {
                lastConnectionFailure = exception;
            }
            catch (SocketException exception) when (!cancellationToken.IsCancellationRequested)
            {
                lastConnectionFailure = exception;
            }
        }

        if (cancellationToken.IsCancellationRequested)
        {
            cancellationToken.ThrowIfCancellationRequested();
        }

        throw new IOException(
            attempts == 0
                ? "The validated DNS pin set contained no connection candidates."
                : "No address in the bounded validated DNS pin set accepted an upstream connection.",
            lastConnectionFailure);
    }

    private static async Task<ConnectRequest> ReadRequestAsync(Stream stream, CancellationToken cancellationToken)
    {
        var received = new List<byte>(4096);
        byte[] readBuffer = new byte[MaximumEarlyTunnelBytes];

        while (received.Count <= MaximumRequestBytes)
        {
            int read = await stream.ReadAsync(readBuffer.AsMemory(), cancellationToken).ConfigureAwait(false);
            if (read == 0)
            {
                throw new ConnectRequestRejectedException();
            }

            for (int index = 0; index < read; index++)
            {
                received.Add(readBuffer[index]);
            }

            int terminator = FindHeaderTerminator(received);
            if (terminator >= 0)
            {
                int headerLength = terminator + 4;
                if (headerLength > MaximumRequestBytes)
                {
                    throw new ConnectRequestRejectedException();
                }

                byte[] header = received.Take(headerLength).ToArray();
                byte[] earlyTunnelData = received.Skip(headerLength).ToArray();
                if (earlyTunnelData.Length > MaximumEarlyTunnelBytes)
                {
                    throw new ConnectRequestRejectedException();
                }

                return ParseRequest(header, earlyTunnelData);
            }

            if (received.Count > MaximumRequestBytes)
            {
                throw new ConnectRequestRejectedException();
            }
        }

        throw new ConnectRequestRejectedException();
    }

    private static int FindHeaderTerminator(IReadOnlyList<byte> bytes)
    {
        for (int index = 0; index <= bytes.Count - 4; index++)
        {
            if (bytes[index] == (byte)'\r'
                && bytes[index + 1] == (byte)'\n'
                && bytes[index + 2] == (byte)'\r'
                && bytes[index + 3] == (byte)'\n')
            {
                return index;
            }
        }
        return -1;
    }

    private static ConnectRequest ParseRequest(byte[] header, byte[] earlyTunnelData)
    {
        for (int index = 0; index < header.Length; index++)
        {
            byte value = header[index];
            if (value > 0x7e
                || value == 0x7f
                || (value < 0x20 && value is not (byte)'\r' and not (byte)'\n' and not (byte)'\t'))
            {
                throw new ConnectRequestRejectedException();
            }
            if (value == (byte)'\r' && (index + 1 >= header.Length || header[index + 1] != (byte)'\n'))
            {
                throw new ConnectRequestRejectedException();
            }
            if (value == (byte)'\n' && (index == 0 || header[index - 1] != (byte)'\r'))
            {
                throw new ConnectRequestRejectedException();
            }
        }

        if (header.Length < 4 || header[^4] != (byte)'\r' || header[^3] != (byte)'\n'
            || header[^2] != (byte)'\r' || header[^1] != (byte)'\n')
        {
            throw new ConnectRequestRejectedException();
        }

        int requestLineEnd = Array.IndexOf(header, (byte)'\r');
        if (requestLineEnd <= 0 || requestLineEnd > MaximumRequestLineBytes
            || requestLineEnd + 1 >= header.Length || header[requestLineEnd + 1] != (byte)'\n')
        {
            throw new ConnectRequestRejectedException();
        }

        string text = Encoding.ASCII.GetString(header, 0, header.Length - 4);
        string[] lines = text.Split("\r\n", StringSplitOptions.None);
        if (lines.Length < 2 || lines[^1].Length == 0 || lines.Length - 1 > MaximumHeaderCount)
        {
            throw new ConnectRequestRejectedException();
        }

        string requestLine = lines[0];
        int firstSpace = requestLine.IndexOf(' ');
        int secondSpace = firstSpace < 0 ? -1 : requestLine.IndexOf(' ', firstSpace + 1);
        if (firstSpace <= 0 || secondSpace <= firstSpace + 1 || requestLine.IndexOf(' ', secondSpace + 1) >= 0
            || !StringComparer.Ordinal.Equals(requestLine[..firstSpace], "CONNECT")
            || !StringComparer.Ordinal.Equals(requestLine[(secondSpace + 1)..], "HTTP/1.1"))
        {
            throw new ConnectRequestRejectedException();
        }

        string authority = requestLine[(firstSpace + 1)..secondSpace];
        string hostname = ParseAuthority(authority);
        string? hostHeader = null;
        bool hasContentLength = false;
        for (int index = 1; index < lines.Length; index++)
        {
            string line = lines[index];
            if (line.Length == 0 || line[0] is ' ' or '\t')
            {
                throw new ConnectRequestRejectedException();
            }

            int colon = line.IndexOf(':');
            if (colon <= 0)
            {
                throw new ConnectRequestRejectedException();
            }

            string fieldName = line[..colon];
            if (fieldName.Any(character => !IsTokenCharacter(character)))
            {
                throw new ConnectRequestRejectedException();
            }

            string fieldValue = line[(colon + 1)..].Trim(' ', '\t');
            if (fieldValue.Any(character => (character < 0x20 && character != '\t') || character == 0x7f))
            {
                throw new ConnectRequestRejectedException();
            }

            if (StringComparer.OrdinalIgnoreCase.Equals(fieldName, "Host"))
            {
                if (hostHeader is not null)
                {
                    throw new ConnectRequestRejectedException();
                }
                hostHeader = fieldValue;
            }
            else if (StringComparer.OrdinalIgnoreCase.Equals(fieldName, "Content-Length"))
            {
                if (hasContentLength || !StringComparer.Ordinal.Equals(fieldValue, "0"))
                {
                    throw new ConnectRequestRejectedException();
                }
                hasContentLength = true;
            }
            else if (StringComparer.OrdinalIgnoreCase.Equals(fieldName, "Transfer-Encoding")
                || StringComparer.OrdinalIgnoreCase.Equals(fieldName, "Proxy-Authorization")
                || StringComparer.OrdinalIgnoreCase.Equals(fieldName, "Expect"))
            {
                throw new ConnectRequestRejectedException();
            }
        }

        if (hostHeader is null || !StringComparer.OrdinalIgnoreCase.Equals(hostHeader, authority))
        {
            throw new ConnectRequestRejectedException();
        }

        return new ConnectRequest(hostname, earlyTunnelData);
    }

    private static string ParseAuthority(string authority)
    {
        int colon = authority.IndexOf(':');
        if (colon <= 0 || colon != authority.LastIndexOf(':')
            || !StringComparer.Ordinal.Equals(authority[(colon + 1)..], "443"))
        {
            throw new ConnectRequestRejectedException();
        }

        string host = authority[..colon];
        if (IPAddress.TryParse(host, out _))
        {
            throw new ConnectRequestRejectedException();
        }

        try
        {
            return LeaseEgressPolicy.NormalizeDnsName(host);
        }
        catch (InvalidOperationException)
        {
            throw new ConnectRequestRejectedException();
        }
    }

    private static bool IsAllowedHostname(string hostname) =>
        ExactHosts.Contains(hostname)
        || AllowedHostSuffixes.Any(suffix =>
            StringComparer.Ordinal.Equals(hostname, suffix[1..])
            || hostname.EndsWith(suffix, StringComparison.Ordinal));

    private static bool IsTokenCharacter(char character) =>
        character is >= 'A' and <= 'Z'
            or >= 'a' and <= 'z'
            or >= '0' and <= '9'
            or '!' or '#' or '$' or '%' or '&' or '\'' or '*' or '+' or '-' or '.' or '^' or '_' or '`' or '|' or '~';

    private static async Task RelayAsync(
        IHttpsConnectPeer client,
        LeaseTcpConnection upstream,
        byte[] earlyTunnelData,
        CancellationToken cancellationToken)
    {
        using var lifetime = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        lifetime.CancelAfter(TunnelLifetime);
        using var idle = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
        idle.CancelAfter(TunnelIdleTimeout);

        long transferredBytes = earlyTunnelData.Length;
        if (transferredBytes > MaximumTunnelBytes)
        {
            throw new IOException("CONNECT tunnel exceeded its byte limit.");
        }

        if (earlyTunnelData.Length > 0)
        {
            await upstream.Stream.WriteAsync(earlyTunnelData, idle.Token).ConfigureAwait(false);
            idle.CancelAfter(TunnelIdleTimeout);
        }

        async Task CopyAsync(Stream source, Stream destination, Action shutdownDestination)
        {
            try
            {
                byte[] buffer = new byte[32 * 1024];
                while (true)
                {
                    int read = await source.ReadAsync(buffer.AsMemory(), idle.Token).ConfigureAwait(false);
                    if (read == 0)
                    {
                        shutdownDestination();
                        return;
                    }

                    if (Interlocked.Add(ref transferredBytes, read) > MaximumTunnelBytes)
                    {
                        throw new IOException("CONNECT tunnel exceeded its byte limit.");
                    }
                    await destination.WriteAsync(buffer.AsMemory(0, read), idle.Token).ConfigureAwait(false);
                    idle.CancelAfter(TunnelIdleTimeout);
                }
            }
            catch
            {
                lifetime.Cancel();
                throw;
            }
        }

        await Task.WhenAll(
            CopyAsync(client.Stream, upstream.Stream, upstream.ShutdownSend),
            CopyAsync(upstream.Stream, client.Stream, client.ShutdownSend)).ConfigureAwait(false);
    }

    private static async Task TryWriteStatusAsync(Stream stream, int statusCode, string reason)
    {
        using var deadline = new CancellationTokenSource(FailureResponseDeadline);
        byte[] response = Encoding.ASCII.GetBytes(
            $"HTTP/1.1 {statusCode} {reason}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n");
        try
        {
            await stream.WriteAsync(response, deadline.Token).ConfigureAwait(false);
            await stream.FlushAsync(deadline.Token).ConfigureAwait(false);
        }
        catch (Exception)
        {
            // The peer is closed by the owner; never log or reflect request data.
        }
    }

    private sealed record ConnectRequest(string Hostname, byte[] EarlyTunnelData);

    private sealed class ConnectRequestRejectedException : Exception { }
}
