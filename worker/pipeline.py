"""Job-discovery orchestration.

run_discovery() is the pure, injectable core (deps passed in -> unit-tested with
fakes). gather_jobs() is the runtime glue that calls the real source clients.
"""
from worker.dedupe import filter_new, content_key_for
from worker.normalize import in_target_region
from worker.visa import assess, SponsorRegister
from worker.sources.base import get_text
from worker.llm import BudgetExhausted
from worker.match import score


async def run_discovery(*, jobs, profile, gateway, store, notion_create,
                        register=None, min_score: int = 60,
                        max_match: int | None = None,
                        discovered: str, dry_run: bool = False) -> dict:
    new = filter_new(jobs, store)
    inserted: list[dict] = []
    eligible = 0
    scored = 0
    capped = False
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
        # Cost guard: cap LLM scoring per run. Jobs beyond the cap are simply left
        # for a later run (never marked seen), so coverage rolls forward day to day.
        if max_match is not None and scored >= max_match:
            capped = True
            break
        try:
            m = await score(job, profile, gateway)
        except BudgetExhausted:
            # All keys over the monthly cap — stop cleanly, keep what we already
            # inserted, rather than 500-ing and triggering W3 retries. Other
            # RuntimeErrors are real bugs and propagate (must not look like a stop).
            capped = True
            break
        scored += 1
        ckey = content_key_for(job)
        if m.score < min_score:
            # A definitive negative against a stable profile — mark it seen (no
            # Notion page) so it is not re-scored, and re-paid for, every run. This
            # also stops the per-run cap being consumed by the same front-of-list
            # rejects daily, which would starve genuinely new jobs further down.
            store.mark(url=job.url, title=job.title, org=job.org,
                       source=job.source, notion_page_url=None, content_key=ckey)
            dropped["score"] += 1
            continue
        res = await notion_create(job, m, v, discovered=discovered)
        store.mark(url=job.url, title=job.title, org=job.org, source=job.source,
                   notion_page_url=res.get("url"), content_key=ckey)
        inserted.append({"title": job.title, "url": job.url, "score": m.score,
                         "visa": v.label, "notion": res.get("url")})

    return {"considered": len(jobs), "new": len(new), "eligible": eligible,
            "scored": scored, "inserted": 0 if dry_run else len(inserted),
            "dropped": dropped, "capped": capped, "dry_run": dry_run,
            "items": inserted}


async def load_register(settings, *, fetch=None) -> SponsorRegister | None:
    """Best-effort load of the licensed-sponsor register from a configured CSV
    URL. Returns None (soft gate still surfaces jobs) when the URL is unset or the
    fetch/parse fails — a missing register must never break discovery."""
    url = getattr(settings, "sponsor_register_url", "")
    if not url:
        return None
    fetch = fetch or get_text
    try:
        text = await fetch(url)
        return SponsorRegister.from_csv_text(text)
    except Exception:  # noqa: BLE001 — register is an enhancement, never fatal
        return None


async def gather_jobs(settings, queries: list[str] | None = None) -> list:
    """Runtime: pull from each configured source. One source failing never fails
    the whole run."""
    from worker.sources import adzuna, arbeitnow, scrapingdog_indeed
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
    # Indeed via Scrapingdog (no official Indeed API). Only runs when a key is set.
    # Medium credit guard: 3 queries x 5 countries = 15 requests/run (~15 credits).
    if settings.scrapingdog_key:
        for country in ("gb", "de", "nl", "ca", "au"):
            for q in queries[:3]:
                await _safe(scrapingdog_indeed.fetch(
                    api_key=settings.scrapingdog_key, country=country, what=q))
    # Academic RSS feeds (no key needed)
    for url, src in [
        ("https://www.jobs.ac.uk/feeds/jobs", "jobs.ac.uk"),
        ("https://euraxess.ec.europa.eu/jobs/search/feed", "euraxess"),
    ]:
        await _safe(fetch_rss(url, source=src, track_hint="academic"))
    return out
