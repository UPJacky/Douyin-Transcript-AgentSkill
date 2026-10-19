namespace DouyinTranscript.CapturePipe;

internal static class ProtocolLimits
{
    public const int ProtocolVersion = 1;
    public const int MaxRequestFrameBytes = 32 * 1024;
    public const int MaxResultFrameBytes = 16 * 1024;
    public const int MaxOriginalUrlUtf8Bytes = 8 * 1024;
    public const long MaxMediaBytes = 512L * 1024 * 1024;
    public const int MaxMediaChunkBytes = 64 * 1024;
    public const int MaxMediaDurationSeconds = 4 * 60 * 60;
    public const int PipeBufferBytes = 64 * 1024;
    public const int MaxConcurrentConnections = 4;
    public const int ClientPreambleReadMilliseconds = 1_000;
    public const int ServerAuthenticationAckMilliseconds = 5_000;
    public const int MaxRequestReadSeconds = 15;
    public const int MaxExchangeSeconds = 15 * 60;

    public const string PipeName = @"\\.\pipe\DouyinTranscript.Capture.v1";
    public const string PipeNameWithoutPrefix = "DouyinTranscript.Capture.v1";
}
