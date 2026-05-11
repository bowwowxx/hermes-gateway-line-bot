from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

LINE_BRIDGE_PROMPT = (
    "你現在透過 LINE bot 和使用者對話。"
    "請直接回覆使用者可讀的內容，保持簡短、清楚、適合 LINE。"
    "不要輸出 session id、工具呼叫細節、路徑或內部除錯資訊，除非使用者真的需要。"
)


class HermesGatewayClient:
    def __init__(self, *, base_url: str, api_key: str = "", model: str = "hermes-agent"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    @property
    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer {token}".format(token=self.api_key)
        return headers

    async def ask(self, text: str, *, conversation: str, instructions: Optional[str] = None) -> str:
        payload = {
            "model": self.model,
            "input": text.strip(),
            "conversation": conversation,
            "instructions": instructions or LINE_BRIDGE_PROMPT,
            "store": True,
        }
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                "{base}/responses".format(base=self.base_url),
                headers=self._headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        return self._extract_text(data)

    def _extract_text(self, data: Dict[str, Any]) -> str:
        chunks = []
        for item in data.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    chunks.append(content.get("text", ""))
        text = "\n".join([chunk.strip() for chunk in chunks if chunk and chunk.strip()]).strip()
        return text or "（Hermes gateway 沒有回傳文字內容）"
