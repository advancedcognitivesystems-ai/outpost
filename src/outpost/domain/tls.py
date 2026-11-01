"""What the edge needs to serve HTTPS, whatever produced it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from outpost.domain.names import Domain


@dataclass(frozen=True)
class CertificateFiles:
    """A wildcard certificate and its key, alone in their directory on the host."""

    certificate: PurePosixPath
    key: PurePosixPath

    @property
    def directory(self) -> PurePosixPath:
        return self.certificate.parent


@dataclass(frozen=True)
class AcmeIssuance:
    """The edge obtains and renews a wildcard certificate itself through DNS-01.

    Each DNS provider credential is one file in `credentials_dir`, named after its variable,
    so the edge reads them through `<VARIABLE>_FILE` and never holds them in its environment.
    """

    domain: Domain
    email: str
    dns_provider: str
    credentials_dir: PurePosixPath
    variables: tuple[str, ...]


@dataclass(frozen=True)
class Plaintext:
    """No TLS: the edge serves HTTP only."""


TlsMaterial = CertificateFiles | AcmeIssuance | Plaintext
