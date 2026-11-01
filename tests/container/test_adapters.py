"""In-container adapters: Caddy's API against a local stand-in, the proxy's container, scripts."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from outpost.container.adapters.caddy import (
    ROUTES_PATH,
    CaddyAdmin,
    caddy_route,
    parse_route,
    saved_routes,
    with_routes,
)
from outpost.container.adapters.init_files import JsonBootStore, ScriptDirectories
from outpost.container.adapters.proxy_container import CaddyContainer
from outpost.domain.errors import Unavailable
from outpost.domain.names import DnsName
from outpost.domain.routes import Route, Site, Upstream
from outpost.domain.status import BootRecord
from tests.fakes import FakeRunner, failed, ok

SITE = Site(DnsName("dev.localhost"), 8443)
API = Route(DnsName("api.feat-a"), Upstream("feat-a-api-1", 8080))
IMAGE_CONFIG = Path(__file__).resolve().parents[2] / "image" / "caddy.json"


class CaddyStandIn(BaseHTTPRequestHandler):
    """Just enough of Caddy's admin API: routes by `@id`, and the CA endpoint."""

    routes: list[dict[str, object]]
    requests: list[str]

    def log_message(self, format: str, *args: object) -> None:
        return None

    def _send(self, status: int, body: object = None) -> None:
        payload = json.dumps(body).encode() if body is not None else b""
        self.send_response(status)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        data = json.loads(self.rfile.read(length))
        assert isinstance(data, dict)
        return data

    def _find(self) -> int | None:
        wanted = self.path.removeprefix("/id/")
        return next((i for i, r in enumerate(self.routes) if r.get("@id") == wanted), None)

    def do_GET(self) -> None:
        self.requests.append(f"GET {self.path}")
        if self.path == "/config/":
            self._send(200, {})
        elif self.path == ROUTES_PATH:
            self._send(200, self.routes)
        elif self.path == "/pki/ca/local":
            self._send(200, {"id": "local", "root_certificate": "-----BEGIN CERTIFICATE-----\n"})
        else:
            index = self._find()
            if index is None:
                self._send(404, {"error": "unknown object ID"})
            else:
                self._send(200, self.routes[index])

    def do_POST(self) -> None:
        self.requests.append(f"POST {self.path}")
        self.routes.append(self._body())
        self._send(200)

    def do_PATCH(self) -> None:
        self.requests.append(f"PATCH {self.path}")
        index = self._find()
        if index is None:
            self._send(404, {"error": "unknown object ID"})
            return
        self.routes[index] = self._body()
        self._send(200)

    def do_DELETE(self) -> None:
        self.requests.append(f"DELETE {self.path}")
        index = self._find()
        if index is None:
            self._send(404, {"error": "unknown object ID"})
            return
        del self.routes[index]
        self._send(200)


@pytest.fixture
def caddy() -> Iterator[tuple[CaddyAdmin, type[CaddyStandIn]]]:
    handler = type("Handler", (CaddyStandIn,), {"routes": [], "requests": []})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield CaddyAdmin(base_url=f"http://{host!s}:{port}", site=SITE), handler
    finally:
        server.shutdown()


def test_a_new_route_is_posted_then_patched(
    caddy: tuple[CaddyAdmin, type[CaddyStandIn]],
) -> None:
    admin, server = caddy
    admin.put(API)
    admin.put(Route(API.name, Upstream("feat-a-api-1", 9090)))
    assert admin.routes() == (Route(API.name, Upstream("feat-a-api-1", 9090)),)
    assert [request.split()[0] for request in server.requests] == [
        "GET",
        "POST",
        "GET",
        "PATCH",
        "GET",
    ]
    assert server.routes[0]["match"] == [{"host": ["api.feat-a.dev.localhost"]}]


def test_routes_are_removed_and_the_root_is_served(
    caddy: tuple[CaddyAdmin, type[CaddyStandIn]],
) -> None:
    admin, _ = caddy
    admin.put(API)
    admin.remove(API.name)
    assert admin.routes() == ()
    with pytest.raises(Unavailable, match="404"):
        admin.remove(API.name)
    assert admin.root_certificate().startswith("-----BEGIN CERTIFICATE-----")
    assert admin.running()


def test_an_absent_proxy_is_not_running() -> None:
    admin = CaddyAdmin(base_url="http://127.0.0.1:9", site=SITE, sleep=lambda _: None)
    assert not admin.running()
    with pytest.raises(Unavailable, match="did not answer"):
        admin.wait_ready(0)


def test_only_outposts_routes_are_read_back() -> None:
    assert parse_route(caddy_route(API, SITE)) == API
    assert parse_route({"@id": "someone-else", "handle": []}) is None
    assert parse_route({"@id": "outpost-route-api", "handle": []}) is None
    assert parse_route("not an object") is None


def test_saved_routes_move_onto_a_new_base() -> None:
    base = json.loads(IMAGE_CONFIG.read_text(encoding="utf-8"))
    saved = with_routes(base, [caddy_route(API, SITE), {"@id": "foreign"}])
    kept = saved_routes(saved)
    assert kept == [caddy_route(API, SITE)]
    assert saved_routes({"apps": {}}) == []


# ------------------------------------------------------------------ the proxy's container


def container(tmp_path: Path, runner: FakeRunner) -> CaddyContainer:
    base = tmp_path / "caddy.json"
    base.write_text(IMAGE_CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
    return CaddyContainer(runner, base_config=base, state=tmp_path / "proxy")


def test_a_missing_proxy_is_created_on_the_outpost_network(tmp_path: Path) -> None:
    runner = FakeRunner()
    runner.answer(["docker", "network", "inspect"], failed())
    runner.answer(["docker", "container", "inspect"], failed(1, "No such container"))
    container(tmp_path, runner).ensure_running()
    argvs = runner.argvs()
    assert argvs[1] == ("docker", "network", "create", "outpost")
    run = argvs[-1]
    assert run[:5] == ("docker", "run", "--detach", "--name", "outpost-proxy")
    for expected in ("443:443", "127.0.0.1:2019:2019", "devcontainer:host-gateway"):
        assert expected in run
    assert run[-6:] == (
        "caddy:2.11",
        "caddy",
        "run",
        "--resume",
        "--config",
        "/etc/caddy/outpost.json",
    )
    assert (tmp_path / "proxy" / "data").is_dir()


def test_a_current_proxy_is_only_started(tmp_path: Path) -> None:
    runner = FakeRunner()
    proxy = container(tmp_path, runner)
    spec = proxy._spec()
    runner.answer(["docker", "container", "inspect"], ok(f"false {spec}\n"))
    proxy.ensure_running()
    assert runner.argvs()[-1] == ("docker", "start", "outpost-proxy")


def test_an_outdated_proxy_is_recreated_with_its_routes(tmp_path: Path) -> None:
    runner = FakeRunner()
    proxy = container(tmp_path, runner)
    saved = tmp_path / "proxy" / "config" / "caddy" / "autosave.json"
    saved.parent.mkdir(parents=True)
    old_base = json.loads(IMAGE_CONFIG.read_text(encoding="utf-8"))
    old_base["admin"]["listen"] = "localhost:2019"
    saved.write_text(json.dumps(with_routes(old_base, [caddy_route(API, SITE)])), encoding="utf-8")
    runner.answer(["docker", "container", "inspect"], ok("true oldspec\n"))
    proxy.ensure_running()
    assert ("docker", "rm", "--force", "outpost-proxy") in runner.argvs()
    rewritten = json.loads(saved.read_text(encoding="utf-8"))
    assert rewritten["admin"]["listen"] == "0.0.0.0:2019"
    assert saved_routes(rewritten) == [caddy_route(API, SITE)]


# ------------------------------------------------------------------ init scripts and record


def test_scripts_list_image_ones_first_and_run_by_kind(tmp_path: Path) -> None:
    image, yours = tmp_path / "image", tmp_path / "yours"
    image.mkdir()
    yours.mkdir()
    (image / "10-base.sh").write_text("true\n", encoding="utf-8")
    (yours / "02-b.sh").write_text("true\n", encoding="utf-8")
    runnable = yours / "01-a.sh"
    runnable.write_text("#!/bin/sh\ntrue\n", encoding="utf-8")
    runnable.chmod(0o755)
    runner = FakeRunner()
    directories = ScriptDirectories(runner, [image, yours, tmp_path / "missing"])
    listing = directories.listing()
    assert [script.name for script in listing] == ["10-base.sh", "01-a.sh", "02-b.sh"]
    for script in listing:
        directories.run(script)
    assert runner.argvs() == [
        ("sh", str(image / "10-base.sh")),
        (str(runnable),),
        ("sh", str(yours / "02-b.sh")),
    ]
    assert runner.calls[0].env == {"OUTPOST_USER": "dev"}


def test_the_boot_record_survives_a_bad_file(tmp_path: Path) -> None:
    store = JsonBootStore(tmp_path / "state" / "boot.json")
    assert store.read() == BootRecord(ready=False)
    record = BootRecord(ready=True, init_digest="abc", init_failed=("01-a.sh",))
    store.write(record)
    assert store.read() == record
    (tmp_path / "state" / "boot.json").write_text("{", encoding="utf-8")
    assert store.read() == BootRecord(ready=False)
