"""`outpost` inside the dev container: routes for stacks, the proxy's certificate, status."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from outpost import __version__
from outpost.container.cli.wiring import InContainer
from outpost.domain.errors import InvalidValue, OutpostError
from outpost.domain.layout import NETWORK
from outpost.domain.names import DnsName
from outpost.domain.routes import Upstream
from outpost.domain.status import INIT_SCRIPTS_FAILED

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2

Handler = Callable[[InContainer, argparse.Namespace], int]
if TYPE_CHECKING:
    Subcommands = argparse._SubParsersAction[argparse.ArgumentParser]


def route_add(tool: InContainer, args: argparse.Namespace) -> int:
    added = tool.routes().add(DnsName(args.name), Upstream.parse(args.upstream))
    print(added.url)
    if added.attached:
        print(
            f"outpost: attached {added.attached} to the `{NETWORK}` network; a container created "
            "again, as a compose change does, leaves it: add the route again, or declare the "
            "network in your compose file",
            file=sys.stderr,
        )
    return EXIT_OK


def route_rm(tool: InContainer, args: argparse.Namespace) -> int:
    for name in tool.routes().remove(args.names):
        print(f"removed {name}")
    return EXIT_OK


def route_ls(tool: InContainer, args: argparse.Namespace) -> int:
    listing = tool.routes().listing()
    if args.json:
        rows = [
            {"name": item.route.name.value, "url": item.url, "upstream": str(item.route.upstream)}
            for item in listing
        ]
        print(json.dumps(rows, indent=2))
    elif not listing:
        print("No routes. Add one with `outpost route add <name> <container>:<port>`.")
    else:
        width = max(len(item.url) for item in listing)
        for item in listing:
            print(f"{item.url:<{width}}  ->  {item.route.upstream}")
    return EXIT_OK


def ca(tool: InContainer, args: argparse.Namespace) -> int:
    print(tool.root_certificate(), end="")
    return EXIT_OK


def status(tool: InContainer, args: argparse.Namespace) -> int:
    report = tool.status().report()
    if args.json:
        print(report.to_json(), end="")
        return EXIT_OK
    print(f"boot: {'ready' if report.ready else 'in progress'}")
    print(f"proxy: {'running' if report.proxy_running else 'not running'}, {report.routes} routes")
    if report.init_failed:
        print(f"init scripts failed: {', '.join(report.init_failed)}")
    return EXIT_OK


def proxy_start(tool: InContainer, args: argparse.Namespace) -> int:
    count = tool.proxy_startup().run()
    print(f"proxy running with {count} routes")
    return EXIT_OK


def boot(tool: InContainer, args: argparse.Namespace) -> int:
    record = tool.boot().run()
    print(f"outpost: ready ({len(record.init_failed)} init scripts failed)", file=sys.stderr)
    return EXIT_OK


def init(tool: InContainer, args: argparse.Namespace) -> int:
    record = tool.init().run(only_if_changed=args.if_changed)
    if record.init_failed:
        print(f"outpost: init scripts failed: {', '.join(record.init_failed)}", file=sys.stderr)
        return INIT_SCRIPTS_FAILED
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="outpost", description="Outpost inside the dev container: routes, certificate, status."
    )
    parser.add_argument("--version", action="version", version=f"outpost {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    def command(
        into: Subcommands, name: str, handler: Handler, text: str
    ) -> argparse.ArgumentParser:
        created = into.add_parser(name, help=text, description=text)
        created.set_defaults(handler=handler)
        return created

    route = sub.add_parser("route", help="serve stacks over HTTPS", description="manage routes")
    routes = route.add_subparsers(dest="action", required=True, metavar="<action>")
    add = command(routes, "add", route_add, "serve https://NAME.<domain> from UPSTREAM")
    add.add_argument("name", help="route name, such as api.feat-a")
    add.add_argument("upstream", help="container:port, or devcontainer:port")
    rm = command(routes, "rm", route_rm, "remove routes; names may use *")
    rm.add_argument("names", nargs="+", metavar="name")
    ls = command(routes, "ls", route_ls, "list routes with their URLs")
    ls.add_argument("--json", action="store_true")
    proxy = sub.add_parser("proxy", help="the proxy's container", description="the proxy")
    proxies = proxy.add_subparsers(dest="action", required=True, metavar="<action>")
    command(proxies, "start", proxy_start, "start the proxy, or create it again, with its routes")
    command(sub, "ca", ca, "print the proxy's root certificate")
    state = command(sub, "status", status, "boot, proxy and init state")
    state.add_argument("--json", action="store_true")
    command(sub, "boot", boot, "start the proxy and run init scripts (the entrypoint runs it)")
    rerun = command(sub, "init", init, "run the init scripts")
    rerun.add_argument("--if-changed", action="store_true", help="only when they changed")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler: Handler = args.handler
    try:
        return handler(InContainer(), args)
    except InvalidValue as error:
        print(f"outpost: {error}", file=sys.stderr)
        return EXIT_USAGE
    except PermissionError as error:
        print(
            f"outpost: {error}; `boot`, `init` and `proxy start` run as root, with sudo",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    except (OutpostError, OSError) as error:
        print(f"outpost: {error}", file=sys.stderr)
        return EXIT_FAILURE


if __name__ == "__main__":
    sys.exit(main())
