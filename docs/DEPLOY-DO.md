# Deploy on DigitalOcean App Platform (app-from-repo, no server admin)

App Platform runs **outside Iran** → OpenAI, Google and global job boards are
reachable. It deploys our repo as *components* (no `docker compose`), gives free
HTTPS + a domain, and uses a **Managed Postgres** instead of a container volume.

> ⚠️ Account caveat: DigitalOcean prohibits Iran (US sanctions). You need a
> **foreign card + non-Iran billing address** to open/pay the account. The
> running app is fine; only signup/payment from Iran is blocked.

## One-time

1. **Push this repo to GitHub** (App Platform deploys from GitHub/GitLab):
   ```bash
   git remote add origin git@github.com:<you>/ai-job-agent.git
   git push -u origin master
   ```
2. Edit `.do/app.yaml` → set both `github.repo` to `<you>/ai-job-agent`.

## Create the app

- UI: https://cloud.digitalocean.com/apps → **Create App** → **Import from App Spec** → paste `.do/app.yaml`.
- or CLI: `doctl apps create --spec .do/app.yaml`

This provisions: `worker` (internal), `n8n` (public, HTTPS), a Managed Postgres
`db`, and a `migrate` PRE_DEPLOY job that creates our tables.

## Set secrets (App → Settings → component → Environment Variables)

| Secret | Where | Value |
|---|---|---|
| `OPENAI_KEY_A`, `OPENAI_KEY_B` | worker | your two keys ($8 cap enforced in code) |
| `NOTION_TOKEN` | worker | Notion internal integration token |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | worker | from developer.adzuna.com |
| `N8N_ENCRYPTION_KEY` | n8n | random 32+ chars — **keep stable** or saved creds break |
| `N8N_BASIC_AUTH_USER`, `N8N_BASIC_AUTH_PASSWORD` | n8n | login for the n8n UI |

Keep `DRY_RUN=true` until you've verified drafts + Notion writes.

## After first deploy

1. Open the n8n URL (the app's domain) → log in with the basic-auth creds.
2. Add credentials in n8n: **Google (Gmail+Calendar OAuth)**, **Notion**, **Telegram**.
   - Google OAuth redirect: `https://<app-domain>/rest/oauth2-credential/callback`.
   - Complete Google consent from a **non-Iran IP**.
3. Import workflows from `n8n/workflows/`.
4. Flip `DRY_RUN=false` when ready to allow real Gmail drafts + Notion inserts.

## How components talk

- n8n → worker over the private network at `${worker.PRIVATE_URL}` (env `WORKER_URL`).
- worker → Postgres via `${db.DATABASE_URL}` (SSL required, already set).

## Notes

- No Caddy here — App Platform terminates TLS.
- State lives in Managed Postgres (n8n workflows/creds + our `usage_ledger`,
  `seen_jobs`, `profile`). Components are otherwise stateless → safe to redeploy.
- Migrating off DO later: the same repo runs anywhere via `docker compose up -d`
  (see `README.md`); export data with `make backup`.
