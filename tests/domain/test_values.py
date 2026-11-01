"""Names, hosts, routes, volumes, copies and status: plain values, checked when built."""

from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from outpost.domain.errors import InvalidValue
from outpost.domain.host import LocalHost, SshHost, parse_host
from outpost.domain.init import Script, scripts_digest
from outpost.domain.names import DnsName, EnvironmentName
from outpost.domain.routes import Site, Upstream, matches
from outpost.domain.status import BootRecord, ContainerStatus
from outpost.domain.transfer import ClientEndpoint, CopyIn, CopyOut, parse_copy, placement
from outpost.domain.volumes import persist_path, volumes_for

SITE = Site(DnsName("dev.localhost"), 8443)


@pytest.mark.parametrize("name", ["main", "a", "feat-1", "x" * 30])
def test_environment_names_accepted(name: str) -> None:
    assert EnvironmentName(name).container == f"outpost-{name}"


@pytest.mark.parametrize("name", ["", "Main", "1main", "main-", "x" * 31, "a_b"])
def test_environment_names_refused(name: str) -> None:
    with pytest.raises(InvalidValue):
        EnvironmentName(name)


def test_dns_names_compose_and_split() -> None:
    domain = DnsName("dev.localhost")
    assert DnsName("api.feat-a").under(domain) == DnsName("api.feat-a.dev.localhost")
    assert DnsName("api.feat-a.dev.localhost").relative_to(domain) == DnsName("api.feat-a")
    assert DnsName("dev.localhost").relative_to(domain) is None
    assert DnsName("api.example.com").relative_to(domain) is None


@pytest.mark.parametrize("name", ["API", "-api", "api-", "a..b", "a_b", "a" * 64])
def test_dns_names_refused(name: str) -> None:
    with pytest.raises(InvalidValue):
        DnsName(name)


def test_hosts_parse() -> None:
    assert parse_host("local") == LocalHost()
    remote = parse_host("ssh://dev@my-vm:2222")
    assert remote == SshHost("my-vm", "dev", 2222)
    assert isinstance(remote, SshHost)
    assert remote.docker_host == "ssh://dev@my-vm:2222"
    assert remote.ssh_arguments() == ("-p", "2222", "dev@my-vm")
    assert parse_host("ssh://my-vm") == SshHost("my-vm")


@pytest.mark.parametrize(
    "text", ["", "remote", "http://my-vm", "ssh://", "ssh://u:pw@vm", "ssh://vm/path", "ssh://vm:0"]
)
def test_hosts_refused(text: str) -> None:
    with pytest.raises(InvalidValue):
        parse_host(text)


def test_upstreams_and_urls() -> None:
    assert Upstream.parse("feat-a-api-1:8080") == Upstream("feat-a-api-1", 8080)
    assert Upstream.parse("devcontainer:3000").is_devcontainer
    assert SITE.url(DnsName("api.feat-a")) == "https://api.feat-a.dev.localhost:8443"
    assert (
        Site(DnsName("dev.example.com"), 443).url(DnsName("web")) == "https://web.dev.example.com"
    )
    assert SITE.name_of("api.feat-a.dev.localhost") == DnsName("api.feat-a")
    assert SITE.name_of("not a name") is None


@pytest.mark.parametrize("text", ["api", "api:", ":80", "api:http", "api:70000", "a b:80"])
def test_upstreams_refused(text: str) -> None:
    with pytest.raises(InvalidValue):
        Upstream.parse(text)


def test_route_patterns() -> None:
    assert matches(DnsName("api.feat-a"), "*.feat-a")
    assert not matches(DnsName("api.feat-b"), "*.feat-a")
    assert matches(DnsName("api.feat-a"), "api.feat-a")


def test_default_volumes_then_persisted_paths() -> None:
    volumes = volumes_for(EnvironmentName("main"), [PurePosixPath("/opt/my_tools")])
    assert [(v.name, str(v.target)) for v in volumes] == [
        ("outpost-main-home", "/home/dev"),
        ("outpost-main-workspaces", "/workspaces"),
        ("outpost-main-docker", "/var/lib/docker"),
        ("outpost-main-state", "/var/lib/outpost"),
        ("outpost-main-persist-opt-my_tools", "/opt/my_tools"),
    ]


@pytest.mark.parametrize(
    "text", ["opt/tools", "/", "/home", "/home/dev/.cache", "/var/lib", "/proc/x", "/opt/../etc"]
)
def test_persisted_paths_refused(text: str) -> None:
    with pytest.raises(InvalidValue):
        persist_path(text)


def test_persisted_paths_cannot_overlap_each_other() -> None:
    with pytest.raises(InvalidValue, match="overlaps"):
        volumes_for(EnvironmentName("main"), [PurePosixPath("/opt"), PurePosixPath("/opt/tools")])


def test_copies_go_one_way_or_the_other() -> None:
    copy_in = parse_copy("./notes.md", ":~/inbox/")
    assert isinstance(copy_in, CopyIn)
    assert copy_in.destination.path == PurePosixPath("/home/dev/inbox")
    assert copy_in.destination.into
    copy_out = parse_copy(":/workspaces/app/out", ".")
    assert isinstance(copy_out, CopyOut)
    assert copy_out.destination == ClientEndpoint(copy_out.destination.path, into=True)
    for source, destination in (("a", "b"), (":/a", ":/b"), ("a", ":relative")):
        with pytest.raises(InvalidValue):
            parse_copy(source, destination)


def test_placement_inside_or_as_the_destination() -> None:
    target = PurePosixPath("/home/dev/inbox")
    assert placement(target, "notes.md", into=True) == (target, "notes.md")
    assert placement(target, "notes.md", into=False) == (PurePosixPath("/home/dev"), "inbox")


def test_status_round_trips_as_json() -> None:
    status = ContainerStatus(ready=True, proxy_running=True, routes=3, init_failed=("01-a.sh",))
    assert ContainerStatus.from_json(status.to_json()) == status
    record = BootRecord(ready=True, init_digest="abc", init_failed=())
    assert BootRecord.from_json(record.to_json()) == record
    with pytest.raises(InvalidValue):
        ContainerStatus.from_json("not json")


def test_init_digest_follows_content_and_order() -> None:
    one = Script("01-a.sh", PurePosixPath("/var/lib/outpost/init.d/01-a.sh"), "aaa")
    two = Script("02-b.sh", PurePosixPath("/var/lib/outpost/init.d/02-b.sh"), "bbb")
    edited = Script(one.name, one.path, "ccc")
    assert scripts_digest([one, two]) != scripts_digest([two, one])
    assert scripts_digest([one, two]) != scripts_digest([edited, two])
    assert scripts_digest([one, two]) == scripts_digest([one, two])
