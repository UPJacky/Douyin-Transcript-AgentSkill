using NuGet.Packaging;
using System.Threading;

internal static class Program
{
    private const long MaxPackageBytes = 64L * 1024 * 1024;

    private static int Main(string[] args)
    {
        if (args.Length != 1)
        {
            return Fail();
        }

        try
        {
            using var stream = new FileStream(
                args[0],
                FileMode.Open,
                FileAccess.Read,
                FileShare.Read);
            if (!stream.CanSeek || stream.Length <= 0 || stream.Length > MaxPackageBytes)
            {
                return Fail();
            }

            using var reader = new PackageArchiveReader(stream, leaveStreamOpen: true);
            var contentHash = reader.GetContentHash(CancellationToken.None);
            var digest = Convert.FromBase64String(contentHash);
            if (digest.Length != 64)
            {
                return Fail();
            }

            Console.WriteLine(Convert.ToBase64String(digest));
            return 0;
        }
        catch
        {
            return Fail();
        }
    }

    private static int Fail()
    {
        Console.Error.WriteLine("NuGet package content hash computation failed.");
        return 2;
    }
}
