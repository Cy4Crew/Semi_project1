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
    items = _read_json(path)
    result = targets_repo.upsert_targets_from_seed(conn, items)
    return int(result["seed_count"])


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
            continue

    conn.commit()
    return count
