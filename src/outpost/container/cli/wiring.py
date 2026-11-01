"""The composition root of the in-container tool: the only module that builds its adapters."""

from __future__ import annotations

import os
from collections.abc import Mapping
from functools import cached_property

from outpost.container.adapters.caddy import CaddyAdmin
from outpost.container.adapters.docker_engine import DockerEngine
from outpost.container.adapters.init_files import (
    DirectoryOwnership,
    JsonBootStore,
    ScriptDirectories,
)
from outpost.container.adapters.proxy_container import CaddyContainer
from outpost.container.application.boot import Boot, Init, ProxyStartup, Status
from outpost.container.application.routes import Routes
from outpost.domain.layout import DEFAULT_DOMAIN, DEFAULT_PORT, ENV_DOMAIN, ENV_PERSIST, ENV_PORT
from outpost.domain.names import DnsName, port_number
from outpost.domain.routes import Site
from outpost.domain.volumes import persisted_paths
from outpost.infra.process import SubprocessRunner


class InContainer:
    """Everything the tool needs, read from the variables the launcher sets in devcontainer.json."""

    def __init__(self, environ: Mapping[str, str] = os.environ) -> None:
        self._environ = environ
        self._runner = SubprocessRunner()

    @cached_property
    def site(self) -> Site:
        domain = DnsName(self._environ.get(ENV_DOMAIN, DEFAULT_DOMAIN))
        return Site(domain, port_number(int(self._environ.get(ENV_PORT, DEFAULT_PORT))))

    @cached_property
    def _proxy(self) -> CaddyAdmin:
        return CaddyAdmin(site=self.site)

    @cached_property
    def _store(self) -> JsonBootStore:
        return JsonBootStore()

    @cached_property
    def _init(self) -> Init:
        return Init(ScriptDirectories(self._runner), self._store)

    def routes(self) -> Routes:
        return Routes(self.site, self._proxy, DockerEngine(self._runner))

    def proxy_startup(self) -> ProxyStartup:
        return ProxyStartup(CaddyContainer(self._runner), self._proxy)

    def boot(self) -> Boot:
        return Boot(
            proxy=self.proxy_startup(),
            init=self._init,
            store=self._store,
            ownership=DirectoryOwnership(),
            persisted=persisted_paths(self._environ.get(ENV_PERSIST, "")),
        )

    def init(self) -> Init:
        return self._init

    def status(self) -> Status:
        return Status(self._proxy, self._store)

    def root_certificate(self) -> str:
        return self._proxy.root_certificate()
