"""In-memory implementations of the ports, one per port, shared by every test."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from outpost.domain.config import GitIdentity, Isolation
from outpost.domain.credentials import AuthState, Tool
from outpost.domain.names import ImageRef, WorktreeName
from outpost.domain.resources import HostLayout
from outpost.domain.routes import Route
from outpost.domain.secrets import Secret
from outpost.domain.tls import Plaintext, TlsMaterial
from outpost.domain.worktrees import Worktree
from outpost.ports.engine import ContainerSpec, ContainerState
from outpost.ports.shell import CommandResult
from outpost.ports.stacks import StackDefinition


@dataclass
class _Response:
    prefix: tuple[str, ...]
    result: tuple[int, str, str]


class FakeShell:
    """Answers commands by longest matching argv prefix; records everything it is asked."""

    def __init__(self, description: str = "fake") -> None:
        self.description = description
        self.calls: list[tuple[str, ...]] = []
        self.stdins: list[str | None] = []
        self.interactive: list[tuple[str, ...]] = []
        self.interactive_code = 0
        self.files: dict[PurePosixPath, str] = {}
        self.modes: dict[PurePosixPath, int] = {}
        self.directories: set[PurePosixPath] = set()
        self._responses: list[_Response] = []

    def respond(self, *prefix: str, code: int = 0, stdout: str = "", stderr: str = "") -> None:
        self._responses.append(_Response(tuple(prefix), (code, stdout, stderr)))

    def _answer(self, argv: tuple[str, ...]) -> tuple[int, str, str]:
        matches = [item for item in self._responses if argv[: len(item.prefix)] == item.prefix]
        if not matches:
            return (0, "", "")
        return max(matches, key=lambda item: len(item.prefix)).result

    def run(
        self,
        argv: Sequence[str],
        *,
        stdin: str | None = None,
        cwd: PurePosixPath | None = None,
    ) -> CommandResult:
        call = tuple(argv)
        self.calls.append(call)
        self.stdins.append(stdin)
        code, stdout, stderr = self._answer(call)
        return CommandResult(call, code, stdout, stderr)

    def run_interactive(self, argv: Sequence[str], *, cwd: PurePosixPath | None = None) -> int:
        self.interactive.append(tuple(argv))
        return self.interactive_code

    def ensure_directory(self, path: PurePosixPath) -> None:
        self.directories.add(path)

    def write_file(self, path: PurePosixPath, content: str, *, mode: int = 0o644) -> None:
        self.files[path] = content
        self.modes[path] = mode

    def read_file(self, path: PurePosixPath) -> str | None:
        return self.files.get(path)

    def upload(self, source: Path, target: PurePosixPath) -> None:
        self.files[target] = source.read_text(encoding="utf-8")

    def ran(self, *prefix: str) -> bool:
        return any(call[: len(prefix)] == prefix for call in self.calls)


@dataclass
class FakeEngine:
    containers: dict[str, ContainerSpec] = field(default_factory=dict)
    running: set[str] = field(default_factory=set)
    images: set[str] = field(default_factory=set)
    networks: set[str] = field(default_factory=set)
    volumes: set[str] = field(default_factory=set)
    events: list[str] = field(default_factory=list)
    reachable: bool = True

    def version(self) -> str | None:
        return "27.0.0" if self.reachable else None

    def supports(self, isolation: Isolation) -> bool:
        return isolation is Isolation.PRIVILEGED

    def image_exists(self, ref: str) -> bool:
        return ref in self.images

    def pull(self, ref: str) -> None:
        self.events.append(f"pull {ref}")
        self.images.add(ref)

    def build(self, context: PurePosixPath, tag: str) -> None:
        self.events.append(f"build {tag}")
        self.images.add(tag)

    def save(self, ref: str, archive: Path) -> None:
        archive.write_text(ref, encoding="utf-8")

    def load(self, archive: PurePosixPath) -> None:
        self.events.append(f"load {archive}")

    def login(self, registry: str, username: str, password: Secret) -> None:
        self.events.append(f"login {registry} {username}")

    def ensure_network(self, name: str) -> None:
        self.networks.add(name)

    def ensure_volume(self, name: str) -> None:
        self.volumes.add(name)

    def state(self, container: str) -> ContainerState:
        if container not in self.containers:
            return ContainerState.MISSING
        return ContainerState.RUNNING if container in self.running else ContainerState.STOPPED

    def label(self, container: str, key: str) -> str | None:
        spec = self.containers.get(container)
        return spec.labels.get(key) if spec else None

    def run(self, spec: ContainerSpec) -> None:
        self.events.append(f"run {spec.name}")
        self.containers[spec.name] = spec
        self.running.add(spec.name)

    def start(self, container: str) -> None:
        self.events.append(f"start {container}")
        self.running.add(container)

    def stop(self, container: str) -> None:
        self.events.append(f"stop {container}")
        self.running.discard(container)

    def remove(self, container: str) -> None:
        self.events.append(f"remove {container}")
        self.containers.pop(container, None)
        self.running.discard(container)

    def exec(
        self,
        container: str,
        argv: Sequence[str],
        *,
        user: str | None = None,
        stdin: str | None = None,
        workdir: PurePosixPath | None = None,
    ) -> CommandResult:
        return CommandResult(tuple(argv), 0, "", "")

    def exec_interactive(
        self,
        container: str,
        argv: Sequence[str],
        *,
        user: str | None = None,
        workdir: PurePosixPath | None = None,
    ) -> int:
        return 0

    def copy_into(self, container: str, source: PurePosixPath, target: PurePosixPath) -> None:
        self.events.append(f"copy {source} {container}:{target}")


class FakePrompter:
    def __init__(self, *, confirms: Sequence[bool] = (), choices: Sequence[int] = ()) -> None:
        self.messages: list[str] = []
        self.questions: list[str] = []
        self._confirms = list(confirms)
        self._choices = list(choices)

    def info(self, message: str) -> None:
        self.messages.append(message)

    def warn(self, message: str) -> None:
        self.messages.append(f"warning: {message}")

    def confirm(self, question: str, *, default: bool) -> bool:
        self.questions.append(question)
        return self._confirms.pop(0) if self._confirms else default

    def choose(self, question: str, options: Sequence[str]) -> int:
        self.questions.append(question)
        return self._choices.pop(0) if self._choices else 0


class FakeSecretSource:
    def __init__(self, value: str | None, description: str = "fake source") -> None:
        self.value = value
        self.description = description

    def read(self) -> Secret | None:
        return Secret(self.value) if self.value else None


class FakeToolAuth:
    """Valid once something installs a secret or logs in."""

    def __init__(self, tool: Tool, *, valid: bool = False, login_works: bool = True) -> None:
        self.tool = tool
        self.valid = valid
        self.login_works = login_works
        self.installed: list[Secret] = []
        self.logins = 0
        self.finished = 0

    def state(self) -> AuthState:
        return AuthState(self.tool, self.valid, "logged in" if self.valid else "not logged in")

    def install(self, secret: Secret) -> None:
        self.installed.append(secret)
        self.valid = True

    def login(self) -> None:
        self.logins += 1
        self.valid = self.login_works

    def finish(self) -> None:
        self.finished += 1


class FakeProbe:
    def __init__(
        self, *, reachable: bool = True, free_gb: float | None = 500.0, commands: Sequence[str] = ()
    ) -> None:
        self._reachable = reachable
        self._free = free_gb
        self._commands = set(commands)
        self.addresses: dict[str, tuple[str, ...]] = {}

    def reachable(self) -> bool:
        return self._reachable

    def home(self) -> str:
        return "/home/dev"

    def has_command(self, name: str) -> bool:
        return name in self._commands

    def free_disk_gb(self, path: str) -> float | None:
        return self._free

    def resolve(self, hostname: str) -> tuple[str, ...]:
        return self.addresses.get(hostname, ())


@dataclass
class FakeRepository:
    cloned: bool = False
    items: list[Worktree] = field(default_factory=list)
    identity: GitIdentity | None = None
    removed: list[WorktreeName] = field(default_factory=list)

    def is_cloned(self) -> bool:
        return self.cloned

    def clone(self, url: str, branch: str) -> None:
        self.cloned = True

    def add_worktree(self, name: WorktreeName, branch: str, start_point: str) -> Worktree:
        created = Worktree(name, branch, PurePosixPath("/workspaces/acme/worktrees") / str(name))
        self.items.append(created)
        return created

    def remove_worktree(self, name: WorktreeName, *, force: bool) -> None:
        self.removed.append(name)
        self.items = [item for item in self.items if item.name != name]

    def worktrees(self) -> tuple[Worktree, ...]:
        return tuple(self.items)

    def set_identity(self, identity: GitIdentity) -> None:
        self.identity = identity


@dataclass
class FakeStackRunner:
    started: list[StackDefinition] = field(default_factory=list)
    stopped: list[WorktreeName] = field(default_factory=list)

    def up(self, stack: StackDefinition) -> None:
        self.started.append(stack)

    def down(self, worktree: WorktreeName) -> None:
        self.stopped.append(worktree)

    def running(self) -> tuple[WorktreeName, ...]:
        names = [stack.worktree for stack in self.started]
        return tuple(name for name in names if name not in self.stopped)

    def follow_logs(self, worktree: WorktreeName, service: str | None) -> int:
        return 0


class FakeRouter:
    network = "routes"

    def labels(self, route: Route) -> Mapping[str, str]:
        return {"route": route.hostname}

    def bootstrap_script(self) -> str:
        return "start-router"


class FakeImages:
    def __init__(self) -> None:
        self.ensured: list[ImageRef] = []

    def ensure(self, ref: ImageRef) -> None:
        self.ensured.append(ref)


class FakeTls:
    def prepare(self, layout: HostLayout) -> TlsMaterial:
        return Plaintext()

    def client_trust_bundle(self, layout: HostLayout) -> str | None:
        return None


class FakeEdge:
    def prepare(self, layout: HostLayout, material: TlsMaterial) -> ContainerSpec:
        return ContainerSpec(name="outpost-acme-edge", image="edge:1")


class EchoTemplates:
    def render(self, name: str, values: Mapping[str, str]) -> str:
        return f"{name}:" + ",".join(f"{key}={value}" for key, value in sorted(values.items()))
