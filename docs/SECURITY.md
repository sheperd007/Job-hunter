# Security hardening

Goal: run on a machine other people can also access, with secrets isolated,
encrypted at rest, and kept out of env. This doc covers all six measures.

## Threat model — read this first

**What hardening stops:** other *non-root* users snooping, secret theft from disk
or git, secrets leaking through `docker inspect` / `/proc/environ`, data exposure
if the disk is read or stolen.

**What it does NOT stop:** a user with **root / `sudo` / `docker`-group** access on
the host. Root can read any container's memory, exec into it, read volumes, and use
the docker socket. **No in-container measure defeats host root.** If untrusted
people have root, the only real isolation is:

- a **VM/VPS that only you control** (a $5/mo VPS *is* this), or
- a **confidential-computing VM** (AMD SEV / Intel TDX — encrypted RAM, e.g. Azure
  / GCP confidential VMs), which is the only thing that hides memory from host root.

Check what the other users actually have:

```bash
getent group docker sudo          # who is in docker/sudo groups
ls -l /var/run/docker.sock         # who can reach the docker socket
```

If your user is the only one in those groups, the steps below isolate you well.

---

## 1. Secrets as files, not env

`docker-compose.hardened.yml` reads every secret from `./secrets/*` (mounted at
`/run/secrets`) instead of env. They no longer show in `docker inspect` or
`/proc/<pid>/environ`.

- Worker: pydantic `secrets_dir=/run/secrets` (auto-reads `openai_key_a`, etc.).
- Postgres: `POSTGRES_PASSWORD_FILE`. n8n: `DB_POSTGRESDB_PASSWORD_FILE`,
  `N8N_ENCRYPTION_KEY_FILE`, `N8N_BASIC_AUTH_PASSWORD_FILE`.

Create the files (see [`secrets/README.md`](../secrets/README.md)), then bring the
stack up with the overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.hardened.yml up -d --build
```

**Use the secret-free `.env`** in hardened mode: `cp .env.hardened.example .env`.
This is not optional — env vars (and `.env`) **outrank** the secret files in both
pydantic-settings and Docker, so any secret left in `.env` would (a) be injected
into the container env (visible in `docker inspect`) and (b) silently override the
`/run/secrets/*` file. The overlay also blanks the base plaintext password keys
(`POSTGRES_PASSWORD`, `DB_POSTGRESDB_PASSWORD`, `N8N_BASIC_AUTH_PASSWORD`) so the
`*_FILE` values are the only ones that reach the containers.

## 2. Encrypt secrets at rest (age / SOPS)

Install [`age`](https://github.com/FiloSottile/age):

```bash
age-keygen -o age-key.txt          # prints the public key age1...; keep age-key.txt OFF the host
AGE_RECIPIENT=age1xxxx bash scripts/secrets-encrypt.sh   # -> secrets.tar.age (safe to store/commit)
```

At deploy, materialize the plaintext only long enough to start the stack:

```bash
AGE_KEY_FILE=/path/to/age-key.txt bash scripts/secrets-decrypt.sh
docker compose -f docker-compose.yml -f docker-compose.hardened.yml up -d
shred -u age-key.txt 2>/dev/null || rm -f age-key.txt   # remove the private key from the box
```

> Prefer SOPS? Encrypt a `secrets.yaml` with `sops --age age1xxxx -e -i secrets.yaml`
> and split it into `./secrets/*` on deploy. Same idea; age-tarball just needs one binary.

## 3. Rootless Docker (isolate from other non-root users)

Run the daemon under *your* user so others can't see/manage your containers and
there's no shared root docker socket:

```bash
sudo apt install -y uidmap dbus-user-session
dockerd-rootless-setuptool.sh install
export DOCKER_HOST=unix:///run/user/$(id -u)/docker.sock
docker compose -f docker-compose.yml -f docker-compose.hardened.yml up -d
```

(Ports <1024 need extra config; we don't use any. Podman in rootless mode is an
equivalent alternative.)

## 4. Encrypt data at rest (LUKS)

Put Postgres + n8n volumes on an encrypted volume so other users / a stolen disk
can't read them. File-backed LUKS container (no repartitioning):

```bash
fallocate -l 5G ~/agentdata.img
sudo cryptsetup luksFormat ~/agentdata.img
sudo cryptsetup open ~/agentdata.img agentdata
sudo mkfs.ext4 /dev/mapper/agentdata
sudo mkdir -p /mnt/agentdata && sudo mount /dev/mapper/agentdata /mnt/agentdata
sudo chown "$USER" /mnt/agentdata
```

`make luks-init` does the above and creates `$DATA_DIR/{postgres,n8n}` (chowning
the n8n dir to uid 1000, which the n8n container runs as). The hardened overlay
binds the data volumes to `$DATA_DIR`.

**Two traps to avoid (both silently leave data unencrypted):**
- **Set `DATA_DIR` + mount LUKS BEFORE the first `make harden-up`.** A Docker named
  volume caches its device path on first creation; pointing `DATA_DIR` somewhere new
  later does nothing until you `make harden-reset` (destroys the volumes so they
  rebind). `make harden-up` hard-aborts if `DATA_DIR` isn't a live mountpoint.
- **Reboot ordering.** Services use `restart: unless-stopped`, so the Docker daemon
  may start them before you unlock LUKS. After a reboot run `make luks-open` first,
  then `make harden-up`. For a fully automatic boot, add a systemd `.mount` unit (or
  `/etc/crypttab` + `/etc/fstab`) ordered `Before=docker.service` so `$DATA_DIR` is
  unlocked and mounted before Docker touches the bind paths.

## 5. n8n encryption key as a secret file

n8n encrypts stored credentials (Gmail/Telegram/Calendar tokens) at rest with
`N8N_ENCRYPTION_KEY`. The overlay supplies it via `N8N_ENCRYPTION_KEY_FILE` from
`./secrets/n8n_encryption_key`. **Keep it stable** — rotating it makes all saved
credentials unreadable.

## 6. Firewall + localhost-only binding

n8n (5678) and the worker (8000) are bound to `127.0.0.1` already — not reachable
from the network. Lock inbound to SSH and tunnel the UI:

```bash
bash scripts/firewall.sh
ssh -L 5678:localhost:5678 user@server      # then open http://localhost:5678
```

---

## Putting it together (hardened deploy)

```bash
# 1. create ./secrets/* (secrets/README.md)        # 2. firewall
bash scripts/firewall.sh
# 3. (optional) rootless docker, LUKS volume        # 4. bring up with overlay
docker compose -f docker-compose.yml -f docker-compose.hardened.yml up -d --build
# 5. encrypt secrets at rest, remove plaintext key
AGE_RECIPIENT=age1xxxx bash scripts/secrets-encrypt.sh
```

Residual risk: a root co-tenant. If that's your situation, move to a VM/VPS you
alone control — it's cheaper and stronger than any in-container trick.
