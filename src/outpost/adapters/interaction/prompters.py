"""Asking the person in the terminal, or, with `--yes`, taking the recommended answer every time."""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from typing import TextIO


class _Messages:
    def __init__(self, output: TextIO) -> None:
        self._output = output

    def info(self, message: str) -> None:
        print(message, file=self._output)

    def warn(self, message: str) -> None:
        print(f"warning: {message}", file=self._output)


class TerminalPrompter(_Messages):
    def __init__(self, output: TextIO = sys.stderr, ask: Callable[[str], str] = input) -> None:
        super().__init__(output)
        self._ask = ask

    def confirm(self, question: str, *, default: bool) -> bool:
        hint = "[Y/n]" if default else "[y/N]"
        while True:
            answer = self._ask(f"{question} {hint} ").strip().lower()
            if not answer:
                return default
            if answer in {"y", "yes"}:
                return True
            if answer in {"n", "no"}:
                return False

    def choose(self, question: str, options: Sequence[str]) -> int:
        self.info(question)
        for number, option in enumerate(options, start=1):
            self.info(f"  {number}. {option}")
        while True:
            answer = self._ask(f"Choice [1-{len(options)}, default 1]: ").strip()
            if not answer:
                return 0
            if answer.isdigit() and 1 <= int(answer) <= len(options):
                return int(answer) - 1


class UnattendedPrompter(_Messages):
    """`--yes`: accepts every offered fix and takes the first (recommended) option."""

    def __init__(self, output: TextIO = sys.stderr) -> None:
        super().__init__(output)

    def confirm(self, question: str, *, default: bool) -> bool:
        self.info(f"{question} yes (--yes)")
        return True

    def choose(self, question: str, options: Sequence[str]) -> int:
        self.info(f"{question} {options[0]} (--yes)")
        return 0
