"""Text shown to the person. Formatting only: no decisions, no I/O beyond the stream given."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TextIO

from outpost.application.environment import EnvironmentStatus
from outpost.application.worktrees import WorktreeStatus
from outpost.domain.checks import DoctorReport, Status
from outpost.domain.credentials import AuthState

_MARKS = {Status.OK: "ok  ", Status.WARN: "warn", Status.FAIL: "FAIL", Status.SKIPPED: "skip"}


def doctor_report(report: DoctorReport, out: TextIO) -> None:
    width = max((len(result.title) for result in report.results), default=0)
    for result in report.results:
        print(f"[{_MARKS[result.status]}] {result.title.ljust(width)}  {result.detail}", file=out)
        if result.remedy and result.status in {Status.FAIL, Status.WARN}:
            print(f"       {''.ljust(width)}  → {result.remedy}", file=out)
    verdict = "blocking problems found" if report.blocking else "nothing blocks `outpost up`"
    print(f"\n{verdict}", file=out)


def environment_status(status: EnvironmentStatus, out: TextIO) -> None:
    print(f"edge  {status.edge.value}", file=out)
    print(f"box   {status.box.value}", file=out)


def lines(items: Iterable[str], out: TextIO, *, empty: str) -> None:
    printed = False
    for item in items:
        print(item, file=out)
        printed = True
    if not printed:
        print(empty, file=out)


def worktrees(items: Iterable[WorktreeStatus], out: TextIO) -> None:
    rows = [
        f"{item.worktree.name}\t{item.worktree.branch}\t{'running' if item.stack_running else '-'}"
        for item in items
    ]
    lines(rows, out, empty="no worktrees yet: `outpost worktree add <name>`")


def auth_states(states: Iterable[AuthState], out: TextIO) -> None:
    for state in states:
        mark = "ok  " if state.valid else "FAIL"
        print(f"[{mark}] {state.tool.value}  {state.detail}", file=out)
