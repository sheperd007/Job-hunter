import pytest
from worker.pipeline import run_discovery
from worker.dedupe import InMemorySeenStore
from worker.models import Job


class FakeGateway:
    def __init__(self, score):
        self._score = score

    async def complete(self, task, messages):
        return {"content": f'{{"score": {self._score}, "track": "Industry", "tags": ["ML"]}}'}


def jobs():
    return [
        Job(title="ML Eng EU", org="Acme", url="https://x.com/eu", source="arbeitnow",
            region="EU", track_hint="industry", description="visa sponsorship offered"),
        Job(title="ML Eng US", org="Beta", url="https://x.com/us", source="adzuna",
            region="US", track_hint="industry", description="visa sponsorship offered"),
        Job(title="DS no-visa", org="Gamma", url="https://x.com/nv", source="adzuna",
            region="EU", track_hint="industry", description="must already have right to work"),
    ]


async def _notion_collector(calls):
    async def _create(job, m, v, *, discovered):
        calls.append(job.url)
        return {"url": f"https://notion.so/{job.title}"}
    return _create


@pytest.mark.asyncio
async def test_run_discovery_filters_and_inserts():
    store = InMemorySeenStore()
    calls = []
    notion_create = await _notion_collector(calls)
    out = await run_discovery(jobs=jobs(), profile={}, gateway=FakeGateway(85),
                              store=store, notion_create=notion_create,
                              discovered="2026-06-12", min_score=60)
    assert out["dropped"]["region"] == 1     # US dropped
    assert out["dropped"]["visa"] == 1        # no-visa dropped
    assert out["eligible"] == 1               # only EU-with-visa
    assert out["inserted"] == 1
    assert calls == ["https://x.com/eu"]
    assert store.is_seen("https://x.com/eu") is True   # marked after insert


@pytest.mark.asyncio
async def test_run_discovery_score_threshold():
    store = InMemorySeenStore()
    calls = []
    notion_create = await _notion_collector(calls)
    out = await run_discovery(jobs=jobs(), profile={}, gateway=FakeGateway(40),
                              store=store, notion_create=notion_create,
                              discovered="2026-06-12", min_score=60)
    assert out["inserted"] == 0
    assert out["dropped"]["score"] == 1
    assert calls == []


@pytest.mark.asyncio
async def test_run_discovery_dry_run_no_writes():
    store = InMemorySeenStore()
    calls = []
    notion_create = await _notion_collector(calls)
    out = await run_discovery(jobs=jobs(), profile={}, gateway=FakeGateway(99),
                              store=store, notion_create=notion_create,
                              discovered="2026-06-12", dry_run=True)
    assert out["dry_run"] is True
    assert out["inserted"] == 0
    assert calls == []                        # no Notion writes in dry run
    assert out["eligible"] == 1
