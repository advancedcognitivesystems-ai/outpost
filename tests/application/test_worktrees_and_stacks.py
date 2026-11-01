from __future__ import annotations

import pytest

from outpost.application.stacks import Stacks
from outpost.application.worktrees import Worktrees
from outpost.domain.config import ResolvedConfig
from outpost.domain.errors import Unavailable
from outpost.domain.names import WorktreeName
from tests.fakes import FakeRepository, FakeStackRunner

FEAT = WorktreeName("feat-a")


def _services(config: ResolvedConfig) -> tuple[Worktrees, Stacks, FakeRepository, FakeStackRunner]:
    repository = FakeRepository(cloned=True)
    runner = FakeStackRunner()
    worktrees = Worktrees(config, repository, runner)
    return worktrees, Stacks(config, runner, worktrees), repository, runner


def test_stack_up_uses_the_worktree_and_returns_its_urls(azure: ResolvedConfig) -> None:
    worktrees, stacks, _, runner = _services(azure)
    worktrees.add(FEAT, branch="feature/a", start=None)
    urls = stacks.up(FEAT)
    assert urls == (
        "https://web--feat-a.dev.acme.example",
        "https://api--feat-a.dev.acme.example",
        "https://auth--feat-a.dev.acme.example",
    )
    (started,) = runner.started
    assert started.compose_files == ("deploy/compose.yaml",)
    assert str(started.directory) == "/workspaces/acme/worktrees/feat-a"


def test_stack_of_an_unknown_worktree_is_refused(azure: ResolvedConfig) -> None:
    _, stacks, _, _ = _services(azure)
    with pytest.raises(Unavailable, match="no worktree named feat-a"):
        stacks.up(FEAT)


def test_removing_a_worktree_stops_its_stack_first(azure: ResolvedConfig) -> None:
    worktrees, stacks, repository, runner = _services(azure)
    worktrees.add(FEAT, branch=None, start=None)
    stacks.up(FEAT)
    worktrees.remove(FEAT, force=False)
    assert runner.stopped == [FEAT]
    assert repository.removed == [FEAT]


def test_adding_an_existing_worktree_is_refused(azure: ResolvedConfig) -> None:
    worktrees, _, _, _ = _services(azure)
    worktrees.add(FEAT, branch=None, start=None)
    with pytest.raises(Unavailable, match="already exists"):
        worktrees.add(FEAT, branch=None, start=None)
    (status,) = worktrees.list()
    assert status.worktree.branch == "feat-a"
    assert not status.stack_running
