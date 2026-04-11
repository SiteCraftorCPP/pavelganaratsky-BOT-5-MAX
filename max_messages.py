from __future__ import annotations

from typing import Any

from max_client import MaxClient, extract_message_mid, image_attachment_token, new_message_simple


def message_body_text(message: dict[str, Any]) -> str:
    body = message.get("body") or {}
    return (body.get("text") or "").strip()


def message_mid(message: dict[str, Any]) -> str | None:
    body = message.get("body") or {}
    return body.get("mid")


def first_image_token(message: dict[str, Any]) -> str | None:
    body = message.get("body") or {}
    for att in body.get("attachments") or []:
        if att.get("type") == "image":
            p = att.get("payload") or {}
            tok = p.get("token")
            if tok:
                return str(tok)
    return None


def is_from_user(message: dict[str, Any]) -> bool:
    s = message.get("sender") or {}
    return not s.get("is_bot", False)


def actor_user_id(message: dict[str, Any]) -> int | None:
    """Кто написал сообщение (в MAX для ACL и БД нужен sender.user_id, не recipient)."""
    if not is_from_user(message):
        return None
    s = message.get("sender") or {}
    uid = s.get("user_id")
    if uid is None:
        return None
    try:
        return int(uid)
    except (TypeError, ValueError):
        return None


async def send_text(
    client: MaxClient,
    user_id: int,
    text: str,
    *,
    attachments: list[dict[str, Any]] | None = None,
    chat_id: int | None = None,
) -> str | None:
    res = await client.send_message(
        user_id,
        new_message_simple(text, attachments=attachments),
        chat_id=chat_id,
    )
    return extract_message_mid(res)


async def edit_text(
    client: MaxClient,
    mid: str,
    text: str,
    *,
    attachments: list[dict[str, Any]] | None = None,
) -> None:
    await client.edit_message(mid, new_message_simple(text, attachments=attachments))
