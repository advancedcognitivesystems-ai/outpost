# 0004. If it is not in the image, it is in a volume

Status: accepted, 2026-11-01.

## Context

A dev container is recreated when its image or settings change. Logins, Claude Code sessions, repositories, inner images and the proxy's CA must survive that; tools must not drift from the image.

## Decision

Four named volumes always exist: `/home/dev`, `/workspaces`, `/var/lib/docker` and `/var/lib/outpost`; `persist` adds more. Tools are installed by the image under `/usr/local` or `/opt`. The container restarts with `--restart unless-stopped`, so a restart keeps its whole disk; `up` asks before recreating, which keeps only the volumes.

## Consequences

- Manual installs outside the volumes are lost on recreation; their place is the image, a feature or an init script.
- Files the image puts in the home directory reach the home volume only when it is created.
- `destroy` is the only command that removes volumes, after the environment's name is typed.
- Every stop is graceful: the container has a 60-second stop timeout, its entrypoint stops the inner Docker on SIGTERM, and Outpost stops before it removes.
