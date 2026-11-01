"""Worktrees in the box, each one the home of an agent and of a stack."""

from __future__ import annotations

from dataclasses import dataclass

from outpost.domain.config import ResolvedConfig
from outpost.domain.errors import Unavailable
from outpost.domain.names import WorktreeName
from outpost.domain.worktrees import Worktree
from outpost.ports.repository import Repository
from outpost.ports.stacks import StackRunner


@dataclass(frozen=True)
class WorktreeStatus:
    worktree: Worktree
    stack_running: bool


class Worktrees:
    def __init__(self, config: ResolvedConfig, repository: Repository, runner: StackRunner) -> None:
        self._config = config
        self._repository = repository
        self._runner = runner

    def add(self, name: WorktreeName, *, branch: str | None, start: str | None) -> Worktree:
        if any(item.name == name for item in self._repository.worktrees()):
            raise Unavailable(f"worktree {name} already exists")
        start_point = start or f"origin/{self._config.project.default_branch}"
        return self._repository.add_worktree(name, branch or str(name), start_point)

    def remove(self, name: WorktreeName, *, force: bool) -> None:
        self.get(name)
        if name in self._runner.running():
            self._runner.down(name)
        self._repository.remove_worktree(name, force=force)

    def get(self, name: WorktreeName) -> Worktree:
        for item in self._repository.worktrees():
            if item.name == name:
                return item
        raise Unavailable(f"no worktree named {name}; see `outpost worktree ls`")

    def list(self) -> tuple[WorktreeStatus, ...]:
        running = set(self._runner.running())
        return tuple(
            WorktreeStatus(item, item.name in running) for item in self._repository.worktrees()
        )
