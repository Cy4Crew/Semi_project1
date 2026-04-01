"""bridge.py – Telegram/darkweb → wallet tracker bridge.

This module is imported from app.telegram (outside analyzer package),
so it uses absolute imports for analyzer internals.
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger("bridge")


def _convert_tags(tags_str: str) -> list[str]:
    risk_tags: list[str] = []
    if not tags_str:
        return risk_tags
    t = tags_str.lower()
    if "ransomware" in t:
        risk_tags.append("ransomware")
    if "db_leak" in t or "data_stealer" in t:
        risk_tags.append("high_volume")
    if "access_sale" in t:
        risk_tags.append("large_tx")
    return risk_tags


def _calc_risk_score(tags: list[str]) -> int:
    weights = {"ransomware": 80, "high_volume": 50, "large_tx": 40}
    if not tags:
        return 0
    uniq = list(dict.fromkeys(tags))
    base = max(weights.get(t, 20) for t in uniq)
    bonus = max(0, len(uniq) - 1) * 7
    return min(100, base + bonus)


def _maybe_register_stream(address: str, chain: str) -> None:
    if chain == "BTC":
        return
    try:
        from analyzer.etherscan_client import client as moralis_client, STREAM_CHAIN_IDS
        from app.core.db import get_conn

        webhook_url = os.getenv("MORALIS_STREAM_WEBHOOK_URL", "").strip()
        if not webhook_url:
            return

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT stream_id FROM moralis_stream_state WHERE chain = %s LIMIT 1",
                    (chain,),
                )
                row = cur.fetchone()
                stream_id = row["stream_id"] if row and row.get("stream_id") else None

                if not stream_id:
                    created = moralis_client.create_stream(
                        chain_ids=[STREAM_CHAIN_IDS[chain]],
                        webhook_url=webhook_url,
                        description=f"wallet-tracker-{chain.lower()}",
                        tag=f"wallet-tracker-{chain.lower()}",
                    )
                    stream_id = created.get("id")
                    if stream_id:
                        cur.execute(
                            """
                            INSERT INTO moralis_stream_state (chain, stream_id, webhook_url, status, updated_at)
                            VALUES (%s, %s, %s, %s, NOW())
                            ON CONFLICT (chain) DO UPDATE SET
                                stream_id = EXCLUDED.stream_id,
                                webhook_url = EXCLUDED.webhook_url,
                                status = EXCLUDED.status,
                                updated_at = NOW()
                            """,
                            (chain, stream_id, webhook_url, created.get("status", "active")),
                        )

                if stream_id:
                    moralis_client.add_address_to_stream(stream_id, address)
            conn.commit()
    except Exception:
        logger.exception("[Bridge] stream register failed")


def on_wallet_recorded(
    channel_name: str,
    coin_type: str,
    address: str,
    tags_str: str = "",
) -> None:
    if coin_type not in ("BTC", "BTC_BECH32", "BTC_LEGACY", "ETH", "ETH_ERC20"):
        logger.warning("[Bridge] unsupported coin_type=%s", coin_type)
        return

    try:
        from app.core.db import get_conn

        risk_tags = _convert_tags(tags_str)
        risk_score = _calc_risk_score(risk_tags)
        chain = "ETH" if coin_type.startswith("ETH") else "BTC"

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tracked_wallets
                        (address, chain, category, is_seed, depth, source, source_detail,
                         channel_name, original_tags, risk_tags, risk_score,
                         is_contract, no_expand, created_at, updated_at)
                    VALUES (%s, %s, 'seller', TRUE, 0, 'telegram', %s, %s, %s, %s, %s,
                            FALSE, FALSE, NOW(), NOW())
                    ON CONFLICT (address, chain) DO UPDATE SET
                        updated_at = NOW(),
                        source_detail = EXCLUDED.source_detail,
                        channel_name = EXCLUDED.channel_name,
                        original_tags = EXCLUDED.original_tags,
                        risk_tags = EXCLUDED.risk_tags,
                        risk_score = GREATEST(tracked_wallets.risk_score, EXCLUDED.risk_score)
                    """,
                    (
                        address, chain, channel_name, channel_name, tags_str,
                        json.dumps(risk_tags), risk_score,
                    ),
                )

                # Use tracer.queue_wallet for consistency
                try:
                    from analyzer.tracer import queue_wallet
                    queue_wallet(cur, address, chain, priority=1)
                except ImportError:
                    # Fallback if analyzer not on path
                    cur.execute(
                        """
                        INSERT INTO trace_queue (address, chain, priority, processed)
                        VALUES (%s, %s, 1, FALSE)
                        ON CONFLICT (address, chain) DO UPDATE SET
                            processed = FALSE,
                            priority = GREATEST(trace_queue.priority, 1)
                        """,
                        (address, chain),
                    )

            conn.commit()

        _maybe_register_stream(address, chain)

    except Exception:
        logger.exception("[Bridge] 실패")
