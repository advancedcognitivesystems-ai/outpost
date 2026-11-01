"""The outcome of a command, wherever it ran: your machine, the host, or the container."""

from __future__ import annotations

from dataclasses import dataclass

from outpost.domain.errors import CommandFailed

COMMAND_NOT_FOUND = 127


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    code: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def missing_command(self) -> bool:
        return self.code == COMMAND_NOT_FOUND

    def check(self) -> CommandResult:
        """Return itself when the command succeeded, raise `CommandFailed` otherwise."""
        if not self.ok:
            raise CommandFailed(self.argv, self.code, self.stderr)
        return self
