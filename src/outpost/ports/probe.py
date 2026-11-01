"""Facts about a machine, for `doctor`."""

from __future__ import annotations

from typing import Protocol


class MachineProbe(Protocol):
    def reachable(self) -> bool: ...

    def home(self) -> str: ...

    def has_command(self, name: str) -> bool: ...

    def free_disk_gb(self, path: str) -> float | None:
        """Free space on the filesystem holding `path` (or its closest existing parent)."""
        ...

    def resolve(self, hostname: str) -> tuple[str, ...]:
        """Addresses the hostname resolves to from this machine; empty when it does not resolve."""
        ...
