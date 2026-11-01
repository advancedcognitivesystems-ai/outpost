"""Docker Compose on the box's inner engine, with a generated override for routes and restarts.

The override lives outside the worktree, so `git status` stays clean.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from typing import Any

import yaml

from outpost.domain.errors import InvalidValue
from outpost.domain.names import WorktreeName
from outpost.domain.resources import BoxLayout
from outpost.domain.routes import Route, stack_project, worktree_of_stack
from outpost.ports.proxy import RouterConvention
from outpost.ports.shell import Shell
from outpost.ports.stacks import StackDefinition

COMPOSE = ("docker", "compose")


class ComposeStacks:
    def __init__(self, box: Shell, router: RouterConvention, layout: BoxLayout) -> None:
        self._box = box
        self._router = router
        self._layout = layout

    def up(self, stack: StackDefinition) -> None:
        files = _file_arguments(stack.compose_files)
        services = self._box.run(
            [*COMPOSE, *files, "config", "--services"], cwd=stack.directory
        ).check()
        override = compose_override(services.stdout.split(), stack.routes, self._router)
        path = self._layout.stack_overrides_dir / f"{stack.worktree}.yaml"
        self._box.write_file(path, yaml.safe_dump(override, sort_keys=False))
        project = stack_project(stack.worktree)
        self._box.run(
            [*COMPOSE, "--project-name", project, *files, "--file", str(path),
             "up", "--detach", "--remove-orphans"],
            cwd=stack.directory,
        ).check()  # fmt: skip

    def down(self, worktree: WorktreeName) -> None:
        self._box.run([*COMPOSE, "--project-name", stack_project(worktree), "down"]).check()

    def running(self) -> tuple[WorktreeName, ...]:
        result = self._box.run([*COMPOSE, "ls", "--format", "json"]).check()
        entries = json.loads(result.stdout or "[]")
        worktrees = (
            worktree_of_stack(entry["Name"])
            for entry in entries
            if "running" in entry.get("Status", "")
        )
        return tuple(worktree for worktree in worktrees if worktree is not None)

    def follow_logs(self, worktree: WorktreeName, service: str | None) -> int:
        services = [service] if service else []
        project = stack_project(worktree)
        return self._box.run_interactive(
            [*COMPOSE, "--project-name", project, "logs", "--follow", *services]
        )


def compose_override(
    services: Sequence[str], routes: Iterable[Route], router: RouterConvention
) -> dict[str, Any]:
    """Every service restarts with the engine; exposed services also join the router's network."""
    labels: dict[str, dict[str, str]] = {}
    for route in routes:
        labels.setdefault(str(route.service), {}).update(router.labels(route))
    unknown = sorted(set(labels) - set(services))
    if unknown:
        raise InvalidValue(
            f"stacks.expose names services the compose files lack: {', '.join(unknown)}"
        )
    entries: dict[str, Any] = {}
    for name in services:
        entry: dict[str, Any] = {"restart": "unless-stopped"}
        if name in labels:
            entry["labels"] = labels[name]
            entry["networks"] = ["default", router.network]
        entries[name] = entry
    return {
        "services": entries,
        "networks": {router.network: {"external": True, "name": router.network}},
    }


def _file_arguments(files: Iterable[str]) -> list[str]:
    return [argument for path in files for argument in ("--file", path)]
