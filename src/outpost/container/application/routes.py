"""`outpost route`: stacks register and remove their own routes, at run time."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from outpost.container.ports.engine import Engine
from outpost.container.ports.proxy import Proxy
from outpost.domain.errors import Unavailable
from outpost.domain.layout import NETWORK
from outpost.domain.names import DnsName
from outpost.domain.routes import Route, Site, Upstream, matches


@dataclass(frozen=True)
class AddedRoute:
    url: str
    attached: str | None
    """The container this call attached to the proxy's network; it leaves the network when
    it is created again, as a compose change does."""


@dataclass(frozen=True)
class ListedRoute:
    route: Route
    url: str


class Routes:
    def __init__(self, site: Site, proxy: Proxy, engine: Engine) -> None:
        self._site = site
        self._proxy = proxy
        self._engine = engine

    def add(self, name: DnsName, upstream: Upstream) -> AddedRoute:
        """Serve `name` from `upstream`, attaching the upstream container to the proxy's network."""
        container = not upstream.is_devcontainer and self._engine.is_container(upstream.host)
        attached = container and NETWORK not in self._engine.networks(upstream.host)
        if attached:
            self._engine.connect(NETWORK, upstream.host)
        self._proxy.put(Route(name, upstream))
        return AddedRoute(self._site.url(name), upstream.host if attached else None)

    def remove(self, patterns: Sequence[str]) -> tuple[DnsName, ...]:
        """Remove every route matching one of the patterns, such as `*.feat-a`."""
        names = tuple(
            route.name
            for route in self._proxy.routes()
            if any(matches(route.name, pattern) for pattern in patterns)
        )
        if not names:
            raise Unavailable(f"no route matches {', '.join(patterns)}")
        for name in names:
            self._proxy.remove(name)
        return names

    def listing(self) -> tuple[ListedRoute, ...]:
        routes = sorted(self._proxy.routes(), key=lambda route: route.name.value)
        return tuple(ListedRoute(route, self._site.url(route.name)) for route in routes)
