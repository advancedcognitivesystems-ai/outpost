"""The Dev Container CLI, which applies features and starts the container."""

from __future__ import annotations

from pathlib import PurePath
from typing import Protocol

from outpost.domain.devcontainer import DevContainerDefinition


class DevContainerCli(Protocol):
    def version(self) -> str | None:
        """The CLI's version, or None when it is not installed."""
        ...

    def up(
        self,
        definition: DevContainerDefinition,
        workdir: PurePath,
        id_label: str,
        *,
        recreate: bool,
    ) -> None:
        """Write the definition under `workdir`, then create or start the container from it."""
        ...
