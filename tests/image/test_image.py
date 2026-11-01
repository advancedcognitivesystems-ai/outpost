"""The image in `image/` agrees with the layout and the adapters that rely on it."""

from __future__ import annotations

import ast
import json
import tomllib
from pathlib import Path

from outpost.container.adapters.caddy import SERVER, SOCKET_DIR_IN_PROXY
from outpost.domain.layout import (
    ADMIN_SOCKET,
    CA_BUNDLE,
    IMAGE_INIT_DIR,
    PROXY_BASE_CONFIG,
    PROXY_LISTEN_PORT,
    STATE,
    TOOL,
    TRUSTED_CA,
    USER,
    WORKSPACES,
)
from outpost.launcher.adapters.base_image import SOURCES

REPOSITORY = Path(__file__).resolve().parents[2]
IMAGE = REPOSITORY / "image"
IN_CONTAINER = ("domain", "container", "infra")


def text(name: str) -> str:
    return (IMAGE / name).read_text(encoding="utf-8")


def test_caddy_serves_the_server_the_adapter_edits() -> None:
    config = json.loads(text("caddy.json"))
    server = config["apps"]["http"]["servers"][SERVER]
    assert server["listen"] == [f":{PROXY_LISTEN_PORT}"]
    assert server["routes"] == []
    assert config["apps"]["pki"]["certificate_authorities"]["local"]["install_trust"] is False


def test_the_admin_api_is_a_socket_never_a_tcp_port() -> None:
    listen = json.loads(text("caddy.json"))["admin"]["listen"]
    assert listen.startswith(f"unix/{SOCKET_DIR_IN_PROXY}/{ADMIN_SOCKET.name}")


def test_the_dockerfile_creates_the_user_and_the_paths() -> None:
    dockerfile = text("Dockerfile")
    assert f"--uid 1000 --groups docker,sudo {USER}" in dockerfile
    assert f"install -d -o {USER} -g {USER} {WORKSPACES}" in dockerfile
    assert f"install -d {STATE} {IMAGE_INIT_DIR}" in dockerfile
    assert f"COPY image/caddy.json {PROXY_BASE_CONFIG}" in dockerfile


def test_route_urls_resolve_and_are_trusted_in_the_container() -> None:
    dockerfile = text("Dockerfile")
    assert "libnss-myhostname" in dockerfile
    assert "hosts: files myhostname dns" in dockerfile
    assert f"NODE_EXTRA_CA_CERTS={CA_BUNDLE}" in dockerfile
    assert f"REQUESTS_CA_BUNDLE={CA_BUNDLE}" in dockerfile
    assert str(TRUSTED_CA.parent) == "/usr/local/share/ca-certificates"
    assert TRUSTED_CA.suffix == ".crt"


def test_the_tool_on_the_path_runs_the_in_container_entry_point() -> None:
    scripts = tomllib.loads((REPOSITORY / "pyproject.toml").read_text(encoding="utf-8"))
    module = scripts["project"]["scripts"]["outpost-container"].split(":")[0]
    assert f"-m {module} " in text("outpost")
    assert f"COPY image/outpost /usr/local/bin/{TOOL}" in text("Dockerfile")


def test_the_image_gets_the_in_container_side_and_nothing_else() -> None:
    dockerfile = text("Dockerfile")
    for package in IN_CONTAINER:
        assert f"COPY src/outpost/{package} /opt/outpost/lib/outpost/{package}" in dockerfile
    assert "src/outpost/launcher" not in dockerfile
    for package in IN_CONTAINER:
        for module in (REPOSITORY / "src" / "outpost" / package).rglob("*.py"):
            for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.module:
                    parts = node.module.split(".")
                    copied = parts[0] != "outpost" or len(parts) == 1 or parts[1] in IN_CONTAINER
                    assert copied, (module, node.module)
                    assert parts[0] != "yaml", module


def test_the_entrypoint_stops_the_inner_engine_then_boots() -> None:
    entrypoint = text("entrypoint.sh")
    assert "trap stop TERM INT" in entrypoint
    assert 'kill -TERM "$dockerd_pid"' in entrypoint
    assert f"{TOOL} boot" in entrypoint


def test_the_build_context_is_what_the_digest_covers() -> None:
    ignored = (REPOSITORY / ".dockerignore").read_text(encoding="utf-8").splitlines()
    allowed = {line[1:].rstrip("/") for line in ignored if line.startswith("!")}
    assert allowed == set(SOURCES)
