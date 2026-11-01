"""Your machine: the terminal, program versions, files, the SSH tunnel."""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from pathlib import Path, PurePath
from typing import TextIO

from outpost.domain.host import SshHost
from outpost.infra.process import Runner


class TerminalConsole:
    def __init__(
        self,
        *,
        assume_yes: bool,
        interactive: bool,
        output: TextIO = sys.stderr,
        ask: Callable[[str], str] = input,
    ) -> None:
        self._assume_yes = assume_yes
        self._interactive = interactive
        self._output = output
        self._ask = ask

    @property
    def interactive(self) -> bool:
        return self._interactive

    def info(self, message: str) -> None:
        print(message, file=self._output)

    def warn(self, message: str) -> None:
        print(f"warning: {message}", file=self._output)

    def confirm(self, question: str, *, default: bool) -> bool:
        if self._assume_yes:
            self.info(f"{question} yes (--yes)")
            return True
        if not self._interactive:
            return default
        hint = "[Y/n]" if default else "[y/N]"
        while True:
            answer = self._ask(f"{question} {hint} ").strip().lower()
            if not answer:
                return default
            if answer in {"y", "yes"}:
                return True
            if answer in {"n", "no"}:
                return False

    def ask(self, question: str) -> str:
        return self._ask(f"{question} ") if self._interactive else ""


class ProgramVersions:
    def __init__(self, runner: Runner) -> None:
        self._runner = runner

    def version(self, argv: Sequence[str]) -> str | None:
        result = self._runner.run(argv)
        if not result.ok:
            return None
        lines = (result.stdout + "\n" + result.stderr).splitlines()
        return next((line.strip() for line in lines if line.strip()), "")


class LocalFiles:
    def is_dir(self, path: PurePath) -> bool:
        return Path(path).expanduser().is_dir()

    def exists(self, path: PurePath) -> bool:
        return Path(path).expanduser().exists()


class SshTunnel:
    def __init__(self, runner: Runner) -> None:
        self._runner = runner

    def forward(self, host: SshHost, port: int) -> int:
        forward = f"127.0.0.1:{port}:127.0.0.1:{port}"
        argv = ["ssh", "-N", "-o", "ExitOnForwardFailure=yes", "-L", forward]
        return self._runner.attached([*argv, *host.ssh_arguments()])
