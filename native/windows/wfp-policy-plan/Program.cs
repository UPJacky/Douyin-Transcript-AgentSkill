using System.Text.Json;
using System.Text.Json.Serialization;

namespace WfpPolicyPlan;

internal static class Program
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.Never,
    };

    private static int Main(string[] args)
    {
        if (args.Length != 1 || args[0] is not ("--plan" or "--filter-plan" or "--layout" or "--help"))
        {
            Console.Error.WriteLine("Usage: WfpPolicyPlan --plan | --filter-plan | --layout | --help");
            Console.Error.WriteLine("This executable only prints JSON and has no policy-application command.");
            return 2;
        }

        if (args[0] == "--help")
        {
            Console.WriteLine("WFP semantic policy preview and CsWin32 managed-layout report.");
            Console.WriteLine("Commands: --plan, --filter-plan, --layout, --help. No WFP policy is read or changed.");
            return 0;
        }

        try
        {
            object document = args[0] switch
            {
                "--plan" => PolicyPlan.CreateAndValidate(),
                "--filter-plan" => NativeFilterPlan.CreateAndValidate(),
                _ => ManagedLayoutReport.Create(),
            };
            Console.WriteLine(JsonSerializer.Serialize(document, JsonOptions));
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine($"Refusing to emit an invalid report: {error.Message}");
            return 1;
        }
    }
}
