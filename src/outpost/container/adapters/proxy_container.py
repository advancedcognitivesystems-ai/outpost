"""`ProxyRuntime`: Caddy as a container of the inner Docker, on the network stacks join."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from outpost.container.adapters.caddy import SOCKET_DIR_IN_PROXY, saved_routes, with_routes
from outpost.domain.layout import (
    ADMIN_SOCKET,
    NETWORK,
    PROXY_BASE_CONFIG,
    PROXY_CONTAINER,
    PROXY_LISTEN_PORT,
    PROXY_STATE,
)
from outpost.domain.routes import DEVCONTAINER
from outpost.infra.process import CommandResult, Runner

PROXY_IMAGE = "caddy:2.11"
PROXY_LABEL = "outpost.proxy"
CONFIG_IN_PROXY = "/etc/caddy/outpost.json"
AUTOSAVE = Path("caddy") / "autosave.json"
SOCKET_GROUP = "docker"
"""Who may use the admin socket besides root: the docker group, of which dev is a member."""


class CaddyContainer:
    def __init__(
        self,
        runner: Runner,
        *,
        site_port: int,
        base_config: Path = Path(PROXY_BASE_CONFIG),
        state: Path = Path(PROXY_STATE),
        socket_dir: Path = Path(ADMIN_SOCKET).parent,
        socket_group: str | None = SOCKET_GROUP,
        image: str = PROXY_IMAGE,
    ) -> None:
        self._runner = runner
        self._site_port = site_port
        self._base_config = base_config
        self._state = state
        self._socket_dir = socket_dir
        self._socket_group = socket_group
        self._image = image

    def ensure_running(self) -> None:
        self._prepare_socket_dir()
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
            self._docker("stop", PROXY_CONTAINER)
            self._docker("rm", "--force", PROXY_CONTAINER, check=True)
        self._carry_routes_over()
        self._docker(*self._run_arguments(spec), check=True)

    def _prepare_socket_dir(self) -> None:
        """The socket's folder: root and the docker group may enter it, nobody else."""
        self._socket_dir.mkdir(parents=True, exist_ok=True)
        self._socket_dir.chmod(0o750)
        if self._socket_group is not None:
            shutil.chown(self._socket_dir, group=self._socket_group)

    def _spec(self) -> str:
        """What the proxy is made of; a change recreates it, keeping its routes and its CA."""
        digest = hashlib.sha256(self._base_config.read_bytes())
        digest.update(json.dumps(self._run_arguments("")).encode())
        return digest.hexdigest()[:12]

    def _carry_routes_over(self) -> None:
        """Rewrite the saved config as the new base plus the saved routes, for `--resume`.

        A saved config that cannot be read is set aside: the proxy starts from the base, and
        boot reports no routes rather than a proxy that never starts.
        """
        saved = self._state / "config" / AUTOSAVE
        (self._state / "data").mkdir(parents=True, exist_ok=True)
        saved.parent.mkdir(parents=True, exist_ok=True)
        if not saved.is_file():
            return
        try:
            routes = saved_routes(json.loads(saved.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            saved.replace(saved.with_suffix(".unreadable"))
            return
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
            *self._published(),
            "--add-host",
            f"{DEVCONTAINER}:host-gateway",
            "--volume",
            f"{self._state / 'data'}:/data",
            "--volume",
            f"{self._state / 'config'}:/config",
            "--volume",
            f"{self._socket_dir}:{SOCKET_DIR_IN_PROXY}",
            "--volume",
            f"{self._base_config}:{CONFIG_IN_PROXY}:ro",
            self._image,
            "caddy",
            "run",
            "--resume",
            "--config",
            CONFIG_IN_PROXY,
        ]

    def _published(self) -> list[str]:
        """The port the host's publication reaches, and the port in the routes' URLs, so those
        URLs work in the dev container too."""
        ports = dict.fromkeys((PROXY_LISTEN_PORT, self._site_port))
        return [part for port in ports for part in ("--publish", f"{port}:{PROXY_LISTEN_PORT}")]

    def _docker(self, *argv: str, check: bool = False) -> CommandResult:
        result = self._runner.run(["docker", *argv])
        return result.check() if check else result
