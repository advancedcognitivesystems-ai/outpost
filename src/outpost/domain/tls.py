"""What the edge needs to serve HTTPS, whatever produced it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from outpost.domain.names import Domain


@dataclass(frozen=True)
class CertificateFiles:
    """A wildcard certificate and its key, already on the host."""

    certificate: PurePosixPath
    key: PurePosixPath


@dataclass(frozen=True)
class AcmeIssuance:
    """The edge obtains and renews a wildcard certificate itself through DNS-01."""

    domain: Domain
    email: str
    dns_provider: str
    provider_env_file: PurePosixPath


@dataclass(frozen=True)
class Plaintext:
    """No TLS: the edge serves HTTP only."""


TlsMaterial = CertificateFiles | AcmeIssuance | Plaintext
