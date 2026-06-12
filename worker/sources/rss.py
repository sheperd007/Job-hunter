"""Generic RSS source. Used for EURAXESS, jobs.ac.uk, AcademicTransfer, Nature
Careers and other academic feeds that publish RSS.

parse_rss() is pure (no network) so it is unit-tested directly; fetch_rss()
wraps it with an HTTP GET.
"""
import xml.etree.ElementTree as ET
from worker.models import Job
from worker.normalize import canonical_url, detect_region
from worker.sources.base import get_text


def parse_rss(text: str, *, source: str, track_hint: str = "academic",
              region_hint: str = "") -> list[Job]:
    root = ET.fromstring(text)
    jobs: list[Job] = []
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        title = (it.findtext("title") or "").strip()
        if not link or not title:
            continue
        desc = (it.findtext("description") or "").strip()
        region = detect_region(f"{title} {desc} {region_hint}")
        if region == "Other" and region_hint:
            region = region_hint
        jobs.append(Job(
            title=title,
            url=canonical_url(link),
            source=source,
            description=desc,
            region=region,
            track_hint=track_hint,
            raw={},
        ))
    return jobs


async def fetch_rss(url: str, *, source: str, track_hint: str = "academic",
                    region_hint: str = "") -> list[Job]:
    text = await get_text(url)
    return parse_rss(text, source=source, track_hint=track_hint,
                     region_hint=region_hint)
