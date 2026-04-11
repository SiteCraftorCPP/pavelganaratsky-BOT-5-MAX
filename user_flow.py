from __future__ import annotations

import logging
from typing import Any

from database import (
    get_access_request,
    get_setting,
    get_user_language,
    set_access_request,
    set_user_dialog_chat,
    set_user_language,
)
from keyboards import (
    get_language_keyboard,
    get_request_actions_keyboard,
    get_welcome_keyboard,
)
from max_client import MaxClient, image_attachment_token, new_message_simple, recipient_chat_id
from max_messages import actor_user_id, message_body_text

log = logging.getLogger(__name__)

DEFAULT_WELCOME_TEXT_RU = (
    "Привет!\n\n"
    'Я - Бот "Ледяной" Луны🌙\n\n'
    "Вместе с тобой мы будем наблюдать за процессом жизни."
)

DEFAULT_WELCOME_TEXT_EN = (
    "Hello!\n\n"
    'I am the "Icy" Moon bot 🌙\n\n'
    "Together we will observe the flow of life."
)


async def send_welcome(
    client: MaxClient, user_id: int, lang: str, *, chat_id: int | None = None
) -> None:
    if lang == "en":
        setting = await get_setting("welcome_en")
        base = DEFAULT_WELCOME_TEXT_EN
    else:
        setting = await get_setting("welcome_ru")
        base = DEFAULT_WELCOME_TEXT_RU

    text = setting["text"] if setting and setting["text"] else base
    photo_token = setting["photo_file_id"] if setting else None

    attachments: list[dict[str, Any]] = []
    if photo_token:
        attachments.append(image_attachment_token(photo_token))
    attachments.extend(get_welcome_keyboard(lang))

    await client.send_message(
        user_id,
        new_message_simple(text, attachments=attachments),
        chat_id=chat_id,
    )


async def handle_start_like(
    client: MaxClient, user_id: int, *, recipient: dict[str, Any] | None = None
) -> None:
    cid = recipient_chat_id(recipient)
    lang = await get_user_language(user_id)
    if not lang:
        await client.send_message(
            user_id,
            new_message_simple(
                "Выберите язык / Choose the language",
                attachments=get_language_keyboard(),
            ),
            chat_id=cid,
        )
        return

    await send_welcome(client, user_id, lang, chat_id=cid)


async def on_user_text_message(client: MaxClient, message: dict[str, Any]) -> bool:
    """
    Обрабатывает пользовательские текстовые команды. Возвращает True, если событие поглощено.
    """
    from max_messages import is_from_user

    if not is_from_user(message):
        return False

    user_id = actor_user_id(message)
    if user_id is None:
        return False

    text = message_body_text(message).lower()
    if text in ("/start", "start", "/старт"):
        r = message.get("recipient") or {}
        await handle_start_like(client, user_id, recipient=r)
        return True

    return False


async def on_language_callback(
    client: MaxClient,
    callback_id: str,
    user_id: int,
    payload: str,
    *,
    recipient: dict[str, Any] | None = None,
) -> None:
    lang = "ru" if payload == "lang_ru" else "en"
    await set_user_language(user_id, lang)
    cid = recipient_chat_id(recipient)
    if cid:
        await set_user_dialog_chat(user_id, cid)
    await client.answer_callback(callback_id)
    await send_welcome(client, user_id, lang, chat_id=cid)


async def on_request_access_callback(
    client: MaxClient, callback_id: str, user_id: int, user_obj: dict[str, Any]
) -> None:
    try:
        req = await get_access_request(user_id)

        if req and req["status"] == "approved":
            await client.answer_callback(callback_id, notification="Запрос уже одобрен.")
            return

        if req and req["status"] == "pending":
            await client.answer_callback(
                callback_id, notification="Запрос уже направлен, ожидайте решения."
            )
            return

        if req and req["status"] == "rejected":
            await client.answer_callback(callback_id, notification="Заявка была отклонена.")
            return

        await set_access_request(user_id, "pending")

        name = (
            (user_obj.get("first_name") or "")
            + (" " + user_obj["last_name"] if user_obj.get("last_name") else "")
        ).strip() or "—"
        username = user_obj.get("username")
        username_str = f"@{username}" if username else "не указан"
        user_lang = await get_user_language(user_id)
        lang_str = (user_lang or "не выбран").upper()
        admin_text = (
            "Новый запрос:\n\n"
            f"Имя: {name}\n"
            f"Username: {username_str}\n"
            f"Язык: {lang_str}"
        )

        from config import ADMIN_IDS as ADM

        kb = get_request_actions_keyboard(user_id)
        for admin_id in ADM:
            res = await client.send_message(
                admin_id,
                new_message_simple(admin_text, attachments=kb),
                raise_for_status=False,
            )
            if res is None:
                log.warning(
                    "Не удалось отправить уведомление админу %s "
                    "(часто 404: пользователь ещё не открывал чат с ботом).",
                    admin_id,
                )

        await client.answer_callback(callback_id, notification="Заявка отправлена.")
    except Exception:
        log.exception("request_access")
        await client.answer_callback(
            callback_id, notification="Ошибка. Попробуйте позже."
        )


async def on_tz_ignore_callback(client: MaxClient, callback_id: str) -> None:
    await client.answer_callback(callback_id)
