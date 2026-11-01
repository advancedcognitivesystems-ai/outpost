"""Launcher adapters: the commands they build, and real files where that is safe."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path, PurePosixPath

import pytest

from outpost.domain.credentials import Tool
from outpost.domain.devcontainer import DevContainerSettings
from outpost.domain.environment import Environment
from outpost.domain.errors import CommandFailed, Unavailable
from outpost.domain.host import SshHost
from outpost.domain.names import ImageRef
from outpost.domain.secrets import Secret
from outpost.domain.status import INIT_SCRIPTS_FAILED, ContainerStatus
from outpost.domain.volumes import Volume
from outpost.infra.process import CommandResult
from outpost.launcher.adapters.archive import extract_archive, write_archive
from outpost.launcher.adapters.base_image import CheckoutBaseImage
from outpost.launcher.adapters.devcontainer_cli import DevContainerCliAdapter
from outpost.launcher.adapters.docker_cli import DockerCli, ImagePipe
from outpost.launcher.adapters.logins import (
    ClaudeLogin,
    CommandSource,
    FileSource,
    GithubLogin,
    login_source,
)
from outpost.launcher.adapters.machine import SshTunnel, TerminalConsole
from outpost.launcher.adapters.runtime import ToolRuntime
from outpost.launcher.ports.docker import ContainerState
from tests.fakes import FakeRunner, failed, ok

REMOTE = {"DOCKER_HOST": "ssh://dev@vm"}


def docker(runner: FakeRunner) -> DockerCli:
    return DockerCli(runner, description="ssh://dev@vm", environment=REMOTE)


# ------------------------------------------------------------------ Docker CLI


def test_every_docker_command_carries_the_host() -> None:
    runner = FakeRunner()
    runner.answer(["docker", "version"], ok("28.0.1\n"))
    assert docker(runner).server_version() == "28.0.1"
    assert runner.calls[0].env == REMOTE


def test_an_unreachable_engine_is_unavailable() -> None:
    runner = FakeRunner()
    runner.answer(["docker", "version"], failed(1, "error during connect: ssh: no route\n"))
    with pytest.raises(Unavailable, match="ssh://dev@vm does not answer: error during connect"):
        docker(runner).server_version()


def test_container_state_and_settings_digest() -> None:
    runner = FakeRunner()
    runner.answer(["docker", "container", "inspect"], ok("running abc123\n"))
    info = docker(runner).container("outpost-main")
    assert (info.state, info.settings_digest) == (ContainerState.RUNNING, "abc123")
    runner.answer(["docker", "container", "inspect"], failed(1, "Error: No such container: x"))
    assert docker(runner).container("x").state is ContainerState.MISSING
    runner.answer(["docker", "container", "inspect"], ok("exited \n"))
    info = docker(runner).container("x")
    assert (info.state, info.settings_digest, info.status) == (
        ContainerState.STOPPED,
        None,
        "exited",
    )
    runner.answer(["docker", "container", "inspect"], ok("restarting abc\n"))
    assert docker(runner).container("x").state is ContainerState.RESTARTING


def test_exposure_reads_mounts_network_and_ports() -> None:
    runner = FakeRunner()
    inspected = {
        "Mounts": [
            {"Type": "volume", "Destination": "/home/dev"},
            {"Type": "bind", "Destination": "/var/run/docker.sock"},
        ],
        "HostConfig": {
            "NetworkMode": "bridge",
            "PortBindings": {"443/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8443"}]},
        },
    }
    runner.answer(["docker", "container", "inspect"], ok(json.dumps(inspected)))
    exposure = docker(runner).exposure("outpost-main")
    assert [mount.kind for mount in exposure.mounts] == ["volume", "bind"]
    assert exposure.network_mode == "bridge"
    assert [str(item) for item in exposure.published] == ["127.0.0.1:8443->443/tcp"]


def test_volumes_are_created_once_with_labels() -> None:
    runner = FakeRunner()
    runner.answer(["docker", "volume", "inspect"], failed())
    volume = Volume("outpost-main-home", PurePosixPath("/home/dev"))
    docker(runner).ensure_volume(volume, {"outpost.environment": "main"})
    assert runner.argvs()[-1] == (
        "docker",
        "volume",
        "create",
        "--label",
        "outpost.environment=main",
        "outpost-main-home",
    )


def test_secrets_reach_exec_through_stdin_only() -> None:
    runner = FakeRunner()
    docker(runner).exec("outpost-main", ["cat"], user="dev", stdin="secret")
    call = runner.calls[0]
    assert call.argv == ("docker", "exec", "--interactive", "--user", "dev", "outpost-main", "cat")
    assert call.stdin == "secret"


def test_images_stream_from_your_docker_to_the_host() -> None:
    runner = FakeRunner()
    mine = DockerCli(runner, description="your Docker")
    ImagePipe(runner, mine=mine, host=docker(runner)).send(ImageRef("acme/dev:3"))
    assert [(call.argv, call.env) for call in runner.calls] == [
        (("docker", "save", "acme/dev:3"), None),
        (("docker", "load"), REMOTE),
    ]


def test_copy_in_streams_a_tar_extracted_as_the_user(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("hello", encoding="utf-8")
    runner = FakeRunner()
    docker(runner).copy_in(
        "outpost-main", tmp_path / "notes.md", PurePosixPath("/home/dev/inbox"), "n.md", user="dev"
    )
    call = runner.calls[0]
    assert call.argv[:6] == ("docker", "exec", "--interactive", "--user", "dev", "outpost-main")
    assert call.argv[-1] == "/home/dev/inbox"
    extract_archive(io.BytesIO(call.fed), tmp_path / "out", "n.md")
    assert (tmp_path / "out" / "n.md").read_text(encoding="utf-8") == "hello"


def test_copy_out_unpacks_under_the_new_name(tmp_path: Path) -> None:
    source = tmp_path / "src" / "report"
    source.mkdir(parents=True)
    (source / "a.txt").write_text("a", encoding="utf-8")
    buffer = io.BytesIO()
    write_archive(source, "report", buffer)
    runner = FakeRunner()
    runner.drained = buffer.getvalue()
    target = tmp_path / "dest"
    docker(runner).copy_out(
        "outpost-main", PurePosixPath("/workspaces/report"), target, "copy", user="dev"
    )
    assert runner.calls[0].argv[-5:] == ("-f", "-", "-C", "/workspaces", "report")
    assert (target / "copy" / "a.txt").read_text(encoding="utf-8") == "a"


def test_an_unreadable_source_is_named(tmp_path: Path) -> None:
    secret = tmp_path / "secret"
    secret.mkdir()
    (secret / "key").write_text("x", encoding="utf-8")
    (secret / "key").chmod(0)
    runner = FakeRunner()
    if os.access(secret / "key", os.R_OK):
        pytest.skip("running as root: every file is readable")
    with pytest.raises(Unavailable, match="could not read"):
        docker(runner).copy_in("c", secret, PurePosixPath("/tmp"), "secret", user="dev")


def test_unsafe_archives_are_refused(tmp_path: Path) -> None:
    link = tmp_path / "link"
    link.symlink_to("/etc/passwd")
    buffer = io.BytesIO()
    write_archive(link, "link", buffer)
    runner = FakeRunner()
    runner.drained = buffer.getvalue()
    with pytest.raises(Unavailable, match="could not write"):
        docker(runner).copy_out("c", PurePosixPath("/x/link"), tmp_path / "d", "link", user="dev")


# ------------------------------------------------------------------ Dev Container CLI


def test_devcontainer_up_writes_the_file_then_runs_on_the_same_host(tmp_path: Path) -> None:
    runner = FakeRunner()
    environment = Environment(root=tmp_path, host=SshHost("vm", "dev"))
    definition = environment.definition(ImageRef("outpost/base:0123456789ab"))
    cli = DevContainerCliAdapter(runner, environment=REMOTE)
    cli.up(definition, environment.workdir, environment.id_label, recreate=True)
    written = tmp_path / ".outpost" / "main" / "devcontainer.json"
    assert json.loads(written.read_text(encoding="utf-8"))["name"] == "outpost-main"
    call = runner.calls[0]
    assert call.argv == (
        "devcontainer",
        "up",
        "--workspace-folder",
        str(tmp_path / ".outpost" / "main"),
        "--config",
        str(written),
        "--id-label",
        "outpost.environment=main",
        "--remove-existing-container",
    )
    assert call.env == REMOTE


def test_a_missing_devcontainer_cli_says_how_to_install_it(tmp_path: Path) -> None:
    runner = FakeRunner()
    runner.attached_codes[("devcontainer",)] = 127
    environment = Environment(root=tmp_path, devcontainer=DevContainerSettings())
    definition = environment.definition(ImageRef("outpost/base:0123456789ab"))
    with pytest.raises(Unavailable, match="npm install -g @devcontainers/cli"):
        DevContainerCliAdapter(runner).up(definition, tmp_path, "l=v", recreate=False)


# ------------------------------------------------------------------ runtime


def test_wait_ready_polls_until_boot_finishes() -> None:
    runner = FakeRunner()
    status = ["docker", "exec", "--user", "dev", "outpost-main", "outpost", "status"]
    not_yet = ContainerStatus(ready=False, proxy_running=False, routes=0)
    runner.answer(status, ok(not_yet.to_json()))
    clock = iter([0.0, 1.0, 2.0, 3.0])
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        runner.answer(
            status, ok(ContainerStatus(ready=True, proxy_running=True, routes=2).to_json())
        )

    tool = ToolRuntime(docker(runner), sleep=sleep, clock=lambda: next(clock))
    assert tool.wait_ready("outpost-main", 60).routes == 2
    assert sleeps == [2.0]


def test_an_image_without_the_tool_is_named() -> None:
    runner = FakeRunner()
    runner.answer(["docker", "exec"], CommandResult((), 127))
    with pytest.raises(Unavailable, match="must derive from outpost/base"):
        ToolRuntime(docker(runner)).status("outpost-main")


def test_init_runs_as_root_on_the_terminal_and_failed_scripts_are_reported() -> None:
    runner = FakeRunner()
    failed_status = ContainerStatus(True, True, 0, init_failed=("01-a.sh",))
    runner.answer(["docker", "exec"], ok(failed_status.to_json()))
    runner.attached_codes[("docker", "exec")] = INIT_SCRIPTS_FAILED
    assert ToolRuntime(docker(runner)).run_init("outpost-main").init_failed == ("01-a.sh",)
    attached = runner.calls[0].argv
    assert attached[attached.index("--user") + 1] == "root"
    assert attached[-3:] == ("outpost", "init", "--if-changed")
    runner.attached_codes[("docker", "exec")] = 2
    with pytest.raises(CommandFailed):
        ToolRuntime(docker(runner)).run_init("outpost-main")


# ------------------------------------------------------------------ logins


@pytest.mark.parametrize(
    ("result", "valid", "detail"),
    [
        (ok('{"loggedIn": true, "authMethod": "claude.ai", "email": "me@x.io"}'), True, "me@x.io"),
        (failed(1, ""), False, "unexpected `claude auth status` output"),
        (CommandResult((), 1, '{"loggedIn": false, "authMethod": "none"}'), False, "not logged in"),
        (ok('{"authMethod": "api_key"}'), False, "logged in with api_key"),
        (CommandResult((), 127), False, "Claude Code is not installed"),
    ],
)
def test_claude_login_state(result: CommandResult, valid: bool, detail: str) -> None:
    runner = FakeRunner()
    runner.answer(["docker", "exec"], result)
    state = ClaudeLogin(docker(runner), "outpost-main").state()
    assert state.valid is valid
    assert state.detail.startswith(detail)


def test_claude_login_is_written_private() -> None:
    runner = FakeRunner()
    ClaudeLogin(docker(runner), "outpost-main").install(Secret('{"claudeAiOauth": {}}'))
    call = runner.calls[0]
    assert call.argv[-1] == "/home/dev/.claude/.credentials.json"
    assert "umask 077" in call.argv[-3]
    assert call.argv[3:5] == ("--user", "dev")
    assert call.stdin == '{"claudeAiOauth": {}}'


def test_gh_token_login_then_git_setup() -> None:
    runner = FakeRunner()
    login = GithubLogin(docker(runner), "outpost-main")
    login.install(Secret("gho_x"))
    login.finish()
    assert [call.argv[call.argv.index("gh") :][:3] for call in runner.calls] == [
        ("gh", "auth", "login"),
        ("gh", "auth", "setup-git"),
    ]
    assert runner.calls[0].stdin == "gho_x\n"


def test_login_sources_per_platform(tmp_path: Path) -> None:
    runner = FakeRunner()
    keychain = login_source(Tool.CLAUDE, runner, {}, "darwin")
    assert isinstance(keychain, CommandSource)
    assert keychain.description == "the macOS Keychain"
    on_linux = login_source(Tool.CLAUDE, runner, {"CLAUDE_CONFIG_DIR": str(tmp_path)}, "linux")
    assert isinstance(on_linux, FileSource)
    assert on_linux.read() is None
    (tmp_path / ".credentials.json").write_text("{}", encoding="utf-8")
    assert on_linux.read() == Secret("{}")
    runner.answer(["gh", "auth", "token"], ok("gho_abc\n"))
    assert login_source(Tool.GITHUB, runner, {}).read() == Secret("gho_abc")


# ------------------------------------------------------------------ your machine


def test_the_base_image_tag_follows_the_container_side_only(tmp_path: Path) -> None:
    (tmp_path / "image").mkdir()
    (tmp_path / "image" / "Dockerfile").write_text("FROM ubuntu:24.04\n", encoding="utf-8")
    for side in ("container", "launcher"):
        (tmp_path / "src" / "outpost" / side).mkdir(parents=True)
        (tmp_path / "src" / "outpost" / side / "a.py").write_text("x = 1\n", encoding="utf-8")
    first = CheckoutBaseImage(tmp_path).reference()
    assert first.value.startswith("outpost/base:")
    (tmp_path / "src" / "outpost" / "launcher" / "a.py").write_text("x = 2\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("changed\n", encoding="utf-8")
    assert CheckoutBaseImage(tmp_path).reference() == first
    (tmp_path / "src" / "outpost" / "container" / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert CheckoutBaseImage(tmp_path).reference() != first
    assert CheckoutBaseImage(tmp_path).dockerfile == tmp_path / "image" / "Dockerfile"


def test_the_tunnel_forwards_the_same_port_on_loopback() -> None:
    runner = FakeRunner()
    SshTunnel(runner).forward(SshHost("vm", "dev", 2222), 8443)
    assert runner.argvs() == [
        (
            "ssh",
            "-N",
            "-o",
            "ExitOnForwardFailure=yes",
            "-L",
            "127.0.0.1:8443:127.0.0.1:8443",
            "-p",
            "2222",
            "dev@vm",
        )
    ]


def test_the_console_without_a_terminal_takes_the_default() -> None:
    output = io.StringIO()
    console = TerminalConsole(assume_yes=False, interactive=False, output=output)
    assert console.confirm("Recreate?", default=False) is False
    assert console.ask("Type the name:") == ""
    assert TerminalConsole(assume_yes=True, interactive=False, output=output).confirm(
        "Recreate?", default=False
    )
    answers = iter(["maybe", "y"])
    asking = TerminalConsole(
        assume_yes=False, interactive=True, output=output, ask=lambda _: next(answers)
    )
    assert asking.confirm("Recreate?", default=False)
