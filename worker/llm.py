"""The ONLY place that calls the LLM API. Enforces Budget Guard, records usage."""
import httpx
from worker.config import Settings
from worker.budget import choose
from worker.pricing import cost
from worker.ledger import UsageLedger


class BudgetExhausted(RuntimeError):
    """Raised when every key is over its monthly cap. A dedicated type so callers
    can stop a batch cleanly on budget exhaustion WITHOUT swallowing unrelated
    RuntimeErrors (which must surface, not masquerade as a clean stop)."""


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
            raise BudgetExhausted("LLM budget exhausted for all keys this month")
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
