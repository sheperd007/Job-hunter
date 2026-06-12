# Agentic Job & Inbox Stack — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A portable, Docker-based agentic stack that triages Gmail (draft-only), assists Google Calendar, discovers visa-sponsorship/relocation jobs matched to the owner's resume, and writes them to Notion Career Hub — with hard per-key LLM spend caps enforced in code.

**Architecture:** n8n is the thin orchestrator (cron, Gmail/Calendar/Notion/Telegram nodes, approval UI, credential vault). A Python `worker` (FastAPI) owns all business logic (LLM gateway + budget guard, job sources, dedupe, visa filter, match scoring, Notion upsert). Postgres backs both. Everything is 12-factor (`.env`), runs via `docker compose up -d`, and migrates by moving a DB dump + `.env`.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, httpx, pydantic-settings, psycopg (v3), pytest; n8n; Postgres 16; Playwright (Phase 2); Docker Compose; Caddy (optional proxy profile).

**Build order:** Phase 1 (this plan, full detail) → Phase 2 Job Discovery → Phase 3 Email/Calendar → Phase 4 Digest/Approvals. Each phase ships working, testable software. Phases 2–4 are scoped in the Roadmap and get their own detailed plans when reached.

---

## File structure (Phase 1)

```
worker/
  __init__.py
  config.py        # pydantic Settings from env: keys, models, caps, base_url, DRY_RUN
  pricing.py       # PRICE_MAP + cost() pure function
  budget.py        # pure budget logic: month gate, key/model selection, fallback ladder
  ledger.py        # UsageLedger protocol + PostgresLedger + InMemoryLedger (tests)
  llm.py           # LLMGateway: config+pricing+budget+ledger+httpx OpenAI call
  app.py           # FastAPI: /health, /llm/complete, /budget/status
  Dockerfile
  requirements.txt
tests/
  test_pricing.py
  test_budget.py
  test_ledger_inmemory.py
  test_llm_gateway.py
db/
  init.sql         # usage_ledger, seen_jobs, profile
docker-compose.yml
.env.example
README.md
Makefile
```

Responsibilities: `pricing` and `budget` are **pure** (no I/O) → fast unit tests. `ledger` isolates persistence behind a Protocol → tests use `InMemoryLedger`. `llm` composes them and is the only place that calls OpenAI. `app` is a thin HTTP shell.

---

### Task 1: Worker scaffold + dependencies

**Files:**
- Create: `worker/__init__.py`, `worker/requirements.txt`, `worker/Dockerfile`
- Create: `tests/__init__.py`, `pytest.ini`

- [ ] **Step 1: Create `worker/requirements.txt`**

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
httpx==0.28.1
pydantic==2.10.4
pydantic-settings==2.7.1
psycopg[binary]==3.2.3
pytest==8.3.4
pytest-asyncio==0.25.0
respx==0.22.0
```

- [ ] **Step 2: Create `worker/__init__.py` and `tests/__init__.py`** (empty files)

- [ ] **Step 3: Create `pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
pythonpath = .
```

- [ ] **Step 4: Create `worker/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "worker.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 5: Install locally and verify pytest runs**

Run: `cd "d:/AI Agentic job searching" && python -m venv .venv && .venv/Scripts/pip install -r worker/requirements.txt && .venv/Scripts/python -m pytest -q`
Expected: `no tests ran` (collection succeeds, 0 tests).

- [ ] **Step 6: Commit**

```bash
git add worker/ tests/ pytest.ini && git commit -m "chore: worker scaffold + deps"
```

---

### Task 2: Pricing (pure cost calculation)

**Files:**
- Create: `worker/pricing.py`
- Test: `tests/test_pricing.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pricing.py
import pytest
from worker.pricing import cost, PRICE_MAP

def test_cost_known_model():
    # gpt-4.1-mini: $0.40 / 1M input, $1.60 / 1M output
    c = cost("gpt-4.1-mini", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert c == pytest.approx(0.40 + 1.60)

def test_cost_partial_tokens():
    c = cost("gpt-4.1-mini", prompt_tokens=500_000, completion_tokens=0)
    assert c == pytest.approx(0.20)

def test_unknown_model_raises():
    with pytest.raises(KeyError):
        cost("nonexistent-model", 100, 100)

def test_price_map_has_required_models():
    assert "gpt-4.1-mini" in PRICE_MAP
    assert "gpt-4.1" in PRICE_MAP
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_pricing.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'worker.pricing'`.

- [ ] **Step 3: Write minimal implementation**

```python
# worker/pricing.py
"""LLM price map (USD per 1M tokens) and cost calculation. Pure, no I/O.
Update PRICE_MAP when provider prices change."""

# (input_per_million, output_per_million)
PRICE_MAP: dict[str, tuple[float, float]] = {
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4o-mini": (0.15, 0.60),
}

def cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """USD cost of one call. Raises KeyError on unknown model (fail loud)."""
    inp, out = PRICE_MAP[model]
    return (prompt_tokens / 1_000_000) * inp + (completion_tokens / 1_000_000) * out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_pricing.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add worker/pricing.py tests/test_pricing.py && git commit -m "feat: LLM pricing/cost calculation"
```

---

### Task 3: Config (env-driven settings)

**Files:**
- Create: `worker/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from worker.config import Settings

def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("OPENAI_KEY_A", "sk-a")
    monkeypatch.setenv("OPENAI_KEY_B", "sk-b")
    monkeypatch.setenv("DRY_RUN", "true")
    s = Settings()
    assert s.openai_key_a == "sk-a"
    assert s.openai_key_b == "sk-b"
    assert s.dry_run is True
    assert s.monthly_cap_usd == 8.0          # default
    assert s.cap_safety_margin_usd == 7.5     # default
    assert s.model_triage == "gpt-4.1-mini"   # default
    assert s.model_match == "gpt-4.1"         # default
    assert s.openai_base_url == "https://api.openai.com/v1"  # default
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_config.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'worker.config'`.

- [ ] **Step 3: Write minimal implementation**

```python
# worker/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_key_a: str = ""           # triage + visa pre-filter
    openai_key_b: str = ""           # match scoring + reply drafting
    openai_base_url: str = "https://api.openai.com/v1"
    model_triage: str = "gpt-4.1-mini"
    model_match: str = "gpt-4.1"
    model_fallback: str = "gpt-4o-mini"

    monthly_cap_usd: float = 8.0
    cap_safety_margin_usd: float = 7.5     # block key once month spend >= this
    daily_soft_cap_usd: float = 0.27       # ~ 8/30, advisory

    database_url: str = "postgresql://n8n:n8n@postgres:5432/n8n"
    dry_run: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add worker/config.py tests/test_config.py && git commit -m "feat: env-driven worker config"
```

---

### Task 4: Budget logic (pure gate + fallback ladder)

**Files:**
- Create: `worker/budget.py`
- Test: `tests/test_budget.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_budget.py
import pytest
from worker.budget import choose, BudgetDecision, KeySpend

# choose(task, spend, *, margin) returns which key+model to use, or blocked.
# task "triage" prefers key_a/model_triage; task "match" prefers key_b/model_match.

def s(a=0.0, b=0.0):
    return {"a": KeySpend(month_usd=a), "b": KeySpend(month_usd=b)}

def test_triage_uses_key_a_when_room():
    d = choose("triage", s(a=1.0, b=1.0), margin=7.5)
    assert d == BudgetDecision(key="a", model="gpt-4.1-mini")

def test_match_uses_key_b_when_room():
    d = choose("match", s(a=1.0, b=1.0), margin=7.5)
    assert d == BudgetDecision(key="b", model="gpt-4.1")

def test_match_falls_back_to_key_a_when_b_exhausted():
    d = choose("match", s(a=1.0, b=7.6), margin=7.5)
    # B is over margin -> shift match to A, downgraded model
    assert d.key == "a"
    assert d.model in ("gpt-4.1-mini", "gpt-4o-mini")

def test_both_exhausted_blocks():
    d = choose("match", s(a=7.6, b=7.6), margin=7.5)
    assert d.blocked is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_budget.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'worker.budget'`.

- [ ] **Step 3: Write minimal implementation**

```python
# worker/budget.py
"""Pure budget decisions. No I/O. Caller supplies current spend snapshot."""
from dataclasses import dataclass, field

@dataclass(frozen=True)
class KeySpend:
    month_usd: float = 0.0

@dataclass(frozen=True)
class BudgetDecision:
    key: str | None = None
    model: str | None = None
    blocked: bool = False

PRIMARY = {"triage": ("a", "gpt-4.1-mini"), "match": ("b", "gpt-4.1")}
DOWNGRADE = {"gpt-4.1": "gpt-4.1-mini", "gpt-4.1-mini": "gpt-4o-mini",
             "gpt-4o-mini": "gpt-4o-mini"}

def _has_room(spend: dict, key: str, margin: float) -> bool:
    return spend[key].month_usd < margin

def choose(task: str, spend: dict, *, margin: float) -> BudgetDecision:
    key, model = PRIMARY[task]
    if _has_room(spend, key, margin):
        return BudgetDecision(key=key, model=model)
    # primary key exhausted -> try the other key with a downgraded model
    other = "b" if key == "a" else "a"
    if _has_room(spend, other, margin):
        return BudgetDecision(key=other, model=DOWNGRADE[model])
    return BudgetDecision(blocked=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_budget.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add worker/budget.py tests/test_budget.py && git commit -m "feat: pure budget gate + fallback ladder"
```

---

### Task 5: Usage ledger (Protocol + InMemory impl)

**Files:**
- Create: `worker/ledger.py`
- Test: `tests/test_ledger_inmemory.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ledger_inmemory.py
from worker.ledger import InMemoryLedger
from worker.budget import KeySpend

def test_record_and_month_spend():
    led = InMemoryLedger()
    led.record(key="a", model="gpt-4.1-mini", prompt_tokens=1_000_000,
               completion_tokens=0, cost_usd=0.40, ts="2026-06-01T00:00:00Z")
    led.record(key="a", model="gpt-4.1-mini", prompt_tokens=0,
               completion_tokens=1_000_000, cost_usd=1.60, ts="2026-06-02T00:00:00Z")
    led.record(key="b", model="gpt-4.1", prompt_tokens=0,
               completion_tokens=0, cost_usd=0.0, ts="2026-06-02T00:00:00Z")
    snap = led.month_spend("2026-06")
    assert snap["a"] == KeySpend(month_usd=2.0)
    assert snap["b"] == KeySpend(month_usd=0.0)

def test_month_spend_isolates_months():
    led = InMemoryLedger()
    led.record(key="a", model="m", prompt_tokens=0, completion_tokens=0,
               cost_usd=5.0, ts="2026-05-31T00:00:00Z")
    snap = led.month_spend("2026-06")
    assert snap["a"] == KeySpend(month_usd=0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_ledger_inmemory.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'worker.ledger'`.

- [ ] **Step 3: Write minimal implementation**

```python
# worker/ledger.py
"""Usage ledger. Protocol + in-memory (tests) + Postgres (runtime) impls."""
from typing import Protocol
from worker.budget import KeySpend

class UsageLedger(Protocol):
    def record(self, *, key: str, model: str, prompt_tokens: int,
               completion_tokens: int, cost_usd: float, ts: str) -> None: ...
    def month_spend(self, month: str) -> dict[str, KeySpend]: ...

class InMemoryLedger:
    def __init__(self) -> None:
        self._rows: list[dict] = []

    def record(self, *, key, model, prompt_tokens, completion_tokens, cost_usd, ts) -> None:
        self._rows.append({"key": key, "cost_usd": cost_usd, "ts": ts})

    def month_spend(self, month: str) -> dict[str, KeySpend]:
        out = {"a": 0.0, "b": 0.0}
        for r in self._rows:
            if r["ts"].startswith(month):
                out[r["key"]] = out.get(r["key"], 0.0) + r["cost_usd"]
        return {k: KeySpend(month_usd=v) for k, v in out.items()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_ledger_inmemory.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add worker/ledger.py tests/test_ledger_inmemory.py && git commit -m "feat: usage ledger protocol + in-memory impl"
```

---

### Task 6: Postgres schema + PostgresLedger

**Files:**
- Create: `db/init.sql`
- Modify: `worker/ledger.py` (add `PostgresLedger`)

- [ ] **Step 1: Create `db/init.sql`**

```sql
-- Runs once on first Postgres start (mounted to /docker-entrypoint-initdb.d).
CREATE TABLE IF NOT EXISTS usage_ledger (
    id BIGSERIAL PRIMARY KEY,
    key_id TEXT NOT NULL,                 -- 'a' | 'b'
    model TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    cost_usd NUMERIC(12,6) NOT NULL,
    ts TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_usage_ledger_ts ON usage_ledger (ts);

CREATE TABLE IF NOT EXISTS seen_jobs (
    vacancy_url TEXT PRIMARY KEY,
    title TEXT,
    org TEXT,
    source TEXT,
    notion_page_url TEXT,
    discovered TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY DEFAULT 1,
    data JSONB NOT NULL,
    updated TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT singleton CHECK (id = 1)
);
```

- [ ] **Step 2: Add `PostgresLedger` to `worker/ledger.py`**

```python
# append to worker/ledger.py
import psycopg

class PostgresLedger:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def record(self, *, key, model, prompt_tokens, completion_tokens, cost_usd, ts) -> None:
        with psycopg.connect(self._dsn) as conn:
            conn.execute(
                "INSERT INTO usage_ledger (key_id, model, prompt_tokens, "
                "completion_tokens, cost_usd, ts) VALUES (%s,%s,%s,%s,%s,%s)",
                (key, model, prompt_tokens, completion_tokens, cost_usd, ts),
            )

    def month_spend(self, month: str) -> dict[str, KeySpend]:
        out = {"a": 0.0, "b": 0.0}
        with psycopg.connect(self._dsn) as conn:
            rows = conn.execute(
                "SELECT key_id, COALESCE(SUM(cost_usd),0) FROM usage_ledger "
                "WHERE to_char(ts,'YYYY-MM') = %s GROUP BY key_id", (month,),
            ).fetchall()
        for key_id, total in rows:
            out[key_id] = float(total)
        return {k: KeySpend(month_usd=v) for k, v in out.items()}
```

- [ ] **Step 3: Verify in-memory tests still pass (no regression)**

Run: `.venv/Scripts/python -m pytest tests/test_ledger_inmemory.py -q`
Expected: PASS. (PostgresLedger is exercised later via the integration check in Task 8.)

- [ ] **Step 4: Commit**

```bash
git add db/init.sql worker/ledger.py && git commit -m "feat: postgres schema + PostgresLedger"
```

---

### Task 7: LLM gateway (the single chokepoint)

**Files:**
- Create: `worker/llm.py`
- Test: `tests/test_llm_gateway.py`

- [ ] **Step 1: Write the failing test** (mocks OpenAI HTTP with respx; uses InMemoryLedger)

```python
# tests/test_llm_gateway.py
import httpx, respx, pytest
from worker.llm import LLMGateway
from worker.ledger import InMemoryLedger
from worker.config import Settings

def make_gw(spend_a=0.0):
    led = InMemoryLedger()
    if spend_a:
        led.record(key="a", model="gpt-4.1-mini", prompt_tokens=0,
                   completion_tokens=0, cost_usd=spend_a, ts="2026-06-01T00:00:00Z")
    s = Settings(openai_key_a="sk-a", openai_key_b="sk-b",
                 openai_base_url="https://api.openai.com/v1")
    return LLMGateway(settings=s, ledger=led, now_month="2026-06"), led

@respx.mock
@pytest.mark.asyncio
async def test_complete_records_usage():
    gw, led = make_gw()
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"content": "hi"}}],
            "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 0},
            "model": "gpt-4.1-mini",
        }))
    out = await gw.complete("triage", [{"role": "user", "content": "x"}])
    assert out["content"] == "hi"
    assert led.month_spend("2026-06")["a"].month_usd == pytest.approx(0.40)

@pytest.mark.asyncio
async def test_complete_blocks_when_capped():
    gw, _ = make_gw(spend_a=7.6)   # over default margin 7.5, and B is 'match' only
    with pytest.raises(RuntimeError, match="budget"):
        await gw.complete("triage", [{"role": "user", "content": "x"}])

@pytest.mark.asyncio
async def test_dry_run_does_not_call_api():
    led = InMemoryLedger()
    s = Settings(openai_key_a="sk-a", openai_key_b="sk-b", dry_run=True)
    gw = LLMGateway(settings=s, ledger=led, now_month="2026-06")
    out = await gw.complete("triage", [{"role": "user", "content": "x"}])
    assert out["dry_run"] is True
    assert led.month_spend("2026-06")["a"].month_usd == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_llm_gateway.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'worker.llm'`.

- [ ] **Step 3: Write minimal implementation**

```python
# worker/llm.py
"""The ONLY place that calls the LLM API. Enforces Budget Guard, records usage."""
import httpx
from worker.config import Settings
from worker.budget import choose
from worker.pricing import cost
from worker.ledger import UsageLedger

class LLMGateway:
    def __init__(self, *, settings: Settings, ledger: UsageLedger, now_month: str):
        self.s = settings
        self.ledger = ledger
        self.now_month = now_month

    async def complete(self, task: str, messages: list[dict]) -> dict:
        if self.s.dry_run:
            return {"content": "[DRY_RUN]", "dry_run": True}
        spend = self.ledger.month_spend(self.now_month)
        d = choose(task, spend, margin=self.s.cap_safety_margin_usd)
        if d.blocked:
            raise RuntimeError("LLM budget exhausted for all keys this month")
        api_key = self.s.openai_key_a if d.key == "a" else self.s.openai_key_b
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.s.openai_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": d.model, "messages": messages},
            )
        resp.raise_for_status()
        body = resp.json()
        usage = body.get("usage", {})
        pt = usage.get("prompt_tokens", 0)
        ct = usage.get("completion_tokens", 0)
        c = cost(d.model, pt, ct)
        self.ledger.record(key=d.key, model=d.model, prompt_tokens=pt,
                           completion_tokens=ct, cost_usd=c,
                           ts=f"{self.now_month}-15T00:00:00Z")
        return {"content": body["choices"][0]["message"]["content"],
                "model": d.model, "key": d.key, "cost_usd": c, "dry_run": False}
```

> Note: the `ts` stamp uses `now_month` (injected) so the module stays free of `Date.now()`-style nondeterminism in tests. The runtime composition (Task 8) injects the real current month; the Postgres `ts` column defaults to `now()` for the canonical timestamp, so the synthetic mid-month stamp only affects month bucketing, which is correct.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_llm_gateway.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add worker/llm.py tests/test_llm_gateway.py && git commit -m "feat: budget-guarded LLM gateway"
```

---

### Task 8: FastAPI app + healthcheck + full suite

**Files:**
- Create: `worker/app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_app.py
from fastapi.testclient import TestClient
from worker.app import app

def test_health():
    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'worker.app'`.

- [ ] **Step 3: Write minimal implementation**

```python
# worker/app.py
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
```

- [ ] **Step 4: Run the FULL suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS (all tasks' tests green).

- [ ] **Step 5: Commit**

```bash
git add worker/app.py tests/test_app.py && git commit -m "feat: worker FastAPI app + health/budget/llm endpoints"
```

---

### Task 9: docker-compose + .env.example + Makefile + README

**Files:**
- Create: `docker-compose.yml`, `.env.example`, `Makefile`, `README.md`, `caddy/Caddyfile`

- [ ] **Step 1: Create `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-n8n}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-n8n}
      POSTGRES_DB: ${POSTGRES_DB:-n8n}
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-n8n}"]
      interval: 10s
      retries: 5
    restart: unless-stopped

  worker:
    build: ./worker
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  n8n:
    image: n8nio/n8n:latest
    env_file: .env
    environment:
      DB_TYPE: postgresdb
      DB_POSTGRESDB_HOST: postgres
      DB_POSTGRESDB_USER: ${POSTGRES_USER:-n8n}
      DB_POSTGRESDB_PASSWORD: ${POSTGRES_PASSWORD:-n8n}
      N8N_HOST: ${N8N_HOST:-localhost}
      WEBHOOK_URL: ${WEBHOOK_URL:-http://localhost:5678/}
      GENERIC_TIMEZONE: ${TZ:-Asia/Tehran}
    ports:
      - "127.0.0.1:5678:5678"   # localhost-only by default; use proxy profile for public
    volumes:
      - n8n-data:/home/node/.n8n
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  caddy:
    image: caddy:2
    profiles: ["proxy"]
    ports: ["80:80", "443:443"]
    volumes:
      - ./caddy/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data
    depends_on: [n8n]
    restart: unless-stopped

volumes:
  postgres-data:
  n8n-data:
  caddy-data:
```

- [ ] **Step 2: Create `.env.example`** (every var documented; owner fills later)

```bash
# ===== Postgres =====
POSTGRES_USER=n8n
POSTGRES_PASSWORD=change-me
POSTGRES_DB=n8n
DATABASE_URL=postgresql://n8n:change-me@postgres:5432/n8n

# ===== OpenAI (2 keys, $8 cap each enforced in code) =====
OPENAI_KEY_A=sk-...   # triage + visa pre-filter (cheap model)
OPENAI_KEY_B=sk-...   # match scoring + reply drafting (stronger model)
OPENAI_BASE_URL=https://api.openai.com/v1   # swap for OpenRouter/Azure/Ollama
MODEL_TRIAGE=gpt-4.1-mini
MODEL_MATCH=gpt-4.1
MODEL_FALLBACK=gpt-4o-mini
MONTHLY_CAP_USD=8.0
CAP_SAFETY_MARGIN_USD=7.5
DAILY_SOFT_CAP_USD=0.27

# ===== Safety =====
DRY_RUN=true          # set false to allow real sends/writes

# ===== n8n / networking =====
TZ=Asia/Tehran
N8N_HOST=localhost
WEBHOOK_URL=http://localhost:5678/
N8N_BASIC_AUTH_ACTIVE=true
N8N_BASIC_AUTH_USER=admin
N8N_BASIC_AUTH_PASSWORD=change-me

# ===== Notion =====
NOTION_TOKEN=secret_...
NOTION_APPLICATIONS_DS=cd54c7e6-fca0-4234-b8fb-87745292ac83

# ===== Telegram =====
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# ===== Job source API keys (Phase 2) =====
ADZUNA_APP_ID=
ADZUNA_APP_KEY=
JOOBLE_KEY=

# ===== Google OAuth (configured in n8n UI; domain only needed for proxy profile) =====
# DOMAIN=jobs.example.com
```

- [ ] **Step 3: Create `caddy/Caddyfile`**

```
{$DOMAIN} {
    basic_auth {
        {$N8N_BASIC_AUTH_USER} {$N8N_BASIC_AUTH_PASSWORD_HASH}
    }
    reverse_proxy n8n:5678
}
```

- [ ] **Step 4: Create `Makefile`**

```makefile
.PHONY: up down logs test backup restore proxy-up
up:        ; docker compose up -d --build
down:      ; docker compose down
logs:      ; docker compose logs -f --tail=100
proxy-up:  ; docker compose --profile proxy up -d --build
test:      ; python -m pytest -q
backup:    ; bash scripts/backup.sh
restore:   ; bash scripts/restore.sh $(DUMP)
```

- [ ] **Step 5: Create `README.md`** (quickstart: copy `.env.example`→`.env`, fill, `make up`, open `http://localhost:5678`, import workflows from `n8n/workflows/`, complete OAuth from non-Iran IP; keep `DRY_RUN=true` until verified).

- [ ] **Step 6: Validate compose syntax**

Run: `docker compose config -q && echo OK`
Expected: `OK` (no errors).

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml .env.example Makefile README.md caddy/ && git commit -m "feat: compose stack + env template + make targets"
```

---

### Task 10: Backup/restore scripts (portability)

**Files:**
- Create: `scripts/backup.sh`, `scripts/restore.sh`

- [ ] **Step 1: Create `scripts/backup.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p backups
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-n8n}" "${POSTGRES_DB:-n8n}" > "backups/db-$STAMP.sql"
echo "Wrote backups/db-$STAMP.sql"
echo "To migrate: copy this dump + your .env to the new host, then: make restore DUMP=backups/db-$STAMP.sql && make up"
```

- [ ] **Step 2: Create `scripts/restore.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
DUMP="${1:?usage: restore.sh <dump.sql>}"
docker compose up -d postgres
until docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-n8n}"; do sleep 1; done
cat "$DUMP" | docker compose exec -T postgres psql -U "${POSTGRES_USER:-n8n}" "${POSTGRES_DB:-n8n}"
echo "Restored $DUMP"
```

- [ ] **Step 3: Make executable + smoke-check syntax**

Run: `chmod +x scripts/*.sh && bash -n scripts/backup.sh && bash -n scripts/restore.sh && echo OK`
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add scripts/ && git commit -m "feat: backup/restore scripts for portable migration"
```

---

## Phase 1 self-review (done)

- Spec §3 (containers/portability): Tasks 9–10. ✓
- Spec §6 (Budget Guard): Tasks 2,4,5,6,7 (pricing, gate, ledger, gateway, chokepoint). ✓
- Spec §10 (DRY_RUN, secrets in .env, localhost-bind, optional proxy): Tasks 7,9. ✓
- Spec §3 (provider-swappable LLM): `OPENAI_BASE_URL` in config + gateway. ✓
- No placeholders; types consistent (`KeySpend`, `BudgetDecision`, `choose`, `UsageLedger`, `LLMGateway.complete`) across tasks 4–8. ✓

---

## Roadmap — Phases 2–4 (own detailed plans when reached)

### Phase 2 — Job Discovery (highest value)
**Worker modules:** `sources/` (one client per source: `adzuna.py`, `arbeitnow.py`, `jooble.py`, `euraxess.py`, `jobsacuk.py`, `academictransfer.py`, `relocateme_scrape.py` via Playwright), `normalize.py`, `dedupe.py` (uses `seen_jobs`), `visa.py` (sponsor-register CSV loaders + JD scan via LLM gateway), `match.py` (profile-vs-job scoring prompt), `profile_build.py` (CV PDF → profile JSON), `notion.py` (idempotent upsert + 4 new props), `pipeline.py` (`/jobs/run`).
**n8n:** W3 (cron 06:00 → `POST worker/jobs/run` → handles its own Notion writes; DRY_RUN aware). W0 profile-build trigger.
**Tests:** each source client against recorded fixtures (respx); `dedupe`, `visa`, `normalize`, `match` pure-ish unit tests with fakes; Notion upsert against a single test row.
**Deliverable:** matched, visa-filtered jobs appear in Career Hub → Applications.

### Phase 3 — Email & Calendar
**Worker:** `triage.py` (classify + draft via gateway), `calendar_parse.py` (extract event proposals).
**n8n:** W1 (Gmail node fetch → `worker/triage` → Gmail create-draft + label `AI/Drafted`), W2 (detect requests → propose event → approval → Google Calendar create). Draft-only; nothing sent.
**Tests:** triage classification + draft prompt with fixtures; calendar parse unit tests.

### Phase 4 — Digest & Approvals
**Worker:** `digest.py` (compile daily summary).
**n8n:** W4 (daily digest email + Telegram summary with inline approve/reject; Telegram long-poll trigger locked to `TELEGRAM_CHAT_ID`; approve → send draft / confirm event / bump priority). Error-trigger workflow → Telegram alert. Monthly budget-reset cron.
**Tests:** digest formatting; approval-handler routing with fakes.
