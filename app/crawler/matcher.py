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


def _get_alert_channels() -> list[str]:
    channels = []

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


def match_and_queue_alerts(conn, *, page_id: int, extracted_items: list[dict], seen_at: str) -> list[int]:
    watchlist = watchlist_repo.list_enabled_watchlist(conn)
    compiled = _build_compiled_watchlist(watchlist)

    created_hit_ids: list[int] = []
    channels = _get_alert_channels()

    for item in extracted_items:
        matched = _find_match(compiled, item["type"], item["normalized"])
        if not matched:
            continue

        page_url = str(item["page_url"]).strip()
        if not page_url:
            continue

        # hit은 URL 기준으로 누적
        hit_fingerprint = sha256(
            f"{matched['id']}|{item['type']}|{item['normalized']}|{page_url}".encode("utf-8")
        ).hexdigest()

        # alert는 값 기준으로 전역 1회만
        alert_fingerprint = sha256(
            f"{matched['id']}|{item['type']}|{item['normalized']}".encode("utf-8")
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

        # 같은 URL 재스캔이면 새 hit가 아니므로
        # alert도 만들지 않음
        if not result["is_new"]:
            continue

        # 새 URL에서 나온 경우 hit는 추가되지만,
        # alert는 해당 값이 처음일 때만 생성됨
        for channel in channels:
            alerts_repo.create_alert_if_not_exists(
                conn,
                hit_id=result["hit_id"],
                channel=channel,
                created_at=seen_at,
                alert_fingerprint=alert_fingerprint,
            )

    return created_hit_ids