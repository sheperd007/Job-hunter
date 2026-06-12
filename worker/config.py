from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_key_a: str = ""           # triage + visa pre-filter
    openai_key_b: str = ""           # match scoring + reply drafting
    openai_base_url: str = "https://api.openai.com/v1"
    model_triage: str = "gpt-4.1-mini"
    model_match: str = "gpt-4.1"
    model_fallback: str = "gpt-4o-mini"

    monthly_cap_usd: float = 8.0
    cap_safety_margin_usd: float = 7.5     # block key once month spend >= this
    daily_soft_cap_usd: float = 0.27       # ~ 8/30, advisory

    database_url: str = "postgresql://n8n:n8n@postgres:5432/n8n"
    dry_run: bool = False
