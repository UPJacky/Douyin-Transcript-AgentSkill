using System.Buffers.Binary;

namespace DouyinTranscript.CapturePipe;

internal static class PipeFrames
{
    private static readonly byte[] ClientPreamble = "DTP1"u8.ToArray();
    private static readonly byte[] ServerAuthenticationAck = "DTA1"u8.ToArray();

    public static async Task ReadAndValidateClientPreambleAsync(
        Stream stream,
        CancellationToken cancellationToken)
    {
        byte[] preamble = new byte[ClientPreamble.Length];
        await stream.ReadExactlyAsync(preamble, cancellationToken).ConfigureAwait(false);
        if (!preamble.SequenceEqual(ClientPreamble))
        {
            throw new CaptureProtocolException("Named pipe client preamble is invalid.");
        }
    }

    public static async Task WriteClientPreambleAsync(Stream stream, CancellationToken cancellationToken)
    {
        await stream.WriteAsync(ClientPreamble, cancellationToken).ConfigureAwait(false);
        await stream.FlushAsync(cancellationToken).ConfigureAwait(false);
    }

    public static async Task ReadAndValidateServerAuthenticationAckAsync(
        Stream stream,
        CancellationToken cancellationToken)
    {
        byte[] acknowledgment = new byte[ServerAuthenticationAck.Length];
        await stream.ReadExactlyAsync(acknowledgment, cancellationToken).ConfigureAwait(false);
        if (!acknowledgment.SequenceEqual(ServerAuthenticationAck))
        {
            throw new PipeAuthenticationException("The named pipe server did not authenticate the client.");
        }
    }

    public static async Task WriteServerAuthenticationAckAsync(
        Stream stream,
        CancellationToken cancellationToken)
    {
        await stream.WriteAsync(ServerAuthenticationAck, cancellationToken).ConfigureAwait(false);
        await stream.FlushAsync(cancellationToken).ConfigureAwait(false);
    }

    public static async Task<byte[]> ReadFrameAsync(
        Stream stream,
        int maximumBytes,
        CancellationToken cancellationToken)
    {
        byte[] prefix = new byte[sizeof(uint)];
        await stream.ReadExactlyAsync(prefix, cancellationToken).ConfigureAwait(false);
        uint length = BinaryPrimitives.ReadUInt32LittleEndian(prefix);
        if (length is 0 || length > maximumBytes)
        {
            throw new CaptureProtocolException("Named pipe frame length is outside the protocol limit.");
        }
        byte[] frame = new byte[checked((int)length)];
        await stream.ReadExactlyAsync(frame, cancellationToken).ConfigureAwait(false);
        return frame;
    }

    public static async Task WriteFrameAsync(
        Stream stream,
        ReadOnlyMemory<byte> frame,
        int maximumBytes,
        CancellationToken cancellationToken)
    {
        if (frame.Length is < 1 || frame.Length > maximumBytes)
        {
            throw new CaptureProtocolException("Named pipe frame length is outside the protocol limit.");
        }
        byte[] prefix = new byte[sizeof(uint)];
        BinaryPrimitives.WriteUInt32LittleEndian(prefix, checked((uint)frame.Length));
        await stream.WriteAsync(prefix, cancellationToken).ConfigureAwait(false);
        await stream.WriteAsync(frame, cancellationToken).ConfigureAwait(false);
        await stream.FlushAsync(cancellationToken).ConfigureAwait(false);
    }
}
