"""`outpost doctor`: run checks in order, skip those whose prerequisites failed, offer fixes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from outpost.domain.checks import CheckResult, DoctorReport, Status
from outpost.domain.errors import Unavailable
from outpost.ports.interaction import Prompter


class Check(ABC):
    def __init__(self, check_id: str, title: str, requires: tuple[str, ...] = ()) -> None:
        self.check_id = check_id
        self.title = title
        self.requires = requires

    @abstractmethod
    def run(self) -> CheckResult: ...

    def fix(self) -> None:
        raise Unavailable(f"{self.title}: no automatic fix")

    def _result(
        self, status: Status, detail: str = "", remedy: str = "", *, fixable: bool = False
    ) -> CheckResult:
        return CheckResult(self.check_id, self.title, status, detail, remedy, fixable)

    def ok(self, detail: str = "") -> CheckResult:
        return self._result(Status.OK, detail)

    def warn(self, detail: str, remedy: str = "") -> CheckResult:
        return self._result(Status.WARN, detail, remedy)

    def fail(self, detail: str, remedy: str = "", *, fixable: bool = False) -> CheckResult:
        return self._result(Status.FAIL, detail, remedy, fixable=fixable)


class Doctor:
    def __init__(self, checks: Sequence[Check], prompter: Prompter) -> None:
        self._checks = checks
        self._prompter = prompter

    def run(self, *, fix: bool) -> DoctorReport:
        results: dict[str, CheckResult] = {}
        for check in self._checks:
            blocked = [
                need
                for need in check.requires
                if need in results and results[need].status is not Status.OK
            ]
            if blocked:
                result = CheckResult(
                    check.check_id, check.title, Status.SKIPPED, f"needs {', '.join(blocked)}"
                )
            else:
                result = self._run_and_fix(check, fix=fix)
            results[check.check_id] = result
        return DoctorReport(tuple(results.values()))

    def _run_and_fix(self, check: Check, *, fix: bool) -> CheckResult:
        result = check.run()
        if result.status is not Status.FAIL or not result.fixable or not fix:
            return result
        if not self._prompter.confirm(f"{check.title}: {result.detail}. Fix it now?", default=True):
            return result
        check.fix()
        return check.run()
