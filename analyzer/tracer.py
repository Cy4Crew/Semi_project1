"""tracer.py – BFS wallet tracer with EVM smart-filtering + multichain discovery.

Lives in analyzer/ package.  Imports:
  - from app.core.db import get_conn          (absolute – app package)
  - from .mempool_client import client         (relative – same package)
  - from .etherscan_client import client       (relative – same package)
  - from .evm_filter_config import ...         (relative – same package)

v3: multichain auto-discovery via Moralis get_chain_activity()
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.db import get_conn
from .mempool_client import client as btc_client
from .etherscan_client import client as moralis_client

logger = logging.getLogger("tracer")

# ---------------------------------------------------------------------------
# Config (graceful fallback if config module missing)
# ---------------------------------------------------------------------------
try:
    from .evm_filter_config import (
        EVM_MIN_NATIVE_VALUE, EVM_MIN_NATIVE_DEFAULT,
        EVM_MIN_CUMULATIVE_NATIVE_ETH, EVM_MIN_CUMULATIVE_USD,
        EVM_MIN_REPEAT_COUNT, EVM_HUB_MIN_TRACED_LINKS,
        EVM_MAX_COUNTERPARTIES_FOR_EXPANSION, EVM_MAX_DEPTH,
        DEPTH_POLICY, DEPTH_HARD_CUTOFF,
        SCORE_LARGE_VALUE, SCORE_REPEAT_CONTACT, SCORE_CUMULATIVE_BIG,
        SCORE_RISK_TAG, SCORE_CONTRACT, SCORE_SERVICE_LABEL,
        SCORE_HIGH_FANOUT, SCORE_THRESHOLD,
        EVM_MAX_NEW_NEIGHBORS_PER_WALLET,
        SERVICE_KEYWORDS, RISK_KEYWORDS,
    )
except ImportError:
    logger.warning("evm_filter_config not found – using built-in defaults")
    EVM_MIN_NATIVE_VALUE = {"ETH": Decimal("1")}
    EVM_MIN_NATIVE_DEFAULT = Decimal("1")
    EVM_MIN_CUMULATIVE_NATIVE_ETH = Decimal("2")
    EVM_MIN_CUMULATIVE_USD = 3000.0
    EVM_MIN_REPEAT_COUNT = 2
    EVM_HUB_MIN_TRACED_LINKS = 3
    EVM_MAX_COUNTERPARTIES_FOR_EXPANSION = 15
    EVM_MAX_DEPTH = 5
    DEPTH_POLICY = {
        0: {"native_mult": Decimal("1"), "min_usd": 0, "require_repeat": False},
        1: {"native_mult": Decimal("2"), "min_usd": 5000, "require_repeat": False},
        2: {"native_mult": Decimal("3"), "min_usd": 8000, "require_repeat": True},
    }
    DEPTH_HARD_CUTOFF = 3
    SCORE_LARGE_VALUE = 3; SCORE_REPEAT_CONTACT = 2; SCORE_CUMULATIVE_BIG = 2
    SCORE_RISK_TAG = 3; SCORE_CONTRACT = -3; SCORE_SERVICE_LABEL = -2
    SCORE_HIGH_FANOUT = -3; SCORE_THRESHOLD = 2
    EVM_MAX_NEW_NEIGHBORS_PER_WALLET = 8
    SERVICE_KEYWORDS = {"exchange","bridge","mixer","router","swap","pool",
                        "staking","vault","dex","cex","relay","aggregator"}
    RISK_KEYWORDS = {"ransomware","cashout","laundering","mixer","scam",
                     "phishing","theft","exploit","hack","fraud"}


# ═══════════════════════════════════════════════════════════════════
# Edge / queue helpers
# ═══════════════════════════════════════════════════════════════════

def insert_edge(
    cur,
    from_addr: str,
    to_addr: str,
    chain: str,
    value_sat: int | Decimal = 0,
    value_native: Decimal | None = None,
    value_usd: float | Decimal = 0,
    tx_count: int = 1,
    ts: Any = None,
) -> None:
    """Upsert an aggregated edge (1 row per from/to/chain)."""
    if not from_addr or not to_addr:
        return
    from_addr = str(from_addr).lower().strip()
    to_addr = str(to_addr).lower().strip()
    if from_addr == to_addr:
        return
    _NULL_ADDRS = ("", "0x", "0x0000000000000000000000000000000000000000")
    if from_addr in _NULL_ADDRS or to_addr in _NULL_ADDRS:
        return

    try:
        value_sat = int(Decimal(str(value_sat or 0)))
    except (InvalidOperation, ValueError):
        value_sat = 0
    try:
        value_native = Decimal(str(value_native)) if value_native is not None else Decimal(0)
    except (InvalidOperation, ValueError):
        value_native = Decimal(0)
    try:
        value_usd = float(Decimal(str(value_usd or 0)))
    except (InvalidOperation, ValueError):
        value_usd = 0.0

    cur.execute(
        """
        INSERT INTO tracked_edges
            (from_address, to_address, chain, value_sat, value_native, value_usd, tx_count, block_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (from_address, to_address, chain) DO UPDATE SET
            value_sat    = tracked_edges.value_sat    + EXCLUDED.value_sat,
            value_native = tracked_edges.value_native + EXCLUDED.value_native,
            value_usd    = tracked_edges.value_usd    + EXCLUDED.value_usd,
            tx_count     = tracked_edges.tx_count     + EXCLUDED.tx_count,
            block_time   = GREATEST(tracked_edges.block_time, EXCLUDED.block_time)
        """,
        (from_addr, to_addr, chain, value_sat, value_native, value_usd, tx_count, ts),
    )


def queue_wallet(cur, address: str, chain: str, priority: int = 1) -> None:
    """Insert or bump a wallet in trace_queue."""
    if not address:
        return
    cur.execute(
        """
        INSERT INTO trace_queue (address, chain, priority, processed)
        VALUES (%s, %s, %s, FALSE)
        ON CONFLICT (address, chain) DO UPDATE SET
            processed = FALSE,
            priority  = GREATEST(trace_queue.priority, EXCLUDED.priority)
        """,
        (address.lower().strip(), chain, priority),
    )


def mark_processed(cur, address: str, chain: str) -> None:
    cur.execute(
        "UPDATE trace_queue SET processed = TRUE WHERE address = %s AND chain = %s",
        (address.lower().strip(), chain),
    )


# ═══════════════════════════════════════════════════════════════════
# ★ Multichain auto-discovery
# ═══════════════════════════════════════════════════════════════════

def discover_and_register_chains(cur, address: str, source_chain: str) -> list[str]:
    """Query Moralis for all chains this EVM address is active on.

    For each discovered chain (other than source_chain and BTC):
      - Register in tracked_wallets as seed, depth 0
      - Enqueue in trace_queue

    Returns list of all active chains (including source_chain).
    """
    if source_chain == "BTC":
        return ["BTC"]

    address = address.lower().strip()
    try:
        active_chains = moralis_client.get_chain_activity(address)
    except Exception:
        logger.exception("[Multichain] get_chain_activity failed for %s", address)
        return [source_chain]

    if not active_chains:
        return [source_chain]

    # Ensure source chain is included
    if source_chain not in active_chains:
        active_chains.insert(0, source_chain)

    registered: list[str] = []
    for chain in active_chains:
        if chain == "BTC":
            continue  # EVM address can't be BTC

        # Copy seed wallet metadata from source chain row
        cur.execute(
            "SELECT category, source, source_detail, channel_name, risk_tags, risk_score "
            "FROM tracked_wallets WHERE address = %s AND chain = %s",
            (address, source_chain),
        )
        src_row = cur.fetchone()

        category = (src_row["category"] if src_row else "seller") or "seller"
        source = (src_row["source"] if src_row else "trace") or "trace"
        source_detail = (src_row["source_detail"] if src_row else "") or ""
        channel_name = (src_row["channel_name"] if src_row else "") or ""
        risk_tags = src_row["risk_tags"] if src_row and src_row.get("risk_tags") else "[]"
        risk_score = int(src_row["risk_score"]) if src_row and src_row.get("risk_score") else 0

        import json
        risk_tags_str = risk_tags if isinstance(risk_tags, str) else json.dumps(risk_tags)

        cur.execute(
            """
            INSERT INTO tracked_wallets
                (address, chain, category, is_seed, depth, source, source_detail,
                 channel_name, risk_tags, risk_score, label,
                 is_contract, no_expand, created_at, updated_at)
            VALUES (%s, %s, %s, TRUE, 0, %s, %s, %s, %s, %s, %s,
                    FALSE, FALSE, NOW(), NOW())
            ON CONFLICT (address, chain) DO UPDATE SET
                updated_at = NOW(),
                is_seed    = TRUE,
                risk_score = GREATEST(tracked_wallets.risk_score, EXCLUDED.risk_score)
            """,
            (address, chain, category, source, source_detail, channel_name,
             risk_tags_str, risk_score, f"{address[:8]}... ({chain})"),
        )

        queue_wallet(cur, address, chain, priority=2)
        registered.append(chain)

    if registered:
        logger.info("[Multichain] %s active on: %s", address[:10], ", ".join(registered))

    return registered


# ═══════════════════════════════════════════════════════════════════
# EVM scoring helpers
# ═══════════════════════════════════════════════════════════════════

def _is_service_label(tx: dict) -> bool:
    blob = " ".join([
        str(tx.get("category") or ""),
        str(tx.get("label") or ""),
        str(tx.get("source_detail") or ""),
        str(tx.get("to_address_label") or ""),
        str(tx.get("from_address_label") or ""),
    ]).lower()
    return any(kw in blob for kw in SERVICE_KEYWORDS)


def _is_contract_heuristic(tx: dict) -> bool:
    inp = str(tx.get("input") or tx.get("data") or "")
    if inp in ("", "0x", "deprecated"):
        return False
    return len(inp) > 10


def _has_risk_tags(tags) -> bool:
    if not tags:
        return False
    blob = str(tags).lower() if isinstance(tags, str) else " ".join(str(t) for t in tags).lower()
    return any(kw in blob for kw in RISK_KEYWORDS)


def _count_unique_counterparties(txs: list[dict], address: str) -> int:
    peers: set[str] = set()
    addr_low = address.lower()
    for tx in txs:
        f = (tx.get("from_address") or "").lower()
        t = (tx.get("to_address") or "").lower()
        if f and f != addr_low:
            peers.add(f)
        if t and t != addr_low:
            peers.add(t)
    return len(peers)


def _fetch_and_update_wallet_info(cur, address: str, chain: str) -> None:
    """Fetch balance from Moralis and update tracked_wallets."""
    try:
        info = moralis_client.get_address_info(address, chain=chain)
        balance_wei = info.get("balance_wei", 0)

        # Get tx count from a small history fetch
        try:
            hist = moralis_client.get_wallet_history(address, chain=chain, limit=1)
            # Moralis returns cursor-based pagination; use 'total' if available
            tx_count = hist.get("total", 0) or len(hist.get("result", []))
        except Exception:
            tx_count = 0

        cur.execute(
            """
            UPDATE tracked_wallets SET
                balance_wei = %s,
                updated_at  = NOW()
            WHERE address = %s AND chain = %s
            """,
            (balance_wei, address, chain),
        )
        logger.debug("[Balance] %s/%s: %s wei, %d txs", address[:10], chain, balance_wei, tx_count)
    except Exception:
        logger.debug("[Balance] fetch failed for %s/%s", address[:10], chain)


# ═══════════════════════════════════════════════════════════════════
# Main trace entry point
# ═══════════════════════════════════════════════════════════════════

def trace_wallet(address: str, chain: str) -> None:
    """Dispatch to BTC or EVM tracer.  Opens its own DB connection."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            # ★ Multichain discovery for seed wallets
            if chain != "BTC":
                cur.execute(
                    "SELECT is_seed, depth FROM tracked_wallets WHERE address = %s AND chain = %s",
                    (address.lower().strip(), chain),
                )
                seed_row = cur.fetchone()
                if seed_row and seed_row.get("is_seed") and (seed_row.get("depth") or 0) == 0:
                    discover_and_register_chains(cur, address, chain)

            # ★ Fetch balance for the wallet being traced
            if chain != "BTC":
                _fetch_and_update_wallet_info(cur, address.lower().strip(), chain)

            if chain == "BTC":
                _trace_btc(cur, address)
            else:
                _trace_evm(cur, address, chain)
            mark_processed(cur, address, chain)
        conn.commit()


# ── BTC ──────────────────────────────────────────────────────────

def _trace_btc(cur, address: str) -> None:
    try:
        txs = btc_client.get_address_txs(address, 20)
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
        logger.exception("[Tracer] BTC trace failed for %s", address)


# ── EVM (smart-filtering) ───────────────────────────────────────

def _trace_evm(cur, address: str, chain: str) -> None:
    """Score-based EVM tracing."""
    address = address.lower().strip()

    cur.execute(
        "SELECT depth, is_seed, no_expand FROM tracked_wallets WHERE address = %s AND chain = %s",
        (address, chain),
    )
    row = cur.fetchone()
    if not row:
        logger.warning("[Tracer] wallet not in tracked_wallets: %s/%s", address, chain)
        return

    current_depth = int(row["depth"] if row["depth"] is not None else 0)
    is_seed = bool(row.get("is_seed"))
    no_expand = bool(row.get("no_expand"))

    if no_expand and not is_seed:
        logger.info("[Tracer] Skipping expansion (no_expand) %s/%s", address, chain)
        return

    next_depth = current_depth + 1
    if next_depth > EVM_MAX_DEPTH:
        logger.info("[Tracer] Max depth reached %s/%s d=%d", address, chain, current_depth)
        return

    try:
        data = moralis_client.get_wallet_history(address, chain=chain, limit=50)
        txs = data.get("result", []) if isinstance(data, dict) else []
    except Exception:
        logger.exception("[Tracer] Moralis fetch failed %s/%s", address, chain)
        return

    if not txs:
        logger.info("[Tracer] No txs %s/%s", address, chain)
        return

    unique_cp = _count_unique_counterparties(txs, address)
    if unique_cp > EVM_MAX_COUNTERPARTIES_FOR_EXPANSION:
        logger.info("[Tracer] %s/%s fanout=%d → no_expand", address, chain, unique_cp)
        cur.execute(
            "UPDATE tracked_wallets SET no_expand = TRUE WHERE address = %s AND chain = %s",
            (address, chain),
        )
        _store_evm_edges_only(cur, txs, address, chain)
        return

    # Aggregate per counterparty
    peers: dict[str, dict] = {}

    for tx in txs:
        from_addr = (tx.get("from_address") or "").lower().strip()
        to_addr = (tx.get("to_address") or "").lower().strip()
        if not from_addr or not to_addr:
            continue

        peer = to_addr if from_addr == address else (from_addr if to_addr == address else None)
        if not peer or peer == address:
            continue
        if peer in ("", "0x", "0x0000000000000000000000000000000000000000"):
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

        is_contract = _is_contract_heuristic(tx)
        is_service = _is_service_label(tx)

        if peer not in peers:
            peers[peer] = {
                "total_native": Decimal(0), "total_usd": 0.0,
                "tx_count": 0, "is_contract_suspect": False,
                "is_service": False, "latest_ts": None,
                "value_wei_list": [],
            }
        p = peers[peer]
        p["total_native"] += value_native
        p["tx_count"] += 1
        p["value_wei_list"].append(value_wei)
        if is_contract:
            p["is_contract_suspect"] = True
        if is_service:
            p["is_service"] = True
        if ts and (p["latest_ts"] is None or ts > p["latest_ts"]):
            p["latest_ts"] = ts

    # Hub check
    peer_addrs = list(peers.keys())
    hub_counts: dict[str, int] = {}
    if peer_addrs:
        ph = ",".join(["%s"] * len(peer_addrs))
        cur.execute(
            f"""
            SELECT sub.peer, COUNT(DISTINCT sub.other) AS link_count
            FROM (
                SELECT to_address AS peer, from_address AS other
                FROM tracked_edges WHERE to_address IN ({ph}) AND chain = %s
                UNION ALL
                SELECT from_address AS peer, to_address AS other
                FROM tracked_edges WHERE from_address IN ({ph}) AND chain = %s
            ) sub
            WHERE sub.other IN (SELECT address FROM tracked_wallets WHERE chain = %s)
            GROUP BY sub.peer
            """,
            (*peer_addrs, chain, *peer_addrs, chain, chain),
        )
        for r in cur.fetchall():
            hub_counts[r["peer"]] = int(r["link_count"])

    # Risk tags from DB
    peer_risk: dict[str, bool] = {}
    if peer_addrs:
        ph = ",".join(["%s"] * len(peer_addrs))
        cur.execute(
            f"SELECT address, risk_tags FROM tracked_wallets WHERE address IN ({ph}) AND chain = %s",
            (*peer_addrs, chain),
        )
        for r in cur.fetchall():
            peer_risk[r["address"]] = _has_risk_tags(r.get("risk_tags"))

    # Score
    chain_min_native = EVM_MIN_NATIVE_VALUE.get(chain, EVM_MIN_NATIVE_DEFAULT)
    depth_pol = DEPTH_POLICY.get(current_depth)

    scored: list[tuple[str, int, dict]] = []

    for peer, info in peers.items():
        score = 0

        if info["total_native"] >= chain_min_native:
            score += SCORE_LARGE_VALUE
        if info["tx_count"] >= EVM_MIN_REPEAT_COUNT:
            score += SCORE_REPEAT_CONTACT
        if info["total_native"] >= EVM_MIN_CUMULATIVE_NATIVE_ETH:
            score += SCORE_CUMULATIVE_BIG
        if info["total_usd"] >= EVM_MIN_CUMULATIVE_USD:
            score += SCORE_CUMULATIVE_BIG
        if hub_counts.get(peer, 0) >= EVM_HUB_MIN_TRACED_LINKS:
            score += SCORE_LARGE_VALUE
        if peer_risk.get(peer, False):
            score += SCORE_RISK_TAG

        if info["is_contract_suspect"]:
            score += SCORE_CONTRACT
        if info["is_service"]:
            score += SCORE_SERVICE_LABEL

        if depth_pol:
            adj_min = chain_min_native * depth_pol["native_mult"]
            if info["total_native"] < adj_min:
                score -= 1
            if depth_pol["require_repeat"] and info["tx_count"] < EVM_MIN_REPEAT_COUNT:
                score -= 2

        if current_depth >= DEPTH_HARD_CUTOFF:
            score -= 3

        scored.append((peer, score, info))

    scored.sort(key=lambda x: -x[1])

    # Store ALL edges
    for peer, _score, info in scored:
        insert_edge(
            cur,
            from_addr=address, to_addr=peer, chain=chain,
            value_sat=0,
            value_native=info["total_native"],
            value_usd=info["total_usd"],
            tx_count=info["tx_count"],
            ts=info["latest_ts"],
        )

    # Enqueue passing peers
    added = 0
    for peer, score, info in scored:
        if added >= EVM_MAX_NEW_NEIGHBORS_PER_WALLET:
            break
        if score < SCORE_THRESHOLD:
            continue

        category = "traced"
        no_exp = False
        if info["is_contract_suspect"]:
            category = "contract"
            no_exp = True
        if info["is_service"]:
            category = "service"
            no_exp = True

        label = f"{peer[:8]}... ({chain})"

        cur.execute(
            """
            INSERT INTO tracked_wallets
                (address, chain, category, is_seed, depth, source, label,
                 is_contract, no_expand, created_at, updated_at)
            VALUES (%s, %s, %s, FALSE, %s, 'trace', %s, %s, %s, NOW(), NOW())
            ON CONFLICT (address, chain) DO UPDATE SET
                updated_at  = NOW(),
                depth       = LEAST(tracked_wallets.depth, EXCLUDED.depth),
                is_contract = tracked_wallets.is_contract OR EXCLUDED.is_contract,
                no_expand   = tracked_wallets.no_expand OR EXCLUDED.no_expand
            """,
            (peer, chain, category, next_depth, label,
             info["is_contract_suspect"], no_exp),
        )

        # ★ Fetch balance for newly registered peer
        _fetch_and_update_wallet_info(cur, peer, chain)

        if not no_exp:
            queue_wallet(cur, peer, chain, priority=max(1, score))

        added += 1

    logger.info(
        "[Tracer] EVM %s/%s d=%d → %d peers scored, %d enqueued",
        address, chain, current_depth, len(scored), added,
    )


def _store_evm_edges_only(cur, txs: list[dict], address: str, chain: str) -> None:
    """Store edges AND register counterparty nodes (as no_expand) for graph display."""
    address = address.lower().strip()
    seen_peers: set[str] = set()
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
        insert_edge(cur, from_addr=from_addr, to_addr=to_addr, chain=chain,
                    value_sat=0, value_native=value_native, value_usd=0, tx_count=1, ts=ts)

        # Register counterparty as node (no_expand) so it shows in graph
        peer = to_addr if from_addr == address else from_addr
        if peer and peer != address and peer not in seen_peers:
            seen_peers.add(peer)
            cur.execute(
                """
                INSERT INTO tracked_wallets
                    (address, chain, category, is_seed, depth, source, label,
                     is_contract, no_expand, created_at, updated_at)
                VALUES (%s, %s, 'linked', FALSE, 1, 'trace', %s,
                        FALSE, TRUE, NOW(), NOW())
                ON CONFLICT (address, chain) DO UPDATE SET
                    updated_at = NOW()
                """,
                (peer, chain, f"{peer[:8]}... ({chain})"),
            )
            # ★ Fetch balance (limit to first 15 peers to avoid API overload)
            if len(seen_peers) <= 15:
                _fetch_and_update_wallet_info(cur, peer, chain)
    if seen_peers:
        logger.info("[Tracer] edges-only %s/%s: %d edges, %d peer nodes registered",
                    address[:10], chain, len(txs), len(seen_peers))
