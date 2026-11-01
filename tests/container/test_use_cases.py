"""Routes, boot, init and status inside the container, through fakes."""

from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from outpost.container.application.boot import Boot, Init, Status
from outpost.container.application.routes import Routes
from outpost.domain.errors import Unavailable
from outpost.domain.init import Script
from outpost.domain.names import DnsName
from outpost.domain.routes import Route, Site, Upstream
from outpost.domain.status import BootRecord
from tests.fakes import Events, FakeEngine, FakeProxy, FakeProxyRuntime, FakeScripts, FakeStore

SITE = Site(DnsName("dev.localhost"), 8443)


def routes(events: Events, containers: dict[str, list[str]]) -> tuple[Routes, FakeProxy]:
    proxy = FakeProxy(events)
    return Routes(SITE, proxy, FakeEngine(events, containers)), proxy


def test_a_container_upstream_joins_the_proxy_network_once() -> None:
    events: Events = []
    service, proxy = routes(events, {"feat-a-api-1": ["feat-a_default"]})
    url = service.add(DnsName("api.feat-a"), Upstream.parse("feat-a-api-1:8080"))
    service.add(DnsName("api.feat-a"), Upstream.parse("feat-a-api-1:8081"))
    assert url == "https://api.feat-a.dev.localhost:8443"
    assert events == [
        "connect feat-a-api-1 to outpost",
        "put api.feat-a feat-a-api-1:8080",
        "put api.feat-a feat-a-api-1:8081",
    ]
    assert len(proxy.routes()) == 1


def test_other_upstreams_are_left_to_the_proxy() -> None:
    events: Events = []
    service, _ = routes(events, {})
    service.add(DnsName("web"), Upstream.parse("devcontainer:3000"))
    service.add(DnsName("api"), Upstream.parse("api-alias:80"))
    assert events == ["put web devcontainer:3000", "put api api-alias:80"]


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


def test_boot_starts_the_proxy_then_runs_init_then_is_ready() -> None:
    events: Events = []
    store = FakeStore(BootRecord(ready=True, init_digest="old"))
    init = Init(scripts(events), store)
    record = Boot(FakeProxyRuntime(events), FakeProxy(events), init, store).run()
    assert events == ["proxy running", "proxy ready", "run 10-image.sh", "run 01-yours.sh"]
    assert store.writes[0].ready is False
    assert record.ready
    assert record.init_digest != "old"


def test_a_proxy_that_does_not_start_still_lets_boot_finish() -> None:
    events: Events = []
    proxy = FakeProxy(events)
    proxy.fail_ready = True
    store = FakeStore()
    boot = Boot(FakeProxyRuntime(events), proxy, Init(scripts(events), store), store)
    with pytest.raises(Unavailable):
        boot.run()
    assert store.record.ready
    assert "run 01-yours.sh" in events


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


def test_status_counts_routes_of_a_running_proxy() -> None:
    proxy = FakeProxy([])
    proxy.put(Route(DnsName("api"), Upstream("x", 80)))
    store = FakeStore(BootRecord(ready=True, init_failed=("01-a.sh",)))
    report = Status(proxy, store).report()
    assert (report.ready, report.proxy_running, report.routes) == (True, True, 1)
    assert report.init_failed == ("01-a.sh",)
    proxy.is_running = False
    assert Status(proxy, store).report().routes == 0
