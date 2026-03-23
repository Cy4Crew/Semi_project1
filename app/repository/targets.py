from __future__ import annotations

from typing import Any


def _rows_to_dicts(cur, rows):
    if not rows:
        return []

    first = rows[0]

    # 이미 dict인 경우 그대로 사용
    if isinstance(first, dict):
        return [dict(r) for r in rows]

    # tuple/list인 경우만 변환
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in rows]


def create_target(conn, name: str, seed_url: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO targets (name, seed_url)
            VALUES (%s, %s)
            ON CONFLICT (seed_url) DO NOTHING
            RETURNING id
            """,
            (name, seed_url),
        )
        row = cur.fetchone()

        if row:
            target_id = row["id"]
        else:
            cur.execute(
                "SELECT id FROM targets WHERE seed_url = %s",
                (seed_url,),
            )
            existing = cur.fetchone()
            if not existing:
                raise RuntimeError(f"failed to create or find target: {seed_url}")
            target_id = existing["id"]

    conn.commit()
    return target_id


def list_targets(conn) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, seed_url, enabled, is_queued, last_queued_at, last_fetched_at, created_at
            FROM targets
            ORDER BY id ASC
            """
        )
        rows = cur.fetchall()
        return _rows_to_dicts(cur, rows)


def delete_target(conn, target_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM targets WHERE id = %s", (target_id,))
        deleted = cur.rowcount > 0
    conn.commit()
    return deleted


def get_due_targets(conn, revisit_after_seconds: int) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, seed_url, enabled, is_queued, last_queued_at, last_fetched_at
            FROM targets
            WHERE enabled = TRUE
              AND is_queued = FALSE
              AND (
                    last_queued_at IS NULL
                    OR last_queued_at <= NOW() - (%s * INTERVAL '1 second')
                  )
            ORDER BY id ASC
            """,
            (revisit_after_seconds,),
        )
        rows = cur.fetchall()
        return _rows_to_dicts(cur, rows)


def mark_target_queued(conn, target_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE targets
            SET is_queued = TRUE,
                last_queued_at = NOW()
            WHERE id = %s
            """,
            (target_id,),
        )
    conn.commit()


def mark_target_done(conn, target_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE targets
            SET is_queued = FALSE,
                last_fetched_at = NOW()
            WHERE id = %s
            """,
            (target_id,),
        )
    conn.commit()


def mark_target_failed(conn, target_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE targets
            SET is_queued = FALSE
            WHERE id = %s
            """,
            (target_id,),
        )
    conn.commit()