# Contributing to Outpost

This guide points to files and line ranges instead of repeating code. Every `[symbol](file#lines)` link below is kept current by [`refresh`](tools/line_refs.py#L90-L110) and checked by [`test_reference_is_current`](tests/test_doc_references.py#L17-L24); when a link goes stale, the tests say how to refresh it.

## Before you start

- Read [docs/architecture.md](docs/architecture.md): the runtime topology and the four code layers.
- The layering is enforced, not just described: the import contracts start at [`tool.importlinter`](pyproject.toml#L57-L59) and break the build when a layer imports the wrong way.
- Decisions that shaped the code are recorded in [docs/adr/](docs/adr/). A change that reverses one adds a new ADR.

## Working setup

- Python and the tools come from uv; the dependency list starts at [`dependency-groups`](pyproject.toml#L12-L20).
- The checks are the hooks in [`repo: local`](.pre-commit-config.yaml#L14-L43): format, lint, strict types, import contracts, tests. CI runs exactly these hooks, see [`checks`](.github/workflows/ci.yml#L9-L17).
- Commands, fakes and what the tests do not cover are in [docs/testing.md](docs/testing.md).

## Where a change goes

| You want to | Start here | Then |
| --- | --- | --- |
| Add a configuration key | The value type, such as [`EdgeSpec`](src/outpost/domain/config.py#L74-L87) | Parse it in [`_edge`](src/outpost/config/loader.py#L172-L183) or its neighbour, add it to `outpost.example.yaml`, add its row to [docs/configuration.md](docs/configuration.md) |
| Add a kind (connection, TLS, image source, registry login, secret source) | [docs/extending.md](docs/extending.md) | One adapter module, one line in its factory, such as [`build_tls`](src/outpost/adapters/tls/factory.py#L14-L21) |
| Add a doctor check | The base class [`Check`](src/outpost/application/doctor.py#L13-L37); an example is [`FreeDisk`](src/outpost/application/checks.py#L82-L98) | Register it in [`standard_checks`](src/outpost/application/checks.py#L165-L187) |
| Add a command | The parser in [`build_parser`](src/outpost/cli/main.py#L27-L107) | A handler in `src/outpost/cli/commands.py`, a use case in `src/outpost/application/`, its ports from [`App`](src/outpost/cli/wiring.py#L58-L187) |
| Change what the box contains | `src/outpost/resources/box/Dockerfile.tmpl` | [`BoxImage`](src/outpost/application/box.py#L23-L54) rebuilds when the rendered file changes |
| Change how routes are named | [`plan_routes`](src/outpost/domain/routes.py#L45-L65) | The labels in [`TraefikRouter`](src/outpost/adapters/proxy/traefik.py#L140-L174) and the edge rule in [`edge_dynamic_config`](src/outpost/adapters/proxy/traefik.py#L99-L129) |
| Change the credential flow | [`CredentialSync`](src/outpost/application/credentials.py#L26-L90) | Tool specifics stay in [`ClaudeAuth`](src/outpost/adapters/credentials/claude.py#L25-L59) and [`GithubAuth`](src/outpost/adapters/credentials/github.py#L15-L43) |
| Add a port | A new module in `src/outpost/ports/` | A fake in `tests/fakes.py` next to [`FakeShell`](tests/fakes.py#L28-L82), and its adapter built in [`App`](src/outpost/cli/wiring.py#L58-L187) |

## Rules the review checks

- **Layers.** The domain imports nothing from Outpost and does no I/O. Ports import the domain only. The application imports the domain and ports. Adapters import the domain and ports, never the application. Only [`App`](src/outpost/cli/wiring.py#L58-L187) builds adapters.
- **One place per decision.** A configuration `kind` becomes an adapter in exactly one factory; there is no other branch on a kind. Parsing tables such as [`_TLS`](src/outpost/config/loader.py#L193-L201) do the same for the file format.
- **Domain types in signatures.** Pass [`WorktreeName`](src/outpost/domain/names.py#L42-L56), `Route` or `ImageRef`, not strings; a value is validated once, when it is built.
- **Errors.** Raise the errors in [`OutpostError`](src/outpost/domain/errors.py#L8-L9)'s module; only [`main`](src/outpost/cli/main.py#L110-L122) turns them into messages and exit codes.
- **No duplication.** Every command on the client, the host or the box goes through a `Shell`; the box reuses the host's shell through [`ContainerShell`](src/outpost/adapters/shell/container.py#L16-L40). Shared POSIX behaviour lives once in [`ShellBase`](src/outpost/adapters/shell/base.py#L15-L58).
- **Generated files.** Files for the host are templates in `src/outpost/resources/` rendered by [`render_text`](src/outpost/adapters/interaction/templates.py#L23-L30); generated YAML is built as data and serialised, as in [`compose_override`](src/outpost/adapters/stacks/compose.py#L67-L89).
- **Secrets.** Secrets travel as [`Secret`](src/outpost/domain/secrets.py#L8-L28), through stdin or files with mode 0600, never through arguments, environment listings or logs.

## Tests

- Every port has an in-memory fake in `tests/fakes.py`; use cases are tested only through them, as in [`test_up_builds_runs_edge_then_box_then_clones`](tests/application/test_doctor_and_environment.py#L119-L135).
- Adapters are tested on the arguments they produce, as in [`test_box_run_arguments_are_stable`](tests/adapters/test_shells_and_engine.py#L39-L61), or against a real local tool when it is safe, as in [`test_local_ca_issues_a_wildcard_once`](tests/adapters/test_tls_templates_credentials.py#L27-L42).
- Strategy and layout are in [docs/testing.md](docs/testing.md).

## Documentation

- Specialised guides live in `docs/`: [architecture](docs/architecture.md), [configuration](docs/configuration.md), [extending](docs/extending.md), [testing](docs/testing.md), [decisions](docs/adr/).
- A new configuration key, command or kind updates its guide in the same change.
- Link code with a symbol and a line range, as this file does; the refresh tool fixes the numbers.

## Commits and changes

- Commit messages follow Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
- User-visible changes get a line under Unreleased in [CHANGELOG.md](CHANGELOG.md).
- `outpost.yaml` stays out of git; only `outpost.example.yaml` is versioned, and it must keep loading, see [`test_example_loads_both_targets`](tests/config/test_loader.py#L40-L43).
