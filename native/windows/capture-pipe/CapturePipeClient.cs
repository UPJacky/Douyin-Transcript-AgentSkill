using System.IO.Pipes;
using System.Security.Principal;

namespace DouyinTranscript.CapturePipe;

internal sealed class CapturePipeClient(ServicePeerPolicy expectedServer, string pipeNameWithoutPrefix)
{
    public async Task<PipeCaptureExchange> ExchangeAsync(byte[] requestFrame, CancellationToken cancellationToken)
    {
        CaptureRequestEnvelope request = CaptureProtocol.ValidateRequest(requestFrame);
        long deadlineTick = Environment.TickCount64 + (long)ProtocolLimits.MaxExchangeSeconds * 1000;
        using var exchangeDeadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        exchangeDeadline.CancelAfter(TimeSpan.FromSeconds(ProtocolLimits.MaxExchangeSeconds));
        CancellationToken exchangeToken = exchangeDeadline.Token;
        var pipe = new NamedPipeClientStream(
            ".",
            pipeNameWithoutPrefix,
            PipeDirection.InOut,
            PipeOptions.Asynchronous,
            TokenImpersonationLevel.Identification);

        try
        {
            await pipe.ConnectAsync(5_000, exchangeToken).ConfigureAwait(false);
            _ = PeerAuthenticator.AuthenticateServer(pipe, expectedServer);
            await PipeFrames.WriteClientPreambleAsync(pipe, exchangeToken).ConfigureAwait(false);
            using (var authenticationAckDeadline = CancellationTokenSource.CreateLinkedTokenSource(exchangeToken))
            {
                authenticationAckDeadline.CancelAfter(
                    TimeSpan.FromMilliseconds(ProtocolLimits.ServerAuthenticationAckMilliseconds));
                await PipeFrames.ReadAndValidateServerAuthenticationAckAsync(
                    pipe,
                    authenticationAckDeadline.Token).ConfigureAwait(false);
            }
            await PipeFrames.WriteFrameAsync(
                pipe,
                requestFrame,
                ProtocolLimits.MaxRequestFrameBytes,
                exchangeToken).ConfigureAwait(false);
            byte[] resultFrame = await PipeFrames.ReadFrameAsync(
                pipe,
                ProtocolLimits.MaxResultFrameBytes,
                exchangeToken).ConfigureAwait(false);
            CaptureResponseEnvelope response = CaptureProtocol.ValidateResponse(resultFrame, request);
            if (response.ArtifactSizeBytes is null)
            {
                byte[] trailing = new byte[1];
                if (await pipe.ReadAsync(trailing, exchangeToken).ConfigureAwait(false) != 0)
                {
                    throw new CaptureProtocolException("A response without media included trailing bytes.");
                }
            }
            return new PipeCaptureExchange(pipe, resultFrame, response, deadlineTick);
        }
        catch
        {
            await pipe.DisposeAsync().ConfigureAwait(false);
            throw;
        }
    }
}

internal sealed class PipeCaptureExchange(
    NamedPipeClientStream pipe,
    byte[] resultFrame,
    CaptureResponseEnvelope response,
    long deadlineTick) : IAsyncDisposable
{
    private int disposed;

    public byte[] ResultFrame { get; } = resultFrame;
    public CaptureResponseEnvelope Response { get; } = response;

    public async Task CopyArtifactToAsync(Stream destination, CancellationToken cancellationToken)
    {
        ObjectDisposedException.ThrowIf(Volatile.Read(ref disposed) != 0, this);
        if (Response.ArtifactSizeBytes is not long size || Response.ArtifactSha256 is not string sha256)
        {
            throw new InvalidOperationException("This response has no media artifact.");
        }
        if (!destination.CanWrite)
        {
            throw new ArgumentException("The artifact destination must be writable.", nameof(destination));
        }
        long remainingMs = deadlineTick - Environment.TickCount64;
        if (remainingMs <= 0)
        {
            throw new OperationCanceledException("The named pipe exchange exceeded its deadline.");
        }
        using var copyDeadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        copyDeadline.CancelAfter(TimeSpan.FromMilliseconds(remainingMs));
        await ArtifactTransfer.CopyAndValidateArtifactAsync(
            pipe,
            destination,
            size,
            sha256,
            copyDeadline.Token).ConfigureAwait(false);
    }

    public async ValueTask DisposeAsync()
    {
        if (Interlocked.Exchange(ref disposed, 1) == 0)
        {
            await pipe.DisposeAsync().ConfigureAwait(false);
        }
    }
}
