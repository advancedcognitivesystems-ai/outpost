# Contributing to Outpost

This guide points to files and line ranges instead of repeating code. Every `[symbol](file#lines)` link below is kept current by [`refresh`](tools/line_refs.py#L90-L110) and checked by [`test_reference_is_current`](tests/test_doc_references.py#L17-L24); when a link goes stale, the tests say how to refresh it.

## Before you start

- Read [docs/architecture.md](docs/architecture.md): what runs where, and the code's two sides on one domain.
- The layering is enforced: the import contracts start at [`tool.importlinter`](pyproject.toml#L58-L60) and break the build when a module imports the wrong way.
- Decisions that shaped the code are in [docs/adr/](docs/adr/). A change that reverses one adds a new ADR.

## Working setup

- Python and the tools come from uv; the development tools are listed at [`dependency-groups`](pyproject.toml#L13-L21).
- The checks are the hooks in [`repo: local`](.pre-commit-config.yaml#L14-L43): format, lint, strict types, import contracts, tests. CI runs exactly these hooks, see [`checks`](.github/workflows/ci.yml#L9-L17).
- Commands, fakes and the manual checklist are in [docs/testing.md](docs/testing.md).

## Where a change goes

| You want to | Start here | Then |
| --- | --- | --- |
| Add a key to `outpost.yaml` | The value it becomes, in [`Environment`](src/outpost/domain/environment.py#L30-L72) | Read it in [`parse`](src/outpost/launcher/config/loader.py#L47-L71), add it to `outpost.example.yaml` and to [docs/configuration.md](docs/configuration.md) |
| Change what devcontainer.json Outpost writes | [`define`](src/outpost/domain/devcontainer.py#L218-L240) and the owned keys in [`OWNED_KEYS`](src/outpost/domain/devcontainer.py#L43-L57) | Its tests in `tests/domain/test_devcontainer.py`; the doc table in [docs/configuration.md](docs/configuration.md) |
| Change a step of `./outpost up` | [`Up.run`](src/outpost/launcher/application/up.py#L63-L83) | The order test [`test_a_first_up_builds_then_creates_then_logs_in_then_inits`](tests/launcher/test_up.py#L64-L88) |
| Add a launcher command | The parser in [`build_parser`](src/outpost/launcher/cli/main.py#L23-L60) | A handler in `src/outpost/launcher/cli/commands.py`, a use case in `src/outpost/launcher/application/`, its adapters from [`Launcher`](src/outpost/launcher/cli/wiring.py#L51-L146) |
| Add an in-container command | The parser in [`build_parser`](src/outpost/container/cli/main.py#L82-L111) | A use case in `src/outpost/container/application/`, its adapters from [`Tool`](src/outpost/container/cli/wiring.py#L21-L57) |
| Change how routes reach the proxy | [`Routes.add`](src/outpost/container/application/routes.py#L28-L34) | The Caddy objects in [`caddy_route`](src/outpost/container/adapters/caddy.py#L31-L37); the stand-in API in `tests/container/test_adapters.py` |
| Change the proxy itself | `image/caddy.json` and [`CaddyContainer`](src/outpost/container/adapters/proxy_container.py#L28-L109) | A changed config recreates the proxy and carries routes over in [`CaddyContainer._carry_routes_over`](src/outpost/container/adapters/proxy_container.py#L64-L73) |
| Change what the image contains | `image/Dockerfile` | Paths it shares with the code live in [domain/layout.py](src/outpost/domain/layout.py), checked by `tests/image/test_image.py` |
| Carry another login | [`Tool`](src/outpost/domain/credentials.py#L9-L11) | A source and a login in [`login_source`](src/outpost/launcher/adapters/logins.py#L136-L149) and [`tool_login`](src/outpost/launcher/adapters/logins.py#L152-L157) |
| Add a port | A protocol in the side's `ports/` package | Its fake in `tests/fakes.py` next to [`FakeDocker`](tests/fakes.py#L119-L212), its adapter built in the side's `cli/wiring.py` |

## Rules the review checks

- **Layers.** The domain imports nothing from Outpost and does no I/O. Use cases see the domain and their ports. Adapters implement ports and never call use cases. Only each side's `cli/wiring.py` builds adapters. The launcher and the in-container tool never import each other.
- **One place per decision.** What Outpost refuses in devcontainer.json is decided once, in [`DevContainerSettings.parse`](src/outpost/domain/devcontainer.py#L86-L103); where things live in the container is decided once, in [domain/layout.py](src/outpost/domain/layout.py).
- **Domain types in signatures.** Pass [`EnvironmentName`](src/outpost/domain/names.py#L18-L35), [`DnsName`](src/outpost/domain/names.py#L39-L63), [`Upstream`](src/outpost/domain/routes.py#L20-L45) or `ImageRef`, not strings; a value is checked once, when it is built.
- **Errors.** Raise the errors of [`OutpostError`](src/outpost/domain/errors.py#L8-L9)'s module; only each side's `cli/main.py` turns them into messages and exit codes.
- **Processes.** Every program runs through a [`Runner`](src/outpost/infra/process.py#L19-L42), so adapters are tested with [`FakeRunner`](tests/fakes.py#L47-L113).
- **Secrets.** Secrets travel as [`Secret`](src/outpost/domain/secrets.py#L8-L28), through stdin into files with mode 0600, never through arguments, environment listings or logs.
- **No mounts.** Nothing Outpost writes may bind-mount a host path into the dev container; files cross with [`Transfers`](src/outpost/launcher/application/transfers.py#L17-L61).

## Tests

- Every port has an in-memory fake in `tests/fakes.py`; use cases are tested only through them, and the fakes share an event log so a test can assert the order of effects.
- Adapters are tested on the commands they build, as in [`test_every_docker_command_carries_the_host`](tests/launcher/test_adapters.py#L47-L51), or against a local stand-in, as in [`CaddyStandIn`](tests/container/test_adapters.py#L34-L96).
- Strategy, layout and the manual checklist are in [docs/testing.md](docs/testing.md).

## Documentation

- Specialised guides live in `docs/`: [architecture](docs/architecture.md), [setup](docs/setup.md), [configuration](docs/configuration.md), [stacks](docs/stacks.md), [testing](docs/testing.md), [decisions](docs/adr/).
- A new configuration key, command or convention updates its guide in the same change.
- Link code with a symbol and a line range, as this file does; `uv run python -m tools.line_refs` fixes the numbers.

## Commits and changes

- Commit messages follow Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
- User-visible changes get a line under Unreleased in [CHANGELOG.md](CHANGELOG.md).
- `outpost.yaml` and `.outpost/` stay out of git; `outpost.example.yaml` is versioned and must keep loading, see [`test_the_example_loads`](tests/launcher/test_config.py#L35-L41).
