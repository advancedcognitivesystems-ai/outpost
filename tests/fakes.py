"""One in-memory fake per port, plus a fake `Runner` for adapters. Fakes log to a shared list,
so tests can assert the order of effects."""

from __future__ import annotations

import io
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import PurePath, PurePosixPath
from typing import IO

from outpost.domain.credentials import LoginState, Tool
from outpost.domain.devcontainer import DevContainerDefinition
from outpost.domain.errors import CommandFailed, Unavailable
from outpost.domain.exposure import Exposure, Published
from outpost.domain.host import SshHost
from outpost.domain.init import Script
from outpost.domain.names import DnsName, ImageRef
from outpost.domain.routes import Route
from outpost.domain.secrets import Secret
from outpost.domain.status import BootRecord, ContainerStatus
from outpost.domain.volumes import Volume
from outpost.infra.process import CommandResult
from outpost.launcher.ports.docker import ContainerInfo, ContainerState

type Events = list[str]


def ok(stdout: str = "", argv: Sequence[str] = ()) -> CommandResult:
    return CommandResult(tuple(argv), 0, stdout, "")


def failed(code: int = 1, stderr: str = "failed", argv: Sequence[str] = ()) -> CommandResult:
    return CommandResult(tuple(argv), code, "", stderr)


# ------------------------------------------------------------------ processes


@dataclass
class Call:
    argv: tuple[str, ...]
    env: Mapping[str, str] | None
    stdin: str | None = None
    fed: bytes = b""


class FakeRunner:
    """Answers by the longest matching argument prefix; unknown commands succeed silently."""

    def __init__(self) -> None:
        self.calls: list[Call] = []
        self._answers: dict[tuple[str, ...], CommandResult] = {}
        self.attached_codes: dict[tuple[str, ...], int] = {}
        self.drained: bytes = b""

    def answer(self, prefix: Sequence[str], result: CommandResult) -> None:
        self._answers[tuple(prefix)] = result

    def argvs(self) -> list[tuple[str, ...]]:
        return [call.argv for call in self.calls]

    def _result(self, argv: Sequence[str]) -> CommandResult:
        matches = [prefix for prefix in self._answers if tuple(argv[: len(prefix)]) == prefix]
        if not matches:
            return CommandResult(tuple(argv), 0)
        found = self._answers[max(matches, key=len)]
        return CommandResult(tuple(argv), found.code, found.stdout, found.stderr)

    def run(
        self, argv: Sequence[str], *, env: Mapping[str, str] | None = None, stdin: str | None = None
    ) -> CommandResult:
        self.calls.append(Call(tuple(argv), env, stdin))
        return self._result(argv)

    def attached(self, argv: Sequence[str], *, env: Mapping[str, str] | None = None) -> int:
        self.calls.append(Call(tuple(argv), env))
        matches = [p for p in self.attached_codes if tuple(argv[: len(p)]) == p]
        return self.attached_codes[max(matches, key=len)] if matches else 0

    def feed(
        self,
        argv: Sequence[str],
        write: Callable[[IO[bytes]], None],
        *,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        buffer = io.BytesIO()
        write(buffer)
        self.calls.append(Call(tuple(argv), env, fed=buffer.getvalue()))
        return self._result(argv)

    def drain(
        self,
        argv: Sequence[str],
        read: Callable[[IO[bytes]], None],
        *,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        self.calls.append(Call(tuple(argv), env))
        read(io.BytesIO(self.drained))
        return self._result(argv)

    def pipe(
        self,
        producer: Sequence[str],
        consumer: Sequence[str],
        *,
        env: Mapping[str, str] | None,
        consumer_env: Mapping[str, str] | None,
    ) -> CommandResult:
        self.calls.append(Call(tuple(producer), env))
        self.calls.append(Call(tuple(consumer), consumer_env))
        return self._result(consumer)


# ------------------------------------------------------------------ launcher ports


class FakeDocker:
    def __init__(self, events: Events, *, description: str = "local", reachable: bool = True):
        self.events = events
        self._description = description
        self.reachable = reachable
        self.containers: dict[str, ContainerInfo] = {}
        self.images: set[str] = set()
        self.volume_labels: dict[str, dict[str, str]] = {}
        self.directories: set[str] = set()
        self.exposed = Exposure((), "outpost", (Published("127.0.0.1", "8443", "443/tcp"),))
        self.copies: list[tuple[str, str, str, str, str]] = []
        self.attached_code = 0

    @property
    def description(self) -> str:
        return self._description

    def server_version(self) -> str:
        self.events.append("docker.version")
        if not self.reachable:
            raise Unavailable(f"Docker on {self._description} does not answer")
        return "28.0.0"

    def container(self, name: str) -> ContainerInfo:
        return self.containers.get(name, ContainerInfo(ContainerState.MISSING))

    def image_exists(self, image: ImageRef) -> bool:
        return image.value in self.images

    def build_image(self, image: ImageRef, context: PurePath, dockerfile: PurePath) -> None:
        self.events.append(f"build {image}")
        self.images.add(image.value)

    def exposure(self, container: str) -> Exposure:
        return self.exposed

    def ensure_volume(self, volume: Volume, labels: Mapping[str, str]) -> None:
        self.events.append(f"volume {volume.name}")
        self.volume_labels.setdefault(volume.name, dict(labels))

    def volumes(self, labels: Mapping[str, str]) -> tuple[str, ...]:
        return tuple(
            sorted(
                name
                for name, own in self.volume_labels.items()
                if all(own.get(key) == value for key, value in labels.items())
            )
        )

    def remove_volumes(self, names: Sequence[str]) -> None:
        self.events.append(f"rm volumes {' '.join(names)}")
        for name in names:
            self.volume_labels.pop(name, None)

    def stop(self, container: str) -> None:
        self.events.append(f"stop {container}")
        self.containers[container] = ContainerInfo(ContainerState.STOPPED)

    def remove(self, container: str) -> None:
        self.events.append(f"rm {container}")
        self.containers.pop(container, None)

    def is_directory(self, container: str, path: PurePosixPath) -> bool:
        return str(path) in self.directories

    def reset_directory(self, container: str, path: PurePosixPath, *, user: str) -> None:
        self.events.append(f"reset {path} for {user}")

    def exec_attached(
        self, container: str, argv: Sequence[str], *, user: str, workdir: PurePosixPath
    ) -> int:
        self.events.append(f"attached {' '.join(argv)} as {user} in {workdir}")
        return self.attached_code

    def copy_in(
        self, container: str, source: PurePath, directory: PurePosixPath, name: str, *, user: str
    ) -> None:
        self.events.append(f"copy in {source} -> {directory / name} as {user}")
        self.copies.append(("in", str(source), str(directory), name, user))

    def copy_out(
        self, container: str, source: PurePosixPath, directory: PurePath, name: str, *, user: str
    ) -> None:
        self.events.append(f"copy out {source} -> {directory / name}")
        self.copies.append(("out", str(source), str(directory), name, user))

    def logs(self, container: str, *, follow: bool) -> int:
        return 0


class FakeImages:
    def __init__(self, events: Events, docker: FakeDocker, images: Sequence[str] = ()) -> None:
        self.events = events
        self.docker = docker
        self.images = set(images)

    @property
    def description(self) -> str:
        return "your Docker"

    def available(self, image: ImageRef) -> bool:
        return image.value in self.images

    def send(self, image: ImageRef) -> None:
        self.events.append(f"send {image}")
        self.docker.images.add(image.value)


class FakeDevContainer:
    def __init__(self, events: Events, docker: FakeDocker, *, installed: bool = True) -> None:
        self.events = events
        self.docker = docker
        self.installed = installed
        self.definitions: list[DevContainerDefinition] = []
        self.recreated: list[bool] = []

    def version(self) -> str | None:
        return "0.80.0" if self.installed else None

    def up(
        self,
        definition: DevContainerDefinition,
        workdir: PurePath,
        id_label: str,
        *,
        recreate: bool,
    ) -> None:
        self.events.append(f"devcontainer up recreate={recreate}")
        self.definitions.append(definition)
        self.recreated.append(recreate)
        name = str(definition.document["name"])
        self.docker.containers[name] = ContainerInfo(
            ContainerState.RUNNING, definition.settings_digest
        )


class FakeRuntime:
    def __init__(
        self, events: Events, status: ContainerStatus | None = None, *, proxy_starts: bool = True
    ) -> None:
        self.events = events
        self.current = status or ContainerStatus(ready=True, proxy_running=True, routes=0)
        self.certificate = "-----BEGIN CERTIFICATE-----\nAAA\n-----END CERTIFICATE-----\n"
        self.proxy_starts = proxy_starts

    def wait_ready(self, container: str, timeout: float) -> ContainerStatus:
        self.events.append("wait ready")
        return self.current

    def status(self, container: str) -> ContainerStatus:
        return self.current

    def routes(self, container: str) -> str:
        if not self.current.proxy_running:
            raise Unavailable("the proxy's API does not answer")
        return "https://api.feat-a.dev.localhost:8443  ->  feat-a-api-1:8080\n"

    def start_proxy(self, container: str) -> ContainerStatus:
        self.events.append("start proxy")
        if not self.proxy_starts:
            raise Unavailable("caddy:2.11 cannot be pulled")
        self.current = replace(self.current, proxy_running=True)
        return self.current

    def run_init(self, container: str) -> ContainerStatus:
        self.events.append("run init")
        return self.current

    def root_certificate(self, container: str) -> str:
        return self.certificate


BASE = ImageRef("outpost/base:0123456789ab")
CHECKOUT = PurePath("/outpost")


@dataclass
class FakeBaseImage:
    ref: ImageRef = BASE
    context: PurePath = CHECKOUT
    dockerfile: PurePath = CHECKOUT / "image" / "Dockerfile"

    def reference(self) -> ImageRef:
        return self.ref


class FakeConsole:
    def __init__(
        self, *, answers: Sequence[bool] = (), text: str = "", interactive: bool = True
    ) -> None:
        self.answers = list(answers)
        self.text = text
        self._interactive = interactive
        self.questions: list[str] = []
        self.messages: list[str] = []
        self.warnings: list[str] = []

    @property
    def interactive(self) -> bool:
        return self._interactive

    def info(self, message: str) -> None:
        self.messages.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def confirm(self, question: str, *, default: bool) -> bool:
        self.questions.append(question)
        return self.answers.pop(0) if self.answers else default

    def ask(self, question: str) -> str:
        self.questions.append(question)
        return self.text


@dataclass
class FakeSource:
    secret: Secret | None = None
    description: str = "a test source"

    def read(self) -> Secret | None:
        return self.secret


@dataclass
class FakeLogin:
    tool: Tool
    states: list[LoginState]
    events: Events = field(default_factory=list)
    installed: list[Secret] = field(default_factory=list)

    def state(self) -> LoginState:
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]

    refuse: bool = False

    def install(self, secret: Secret) -> None:
        self.events.append(f"install {self.tool}")
        if self.refuse:
            raise CommandFailed(["gh", "auth", "login"], 1, "the token is not valid")
        self.installed.append(secret)

    def login(self) -> None:
        self.events.append(f"login {self.tool}")

    def finish(self) -> None:
        self.events.append(f"finish {self.tool}")


@dataclass
class FakeFiles:
    existing: set[str] = field(default_factory=set)
    directories: set[str] = field(default_factory=set)

    def is_dir(self, path: PurePath) -> bool:
        return str(path) in self.directories

    def exists(self, path: PurePath) -> bool:
        return str(path) in self.existing or str(path) in self.directories


@dataclass
class FakeTunnel:
    forwarded: list[tuple[str, int]] = field(default_factory=list)

    def forward(self, host: SshHost, port: int) -> int:
        self.forwarded.append((str(host), port))
        return 0


@dataclass
class FakePrograms:
    versions: dict[str, str] = field(default_factory=dict)

    def version(self, argv: Sequence[str]) -> str | None:
        return self.versions.get(argv[0])


# ------------------------------------------------------------------ container ports


class FakeProxy:
    def __init__(self, events: Events, *, running: bool = True) -> None:
        self.events = events
        self.is_running = running
        self.table: dict[str, Route] = {}
        self.fail_ready = False

    def running(self) -> bool:
        return self.is_running

    def wait_ready(self, timeout: float) -> None:
        self.events.append("proxy ready")
        if self.fail_ready:
            raise Unavailable("the proxy's API did not answer")

    def routes(self) -> tuple[Route, ...]:
        return tuple(self.table.values())

    def put(self, route: Route) -> None:
        self.events.append(f"put {route.name} {route.upstream}")
        self.table[route.name.value] = route

    def remove(self, name: DnsName) -> None:
        self.events.append(f"remove {name}")
        del self.table[name.value]

    def root_certificate(self) -> str:
        return "PEM"


@dataclass
class FakeProxyRuntime:
    events: Events

    def ensure_running(self) -> None:
        self.events.append("proxy running")


@dataclass
class FakeTrust:
    events: Events
    trusted: list[str] = field(default_factory=list)

    def trust(self, certificate: str) -> bool:
        self.events.append(f"trust {certificate}")
        changed = certificate not in self.trusted
        self.trusted.append(certificate)
        return changed


@dataclass
class FakeEngine:
    events: Events
    containers: dict[str, list[str]] = field(default_factory=dict)

    def is_container(self, name: str) -> bool:
        return name in self.containers

    def networks(self, container: str) -> tuple[str, ...]:
        return tuple(self.containers[container])

    def connect(self, network: str, container: str) -> None:
        self.events.append(f"connect {container} to {network}")
        self.containers[container].append(network)


@dataclass
class FakeScripts:
    events: Events
    scripts: list[Script] = field(default_factory=list)
    codes: dict[str, int] = field(default_factory=dict)

    def listing(self) -> tuple[Script, ...]:
        return tuple(self.scripts)

    def run(self, script: Script) -> int:
        self.events.append(f"run {script.name}")
        return self.codes.get(script.name, 0)


@dataclass
class FakeOwnership:
    events: Events

    def claim_if_empty(self, path: PurePosixPath) -> None:
        self.events.append(f"claim {path}")


@dataclass
class FakeStore:
    record: BootRecord = field(default_factory=lambda: BootRecord(ready=False))
    writes: list[BootRecord] = field(default_factory=list)
    boot: str = "boot-1"

    def current_boot(self) -> str:
        return self.boot

    def read(self) -> BootRecord:
        return self.record

    def write(self, record: BootRecord) -> None:
        self.record = record
        self.writes.append(record)
