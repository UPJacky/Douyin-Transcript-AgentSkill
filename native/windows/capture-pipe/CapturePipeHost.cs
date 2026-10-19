using System.IO.Pipes;
using Microsoft.Win32.SafeHandles;

namespace DouyinTranscript.CapturePipe;

internal sealed class CapturePipeHost(
    string pipeName,
    ServicePeerPolicy servicePolicy,
    ClientPeerPolicy clientPolicy,
    ICaptureWorker worker) : ICapturePipeServiceServer
{
    private readonly TaskCompletionSource started = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly SemaphoreSlim captureLease = new(1, 1);

    public Task Started => started.Task;

    public async Task ServeAsync(CancellationToken stoppingToken)
    {
        try
        {
            servicePolicy.ValidateCurrentProcess();
            SafePipeHandle firstInstance = NativeMethods.CreateSecurePipe(
                pipeName,
                clientPolicy.UserSids.ToArray(),
                servicePolicy.NormalizeServiceSid(),
                firstPipeInstance: true);
            var listeners = new Task[ProtocolLimits.MaxConcurrentConnections];
            listeners[0] = ListenLoopAsync(stoppingToken, firstInstance);
            for (int index = 1; index < listeners.Length; index++)
            {
                listeners[index] = ListenLoopAsync(stoppingToken);
            }
            started.TrySetResult();
            await Task.WhenAll(listeners).ConfigureAwait(false);
        }
        catch (Exception exception)
        {
            started.TrySetException(exception);
            throw;
        }
    }

    private async Task ListenLoopAsync(
        CancellationToken stoppingToken,
        SafePipeHandle? firstInstance = null)
    {
        try
        {
            while (!stoppingToken.IsCancellationRequested)
            {
                SafePipeHandle handle;
                try
                {
                    handle = firstInstance ?? NativeMethods.CreateSecurePipe(
                        pipeName,
                        clientPolicy.UserSids.ToArray(),
                        servicePolicy.NormalizeServiceSid(),
                        firstPipeInstance: false);
                    firstInstance = null;
                }
                catch (Exception) when (stoppingToken.IsCancellationRequested)
                {
                    return;
                }

                await using var pipe = new NamedPipeServerStream(
                    PipeDirection.InOut,
                    isAsync: true,
                    isConnected: false,
                    handle);
                try
                {
                    await pipe.WaitForConnectionAsync(stoppingToken).ConfigureAwait(false);
                    await HandleConnectedAsync(pipe, stoppingToken).ConfigureAwait(false);
                }
                catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
                {
                    return;
                }
                catch (IOException)
                {
                    // A peer may disconnect at any I/O boundary. Its pipe instance is closed below.
                }
                catch (CaptureProtocolException)
                {
                    // Malformed or over-limit frames are closed without reflecting attacker input.
                }
                catch (PipeAuthenticationException)
                {
                    // Unauthorized local peers receive no protocol response.
                }
                catch (Exception) when (stoppingToken.IsCancellationRequested)
                {
                    return;
                }
                catch
                {
                    // Handler details may contain URLs or filesystem paths; keep them off the wire/log.
                }
            }
        }
        finally
        {
            firstInstance?.Dispose();
        }
    }

    private async Task HandleConnectedAsync(NamedPipeServerStream pipe, CancellationToken stoppingToken)
    {
        using var preambleDeadline = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
        preambleDeadline.CancelAfter(TimeSpan.FromMilliseconds(ProtocolLimits.ClientPreambleReadMilliseconds));
        await PipeFrames.ReadAndValidateClientPreambleAsync(pipe, preambleDeadline.Token).ConfigureAwait(false);

        // RunAsClient impersonates the peer associated with the most recent server read.
        // Keep this read a fixed non-sensitive preamble; do not read URL-bearing JSON yet.
        PeerIdentity peer = PeerAuthenticator.AuthenticateClient(pipe);
        clientPolicy.Validate(peer);
        await PipeFrames.WriteServerAuthenticationAckAsync(pipe, stoppingToken).ConfigureAwait(false);

        using var requestDeadline = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
        requestDeadline.CancelAfter(TimeSpan.FromSeconds(ProtocolLimits.MaxRequestReadSeconds));
        byte[] requestFrame = await PipeFrames.ReadFrameAsync(
            pipe,
            ProtocolLimits.MaxRequestFrameBytes,
            requestDeadline.Token).ConfigureAwait(false);
        CaptureRequestEnvelope request = CaptureProtocol.ValidateRequest(requestFrame);

        using var operationCancellation = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
        operationCancellation.CancelAfter(TimeSpan.FromSeconds(ProtocolLimits.MaxExchangeSeconds));

        if (!captureLease.Wait(0))
        {
            byte[] busyResult = CaptureProtocol.CreateFailureResult(request, "SERVICE_BUSY");
            await PipeFrames.WriteFrameAsync(
                pipe,
                busyResult,
                ProtocolLimits.MaxResultFrameBytes,
                operationCancellation.Token).ConfigureAwait(false);
            return;
        }

        try
        {
            using var monitorCancellation = new CancellationTokenSource();
            Task disconnectMonitor = MonitorDisconnectAsync(
                pipe.SafePipeHandle,
                operationCancellation,
                monitorCancellation.Token);

            CaptureWorkerResponse response = new(
                CaptureProtocol.CreateFailureResult(request, "INTERNAL_ERROR"),
                ArtifactStream: null);
            try
            {
                try
                {
                    var executionContext = new CaptureExecutionContext(Guid.NewGuid(), peer);
                    response = await worker.HandleAsync(request, executionContext, operationCancellation.Token).ConfigureAwait(false);
                }
                catch (OperationCanceledException) when (operationCancellation.IsCancellationRequested)
                {
                    return;
                }
                catch
                {
                    response = new CaptureWorkerResponse(
                        CaptureProtocol.CreateFailureResult(request, "INTERNAL_ERROR"),
                        ArtifactStream: null);
                }

                CaptureResponseEnvelope result;
                try
                {
                    result = CaptureProtocol.ValidateResponse(response.ResultFrame, request);
                    if (result.ArtifactSizeBytes is long)
                    {
                        if (response.ArtifactStream is null)
                        {
                            throw new CaptureProtocolException("Worker success has no artifact stream.");
                        }
                        await ArtifactTransfer.ValidateSeekableArtifactAsync(
                            response.ArtifactStream,
                            result,
                            operationCancellation.Token).ConfigureAwait(false);
                    }
                    else if (response.ArtifactStream is not null)
                    {
                        throw new CaptureProtocolException("Worker sent artifact bytes without a successful capture.");
                    }
                }
                catch
                {
                    if (response.ArtifactStream is not null)
                    {
                        await response.ArtifactStream.DisposeAsync().ConfigureAwait(false);
                    }
                    response = new CaptureWorkerResponse(
                        CaptureProtocol.CreateFailureResult(request, "INTERNAL_ERROR"),
                        ArtifactStream: null);
                    result = CaptureProtocol.ValidateResponse(response.ResultFrame, request);
                }

                await PipeFrames.WriteFrameAsync(
                    pipe,
                    response.ResultFrame,
                    ProtocolLimits.MaxResultFrameBytes,
                    operationCancellation.Token).ConfigureAwait(false);
                if (response.ArtifactStream is not null && result.ArtifactSizeBytes is long size)
                {
                    await ArtifactTransfer.SendArtifactAsync(
                        response.ArtifactStream,
                        pipe,
                        size,
                        operationCancellation.Token).ConfigureAwait(false);
                }
            }
            finally
            {
                monitorCancellation.Cancel();
                await IgnoreCancellationAsync(disconnectMonitor).ConfigureAwait(false);
                if (response.ArtifactStream is not null)
                {
                    await response.ArtifactStream.DisposeAsync().ConfigureAwait(false);
                }
            }
        }
        finally
        {
            captureLease.Release();
        }
    }

    private static async Task MonitorDisconnectAsync(
        SafePipeHandle pipe,
        CancellationTokenSource operationCancellation,
        CancellationToken monitorCancellation)
    {
        try
        {
            while (!monitorCancellation.IsCancellationRequested)
            {
                if (!NativeMethods.PeekNamedPipe(
                        pipe,
                        IntPtr.Zero,
                        0,
                        IntPtr.Zero,
                        out _,
                        IntPtr.Zero))
                {
                    operationCancellation.Cancel();
                    return;
                }
                await Task.Delay(TimeSpan.FromMilliseconds(100), monitorCancellation).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException) when (monitorCancellation.IsCancellationRequested)
        {
        }
    }

    private static async Task IgnoreCancellationAsync(Task task)
    {
        try
        {
            await task.ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
        }
    }
}
