"""Running commands and moving files on one machine: the client, the host or the box."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from outpost.domain.errors import CommandFailed

COMMAND_NOT_FOUND = 127


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def missing_command(self) -> bool:
        """The program itself is not installed where the command ran."""
        return self.code == COMMAND_NOT_FOUND

    def check(self) -> CommandResult:
        """Return itself when the command succeeded, raise `CommandFailed` otherwise."""
        if not self.ok:
            raise CommandFailed(self.argv, self.code, self.stderr)
        return self


class ClientNeeds(Protocol):
    @property
    def client_commands(self) -> tuple[str, ...]:
        """Programs this adapter runs on the client, so `doctor` can check them first."""
        ...


class Shell(ClientNeeds, Protocol):
    @property
    def description(self) -> str:
        """Where commands run, for messages: `local`, `ssh dev@vm`, `ssh dev@vm > box`."""
        ...

    def run(
        self,
        argv: Sequence[str],
        *,
        stdin: str | None = None,
        cwd: PurePosixPath | None = None,
    ) -> CommandResult:
        """Run a command to completion and capture its output. Never raises on a non-zero exit."""
        ...

    def run_interactive(self, argv: Sequence[str], *, cwd: PurePosixPath | None = None) -> int:
        """Run a command attached to the person's terminal; returns its exit code."""
        ...

    def ensure_directory(self, path: PurePosixPath) -> None:
        """Create a directory and its parents when missing."""
        ...

    def write_file(self, path: PurePosixPath, content: str, *, mode: int = 0o644) -> None:
        """Create or replace a file, creating parent directories; never readable by others first."""
        ...

    def read_file(self, path: PurePosixPath) -> str | None:
        """Content of a file, or None when it does not exist."""
        ...

    def remove_file(self, path: PurePosixPath) -> None:
        """Delete a file; nothing happens when it does not exist."""
        ...

    def upload(self, source: Path, target: PurePosixPath) -> None:
        """Copy a file from the client to this machine."""
        ...

    def staged(self, source: Path) -> AbstractContextManager[PurePosixPath]:
        """Upload a client file to a temporary path, and remove it when the block ends."""
        ...
