"""Init scripts and the boot record kept in the state volume."""

from __future__ import annotations

from typing import Protocol

from outpost.domain.init import Script
from outpost.domain.status import BootRecord


class Scripts(Protocol):
    def listing(self) -> tuple[Script, ...]:
        """The image's scripts, then yours, each set in name order."""
        ...

    def run(self, script: Script) -> int: ...


class BootStore(Protocol):
    def read(self) -> BootRecord: ...

    def write(self, record: BootRecord) -> None: ...
