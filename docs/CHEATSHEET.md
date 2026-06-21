# Job-Hunter — Cheatsheet

One-page operator reference. Deep setup → [GETTING-STARTED](GETTING-STARTED.md) ·
security model → [SECURITY.md](SECURITY.md) · server commands → [RUNBOOK](RUNBOOK.md).

---

## What it is

n8n (orchestration) + a FastAPI **worker** (all logic + LLM/Notion calls) + Postgres.
Daily it discovers ML/AI jobs, scores them against your CV with one LLM call, ranks
visa/relocation-friendly roles to the top, and writes matches to a Notion board.

```
sources ─► gather ─► dedup ─► region gate ─► visa gate ─► sort by visa conf
                                                              │
        Notion ◄─ rank (effective_score) ◄─ score (LLM, capped) ◄┘
```

---

## Production lives here

| | |
|---|---|
| Host | **192.168.1.48**, SSH as **`hamid`** (the `test`/`tararis` users can't reach `/home/hamid`) |
| Dir | `/home/hamid/Job-hunter` (files-only deploy via `scp`; **not** a git checkout) |
| Mode | **HARDENED** — secrets in `./secrets/*`, data on the LUKS mount `/mnt/agentdata` |
| Repo | `github.com/sheperd007/Job-hunter` (push from your machine, then scp to the box) |
| Ports | worker `127.0.0.1:8000`, n8n `127.0.0.1:5678` — localhost-only, tunnel to reach |

> ⚠️ **Always bring the stack up with the 3-file overlay.** Plain `docker compose up`
> uses the base file → worker loses `/run/secrets` (Notion 401) and postgres detaches
> from the LUKS bind. Define this once:

```bash
C='docker compose -f docker-compose.yml -f docker-compose.hardened.yml -f docker-compose.telegram.yml'
```

---

## Day-to-day commands  (run on the box, in `/home/hamid/Job-hunter`)

```bash
$C ps                                   # service status
$C logs -f --tail=100 worker            # follow worker logs
$C up -d --build worker                 # rebuild + restart worker after a code change
$C restart worker                       # restart only (re-reads secrets/env)
$C exec -T worker python -c "from worker.config import Settings as S; print(S())"   # effective config

curl -s localhost:8000/health                       # {"status":"ok","dry_run":false}
curl -s localhost:8000/budget/status                # {"a":1.2,"b":3.4}  USD this month per key
curl -s -XPOST localhost:8000/jobs/run | python3 -m json.tool   # manual discovery run (spends $, writes Notion)
```

### Worker HTTP endpoints
`GET /health` · `GET /budget/status` · `POST /jobs/run` (W3) · `GET /digest` (W4) ·
`POST /profile/build {cv_text}` · `POST /triage` (W1) · `POST /calendar/parse` (W2) ·
`POST /pending` / `POST /pending/{id}/resolve` (W5).

### DB peeks
```bash
$C exec -T postgres psql -U n8n -tAc "select source,count(*) from seen_jobs \
  where discovered::date=current_date and notion_page_url is not null group by source order by 2 desc;"
$C exec -T postgres psql -U n8n -tAc \
  "select count(*) filter(where notion_page_url is not null) inserted, \
          count(*) filter(where notion_page_url is null) rejected from seen_jobs;"
```
`seen_jobs`: dedup ledger (`vacancy_url` PK = canonical URL, `content_key` = org|title|region,
`notion_page_url` NULL ⇒ scored-but-rejected). Also: `profile`, `usage_ledger`, `pending_actions`.

---

## The funnel (run_discovery)

1. **gather** — round-robin interleave of sources (so the cap samples all).
2. **filter_new** — drop if canonical URL **or** `content_key` (org|title|region) already seen.
3. **region gate** — keep UK / EU / Canada / AU-NZ / Remote; drop US / Other.
4. **visa gate** — `assess()`: explicit "we don't sponsor" → **drop**; everything else → keep
   (soft gate). Verdict carries a confidence.
5. **sort** by visa confidence desc (register .9 > source-flag .85 > keyword .7 > academic .6 >
   Unclear .3) so the cap spends on signal-bearing jobs first.
6. **score** — one LLM call/job (fit score **+** visa intent), bounded by `MAX_MATCH_PER_RUN`.
   `score < min_score` (60) → mark seen, no Notion (won't re-score). `BudgetExhausted` → stop clean.
7. **reconcile + rank** — LLM visa intent upgrades only the "Unclear" bucket; `effective_score =
   clamp(raw + VISA_RANK_WEIGHT·(conf-0.5))` is written to Notion "Match score" (the sort key).

---

## Sources  (`gather_jobs`)

| Source | Cost | Notes |
|---|---|---|
| **Google Jobs** (Scrapingdog `/google_jobs`) | 1 credit/req | aggregates LinkedIn/Indeed/company sites. `GOOGLE_QUERY_CAP×5` countries credits/run (3×5=15). Uses `source_link` (direct board URL). Needs `scrapingdog_key`. |
| **Arbeitnow** | free | EU/Germany; native `visa_sponsorship` flag. |
| **Academic RSS** | free | jobs.ac.uk, EURAXESS (track=academic, default visa-eligible). |

*(Adzuna and the Indeed scraper were removed — Indeed's Scrapingdog endpoint 400s.)*

---

## Config knobs  (`.env` on the box; defaults in `worker/config.py`)

| Var | Default | Meaning |
|---|---|---|
| `DRY_RUN` | false | true = no LLM/Notion writes |
| `MONTHLY_CAP_USD` / `CAP_SAFETY_MARGIN_USD` | 10 / 9.5 | per-key budget; Budget Guard hard-stops key at the margin |
| `MAX_MATCH_PER_RUN` | 60 | LLM scorings per run (cost cap) |
| `SPONSOR_REGISTER_URL` | (empty) | `govuk:workers` auto-resolves the daily UK Home Office CSV; empty = off |
| `VISA_RANK_WEIGHT` | 20 | visa boost on the Notion sort score; 0 = ranking off |
| `LLM_VISA_MIN_CONF` | 0.6 | min LLM confidence to upgrade an "Unclear" verdict |
| `GOOGLE_QUERY_CAP` | 3 | distinct Google Jobs queries/country (credit guard) |
| `VISA_QUERY_SUFFIXES` | visa sponsorship, relocation | appended to the top query for visa-biased results |
| `SCRAPINGDOG_KEY` | (secret) | Google Jobs key (Roomvu company plan) |
| `TELEGRAM_CHAT_ID` | (env) | where the worker run-ping + n8n digest go |

**Secrets** (files in `./secrets/`, mounted at `/run/secrets`, **never** in git/.env):
`openai_key_a`, `openai_key_b`, `notion_token`, `scrapingdog_key`, `telegram_bot_token`,
`db_password`, `n8n_encryption_key`, `n8n_basic_auth_password`.
Write one with `printf` (no trailing newline) then `restart`:
```bash
printf '%s' 'VALUE' > secrets/<name> && chmod 444 secrets/<name> && $C restart worker
```

---

## n8n workflows (cron times = `Asia/Tehran`)

| WF | Trigger | Does |
|---|---|---|
| W1 Email Triage | on email | classify + draft reply (key A) |
| W2 Calendar Assist | on email | detect meeting → propose event |
| **W3 Job Discovery** | **06:00 daily** | POST worker `/jobs/run` |
| **W4 Daily Digest** | **08:00 daily** | GET `/digest` → email **+** Telegram |
| W5 Telegram Approvals | per-minute poll | one-tap approve/reject pending actions |

Workflows live in n8n's DB (import from `n8n/workflows/*.json` via the UI).

---

## Telegram

- **Digest** (email + TG) = n8n W4 at 08:00. **Run-finished ping** = the worker after each
  `/jobs/run` ([worker/notify.py](../worker/notify.py)).
- Bot **@HamidJobHunter_bot**, chat `8164243924`. **You must `/start` the bot once** or sends
  fail with `chat not found` (swallowed by `onError:continue` → you'd only get email).
- Iran DNS sinkholes `api.telegram.org` → pinned to `149.154.167.220` for n8n **and** worker in
  `docker-compose.telegram.yml`. If TG breaks, re-verify the IP.

---

## Cost (real, from the ledger)

| Item | Rate | Monthly |
|---|---|---|
| LLM match (gpt-4.1, key B) | $0.00365/job × ≤60/day | ~$3–7 · hard cap **$9.5** |
| LLM triage (gpt-4.1-mini, key A) | $0.0001/call | ~$0.4–1 · hard cap **$9.5** |
| Scrapingdog Google Jobs | ~300–450 credits/mo | **$0 marginal** (Roomvu 1M/mo plan; standalone Lite = $40/mo) |
| Adzuna(removed)/Arbeitnow/RSS/Notion/Telegram | free | $0 |
| Server (LAN box) | self-hosted | $0 cloud |

**Realistic ≈ $4–7/mo (just OpenAI). Hard ceiling $19/mo** (both keys maxed by the Budget Guard).

---

## Troubleshooting

| Symptom | Likely cause → fix |
|---|---|
| **0 new matches** | Check the `/jobs/run` funnel JSON. `dropped.visa` high → explicit-neg JD text; `dropped.region` high → US/Other; `capped` → backlog (rolls forward); `inserted 0` + scored 0 → empty profile or `DRY_RUN=true`. |
| **Notion writes 401 / `notion=False`** | Stack rebuilt with **base** compose → no `/run/secrets`. Bring up with the **3-file overlay**. |
| **No Telegram** | Bot never `/start`ed (`chat not found`); or pinned IP stale; or worker missing DNS pin / `telegram_bot_token`. |
| **Bad/"Not Found" Notion links** | Old pages from before the URL fix (canonical-stripped). New jobs store the real `source_link`. |
| **Budget exhausted** | Key hit `$9.5`. Raise `MONTHLY_CAP_USD`/`CAP_SAFETY_MARGIN_USD` (both code + `.env`), or wait for month reset. |
| **Google Jobs silent / 0** | `scrapingdog_key` unset/empty (source skipped), or Scrapingdog account out of credits. Test: `GET /google_jobs?api_key=…&query=…`. |
| **Duplicate jobs** | Same role at two URLs is collapsed by `content_key` (org|title|region); only genuinely different URLs+content slip through. |

---

## Common tasks

```bash
# Enable the UK sponsor register (gov.uk must be reachable from the box):
echo 'SPONSOR_REGISTER_URL=govuk:workers' >> .env && $C restart worker

# Change the budget cap (edit BOTH .env and worker/config.py default to stay consistent):
sed -i 's/^MONTHLY_CAP_USD=.*/MONTHLY_CAP_USD=15.0/' .env && $C up -d worker

# Rebuild your CV profile:
curl -s -XPOST localhost:8000/profile/build -H 'content-type: application/json' \
  --data "$(python3 -c 'import json;print(json.dumps({"cv_text":open("cv.txt").read()}))')"

# Deploy a code change from your machine (then rebuild on the box):
scp -p worker/<file>.py hamid@192.168.1.48:~/Job-hunter/worker/ && \
  ssh hamid@192.168.1.48 "cd ~/Job-hunter && $C up -d --build worker"
```

---

## Tests

```bash
python -m pytest -q          # 111 passing. Needs: pytest-asyncio respx psycopg fastapi
```
