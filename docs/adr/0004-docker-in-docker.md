# 0004. Docker-in-Docker in the box

Status: accepted, 2026-11-01

## Context

Each worktree runs a full stack. Stacks must not collide with each other or with the host, and compose bind mounts must resolve to the worktrees.

## Decision

Run a Docker engine inside the box. Use the Sysbox runtime where the host has it, and privileged mode otherwise. Keep the inner engine's data on a volume.

## Consequences

Stacks are isolated per box and bind mounts resolve inside the box. Privileged mode gives the box power over the host, so it is meant for machines you own. Sysbox on WSL2 is unverified.
