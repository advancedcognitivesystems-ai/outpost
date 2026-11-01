"""What every shell shares: working directories, files and staging, built on `run`."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from outpost.ports.shell import CommandResult

STAGING_DIR = PurePosixPath("/tmp")
_IN_DIRECTORY = 'cd "$1" && shift && exec "$@"'
_WRITE_FILE = 'set -e; mkdir -p "$(dirname "$1")"; umask 077; cat > "$1"; chmod "$2" "$1"'


class ShellBase(ABC):
    """Subclasses only say how to execute a command; the rest is portable POSIX."""

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    def client_commands(self) -> tuple[str, ...]:
        return ()

    @abstractmethod
    def _execute(self, argv: Sequence[str], stdin: str | None) -> CommandResult: ...

    @abstractmethod
    def _attach(self, argv: Sequence[str]) -> int: ...

    @abstractmethod
    def upload(self, source: Path, target: PurePosixPath) -> None: ...

    def run(
        self,
        argv: Sequence[str],
        *,
        stdin: str | None = None,
        cwd: PurePosixPath | None = None,
    ) -> CommandResult:
        return self._execute(self._in_directory(argv, cwd), stdin)

    def run_interactive(self, argv: Sequence[str], *, cwd: PurePosixPath | None = None) -> int:
        return self._attach(self._in_directory(argv, cwd))

    def ensure_directory(self, path: PurePosixPath) -> None:
        self.run(["mkdir", "-p", str(path)]).check()

    def write_file(self, path: PurePosixPath, content: str, *, mode: int = 0o644) -> None:
        self.run(["sh", "-c", _WRITE_FILE, "sh", str(path), f"{mode:o}"], stdin=content).check()

    def read_file(self, path: PurePosixPath) -> str | None:
        if not self.run(["test", "-f", str(path)]).ok:
            return None
        return self.run(["cat", str(path)]).check().stdout

    def remove_file(self, path: PurePosixPath) -> None:
        self.run(["rm", "-f", str(path)]).check()

    @contextmanager
    def staged(self, source: Path) -> Iterator[PurePosixPath]:
        target = STAGING_DIR / f"outpost-{uuid.uuid4().hex}-{source.name}"
        self.upload(source, target)
        try:
            yield target
        finally:
            self.remove_file(target)

    @staticmethod
    def _in_directory(argv: Sequence[str], cwd: PurePosixPath | None) -> list[str]:
        if cwd is None:
            return list(argv)
        return ["sh", "-c", _IN_DIRECTORY, "sh", str(cwd), *argv]
