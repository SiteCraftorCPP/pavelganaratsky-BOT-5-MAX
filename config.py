import os
from dotenv import load_dotenv

load_dotenv()

MAX_BOT_TOKEN = (os.getenv("MAX_BOT_TOKEN") or "").strip()
MAX_API_BASE = (os.getenv("MAX_API_BASE") or "https://platform-api.max.ru").rstrip("/")

_raw_admins = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = {
    int(part.strip())
    for part in _raw_admins.split(",")
    if part.strip().isdigit()
}

MAX_UNSUBSCRIBE_WEBHOOK_ON_START = (
    (os.getenv("MAX_UNSUBSCRIBE_WEBHOOK_ON_START") or "0").strip().lower()
    in ("1", "true", "yes")
)
