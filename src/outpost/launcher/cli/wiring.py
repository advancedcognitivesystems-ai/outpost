"""The composition root: the only module that builds adapters and hands them to use cases."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from outpost.domain.environment import Environment
from outpost.domain.host import SshHost
from outpost.infra.process import Runner, stderr_runner
from outpost.launcher.adapters.base_image import CheckoutBaseImage
from outpost.launcher.adapters.devcontainer_cli import DevContainerCliAdapter
from outpost.launcher.adapters.docker_cli import DockerCli
from outpost.launcher.adapters.logins import login_source, tool_login
from outpost.launcher.adapters.machine import (
    LocalFiles,
    ProgramVersions,
    SshTunnel,
    TerminalConsole,
)
from outpost.launcher.adapters.runtime import ToolRuntime
from outpost.launcher.application.access import Access
from outpost.launcher.application.doctor import Doctor
from outpost.launcher.application.lifecycle import Lifecycle
from outpost.launcher.application.logins import Logins
from outpost.launcher.application.transfers import Transfers
from outpost.launcher.application.up import Up
from outpost.launcher.config.loader import load, locate
from outpost.launcher.ports.machine import Console

HOME_VARIABLE = "OUTPOST_HOME"


@dataclass(frozen=True)
class Options:
    config: Path | None = None
    verbose: bool = False
    assume_yes: bool = False


def outpost_home(environ: Mapping[str, str]) -> Path:
    """The Outpost checkout: set by the `./outpost` script, else found from this file."""
    configured = environ.get(HOME_VARIABLE)
    return Path(configured) if configured else Path(__file__).resolve().parents[4]


class Launcher:
    def __init__(
        self,
        options: Options,
        *,
        environ: Mapping[str, str] = os.environ,
        cwd: Path | None = None,
    ) -> None:
        self._options = options
        self._environ = environ
        self._cwd = cwd or Path.cwd()

    @cached_property
    def env(self) -> Environment:
        return load(locate(self._options.config, self._environ, self._cwd), self._cwd)

    @cached_property
    def console(self) -> Console:
        return TerminalConsole(assume_yes=self._options.assume_yes, interactive=sys.stdin.isatty())

    @cached_property
    def _runner(self) -> Runner:
        return stderr_runner(self._options.verbose)

    @cached_property
    def _docker(self) -> DockerCli:
        host = self.env.host
        environment = {"DOCKER_HOST": host.docker_host} if isinstance(host, SshHost) else None
        return DockerCli(
            self._runner,
            description=str(host),
            environment=environment,
            terminal=sys.stdin.isatty() and sys.stdout.isatty(),
        )

    @cached_property
    def _local_docker(self) -> DockerCli | None:
        if not isinstance(self.env.host, SshHost):
            return None
        return DockerCli(self._runner, description="your Docker")

    @cached_property
    def _devcontainer(self) -> DevContainerCliAdapter:
        return DevContainerCliAdapter(self._runner, environment=self._docker.environment)

    @cached_property
    def _runtime(self) -> ToolRuntime:
        return ToolRuntime(self._docker)

    @cached_property
    def _transfers(self) -> Transfers:
        return Transfers(self._docker, LocalFiles(), self.env.container)

    def up(self) -> Up:
        logins = Logins(
            self.console,
            [
                (
                    login_source(tool, self._runner, self._environ),
                    tool_login(tool, self._docker, self.env.container),
                )
                for tool in self.env.credentials
            ],
        )
        return Up(
            self.env,
            docker=self._docker,
            local_docker=self._local_docker,
            devcontainer=self._devcontainer,
            runtime=self._runtime,
            base_image=CheckoutBaseImage(outpost_home(self._environ)),
            console=self.console,
            logins=logins,
            transfers=self._transfers,
        )

    def lifecycle(self) -> Lifecycle:
        return Lifecycle(self.env, self._docker, self._runtime, self.console)

    def access(self) -> Access:
        return Access(self.env, self._docker, self._runtime, SshTunnel(self._runner))

    def transfers(self) -> Transfers:
        return self._transfers

    def doctor(self) -> Doctor:
        return Doctor(
            self.env,
            programs=ProgramVersions(self._runner),
            devcontainer=self._devcontainer,
            docker=self._docker,
            sources={
                tool: login_source(tool, self._runner, self._environ)
                for tool in self.env.credentials
            },
        )
