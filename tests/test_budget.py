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
