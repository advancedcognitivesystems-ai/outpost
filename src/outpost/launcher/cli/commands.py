"""One function per command: arguments into domain values, a use case, then rendered text."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from outpost.domain.transfer import parse_copy
from outpost.launcher.application.doctor import Severity
from outpost.launcher.cli import render
from outpost.launcher.cli.wiring import Launcher

EXIT_OK = 0
EXIT_FAILURE = 1


def up(launcher: Launcher, args: argparse.Namespace) -> int:
    report = launcher.up().run(recreate=args.recreate, assume_yes=args.yes)
    print(render.up_report(report, launcher.env))
    return EXIT_OK


def stop(launcher: Launcher, args: argparse.Namespace) -> int:
    stopped = launcher.lifecycle().stop()
    name = launcher.env.container
    print(f"{name} stopped; its disk is kept." if stopped else f"{name} was not running.")
    return EXIT_OK


def down(launcher: Launcher, args: argparse.Namespace) -> int:
    removed = launcher.lifecycle().down()
    name = launcher.env.container
    print(f"{name} removed; its volumes are kept." if removed else f"{name} does not exist.")
    return EXIT_OK


def destroy(launcher: Launcher, args: argparse.Namespace) -> int:
    volumes = launcher.lifecycle().destroy(assume_yes=args.yes)
    print(f"{launcher.env.container} removed with {len(volumes)} volumes.")
    return EXIT_OK


def status(launcher: Launcher, args: argparse.Namespace) -> int:
    print(render.status(launcher.lifecycle().status(), launcher.env))
    return EXIT_OK


def shell(launcher: Launcher, args: argparse.Namespace) -> int:
    return launcher.access().shell()


def exec_(launcher: Launcher, args: argparse.Namespace) -> int:
    argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
    if not argv:
        raise SystemExit("outpost exec: name a command, as in `./outpost exec -- ls`")
    return launcher.access().run(argv)


def cp(launcher: Launcher, args: argparse.Namespace) -> int:
    landed = launcher.transfers().copy(parse_copy(args.source, args.destination))
    print(f"copied to {landed}")
    return EXIT_OK


def logs(launcher: Launcher, args: argparse.Namespace) -> int:
    return launcher.access().logs(follow=args.follow)


def ca(launcher: Launcher, args: argparse.Namespace) -> int:
    path: Path = args.out
    path.write_text(launcher.access().root_certificate(), encoding="utf-8")
    print(render.trust_instructions(path, sys.platform))
    return EXIT_OK


def tunnel(launcher: Launcher, args: argparse.Namespace) -> int:
    print(f"Forwarding {launcher.env.site.url_pattern()} to {launcher.env.host}; Ctrl-C stops it.")
    return launcher.access().tunnel()


def config(launcher: Launcher, args: argparse.Namespace) -> int:
    print(launcher.up().plan().text(), end="")
    return EXIT_OK


def doctor(launcher: Launcher, args: argparse.Namespace) -> int:
    found = launcher.doctor().run()
    print(render.findings(found))
    return EXIT_FAILURE if any(item.severity is Severity.FAIL for item in found) else EXIT_OK
