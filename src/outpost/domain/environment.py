"""One environment: everything `outpost.yaml` says, resolved, with Outpost's defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePath, PurePosixPath

from outpost.domain.credentials import Tool
from outpost.domain.devcontainer import DevContainerDefinition, DevContainerSettings, define
from outpost.domain.host import Host, LocalHost
from outpost.domain.layout import DEFAULT_DOMAIN, DEFAULT_NAME, DEFAULT_PORT, ENVIRONMENT_LABEL
from outpost.domain.names import DnsName, EnvironmentName, ImageRef
from outpost.domain.routes import Site
from outpost.domain.volumes import Volume, volumes_for

GENERATED_DIR = ".outpost"
DEFAULT_ENVIRONMENT = EnvironmentName(DEFAULT_NAME)
DEFAULT_SITE = Site(DnsName(DEFAULT_DOMAIN), DEFAULT_PORT)


@dataclass(frozen=True)
class FileCopy:
    """A file or folder of yours copied into the container on every `up`."""

    source: PurePath
    target: PurePosixPath


@dataclass(frozen=True)
class Environment:
    root: PurePath
    """The folder holding outpost.yaml; paths on your machine are relative to it."""
    name: EnvironmentName = DEFAULT_ENVIRONMENT
    host: Host = field(default_factory=LocalHost)
    site: Site = DEFAULT_SITE
    devcontainer: DevContainerSettings = field(default_factory=DevContainerSettings)
    init_scripts: tuple[PurePath, ...] = ()
    credentials: tuple[Tool, ...] = (Tool.CLAUDE, Tool.GITHUB)
    copies: tuple[FileCopy, ...] = ()
    persist: tuple[PurePosixPath, ...] = ()

    @property
    def container(self) -> str:
        return self.name.container

    @property
    def volumes(self) -> tuple[Volume, ...]:
        return volumes_for(self.name, self.persist)

    @property
    def labels(self) -> dict[str, str]:
        """Labels on everything Outpost creates for this environment, so it can find it again."""
        return {ENVIRONMENT_LABEL: self.name.value}

    @property
    def id_label(self) -> str:
        return f"{ENVIRONMENT_LABEL}={self.name}"

    @property
    def workdir(self) -> PurePath:
        """Where Outpost writes the devcontainer.json it runs."""
        return self.root / GENERATED_DIR / self.name.value

    def definition(self, base: ImageRef) -> DevContainerDefinition:
        return define(
            name=self.name,
            site=self.site,
            volumes=self.volumes,
            settings=self.devcontainer,
            root=self.root,
            base=base,
        )
