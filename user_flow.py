from __future__ import annotations

import logging
from typing import Any

from database import (
    get_access_request,
    get_setting,
    get_user_dialog_chat,
    get_user_language,
    set_access_request,
    set_user_dialog_chat,
    set_user_language,
)
from keyboards import get_request_actions_keyboard, get_welcome_keyboard
from max_client import MaxClient, image_attachment_token, new_message_simple, recipient_chat_id
from max_messages import actor_user_id, message_body_text

log = logging.getLogger(__name__)

DEFAULT_WELCOME_TEXT_RU = (
    "Привет!\n\n"
    'Я - Бот "Ледяной" Луны🌙\n\n'
    "Вместе с тобой мы будем наблюдать за процессом жизни."
)


async def _send_user_chat(
    client: MaxClient,
    user_id: int,
    chat_id: int | None,
    text: str,
) -> None:
    if not chat_id:
        return
    try:
        await client.send_message(
            user_id,
            new_message_simple(text),
            chat_id=chat_id,
        )
    except Exception:
        log.exception("send user chat notice")


async def send_welcome(
    client: MaxClient, user_id: int, *, chat_id: int | None = None
) -> None:
    setting = await get_setting("welcome_ru")
    text = setting["text"] if setting and setting["text"] else DEFAULT_WELCOME_TEXT_RU
    photo_token = setting["photo_file_id"] if setting else None

    attachments: list[dict[str, Any]] = []
    if photo_token:
        attachments.append(image_attachment_token(photo_token))
    attachments.extend(get_welcome_keyboard())

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
    if lang != "ru":
        await set_user_language(user_id, "ru")
    await send_welcome(client, user_id, chat_id=cid)


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


async def on_request_access_callback(
    client: MaxClient,
    callback_id: str,
    user_id: int,
    user_obj: dict[str, Any],
    *,
    recipient: dict[str, Any] | None = None,
) -> None:
    cid = recipient_chat_id(recipient)
    try:
        req = await get_access_request(user_id)

        if req and req["status"] == "approved":
            await client.answer_callback(
                callback_id, notification="Доступ уже открыт."
            )
            await _send_user_chat(
                client,
                user_id,
                cid,
                "У вас уже есть доступ к боту.",
            )
            return

        if req and req["status"] == "pending":
            await client.answer_callback(
                callback_id, notification="Запрос уже отправлен."
            )
            await _send_user_chat(
                client,
                user_id,
                cid,
                "Запрос уже отправлен администратору. Ожидайте решения.",
            )
            return

        if req and req["status"] == "rejected":
            await client.answer_callback(
                callback_id, notification="Предыдущая заявка отклонена."
            )
            await _send_user_chat(
                client,
                user_id,
                cid,
                "Предыдущая заявка была отклонена. Если нужен доступ — напишите администратору.",
            )
            return

        from config import ADMIN_IDS as ADM

        if not ADM:
            log.error(
                "ADMIN_IDS пуст — в .env укажите числовые user_id админов через запятую."
            )
            await client.answer_callback(
                callback_id,
                notification="Бот не настроен (список админов пуст).",
            )
            return

        await set_access_request(user_id, "pending")

        name = (
            (user_obj.get("first_name") or "")
            + (" " + user_obj["last_name"] if user_obj.get("last_name") else "")
        ).strip() or "—"
        username = user_obj.get("username")
        username_str = f"@{username}" if username else "не указан"
        admin_text = (
            "Новый запрос:\n\n"
            f"Имя: {name}\n"
            f"Username: {username_str}"
        )

        kb = get_request_actions_keyboard(user_id)
        for admin_id in ADM:
            admin_chat = await get_user_dialog_chat(admin_id)
            res = await client.send_message(
                admin_id,
                new_message_simple(admin_text, attachments=kb),
                chat_id=admin_chat,
                raise_for_status=False,
            )
            if res is None:
                log.warning(
                    "Не удалось отправить уведомление админу %s "
                    "(часто: неверный ADMIN_IDS или админ ни разу не писал боту — нужен хотя бы /start или /admin в чате).",
                    admin_id,
                )

        await client.answer_callback(
            callback_id, notification="Заявка отправлена."
        )
        await _send_user_chat(
            client,
            user_id,
            cid,
            "✅ Запрос отправлен администратору.\n\n"
            "Ожидайте решения — здесь же придёт уведомление.",
        )
    except Exception:
        log.exception("request_access")
        await client.answer_callback(
            callback_id, notification="Ошибка. Попробуйте позже."
        )


async def on_tz_ignore_callback(client: MaxClient, callback_id: str) -> None:
    await client.answer_callback(callback_id)
