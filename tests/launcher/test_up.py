"""`./outpost up` from any state: what happens, and in which order."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from outpost.domain.credentials import LoginState, Tool
from outpost.domain.devcontainer import DevContainerSettings
from outpost.domain.environment import Environment, FileCopy
from outpost.domain.errors import ConfigError
from outpost.domain.exposure import Exposure, Mount
from outpost.domain.host import SshHost
from outpost.domain.status import ContainerStatus
from outpost.launcher.application.logins import Logins
from outpost.launcher.application.transfers import Transfers
from outpost.launcher.application.up import RECREATE_QUESTION, Up
from outpost.launcher.ports.docker import ContainerInfo, ContainerState
from tests.fakes import (
    Events,
    FakeBaseImage,
    FakeConsole,
    FakeDevContainer,
    FakeDocker,
    FakeFiles,
    FakeImages,
    FakeLogin,
    FakeRuntime,
    FakeSource,
)

ROOT = Path("/home/me/project")


class World:
    """An `Up` wired to fakes that share one event log."""

    def __init__(
        self,
        env: Environment | None = None,
        *,
        answers: tuple[bool, ...] = (),
        status: ContainerStatus | None = None,
        proxy_starts: bool = True,
    ) -> None:
        self.events: Events = []
        self.env = env or Environment(root=ROOT)
        self.docker = FakeDocker(self.events)
        self.mine = FakeImages(self.events, self.docker)
        self.devcontainer = FakeDevContainer(self.events, self.docker)
        self.console = FakeConsole(answers=answers)
        self.base = FakeBaseImage()
        self.files = FakeFiles(existing={"/home/me/project/init.sh", "/home/me/.npmrc"})
        valid = LoginState(Tool.GITHUB, True)
        self.login = FakeLogin(Tool.GITHUB, [valid], self.events)
        self.up = Up(
            self.env,
            docker=self.docker,
            images_from_you=self.mine if isinstance(self.env.host, SshHost) else None,
            devcontainer=self.devcontainer,
            runtime=FakeRuntime(self.events, status, proxy_starts=proxy_starts),
            base_image=self.base,
            console=self.console,
            logins=Logins(self.console, [(FakeSource(), self.login)]),
            transfers=Transfers(self.docker, self.files, self.env.container),
        )


def test_a_first_up_builds_then_creates_then_logs_in_then_inits() -> None:
    env = Environment(
        root=ROOT,
        init_scripts=(ROOT / "init.sh",),
        copies=(FileCopy(Path("/home/me/.npmrc"), PurePosixPath("/home/dev/.npmrc")),),
    )
    world = World(env)
    report = world.up.run()
    assert world.events == [
        "docker.version",
        "build outpost/base:0123456789ab",
        "volume outpost-main-home",
        "volume outpost-main-workspaces",
        "volume outpost-main-docker",
        "volume outpost-main-state",
        "devcontainer up recreate=False",
        "wait ready",
        "finish gh",
        "copy in /home/me/.npmrc -> /home/dev/.npmrc as dev",
        "reset /var/lib/outpost/init.d for root",
        "copy in /home/me/project/init.sh -> /var/lib/outpost/init.d/01-init.sh as root",
        "run init",
    ]
    assert report.example_url == "https://api.feat-a.dev.localhost:8443"
    assert world.docker.volume_labels["outpost-main-home"] == {"outpost.environment": "main"}


def test_the_base_image_is_built_only_when_missing() -> None:
    world = World()
    world.docker.images.add(world.base.ref.value)
    world.up.run()
    assert not any(event.startswith("build") for event in world.events)


def test_unchanged_settings_start_the_container_as_it_is() -> None:
    world = World()
    digest = world.up.plan().settings_digest
    world.docker.containers["outpost-main"] = ContainerInfo(ContainerState.STOPPED, digest)
    world.up.run()
    assert world.devcontainer.recreated == [False]
    assert world.console.questions == []


def test_changed_settings_ask_before_recreating() -> None:
    world = World(answers=(False,))
    world.docker.containers["outpost-main"] = ContainerInfo(ContainerState.RUNNING, "old")
    world.up.run()
    assert world.console.questions == [RECREATE_QUESTION]
    assert world.devcontainer.recreated == [False]
    assert world.console.warnings


def test_changed_settings_recreate_when_agreed_or_with_yes() -> None:
    agreed = World(answers=(True,))
    agreed.docker.containers["outpost-main"] = ContainerInfo(ContainerState.RUNNING, "old")
    agreed.up.run()
    assert agreed.devcontainer.recreated == [True]
    stop = agreed.events.index("stop outpost-main")
    assert stop < agreed.events.index("devcontainer up recreate=True")
    unattended = World()
    unattended.docker.containers["outpost-main"] = ContainerInfo(ContainerState.RUNNING, "old")
    unattended.up.run(assume_yes=True)
    assert unattended.devcontainer.recreated == [True]
    assert unattended.console.questions == []


def test_recreate_on_request_and_never_for_a_missing_container() -> None:
    asked = World()
    digest = asked.up.plan().settings_digest
    asked.docker.containers["outpost-main"] = ContainerInfo(ContainerState.RUNNING, digest)
    asked.up.run(recreate=True)
    assert asked.devcontainer.recreated == [True]
    fresh = World()
    fresh.up.run(recreate=True)
    assert fresh.devcontainer.recreated == [False]


def test_a_local_only_image_is_streamed_to_a_remote_host() -> None:
    env = Environment(
        root=ROOT,
        host=SshHost("my-vm", "dev"),
        devcontainer=DevContainerSettings.parse({"image": "acme/dev:3"}, "devcontainer"),
    )
    world = World(env)
    world.mine.images.add("acme/dev:3")
    world.up.run()
    assert "send acme/dev:3" in world.events
    assert not any(event.startswith("build") for event in world.events)


def test_a_proxy_stopped_or_removed_since_the_start_is_started_again() -> None:
    world = World(status=ContainerStatus(ready=True, proxy_running=False, routes=0))
    assert world.up.run().status.proxy_running
    assert world.events.index("wait ready") < world.events.index("start proxy")
    assert world.events.index("start proxy") < world.events.index("run init")
    assert world.console.warnings == []


def test_failures_after_boot_are_reported_not_fatal() -> None:
    status = ContainerStatus(ready=True, proxy_running=False, routes=0, init_failed=("01-a.sh",))
    world = World(status=status, proxy_starts=False)
    report = world.up.run()
    assert report.status.init_failed == ("01-a.sh",)
    assert "the proxy did not start: caddy:2.11 cannot be pulled" in world.console.warnings
    assert any("01-a.sh" in warning for warning in world.console.warnings)


def test_a_container_that_reaches_the_host_is_refused() -> None:
    world = World()
    world.docker.exposed = Exposure((Mount("bind", "/var/run/docker.sock"),), "outpost", ())
    with pytest.raises(ConfigError, match=r"/var/run/docker\.sock is mounted from the host"):
        world.up.run()
    assert world.events[-2:] == ["stop outpost-main", "rm outpost-main"]
    assert "wait ready" not in world.events
