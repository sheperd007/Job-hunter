from worker.dedupe import InMemorySeenStore, filter_new, content_key_for
from worker.models import Job


def j(url, title="t"):
    return Job(title=title, url=url, source="s")


def _seed(store, job):
    store.mark(url=job.url, title=job.title, org=job.org, source=job.source,
               content_key=content_key_for(job))


def test_content_key_for_normalizes_org_title_region():
    a = Job(title="ML Engineer", url="https://a/1", org="Acme Ltd", source="google_jobs", region="UK")
    b = Job(title="ml  engineer", url="https://b/2", org="ACME LIMITED", source="arbeitnow", region="UK")
    assert content_key_for(a) == content_key_for(b)        # same role -> same key


def test_content_key_for_none_without_org():
    assert content_key_for(Job(title="PostDoc", url="https://x/1", source="rss", region="UK")) is None


def test_filter_new_drops_cross_source_duplicate():
    store = InMemorySeenStore()
    _seed(store, Job(title="ML Engineer", url="https://boardA/1", org="Acme Ltd",
                     source="google_jobs", region="UK"))
    dup = Job(title="ML Engineer", url="https://boardB/9", org="ACME LIMITED",
              source="arbeitnow", region="UK")              # same role, different URL+board
    assert filter_new([dup], store) == []


def test_filter_new_keeps_same_title_different_region():
    store = InMemorySeenStore()
    _seed(store, Job(title="ML Engineer", url="https://a/1", org="Acme", source="google_jobs", region="UK"))
    other = Job(title="ML Engineer", url="https://b/2", org="Acme", source="google_jobs", region="EU")
    assert [x.url for x in filter_new([other], store)] == ["https://b/2"]


def test_filter_new_collapses_cross_source_within_batch():
    a = Job(title="ML Engineer", url="https://a/1", org="Acme", source="google_jobs", region="UK")
    b = Job(title="ML Engineer", url="https://b/2", org="Acme", source="arbeitnow", region="UK")
    assert len(filter_new([a, b], InMemorySeenStore())) == 1


def test_filter_new_drops_already_seen():
    store = InMemorySeenStore()
    store.mark(url="https://x.com/1?utm=a", title="t", org="o", source="s")
    out = filter_new([j("https://x.com/1"), j("https://x.com/2")], store)
    assert [job.url for job in out] == ["https://x.com/2"]


def test_filter_new_dedupes_within_batch():
    store = InMemorySeenStore()
    out = filter_new([j("https://x.com/9?a=1"), j("https://x.com/9?b=2")], store)
    assert len(out) == 1


def test_mark_then_seen_uses_canonical_url():
    store = InMemorySeenStore()
    assert store.is_seen("https://x.com/5#frag") is False
    store.mark(url="https://x.com/5", title="t", org="o", source="s")
    assert store.is_seen("https://x.com/5?ref=z") is True
