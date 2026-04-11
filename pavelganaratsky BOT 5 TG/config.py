import os
from dotenv import load_dotenv
from urllib.parse import quote

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
_raw_broadcast_chat_id = (os.getenv("BROADCAST_CHAT_ID") or "").strip()
BROADCAST_CHAT_ID = int(_raw_broadcast_chat_id) if _raw_broadcast_chat_id else None

_raw_admins = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = {
    int(part.strip())
    for part in _raw_admins.split(",")
    if part.strip().isdigit()
}


def get_telegram_proxy_url() -> str | None:
    """
    Поддерживаем форматы:
    - socks5://user:pass@host:port
    - http://user:pass@host:port
    - host:port:user:pass
    """
    raw = (os.getenv("TELEGRAM_PROXY") or "").strip()
    if not raw:
        return None
    if "://" in raw:
        return raw

    parts = raw.split(":")
    if len(parts) == 4:
        host, port, user, password = parts
        user_q = quote(user, safe="")
        pass_q = quote(password, safe="")
        return f"socks5://{user_q}:{pass_q}@{host}:{port}"

    return raw
