"""`ProxyRuntime`: Caddy as a container of the inner Docker, on the network stacks join."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from outpost.container.adapters.caddy import saved_routes, with_routes
from outpost.domain.commands import CommandResult
from outpost.domain.layout import (
    ADMIN_PORT,
    NETWORK,
    PROXY_BASE_CONFIG,
    PROXY_CONTAINER,
    PROXY_LISTEN_PORT,
    PROXY_STATE,
)
from outpost.domain.routes import DEVCONTAINER
from outpost.infra.process import Runner

PROXY_IMAGE = "caddy:2.11"
PROXY_LABEL = "outpost.proxy"
CONFIG_IN_PROXY = "/etc/caddy/outpost.json"
AUTOSAVE = Path("caddy") / "autosave.json"


class CaddyContainer:
    def __init__(
        self,
        runner: Runner,
        *,
        base_config: Path = Path(PROXY_BASE_CONFIG),
        state: Path = Path(PROXY_STATE),
        image: str = PROXY_IMAGE,
    ) -> None:
        self._runner = runner
        self._base_config = base_config
        self._state = state
        self._image = image

    def ensure_running(self) -> None:
        if not self._docker("network", "inspect", NETWORK).ok:
            self._docker("network", "create", NETWORK, check=True)
        template = f'{{{{.State.Running}}}} {{{{index .Config.Labels "{PROXY_LABEL}"}}}}'
        found = self._docker("container", "inspect", "--format", template, PROXY_CONTAINER)
        running, _, label = found.stdout.strip().partition(" ")
        spec = self._spec()
        if found.ok and label == spec:
            if running != "true":
                self._docker("start", PROXY_CONTAINER, check=True)
            return
        if found.ok:
            self._docker("rm", "--force", PROXY_CONTAINER, check=True)
        self._carry_routes_over()
        self._docker(*self._run_arguments(spec), check=True)

    def _spec(self) -> str:
        """What the proxy is made of; a change recreates it, keeping its routes and its CA."""
        digest = hashlib.sha256(self._base_config.read_bytes())
        digest.update(json.dumps(self._run_arguments("")).encode())
        return digest.hexdigest()[:12]

    def _carry_routes_over(self) -> None:
        """Rewrite the saved config as the new base plus the saved routes, for `--resume`."""
        saved = self._state / "config" / AUTOSAVE
        (self._state / "data").mkdir(parents=True, exist_ok=True)
        saved.parent.mkdir(parents=True, exist_ok=True)
        if not saved.is_file():
            return
        routes = saved_routes(json.loads(saved.read_text(encoding="utf-8")))
        base = json.loads(self._base_config.read_text(encoding="utf-8"))
        saved.write_text(json.dumps(with_routes(base, routes)), encoding="utf-8")

    def _run_arguments(self, spec: str) -> list[str]:
        return [
            "run",
            "--detach",
            "--name",
            PROXY_CONTAINER,
            "--restart",
            "unless-stopped",
            "--network",
            NETWORK,
            "--label",
            f"{PROXY_LABEL}={spec}",
            "--publish",
            f"{PROXY_LISTEN_PORT}:{PROXY_LISTEN_PORT}",
            "--publish",
            f"127.0.0.1:{ADMIN_PORT}:{ADMIN_PORT}",
            "--add-host",
            f"{DEVCONTAINER}:host-gateway",
            "--volume",
            f"{self._state / 'data'}:/data",
            "--volume",
            f"{self._state / 'config'}:/config",
            "--volume",
            f"{self._base_config}:{CONFIG_IN_PROXY}:ro",
            self._image,
            "caddy",
            "run",
            "--resume",
            "--config",
            CONFIG_IN_PROXY,
        ]

    def _docker(self, *argv: str, check: bool = False) -> CommandResult:
        result = self._runner.run(["docker", *argv])
        return result.check() if check else result
