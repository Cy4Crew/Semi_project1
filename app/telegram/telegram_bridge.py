from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import User

logger = logging.getLogger(__name__)

from app.telegram.scanner import (
    scrape_channel, join_target_channel, extract_all_info,
    collect_channel_info, _resolve_private_links, resolve_private_invite,
    random_delay
)
from app.telegram.recorder import record_raw_message
from app.telegram.bot_handler import handle_bot_chat
from app.core.db import get_conn

TELEGRAM_COLLECTOR_API_ID = int(os.environ.get("TELEGRAM_COLLECTOR_API_ID", "0"))
TELEGRAM_COLLECTOR_API_HASH = os.environ.get("TELEGRAM_COLLECTOR_API_HASH", "")
TELEGRAM_COLLECTOR_SESSION = os.environ.get("TELEGRAM_COLLECTOR_SESSION", "")

POLL_INTERVAL = 180

INVESTIGATED_FILE = "data/tg_investigated_channels.json"


def _load_investigated() -> set[str]:
    if os.path.exists(INVESTIGATED_FILE):
        try:
            with open(INVESTIGATED_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def _save_investigated(channels: set[str]) -> None:
    os.makedirs(os.path.dirname(INVESTIGATED_FILE), exist_ok=True)
    with open(INVESTIGATED_FILE, "w") as f:
        json.dump(list(channels), f)


def fetch_new_telegram_links(last_id: int) -> list[dict]:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ei.id, ei.normalized, ei.raw, ei.first_seen_at,
                           p.url AS source_page
                    FROM extracted_items ei
                    JOIN pages p ON p.id = ei.page_id
                    WHERE ei.type = 'telegram' AND ei.id > %s
                    ORDER BY ei.id ASC
                    LIMIT 50
                    """,
                    (last_id,),
                )
                return list(cur.fetchall())
    except Exception as e:
        print(f"[TELEGRAM-BRIDGE] DB 조회 실패: {e}")
        return []


def parse_tg_link(normalized: str) -> tuple[str | None, bool]:
    cleaned = normalized.removeprefix("t.me/").strip("/")

    if not cleaned:
        return None, False

    if cleaned.startswith("+"):
        return cleaned, True

    if cleaned.startswith("joinchat/"):
        hash_part = cleaned.removeprefix("joinchat/")
        return f"+{hash_part}", True

    if re.match(r'^[a-zA-Z][a-zA-Z0-9_]{3,}$', cleaned):
        return cleaned, False

    return None, False


async def process_target(client: TelegramClient, target_id: str) -> None:
    print(f"\n[TELEGRAM-BRIDGE] 타겟 처리 중: {target_id}")

    if target_id.startswith('+'):
        print(f"[TELEGRAM-BRIDGE] '{target_id}'는 비공개 채널입니다. 건너뜁니다.")
        return

    entity = None
    is_bot = False

    clean_id = target_id.lstrip('@')
    if clean_id.lower().endswith('bot'):
        try:
            entity = await client.get_entity(clean_id)
            if isinstance(entity, User) and getattr(entity, 'bot', False):
                is_bot = True
                print(f"[TELEGRAM-BRIDGE] '{clean_id}'는 봇입니다. bot_handler 실행.")
            else:
                entity = None
        except Exception as e:
            print(f"[TELEGRAM-BRIDGE] 봇 정보 조회 실패 ({clean_id}): {e}")
            return

    if is_bot and entity:
        await handle_bot_chat(client, entity)
    else:
        entity = await join_target_channel(client, target_id)
        if entity is None:
            print(f"[TELEGRAM-BRIDGE] '{target_id}' 입장 실패. 건너뜁니다.")
            return

        if isinstance(entity, User) and getattr(entity, 'bot', False):
            print(f"[TELEGRAM-BRIDGE] '{target_id}'는 봇 채팅방입니다.")
            await handle_bot_chat(client, entity)
        else:
            print(f"[TELEGRAM-BRIDGE] '{target_id}'는 일반 채널/그룹입니다. 스캔 실행.")
            await scrape_channel(client, entity, limit=100)

    await asyncio.sleep(2.0)

    if not hasattr(process_target, "_cnt"):
        process_target._cnt = 0

    process_target._cnt += 1

    if process_target._cnt % 3 == 0:
        print("[BRIDGE] 롱슬립 10s")
        await asyncio.sleep(10.0)


_message_folders: dict[int, list] = {}


async def setup_live_monitor(client: TelegramClient) -> None:

    @client.on(events.NewMessage())
    async def handler(event):
        if not event.raw_text:
            return

        channel_id = event.chat_id
        channel_name = getattr(event.chat, 'title', 'Unknown')

        if channel_id not in _message_folders:
            _message_folders[channel_id] = []
            import random
            gather_time = random.randint(600, 1200)
            print(f"[TELEGRAM-LIVE] '{channel_name}' 새 메시지 포착. "
                  f"{gather_time // 60}분 대기...")

            _message_folders[channel_id].append(event)
            await asyncio.sleep(gather_time)

            captured = _message_folders.pop(channel_id, [])
            print(f"[TELEGRAM-LIVE] '{channel_name}' {len(captured)}개 메시지 분석 시작")

            for msg in captured:
                reply_to = getattr(msg, 'reply_to', None)
                if reply_to and getattr(reply_to, 'reply_to_msg_id', None):
                    source = f"live_reply_to_{reply_to.reply_to_msg_id}"
                else:
                    source = "live_monitor"

                sender = getattr(msg, 'sender', None)
                sender_id = getattr(sender, 'id', None) if sender else \
                            getattr(msg, 'sender_id', None)
                sender_name = ""
                if sender:
                    sender_name = getattr(sender, 'first_name', '') or ''
                    uname = getattr(sender, 'username', '')
                    if uname:
                        sender_name = f"{sender_name} (@{uname})"

                record_raw_message(
                    channel_name, channel_id, sender_id or "",
                    sender_name, msg.id, msg.raw_text,
                    msg.date, source=source
                )
                extract_all_info(msg.raw_text, channel_name, source=source)
                await _resolve_private_links(client, msg.raw_text, channel_name)
                await asyncio.sleep(1.0)
        else:
            _message_folders[channel_id].append(event)


async def run_bridge() -> None:
    if not TELEGRAM_COLLECTOR_API_ID or not TELEGRAM_COLLECTOR_API_HASH or not TELEGRAM_COLLECTOR_SESSION:
        print(
            "[TELEGRAM-BRIDGE] TELEGRAM_COLLECTOR_API_ID, TELEGRAM_COLLECTOR_API_HASH, "
            "TELEGRAM_COLLECTOR_SESSION 환경변수가 필요합니다. .env 파일을 확인하세요."
        )
        return

    try:
        client = TelegramClient(
            StringSession(TELEGRAM_COLLECTOR_SESSION),
            TELEGRAM_COLLECTOR_API_ID,
            TELEGRAM_COLLECTOR_API_HASH,
            device_model="Samsung Galaxy S23",
            system_version="Android 14",
            app_version="10.11.1",
            lang_code="ko",
            system_lang_code="ko-KR"
        )

        async with client:
            await client.start()
            me = await client.get_me()
            print(f"[TELEGRAM-BRIDGE] 텔레그램 접속 성공! 계정명: {me.first_name}")

            await setup_live_monitor(client)

            investigated = _load_investigated()
            last_seen_id = 0

            print(f"[TELEGRAM-BRIDGE] DB 폴링 시작 (간격: {POLL_INTERVAL}초)")

            while True:
                try:
                    new_links = fetch_new_telegram_links(last_seen_id)

                    for row in new_links:
                        item_id = row["id"]
                        normalized = row["normalized"]
                        source_page = row.get("source_page", "unknown")

                        if item_id > last_seen_id:
                            last_seen_id = item_id

                        username, is_private = parse_tg_link(normalized)
                        if username is None:
                            continue

                        if username in investigated:
                            continue

                        print(f"[TELEGRAM-BRIDGE] 새 텔레그램 링크 발견: {normalized} "
                              f"(출처: {source_page})")

                        if is_private:
                            hash_part = username.lstrip('+')
                            await resolve_private_invite(
                                client, hash_part,
                                found_in_channel=f"darkweb:{source_page}"
                            )
                        else:
                            await process_target(client, username)

                        investigated.add(username)
                        _save_investigated(investigated)

                except Exception as e:
                    print(f"[TELEGRAM-BRIDGE] 폴링 오류: {e}")

                await asyncio.sleep(POLL_INTERVAL)

    except Exception as e:
        print(f"[TELEGRAM-BRIDGE] 브릿지 치명적 오류: {e}")
        import traceback
        traceback.print_exc()
