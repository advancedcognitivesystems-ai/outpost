"""GitHub CLI: login state, token login, interactive login, git integration."""

from __future__ import annotations

from outpost.domain.credentials import AuthState, Tool
from outpost.domain.errors import CommandFailed
from outpost.domain.secrets import Secret
from outpost.ports.shell import Shell

HOSTNAME = "github.com"
TOKEN_COMMAND = ("gh", "auth", "token")


class GithubAuth:
    def __init__(self, shell: Shell, *, setup_git: bool) -> None:
        self._shell = shell
        self._setup_git = setup_git

    @property
    def tool(self) -> Tool:
        return Tool.GITHUB

    def state(self) -> AuthState:
        result = self._shell.run(["gh", "auth", "status", "--hostname", HOSTNAME])
        if result.missing_command:
            return AuthState(Tool.GITHUB, False, "gh is not installed")
        text = (result.stdout + result.stderr).strip()
        return AuthState(Tool.GITHUB, result.ok, text.splitlines()[0] if text else "")

    def install(self, secret: Secret) -> None:
        argv = ["gh", "auth", "login", "--hostname", HOSTNAME, "--with-token"]
        self._shell.run(argv, stdin=secret.reveal() + "\n").check()

    def login(self) -> None:
        argv = ["gh", "auth", "login", "--hostname", HOSTNAME, "--git-protocol", "https", "--web"]
        code = self._shell.run_interactive(argv)
        if code != 0:
            raise CommandFailed(argv, code, "the login did not complete")

    def finish(self) -> None:
        if self._setup_git:
            self._shell.run(["gh", "auth", "setup-git", "--hostname", HOSTNAME]).check()
