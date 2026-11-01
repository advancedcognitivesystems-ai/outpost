"""Names Outpost accepts. Each value is checked once, when it is built."""

from __future__ import annotations

import re
from dataclasses import dataclass

from outpost.domain.errors import InvalidValue

_ENVIRONMENT = re.compile(r"[a-z](?:[a-z0-9-]{0,28}[a-z0-9])?")
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_IMAGE = re.compile(r"[a-z0-9][A-Za-z0-9._/:@-]*")
MAX_DNS_NAME = 253
MAX_PORT = 65535


@dataclass(frozen=True, slots=True)
class EnvironmentName:
    """Names the container `outpost-<name>` and its volumes `outpost-<name>-*`."""

    value: str

    def __post_init__(self) -> None:
        if not _ENVIRONMENT.fullmatch(self.value):
            raise InvalidValue(
                f"{self.value!r} is not a valid name: use 1 to 30 lowercase letters, digits "
                "and '-', starting with a letter"
            )

    @property
    def container(self) -> str:
        return f"outpost-{self.value}"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class DnsName:
    """Lowercase DNS labels separated by dots, such as `api.feat-a` or `dev.localhost`."""

    value: str

    def __post_init__(self) -> None:
        labels = self.value.split(".")
        if len(self.value) > MAX_DNS_NAME or not all(_LABEL.fullmatch(label) for label in labels):
            raise InvalidValue(
                f"{self.value!r} is not a DNS name: use lowercase labels of letters, digits "
                "and '-', separated by dots"
            )

    def under(self, parent: DnsName) -> DnsName:
        return DnsName(f"{self.value}.{parent.value}")

    def relative_to(self, parent: DnsName) -> DnsName | None:
        """The part of this name before `parent`, or None when it is not under `parent`."""
        suffix = f".{parent.value}"
        if not self.value.endswith(suffix) or len(self.value) == len(suffix):
            return None
        return DnsName(self.value[: -len(suffix)])

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ImageRef:
    """A container image reference, such as `outpost/base:3f2a9c1e5b7d`."""

    value: str

    def __post_init__(self) -> None:
        if not _IMAGE.fullmatch(self.value):
            raise InvalidValue(f"{self.value!r} is not an image reference")

    def __str__(self) -> str:
        return self.value


def port_number(value: int) -> int:
    if not 1 <= value <= MAX_PORT:
        raise InvalidValue(f"{value} is not a port: use 1 to {MAX_PORT}")
    return value
