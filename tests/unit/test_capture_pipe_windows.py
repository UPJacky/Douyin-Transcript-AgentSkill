from __future__ import annotations

import ctypes
import io
import os

import pytest

from douyin_transcript.capture_pipe_windows import (
    CapturePipeProtocolError,
    WindowsNamedPipeTransport,
    _FramedMediaStream,
    _TOKEN_QUERY,
    _WindowsPipeApi,
    _check_io_state,
)


def _framed(
    payload: bytes,
    *,
    block_size: int = 7,
    terminal: bytes = b"\0\0\0\0",
    trailing: bytes = b"",
) -> bytes:
    result = bytearray()
    for offset in range(0, len(payload), block_size):
        chunk = payload[offset : offset + block_size]
        result.extend(len(chunk).to_bytes(4, "little"))
        result.extend(chunk)
    result.extend(terminal)
    result.extend(trailing)
    return bytes(result)


def _reader(wire: bytes, declared_size: int) -> _FramedMediaStream:
    source = io.BytesIO(wire)

    def read_exactly(count: int) -> bytes:
        data = source.read(count)
        if len(data) != count:
            raise EOFError("short test frame")
        return data

    return _FramedMediaStream(read_exactly, source.read, declared_size)


def test_framed_media_stream_unwraps_blocks_and_checks_terminal_eof():
    payload = bytes(range(40))
    reader = _reader(_framed(payload, block_size=7), len(payload))

    received = bytearray()
    while True:
        chunk = reader.read(5)
        if not chunk:
            break
        received.extend(chunk)

    assert bytes(received) == payload
    assert reader.read(1) == b""


@pytest.mark.parametrize(
    ("wire", "declared_size"),
    [
        (b"\x00\x00\x00\x00", 1),  # premature terminator
        ((8).to_bytes(4, "little") + b"12345678", 4),  # block exceeds descriptor
        (_framed(b"abc", terminal=b"nope"), 3),  # bad terminal marker
        (_framed(b"abc", trailing=b"x"), 3),  # bytes after terminal marker
    ],
)
def test_framed_media_stream_rejects_malformed_termination(
    wire: bytes, declared_size: int
):
    reader = _reader(wire, declared_size)
    try:
        while reader.read(8):
            pass
    except (CapturePipeProtocolError, EOFError):
        pass
    else:
        pytest.fail("malformed artifact framing was accepted")


def test_framed_media_stream_rejects_oversized_chunk():
    wire = (65_537).to_bytes(4, "little") + b"x" * 65_537
    reader = _reader(wire, 65_537)
    with pytest.raises(CapturePipeProtocolError):
        reader.read(1)


def test_pipe_io_state_checks_cancellation_and_deadline():
    with pytest.raises(InterruptedError):
        _check_io_state(float("inf"), lambda: True)
    with pytest.raises(TimeoutError):
        _check_io_state(0.0, None)


def test_windows_transport_rejects_invalid_trust_configuration_before_connecting():
    with pytest.raises(ValueError, match="pipe_name"):
        WindowsNamedPipeTransport("S-1-5-80-1", pipe_name="..\\pipe")
    with pytest.raises(ValueError, match="service_sid"):
        WindowsNamedPipeTransport("not-a-sid")


@pytest.mark.skipif(os.name == "nt", reason="non-Windows host check")
def test_windows_transport_is_unavailable_off_windows():
    with pytest.raises(OSError, match="unavailable"):
        WindowsNamedPipeTransport("S-1-5-80-1")


@pytest.mark.skipif(os.name != "nt", reason="Windows token API check")
def test_windows_token_api_reads_current_process_identity():
    api = _WindowsPipeApi()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    process = kernel32.GetCurrentProcess()
    token = ctypes.c_void_p()
    assert api._advapi32.OpenProcessToken(process, _TOKEN_QUERY, ctypes.byref(token))
    try:
        assert api._read_token_user_sid(token.value).startswith("S-1-")
        groups = api._read_enabled_token_groups(token.value)
        assert all(group.startswith("S-1-") for group in groups)
        assert api._read_token_session(token.value) >= 0
        assert api.validate_service_sid("S-1-5-80-1") == "S-1-5-80-1"
    finally:
        api._kernel32.CloseHandle(token)
