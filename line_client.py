from __future__ import annotations

from typing import Dict, Iterable, List

import httpx

LINE_API_BASE = "https://api.line.me/v2/bot/message"


class LineClient:
    def __init__(self, channel_access_token: str):
        self.channel_access_token = channel_access_token

    @property
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": "Bearer {token}".format(token=self.channel_access_token),
            "Content-Type": "application/json",
        }

    async def reply_text(self, reply_token: str, text: str) -> None:
        messages = [{"type": "text", "text": chunk} for chunk in self._chunk_text(text)]
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                "{base}/reply".format(base=LINE_API_BASE),
                headers=self._headers,
                json={"replyToken": reply_token, "messages": messages[:5]},
            )
            resp.raise_for_status()

    async def push_text(self, to: str, text: str) -> None:
        messages = [{"type": "text", "text": chunk} for chunk in self._chunk_text(text)]
        async with httpx.AsyncClient(timeout=20.0) as client:
            for batch in self._batched(messages, 5):
                resp = await client.post(
                    "{base}/push".format(base=LINE_API_BASE),
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
