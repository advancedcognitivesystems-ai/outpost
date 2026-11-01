"""The certificates programs in the container trust."""

from __future__ import annotations

from typing import Protocol


class TrustStore(Protocol):
    def trust(self, certificate: str) -> bool:
        """Trust `certificate` from now on; returns whether that changed anything."""
        ...
