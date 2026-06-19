import pytest
from worker.match import score, _extract_json, _priority, effective_score
from worker.models import Job


class FakeGateway:
    def __init__(self, content):
        self.content = content
        self.calls = []

    async def complete(self, task, messages):
        self.calls.append((task, messages))
        return {"content": self.content}


def job():
    return Job(title="ML Engineer", org="Acme", url="https://x.com/1",
               description="Build LLM/RAG systems", track_hint="industry")


def test_priority_thresholds():
    assert _priority(81) == "High"
    assert _priority(60) == "Medium"
    assert _priority(59) == "Low"


def test_extract_json_with_fences():
    assert _extract_json('```json\n{"score": 5}\n```') == {"score": 5}


@pytest.mark.asyncio
async def test_score_parses_and_filters():
    gw = FakeGateway('```json\n{"score": 82, "rationale": "strong ML fit", '
                     '"track": "Industry", "tags": ["ML", "AI", "banana"]}\n```')
    r = await score(job(), {"skills": ["python"]}, gw)
    assert r.score == 82
    assert r.priority == "High"
    assert r.tags == ["ML", "AI"]          # invalid 'banana' filtered out
    assert r.track == "Industry"
    assert gw.calls[0][0] == "match"       # routed through gateway with task=match


@pytest.mark.asyncio
async def test_score_malformed_json_defaults_zero():
    gw = FakeGateway("sorry, I cannot help")
    r = await score(job(), {}, gw)
    assert r.score == 0 and r.priority == "Low"


@pytest.mark.asyncio
async def test_score_clamps_out_of_range():
    gw = FakeGateway('{"score": 250}')
    r = await score(job(), {}, gw)
    assert r.score == 100


def test_effective_score_boosts_high_visa_confidence():
    # at equal fit, a strong visa signal outranks an unclear one
    assert effective_score(80, 0.9, 20) > effective_score(80, 0.3, 20)


def test_effective_score_neutral_at_half():
    assert effective_score(70, 0.5, 20) == 70


def test_effective_score_weight_zero_is_kill_switch():
    assert effective_score(73, 0.9, 0) == 73


def test_effective_score_clamps_0_100():
    assert effective_score(99, 1.0, 20) == 100
    assert effective_score(1, 0.0, 50) == 0


@pytest.mark.asyncio
async def test_score_parses_visa_object():
    gw = FakeGateway('{"score": 70, "visa": {"intent": "sponsors", '
                     '"confidence": 0.9, "evidence": "we sponsor visas"}}')
    r = await score(job(), {}, gw)
    assert r.visa_intent == "sponsors"
    assert r.visa_confidence == 0.9
    assert "sponsor" in r.visa_evidence


@pytest.mark.asyncio
async def test_score_missing_visa_defaults_unclear():
    gw = FakeGateway('{"score": 70}')
    r = await score(job(), {}, gw)
    assert r.visa_intent == "unclear" and r.visa_confidence == 0.0


@pytest.mark.asyncio
async def test_score_junk_visa_intent_and_confidence_coerced():
    gw = FakeGateway('{"score": 70, "visa": {"intent": "banana", "confidence": 5}}')
    r = await score(job(), {}, gw)
    assert r.visa_intent == "unclear"      # invalid intent -> unclear
    assert r.visa_confidence == 1.0        # 5 clamped to 1.0
