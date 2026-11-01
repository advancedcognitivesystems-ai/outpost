"""Logins: where they are read on your machine, and how a tool checks and takes one inside."""

from __future__ import annotations

from typing import Protocol

from outpost.domain.credentials import LoginState, Tool
from outpost.domain.secrets import Secret


class LoginSource(Protocol):
    """A login on your machine, such as the macOS Keychain entry of Claude Code."""

    @property
    def description(self) -> str: ...

    def read(self) -> Secret | None: ...


class ToolLogin(Protocol):
    """A tool in the container that holds a login: Claude Code or the GitHub CLI."""

    @property
    def tool(self) -> Tool: ...

    def state(self) -> LoginState: ...

    def install(self, secret: Secret) -> None: ...

    def login(self) -> None:
        """Run the tool's own interactive login in the container."""
        ...

    def finish(self) -> None:
        """Anything the tool needs once it is logged in, such as `gh auth setup-git`."""
        ...
