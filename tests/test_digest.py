from worker.digest import build_digest


def test_digest_counts_and_formats():
    jobs = [
        {"title": "ML Engineer", "notion_page_url": "https://notion.so/a",
         "visa": "Sponsors visa", "score": 88},
        {"title": "PostDoc NLP", "url": "https://x.com/b",
         "visa": "Hires-intl (academia)"},
    ]
    d = build_digest(jobs=jobs, budget={"a": 1.5, "b": 0.0}, date="2026-06-12", cap=10.0)
    assert "2 new match" in d["subject"]
    assert "ML Engineer" in d["html"] and "PostDoc NLP" in d["html"]
    assert "https://notion.so/a" in d["html"]      # prefers notion url
    assert "key A $1.50/10" in d["html"]           # cap shown dynamically (10, not 8)
    assert d["telegram"].startswith("2026-06-12 — Job Agent digest")


def test_digest_empty():
    d = build_digest(jobs=[], budget={}, date="2026-06-12", cap=9.5)
    assert "0 new match" in d["subject"]
    assert "key A $0.00/9.5" in d["html"]          # fractional caps render too
