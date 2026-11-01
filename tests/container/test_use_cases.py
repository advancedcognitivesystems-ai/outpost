"""Routes, boot, init and status inside the container, through fakes."""

from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from outpost.container.application.boot import Boot, Init, ProxyStartup, Status
from outpost.container.application.routes import Routes
from outpost.domain.errors import Unavailable
from outpost.domain.init import Script
from outpost.domain.names import DnsName
from outpost.domain.routes import Route, Site, Upstream
from outpost.domain.status import BootRecord
from tests.fakes import (
    Events,
    FakeEngine,
    FakeOwnership,
    FakeProxy,
    FakeProxyRuntime,
    FakeScripts,
    FakeStore,
)

SITE = Site(DnsName("dev.localhost"), 8443)
API = Route(DnsName("api.feat-a"), Upstream("feat-a-api-1", 8080))


def routes(events: Events, containers: dict[str, list[str]]) -> tuple[Routes, FakeProxy]:
    proxy = FakeProxy(events)
    return Routes(SITE, proxy, FakeEngine(events, containers)), proxy


def test_a_container_upstream_joins_the_proxy_network_once() -> None:
    events: Events = []
    service, proxy = routes(events, {"feat-a-api-1": ["feat-a_default"]})
    first = service.add(DnsName("api.feat-a"), Upstream.parse("feat-a-api-1:8080"))
    again = service.add(DnsName("api.feat-a"), Upstream.parse("feat-a-api-1:8081"))
    assert first.url == "https://api.feat-a.dev.localhost:8443"
    assert (first.attached, again.attached) == ("feat-a-api-1", None)
    assert events == [
        "connect feat-a-api-1 to outpost",
        "put api.feat-a feat-a-api-1:8080",
        "put api.feat-a feat-a-api-1:8081",
    ]
    assert len(proxy.routes()) == 1


def test_other_upstreams_are_left_to_the_proxy() -> None:
    events: Events = []
    service, _ = routes(events, {"devcontainer": []})
    web = service.add(DnsName("web"), Upstream.parse("devcontainer:3000"))
    api = service.add(DnsName("api"), Upstream.parse("api-alias:80"))
    assert events == ["put web devcontainer:3000", "put api api-alias:80"]
    assert (web.attached, api.attached) == (None, None)


def test_routes_are_removed_by_pattern() -> None:
    events: Events = []
    service, proxy = routes(events, {})
    for name in ("api.feat-a", "web.feat-a", "api.feat-b"):
        proxy.put(Route(DnsName(name), Upstream("x", 80)))
    assert service.remove(["*.feat-a"]) == (DnsName("api.feat-a"), DnsName("web.feat-a"))
    assert [item.route.name.value for item in service.listing()] == ["api.feat-b"]
    with pytest.raises(Unavailable, match="no route matches"):
        service.remove(["*.feat-z"])


def scripts(events: Events, codes: dict[str, int] | None = None) -> FakeScripts:
    listing = [
        Script("10-image.sh", PurePosixPath("/etc/outpost/init.d/10-image.sh"), "a"),
        Script("01-yours.sh", PurePosixPath("/var/lib/outpost/init.d/01-yours.sh"), "b"),
    ]
    return FakeScripts(events, listing, codes or {})


def boot(events: Events, store: FakeStore, proxy: FakeProxy | None = None) -> Boot:
    return Boot(
        proxy=ProxyStartup(FakeProxyRuntime(events), proxy or FakeProxy(events)),
        init=Init(scripts(events), store),
        store=store,
        ownership=FakeOwnership(events),
        persisted=(PurePosixPath("/opt/tools"),),
    )


def test_boot_starts_the_proxy_reapplies_routes_then_inits_then_is_ready() -> None:
    events: Events = []
    proxy = FakeProxy(events)
    proxy.table[API.name.value] = API
    store = FakeStore(BootRecord(ready=True, boot_id="boot-0", init_digest="old"))
    record = boot(events, store, proxy).run()
    assert events == [
        "proxy running",
        "proxy ready",
        "put api.feat-a feat-a-api-1:8080",
        "claim /opt/tools",
        "run 10-image.sh",
        "run 01-yours.sh",
    ]
    assert store.writes[0].ready is False
    assert (record.ready, record.boot_id) == (True, "boot-1")
    assert record.init_digest != "old"


def test_the_proxy_starts_alone_with_its_routes() -> None:
    events: Events = []
    proxy = FakeProxy(events)
    proxy.table[API.name.value] = API
    assert ProxyStartup(FakeProxyRuntime(events), proxy).run() == 1
    assert events == ["proxy running", "proxy ready", "put api.feat-a feat-a-api-1:8080"]


def test_a_proxy_that_does_not_start_still_lets_boot_finish() -> None:
    events: Events = []
    proxy = FakeProxy(events)
    proxy.fail_ready = True
    store = FakeStore()
    with pytest.raises(Unavailable):
        boot(events, store, proxy).run()
    assert store.record.ready
    assert "run 01-yours.sh" in events


def test_boot_ends_ready_even_when_init_breaks() -> None:
    events: Events = []
    store = FakeStore()
    broken = Boot(
        proxy=ProxyStartup(FakeProxyRuntime(events), FakeProxy(events)),
        init=Init(BrokenScripts(), store),
        store=store,
        ownership=FakeOwnership(events),
        persisted=(),
    )
    with pytest.raises(RuntimeError):
        broken.run()
    assert store.record.ready


class BrokenScripts:
    def listing(self) -> tuple[Script, ...]:
        raise RuntimeError("unreadable init.d")

    def run(self, script: Script) -> int:
        return 0


def test_init_reruns_only_when_the_scripts_changed() -> None:
    events: Events = []
    store = FakeStore()
    init = Init(scripts(events, {"01-yours.sh": 3}), store)
    first = init.run(only_if_changed=True)
    assert first.init_failed == ("01-yours.sh",)
    events.clear()
    assert init.run(only_if_changed=True) == first
    assert events == []
    init.run(only_if_changed=False)
    assert events == ["run 10-image.sh", "run 01-yours.sh"]


def test_status_is_ready_only_for_this_start() -> None:
    proxy = FakeProxy([])
    proxy.put(Route(DnsName("api"), Upstream("x", 80)))
    store = FakeStore(BootRecord(ready=True, boot_id="boot-1", init_failed=("01-a.sh",)))
    report = Status(proxy, store).report()
    assert (report.ready, report.proxy_running, report.routes) == (True, True, 1)
    assert report.init_failed == ("01-a.sh",)
    store.boot = "boot-2"
    assert not Status(proxy, store).report().ready
    proxy.is_running = False
    assert Status(proxy, store).report().routes == 0
