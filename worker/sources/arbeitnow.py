"""Arbeitnow job-board API. Free, no key. Exposes a `visa_sponsorship` flag —
valuable for the visa filter. EU/Germany heavy.
Docs: https://www.arbeitnow.com/api
"""
from worker.models import Job
from worker.normalize import canonical_url, detect_region
from worker.sources.base import get_json

_URL = "https://www.arbeitnow.com/api/job-board-api"


async def fetch(*, page: int = 1) -> list[Job]:
    data = await get_json(_URL, params={"page": page})
    jobs: list[Job] = []
    for r in data.get("data", []):
        url = r.get("url", "")
        if not url:
            continue
        loc = r.get("location", "")
        remote = bool(r.get("remote"))
        jobs.append(Job(
            title=r.get("title", ""),
            org=r.get("company_name", ""),
            location=loc,
            url=canonical_url(url),
            source="arbeitnow",
            description=r.get("description", ""),
            region=detect_region("remote" if remote else loc),
            track_hint="industry",
            raw={"visa_sponsorship": bool(r.get("visa_sponsorship")),
                 "tags": r.get("tags", [])},
        ))
    return jobs
