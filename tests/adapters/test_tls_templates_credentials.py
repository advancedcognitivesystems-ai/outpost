from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path, PurePosixPath

import pytest

from outpost.adapters.credentials.claude import ClaudeAuth
from outpost.adapters.credentials.factory import build_secret_source
from outpost.adapters.credentials.github import GithubAuth
from outpost.adapters.credentials.sources import CommandSecret, EnvSecret, FileSecret
from outpost.adapters.interaction.templates import PackageTemplates, render_text
from outpost.adapters.repository.git_cli import GitRepository
from outpost.adapters.shell.local import LocalShell
from outpost.adapters.tls.acme import AcmeDnsChallenge, parse_assignments
from outpost.adapters.tls.local_ca import LocalCertificateAuthority
from outpost.domain.config import AcmeTls, AutoSource, ResolvedConfig
from outpost.domain.credentials import Tool
from outpost.domain.errors import InvalidValue
from outpost.domain.names import Domain, ProjectName, WorktreeName
from outpost.domain.resources import HostLayout
from outpost.domain.secrets import Secret
from outpost.domain.tls import AcmeIssuance, CertificateFiles
from tests.fakes import FakeSecretSource, FakeShell

HOME = PurePosixPath("/home/dev")


@pytest.mark.skipif(shutil.which("openssl") is None, reason="needs openssl")
def test_local_ca_issues_a_private_wildcard_once(tmp_path: Path) -> None:
    authority = LocalCertificateAuthority(
        LocalShell(), Domain("dev.localhost"), ProjectName("acme")
    )
    layout = HostLayout(PurePosixPath(tmp_path))
    material = authority.prepare(layout)
    assert isinstance(material, CertificateFiles)
    text = subprocess.run(
        ["openssl", "x509", "-in", str(material.certificate), "-noout", "-text"],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    assert "DNS:*.dev.localhost" in text
    assert sorted(path.name for path in Path(material.directory).iterdir()) == [
        "wildcard.crt",
        "wildcard.key",
    ]
    assert (Path(tmp_path / "tls" / "ca.key").stat().st_mode & 0o777) == 0o600
    assert (Path(material.key).stat().st_mode & 0o777) == 0o600
    first = Path(material.certificate).read_bytes()
    authority.prepare(layout)
    assert Path(material.certificate).read_bytes() == first
    assert authority.client_trust_bundle(layout) is not None


def test_acme_credentials_become_one_private_file_each() -> None:
    host = FakeShell()
    content = "# Azure DNS\nexport AZURE_CLIENT_ID=abc\nAZURE_CLIENT_SECRET='s3cret'\n"
    spec = AcmeTls(email="ops@x.io", dns_provider="azuredns", dns_env_file="~/dns.env")
    challenge = AcmeDnsChallenge(host, spec, Domain("dev.x.io"), FakeSecretSource(content))
    material = challenge.prepare(HostLayout(PurePosixPath("/s")))
    assert isinstance(material, AcmeIssuance)
    assert material.variables == ("AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET")
    secret_file = PurePosixPath("/s/secrets/acme-dns/AZURE_CLIENT_SECRET")
    assert host.files[secret_file] == "s3cret"
    assert host.modes[secret_file] == 0o600


def test_acme_credentials_must_be_assignments() -> None:
    with pytest.raises(InvalidValue, match="line 1"):
        parse_assignments(Secret("not an assignment"))
    with pytest.raises(InvalidValue, match="environment variable"):
        parse_assignments(Secret("1BAD=x"))


def test_box_templates_render_with_their_values() -> None:
    templates = PackageTemplates()
    dockerfile = templates.render("box/Dockerfile.tmpl", {"base_image": "base:1", "user": "dev"})
    assert dockerfile.splitlines()[2] == "FROM base:1"
    assert "install -d -o dev -g dev /workspaces" in dockerfile
    init = templates.render("box/outpost-init.sh.tmpl", {"boot": "echo stacks"})
    assert "echo stacks" in init
    assert "cgroup.subtree_control" in init
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
    assert on_mac.client_commands == ("security",)
    on_linux = build_secret_source(
        AutoSource(), Tool.CLAUDE, client, {"CLAUDE_CONFIG_DIR": str(tmp_path)}, platform="linux"
    )
    assert isinstance(on_linux, FileSecret)
    assert on_linux.description == f"file {tmp_path / '.credentials.json'}"
    github = build_secret_source(AutoSource(), Tool.GITHUB, client, {}, platform="linux")
    assert github.description == "command `gh auth token`"
    assert github.client_commands == ("gh",)


def test_sources_return_nothing_rather_than_empty_secrets(tmp_path: Path) -> None:
    client = FakeShell()
    client.respond("gh", "auth", "token", code=1)
    assert CommandSecret(client, ["gh", "auth", "token"]).read() is None
    assert EnvSecret("TOKEN", {"TOKEN": "  "}).read() is None
    assert FileSecret(tmp_path / "absent").read() is None
    assert EnvSecret("TOKEN", {"TOKEN": "abc"}).read() == Secret("abc")


@pytest.mark.parametrize(
    ("code", "status", "valid", "detail"),
    [
        (0, {"authMethod": "claude.ai", "email": "jane@acme.example"}, True, "jane@acme.example"),
        (1, {"authMethod": "none"}, False, "not logged in"),
        (0, {"authMethod": "oauth_token"}, False, "logged in with oauth_token"),
    ],
)
def test_claude_needs_the_claude_ai_login(
    code: int, status: dict[str, str], valid: bool, detail: str
) -> None:
    box = FakeShell()
    box.respond("claude", "auth", "status", code=code, stdout=json.dumps(status))
    state = ClaudeAuth(box, HOME).state()
    assert state.valid is valid
    assert state.detail.startswith(detail)


def test_claude_install_writes_a_private_credentials_file() -> None:
    box = FakeShell()
    ClaudeAuth(box, HOME).install(Secret("{}"))
    assert box.modes[HOME / ".claude/.credentials.json"] == 0o600


def test_github_login_with_token_and_git_setup() -> None:
    box = FakeShell()
    auth = GithubAuth(box, setup_git=True)
    auth.install(Secret("ghp_x"))
    auth.finish()
    assert box.calls[0][:3] == ("gh", "auth", "login")
    assert box.stdins[0] == "ghp_x\n"
    assert box.ran("gh", "auth", "setup-git")


def _git(azure: ResolvedConfig) -> tuple[FakeShell, GitRepository, tuple[str, ...]]:
    box = FakeShell()
    git = ("git", "-C", "/workspaces/acme/repo")
    return box, GitRepository(box, azure.box_layout, azure.project), git


def test_git_lists_only_outpost_worktrees(azure: ResolvedConfig) -> None:
    box, repository, git = _git(azure)
    box.respond(
        *git, "worktree", "list", "--porcelain",
        stdout=(
            "worktree /workspaces/acme/repo\nHEAD abc\nbranch refs/heads/main\n\n"
            "worktree /workspaces/acme/worktrees/feat-a\nHEAD def\nbranch refs/heads/feature/a\n"
        ),
    )  # fmt: skip
    (only,) = repository.worktrees()
    assert only.name == WorktreeName("feat-a")
    assert only.branch == "feature/a"


def test_git_reuses_a_local_branch_without_resetting_it(azure: ResolvedConfig) -> None:
    box, repository, git = _git(azure)
    box.respond(*git, "rev-parse", "--verify", "--quiet", "refs/heads/feat-a", code=0)
    repository.add_worktree(WorktreeName("feat-a"), "feat-a", None)
    assert box.calls[-1] == (*git, "worktree", "add", "/workspaces/acme/worktrees/feat-a", "feat-a")


def test_git_tracks_a_remote_branch(azure: ResolvedConfig) -> None:
    box, repository, git = _git(azure)
    box.respond(*git, "rev-parse", "--verify", "--quiet", code=1)
    box.respond(*git, "rev-parse", "--verify", "--quiet", "refs/remotes/origin/feat-a", code=0)
    repository.add_worktree(WorktreeName("feat-a"), "feat-a", None)
    assert box.calls[-1][-5:] == (
        "--track", "-b", "feat-a", "/workspaces/acme/worktrees/feat-a", "origin/feat-a",
    )  # fmt: skip


def test_git_starts_a_new_branch_without_upstream(azure: ResolvedConfig) -> None:
    box, repository, git = _git(azure)
    box.respond(*git, "rev-parse", "--verify", "--quiet", code=1)
    repository.add_worktree(WorktreeName("feat-a"), "feat-a", None)
    assert box.calls[-1][-5:] == (
        "--no-track", "-b", "feat-a", "/workspaces/acme/worktrees/feat-a", "origin/main",
    )  # fmt: skip


def test_git_clones_over_the_configured_url(azure: ResolvedConfig) -> None:
    box, repository, _ = _git(azure)
    repository.clone()
    assert box.calls[-1][-2:] == ("https://github.com/acme/platform.git", "/workspaces/acme/repo")
