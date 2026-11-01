"""Validated names and references. Each value is checked once, when it is built."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar

from outpost.domain.errors import InvalidValue

DNS_LABEL_MAX = 63
_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
_HOSTNAME = re.compile(
    r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$"
)
_COMPOSE_SERVICE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
_USER = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
_VARIABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SECRET_LIKE = re.compile(r"TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY|CREDENTIAL", re.I)


def _require_label(value: str, what: str, max_length: int) -> None:
    if len(value) > max_length or not _LABEL.match(value):
        raise InvalidValue(
            f"{what} {value!r} must use lowercase letters, digits and '-', "
            f"start and end with a letter or digit, and stay within {max_length} characters"
        )


@dataclass(frozen=True)
class ProjectName:
    """Prefix of every host object, `outpost-<project>-<role>`."""

    value: str
    MAX_LENGTH: ClassVar[int] = 30

    def __post_init__(self) -> None:
        _require_label(self.value, "project name", self.MAX_LENGTH)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class WorktreeName:
    """A worktree, its stack and the second half of its route names."""

    value: str
    MAX_LENGTH: ClassVar[int] = 40

    def __post_init__(self) -> None:
        _require_label(self.value, "worktree name", self.MAX_LENGTH)
        if "--" in self.value:
            raise InvalidValue(
                f"worktree name {self.value!r} cannot contain '--', the route separator"
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Subdomain:
    """First half of a route name, before the `--` separator."""

    value: str

    def __post_init__(self) -> None:
        _require_label(self.value, "subdomain", DNS_LABEL_MAX)
        if "--" in self.value:
            raise InvalidValue(f"subdomain {self.value!r} cannot contain '--', the route separator")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ServiceName:
    """A service as named in the stack's compose files."""

    value: str

    def __post_init__(self) -> None:
        if not _COMPOSE_SERVICE.match(self.value):
            raise InvalidValue(f"service name {self.value!r} is not a valid compose service name")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Domain:
    """The domain every route lives under, such as `dev.acme.example`."""

    value: str

    def __post_init__(self) -> None:
        if not _HOSTNAME.match(self.value):
            raise InvalidValue(f"domain {self.value!r} must be a lowercase DNS name with a dot")

    @property
    def is_loopback(self) -> bool:
        """Names under `localhost` reach this machine in browsers without any DNS record."""
        return self.value.endswith(".localhost")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ImageRef:
    """A container image reference, such as `acmecr.azurecr.io/dev/dotnet:1`."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or any(char.isspace() for char in self.value):
            raise InvalidValue(f"image reference {self.value!r} must be non-empty without spaces")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Port:
    """A TCP port number."""

    value: int

    def __post_init__(self) -> None:
        if not 1 <= self.value <= 65535:
            raise InvalidValue(f"port {self.value} must be between 1 and 65535")

    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True)
class UserName:
    """A Unix user, safe to place in a Dockerfile or a sudoers rule."""

    value: str

    def __post_init__(self) -> None:
        if not _USER.match(self.value):
            raise InvalidValue(f"user name {self.value!r} must be a lowercase Unix user name")

    def __str__(self) -> str:
        return self.value


def variable_name(name: str) -> str:
    """An environment variable name; returns it unchanged."""
    if not _VARIABLE.match(name):
        raise InvalidValue(f"{name!r} is not a valid environment variable name")
    return name


def plain_setting_name(name: str) -> str:
    """A variable for plain settings; names that look like secrets are refused."""
    variable_name(name)
    if _SECRET_LIKE.search(name):
        raise InvalidValue(
            f"{name!r} looks like a secret; secrets never go in outpost.yaml (see credentials)"
        )
    return name
