"""Adzuna jobs API client. Free tier; aggregates many boards across UK/EU/CA/AU.
Docs: https://developer.adzuna.com/  (needs app_id + app_key)
"""
from worker.models import Job
from worker.normalize import detect_region
from worker.sources.base import get_json

_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


async def fetch(*, app_id: str, app_key: str, country: str = "gb",
                what: str = "machine learning", where: str = "",
                results: int = 20, page: int = 1) -> list[Job]:
    if not app_id or not app_key:
        return []
    data = await get_json(
        _URL.format(country=country, page=page),
        params={"app_id": app_id, "app_key": app_key, "what": what,
                "where": where, "results_per_page": results,
                "content-type": "application/json"},
    )
    jobs: list[Job] = []
    for r in data.get("results", []):
        url = r.get("redirect_url", "")
        if not url:
            continue
        loc = (r.get("location") or {}).get("display_name", "")
        jobs.append(Job(
            title=(r.get("title") or "").strip(),
            org=(r.get("company") or {}).get("display_name", ""),
            location=loc,
            url=url,                       # keep the REAL redirect_url (its signed
                                           # `se` token is required; canonicalizing
                                           # is dedup-only, done in worker.dedupe)
            source="adzuna",
            description=r.get("description", ""),
            region=detect_region(loc),
            track_hint="industry",
            raw={"adzuna_id": r.get("id"), "country": country},
        ))
    return jobs
