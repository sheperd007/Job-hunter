# Getting started — credentials, launch, and commands

A complete walkthrough: get every credential, put it in place, launch (normal or
hardened), finish setup in n8n, and the commands you'll use day to day.

- Run it on a **non-Iran host** (OpenAI + Google geoblock Iranian IPs).
- Sizing: 2 vCPU / 4 GB / 25 GB recommended (1 vCPU / 2 GB minimum).

---

## 0. Checklist

| You need | For | Where in this guide |
|---|---|---|
| 2 × OpenAI API keys | the brain ($8/mo cap each) | §1.1 |
| Notion integration token | writing jobs to Career Hub | §1.2 |
| Telegram bot token + chat id | digest + one-tap approvals | §1.3 |
| Google OAuth client (Gmail+Calendar) | email + calendar | §1.4 |
| Adzuna app id + key | a job source | §1.5 |

---

## 1. Get the credentials

### 1.1 OpenAI (two keys)
1. Sign in at <https://platform.openai.com> and add a payment method.
2. **API keys → Create new secret key** — do it **twice**. Copy both
   (`OPENAI_KEY_A`, `OPENAI_KEY_B`).
3. Optional backstop: **Settings → Limits** → set a monthly budget. (The worker
   enforces $8/key in code regardless.)

### 1.2 Notion
1. <https://www.notion.so/my-integrations> → **New integration** → **Internal** →
   **Save** → copy the **Internal Integration Secret** → `NOTION_TOKEN`.
2. Open your **Career Hub** page → top-right **···** → **Connections** →
   **Connect to** → select your integration. (Grants access to the Applications DB.)
3. Nothing else — `NOTION_APPLICATIONS_DB` is already set and the 4 extra
   properties (Match score, Visa support, Source, Discovered) already exist.

### 1.3 Telegram
1. In Telegram, message **@BotFather** → `/newbot` → pick a name + username → copy
   the token → `TELEGRAM_BOT_TOKEN`.
2. Open your new bot and tap **Start** (send any message).
3. Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser → find
   `"chat":{"id":<NUMBER>}` → `TELEGRAM_CHAT_ID = <NUMBER>`.
   (Alternative: message **@userinfobot**, it replies with your id.)

### 1.4 Google (Gmail + Calendar)
This one is set up **inside n8n** (the client id/secret are not `.env` values).
1. <https://console.cloud.google.com> → create a project.
2. **APIs & Services → Library** → enable **Gmail API** + **Google Calendar API**.
3. **OAuth consent screen** → External → add your Gmail as a **Test user**.
4. **Credentials → Create credentials → OAuth client ID → Web application**:
   - Authorized redirect URI: `http://localhost:5678/rest/oauth2-credential/callback`
     (or `https://<domain>/rest/oauth2-credential/callback` with the proxy).
   - Copy **Client ID** + **Client secret** (used in §4.1).
5. `OWNER_EMAIL` = your Gmail. `GOOGLE_CALENDAR_ID = primary`.

### 1.5 Adzuna
1. <https://developer.adzuna.com> → register → create an app → copy **app_id** +
   **app_key** → `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`. (Free tier is plenty;
   Arbeitnow + EURAXESS + jobs.ac.uk need no key.)

---

## 2. Put the credentials in place

### Normal mode (single-user host) — use `.env`
```bash
cp .env.example .env
nano .env          # fill OPENAI_KEY_A/B, NOTION_TOKEN, TELEGRAM_*, ADZUNA_*, OWNER_EMAIL, passwords
```

### Hardened mode (shared host) — use `./secrets/*` files
Keep `.env` **secret-free**; put secrets in files instead (see
[`secrets/README.md`](../secrets/README.md)):
```bash
umask 077
printf '%s' 'sk-...A...'           > secrets/openai_key_a
printf '%s' 'sk-...B...'           > secrets/openai_key_b
printf '%s' 'secret_...'           > secrets/notion_token
printf '%s' '...adzuna_app_key...' > secrets/adzuna_app_key
printf '%s' 'a-strong-db-pass'     > secrets/db_password
openssl rand -hex 24               > secrets/n8n_encryption_key
printf '%s' 'n8n-ui-password'      > secrets/n8n_basic_auth_password
chmod 600 secrets/*
# ADZUNA_APP_ID, OWNER_EMAIL, GOOGLE_CALENDAR_ID, TZ stay in .env (not secret)
```

---

## 3. Launch

### 3a. Normal
```bash
docker compose up -d --build
curl -s http://localhost:8000/health        # {"status":"ok","dry_run":true}
```

### 3b. Hardened (firewall → optional LUKS → secrets → up)
```bash
make firewall                                # inbound = SSH only
# optional: encrypt data at rest
sudo apt install -y cryptsetup
DATA_DIR=/mnt/agentdata make luks-init       # one time (asks a passphrase)
echo 'DATA_DIR=/mnt/agentdata' >> .env
# launch with secrets-as-files + container hardening (one command):
DATA_DIR=/mnt/agentdata make harden-up
curl -s http://localhost:8000/health
# encrypt the secret files at rest, then remove the age key from the box:
AGE_RECIPIENT=age1... make secrets-encrypt
```
After a **reboot**: `DATA_DIR=/mnt/agentdata make luks-open && DATA_DIR=/mnt/agentdata make harden-up`.

> Full hardening rationale + the root-co-tenant caveat: [`docs/SECURITY.md`](SECURITY.md).

---

## 4. Finish setup in n8n

Reach the UI (it's bound to localhost on the server):
```bash
ssh -L 5678:localhost:5678 user@server       # then open http://localhost:5678
```
Log in with `N8N_BASIC_AUTH_USER` / password.

### 4.1 Add credentials (Credentials → New)
- **Gmail OAuth2 API** and **Google Calendar OAuth2 API** — paste the Client ID +
  Secret from §1.4, click **Sign in with Google**, consent **from a non-Iran IP**.
- **Telegram** — paste the bot token from §1.3.

### 4.2 Import + wire workflows
1. **Workflows → Import from File** → import all 6 in `n8n/workflows/`.
2. Open each → select your credential on its Gmail / Telegram / Calendar nodes.
3. Each workflow → **Settings → Error Workflow → Error Alerts**.
4. **Activate** W1, W2, W3, W4, W5.

### 4.3 Build your résumé profile (once)
```bash
# paste your CV text into cv.txt, then:
python3 - <<'PY' > profile.json
import json; print(json.dumps({"cv_text": open("cv.txt", encoding="utf-8").read()}))
PY
curl -s -X POST http://localhost:8000/profile/build \
  -H 'content-type: application/json' --data @profile.json | head
```

### 4.4 Dry-run, then go live
```bash
curl -s -X POST http://localhost:8000/jobs/run | python3 -m json.tool   # no spend/writes
# happy with it? turn off dry run:
sed -i 's/^DRY_RUN=true/DRY_RUN=false/' .env
docker compose up -d            # or: make harden-up
```

---

## 5. Useful commands

```bash
# health & spend
curl -s http://localhost:8000/health
curl -s http://localhost:8000/budget/status        # {"a":1.2,"b":0.4}  USD this month/key

# manual triggers (handy for testing)
curl -s -X POST http://localhost:8000/jobs/run | python3 -m json.tool
curl -s http://localhost:8000/digest | python3 -m json.tool

# logs / status
make logs                 # or: make harden-logs
docker compose ps
docker compose logs -f worker

# lifecycle
make up / make down                 # normal
make harden-up / make harden-down   # hardened
docker compose up -d --build worker # rebuild just the worker after a code change

# data
make backup                         # dump DB to backups/
make restore DUMP=backups/db-<stamp>.sql

# tests (dev machine)
make test                           # 63 passing
```

---

## 6. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `/health` shows `dry_run:true` but you set false | recreate: `docker compose up -d` (env changes need a recreate) |
| Jobs found but 0 inserted | still in DRY_RUN, or all below match threshold / failed the visa filter — check `/jobs/run` `dropped` counts |
| n8n Gmail node "no credential" | attach the Gmail OAuth2 credential to the node (§4.1–4.2) |
| Google sign-in blocked | you're on an Iran IP — do OAuth via the server / a non-Iran VPN |
| Telegram buttons do nothing | W5 not active, or Telegram credential missing on W5 nodes |
| `harden-up` warns "NOT a mountpoint" | run `make luks-open` first (data would otherwise land unencrypted) |
| Budget alert "both keys exhausted" | month cap hit ($8×2); resets on the 1st, or raise `CAP_SAFETY_MARGIN_USD` |
