"""Talking to the person, and reading the templates Outpost ships."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol


class Prompter(Protocol):
    def info(self, message: str) -> None: ...

    def warn(self, message: str) -> None: ...

    def confirm(self, question: str, *, default: bool) -> bool: ...

    def choose(self, question: str, options: Sequence[str]) -> int:
        """Index of the chosen option; the first option is the recommended one."""
        ...


class TemplateRenderer(Protocol):
    def render(self, name: str, values: Mapping[str, str]) -> str:
        """Render a shipped template; every placeholder must get a value and every value a use."""
        ...
