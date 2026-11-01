"""git in the box: one clone of the project, one worktree per task."""

from __future__ import annotations

from pathlib import PurePosixPath

from outpost.domain.config import GitIdentity
from outpost.domain.names import WorktreeName
from outpost.domain.resources import BoxLayout
from outpost.domain.worktrees import Worktree
from outpost.ports.shell import CommandResult, Shell

_BRANCH_REF = "refs/heads/"


class GitRepository:
    def __init__(self, box: Shell, layout: BoxLayout) -> None:
        self._box = box
        self._layout = layout

    def _git(self, *args: str) -> CommandResult:
        return self._box.run(["git", "-C", str(self._layout.repository), *args])

    def is_cloned(self) -> bool:
        return self._git("rev-parse", "--git-dir").ok

    def clone(self, url: str, branch: str) -> None:
        self._box.ensure_directory(self._layout.project_dir)
        self._box.run(
            ["git", "clone", "--branch", branch, url, str(self._layout.repository)]
        ).check()

    def add_worktree(self, name: WorktreeName, branch: str, start_point: str) -> Worktree:
        path = self._layout.worktree(name)
        self._git("fetch", "--prune", "origin").check()
        remote = f"origin/{branch}"
        if self._git("rev-parse", "--verify", "--quiet", remote).ok:
            self._git("worktree", "add", "--track", "-B", branch, str(path), remote).check()
        else:
            self._git("worktree", "add", "-b", branch, str(path), start_point).check()
        return Worktree(name=name, branch=branch, path=path)

    def remove_worktree(self, name: WorktreeName, *, force: bool) -> None:
        flags = ["--force"] if force else []
        self._git("worktree", "remove", *flags, str(self._layout.worktree(name))).check()

    def worktrees(self) -> tuple[Worktree, ...]:
        listing = self._git("worktree", "list", "--porcelain").check().stdout
        return tuple(self._parse(block) for block in listing.split("\n\n") if self._ours(block))

    def set_identity(self, identity: GitIdentity) -> None:
        self._box.run(["git", "config", "--global", "user.name", identity.user_name]).check()
        self._box.run(["git", "config", "--global", "user.email", identity.user_email]).check()

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
