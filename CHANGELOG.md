# Changelog

All notable changes to Outpost. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- A login your machine has but the container refuses is reported, and a login is offered, instead of stopping `up`.

## [0.2.0] - 2026-11-01

Outpost is now a dev container framework: one container is the entry point, locally or on a remote host. See [ADR 0001](docs/adr/0001-dev-container-framework.md).

### Added

- `./outpost` commands: `up`, `stop`, `down`, `destroy`, `status`, `shell`, `exec`, `cp`, `logs`, `ca`, `tunnel`, `config`, `doctor`.
- `outpost` inside the container: `route add|rm|ls`, `ca`, `status`, and `boot` and `init` for the entrypoint.
- The default image `outpost/base` in `image/`: inner Docker, the GitHub CLI, the `outpost` tool (standard library only), an entrypoint run at every start that stops the inner Docker cleanly, Caddy's base config with its admin API on a unix socket.
- A generated devcontainer.json, merged from your settings, run with the reference Dev Container CLI; bind mounts, published ports and the host network are refused in the settings, and checked again on the running container.
- Four named volumes and `persist`; a settings digest that makes `up` ask before recreating.
- Copies in and out as tar streams through `docker exec`.
- Claude Code and GitHub CLI logins checked in the container and copied from your machine when missing.
- Documentation: architecture, setup, configuration, stacks, testing, seven decision records.

### Removed

- Git, worktree and compose stack management, the host-side edge proxy, the isolation choice, and the per-target configuration of 0.1.0.

## [0.1.0] - 2026-11-01

### Added

- Repository hygiene and the first layered skeleton, for a design since replaced.
