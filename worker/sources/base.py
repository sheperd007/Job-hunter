"""Shared HTTP helpers for source clients."""
import httpx


async def get_json(url: str, *, params: dict | None = None,
                   headers: dict | None = None, timeout: int = 30) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.get(url, params=params, headers=headers)
        r.raise_for_status()
        return r.json()


async def get_text(url: str, *, timeout: int = 30) -> str:
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.text
