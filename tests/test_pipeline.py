import pytest
from worker.pipeline import (run_discovery, load_register, _interleave,
                             _google_queries, resolve_register_url)
from worker.visa import SponsorRegister


def test_interleave_round_robins_sources():
    # So the per-run scoring cap samples every source instead of being eaten by
    # whichever source happens to come first.
    assert _interleave([[1, 2, 3], [10, 20], [100]]) == [1, 10, 100, 2, 20, 3]


def test_interleave_skips_empty_sources():
    assert _interleave([[], [1], [], [2, 3]]) == [1, 2, 3]
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
                source="google_jobs", region="EU", track_hint="industry",
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
        Job(title="ML Eng US", org="Beta", url="https://x.com/us", source="google_jobs",
            region="US", track_hint="industry", description="visa sponsorship offered"),
        Job(title="DS no-visa", org="Gamma", url="https://x.com/nv", source="google_jobs",
            region="EU", track_hint="industry", description="must already have right to work"),
    ]


async def _notion_collector(calls):
    async def _create(job, m, v, *, discovered, effective_score=None):
        calls.append(job.url)
        return {"url": f"https://notion.so/{job.title}"}
    return _create


def _flagged(i):
    # source visa_sponsorship flag -> verdict confidence 0.85
    return Job(title=f"F{i}", org=f"O{i}", url=f"https://x.com/f{i}",
               source="google_jobs", region="EU", track_hint="industry",
               description="great team", raw={"visa_sponsorship": True})


def _unclear(i):
    # no signal -> soft-gate "Unclear" 0.3
    return Job(title=f"U{i}", org=f"O{i}", url=f"https://x.com/u{i}",
               source="google_jobs", region="EU", track_hint="industry",
               description="great team")


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
async def test_run_discovery_stops_gracefully_on_notion_outage():
    # A Notion connect failure (ConnectTimeout etc, all subclass httpx.HTTPError)
    # must not 500 the whole run: LLM cost for already-scored jobs is kept, the
    # run returns cleanly, and the caller (the /jobs/run 500s + Telegram ping
    # never firing) is what this guards against.
    import httpx

    async def flaky_notion(job, m, v, *, discovered, effective_score=None):
        raise httpx.ConnectTimeout("boom")

    store = InMemorySeenStore()
    out = await run_discovery(jobs=eligible_jobs(5), profile={}, gateway=CountingGateway(85),
                              store=store, notion_create=flaky_notion,
                              discovered="2026-06-12", min_score=60)
    assert out["inserted"] == 0
    assert out["notion_down"] is True


@pytest.mark.asyncio
async def test_run_discovery_stops_scoring_after_first_notion_failure():
    # Notion being down is systemic, not per-job: once it fails once, further
    # score() calls are doomed to also fail at the Notion step, so the loop must
    # stop immediately rather than burn the rest of the LLM budget on jobs that
    # can never be inserted this run.
    import httpx

    async def flaky_notion(job, m, v, *, discovered, effective_score=None):
        raise httpx.ConnectError("boom")

    store = InMemorySeenStore()
    gw = CountingGateway(85)
    out = await run_discovery(jobs=eligible_jobs(5), profile={}, gateway=gw,
                              store=store, notion_create=flaky_notion,
                              discovered="2026-06-12", min_score=60)
    assert gw.calls == 1                 # only the first (doomed) job was scored
    assert out["notion_down"] is True


@pytest.mark.asyncio
async def test_run_discovery_notion_failure_leaves_job_unmarked_for_retry():
    # The job that failed to insert must NOT be marked seen — otherwise it's lost
    # forever even though it was never actually written to Notion.
    import httpx

    async def flaky_notion(job, m, v, *, discovered, effective_score=None):
        raise httpx.ConnectTimeout("boom")

    store = InMemorySeenStore()
    jb = eligible_jobs(1)
    await run_discovery(jobs=jb, profile={}, gateway=CountingGateway(85),
                        store=store, notion_create=flaky_notion,
                        discovered="2026-06-12", min_score=60)
    assert store.is_seen(jb[0].url) is False


@pytest.mark.asyncio
async def test_run_discovery_keeps_inserts_before_notion_outage():
    # If Notion fails partway through a run (e.g. after succeeding a few times),
    # everything inserted before the failure is kept, not rolled back.
    import httpx

    calls = []
    good = await _notion_collector(calls)

    class FlakyAfterN:
        def __init__(self, n):
            self.n = n
            self.calls = 0

        async def __call__(self, job, m, v, *, discovered, effective_score=None):
            self.calls += 1
            if self.calls > self.n:
                raise httpx.ConnectTimeout("boom")
            return await good(job, m, v, discovered=discovered, effective_score=effective_score)

    store = InMemorySeenStore()
    out = await run_discovery(jobs=eligible_jobs(5), profile={}, gateway=CountingGateway(85),
                              store=store, notion_create=FlakyAfterN(2),
                              discovered="2026-06-12", min_score=60)
    assert out["inserted"] == 2
    assert out["notion_down"] is True


@pytest.mark.asyncio
async def test_run_discovery_propagates_non_notion_notion_create_errors():
    # A bug inside the injected notion_create (not a network/API failure) must
    # still surface, not be silently treated as "Notion is down".
    async def buggy_notion(job, m, v, *, discovered, effective_score=None):
        raise TypeError("bug: missing arg")

    store = InMemorySeenStore()
    with pytest.raises(TypeError):
        await run_discovery(jobs=eligible_jobs(1), profile={}, gateway=CountingGateway(85),
                            store=store, notion_create=buggy_notion,
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
async def test_run_discovery_scores_signal_bearing_jobs_first():
    # Two-phase: visa-signal jobs are scored before "Unclear" ones, so the per-run
    # cap is spent on likely-relocation roles.
    store = InMemorySeenStore()
    calls = []
    notion_create = await _notion_collector(calls)
    mixed = [_unclear(0), _unclear(1), _flagged(0), _flagged(1)]
    out = await run_discovery(jobs=mixed, profile={}, gateway=FakeGateway(85),
                              store=store, notion_create=notion_create,
                              discovered="2026-06-12", min_score=60, max_match=2)
    assert out["capped"] is True
    assert set(calls) == {"https://x.com/f0", "https://x.com/f1"}   # flagged scored first


@pytest.mark.asyncio
async def test_effective_score_boosts_sponsor_over_unclear():
    recorded = {}

    async def notion_create(job, m, v, *, discovered, effective_score=None):
        recorded[job.url] = effective_score
        return {"url": "n"}

    store = InMemorySeenStore()
    await run_discovery(jobs=[_unclear(0), _flagged(0)], profile={},
                        gateway=FakeGateway(70), store=store,
                        notion_create=notion_create, discovered="2026-06-12",
                        min_score=60, visa_rank_weight=20)
    assert recorded["https://x.com/f0"] > recorded["https://x.com/u0"]


@pytest.mark.asyncio
async def test_run_discovery_llm_upgrades_unclear_visa():
    captured = {}

    async def notion_create(job, m, v, *, discovered, effective_score=None):
        captured[job.url] = v
        return {"url": "n"}

    class VisaGW:
        async def complete(self, task, messages):
            return {"content": '{"score": 75, "visa": {"intent": "sponsors", '
                               '"confidence": 0.9, "evidence": "we sponsor"}}'}

    store = InMemorySeenStore()
    await run_discovery(jobs=[_unclear(0)], profile={}, gateway=VisaGW(),
                        store=store, notion_create=notion_create,
                        discovered="2026-06-12", min_score=60, visa_rank_weight=20)
    v = captured["https://x.com/u0"]
    assert v.label == "Sponsors visa" and v.source == "llm"


@pytest.mark.asyncio
async def test_run_discovery_register_visa_survives_llm_negative():
    captured = {}

    async def notion_create(job, m, v, *, discovered, effective_score=None):
        captured[job.url] = v
        return {"url": "n"}

    class NegGW:
        async def complete(self, task, messages):
            return {"content": '{"score": 75, "visa": {"intent": "negative", '
                               '"confidence": 0.9}}'}

    reg = SponsorRegister(["Acme Ltd"])
    j = Job(title="ML", org="Acme", url="https://x.com/r", source="google_jobs",
            region="EU", track_hint="industry", description="great team")
    store = InMemorySeenStore()
    await run_discovery(jobs=[j], profile={}, gateway=NegGW(), store=store,
                        notion_create=notion_create, discovered="2026-06-12",
                        min_score=60, register=reg, visa_rank_weight=20)
    assert captured["https://x.com/r"].label == "On sponsor register"


def test_google_queries_adds_visa_bias_capped():
    out = _google_queries(["machine learning", "deep learning"],
                          ["visa sponsorship", "relocation"], cap=3)
    assert out == ["machine learning", "deep learning",
                   "machine learning visa sponsorship"]


def test_google_queries_no_suffixes_is_passthrough():
    assert _google_queries(["a", "b"], [], cap=5) == ["a", "b"]


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


@pytest.mark.asyncio
async def test_resolve_register_url_passthrough_non_sentinel():
    assert await resolve_register_url("http://x/reg.csv") == "http://x/reg.csv"


@pytest.mark.asyncio
async def test_resolve_register_url_finds_csv_from_govuk_api():
    async def fake_json(u):
        return {"details": {"attachments": [
            {"url": "https://assets.gov.uk/something.pdf"},
            {"url": "https://assets.gov.uk/worker-2026-06-19.csv"}]}}

    out = await resolve_register_url("govuk:workers", fetch_json=fake_json)
    assert out.endswith("worker-2026-06-19.csv")


@pytest.mark.asyncio
async def test_resolve_register_url_none_on_error():
    async def boom(u):
        raise RuntimeError("down")

    assert await resolve_register_url("govuk:workers", fetch_json=boom) is None


@pytest.mark.asyncio
async def test_load_register_resolves_govuk_sentinel():
    async def fake_json(u):
        return {"details": {"attachments": [{"url": "http://x/workers.csv"}]}}

    async def fake_fetch(u):
        assert u == "http://x/workers.csv"
        return "Organisation Name\nAcme Ltd\n"

    reg = await load_register(_FakeSettings("govuk:workers"),
                              fetch=fake_fetch, fetch_json=fake_json)
    assert reg is not None and reg.contains("Acme") is True
