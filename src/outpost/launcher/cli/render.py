"""Text for the terminal. Nothing here decides anything."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from outpost.domain.environment import Environment
from outpost.domain.host import SshHost
from outpost.launcher.application.doctor import Finding
from outpost.launcher.application.lifecycle import EnvironmentStatus
from outpost.launcher.application.up import UpReport
from outpost.launcher.ports.docker import ContainerState

TRUST: dict[str, Sequence[str]] = {
    "darwin": (
        "security add-trusted-cert -r trustRoot -k ~/Library/Keychains/login.keychain-db {path}",
    ),
    "win32": ("certutil -user -addstore Root {path}",),
    "linux": (
        "sudo cp {path} /usr/local/share/ca-certificates/outpost-ca.crt",
        "sudo update-ca-certificates",
        "certutil -d sql:$HOME/.pki/nssdb -A -t C,, -n outpost -i {path}   # Chrome",
    ),
}


def up_report(report: UpReport, env: Environment) -> str:
    lines = [f"{env.container} is ready on {env.host}."]
    lines += [
        f"  {state.tool}: {'logged in' if state.valid else 'not logged in'}"
        + (f" ({state.detail})" if state.detail else "")
        for state in report.logins
    ]
    lines.append(f"Routes: {env.site.url_pattern()}, e.g. {report.example_url}")
    lines.append("  register one inside with `outpost route add <name> <container>:<port>`")
    if isinstance(env.host, SshHost):
        lines.append("Browse through `./outpost tunnel`, kept open in another terminal.")
    lines.append("Next: `./outpost shell`, then `claude`.")
    return "\n".join(lines)


def status(report: EnvironmentStatus, env: Environment) -> str:
    detail = f" ({report.detail})" if report.detail and report.detail != report.state else ""
    lines = [f"{report.container} on {env.host}: {report.state}{detail}"]
    if report.runtime is not None:
        runtime = report.runtime
        lines.append(f"  boot: {'ready' if runtime.ready else 'in progress'}")
        lines.append(f"  proxy: {'running' if runtime.proxy_running else 'not running'}")
        if runtime.init_failed:
            lines.append(f"  init scripts failed: {', '.join(runtime.init_failed)}")
    lines.append(f"  volumes: {', '.join(report.volumes) or 'none'}")
    if report.state is ContainerState.RESTARTING:
        lines.append("  it keeps restarting: see `./outpost logs`")
    if report.routes.strip():
        lines.append("Routes:")
        lines.extend(f"  {line}" for line in report.routes.strip().splitlines())
    return "\n".join(lines)


def findings(items: Sequence[Finding]) -> str:
    width = max(len(item.check) for item in items)
    return "\n".join(
        f"{item.severity.value:<4}  {item.check:<{width}}  {item.detail}" for item in items
    )


def trust_instructions(path: Path, platform: str) -> str:
    key = next((name for name in TRUST if platform.startswith(name)), "linux")
    commands = [line.format(path=path) for line in TRUST[key]]
    lines = [
        f"Saved the proxy's root certificate to {path}. Trust it once:",
        *commands,
        "Firefox keeps its own list: Settings, Certificates, Import.",
    ]
    return "\n".join(lines)
