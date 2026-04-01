"""worker.py – Background worker for wallet tracing & polling.

Lives in analyzer/ package.  Run via: python -m analyzer.worker
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.core.db import get_conn
from app.init_db import init_db
from .tracer import trace_wallet, insert_edge
from .etherscan_client import client as moralis_client

logger = logging.getLogger("worker")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
try:
    from .evm_filter_config import POLL_BATCH_SIZE, QUEUE_BATCH_SIZE, WORKER_SLEEP_SEC
except ImportError:
    POLL_BATCH_SIZE = 20
    QUEUE_BATCH_SIZE = 10
    WORKER_SLEEP_SEC = 600


# ═══════════════════════════════════════════════════════════════════
# Queue / wallet fetch
# ═══════════════════════════════════════════════════════════════════

def fetch_queue(cur, limit: int = QUEUE_BATCH_SIZE) -> list[dict]:
    """Fetch unprocessed queue items, highest priority first."""
    cur.execute(
        """
        SELECT address, chain
        FROM trace_queue
        WHERE processed = FALSE
        ORDER BY priority DESC, created_at ASC
        LIMIT %s
        """,
        (limit,),
    )
    return cur.fetchall()


def fetch_tracked_wallets(cur, limit: int = POLL_BATCH_SIZE) -> list[dict]:
    """Fetch wallets for incremental polling.

    Skips no_expand wallets.  Prioritises seeds and recently-updated.
    """
    cur.execute(
        """
        SELECT address, chain
        FROM tracked_wallets
        WHERE (no_expand IS NOT TRUE)
          AND (
              is_seed = TRUE
              OR updated_at >= NOW() - INTERVAL '7 days'
              OR updated_at IS NULL
          )
        ORDER BY
            is_seed DESC,
            COALESCE(updated_at, created_at) DESC NULLS LAST
        LIMIT %s
        """,
        (limit,),
    )
    return cur.fetchall()


# ═══════════════════════════════════════════════════════════════════
# Poll: incremental edge updates (no BFS expansion)
# ═══════════════════════════════════════════════════════════════════

def poll_wallet(cur, address: str, chain: str) -> None:
    """Poll recent txs and store edges (no new-node expansion)."""
    if chain == "BTC":
        _poll_btc(cur, address)
    else:
        _poll_evm(cur, address, chain)


def _poll_btc(cur, address: str) -> None:
    try:
        from .mempool_client import client as btc_client
        txs = btc_client.get_address_txs(address, 10)
        if not txs:
            return
        for tx in txs:
            ts = tx.get("status", {}).get("block_time")
            for v in tx.get("vout", []):
                to_addr = v.get("scriptpubkey_address")
                sat = v.get("value", 0)
                if to_addr and sat:
                    insert_edge(cur, address, to_addr, "BTC",
                                value_sat=sat, value_usd=0, tx_count=1, ts=ts)
    except Exception:
        logger.exception("[Worker] BTC poll error %s", address)


def _poll_evm(cur, address: str, chain: str) -> None:
    try:
        data = moralis_client.get_wallet_history(address, chain=chain, limit=10)
        txs = data.get("result", []) if isinstance(data, dict) else []

        for tx in txs:
            from_addr = (tx.get("from_address") or "").lower().strip()
            to_addr = (tx.get("to_address") or "").lower().strip()
            if not from_addr or not to_addr or from_addr == to_addr:
                continue
            try:
                value_wei = int(Decimal(str(tx.get("value") or "0")))
            except (InvalidOperation, ValueError):
                value_wei = 0
            value_native = Decimal(value_wei) / Decimal(10**18)
            ts_raw = tx.get("block_timestamp")
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")) if ts_raw else None
            except Exception:
                ts = None
            insert_edge(
                cur,
                from_addr=from_addr, to_addr=to_addr, chain=chain,
                value_sat=0, value_native=value_native, value_usd=0,
                tx_count=1, ts=ts,
            )
    except Exception:
        logger.exception("[Worker] EVM poll error %s/%s", address, chain)


# ═══════════════════════════════════════════════════════════════════
# Main loop
# ═══════════════════════════════════════════════════════════════════

def run_worker() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    init_db(load_seed_data=False)
    logger.info("[Worker] Starting (queue=%d, poll=%d, sleep=%ds)",
                QUEUE_BATCH_SIZE, POLL_BATCH_SIZE, WORKER_SLEEP_SEC)

    while True:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    # Phase 1: BFS trace queue
                    for job in fetch_queue(cur):
                        addr, ch = job["address"], job["chain"]
                        try:
                            trace_wallet(addr, ch)
                            logger.info("[Worker] Traced %s/%s", addr, ch)
                        except Exception:
                            logger.exception("[Worker] Trace failed %s/%s", addr, ch)

                    # Phase 2: incremental poll
                    for w in fetch_tracked_wallets(cur):
                        try:
                            poll_wallet(cur, w["address"], w["chain"])
                        except Exception:
                            logger.exception("[Worker] Poll failed %s/%s",
                                             w["address"], w["chain"])

                    conn.commit()
        except Exception:
            logger.exception("[Worker] Loop error")

        time.sleep(WORKER_SLEEP_SEC)


if __name__ == "__main__":
    run_worker()
