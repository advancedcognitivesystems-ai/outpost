"""Where the dev container runs: the local Docker, or a Linux host reached over SSH."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from outpost.domain.errors import InvalidValue
from outpost.domain.names import port_number

LOCAL = "local"


@dataclass(frozen=True, slots=True)
class LocalHost:
    def __str__(self) -> str:
        return LOCAL


@dataclass(frozen=True, slots=True)
class SshHost:
    hostname: str
    user: str | None = None
    port: int | None = None

    @property
    def destination(self) -> str:
        return f"{self.user}@{self.hostname}" if self.user else self.hostname

    @property
    def docker_host(self) -> str:
        """The value of `DOCKER_HOST` that makes Docker run its commands on this host."""
        return str(self)

    def ssh_arguments(self) -> tuple[str, ...]:
        """Arguments that make `ssh` reach this host; your ssh config still applies."""
        port = ("-p", str(self.port)) if self.port else ()
        return (*port, self.destination)

    def __str__(self) -> str:
        port = f":{self.port}" if self.port else ""
        return f"ssh://{self.destination}{port}"


type Host = LocalHost | SshHost


def parse_host(text: str) -> Host:
    if text == LOCAL:
        return LocalHost()
    parts = urlsplit(text)
    try:
        port = parts.port
    except ValueError:
        port = -1
    if (
        parts.scheme != "ssh"
        or not parts.hostname
        or parts.password is not None
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
        or port == -1
    ):
        raise InvalidValue(f"{text!r} is not a host: use 'local' or 'ssh://user@host[:port]'")
    return SshHost(
        hostname=parts.hostname,
        user=parts.username,
        port=port_number(port) if port is not None else None,
    )
