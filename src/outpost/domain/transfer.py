"""Copies between your machine and the container: the only way files cross, in both directions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath, PurePosixPath

from outpost.domain.errors import InvalidValue
from outpost.domain.layout import HOME

CONTAINER_PREFIX = ":"
_INTO = ("", ".", "..", "~")


def container_path(text: str) -> PurePosixPath:
    """A path in the container: absolute, or under the home directory with `~`."""
    path = HOME / text[2:] if text == "~" or text.startswith("~/") else PurePosixPath(text)
    if not path.is_absolute() or ".." in path.parts:
        raise InvalidValue(f"{text!r} must be absolute or start with ~/, without '..'")
    return path


@dataclass(frozen=True)
class ContainerEndpoint:
    path: PurePosixPath
    into: bool
    """True when the text names a directory to copy into (it ends with `/`)."""


@dataclass(frozen=True)
class ClientEndpoint:
    path: PurePath
    into: bool


type Endpoint = ContainerEndpoint | ClientEndpoint


def parse_endpoint(text: str, *, client: type[PurePath] = PurePath) -> Endpoint:
    """`:path` is in the container; anything else is on your machine."""
    if text.startswith(CONTAINER_PREFIX):
        raw = text[len(CONTAINER_PREFIX) :]
        return ContainerEndpoint(container_path(raw), into=raw.endswith("/") or raw == "~")
    if not text:
        raise InvalidValue("a path on your machine cannot be empty")
    return ClientEndpoint(client(text), into=text.endswith("/") or text in _INTO)


@dataclass(frozen=True)
class CopyIn:
    source: PurePath
    destination: ContainerEndpoint


@dataclass(frozen=True)
class CopyOut:
    source: PurePosixPath
    destination: ClientEndpoint


def parse_copy(source: str, destination: str) -> CopyIn | CopyOut:
    match parse_endpoint(source), parse_endpoint(destination):
        case ClientEndpoint(path=path), ContainerEndpoint() as into_container:
            return CopyIn(path, into_container)
        case ContainerEndpoint(path=path), ClientEndpoint() as onto_client:
            return CopyOut(path, onto_client)
        case _:
            raise InvalidValue(
                "copy between your machine and the container: one side starts with ':', "
                "such as `outpost cp ./notes.md :~/inbox/`"
            )


def placement[P: PurePath](destination: P, source_name: str, *, into: bool) -> tuple[P, str]:
    """The directory to write into and the name to give: inside `destination`, or as it."""
    if into:
        return destination, source_name
    return destination.parent, destination.name
