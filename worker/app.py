from datetime import datetime, timezone
from fastapi import FastAPI
from pydantic import BaseModel
from worker.config import Settings
from worker.ledger import PostgresLedger, InMemoryLedger
from worker.llm import LLMGateway
from worker.dedupe import PostgresSeenStore
from worker.notion import create_page
from worker.pipeline import run_discovery, gather_jobs
from worker.profile_build import build_profile
from worker.triage import triage_email
from worker.calendar_parse import parse_event
from worker.digest import build_digest

app = FastAPI(title="job-agent-worker")
settings = Settings()


def _ledger():
    try:
        return PostgresLedger(settings.database_url)
    except Exception:
        return InMemoryLedger()


def _month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _gateway():
    return LLMGateway(settings=settings, ledger=_ledger(), now_month=_month())


def _load_profile() -> dict:
    try:
        import psycopg
        with psycopg.connect(settings.database_url) as conn:
            row = conn.execute("SELECT data FROM profile WHERE id = 1").fetchone()
        return row[0] if row else {}
    except Exception:
        return {}


def _save_profile(data: dict) -> None:
    import json
    import psycopg
    with psycopg.connect(settings.database_url) as conn:
        conn.execute(
            "INSERT INTO profile (id, data) VALUES (1, %s) "
            "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, updated = now()",
            (json.dumps(data),),
        )


@app.get("/health")
def health():
    return {"status": "ok", "dry_run": settings.dry_run}


@app.get("/budget/status")
def budget_status():
    return {k: v.month_usd for k, v in _ledger().month_spend(_month()).items()}


class CompleteReq(BaseModel):
    task: str
    messages: list[dict]


@app.post("/llm/complete")
async def llm_complete(req: CompleteReq):
    return await _gateway().complete(req.task, req.messages)


@app.post("/jobs/run")
async def jobs_run():
    """W3 entrypoint: discover -> filter -> visa -> match -> Notion."""
    store = PostgresSeenStore(settings.database_url)
    profile = _load_profile()
    discovered = _today()
    jobs = await gather_jobs(settings)

    async def notion_create(job, m, v, *, discovered):
        return await create_page(
            job, m, v, token=settings.notion_token,
            database_id=settings.notion_applications_db,
            version=settings.notion_version, discovered=discovered,
            dry_run=settings.dry_run)

    return await run_discovery(
        jobs=jobs, profile=profile, gateway=_gateway(), store=store,
        notion_create=notion_create, discovered=discovered,
        dry_run=settings.dry_run)


class ProfileReq(BaseModel):
    cv_text: str


@app.post("/profile/build")
async def profile_build_ep(req: ProfileReq):
    data = await build_profile(req.cv_text, _gateway())
    if data and not settings.dry_run:
        _save_profile(data)
    return {"saved": bool(data) and not settings.dry_run, "profile": data}


@app.post("/triage")
async def triage_ep(email: dict):
    """W1: classify a Gmail message + draft a reply (draft-only; n8n saves it)."""
    return await triage_email(email, _gateway())


@app.post("/calendar/parse")
async def calendar_ep(email: dict):
    """W2: detect a meeting/interview request + propose an event (no auto-create)."""
    return await parse_event(email, _gateway())


def _recent_jobs(date: str) -> list[dict]:
    try:
        import psycopg
        with psycopg.connect(settings.database_url) as conn:
            rows = conn.execute(
                "SELECT title, vacancy_url, source, notion_page_url FROM seen_jobs "
                "WHERE discovered::date = %s ORDER BY discovered DESC", (date,),
            ).fetchall()
        return [{"title": t, "url": u, "source": s, "notion_page_url": n}
                for (t, u, s, n) in rows]
    except Exception:
        return []


@app.get("/digest")
def digest_ep():
    """W4: assemble the daily digest (email HTML + Telegram text)."""
    date = _today()
    budget = {k: v.month_usd for k, v in _ledger().month_spend(_month()).items()}
    return build_digest(jobs=_recent_jobs(date), budget=budget, date=date)
