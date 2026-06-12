from worker.config import Settings


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("OPENAI_KEY_A", "sk-a")
    monkeypatch.setenv("OPENAI_KEY_B", "sk-b")
    monkeypatch.setenv("DRY_RUN", "true")
    s = Settings()
    assert s.openai_key_a == "sk-a"
    assert s.openai_key_b == "sk-b"
    assert s.dry_run is True
    assert s.monthly_cap_usd == 8.0          # default
    assert s.cap_safety_margin_usd == 7.5    # default
    assert s.model_triage == "gpt-4.1-mini"  # default
    assert s.model_match == "gpt-4.1"        # default
    assert s.openai_base_url == "https://api.openai.com/v1"  # default
