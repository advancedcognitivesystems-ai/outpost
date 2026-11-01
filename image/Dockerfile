# outpost/base: the default image of an Outpost dev container.
# `./outpost up` builds it on the host from this checkout, tagged with a digest of its sources.
# Derive your own image from it: `ARG OUTPOST_BASE` then `FROM ${OUTPOST_BASE}`.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      bash-completion ca-certificates curl git gnupg iptables less openssh-client \
      python3 sudo tar tini unzip; \
    rm -rf /var/lib/apt/lists/*

# Docker Engine, for the inner Docker that runs the proxy and your stacks.
RUN set -eux; \
    install -m 0755 -d /etc/apt/keyrings; \
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc; \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable" \
      > /etc/apt/sources.list.d/docker.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin; \
    rm -rf /var/lib/apt/lists/*

# GitHub CLI, from its apt repository.
RUN set -eux; \
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      -o /etc/apt/keyrings/githubcli-archive-keyring.gpg; \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends gh; \
    rm -rf /var/lib/apt/lists/*

# The user `dev` (uid 1000) uses the inner Docker and sudo. Ubuntu's own uid 1000 user goes first.
# /workspaces belongs to dev here, so its empty volume takes that owner when first mounted.
RUN set -eux; \
    if id ubuntu >/dev/null 2>&1; then userdel --remove ubuntu; fi; \
    useradd --create-home --shell /bin/bash --uid 1000 --groups docker,sudo dev; \
    echo "dev ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/outpost; \
    chmod 0440 /etc/sudoers.d/outpost; \
    install -d -o dev -g dev /workspaces; \
    install -d /var/lib/outpost /etc/outpost/init.d /var/log/outpost

# The `outpost` tool: the in-container side of the package, standard library only, run by the
# system Python. The launcher's code is not copied, so launcher changes never rebuild the image.
COPY src/outpost/__init__.py /opt/outpost/lib/outpost/__init__.py
COPY src/outpost/domain /opt/outpost/lib/outpost/domain
COPY src/outpost/container /opt/outpost/lib/outpost/container
COPY src/outpost/infra /opt/outpost/lib/outpost/infra
COPY image/outpost /usr/local/bin/outpost
RUN chmod 0755 /usr/local/bin/outpost

COPY image/caddy.json /etc/outpost/caddy.json
COPY image/entrypoint.sh /usr/local/lib/outpost/entrypoint
RUN chmod 0755 /usr/local/lib/outpost/entrypoint

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/lib/outpost/entrypoint"]
