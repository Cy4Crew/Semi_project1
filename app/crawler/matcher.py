from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

from app.core.config import settings
from app.repository import alerts as alerts_repo
from app.repository import watchlist as watchlist_repo
from app.repository import watchlist_hits as hits_repo


def _to_dt(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


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
    seen_dt = _to_dt(seen_at) or datetime.now(timezone.utc)
    channels = _get_alert_channels()

    for item in extracted_items:
        matched = by_type.get(item["type"], {}).get(item["normalized"])
        if not matched:
            continue

        fingerprint = sha256(
            f"{matched['id']}|{item['normalized']}|{page_id}".encode("utf-8")
        ).hexdigest()

        result = hits_repo.upsert_watchlist_hit(
            conn,
            extracted_item_id=item["id"],
            watchlist_id=int(matched["id"]),
            page_id=page_id,
            matched_value=item["raw"],
            fingerprint=fingerprint,
            seen_at=seen_at,
        )

        should_alert = result["is_new"]
        last_alerted_at = _to_dt(result.get("last_alerted_at"))

        if not should_alert and last_alerted_at is not None:
            should_alert = (
                seen_dt - last_alerted_at
            ).total_seconds() >= settings.alert_cooldown_seconds

        if should_alert:
            for channel in channels:
                alerts_repo.create_alert(
                    conn,
                    hit_id=result["hit_id"],
                    channel=channel,
                    created_at=seen_at,
                )
            hits_repo.touch_last_alerted_at(
                conn,
                hit_id=result["hit_id"],
                alerted_at=seen_at,
            )

        created_hit_ids.append(result["hit_id"])

    return created_hit_ids