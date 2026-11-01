"""If it is not in the image, it is in a volume: the four default volumes and the ones you add."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from outpost.domain.errors import InvalidValue
from outpost.domain.layout import DOCKER_DATA, HOME, STATE, WORKSPACES
from outpost.domain.names import EnvironmentName

DEFAULT_TARGETS: dict[str, PurePosixPath] = {
    "home": HOME,
    "workspaces": WORKSPACES,
    "docker": DOCKER_DATA,
    "state": STATE,
}
WORKSPACES_ROLE = "workspaces"
_SYSTEM = tuple(PurePosixPath(path) for path in ("/proc", "/sys", "/dev"))
_SLUG = re.compile(r"[^a-z0-9_.-]+")


@dataclass(frozen=True, slots=True)
class Volume:
    name: str
    target: PurePosixPath


def _overlaps(one: PurePosixPath, other: PurePosixPath) -> bool:
    return one == other or other in one.parents or one in other.parents


def persist_path(text: str) -> PurePosixPath:
    """An extra path to keep in a volume: absolute, outside the defaults and the kernel's."""
    path = PurePosixPath(text)
    if not path.is_absolute() or ".." in path.parts or path == PurePosixPath("/"):
        raise InvalidValue(f"{text!r} must be an absolute path below /, without '..'")
    for target in (*DEFAULT_TARGETS.values(), *_SYSTEM):
        if _overlaps(path, target):
            raise InvalidValue(f"{path} overlaps {target}, which Outpost already handles")
    return path


def volume_name(environment: EnvironmentName, role: str) -> str:
    return f"{environment.container}-{role}"


def volumes_for(
    environment: EnvironmentName, persist: Sequence[PurePosixPath]
) -> tuple[Volume, ...]:
    """The default volumes, then one per persisted path, named after it."""
    volumes = [Volume(volume_name(environment, role), t) for role, t in DEFAULT_TARGETS.items()]
    for index, path in enumerate(persist):
        for earlier in persist[:index]:
            if _overlaps(path, earlier):
                raise InvalidValue(f"{path} overlaps {earlier}; keep one of them")
        slug = _SLUG.sub("-", "-".join(path.parts[1:]).lower()).strip("-.") or "root"
        volumes.append(Volume(volume_name(environment, f"persist-{slug}"), path))
    names = [volume.name for volume in volumes]
    duplicate = next((name for name in names if names.count(name) > 1), None)
    if duplicate:
        raise InvalidValue(f"two persisted paths would share the volume {duplicate}")
    return tuple(volumes)
