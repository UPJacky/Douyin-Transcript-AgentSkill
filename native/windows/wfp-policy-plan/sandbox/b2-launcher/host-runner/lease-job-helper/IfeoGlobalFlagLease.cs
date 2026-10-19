using Microsoft.Win32;
using System.Security.Cryptography;
using System.Text;

namespace DouyinTranscript.LeaseJobHelper;

internal sealed record IfeoGlobalFlagSnapshot(bool KeyExists, bool ValueExists, uint? Value);

internal interface IIfeoGlobalFlagStore
{
    IfeoGlobalFlagSnapshot Read(string imageName);
    void Write(string imageName, uint value);
    void DeleteValue(string imageName);
    void DeleteKeyIfEmpty(string imageName);
}

internal sealed class IfeoGlobalFlagLease
{
    internal const uint ShowLoaderSnaps = 0x00000002;

    private readonly IIfeoGlobalFlagStore _store;
    private readonly string _imageName;
    private readonly IfeoGlobalFlagSnapshot _original;
    private readonly Semaphore _semaphore;
    private bool _ownsSemaphore = true;
    private bool _restored;

    private IfeoGlobalFlagLease(IIfeoGlobalFlagStore store, string imageName,
        IfeoGlobalFlagSnapshot original, Semaphore semaphore)
    {
        _store = store;
        _imageName = imageName;
        _original = original;
        _semaphore = semaphore;
        EnabledValue = (original.Value ?? 0) | ShowLoaderSnaps;
    }

    internal uint EnabledValue { get; }
    internal IfeoGlobalFlagSnapshot Original => _original;

    internal static IfeoGlobalFlagLease Acquire(string imageName, IIfeoGlobalFlagStore? store = null)
    {
        ValidateImageName(imageName);
        store ??= new WindowsIfeoGlobalFlagStore();
        string semaphoreSuffix = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(imageName.ToUpperInvariant())));
        var semaphore = new Semaphore(initialCount: 1, maximumCount: 1, name: $"Global\\LunaIfeoGlobalFlag-{semaphoreSuffix}");
        bool ownsSemaphore = false;
        IfeoGlobalFlagLease? lease = null;
        try
        {
            ownsSemaphore = semaphore.WaitOne(TimeSpan.FromSeconds(5));
            if (!ownsSemaphore) throw new TimeoutException("The IFEO diagnostic semaphore was not acquired within the bound.");
            IfeoGlobalFlagSnapshot original = store.Read(imageName);
            lease = new IfeoGlobalFlagLease(store, imageName, original, semaphore);
            store.Write(imageName, lease.EnabledValue);
            IfeoGlobalFlagSnapshot readback = store.Read(imageName);
            if (!readback.KeyExists || !readback.ValueExists || readback.Value != lease.EnabledValue)
            {
                throw new InvalidDataException("IFEO GlobalFlag readback did not match the requested Loader Snaps flags.");
            }
            return lease;
        }
        catch (Exception applyError)
        {
            try
            {
                if (lease is not null) lease.Restore();
            }
            catch (Exception restoreError)
            {
                lease?.ReleaseForSandboxTeardown();
                throw new AggregateException("IFEO GlobalFlag setup failed and exact restoration also failed.", applyError, restoreError);
            }
            throw;
        }
        finally
        {
            if (lease is null)
            {
                if (ownsSemaphore)
                {
                    try { semaphore.Release(); } catch (SemaphoreFullException) { }
                }
                semaphore.Dispose();
            }
        }
    }

    internal IfeoGlobalFlagSnapshot Restore()
    {
        if (_restored)
        {
            IfeoGlobalFlagSnapshot alreadyRestored = _store.Read(_imageName);
            AssertMatchesOriginal(alreadyRestored);
            return alreadyRestored;
        }
        IfeoGlobalFlagSnapshot current = _store.Read(_imageName);
        if (_original.ValueExists)
        {
            if (current.ValueExists && current.Value == _original.Value)
            {
                _restored = true;
                ReleaseSemaphore();
                return current;
            }
            if (!current.ValueExists || current.Value != EnabledValue)
            {
                throw new InvalidOperationException("IFEO GlobalFlag changed outside this diagnostic; refusing to overwrite the new value.");
            }
            _store.Write(_imageName, _original.Value!.Value);
        }
        else
        {
            if (!current.ValueExists)
            {
                if (!_original.KeyExists && current.KeyExists)
                {
                    _store.DeleteKeyIfEmpty(_imageName);
                }
                current = _store.Read(_imageName);
                AssertMatchesOriginal(current);
                _restored = true;
                ReleaseSemaphore();
                return current;
            }
            if (current.Value != EnabledValue)
            {
                throw new InvalidOperationException("IFEO GlobalFlag changed outside this diagnostic; refusing to overwrite the new value.");
            }
            _store.DeleteValue(_imageName);
            if (!_original.KeyExists)
            {
                _store.DeleteKeyIfEmpty(_imageName);
            }
        }

        IfeoGlobalFlagSnapshot restored = _store.Read(_imageName);
        AssertMatchesOriginal(restored);
        _restored = true;
        ReleaseSemaphore();
        return restored;
    }

    internal void Dispose()
    {
        try
        {
            if (!_restored) _ = Restore();
        }
        finally
        {
            ReleaseSemaphore();
        }
    }

    internal void ReleaseForSandboxTeardown() => ReleaseSemaphore();

    private void AssertMatchesOriginal(IfeoGlobalFlagSnapshot actual)
    {
        if (actual.KeyExists != _original.KeyExists
            || actual.ValueExists != _original.ValueExists
            || actual.Value != _original.Value)
        {
            throw new InvalidOperationException("IFEO GlobalFlag did not return to its original key/value state.");
        }
    }

    private void ReleaseSemaphore()
    {
        if (!_ownsSemaphore) return;
        _ownsSemaphore = false;
        try { _semaphore.Release(); }
        finally { _semaphore.Dispose(); }
    }

    internal static void ValidateSelfTest()
    {
        var missing = new MemoryIfeoGlobalFlagStore();
        IfeoGlobalFlagLease missingLease = Acquire("probe-a.exe", missing);
        if (missingLease.EnabledValue != ShowLoaderSnaps || !missing.Read("probe-a.exe").KeyExists)
        {
            throw new InvalidOperationException("IFEO self-test failed to add Loader Snaps for a missing value.");
        }
        IfeoGlobalFlagSnapshot missingRestored = missingLease.Restore();
        if (missingRestored.KeyExists || missingRestored.ValueExists)
        {
            throw new InvalidOperationException("IFEO self-test did not remove a diagnostic-only key.");
        }

        var existing = new MemoryIfeoGlobalFlagStore();
        existing.Seed("probe-b.exe", keyExists: true, valueExists: true, value: 0x400);
        IfeoGlobalFlagLease existingLease = Acquire("probe-b.exe", existing);
        if (existingLease.EnabledValue != 0x402 || existingLease.Original.Value != 0x400)
        {
            throw new InvalidOperationException("IFEO self-test did not preserve pre-existing flag bits.");
        }
        _ = existingLease.Restore();
        IfeoGlobalFlagSnapshot existingRestored = existing.Read("probe-b.exe");
        if (!existingRestored.KeyExists || !existingRestored.ValueExists || existingRestored.Value != 0x400)
        {
            throw new InvalidOperationException("IFEO self-test did not restore the original DWORD value.");
        }

        var concurrent = new MemoryIfeoGlobalFlagStore();
        IfeoGlobalFlagLease concurrentLease = Acquire("probe-c.exe", concurrent);
        concurrent.Seed("probe-c.exe", keyExists: true, valueExists: true, value: 0x40);
        bool refusedOverwrite = false;
        try { _ = concurrentLease.Restore(); }
        catch (InvalidOperationException) { refusedOverwrite = true; }
        if (!refusedOverwrite || concurrent.Read("probe-c.exe").Value != 0x40)
        {
            throw new InvalidOperationException("IFEO self-test overwrote an unrelated concurrent value.");
        }
        concurrentLease.ReleaseForSandboxTeardown();

        var deletedOriginalKey = new MemoryIfeoGlobalFlagStore();
        deletedOriginalKey.Seed("probe-d.exe", keyExists: true, valueExists: false, value: null);
        IfeoGlobalFlagLease deletedKeyLease = Acquire("probe-d.exe", deletedOriginalKey);
        deletedOriginalKey.Remove("probe-d.exe");
        bool missingOriginalKeyRejected = false;
        try { _ = deletedKeyLease.Restore(); }
        catch (InvalidOperationException) { missingOriginalKeyRejected = true; }
        if (!missingOriginalKeyRejected)
        {
            throw new InvalidOperationException("IFEO self-test accepted a missing key that originally existed.");
        }
        deletedKeyLease.ReleaseForSandboxTeardown();
    }

    private static void ValidateImageName(string imageName)
    {
        if (string.IsNullOrWhiteSpace(imageName) || imageName.Length > 128
            || imageName is "." or ".."
            || imageName.IndexOfAny(['\\', '/', ':', '\0']) >= 0
            || !imageName.EndsWith(".exe", StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException("IFEO image name must be a single executable basename.", nameof(imageName));
        }
    }

    private sealed class MemoryIfeoGlobalFlagStore : IIfeoGlobalFlagStore
    {
        private readonly Dictionary<string, IfeoGlobalFlagSnapshot> _values = new(StringComparer.OrdinalIgnoreCase);

        internal void Seed(string imageName, bool keyExists, bool valueExists, uint? value) =>
            _values[imageName] = new IfeoGlobalFlagSnapshot(keyExists, valueExists, value);

        internal void Remove(string imageName) => _values.Remove(imageName);

        public IfeoGlobalFlagSnapshot Read(string imageName) =>
            _values.TryGetValue(imageName, out IfeoGlobalFlagSnapshot? value)
                ? value
                : new IfeoGlobalFlagSnapshot(false, false, null);

        public void Write(string imageName, uint value) =>
            _values[imageName] = new IfeoGlobalFlagSnapshot(true, true, value);

        public void DeleteValue(string imageName)
        {
            IfeoGlobalFlagSnapshot current = Read(imageName);
            _values[imageName] = current with { ValueExists = false, Value = null };
        }

        public void DeleteKeyIfEmpty(string imageName)
        {
            IfeoGlobalFlagSnapshot current = Read(imageName);
            if (!current.ValueExists) _values.Remove(imageName);
        }
    }

    private sealed class WindowsIfeoGlobalFlagStore : IIfeoGlobalFlagStore
    {
        private const string ParentPath = @"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options";

        public IfeoGlobalFlagSnapshot Read(string imageName)
        {
            using RegistryKey baseKey = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64);
            using RegistryKey? parent = baseKey.OpenSubKey(ParentPath, writable: false);
            if (parent is null)
            {
                throw new InvalidOperationException("The standard IFEO parent key is unavailable; no registry changes were made.");
            }
            using RegistryKey? imageKey = parent.OpenSubKey(imageName, writable: false);
            if (imageKey is null) return new IfeoGlobalFlagSnapshot(false, false, null);
            bool exists = imageKey.GetValueNames().Contains("GlobalFlag", StringComparer.OrdinalIgnoreCase);
            if (!exists) return new IfeoGlobalFlagSnapshot(true, false, null);
            if (imageKey.GetValueKind("GlobalFlag") != RegistryValueKind.DWord)
            {
                throw new InvalidOperationException("Existing IFEO GlobalFlag has a non-DWORD type; refusing to modify it.");
            }
            object? raw = imageKey.GetValue("GlobalFlag", null, RegistryValueOptions.DoNotExpandEnvironmentNames);
            if (raw is not int dword)
            {
                throw new InvalidOperationException("Existing IFEO GlobalFlag DWORD could not be read losslessly.");
            }
            return new IfeoGlobalFlagSnapshot(true, true, unchecked((uint)dword));
        }

        public void Write(string imageName, uint value)
        {
            using RegistryKey baseKey = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64);
            using RegistryKey? parent = baseKey.OpenSubKey(ParentPath, writable: true);
            if (parent is null) throw new InvalidOperationException("The standard IFEO parent key is not writable.");
            using RegistryKey imageKey = parent.CreateSubKey(imageName, writable: true)
                ?? throw new InvalidOperationException("The IFEO image key could not be opened for writing.");
            imageKey.SetValue("GlobalFlag", unchecked((int)value), RegistryValueKind.DWord);
            imageKey.Flush();
        }

        public void DeleteValue(string imageName)
        {
            using RegistryKey baseKey = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64);
            using RegistryKey? parent = baseKey.OpenSubKey(ParentPath, writable: true);
            using RegistryKey? imageKey = parent?.OpenSubKey(imageName, writable: true);
            if (imageKey is null) return;
            imageKey.DeleteValue("GlobalFlag", throwOnMissingValue: false);
            imageKey.Flush();
        }

        public void DeleteKeyIfEmpty(string imageName)
        {
            using RegistryKey baseKey = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64);
            using RegistryKey? parent = baseKey.OpenSubKey(ParentPath, writable: true);
            if (parent is null) return;
            using RegistryKey? imageKey = parent.OpenSubKey(imageName, writable: false);
            if (imageKey is null) return;
            if (imageKey.ValueCount != 0 || imageKey.SubKeyCount != 0)
            {
                throw new InvalidOperationException("New IFEO key is no longer empty; refusing to delete other diagnostic data.");
            }
            parent.DeleteSubKey(imageName, throwOnMissingSubKey: false);
            parent.Flush();
        }
    }
}
