import csv
import os
import json
from datetime import datetime


def _ensure_dir():
    os.makedirs("data", exist_ok=True)


_seen_per_channel: set[str] = set()


def _is_duplicate(channel_name: str, data_type: str, value: str) -> bool:
    key = f"{channel_name}::{data_type}::{value}"
    if key in _seen_per_channel:
        return True
    _seen_per_channel.add(key)
    return False


def record_wallet(channel_name, coin_type, address, tags=None):
    if _is_duplicate(channel_name, coin_type, address):
        return

    _ensure_dir()
    file_path = "data/wallet_targets.csv"
    file_exists = os.path.isfile(file_path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tag_str = ", ".join(tags) if tags else "NORMAL"

    try:
        with open(file_path, mode="a", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["수집시간", "채널명", "코인유형", "지갑주소", "분석태그"])
            writer.writerow([now, channel_name, coin_type, address, tag_str])
    except Exception as e:
        print(f"[!] 지갑 기록 실패: {e}")


def record_btc_leaks(channel_name, btc_addresses, tags=None):
    _ensure_dir()
    file_path = "data/btc_targets.csv"
    file_exists = os.path.isfile(file_path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tag_str = ", ".join(tags) if tags else "NORMAL"

    try:
        with open(file_path, mode="a", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["수집시간", "채널명", "분석태그", "비트코인_주소"])
            for addr in btc_addresses:
                if not _is_duplicate(channel_name, "BTC_legacy", addr):
                    writer.writerow([now, channel_name, tag_str, addr])
    except Exception as e:
        print(f"[!] 기록 실패: {e}")



def record_extracted_info(channel_name, data_type, value, source="chat"):
    if _is_duplicate(channel_name, data_type, value):
        return

    _ensure_dir()
    file_path = "data/extracted_info.csv"
    file_exists = os.path.isfile(file_path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with open(file_path, mode="a", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["수집시간", "채널명", "데이터유형", "값", "출처"])
            writer.writerow([now, channel_name, data_type, value, source])
    except Exception as e:
        print(f"[!] 비-지갑 데이터 기록 실패: {e}")



def record_raw_message(channel_name, channel_id, sender_id, sender_name,
                       message_id, text, timestamp, source="chat"):
    _ensure_dir()
    file_path = "data/raw_messages.csv"
    file_exists = os.path.isfile(file_path)

    try:
        with open(file_path, mode="a", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow([
                    "수집시간", "채널명", "채널ID", "발신자ID",
                    "발신자이름", "메시지ID", "내용", "원본시간", "출처"
                ])
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            msg_time = timestamp.strftime("%Y-%m-%d %H:%M:%S") if timestamp else ""
            writer.writerow([
                now, channel_name, channel_id, sender_id,
                sender_name, message_id, text, msg_time, source
            ])
    except Exception as e:
        print(f"[!] 대화 원본 기록 실패: {e}")



def record_channel_info(channel_name, channel_id, admin_ids=None,
                        source_type="entered"):

    _ensure_dir()
    file_path = "data/channel_info.csv"
    file_exists = os.path.isfile(file_path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    admin_str = ", ".join(str(a) for a in admin_ids) if admin_ids else ""

    try:
        with open(file_path, mode="a", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["수집시간", "채널명", "채널ID", "관리자IDs", "출처유형"])
            writer.writerow([now, channel_name, channel_id, admin_str, source_type])
    except Exception as e:
        print(f"[!] 채널 정보 기록 실패: {e}")



def record_private_channel(invite_link, channel_id=None, channel_name=None,
                           found_in_channel=None):

    if _is_duplicate(found_in_channel or "global", "private_channel", invite_link):
        return

    _ensure_dir()
    file_path = "data/private_channels.csv"
    file_exists = os.path.isfile(file_path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with open(file_path, mode="a", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow([
                    "수집시간", "초대링크", "채널ID", "채널이름",
                    "발견된_채널"
                ])
            writer.writerow([
                now, invite_link, channel_id or "", channel_name or "",
                found_in_channel or ""
            ])
    except Exception as e:
        print(f"[!] 비공개 채널 기록 실패: {e}")



def record_members(channel_name, channel_id, members):

    _ensure_dir()
    file_path = "data/members.csv"
    file_exists = os.path.isfile(file_path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with open(file_path, mode="a", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow([
                    "수집시간", "채널명", "채널ID",
                    "유저ID", "유저네임", "닉네임"
                ])
            for user_id, username, first_name in members:
                writer.writerow([
                    now, channel_name, channel_id,
                    user_id, username or "", first_name or ""
                ])
    except Exception as e:
        print(f"[!] 멤버 정보 기록 실패: {e}")
