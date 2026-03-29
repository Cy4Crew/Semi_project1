import asyncio
import random
import re
import os
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
from telethon.tl.functions.channels import (
    JoinChannelRequest, GetFullChannelRequest, GetParticipantsRequest
)
from telethon.tl.types import (
    ChannelParticipantsAdmins, ChannelParticipantsRecent,
    ChatInviteAlready, ChatInvite
)
from app.telegram.recorder import (
    record_wallet, record_btc_leaks, record_extracted_info,
    record_raw_message, record_channel_info, record_private_channel,
    record_members
)


ALL_WALLET_PATTERNS = {
    "XMR": r'4[0-9AB][1-9A-HJ-NP-Za-km-z]{93}',
    "BCH": r'(?:bitcoincash:)?[qp][a-z0-9]{41}',
    "ETH": r'0x[0-9a-fA-F]{40}',
    "BTC_BECH32": r'bc1[a-z0-9]{39,59}',
    "LTC_BECH32": r'ltc1[a-z0-9]{39,59}',
    "SOL": r'[1-9A-HJ-NP-Za-km-z]{32,44}',
    "BTC_LEGACY": r'[13][a-km-zA-HJ-NP-Z1-9]{25,34}',
    "LTC_LEGACY": r'[LM][a-km-zA-HJ-NP-Z1-9]{26,33}',
    "TRX": r'T[a-zA-Z0-9]{33}',
}

COIN_DISPLAY = {
    "BTC_BECH32": "BTC",
    "BTC_LEGACY": "BTC",
    "LTC_BECH32": "LTC",
    "LTC_LEGACY": "LTC",
    "ETH": "ETH",
    "XMR": "XMR",
    "TRX": "TRX",
    "BCH": "BCH",
    "SOL": "SOL",
}

SOL_CONTEXT_KEYWORDS = [
    'solana', 'sol', 'phantom', 'solflare', 'raydium',
    'jupiter', 'spl', 'lamport'
]

EMAIL_PATTERN = r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
URL_PATTERN = r'https?://[^\s<>\"\']+|[a-zA-Z0-9\-]+\.onion(?:/[^\s<>\"\']*)?'
TG_LINK_PATTERN = r'(?:https?://)?(?:t\.me|telegram\.me)/[a-zA-Z0-9_+/]+|@[a-zA-Z][a-zA-Z0-9_]{3,}'
TG_PRIVATE_PATTERN = r'(?:https?://)?t\.me/\+([a-zA-Z0-9_-]+)'

TARGET_KEYWORDS = {
    "DB_LEAK": ["database", "leak", "dump", "db", "exfil", "full logs", "유출", "판매"],
    "RANSOMWARE": ["ransomware", "encrypted", "decrypt", "onion", "victim", "recovery fee", "donations", "복구"],
    "INFRA_ATTACK": ["exploit", "cve-", "vulnerability", "poc", "shodan", "rce", "취약점"],
    "DATA_STEALER": ["stealer", "redline", "lumma", "vidar", "fresh logs", "cookies", "계정탈취"],
    "ACCESS_SALE": ["rdp", "vpn", "initial access", "iab", "domain admin", "shell", "root", "권한판매"],
    "HIGH_TARGET": ["whale", "big game", "government", "enterprise", "대기업", "정부기관"]
}


def disambiguate_wallet(coin_type, addr, text):
    display = COIN_DISPLAY.get(coin_type, coin_type)

    if coin_type == "SOL":
        lower_text = text.lower()
        has_sol_context = any(kw in lower_text for kw in SOL_CONTEXT_KEYWORDS)
        if not has_sol_context:
            return None
        return "SOL"

    if coin_type == "TRX":
        lower_text = text.lower()
        trx_keywords = ['tron', 'trx', 'trc20', 'usdt', 'tether']
        if any(kw in lower_text for kw in trx_keywords):
            return "TRX"
        return "TRX"

    return display


def extract_all_info(text, channel_name, source="chat"):
    if not text:
        return {"wallets": [], "emails": [], "urls": [], "tg_links": []}

    all_matches = []
    for coin_type, pattern in ALL_WALLET_PATTERNS.items():
        for m in re.finditer(pattern, text):
            all_matches.append((m.start(), m.end(), coin_type, m.group()))

    all_matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))

    found_wallets = []
    occupied_ranges = []

    for start, end, coin_type, addr in all_matches:
        is_substring = False
        for occ_start, occ_end in occupied_ranges:
            if start >= occ_start and end <= occ_end:
                is_substring = True
                break
        if is_substring:
            continue
        if start > 0 and text[start - 1].isalnum():
            continue
        if end < len(text) and text[end].isalnum():
            continue

        display_coin = disambiguate_wallet(coin_type, addr, text)
        if display_coin is None:
            continue

        occupied_ranges.append((start, end))
        if addr not in {a for _, a in found_wallets}:
            found_wallets.append((display_coin, addr))

    found_emails = list(set(re.findall(EMAIL_PATTERN, text)))
    found_urls = list(set(re.findall(URL_PATTERN, text)))
    found_tg = list(set(re.findall(TG_LINK_PATTERN, text)))

    if found_wallets:
        detected_tags = []
        lower_text = text.lower()
        for category, keywords in TARGET_KEYWORDS.items():
            if any(kw in lower_text for kw in keywords):
                detected_tags.append(category)

        for coin_type, addr in found_wallets:
            record_wallet(channel_name, coin_type, addr, tags=detected_tags)
            print(f"    [🔥] {coin_type} 지갑 주소 감지: {addr}")

        btc_addrs = [a for c, a in found_wallets if c == "BTC"]
        if btc_addrs:
            record_btc_leaks(channel_name, btc_addrs, tags=detected_tags)

    for email in found_emails:
        record_extracted_info(channel_name, "email", email, source=source)
        print(f"    [📧] 이메일 감지: {email}")

    for url in found_urls:
        record_extracted_info(channel_name, "url", url, source=source)
        print(f"    [🔗] URL 감지: {url}")

    for tg in found_tg:
        record_extracted_info(channel_name, "tg_link", tg, source=source)
        print(f"    [✈️] 텔레그램 링크 감지: {tg}")

    return {
        "wallets": found_wallets,
        "emails": found_emails,
        "urls": found_urls,
        "tg_links": found_tg
    }


async def random_delay(min_sec=0.3, max_sec=0.6):
    await asyncio.sleep(random.uniform(min_sec, max_sec))


async def join_target_channel(client, target_id):
    try:
        if target_id.startswith('+'):
            clean_hash = target_id.replace('+', '')
            try:
                updates = await client(ImportChatInviteRequest(clean_hash))
                print(f"[+] 비공개 채널 입장 완료: {target_id}")
                return updates.chats[0]
            except Exception as e:
                if "already a participant" in str(e).lower():
                    print(f"[*] 이미 참여 중인 채널입니다. 방 정보를 찾는 중...")
                    async for dialog in client.iter_dialogs():
                        if dialog.is_channel or dialog.is_group:
                            return await client.get_entity(dialog.id)
                raise e
        else:
            await client(JoinChannelRequest(target_id))
            print(f"[+] 공개 채널 입장 완료: {target_id}")
            return await client.get_entity(target_id)
    except Exception as e:
        print(f"[!] 채널 정보를 가져오지 못했습니다: {e}")
        return None


async def collect_channel_info(client, channel_entity, source_type="entered"):
    channel_name = getattr(channel_entity, 'title', 'Unknown')
    channel_id = channel_entity.id

    admin_ids = []
    try:
        admins = await client(GetParticipantsRequest(
            channel=channel_entity,
            filter=ChannelParticipantsAdmins(),
            offset=0, limit=100, hash=0
        ))
        for user in admins.users:
            admin_ids.append(user.id)
    except Exception as e:
        print(f"[!] 관리자 정보 수집 실패 ({channel_name}): {e}")

    record_channel_info(channel_name, channel_id, admin_ids, source_type)
    print(f"[*] 채널 정보 저장: {channel_name} (ID: {channel_id}, 관리자 {len(admin_ids)}명)")


async def collect_members(client, channel_entity):
    channel_name = getattr(channel_entity, 'title', 'Unknown')
    channel_id = channel_entity.id
    members = []

    try:
        participants = await client(GetParticipantsRequest(
            channel=channel_entity,
            filter=ChannelParticipantsRecent(),
            offset=0, limit=200, hash=0
        ))
        for user in participants.users:
            members.append((
                user.id,
                getattr(user, 'username', None),
                getattr(user, 'first_name', None)
            ))
        record_members(channel_name, channel_id, members)
        print(f"[*] 멤버 정보 저장: {channel_name} ({len(members)}명)")
    except Exception as e:
        print(f"[!] 멤버 정보 수집 실패 ({channel_name}): {e}")


async def resolve_private_invite(client, invite_hash, found_in_channel=None):
    try:
        result = await client(CheckChatInviteRequest(hash=invite_hash))

        if isinstance(result, ChatInviteAlready):
            chat = result.chat
            record_private_channel(
                f"+{invite_hash}",
                channel_id=chat.id,
                channel_name=getattr(chat, 'title', 'Unknown'),
                found_in_channel=found_in_channel
            )
            print(f"    [🔒] 비공개 채널 (이미 참여): +{invite_hash} → ID: {chat.id}")
        elif isinstance(result, ChatInvite):
            record_private_channel(
                f"+{invite_hash}",
                channel_id=None,
                channel_name=getattr(result, 'title', 'Unknown'),
                found_in_channel=found_in_channel
            )
            print(f"    [🔒] 비공개 채널 정보: +{invite_hash} → 이름: {result.title}")
    except Exception as e:
        record_private_channel(
            f"+{invite_hash}", found_in_channel=found_in_channel
        )
        print(f"    [🔒] 비공개 채널 +{invite_hash} (ID 조회 실패: {e})")


async def scrape_channel(client, channel_entity, limit=100, _visited_ids=None):
    if _visited_ids is None:
        _visited_ids = set()

    entity_id = getattr(channel_entity, 'id', str(channel_entity))
    channel_name = getattr(channel_entity, 'title', 'Unknown')

    if entity_id in _visited_ids:
        print(f"[*] '{channel_name}' 이미 스캔 완료. 건너뜁니다.")
        return
    _visited_ids.add(entity_id)

    discovered_tg_links = []

    last_id_file = f"data/last_id_{entity_id}.txt"
    last_read_id = 0

    if os.path.exists(last_id_file):
        with open(last_id_file, "r") as f:
            try: last_read_id = int(f.read().strip())
            except: last_read_id = 0

    print(f"[*] '{channel_name}' 정찰 시작 (마지막 확인 ID: {last_read_id})")

    await collect_channel_info(client, channel_entity, source_type="entered")

    linked_chat_id = None
    try:
        full_info = await client(GetFullChannelRequest(channel=channel_entity))

        pinned_id = full_info.full_chat.pinned_msg_id
        if pinned_id:
            print(f"[*] 공지 발견! 분석 중...")
            p_msg = await client.get_messages(channel_entity, ids=pinned_id)
            if p_msg and p_msg.text:
                _save_raw(p_msg, channel_name, entity_id, "pinned")
                result = extract_all_info(p_msg.text, channel_name, source="pinned")
                discovered_tg_links.extend(result.get("tg_links", []))
                await random_delay()

        linked_chat_id = getattr(full_info.full_chat, 'linked_chat_id', None)
        if linked_chat_id:
            print(f"[*] Discussion Group 발견 (ID: {linked_chat_id})")
    except:
        pass

    new_last_id = last_read_id
    all_messages = []

    try:
        async for message in client.iter_messages(channel_entity, limit=limit, min_id=last_read_id):
            all_messages.append(message)
            if message.id > new_last_id:
                new_last_id = message.id
            await random_delay(0.3, 0.6)

        if not all_messages:
            print("[*] 새로 올라온 메시지가 없습니다.")
        else:
            for message in all_messages:
                _save_raw(message, channel_name, entity_id, "chat")

                if message.text:
                    actual_text = message.text.strip()
                    clean_text = actual_text[:40].replace(chr(10), ' ')
                    print(f"[!] 데이터 분석({len(actual_text)}자): {clean_text}...")
                    result = extract_all_info(actual_text, channel_name, source="chat")
                    discovered_tg_links.extend(result.get("tg_links", []))

                    await _resolve_private_links(client, actual_text, channel_name)

                await random_delay(0.3, 0.6)

            if linked_chat_id:
                await _scrape_reply_threads(client, channel_entity, channel_name,
                                             entity_id, all_messages)
            else:
                print(f"[*] '{channel_name}'에 Discussion Group이 없어 댓글 수집을 건너뜁니다.")

        if new_last_id > last_read_id:
            with open(last_id_file, "w") as f:
                f.write(str(new_last_id))
            print(f"[+] 마지막 읽은 위치 업데이트: {new_last_id}")

        print(f"[+] '{channel_name}' 정찰 세션 종료.")

        if linked_chat_id and linked_chat_id not in _visited_ids:
            await _scrape_discussion_group(client, linked_chat_id, _visited_ids)

        await _explore_discovered_channels(
            client, discovered_tg_links, channel_name, _visited_ids
        )

    except Exception as e:
        print(f"[!] 정찰 실패: {e}")


def _save_raw(message, channel_name, channel_id, source):
    sender = getattr(message, 'sender', None)
    sender_id = getattr(sender, 'id', None) if sender else \
                getattr(message, 'sender_id', None)
    sender_name = ""
    if sender:
        sender_name = getattr(sender, 'first_name', '') or ''
        uname = getattr(sender, 'username', '')
        if uname:
            sender_name = f"{sender_name} (@{uname})"

    record_raw_message(
        channel_name=channel_name,
        channel_id=channel_id,
        sender_id=sender_id or "",
        sender_name=sender_name,
        message_id=message.id,
        text=message.text or message.raw_text or "",
        timestamp=message.date,
        source=source
    )


async def _resolve_private_links(client, text, found_in_channel):
    hashes = re.findall(TG_PRIVATE_PATTERN, text)
    for h in hashes:
        await resolve_private_invite(client, h, found_in_channel=found_in_channel)
        await random_delay(0.3, 0.6)


async def _scrape_reply_threads(client, channel_entity, channel_name,
                                 channel_id, messages):
    for message in messages:
        try:
            reply_count = 0
            async for reply in client.iter_messages(
                channel_entity, reply_to=message.id
            ):
                if reply:
                    reply_count += 1
                    _save_raw(reply, channel_name, channel_id,
                             f"reply_to_{message.id}")
                    if reply.text:
                        reply_text = reply.text.strip()
                        if reply_text:
                            extract_all_info(
                                reply_text, channel_name,
                                source=f"reply_to_{message.id}"
                            )
                            await _resolve_private_links(
                                client, reply_text, channel_name
                            )
                await random_delay(0.3, 0.6)

            if reply_count > 0:
                print(f"[*] 게시물 {message.id}의 댓글 {reply_count}개 수집 완료")

        except Exception as e:
            err_msg = str(e).lower()
            silent_errors = [
                'msg_id_invalid', 'message id', 'no replies',
                'invalid', 'getreplie'
            ]
            if not any(kw in err_msg for kw in silent_errors):
                print(f"[!] 게시물 {message.id} 댓글 수집 실패: {e}")
            continue


async def _scrape_discussion_group(client, linked_chat_id, _visited_ids):
    try:
        discussion_entity = await client.get_entity(linked_chat_id)
        discussion_name = getattr(discussion_entity, 'title', 'Unknown')

        is_restricted = False
        if getattr(discussion_entity, 'join_request', False):
            is_restricted = True
        if not is_restricted:
            try:
                test_msgs = await client.get_messages(discussion_entity, limit=1)
                if test_msgs is None or (hasattr(test_msgs, '__len__') and len(test_msgs) == 0):
                    pass
            except Exception:
                is_restricted = True

        if is_restricted:
            print(f"[*] Discussion Group '{discussion_name}'은 승인제입니다. 정보만 저장.")
            record_channel_info(discussion_name, linked_chat_id, source_type="restricted_group")
            return

        print(f"\n[*] Discussion Group '{discussion_name}' 스캔 시작...")

        await collect_members(client, discussion_entity)

        await collect_channel_info(client, discussion_entity, source_type="discussion_group")

        await scrape_channel(
            client, discussion_entity, limit=100, _visited_ids=_visited_ids
        )
    except Exception as e:
        print(f"[!] Discussion Group(ID: {linked_chat_id}) 스캔 실패: {e}")


async def _explore_discovered_channels(client, tg_links, found_in_channel, _visited_ids):
    if not tg_links:
        return

    unique_links = list(set(tg_links))
    print(f"\n[*] '{found_in_channel}'에서 발견된 텔레그램 링크 {len(unique_links)}개 탐색 시작")

    for link in unique_links:
        username = _extract_username_from_link(link)
        if not username:
            continue

        if username.startswith('+'):
            continue

        if username.lower() in {str(vid).lower() for vid in _visited_ids}:
            continue

        _visited_ids.add(username.lower())

        print(f"[*] 발견된 채널 탐색: @{username} (출처: {found_in_channel})")

        try:
            from telethon.tl.types import User as TelethonUser

            entity = await client.get_entity(username)

            if isinstance(entity, TelethonUser) and getattr(entity, 'bot', False):
                from app.telegram.bot_handler import handle_bot_chat
                print(f"[*] '@{username}'는 봇입니다. bot_handler 실행.")
                await handle_bot_chat(client, entity)
            elif hasattr(entity, 'title'):
                await scrape_channel(client, entity, limit=100, _visited_ids=_visited_ids)
            else:
                print(f"[*] '@{username}'는 개인 사용자입니다. 건너뜁니다.")

        except Exception as e:
            print(f"[!] '@{username}' 탐색 실패: {e}")

        await random_delay(0.5, 1.0)

    print(f"[+] '{found_in_channel}' 발견 채널 탐색 완료.")


def _extract_username_from_link(link: str) -> str | None:
    link = link.strip()

    if link.startswith('@'):
        return link[1:]

    cleaned = link
    for prefix in ['https://t.me/', 'http://t.me/',
                    'https://telegram.me/', 'http://telegram.me/',
                    't.me/', 'telegram.me/']:
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    else:
        return None

    cleaned = cleaned.strip('/').split('/')[0]
    if not cleaned:
        return None

    if cleaned.lower() == 'joinchat':
        parts = link.strip('/').split('/')
        if len(parts) > 1:
            return f"+{parts[-1]}"
        return None

    if cleaned.startswith('+'):
        return cleaned

    return cleaned
