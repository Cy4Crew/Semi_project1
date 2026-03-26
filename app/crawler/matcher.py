from __future__ import annotations

from hashlib import sha256
from urllib.parse import urlparse

from app.core.config import settings
from app.repository import alerts as alerts_repo
from app.repository import watchlist as watchlist_repo
from app.repository import watchlist_hits as hits_repo


def _get_alert_channels() -> list[str]:
    channels = ["stdout"]

    if settings.discord_webhook_url:
        channels.append("discord")

    if settings.telegram_bot_token and settings.telegram_chat_id:
        channels.append("telegram")

    return channels


def match_and_queue_alerts(conn, *, page_id: int, extracted_items: list[dict], seen_at: str) -> list[int]:
    watchlist = watchlist_repo.list_enabled_watchlist(conn)
    by_type = {}

    for item in watchlist:
        by_type.setdefault(item["type"], {})[item["normalized"]] = item

    created_hit_ids: list[int] = []
    channels = _get_alert_channels()

    for item in extracted_items:
        matched = by_type.get(item["type"], {}).get(item["normalized"])
        if not matched:
            continue

        page_url = str(item["page_url"]).strip()
        host = urlparse(page_url).netloc.lower()
        if not host:
            continue

        # hit 기준: full URL
        hit_fingerprint = sha256(
            f"{matched['id']}|{item['type']}|{item['normalized']}|{page_url}".encode("utf-8")
        ).hexdigest()

        # alert 기준: host
        alert_fingerprint = sha256(
            f"{matched['id']}|{item['type']}|{item['normalized']}|{host}".encode("utf-8")
        ).hexdigest()

        result = hits_repo.upsert_watchlist_hit(
            conn,
            extracted_item_id=item["id"],
            watchlist_id=int(matched["id"]),
            page_id=page_id,
            matched_value=item["raw"],
            fingerprint=hit_fingerprint,
            seen_at=seen_at,
        )

        created_hit_ids.append(result["hit_id"])

        # 같은 URL 재스캔이면 is_new=False
        if not result["is_new"]:
            continue

        # 새 hit라도 같은 host에서 이미 alert 보낸 적 있으면 alert 생성 안 함
        for channel in channels:
            alerts_repo.create_alert_if_not_exists(
                conn,
                hit_id=result["hit_id"],
                channel=channel,
                created_at=seen_at,
                alert_fingerprint=alert_fingerprint,
            )

    return created_hit_ids
