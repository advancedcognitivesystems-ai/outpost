"""Getting the base image onto the host: pull it from a registry, or copy it from the client."""

from __future__ import annotations

import tempfile
from pathlib import Path

from outpost.domain.errors import Unavailable
from outpost.domain.names import ImageRef
from outpost.ports.engine import ContainerEngine
from outpost.ports.images import RegistryAuth
from outpost.ports.shell import Shell


class RegistryImages:
    def __init__(self, host_engine: ContainerEngine, auth: RegistryAuth) -> None:
        self._engine = host_engine
        self._auth = auth

    @property
    def client_commands(self) -> tuple[str, ...]:
        return self._auth.client_commands

    def ensure(self, ref: ImageRef) -> None:
        if self._engine.image_exists(ref):
            return
        self._auth.login()
        self._engine.pull(ref)


class ClientImages:
    """Copies an image from the client. When the client is the host, it must already be there."""

    def __init__(
        self,
        client_engine: ContainerEngine,
        host_engine: ContainerEngine,
        host: Shell,
        *,
        same_machine: bool,
    ) -> None:
        self._client_engine = client_engine
        self._host_engine = host_engine
        self._host = host
        self._same_machine = same_machine

    @property
    def client_commands(self) -> tuple[str, ...]:
        return () if self._same_machine else ("docker",)

    def ensure(self, ref: ImageRef) -> None:
        if self._host_engine.image_exists(ref):
            return
        if self._same_machine or not self._client_engine.image_exists(ref):
            raise Unavailable(f"image {ref} is not available locally; build or pull it first")
        with tempfile.TemporaryDirectory(prefix="outpost-") as directory:
            archive = Path(directory) / "image.tar"
            self._client_engine.save(ref, archive)
            with self._host.staged(archive) as on_host:
                self._host_engine.load(on_host)
