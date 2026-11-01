"""Running a process on the client. Every shell ends up here."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence

from outpost.ports.shell import COMMAND_NOT_FOUND, CommandResult


def run_captured(argv: Sequence[str], *, stdin: str | None = None) -> CommandResult:
    """Run without the person's terminal: stdin is the given text, or nothing at all."""
    try:
        if stdin is None:
            completed = subprocess.run(
                list(argv), stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False
            )
        else:
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
