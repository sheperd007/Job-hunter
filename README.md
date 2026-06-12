# Agentic Job & Inbox Stack

Self-hosted Docker stack that triages Gmail (draft-only), assists Google Calendar, discovers
**visa-sponsorship / relocation** jobs matched to your resume, and writes them to your Notion
**Career Hub → Applications** database. Hard per-key LLM spend caps are enforced in code.

> Design: [`docs/superpowers/specs/2026-06-12-agentic-job-stack-design.md`](docs/superpowers/specs/2026-06-12-agentic-job-stack-design.md)
> Plan: [`docs/superpowers/plans/2026-06-12-agentic-job-stack.md`](docs/superpowers/plans/2026-06-12-agentic-job-stack.md)

## Components

| Service | Role |
|---|---|
| `n8n` | Orchestrator + UI + cron + credential vault (thin layer). |
| `worker` | Python/FastAPI business logic: budget-guarded LLM gateway, job sources, dedupe, visa filter, matcher, Notion upsert. |
| `postgres` | n8n DB + `usage_ledger`, `seen_jobs`, `profile`. |
| `caddy` | Optional reverse proxy + HTTPS + basic-auth (compose profile `proxy`). |

## Quickstart (on the Ubuntu server)

```bash
cp .env.example .env        # then fill in secrets (see Prerequisites)
docker compose up -d --build
# n8n UI: http://localhost:5678  (localhost-bound by default; SSH-tunnel in, or use the proxy profile)
```

Import the workflows from `n8n/workflows/` in the n8n UI, complete the Google/Notion/Telegram
credentials, and **keep `DRY_RUN=true` until you've verified** drafts and Notion writes look right.

### Public access (optional, needed for Google OAuth callback)

```bash
# set DOMAIN + N8N_BASIC_AUTH_PASSWORD_HASH in .env  (caddy hash-password)
docker compose --profile proxy up -d --build
```

## Prerequisites (fill into `.env`)

1. **Domain / DuckDNS** — only if using the `proxy` profile for Google OAuth HTTPS callback.
2. **Google Cloud OAuth** (Gmail + Calendar) — complete consent **from a non-Iran IP** (Google blocks Iran): do it via the server or a VPN.
3. **Notion integration token** — create at notion.so/my-integrations, then share the Career Hub with it.
4. **Telegram bot token** (BotFather) + your chat ID.
5. **2 OpenAI API keys** — `OPENAI_KEY_A`, `OPENAI_KEY_B`. The $8/key ceiling is enforced by the worker's Budget Guard.

## Budget Guard

All LLM calls go through the worker's single `LLMGateway`. It logs every call's cost to
`usage_ledger`, blocks a key once its calendar-month spend reaches `CAP_SAFETY_MARGIN_USD` ($7.50),
falls back to the other key / a cheaper model, and alerts when both are exhausted. Provider is
swappable via `OPENAI_BASE_URL` (OpenAI / OpenRouter / Azure / local Ollama).

## Migration (portability)

```bash
make backup                         # writes backups/db-<stamp>.sql
# copy that dump + your .env to the new host, then:
make restore DUMP=backups/db-<stamp>.sql
make up
```

## Development

```bash
py -m venv .venv && .venv/Scripts/python -m pip install -r worker/requirements.txt
make test            # or: python -m pytest -q
```

## Safety

- Email is **draft-only**; calendar events and outbound replies require explicit approval (Telegram / digest).
- No auto-apply — jobs are only collected to Notion.
- Secrets live in `.env` (gitignored) + the n8n credential vault. Only `.env.example` is committed.
