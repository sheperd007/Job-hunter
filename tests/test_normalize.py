from worker.normalize import canonical_url, detect_region, in_target_region
from worker.models import Job


def test_canonical_url_strips_query_and_fragment():
    assert canonical_url("https://Jobs.Example.com/view/123?utm=x&ref=y#frag") \
        == "https://jobs.example.com/view/123"


def test_canonical_url_trailing_slash_and_scheme():
    assert canonical_url("HTTP://a.com/p/") == "http://a.com/p"


def test_detect_region():
    assert detect_region("Amsterdam, Netherlands") == "EU"
    assert detect_region("London, United Kingdom") == "UK"
    assert detect_region("Toronto, Canada") == "Canada"
    assert detect_region("Sydney, Australia") == "AU-NZ"
    assert detect_region("Remote (worldwide)") == "Remote"
    assert detect_region("New York, USA") == "US"
    assert detect_region("Tehran, Iran") == "Other"


def test_in_target_region():
    assert in_target_region("EU") is True
    assert in_target_region("UK") is True
    assert in_target_region("US") is False
    assert in_target_region("Other") is False


def test_job_model_defaults():
    j = Job(title="ML Engineer", url="https://x.com/1")
    assert j.org == "" and j.raw == {} and j.deadline is None
