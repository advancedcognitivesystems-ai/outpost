# Setup

A host needs only Docker. Your machine needs the Docker CLI, uv and the Dev Container CLI, plus OpenSSH for a remote host; `./outpost doctor` checks them all.

## On your machine

| Tool | Why | Check |
| --- | --- | --- |
| Docker CLI | Drives the host's Docker; the daemon only for a local host | `docker version` |
| uv | Runs the launcher | `uv --version` |
| Dev Container CLI (Node.js) | Applies features and starts the container: `npm install -g @devcontainers/cli` | `devcontainer --version` |
| OpenSSH | Remote host only: Docker's transport and the tunnel | `ssh -V` |
| Claude Code, gh (optional) | Their logins are copied in when present | `claude auth status`, `gh auth status` |

## Local host

1. Run `./outpost up` from the Outpost folder, or `./outpost --config path/to/outpost.yaml up`.
2. Run `./outpost ca` and trust the saved certificate.
3. Open routes at `https://<route>.dev.localhost:8443` in Chrome or Firefox.

On Windows, run `./outpost` inside WSL with Docker Engine in WSL or Docker Desktop's WSL integration, and trust the certificate in Windows, where the browser runs.

## Remote host (Azure or any Linux VM)

1. Create an Ubuntu 24.04 VM sized for your stacks, for example 8 vCPU, 32 GB and a 256 GB disk.
2. Allow inbound SSH only, from your address or a VPN. No other port is needed.
3. Install Docker Engine and add your user to the `docker` group.
4. Add the VM to `~/.ssh/config` with connection sharing, then check `ssh my-vm docker version`.
5. Set `host: ssh://dev@my-vm` in `outpost.yaml` and run `./outpost up`.
6. Keep `./outpost tunnel` open while you browse; run `./outpost ca` once.

On Azure, steps 1 to 3:

```bash
az group create --name outpost --location westeurope
az vm create --resource-group outpost --name outpost-vm \
  --image Ubuntu2404 --size Standard_D8s_v5 --os-disk-size-gb 256 \
  --admin-username dev --ssh-key-values ~/.ssh/id_ed25519.pub
# then restrict the SSH rule of the VM's network security group to your address
ssh dev@<public-ip> 'curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker dev'
```

Each Docker command over SSH opens a session; sharing one keeps `up`, `shell` and `cp` fast:

```text
Host my-vm
  HostName <public-ip>
  User dev
  ControlMaster auto
  ControlPath ~/.ssh/cm-%r@%h:%p
  ControlPersist 10m
```

Registry logins stay on your machine: after `az acr login --name <registry>` or `docker login`, Docker sends the credentials with each pull it asks the host to make.

## Trust the certificate once

| Where the browser runs | Command |
| --- | --- |
| macOS | `security add-trusted-cert -r trustRoot -k ~/Library/Keychains/login.keychain-db outpost-ca.pem` |
| Windows | `certutil -user -addstore Root outpost-ca.pem` |
| Ubuntu or Debian | `sudo cp outpost-ca.pem /usr/local/share/ca-certificates/outpost-ca.crt && sudo update-ca-certificates` |
| Chrome on Linux | `certutil -d sql:$HOME/.pki/nssdb -A -t C,, -n outpost -i outpost-ca.pem` |
| Firefox | Settings, Certificates, Import |

`./outpost ca` prints the commands for your system, from [`trust_instructions`](../src/outpost/launcher/cli/render.py#L68-L76). The root survives recreation; only `destroy` makes a new one.

## Names in the browser

Chrome, Firefox and curl resolve every `*.localhost` name to your machine. Safari, and programs that ask the system's resolver, such as Python's, may not: add hosts entries, or set `domain` to a name whose DNS answers `127.0.0.1` for every subdomain.
