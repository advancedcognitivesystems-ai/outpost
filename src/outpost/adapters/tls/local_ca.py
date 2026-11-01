"""A private CA on the host and one wildcard certificate it signs, made with openssl."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from outpost.domain.names import Domain, ProjectName
from outpost.domain.resources import HostLayout
from outpost.domain.tls import CertificateFiles, TlsMaterial
from outpost.ports.shell import Shell

CA_VALIDITY_DAYS = 3650
LEAF_VALIDITY_DAYS = 397


@dataclass(frozen=True)
class _Files:
    directory: PurePosixPath

    @property
    def ca_key(self) -> PurePosixPath:
        return self.directory / "ca.key"

    @property
    def ca_certificate(self) -> PurePosixPath:
        return self.directory / "ca.crt"

    @property
    def key(self) -> PurePosixPath:
        return self.directory / "wildcard.key"

    @property
    def request(self) -> PurePosixPath:
        return self.directory / "wildcard.csr"

    @property
    def certificate(self) -> PurePosixPath:
        return self.directory / "wildcard.crt"

    @property
    def extensions(self) -> PurePosixPath:
        return self.directory / "wildcard.ext"

    @property
    def issued_for(self) -> PurePosixPath:
        return self.directory / "issued-for"


class LocalCertificateAuthority:
    def __init__(self, host: Shell, domain: Domain, project: ProjectName) -> None:
        self._host = host
        self._domain = domain
        self._project = project

    def prepare(self, layout: HostLayout) -> TlsMaterial:
        files = _Files(layout.tls_dir)
        if self._host.read_file(files.ca_certificate) is None:
            self._create_authority(files)
        if self._host.read_file(files.issued_for) != str(self._domain):
            self._issue(files)
        return CertificateFiles(certificate=files.certificate, key=files.key)

    def client_trust_bundle(self, layout: HostLayout) -> str | None:
        return self._host.read_file(_Files(layout.tls_dir).ca_certificate)

    def _openssl(self, *args: str) -> None:
        self._host.run(["openssl", *args]).check()

    def _create_authority(self, files: _Files) -> None:
        self._host.ensure_directory(files.directory)
        self._openssl(
            "req", "-x509", "-newkey", "rsa:4096", "-sha256", "-nodes",
            "-days", str(CA_VALIDITY_DAYS),
            "-keyout", str(files.ca_key), "-out", str(files.ca_certificate),
            "-subj", f"/CN=Outpost local CA ({self._project})",
            "-addext", "basicConstraints=critical,CA:TRUE",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign",
        )  # fmt: skip
        self._host.run(["chmod", "600", str(files.ca_key)]).check()

    def _issue(self, files: _Files) -> None:
        domain = str(self._domain)
        self._host.write_file(
            files.extensions,
            f"subjectAltName=DNS:*.{domain},DNS:{domain}\n"
            "basicConstraints=CA:FALSE\n"
            "keyUsage=digitalSignature,keyEncipherment\n"
            "extendedKeyUsage=serverAuth\n",
        )
        self._openssl(
            "req", "-new", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(files.key), "-out", str(files.request),
            "-subj", f"/CN=*.{domain}",
        )  # fmt: skip
        self._openssl(
            "x509", "-req", "-sha256", "-in", str(files.request),
            "-CA", str(files.ca_certificate), "-CAkey", str(files.ca_key), "-CAcreateserial",
            "-days", str(LEAF_VALIDITY_DAYS),
            "-out", str(files.certificate), "-extfile", str(files.extensions),
        )  # fmt: skip
        self._host.run(["chmod", "600", str(files.key)]).check()
        self._host.write_file(files.issued_for, domain)
