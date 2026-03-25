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
                print("[PRODUCER] checking due targets...")
                await self._enqueue_initial_targets()
            except Exception as e:
                print(f"[PRODUCER] error: {e}")
            await asyncio.sleep(max(1, settings.poll_interval_seconds))

    async def _enqueue_initial_targets(self) -> None:
        with get_conn() as conn:
            targets = get_due_targets(conn, settings.revisit_after_seconds)
            print(f"[PRODUCER] due_targets={len(targets)}")

            for item in targets:
                try:
                    target_id = int(item["id"])
                    url = self._normalize_url(item["seed_url"])

                    if not url:
                        continue

                    mark_target_queued(conn, target_id)
                    print(f"[QUEUE] target_id={target_id} depth=0 url={url}")
                    await self._enqueue(url, depth=0, target_id=target_id)

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
            print(f"[WORKER {worker_id}] picked depth={depth} target_id={target_id} url={url}")

            failed = False

            try:
                with get_conn() as conn:
                    await self._process_url(
                        conn=conn,
                        url=url,
                        depth=depth,
                        target_id=target_id,
                    )
                    conn.commit()

            except Exception as e:
                failed = True
                print(f"[WORKER {worker_id}] error target_id={target_id} url={url} err={e}")

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

        print(f"[FETCH START] {url}")
        result = await fetch_page(url)
        print(f"[FETCH DONE] {url} status={result.status_code} err={result.error_message}")

        meaningful = bool(result.text.strip())
        skip_reason = None if meaningful else "empty_text"

        print(f"[SCREENSHOT START] {result.url}")
        screenshot_path = await take_screenshot(result.url)
        print(f"[SCREENSHOT DONE] {result.url} path={screenshot_path}")

        previous = pages_repo.get_latest_page_snapshot(conn, result.url)
        changed = previous is None or previous["content_hash"] != result.content_hash
        last_changed_at = fetched_at if changed else (previous["last_changed_at"] if previous else fetched_at)

        html_path = self._save_text_file(settings.html_dir, result.url, result.html, ".html") if result.html else None
        text_path = self._save_text_file(settings.text_dir, result.url, result.text, ".txt") if result.text else None

        print(f"[SAVE PAGE] {result.url}")
        page_id = pages_repo.save_page(
            conn,
            target_id=target_id,
            url=result.url,
            host=result.host,
            title=result.title,
            status_code=result.status_code,
            fetched_at=fetched_at,
            content_hash=result.content_hash,
            last_changed_at=last_changed_at,
            is_meaningful=meaningful,
            skip_reason=skip_reason,
            content_changed=changed,
            raw_html_path=html_path,
            text_dump_path=text_path,
            screenshot_path=screenshot_path,
            error_message=result.error_message,
        )

        saved_items: list[dict] = []

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
            saved_items.append({**item, "id": item_id})

        match_and_queue_alerts(
            conn,
            page_id=page_id,
            extracted_items=saved_items,
            seen_at=fetched_at,
        )

        if depth < settings.max_depth:
            current_host = urlparse(result.url).netloc.lower()
            count = 0
            max_children = 30

            for link in result.links:
                normalized = self._normalize_url(link)
                if not normalized:
                    continue

                if urlparse(normalized).netloc.lower() != current_host:
                    continue

                if count >= max_children:
                    break

                await self._enqueue(normalized, depth + 1, target_id)
                count += 1

            print(f"[DEPTH] queued {count} children from {result.url}")

    def _safe_name(self, url: str) -> str:
        host = urlparse(url).netloc.replace(":", "_") or "page"
        return f"{host}_{sha1(url.encode()).hexdigest()[:12]}"

    def _save_text_file(self, folder: Path, url: str, content: str, suffix: str) -> str:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{self._safe_name(url)}{suffix}"
        path.write_text(content, encoding="utf-8", errors="ignore")
        return str(path)


scheduler = Scheduler()