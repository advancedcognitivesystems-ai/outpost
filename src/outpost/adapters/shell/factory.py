"""Connection kind to shell. The only place that decides it."""

from __future__ import annotations

from outpost.adapters.shell.local import LocalShell
from outpost.adapters.shell.ssh import SshShell
from outpost.domain.config import ConnectionSpec, LocalConnection, SshConnection
from outpost.ports.shell import Shell


def build_host_shell(connection: ConnectionSpec) -> Shell:
    match connection:
        case LocalConnection():
            return LocalShell()
        case SshConnection():
            return SshShell(connection)


def build_client_shell() -> Shell:
    return LocalShell()
