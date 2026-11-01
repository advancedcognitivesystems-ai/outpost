"""What runs at every start of the container, after the entrypoint starts the inner Docker."""

from __future__ import annotations

from dataclasses import replace

from outpost.container.ports.init import BootStore, Scripts
from outpost.container.ports.proxy import Proxy, ProxyRuntime
from outpost.domain.errors import OutpostError
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
        record = replace(current, init_digest=digest, init_failed=failed)
        self._store.write(record)
        return record


class Boot:
    def __init__(self, runtime: ProxyRuntime, proxy: Proxy, init: Init, store: BootStore) -> None:
        self._runtime = runtime
        self._proxy = proxy
        self._init = init
        self._store = store

    def run(self) -> BootRecord:
        """Start the proxy, run the init scripts, then mark the container ready.

        A proxy that does not start still lets init run and boot finish, so `up` stops waiting
        and reports it; the error is raised afterwards, for the container's log.
        """
        self._store.write(replace(self._store.read(), ready=False))
        problem: OutpostError | None = None
        try:
            self._runtime.ensure_running()
            self._proxy.wait_ready(PROXY_TIMEOUT)
        except OutpostError as error:
            problem = error
        record = replace(self._init.run(only_if_changed=False), ready=True)
        self._store.write(record)
        if problem is not None:
            raise problem
        return record


class Status:
    def __init__(self, proxy: Proxy, store: BootStore) -> None:
        self._proxy = proxy
        self._store = store

    def report(self) -> ContainerStatus:
        record = self._store.read()
        running = self._proxy.running()
        return ContainerStatus(
            ready=record.ready,
            proxy_running=running,
            routes=len(self._proxy.routes()) if running else 0,
            init_failed=record.init_failed,
        )
