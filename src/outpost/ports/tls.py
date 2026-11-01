"""Certificate material for the edge."""

from __future__ import annotations

from typing import Protocol

from outpost.domain.resources import HostLayout
from outpost.domain.tls import TlsMaterial


class TlsProvisioner(Protocol):
    def prepare(self, layout: HostLayout) -> TlsMaterial:
        """Make the material exist on the host and describe it for the edge."""
        ...

    def client_trust_bundle(self, layout: HostLayout) -> str | None:
        """PEM text the client must trust, or None when public trust applies."""
        ...
