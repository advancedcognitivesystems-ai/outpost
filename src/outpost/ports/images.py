"""Putting the base image on the host."""

from __future__ import annotations

from typing import Protocol

from outpost.domain.names import ImageRef
from outpost.ports.shell import ClientNeeds


class RegistryAuth(ClientNeeds, Protocol):
    def login(self) -> None:
        """Log the host's engine into the registry; no-op when none is needed."""
        ...


class ImageSupplier(ClientNeeds, Protocol):
    def ensure(self, ref: ImageRef) -> None:
        """Make the image present on the host, fetching or copying it if needed."""
        ...
