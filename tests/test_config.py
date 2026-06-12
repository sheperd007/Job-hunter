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


def test_dsn_built_from_parts_by_default():
    s = Settings()
    assert s.dsn == "postgresql://n8n:n8n@postgres:5432/n8n"


def test_dsn_explicit_url_wins(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:5432/db")
    assert Settings().dsn == "postgresql://u:p@host:5432/db"


def test_dsn_uses_secret_db_password(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "s3cr3t")
    assert Settings().dsn == "postgresql://n8n:s3cr3t@postgres:5432/n8n"
