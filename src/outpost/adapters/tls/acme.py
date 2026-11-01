"""Let's Encrypt through DNS-01: the edge issues and renews, Outpost hands it the DNS secrets."""

from __future__ import annotations

from pathlib import Path

from outpost.domain.config import AcmeTls
from outpost.domain.errors import Unavailable
from outpost.domain.names import Domain
from outpost.domain.resources import HostLayout
from outpost.domain.tls import AcmeIssuance, TlsMaterial
from outpost.ports.shell import Shell

PROVIDER_ENV_FILE = "acme-dns.env"


class AcmeDnsChallenge:
    def __init__(self, host: Shell, spec: AcmeTls, domain: Domain) -> None:
        self._host = host
        self._spec = spec
        self._domain = domain

    def prepare(self, layout: HostLayout) -> TlsMaterial:
        source = Path(self._spec.dns_env_file).expanduser()
        if not source.is_file():
            raise Unavailable(f"DNS provider credentials not found at {source} (tls.dns_env_file)")
        target = layout.secrets_dir / PROVIDER_ENV_FILE
        self._host.write_file(target, source.read_text(encoding="utf-8"), mode=0o600)
        return AcmeIssuance(
            domain=self._domain,
            email=self._spec.email,
            dns_provider=self._spec.dns_provider,
            provider_env_file=target,
        )

    def client_trust_bundle(self, layout: HostLayout) -> str | None:
        return None
