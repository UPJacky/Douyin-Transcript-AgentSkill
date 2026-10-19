"""Legacy application-side placeholders for the unavailable WFP broker.

The project does not currently ship a Windows service, authenticated IPC
transport, or broker trust anchor. ``open_system_broker`` therefore fails
closed. These in-process interfaces are not the v1 capture wire contract:
that contract submits one original URL and bounded limits so a future worker
can own browser capture and media download end to end. Neither these types nor
the protocol codec attest that any WFP policy is active.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class IsolationBrokerUnavailable(RuntimeError):
    """No authenticated, supported system broker is available."""


class IsolationLeaseLost(RuntimeError):
    """The broker could not confirm that a capture lease is still active."""


@dataclass(frozen=True, slots=True)
class BrowserIdentity:
    """Legacy browser identity shape; it is not exposed by capture IPC v1."""

    executable_path: Path
    executable_sha256: str
    playwright_version: str
    chromium_revision: str


@dataclass(frozen=True, slots=True)
class ProxyEndpoint:
    """Legacy proxy shape; capture IPC v1 does not return a proxy endpoint."""

    host: str
    port: int


class IsolationLease(Protocol):
    """Legacy shape retained for existing integration points, not v1 IPC.

    Returning browser identity and proxy details to the caller conflicts with
    the full-job service protocol. A production implementation must not expose
    these fields to an untrusted caller; the worker should own browser startup,
    network policy, capture, and download. No such implementation exists yet.
    """

    @property
    def browser(self) -> BrowserIdentity:
        """Protected Chromium identity selected and verified by the broker."""

    @property
    def proxy_endpoint(self) -> ProxyEndpoint:
        """Exact service-owned loopback HTTP proxy endpoint for this lease."""

    def ensure_active(self) -> None:
        """Read locally cached health; never perform IPC or wait in a route callback.

        A future adapter must maintain broker heartbeats asynchronously and
        make this a nonblocking state check. No such monitor is implemented in
        this project yet.
        """

    def close(self) -> None:
        """Release the lease and its temporary proxy exception."""


class IsolationBroker(Protocol):
    """Legacy broker interface; no authenticated transport is implemented."""

    def acquire(self) -> IsolationLease:
        """Derive peer identity and return broker-selected lease resources."""


def open_system_broker() -> IsolationBroker:
    """Fail closed because no reviewed platform broker adapter exists.

    The v1 capture protocol is a contract only, not a transport or trust anchor.
    A future adapter needs authenticated peer identity, a reviewed IPC ACL, and
    administrator-owned service identity. A pipe name, environment variable,
    proxy probe, or provider boolean does not prove that WFP rules are active.
    """

    raise IsolationBrokerUnavailable
