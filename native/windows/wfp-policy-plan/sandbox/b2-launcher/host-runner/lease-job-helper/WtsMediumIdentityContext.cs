using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text;
using Microsoft.Win32;
using Microsoft.Win32.SafeHandles;

namespace DouyinTranscript.LeaseJobHelper;

/// <summary>
/// Creates a disposable, filtered derivative of the already logged-on WTS
/// Session 1 token. This context never loads/unloads a profile or changes ACLs.
/// </summary>
internal sealed class WtsMediumIdentityContext : ITargetProcessIdentity, IDisposable
{
    private static readonly string[] CheckedBuiltinElevatedAliasSids =
    [
        "S-1-5-32-544", // BUILTIN\Administrators
        "S-1-5-32-548", // Account Operators
        "S-1-5-32-549", // Server Operators
        "S-1-5-32-550", // Print Operators
        "S-1-5-32-551", // Backup Operators
        "S-1-5-32-552", // Replicator
        "S-1-5-32-547", // Power Users
        "S-1-5-114",    // Local account and member of Administrators
    ];

    private SafeAccessTokenHandle? _sourceToken;
    private SafeAccessTokenHandle? _token;
    private IntPtr _environment;
    private bool _disposed;
    private string _tempDirectory = string.Empty;
    private string _profileDirectory = string.Empty;
    private (uint Volume, ulong Index)? _workDirectoryIdentity;

    public SafeAccessTokenHandle Token => _token is { IsInvalid: false, IsClosed: false }
        ? _token
        : throw new InvalidOperationException("The WTS filtered token is not initialized.");
    public IntPtr Environment => _environment != IntPtr.Zero
        ? _environment
        : throw new InvalidOperationException("The WTS token environment is not initialized.");
    public string UserSid { get; private set; } = string.Empty;
    public string LogonSid { get; private set; } = string.Empty;
    public int SessionId { get; private set; }
    public Dictionary<string, object?>? LastIdentityReport { get; private set; }
    internal string ProfileDirectory => _profileDirectory;
    internal string TempDirectory => _tempDirectory;
    internal string? WorkDirectory { get; private set; }
    internal string EnvironmentCleanupStatus { get; private set; } = "not_created";
    internal bool TokenHandlesClosed { get; private set; }

    internal Dictionary<string, object?> Initialize()
    {
        string? helperSid = WindowsIdentity.GetCurrent().User?.Value;
        var report = new Dictionary<string, object?>
        {
            ["source"] = "WTSQueryUserToken(Session 1) for a verified local SAM account, then CreateRestrictedToken(DISABLE_MAX_PRIVILEGE, disable the explicitly listed built-in elevated aliases); no SidsToRestrict",
            ["helper_sid"] = helperSid,
            ["helper_is_local_system"] = helperSid == "S-1-5-18",
            ["required_privilege"] = "SeTcbPrivilege",
            ["requested_session_id"] = 1,
            ["wts_session_1_active"] = false,
            ["target_session_is_interactive"] = false,
            ["target_session_id"] = null,
            ["desktop"] = new Dictionary<string, object?>
            {
                ["requested_lpDesktop"] = TargetProcessLauncher.InteractiveDefaultDesktop,
                ["selection"] = "WTS Session 1 with explicit WinSta0\\Default; no station/desktop ACL changes",
                ["acl_mutated"] = false,
                ["preflight"] = "no guest-written DACL evidence is treated as trusted or used as a gate; final filtered token readback and native User32 station/desktop markers gate the fixture",
            },
            ["source_user_sid"] = null,
            ["source_logon_sid"] = null,
            ["source_session_id"] = null,
            ["source_account_is_local"] = false,
            ["source_account"] = null,
            ["token_filter"] = null,
            ["final_token"] = null,
            ["profile"] = null,
            ["environment"] = null,
            ["scratch_directory"] = null,
            ["profile_loaded_by_helper"] = false,
            ["profile_unloaded_by_helper"] = false,
            ["acl_mutated"] = false,
        };
        LastIdentityReport = report;
        if (helperSid != "S-1-5-18")
        {
            throw new NativeApiException("WtsMedium.Precondition.LocalSystem", NativeMethods.ErrorAccessDenied);
        }

        uint enabledSession = ReadWtsSessionOneState(report);
        if (enabledSession != 1)
        {
            throw new NativeApiException("WtsMedium.Session1NotActive", NativeMethods.ErrorNotFound);
        }
        if (!NativeMethods.WtsQueryUserToken(1, out SafeAccessTokenHandle source))
        {
            throw LastError("WTSQueryUserToken.Session1");
        }
        _sourceToken = source;

        UserSid = ReadTokenSid(_sourceToken, NativeMethods.TokenUser, "WtsSource.TokenUser");
        report["source_user_sid"] = UserSid;
        VerifyLocalSamAccount(UserSid, report);
        LogonSid = ReadLogonSid(_sourceToken, "WtsSource.LogonSid");
        uint sourceSession = ReadTokenUInt32(_sourceToken, NativeMethods.TokenSessionId, "WtsSource.TokenSessionId");
        uint sourceElevation = ReadTokenUInt32(_sourceToken, NativeMethods.TokenElevation, "WtsSource.TokenElevation");
        uint sourceTokenType = ReadTokenUInt32(_sourceToken, NativeMethods.TokenType, "WtsSource.TokenType");
        uint sourceElevationType = ReadTokenUInt32(_sourceToken, NativeMethods.TokenElevationType, "WtsSource.TokenElevationType");
        string sourceIntegritySid = ReadTokenSid(_sourceToken, NativeMethods.TokenIntegrityLevel, "WtsSource.TokenIntegrityLevel");
        report["source_user_sid"] = UserSid;
        report["source_logon_sid"] = LogonSid;
        report["source_session_id"] = sourceSession;
        report["source_token"] = new Dictionary<string, object?>
        {
            ["token_type"] = sourceTokenType,
            ["token_elevation"] = sourceElevation != 0,
            ["token_elevation_type"] = sourceElevationType,
            ["token_elevation_type_accepted"] = sourceElevationType is 1 or 2,
            ["integrity_sid"] = sourceIntegritySid,
        };
        // A default elevation type means the token has no linked token; it does
        // not mean the token is unelevated. Require the independent elevation,
        // high-integrity, primary-token, session, and enabled-Administrators
        // checks below before deriving the filtered diagnostic token.
        if (sourceSession != 1 || sourceElevation != 1 || sourceTokenType != NativeMethods.TokenPrimary
            || sourceElevationType is not (1 or 2) || sourceIntegritySid != "S-1-16-12288")
        {
            throw new NativeApiException("WtsMedium.SourceTokenNotSession1ElevatedAdmin", NativeMethods.ErrorAccessDenied);
        }
        SessionId = 1;
        report["target_session_id"] = SessionId;
        report["target_session_is_interactive"] = true;

        IReadOnlyList<TokenGroup> sourceGroups = ReadGroups(_sourceToken, NativeMethods.TokenGroups, "WtsSource.TokenGroups");
        IReadOnlyList<TokenPrivilege> sourcePrivileges = ReadPrivileges(_sourceToken, "WtsSource.TokenPrivileges");
        report["source_groups"] = sourceGroups.Select(SerializeGroup).ToArray();
        report["source_privileges"] = sourcePrivileges.Select(SerializePrivilege).ToArray();
        TokenGroup? sourceAdministrators = sourceGroups.FirstOrDefault(group => group.Sid == "S-1-5-32-544");
        if (sourceAdministrators is null || (sourceAdministrators.Attributes & NativeMethods.GroupEnabled) == 0)
        {
            throw new NativeApiException("WtsMedium.SourceAdministratorsGroupNotEnabled", NativeMethods.ErrorAccessDenied);
        }
        if (!sourceGroups.Any(group => group.Sid == "S-1-5-32-545" && (group.Attributes & NativeMethods.GroupEnabled) != 0))
        {
            throw new NativeApiException("WtsMedium.SourceUsersGroupNotEnabled", NativeMethods.ErrorAccessDenied);
        }

        List<string> disabledSids = CheckedBuiltinElevatedAliasSids
            .Where(sid => sourceGroups.Any(group => group.Sid == sid))
            .ToList();
        if (!disabledSids.Contains("S-1-5-32-544", StringComparer.Ordinal))
        {
            throw new NativeApiException("WtsMedium.AdministratorsSidMissing", NativeMethods.ErrorAccessDenied);
        }
        SafeAccessTokenHandle? restricted = null;
        try
        {
            CreateFilteredToken(_sourceToken, disabledSids, out restricted);
            if (restricted is null || restricted.IsInvalid || restricted.IsClosed)
            {
                throw new NativeApiException("CreateRestrictedToken.WtsMedium.InvalidHandle", NativeMethods.ErrorAccessDenied);
            }
            if (!NativeMethods.DuplicateTokenEx(restricted, NativeMethods.TokenAllForLaunch | NativeMethods.TokenImpersonateAccess,
                    IntPtr.Zero, NativeMethods.SecurityImpersonation, NativeMethods.TokenPrimary,
                    out SafeAccessTokenHandle primary))
            {
                throw LastError("DuplicateTokenEx.WtsMediumPrimary");
            }
            _token = primary;
        }
        finally
        {
            restricted?.Dispose();
        }

        SetMediumIntegrity(_token);
        Dictionary<string, object?> finalToken = VerifyFinalToken(_sourceToken, _token,
            UserSid, LogonSid, sourceSession);
        report["token_filter"] = new Dictionary<string, object?>
        {
            ["create_restricted_token_flags"] = "DISABLE_MAX_PRIVILEGE",
            ["sids_to_disable"] = disabledSids,
            ["checked_builtin_privileged_alias_sids"] = CheckedBuiltinElevatedAliasSids,
            ["sids_to_restrict_count"] = 0,
            ["privileges_to_delete_count"] = 0,
            ["administrators_deny_only"] = true,
            ["checked_builtin_privileged_alias_enabled_groups_absent"] = true,
            ["all_privileges_disabled_except_change_notify"] = true,
            ["token_is_restricted"] = NativeMethods.IsTokenRestricted(_token),
            ["token_is_restricted_expected"] = false,
        };
        report["final_token"] = finalToken;

        if (!NativeMethods.CreateEnvironmentBlock(out _environment, _token, false))
        {
            throw LastError("CreateEnvironmentBlock.WtsMedium");
        }
        Dictionary<string, string> environment = ReadEnvironment(_environment);
        string profileFromToken = ReadProfileDirectory(_token);
        if (!environment.TryGetValue("USERPROFILE", out string? userProfile)
            || !environment.TryGetValue("TEMP", out string? temp)
            || !environment.TryGetValue("TMP", out string? tmp)
            || !environment.TryGetValue("USERNAME", out string? userName)
            || string.IsNullOrWhiteSpace(userProfile) || string.IsNullOrWhiteSpace(temp)
            || string.IsNullOrWhiteSpace(tmp) || string.IsNullOrWhiteSpace(userName)
            || !string.Equals(Path.GetFullPath(userProfile).TrimEnd('\\'), Path.GetFullPath(profileFromToken).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase)
            || !string.Equals(Path.GetFullPath(temp), Path.GetFullPath(tmp), StringComparison.OrdinalIgnoreCase))
        {
            throw new NativeApiException("WtsMedium.UserEnvironmentMismatch", NativeMethods.ErrorAccessDenied);
        }
        _profileDirectory = Path.GetFullPath(profileFromToken).TrimEnd('\\');
        _tempDirectory = Path.GetFullPath(temp).TrimEnd('\\');
        if (!IsWithin(_tempDirectory, _profileDirectory) || !Directory.Exists(_profileDirectory) || !Directory.Exists(_tempDirectory))
        {
            throw new NativeApiException("WtsMedium.ProfileOrTempDirectoryInvalid", NativeMethods.ErrorAccessDenied);
        }
        EnsurePlainDirectory(_profileDirectory, "WtsMedium.ProfileDirectory.ReparsePoint");
        EnsurePathComponentsPlain(_profileDirectory, "WtsMedium.ProfilePath.ReparsePoint");
        EnsurePathComponentsPlain(_tempDirectory, "WtsMedium.TempPath.ReparsePoint");
        using (RegistryKey? hive = Registry.Users.OpenSubKey(UserSid, writable: false))
        {
            if (hive is null)
            {
                throw new NativeApiException("WtsMedium.ExistingUserProfileHiveNotLoaded", NativeMethods.ErrorNotFound);
            }
        }
        report["profile"] = new Dictionary<string, object?>
        {
            ["path"] = _profileDirectory,
            ["hive_loaded"] = true,
            ["profile_loaded_by_helper"] = false,
            ["profile_unloaded_by_helper"] = false,
        };
        report["environment"] = new Dictionary<string, object?>
        {
            ["created_from_existing_wts_token"] = true,
            ["userprofile_matches_token_profile"] = true,
            ["temp"] = _tempDirectory,
            ["tmp_matches_temp"] = true,
            ["username_present"] = !string.IsNullOrWhiteSpace(userName),
            ["all_required_variables_present"] = true,
        };
        return report;
    }

    internal string CreateWorkDirectory()
    {
        if (WorkDirectory is not null)
        {
            throw new InvalidOperationException("The WTS work leaf has already been allocated.");
        }
        string path = Path.Combine(_tempDirectory, "b2-wts-" + Guid.NewGuid().ToString("D"));
        if (Directory.Exists(path) || File.Exists(path))
        {
            throw new NativeApiException("WtsMedium.WorkDirectoryCollision", NativeMethods.ErrorAlreadyExists);
        }
        try
        {
            WindowsIdentity.RunImpersonated(Token, () =>
            {
                Directory.CreateDirectory(path);
                WorkDirectory = path;
                EnsurePlainDirectory(path, "WtsMedium.WorkDirectory.ReparsePoint");
                _workDirectoryIdentity = ReadDirectoryIdentity(path);
                string markerPath = Path.Combine(path, ".write-check");
                using (var marker = new FileStream(markerPath, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                {
                    marker.WriteByte(0x42);
                    marker.Flush(flushToDisk: true);
                }
                File.Delete(markerPath);
            });
        }
        catch
        {
            // Preserve the leaf path so the caller can remove it after confirming no job started.
            if (Directory.Exists(path)) WorkDirectory = path;
            throw;
        }
        LastIdentityReport!["scratch_directory"] = new Dictionary<string, object?>
        {
            ["path"] = path,
            ["parent"] = _tempDirectory,
            ["created_under_target_impersonation"] = true,
            ["acl_mutated"] = false,
            ["used_for_native_markers_only"] = true,
        };
        return path;
    }

    internal Dictionary<string, object?> CleanupWorkDirectory(bool jobDrained)
    {
        var result = new Dictionary<string, object?>
        {
            ["attempted"] = jobDrained && WorkDirectory is not null,
            ["removed"] = false,
            ["path"] = WorkDirectory,
            ["status"] = WorkDirectory is null ? "not_created" : jobDrained ? "pending" : "preserved; process job drain not proven",
        };
        if (jobDrained && WorkDirectory is not null)
        {
            try
            {
                if (!IsWithin(WorkDirectory, _tempDirectory)
                    || !string.Equals(Path.GetDirectoryName(WorkDirectory), _tempDirectory, StringComparison.OrdinalIgnoreCase)
                    || !Path.GetFileName(WorkDirectory).StartsWith("b2-wts-", StringComparison.OrdinalIgnoreCase)
                    || !Guid.TryParseExact(Path.GetFileName(WorkDirectory)[7..], "D", out _))
                {
                    throw new NativeApiException("WtsMedium.WorkDirectoryCleanup.PathMismatch", NativeMethods.ErrorAccessDenied);
                }
                EnsureNoReparsePoints(WorkDirectory);
                if (_workDirectoryIdentity is null || ReadDirectoryIdentity(WorkDirectory) != _workDirectoryIdentity.Value)
                {
                    throw new NativeApiException("WtsMedium.WorkDirectoryCleanup.IdentityChanged", NativeMethods.ErrorAccessDenied);
                }
                Directory.Delete(WorkDirectory, recursive: true);
                result["removed"] = true;
                result["status"] = "removed after complete job drain";
            }
            catch (Exception exception)
            {
                result["status"] = "failed; " + exception.GetType().Name;
                result["error_type"] = exception.GetType().Name;
            }
        }
        return result;
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        if (_environment != IntPtr.Zero)
        {
            EnvironmentCleanupStatus = NativeMethods.DestroyEnvironmentBlock(_environment) ? "destroyed" : "failed";
            _environment = IntPtr.Zero;
        }
        _token?.Dispose();
        _token = null;
        _sourceToken?.Dispose();
        _sourceToken = null;
        TokenHandlesClosed = true;
    }

    private static uint ReadWtsSessionOneState(Dictionary<string, object?> report)
    {
        if (!NativeMethods.WtsEnumerateSessions(new IntPtr(NativeMethods.WtsCurrentServerHandle), 0, 1,
                out IntPtr sessions, out int count))
        {
            throw LastError("WTSEnumerateSessions.WtsMedium");
        }
        try
        {
            int size = Marshal.SizeOf<NativeMethods.WtsSessionInfo>();
            var observed = new List<Dictionary<string, object?>>();
            int? sessionOneState = null;
            for (int index = 0; index < count; index++)
            {
                NativeMethods.WtsSessionInfo session = Marshal.PtrToStructure<NativeMethods.WtsSessionInfo>(IntPtr.Add(sessions, index * size));
                observed.Add(new Dictionary<string, object?> { ["session_id"] = session.SessionId, ["state"] = session.State });
                if (session.SessionId == 1) sessionOneState = session.State;
            }
            uint activeConsole = NativeMethods.WtsGetActiveConsoleSessionId();
            report["wts_sessions"] = observed;
            report["active_console_session_id"] = activeConsole;
            bool sessionOneActive = sessionOneState == NativeMethods.WtsActive;
            report["wts_session_1_state_active"] = sessionOneActive;
            report["active_console_session_matches_session_1"] = activeConsole == 1;
            // A WSB connect establishes a Remote Desktop Services session. The
            // physical-console ID is diagnostic only and may be 0xFFFFFFFF.
            bool active = sessionOneActive;
            report["wts_session_1_active"] = active;
            return active ? 1u : uint.MaxValue;
        }
        finally
        {
            if (sessions != IntPtr.Zero) NativeMethods.WtsFreeMemory(sessions);
        }
    }

    private static void VerifyLocalSamAccount(string tokenUserSid, Dictionary<string, object?> identityReport)
    {
        identityReport["source_account_is_local"] = false;
        var accountReport = new Dictionary<string, object?>
        {
            ["status"] = "checking",
            ["token_user_sid"] = tokenUserSid,
            ["local_sam_domain_name"] = null,
            ["local_sam_domain_sid"] = null,
            ["resolved_account_name"] = null,
            ["resolved_account_domain"] = null,
            ["resolved_sid_name_use"] = null,
            ["account_domain_sid"] = null,
            ["lookup_account_name"] = null,
            ["round_trip_sid"] = null,
            ["round_trip_sid_exact_match"] = false,
        };
        identityReport["source_account"] = accountReport;

        int result = NativeMethods.NetUserModalsGet(null, 2, out IntPtr buffer);
        if (result != NativeMethods.ErrorSuccess || buffer == IntPtr.Zero)
        {
            throw new NativeApiException("NetUserModalsGet.LocalSamDomain", result == NativeMethods.ErrorSuccess ? 13 : result);
        }
        try
        {
            NativeMethods.UserModalsInfo2 info = Marshal.PtrToStructure<NativeMethods.UserModalsInfo2>(buffer);
            string localSamDomainName = Marshal.PtrToStringUni(info.DomainName)
                ?? throw new NativeApiException("NetUserModalsGet.LocalSamDomainNameMissing", 13);
            if (string.IsNullOrWhiteSpace(localSamDomainName) || info.DomainId == IntPtr.Zero)
            {
                throw new NativeApiException("NetUserModalsGet.LocalSamDomainInvalid", 13);
            }
            string localSamDomainSid = new SecurityIdentifier(info.DomainId).Value;
            accountReport["local_sam_domain_name"] = localSamDomainName;
            accountReport["local_sam_domain_sid"] = localSamDomainSid;

            SecurityIdentifier userSid = new(tokenUserSid);
            string? accountDomainSid = userSid.AccountDomainSid?.Value;
            accountReport["account_domain_sid"] = accountDomainSid;
            bool matchesLocalSamDomain = string.Equals(accountDomainSid, localSamDomainSid, StringComparison.Ordinal)
                && string.Equals(localSamDomainName, System.Environment.MachineName, StringComparison.OrdinalIgnoreCase);
            accountReport["local_sam_domain_sid_matches_token_account_domain_sid"] =
                string.Equals(accountDomainSid, localSamDomainSid, StringComparison.Ordinal);
            accountReport["local_sam_domain_name_matches_machine_name"] =
                string.Equals(localSamDomainName, System.Environment.MachineName, StringComparison.OrdinalIgnoreCase);
            if (!matchesLocalSamDomain)
            {
                accountReport["status"] = "fail; token SID is outside this workstation's local SAM domain";
                throw new NativeApiException("WtsSource.AccountIsNotLocalSamUser", NativeMethods.ErrorAccessDenied);
            }
            (string accountName, string accountDomain, int accountUse) = LookupAccountForSid(tokenUserSid, "WtsSource.LookupAccountSid");
            accountReport["resolved_account_name"] = accountName;
            accountReport["resolved_account_domain"] = accountDomain;
            accountReport["resolved_sid_name_use"] = accountUse;

            string accountLookupName = $"{localSamDomainName}\\{accountName}";
            (string roundTripSid, string roundTripDomain, int roundTripUse) = LookupSidForAccount(accountLookupName, "WtsSource.LookupAccountName");
            bool roundTripSidMatches = string.Equals(roundTripSid, userSid.Value, StringComparison.Ordinal);
            bool localSamMatch = string.Equals(accountDomainSid, localSamDomainSid, StringComparison.Ordinal)
                && string.Equals(accountDomain, localSamDomainName, StringComparison.OrdinalIgnoreCase)
                && string.Equals(roundTripDomain, localSamDomainName, StringComparison.OrdinalIgnoreCase)
                && roundTripSidMatches && accountUse == NativeMethods.SidTypeUser && roundTripUse == NativeMethods.SidTypeUser;
            accountReport["lookup_account_name"] = accountLookupName;
            accountReport["round_trip_domain"] = roundTripDomain;
            accountReport["round_trip_sid"] = roundTripSid;
            accountReport["round_trip_sid_name_use"] = roundTripUse;
            accountReport["round_trip_sid_exact_match"] = roundTripSidMatches;
            accountReport["status"] = localSamMatch ? "pass" : "fail; token SID did not resolve and round-trip through the local SAM";
            if (!localSamMatch)
            {
                throw new NativeApiException("WtsSource.AccountIsNotLocalSamUser", NativeMethods.ErrorAccessDenied);
            }
            identityReport["source_account_is_local"] = true;
        }
        finally
        {
            _ = NativeMethods.NetApiBufferFree(buffer);
        }
    }

    private static (string Name, string Domain, int Use) LookupAccountForSid(string sidString, string api)
    {
        IntPtr sid = AllocateSid(sidString);
        try
        {
            uint nameSize = 1;
            uint domainSize = 1;
            var name = new StringBuilder(1);
            var domain = new StringBuilder(1);
            _ = NativeMethods.LookupAccountSid(null, sid, name, ref nameSize, domain, ref domainSize, out _);
            int sizeError = Marshal.GetLastWin32Error();
            if (sizeError != NativeMethods.ErrorInsufficientBuffer || nameSize is 0 or > 32768 || domainSize is 0 or > 32768)
            {
                throw new NativeApiException(api + ".Size", sizeError);
            }
            name = new StringBuilder(checked((int)nameSize));
            domain = new StringBuilder(checked((int)domainSize));
            if (!NativeMethods.LookupAccountSid(null, sid, name, ref nameSize, domain, ref domainSize, out int use))
            {
                throw LastError(api);
            }
            if (string.IsNullOrWhiteSpace(name.ToString()) || string.IsNullOrWhiteSpace(domain.ToString()))
            {
                throw new NativeApiException(api + ".EmptyResult", 13);
            }
            return (name.ToString(), domain.ToString(), use);
        }
        finally
        {
            Marshal.FreeHGlobal(sid);
        }
    }

    private static (string Sid, string Domain, int Use) LookupSidForAccount(string accountName, string api)
    {
        uint sidSize = 0;
        uint domainSize = 1;
        var domain = new StringBuilder(1);
        _ = NativeMethods.LookupAccountName(null, accountName, IntPtr.Zero, ref sidSize, domain, ref domainSize, out _);
        int sizeError = Marshal.GetLastWin32Error();
        if (sizeError != NativeMethods.ErrorInsufficientBuffer || sidSize is 0 or > 4096 || domainSize is 0 or > 32768)
        {
            throw new NativeApiException(api + ".Size", sizeError);
        }
        IntPtr sid = Marshal.AllocHGlobal(checked((int)sidSize));
        try
        {
            uint sidCapacity = sidSize;
            domain = new StringBuilder(checked((int)domainSize));
            uint domainCapacity = checked((uint)domain.Capacity);
            if (!NativeMethods.LookupAccountName(null, accountName, sid, ref sidCapacity, domain, ref domainCapacity, out int use))
            {
                throw LastError(api);
            }
            string sidString = new SecurityIdentifier(sid).Value;
            string domainName = domain.ToString();
            if (string.IsNullOrWhiteSpace(domainName))
            {
                throw new NativeApiException(api + ".EmptyDomain", 13);
            }
            return (sidString, domainName, use);
        }
        finally
        {
            Marshal.FreeHGlobal(sid);
        }
    }

    private static void CreateFilteredToken(SafeAccessTokenHandle source, IReadOnlyList<string> sidsToDisable,
        out SafeAccessTokenHandle restricted)
    {
        var sidPointers = new List<IntPtr>();
        IntPtr entries = IntPtr.Zero;
        try
        {
            int entrySize = Marshal.SizeOf<NativeMethods.SidAndAttributes>();
            entries = Marshal.AllocHGlobal(checked(entrySize * sidsToDisable.Count));
            for (int index = 0; index < sidsToDisable.Count; index++)
            {
                IntPtr sid = AllocateSid(sidsToDisable[index]);
                sidPointers.Add(sid);
                Marshal.StructureToPtr(new NativeMethods.SidAndAttributes { Sid = sid, Attributes = 0 },
                    IntPtr.Add(entries, index * entrySize), false);
            }
            if (!NativeMethods.CreateRestrictedToken(source, NativeMethods.CreateRestrictedTokenDisableMaxPrivilege,
                    checked((uint)sidsToDisable.Count), entries, 0, IntPtr.Zero, 0, IntPtr.Zero,
                    out restricted))
            {
                throw LastError("CreateRestrictedToken.WtsMedium");
            }
        }
        finally
        {
            if (entries != IntPtr.Zero)
            {
                for (int index = 0; index < sidsToDisable.Count; index++)
                {
                    Marshal.DestroyStructure<NativeMethods.SidAndAttributes>(IntPtr.Add(entries, index * Marshal.SizeOf<NativeMethods.SidAndAttributes>()));
                }
                Marshal.FreeHGlobal(entries);
            }
            foreach (IntPtr sid in sidPointers) Marshal.FreeHGlobal(sid);
        }
    }

    private static Dictionary<string, object?> VerifyFinalToken(
        SafeAccessTokenHandle source,
        SafeAccessTokenHandle token,
        string expectedUserSid,
        string expectedLogonSid,
        uint expectedSession)
    {
        string finalUserSid = ReadTokenSid(token, NativeMethods.TokenUser, "WtsFinal.TokenUser");
        string finalLogonSid = ReadLogonSid(token, "WtsFinal.LogonSid");
        uint session = ReadTokenUInt32(token, NativeMethods.TokenSessionId, "WtsFinal.TokenSessionId");
        uint elevation = ReadTokenUInt32(token, NativeMethods.TokenElevation, "WtsFinal.TokenElevation");
        uint tokenType = ReadTokenUInt32(token, NativeMethods.TokenType, "WtsFinal.TokenType");
        uint elevationType = ReadTokenUInt32(token, NativeMethods.TokenElevationType, "WtsFinal.TokenElevationType");
        string integritySid = ReadTokenSid(token, NativeMethods.TokenIntegrityLevel, "WtsFinal.TokenIntegrityLevel");
        IReadOnlyList<TokenGroup> groups = ReadGroups(token, NativeMethods.TokenGroups, "WtsFinal.TokenGroups");
        IReadOnlyList<TokenPrivilege> privileges = ReadPrivileges(token, "WtsFinal.TokenPrivileges");
        IReadOnlyList<TokenGroup> restrictedSids = ReadGroups(token, NativeMethods.TokenRestrictedSids, "WtsFinal.TokenRestrictedSids");

        TokenGroup? users = groups.FirstOrDefault(group => group.Sid == "S-1-5-32-545");
        bool usersEnabled = users is not null && (users.Attributes & NativeMethods.GroupEnabled) != 0;
        var checkedBuiltinAliasGroups = groups.Where(group => CheckedBuiltinElevatedAliasSids.Contains(group.Sid, StringComparer.Ordinal)).ToList();
        bool administratorsDenyOnly = groups.Any(group => group.Sid == "S-1-5-32-544"
            && (group.Attributes & NativeMethods.GroupUseForDenyOnly) != 0
            && (group.Attributes & NativeMethods.GroupEnabled) == 0);
        bool noEnabledCheckedAliases = checkedBuiltinAliasGroups.All(group => (group.Attributes & NativeMethods.GroupEnabled) == 0);
        bool enabledPrivilegesLimitedToChangeNotify = VerifyPrivileges(privileges);
        bool elevationTypeAcceptable = elevationType is 1 or 3;
        bool isRestricted = NativeMethods.IsTokenRestricted(token);
        bool sameSourceIdentity = ReadTokenSid(source, NativeMethods.TokenUser, "WtsSource.VerifyUser") == expectedUserSid
            && ReadLogonSid(source, "WtsSource.VerifyLogonSid") == expectedLogonSid;
        bool checks = finalUserSid == expectedUserSid && finalLogonSid == expectedLogonSid
            && session == expectedSession && elevation == 0 && tokenType == NativeMethods.TokenPrimary
            && elevationTypeAcceptable && integritySid == "S-1-16-8192" && usersEnabled
            && administratorsDenyOnly && noEnabledCheckedAliases && enabledPrivilegesLimitedToChangeNotify
            && restrictedSids.Count == 0 && !isRestricted && sameSourceIdentity;
        if (!checks)
        {
            throw new NativeApiException("WtsMedium.FinalTokenReadbackGate", NativeMethods.ErrorAccessDenied);
        }
        return new Dictionary<string, object?>
        {
            ["status"] = "pass",
            ["user_sid"] = finalUserSid,
            ["logon_sid"] = finalLogonSid,
            ["session_id"] = session,
            ["token_type"] = tokenType == NativeMethods.TokenPrimary ? "primary" : tokenType.ToString(System.Globalization.CultureInfo.InvariantCulture),
            ["token_type_value"] = tokenType,
            ["token_elevation_type"] = elevationType switch { 1 => "default", 2 => "full", 3 => "limited", _ => "unknown" },
            ["token_elevation_type_value"] = elevationType,
            ["token_elevation"] = elevation != 0,
            ["integrity_sid"] = integritySid,
            ["integrity_level"] = "medium",
            ["users_group_enabled"] = usersEnabled,
            ["administrators_group_deny_only"] = administratorsDenyOnly,
            ["checked_builtin_privileged_alias_sids"] = CheckedBuiltinElevatedAliasSids,
            ["checked_builtin_privileged_alias_enabled_groups_absent"] = noEnabledCheckedAliases,
            ["groups"] = groups.Select(SerializeGroup).ToArray(),
            ["privileges"] = privileges.Select(SerializePrivilege).ToArray(),
            ["all_enabled_privileges_limited_to_change_notify"] = enabledPrivilegesLimitedToChangeNotify,
            ["restricted_sid_list_count"] = restrictedSids.Count,
            ["token_is_restricted"] = isRestricted,
            ["same_user_and_logon_sid_as_wts_source"] = sameSourceIdentity,
            ["readback_gate_pass"] = true,
        };
    }

    private static bool VerifyPrivileges(IReadOnlyList<TokenPrivilege> privileges)
    {
        if (!NativeMethods.LookupPrivilegeValue(null, "SeChangeNotifyPrivilege", out NativeMethods.Luid changeNotify))
        {
            throw LastError("LookupPrivilegeValue.SeChangeNotifyPrivilege");
        }
        string allowed = LuidText(changeNotify);
        return privileges.All(privilege => (privilege.Attributes & NativeMethods.PrivilegeEnabled) == 0
            || privilege.Luid == allowed);
    }

    private static void SetMediumIntegrity(SafeAccessTokenHandle token)
    {
        SecurityIdentifier sid = new("S-1-16-8192");
        byte[] sidBytes = new byte[sid.BinaryLength];
        sid.GetBinaryForm(sidBytes, 0);
        int labelSize = Marshal.SizeOf<NativeMethods.TokenMandatoryLabel>();
        IntPtr buffer = Marshal.AllocHGlobal(checked(labelSize + sidBytes.Length));
        try
        {
            IntPtr sidPointer = IntPtr.Add(buffer, labelSize);
            Marshal.Copy(sidBytes, 0, sidPointer, sidBytes.Length);
            Marshal.StructureToPtr(new NativeMethods.TokenMandatoryLabel
            {
                Label = new NativeMethods.SidAndAttributes
                {
                    Sid = sidPointer,
                    Attributes = NativeMethods.MandatoryLabelIntegrityEnabled,
                },
            }, buffer, false);
            if (!NativeMethods.SetTokenInformation(token, NativeMethods.TokenIntegrityLevel, buffer,
                    checked(labelSize + sidBytes.Length)))
            {
                throw LastError("SetTokenInformation.TokenIntegrityLevel.Medium");
            }
        }
        finally
        {
            Marshal.DestroyStructure<NativeMethods.TokenMandatoryLabel>(buffer);
            Marshal.FreeHGlobal(buffer);
        }
    }

    private static string ReadTokenSid(SafeAccessTokenHandle token, int informationClass, string api)
    {
        using TokenInformationBuffer buffer = QueryTokenInformation(token, informationClass, api);
        NativeMethods.SidAndAttributes entry = Marshal.PtrToStructure<NativeMethods.SidAndAttributes>(buffer.Pointer);
        if (entry.Sid == IntPtr.Zero) throw new NativeApiException(api + ".SidMissing", 13);
        return new SecurityIdentifier(entry.Sid).Value;
    }

    private static string ReadLogonSid(SafeAccessTokenHandle token, string api)
    {
        using TokenInformationBuffer buffer = QueryTokenInformation(token, NativeMethods.TokenGroups, api);
        int offset = Marshal.OffsetOf<NativeMethods.TokenGroupsHeader>(nameof(NativeMethods.TokenGroupsHeader.FirstGroup)).ToInt32();
        int stride = Marshal.SizeOf<NativeMethods.SidAndAttributes>();
        uint count = unchecked((uint)Marshal.ReadInt32(buffer.Pointer));
        var logonIds = new List<string>();
        for (uint index = 0; index < count; index++)
        {
            NativeMethods.SidAndAttributes entry = Marshal.PtrToStructure<NativeMethods.SidAndAttributes>(IntPtr.Add(buffer.Pointer, checked(offset + (int)index * stride)));
            if ((entry.Attributes & NativeMethods.GroupLogonId) == NativeMethods.GroupLogonId)
            {
                logonIds.Add(new SecurityIdentifier(entry.Sid).Value);
            }
        }
        return logonIds.Count == 1 ? logonIds[0] : throw new NativeApiException(api + ".AmbiguousOrMissing", 13);
    }

    private static IReadOnlyList<TokenGroup> ReadGroups(SafeAccessTokenHandle token, int informationClass, string api)
    {
        using TokenInformationBuffer buffer = QueryTokenInformation(token, informationClass, api);
        int offset = Marshal.OffsetOf<NativeMethods.TokenGroupsHeader>(nameof(NativeMethods.TokenGroupsHeader.FirstGroup)).ToInt32();
        int stride = Marshal.SizeOf<NativeMethods.SidAndAttributes>();
        uint count = unchecked((uint)Marshal.ReadInt32(buffer.Pointer));
        if (count > (uint)Math.Max(0, (buffer.Length - offset) / stride))
        {
            throw new NativeApiException(api + ".InvalidCount", 13);
        }
        var groups = new List<TokenGroup>(checked((int)count));
        for (uint index = 0; index < count; index++)
        {
            NativeMethods.SidAndAttributes entry = Marshal.PtrToStructure<NativeMethods.SidAndAttributes>(IntPtr.Add(buffer.Pointer, checked(offset + (int)index * stride)));
            if (entry.Sid == IntPtr.Zero) throw new NativeApiException(api + ".NullSid", 13);
            groups.Add(new TokenGroup(new SecurityIdentifier(entry.Sid).Value, entry.Attributes));
        }
        return groups;
    }

    private static IReadOnlyList<TokenPrivilege> ReadPrivileges(SafeAccessTokenHandle token, string api)
    {
        using TokenInformationBuffer buffer = QueryTokenInformation(token, NativeMethods.TokenPrivilegesClass, api);
        int offset = Marshal.OffsetOf<NativeMethods.TokenPrivileges>(nameof(NativeMethods.TokenPrivileges.Privileges)).ToInt32();
        int stride = Marshal.SizeOf<NativeMethods.LuidAndAttributes>();
        uint count = unchecked((uint)Marshal.ReadInt32(buffer.Pointer));
        if (count > (uint)Math.Max(0, (buffer.Length - offset) / stride))
        {
            throw new NativeApiException(api + ".InvalidCount", 13);
        }
        var privileges = new List<TokenPrivilege>(checked((int)count));
        if (!NativeMethods.LookupPrivilegeValue(null, "SeChangeNotifyPrivilege", out NativeMethods.Luid changeNotify))
        {
            throw LastError("LookupPrivilegeValue.SeChangeNotifyPrivilege");
        }
        string changeNotifyLuid = LuidText(changeNotify);
        for (uint index = 0; index < count; index++)
        {
            NativeMethods.LuidAndAttributes entry = Marshal.PtrToStructure<NativeMethods.LuidAndAttributes>(IntPtr.Add(buffer.Pointer, checked(offset + (int)index * stride)));
            string luid = LuidText(entry.Luid);
            privileges.Add(new TokenPrivilege(luid, entry.Attributes, LookupPrivilegeName(entry.Luid, api)));
        }
        return privileges;
    }

    private static string LookupPrivilegeName(NativeMethods.Luid luid, string api)
    {
        uint required = 0;
        var initial = new StringBuilder(1);
        if (NativeMethods.LookupPrivilegeName(null, ref luid, initial, ref required))
        {
            return initial.ToString();
        }
        int sizeError = Marshal.GetLastWin32Error();
        if (sizeError != NativeMethods.ErrorInsufficientBuffer || required is 0 or > 256)
        {
            throw new NativeApiException(api + ".LookupPrivilegeName.Size", sizeError);
        }
        var name = new StringBuilder(checked((int)required));
        uint capacity = required;
        if (!NativeMethods.LookupPrivilegeName(null, ref luid, name, ref capacity))
        {
            throw LastError(api + ".LookupPrivilegeName");
        }
        return name.ToString();
    }

    private static Dictionary<string, object?> SerializeGroup(TokenGroup group) => new()
    {
        ["sid"] = group.Sid,
        ["attributes"] = $"0x{group.Attributes:X8}",
        ["enabled"] = (group.Attributes & NativeMethods.GroupEnabled) != 0,
        ["deny_only"] = (group.Attributes & NativeMethods.GroupUseForDenyOnly) != 0,
        ["logon_id"] = (group.Attributes & NativeMethods.GroupLogonId) == NativeMethods.GroupLogonId,
    };

    private static Dictionary<string, object?> SerializePrivilege(TokenPrivilege privilege) => new()
    {
        ["luid"] = privilege.Luid,
        ["attributes"] = $"0x{privilege.Attributes:X8}",
        ["enabled"] = (privilege.Attributes & NativeMethods.PrivilegeEnabled) != 0,
        ["name"] = privilege.Name,
    };

    private static uint ReadTokenUInt32(SafeAccessTokenHandle token, int informationClass, string api)
    {
        IntPtr buffer = Marshal.AllocHGlobal(sizeof(uint));
        try
        {
            if (!NativeMethods.GetTokenInformation(token, informationClass, buffer, sizeof(uint), out int returned))
            {
                throw LastError(api);
            }
            if (returned < sizeof(uint)) throw new NativeApiException(api + ".ShortBuffer", 13);
            return unchecked((uint)Marshal.ReadInt32(buffer));
        }
        finally
        {
            Marshal.FreeHGlobal(buffer);
        }
    }

    private static TokenInformationBuffer QueryTokenInformation(SafeAccessTokenHandle token, int informationClass, string api)
    {
        _ = NativeMethods.GetTokenInformation(token, informationClass, IntPtr.Zero, 0, out int required);
        int sizeError = Marshal.GetLastWin32Error();
        if (sizeError != NativeMethods.ErrorInsufficientBuffer || required is <= 0 or > 1024 * 1024)
        {
            throw new NativeApiException(api + ".Size", sizeError);
        }
        IntPtr buffer = Marshal.AllocHGlobal(required);
        if (!NativeMethods.GetTokenInformation(token, informationClass, buffer, required, out int returned))
        {
            int error = Marshal.GetLastWin32Error();
            Marshal.FreeHGlobal(buffer);
            throw new NativeApiException(api, error);
        }
        if (returned <= 0 || returned > required)
        {
            Marshal.FreeHGlobal(buffer);
            throw new NativeApiException(api + ".InvalidLength", 13);
        }
        return new TokenInformationBuffer(buffer, returned);
    }

    private static Dictionary<string, string> ReadEnvironment(IntPtr block)
    {
        var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        int offset = 0;
        for (int item = 0; item < 4096; item++)
        {
            string? entry = Marshal.PtrToStringUni(IntPtr.Add(block, offset));
            if (string.IsNullOrEmpty(entry)) return values;
            int equals = entry.IndexOf('=');
            if (equals > 0) values[entry[..equals]] = entry[(equals + 1)..];
            offset = checked(offset + (entry.Length + 1) * sizeof(char));
        }
        throw new NativeApiException("WtsMedium.EnvironmentBlock.Unterminated", 13);
    }

    private static string ReadProfileDirectory(SafeAccessTokenHandle token)
    {
        uint size = 0;
        _ = NativeMethods.GetUserProfileDirectory(token, new StringBuilder(1), ref size);
        int error = Marshal.GetLastWin32Error();
        if (error != NativeMethods.ErrorInsufficientBuffer || size is 0 or > 32768)
        {
            throw new NativeApiException("GetUserProfileDirectory.WtsMedium.Size", error);
        }
        var buffer = new StringBuilder(checked((int)size));
        if (!NativeMethods.GetUserProfileDirectory(token, buffer, ref size)) throw LastError("GetUserProfileDirectory.WtsMedium");
        return buffer.ToString();
    }

    private static bool IsWithin(string path, string parent)
    {
        string canonicalPath = Path.GetFullPath(path).TrimEnd('\\') + "\\";
        string canonicalParent = Path.GetFullPath(parent).TrimEnd('\\') + "\\";
        return canonicalPath.StartsWith(canonicalParent, StringComparison.OrdinalIgnoreCase);
    }

    private static void EnsurePathComponentsPlain(string path, string api)
    {
        string fullPath = Path.GetFullPath(path);
        string root = Path.GetPathRoot(fullPath) ?? throw new NativeApiException(api + ".NoRoot", NativeMethods.ErrorAccessDenied);
        string current = root;
        string relative = fullPath[root.Length..];
        foreach (string component in relative.Split(Path.DirectorySeparatorChar, StringSplitOptions.RemoveEmptyEntries))
        {
            current = Path.Combine(current, component);
            EnsurePlainDirectory(current, api);
        }
    }

    private static (uint Volume, ulong Index) ReadDirectoryIdentity(string path)
    {
        using SafeFileHandle handle = NativeMethods.OpenDirectoryHandle(path, NativeMethods.FileReadAttributes,
            NativeMethods.FileShareRead | NativeMethods.FileShareWrite | NativeMethods.FileShareDelete,
            IntPtr.Zero, NativeMethods.OpenExisting, NativeMethods.FileFlagBackupSemantics, IntPtr.Zero);
        if (handle.IsInvalid) throw LastError("CreateFile.WorkDirectoryIdentity");
        if (!NativeMethods.GetFileInformationByHandle(handle, out NativeMethods.ByHandleFileInformation info))
        {
            throw LastError("GetFileInformationByHandle.WorkDirectoryIdentity");
        }
        ulong index = ((ulong)info.FileIndexHigh << 32) | info.FileIndexLow;
        return (info.VolumeSerialNumber, index);
    }

    private static IntPtr AllocateSid(string sidString)
    {
        SecurityIdentifier sid = new(sidString);
        byte[] bytes = new byte[sid.BinaryLength];
        sid.GetBinaryForm(bytes, 0);
        IntPtr pointer = Marshal.AllocHGlobal(bytes.Length);
        Marshal.Copy(bytes, 0, pointer, bytes.Length);
        return pointer;
    }

    private static string LuidText(NativeMethods.Luid luid) => $"{unchecked((uint)luid.HighPart):X8}{luid.LowPart:X8}";

    private static void EnsurePlainDirectory(string path, string api)
    {
        FileAttributes attributes = File.GetAttributes(path);
        if ((attributes & FileAttributes.Directory) == 0 || (attributes & FileAttributes.ReparsePoint) != 0)
        {
            throw new NativeApiException(api, NativeMethods.ErrorAccessDenied);
        }
    }

    private static void EnsureNoReparsePoints(string root)
    {
        EnsurePlainDirectory(root, "WtsMedium.WorkDirectoryCleanup.ReparsePoint");
        var pending = new Stack<string>();
        pending.Push(root);
        while (pending.Count > 0)
        {
            string current = pending.Pop();
            foreach (FileSystemInfo entry in new DirectoryInfo(current).EnumerateFileSystemInfos("*", SearchOption.TopDirectoryOnly))
            {
                FileAttributes attributes = entry.Attributes;
                if ((attributes & FileAttributes.ReparsePoint) != 0)
                {
                    throw new NativeApiException("WtsMedium.WorkDirectoryCleanup.ChildReparsePoint", NativeMethods.ErrorAccessDenied);
                }
                if ((attributes & FileAttributes.Directory) != 0)
                {
                    pending.Push(entry.FullName);
                }
            }
        }
    }

    private static NativeApiException LastError(string api) => new(api, Marshal.GetLastWin32Error());

    private sealed record TokenGroup(string Sid, uint Attributes);
    private sealed record TokenPrivilege(string Luid, uint Attributes, string? Name);

    private sealed class TokenInformationBuffer : IDisposable
    {
        internal TokenInformationBuffer(IntPtr pointer, int length) { Pointer = pointer; Length = length; }
        internal IntPtr Pointer { get; }
        internal int Length { get; }
        public void Dispose() => Marshal.FreeHGlobal(Pointer);
    }
}
