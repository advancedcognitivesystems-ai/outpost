"""Composition root: the one module that turns configuration into concrete adapters."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path, PurePosixPath

from outpost.adapters.credentials.factory import build_secret_source, build_tool_auth
from outpost.adapters.engine.docker_cli import DockerCliEngine
from outpost.adapters.images.factory import build_image_supplier
from outpost.adapters.interaction.factory import build_prompter
from outpost.adapters.interaction.templates import PackageTemplates
from outpost.adapters.probe.factory import build_client_probe, build_host_probe
from outpost.adapters.proxy.traefik import TraefikEdge, TraefikRouter
from outpost.adapters.repository.git_cli import GitRepository
from outpost.adapters.shell.container import ContainerShell
from outpost.adapters.shell.factory import build_client_shell, build_host_shell
from outpost.adapters.shell.tracing import TracingShell
from outpost.adapters.stacks.compose import ComposeStacks
from outpost.adapters.tls.factory import build_tls
from outpost.application.box import BoxImage
from outpost.application.checks import standard_checks
from outpost.application.credentials import CredentialBinding, CredentialSync
from outpost.application.doctor import Doctor
from outpost.application.environment import Environment
from outpost.application.session import BoxSession
from outpost.application.stacks import Stacks
from outpost.application.worktrees import Worktrees
from outpost.config import load_config
from outpost.domain.config import ResolvedConfig, ToolCredentials
from outpost.domain.errors import NotImplementedYet
from outpost.domain.resources import Role
from outpost.ports.engine import ContainerEngine
from outpost.ports.interaction import Prompter
from outpost.ports.probe import MachineProbe
from outpost.ports.repository import Repository
from outpost.ports.shell import Shell
from outpost.ports.stacks import StackRunner


@dataclass(frozen=True)
class Options:
    config_path: Path
    target: str | None
    assume_yes: bool
    verbose: bool
    dry_run: bool


def standalone_prompter(*, assume_yes: bool) -> Prompter:
    """For commands that run before a configuration exists, such as `init`."""
    return build_prompter(assume_yes=assume_yes)


class App:
    """Builds each adapter once, on first use, and hands use cases only the ports they need."""

    def __init__(self, options: Options, environ: Mapping[str, str] = os.environ) -> None:
        if options.dry_run:
            raise NotImplementedYet("--dry-run is designed but not built yet")
        self.options = options
        self.config: ResolvedConfig = load_config(options.config_path).resolve(options.target)
        self._environ = environ

    # ---------------------------------------------------------------- machines

    @cached_property
    def prompter(self) -> Prompter:
        return build_prompter(assume_yes=self.options.assume_yes)

    def _traced(self, shell: Shell) -> Shell:
        return TracingShell(shell, self.prompter.info) if self.options.verbose else shell

    @cached_property
    def client_shell(self) -> Shell:
        return self._traced(build_client_shell())

    @cached_property
    def host_shell(self) -> Shell:
        return self._traced(build_host_shell(self.config.target.connection))

    @cached_property
    def client_engine(self) -> ContainerEngine:
        return DockerCliEngine(self.client_shell)

    @cached_property
    def host_engine(self) -> ContainerEngine:
        return DockerCliEngine(self.host_shell)

    @cached_property
    def box_shell(self) -> Shell:
        box = self.config.resources.name(Role.BOX)
        return ContainerShell(self.host_engine, self.host_shell, box, self.config.box.user)

    @cached_property
    def host_probe(self) -> MachineProbe:
        return build_host_probe(self.config.target.connection, self.host_shell)

    # ---------------------------------------------------------------- credentials

    def _binding(self, spec: ToolCredentials) -> CredentialBinding:
        setup_git = self.config.credentials.setup_git
        return CredentialBinding(
            spec=spec,
            source=build_secret_source(spec.source, spec.tool, self.client_shell, self._environ),
            box=build_tool_auth(
                spec.tool, self.box_shell, self.config.box_layout.home, setup_git=setup_git
            ),
            client=build_tool_auth(
                spec.tool, self.client_shell, PurePosixPath(Path.home()), setup_git=False
            ),
        )

    @cached_property
    def credentials(self) -> CredentialSync:
        bindings = [self._binding(spec) for spec in self.config.credentials.tools]
        return CredentialSync(bindings, self.prompter)

    # ---------------------------------------------------------------- use cases

    @cached_property
    def doctor(self) -> Doctor:
        checks = standard_checks(
            self.config,
            client=build_client_probe(),
            host=self.host_probe,
            host_description=self.host_shell.description,
            engine=self.host_engine,
            credentials=self.credentials,
        )
        return Doctor(checks, self.prompter)

    @cached_property
    def repository(self) -> Repository:
        return GitRepository(self.box_shell, self.config.box_layout)

    @cached_property
    def stack_runner(self) -> StackRunner:
        return ComposeStacks(self.box_shell, TraefikRouter(), self.config.box_layout)

    @cached_property
    def environment(self) -> Environment:
        config = self.config
        target = config.target
        return Environment(
            config=config,
            doctor=self.doctor,
            host=self.host_shell,
            host_probe=self.host_probe,
            engine=self.host_engine,
            images=build_image_supplier(
                config.box.image,
                client=self.client_shell,
                client_engine=self.client_engine,
                host=self.host_shell,
                host_engine=self.host_engine,
                same_machine=target.runs_on_client,
                environ=self._environ,
            ),
            box_image=BoxImage(
                config, self.host_shell, self.host_engine, PackageTemplates(), TraefikRouter()
            ),
            tls=build_tls(
                target.edge.tls, self.host_shell, target.edge.domain, config.project.name
            ),
            edge=TraefikEdge(
                self.host_shell, config.resources, target.edge, config.resources.name(Role.BOX)
            ),
            credentials=self.credentials,
            repository=self.repository,
            prompter=self.prompter,
        )

    @cached_property
    def worktrees(self) -> Worktrees:
        return Worktrees(self.config, self.repository, self.stack_runner)

    @cached_property
    def stacks(self) -> Stacks:
        return Stacks(self.config, self.stack_runner, self.worktrees)

    @cached_property
    def session(self) -> BoxSession:
        return BoxSession(self.box_shell, self.config.box_layout, self.worktrees)
