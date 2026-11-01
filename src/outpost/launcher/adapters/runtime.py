"""`ContainerRuntime` by running the `outpost` tool inside the container."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from outpost.domain.commands import CommandResult
from outpost.domain.errors import Unavailable
from outpost.domain.layout import TOOL, USER
from outpost.domain.status import ContainerStatus
from outpost.launcher.ports.docker import DockerHost

ROOT = "root"
POLL_SECONDS = 2.0


class ToolRuntime:
    def __init__(
        self,
        docker: DockerHost,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._docker = docker
        self._sleep = sleep
        self._clock = clock

    def wait_ready(self, container: str, timeout: float) -> ContainerStatus:
        deadline = self._clock() + timeout
        while True:
            result = self._tool(container, ["status", "--json"])
            if result.ok:
                status = ContainerStatus.from_json(result.stdout)
                if status.ready:
                    return status
            if self._clock() >= deadline:
                raise Unavailable(
                    f"{container} did not finish booting in {timeout:.0f}s; see `./outpost logs`"
                )
            self._sleep(POLL_SECONDS)

    def status(self, container: str) -> ContainerStatus:
        return ContainerStatus.from_json(self._tool(container, ["status", "--json"]).check().stdout)

    def routes(self, container: str) -> str:
        return self._tool(container, ["route", "ls"]).check().stdout

    def run_init(self, container: str) -> ContainerStatus:
        self._tool(container, ["init", "--if-changed"], user=ROOT).check()
        return self.status(container)

    def root_certificate(self, container: str) -> str:
        return self._tool(container, ["ca"]).check().stdout

    def _tool(self, container: str, argv: Sequence[str], *, user: str = USER) -> CommandResult:
        result = self._docker.exec(container, [TOOL, *argv], user=user)
        if result.missing_command:
            raise Unavailable(
                f"{container} has no `{TOOL}` tool: its image must derive from outpost/base"
            )
        return result
