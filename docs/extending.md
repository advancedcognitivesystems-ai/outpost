# Extending Outpost

Every choice that can vary is a `kind` in the configuration, resolved by one factory into one adapter. Adding a kind touches the same five places each time.

## The five places

1. **Domain value.** A frozen dataclass for the new kind, added to its union, such as `TlsSpec` next to [`AcmeTls`](../src/outpost/domain/config.py#L54-L57).
2. **Parsing.** The kind's name in its enum and a line in its table, such as [`TlsKind`](../src/outpost/config/loader.py#L62-L65) and [`_TLS`](../src/outpost/config/loader.py#L193-L201).
3. **Adapter.** One module in the port family's package, implementing the port, such as [`AcmeDnsChallenge`](../src/outpost/adapters/tls/acme.py#L17-L37) for [`TlsProvisioner`](../src/outpost/ports/tls.py#L11-L18).
4. **Factory.** One `case` in the family's factory, such as [`build_tls`](../src/outpost/adapters/tls/factory.py#L14-L21). mypy checks that every case of the union is handled.
5. **Tests and docs.** A test of the adapter's output, a row in [configuration.md](configuration.md), and the kind in `outpost.example.yaml` if it is common.

## The families

| Family | Port | Factory | Existing kinds |
| --- | --- | --- | --- |
| Connection to the host | [`Shell`](../src/outpost/ports/shell.py#L31-L65) | [`build_host_shell`](../src/outpost/adapters/shell/factory.py#L11-L16) | `local`, `ssh` |
| Facts about the host | [`MachineProbe`](../src/outpost/ports/probe.py#L8-L21) | [`build_host_probe`](../src/outpost/adapters/probe/factory.py#L12-L17) | in-process, through a shell |
| Certificates | [`TlsProvisioner`](../src/outpost/ports/tls.py#L11-L18) | [`build_tls`](../src/outpost/adapters/tls/factory.py#L14-L21) | `acme`, `local-ca`, `none` |
| Base image | [`ImageSupplier`](../src/outpost/ports/images.py#L16-L19) | [`build_image_supplier`](../src/outpost/adapters/images/factory.py#L27-L42) | `registry`, `local` |
| Registry login | [`RegistryAuth`](../src/outpost/ports/images.py#L10-L13) | [`build_registry_auth`](../src/outpost/adapters/images/factory.py#L45-L56) | `none`, `docker-login`, `azure-acr` |
| Client secrets | [`SecretSource`](../src/outpost/ports/credentials.py#L11-L19) | [`build_secret_source`](../src/outpost/adapters/credentials/factory.py#L25-L44) | `auto`, `file`, `keychain`, `command`, `env` |
| Tool logins | [`ToolAuth`](../src/outpost/ports/credentials.py#L22-L38) | [`build_tool_auth`](../src/outpost/adapters/credentials/factory.py#L59-L64) | `claude`, `github` |

## Ports with a single adapter today

These have one implementation, built directly in [`App`](../src/outpost/cli/wiring.py#L58-L187). A second one gets a factory and a configuration kind at that point.

| Port | Adapter |
| --- | --- |
| [`ContainerEngine`](../src/outpost/ports/engine.py#L63-L123) | [`DockerCliEngine`](../src/outpost/adapters/engine/docker_cli.py#L22-L126) |
| [`EdgeProxy`](../src/outpost/ports/proxy.py#L14-L17), [`RouterConvention`](../src/outpost/ports/proxy.py#L20-L32) | [`TraefikEdge`](../src/outpost/adapters/proxy/traefik.py#L30-L70), [`TraefikRouter`](../src/outpost/adapters/proxy/traefik.py#L140-L174) |
| [`StackRunner`](../src/outpost/ports/stacks.py#L21-L28) | [`ComposeStacks`](../src/outpost/adapters/stacks/compose.py#L25-L64) |
| [`Repository`](../src/outpost/ports/repository.py#L12-L23) | [`GitRepository`](../src/outpost/adapters/repository/git_cli.py#L16-L63) |

## Adding a doctor check

Subclass [`Check`](../src/outpost/application/doctor.py#L13-L37), name its prerequisites in `requires` so it is skipped when they fail, and return `ok`, `warn` or `fail`. A check that can repair itself returns `fail(..., fixable=True)` and overrides `fix`, like [`ToolLogin`](../src/outpost/application/checks.py#L132-L145). Register it in [`standard_checks`](../src/outpost/application/checks.py#L165-L187).

## Adding a client tool requirement

When a configuration value makes Outpost run a new command on the client, add it to [`required_client_tools`](../src/outpost/application/checks.py#L148-L162) so `doctor` reports it missing before `up` needs it.
