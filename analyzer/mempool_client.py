"""Mempool API client — Bitcoin only, rate-limited"""
from __future__ import annotations
import time, logging, requests
from typing import Any

logger = logging.getLogger("mempool")
BASE_URL = "https://mempool.space/api"

class MempoolClient:
    def __init__(self, base_url=BASE_URL, timeout=10):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "DarkwebMonitor/1.0"
        self._last = 0.0

    def _get(self, path):
        url = self.base + path
        for attempt in range(1, 5):
            elapsed = time.time() - self._last
            if elapsed < 0.12:
                time.sleep(0.12 - elapsed)
            try:
                self._last = time.time()
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code == 429:
                    time.sleep(1.5 ** attempt)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.RequestException as e:
                if attempt == 4:
                    raise
                time.sleep(1.5 ** attempt)

    def get_address(self, address):
        return self._get("/address/" + address)

    def get_address_txs(self, address, limit: int | None = None):
        txs = self._get("/address/" + address + "/txs")
        if limit is None:
            return txs
        return txs[: max(0, limit)]

    def get_tx(self, txid):
        return self._get("/tx/" + txid)

    def get_btc_price(self):
        try:
            data = self._get("/v1/prices")
            return float(data.get("USD", 65000))
        except Exception:
            return 65000.0

client = MempoolClient()
