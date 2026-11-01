"""`./outpost`: argument parsing and exit codes. Each command is a function in `commands`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from outpost import __version__
from outpost.domain.errors import ConfigError, Declined, InvalidValue, OutpostError
from outpost.launcher.cli import commands
from outpost.launcher.cli.wiring import Launcher, Options

EXIT_USAGE = 2
EXIT_DECLINED = 3
EXIT_INTERRUPTED = 130
CA_FILE = "outpost-ca.pem"

Handler = Callable[[Launcher, argparse.Namespace], int]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="outpost", description="Run and reach your Outpost dev container."
    )
    parser.add_argument("--version", action="version", version=f"outpost {__version__}")
    parser.add_argument(
        "--config", type=Path, help="outpost.yaml to use (default: ./outpost.yaml if present)"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="print every command run")
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    def command(name: str, handler: Handler, text: str) -> argparse.ArgumentParser:
        created = sub.add_parser(name, help=text, description=text)
        created.set_defaults(handler=handler, yes=False)
        return created

    up = command("up", commands.up, "create or start the dev container, then logins and init")
    up.add_argument("--yes", action="store_true", help="agree to recreate when settings changed")
    up.add_argument("--recreate", action="store_true", help="recreate it, keeping the volumes")
    command("stop", commands.stop, "stop the container; its disk stays as it is")
    command("down", commands.down, "remove the container; the volumes stay")
    destroy = command("destroy", commands.destroy, "remove the container and its volumes")
    destroy.add_argument("--yes", action="store_true", help="do not ask for the name")
    command("status", commands.status, "container, volumes, routes, init result")
    command("shell", commands.shell, "a login shell as dev in /workspaces")
    run = command("exec", commands.exec_, "run one command as dev: ./outpost exec -- CMD")
    run.add_argument("argv", nargs=argparse.REMAINDER, help="the command and its arguments")
    cp = command("cp", commands.cp, "copy in or out; the container side starts with ':'")
    cp.add_argument("source")
    cp.add_argument("destination")
    logs = command("logs", commands.logs, "the container's log: boot and init at each start")
    logs.add_argument("-f", "--follow", action="store_true", help="keep following")
    ca = command("ca", commands.ca, "save the proxy's root certificate and show how to trust it")
    ca.add_argument("--out", type=Path, default=Path(CA_FILE), help=f"default: ./{CA_FILE}")
    command("tunnel", commands.tunnel, "remote host: forward the proxy's port over SSH")
    command("config", commands.config, "print the devcontainer.json Outpost runs")
    command("doctor", commands.doctor, "check your machine, the host and your logins")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    launcher = Launcher(Options(config=args.config, verbose=args.verbose, assume_yes=args.yes))
    handler: Handler = args.handler
    try:
        return handler(launcher, args)
    except (ConfigError, InvalidValue) as error:
        print(f"outpost: {error}", file=sys.stderr)
        return EXIT_USAGE
    except Declined as error:
        print(f"outpost: declined: {error}", file=sys.stderr)
        return EXIT_DECLINED
    except (OutpostError, OSError) as error:
        print(f"outpost: {error}", file=sys.stderr)
        return commands.EXIT_FAILURE
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED


if __name__ == "__main__":
    sys.exit(main())
