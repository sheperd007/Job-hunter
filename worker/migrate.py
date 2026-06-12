"""One-shot schema migration entrypoint. Run as a PRE_DEPLOY job on App Platform
or manually: `python -m worker.migrate`."""
from worker.config import Settings
from worker.db import ensure_schema


def main() -> None:
    s = Settings()
    ensure_schema(s.database_url)
    print("schema ensured")


if __name__ == "__main__":
    main()
