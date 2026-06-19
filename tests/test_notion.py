import httpx
import respx
import pytest
from worker.notion import build_properties, create_page
from worker.models import Job, MatchResult, VisaVerdict


def fixtures():
    job = Job(title="ML Engineer", org="Acme", location="Berlin, Germany",
              url="https://x.com/1", source="arbeitnow", deadline="2026-07-01")
    match = MatchResult(score=82, rationale="strong ML/RAG fit",
                        track="Industry", tags=["ML", "AI"], priority="High")
    visa = VisaVerdict(label="Sponsors visa", confidence=0.85,
                       evidence="visa_sponsorship flag", eligible=True)
    return job, match, visa


def test_build_properties_maps_fields():
    job, match, visa = fixtures()
    p = build_properties(job, match, visa, discovered="2026-06-12")
    assert p["Position"]["title"][0]["text"]["content"] == "ML Engineer"
    assert p["Stage"]["select"]["name"] == "To apply"
    assert p["Match score"]["number"] == 82
    assert p["Priority"]["select"]["name"] == "High"
    assert p["Visa support"]["select"]["name"] == "Sponsors visa"
    assert p["Source"]["select"]["name"] == "arbeitnow"
    assert p["Track"]["select"]["name"] == "Industry"
    assert {t["name"] for t in p["Tags"]["multi_select"]} == {"ML", "AI"}
    assert p["Deadline"]["date"]["start"] == "2026-07-01"
    assert p["Discovered"]["date"]["start"] == "2026-06-12"


def test_build_properties_uses_effective_score():
    job, match, visa = fixtures()                  # match.score == 82
    p = build_properties(job, match, visa, discovered="2026-06-12",
                         effective_score=89)
    assert p["Match score"]["number"] == 89        # effective drives the sort field
    notes = p["Notes"]["rich_text"][0]["text"]["content"]
    assert "82/100" in notes and "89" in notes     # raw fit + effective both shown


@pytest.mark.asyncio
async def test_create_page_dry_run_skips_api():
    job, match, visa = fixtures()
    out = await create_page(job, match, visa, token="t", database_id="db",
                            version="2022-06-28", discovered="2026-06-12",
                            dry_run=True)
    assert out["dry_run"] is True


@respx.mock
@pytest.mark.asyncio
async def test_create_page_posts_to_notion():
    job, match, visa = fixtures()
    route = respx.post("https://api.notion.com/v1/pages").mock(
        return_value=httpx.Response(200, json={"id": "page-1",
                                               "url": "https://notion.so/page-1"}))
    out = await create_page(job, match, visa, token="secret", database_id="db123",
                            version="2022-06-28", discovered="2026-06-12")
    assert out["id"] == "page-1"
    sent = route.calls[0].request
    assert sent.headers["Authorization"] == "Bearer secret"
    assert sent.headers["Notion-Version"] == "2022-06-28"
