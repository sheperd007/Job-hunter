"""Job-discovery orchestration.

run_discovery() is the pure, injectable core (deps passed in -> unit-tested with
fakes). gather_jobs() is the runtime glue that calls the real source clients.
"""
from itertools import zip_longest
from worker.dedupe import filter_new, content_key_for
from worker.normalize import in_target_region
from worker.visa import assess, reconcile, SponsorRegister
from worker.sources.base import get_text
from worker.llm import BudgetExhausted
from worker.match import score, effective_score


def _interleave(lists: list[list]) -> list:
    """Round-robin merge several source lists into one (source 0 item 0, source 1
    item 0, ..., source 0 item 1, ...). Keeps the per-run scoring cap from being
    monopolized by whichever source is gathered first."""
    out: list = []
    for tup in zip_longest(*lists):
        out.extend(x for x in tup if x is not None)
    return out


async def run_discovery(*, jobs, profile, gateway, store, notion_create,
                        register=None, min_score: int = 60,
                        max_match: int | None = None,
                        discovered: str, dry_run: bool = False,
                        visa_rank_weight: int = 0,
                        visa_min_conf: float = 0.6) -> dict:
    new = filter_new(jobs, store)
    inserted: list[dict] = []
    scored = 0
    capped = False
    dropped = {"region": 0, "visa": 0, "score": 0}

    # Phase 1: cheap region + visa gate on every new job (pure, no LLM). Collect the
    # eligible (job, verdict) pairs and tally drops.
    gated: list[tuple] = []
    for job in new:
        if not in_target_region(job.region):
            dropped["region"] += 1
            continue
        v = assess(job=job, register=register, academic=(job.track_hint == "academic"))
        if not v.eligible:
            dropped["visa"] += 1
            continue
        gated.append((job, v))
    eligible = len(gated)

    # Score the most-likely-to-relocate jobs first so the per-run cap is spent on
    # signal-bearing roles (register/source-flag/keyword) before "Unclear" ones.
    # Stable sort preserves the source interleave within a confidence band.
    gated.sort(key=lambda jv: jv[1].confidence, reverse=True)

    for job, v in gated:
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
        # Refine the keyword verdict with the LLM's JD-aware visa intent (same call,
        # no extra cost), then compute the visa-aware Notion ranking score.
        v = reconcile(v, m, min_conf=visa_min_conf)
        eff = effective_score(m.score, v.confidence, visa_rank_weight)
        res = await notion_create(job, m, v, discovered=discovered,
                                  effective_score=eff if visa_rank_weight else None)
        store.mark(url=job.url, title=job.title, org=job.org, source=job.source,
                   notion_page_url=res.get("url"), content_key=ckey)
        inserted.append({"title": job.title, "url": job.url, "score": m.score,
                         "effective": eff, "visa": v.label, "notion": res.get("url")})

    return {"considered": len(jobs), "new": len(new), "eligible": eligible,
            "scored": scored, "inserted": 0 if dry_run else len(inserted),
            "dropped": dropped, "capped": capped, "dry_run": dry_run,
            "items": inserted}


# gov.uk content API for the UK Home Office "Register of licensed sponsors:
# workers" publication. The CSV asset filename rotates daily, so we resolve the
# current link from the stable API rather than hardcoding a CSV URL.
_GOVUK_WORKERS_API = ("https://www.gov.uk/api/content/government/publications/"
                      "register-of-licensed-sponsors-workers")
_GOVUK_SENTINEL = "govuk:workers"


async def resolve_register_url(url: str, *, fetch_json=None) -> str | None:
    """If `url` is the gov.uk sentinel, resolve the current CSV link via the gov.uk
    content API (the published CSV filename rotates daily); otherwise return `url`
    unchanged. Best-effort: returns None on any failure so discovery still runs."""
    if url != _GOVUK_SENTINEL:
        return url
    if fetch_json is None:
        from worker.sources.base import get_json
        fetch_json = get_json
    try:
        data = await fetch_json(_GOVUK_WORKERS_API)
        for att in (data.get("details", {}) or {}).get("attachments", []) or []:
            u = (att.get("url") or "")
            if u.lower().endswith(".csv"):
                return u
    except Exception:  # noqa: BLE001 — resolver is best-effort, never fatal
        return None
    return None


async def load_register(settings, *, fetch=None,
                        fetch_json=None) -> SponsorRegister | None:
    """Best-effort load of the licensed-sponsor register from a configured CSV
    URL (or the `govuk:workers` sentinel, auto-resolved). Returns None (soft gate
    still surfaces jobs) when unset or the resolve/fetch/parse fails — a missing
    register must never break discovery."""
    url = getattr(settings, "sponsor_register_url", "")
    if not url:
        return None
    url = await resolve_register_url(url, fetch_json=fetch_json)
    if not url:
        return None
    fetch = fetch or get_text
    try:
        text = await fetch(url)
        return SponsorRegister.from_csv_text(text)
    except Exception:  # noqa: BLE001 — register is an enhancement, never fatal
        return None


def _google_queries(base: list[str], suffixes: list[str], cap: int) -> list[str]:
    """Build the Google Jobs query list: base terms plus visa/relocation-suffixed
    variants of the top term, bounded by `cap` (credit guard)."""
    out = list(base)
    if base and suffixes:
        out += [f"{base[0]} {s}" for s in suffixes]
    return out[:cap]


async def gather_jobs(settings, queries: list[str] | None = None) -> list:
    """Runtime: pull from each configured source into its own bucket, then
    round-robin interleave so the per-run scoring cap samples every source. One
    source failing never fails the whole run."""
    from worker.sources import arbeitnow, scrapingdog_google_jobs
    from worker.sources.rss import fetch_rss

    queries = queries or ["machine learning", "deep learning", "data scientist",
                          "NLP", "generative AI"]

    async def _collect(coros: list) -> list:
        bucket: list = []
        for coro in coros:
            try:
                bucket.extend(await coro)
            except Exception:  # noqa: BLE001 — isolate per-source failures
                pass
        return bucket

    arbeitnow_jobs = await _collect([arbeitnow.fetch()])
    # Google Jobs via Scrapingdog (aggregates Indeed/Glassdoor/LinkedIn/company
    # sites). Only runs when a key is set. Queries are biased toward visa/relocation
    # and capped: google_query_cap x 5 countries credits/run (default 3 x 5 = 15).
    g_queries = _google_queries(queries[:2],
                                getattr(settings, "visa_query_suffixes", []),
                                getattr(settings, "google_query_cap", 2))
    google_jobs = await _collect([
        scrapingdog_google_jobs.fetch(api_key=settings.scrapingdog_key,
                                      country=country, what=q)
        for country in ("gb", "de", "nl", "ca", "au") for q in g_queries]
    ) if settings.scrapingdog_key else []
    # Academic RSS feeds (no key needed)
    rss_jobs = await _collect([
        fetch_rss(url, source=src, track_hint="academic")
        for url, src in [("https://www.jobs.ac.uk/feeds/jobs", "jobs.ac.uk"),
                         ("https://euraxess.ec.europa.eu/jobs/search/feed", "euraxess")]])

    return _interleave([arbeitnow_jobs, google_jobs, rss_jobs])
