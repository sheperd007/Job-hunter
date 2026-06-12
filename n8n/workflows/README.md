# n8n workflows

Import in the n8n UI: **Workflows → ⋯ → Import from File**, pick a JSON here.

| File | What it does | Status |
|---|---|---|
| `W3-job-discovery.json` | Daily 06:00 cron → `POST {{WORKER_URL}}/jobs/run`. The worker pulls sources, dedupes, applies the visa filter, scores vs your profile, and inserts matches into Notion. | Phase 2 ✅ |
| W1 (email triage) | every 30 min → Gmail fetch → `worker /triage` → save Gmail draft | Phase 3 (todo) |
| W2 (calendar) | meeting/interview detection → propose event → approve → create | Phase 3 (todo) |
| W4 (digest + approvals) | daily digest email + Telegram approve/reject buttons | Phase 4 (todo) |

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
