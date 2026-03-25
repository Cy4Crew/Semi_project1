from __future__ import annotations

import json
import re
from pathlib import Path

from app.repository import targets as targets_repo
from app.repository import watchlist as watchlist_repo


def _read_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _validate_pattern(value: str) -> bool:
    """정규표현식이 유효한지 검증한다."""
    try:
        re.compile(value)
        return True
    except re.error:
        return False


def load_targets_file(conn, path: Path) -> int:
    count = 0
    for item in _read_json(path):
        seed_url = str(item.get("seed_url", "")).strip()
        if not seed_url:
            continue
        name = str(item.get("name", seed_url)).strip() or seed_url
        targets_repo.create_target(conn, name=name, seed_url=seed_url)
        count += 1
    conn.commit()
    return count


def load_watchlist_file(conn, path: Path) -> int:
    count = 0
    for item in _read_json(path):
        item_type = str(item.get("type", "")).strip().lower()
        value = str(item.get("value", "")).strip()
        label = item.get("label")

        if not item_type or not value:
            continue

        # pattern 타입은 정규표현식 유효성 검증 후 저장
        # target_types는 JSON 직렬화하여 label에 함께 보관하거나
        # 별도 컬럼이 없으므로 meta 정보를 label에 prefix로 저장
        if item_type == "pattern":
            if not _validate_pattern(value):
                print(f"[seed_loader] 유효하지 않은 정규표현식 건너뜀: {value!r}")
                continue
            # target_types가 있으면 label에 직렬화해서 붙임
            target_types = item.get("target_types")
            if target_types and isinstance(target_types, list):
                meta = json.dumps({"target_types": target_types}, ensure_ascii=False)
                label = f"{label or ''}|meta:{meta}"

        watchlist_repo.create_watchlist_item(
            conn, item_type=item_type, value=value, label=label
        )
        count += 1
    conn.commit()
    return count
