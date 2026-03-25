from __future__ import annotations

import json
import re
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


def _parse_pattern_entry(entry: dict) -> tuple[re.Pattern, list[str] | None]:
    """
    watchlist pattern 항목을 파싱하여 (컴파일된 패턴, target_types)를 반환한다.
    target_types가 없으면 None (= 전체 타입에 적용).
    """
    pattern = re.compile(entry["value"])

    target_types: list[str] | None = None
    label = entry.get("label") or ""
    if "|meta:" in label:
        _, meta_str = label.split("|meta:", 1)
        try:
            meta = json.loads(meta_str)
            target_types = meta.get("target_types")
        except (json.JSONDecodeError, KeyError):
            pass

    return pattern, target_types


def _record_hit(
    conn,
    *,
    page_id: int,
    item: dict,
    watchlist_entry: dict,
    matched_value: str,
    seen_at: str,
    channels: list[str],
) -> int:
    """hit를 upsert하고 필요하면 알림을 생성한다. hit_id를 반환한다."""
    seen_dt = _to_dt(seen_at) or datetime.now(timezone.utc)

    fingerprint = sha256(
        f"{watchlist_entry['id']}|{item['normalized']}|{page_id}".encode("utf-8")
    ).hexdigest()

    result = hits_repo.upsert_watchlist_hit(
        conn,
        extracted_item_id=item["id"],
        watchlist_id=int(watchlist_entry["id"]),
        page_id=page_id,
        matched_value=matched_value,
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

    return result["hit_id"]


def match_and_queue_alerts(
    conn,
    *,
    page_id: int,
    extracted_items: list[dict],
    seen_at: str,
) -> list[int]:
    watchlist = watchlist_repo.list_enabled_watchlist(conn)
    channels = _get_alert_channels()
    created_hit_ids: list[int] = []

    # ── 1) 기존 exact-match 항목 분류 ───────────────────────────────────────
    by_type: dict[str, dict[str, dict]] = {}
    pattern_entries: list[dict] = []

    for entry in watchlist:
        if entry["type"] == "pattern":
            pattern_entries.append(entry)
        else:
            by_type.setdefault(entry["type"], {})[entry["normalized"]] = entry

    # ── 2) Exact-match 매칭 (기존 동작 유지) ────────────────────────────────
    for item in extracted_items:
        matched = by_type.get(item["type"], {}).get(item["normalized"])
        if not matched:
            continue

        hit_id = _record_hit(
            conn,
            page_id=page_id,
            item=item,
            watchlist_entry=matched,
            matched_value=item["raw"],
            seen_at=seen_at,
            channels=channels,
        )
        created_hit_ids.append(hit_id)

    # ── 3) 정규표현식 패턴 매칭 (신규) ─────────────────────────────────────
    for entry in pattern_entries:
        try:
            pattern, target_types = _parse_pattern_entry(entry)
        except re.error:
            # DB에 잘못 저장된 패턴은 건너뜀
            continue

        for item in extracted_items:
            # target_types 필터: 지정된 타입만 검사
            if target_types and item["type"] not in target_types:
                continue

            # raw 값과 normalized 값 둘 다 검사하여 매칭 범위 확대
            search_text = item["raw"] + " " + item["normalized"]
            m = pattern.search(search_text)
            if not m:
                continue

            # 매칭된 텍스트를 matched_value로 기록
            matched_value = m.group(0)

            hit_id = _record_hit(
                conn,
                page_id=page_id,
                item=item,
                watchlist_entry=entry,
                matched_value=matched_value,
                seen_at=seen_at,
                channels=channels,
            )
            created_hit_ids.append(hit_id)

    return created_hit_ids
