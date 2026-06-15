import httpx
import respx
import pytest
from worker.sources import adzuna, arbeitnow
from worker.sources.rss import parse_rss


@respx.mock
@pytest.mark.asyncio
async def test_adzuna_maps_results():
    respx.get(url__startswith="https://api.adzuna.com/v1/api/jobs/gb/search/1").mock(
        return_value=httpx.Response(200, json={"results": [{
            "id": "42", "title": "ML Engineer ",
            "company": {"display_name": "Acme"},
            "location": {"display_name": "London, UK"},
            "redirect_url": "https://adzuna.example/job/42?utm=x",
            "description": "Build models",
        }, {"title": "no url job"}]}))
    jobs = await adzuna.fetch(app_id="id", app_key="key", what="ml")
    assert len(jobs) == 1                       # second result dropped (no url)
    j = jobs[0]
    assert j.title == "ML Engineer" and j.org == "Acme"
    assert j.region == "UK" and j.source == "adzuna"
    assert j.url == "https://adzuna.example/job/42?utm=x"   # REAL url kept (link must work)
    assert j.track_hint == "industry"


@pytest.mark.asyncio
async def test_adzuna_no_keys_returns_empty():
    assert await adzuna.fetch(app_id="", app_key="") == []


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
