from worker.db import DDL


def test_ddl_defines_all_tables():
    for table in ("usage_ledger", "seen_jobs", "profile"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in DDL
