"""routes_graph.py – FastAPI graph data endpoints.

Lives in analyzer/ package.
Uses psycopg (v3) with dict_row – matching app.core.db and requirements.txt.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row
from fastapi import APIRouter, Header, Query, Request

logger = logging.getLogger("routes_graph")
router = APIRouter()


def get_conn_direct():
    """Standalone psycopg3 connection for graph endpoints.

    Returns a connection with dict_row so rows behave like dicts.
    The caller is responsible for closing the connection.
    """
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "db"),
        dbname=os.getenv("POSTGRES_DB", "intel"),
        user=os.getenv("POSTGRES_USER", "intel"),
        password=os.getenv("POSTGRES_PASSWORD", "intelpass"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        row_factory=dict_row,
        autocommit=False,
    )


def _chain_label(chain: str | None, address: str | None = None) -> str:
    c = (chain or "").strip().upper()
    if c:
        return c
    if str(address or "").startswith("0x"):
        return "ETH"
    return "BTC"


def _is_evm_chain(chain: str) -> bool:
    return _chain_label(chain) != "BTC"


def _format_balance(row) -> int:
    chain = _chain_label(row.get("chain"), row.get("address"))
    if chain == "BTC":
        return int(row.get("balance_sat") or 0)
    return int(row.get("balance_wei") or 0)


# ═══════════════════════════════════════════════════════════════════
# GET /data
# ═══════════════════════════════════════════════════════════════════

@router.get("/data")
def get_graph_data(
    min_usd: float = Query(2500),
    max_depth: int = Query(10),
    chain: str = Query(""),
):
    conn = None
    try:
        conn = get_conn_direct()
        cur = conn.cursor()
        chain = (chain or "").strip().upper()

        # ── Wallets ──────────────────────────────────────────
        wallet_where: list[str] = []
        wallet_params: list = []
        if chain:
            wallet_where.append("chain = %s")
            wallet_params.append(chain)
        if max_depth is not None and max_depth >= 0:
            wallet_where.append("depth <= %s")
            wallet_params.append(max_depth)

        wallet_query = """
            SELECT
                address, chain, category, is_seed, depth, source,
                balance_sat, balance_wei,
                total_received_sat, total_sent_sat,
                risk_score, created_at, updated_at,
                label, risk_tags, source_detail,
                COALESCE(is_contract, FALSE) AS is_contract,
                COALESCE(no_expand, FALSE) AS no_expand
            FROM tracked_wallets
        """
        if wallet_where:
            wallet_query += " WHERE " + " AND ".join(wallet_where)
        wallet_query += " ORDER BY COALESCE(updated_at, created_at) DESC NULLS LAST"

        cur.execute(wallet_query, tuple(wallet_params))
        wallet_rows = cur.fetchall()

        nodes = []
        address_set: set[tuple[str, str]] = set()

        for row in wallet_rows:
            address = row["address"]
            row_chain = _chain_label(row.get("chain"), address)
            address_set.add((address, row_chain))

            cat = row.get("category") or "traced"
            # Enrich category for display
            if row.get("is_contract") and cat in ("traced", "linked"):
                cat = "contract"
            if row.get("no_expand") and cat in ("traced", "linked", "service"):
                lbl_lower = (row.get("label") or "").lower()
                if "exchange" in lbl_lower or "cex" in lbl_lower:
                    cat = "exchange"
                elif "mixer" in lbl_lower:
                    cat = "mixer"
                elif "bridge" in lbl_lower:
                    cat = "bridge"

            nodes.append({
                "address": address,
                "chain": row_chain,
                "category": cat,
                "is_seed": bool(row.get("is_seed", False)),
                "depth": row.get("depth") or 0,
                "balance_sat": _format_balance(row),
                "total_received_sat": int(row.get("total_received_sat") or 0),
                "total_sent_sat": int(row.get("total_sent_sat") or 0),
                "risk_score": int(row.get("risk_score") or 0),
                "created_at": str(row.get("created_at") or ""),
                "updated_at": str(row.get("updated_at") or ""),
                "last_updated": str(row.get("updated_at") or row.get("created_at") or ""),
                "label": row.get("label") or f"{address[:8]}... ({row_chain})",
                "risk_tags": row.get("risk_tags") or [],
                "source": row.get("source") or "",
                "source_detail": row.get("source_detail") or "",
                "is_contract": bool(row.get("is_contract", False)),
                "no_expand": bool(row.get("no_expand", False)),
                "x": 0,
                "y": 0,
            })

        # ── Edges ────────────────────────────────────────────
        # EVM edges may have value_usd=0 initially, so also check
        # value_native * rough_price >= min_usd
        edge_where: list[str] = [
            "(value_usd >= %s OR (value_native * 3500) >= %s)"
        ]
        edge_params: list = [min_usd, min_usd]

        if chain:
            edge_where.append("chain = %s")
            edge_params.append(chain)

        edge_query = """
            SELECT
                from_address, to_address, chain,
                value_sat, value_native, value_usd,
                tx_count, block_time
            FROM tracked_edges
        """
        if edge_where:
            edge_query += " WHERE " + " AND ".join(edge_where)
        edge_query += " ORDER BY block_time DESC NULLS LAST"

        cur.execute(edge_query, tuple(edge_params))
        edge_rows = cur.fetchall()

        edges = []
        for row in edge_rows:
            from_address = row["from_address"]
            to_address = row["to_address"]
            row_chain = _chain_label(row.get("chain"), from_address)

            if address_set and (
                (from_address, row_chain) not in address_set
                or (to_address, row_chain) not in address_set
            ):
                continue

            raw_native = row.get("value_native")
            raw_sat = row.get("value_sat") or 0

            if _is_evm_chain(row_chain):
                if raw_native not in (None, ""):
                    total_value_sat = int(Decimal(str(raw_native)) * Decimal(10**18))
                else:
                    total_value_sat = int(raw_sat or 0)
            else:
                total_value_sat = int(raw_sat or 0)

            stored_usd = float(row.get("value_usd") or 0)
            if stored_usd < 1 and raw_native not in (None, ""):
                native_f = float(Decimal(str(raw_native)))
                if _is_evm_chain(row_chain):
                    stored_usd = native_f * 3500
                else:
                    stored_usd = native_f * 65000

            edges.append({
                "from_address": from_address,
                "to_address": to_address,
                "chain": row_chain,
                "total_value_sat": total_value_sat,
                "total_value_usd": stored_usd,
                "tx_count": int(row.get("tx_count") or 1),
                "last_tx_time": str(row.get("block_time") or ""),
            })

        return {"status": "success", "nodes": nodes, "edges": edges}

    except Exception as e:
        logger.exception("Graph Data Error")
        return {"status": "error", "message": str(e), "nodes": [], "edges": []}
    finally:
        if conn:
            conn.close()


# ═══════════════════════════════════════════════════════════════════
# GET /wallet/{address}
# ═══════════════════════════════════════════════════════════════════

@router.get("/wallet/{address}")
def get_wallet_detail(address: str, chain: str = ""):
    conn = None
    try:
        conn = get_conn_direct()
        cur = conn.cursor()
        chain = (chain or "").strip().upper()
        if chain:
            cur.execute(
                "SELECT * FROM tracked_wallets WHERE address=%s AND chain=%s",
                (address, chain),
            )
        else:
            cur.execute(
                "SELECT * FROM tracked_wallets WHERE address=%s "
                "ORDER BY updated_at DESC NULLS LAST LIMIT 1",
                (address,),
            )
        w = cur.fetchone()
        return {"status": "success", "data": w}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        if conn:
            conn.close()


# ═══════════════════════════════════════════════════════════════════
# POST /streams/webhook  (Moralis Streams)
# ═══════════════════════════════════════════════════════════════════

def _verify_moralis_signature(body: bytes, signature: str | None) -> bool:
    secret = os.getenv("MORALIS_STREAMS_SECRET", "").strip()
    if not secret:
        return True
    if not signature:
        return False
    expected = "0x" + hashlib.sha3_256(body + secret.encode("utf-8")).hexdigest()
    return expected.lower() == signature.lower()


@router.post("/streams/webhook")
async def moralis_streams_webhook(
    request: Request,
    x_signature: str | None = Header(default=None),
):
    raw_body = await request.body()
    if not _verify_moralis_signature(raw_body, x_signature):
        return {"status": "error", "message": "invalid signature"}

    payload = json.loads(raw_body.decode("utf-8") or "{}")
    if not payload:
        return {"status": "ok", "processed": 0}

    tag = payload.get("tag") or ""
    chain = _chain_label(payload.get("chainId") or payload.get("chain"))
    txs = payload.get("txs") or []
    internal_txs = payload.get("internalTxs") or []

    conn = None
    processed = 0
    try:
        conn = get_conn_direct()
        cur = conn.cursor()

        dedupe_key = hashlib.sha256(raw_body).hexdigest()
        cur.execute(
            """
            INSERT INTO moralis_webhook_events (event_hash, tag, chain)
            VALUES (%s, %s, %s)
            ON CONFLICT (event_hash) DO NOTHING RETURNING event_hash
            """,
            (dedupe_key, tag, chain),
        )
        inserted = cur.fetchone()
        if not inserted:
            conn.commit()
            return {"status": "ok", "processed": 0, "duplicate": True}

        # Import from same package
        from analyzer.tracer import insert_edge, queue_wallet

        for tx in txs:
            from_addr = (tx.get("fromAddress") or "").lower()
            to_addr = (tx.get("toAddress") or "").lower()
            value_wei = int(tx.get("value") or 0)
            ts = payload.get("block", {}).get("timestamp")
            if from_addr and to_addr and value_wei > 0:
                for addr in (from_addr, to_addr):
                    cur.execute(
                        """
                        INSERT INTO tracked_wallets
                            (address, chain, category, is_seed, depth, source, label,
                             is_contract, no_expand, created_at, updated_at)
                        VALUES (%s, %s, 'linked', FALSE, 1, 'streams', %s,
                                FALSE, FALSE, NOW(), NOW())
                        ON CONFLICT (address, chain) DO UPDATE SET
                            updated_at = NOW(),
                            source = CASE
                                WHEN tracked_wallets.source = 'streams' THEN 'streams'
                                ELSE tracked_wallets.source
                            END
                        """,
                        (addr, chain, f"{addr[:8]}... ({chain})"),
                    )

                insert_edge(
                    cur,
                    from_addr=from_addr, to_addr=to_addr, chain=chain,
                    value_sat=0,
                    value_native=Decimal(value_wei) / Decimal(10**18),
                    value_usd=0, tx_count=1, ts=ts,
                )
                queue_wallet(cur, from_addr, chain, priority=2)
                queue_wallet(cur, to_addr, chain, priority=2)
                processed += 1

        for tx in internal_txs:
            from_addr = (tx.get("from") or tx.get("fromAddress") or "").lower()
            to_addr = (tx.get("to") or tx.get("toAddress") or "").lower()
            value_wei = int(tx.get("value") or 0)
            ts = payload.get("block", {}).get("timestamp")
            if from_addr and to_addr and value_wei > 0:
                insert_edge(
                    cur,
                    from_addr=from_addr, to_addr=to_addr, chain=chain,
                    value_sat=0,
                    value_native=Decimal(value_wei) / Decimal(10**18),
                    value_usd=0, tx_count=1, ts=ts,
                )
                processed += 1

        conn.commit()
        event_id = payload.get("confirmed", "")
        return {"status": "ok", "processed": processed, "event": event_id}

    except Exception as e:
        if conn:
            conn.rollback()
        logger.exception("Streams webhook error")
        return {"status": "error", "message": str(e)}
    finally:
        if conn:
            conn.close()
