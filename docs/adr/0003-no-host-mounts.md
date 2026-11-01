# 0003. No mounts between the host and the dev container

Status: accepted, 2026-11-01.

## Context

A bind mount behaves differently on a local and on a remote host: locally it is your disk, remotely it is the VM's disk, and a sync tool in between brings conflicts, latency and partial states. Mounted host folders also leak host state into the container and container output onto the host.

## Decision

Files cross only by copy: `./outpost cp` in both directions, and the `copy` entries of `outpost.yaml` on every `up`. A copy is a tar stream through `docker exec`, as the container's user, identical locally and remotely, with nothing staged on the host. Bind mounts in the settings (`mounts`, `workspaceMount`, `-v`, `--volume`, `--mount`, `--volumes-from` in `runArgs`) are refused, and `up` checks the running container as well, since features and image metadata can add mounts of their own.

## Consequences

- No live editing of your machine's files from the container: a copy is a snapshot.
- Work happens inside the container: its shell, VS Code attached to it, agents.
- The same commands work unchanged when the host moves from local to remote.
