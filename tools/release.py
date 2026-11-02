"""Releases: `prepare X.Y.Z` turns Unreleased into that version, `notes vX.Y.Z` checks a tag.

The version lives in pyproject.toml only, and CHANGELOG.md has one section per version.
`prepare` writes the release commit's changes; the release workflow runs `notes` on the tag
and publishes what it prints. Standard library only, so the workflow runs it without uv.
"""

from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNRELEASED = "## [Unreleased]"
SEMVER = re.compile(r"\d+\.\d+\.\d+")
HEADING = re.compile(r"^## \[(?P<name>[^\]]+)\]", re.MULTILINE)
PROJECT_VERSION = re.compile(r'^version = "[^"]*"$', re.MULTILINE)


class ReleaseError(Exception):
    pass


def project_version(pyproject: str) -> str:
    version = tomllib.loads(pyproject)["project"]["version"]
    if not isinstance(version, str):
        raise ReleaseError("pyproject.toml has no project version")
    return version


def section(changelog: str, name: str) -> str:
    """The body of a CHANGELOG section, such as `Unreleased` or `0.3.0`, without its heading."""
    headings = list(HEADING.finditer(changelog))
    for index, heading in enumerate(headings):
        if heading["name"] == name:
            start = changelog.index("\n", heading.end()) + 1
            end = headings[index + 1].start() if index + 1 < len(headings) else len(changelog)
            return changelog[start:end].strip()
    raise ReleaseError(f"CHANGELOG.md has no section {name}")


def notes(tag: str, pyproject: str, changelog: str) -> str:
    """The release notes of `tag`, which must name the project's version."""
    version = project_version(pyproject)
    if tag != f"v{version}":
        raise ReleaseError(f"the tag {tag} does not name the version {version}; tag v{version}")
    body = section(changelog, version)
    if not body:
        raise ReleaseError(f"the section {version} of CHANGELOG.md is empty")
    return body + "\n"


def prepared(version: str, today: datetime.date, pyproject: str, changelog: str) -> tuple[str, str]:
    """pyproject.toml and CHANGELOG.md for releasing `version`, from their current text."""
    if not SEMVER.fullmatch(version):
        raise ReleaseError(f"{version} is not a version such as 0.3.0")
    current = project_version(pyproject)
    if _parts(version) <= _parts(current):
        raise ReleaseError(f"{version} does not follow the current version {current}")
    if not section(changelog, "Unreleased"):
        raise ReleaseError("the Unreleased section of CHANGELOG.md is empty: nothing to release")
    heading = f"{UNRELEASED}\n\n## [{version}] - {today.isoformat()}"
    return (
        PROJECT_VERSION.sub(f'version = "{version}"', pyproject, count=1),
        changelog.replace(UNRELEASED, heading, 1),
    )


def _parts(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(
        prog="tools.release", description="Prepare and check releases."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare", help="release Unreleased as VERSION").add_argument("version")
    sub.add_parser("notes", help="check TAG and print its notes").add_argument("tag")
    args = parser.parse_args(argv)
    pyproject_file, changelog_file = root / "pyproject.toml", root / "CHANGELOG.md"
    pyproject = pyproject_file.read_text(encoding="utf-8")
    changelog = changelog_file.read_text(encoding="utf-8")
    try:
        if args.command == "notes":
            sys.stdout.write(notes(args.tag, pyproject, changelog))
            return 0
        today = datetime.date.today()
        new_pyproject, new_changelog = prepared(args.version, today, pyproject, changelog)
    except ReleaseError as error:
        print(f"release: {error}", file=sys.stderr)
        return 1
    pyproject_file.write_text(new_pyproject, encoding="utf-8")
    changelog_file.write_text(new_changelog, encoding="utf-8")
    subprocess.run(["uv", "lock", "--quiet"], cwd=root, check=True)
    print(f"release: {args.version} prepared; commit it as `chore(release): {args.version}`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
