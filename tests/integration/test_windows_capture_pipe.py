from __future__ import annotations

import ctypes
import hashlib
import os
import queue
import shutil
import subprocess
import threading
import uuid
from pathlib import Path

import pytest

from douyin_transcript.capture_client import CaptureClientError, CaptureServiceClient
from douyin_transcript.capture_pipe_windows import (
    WindowsNamedPipeTransport,
    _TOKEN_QUERY,
    _WindowsPipeApi,
)


def _current_user_identity() -> tuple[str, int]:
    api = _WindowsPipeApi()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    process = kernel32.GetCurrentProcess()
    token = ctypes.c_void_p()
    if not api._advapi32.OpenProcessToken(process, _TOKEN_QUERY, ctypes.byref(token)):
        raise OSError(ctypes.get_last_error(), "Could not open the test process token")
    try:
        return api._read_token_user_sid(token.value), api._read_token_session(
            token.value
        )
    finally:
        api._kernel32.CloseHandle(token)


def _read_lines(stream, output: queue.Queue[str]) -> None:
    for line in stream:
        output.put(line.strip())


def _start_test_server(mode: str):
    dotnet = os.environ.get("DOUYIN_CAPTURE_PIPE_DOTNET") or shutil.which("dotnet")
    server_dll = os.environ.get("DOUYIN_CAPTURE_PIPE_DLL")
    if not dotnet or not server_dll:
        pytest.skip("native interop server paths are not configured")
    if not Path(dotnet).is_file() or not Path(server_dll).is_file():
        pytest.fail("configured native interop server path does not exist")

    service_sid, session_id = _current_user_identity()
    pipe_name = f"DouyinTranscript.Capture.InteropTest.{uuid.uuid4().hex}"
    output: queue.Queue[str] = queue.Queue()
    server = subprocess.Popen(
        [dotnet, server_dll, "--interop-test-server", pipe_name, mode],
        cwd=Path(server_dll).parent,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    reader = threading.Thread(
        target=_read_lines, args=(server.stdout, output), daemon=True
    )
    reader.start()
    try:
        ready = output.get(timeout=15)
    except queue.Empty:
        _stop_test_server(server)
        pytest.fail("native pipe test server did not become ready")
    if ready != "READY":
        _stop_test_server(server)
        pytest.fail(f"native pipe test server failed to start: {ready}")
    return server, pipe_name, service_sid, session_id, output


def _stop_test_server(server: subprocess.Popen[str]) -> None:
    if server.stdin is not None and not server.stdin.closed:
        server.stdin.close()
    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait(timeout=5)
    if server.stdout is not None:
        server.stdout.close()
    if server.stderr is not None:
        server.stderr.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows named pipe integration")
def test_python_transport_authenticates_and_receives_native_pipe_artifact(tmp_path):
    server, pipe_name, service_sid, session_id, _ = _start_test_server("artifact")
    try:
        wrong_service_sid = "S-1-5-80-999999999-999999999-999999999-999999999-999999999"
        wrong_transport = WindowsNamedPipeTransport(
            wrong_service_sid,
            pipe_name=pipe_name,
            required_session_id=session_id,
        )
        with pytest.raises(CaptureClientError) as rejected:
            CaptureServiceClient(
                wrong_transport, tmp_path / "rejected-cache", timeout_seconds=10
            ).capture("https://www.douyin.com/video/1234567890123456789")
        assert rejected.value.code == "CAPTURE_TRANSPORT_FAILED"

        transport = WindowsNamedPipeTransport(
            service_sid,
            pipe_name=pipe_name,
            required_session_id=session_id,
        )
        client = CaptureServiceClient(
            transport, tmp_path / "media-cache", timeout_seconds=30
        )
        captured = client.capture("https://www.douyin.com/video/1234567890123456789")

        expected = bytes((index * 31) % 256 for index in range(133_777))
        assert captured.video.video_id == "1234567890123456789"
        assert captured.path.read_bytes() == expected
        assert captured.size_bytes == len(expected)
        assert captured.sha256 == hashlib.sha256(expected).hexdigest()
    finally:
        _stop_test_server(server)


@pytest.mark.skipif(os.name != "nt", reason="Windows named pipe integration")
def test_python_transport_cancels_and_drains_pending_overlapped_read(tmp_path):
    server, pipe_name, service_sid, session_id, output = _start_test_server("cancel")
    cancel = threading.Event()
    outcome: queue.Queue[object] = queue.Queue()
    client = CaptureServiceClient(
        WindowsNamedPipeTransport(
            service_sid,
            pipe_name=pipe_name,
            required_session_id=session_id,
        ),
        tmp_path / "media-cache",
        timeout_seconds=10,
    )

    def run_capture() -> None:
        try:
            client.capture(
                "https://www.douyin.com/video/1234567890123456789",
                is_cancelled=cancel.is_set,
            )
        except Exception as exc:
            outcome.put(exc)
        else:
            outcome.put(None)

    request_thread = threading.Thread(target=run_capture, daemon=True)
    request_thread.start()
    try:
        assert output.get(timeout=10) == "WORKER_STARTED"
        cancel.set()
        request_thread.join(timeout=5)
        assert not request_thread.is_alive(), "cancelled pipe read did not return"
        error = outcome.get_nowait()
        assert isinstance(error, CaptureClientError)
        assert error.code == "CANCELLED"
        assert list(tmp_path.iterdir()) == []
    finally:
        cancel.set()
        request_thread.join(timeout=5)
        _stop_test_server(server)
