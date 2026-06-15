import pytest
from worker.pipeline import run_discovery, load_register
from worker.dedupe import InMemorySeenStore
from worker.llm import BudgetExhausted
from worker.models import Job


class CountingGateway:
    """Counts score calls; optionally raises `exc` after N successful calls."""

    def __init__(self, score, fail_after=None, exc=BudgetExhausted):
        self._score = score
        self.calls = 0
        self._fail_after = fail_after
        self._exc = exc

    async def complete(self, task, messages):
        self.calls += 1
        if self._fail_after is not None and self.calls > self._fail_after:
            raise self._exc("boom")
        return {"content": f'{{"score": {self._score}, "track": "Industry", "tags": ["ML"]}}'}


def eligible_jobs(n):
    """n in-region, visa-eligible industry jobs."""
    return [Job(title=f"ML {i}", org=f"Org{i}", url=f"https://x.com/{i}",
                source="adzuna", region="EU", track_hint="industry",
                description="visa sponsorship offered")
            for i in range(n)]


class _FakeSettings:
    def __init__(self, url):
        self.sponsor_register_url = url


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


@pytest.mark.asyncio
async def test_run_discovery_caps_scoring_per_run():
    # max_match bounds LLM cost: only the first N eligible jobs get scored;
    # the rest are left untouched (not marked) for a later run to pick up.
    store = InMemorySeenStore()
    calls = []
    notion_create = await _notion_collector(calls)
    gw = CountingGateway(85)
    out = await run_discovery(jobs=eligible_jobs(5), profile={}, gateway=gw,
                              store=store, notion_create=notion_create,
                              discovered="2026-06-12", min_score=60, max_match=2)
    assert gw.calls == 2          # scored exactly the cap
    assert out["inserted"] == 2
    assert out["capped"] is True
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_run_discovery_stops_gracefully_on_budget_block():
    # A BudgetExhausted mid-run stops cleanly (no exception out), keeping whatever
    # was already inserted.
    store = InMemorySeenStore()
    calls = []
    notion_create = await _notion_collector(calls)
    gw = CountingGateway(85, fail_after=1, exc=BudgetExhausted)  # 2nd call raises
    out = await run_discovery(jobs=eligible_jobs(5), profile={}, gateway=gw,
                              store=store, notion_create=notion_create,
                              discovered="2026-06-12", min_score=60)
    assert out["inserted"] == 1                # first succeeded
    assert out["capped"] is True
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_run_discovery_propagates_non_budget_errors():
    # A non-budget RuntimeError must NOT be swallowed as a clean stop — it would
    # silently regress to "0 new matches, no error". It propagates.
    store = InMemorySeenStore()
    calls = []
    notion_create = await _notion_collector(calls)
    gw = CountingGateway(85, fail_after=0, exc=RuntimeError)     # 1st call raises
    with pytest.raises(RuntimeError):
        await run_discovery(jobs=eligible_jobs(5), profile={}, gateway=gw,
                            store=store, notion_create=notion_create,
                            discovered="2026-06-12", min_score=60)


@pytest.mark.asyncio
async def test_below_threshold_jobs_marked_seen_not_rescored():
    # A scored-but-rejected job is marked seen (notion_page_url=None) so it is not
    # re-scored on later runs — bounds cost and stops the cap being eaten by the
    # same front-of-list rejects every day.
    store = InMemorySeenStore()
    calls = []
    notion_create = await _notion_collector(calls)
    jb = eligible_jobs(1)
    out = await run_discovery(jobs=jb, profile={}, gateway=CountingGateway(40),
                              store=store, notion_create=notion_create,
                              discovered="2026-06-12", min_score=60)
    assert out["dropped"]["score"] == 1
    assert out["inserted"] == 0
    assert calls == []                                  # not inserted to Notion
    assert store.is_seen(jb[0].url) is True             # but marked seen
    # second run: the reject is filtered out, never re-scored
    gw2 = CountingGateway(40)
    out2 = await run_discovery(jobs=jb, profile={}, gateway=gw2, store=store,
                               notion_create=notion_create,
                               discovered="2026-06-13", min_score=60)
    assert gw2.calls == 0
    assert out2["new"] == 0


@pytest.mark.asyncio
async def test_load_register_none_when_url_unset():
    assert await load_register(_FakeSettings("")) is None


@pytest.mark.asyncio
async def test_load_register_builds_from_fetched_csv():
    csv = "Organisation Name,Town/City\nDeepMind Technologies Limited,London\n"

    async def fake_fetch(url):
        return csv

    reg = await load_register(_FakeSettings("http://x/reg.csv"), fetch=fake_fetch)
    assert reg is not None and reg.contains("DeepMind Technologies") is True


@pytest.mark.asyncio
async def test_load_register_none_on_fetch_error():
    async def boom(url):
        raise RuntimeError("404")

    assert await load_register(_FakeSettings("http://x/reg.csv"), fetch=boom) is None
