"""Pure budget decisions. No I/O. Caller supplies current spend snapshot."""
from dataclasses import dataclass


@dataclass(frozen=True)
class KeySpend:
    month_usd: float = 0.0


@dataclass(frozen=True)
class BudgetDecision:
    key: str | None = None
    model: str | None = None
    blocked: bool = False


PRIMARY = {"triage": ("a", "gpt-4.1-mini"), "match": ("b", "gpt-4.1")}
DOWNGRADE = {
    "gpt-4.1": "gpt-4.1-mini",
    "gpt-4.1-mini": "gpt-4o-mini",
    "gpt-4o-mini": "gpt-4o-mini",
}


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
