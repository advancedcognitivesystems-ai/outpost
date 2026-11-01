from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from outpost.config import load_config, parse_config
from outpost.domain.config import (
    AcmeTls,
    AzureAcrAuth,
    CommandSource,
    EnvSource,
    ImageSource,
    Isolation,
    LocalCaTls,
    LocalConnection,
    OutpostConfig,
    SshConnection,
)
from outpost.domain.credentials import Strategy
from outpost.domain.errors import ConfigError
from tests.conftest import EXAMPLE


def _example_data() -> dict[str, Any]:
    data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _parse_with(change: Any) -> OutpostConfig:
    data = copy.deepcopy(_example_data())
    change(data)
    return parse_config(data)


def test_example_loads_both_targets(example: OutpostConfig) -> None:
    assert set(example.targets) == {"wsl", "azure"}
    assert example.default_target == "azure"
    assert str(example.project.name) == "acme"


def test_wsl_target_is_local_with_a_local_image(example: OutpostConfig) -> None:
    wsl = example.resolve("wsl")
    assert isinstance(wsl.target.connection, LocalConnection)
    assert wsl.target.runs_on_client
    assert wsl.target.host.isolation is Isolation.PRIVILEGED
    assert isinstance(wsl.target.edge.tls, LocalCaTls)
    assert wsl.box.image.source is ImageSource.LOCAL
    assert str(wsl.box.image.ref) == "acme/dotnet-dev:latest"


def test_azure_target_uses_ssh_acme_and_acr(example: OutpostConfig) -> None:
    azure = example.resolve()
    assert isinstance(azure.target.connection, SshConnection)
    assert int(azure.target.connection.port) == 22
    assert isinstance(azure.target.edge.tls, AcmeTls)
    assert isinstance(azure.box.image.auth, AzureAcrAuth)
    assert azure.target.edge.public_port == 443


def test_stacks_and_credentials(example: OutpostConfig) -> None:
    exposed = {str(item.subdomain): int(item.port) for item in example.stacks.expose}
    assert exposed == {"web": 8080, "api": 5000, "auth": 5001}
    assert example.credentials.github.strategy is Strategy.COPY
    assert example.credentials.github.source == CommandSource(argv=("gh", "auth", "token"))
    assert example.credentials.setup_git


def test_unknown_target_is_named() -> None:
    with pytest.raises(ConfigError, match="known targets: azure, wsl"):
        load_config(EXAMPLE).resolve("aws")


@pytest.mark.parametrize(
    ("change", "path"),
    [
        (lambda d: d["project"].update(nmae="typo"), "project"),
        (lambda d: d["targets"]["wsl"]["edge"].pop("domain"), "targets.wsl.edge.domain"),
        (
            lambda d: d["targets"]["wsl"]["host"].update(isolation="vm"),
            "targets.wsl.host.isolation",
        ),
        (lambda d: d["box"]["env"].update(GH_TOKEN="x"), "box.env.GH_TOKEN"),
        (
            lambda d: d["credentials"]["claude"].update(strategy="token"),
            "credentials.claude.strategy",
        ),
        (lambda d: d["stacks"]["expose"][1].update(subdomain="web"), "stacks.expose"),
        (lambda d: d["targets"]["azure"]["connection"].update(port=70000), "connection.port"),
        (lambda d: d.update(default_target="aws"), "default_target"),
        (lambda d: d["box"].update(user="Root User"), "box.user"),
        (lambda d: d["targets"]["wsl"]["host"].update(state_dir="relative"), "host.state_dir"),
        (
            lambda d: d["targets"]["wsl"]["image"].update(registry_auth={"kind": "azure-acr"}),
            "targets.wsl.image.registry_auth",
        ),
    ],
)
def test_errors_name_the_key_at_fault(change: Any, path: str) -> None:
    with pytest.raises(ConfigError) as caught:
        _parse_with(change)
    assert path in caught.value.path


def test_github_token_strategy_reads_the_configured_variable() -> None:
    config = _parse_with(
        lambda d: d["credentials"]["github"].update(strategy="token", token_env="MY_PAT")
    )
    assert config.credentials.github.source == EnvSource("MY_PAT")


def test_target_image_replaces_box_image(example: OutpostConfig) -> None:
    assert example.resolve("azure").box.image.source is ImageSource.REGISTRY
    assert example.resolve("wsl").box.image.source is ImageSource.LOCAL


def test_missing_file_and_bad_yaml(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "outpost.yaml")
    broken = tmp_path / "broken.yaml"
    broken.write_text("version: [1", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_config(broken)
