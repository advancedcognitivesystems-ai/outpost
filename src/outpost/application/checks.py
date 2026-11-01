"""The checks `doctor` runs, and which of them a configuration needs."""

from __future__ import annotations

from collections.abc import Sequence

from outpost.application.credentials import CredentialSync
from outpost.application.doctor import Check
from outpost.domain.checks import CheckResult
from outpost.domain.config import (
    AcmeTls,
    AzureAcrAuth,
    CommandSource,
    ImageSource,
    Isolation,
    ResolvedConfig,
)
from outpost.domain.credentials import Strategy, Tool
from outpost.domain.names import Domain
from outpost.domain.resources import Role
from outpost.ports.engine import ContainerEngine, ContainerState
from outpost.ports.probe import MachineProbe


class ClientTools(Check):
    def __init__(self, probe: MachineProbe, tools: Sequence[str]) -> None:
        super().__init__("client-tools", "Tools on this machine")
        self._probe = probe
        self._tools = tuple(tools)

    def run(self) -> CheckResult:
        missing = [tool for tool in self._tools if not self._probe.has_command(tool)]
        if missing:
            return self.fail(f"missing: {', '.join(missing)}", "install them, then run again")
        return self.ok(", ".join(self._tools) or "none needed")


class HostReachable(Check):
    def __init__(self, probe: MachineProbe, description: str) -> None:
        super().__init__("host", "Host reachable")
        self._probe = probe
        self._description = description

    def run(self) -> CheckResult:
        if self._probe.reachable():
            return self.ok(self._description)
        return self.fail(
            f"cannot run commands through {self._description}",
            "check the connection settings and that ssh works without a password prompt",
        )


class EngineRunning(Check):
    def __init__(self, engine: ContainerEngine) -> None:
        super().__init__("engine", "Docker engine on the host", ("host",))
        self._engine = engine

    def run(self) -> CheckResult:
        version = self._engine.version()
        if version:
            return self.ok(f"Docker {version}")
        return self.fail(
            "no Docker engine answered", "install Docker Engine; add the user to the docker group"
        )


class IsolationAvailable(Check):
    def __init__(self, engine: ContainerEngine, isolation: Isolation) -> None:
        super().__init__("isolation", "Box isolation runtime", ("engine",))
        self._engine = engine
        self._isolation = isolation

    def run(self) -> CheckResult:
        if self._engine.supports(self._isolation):
            return self.ok(self._isolation.value)
        return self.fail(
            f"{self._isolation.value} is not available on the host",
            "install Sysbox, or set host.isolation: privileged for this target",
        )


class FreeDisk(Check):
    def __init__(self, probe: MachineProbe, path: str, minimum_gb: int) -> None:
        super().__init__("disk", "Free disk on the host", ("host",))
        self._probe = probe
        self._path = path
        self._minimum = minimum_gb

    def run(self) -> CheckResult:
        free = self._probe.free_disk_gb(self._path)
        if free is None:
            return self.warn(f"could not measure free space for {self._path}")
        if free < self._minimum:
            return self.fail(
                f"{free:.0f} GB free, {self._minimum} GB required",
                "free space, grow the disk, or lower host.min_free_disk_gb",
            )
        return self.ok(f"{free:.0f} GB free")


class WildcardDns(Check):
    PROBE_LABEL = "outpost-dns-check"

    def __init__(self, probe: MachineProbe, domain: Domain) -> None:
        super().__init__("dns", "Wildcard DNS record")
        self._probe = probe
        self._domain = domain

    def run(self) -> CheckResult:
        addresses = self._probe.resolve(f"{self.PROBE_LABEL}.{self._domain}")
        if addresses:
            return self.ok(f"*.{self._domain} resolves to {', '.join(addresses)}")
        return self.fail(
            f"*.{self._domain} does not resolve from this machine",
            f"create a DNS record *.{self._domain} pointing to the host's address",
        )


class BoxRunning(Check):
    def __init__(self, engine: ContainerEngine, container: str) -> None:
        super().__init__("box", "Box running", ("engine",))
        self._engine = engine
        self._container = container

    def run(self) -> CheckResult:
        state = self._engine.state(self._container)
        if state is ContainerState.RUNNING:
            return self.ok(self._container)
        return self.warn(f"{self._container} is {state.value}", "run `outpost up`")


class ToolLogin(Check):
    def __init__(self, credentials: CredentialSync, tool: Tool) -> None:
        super().__init__(f"auth-{tool.value}", f"{tool.value} logged in, in the box", ("box",))
        self._credentials = credentials
        self._tool = tool

    def run(self) -> CheckResult:
        state = self._credentials.state(self._tool)
        if state.valid:
            return self.ok(state.detail)
        return self.fail(state.detail or "not logged in", "run `outpost creds sync`", fixable=True)

    def fix(self) -> None:
        self._credentials.sync(only=self._tool)


def required_client_tools(config: ResolvedConfig) -> tuple[str, ...]:
    """Commands this configuration runs on the client, beyond Outpost's own."""
    tools: list[str] = []
    remote = not config.target.runs_on_client
    if remote:
        tools += ["ssh", "scp"]
    image = config.box.image
    if image.source is ImageSource.LOCAL and remote:
        tools.append("docker")
    if isinstance(image.auth, AzureAcrAuth):
        tools.append("az")
    for tool in config.credentials.tools:
        if tool.strategy is Strategy.COPY and isinstance(tool.source, CommandSource):
            tools.append(tool.source.argv[0])
    return tuple(dict.fromkeys(tools))


def standard_checks(
    config: ResolvedConfig,
    *,
    client: MachineProbe,
    host: MachineProbe,
    host_description: str,
    engine: ContainerEngine,
    credentials: CredentialSync,
) -> list[Check]:
    target = config.target
    checks: list[Check] = [ClientTools(client, required_client_tools(config))]
    if not target.runs_on_client:
        checks.append(HostReachable(host, host_description))
    checks += [
        EngineRunning(engine),
        IsolationAvailable(engine, target.host.isolation),
        FreeDisk(host, target.host.state_dir, target.host.min_free_disk_gb),
    ]
    if isinstance(target.edge.tls, AcmeTls):
        checks.append(WildcardDns(client, target.edge.domain))
    checks.append(BoxRunning(engine, config.resources.name(Role.BOX)))
    checks += [ToolLogin(credentials, tool) for tool in credentials.tools]
    return checks
