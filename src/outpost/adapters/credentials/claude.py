"""Claude Code: login state, credential file, interactive login.

Claude Code keeps its login in `~/.claude/.credentials.json` on Linux. The box is Linux, so
installing a copied login means writing that file with mode 0600.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from outpost.adapters.shell.process import COMMAND_NOT_FOUND
from outpost.domain.credentials import AuthState, Tool
from outpost.domain.errors import CommandFailed
from outpost.domain.secrets import Secret
from outpost.ports.shell import Shell

CREDENTIALS_FILE = PurePosixPath(".claude/.credentials.json")
KEYCHAIN_SERVICE = "Claude Code-credentials"
_LOGGED_OUT_MARKERS = ("not logged in", "not authenticated", "please run /login")
# Either variable takes precedence over the claude.ai login and hides claude.ai connectors.
OVERRIDING_VARIABLES = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY")
_PRINT_SET = 'for name; do printenv "$name" >/dev/null && echo "$name"; done; true'


class ClaudeAuth:
    def __init__(self, shell: Shell, home: PurePosixPath) -> None:
        self._shell = shell
        self._home = home

    @property
    def tool(self) -> Tool:
        return Tool.CLAUDE

    def state(self) -> AuthState:
        overriding = self._shell.run(["sh", "-c", _PRINT_SET, "sh", *OVERRIDING_VARIABLES])
        if overriding.stdout.strip():
            names = ", ".join(overriding.stdout.split())
            return AuthState(
                Tool.CLAUDE, False, f"{names} set: it hides the claude.ai login; unset it"
            )
        result = self._shell.run(["claude", "auth", "status"])
        if result.code == COMMAND_NOT_FOUND:
            return AuthState(Tool.CLAUDE, False, "claude is not installed")
        text = (result.stdout + result.stderr).strip()
        logged_out = any(marker in text.lower() for marker in _LOGGED_OUT_MARKERS)
        summary = text.splitlines()[0] if text else ""
        return AuthState(Tool.CLAUDE, result.ok and not logged_out, summary)

    def install(self, secret: Secret) -> None:
        self._shell.write_file(self._home / CREDENTIALS_FILE, secret.reveal(), mode=0o600)

    def login(self) -> None:
        argv = ["claude", "auth", "login"]
        code = self._shell.run_interactive(argv)
        if code != 0:
            raise CommandFailed(argv, code, "the login did not complete")

    def finish(self) -> None:
        return None
