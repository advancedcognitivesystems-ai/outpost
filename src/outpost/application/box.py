"""The box: its image (base image plus the Outpost layer) and its container."""

from __future__ import annotations

from outpost.domain.config import ResolvedConfig
from outpost.domain.fingerprint import fingerprint
from outpost.domain.resources import (
    BOX_DOCKER_DATA,
    BOX_EXCHANGE,
    BOX_WORKSPACES,
    HostLayout,
    Role,
)
from outpost.ports.engine import ContainerEngine, ContainerSpec, Mount, MountKind
from outpost.ports.interaction import TemplateRenderer
from outpost.ports.proxy import RouterConvention
from outpost.ports.shell import Shell

DOCKERFILE_TEMPLATE = "box/Dockerfile.tmpl"
INIT_TEMPLATE = "box/outpost-init.sh.tmpl"


class BoxImage:
    """Builds the box image only when the rendered Dockerfile or init script changed."""

    def __init__(
        self,
        config: ResolvedConfig,
        host: Shell,
        engine: ContainerEngine,
        templates: TemplateRenderer,
        router: RouterConvention,
    ) -> None:
        self._config = config
        self._host = host
        self._engine = engine
        self._templates = templates
        self._router = router

    def ensure(self, layout: HostLayout) -> str:
        box = self._config.box
        dockerfile = self._templates.render(
            DOCKERFILE_TEMPLATE, {"base_image": str(box.image.ref), "user": box.user}
        )
        init = self._templates.render(
            INIT_TEMPLATE, {"router_bootstrap": self._router.bootstrap_script()}
        )
        tag = self._config.resources.box_image(fingerprint(dockerfile, init))
        if not self._engine.image_exists(tag):
            context = layout.box_build_dir
            self._host.write_file(context / "Dockerfile", dockerfile)
            self._host.write_file(context / "outpost-init.sh", init, mode=0o755)
            self._engine.build(context, tag)
        return tag


def box_container(config: ResolvedConfig, layout: HostLayout, image: str) -> ContainerSpec:
    names = config.resources
    box = config.box
    return ContainerSpec(
        name=names.name(Role.BOX),
        image=image,
        isolation=config.target.host.isolation,
        hostname=f"outpost-{config.project.name}",
        mounts=(
            Mount(MountKind.VOLUME, names.name(Role.WORKSPACES), BOX_WORKSPACES),
            Mount(MountKind.VOLUME, names.name(Role.DOCKER_DATA), BOX_DOCKER_DATA),
            Mount(MountKind.VOLUME, names.name(Role.HOME), config.box_layout.home),
            Mount(MountKind.BIND, str(layout.exchange_dir), BOX_EXCHANGE),
        ),
        networks=(names.name(Role.EDGE_NETWORK),),
        env={**box.env, "OUTPOST_PROJECT": str(config.project.name)},
        cpus=box.cpus,
        memory_gb=box.memory_gb,
    )
