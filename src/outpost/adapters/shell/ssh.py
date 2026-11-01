"""Commands on a host reached with OpenSSH; the user's ssh configuration still applies."""

from __future__ import annotations

import shlex
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from outpost.adapters.shell.base import ShellBase
from outpost.adapters.shell.process import run_attached, run_captured
from outpost.domain.config import SshConnection
from outpost.ports.shell import CommandResult

CONNECT_TIMEOUT_SECONDS = 10


class SshShell(ShellBase):
    def __init__(self, connection: SshConnection) -> None:
        self._connection = connection

    @property
    def description(self) -> str:
        return f"ssh {self._destination}"

    @property
    def client_commands(self) -> tuple[str, ...]:
        return ("ssh", "scp")

    @property
    def _destination(self) -> str:
        user = self._connection.user
        return f"{user}@{self._connection.host}" if user else self._connection.host

    def _options(self, *, port_flag: str, interactive: bool) -> list[str]:
        options = ["-o", f"ConnectTimeout={CONNECT_TIMEOUT_SECONDS}"]
        if not interactive:
            options += ["-o", "BatchMode=yes"]
        options += [port_flag, str(int(self._connection.port))]
        if self._connection.identity_file:
            options += ["-i", str(Path(self._connection.identity_file).expanduser())]
        return options

    def command(self, argv: Sequence[str], *, interactive: bool = False) -> list[str]:
        """The client-side `ssh` invocation that runs `argv` on the host."""
        tty = ["-t"] if interactive else []
        options = self._options(port_flag="-p", interactive=interactive)
        return ["ssh", *tty, *options, self._destination, "--", shlex.join(argv)]

    def _execute(self, argv: Sequence[str], stdin: str | None) -> CommandResult:
        result = run_captured(self.command(argv), stdin=stdin)
        return CommandResult(tuple(argv), result.code, result.stdout, result.stderr)

    def _attach(self, argv: Sequence[str]) -> int:
        return run_attached(self.command(argv, interactive=True))

    def upload(self, source: Path, target: PurePosixPath) -> None:
        self.ensure_directory(target.parent)
        options = self._options(port_flag="-P", interactive=False)
        run_captured(["scp", "-q", *options, str(source), f"{self._destination}:{target}"]).check()
