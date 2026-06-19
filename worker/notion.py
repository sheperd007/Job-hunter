"""Idempotent insert of a matched job into the Notion Career Hub > Applications
database. Idempotency is enforced upstream by dedupe (seen_jobs); this module
just creates the page. Uses the stable 2022-06-28 API (single data source ->
create-page by database_id, properties mapped by name).
"""
import httpx
from worker.models import Job, MatchResult, VisaVerdict

_API = "https://api.notion.com/v1/pages"
_MAX = 2000  # Notion rich_text content limit per text object


def _rt(text: str) -> dict:
    return {"rich_text": [{"text": {"content": (text or "")[:_MAX]}}]}


def build_properties(job: Job, match: MatchResult, visa: VisaVerdict,
                     discovered: str, effective_score: int | None = None) -> dict:
    # "Match score" is the Notion view's sort key. When an effective (visa-aware)
    # score is supplied, write that so relocation/visa jobs rise to the top; keep
    # the raw fit visible in Notes for transparency.
    shown = match.score if effective_score is None else effective_score
    notes = (f"Match {match.score}/100"
             + ("" if effective_score is None else f" (effective {effective_score})")
             + f" — {match.rationale}\n"
             f"Visa: {visa.label} ({visa.confidence:.0%}) — {visa.evidence}\n"
             f"Org: {job.org}")
    props: dict = {
        "Position": {"title": [{"text": {"content": (job.title or "Untitled")[:_MAX]}}]},
        "Vacancy link": {"url": job.url or None},
        "Stage": {"select": {"name": "To apply"}},
        "Location": _rt(job.location),
        "Match score": {"number": shown},
        "Priority": {"select": {"name": match.priority}},
        "Visa support": {"select": {"name": visa.label}},
        "Source": {"select": {"name": job.source or "Other"}},
        "Discovered": {"date": {"start": discovered}},
        "Notes": _rt(notes),
    }
    if match.track:
        props["Track"] = {"select": {"name": match.track}}
    if match.tags:
        props["Tags"] = {"multi_select": [{"name": t} for t in match.tags]}
    if job.deadline:
        props["Deadline"] = {"date": {"start": job.deadline}}
    return props


async def create_page(job: Job, match: MatchResult, visa: VisaVerdict, *,
                      token: str, database_id: str, version: str,
                      discovered: str, dry_run: bool = False,
                      effective_score: int | None = None) -> dict:
    if dry_run:
        return {"dry_run": True, "title": job.title}
    payload = {"parent": {"database_id": database_id},
               "properties": build_properties(job, match, visa, discovered,
                                              effective_score=effective_score)}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(_API, headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": version,
            "Content-Type": "application/json",
        }, json=payload)
    r.raise_for_status()
    return r.json()
