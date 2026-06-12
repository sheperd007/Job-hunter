"""Job-discovery orchestration.

run_discovery() is the pure, injectable core (deps passed in -> unit-tested with
fakes). gather_jobs() is the runtime glue that calls the real source clients.
"""
from worker.dedupe import filter_new
from worker.normalize import in_target_region
from worker.visa import assess
from worker.match import score


async def run_discovery(*, jobs, profile, gateway, store, notion_create,
                        register=None, min_score: int = 60,
                        discovered: str, dry_run: bool = False) -> dict:
    new = filter_new(jobs, store)
    inserted: list[dict] = []
    eligible = 0
    dropped = {"region": 0, "visa": 0, "score": 0}

    for job in new:
        if not in_target_region(job.region):
            dropped["region"] += 1
            continue
        v = assess(job=job, register=register, academic=(job.track_hint == "academic"))
        if not v.eligible:
            dropped["visa"] += 1
            continue
        eligible += 1
        if dry_run:
            inserted.append({"title": job.title, "url": job.url,
                             "visa": v.label, "dry_run": True})
            continue
        m = await score(job, profile, gateway)
        if m.score < min_score:
            dropped["score"] += 1
            continue
        res = await notion_create(job, m, v, discovered=discovered)
        store.mark(url=job.url, title=job.title, org=job.org, source=job.source,
                   notion_page_url=res.get("url"))
        inserted.append({"title": job.title, "url": job.url, "score": m.score,
                         "visa": v.label, "notion": res.get("url")})

    return {"considered": len(jobs), "new": len(new), "eligible": eligible,
            "inserted": 0 if dry_run else len(inserted), "dropped": dropped,
            "dry_run": dry_run, "items": inserted}


async def gather_jobs(settings, queries: list[str] | None = None) -> list:
    """Runtime: pull from each configured source. One source failing never fails
    the whole run."""
    from worker.sources import adzuna, arbeitnow
    from worker.sources.rss import fetch_rss

    queries = queries or ["machine learning", "deep learning", "data scientist",
                          "NLP", "generative AI"]
    out: list = []

    async def _safe(coro):
        try:
            out.extend(await coro)
        except Exception:  # noqa: BLE001 — isolate per-source failures
            pass

    for country in ("gb", "de", "nl", "ca", "au"):
        for q in queries[:2]:
            await _safe(adzuna.fetch(app_id=settings.adzuna_app_id,
                                     app_key=settings.adzuna_app_key,
                                     country=country, what=q))
    await _safe(arbeitnow.fetch())
    # Academic RSS feeds (no key needed)
    for url, src in [
        ("https://www.jobs.ac.uk/feeds/jobs", "jobs.ac.uk"),
        ("https://euraxess.ec.europa.eu/jobs/search/feed", "euraxess"),
    ]:
        await _safe(fetch_rss(url, source=src, track_hint="academic"))
    return out
