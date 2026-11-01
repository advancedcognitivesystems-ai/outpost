# Decision records

Each record states one decision, why it was taken, and what it costs. A change that reverses a decision adds a new record that supersedes the old one.

| ADR | Decision |
| --- | --- |
| [0001](0001-dev-container-framework.md) | Outpost is a framework around one dev container |
| [0002](0002-reference-devcontainer-cli.md) | Build and start with the reference Dev Container CLI |
| [0003](0003-no-host-mounts.md) | No mounts between the host and the dev container |
| [0004](0004-image-or-volume.md) | If it is not in the image, it is in a volume |
| [0005](0005-caddy-proxy-in-the-container.md) | Caddy on the inner Docker, routes through its admin API |
| [0006](0006-docker-over-ssh.md) | Reach a remote host through Docker over SSH |
| [0007](0007-copy-logins-first.md) | Copy logins first, log in inside as a fallback |
