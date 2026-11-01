"""Routes: a name under the domain, served over HTTPS by the proxy and sent to one upstream."""

from __future__ import annotations

import re
from dataclasses import dataclass
from fnmatch import fnmatchcase

from outpost.domain.errors import InvalidValue
from outpost.domain.names import DnsName, port_number

DEVCONTAINER = "devcontainer"
"""The upstream host that stands for the dev container itself, as seen from the proxy."""

HTTPS_PORT = 443
_UPSTREAM_HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


@dataclass(frozen=True, slots=True)
class Upstream:
    """Where the proxy sends a route: a container, a network alias, or `devcontainer`."""

    host: str
    port: int

    def __post_init__(self) -> None:
        if not _UPSTREAM_HOST.fullmatch(self.host):
            raise InvalidValue(f"{self.host!r} is not a container name or network alias")
        port_number(self.port)

    @classmethod
    def parse(cls, text: str) -> Upstream:
        host, separator, port = text.rpartition(":")
        if not separator or not port.isdigit():
            raise InvalidValue(
                f"{text!r} is not an upstream: use container:port or devcontainer:port"
            )
        return cls(host, int(port))

    @property
    def is_devcontainer(self) -> bool:
        return self.host == DEVCONTAINER

    def __str__(self) -> str:
        return f"{self.host}:{self.port}"


@dataclass(frozen=True, slots=True)
class Route:
    name: DnsName
    upstream: Upstream


@dataclass(frozen=True, slots=True)
class Site:
    """Where routes are served: the domain their names live under, and the port browsers use."""

    domain: DnsName
    port: int

    def __post_init__(self) -> None:
        port_number(self.port)

    def hostname(self, name: DnsName) -> DnsName:
        return name.under(self.domain)

    def url(self, name: DnsName) -> str:
        return f"https://{self.hostname(name)}{self._port_suffix}"

    def url_pattern(self) -> str:
        return f"https://<route>.{self.domain}{self._port_suffix}"

    @property
    def _port_suffix(self) -> str:
        return "" if self.port == HTTPS_PORT else f":{self.port}"

    def name_of(self, hostname: str) -> DnsName | None:
        """The route name a hostname stands for, or None when it is not under the domain."""
        try:
            return DnsName(hostname).relative_to(self.domain)
        except InvalidValue:
            return None


def matches(name: DnsName, pattern: str) -> bool:
    """Whether a route name matches a pattern such as `api.feat-a` or `*.feat-a`."""
    return fnmatchcase(name.value, pattern)
