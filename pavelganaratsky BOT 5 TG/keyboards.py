from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def get_welcome_keyboard(lang: str = "ru"):
    text = "REQUEST" if lang == "en" else "ЗАПРОС"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, callback_data="request_access")]]
    )

def get_admin_reply_keyboard():
    # Кнопка над клавиатурой, которая шлёт /admin
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Админ-панель")]],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def get_language_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇷🇺 RU", callback_data="lang_ru"),
                InlineKeyboardButton(text="🇬🇧 EN", callback_data="lang_en"),
            ]
        ]
    )


def get_admin_keyboard():
    buttons = [
        [InlineKeyboardButton(text="📋 Сообщения рассылки", callback_data="admin_list")],
        [InlineKeyboardButton(text="➕ Добавить сообщение", callback_data="admin_add")],
        [InlineKeyboardButton(text="✏️ Приветственное сообщение", callback_data="admin_edit_welcome")],
        [InlineKeyboardButton(text="🧹 Удалить все сообщения", callback_data="admin_delete_all_confirm")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_request_actions_keyboard(user_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Одобрить", callback_data=f"approve_{user_id}"),
                InlineKeyboardButton(text="Отклонить", callback_data=f"reject_{user_id}"),
            ]
        ]
    )


def get_back_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]]
    )
