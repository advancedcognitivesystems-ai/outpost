"""`Proxy` through Caddy's admin API: one route object per name, addressed by its `@id`.

The API listens on a unix socket shared with the dev container only, never on TCP: on a
wildcard address Caddy skips its Host check, and every stack container would reach it.
Caddy saves every change made through the API and restores it at start (`caddy run --resume`),
so routes outlive restarts of the proxy and of the dev container.
"""

from __future__ import annotations

import http.client
import json
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from outpost.domain.errors import InvalidValue, Unavailable
from outpost.domain.layout import ADMIN_SOCKET
from outpost.domain.names import DnsName
from outpost.domain.routes import Route, Site, Upstream

SERVER = "outpost"
"""The server's name in `image/caddy.json`; a test reads both."""
ROUTES_PATH = f"/config/apps/http/servers/{SERVER}/routes"
ROUTE_ID_PREFIX = "outpost-route-"
CA_PATH = "/pki/ca/local"
SOCKET_DIR_IN_PROXY = "/run/outpost"
"""Where the proxy container sees the socket's folder; `image/caddy.json` listens there."""
POLL_SECONDS = 0.5

type JsonObject = dict[str, object]


def caddy_route(route: Route, site: Site) -> JsonObject:
    return {
        "@id": ROUTE_ID_PREFIX + route.name.value,
        "match": [{"host": [site.hostname(route.name).value]}],
        "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": str(route.upstream)}]}],
        "terminal": True,
    }


def parse_route(item: object) -> Route | None:
    """The route an object of Caddy's config stands for, or None when it is not Outpost's."""
    if not isinstance(item, dict):
        return None
    identifier = item.get("@id")
    if not isinstance(identifier, str) or not identifier.startswith(ROUTE_ID_PREFIX):
        return None
    try:
        dial = item["handle"][0]["upstreams"][0]["dial"]
        return Route(DnsName(identifier[len(ROUTE_ID_PREFIX) :]), Upstream.parse(str(dial)))
    except (KeyError, IndexError, TypeError, InvalidValue):
        return None


def saved_routes(config: object) -> list[object]:
    """Outpost's routes in a saved Caddy config, such as `autosave.json`."""
    try:
        routes = config["apps"]["http"]["servers"][SERVER]["routes"]  # type: ignore[index]
    except (KeyError, TypeError):
        return []
    return [item for item in routes if parse_route(item) is not None]


def with_routes(base: JsonObject, routes: list[object]) -> JsonObject:
    """`base` with its server's routes replaced: how saved routes move to a new base config."""
    config = json.loads(json.dumps(base))
    config["apps"]["http"]["servers"][SERVER]["routes"] = routes
    return config  # type: ignore[no-any-return]


@dataclass(frozen=True)
class _Reply:
    status: int
    body: bytes

    @property
    def ok(self) -> bool:
        return self.status == 200

    def json(self) -> object:
        return json.loads(self.body) if self.body.strip() else None


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: Path, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self._path = path

    def connect(self) -> None:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(self.timeout)
        connection.connect(str(self._path))
        self.sock = connection


class CaddyAdmin:
    def __init__(
        self,
        *,
        site: Site,
        socket_path: Path = Path(ADMIN_SOCKET),
        timeout: float = 10.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._site = site
        self._socket = socket_path
        self._timeout = timeout
        self._sleep = sleep
        self._clock = clock

    def running(self) -> bool:
        try:
            return self._request("GET", "/config/").ok
        except Unavailable:
            return False

    def wait_ready(self, timeout: float) -> None:
        deadline = self._clock() + timeout
        while not self.running():
            if self._clock() >= deadline:
                raise Unavailable(f"the proxy's API did not answer on {self._socket}")
            self._sleep(POLL_SECONDS)

    def routes(self) -> tuple[Route, ...]:
        items = self._expect("GET", ROUTES_PATH).json()
        parsed = (parse_route(item) for item in (items if isinstance(items, list) else []))
        return tuple(route for route in parsed if route is not None)

    def put(self, route: Route) -> None:
        body = caddy_route(route, self._site)
        path = f"/id/{body['@id']}"
        if self._request("GET", path).ok:
            self._expect("PATCH", path, body)
        else:
            self._expect("POST", ROUTES_PATH, body)

    def remove(self, name: DnsName) -> None:
        self._expect("DELETE", f"/id/{ROUTE_ID_PREFIX}{name}")

    def root_certificate(self) -> str:
        data = self._expect("GET", CA_PATH).json()
        certificate = data.get("root_certificate") if isinstance(data, dict) else None
        if not isinstance(certificate, str) or not certificate.strip():
            raise Unavailable("the proxy has no root certificate yet")
        return certificate

    def _expect(self, method: str, path: str, body: object = None) -> _Reply:
        reply = self._request(method, path, body)
        if not reply.ok:
            detail = reply.body.decode(errors="replace").strip()
            raise Unavailable(f"the proxy refused {method} {path} ({reply.status}): {detail}")
        return reply

    def _request(self, method: str, path: str, body: object = None) -> _Reply:
        data = None if body is None else json.dumps(body).encode()
        headers = {} if body is None else {"Content-Type": "application/json"}
        connection = _UnixConnection(self._socket, self._timeout)
        try:
            connection.request(method, path, data, headers)
            response = connection.getresponse()
            return _Reply(response.status, response.read())
        except PermissionError:
            raise Unavailable(f"{self._socket} is reserved to root and the docker group") from None
        except OSError as error:
            raise Unavailable(
                f"the proxy's API does not answer on {self._socket}: {error}"
            ) from None
        finally:
            connection.close()
