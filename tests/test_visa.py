from worker.visa import assess, keyword_scan, normalize_org, SponsorRegister
from worker.models import Job


def job(title="ML Engineer", desc="", org="", raw=None):
    return Job(title=title, description=desc, org=org, url="https://x.com/1", raw=raw or {})


def test_normalize_org_strips_suffixes():
    assert normalize_org("Acme Ltd.") == normalize_org("ACME LIMITED") == "acme"


def test_sponsor_register_contains():
    reg = SponsorRegister(["DeepMind Technologies Limited", "Spotify AB"])
    assert reg.contains("DeepMind Technologies") is True
    assert reg.contains("Unknown Co") is False


def test_register_hit_is_strongest_signal():
    reg = SponsorRegister(["Acme Ltd"])
    v = assess(job=job(org="Acme"), register=reg)
    assert v.label == "On sponsor register" and v.eligible is True


def test_explicit_negative_disqualifies():
    v = assess(job=job(desc="You must already have the right to work in the UK."))
    assert v.eligible is False


def test_arbeitnow_flag_passes():
    v = assess(job=job(raw={"visa_sponsorship": True}))
    assert v.label == "Sponsors visa" and v.eligible is True


def test_relocation_keyword():
    v = assess(job=job(desc="We offer relocation assistance for the right candidate."))
    assert v.eligible is True and v.label == "Relocation support"


def test_academic_default_eligible():
    v = assess(job=job(title="PostDoc in ML"), academic=True)
    assert v.eligible is True and "academia" in v.label.lower()


def test_industry_no_signal_dropped():
    v = assess(job=job(desc="Great team, fast pace."), academic=False)
    assert v.eligible is False


def test_keyword_scan_returns_evidence():
    sign, ev = keyword_scan("Visa sponsorship available for this role")
    assert sign == "pos" and "visa sponsorship" in ev
