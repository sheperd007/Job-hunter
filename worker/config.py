import os
from pydantic_settings import BaseSettings, SettingsConfigDict

# Docker/compose secrets are mounted here as files named after the field
# (e.g. /run/secrets/openai_key_a). pydantic-settings reads them automatically
# when the directory exists. Env vars still win for local dev; on a shared host
# you supply secrets as files so they never appear in `docker inspect` or
# /proc/<pid>/environ. The dir is only wired in when present, so tests/dev that
# lack /run/secrets are unaffected.
_SECRETS_DIR = "/run/secrets"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        secrets_dir=_SECRETS_DIR if os.path.isdir(_SECRETS_DIR) else None,
    )

    openai_key_a: str = ""           # triage + visa pre-filter
    openai_key_b: str = ""           # match scoring + reply drafting
    openai_base_url: str = "https://api.openai.com/v1"
    model_triage: str = "gpt-4.1-mini"
    model_match: str = "gpt-4.1"
    model_fallback: str = "gpt-4o-mini"

    monthly_cap_usd: float = 10.0
    cap_safety_margin_usd: float = 9.5     # block key once month spend >= this
    daily_soft_cap_usd: float = 0.33       # ~ 10/30, advisory

    # DB: set DATABASE_URL directly, or supply parts (db_password can be a secret
    # file) and let `dsn` build the connection string.
    database_url: str = ""
    db_host: str = "postgres"
    db_port: int = 5432
    db_user: str = "n8n"
    db_password: str = "n8n"
    db_name: str = "n8n"

    dry_run: bool = False

    # Telegram (worker-side run-completion ping only; n8n owns digest/approvals).
    # Token is a secret file in hardened mode; chat id comes from env TELEGRAM_CHAT_ID.
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Notion (worker performs all Notion writes)
    notion_token: str = ""
    notion_applications_db: str = "70b08f56f7fc4825b9e45993a409cb11"  # Applications database id
    notion_version: str = "2022-06-28"

    # Job source keys
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    scrapingdog_key: str = ""        # Indeed via Scrapingdog scraper API (1 credit/req)

    # Per-run cap on LLM match scoring (cost guard). ~189 in-region jobs/day reach
    # scoring under the soft visa gate; capping keeps key B under the $10/mo cap.
    # Uncapped runs are bounded only by the Budget Guard hard stop.
    max_match_per_run: int = 60

    # Optional licensed-sponsor register CSV (e.g. UK Home Office list). When set,
    # employers on the list are flagged "On sponsor register" (strongest visa
    # signal). Unset -> register check skipped; soft gate still surfaces jobs.
    sponsor_register_url: str = ""

    @property
    def dsn(self) -> str:
        """Postgres connection string. DATABASE_URL wins if set; otherwise built
        from parts so db_password can come from a mounted secret file."""
        if self.database_url:
            return self.database_url
        return (f"postgresql://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}")
