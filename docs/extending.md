# Extending Outpost

Every choice that can vary is a `kind` in the configuration, resolved by one factory into one adapter. Adding a kind touches the same five places each time, and nothing outside them.

## The five places

1. **Domain value.** A frozen dataclass for the new kind, added to its union, such as `TlsSpec` next to [`AcmeTls`](../src/outpost/domain/config.py#L54-L57).
2. **Parsing.** The kind's name in its enum and a line in its table, such as [`TlsKind`](../src/outpost/config/loader.py#L70-L73) and [`_TLS`](../src/outpost/config/loader.py#L199-L207).
3. **Adapter.** One module in the port family's package, implementing the port, such as [`AcmeDnsChallenge`](../src/outpost/adapters/tls/acme.py#L22-L50) for [`TlsProvisioner`](../src/outpost/ports/tls.py#L11-L18). If it runs a program on the client, it lists it in `client_commands` (see below).
4. **Factory.** One `case` in the family's factory, such as [`build_tls`](../src/outpost/adapters/tls/factory.py#L17-L25). mypy checks that every case of the union is handled.
5. **Tests and docs.** A test of the adapter's output, a row in [configuration.md](configuration.md), and the kind in `outpost.example.yaml` if it is common.

A new TLS kind usually produces one of the existing [`TlsMaterial`](../src/outpost/domain/tls.py#L43) shapes. Only a new shape also needs the edge to handle it, in [`TraefikEdge`](../src/outpost/adapters/proxy/traefik.py#L35-L80).

## The families

| Family | Port | Factory | Existing kinds |
| --- | --- | --- | --- |
| Connection to the host | [`Shell`](../src/outpost/ports/shell.py#L46-L88) | [`build_host_shell`](../src/outpost/adapters/shell/factory.py#L11-L16) | `local`, `ssh` |
| Certificates | [`TlsProvisioner`](../src/outpost/ports/tls.py#L11-L18) | [`build_tls`](../src/outpost/adapters/tls/factory.py#L17-L25) | `acme`, `local-ca`, `none` |
| Base image | [`ImageSupplier`](../src/outpost/ports/images.py#L17-L20) | [`build_image_supplier`](../src/outpost/adapters/images/factory.py#L27-L42) | `registry`, `local` |
| Registry login | [`RegistryAuth`](../src/outpost/ports/images.py#L11-L14) | [`build_registry_auth`](../src/outpost/adapters/images/factory.py#L45-L56) | `none`, `docker-login`, `azure-acr` |
| Client secrets | [`SecretSource`](../src/outpost/ports/credentials.py#L12-L20) | [`build_secret_source`](../src/outpost/adapters/credentials/factory.py#L25-L44) | `auto`, `file`, `keychain`, `command`, `env` |
| Tool logins | [`ToolAuth`](../src/outpost/ports/credentials.py#L23-L39) | [`build_tool_auth`](../src/outpost/adapters/credentials/factory.py#L59-L64) | `claude`, `github` |

## Ports with a single adapter today

These have one implementation, built directly in [`App`](../src/outpost/cli/wiring.py#L60-L205). A second one gets a factory and a configuration kind at that point.

| Port | Adapter |
| --- | --- |
| [`ContainerEngine`](../src/outpost/ports/engine.py#L63-L117) | [`DockerCliEngine`](../src/outpost/adapters/engine/docker_cli.py#L23-L117), used for the client, the host and the box's inner engine |
| [`MachineProbe`](../src/outpost/ports/probe.py#L8-L21) | [`ShellProbe`](../src/outpost/adapters/probe/shell_probe.py#L14-L43) for the host, through any shell; [`InProcessProbe`](../src/outpost/adapters/probe/in_process.py#L12-L33) for the client |
| [`EdgeProxy`](../src/outpost/ports/proxy.py#L14-L17), [`RouterConvention`](../src/outpost/ports/proxy.py#L20-L32) | [`TraefikEdge`](../src/outpost/adapters/proxy/traefik.py#L35-L80), [`TraefikRouter`](../src/outpost/adapters/proxy/traefik.py#L153-L184) |
| [`StackRunner`](../src/outpost/ports/stacks.py#L21-L36) | [`ComposeStacks`](../src/outpost/adapters/stacks/compose.py#L32-L82) |
| [`Repository`](../src/outpost/ports/repository.py#L12-L26) | [`GitRepository`](../src/outpost/adapters/repository/git_cli.py#L17-L77) |

## Programs on the client

An adapter that runs a program on the client says so through `client_commands`, from [`ClientNeeds`](../src/outpost/ports/shell.py#L39-L43): [`SshShell`](../src/outpost/adapters/shell/ssh.py#L17-L59) needs `ssh` and `scp`, [`AzureAcrLogin`](../src/outpost/adapters/images/registry_auth.py#L44-L63) needs `az`. The composition root hands the adapters in use to `doctor`, and [`ClientTools`](../src/outpost/application/checks.py#L19-L31) checks them all before `up` needs them. Nothing else keeps a list.

## Adding a doctor check

Subclass [`Check`](../src/outpost/application/doctor.py#L13-L37), name its prerequisites in `requires` so it is skipped when they fail, and return `ok`, `warn` or `fail`. A check that can repair itself returns `fail(..., fixable=True)` and overrides `fix`, like [`ToolLogin`](../src/outpost/application/checks.py#L128-L143). Register it in [`standard_checks`](../src/outpost/application/checks.py#L146-L169).
