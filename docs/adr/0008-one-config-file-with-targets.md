# 0008. One configuration file with targets

Status: accepted, 2026-11-01

## Context

The same project runs on a WSL distro and on an Azure VM. Most settings (project, box, stacks, credentials) are shared.

## Decision

Use one `outpost.yaml` with a `targets` map for what differs: connection, host, edge and an optional image override. `--target` or `default_target` picks one.

## Consequences

Shared settings are written once. A target can override the image but not the stacks or credentials.
