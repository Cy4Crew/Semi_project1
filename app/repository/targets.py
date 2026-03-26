from __future__ import annotations

from typing import Any


def _rows_to_dicts(cur, rows):
    if not rows:
        return []

    first = rows[0]

    if isinstance(first, dict):
        return [dict(r) for r in rows]

    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in rows]


def create_target(conn, name: str, seed_url: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO targets (name, seed_url)
            VALUES (%s, %s)
            ON CONFLICT (seed_url) DO UPDATE
            SET name = EXCLUDED.name
            RETURNING id
            """,
            (name, seed_url),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"failed to create or update target: {seed_url}")
        target_id = row["id"]

    conn.commit()
    return target_id


def upsert_targets_from_seed(conn, items: list[dict[str, str]]) -> dict[str, int]:
    normalized_items: list[dict[str, str]] = []
    seed_urls: list[str] = []

    for item in items:
        seed_url = str(item.get("seed_url", "")).strip()
        if not seed_url:
            continue

        name = str(item.get("name", seed_url)).strip() or seed_url
        normalized_items.append({"name": name, "seed_url": seed_url})
        seed_urls.append(seed_url)

    inserted_or_updated = 0
    deleted = 0

    with conn.cursor() as cur:
        for item in normalized_items:
            cur.execute(
                """
                INSERT INTO targets (name, seed_url)
                VALUES (%s, %s)
                ON CONFLICT (seed_url) DO UPDATE
                SET name = EXCLUDED.name
                """,
                (item["name"], item["seed_url"]),
            )
            inserted_or_updated += 1

        if seed_urls:
            cur.execute(
                "DELETE FROM targets WHERE seed_url <> ALL(%s)",
                (seed_urls,),
            )
        else:
            cur.execute("DELETE FROM targets")

        deleted = cur.rowcount

    conn.commit()
    return {
        "seed_count": len(normalized_items),
        "upserted": inserted_or_updated,
        "deleted": deleted,
    }


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
                    last_fetched_at IS NULL
                    OR last_fetched_at <= NOW() - (%s * INTERVAL '1 second')
                  )
            ORDER BY id ASC
            """,
            (revisit_after_seconds,),
        )
        rows = cur.fetchall()
        return _rows_to_dicts(cur, rows)


def reset_queued_targets(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE targets
            SET is_queued = FALSE
            WHERE is_queued = TRUE
            """
        )


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
