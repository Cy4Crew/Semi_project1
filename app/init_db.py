from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.core.db import get_conn, open_pool
from app.core.seed_loader import load_targets_file, load_watchlist_file

BASE_DIR = Path(__file__).resolve().parents[1]
WALLET_TRACKER_SCHEMA_PATH = BASE_DIR / "analyzer" / "schema_wallet_tracker.sql"


def _apply_wallet_tracker_schema(cur) -> None:
    if not WALLET_TRACKER_SCHEMA_PATH.exists():
        raise FileNotFoundError(
            f"wallet tracker schema not found: {WALLET_TRACKER_SCHEMA_PATH}"
        )

    sql = WALLET_TRACKER_SCHEMA_PATH.read_text(encoding="utf-8")
    cur.execute(sql)


def init_db(load_seed_data: bool = True):
    settings.html_dir.mkdir(parents=True, exist_ok=True)
    settings.screenshot_dir.mkdir(parents=True, exist_ok=True)
    settings.text_dir.mkdir(parents=True, exist_ok=True)

    open_pool()

    with get_conn() as conn:
        with conn.cursor() as cur:

            # ================= SCHEMA =================
            for stmt in SCHEMA:
                cur.execute(stmt)

            # ================= MIGRATIONS =================
            for stmt in MIGRATIONS:
                try:
                    cur.execute(stmt)
                except Exception:
                    pass

            # ================= WALLET TRACKER =================
            _apply_wallet_tracker_schema(cur)

            # ================= INDEXES =================
            for stmt in INDEXES:
                cur.execute(stmt)

            # ================= VIEWS =================
            for stmt in VIEWS:
                cur.execute(stmt)

            # ================= SEED =================
            if load_seed_data:
                load_targets_file(conn, settings.targets_seed_path)
                load_watchlist_file(conn, settings.watchlist_seed_path)

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

        conn.commit()


# ================= 기본 테이블 =================

SCHEMA = [

    # ================= targets =================
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

    # ================= pages =================
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

    # ================= extracted_items =================
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

    # ================= watchlist =================
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

    # ================= watchlist_hits =================
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

    # ================= alerts =================
    """
    CREATE TABLE IF NOT EXISTS alerts (
        id BIGSERIAL PRIMARY KEY,
        hit_id BIGINT REFERENCES watchlist_hits(id) ON DELETE CASCADE,
        channel TEXT NOT NULL,
        status TEXT NOT NULL,
        error_message TEXT,
        created_at TIMESTAMPTZ NOT NULL,
        sent_at TIMESTAMPTZ,
        alert_fingerprint TEXT
    )
    """,

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
    """
    CREATE TABLE IF NOT EXISTS tg_wallets (
        id BIGSERIAL PRIMARY KEY,
        channel_name TEXT NOT NULL,
        coin_type TEXT NOT NULL,
        address TEXT NOT NULL,
        tags TEXT,
        collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(channel_name, coin_type, address)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tg_extracted_info (
        id BIGSERIAL PRIMARY KEY,
        channel_name TEXT NOT NULL,
        data_type TEXT NOT NULL,
        value TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'chat',
        collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(channel_name, data_type, value)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tg_private_channels (
        id BIGSERIAL PRIMARY KEY,
        invite_link TEXT NOT NULL,
        channel_id BIGINT,
        channel_name TEXT,
        found_in_channel TEXT,
        collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(invite_link, found_in_channel)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tg_members (
        id BIGSERIAL PRIMARY KEY,
        channel_name TEXT NOT NULL,
        channel_id BIGINT,
        user_id BIGINT NOT NULL,
        username TEXT,
        nickname TEXT,
        collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(channel_id, user_id)
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

    # ================= cache =================
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
]

# ================= INDEX =================

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_pages_url ON pages(url)",
    "CREATE INDEX IF NOT EXISTS idx_pages_host ON pages(host)",
    "CREATE INDEX IF NOT EXISTS idx_watchlist_normalized ON watchlist(normalized)",
    "CREATE INDEX IF NOT EXISTS idx_darkweb_onion ON darkweb_posts(onion_url)",
    "CREATE INDEX IF NOT EXISTS idx_tg_channels_channel_id ON tg_channels(channel_id)",
    "CREATE INDEX IF NOT EXISTS idx_tg_raw_messages_channel_id ON tg_raw_messages(channel_id)",
    "CREATE INDEX IF NOT EXISTS idx_tg_wallets_address ON tg_wallets(address)",
    "CREATE INDEX IF NOT EXISTS idx_tg_wallets_coin_type ON tg_wallets(coin_type)",
    "CREATE INDEX IF NOT EXISTS idx_tg_extracted_info_data_type ON tg_extracted_info(data_type)",
    "CREATE INDEX IF NOT EXISTS idx_tg_extracted_info_value ON tg_extracted_info(value)",
    "CREATE INDEX IF NOT EXISTS idx_tg_members_user_id ON tg_members(user_id)",
]

# ================= VIEW =================

VIEWS = [
    """
    CREATE OR REPLACE VIEW v_wallet_graph_edges AS
    SELECT
        from_address,
        to_address,
        chain,
        SUM(value_sat) AS total_value_sat,
        SUM(value_usd) AS total_value_usd,
        SUM(tx_count) AS tx_count,
        MAX(block_time) AS last_tx_time
    FROM tracked_edges
    GROUP BY from_address, to_address, chain
    """
]

# ================= MIGRATION =================

MIGRATIONS = [
    "ALTER TABLE targets ADD COLUMN IF NOT EXISTS is_queued BOOLEAN DEFAULT FALSE",
    "ALTER TABLE targets ADD COLUMN IF NOT EXISTS last_queued_at TIMESTAMPTZ",
    "ALTER TABLE targets ADD COLUMN IF NOT EXISTS last_fetched_at TIMESTAMPTZ",
    "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS alert_fingerprint TEXT",
    "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS hit_id BIGINT",
]


if __name__ == "__main__":
    init_db()
    print("DB initialized")