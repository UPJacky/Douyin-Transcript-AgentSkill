using System.Net;
using System.Net.Sockets;
using DouyinTranscript.NetworkPolicy;

namespace DouyinTranscript.CapturePipe;

/// <summary>
/// A lease-scoped policy provider must install the exact endpoint permit before
/// the connector opens a socket, and remove it when the returned connection ends.
/// </summary>
internal interface ILeaseUpstreamPermitProvider
{
    ValueTask<IAsyncDisposable> AcquireAsync(IPEndPoint endpoint, CancellationToken cancellationToken);
}

internal interface ILeaseTcpConnectionHandle : IAsyncDisposable
{
    EndPoint? RemoteEndPoint { get; }
    Stream Stream { get; }
    void ShutdownSend();
}

internal interface ILeaseTcpDialer
{
    ValueTask<ILeaseTcpConnectionHandle> ConnectAsync(IPEndPoint endpoint, CancellationToken cancellationToken);
}

/// <summary>
/// Owns one numeric-IP connection and the exact lease permit that authorized it.
/// The caller supplies <see cref="Hostname"/> as TLS SNI/validation name; it is
/// never used for socket resolution.
/// </summary>
internal sealed class LeaseTcpConnection : IAsyncDisposable
{
    private ILeaseTcpConnectionHandle? _connection;
    private IAsyncDisposable? _permit;

    internal LeaseTcpConnection(
        string hostname,
        IPEndPoint endpoint,
        ILeaseTcpConnectionHandle connection,
        IAsyncDisposable permit)
    {
        Hostname = hostname;
        RemoteEndPoint = endpoint;
        _connection = connection;
        _permit = permit;
    }

    public string Hostname { get; }
    public IPEndPoint RemoteEndPoint { get; }

    public Stream Stream => _connection?.Stream
        ?? throw new ObjectDisposedException(nameof(LeaseTcpConnection));

    public void ShutdownSend()
    {
        ILeaseTcpConnectionHandle connection = _connection
            ?? throw new ObjectDisposedException(nameof(LeaseTcpConnection));
        connection.ShutdownSend();
    }

    public async ValueTask DisposeAsync()
    {
        ILeaseTcpConnectionHandle? connection = Interlocked.Exchange(ref _connection, null);
        IAsyncDisposable? permit = Interlocked.Exchange(ref _permit, null);
        try
        {
            if (connection is not null)
            {
                await connection.DisposeAsync().ConfigureAwait(false);
            }
        }
        finally
        {
            if (permit is not null)
            {
                await permit.DisposeAsync().ConfigureAwait(false);
            }
        }
    }
}

/// <summary>
/// Connects only to an address already returned by the lease's validated DNS
/// result. It does not resolve hostnames, follow redirects, or reuse connections.
/// </summary>
internal static class LeaseTcpConnector
{
    private static readonly TimeSpan MaximumConnectDeadline = TimeSpan.FromSeconds(15);

    public static Task<LeaseTcpConnection> ConnectAsync(
        LeaseResolvedAddressSet resolved,
        IPAddress selectedAddress,
        ILeaseUpstreamPermitProvider permitProvider,
        CancellationToken cancellationToken) =>
        ConnectAsync(
            resolved,
            selectedAddress,
            permitProvider,
            new SocketLeaseTcpDialer(),
            MaximumConnectDeadline,
            cancellationToken);

    internal static async Task<LeaseTcpConnection> ConnectAsync(
        LeaseResolvedAddressSet resolved,
        IPAddress selectedAddress,
        ILeaseUpstreamPermitProvider permitProvider,
        ILeaseTcpDialer dialer,
        TimeSpan connectDeadline,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(resolved);
        ArgumentNullException.ThrowIfNull(selectedAddress);
        ArgumentNullException.ThrowIfNull(permitProvider);
        ArgumentNullException.ThrowIfNull(dialer);
        if (connectDeadline <= TimeSpan.Zero || connectDeadline > MaximumConnectDeadline)
        {
            throw new ArgumentOutOfRangeException(
                nameof(connectDeadline),
                "TCP connection deadline must be positive and may not exceed the production limit.");
        }

        string hostname = LeaseEgressPolicy.NormalizeDnsName(resolved.Hostname);
        if (resolved.Addresses is null
            || resolved.Addresses.Count is 0 or > LeaseEgressPolicy.MaxPinnedAddresses
            || resolved.Addresses.Any(address => address is null || !PublicUnicastAddressPolicy.IsPublicUnicast(address))
            || !resolved.Addresses.Contains(selectedAddress))
        {
            throw new InvalidOperationException("The selected endpoint is not in a valid public pinned address set.");
        }

        var endpoint = new IPEndPoint(new IPAddress(selectedAddress.GetAddressBytes()), LeaseEgressPolicy.HttpsPort);
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(connectDeadline);

        IAsyncDisposable? permit = null;
        ILeaseTcpConnectionHandle? connection = null;
        try
        {
            permit = await permitProvider.AcquireAsync(endpoint, deadline.Token).ConfigureAwait(false);
            if (permit is null)
            {
                throw new InvalidOperationException("The lease policy provider returned no endpoint permit.");
            }

            connection = await dialer.ConnectAsync(endpoint, deadline.Token).ConfigureAwait(false);
            if (connection is null)
            {
                throw new InvalidOperationException("The TCP dialer returned no connection.");
            }
            if (connection.RemoteEndPoint is not IPEndPoint actualEndpoint || !actualEndpoint.Equals(endpoint))
            {
                throw new InvalidDataException("TCP connection reached an endpoint outside the pinned lease target.");
            }

            var result = new LeaseTcpConnection(hostname, endpoint, connection, permit);
            connection = null;
            permit = null;
            return result;
        }
        catch (OperationCanceledException exception) when (!cancellationToken.IsCancellationRequested)
        {
            await DisposeFailedAttemptAsync(connection, permit).ConfigureAwait(false);
            throw new TimeoutException("Pinned TCP connection exceeded its deadline.", exception);
        }
        catch
        {
            await DisposeFailedAttemptAsync(connection, permit).ConfigureAwait(false);
            throw;
        }
    }

    private static async ValueTask DisposeFailedAttemptAsync(
        ILeaseTcpConnectionHandle? connection,
        IAsyncDisposable? permit)
    {
        try
        {
            if (connection is not null)
            {
                await connection.DisposeAsync().ConfigureAwait(false);
            }
        }
        finally
        {
            if (permit is not null)
            {
                await permit.DisposeAsync().ConfigureAwait(false);
            }
        }
    }

    private sealed class SocketLeaseTcpDialer : ILeaseTcpDialer
    {
        public async ValueTask<ILeaseTcpConnectionHandle> ConnectAsync(
            IPEndPoint endpoint,
            CancellationToken cancellationToken)
        {
            var socket = new Socket(endpoint.AddressFamily, SocketType.Stream, ProtocolType.Tcp);
            try
            {
                await socket.ConnectAsync(endpoint, cancellationToken).ConfigureAwait(false);
                return new SocketLeaseTcpConnectionHandle(socket);
            }
            catch
            {
                socket.Dispose();
                throw;
            }
        }
    }

    private sealed class SocketLeaseTcpConnectionHandle : ILeaseTcpConnectionHandle
    {
        private readonly Socket _socket;
        private readonly NetworkStream _stream;

        public SocketLeaseTcpConnectionHandle(Socket socket)
        {
            _socket = socket;
            _stream = new NetworkStream(socket, ownsSocket: false);
        }

        public EndPoint? RemoteEndPoint => _socket.RemoteEndPoint;
        public Stream Stream => _stream;

        public void ShutdownSend() => _socket.Shutdown(SocketShutdown.Send);

        public ValueTask DisposeAsync()
        {
            _stream.Dispose();
            _socket.Dispose();
            return ValueTask.CompletedTask;
        }
    }
}
