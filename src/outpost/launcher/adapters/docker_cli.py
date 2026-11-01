"""`DockerHost` through the Docker CLI. A remote host is reached with `DOCKER_HOST=ssh://...`."""

from __future__ import annotations

import tarfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePath, PurePosixPath
from typing import IO

from outpost.domain.commands import CommandResult
from outpost.domain.errors import CommandFailed, Unavailable
from outpost.domain.layout import SETTINGS_LABEL
from outpost.domain.names import ImageRef
from outpost.domain.volumes import Volume
from outpost.infra.process import Runner
from outpost.launcher.adapters.archive import extract_archive, write_archive
from outpost.launcher.ports.docker import ContainerInfo, ContainerState, DockerHost

EXTRACT = 'mkdir -p "$1" && tar -x --no-same-owner -f - -C "$1"'


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
            detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else ""
            raise Unavailable(f"Docker on {self._description} does not answer: {detail}")
        return result.stdout.strip()

    def container(self, name: str) -> ContainerInfo:
        template = f'{{{{.State.Status}}}} {{{{index .Config.Labels "{SETTINGS_LABEL}"}}}}'
        result = self._run("container", "inspect", "--format", template, name)
        if not result.ok and "no such" in result.stderr.lower():
            return ContainerInfo(ContainerState.MISSING)
        status, _, digest = result.check().stdout.strip().partition(" ")
        state = ContainerState.RUNNING if status == "running" else ContainerState.STOPPED
        return ContainerInfo(state, digest or None)

    def image_exists(self, image: ImageRef) -> bool:
        return self._run("image", "inspect", "--format", "{{.Id}}", image.value).ok

    def build_image(self, image: ImageRef, context: PurePath, dockerfile: PurePath) -> None:
        argv = ["docker", "build", "--file", str(dockerfile), "--tag", image.value, str(context)]
        self._attached(argv)

    def load_image(self, image: ImageRef, source: DockerHost) -> None:
        if not isinstance(source, DockerCli):
            raise TypeError("images can only be copied between Docker CLI engines")
        self._runner.pipe(
            ["docker", "save", image.value],
            ["docker", "load"],
            env=source.environment,
            consumer_env=self.environment,
        ).check()

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

    def copy_in(
        self, container: str, source: PurePath, directory: PurePosixPath, name: str, *, user: str
    ) -> None:
        argv = ["docker", "exec", "--interactive", "--user", user, container]
        argv += ["sh", "-c", EXTRACT, "sh", str(directory)]

        def write(out: IO[bytes]) -> None:
            write_archive(Path(source), name, out)

        self._runner.feed(argv, write, env=self.environment).check()

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

    def _attached(self, argv: Sequence[str]) -> None:
        code = self._runner.attached(argv, env=self.environment)
        if code != 0:
            raise CommandFailed(argv, code, "see the output above")
