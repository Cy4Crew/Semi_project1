from __future__ import annotations

import re
import logging
from datetime import datetime, timezone
from hashlib import sha256
from typing import NamedTuple

from app.core.config import settings
from app.repository import alerts as alerts_repo
from app.repository import watchlist as watchlist_repo
from app.repository import watchlist_hits as hits_repo

logger = logging.getLogger(__name__)


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


class _CompiledWatchlist(NamedTuple):
    """매 호출마다 재컴파일하지 않도록 분리한 구조체."""
    # 타입별 exact match: {type: {normalized: wl_item}}
    exact: dict[str, dict[str, dict]]
    # 타입별 regex match: {type: [(compiled_re, wl_item), ...]}
    regex: dict[str, list[tuple[re.Pattern, dict]]]


def _build_compiled_watchlist(watchlist: list[dict]) -> _CompiledWatchlist:
    """watchlist 목록을 exact / regex 두 버킷으로 분류하고 정규표현식을 컴파일한다."""
    exact: dict[str, dict[str, dict]] = {}
    regex: dict[str, list[tuple[re.Pattern, dict]]] = {}

    for item in watchlist:
        t = item["type"]
        if item.get("is_regex"):
            try:
                compiled = re.compile(item["normalized"], re.IGNORECASE)
                regex.setdefault(t, []).append((compiled, item))
            except re.error as exc:
                logger.warning(
                    "[matcher] 정규표현식 컴파일 실패, 건너뜀: %r (%s)",
                    item["normalized"],
                    exc,
                )
        else:
            exact.setdefault(t, {})[item["normalized"]] = item

    return _CompiledWatchlist(exact=exact, regex=regex)


def _find_match(compiled: _CompiledWatchlist, item_type: str, normalized: str) -> dict | None:
    """추출된 IoC 하나에 대해 watchlist에서 매칭 항목을 찾는다.

    우선순위: exact match → regex match (등록 순서대로 첫 번째 매칭)
    """
    # 1) exact match (O(1))
    matched = compiled.exact.get(item_type, {}).get(normalized)
    if matched:
        return matched

    # 2) regex match (등록 순서대로 첫 번째 매칭)
    for compiled_re, wl_item in compiled.regex.get(item_type, []):
        if compiled_re.fullmatch(normalized):
            return wl_item

    return None


def match_and_queue_alerts(
    conn,
    *,
    page_id: int,
    extracted_items: list[dict],
    seen_at: str,
) -> list[int]:
    watchlist = watchlist_repo.list_enabled_watchlist(conn)
    compiled = _build_compiled_watchlist(watchlist)

    created_hit_ids: list[int] = []
    seen_dt = _to_dt(seen_at) or datetime.now(timezone.utc)
    channels = _get_alert_channels()

    for item in extracted_items:
        matched = _find_match(compiled, item["type"], item["normalized"])
        if not matched:
            continue

        # page_id를 fingerprint에서 제외해야 같은 값이 여러 페이지에 나와도
        # 동일한 watchlist hit로 집계되고 cooldown이 제대로 동작한다.
        fingerprint = sha256(
            f"{matched['id']}|{item['type']}|{item['normalized']}".encode("utf-8")
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
