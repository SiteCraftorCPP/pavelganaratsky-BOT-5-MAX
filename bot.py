from __future__ import annotations

import asyncio
import logging
import sys

from config import (
    ADMIN_IDS,
    MAX_API_BASE,
    MAX_BOT_TOKEN,
    MAX_UNSUBSCRIBE_WEBHOOK_ON_START,
)
from database import get_meta, init_db, seed_march_if_needed, set_meta, set_user_dialog_chat
from max_client import MaxClient, recipient_chat_id
from max_messages import actor_user_id, is_from_user, message_body_text
import admin_flow
import user_flow
from scheduler import check_and_send_messages

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")


UPDATE_TYPES = [
    "bot_started",
    "message_created",
    "message_callback",
]


async def scheduler_loop(client: MaxClient):
    while True:
        try:
            await check_and_send_messages(client)
        except Exception:
            log.exception("scheduler")
        await asyncio.sleep(60)


async def maybe_clear_webhooks(client: MaxClient) -> None:
    if not MAX_UNSUBSCRIBE_WEBHOOK_ON_START:
        return
    try:
        subs = await client.get_subscriptions()
    except Exception:
        log.exception("get_subscriptions")
        return
    for s in subs:
        url = s.get("url")
        if url:
            log.info("Removing webhook subscription: %s", url)
            await client.unsubscribe_webhook(url)


def _parse_marker(raw: str | None) -> int | None:
    if not raw or not raw.strip().isdigit():
        return None
    return int(raw.strip())


async def handle_update(client: MaxClient, update: dict) -> None:
    ut = update.get("update_type")

    if ut == "bot_started":
        user = update.get("user") or {}
        uid = user.get("user_id")
        ch = update.get("chat_id")
        if uid and ch:
            await set_user_dialog_chat(int(uid), int(ch))
        if uid:
            rec = {"chat_id": ch, "user_id": uid} if ch else None
            await user_flow.handle_start_like(client, int(uid), recipient=rec)
        return

    if ut == "message_created":
        msg = update.get("message") or {}
        if not is_from_user(msg):
            return
        uid = actor_user_id(msg)
        if uid is None:
            return
        r = msg.get("recipient") or {}
        cid = recipient_chat_id(r)
        if cid:
            await set_user_dialog_chat(uid, cid)

        text = message_body_text(msg)
        if text.lower() in ("/start", "start", "/старт"):
            await user_flow.handle_start_like(client, uid, recipient=r)
            return

        if await admin_flow.on_admin_message(client, msg):
            return

        return

    if ut == "message_callback":
        cb = update.get("callback") or {}
        callback_id = cb.get("callback_id")
        payload = cb.get("payload") or ""
        user_obj = cb.get("user") or {}
        raw_uid = user_obj.get("user_id") if user_obj else None
        if raw_uid is None and user_obj:
            raw_uid = user_obj.get("id")
        msg = update.get("message")
        if callback_id is None or raw_uid is None:
            return

        try:
            uid = int(raw_uid)
        except (TypeError, ValueError):
            log.warning("message_callback: неверный user_id: %r", raw_uid)
            return

        if msg:
            mr = msg.get("recipient") or {}
            mcid = recipient_chat_id(mr)
            if mcid:
                await set_user_dialog_chat(uid, mcid)

        if payload == "request_access":
            await user_flow.on_request_access_callback(
                client,
                callback_id,
                uid,
                user_obj,
                recipient=msg.get("recipient") if msg else None,
            )
            return

        if payload.startswith("tz_"):
            await user_flow.on_tz_ignore_callback(client, callback_id)
            return

        if (
            payload.startswith("admin_")
            or payload.startswith("approve_")
            or payload.startswith("reject_")
        ):
            await admin_flow.on_admin_callback(
                client, uid, payload, callback_id, msg
            )
        return


async def main():
    if not MAX_BOT_TOKEN:
        log.error("MAX_BOT_TOKEN не задан (.env)")
        sys.exit(1)
    if not ADMIN_IDS:
        log.warning("ADMIN_IDS пуст — одобрение заявок будет только в БД.")

    await init_db()
    await seed_march_if_needed()

    client = MaxClient(MAX_BOT_TOKEN, MAX_API_BASE)

    try:
        me = await client.get_me()
        log.info("Бот запущен: %s", me.get("first_name") or me.get("username"))
    except Exception:
        log.exception("GET /me — проверьте токен и MAX_API_BASE")

    await maybe_clear_webhooks(client)

    asyncio.create_task(scheduler_loop(client))

    marker = _parse_marker(await get_meta("updates_marker"))

    log.info("Long polling (GET /updates)...")

    while True:
        try:
            data = await client.get_updates(
                marker=marker,
                limit=100,
                timeout=30,
                types=UPDATE_TYPES,
            )
        except Exception:
            log.exception("get_updates")
            await asyncio.sleep(3)
            continue

        updates = data.get("updates") or []
        new_marker = data.get("marker")
        if new_marker is not None:
            marker = int(new_marker)
            await set_meta("updates_marker", str(marker))

        for upd in updates:
            try:
                await handle_update(client, upd)
            except Exception:
                log.exception("handle_update")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
