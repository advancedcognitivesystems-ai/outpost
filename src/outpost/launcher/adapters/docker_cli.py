"""`DockerHost` through the Docker CLI. A remote host is reached with `DOCKER_HOST=ssh://...`."""

from __future__ import annotations

import json
import tarfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePath, PurePosixPath
from typing import IO

from outpost.domain.errors import CommandFailed, Unavailable, last_line
from outpost.domain.exposure import Exposure, Mount, Published
from outpost.domain.layout import ROOT_USER, SETTINGS_LABEL
from outpost.domain.names import ImageRef
from outpost.domain.volumes import Volume
from outpost.infra.process import CommandResult, Runner
from outpost.launcher.adapters.archive import extract_archive, write_archive
from outpost.launcher.ports.docker import ContainerInfo, ContainerState

EXTRACT = 'mkdir -p "$1" && tar -x --no-same-owner --warning=no-timestamp -f - -C "$1"'
RESET = 'rm -rf "$1" && mkdir -p "$1" && chown "$2" "$1"'
_STATES = {"running": ContainerState.RUNNING, "restarting": ContainerState.RESTARTING}


class DockerCli:
    def __init__(
        self,
        runner: Runner,
        *,
        description: str,
        environment: Mapping[str, str] | None = None,
        terminal: bool = False,
    ) -> None:
        self._runner = runner
        self._description = description
        self.environment = dict(environment) if environment else None
        self._terminal = terminal

    @property
    def description(self) -> str:
        return self._description

    def server_version(self) -> str:
        result = self._run("version", "--format", "{{.Server.Version}}")
        if result.missing_command:
            raise Unavailable("the docker CLI is not installed on your machine")
        if not result.ok:
            detail = last_line(result.stderr)
            raise Unavailable(f"Docker on {self._description} does not answer: {detail}")
        return result.stdout.strip()

    def container(self, name: str) -> ContainerInfo:
        template = f'{{{{.State.Status}}}} {{{{index .Config.Labels "{SETTINGS_LABEL}"}}}}'
        result = self._run("container", "inspect", "--format", template, name)
        if not result.ok and "no such" in result.stderr.lower():
            return ContainerInfo(ContainerState.MISSING)
        status, _, digest = result.check().stdout.strip().partition(" ")
        state = _STATES.get(status, ContainerState.STOPPED)
        return ContainerInfo(state, digest or None, status)

    def exposure(self, container: str) -> Exposure:
        result = self._run("container", "inspect", "--format", "{{json .}}", container).check()
        data = json.loads(result.stdout)
        host = data.get("HostConfig") or {}
        mounts = tuple(
            Mount(str(item.get("Type", "")), str(item.get("Destination", "")))
            for item in data.get("Mounts") or []
        )
        published = tuple(
            Published(str(binding.get("HostIp", "")), str(binding.get("HostPort", "")), port)
            for port, bindings in (host.get("PortBindings") or {}).items()
            for binding in bindings or []
        )
        return Exposure(mounts, str(host.get("NetworkMode", "")), published)

    def image_exists(self, image: ImageRef) -> bool:
        return self._run("image", "inspect", "--format", "{{.Id}}", image.value).ok

    def build_image(self, image: ImageRef, context: PurePath, dockerfile: PurePath) -> None:
        argv = ["docker", "build", "--file", str(dockerfile), "--tag", image.value, str(context)]
        code = self._runner.attached(argv, env=self.environment)
        if code != 0:
            raise CommandFailed(argv, code, "see the output above")

    def ensure_volume(self, volume: Volume, labels: Mapping[str, str]) -> None:
        if self._run("volume", "inspect", volume.name).ok:
            return
        flags = [item for key, value in labels.items() for item in ("--label", f"{key}={value}")]
        self._run("volume", "create", *flags, volume.name).check()

    def volumes(self, labels: Mapping[str, str]) -> tuple[str, ...]:
        filters = [
            item for key, value in labels.items() for item in ("--filter", f"label={key}={value}")
        ]
        result = self._run("volume", "ls", "--quiet", *filters).check()
        return tuple(sorted(line for line in result.stdout.split() if line))

    def remove_volumes(self, names: Sequence[str]) -> None:
        self._run("volume", "rm", *names).check()

    def stop(self, container: str) -> None:
        self._run("stop", container).check()

    def remove(self, container: str) -> None:
        self._run("rm", "--force", container).check()

    def exec(
        self, container: str, argv: Sequence[str], *, user: str, stdin: str | None = None
    ) -> CommandResult:
        """Run a program in the container and capture its output; for other adapters."""
        interactive = ["--interactive"] if stdin is not None else []
        return self._runner.run(
            ["docker", "exec", *interactive, "--user", user, container, *argv],
            env=self.environment,
            stdin=stdin,
        )

    def exec_attached(
        self, container: str, argv: Sequence[str], *, user: str, workdir: PurePosixPath
    ) -> int:
        tty = ["--interactive", "--tty"] if self._terminal else ["--interactive"]
        command = ["docker", "exec", *tty, "--user", user, "--workdir", str(workdir), container]
        return self._runner.attached([*command, *argv], env=self.environment)

    def is_directory(self, container: str, path: PurePosixPath) -> bool:
        return self.exec(container, ["test", "-d", str(path)], user=ROOT_USER).ok

    def reset_directory(self, container: str, path: PurePosixPath, *, user: str) -> None:
        self.exec(container, ["sh", "-c", RESET, "sh", str(path), user], user=ROOT_USER).check()

    def copy_in(
        self, container: str, source: PurePath, directory: PurePosixPath, name: str, *, user: str
    ) -> None:
        argv = ["docker", "exec", "--interactive", "--user", user, container]
        argv += ["sh", "-c", EXTRACT, "sh", str(directory)]
        problems: list[str] = []

        def write(out: IO[bytes]) -> None:
            try:
                write_archive(Path(source), name, out)
            except (tarfile.TarError, OSError) as error:
                if isinstance(error, BrokenPipeError):
                    raise
                problems.append(str(error))

        result = self._runner.feed(argv, write, env=self.environment)
        if problems:
            raise Unavailable(f"could not read {source}: {problems[0]}")
        result.check()

    def copy_out(
        self, container: str, source: PurePosixPath, directory: PurePath, name: str, *, user: str
    ) -> None:
        argv = ["docker", "exec", "--user", user, container]
        argv += ["tar", "-c", "-f", "-", "-C", str(source.parent), source.name]
        problems: list[str] = []

        def read(stream: IO[bytes]) -> None:
            try:
                extract_archive(stream, Path(directory), name)
            except (tarfile.TarError, OSError) as error:
                problems.append(str(error))
                while stream.read(1 << 16):
                    pass

        self._runner.drain(argv, read, env=self.environment).check()
        if problems:
            raise Unavailable(f"could not write {Path(directory) / name}: {problems[0]}")

    def logs(self, container: str, *, follow: bool) -> int:
        return self._runner.attached(
            ["docker", "logs", *(["--follow"] if follow else []), container], env=self.environment
        )

    def _run(self, *argv: str) -> CommandResult:
        return self._runner.run(["docker", *argv], env=self.environment)


class ImagePipe:
    """`ImageTransfer`: `docker save` on your machine piped into `docker load` on the host."""

    def __init__(self, runner: Runner, *, mine: DockerCli, host: DockerCli) -> None:
        self._runner = runner
        self._mine = mine
        self._host = host

    @property
    def description(self) -> str:
        return self._mine.description

    def available(self, image: ImageRef) -> bool:
        return self._mine.image_exists(image)

    def send(self, image: ImageRef) -> None:
        self._runner.pipe(
            ["docker", "save", image.value],
            ["docker", "load"],
            env=self._mine.environment,
            consumer_env=self._host.environment,
        ).check()
