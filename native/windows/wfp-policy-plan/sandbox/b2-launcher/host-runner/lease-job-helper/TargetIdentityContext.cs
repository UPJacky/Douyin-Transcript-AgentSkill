using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace DouyinTranscript.LeaseJobHelper;

internal sealed class NativeApiException : Exception
{
    internal NativeApiException(string api, int errorCode) : base(api)
    {
        Api = api;
        ErrorCode = errorCode;
    }

    internal string Api { get; }
    internal int ErrorCode { get; }
}

internal sealed class TokenPrivilegeScope : IDisposable
{
    private readonly SafeAccessTokenHandle _processToken;
    private readonly List<NativeMethods.TokenPrivileges> _previousStates = [];
    private bool _disposed;

    private TokenPrivilegeScope(SafeAccessTokenHandle processToken) => _processToken = processToken;

    internal static TokenPrivilegeScope EnableRequired()
    {
        return EnableForNames("SeTcbPrivilege", "SeAssignPrimaryTokenPrivilege", "SeIncreaseQuotaPrivilege");
    }

    internal static TokenPrivilegeScope EnableWtsQueryUserTokenOnly()
    {
        return EnableForNames("SeTcbPrivilege");
    }

    private static TokenPrivilegeScope EnableForNames(params string[] names)
    {
        if (!NativeMethods.OpenProcessToken(NativeMethods.GetCurrentProcess(), NativeMethods.TokenQuery | NativeMethods.TokenAdjustPrivileges,
                out SafeAccessTokenHandle token))
        {
            throw LastError("OpenProcessToken");
        }

        var scope = new TokenPrivilegeScope(token);
        try
        {
            foreach (string name in names) scope.Enable(name);
            return scope;
        }
        catch
        {
            scope.Dispose();
            throw;
        }
    }

    private void Enable(string name)
    {
        if (!NativeMethods.LookupPrivilegeValue(null, name, out NativeMethods.Luid luid))
        {
            throw LastError("LookupPrivilegeValue");
        }
        var request = new NativeMethods.TokenPrivileges
        {
            PrivilegeCount = 1,
            Privileges = new NativeMethods.LuidAndAttributes { Luid = luid, Attributes = 0x00000002 },
        };
        if (!NativeMethods.AdjustTokenPrivileges(_processToken, false, ref request,
                Marshal.SizeOf<NativeMethods.TokenPrivileges>(), out NativeMethods.TokenPrivileges previous, out _))
        {
            throw LastError("AdjustTokenPrivileges");
        }
        int error = Marshal.GetLastWin32Error();
        if (error == NativeMethods.ErrorNotAllAssigned)
        {
            throw new NativeApiException("AdjustTokenPrivileges", error);
        }
        _previousStates.Add(previous);
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }
        _disposed = true;
        for (int index = _previousStates.Count - 1; index >= 0; index--)
        {
            NativeMethods.TokenPrivileges previous = _previousStates[index];
            _ = NativeMethods.AdjustTokenPrivileges(_processToken, false, ref previous,
                Marshal.SizeOf<NativeMethods.TokenPrivileges>(), out _, out _);
        }
        _processToken.Dispose();
    }

    private static NativeApiException LastError(string api) => new(api, Marshal.GetLastWin32Error());
}

internal sealed class TargetIdentityContext : ITargetProcessIdentity, IDisposable
{
    private TemporaryAccount? _account;
    private SafeAccessTokenHandle? _token;
    private SafeNativeHandle? _profileHandle;
    private IntPtr _environment;
    private bool _profileLoaded;
    private bool _disposed;

    public string UserSid { get; private set; } = string.Empty;
    public string LogonSid { get; private set; } = string.Empty;
    public int SessionId { get; private set; }
    internal string ProfilePath { get; private set; } = string.Empty;
    public Dictionary<string, object?>? LastIdentityReport { get; private set; }
    public SafeAccessTokenHandle Token => _token is { IsInvalid: false, IsClosed: false }
        ? _token
        : throw new InvalidOperationException("The target token is not initialized.");
    public IntPtr Environment => _environment != IntPtr.Zero
        ? _environment
        : throw new InvalidOperationException("The target environment block is not initialized.");

    internal static (bool UsersGroupEnabled, bool AdministratorsGroupEnabled) ValidateCurrentProcessGroupMembershipChecks()
    {
        if (!NativeMethods.OpenProcessToken(NativeMethods.GetCurrentProcess(), NativeMethods.TokenQuery | NativeMethods.TokenDuplicate,
                out SafeAccessTokenHandle token))
        {
            throw LastError("OpenProcessToken.GroupMembershipSelfTest");
        }
        using (token)
        {
            return CheckStandardGroupMembership(token, "CurrentTokenMembershipSelfTest");
        }
    }

    internal static (uint ActiveConsoleSessionId, int ActiveSessionCount) ValidateCurrentSessionEnumerationApis()
    {
        uint activeConsoleSessionId = NativeMethods.WtsGetActiveConsoleSessionId();
        if (!NativeMethods.WtsEnumerateSessions(new IntPtr(NativeMethods.WtsCurrentServerHandle), 0, 1,
                out IntPtr sessions, out int count))
        {
            throw LastError("WTSEnumerateSessions.SelfTest");
        }
        try
        {
            return (activeConsoleSessionId, count);
        }
        finally
        {
            if (sessions != IntPtr.Zero)
            {
                NativeMethods.WtsFreeMemory(sessions);
            }
        }
    }

    internal static (bool UsersGroupEnabled, bool AdministratorsGroupEnabled) CheckStandardGroupMembership(
        SafeAccessTokenHandle primaryToken,
        string failureContext)
    {
        if (!NativeMethods.DuplicateTokenEx(primaryToken, NativeMethods.TokenQuery, IntPtr.Zero,
                NativeMethods.SecurityImpersonation, NativeMethods.TokenImpersonation,
                out SafeAccessTokenHandle impersonationToken))
        {
            throw LastError($"{failureContext}.DuplicateTokenEx");
        }
        using (impersonationToken)
        {
            bool usersEnabled = CheckTokenMembershipForSid(impersonationToken, "S-1-5-32-545",
                $"{failureContext}.CheckTokenMembership.Users");
            bool administratorsEnabled = CheckTokenMembershipForSid(impersonationToken, "S-1-5-32-544",
                $"{failureContext}.CheckTokenMembership.Administrators");
            return (usersEnabled, administratorsEnabled);
        }
    }

    private static bool CheckTokenMembershipForSid(SafeAccessTokenHandle token, string sidString, string api)
    {
        IntPtr sid = AllocateSid(sidString);
        try
        {
            if (!NativeMethods.CheckTokenMembership(token, sid, out bool isMember))
            {
                throw LastError(api);
            }
            return isMember;
        }
        finally
        {
            Marshal.FreeHGlobal(sid);
        }
    }

    private static IntPtr AllocateSid(string sidString)
    {
        SecurityIdentifier sid = new(sidString);
        byte[] binary = new byte[sid.BinaryLength];
        sid.GetBinaryForm(binary, 0);
        IntPtr pointer = Marshal.AllocHGlobal(binary.Length);
        Marshal.Copy(binary, 0, pointer, binary.Length);
        return pointer;
    }

    internal Dictionary<string, object?> Initialize()
    {
        var identityReport = new Dictionary<string, object?>
        {
            ["helper_sid"] = WindowsIdentity.GetCurrent().User?.Value,
            ["helper_session_id"] = System.Diagnostics.Process.GetCurrentProcess().SessionId,
            ["is_local_system"] = WindowsIdentity.GetCurrent().User?.Value == "S-1-5-18",
            ["account_created"] = false,
            ["account_groups_verified"] = false,
            ["users_group_present"] = false,
            ["administrators_group_absent"] = false,
            ["users_group_enabled"] = false,
            ["administrators_group_enabled"] = false,
            ["logon_succeeded"] = false,
            ["target_logon_sid"] = null,
            ["token_is_elevated"] = null,
            ["not_elevated"] = false,
            ["token_session_id_before"] = null,
            ["target_session_id"] = null,
            ["token_session_id_after"] = null,
            ["profile_loaded"] = false,
            ["environment_block_created"] = false,
            ["environment_checks"] = null,
            ["desktop"] = new Dictionary<string, object?>
            {
                ["requested_lpDesktop"] = TargetProcessLauncher.SystemSelectedDesktop,
                ["selection"] = "Windows logon-session connection rules; actual root/child station and desktop remain unknown until supervised fixture markers",
                ["acl_mutated"] = false,
                ["preflight"] = "same-session interactive WinSta0/Default DACL is captured and checked for diagnostic evidence only; no ACL change is made",
            },
        };
        LastIdentityReport = identityReport;

        if (identityReport["is_local_system"] is not true)
        {
            throw new NativeApiException("Precondition.LocalSystem", 5);
        }

        _account = TemporaryAccount.Create(account =>
        {
            _account = account;
            identityReport["account_created"] = true;
        });
        UserSid = _account.UserSid;
        identityReport["account_created"] = true;
        identityReport["target_user_sid"] = UserSid;
        identityReport["users_group_present"] = _account.UsersGroupPresent;
        identityReport["administrators_group_absent"] = _account.AdministratorsGroupAbsent;
        identityReport["users_group_enabled"] = _account.UsersGroupEnabled;
        identityReport["administrators_group_enabled"] = _account.AdministratorsGroupEnabled;
        identityReport["account_groups_verified"] = _account.UsersGroupPresent
            && _account.AdministratorsGroupAbsent
            && _account.UsersGroupEnabled
            && !_account.AdministratorsGroupEnabled;

        _token = _account.LogonAndDuplicatePrimary();
        identityReport["logon_succeeded"] = true;
        LogonSid = ReadLogonSid(_token, "TargetTokenGroups.LogonSid");
        identityReport["target_logon_sid"] = LogonSid;
        bool tokenIsElevated = ReadTokenElevation(_token);
        identityReport["token_is_elevated"] = tokenIsElevated;
        identityReport["not_elevated"] = !tokenIsElevated;
        if (tokenIsElevated)
        {
            throw new NativeApiException("VerifyTokenElevation.NotElevated", NativeMethods.ErrorAccessDenied);
        }

        uint beforeSession = ReadTokenSessionId(_token);
        identityReport["token_session_id_before"] = beforeSession;
        (SessionId, uint activeConsole, string sessionSource) = SelectTargetSession(identityReport, beforeSession);
        identityReport["active_console_session_id"] = activeConsole;
        identityReport["session_selection"] = sessionSource;
        identityReport["target_session_is_interactive"] =
            sessionSource != "original-token-session0-headless-diagnostic";
        identityReport["target_session_id"] = SessionId;
        uint targetSession = (uint)SessionId;
        if (!NativeMethods.SetTokenInformation(_token, NativeMethods.TokenSessionId, ref targetSession, sizeof(uint)))
        {
            throw LastError("SetTokenInformation.TokenSessionId");
        }
        uint afterSession = ReadTokenSessionId(_token);
        identityReport["token_session_id_after"] = afterSession;
        if (afterSession != targetSession)
        {
            throw new NativeApiException("VerifyTokenSessionId", 13);
        }

        string profileUserName = _account.UserName;
        var profileInfo = new NativeMethods.ProfileInfo
        {
            Size = Marshal.SizeOf<NativeMethods.ProfileInfo>(),
            Flags = 0,
            UserName = Marshal.StringToHGlobalUni(profileUserName),
        };
        try
        {
            if (!NativeMethods.LoadUserProfile(_token, ref profileInfo))
            {
                throw LastError("LoadUserProfile");
            }
            _profileLoaded = true;
            _profileHandle = new SafeNativeHandle(profileInfo.ProfileHandle);
            identityReport["profile_loaded"] = true;
        }
        finally
        {
            Marshal.FreeHGlobal(profileInfo.UserName);
        }

        ProfilePath = ReadUserProfilePath(_token);
        identityReport["profile_path_available"] = !string.IsNullOrWhiteSpace(ProfilePath);
        if (!NativeMethods.CreateEnvironmentBlock(out _environment, _token, false))
        {
            throw LastError("CreateEnvironmentBlock");
        }
        identityReport["environment_block_created"] = true;
        var environmentValues = ReadEnvironment(_environment);
        string[] requiredVariables = ["USERPROFILE", "USERNAME", "TEMP", "TMP"];
        string[] optionalDiagnosticVariables = ["HOMEDRIVE"];
        string[] observedVariables = [.. requiredVariables, .. optionalDiagnosticVariables];
        var environmentChecks = observedVariables.ToDictionary(
            name => name,
            name => environmentValues.ContainsKey(name),
            StringComparer.OrdinalIgnoreCase);
        identityReport["environment_checks"] = environmentChecks;
        identityReport["environment_required_variables"] = requiredVariables;
        identityReport["environment_optional_diagnostics"] = optionalDiagnosticVariables;
        if (requiredVariables.Any(name => !environmentChecks[name]))
        {
            throw new NativeApiException("VerifyUserEnvironment", 13);
        }

        return identityReport;
    }

    internal Dictionary<string, object?> Cleanup()
    {
        var cleanup = new Dictionary<string, object?>
        {
            ["environment_destroyed"] = _environment == IntPtr.Zero,
            ["profile_unloaded"] = !_profileLoaded,
            ["account_deleted"] = _account is null,
            ["errors"] = new List<Dictionary<string, object?>>(),
        };
        var errors = (List<Dictionary<string, object?>>)cleanup["errors"]!;

        if (_environment != IntPtr.Zero)
        {
            if (!NativeMethods.DestroyEnvironmentBlock(_environment))
            {
                AddError(errors, "DestroyEnvironmentBlock", Marshal.GetLastWin32Error());
            }
            else
            {
                cleanup["environment_destroyed"] = true;
            }
            _environment = IntPtr.Zero;
        }

        if (_profileLoaded && _profileHandle is not null && _token is not null)
        {
            if (!NativeMethods.UnloadUserProfile(_token, _profileHandle))
            {
                AddError(errors, "UnloadUserProfile", Marshal.GetLastWin32Error());
            }
            else
            {
                cleanup["profile_unloaded"] = true;
                _profileLoaded = false;
            }
        }
        _profileHandle?.Dispose();
        _profileHandle = null;
        _token?.Dispose();
        _token = null;

        if (_account is not null)
        {
            int result = _account.Delete();
            cleanup["account_deleted"] = result == NativeMethods.ErrorSuccess || result == NativeMethods.ErrorNoSuchUser;
            if (!((bool)cleanup["account_deleted"]!))
            {
                AddError(errors, "NetUserDel", result);
            }
            _account = null;
        }
        _disposed = true;
        return cleanup;
    }

    public void Dispose()
    {
        if (!_disposed)
        {
            _ = Cleanup();
        }
    }

    private static uint ReadTokenSessionId(SafeAccessTokenHandle token)
    {
        return ReadTokenUInt32(token, NativeMethods.TokenSessionId, "GetTokenInformation.TokenSessionId");
    }

    private static string ReadLogonSid(SafeAccessTokenHandle token, string failureContext)
    {
        _ = NativeMethods.GetTokenInformation(token, NativeMethods.TokenGroups, IntPtr.Zero, 0, out int required);
        int error = Marshal.GetLastWin32Error();
        int groupsOffset = Marshal.OffsetOf<NativeMethods.TokenGroupsHeader>(nameof(NativeMethods.TokenGroupsHeader.FirstGroup)).ToInt32();
        int groupStride = Marshal.SizeOf<NativeMethods.SidAndAttributes>();
        if (error != NativeMethods.ErrorInsufficientBuffer || required < groupsOffset)
        {
            throw new NativeApiException($"{failureContext}.Size", error);
        }

        IntPtr buffer = Marshal.AllocHGlobal(required);
        try
        {
            if (!NativeMethods.GetTokenInformation(token, NativeMethods.TokenGroups, buffer, required, out int returned))
            {
                throw new NativeApiException(failureContext, Marshal.GetLastWin32Error());
            }
            if (returned < groupsOffset)
            {
                throw new NativeApiException($"{failureContext}.ShortBuffer", 13);
            }
            uint groupCount = unchecked((uint)Marshal.ReadInt32(buffer));
            long available = returned - (long)groupsOffset;
            if (groupCount > available / groupStride)
            {
                throw new NativeApiException($"{failureContext}.InvalidGroupCount", 13);
            }

            string? found = null;
            for (uint index = 0; index < groupCount; index++)
            {
                IntPtr entry = IntPtr.Add(buffer, checked(groupsOffset + (int)index * groupStride));
                NativeMethods.SidAndAttributes group = Marshal.PtrToStructure<NativeMethods.SidAndAttributes>(entry);
                if ((group.Attributes & 0xC0000000) != 0xC0000000) continue;
                if (group.Sid == IntPtr.Zero || found is not null)
                {
                    throw new NativeApiException($"{failureContext}.Ambiguous", 13);
                }
                found = new SecurityIdentifier(group.Sid).Value;
            }
            return found ?? throw new NativeApiException($"{failureContext}.Missing", 13);
        }
        finally
        {
            Marshal.FreeHGlobal(buffer);
        }
    }

    private static bool ReadTokenElevation(SafeAccessTokenHandle token)
    {
        uint elevated = ReadTokenUInt32(token, NativeMethods.TokenElevation, "GetTokenInformation.TokenElevation");
        if (elevated > 1)
        {
            throw new NativeApiException("VerifyTokenElevation.InvalidValue", 13);
        }
        return elevated != 0;
    }

    private static uint ReadTokenUInt32(SafeAccessTokenHandle token, int informationClass, string api)
    {
        IntPtr buffer = Marshal.AllocHGlobal(sizeof(uint));
        try
        {
            if (!NativeMethods.GetTokenInformation(token, informationClass, buffer, sizeof(uint), out int returned))
            {
                throw LastError(api);
            }
            if (returned < sizeof(uint))
            {
                throw new NativeApiException($"{api}.InvalidLength", 13);
            }
            return unchecked((uint)Marshal.ReadInt32(buffer));
        }
        finally
        {
            Marshal.FreeHGlobal(buffer);
        }
    }

    private static string ReadUserProfilePath(SafeAccessTokenHandle token)
    {
        uint size = 0;
        _ = NativeMethods.GetUserProfileDirectory(token, new StringBuilder(), ref size);
        int error = Marshal.GetLastWin32Error();
        if (size == 0 && error != NativeMethods.ErrorInsufficientBuffer)
        {
            throw new NativeApiException("GetUserProfileDirectory.size", error);
        }
        var buffer = new StringBuilder(checked((int)size));
        if (!NativeMethods.GetUserProfileDirectory(token, buffer, ref size))
        {
            throw LastError("GetUserProfileDirectory");
        }
        return Path.GetFullPath(buffer.ToString());
    }

    private static Dictionary<string, string> ReadEnvironment(IntPtr environment)
    {
        var result = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        int offset = 0;
        while (true)
        {
            IntPtr entryPointer = IntPtr.Add(environment, offset * sizeof(char));
            string? entry = Marshal.PtrToStringUni(entryPointer);
            if (string.IsNullOrEmpty(entry))
            {
                break;
            }
            int delimiter = entry[0] == '=' ? entry.IndexOf('=', 1) : entry.IndexOf('=');
            if (delimiter > 0)
            {
                result[entry[..delimiter]] = entry[(delimiter + 1)..];
            }
            offset = checked(offset + entry.Length + 1);
        }
        return result;
    }

    private static (int SessionId, uint ActiveConsoleSessionId, string Source) SelectTargetSession(
        Dictionary<string, object?> identityReport,
        uint originalTokenSessionId)
    {
        uint activeConsoleSessionId = NativeMethods.WtsGetActiveConsoleSessionId();
        identityReport["active_console_session_id"] = activeConsoleSessionId;
        if (!NativeMethods.WtsEnumerateSessions(new IntPtr(NativeMethods.WtsCurrentServerHandle), 0, 1,
                out IntPtr sessions, out int count))
        {
            identityReport["wts_enumeration_succeeded"] = false;
            throw LastError("WTSEnumerateSessions");
        }
        identityReport["wts_enumeration_succeeded"] = true;
        try
        {
            var candidates = new List<int>();
            var observedSessions = new List<Dictionary<string, object?>>(Math.Max(count, 0));
            int entrySize = Marshal.SizeOf<NativeMethods.WtsSessionInfo>();
            for (int index = 0; index < count; index++)
            {
                NativeMethods.WtsSessionInfo session = Marshal.PtrToStructure<NativeMethods.WtsSessionInfo>(
                    IntPtr.Add(sessions, index * entrySize));
                observedSessions.Add(new Dictionary<string, object?>
                {
                    ["session_id"] = session.SessionId,
                    ["state"] = session.State,
                });
                if (session.SessionId > 0 && session.State == NativeMethods.WtsActive)
                {
                    candidates.Add(session.SessionId);
                }
            }
            identityReport["wts_session_count"] = count;
            identityReport["wts_sessions"] = observedSessions;
            identityReport["eligible_active_session_ids"] = candidates;

            if (activeConsoleSessionId != uint.MaxValue && activeConsoleSessionId > 0
                && candidates.Contains(checked((int)activeConsoleSessionId)))
            {
                return (checked((int)activeConsoleSessionId), activeConsoleSessionId, "active-console");
            }
            if (candidates.Count > 0)
            {
                int selected = candidates.Order().First();
                return (selected, activeConsoleSessionId, "active-wts-session");
            }

            int helperSessionId = System.Diagnostics.Process.GetCurrentProcess().SessionId;
            bool disconnectedSessionZeroExists = observedSessions.Any(session =>
                session["session_id"] is int sessionId && sessionId == 0
                && session["state"] is int state && state == NativeMethods.WtsDisconnected);
            if (activeConsoleSessionId == uint.MaxValue
                && helperSessionId == 0
                && originalTokenSessionId == 0
                && disconnectedSessionZeroExists)
            {
                return (0, activeConsoleSessionId, "original-token-session0-headless-diagnostic");
            }
            throw new NativeApiException("SelectTargetSession.NoEligibleSession", NativeMethods.ErrorNotFound);
        }
        finally
        {
            NativeMethods.WtsFreeMemory(sessions);
        }
    }

    private static void AddError(List<Dictionary<string, object?>> errors, string api, int code) =>
        errors.Add(new Dictionary<string, object?> { ["api"] = api, ["win32_error"] = code });

    private static NativeApiException LastError(string api) => new(api, Marshal.GetLastWin32Error());
}

internal sealed class TemporaryAccount
{
    private TemporaryAccount(string userName)
    {
        UserName = userName;
    }

    internal string UserName { get; }
    internal string UserSid { get; private set; } = string.Empty;
    internal bool UsersGroupPresent { get; private set; }
    internal bool AdministratorsGroupAbsent { get; private set; }
    internal bool UsersGroupEnabled { get; private set; }
    internal bool AdministratorsGroupEnabled { get; private set; }

    internal static TemporaryAccount Create(Action<TemporaryAccount> registerForCleanup)
    {
        ArgumentNullException.ThrowIfNull(registerForCleanup);
        byte[] nameEntropy = RandomNumberGenerator.GetBytes(8);
        string userName = "b2u" + Convert.ToHexString(nameEntropy).ToLowerInvariant();
        CryptographicOperations.ZeroMemory(nameEntropy);
        char[] password = GeneratePassword();
        var account = new TemporaryAccount(userName);
        SafeAccessTokenHandle? logonToken = null;
        try
        {
            AddUser(userName, password);
            registerForCleanup(account);
            string localAccountName = $"{Environment.MachineName}\\{userName}";
            string userSid = LookupSidForAccount(localAccountName, "LookupTargetAccountSid");
            EnsureUsersMembership(userSid);
            IReadOnlyList<string> localGroupNames = ReadLocalGroupNames(userName);
            string usersGroupName = LookupNameForSid("S-1-5-32-545");
            string administratorsGroupName = LookupNameForSid("S-1-5-32-544");
            bool usersGroupPresent = localGroupNames.Contains(usersGroupName, StringComparer.OrdinalIgnoreCase);
            bool administratorsGroupAbsent = !localGroupNames.Contains(administratorsGroupName, StringComparer.OrdinalIgnoreCase);
            logonToken = Logon(userName, password);
            (bool usersGroupEnabled, bool administratorsGroupEnabled) =
                TargetIdentityContext.CheckStandardGroupMembership(logonToken, "TargetTokenGroups");
            if (!usersGroupPresent || !administratorsGroupAbsent || !usersGroupEnabled || administratorsGroupEnabled)
            {
                throw new NativeApiException("VerifyTemporaryAccountGroups", 5);
            }

            account.UserSid = userSid;
            account.UsersGroupPresent = usersGroupPresent;
            account.AdministratorsGroupAbsent = administratorsGroupAbsent;
            account.UsersGroupEnabled = usersGroupEnabled;
            account.AdministratorsGroupEnabled = administratorsGroupEnabled;
            account._logonToken = logonToken;
            logonToken = null;
            return account;
        }
        catch
        {
            logonToken?.Dispose();
            throw;
        }
        finally
        {
            CryptographicOperations.ZeroMemory(MemoryMarshal.AsBytes(password.AsSpan()));
        }
    }

    private SafeAccessTokenHandle? _logonToken;
    private bool _deleted;

    internal SafeAccessTokenHandle LogonAndDuplicatePrimary()
    {
        if (_logonToken is null || _logonToken.IsInvalid || _logonToken.IsClosed)
        {
            throw new InvalidOperationException("The temporary account logon token is missing.");
        }
        if (!NativeMethods.DuplicateTokenEx(_logonToken, NativeMethods.TokenAllForLaunch, IntPtr.Zero,
                NativeMethods.SecurityImpersonation, NativeMethods.TokenPrimary, out SafeAccessTokenHandle primary))
        {
            throw LastError("DuplicateTokenEx");
        }
        return primary;
    }

    internal int Delete()
    {
        if (_deleted)
        {
            return NativeMethods.ErrorSuccess;
        }
        _logonToken?.Dispose();
        _logonToken = null;
        int result = NativeMethods.NetUserDel(null, UserName);
        if (result == NativeMethods.ErrorSuccess || result == NativeMethods.ErrorNoSuchUser)
        {
            _deleted = true;
        }
        return result;
    }

    private static unsafe void AddUser(string userName, char[] password)
    {
        IntPtr name = Marshal.StringToHGlobalUni(userName);
        IntPtr comment = Marshal.StringToHGlobalUni("Disposable B2 guest verification account");
        try
        {
            fixed (char* passwordPointer = password)
            {
                var info = new NativeMethods.UserInfo1Raw
                {
                    Name = name,
                    Password = (IntPtr)passwordPointer,
                    PasswordAge = 0,
                    Privilege = NativeMethods.UserPrivUser,
                    Comment = comment,
                    Flags = NativeMethods.UfScript | NativeMethods.UfDontExpirePasswd,
                };
                IntPtr buffer = Marshal.AllocHGlobal(Marshal.SizeOf<NativeMethods.UserInfo1Raw>());
                try
                {
                    Marshal.StructureToPtr(info, buffer, false);
                    int result = NativeMethods.NetUserAdd(null, 1, buffer, out _);
                    if (result != NativeMethods.ErrorSuccess)
                    {
                        throw new NativeApiException("NetUserAdd", result);
                    }
                }
                finally
                {
                    Marshal.DestroyStructure<NativeMethods.UserInfo1Raw>(buffer);
                    Marshal.FreeHGlobal(buffer);
                }
            }
        }
        finally
        {
            Marshal.FreeHGlobal(comment);
            Marshal.FreeHGlobal(name);
        }
    }

    private static unsafe SafeAccessTokenHandle Logon(string userName, char[] password)
    {
        fixed (char* passwordPointer = password)
        {
            if (!NativeMethods.LogonUser(userName, ".", passwordPointer,
                    NativeMethods.Logon32LogonInteractive, NativeMethods.Logon32ProviderDefault,
                    out SafeAccessTokenHandle token))
            {
                throw LastError("LogonUser");
            }
            return token;
        }
    }

    private static char[] GeneratePassword()
    {
        const string upper = "ABCDEFGHJKLMNPQRSTUVWXYZ";
        const string lower = "abcdefghijkmnopqrstuvwxyz";
        const string digits = "23456789";
        const string special = "!#$%&()*+,-./:;<=>?@[]^_{|}~";
        const string alphabet = upper + lower + digits + special;
        char[] result = new char[48];
        result[0] = Pick(upper);
        result[1] = Pick(lower);
        result[2] = Pick(digits);
        result[3] = Pick(special);
        for (int index = 4; index < result.Length; index++)
        {
            result[index] = Pick(alphabet);
        }
        byte[] shuffle = RandomNumberGenerator.GetBytes(result.Length);
        try
        {
            for (int index = result.Length - 1; index > 0; index--)
            {
                int swapIndex = shuffle[index] % (index + 1);
                (result[index], result[swapIndex]) = (result[swapIndex], result[index]);
            }
        }
        finally
        {
            CryptographicOperations.ZeroMemory(shuffle);
        }
        return result;

        static char Pick(string choices)
        {
            byte[] random = RandomNumberGenerator.GetBytes(1);
            try
            {
                return choices[random[0] % choices.Length];
            }
            finally
            {
                CryptographicOperations.ZeroMemory(random);
            }
        }
    }

    private static void EnsureUsersMembership(string userSid)
    {
        string usersGroupName = LookupNameForSid("S-1-5-32-545");
        IntPtr sid = GetSidPointer(userSid);
        try
        {
            var member = new NativeMethods.LocalGroupMembersInfo0 { Sid = sid };
            IntPtr buffer = Marshal.AllocHGlobal(Marshal.SizeOf<NativeMethods.LocalGroupMembersInfo0>());
            try
            {
                Marshal.StructureToPtr(member, buffer, false);
                int result = NativeMethods.NetLocalGroupAddMembers(null, usersGroupName, 0, buffer, 1);
                if (result != NativeMethods.ErrorSuccess && result != NativeMethods.ErrorAlreadyMember)
                {
                    throw new NativeApiException("NetLocalGroupAddMembers.Users", result);
                }
            }
            finally
            {
                Marshal.FreeHGlobal(buffer);
            }
        }
        finally
        {
            Marshal.FreeHGlobal(sid);
        }
    }

    private static IReadOnlyList<string> ReadLocalGroupNames(string userName)
    {
        int result = NativeMethods.NetUserGetLocalGroups(null, userName, 0, 0, out IntPtr buffer,
            uint.MaxValue, out uint entriesRead, out _);
        if (result != NativeMethods.ErrorSuccess)
        {
            throw new NativeApiException("NetUserGetLocalGroups", result);
        }
        try
        {
            var names = new List<string>(checked((int)entriesRead));
            for (int index = 0; index < entriesRead; index++)
            {
                IntPtr namePointer = Marshal.ReadIntPtr(buffer, checked((int)index * IntPtr.Size));
                string? name = Marshal.PtrToStringUni(namePointer);
                if (string.IsNullOrWhiteSpace(name))
                    throw new NativeApiException("NetUserGetLocalGroups.NullName", 13);
                names.Add(name);
            }
            return names;
        }
        finally
        {
            if (buffer != IntPtr.Zero)
                _ = NativeMethods.NetApiBufferFree(buffer);
        }
    }

    private static string LookupSidForAccount(string accountName, string failureContext)
    {
        uint sidSize = 0;
        uint domainSize = 0;
        var domain = new StringBuilder(256);
        _ = NativeMethods.LookupAccountName(null, accountName, IntPtr.Zero, ref sidSize, domain, ref domainSize, out _);
        int error = Marshal.GetLastWin32Error();
        if (sidSize == 0 || error != NativeMethods.ErrorInsufficientBuffer)
        {
            throw new NativeApiException($"{failureContext}.LookupAccountName.size", error);
        }
        IntPtr sid = Marshal.AllocHGlobal(checked((int)sidSize));
        try
        {
            domain = new StringBuilder(checked((int)Math.Max(domainSize, 1)));
            if (!NativeMethods.LookupAccountName(null, accountName, sid, ref sidSize, domain, ref domainSize, out _))
            {
                throw LastError($"{failureContext}.LookupAccountName");
            }
            return ConvertSidToString(sid);
        }
        finally
        {
            Marshal.FreeHGlobal(sid);
        }
    }

    private static string ConvertSidToString(IntPtr sid)
    {
        if (!NativeMethods.ConvertSidToStringSid(sid, out IntPtr sidText))
        {
            throw LastError("ConvertSidToStringSid");
        }
        try
        {
            return Marshal.PtrToStringUni(sidText)
                ?? throw new NativeApiException("ConvertSidToStringSid.Read", 13);
        }
        finally
        {
            _ = NativeMethods.LocalFree(sidText);
        }
    }

    private static string LookupNameForSid(string sidString)
    {
        IntPtr sid = GetSidPointer(sidString);
        try
        {
            uint nameSize = 0;
            uint domainSize = 0;
            var name = new StringBuilder();
            var domain = new StringBuilder();
            _ = NativeMethods.LookupAccountSid(null, sid, name, ref nameSize, domain, ref domainSize, out _);
            int error = Marshal.GetLastWin32Error();
            if (error != NativeMethods.ErrorInsufficientBuffer || nameSize == 0)
            {
                throw new NativeApiException("LookupAccountSid.size", error);
            }
            name = new StringBuilder(checked((int)nameSize));
            domain = new StringBuilder(checked((int)Math.Max(domainSize, 1)));
            if (!NativeMethods.LookupAccountSid(null, sid, name, ref nameSize, domain, ref domainSize, out _))
            {
                throw LastError("LookupAccountSid");
            }
            return name.ToString();
        }
        finally
        {
            Marshal.FreeHGlobal(sid);
        }
    }

    private static IntPtr GetSidPointer(string sidString)
    {
        SecurityIdentifier sid = new(sidString);
        byte[] binary = new byte[sid.BinaryLength];
        sid.GetBinaryForm(binary, 0);
        IntPtr pointer = Marshal.AllocHGlobal(binary.Length);
        Marshal.Copy(binary, 0, pointer, binary.Length);
        return pointer;
    }

    private static NativeApiException LastError(string api) => new(api, Marshal.GetLastWin32Error());
}
