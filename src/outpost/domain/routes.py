"""Routes: how a worktree's services become `https://<subdomain>--<worktree>.<domain>`."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from outpost.domain.errors import InvalidValue
from outpost.domain.names import DNS_LABEL_MAX, Domain, Port, ServiceName, Subdomain, WorktreeName

SEPARATOR = "--"
HTTPS_DEFAULT_PORT = 443
HTTP_DEFAULT_PORT = 80


@dataclass(frozen=True)
class ExposedService:
    """A compose service that gets a route, from `stacks.expose`."""

    service: ServiceName
    port: Port
    subdomain: Subdomain


@dataclass(frozen=True)
class Route:
    """One hostname mapped to one service port of one worktree's stack."""

    worktree: WorktreeName
    service: ServiceName
    port: Port
    hostname: str

    @property
    def key(self) -> str:
        """Stable identifier, unique per worktree and subdomain."""
        return self.hostname.split(".", 1)[0]

    def url(self, *, secure: bool, port: int) -> str:
        scheme, default = ("https", HTTPS_DEFAULT_PORT) if secure else ("http", HTTP_DEFAULT_PORT)
        suffix = "" if port == default else f":{port}"
        return f"{scheme}://{self.hostname}{suffix}"


def plan_routes(
    worktree: WorktreeName, services: Iterable[ExposedService], domain: Domain
) -> tuple[Route, ...]:
    """Every route of a worktree; refuses names that do not fit one DNS label."""
    routes = []
    for exposed in services:
        label = f"{exposed.subdomain}{SEPARATOR}{worktree}"
        if len(label) > DNS_LABEL_MAX:
            raise InvalidValue(
                f"route {label!r} is {len(label)} characters; a DNS label allows {DNS_LABEL_MAX}. "
                "Use a shorter worktree name or subdomain."
            )
        routes.append(
            Route(
                worktree=worktree,
                service=exposed.service,
                port=exposed.port,
                hostname=f"{label}.{domain}",
            )
        )
    return tuple(routes)


STACK_PREFIX = "wt-"


def stack_project(worktree: WorktreeName) -> str:
    """Name of a worktree's stack on the inner engine."""
    return f"{STACK_PREFIX}{worktree}"


def worktree_of_stack(project: str) -> WorktreeName | None:
    """The worktree a stack belongs to, or None for a stack Outpost did not start."""
    if not project.startswith(STACK_PREFIX):
        return None
    try:
        return WorktreeName(project.removeprefix(STACK_PREFIX))
    except InvalidValue:
        return None
