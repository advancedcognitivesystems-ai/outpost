"""Where things live in an Outpost container.

This is the contract between the launcher, the in-container tool and the image in `image/`;
`tests/image` checks that the image's files agree with it.
"""

from __future__ import annotations

from pathlib import PurePosixPath

USER = "dev"
ROOT_USER = "root"
HOME = PurePosixPath("/home") / USER
WORKSPACES = PurePosixPath("/workspaces")
DOCKER_DATA = PurePosixPath("/var/lib/docker")
STATE = PurePosixPath("/var/lib/outpost")

USER_INIT_DIR = STATE / "init.d"
IMAGE_INIT_DIR = PurePosixPath("/etc/outpost/init.d")
BOOT_RECORD = STATE / "boot.json"
PROXY_STATE = STATE / "proxy"
PROXY_BASE_CONFIG = PurePosixPath("/etc/outpost/caddy.json")
ADMIN_SOCKET = PROXY_STATE / "admin" / "admin.sock"
"""The proxy's admin API: a unix socket, reachable from the dev container only."""
TRUSTED_CA = PurePosixPath("/usr/local/share/ca-certificates/outpost-ca.crt")
"""The proxy's root, added to the container's own CA list at every start."""
CA_BUNDLE = PurePosixPath("/etc/ssl/certs/ca-certificates.crt")
"""The container's CA list, which the image points Node and Python's requests at."""

TOOL = "outpost"
NETWORK = "outpost"
PROXY_CONTAINER = "outpost-proxy"
PROXY_LISTEN_PORT = 443
STOP_TIMEOUT_SECONDS = 60
"""Time the inner Docker gets to stop the stacks when the container stops."""

ENV_NAME = "OUTPOST_NAME"
ENV_DOMAIN = "OUTPOST_DOMAIN"
ENV_PORT = "OUTPOST_PORT"
ENV_PERSIST = "OUTPOST_PERSIST"

ENVIRONMENT_LABEL = "outpost.environment"
SETTINGS_LABEL = "outpost.settings"

DEFAULT_NAME = "main"
DEFAULT_DOMAIN = "dev.localhost"
DEFAULT_PORT = 8443
