from __future__ import annotations

from typing import Any

from app.crawler.extractor import normalize_value


def create_watchlist_item(
    conn,
    *,
    item_type: str,
    value: str,
    label: str | None = None,
    is_regex: bool = False,
) -> int:
    """watchlist 항목 1건을 INSERT(또는 UPSERT)한다.

    is_regex=True 인 경우 normalized 컬럼에 원본 패턴 문자열을 그대로 저장한다.
    (정규표현식 패턴은 normalize_value 로 변형하면 안 됨)
    """
    if is_regex:
        # 정규표현식 패턴은 소문자 정규화만 적용 (strip 등 최소한만)
        normalized = value.strip().lower()
    else:
        normalized = normalize_value(item_type, value)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO watchlist(type, value, normalized, label, enabled, is_regex)
            VALUES(%s, %s, %s, %s, TRUE, %s)
            ON CONFLICT (type, normalized)
            DO UPDATE SET
                value      = EXCLUDED.value,
                label      = EXCLUDED.label,
                is_regex   = EXCLUDED.is_regex
            RETURNING id
            """,
            (item_type.strip().lower(), value.strip(), normalized, label, is_regex),
        )
        return int(cur.fetchone()["id"])


def list_watchlist(conn) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, type, value, normalized, label, enabled, is_regex, created_at
            FROM watchlist
            ORDER BY id DESC
            """
        )
        return list(cur.fetchall())


def list_enabled_watchlist(conn) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, type, value, normalized, label, is_regex
            FROM watchlist
            WHERE enabled = TRUE
            ORDER BY id ASC
            """
        )
        return list(cur.fetchall())


def delete_watchlist_item(conn, watchlist_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM watchlist WHERE id = %s", (watchlist_id,))
