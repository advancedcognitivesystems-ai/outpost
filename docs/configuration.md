# Configuration

One file, `outpost.yaml`, describes the environment. It stays out of git; [`outpost.example.yaml`](../outpost.example.yaml) is its template and shows every key with its accepted values. Shared sections hold the project, the box, the stacks and the credentials; `targets` hold what differs per host, and `--target` or `default_target` picks one.

The file is parsed by [`parse_config`](../src/outpost/config/loader.py#L94-L109) into [`OutpostConfig`](../src/outpost/domain/config.py#L246-L268). Unknown keys are refused, and every error names the exact key at fault.

## Reference

| Key | Values | Default | Meaning |
| --- | --- | --- | --- |
| `version` | `1` | Required | Schema version |
| `project.name` | Lowercase letters, digits, `-` (30 max) | Required | Prefix of every host object, `outpost-<name>-*` |
| `project.repository` | Git URL | Required | Cloned into `/workspaces/<name>/repo` on the first `up` |
| `project.default_branch` | Branch name | `main` | Base of new worktrees |
| `default_target` | A key of `targets` | The only target | Used when `--target` is absent |
| `targets.<t>.connection.kind` | `local`, `ssh` | Required | How the client runs host commands |
| `targets.<t>.connection.host`, `user`, `port`, `identity_file` | | `ssh` only; port `22` | Passed to OpenSSH; your ssh config still applies |
| `targets.<t>.host.isolation` | `sysbox`, `privileged` | `sysbox` | Runtime of the box |
| `targets.<t>.host.state_dir` | Absolute path or `~/…` on the host | `~/.outpost` | Rendered settings, secrets (0600), exchange directory |
| `targets.<t>.host.min_free_disk_gb` | Integer | `50` | `doctor` fails below it |
| `targets.<t>.edge.domain` | DNS name with a dot | Required | Routes are `<service>--<worktree>.<domain>` |
| `targets.<t>.edge.listen` | IP address | `127.0.0.1` | Address the edge binds on the host |
| `targets.<t>.edge.ports.http`, `https` | Ports | `80`, `443` | Host ports of the edge |
| `targets.<t>.edge.tls.kind` | `acme`, `local-ca`, `none` | `local-ca` | Source of the wildcard certificate |
| `targets.<t>.edge.tls.email`, `dns_provider`, `dns_env_file` | | `acme` only | ACME account, DNS-01 provider (a lego provider name), client file with its credentials |
| `targets.<t>.image` | Same shape as `box.image` | None | Replaces `box.image` for that target |
| `box.image.source` | `registry`, `local` | Required | Pull on the host, or copy from the client's Docker |
| `box.image.ref` | Image reference | Required | Base image the box is built on (Debian or Ubuntu based) |
| `box.image.registry_auth.kind` | `none`, `docker-login`, `azure-acr` | `none` | How the host logs in before pulling; `registry` source only |
| `box.image.registry_auth.registry`, `username`, `password_env` | | Per kind | ACR name; or registry host, user and the client env var holding the password |
| `box.user` | Unix user name | `dev` | User inside the box |
| `box.cpus`, `box.memory_gb` | Numbers | No limit | Resource limits of the box |
| `box.env` | Map of strings | Empty | Plain settings; names that look like secrets are refused |
| `stacks.compose_files` | Paths in the worktree | Required | Passed to `docker compose --file`, in order |
| `stacks.expose[]` | `service`, `port`, `subdomain` | `subdomain` = `service` | One route per entry; subdomains must be unique |
| `credentials.claude.strategy` | `copy`, `login`, `skip` | `copy` | See the credential flow |
| `credentials.claude.source.kind` | `auto`, `file`, `keychain`, `command`, `env` | `auto` | `auto`: the macOS keychain, else `~/.claude/.credentials.json` |
| `credentials.github.strategy` | `copy`, `token`, `login`, `skip` | `copy` | See the credential flow |
| `credentials.github.source` | As above | `auto`: `gh auth token` | Read by `copy` |
| `credentials.github.token_env` | Env var name | `OUTPOST_GH_TOKEN` | Read by `token`: a fine-grained PAT |
| `credentials.github.setup_git` | Boolean | `true` | Runs `gh auth setup-git` in the box |
| `credentials.git.user_name`, `user_email` | Strings | Required | Commit identity in the box |

## Secrets

- `outpost.yaml` never holds a secret, only where to read one on the client: a file, an environment variable name, the macOS keychain, or a command's output. The readers are built by [`build_secret_source`](../src/outpost/adapters/credentials/factory.py#L25-L44).
- On the host, Outpost writes secrets only into the box home volume or `<state_dir>/secrets`, with mode 0600.
- The box must not define `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY`: either one takes precedence over the claude.ai login and hides claude.ai connectors. [`ClaudeAuth.state`](../src/outpost/adapters/credentials/claude.py#L34-L47) reports it.

## Credential flow

`up` and `creds sync` run the same steps for Claude Code, then GitHub; see [`CredentialSync`](../src/outpost/application/credentials.py#L26-L90).

1. Check in the box with the tool itself. Valid means nothing to do.
2. `copy`: read the client source; found means install it in the box, then check again.
3. Nothing on the client: ask whether to log in on the box, or on this machine and then copy, or stop.
4. `login`: open the tool's interactive login in the box.
5. `token` (GitHub only): read the PAT from `token_env` and log `gh` in with it.
6. Then `gh auth setup-git` when `setup_git` is true, and the git identity during `up`.

Copying a Claude login gives the client and the box the same refresh token. If that logs one side out, switch to `strategy: login` (tracked in [ADR 0007](adr/0007-credentials-copy-first.md)).
