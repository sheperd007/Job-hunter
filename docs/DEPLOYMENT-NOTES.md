# Deployment Notes — tararis-AI server (hardened)

Live deployment record + fixes discovered during the first hardened deploy.
**This file is secret-free and safe to commit.** Actual secret values (API keys,
LUKS passphrase, n8n login, bot token) live in the operator's password manager —
never commit them. Placeholders below read `<...>`.

Deployed: 2026-06-13. Mode: **hardened** (`docker-compose.hardened.yml`), data on LUKS,
secrets as files, `DRY_RUN=false` (live).

---

## 1. Host / topology

| Item | Value |
|---|---|
| Host | `192.168.1.48` (`tararis-AI`), Ubuntu 24.04.4 LTS, kernel 6.17 |
| SSH user | `hamid` (uid **1001**; in `sudo` + `docker` groups, NOPASSWD sudo) |
| Docker / Compose | 29.1.3 / v2.40.3 |
| Project dir | `~/Job-hunter` |
| Data (LUKS) | `/mnt/agentdata` → `postgres/`, `n8n/` (n8n dir chown **1000:1000**) |
| LUKS image | `~/agentdata.img` (10 GB, LUKS2, aes-xts), mapper `agentdata` |
| Published ports | n8n `127.0.0.1:5678`, worker `127.0.0.1:8000` (localhost only) |
| Postgres | internal only (no host port) |
| Co-tenants on host | airflow, grafana, openclaw, gitlab-runner (port 8080 in use). No conflict. |
| Access from laptop | `ssh -i <key> -L 5678:localhost:5678 hamid@192.168.1.48` → http://localhost:5678 |

> n8n is **2.25.7** (the 2.x line) — relevant to fixes #2, #3, #5 below.

---

## 2. Where every credential lives

| Credential | Location | Consumed by |
|---|---|---|
| OpenAI key A / B | `secrets/openai_key_a`, `_b` | worker (pydantic `secrets_dir`) |
| Notion token | `secrets/notion_token` | worker |
| Adzuna **app_key** | `secrets/adzuna_app_key` | worker |
| DB password | `secrets/db_password` | postgres / n8n / worker |
| n8n encryption key | `secrets/n8n_encryption_key` | n8n (keep STABLE) |
| n8n basic-auth pwd | `secrets/n8n_basic_auth_password` | n8n (superseded — see note) |
| Adzuna **app_id** | `.env` `ADZUNA_APP_ID` (non-secret) | worker |
| Telegram **chat_id** | `.env` `TELEGRAM_CHAT_ID` (non-secret) | n8n workflows (`$env`) |
| Telegram **bot token** | n8n "Telegram account" credential **and** hardcoded in W5 `getUpdates` URL | n8n |
| Google (Gmail+Calendar) | n8n OAuth2 credentials | n8n |
| CV profile | Postgres `profile` table (built from CV via `/profile/build`) | worker matcher |

n8n credential IDs (for embedding in workflow JSON): Gmail `gmailOAuth2` =
`rjcfw9HnGlTu7u7J`, Calendar `googleCalendarOAuth2Api` = `RuFZXYAHqhXHO29S`,
Telegram `telegramApi` = `OUYOPmNjlUrpmaZK`.

> **n8n login note:** n8n 2.x uses its built-in owner account (created at
> `http://localhost:5678/setup`), which **supersedes** `N8N_BASIC_AUTH_*`. The
> basic-auth secret file is effectively unused for login.

---

## 3. Network findings (Iran egress)

Tested reachability from the server:

| Host | Result |
|---|---|
| OpenAI, Notion, Adzuna | ✅ reachable, keys validated (HTTP 200) |
| Google (oauth2 / gmail / accounts / googleapis) | ✅ reachable |
| **api.telegram.org** | ❌ **DNS-sinkholed** → `10.10.34.36` (Iran filternet); times out |

- Telegram is blocked **only at DNS** — the real Telegram DC IP
  **`149.154.167.220`** is reachable and serves the API (verified HTTP 200 via
  `curl --resolve`). Other Telegram IPs (`149.154.167.222`, `91.108.56.130`) did
  not respond on HTTPS.
- Fix = pin the IP for the n8n container (fix #4). **If Telegram breaks later,
  re-verify this IP** (Telegram may rotate it):
  `curl --resolve api.telegram.org:443:<ip> https://api.telegram.org/bot<token>/getMe`
- OpenAI/Google reachable means no relocation needed (the README's "never host on
  Iranian infra" warning is only partly triggered — Telegram is the lone casualty).
- The **operator's own** phone/browser still needs a VPN for Telegram and for the
  Google "Sign in with Google" consent step (Google blocks Iran sign-in). Only the
  *server-side* path is handled here.

---

## 4. The 6 fixes applied on the server (BACKPORT THESE to the repo)

These were needed to make the hardened stack actually run. They are live on the
server but **not yet in the git repo**.

### Fix 1 — `secrets/*` must be mode `0444`, not `0600`
- **Symptom:** worker crash-loop: `SettingsError: error getting value for field
  "openai_key_a" from source "SecretsSettingsSource"` → `Permission denied`.
- **Cause:** in non-swarm Compose, file secrets keep the host file's mode (`0600`,
  owner uid 1001). The worker runs `cap_drop: ALL` → container-root loses
  `CAP_DAC_OVERRIDE` → cannot read a `0600` file it doesn't own. (n8n uid-1000 and
  postgres hit the same wall.)
- **Fix:** `chmod 0444 secrets/*`. Safe because `~` is `0750` (only owner+root can
  traverse). **`secrets/README.md` currently says `chmod 600` — that is wrong for
  non-swarm compose; change it to `chmod 444`.** Consider having `make harden-up`
  enforce `chmod 444 secrets/*`.

### Fix 2 — n8n plaintext password keys must be `null`, not `""`
- **File:** `docker-compose.hardened.yml`, `n8n.environment`.
- **Symptom:** n8n crash-loop: `SASL: SCRAM-SERVER-FIRST-MESSAGE: client password
  must be a string`.
- **Cause:** the overlay blanked `DB_POSTGRESDB_PASSWORD: ""` /
  `N8N_BASIC_AUTH_PASSWORD: ""`. n8n reads `*_PASSWORD_FILE` **only when the plain
  var is UNSET** — an empty string still counts as *set* → n8n uses `""` →
  undefined password → crash. (Postgres survives the same `""` because its
  `file_env` treats empty as unset; n8n does not.)
- **Fix:** set them to **null** (key with no value) so the var is unset and the
  `_FILE` value wins:
  ```yaml
  n8n:
    environment:
      DB_POSTGRESDB_PASSWORD:          # was ""
      N8N_BASIC_AUTH_PASSWORD:         # was ""
  ```

### Fix 3 — `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`
- **Symptom:** workflow expressions show `[ERROR: access to env vars denied]`.
- **Cause:** n8n **2.0** changed the default of `N8N_BLOCK_ENV_ACCESS_IN_NODE` to
  `true`, blocking `$env` in expressions + Code nodes. The workflows use
  `$env.WORKER_URL`, `$env.TELEGRAM_CHAT_ID`, `$env.OWNER_EMAIL`,
  `$env.GOOGLE_CALENDAR_ID`.
- **Fix:** `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` in `.env` (and document in
  `.env.hardened.example`). **Note:** the editor *preview* still prints
  "access to env vars denied" because the browser can't read server env — that's
  **cosmetic**; at runtime the expression resolves (verified: W3 `POST /jobs/run`
  returned 200).

### Fix 4 — Telegram DNS pin (new compose file + Makefile)
- **New file `docker-compose.telegram.yml`:**
  ```yaml
  services:
    n8n:
      extra_hosts:
        - "api.telegram.org:149.154.167.220"
  ```
- **Makefile:** add the file to the hardened set:
  ```make
  HARDENED := -f docker-compose.yml -f docker-compose.hardened.yml -f docker-compose.telegram.yml
  ```
- Only required on Iran/filtered networks; harmless elsewhere. See §3.

### Fix 5 — W5 rebuilt as **polling** (no public webhook)
- **File:** `n8n/workflows/W5-telegram-approvals.json`.
- **Symptom:** W5 fails to activate: `Bad request - please check your parameters`
  (looping).
- **Cause:** the original W5 uses a **Telegram Trigger**, which registers a
  **webhook** with Telegram → needs a public **HTTPS** URL. This deployment is
  localhost-only behind NAT — no public URL.
- **Fix:** replaced the trigger chain with polling, keeping the downstream
  (`Parse → Resolve → Act now? → reply/event → Gmail/Calendar`) identical:
  - `Schedule Trigger` (every 1 min)
  - `Read offset` (Code): reads `tgOffset` from workflow static data
  - `getUpdates` (HTTP GET, bot token in URL, resolves via the DNS pin)
  - `Advance offset` (Code): stores `last update_id + 1` in static data, emits one
    item per `callback_query`
  - Embedded credential IDs so no manual re-wiring.
  - Button contract unchanged: W1/W2 send `callback_data` = `a:<id>` (approve) /
    `r:<id>` (reject); `a:` ⇒ decision `approve`.
- **Tradeoffs:** ~60s latency on taps (vs instant); bot token is hardcoded in the
  `getUpdates` URL (visible to anyone with n8n access). Run `deleteWebhook` once
  before activating (done) so `getUpdates` doesn't 409. Verified: scheduled run =
  `success`, no errors.
- **Alternative** (not chosen): Cloudflare Tunnel for a public HTTPS webhook
  (instant, but needs a Cloudflare account/domain + public exposure).

### Fix 6 — `.env` contents (secret-free, hardened)
The committed `.env.hardened.example` referenced in the overlay **does not exist
in the repo** — create it. The live `.env` is secret-free and contains:
```
DATA_DIR=/mnt/agentdata
DRY_RUN=false                      # was true until first watched run
POSTGRES_USER=n8n
POSTGRES_DB=n8n
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL_TRIAGE=gpt-4.1-mini
MODEL_MATCH=gpt-4.1
MODEL_FALLBACK=gpt-4o-mini
MONTHLY_CAP_USD=8.0
CAP_SAFETY_MARGIN_USD=7.5
DAILY_SOFT_CAP_USD=0.27
TZ=Asia/Tehran
N8N_HOST=localhost
WEBHOOK_URL=http://localhost:5678/
N8N_BASIC_AUTH_ACTIVE=true
N8N_BASIC_AUTH_USER=admin
N8N_BLOCK_ENV_ACCESS_IN_NODE=false   # fix #3
NOTION_APPLICATIONS_DB=70b08f56f7fc4825b9e45993a409cb11
NOTION_VERSION=2022-06-28
OWNER_EMAIL=<owner gmail>
WORKER_URL=http://worker:8000
GOOGLE_CALENDAR_ID=primary
ADZUNA_APP_ID=<adzuna app id>
TELEGRAM_CHAT_ID=<numeric chat id>
```
No passwords/keys/tokens in `.env` (hardened mode reads those from `secrets/*`).

---

## 5. Reboot / LUKS procedure (HOST reboot only)

The LUKS mount survives as long as the host is powered on; container restarts do
**not** need a re-unlock. Only a **host reboot/power-cycle** locks the volume.

**Race to avoid:** Docker auto-starts the containers (`restart: unless-stopped`)
*before* LUKS is unlocked → bind path `/mnt/agentdata` is an empty folder on the
root disk → Postgres could initialise an empty DB on **plain (unencrypted)** disk.
Real data is safe on the locked volume, but you'd briefly run a wrong instance.

**Correct sequence after a host reboot:**
```bash
cd ~/Job-hunter
make luks-open      # enter LUKS passphrase -> unlock + mount /mnt/agentdata
make harden-up      # recreate containers so they bind the now-mounted real data
```
Order matters: unlock first, then (re)start containers.

**Optional automation (not yet done):** a systemd `.mount`/`crypttab` unit ordered
`Before=docker.service`.
- *Manual-unlock-but-Docker-waits* (recommended): keeps the passphrase off disk,
  removes the race; you still `make luks-open` after reboot.
- *Keyfile auto-unlock*: fully unattended boot, but the key sits on the root disk
  (weaker at-rest protection).

---

## 6. What's live

| Workflow | Schedule | Action |
|---|---|---|
| W3 Job Discovery | daily 06:00 | discover → dedupe → visa filter → LLM match → Notion |
| W4 Daily Digest | daily 08:00 | email + Telegram: matches + LLM spend |
| W1 Email Triage | every 30 min | Gmail unread → draft reply → Telegram Send/Discard |
| W2 Calendar Assist | hourly | detect meeting → Telegram Add/Ignore |
| W5 Approvals | polls 60s | resolve taps → send reply + delete draft / create event |
| error-alerts | on failure | Telegram alert (set as each workflow's Error Workflow) |

First real `/jobs/run` (verified): considered 300, new 287, eligible 3, **inserted 1**
to Notion (dropped: region 107, visa 177, score 2). LLM spend key B ≈ `$0.02`.

**Monitoring:** `curl localhost:8000/health` · `curl localhost:8000/budget/status`
· `docker compose -f docker-compose.yml -f docker-compose.hardened.yml -f docker-compose.telegram.yml logs -f`.

---

## 7. Security notes / outstanding

- **Unencrypted SSH key** at `C:\Users\ASUS\.ssh\hamid_nopass` (passphrase-stripped
  copy of `Hamid's Private.ppk`) was created for non-interactive automation.
  Anyone who reads that file gets root on the server. Delete it or move to a
  Pageant/agent flow when automation is done.
- Secrets and the LUKS passphrase were transmitted in a chat session — **rotate**
  if that channel isn't trusted (OpenAI keys, Notion token, Adzuna key, bot token,
  LUKS passphrase, n8n login).
- Hardening does **not** protect against a host root / docker-group user — they can
  read container memory and the docker socket regardless (see `docs/SECURITY.md`).
- Bot token is hardcoded in W5's `getUpdates` URL (fix #5) — rotate ⇒ update the
  workflow.
- Leftover `docker-compose.hardened.yml.bak` on the server (from the fix #2 edit) —
  remove when satisfied.
- `age`/SOPS at-rest encryption of `secrets/*` (SECURITY.md §2) is **not** set up.
- Firewall (`scripts/firewall.sh`) **intentionally not run** — it would `ufw deny
  incoming` and cut off the host's co-tenant services. Ports are localhost-bound
  already.
