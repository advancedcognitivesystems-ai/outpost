"""Ways into the running container: a shell, a command, its log, its CA, the tunnel."""

from __future__ import annotations

from collections.abc import Sequence

from outpost.domain.environment import Environment
from outpost.domain.errors import Unavailable
from outpost.domain.host import LocalHost, SshHost
from outpost.domain.layout import USER, WORKSPACES
from outpost.launcher.ports.docker import ContainerState, DockerHost
from outpost.launcher.ports.machine import Tunnel
from outpost.launcher.ports.runtime import ContainerRuntime

LOGIN_SHELL = ("bash", "-l")


class Access:
    def __init__(
        self, env: Environment, docker: DockerHost, runtime: ContainerRuntime, tunnel: Tunnel
    ) -> None:
        self._env = env
        self._docker = docker
        self._runtime = runtime
        self._tunnel = tunnel

    def shell(self) -> int:
        return self.run(LOGIN_SHELL)

    def run(self, argv: Sequence[str]) -> int:
        self._require_running()
        return self._docker.exec_attached(self._env.container, argv, user=USER, workdir=WORKSPACES)

    def logs(self, *, follow: bool) -> int:
        return self._docker.logs(self._env.container, follow=follow)

    def root_certificate(self) -> str:
        self._require_running()
        return self._runtime.root_certificate(self._env.container)

    def tunnel(self) -> int:
        match self._env.host:
            case LocalHost():
                raise Unavailable(
                    f"the host is local: open {self._env.site.url_pattern()} directly, "
                    "no tunnel needed"
                )
            case SshHost() as host:
                return self._tunnel.forward(host, self._env.site.port)

    def _require_running(self) -> None:
        if self._docker.container(self._env.container).state is not ContainerState.RUNNING:
            raise Unavailable(f"{self._env.container} is not running; run `./outpost up` first")
