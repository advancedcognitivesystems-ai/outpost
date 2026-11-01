"""Stop, remove, destroy, and report: what happens to the container and its volumes."""

from __future__ import annotations

from dataclasses import dataclass

from outpost.domain.environment import Environment
from outpost.domain.errors import Declined
from outpost.domain.status import ContainerStatus
from outpost.launcher.ports.docker import ContainerState, DockerHost
from outpost.launcher.ports.machine import Console
from outpost.launcher.ports.runtime import ContainerRuntime


@dataclass(frozen=True)
class EnvironmentStatus:
    container: str
    state: ContainerState
    volumes: tuple[str, ...]
    runtime: ContainerStatus | None
    routes: str


class Lifecycle:
    def __init__(
        self, env: Environment, docker: DockerHost, runtime: ContainerRuntime, console: Console
    ) -> None:
        self._env = env
        self._docker = docker
        self._runtime = runtime
        self._console = console

    def stop(self) -> bool:
        """Stop the container; its disk stays exactly as it is. False when it was not running."""
        if self._state() is not ContainerState.RUNNING:
            return False
        self._docker.stop(self._env.container)
        return True

    def down(self) -> bool:
        """Remove the container and keep the volumes. False when there was no container."""
        if self._state() is ContainerState.MISSING:
            return False
        self._docker.remove(self._env.container)
        return True

    def destroy(self, *, assume_yes: bool) -> tuple[str, ...]:
        """Remove the container and every volume labelled with this environment."""
        volumes = self._docker.volumes(self._env.labels)
        if not assume_yes:
            question = (
                f"This removes {self._env.container} and {len(volumes)} volumes: logins, "
                f"workspaces, images and the proxy's CA. Type '{self._env.name}' to confirm:"
            )
            if self._console.ask(question).strip() != self._env.name.value:
                raise Declined("nothing was removed")
        if self._state() is not ContainerState.MISSING:
            self._docker.remove(self._env.container)
        if volumes:
            self._docker.remove_volumes(volumes)
        return volumes

    def status(self) -> EnvironmentStatus:
        state = self._state()
        running = state is ContainerState.RUNNING
        container = self._env.container
        return EnvironmentStatus(
            container=container,
            state=state,
            volumes=self._docker.volumes(self._env.labels),
            runtime=self._runtime.status(container) if running else None,
            routes=self._runtime.routes(container) if running else "",
        )

    def _state(self) -> ContainerState:
        return self._docker.container(self._env.container).state
