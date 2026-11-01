"""Getting the base image onto the host: pull it from a registry, or copy it from the client."""

from __future__ import annotations

import tempfile
from pathlib import Path, PurePosixPath

from outpost.domain.errors import Unavailable
from outpost.domain.fingerprint import fingerprint
from outpost.domain.names import ImageRef
from outpost.ports.engine import ContainerEngine
from outpost.ports.images import RegistryAuth
from outpost.ports.shell import Shell

HOST_STAGING = PurePosixPath("/tmp")


class RegistryImages:
    def __init__(self, host_engine: ContainerEngine, auth: RegistryAuth) -> None:
        self._engine = host_engine
        self._auth = auth

    def ensure(self, ref: ImageRef) -> None:
        if self._engine.image_exists(str(ref)):
            return
        self._auth.login()
        self._engine.pull(str(ref))


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

    def ensure(self, ref: ImageRef) -> None:
        if self._host_engine.image_exists(str(ref)):
            return
        if self._same_machine or not self._client_engine.image_exists(str(ref)):
            raise Unavailable(f"image {ref} is not available locally; build or pull it first")
        remote_archive = HOST_STAGING / f"outpost-image-{fingerprint(str(ref))}.tar"
        with tempfile.TemporaryDirectory(prefix="outpost-") as directory:
            archive = Path(directory) / "image.tar"
            self._client_engine.save(str(ref), archive)
            self._host.upload(archive, remote_archive)
        try:
            self._host_engine.load(remote_archive)
        finally:
            self._host.run(["rm", "-f", str(remote_archive)])
