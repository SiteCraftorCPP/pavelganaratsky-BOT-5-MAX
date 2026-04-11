import asyncio
from datetime import datetime, timedelta
from aiogram import Bot

from database import (
    get_all_messages,
    get_users,
    is_message_sent_for_user,
    mark_message_sent_for_user,
    mark_schedule_sent,
)
from config import BROADCAST_CHAT_ID


MSK_OFFSET = 3  # Москва = UTC+3


def _parse_send_time(send_time_str: str) -> datetime:
    return datetime.strptime(send_time_str, "%Y-%m-%d %H:%M:%S")


async def check_and_send_messages(bot: Bot):
    """
    Логика:
    - админ вносит дату/время в МСК;
    - в БД в schedule.send_time хранится это МСК-время;
    - рассылка идёт синхронно всем пользователям по МСК (без учета timezone);
    - учитывается только язык пользователя (users.language) и таргет-язык сообщения (schedule.target_language).
    """

    messages = await get_all_messages()
    if not messages:
        return

    users = await get_users()
    if not users:
        return

    # VPS, скорее всего, в UTC — переводим в МСК вручную
    now_utc = datetime.utcnow()
    now_msk = now_utc + timedelta(hours=MSK_OFFSET)

    for msg in messages:
        text = msg["message_text"]
        schedule_id = msg["id"]

        try:
            target_lang = msg["target_language"]
        except Exception:
            # если в старой БД нет колонки
            target_lang = "all"

        base_msk_time = _parse_send_time(msg["send_time"])

        # если дата рассылки уже прошла (вчера и раньше) — не догоняем
        if base_msk_time.date() < now_msk.date():
            continue

        # ещё рано — пропускаем целиком (для всех пользователей)
        if now_msk < base_msk_time:
            continue

        # Отправляем в общий чат один раз на сообщение расписания
        if BROADCAST_CHAT_ID and not msg["is_sent"]:
            try:
                await bot.send_message(chat_id=BROADCAST_CHAT_ID, text=text)
                await mark_schedule_sent(schedule_id)
            except Exception as e:
                print(f"Failed to send to broadcast chat {BROADCAST_CHAT_ID}: {e}")

        for user in users:
            user_id = user["user_id"]
            user_lang = user["language"] if user["language"] else "ru"

            # фильтруем по языку
            if target_lang and target_lang not in ("all", "both"):
                if target_lang != user_lang:
                    continue

            # уже отправляли этому пользователю это сообщение?
            if await is_message_sent_for_user(user_id, schedule_id):
                continue

            try:
                await bot.send_message(chat_id=user_id, text=text)
                await mark_message_sent_for_user(user_id, schedule_id)
            except Exception as e:
                print(f"Failed to send to {user_id}: {e}")
