"""The proxy: its routes through its API, and the container it runs in."""

from __future__ import annotations

from typing import Protocol

from outpost.domain.names import DnsName
from outpost.domain.routes import Route


class Proxy(Protocol):
    def running(self) -> bool: ...

    def wait_ready(self, timeout: float) -> None:
        """Wait until the API answers; raises `Unavailable` after `timeout` seconds."""
        ...

    def routes(self) -> tuple[Route, ...]: ...

    def put(self, route: Route) -> None:
        """Add the route, or replace the route of the same name."""
        ...

    def remove(self, name: DnsName) -> None: ...

    def root_certificate(self) -> str: ...


class ProxyRuntime(Protocol):
    def ensure_running(self) -> None:
        """Create the network and the proxy when missing, upgrade the proxy, start it."""
        ...
