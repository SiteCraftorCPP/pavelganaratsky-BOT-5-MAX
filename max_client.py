from __future__ import annotations

import json
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


def recipient_chat_id(recipient: dict[str, Any] | None) -> int | None:
    """chat_id из апдейта (диалог); без него часть сценариев на стороне MAX ведёт себя иначе."""
    if not recipient:
        return None
    cid = recipient.get("chat_id")
    if cid is None or cid == 0:
        return None
    try:
        return int(cid)
    except (TypeError, ValueError):
        return None


class MaxClient:
    def __init__(self, token: str, base_url: str):
        self._token = token
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": self._token, "Content-Type": "application/json"}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._base, headers=self._headers, timeout=120.0)

    async def get_me(self) -> dict[str, Any]:
        async with self._client() as c:
            r = await c.get("/me")
            r.raise_for_status()
            return r.json()

    async def get_subscriptions(self) -> list[dict[str, Any]]:
        async with self._client() as c:
            r = await c.get("/subscriptions")
            r.raise_for_status()
            data = r.json()
            subs = data.get("subscriptions")
            if isinstance(subs, list):
                return subs
            return []

    async def unsubscribe_webhook(self, url: str) -> None:
        async with self._client() as c:
            r = await c.request("DELETE", "/subscriptions", params={"url": url})
            if r.status_code >= 400:
                log.warning("Unsubscribe failed %s: %s", r.status_code, r.text)

    async def get_updates(
        self,
        *,
        marker: int | None = None,
        limit: int = 100,
        timeout: int = 30,
        types: list[str] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "timeout": timeout}
        if marker is not None:
            params["marker"] = marker
        if types:
            params["types"] = ",".join(types)
        async with self._client() as c:
            r = await c.get("/updates", params=params)
            r.raise_for_status()
            return r.json()

    async def send_message(
        self,
        user_id: int,
        body: dict[str, Any],
        *,
        chat_id: int | None = None,
        raise_for_status: bool = True,
    ) -> dict[str, Any] | None:
        params: dict[str, Any] = {"user_id": user_id}
        if chat_id is not None and chat_id != 0:
            params["chat_id"] = int(chat_id)
        async with self._client() as c:
            r = await c.post("/messages", params=params, json=body)
            if r.status_code >= 400:
                log.error("send_message %s: %s", r.status_code, r.text)
            if not raise_for_status and r.status_code >= 400:
                return None
            r.raise_for_status()
            return r.json()

    async def edit_message(self, message_id: str, body: dict[str, Any]) -> dict[str, Any]:
        async with self._client() as c:
            r = await c.put("/messages", params={"message_id": message_id}, json=body)
            if r.status_code >= 400:
                log.error("edit_message %s: %s", r.status_code, r.text)
            r.raise_for_status()
            return r.json()

    async def answer_callback(
        self,
        callback_id: str,
        *,
        notification: str | None = None,
        message: dict[str, Any] | None = None,
    ) -> None:
        body: dict[str, Any] = {}
        if notification is not None:
            body["notification"] = notification
        if message is not None:
            body["message"] = message
        if not body:
            # Тост без текста: notification=null (не невидимые символы — на iOS/Android они дают «пустое окно»).
            body = {"notification": None}

        async with self._client() as c:
            r = await c.post(
                "/answers",
                params={"callback_id": callback_id},
                json=body,
            )
            if r.status_code >= 400:
                log.warning("answer_callback %s: %s", r.status_code, r.text)

    async def get_upload_url(self, upload_type: str = "image") -> dict[str, Any]:
        async with self._client() as c:
            r = await c.post("/uploads", params={"type": upload_type})
            r.raise_for_status()
            return r.json()

    async def upload_photo_binary(self, upload_url: str, data: bytes, filename: str) -> Any:
        async with httpx.AsyncClient(timeout=120.0) as c:
            r = await c.post(
                upload_url,
                files={"data": (filename, data)},
                headers={"Content-Type": "multipart/form-data"},
            )
            r.raise_for_status()
            ct = r.headers.get("content-type", "")
            if "json" in ct:
                return r.json()
            try:
                return json.loads(r.text)
            except json.JSONDecodeError:
                return r.text


def new_message_simple(
    text: str,
    *,
    attachments: list[dict[str, Any]] | None = None,
    format_: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"text": text, "attachments": attachments or []}
    if format_:
        body["format"] = format_
    return body


def image_attachment_token(token: str) -> dict[str, Any]:
    return {"type": "image", "payload": {"token": token}}


def inline_keyboard(button_rows: list[list[dict[str, Any]]]) -> dict[str, Any]:
    return {"type": "inline_keyboard", "payload": {"buttons": button_rows}}


def extract_message_mid(send_result: dict[str, Any]) -> str | None:
    msg = send_result.get("message")
    if not msg:
        return None
    body = msg.get("body") or {}
    return body.get("mid")
