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

`tests/fakes.py` holds one fake per port and a [`FakeRunner`](../tests/fakes.py#L48-L114) answering by the longest matching argument prefix. Launcher fakes share an event log, so a test can assert the order of effects, as in [`test_a_first_up_builds_then_creates_then_logs_in_then_inits`](../tests/launcher/test_up.py#L69-L93).

## Not covered yet

No automated test talks to a real Docker engine, SSH host, registry or Caddy. Before calling a version done, run this by hand on a local host and on a remote VM:

1. `./outpost doctor`, then `./outpost up` from nothing, then `./outpost up` again: nothing changes.
2. `./outpost shell`; `claude` is logged in with the claude.ai login and lists your claude.ai connectors; `gh auth status` succeeds.
3. In the container, `docker run -d --name hello traefik/whoami`, then `outpost route add hello hello:80`; open the URL from your browser, after `./outpost ca` and, remotely, `./outpost tunnel`.
4. `./outpost cp` in and out, with a file and a folder.
5. Restart the host: the container, the proxy, the route and the stack come back on their own; a database in a stack was stopped cleanly (its log shows a normal shutdown).
6. Change `devcontainer` in `outpost.yaml`, run `./outpost up`, accept the recreation: logins, routes and `/workspaces` are still there.
7. Add the feature `ghcr.io/devcontainers/features/docker-outside-of-docker:1`: `up` removes the container, keeps the volumes, and names the host mount.

Last run on 2026-11-01, on a local Linux host (Docker 29.9, cgroup v1): items 1, 3, 4, 6 and 7 passed, and a stop took 2 s with the inner engine shutting down cleanly. Not yet run: real Claude Code and GitHub logins (item 2), a host reboot (item 5), a remote host.
