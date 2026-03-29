
import asyncio
import os
import json
from telethon import events
from telethon.tl.custom import Message
from telethon.tl.types import (
    ReplyKeyboardMarkup,
    ReplyInlineMarkup,
    KeyboardButtonCallback,
    KeyboardButtonUrl,
    KeyboardButton,
)
from app.telegram.scanner import extract_all_info, random_delay


INVESTIGATED_FILE = "data/investigated_bots.json"


def load_investigated_bots():
    if os.path.exists(INVESTIGATED_FILE):
        try:
            with open(INVESTIGATED_FILE, "r") as f:
                return set(json.load(f))
        except:
            pass
    return set()


def save_investigated_bot(bot_id):
    bots = load_investigated_bots()
    bots.add(str(bot_id))
    os.makedirs(os.path.dirname(INVESTIGATED_FILE), exist_ok=True)
    with open(INVESTIGATED_FILE, "w") as f:
        json.dump(list(bots), f)


def is_already_investigated(bot_id):
    return str(bot_id) in load_investigated_bots()


BACK_KEYWORDS = [
    'back', 'go back', 'return', 'previous', 'prev',
    'home', 'main menu', 'menu',
    '⬅', '◀', '←', '«',
    '뒤로', '돌아가', '이전',
]

ACTION_SKIP_KEYWORDS = [
    'check payment', 'check pay', 'verify payment',
    'cancel', 'close', 'dismiss',
    'confirm', 'submit', 'proceed',
    'pay now', 'pay with', 'payment',
    'refresh', 'reload',
    'delete', 'remove',
]


def _is_back_button(text):
    if not text:
        return False
    lower = text.lower().strip()
    return any(kw in lower for kw in BACK_KEYWORDS)


def _is_action_button(text):
    if not text:
        return False
    lower = text.lower().strip()
    return any(kw in lower for kw in ACTION_SKIP_KEYWORDS)


def _should_skip_button(text):
    if not text:
        return False
    lower = text.lower().strip()
    if _is_back_button(text):
        return True
    if 'bot' in lower:
        return True
    if _is_action_button(text):
        return True
    return False


async def handle_bot_chat(client, bot_entity):
    bot_id = bot_entity.id
    bot_name = getattr(bot_entity, 'first_name', None) or \
               getattr(bot_entity, 'title', None) or \
               str(bot_id)

    if is_already_investigated(bot_id):
        print(f"[BOT] '{bot_name}' 이미 조사 완료. 건너뜁니다.")
        return True

    print(f"\n{'='*50}")
    print(f"[BOT] '{bot_name}' 봇 조사 시작")
    print(f"{'='*50}")

    seen_wallets = set()

    print(f"[BOT] /start 전송 중...")
    sent_msg = await client.send_message(bot_entity, '/start')
    sent_id = sent_msg.id
    await random_delay(0.5, 1.0)

    response = await _wait_for_bot_response(client, bot_entity, after_id=sent_id)

    if response is None:
        print(f"[BOT] '{bot_name}' 봇이 /start에 응답하지 않음. 기존 메시지에서 키보드 탐색...")
        response = await _find_existing_keyboard_message(client, bot_entity)
        if response is None:
            print(f"[BOT] 기존 메시지에서도 키보드를 찾지 못함. 다음 채팅방으로.")
            save_investigated_bot(bot_id)
            return True

    result = extract_all_info(response.text or "", bot_name, source="bot_message")
    new_addrs = _collect_new_wallets(result, seen_wallets)

    if new_addrs:
        print(f"[BOT] 첫 응답에서 지갑 주소 {len(new_addrs)}개 발견. 수집 종료.")
        save_investigated_bot(bot_id)
        return True

    has_reply_kb = _has_reply_keyboard(response)
    has_inline_kb = _has_inline_keyboard(response)

    if not has_reply_kb and not has_inline_kb:
        print(f"[BOT] 키보드 메뉴 없음. 수집 종료.")
        save_investigated_bot(bot_id)
        return True

    if has_reply_kb:
        print(f"[BOT] Reply Keyboard 발견. 탐색 시작.")
        await _explore_reply_keyboard(client, bot_entity, response, bot_name, seen_wallets)
    elif has_inline_kb:
        print(f"[BOT] Inline Keyboard만 발견. 탐색 시작.")
        await _explore_inline_keyboard(client, bot_entity, response, bot_name, seen_wallets)

    save_investigated_bot(bot_id)
    print(f"[BOT] '{bot_name}' 봇 조사 완료. 총 고유 지갑 주소 {len(seen_wallets)}개 수집.")
    return True


async def _explore_reply_keyboard(client, bot_entity, initial_response, bot_name, seen_wallets):
    buttons = _get_reply_keyboard_buttons(initial_response)
    if not buttons:
        return

    explored = set()
    buttons_sorted = _sort_buttons_deposit_first(buttons)

    for btn_text in buttons_sorted:
        if btn_text in explored:
            continue
        if _should_skip_button(btn_text):
            print(f"[BOT] '{btn_text}' 메뉴 건너뜀")
            continue

        explored.add(btn_text)
        print(f"[BOT] Reply Keyboard 선택: '{btn_text}'")

        sent = await client.send_message(bot_entity, btn_text)
        await random_delay(0.5, 1.0)

        response = await _wait_for_bot_response(client, bot_entity, after_id=sent.id)
        if response is None:
            continue

        result = extract_all_info(response.text or "", bot_name, source="bot_message")
        new_addrs = _collect_new_wallets(result, seen_wallets)

        if new_addrs:
            print(f"[BOT] Reply Keyboard '{btn_text}'에서 지갑 주소 발견. 수집 종료.")
            return

        if _has_inline_keyboard(response):
            print(f"[BOT] 응답에 Inline Keyboard 포함. 탐색 시작.")
            should_stop = await _explore_inline_keyboard(
                client, bot_entity, response, bot_name, seen_wallets
            )
            if should_stop:
                return

            print(f"[BOT] Inline 탐색 완료. 다른 Reply Keyboard 메뉴 계속 탐색.")
            await _go_back(client, bot_entity, response)
            await random_delay(0.3, 0.6)


async def _explore_inline_keyboard(client, bot_entity, message, bot_name,
                                   seen_wallets, _explored_data=None):
    if _explored_data is None:
        _explored_data = set()

    while True:
        buttons = _get_inline_keyboard_buttons(message)
        if not buttons:
            break

        next_btn = _find_next_button(buttons, _explored_data)
        if next_btn is None:
            break

        btn_text, btn_data, btn_url = next_btn

        if btn_url:
            print(f"[BOT] URL 버튼 감지: '{btn_text}' → {btn_url}")
            extract_all_info(btn_url, bot_name, source="bot_button_url")
            _explored_data.add(f"url:{btn_url}")
            continue

        if btn_data is not None:
            _explored_data.add(btn_data)
            print(f"[BOT] Inline 버튼 선택: '{btn_text}'")
            try:
                await message.click(data=btn_data)
            except Exception as e:
                print(f"[BOT] 버튼 클릭 실패: {e}")
                continue

            await random_delay(0.5, 1.0)

            updated_msg = await _get_updated_message(client, bot_entity, message.id)
            if updated_msg is None:
                updated_msg = await _wait_for_bot_response(client, bot_entity)
                if updated_msg is None:
                    continue

            result = extract_all_info(
                updated_msg.text or "", bot_name, source="bot_message"
            )
            new_addrs = _collect_new_wallets(result, seen_wallets)

            if new_addrs is None:
                print(f"[BOT] 중복 지갑 주소 발견. 수집 종료.")
                return True

            if len(new_addrs) >= 2:
                print(f"[BOT] 지갑 주소 {len(new_addrs)}개 한번에 발견. 수집 종료.")
                return True

            if len(new_addrs) == 1:
                print(f"[BOT] 지갑 주소 1개 발견. back 후 다른 코인 탐색.")
                await _go_back_inline(client, bot_entity, updated_msg)
                await random_delay(0.3, 0.6)
                refreshed = await _get_updated_message(client, bot_entity, message.id)
                if refreshed is not None:
                    message = refreshed
                continue

            if _has_inline_keyboard(updated_msg):
                should_stop = await _explore_inline_keyboard(
                    client, bot_entity, updated_msg, bot_name,
                    seen_wallets, _explored_data=_explored_data
                )
                if should_stop:
                    return True

            await _go_back_inline(client, bot_entity, updated_msg)
            await random_delay(0.3, 0.6)
            refreshed = await _get_updated_message(client, bot_entity, message.id)
            if refreshed is not None:
                message = refreshed

    return False


def _collect_new_wallets(result, seen_wallets):
    wallets = result.get("wallets", [])
    if not wallets:
        return []

    new_addrs = []
    for coin_type, addr in wallets:
        if addr in seen_wallets:
            print(f"[BOT] 중복 지갑 감지 ({coin_type}): {addr}")
            return None
        seen_wallets.add(addr)
        new_addrs.append(addr)

    return new_addrs


def _find_next_button(buttons, explored_data):
    deposit = []
    others = []
    for btn_text, btn_data, btn_url in buttons:
        if btn_text and 'deposit' in btn_text.lower():
            deposit.append((btn_text, btn_data, btn_url))
        else:
            others.append((btn_text, btn_data, btn_url))

    for btn_text, btn_data, btn_url in deposit + others:
        if _should_skip_button(btn_text):
            continue

        if btn_url:
            key = f"url:{btn_url}"
            if key not in explored_data:
                return (btn_text, btn_data, btn_url)
            continue

        key = btn_data if btn_data is not None else f"text:{btn_text}"
        if key not in explored_data:
            return (btn_text, btn_data, btn_url)

    return None


async def _wait_for_bot_response(client, bot_entity, timeout=15, after_id=None):
    try:
        for attempt in range(timeout):
            if after_id:
                messages = await client.get_messages(
                    bot_entity, limit=5, min_id=after_id
                )
                bot_msgs = [m for m in messages if m and not m.out]
                if bot_msgs:
                    return bot_msgs[0]
            else:
                messages = await client.get_messages(bot_entity, limit=1)
                if messages and not messages[0].out:
                    return messages[0]
            await asyncio.sleep(1.0)
        print(f"[BOT] 봇 응답 대기 시간 초과 ({timeout}초)")
        return None
    except Exception as e:
        print(f"[BOT] 봇 응답 대기 실패: {e}")
        return None


async def _find_existing_keyboard_message(client, bot_entity, search_limit=20):
    try:
        async for msg in client.iter_messages(bot_entity, limit=search_limit):
            if msg.out:
                continue
            if _has_reply_keyboard(msg) or _has_inline_keyboard(msg):
                print(f"[BOT] 기존 메시지에서 키보드 발견 (msg_id: {msg.id})")
                return msg
        return None
    except Exception as e:
        print(f"[BOT] 기존 메시지 탐색 실패: {e}")
        return None


async def _get_updated_message(client, bot_entity, message_id):
    try:
        msg = await client.get_messages(bot_entity, ids=message_id)
        return msg
    except Exception as e:
        print(f"[BOT] 메시지 재조회 실패: {e}")
        return None


def _has_reply_keyboard(message):
    return message and hasattr(message, 'reply_markup') and \
           isinstance(message.reply_markup, ReplyKeyboardMarkup)


def _has_inline_keyboard(message):
    return message and hasattr(message, 'reply_markup') and \
           isinstance(message.reply_markup, ReplyInlineMarkup)


def _get_reply_keyboard_buttons(message):
    if not _has_reply_keyboard(message):
        return []
    buttons = []
    for row in message.reply_markup.rows:
        for btn in row.buttons:
            if isinstance(btn, KeyboardButton) and btn.text:
                buttons.append(btn.text)
    return buttons


def _get_inline_keyboard_buttons(message):
    if not _has_inline_keyboard(message):
        return []
    buttons = []
    for row in message.reply_markup.rows:
        for btn in row.buttons:
            text = getattr(btn, 'text', '') or ''
            data = getattr(btn, 'data', None)
            url = getattr(btn, 'url', None)
            buttons.append((text, data, url))
    return buttons


def _sort_buttons_deposit_first(button_texts):
    deposit = [t for t in button_texts if 'deposit' in t.lower()]
    others = [t for t in button_texts if 'deposit' not in t.lower()]
    return deposit + others


async def _go_back(client, bot_entity, current_response):
    buttons = _get_reply_keyboard_buttons(current_response)
    for text in buttons:
        if _is_back_button(text):
            print(f"[BOT] Back 버튼 선택: '{text}'")
            await client.send_message(bot_entity, text)
            await random_delay(0.5, 1.0)
            return

    print(f"[BOT] Back 버튼 없음. /start 재전송.")
    await client.send_message(bot_entity, '/start')
    await random_delay(0.5, 1.0)


async def _go_back_inline(client, bot_entity, message):
    buttons = _get_inline_keyboard_buttons(message)
    for text, data, url in buttons:
        if text and _is_back_button(text):
            print(f"[BOT] Inline Back 버튼 클릭: '{text}'")
            try:
                await message.click(data=data)
                await random_delay(0.5, 1.0)
                return
            except Exception as e:
                print(f"[BOT] Back 버튼 클릭 실패: {e}")

    print(f"[BOT] Inline Back 버튼 없음. /start 재전송.")
    await client.send_message(bot_entity, '/start')
    await random_delay(0.5, 1.0)
