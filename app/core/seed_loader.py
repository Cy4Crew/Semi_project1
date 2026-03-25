from __future__ import annotations

import json
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
    count = 0

    for item in _read_json(path):
        item_type = str(item.get("type", "")).strip().lower()
        value = str(item.get("pattern", item.get("value", ""))).strip().lower()
        label = item.get("label")

        if not item_type or not value:
            continue

        try:
            watchlist_repo.create_watchlist_item(
                conn,
                item_type=item_type,
                value=value,
                label=label,
            )
            count += 1
        except Exception:
            # 중복 항목 등은 무시
            continue

    conn.commit()
    return count