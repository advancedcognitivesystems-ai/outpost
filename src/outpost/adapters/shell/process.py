"""Running a process on the client. Every shell ends up here."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence

from outpost.ports.shell import CommandResult

COMMAND_NOT_FOUND = 127


def run_captured(argv: Sequence[str], *, stdin: str | None = None) -> CommandResult:
    try:
        completed = subprocess.run(
            list(argv), input=stdin, capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        return CommandResult(tuple(argv), COMMAND_NOT_FOUND, "", f"{argv[0]}: command not found")
    return CommandResult(tuple(argv), completed.returncode, completed.stdout, completed.stderr)


def run_attached(argv: Sequence[str]) -> int:
    try:
        return subprocess.run(list(argv), check=False).returncode
    except FileNotFoundError:
        return COMMAND_NOT_FOUND
