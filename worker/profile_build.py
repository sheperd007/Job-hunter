"""Build a structured profile JSON from the owner's CV text via the LLM gateway.

Runs rarely (W0), so it routes through the 'match' lane (stronger model). PDF
text extraction uses pypdf, imported lazily so the module loads without it.
"""
from worker.match import _extract_json

PROFILE_SYSTEM = (
    "You extract a structured professional profile from a CV. The applicant "
    "targets ML / Deep Learning / Generative AI roles (academic and industry) "
    "and wants visa-sponsor / relocation jobs. IGNORE any 'research interests' "
    "prose; capture concrete skills and impact. Reply ONLY with JSON having keys: "
    "name, skills (list of str), subfields (list), seniority_years (int), "
    "target_titles (list), tracks (list of 'academic'|'industry'), languages "
    "(list), publications (int), notes (str)."
)


async def build_profile(cv_text: str, gateway) -> dict:
    messages = [{"role": "system", "content": PROFILE_SYSTEM},
                {"role": "user", "content": cv_text[:12000]}]
    resp = await gateway.complete("match", messages)
    return _extract_json(resp.get("content", ""))


def extract_text_from_pdf(paths: list[str]) -> str:
    from pypdf import PdfReader
    chunks: list[str] = []
    for p in paths:
        reader = PdfReader(p)
        for page in reader.pages:
            chunks.append(page.extract_text() or "")
    return "\n".join(chunks)
