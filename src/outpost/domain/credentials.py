"""Credential vocabulary: which tools, which strategies, what state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Tool(StrEnum):
    CLAUDE = "claude"
    GITHUB = "github"


class Strategy(StrEnum):
    """How a missing credential is put in place in the box."""

    COPY = "copy"
    TOKEN = "token"
    LOGIN = "login"
    SKIP = "skip"


@dataclass(frozen=True)
class AuthState:
    tool: Tool
    valid: bool
    detail: str = ""
