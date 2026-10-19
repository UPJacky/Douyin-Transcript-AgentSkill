from __future__ import annotations

import socket
import sys
import threading
import time
import os

import pytest
from douyin_transcript import browser_proxy
from douyin_transcript.browser_proxy import (
    PinnedHttpsConnectProxy,
    resolve_browser_destination,
)


def _read_response_headers(stream):
    lines = []
    while True:
        line = stream.readline()
        lines.append(line)
        if line in {b"\r\n", b"", b"\n"}:
            return b"".join(lines)


def _duplicate_socket(sock: socket.socket) -> socket.socket:
    if sys.platform == "win32":
        return socket.fromshare(sock.share(os.getpid()))
    return socket.socket(fileno=os.dup(sock.fileno()))


def test_connect_tunnel_uses_pinned_ip_and_relays_bytes():
    with socket.socket() as echo_server:
        echo_server.bind(("127.0.0.1", 0))
        echo_server.listen(1)
        echo_port = echo_server.getsockname()[1]
        received = threading.Event()

        def echo() -> None:
            connection, _address = echo_server.accept()
            with connection:
                assert connection.recv(4) == b"ping"
                connection.sendall(b"pong")
                received.set()

        worker = threading.Thread(target=echo, daemon=True)
        worker.start()
        destinations = []

        def connect_to_pinned_address(address: str, port: int, timeout: float):
            destinations.append((address, port, timeout))
            return socket.create_connection(("127.0.0.1", echo_port), timeout=timeout)

        proxy = PinnedHttpsConnectProxy(
            resolve_address=lambda host, *, deadline: "8.8.8.8",
            connector=connect_to_pinned_address,
        ).start()
        try:
            proxy_host, proxy_port = proxy._server.server_address
            with socket.create_connection(
                (proxy_host, proxy_port), timeout=2
            ) as client:
                stream = client.makefile("rb")
                client.sendall(
                    b"CONNECT www.douyin.com:443 HTTP/1.1\r\n"
                    b"Host: www.douyin.com:443\r\n\r\n"
                )
                response = _read_response_headers(stream)
                assert response.startswith(b"HTTP/1.1 200 Connection Established")
                client.sendall(b"ping")
                assert stream.read(4) == b"pong"
            assert received.wait(2)
            worker.join(timeout=2)
            assert destinations and destinations[0][0:2] == ("8.8.8.8", 443)
        finally:
            proxy.close()


def test_standalone_proxy_can_use_a_supplied_loopback_listener_socket():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as broker_listener:
        broker_listener.bind(("127.0.0.1", 0))
        broker_listener.listen(8)
        endpoint = broker_listener.getsockname()
        client_copy = _duplicate_socket(broker_listener)
        proxy = PinnedHttpsConnectProxy().start(
            listener_socket=client_copy,
            expected_endpoint=endpoint,
        )
        try:
            assert proxy._server.server_address[:2] == endpoint
            with socket.create_connection(endpoint, timeout=2) as client:
                client.sendall(
                    b"CONNECT www.douyin.com:80 HTTP/1.1\r\n"
                    b"Host: www.douyin.com:80\r\n\r\n"
                )
                assert client.recv(256).startswith(b"HTTP/1.1 403")
        finally:
            proxy.close()
        # The socket owner retains its original handle while the proxy closes
        # only the handle supplied to this standalone diagnostic instance.
        assert broker_listener.getsockname() == endpoint
        with socket.create_connection(endpoint, timeout=2):
            broker_listener.settimeout(2)
            accepted, _address = broker_listener.accept()
            accepted.close()


@pytest.mark.parametrize("bad_endpoint", [("0.0.0.0", 1234), ("127.0.0.1", 0)])
def test_proxy_rejects_untrusted_expected_endpoint(bad_endpoint):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        duplicate = _duplicate_socket(listener)
        with pytest.raises(ValueError, match="does not match"):
            PinnedHttpsConnectProxy().start(
                listener_socket=duplicate,
                expected_endpoint=bad_endpoint,
            )
        duplicate.close()


def test_proxy_rejects_socket_that_is_not_listening():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as unbound:
        unbound.bind(("127.0.0.1", 0))
        with pytest.raises(ValueError, match="does not match"):
            PinnedHttpsConnectProxy().start(
                listener_socket=unbound,
                expected_endpoint=unbound.getsockname(),
            )


def test_proxy_listener_validation_fallback_handles_unavailable_acceptconn(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(browser_proxy, "_acceptconn_status", lambda listener: None)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listening:
        listening.bind(("127.0.0.1", 0))
        listening.listen(1)
        assert browser_proxy._is_expected_loopback_listener(
            listening, listening.getsockname()
        )
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as unlistened:
        unlistened.bind(("127.0.0.1", 0))
        assert not browser_proxy._is_expected_loopback_listener(
            unlistened, unlistened.getsockname()
        )


@pytest.mark.parametrize(
    "payload",
    [
        b"CONNECT 127.0.0.1:443 HTTP/1.1\r\nHost: 127.0.0.1:443\r\n\r\n",
        b"CONNECT www.douyin.com:80 HTTP/1.1\r\nHost: www.douyin.com:80\r\n\r\n",
        b"GET https://www.douyin.com/ HTTP/1.1\r\nHost: www.douyin.com\r\n\r\n",
    ],
)
def test_proxy_rejects_non_https_or_non_allowlisted_connect(payload: bytes):
    resolver_calls = []
    proxy = PinnedHttpsConnectProxy(
        resolve_address=lambda host, *, deadline: resolver_calls.append(host)
        or "8.8.8.8"
    ).start()
    try:
        host, port = proxy._server.server_address
        with socket.create_connection((host, port), timeout=2) as client:
            client.sendall(payload)
            response = client.recv(256)
        assert response.startswith((b"HTTP/1.1 403", b"HTTP/1.1 405"))
        assert not resolver_calls
    finally:
        proxy.close()


def test_proxy_rejects_private_address_returned_by_resolver():
    proxy = PinnedHttpsConnectProxy(
        resolve_address=lambda _host, *, deadline: "127.0.0.1"
    ).start()
    try:
        host, port = proxy._server.server_address
        with socket.create_connection((host, port), timeout=2) as client:
            client.sendall(
                b"CONNECT www.douyin.com:443 HTTP/1.1\r\n"
                b"Host: www.douyin.com:443\r\n\r\n"
            )
            response = client.recv(256)
        assert response.startswith(b"HTTP/1.1 403")
    finally:
        proxy.close()


def test_resolve_browser_destination_uses_host_allowlist_and_rejects_private_dns(
    monkeypatch,
):
    calls = []

    def fake_validate(url, **kwargs):
        calls.append((url, kwargs))
        return (None, "8.8.4.4")

    monkeypatch.setattr(
        "douyin_transcript.browser_proxy.validate_https_url", fake_validate
    )

    deadline = time.monotonic() + 5
    assert (
        resolve_browser_destination("v3-web.douyinvod.com", deadline=deadline)
        == "8.8.4.4"
    )
    assert calls[0][0] == "https://v3-web.douyinvod.com/"
    assert calls[0][1]["resolve_dns"] is True
    assert calls[0][1]["deadline"] == deadline

    with pytest.raises(ValueError):
        resolve_browser_destination("attacker.example", deadline=deadline)
    assert len(calls) == 1

    monkeypatch.setattr(
        "douyin_transcript.browser_proxy.validate_https_url",
        lambda *_args, **_kwargs: (None, "127.0.0.1"),
    )
    with pytest.raises(ValueError):
        resolve_browser_destination("www.douyin.com", deadline=deadline)


def test_proxy_dns_timeout_closes_connect_and_releases_client_slot(
    monkeypatch, tmp_path
):
    import douyin_transcript.browser_proxy as proxy_module
    import douyin_transcript.urls as urls_module

    monkeypatch.setattr(proxy_module, "_MAX_CLIENTS", 1)
    monkeypatch.setattr(proxy_module, "_CONNECT_TIMEOUT_SECONDS", 1.0)
    marker = tmp_path / "resolver-started"
    script = """
import json
import os
import sys
import time

try:
    descriptor = os.open(sys.argv[2], os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
except FileExistsError:
    sys.stdout.write(json.dumps({"ok": True, "addresses": ["8.8.8.8"]}) + "\\n")
else:
    os.close(descriptor)
    time.sleep(30)
"""
    monkeypatch.setattr(
        urls_module,
        "_dns_worker_command",
        lambda host: [sys.executable, "-I", "-c", script, host, str(marker)],
    )
    upstream_peers = []

    def connector(_address: str, _port: int, _timeout: float):
        upstream, peer = socket.socketpair()
        upstream_peers.append(peer)
        return upstream

    proxy = PinnedHttpsConnectProxy(connector=connector).start()
    try:
        proxy_host, proxy_port = proxy._server.server_address
        with socket.create_connection((proxy_host, proxy_port), timeout=1) as client:
            client.settimeout(3)
            client.sendall(
                b"CONNECT www.douyin.com:443 HTTP/1.1\r\n"
                b"Host: www.douyin.com:443\r\n\r\n"
            )
            first_response = _read_response_headers(client.makefile("rb"))
        assert first_response == b"" or first_response.startswith(b"HTTP/1.1 504")
        assert marker.is_file()

        # The timed-out DNS child must be reaped and return the proxy-client slot.
        assert proxy._server._client_slots.acquire(timeout=1)
        proxy._server._client_slots.release()

        with socket.create_connection((proxy_host, proxy_port), timeout=1) as client:
            client.settimeout(3)
            client.sendall(
                b"CONNECT www.douyin.com:443 HTTP/1.1\r\n"
                b"Host: www.douyin.com:443\r\n\r\n"
            )
            second_response = _read_response_headers(client.makefile("rb"))
            assert second_response.startswith(b"HTTP/1.1 200 Connection Established")
        assert urls_module._DNS_LOOKUP_SLOTS.acquire(blocking=False)
        urls_module._DNS_LOOKUP_SLOTS.release()
    finally:
        for peer in upstream_peers:
            peer.close()
        proxy.close()


def test_proxy_relay_backpressure_times_out_and_releases_client_slot(monkeypatch):
    import douyin_transcript.browser_proxy as proxy_module

    monkeypatch.setattr(proxy_module, "_MAX_CLIENTS", 1)
    monkeypatch.setattr(proxy_module, "_IDLE_TIMEOUT_SECONDS", 5.0)
    monkeypatch.setattr(proxy_module, "_WRITE_TIMEOUT_SECONDS", 0.2)
    upstream_peers = []

    def connector(_address: str, _port: int, _timeout: float):
        upstream, peer = socket.socketpair()
        upstream.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        upstream_peers.append(peer)  # Intentionally never read from the peer.
        return upstream

    proxy = PinnedHttpsConnectProxy(
        resolve_address=lambda _host, *, deadline: "8.8.8.8",
        connector=connector,
    ).start()
    first_client = None
    second_client = None
    flood_thread = None
    flood_started = threading.Event()
    flood_finished = threading.Event()
    stop_flood = threading.Event()
    try:
        proxy_host, proxy_port = proxy._server.server_address

        first_client = socket.create_connection((proxy_host, proxy_port), timeout=1)
        first_client.settimeout(1)
        first_client.sendall(
            b"CONNECT www.douyin.com:443 HTTP/1.1\r\nHost: www.douyin.com:443\r\n\r\n"
        )
        with first_client.makefile("rb") as stream:
            response = _read_response_headers(stream)
        assert response.startswith(b"HTTP/1.1 200 Connection Established")

        def flood_tunnel() -> None:
            payload = b"x" * (64 * 1024)
            flood_started.set()
            try:
                while not stop_flood.is_set():
                    first_client.sendall(payload)
            except OSError:
                pass
            finally:
                flood_finished.set()

        flood_thread = threading.Thread(target=flood_tunnel, daemon=True)
        flood_thread.start()
        assert flood_started.wait(1)

        # The destination never drains its socket. The relay must close the
        # tunnel after the bounded write-stall interval, even though its idle
        # timeout is longer, and return the only proxy-client slot.
        assert proxy._server._client_slots.acquire(timeout=3)
        proxy._server._client_slots.release()
        assert flood_finished.wait(1)
        flood_thread.join(timeout=1)
        assert not flood_thread.is_alive()

        second_client = socket.create_connection((proxy_host, proxy_port), timeout=1)
        second_client.settimeout(1)
        second_client.sendall(
            b"CONNECT www.douyin.com:443 HTTP/1.1\r\nHost: www.douyin.com:443\r\n\r\n"
        )
        with second_client.makefile("rb") as stream:
            response = _read_response_headers(stream)
        assert response.startswith(b"HTTP/1.1 200 Connection Established")
        second_client.close()
        second_client = None

        assert proxy._server._client_slots.acquire(timeout=1)
        proxy._server._client_slots.release()
    finally:
        stop_flood.set()
        if first_client is not None:
            first_client.close()
        if second_client is not None:
            second_client.close()
        if flood_thread is not None:
            flood_thread.join(timeout=1)
        for peer in upstream_peers:
            peer.close()
        proxy.close()
