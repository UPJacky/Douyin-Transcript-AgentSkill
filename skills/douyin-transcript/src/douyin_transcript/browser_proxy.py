"""Standalone HTTPS CONNECT relay for diagnostics; not an isolation service.

This module is not used by ``BrowserCapture``. Its listener and upstream
connections run in the calling process, so it must not be treated as the
service-owned proxy or as proof of process-level egress isolation.
"""

from __future__ import annotations

import ipaddress
import select
import socket
import socketserver
import threading
import time
from collections.abc import Callable
from urllib.parse import urlsplit

from .urls import (
    DOUYIN_SHORT_HOSTS,
    DOUYIN_WEB_HOSTS,
    MEDIA_HOST_SUFFIXES,
    validate_https_url,
)

_NAVIGATION_HOSTS = (
    DOUYIN_WEB_HOSTS
    | DOUYIN_SHORT_HOSTS
    | {
        "passport.douyin.com",
        "www.iesdouyin.com",
    }
)
_RESOURCE_SUFFIXES = MEDIA_HOST_SUFFIXES | {".douyin.com", ".iesdouyin.com"}
_CONNECT_TIMEOUT_SECONDS = 10.0
_IDLE_TIMEOUT_SECONDS = 60.0
_WRITE_TIMEOUT_SECONDS = 60.0
_MAX_RELAY_BUFFER_BYTES = 256 * 1024
_RELAY_CHUNK_BYTES = 64 * 1024
_MAX_REQUEST_LINE = 8192
_MAX_HEADERS = 32 * 1024
_MAX_CLIENTS = 64


def resolve_browser_destination(host: str, *, deadline: float) -> str:
    """Return one validated public IP for an allowlisted HTTPS host."""
    normalized = host.lower().rstrip(".")
    if normalized not in _NAVIGATION_HOSTS and not any(
        normalized == suffix[1:] or normalized.endswith(suffix) for suffix in _RESOURCE_SUFFIXES
    ):
        raise ValueError("destination is not allowlisted")
    formatted_host = f"[{normalized}]" if ":" in normalized else normalized
    _parsed, address = validate_https_url(
        f"https://{formatted_host}/",
        allowed_hosts=_NAVIGATION_HOSTS,
        allowed_suffixes=_RESOURCE_SUFFIXES,
        resolve_dns=True,
        deadline=deadline,
    )
    if address is None:
        raise ValueError("destination did not resolve")
    # Keep this check local even though validate_https_url already rejects
    # non-global answers; it protects this connection sink if that API changes.
    parsed_ip = ipaddress.ip_address(address)
    if not parsed_ip.is_global:
        raise ValueError("destination is not public")
    return str(parsed_ip)


def _connect_authority(authority: str) -> tuple[str, int] | None:
    try:
        parsed = urlsplit(f"//{authority}")
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if (
        not host
        or port != 443
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        return None
    normalized_host = host.lower().rstrip(".")
    try:
        ipaddress.ip_address(normalized_host)
    except ValueError:
        pass
    else:
        return None
    return normalized_host, port


class _ConnectHandler(socketserver.StreamRequestHandler):
    rbufsize = 0
    wbufsize = 0
    server: _ProxyServer

    def handle(self) -> None:
        client = self.request
        deadline = time.monotonic() + _CONNECT_TIMEOUT_SECONDS
        timer = threading.Timer(_CONNECT_TIMEOUT_SECONDS, _shutdown_socket, args=(client,))
        timer.daemon = True
        timer.start()
        upstream: socket.socket | None = None
        try:
            client.settimeout(_remaining(deadline))
            line = self.rfile.readline(_MAX_REQUEST_LINE + 1)
            if len(line) > _MAX_REQUEST_LINE or not line.endswith(b"\r\n"):
                self._respond(400, "Bad Request")
                return
            try:
                method, authority, version = line.decode("ascii").strip().split(" ")
            except (UnicodeDecodeError, ValueError):
                self._respond(400, "Bad Request")
                return
            if method != "CONNECT" or version not in {"HTTP/1.0", "HTTP/1.1"}:
                self._respond(405, "Method Not Allowed")
                return
            if not self._read_headers():
                self._respond(431, "Request Header Fields Too Large")
                return
            destination = _connect_authority(authority)
            if destination is None:
                self._respond(403, "Forbidden")
                return

            host, port = destination
            address = self.server.resolve_address(host, deadline=deadline)
            parsed_address = ipaddress.ip_address(address)
            if not parsed_address.is_global:
                self._respond(403, "Forbidden")
                return
            remaining = _remaining(deadline)
            upstream = self.server.connector(
                str(parsed_address), port, min(_CONNECT_TIMEOUT_SECONDS, remaining)
            )
            remaining = _remaining(deadline)
            client.settimeout(remaining)
            client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            # The setup deadline ends once the CONNECT response is sent. The
            # tunnel itself is governed by the bounded idle timeout below.
            timer.cancel()
            upstream.settimeout(None)
            client.settimeout(None)
            self._relay(client, upstream)
        except TimeoutError:
            self._respond(504, "Gateway Timeout")
        except OSError:
            pass
        except Exception as exc:
            if getattr(exc, "code", None) == "TIMEOUT" or time.monotonic() >= deadline:
                self._respond(504, "Gateway Timeout")
            else:
                self._respond(403, "Forbidden")
        finally:
            timer.cancel()
            if upstream is not None:
                try:
                    upstream.close()
                except OSError:
                    pass

    def _read_headers(self) -> bool:
        consumed = 0
        while True:
            line = self.rfile.readline(_MAX_REQUEST_LINE + 1)
            consumed += len(line)
            if len(line) > _MAX_REQUEST_LINE or consumed > _MAX_HEADERS:
                return False
            if not line:
                return False
            if line == b"\r\n":
                return True
            if not line.endswith(b"\r\n"):
                return False

    def _respond(self, status: int, reason: str) -> None:
        try:
            self.request.sendall(
                f"HTTP/1.1 {status} {reason}\r\nConnection: close\r\n\r\n".encode("ascii")
            )
        except OSError:
            pass

    @staticmethod
    def _relay(client: socket.socket, upstream: socket.socket) -> None:
        sockets = (client, upstream)
        pending = {client: bytearray(), upstream: bytearray()}
        pending_since: dict[socket.socket, float | None] = {
            client: None,
            upstream: None,
        }
        last_activity = time.monotonic()
        try:
            client.setblocking(False)
            upstream.setblocking(False)
            while True:
                now = time.monotonic()
                remaining = _IDLE_TIMEOUT_SECONDS - (now - last_activity)
                if remaining <= 0:
                    return
                for destination in pending:
                    queued_at = pending_since[destination]
                    if queued_at is not None:
                        write_remaining = _WRITE_TIMEOUT_SECONDS - (now - queued_at)
                        if write_remaining <= 0:
                            return
                        remaining = min(remaining, write_remaining)

                readable = []
                if len(pending[upstream]) < _MAX_RELAY_BUFFER_BYTES:
                    readable.append(client)
                if len(pending[client]) < _MAX_RELAY_BUFFER_BYTES:
                    readable.append(upstream)
                writable = [destination for destination in sockets if pending[destination]]
                try:
                    ready_read, ready_write, exceptional = select.select(
                        readable, writable, sockets, remaining
                    )
                except OSError:
                    return
                if exceptional or not ready_read and not ready_write:
                    return

                for destination in ready_write:
                    payload = pending[destination]
                    try:
                        sent = destination.send(payload)
                    except (BlockingIOError, InterruptedError):
                        continue
                    except OSError:
                        return
                    if sent <= 0:
                        return
                    del payload[:sent]
                    last_activity = time.monotonic()
                    if not payload:
                        pending_since[destination] = None

                for source in ready_read:
                    destination = upstream if source is client else client
                    available = _MAX_RELAY_BUFFER_BYTES - len(pending[destination])
                    if available <= 0:
                        continue
                    try:
                        payload = source.recv(min(_RELAY_CHUNK_BYTES, available))
                    except (BlockingIOError, InterruptedError):
                        continue
                    except OSError:
                        return
                    if not payload:
                        return
                    if not pending[destination]:
                        pending_since[destination] = time.monotonic()
                    pending[destination].extend(payload)
                    last_activity = time.monotonic()
        finally:
            # A stalled peer must not leave either half of the tunnel open.
            for connection in sockets:
                _shutdown_socket(connection)


class _ProxyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = False
    daemon_threads = True
    request_queue_size = _MAX_CLIENTS

    def __init__(
        self,
        server_address: tuple[str, int],
        resolve_address: Callable[..., str],
        connector: Callable[[str, int, float], socket.socket],
        *,
        listener_socket: socket.socket | None = None,
    ) -> None:
        self.resolve_address = resolve_address
        self.connector = connector
        self._client_slots = threading.BoundedSemaphore(_MAX_CLIENTS)
        super().__init__(server_address, _ConnectHandler, bind_and_activate=listener_socket is None)
        if listener_socket is not None:
            # TCPServer creates an unbound socket even when activation is
            # deferred. Replace it with the broker-duplicated listener; the
            # broker retains its own handle until the lease is released.
            self.socket.close()
            self.socket = listener_socket
            self.server_address = listener_socket.getsockname()

    def process_request(self, request: socket.socket, client_address: tuple[str, int]) -> None:
        if not self._client_slots.acquire(blocking=False):
            try:
                request.sendall(b"HTTP/1.1 503 Busy\r\nConnection: close\r\n\r\n")
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._client_slots.release()
            raise

    def process_request_thread(
        self, request: socket.socket, client_address: tuple[str, int]
    ) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._client_slots.release()


class PinnedHttpsConnectProxy:
    """Standalone loopback test/diagnostic proxy, outside the capture path."""

    def __init__(
        self,
        *,
        resolve_address: Callable[..., str] = resolve_browser_destination,
        connector: Callable[[str, int, float], socket.socket] | None = None,
    ) -> None:
        self._resolve_address = resolve_address
        self._connector = connector or self._connect
        self._server: _ProxyServer | None = None
        self._thread: threading.Thread | None = None

    @staticmethod
    def _connect(address: str, port: int, timeout: float) -> socket.socket:
        return socket.create_connection((address, port), timeout=timeout)

    @property
    def server_url(self) -> str:
        if self._server is None:
            raise RuntimeError("proxy is not running")
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    @property
    def playwright_options(self) -> dict[str, str]:
        # Chromium otherwise bypasses a manually configured proxy for loopback
        # and link-local destinations. Route those requests through this proxy
        # so its allowlist and public-address checks remain the network boundary.
        return {"server": self.server_url, "bypass": "<-loopback>"}

    def start(
        self,
        *,
        listener_socket: socket.socket | None = None,
        expected_endpoint: tuple[str, int] | None = None,
    ) -> PinnedHttpsConnectProxy:
        if self._server is not None:
            return self
        if listener_socket is not None:
            if expected_endpoint is None or not _is_expected_loopback_listener(
                listener_socket, expected_endpoint
            ):
                raise ValueError("broker proxy socket does not match its loopback lease")
            listener_socket.setblocking(True)
        server = _ProxyServer(
            ("127.0.0.1", 0),
            self._resolve_address,
            self._connector,
            listener_socket=listener_socket,
        )
        thread = threading.Thread(
            target=server.serve_forever,
            name="douyin-pinned-https-proxy",
            daemon=True,
        )
        try:
            thread.start()
        except Exception:
            server.server_close()
            raise
        self._server = server
        self._thread = thread
        return self

    def close(self) -> None:
        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=2)


def _is_expected_loopback_listener(
    listener: socket.socket, expected_endpoint: tuple[str, int]
) -> bool:
    expected_host, expected_port = expected_endpoint
    if (
        expected_host != "127.0.0.1"
        or type(expected_port) is not int
        or not 1 <= expected_port <= 65535
    ):
        return False
    try:
        actual = listener.getsockname()
        return (
            listener.family == socket.AF_INET
            and listener.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) == socket.SOCK_STREAM
            and listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) == 1
            and actual[0] == expected_host
            and actual[1] == expected_port
        )
    except (OSError, AttributeError):
        return False


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("browser CONNECT exceeded its total deadline")
    return remaining


def _shutdown_socket(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass
