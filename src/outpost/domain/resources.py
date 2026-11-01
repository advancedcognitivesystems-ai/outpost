"""Names of the objects Outpost owns on a host, and the paths it uses on the host and in the box."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from outpost.domain.errors import InvalidValue
from outpost.domain.names import ImageRef, ProjectName, UserName, WorktreeName

BOX_WORKSPACES = PurePosixPath("/workspaces")
BOX_EXCHANGE = PurePosixPath("/exchange")
BOX_DOCKER_DATA = PurePosixPath("/var/lib/docker")


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

    @property
    def prefix(self) -> str:
        return f"outpost-{self.project}"

    def name(self, role: Role) -> str:
        return f"{self.prefix}-{role.value}"

    def box_image(self, fingerprint: str) -> ImageRef:
        return ImageRef(f"{self.name(Role.BOX)}:{fingerprint}")


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
    def exchange_dir(self) -> PurePosixPath:
        return self.state_dir / "exchange"


@dataclass(frozen=True)
class BoxLayout:
    """Paths inside the box, the same on every host."""

    project: ProjectName
    user: UserName

    @property
    def home(self) -> PurePosixPath:
        return PurePosixPath("/home") / str(self.user)

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
    def stacks_dir(self) -> PurePosixPath:
        """Outpost's files per stack, outside the worktrees so `git status` stays clean."""
        return self.project_dir / ".outpost" / "stacks"

    def worktree(self, name: WorktreeName) -> PurePosixPath:
        return self.worktrees_dir / str(name)


def state_path(path: str) -> str:
    """A host path Outpost accepts in configuration: absolute, or under the home directory."""
    if path == "~" or path.startswith(("~/", "/")):
        return path
    raise InvalidValue(f"path {path!r} must be absolute or start with '~/'")


def expand_home(path: str, home: str) -> PurePosixPath:
    """Resolve a leading `~` against a home directory."""
    state_path(path)
    if path.startswith("~"):
        return PurePosixPath(home) / path[2:]
    return PurePosixPath(path)
