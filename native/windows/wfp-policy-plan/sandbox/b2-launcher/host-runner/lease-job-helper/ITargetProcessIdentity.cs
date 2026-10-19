using Microsoft.Win32.SafeHandles;

namespace DouyinTranscript.LeaseJobHelper;

internal interface ITargetProcessIdentity
{
    SafeAccessTokenHandle Token { get; }
    IntPtr Environment { get; }
    string UserSid { get; }
    string LogonSid { get; }
    int SessionId { get; }
    Dictionary<string, object?>? LastIdentityReport { get; }
}
