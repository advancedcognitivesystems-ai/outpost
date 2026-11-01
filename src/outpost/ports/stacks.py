"""Running one worktree's stack on the box's inner engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol

from outpost.domain.names import ServiceName, WorktreeName
from outpost.domain.routes import Route


@dataclass(frozen=True)
class StackDefinition:
    worktree: WorktreeName
    directory: PurePosixPath
    compose_files: tuple[str, ...]
    routes: tuple[Route, ...]


class StackRunner(Protocol):
    def up(self, stack: StackDefinition) -> None:
        """Start the stack and remember it, so it starts again when the box starts."""
        ...

    def down(self, worktree: WorktreeName) -> None:
        """Stop the stack and forget it."""
        ...

    def running(self) -> tuple[WorktreeName, ...]: ...

    def follow_logs(self, worktree: WorktreeName, service: ServiceName | None) -> int: ...

    def boot_script(self) -> str:
        """Shell lines the box runs at start to bring back every remembered stack."""
        ...
