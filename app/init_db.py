from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.core.db import get_conn, open_pool
from app.core.seed_loader import load_targets_file, load_watchlist_file

BASE_DIR = Path(__file__).resolve().parents[1]
WALLET_TRACKER_SCHEMA_PATH = BASE_DIR / "analyzer" / "schema_wallet_tracker.sql"

SCHEMA = [
    "CREATE TABLE IF NOT EXISTS targets (id BIGSERIAL PRIMARY KEY,name TEXT NOT NULL,seed_url TEXT NOT NULL UNIQUE,enabled BOOLEAN NOT NULL DEFAULT TRUE,is_queued BOOLEAN NOT NULL DEFAULT FALSE,last_queued_at TIMESTAMPTZ,last_fetched_at TIMESTAMPTZ,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())",
    "CREATE TABLE IF NOT EXISTS pages (id BIGSERIAL PRIMARY KEY,target_id BIGINT REFERENCES targets(id) ON DELETE SET NULL,url TEXT NOT NULL,host TEXT,title TEXT,status_code INTEGER,fetched_at TIMESTAMPTZ NOT NULL,content_hash TEXT,last_changed_at TIMESTAMPTZ,is_meaningful BOOLEAN NOT NULL DEFAULT FALSE,skip_reason TEXT,content_changed BOOLEAN NOT NULL DEFAULT TRUE,raw_html_path TEXT,text_dump_path TEXT,screenshot_path TEXT,error_message TEXT)",
    "CREATE TABLE IF NOT EXISTS extracted_items (id BIGSERIAL PRIMARY KEY,page_id BIGINT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,type TEXT NOT NULL,raw TEXT NOT NULL,normalized TEXT NOT NULL,group_key TEXT,first_seen_at TIMESTAMPTZ NOT NULL,UNIQUE(page_id,type,normalized))",
    "CREATE TABLE IF NOT EXISTS watchlist (id BIGSERIAL PRIMARY KEY,type TEXT NOT NULL,value TEXT NOT NULL,normalized TEXT NOT NULL,label TEXT,enabled BOOLEAN NOT NULL DEFAULT TRUE,is_regex BOOLEAN NOT NULL DEFAULT FALSE,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),UNIQUE(type,normalized))",
    "CREATE TABLE IF NOT EXISTS watchlist_hits (id BIGSERIAL PRIMARY KEY,extracted_item_id BIGINT NOT NULL REFERENCES extracted_items(id) ON DELETE CASCADE,watchlist_id BIGINT NOT NULL REFERENCES watchlist(id) ON DELETE CASCADE,page_id BIGINT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,matched_value TEXT NOT NULL,fingerprint TEXT NOT NULL UNIQUE,first_seen_at TIMESTAMPTZ NOT NULL,last_seen_at TIMESTAMPTZ NOT NULL,last_alerted_at TIMESTAMPTZ)",
    "CREATE TABLE IF NOT EXISTS alerts (id BIGSERIAL PRIMARY KEY,hit_id BIGINT NOT NULL REFERENCES watchlist_hits(id) ON DELETE CASCADE,channel TEXT NOT NULL,status TEXT NOT NULL,error_message TEXT,created_at TIMESTAMPTZ NOT NULL,sent_at TIMESTAMPTZ,alert_fingerprint TEXT)",
    "CREATE TABLE IF NOT EXISTS tg_channels (id BIGSERIAL PRIMARY KEY,channel_name TEXT,channel_id BIGINT UNIQUE,source_type TEXT NOT NULL DEFAULT 'entered',created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())",
    "CREATE TABLE IF NOT EXISTS tg_channel_admins (id BIGSERIAL PRIMARY KEY,tg_channel_id BIGINT NOT NULL REFERENCES tg_channels(id) ON DELETE CASCADE,admin_user_id BIGINT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),UNIQUE(tg_channel_id,admin_user_id))",
    "CREATE TABLE IF NOT EXISTS tg_raw_messages (id BIGSERIAL PRIMARY KEY,channel_name TEXT,channel_id BIGINT,sender_id BIGINT,sender_name TEXT,message_id BIGINT,content TEXT,original_timestamp TIMESTAMPTZ,source TEXT NOT NULL DEFAULT 'chat',collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),UNIQUE(channel_id,message_id))",
    "CREATE TABLE IF NOT EXISTS tg_wallets (id BIGSERIAL PRIMARY KEY,channel_name TEXT NOT NULL,coin_type TEXT NOT NULL,address TEXT NOT NULL,tags TEXT,collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),UNIQUE(channel_name,coin_type,address))",
    "CREATE TABLE IF NOT EXISTS tg_extracted_info (id BIGSERIAL PRIMARY KEY,channel_name TEXT NOT NULL,data_type TEXT NOT NULL,value TEXT NOT NULL,source TEXT NOT NULL DEFAULT 'chat',collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),UNIQUE(channel_name,data_type,value))",
    "CREATE TABLE IF NOT EXISTS tg_private_channels (id BIGSERIAL PRIMARY KEY,invite_link TEXT NOT NULL,channel_id BIGINT,channel_name TEXT,found_in_channel TEXT,collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),UNIQUE(invite_link,found_in_channel))",
    "CREATE TABLE IF NOT EXISTS tg_members (id BIGSERIAL PRIMARY KEY,channel_name TEXT NOT NULL,channel_id BIGINT,user_id BIGINT NOT NULL,username TEXT,nickname TEXT,collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),UNIQUE(channel_id,user_id))",
    "CREATE TABLE IF NOT EXISTS tracked_transactions (id BIGSERIAL PRIMARY KEY,txid TEXT NOT NULL UNIQUE,block_height INTEGER,block_time TIMESTAMPTZ,fee_sat BIGINT DEFAULT 0,is_coinbase BOOLEAN NOT NULL DEFAULT FALSE,confirmed BOOLEAN NOT NULL DEFAULT FALSE,is_analysis_root BOOLEAN NOT NULL DEFAULT FALSE)",
    "CREATE TABLE IF NOT EXISTS wallet_alert_history (id BIGSERIAL PRIMARY KEY,wallet_address TEXT NOT NULL,txid TEXT NOT NULL,amount_sat BIGINT NOT NULL DEFAULT 0,amount_usd REAL NOT NULL DEFAULT 0,alert_type TEXT NOT NULL DEFAULT 'large_deposit',channel TEXT NOT NULL DEFAULT 'discord',status TEXT NOT NULL DEFAULT 'pending',sent_at TIMESTAMPTZ,error_message TEXT DEFAULT '',created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())",
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
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_alerts_alert_fingerprint_channel ON alerts(alert_fingerprint,channel) WHERE alert_fingerprint IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_tg_channels_channel_id ON tg_channels(channel_id)",
    "CREATE INDEX IF NOT EXISTS idx_tg_raw_messages_channel_id ON tg_raw_messages(channel_id)",
    "CREATE INDEX IF NOT EXISTS idx_tg_wallets_address ON tg_wallets(address)",
    "CREATE INDEX IF NOT EXISTS idx_tg_wallets_coin_type ON tg_wallets(coin_type)",
    "CREATE INDEX IF NOT EXISTS idx_tg_extracted_info_data_type ON tg_extracted_info(data_type)",
    "CREATE INDEX IF NOT EXISTS idx_tg_extracted_info_value ON tg_extracted_info(value)",
    "CREATE INDEX IF NOT EXISTS idx_tg_members_user_id ON tg_members(user_id)",
]

VIEWS = [
    "CREATE OR REPLACE VIEW v_wallet_graph_edges AS SELECT from_address,to_address,chain,SUM(value_sat) AS total_value_sat,SUM(value_usd) AS total_value_usd,SUM(tx_count) AS tx_count,MAX(block_time) AS last_tx_time FROM tracked_edges GROUP BY from_address,to_address,chain",
]

MIGRATIONS = [
    "ALTER TABLE targets ADD COLUMN IF NOT EXISTS is_queued BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE targets ADD COLUMN IF NOT EXISTS last_queued_at TIMESTAMPTZ",
    "ALTER TABLE targets ADD COLUMN IF NOT EXISTS last_fetched_at TIMESTAMPTZ",
    "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS alert_fingerprint TEXT",
    "ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS is_regex BOOLEAN NOT NULL DEFAULT FALSE",
]


def _reconcile_wallet_tracker_schema(cur) -> None:
    """Make legacy wallet-tracker tables compatible with analyzer/*.py."""
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'tracked_wallets') AS exists"
    )
    if cur.fetchone()["exists"]:
        cur.execute("ALTER TABLE tracked_wallets ADD COLUMN IF NOT EXISTS chain TEXT NOT NULL DEFAULT 'BTC'")
        cur.execute("ALTER TABLE tracked_wallets ADD COLUMN IF NOT EXISTS category TEXT")
        cur.execute("ALTER TABLE tracked_wallets ADD COLUMN IF NOT EXISTS is_seed BOOLEAN DEFAULT FALSE")
        cur.execute("ALTER TABLE tracked_wallets ADD COLUMN IF NOT EXISTS depth INTEGER DEFAULT 0")
        cur.execute("ALTER TABLE tracked_wallets ADD COLUMN IF NOT EXISTS source TEXT")
        cur.execute("ALTER TABLE tracked_wallets ADD COLUMN IF NOT EXISTS source_detail TEXT")
        cur.execute("ALTER TABLE tracked_wallets ADD COLUMN IF NOT EXISTS channel_name TEXT")
        cur.execute("ALTER TABLE tracked_wallets ADD COLUMN IF NOT EXISTS original_tags TEXT")
        cur.execute("ALTER TABLE tracked_wallets ADD COLUMN IF NOT EXISTS risk_tags JSONB DEFAULT '[]'")
        cur.execute("ALTER TABLE tracked_wallets ADD COLUMN IF NOT EXISTS risk_score INTEGER DEFAULT 0")
        cur.execute("ALTER TABLE tracked_wallets ADD COLUMN IF NOT EXISTS label TEXT")
        cur.execute("ALTER TABLE tracked_wallets ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ")
        cur.execute("ALTER TABLE tracked_wallets ADD COLUMN IF NOT EXISTS balance_sat NUMERIC DEFAULT 0")
        cur.execute("ALTER TABLE tracked_wallets ADD COLUMN IF NOT EXISTS total_received_sat NUMERIC DEFAULT 0")
        cur.execute("ALTER TABLE tracked_wallets ADD COLUMN IF NOT EXISTS total_sent_sat NUMERIC DEFAULT 0")
        cur.execute("ALTER TABLE tracked_wallets ADD COLUMN IF NOT EXISTS balance_wei NUMERIC DEFAULT 0")
        cur.execute("ALTER TABLE tracked_wallets ADD COLUMN IF NOT EXISTS total_received_wei NUMERIC DEFAULT 0")
        cur.execute("ALTER TABLE tracked_wallets ADD COLUMN IF NOT EXISTS total_sent_wei NUMERIC DEFAULT 0")
        cur.execute("ALTER TABLE tracked_wallets ADD COLUMN IF NOT EXISTS is_contract BOOLEAN DEFAULT FALSE")
        cur.execute("ALTER TABLE tracked_wallets ADD COLUMN IF NOT EXISTS no_expand BOOLEAN DEFAULT FALSE")

    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'tracked_edges') AS exists"
    )
    if cur.fetchone()["exists"]:
        cur.execute("ALTER TABLE tracked_edges ADD COLUMN IF NOT EXISTS chain TEXT NOT NULL DEFAULT 'BTC'")
        cur.execute("ALTER TABLE tracked_edges ADD COLUMN IF NOT EXISTS value_native NUMERIC DEFAULT 0")
        cur.execute("ALTER TABLE tracked_edges ADD COLUMN IF NOT EXISTS tx_count INTEGER DEFAULT 1")
        cur.execute("ALTER TABLE tracked_edges ADD COLUMN IF NOT EXISTS value_usd NUMERIC DEFAULT 0")
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'tracked_edges' AND column_name = 'txid') AS exists"
        )
        if cur.fetchone()["exists"]:
            cur.execute("ALTER TABLE tracked_edges ALTER COLUMN txid DROP NOT NULL")


def _apply_wallet_tracker_schema(cur) -> None:
    if not WALLET_TRACKER_SCHEMA_PATH.exists():
        raise FileNotFoundError(f"wallet tracker schema not found: {WALLET_TRACKER_SCHEMA_PATH}")
    cur.execute(WALLET_TRACKER_SCHEMA_PATH.read_text(encoding="utf-8"))
    _reconcile_wallet_tracker_schema(cur)


def init_db(load_seed_data: bool = True):
    settings.html_dir.mkdir(parents=True, exist_ok=True)
    settings.screenshot_dir.mkdir(parents=True, exist_ok=True)
    settings.text_dir.mkdir(parents=True, exist_ok=True)
    open_pool()
    with get_conn() as conn:
        with conn.cursor() as cur:
            for stmt in SCHEMA:
                cur.execute(stmt)
            for stmt in MIGRATIONS:
                try:
                    cur.execute(stmt)
                except Exception:
                    pass
            _apply_wallet_tracker_schema(cur)
            for stmt in INDEXES:
                cur.execute(stmt)
            for stmt in VIEWS:
                cur.execute(stmt)
        if load_seed_data:
            load_targets_file(conn, settings.targets_seed_path)
            load_watchlist_file(conn, settings.watchlist_seed_path)
        conn.commit()


if __name__ == "__main__":
    init_db()
    print("DB initialized")
