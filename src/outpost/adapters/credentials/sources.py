"""Where a credential is read on the client: a file, a command's output, an environment variable."""

from __future__ import annotations

import shlex
from collections.abc import Mapping, Sequence
from pathlib import Path

from outpost.domain.secrets import Secret
from outpost.ports.shell import Shell


class FileSecret:
    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def description(self) -> str:
        return f"file {self._path}"

    @property
    def client_commands(self) -> tuple[str, ...]:
        return ()

    def read(self) -> Secret | None:
        try:
            content = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        return Secret(content) if content.strip() else None


class CommandSecret:
    """The trimmed standard output of a command; a failing command means no secret."""

    def __init__(self, shell: Shell, argv: Sequence[str]) -> None:
        self._shell = shell
        self._argv = tuple(argv)

    @property
    def description(self) -> str:
        return f"command `{shlex.join(self._argv)}`"

    @property
    def client_commands(self) -> tuple[str, ...]:
        return self._argv[:1]

    def read(self) -> Secret | None:
        result = self._shell.run(self._argv)
        value = result.stdout.strip()
        return Secret(value) if result.ok and value else None


class EnvSecret:
    def __init__(self, name: str, environ: Mapping[str, str]) -> None:
        self._name = name
        self._environ = environ

    @property
    def description(self) -> str:
        return f"environment variable {self._name}"

    @property
    def client_commands(self) -> tuple[str, ...]:
        return ()

    def read(self) -> Secret | None:
        value = self._environ.get(self._name, "")
        return Secret(value) if value.strip() else None
