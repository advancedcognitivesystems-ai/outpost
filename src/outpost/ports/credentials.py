"""Reading credentials on the client, and installing them for a tool on a machine."""

from __future__ import annotations

from typing import Protocol

from outpost.domain.credentials import AuthState, Tool
from outpost.domain.secrets import Secret
from outpost.ports.shell import ClientNeeds


class SecretSource(ClientNeeds, Protocol):
    @property
    def description(self) -> str:
        """Where the secret is read from, for messages; never the secret itself."""
        ...

    def read(self) -> Secret | None:
        """The secret, or None when this source has nothing."""
        ...


class ToolAuth(Protocol):
    @property
    def tool(self) -> Tool: ...

    def state(self) -> AuthState: ...

    def install(self, secret: Secret) -> None:
        """Put a credential read elsewhere in place for the tool."""
        ...

    def login(self) -> None:
        """Run the tool's own interactive login."""
        ...

    def finish(self) -> None:
        """Setup that follows a valid login, such as wiring git to the tool."""
        ...
