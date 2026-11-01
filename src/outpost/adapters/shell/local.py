"""Commands on the machine running Outpost."""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from outpost.adapters.shell.base import ShellBase
from outpost.adapters.shell.process import run_attached, run_captured
from outpost.ports.shell import CommandResult


class LocalShell(ShellBase):
    @property
    def description(self) -> str:
        return "local"

    def _execute(self, argv: Sequence[str], stdin: str | None) -> CommandResult:
        return run_captured(argv, stdin=stdin)

    def _attach(self, argv: Sequence[str]) -> int:
        return run_attached(argv)

    def upload(self, source: Path, target: PurePosixPath) -> None:
        destination = Path(target)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
