# n8n workflows

Import in the n8n UI: **Workflows -> ... -> Import from File**, pick a JSON here.

| File | What it does | Status |
|---|---|---|
| `W3-job-discovery.json` | Daily 06:00 -> `POST {{WORKER_URL}}/jobs/run`. Worker pulls sources, dedupes, visa-filters, scores vs your profile, inserts matches into Notion. | ✅ |
| `W1-email-triage.json` | Every 30 min -> Gmail get unread -> `worker /triage` -> if needs reply, save a Gmail draft + store a pending action + Telegram message with **Send / Discard** buttons. | ✅ |
| `W2-calendar-assist.json` | Hourly -> Gmail get unread -> `worker /calendar/parse` -> if a meeting is detected, store a pending action + Telegram **Add to calendar / Ignore** buttons. | ✅ |
| `W4-daily-digest.json` | Daily 08:00 -> `worker /digest` -> emails you the day's matches + LLM spend, same to Telegram. | ✅ |
| `W5-telegram-approvals.json` | **Telegram Trigger** on a button tap -> `worker /pending/{id}/resolve` (idempotent) -> if approved: send the reply + delete the draft, or create the calendar event. | ✅ |
| `error-alerts.json` | Error Trigger on any workflow failure -> Telegram alert. Set as the **Error Workflow** in each workflow's Settings. | ✅ |

## Requirements

- Env: `WORKER_URL` (compose: `http://worker:8000`), `TELEGRAM_CHAT_ID`, `OWNER_EMAIL`, `GOOGLE_CALENDAR_ID`.
- Credentials to attach in the UI after import:
  - **Gmail OAuth2** -> W1, W2, W5 Gmail nodes
  - **Telegram** bot token -> W1, W2, W4, W5, error-alerts Telegram nodes
  - **Google Calendar OAuth2** -> W5 "Create event"
- Keep `DRY_RUN=true` on the worker until you've watched one run.

## One-tap approval flow

Nothing sends or touches your calendar until you tap a button in Telegram.
W1 saves a Gmail draft (so you can edit it) and pings you with **Send / Discard**;
tapping **Send** sends the reply and deletes the draft, **Discard** removes it.
W2 pings you with **Add to calendar / Ignore**. Resolution is idempotent — a
double-tap will not double-send (the worker only acts on the first resolve).

Job matches need no approval — they go straight to Notion.

## First run (manual test)

Open `W3 - Job Discovery` and click **Execute Workflow** to trigger once. Inspect
the HTTP node output: `{considered, new, eligible, inserted, dropped, items}`.
