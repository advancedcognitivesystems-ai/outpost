from __future__ import annotations

import shutil
import subprocess
from pathlib import Path, PurePosixPath

import pytest

from outpost.adapters.credentials.factory import build_secret_source
from outpost.adapters.credentials.github import GithubAuth
from outpost.adapters.credentials.sources import CommandSecret, EnvSecret, FileSecret
from outpost.adapters.interaction.templates import PackageTemplates, render_text
from outpost.adapters.repository.git_cli import GitRepository
from outpost.adapters.shell.local import LocalShell
from outpost.adapters.tls.local_ca import LocalCertificateAuthority
from outpost.domain.config import AutoSource
from outpost.domain.credentials import Tool
from outpost.domain.errors import InvalidValue
from outpost.domain.names import Domain, ProjectName, WorktreeName
from outpost.domain.resources import BoxLayout, HostLayout
from outpost.domain.secrets import Secret
from outpost.domain.tls import CertificateFiles
from tests.fakes import FakeShell


@pytest.mark.skipif(shutil.which("openssl") is None, reason="needs openssl")
def test_local_ca_issues_a_wildcard_once(tmp_path: Path) -> None:
    shell = LocalShell()
    authority = LocalCertificateAuthority(shell, Domain("dev.localhost"), ProjectName("acme"))
    layout = HostLayout(PurePosixPath(tmp_path))
    material = authority.prepare(layout)
    assert isinstance(material, CertificateFiles)
    text = subprocess.run(
        ["openssl", "x509", "-in", str(material.certificate), "-noout", "-text"],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    assert "DNS:*.dev.localhost" in text
    first = Path(material.certificate).read_bytes()
    authority.prepare(layout)
    assert Path(material.certificate).read_bytes() == first
    assert (Path(material.key).stat().st_mode & 0o777) == 0o600
    assert authority.client_trust_bundle(layout) is not None


def test_box_templates_render_with_their_values() -> None:
    templates = PackageTemplates()
    dockerfile = templates.render("box/Dockerfile.tmpl", {"base_image": "base:1", "user": "dev"})
    assert dockerfile.splitlines()[2] == "FROM base:1"
    init = templates.render("box/outpost-init.sh.tmpl", {"router_bootstrap": "echo router"})
    assert "echo router" in init
    assert "{{" not in dockerfile + init


def test_templates_refuse_missing_and_unused_values() -> None:
    with pytest.raises(InvalidValue, match="missing values \\['b'\\]"):
        render_text("{{a}} {{b}}", {"a": "1"})
    with pytest.raises(InvalidValue, match="unused values \\['c'\\]"):
        render_text("{{a}}", {"a": "1", "c": "2"})


def test_auto_source_per_platform(tmp_path: Path) -> None:
    client = FakeShell()
    on_mac = build_secret_source(AutoSource(), Tool.CLAUDE, client, {}, platform="darwin")
    assert isinstance(on_mac, CommandSecret)
    assert "Claude Code-credentials" in on_mac.description
    on_linux = build_secret_source(
        AutoSource(), Tool.CLAUDE, client, {"CLAUDE_CONFIG_DIR": str(tmp_path)}, platform="linux"
    )
    assert isinstance(on_linux, FileSecret)
    assert on_linux.description == f"file {tmp_path / '.credentials.json'}"
    github = build_secret_source(AutoSource(), Tool.GITHUB, client, {}, platform="linux")
    assert github.description == "command `gh auth token`"


def test_sources_return_nothing_rather_than_empty_secrets(tmp_path: Path) -> None:
    client = FakeShell()
    client.respond("gh", "auth", "token", code=1)
    assert CommandSecret(client, ["gh", "auth", "token"]).read() is None
    assert EnvSecret("TOKEN", {"TOKEN": "  "}).read() is None
    assert FileSecret(tmp_path / "absent").read() is None
    assert EnvSecret("TOKEN", {"TOKEN": "abc"}).read() == Secret("abc")


def test_github_login_with_token_and_git_setup() -> None:
    box = FakeShell()
    auth = GithubAuth(box, setup_git=True)
    auth.install(Secret("ghp_x"))
    auth.finish()
    assert box.calls[0][:3] == ("gh", "auth", "login")
    assert box.stdins[0] == "ghp_x\n"
    assert box.ran("gh", "auth", "setup-git")


def test_git_lists_only_outpost_worktrees() -> None:
    box = FakeShell()
    layout = BoxLayout(ProjectName("acme"), "dev")
    box.respond(
        "git", "-C", str(layout.repository), "worktree", "list", "--porcelain",
        stdout=(
            "worktree /workspaces/acme/repo\nHEAD abc\nbranch refs/heads/main\n\n"
            "worktree /workspaces/acme/worktrees/feat-a\nHEAD def\nbranch refs/heads/feature/a\n"
        ),
    )  # fmt: skip
    (only,) = GitRepository(box, layout).worktrees()
    assert only.name == WorktreeName("feat-a")
    assert only.branch == "feature/a"
