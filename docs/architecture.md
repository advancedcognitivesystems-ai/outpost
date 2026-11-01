# Architecture

Every request takes the same path on WSL and on Azure: browser, edge, router, stack service. Per target, only two things change: how the client reaches the host, and where the edge's certificate comes from.

## Runtime topology

```mermaid
flowchart TB
  subgraph client[Your machine]
    browser[Browser]
    editor[VS Code or shell]
    cli[./outpost]
  end
  subgraph host[Host: WSL2 distro or Azure VM]
    edge[Edge: Traefik, TLS for *.domain]
    engine[Host Docker engine]
    subgraph box[Box: dev container]
      router[Router: Traefik, Docker labels]
      agents[Agents in tmux]
      inner[Inner Docker engine]
      stackA[Stack wt-feat-a]
      stackB[Stack wt-feat-b]
    end
    volumes[(workspaces, docker, home, exchange)]
  end
  browser -- HTTPS 443 --> edge
  edge -- HTTP, Host kept --> router
  router --> stackA
  router --> stackB
  editor -- SSH, docker exec --> agents
  cli -- SSH or local --> engine
  engine --> edge
  engine --> box
  volumes -.mounted.-> box
```

- The edge holds the only certificate and forwards every hostname under the domain to the router: one catch-all rule, written by [`edge_dynamic_config`](../src/outpost/adapters/proxy/traefik.py#L99-L129).
- The router runs inside the box against the inner engine and finds stacks from their labels. The box starts it at boot, with the lines from [`TraefikRouter.bootstrap_script`](../src/outpost/adapters/proxy/traefik.py#L158-L174).
- The CLI never talks to the box directly: it drives the host's engine and runs box commands through `docker exec`.

## New stacks go live without a reload

1. `outpost stack up <worktree>` renders a compose override for that worktree: project `wt-<worktree>`, router labels for each exposed service, the `outpost-routes` network, `restart: unless-stopped` for every service. See [`compose_override`](../src/outpost/adapters/stacks/compose.py#L67-L89).
2. The router's Docker provider sees the containers start and adds their routes.
3. The edge already forwards `*.<domain>`, and its wildcard certificate already covers the new name.

No host port is allocated per stack: every stack keeps its internal ports, and hostnames tell them apart. Route names are flat, `<service>--<worktree>.<domain>`, because a wildcard certificate covers one label; see [`plan_routes`](../src/outpost/domain/routes.py#L45-L65).

## Same implementation on WSL and Azure

| Concern | WSL (local VM) | Azure VM |
| --- | --- | --- |
| Client to host | `connection.kind: local`, Outpost runs in the distro | `connection.kind: ssh` |
| Domain | `dev.localhost`; Chromium and Firefox resolve `*.localhost` to loopback | Your domain with a wildcard DNS record |
| Edge listens on | `127.0.0.1`, reached from Windows by WSL localhost forwarding | The VPN interface, or `0.0.0.0` behind an NSG allowlist |
| Certificate | `local-ca`, trusted once with `outpost tls trust` | `acme`, Let's Encrypt wildcard through DNS-01 |
| Isolation | `privileged` | `sysbox` |

## Persistence

| What | Volume or path | Mounted at |
| --- | --- | --- |
| Clone, worktrees, build outputs | `outpost-<project>-workspaces` | `/workspaces` |
| Inner images, containers, stack volumes | `outpost-<project>-docker` | `/var/lib/docker` |
| `~/.claude`, `~/.config/gh`, NuGet cache | `outpost-<project>-home` | `/home/<user>` |
| Files shared with your machine | `<state_dir>/exchange` on the host | `/exchange` |
| Edge certificates, ACME account | `outpost-<project>-edge-data` | `/data` in the edge |

The box container is built by [`box_container`](../src/outpost/application/box.py#L57-L75). Containers are recreated only when their spec changes, by [`converge`](../src/outpost/application/containers.py#L21-L42); volumes always survive.

## Code layers

```mermaid
flowchart TB
  cli[cli: parsing, rendering, exit codes] --> application[application: use cases]
  application --> ports[ports: interfaces]
  ports --> domain[domain: pure values and rules]
  wiring[cli.wiring: composition root] --> adapters[adapters: one per kind]
  adapters -. implement .-> ports
  cli --> config[config: YAML to domain]
  config --> domain
```

- Arrows are imports, checked by the contracts in `pyproject.toml`.
- The use cases are [`Environment`](../src/outpost/application/environment.py#L33-L134), [`Doctor`](../src/outpost/application/doctor.py#L40-L69), [`CredentialSync`](../src/outpost/application/credentials.py#L26-L90), [`Worktrees`](../src/outpost/application/worktrees.py#L21-L49), [`Stacks`](../src/outpost/application/stacks.py#L12-L46) and [`BoxSession`](../src/outpost/application/session.py#L13-L21).
- The composition root is [`App`](../src/outpost/cli/wiring.py#L58-L187); it is the only module that names an adapter class.
