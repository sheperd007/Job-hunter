# RUNBOOK — run on your Ubuntu server

Exact commands, top to bottom. Token/credential details: see the README
"Environment & credentials" section.

## 0. Server resources

| Load | vCPU | RAM | Disk | Notes |
|---|---|---|---|---|
| Minimum | 1 | 2 GB | 20 GB | works; n8n+Postgres+worker are light (RSS/JSON sources, no headless browser) |
| **Recommended** | **2** | **4 GB** | **25 GB** | comfortable headroom for n8n executions + Postgres |
| If you later add Playwright scraping | 2 | 4–8 GB | 30 GB | Chromium needs ~1 GB RAM/run |

Idle footprint ≈ n8n 300–500 MB · Postgres 150–250 MB · worker 120–180 MB.
**Must be a non-Iran host** (OpenAI + Google geoblock Iranian IPs). Egress to the
internet required.

## 1. Install Docker

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker $USER
# log out and back in so the group applies, then:
docker --version && docker compose version
```

## 2. Get the code onto the server

```bash
# option A — from GitHub:
git clone https://github.com/<you>/ai-job-agent.git && cd ai-job-agent
# option B — copy from your machine:
#   scp -r "ai-job-agent" user@server:~/   (then: cd ~/ai-job-agent)
```

## 3. Configure secrets

```bash
cp .env.example .env
nano .env        # fill every value — see README "Environment & credentials"
```

Keep `DRY_RUN=true` for now.

## 4. Launch the stack

```bash
docker compose up -d --build
docker compose ps                 # all services "running"/"healthy"
docker compose logs -f worker     # Ctrl-C to stop following
curl -s http://localhost:8000/health   # {"status":"ok","dry_run":true}
```

## 5. Open the n8n UI (it is bound to localhost on the server)

From your laptop, tunnel in:

```bash
ssh -L 5678:localhost:5678 user@server
# now open http://localhost:5678 in your browser; log in with N8N_BASIC_AUTH_*
```

In n8n:
1. **Credentials** → add: Gmail OAuth2, Telegram (bot token), Google Calendar OAuth2.
   - Gmail/Calendar: click "Sign in with Google" and complete consent **from a non-Iran IP**.
2. **Workflows → Import from File** → import all 6 files in `n8n/workflows/`.
3. Open each workflow, pick the credential on its Gmail/Telegram/Calendar nodes.
4. Each workflow → **Settings → Error Workflow → Error Alerts**.
5. **Activate** W1, W2, W3, W4, W5 (toggle top-right).

## 6. Build your résumé profile (once)

```bash
# put your CV text into cv.txt (paste from the PDF), then:
python3 - <<'PY' > profile.json
import json
print(json.dumps({"cv_text": open("cv.txt", encoding="utf-8").read()}))
PY
curl -s -X POST http://localhost:8000/profile/build \
  -H 'content-type: application/json' --data @profile.json | head
```

## 7. Dry-run, then go live

```bash
# trigger one discovery pass while DRY_RUN=true (no spend, no writes):
curl -s -X POST http://localhost:8000/jobs/run | python3 -m json.tool
# looks right? flip the switch:
sed -i 's/^DRY_RUN=true/DRY_RUN=false/' .env
docker compose up -d            # recreate with new env
```

## 8. Day-to-day

```bash
docker compose logs -f --tail=100        # watch
docker compose restart worker            # after editing worker code + rebuild
docker compose up -d --build worker      # rebuild worker image
bash scripts/backup.sh                   # dump DB to backups/
make down                                # stop everything
```

Check spend any time: `curl -s http://localhost:8000/budget/status`
→ `{"a": 1.23, "b": 0.40}` (USD this month per key; hard-stopped at
`CAP_SAFETY_MARGIN_USD`, default $9.5 of a $10 cap).

> **Hardened / shared host:** the commands above use the base compose file. On a
> multi-user host (secrets as files, encrypted-at-rest), bring the stack up with
> the 3-file overlay instead — see [SECURITY.md](SECURITY.md) and the
> [cheatsheet](CHEATSHEET.md):
> ```bash
> docker compose -f docker-compose.yml -f docker-compose.hardened.yml -f docker-compose.telegram.yml up -d --build
> ```
