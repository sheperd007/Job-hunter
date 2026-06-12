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


class PostgresLedger:
    """Runtime ledger backed by Postgres. psycopg is imported lazily so the
    module imports without psycopg installed (the in-memory path stays
    dependency-free for unit tests / restricted environments)."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def record(self, *, key, model, prompt_tokens, completion_tokens, cost_usd, ts) -> None:
        import psycopg
        with psycopg.connect(self._dsn) as conn:
            conn.execute(
                "INSERT INTO usage_ledger (key_id, model, prompt_tokens, "
                "completion_tokens, cost_usd, ts) VALUES (%s,%s,%s,%s,%s,%s)",
                (key, model, prompt_tokens, completion_tokens, cost_usd, ts),
            )

    def month_spend(self, month: str) -> dict[str, KeySpend]:
        import psycopg
        out = {"a": 0.0, "b": 0.0}
        with psycopg.connect(self._dsn) as conn:
            rows = conn.execute(
                "SELECT key_id, COALESCE(SUM(cost_usd),0) FROM usage_ledger "
                "WHERE to_char(ts,'YYYY-MM') = %s GROUP BY key_id", (month,),
            ).fetchall()
        for key_id, total in rows:
            out[key_id] = float(total)
        return {k: KeySpend(month_usd=v) for k, v in out.items()}
