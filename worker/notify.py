"""Best-effort Telegram notifier for worker-side run-completion pings.

n8n owns the digest + approval bots; this is only for a "discovery finished"
ping right after /jobs/run. It NEVER raises — a failed notify must not fail the
run. In hardened mode the worker needs the api.telegram.org DNS pin (see
docker-compose.telegram.yml) since the host DNS is sinkholed.
"""
import httpx


async def telegram_notify(settings, text: str) -> bool:
    """Send `text` to the configured chat. Returns True on a 200, else False
    (including when unconfigured or on any network error)."""
    token = getattr(settings, "telegram_bot_token", "") or ""
    chat = getattr(settings, "telegram_chat_id", "") or ""
    if not token or not chat:
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(f"https://api.telegram.org/bot{token}/sendMessage",
                             json={"chat_id": chat, "text": text})
        return r.status_code == 200
    except Exception:  # noqa: BLE001 — notify is best-effort, never fatal
        return False
