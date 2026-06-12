"""Pending approvals store. A proposed action (email reply or calendar event) is
stored 'pending'; a Telegram one-tap button resolves it approve/reject.

resolve() is idempotent: only the FIRST resolve of a pending row flips it and
reports already=False (so n8n performs the side effect exactly once). Telegram
can deliver a callback twice — this guards against double-send.
"""
from typing import Protocol
from worker.budget import KeySpend  # noqa: F401  (kept for parity; unused)


class PendingStore(Protocol):
    def add(self, kind: str, payload: dict) -> str: ...
    def resolve(self, action_id: str, decision: str) -> dict: ...


def _decision_status(decision: str) -> str:
    return "approved" if decision == "approve" else "rejected"


class InMemoryPendingStore:
    def __init__(self) -> None:
        self._d: dict[str, dict] = {}
        self._n = 0

    def add(self, kind: str, payload: dict) -> str:
        self._n += 1
        action_id = str(self._n)
        self._d[action_id] = {"kind": kind, "payload": payload, "status": "pending"}
        return action_id

    def resolve(self, action_id: str, decision: str) -> dict:
        rec = self._d.get(action_id)
        if rec is None:
            return {"status": "not_found", "kind": None, "payload": None, "already": False}
        if rec["status"] != "pending":
            return {"status": rec["status"], "kind": rec["kind"],
                    "payload": rec["payload"], "already": True}
        rec["status"] = _decision_status(decision)
        return {"status": rec["status"], "kind": rec["kind"],
                "payload": rec["payload"], "already": False}


class PostgresPendingStore:
    """psycopg imported lazily. resolve() uses a conditional UPDATE so concurrent
    duplicate callbacks resolve exactly once."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def add(self, kind: str, payload: dict) -> str:
        import json
        import psycopg
        with psycopg.connect(self._dsn) as conn:
            row = conn.execute(
                "INSERT INTO pending_actions (kind, payload) VALUES (%s, %s) RETURNING id",
                (kind, json.dumps(payload)),
            ).fetchone()
        return str(row[0])

    def resolve(self, action_id: str, decision: str) -> dict:
        import psycopg
        status = _decision_status(decision)
        with psycopg.connect(self._dsn) as conn:
            updated = conn.execute(
                "UPDATE pending_actions SET status = %s, resolved = now() "
                "WHERE id = %s AND status = 'pending' RETURNING kind, payload",
                (status, action_id),
            ).fetchone()
            if updated is not None:
                return {"status": status, "kind": updated[0],
                        "payload": updated[1], "already": False}
            cur = conn.execute(
                "SELECT kind, payload, status FROM pending_actions WHERE id = %s",
                (action_id,),
            ).fetchone()
        if cur is None:
            return {"status": "not_found", "kind": None, "payload": None, "already": False}
        return {"status": cur[2], "kind": cur[0], "payload": cur[1], "already": True}
