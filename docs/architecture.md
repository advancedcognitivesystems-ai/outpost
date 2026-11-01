# Architecture

Your machine drives the host's Docker; everything else runs inside one dev container, and a browser reaches it only through the proxy's port on `127.0.0.1`.

```text
your machine                         host (local Docker, or a Linux VM over SSH)
+--------------------+               +-------------------------------------------------+
| ./outpost          | Docker API -> | dev container  outpost-<name>   (privileged)    |
|                    | (over SSH)    |   claude, gh, git, outpost tool                 |
| browser            | HTTPS ------> |   inner Docker, network `outpost`               |
|  *.dev.localhost   | :8443         |     outpost-proxy (Caddy)  -> stack containers  |
|                    | (tunnel if    |                                                 |
| ./outpost tunnel   |  remote)      | named volumes: home, workspaces, docker, state   |
+--------------------+               +-------------------------------------------------+
```

## What `./outpost up` does

[`Up.run`](../src/outpost/launcher/application/up.py#L63-L83), in order:

1. Checks the host's Docker answers. A remote host is reached with `DOCKER_HOST=ssh://...`, set once in [`Launcher`](../src/outpost/launcher/cli/wiring.py#L51-L146).
2. Builds the default image on the host when missing. Its tag is a digest of its sources, computed by [`CheckoutBaseImage`](../src/outpost/launcher/adapters/base_image.py#L17-L52).
3. Streams a custom image that only exists on your machine to a remote host, with `docker save | docker load`.
4. Creates the named volumes, labelled with the environment's name.
5. Compares the settings digest on the existing container with the new one, and asks before recreating.
6. Runs `devcontainer up` with the file [`define`](../src/outpost/domain/devcontainer.py#L218-L240) builds, through [`DevContainerCliAdapter`](../src/outpost/launcher/adapters/devcontainer_cli.py#L17-L56).
7. Waits until the container's boot record says ready.
8. Checks and copies the logins, with [`Logins`](../src/outpost/launcher/application/logins.py#L12-L53).
9. Copies the `copy` entries, replaces the init scripts, and runs them if they changed.

## Inside the container, at every start

The image's entrypoint, `image/entrypoint.sh`, runs whoever starts the container: `./outpost up`, `docker start`, or Docker after a reboot through `--restart unless-stopped`.

1. It clears the last boot record, prepares cgroup v2 nesting, and starts the inner Docker engine.
2. `outpost boot` runs [`Boot.run`](../src/outpost/container/application/boot.py#L41-L58): the `outpost` network and the proxy through [`CaddyContainer`](../src/outpost/container/adapters/proxy_container.py#L28-L109), then the init scripts, then the record says ready.
3. The container lives as long as the inner engine.

## Proxy and certificates

- Caddy runs on the inner Docker as `outpost-proxy`, on the `outpost` network, listening on 443, with the base config `image/caddy.json`.
- Its admin API is published on the dev container's `127.0.0.1:2019` only; [`CaddyAdmin`](../src/outpost/container/adapters/caddy.py#L83-L155) adds and removes routes by `@id`.
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

The volumes are built in [`volumes_for`](../src/outpost/domain/volumes.py#L50-L65). A restart keeps the whole disk; a recreation keeps the volumes; `destroy` removes both.

## Moving files

`./outpost cp` streams a tar archive through `docker exec`, as `dev`, in both directions, with nothing staged on the host: [`DockerCli.copy_in`](../src/outpost/launcher/adapters/docker_cli.py#L114-L123) and [`DockerCli.copy_out`](../src/outpost/launcher/adapters/docker_cli.py#L125-L142). Archives coming out are extracted with Python's `data` filter, which refuses absolute paths and links leaving the target.

## Code

One package, two sides on one domain:

| Package | Holds |
| --- | --- |
| `outpost.domain` | Values and rules shared by both sides: names, host, routes, volumes, devcontainer generation, layout, status |
| `outpost.launcher` | `./outpost`: `config`, `ports`, `application`, `adapters`, `cli` |
| `outpost.container` | `outpost` inside: `ports`, `application`, `adapters`, `cli` |
| `outpost.infra` | Running programs, for adapters of both sides |

Seven import contracts, from [`tool.importlinter`](../pyproject.toml#L58-L60), keep the layers pointing down and the sides apart.
