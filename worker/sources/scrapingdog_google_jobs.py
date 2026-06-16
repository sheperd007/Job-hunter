"""Google Jobs via Scrapingdog's Google Jobs API.

Google Jobs aggregates postings across many boards (LinkedIn, Indeed, company
career sites, ...), so one query yields cross-board coverage. Scrapingdog renders
the Google Jobs SERP and returns parsed JSON. 1 credit per request.
Docs: https://docs.scrapingdog.com/google-jobs-scraping-api-documentation

IMPORTANT: the location must be embedded in the `query` ("... jobs in United
Kingdom"); the bare `country` param alone returns "There are no jobs for this
query". The API wraps results in `jobs_results`, which is a list of strings (a
"no jobs" message) when empty — guarded below.
"""
from worker.models import Job
from worker.normalize import detect_region
from worker.sources.base import get_json

_API = "https://api.scrapingdog.com/google_jobs"

# country code -> (location phrase for the query, region fallback)
_COUNTRY = {
    "gb": ("United Kingdom", "UK"),
    "de": ("Germany", "EU"),
    "nl": ("Netherlands", "EU"),
    "ca": ("Canada", "Canada"),
    "au": ("Australia", "AU-NZ"),
}


async def fetch(*, api_key: str, what: str = "machine learning",
                country: str = "gb") -> list[Job]:
    if not api_key:
        return []
    place, fallback_region = _COUNTRY.get(country, ("", "Other"))
    query = f"{what} jobs in {place}" if place else f"{what} jobs"
    data = await get_json(_API, params={"api_key": api_key, "query": query,
                                        "country": country})
    rows = data.get("jobs_results", []) if isinstance(data, dict) else []
    jobs: list[Job] = []
    for r in rows:
        if not isinstance(r, dict):        # empty search -> ["There are no jobs ..."]
            continue
        title = (r.get("title") or "").strip()
        # Prefer the DIRECT board link (unique path -> safe dedupe key + lands on the
        # real posting). share_link is a Google-search URL whose id lives in the
        # query string, which canonical_url strips -> would collapse all jobs to one.
        link = (r.get("source_link") or "").strip()
        if not link:
            ao = r.get("apply_options") or []
            if ao and isinstance(ao[0], dict):
                link = (ao[0].get("link") or "").strip()
        if not link:
            link = (r.get("share_link") or "").strip()
        if not link or not title:
            continue
        loc = (r.get("location") or "").strip()
        region = detect_region(loc)
        if region == "Other":              # country is a reliable region signal
            region = fallback_region
        jobs.append(Job(
            title=title,
            org=(r.get("company_name") or "").strip(),
            location=loc,
            url=link,                      # share_link; real Google Jobs listing URL
            source="google_jobs",
            description=(r.get("description") or "").strip(),
            region=region,
            track_hint="industry",
            raw={"via": r.get("via", ""), "extensions": r.get("extensions", []),
                 "country": country},
        ))
    return jobs
