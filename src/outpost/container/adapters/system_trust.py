"""`TrustStore`: the system's CA list, read by curl, git, Python and, through the image, Node."""

from __future__ import annotations

from pathlib import Path

from outpost.domain.layout import TRUSTED_CA
from outpost.infra.process import Runner


class SystemTrust:
    def __init__(self, runner: Runner, *, path: Path = Path(TRUSTED_CA)) -> None:
        self._runner = runner
        self._path = path

    def trust(self, certificate: str) -> bool:
        if self._path.is_file() and self._path.read_text(encoding="utf-8") == certificate:
            return False
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(certificate, encoding="utf-8")
        self._runner.run(["update-ca-certificates"]).check()
        return True
