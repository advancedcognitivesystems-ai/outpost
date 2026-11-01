"""`./outpost up`: from nothing, or from any state, to a running and logged-in dev container."""

from __future__ import annotations

from dataclasses import dataclass

from outpost.domain.credentials import LoginState
from outpost.domain.devcontainer import DevContainerDefinition
from outpost.domain.environment import Environment
from outpost.domain.errors import ConfigError
from outpost.domain.exposure import exposure_problems
from outpost.domain.names import DnsName
from outpost.domain.status import ContainerStatus
from outpost.launcher.application.logins import Logins
from outpost.launcher.application.transfers import Transfers
from outpost.launcher.ports.devcontainer import DevContainerCli
from outpost.launcher.ports.docker import ContainerState, DockerHost, ImageTransfer
from outpost.launcher.ports.machine import BaseImageSource, Console
from outpost.launcher.ports.runtime import ContainerRuntime

READY_TIMEOUT = 300.0
EXAMPLE_ROUTE = DnsName("api.feat-a")
RECREATE_QUESTION = (
    "The dev container's settings changed. Recreate it? "
    "Volumes are kept; changes outside them are lost."
)


@dataclass(frozen=True)
class UpReport:
    status: ContainerStatus
    logins: tuple[LoginState, ...]
    example_url: str
    recreated: bool


class Up:
    def __init__(
        self,
        env: Environment,
        *,
        docker: DockerHost,
        images_from_you: ImageTransfer | None,
        devcontainer: DevContainerCli,
        runtime: ContainerRuntime,
        base_image: BaseImageSource,
        console: Console,
        logins: Logins,
        transfers: Transfers,
    ) -> None:
        self._env = env
        self._docker = docker
        self._images_from_you = images_from_you
        self._devcontainer = devcontainer
        self._runtime = runtime
        self._base_image = base_image
        self._console = console
        self._logins = logins
        self._transfers = transfers

    def plan(self) -> DevContainerDefinition:
        """The devcontainer.json `up` runs; needs no Docker."""
        return self._env.definition(self._base_image.reference())

    def run(self, *, recreate: bool = False, assume_yes: bool = False) -> UpReport:
        self._docker.server_version()
        definition = self.plan()
        self._ensure_images(definition)
        for volume in self._env.volumes:
            self._docker.ensure_volume(volume, self._env.labels)
        recreate = self._must_recreate(definition, recreate, assume_yes)
        if recreate:
            self._docker.stop(self._env.container)
        self._devcontainer.up(definition, self._env.workdir, self._env.id_label, recreate=recreate)
        self._refuse_exposure()
        booted = self._runtime.wait_ready(self._env.container, READY_TIMEOUT)
        if not booted.proxy_running:
            self._console.warn("the proxy is not running; see `./outpost logs`")
        logins = self._logins.ensure_all()
        for item in self._env.copies:
            self._transfers.copy_to(item.source, item.target)
        self._transfers.sync_init(self._env.init_scripts)
        status = self._runtime.run_init(self._env.container)
        if status.init_failed:
            self._console.warn(f"init scripts failed: {', '.join(status.init_failed)}")
        return UpReport(status, logins, self._env.site.url(EXAMPLE_ROUTE), recreate)

    def _ensure_images(self, definition: DevContainerDefinition) -> None:
        if definition.needs_base:
            base = self._base_image.reference()
            if not self._docker.image_exists(base):
                self._console.info(f"building {base} on {self._docker.description}")
                self._docker.build_image(
                    base, self._base_image.context, self._base_image.dockerfile
                )
        image = definition.image
        mine = self._images_from_you
        if (
            image is not None
            and mine is not None
            and not self._docker.image_exists(image)
            and mine.available(image)
        ):
            self._console.info(f"copying {image} from {mine.description} to the host")
            mine.send(image)

    def _refuse_exposure(self) -> None:
        """Features and image metadata may add mounts: refuse the container if they did."""
        container = self._env.container
        problems = exposure_problems(self._docker.exposure(container), self._env.site)
        if not problems:
            return
        self._docker.stop(container)
        self._docker.remove(container)
        raise ConfigError(
            "devcontainer",
            f"the container was removed, its volumes kept: {'; '.join(problems)}. "
            "A feature or the image asks for it; remove that feature or change the image.",
        )

    def _must_recreate(
        self, definition: DevContainerDefinition, asked: bool, assume_yes: bool
    ) -> bool:
        info = self._docker.container(self._env.container)
        if info.state is ContainerState.MISSING:
            return False
        if asked:
            return True
        if info.settings_digest == definition.settings_digest:
            return False
        if assume_yes or self._console.confirm(RECREATE_QUESTION, default=False):
            return True
        self._console.warn("keeping the current container; its settings are not the new ones")
        return False
