"""The Outpost runtime inside the container, as the launcher sees it: the `outpost` tool."""

from __future__ import annotations

from typing import Protocol

from outpost.domain.status import ContainerStatus


class ContainerRuntime(Protocol):
    def wait_ready(self, container: str, timeout: float) -> ContainerStatus:
        """Wait until boot has finished; raises `Unavailable` after `timeout` seconds."""
        ...

    def status(self, container: str) -> ContainerStatus: ...

    def routes(self, container: str) -> str:
        """The route listing, as `outpost route ls` prints it."""
        ...

    def start_proxy(self, container: str) -> ContainerStatus:
        """Start the proxy, or create it again, with its routes."""
        ...

    def run_init(self, container: str) -> ContainerStatus:
        """Run the init scripts if they changed since they last ran, showing their output."""
        ...

    def root_certificate(self, container: str) -> str: ...
