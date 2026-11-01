from __future__ import annotations

import json
from pathlib import PurePosixPath

import pytest

from outpost.adapters.proxy.traefik import (
    TraefikEdge,
    TraefikRouter,
    edge_dynamic_config,
    edge_static_config,
)
from outpost.adapters.stacks.compose import ComposeStacks, compose_override
from outpost.domain.config import ResolvedConfig
from outpost.domain.errors import InvalidValue
from outpost.domain.names import (
    Domain,
    Port,
    ProjectName,
    ServiceName,
    Subdomain,
    UserName,
    WorktreeName,
)
from outpost.domain.resources import BoxLayout, HostLayout
from outpost.domain.routes import ExposedService, Route, plan_routes
from outpost.domain.tls import AcmeIssuance, CertificateFiles, Plaintext
from outpost.ports.stacks import StackDefinition
from tests.fakes import FakeShell

FEAT = WorktreeName("feat-a")
CERTS = CertificateFiles(
    PurePosixPath("/s/tls/edge/wildcard.crt"), PurePosixPath("/s/tls/edge/wildcard.key")
)
ACME = AcmeIssuance(
    Domain("dev.acme.example"),
    "ops@acme.example",
    "azuredns",
    PurePosixPath("/s/secrets/acme-dns"),
    ("AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"),
)


def _exposed(name: str, port: int) -> ExposedService:
    return ExposedService(ServiceName(name), Port(port), Subdomain(name))


def _routes(name: str = "api") -> tuple[Route, ...]:
    return plan_routes(FEAT, [_exposed(name, 5000)], Domain("dev.x.io"))


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
    assert set(edge_static_config(Plaintext())["entryPoints"]) == {"web"}
    dynamic = edge_dynamic_config("dev.localhost", Plaintext(), "http://box:80")
    assert dynamic["http"]["routers"]["outpost"]["entryPoints"] == ["web"]


def test_edge_sees_only_the_leaf_certificate(wsl: ResolvedConfig) -> None:
    shell = FakeShell()
    edge = TraefikEdge(shell, wsl.resources, wsl.target.edge, "outpost-acme-box")
    spec = edge.prepare(HostLayout(PurePosixPath("/s")), CERTS)
    assert PurePosixPath("/s/edge/traefik.yml") in shell.files
    assert [(port.host_ip, port.host_port) for port in spec.ports] == [
        ("127.0.0.1", 80),
        ("127.0.0.1", 443),
    ]
    certs = next(mount for mount in spec.mounts if str(mount.target) == "/certs")
    assert certs.source == "/s/tls/edge"
    assert certs.read_only


def test_acme_credentials_reach_the_edge_as_files_only(azure: ResolvedConfig) -> None:
    edge = TraefikEdge(FakeShell(), azure.resources, azure.target.edge, "outpost-acme-box")
    spec = edge.prepare(HostLayout(PurePosixPath("/s")), ACME)
    assert spec.env == {
        "AZURE_CLIENT_ID_FILE": "/run/secrets/acme/AZURE_CLIENT_ID",
        "AZURE_CLIENT_SECRET_FILE": "/run/secrets/acme/AZURE_CLIENT_SECRET",
    }
    assert any(mount.source == "/s/secrets/acme-dns" for mount in spec.mounts)


def test_router_runs_on_the_inner_engine_and_reads_labels() -> None:
    router = TraefikRouter()
    (route,) = _routes()
    labels = router.labels(route)
    assert labels["traefik.http.routers.api--feat-a.rule"] == "Host(`api--feat-a.dev.x.io`)"
    assert labels["traefik.http.services.api--feat-a.loadbalancer.server.port"] == "5000"
    spec = router.container()
    assert spec.networks == (router.network,)
    assert "--providers.docker.exposedbydefault=false" in spec.command


def test_override_keeps_declared_networks_and_adds_the_router() -> None:
    resolved = {"services": {"api": {"networks": {"backend": None}}, "migrate": {}}}
    override = compose_override(resolved, _routes(), TraefikRouter())
    assert set(override["services"]) == {"api"}
    assert override["services"]["api"]["networks"] == ["backend", "outpost-routes"]
    assert "restart" not in override["services"]["api"]


def test_override_keeps_the_default_network_when_none_is_declared() -> None:
    override = compose_override({"services": {"api": {}}}, _routes(), TraefikRouter())
    assert override["services"]["api"]["networks"] == ["default", "outpost-routes"]


def test_override_refuses_unknown_exposed_services() -> None:
    with pytest.raises(InvalidValue, match="web"):
        compose_override({"services": {"api": {}}}, _routes("web"), TraefikRouter())


def test_stack_up_remembers_the_stack_and_down_forgets_it() -> None:
    box = FakeShell()
    box.respond("docker", "compose", stdout=json.dumps({"services": {"api": {}}}))
    layout = BoxLayout(ProjectName("acme"), UserName("dev"))
    stacks = ComposeStacks(box, TraefikRouter(), layout)
    directory = PurePosixPath("/workspaces/acme/worktrees/feat-a")
    stacks.up(StackDefinition(FEAT, directory, ("deploy/compose.yaml",), _routes()))
    starter = layout.stacks_dir / "feat-a.up.sh"
    assert "cd /workspaces/acme/worktrees/feat-a && exec docker compose" in box.files[starter]
    assert box.modes[starter] == 0o755
    assert str(layout.stacks_dir) in stacks.boot_script()
    stacks.down(FEAT)
    assert starter not in box.files
