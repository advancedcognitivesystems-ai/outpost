# Changelog

All notable changes to Outpost. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- The box user owns `/workspaces`, so cloning and stack files work as that user.
- `strategy: skip` warns in `doctor` instead of blocking `up`.
- The example repository URL uses HTTPS, which git in the box can use through gh.
- The box's init script prepares cgroup v2 nesting and clears stale pid files before starting the inner engine.
- Worktrees reuse an existing local branch, track a remote one, or start a new branch without upstream; nothing is reset.
- Stacks keep their own restart policies and networks; the box replays `stack up` at start instead.
- The edge mounts only the leaf certificate, never the local CA key; keys are created with a private umask.
- DNS-01 credentials reach the edge as files (`<NAME>_FILE`), never in its environment.
- Claude Code's login is read from the JSON of `claude auth status` and must be the claude.ai login.
- Commands run without the terminal's stdin unless given one.

### Changed

- Adapters declare the client programs they run; `doctor` checks exactly those.
- The router runs on the box's inner engine and is started by `up`, through the same engine adapter as everything else.
- Domain rules for user names, variable names and state paths moved from the loader to the domain.

## [0.1.0] - 2026-11-01

### Added

- Repository hygiene: uv project, ruff, strict mypy, pytest, import contracts, pre-commit, CI, LF endings.
- Layered skeleton: domain, ports, application, adapters, config loader, CLI with a composition root.
- `outpost.yaml` with targets, validated with key paths; `outpost.example.yaml` for WSL and Azure.
- Commands: `init`, `config validate|show`, `doctor`, `up`, `down`, `status`, `shell`, `worktree add|ls|rm`, `stack up|down|ls|urls|logs`, `creds status|sync`, `tls trust`.
- Adapters: local, SSH and container shells; Docker CLI engine; Traefik edge and router; local CA, ACME DNS-01 and plain HTTP; registry, ACR and client image supply; Claude Code and GitHub credentials; compose stacks; git worktrees.
- Documentation: architecture, configuration, extending, testing, eight decision records; code links checked by the tests.

### Not built yet

- `--dry-run`, `destroy`, `stack forward`, `tls status`.
- Nothing has run against a real host yet; see docs/testing.md for the manual checklist.
