from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional

import httpx

LINE_API_BASE = "https://api.line.me/v2/bot"
LINE_DATA_API_BASE = "https://api-data.line.me/v2/bot"

logger = logging.getLogger("line-hermes-gateway-bot.line")


class LineClient:
    def __init__(self, channel_access_token: str):
        self.channel_access_token = channel_access_token
        self._client = httpx.AsyncClient(timeout=20.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    @property
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": "Bearer {token}".format(token=self.channel_access_token),
            "Content-Type": "application/json",
        }

    async def show_loading(self, chat_id: str, seconds: int = 60) -> None:
        """顯示「輸入中」動畫。免費、不消耗 reply token，僅限 1 對 1 聊天。

        失敗時只記 log，不拋例外（群組/多人聊天室呼叫會被 LINE 拒絕，屬預期行為）。
        """
        # loadingSeconds 必須是 5 的倍數，5~60
        seconds = max(5, min(60, (seconds // 5) * 5))
        try:
            resp = await self._client.post(
                "{base}/chat/loading/start".format(base=LINE_API_BASE),
                headers=self._headers,
                json={"chatId": chat_id, "loadingSeconds": seconds},
            )
            resp.raise_for_status()
        except Exception:
            logger.debug("show_loading failed for chat %s (non-fatal)", chat_id, exc_info=True)

    async def get_message_content(self, message_id: str) -> tuple[bytes, str]:
        """下載使用者傳來的圖片/檔案內容。注意：要打 api-data.line.me。

        回傳 (二進位內容, content-type)。LINE 暫存有時效，收到 webhook 後盡快抓。
        """
        resp = await self._client.get(
            "{base}/message/{mid}/content".format(base=LINE_DATA_API_BASE, mid=message_id),
            headers={"Authorization": self._headers["Authorization"]},
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.content, resp.headers.get("content-type", "application/octet-stream")

    async def send_text(self, *, reply_token: Optional[str], to: str, text: str) -> str:
        chunks = self._chunk_text(text)
        messages = [{"type": "text", "text": chunk} for chunk in chunks]
        return await self.send_messages(reply_token=reply_token, to=to, messages=messages)

    async def send_messages(
        self, *, reply_token: Optional[str], to: str, messages: List[Dict[str, str]]
    ) -> str:
        """送出任意 message objects（text/image/...）：優先 reply，失敗才 fallback push。

        超過 5 個訊息時，前 5 個用 reply，剩餘的用 push。
        回傳 "reply"、"reply+push" 或 "push"，方便 log 觀察額度消耗。
        """
        if not messages:
            return "noop"

        if reply_token:
            try:
                await self._reply(reply_token, messages[:5])
                if len(messages) > 5:
                    await self._push(to, messages[5:])
                    return "reply+push"
                return "reply"
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "Reply failed (%s), falling back to push: %s",
                    exc.response.status_code,
                    exc.response.text[:200],
                )

        await self._push(to, messages)
        return "push"

    async def reply_text(self, reply_token: str, text: str) -> None:
        messages = [{"type": "text", "text": chunk} for chunk in self._chunk_text(text)]
        await self._reply(reply_token, messages[:5])

    async def push_text(self, to: str, text: str) -> None:
        messages = [{"type": "text", "text": chunk} for chunk in self._chunk_text(text)]
        await self._push(to, messages)

    async def _reply(self, reply_token: str, messages: List[Dict[str, str]]) -> None:
        resp = await self._client.post(
            "{base}/message/reply".format(base=LINE_API_BASE),
            headers=self._headers,
            json={"replyToken": reply_token, "messages": messages},
        )
        resp.raise_for_status()

    async def _push(self, to: str, messages: List[Dict[str, str]]) -> None:
        for batch in self._batched(messages, 5):
            resp = await self._client.post(
                "{base}/message/push".format(base=LINE_API_BASE),
                headers=self._headers,
                json={"to": to, "messages": batch},
            )
            resp.raise_for_status()

    def _chunk_text(self, text: str, limit: int = 4500) -> List[str]:
        text = (text or "").strip() or "(空訊息)"
        if len(text) <= limit:
            return [text]

        chunks = []
        current = ""
        for paragraph in text.splitlines(True):
            if len(current) + len(paragraph) <= limit:
                current += paragraph
                continue
            if current:
                chunks.append(current.rstrip())
                current = ""
            while len(paragraph) > limit:
                chunks.append(paragraph[:limit])
                paragraph = paragraph[limit:]
            current = paragraph
        if current:
            chunks.append(current.rstrip())
        return chunks or [text[:limit]]

    def _batched(self, items: List[Dict[str, str]], size: int) -> Iterable[List[Dict[str, str]]]:
        for idx in range(0, len(items), size):
            yield items[idx : idx + size]
