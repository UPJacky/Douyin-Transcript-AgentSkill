"""Historical Winsock socket-share experiment; capture no longer uses handoff."""

from __future__ import annotations

import multiprocessing
import socket
import sys

import pytest


IO_TIMEOUT_SECONDS = 5
CHILD_JOIN_TIMEOUT_SECONDS = 8
MAX_SHARE_BYTES = 4096


def _recv_exact(connection: socket.socket, size: int) -> bytes:
    received = bytearray()
    while len(received) < size:
        chunk = connection.recv(size - len(received))
        if not chunk:
            raise ConnectionError(
                "peer closed before sending the complete test payload"
            )
        received.extend(chunk)
    return bytes(received)


def _child_accept_shared_listener(share_pipe) -> None:
    listener = None
    try:
        share_bytes = share_pipe.recv_bytes(MAX_SHARE_BYTES)
        listener = socket.fromshare(share_bytes)
        listener.settimeout(IO_TIMEOUT_SECONDS)
        accepted, _address = listener.accept()
        with accepted:
            accepted.settimeout(IO_TIMEOUT_SECONDS)
            assert _recv_exact(accepted, len(b"child-proof")) == b"child-proof"
            accepted.sendall(b"child-accepted")
    finally:
        if listener is not None:
            listener.close()
        share_pipe.close()


@pytest.mark.skipif(
    sys.platform != "win32", reason="socket.share/fromshare handoff is Windows-only"
)
def test_shared_loopback_listener_is_accepted_in_child_and_retained_by_parent():
    context = multiprocessing.get_context("spawn")
    child_share_pipe, parent_share_pipe = context.Pipe(duplex=False)
    child = context.Process(
        target=_child_accept_shared_listener, args=(child_share_pipe,)
    )
    started = False

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as parent_listener:
        parent_listener.bind(("127.0.0.1", 0))
        parent_listener.listen(4)
        parent_listener.settimeout(IO_TIMEOUT_SECONDS)
        endpoint = parent_listener.getsockname()

        try:
            child.start()
            started = True
            child_share_pipe.close()
            assert child.pid is not None

            # The pipe carries only the WSAPROTOCOL_INFO bytes returned by share().
            parent_share_pipe.send_bytes(parent_listener.share(child.pid))
            parent_share_pipe.close()

            with socket.create_connection(
                endpoint, timeout=IO_TIMEOUT_SECONDS
            ) as client:
                client.settimeout(IO_TIMEOUT_SECONDS)
                client.sendall(b"child-proof")
                assert _recv_exact(client, len(b"child-accepted")) == b"child-accepted"

            child.join(timeout=CHILD_JOIN_TIMEOUT_SECONDS)
            assert not child.is_alive(), (
                "child did not exit after accepting the shared listener"
            )
            assert child.exitcode == 0

            # The child closed its duplicate; the parent's original handle still accepts.
            assert parent_listener.fileno() != -1
            assert parent_listener.getsockname() == endpoint
            with socket.create_connection(
                endpoint, timeout=IO_TIMEOUT_SECONDS
            ) as client:
                client.sendall(b"parent-proof")
                accepted, _address = parent_listener.accept()
                with accepted:
                    accepted.settimeout(IO_TIMEOUT_SECONDS)
                    assert (
                        _recv_exact(accepted, len(b"parent-proof")) == b"parent-proof"
                    )
                    accepted.sendall(b"parent-accepted")
                client.settimeout(IO_TIMEOUT_SECONDS)
                assert (
                    _recv_exact(client, len(b"parent-accepted")) == b"parent-accepted"
                )
        finally:
            child_share_pipe.close()
            parent_share_pipe.close()
            if started:
                if child.is_alive():
                    child.terminate()
                    child.join(timeout=CHILD_JOIN_TIMEOUT_SECONDS)
                if child.is_alive() and hasattr(child, "kill"):
                    child.kill()
                    child.join(timeout=CHILD_JOIN_TIMEOUT_SECONDS)
                child.close()
