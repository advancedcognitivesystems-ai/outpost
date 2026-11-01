# Building on Outpost

A stack is anything started on the inner Docker; it becomes reachable from your browser when it registers a route. People and agents use the same commands.

## Register a route

1. Start the stack on the inner Docker, such as `docker compose -p feat-a up -d` in a worktree.
2. Register what you want to open: `outpost route add api.feat-a feat-a-api-1:8080`.
3. [`Routes.add`](../src/outpost/container/application/routes.py#L28-L34) attaches the container to the `outpost` network when needed, then adds the route through the proxy's API.
4. `https://api.feat-a.dev.localhost:8443` answers at once, with a certificate from the proxy's CA.

A route answers 502 until its upstream listens. Routes survive restarts of the proxy and of the dev container.

## Upstreams

| Form | Reaches | Note |
| --- | --- | --- |
| `container:port` | A container on the inner Docker | Attached to `outpost` automatically; a compose recreation detaches it, so declare the network or register again |
| `alias:port` | A network alias on the `outpost` network | For compose services that join it |
| `devcontainer:port` | A process run directly in the dev container | It must listen on `0.0.0.0` |

Upstreams speak HTTP; TLS ends at the proxy. Upstreams are parsed by [`Upstream.parse`](../src/outpost/domain/routes.py#L32-L38).

## Compose pattern

```yaml
# compose.override.yaml in the worktree
services:
  api:
    networks: [default, outpost]
networks:
  outpost:
    external: true
```

## Names

- A route name is one or more DNS labels, such as `api.feat-a`, checked by [`DnsName`](../src/outpost/domain/names.py#L39-L56).
- `<service>.<worktree>` scales: `outpost route rm '*.feat-a'` removes a worktree's routes, through [`Routes.remove`](../src/outpost/container/application/routes.py#L36-L47).

## Tools and init scripts

- Tools belong in the image, through features or your Dockerfile, under `/usr/local` or `/opt`. The image's files under the home directory are copied into the home volume only when that volume is created.
- Init scripts run as root at every start, after the inner Docker and the proxy, from [`ScriptDirectories`](../src/outpost/container/adapters/init_files.py#L22-L51): the image's `/etc/outpost/init.d` first, then yours. Executable scripts run directly, others with `sh`; `OUTPOST_USER` names the user.
- Make them idempotent, and use `runuser -u dev --` for steps that must run as `dev`. A failure is recorded and reported by `up` and `status`; the container still starts.
- At a start, their output goes to the container's log (`./outpost logs`); when `up` runs changed scripts, their output is on your terminal.
- Lifecycle commands of devcontainer.json, such as `postCreateCommand`, may run before the inner Docker is ready: use init scripts for anything that needs Docker.
- Persisted paths are handed to `dev` when their volume is new and empty, so tools and agents can write there.
