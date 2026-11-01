"""The Docker CLI, run through any shell: the client's, the host's, or the box's."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from outpost.domain.config import Isolation
from outpost.domain.names import ImageRef
from outpost.domain.secrets import Secret
from outpost.ports.engine import ContainerSpec, ContainerState
from outpost.ports.shell import CommandResult, Shell

DOCKER = "docker"
_ISOLATION_FLAGS: dict[Isolation, tuple[str, ...]] = {
    Isolation.SYSBOX: ("--runtime", "sysbox-runc"),
    Isolation.PRIVILEGED: ("--privileged",),
}
_REQUIRED_RUNTIME: dict[Isolation, str] = {Isolation.SYSBOX: "sysbox-runc"}


class DockerCliEngine:
    def __init__(self, shell: Shell) -> None:
        self._shell = shell

    def _docker(self, *args: str, stdin: str | None = None) -> CommandResult:
        return self._shell.run([DOCKER, *args], stdin=stdin)

    def _inspect(self, container: str, template: str) -> str | None:
        result = self._docker("container", "inspect", "--format", template, container)
        return result.stdout.strip() if result.ok else None

    def version(self) -> str | None:
        result = self._docker("version", "--format", "{{.Server.Version}}")
        if not result.ok:
            return None
        return result.stdout.strip() or None

    def supports(self, isolation: Isolation) -> bool:
        runtime = _REQUIRED_RUNTIME.get(isolation)
        if runtime is None:
            return True
        result = self._docker("info", "--format", "{{json .Runtimes}}")
        return result.ok and runtime in json.loads(result.stdout or "{}")

    def image_exists(self, ref: ImageRef) -> bool:
        return self._docker("image", "inspect", str(ref)).ok

    def pull(self, ref: ImageRef) -> None:
        self._docker("pull", str(ref)).check()

    def build(self, context: PurePosixPath, tag: ImageRef) -> None:
        self._docker("build", "--tag", str(tag), str(context)).check()

    def save(self, ref: ImageRef, archive: Path) -> None:
        self._docker("save", "--output", str(archive), str(ref)).check()

    def load(self, archive: PurePosixPath) -> None:
        self._docker("load", "--input", str(archive)).check()

    def login(self, registry: str, username: str, password: Secret) -> None:
        self._docker(
            "login", registry, "--username", username, "--password-stdin", stdin=password.reveal()
        ).check()

    def ensure_network(self, name: str) -> None:
        if not self._docker("network", "inspect", name).ok:
            self._docker("network", "create", name).check()

    def ensure_volume(self, name: str) -> None:
        if not self._docker("volume", "inspect", name).ok:
            self._docker("volume", "create", name).check()

    def state(self, container: str) -> ContainerState:
        running = self._inspect(container, "{{.State.Running}}")
        if running is None:
            return ContainerState.MISSING
        return ContainerState.RUNNING if running == "true" else ContainerState.STOPPED

    def label(self, container: str, key: str) -> str | None:
        labels = json.loads(self._inspect(container, "{{json .Config.Labels}}") or "null") or {}
        value = labels.get(key)
        return str(value) if value is not None else None

    def run(self, spec: ContainerSpec) -> None:
        self._docker(*run_arguments(spec)).check()

    def start(self, container: str) -> None:
        self._docker("container", "start", container).check()

    def stop(self, container: str) -> None:
        self._docker("container", "stop", container).check()

    def remove(self, container: str) -> None:
        self._docker("container", "rm", "--force", container).check()

    def exec(
        self,
        container: str,
        argv: Sequence[str],
        *,
        user: str | None = None,
        stdin: str | None = None,
    ) -> CommandResult:
        args = exec_arguments(container, argv, user=user, keep_stdin=stdin is not None)
        result = self._shell.run([DOCKER, *args], stdin=stdin)
        return CommandResult(tuple(argv), result.code, result.stdout, result.stderr)

    def exec_interactive(
        self, container: str, argv: Sequence[str], *, user: str | None = None
    ) -> int:
        args = exec_arguments(container, argv, user=user, keep_stdin=True, tty=True)
        return self._shell.run_interactive([DOCKER, *args])

    def copy_into(self, container: str, source: PurePosixPath, target: PurePosixPath) -> None:
        self._docker("container", "cp", str(source), f"{container}:{target}").check()


def run_arguments(spec: ContainerSpec) -> list[str]:
    """`docker run` arguments for a container spec, in a stable order."""
    args = ["run", "--detach", "--name", spec.name]
    if spec.hostname:
        args += ["--hostname", spec.hostname]
    if spec.restart_unless_stopped:
        args += ["--restart", "unless-stopped"]
    if spec.isolation is not None:
        args += _ISOLATION_FLAGS[spec.isolation]
    for mount in spec.mounts:
        option = f"type={mount.kind.value},source={mount.source},target={mount.target}"
        args += ["--mount", option + (",readonly" if mount.read_only else "")]
    for binding in spec.ports:
        args += ["--publish", f"{binding.host_ip}:{binding.host_port}:{binding.container_port}"]
    for network in spec.networks:
        args += ["--network", network]
    for name, value in sorted(spec.env.items()):
        args += ["--env", f"{name}={value}"]
    for key, value in sorted(spec.labels.items()):
        args += ["--label", f"{key}={value}"]
    if spec.cpus is not None:
        args += ["--cpus", f"{spec.cpus:g}"]
    if spec.memory_gb is not None:
        args += ["--memory", f"{spec.memory_gb}g"]
    return [*args, str(spec.image), *spec.command]


def exec_arguments(
    container: str,
    argv: Sequence[str],
    *,
    user: str | None,
    keep_stdin: bool,
    tty: bool = False,
) -> list[str]:
    args = ["exec"]
    if keep_stdin:
        args.append("--interactive")
    if tty:
        args.append("--tty")
    if user:
        args += ["--user", user]
    return [*args, container, *argv]
