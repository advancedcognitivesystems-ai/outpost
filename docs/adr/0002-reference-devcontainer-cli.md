# 0002. Build and start with the reference Dev Container CLI

Status: accepted, 2026-11-01.

## Context

People want to extend the container the standard way: devcontainer.json features such as Claude Code's, lifecycle commands, a Dockerfile. Re-implementing feature installation and image extension would be a large, fragile copy of the specification.

## Decision

Outpost writes a devcontainer.json and runs `devcontainer up` from the reference CLI, on the host's Docker. The image keeps its own entrypoint (`overrideCommand: false`), and the workspace is a volume (`workspaceMount`), so the CLI adds no bind mount. `--id-label outpost.environment=<name>` finds the container again from any folder or machine.

## Consequences

- Your machine needs Node.js and `@devcontainers/cli`.
- Features and lifecycle commands behave as in VS Code and Codespaces; VS Code can attach to the running container.
- Local features are refused: the CLI only accepts them beside the devcontainer.json it runs, and that file is generated under `.outpost/`.
