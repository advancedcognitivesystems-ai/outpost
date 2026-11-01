"""`outpost.yaml` to `OutpostConfig`. Kinds are dispatched through tables, one per family."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from pathlib import Path

import yaml

from outpost.config.reader import Node
from outpost.domain.config import (
    DEFAULT_SSH_PORT,
    AcmeTls,
    AutoSource,
    AzureAcrAuth,
    BoxSpec,
    CommandSource,
    ConnectionSpec,
    CredentialsSpec,
    DockerLoginAuth,
    EdgeSpec,
    EnvSource,
    FileSource,
    GitIdentity,
    HostSpec,
    ImageSource,
    ImageSpec,
    Isolation,
    KeychainSource,
    LocalCaTls,
    LocalConnection,
    NoRegistryAuth,
    NoTls,
    OutpostConfig,
    ProjectSpec,
    RegistryAuthSpec,
    SecretSourceSpec,
    SshConnection,
    StacksSpec,
    TargetSpec,
    TlsSpec,
    ToolCredentials,
)
from outpost.domain.credentials import Strategy, Tool
from outpost.domain.errors import ConfigError, InvalidValue
from outpost.domain.names import (
    Domain,
    ImageRef,
    Port,
    ProjectName,
    ServiceName,
    Subdomain,
    UserName,
    plain_setting_name,
    variable_name,
)
from outpost.domain.resources import state_path
from outpost.domain.routes import ExposedService

SUPPORTED_VERSION = 1
DEFAULT_GH_TOKEN_ENV = "OUTPOST_GH_TOKEN"


class ConnectionKind(StrEnum):
    LOCAL = "local"
    SSH = "ssh"


class TlsKind(StrEnum):
    ACME = "acme"
    LOCAL_CA = "local-ca"
    NONE = "none"


class RegistryAuthKind(StrEnum):
    NONE = "none"
    DOCKER_LOGIN = "docker-login"
    AZURE_ACR = "azure-acr"


class SourceKind(StrEnum):
    AUTO = "auto"
    FILE = "file"
    KEYCHAIN = "keychain"
    COMMAND = "command"
    ENV = "env"


def load_config(path: Path) -> OutpostConfig:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError("", f"{path} not found; copy outpost.example.yaml to start") from None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ConfigError("", f"{path} is not valid YAML: {error}") from None
    return parse_config(data)


def parse_config(data: object) -> OutpostConfig:
    root = Node(data, "")
    if root.integer("version") != SUPPORTED_VERSION:
        raise ConfigError("version", f"only version {SUPPORTED_VERSION} is supported")
    config = OutpostConfig(
        project=_project(root.child("project")),
        targets={name: _target(name, node) for name, node in root.node_map("targets").items()},
        default_target=root.optional_text("default_target"),
        box=_box(root.child("box")),
        stacks=_stacks(root.child("stacks")),
        credentials=_credentials(root.child("credentials")),
    )
    root.done()
    if config.default_target is not None and config.default_target not in config.targets:
        raise ConfigError("default_target", f"{config.default_target!r} is not a key of targets")
    return config


# ------------------------------------------------------------------ project and targets


def _project(node: Node) -> ProjectSpec:
    spec = ProjectSpec(
        name=node.value("name", ProjectName),
        repository=node.text("repository"),
        default_branch=node.text("default_branch", "main"),
    )
    node.done()
    return spec


def _target(name: str, node: Node) -> TargetSpec:
    image = node.section("image")
    spec = TargetSpec(
        name=name,
        connection=_connection(node.child("connection")),
        host=_host(node.section("host")),
        edge=_edge(node.child("edge")),
        image=_image(image) if image.keys() else None,
    )
    node.done()
    return spec


def _connection(node: Node) -> ConnectionSpec:
    kind = node.choice("kind", ConnectionKind)
    spec = _CONNECTIONS[kind](node)
    node.done()
    return spec


def _ssh(node: Node) -> SshConnection:
    return SshConnection(
        host=node.text("host"),
        user=node.optional_text("user"),
        port=_port(node, "port", int(DEFAULT_SSH_PORT)),
        identity_file=node.optional_text("identity_file"),
    )


_CONNECTIONS: dict[ConnectionKind, Callable[[Node], ConnectionSpec]] = {
    ConnectionKind.LOCAL: lambda _node: LocalConnection(),
    ConnectionKind.SSH: _ssh,
}


def _host(node: Node) -> HostSpec:
    spec = HostSpec(
        isolation=node.choice("isolation", Isolation, Isolation.SYSBOX),
        state_dir=node.value("state_dir", state_path, "~/.outpost"),
        min_free_disk_gb=node.integer("min_free_disk_gb", 50),
    )
    node.done()
    return spec


def _edge(node: Node) -> EdgeSpec:
    ports = node.section("ports")
    spec = EdgeSpec(
        domain=node.value("domain", Domain),
        listen=node.text("listen", "127.0.0.1"),
        http_port=_port(ports, "http", 80),
        https_port=_port(ports, "https", 443),
        tls=_tls(node.section("tls")),
    )
    ports.done()
    node.done()
    return spec


def _tls(node: Node) -> TlsSpec:
    kind = node.choice("kind", TlsKind, TlsKind.LOCAL_CA)
    spec = _TLS[kind](node)
    node.done()
    return spec


_TLS: dict[TlsKind, Callable[[Node], TlsSpec]] = {
    TlsKind.ACME: lambda node: AcmeTls(
        email=node.text("email"),
        dns_provider=node.text("dns_provider"),
        dns_env_file=node.text("dns_env_file"),
    ),
    TlsKind.LOCAL_CA: lambda _node: LocalCaTls(),
    TlsKind.NONE: lambda _node: NoTls(),
}


# ------------------------------------------------------------------ image and box


def _image(node: Node) -> ImageSpec:
    source = node.choice("source", ImageSource)
    auth_node = node.section("registry_auth")
    auth = _registry_auth(auth_node)
    if source is ImageSource.LOCAL and not isinstance(auth, NoRegistryAuth):
        raise ConfigError(auth_node.path, "applies to source: registry only")
    spec = ImageSpec(source=source, ref=node.value("ref", ImageRef), auth=auth)
    node.done()
    return spec


def _registry_auth(node: Node) -> RegistryAuthSpec:
    kind = node.choice("kind", RegistryAuthKind, RegistryAuthKind.NONE)
    spec = _REGISTRY_AUTH[kind](node)
    node.done()
    return spec


_REGISTRY_AUTH: dict[RegistryAuthKind, Callable[[Node], RegistryAuthSpec]] = {
    RegistryAuthKind.NONE: lambda _node: NoRegistryAuth(),
    RegistryAuthKind.DOCKER_LOGIN: lambda node: DockerLoginAuth(
        registry=node.text("registry"),
        username=node.text("username"),
        password_env=_env_name(node, "password_env"),
    ),
    RegistryAuthKind.AZURE_ACR: lambda node: AzureAcrAuth(registry=node.text("registry")),
}


def _box(node: Node) -> BoxSpec:
    memory = node.integer("memory_gb", minimum=1) if node.has("memory_gb") else None
    spec = BoxSpec(
        image=_image(node.child("image")),
        user=node.value("user", UserName, "dev"),
        cpus=node.optional_number("cpus"),
        memory_gb=memory,
        env=_box_env(node),
    )
    node.done()
    return spec


def _box_env(node: Node) -> dict[str, str]:
    env = node.text_map("env")
    for name in env:
        node.check(f"env.{name}", plain_setting_name, name)
    return env


# ------------------------------------------------------------------ stacks


def _stacks(node: Node) -> StacksSpec:
    exposed = tuple(_exposed(item) for item in node.nodes("expose"))
    subdomains = [str(item.subdomain) for item in exposed]
    duplicates = sorted({name for name in subdomains if subdomains.count(name) > 1})
    if duplicates:
        raise ConfigError(node.at("expose"), f"subdomains used twice: {', '.join(duplicates)}")
    spec = StacksSpec(compose_files=node.texts("compose_files"), expose=exposed)
    node.done()
    return spec


def _exposed(node: Node) -> ExposedService:
    service = node.value("service", ServiceName)
    if node.has("subdomain"):
        subdomain = node.value("subdomain", Subdomain)
    else:
        try:
            subdomain = Subdomain(service.value)
        except InvalidValue as error:
            raise ConfigError(node.at("subdomain"), f"needed: {error}") from None
    spec = ExposedService(service=service, port=_port(node, "port"), subdomain=subdomain)
    node.done()
    return spec


# ------------------------------------------------------------------ credentials


def _credentials(node: Node) -> CredentialsSpec:
    claude_node = node.child("claude")
    github_node = node.child("github")
    git_node = node.child("git")
    spec = CredentialsSpec(
        claude=_tool(Tool.CLAUDE, claude_node, {Strategy.COPY, Strategy.LOGIN, Strategy.SKIP}),
        github=_tool(Tool.GITHUB, github_node, set(Strategy)),
        setup_git=github_node.flag("setup_git", True),
        git=GitIdentity(
            user_name=git_node.text("user_name"), user_email=git_node.text("user_email")
        ),
    )
    for child in (claude_node, github_node, git_node, node):
        child.done()
    return spec


def _tool(tool: Tool, node: Node, allowed: set[Strategy]) -> ToolCredentials:
    strategy = node.choice("strategy", Strategy, Strategy.COPY)
    if strategy not in allowed:
        names = ", ".join(sorted(item.value for item in allowed))
        raise ConfigError(node.at("strategy"), f"must be one of: {names}")
    source = _source(node.section("source"))
    if tool is Tool.GITHUB:
        token_env = _env_name(node, "token_env", DEFAULT_GH_TOKEN_ENV)
        if strategy is Strategy.TOKEN:
            source = EnvSource(token_env)
    return ToolCredentials(tool=tool, strategy=strategy, source=source)


def _source(node: Node) -> SecretSourceSpec:
    kind = node.choice("kind", SourceKind, SourceKind.AUTO)
    spec = _SOURCES[kind](node)
    node.done()
    return spec


_SOURCES: dict[SourceKind, Callable[[Node], SecretSourceSpec]] = {
    SourceKind.AUTO: lambda _node: AutoSource(),
    SourceKind.FILE: lambda node: FileSource(path=node.text("path")),
    SourceKind.KEYCHAIN: lambda node: KeychainSource(
        service=node.text("service"), account=node.optional_text("account")
    ),
    SourceKind.COMMAND: lambda node: CommandSource(argv=node.texts("command")),
    SourceKind.ENV: lambda node: EnvSource(name=_env_name(node, "name")),
}


# ------------------------------------------------------------------ shared field rules


def _port(node: Node, key: str, default: int | None = None) -> Port:
    try:
        return Port(node.integer(key, default, minimum=1))
    except InvalidValue as error:
        raise ConfigError(node.at(key), str(error)) from None


def _env_name(node: Node, key: str, default: str | None = None) -> str:
    return node.value(key, variable_name, default)
