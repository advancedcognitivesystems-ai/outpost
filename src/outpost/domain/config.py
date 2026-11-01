"""The configuration as typed values. `config/` builds it from YAML; everything else reads it."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum

from outpost.domain.credentials import Strategy, Tool
from outpost.domain.errors import ConfigError
from outpost.domain.names import Domain, ImageRef, Port, ProjectName, UserName
from outpost.domain.resources import BoxLayout, HostResources
from outpost.domain.routes import ExposedService

# ------------------------------------------------------------------ connection

DEFAULT_SSH_PORT = Port(22)


@dataclass(frozen=True)
class LocalConnection:
    """Outpost runs on the host itself, for example inside a WSL distro."""


@dataclass(frozen=True)
class SshConnection:
    host: str
    user: str | None = None
    port: Port = DEFAULT_SSH_PORT
    identity_file: str | None = None


ConnectionSpec = LocalConnection | SshConnection

# ------------------------------------------------------------------ host


class Isolation(StrEnum):
    SYSBOX = "sysbox"
    PRIVILEGED = "privileged"


@dataclass(frozen=True)
class HostSpec:
    isolation: Isolation
    state_dir: str
    min_free_disk_gb: int


# ------------------------------------------------------------------ edge and TLS


@dataclass(frozen=True)
class AcmeTls:
    email: str
    dns_provider: str
    dns_env_file: str


@dataclass(frozen=True)
class LocalCaTls:
    pass


@dataclass(frozen=True)
class NoTls:
    pass


TlsSpec = AcmeTls | LocalCaTls | NoTls


@dataclass(frozen=True)
class EdgeSpec:
    domain: Domain
    listen: str
    http_port: Port
    https_port: Port
    tls: TlsSpec

    @property
    def secure(self) -> bool:
        return not isinstance(self.tls, NoTls)

    @property
    def public_port(self) -> int:
        return int(self.https_port if self.secure else self.http_port)


# ------------------------------------------------------------------ images


class ImageSource(StrEnum):
    REGISTRY = "registry"
    LOCAL = "local"


@dataclass(frozen=True)
class NoRegistryAuth:
    pass


@dataclass(frozen=True)
class DockerLoginAuth:
    registry: str
    username: str
    password_env: str


@dataclass(frozen=True)
class AzureAcrAuth:
    registry: str


RegistryAuthSpec = NoRegistryAuth | DockerLoginAuth | AzureAcrAuth


@dataclass(frozen=True)
class ImageSpec:
    source: ImageSource
    ref: ImageRef
    auth: RegistryAuthSpec = NoRegistryAuth()


# ------------------------------------------------------------------ box and stacks


@dataclass(frozen=True)
class BoxSpec:
    image: ImageSpec
    user: UserName
    cpus: float | None
    memory_gb: int | None
    env: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class StacksSpec:
    compose_files: tuple[str, ...]
    expose: tuple[ExposedService, ...]


# ------------------------------------------------------------------ credentials


@dataclass(frozen=True)
class AutoSource:
    """The usual place for this tool on this client."""


@dataclass(frozen=True)
class FileSource:
    path: str


@dataclass(frozen=True)
class KeychainSource:
    service: str
    account: str | None = None


@dataclass(frozen=True)
class CommandSource:
    argv: tuple[str, ...]


@dataclass(frozen=True)
class EnvSource:
    name: str


SecretSourceSpec = AutoSource | FileSource | KeychainSource | CommandSource | EnvSource


@dataclass(frozen=True)
class ToolCredentials:
    """How one tool's credential reaches the box. `source` is what `copy` or `token` reads."""

    tool: Tool
    strategy: Strategy
    source: SecretSourceSpec


@dataclass(frozen=True)
class GitIdentity:
    user_name: str
    user_email: str


@dataclass(frozen=True)
class CredentialsSpec:
    claude: ToolCredentials
    github: ToolCredentials
    setup_git: bool
    git: GitIdentity

    @property
    def tools(self) -> tuple[ToolCredentials, ...]:
        return (self.claude, self.github)


# ------------------------------------------------------------------ whole file


@dataclass(frozen=True)
class ProjectSpec:
    name: ProjectName
    repository: str
    default_branch: str


@dataclass(frozen=True)
class TargetSpec:
    name: str
    connection: ConnectionSpec
    host: HostSpec
    edge: EdgeSpec
    image: ImageSpec | None = None

    @property
    def runs_on_client(self) -> bool:
        """True when Outpost runs on the host itself, so the client and host are one machine."""
        return isinstance(self.connection, LocalConnection)


@dataclass(frozen=True)
class ResolvedConfig:
    """The configuration for one target: what every use case works with."""

    project: ProjectSpec
    target: TargetSpec
    box: BoxSpec
    stacks: StacksSpec
    credentials: CredentialsSpec

    @property
    def resources(self) -> HostResources:
        return HostResources(self.project.name)

    @property
    def box_layout(self) -> BoxLayout:
        return BoxLayout(self.project.name, self.box.user)


@dataclass(frozen=True)
class OutpostConfig:
    project: ProjectSpec
    targets: Mapping[str, TargetSpec]
    default_target: str | None
    box: BoxSpec
    stacks: StacksSpec
    credentials: CredentialsSpec

    def resolve(self, target: str | None = None) -> ResolvedConfig:
        """Pick a target: the one asked for, else `default_target`, else the only one."""
        name = target or self.default_target
        if name is None:
            if len(self.targets) != 1:
                raise ConfigError(
                    "default_target", "several targets exist; set one or pass --target"
                )
            name = next(iter(self.targets))
        if name not in self.targets:
            known = ", ".join(sorted(self.targets))
            raise ConfigError("targets", f"no target named {name!r}; known targets: {known}")
        chosen = self.targets[name]
        box = self.box if chosen.image is None else replace(self.box, image=chosen.image)
        return ResolvedConfig(self.project, chosen, box, self.stacks, self.credentials)
