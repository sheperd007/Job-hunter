from datetime import datetime, timezone
from fastapi import FastAPI
from pydantic import BaseModel
from worker.config import Settings
from worker.ledger import PostgresLedger, InMemoryLedger
from worker.llm import LLMGateway

app = FastAPI(title="job-agent-worker")
settings = Settings()


def _ledger():
    try:
        return PostgresLedger(settings.database_url)
    except Exception:
        return InMemoryLedger()


def _month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


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
    gw = LLMGateway(settings=settings, ledger=_ledger(), now_month=_month())
    return await gw.complete(req.task, req.messages)
