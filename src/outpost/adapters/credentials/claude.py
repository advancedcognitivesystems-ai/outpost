"""Claude Code: login state, credential file, interactive login.

Claude Code keeps its login in `~/.claude/.credentials.json` on Linux. The box is Linux, so
installing a copied login means writing that file with mode 0600. `claude auth status` prints
JSON and exits 1 when logged out; its `authMethod` must be `claude.ai`, because any other method
(a token or an API key from the environment, for instance) hides the claude.ai connectors.
"""

from __future__ import annotations

import json
from pathlib import PurePosixPath

from outpost.domain.credentials import AuthState, Tool
from outpost.domain.errors import CommandFailed
from outpost.domain.secrets import Secret
from outpost.ports.shell import Shell

CREDENTIALS_FILE = PurePosixPath(".claude/.credentials.json")
KEYCHAIN_SERVICE = "Claude Code-credentials"
REQUIRED_METHOD = "claude.ai"


class ClaudeAuth:
    def __init__(self, shell: Shell, home: PurePosixPath) -> None:
        self._shell = shell
        self._home = home

    @property
    def tool(self) -> Tool:
        return Tool.CLAUDE

    def state(self) -> AuthState:
        result = self._shell.run(["claude", "auth", "status"])
        if result.missing_command:
            return AuthState(Tool.CLAUDE, False, "claude is not installed")
        try:
            status = json.loads(result.stdout)
        except json.JSONDecodeError:
            return AuthState(Tool.CLAUDE, False, "unexpected `claude auth status` output")
        method = str(status.get("authMethod", "none"))
        if not result.ok or method == "none":
            return AuthState(Tool.CLAUDE, False, "not logged in")
        if method != REQUIRED_METHOD:
            return AuthState(
                Tool.CLAUDE, False, f"logged in with {method}; claude.ai connectors need claude.ai"
            )
        return AuthState(Tool.CLAUDE, True, str(status.get("email", REQUIRED_METHOD)))

    def install(self, secret: Secret) -> None:
        self._shell.write_file(self._home / CREDENTIALS_FILE, secret.reveal(), mode=0o600)

    def login(self) -> None:
        argv = ["claude", "auth", "login"]
        code = self._shell.run_interactive(argv)
        if code != 0:
            raise CommandFailed(argv, code, "the login did not complete")

    def finish(self) -> None:
        return None
