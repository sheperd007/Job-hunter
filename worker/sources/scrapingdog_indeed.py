"""Indeed via Scrapingdog's dedicated Indeed Scraper API.

Indeed has no usable official job-search API (the Publisher Job Search API is
deprecated), so we go through Scrapingdog, which renders an Indeed search URL and
returns parsed JSON. 1 credit per request.
Docs: https://docs.scrapingdog.com/indeed-scraper-api

The API returns a JSON *array* of job objects; the trailing element is search
metadata (totalJobs, no jobLink) — it is dropped naturally by the no-link guard.
"""
from urllib.parse import urlencode
from worker.models import Job
from worker.normalize import detect_region
from worker.sources.base import get_json

_API = "https://api.scrapingdog.com/indeed"

# Indeed search domain per country code.
_DOMAIN = {
    "gb": "uk.indeed.com", "de": "de.indeed.com", "nl": "nl.indeed.com",
    "ca": "ca.indeed.com", "au": "au.indeed.com",
}
# Region fallback when the location string is unrecognized (the searched country
# is a reliable region signal even if the city keyword isn't in our buckets).
_COUNTRY_REGION = {"gb": "UK", "de": "EU", "nl": "EU", "ca": "Canada", "au": "AU-NZ"}


def _indeed_url(*, what: str, where: str, domain: str) -> str:
    return f"https://{domain}/jobs?{urlencode({'q': what, 'l': where})}"


async def fetch(*, api_key: str, what: str = "machine learning",
                country: str = "gb", where: str = "") -> list[Job]:
    if not api_key:
        return []
    domain = _DOMAIN.get(country, "www.indeed.com")
    target = _indeed_url(what=what, where=where, domain=domain)
    data = await get_json(_API, params={"api_key": api_key, "url": target})
    rows = data if isinstance(data, list) else data.get("jobs", [])
    jobs: list[Job] = []
    for r in rows:
        link = (r.get("jobLink") or "").strip()
        title = (r.get("jobTitle") or "").strip()
        if not link or not title:          # drops the trailing metadata element too
            continue
        if link.startswith("/"):           # Indeed often returns a relative path;
            link = f"https://{domain}{link}"  # make it absolute (dedupe key + link)
        loc = (r.get("companyLocation") or "").strip()
        meta = r.get("jobMetaData") or []
        # Remote wins over the country fallback: a remote role must key as "Remote"
        # (matching other boards) so it dedupes instead of leaking under EU/UK.
        remote = "remote" in loc.lower() or any("remote" in str(m).lower() for m in meta)
        if remote:
            region = "Remote"
        else:
            region = detect_region(loc)
            if region == "Other":
                region = _COUNTRY_REGION.get(country, "Other")
        jobs.append(Job(
            title=title,
            org=(r.get("companyName") or "").strip(),
            location=loc,
            url=link,                      # real link; canonicalization is dedup-only
            source="indeed",
            description=(r.get("jobDescription") or "").strip(),
            region=region,
            track_hint="industry",
            raw={"salary": r.get("Salary", ""),
                 "posted": r.get("jobPosting", ""),
                 "meta": r.get("jobMetaData", []),
                 "country": country},
        ))
    return jobs
