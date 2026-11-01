"""The host's Docker engine, wherever it runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePath, PurePosixPath
from typing import Protocol

from outpost.domain.commands import CommandResult
from outpost.domain.names import ImageRef
from outpost.domain.volumes import Volume


class ContainerState(StrEnum):
    MISSING = "missing"
    RUNNING = "running"
    STOPPED = "stopped"


@dataclass(frozen=True)
class ContainerInfo:
    state: ContainerState
    settings_digest: str | None = None


class DockerHost(Protocol):
    @property
    def description(self) -> str: ...

    def server_version(self) -> str:
        """The engine's version; raises `Unavailable` when the engine does not answer."""
        ...

    def container(self, name: str) -> ContainerInfo: ...

    def image_exists(self, image: ImageRef) -> bool: ...

    def build_image(self, image: ImageRef, context: PurePath, dockerfile: PurePath) -> None: ...

    def load_image(self, image: ImageRef, source: DockerHost) -> None:
        """Copy an image from another engine, streamed, with nothing written to disk on the way."""
        ...

    def ensure_volume(self, volume: Volume, labels: Mapping[str, str]) -> None: ...

    def volumes(self, labels: Mapping[str, str]) -> tuple[str, ...]: ...

    def remove_volumes(self, names: Sequence[str]) -> None: ...

    def stop(self, container: str) -> None: ...

    def remove(self, container: str) -> None: ...

    def exec(
        self, container: str, argv: Sequence[str], *, user: str, stdin: str | None = None
    ) -> CommandResult: ...

    def exec_attached(
        self, container: str, argv: Sequence[str], *, user: str, workdir: PurePosixPath
    ) -> int: ...

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
