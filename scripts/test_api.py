"""Одноразовая проверка GET /me после миграции на platform-api2.max.ru."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import MAX_API_BASE, MAX_BOT_TOKEN
from max_client import MaxClient
from ssl_context import build_max_ssl_verify


async def main() -> int:
    if not MAX_BOT_TOKEN:
        print("MAX_BOT_TOKEN не задан")
        return 1
    client = MaxClient(MAX_BOT_TOKEN, MAX_API_BASE, ssl_verify=build_max_ssl_verify())
    me = await client.get_me()
    print("OK", MAX_API_BASE, me.get("username") or me.get("name"))
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    raise SystemExit(asyncio.run(main()))
