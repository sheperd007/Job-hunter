import json
import httpx
import respx
import pytest
from worker.notify import telegram_notify


class _S:
    def __init__(self, token="", chat=""):
        self.telegram_bot_token = token
        self.telegram_chat_id = chat


@pytest.mark.asyncio
async def test_notify_noop_without_token_or_chat():
    # Best-effort: with nothing configured it silently does nothing (returns False),
    # never raising and never blocking the run.
    assert await telegram_notify(_S(token="", chat="123"), "hi") is False
    assert await telegram_notify(_S(token="T", chat=""), "hi") is False


@respx.mock
@pytest.mark.asyncio
async def test_notify_posts_message_when_configured():
    route = respx.post(url__startswith="https://api.telegram.org/bot").mock(
        return_value=httpx.Response(200, json={"ok": True}))
    ok = await telegram_notify(_S(token="TOK", chat="8164243924"), "done: 5 new")
    assert ok is True and route.called
    sent = json.loads(route.calls[0].request.content)
    assert sent["chat_id"] == "8164243924" and "5 new" in sent["text"]


@respx.mock
@pytest.mark.asyncio
async def test_notify_swallows_network_errors():
    respx.post(url__startswith="https://api.telegram.org/bot").mock(
        side_effect=httpx.ConnectError("boom"))
    assert await telegram_notify(_S(token="TOK", chat="123"), "x") is False
