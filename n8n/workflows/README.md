# n8n workflows

Import in the n8n UI: **Workflows → ⋯ → Import from File**, pick a JSON here.

| File | What it does | Status |
|---|---|---|
| `W3-job-discovery.json` | Daily 06:00 cron → `POST {{WORKER_URL}}/jobs/run`. The worker pulls sources, dedupes, applies the visa filter, scores vs your profile, and inserts matches into Notion. | Phase 2 ✅ |
| `W1-email-triage.json` | Every 30 min → Gmail get unread → `worker /triage` → if needs reply, **save a Gmail draft** (never sends). | Phase 3 ✅ |
| `W2-calendar-assist.json` | Hourly → Gmail get unread → `worker /calendar/parse` → if a meeting/interview is detected, surface a proposal (event creation is gated behind W4 approval). | Phase 3 ✅ |
| `W4-daily-digest.json` | Daily 08:00 → `worker /digest` → emails you the day's new matches + LLM spend, and sends the same to Telegram. | Phase 4 ✅ |
| `error-alerts.json` | Error Trigger on any workflow failure → Telegram alert. Set this as the **Error Workflow** in each workflow's Settings. | Phase 4 ✅ |

W4 needs env `OWNER_EMAIL` + `TELEGRAM_CHAT_ID`, and a **Telegram** credential (bot token) on the Telegram nodes.

> Approvals are intentionally lightweight: email is **draft-only** (open the Gmail
> draft and hit send), jobs land in Notion (no action needed), and calendar events
> are surfaced as proposals. One-tap Telegram approve/reject is a future enhancement.

## Credentials (set in the n8n UI after import)

W1/W2 need a **Gmail OAuth2** credential — open each Gmail node and select/create it.
Imported workflows don't carry credentials; n8n will prompt you to pick one.

## Requirements

- Env var `WORKER_URL` must point at the worker service:
  - docker compose: `http://worker:8000`
  - DigitalOcean App Platform: bound automatically via `${worker.PRIVATE_URL}`
- Keep `DRY_RUN=true` on the worker until you've watched one run: in dry mode the
  worker discovers + filters but performs **no** LLM spend and **no** Notion writes,
  and returns the counts it *would* have inserted.

## First run (manual test)

Open `W3 - Job Discovery` and click **Execute Workflow** to trigger it once without
waiting for 06:00. Inspect the HTTP node output: `{considered, new, eligible,
inserted, dropped, items}`.
