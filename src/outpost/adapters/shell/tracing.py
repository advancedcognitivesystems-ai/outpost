"""`--verbose`: prints every command before delegating to the real shell."""

from __future__ import annotations

import shlex
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from outpost.ports.shell import CommandResult, Shell


class TracingShell:
    def __init__(self, inner: Shell, emit: Callable[[str], None]) -> None:
        self._inner = inner
        self._emit = emit

    def _trace(self, what: str) -> None:
        self._emit(f"[{self._inner.description}] {what}")

    @property
    def description(self) -> str:
        return self._inner.description

    @property
    def client_commands(self) -> tuple[str, ...]:
        return self._inner.client_commands

    def run(
        self,
        argv: Sequence[str],
        *,
        stdin: str | None = None,
        cwd: PurePosixPath | None = None,
    ) -> CommandResult:
        self._trace(shlex.join(argv) + (" <stdin" if stdin is not None else ""))
        return self._inner.run(argv, stdin=stdin, cwd=cwd)

    def run_interactive(self, argv: Sequence[str], *, cwd: PurePosixPath | None = None) -> int:
        self._trace(shlex.join(argv))
        return self._inner.run_interactive(argv, cwd=cwd)

    def ensure_directory(self, path: PurePosixPath) -> None:
        self._trace(f"mkdir -p {path}")
        self._inner.ensure_directory(path)

    def write_file(self, path: PurePosixPath, content: str, *, mode: int = 0o644) -> None:
        self._trace(f"write {path} ({len(content)} bytes, mode {mode:o})")
        self._inner.write_file(path, content, mode=mode)

    def read_file(self, path: PurePosixPath) -> str | None:
        self._trace(f"read {path}")
        return self._inner.read_file(path)

    def remove_file(self, path: PurePosixPath) -> None:
        self._trace(f"rm -f {path}")
        self._inner.remove_file(path)

    def upload(self, source: Path, target: PurePosixPath) -> None:
        self._trace(f"upload {source} -> {target}")
        self._inner.upload(source, target)

    @contextmanager
    def staged(self, source: Path) -> Iterator[PurePosixPath]:
        with self._inner.staged(source) as target:
            self._trace(f"staged {source} at {target}")
            yield target
