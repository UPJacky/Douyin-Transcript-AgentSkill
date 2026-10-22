using System.Security.Cryptography;
using System.Security.Principal;
using System.Net;
using System.Net.Sockets;
using System.Buffers.Binary;
using System.Text;
using System.Text.Json;
using System.IO.Pipes;
using Microsoft.Win32.SafeHandles;
using System.Diagnostics;

namespace DouyinTranscript.CapturePipe;

internal static class LocalHarness
{
    public static async Task RunInteropTestServerAsync(string pipeNameWithoutPrefix, string mode)
    {
        const string requiredPrefix = "DouyinTranscript.Capture.InteropTest.";
        if (!pipeNameWithoutPrefix.StartsWith(requiredPrefix, StringComparison.Ordinal)
            || pipeNameWithoutPrefix.Length != requiredPrefix.Length + 32
            || !pipeNameWithoutPrefix[requiredPrefix.Length..].All(Uri.IsHexDigit))
        {
            throw new ArgumentException("The interop test endpoint name is invalid.", nameof(pipeNameWithoutPrefix));
        }
        if (mode is not ("artifact" or "cancel"))
        {
            throw new ArgumentException("The interop test mode is invalid.", nameof(mode));
        }

        PeerIdentity current = PeerAuthenticator.ReadCurrentProcessIdentity();
        var servicePolicy = new ServicePeerPolicy(current.UserSid, current.SessionId);
        ClientPeerPolicy clientPolicy = ClientPeerPolicy.Create([current.UserSid], [current.SessionId]);
        string pipeName = $@"\\.\pipe\{pipeNameWithoutPrefix}";
        ICaptureWorker worker;
        Task? workerStarted = null;
        if (mode == "artifact")
        {
            byte[] artifact = Enumerable.Range(0, 133_777).Select(value => (byte)(value * 31)).ToArray();
            worker = new HarnessArtifactWorker(artifact);
        }
        else
        {
            var cancellationWorker = new CancellationProbeWorker();
            worker = cancellationWorker;
            workerStarted = cancellationWorker.Started.Task;
        }
        var host = new CapturePipeHost(
            pipeName,
            servicePolicy,
            clientPolicy,
            worker);
        using var stopping = new CancellationTokenSource();
        Task server = host.ServeAsync(stopping.Token);
        await host.Started.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
        Console.WriteLine("READY");
        Console.Out.Flush();
        try
        {
            if (workerStarted is not null)
            {
                await workerStarted.WaitAsync(TimeSpan.FromSeconds(30)).ConfigureAwait(false);
                Console.WriteLine("WORKER_STARTED");
                Console.Out.Flush();
            }
            _ = await Console.In.ReadLineAsync().ConfigureAwait(false);
        }
        finally
        {
            stopping.Cancel();
            await IgnoreExpectedStopAsync(server);
        }
    }

    public static async Task RunAsync()
    {
        await LeaseProcessJobHarness.RunAsync().ConfigureAwait(false);
        await ServiceLifecycleHarness.RunAsync().ConfigureAwait(false);
        await VerifyLeaseEgressPolicyAsync().ConfigureAwait(false);
        await VerifyLeaseTcpConnectorAsync().ConfigureAwait(false);
        await HttpsConnectTunnelHarness.RunAsync().ConfigureAwait(false);
        await VerifyDnsWireAndTransportAsync().ConfigureAwait(false);
        await VerifyArtifactValidationBeforePublishAsync().ConfigureAwait(false);
        Assert(PeerIdentity.IsEffectiveGroup(NativeMethods.GroupEnabled), "enabled service SID group was rejected");
        Assert(!PeerIdentity.IsEffectiveGroup(NativeMethods.GroupUseForDenyOnly), "deny-only SID group was accepted");
        Assert(!PeerIdentity.IsEffectiveGroup(NativeMethods.GroupEnabled | NativeMethods.GroupUseForDenyOnly),
            "enabled deny-only SID group was accepted");
        PeerIdentity current = PeerAuthenticator.ReadCurrentProcessIdentity();
        var servicePolicy = new ServicePeerPolicy(current.UserSid, current.SessionId);
        ClientPeerPolicy clientPolicy = ClientPeerPolicy.Create([current.UserSid], [current.SessionId]);
        string pipeNameWithoutPrefix = $"DouyinTranscript.Capture.SelfTest.{Guid.NewGuid():N}";
        string pipeName = $@"\\.\pipe\{pipeNameWithoutPrefix}";
        VerifyPipeFirstInstanceProtection(pipeName, clientPolicy, current.UserSid);
        using var stopping = new CancellationTokenSource();
        var failClosedHost = new CapturePipeHost(pipeName, servicePolicy, clientPolicy, new FailClosedCaptureWorker());
        Task failClosedServer = failClosedHost.ServeAsync(stopping.Token);
        await failClosedHost.Started.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
        var client = new CapturePipeClient(servicePolicy, pipeNameWithoutPrefix);

        try
        {
            byte[] captureRequest = CreateCaptureRequest("12345678-1234-4234-8234-123456789abc");
            await using (PipeCaptureExchange exchange = await client.ExchangeAsync(captureRequest, CancellationToken.None))
            {
                CaptureResponseEnvelope response = CaptureProtocol.ValidateResponse(exchange.ResultFrame, CaptureProtocol.ValidateRequest(captureRequest));
                Assert(!response.IsSuccess, "default worker returned a success result");
                Assert(Encoding.UTF8.GetString(exchange.ResultFrame).Contains("BROWSER_ISOLATION_UNAVAILABLE", StringComparison.Ordinal),
                    "default worker did not fail closed with the isolation-unavailable code");
            }

            byte[] resolveRequest = CreateResolveRequest("12345678-1234-4234-8234-123456789abd");
            await using (PipeCaptureExchange exchange = await client.ExchangeAsync(resolveRequest, CancellationToken.None))
            {
                CaptureResponseEnvelope response = CaptureProtocol.ValidateResponse(exchange.ResultFrame, CaptureProtocol.ValidateRequest(resolveRequest));
                Assert(!response.IsSuccess, "default worker resolved a URL despite having no capture worker");
            }

            await AssertRejectsOversizedFrameAsync(client);
            AssertRejectsBidiControlInUrl();
        }
        finally
        {
            stopping.Cancel();
            await IgnoreExpectedStopAsync(failClosedServer);
        }

        await VerifyArtifactTransferAsync(pipeName, pipeNameWithoutPrefix, servicePolicy, clientPolicy);
        await VerifyServiceWideCaptureLeaseAsync(servicePolicy, clientPolicy);
        await VerifyDisconnectCancellationAsync(pipeName, servicePolicy, clientPolicy, client);
        await VerifyClientAuthenticationBeforeRequestAsync(pipeName, pipeNameWithoutPrefix, servicePolicy, current);
        await VerifyPreambleTimeoutReleasesListenersAsync(pipeName, pipeNameWithoutPrefix, servicePolicy, current);
        Console.WriteLine("PASS local named-pipe first-instance, identity, fail-closed, framing, artifact, and disconnect harness");
    }

    private static async Task VerifyServiceWideCaptureLeaseAsync(
        ServicePeerPolicy servicePolicy,
        ClientPeerPolicy clientPolicy)
    {
        string pipeNameWithoutPrefix = $"DouyinTranscript.Capture.LeaseTest.{Guid.NewGuid():N}";
        string pipeName = $@"\\.\pipe\{pipeNameWithoutPrefix}";
        var worker = new LeaseProbeWorker();
        using var stopping = new CancellationTokenSource();
        var host = new CapturePipeHost(pipeName, servicePolicy, clientPolicy, worker);
        Task server = host.ServeAsync(stopping.Token);
        await host.Started.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
        var client = new CapturePipeClient(servicePolicy, pipeNameWithoutPrefix);
        try
        {
            Task<PipeCaptureExchange> firstTask = client.ExchangeAsync(
                CreateCaptureRequest("52345678-1234-4234-8234-123456789abc"),
                CancellationToken.None);
            await worker.FirstStarted.Task.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);

            byte[] busyRequest = CreateCaptureRequest("52345678-1234-4234-8234-123456789abd");
            await using (PipeCaptureExchange busyExchange = await client.ExchangeAsync(
                busyRequest,
                CancellationToken.None).WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false))
            {
                CaptureResponseEnvelope busyResponse = CaptureProtocol.ValidateResponse(
                    busyExchange.ResultFrame,
                    CaptureProtocol.ValidateRequest(busyRequest));
                Assert(!busyResponse.IsSuccess
                    && Encoding.UTF8.GetString(busyExchange.ResultFrame).Contains("\"code\":\"SERVICE_BUSY\"", StringComparison.Ordinal),
                    "a concurrent request was not rejected with SERVICE_BUSY");
            }
            Assert(worker.CallCount == 1, "a busy request reached the capture worker");

            byte[] busyResolveRequest = CreateResolveRequest(Guid.NewGuid().ToString("D"));
            await using (PipeCaptureExchange busyResolveExchange = await client.ExchangeAsync(
                busyResolveRequest,
                CancellationToken.None).WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false))
            {
                CaptureResponseEnvelope busyResolveResponse = CaptureProtocol.ValidateResponse(
                    busyResolveExchange.ResultFrame,
                    CaptureProtocol.ValidateRequest(busyResolveRequest));
                Assert(!busyResolveResponse.IsSuccess
                    && ReadFailureCode(busyResolveExchange.ResultFrame) == "SERVICE_BUSY",
                    "a concurrent short-link resolve request was not rejected with SERVICE_BUSY");
            }
            Assert(worker.CallCount == 1, "a busy resolve request reached the capture worker");

            worker.ReleaseFirst.TrySetResult();
            await using (PipeCaptureExchange firstExchange = await firstTask
                .WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false))
            {
                Assert(!firstExchange.Response.IsSuccess, "lease probe worker returned an unexpected success");
            }

            using (var callerCancellation = new CancellationTokenSource())
            {
                Task<PipeCaptureExchange> cancelledTask = client.ExchangeAsync(
                    CreateCaptureRequest("52345678-1234-4234-8234-123456789abe"),
                    callerCancellation.Token);
                await worker.CancellationStarted.Task.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
                callerCancellation.Cancel();
                try
                {
                    await cancelledTask.ConfigureAwait(false);
                    throw new InvalidOperationException("A cancelled lease probe unexpectedly returned a response.");
                }
                catch (OperationCanceledException)
                {
                }
                catch (IOException)
                {
                }
                await worker.CancellationObserved.Task.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
            }

            bool workerExceptionObserved = false;
            for (int attempt = 0; attempt < 50 && !workerExceptionObserved; attempt++)
            {
                byte[] exceptionRequest = CreateCaptureRequest(Guid.NewGuid().ToString("D"));
                await using PipeCaptureExchange exceptionExchange = await client.ExchangeAsync(
                    exceptionRequest,
                    CancellationToken.None).WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
                CaptureResponseEnvelope exceptionResponse = CaptureProtocol.ValidateResponse(
                    exceptionExchange.ResultFrame,
                    CaptureProtocol.ValidateRequest(exceptionRequest));
                string errorCode = ReadFailureCode(exceptionExchange.ResultFrame);
                if (errorCode == "SERVICE_BUSY")
                {
                    await Task.Delay(20).ConfigureAwait(false);
                    continue;
                }
                Assert(!exceptionResponse.IsSuccess && errorCode == "INTERNAL_ERROR",
                    "a worker exception did not produce the bounded internal error response");
                workerExceptionObserved = true;
            }
            Assert(workerExceptionObserved, "the capture lease did not recover after cancellation");

            bool recoveryObserved = false;
            for (int attempt = 0; attempt < 50 && !recoveryObserved; attempt++)
            {
                byte[] recoveredRequest = CreateCaptureRequest(Guid.NewGuid().ToString("D"));
                await using PipeCaptureExchange recoveredExchange = await client.ExchangeAsync(
                    recoveredRequest,
                    CancellationToken.None).WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
                CaptureResponseEnvelope recoveredResponse = CaptureProtocol.ValidateResponse(
                    recoveredExchange.ResultFrame,
                    CaptureProtocol.ValidateRequest(recoveredRequest));
                string errorCode = ReadFailureCode(recoveredExchange.ResultFrame);
                if (errorCode == "SERVICE_BUSY")
                {
                    await Task.Delay(20).ConfigureAwait(false);
                    continue;
                }
                Assert(!recoveredResponse.IsSuccess && errorCode == "BROWSER_ISOLATION_UNAVAILABLE",
                    "lease recovery probe returned an unexpected response");
                recoveryObserved = true;
            }
            Assert(recoveryObserved, "the capture lease did not recover after the worker exception");
            Assert(worker.CallCount == 4, "the capture lease did not recover after cancellation and worker failure");
        }
        finally
        {
            worker.ReleaseFirst.TrySetResult();
            stopping.Cancel();
            await IgnoreExpectedStopAsync(server);
        }
    }

    private static async Task VerifyLeaseEgressPolicyAsync()
    {
        const string hostname = "video.example";
        IPAddress resolver = IPAddress.Parse("1.1.1.1");
        var successfulQuestioner = new FakeNumericDnsQuestioner((name, type) => type switch
        {
            LeaseDnsQuestionType.A => new LeaseDnsResponse(name, type, 0, false,
            [
                new LeaseDnsRecord(name, LeaseDnsRecordType.CName, "edge.example"),
                new LeaseDnsRecord("edge.example", LeaseDnsRecordType.A, "93.184.216.34"),
            ]),
            LeaseDnsQuestionType.Aaaa => new LeaseDnsResponse(name, type, 0, false,
            [
                new LeaseDnsRecord(name, LeaseDnsRecordType.CName, "edge.example"),
                new LeaseDnsRecord("edge.example", LeaseDnsRecordType.Aaaa, "2606:4700:4700::1111"),
            ]),
            _ => throw new InvalidOperationException("Unexpected DNS question type."),
        });
        LeaseResolvedAddressSet resolved = await LeaseEgressPolicy.ResolveAsync(
            hostname,
            resolver,
            successfulQuestioner,
            CancellationToken.None).ConfigureAwait(false);
        Assert(resolved.Hostname == hostname, "DNS result did not retain its canonical hostname");
        Assert(resolved.Addresses.Select(address => address.ToString()).SequenceEqual(
            ["93.184.216.34", "2606:4700:4700::1111"]), "DNS resolver did not return the complete public A/AAAA pin set");
        Assert(successfulQuestioner.Calls.Count == 2, "DNS resolver did not ask for both A and AAAA");
        Assert(successfulQuestioner.Calls.All(call => call.Resolver.Equals(resolver) && call.Port == LeaseEgressPolicy.DnsPort),
            "DNS questioner was not given the numeric resolver and fixed DNS port");

        var ttlQuestioner = new FakeNumericDnsQuestioner((name, type) => type == LeaseDnsQuestionType.A
            ? new LeaseDnsResponse(name, type, 0, false,
            [
                new LeaseDnsRecord(name, LeaseDnsRecordType.CName, "edge.example", 600),
                new LeaseDnsRecord("edge.example", LeaseDnsRecordType.A, "93.184.216.34", 550),
            ],
            Stopwatch.GetTimestamp())
            : new LeaseDnsResponse(name, type, 0, false,
            [
                new LeaseDnsRecord(name, LeaseDnsRecordType.CName, "edge.example", 500),
                new LeaseDnsRecord("edge.example", LeaseDnsRecordType.Aaaa, "2606:4700:4700::1111", 400),
            ],
            Stopwatch.GetTimestamp()));
        LeaseResolvedAddressSet ttlResolved = await LeaseEgressPolicy.ResolveAsync(
            hostname,
            resolver,
            ttlQuestioner,
            CancellationToken.None).ConfigureAwait(false);
        Assert(ttlResolved.CacheTtlSeconds is > 295 and <= LeaseEgressPolicy.MaxCacheTtlSeconds,
            "DNS pin lifetime was not capped at the configured maximum TTL");

        long alreadyAgedTimestamp = Stopwatch.GetTimestamp() - (2 * Stopwatch.Frequency);
        var agedTtlQuestioner = new FakeNumericDnsQuestioner((name, type) => new LeaseDnsResponse(
            name,
            type,
            0,
            false,
            [new LeaseDnsRecord(name, type == LeaseDnsQuestionType.A ? LeaseDnsRecordType.A : LeaseDnsRecordType.Aaaa,
                type == LeaseDnsQuestionType.A ? "8.8.8.8" : "2606:4700:4700::1111", 5)],
            alreadyAgedTimestamp));
        LeaseResolvedAddressSet agedTtlResolved = await LeaseEgressPolicy.ResolveAsync(
            hostname, resolver, agedTtlQuestioner, CancellationToken.None).ConfigureAwait(false);
        Assert(agedTtlResolved.CacheTtlSeconds is > 0 and <= 3,
            "DNS cache lifetime did not subtract time elapsed since the response arrived");

        var negativeFamilyQuestioner = new FakeNumericDnsQuestioner((name, type) =>
            new LeaseDnsResponse(name, type, 0, false,
                type == LeaseDnsQuestionType.A
                    ? [new LeaseDnsRecord(name, LeaseDnsRecordType.A, "8.8.8.8", 60)]
                    : []));
        LeaseResolvedAddressSet negativeFamilyResolved = await LeaseEgressPolicy.ResolveAsync(
            hostname, resolver, negativeFamilyQuestioner, CancellationToken.None).ConfigureAwait(false);
        Assert(negativeFamilyResolved.CacheTtlSeconds is null,
            "an address set with an unbounded negative-family TTL was marked cacheable");

        var unrelatedPrivateAnswerQuestioner = new FakeNumericDnsQuestioner((name, type) =>
            new LeaseDnsResponse(name, type, 0, false, type == LeaseDnsQuestionType.A
                ? [
                    new LeaseDnsRecord(name, LeaseDnsRecordType.A, "8.8.8.8"),
                    new LeaseDnsRecord("unrelated.example", LeaseDnsRecordType.A, "192.168.1.1"),
                ]
                : [
                    new LeaseDnsRecord(name, LeaseDnsRecordType.Aaaa, "2606:4700:4700::1111"),
                    new LeaseDnsRecord("unrelated-v6.example", LeaseDnsRecordType.Aaaa, "fd00::1"),
                ]));
        LeaseResolvedAddressSet unrelatedPrivateResolved = await LeaseEgressPolicy.ResolveAsync(
            hostname,
            resolver,
            unrelatedPrivateAnswerQuestioner,
            CancellationToken.None).ConfigureAwait(false);
        Assert(unrelatedPrivateResolved.Addresses.Count == 2,
            "an unrelated private DNS answer incorrectly rejected the reachable public addresses");

        var unrelatedServiceNameQuestioner = new FakeNumericDnsQuestioner((name, type) =>
            new LeaseDnsResponse(name, type, 0, false, type == LeaseDnsQuestionType.A
                ? [
                    new LeaseDnsRecord(name, LeaseDnsRecordType.A, "8.8.8.8"),
                    new LeaseDnsRecord("_service.example", LeaseDnsRecordType.CName, "target._service.example"),
                    new LeaseDnsRecord("target._service.example", LeaseDnsRecordType.A, "192.168.1.10"),
                ]
                : [new LeaseDnsRecord(name, LeaseDnsRecordType.Aaaa, "2606:4700:4700::1111")]));
        LeaseResolvedAddressSet unrelatedServiceResolved = await LeaseEgressPolicy.ResolveAsync(
            hostname, resolver, unrelatedServiceNameQuestioner, CancellationToken.None).ConfigureAwait(false);
        Assert(unrelatedServiceResolved.Addresses.Count == 2,
            "an unrelated legal DNS owner with underscore labels rejected reachable public answers");

        var splitCnameQuestioner = new FakeNumericDnsQuestioner((name, type) =>
        {
            if (name == hostname)
            {
                return new LeaseDnsResponse(name, type, 0, false,
                    [new LeaseDnsRecord(name, LeaseDnsRecordType.CName, "edge.example")]);
            }
            return new LeaseDnsResponse(name, type, 0, false,
                [new LeaseDnsRecord(name, type == LeaseDnsQuestionType.A ? LeaseDnsRecordType.A : LeaseDnsRecordType.Aaaa,
                    type == LeaseDnsQuestionType.A ? "93.184.216.35" : "2606:4700:4700::1001")]);
        });
        LeaseResolvedAddressSet splitResolved = await LeaseEgressPolicy.ResolveAsync(
            hostname,
            resolver,
            splitCnameQuestioner,
            CancellationToken.None).ConfigureAwait(false);
        Assert(splitCnameQuestioner.Calls.Count == 4, "DNS resolver did not follow CNAME targets across responses for both families");
        Assert(splitResolved.Addresses.Count == 2, "cross-response CNAME resolution lost an address family");

        var mixedAddressQuestioner = new FakeNumericDnsQuestioner((name, type) =>
            new LeaseDnsResponse(name, type, 0, false, type == LeaseDnsQuestionType.A
                ? [new LeaseDnsRecord(name, LeaseDnsRecordType.A, "8.8.8.8")]
                : [new LeaseDnsRecord(name, LeaseDnsRecordType.Aaaa, "fd00::1")]));
        await AssertDnsRejectedAsync(hostname, resolver, mixedAddressQuestioner,
            "mixed public/private DNS answers were accepted").ConfigureAwait(false);

        var carrierGradeNatQuestioner = new FakeNumericDnsQuestioner((name, type) =>
            new LeaseDnsResponse(name, type, 0, false, type == LeaseDnsQuestionType.A
                ? [new LeaseDnsRecord(name, LeaseDnsRecordType.A, "100.68.0.1")]
                : [new LeaseDnsRecord(name, LeaseDnsRecordType.Aaaa, "2606:4700:4700::1001")]));
        await AssertDnsRejectedAsync(hostname, resolver, carrierGradeNatQuestioner,
            "an address inside the carrier-grade NAT range was accepted").ConfigureAwait(false);

        var loopQuestioner = new FakeNumericDnsQuestioner((name, type) =>
            new LeaseDnsResponse(name, type, 0, false,
            [
                new LeaseDnsRecord(name, LeaseDnsRecordType.CName, "alias.example"),
                new LeaseDnsRecord("alias.example", LeaseDnsRecordType.CName, name),
            ]));
        await AssertDnsRejectedAsync(hostname, resolver, loopQuestioner,
            "a CNAME loop was accepted").ConfigureAwait(false);

        var truncatedQuestioner = new FakeNumericDnsQuestioner((name, type) =>
            new LeaseDnsResponse(name, type, 0, true, [new LeaseDnsRecord(name, LeaseDnsRecordType.A, "8.8.8.8")]));
        await AssertDnsRejectedAsync(hostname, resolver, truncatedQuestioner,
            "a truncated DNS response was accepted").ConfigureAwait(false);

        var wrongQuestionQuestioner = new FakeNumericDnsQuestioner((name, type) =>
            new LeaseDnsResponse("other.example", type, 0, false, [new LeaseDnsRecord(name, LeaseDnsRecordType.A, "8.8.8.8")]));
        await AssertDnsRejectedAsync(hostname, resolver, wrongQuestionQuestioner,
            "a DNS response for another question was accepted").ConfigureAwait(false);

        LeaseDnsRecord[] excessiveCnameChain = Enumerable.Range(0, LeaseEgressPolicy.MaxCnameHops + 1)
            .Select(index => new LeaseDnsRecord(
                index == 0 ? hostname : $"alias{index}.example",
                LeaseDnsRecordType.CName,
                $"alias{index + 1}.example"))
            .ToArray();
        var excessiveCnameQuestioner = new FakeNumericDnsQuestioner((name, type) =>
            new LeaseDnsResponse(name, type, 0, false, excessiveCnameChain));
        await AssertDnsRejectedAsync(hostname, resolver, excessiveCnameQuestioner,
            "an overlong CNAME chain was accepted").ConfigureAwait(false);

        LeaseDnsRecord[] excessiveAnswers = Enumerable.Range(0, LeaseEgressPolicy.MaxAnswersPerResponse + 1)
            .Select(_ => new LeaseDnsRecord(hostname, LeaseDnsRecordType.A, "8.8.8.8"))
            .ToArray();
        var excessiveAnswerQuestioner = new FakeNumericDnsQuestioner((name, type) =>
            new LeaseDnsResponse(name, type, 0, false, excessiveAnswers));
        await AssertDnsRejectedAsync(hostname, resolver, excessiveAnswerQuestioner,
            "an oversized DNS answer set was accepted").ConfigureAwait(false);

        LeaseDnsRecord[] largeAnswerChain = Enumerable.Range(0, LeaseEgressPolicy.MaxAnswersPerResponse)
            .Select(index => index == 0
                ? new LeaseDnsRecord(hostname, LeaseDnsRecordType.CName, "alias1.example")
                : new LeaseDnsRecord($"noise{index}.example", LeaseDnsRecordType.A, "8.8.8.8"))
            .ToArray();
        LeaseDnsResponse CreateLargeAnswerResponse(string name, string target)
        {
            LeaseDnsRecord[] records = largeAnswerChain
                .Select(record => record.Owner == hostname
                    ? record with { Owner = name, Data = target }
                    : record)
                .ToArray();
            return new LeaseDnsResponse(name, LeaseDnsQuestionType.A, 0, false, records);
        }
        var excessiveTotalAnswersQuestioner = new FakeNumericDnsQuestioner((name, type) =>
            type != LeaseDnsQuestionType.A
                ? new LeaseDnsResponse(name, type, 0, false, [])
                : name switch
                {
                    "video.example" => CreateLargeAnswerResponse(name, "alias1.example"),
                    "alias1.example" => CreateLargeAnswerResponse(name, "alias2.example"),
                    _ => CreateLargeAnswerResponse(name, "alias3.example"),
                });
        await AssertDnsRejectedAsync(hostname, resolver, excessiveTotalAnswersQuestioner,
            "DNS answers beyond the total response limit were accepted").ConfigureAwait(false);

        var excessivePinnedAddressesQuestioner = new FakeNumericDnsQuestioner((name, type) =>
            new LeaseDnsResponse(name, type, 0, false, type == LeaseDnsQuestionType.A
                ? Enumerable.Range(1, LeaseEgressPolicy.MaxPinnedAddresses)
                    .Select(index => new LeaseDnsRecord(name, LeaseDnsRecordType.A, $"8.8.4.{index}"))
                    .ToArray()
                : [new LeaseDnsRecord(name, LeaseDnsRecordType.Aaaa, "2606:4700:4700::1001")]));
        await AssertDnsRejectedAsync(hostname, resolver, excessivePinnedAddressesQuestioner,
            "too many pinned DNS addresses were accepted").ConfigureAwait(false);

        await VerifyLeaseEgressCancellationAsync(hostname, resolver).ConfigureAwait(false);

        var privateResolverQuestioner = new FakeNumericDnsQuestioner((name, type) =>
            throw new InvalidOperationException("Questioner must not be called for a private resolver."));
        await AssertDnsRejectedAsync(hostname, IPAddress.Parse("127.0.0.1"), privateResolverQuestioner,
            "a private DNS resolver was accepted").ConfigureAwait(false);

        Console.WriteLine("PASS 18 bounded lease DNS policy scenarios using an offline fake transport");
    }

    private static async Task VerifyDnsWireAndTransportAsync()
    {
        const string hostname = "video.example";
        var query = DnsWireCodec.CreateQuery(hostname, LeaseDnsQuestionType.A);
        byte[] validAResponse = CreateDnsResponse(
            query,
            0x8180,
            [CreateDnsRecord(1, [93, 184, 216, 34])]);
        LeaseDnsResponse parsed = DnsWireCodec.ParseResponse(validAResponse, query);
        Assert(parsed.Answers.Count == 1
            && parsed.Answers[0].Owner == hostname
            && parsed.Answers[0].Data == "93.184.216.34"
            && parsed.Answers[0].TimeToLiveSeconds == 60,
            "DNS wire parser did not decode a compressed A answer and its TTL");

        byte[] validCnameResponse = CreateDnsResponse(
            query,
            0x8180,
            [CreateDnsRecord(5, EncodeDnsName("edge.example"))]);
        LeaseDnsResponse parsedCname = DnsWireCodec.ParseResponse(validCnameResponse, query);
        Assert(parsedCname.Answers.Count == 1
            && parsedCname.Answers[0].Type == LeaseDnsRecordType.CName
            && parsedCname.Answers[0].Data == "edge.example",
            "DNS wire parser did not decode a bounded CNAME RDATA name");

        byte[] wrongId = (byte[])validAResponse.Clone();
        wrongId[0] ^= 0xff;
        AssertDnsWireRejected(() => DnsWireCodec.ParseResponse(wrongId, query),
            "DNS parser accepted a response with a mismatched transaction ID");

        byte[] wrongQuestion = (byte[])validAResponse.Clone();
        wrongQuestion[13] = (byte)'x';
        AssertDnsWireRejected(() => DnsWireCodec.ParseResponse(wrongQuestion, query),
            "DNS parser accepted a response for another question name");

        int answerOffset = query.Packet.Length;
        byte[] selfPointer = CreateDnsRecord(1, [93, 184, 216, 34], (ushort)(0xc000 | answerOffset));
        byte[] pointerLoopResponse = CreateDnsResponse(query, 0x8180, [selfPointer]);
        AssertDnsWireRejected(() => DnsWireCodec.ParseResponse(pointerLoopResponse, query),
            "DNS parser accepted a forward/self-referential compression pointer");

        byte[] nonNameRdata = [3, (byte)'a', (byte)'b', (byte)'c', 0];
        byte[] opaqueRecord = CreateDnsRecord(16, nonNameRdata);
        int opaqueRdataOffset = query.Packet.Length + opaqueRecord.Length - nonNameRdata.Length;
        byte[] pointerIntoRdata = CreateDnsRecord(
            1,
            [93, 184, 216, 34],
            checked((ushort)(0xc000 | opaqueRdataOffset)));
        byte[] invalidBoundaryResponse = CreateDnsResponse(query, 0x8180, [opaqueRecord, pointerIntoRdata]);
        AssertDnsWireRejected(() => DnsWireCodec.ParseResponse(invalidBoundaryResponse, query),
            "DNS parser accepted a backward pointer into non-name RDATA bytes");

        byte[] excessiveCountResponse = (byte[])query.Packet.Clone();
        BinaryPrimitives.WriteUInt16BigEndian(excessiveCountResponse.AsSpan(2, 2), 0x8180);
        BinaryPrimitives.WriteUInt16BigEndian(excessiveCountResponse.AsSpan(6, 2),
            checked((ushort)(LeaseEgressPolicy.MaxAnswersPerResponse + 1)));
        AssertDnsWireRejected(() => DnsWireCodec.ParseResponse(excessiveCountResponse, query),
            "DNS parser accepted an answer count beyond the configured cap");

        byte[] malformedAResponse = CreateDnsResponse(query, 0x8180, [CreateDnsRecord(1, [93, 184, 216])]);
        AssertDnsWireRejected(() => DnsWireCodec.ParseResponse(malformedAResponse, query),
            "DNS parser accepted an A record with the wrong RDATA length");

        byte[] truncatedResponse = CreateDnsResponse(query, 0x8380, []);
        Assert(DnsWireCodec.ParseResponse(truncatedResponse, query).IsTruncated,
            "DNS parser did not preserve the UDP truncation flag for TCP fallback");

        await VerifyNumericDnsPermitDenialAsync(hostname).ConfigureAwait(false);
        Console.WriteLine("PASS bounded DNS wire parser scenarios");
        if (!CanBindLoopbackDnsSockets(out SocketException? socketException))
        {
            Console.WriteLine(
                $"SKIP local DNS UDP/TCP transport fixtures: runner denied loopback sockets ({socketException!.SocketErrorCode}).");
            return;
        }

        try
        {
            await VerifyNumericDnsUdpAsync(hostname).ConfigureAwait(false);
            await VerifyNumericDnsTcpFallbackAsync(hostname).ConfigureAwait(false);
            await VerifyNumericDnsCancellationAsync(hostname).ConfigureAwait(false);
            await VerifyNumericDnsTcpCancellationAsync(hostname).ConfigureAwait(false);
            Console.WriteLine("PASS DNS UDP/TCP fallback and local socket-cancellation fixtures");
        }
        catch (SocketException exception) when (exception.SocketErrorCode == SocketError.AccessDenied)
        {
            Console.WriteLine(
                "SKIP local DNS UDP/TCP transport fixtures: runner denied a loopback socket operation (AccessDenied).");
        }
    }

    private static bool CanBindLoopbackDnsSockets(out SocketException? socketException)
    {
        try
        {
            using (var udpSocket = new Socket(AddressFamily.InterNetwork, SocketType.Dgram, ProtocolType.Udp))
            {
                udpSocket.Bind(new IPEndPoint(IPAddress.Loopback, 0));
            }

            var tcpListener = new TcpListener(IPAddress.Loopback, 0);
            tcpListener.Start();
            tcpListener.Stop();
            socketException = null;
            return true;
        }
        catch (SocketException exception) when (exception.SocketErrorCode == SocketError.AccessDenied)
        {
            socketException = exception;
            return false;
        }
    }

    private static async Task VerifyLeaseTcpConnectorAsync()
    {
        IPAddress pinnedAddress = IPAddress.Parse("8.8.8.8");
        var resolved = new LeaseResolvedAddressSet("API.Example.com", [pinnedAddress], 60);
        var order = new List<string>();
        var permits = new FakeLeaseUpstreamPermitProvider(order);
        var dialer = new FakeLeaseTcpDialer(new IPEndPoint(pinnedAddress, LeaseEgressPolicy.HttpsPort), order);

        await using (LeaseTcpConnection connection = await LeaseTcpConnector.ConnectAsync(
            resolved,
            pinnedAddress,
            permits,
            dialer,
            TimeSpan.FromSeconds(2),
            CancellationToken.None).ConfigureAwait(false))
        {
            Assert(connection.Hostname == "api.example.com", "the original TLS hostname was not canonicalized");
            Assert(connection.RemoteEndPoint.Equals(new IPEndPoint(pinnedAddress, LeaseEgressPolicy.HttpsPort)),
                "the connector did not retain the numeric pinned endpoint");
            Assert(order.SequenceEqual(["permit", "connect"]),
                "the endpoint permit was not acquired before opening the socket");
            Assert(connection.Stream.CanRead && connection.Stream.CanWrite,
                "the connected stream was not exposed to the lease caller");
        }
        Assert(dialer.LastConnection?.Disposed == true, "disposing the lease connection did not close its socket handle");
        Assert(permits.LastPermit?.Disposed == true, "disposing the lease connection did not revoke its endpoint permit");

        var rejectedPermits = new FakeLeaseUpstreamPermitProvider([]);
        var rejectedDialer = new FakeLeaseTcpDialer(
            new IPEndPoint(IPAddress.Parse("1.1.1.1"), LeaseEgressPolicy.HttpsPort), []);
        await AssertLeaseConnectRejectedAsync(
            resolved,
            IPAddress.Parse("1.1.1.1"),
            rejectedPermits,
            rejectedDialer,
            "an address outside the pinned set was accepted").ConfigureAwait(false);
        Assert(rejectedPermits.LastPermit is null && rejectedDialer.LastConnection is null,
            "an unpinned address reached policy or socket setup");

        var privateSet = new LeaseResolvedAddressSet("local.example", [IPAddress.Loopback], null);
        await AssertLeaseConnectRejectedAsync(
            privateSet,
            IPAddress.Loopback,
            rejectedPermits,
            rejectedDialer,
            "a private destination was accepted by the upstream connector").ConfigureAwait(false);

        var wrongEndpointPermits = new FakeLeaseUpstreamPermitProvider([]);
        var wrongEndpointDialer = new FakeLeaseTcpDialer(
            new IPEndPoint(IPAddress.Parse("1.1.1.1"), LeaseEgressPolicy.HttpsPort), []);
        await AssertLeaseConnectRejectedAsync(
            resolved,
            pinnedAddress,
            wrongEndpointPermits,
            wrongEndpointDialer,
            "a socket connected to an endpoint outside its pinned target").ConfigureAwait(false);
        Assert(wrongEndpointDialer.LastConnection?.Disposed == true
            && wrongEndpointPermits.LastPermit?.Disposed == true,
            "a wrong-endpoint connection failure did not dispose both the socket and its permit");

        Console.WriteLine("PASS pinned numeric-IP TCP connector ordering, validation, and cleanup scenarios");
    }

    private static async Task AssertLeaseConnectRejectedAsync(
        LeaseResolvedAddressSet resolved,
        IPAddress address,
        ILeaseUpstreamPermitProvider permitProvider,
        ILeaseTcpDialer dialer,
        string message)
    {
        try
        {
            await LeaseTcpConnector.ConnectAsync(
                resolved,
                address,
                permitProvider,
                dialer,
                TimeSpan.FromSeconds(2),
                CancellationToken.None).ConfigureAwait(false);
        }
        catch (InvalidOperationException)
        {
            return;
        }
        catch (InvalidDataException)
        {
            return;
        }

        throw new InvalidOperationException(message);
    }

    private static async Task VerifyNumericDnsPermitDenialAsync(string hostname)
    {
        var order = new List<string>();
        var sockets = new TrackingDnsSocketFactory(order);
        var permits = new FakeLeaseDnsPermitProvider(order, () => sockets.AllCreatedSocketsClosed) { DenyNext = true };
        var questioner = new NumericDnsQuestioner(permits, sockets.CreateUdpClient, sockets.CreateTcpClient);

        try
        {
            _ = await questioner.QueryAsync(
                IPAddress.Loopback,
                53,
                hostname,
                LeaseDnsQuestionType.A,
                CancellationToken.None).ConfigureAwait(false);
            throw new InvalidOperationException("DNS query continued after its lease permit was denied.");
        }
        catch (InvalidOperationException exception) when (exception.Message == "Harness DNS permit denied.")
        {
        }

        Assert(sockets.UdpHandles.Count == 0 && sockets.TcpHandles.Count == 0,
            "DNS permit denial still created a network socket");
        Assert(order.SequenceEqual(["permit-udp"]),
            "DNS permit denial continued into socket setup");
    }

    private static async Task VerifyNumericDnsUdpAsync(string hostname)
    {
        var order = new List<string>();
        var sockets = new TrackingDnsSocketFactory(order);
        var permits = new FakeLeaseDnsPermitProvider(order, () => sockets.AllCreatedSocketsClosed);
        var questioner = new NumericDnsQuestioner(permits, sockets.CreateUdpClient, sockets.CreateTcpClient);
        using var server = new UdpClient(new IPEndPoint(IPAddress.Loopback, 0));
        var endpoint = (IPEndPoint)server.Client.LocalEndPoint!;
        Task serverTask = Task.Run(async () =>
        {
            UdpReceiveResult request = await server.ReceiveAsync().ConfigureAwait(false);
            DnsWireQuery query = CreateHarnessQuery(request.Buffer, hostname, LeaseDnsQuestionType.A);
            byte[] response = CreateDnsResponse(query, 0x8180, [CreateDnsRecord(1, [93, 184, 216, 35])]);
            _ = await server.SendAsync(response, response.Length, request.RemoteEndPoint).ConfigureAwait(false);
        });

        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(3));
        LeaseDnsResponse response = await questioner.QueryAsync(
            IPAddress.Loopback,
            endpoint.Port,
            hostname,
            LeaseDnsQuestionType.A,
            deadline.Token).ConfigureAwait(false);
        await serverTask.WaitAsync(TimeSpan.FromSeconds(3)).ConfigureAwait(false);
        Assert(response.Answers.Single().Data == "93.184.216.35",
            "numeric DNS questioner did not receive a response from its connected UDP peer");
        Assert(order.SequenceEqual(["permit-udp", "socket-udp", "release-udp"]),
            "DNS UDP permit was not acquired before socket creation and released after socket closure");
        Assert(permits.Permits.Single().SocketsClosedAtRelease,
            "DNS UDP permit was released before its socket closed");
    }

    private static async Task VerifyNumericDnsTcpFallbackAsync(string hostname)
    {
        var order = new List<string>();
        var sockets = new TrackingDnsSocketFactory(order);
        var permits = new FakeLeaseDnsPermitProvider(order, () => sockets.AllCreatedSocketsClosed);
        var questioner = new NumericDnsQuestioner(permits, sockets.CreateUdpClient, sockets.CreateTcpClient);
        var tcpListener = new TcpListener(IPAddress.Loopback, 0);
        tcpListener.Start();
        int port = ((IPEndPoint)tcpListener.LocalEndpoint).Port;
        using var udpServer = new UdpClient(new IPEndPoint(IPAddress.Loopback, port));
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(3));
        Task udpTask = Task.Run(async () =>
        {
            UdpReceiveResult request = await udpServer.ReceiveAsync(deadline.Token).ConfigureAwait(false);
            DnsWireQuery query = CreateHarnessQuery(request.Buffer, hostname, LeaseDnsQuestionType.A);
            byte[] truncated = CreateDnsResponse(query, 0x8380, []);
            _ = await udpServer.SendAsync(truncated, truncated.Length, request.RemoteEndPoint).ConfigureAwait(false);
        }, deadline.Token);
        Task tcpTask = Task.Run(async () =>
        {
            using TcpClient peer = await tcpListener.AcceptTcpClientAsync(deadline.Token).ConfigureAwait(false);
            NetworkStream stream = peer.GetStream();
            byte[] lengthPrefix = new byte[sizeof(ushort)];
            await stream.ReadExactlyAsync(lengthPrefix, deadline.Token).ConfigureAwait(false);
            int queryLength = BinaryPrimitives.ReadUInt16BigEndian(lengthPrefix);
            byte[] request = new byte[queryLength];
            await stream.ReadExactlyAsync(request, deadline.Token).ConfigureAwait(false);
            DnsWireQuery query = CreateHarnessQuery(request, hostname, LeaseDnsQuestionType.A);
            byte[] response = CreateDnsResponse(query, 0x8180, [CreateDnsRecord(1, [93, 184, 216, 36])]);
            byte[] framedResponse = new byte[sizeof(ushort) + response.Length];
            BinaryPrimitives.WriteUInt16BigEndian(framedResponse.AsSpan(0, sizeof(ushort)), checked((ushort)response.Length));
            response.CopyTo(framedResponse, sizeof(ushort));
            await stream.WriteAsync(framedResponse, deadline.Token).ConfigureAwait(false);
        }, deadline.Token);

        try
        {
            LeaseDnsResponse response = await questioner.QueryAsync(
                IPAddress.Loopback,
                port,
                hostname,
                LeaseDnsQuestionType.A,
                deadline.Token).ConfigureAwait(false);
            await Task.WhenAll(udpTask, tcpTask).WaitAsync(TimeSpan.FromSeconds(3)).ConfigureAwait(false);
            Assert(!response.IsTruncated && response.Answers.Single().Data == "93.184.216.36",
                "DNS questioner did not retry a truncated UDP answer over length-prefixed TCP");
            Assert(order.SequenceEqual([
                    "permit-udp", "socket-udp", "release-udp",
                    "permit-tcp", "socket-tcp", "release-tcp"]),
                "DNS TCP fallback did not release the UDP permit before acquiring a TCP permit");
            Assert(permits.Permits.Count == 2
                && permits.Permits.All(permit => permit.Disposed && permit.SocketsClosedAtRelease),
                "DNS transport permit was not released after its matching socket closed");
        }
        finally
        {
            deadline.Cancel();
            tcpListener.Stop();
        }
    }

    private static async Task VerifyNumericDnsCancellationAsync(string hostname)
    {
        var order = new List<string>();
        var sockets = new TrackingDnsSocketFactory(order);
        var permits = new FakeLeaseDnsPermitProvider(order, () => sockets.AllCreatedSocketsClosed);
        var questioner = new NumericDnsQuestioner(permits, sockets.CreateUdpClient, sockets.CreateTcpClient);
        using var server = new UdpClient(new IPEndPoint(IPAddress.Loopback, 0));
        var endpoint = (IPEndPoint)server.Client.LocalEndPoint!;
        Task<UdpReceiveResult> receive = server.ReceiveAsync();
        using var cancellation = new CancellationTokenSource();
        Task<LeaseDnsResponse> pending = questioner.QueryAsync(
            IPAddress.Loopback,
            endpoint.Port,
            hostname,
            LeaseDnsQuestionType.A,
            cancellation.Token).AsTask();
        _ = await receive.WaitAsync(TimeSpan.FromSeconds(2)).ConfigureAwait(false);
        cancellation.Cancel();
        try
        {
            _ = await pending.WaitAsync(TimeSpan.FromSeconds(2)).ConfigureAwait(false);
            throw new InvalidOperationException("A pending numeric DNS socket ignored caller cancellation.");
        }
        catch (OperationCanceledException) when (cancellation.IsCancellationRequested)
        {
        }
        Assert(sockets.UdpHandles.Count == 1 && sockets.UdpHandles[0].IsClosed,
            "UDP cancellation completed without closing the underlying socket handle");
        Assert(permits.Permits.Single().Disposed && permits.Permits.Single().SocketsClosedAtRelease,
            "UDP cancellation leaked its permit or released it before closing the socket");
    }

    private static async Task VerifyNumericDnsTcpCancellationAsync(string hostname)
    {
        var order = new List<string>();
        var sockets = new TrackingDnsSocketFactory(order);
        var permits = new FakeLeaseDnsPermitProvider(order, () => sockets.AllCreatedSocketsClosed);
        var questioner = new NumericDnsQuestioner(permits, sockets.CreateUdpClient, sockets.CreateTcpClient);
        var tcpListener = new TcpListener(IPAddress.Loopback, 0);
        tcpListener.Start();
        int port = ((IPEndPoint)tcpListener.LocalEndpoint).Port;
        using var udpServer = new UdpClient(new IPEndPoint(IPAddress.Loopback, port));
        using var cancellation = new CancellationTokenSource();
        using var serverStopping = new CancellationTokenSource();
        var tcpRequestRead = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        Task udpTask = Task.Run(async () =>
        {
            UdpReceiveResult request = await udpServer.ReceiveAsync(serverStopping.Token).ConfigureAwait(false);
            DnsWireQuery query = CreateHarnessQuery(request.Buffer, hostname, LeaseDnsQuestionType.A);
            byte[] truncated = CreateDnsResponse(query, 0x8380, []);
            _ = await udpServer.SendAsync(truncated, truncated.Length, request.RemoteEndPoint).ConfigureAwait(false);
        }, serverStopping.Token);
        Task tcpTask = Task.Run(async () =>
        {
            using TcpClient peer = await tcpListener.AcceptTcpClientAsync(serverStopping.Token).ConfigureAwait(false);
            NetworkStream stream = peer.GetStream();
            byte[] lengthPrefix = new byte[sizeof(ushort)];
            await stream.ReadExactlyAsync(lengthPrefix, serverStopping.Token).ConfigureAwait(false);
            int queryLength = BinaryPrimitives.ReadUInt16BigEndian(lengthPrefix);
            byte[] request = new byte[queryLength];
            await stream.ReadExactlyAsync(request, serverStopping.Token).ConfigureAwait(false);
            tcpRequestRead.TrySetResult();
            await Task.Delay(Timeout.InfiniteTimeSpan, serverStopping.Token).ConfigureAwait(false);
        }, serverStopping.Token);

        Task<LeaseDnsResponse> pending = questioner.QueryAsync(
            IPAddress.Loopback,
            port,
            hostname,
            LeaseDnsQuestionType.A,
            cancellation.Token).AsTask();
        try
        {
            await tcpRequestRead.Task.WaitAsync(TimeSpan.FromSeconds(2)).ConfigureAwait(false);
            cancellation.Cancel();
            try
            {
                _ = await pending.WaitAsync(TimeSpan.FromSeconds(2)).ConfigureAwait(false);
                throw new InvalidOperationException("A pending DNS-over-TCP socket ignored caller cancellation.");
            }
            catch (OperationCanceledException) when (cancellation.IsCancellationRequested)
            {
            }
            Assert(sockets.UdpHandles.Count == 1 && sockets.UdpHandles[0].IsClosed,
                "UDP truncation fallback did not release its UDP socket before TCP completion");
            Assert(sockets.TcpHandles.Count == 1 && sockets.TcpHandles[0].IsClosed,
                "TCP cancellation completed without closing the underlying socket handle");
            Assert(permits.Permits.Count == 2 && permits.Permits.All(permit => permit.Disposed),
                "DNS-over-TCP cancellation leaked a transport permit");
            Assert(permits.Permits.All(permit => permit.SocketsClosedAtRelease),
                "DNS cancellation released a permit before its matching transport socket closed");
        }
        finally
        {
            serverStopping.Cancel();
            tcpListener.Stop();
            try
            {
                await Task.WhenAll(udpTask, tcpTask).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (serverStopping.IsCancellationRequested)
            {
            }
            catch (ObjectDisposedException) when (serverStopping.IsCancellationRequested)
            {
            }
        }
    }

    private static DnsWireQuery CreateHarnessQuery(byte[] packet, string hostname, LeaseDnsQuestionType questionType) =>
        new(BinaryPrimitives.ReadUInt16BigEndian(packet.AsSpan(0, sizeof(ushort))), packet, hostname, questionType);

    private static byte[] CreateDnsResponse(DnsWireQuery query, ushort flags, IReadOnlyList<byte[]> answers)
    {
        int answersLength = answers.Sum(answer => answer.Length);
        byte[] response = new byte[query.Packet.Length + answersLength];
        query.Packet.CopyTo(response, 0);
        BinaryPrimitives.WriteUInt16BigEndian(response.AsSpan(2, 2), flags);
        BinaryPrimitives.WriteUInt16BigEndian(response.AsSpan(6, 2), checked((ushort)answers.Count));
        int offset = query.Packet.Length;
        foreach (byte[] answer in answers)
        {
            answer.CopyTo(response, offset);
            offset += answer.Length;
        }
        return response;
    }

    private static byte[] CreateDnsRecord(ushort type, byte[] data, ushort? ownerPointer = null)
    {
        using var record = new MemoryStream();
        if (ownerPointer is ushort pointer)
        {
            WriteDnsUInt16(record, pointer);
        }
        else
        {
            record.Write([0xc0, 0x0c]);
        }
        WriteDnsUInt16(record, type);
        WriteDnsUInt16(record, 1);
        WriteDnsUInt32(record, 60);
        WriteDnsUInt16(record, checked((ushort)data.Length));
        record.Write(data);
        return record.ToArray();
    }

    private static byte[] EncodeDnsName(string hostname)
    {
        using var encoded = new MemoryStream();
        foreach (string label in hostname.Split('.'))
        {
            byte[] bytes = Encoding.ASCII.GetBytes(label);
            encoded.WriteByte(checked((byte)bytes.Length));
            encoded.Write(bytes);
        }
        encoded.WriteByte(0);
        return encoded.ToArray();
    }

    private static void WriteDnsUInt16(Stream stream, ushort value)
    {
        Span<byte> encoded = stackalloc byte[sizeof(ushort)];
        BinaryPrimitives.WriteUInt16BigEndian(encoded, value);
        stream.Write(encoded);
    }

    private static void WriteDnsUInt32(Stream stream, uint value)
    {
        Span<byte> encoded = stackalloc byte[sizeof(uint)];
        BinaryPrimitives.WriteUInt32BigEndian(encoded, value);
        stream.Write(encoded);
    }

    private static void AssertDnsWireRejected(Action action, string message)
    {
        try
        {
            action();
        }
        catch (InvalidDataException)
        {
            return;
        }
        throw new InvalidOperationException(message);
    }

    private static async Task VerifyLeaseEgressCancellationAsync(string hostname, IPAddress resolver)
    {
        var timeoutQuestioner = new WaitingNumericDnsQuestioner();
        try
        {
            _ = await LeaseEgressPolicy.ResolveAsync(
                hostname,
                resolver,
                timeoutQuestioner,
                CancellationToken.None,
                TimeSpan.FromMilliseconds(100)).ConfigureAwait(false);
            throw new InvalidOperationException("DNS deadline did not stop a pending question.");
        }
        catch (TimeoutException)
        {
        }
        await timeoutQuestioner.Cancelled.Task.WaitAsync(TimeSpan.FromSeconds(2)).ConfigureAwait(false);

        var callerQuestioner = new WaitingNumericDnsQuestioner();
        using var callerCancellation = new CancellationTokenSource();
        Task<LeaseResolvedAddressSet> pending = LeaseEgressPolicy.ResolveAsync(
            hostname,
            resolver,
            callerQuestioner,
            callerCancellation.Token,
            TimeSpan.FromSeconds(1));
        await callerQuestioner.Started.Task.WaitAsync(TimeSpan.FromSeconds(2)).ConfigureAwait(false);
        callerCancellation.Cancel();
        try
        {
            _ = await pending.ConfigureAwait(false);
            throw new InvalidOperationException("Caller cancellation did not stop DNS resolution.");
        }
        catch (OperationCanceledException) when (callerCancellation.IsCancellationRequested)
        {
        }
        await callerQuestioner.Cancelled.Task.WaitAsync(TimeSpan.FromSeconds(2)).ConfigureAwait(false);
    }

    private static async Task AssertDnsRejectedAsync(
        string hostname,
        IPAddress resolver,
        FakeNumericDnsQuestioner questioner,
        string message)
    {
        try
        {
            _ = await LeaseEgressPolicy.ResolveAsync(hostname, resolver, questioner, CancellationToken.None).ConfigureAwait(false);
        }
        catch (InvalidOperationException)
        {
            return;
        }
        throw new InvalidOperationException(message);
    }

    private static void VerifyPipeFirstInstanceProtection(
        string pipeName,
        ClientPeerPolicy clientPolicy,
        string serviceSid)
    {
        using SafePipeHandle squatter = NativeMethods.CreateSecurePipe(
            pipeName,
            clientPolicy.UserSids.ToArray(),
            serviceSid,
            firstPipeInstance: true);
        try
        {
            using SafePipeHandle rejected = NativeMethods.CreateSecurePipe(
                pipeName,
                clientPolicy.UserSids.ToArray(),
                serviceSid,
                firstPipeInstance: true);
            throw new InvalidOperationException("A second first pipe instance was accepted.");
        }
        catch (System.ComponentModel.Win32Exception exception) when (exception.NativeErrorCode == 5)
        {
        }
    }

    private static async Task VerifyArtifactTransferAsync(
        string pipeName,
        string pipeNameWithoutPrefix,
        ServicePeerPolicy servicePolicy,
        ClientPeerPolicy clientPolicy)
    {
        byte[] artifact = Enumerable.Range(0, 133_777).Select(value => (byte)(value * 31)).ToArray();
        var worker = new HarnessArtifactWorker(artifact);
        using var stopping = new CancellationTokenSource();
        var host = new CapturePipeHost(pipeName, servicePolicy, clientPolicy, worker);
        Task server = host.ServeAsync(stopping.Token);
        await host.Started.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
        byte[] request = CreateCaptureRequest("22345678-1234-4234-8234-123456789abc");
        var client = new CapturePipeClient(servicePolicy, pipeNameWithoutPrefix);
        try
        {
            await using PipeCaptureExchange exchange = await client.ExchangeAsync(request, CancellationToken.None);
            using var received = new MemoryStream();
            await exchange.CopyArtifactToAsync(received, CancellationToken.None).ConfigureAwait(false);
            Assert(received.ToArray().SequenceEqual(artifact), "transferred artifact bytes changed");
            CaptureExecutionContext executionContext = await worker.ContextCaptured.Task
                .WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
            PeerIdentity current = PeerAuthenticator.ReadCurrentProcessIdentity();
            Assert(executionContext.OperationId != Guid.Empty, "capture operation ID was not generated by the host");
            Assert(executionContext.AuthenticatedPeer.ProcessId == current.ProcessId, "worker received a different authenticated process ID");
            Assert(executionContext.AuthenticatedPeer.SessionId == current.SessionId, "worker received a different authenticated session ID");
            Assert(executionContext.AuthenticatedPeer.UserSid == current.UserSid, "worker received a different authenticated user SID");
        }
        finally
        {
            stopping.Cancel();
            await IgnoreExpectedStopAsync(server);
        }
    }

    private static async Task VerifyArtifactValidationBeforePublishAsync()
    {
        byte[] payload = [0x10, 0x20, 0x30, 0x40, 0x50];
        string digest = Convert.ToHexString(SHA256.HashData(payload));

        await AssertRejectedArtifactLeavesDestinationUnchangedAsync(
            CreateArtifactWireFrame(payload, terminalMarker: 1),
            payload.Length,
            digest,
            "invalid terminal marker").ConfigureAwait(false);
        await AssertRejectedArtifactLeavesDestinationUnchangedAsync(
            CreateArtifactWireFrame(payload, trailingBytes: [0xFF]),
            payload.Length,
            digest,
            "trailing artifact data").ConfigureAwait(false);
        await AssertRejectedArtifactLeavesDestinationUnchangedAsync(
            CreateArtifactWireFrame(payload),
            payload.Length,
            Convert.ToHexString(SHA256.HashData([0x99])),
            "digest mismatch").ConfigureAwait(false);
        await AssertRejectedArtifactLeavesDestinationUnchangedAsync(
            CreateArtifactWireFrame(payload, chunkSize: (uint)(payload.Length + 1)),
            payload.Length,
            digest,
            "chunk exceeds declared size").ConfigureAwait(false);

        using var source = new MemoryStream(CreateArtifactWireFrame(payload), writable: false);
        using var destination = new MemoryStream();
        byte[] prefix = [0xA5, 0x5A];
        await destination.WriteAsync(prefix).ConfigureAwait(false);
        await ArtifactTransfer.CopyAndValidateArtifactAsync(
            source,
            destination,
            payload.Length,
            digest,
            CancellationToken.None).ConfigureAwait(false);
        byte[] expected = [.. prefix, .. payload];
        Assert(destination.ToArray().SequenceEqual(expected),
            "verified artifact was not appended after the destination prefix");
    }

    private static async Task AssertRejectedArtifactLeavesDestinationUnchangedAsync(
        byte[] frame,
        long sizeBytes,
        string sha256,
        string caseName)
    {
        using var source = new MemoryStream(frame, writable: false);
        using var destination = new MemoryStream();
        byte[] original = [0xC1, 0xD2, 0xE3];
        await destination.WriteAsync(original).ConfigureAwait(false);
        long originalPosition = destination.Position;

        try
        {
            await ArtifactTransfer.CopyAndValidateArtifactAsync(
                source,
                destination,
                sizeBytes,
                sha256,
                CancellationToken.None).ConfigureAwait(false);
            throw new InvalidOperationException($"Artifact with {caseName} was unexpectedly accepted.");
        }
        catch (CaptureProtocolException)
        {
        }

        Assert(destination.ToArray().SequenceEqual(original),
            $"artifact with {caseName} changed the destination before validation completed");
        Assert(destination.Position == originalPosition,
            $"artifact with {caseName} moved the destination before validation completed");
    }

    private static byte[] CreateArtifactWireFrame(
        byte[] payload,
        uint? chunkSize = null,
        uint terminalMarker = 0,
        byte[]? trailingBytes = null)
    {
        trailingBytes ??= [];
        byte[] frame = new byte[sizeof(uint) + payload.Length + sizeof(uint) + trailingBytes.Length];
        BinaryPrimitives.WriteUInt32LittleEndian(frame, chunkSize ?? checked((uint)payload.Length));
        payload.CopyTo(frame.AsSpan(sizeof(uint)));
        BinaryPrimitives.WriteUInt32LittleEndian(frame.AsSpan(sizeof(uint) + payload.Length), terminalMarker);
        trailingBytes.CopyTo(frame.AsSpan(sizeof(uint) + payload.Length + sizeof(uint)));
        return frame;
    }

    private static async Task VerifyDisconnectCancellationAsync(
        string pipeName,
        ServicePeerPolicy servicePolicy,
        ClientPeerPolicy clientPolicy,
        CapturePipeClient client)
    {
        var worker = new CancellationProbeWorker();
        using var stopping = new CancellationTokenSource();
        var host = new CapturePipeHost(pipeName, servicePolicy, clientPolicy, worker);
        Task server = host.ServeAsync(stopping.Token);
        await host.Started.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
        using var callerCancellation = new CancellationTokenSource();
        try
        {
            Task<PipeCaptureExchange> exchangeTask = client.ExchangeAsync(
                CreateCaptureRequest("32345678-1234-4234-8234-123456789abc"),
                callerCancellation.Token);
            await worker.Started.Task.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
            callerCancellation.Cancel();
            try
            {
                await exchangeTask.ConfigureAwait(false);
                throw new InvalidOperationException("Cancelled client unexpectedly received a result.");
            }
            catch (OperationCanceledException)
            {
            }
            catch (IOException)
            {
            }
            await worker.Cancelled.Task.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
        }
        finally
        {
            stopping.Cancel();
            await IgnoreExpectedStopAsync(server);
        }
    }

    private static async Task VerifyClientAuthenticationBeforeRequestAsync(
        string pipeName,
        string pipeNameWithoutPrefix,
        ServicePeerPolicy servicePolicy,
        PeerIdentity current)
    {
        uint deniedSession = current.SessionId == 0 ? 1u : current.SessionId - 1;
        ClientPeerPolicy deniedPolicy = ClientPeerPolicy.Create([current.UserSid], [deniedSession]);
        var worker = new CallCountingWorker();
        using var stopping = new CancellationTokenSource();
        var host = new CapturePipeHost(pipeName, servicePolicy, deniedPolicy, worker);
        Task server = host.ServeAsync(stopping.Token);
        await host.Started.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
        await using var client = new NamedPipeClientStream(
            ".",
            pipeNameWithoutPrefix,
            PipeDirection.InOut,
            PipeOptions.Asynchronous);
        try
        {
            await client.ConnectAsync(5_000).ConfigureAwait(false);
            await PipeFrames.WriteClientPreambleAsync(client, CancellationToken.None).ConfigureAwait(false);
            byte[] response = new byte[1];
            int read = await client.ReadAsync(response)
                .AsTask()
                .WaitAsync(TimeSpan.FromSeconds(5))
                .ConfigureAwait(false);
            Assert(read == 0, "a disallowed client received a protocol response");
            Assert(!worker.WasCalled, "a disallowed client reached the capture worker");
        }
        finally
        {
            stopping.Cancel();
            await IgnoreExpectedStopAsync(server);
        }
    }

    private static async Task VerifyPreambleTimeoutReleasesListenersAsync(
        string pipeName,
        string pipeNameWithoutPrefix,
        ServicePeerPolicy servicePolicy,
        PeerIdentity current)
    {
        ClientPeerPolicy clientPolicy = ClientPeerPolicy.Create([current.UserSid], [current.SessionId]);
        var host = new CapturePipeHost(pipeName, servicePolicy, clientPolicy, new FailClosedCaptureWorker());
        using var stopping = new CancellationTokenSource();
        Task server = host.ServeAsync(stopping.Token);
        await host.Started.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
        var stalledClients = new List<NamedPipeClientStream>();
        try
        {
            for (int index = 0; index < ProtocolLimits.MaxConcurrentConnections; index++)
            {
                var stalled = new NamedPipeClientStream(
                    ".",
                    pipeNameWithoutPrefix,
                    PipeDirection.InOut,
                    PipeOptions.Asynchronous);
                await stalled.ConnectAsync(5_000).ConfigureAwait(false);
                stalledClients.Add(stalled);
            }
            await Task.Delay(ProtocolLimits.ClientPreambleReadMilliseconds + 500).ConfigureAwait(false);
            foreach (NamedPipeClientStream stalled in stalledClients)
            {
                await stalled.DisposeAsync().ConfigureAwait(false);
            }
            stalledClients.Clear();

            var client = new CapturePipeClient(servicePolicy, pipeNameWithoutPrefix);
            byte[] request = CreateResolveRequest("42345678-1234-4234-8234-123456789abc");
            await using PipeCaptureExchange exchange = await client.ExchangeAsync(request, CancellationToken.None)
                .WaitAsync(TimeSpan.FromSeconds(5))
                .ConfigureAwait(false);
            CaptureResponseEnvelope response = CaptureProtocol.ValidateResponse(
                exchange.ResultFrame,
                CaptureProtocol.ValidateRequest(request));
            Assert(!response.IsSuccess, "preamble timeout probe returned an unexpected success");
        }
        finally
        {
            foreach (NamedPipeClientStream stalled in stalledClients)
            {
                await stalled.DisposeAsync().ConfigureAwait(false);
            }
            stopping.Cancel();
            await IgnoreExpectedStopAsync(server);
        }
    }

    private static async Task AssertRejectsOversizedFrameAsync(CapturePipeClient client)
    {
        byte[] oversized = new byte[ProtocolLimits.MaxRequestFrameBytes + 1];
        try
        {
            _ = await client.ExchangeAsync(oversized, CancellationToken.None).ConfigureAwait(false);
            throw new InvalidOperationException("Oversized frame was accepted.");
        }
        catch (CaptureProtocolException)
        {
        }
    }

    private static void AssertRejectsBidiControlInUrl()
    {
        byte[] request = CreateCaptureRequest(
            "12345678-1234-4234-8234-123456789abe",
            "https://www.douyin.com/video/123\u202e456");
        try
        {
            _ = CaptureProtocol.ValidateRequest(request);
            throw new InvalidOperationException("Bidi control in source URL was accepted.");
        }
        catch (CaptureProtocolException)
        {
        }
    }

    private static byte[] CreateCaptureRequest(
        string requestId,
        string originalUrl = "https://www.douyin.com/video/1234567890123456789") => JsonSerializer.SerializeToUtf8Bytes(new
        {
            protocol_version = 1,
            message_type = "capture_request",
            request_id = requestId,
            original_url = originalUrl,
            limits = new
            {
                max_media_bytes = ProtocolLimits.MaxMediaBytes,
                max_media_duration_seconds = 3600,
                max_short_link_redirects = 5,
                max_media_redirects = 3,
            },
        });

    private static string ReadFailureCode(byte[] resultFrame)
    {
        using JsonDocument document = JsonDocument.Parse(resultFrame);
        return document.RootElement.GetProperty("error").GetProperty("code").GetString() ?? string.Empty;
    }

    private static byte[] CreateResolveRequest(string requestId) => JsonSerializer.SerializeToUtf8Bytes(new
    {
        protocol_version = 1,
        message_type = "capture_resolve_request",
        request_id = requestId,
        original_url = "https://v.douyin.com/AbCdEf/",
        max_short_link_redirects = 5,
    });

    private static async Task IgnoreExpectedStopAsync(Task server)
    {
        try
        {
            await server.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
        }
        catch (TimeoutException)
        {
            throw new InvalidOperationException("Pipe listener did not stop after cancellation.");
        }
    }

    private static void Assert(bool condition, string message)
    {
        if (!condition)
        {
            throw new InvalidOperationException(message);
        }
    }

    private sealed class FakeLeaseUpstreamPermitProvider(List<string> order) : ILeaseUpstreamPermitProvider
    {
        public FakeLeaseUpstreamPermit? LastPermit { get; private set; }
        public IPEndPoint? LastEndpoint { get; private set; }

        public ValueTask<IAsyncDisposable> AcquireAsync(IPEndPoint endpoint, CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            order.Add("permit");
            LastEndpoint = endpoint;
            LastPermit = new FakeLeaseUpstreamPermit();
            return ValueTask.FromResult<IAsyncDisposable>(LastPermit);
        }
    }

    private sealed class FakeLeaseUpstreamPermit : IAsyncDisposable
    {
        public bool Disposed { get; private set; }

        public ValueTask DisposeAsync()
        {
            Disposed = true;
            return ValueTask.CompletedTask;
        }
    }

    private sealed class FakeLeaseDnsPermitProvider(
        List<string> order,
        Func<bool> socketsClosedAtRelease) : ILeaseDnsPermitProvider
    {
        public bool DenyNext { get; set; }
        public List<FakeLeaseDnsPermit> Permits { get; } = [];

        public ValueTask<IAsyncDisposable> AcquireAsync(
            IPEndPoint resolverEndpoint,
            LeaseDnsTransport transport,
            CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            order.Add($"permit-{transport.ToString().ToLowerInvariant()}");
            if (DenyNext)
            {
                DenyNext = false;
                throw new InvalidOperationException("Harness DNS permit denied.");
            }

            var permit = new FakeLeaseDnsPermit(
                transport,
                order,
                socketsClosedAtRelease);
            Permits.Add(permit);
            return ValueTask.FromResult<IAsyncDisposable>(permit);
        }
    }

    private sealed class FakeLeaseDnsPermit(
        LeaseDnsTransport transport,
        List<string> order,
        Func<bool> socketsClosedAtRelease) : IAsyncDisposable
    {
        public bool Disposed { get; private set; }
        public bool SocketsClosedAtRelease { get; private set; }

        public ValueTask DisposeAsync()
        {
            SocketsClosedAtRelease = socketsClosedAtRelease();
            Disposed = true;
            order.Add($"release-{transport.ToString().ToLowerInvariant()}");
            return ValueTask.CompletedTask;
        }
    }

    private sealed class FakeLeaseTcpDialer(EndPoint remoteEndpoint, List<string> order) : ILeaseTcpDialer
    {
        public FakeLeaseTcpConnectionHandle? LastConnection { get; private set; }
        public IPEndPoint? RequestedEndpoint { get; private set; }

        public ValueTask<ILeaseTcpConnectionHandle> ConnectAsync(
            IPEndPoint endpoint,
            CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            order.Add("connect");
            RequestedEndpoint = endpoint;
            LastConnection = new FakeLeaseTcpConnectionHandle(remoteEndpoint);
            return ValueTask.FromResult<ILeaseTcpConnectionHandle>(LastConnection);
        }
    }

    private sealed class FakeLeaseTcpConnectionHandle(EndPoint remoteEndpoint) : ILeaseTcpConnectionHandle
    {
        private readonly MemoryStream _stream = new();

        public EndPoint? RemoteEndPoint { get; } = remoteEndpoint;
        public Stream Stream => _stream;
        public bool Disposed { get; private set; }
        public bool SendShutdown { get; private set; }

        public void ShutdownSend() => SendShutdown = true;

        public ValueTask DisposeAsync()
        {
            Disposed = true;
            _stream.Dispose();
            return ValueTask.CompletedTask;
        }
    }

    private sealed class FakeNumericDnsQuestioner(
        Func<string, LeaseDnsQuestionType, LeaseDnsResponse> responseFactory) : INumericDnsQuestioner
    {
        public List<(IPAddress Resolver, int Port, string Name, LeaseDnsQuestionType Type)> Calls { get; } = [];

        public ValueTask<LeaseDnsResponse> QueryAsync(
            IPAddress resolver,
            int port,
            string questionName,
            LeaseDnsQuestionType questionType,
            CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Calls.Add((resolver, port, questionName, questionType));
            return ValueTask.FromResult(responseFactory(questionName, questionType));
        }
    }

    private sealed class TrackingDnsSocketFactory
    {
        private readonly List<string>? _order;

        public TrackingDnsSocketFactory(List<string>? order = null) => _order = order;

        public List<SafeSocketHandle> UdpHandles { get; } = [];
        public List<SafeSocketHandle> TcpHandles { get; } = [];
        public bool AllCreatedSocketsClosed => UdpHandles.All(handle => handle.IsClosed)
            && TcpHandles.All(handle => handle.IsClosed);

        public UdpClient CreateUdpClient(AddressFamily family)
        {
            var client = new UdpClient(family);
            _order?.Add("socket-udp");
            UdpHandles.Add(client.Client.SafeHandle);
            return client;
        }

        public TcpClient CreateTcpClient(AddressFamily family)
        {
            var client = new TcpClient(family);
            _order?.Add("socket-tcp");
            TcpHandles.Add(client.Client.SafeHandle);
            return client;
        }
    }

    private sealed class WaitingNumericDnsQuestioner : INumericDnsQuestioner
    {
        public TaskCompletionSource Started { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource Cancelled { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public async ValueTask<LeaseDnsResponse> QueryAsync(
            IPAddress resolver,
            int port,
            string questionName,
            LeaseDnsQuestionType questionType,
            CancellationToken cancellationToken)
        {
            Started.TrySetResult();
            try
            {
                await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                Cancelled.TrySetResult();
                throw;
            }
            throw new InvalidOperationException("Waiting DNS question should only stop through cancellation.");
        }
    }

    private sealed class HarnessArtifactWorker(byte[] artifact) : ICaptureWorker
    {
        public TaskCompletionSource<CaptureExecutionContext> ContextCaptured { get; } =
            new(TaskCreationOptions.RunContinuationsAsynchronously);

        public Task<CaptureWorkerResponse> HandleAsync(
            CaptureRequestEnvelope request,
            CaptureExecutionContext executionContext,
            CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            ContextCaptured.TrySetResult(executionContext);
            string hash = Convert.ToHexString(SHA256.HashData(artifact)).ToLowerInvariant();
            byte[] result = JsonSerializer.SerializeToUtf8Bytes(new
            {
                protocol_version = 1,
                message_type = "capture_result",
                request_id = request.RequestId,
                status = "succeeded",
                video = new
                {
                    video_id = "1234567890123456789",
                    title = "harness",
                    author = (string?)null,
                    publish_date = (string?)null,
                    duration_seconds = 2.0,
                },
                media_artifact = new
                {
                    artifact_id = "42345678-1234-4234-8234-123456789abc",
                    sha256 = hash,
                    size_bytes = artifact.LongLength,
                    media_type = "video/mp4",
                    duration_seconds = 2.0,
                },
            });
            return Task.FromResult(new CaptureWorkerResponse(result, new MemoryStream(artifact, writable: false)));
        }
    }

    private sealed class CancellationProbeWorker : ICaptureWorker
    {
        public TaskCompletionSource Started { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource Cancelled { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public async Task<CaptureWorkerResponse> HandleAsync(
            CaptureRequestEnvelope request,
            CaptureExecutionContext executionContext,
            CancellationToken cancellationToken)
        {
            Started.TrySetResult();
            try
            {
                await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                Cancelled.TrySetResult();
                throw;
            }
            throw new InvalidOperationException("Cancellation probe should not complete normally.");
        }
    }

    private sealed class LeaseProbeWorker : ICaptureWorker
    {
        private int calls;

        public TaskCompletionSource FirstStarted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource ReleaseFirst { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource CancellationStarted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource CancellationObserved { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public int CallCount => Volatile.Read(ref calls);

        public async Task<CaptureWorkerResponse> HandleAsync(
            CaptureRequestEnvelope request,
            CaptureExecutionContext executionContext,
            CancellationToken cancellationToken)
        {
            int call = Interlocked.Increment(ref calls);
            if (call == 1)
            {
                FirstStarted.TrySetResult();
                await ReleaseFirst.Task.WaitAsync(cancellationToken).ConfigureAwait(false);
            }
            else if (call == 2)
            {
                CancellationStarted.TrySetResult();
                try
                {
                    await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken).ConfigureAwait(false);
                }
                catch (OperationCanceledException)
                {
                    CancellationObserved.TrySetResult();
                    throw;
                }
            }
            else if (call == 3)
            {
                throw new InvalidOperationException("Harness worker failure.");
            }

            return new CaptureWorkerResponse(
                CaptureProtocol.CreateFailClosedResult(request),
                ArtifactStream: null);
        }
    }

    private sealed class CallCountingWorker : ICaptureWorker
    {
        private int calls;

        public bool WasCalled => Volatile.Read(ref calls) != 0;

        public Task<CaptureWorkerResponse> HandleAsync(
            CaptureRequestEnvelope request,
            CaptureExecutionContext executionContext,
            CancellationToken cancellationToken)
        {
            Interlocked.Increment(ref calls);
            return Task.FromResult(new CaptureWorkerResponse(
                CaptureProtocol.CreateFailClosedResult(request),
                ArtifactStream: null));
        }
    }
}
