"""One function per command: parse arguments into domain values, call a use case, render."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys
from pathlib import Path

from outpost.cli import render
from outpost.cli.wiring import App, Options, standalone_prompter
from outpost.domain.credentials import Tool
from outpost.domain.errors import ConfigError, InvalidValue, NotImplementedYet
from outpost.domain.names import WorktreeName
from outpost.ports.engine import ContainerState

EXAMPLE_FILE = "outpost.example.yaml"
CA_FILE = "outpost-ca.pem"
INIT_TARGETS = ("wsl", "azure")


def _app(args: argparse.Namespace) -> App:
    return App(
        Options(
            config_path=args.config,
            target=args.target,
            assume_yes=args.yes,
            verbose=args.verbose,
            dry_run=args.dry_run,
        )
    )


def _outpost_home() -> Path:
    configured = os.environ.get("OUTPOST_HOME")
    return Path(configured) if configured else Path(__file__).resolve().parents[3]


# -------------------------------------------------------------------- setup


def init(args: argparse.Namespace) -> int:
    destination: Path = args.config
    if destination.exists():
        raise ConfigError("", f"{destination} already exists; edit it or remove it first")
    example = (_outpost_home() / EXAMPLE_FILE).read_text(encoding="utf-8")
    prompter = standalone_prompter(assume_yes=args.yes)
    target = INIT_TARGETS[prompter.choose("Which target will you use first?", INIT_TARGETS)]
    text = re.sub(r"(?m)^default_target: \S+", f"default_target: {target}", example, count=1)
    destination.write_text(text, encoding="utf-8")
    prompter.info(f"wrote {destination}; fill in the `{target}` target, then `outpost doctor`")
    return 0


def config_validate(args: argparse.Namespace) -> int:
    app = _app(args)
    config = app.config
    print(f"valid: project {config.project.name}, target {config.target.name}")
    return 0


def config_show(args: argparse.Namespace) -> int:
    config = _app(args).config
    print(json.dumps(dataclasses.asdict(config), indent=2, default=str))
    return 0


def doctor(args: argparse.Namespace) -> int:
    report = _app(args).doctor.run(fix=args.fix)
    render.doctor_report(report, sys.stdout)
    return 1 if report.blocking else 0


# -------------------------------------------------------------------- lifecycle


def up(args: argparse.Namespace) -> int:
    _app(args).environment.up()
    return 0


def down(args: argparse.Namespace) -> int:
    _app(args).environment.down()
    return 0


def destroy(args: argparse.Namespace) -> int:
    raise NotImplementedYet("`outpost destroy` is designed but not built yet")


def status(args: argparse.Namespace) -> int:
    app = _app(args)
    current = app.environment.status()
    render.environment_status(current, sys.stdout)
    if current.box is ContainerState.RUNNING:
        for worktree in app.stacks.running():
            render.lines(app.stacks.urls(worktree), sys.stdout, empty=f"{worktree}: no routes")
    return 0


def shell(args: argparse.Namespace) -> int:
    return _app(args).session.open(args.worktree)


# -------------------------------------------------------------------- worktrees and stacks


def worktree_add(args: argparse.Namespace) -> int:
    created = _app(args).worktrees.add(args.name, branch=args.branch, start=args.start)
    print(f"{created.name}: branch {created.branch} at {created.path}")
    return 0


def worktree_ls(args: argparse.Namespace) -> int:
    render.worktrees(_app(args).worktrees.list(), sys.stdout)
    return 0


def worktree_rm(args: argparse.Namespace) -> int:
    _app(args).worktrees.remove(args.name, force=args.force)
    return 0


def stack_up(args: argparse.Namespace) -> int:
    render.lines(_app(args).stacks.up(args.worktree), sys.stdout, empty="started, no routes")
    return 0


def stack_down(args: argparse.Namespace) -> int:
    _app(args).stacks.down(args.worktree)
    return 0


def stack_ls(args: argparse.Namespace) -> int:
    running = [str(name) for name in _app(args).stacks.running()]
    render.lines(running, sys.stdout, empty="no stack running")
    return 0


def stack_urls(args: argparse.Namespace) -> int:
    render.lines(_app(args).stacks.urls(args.worktree), sys.stdout, empty="no exposed services")
    return 0


def stack_logs(args: argparse.Namespace) -> int:
    return _app(args).stacks.follow_logs(args.worktree, args.service)


def stack_forward(args: argparse.Namespace) -> int:
    raise NotImplementedYet("`outpost stack forward` is designed but not built yet")


# -------------------------------------------------------------------- credentials and TLS


def creds_status(args: argparse.Namespace) -> int:
    credentials = _app(args).credentials
    states = [credentials.state(tool) for tool in credentials.tools]
    render.auth_states(states, sys.stdout)
    return 0 if all(state.valid for state in states) else 1


def creds_sync(args: argparse.Namespace) -> int:
    only = Tool(args.only) if args.only else None
    render.auth_states(_app(args).credentials.sync(only), sys.stdout)
    return 0


def tls_trust(args: argparse.Namespace) -> int:
    bundle = _app(args).environment.trust_bundle()
    if bundle is None:
        print("nothing to trust: this target uses a publicly trusted certificate or plain HTTP")
        return 0
    destination = Path(CA_FILE)
    destination.write_text(bundle, encoding="utf-8")
    print(f"wrote {destination.resolve()}; add it to your system or browser trust store")
    return 0


def tls_status(args: argparse.Namespace) -> int:
    raise NotImplementedYet("`outpost tls status` is designed but not built yet")


def worktree_name(value: str) -> WorktreeName:
    """argparse type for worktree arguments: the domain rule, reported as a usage error."""
    try:
        return WorktreeName(value)
    except InvalidValue as error:
        raise argparse.ArgumentTypeError(str(error)) from None
