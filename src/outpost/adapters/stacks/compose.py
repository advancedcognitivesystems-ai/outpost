"""Docker Compose on the box's inner engine.

`up` adds a small override (router labels and network for exposed services) and writes a starter
script with the exact `up` command; the box runs every starter when it starts, so stacks come
back after a reboot while each service keeps its own restart policy. Both files live outside the
worktree, so `git status` stays clean.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Iterable, Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any

import yaml

from outpost.domain.errors import InvalidValue
from outpost.domain.names import ServiceName, WorktreeName
from outpost.domain.resources import BoxLayout
from outpost.domain.routes import Route, stack_project, worktree_of_stack
from outpost.ports.proxy import RouterConvention
from outpost.ports.shell import Shell
from outpost.ports.stacks import StackDefinition

COMPOSE = ("docker", "compose")
STARTER_SUFFIX = ".up.sh"
BOOT_LOG = PurePosixPath("/var/log/outpost-stacks.log")


class ComposeStacks:
    def __init__(self, box: Shell, router: RouterConvention, layout: BoxLayout) -> None:
        self._box = box
        self._router = router
        self._layout = layout

    def _override(self, worktree: WorktreeName) -> PurePosixPath:
        return self._layout.stacks_dir / f"{worktree}.override.yaml"

    def _starter(self, worktree: WorktreeName) -> PurePosixPath:
        return self._layout.stacks_dir / f"{worktree}{STARTER_SUFFIX}"

    def up(self, stack: StackDefinition) -> None:
        compose = [*COMPOSE, "--project-name", stack_project(stack.worktree)]
        compose += _file_arguments(stack.compose_files)
        resolved = self._box.run([*compose, "config", "--format", "json"], cwd=stack.directory)
        override = compose_override(json.loads(resolved.check().stdout), stack.routes, self._router)
        override_path = self._override(stack.worktree)
        self._box.write_file(override_path, yaml.safe_dump(override, sort_keys=False))
        command = [*compose, "--file", str(override_path), "up", "--detach", "--remove-orphans"]
        starter = starter_script(stack.directory, command)
        self._box.write_file(self._starter(stack.worktree), starter, mode=0o755)
        self._box.run(command, cwd=stack.directory).check()

    def down(self, worktree: WorktreeName) -> None:
        self._box.run([*COMPOSE, "--project-name", stack_project(worktree), "down"]).check()
        self._box.remove_file(self._starter(worktree))

    def running(self) -> tuple[WorktreeName, ...]:
        result = self._box.run([*COMPOSE, "ls", "--format", "json"]).check()
        entries = json.loads(result.stdout or "[]")
        worktrees = (
            worktree_of_stack(entry["Name"])
            for entry in entries
            if "running" in entry.get("Status", "")
        )
        return tuple(worktree for worktree in worktrees if worktree is not None)

    def follow_logs(self, worktree: WorktreeName, service: ServiceName | None) -> int:
        services = [str(service)] if service else []
        project = stack_project(worktree)
        return self._box.run_interactive(
            [*COMPOSE, "--project-name", project, "logs", "--follow", *services]
        )

    def boot_script(self) -> str:
        pattern = f"{shlex.quote(str(self._layout.stacks_dir))}/*{STARTER_SUFFIX}"
        return (
            f'for starter in {pattern}; do [ -f "$starter" ] '
            f'&& sh "$starter" >>{BOOT_LOG} 2>&1; done'
        )


def compose_override(
    resolved: Mapping[str, Any], routes: Iterable[Route], router: RouterConvention
) -> dict[str, Any]:
    """Exposed services get router labels and join the router's network, keeping their own."""
    services: Mapping[str, Any] = resolved.get("services", {})
    labels: dict[str, dict[str, str]] = {}
    for route in routes:
        labels.setdefault(str(route.service), {}).update(router.labels(route))
    unknown = sorted(set(labels) - set(services))
    if unknown:
        raise InvalidValue(
            f"stacks.expose names services the compose files lack: {', '.join(unknown)}"
        )
    entries: dict[str, Any] = {}
    for name, service_labels in labels.items():
        declared = services[name].get("networks") or {"default": None}
        entries[name] = {
            "labels": service_labels,
            "networks": sorted({*declared, router.network}),
        }
    return {
        "services": entries,
        "networks": {router.network: {"external": True, "name": router.network}},
    }


def starter_script(directory: PurePosixPath, command: Sequence[str]) -> str:
    return (
        "#!/bin/sh\n"
        "# Written by `outpost stack up`, run when the box starts, removed by `stack down`.\n"
        f"cd {shlex.quote(str(directory))} && exec {shlex.join(command)}\n"
    )


def _file_arguments(files: Iterable[str]) -> list[str]:
    return [argument for path in files for argument in ("--file", path)]
