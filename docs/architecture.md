# Architecture

Your machine drives the host's Docker; everything else runs inside one dev container, and a browser reaches it only through the proxy's port on `127.0.0.1`.

```text
your machine                         host (local Docker, or a Linux VM over SSH)
+--------------------+               +-------------------------------------------------+
| ./outpost          | Docker API -> | dev container  outpost-<name>   (privileged)    |
|                    | (over SSH)    |   claude, gh, git, outpost tool                 |
| browser            | HTTPS ------> |   inner Docker, network `outpost`               |
|  *.dev.localhost   | :8443         |     outpost-proxy (Caddy)  -> stack containers  |
|                    | (tunnel if    |     admin API: a unix socket, never a TCP port  |
| ./outpost tunnel   |  remote)      | named volumes: home, workspaces, docker, state   |
+--------------------+               +-------------------------------------------------+
```

## What `./outpost up` does

[`Up.run`](../src/outpost/launcher/application/up.py#L65-L86), in order:

1. Checks the host's Docker answers. A remote host is reached with `DOCKER_HOST=ssh://...`, set once in [`Launcher`](../src/outpost/launcher/cli/wiring.py#L51-L147).
2. Builds the default image on the host when missing. Its tag is a digest of its sources, computed by [`CheckoutBaseImage`](../src/outpost/launcher/adapters/base_image.py#L23-L58).
3. Streams a custom image that only exists on your machine to a remote host, with `docker save | docker load`.
4. Creates the named volumes, labelled with the environment's name.
5. Compares the settings digest on the existing container with the new one, and asks before recreating; a recreation stops the container first, so its stacks stop cleanly.
6. Runs `devcontainer up` with the file [`define`](../src/outpost/domain/devcontainer.py#L231-L254) builds, through [`DevContainerCliAdapter`](../src/outpost/launcher/adapters/devcontainer_cli.py#L16-L55).
7. Checks what the container actually exposes, since features and image metadata can add mounts: a bind mount, the host's network or another published port removes it again, by [`exposure_problems`](../src/outpost/domain/exposure.py#L42-L53).
8. Waits until the boot record says ready for this start of the container.
9. Checks and copies the logins, with [`Logins`](../src/outpost/launcher/application/logins.py#L12-L53).
10. Copies the `copy` entries, replaces the init scripts, and runs them if they changed, with their output on your terminal.

## Inside the container, at every start

The image's entrypoint, `image/entrypoint.sh`, runs whoever starts the container: `./outpost up`, `docker start`, or Docker after a reboot through `--restart unless-stopped`.

1. It prepares cgroup v2 nesting and starts the inner Docker engine, which logs to `/var/log/outpost/dockerd.log`.
2. `outpost boot` runs [`Boot.run`](../src/outpost/container/application/boot.py#L54-L75): the `outpost` network and the proxy through [`CaddyContainer`](../src/outpost/container/adapters/proxy_container.py#L30-L132), every route applied again (so a changed domain takes effect), new persisted volumes handed to `dev`, then the init scripts. Whatever fails, boot ends by writing a ready record named after this start.
3. The container lives as long as the inner engine. Stopping it stops the inner engine first, which stops the stacks cleanly within the container's 60-second stop timeout.

## Proxy and certificates

- Caddy runs on the inner Docker as `outpost-proxy`, on the `outpost` network, listening on 443, with the base config `image/caddy.json`.
- Its admin API is a unix socket in `/var/lib/outpost/proxy/admin`, a folder only root and the docker group can enter; [`CaddyAdmin`](../src/outpost/container/adapters/caddy.py#L100-L174) adds and removes routes by `@id` through it. Never a TCP port: on a wildcard address Caddy skips its Host check, and every stack would reach the API.
- Caddy saves every API change and restores it at start (`--resume`). When the base config or the proxy's arguments change, the proxy is recreated and its routes are carried over.
- Caddy's internal CA issues a certificate per route name. Its root key stays in the state volume.
- `devcontainer` is a host alias of the proxy pointing at the dev container itself, for processes run outside the inner Docker.

## What persists

| Path | Volume | Holds |
| --- | --- | --- |
| `/home/dev` | `outpost-<name>-home` | Claude Code login and sessions, gh login, shell history, caches |
| `/workspaces` | `outpost-<name>-workspaces` | Repositories, worktrees, scratch |
| `/var/lib/docker` | `outpost-<name>-docker` | Inner images, stacks, their volumes |
| `/var/lib/outpost` | `outpost-<name>-state` | Proxy CA, certificates and routes; init scripts; the boot record |
| Each `persist` path | `outpost-<name>-persist-<path>` | What you list |

The volumes are built in [`volumes_for`](../src/outpost/domain/volumes.py#L57-L72). A restart keeps the whole disk; a recreation keeps the volumes; `destroy` removes both.

## Moving files

`./outpost cp` streams a tar archive through `docker exec`, as `dev`, in both directions, with nothing staged on the host: [`DockerCli.copy_in`](../src/outpost/launcher/adapters/docker_cli.py#L131-L149) and [`DockerCli.copy_out`](../src/outpost/launcher/adapters/docker_cli.py#L151-L168). Archives coming out are extracted with Python's `data` filter, which refuses absolute paths and links leaving the target.

## The image

`image/Dockerfile` builds `outpost/base` on Ubuntu 24.04: Docker Engine, the GitHub CLI, `tini`, the entrypoint, Caddy's base config, and the in-container side of the package (`domain`, `container`, `infra`), run by the system Python with the standard library only. The launcher's code is not copied, so changing it never rebuilds the image; [`CheckoutBaseImage`](../src/outpost/launcher/adapters/base_image.py#L23-L58) digests exactly what is copied.

## Code

One package, two sides on one domain:

| Package | Holds |
| --- | --- |
| `outpost.domain` | Values and rules shared by both sides: names, host, routes, volumes, devcontainer generation, layout, status |
| `outpost.launcher` | `./outpost`: `config`, `ports`, `application`, `adapters`, `cli` |
| `outpost.container` | `outpost` inside: `ports`, `application`, `adapters`, `cli` |
| `outpost.infra` | Running programs, for adapters of both sides; output pipes are read on threads so a chatty program never blocks |

Seven import contracts, from [`tool.importlinter`](../pyproject.toml#L58-L60), keep the layers pointing down and the sides apart.
