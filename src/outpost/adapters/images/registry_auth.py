"""Logging the host's engine into a registry, with a credential obtained on the client."""

from __future__ import annotations

from outpost.domain.errors import Unavailable
from outpost.domain.secrets import Secret
from outpost.ports.credentials import SecretSource
from outpost.ports.engine import ContainerEngine
from outpost.ports.shell import Shell

ACR_TOKEN_USER = "00000000-0000-0000-0000-000000000000"
ACR_SUFFIX = ".azurecr.io"


class NoRegistryLogin:
    @property
    def client_commands(self) -> tuple[str, ...]:
        return ()

    def login(self) -> None:
        return None


class DockerRegistryLogin:
    def __init__(
        self, engine: ContainerEngine, registry: str, username: str, password: SecretSource
    ) -> None:
        self._engine = engine
        self._registry = registry
        self._username = username
        self._password = password

    @property
    def client_commands(self) -> tuple[str, ...]:
        return self._password.client_commands

    def login(self) -> None:
        secret = self._password.read()
        if secret is None:
            raise Unavailable(f"no registry password in {self._password.description}")
        self._engine.login(self._registry, self._username, secret)


class AzureAcrLogin:
    """Asks `az` on the client for a short-lived ACR token, then logs the host in with it."""

    def __init__(self, engine: ContainerEngine, client: Shell, registry: str) -> None:
        self._engine = engine
        self._client = client
        self._name = registry.removesuffix(ACR_SUFFIX).split(".")[0]
        self._server = registry if "." in registry else f"{registry}{ACR_SUFFIX}"

    @property
    def client_commands(self) -> tuple[str, ...]:
        return ("az",)

    def login(self) -> None:
        argv = ["az", "acr", "login", "--name", self._name, "--expose-token"]
        result = self._client.run([*argv, "--output", "tsv", "--query", "accessToken"]).check()
        token = result.stdout.strip()
        if not token:
            raise Unavailable(f"`az acr login` returned no token for {self._name}; run `az login`")
        self._engine.login(self._server, ACR_TOKEN_USER, Secret(token))
