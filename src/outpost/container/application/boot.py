"""What runs at every start of the container, after the entrypoint starts the inner Docker."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import PurePosixPath

from outpost.container.ports.init import BootStore, Ownership, Scripts
from outpost.container.ports.proxy import Proxy, ProxyRuntime
from outpost.container.ports.trust import TrustStore
from outpost.domain.errors import OutpostError, Unavailable
from outpost.domain.init import scripts_digest
from outpost.domain.status import BootRecord, ContainerStatus

PROXY_TIMEOUT = 60.0


class Init:
    def __init__(self, scripts: Scripts, store: BootStore) -> None:
        self._scripts = scripts
        self._store = store

    def run(self, *, only_if_changed: bool) -> BootRecord:
        """Run every script in order; a failure is recorded and the next script still runs."""
        listing = self._scripts.listing()
        digest = scripts_digest(listing)
        current = self._store.read()
        if only_if_changed and digest == current.init_digest:
            return current
        failed = tuple(script.name for script in listing if self._scripts.run(script) != 0)
        record = replace(self._store.read(), init_digest=digest, init_failed=failed)
        self._store.write(record)
        return record


class ProxyStartup:
    def __init__(self, runtime: ProxyRuntime, proxy: Proxy, trust: TrustStore) -> None:
        self._runtime = runtime
        self._proxy = proxy
        self._trust = trust

    def run(self) -> int:
        """Create or start the proxy, apply every saved route again, then trust its CA here.

        Applying the routes again rewrites their names when the domain changed. Trusting the
        CA lets programs in the container open the routes' URLs. Returns the routes' count.
        """
        self._runtime.ensure_running()
        self._proxy.wait_ready(PROXY_TIMEOUT)
        routes = self._proxy.routes()
        for route in routes:
            self._proxy.put(route)
        self._trust.trust(self._proxy.root_certificate())
        return len(routes)


class Boot:
    def __init__(
        self,
        *,
        proxy: ProxyStartup,
        init: Init,
        store: BootStore,
        ownership: Ownership,
        persisted: Sequence[PurePosixPath],
    ) -> None:
        self._proxy = proxy
        self._init = init
        self._store = store
        self._ownership = ownership
        self._persisted = tuple(persisted)

    def run(self) -> BootRecord:
        """Start the proxy, hand new volumes to dev, run the init scripts, then mark ready.

        Boot always ends ready, so `up` stops waiting: a proxy that does not start is raised
        afterwards, for the container's log, and `status` reports it.
        """
        boot = self._store.current_boot()
        self._store.write(replace(self._store.read(), ready=False, boot_id=boot))
        problem: OutpostError | None = None
        try:
            self._proxy.run()
        except Exception as error:  # any failure here must not keep the container from booting
            problem = error if isinstance(error, OutpostError) else Unavailable(str(error))
        try:
            for path in self._persisted:
                self._ownership.claim_if_empty(path)
            self._init.run(only_if_changed=False)
        finally:
            self._store.write(replace(self._store.read(), ready=True, boot_id=boot))
        if problem is not None:
            raise problem
        return self._store.read()


class Status:
    def __init__(self, proxy: Proxy, store: BootStore) -> None:
        self._proxy = proxy
        self._store = store

    def report(self) -> ContainerStatus:
        """Ready only when this start's boot has finished: an older record never counts."""
        record = self._store.read()
        running = self._proxy.running()
        return ContainerStatus(
            ready=record.ready and record.boot_id == self._store.current_boot(),
            proxy_running=running,
            routes=len(self._proxy.routes()) if running else 0,
            init_failed=record.init_failed,
        )
