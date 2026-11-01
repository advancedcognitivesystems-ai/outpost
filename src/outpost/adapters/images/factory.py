"""Image source and registry auth kinds to adapters."""

from __future__ import annotations

from collections.abc import Mapping

from outpost.adapters.credentials.sources import EnvSecret
from outpost.adapters.images.registry_auth import (
    AzureAcrLogin,
    DockerRegistryLogin,
    NoRegistryLogin,
)
from outpost.adapters.images.suppliers import ClientImages, RegistryImages
from outpost.domain.config import (
    AzureAcrAuth,
    DockerLoginAuth,
    ImageSource,
    ImageSpec,
    NoRegistryAuth,
    RegistryAuthSpec,
)
from outpost.ports.engine import ContainerEngine
from outpost.ports.images import ImageSupplier, RegistryAuth
from outpost.ports.shell import Shell


def build_image_supplier(
    image: ImageSpec,
    *,
    client: Shell,
    client_engine: ContainerEngine,
    host: Shell,
    host_engine: ContainerEngine,
    same_machine: bool,
    environ: Mapping[str, str],
) -> ImageSupplier:
    match image.source:
        case ImageSource.REGISTRY:
            auth = build_registry_auth(image.auth, client, host_engine, environ)
            return RegistryImages(host_engine, auth)
        case ImageSource.LOCAL:
            return ClientImages(client_engine, host_engine, host, same_machine=same_machine)


def build_registry_auth(
    spec: RegistryAuthSpec, client: Shell, host_engine: ContainerEngine, environ: Mapping[str, str]
) -> RegistryAuth:
    match spec:
        case NoRegistryAuth():
            return NoRegistryLogin()
        case DockerLoginAuth(registry=registry, username=username, password_env=password_env):
            return DockerRegistryLogin(
                host_engine, registry, username, EnvSecret(password_env, environ)
            )
        case AzureAcrAuth(registry=registry):
            return AzureAcrLogin(host_engine, client, registry)
