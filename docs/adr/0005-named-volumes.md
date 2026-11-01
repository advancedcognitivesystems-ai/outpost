# 0005. Named volumes for everything that must survive

Status: accepted, 2026-11-01

## Context

Worktrees hold about 4 GB of build output each; inner images take time to rebuild; credentials must survive restarts.

## Decision

Keep workspaces, inner Docker data and the box home in named volumes. Use one host directory, for exchange with the client, because sync tools need a host path.

## Consequences

The same behaviour on WSL and Azure, and a box rebuild loses nothing. Volumes are removed only on request (`destroy --volumes`).
