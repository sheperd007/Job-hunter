import httpx
import respx
import pytest
from worker.llm import LLMGateway
from worker.ledger import InMemoryLedger
from worker.config import Settings


def make_gw(spend_a=0.0, spend_b=0.0):
    led = InMemoryLedger()
    if spend_a:
        led.record(key="a", model="gpt-4.1-mini", prompt_tokens=0,
                   completion_tokens=0, cost_usd=spend_a, ts="2026-06-01T00:00:00Z")
    if spend_b:
        led.record(key="b", model="gpt-4.1", prompt_tokens=0,
                   completion_tokens=0, cost_usd=spend_b, ts="2026-06-01T00:00:00Z")
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
async def test_complete_blocks_when_both_keys_capped():
    # Both keys over the safety margin -> no fallback possible -> block.
    gw, _ = make_gw(spend_a=9.6, spend_b=9.6)
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
