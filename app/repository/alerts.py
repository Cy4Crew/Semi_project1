from __future__ import annotations

from typing import Any


def create_alert(conn, *, hit_id: int, channel: str, created_at: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO alerts(hit_id, channel, status, created_at)
            VALUES(%s, %s, 'pending', %s::timestamptz)
            RETURNING id
            """,
            (hit_id, channel, created_at),
        )
        return int(cur.fetchone()["id"])


def create_alert_if_not_exists(
    conn,
    *,
    hit_id: int,
    channel: str,
    created_at: str,
    alert_fingerprint: str,
) -> int | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO alerts(hit_id, channel, status, created_at, alert_fingerprint)
            VALUES(%s, %s, 'pending', %s::timestamptz, %s)
            ON CONFLICT (alert_fingerprint, channel) DO NOTHING
            RETURNING id
            """,
            (hit_id, channel, created_at, alert_fingerprint),
        )
        row = cur.fetchone()

    if row is None:
        return None

    if isinstance(row, dict):
        return int(row["id"])

    return int(row[0])


def list_recent_alerts(conn, limit: int = 100) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.id, a.hit_id, a.channel, a.status, a.error_message, a.created_at, a.sent_at,
                   h.matched_value, p.url
            FROM alerts a
            JOIN watchlist_hits h ON h.id = a.hit_id
            JOIN pages p ON p.id = h.page_id
            ORDER BY a.id DESC
            LIMIT %s
            """,
            (limit,),
        )
        return list(cur.fetchall())


def get_pending_alerts(conn, limit: int = 20) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, hit_id, channel FROM alerts WHERE status = 'pending' ORDER BY id ASC LIMIT %s",
            (limit,),
        )
        return list(cur.fetchall())


def mark_alert_sent(conn, alert_id: int, sent_at: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE alerts SET status = 'sent', sent_at = %s::timestamptz, error_message = NULL WHERE id = %s",
            (sent_at, alert_id),
        )


def mark_alert_failed(conn, alert_id: int, error_message: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE alerts SET status = 'failed', error_message = %s WHERE id = %s",
            (error_message[:2000], alert_id),
        )
