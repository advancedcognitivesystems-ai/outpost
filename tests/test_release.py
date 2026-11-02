"""The release tool: one version in pyproject.toml, one changelog section per version."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from outpost.launcher.cli.main import build_parser
from tools.release import ReleaseError, notes, prepared, project_version, section

ROOT = Path(__file__).resolve().parents[1]
DAY = datetime.date(2026, 11, 2)
PYPROJECT = (
    '[project]\nname = "outpost"\nversion = "0.2.0"\n\n[tool.ruff]\ntarget-version = "py312"\n'
)
CHANGELOG = """# Changelog

## [Unreleased]

### Added

- Something new.

## [0.2.0] - 2026-11-01

### Added

- The framework.
"""


def test_the_version_has_its_changelog_section() -> None:
    version = project_version((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert section((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), version)


def test_the_launcher_reports_the_projects_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--version"])
    version = project_version((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert capsys.readouterr().out.strip() == f"outpost {version}"


def test_prepare_moves_unreleased_under_the_version() -> None:
    pyproject, changelog = prepared("0.3.0", DAY, PYPROJECT, CHANGELOG)
    assert project_version(pyproject) == "0.3.0"
    assert 'target-version = "py312"' in pyproject
    assert section(changelog, "Unreleased") == ""
    assert section(changelog, "0.3.0") == "### Added\n\n- Something new."
    assert "## [0.3.0] - 2026-11-02" in changelog
    assert section(changelog, "0.2.0") == "### Added\n\n- The framework."


@pytest.mark.parametrize(
    ("version", "changelog", "message"),
    [
        ("0.3", CHANGELOG, "not a version"),
        ("0.2.0", CHANGELOG, "does not follow"),
        ("0.1.9", CHANGELOG, "does not follow"),
        ("0.3.0", CHANGELOG.replace("### Added\n\n- Something new.\n\n", "", 1), "nothing"),
    ],
)
def test_prepare_refuses(version: str, changelog: str, message: str) -> None:
    with pytest.raises(ReleaseError, match=message):
        prepared(version, DAY, PYPROJECT, changelog)


def test_a_tag_gets_its_versions_section_as_notes() -> None:
    assert notes("v0.2.0", PYPROJECT, CHANGELOG) == "### Added\n\n- The framework.\n"


@pytest.mark.parametrize("tag", ["0.2.0", "v0.3.0", "v0.2.0-rc1"])
def test_a_tag_must_name_the_version(tag: str) -> None:
    with pytest.raises(ReleaseError, match="does not name"):
        notes(tag, PYPROJECT, CHANGELOG)


def test_a_version_without_its_section_is_not_released() -> None:
    with pytest.raises(ReleaseError, match=r"no section 0\.2\.0"):
        notes("v0.2.0", PYPROJECT, CHANGELOG.split("## [0.2.0]")[0])
