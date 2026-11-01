"""`DevContainerCli` through the reference `devcontainer` CLI, on the same Docker as `DockerCli`."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePath

from outpost.domain.devcontainer import DevContainerDefinition
from outpost.domain.errors import CommandFailed, Unavailable
from outpost.infra.process import COMMAND_NOT_FOUND, Runner
from outpost.launcher.ports.devcontainer import INSTALL

CONFIG_FILE = "devcontainer.json"


class DevContainerCliAdapter:
    def __init__(self, runner: Runner, *, environment: Mapping[str, str] | None = None) -> None:
        self._runner = runner
        self._environment = environment

    def version(self) -> str | None:
        result = self._runner.run(["devcontainer", "--version"], env=self._environment)
        if not result.ok:
            return None
        return result.stdout.strip() or None

    def up(
        self,
        definition: DevContainerDefinition,
        workdir: PurePath,
        id_label: str,
        *,
        recreate: bool,
    ) -> None:
        directory = Path(workdir)
        directory.mkdir(parents=True, exist_ok=True)
        config = directory / CONFIG_FILE
        config.write_text(definition.text(), encoding="utf-8")
        argv = [
            "devcontainer",
            "up",
            "--workspace-folder",
            str(directory),
            "--config",
            str(config),
            "--id-label",
            id_label,
        ]
        if recreate:
            argv.append("--remove-existing-container")
        code = self._runner.attached(argv, env=self._environment)
        if code == COMMAND_NOT_FOUND:
            raise Unavailable(f"the Dev Container CLI is not installed: {INSTALL}")
        if code != 0:
            raise CommandFailed(argv, code, "see the output above")
