from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
from collections import defaultdict
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from config import DB_PATH, ensure_directories, load_settings
from hermes_gateway_client import HermesGatewayClient
from line_client import LineClient
from storage import Storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("line-hermes-gateway-bot")

settings = load_settings()
ensure_directories()
storage = Storage(DB_PATH)
storage.init_db()
line_client = LineClient(settings.line_channel_access_token)
hermes_client = HermesGatewayClient(
    base_url=settings.gateway_base_url,
    api_key=settings.gateway_api_key,
    model=settings.gateway_model,
)
chat_locks = defaultdict(asyncio.Lock)

app = FastAPI(title="LINE Hermes Gateway Bot")


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "webhook_url": settings.webhook_url,
        "gateway_base_url": settings.gateway_base_url,
        "db": str(DB_PATH),
    }


@app.post(settings.webhook_path)
async def line_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("x-line-signature", "")
    if not _verify_line_signature(raw_body, signature):
        raise HTTPException(status_code=401, detail="Invalid LINE signature")

    payload = await request.json()
    for event in payload.get("events", []):
        asyncio.create_task(_handle_event(event))
    return JSONResponse({"ok": True})


async def _handle_event(event: Dict[str, Any]) -> None:
    if event.get("type") != "message":
        return

    message = event.get("message") or {}
    if message.get("type") != "text":
        return

    source = event.get("source") or {}
    source_type = source.get("type", "user")
    source_id = source.get("userId") or source.get("groupId") or source.get("roomId")
    user_id = source.get("userId")
    reply_token = event.get("replyToken")
    text = (message.get("text") or "").strip()
    if not source_id or not reply_token or not text:
        return

    chat_key = "{source_type}:{source_id}".format(source_type=source_type, source_id=source_id)
    conversation_name = "line:{chat_key}".format(chat_key=chat_key)
    reply_target_id = source_id
    event_key = (
        event.get("webhookEventId")
        or ("message:{mid}".format(mid=message.get("id")) if message.get("id") else None)
        or ("reply:{token}".format(token=reply_token) if reply_token else None)
        or "chat:{chat_key}:ts:{ts}".format(chat_key=chat_key, ts=event.get("timestamp"))
    )
    if not storage.record_event_if_new(event_key=event_key, chat_key=chat_key):
        logger.info("Skipping duplicate LINE event: %s", event_key)
        return

    storage.upsert_session(
        chat_key=chat_key,
        conversation_name=conversation_name,
        reply_target_id=reply_target_id,
        source_type=source_type,
        source_id=source_id,
        user_id=user_id,
    )

    await line_client.reply_text(reply_token, settings.ack_text)
    asyncio.create_task(
        _run_chat_task(
            chat_key=chat_key,
            reply_target_id=reply_target_id,
            conversation_name=conversation_name,
            text=text,
        )
    )


async def _run_chat_task(*, chat_key: str, reply_target_id: str, conversation_name: str, text: str) -> None:
    lock = chat_locks[chat_key]
    async with lock:
        try:
            result_text = await hermes_client.ask(text, conversation=conversation_name)
            await line_client.push_text(reply_target_id, result_text)
        except Exception as exc:
            logger.exception("Failed to process LINE message for %s", chat_key)
            await line_client.push_text(reply_target_id, "Jarvis 執行失敗：{msg}".format(msg=str(exc)))



def _verify_line_signature(raw_body: bytes, signature: str) -> bool:
    if not settings.line_channel_secret:
        logger.warning("LINE_CHANNEL_SECRET is empty; signature verification will fail")
        return False
    digest = hmac.new(
        settings.line_channel_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature or "")
