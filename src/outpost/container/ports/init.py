"""Init scripts, persisted paths, and the boot record kept in the state volume."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Protocol

from outpost.domain.init import Script
from outpost.domain.status import BootRecord


class Scripts(Protocol):
    def listing(self) -> tuple[Script, ...]:
        """The image's scripts, then yours, each set in name order."""
        ...

    def run(self, script: Script) -> int: ...


class Ownership(Protocol):
    def claim_if_empty(self, path: PurePosixPath) -> None:
        """Give an empty, new volume to the dev user, so it can write there."""
        ...


class BootStore(Protocol):
    def current_boot(self) -> str:
        """Names this start of the container: it changes at every start."""
        ...

    def read(self) -> BootRecord: ...

    def write(self, record: BootRecord) -> None: ...
