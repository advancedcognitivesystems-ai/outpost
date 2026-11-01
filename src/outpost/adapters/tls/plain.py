"""No TLS at all: for trying Outpost out on a machine you trust."""

from __future__ import annotations

from outpost.domain.resources import HostLayout
from outpost.domain.tls import Plaintext, TlsMaterial


class PlainHttp:
    def prepare(self, layout: HostLayout) -> TlsMaterial:
        return Plaintext()

    def client_trust_bundle(self, layout: HostLayout) -> str | None:
        return None
