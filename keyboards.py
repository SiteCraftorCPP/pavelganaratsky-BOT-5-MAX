from max_client import inline_keyboard


def get_welcome_keyboard(lang: str = "ru"):
    """Только кнопка заявки; админка — по команде /admin."""
    text = "REQUEST" if lang == "en" else "ЗАПРОС"
    return [
        inline_keyboard(
            [[{"type": "callback", "text": text, "payload": "request_access"}]]
        )
    ]


def get_language_keyboard():
    return [
        inline_keyboard(
            [
                [
                    {"type": "callback", "text": "🇷🇺 RU", "payload": "lang_ru"},
                    {"type": "callback", "text": "🇬🇧 EN", "payload": "lang_en"},
                ]
            ]
        )
    ]


def get_admin_keyboard():
    rows = [
        [
            {
                "type": "callback",
                "text": "📋 Сообщения рассылки",
                "payload": "admin_list",
            }
        ],
        [
            {
                "type": "callback",
                "text": "➕ Добавить сообщение",
                "payload": "admin_add",
            }
        ],
        [
            {
                "type": "callback",
                "text": "✏️ Приветственное сообщение",
                "payload": "admin_edit_welcome",
            }
        ],
        [
            {
                "type": "callback",
                "text": "🧹 Удалить все сообщения",
                "payload": "admin_delete_all_confirm",
            }
        ],
    ]
    return [inline_keyboard(rows)]


def get_request_actions_keyboard(user_id: int):
    return [
        inline_keyboard(
            [
                [
                    {
                        "type": "callback",
                        "text": "Одобрить",
                        "payload": f"approve_{user_id}",
                    },
                    {
                        "type": "callback",
                        "text": "Отклонить",
                        "payload": f"reject_{user_id}",
                    },
                ]
            ]
        )
    ]


def get_back_keyboard():
    return [
        inline_keyboard(
            [[{"type": "callback", "text": "🔙 Назад", "payload": "admin_back"}]]
        )
    ]
