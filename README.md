# Outpost

Outpost runs a full development environment on a remote Docker host and drives it from your machine with one script. The environment is one dev container (the *box*) with its own Docker engine, many git worktrees, and one live stack per worktree, each service reachable at `https://<service>--<worktree>.<domain>` with a valid certificate.

The same implementation targets a local VM (WSL) or a remote VM (Azure, any SSH host); only `outpost.yaml` changes.

## Quick start

```sh
cp outpost.example.yaml outpost.yaml   # or: ./outpost init
./outpost config validate
./outpost doctor
./outpost up
./outpost worktree add feat-a --branch feature/a
./outpost stack up feat-a              # prints the stack's URLs
```

The entry script needs bash and [uv](https://docs.astral.sh/uv/); uv installs Python 3.12 and the dependencies on first run.

## Documentation

| Topic | Where |
| --- | --- |
| How it works: topology, routing, persistence, isolation | [docs/architecture.md](docs/architecture.md) |
| Every key of `outpost.yaml` | [docs/configuration.md](docs/configuration.md) |
| Adding a connection, TLS source, image source or check | [docs/extending.md](docs/extending.md) |
| Tests and fakes | [docs/testing.md](docs/testing.md) |
| Why things are the way they are | [docs/adr/](docs/adr/) |
| Working on Outpost | [CONTRIBUTING.md](CONTRIBUTING.md) |

## Status

Version 0.1.0 is a skeleton: the layers, the configuration and every port exist, and the adapters are written, but nothing has run against a real host yet.

| Area | State |
| --- | --- |
| Configuration: loading, validation, targets | Built and tested |
| Domain: names, routes, layouts, doctor results | Built and tested |
| `doctor`, `up`, `down`, `status`, `shell` | Built, tested with fakes, not yet run on a host |
| `worktree add / ls / rm`, `stack up / down / ls / urls / logs` | Built, tested with fakes, not yet run on a host |
| `creds status / sync`: copy, token, login | Built, tested with fakes, not yet run on a host |
| Edge and router (Traefik), local CA, ACME DNS-01 | Built; local CA generation tested with openssl |
| Box image (`resources/box/Dockerfile.tmpl`) | Written, not yet built |
| `--dry-run`, `destroy`, `stack forward`, `tls status` | Designed, not built: they exit with a clear message |

The [changelog](CHANGELOG.md) tracks what changes from here.
