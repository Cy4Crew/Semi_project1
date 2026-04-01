from __future__ import annotations

from typing import Any


def save_extracted_item(
    conn,
    *,
    page_id: int,
    item_type: str,
    raw: str,
    normalized: str,
    group_key: str,
    first_seen_at: str,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO extracted_items(page_id, type, raw, normalized, group_key, first_seen_at)
            VALUES(%s, %s, %s, %s, %s, %s::timestamptz)
            ON CONFLICT (page_id, type, normalized)
            DO UPDATE SET raw = EXCLUDED.raw
            RETURNING id
            """,
            (page_id, item_type, raw, normalized, group_key, first_seen_at),
        )
        return int(cur.fetchone()["id"])


def list_recent_extracted_items(conn, limit: int = 100) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ei.id, ei.page_id, ei.type, ei.raw, ei.normalized, ei.group_key, ei.first_seen_at,
                   p.url, p.title
            FROM extracted_items ei
            JOIN pages p ON p.id = ei.page_id
            ORDER BY ei.id DESC
            LIMIT %s
            """,
            (limit,),
        )
        return list(cur.fetchall())
