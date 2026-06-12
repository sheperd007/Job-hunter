from worker.pending import InMemoryPendingStore


def test_add_then_resolve_approve_acts_once():
    s = InMemoryPendingStore()
    aid = s.add("reply", {"to": "x@y.com", "subject": "Re: hi", "body": "..."})
    r1 = s.resolve(aid, "approve")
    assert r1["status"] == "approved" and r1["already"] is False
    assert r1["kind"] == "reply" and r1["payload"]["to"] == "x@y.com"
    # duplicate callback -> no second action
    r2 = s.resolve(aid, "approve")
    assert r2["already"] is True and r2["status"] == "approved"


def test_reject():
    s = InMemoryPendingStore()
    aid = s.add("event", {"title": "Interview"})
    r = s.resolve(aid, "reject")
    assert r["status"] == "rejected" and r["already"] is False


def test_resolve_unknown_id():
    s = InMemoryPendingStore()
    r = s.resolve("999", "approve")
    assert r["status"] == "not_found" and r["payload"] is None
