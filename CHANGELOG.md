# Changelog

All notable changes to Outpost. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `outpost proxy start` starts the proxy, or creates it again, with its routes; `./outpost up` does it when the proxy was stopped or removed since the container started.
- `outpost route add` says when it attached a container to the `outpost` network, since a container created again leaves it.
- A route's URL works in the dev container too, port included: every program resolves `*.localhost` to the container, the proxy is also published there on the port in the URLs, and the proxy's CA is added to the container's CA list at every start, which Node and Python's requests are pointed at.
- Releases: a `vX.Y.Z` tag on `main` publishes a GitHub Release with the version's changelog section once the checks pass; `python -m tools.release prepare X.Y.Z` writes the release commit.

### Removed

- `outpost --version` inside the container: the version is now written only in `pyproject.toml`, and the image no longer carries it, so a release rebuilds the image only when its sources changed. `./outpost --version` gives it.

### Fixed

- A login your machine has but the container refuses is reported, and a login is offered, instead of stopping `up`.
- `./outpost status` reports a proxy that is not running instead of failing.

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
