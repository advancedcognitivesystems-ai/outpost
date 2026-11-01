"""`outpost shell`: an interactive shell in the box, in a worktree or the project directory."""

from __future__ import annotations

from outpost.application.worktrees import Worktrees
from outpost.domain.names import WorktreeName
from outpost.domain.resources import BoxLayout
from outpost.ports.shell import Shell

LOGIN_SHELL = ("bash", "-l")


class BoxSession:
    def __init__(self, box: Shell, layout: BoxLayout, worktrees: Worktrees) -> None:
        self._box = box
        self._layout = layout
        self._worktrees = worktrees

    def open(self, name: WorktreeName | None) -> int:
        directory = self._worktrees.get(name).path if name else self._layout.project_dir
        return self._box.run_interactive(LOGIN_SHELL, cwd=directory)
