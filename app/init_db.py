from __future__ import annotations

from app.core.config import settings
from app.core.db import get_conn, open_pool
from app.core.seed_loader import load_targets_file, load_watchlist_file

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS targets (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        seed_url TEXT NOT NULL UNIQUE,
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        is_queued BOOLEAN NOT NULL DEFAULT FALSE,
        last_queued_at TIMESTAMPTZ,
        last_fetched_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pages (
        id BIGSERIAL PRIMARY KEY,
        target_id BIGINT REFERENCES targets(id) ON DELETE SET NULL,
        url TEXT NOT NULL,
        host TEXT,
        title TEXT,
        status_code INTEGER,
        fetched_at TIMESTAMPTZ NOT NULL,
        content_hash TEXT,
        last_changed_at TIMESTAMPTZ,
        is_meaningful BOOLEAN NOT NULL DEFAULT FALSE,
        skip_reason TEXT,
        content_changed BOOLEAN NOT NULL DEFAULT TRUE,
        raw_html_path TEXT,
        text_dump_path TEXT,
        screenshot_path TEXT,
        error_message TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS extracted_items (
        id BIGSERIAL PRIMARY KEY,
        page_id BIGINT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
        type TEXT NOT NULL,
        raw TEXT NOT NULL,
        normalized TEXT NOT NULL,
        group_key TEXT,
        first_seen_at TIMESTAMPTZ NOT NULL,
        UNIQUE(page_id, type, normalized)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS watchlist (
        id BIGSERIAL PRIMARY KEY,
        type TEXT NOT NULL,
        value TEXT NOT NULL,
        normalized TEXT NOT NULL,
        label TEXT,
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        is_regex BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(type, normalized)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS watchlist_hits (
        id BIGSERIAL PRIMARY KEY,
        extracted_item_id BIGINT NOT NULL REFERENCES extracted_items(id) ON DELETE CASCADE,
        watchlist_id BIGINT NOT NULL REFERENCES watchlist(id) ON DELETE CASCADE,
        page_id BIGINT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
        matched_value TEXT NOT NULL,
        fingerprint TEXT NOT NULL UNIQUE,
        first_seen_at TIMESTAMPTZ NOT NULL,
        last_seen_at TIMESTAMPTZ NOT NULL,
        last_alerted_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS alerts (
        id BIGSERIAL PRIMARY KEY,
        hit_id BIGINT NOT NULL REFERENCES watchlist_hits(id) ON DELETE CASCADE,
        channel TEXT NOT NULL,
        status TEXT NOT NULL,
        error_message TEXT,
        created_at TIMESTAMPTZ NOT NULL,
        sent_at TIMESTAMPTZ
    )
    """,
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_pages_url ON pages(url)",
    "CREATE INDEX IF NOT EXISTS idx_pages_host ON pages(host)",
    "CREATE INDEX IF NOT EXISTS idx_extracted_items_normalized ON extracted_items(normalized)",
    "CREATE INDEX IF NOT EXISTS idx_extracted_items_group_key ON extracted_items(group_key)",
    "CREATE INDEX IF NOT EXISTS idx_watchlist_normalized ON watchlist(normalized)",
    "CREATE INDEX IF NOT EXISTS idx_watchlist_hits_watchlist_id ON watchlist_hits(watchlist_id)",
    "CREATE INDEX IF NOT EXISTS idx_watchlist_hits_last_seen_at ON watchlist_hits(last_seen_at)",
    "CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status)",
]


def init_db(load_seed_data: bool = True) -> None:
    settings.html_dir.mkdir(parents=True, exist_ok=True)
    settings.screenshot_dir.mkdir(parents=True, exist_ok=True)
    settings.text_dir.mkdir(parents=True, exist_ok=True)

    open_pool()

    with get_conn() as conn:
        with conn.cursor() as cur:
            for stmt in SCHEMA:
                cur.execute(stmt)

            cur.execute(
                "ALTER TABLE targets ADD COLUMN IF NOT EXISTS is_queued BOOLEAN NOT NULL DEFAULT FALSE"
            )
            cur.execute(
                "ALTER TABLE targets ADD COLUMN IF NOT EXISTS last_queued_at TIMESTAMPTZ"
            )
            cur.execute(
                "ALTER TABLE targets ADD COLUMN IF NOT EXISTS last_fetched_at TIMESTAMPTZ"
            )

            # watchlist 정규표현식 지원 마이그레이션
            cur.execute(
                "ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS is_regex BOOLEAN NOT NULL DEFAULT FALSE"
            )

            for stmt in INDEXES:
                cur.execute(stmt)

        if load_seed_data:
            load_targets_file(conn, settings.targets_seed_path)
            load_watchlist_file(conn, settings.watchlist_seed_path)

        conn.commit()


if __name__ == "__main__":
    init_db()
    print("DB initialized")