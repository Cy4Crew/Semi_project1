from __future__ import annotations

from typing import Any

from app.crawler.extractor import normalize_value


def create_watchlist_item(conn, *, item_type: str, value: str, label: str | None = None) -> int:
    normalized = normalize_value(item_type, value)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO watchlist(type, value, normalized, label, enabled)
            VALUES(%s, %s, %s, %s, TRUE)
            ON CONFLICT (type, normalized)
            DO UPDATE SET value = EXCLUDED.value, label = EXCLUDED.label
            RETURNING id
            """,
            (item_type.strip().lower(), value.strip(), normalized, label),
        )
        return int(cur.fetchone()["id"])


def list_watchlist(conn) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, type, value, normalized, label, enabled, created_at FROM watchlist ORDER BY id DESC"
        )
        return list(cur.fetchall())


def list_enabled_watchlist(conn) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, type, value, normalized, label FROM watchlist WHERE enabled = TRUE ORDER BY id ASC"
        )
        return list(cur.fetchall())


def delete_watchlist_item(conn, watchlist_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM watchlist WHERE id = %s", (watchlist_id,))
