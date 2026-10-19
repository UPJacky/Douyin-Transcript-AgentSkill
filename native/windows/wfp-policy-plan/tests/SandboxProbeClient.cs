using System.Runtime.Versioning;

namespace WfpPolicyPlanTests;

[SupportedOSPlatform("windows6.0.6000")]
internal static class SandboxProbeClient
{
    internal static int Run(string[] args)
    {
        _ = args;
        Console.Error.WriteLine("Sandbox network probe is disabled until guest identity can be independently authenticated.");
        return 2;
    }

    internal sealed record HelperMessage(string Type, string? Sid, int Pid, string ImagePath, bool? Succeeded);
}
