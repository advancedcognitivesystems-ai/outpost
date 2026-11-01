"""Where things live in an Outpost container.

This is the contract between the launcher, the in-container tool and the image in `image/`;
`tests/image` checks that the image's files agree with it.
"""

from __future__ import annotations

from pathlib import PurePosixPath

USER = "dev"
HOME = PurePosixPath("/home") / USER
WORKSPACES = PurePosixPath("/workspaces")
DOCKER_DATA = PurePosixPath("/var/lib/docker")
STATE = PurePosixPath("/var/lib/outpost")

USER_INIT_DIR = STATE / "init.d"
IMAGE_INIT_DIR = PurePosixPath("/etc/outpost/init.d")
BOOT_RECORD = STATE / "boot.json"
PROXY_STATE = STATE / "proxy"
PROXY_BASE_CONFIG = PurePosixPath("/etc/outpost/caddy.json")

TOOL = "outpost"
NETWORK = "outpost"
PROXY_CONTAINER = "outpost-proxy"
PROXY_LISTEN_PORT = 443
ADMIN_PORT = 2019

ENV_NAME = "OUTPOST_NAME"
ENV_DOMAIN = "OUTPOST_DOMAIN"
ENV_PORT = "OUTPOST_PORT"

ENVIRONMENT_LABEL = "outpost.environment"
SETTINGS_LABEL = "outpost.settings"

DEFAULT_NAME = "main"
DEFAULT_DOMAIN = "dev.localhost"
DEFAULT_PORT = 8443
