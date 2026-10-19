using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace DouyinTranscript.CapturePipe;

internal sealed record CaptureRequestEnvelope(
    string RequestId,
    string MessageType,
    string OriginalUrl,
    long? MaxMediaBytes,
    double? MaxMediaDurationSeconds,
    byte[] Frame);

internal sealed record CaptureResponseEnvelope(
    string RequestId,
    string MessageType,
    bool IsSuccess,
    long? ArtifactSizeBytes,
    string? ArtifactSha256);

internal static partial class CaptureProtocol
{
    private static readonly HashSet<string> FailureCodes =
    [
        "INVALID_URL", "UNSUPPORTED_URL", "NETWORK_ERROR", "BROWSER_ISOLATION_UNAVAILABLE",
        "BROWSER_ISOLATION_LOST", "LOGIN_REQUIRED", "CAPTURE_NO_MEDIA", "CAPTURE_TIMEOUT",
        "DOWNLOAD_FAILED", "MEDIA_INVALID", "RESOURCE_LIMIT", "SERVICE_BUSY", "CANCELLED",
        "INTERNAL_ERROR",
    ];

    private static readonly HashSet<string> RetryableCodes =
    ["NETWORK_ERROR", "BROWSER_ISOLATION_LOST", "CAPTURE_TIMEOUT", "DOWNLOAD_FAILED", "SERVICE_BUSY"];

    private static readonly HashSet<string> MediaTypes =
    [
        "audio/aac", "audio/mp4", "audio/mpeg", "audio/ogg", "audio/wav", "audio/webm",
        "audio/x-m4a", "audio/x-wav", "video/mp4", "video/webm", "video/quicktime",
        "video/x-matroska",
    ];

    private static readonly HashSet<string> SourceHosts =
    ["douyin.com", "www.douyin.com", "v.douyin.com"];
    private const string BidiControls = "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069";

    public static CaptureRequestEnvelope ValidateRequest(byte[] frame)
    {
        if (frame.Length is < 1 or > ProtocolLimits.MaxRequestFrameBytes)
        {
            throw new CaptureProtocolException("Request frame length is outside the protocol limit.");
        }

        using JsonDocument document = Parse(frame);
        JsonElement root = document.RootElement;
        if (root.ValueKind != JsonValueKind.Object)
        {
            throw new CaptureProtocolException("Request must be a JSON object.");
        }
        Dictionary<string, JsonElement> top = ReadExactObject(root,
            ["protocol_version", "message_type", "request_id", "original_url"],
            ["limits", "max_short_link_redirects"]);
        if (ReadInt(top["protocol_version"], 1, 1) != ProtocolLimits.ProtocolVersion)
        {
            throw new CaptureProtocolException("Unsupported protocol version.");
        }
        string type = ReadString(top["message_type"], 64);
        string requestId = ReadRequestId(top["request_id"]);
        string url = ReadUrl(top["original_url"]);

        if (type == "capture_request")
        {
            RequireExactKeySet(top, ["protocol_version", "message_type", "request_id", "original_url", "limits"]);
            Dictionary<string, JsonElement> limits = ReadExactObject(top["limits"],
                ["max_media_bytes", "max_media_duration_seconds", "max_short_link_redirects", "max_media_redirects"]);
            long maxMediaBytes = ReadLong(limits["max_media_bytes"], 1, ProtocolLimits.MaxMediaBytes);
            double maxDuration = ReadFiniteNumber(limits["max_media_duration_seconds"], 0, ProtocolLimits.MaxMediaDurationSeconds, exclusiveMinimum: true);
            _ = ReadInt(limits["max_short_link_redirects"], 0, 5);
            _ = ReadInt(limits["max_media_redirects"], 0, 3);
            return new CaptureRequestEnvelope(requestId, type, url, maxMediaBytes, maxDuration, frame);
        }
        if (type == "capture_resolve_request")
        {
            RequireExactKeySet(top, ["protocol_version", "message_type", "request_id", "original_url", "max_short_link_redirects"]);
            _ = ReadInt(top["max_short_link_redirects"], 0, 5);
            return new CaptureRequestEnvelope(requestId, type, url, null, null, frame);
        }
        throw new CaptureProtocolException("Unsupported request type.");
    }

    public static CaptureResponseEnvelope ValidateResponse(byte[] frame, CaptureRequestEnvelope request)
    {
        if (frame.Length is < 1 or > ProtocolLimits.MaxResultFrameBytes)
        {
            throw new CaptureProtocolException("Result frame length is outside the protocol limit.");
        }
        using JsonDocument document = Parse(frame);
        JsonElement root = document.RootElement;
        if (root.ValueKind != JsonValueKind.Object)
        {
            throw new CaptureProtocolException("Result must be a JSON object.");
        }
        Dictionary<string, JsonElement> top = ReadObject(root);
        if (ReadInt(Require(top, "protocol_version"), 1, 1) != ProtocolLimits.ProtocolVersion)
        {
            throw new CaptureProtocolException("Unsupported result version.");
        }
        string expectedType = request.MessageType == "capture_request" ? "capture_result" : "capture_resolve_result";
        if (ReadString(Require(top, "message_type"), 64) != expectedType
            || ReadRequestId(Require(top, "request_id")) != request.RequestId)
        {
            throw new CaptureProtocolException("Result does not match its request.");
        }
        string status = ReadString(Require(top, "status"), 16);
        if (status == "failed")
        {
            RequireExactKeySet(top, ["protocol_version", "message_type", "request_id", "status", "error"]);
            Dictionary<string, JsonElement> failure = ReadExactObject(top["error"], ["code", "retryable"]);
            string code = ReadString(failure["code"], 64);
            if (!FailureCodes.Contains(code)
                || failure["retryable"].ValueKind is not (JsonValueKind.True or JsonValueKind.False)
                || failure["retryable"].GetBoolean() != RetryableCodes.Contains(code))
            {
                throw new CaptureProtocolException("Result failure code is invalid.");
            }
            return new CaptureResponseEnvelope(request.RequestId, expectedType, false, null, null);
        }
        if (status != "resolved" && status != "succeeded")
        {
            throw new CaptureProtocolException("Result status is invalid.");
        }

        if (request.MessageType == "capture_resolve_request")
        {
            if (status != "resolved")
            {
                throw new CaptureProtocolException("Resolve result status is invalid.");
            }
            RequireExactKeySet(top, ["protocol_version", "message_type", "request_id", "status", "video_id"]);
            string videoId = ReadString(top["video_id"], 32);
            if (!VideoIdRegex().IsMatch(videoId))
            {
                throw new CaptureProtocolException("Resolved video ID is invalid.");
            }
            return new CaptureResponseEnvelope(request.RequestId, expectedType, true, null, null);
        }

        if (status != "succeeded")
        {
            throw new CaptureProtocolException("Capture result status is invalid.");
        }
        RequireExactKeySet(top, ["protocol_version", "message_type", "request_id", "status", "video", "media_artifact"]);
        double? videoDuration = ValidateVideo(top["video"]);
        Dictionary<string, JsonElement> artifact = ReadExactObject(top["media_artifact"],
            ["artifact_id", "sha256", "size_bytes", "media_type", "duration_seconds"]);
        _ = ReadRequestId(artifact["artifact_id"]);
        string hash = ReadString(artifact["sha256"], 64);
        if (!Sha256Regex().IsMatch(hash))
        {
            throw new CaptureProtocolException("Artifact digest is invalid.");
        }
        long size = ReadLong(artifact["size_bytes"], 1, ProtocolLimits.MaxMediaBytes);
        double duration = ReadFiniteNumber(artifact["duration_seconds"], 0, ProtocolLimits.MaxMediaDurationSeconds, exclusiveMinimum: true);
        string mediaType = ReadString(artifact["media_type"], 64);
        if (!MediaTypes.Contains(mediaType)
            || size > request.MaxMediaBytes
            || request.MaxMediaDurationSeconds is null
            || duration > request.MaxMediaDurationSeconds.Value
            || (videoDuration is not null && videoDuration.Value > request.MaxMediaDurationSeconds.Value))
        {
            throw new CaptureProtocolException("Artifact exceeds the request limits.");
        }
        return new CaptureResponseEnvelope(request.RequestId, expectedType, true, size, hash);
    }

    public static byte[] CreateFailClosedResult(CaptureRequestEnvelope request)
        => CreateFailureResult(request, "BROWSER_ISOLATION_UNAVAILABLE");

    public static byte[] CreateFailureResult(CaptureRequestEnvelope request, string code)
    {
        if (!FailureCodes.Contains(code))
        {
            throw new ArgumentOutOfRangeException(nameof(code));
        }
        object payload = request.MessageType == "capture_request"
            ? new
            {
                protocol_version = ProtocolLimits.ProtocolVersion,
                message_type = "capture_result",
                request_id = request.RequestId,
                status = "failed",
                error = new { code, retryable = RetryableCodes.Contains(code) },
            }
            : new
            {
                protocol_version = ProtocolLimits.ProtocolVersion,
                message_type = "capture_resolve_result",
                request_id = request.RequestId,
                status = "failed",
                error = new { code, retryable = RetryableCodes.Contains(code) },
            };
        return JsonSerializer.SerializeToUtf8Bytes(payload);
    }

    private static double? ValidateVideo(JsonElement value)
    {
        Dictionary<string, JsonElement> video = ReadExactObject(value,
            ["video_id", "title", "author", "publish_date", "duration_seconds"]);
        string id = ReadString(video["video_id"], 32);
        if (!VideoIdRegex().IsMatch(id))
        {
            throw new CaptureProtocolException("Video ID is invalid.");
        }
        ReadOptionalText(video["title"], 160);
        ReadOptionalText(video["author"], 256);
        ReadOptionalText(video["publish_date"], 128);
        double? duration = null;
        if (video["duration_seconds"].ValueKind != JsonValueKind.Null)
        {
            duration = ReadFiniteNumber(video["duration_seconds"], 0, ProtocolLimits.MaxMediaDurationSeconds, exclusiveMinimum: true);
        }
        return duration;
    }

    private static string ReadUrl(JsonElement value)
    {
        string url = ReadString(value, ProtocolLimits.MaxOriginalUrlUtf8Bytes);
        if (Encoding.UTF8.GetByteCount(url) > ProtocolLimits.MaxOriginalUrlUtf8Bytes
            || url.Contains('\\')
            || HasForbiddenTextCharacter(url, rejectWhitespace: true)
            || HasNonEmptyFragment(url)
            || !Uri.TryCreate(url, UriKind.Absolute, out Uri? uri)
            || uri.Scheme != Uri.UriSchemeHttps
            || uri.Port != 443
            || uri.UserInfo.Length != 0
            || !SourceHosts.Contains(uri.IdnHost.TrimEnd('.').ToLowerInvariant()))
        {
            throw new CaptureProtocolException("Source URL is invalid.");
        }
        return url;
    }

    private static JsonDocument Parse(byte[] frame)
    {
        try
        {
            var document = JsonDocument.Parse(frame, new JsonDocumentOptions
            {
                AllowTrailingCommas = false,
                CommentHandling = JsonCommentHandling.Disallow,
                MaxDepth = 16,
            });
            return document;
        }
        catch (JsonException)
        {
            throw new CaptureProtocolException("Frame is not valid JSON.");
        }
    }

    private static Dictionary<string, JsonElement> ReadExactObject(JsonElement value, string[] required, string[]? optional = null)
    {
        Dictionary<string, JsonElement> result = ReadObject(value);
        HashSet<string> allowed = required.Concat(optional ?? []).ToHashSet(StringComparer.Ordinal);
        if (required.Any(name => !result.ContainsKey(name)) || result.Keys.Any(name => !allowed.Contains(name)))
        {
            throw new CaptureProtocolException("JSON object fields do not match the protocol.");
        }
        return result;
    }

    private static Dictionary<string, JsonElement> ReadObject(JsonElement value)
    {
        if (value.ValueKind != JsonValueKind.Object)
        {
            throw new CaptureProtocolException("Expected a JSON object.");
        }
        var result = new Dictionary<string, JsonElement>(StringComparer.Ordinal);
        foreach (JsonProperty property in value.EnumerateObject())
        {
            if (!result.TryAdd(property.Name, property.Value))
            {
                throw new CaptureProtocolException("Duplicate JSON field.");
            }
        }
        return result;
    }

    private static void RequireExactKeySet(Dictionary<string, JsonElement> values, string[] keys)
    {
        if (values.Count != keys.Length || keys.Any(key => !values.ContainsKey(key)))
        {
            throw new CaptureProtocolException("JSON object fields do not match the protocol.");
        }
    }

    private static JsonElement Require(Dictionary<string, JsonElement> values, string name) =>
        values.TryGetValue(name, out JsonElement value)
            ? value
            : throw new CaptureProtocolException("Required JSON field is missing.");

    private static int ReadInt(JsonElement value, int minimum, int maximum)
    {
        if (value.ValueKind != JsonValueKind.Number || !value.TryGetInt32(out int number) || number < minimum || number > maximum)
        {
            throw new CaptureProtocolException("Integer value is outside the protocol limit.");
        }
        return number;
    }

    private static long ReadLong(JsonElement value, long minimum, long maximum)
    {
        if (value.ValueKind != JsonValueKind.Number || !value.TryGetInt64(out long number) || number < minimum || number > maximum)
        {
            throw new CaptureProtocolException("Integer value is outside the protocol limit.");
        }
        return number;
    }

    private static double ReadFiniteNumber(JsonElement value, double minimum, double maximum, bool exclusiveMinimum = false)
    {
        if (value.ValueKind != JsonValueKind.Number
            || !value.TryGetDouble(out double number)
            || !double.IsFinite(number)
            || (exclusiveMinimum ? number <= minimum : number < minimum)
            || number > maximum)
        {
            throw new CaptureProtocolException("Numeric value is outside the protocol limit.");
        }
        return number;
    }

    private static string ReadString(JsonElement value, int maxChars)
    {
        if (value.ValueKind != JsonValueKind.String || value.GetString() is not string text || text.Length > maxChars)
        {
            throw new CaptureProtocolException("Text value is outside the protocol limit.");
        }
        return text;
    }

    private static string ReadRequestId(JsonElement value)
    {
        string text = ReadString(value, 36);
        if (!Guid.TryParseExact(text, "D", out Guid id) || id.ToString("D", CultureInfo.InvariantCulture) != text)
        {
            throw new CaptureProtocolException("Request identifier is invalid.");
        }
        return text;
    }

    private static void ReadOptionalText(JsonElement value, int maxChars)
    {
        if (value.ValueKind == JsonValueKind.Null)
        {
            return;
        }
        string text = ReadString(value, maxChars);
        if (HasForbiddenTextCharacter(text, rejectWhitespace: false))
        {
            throw new CaptureProtocolException("Text contains control characters.");
        }
    }

    private static bool HasForbiddenTextCharacter(string value, bool rejectWhitespace)
    {
        for (int index = 0; index < value.Length; index++)
        {
            char character = value[index];
            if (char.IsControl(character)
                || BidiControls.Contains(character)
                || (rejectWhitespace && char.IsWhiteSpace(character)))
            {
                return true;
            }
            if (char.IsHighSurrogate(character))
            {
                if (index + 1 >= value.Length || !char.IsLowSurrogate(value[index + 1]))
                {
                    return true;
                }
                index++;
            }
            else if (char.IsLowSurrogate(character))
            {
                return true;
            }
        }
        return false;
    }

    private static bool HasNonEmptyFragment(string url)
    {
        int fragmentIndex = url.IndexOf('#');
        return fragmentIndex >= 0 && fragmentIndex < url.Length - 1;
    }

    [GeneratedRegex("^[0-9]{1,32}$", RegexOptions.CultureInvariant)]
    private static partial Regex VideoIdRegex();

    [GeneratedRegex("^[0-9a-f]{64}$", RegexOptions.CultureInvariant)]
    private static partial Regex Sha256Regex();
}

internal sealed class CaptureProtocolException(string message) : Exception(message);
