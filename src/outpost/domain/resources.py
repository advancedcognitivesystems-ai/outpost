"""Names of the objects Outpost owns on a host, and the paths it uses on the host and in the box."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from outpost.domain.errors import InvalidValue
from outpost.domain.names import ProjectName, WorktreeName

BOX_WORKSPACES = PurePosixPath("/workspaces")
BOX_EXCHANGE = PurePosixPath("/exchange")
BOX_DOCKER_DATA = PurePosixPath("/var/lib/docker")
ROUTES_NETWORK = "outpost-routes"
ROUTER_PORT = 80


class Role(StrEnum):
    """What a host object is for; part of its name."""

    EDGE = "edge"
    BOX = "box"
    EDGE_NETWORK = "edge-net"
    WORKSPACES = "workspaces"
    DOCKER_DATA = "docker"
    HOME = "home"
    EDGE_DATA = "edge-data"


@dataclass(frozen=True)
class HostResources:
    """Container, network, volume and image names for one project."""

    project: ProjectName

    def name(self, role: Role) -> str:
        return f"outpost-{self.project}-{role.value}"

    def box_image(self, fingerprint: str) -> str:
        return f"outpost-{self.project}-box:{fingerprint}"


@dataclass(frozen=True)
class HostLayout:
    """Absolute paths under the host's state directory."""

    state_dir: PurePosixPath

    @property
    def tls_dir(self) -> PurePosixPath:
        return self.state_dir / "tls"

    @property
    def secrets_dir(self) -> PurePosixPath:
        return self.state_dir / "secrets"

    @property
    def edge_dir(self) -> PurePosixPath:
        return self.state_dir / "edge"

    @property
    def box_build_dir(self) -> PurePosixPath:
        return self.state_dir / "box"

    @property
    def staging_dir(self) -> PurePosixPath:
        return self.state_dir / "staging"

    @property
    def exchange_dir(self) -> PurePosixPath:
        return self.state_dir / "exchange"


@dataclass(frozen=True)
class BoxLayout:
    """Paths inside the box, the same on every host."""

    project: ProjectName
    user: str

    @property
    def home(self) -> PurePosixPath:
        return PurePosixPath("/home") / self.user

    @property
    def project_dir(self) -> PurePosixPath:
        return BOX_WORKSPACES / str(self.project)

    @property
    def repository(self) -> PurePosixPath:
        return self.project_dir / "repo"

    @property
    def worktrees_dir(self) -> PurePosixPath:
        return self.project_dir / "worktrees"

    @property
    def stack_overrides_dir(self) -> PurePosixPath:
        return self.project_dir / ".outpost" / "stacks"

    def worktree(self, name: WorktreeName) -> PurePosixPath:
        return self.worktrees_dir / str(name)


def expand_home(path: str, home: str) -> PurePosixPath:
    """Resolve a leading `~` against a home directory; other paths must be absolute."""
    if path == "~" or path.startswith("~/"):
        return PurePosixPath(home) / path[2:]
    resolved = PurePosixPath(path)
    if not resolved.is_absolute():
        raise InvalidValue(f"path {path!r} must be absolute or start with '~/'")
    return resolved
