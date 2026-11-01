"""The logins Outpost carries into the container."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Tool(StrEnum):
    CLAUDE = "claude"
    GITHUB = "gh"


@dataclass(frozen=True)
class LoginState:
    tool: Tool
    valid: bool
    detail: str = ""
    installed: bool = True
    """False when the tool is missing from the container: nothing to copy into, no login."""
