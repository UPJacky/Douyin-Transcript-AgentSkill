using System.Buffers.Binary;
using System.Net;
using System.Net.Sockets;
using System.Diagnostics;

namespace DouyinTranscript.CapturePipe;

internal enum LeaseDnsTransport
{
    Udp,
    Tcp,
}

/// <summary>
/// A lease-bound provider must install a permit for the exact numeric resolver
/// endpoint and transport before DNS socket creation, then remove it after the
/// socket closes. Production implementations must accept only the configured
/// resolver on port 53; this interface intentionally carries no caller lease ID.
/// </summary>
internal interface ILeaseDnsPermitProvider
{
    ValueTask<IAsyncDisposable> AcquireAsync(
        IPEndPoint resolverEndpoint,
        LeaseDnsTransport transport,
        CancellationToken cancellationToken);
}

/// <summary>
/// Queries one explicitly supplied numeric resolver endpoint. Connected sockets
/// constrain response peers; cancellation disposes the socket rather than only
/// abandoning the caller's wait. DNSSEC/cryptographic response validation is not
/// provided, so callers must trust the configured resolver and network path.
/// </summary>
internal sealed class NumericDnsQuestioner : INumericDnsQuestioner
{
    private readonly ILeaseDnsPermitProvider _permitProvider;
    private readonly Func<AddressFamily, UdpClient> _udpClientFactory;
    private readonly Func<AddressFamily, TcpClient> _tcpClientFactory;

    public NumericDnsQuestioner(ILeaseDnsPermitProvider permitProvider)
        : this(permitProvider, static family => new UdpClient(family), static family => new TcpClient(family))
    {
    }

    internal NumericDnsQuestioner(
        ILeaseDnsPermitProvider permitProvider,
        Func<AddressFamily, UdpClient> udpClientFactory,
        Func<AddressFamily, TcpClient> tcpClientFactory)
    {
        _permitProvider = permitProvider ?? throw new ArgumentNullException(nameof(permitProvider));
        _udpClientFactory = udpClientFactory ?? throw new ArgumentNullException(nameof(udpClientFactory));
        _tcpClientFactory = tcpClientFactory ?? throw new ArgumentNullException(nameof(tcpClientFactory));
    }

    public async ValueTask<LeaseDnsResponse> QueryAsync(
        IPAddress resolver,
        int port,
        string questionName,
        LeaseDnsQuestionType questionType,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(resolver);
        if (port is < IPEndPoint.MinPort or > IPEndPoint.MaxPort)
        {
            throw new ArgumentOutOfRangeException(nameof(port));
        }
        cancellationToken.ThrowIfCancellationRequested();

        var endpoint = new IPEndPoint(resolver, port);
        DnsWireQuery query = DnsWireCodec.CreateQuery(questionName, questionType);
        byte[] responseBytes = await QueryUdpAsync(endpoint, query, cancellationToken).ConfigureAwait(false);
        LeaseDnsResponse response = DnsWireCodec.ParseResponse(responseBytes, query) with
        {
            ReceivedAtTimestamp = Stopwatch.GetTimestamp(),
        };
        if (!response.IsTruncated)
        {
            return response;
        }

        return await QueryTcpAsync(endpoint, query, cancellationToken).ConfigureAwait(false);
    }

    private async Task<byte[]> QueryUdpAsync(
        IPEndPoint endpoint,
        DnsWireQuery query,
        CancellationToken cancellationToken)
    {
        await using IAsyncDisposable permit = await AcquirePermitAsync(
            endpoint,
            LeaseDnsTransport.Udp,
            cancellationToken).ConfigureAwait(false);
        using UdpClient client = _udpClientFactory(endpoint.AddressFamily);
        client.Connect(endpoint);
        using CancellationTokenRegistration cancellation = cancellationToken.Register(
            static state => ((UdpClient)state!).Dispose(),
            client);

        try
        {
            int sent = await client.SendAsync(query.Packet, cancellationToken).ConfigureAwait(false);
            if (sent != query.Packet.Length)
            {
                throw new IOException("DNS UDP query was not sent in full.");
            }

            UdpReceiveResult received = await client.ReceiveAsync(cancellationToken).ConfigureAwait(false);
            if (!received.RemoteEndPoint.Equals(endpoint))
            {
                throw new InvalidDataException("DNS UDP response came from an unexpected endpoint.");
            }
            if (received.Buffer.Length > DnsWireCodec.MaxMessageBytes)
            {
                throw new InvalidDataException("DNS UDP response exceeded the wire-message limit.");
            }
            return received.Buffer;
        }
        catch (ObjectDisposedException exception) when (cancellationToken.IsCancellationRequested)
        {
            throw new OperationCanceledException("DNS UDP query was cancelled.", exception, cancellationToken);
        }
        catch (SocketException exception) when (cancellationToken.IsCancellationRequested)
        {
            throw new OperationCanceledException("DNS UDP query was cancelled.", exception, cancellationToken);
        }
    }

    private async Task<LeaseDnsResponse> QueryTcpAsync(
        IPEndPoint endpoint,
        DnsWireQuery query,
        CancellationToken cancellationToken)
    {
        await using IAsyncDisposable permit = await AcquirePermitAsync(
            endpoint,
            LeaseDnsTransport.Tcp,
            cancellationToken).ConfigureAwait(false);
        using TcpClient client = _tcpClientFactory(endpoint.AddressFamily);
        using CancellationTokenRegistration cancellation = cancellationToken.Register(
            static state => ((TcpClient)state!).Dispose(),
            client);

        try
        {
            await client.ConnectAsync(endpoint, cancellationToken).ConfigureAwait(false);
            if (client.Client.RemoteEndPoint is not IPEndPoint connectedEndpoint || !connectedEndpoint.Equals(endpoint))
            {
                throw new InvalidDataException("DNS TCP connection reached an unexpected endpoint.");
            }

            NetworkStream stream = client.GetStream();
            byte[] requestFrame = new byte[sizeof(ushort) + query.Packet.Length];
            BinaryPrimitives.WriteUInt16BigEndian(requestFrame.AsSpan(0, sizeof(ushort)), checked((ushort)query.Packet.Length));
            query.Packet.CopyTo(requestFrame, sizeof(ushort));
            await stream.WriteAsync(requestFrame, cancellationToken).ConfigureAwait(false);

            byte[] lengthPrefix = new byte[sizeof(ushort)];
            await stream.ReadExactlyAsync(lengthPrefix, cancellationToken).ConfigureAwait(false);
            int responseLength = BinaryPrimitives.ReadUInt16BigEndian(lengthPrefix);
            if (responseLength is < 12 or > DnsWireCodec.MaxMessageBytes)
            {
                throw new InvalidDataException("DNS TCP response length is outside the accepted bounds.");
            }

            byte[] responseBytes = new byte[responseLength];
            await stream.ReadExactlyAsync(responseBytes, cancellationToken).ConfigureAwait(false);
            return DnsWireCodec.ParseResponse(responseBytes, query);
        }
        catch (ObjectDisposedException exception) when (cancellationToken.IsCancellationRequested)
        {
            throw new OperationCanceledException("DNS TCP query was cancelled.", exception, cancellationToken);
        }
        catch (SocketException exception) when (cancellationToken.IsCancellationRequested)
        {
            throw new OperationCanceledException("DNS TCP query was cancelled.", exception, cancellationToken);
        }
        catch (IOException exception) when (cancellationToken.IsCancellationRequested)
        {
            throw new OperationCanceledException("DNS TCP query was cancelled.", exception, cancellationToken);
        }
    }

    private async ValueTask<IAsyncDisposable> AcquirePermitAsync(
        IPEndPoint endpoint,
        LeaseDnsTransport transport,
        CancellationToken cancellationToken)
    {
        IAsyncDisposable permit = await _permitProvider.AcquireAsync(
            endpoint,
            transport,
            cancellationToken).ConfigureAwait(false);
        return permit ?? throw new InvalidOperationException("Lease DNS permit provider returned no permit.");
    }
}
