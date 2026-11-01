"""The host's Docker engine, wherever it runs, and moving images to it."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePath, PurePosixPath
from typing import Protocol

from outpost.domain.exposure import Exposure
from outpost.domain.names import ImageRef
from outpost.domain.volumes import Volume


class ContainerState(StrEnum):
    MISSING = "missing"
    RUNNING = "running"
    STOPPED = "stopped"
    RESTARTING = "restarting"


@dataclass(frozen=True)
class ContainerInfo:
    state: ContainerState
    settings_digest: str | None = None
    status: str = ""
    """Docker's own word for it, such as `exited` or `created`."""


class DockerHost(Protocol):
    @property
    def description(self) -> str: ...

    def server_version(self) -> str:
        """The engine's version; raises `Unavailable` when the engine does not answer."""
        ...

    def container(self, name: str) -> ContainerInfo: ...

    def exposure(self, container: str) -> Exposure:
        """Its mounts, network mode and published ports, as the engine reports them."""
        ...

    def image_exists(self, image: ImageRef) -> bool: ...

    def build_image(self, image: ImageRef, context: PurePath, dockerfile: PurePath) -> None: ...

    def ensure_volume(self, volume: Volume, labels: Mapping[str, str]) -> None: ...

    def volumes(self, labels: Mapping[str, str]) -> tuple[str, ...]: ...

    def remove_volumes(self, names: Sequence[str]) -> None: ...

    def stop(self, container: str) -> None:
        """Stop gracefully: the container's stop timeout lets its inner Docker stop the stacks."""
        ...

    def remove(self, container: str) -> None: ...

    def exec_attached(
        self, container: str, argv: Sequence[str], *, user: str, workdir: PurePosixPath
    ) -> int:
        """Run a program in the container on your terminal."""
        ...

    def is_directory(self, container: str, path: PurePosixPath) -> bool: ...

    def reset_directory(self, container: str, path: PurePosixPath, *, user: str) -> None:
        """Make `path` an empty directory owned by `user`."""
        ...

    def copy_in(
        self, container: str, source: PurePath, directory: PurePosixPath, name: str, *, user: str
    ) -> None:
        """Copy a file or folder of yours into `directory/name`, written as `user`."""
        ...

    def copy_out(
        self, container: str, source: PurePosixPath, directory: PurePath, name: str, *, user: str
    ) -> None:
        """Copy a file or folder of the container to `directory/name` on your machine."""
        ...

    def logs(self, container: str, *, follow: bool) -> int: ...


class ImageTransfer(Protocol):
    """Images on your machine's Docker, sent to a remote host when only you have them."""

    @property
    def description(self) -> str: ...

    def available(self, image: ImageRef) -> bool: ...

    def send(self, image: ImageRef) -> None:
        """Stream it to the host, with nothing written to disk on the way."""
        ...
