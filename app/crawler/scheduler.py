from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from urllib.parse import urldefrag, urlparse

from app.core.config import settings
from app.core.db import get_conn
from app.crawler.extractor import extract_indicators
from app.crawler.fetcher import fetch_page
from app.crawler.matcher import match_and_queue_alerts
from app.crawler.screenshot import take_screenshot
from app.repository import extracted_items as extracted_repo
from app.repository import pages as pages_repo
from app.repository.targets import (
    get_due_targets,
    mark_target_done,
    mark_target_failed,
    mark_target_queued,
)

logger = logging.getLogger(__name__)

# === URL 필터/우선순위 ===
HARD_BLOCK = ("login", "register", "lostpw")

LOW_PRIORITY = (
    "member",
    "user-",
    "memberlist",
    "search",
    "showteam",
    "status",
    "misc.php?page=chat",  # chat은 차단이 아니라 저우선순위
)

HIGH_PRIORITY = ("thread-", "forum-", "pid=", "lastpost")


def classify_url(url: str) -> int:
    low = url.lower()

    if any(x in low for x in HARD_BLOCK):
        return -1

    if any(x in low for x in HIGH_PRIORITY):
        return 2

    if any(x in low for x in LOW_PRIORITY):
        return 0

    return 1


class Scheduler:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[tuple[str, int, int | None]] = asyncio.Queue()
        self.host_counts: dict[str, int] = defaultdict(int)
        self.seen_in_cycle: set[str] = set()
        self.target_inflight: dict[int, int] = defaultdict(int)
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        workers = [asyncio.create_task(self._worker_loop(i)) for i in range(settings.worker_count)]
        producer = asyncio.create_task(self._producer_loop())
        try:
            await self._stop.wait()
        finally:
            producer.cancel()
            for worker in workers:
                worker.cancel()
            await asyncio.gather(producer, *workers, return_exceptions=True)

    async def _producer_loop(self) -> None:
        while True:
            try:
                self.host_counts.clear()
                self.seen_in_cycle.clear()
                await self._enqueue_initial_targets()
            except Exception as e:
            await asyncio.sleep(max(1, settings.poll_interval_seconds))

    async def _enqueue_initial_targets(self) -> None:
        with get_conn() as conn:
            targets = get_due_targets(conn, settings.revisit_after_seconds)

            for item in targets:
                try:
                    target_id = int(item["id"])
                    url = self._normalize_url(item["seed_url"])
                    if not url:
                        continue

                    mark_target_queued(conn, target_id)
                    await self._enqueue(url, 0, target_id)

                except Exception as e:
                    print(f"[SKIP TARGET] {e}")

            conn.commit()

    async def _enqueue(self, url: str, depth: int, target_id: int | None) -> None:
        if url in self.seen_in_cycle:
            return

        host = urlparse(url).netloc.lower()
        if self.host_counts[host] >= settings.max_pages_per_host:
            return

        self.host_counts[host] += 1
        self.seen_in_cycle.add(url)

        if target_id is not None:
            self.target_inflight[target_id] += 1

        await self.queue.put((url, depth, target_id))

    def _normalize_url(self, url: str) -> str | None:
        try:
            url = (url or "").strip()
            if not url:
                return None

            if "://" not in url:
                url = f"http://{url}"

            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"}:
                return None
            if not parsed.netloc:
                return None

            normalized, _ = urldefrag(parsed.geturl())
            return normalized
        except Exception:
            return None

    async def _worker_loop(self, worker_id: int) -> None:
        while True:
            url, depth, target_id = await self.queue.get()

            failed = False
            try:
                with get_conn() as conn:
                    await self._process_url(conn=conn, url=url, depth=depth, target_id=target_id)
                    conn.commit()

            except Exception as e:
                failed = True
                print(f"[ERROR] {url} {e}")

                with get_conn() as conn:
                    if target_id is not None:
                        mark_target_failed(conn, target_id)
                    conn.commit()

            finally:
                if target_id is not None:
                    self.target_inflight[target_id] -= 1
                    if self.target_inflight[target_id] <= 0:
                        del self.target_inflight[target_id]
                        if not failed:
                            with get_conn() as conn:
                                mark_target_done(conn, target_id)
                                conn.commit()

                self.queue.task_done()

    async def _process_url(self, *, conn, url: str, depth: int, target_id: int | None) -> None:
        fetched_at = datetime.now(timezone.utc).isoformat()

        result = await fetch_page(url)
        if not result.text:
            return

        screenshot_path = await take_screenshot(result.url)

        previous = pages_repo.get_latest_page_snapshot(conn, result.url)
        changed = previous is None or previous["content_hash"] != result.content_hash

        page_id = pages_repo.save_page(
            conn,
            target_id=target_id,
            url=result.url,
            host=result.host,
            title=result.title,
            status_code=result.status_code,
            fetched_at=fetched_at,
            content_hash=result.content_hash,
            last_changed_at=fetched_at,
            is_meaningful=True,
            skip_reason=None,
            content_changed=changed,
            raw_html_path=None,
            text_dump_path=None,
            screenshot_path=screenshot_path,
            error_message=result.error_message,
        )

        items = []
        for item in extract_indicators(result.text):
            item_id = extracted_repo.save_extracted_item(
                conn,
                page_id=page_id,
                item_type=item["type"],
                raw=item["raw"],
                normalized=item["normalized"],
                group_key=item["group_key"],
                first_seen_at=fetched_at,
            )
            items.append({**item, "id": item_id})

        match_and_queue_alerts(conn, page_id=page_id, extracted_items=items, seen_at=fetched_at)

        # === 핵심: changed일 때만 확장 ===
        if not changed:
            return

        if depth < settings.max_depth:
            current_host = urlparse(result.url).netloc.lower()

            links = []
            for link in result.links:
                normalized = self._normalize_url(link)
                if not normalized:
                    continue

                if urlparse(normalized).netloc.lower() != current_host:
                    continue

                priority = classify_url(normalized)
                if priority == -1:
                    continue

                links.append((priority, normalized))

            links.sort(key=lambda x: -x[0])

            count = 0
            for _, link in links:
                if count >= 30:
                    break
                await self._enqueue(link, depth + 1, target_id)
                count += 1

            print(f"[DEPTH] queued {count} children from {result.url}")


scheduler = Scheduler()
