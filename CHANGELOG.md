# Changelog

All notable changes to Outpost. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
