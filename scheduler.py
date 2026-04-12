import logging
from datetime import datetime, timedelta

from database import (
    get_all_messages,
    get_users,
    is_message_sent_for_user,
    mark_message_sent_for_user,
)
from max_client import MaxClient, image_attachment_token, new_message_simple

log = logging.getLogger(__name__)

MSK_OFFSET = 3


def _parse_send_time(send_time_str: str) -> datetime:
    return datetime.strptime(send_time_str, "%Y-%m-%d %H:%M:%S")


async def check_and_send_messages(client: MaxClient):
    """
    Расписание в БД — время МСК; рассылка по target_language (ru/all/both).
    Пересылка в отдельный чат не используется.
    """

    messages = await get_all_messages()
    if not messages:
        return

    users = await get_users()
    if not users:
        return

    now_utc = datetime.utcnow()
    now_msk = now_utc + timedelta(hours=MSK_OFFSET)

    for msg in messages:
        text = msg["message_text"]
        schedule_id = msg["id"]

        try:
            target_lang = msg["target_language"]
        except Exception:
            target_lang = "all"
        # только русский контент: старые записи «только EN» не шлём
        if target_lang == "en":
            continue

        base_msk_time = _parse_send_time(msg["send_time"])

        if base_msk_time.date() < now_msk.date():
            continue

        if now_msk < base_msk_time:
            continue

        for user in users:
            user_id = user["user_id"]
            user_lang = user["language"] if user["language"] else "ru"

            if target_lang and target_lang not in ("all", "both"):
                if target_lang != user_lang:
                    continue

            if await is_message_sent_for_user(user_id, schedule_id):
                continue

            try:
                chat_id = user["dialog_chat_id"]
                if chat_id is not None:
                    chat_id = int(chat_id)
                await client.send_message(
                    user_id,
                    new_message_simple(text),
                    chat_id=chat_id,
                )
                await mark_message_sent_for_user(user_id, schedule_id)
            except Exception as e:
                log.warning("Failed to send schedule to %s: %s", user_id, e)
