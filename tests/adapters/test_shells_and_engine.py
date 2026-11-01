from __future__ import annotations

from pathlib import Path, PurePosixPath

from outpost.adapters.engine.docker_cli import DockerCliEngine, exec_arguments, run_arguments
from outpost.adapters.shell.local import LocalShell
from outpost.adapters.shell.process import run_captured
from outpost.adapters.shell.ssh import SshShell
from outpost.domain.config import Isolation, SshConnection
from outpost.domain.names import ImageRef, Port
from outpost.ports.engine import ContainerSpec, ContainerState, Mount, MountKind, PortBinding
from tests.fakes import FakeShell


def test_ssh_quotes_the_remote_command() -> None:
    shell = SshShell(SshConnection(host="vm", user="dev", port=Port(2222)))
    argv = shell.command(["sh", "-c", "echo $HOME", "it's"])
    assert argv[:2] == ["ssh", "-o"]
    assert "BatchMode=yes" in argv
    assert argv[argv.index("-p") + 1] == "2222"
    assert argv[-3:] == ["dev@vm", "--", "sh -c 'echo $HOME' 'it'\"'\"'s'"]
    assert shell.client_commands == ("ssh", "scp")


def test_interactive_ssh_allocates_a_terminal_and_allows_prompts() -> None:
    argv = SshShell(SshConnection(host="vm")).command(["bash", "-l"], interactive=True)
    assert "-t" in argv
    assert "BatchMode=yes" not in argv


def test_captured_commands_never_read_the_terminal() -> None:
    assert run_captured(["cat"]).stdout == ""
    assert run_captured(["cat"], stdin="given").stdout == "given"


def test_local_shell_files_and_working_directory(tmp_path: Path) -> None:
    shell = LocalShell()
    target = PurePosixPath(tmp_path) / "nested" / "secret.txt"
    shell.write_file(target, "value", mode=0o600)
    assert shell.read_file(target) == "value"
    assert (Path(target).stat().st_mode & 0o777) == 0o600
    assert shell.read_file(PurePosixPath(tmp_path) / "missing") is None
    assert shell.run(["pwd"], cwd=PurePosixPath(tmp_path)).stdout.strip() == str(tmp_path)


def test_staged_files_are_removed_after_use(tmp_path: Path) -> None:
    source = tmp_path / "archive.tar"
    source.write_text("image", encoding="utf-8")
    with LocalShell().staged(source) as staged:
        assert Path(staged).read_text(encoding="utf-8") == "image"
    assert not Path(staged).exists()


def test_box_run_arguments_are_stable() -> None:
    spec = ContainerSpec(
        name="outpost-acme-box",
        image=ImageRef("outpost-acme-box:abc"),
        isolation=Isolation.SYSBOX,
        mounts=(Mount(MountKind.VOLUME, "outpost-acme-home", PurePosixPath("/home/dev")),),
        ports=(PortBinding("127.0.0.1", 443, 443),),
        networks=("outpost-acme-edge-net",),
        env={"B": "2", "A": "1"},
        cpus=16,
        memory_gb=64,
    )
    assert run_arguments(spec) == [
        "run", "--detach", "--name", "outpost-acme-box",
        "--restart", "unless-stopped",
        "--runtime", "sysbox-runc",
        "--mount", "type=volume,source=outpost-acme-home,target=/home/dev",
        "--publish", "127.0.0.1:443:443",
        "--network", "outpost-acme-edge-net",
        "--env", "A=1", "--env", "B=2",
        "--cpus", "16", "--memory", "64g",
        "outpost-acme-box:abc",
    ]  # fmt: skip


def test_exec_arguments() -> None:
    argv = exec_arguments("box", ["claude", "auth", "status"], user="dev", keep_stdin=False)
    assert argv == ["exec", "--user", "dev", "box", "claude", "auth", "status"]


def test_engine_reads_container_state_and_labels() -> None:
    shell = FakeShell()
    engine = DockerCliEngine(shell)
    shell.respond("docker", "container", "inspect", code=1)
    assert engine.state("missing") is ContainerState.MISSING
    shell.respond("docker", "container", "inspect", "--format", "{{.State.Running}}", stdout="true")
    assert engine.state("box") is ContainerState.RUNNING
    labels = '{"outpost.fingerprint": "abc"}'
    shell.respond(
        "docker", "container", "inspect", "--format", "{{json .Config.Labels}}", stdout=labels
    )
    assert engine.label("box", "outpost.fingerprint") == "abc"


def test_sysbox_support_reads_the_runtimes() -> None:
    shell = FakeShell()
    shell.respond("docker", "info", stdout='{"runc": {}, "sysbox-runc": {}}')
    engine = DockerCliEngine(shell)
    assert engine.supports(Isolation.SYSBOX)
    assert engine.supports(Isolation.PRIVILEGED)
