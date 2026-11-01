"""TLS kind to provisioner."""

from __future__ import annotations

from pathlib import Path

from outpost.adapters.credentials.sources import FileSecret
from outpost.adapters.tls.acme import AcmeDnsChallenge
from outpost.adapters.tls.local_ca import LocalCertificateAuthority
from outpost.adapters.tls.plain import PlainHttp
from outpost.domain.config import AcmeTls, LocalCaTls, NoTls, TlsSpec
from outpost.domain.names import Domain, ProjectName
from outpost.ports.shell import Shell
from outpost.ports.tls import TlsProvisioner


def build_tls(spec: TlsSpec, host: Shell, domain: Domain, project: ProjectName) -> TlsProvisioner:
    match spec:
        case AcmeTls(dns_env_file=dns_env_file):
            credentials = FileSecret(Path(dns_env_file).expanduser())
            return AcmeDnsChallenge(host, spec, domain, credentials)
        case LocalCaTls():
            return LocalCertificateAuthority(host, domain, project)
        case NoTls():
            return PlainHttp()
