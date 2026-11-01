"""Claude Code and GitHub CLI logins: read on your machine, checked and installed in the container.

Claude Code keeps its login in `~/.claude/.credentials.json` on Linux, and in the Keychain on
macOS. `claude auth status` prints JSON and exits 1 when logged out; its `authMethod` must be
`claude.ai`, because a token or an API key would hide the claude.ai connectors.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath

from outpost.domain.credentials import LoginState, Tool
from outpost.domain.errors import CommandFailed
from outpost.domain.layout import HOME, USER
from outpost.domain.secrets import Secret
from outpost.infra.process import Runner
from outpost.launcher.adapters.docker_cli import DockerCli
from outpost.launcher.ports.credentials import LoginSource, ToolLogin

CLAUDE_CREDENTIALS = PurePosixPath(".claude/.credentials.json")
KEYCHAIN_SERVICE = "Claude Code-credentials"
CLAUDE_METHOD = "claude.ai"
GITHUB_HOST = "github.com"
WRITE_PRIVATE = 'mkdir -p "$(dirname "$1")" && umask 077 && cat > "$1" && chmod 600 "$1"'


class FileSource:
    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def description(self) -> str:
        return str(self._path)

    def read(self) -> Secret | None:
        try:
            content = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        return Secret(content) if content.strip() else None


class CommandSource:
    """The trimmed output of a command on your machine; a failing command means no login."""

    def __init__(self, runner: Runner, argv: Sequence[str], description: str) -> None:
        self._runner = runner
        self._argv = tuple(argv)
        self._description = description

    @property
    def description(self) -> str:
        return self._description

    def read(self) -> Secret | None:
        result = self._runner.run(self._argv)
        value = result.stdout.strip()
        return Secret(value) if result.ok and value else None


class _InContainer:
    def __init__(self, docker: DockerCli, container: str) -> None:
        self._docker = docker
        self._container = container

    def _interactive(self, argv: Sequence[str]) -> None:
        code = self._docker.exec_attached(self._container, argv, user=USER, workdir=HOME)
        if code != 0:
            raise CommandFailed(argv, code, "the login did not complete")


class ClaudeLogin(_InContainer):
    @property
    def tool(self) -> Tool:
        return Tool.CLAUDE

    def state(self) -> LoginState:
        result = self._docker.exec(self._container, ["claude", "auth", "status"], user=USER)
        if result.missing_command:
            return LoginState(Tool.CLAUDE, False, "Claude Code is not installed", installed=False)
        try:
            status = json.loads(result.stdout)
        except json.JSONDecodeError:
            return LoginState(Tool.CLAUDE, False, "unexpected `claude auth status` output")
        method = str(status.get("authMethod", "none")) if isinstance(status, dict) else "none"
        if not result.ok or method == "none":
            return LoginState(Tool.CLAUDE, False, "not logged in")
        if method != CLAUDE_METHOD:
            detail = f"logged in with {method}; claude.ai connectors need the claude.ai login"
            return LoginState(Tool.CLAUDE, False, detail)
        return LoginState(Tool.CLAUDE, True, str(status.get("email", CLAUDE_METHOD)))

    def install(self, secret: Secret) -> None:
        target = str(HOME / CLAUDE_CREDENTIALS)
        argv = ["sh", "-c", WRITE_PRIVATE, "sh", target]
        self._docker.exec(self._container, argv, user=USER, stdin=secret.reveal()).check()

    def login(self) -> None:
        self._interactive(["claude", "auth", "login"])

    def finish(self) -> None:
        return None


class GithubLogin(_InContainer):
    @property
    def tool(self) -> Tool:
        return Tool.GITHUB

    def state(self) -> LoginState:
        argv = ["gh", "auth", "status", "--hostname", GITHUB_HOST]
        result = self._docker.exec(self._container, argv, user=USER)
        if result.missing_command:
            return LoginState(Tool.GITHUB, False, "gh is not installed", installed=False)
        text = (result.stdout + result.stderr).strip()
        first = next((line.strip() for line in text.splitlines() if line.strip()), "")
        return LoginState(Tool.GITHUB, result.ok, first if not result.ok else "logged in")

    def install(self, secret: Secret) -> None:
        argv = ["gh", "auth", "login", "--hostname", GITHUB_HOST, "--with-token"]
        self._docker.exec(self._container, argv, user=USER, stdin=secret.reveal() + "\n").check()

    def login(self) -> None:
        self._interactive(
            ["gh", "auth", "login", "--hostname", GITHUB_HOST, "--git-protocol", "https"]
        )

    def finish(self) -> None:
        argv = ["gh", "auth", "setup-git", "--hostname", GITHUB_HOST]
        self._docker.exec(self._container, argv, user=USER).check()


def login_source(
    tool: Tool, runner: Runner, environ: Mapping[str, str], platform: str = sys.platform
) -> LoginSource:
    """Your login: the Keychain on macOS, the credentials file elsewhere, `gh auth token`."""
    match tool:
        case Tool.CLAUDE if platform == "darwin":
            argv = ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"]
            return CommandSource(runner, argv, "the macOS Keychain")
        case Tool.CLAUDE:
            configured = environ.get("CLAUDE_CONFIG_DIR")
            directory = Path(configured) if configured else Path.home() / ".claude"
            return FileSource(directory / CLAUDE_CREDENTIALS.name)
        case Tool.GITHUB:
            return CommandSource(runner, ["gh", "auth", "token"], "`gh auth token`")


def tool_login(tool: Tool, docker: DockerCli, container: str) -> ToolLogin:
    match tool:
        case Tool.CLAUDE:
            return ClaudeLogin(docker, container)
        case Tool.GITHUB:
            return GithubLogin(docker, container)
