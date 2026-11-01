"""Results of `outpost doctor`."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Status(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    title: str
    status: Status
    detail: str = ""
    remedy: str = ""
    fixable: bool = False


@dataclass(frozen=True)
class DoctorReport:
    results: tuple[CheckResult, ...]

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        return tuple(result for result in self.results if result.status is Status.FAIL)

    @property
    def blocking(self) -> bool:
        return bool(self.failures)
