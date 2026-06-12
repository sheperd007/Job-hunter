from worker.dedupe import InMemorySeenStore, filter_new
from worker.models import Job


def j(url, title="t"):
    return Job(title=title, url=url, source="s")


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
