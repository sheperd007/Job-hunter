"""Email triage + draft reply via the LLM gateway (triage lane, cheap model).

Draft-only: this returns a draft string; n8n saves it as a Gmail DRAFT and never
sends. Pure-ish — inject a gateway with `async complete(task, messages)`.
"""
from worker.match import _extract_json

CATEGORIES = {"job", "recruiter", "interview", "networking", "personal",
              "newsletter", "spam", "other"}

SYSTEM = (
    "You are an email assistant for {owner}, who is job-hunting abroad (ML/Data "
    "Science, seeking visa sponsorship). Classify the email and, if it needs a "
    "reply, draft a concise, professional reply in the owner's first-person voice "
    "with NO placeholders (no [name]/[date]) — if a fact is unknown, phrase around "
    "it. Reply ONLY with JSON: {{\"category\": one of "
    "[\"job\",\"recruiter\",\"interview\",\"networking\",\"personal\",\"newsletter\",\"spam\",\"other\"], "
    "\"urgency\": one of [\"high\",\"normal\",\"low\"], \"needs_reply\": bool, "
    "\"draft\": str (empty if needs_reply is false), \"summary\": str}}."
)


async def triage_email(email: dict, gateway, owner: str = "the owner") -> dict:
    user = (f"From: {email.get('from', '')}\n"
            f"Subject: {email.get('subject', '')}\n\n"
            f"{(email.get('body', '') or '')[:6000]}")
    resp = await gateway.complete("triage", [
        {"role": "system", "content": SYSTEM.format(owner=owner)},
        {"role": "user", "content": user},
    ])
    data = _extract_json(resp.get("content", ""))
    category = data.get("category", "other")
    if category not in CATEGORIES:
        category = "other"
    needs_reply = bool(data.get("needs_reply", False))
    draft = data.get("draft", "") if needs_reply else ""
    return {
        "category": category,
        "urgency": data.get("urgency", "normal"),
        "needs_reply": needs_reply,
        "draft": draft,
        "summary": data.get("summary", ""),
    }
