"""`outpost` inside the container: arguments, exit codes, printed text."""

from __future__ import annotations

import pytest

from outpost.container.cli.main import build_parser, main


def test_usage_errors_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["route", "add", "API", "x:80"]) == 2
    assert "not a DNS name" in capsys.readouterr().err
    assert main(["route", "add", "api", "x"]) == 2
    assert "container:port or devcontainer:port" in capsys.readouterr().err


def test_every_command_is_reachable() -> None:
    parser = build_parser()
    for argv in (
        ["route", "add", "api.feat-a", "feat-a-api-1:8080"],
        ["route", "rm", "*.feat-a"],
        ["route", "ls", "--json"],
        ["proxy", "start"],
        ["ca"],
        ["status", "--json"],
        ["boot"],
        ["init", "--if-changed"],
    ):
        assert callable(parser.parse_args(argv).handler)
