"""Stacks: one compose project per worktree, one route per exposed service."""

from __future__ import annotations

from outpost.application.worktrees import Worktrees
from outpost.domain.config import ResolvedConfig
from outpost.domain.names import ServiceName, WorktreeName
from outpost.domain.routes import Route, plan_routes
from outpost.ports.stacks import StackDefinition, StackRunner


class Stacks:
    def __init__(self, config: ResolvedConfig, runner: StackRunner, worktrees: Worktrees) -> None:
        self._config = config
        self._runner = runner
        self._worktrees = worktrees

    def routes(self, name: WorktreeName) -> tuple[Route, ...]:
        return plan_routes(name, self._config.stacks.expose, self._config.target.edge.domain)

    def urls(self, name: WorktreeName) -> tuple[str, ...]:
        edge = self._config.target.edge
        return tuple(
            route.url(secure=edge.secure, port=edge.public_port) for route in self.routes(name)
        )

    def up(self, name: WorktreeName) -> tuple[str, ...]:
        worktree = self._worktrees.get(name)
        self._runner.up(
            StackDefinition(
                worktree=name,
                directory=worktree.path,
                compose_files=self._config.stacks.compose_files,
                routes=self.routes(name),
            )
        )
        return self.urls(name)

    def down(self, name: WorktreeName) -> None:
        self._runner.down(name)

    def running(self) -> tuple[WorktreeName, ...]:
        return self._runner.running()

    def follow_logs(self, name: WorktreeName, service: ServiceName | None) -> int:
        return self._runner.follow_logs(name, service)
