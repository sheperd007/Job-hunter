import pytest
from worker.profile_build import build_profile


class FakeGateway:
    def __init__(self, content):
        self.content = content
        self.calls = []

    async def complete(self, task, messages):
        self.calls.append((task, messages))
        return {"content": self.content}


@pytest.mark.asyncio
async def test_build_profile_parses_json():
    gw = FakeGateway('{"name": "Hamid Jahani", "skills": ["python", "pytorch"], '
                     '"tracks": ["academic", "industry"], "seniority_years": 4}')
    p = await build_profile("CV text here", gw)
    assert p["name"] == "Hamid Jahani"
    assert "pytorch" in p["skills"]
    assert gw.calls[0][0] == "match"      # routes through the strong lane


@pytest.mark.asyncio
async def test_build_profile_bad_json_returns_empty():
    gw = FakeGateway("I cannot do that")
    assert await build_profile("x", gw) == {}
