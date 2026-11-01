"""`./outpost` end to end, where no Docker is needed: exit codes and printed text."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from outpost.launcher.cli.main import main

REPOSITORY = Path(__file__).resolve().parents[2]


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OUTPOST_HOME", str(REPOSITORY))
    monkeypatch.delenv("OUTPOST_CONFIG", raising=False)
    return tmp_path


def test_config_prints_the_devcontainer_json(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (project / "outpost.yaml").write_text("name: demo\nport: 9443\n", encoding="utf-8")
    assert main(["config"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["name"] == "outpost-demo"
    assert "127.0.0.1:9443:443" in document["runArgs"]
    assert str(document["image"]).startswith("outpost/base:")


def test_configuration_errors_exit_2_and_name_the_key(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (project / "outpost.yaml").write_text(
        "devcontainer:\n  runArgs: ['-v', '/x:/y']\n", encoding="utf-8"
    )
    assert main(["config"]) == 2
    assert "devcontainer.runArgs[0]: -v is refused" in capsys.readouterr().err


def test_a_copy_needs_one_container_side(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["cp", "a.md", "b.md"]) == 2
    assert "one side starts with ':'" in capsys.readouterr().err
