"""The image in `image/` agrees with the layout and the adapters that rely on it."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from outpost.container.adapters.caddy import SERVER
from outpost.domain.layout import (
    ADMIN_PORT,
    BOOT_RECORD,
    IMAGE_INIT_DIR,
    PROXY_BASE_CONFIG,
    PROXY_LISTEN_PORT,
    STATE,
    TOOL,
    USER,
    WORKSPACES,
)
from outpost.launcher.adapters.base_image import SOURCES

REPOSITORY = Path(__file__).resolve().parents[2]
IMAGE = REPOSITORY / "image"


def text(name: str) -> str:
    return (IMAGE / name).read_text(encoding="utf-8")


def test_caddy_serves_the_server_the_adapter_edits() -> None:
    config = json.loads(text("caddy.json"))
    server = config["apps"]["http"]["servers"][SERVER]
    assert server["listen"] == [f":{PROXY_LISTEN_PORT}"]
    assert server["routes"] == []
    assert config["admin"]["listen"].endswith(f":{ADMIN_PORT}")
    assert f"127.0.0.1:{ADMIN_PORT}" in config["admin"]["origins"]
    assert config["apps"]["pki"]["certificate_authorities"]["local"]["install_trust"] is False


def test_the_dockerfile_creates_the_user_and_the_paths() -> None:
    dockerfile = text("Dockerfile")
    assert f"--uid 1000 --groups docker,sudo {USER}" in dockerfile
    assert f"install -d -o {USER} -g {USER} {WORKSPACES}" in dockerfile
    assert f"install -d {STATE} {IMAGE_INIT_DIR}" in dockerfile
    assert f"COPY image/caddy.json {PROXY_BASE_CONFIG}" in dockerfile


def test_the_tool_on_the_path_is_the_in_container_entry_point() -> None:
    scripts = tomllib.loads((REPOSITORY / "pyproject.toml").read_text(encoding="utf-8"))
    entry = scripts["project"]["scripts"]["outpost-container"]
    assert entry == "outpost.container.cli.main:main"
    assert f"/opt/outpost/venv/bin/outpost-container /usr/local/bin/{TOOL}" in text("Dockerfile")


def test_the_entrypoint_resets_the_record_then_boots() -> None:
    entrypoint = text("entrypoint.sh")
    assert f"rm -f {BOOT_RECORD}" in entrypoint
    assert f"{TOOL} boot" in entrypoint
    assert (IMAGE / "entrypoint.sh").stat().st_mode & 0o111 or "chmod 0755" in text("Dockerfile")


def test_the_build_context_is_what_the_digest_covers() -> None:
    ignored = (REPOSITORY / ".dockerignore").read_text(encoding="utf-8").splitlines()
    allowed = {line[1:].rstrip("/") for line in ignored if line.startswith("!")}
    assert allowed == set(SOURCES)
