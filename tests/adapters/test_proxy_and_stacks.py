from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from outpost.adapters.proxy.traefik import (
    TraefikEdge,
    TraefikRouter,
    edge_dynamic_config,
    edge_static_config,
)
from outpost.adapters.stacks.compose import compose_override
from outpost.domain.config import ResolvedConfig
from outpost.domain.errors import InvalidValue
from outpost.domain.names import Domain, Port, ServiceName, Subdomain, WorktreeName
from outpost.domain.resources import HostLayout
from outpost.domain.routes import ExposedService, plan_routes
from outpost.domain.tls import AcmeIssuance, CertificateFiles, Plaintext
from tests.fakes import FakeShell

CERTS = CertificateFiles(PurePosixPath("/s/tls/wildcard.crt"), PurePosixPath("/s/tls/wildcard.key"))
ACME = AcmeIssuance(
    Domain("dev.acme.example"), "ops@acme.example", "azuredns", PurePosixPath("/s/dns.env")
)


def test_edge_catches_every_name_under_the_domain() -> None:
    config = edge_dynamic_config("dev.acme.example", CERTS, "http://box:80")
    router = config["http"]["routers"]["outpost"]
    assert router["rule"] == "HostRegexp(`^.+\\.dev\\.acme\\.example$`)"
    assert router["entryPoints"] == ["websecure"]
    assert config["tls"]["certificates"] == [
        {"certFile": "/certs/wildcard.crt", "keyFile": "/certs/wildcard.key"}
    ]


def test_acme_asks_for_one_wildcard_certificate() -> None:
    router = edge_dynamic_config("dev.acme.example", ACME, "http://box:80")["http"]["routers"]
    assert router["outpost"]["tls"]["domains"] == [
        {"main": "dev.acme.example", "sans": ["*.dev.acme.example"]}
    ]
    resolver = edge_static_config(ACME)["certificatesResolvers"]["outpost"]["acme"]
    assert resolver["dnsChallenge"] == {"provider": "azuredns"}


def test_plaintext_serves_http_only() -> None:
    static = edge_static_config(Plaintext())
    assert set(static["entryPoints"]) == {"web"}
    dynamic = edge_dynamic_config("dev.localhost", Plaintext(), "http://box:80")
    assert dynamic["http"]["routers"]["outpost"]["entryPoints"] == ["web"]


def test_edge_container_mounts_its_config_and_certificates(wsl: ResolvedConfig) -> None:
    shell = FakeShell()
    edge = TraefikEdge(shell, wsl.resources, wsl.target.edge, "outpost-acme-box")
    spec = edge.prepare(HostLayout(PurePosixPath("/s")), CERTS)
    assert PurePosixPath("/s/edge/traefik.yml") in shell.files
    assert spec.name == "outpost-acme-edge"
    assert [(port.host_ip, port.host_port) for port in spec.ports] == [
        ("127.0.0.1", 80),
        ("127.0.0.1", 443),
    ]
    assert any(str(mount.target) == "/certs" for mount in spec.mounts)


def test_router_labels_declare_one_route() -> None:
    (route,) = plan_routes(WorktreeName("feat-a"), [_exposed("api", 5000)], Domain("dev.x.io"))
    labels = TraefikRouter().labels(route)
    assert labels["traefik.http.routers.api--feat-a.rule"] == "Host(`api--feat-a.dev.x.io`)"
    assert labels["traefik.http.services.api--feat-a.loadbalancer.server.port"] == "5000"
    assert "outpost-routes" in TraefikRouter().bootstrap_script()


def test_compose_override_restarts_everything_and_routes_exposed_services() -> None:
    routes = plan_routes(WorktreeName("feat-a"), [_exposed("api", 5000)], Domain("dev.x.io"))
    override = compose_override(["api", "db"], routes, TraefikRouter())
    assert override["services"]["db"] == {"restart": "unless-stopped"}
    assert override["services"]["api"]["networks"] == ["default", "outpost-routes"]
    assert override["networks"]["outpost-routes"] == {"external": True, "name": "outpost-routes"}


def test_compose_override_refuses_unknown_exposed_services() -> None:
    routes = plan_routes(WorktreeName("feat-a"), [_exposed("web", 80)], Domain("dev.x.io"))
    with pytest.raises(InvalidValue, match="web"):
        compose_override(["api"], routes, TraefikRouter())


def _exposed(name: str, port: int) -> ExposedService:
    return ExposedService(ServiceName(name), Port(port), Subdomain(name))
