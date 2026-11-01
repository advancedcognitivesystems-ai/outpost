"""Errors Outpost raises on purpose. Only the CLI turns them into messages and exit codes."""

from __future__ import annotations

from collections.abc import Sequence


class OutpostError(Exception):
    """Base class of every deliberate Outpost error."""


class ConfigError(OutpostError):
    """The configuration is invalid; `path` names the offending key."""

    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path}: {message}" if path else message)
        self.path = path
        self.message = message


class InvalidValue(OutpostError):
    """A value breaks a domain rule: a name, a port, a reference."""


class CommandFailed(OutpostError):
    """A command on the client, the host or the box exited with a non-zero code."""

    def __init__(self, argv: Sequence[str], code: int, stderr: str) -> None:
        detail = stderr.strip().splitlines()[-1] if stderr.strip() else "no error output"
        super().__init__(f"`{' '.join(argv)}` exited with {code}: {detail}")
        self.argv = tuple(argv)
        self.code = code
        self.stderr = stderr


class Declined(OutpostError):
    """The person declined a step that is required to continue."""


class Unavailable(OutpostError):
    """Something Outpost needs is missing: a tool, a secret, an image, a host."""


class NotImplementedYet(OutpostError):
    """A command that is designed but not built yet."""
