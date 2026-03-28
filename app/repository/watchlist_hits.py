from __future__ import annotations


def _as_dict(row, columns: list[str]) -> dict | None:
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    return {col: row[idx] for idx, col in enumerate(columns)}


def get_watchlist_hit_by_fingerprint(conn, fingerprint: str):
    columns = [
        "id",
        "extracted_item_id",
        "watchlist_id",
        "page_id",
        "matched_value",
        "fingerprint",
        "first_seen_at",
        "last_seen_at",
        "last_alerted_at",
    ]

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                extracted_item_id,
                watchlist_id,
                page_id,
                matched_value,
                fingerprint,
                first_seen_at,
                last_seen_at,
                last_alerted_at
            FROM watchlist_hits
            WHERE fingerprint = %s
            LIMIT 1
            """,
            (fingerprint,),
        )
        row = cur.fetchone()

    return _as_dict(row, columns)


def upsert_watchlist_hit(
    conn,
    *,
    extracted_item_id: int,
    watchlist_id: int,
    page_id: int,
    matched_value: str,
    fingerprint: str,
    seen_at: str,
):
    existing = get_watchlist_hit_by_fingerprint(conn, fingerprint)

    if existing:
        columns = ["hit_id", "last_alerted_at"]
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE watchlist_hits
                SET
                    extracted_item_id = %s,
                    page_id = %s,
                    matched_value = %s,
                    last_seen_at = %s
                WHERE id = %s
                RETURNING id AS hit_id, last_alerted_at
                """,
                (
                    extracted_item_id,
                    page_id,
                    matched_value,
                    seen_at,
                    existing["id"],
                ),
            )
            row = cur.fetchone()

        result = _as_dict(row, columns)
        return {
            "hit_id": result["hit_id"],
            "is_new": False,
            "last_alerted_at": result["last_alerted_at"],
        }

    columns = ["hit_id", "last_alerted_at"]
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO watchlist_hits (
                extracted_item_id,
                watchlist_id,
                page_id,
                matched_value,
                fingerprint,
                first_seen_at,
                last_seen_at,
                last_alerted_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, NULL)
            RETURNING id AS hit_id, last_alerted_at
            """,
            (
                extracted_item_id,
                watchlist_id,
                page_id,
                matched_value,
                fingerprint,
                seen_at,
                seen_at,
            ),
        )
        row = cur.fetchone()

    result = _as_dict(row, columns)
    return {
        "hit_id": result["hit_id"],
        "is_new": True,
        "last_alerted_at": result["last_alerted_at"],
    }


def touch_last_alerted_at(conn, *, hit_id: int, alerted_at: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE watchlist_hits
            SET last_alerted_at = %s
            WHERE id = %s
            """,
            (alerted_at, hit_id),
        )


def get_hit_detail(conn, hit_id: int):
    columns = [
        "id",
        "matched_value",
        "fingerprint",
        "first_seen_at",
        "last_seen_at",
        "last_alerted_at",
        "page_id",
        "watchlist_id",
        "url",
        "title",
        "screenshot_path",
        "watch_type",
        "watch_value",
        "label",
    ]

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                h.id,
                h.matched_value,
                h.fingerprint,
                h.first_seen_at,
                h.last_seen_at,
                h.last_alerted_at,
                h.page_id,
                h.watchlist_id,
                p.url,
                p.title,
                p.screenshot_path,
                w.type AS watch_type,
                w.normalized AS watch_value,
                w.label
            FROM watchlist_hits h
            LEFT JOIN pages p ON p.id = h.page_id
            LEFT JOIN watchlist w ON w.id = h.watchlist_id
            WHERE h.id = %s
            LIMIT 1
            """,
            (hit_id,),
        )
        row = cur.fetchone()

    return _as_dict(row, columns)


def list_recent_hits(conn, limit: int = 20, offset: int = 0) -> list[dict]:
    columns = [
        "id",
        "matched_value",
        "fingerprint",
        "first_seen_at",
        "last_seen_at",
        "last_alerted_at",
        "page_id",
        "watchlist_id",
        "url",
        "title",
        "screenshot_path",
        "watch_type",
        "watch_value",
        "label",
    ]

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                h.id,
                h.matched_value,
                h.fingerprint,
                h.first_seen_at,
                h.last_seen_at,
                h.last_alerted_at,
                h.page_id,
                h.watchlist_id,
                p.url,
                p.title,
                p.screenshot_path,
                w.type AS watch_type,
                w.normalized AS watch_value,
                w.label
            FROM watchlist_hits h
            LEFT JOIN pages p ON p.id = h.page_id
            LEFT JOIN watchlist w ON w.id = h.watchlist_id
            ORDER BY h.id DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        rows = cur.fetchall()

    return [_as_dict(row, columns) for row in rows]