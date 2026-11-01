"""The inner Docker engine, as the route tool needs it."""

from __future__ import annotations

from typing import Protocol


class Engine(Protocol):
    def is_container(self, name: str) -> bool: ...

    def networks(self, container: str) -> tuple[str, ...]: ...

    def connect(self, network: str, container: str) -> None: ...
