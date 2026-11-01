from __future__ import annotations

import pytest

from outpost.domain.errors import InvalidValue
from outpost.domain.names import Domain, Port, ProjectName, ServiceName, Subdomain, WorktreeName
from outpost.domain.resources import HostResources, Role, expand_home
from outpost.domain.routes import ExposedService, plan_routes, stack_project, worktree_of_stack


@pytest.mark.parametrize("value", ["feat-a", "a", "fix-123", "x" * 40])
def test_valid_worktree_names(value: str) -> None:
    assert str(WorktreeName(value)) == value


@pytest.mark.parametrize("value", ["Feat", "feat_a", "-feat", "feat-", "a--b", "x" * 41, ""])
def test_invalid_worktree_names(value: str) -> None:
    with pytest.raises(InvalidValue):
        WorktreeName(value)


def test_domain_needs_a_dot_and_lowercase() -> None:
    assert str(Domain("dev.localhost")) == "dev.localhost"
    with pytest.raises(InvalidValue):
        Domain("localhost")
    with pytest.raises(InvalidValue):
        Domain("Dev.Example.com")


def test_port_range() -> None:
    assert int(Port(443)) == 443
    with pytest.raises(InvalidValue):
        Port(0)
    with pytest.raises(InvalidValue):
        Port(70000)


def _api() -> ExposedService:
    return ExposedService(ServiceName("api"), Port(5000), Subdomain("api"))


def test_routes_are_flat_under_one_wildcard() -> None:
    (route,) = plan_routes(WorktreeName("feat-a"), [_api()], Domain("dev.acme.example"))
    assert route.hostname == "api--feat-a.dev.acme.example"
    assert route.key == "api--feat-a"
    assert route.url(secure=True, port=443) == "https://api--feat-a.dev.acme.example"
    assert route.url(secure=True, port=8443) == "https://api--feat-a.dev.acme.example:8443"
    assert route.url(secure=False, port=80) == "http://api--feat-a.dev.acme.example"


def test_route_longer_than_a_dns_label_is_refused() -> None:
    long_service = ExposedService(ServiceName("svc"), Port(80), Subdomain("s" * 30))
    with pytest.raises(InvalidValue, match="DNS label"):
        plan_routes(WorktreeName("w" * 40), [long_service], Domain("dev.example.com"))


def test_stack_names_round_trip() -> None:
    name = WorktreeName("feat-a")
    assert stack_project(name) == "wt-feat-a"
    assert worktree_of_stack("wt-feat-a") == name
    assert worktree_of_stack("other-project") is None


def test_host_object_names() -> None:
    names = HostResources(project=ProjectName("acme"))
    assert names.name(Role.BOX) == "outpost-acme-box"
    assert names.box_image("abc") == "outpost-acme-box:abc"


def test_expand_home() -> None:
    assert str(expand_home("~/.outpost", "/home/dev")) == "/home/dev/.outpost"
    assert str(expand_home("/srv/outpost", "/home/dev")) == "/srv/outpost"
    with pytest.raises(InvalidValue):
        expand_home("relative/path", "/home/dev")
