"""Source kind to `SecretSource`, tool to `ToolAuth`; `auto` is resolved here per tool and OS."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from outpost.adapters.credentials.claude import CREDENTIALS_FILE, KEYCHAIN_SERVICE, ClaudeAuth
from outpost.adapters.credentials.github import TOKEN_COMMAND, GithubAuth
from outpost.adapters.credentials.sources import CommandSecret, EnvSecret, FileSecret
from outpost.domain.config import (
    AutoSource,
    CommandSource,
    EnvSource,
    FileSource,
    KeychainSource,
    SecretSourceSpec,
)
from outpost.domain.credentials import Tool
from outpost.ports.credentials import SecretSource, ToolAuth
from outpost.ports.shell import Shell


def build_secret_source(
    spec: SecretSourceSpec,
    tool: Tool,
    client: Shell,
    environ: Mapping[str, str],
    platform: str = sys.platform,
) -> SecretSource:
    match spec:
        case AutoSource():
            return build_secret_source(_auto(tool, environ, platform), tool, client, environ)
        case FileSource(path=path):
            return FileSecret(Path(path).expanduser())
        case KeychainSource(service=service, account=account):
            account_args = ["-a", account] if account else []
            argv = ["security", "find-generic-password", "-s", service, *account_args, "-w"]
            return CommandSecret(client, argv)
        case CommandSource(argv=argv):
            return CommandSecret(client, argv)
        case EnvSource(name=name):
            return EnvSecret(name, environ)


def _auto(tool: Tool, environ: Mapping[str, str], platform: str) -> SecretSourceSpec:
    match tool:
        case Tool.CLAUDE if platform == "darwin":
            return KeychainSource(service=KEYCHAIN_SERVICE)
        case Tool.CLAUDE:
            config_dir = environ.get("CLAUDE_CONFIG_DIR")
            directory = Path(config_dir) if config_dir else Path.home() / ".claude"
            return FileSource(path=str(directory / CREDENTIALS_FILE.name))
        case Tool.GITHUB:
            return CommandSource(argv=TOKEN_COMMAND)


def build_tool_auth(tool: Tool, shell: Shell, home: PurePosixPath, *, setup_git: bool) -> ToolAuth:
    match tool:
        case Tool.CLAUDE:
            return ClaudeAuth(shell, home)
        case Tool.GITHUB:
            return GithubAuth(shell, setup_git=setup_git)
