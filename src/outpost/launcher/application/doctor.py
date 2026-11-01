"""`./outpost doctor`: what is missing on your machine or on the host, before `up` needs it."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from outpost.domain.credentials import Tool
from outpost.domain.environment import Environment
from outpost.domain.errors import Unavailable
from outpost.domain.host import SshHost
from outpost.launcher.ports.credentials import LoginSource
from outpost.launcher.ports.devcontainer import DevContainerCli
from outpost.launcher.ports.docker import DockerHost
from outpost.launcher.ports.machine import Programs

DEVCONTAINER_INSTALL = "npm install -g @devcontainers/cli"


class Severity(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True)
class Finding:
    check: str
    severity: Severity
    detail: str


class Doctor:
    def __init__(
        self,
        env: Environment,
        *,
        programs: Programs,
        devcontainer: DevContainerCli,
        docker: DockerHost,
        sources: Mapping[Tool, LoginSource],
    ) -> None:
        self._env = env
        self._programs = programs
        self._devcontainer = devcontainer
        self._docker = docker
        self._sources = sources

    def run(self) -> tuple[Finding, ...]:
        findings = [
            self._program("docker CLI", ("docker", "--version"), "install Docker"),
            self._devcontainer_cli(),
        ]
        if isinstance(self._env.host, SshHost):
            findings.append(self._program("ssh", ("ssh", "-V"), "install OpenSSH"))
        findings.append(self._host())
        findings.extend(self._login(tool) for tool in self._env.credentials)
        return tuple(findings)

    def _program(self, name: str, argv: tuple[str, ...], fix: str) -> Finding:
        version = self._programs.version(argv)
        if version is None:
            return Finding(name, Severity.FAIL, f"not found: {fix}")
        return Finding(name, Severity.OK, version)

    def _devcontainer_cli(self) -> Finding:
        version = self._devcontainer.version()
        if version is None:
            return Finding("Dev Container CLI", Severity.FAIL, f"not found: {DEVCONTAINER_INSTALL}")
        return Finding("Dev Container CLI", Severity.OK, version)

    def _host(self) -> Finding:
        name = f"Docker on {self._env.host}"
        try:
            return Finding(name, Severity.OK, f"engine {self._docker.server_version()}")
        except Unavailable as error:
            return Finding(name, Severity.FAIL, str(error))

    def _login(self, tool: Tool) -> Finding:
        source = self._sources[tool]
        if source.read() is None:
            detail = f"none in {source.description}; `up` will offer a login in the container"
            return Finding(f"{tool} login", Severity.WARN, detail)
        return Finding(f"{tool} login", Severity.OK, f"found in {source.description}")
