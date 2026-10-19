using System.Security.Cryptography;
using System.Buffers.Binary;

namespace DouyinTranscript.CapturePipe;

internal sealed record CaptureWorkerResponse(byte[] ResultFrame, Stream? ArtifactStream);

// Constructed only by CapturePipeHost after authenticating and validating the connected peer.
internal sealed record CaptureExecutionContext(Guid OperationId, PeerIdentity AuthenticatedPeer);

internal interface ICaptureWorker
{
    Task<CaptureWorkerResponse> HandleAsync(
        CaptureRequestEnvelope request,
        CaptureExecutionContext executionContext,
        CancellationToken cancellationToken);
}

internal sealed class FailClosedCaptureWorker : ICaptureWorker
{
    public Task<CaptureWorkerResponse> HandleAsync(
        CaptureRequestEnvelope request,
        CaptureExecutionContext executionContext,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return Task.FromResult(new CaptureWorkerResponse(
            CaptureProtocol.CreateFailClosedResult(request),
            ArtifactStream: null));
    }
}

internal static class ArtifactTransfer
{
    public static async Task ValidateSeekableArtifactAsync(
        Stream stream,
        CaptureResponseEnvelope response,
        CancellationToken cancellationToken)
    {
        if (!stream.CanRead || !stream.CanSeek || response.ArtifactSizeBytes is not long expectedSize
            || response.ArtifactSha256 is null)
        {
            throw new CaptureProtocolException("Worker artifact stream is not bounded and seekable.");
        }

        long originalPosition = stream.Position;
        stream.Position = 0;
        using var digest = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        byte[] buffer = new byte[ProtocolLimits.MaxMediaChunkBytes];
        long total = 0;
        while (total < expectedSize)
        {
            cancellationToken.ThrowIfCancellationRequested();
            int count = (int)Math.Min(buffer.Length, expectedSize - total);
            int read = await stream.ReadAsync(buffer.AsMemory(0, count), cancellationToken).ConfigureAwait(false);
            if (read == 0)
            {
                throw new CaptureProtocolException("Worker artifact ended before its declared length.");
            }
            digest.AppendData(buffer, 0, read);
            total += read;
        }
        cancellationToken.ThrowIfCancellationRequested();
        byte[] trailing = new byte[1];
        if (await stream.ReadAsync(trailing, cancellationToken).ConfigureAwait(false) != 0
            || total != expectedSize
            || !CryptographicOperations.FixedTimeEquals(
                digest.GetHashAndReset(),
                Convert.FromHexString(response.ArtifactSha256)))
        {
            throw new CaptureProtocolException("Worker artifact length or digest does not match its descriptor.");
        }
        stream.Position = originalPosition;
    }

    public static async Task SendArtifactAsync(
        Stream source,
        Stream destination,
        long sizeBytes,
        CancellationToken cancellationToken)
    {
        source.Position = 0;
        byte[] buffer = new byte[ProtocolLimits.MaxMediaChunkBytes];
        long remaining = sizeBytes;
        while (remaining > 0)
        {
            cancellationToken.ThrowIfCancellationRequested();
            int requested = (int)Math.Min(buffer.Length, remaining);
            int read = await source.ReadAsync(buffer.AsMemory(0, requested), cancellationToken).ConfigureAwait(false);
            if (read == 0 || read > requested || read > ProtocolLimits.MaxMediaChunkBytes)
            {
                throw new EndOfStreamException("Validated artifact changed during transfer.");
            }
            byte[] lengthPrefix = new byte[sizeof(uint)];
            BinaryPrimitives.WriteUInt32LittleEndian(lengthPrefix, checked((uint)read));
            await destination.WriteAsync(lengthPrefix, cancellationToken).ConfigureAwait(false);
            await destination.WriteAsync(buffer.AsMemory(0, read), cancellationToken).ConfigureAwait(false);
            remaining -= read;
        }
        await destination.WriteAsync(new byte[sizeof(uint)], cancellationToken).ConfigureAwait(false);
        await destination.FlushAsync(cancellationToken).ConfigureAwait(false);
    }

    public static async Task CopyAndValidateArtifactAsync(
        Stream source,
        Stream destination,
        long sizeBytes,
        string sha256,
        CancellationToken cancellationToken)
    {
        if (sizeBytes is < 1 or > ProtocolLimits.MaxMediaBytes)
        {
            throw new CaptureProtocolException("Artifact size is outside the protocol limit.");
        }
        if (sha256.Length != 64 || !sha256.All(Uri.IsHexDigit))
        {
            throw new CaptureProtocolException("Artifact digest is invalid.");
        }

        await using FileStream staged = CreateStagingStream();
        using var digest = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        byte[] buffer = new byte[ProtocolLimits.MaxMediaChunkBytes];
        long remaining = sizeBytes;
        while (remaining > 0)
        {
            cancellationToken.ThrowIfCancellationRequested();
            byte[] lengthPrefix = new byte[sizeof(uint)];
            await source.ReadExactlyAsync(lengthPrefix, cancellationToken).ConfigureAwait(false);
            uint chunkSize = BinaryPrimitives.ReadUInt32LittleEndian(lengthPrefix);
            if (chunkSize is 0 or > ProtocolLimits.MaxMediaChunkBytes || chunkSize > remaining)
            {
                throw new CaptureProtocolException("Artifact chunk size is outside the protocol limit.");
            }
            int read = checked((int)chunkSize);
            await source.ReadExactlyAsync(buffer.AsMemory(0, read), cancellationToken).ConfigureAwait(false);
            digest.AppendData(buffer, 0, read);
            await staged.WriteAsync(buffer.AsMemory(0, read), cancellationToken).ConfigureAwait(false);
            remaining -= read;
        }

        byte[] terminalPrefix = new byte[sizeof(uint)];
        await source.ReadExactlyAsync(terminalPrefix, cancellationToken).ConfigureAwait(false);
        if (BinaryPrimitives.ReadUInt32LittleEndian(terminalPrefix) != 0)
        {
            throw new CaptureProtocolException("Artifact stream has no valid terminal marker.");
        }
        byte[] trailing = new byte[1];
        if (await source.ReadAsync(trailing, cancellationToken).ConfigureAwait(false) != 0)
        {
            throw new CaptureProtocolException("Artifact stream exceeded its declared length.");
        }
        byte[] actualHash = digest.GetHashAndReset();
        byte[] expectedHash = Convert.FromHexString(sha256);
        if (!CryptographicOperations.FixedTimeEquals(actualHash, expectedHash))
        {
            throw new CaptureProtocolException("Artifact stream digest does not match its descriptor.");
        }

        await staged.FlushAsync(cancellationToken).ConfigureAwait(false);
        staged.Position = 0;
        await staged.CopyToAsync(destination, ProtocolLimits.MaxMediaChunkBytes, cancellationToken).ConfigureAwait(false);
        await destination.FlushAsync(cancellationToken).ConfigureAwait(false);
    }

    private static FileStream CreateStagingStream()
    {
        string tempDirectory = Path.GetTempPath();
        for (int attempt = 0; attempt < 8; attempt++)
        {
            string path = Path.Combine(tempDirectory, $"douyin-artifact-{Guid.NewGuid():N}.tmp");
            try
            {
                return new FileStream(path, new FileStreamOptions
                {
                    Mode = FileMode.CreateNew,
                    Access = FileAccess.ReadWrite,
                    Share = FileShare.None,
                    BufferSize = ProtocolLimits.MaxMediaChunkBytes,
                    Options = FileOptions.Asynchronous | FileOptions.DeleteOnClose,
                });
            }
            catch (IOException) when (File.Exists(path))
            {
                // A random-name collision is safe to retry; other I/O failures remain visible.
            }
        }

        throw new IOException("Could not create a private artifact staging file.");
    }
}
