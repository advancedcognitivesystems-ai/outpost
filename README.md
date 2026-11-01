# Outpost

Outpost runs one dev container, your single entry point, on your machine or on a remote Linux host, from one optional file and one command.

```bash
./outpost up        # build the default image if needed, start the container, copy your logins
./outpost ca        # once: save the proxy's root certificate, then trust it
./outpost shell     # then `claude`, `gh`, `docker compose up` ...
```

Inside, a stack registers its own HTTPS URL:

```bash
outpost route add api.feat-a feat-a-api-1:8080   # https://api.feat-a.dev.localhost:8443
```

## What you get

- **One container is the entry point.** Claude Code with your claude.ai login and connectors, the GitHub CLI, an inner Docker for your stacks, and a proxy with its own certificate authority.
- **Local or remote, same commands.** `host: ssh://dev@my-vm` runs it on a VM; the host only needs Docker and SSH.
- **No mounts.** Files cross by copy: `./outpost cp ./spec.pdf :~/inbox/`, `./outpost cp :/workspaces/app/out ./out`.
- **A restart changes nothing on disk.** What is not in the image is in a named volume; recreating the container keeps the volumes.

## Documentation

- [Setup](docs/setup.md): prerequisites, a local host, an Azure VM, trusting the certificate.
- [Configuration](docs/configuration.md): `outpost.yaml`, the devcontainer settings, logins.
- [Building on Outpost](docs/stacks.md): routes, upstreams, init scripts.
- [Architecture](docs/architecture.md) and [decisions](docs/adr/).
- [Contributing](CONTRIBUTING.md) and [testing](docs/testing.md).
