"""Facts about the machine running Outpost, read with the standard library."""

from __future__ import annotations

import shutil
import socket
from pathlib import Path

_GB = 1024**3


class LocalProbe:
    def reachable(self) -> bool:
        return True

    def home(self) -> str:
        return str(Path.home())

    def has_command(self, name: str) -> bool:
        return shutil.which(name) is not None

    def free_disk_gb(self, path: str) -> float | None:
        candidate = Path(path).expanduser()
        while not candidate.exists() and candidate != candidate.parent:
            candidate = candidate.parent
        return shutil.disk_usage(candidate).free / _GB

    def resolve(self, hostname: str) -> tuple[str, ...]:
        try:
            infos = socket.getaddrinfo(hostname, None)
        except socket.gaierror:
            return ()
        return tuple(sorted({str(info[4][0]) for info in infos}))
