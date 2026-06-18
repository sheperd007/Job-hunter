import httpx
import respx
import pytest
from worker.sources import arbeitnow
from worker.sources import scrapingdog_google_jobs as gjobs
from worker.sources.rss import parse_rss


@respx.mock
@pytest.mark.asyncio
async def test_arbeitnow_maps_visa_flag():
    respx.get("https://www.arbeitnow.com/api/job-board-api").mock(
        return_value=httpx.Response(200, json={"data": [{
            "title": "Data Scientist", "company_name": "BerlinCo",
            "location": "Berlin", "url": "https://arbeitnow.example/x",
            "description": "NLP role", "remote": False,
            "visa_sponsorship": True, "tags": ["python"],
        }]}))
    jobs = await arbeitnow.fetch()
    assert len(jobs) == 1
    assert jobs[0].raw["visa_sponsorship"] is True
    assert jobs[0].region == "EU"


@respx.mock
@pytest.mark.asyncio
async def test_google_jobs_maps_results():
    # Each job's URL must be the DIRECT board link (source_link) — the share_link is
    # a Google-search URL whose uniqueness lives in the query string, which
    # canonical_url strips, so it would collapse every job to one dedupe key.
    respx.get(url__startswith="https://api.scrapingdog.com/google_jobs").mock(
        return_value=httpx.Response(200, json={"jobs_results": [
            {"title": "ML Engineer ", "company_name": "Acme",
             "location": "London, UK", "via": "via LinkedIn",
             "source_link": "https://uk.linkedin.com/jobs/view/ml-eng-123",
             "share_link": "https://www.google.com/search?q=ml#fpstate=tldetail",
             "apply_options": [{"title": "LinkedIn", "link": "https://linkedin.com/x"}],
             "description": "Build models", "extensions": ["Full-time"]},
            {"title": "no link", "company_name": "X"},        # dropped: no link at all
        ]}))
    jobs = await gjobs.fetch(api_key="k", what="machine learning", country="gb")
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "ML Engineer" and j.org == "Acme"
    assert j.source == "google_jobs" and j.track_hint == "industry"
    assert j.region == "UK"
    assert j.url == "https://uk.linkedin.com/jobs/view/ml-eng-123"   # source_link wins
    assert j.raw["via"] == "via LinkedIn" and j.raw["country"] == "gb"


@respx.mock
@pytest.mark.asyncio
async def test_google_jobs_url_falls_back_apply_then_share():
    respx.get(url__startswith="https://api.scrapingdog.com/google_jobs").mock(
        return_value=httpx.Response(200, json={"jobs_results": [
            {"title": "A", "company_name": "C", "location": "London",
             "apply_options": [{"title": "Co", "link": "https://co.com/job/1"}]},   # no source_link
            {"title": "B", "company_name": "C", "location": "London",
             "share_link": "https://www.google.com/search?q=b"},                    # only share_link
        ]}))
    jobs = await gjobs.fetch(api_key="k", what="ml", country="gb")
    assert [j.url for j in jobs] == ["https://co.com/job/1",
                                     "https://www.google.com/search?q=b"]


@pytest.mark.asyncio
async def test_google_jobs_no_key_returns_empty():
    assert await gjobs.fetch(api_key="") == []


@respx.mock
@pytest.mark.asyncio
async def test_google_jobs_empty_message_no_crash():
    # Empty searches return jobs_results = ["There are no jobs for this query"]
    # (a list of strings, not dicts) — must not crash.
    respx.get(url__startswith="https://api.scrapingdog.com/google_jobs").mock(
        return_value=httpx.Response(200, json={"jobs_results": ["There are no jobs for this query"]}))
    assert await gjobs.fetch(api_key="k", what="ml", country="gb") == []


@respx.mock
@pytest.mark.asyncio
async def test_google_jobs_region_falls_back_to_country():
    respx.get(url__startswith="https://api.scrapingdog.com/google_jobs").mock(
        return_value=httpx.Response(200, json={"jobs_results": [
            {"title": "ML", "company_name": "Z", "location": "Stuttgart",
             "share_link": "https://g/2", "description": "x"},
        ]}))
    jobs = await gjobs.fetch(api_key="k", country="de")
    assert jobs[0].region == "EU" and jobs[0].source == "google_jobs"


def test_parse_rss():
    xml = """<?xml version='1.0'?><rss><channel>
      <item><title>PostDoc in Machine Learning</title>
            <link>https://jobs.ac.uk/job/123/</link>
            <description>University of Cambridge, UK</description></item>
      <item><title>No link</title><link></link></item>
    </channel></rss>"""
    jobs = parse_rss(xml, source="jobs.ac.uk", track_hint="academic")
    assert len(jobs) == 1
    assert jobs[0].source == "jobs.ac.uk"
    assert jobs[0].track_hint == "academic"
    assert jobs[0].url == "https://jobs.ac.uk/job/123/"   # REAL link kept verbatim
    assert jobs[0].region == "UK"
