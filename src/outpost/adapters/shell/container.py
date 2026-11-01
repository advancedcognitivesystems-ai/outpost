"""Commands inside a container, through the engine of the machine that runs it."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from outpost.adapters.shell.base import ShellBase
from outpost.ports.engine import ContainerEngine
from outpost.ports.shell import CommandResult, Shell

_STAGING = PurePosixPath("/tmp")


class ContainerShell(ShellBase):
    def __init__(self, engine: ContainerEngine, host: Shell, container: str, user: str) -> None:
        self._engine = engine
        self._host = host
        self._container = container
        self._user = user

    @property
    def description(self) -> str:
        return f"{self._host.description} > {self._container}"

    def _execute(self, argv: Sequence[str], stdin: str | None) -> CommandResult:
        return self._engine.exec(self._container, argv, user=self._user, stdin=stdin)

    def _attach(self, argv: Sequence[str]) -> int:
        return self._engine.exec_interactive(self._container, argv, user=self._user)

    def upload(self, source: Path, target: PurePosixPath) -> None:
        staged = _STAGING / f"outpost-upload-{uuid.uuid4().hex}"
        self._host.upload(source, staged)
        try:
            self.ensure_directory(target.parent)
            self._engine.copy_into(self._container, staged, target)
        finally:
            self._host.run(["rm", "-f", str(staged)])
