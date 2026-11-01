# 0005. Caddy on the inner Docker, routes through its admin API

Status: accepted, 2026-11-01. Supersedes the first design's two Traefik proxies, one on the host.

## Context

Stacks start and stop at run time, from inside the container, under names nobody knows in advance. Each needs an HTTPS URL with a certificate the browser trusts, without reloading the others, locally and remotely.

## Decision

Caddy runs as a container of the inner Docker, on the `outpost` network. `outpost route add NAME UPSTREAM` adds a route object through Caddy's admin API, addressed by its `@id`, and attaches the upstream container to the network. Caddy's internal CA issues a certificate per name; you trust its root once. Caddy saves API changes and restores them with `--resume`. The admin API listens on the dev container's loopback only, with explicit `origins`.

## Consequences

- One port is published, on the host's `127.0.0.1`; nothing listens publicly.
- A trusted root can sign any name: its key never leaves the state volume.
- A process run directly in the dev container is reached as `devcontainer:<port>` and must listen on all interfaces.
