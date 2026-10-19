using System.Buffers.Binary;
using System.Net;
using System.Security.Cryptography;
using System.Text;

namespace DouyinTranscript.CapturePipe;

internal sealed record DnsWireQuery(
    ushort TransactionId,
    byte[] Packet,
    string QuestionName,
    LeaseDnsQuestionType QuestionType);

/// <summary>
/// Bounded DNS wire encoding and parsing for numeric-resolver queries. It does not
/// provide cryptographic DNSSEC validation; the configured resolver remains trusted.
/// </summary>
internal static class DnsWireCodec
{
    public const int MaxMessageBytes = 16 * 1024;

    private const int HeaderLength = 12;
    private const int MaxSectionRecords = LeaseEgressPolicy.MaxAnswersPerResponse;
    private const int MaxTotalSectionRecords = 256;
    private const int MaxCompressionPointers = 16;
    private const ushort InternetClass = 1;
    private const ushort TypeA = 1;
    private const ushort TypeCName = 5;
    private const ushort TypeAaaa = 28;

    public static DnsWireQuery CreateQuery(string hostname, LeaseDnsQuestionType questionType)
    {
        string canonicalHostname = LeaseEgressPolicy.NormalizeDnsName(hostname);
        byte[] transactionBytes = RandomNumberGenerator.GetBytes(sizeof(ushort));
        ushort transactionId = BinaryPrimitives.ReadUInt16BigEndian(transactionBytes);
        using var packet = new MemoryStream();
        byte[] header = new byte[HeaderLength];
        BinaryPrimitives.WriteUInt16BigEndian(header.AsSpan(0, 2), transactionId);
        BinaryPrimitives.WriteUInt16BigEndian(header.AsSpan(2, 2), 0x0100); // recursion desired
        BinaryPrimitives.WriteUInt16BigEndian(header.AsSpan(4, 2), 1); // one question
        packet.Write(header);

        foreach (string label in canonicalHostname.Split('.'))
        {
            byte[] labelBytes = Encoding.ASCII.GetBytes(label);
            packet.WriteByte(checked((byte)labelBytes.Length));
            packet.Write(labelBytes);
        }
        packet.WriteByte(0);

        Span<byte> questionTail = stackalloc byte[4];
        BinaryPrimitives.WriteUInt16BigEndian(questionTail[..2], GetTypeCode(questionType));
        BinaryPrimitives.WriteUInt16BigEndian(questionTail[2..], InternetClass);
        packet.Write(questionTail);

        return new DnsWireQuery(transactionId, packet.ToArray(), canonicalHostname, questionType);
    }

    public static LeaseDnsResponse ParseResponse(ReadOnlySpan<byte> packet, DnsWireQuery query)
    {
        ArgumentNullException.ThrowIfNull(query);
        if (packet.Length is < HeaderLength or > MaxMessageBytes)
        {
            throw new InvalidDataException("DNS message length is outside the accepted bounds.");
        }

        ushort transactionId = BinaryPrimitives.ReadUInt16BigEndian(packet[..2]);
        ushort flags = BinaryPrimitives.ReadUInt16BigEndian(packet.Slice(2, 2));
        ushort questionCount = BinaryPrimitives.ReadUInt16BigEndian(packet.Slice(4, 2));
        ushort answerCount = BinaryPrimitives.ReadUInt16BigEndian(packet.Slice(6, 2));
        ushort authorityCount = BinaryPrimitives.ReadUInt16BigEndian(packet.Slice(8, 2));
        ushort additionalCount = BinaryPrimitives.ReadUInt16BigEndian(packet.Slice(10, 2));
        if (transactionId != query.TransactionId)
        {
            throw new InvalidDataException("DNS response transaction ID does not match the request.");
        }
        if ((flags & 0x8000) == 0 || (flags & 0x7800) != 0)
        {
            throw new InvalidDataException("DNS response is not a standard response message.");
        }
        if (questionCount != 1
            || answerCount > MaxSectionRecords
            || authorityCount > MaxSectionRecords
            || additionalCount > MaxSectionRecords
            || answerCount + authorityCount + additionalCount > MaxTotalSectionRecords)
        {
            throw new InvalidDataException("DNS response section counts exceed the accepted bounds.");
        }

        int offset = HeaderLength;
        var knownNameLabelOffsets = new HashSet<int>();
        string questionName = ReadName(packet, ref offset, packet.Length, knownNameLabelOffsets);
        ushort questionTypeCode = ReadUInt16(packet, ref offset);
        ushort questionClass = ReadUInt16(packet, ref offset);
        if (!StringComparer.OrdinalIgnoreCase.Equals(questionName, query.QuestionName)
            || questionTypeCode != GetTypeCode(query.QuestionType)
            || questionClass != InternetClass)
        {
            throw new InvalidDataException("DNS response question does not match the request.");
        }

        int responseCode = flags & 0x000f;
        bool isTruncated = (flags & 0x0200) != 0;
        if (isTruncated)
        {
            return new LeaseDnsResponse(questionName, query.QuestionType, responseCode, true, []);
        }

        var answers = new List<LeaseDnsRecord>(answerCount);
        int totalRecords = answerCount + authorityCount + additionalCount;
        for (int index = 0; index < totalRecords; index++)
        {
            bool isAnswer = index < answerCount;
            string owner = ReadName(packet, ref offset, packet.Length, knownNameLabelOffsets);
            ushort typeCode = ReadUInt16(packet, ref offset);
            ushort recordClass = ReadUInt16(packet, ref offset);
            uint ttlSeconds = ReadUInt32(packet, ref offset);
            ushort recordLength = ReadUInt16(packet, ref offset);
            EnsureRemaining(packet, offset, recordLength);
            int recordEnd = offset + recordLength;

            if (isAnswer && recordClass == InternetClass)
            {
                switch (typeCode)
                {
                    case TypeA:
                        if (recordLength != 4)
                        {
                            throw new InvalidDataException("DNS A record has an invalid length.");
                        }
                        answers.Add(new LeaseDnsRecord(
                            owner,
                            LeaseDnsRecordType.A,
                            new IPAddress(packet.Slice(offset, 4)).ToString(),
                            ttlSeconds));
                        break;
                    case TypeAaaa:
                        if (recordLength != 16)
                        {
                            throw new InvalidDataException("DNS AAAA record has an invalid length.");
                        }
                        answers.Add(new LeaseDnsRecord(
                            owner,
                            LeaseDnsRecordType.Aaaa,
                            new IPAddress(packet.Slice(offset, 16)).ToString(),
                            ttlSeconds));
                        break;
                    case TypeCName:
                        int targetOffset = offset;
                        string target = ReadName(packet, ref targetOffset, recordEnd, knownNameLabelOffsets);
                        if (targetOffset != recordEnd)
                        {
                            throw new InvalidDataException("DNS CNAME record contains trailing RDATA bytes.");
                        }
                        answers.Add(new LeaseDnsRecord(
                            owner,
                            LeaseDnsRecordType.CName,
                            target,
                            ttlSeconds));
                        break;
                }
            }

            offset = recordEnd;
        }

        if (offset != packet.Length)
        {
            throw new InvalidDataException("DNS response contains unparsed trailing bytes.");
        }
        if (answers.Count > LeaseEgressPolicy.MaxAnswersPerResponse)
        {
            throw new InvalidDataException("DNS response exceeded the answer record limit.");
        }

        return new LeaseDnsResponse(questionName, query.QuestionType, responseCode, false, answers.AsReadOnly());
    }

    private static string ReadName(
        ReadOnlySpan<byte> packet,
        ref int offset,
        int inlineLimit,
        HashSet<int> knownNameLabelOffsets)
    {
        int cursor = offset;
        int consumedOffset = -1;
        int expandedLength = 1;
        int pointerCount = 0;
        bool jumped = false;
        var pointerTargets = new HashSet<int>();
        var thisNameLabelOffsets = new HashSet<int>();
        var labels = new List<string>();

        while (true)
        {
            int currentLimit = jumped ? packet.Length : inlineLimit;
            if (cursor >= currentLimit || cursor >= packet.Length)
            {
                throw new InvalidDataException("DNS name ended before its root label.");
            }

            int labelOffset = cursor;
            byte length = packet[cursor++];
            if (length == 0)
            {
                thisNameLabelOffsets.Add(labelOffset);
                if (!jumped)
                {
                    consumedOffset = cursor;
                }
                break;
            }

            if ((length & 0xc0) == 0xc0)
            {
                if (cursor >= currentLimit || cursor >= packet.Length)
                {
                    throw new InvalidDataException("DNS compression pointer is incomplete.");
                }
                int pointerPosition = cursor - 1;
                int target = ((length & 0x3f) << 8) | packet[cursor++];
                if (target < HeaderLength
                    || target >= pointerPosition
                    || target >= packet.Length
                    || !knownNameLabelOffsets.Contains(target)
                    || !pointerTargets.Add(target))
                {
                    throw new InvalidDataException("DNS compression pointer is not an earlier parsed name-label boundary.");
                }
                thisNameLabelOffsets.Add(labelOffset);
                if (!jumped)
                {
                    consumedOffset = cursor;
                }
                jumped = true;
                pointerCount++;
                if (pointerCount > MaxCompressionPointers)
                {
                    throw new InvalidDataException("DNS name exceeded the compression-pointer limit.");
                }
                cursor = target;
                continue;
            }

            if ((length & 0xc0) != 0)
            {
                throw new InvalidDataException("DNS name uses an unsupported extended label encoding.");
            }
            int labelLength = length;
            thisNameLabelOffsets.Add(labelOffset);
            currentLimit = jumped ? packet.Length : inlineLimit;
            EnsureRemaining(packet[..currentLimit], cursor, labelLength);
            expandedLength = checked(expandedLength + labelLength + 1);
            if (expandedLength > 255)
            {
                throw new InvalidDataException("DNS name exceeds the maximum expanded wire length.");
            }

            ReadOnlySpan<byte> labelBytes = packet.Slice(cursor, labelLength);
            bool invalidLabelByte = false;
            foreach (byte value in labelBytes)
            {
                if (value is < 0x21 or > 0x7e || value == (byte)'.')
                {
                    invalidLabelByte = true;
                    break;
                }
            }
            if (invalidLabelByte)
            {
                throw new InvalidDataException("DNS hostname labels must use visible ASCII without embedded dots.");
            }
            labels.Add(Encoding.ASCII.GetString(labelBytes));
            cursor += labelLength;
        }

        knownNameLabelOffsets.UnionWith(thisNameLabelOffsets);
        offset = consumedOffset;
        return string.Join('.', labels);
    }

    private static ushort GetTypeCode(LeaseDnsQuestionType questionType) => questionType switch
    {
        LeaseDnsQuestionType.A => TypeA,
        LeaseDnsQuestionType.Aaaa => TypeAaaa,
        _ => throw new ArgumentOutOfRangeException(nameof(questionType)),
    };

    private static ushort ReadUInt16(ReadOnlySpan<byte> packet, ref int offset)
    {
        EnsureRemaining(packet, offset, sizeof(ushort));
        ushort value = BinaryPrimitives.ReadUInt16BigEndian(packet.Slice(offset, sizeof(ushort)));
        offset += sizeof(ushort);
        return value;
    }

    private static uint ReadUInt32(ReadOnlySpan<byte> packet, ref int offset)
    {
        EnsureRemaining(packet, offset, sizeof(uint));
        uint value = BinaryPrimitives.ReadUInt32BigEndian(packet.Slice(offset, sizeof(uint)));
        offset += sizeof(uint);
        return value;
    }

    private static void EnsureRemaining(ReadOnlySpan<byte> packet, int offset, int length)
    {
        if (offset < 0 || length < 0 || offset > packet.Length - length)
        {
            throw new InvalidDataException("DNS record is truncated or contains an invalid length.");
        }
    }
}
