"""Errors Outpost raises on purpose. Only each side's `cli.main` turns them into exit codes."""

from __future__ import annotations

from collections.abc import Sequence


def last_line(text: str, default: str = "") -> str:
    """The last non-empty line of a program's error output: usually the one that explains."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else default


class OutpostError(Exception):
    """Base class of every deliberate Outpost error."""


class ConfigError(OutpostError):
    """The configuration is invalid; `path` names the key at fault."""

    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path}: {message}" if path else message)
        self.path = path
        self.message = message


class InvalidValue(OutpostError):
    """A value breaks a domain rule: a name, a port, a path."""


class CommandFailed(OutpostError):
    """A command on your machine, on the host or in the container exited with an error."""

    def __init__(self, argv: Sequence[str], code: int, stderr: str) -> None:
        detail = last_line(stderr, "no error output")
        super().__init__(f"`{' '.join(argv)}` exited with {code}: {detail}")
        self.argv = tuple(argv)
        self.code = code
        self.stderr = stderr


class Declined(OutpostError):
    """The person declined a step that is required to continue."""


class Unavailable(OutpostError):
    """Something Outpost needs is missing or unreachable: a tool, the host, the proxy, a file."""
