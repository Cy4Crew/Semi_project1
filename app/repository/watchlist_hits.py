from __future__ import annotations

from typing import Any


def upsert_watchlist_hit(
    conn,
    *,
    extracted_item_id: int,
    watchlist_id: int,
    page_id: int,
    matched_value: str,
    fingerprint: str,
    seen_at: str,
) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO watchlist_hits(
                extracted_item_id, watchlist_id, page_id, matched_value, fingerprint,
                first_seen_at, last_seen_at
            ) VALUES(%s, %s, %s, %s, %s, %s::timestamptz, %s::timestamptz)
            ON CONFLICT (fingerprint)
            DO UPDATE SET last_seen_at = EXCLUDED.last_seen_at, matched_value = EXCLUDED.matched_value
            RETURNING id, xmax = 0 AS inserted, last_alerted_at
            """,
            (extracted_item_id, watchlist_id, page_id, matched_value, fingerprint, seen_at, seen_at),
        )
        row = cur.fetchone()
        return {
            "hit_id": int(row["id"]),
            "is_new": bool(row["inserted"]),
            "last_alerted_at": row["last_alerted_at"],
        }


def touch_last_alerted_at(conn, hit_id: int, alerted_at: str) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE watchlist_hits SET last_alerted_at = %s::timestamptz WHERE id = %s", (alerted_at, hit_id))


def get_hit_detail(conn, hit_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT h.id, h.page_id, h.watchlist_id, h.matched_value, h.first_seen_at, h.last_seen_at, h.last_alerted_at,
                   w.type AS watch_type, w.value AS watch_value, w.label,
                   ei.type AS extracted_type, ei.raw, ei.normalized,
                   p.url, p.title, p.screenshot_path
            FROM watchlist_hits h
            JOIN watchlist w ON w.id = h.watchlist_id
            JOIN extracted_items ei ON ei.id = h.extracted_item_id
            JOIN pages p ON p.id = h.page_id
            WHERE h.id = %s
            """,
            (hit_id,),
        )
        return cur.fetchone()


def list_recent_hits(conn, limit: int = 100) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT h.id, h.page_id, h.watchlist_id, h.matched_value, h.first_seen_at, h.last_seen_at, h.last_alerted_at,
                   w.type AS watch_type, w.value AS watch_value, w.label, p.url, p.title, p.screenshot_path
            FROM watchlist_hits h
            JOIN watchlist w ON w.id = h.watchlist_id
            JOIN pages p ON p.id = h.page_id
            ORDER BY h.id DESC
            LIMIT %s
            """,
            (limit,),
        )
        return list(cur.fetchall())
