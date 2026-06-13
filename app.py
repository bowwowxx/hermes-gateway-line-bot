from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from config import DB_PATH, ensure_directories, load_settings
from hermes_gateway_client import HermesGatewayClient
from line_client import LineClient
from media import image_messages, rewrite_local_paths
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


class ChatLockManager:
    """每個聊天室一把鎖，沒人用就回收，避免 defaultdict 無限增長。"""

    def __init__(self) -> None:
        self._locks: Dict[str, asyncio.Lock] = {}
        self._refcounts: Dict[str, int] = {}
        self._guard = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self, key: str):
        async with self._guard:
            lock = self._locks.setdefault(key, asyncio.Lock())
            self._refcounts[key] = self._refcounts.get(key, 0) + 1
        try:
            async with lock:
                yield
        finally:
            async with self._guard:
                self._refcounts[key] -= 1
                if self._refcounts[key] <= 0:
                    self._locks.pop(key, None)
                    self._refcounts.pop(key, None)


chat_locks = ChatLockManager()

# 持有背景 task 的參考，避免被 GC 中途回收
_background_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


app = FastAPI(title="LINE Hermes Gateway Bot")


@app.on_event("shutdown")
async def _shutdown() -> None:
    await line_client.aclose()
    await hermes_client.aclose()


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
        _spawn(_handle_event(event))
    return JSONResponse({"ok": True})


async def _handle_event(event: Dict[str, Any]) -> None:
    if event.get("type") != "message":
        return

    message = event.get("message") or {}
    msg_type = message.get("type")
    if msg_type not in ("text", "image", "file"):
        return

    source = event.get("source") or {}
    source_type = source.get("type", "user")
    source_id = source.get("userId") or source.get("groupId") or source.get("roomId")
    user_id = source.get("userId")
    reply_token = event.get("replyToken")
    text = (message.get("text") or "").strip()
    if not source_id or not reply_token:
        return
    if msg_type == "text" and not text:
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

    # 不再用 reply 傳 ack 文字（那會把免費的 reply token 浪費掉）。
    # 改用 loading 動畫：免費、不消耗 token。只在 1 對 1 聊天有效，群組會被靜默忽略。
    if source_type == "user" and user_id:
        await line_client.show_loading(user_id)

    # 圖片/檔案：webhook 只給 message id，內容要另外從 api-data.line.me 抓下來存到本地
    if msg_type in ("image", "file"):
        try:
            saved_path = await _save_incoming_content(message)
        except Exception as exc:
            logger.exception("Failed to download LINE content for %s", chat_key)
            await line_client.send_text(
                reply_token=reply_token,
                to=reply_target_id,
                text="抓取你傳的{kind}失敗了：{msg}".format(
                    kind="圖片" if msg_type == "image" else "檔案", msg=str(exc)
                ),
            )
            return
        if msg_type == "image":
            text = (
                "（使用者透過 LINE 傳來一張圖片，已存到本機路徑 {path} 。"
                "請查看這張圖片的內容並回應使用者。）"
            ).format(path=saved_path)
        else:
            text = (
                "（使用者透過 LINE 傳來檔案「{name}」，已存到本機路徑 {path} 。"
                "請視需要查看內容並回應使用者。）"
            ).format(name=message.get("fileName") or "未命名", path=saved_path)

    _spawn(
        _run_chat_task(
            chat_key=chat_key,
            reply_target_id=reply_target_id,
            reply_token=reply_token,
            conversation_name=conversation_name,
            text=text,
        )
    )


_CONTENT_TYPE_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
}


async def _save_incoming_content(message: Dict[str, Any]) -> str:
    message_id = message.get("id")
    if not message_id:
        raise ValueError("message has no id")

    content, content_type = await line_client.get_message_content(message_id)
    content_type = (content_type or "").split(";")[0].strip().lower()

    if message.get("type") == "file" and message.get("fileName"):
        # 保留原始檔名（去掉路徑分隔符避免跳目錄）
        safe_name = str(message["fileName"]).replace("/", "_").replace("\\", "_").replace("..", "_")
        filename = "{mid}_{name}".format(mid=message_id, name=safe_name)
    else:
        ext = _CONTENT_TYPE_EXT.get(content_type, ".bin")
        filename = "{mid}{ext}".format(mid=message_id, ext=ext)

    incoming_dir = Path(settings.incoming_dir)
    incoming_dir.mkdir(parents=True, exist_ok=True)
    path = incoming_dir / filename
    path.write_bytes(content)
    logger.info("Saved incoming %s (%d bytes, %s) to %s", message.get("type"), len(content), content_type, path)
    return str(path)


async def _run_chat_task(
    *,
    chat_key: str,
    reply_target_id: str,
    reply_token: str,
    conversation_name: str,
    text: str,
) -> None:
    async with chat_locks.acquire(chat_key):
        token: str | None = reply_token
        try:
            result_text = await hermes_client.ask(text, conversation=conversation_name)
            result_text, image_urls = rewrite_local_paths(
                result_text,
                local_root=settings.file_local_root,
                public_base=settings.file_public_base,
            )
            messages = [
                {"type": "text", "text": chunk}
                for chunk in line_client._chunk_text(result_text)
            ]
            messages.extend(image_messages(image_urls))
            via = await line_client.send_messages(
                reply_token=token,
                to=reply_target_id,
                messages=messages,
            )
            token = None  # reply token 已消耗（或已 fallback），不可再用
            logger.info("Sent answer to %s via %s", chat_key, via)
        except Exception as exc:
            logger.exception("Failed to process LINE message for %s", chat_key)
            try:
                await line_client.send_text(
                    reply_token=token,
                    to=reply_target_id,
                    text="Jarvis 執行失敗：{msg}".format(msg=str(exc)),
                )
            except Exception:
                logger.exception("Failed to deliver error message for %s", chat_key)


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
