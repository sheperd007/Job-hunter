"""Shared data models for job discovery."""
from pydantic import BaseModel, Field


class Job(BaseModel):
    """A normalized job posting from any source."""
    title: str
    org: str = ""
    location: str = ""
    url: str                       # canonical URL; the dedupe key
    source: str = ""               # e.g. "google_jobs", "euraxess"
    description: str = ""
    deadline: str | None = None    # ISO date if known
    region: str = ""               # UK / EU / Canada / AU-NZ / US / Remote / Other
    track_hint: str = ""           # "academic" | "industry" | ""
    raw: dict = Field(default_factory=dict)


class VisaVerdict(BaseModel):
    label: str          # Sponsors visa / Relocation support / Hires-intl (academia) / On sponsor register / Unclear
    confidence: float   # 0..1
    evidence: str = ""  # short snippet justifying the label
    eligible: bool      # passes the filter (kept) or not (dropped)
    source: str = "keyword"  # keyword | register | source_flag | llm | academic (provenance for reconcile precedence)


class MatchResult(BaseModel):
    score: int          # 0..100
    rationale: str = ""
    track: str = ""     # Academic - PhD/PostDoc/Lectureship/Faculty | Industry
    tags: list[str] = Field(default_factory=list)
    priority: str = "Low"   # High / Medium / Low
    # Visa/relocation intent classified by the LLM in the same match call (no extra
    # call). Reconciled into the VisaVerdict for keyword-"Unclear" jobs only.
    visa_intent: str = "unclear"     # sponsors | relocation | unclear | negative
    visa_confidence: float = 0.0     # 0..1
    visa_evidence: str = ""
