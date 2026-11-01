"""git in the box: one clone of the project, one worktree per task."""

from __future__ import annotations

from pathlib import PurePosixPath

from outpost.domain.config import GitIdentity, ProjectSpec
from outpost.domain.names import WorktreeName
from outpost.domain.resources import BoxLayout
from outpost.domain.worktrees import Worktree
from outpost.ports.shell import CommandResult, Shell

REMOTE = "origin"
_BRANCH_REF = "refs/heads/"


class GitRepository:
    def __init__(self, box: Shell, layout: BoxLayout, project: ProjectSpec) -> None:
        self._box = box
        self._layout = layout
        self._project = project

    def _git(self, *args: str) -> CommandResult:
        return self._box.run(["git", "-C", str(self._layout.repository), *args])

    def _has_ref(self, ref: str) -> bool:
        return self._git("rev-parse", "--verify", "--quiet", ref).ok

    def is_cloned(self) -> bool:
        return self._git("rev-parse", "--git-dir").ok

    def clone(self) -> None:
        self._box.ensure_directory(self._layout.project_dir)
        url, branch = self._project.repository, self._project.default_branch
        target = str(self._layout.repository)
        self._box.run(["git", "clone", "--origin", REMOTE, "--branch", branch, url, target]).check()

    def add_worktree(self, name: WorktreeName, branch: str, start: str | None) -> Worktree:
        path = str(self._layout.worktree(name))
        self._git("fetch", "--prune", REMOTE).check()
        if self._has_ref(f"{_BRANCH_REF}{branch}"):
            self._git("worktree", "add", path, branch).check()
        elif self._has_ref(f"refs/remotes/{REMOTE}/{branch}"):
            self._git(
                "worktree", "add", "--track", "-b", branch, path, f"{REMOTE}/{branch}"
            ).check()
        else:
            base = start or f"{REMOTE}/{self._project.default_branch}"
            self._git("worktree", "add", "--no-track", "-b", branch, path, base).check()
        return Worktree(name=name, branch=branch, path=PurePosixPath(path))

    def remove_worktree(self, name: WorktreeName, *, force: bool) -> None:
        flags = ["--force"] if force else []
        self._git("worktree", "remove", *flags, str(self._layout.worktree(name))).check()

    def worktrees(self) -> tuple[Worktree, ...]:
        listing = self._git("worktree", "list", "--porcelain").check().stdout
        return tuple(self._parse(block) for block in listing.split("\n\n") if self._ours(block))

    def set_identity(self, identity: GitIdentity) -> None:
        """Commit identity, and a first `git push` that creates the branch on the remote."""
        for key, value in (
            ("user.name", identity.user_name),
            ("user.email", identity.user_email),
            ("push.autoSetupRemote", "true"),
        ):
            self._box.run(["git", "config", "--global", key, value]).check()

    def _ours(self, block: str) -> bool:
        path = _field(block, "worktree")
        return path is not None and PurePosixPath(path).parent == self._layout.worktrees_dir

    @staticmethod
    def _parse(block: str) -> Worktree:
        path = PurePosixPath(_field(block, "worktree") or "")
        branch = (_field(block, "branch") or "(detached)").removeprefix(_BRANCH_REF)
        return Worktree(name=WorktreeName(path.name), branch=branch, path=path)


def _field(block: str, name: str) -> str | None:
    prefix = f"{name} "
    for line in block.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :]
    return None
