"""Facts about a host, read with POSIX commands through its shell."""

from __future__ import annotations

from outpost.domain.resources import expand_home
from outpost.ports.shell import Shell

_EXISTING_PARENT = (
    'p="$1"; while [ ! -e "$p" ] && [ "$p" != / ]; do p=$(dirname "$p"); done; df -Pk "$p"'
)
_KB_PER_GB = 1024**2


class RemoteProbe:
    def __init__(self, shell: Shell) -> None:
        self._shell = shell
        self._home: str | None = None

    def reachable(self) -> bool:
        return self._shell.run(["true"]).ok

    def home(self) -> str:
        if self._home is None:
            self._home = self._shell.run(["sh", "-c", 'printf %s "$HOME"']).check().stdout
        return self._home

    def has_command(self, name: str) -> bool:
        return self._shell.run(["sh", "-c", 'command -v "$1" >/dev/null', "sh", name]).ok

    def free_disk_gb(self, path: str) -> float | None:
        expanded = expand_home(path, self.home())
        result = self._shell.run(["sh", "-c", _EXISTING_PARENT, "sh", str(expanded)])
        lines = result.stdout.strip().splitlines()
        if not result.ok or len(lines) < 2:
            return None
        available_kb = int(lines[-1].split()[3])
        return available_kb / _KB_PER_GB

    def resolve(self, hostname: str) -> tuple[str, ...]:
        result = self._shell.run(["getent", "hosts", hostname])
        if not result.ok:
            return ()
        return tuple(sorted({line.split()[0] for line in result.stdout.splitlines() if line}))
