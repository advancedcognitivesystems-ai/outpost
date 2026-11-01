"""`ContainerRuntime` by running the `outpost` tool inside the container."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from pathlib import PurePosixPath

from outpost.domain.errors import CommandFailed, Unavailable
from outpost.domain.layout import ROOT_USER, TOOL, USER
from outpost.domain.status import INIT_SCRIPTS_FAILED, ContainerStatus
from outpost.infra.process import COMMAND_NOT_FOUND, CommandResult
from outpost.launcher.adapters.docker_cli import DockerCli

POLL_SECONDS = 2.0
NO_IMAGE_TOOL = "{container} has no `{tool}` tool: its image must derive from outpost/base"


class ToolRuntime:
    def __init__(
        self,
        docker: DockerCli,
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

    def start_proxy(self, container: str) -> ContainerStatus:
        self._tool(container, ["proxy", "start"], user=ROOT_USER).check()
        return self.status(container)

    def run_init(self, container: str) -> ContainerStatus:
        argv = [TOOL, "init", "--if-changed"]
        code = self._docker.exec_attached(
            container, argv, user=ROOT_USER, workdir=PurePosixPath("/")
        )
        if code == COMMAND_NOT_FOUND:
            raise Unavailable(NO_IMAGE_TOOL.format(container=container, tool=TOOL))
        if code not in (0, INIT_SCRIPTS_FAILED):
            raise CommandFailed(argv, code, "see the output above")
        return self.status(container)

    def root_certificate(self, container: str) -> str:
        return self._tool(container, ["ca"]).check().stdout

    def _tool(self, container: str, argv: Sequence[str], *, user: str = USER) -> CommandResult:
        result = self._docker.exec(container, [TOOL, *argv], user=user)
        if result.missing_command:
            raise Unavailable(NO_IMAGE_TOOL.format(container=container, tool=TOOL))
        return result
