using System.Runtime.InteropServices;
using System.Text.Json.Serialization;
using Wfp = Windows.Win32.NetworkManagement.WindowsFilteringPlatform;

namespace WfpPolicyPlan;

internal sealed record ManagedLayoutReportDocument(
    string ReportKind,
    string Architecture,
    string Runtime,
    string CsWin32Package,
    bool NativeSdkComparisonPerformed,
    string ValidationLimit,
    IReadOnlyList<StructLayoutEntry> Structures);

internal sealed record StructLayoutEntry(
    string Name,
    int Size,
    IReadOnlyList<FieldLayoutEntry> Fields);

internal sealed record FieldLayoutEntry(string Name, int Offset);

internal static class ManagedLayoutReport
{
    public static ManagedLayoutReportDocument Create()
    {
        if (!Environment.Is64BitProcess || RuntimeInformation.ProcessArchitecture != Architecture.X64)
        {
            throw new PlatformNotSupportedException("The layout report is pinned to an x64 process.");
        }

        StructLayoutEntry[] structs =
        [
            Describe<Wfp.FWPM_FILTER0>("FWPM_FILTER0",
                "filterKey", "displayData", "flags", "providerKey", "providerData", "layerKey", "subLayerKey",
                "weight", "numFilterConditions", "filterCondition", "action", "Anonymous", "reserved", "filterId", "effectiveWeight"),
            Describe<Wfp.FWPM_FILTER_CONDITION0>("FWPM_FILTER_CONDITION0", "fieldKey", "matchType", "conditionValue"),
            Describe<Wfp.FWPM_ACTION0>("FWPM_ACTION0", "type", "Anonymous"),
            Describe<Wfp.FWPM_ACTION0._Anonymous_e__Union>("FWPM_ACTION0.Anonymous", "filterType", "calloutKey"),
            Describe<Wfp.FWPM_SESSION0>("FWPM_SESSION0",
                "sessionKey", "displayData", "flags", "txnWaitTimeoutInMSec", "processId", "sid", "username", "kernelMode"),
            Describe<Wfp.FWPM_PROVIDER0>("FWPM_PROVIDER0", "providerKey", "displayData", "flags", "providerData", "serviceName"),
            Describe<Wfp.FWPM_SUBLAYER0>("FWPM_SUBLAYER0", "subLayerKey", "displayData", "flags", "providerKey", "providerData", "weight"),
            Describe<Wfp.FWP_CONDITION_VALUE0>("FWP_CONDITION_VALUE0", "type", "Anonymous"),
            Describe<Wfp.FWP_VALUE0>("FWP_VALUE0", "type", "Anonymous"),
        ];

        return new ManagedLayoutReportDocument(
            ReportKind: "managed-cswin32-layout-only",
            Architecture: RuntimeInformation.ProcessArchitecture.ToString(),
            Runtime: RuntimeInformation.FrameworkDescription,
            CsWin32Package: "Microsoft.Windows.CsWin32 0.3.360",
            NativeSdkComparisonPerformed: false,
            ValidationLimit: "Marshal.SizeOf/OffsetOf for CsWin32-generated managed declarations only. This is not a sizeof/offsetof comparison against fwpmu.h/fwpmtypes.h compiled by the Windows SDK, and it is not evidence that WFP behavior is correct.",
            Structures: structs);
    }

    private static StructLayoutEntry Describe<T>(string name, params string[] fields) where T : struct
    {
        var entries = fields.Select(field => new FieldLayoutEntry(field, OffsetOf<T>(field))).ToArray();
        return new StructLayoutEntry(name, Marshal.SizeOf<T>(), entries);
    }

    private static int OffsetOf<T>(string field) where T : struct => checked((int)Marshal.OffsetOf<T>(field));
}
