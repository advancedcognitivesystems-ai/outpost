# Configuration

Every key is optional: without `outpost.yaml`, `./outpost up` runs on your local Docker with the default image and both logins. [`outpost.example.yaml`](../outpost.example.yaml) shows every key.

The file is found by [`locate`](../src/outpost/launcher/config/loader.py#L26-L34) (`--config`, then `$OUTPOST_CONFIG`, then `./outpost.yaml`) and read by [`parse`](../src/outpost/launcher/config/loader.py#L47-L71). Unknown keys are refused, and every error names its key.

## Keys

| Key | Default | Meaning |
| --- | --- | --- |
| `name` | `main` | 1 to 30 lowercase letters, digits and `-`. Names the container `outpost-<name>` and its volumes |
| `host` | `local` | `local`, or `ssh://user@host[:port]`; your ssh config applies |
| `domain` | `dev.localhost` | Routes are `https://<route>.<domain>:<port>` |
| `port` | `8443` | Port on `127.0.0.1` where the proxy answers, on the host and through the tunnel |
| `devcontainer` | See below | devcontainer.json properties, merged over Outpost's defaults |
| `init` | None | Scripts copied into the state volume and run in order, as root, at every start |
| `credentials` | `[claude, gh]` | Logins checked and copied on every `up`; `[]` skips both |
| `copy` | None | A path of yours to a container path, copied on every `up`; `~` in the target is `/home/dev` |
| `persist` | None | More absolute container paths kept in volumes |

Paths on your machine are relative to the folder of `outpost.yaml`. The generated devcontainer.json goes to `.outpost/<name>/` in that folder; `./outpost config` prints it.

## The devcontainer settings

The defaults are the default image and the Claude Code feature. Your settings are checked by [`DevContainerSettings.parse`](../src/outpost/domain/devcontainer.py#L86-L103) and merged by [`define`](../src/outpost/domain/devcontainer.py#L218-L240):

- Your keys replace the defaults, except `features` and `containerEnv`, merged key by key; `null` removes a default entry.
- `build` replaces `image`. Its `dockerfile` and `context` are relative to `outpost.yaml`, and the build argument `OUTPOST_BASE` names the default image, for `ARG OUTPOST_BASE` then `FROM ${OUTPOST_BASE}`.
- Images must derive from `outpost/base`: the inner Docker, the proxy and the `outpost` tool come from it.
- Features come from a registry; local features are refused.

## What Outpost sets and refuses

| Setting | Value | Why |
| --- | --- | --- |
| `workspaceMount`, `workspaceFolder` | A volume on `/workspaces` | No folder of your machine is mounted |
| `mounts` | Outpost's volumes | Add volumes with `persist` |
| `privileged` | `true` | The inner Docker needs it |
| `overrideCommand` | `false` | The image's entrypoint runs at every start |
| `remoteUser` | `dev` | Logins, copies and shells belong to this user |
| `updateRemoteUserUID` | `false` | No bind mount to match |
| `runArgs` | `--name`, `--restart unless-stopped`, `--publish 127.0.0.1:<port>:443`, `--label outpost.settings=<digest>` | Identity, reboot recovery, the only published port, recreation |
| `containerEnv` `OUTPOST_*` | Name, domain, port | Read by the `outpost` tool |

Setting one of these is an error naming the key, from [`OWNED_KEYS`](../src/outpost/domain/devcontainer.py#L43-L57). So are `-v`, `--volume`, `--mount`, `-p`, `--publish`, `--name` and `--restart` in `runArgs`, from [`REFUSED_RUN_ARGS`](../src/outpost/domain/devcontainer.py#L58-L68).

## Logins

- **claude**: valid when `claude auth status` reports the claude.ai login, read by [`ClaudeLogin.state`](../src/outpost/launcher/adapters/logins.py#L80-L94). Otherwise your login is copied from the macOS Keychain or `~/.claude/.credentials.json` (`$CLAUDE_CONFIG_DIR` is honoured). With neither, `up` offers `claude auth login` in the container.
- **gh**: valid when `gh auth status` succeeds. Otherwise `gh auth token` from your machine is piped into `gh auth login --with-token`, then `gh auth setup-git` runs.
- Secrets go through stdin into files with mode 0600. Copying shares one Claude refresh token between your machine and the container; if one side is logged out, log in inside the container instead ([ADR 0007](adr/0007-copy-logins-first.md)).
