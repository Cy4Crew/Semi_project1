from __future__ import annotations
import os, re, json
from datetime import datetime
from app.core.db import get_conn

TELEGRAM_TEXT_DIR = "evidence/telegram_text"

def _execute(query, params):
    with get_conn() as conn:
        with conn.cursor() as cur: cur.execute(query, params)
        conn.commit()

def _execute_returning(query, params):
    with get_conn() as conn:
        with conn.cursor() as cur: cur.execute(query, params); row = cur.fetchone()
        conn.commit()
        return row

def record_wallet(channel_name, coin_type, address, tags=None):
    tag_str = ", ".join(tags) if tags else "NORMAL"
    try:
        _execute("INSERT INTO tg_wallets (channel_name,coin_type,address,tags) VALUES (%s,%s,%s,%s) ON CONFLICT (channel_name,coin_type,address) DO NOTHING",
            (channel_name, coin_type, address, tag_str))
        _bridge_to_tracked(channel_name, coin_type, address, tag_str)
    except Exception as e:
        print(f"[!] 지갑 기록 실패: {e}")

def _bridge_to_tracked(channel_name, coin_type, address, tag_str):
    """BTC/ETH 지갑 → tracked_wallets + trace_queue 자동 등록 + 멀티체인 탐지"""
    if coin_type in ("BTC", "BTC_BECH32", "BTC_LEGACY"):
        chain = "BTC"
    elif coin_type in ("ETH", "ETH_ERC20"):
        chain = "ETH"
        address = address.lower().strip()  # ★ EVM 주소 정규화
    else:
        return

    try:
        risk_tags = []
        t = tag_str.lower() if tag_str else ""
        if "ransomware" in t: risk_tags.append("ransomware")
        if "db_leak" in t or "data_stealer" in t: risk_tags.append("high_volume")
        if "access_sale" in t: risk_tags.append("large_tx")

        risk_score = len(risk_tags) * 25

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO tracked_wallets
                           (address, chain, category, is_seed, depth, source,
                            source_detail, channel_name, original_tags,
                            risk_tags, risk_score, is_contract, no_expand,
                            created_at, updated_at)
                       VALUES (%s,%s,'seller',TRUE,0,'telegram',%s,%s,%s,%s,%s,
                               FALSE, FALSE, NOW(), NOW())
                       ON CONFLICT (address, chain) DO UPDATE SET
                           updated_at    = NOW(),
                           channel_name  = COALESCE(NULLIF(tracked_wallets.channel_name,''), EXCLUDED.channel_name),
                           original_tags = EXCLUDED.original_tags,
                           risk_tags     = EXCLUDED.risk_tags,
                           risk_score    = GREATEST(tracked_wallets.risk_score, EXCLUDED.risk_score)""",
                    (address, chain, channel_name, channel_name, tag_str,
                     json.dumps(risk_tags), risk_score))

                # trace_queue에도 등록
                cur.execute(
                    """INSERT INTO trace_queue (address, chain, priority, processed)
                       VALUES (%s, %s, 1, FALSE)
                       ON CONFLICT (address, chain) DO UPDATE SET
                           processed = FALSE,
                           priority  = GREATEST(trace_queue.priority, 1)""",
                    (address, chain))

                # ★ EVM 주소: 멀티체인 자동 탐지
                if chain != "BTC":
                    try:
                        from analyzer.tracer import discover_and_register_chains
                        discovered = discover_and_register_chains(cur, address, chain)
                        if len(discovered) > 1:
                            extra = [c for c in discovered if c != chain]
                            print(f"    [🌐] 멀티체인 탐지: {', '.join(extra)}")
                    except Exception as mc_err:
                        print(f"    [!] 멀티체인 탐지 실패 (무시): {mc_err}")

            conn.commit()
        print(f"    [🔗] tracked_wallets 등록 완료: {address[:10]}... ({chain})")
    except Exception as e:
        print(f"[!] tracked_wallets 브릿지 실패 (무시): {e}")

def record_btc_leaks(channel_name, btc_addresses, tags=None):
    for addr in btc_addresses:
        record_wallet(channel_name, "BTC", addr, tags=tags)

def record_extracted_info(channel_name, data_type, value, source="chat"):
    try:
        _execute("INSERT INTO tg_extracted_info (channel_name,data_type,value,source) VALUES (%s,%s,%s,%s) ON CONFLICT (channel_name,data_type,value) DO NOTHING",
            (channel_name, data_type, value, source))
    except Exception as e:
        print(f"[!] 비-지갑 데이터 기록 실패: {e}")

def record_raw_message(channel_name, channel_id, sender_id, sender_name, message_id, text, timestamp, source="chat"):
    msg_time = None
    if timestamp:
        msg_time = timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp)
    try:
        _execute("INSERT INTO tg_raw_messages (channel_name,channel_id,sender_id,sender_name,message_id,content,original_timestamp,source) VALUES (%s,%s,%s,%s,%s,%s,%s::timestamptz,%s) ON CONFLICT (channel_id,message_id) DO NOTHING",
            (channel_name, channel_id or None, sender_id or None, sender_name, message_id, text, msg_time, source))
    except Exception as e:
        print(f"[!] 대화 원본 기록 실패: {e}")
    _save_text_file(channel_name, channel_id, sender_name, message_id, text, msg_time, source)

def _save_text_file(channel_name, channel_id, sender_name, message_id, text, msg_time, source):
    try:
        os.makedirs(TELEGRAM_TEXT_DIR, exist_ok=True)
        safe_name = re.sub(r'[^\w\-]', '_', channel_name or "unknown")
        filepath = os.path.join(TELEGRAM_TEXT_DIR, f"{safe_name}_{channel_id}.txt")
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(f"[{msg_time or datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{source}] {sender_name or 'Unknown'} (msg:{message_id})\n{text}\n{'-'*40}\n")
    except Exception as e:
        print(f"[!] 텍스트 파일 저장 실패: {e}")

def record_channel_info(channel_name, channel_id, admin_ids=None, source_type="entered"):
    try:
        row = _execute_returning("INSERT INTO tg_channels (channel_name,channel_id,source_type) VALUES (%s,%s,%s) ON CONFLICT (channel_id) DO UPDATE SET channel_name=EXCLUDED.channel_name,source_type=EXCLUDED.source_type RETURNING id",
            (channel_name, channel_id, source_type))
        if row and admin_ids:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    for aid in admin_ids:
                        cur.execute("INSERT INTO tg_channel_admins (tg_channel_id,admin_user_id) VALUES (%s,%s) ON CONFLICT (tg_channel_id,admin_user_id) DO NOTHING",(row["id"],aid))
                conn.commit()
    except Exception as e:
        print(f"[!] 채널 정보 기록 실패: {e}")

def record_private_channel(invite_link, channel_id=None, channel_name=None, found_in_channel=None):
    try:
        _execute("INSERT INTO tg_private_channels (invite_link,channel_id,channel_name,found_in_channel) VALUES (%s,%s,%s,%s) ON CONFLICT (invite_link,found_in_channel) DO NOTHING",
            (invite_link, channel_id, channel_name, found_in_channel))
    except Exception as e:
        print(f"[!] 비공개 채널 기록 실패: {e}")

def record_members(channel_name, channel_id, members):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                for user_id, username, first_name in members:
                    cur.execute("INSERT INTO tg_members (channel_name,channel_id,user_id,username,nickname) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (channel_id,user_id) DO UPDATE SET username=EXCLUDED.username,nickname=EXCLUDED.nickname",
                        (channel_name, channel_id, user_id, username or None, first_name or None))
            conn.commit()
    except Exception as e:
        print(f"[!] 멤버 정보 기록 실패: {e}")
