import os
import re
from dotenv import load_dotenv

load_dotenv()

MAX_BOT_TOKEN = (os.getenv("MAX_BOT_TOKEN") or "").strip()
MAX_API_BASE = (os.getenv("MAX_API_BASE") or "https://platform-api.max.ru").rstrip("/")

_raw_admins = os.getenv("ADMIN_IDS", "")


def _parse_admin_ids(raw: str) -> set[int]:
    """Числовые user_id админов (как в профиле MAX / ответах API). Разделитель: запятая или ;"""
    out: set[int] = set()
    for part in re.split(r"[;,]", raw):
        p = part.strip().strip("\ufeff")
        if not p:
            continue
        if "#" in p:
            p = p.split("#", 1)[0].strip()
        if p.isdigit():
            out.add(int(p))
    return out


ADMIN_IDS = _parse_admin_ids(_raw_admins)

MAX_UNSUBSCRIBE_WEBHOOK_ON_START = (
    (os.getenv("MAX_UNSUBSCRIBE_WEBHOOK_ON_START") or "0").strip().lower()
    in ("1", "true", "yes")
)
