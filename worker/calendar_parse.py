"""Detect a meeting/interview request in an email and extract an event proposal.

Proposal only — n8n creates the Google Calendar event ONLY after approval
(Phase 4). Routes via the triage (cheap) lane.
"""
from worker.match import _extract_json

SYSTEM = (
    "Detect whether the email proposes or requests a meeting, call or interview. "
    "If yes, extract the event details. Reply ONLY with JSON: {\"is_event\": bool, "
    "\"title\": str, \"start\": ISO-8601 datetime or \"\", \"end\": ISO-8601 "
    "datetime or \"\", \"timezone\": IANA tz or \"\", \"location\": str (room or "
    "video link), \"notes\": str}. If there is no meeting, set is_event to false."
)


async def parse_event(email: dict, gateway) -> dict:
    user = (f"From: {email.get('from', '')}\n"
            f"Subject: {email.get('subject', '')}\n\n"
            f"{(email.get('body', '') or '')[:6000]}")
    resp = await gateway.complete("triage", [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user},
    ])
    data = _extract_json(resp.get("content", ""))
    is_event = bool(data.get("is_event", False))
    return {
        "is_event": is_event,
        "title": data.get("title", "") if is_event else "",
        "start": data.get("start", "") if is_event else "",
        "end": data.get("end", "") if is_event else "",
        "timezone": data.get("timezone", "") if is_event else "",
        "location": data.get("location", "") if is_event else "",
        "notes": data.get("notes", "") if is_event else "",
    }
