from worker.visa import assess, keyword_scan, normalize_org, SponsorRegister, reconcile
from worker.models import Job, MatchResult


def job(title="ML Engineer", desc="", org="", raw=None):
    return Job(title=title, description=desc, org=org, url="https://x.com/1", raw=raw or {})


def _match(intent="unclear", conf=0.0):
    return MatchResult(score=70, visa_intent=intent, visa_confidence=conf,
                       visa_evidence=f"{intent} evidence")


def test_reconcile_register_beats_llm():
    reg = SponsorRegister(["Acme Ltd"])
    v = assess(job=job(org="Acme"), register=reg)          # On sponsor register (register)
    out = reconcile(v, _match("negative", 0.9))
    assert out.label == "On sponsor register" and out.eligible is True


def test_reconcile_source_flag_beats_llm():
    v = assess(job=job(raw={"visa_sponsorship": True}))     # Sponsors visa (source_flag)
    out = reconcile(v, _match("unclear", 0.0))
    assert out.label == "Sponsors visa" and out.source == "source_flag"


def test_reconcile_llm_resolves_unclear_positive():
    v = assess(job=job(desc="Great team."))                 # Unclear soft gate
    out = reconcile(v, _match("sponsors", 0.8))
    assert out.label == "Sponsors visa" and out.confidence == 0.8
    assert out.source == "llm" and out.eligible is True


def test_reconcile_llm_relocation_label():
    v = assess(job=job(desc="Great team."))
    out = reconcile(v, _match("relocation", 0.7))
    assert out.label == "Relocation support"


def test_reconcile_low_confidence_stays_unclear():
    v = assess(job=job(desc="Great team."))
    out = reconcile(v, _match("sponsors", 0.3))             # below default min_conf 0.6
    assert out.label == "Unclear"


def test_reconcile_llm_negative_downranks_not_drops():
    v = assess(job=job(desc="Great team."))                 # Unclear 0.3
    out = reconcile(v, _match("negative", 0.9))
    assert out.eligible is True and out.label == "Unclear"
    assert out.confidence < 0.3                             # demoted so it sorts last


def test_reconcile_positive_keyword_not_downgraded():
    v = assess(job=job(desc="We offer relocation assistance."))  # Relocation support (keyword)
    out = reconcile(v, _match("negative", 0.9))
    assert out.eligible is True and out.label == "Relocation support"


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


def test_industry_no_signal_surfaced_soft_gate():
    # Soft gate: no explicit sponsorship signal is no longer a hard drop. The job
    # is surfaced (eligible) but flagged "Unclear" so a human checks visa later.
    v = assess(job=job(desc="Great team, fast pace."), academic=False)
    assert v.eligible is True and v.label == "Unclear"


def test_explicit_negative_still_hard_dropped():
    # The only visa hard-drop that survives the soft gate: an explicit refusal.
    v = assess(job=job(desc="We do not sponsor visas; right to work in the UK required."))
    assert v.eligible is False


def test_keyword_scan_returns_evidence():
    sign, ev = keyword_scan("Visa sponsorship available for this role")
    assert sign == "pos" and "visa sponsorship" in ev
