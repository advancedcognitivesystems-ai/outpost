"""Connection kind to probe."""

from __future__ import annotations

from outpost.adapters.probe.local import LocalProbe
from outpost.adapters.probe.remote import RemoteProbe
from outpost.domain.config import ConnectionSpec, LocalConnection, SshConnection
from outpost.ports.probe import MachineProbe
from outpost.ports.shell import Shell


def build_host_probe(connection: ConnectionSpec, host_shell: Shell) -> MachineProbe:
    match connection:
        case LocalConnection():
            return LocalProbe()
        case SshConnection():
            return RemoteProbe(host_shell)


def build_client_probe() -> MachineProbe:
    return LocalProbe()
