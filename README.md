# Agentic Job & Inbox Stack

A self-hosted, Dockerized agent that helps you land a visa-sponsored job abroad:

- **Job discovery** — scans job APIs + academic feeds daily, dedupes, keeps only
  **visa-sponsorship / relocation** roles, scores each against your résumé, and
  writes the good matches into your **Notion Career Hub → Applications**.
- **Email triage** — reads new Gmail, drafts replies in your voice, and pings you
  on Telegram with one-tap **Send / Discard** (nothing sends until you tap).
- **Calendar** — spots meeting/interview requests and offers one-tap
  **Add to calendar**.
- **Daily digest** — emails + Telegrams the day's new matches and your LLM spend.
- **Hard cost cap** — two OpenAI keys, **$8/month each, enforced in code**.

> Design: [`docs/superpowers/specs/`](docs/superpowers/specs/) · Plan:
> [`docs/superpowers/plans/`](docs/superpowers/plans/) · Run it:
> [`docs/RUNBOOK.md`](docs/RUNBOOK.md)

## Architecture

| Service | Role |
|---|---|
| **n8n** | Orchestrator: cron, Gmail/Calendar/Telegram nodes, approval buttons, credential vault. |
| **worker** (Python/FastAPI) | All logic: budget-guarded LLM gateway, job sources, dedupe, visa filter, résumé matcher, Notion writer, triage, digest, approvals. |
| **postgres** | n8n data + `usage_ledger`, `seen_jobs`, `profile`, `pending_actions`. |
| **caddy** *(optional)* | Reverse proxy + HTTPS (compose profile `proxy`). |

n8n calls the worker over the internal network; the worker is the brain.

## Deploy targets

- **Any Linux + Docker host** (your Ubuntu server / Hetzner / etc.) — see
  [`docs/RUNBOOK.md`](docs/RUNBOOK.md). Sizing: **2 vCPU / 4 GB / 25 GB** recommended
  (1 vCPU / 2 GB works).
- **DigitalOcean App Platform** (app-from-repo, no server admin) —
  [`docs/DEPLOY-DO.md`](docs/DEPLOY-DO.md).
- ⚠️ **Never host on Iranian infra (e.g. ArvanCloud)** — an Iranian outbound IP is
  geoblocked by OpenAI and Google, which kills the brain + Gmail/Calendar.

## Quickstart

```bash
cp .env.example .env        # fill it in — see "Environment & credentials" below
docker compose up -d --build
curl -s http://localhost:8000/health    # {"status":"ok","dry_run":true}
# open n8n: ssh -L 5678:localhost:5678 user@server  ->  http://localhost:5678
```

Keep `DRY_RUN=true` until you've watched one run, then set it `false`.

---

## Environment & credentials — how to get each

Everything lives in `.env` (copy from `.env.example`). Below is every value and
exactly where to get it. Google OAuth is the only one that lives in the n8n UI
(credential vault), not in `.env`.

### 1. OpenAI — `OPENAI_KEY_A`, `OPENAI_KEY_B`

The brain. **Two separate keys** so each can be capped at $8/month.

1. Go to <https://platform.openai.com/api-keys> (sign in / add a payment method).
2. **Create new secret key** twice → copy each into `OPENAI_KEY_A` and `OPENAI_KEY_B`.
3. Recommended: under **Settings → Limits / Projects**, also set a hard monthly
   budget per project as a backstop (the worker enforces $8 in code regardless).
4. Leave `OPENAI_BASE_URL=https://api.openai.com/v1`. (Swap it for OpenRouter,
   Azure OpenAI, or a local Ollama endpoint if you ever want a different provider.)

> `MODEL_TRIAGE=gpt-4.1-mini` (cheap, key A) and `MODEL_MATCH=gpt-4.1` (key B) are
> sensible defaults. Estimated spend at this volume: ~$5–15/mo total.

### 2. Notion — `NOTION_TOKEN`

Lets the worker write job rows into your Career Hub.

1. Go to <https://www.notion.so/my-integrations> → **New integration** →
   type **Internal** → create → copy the **Internal Integration Secret** into
   `NOTION_TOKEN`.
2. Open your **Career Hub** page in Notion → top-right **···** → **Connections** →
   **Connect to** → pick your integration. (This grants it access to the
   Applications database.)
3. `NOTION_APPLICATIONS_DB=70b08f56f7fc4825b9e45993a409cb11` is already set (your
   Applications database). The 4 extra properties — Match score, Visa support,
   Source, Discovered — are already added.

### 3. Telegram — `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

For the daily digest + one-tap approvals.

1. In Telegram, open **@BotFather** → `/newbot` → follow prompts → copy the bot
   token into `TELEGRAM_BOT_TOKEN`.
2. Send any message to your new bot (search its username, tap Start).
3. Get your chat id: open
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser → find
   `"chat":{"id":<NUMBER>}` → put `<NUMBER>` in `TELEGRAM_CHAT_ID`.
   (Or message **@userinfobot**, which replies with your id.)
4. In n8n, create a **Telegram** credential with the same bot token and select it
   on the Telegram nodes.

### 4. Google (Gmail + Calendar) — n8n credential, **not** an `.env` value

1. <https://console.cloud.google.com/> → create a project.
2. **APIs & Services → Library** → enable **Gmail API** and **Google Calendar API**.
3. **OAuth consent screen** → External → add your Gmail as a **Test user**.
4. **Credentials → Create credentials → OAuth client ID → Web application**.
   - Authorized redirect URI:
     `http://localhost:5678/rest/oauth2-credential/callback`
     (or `https://<your-domain>/rest/oauth2-credential/callback` with the proxy).
   - Copy the **Client ID** + **Client secret**.
5. In n8n, create **Gmail OAuth2 API** and **Google Calendar OAuth2 API**
   credentials with that client id/secret → click **Sign in with Google** and
   consent. **Do this from a non-Iran IP** (Google blocks Iran).
6. `OWNER_EMAIL` = your Gmail address (where the digest is sent).
   `GOOGLE_CALENDAR_ID=primary` (or a specific calendar id from Calendar settings).

### 5. Adzuna (job source) — `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`

1. <https://developer.adzuna.com/> → register → create an app → copy **app_id**
   and **app_key**. Free tier is plenty.
   (Arbeitnow + EURAXESS + jobs.ac.uk need no key.)

### 6. n8n / infra

| Var | What |
|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | pick your own; `DATABASE_URL` must match |
| `N8N_BASIC_AUTH_USER` / `N8N_BASIC_AUTH_PASSWORD` | login for the n8n UI |
| `WORKER_URL` | `http://worker:8000` (compose internal hostname) |
| `TZ` | `Asia/Tehran` |
| `DRY_RUN` | `true` until verified, then `false` |

---

## Budget Guard

Every LLM call goes through the worker's single `LLMGateway`. It logs each call's
cost to `usage_ledger`, blocks a key once its month spend reaches **$7.50** (safety
margin under $8), falls back to the other key / a cheaper model, and alerts when
both are exhausted. Check it any time:

```bash
curl -s http://localhost:8000/budget/status   # {"a": 1.23, "b": 0.40}
```

## Safety

- Email is **draft-only**; replies + calendar events require a Telegram tap. Jobs
  only go to Notion (no outbound action). Approvals are idempotent (no double-send).
- Secrets live in `.env` (gitignored) + the n8n credential vault. Only
  `.env.example` is committed.
- `DRY_RUN=true` → discovers + filters but spends nothing and writes nothing.

## Migration / portability

```bash
make backup                                   # backups/db-<stamp>.sql
# copy the dump + your .env to a new host, then:
make restore DUMP=backups/db-<stamp>.sql && make up
```

## Development

```bash
py -m venv .venv && .venv/Scripts/python -m pip install -r worker/requirements.txt
python -m pytest -q        # 60 tests
```

Worker endpoints: `/health` `/budget/status` `/llm/complete` `/jobs/run`
`/profile/build` `/triage` `/calendar/parse` `/digest` `/pending`
`/pending/{id}/resolve`.
