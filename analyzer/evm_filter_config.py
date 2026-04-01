"""evm_filter_config.py – tunable constants for EVM smart-filtering.

Every value can be overridden by an environment variable of the same name.
Place this file in the analyzer/ package alongside tracer.py / worker.py.
"""
from __future__ import annotations

import os
from decimal import Decimal


def _env_decimal(name: str, default: str) -> Decimal:
    return Decimal(os.getenv(name, default))


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


# ── [1A] 큰 금액 기준 (native, per chain) ───────────────────────
EVM_MIN_NATIVE_VALUE: dict[str, Decimal] = {
    "ETH":       _env_decimal("EVM_MIN_NATIVE_ETH", "1"),
    "BSC":       _env_decimal("EVM_MIN_NATIVE_BSC", "3"),
    "POLYGON":   _env_decimal("EVM_MIN_NATIVE_POLYGON", "500"),
    "ARBITRUM":  _env_decimal("EVM_MIN_NATIVE_ARBITRUM", "1"),
    "BASE":      _env_decimal("EVM_MIN_NATIVE_BASE", "1"),
    "OPTIMISM":  _env_decimal("EVM_MIN_NATIVE_OPTIMISM", "1"),
    "AVALANCHE": _env_decimal("EVM_MIN_NATIVE_AVALANCHE", "30"),
}
EVM_MIN_NATIVE_DEFAULT = _env_decimal("EVM_MIN_NATIVE_DEFAULT", "1")

# ── [1C] 누적 금액 기준 ─────────────────────────────────────────
EVM_MIN_CUMULATIVE_NATIVE_ETH = _env_decimal("EVM_MIN_CUMULATIVE_NATIVE_ETH", "2")
EVM_MIN_CUMULATIVE_USD = _env_float("EVM_MIN_CUMULATIVE_USD", 3000.0)

# ── [1B] 반복 접촉 기준 ─────────────────────────────────────────
EVM_MIN_REPEAT_COUNT = _env_int("EVM_MIN_REPEAT_COUNT", 2)

# ── [1D] 허브 기준 ──────────────────────────────────────────────
EVM_HUB_MIN_TRACED_LINKS = _env_int("EVM_HUB_MIN_TRACED_LINKS", 3)

# ── [2C] 너무 많은 counterparty 제한 ────────────────────────────
EVM_MAX_COUNTERPARTIES_FOR_EXPANSION = _env_int("EVM_MAX_COUNTERPARTIES_FOR_EXPANSION", 15)

# ── [4] depth별 임계값 ──────────────────────────────────────────
EVM_MAX_DEPTH = _env_int("EVM_MAX_DEPTH", 5)

# depth -> (native_mult, min_usd, require_repeat)
DEPTH_POLICY: dict[int, dict] = {
    0: {"native_mult": Decimal("1"),  "min_usd": 0,    "require_repeat": False},
    1: {"native_mult": Decimal("2"),  "min_usd": 5000, "require_repeat": False},
    2: {"native_mult": Decimal("3"),  "min_usd": 8000, "require_repeat": True},
}
DEPTH_HARD_CUTOFF = _env_int("EVM_DEPTH_HARD_CUTOFF", 3)

# ── [7] 점수 가중치 ─────────────────────────────────────────────
SCORE_LARGE_VALUE     =  3
SCORE_REPEAT_CONTACT  =  2
SCORE_CUMULATIVE_BIG  =  2
SCORE_RISK_TAG        =  3
SCORE_CONTRACT        = -3
SCORE_SERVICE_LABEL   = -2
SCORE_HIGH_FANOUT     = -3
SCORE_THRESHOLD       = _env_int("EVM_SCORE_THRESHOLD", 2)

# ── [7] worker 제한 ─────────────────────────────────────────────
EVM_MAX_NEW_NEIGHBORS_PER_WALLET = _env_int("EVM_MAX_NEW_NEIGHBORS_PER_WALLET", 8)
POLL_BATCH_SIZE  = _env_int("POLL_BATCH_SIZE", 20)
QUEUE_BATCH_SIZE = _env_int("QUEUE_BATCH_SIZE", 10)
WORKER_SLEEP_SEC = _env_int("WORKER_SLEEP_SEC", 600)

# ── 서비스 라벨 키워드 (소문자) ──────────────────────────────────
SERVICE_KEYWORDS: set[str] = {
    "exchange", "bridge", "mixer", "router", "swap", "pool",
    "staking", "vault", "dex", "cex", "relay", "aggregator",
}

# ── 위험 태그 키워드 ─────────────────────────────────────────────
RISK_KEYWORDS: set[str] = {
    "ransomware", "cashout", "laundering", "mixer", "scam",
    "phishing", "theft", "exploit", "hack", "fraud",
}
