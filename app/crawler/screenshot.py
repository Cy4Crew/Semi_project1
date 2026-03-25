from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

from app.core.config import settings


def is_onion(url: str) -> bool:
    return (urlparse(url).hostname or "").endswith(".onion")


def get_proxy(url: str) -> dict[str, str] | None:
    if not settings.tor_enabled:
        return None

    if settings.tor_for_all_requests or is_onion(url):
        return {
            "server": f"socks5://{settings.tor_socks_host}:{settings.tor_socks_port}"
        }

    return None


async def take_screenshot(url: str) -> str | None:
    if not settings.screenshot_enabled:
        return None

    out_dir = settings.screenshot_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = out_dir / f"{hashlib.sha1(url.encode('utf-8')).hexdigest()}.png"

    try:
        async with async_playwright() as p:
            launch_kwargs = {"headless": True}

            proxy = get_proxy(url)
            if proxy is not None:
                launch_kwargs["proxy"] = proxy

            browser = await p.chromium.launch(**launch_kwargs)
            try:
                page = await browser.new_page()
                await page.goto(
                    url,
                    timeout=settings.playwright_timeout_ms,
                    wait_until="domcontentloaded",
                )
                await page.screenshot(path=str(fname), full_page=True)
                return str(fname)
            finally:
                await browser.close()

    except Exception as e:
        print(f"[SCREENSHOT ERROR] {url} -> {e}")
        return None