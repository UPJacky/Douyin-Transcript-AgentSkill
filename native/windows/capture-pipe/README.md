# Windows capture named-pipe boundary (source prototype)

This standalone .NET 10 x64 project contains a Windows SCM service entry point and named-pipe lifecycle source prototype for the Windows IPC boundary. It does **not** install the service, create per-capture worker identities, configure WFP, launch Chromium, or prove browser isolation. The shipped worker handler returns `BROWSER_ISOLATION_UNAVAILABLE` for every valid capture or short-link request.

## Wire contract

The JSON payloads use the v1 field names and validation limits from `skills/douyin-transcript/src/douyin_transcript/capture_ipc.py` and `skills/douyin-transcript/references/capture-ipc-v1.schema.json`. The Python codec returns naked JSON bytes; it does not define transport framing. This prototype adds the following framing around those compatible JSON payloads:

1. The client writes the fixed four-byte `DTP1` preamble. The server reads only this preamble, within one second, then authenticates the connected client. It replies with the fixed four-byte `DTA1` acknowledgment only after identity and allowlist checks pass; the client waits for this acknowledgment before sending the request.
2. Each request and result JSON payload is preceded by a four-byte unsigned little-endian byte length.
3. A successful capture result is followed by artifact blocks. Each block has a four-byte unsigned little-endian length from 1 through 65,536, then that many payload bytes. A zero length terminates the artifact. The client requires the declared byte count, SHA-256, terminator, and pipe EOF to match the result descriptor.
4. A resolve result has no artifact blocks. One pipe connection carries one request and is then closed.

Limits are 32 KiB per request JSON payload, 16 KiB per result JSON payload, 8 KiB UTF-8 source URL, 512 MiB media payload, 64 KiB per media block, four simultaneous connections, one second to receive the fixed preamble, five seconds for server authentication acknowledgment, 15 seconds to receive a request after peer authentication, five seconds to connect, and 15 minutes per exchange. The artifact-block length words add at most about 32 KiB to a maximum-size transfer.

The Python `capture_pipe_windows.py` adapter implements this framing and returns a result JSON frame plus a raw, request-bound artifact stream. It authenticates the server PID, session, and enabled service SID before sending the URL. The adapter is not selected by the default CLI because this source prototype has no installed service or production service-SID configuration.

## Peer identity checks

- The server creates the fixed local pipe using an explicit protected DACL for SYSTEM, its configured service SID, and configured client user SIDs.
- `PIPE_REJECT_REMOTE_CLIENTS` rejects remote named-pipe connections in the kernel.
- The server reads the fixed `DTP1` preamble under a one-second deadline, then obtains the connected client PID and session from the pipe APIs. It impersonates the client associated with that last read, reads that token's user SID, group SIDs, session ID, and logon authentication ID, then opens the connected PID and requires matching user SID, session ID, and logon AuthenticationId. The configured user SID and session allowlist is checked before it returns the fixed `DTA1` acknowledgment. The client must receive that acknowledgment before sending the URL-bearing request frame; the server reads the JSON under a separate 15-second deadline.
- The client obtains the connected server PID/session from the pipe APIs, opens that process token, and requires the configured service SID as the user SID or an enabled, non-deny-only token group, plus the configured session (production policy is expected to use session 0). The PID, session, token identity, and image path are taken from Windows APIs; the image path is diagnostic only and is not treated as a trust anchor.
- The server claims the first pipe instance with `FILE_FLAG_FIRST_PIPE_INSTANCE`; listener instances created afterward omit that flag. A same-name pipe instance already created by another process prevents startup instead of letting the service attach to a squatted endpoint.
- The local harness sets the current user SID/session as the test “service” identity so it can exercise the pipe without a service install or elevation. That verifies API plumbing only; it is **not** evidence for an installed service SID, service ACL, SYSTEM/session-0 operation, or rejection of another same-user process.

The service SID and process token are the intended server identity anchor. Installation still needs to configure a unique service SID and a protected service binary location. The user SID allowlist authorizes processes running as those users; this prototype does not attest a specific client executable or distinguish separate processes running under one allowed user.

## SCM service bootstrap and lifecycle

`--service` enters `StartServiceCtrlDispatcherW` for the fixed service name `DouyinTranscriptCapture`. It is accepted only when launched by the Windows Service Control Manager; an interactive invocation returns `ERROR_FAILED_SERVICE_CONTROLLER_CONNECT`. The service registers an extended control handler, reports `START_PENDING`, `RUNNING`, `STOP_PENDING`, and `STOPPED`, accepts Stop and Shutdown, and cancels/awaits the named-pipe host during shutdown. Startup errors report a stable service-specific failure code without logging URLs or local paths.

The service resolves the `NT SERVICE\DouyinTranscriptCapture` SID and verifies that the current Session 0 token has that SID enabled before the pipe listener is opened. An installer must register this exact service name, enable its service SID in the service token, protect the executable directory, and configure a least-privileged service account. This repository does not include or invoke a service installer.

The caller allowlist is read from `%ProgramData%\OpenAI\DouyinTranscript\service.json`:

```json
{
  "schema_version": 1,
  "client_user_sids": ["S-1-5-21-<machine-specific-user-sid>"]
}
```

The configuration path must already exist. Both application directories and the JSON file must have protected, non-inherited DACLs, be owned by SYSTEM or Administrators, and grant write-capable rights only to SYSTEM or Administrators. The JSON file must also grant the service SID read access. Reparse points, unknown or duplicate JSON properties, duplicate SIDs, and oversized configuration are rejected. The service SID and pipe name are fixed in code; the allowlisted client SIDs are the only configurable authorization inputs. Clients may connect from nonzero interactive session IDs, but the current host authenticates only user SID and session—it does not bind authorization to a particular client executable.

## Lease process-tree supervision source component

`LeaseProcessJob` is a standalone Windows lifecycle component for a future per-lease worker launcher. It creates an unnamed Job Object, sets and reads back exactly `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, and rejects either breakaway flag. Its caller must return a newly created suspended process and primary-thread handle. The component assigns the process to the job before resuming the primary thread, and accepts only the expected initial suspend count of one. Startup errors terminate and await the unassigned process or assigned job tree; normal stop terminates the tree, polls the job's active-process count to zero, and then closes handles. Closing the job is the kill-on-close fallback.

The `--self-test` harness exercises fake-API ordering and failure paths, then launches a harmless suspended copy of the harness. That process starts one child which inherits the job; the harness verifies both are members, keeps both alive through a bounded observation window, and confirms both exit after normal and injected-exception cleanup. The fixture uses only local processes and an exclusively created, owner-marked temporary directory that is containment-checked before removal. This validates the source component's local lifecycle on this Windows host; it does not prove service-account behavior, per-lease SID separation, Chromium containment, WFP egress, or live capture.

The component is **not wired to the SCM service or capture worker**. The service still uses `FailClosedCaptureWorker` and returns `BROWSER_ISOLATION_UNAVAILABLE`; this source slice does not change URL-capture readiness.

`--self-test` exercises the lifecycle state machine with a fake pipe host: startup, Stop/Shutdown while running, Stop during `START_PENDING`, cancellation, unexpected host exit, startup failure, and the interactive-session caller policy. A requested stop during startup reports `STOP_PENDING`, cancels and drains the host, then exits successfully as `STOPPED`. This is a source/harness check, not an SCM installation test. Even when the service is installed and reports `RUNNING`, its worker remains fail closed and returns `BROWSER_ISOLATION_UNAVAILABLE`; the service bootstrap does not mean that URL capture or P2 isolation is available.

## Build and local harness

The project pins the existing .NET SDK 10.0.401 in `global.json` and has no external package dependencies.

```powershell
dotnet build CapturePipe.csproj -c Release -p:Platform=x64
dotnet run --project CapturePipe.csproj -c Release -p:Platform=x64 -- --lease-process-job-self-test
dotnet run --project CapturePipe.csproj -c Release -p:Platform=x64 -- --self-test
```

The harness covers first-instance collision rejection, enabled/deny-only SID attribute handling, same-process OS peer identity checks, rejection of a disallowed session before any request frame is sent, timeout and recovery of all four listeners when clients omit the preamble, fail-closed capture and resolve replies, request size rejection, a multi-block artifact transfer with digest verification, client cancellation, and worker cancellation after disconnect. Its offline lease DNS suite passes 18 policy scenarios covering numeric resolver/port handoff, A and AAAA, CNAME chains within and across responses, private-address rejection, unrelated underscore-label DNS owners, loops/hop limits, truncation/question mismatch, per-response and aggregate answer caps, pinned-address caps, deadline expiry, caller cancellation, TTL aging, and conservative no-cache handling for negative families. The pinned numeric-IP TCP connector harness covers permit-before-connect ordering, rejection of unpinned/private targets, remote-endpoint verification, and connection/permit cleanup. The wire harness uses only loopback fixtures and checks A/AAAA/CNAME parsing, malformed compression-pointer boundaries, UDP truncation fallback to TCP, and UDP/TCP socket-handle closure on cancellation. The lease-job fixture checks fake-API startup/cleanup paths and real parent/child Job membership, survival through a bounded observation timeout, injected-exception cleanup, and direct exit waits for both processes. These fixtures do not validate public resolver behavior, spoofing resistance outside the connected local socket, DNSSEC, complete RRsets, production peer identity, service installation, WFP policy, production worker wiring, or Chromium egress.

The integration-only `--interop-test-server` command accepts only a randomly named `DouyinTranscript.Capture.InteropTest.<32 hex>` endpoint and supports fixed `artifact` and `cancel` probes under the current user's SID/session. It is used by `tests/integration/test_windows_capture_pipe.py` to exercise the Python adapter, token P/Invoke, framing, digest, EOF, and cancellation/draining of a pending overlapped read across separate Python and .NET processes. This still does not emulate a production service identity or Session 0.

## Remaining integration and trust gaps

- The source now has an SCM dispatcher/lifecycle and protected configuration reader, but the project still has no service registration/install command, upgrade/rollback logic, package signature/protected deployment path, or production service SID setup. The service entry point has not been installed or exercised under SCM.
- The named-pipe and media block headers are project-specific transport additions. A Python Windows adapter now implements them, but no packaged service SID or installed service exists, so it is not enabled by the default CLI.
- The Python/.NET interop test must run only against the test-only ephemeral endpoint; do not pass the fixed production pipe name to the test server.
- Worker handling is deliberately fail closed. `LeaseEgressPolicy` validates bounded A/AAAA/CNAME results; `NumericDnsQuestioner` supplies a bounded wire parser and numeric-resolver UDP/TCP transport; `LeaseTcpConnector` directly connects to one selected public numeric address from the validated set and returns the original hostname for TLS SNI/certificate validation. The connector requires a lease-scoped permit provider, but no production WFP permit provider exists and the connector is not wired to the capture handler. The DNS transport still has no DNSSEC authentication or complete-RRset/negative-SOA proof. A production worker must compose these pieces under its own lease identity. No browser capture, media download, lease lifecycle, or per-lease worker exists here.
- The current service-side host is an in-process protocol boundary. `LeaseProcessJob` now provides an offline-tested process-tree supervision source component, but it is not wired to the service or a worker, so the current host still cannot kill a production browser/worker tree.
- PID/session/token checks authenticate the OS peer identity snapshot, but do not attest the client executable. Any process running under an allowlisted user SID and session can attempt a connection; callers must be chosen accordingly.
- The artifact source must be seekable so the host can check declared length and digest before sending. The client checks the digest again. A caller must discard its destination if copying fails before verification completes.
- This local harness does not validate named-pipe ACL behavior across service/user accounts or prove the kernel remote-client rejection flag dynamically.
