"""Moralis-backed multi-chain wallet client.

Kept in the original filename to avoid changing existing imports.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import requests

logger = logging.getLogger("moralis")


CHAIN_ALIASES = {
    "ETH": "eth",
    "0X1": "eth",
    "BSC": "bsc",
    "0X38": "bsc",
    "POLYGON": "polygon",
    "0X89": "polygon",
    "ARBITRUM": "arbitrum",
    "0XA4B1": "arbitrum",
    "BASE": "base",
    "0X2105": "base",
    "OPTIMISM": "optimism",
    "0XA": "optimism",
    "AVALANCHE": "avalanche",
    "0XA86A": "avalanche",
    "GNOSIS": "gnosis",
    "0X64": "gnosis",
    "LINEA": "linea",
    "0XE708": "linea",
    "RONIN": "ronin",
    "0X7E4": "ronin",
    "CRONOS": "cronos",
    "0X19": "cronos",
    "FANTOM": "fantom",
    "0XFA": "fantom",
    "SEI": "sei",
    "0X531": "sei",
    "MONAD": "monad",
    "0X8F": "monad",
}

DISPLAY_CHAIN = {
    "eth": "ETH",
    "bsc": "BSC",
    "polygon": "POLYGON",
    "arbitrum": "ARBITRUM",
    "base": "BASE",
    "optimism": "OPTIMISM",
    "avalanche": "AVALANCHE",
    "gnosis": "GNOSIS",
    "linea": "LINEA",
    "ronin": "RONIN",
    "cronos": "CRONOS",
    "fantom": "FANTOM",
    "sei": "SEI",
    "monad": "MONAD",
}

STREAM_CHAIN_IDS = {
    "ETH": "0x1",
    "BSC": "0x38",
    "POLYGON": "0x89",
    "ARBITRUM": "0xa4b1",
    "BASE": "0x2105",
    "OPTIMISM": "0xa",
    "AVALANCHE": "0xa86a",
    "GNOSIS": "0x64",
    "LINEA": "0xe708",
    "RONIN": "0x7e4",
    "CRONOS": "0x19",
    "FANTOM": "0xfa",
    "SEI": "0x531",
    "MONAD": "0x8f",
}


class MoralisClient:
    def __init__(self, api_key: str = "", base_url: str = "https://deep-index.moralis.io/api/v2.2"):
        self.base = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("MORALIS_API_KEY", "")
        self.streams_base = os.environ.get("MORALIS_STREAMS_BASE_URL", "https://api.moralis-streams.com").rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "DarkwebMonitor/1.0",
                "Accept": "application/json",
            }
        )
        if self.api_key:
            self.session.headers["X-API-Key"] = self.api_key
            self.session.headers["x-api-key"] = self.api_key
        self._last = 0.0

    def _sleep_rate_limit(self) -> None:
        elapsed = time.time() - self._last
        delay = 0.25
        if elapsed < delay:
            time.sleep(delay - elapsed)

    def _request(self, method: str, url: str, *, params: dict[str, Any] | None = None, json_body: Any = None) -> Any:
        if not self.api_key:
            raise RuntimeError("MORALIS_API_KEY is not set")
        for attempt in range(1, 5):
            self._sleep_rate_limit()
            try:
                self._last = time.time()
                resp = self.session.request(method, url, params=params, json=json_body, timeout=20)
                if resp.status_code in (408, 425, 429, 500, 502, 503, 504):
                    if attempt == 4:
                        resp.raise_for_status()
                    time.sleep(1.7 ** attempt)
                    continue
                resp.raise_for_status()
                if not resp.text.strip():
                    return {}
                return resp.json()
            except requests.RequestException:
                if attempt == 4:
                    raise
                time.sleep(1.7 ** attempt)
        return {}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", f"{self.base}{path}", params=params)

    def _post_streams(self, path: str, body: dict[str, Any]) -> Any:
        return self._request("POST", f"{self.streams_base}{path}", json_body=body)

    def _put_streams(self, path: str, body: dict[str, Any]) -> Any:
        return self._request("PUT", f"{self.streams_base}{path}", json_body=body)

    def _get_streams(self, path: str) -> Any:
        return self._request("GET", f"{self.streams_base}{path}")

    @staticmethod
    def normalize_chain(chain: str | None) -> str:
        if not chain:
            return "ETH"
        c = str(chain).strip().upper()
        if c in CHAIN_ALIASES:
            return DISPLAY_CHAIN[CHAIN_ALIASES[c]]
        return c

    @staticmethod
    def moralis_chain(chain: str | None) -> str:
        c = str(chain or "ETH").strip().upper()
        return CHAIN_ALIASES.get(c, c.lower())

    def get_chain_activity(self, address: str) -> list[str]:
        data = self._get(f"/wallets/{address}/chains")
        chains: list[str] = []
        for item in data.get("active_chains", []) or data.get("result", []) or []:
            chain = item.get("chain") or item.get("chain_id") or item.get("name")
            if chain:
                chains.append(self.normalize_chain(chain))
        # free-tier-safe fallback
        if not chains:
            chains.append("ETH")
        seen = set()
        out = []
        for c in chains:
            if c not in seen:
                seen.add(c)
                out.append(c)
        return out

    def get_wallet_history(self, address: str, chain: str = "ETH", limit: int = 100, cursor: str | None = None, include_internal_transactions: bool = True) -> dict[str, Any]:
        params: dict[str, Any] = {
            "chain": self.moralis_chain(chain),
            "order": "DESC",
            "limit": limit,
            "include_internal_transactions": str(bool(include_internal_transactions)).lower(),
        }
        if cursor:
            params["cursor"] = cursor
        return self._get(f"/wallets/{address}/history", params=params)

    def get_normal_txs(self, address: str, page: int = 1, offset: int = 50, sort: str = "desc", chain: str = "ETH") -> list[dict[str, Any]]:
        # compatibility shim for existing imports
        data = self.get_wallet_history(address, chain=chain, limit=offset, include_internal_transactions=False)
        return data.get("result", []) if isinstance(data, dict) else []

    def get_address_info(self, address: str, chain: str = "ETH") -> dict[str, Any]:
        try:
            data = self._get(f"/{address}/balance", params={"chain": self.moralis_chain(chain)})
        except Exception:
            data = {}
        balance_raw = data.get("balance") or data.get("wei") or "0"
        try:
            balance_wei = int(str(balance_raw))
        except Exception:
            balance_wei = 0
        return {
            "balance_wei": balance_wei,
            "balance_eth": balance_wei / 1e18,
            "tx_count": 0,
            "total_received_wei": 0,
            "total_sent_wei": 0,
        }

    def get_multiple_supported_chains(self, address: str) -> list[str]:
        return self.get_chain_activity(address)

    def list_streams(self) -> list[dict[str, Any]]:
        data = self._get_streams("/streams/evm")
        if isinstance(data, list):
            return data
        return data.get("result", []) or data.get("streams", []) or []

    def create_stream(self, chain_ids: list[str], webhook_url: str, description: str = "wallet-tracker", tag: str = "wallet-tracker") -> dict[str, Any]:
        body = {
            "chainIds": chain_ids,
            "webhookUrl": webhook_url,
            "description": description,
            "tag": tag,
            "allAddresses": False,
            "includeNativeTxs": True,
            "includeInternalTxs": True,
            "includeContractLogs": False,
            "includeAllTxLogs": False,
        }
        return self._put_streams("/streams/evm", body)

    def add_address_to_stream(self, stream_id: str, address: str) -> dict[str, Any]:
        return self._post_streams(f"/streams/evm/{stream_id}/address", {"address": address})


client = MoralisClient(api_key=os.environ.get("MORALIS_API_KEY", ""))
