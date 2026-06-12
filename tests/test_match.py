import pytest
from worker.match import score, _extract_json, _priority
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
