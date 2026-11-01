"""A git worktree in the box."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from outpost.domain.names import WorktreeName


@dataclass(frozen=True)
class Worktree:
    name: WorktreeName
    branch: str
    path: PurePosixPath
