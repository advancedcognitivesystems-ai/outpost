# Building on Outpost

A stack is anything started on the inner Docker; it becomes reachable from your browser when it registers a route. People and agents use the same commands.

## Register a route

1. Start the stack on the inner Docker, such as `docker compose -p feat-a up -d` in a worktree.
2. Register what you want to open: `outpost route add api.feat-a feat-a-api-1:8080`.
3. [`Routes.add`](../src/outpost/container/application/routes.py#L36-L43) attaches the container to the `outpost` network when needed, and says so, then adds the route through the proxy's API.
4. `https://api.feat-a.dev.localhost:8443` answers at once, with a certificate from the proxy's CA.

A route answers 502 until its upstream listens. A name without a route fails at the TLS handshake, as `ERR_SSL_PROTOCOL_ERROR` in Chrome or error 35 in curl, because the proxy has no certificate for it: check `outpost route ls`.

## Calling a route from inside

- In the dev container, a route's URL works as in your browser, port included, so tests and agents use the URLs `outpost route ls` prints: `curl https://api.feat-a.dev.localhost:8443`.
- Every program there resolves `*.localhost` to the container, the proxy listens there on 443 and on the port in the URLs, and the container trusts the proxy's CA: [`ProxyStartup`](../src/outpost/container/application/boot.py#L37-L55) adds it to the system's list at every start, through [`SystemTrust`](../src/outpost/container/adapters/system_trust.py#L11-L22). curl, git, Python and Go read that list; the image points Node and Python's requests at it with `NODE_EXTRA_CA_CERTS` and `REQUESTS_CA_BUNDLE`.
- A browser started in the container, such as Playwright's Chromium, keeps its own list: add the root with `mkdir -p ~/.pki/nssdb && certutil -d sql:$HOME/.pki/nssdb -A -t C,, -n outpost -i /usr/local/share/ca-certificates/outpost-ca.crt`, after `sudo apt-get install libnss3-tools`, or set Playwright's `ignoreHTTPSErrors`.
- Stacks cannot use these names: in a container, `*.localhost` is that container itself. Stacks call each other by service or container name over HTTP, such as `http://api:8080`, on a network they share.

## Restarts

- Routes and the CA survive restarts of the proxy and of the dev container, and recreations.
- Stacks come back after a restart of the dev container or the host only with a restart policy, such as `restart: unless-stopped` in compose. Processes run directly in the dev container do not come back: start them again, or from an init script.
- A proxy stopped or removed, as by `docker rm -f $(docker ps -aq)`, comes back with its routes through `sudo outpost proxy start`, `./outpost up`, or the next start of the dev container.

## Upstreams

| Form | Reaches | Note |
| --- | --- | --- |
| `container:port` | A container on the inner Docker | Attached to `outpost` automatically; a compose recreation detaches it, so declare the network or register again |
| `alias:port` | A network alias on the `outpost` network | For compose services that join it |
| `devcontainer:port` | A process run directly in the dev container | It must listen on `0.0.0.0` |

Upstreams speak HTTP, WebSockets included; TLS ends at the proxy, which speaks HTTP/2 and HTTP/1.1 to the browser. Upstreams are parsed by [`Upstream.parse`](../src/outpost/domain/routes.py#L32-L38).

## Compose pattern

```yaml
# compose.override.yaml in the worktree
services:
  api:
    restart: unless-stopped
    networks: [default, outpost]
networks:
  outpost:
    external: true
```

## Names

- A route name is one or more DNS labels, such as `api.feat-a`, checked by [`DnsName`](../src/outpost/domain/names.py#L39-L56).
- `<service>.<worktree>` scales: `outpost route rm '*.feat-a'` removes a worktree's routes, through [`Routes.remove`](../src/outpost/container/application/routes.py#L45-L56).

## Tools and init scripts

- Tools belong in the image, through features or your Dockerfile, under `/usr/local` or `/opt`. The image's files under the home directory are copied into the home volume only when that volume is created.
- Init scripts run as root at every start, after the inner Docker and the proxy, from [`ScriptDirectories`](../src/outpost/container/adapters/init_files.py#L22-L51): the image's `/etc/outpost/init.d` first, then yours. Executable scripts run directly, others with `sh`; `OUTPOST_USER` names the user.
- Make them idempotent, and use `runuser -u dev --` for steps that must run as `dev`. A failure is recorded and reported by `up` and `status`; the container still starts.
- At a start, their output goes to the container's log (`./outpost logs`); when `up` runs changed scripts, their output is on your terminal.
- Lifecycle commands of devcontainer.json, such as `postCreateCommand`, may run before the inner Docker is ready: use init scripts for anything that needs Docker.
- Persisted paths are handed to `dev` when their volume is new and empty, so tools and agents can write there.
