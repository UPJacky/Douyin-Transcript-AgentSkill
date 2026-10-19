# Retired: the former probe installed an unconditional IPv4 ALE connect block.
# It could interrupt every host IPv4 connection when run outside Windows Sandbox.
# Keep this entry point fail-closed so stale .wsb files cannot reapply that policy.
$ErrorActionPreference = 'Stop'
throw [System.InvalidOperationException]::new(
    'This all-app IPv4 WFP smoke is retired and cannot run. Do not invoke it on the host. Use the C# materializer Sandbox probe only after reviewing its current safety requirements.'
)
