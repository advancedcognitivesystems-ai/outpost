"""Logins, copies, lifecycle, access and doctor, through fakes."""

from __future__ import annotations

from pathlib import Path, PurePath, PurePosixPath

import pytest

from outpost.domain.credentials import LoginState, Tool
from outpost.domain.environment import Environment
from outpost.domain.errors import Declined, Unavailable
from outpost.domain.host import SshHost
from outpost.domain.secrets import Secret
from outpost.domain.status import ContainerStatus
from outpost.domain.transfer import parse_copy
from outpost.launcher.application.access import Access
from outpost.launcher.application.doctor import Doctor, Severity
from outpost.launcher.application.lifecycle import Lifecycle
from outpost.launcher.application.logins import Logins
from outpost.launcher.application.transfers import Transfers
from outpost.launcher.ports.docker import ContainerInfo, ContainerState
from tests.fakes import (
    Events,
    FakeConsole,
    FakeDevContainer,
    FakeDocker,
    FakeFiles,
    FakeLogin,
    FakePrograms,
    FakeRuntime,
    FakeSource,
    FakeTunnel,
)

ENV = Environment(root=Path("/home/me/project"))
OUT = LoginState(Tool.CLAUDE, False, "not logged in")
IN = LoginState(Tool.CLAUDE, True, "me@example.com")


# ------------------------------------------------------------------ logins


def test_a_valid_login_is_left_alone() -> None:
    login = FakeLogin(Tool.CLAUDE, [IN])
    state = Logins(FakeConsole(), []).ensure(FakeSource(Secret("x")), login)
    assert state.valid
    assert login.events == ["finish claude"]


def test_a_missing_login_is_copied_from_your_machine() -> None:
    login = FakeLogin(Tool.CLAUDE, [OUT, IN])
    state = Logins(FakeConsole(), []).ensure(FakeSource(Secret("token")), login)
    assert state.valid
    assert login.events == ["install claude", "finish claude"]
    assert login.installed == [Secret("token")]


def test_a_refused_copy_is_reported_then_a_login_offered() -> None:
    login = FakeLogin(Tool.GITHUB, [OUT, IN], refuse=True)
    console = FakeConsole(answers=(True,))
    assert Logins(console, []).ensure(FakeSource(Secret("bad")), login).valid
    assert login.events == ["install gh", "login gh", "finish gh"]
    assert any("was refused" in warning for warning in console.warnings)


def test_without_a_login_to_copy_one_is_offered() -> None:
    login = FakeLogin(Tool.CLAUDE, [OUT, IN])
    console = FakeConsole(answers=(True,))
    assert Logins(console, []).ensure(FakeSource(), login).valid
    assert login.events == ["login claude", "finish claude"]


def test_no_terminal_means_no_interactive_login() -> None:
    login = FakeLogin(Tool.CLAUDE, [OUT])
    console = FakeConsole(interactive=False)
    assert not Logins(console, []).ensure(FakeSource(), login).valid
    assert login.events == []
    assert console.warnings


def test_a_tool_missing_from_the_image_is_only_reported() -> None:
    missing = LoginState(Tool.CLAUDE, False, "not installed", installed=False)
    login = FakeLogin(Tool.CLAUDE, [missing])
    console = FakeConsole(answers=(True,))
    Logins(console, []).ensure(FakeSource(Secret("token")), login)
    assert login.events == []
    assert console.questions == []


# ------------------------------------------------------------------ copies


def transfers(events: Events, files: FakeFiles | None = None) -> tuple[Transfers, FakeDocker]:
    docker = FakeDocker(events)
    return Transfers(docker, files or FakeFiles(existing={"notes.md"}), "outpost-main"), docker


def test_copy_into_a_folder_or_as_a_new_name() -> None:
    copies, docker = transfers([])
    assert copies.copy(parse_copy("notes.md", ":~/inbox/")) == ":/home/dev/inbox/notes.md"
    assert copies.copy(parse_copy("notes.md", ":~/inbox/todo.md")) == ":/home/dev/inbox/todo.md"
    assert docker.copies[1] == ("in", "notes.md", "/home/dev/inbox", "todo.md", "dev")


def test_copy_into_an_existing_container_folder_without_a_slash() -> None:
    copies, docker = transfers([])
    assert copies.copy(parse_copy("notes.md", ":/workspaces/n.md")) == ":/workspaces/n.md"
    docker.directories.add("/workspaces")
    assert copies.copy(parse_copy("notes.md", ":/workspaces")) == ":/workspaces/notes.md"


def test_copy_out_into_the_current_folder() -> None:
    copies, docker = transfers([], FakeFiles(directories={"out"}))
    assert copies.copy(parse_copy(":/workspaces/app/report.pdf", ".")) == "report.pdf"
    assert copies.copy(parse_copy(":/workspaces/app/report.pdf", "out")) == "out/report.pdf"
    assert docker.copies[0][:4] == ("out", "/workspaces/app/report.pdf", ".", "report.pdf")


def test_copying_a_missing_file_fails_before_touching_the_container() -> None:
    copies, docker = transfers([])
    with pytest.raises(Unavailable, match="does not exist"):
        copies.copy(parse_copy("missing.md", ":~/"))
    assert docker.copies == []


def test_init_scripts_are_replaced_and_numbered() -> None:
    files = FakeFiles(existing={"/p/a.sh", "/p/b.sh"})
    copies, docker = transfers([], files)
    copies.sync_init([PurePath("/p/a.sh"), PurePath("/p/b.sh")])
    assert [copy[3] for copy in docker.copies] == ["01-a.sh", "02-b.sh"]
    assert {copy[4] for copy in docker.copies} == {"root"}
    with pytest.raises(Unavailable):
        copies.sync_init([PurePath("/p/missing.sh")])


# ------------------------------------------------------------------ lifecycle


def lifecycle(
    state: ContainerState, *, text: str = "", runtime: ContainerStatus | None = None
) -> tuple[Lifecycle, FakeDocker]:
    events: Events = []
    docker = FakeDocker(events)
    if state is not ContainerState.MISSING:
        docker.containers["outpost-main"] = ContainerInfo(state)
    docker.volume_labels = {
        "outpost-main-home": {"outpost.environment": "main"},
        "outpost-main-state": {"outpost.environment": "main"},
        "outpost-other-home": {"outpost.environment": "other"},
    }
    return Lifecycle(ENV, docker, FakeRuntime(events, runtime), FakeConsole(text=text)), docker


def test_stop_and_down_keep_the_volumes() -> None:
    running, docker = lifecycle(ContainerState.RUNNING)
    assert running.stop()
    assert not running.stop()
    assert running.down()
    assert docker.events == ["stop outpost-main", "rm outpost-main"]
    restarting, docker = lifecycle(ContainerState.RESTARTING)
    assert restarting.down()
    assert docker.events == ["stop outpost-main", "rm outpost-main"]
    assert "outpost-main-home" in docker.volume_labels


def test_destroy_needs_the_name_typed() -> None:
    refused, docker = lifecycle(ContainerState.RUNNING, text="nope")
    with pytest.raises(Declined):
        refused.destroy(assume_yes=False)
    assert docker.events == []
    agreed, docker = lifecycle(ContainerState.RUNNING, text="main")
    assert agreed.destroy(assume_yes=False) == ("outpost-main-home", "outpost-main-state")
    assert docker.events == [
        "stop outpost-main",
        "rm outpost-main",
        "rm volumes outpost-main-home outpost-main-state",
    ]
    assert list(docker.volume_labels) == ["outpost-other-home"]


def test_status_asks_the_container_only_when_it_runs() -> None:
    stopped, _ = lifecycle(ContainerState.STOPPED)
    assert stopped.status().runtime is None
    running, _ = lifecycle(ContainerState.RUNNING)
    report = running.status()
    assert report.runtime is not None
    assert "feat-a-api-1:8080" in report.routes


def test_status_reports_a_stopped_proxy_instead_of_failing() -> None:
    down = ContainerStatus(ready=True, proxy_running=False, routes=0)
    report = lifecycle(ContainerState.RUNNING, runtime=down)[0].status()
    assert report.runtime == down
    assert report.routes == ""


# ------------------------------------------------------------------ access


def test_a_shell_needs_a_running_container() -> None:
    docker = FakeDocker([])
    access = Access(ENV, docker, FakeRuntime([]), FakeTunnel())
    with pytest.raises(Unavailable, match=r"\./outpost up"):
        access.shell()
    docker.containers["outpost-main"] = ContainerInfo(ContainerState.RUNNING)
    assert access.shell() == 0
    assert docker.events == ["attached bash -l as dev in /workspaces"]


def test_the_tunnel_is_for_remote_hosts() -> None:
    tunnel = FakeTunnel()
    with pytest.raises(Unavailable, match="no tunnel needed"):
        Access(ENV, FakeDocker([]), FakeRuntime([]), tunnel).tunnel()
    remote = Environment(root=PurePosixPath("/p"), host=SshHost("vm", "dev"))
    Access(remote, FakeDocker([]), FakeRuntime([]), tunnel).tunnel()
    assert tunnel.forwarded == [("ssh://dev@vm", 8443)]


# ------------------------------------------------------------------ doctor


def test_doctor_reports_each_need() -> None:
    remote = Environment(root=PurePosixPath("/p"), host=SshHost("vm", "dev"))
    docker = FakeDocker([], description="ssh://dev@vm", reachable=False)
    findings = Doctor(
        remote,
        programs=FakePrograms({"docker": "Docker version 28.0.0"}),
        devcontainer=FakeDevContainer([], docker, installed=False),
        docker=docker,
        sources={Tool.CLAUDE: FakeSource(Secret("x")), Tool.GITHUB: FakeSource()},
    ).run()
    assert [(item.check, item.severity) for item in findings] == [
        ("docker CLI", Severity.OK),
        ("Dev Container CLI", Severity.FAIL),
        ("ssh", Severity.FAIL),
        ("Docker on ssh://dev@vm", Severity.FAIL),
        ("claude login", Severity.OK),
        ("gh login", Severity.WARN),
    ]
