# Agentic Job & Inbox Stack — Design Spec

**Date:** 2026-06-12
**Owner:** Hamid Jahani (`hamidjahani999@gmail.com`)
**Status:** Approved (brainstorming complete)

## 1. Goal

Self-hosted, Docker-based agentic stack on an Ubuntu server (server is **outside Iran** — no
sanctions/IP blocks server-side) that:

1. Triages Gmail and **drafts** replies (never auto-sends).
2. Assists with Google Calendar (proposes events from mail; creates only on approval).
3. Discovers academic + industry jobs across the web/job platforms, **matched to the owner's
   resume**, **filtered to visa-sponsorship / relocation-friendly** roles.
4. Inserts matched jobs into the existing Notion **Career Hub → Applications** database.

The owner is an Iranian national in Tehran seeking visa sponsorship to relocate. Target regions:
**Europe (EU + UK), Canada, Australia/NZ**. Tracks: **both academic** (PhD/PostDoc/Faculty) **and
industry** (ML Engineer / Data Scientist / NLP-GenAI / MLOps).

## 2. Owner profile (resume-derived, used by matcher)

- **Education:** M.Sc Statistics (Data Science), Tarbiat Modares (1st rank, GPA 4.0); B.Sc Statistics,
  Allameh Tabataba'i (1st rank).
- **Industry (~4 yr):** Snappfood (MLOps/ML Eng), RoomVU (DS/ML Eng — NER, RAG, LLM agents, voice/image
  on AWS SageMaker), Digikala (analyst).
- **Publications:** Cognitive Computation (2024, EEG/ADHD DL), J. Biostatistics (2025, U-Net brain-tumor
  segmentation), Elsevier book chapter, textbook *Mathematical Statistics with R*.
- **Skills:** Python, R, PySpark, SQL; PyTorch, TensorFlow, scikit-learn; transformers/LLMs, RAG, GenAI;
  FastAPI/Flask/gRPC; Docker, GitLab CI, Airflow, MLflow, Qdrant; AWS SageMaker; Spark/Hadoop.
- **Languages:** English C1 (TOEFL); Persian native.
- **Targeting note (explicit owner instruction):** *Ignore the CV "research interests" block.* Target
  **ML / Deep Learning / Generative AI in hot, high-growth fields** (incl. biomedical). The matcher
  weights skills + demonstrated impact, not the stated research-interests paragraph.

Two CV variants are inputs: `Jahani_CV_ATS.pdf` (academic) and `resume.pdf` (industry).

## 3. Architecture

Single `docker-compose.yml` on the Ubuntu host. Strict 12-factor: **all** config/secrets in `.env`
(documented in `.env.example`); nothing hardcoded; secrets also stored in the n8n credential vault.

### Containers

| Container | Role |
|---|---|
| **n8n** | Orchestrator, UI, cron scheduler, credential vault. Runs all workflows. |
| **postgres** | n8n's DB + app tables: `usage_ledger`, `seen_jobs`, `profile`. |
| **scraper** | FastAPI + Playwright sidecar. Called via HTTP only for sources lacking an API/RSS. |
| **caddy** *(optional, compose profile `proxy`)* | Reverse proxy + auto-HTTPS + basic-auth. Enabled only when a domain is configured (needed for Google OAuth callback). |

### External services (via API/OAuth, no container)

Gmail API, Google Calendar API (one Google Cloud OAuth client), Notion API (internal integration),
OpenAI (2 API keys), Telegram Bot API, job-board APIs (Adzuna, Arbeitnow, Jooble, EURAXESS, etc.).

### Portability (explicit requirement)

- Pure `docker compose` → runs on any Linux + Docker host (Hetzner / DigitalOcean / AWS / local).
  `docker compose up -d` brings up the whole stack.
- Named volumes for Postgres + n8n. `scripts/backup.sh` (pg_dump + `n8n export`) and
  `scripts/restore.sh`. **Migration = copy the dump + `.env` to a new host and `up`.**
- LLM access via swappable `OPENAI_BASE_URL` + model env vars → works with OpenAI, OpenRouter, Azure
  OpenAI, or a local Ollama (OpenAI-compatible) endpoint by changing env only.
- **Telegram long-poll is the default** → no public domain/HTTPS required. Caddy/HTTPS is opt-in
  (compose profile) for when a domain exists (Google OAuth callback needs HTTPS).
- No host-specific absolute paths; only relative bind mounts for config files.

## 4. Workflows (in n8n)

All workflows are authored/validated with the `n8n-mcp` tooling and exported as JSON under
`n8n/workflows/`. Importable on any fresh n8n instance.

- **W0 — Profile builder** (manual / on CV change): read CV PDFs → LLM extracts a structured profile
  JSON (skills, subfields, seniority, publications, target titles, languages, constraints) → store in
  Postgres `profile`. Consumed by W1 (reply context) and W3 (matching).
- **W1 — Email triage** (cron, every 30 min): Gmail fetch new/unread → LLM classify (category, urgency,
  needs-reply?) → if reply needed, draft in the owner's voice → **save as Gmail draft** (label
  `AI/Drafted`) → queue for digest + Telegram ping. **Never sends.**
- **W2 — Calendar assist** (on triage + daily 07:30 Tehran): detect meeting/interview requests → propose
  event (date/time/timezone) → **hold for approval** → on approve, create Google Calendar event. Daily
  agenda push.
- **W3 — Job discovery** (cron, daily 06:00 server):
  1. Query each source (API/RSS first; scraper sidecar fallback) using profile + target regions.
  2. Normalize → **dedupe** against `seen_jobs` and existing Notion rows (key = vacancy URL; fallback
     title+org).
  3. **Visa filter** (see §5).
  4. **Match engine:** LLM scores fit vs profile 0–100 + rationale; assigns Track, Tags, Priority.
  5. Above threshold → **insert Notion row** (Stage = "To apply") + add to digest.
- **W4 — Digest + approvals** (daily 08:00 Tehran): email digest to Gmail (new jobs + pending drafts,
  each with an approve link) **and** Telegram summary with inline approve/reject buttons → button hits an
  n8n webhook/long-poll handler → sends approved draft / confirms event / sets job priority.
- **LLM Call** (reusable sub-workflow): the single chokepoint for all LLM calls — enforces Budget Guard
  (§6), records usage, applies model fallback.
- **Budget reset** (cron, monthly): resets monthly counters / marks calendar boundary.

## 5. Visa-sponsorship filter (core value)

Layered, evidence-producing — not naive keyword matching:

1. **Official sponsor registers** (strong, legal signal): cross-check the hiring company against
   - **UK Home Office register of licensed sponsors** (public CSV) → presence ⇒ can sponsor Skilled
     Worker.
   - **Netherlands IND recognised sponsors** list.
   - **Germany** Make-it-in-Germany / known-sponsor lists.
2. **Source-native flags + JD scan:** Arbeitnow exposes a `visa_sponsorship` boolean; LLM/keyword scan of
   the JD for "visa sponsorship", "relocation", "Blue Card", "work permit", "international applicants".
3. **Academia = default-eligible:** universities routinely sponsor researcher visas → high-confidence
   unless the JD explicitly requires existing work authorization.

Each job stores a **visa-confidence label** + an **evidence snippet** in Notion Notes. Jobs failing the
filter (no sponsorship signal, non-target region, explicit work-auth requirement) are dropped.

## 6. Budget Guard (hard $8 per key, enforced in code)

The OpenAI API has no trusted built-in hard cap → enforce in code (dashboard limit set too, as
belt-and-suspenders).

- **Single chokepoint:** all LLM calls go through the `LLM Call` sub-workflow. No workflow calls OpenAI
  directly.
- **Usage ledger** (Postgres `usage_ledger`): logs `key_id, model, prompt_tokens, completion_tokens,
  cost_usd, ts` per call. Cost computed from a maintained price map (model → $/1M in, $/1M out) using the
  `usage` field returned on every response.
- **Pre-call gate:** sum the current calendar-month `cost_usd` for the key; if `≥ $7.50` (safety margin
  under $8) → block that key.
- **Fallback ladder near cap:** (1) downgrade to a cheaper model → (2) shift to the other key if it has
  room → (3) both exhausted ⇒ pause non-urgent work + Telegram alert.
- **Daily soft cap** ≈ `$8/30` per key (rolls over) → spreads spend across the month.
- **Monthly reset** on the calendar boundary.

Key split: **Key A** = triage + visa pre-filter (cheap model). **Key B** = match scoring + reply drafting
(stronger model). Ledger caps each at $8 independently.

## 7. Notion integration

Target: **Career Hub → Applications** data source (`collection://cd54c7e6-fca0-4234-b8fb-87745292ac83`).

Reuse existing properties: Position (title), Track, Stage (set "To apply"), Organization (relation),
Location, Vacancy link, Application email, Deadline, Priority (tiered by match score), Tags (mapped to
ML/AI/NLP/Data Science/…), Notes (rationale + visa evidence + JD summary).

**Add 4 new properties** (approved):

| Property | Type | Use |
|---|---|---|
| Match score | number | 0–100 fit vs profile |
| Visa support | select | Sponsors visa / Relocation support / Hires-intl (academia) / On sponsor register / Unclear |
| Source | select | EURAXESS, jobs.ac.uk, AcademicTransfer, Academic Positions, Nature, Adzuna, Arbeitnow, Relocate.me, Jooble, Other |
| Discovered | date | when the agent found it |

Inserts are **idempotent** (dedupe on Vacancy link via `seen_jobs`) so re-runs never duplicate rows.

## 8. Job sources

- **Academic:** EURAXESS (EU, API/RSS), jobs.ac.uk (UK, RSS), AcademicTransfer (NL, API), Academic
  Positions (EU), Nature Careers, THEunijobs; Canada/AU/NZ: UniversityAffairs.ca, seek.com.au, university
  HR feeds.
- **Industry:** Adzuna API (free tier; aggregates UK/EU/CA/AU boards), Arbeitnow API (EU/DE, visa flag),
  Jooble API, Remotive/RemoteOK (remote), Relocate.me (scrape — explicit relocation jobs).
- **Excluded:** LinkedIn / Indeed automated scraping (ToS prohibits; APIs closed). Adzuna covers much of
  their inventory legally. Owner may add LinkedIn manually.

## 9. Schedules (all env-configurable)

| Workflow | Cadence |
|---|---|
| W1 triage | every 30 min |
| W2 calendar agenda | daily 07:30 Tehran |
| W3 job discovery | daily 06:00 server |
| W4 digest | daily 08:00 Tehran |
| Telegram alerts | realtime as events occur |
| Budget reset | monthly (calendar boundary) |

## 10. Security & safety

- **Draft-only** email + **approval gate** before any send or calendar create. **No auto-apply** — jobs
  are only collected to Notion.
- Secrets in n8n credential vault + gitignored `.env`. `.env.example` is the only committed env file.
- When `proxy` profile is on: Caddy HTTPS + basic-auth; n8n never exposed raw; firewall opens 80/443 only.
  Default (no proxy): n8n bound to localhost, reached via SSH tunnel.
- Telegram bot **locked to the owner's chat ID** (allowlist) — only the owner can approve.
- Budget Guard hard-caps spend (§6).
- `DRY_RUN` env flag → safe test mode (logs intended actions; no sends, no calendar writes, no Notion
  writes).
- Scraping is API-first and polite (rate-limited, robots-aware); ToS-prohibited sources excluded.

## 11. Prerequisites (owner supplies via `.env` after build)

1. **Domain or DuckDNS** subdomain — only if enabling the `proxy` profile for Google OAuth HTTPS callback.
2. **Google Cloud OAuth client** (Gmail + Calendar scopes). Consent must be completed **from a non-Iran
   IP** (Google blocks Iran) — do it via the server / a VPN.
3. **Notion integration token** + share Career Hub with the integration.
4. **Telegram bot token** (BotFather) + owner chat ID.
5. **2 OpenAI API keys**, each intended for an $8/month ceiling (enforced by Budget Guard, not the API).

## 12. Error handling & testing

- n8n error-trigger workflow → Telegram alert on any workflow failure.
- Per-source try/catch in W3 (one board failing never fails the whole run).
- Idempotent Notion upsert keyed on Vacancy link.
- `DRY_RUN` mode for end-to-end safe rehearsal.
- Scraper service unit-tested with pytest; Notion writes validated against a single test row first.

## 13. Repository layout

```
.
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
├── Makefile
├── caddy/Caddyfile
├── db/init.sql                 # usage_ledger, seen_jobs, profile
├── scraper/                    # FastAPI + Playwright sidecar
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app.py
├── n8n/workflows/              # exported workflow JSON (W0–W4, LLM Call, budget reset)
├── scripts/{backup.sh,restore.sh}
└── docs/{SETUP.md,MIGRATION.md, superpowers/specs/...}
```

## 14. Out of scope (v1, YAGNI)

- Auto-sending email / auto-applying to jobs.
- Redis/queue mode for n8n (volume doesn't warrant it).
- LinkedIn/Indeed scraping.
- Multi-user support.
