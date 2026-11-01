"""`outpost.yaml` into an `Environment`. Every key is optional; no file means every default."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import yaml

from outpost.domain.credentials import Tool
from outpost.domain.devcontainer import DevContainerSettings
from outpost.domain.environment import Environment, FileCopy
from outpost.domain.errors import ConfigError, InvalidValue
from outpost.domain.host import LOCAL, parse_host
from outpost.domain.layout import DEFAULT_DOMAIN, DEFAULT_NAME, DEFAULT_PORT
from outpost.domain.names import DnsName, EnvironmentName, port_number
from outpost.domain.routes import Site
from outpost.domain.transfer import container_path
from outpost.domain.volumes import persist_path
from outpost.launcher.config.reader import Node

CONFIG_FILE = "outpost.yaml"
CONFIG_VARIABLE = "OUTPOST_CONFIG"


def locate(explicit: Path | None, environ: Mapping[str, str], cwd: Path) -> Path | None:
    """`--config`, else `$OUTPOST_CONFIG`, else `./outpost.yaml` when it exists."""
    chosen = explicit or (Path(environ[CONFIG_VARIABLE]) if environ.get(CONFIG_VARIABLE) else None)
    if chosen is not None:
        if not chosen.is_file():
            raise ConfigError("", f"{chosen} does not exist")
        return chosen
    default = cwd / CONFIG_FILE
    return default if default.is_file() else None


def load(path: Path | None, cwd: Path) -> Environment:
    if path is None:
        return Environment(root=cwd)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ConfigError("", f"{path} is not valid YAML: {error}") from None
    return parse(data, root=path.resolve().parent)


def parse(data: object, root: Path) -> Environment:
    node = Node(data, "")
    environment = Environment(
        root=root,
        name=node.value("name", EnvironmentName, DEFAULT_NAME),
        host=node.value("host", parse_host, LOCAL),
        site=Site(
            node.value("domain", DnsName, DEFAULT_DOMAIN),
            node.check("port", port_number, node.integer("port", DEFAULT_PORT)),
        ),
        devcontainer=DevContainerSettings.parse(node.raw("devcontainer"), node.at("devcontainer")),
        init_scripts=tuple(_client_path(root, item) for item in node.texts("init")),
        credentials=_credentials(node),
        copies=tuple(
            FileCopy(_client_path(root, source), node.check("copy", container_path, target))
            for source, target in node.text_map("copy").items()
        ),
        persist=tuple(node.check("persist", persist_path, item) for item in node.texts("persist")),
    )
    node.done()
    try:
        environment.volumes  # noqa: B018 - checks that persisted paths do not collide
    except InvalidValue as error:
        raise ConfigError("persist", str(error)) from None
    return environment


def _credentials(node: Node) -> tuple[Tool, ...]:
    names = node.texts("credentials", tuple(tool.value for tool in Tool))
    tools = tuple(node.check("credentials", _tool, name) for name in names)
    return tuple(dict.fromkeys(tools))


def _tool(name: str) -> Tool:
    try:
        return Tool(name)
    except ValueError:
        allowed = ", ".join(tool.value for tool in Tool)
        raise InvalidValue(f"{name!r} is not a login Outpost carries: use {allowed}") from None


def _client_path(root: Path, text: str) -> Path:
    path = Path(text).expanduser()
    return path if path.is_absolute() else root / path
