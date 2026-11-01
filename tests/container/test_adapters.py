"""In-container adapters: Caddy's API against a local stand-in, the proxy's container, scripts."""

from __future__ import annotations

import json
import os
import pwd
import socketserver
import tempfile
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler
from pathlib import Path, PurePosixPath

import pytest

from outpost.container.adapters.caddy import (
    ROUTES_PATH,
    CaddyAdmin,
    caddy_route,
    parse_route,
    saved_routes,
    with_routes,
)
from outpost.container.adapters.init_files import (
    DirectoryOwnership,
    JsonBootStore,
    ScriptDirectories,
)
from outpost.container.adapters.proxy_container import CaddyContainer
from outpost.container.adapters.system_trust import SystemTrust
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
    """The stand-in listens on a unix socket, as Caddy's admin API does in the image."""
    handler = type("Handler", (CaddyStandIn,), {"routes": [], "requests": []})
    with tempfile.TemporaryDirectory(dir="/tmp") as folder:
        path = Path(folder) / "admin.sock"
        server = socketserver.ThreadingUnixStreamServer(str(path), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield CaddyAdmin(site=SITE, socket_path=path), handler
        finally:
            server.shutdown()
            server.server_close()


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


def test_an_absent_proxy_is_not_running(tmp_path: Path) -> None:
    admin = CaddyAdmin(site=SITE, socket_path=tmp_path / "none.sock", sleep=lambda _: None)
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


def container(tmp_path: Path, runner: FakeRunner, site_port: int = 8443) -> CaddyContainer:
    base = tmp_path / "caddy.json"
    base.write_text(IMAGE_CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
    return CaddyContainer(
        runner,
        site_port=site_port,
        base_config=base,
        state=tmp_path / "proxy",
        socket_dir=tmp_path / "proxy" / "admin",
        socket_group=None,
    )


def test_a_missing_proxy_is_created_on_the_outpost_network(tmp_path: Path) -> None:
    runner = FakeRunner()
    runner.answer(["docker", "network", "inspect"], failed())
    runner.answer(["docker", "container", "inspect"], failed(1, "No such container"))
    container(tmp_path, runner).ensure_running()
    argvs = runner.argvs()
    assert argvs[1] == ("docker", "network", "create", "outpost")
    run = argvs[-1]
    assert run[:5] == ("docker", "run", "--detach", "--name", "outpost-proxy")
    for expected in (
        "443:443",
        "8443:443",
        "devcontainer:host-gateway",
        f"{tmp_path}/proxy/admin:/run/outpost",
    ):
        assert expected in run
    assert [item for item in run if "2019" in item] == []
    assert oct((tmp_path / "proxy" / "admin").stat().st_mode & 0o777) == "0o750"
    assert run[-6:] == (
        "caddy:2.11",
        "caddy",
        "run",
        "--resume",
        "--config",
        "/etc/caddy/outpost.json",
    )
    assert (tmp_path / "proxy" / "data").is_dir()


def test_the_port_in_the_urls_is_published_in_the_container_too(tmp_path: Path) -> None:
    for site_port, published in ((8443, ["443:443", "8443:443"]), (443, ["443:443"])):
        runner = FakeRunner()
        runner.answer(["docker", "container", "inspect"], failed(1, "No such container"))
        container(tmp_path, runner, site_port).ensure_running()
        run = runner.argvs()[-1]
        assert [run[i + 1] for i, part in enumerate(run) if part == "--publish"] == published


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
    assert rewritten["admin"]["listen"].startswith("unix//run/outpost/")
    assert saved_routes(rewritten) == [caddy_route(API, SITE)]


def test_an_unreadable_saved_config_is_set_aside(tmp_path: Path) -> None:
    runner = FakeRunner()
    saved = tmp_path / "proxy" / "config" / "caddy" / "autosave.json"
    saved.parent.mkdir(parents=True)
    saved.write_text("{", encoding="utf-8")
    runner.answer(["docker", "container", "inspect"], failed(1, "No such container"))
    container(tmp_path, runner).ensure_running()
    assert not saved.exists()
    assert saved.with_suffix(".unreadable").read_text(encoding="utf-8") == "{"
    assert runner.argvs()[-1][:2] == ("docker", "run")


# ------------------------------------------------------------------ the container's trust


def test_the_proxys_ca_is_added_to_the_system_list_once(tmp_path: Path) -> None:
    runner = FakeRunner()
    trust = SystemTrust(runner, path=tmp_path / "ca-certificates" / "outpost-ca.crt")
    assert trust.trust("PEM one")
    assert not trust.trust("PEM one")
    assert trust.trust("PEM two")
    assert (tmp_path / "ca-certificates" / "outpost-ca.crt").read_text() == "PEM two"
    assert runner.argvs() == [("update-ca-certificates",)] * 2


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


def test_new_empty_volumes_go_to_dev(tmp_path: Path) -> None:
    fresh, used = tmp_path / "fresh", tmp_path / "used"
    fresh.mkdir()
    used.mkdir()
    (used / "keep").write_text("x", encoding="utf-8")
    me = os.getuid()
    owner = DirectoryOwnership(user=pwd.getpwuid(me).pw_name)
    owner.claim_if_empty(PurePosixPath(fresh))
    owner.claim_if_empty(PurePosixPath(used))
    owner.claim_if_empty(PurePosixPath(tmp_path / "missing"))
    assert fresh.stat().st_uid == me


def test_each_start_has_its_own_boot_id(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    (proc / "sys/kernel/random").mkdir(parents=True)
    (proc / "1").mkdir()
    (proc / "sys/kernel/random/boot_id").write_text("kernel-boot\n", encoding="utf-8")
    fields = " ".join(str(number) for number in range(4, 30))
    (proc / "1/stat").write_text(f"1 (tini (odd) name) S {fields}\n", encoding="utf-8")
    store = JsonBootStore(tmp_path / "boot.json", proc=proc)
    assert store.current_boot() == "kernel-boot/22"
    assert JsonBootStore(tmp_path / "boot.json", proc=tmp_path / "none").current_boot() == ""


def test_the_boot_record_survives_a_bad_file(tmp_path: Path) -> None:
    store = JsonBootStore(tmp_path / "state" / "boot.json")
    assert store.read() == BootRecord(ready=False)
    record = BootRecord(ready=True, init_digest="abc", init_failed=("01-a.sh",))
    store.write(record)
    assert store.read() == record
    (tmp_path / "state" / "boot.json").write_text("{", encoding="utf-8")
    assert store.read() == BootRecord(ready=False)
