from __future__ import annotations

import httpx

from app.core.config import settings


async def send_discord(message: str) -> None:
    if not settings.discord_webhook_url:
        return
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(settings.discord_webhook_url, json={"content": message})
        response.raise_for_status()
