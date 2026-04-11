from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from config import ADMIN_IDS
from database import (
    get_setting,
    get_access_request,
    set_access_request,
    set_user_language,
    get_user_language,
)
from keyboards import (
    get_admin_reply_keyboard,
    get_welcome_keyboard,
    get_request_actions_keyboard,
    get_language_keyboard,
)

router = Router()


DEFAULT_WELCOME_TEXT_RU = (
    "Привет!\n\n"
    "Я - Бот \"Ледяной\" Луны🌙\n\n"
    "Вместе с тобой мы будем наблюдать за процессом жизни."
)

DEFAULT_WELCOME_TEXT_EN = (
    "Hello!\n\n"
    "I am the \"Icy\" Moon bot 🌙\n\n"
    "Together we will observe the flow of life."
)

DEFAULT_AFTER_TZ_TEXT_RU = "Часовой пояс {tz} установлен."
DEFAULT_AFTER_TZ_TEXT_EN = "Time zone {tz} has been set."


async def send_welcome(message: Message | CallbackQuery, lang: str):
    # Раздельные настройки для RU/EN
    if lang == "en":
        setting = await get_setting("welcome_en")
        base = DEFAULT_WELCOME_TEXT_EN
    else:
        setting = await get_setting("welcome_ru")
        base = DEFAULT_WELCOME_TEXT_RU

    text = setting["text"] if setting and setting["text"] else base
    photo_id = setting["photo_file_id"] if setting else None

    target = message.message if isinstance(message, CallbackQuery) else message

    if photo_id:
        await target.answer_photo(
            photo=photo_id, caption=text, reply_markup=get_welcome_keyboard(lang)
        )
    else:
        await target.answer(text, reply_markup=get_welcome_keyboard(lang))

    user_id = (
        message.from_user.id
        if isinstance(message, Message)
        else message.from_user.id
    )
    if user_id in ADMIN_IDS and isinstance(message, Message):
        await message.answer(
            "Админ-клавиатура активна.", reply_markup=get_admin_reply_keyboard()
        )


@router.message(Command("start"))
async def cmd_start(message: Message):
    lang = await get_user_language(message.from_user.id)
    if not lang:
        await message.answer(
            "Выберите язык / Choose the language", reply_markup=get_language_keyboard()
        )
        return

    await send_welcome(message, lang)


@router.callback_query(F.data.in_(["lang_ru", "lang_en"]))
async def process_language_select(callback: CallbackQuery):
    lang = "ru" if callback.data == "lang_ru" else "en"
    user_id = callback.from_user.id
    await set_user_language(user_id, lang)
    await callback.answer()
    await send_welcome(callback, lang)


@router.callback_query(F.data == "request_access")
async def process_request_access(callback: CallbackQuery):
    try:
        user_id = callback.from_user.id
        req = await get_access_request(user_id)

        if req and req["status"] == "approved":
            # Уже одобрен — ничего дополнительно не отправляем
            await callback.answer("Запрос уже одобрен.")
            return

        if req and req["status"] == "pending":
            await callback.answer("Запрос уже направлен, ожидайте решения.", show_alert=True)
            return

        if req and req["status"] == "rejected":
            await callback.answer("Заявка была отклонена.", show_alert=True)
            return

        await set_access_request(user_id, "pending")

        name = callback.from_user.full_name or "—"
        username = callback.from_user.username
        username_str = f"@{username}" if username else "не указан"
        user_lang = await get_user_language(user_id)
        lang_str = (user_lang or "не выбран").upper()
        admin_text = (
            "Новый запрос:\n\n"
            f"Имя: {name}\n"
            f"Username: {username_str}\n"
            f"Язык: {lang_str}"
        )

        kb = get_request_actions_keyboard(user_id)
        for admin_id in ADMIN_IDS:
            try:
                await callback.bot.send_message(
                    chat_id=admin_id, text=admin_text, reply_markup=kb
                )
            except Exception:
                pass

        await callback.answer("Заявка отправлена.")
    except Exception:
        await callback.answer("Ошибка. Попробуйте позже.", show_alert=True)


# Старые инлайновые кнопки выбора пояса могут остаться у пользователей.
# Чтобы не ловить тишину — игнорируем их.
@router.callback_query(F.data.startswith("tz_"))
async def ignore_timezone_buttons(callback: CallbackQuery):
    await callback.answer()
