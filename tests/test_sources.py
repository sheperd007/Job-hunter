import httpx
import respx
import pytest
from worker.sources import adzuna, arbeitnow, scrapingdog_indeed
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


@respx.mock
@pytest.mark.asyncio
async def test_scrapingdog_indeed_maps_array_response():
    # Indeed Scraper API returns a JSON ARRAY of job objects; the trailing element
    # is search metadata (totalJobs, no jobLink) and must be dropped.
    respx.get(url__startswith="https://api.scrapingdog.com/indeed").mock(
        return_value=httpx.Response(200, json=[
            {"jobTitle": "ML Engineer ", "companyName": "Acme",
             "companyLocation": "London", "jobLink": "https://uk.indeed.com/viewjob?jk=1",
             "jobDescription": "Build models", "Salary": "£70k",
             "jobMetaData": ["Full-time"], "jobPosting": "Today"},
            {"jobTitle": "no link job", "companyName": "X"},        # dropped: no jobLink
            {"totalJobs": "120", "jobTitle": "machine learning"},   # metadata tail, dropped
        ]))
    jobs = await scrapingdog_indeed.fetch(api_key="k", what="ml", country="gb")
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "ML Engineer" and j.org == "Acme"
    assert j.source == "indeed" and j.track_hint == "industry"
    assert j.region == "UK"
    assert j.url == "https://uk.indeed.com/viewjob?jk=1"   # absolute link kept verbatim
    assert j.raw["salary"] == "£70k" and j.raw["posted"] == "Today"
    assert j.raw["country"] == "gb"


@pytest.mark.asyncio
async def test_scrapingdog_indeed_no_key_returns_empty():
    assert await scrapingdog_indeed.fetch(api_key="") == []


@respx.mock
@pytest.mark.asyncio
async def test_scrapingdog_indeed_resolves_relative_link():
    # Indeed often returns a relative jobLink; it must be made absolute against the
    # country domain so the URL is a valid dedupe key and a clickable Notion link.
    respx.get(url__startswith="https://api.scrapingdog.com/indeed").mock(
        return_value=httpx.Response(200, json=[
            {"jobTitle": "DS", "companyName": "Y", "companyLocation": "London",
             "jobLink": "/rc/clk?jk=abc", "jobDescription": "x"},
        ]))
    jobs = await scrapingdog_indeed.fetch(api_key="k", country="gb")
    assert jobs[0].url == "https://uk.indeed.com/rc/clk?jk=abc"


@respx.mock
@pytest.mark.asyncio
async def test_scrapingdog_indeed_region_falls_back_to_country():
    # When the location string is unrecognized, the searched country fixes the
    # region so the job still passes the in-target-region gate (de -> EU).
    respx.get(url__startswith="https://api.scrapingdog.com/indeed").mock(
        return_value=httpx.Response(200, json=[
            {"jobTitle": "ML", "companyName": "Z", "companyLocation": "Stuttgart",
             "jobLink": "https://de.indeed.com/viewjob?jk=2", "jobDescription": "x"},
        ]))
    jobs = await scrapingdog_indeed.fetch(api_key="k", country="de")
    assert jobs[0].region == "EU"


@respx.mock
@pytest.mark.asyncio
async def test_scrapingdog_indeed_remote_beats_country_fallback():
    # A remote job (signalled in jobMetaData, with no usable location) must key as
    # Remote — NOT the country fallback — so it dedupes against the same remote role
    # from other boards instead of leaking a duplicate under an EU/UK region.
    respx.get(url__startswith="https://api.scrapingdog.com/indeed").mock(
        return_value=httpx.Response(200, json=[
            {"jobTitle": "ML", "companyName": "Z", "companyLocation": "",
             "jobLink": "https://de.indeed.com/viewjob?jk=3",
             "jobMetaData": ["Full-time", "Remote"], "jobDescription": "x"},
        ]))
    jobs = await scrapingdog_indeed.fetch(api_key="k", country="de")
    assert jobs[0].region == "Remote"


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
