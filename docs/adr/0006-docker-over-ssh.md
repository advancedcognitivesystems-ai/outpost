# 0006. Reach a remote host through Docker over SSH

Status: accepted, 2026-11-01.

## Context

A remote host could run an Outpost agent or expose Docker's API. Both add software and an open port to secure.

## Decision

Every Docker command runs on your machine with `DOCKER_HOST=ssh://user@host`, including `devcontainer up`. The browser reaches the proxy through `./outpost tunnel`, an SSH local forward of the same loopback port. Registry credentials stay on your machine: Docker sends them with each pull it asks the host to make.

## Consequences

- The host needs Docker and SSH, nothing else; SSH is its only open port.
- Each command opens an SSH session unless connection sharing (`ControlMaster`) is configured.
