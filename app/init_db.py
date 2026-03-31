from __future__ import annotations

from app.core.config import settings
from app.core.db import get_conn, open_pool
from app.core.seed_loader import load_targets_file, load_watchlist_file

SCHEMA = [
    # ================= 기존 =================
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
        sent_at TIMESTAMPTZ,
        alert_fingerprint TEXT
    )
    """,

    # ================= ⭐ 핵심: darkweb_posts 확장 =================
    """
    CREATE TABLE IF NOT EXISTS darkweb_posts (
        id BIGSERIAL PRIMARY KEY,
        source TEXT,
        victim TEXT,
        group_name TEXT,
        description TEXT,

        post_url TEXT,
        discovered_at TIMESTAMPTZ,
        attack_date TIMESTAMPTZ,

        category TEXT,
        is_corp BOOLEAN,
        confidence FLOAT,

        has_onion BOOLEAN,
        onion_url TEXT,

        matched_keywords TEXT[],
        telegram_links TEXT[],

        raw JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,

    # ================= ⭐ 캐시 테이블 추가 =================
    """
    CREATE TABLE IF NOT EXISTS rl_info_cache (
        id INTEGER PRIMARY KEY,
        payload JSONB,
        fetched_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rl_victims_cache (
        id INTEGER PRIMARY KEY,
        payload JSONB,
        fetched_at TIMESTAMPTZ
    )
    """,

    # ================= Telegram =================
    """
    CREATE TABLE IF NOT EXISTS tg_channels (
        id BIGSERIAL PRIMARY KEY,
        channel_name TEXT,
        channel_id BIGINT UNIQUE,
        source_type TEXT NOT NULL DEFAULT 'entered',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tg_channel_admins (
        id BIGSERIAL PRIMARY KEY,
        tg_channel_id BIGINT NOT NULL REFERENCES tg_channels(id) ON DELETE CASCADE,
        admin_user_id BIGINT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(tg_channel_id, admin_user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tg_raw_messages (
        id BIGSERIAL PRIMARY KEY,
        channel_name TEXT,
        channel_id BIGINT,
        sender_id BIGINT,
        sender_name TEXT,
        message_id BIGINT,
        content TEXT,
        original_timestamp TIMESTAMPTZ,
        source TEXT NOT NULL DEFAULT 'chat',
        collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(channel_id, message_id)
    )
    """,
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_pages_url ON pages(url)",
    "CREATE INDEX IF NOT EXISTS idx_pages_host ON pages(host)",
    "CREATE INDEX IF NOT EXISTS idx_darkweb_onion ON darkweb_posts(onion_url)",
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

            # 안전 마이그레이션
            cur.execute("""
                ALTER TABLE darkweb_posts
                ADD COLUMN IF NOT EXISTS post_url TEXT,
                ADD COLUMN IF NOT EXISTS discovered_at TIMESTAMPTZ,
                ADD COLUMN IF NOT EXISTS attack_date TIMESTAMPTZ,
                ADD COLUMN IF NOT EXISTS has_onion BOOLEAN,
                ADD COLUMN IF NOT EXISTS onion_url TEXT,
                ADD COLUMN IF NOT EXISTS confidence FLOAT
            """)

            cur.execute(
                "ALTER TABLE targets ADD COLUMN IF NOT EXISTS is_queued BOOLEAN NOT NULL DEFAULT FALSE"
            )

            for stmt in INDEXES:
                cur.execute(stmt)

            # ⭐ 캐시 기본 row 생성 (에러 방지 핵심)
            cur.execute("""
                INSERT INTO rl_info_cache (id, payload, fetched_at)
                VALUES (1, '{}'::jsonb, NOW())
                ON CONFLICT (id) DO NOTHING
            """)

            cur.execute("""
                INSERT INTO rl_victims_cache (id, payload, fetched_at)
                VALUES (1, '{}'::jsonb, NOW())
                ON CONFLICT (id) DO NOTHING
            """)

        if load_seed_data:
            load_targets_file(conn, settings.targets_seed_path)
            load_watchlist_file(conn, settings.watchlist_seed_path)

        conn.commit()


if __name__ == "__main__":
    init_db()
    print("DB initialized")