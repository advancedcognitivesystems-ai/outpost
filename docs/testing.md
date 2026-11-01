# Testing

Use cases are tested through in-memory fakes of their ports; adapters are tested on the commands and files they produce; the configuration is tested against `outpost.example.yaml` itself.

## Running the checks

| What | Command |
| --- | --- |
| Everything CI runs | `uv run pre-commit run --all-files` |
| Tests | `uv run pytest` |
| Strict types | `uv run mypy` |
| Layer contracts | `uv run lint-imports` |
| Format and lint | `uv run ruff format` then `uv run ruff check` |
| Refresh line links in the docs | `uv run python -m tools.line_refs` |

Install the hooks once with `uv run pre-commit install`, so they run on every commit.

## Layout

| Folder | Covers | Style |
| --- | --- | --- |
| `tests/domain` | Names, routes, layouts | Plain values |
| `tests/config` | The loader, on the example file and on targeted breakages | Each error asserts the key path it names |
| `tests/adapters` | Shells, Docker arguments, Traefik settings, compose override, local CA, templates, sources | Fake shell answers; real `openssl` and local files where safe |
| `tests/application` | Doctor, credentials, converge, `up`, worktrees, stacks | Fakes only |
| `tests/cli` | Exit codes, usage errors, `init` | Through [`main`](../src/outpost/cli/main.py#L116-L128) |
| `tests/test_doc_references.py` | Every code link in the docs | Fails on a stale line range |

## Fakes

`tests/fakes.py` holds one fake per port. [`FakeShell`](../tests/fakes.py#L29-L96) answers by the longest matching argument prefix and records every call, stdin and written file; [`FakeEngine`](../tests/fakes.py#L100-L184) keeps containers, images and an event log, so tests can assert order, as in [`test_up_builds_then_runs_edge_box_router_then_clones`](../tests/application/test_doctor_and_environment.py#L172-L189).

## Not covered yet

Nothing here talks to a real Docker engine, SSH host or registry. Before calling v0.1 done on a host, run this by hand on WSL and on an Azure VM:

1. `outpost doctor`, then `outpost up` from an empty host, then `outpost up` again (nothing changes).
2. `outpost worktree add`, `outpost stack up`, then open each URL from the client's browser.
3. Restart the host; the edge, the box, the router and the stacks come back on their own.
4. `outpost creds sync` with each strategy, on a client with and without existing logins.
