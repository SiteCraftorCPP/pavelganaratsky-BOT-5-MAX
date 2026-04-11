from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from config import ADMIN_IDS
from keyboards import get_admin_keyboard, get_back_keyboard
from states import AdminStates
from database import (
    get_all_messages,
    add_message,
    update_message,
    delete_message,
    delete_all_messages,
    get_message,
    get_setting,
    set_setting,
    get_access_request,
    set_access_request,
    get_user_language,
)
from datetime import datetime

router = Router()


def is_admin(user_id):
    return user_id in ADMIN_IDS


async def _send_admin_menu(message_or_callback):
    """
    Унифицированный вывод главного меню админки.
    """
    text = "Выберите действие:"
    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(text, reply_markup=get_admin_keyboard())
    else:
        await message_or_callback.message.edit_text(text, reply_markup=get_admin_keyboard())


@router.message(Command("admin"))
@router.message(F.text == "Админ-панель")
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return

    await _send_admin_menu(message)


@router.callback_query(F.data == "admin_menu")
async def admin_menu_callback(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    await _send_admin_menu(callback)


@router.callback_query(F.data.startswith("approve_"))
async def process_approve_request(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    try:
        user_id = int(callback.data.split("_", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    req = await get_access_request(user_id)
    if not req or req["status"] != "pending":
        await callback.answer("Заявка уже обработана.", show_alert=True)
        return
    await set_access_request(user_id, "approved")

    # язык пользователя для инфы админам
    user_lang = await get_user_language(user_id)
    lang_str = (user_lang or "не выбран").upper()

    # Уведомляем пользователя об одобрении подписки
    try:
        if user_lang == "en":
            await callback.bot.send_message(chat_id=user_id, text="Subscription approved")
        else:
            await callback.bot.send_message(chat_id=user_id, text="Подписка одобрена")
    except Exception:
        await callback.answer("Не удалось отправить пользователю.", show_alert=True)
        return

    # уведомляем всех админов о результате
    for admin_id in ADMIN_IDS:
        # тому админу, кто уже видит отредактированное сообщение,
        # дублировать уведомление не будем
        if admin_id == callback.from_user.id:
            continue
        try:
            await callback.bot.send_message(
                chat_id=admin_id,
                text=callback.message.text + f"\n\n✅ Одобрено (язык: {lang_str}).",
            )
        except Exception:
            pass

    try:
        await callback.message.edit_text(
            callback.message.text + "\n\n✅ Одобрено.",
            reply_markup=None,
        )
    except Exception:
        pass
    await callback.answer("Одобрено.")


@router.callback_query(F.data.startswith("reject_"))
async def process_reject_request(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    try:
        user_id = int(callback.data.split("_", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    await set_access_request(user_id, "rejected")

    user_lang = await get_user_language(user_id)
    lang_str = (user_lang or "не выбран").upper()

    # уведомляем всех админов
    for admin_id in ADMIN_IDS:
        if admin_id == callback.from_user.id:
            continue
        try:
            await callback.bot.send_message(
                chat_id=admin_id,
                text=callback.message.text + f"\n\n❌ Отклонено (язык: {lang_str}).",
            )
        except Exception:
            pass

    try:
        await callback.message.edit_text(
            callback.message.text + "\n\n❌ Отклонено.",
            reply_markup=None,
        )
    except Exception:
        pass
    await callback.answer("Отклонено.")


@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery, state: FSMContext):
    """
    Шаг назад по сценариям, а не просто в меню.
    """
    if not is_admin(callback.from_user.id):
        return

    current = await state.get_state()

    # Нет активного сценария — в меню
    if current is None:
        await state.clear()
        await _send_admin_menu(callback)
        return

    # --- Создание сообщения ---
    if current == AdminStates.waiting_for_message_text.state:
        # Первый шаг мастера - назад = в меню
        await state.clear()
        await _send_admin_menu(callback)
        return

    if current == AdminStates.waiting_for_message_date.state:
        # Назад с даты -> обратно к вводу текста
        await state.set_state(AdminStates.waiting_for_message_text)
        await callback.message.edit_text(
            "Введите текст сообщения:",
            reply_markup=get_back_keyboard(),
        )
        return

    if current == AdminStates.waiting_for_message_time.state:
        # Назад со времени -> обратно к дате
        await state.set_state(AdminStates.waiting_for_message_date)
        await callback.message.edit_text(
            "Введите дату отправки:",
            reply_markup=get_back_keyboard(),
        )
        return

    # --- Редактирование сообщения ---
    data = await state.get_data()
    editing_id = data.get("editing_id")

    # Шаг редактирования текста: назад -> карточка сообщения
    if current == AdminStates.editing_text.state:
        if not editing_id:
            await state.clear()
            await _send_admin_menu(callback)
            return

        msg = await get_message(editing_id)
        if not msg:
            await state.clear()
            await _send_admin_menu(callback)
            return

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        try:
            dt = datetime.strptime(msg["send_time"], "%Y-%m-%d %H:%M:%S")
            date_str = dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            date_str = msg["send_time"]

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✏️ Изменить",
                        callback_data=f"admin_edit:{editing_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Удалить",
                        callback_data=f"admin_delete:{editing_id}",
                    )
                ],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_list")],
            ]
        )

        await state.clear()
        await callback.message.edit_text(
            f"Сообщение:\n\n{msg['message_text']}\n{date_str}",
            reply_markup=kb,
        )
        return

    # Шаг редактирования даты: назад -> к вводу нового текста
    if current == AdminStates.editing_date.state:
        await state.set_state(AdminStates.editing_text)
        await callback.message.edit_text(
            "Введите новый текст:",
            reply_markup=get_back_keyboard(),
        )
        return

    # Шаг редактирования времени: назад -> к редактированию даты
    if current == AdminStates.editing_time.state:
        if not editing_id:
            await state.clear()
            await _send_admin_menu(callback)
            return

        msg = await get_message(editing_id)
        if not msg:
            await state.clear()
            await _send_admin_menu(callback)
            return

        try:
            dt = datetime.strptime(msg["send_time"], "%Y-%m-%d %H:%M:%S")
            date_str = dt.strftime("%d.%m")
        except Exception:
            date_str = "??.??"

        await state.set_state(AdminStates.editing_date)
        await callback.message.edit_text(
            f"Текущая дата: {date_str}\n"
            f"Введите новую дату (ДД.ММ) или '-' чтобы оставить:",
            reply_markup=get_back_keyboard(),
        )
        return

    # Для всех прочих случаев — просто назад в меню
    await state.clear()
    await _send_admin_menu(callback)


@router.callback_query(F.data == "admin_edit_welcome")
async def admin_edit_welcome(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "Отправьте текст RU:", reply_markup=get_back_keyboard()
    )
    await state.set_state(AdminStates.editing_welcome_text_ru)


@router.message(AdminStates.editing_welcome_text_ru)
async def admin_welcome_text_ru(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    text_ru = message.text
    await state.update_data(welcome_text_ru=text_ru)

    await message.answer(
        "Отправьте фото для RU или нажмите '-':",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(AdminStates.editing_welcome_photo_ru)


@router.message(AdminStates.editing_welcome_photo_ru)
async def admin_welcome_photo_ru(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    text_ru = data.get("welcome_text_ru")

    setting_ru = await get_setting("welcome_ru")
    old_photo_ru = setting_ru["photo_file_id"] if setting_ru else None

    photo_ru = old_photo_ru
    if message.photo:
        photo_ru = message.photo[-1].file_id
    elif message.text and message.text.strip() == "-":
        photo_ru = old_photo_ru
    else:
        await message.answer(
            "Пришлите фото или '-' чтобы оставить текущее значение.",
            reply_markup=get_back_keyboard(),
        )
        return

    await set_setting("welcome_ru", text_ru, photo_ru)

    await message.answer(
        "Отправьте текст EN:", reply_markup=get_back_keyboard()
    )
    await state.set_state(AdminStates.editing_welcome_text_en)


@router.message(AdminStates.editing_welcome_text_en)
async def admin_welcome_text_en(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    text_en = message.text
    await state.update_data(welcome_text_en=text_en)

    await message.answer(
        "Отправьте фото для EN или нажмите '-':",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(AdminStates.editing_welcome_photo_en)


@router.message(AdminStates.editing_welcome_photo_en)
async def admin_welcome_photo_en(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    text_en = data.get("welcome_text_en")

    setting_en = await get_setting("welcome_en")
    old_photo_en = setting_en["photo_file_id"] if setting_en else None

    photo_en = old_photo_en
    if message.photo:
        photo_en = message.photo[-1].file_id
    elif message.text and message.text.strip() == "-":
        photo_en = old_photo_en
    else:
        await message.answer(
            "Пришлите фото или '-' чтобы оставить текущее значение.",
            reply_markup=get_back_keyboard(),
        )
        return

    await set_setting("welcome_en", text_en, photo_en)
    await state.clear()

    await message.answer(
        "Приветствие (RU/EN) обновлено.",
        reply_markup=get_admin_keyboard(),
    )


@router.callback_query(F.data == "admin_edit_after_tz")
async def admin_edit_after_tz(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "Отправьте текст RU:", reply_markup=get_back_keyboard()
    )
    await state.set_state(AdminStates.editing_after_tz_text_ru)


@router.message(AdminStates.editing_after_tz_text_ru)
async def admin_after_tz_text_ru(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    text_ru = message.text
    await state.update_data(after_tz_text_ru=text_ru)

    await message.answer(
        "Отправьте фото для RU или нажмите '-':",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(AdminStates.editing_after_tz_photo_ru)


@router.message(AdminStates.editing_after_tz_photo_ru)
async def admin_after_tz_photo_ru(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    text_ru = data.get("after_tz_text_ru")

    setting_ru = await get_setting("after_timezone_ru")
    old_photo_ru = setting_ru["photo_file_id"] if setting_ru else None

    photo_ru = old_photo_ru
    if message.photo:
        photo_ru = message.photo[-1].file_id
    elif message.text and message.text.strip() == "-":
        photo_ru = old_photo_ru
    else:
        await message.answer(
            "Пришлите фото или '-' чтобы оставить текущее значение.",
            reply_markup=get_back_keyboard(),
        )
        return

    await set_setting("after_timezone_ru", text_ru, photo_ru)

    await message.answer(
        "Отправьте текст EN:", reply_markup=get_back_keyboard()
    )
    await state.set_state(AdminStates.editing_after_tz_text_en)


@router.message(AdminStates.editing_after_tz_text_en)
async def admin_after_tz_text_en(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    text_en = message.text
    await state.update_data(after_tz_text_en=text_en)

    await message.answer(
        "Отправьте фото для EN или нажмите '-':",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(AdminStates.editing_after_tz_photo_en)


@router.message(AdminStates.editing_after_tz_photo_en)
async def admin_after_tz_photo_en(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    text_en = data.get("after_tz_text_en")

    setting_en = await get_setting("after_timezone_en")
    old_photo_en = setting_en["photo_file_id"] if setting_en else None

    photo_en = old_photo_en
    if message.photo:
        photo_en = message.photo[-1].file_id
    elif message.text and message.text.strip() == "-":
        photo_en = old_photo_en
    else:
        await message.answer(
            "Пришлите фото или '-' чтобы оставить текущее значение.",
            reply_markup=get_back_keyboard(),
        )
        return

    await set_setting("after_timezone_en", text_en, photo_en)
    await state.clear()

    await message.answer(
        "Текст после выбора пояса (RU/EN) обновлён.",
        reply_markup=get_admin_keyboard(),
    )


@router.callback_query(F.data == "admin_list")
async def process_list(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    messages = await get_all_messages()

    if not messages:
        await callback.message.edit_text(
            "Список рассылки пуст.",
            reply_markup=get_back_keyboard(),
        )
        return

    # Показываем список как набор кнопок "дата — текст"
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    buttons = []
    for msg in messages:
        try:
            dt = datetime.strptime(msg["send_time"], "%Y-%m-%d %H:%M:%S")
            date_str = dt.strftime("%d.%m %H:%M")
        except Exception:
            date_str = msg["send_time"]

        status = "✅" if msg["is_sent"] else "⏳"
        label = f"{date_str} — {msg['message_text']} {status}"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"admin_select:{msg['id']}",
                )
            ]
        )

    # Кнопка назад в меню
    buttons.append(
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")]
    )

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        "Рассылка:",
        reply_markup=markup,
    )


@router.callback_query(F.data.startswith("admin_select:"))
async def process_select_message(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    msg_id = int(callback.data.split(":", 1)[1])
    msg = await get_message(msg_id)
    if not msg:
        await callback.answer("Сообщение не найдено.", show_alert=True)
        return

    try:
        dt = datetime.strptime(msg["send_time"], "%Y-%m-%d %H:%M:%S")
        date_str = dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        date_str = msg["send_time"]

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Изменить", callback_data=f"admin_edit:{msg_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Удалить", callback_data=f"admin_delete:{msg_id}"
                )
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_list")],
        ]
    )

    await callback.message.edit_text(
        f"{date_str}\n"
        f"Сообщение:\n\n"
        f"{msg['message_text']}",
        reply_markup=kb,
    )


# --- ADD MESSAGE ---
@router.callback_query(F.data == "admin_add")
async def process_add(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "Введите текст сообщения RU:",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(AdminStates.waiting_for_message_text)


@router.message(AdminStates.waiting_for_message_text)
async def process_text_add(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.update_data(text_ru=message.text)
    await message.answer(
        "Введите текст сообщения EN:",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(AdminStates.waiting_for_message_lang)


@router.message(AdminStates.waiting_for_message_date)
async def process_date_add(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    try:
        datetime.strptime(message.text, "%d.%m")
        await state.update_data(date=message.text)
        await message.answer(
            "Введите время отправки:",
            reply_markup=get_back_keyboard(),
        )
        await state.set_state(AdminStates.waiting_for_message_time)
    except ValueError:
        await message.answer("Неверный формат даты. Попробуйте снова (например, '02.03').")


@router.message(AdminStates.waiting_for_message_lang)
async def process_text_add_en_or_lang(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    # Здесь мы ожидаем текст EN для сообщения рассылки
    await state.update_data(text_en=message.text)
    await message.answer(
        "Введите дату отправки:",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(AdminStates.waiting_for_message_date)


@router.message(AdminStates.waiting_for_message_time)
async def process_time_add(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    msg_text_ru = data["text_ru"]
    msg_text_en = data["text_en"]
    msg_date = data["date"]
    msg_time = message.text

    try:
        current_year = datetime.now().year
        dt_str = f"{current_year}.{msg_date} {msg_time}"
        dt = datetime.strptime(dt_str, "%Y.%d.%m %H:%M")

        # Создаём две записи в расписании: RU и EN
        await add_message(msg_text_ru, dt, "ru")
        await add_message(msg_text_en, dt, "en")

        await message.answer(
            f"Сообщения добавлены:\nRU: {msg_text_ru}\nEN: {msg_text_en}\n{dt.strftime('%d.%m.%Y %H:%M')}",
            reply_markup=get_admin_keyboard(),
        )
        await state.clear()

    except ValueError:
        await message.answer("Неверный формат времени. Попробуйте снова (например, '14:07').")


@router.callback_query(F.data.startswith("admin_delete:"))
async def process_delete_single(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    msg_id = int(callback.data.split(":", 1)[1])
    await delete_message(msg_id)
    await callback.answer("Сообщение удалено.")
    # Перерисуем список
    await process_list(callback)


@router.callback_query(F.data == "admin_delete_all_confirm")
async def process_delete_all_confirm(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧹 Да, удалить все", callback_data="admin_delete_all"
                )
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")],
        ]
    )

    await callback.message.edit_text(
        "Точно удалить ВСЮ рассылку? Это действие необратимо.", reply_markup=kb
    )


@router.callback_query(F.data == "admin_delete_all")
async def process_delete_all(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    await delete_all_messages()
    await state.clear()
    await callback.message.edit_text(
        "Вся рассылка удалена.", reply_markup=get_admin_keyboard()
    )


@router.callback_query(F.data.startswith("admin_edit:"))
async def process_edit_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    msg_id = int(callback.data.split(":", 1)[1])
    msg = await get_message(msg_id)
    if not msg:
        await callback.answer("Сообщение не найдено.", show_alert=True)
        return

    await state.update_data(editing_id=msg_id)

    await callback.message.edit_text(
        "Введите новый текст:",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(AdminStates.editing_text)


@router.message(AdminStates.editing_text)
async def process_edit_text(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    msg_id = data["editing_id"]
    msg = await get_message(msg_id)

    new_text = message.text
    if new_text == "-":
        new_text = msg["message_text"]

    await state.update_data(editing_text=new_text)

    try:
        dt = datetime.strptime(msg["send_time"], "%Y-%m-%d %H:%M:%S")
        date_str = dt.strftime("%d.%m")
    except Exception:
        date_str = "??.??"

    await message.answer(
        f"Текущая дата: {date_str}\n"
        f"Введите новую дату (ДД.ММ) или '-' чтобы оставить:",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(AdminStates.editing_date)


@router.message(AdminStates.editing_date)
async def process_edit_date(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    msg_id = data["editing_id"]
    msg = await get_message(msg_id)

    new_date = message.text
    if new_date == "-":
        try:
            dt = datetime.strptime(msg["send_time"], "%Y-%m-%d %H:%M:%S")
            new_date = dt.strftime("%d.%m")
        except Exception:
            await message.answer("Ошибка получения текущей даты. Введите дату вручную (ДД.ММ):")
            return
    else:
        try:
            datetime.strptime(new_date, "%d.%m")
        except ValueError:
            await message.answer("Неверный формат даты. Попробуйте снова (ДД.ММ):")
            return

    await state.update_data(editing_date=new_date)

    try:
        dt = datetime.strptime(msg["send_time"], "%Y-%m-%d %H:%M:%S")
        time_str = dt.strftime("%H:%M")
    except Exception:
        time_str = "??:??"

    await message.answer(
        f"Текущее время: {time_str}\n"
        f"Введите новое время (ЧЧ:ММ) или '-' чтобы оставить:",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(AdminStates.editing_time)


@router.message(AdminStates.editing_time)
async def process_edit_time(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    msg_id = data["editing_id"]
    msg = await get_message(msg_id)

    new_time = message.text
    if new_time == "-":
        try:
            dt = datetime.strptime(msg["send_time"], "%Y-%m-%d %H:%M:%S")
            new_time = dt.strftime("%H:%M")
        except Exception:
            await message.answer("Ошибка. Введите время вручную (ЧЧ:ММ):")
            return
    else:
        try:
            datetime.strptime(new_time, "%H:%M")
        except ValueError:
            await message.answer("Неверный формат. Попробуйте снова (ЧЧ:ММ):")
            return

    try:
        current_year = datetime.now().year
        dt_str = f"{current_year}.{data['editing_date']} {new_time}"
        dt = datetime.strptime(dt_str, "%Y.%d.%m %H:%M")

        await update_message(msg_id, data["editing_text"], dt)

        await message.answer(
            f"Сообщение {msg_id} обновлено.",
            reply_markup=get_admin_keyboard(),
        )
        await state.clear()
    except Exception as e:
        await message.answer(f"Ошибка сохранения: {e}")
