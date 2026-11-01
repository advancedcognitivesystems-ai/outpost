"""`outpost up`, `down` and `status`: the host converged to the configuration, step by step."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from outpost.application.box import BoxImage, box_container
from outpost.application.containers import Change, converge
from outpost.application.credentials import CredentialSync
from outpost.application.doctor import Doctor
from outpost.domain.config import ResolvedConfig
from outpost.domain.errors import Unavailable
from outpost.domain.resources import HostLayout, Role, expand_home
from outpost.ports.engine import ContainerEngine, ContainerState
from outpost.ports.images import ImageSupplier
from outpost.ports.interaction import Prompter
from outpost.ports.probe import MachineProbe
from outpost.ports.proxy import EdgeProxy, RouterConvention
from outpost.ports.repository import Repository
from outpost.ports.shell import Shell
from outpost.ports.tls import TlsProvisioner

VOLUMES = (Role.WORKSPACES, Role.DOCKER_DATA, Role.HOME, Role.EDGE_DATA)
INNER_ENGINE_ATTEMPTS = 60


@dataclass(frozen=True)
class EnvironmentStatus:
    edge: ContainerState
    box: ContainerState


class InnerRouter:
    """The router on the box's inner engine, once that engine answers."""

    def __init__(
        self,
        engine: ContainerEngine,
        router: RouterConvention,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._engine = engine
        self._router = router
        self._sleep = sleep

    def ensure(self) -> Change:
        for _ in range(INNER_ENGINE_ATTEMPTS):
            if self._engine.version():
                break
            self._sleep(1)
        else:
            raise Unavailable("the box's Docker engine did not start; see /var/log/dockerd.log")
        self._engine.ensure_network(self._router.network)
        return converge(self._engine, self._router.container())


class Environment:
    def __init__(
        self,
        *,
        config: ResolvedConfig,
        doctor: Doctor,
        host: Shell,
        host_probe: MachineProbe,
        engine: ContainerEngine,
        images: ImageSupplier,
        box_image: BoxImage,
        tls: TlsProvisioner,
        edge: EdgeProxy,
        router: InnerRouter,
        credentials: CredentialSync,
        repository: Repository,
        prompter: Prompter,
    ) -> None:
        self._config = config
        self._doctor = doctor
        self._host = host
        self._host_probe = host_probe
        self._engine = engine
        self._images = images
        self._box_image = box_image
        self._tls = tls
        self._edge = edge
        self._router = router
        self._credentials = credentials
        self._repository = repository
        self._prompter = prompter

    def layout(self) -> HostLayout:
        home = self._host_probe.home()
        return HostLayout(expand_home(self._config.target.host.state_dir, home))

    def up(self) -> None:
        report = self._doctor.run(fix=True)
        if report.blocking:
            problems = "; ".join(f"{item.title}: {item.detail}" for item in report.failures)
            raise Unavailable(f"doctor found blocking problems: {problems}")
        layout = self.layout()
        names = self._config.resources

        self._step("base image", lambda: self._images.ensure(self._config.box.image.ref))
        tag = self._box_image.ensure(layout)
        self._prompter.info(f"box image: {tag}")

        self._engine.ensure_network(names.name(Role.EDGE_NETWORK))
        for role in VOLUMES:
            self._engine.ensure_volume(names.name(role))
        self._host.ensure_directory(layout.exchange_dir)

        material = self._tls.prepare(layout)
        self._report("edge", converge(self._engine, self._edge.prepare(layout, material)))
        box = box_container(self._config, layout, tag)
        self._report("box", converge(self._engine, box, allow_recreate=self._confirm_recreate))
        self._report("router", self._router.ensure())

        self._credentials.sync()
        if not self._repository.is_cloned():
            self._step("clone", self._repository.clone)
        self._repository.set_identity(self._config.credentials.git)
        self._prompter.info("ready: `outpost worktree add <name>`, then `outpost stack up <name>`")

    def down(self) -> None:
        names = self._config.resources
        for role in (Role.BOX, Role.EDGE):
            if self._engine.state(names.name(role)) is ContainerState.RUNNING:
                self._engine.stop(names.name(role))
                self._prompter.info(f"{role.value}: stopped")

    def status(self) -> EnvironmentStatus:
        names = self._config.resources
        return EnvironmentStatus(
            edge=self._engine.state(names.name(Role.EDGE)),
            box=self._engine.state(names.name(Role.BOX)),
        )

    def trust_bundle(self) -> str | None:
        return self._tls.client_trust_bundle(self.layout())

    def _confirm_recreate(self) -> bool:
        return self._prompter.confirm(
            "The box settings changed; recreating it restarts agents and stacks "
            "(volumes are kept). Recreate now?",
            default=True,
        )

    def _step(self, name: str, action: Callable[[], None]) -> None:
        self._prompter.info(f"{name}: ...")
        action()
        self._prompter.info(f"{name}: done")

    def _report(self, name: str, change: Change) -> None:
        self._prompter.info(f"{name}: {change.value}")
