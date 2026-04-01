from __future__ import annotations

import hashlib
from dataclasses import dataclass
from urllib.parse import urljoin, urldefrag, urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings


@dataclass
class FetchResult:
    url: str
    host: str
    status_code: int | None
    title: str | None
    html: str
    text: str
    content_hash: str
    links: list[str]
    error_message: str | None = None


def _normalize_link(base_url: str, href: str) -> str | None:
    href = (href or "").strip()
    if not href:
        return None

    lowered = href.lower()
    if lowered.startswith(("#", "javascript:", "mailto:", "tel:")):
        return None

    absolute = urljoin(base_url, href)
    absolute, _ = urldefrag(absolute)

    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.netloc:
        return None

    return parsed.geturl()


def _is_onion_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host.endswith(".onion")


def _get_proxy_for_url(url: str) -> str | None:
    if not settings.tor_enabled:
        return None
    if settings.tor_for_all_requests or _is_onion_url(url):
        return settings.tor_proxy_url
    return None


async def fetch_page(url: str) -> FetchResult:
    host = urlparse(url).netloc
    headers = {"User-Agent": settings.user_agent}
    proxy = _get_proxy_for_url(url)

    try:
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
            headers=headers,
            proxy=proxy,
            verify=False if _is_onion_url(url) else True,
            trust_env=False,
        ) as client:
            response = await client.get(url)

        final_url = str(response.url)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else None
        text = soup.get_text("\n", strip=True)

        seen: set[str] = set()
        links: list[str] = []

        for a in soup.find_all("a", href=True):
            normalized = _normalize_link(final_url, a.get("href", ""))
            if not normalized:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            links.append(normalized)

        return FetchResult(
            url=final_url,
            host=urlparse(final_url).netloc or host,
            status_code=response.status_code,
            title=title,
            html=html,
            text=text,
            content_hash=hashlib.sha256(html.encode("utf-8", errors="ignore")).hexdigest(),
            links=links,
        )

    except Exception as exc:
        return FetchResult(
            url=url,
            host=host,
            status_code=None,
            title=None,
            html="",
            text="",
            content_hash=hashlib.sha256(b"").hexdigest(),
            links=[],
            error_message=str(exc),
        )