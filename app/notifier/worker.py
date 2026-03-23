from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.core.db import get_conn
from app.notifier.discord import send_discord
from app.notifier.telegram import send_telegram
from app.repository import alerts as alerts_repo
from app.repository import watchlist_hits as hits_repo

logger = logging.getLogger(__name__)


class AlertWorker:
    def __init__(self) -> None:
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        while not self._stop.is_set():
            await self._process_batch()
            await asyncio.sleep(2)

    async def _process_batch(self) -> None:
        with get_conn() as conn:
            pending = alerts_repo.get_pending_alerts(conn, limit=20)
            conn.commit()
        for alert in pending:
            try:
                await self._deliver(alert_id=int(alert["id"]), hit_id=int(alert["hit_id"]), channel=str(alert["channel"]))
            except Exception:
                logger.exception("alert delivery failed alert_id=%s", alert["id"])

    async def _deliver(self, *, alert_id: int, hit_id: int, channel: str) -> None:
        with get_conn() as conn:
            hit = hits_repo.get_hit_detail(conn, hit_id)
            if hit is None:
                alerts_repo.mark_alert_failed(conn, alert_id, "missing hit")
                conn.commit()
                return
            message = self._build_message(hit)
            try:
                if channel == "stdout":
                    print(message)
                elif channel == "discord":
                    await send_discord(message)
                elif channel == "telegram":
                    await send_telegram(message)
                else:
                    raise ValueError(f"unsupported channel: {channel}")
                alerts_repo.mark_alert_sent(conn, alert_id, datetime.now(timezone.utc).isoformat())
            except Exception as exc:
                alerts_repo.mark_alert_failed(conn, alert_id, str(exc))
            conn.commit()

    def _build_message(self, hit: dict) -> str:
        parts = [
            f"[WATCHLIST HIT] {hit['watch_type']}: {hit['watch_value']}",
            f"matched={hit['matched_value']}",
            f"url={hit['url']}",
        ]
        if hit.get("title"):
            parts.append(f"title={hit['title']}")
        if hit.get("label"):
            parts.append(f"label={hit['label']}")
        if hit.get("screenshot_path"):
            parts.append(f"screenshot={hit['screenshot_path']}")
        return "\n".join(parts)


alert_worker = AlertWorker()
