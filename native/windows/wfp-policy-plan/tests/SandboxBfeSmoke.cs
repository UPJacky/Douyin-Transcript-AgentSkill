using System.Runtime.Versioning;

namespace WfpPolicyPlanTests;

[SupportedOSPlatform("windows6.0.6000")]
internal static class SandboxBfeSmoke
{
    internal static int Run(string[] args)
    {
        _ = args;
        Console.Error.WriteLine("Sandbox BFE mutation probe is disabled until its guest boundary can be independently authenticated.");
        return 2;
    }
}
