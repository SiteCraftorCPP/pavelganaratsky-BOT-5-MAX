from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from config import ADMIN_IDS
from database import (
    add_message,
    delete_all_messages,
    delete_message,
    get_access_request,
    get_all_messages,
    get_message,
    get_setting,
    get_user_dialog_chat,
    set_access_request,
    set_setting,
    update_message,
)
from fsm import clear, get_data, get_state, set_state, update_data
from keyboards import get_admin_keyboard, get_back_keyboard
from max_client import MaxClient, inline_keyboard, new_message_simple, recipient_chat_id
from max_messages import (
    actor_user_id,
    edit_text,
    first_image_token,
    message_body_text,
    message_mid,
    send_text,
)

log = logging.getLogger(__name__)


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def _schedule_list_buttons(messages: list) -> list[list[dict[str, Any]]]:
    buttons: list[list[dict[str, Any]]] = []
    for msg in messages:
        try:
            dt = datetime.strptime(msg["send_time"], "%Y-%m-%d %H:%M:%S")
            date_str = dt.strftime("%d.%m %H:%M")
        except Exception:
            date_str = str(msg["send_time"])
        status = "✅" if msg["is_sent"] else "⏳"
        label = f"{date_str} — {msg['message_text'][:60]} {status}"
        buttons.append(
            [
                {
                    "type": "callback",
                    "text": label[:128],
                    "payload": f"admin_select:{msg['id']}",
                }
            ]
        )
    buttons.append(
        [{"type": "callback", "text": "🔙 Назад", "payload": "admin_menu"}]
    )
    return buttons


async def send_admin_menu(
    client: MaxClient,
    user_id: int,
    *,
    edit_mid: str | None = None,
    recipient: dict[str, Any] | None = None,
) -> None:
    """Только inline-клавиатура (как в MAX / на скриншоте)."""
    cid = recipient_chat_id(recipient)
    body = new_message_simple("Выберите действие:", attachments=get_admin_keyboard())
    if edit_mid:
        await client.edit_message(edit_mid, body)
    else:
        await client.send_message(user_id, body, chat_id=cid)


async def on_admin_callback(
    client: MaxClient,
    user_id: int,
    payload: str,
    callback_id: str,
    message: dict[str, Any] | None,
) -> None:
    if not _is_admin(user_id):
        await client.answer_callback(callback_id, notification="Нет доступа.")
        return

    mid = message_mid(message) if message else None

    # С приветствия: отдельное сообщение, не затираем привет через PUT
    if payload == "admin_open":
        clear(user_id)
        rec = (message or {}).get("recipient")
        await send_admin_menu(client, user_id, recipient=rec)
        await client.answer_callback(callback_id)
        return

    if payload == "admin_menu":
        clear(user_id)
        rec = (message or {}).get("recipient")
        if mid:
            await send_admin_menu(client, user_id, edit_mid=mid)
        else:
            await send_admin_menu(client, user_id, recipient=rec)
        await client.answer_callback(callback_id)
        return

    if payload == "admin_back":
        await _admin_back(client, user_id, callback_id, message, mid)
        return

    if payload == "admin_edit_welcome":
        if mid:
            await edit_text(
                client,
                mid,
                "Отправьте текст приветствия:",
                attachments=get_back_keyboard(),
            )
        set_state(user_id, "editing_welcome_text_ru")
        await client.answer_callback(callback_id)
        return

    if payload == "admin_list":
        await _show_schedule_list(client, user_id, callback_id, mid)
        return

    if payload == "admin_add":
        if mid:
            await edit_text(
                client,
                mid,
                "Введите текст рассылки:",
                attachments=get_back_keyboard(),
            )
        set_state(user_id, "waiting_for_message_text")
        await client.answer_callback(callback_id)
        return

    if payload.startswith("approve_"):
        await _approve_request(client, user_id, payload, callback_id, message)
        return

    if payload.startswith("reject_"):
        await _reject_request(client, user_id, payload, callback_id, message)
        return

    if payload.startswith("admin_select:"):
        await _select_message(client, user_id, payload, callback_id, mid)
        return

    if payload.startswith("admin_delete:"):
        await _delete_single(client, user_id, payload, callback_id, mid)
        return

    if payload.startswith("admin_edit:"):
        await _edit_start(client, user_id, payload, callback_id, mid)
        return

    if payload == "admin_delete_all_confirm":
        if mid:
            kb = [
                inline_keyboard(
                    [
                        [
                            {
                                "type": "callback",
                                "text": "🧹 Да, удалить все",
                                "payload": "admin_delete_all",
                            }
                        ],
                        [
                            {
                                "type": "callback",
                                "text": "🔙 Назад",
                                "payload": "admin_menu",
                            }
                        ],
                    ]
                )
            ]
            await edit_text(
                client,
                mid,
                "Точно удалить ВСЮ рассылку? Это действие необратимо.",
                attachments=kb,
            )
        await client.answer_callback(callback_id)
        return

    if payload == "admin_delete_all":
        await delete_all_messages()
        clear(user_id)
        if mid:
            await edit_text(
                client, mid, "Вся рассылка удалена.", attachments=get_admin_keyboard()
            )
        await client.answer_callback(callback_id)
        return


async def _show_schedule_list(
    client: MaxClient, user_id: int, callback_id: str, mid: str | None
) -> None:
    messages = await get_all_messages()
    if not messages:
        if mid:
            await edit_text(
                client,
                mid,
                "Список рассылки пуст.",
                attachments=get_back_keyboard(),
            )
        await client.answer_callback(callback_id)
        return

    kb = [inline_keyboard(_schedule_list_buttons(messages))]
    if mid:
        await edit_text(client, mid, "Рассылка:", attachments=kb)
    await client.answer_callback(callback_id)


async def _select_message(
    client: MaxClient, user_id: int, payload: str, callback_id: str, mid: str | None
) -> None:
    msg_id = int(payload.split(":", 1)[1])
    msg = await get_message(msg_id)
    if not msg:
        await client.answer_callback(callback_id, notification="Сообщение не найдено.")
        return

    try:
        dt = datetime.strptime(msg["send_time"], "%Y-%m-%d %H:%M:%S")
        date_str = dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        date_str = str(msg["send_time"])

    kb = [
        inline_keyboard(
            [
                [
                    {
                        "type": "callback",
                        "text": "✏️ Изменить",
                        "payload": f"admin_edit:{msg_id}",
                    }
                ],
                [
                    {
                        "type": "callback",
                        "text": "❌ Удалить",
                        "payload": f"admin_delete:{msg_id}",
                    }
                ],
                [{"type": "callback", "text": "🔙 Назад", "payload": "admin_list"}],
            ]
        )
    ]
    if mid:
        await edit_text(
            client,
            mid,
            f"{date_str}\nСообщение:\n\n{msg['message_text']}",
            attachments=kb,
        )
    await client.answer_callback(callback_id)


async def _delete_single(
    client: MaxClient, user_id: int, payload: str, callback_id: str, mid: str | None
) -> None:
    msg_id = int(payload.split(":", 1)[1])
    await delete_message(msg_id)
    await client.answer_callback(callback_id, notification="Сообщение удалено.")
    messages = await get_all_messages()
    if not messages:
        if mid:
            await edit_text(
                client,
                mid,
                "Список рассылки пуст.",
                attachments=get_back_keyboard(),
            )
        return
    kb = [inline_keyboard(_schedule_list_buttons(messages))]
    if mid:
        await edit_text(client, mid, "Рассылка:", attachments=kb)


async def _edit_start(
    client: MaxClient, user_id: int, payload: str, callback_id: str, mid: str | None
) -> None:
    msg_id = int(payload.split(":", 1)[1])
    msg = await get_message(msg_id)
    if not msg:
        await client.answer_callback(callback_id, notification="Сообщение не найдено.")
        return
    update_data(user_id, editing_id=msg_id)
    set_state(user_id, "editing_text")
    if mid:
        await edit_text(
            client, mid, "Введите новый текст:", attachments=get_back_keyboard()
        )
    await client.answer_callback(callback_id)


async def _approve_request(
    client: MaxClient,
    admin_user_id: int,
    payload: str,
    callback_id: str,
    message: dict[str, Any] | None,
) -> None:
    try:
        target_uid = int(payload.split("_", 1)[1])
    except (IndexError, ValueError):
        await client.answer_callback(callback_id, notification="Ошибка.")
        return

    req = await get_access_request(target_uid)
    if not req or req["status"] != "pending":
        await client.answer_callback(callback_id, notification="Заявка уже обработана.")
        return

    await set_access_request(target_uid, "approved")
    target_chat = await get_user_dialog_chat(target_uid)

    try:
        await client.send_message(
            target_uid,
            new_message_simple(
                "Заявка одобрена. Можете пользоваться ботом — откройте меню или нажмите «Старт»."
            ),
            chat_id=target_chat,
        )
    except Exception:
        await client.answer_callback(
            callback_id, notification="Не удалось отправить пользователю."
        )
        return

    mid = message_mid(message) if message else None
    prev_text = ""
    if message:
        prev_text = message_body_text(message) or ""
        if not prev_text:
            body = message.get("body") or {}
            prev_text = body.get("text") or ""

    for admin_id in ADMIN_IDS:
        if admin_id == admin_user_id:
            continue
        try:
            await client.send_message(
                admin_id,
                new_message_simple(prev_text + "\n\n✅ Одобрено."),
            )
        except Exception:
            pass

    if mid:
        try:
            await client.edit_message(
                mid,
                new_message_simple(
                    (prev_text or "Запрос") + "\n\n✅ Одобрено.", attachments=[]
                ),
            )
        except Exception:
            log.exception("edit approve msg")

    await client.answer_callback(callback_id, notification="Одобрено.")


async def _reject_request(
    client: MaxClient,
    admin_user_id: int,
    payload: str,
    callback_id: str,
    message: dict[str, Any] | None,
) -> None:
    try:
        target_uid = int(payload.split("_", 1)[1])
    except (IndexError, ValueError):
        await client.answer_callback(callback_id, notification="Ошибка.")
        return

    await set_access_request(target_uid, "rejected")
    target_chat = await get_user_dialog_chat(target_uid)
    try:
        await client.send_message(
            target_uid,
            new_message_simple(
                "Заявка отклонена. Если это ошибка — свяжитесь с администратором."
            ),
            chat_id=target_chat,
        )
    except Exception:
        log.exception("reject notify user")

    mid = message_mid(message) if message else None
    prev_text = message_body_text(message) if message else ""
    if message and not prev_text:
        body = message.get("body") or {}
        prev_text = body.get("text") or ""

    for admin_id in ADMIN_IDS:
        if admin_id == admin_user_id:
            continue
        try:
            await client.send_message(
                admin_id,
                new_message_simple(prev_text + "\n\n❌ Отклонено."),
            )
        except Exception:
            pass

    if mid:
        try:
            await client.edit_message(
                mid,
                new_message_simple(
                    (prev_text or "Запрос") + "\n\n❌ Отклонено.", attachments=[]
                ),
            )
        except Exception:
            log.exception("edit reject msg")

    await client.answer_callback(callback_id, notification="Отклонено.")


async def _admin_back(
    client: MaxClient,
    user_id: int,
    callback_id: str,
    message: dict[str, Any] | None,
    mid: str | None,
) -> None:
    current = get_state(user_id)

    if current is None:
        clear(user_id)
        if mid:
            await send_admin_menu(client, user_id, edit_mid=mid)
        await client.answer_callback(callback_id)
        return

    if current == "waiting_for_message_text":
        clear(user_id)
        if mid:
            await send_admin_menu(client, user_id, edit_mid=mid)
        await client.answer_callback(callback_id)
        return

    if current == "waiting_for_message_date":
        set_state(user_id, "waiting_for_message_text")
        if mid:
            await edit_text(
                client,
                mid,
                "Введите текст рассылки:",
                attachments=get_back_keyboard(),
            )
        await client.answer_callback(callback_id)
        return

    if current == "waiting_for_message_time":
        set_state(user_id, "waiting_for_message_date")
        if mid:
            await edit_text(
                client,
                mid,
                "Введите дату отправки:",
                attachments=get_back_keyboard(),
            )
        await client.answer_callback(callback_id)
        return

    data = get_data(user_id)
    editing_id = data.get("editing_id")

    if current == "editing_text":
        if not editing_id:
            clear(user_id)
            if mid:
                await send_admin_menu(client, user_id, edit_mid=mid)
            await client.answer_callback(callback_id)
            return
        msg = await get_message(editing_id)
        if not msg:
            clear(user_id)
            if mid:
                await send_admin_menu(client, user_id, edit_mid=mid)
            await client.answer_callback(callback_id)
            return
        try:
            dt = datetime.strptime(msg["send_time"], "%Y-%m-%d %H:%M:%S")
            date_str = dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            date_str = str(msg["send_time"])
        kb = [
            inline_keyboard(
                [
                    [
                        {
                            "type": "callback",
                            "text": "✏️ Изменить",
                            "payload": f"admin_edit:{editing_id}",
                        }
                    ],
                    [
                        {
                            "type": "callback",
                            "text": "❌ Удалить",
                            "payload": f"admin_delete:{editing_id}",
                        }
                    ],
                    [{"type": "callback", "text": "🔙 Назад", "payload": "admin_list"}],
                ]
            )
        ]
        clear(user_id)
        if mid:
            await edit_text(
                client,
                mid,
                f"Сообщение:\n\n{msg['message_text']}\n{date_str}",
                attachments=kb,
            )
        await client.answer_callback(callback_id)
        return

    if current == "editing_date":
        set_state(user_id, "editing_text")
        if mid:
            await edit_text(
                client, mid, "Введите новый текст:", attachments=get_back_keyboard()
            )
        await client.answer_callback(callback_id)
        return

    if current == "editing_time":
        if not editing_id:
            clear(user_id)
            if mid:
                await send_admin_menu(client, user_id, edit_mid=mid)
            await client.answer_callback(callback_id)
            return
        msg = await get_message(editing_id)
        if not msg:
            clear(user_id)
            if mid:
                await send_admin_menu(client, user_id, edit_mid=mid)
            await client.answer_callback(callback_id)
            return
        try:
            dt = datetime.strptime(msg["send_time"], "%Y-%m-%d %H:%M:%S")
            date_str = dt.strftime("%d.%m")
        except Exception:
            date_str = "??.??"
        set_state(user_id, "editing_date")
        if mid:
            await edit_text(
                client,
                mid,
                f"Текущая дата: {date_str}\n"
                f"Введите новую дату (ДД.ММ) или '-' чтобы оставить:",
                attachments=get_back_keyboard(),
            )
        await client.answer_callback(callback_id)
        return

    clear(user_id)
    if mid:
        await send_admin_menu(client, user_id, edit_mid=mid)
    await client.answer_callback(callback_id)


async def on_admin_message(client: MaxClient, message: dict[str, Any]) -> bool:
    from max_messages import is_from_user

    if not is_from_user(message):
        return False

    user_id = actor_user_id(message)
    if user_id is None:
        return False

    r = message.get("recipient") or {}
    cid = recipient_chat_id(r)

    raw = message_body_text(message)
    text = raw.strip()

    async def st(t: str, *, attachments: list[dict[str, Any]] | None = None) -> None:
        await send_text(client, user_id, t, attachments=attachments, chat_id=cid)

    # Вся админка — по sender.user_id; chat_id из recipient для POST /messages
    if not _is_admin(user_id):
        if text.lower() in ("/admin", "/админ") or text == "Админ-панель":
            await client.send_message(
                user_id,
                new_message_simple(
                    "Эта команда доступна только администраторам бота."
                ),
                chat_id=cid,
            )
            return True
        return False

    if text.lower() in ("/admin", "/админ") or text == "Админ-панель":
        clear(user_id)
        await send_admin_menu(client, user_id, recipient=r)
        return True

    state = get_state(user_id)
    if not state:
        return False

    if state == "editing_welcome_text_ru":
        update_data(user_id, welcome_text_ru=text)
        await st(
            "Пришлите фото для приветствия или «-», чтобы оставить текущее.",
            attachments=get_back_keyboard(),
        )
        set_state(user_id, "editing_welcome_photo_ru")
        return True

    if state == "editing_welcome_photo_ru":
        tok = first_image_token(message)
        data = get_data(user_id)
        text_ru = data.get("welcome_text_ru")
        setting_ru = await get_setting("welcome_ru")
        old_photo = setting_ru["photo_file_id"] if setting_ru else None
        photo_ru = old_photo
        if tok:
            photo_ru = tok
        elif text == "-":
            photo_ru = old_photo
        else:
            await st(
                "Пришлите фото или '-' чтобы оставить текущее значение.",
                attachments=get_back_keyboard(),
            )
            return True
        await set_setting("welcome_ru", text_ru, photo_ru)
        clear(user_id)
        await st(
            "Приветствие обновлено.",
            attachments=get_admin_keyboard(),
        )
        return True

    if state == "waiting_for_message_text":
        update_data(user_id, text_ru=text)
        await st(
            "Введите дату отправки (ДД.ММ):",
            attachments=get_back_keyboard(),
        )
        set_state(user_id, "waiting_for_message_date")
        return True

    if state == "waiting_for_message_date":
        try:
            datetime.strptime(text, "%d.%m")
        except ValueError:
            await st("Неверный формат даты. Попробуйте снова (например, '02.03').")
            return True
        update_data(user_id, date=text)
        await st(
            "Введите время отправки:",
            attachments=get_back_keyboard(),
        )
        set_state(user_id, "waiting_for_message_time")
        return True

    if state == "waiting_for_message_time":
        data = get_data(user_id)
        msg_text_ru = data["text_ru"]
        msg_date = data["date"]
        msg_time = text
        try:
            current_year = datetime.now().year
            dt_str = f"{current_year}.{msg_date} {msg_time}"
            dt = datetime.strptime(dt_str, "%Y.%d.%m %H:%M")
            await add_message(msg_text_ru, dt, "all")
            await st(
                f"Сообщение добавлено:\n{msg_text_ru}\n\n{dt.strftime('%d.%m.%Y %H:%M')} (МСК)",
                attachments=get_admin_keyboard(),
            )
            clear(user_id)
        except ValueError:
            await st("Неверный формат времени. Попробуйте снова (например, '14:07').")
        return True

    if state == "editing_text":
        data = get_data(user_id)
        msg_id = data["editing_id"]
        msg = await get_message(msg_id)
        new_text = text
        if new_text == "-":
            new_text = msg["message_text"]
        update_data(user_id, editing_text=new_text)
        try:
            dt = datetime.strptime(msg["send_time"], "%Y-%m-%d %H:%M:%S")
            date_str = dt.strftime("%d.%m")
        except Exception:
            date_str = "??.??"
        await st(
            f"Текущая дата: {date_str}\n"
            f"Введите новую дату (ДД.ММ) или '-' чтобы оставить:",
            attachments=get_back_keyboard(),
        )
        set_state(user_id, "editing_date")
        return True

    if state == "editing_date":
        data = get_data(user_id)
        msg_id = data["editing_id"]
        msg = await get_message(msg_id)
        new_date = text
        if new_date == "-":
            try:
                dt = datetime.strptime(msg["send_time"], "%Y-%m-%d %H:%M:%S")
                new_date = dt.strftime("%d.%m")
            except Exception:
                await st("Ошибка получения текущей даты. Введите дату вручную (ДД.ММ):")
                return True
        else:
            try:
                datetime.strptime(new_date, "%d.%m")
            except ValueError:
                await st("Неверный формат даты. Попробуйте снова (ДД.ММ):")
                return True
        update_data(user_id, editing_date=new_date)
        try:
            dt = datetime.strptime(msg["send_time"], "%Y-%m-%d %H:%M:%S")
            time_str = dt.strftime("%H:%M")
        except Exception:
            time_str = "??:??"
        await st(
            f"Текущее время: {time_str}\n"
            f"Введите новое время (ЧЧ:ММ) или '-' чтобы оставить:",
            attachments=get_back_keyboard(),
        )
        set_state(user_id, "editing_time")
        return True

    if state == "editing_time":
        data = get_data(user_id)
        msg_id = data["editing_id"]
        msg = await get_message(msg_id)
        new_time = text
        if new_time == "-":
            try:
                dt = datetime.strptime(msg["send_time"], "%Y-%m-%d %H:%M:%S")
                new_time = dt.strftime("%H:%M")
            except Exception:
                await st("Ошибка. Введите время вручную (ЧЧ:ММ):")
                return True
        else:
            try:
                datetime.strptime(new_time, "%H:%M")
            except ValueError:
                await st("Неверный формат. Попробуйте снова (ЧЧ:ММ):")
                return True
        try:
            current_year = datetime.now().year
            dt_str = f"{current_year}.{data['editing_date']} {new_time}"
            dt = datetime.strptime(dt_str, "%Y.%d.%m %H:%M")
            await update_message(msg_id, data["editing_text"], dt)
            await st(
                f"Сообщение {msg_id} обновлено.",
                attachments=get_admin_keyboard(),
            )
            clear(user_id)
        except Exception as e:
            await st(f"Ошибка сохранения: {e}")
        return True

    return False
