"""Score a job against the owner's resume profile via the LLM gateway.

All model access goes through the gateway (the Budget-Guard chokepoint). This
module is pure-ish: inject a gateway with `async complete(task, messages)`.
"""
import json
import re
from worker.models import Job, MatchResult

ALLOWED_TAGS = {"stat", "ML", "AI", "NLP", "XAI", "HCI", "Bioinformatics",
                "Big data", "Generative AI", "Data Science"}
ALLOWED_TRACKS = {"Academic - PhD", "Academic - PostDoc",
                  "Academic - Lectureship/Faculty", "Industry"}
ALLOWED_VISA_INTENTS = {"sponsors", "relocation", "unclear", "negative"}

SYSTEM = (
    "You are a precise job-matching assistant for an applicant whose profile is "
    "given. Score how well the JOB fits the applicant's SKILLS and demonstrated "
    "impact. The applicant targets ML / Deep Learning / Generative AI roles in "
    "high-growth fields (academic and industry). IGNORE any 'research interests' "
    "prose; weight concrete skills, experience, and publications. ALSO classify the "
    "JOB's visa/relocation stance ONLY from explicit text about visa sponsorship, "
    "relocation, or right-to-work — never infer sponsorship from company size or "
    "prestige; if the JD says nothing explicit use intent \"unclear\" with low "
    "confidence, and \"negative\" only for an explicit refusal to sponsor. Reply "
    "ONLY with JSON: {\"score\": int 0-100, \"rationale\": str, \"track\": one of "
    f"{sorted(ALLOWED_TRACKS)}, \"tags\": subset of {sorted(ALLOWED_TAGS)}, "
    "\"visa\": {\"intent\": one of [\"sponsors\",\"relocation\",\"unclear\","
    "\"negative\"], \"confidence\": number 0-1, \"evidence\": str}}."
)


def build_messages(profile: dict, job: Job) -> list[dict]:
    user = (
        f"PROFILE:\n{json.dumps(profile, ensure_ascii=False)}\n\n"
        f"JOB:\nTitle: {job.title}\nOrg: {job.org}\nLocation: {job.location}\n"
        f"Source: {job.source}\nDescription:\n{job.description[:4000]}"
    )
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": user}]


def _extract_json(text: str) -> dict:
    t = text.strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", t, flags=re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


def _priority(score: int) -> str:
    if score >= 80:
        return "High"
    if score >= 60:
        return "Medium"
    return "Low"


def effective_score(match_score: int, visa_confidence: float, weight: int) -> int:
    """Visa-aware Notion ranking score: nudge the raw fit by visa confidence,
    centred at 0.5 (the soft-gate "Unclear" baseline is below it -> penalty;
    sponsor/relocation signals are above -> boost). weight=0 -> raw score."""
    eff = round(match_score + weight * (visa_confidence - 0.5))
    return max(0, min(100, eff))


def _parse_visa(data: dict) -> tuple[str, float, str]:
    visa = data.get("visa")
    if not isinstance(visa, dict):
        visa = {}
    intent = visa.get("intent", "unclear")
    if intent not in ALLOWED_VISA_INTENTS:
        intent = "unclear"
    try:
        conf = float(visa.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    return intent, conf, str(visa.get("evidence", ""))[:300]


async def score(job: Job, profile: dict, gateway) -> MatchResult:
    resp = await gateway.complete("match", build_messages(profile, job))
    data = _extract_json(resp.get("content", ""))
    try:
        sc = int(data.get("score", 0))
    except (TypeError, ValueError):
        sc = 0
    sc = max(0, min(100, sc))
    tags = [t for t in data.get("tags", []) if t in ALLOWED_TAGS]
    track = data.get("track", "")
    if track not in ALLOWED_TRACKS:
        track = "Industry" if job.track_hint == "industry" else ""
    vi, vc, ve = _parse_visa(data)
    return MatchResult(score=sc, rationale=str(data.get("rationale", "")),
                       track=track, tags=tags, priority=_priority(sc),
                       visa_intent=vi, visa_confidence=vc, visa_evidence=ve)
