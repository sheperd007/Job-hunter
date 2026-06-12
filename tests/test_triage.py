import pytest
from worker.triage import triage_email
from worker.calendar_parse import parse_event


class FakeGateway:
    def __init__(self, content):
        self.content = content
        self.calls = []

    async def complete(self, task, messages):
        self.calls.append(task)
        return {"content": self.content}


@pytest.mark.asyncio
async def test_triage_needs_reply_returns_draft():
    gw = FakeGateway('{"category": "recruiter", "urgency": "high", '
                     '"needs_reply": true, "draft": "Thanks for reaching out...", '
                     '"summary": "Recruiter for ML role"}')
    out = await triage_email({"from": "r@co.com", "subject": "ML role",
                              "body": "Are you interested?"}, gw)
    assert out["category"] == "recruiter"
    assert out["needs_reply"] is True
    assert out["draft"].startswith("Thanks")
    assert gw.calls == ["triage"]            # cheap lane


@pytest.mark.asyncio
async def test_triage_no_reply_clears_draft():
    gw = FakeGateway('{"category": "newsletter", "needs_reply": false, '
                     '"draft": "should be ignored"}')
    out = await triage_email({"subject": "Weekly digest"}, gw)
    assert out["needs_reply"] is False
    assert out["draft"] == ""                 # draft cleared when no reply needed


@pytest.mark.asyncio
async def test_triage_bad_category_defaults_other():
    gw = FakeGateway('{"category": "weird", "needs_reply": false}')
    out = await triage_email({}, gw)
    assert out["category"] == "other"


@pytest.mark.asyncio
async def test_parse_event_extracts():
    gw = FakeGateway('{"is_event": true, "title": "Interview with Acme", '
                     '"start": "2026-06-20T10:00:00", "end": "2026-06-20T10:30:00", '
                     '"timezone": "Europe/Berlin", "location": "Zoom", "notes": ""}')
    out = await parse_event({"subject": "Interview", "body": "Mon 10am?"}, gw)
    assert out["is_event"] is True
    assert out["title"] == "Interview with Acme"
    assert out["timezone"] == "Europe/Berlin"


@pytest.mark.asyncio
async def test_parse_event_none_blanks_fields():
    gw = FakeGateway('{"is_event": false, "title": "leak"}')
    out = await parse_event({"subject": "FYI"}, gw)
    assert out["is_event"] is False
    assert out["title"] == ""
