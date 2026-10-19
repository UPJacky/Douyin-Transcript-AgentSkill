"""Strict Douyin URL parsing and SSRF-safe HTTPS requests.

Network access is deliberately limited to known Douyin hosts. Redirects are
handled one hop at a time and connected to the IP address that was validated.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import SplitResult, urljoin, urlsplit, urlunsplit

DOUYIN_WEB_HOSTS = frozenset({"douyin.com", "www.douyin.com"})
DOUYIN_SHORT_HOSTS = frozenset({"v.douyin.com"})
# Keep this list intentionally narrow. Add a CDN only after observing it in an
# authorized capture and reviewing its ownership and redirect behavior.
MEDIA_HOST_SUFFIXES = frozenset(
    {
        ".douyinvod.com",
        ".douyinpic.com",
        ".bytecdn.cn",
        ".bytecdntp.com",
        ".ibytedtos.com",
        ".byteimg.com",
    }
)
SHORT_LINK_MAX_REDIRECTS = 5
SHORT_LINK_TOTAL_TIMEOUT_SECONDS = 30.0
_PROXY_DNS_RANGE = ipaddress.ip_network("198.18.0.0/15")
_VIDEO_PATH = re.compile(r"^/video/([0-9]{1,32})/?$")
_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_TRAILING_SHARE_PUNCTUATION = ".,;:!?，。；：！？、)]}）】》」』"
_DNS_LOOKUP_SLOTS = threading.BoundedSemaphore(2)
_DNS_MAX_HOST_LENGTH = 253
_DNS_MAX_ADDRESSES = 64
_DNS_MAX_OUTPUT_BYTES = 8192
_DNS_WORKER_SCRIPT = r"""
import json
import socket
import sys

MAX_ADDRESSES = 64
try:
    records = socket.getaddrinfo(sys.argv[1], 443, type=socket.SOCK_STREAM)
    addresses = []
    seen = set()
    too_many = False
    for record in records:
        address = record[4][0]
        if not isinstance(address, str) or not 1 <= len(address) <= 45:
            too_many = True
            break
        if address not in seen:
            if len(addresses) >= MAX_ADDRESSES:
                too_many = True
                break
            addresses.append(address)
            seen.add(address)
    result = {"ok": not too_many, "addresses": addresses}
except OSError:
    result = {"ok": False, "addresses": []}
encoded = json.dumps(result, separators=(",", ":")).encode("ascii")
if len(encoded) > 8192:
    encoded = b'{"ok":false,"addresses":[]}'
sys.stdout.buffer.write(encoded + b"\n")
"""


class UnsupportedUrlError(ValueError):
    """Raised when an input is not a supported, safe Douyin URL."""

    def __init__(self, message: str, code: str = "UNSUPPORTED_URL") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ResolvedInput:
    source_url: str
    canonical_url: str
    video_id: str
    source_type: str


def extract_url(text: str) -> str:
    """Extract one HTTP(S) URL from share text, stripping common trailing prose."""
    if not isinstance(text, str) or not text.strip():
        raise UnsupportedUrlError("URL 为空")
    matches = _URL_PATTERN.findall(text)
    if not matches:
        raise UnsupportedUrlError("未找到 HTTPS 抖音链接")
    if len(matches) > 1:
        raise UnsupportedUrlError("一次只能解析一个链接", "AMBIGUOUS_URL")
    return matches[0].rstrip(_TRAILING_SHARE_PUNCTUATION)


def resolve_input(
    value: str,
    *,
    redirect_resolver: Callable[[str], str | None] | None = None,
    max_redirects: int = SHORT_LINK_MAX_REDIRECTS,
) -> ResolvedInput:
    """Normalize a direct Douyin URL or follow a bounded Douyin short link.

    ``redirect_resolver`` is primarily a test seam. It receives a URL and must
    return the next absolute Location URL, or ``None`` when no redirect exists.
    """
    if max_redirects < 0 or max_redirects > SHORT_LINK_MAX_REDIRECTS:
        raise ValueError(f"max_redirects must be between 0 and {SHORT_LINK_MAX_REDIRECTS}")
    source_url = extract_url(value)
    parsed = _parse_supported_host(source_url, allowed_hosts=DOUYIN_WEB_HOSTS | DOUYIN_SHORT_HOSTS)

    if parsed.hostname and parsed.hostname.lower().rstrip(".") in DOUYIN_WEB_HOSTS:
        return _direct_input(source_url, parsed)

    # One absolute deadline covers every short-link hop, including DNS,
    # connection setup, response headers, and redirect processing.
    deadline = time.monotonic() + SHORT_LINK_TOTAL_TIMEOUT_SECONDS
    current = source_url
    seen = {current}
    for _hop in range(max_redirects):
        _require_deadline(deadline)
        try:
            location = (
                redirect_resolver(current)
                if redirect_resolver is not None
                else _request_short_redirect(current, deadline=deadline)
            )
        except UnsupportedUrlError:
            raise
        except TimeoutError:
            raise UnsupportedUrlError("抖音短链解析超过总时限", "TIMEOUT") from None
        except Exception as exc:
            raise UnsupportedUrlError(
                f"抖音短链解析失败（{type(exc).__name__}）", "SHORT_LINK_REQUEST_FAILED"
            ) from None
        _require_deadline(deadline)
        if not location:
            raise UnsupportedUrlError("抖音短链未跳转到可识别的视频页面", "SHORT_LINK_UNRESOLVED")
        target = urljoin(current, location)
        target_parsed = _parse_supported_host(
            target,
            allowed_hosts=DOUYIN_WEB_HOSTS | DOUYIN_SHORT_HOSTS,
            code="UNSAFE_REDIRECT",
        )
        if target in seen:
            raise UnsupportedUrlError("抖音短链发生跳转环", "REDIRECT_LOOP")
        seen.add(target)
        if (
            target_parsed.hostname
            and target_parsed.hostname.lower().rstrip(".") in DOUYIN_WEB_HOSTS
        ):
            return _direct_input(source_url, target_parsed, source_type="short_link")
        current = target

    raise UnsupportedUrlError("抖音短链跳转次数超过限制", "TOO_MANY_REDIRECTS")


def resolve_direct_input(value: str) -> ResolvedInput:
    """Resolve a supported direct video URL without performing network I/O.

    Short-link expansion belongs in the isolated capture worker because it
    requires DNS and HTTPS. Until that worker is available, reject short links
    here instead of silently resolving them in the caller process.
    """
    source_url = extract_url(value)
    parsed = _parse_supported_host(
        source_url,
        allowed_hosts=DOUYIN_WEB_HOSTS | DOUYIN_SHORT_HOSTS,
    )
    host = parsed.hostname.lower().rstrip(".") if parsed.hostname else ""
    if host in DOUYIN_SHORT_HOSTS:
        raise UnsupportedUrlError(
            "短链接解析需要由隔离服务执行；当前没有可用的系统隔离服务",
            "BROWSER_ISOLATION_UNAVAILABLE",
        )
    return _direct_input(source_url, parsed)


def resolved_short_link(value: str, video_id: str) -> ResolvedInput:
    """Bind an isolated short-link resolution to a safe local task identity."""
    if not isinstance(video_id, str) or re.fullmatch(r"[0-9]{1,32}", video_id) is None:
        raise UnsupportedUrlError("隔离服务返回了无效的视频 ID", "INVALID_RESULT")
    source_url = extract_url(value)
    _parse_supported_host(source_url, allowed_hosts=DOUYIN_SHORT_HOSTS)
    safe_source = urlsplit(source_url)
    source_without_query = urlunsplit(
        (safe_source.scheme, safe_source.netloc, safe_source.path, "", "")
    )
    return ResolvedInput(
        source_without_query,
        f"https://www.douyin.com/video/{video_id}",
        video_id,
        "short_link",
    )


def _require_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise UnsupportedUrlError("抖音短链解析超过总时限", "TIMEOUT")


def resolve_many(values: Iterable[str]) -> list[ResolvedInput]:
    """Resolve direct URLs and deduplicate by video ID without network I/O."""
    results: list[ResolvedInput] = []
    seen: set[str] = set()
    for value in values:
        try:
            item = resolve_direct_input(value)
        except UnsupportedUrlError:
            raise
        if item.video_id not in seen:
            seen.add(item.video_id)
            results.append(item)
    return results


def is_allowed_media_host(hostname: str) -> bool:
    host = hostname.lower().rstrip(".")
    return any(host.endswith(suffix) and host != suffix[1:] for suffix in MEDIA_HOST_SUFFIXES)


def validate_https_url(
    url: str,
    *,
    allowed_hosts: frozenset[str] | set[str] | None = None,
    allowed_suffixes: frozenset[str] | set[str] = frozenset(),
    resolve_dns: bool = True,
    deadline: float | None = None,
    cancellation: Any | None = None,
    allow_proxy_dns: bool = False,
) -> tuple[SplitResult, str | None]:
    """Validate an HTTPS URL and optionally resolve it to a public IP address.

    Returns the ``SplitResult`` and a validated IP for use by the pinned client.
    Host validation is exact for ``allowed_hosts`` and suffix-based for the
    explicitly supplied ``allowed_suffixes``.
    """
    if not isinstance(url, str) or url != url.strip():
        raise UnsupportedUrlError("仅支持 HTTPS 网络地址", "UNSAFE_URL")
    if any(ord(char) < 32 for char in url) or "\\" in url:
        raise UnsupportedUrlError("网络地址格式不安全", "UNSAFE_URL")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        raise UnsupportedUrlError("网络地址格式不安全", "UNSAFE_URL") from None
    if (
        parsed.scheme.lower() != "https"
        or not host
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise UnsupportedUrlError("网络地址格式不安全", "UNSAFE_URL")
    host = host.lower().rstrip(".")
    if port not in (None, 443):
        raise UnsupportedUrlError("只允许 HTTPS 默认端口", "UNSAFE_URL")
    try:
        host.encode("ascii")
    except UnicodeEncodeError:
        raise UnsupportedUrlError("网络主机名格式不安全", "UNSAFE_URL") from None
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise UnsupportedUrlError("不允许使用 IP 地址作为远端主机", "UNSAFE_URL")

    exact_hosts = {item.lower().rstrip(".") for item in (allowed_hosts or set())}
    suffixes = {item.lower() for item in allowed_suffixes}
    if host not in exact_hosts and not any(host.endswith(suffix) for suffix in suffixes):
        raise UnsupportedUrlError("网络主机不在允许列表中", "UNSAFE_HOST")

    if not resolve_dns:
        return parsed, None
    addresses = resolve_public_addresses(
        host,
        deadline=deadline,
        cancellation=cancellation,
        allow_proxy_dns=allow_proxy_dns,
    )
    return parsed, addresses[0]


def _dns_worker_command(host: str) -> list[str]:
    """Build an isolated, shell-free resolver process invocation."""
    return [sys.executable, "-I", "-c", _DNS_WORKER_SCRIPT, host]


def _stop_dns_worker(process: subprocess.Popen[bytes]) -> None:
    """Terminate and reap a resolver process before its concurrency slot is freed."""
    if process.poll() is None:
        try:
            process.terminate()
        except OSError:
            pass
        try:
            process.wait(timeout=0.25)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass
            process.wait()
    else:
        process.wait()
    if process.stdout is not None:
        process.stdout.close()


def _dns_failure(message: str, code: str = "DNS_FAILED") -> UnsupportedUrlError:
    return UnsupportedUrlError(message, code)


def _getaddrinfo_until(
    host: str, deadline: float | None, cancellation: Any | None = None
) -> tuple[str, ...]:
    """Resolve addresses; kill and reap a bounded worker on timeout/cancellation."""
    if not isinstance(host, str) or not host or len(host) > _DNS_MAX_HOST_LENGTH:
        raise _dns_failure("网络主机名格式无效")
    try:
        host.encode("ascii")
    except UnicodeEncodeError:
        raise _dns_failure("网络主机名格式无效") from None
    if deadline is None and cancellation is None:
        if not _DNS_LOOKUP_SLOTS.acquire(blocking=False):
            raise UnsupportedUrlError("网络主机解析并发数已达上限", "TIMEOUT")
        try:
            records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            return tuple(dict.fromkeys(record[4][0] for record in records))
        finally:
            _DNS_LOOKUP_SLOTS.release()
    if cancellation is not None and cancellation.is_set():
        raise _dns_failure("网络请求已取消", "CANCELLED")
    remaining = deadline - time.monotonic() if deadline is not None else float("inf")
    if remaining <= 0:
        raise UnsupportedUrlError("网络主机解析超过总时限", "TIMEOUT")
    if not _DNS_LOOKUP_SLOTS.acquire(blocking=False):
        raise UnsupportedUrlError("网络主机解析并发数已达上限", "TIMEOUT")
    process: subprocess.Popen[bytes] | None = None
    try:
        if cancellation is not None and cancellation.is_set():
            raise _dns_failure("网络请求已取消", "CANCELLED")
        if deadline is not None and time.monotonic() >= deadline:
            raise UnsupportedUrlError("网络主机解析超过总时限", "TIMEOUT")
        options: dict[str, Any] = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if sys.platform == "win32":
            options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            process = subprocess.Popen(_dns_worker_command(host), **options)
        except OSError:
            raise _dns_failure("网络主机解析进程无法启动") from None

        while True:
            if cancellation is not None and cancellation.is_set():
                raise _dns_failure("网络请求已取消", "CANCELLED")
            remaining = deadline - time.monotonic() if deadline is not None else float("inf")
            if remaining <= 0:
                raise UnsupportedUrlError("网络主机解析超过总时限", "TIMEOUT")
            try:
                output, _stderr = process.communicate(
                    timeout=min(remaining, 0.1) if cancellation is not None else remaining
                )
                break
            except subprocess.TimeoutExpired:
                continue

        if cancellation is not None and cancellation.is_set():
            raise _dns_failure("网络请求已取消", "CANCELLED")
        if deadline is not None and time.monotonic() >= deadline:
            raise UnsupportedUrlError("网络主机解析超过总时限", "TIMEOUT")
        if process.returncode != 0 or len(output) > _DNS_MAX_OUTPUT_BYTES:
            raise _dns_failure("网络主机无法解析")
        try:
            result = json.loads(output)
        except (UnicodeError, json.JSONDecodeError):
            raise _dns_failure("网络主机解析结果无效") from None
        if (
            not isinstance(result, dict)
            or set(result) != {"ok", "addresses"}
            or result["ok"] is not True
            or not isinstance(result["addresses"], list)
            or len(result["addresses"]) > _DNS_MAX_ADDRESSES
            or any(
                not isinstance(address, str) or not 1 <= len(address) <= 45
                for address in result["addresses"]
            )
        ):
            raise _dns_failure("网络主机无法解析")
        return tuple(dict.fromkeys(result["addresses"]))
    finally:
        try:
            if process is not None:
                _stop_dns_worker(process)
        finally:
            if process is None or process.poll() is not None:
                _DNS_LOOKUP_SLOTS.release()


def resolve_public_addresses(
    host: str,
    *,
    deadline: float | None = None,
    cancellation: Any | None = None,
    allow_proxy_dns: bool = False,
) -> tuple[str, ...]:
    """Resolve public addresses, optionally accepting a personal proxy's fake-IP range."""
    try:
        records = _getaddrinfo_until(host, deadline, cancellation)
    except UnsupportedUrlError:
        raise
    except OSError:
        raise UnsupportedUrlError("网络主机无法解析", "DNS_FAILED") from None
    addresses = records
    if not addresses:
        raise UnsupportedUrlError("网络主机无法解析", "DNS_FAILED")
    try:
        for address in addresses:
            parsed_address = ipaddress.ip_address(address)
            proxy_dns = (
                allow_proxy_dns is True
                and isinstance(parsed_address, ipaddress.IPv4Address)
                and parsed_address in _PROXY_DNS_RANGE
            )
            if not parsed_address.is_global and not proxy_dns:
                raise UnsupportedUrlError("网络主机解析到非公网地址", "UNSAFE_ADDRESS")
    except ValueError:
        raise UnsupportedUrlError("网络主机解析结果无效", "UNSAFE_ADDRESS") from None
    return addresses


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        host: str,
        ip_address: str,
        *,
        timeout: float,
        deadline: float | None = None,
        cancellation: Any | None = None,
    ) -> None:
        super().__init__(host, 443, timeout=timeout, context=ssl.create_default_context())
        self._validated_ip_address = ip_address
        self._deadline = deadline
        self._cancellation = cancellation
        self._deadline_timer: threading.Timer | None = None
        self._deadline_expired = False
        self._cancel_unregister: Any | None = None

    def arm_deadline(self) -> None:
        if self._deadline is None:
            return
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("HTTPS request exceeded its total deadline")
        timer = threading.Timer(remaining, self._interrupt_at_deadline)
        timer.daemon = True
        self._deadline_timer = timer
        timer.start()

    def _interrupt_at_deadline(self) -> None:
        self._deadline_expired = True
        sock = self.sock
        if sock is None:
            return
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass

    def close(self) -> None:
        timer = self._deadline_timer
        self._deadline_timer = None
        if timer is not None:
            timer.cancel()
        unregister = self._cancel_unregister
        self._cancel_unregister = None
        if unregister is not None:
            unregister()
        super().close()

    def abort(self) -> None:
        """Interrupt an active socket operation from a cancellation callback."""
        sock = self.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        self.close()

    def connect(self) -> None:
        timeout = self.timeout
        if self._deadline is not None:
            remaining = self._deadline - time.monotonic()
            if remaining <= 0 or self._deadline_expired:
                raise TimeoutError("HTTPS request exceeded its total deadline")
            timeout = min(timeout, remaining)
        family = socket.AF_INET6 if ":" in self._validated_ip_address else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        self.sock = sock
        try:
            address = (
                (self._validated_ip_address, self.port, 0, 0)
                if family == socket.AF_INET6
                else (self._validated_ip_address, self.port)
            )
            sock.connect(address)
            if self._cancellation is not None and self._cancellation.is_set():
                raise TimeoutError("HTTPS request was cancelled")
            if self._deadline is not None:
                remaining = self._deadline - time.monotonic()
                if remaining <= 0 or self._deadline_expired:
                    raise TimeoutError("HTTPS request exceeded its total deadline")
                sock.settimeout(min(timeout, remaining))
            # Publish the wrapped socket before the TLS handshake so the
            # deadline timer can interrupt a stalled handshake too.
            wrapped = self._context.wrap_socket(
                sock,
                server_hostname=self.host,
                do_handshake_on_connect=False,
            )
            self.sock = wrapped
            if self._cancellation is not None and self._cancellation.is_set():
                raise TimeoutError("HTTPS request was cancelled")
            wrapped.do_handshake()
            if self._deadline is not None and time.monotonic() >= self._deadline:
                raise TimeoutError("HTTPS request exceeded its total deadline")
        except Exception:
            self.close()
            raise


def open_pinned_https(
    url: str,
    *,
    allowed_hosts: frozenset[str] | set[str] | None = None,
    allowed_suffixes: frozenset[str] | set[str] = frozenset(),
    method: str = "GET",
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
    deadline: float | None = None,
    cancellation: Any | None = None,
    allow_proxy_dns: bool = False,
) -> tuple[_PinnedHTTPSConnection, http.client.HTTPResponse]:
    """Issue one validated HTTPS request, retaining hostname certificate verification."""
    if deadline is not None and time.monotonic() >= deadline:
        raise TimeoutError("HTTPS request exceeded its total deadline")
    parsed, address = validate_https_url(
        url,
        allowed_hosts=allowed_hosts,
        allowed_suffixes=allowed_suffixes,
        resolve_dns=True,
        deadline=deadline,
        cancellation=cancellation,
        allow_proxy_dns=allow_proxy_dns,
    )
    assert address is not None
    if deadline is not None and time.monotonic() >= deadline:
        raise TimeoutError("HTTPS request exceeded its total deadline")
    host = parsed.hostname.lower().rstrip(".")
    connection_options = {"timeout": timeout, "deadline": deadline}
    if cancellation is not None:
        connection_options["cancellation"] = cancellation
    connection = _PinnedHTTPSConnection(host, address, **connection_options)
    if cancellation is not None:
        connection._cancel_unregister = cancellation.register(connection.abort)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    try:
        if cancellation is not None and cancellation.is_set():
            raise UnsupportedUrlError("网络请求已取消", "CANCELLED")
        connection.arm_deadline()
        connection.request(method, path, headers=headers or {"User-Agent": "douyin-transcript/0.1"})
        return connection, connection.getresponse()
    except Exception:
        connection.close()
        raise


def _parse_supported_host(
    url: str,
    *,
    allowed_hosts: frozenset[str],
    code: str = "UNSUPPORTED_URL",
):
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        raise UnsupportedUrlError("抖音链接格式无效", code) from None
    if (
        parsed.scheme != "https"
        or host is None
        or host.lower().rstrip(".") not in allowed_hosts
        or port not in (None, 443)
        or parsed.username
        or parsed.password
        or parsed.fragment
        or "\\" in url
        or any(ord(char) < 32 for char in url)
    ):
        raise UnsupportedUrlError("仅支持允许列表中的 HTTPS 抖音链接", code)
    return parsed


def _direct_input(source_url: str, parsed, source_type: str = "direct") -> ResolvedInput:
    video_match = _VIDEO_PATH.fullmatch(parsed.path)
    video_id = video_match.group(1) if video_match else None
    if video_id is None and parsed.path.rstrip("/") == "/jingxuan":
        # Only the named modal_id parameter may identify this video. Tracking
        # parameters are ignored and never interpreted as an ID.
        matches = [
            item.split("=", 1)[1]
            for item in parsed.query.split("&")
            if item.startswith("modal_id=")
        ]
        if len(matches) == 1 and re.fullmatch(r"[0-9]{1,32}", matches[0]):
            video_id = matches[0]
    if video_id is None:
        raise UnsupportedUrlError("抖音链接中没有受支持的视频 ID")
    canonical = f"https://www.douyin.com/video/{video_id}"
    safe_source = urlsplit(source_url)
    source_without_query = urlunsplit(
        (safe_source.scheme, safe_source.netloc, safe_source.path, "", "")
    )
    return ResolvedInput(source_without_query, canonical, video_id, source_type)


def _request_short_redirect(
    url: str,
    *,
    deadline: float,
    cancellation: Any | None = None,
    allow_proxy_dns: bool = False,
) -> str | None:
    current = url
    for _ in range(SHORT_LINK_MAX_REDIRECTS + 1):
        connection, response = open_pinned_https(
            current,
            allowed_hosts=DOUYIN_SHORT_HOSTS,
            method="GET",
            headers={"User-Agent": "douyin-transcript/0.1", "Range": "bytes=0-0"},
            timeout=10.0,
            deadline=deadline,
            cancellation=cancellation,
            allow_proxy_dns=allow_proxy_dns,
        )
        try:
            if response.status not in (301, 302, 303, 307, 308):
                return None
            return response.getheader("Location")
        finally:
            response.close()
            connection.close()
    return None
