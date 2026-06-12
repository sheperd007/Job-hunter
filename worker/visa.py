"""Visa/relocation eligibility filter. Pure logic; the network fetch of the
sponsor-register CSV happens in the pipeline and is passed in as a SponsorRegister.

Layered signal (strongest first):
  1. company on an official sponsor register (e.g. UK Home Office licensed sponsors)
  2. source-native visa flag (e.g. Arbeitnow `visa_sponsorship`)
  3. JD keyword scan (positive phrases; explicit negatives disqualify)
  4. academia default-eligible (universities routinely sponsor researcher visas)
"""
import re
from collections.abc import Iterable
from worker.models import Job, VisaVerdict

_POS = ["visa sponsorship", "sponsor a visa", "we sponsor", "sponsorship available",
        "relocation", "relocat", "work permit", "blue card", "skilled worker visa",
        "international applicants", "visa support", "we will sponsor"]
_NEG = ["must have the right to work", "must already have", "no visa sponsorship",
        "we do not sponsor", "unable to sponsor", "without sponsorship",
        "right to work in", "no sponsorship"]

_SUFFIXES = {"ltd", "limited", "inc", "llc", "plc", "gmbh", "bv", "ag", "co",
             "corp", "company", "group", "the"}


def normalize_org(name: str) -> str:
    toks = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower()).split()
    toks = [t for t in toks if t not in _SUFFIXES]
    return " ".join(toks)


class SponsorRegister:
    """Set of normalized employer names known to hold a sponsor licence."""

    def __init__(self, names: Iterable[str]):
        self._set = {normalize_org(n) for n in names if n}

    def contains(self, org: str) -> bool:
        n = normalize_org(org)
        return bool(n) and n in self._set

    @classmethod
    def from_csv_text(cls, text: str, column: str = "Organisation Name") -> "SponsorRegister":
        import csv
        import io
        rows = csv.DictReader(io.StringIO(text))
        col = column if (rows.fieldnames and column in rows.fieldnames) else (
            rows.fieldnames[0] if rows.fieldnames else column)
        return cls(r.get(col, "") for r in rows)


def keyword_scan(text: str) -> tuple[str | None, str]:
    """Return ('neg'|'pos'|None, evidence_snippet)."""
    t = (text or "").lower()
    for p in _NEG:
        i = t.find(p)
        if i != -1:
            return "neg", t[max(0, i - 20):i + len(p) + 20].strip()
    for p in _POS:
        i = t.find(p)
        if i != -1:
            return "pos", t[max(0, i - 20):i + len(p) + 30].strip()
    return None, ""


def assess(*, job: Job, register: SponsorRegister | None = None,
           academic: bool = False) -> VisaVerdict:
    text = f"{job.title} {job.description}"
    sign, ev = keyword_scan(text)

    if sign == "neg":
        return VisaVerdict(label="Unclear", confidence=0.2, evidence=ev, eligible=False)

    if register is not None and job.org and register.contains(job.org):
        return VisaVerdict(label="On sponsor register", confidence=0.9,
                           evidence=f"{job.org} appears on the licensed-sponsor register",
                           eligible=True)

    if job.raw.get("visa_sponsorship"):
        return VisaVerdict(label="Sponsors visa", confidence=0.85,
                           evidence="source visa_sponsorship flag = true", eligible=True)

    if sign == "pos":
        label = "Relocation support" if "relocat" in ev else "Sponsors visa"
        return VisaVerdict(label=label, confidence=0.7, evidence=ev, eligible=True)

    if academic:
        return VisaVerdict(label="Hires-intl (academia)", confidence=0.6,
                           evidence="academic role; universities routinely sponsor researcher visas",
                           eligible=True)

    return VisaVerdict(label="Unclear", confidence=0.3,
                       evidence="no explicit sponsorship signal", eligible=False)
