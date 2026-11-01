"""Copies in and out of the container, the `copy` entries of outpost.yaml, and init scripts."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import PurePath, PurePosixPath

from outpost.domain.errors import InvalidValue, Unavailable
from outpost.domain.layout import USER, USER_INIT_DIR
from outpost.domain.transfer import CopyIn, CopyOut, placement
from outpost.launcher.ports.docker import DockerHost
from outpost.launcher.ports.machine import Files

ROOT = "root"


class Transfers:
    def __init__(self, docker: DockerHost, files: Files, container: str) -> None:
        self._docker = docker
        self._files = files
        self._container = container

    def copy(self, operation: CopyIn | CopyOut) -> str:
        """Copy as the container's user; returns where the copy landed."""
        match operation:
            case CopyIn(source=source, destination=destination):
                self._require(source)
                into = destination.into or self._is_container_dir(destination.path)
                directory, name = placement(destination.path, _name(source), into=into)
                return self._copy_in(source, directory, name)
            case CopyOut(source=source, destination=destination):
                into = destination.into or self._files.is_dir(destination.path)
                local_dir, name = placement(destination.path, _name(source), into=into)
                self._docker.copy_out(self._container, source, local_dir, name, user=USER)
                return str(local_dir / name)

    def copy_to(self, source: PurePath, target: PurePosixPath) -> str:
        """Copy to exactly `target`; a folder there receives the folder's content."""
        self._require(source)
        return self._copy_in(source, target.parent, target.name)

    def sync_init(self, scripts: Sequence[PurePath]) -> None:
        """Replace the init scripts in the state volume, numbered in the order given."""
        for script in scripts:
            self._require(script)
        reset = ["sh", "-c", 'rm -rf "$1" && mkdir -p "$1"', "sh", str(USER_INIT_DIR)]
        self._docker.exec(self._container, reset, user=ROOT).check()
        for index, script in enumerate(scripts, start=1):
            name = f"{index:02d}-{script.name}"
            self._docker.copy_in(self._container, script, USER_INIT_DIR, name, user=ROOT)

    def _copy_in(self, source: PurePath, directory: PurePosixPath, name: str) -> str:
        self._docker.copy_in(self._container, source, directory, name, user=USER)
        return f":{directory / name}"

    def _require(self, path: PurePath) -> None:
        if not self._files.exists(path):
            raise Unavailable(f"{path} does not exist on your machine")

    def _is_container_dir(self, path: PurePosixPath) -> bool:
        return self._docker.exec(self._container, ["test", "-d", str(path)], user=USER).ok


def _name(path: PurePath) -> str:
    if not path.name:
        raise InvalidValue(f"{path} has no name to copy; name a file or a folder")
    return path.name
