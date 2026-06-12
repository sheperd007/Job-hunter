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
