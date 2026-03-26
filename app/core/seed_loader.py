from __future__ import annotations

import json
import re
import logging
from pathlib import Path

from app.repository import targets as targets_repo
from app.repository import watchlist as watchlist_repo

logger = logging.getLogger(__name__)


def _read_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def load_targets_file(conn, path: Path) -> int:
    count = 0
    for item in _read_json(path):
        seed_url = str(item.get("seed_url", "")).strip()
        if not seed_url:
            continue

        name = str(item.get("name", seed_url)).strip() or seed_url

        try:
            targets_repo.create_target(conn, name=name, seed_url=seed_url)
            count += 1
        except Exception:
            # 중복 seed_url 등은 무시
            continue

    conn.commit()
    return count


def load_watchlist_file(conn, path: Path) -> int:
    """watchlist.json을 읽어 DB에 적재한다.

    지원 포맷:
    - 단일 패턴 (하위 호환):
        {"type": "email", "pattern": "foo@bar.com", "label": "..."}
    - 다중 패턴:
        {"type": "email", "patterns": ["foo@bar.com", "baz@bar.com"], "label": "..."}
    - 정규표현식 다중 패턴:
        {"type": "domain", "patterns": [".*\\.ru$", ".*\\.su$"], "is_regex": true, "label": "..."}
    """
    count = 0

    for item in _read_json(path):
        item_type = str(item.get("type", "")).strip().lower()
        label = item.get("label")
        is_regex = bool(item.get("is_regex", False))

        # patterns 배열 우선, 없으면 단일 pattern/value 하위 호환
        raw_patterns: list[str] = []
        if "patterns" in item and isinstance(item["patterns"], list):
            raw_patterns = [str(p).strip() for p in item["patterns"] if str(p).strip()]
        else:
            single = str(item.get("pattern", item.get("value", ""))).strip()
            if single:
                raw_patterns = [single]

        if not item_type or not raw_patterns:
            continue

        for pattern in raw_patterns:
            # is_regex 항목은 컴파일 유효성 사전 검증
            if is_regex:
                try:
                    re.compile(pattern, re.IGNORECASE)
                except re.error as exc:
                    logger.warning(
                        "[watchlist] 잘못된 정규표현식 건너뜀: %r (%s)", pattern, exc
                    )
                    continue

            try:
                watchlist_repo.create_watchlist_item(
                    conn,
                    item_type=item_type,
                    value=pattern,
                    label=label,
                    is_regex=is_regex,
                )
                count += 1
            except Exception:
                # 중복 항목 등은 무시
                continue

    conn.commit()
    return count
