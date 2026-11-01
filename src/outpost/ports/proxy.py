"""The two proxies: the edge on the host, and the router that stacks declare their routes to."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from outpost.domain.resources import HostLayout
from outpost.domain.routes import Route
from outpost.domain.tls import TlsMaterial
from outpost.ports.engine import ContainerSpec


class EdgeProxy(Protocol):
    def prepare(self, layout: HostLayout, material: TlsMaterial) -> ContainerSpec:
        """Write the edge's settings on the host and describe the container that serves them."""
        ...


class RouterConvention(Protocol):
    @property
    def network(self) -> str:
        """Network of the inner engine that the router and exposed services share."""
        ...

    def container(self) -> ContainerSpec:
        """The router, run on the box's inner engine."""
        ...

    def labels(self, route: Route) -> Mapping[str, str]:
        """Container labels that declare this route to the router."""
        ...
