"""Running one worktree's stack on the box's inner engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol

from outpost.domain.names import WorktreeName
from outpost.domain.routes import Route


@dataclass(frozen=True)
class StackDefinition:
    worktree: WorktreeName
    directory: PurePosixPath
    compose_files: tuple[str, ...]
    routes: tuple[Route, ...]


class StackRunner(Protocol):
    def up(self, stack: StackDefinition) -> None: ...

    def down(self, worktree: WorktreeName) -> None: ...

    def running(self) -> tuple[WorktreeName, ...]: ...

    def follow_logs(self, worktree: WorktreeName, service: str | None) -> int: ...
