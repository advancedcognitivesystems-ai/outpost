"""`outpost.yaml`: every key optional, every error at its key, the example always loading."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from outpost.domain.credentials import Tool
from outpost.domain.errors import ConfigError
from outpost.domain.host import LocalHost, SshHost
from outpost.domain.names import EnvironmentName
from outpost.launcher.config.loader import load, locate, parse

REPOSITORY = Path(__file__).resolve().parents[2]


def test_no_file_means_every_default(tmp_path: Path) -> None:
    assert locate(None, {}, tmp_path) is None
    environment = load(None, tmp_path)
    assert environment.name == EnvironmentName("main")
    assert environment.host == LocalHost()
    assert environment.site.url_pattern() == "https://<route>.dev.localhost:8443"
    assert environment.credentials == (Tool.CLAUDE, Tool.GITHUB)
    assert environment.root == tmp_path


def test_an_empty_file_is_every_default(tmp_path: Path) -> None:
    (tmp_path / "outpost.yaml").write_text("", encoding="utf-8")
    path = locate(None, {}, tmp_path)
    assert path == tmp_path / "outpost.yaml"
    assert load(path, tmp_path).name == EnvironmentName("main")


def test_the_example_loads() -> None:
    environment = load(REPOSITORY / "outpost.example.yaml", REPOSITORY)
    assert environment.host == SshHost("my-vm", "dev")
    assert environment.init_scripts == (REPOSITORY / "scripts/clone-platform.sh",)
    assert environment.copies[0].source == Path.home() / ".npmrc"
    assert environment.copies[0].target == PurePosixPath("/home/dev/.npmrc")
    assert environment.persist == (PurePosixPath("/opt/tools"),)


def test_the_variable_or_the_option_picks_the_file(tmp_path: Path) -> None:
    chosen = tmp_path / "other.yaml"
    chosen.write_text("name: other\n", encoding="utf-8")
    assert locate(None, {"OUTPOST_CONFIG": str(chosen)}, tmp_path) == chosen
    assert locate(chosen, {}, tmp_path) == chosen
    with pytest.raises(ConfigError, match="does not exist"):
        locate(tmp_path / "missing.yaml", {}, tmp_path)


@pytest.mark.parametrize(
    ("data", "path"),
    [
        ({"nmae": "x"}, "outpost.yaml"),
        ({"name": "Main"}, "name"),
        ({"host": "http://vm"}, "host"),
        ({"domain": "Dev"}, "domain"),
        ({"port": 0}, "port"),
        ({"port": "8443"}, "port"),
        ({"credentials": ["claude", "aws"]}, "credentials"),
        ({"copy": {"~/.npmrc": "relative/path"}}, "copy"),
        ({"persist": ["/home/dev/x"]}, "persist"),
        ({"persist": ["/opt", "/opt/x"]}, "persist"),
        ({"init": ["ok.sh", ""]}, "init[1]"),
        ({"devcontainer": {"mounts": []}}, "devcontainer.mounts"),
        (["not", "a", "mapping"], ""),
    ],
)
def test_errors_name_their_key(data: object, path: str, tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as caught:
        parse(data, tmp_path)
    assert caught.value.path == path


def test_credentials_can_be_turned_off(tmp_path: Path) -> None:
    assert parse({"credentials": []}, tmp_path).credentials == ()
    assert parse({"credentials": ["gh", "gh"]}, tmp_path).credentials == (Tool.GITHUB,)
