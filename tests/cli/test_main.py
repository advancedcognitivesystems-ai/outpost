from __future__ import annotations

from pathlib import Path

import pytest

from outpost.cli.main import EXIT_CONFIG, EXIT_FAILURE, main
from tests.conftest import EXAMPLE


def test_config_validate_names_the_target(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--config", str(EXAMPLE), "--target", "wsl", "config", "validate"]) == 0
    assert capsys.readouterr().out.strip() == "valid: project acme, target wsl"


def test_invalid_configuration_exits_with_its_own_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "outpost.yaml"
    config.write_text("version: 2\n", encoding="utf-8")
    assert main(["--config", str(config), "config", "validate"]) == EXIT_CONFIG
    assert "only version 1 is supported" in capsys.readouterr().err


def test_bad_worktree_name_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as caught:
        main(["--config", str(EXAMPLE), "stack", "up", "Bad_Name"])
    assert caught.value.code == 2


def test_designed_but_unbuilt_commands_say_so(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--config", str(EXAMPLE), "--dry-run", "up"]) == EXIT_FAILURE
    assert "not built yet" in capsys.readouterr().err


def test_init_writes_the_chosen_target(tmp_path: Path) -> None:
    destination = tmp_path / "outpost.yaml"
    assert main(["--config", str(destination), "--yes", "init"]) == 0
    assert "default_target: wsl" in destination.read_text(encoding="utf-8")
    assert main(["--config", str(destination), "--yes", "init"]) == EXIT_CONFIG
