"""Authenticated Windows named-pipe transport for the native capture host.

The endpoint name and expected service SID are supplied by trusted application
configuration. Server PID, session, and token SID are verified before a request
frame (which contains the original URL) is written. This adapter does not
install the native host or prove that its browser worker has WFP isolation.
"""

from __future__ import annotations

import ctypes
import io
import math
import os
import re
import time
from collections.abc import Callable
from typing import BinaryIO

from .capture_client import CaptureExchange
from .capture_ipc import (
    MAX_REQUEST_FRAME_BYTES,
    MAX_RESULT_FRAME_BYTES,
    CaptureIpcProtocolError,
    CaptureRequest,
    CaptureResolveRequest,
    CaptureResultSuccess,
    decode_capture_request,
    decode_capture_resolve_request,
    decode_capture_resolve_result,
    decode_capture_result,
)

DEFAULT_CAPTURE_PIPE_NAME = "DouyinTranscript.Capture.v1"
_PIPE_PREFIX = "\\\\.\\pipe\\"
_PIPE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_SID_PATTERN = re.compile(r"^S-1-(?:[0-9]+-)*[0-9]+$")
_PROTOCOL_PREAMBLE = b"DTP1"
_SERVER_AUTHENTICATION_ACK = b"DTA1"
_MAX_PIPE_CHUNK_BYTES = 64 * 1024
_MAX_EXCHANGE_SECONDS = 15 * 60
_SERVER_AUTHENTICATION_ACK_SECONDS = 5

_ERROR_FILE_NOT_FOUND = 2
_ERROR_BROKEN_PIPE = 109
_ERROR_NO_DATA = 232
_ERROR_PIPE_BUSY = 231
_ERROR_SEM_TIMEOUT = 121
_ERROR_IO_PENDING = 997
_ERROR_INSUFFICIENT_BUFFER = 122
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_TOKEN_QUERY = 0x0008
_TOKEN_USER = 1
_TOKEN_GROUPS = 2
_TOKEN_SESSION_ID = 12
_SE_GROUP_ENABLED = 0x00000004
_SE_GROUP_USE_FOR_DENY_ONLY = 0x00000010


class CapturePipeTransportError(RuntimeError):
    """A detail-free failure while opening or using the capture pipe."""


class CapturePipeAuthenticationError(CapturePipeTransportError):
    """The connected pipe server did not match the configured service identity."""


class CapturePipeProtocolError(CapturePipeTransportError):
    """The native transport framing was malformed or exceeded its bounds."""


class WindowsNamedPipeTransport:
    """Connect to the native service after authenticating its process token.

    ``service_sid`` and ``pipe_name`` must come from trusted packaged
    configuration, never from an environment variable or the request URL.
    The default service session is Session 0. This class is deliberately not
    installed as the product default until a matching service/worker package
    exists.
    """

    def __init__(
        self,
        service_sid: str,
        *,
        pipe_name: str = DEFAULT_CAPTURE_PIPE_NAME,
        required_session_id: int = 0,
    ) -> None:
        if os.name != "nt":
            raise OSError("The Windows capture pipe is unavailable on this platform.")
        if not isinstance(pipe_name, str) or not _PIPE_NAME_PATTERN.fullmatch(pipe_name):
            raise ValueError("pipe_name is invalid")
        if (
            not isinstance(required_session_id, int)
            or isinstance(required_session_id, bool)
            or not 0 <= required_session_id <= 0xFFFFFFFF
        ):
            raise ValueError("required_session_id is invalid")
        if not isinstance(service_sid, str) or not _SID_PATTERN.fullmatch(service_sid):
            raise ValueError("service_sid is invalid")
        self._api = _WindowsPipeApi()
        self._pipe_name = pipe_name
        self._expected_service_sid = self._api.validate_service_sid(service_sid)
        self._required_session_id = required_session_id

    def exchange(
        self,
        request_frame: bytes,
        *,
        deadline_monotonic: float,
        is_cancelled: Callable[[], bool] | None,
    ) -> CaptureExchange:
        if (
            not isinstance(request_frame, bytes)
            or not 1 <= len(request_frame) <= MAX_REQUEST_FRAME_BYTES
        ):
            raise CapturePipeProtocolError("Capture request frame is invalid.")
        if (
            isinstance(deadline_monotonic, bool)
            or not isinstance(deadline_monotonic, (int, float))
            or not math.isfinite(deadline_monotonic)
        ):
            raise CapturePipeProtocolError("Capture deadline is invalid.")
        deadline = min(float(deadline_monotonic), time.monotonic() + _MAX_EXCHANGE_SECONDS)
        _check_io_state(deadline, is_cancelled)

        try:
            request: CaptureRequest | CaptureResolveRequest
            try:
                request = decode_capture_request(request_frame)
            except CaptureIpcProtocolError:
                request = decode_capture_resolve_request(request_frame)

            pipe = self._api.connect_authenticated(
                self._pipe_name,
                self._expected_service_sid,
                self._required_session_id,
                deadline,
                is_cancelled,
            )
            try:
                pipe.write_all(_PROTOCOL_PREAMBLE, deadline, is_cancelled)
                acknowledgment_deadline = min(
                    deadline, time.monotonic() + _SERVER_AUTHENTICATION_ACK_SECONDS
                )
                acknowledgment = pipe.read_exactly(
                    len(_SERVER_AUTHENTICATION_ACK), acknowledgment_deadline, is_cancelled
                )
                if acknowledgment != _SERVER_AUTHENTICATION_ACK:
                    raise CapturePipeAuthenticationError(
                        "The capture service rejected the client identity."
                    )
                pipe.write_all(
                    len(request_frame).to_bytes(4, "little") + request_frame, deadline, is_cancelled
                )
                result_length = int.from_bytes(
                    pipe.read_exactly(4, deadline, is_cancelled), "little"
                )
                if not 1 <= result_length <= MAX_RESULT_FRAME_BYTES:
                    raise CapturePipeProtocolError("Capture result frame length is invalid.")
                result_frame = pipe.read_exactly(result_length, deadline, is_cancelled)

                if isinstance(request, CaptureRequest):
                    result = decode_capture_result(result_frame, request)
                    if isinstance(result, CaptureResultSuccess):
                        media_stream: BinaryIO | None = _FramedMediaStream(
                            lambda count: pipe.read_exactly(count, deadline, is_cancelled),
                            lambda count: pipe.read_some(count, deadline, is_cancelled),
                            result.media_artifact.size_bytes,
                        )
                        return _WindowsPipeExchange(pipe, result_frame, media_stream)
                else:
                    decode_capture_resolve_result(result_frame, request)

                if pipe.read_some(1, deadline, is_cancelled):
                    raise CapturePipeProtocolError(
                        "A result without media included trailing bytes."
                    )
                return _WindowsPipeExchange(pipe, result_frame, None)
            except BaseException:
                pipe.close()
                raise
        except CapturePipeTransportError:
            raise
        except TimeoutError:
            raise
        except InterruptedError:
            raise
        except Exception as exc:
            raise CapturePipeTransportError(
                f"Capture pipe exchange failed ({type(exc).__name__})."
            ) from None


class _WindowsPipeExchange(CaptureExchange):
    def __init__(
        self, pipe: _PipeConnection, result_frame: bytes, media_stream: BinaryIO | None
    ) -> None:
        self.result_frame = result_frame
        self.media_stream = media_stream
        self._pipe = pipe
        self._closed = False

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._pipe.close()


class _FramedMediaStream(io.RawIOBase):
    """Remove native length words and require the terminator plus pipe EOF."""

    def __init__(
        self,
        read_exactly: Callable[[int], bytes],
        read_some: Callable[[int], bytes],
        declared_size: int,
    ) -> None:
        super().__init__()
        if (
            isinstance(declared_size, bool)
            or not isinstance(declared_size, int)
            or declared_size < 0
        ):
            raise CapturePipeProtocolError("Media artifact size is invalid.")
        self._read_exactly = read_exactly
        self._read_some = read_some
        self._remaining = declared_size
        self._block_remaining = 0
        self._finished = False

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        if self.closed:
            raise ValueError("I/O operation on closed media stream")
        if size == 0:
            return b""
        if size < 0:
            raise ValueError("unbounded reads are not supported")
        if self._finished:
            return b""
        if self._remaining == 0:
            terminal = int.from_bytes(self._read_exactly(4), "little")
            if terminal != 0 or self._read_some(1) != b"":
                raise CapturePipeProtocolError("Media artifact terminator or EOF is invalid.")
            self._finished = True
            return b""
        if self._block_remaining == 0:
            block_length = int.from_bytes(self._read_exactly(4), "little")
            if not 1 <= block_length <= _MAX_PIPE_CHUNK_BYTES or block_length > self._remaining:
                raise CapturePipeProtocolError("Media artifact block length is invalid.")
            self._block_remaining = block_length
        count = min(size, self._block_remaining, self._remaining)
        chunk = self._read_exactly(count)
        if len(chunk) != count:
            raise CapturePipeProtocolError("Media artifact block ended early.")
        self._block_remaining -= count
        self._remaining -= count
        return chunk


class _PipeConnection:
    def write_all(
        self, data: bytes, deadline: float, is_cancelled: Callable[[], bool] | None
    ) -> None:
        raise NotImplementedError

    def read_exactly(
        self, size: int, deadline: float, is_cancelled: Callable[[], bool] | None
    ) -> bytes:
        raise NotImplementedError

    def read_some(
        self, size: int, deadline: float, is_cancelled: Callable[[], bool] | None
    ) -> bytes:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class _WindowsPipeApi:
    """Small ctypes wrapper; all pipe I/O uses cancellable OVERLAPPED calls."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("Windows named pipes are unavailable.")
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        self._configure_functions()

    def _configure_functions(self) -> None:
        k = self._kernel32
        a = self._advapi32
        handle = ctypes.c_void_p
        dword = ctypes.c_uint32
        k.WaitNamedPipeW.argtypes = [ctypes.c_wchar_p, dword]
        k.WaitNamedPipeW.restype = ctypes.c_int
        k.CreateFileW.argtypes = [
            ctypes.c_wchar_p,
            dword,
            dword,
            ctypes.c_void_p,
            dword,
            dword,
            handle,
        ]
        k.CreateFileW.restype = handle
        k.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_wchar_p]
        k.CreateEventW.restype = handle
        k.ReadFile.argtypes = [
            handle,
            ctypes.c_void_p,
            dword,
            ctypes.POINTER(dword),
            ctypes.c_void_p,
        ]
        k.ReadFile.restype = ctypes.c_int
        k.WriteFile.argtypes = [
            handle,
            ctypes.c_void_p,
            dword,
            ctypes.POINTER(dword),
            ctypes.c_void_p,
        ]
        k.WriteFile.restype = ctypes.c_int
        k.GetOverlappedResult.argtypes = [
            handle,
            ctypes.c_void_p,
            ctypes.POINTER(dword),
            ctypes.c_int,
        ]
        k.GetOverlappedResult.restype = ctypes.c_int
        k.CancelIoEx.argtypes = [handle, ctypes.c_void_p]
        k.CancelIoEx.restype = ctypes.c_int
        k.WaitForSingleObject.argtypes = [handle, dword]
        k.WaitForSingleObject.restype = dword
        k.CloseHandle.argtypes = [handle]
        k.CloseHandle.restype = ctypes.c_int
        k.GetNamedPipeServerProcessId.argtypes = [handle, ctypes.POINTER(dword)]
        k.GetNamedPipeServerProcessId.restype = ctypes.c_int
        k.GetNamedPipeServerSessionId.argtypes = [handle, ctypes.POINTER(dword)]
        k.GetNamedPipeServerSessionId.restype = ctypes.c_int
        k.OpenProcess.argtypes = [dword, ctypes.c_int, dword]
        k.OpenProcess.restype = handle
        k.ProcessIdToSessionId.argtypes = [dword, ctypes.POINTER(dword)]
        k.ProcessIdToSessionId.restype = ctypes.c_int
        a.OpenProcessToken.argtypes = [handle, dword, ctypes.POINTER(handle)]
        a.OpenProcessToken.restype = ctypes.c_int
        a.GetTokenInformation.argtypes = [
            handle,
            ctypes.c_int,
            ctypes.c_void_p,
            dword,
            ctypes.POINTER(dword),
        ]
        a.GetTokenInformation.restype = ctypes.c_int
        a.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p)]
        a.ConvertSidToStringSidW.restype = ctypes.c_int
        a.ConvertStringSidToSidW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(handle)]
        a.ConvertStringSidToSidW.restype = ctypes.c_int
        k.LocalFree.argtypes = [handle]
        k.LocalFree.restype = handle

    def connect_authenticated(
        self,
        pipe_name: str,
        expected_service_sid: str,
        required_session_id: int,
        deadline: float,
        is_cancelled: Callable[[], bool] | None,
    ) -> _PipeConnection:
        endpoint = _PIPE_PREFIX + pipe_name
        handle = self._open_pipe(endpoint, deadline, is_cancelled)
        pipe = _OverlappedPipeConnection(self, handle)
        try:
            self._verify_server(handle, expected_service_sid, required_session_id)
            _check_io_state(deadline, is_cancelled)
            return pipe
        except BaseException:
            pipe.close()
            raise

    def _open_pipe(
        self,
        endpoint: str,
        deadline: float,
        is_cancelled: Callable[[], bool] | None,
    ) -> int:
        invalid_handle = ctypes.c_void_p(-1).value
        while True:
            _check_io_state(deadline, is_cancelled)
            remaining_ms = max(1, min(50, int((deadline - time.monotonic()) * 1000)))
            if not self._kernel32.WaitNamedPipeW(endpoint, remaining_ms):
                error = ctypes.get_last_error()
                if error not in {_ERROR_FILE_NOT_FOUND, _ERROR_SEM_TIMEOUT, _ERROR_PIPE_BUSY}:
                    raise CapturePipeTransportError("The capture service pipe is unavailable.")
                continue

            flags = (
                0x40000000 | 0x00100000 | 0x00010000
            )  # OVERLAPPED + SECURITY_SQOS_PRESENT + IDENTIFICATION
            handle = self._kernel32.CreateFileW(
                endpoint,
                0x80000000 | 0x40000000,
                0,
                None,
                3,
                flags,
                None,
            )
            if handle != invalid_handle:
                return int(handle)
            error = ctypes.get_last_error()
            if error not in {_ERROR_FILE_NOT_FOUND, _ERROR_PIPE_BUSY, _ERROR_SEM_TIMEOUT}:
                raise CapturePipeTransportError("The capture service pipe is unavailable.")

    def _verify_server(
        self, pipe: int, expected_service_sid: str, required_session_id: int
    ) -> None:
        pid = ctypes.c_uint32()
        pipe_session = ctypes.c_uint32()
        if not self._kernel32.GetNamedPipeServerProcessId(
            pipe, ctypes.byref(pid)
        ) or not self._kernel32.GetNamedPipeServerSessionId(pipe, ctypes.byref(pipe_session)):
            raise CapturePipeAuthenticationError(
                "The capture service identity could not be verified."
            )

        process = self._kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, 0, pid.value)
        if not process:
            raise CapturePipeAuthenticationError(
                "The capture service identity could not be verified."
            )
        token = ctypes.c_void_p()
        try:
            process_session = ctypes.c_uint32()
            if (
                not self._kernel32.ProcessIdToSessionId(pid.value, ctypes.byref(process_session))
                or process_session.value != pipe_session.value
            ):
                raise CapturePipeAuthenticationError("The capture service session is invalid.")
            if pipe_session.value != required_session_id:
                raise CapturePipeAuthenticationError("The capture service session is not trusted.")
            if not self._advapi32.OpenProcessToken(process, _TOKEN_QUERY, ctypes.byref(token)):
                raise CapturePipeAuthenticationError("The capture service token could not be read.")

            user_sid = self._read_token_user_sid(token.value)
            enabled_groups = self._read_enabled_token_groups(token.value)
            token_session = self._read_token_session(token.value)
            if token_session != pipe_session.value or (
                user_sid != expected_service_sid and expected_service_sid not in enabled_groups
            ):
                raise CapturePipeAuthenticationError("The capture service identity is not trusted.")

            pid_after = ctypes.c_uint32()
            session_after = ctypes.c_uint32()
            if (
                not self._kernel32.GetNamedPipeServerProcessId(pipe, ctypes.byref(pid_after))
                or not self._kernel32.GetNamedPipeServerSessionId(pipe, ctypes.byref(session_after))
                or pid_after.value != pid.value
                or session_after.value != pipe_session.value
            ):
                raise CapturePipeAuthenticationError(
                    "The capture service identity changed during verification."
                )
        finally:
            if token.value:
                self._kernel32.CloseHandle(token)
            self._kernel32.CloseHandle(process)

    def _read_token_user_sid(self, token: int) -> str:
        buffer, size = self._token_information(token, _TOKEN_USER)
        try:
            if size < ctypes.sizeof(_SID_AND_ATTRIBUTES):
                raise CapturePipeAuthenticationError("The capture service token user is malformed.")
            entry = ctypes.cast(buffer, ctypes.POINTER(_SID_AND_ATTRIBUTES)).contents
            return self._sid_to_string(entry.sid)
        finally:
            ctypes.memset(buffer, 0, size)

    def _read_enabled_token_groups(self, token: int) -> set[str]:
        buffer, size = self._token_information(token, _TOKEN_GROUPS)
        try:
            header = ctypes.cast(buffer, ctypes.POINTER(_TOKEN_GROUPS_HEADER)).contents
            header_size = _TOKEN_GROUPS_HEADER.first_group.offset
            group_size = ctypes.sizeof(_SID_AND_ATTRIBUTES)
            if (
                size < header_size
                or header.group_count > 65_536
                or header_size + header.group_count * group_size > size
            ):
                raise CapturePipeAuthenticationError(
                    "The capture service token groups are malformed."
                )
            enabled: set[str] = set()
            base = ctypes.addressof(buffer)
            for index in range(header.group_count):
                entry = ctypes.cast(
                    base + header_size + index * group_size, ctypes.POINTER(_SID_AND_ATTRIBUTES)
                ).contents
                if (
                    entry.attributes & _SE_GROUP_ENABLED
                    and not entry.attributes & _SE_GROUP_USE_FOR_DENY_ONLY
                ):
                    enabled.add(self._sid_to_string(entry.sid))
            return enabled
        finally:
            ctypes.memset(buffer, 0, size)

    def _read_token_session(self, token: int) -> int:
        buffer, size = self._token_information(token, _TOKEN_SESSION_ID)
        try:
            if size != ctypes.sizeof(ctypes.c_uint32):
                raise CapturePipeAuthenticationError(
                    "The capture service token session is malformed."
                )
            return ctypes.cast(buffer, ctypes.POINTER(ctypes.c_uint32)).contents.value
        finally:
            ctypes.memset(buffer, 0, size)

    def _token_information(
        self, token: int, information_class: int
    ) -> tuple[ctypes.Array[ctypes.c_char], int]:
        required = ctypes.c_uint32()
        if self._advapi32.GetTokenInformation(
            token, information_class, None, 0, ctypes.byref(required)
        ):
            raise CapturePipeAuthenticationError("The capture service token query was invalid.")
        if (
            ctypes.get_last_error() != _ERROR_INSUFFICIENT_BUFFER
            or not 4 <= required.value <= 1_048_576
        ):
            raise CapturePipeAuthenticationError("The capture service token could not be read.")
        buffer = ctypes.create_string_buffer(required.value)
        returned = ctypes.c_uint32()
        if (
            not self._advapi32.GetTokenInformation(
                token, information_class, buffer, required.value, ctypes.byref(returned)
            )
            or not 4 <= returned.value <= required.value
        ):
            ctypes.memset(buffer, 0, required.value)
            raise CapturePipeAuthenticationError("The capture service token could not be read.")
        return buffer, returned.value

    def _sid_to_string(self, sid: int) -> str:
        text = ctypes.c_wchar_p()
        if not self._advapi32.ConvertSidToStringSidW(sid, ctypes.byref(text)):
            raise CapturePipeAuthenticationError("The capture service SID could not be read.")
        try:
            return (text.value or "").upper()
        finally:
            self._kernel32.LocalFree(ctypes.cast(text, ctypes.c_void_p))

    def validate_service_sid(self, service_sid: str) -> str:
        sid = ctypes.c_void_p()
        if not self._advapi32.ConvertStringSidToSidW(service_sid, ctypes.byref(sid)):
            raise ValueError("service_sid is invalid")
        try:
            return self._sid_to_string(sid.value)
        finally:
            self._kernel32.LocalFree(sid)

    def _transfer(
        self,
        handle: int,
        value: bytes | int,
        *,
        write: bool,
        deadline: float,
        is_cancelled: Callable[[], bool] | None,
    ) -> int | bytes:
        return _transfer_once(
            self,
            handle,
            value,
            write=write,
            deadline=deadline,
            is_cancelled=is_cancelled,
        )


class _OverlappedPipeConnection(_PipeConnection):
    def __init__(self, api: _WindowsPipeApi, handle: int) -> None:
        self._api = api
        self._handle = handle
        self._closed = False

    def write_all(
        self, data: bytes, deadline: float, is_cancelled: Callable[[], bool] | None
    ) -> None:
        offset = 0
        while offset < len(data):
            count = self._api._transfer(
                self._handle,
                data[offset:],
                write=True,
                deadline=deadline,
                is_cancelled=is_cancelled,
            )
            if count <= 0:
                raise CapturePipeTransportError("The capture service pipe closed during a write.")
            offset += count

    def read_exactly(
        self, size: int, deadline: float, is_cancelled: Callable[[], bool] | None
    ) -> bytes:
        if size < 0 or size > MAX_RESULT_FRAME_BYTES + 4 + _MAX_PIPE_CHUNK_BYTES:
            raise CapturePipeProtocolError("Capture pipe read size is invalid.")
        result = bytearray()
        while len(result) < size:
            chunk = self._api._transfer(
                self._handle,
                size - len(result),
                write=False,
                deadline=deadline,
                is_cancelled=is_cancelled,
            )
            if not chunk:
                raise EOFError("The capture service pipe ended early.")
            result.extend(chunk)
        return bytes(result)

    def read_some(
        self, size: int, deadline: float, is_cancelled: Callable[[], bool] | None
    ) -> bytes:
        if not 0 <= size <= _MAX_PIPE_CHUNK_BYTES:
            raise CapturePipeProtocolError("Capture pipe read size is invalid.")
        if size == 0:
            return b""
        return self._api._transfer(
            self._handle, size, write=False, deadline=deadline, is_cancelled=is_cancelled
        )

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._api._kernel32.CloseHandle(self._handle)


class _OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("internal", ctypes.c_void_p),
        ("internal_high", ctypes.c_void_p),
        ("offset", ctypes.c_uint32),
        ("offset_high", ctypes.c_uint32),
        ("event", ctypes.c_void_p),
    ]


class _SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("sid", ctypes.c_void_p), ("attributes", ctypes.c_uint32)]


class _TOKEN_GROUPS_HEADER(ctypes.Structure):
    _fields_ = [("group_count", ctypes.c_uint32), ("first_group", _SID_AND_ATTRIBUTES)]


def _transfer_once(
    api: _WindowsPipeApi,
    handle: int,
    value: bytes | int,
    *,
    write: bool,
    deadline: float,
    is_cancelled: Callable[[], bool] | None,
) -> int | bytes:
    _check_io_state(deadline, is_cancelled)
    if write:
        source = ctypes.create_string_buffer(value)  # type: ignore[arg-type]
        length = len(value)  # type: ignore[arg-type]
        buffer_pointer = ctypes.cast(source, ctypes.c_void_p)
    else:
        length = int(value)
        source = ctypes.create_string_buffer(length)
        buffer_pointer = ctypes.cast(source, ctypes.c_void_p)

    event = api._kernel32.CreateEventW(None, 1, 0, None)
    if not event:
        raise CapturePipeTransportError("The capture service pipe I/O could not start.")
    overlapped = _OVERLAPPED(event=event)
    transferred = ctypes.c_uint32()
    pending = False
    try:
        operation = api._kernel32.WriteFile if write else api._kernel32.ReadFile
        success = operation(
            handle, buffer_pointer, length, ctypes.byref(transferred), ctypes.byref(overlapped)
        )
        if not success:
            error = ctypes.get_last_error()
            if error in {_ERROR_BROKEN_PIPE, _ERROR_NO_DATA}:
                return 0 if write else b""
            if error != _ERROR_IO_PENDING:
                raise CapturePipeTransportError("The capture service pipe I/O failed.")
            pending = True

        if pending:
            while True:
                _check_io_state(deadline, is_cancelled)
                wait_ms = max(1, min(50, int((deadline - time.monotonic()) * 1000)))
                wait_result = api._kernel32.WaitForSingleObject(event, wait_ms)
                if wait_result == 0:
                    if not api._kernel32.GetOverlappedResult(
                        handle, ctypes.byref(overlapped), ctypes.byref(transferred), 0
                    ):
                        error = ctypes.get_last_error()
                        if error in {_ERROR_BROKEN_PIPE, _ERROR_NO_DATA}:
                            return 0 if write else b""
                        raise CapturePipeTransportError("The capture service pipe I/O failed.")
                    break
                if wait_result != 258:
                    raise CapturePipeTransportError("The capture service pipe I/O failed.")

        if write:
            return int(transferred.value)
        return source.raw[: transferred.value]
    except BaseException:
        if pending:
            api._kernel32.CancelIoEx(handle, ctypes.byref(overlapped))
            api._kernel32.WaitForSingleObject(event, 0xFFFFFFFF)
            api._kernel32.GetOverlappedResult(
                handle, ctypes.byref(overlapped), ctypes.byref(transferred), 0
            )
        raise
    finally:
        api._kernel32.CloseHandle(event)


def _check_io_state(deadline: float, is_cancelled: Callable[[], bool] | None) -> None:
    if is_cancelled is not None:
        try:
            if is_cancelled():
                raise InterruptedError("Capture operation cancelled.")
        except InterruptedError:
            raise
        except Exception:
            raise InterruptedError("Capture operation cancelled.") from None
    if time.monotonic() >= deadline:
        raise TimeoutError("Capture operation timed out.")
