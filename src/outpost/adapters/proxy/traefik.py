"""Traefik in both roles: the edge on the host (file provider), the router in the box (Docker)."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

import yaml

from outpost.domain.config import EdgeSpec
from outpost.domain.fingerprint import fingerprint
from outpost.domain.resources import ROUTER_PORT, ROUTES_NETWORK, HostLayout, HostResources, Role
from outpost.domain.routes import Route
from outpost.domain.tls import AcmeIssuance, CertificateFiles, Plaintext, TlsMaterial
from outpost.ports.engine import ContainerSpec, Mount, MountKind, PortBinding
from outpost.ports.shell import Shell

TRAEFIK_IMAGE = "traefik:v3"
ROUTER_CONTAINER = "outpost-router"
RESOLVER = "outpost"
CONFIG_DIR = PurePosixPath("/etc/traefik")
DATA_DIR = PurePosixPath("/data")
CERTS_DIR = PurePosixPath("/certs")
CONFIG_LABEL = "outpost.edge-config"

Config = dict[str, Any]


class TraefikEdge:
    def __init__(
        self, host: Shell, resources: HostResources, edge: EdgeSpec, box_container: str
    ) -> None:
        self._host = host
        self._resources = resources
        self._edge = edge
        self._upstream = f"http://{box_container}:{ROUTER_PORT}"

    def prepare(self, layout: HostLayout, material: TlsMaterial) -> ContainerSpec:
        static = _dump(edge_static_config(material))
        dynamic = _dump(edge_dynamic_config(str(self._edge.domain), material, self._upstream))
        self._host.write_file(layout.edge_dir / "traefik.yml", static)
        self._host.write_file(layout.edge_dir / "dynamic" / "outpost.yml", dynamic)
        return ContainerSpec(
            name=self._resources.name(Role.EDGE),
            image=TRAEFIK_IMAGE,
            mounts=self._mounts(layout, material),
            ports=self._ports(material),
            networks=(self._resources.name(Role.EDGE_NETWORK),),
            env_files=_env_files(material),
            labels={CONFIG_LABEL: fingerprint(static)},
        )

    def _mounts(self, layout: HostLayout, material: TlsMaterial) -> tuple[Mount, ...]:
        mounts = [
            Mount(MountKind.BIND, str(layout.edge_dir), CONFIG_DIR, read_only=True),
            Mount(MountKind.VOLUME, self._resources.name(Role.EDGE_DATA), DATA_DIR),
        ]
        if isinstance(material, CertificateFiles):
            mounts.append(
                Mount(MountKind.BIND, str(material.certificate.parent), CERTS_DIR, read_only=True)
            )
        return tuple(mounts)

    def _ports(self, material: TlsMaterial) -> tuple[PortBinding, ...]:
        listen = self._edge.listen
        ports = [PortBinding(listen, int(self._edge.http_port), 80)]
        if not isinstance(material, Plaintext):
            ports.append(PortBinding(listen, int(self._edge.https_port), 443))
        return tuple(ports)


def edge_static_config(material: TlsMaterial) -> Config:
    entry_points: Config = {"web": {"address": ":80"}}
    config: Config = {
        "entryPoints": entry_points,
        "providers": {"file": {"directory": str(CONFIG_DIR / "dynamic"), "watch": True}},
        "log": {"level": "INFO"},
    }
    if isinstance(material, Plaintext):
        return config
    entry_points["websecure"] = {"address": ":443"}
    entry_points["web"]["http"] = {
        "redirections": {"entryPoint": {"to": "websecure", "scheme": "https"}}
    }
    if isinstance(material, AcmeIssuance):
        config["certificatesResolvers"] = {
            RESOLVER: {
                "acme": {
                    "email": material.email,
                    "storage": str(DATA_DIR / "acme.json"),
                    "dnsChallenge": {"provider": material.dns_provider},
                }
            }
        }
    return config


def edge_dynamic_config(domain: str, material: TlsMaterial, upstream: str) -> Config:
    router: Config = {"rule": f"HostRegexp(`^.+\\.{re.escape(domain)}$`)", "service": "box"}
    config: Config = {
        "http": {
            "routers": {"outpost": router},
            "services": {
                "box": {"loadBalancer": {"servers": [{"url": upstream}], "passHostHeader": True}}
            },
        }
    }
    match material:
        case Plaintext():
            router["entryPoints"] = ["web"]
        case CertificateFiles(certificate=certificate, key=key):
            router["entryPoints"] = ["websecure"]
            router["tls"] = {}
            pair = {
                "certFile": str(CERTS_DIR / certificate.name),
                "keyFile": str(CERTS_DIR / key.name),
            }
            config["tls"] = {
                "certificates": [pair],
                "stores": {"default": {"defaultCertificate": pair}},
            }
        case AcmeIssuance():
            router["entryPoints"] = ["websecure"]
            router["tls"] = {
                "certResolver": RESOLVER,
                "domains": [{"main": domain, "sans": [f"*.{domain}"]}],
            }
    return config


def _env_files(material: TlsMaterial) -> tuple[PurePosixPath, ...]:
    return (material.provider_env_file,) if isinstance(material, AcmeIssuance) else ()


def _dump(config: Config) -> str:
    return yaml.safe_dump(config, sort_keys=False)


class TraefikRouter:
    """Stacks declare routes with Traefik labels; the router discovers them on the inner engine."""

    @property
    def network(self) -> str:
        return ROUTES_NETWORK

    def labels(self, route: Route) -> dict[str, str]:
        key = route.key
        return {
            "traefik.enable": "true",
            "traefik.docker.network": ROUTES_NETWORK,
            f"traefik.http.routers.{key}.rule": f"Host(`{route.hostname}`)",
            f"traefik.http.routers.{key}.entrypoints": "web",
            f"traefik.http.routers.{key}.service": key,
            f"traefik.http.services.{key}.loadbalancer.server.port": str(int(route.port)),
        }

    def bootstrap_script(self) -> str:
        return "\n".join(
            [
                f"docker network inspect {ROUTES_NETWORK} >/dev/null 2>&1 \\",
                f"  || docker network create {ROUTES_NETWORK} >/dev/null",
                f"if ! docker container inspect {ROUTER_CONTAINER} >/dev/null 2>&1; then",
                f"  docker run --detach --name {ROUTER_CONTAINER} --restart unless-stopped \\",
                f"    --network {ROUTES_NETWORK} --publish {ROUTER_PORT}:80 \\",
                "    --volume /var/run/docker.sock:/var/run/docker.sock:ro \\",
                f"    {TRAEFIK_IMAGE} \\",
                "    --entrypoints.web.address=:80 \\",
                "    --providers.docker=true \\",
                "    --providers.docker.exposedbydefault=false \\",
                f"    --providers.docker.network={ROUTES_NETWORK} >/dev/null",
                "fi",
            ]
        )
