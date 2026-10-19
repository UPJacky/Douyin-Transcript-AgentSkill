using System.Net;
using System.Net.Sockets;
using System.Text;

namespace DouyinTranscript.CapturePipe;

internal static class HttpsConnectTunnelHarness
{
    public static async Task RunAsync()
    {
        await VerifyConnectAndRelayAsync().ConfigureAwait(false);
        await VerifyMalformedRequestsFailBeforeNetworkAsync().ConfigureAwait(false);
        await VerifyDeniedHostFailsBeforeDnsAsync().ConfigureAwait(false);
        await VerifyPrivateDnsAnswerFailsBeforePermitAsync().ConfigureAwait(false);
        await VerifyWrongRemoteEndpointIsDisposedAsync().ConfigureAwait(false);
        await VerifyPinnedAddressFallbackAsync().ConfigureAwait(false);
        await VerifyPinnedAddressAttemptLimitAsync().ConfigureAwait(false);
        Console.WriteLine("PASS bounded HTTPS CONNECT parsing, allowlist, pinned dialing, and relay scenarios");
    }

    private static async Task VerifyConnectAndRelayAsync()
    {
        byte[] clientEarlyData = Encoding.ASCII.GetBytes("client-tls-preface");
        var clientStream = new ScriptedDuplexStream(BuildRequest("www.douyin.com")
            .Concat(clientEarlyData).ToArray());
        var client = new FakePeer(clientStream);
        var order = new List<string>();
        var dns = new FakeDnsQuestioner(IPAddress.Parse("93.184.216.34"));
        var permits = new FakePermitProvider(order);
        var upstreamStream = new ScriptedDuplexStream(Encoding.ASCII.GetBytes("server-tls-bytes"));
        var dialer = new FakeDialer(upstreamStream, order);

        await HttpsConnectTunnel.HandleAsync(
            client,
            IPAddress.Parse("8.8.8.8"),
            dns,
            permits,
            dialer,
            CancellationToken.None).ConfigureAwait(false);

        string response = Encoding.ASCII.GetString(clientStream.Written);
        Assert(response.StartsWith("HTTP/1.1 200 Connection Established\r\n\r\n", StringComparison.Ordinal),
            "a valid allowlisted CONNECT request did not receive 200 after upstream connection");
        byte[] serverBytes = clientStream.Written.Skip(response.IndexOf("\r\n\r\n", StringComparison.Ordinal) + 4).ToArray();
        Assert(serverBytes.SequenceEqual(Encoding.ASCII.GetBytes("server-tls-bytes")),
            "the upstream-to-client byte stream was not relayed unchanged");
        Assert(upstreamStream.Written.SequenceEqual(clientEarlyData),
            "bytes read with the CONNECT header were lost or modified instead of being relayed");
        Assert(dns.Calls.Count == 2 && dns.Calls.All(call => call.Name == "www.douyin.com"),
            "the CONNECT destination was not resolved through the injected numeric DNS questioner");
        Assert(order.SequenceEqual(["permit", "connect"]),
            "the lease endpoint permit was not acquired before dialing");
        Assert(permits.LastPermit?.Disposed == true && dialer.LastConnection?.Disposed == true,
            "the upstream connection and endpoint permit were not released after relay completion");
        Assert(dialer.LastConnection?.SendShutdown == true && client.SendShutdown,
            "the relay did not propagate TCP half-close when each input reached EOF");
        Assert(client.Disposed, "the accepted client peer was not closed after the single CONNECT exchange");
    }

    private static async Task VerifyMalformedRequestsFailBeforeNetworkAsync()
    {
        string validRequest = Encoding.ASCII.GetString(BuildRequest("www.douyin.com"));
        string[] invalidRequests =
        [
            "GET https://www.douyin.com/ HTTP/1.1\r\nHost: www.douyin.com:443\r\n\r\n",
            "CONNECT www.douyin.com:444 HTTP/1.1\r\nHost: www.douyin.com:444\r\n\r\n",
            "CONNECT www.douyin.com:443 HTTP/1.1\r\nHost: www.douyin.com:443\r\nHost: www.douyin.com:443\r\n\r\n",
            "CONNECT www.douyin.com:443 HTTP/1.1\r\nHost: www.douyin.com:443\r\nContent-Length: 1\r\n\r\n",
            "CONNECT www.douyin.com:443 HTTP/1.1\r\nHost: www.douyin.com:443\r\nContent-Length: 0\r\nContent-Length: 0\r\n\r\n",
            "CONNECT www.douyin.com:443 HTTP/1.1\r\nHost: www.douyin.com:443\r\nTransfer-Encoding: chunked\r\n\r\n",
            "CONNECT www.douyin.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n",
            "CONNECT 93.184.216.34:443 HTTP/1.1\r\nHost: 93.184.216.34:443\r\n\r\n",
            validRequest.Replace("\r\nHost:", "\nHost:", StringComparison.Ordinal),
            "CONNECT www.douyin.com:443 HTTP/1.1\r\nHost: www.douyin.com:443\r\n"
                + string.Concat(Enumerable.Range(0, HttpsConnectTunnel.MaximumHeaderCount)
                    .Select(index => $"X-Test-{index}: value\r\n")) + "\r\n",
            "CONNECT www.douyin.com:443 HTTP/1.1\r\nHost: www.douyin.com:443\r\nX-Test: "
                + new string('a', HttpsConnectTunnel.MaximumRequestBytes) + "\r\n\r\n",
        ];

        foreach (string invalidRequest in invalidRequests)
        {
            var stream = new ScriptedDuplexStream(Encoding.ASCII.GetBytes(invalidRequest));
            var client = new FakePeer(stream);
            var order = new List<string>();
            var dns = new FakeDnsQuestioner(IPAddress.Parse("93.184.216.34"));
            var permits = new FakePermitProvider(order);
            var dialer = new FakeDialer(new ScriptedDuplexStream([]), order);

            await HttpsConnectTunnel.HandleAsync(
                client,
                IPAddress.Parse("8.8.8.8"),
                dns,
                permits,
                dialer,
                CancellationToken.None).ConfigureAwait(false);

            string response = Encoding.ASCII.GetString(stream.Written);
            Assert(response.StartsWith("HTTP/1.1 400 Bad Request\r\n", StringComparison.Ordinal),
                "a malformed or unsupported CONNECT request was not rejected with a generic 400");
            Assert(dns.Calls.Count == 0 && permits.LastPermit is null && dialer.LastConnection is null,
                "a malformed CONNECT request reached DNS or upstream network setup");
        }
    }

    private static async Task VerifyDeniedHostFailsBeforeDnsAsync()
    {
        var stream = new ScriptedDuplexStream(BuildRequest("www.douyin.com.evil.example"));
        var client = new FakePeer(stream);
        var order = new List<string>();
        var dns = new FakeDnsQuestioner(IPAddress.Parse("93.184.216.34"));
        var permits = new FakePermitProvider(order);
        var dialer = new FakeDialer(new ScriptedDuplexStream([]), order);

        await HttpsConnectTunnel.HandleAsync(
            client,
            IPAddress.Parse("8.8.8.8"),
            dns,
            permits,
            dialer,
            CancellationToken.None).ConfigureAwait(false);

        Assert(Encoding.ASCII.GetString(stream.Written).StartsWith("HTTP/1.1 403 Forbidden\r\n", StringComparison.Ordinal),
            "a hostname outside the reviewed allowlist was not denied");
        Assert(dns.Calls.Count == 0 && permits.LastPermit is null && dialer.LastConnection is null,
            "a denied hostname reached DNS or upstream network setup");
    }

    private static async Task VerifyPrivateDnsAnswerFailsBeforePermitAsync()
    {
        var stream = new ScriptedDuplexStream(BuildRequest("www.douyin.com"));
        var client = new FakePeer(stream);
        var order = new List<string>();
        var dns = new FakeDnsQuestioner(IPAddress.Loopback);
        var permits = new FakePermitProvider(order);
        var dialer = new FakeDialer(new ScriptedDuplexStream([]), order);

        await HttpsConnectTunnel.HandleAsync(
            client,
            IPAddress.Parse("8.8.8.8"),
            dns,
            permits,
            dialer,
            CancellationToken.None).ConfigureAwait(false);

        Assert(Encoding.ASCII.GetString(stream.Written).StartsWith("HTTP/1.1 502 Bad Gateway\r\n", StringComparison.Ordinal),
            "a DNS policy failure was not mapped to a generic gateway error");
        Assert(permits.LastPermit is null && dialer.LastConnection is null,
            "a non-public DNS answer reached permit or socket setup");
    }

    private static async Task VerifyWrongRemoteEndpointIsDisposedAsync()
    {
        var stream = new ScriptedDuplexStream(BuildRequest("www.douyin.com"));
        var client = new FakePeer(stream);
        var order = new List<string>();
        var dns = new FakeDnsQuestioner(IPAddress.Parse("93.184.216.34"));
        var permits = new FakePermitProvider(order);
        var upstreamStream = new ScriptedDuplexStream([]);
        var dialer = new FakeDialer(upstreamStream, order, IPAddress.Parse("1.1.1.1"));

        await HttpsConnectTunnel.HandleAsync(
            client,
            IPAddress.Parse("8.8.8.8"),
            dns,
            permits,
            dialer,
            CancellationToken.None).ConfigureAwait(false);

        Assert(Encoding.ASCII.GetString(stream.Written).StartsWith("HTTP/1.1 502 Bad Gateway\r\n", StringComparison.Ordinal),
            "a dialer endpoint mismatch did not fail closed");
        Assert(permits.LastPermit?.Disposed == true && dialer.LastConnection?.Disposed == true,
            "a failed endpoint verification did not dispose both the permit and socket");
    }

    private static async Task VerifyPinnedAddressFallbackAsync()
    {
        IPAddress firstAddress = IPAddress.Parse("93.184.216.34");
        IPAddress secondAddress = IPAddress.Parse("93.184.216.35");
        var stream = new ScriptedDuplexStream(BuildRequest("www.douyin.com"));
        var client = new FakePeer(stream);
        var order = new List<string>();
        var dns = new FakeDnsQuestioner(firstAddress, secondAddress);
        var permits = new FakePermitProvider(order);
        var dialer = new FakeDialer(new ScriptedDuplexStream([]), order, failuresBeforeSuccess: 1);

        await HttpsConnectTunnel.HandleAsync(
            client,
            IPAddress.Parse("8.8.8.8"),
            dns,
            permits,
            dialer,
            CancellationToken.None).ConfigureAwait(false);

        Assert(Encoding.ASCII.GetString(stream.Written).StartsWith(
                "HTTP/1.1 200 Connection Established\r\n\r\n", StringComparison.Ordinal),
            "a connection failure to the first pinned address prevented fallback to the second");
        Assert(dialer.RequestedEndpoints.Select(endpoint => endpoint.Address)
                .SequenceEqual([firstAddress, secondAddress]),
            "address fallback attempted a destination outside or out of order from the validated DNS pin set");
        Assert(permits.AcquiredEndpoints.SequenceEqual(dialer.RequestedEndpoints)
            && permits.Permits.Count == 2 && permits.Permits.All(permit => permit.Disposed),
            "address fallback did not acquire and release one exact endpoint permit per attempt");
    }

    private static async Task VerifyPinnedAddressAttemptLimitAsync()
    {
        IPAddress[] addresses =
        [
            IPAddress.Parse("93.184.216.34"),
            IPAddress.Parse("93.184.216.35"),
            IPAddress.Parse("93.184.216.36"),
            IPAddress.Parse("93.184.216.37"),
            IPAddress.Parse("93.184.216.38"),
        ];
        var stream = new ScriptedDuplexStream(BuildRequest("www.douyin.com"));
        var client = new FakePeer(stream);
        var order = new List<string>();
        var dns = new FakeDnsQuestioner(addresses);
        var permits = new FakePermitProvider(order);
        var dialer = new FakeDialer(new ScriptedDuplexStream([]), order, failuresBeforeSuccess: int.MaxValue);

        await HttpsConnectTunnel.HandleAsync(
            client,
            IPAddress.Parse("8.8.8.8"),
            dns,
            permits,
            dialer,
            CancellationToken.None).ConfigureAwait(false);

        Assert(Encoding.ASCII.GetString(stream.Written).StartsWith("HTTP/1.1 502 Bad Gateway\r\n", StringComparison.Ordinal),
            "exhausting upstream connection attempts did not fail closed");
        Assert(dialer.RequestedEndpoints.Count == HttpsConnectTunnel.MaximumAddressAttempts,
            "address fallback exceeded its configured attempt limit");
        Assert(permits.Permits.Count == HttpsConnectTunnel.MaximumAddressAttempts
            && permits.Permits.All(permit => permit.Disposed),
            "one or more failed address attempts leaked an endpoint permit");
    }

    private static byte[] BuildRequest(string hostname) => Encoding.ASCII.GetBytes(
        $"CONNECT {hostname}:443 HTTP/1.1\r\nHost: {hostname}:443\r\n\r\n");

    private static void Assert(bool condition, string message)
    {
        if (!condition)
        {
            throw new InvalidOperationException(message);
        }
    }

    private sealed class FakePeer(ScriptedDuplexStream stream) : IHttpsConnectPeer
    {
        public Stream Stream => stream;
        public bool SendShutdown { get; private set; }
        public bool Disposed { get; private set; }

        public void ShutdownSend() => SendShutdown = true;

        public ValueTask DisposeAsync()
        {
            Disposed = true;
            return stream.DisposeAsync();
        }
    }

    private sealed class FakeDnsQuestioner(params IPAddress[] addresses) : INumericDnsQuestioner
    {
        public List<(string Name, LeaseDnsQuestionType Type)> Calls { get; } = [];

        public ValueTask<LeaseDnsResponse> QueryAsync(
            IPAddress resolver,
            int port,
            string questionName,
            LeaseDnsQuestionType questionType,
            CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Calls.Add((questionName, questionType));
            IReadOnlyList<LeaseDnsRecord> answers = questionType == LeaseDnsQuestionType.A
                ? addresses.Select(address => new LeaseDnsRecord(
                    questionName,
                    LeaseDnsRecordType.A,
                    address.ToString(),
                    60)).ToArray()
                : [];
            return ValueTask.FromResult(new LeaseDnsResponse(
                questionName,
                questionType,
                ResponseCode: 0,
                IsTruncated: false,
                answers,
                ReceivedAtTimestamp: System.Diagnostics.Stopwatch.GetTimestamp()));
        }
    }

    private sealed class FakePermitProvider(List<string> order) : ILeaseUpstreamPermitProvider
    {
        public FakePermit? LastPermit { get; private set; }
        public List<IPEndPoint> AcquiredEndpoints { get; } = [];
        public List<FakePermit> Permits { get; } = [];

        public ValueTask<IAsyncDisposable> AcquireAsync(IPEndPoint endpoint, CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            order.Add("permit");
            AcquiredEndpoints.Add(new IPEndPoint(endpoint.Address, endpoint.Port));
            LastPermit = new FakePermit();
            Permits.Add(LastPermit);
            return ValueTask.FromResult<IAsyncDisposable>(LastPermit);
        }
    }

    private sealed class FakePermit : IAsyncDisposable
    {
        public bool Disposed { get; private set; }

        public ValueTask DisposeAsync()
        {
            Disposed = true;
            return ValueTask.CompletedTask;
        }
    }

    private sealed class FakeDialer(
        ScriptedDuplexStream stream,
        List<string> order,
        IPAddress? remoteAddress = null,
        int failuresBeforeSuccess = 0) : ILeaseTcpDialer
    {
        private int _failuresRemaining = failuresBeforeSuccess;
        public FakeConnection? LastConnection { get; private set; }
        public List<IPEndPoint> RequestedEndpoints { get; } = [];

        public ValueTask<ILeaseTcpConnectionHandle> ConnectAsync(
            IPEndPoint endpoint,
            CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            order.Add("connect");
            RequestedEndpoints.Add(new IPEndPoint(endpoint.Address, endpoint.Port));
            if (_failuresRemaining > 0)
            {
                _failuresRemaining--;
                throw new SocketException((int)SocketError.ConnectionRefused);
            }
            LastConnection = new FakeConnection(
                new IPEndPoint(remoteAddress ?? endpoint.Address, endpoint.Port),
                stream);
            return ValueTask.FromResult<ILeaseTcpConnectionHandle>(LastConnection);
        }
    }

    private sealed class FakeConnection(EndPoint remoteEndPoint, ScriptedDuplexStream stream) : ILeaseTcpConnectionHandle
    {
        public EndPoint? RemoteEndPoint { get; } = remoteEndPoint;
        public Stream Stream => stream;
        public bool SendShutdown { get; private set; }
        public bool Disposed { get; private set; }

        public void ShutdownSend() => SendShutdown = true;

        public ValueTask DisposeAsync()
        {
            Disposed = true;
            return stream.DisposeAsync();
        }
    }

    private sealed class ScriptedDuplexStream(byte[] input) : Stream
    {
        private readonly MemoryStream _written = new();
        private int _position;

        public byte[] Written => _written.ToArray();
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => true;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }

        public override int Read(byte[] buffer, int offset, int count)
        {
            int read = Math.Min(count, input.Length - _position);
            Array.Copy(input, _position, buffer, offset, read);
            _position += read;
            return read;
        }

        public override ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            int read = Math.Min(buffer.Length, input.Length - _position);
            input.AsMemory(_position, read).CopyTo(buffer);
            _position += read;
            return ValueTask.FromResult(read);
        }

        public override void Write(byte[] buffer, int offset, int count) => _written.Write(buffer, offset, count);

        public override ValueTask WriteAsync(ReadOnlyMemory<byte> buffer, CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            _written.Write(buffer.Span);
            return ValueTask.CompletedTask;
        }

        public override void Flush() { }
        public override Task FlushAsync(CancellationToken cancellationToken) => Task.CompletedTask;
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
    }
}
