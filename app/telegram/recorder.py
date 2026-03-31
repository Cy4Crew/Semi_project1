from __future__ import annotations

import os
import re
from datetime import datetime
from app.core.db import get_conn

TELEGRAM_TEXT_DIR = "evidence/telegram_text"


def _execute(query, params):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
        conn.commit()


def _execute_returning(query, params):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
        conn.commit()
        return row


def record_wallet(channel_name, coin_type, address, tags=None):
    tag_str = ", ".join(tags) if tags else "NORMAL"
    try:
        _execute(
            """INSERT INTO tg_wallets (channel_name, coin_type, address, tags)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (channel_name, coin_type, address) DO NOTHING""",
            (channel_name, coin_type, address, tag_str),
        )
    except Exception as e:
        print(f"[!] 지갑 기록 실패: {e}")


def record_btc_leaks(channel_name, btc_addresses, tags=None):
    for addr in btc_addresses:
        record_wallet(channel_name, "BTC", addr, tags=tags)


def record_extracted_info(channel_name, data_type, value, source="chat"):
    try:
        _execute(
            """INSERT INTO tg_extracted_info (channel_name, data_type, value, source)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (channel_name, data_type, value) DO NOTHING""",
            (channel_name, data_type, value, source),
        )
    except Exception as e:
        print(f"[!] 비-지갑 데이터 기록 실패: {e}")


def record_raw_message(channel_name, channel_id, sender_id, sender_name,
                       message_id, text, timestamp, source="chat"):
    msg_time = None
    if timestamp:
        if hasattr(timestamp, 'isoformat'):
            msg_time = timestamp.isoformat()
        else:
            msg_time = str(timestamp)

    try:
        _execute(
            """INSERT INTO tg_raw_messages
                   (channel_name, channel_id, sender_id, sender_name,
                    message_id, content, original_timestamp, source)
               VALUES (%s, %s, %s, %s, %s, %s, %s::timestamptz, %s)
               ON CONFLICT (channel_id, message_id) DO NOTHING""",
            (channel_name, channel_id or None, sender_id or None,
             sender_name, message_id, text, msg_time, source),
        )
    except Exception as e:
        print(f"[!] 대화 원본 기록 실패: {e}")

    _save_text_file(channel_name, channel_id, sender_name, message_id,
                    text, msg_time, source)


def _save_text_file(channel_name, channel_id, sender_name, message_id,
                    text, msg_time, source):
    try:
        os.makedirs(TELEGRAM_TEXT_DIR, exist_ok=True)

        safe_name = re.sub(r'[^\w\-]', '_', channel_name or "unknown")
        filename = f"{safe_name}_{channel_id}.txt"
        filepath = os.path.join(TELEGRAM_TEXT_DIR, filename)

        timestamp_str = msg_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sender_str = sender_name or "Unknown"

        with open(filepath, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp_str}] [{source}] {sender_str} (msg:{message_id})\n")
            f.write(f"{text}\n")
            f.write("-" * 40 + "\n")
    except Exception as e:
        print(f"[!] 텍스트 파일 저장 실패: {e}")


def record_channel_info(channel_name, channel_id, admin_ids=None,
                        source_type="entered"):
    try:
        row = _execute_returning(
            """INSERT INTO tg_channels (channel_name, channel_id, source_type)
               VALUES (%s, %s, %s)
               ON CONFLICT (channel_id)
               DO UPDATE SET channel_name = EXCLUDED.channel_name,
                             source_type = EXCLUDED.source_type
               RETURNING id""",
            (channel_name, channel_id, source_type),
        )
        tg_channel_db_id = row["id"] if row else None

        if tg_channel_db_id and admin_ids:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    for admin_id in admin_ids:
                        cur.execute(
                            """INSERT INTO tg_channel_admins (tg_channel_id, admin_user_id)
                               VALUES (%s, %s)
                               ON CONFLICT (tg_channel_id, admin_user_id) DO NOTHING""",
                            (tg_channel_db_id, admin_id),
                        )
                conn.commit()
    except Exception as e:
        print(f"[!] 채널 정보 기록 실패: {e}")


def record_private_channel(invite_link, channel_id=None, channel_name=None,
                           found_in_channel=None):
    try:
        _execute(
            """INSERT INTO tg_private_channels
                   (invite_link, channel_id, channel_name, found_in_channel)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (invite_link, found_in_channel) DO NOTHING""",
            (invite_link, channel_id, channel_name, found_in_channel),
        )
    except Exception as e:
        print(f"[!] 비공개 채널 기록 실패: {e}")


def record_members(channel_name, channel_id, members):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                for user_id, username, first_name in members:
                    cur.execute(
                        """INSERT INTO tg_members
                               (channel_name, channel_id, user_id, username, nickname)
                           VALUES (%s, %s, %s, %s, %s)
                           ON CONFLICT (channel_id, user_id)
                           DO UPDATE SET username = EXCLUDED.username,
                                         nickname = EXCLUDED.nickname""",
                        (channel_name, channel_id, user_id,
                         username or None, first_name or None),
                    )
            conn.commit()
    except Exception as e:
        print(f"[!] 멤버 정보 기록 실패: {e}")
