using System.Security.AccessControl;
using System.Security.Principal;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace DouyinTranscript.CapturePipe;

internal sealed record CaptureServiceConfiguration(IReadOnlyList<string> ClientUserSids)
{
    public const string ServiceName = "DouyinTranscriptCapture";
    public const int SchemaVersion = 1;
    public const int MaxConfigurationBytes = 16 * 1024;
    public const int MaxClientSids = 32;

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = false,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        MaxDepth = 8,
    };

    public static string DefaultConfigurationPath
    {
        get
        {
            string commonData = Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData);
            if (string.IsNullOrWhiteSpace(commonData))
            {
                throw new InvalidOperationException("The common application data directory is unavailable.");
            }
            return Path.Combine(commonData, "OpenAI", "DouyinTranscript", "service.json");
        }
    }

    public static CaptureServiceConfiguration LoadDefault()
    {
        if (!OperatingSystem.IsWindows())
        {
            throw new PlatformNotSupportedException("The capture service is Windows-only.");
        }

        string path = Path.GetFullPath(DefaultConfigurationPath);
        string directory = Path.GetDirectoryName(path)
            ?? throw new InvalidOperationException("The service configuration path has no parent directory.");
        string productDirectory = Path.GetDirectoryName(directory)
            ?? throw new InvalidOperationException("The service configuration path has no product directory.");
        ValidateProtectedDirectory(productDirectory);
        ValidateProtectedDirectory(directory);
        ValidateProtectedFile(path);

        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (stream.Length is <= 0 or > MaxConfigurationBytes)
        {
            throw new InvalidDataException("The service configuration size is outside the allowed range.");
        }
        byte[] bytes = new byte[checked((int)stream.Length)];
        stream.ReadExactly(bytes);
        return Parse(bytes);
    }

    internal static CaptureServiceConfiguration Parse(ReadOnlySpan<byte> utf8Json)
    {
        if (utf8Json.Length is <= 0 or > MaxConfigurationBytes)
        {
            throw new InvalidDataException("The service configuration size is outside the allowed range.");
        }

        byte[] jsonBytes = utf8Json.ToArray();
        using (JsonDocument parsed = JsonDocument.Parse(jsonBytes, new JsonDocumentOptions { MaxDepth = 8 }))
        {
            if (parsed.RootElement.ValueKind != JsonValueKind.Object)
            {
                throw new InvalidDataException("The service configuration must be a JSON object.");
            }
            var propertyNames = new HashSet<string>(StringComparer.Ordinal);
            foreach (JsonProperty property in parsed.RootElement.EnumerateObject())
            {
                if (!propertyNames.Add(property.Name))
                {
                    throw new InvalidDataException("The service configuration contains a duplicate property.");
                }
                if (property.Name is not ("schema_version" or "client_user_sids"))
                {
                    throw new InvalidDataException("The service configuration contains an unknown property.");
                }
            }
        }

        ServiceConfigurationDocument document = JsonSerializer.Deserialize<ServiceConfigurationDocument>(
            jsonBytes,
            JsonOptions)
            ?? throw new InvalidDataException("The service configuration is empty.");
        if (document.SchemaVersion != SchemaVersion
            || document.ClientUserSids is null
            || document.ClientUserSids.Length is < 1 or > MaxClientSids)
        {
            throw new InvalidDataException("The service configuration schema or caller list is invalid.");
        }

        string[] normalized = document.ClientUserSids
            .Select(value => new SecurityIdentifier(value).Value)
            .ToArray();
        if (normalized.Distinct(StringComparer.OrdinalIgnoreCase).Count() != normalized.Length)
        {
            throw new InvalidDataException("The service configuration contains duplicate client SIDs.");
        }
        return new CaptureServiceConfiguration(Array.AsReadOnly(normalized));
    }

    public static string ResolveServiceSid()
    {
        IdentityReference resolved = new NTAccount("NT SERVICE\\" + ServiceName)
            .Translate(typeof(SecurityIdentifier));
        string sid = ((SecurityIdentifier)resolved).Value;
        if (!sid.StartsWith("S-1-5-80-", StringComparison.Ordinal))
        {
            throw new InvalidDataException("The configured SCM service name did not resolve to a service SID.");
        }
        return sid;
    }

    private static void ValidateProtectedDirectory(string path)
    {
        var directory = new DirectoryInfo(path);
        if (!directory.Exists || (directory.Attributes & FileAttributes.ReparsePoint) != 0)
        {
            throw new InvalidDataException("A protected service configuration directory is missing or redirected.");
        }

        DirectorySecurity security = directory.GetAccessControl(AccessControlSections.Owner | AccessControlSections.Access);
        ValidateProtectedAclSddl(security.GetSecurityDescriptorSddlForm(AccessControlSections.Owner | AccessControlSections.Access));
    }

    private static void ValidateProtectedFile(string path)
    {
        var file = new FileInfo(path);
        if (!file.Exists || (file.Attributes & FileAttributes.ReparsePoint) != 0)
        {
            throw new InvalidDataException("The service configuration file is missing or redirected.");
        }

        FileSecurity security = file.GetAccessControl(AccessControlSections.Owner | AccessControlSections.Access);
        ValidateProtectedAclSddl(security.GetSecurityDescriptorSddlForm(AccessControlSections.Owner | AccessControlSections.Access));
    }

    internal static void ValidateProtectedAclSddl(string sddl)
    {
        var descriptor = new RawSecurityDescriptor(sddl);
        if ((descriptor.ControlFlags & ControlFlags.DiscretionaryAclProtected) == 0)
        {
            throw new InvalidDataException("The service configuration ACL must be protected from inheritance.");
        }

        SecurityIdentifier owner = descriptor.Owner
            ?? throw new InvalidDataException("The service configuration has no owner.");
        SecurityIdentifier system = new(WellKnownSidType.LocalSystemSid, null);
        SecurityIdentifier administrators = new(WellKnownSidType.BuiltinAdministratorsSid, null);
        if (!owner.Equals(system) && !owner.Equals(administrators))
        {
            throw new InvalidDataException("The service configuration owner is not trusted.");
        }

        const FileSystemRights mutatingRights = FileSystemRights.Write
            | FileSystemRights.Modify
            | FileSystemRights.Delete
            | FileSystemRights.ChangePermissions
            | FileSystemRights.TakeOwnership
            | FileSystemRights.DeleteSubdirectoriesAndFiles
            | FileSystemRights.WriteData
            | FileSystemRights.AppendData
            | FileSystemRights.CreateDirectories
            | FileSystemRights.CreateFiles
            | FileSystemRights.WriteAttributes
            | FileSystemRights.WriteExtendedAttributes;
        const int genericWrite = unchecked((int)0x40000000);
        const int genericAll = unchecked((int)0x10000000);

        RawAcl dacl = descriptor.DiscretionaryAcl
            ?? throw new InvalidDataException("The service configuration has no discretionary ACL.");
        foreach (GenericAce genericAce in dacl)
        {
            if (genericAce is not QualifiedAce ace
                || ace.AceQualifier != AceQualifier.AccessAllowed
                || (ace.AceFlags & AceFlags.InheritOnly) != 0
                || ((ace.AccessMask & (int)mutatingRights) == 0
                    && (ace.AccessMask & (genericWrite | genericAll)) == 0))
            {
                continue;
            }
            SecurityIdentifier sid = genericAce switch
            {
                CommonAce common => common.SecurityIdentifier,
                ObjectAce objectAce => objectAce.SecurityIdentifier,
                _ => throw new InvalidDataException("The service configuration ACL contains an unsupported allow ACE."),
            };
            if (!sid.Equals(system) && !sid.Equals(administrators))
            {
                throw new InvalidDataException("The service configuration ACL grants write access to an untrusted principal.");
            }
        }
    }

    private sealed class ServiceConfigurationDocument
    {
        [JsonPropertyName("schema_version")]
        public int SchemaVersion { get; init; }

        [JsonPropertyName("client_user_sids")]
        public string[]? ClientUserSids { get; init; }
    }
}
