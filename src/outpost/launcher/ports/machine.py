"""Your machine: the person at the terminal, its programs, its files, its SSH client."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import PurePath
from typing import Protocol

from outpost.domain.host import SshHost
from outpost.domain.names import ImageRef


class Console(Protocol):
    @property
    def interactive(self) -> bool:
        """Whether someone can answer: an interactive login needs a terminal."""
        ...

    def info(self, message: str) -> None: ...

    def warn(self, message: str) -> None: ...

    def confirm(self, question: str, *, default: bool) -> bool: ...

    def ask(self, question: str) -> str: ...


class Programs(Protocol):
    def version(self, argv: Sequence[str]) -> str | None:
        """The first line a program prints, or None when it is missing or fails."""
        ...


class Files(Protocol):
    def is_dir(self, path: PurePath) -> bool: ...

    def exists(self, path: PurePath) -> bool: ...


class BaseImageSource(Protocol):
    """The sources of the default image, in the Outpost checkout."""

    def reference(self) -> ImageRef:
        """The image's reference, tagged with a digest of its sources."""
        ...

    @property
    def context(self) -> PurePath: ...

    @property
    def dockerfile(self) -> PurePath: ...


class Tunnel(Protocol):
    def forward(self, host: SshHost, port: int) -> int:
        """Forward `127.0.0.1:port` here to the same port on the host until stopped."""
        ...
