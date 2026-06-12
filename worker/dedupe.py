"""Dedupe discovered jobs against a 'seen' store keyed on canonical URL.

filter_new() only reads — marking happens in the pipeline AFTER a successful
Notion insert, so a failed insert can be retried on the next run.
"""
from typing import Protocol
from worker.models import Job
from worker.normalize import canonical_url


class SeenStore(Protocol):
    def is_seen(self, url: str) -> bool: ...
    def mark(self, *, url: str, title: str, org: str, source: str,
             notion_page_url: str | None = None) -> None: ...


class InMemorySeenStore:
    def __init__(self) -> None:
        self._seen: dict[str, dict] = {}

    def is_seen(self, url: str) -> bool:
        return canonical_url(url) in self._seen

    def mark(self, *, url, title, org, source, notion_page_url=None) -> None:
        self._seen[canonical_url(url)] = {
            "title": title, "org": org, "source": source,
            "notion_page_url": notion_page_url,
        }


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

    def mark(self, *, url, title, org, source, notion_page_url=None) -> None:
        import psycopg
        with psycopg.connect(self._dsn) as conn:
            conn.execute(
                "INSERT INTO seen_jobs (vacancy_url, title, org, source, notion_page_url) "
                "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (vacancy_url) DO NOTHING",
                (canonical_url(url), title, org, source, notion_page_url),
            )


def filter_new(jobs: list[Job], store: SeenStore) -> list[Job]:
    """Return jobs whose canonical URL is not already in the store.
    Also de-dupes within this batch."""
    out: list[Job] = []
    batch: set[str] = set()
    for j in jobs:
        key = canonical_url(j.url)
        if key in batch or store.is_seen(key):
            continue
        batch.add(key)
        out.append(j)
    return out
