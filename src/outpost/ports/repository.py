"""The project's repository and its worktrees in the box."""

from __future__ import annotations

from typing import Protocol

from outpost.domain.config import GitIdentity
from outpost.domain.names import WorktreeName
from outpost.domain.worktrees import Worktree


class Repository(Protocol):
    def is_cloned(self) -> bool: ...

    def clone(self) -> None: ...

    def add_worktree(self, name: WorktreeName, branch: str, start: str | None) -> Worktree:
        """Check out `branch` in a new worktree: the existing local branch, else the remote one,
        else a new branch from `start` (default: the project's default branch on the remote)."""
        ...

    def remove_worktree(self, name: WorktreeName, *, force: bool) -> None: ...

    def worktrees(self) -> tuple[Worktree, ...]: ...

    def set_identity(self, identity: GitIdentity) -> None: ...
