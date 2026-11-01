# 0001. Outpost is a framework around one dev container

Status: accepted, 2026-11-01. Supersedes the first design, which managed git, worktrees and compose stacks from the launcher.

## Context

The work happens in a full dev environment: a 15 GB live application, two dozen services, several worktrees, edited mostly by agents. How repositories, worktrees and stacks are organised differs per project and changes often.

## Decision

Outpost provides one dev container and conventions, nothing more: a default image, a launcher that creates and reaches the container locally or on a remote host, a proxy that stacks register with, copied logins, and copies in and out. Git, worktrees and stack orchestration are run inside the container by people and agents.

## Consequences

- The launcher stays small and stable; project-specific logic lives in the project, in init scripts or in the image.
- Stacks must register their own routes (see [docs/stacks.md](../stacks.md)).
