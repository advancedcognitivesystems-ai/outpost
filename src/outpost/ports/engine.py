"""Containers, images, networks and volumes on one machine."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Protocol

from outpost.domain.config import Isolation
from outpost.domain.secrets import Secret
from outpost.ports.shell import CommandResult


class MountKind(StrEnum):
    VOLUME = "volume"
    BIND = "bind"


@dataclass(frozen=True)
class Mount:
    kind: MountKind
    source: str
    target: PurePosixPath
    read_only: bool = False


@dataclass(frozen=True)
class PortBinding:
    host_ip: str
    host_port: int
    container_port: int


@dataclass(frozen=True)
class ContainerSpec:
    name: str
    image: str
    isolation: Isolation | None = None
    hostname: str | None = None
    mounts: tuple[Mount, ...] = ()
    ports: tuple[PortBinding, ...] = ()
    networks: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    env_files: tuple[PurePosixPath, ...] = ()
    labels: Mapping[str, str] = field(default_factory=dict)
    cpus: float | None = None
    memory_gb: int | None = None
    restart_unless_stopped: bool = True
    command: tuple[str, ...] = ()


class ContainerState(StrEnum):
    MISSING = "missing"
    RUNNING = "running"
    STOPPED = "stopped"


FINGERPRINT_LABEL = "outpost.fingerprint"


class ContainerEngine(Protocol):
    def version(self) -> str | None:
        """Server version, or None when the engine cannot be reached."""
        ...

    def supports(self, isolation: Isolation) -> bool: ...

    def image_exists(self, ref: str) -> bool: ...

    def pull(self, ref: str) -> None: ...

    def build(self, context: PurePosixPath, tag: str) -> None: ...

    def save(self, ref: str, archive: Path) -> None:
        """Write an image to an archive on this engine's machine."""
        ...

    def load(self, archive: PurePosixPath) -> None: ...

    def login(self, registry: str, username: str, password: Secret) -> None: ...

    def ensure_network(self, name: str) -> None: ...

    def ensure_volume(self, name: str) -> None: ...

    def state(self, container: str) -> ContainerState: ...

    def label(self, container: str, key: str) -> str | None: ...

    def run(self, spec: ContainerSpec) -> None:
        """Create and start a container; it must not exist yet."""
        ...

    def start(self, container: str) -> None: ...

    def stop(self, container: str) -> None: ...

    def remove(self, container: str) -> None: ...

    def exec(
        self,
        container: str,
        argv: Sequence[str],
        *,
        user: str | None = None,
        stdin: str | None = None,
        workdir: PurePosixPath | None = None,
    ) -> CommandResult: ...

    def exec_interactive(
        self,
        container: str,
        argv: Sequence[str],
        *,
        user: str | None = None,
        workdir: PurePosixPath | None = None,
    ) -> int: ...

    def copy_into(self, container: str, source: PurePosixPath, target: PurePosixPath) -> None:
        """Copy a file from the engine's machine into a container."""
        ...
