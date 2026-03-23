from playwright.async_api import async_playwright
from app.core.config import settings
import os
import hashlib

async def take_screenshot(url: str) -> str | None:
    if not settings.screenshot_enabled:
        return None

    os.makedirs("evidence/screenshots", exist_ok=True)
    fname = f"evidence/screenshots/{hashlib.sha1(url.encode()).hexdigest()}.png"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=settings.playwright_timeout_ms)
            await page.screenshot(path=fname, full_page=True)
            await browser.close()
        return fname
    except Exception:
        return None