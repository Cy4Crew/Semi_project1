from __future__ import annotations

from typing import Any


def get_latest_page_snapshot(conn, url: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, url, fetched_at, status_code, title, content_hash, last_changed_at,
                   is_meaningful, skip_reason, content_changed
            FROM pages
            WHERE url = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (url,),
        )
        return cur.fetchone()


def save_page(
    conn,
    *,
    target_id: int | None,
    url: str,
    host: str,
    title: str | None,
    status_code: int | None,
    fetched_at: str,
    content_hash: str,
    last_changed_at: str | None,
    is_meaningful: bool,
    skip_reason: str | None,
    content_changed: bool,
    raw_html_path: str | None,
    text_dump_path: str | None,
    screenshot_path: str | None,
    error_message: str | None = None,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pages(
                target_id, url, host, title, status_code, fetched_at, content_hash,
                last_changed_at, is_meaningful, skip_reason, content_changed,
                raw_html_path, text_dump_path, screenshot_path, error_message
            ) VALUES(%s, %s, %s, %s, %s, %s::timestamptz, %s, %s::timestamptz, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                target_id, url, host, title, status_code, fetched_at, content_hash,
                last_changed_at, is_meaningful, skip_reason, content_changed,
                raw_html_path, text_dump_path, screenshot_path, error_message,
            ),
        )
        return int(cur.fetchone()["id"])


def list_recent_pages(conn, limit: int = 100) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.id, p.target_id, t.name AS target_name, p.url, p.host, p.title, p.status_code,
                   p.fetched_at, p.content_hash, p.last_changed_at, p.is_meaningful, p.skip_reason,
                   p.content_changed, p.raw_html_path, p.text_dump_path, p.screenshot_path, p.error_message
            FROM pages p
            LEFT JOIN targets t ON t.id = p.target_id
            ORDER BY p.id DESC
            LIMIT %s
            """,
            (limit,),
        )
        return list(cur.fetchall())
