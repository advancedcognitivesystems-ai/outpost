# Testing

Use cases are tested through in-memory fakes of their ports; adapters are tested on the commands they build or against local stand-ins; the image is tested for agreement with the code.

## Running the checks

| What | Command |
| --- | --- |
| Everything CI runs | `uv run pre-commit run --all-files` |
| Tests | `uv run pytest` |
| Strict types | `uv run mypy` |
| Import contracts | `uv run lint-imports` |
| Format and lint | `uv run ruff format` then `uv run ruff check` |
| Refresh line links in the docs | `uv run python -m tools.line_refs` |

## Layout

| Folder | Covers | Style |
| --- | --- | --- |
| `tests/domain` | Names, hosts, routes, volumes, copies, status, devcontainer generation | Plain values; every refusal names its key |
| `tests/launcher` | Configuration, `up`, logins, copies, lifecycle, access, doctor, adapters, CLI | Fakes for use cases; `FakeRunner` and real files for adapters |
| `tests/container` | Routes, boot, init, status, the Caddy client, the proxy's container, scripts, CLI | Fakes; a local stand-in of Caddy's API |
| `tests/infra` | The real runner on real processes: large outputs, programs that cannot start | Real subprocesses |
| `tests/image` | `image/` agrees with the layout, the Caddy adapter and the digest | Reads the files |
| `tests/test_doc_references.py` | Every code link in the docs | Fails on a stale line range |

## Fakes

`tests/fakes.py` holds one fake per port and a [`FakeRunner`](../tests/fakes.py#L48-L114) answering by the longest matching argument prefix. Launcher fakes share an event log, so a test can assert the order of effects, as in [`test_a_first_up_builds_then_creates_then_logs_in_then_inits`](../tests/launcher/test_up.py#L70-L94).

## Not covered yet

No automated test talks to a real Docker engine, SSH host, registry or Caddy. Before a [release](../CONTRIBUTING.md#releases), run this by hand on a local host and on a remote VM:

1. `./outpost doctor`, then `./outpost up` from nothing, then `./outpost up` again: nothing changes.
2. `./outpost shell`; `claude` is logged in with the claude.ai login and lists your claude.ai connectors; `gh auth status` succeeds.
3. In the container, `docker run -d --restart unless-stopped --name hello traefik/whoami`, then `outpost route add hello hello:80`; open the URL from your browser, after `./outpost ca` and, remotely, `./outpost tunnel`. Then `docker rm -f outpost-proxy`: `./outpost status` says the proxy is not running, and `./outpost up` brings it back with the route.
4. `./outpost cp` in and out, with a file and a folder.
5. Restart the host: the container, the proxy, the route and the stack, with its restart policy, come back on their own; a database in a stack was stopped cleanly (its log shows a normal shutdown).
6. Change `devcontainer` in `outpost.yaml`, run `./outpost up`, accept the recreation: logins, routes and `/workspaces` are still there.
7. Add the feature `ghcr.io/devcontainers/features/docker-outside-of-docker:1`: `up` removes the container, keeps the volumes, and names the host mount.

Last run on 2026-11-01, on a local Linux host (Docker 29.9, cgroup v1): items 1, 3, 4, 6 and 7 passed, and a stop took 2 s with the inner engine shutting down cleanly. Not yet run: real Claude Code and GitHub logins (item 2), a host reboot (item 5), a remote host.

The proxy was also checked on its own, from the host:

- Chromium opens a route after the root is added with the `certutil` command `./outpost ca` prints, and refuses it before (`ERR_CERT_AUTHORITY_INVALID`); TLS 1.3, HTTP/2, a WebSocket from the page.
- `openssl s_client` verifies root, intermediate and a leaf naming only the route; curl verifies with `--cacert`, never `-k`.
- Compose services with the network declared, attached containers, `devcontainer:` upstreams, 502 for a closed upstream, `route rm` with patterns.
- Only port 443 listens in the proxy; a stack on the `outpost` network cannot reach the API, a user outside the docker group is refused it.
- Routes and the CA's fingerprint survive a restart of the proxy, its removal, a restart of the dev container, a recreation with a new domain and port; `destroy` makes a new CA.
- In the dev container, as `dev`, curl, Python and Node open a route's URL as `outpost route ls` prints it, port included, with no option, also after a restart; Playwright's Chromium does after the `certutil` command in [stacks](stacks.md#calling-a-route-from-inside); from a stack, the same name reaches the stack itself.
