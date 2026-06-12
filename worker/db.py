"""Schema bootstrap. On docker-compose, db/init.sql runs automatically; on
managed databases (e.g. DigitalOcean Managed Postgres) there is no init hook,
so a PRE_DEPLOY job runs `python -m worker.migrate`, which calls ensure_schema().
Keep DDL in sync with db/init.sql.
"""

DDL = """
CREATE TABLE IF NOT EXISTS usage_ledger (
    id BIGSERIAL PRIMARY KEY,
    key_id TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS pending_actions (
    id BIGSERIAL PRIMARY KEY,
    kind TEXT NOT NULL,                        -- 'reply' | 'event'
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',    -- pending | approved | rejected
    created TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved TIMESTAMPTZ
);
"""


def ensure_schema(dsn: str) -> None:
    import psycopg
    with psycopg.connect(dsn) as conn:
        conn.execute(DDL)
