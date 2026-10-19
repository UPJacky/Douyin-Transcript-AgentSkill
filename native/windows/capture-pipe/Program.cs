namespace DouyinTranscript.CapturePipe;

internal static class Program
{
    public static async Task<int> Main(string[] args)
    {
        if (args.Length == 2 && args[0] == "--lease-job-fixture-root")
        {
            return await LeaseProcessJobHarness.RunFixtureRootAsync(args[1]).ConfigureAwait(false);
        }

        if (args.Length == 3 && args[0] == "--lease-job-fixture-supervisor")
        {
            return await LeaseProcessJobHarness.RunFixtureSupervisorAsync(args[1], args[2]).ConfigureAwait(false);
        }

        if (args.Length == 1 && args[0] == "--lease-job-fixture-leaf")
        {
            return LeaseProcessJobHarness.RunFixtureLeaf();
        }

        if (args.Length == 1 && args[0] == "--lease-process-job-self-test")
        {
            try
            {
                await LeaseProcessJobHarness.RunAsync().ConfigureAwait(false);
                return 0;
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine($"FAIL lease process job {exception.GetType().Name}: {exception.Message}");
                return 1;
            }
        }

        if (args.Length == 1 && args[0] == "--self-test")
        {
            try
            {
                await LocalHarness.RunAsync().ConfigureAwait(false);
                return 0;
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine($"FAIL {exception.GetType().Name}: {exception.Message}");
                return 1;
            }
        }

        if (args.Length == 3 && args[0] == "--interop-test-server")
        {
            try
            {
                await LocalHarness.RunInteropTestServerAsync(args[1], args[2]).ConfigureAwait(false);
                return 0;
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine($"FAIL {exception.GetType().Name}: {exception.Message}");
                return 1;
            }
        }

        if (args.Length == 1 && args[0] == "--service")
        {
            return WindowsServiceDispatcher.Dispatch();
        }

        Console.WriteLine("Run --lease-process-job-self-test, --self-test, the integration-only --interop-test-server command, or --service from the Service Control Manager.");
        return args.Length == 0 ? 0 : 2;
    }
}
