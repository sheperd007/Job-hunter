"""Dedupe discovered jobs against a 'seen' store keyed on canonical URL.

filter_new() only reads — marking happens in the pipeline AFTER a successful
Notion insert, so a failed insert can be retried on the next run.
"""
import re
from typing import Protocol
from worker.models import Job
from worker.normalize import canonical_url
from worker.visa import normalize_org


def content_key_for(job: Job) -> str | None:
    """Source-independent identity for a posting: normalized org + title + region.
    Collapses the SAME role listed on different boards (different URLs). Returns
    None when org is missing (e.g. academic RSS) so those fall back to URL-only
    dedupe rather than colliding by title alone. Region is included so the same
    title in two different regions stays as two distinct postings."""
    org = normalize_org(getattr(job, "org", "") or "")
    title = re.sub(r"[^a-z0-9]+", " ", (getattr(job, "title", "") or "").lower()).strip()
    if not org or not title:
        return None
    return f"{org}|{title}|{getattr(job, 'region', '') or ''}"


class SeenStore(Protocol):
    def is_seen(self, url: str) -> bool: ...
    def is_seen_content(self, content_key: str) -> bool: ...
    def mark(self, *, url: str, title: str, org: str, source: str,
             notion_page_url: str | None = None,
             content_key: str | None = None) -> None: ...


class InMemorySeenStore:
    def __init__(self) -> None:
        self._seen: dict[str, dict] = {}
        self._content: set[str] = set()

    def is_seen(self, url: str) -> bool:
        return canonical_url(url) in self._seen

    def is_seen_content(self, content_key: str) -> bool:
        return bool(content_key) and content_key in self._content

    def mark(self, *, url, title, org, source, notion_page_url=None,
             content_key=None) -> None:
        self._seen[canonical_url(url)] = {
            "title": title, "org": org, "source": source,
            "notion_page_url": notion_page_url,
        }
        if content_key:
            self._content.add(content_key)


class PostgresSeenStore:
    """psycopg imported lazily so the module loads without it installed."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def is_seen(self, url: str) -> bool:
        import psycopg
        with psycopg.connect(self._dsn) as conn:
            row = conn.execute(
                "SELECT 1 FROM seen_jobs WHERE vacancy_url = %s",
                (canonical_url(url),),
            ).fetchone()
        return row is not None

    def is_seen_content(self, content_key: str) -> bool:
        if not content_key:
            return False
        import psycopg
        with psycopg.connect(self._dsn) as conn:
            row = conn.execute(
                "SELECT 1 FROM seen_jobs WHERE content_key = %s",
                (content_key,),
            ).fetchone()
        return row is not None

    def mark(self, *, url, title, org, source, notion_page_url=None,
             content_key=None) -> None:
        import psycopg
        with psycopg.connect(self._dsn) as conn:
            conn.execute(
                "INSERT INTO seen_jobs (vacancy_url, title, org, source, "
                "notion_page_url, content_key) VALUES (%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (vacancy_url) DO NOTHING",
                (canonical_url(url), title, org, source, notion_page_url, content_key),
            )


def filter_new(jobs: list[Job], store: SeenStore) -> list[Job]:
    """Return jobs not already seen, by canonical URL OR content identity
    (org+title+region). De-dupes within this batch on both keys too."""
    out: list[Job] = []
    seen_urls: set[str] = set()
    seen_content: set[str] = set()
    for j in jobs:
        ukey = canonical_url(j.url)
        ckey = content_key_for(j)
        if ukey in seen_urls or store.is_seen(ukey):
            continue
        if ckey and (ckey in seen_content or store.is_seen_content(ckey)):
            continue
        seen_urls.add(ukey)
        if ckey:
            seen_content.add(ckey)
        out.append(j)
    return out
