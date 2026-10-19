using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text.Json;

namespace DouyinTranscript.LeaseJobHelper;

internal static class FixtureRuntime
{
    internal static async Task<int> RunRootAsync(string rootMarker, string childMarker)
    {
        Process? child = null;
        try
        {
            string childExecutable = Environment.ProcessPath
                ?? throw new InvalidOperationException("The fixture executable path is unavailable.");
            var start = new ProcessStartInfo
            {
                FileName = childExecutable,
                UseShellExecute = false,
                WorkingDirectory = Path.GetDirectoryName(Path.GetFullPath(rootMarker))!,
            };
            start.ArgumentList.Add("--fixture-leaf");
            start.ArgumentList.Add(Path.GetFullPath(childMarker));
            child = Process.Start(start) ?? throw new InvalidOperationException("The fixture child did not start.");
            await WriteMarkerAsync(rootMarker, child.Id).ConfigureAwait(false);
            await Task.Delay(Timeout.InfiniteTimeSpan).ConfigureAwait(false);
            return 0;
        }
        catch (TaskCanceledException)
        {
            return 0;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine($"fixture-root:{exception.GetType().Name}");
            return 71;
        }
        finally
        {
            child?.Dispose();
        }
    }

    internal static async Task<int> RunLeafAsync(string markerPath)
    {
        try
        {
            await WriteMarkerAsync(markerPath, 0).ConfigureAwait(false);
            await Task.Delay(Timeout.InfiniteTimeSpan).ConfigureAwait(false);
            return 0;
        }
        catch (TaskCanceledException)
        {
            return 0;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine($"fixture-leaf:{exception.GetType().Name}");
            return 72;
        }
    }

    private static async Task WriteMarkerAsync(string path, int childPid)
    {
        string fullPath = Path.GetFullPath(path);
        string directory = Path.GetDirectoryName(fullPath)
            ?? throw new InvalidOperationException("The fixture marker has no parent directory.");
        Directory.CreateDirectory(directory);
        var marker = new Dictionary<string, object?>
        {
            ["pid"] = Environment.ProcessId,
            ["child_pid"] = childPid == 0 ? null : childPid,
            ["sid"] = WindowsIdentity.GetCurrent().User?.Value,
            ["session_id"] = Process.GetCurrentProcess().SessionId,
            ["window_station"] = ReadUserObjectName(NativeMethods.GetProcessWindowStation(), "GetProcessWindowStation"),
            ["desktop"] = ReadUserObjectName(NativeMethods.GetThreadDesktop(NativeMethods.GetCurrentThreadId()), "GetThreadDesktop"),
        };
        string temporary = Path.Combine(directory, $".{Path.GetFileName(path)}.{Guid.NewGuid():N}.tmp");
        try
        {
            await File.WriteAllTextAsync(temporary, JsonSerializer.Serialize(marker)).ConfigureAwait(false);
            File.Move(temporary, fullPath, overwrite: false);
        }
        finally
        {
            try { File.Delete(temporary); } catch (IOException) { } catch (UnauthorizedAccessException) { }
        }
    }

    private static string ReadUserObjectName(IntPtr handle, string api)
    {
        if (handle == IntPtr.Zero)
        {
            throw new NativeApiException(api, Marshal.GetLastWin32Error());
        }
        _ = NativeMethods.GetUserObjectInformation(handle, NativeMethods.UoiName, IntPtr.Zero, 0, out int required);
        int error = Marshal.GetLastWin32Error();
        if (required <= 0 || error != NativeMethods.ErrorInsufficientBuffer)
        {
            throw new NativeApiException($"{api}.GetNameSize", error);
        }
        IntPtr buffer = Marshal.AllocHGlobal(required);
        try
        {
            if (!NativeMethods.GetUserObjectInformation(handle, NativeMethods.UoiName, buffer, required, out _))
            {
                throw new NativeApiException($"{api}.GetName", Marshal.GetLastWin32Error());
            }
            return Marshal.PtrToStringUni(buffer) ?? throw new NativeApiException($"{api}.ReadName", 13);
        }
        finally
        {
            Marshal.FreeHGlobal(buffer);
        }
    }
}
