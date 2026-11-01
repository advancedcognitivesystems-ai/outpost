"""What the running container actually exposes, whatever features or the image added.

Your settings are checked before `up`, but features and image metadata can add mounts too;
`up` therefore checks the container it got, and refuses it when it breaks a rule.
"""

from __future__ import annotations

from dataclasses import dataclass

from outpost.domain.layout import PROXY_LISTEN_PORT
from outpost.domain.routes import Site

BIND = "bind"
HOST_NETWORK = "host"


@dataclass(frozen=True)
class Mount:
    kind: str
    destination: str


@dataclass(frozen=True)
class Published:
    host_ip: str
    host_port: str
    container_port: str
    """Such as `443/tcp`."""

    def __str__(self) -> str:
        return f"{self.host_ip or '0.0.0.0'}:{self.host_port}->{self.container_port}"


@dataclass(frozen=True)
class Exposure:
    mounts: tuple[Mount, ...]
    network_mode: str
    published: tuple[Published, ...]


def exposure_problems(exposure: Exposure, site: Site) -> tuple[str, ...]:
    """Each way the container reaches past its volumes and its one loopback port."""
    allowed = Published("127.0.0.1", str(site.port), f"{PROXY_LISTEN_PORT}/tcp")
    problems = [
        f"{mount.destination} is mounted from the host"
        for mount in exposure.mounts
        if mount.kind == BIND
    ]
    if exposure.network_mode == HOST_NETWORK:
        problems.append("the container shares the host's network")
    problems += [f"{item} is published" for item in exposure.published if item != allowed]
    return tuple(problems)
