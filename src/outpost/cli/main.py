"""Argument parsing and exit codes. Every command lives in `commands`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from outpost import __version__
from outpost.cli import commands
from outpost.cli.commands import worktree_name
from outpost.domain.credentials import Tool
from outpost.domain.errors import ConfigError, Declined, OutpostError

EXIT_FAILURE = 1
EXIT_CONFIG = 2
EXIT_DECLINED = 3
EXIT_INTERRUPTED = 130

Handler = Callable[[argparse.Namespace], int]
if TYPE_CHECKING:
    Subcommands = argparse._SubParsersAction[argparse.ArgumentParser]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="outpost", description="Remote development environments from one script."
    )
    parser.add_argument("--version", action="version", version=f"outpost {__version__}")
    parser.add_argument(
        "--config", type=Path, default=Path("outpost.yaml"), help="configuration file"
    )
    parser.add_argument("--target", help="target to use instead of default_target")
    parser.add_argument("--yes", action="store_true", help="accept every fix, never prompt")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, change nothing")
    parser.add_argument("-v", "--verbose", action="store_true", help="print every command run")
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    def command(
        name: str, handler: Handler | None, help_text: str, into: Subcommands = sub
    ) -> argparse.ArgumentParser:
        created = into.add_parser(name, help=help_text, description=help_text)
        if handler is not None:
            created.set_defaults(handler=handler)
        return created

    command("init", commands.init, "write outpost.yaml from the example")

    config = command("config", None, "inspect the configuration")
    config_sub = config.add_subparsers(dest="action", required=True, metavar="<action>")
    command(
        "validate", commands.config_validate, "validate and name the resolved target", config_sub
    )
    command("show", commands.config_show, "print the resolved configuration", config_sub)

    doctor = command("doctor", commands.doctor, "check everything, offer fixes")
    doctor.add_argument("--fix", action="store_true", help="apply the fixes the checks offer")

    command("up", commands.up, "converge the host to the configuration")
    command("down", commands.down, "stop the box and the edge, keep everything")
    destroy = command("destroy", commands.destroy, "remove containers and networks")
    destroy.add_argument("--volumes", action="store_true", help="also remove the volumes")
    command("status", commands.status, "edge, box, running stacks and their URLs")
    shell = command("shell", commands.shell, "interactive shell in the box")
    shell.add_argument("worktree", nargs="?", type=worktree_name)

    worktree = command("worktree", None, "manage worktrees")
    worktree_sub = worktree.add_subparsers(dest="action", required=True, metavar="<action>")
    add = command("add", commands.worktree_add, "create a worktree", worktree_sub)
    add.add_argument("name", type=worktree_name)
    add.add_argument("--branch", help="branch name (default: the worktree name)")
    add.add_argument("--from", dest="start", help="start point (default: origin/<default_branch>)")
    command("ls", commands.worktree_ls, "list worktrees", worktree_sub)
    remove = command("rm", commands.worktree_rm, "stop its stack, remove a worktree", worktree_sub)
    remove.add_argument("name", type=worktree_name)
    remove.add_argument("--force", action="store_true", help="remove even with local changes")

    stack = command("stack", None, "manage stacks")
    stack_sub = stack.add_subparsers(dest="action", required=True, metavar="<action>")
    for name, handler, help_text in (
        ("up", commands.stack_up, "start a worktree's stack"),
        ("down", commands.stack_down, "stop a worktree's stack"),
        ("urls", commands.stack_urls, "print a worktree's URLs"),
    ):
        command(name, handler, help_text, stack_sub).add_argument("worktree", type=worktree_name)
    command("ls", commands.stack_ls, "list running stacks", stack_sub)
    logs = command("logs", commands.stack_logs, "follow a stack's logs", stack_sub)
    logs.add_argument("worktree", type=worktree_name)
    logs.add_argument("service", nargs="?")
    forward = command("forward", commands.stack_forward, "tunnel a non-HTTP port", stack_sub)
    forward.add_argument("worktree", type=worktree_name)
    forward.add_argument("service")
    forward.add_argument("port", type=int)

    creds = command("creds", None, "credentials in the box")
    creds_sub = creds.add_subparsers(dest="action", required=True, metavar="<action>")
    command("status", commands.creds_status, "login state of each tool", creds_sub)
    sync = command("sync", commands.creds_sync, "run the credential flow", creds_sub)
    sync.add_argument("--only", choices=[tool.value for tool in Tool])

    tls = command("tls", None, "certificates")
    tls_sub = tls.add_subparsers(dest="action", required=True, metavar="<action>")
    command("trust", commands.tls_trust, "export the local CA to trust it", tls_sub)
    command("status", commands.tls_status, "certificate names and expiry", tls_sub)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler: Handler = args.handler
    try:
        return handler(args)
    except ConfigError as error:
        return _fail(f"configuration: {error}", EXIT_CONFIG)
    except Declined as error:
        return _fail(f"stopped: {error}", EXIT_DECLINED)
    except OutpostError as error:
        return _fail(str(error), EXIT_FAILURE)
    except KeyboardInterrupt:
        return _fail("interrupted", EXIT_INTERRUPTED)


def _fail(message: str, code: int) -> int:
    print(f"outpost: {message}", file=sys.stderr)
    return code
