"""Let's Encrypt through DNS-01: the edge issues and renews, Outpost hands it the DNS credentials.

The client file holds `NAME=value` lines for the DNS provider. Each value becomes its own file
on the host (mode 0600), which the edge reads through `<NAME>_FILE`, so no credential ever sits
in a container's environment.
"""

from __future__ import annotations

from outpost.domain.config import AcmeTls
from outpost.domain.errors import InvalidValue, Unavailable
from outpost.domain.names import Domain, variable_name
from outpost.domain.resources import HostLayout
from outpost.domain.secrets import Secret
from outpost.domain.tls import AcmeIssuance, TlsMaterial
from outpost.ports.credentials import SecretSource
from outpost.ports.shell import Shell

CREDENTIALS_DIR = "acme-dns"


class AcmeDnsChallenge:
    def __init__(
        self, host: Shell, spec: AcmeTls, domain: Domain, credentials: SecretSource
    ) -> None:
        self._host = host
        self._spec = spec
        self._domain = domain
        self._credentials = credentials

    def prepare(self, layout: HostLayout) -> TlsMaterial:
        content = self._credentials.read()
        if content is None:
            raise Unavailable(
                f"DNS provider credentials not found in {self._credentials.description}"
            )
        directory = layout.secrets_dir / CREDENTIALS_DIR
        values = parse_assignments(content)
        for name, value in values.items():
            self._host.write_file(directory / name, value.reveal(), mode=0o600)
        return AcmeIssuance(
            domain=self._domain,
            email=self._spec.email,
            dns_provider=self._spec.dns_provider,
            credentials_dir=directory,
            variables=tuple(sorted(values)),
        )

    def client_trust_bundle(self, layout: HostLayout) -> str | None:
        return None


def parse_assignments(content: Secret) -> dict[str, Secret]:
    """`NAME=value` lines; blank lines and `#` comments are skipped, surrounding quotes removed."""
    values: dict[str, Secret] = {}
    for number, line in enumerate(content.reveal().splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name, separator, value = stripped.removeprefix("export ").partition("=")
        if not separator:
            raise InvalidValue(f"DNS credentials line {number} is not NAME=value")
        values[variable_name(name.strip())] = Secret(value.strip().strip("'\""))
    if not values:
        raise InvalidValue("DNS credentials file has no NAME=value line")
    return values
